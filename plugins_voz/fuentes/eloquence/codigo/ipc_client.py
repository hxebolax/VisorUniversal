# -*- coding: UTF-8 -*-
"""
Cliente IPC para comunicación con el servidor Rust de 32 bits.

Implementa el protocolo de Named Pipes y Shared Memory para
comunicarse con ibmtts_host32.dll, permitiendo que Python de 64 bits
use las librerías ECI de 32 bits.

Protocolo:
        - Named Pipe en modo mensaje para comandos/respuestas.
        - Shared Memory + Events para callbacks de audio en tiempo real.
"""

import ctypes
from ctypes import wintypes, byref
import logging
import os
import subprocess
import threading
import time

from ...paths import LIB_DIR

logger = logging.getLogger(__name__)

# Constantes de Windows
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
ERROR_PIPE_BUSY = 231
PIPE_READMODE_MESSAGE = 0x00000002
FILE_MAP_WRITE = 0x0002
FILE_MAP_READ = 0x0004
SYNCHRONIZE = 0x00100000
INFINITE = 0xFFFFFFFF
PIPE_NAME = r"\\.\pipe\ibmtts_host32"
PIPE_SIZE = 65536

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# Configurar funciones de Win32
kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HANDLE,
]
kernel32.CreateFileW.restype = wintypes.HANDLE

kernel32.WriteFile.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.c_void_p,
]
kernel32.WriteFile.restype = wintypes.BOOL

kernel32.ReadFile.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.c_void_p,
]
kernel32.ReadFile.restype = wintypes.BOOL

OpenFileMappingW = kernel32.OpenFileMappingW
OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
OpenFileMappingW.restype = wintypes.HANDLE

MapViewOfFile = kernel32.MapViewOfFile
MapViewOfFile.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.c_size_t,
]
MapViewOfFile.restype = wintypes.LPVOID

UnmapViewOfFile = kernel32.UnmapViewOfFile
UnmapViewOfFile.argtypes = [wintypes.LPCVOID]
UnmapViewOfFile.restype = wintypes.BOOL

OpenEventW = kernel32.OpenEventW
OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
OpenEventW.restype = wintypes.HANDLE

WaitForSingleObject = kernel32.WaitForSingleObject
WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
WaitForSingleObject.restype = wintypes.DWORD

WaitNamedPipeW = kernel32.WaitNamedPipeW
WaitNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
WaitNamedPipeW.restype = wintypes.BOOL

CloseHandle = kernel32.CloseHandle


# ── IDs de funciones del protocolo ──────────────────────────────────────


class HostIds:
    """Identificadores de funciones del protocolo IPC."""

    LOAD_LIBRARY = 1
    ECI_VERSION = 2
    ECI_NEW = 3
    ECI_NEW_EX = 4
    SET_BUFFER = 5
    ECI_ADD_TEXT = 6
    ECI_INSERT_INDEX = 7
    ECI_SYNTHESIZE = 8
    ECI_GET_AVAILABLE_LANGUAGES = 9
    ECI_STOP = 10
    ECI_GET_PARAM = 11
    ECI_SET_PARAM = 12
    ECI_GET_VOICE_PARAM = 13
    ECI_SET_VOICE_PARAM = 14
    ECI_COPY_VOICE = 15
    ECI_NEW_DICT = 16
    ECI_LOAD_DICT = 17
    ECI_SET_DICT = 18
    ECI_DELETE = 19
    LOAD_ETIDEV = 242


# ── Empaquetado/desempaquetado del protocolo ────────────────────────────


def pack(func_id: int, *args) -> bytes:
    """Empaqueta un mensaje según el protocolo IPC.

    Args:
            func_id: ID de la función (u16).
            *args: Mezcla de enteros y cadenas/bytes.

    Returns:
            Mensaje empaquetado listo para enviar.
    """
    # Caso especial: un solo argumento string (para load_library)
    if len(args) == 1 and isinstance(args[0], str):
        return (
            func_id.to_bytes(2, "little", signed=False)
            + args[0].encode("utf-8")
            + b"\x00"
        )

    payload = func_id.to_bytes(2, "little", signed=False)
    string_start = 2 + (len(args) * 4)
    string_data = b""

    for arg in args:
        if isinstance(arg, bytes):
            payload += (string_start + len(string_data)).to_bytes(
                4, "little", signed=False
            )
            string_data += arg + b"\x00"
        elif isinstance(arg, int):
            payload += arg.to_bytes(4, "little", signed=True)
        else:
            raise TypeError(f"Tipo de argumento no soportado: {type(arg).__name__}")

    payload += string_data
    return payload


