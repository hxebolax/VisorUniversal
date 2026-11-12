from __future__ import annotations

import hashlib
import json
import logging
import os
import struct
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..paths import TTS_CACHE_DIR

log = logging.getLogger(__name__)

_MAGIC = b"RSSTTS01"
_HEADER = struct.Struct("<8sI")
_CACHE_LOCK = threading.RLock()


@dataclass(frozen=True, slots=True)
class CacheStats:
    files: int
    bytes: int


def _audio_files(directory: Path = TTS_CACHE_DIR) -> list[Path]:
    if not directory.is_dir():
        return []
    return [path for path in directory.glob("*.audio") if path.is_file()]


def tts_cache_stats(directory: Path = TTS_CACHE_DIR) -> CacheStats:
    with _CACHE_LOCK:
        files = _audio_files(directory)
        return CacheStats(len(files), sum(path.stat().st_size for path in files))


def clear_tts_cache(directory: Path = TTS_CACHE_DIR) -> CacheStats:
    """Elimina solamente entradas reconocibles de la cach\u00e9 de audio."""
    with _CACHE_LOCK:
        files = _audio_files(directory)
        total = sum(path.stat().st_size for path in files)
        for path in files:
            path.unlink(missing_ok=True)
        if directory.is_dir():
            for path in directory.glob("*.tmp"):
                if path.is_file():
                    path.unlink(missing_ok=True)
        return CacheStats(len(files), total)


def format_size(byte_count: int) -> str:
    value = max(0, int(byte_count))
    if value < 1024:
        return f"{value} bytes"
    if value < 1024**2:
        return f"{value / 1024:.1f} KB"
    if value < 1024**3:
        return f"{value / 1024**2:.1f} MB"
    return f"{value / 1024**3:.1f} GB"


class TTSAudioCache:
    """Cach\u00e9 LRU portable para PCM o audio comprimido producido por un TTS."""

    def __init__(
        self,
        provider_id: str,
        config: dict[str, Any],
        directory: Path | None = None,
    ):
        self.provider_id = str(provider_id)
        self.config = config
        self.directory = Path(directory) if directory is not None else TTS_CACHE_DIR
        self.enabled = bool(config.get("_cache_enabled", False))
        self.maximum_bytes = max(
            10, int(config.get("_cache_max_mb", 500))
        ) * 1024**2

    def get(self, text: str) -> tuple[bytes, int] | None:
        if not self.enabled:
            return None
        path = self._path(text)
        with _CACHE_LOCK:
            try:
                raw = path.read_bytes()
                if len(raw) <= _HEADER.size:
                    raise ValueError("entrada vac\u00eda")
                magic, sample_rate = _HEADER.unpack(raw[: _HEADER.size])
                if magic != _MAGIC or not 8000 <= sample_rate <= 192000:
                    raise ValueError("cabecera no v\u00e1lida")
                os.utime(path, None)
                log.debug("Cach\u00e9 TTS reutilizada: %s", path.name)
                return raw[_HEADER.size :], int(sample_rate)
            except FileNotFoundError:
                return None
            except Exception:
                log.warning("Entrada de cach\u00e9 TTS da\u00f1ada: %s", path, exc_info=True)
                path.unlink(missing_ok=True)
                return None

    def put(self, text: str, audio: bytes, sample_rate: int) -> None:
        if not self.enabled or not audio:
            return
        path = self._path(text)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(
            f"{path.stem}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        payload = _HEADER.pack(_MAGIC, int(sample_rate)) + audio
        with _CACHE_LOCK:
            try:
                temporary.write_bytes(payload)
                os.replace(temporary, path)
                self._prune()
                log.debug("Audio guardado en cach\u00e9 TTS: %s", path.name)
            except Exception:
                # La cach\u00e9 es una optimizaci\u00f3n: nunca debe impedir que un
                # audio ya sintetizado llegue al reproductor.
                log.warning("No se pudo guardar la cach\u00e9 TTS", exc_info=True)
            finally:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    log.debug("No se pudo retirar el temporal %s", temporary)

    def _path(self, text: str) -> Path:
        public_config = {
            key: value
            for key, value in self.config.items()
            if not key.startswith("_") and key not in {"api_keys"}
        }
        material = json.dumps(
            {
                "format": 1,
                "provider": self.provider_id,
                "config": public_config,
                "text": str(text or "").strip(),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        digest = hashlib.sha256(material).hexdigest()
        return self.directory / f"{self.provider_id}-{digest}.audio"

    def _prune(self) -> None:
        files = sorted(
            _audio_files(self.directory), key=lambda item: item.stat().st_mtime
        )
        total = sum(path.stat().st_size for path in files)
        while files and total > self.maximum_bytes:
            oldest = files.pop(0)
            size = oldest.stat().st_size
            oldest.unlink(missing_ok=True)
            total -= size
