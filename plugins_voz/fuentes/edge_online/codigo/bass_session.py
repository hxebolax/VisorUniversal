from __future__ import annotations

import logging
import threading

from basskit.alto_nivel.reproductor import (
    inicializar,
    liberar,
    listar_dispositivos_salida,
)
from basskit.dlls.bass import bass
from basskit.excepciones import ErrorBassNativo

log = logging.getLogger(__name__)

_lock = threading.RLock()
_users = 0
_device = 0
_owned = False


def _current_or_initialized_device() -> int:
    current = int(bass.BASS_GetDevice())
    if current:
        return current
    devices = [item for item in listar_dispositivos_salida() if item.inicializado]
    if not devices:
        return 0
    preferred = next((item for item in devices if item.predeterminado), devices[0])
    return int(preferred.indice)


def _select_device(device: int) -> None:
    if not device or not bass.BASS_SetDevice(device):
        raise ErrorBassNativo(int(bass.BASS_ErrorGetCode()), "BASS_SetDevice")


def acquire_bass(device: int = -1, sample_rate: int = 44100) -> None:
    """Comparte una única inicialización BASS entre motores TTS simultáneos."""
    global _users, _device, _owned
    with _lock:
        if _users:
            _select_device(_device)
            _users += 1
            return

        owned = False
        try:
            inicializar(device, sample_rate)
            owned = True
        except ErrorBassNativo as exc:
            if exc.codigo != 14:
                raise
            # Puede haber una sesión de BASS creada por otro componente. Se
            # adopta sin liberarla al cerrar para no romper a su propietario.
            log.info("Se reutiliza una sesión BASS que ya estaba inicializada")

        selected = _current_or_initialized_device()
        if not selected:
            if owned:
                liberar()
            raise RuntimeError("BASS no informó de ningún dispositivo inicializado.")
        _select_device(selected)
        _device = selected
        _owned = owned
        _users = 1


def release_bass() -> None:
    """Libera BASS cuando desaparece el último motor que comparte la sesión."""
    global _users, _device, _owned
    with _lock:
        if _users <= 0:
            return
        _users -= 1
        if _users:
            return
        device = _device
        owned = _owned
        _device = 0
        _owned = False
        if not owned:
            return
        try:
            _select_device(device)
            liberar()
        except Exception:
            log.exception("No se pudo liberar la sesión BASS compartida")
