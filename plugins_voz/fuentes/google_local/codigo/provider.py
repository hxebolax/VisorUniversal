from __future__ import annotations

import threading
from typing import Any

from ..base import VoiceInfo
from ..pcm_provider import QueuedPcmProvider
from . import voice_store
from .assets import check_google_tts_assets
from .bridge import CdpCancelled, ChromeTtsBridge, SAMPLE_RATE
from .catalog import VoiceCatalog


class GoogleChromeProvider(QueuedPcmProvider):
    """Voces locales Google del motor WASM incluido en Chrome."""

    provider_id = "google_chrome"

    def __init__(self, config: dict[str, Any]):
        availability = check_google_tts_assets()
        if not availability.available:
            raise RuntimeError(availability.message)
        full_catalog = VoiceCatalog.load()
        self._catalog = VoiceCatalog(voice_store.installed_packages(full_catalog))
        self._bridge = ChromeTtsBridge(self._catalog)
        super().__init__(config)
        if not self._config.get("voz_id") and self._catalog.speakers:
            self._config["voz_id"] = self._catalog.speakers[0].id

    def voices(self) -> list[VoiceInfo]:
        return [
            VoiceInfo(
                speaker.id, f"{speaker.name} ({speaker.language})", speaker.language
            )
            for speaker in self._catalog.speakers
        ]

    def set_pitch(self, pitch: int) -> None:
        self._config["tono"] = max(0, min(100, int(pitch)))

    def set_rate_boost(self, enabled: bool) -> None:
        self._config["aceleracion"] = bool(enabled)

    def _start_engine(self) -> None:
        # Chrome y el WASM se preparan al crear el proveedor, no al pulsar
        # Reproducir por primera vez. Así la espera inicial suele quedar oculta.
        self._bridge.ensure_connection()

    def _synthesize(self, text: str, cancel: threading.Event) -> tuple[bytes, int]:
        voice_id = str(self._config.get("voz_id", ""))
        if voice_id not in {speaker.id for speaker in self._catalog.speakers}:
            voice_id = self._catalog.speakers[0].id
        speaker = self._catalog.speaker_for_voice(voice_id)
        volume = max(0, min(100, int(self._config.get("volumen", 100))))
        options = {
            "voiceId": speaker.id,
            "voiceName": speaker.name,
            "lang": speaker.language,
            "rate": self._rate_to_chrome(int(self._config.get("velocidad", 50))),
            "pitch": self._pitch_to_chrome(int(self._config.get("tono", 50))),
            "volume": volume / 100.0,
            "outputGain": max(0.0, min(2.0, volume / 50.0)),
        }
        chunks: list[bytes] = []
        try:
            self._bridge.speak(text, options, chunks.append, cancel)
        except CdpCancelled:
            return b"", SAMPLE_RATE
        return b"".join(chunks), SAMPLE_RATE

    def _stop_engine(self) -> None:
        self._bridge.cancel_current()

    def _close_engine(self) -> None:
        self._bridge.terminate()

    def _playback_volume_percent(self) -> int:
        # El motor WASM ya aplica volume y outputGain a las muestras PCM.
        return 100

    def _rate_to_chrome(self, value: int) -> float:
        percent = max(0, min(100, value)) / 100.0
        rate = 0.35 + (2.0 - 0.35) * percent
        if self._config.get("aceleracion", False):
            rate *= 2
        return round(max(0.1, min(10.0, rate)), 3)

    @staticmethod
    def _pitch_to_chrome(value: int) -> float:
        semitones = -12.0 + 24.0 * max(0, min(100, value)) / 100.0
        return round(max(0.1, min(3.0, 1.0 + semitones / 20.0)), 3)
