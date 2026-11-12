from __future__ import annotations

import ctypes
import logging
import os
import re
import struct
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from ...paths import ELOQUENCE_DATA_DIR, LIB_DIR

log = logging.getLogger(__name__)
_eci_ini_lock = threading.RLock()


@dataclass(frozen=True, slots=True)
class EloquenceAvailability:
    available: bool
    message: str
    bridge_path: Path
    dll_path: Path
    data_dir: Path
    supports_22khz: bool = False


def _is_32_bit_pe(path: Path) -> bool:
    """Comprueba que el ejecutable PE sea x86 sin llegar a cargarlo."""
    try:
        with path.open("rb") as stream:
            if stream.read(2) != b"MZ":
                return False
            stream.seek(0x3C)
            pe_offset = struct.unpack("<I", stream.read(4))[0]
            stream.seek(pe_offset)
            return (
                stream.read(4) == b"PE\0\0"
                and struct.unpack("<H", stream.read(2))[0] == 0x014C
            )
    except (OSError, struct.error):
        return False


def supports_22khz(dll_path: Path) -> bool:
    """IBMECI admite 22 kHz; el Eloquence clásico suministrado no."""
    try:
        size = ctypes.windll.version.GetFileVersionInfoSizeW(str(dll_path), None)
        if not size:
            return False
        buffer = ctypes.create_string_buffer(size)
        ctypes.windll.version.GetFileVersionInfoW(str(dll_path), 0, size, buffer)
        value = ctypes.c_void_p()
        length = ctypes.c_uint()
        for language in ("040904B0", "040904E4", "000004B0"):
            query = f"\\StringFileInfo\\{language}\\ProductName"
            if ctypes.windll.version.VerQueryValueW(
                buffer, query, ctypes.byref(value), ctypes.byref(length)
            ):
                product = ctypes.wstring_at(value.value, length.value).rstrip("\0")
                return product.strip().upper() == "IBMECI"
    except Exception:
        log.debug("No se pudo consultar ProductName de %s", dll_path, exc_info=True)
    return False


def _system_ansi_encoding() -> str:
    try:
        return f"cp{ctypes.windll.kernel32.GetACP()}"
    except Exception:
        return "cp1252"


def _short_path(path: Path) -> str:
    try:
        required = ctypes.windll.kernel32.GetShortPathNameW(str(path), None, 0)
        if not required:
            return ""
        buffer = ctypes.create_unicode_buffer(required + 1)
        if ctypes.windll.kernel32.GetShortPathNameW(str(path), buffer, len(buffer)):
            return buffer.value
    except Exception:
        log.debug("No se pudo obtener la ruta corta de %s", path, exc_info=True)
    return ""


def _ansi_path(path: Path, encoding: str) -> str:
    """La ruta escrita de forma que la pueda leer una API ANSI, o cadena vacía.

    ECI es de 1993 y toda su interfaz es ANSI: una ruta con caracteres que no
    quepan en la página de códigos del sistema no le llega entera. En ese caso
    se prueba con el nombre corto 8.3, que por construcción es ASCII.
    """
    texto = str(path)
    try:
        texto.encode(encoding, errors="strict")
        return texto
    except UnicodeEncodeError:
        corta = _short_path(path)
        if corta:
            try:
                corta.encode(encoding, errors="strict")
                return corta
            except UnicodeEncodeError:
                pass
    return ""


def eci_environment(data_dir: Path = ELOQUENCE_DATA_DIR) -> dict[str, str] | None:
    """El entorno con el que hay que arrancar el proceso de 32 bits.

    **ECI no busca su ``ECI.INI`` donde uno creería.** Lo busca por el nombre
    que le diga la variable de entorno ``ECIINI``, y solo si no está recurre a
    lo que encuentre por su cuenta. En un equipo donde otro programa haya
    dejado el suyo —el complemento de Eloquence de un lector de pantalla, sin ir
    más lejos— la biblioteca puede acabar leyendo **ese otro**, que apunta a las
    voces de otra carpeta. Entonces Eloquence suena mientras ese otro programa
    esté instalado y activo, y deja de sonar en cuanto no lo está, que es
    exactamente el síntoma que se reportó.

    Poniendo la variable no queda ninguna duda: la que se lee es la de este
    paquete, esté donde esté instalado.

    :return: El entorno completo que hay que pasarle al proceso, o ``None``
             para heredar el de siempre cuando la ruta no se puede escribir en
             ANSI (ahí se depende del directorio de trabajo, que también es
             este).
    """
    ini = _ansi_path((data_dir / "ECI.INI").resolve(), _system_ansi_encoding())
    if not ini:
        log.debug("La ruta de ECI.INI no cabe en la página de códigos del sistema")
        return None
    entorno = dict(os.environ)
    entorno["ECIINI"] = ini
    return entorno