def parse_response(data: bytes):
    """Parsea una respuesta del servidor.

    Formato:
            byte 0: tipo (0=int con signo, 1=uint, 2=bytes, 3=utf-8, 4=error)
            bytes 1+: datos según el tipo.
    """
    if len(data) < 1:
        raise ValueError("Respuesta vacía del servidor")

    resp_type = data[0]
    resp_data = data[1:]

    if resp_type == 0:  # signed int
        return int.from_bytes(resp_data, "little", signed=True)
    elif resp_type == 1:  # unsigned int
        return int.from_bytes(resp_data, "little", signed=False)
    elif resp_type == 2:  # byte string
        return resp_data
    elif resp_type == 3:  # utf-8 string
        return resp_data.decode("utf-8", errors="ignore")
    elif resp_type == 4:  # error
        raise RuntimeError(
            "Error del servidor: " + resp_data.decode("utf-8", errors="ignore")
        )
    else:
        raise ValueError(f"Tipo de respuesta desconocido: {resp_type}")


# ── Shared Memory para callbacks de audio ───────────────────────────────


class SharedHeader(ctypes.LittleEndianStructure):
    """Header de la memoria compartida (12 bytes)."""

    _pack_ = 1
    _fields_ = [
        ("eciHandle", wintypes.DWORD),
        ("msg", wintypes.DWORD),
        ("lparam", wintypes.LONG),
    ]


class SharedMemoryListener:
    """Escucha callbacks de audio via memoria compartida.

    El servidor Rust escribe datos de audio en la memoria compartida
    y señaliza con un evento. Este listener lee los datos y los pasa
    al callback de Python.
    """

    def __init__(self, eci_id: int, samples_capacity: int, callback):
        self.eci_id = eci_id
        self.total_size = (samples_capacity * 2) + 12
        self.callback = callback

        self.shm_name = f"Local\\eci_shm_{eci_id:x}"
        self.evt_ready_name = f"Local\\eci_ready_{eci_id:x}"
        self.evt_proc_name = f"Local\\eci_proc_{eci_id:x}"

        self.h_map = None
        self.view = None
        self._h_evt_ready = None
        self.h_evt_proc = None
        self.header = None

        self._stop_event = kernel32.CreateEventW(None, True, False, None)
        self._open_resources()
        self._thread = threading.Thread(
            target=self._worker_loop,
            name=f"ECI_Audio_{eci_id:x}",
            daemon=True,
        )
        self._thread.start()

    def _open_resources(self):
        """Abre los recursos de memoria compartida y eventos."""
        self.h_map = OpenFileMappingW(FILE_MAP_WRITE, False, self.shm_name)
        if not self.h_map:
            raise OSError(ctypes.get_last_error(), "Memoria compartida no encontrada")

        self.view = MapViewOfFile(self.h_map, FILE_MAP_WRITE, 0, 0, self.total_size)
        if not self.view:
            raise OSError(ctypes.get_last_error(), "MapViewOfFile falló")

        self.header = SharedHeader.from_address(self.view)
        self._h_evt_ready = OpenEventW(SYNCHRONIZE | 0x0002, False, self.evt_ready_name)
        self.h_evt_proc = OpenEventW(SYNCHRONIZE | 0x0002, False, self.evt_proc_name)

    def _worker_loop(self):
        """Bucle principal que espera callbacks del servidor."""
        handles = (wintypes.HANDLE * 2)(self._stop_event, self._h_evt_ready)
        try:
            while True:
                res = kernel32.WaitForMultipleObjects(
                    2, byref(handles), False, INFINITE
                )
                if res == 0:  # stop
                    break
                elif res == 1:  # callback del servidor
                    handle = self.header.eciHandle
                    msg = self.header.msg
                    lparam = self.header.lparam
                    return_val = self.callback(handle, msg, lparam, 0)
                    self.header.eciHandle = return_val
                    kernel32.SetEvent(self.h_evt_proc)
        except Exception as e:
            logger.error("Error en hilo de memoria compartida %x: %s", self.eci_id, e)
        finally:
            self._cleanup()

    def get_audio_buffer_ptr(self):
        """Devuelve puntero al buffer de audio (byte 12 en adelante)."""
        if not self.view:
            return None
        return self.view + 12

    def stop(self):
        """Detiene el listener."""
        kernel32.SetEvent(self._stop_event)

    def _cleanup(self):
        """Libera recursos."""
        if self.view:
            UnmapViewOfFile(self.view)
        if self.h_map:
            CloseHandle(self.h_map)
        if self._h_evt_ready:
            CloseHandle(self._h_evt_ready)
        if self.h_evt_proc:
            CloseHandle(self.h_evt_proc)


