from __future__ import annotations

import asyncio
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ...paths import EDGE_TTS_DATA_DIR

CATALOG_FILE = EDGE_TTS_DATA_DIR / "voices_es.json"


@dataclass(frozen=True, slots=True)
class EdgeVoice:
    id: str
    locale: str
    gender: str
    name: str

    @property
    def display_name(self) -> str:
        gender = {"Female": "mujer", "Male": "hombre"}.get(
            self.gender, self.gender
        )
        return f"{self.name} ({self.locale}, {gender})"


def _parse_voice(raw: dict[str, Any]) -> EdgeVoice | None:
    locale = str(raw.get("Locale") or raw.get("locale") or "").strip()
    identifier = str(raw.get("ShortName") or raw.get("id") or "").strip()
    if not identifier or not locale.casefold().startswith("es-"):
        return None
    friendly = str(raw.get("name") or "").strip()
    if not friendly:
        friendly = identifier.rsplit("-", 1)[-1].removesuffix("Neural")
    return EdgeVoice(
        id=identifier,
        locale=locale,
        gender=str(raw.get("Gender") or raw.get("gender") or "").strip(),
        name=friendly,
    )


def load_spanish_voices(path: Path = CATALOG_FILE) -> list[EdgeVoice]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return []
    if not isinstance(raw, list):
        return []
    voices = [voice for item in raw if isinstance(item, dict) if (voice := _parse_voice(item))]
    return sorted(voices, key=lambda item: (item.locale.casefold(), item.name.casefold()))


async def _download_spanish_voices() -> list[EdgeVoice]:
    import edge_tts

    raw = await edge_tts.list_voices()
    voices = [voice for item in raw if (voice := _parse_voice(dict(item)))]
    if not voices:
        raise RuntimeError("Microsoft no devolvió ninguna voz española de Edge.")
    return sorted(voices, key=lambda item: (item.locale.casefold(), item.name.casefold()))


def refresh_spanish_voices(path: Path = CATALOG_FILE) -> list[EdgeVoice]:
    """Descarga el catálogo y lo sustituye atómicamente solo si es válido."""
    voices = asyncio.run(_download_spanish_voices())
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="edge_voces_", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump([asdict(voice) for voice in voices], stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return voices