def _portable_eci_value(data_dir: Path, filename: str, encoding: str) -> str:
    """Devuelve una ruta ANSI absoluta o, como último recurso, una ruta relativa."""
    absolute = str((data_dir.resolve() / filename))
    try:
        absolute.encode(encoding, errors="strict")
        return absolute
    except UnicodeEncodeError:
        short = _short_path(data_dir.resolve())
        if short:
            candidate = str(Path(short) / filename)
            try:
                candidate.encode(encoding, errors="strict")
                return candidate
            except UnicodeEncodeError:
                pass
        # El host ECI siempre se inicia con data_dir como directorio de trabajo.
        # Así, hasta una carpeta Unicode sin nombre 8.3 continúa siendo portable.
        return filename


def update_eci_ini(data_dir: Path = ELOQUENCE_DATA_DIR) -> None:
    """Deja en ECI.INI la ruta donde de verdad están las voces, ahora mismo.

    ``ECI.INI`` trae una línea ``Path=`` por idioma con la ruta absoluta de su
    archivo de voz, y esa ruta es la del equipo donde se preparó el paquete: no
    tiene por qué existir en el equipo donde se instala, y desde luego no existe
    si el visor se lleva en un pendrive y hoy es la unidad E y mañana la G.

    Así que no se confía en lo que traiga escrito: **de cada línea se conserva
    solo el nombre del archivo** y se le vuelve a poner delante la carpeta desde
    la que se está arrancando en este momento. Se hace cada vez que el motor se
    activa, y como se compara antes de escribir, no cuesta nada cuando ya está
    bien.

    Se escribe de forma atómica —a un archivo temporal y luego un cambio de
    nombre— porque si el programa se cierra a mitad de la escritura, un ECI.INI
    truncado deja el motor sin arrancar.
    """
    data_dir = data_dir.resolve()
    ini_path = data_dir / "ECI.INI"
    encoding = _system_ansi_encoding()
    with _eci_ini_lock:
        raw = ini_path.read_bytes()
        try:
            text = raw.decode(encoding, errors="strict")
        except UnicodeDecodeError:
            text = raw.decode("cp1252", errors="replace")
        content = text.splitlines(keepends=True)
        updated: list[str] = []
        changed = False
        for line in content:
            body = line.rstrip("\r\n")
            match = re.match(r"^(\s*)(Path(?:_Rom)?)(\s*=\s*)(.*?)(\s*)$", body, re.I)
            if not match:
                updated.append(line)
                continue
            old_value = match.group(4).strip().strip('"')
            filename = re.split(r"[\\/]", old_value)[-1]
            if not filename or any(character in filename for character in "\0\r\n"):
                updated.append(line)
                continue
            replacement = (
                f"{match.group(1)}{match.group(2)}{match.group(3)}"
                f"{_portable_eci_value(data_dir, filename, encoding)}{match.group(5)}"
            )
            ending = line[len(body) :]
            updated.append(replacement + ending)
            changed = changed or replacement != body
        if not changed:
            return
        encoded = "".join(updated).encode(encoding, errors="strict")
        descriptor, temporary = tempfile.mkstemp(
            prefix="ECI_", suffix=".tmp", dir=data_dir
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, ini_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        log.info("Rutas portables actualizadas en %s", ini_path)


def check_eloquence_assets(
    data_dir: Path = ELOQUENCE_DATA_DIR,
    bridge_path: Path | None = None,
) -> EloquenceAvailability:
    """Valida el puente y las bibliotecas antes de ofrecer Eloquence."""
    bridge = bridge_path or (LIB_DIR / "ibmtts_host32.dll")
    dll = data_dir / "ECI.DLL"
    required = [bridge, dll, data_dir / "ECI.INI", data_dir / "ESP.SYN"]
    missing = [path.name for path in required if not path.is_file()]
    if missing:
        return EloquenceAvailability(
            False,
            "Eloquence no está disponible; faltan: " + ", ".join(missing) + ".",
            bridge,
            dll,
            data_dir,
        )
    if not _is_32_bit_pe(bridge) or not _is_32_bit_pe(dll):
        return EloquenceAvailability(
            False,
            "Eloquence no está disponible porque el puente o ECI.DLL no es una biblioteca de 32 bits válida.",
            bridge,
            dll,
            data_dir,
        )
    try:
        update_eci_ini(data_dir)
    except (OSError, UnicodeError) as exc:
        return EloquenceAvailability(
            False,
            f"Eloquence no está disponible porque no se pudo preparar ECI.INI: {exc}.",
            bridge,
            dll,
            data_dir,
        )
    return EloquenceAvailability(
        True,
        "Eloquence está disponible y sus rutas portables están preparadas.",
        bridge,
        dll,
        data_dir,
        supports_22khz(dll),
    )
