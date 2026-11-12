# -*- coding: UTF-8 -*-
"""
Proxy ECI para comunicación con la librería de 32 bits via IPC.

Proporciona una interfaz Pythónica que internamente usa Named Pipes
para comunicarse con el servidor Rust de 32 bits.
Expone todas las funciones de la API ECI.
"""

import logging
import os
import struct
from pathlib import Path

from .assets import eci_environment, update_eci_ini
from .ipc_client import (
    IBMTTSClient,
    HostIds,
    SharedMemoryListener,
    launch_host_32,
)

logger = logging.getLogger(__name__)


class EciProxy:
    """Proxy que expone la API ECI completa via IPC al servidor de 32 bits.

    Uso:
            proxy = EciProxy("C:/ruta/a/ECI.DLL")
            handle = proxy.eciNewEx(dialect_id)
            proxy.eciAddText(handle, b"Hola mundo")
            proxy.eciSynthesize(handle)
            proxy.eciSynchronize(handle)
            proxy.eciDelete(handle)
    """

    def __init__(self, dll_path: str, etidev_path: str = None):
        """Inicializa el proxy, lanza el servidor y carga la librería.

        Args:
                dll_path: Ruta a ECI.DLL.
                etidev_path: Ruta opcional a etidev.dll.
        """
        data_dir = Path(os.path.dirname(os.path.abspath(dll_path)))
        # Las voces se buscan **desde aquí**, y «aquí» no se sabe hasta este
        # momento: el paquete puede estar instalado en cualquier carpeta, y en
        # un equipo portátil hasta en una letra de unidad distinta cada día.
        try:
            update_eci_ini(data_dir)
        except (OSError, UnicodeError) as error:
            # Con el archivo sin poder reescribirse queda el otro camino: los
            # nombres sueltos que trae el paquete se resuelven contra el
            # directorio de trabajo, que es esta misma carpeta.
            logger.warning("No se ha podido actualizar %s: %s",
                           data_dir / "ECI.INI", error)
        launch_host_32(
            working_directory=str(data_dir),
            environment=eci_environment(data_dir),
        )
        self._client = IBMTTSClient()
        self._client.connect()
        self._shm = None
        self._callback = None

        if etidev_path:
            self._load_etidev(etidev_path)
        self._load_library(dll_path)
        logger.info("Proxy ECI inicializado con DLL: %s", dll_path)

    def _load_library(self, path: str):
        return self._client.call(HostIds.LOAD_LIBRARY, path)

    def _load_etidev(self, path: str):
        return self._client.call(HostIds.LOAD_ETIDEV, path)

    # ── Funciones del sistema ───────────────────────────────────────────

    def eciVersion(self) -> str:
        """Devuelve la versión de la librería ECI."""
        result = self._client.call(HostIds.ECI_VERSION)
        if isinstance(result, bytes):
            return result.decode("ascii", errors="replace")
        return str(result)

    def eciNew(self) -> int:
        """Crea una nueva instancia ECI."""
        return self._client.call(HostIds.ECI_NEW)

    def eciNewEx(self, dialect: int) -> int:
        """Crea una nueva instancia ECI con idioma específico."""
        return self._client.call(HostIds.ECI_NEW_EX, dialect)

    def eciDelete(self, handle: int) -> int:
        """Destruye una instancia ECI."""
        if self._shm:
            self._shm.stop()
            self._shm = None
        return self._client.call(HostIds.ECI_DELETE, handle)

    def eciReset(self, handle: int) -> int:
        """Resetea la instancia ECI al estado por defecto."""
        # No hay ID específico en el bridge, se simula con stop + clear
        self.eciStop(handle)
        return 1

    # ── Callbacks y buffer de audio ─────────────────────────────────────

    def eciRegisterCallback(self, handle: int, callback_func, user_data=None):
        """Registra un callback para eventos ECI."""
        self._callback = callback_func
        return 1

    def eciSetOutputBuffer(self, handle: int, samples: int):
        """Configura el buffer de salida y la memoria compartida."""
        if not self._callback:
            raise ValueError("Debe registrar un callback antes de configurar el buffer")
        if self._shm:
            self._shm.stop()
        self._client.call(HostIds.SET_BUFFER, handle, samples)
        self._shm = SharedMemoryListener(handle, samples, self._callback)
        return 1

    def get_audio_buffer_ptr(self):
        """Devuelve el puntero al buffer de audio en memoria compartida."""
        if self._shm:
            return self._shm.get_audio_buffer_ptr()
        return None

    # ── Control de síntesis ─────────────────────────────────────────────

    def eciAddText(self, handle: int, text) -> int:
        """Añade texto al buffer de entrada."""
        if isinstance(text, str):
            text = text.encode("cp1252", errors="replace")
        return self._client.call(HostIds.ECI_ADD_TEXT, handle, text)

    def eciInsertIndex(self, handle: int, index: int) -> int:
        """Inserta un índice en el buffer de entrada."""
        return self._client.call(HostIds.ECI_INSERT_INDEX, handle, index)

    def eciSynthesize(self, handle: int) -> int:
        """Inicia la síntesis del texto en el buffer."""
        return self._client.call(HostIds.ECI_SYNTHESIZE, handle)

    def eciStop(self, handle: int) -> int:
        """Detiene la síntesis en curso."""
        return self._client.call(HostIds.ECI_STOP, handle)

    def eciSynchronize(self, handle: int) -> int:
        """Espera a que termine la síntesis. No disponible via IPC, se simula."""
        # El bridge no expone eciSynchronize directamente.
        # La sincronización se maneja via callbacks.
        return 1

    # ── Parámetros de entorno ───────────────────────────────────────────

    def eciGetParam(self, handle: int, param_id: int) -> int:
        """Obtiene un parámetro de síntesis."""
        return self._client.call(HostIds.ECI_GET_PARAM, handle, param_id)

    def eciSetParam(self, handle: int, param_id: int, value: int) -> int:
        """Establece un parámetro de síntesis."""
        return self._client.call(HostIds.ECI_SET_PARAM, handle, param_id, value)

    # ── Parámetros de voz ───────────────────────────────────────────────

    def eciGetVoiceParam(self, handle: int, voice_id: int, param_id: int) -> int:
        """Obtiene un parámetro de voz."""
        return self._client.call(
            HostIds.ECI_GET_VOICE_PARAM, handle, voice_id, param_id
        )

    def eciSetVoiceParam(
        self, handle: int, voice_id: int, param_id: int, value: int
    ) -> int:
        """Establece un parámetro de voz."""
        return self._client.call(
            HostIds.ECI_SET_VOICE_PARAM, handle, voice_id, param_id, value
        )

    def eciCopyVoice(self, handle: int, from_idx: int, to_idx: int) -> int:
        """Copia una definición de voz."""
        return self._client.call(HostIds.ECI_COPY_VOICE, handle, from_idx, to_idx)

    # ── Diccionarios ────────────────────────────────────────────────────

    def eciNewDict(self, handle: int) -> int:
        """Crea un nuevo conjunto de diccionarios."""
        return self._client.call(HostIds.ECI_NEW_DICT, handle)

    def eciLoadDict(
        self, handle: int, dict_handle: int, dict_vol: int, filename: bytes
    ) -> int:
        """Carga un volumen de diccionario desde archivo."""
        return self._client.call(
            HostIds.ECI_LOAD_DICT, handle, dict_handle, dict_vol, filename
        )

    def eciSetDict(self, handle: int, dict_handle: int) -> int:
        """Establece el diccionario activo."""
        return self._client.call(HostIds.ECI_SET_DICT, handle, dict_handle)

    # ── Idiomas disponibles ─────────────────────────────────────────────

    def eciGetAvailableLanguages(self) -> list:
        """Devuelve lista de IDs de idiomas disponibles."""
        res = self._client.call(HostIds.ECI_GET_AVAILABLE_LANGUAGES)
        if isinstance(res, bytes):
            count = struct.unpack("<i", res[:4])[0]
            if count <= 0:
                return []
            return list(struct.unpack(f"<{count}i", res[4:]))
        return []

    def close(self):
        """Libera memoria compartida y cierra la tubería."""
        if self._shm:
            self._shm.stop()
            self._shm = None
        self._client.close()
