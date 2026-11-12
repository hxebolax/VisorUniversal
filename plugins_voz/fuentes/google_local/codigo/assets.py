from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ...paths import GOOGLE_TTS_DATA_DIR
from .bridge import ChromeTtsBridge
from .catalog import CATALOG_PATH, ENGINE_DIR, VoiceCatalog
from .voice_store import installed_packages


@dataclass(frozen=True, slots=True)
class GoogleTtsAvailability:
    available: bool
    message: str
    data_dir: Path
    chrome_path: str = ""
    voice_count: int = 0


def check_google_tts_assets() -> GoogleTtsAvailability:
    required = [
        CATALOG_PATH,
        ENGINE_DIR / "bindings_main.wasm",
        GOOGLE_TTS_DATA_DIR / "web" / "index.html",
        GOOGLE_TTS_DATA_DIR / "web" / "bridgeHarness.js",
    ]
    missing = [path.name for path in required if not path.is_file()]
    if missing:
        return GoogleTtsAvailability(
            False,
            "Google TTS local no está disponible; faltan: " + ", ".join(missing) + ".",
            GOOGLE_TTS_DATA_DIR,
        )
    try:
        catalog = VoiceCatalog.load()
        packages = installed_packages(catalog)
        voice_count = sum(len(package.speakers) for package in packages)
    except Exception as exc:
        return GoogleTtsAvailability(
            False,
            f"Google TTS local no pudo validar su catálogo: {exc}.",
            GOOGLE_TTS_DATA_DIR,
        )
    if not packages or not voice_count:
        return GoogleTtsAvailability(
            False,
            "Google TTS local no tiene ningún paquete de voces válido en data\\google_tts\\voices.",
            GOOGLE_TTS_DATA_DIR,
        )
    chrome = ChromeTtsBridge.find_chrome() or ""
    if not chrome:
        return GoogleTtsAvailability(
            False,
            "Google TTS local necesita Google Chrome instalado.",
            GOOGLE_TTS_DATA_DIR,
            voice_count=voice_count,
        )
    return GoogleTtsAvailability(
        True,
        f"Google TTS local está disponible con {voice_count} voces instaladas.",
        GOOGLE_TTS_DATA_DIR,
        chrome,
        voice_count,
    )


def installed_google_voices() -> list[tuple[str, str, str]]:
    try:
        catalog = VoiceCatalog(installed_packages(VoiceCatalog.load()))
    except Exception:
        return []
    return [
        (speaker.id, f"{speaker.name} ({speaker.language})", speaker.language)
        for speaker in catalog.speakers
    ]
