from __future__ import annotations

import asyncio
import ctypes
import threading
from typing import Any

from basskit.constantes.bass import BASS_STREAM_PRESCAN
from basskit.dlls.bass import bass

from ..base import VoiceInfo
from ..pcm_provider import QueuedPcmProvider
from .assets import check_edge_tts_available
from .catalog import EdgeVoice, load_spanish_voices


class EdgeTTSProvider(QueuedPcmProvider):
    """Voces neuronales online usadas por la función Leer en voz alta de Edge."""

    provider_id = "edge"

    def __init__(self, config: dict[str, Any]):
        availability = check_edge_tts_available()
        if not availability.available:
            raise RuntimeError(availability.message)
        self._voices = load_spanish_voices()
        if not self._voices:
            raise RuntimeError("No está disponible el catálogo español de voces de Edge.")
        super().__init__(config)
        identifiers = {voice.id for voice in self._voices}
        if self._config.get("voz_id") not in identifiers:
            preferred = next(
                (voice for voice in self._voices if voice.id == "es-ES-ElviraNeural"),
                self._voices[0],
            )
            self._config["voz_id"] = preferred.id

    def voices(self) -> list[VoiceInfo]:
        return [
            VoiceInfo(voice.id, voice.display_name, voice.locale)
            for voice in self._voices
        ]

    def set_pitch(self, pitch: int) -> None:
        self._config["tono"] = max(0, min(100, int(pitch)))

    @staticmethod
    def _rate_argument(value: int) -> str:
        return f"{(max(0, min(100, int(value))) - 50) * 2:+d}%"

    @staticmethod
    def _pitch_argument(value: int) -> str:
        return f"{max(-50, min(50, int(value) - 50)):+d}Hz"

    def _synthesize(self, text: str, cancel: threading.Event) -> tuple[bytes, int]:
        voice_ids = {voice.id for voice in self._voices}
        voice_id = str(self._config.get("voz_id", ""))
        if voice_id not in voice_ids:
            voice_id = self._voices[0].id

        async def collect() -> bytes:
            import edge_tts

            communicator = edge_tts.Communicate(
                text,
                voice=voice_id,
                rate=self._rate_argument(self._config.get("velocidad", 50)),
                volume="+0%",
                pitch=self._pitch_argument(self._config.get("tono", 50)),
            )
            chunks: list[bytes] = []
            async for event in communicator.stream():
                if cancel.is_set():
                    break
                if event.get("type") == "audio":
                    chunks.append(bytes(event["data"]))
            return b"".join(chunks)

        if cancel.is_set():
            return b"", 24000
        return asyncio.run(collect()), 24000

    @staticmethod
    def _open_pcm(audio: bytes, _sample_rate: int) -> tuple[int, ctypes.Array]:
        """Abre el MP3 recibido sin convertirlo ni escribir archivos temporales."""
        memory = ctypes.create_string_buffer(audio)
        channel = bass.BASS_StreamCreateFile(
            1,
            ctypes.cast(memory, ctypes.c_void_p),
            0,
            len(audio),
            BASS_STREAM_PRESCAN,
        )
        if not channel:
            raise RuntimeError(
                f"BASS no pudo abrir el audio de Edge; error {bass.BASS_ErrorGetCode()}."
            )
        return int(channel), memory