# ── Cliente IPC principal ───────────────────────────────────────────────


class IBMTTSClient:
    """Cliente de Named Pipe para comunicarse con el servidor Rust."""

    def __init__(self, pipe_name: str = PIPE_NAME):
        self.pipe_name = pipe_name
        self.h_pipe = None

    def connect(self):
        """Conecta al Named Pipe del servidor."""
        while True:
            self.h_pipe = kernel32.CreateFileW(
                self.pipe_name,
                GENERIC_READ | GENERIC_WRITE,
                0,
                None,
                OPEN_EXISTING,
                0,
                None,
            )
            if self.h_pipe != INVALID_HANDLE_VALUE:
                break
            err = ctypes.get_last_error()
            if err != ERROR_PIPE_BUSY:
                raise ConnectionError(f"No se pudo conectar al pipe. Error: {err}")
            WaitNamedPipeW(self.pipe_name, 2000)

    def _send_request(self, data: bytes) -> bytes:
        """Envía un mensaje y recibe la respuesta."""
        written = wintypes.DWORD(0)
        if not kernel32.WriteFile(self.h_pipe, data, len(data), byref(written), None):
            raise OSError(ctypes.get_last_error(), "WriteFile falló")

        buf = ctypes.create_string_buffer(PIPE_SIZE)
        read = wintypes.DWORD(0)
        if not kernel32.ReadFile(self.h_pipe, buf, PIPE_SIZE, byref(read), None):
            raise OSError(ctypes.get_last_error(), "ReadFile falló")

        return buf.raw[: read.value]

    def call(self, func_id: int, *args):
        """Envía una petición y espera la respuesta parseada."""
        return parse_response(self._send_request(pack(func_id, *args)))

    def close(self):
        """Cierra la tubería del cliente."""
        if self.h_pipe not in (None, INVALID_HANDLE_VALUE):
            CloseHandle(self.h_pipe)
        self.h_pipe = None


# ── Gestión del proceso host de 32 bits ─────────────────────────────────

_process_host32 = None
_host_users = 0
_host_lock = threading.Lock()


def get_bridge_dll_path() -> str:
    """Devuelve la ruta a ibmtts_host32.dll."""
    return str(LIB_DIR / "ibmtts_host32.dll")


def launch_host_32(timeout: float = 5.0, working_directory: str | None = None,
                   environment: dict | None = None):
    """Lanza el servidor de 32 bits y espera a que el pipe esté disponible.

    :param environment: Entorno con el que arranca el proceso. Es por donde
                        viaja ``ECIINI``, que es lo que le dice a ECI qué
                        ``ECI.INI`` tiene que leer; ``None`` hereda el de este
                        proceso.
    """
    global _process_host32, _host_users
    pid = os.getpid()

    with _host_lock:
        if _process_host32 and _process_host32.poll() is None:
            _host_users += 1
            return _process_host32

    dll_path = get_bridge_dll_path()
    if not os.path.exists(dll_path):
        raise FileNotFoundError(f"DLL del servidor no encontrada: {dll_path}")

    system_root = os.environ.get("SystemRoot", "C:\\Windows")
    rundll32 = os.path.join(system_root, "SysWOW64", "rundll32.exe")
    if not os.path.exists(rundll32):
        rundll32 = os.path.join(system_root, "System32", "rundll32.exe")

    _process_host32 = subprocess.Popen(
        [rundll32, f"{dll_path},StartHost", str(pid)],
        cwd=working_directory or os.path.dirname(dll_path),
        env=environment,
        creationflags=0x08000000,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    with _host_lock:
        _host_users = 1

    start_time = time.time()
    while (time.time() - start_time) < timeout:
        if WaitNamedPipeW(PIPE_NAME, 100):
            logger.info("Servidor de 32 bits iniciado correctamente")
            return _process_host32
        if _process_host32.poll() is not None:
            exit_code = _process_host32.returncode
            _process_host32 = None
            raise RuntimeError(
                f"El servidor de 32 bits terminó inesperadamente. Código: {exit_code}"
            )
        time.sleep(0.1)

    terminate_host_32()
    raise TimeoutError("El servidor de 32 bits no respondió a tiempo")


def terminate_host_32(force: bool = False):
    """Termina el proceso del servidor de 32 bits."""
    global _process_host32, _host_users
    with _host_lock:
        if not force and _host_users > 0:
            _host_users -= 1
        if not force and _host_users > 0:
            return
        _host_users = 0
    if _process_host32:
        try:
            _process_host32.terminate()
            _process_host32.wait(timeout=1.0)
        except Exception:
            try:
                _process_host32.kill()
            except Exception:
                pass
        finally:
            _process_host32 = None
