from __future__ import annotations

import ctypes
import io
import logging
import queue
import threading
import wave
from typing import Any

from basskit.constantes.bass import (
    BASS_ACTIVE_PAUSED,
    BASS_ACTIVE_PLAYING,
    BASS_STREAM_PRESCAN,
)
from basskit.dlls.bass import bass

from ..base import BaseTTSProvider, TTSState, VoiceInfo
from ..bass_session import acquire_bass, release_bass
from .assets import check_eloquence_assets
from .engine import ECIEngine, PARAM_SPEED, PARAM_VOLUME, VOICE_VARIANTS

log = logging.getLogger(__name__)


class EloquenceProvider(BaseTTSProvider):
    """Eloquence con síntesis x86 aislada y reproducción BASS x64."""

    provider_id = "eloquence"
    rate_min = 0
    rate_max = 100

    def __init__(self, config: dict[str, Any]):
        super().__init__()
        availability = check_eloquence_assets()
        if not availability.available:
            raise RuntimeError(availability.message)
        self._config = dict(config)
        self._availability = availability
        self._commands: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._closed = threading.Event()
        self._pause_requested = threading.Event()
        self._cancel_lock = threading.Lock()
        self._current_cancel = threading.Event()
        self._state = TTSState.STOPPED
        self._startup_error = ""
        self._thread = threading.Thread(
            target=self._run, name="tts-eloquence", daemon=True
        )
        self._thread.start()

    @property
    def state(self) -> TTSState:
        return self._state

    def voices(self) -> list[VoiceInfo]:
        language = str(self._config.get("idioma", "esp"))
        return [
            VoiceInfo(str(identifier), name, language)
            for identifier, name in VOICE_VARIANTS.items()
        ]

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
        try:
            self._config["variante"] = max(1, min(8, int(voice_id)))
        except (TypeError, ValueError):
            pass

    def set_rate(self, rate: int) -> None:
        value = max(0, min(100, int(rate)))
        self._config["velocidad"] = value
        self._commands.put(("rate", value))

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
        self._thread.join(timeout=4)

    def _emit_state(self, state: TTSState) -> None:
        self._state = state
        if self.on_state:
            self.on_state(state)

    def _emit_error(self, message: str) -> None:
        self._startup_error = message
        self._emit_state(TTSState.ERROR)
        if self.on_error:
            self.on_error(message)

    def _run(self) -> None:
        engine: ECIEngine | None = None
        channel = 0
        memory: ctypes.Array | None = None
        natural_finish = False
        bass_ready = False
        try:
            engine = ECIEngine(self._availability.dll_path)
            engine.initialize(self._config)
            acquire_bass(-1, 44100)
            bass_ready = True
        except Exception as exc:
            log.exception("No se pudo iniciar Eloquence")
            self._emit_error(f"No se pudo iniciar Eloquence: {exc}")

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
                    if engine:
                        engine.stop()
                    self._emit_state(TTSState.STOPPED)
                elif command == "pause" and channel:
                    bass.BASS_ChannelPause(channel)
                    self._emit_state(TTSState.PAUSED)
                elif command == "resume" and channel:
                    bass.BASS_ChannelPlay(channel, 0)
                    self._emit_state(TTSState.PLAYING)
                elif command == "rate" and engine:
                    engine.set_voice_param(PARAM_SPEED, int(value))
                elif command == "volume" and engine:
                    engine.set_voice_param(PARAM_VOLUME, int(value))
                elif command == "speak":
                    text, cancel = value
                    channel = self._free_channel(channel)
                    memory = None
                    natural_finish = False
                    if not engine or not bass_ready:
                        if self._startup_error:
                            self._emit_error(self._startup_error)
                        continue
                    pcm = engine.synthesize(text, cancel)
                    if cancel.is_set() or not pcm:
                        continue
                    channel, memory = self._open_pcm(pcm, engine.sample_rate)
                    bass.BASS_ChannelPlay(channel, 1)
                    natural_finish = True
                    if self._pause_requested.is_set():
                        bass.BASS_ChannelPause(channel)
                        self._emit_state(TTSState.PAUSED)
                    else:
                        self._emit_state(TTSState.PLAYING)
            except Exception as exc:
                log.exception("Error de Eloquence al ejecutar %s", command)
                channel = self._free_channel(channel)
                memory = None
                natural_finish = False
                self._emit_error(str(exc))

            # BASS lee directamente este bloque; la referencia debe vivir mientras exista el canal.
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

        channel = self._free_channel(channel)
        if engine:
            try:
                engine.close()
            except Exception:
                log.exception("No se pudo cerrar por completo Eloquence")
        if bass_ready:
            try:
                release_bass()
            except Exception:
                log.exception("No se pudo liberar el dispositivo BASS de Eloquence")

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
                f"BASS no pudo abrir el audio de Eloquence; error {bass.BASS_ErrorGetCode()}."
            )
        return int(channel), memory
