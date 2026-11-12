from __future__ import annotations

import ctypes
import io
import logging
import queue
import threading
import wave
from abc import abstractmethod
from typing import Any

from basskit.constantes.bass import (
    BASS_ACTIVE_PAUSED,
    BASS_ACTIVE_PLAYING,
    BASS_ATTRIB_VOL,
    BASS_STREAM_PRESCAN,
)
from basskit.dlls.bass import bass

from .base import BaseTTSProvider, TTSState
from .bass_session import acquire_bass, release_bass
from .cache import TTSAudioCache

log = logging.getLogger(__name__)


class QueuedPcmProvider(BaseTTSProvider):
    """Base asíncrona para motores que devuelven PCM mono de 16 bits."""

    rate_min = 0
    rate_max = 100

    def __init__(self, config: dict[str, Any]):
        super().__init__()
        self._config = dict(config)
        self._audio_cache = TTSAudioCache(self.provider_id, self._config)
        self._commands: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._closed = threading.Event()
        self._pause_requested = threading.Event()
        self._cancel_lock = threading.Lock()
        self._current_cancel = threading.Event()
        self._state = TTSState.STOPPED
        self._thread = threading.Thread(
            target=self._run,
            name=f"tts-{self.provider_id}",
            daemon=True,
        )
        self._thread.start()

    @property
    def state(self) -> TTSState:
        return self._state

    def speak(self, text: str) -> None:
        if not text.strip():
            return
        with self._cancel_lock:
            self._current_cancel.set()
            self._current_cancel = threading.Event()
            cancel = self._current_cancel
        self._pause_requested.clear()
        self._commands.put(("speak", (text.strip(), cancel)))

    def pause(self) -> None:
        self._pause_requested.set()
        self._commands.put(("pause", None))

    def resume(self) -> None:
        self._pause_requested.clear()
        self._commands.put(("resume", None))

    def stop(self) -> None:
        with self._cancel_lock:
            self._current_cancel.set()
        self._pause_requested.clear()
        self._commands.put(("stop", None))

    def set_voice(self, voice_id: str) -> None:
        self._config["voz_id"] = str(voice_id or "")

    def set_rate(self, rate: int) -> None:
        self._config["velocidad"] = max(self.rate_min, min(self.rate_max, int(rate)))

    def set_volume(self, volume: int) -> None:
        value = max(0, min(100, int(volume)))
        self._config["volumen"] = value
        self._commands.put(("volume", value))

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        with self._cancel_lock:
            self._current_cancel.set()
        self._commands.put(("close", None))
        self._thread.join(timeout=5)

    def _emit_state(self, state: TTSState) -> None:
        self._state = state
        if self.on_state:
            self.on_state(state)

    def _emit_error(self, message: str) -> None:
        self._emit_state(TTSState.ERROR)
        if self.on_error:
            self.on_error(message)

    def _run(self) -> None:
        channel = 0
        memory: ctypes.Array | None = None
        natural_finish = False
        bass_ready = False
        try:
            self._start_engine()
            acquire_bass(-1, 44100)
            bass_ready = True
        except Exception as exc:
            log.exception("No se pudo iniciar %s", self.provider_id)
            self._emit_error(str(exc))

        while not self._closed.is_set():
            try:
                command, value = self._commands.get(timeout=0.025)
            except queue.Empty:
                command, value = "", None
            try:
                if command == "close":
                    break
                if command == "stop":
                    channel = self._free_channel(channel)
                    memory = None
                    natural_finish = False
                    self._stop_engine()
                    self._emit_state(TTSState.STOPPED)
                elif command == "pause" and channel:
                    bass.BASS_ChannelPause(channel)
                    self._emit_state(TTSState.PAUSED)
                elif command == "resume" and channel:
                    bass.BASS_ChannelPlay(channel, 0)
                    self._emit_state(TTSState.PLAYING)
                elif command == "volume" and channel:
                    bass.BASS_ChannelSetAttribute(
                        channel, BASS_ATTRIB_VOL, int(value) / 100.0
                    )
                elif command == "speak":
                    text, cancel = value
                    channel = self._free_channel(channel)
                    memory = None
                    natural_finish = False
                    if not bass_ready:
                        continue
                    cached = self._audio_cache.get(text)
                    if cached is None:
                        pcm, sample_rate = self._synthesize(text, cancel)
                        if not cancel.is_set() and pcm:
                            self._audio_cache.put(text, pcm, sample_rate)
                    else:
                        pcm, sample_rate = cached
                    if cancel.is_set() or not pcm:
                        continue
                    channel, memory = self._open_pcm(pcm, sample_rate)
                    bass.BASS_ChannelSetAttribute(
                        channel,
                        BASS_ATTRIB_VOL,
                        self._playback_volume_percent() / 100.0,
                    )
                    bass.BASS_ChannelPlay(channel, 1)
                    natural_finish = True
                    if self._pause_requested.is_set():
                        bass.BASS_ChannelPause(channel)
                        self._emit_state(TTSState.PAUSED)
                    else:
                        self._emit_state(TTSState.PLAYING)
            except Exception as exc:
                log.exception("Error de %s al ejecutar %s", self.provider_id, command)
                channel = self._free_channel(channel)
                memory = None
                natural_finish = False
                if not self._closed.is_set():
                    self._emit_error(str(exc))

            _ = memory
            if channel and bass.BASS_ChannelIsActive(channel) not in (
                BASS_ACTIVE_PLAYING,
                BASS_ACTIVE_PAUSED,
            ):
                channel = self._free_channel(channel)
                memory = None
                self._emit_state(TTSState.STOPPED)
                if natural_finish and self.on_finished:
                    natural_finish = False
                    self.on_finished()

        self._free_channel(channel)
        try:
            self._close_engine()
        except Exception:
            log.exception("No se pudo cerrar por completo %s", self.provider_id)
        if bass_ready:
            try:
                release_bass()
            except Exception:
                log.exception("No se pudo liberar BASS para %s", self.provider_id)

    def _start_engine(self) -> None:
        """Permite que el motor prepare recursos antes del primer texto."""

    def _stop_engine(self) -> None:
        """Cancela trabajo interno adicional al evento de cancelación."""

    def _close_engine(self) -> None:
        """Libera recursos propios del motor."""

    def _playback_volume_percent(self) -> int:
        return max(0, min(100, int(self._config.get("volumen", 100))))

    @abstractmethod
    def _synthesize(self, text: str, cancel: threading.Event) -> tuple[bytes, int]: ...

    @staticmethod
    def _free_channel(channel: int) -> int:
        if channel:
            bass.BASS_ChannelStop(channel)
            bass.BASS_StreamFree(channel)
        return 0

    @staticmethod
    def _open_pcm(pcm: bytes, sample_rate: int) -> tuple[int, ctypes.Array]:
        wav_data = io.BytesIO()
        with wave.open(wav_data, "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(sample_rate)
            stream.writeframes(pcm)
        raw = wav_data.getvalue()
        memory = ctypes.create_string_buffer(raw)
        channel = bass.BASS_StreamCreateFile(
            1,
            ctypes.cast(memory, ctypes.c_void_p),
            0,
            len(raw),
            BASS_STREAM_PRESCAN,
        )
        if not channel:
            raise RuntimeError(
                f"BASS no pudo abrir el audio; error {bass.BASS_ErrorGetCode()}."
            )
        return int(channel), memory
