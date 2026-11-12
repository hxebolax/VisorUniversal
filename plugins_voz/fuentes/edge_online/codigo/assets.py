from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class EdgeAvailability:
    available: bool
    message: str
    executable: Path | None = None


def find_edge() -> Path | None:
    """Localiza msedge.exe sin depender del disco ni del idioma de Windows."""
    candidates: list[Path] = []
    configured = os.environ.get("EDGE_PATH", "").strip().strip('"')
    if configured:
        candidates.append(Path(configured))

    try:
        import winreg

        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(
                        root,
                        r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
                        0,
                        winreg.KEY_READ | view,
                    ) as key:
                        value, _kind = winreg.QueryValueEx(key, "")
                        candidates.append(Path(str(value).strip().strip('"')))
                except OSError:
                    pass
    except ImportError:
        pass

    for variable in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        root = os.environ.get(variable)
        if root:
            candidates.append(
                Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
            )

    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            continue
        marker = os.path.normcase(str(resolved))
        if marker in seen:
            continue
        seen.add(marker)
        if resolved.is_file():
            return resolved
    return None


def check_edge_tts_available() -> EdgeAvailability:
    executable = find_edge()
    if executable is None:
        return EdgeAvailability(
            False,
            "Microsoft Edge no está instalado. Este motor no se ofrece.",
        )
    try:
        import edge_tts  # noqa: F401
    except Exception as exc:
        return EdgeAvailability(
            False,
            f"Microsoft Edge está instalado, pero falta el componente edge-tts: {exc}",
            executable,
        )
    return EdgeAvailability(
        True,
        "Microsoft Edge detectado. Las voces de este motor son online y necesitan Internet.",
        executable,
    )
