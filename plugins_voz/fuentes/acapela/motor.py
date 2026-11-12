# -*- coding: utf-8 -*-
"""Acapela portátil para el Visor Universal.

Este adaptador habla directamente con la API ``BabTTS``. No registra SAPI,
no ejecuta instaladores y no escribe en el Registro. Admite un runtime x64 en
el proceso del visor y un runtime x86 mediante ``acapela_host32.exe``.

El paquete no incluye bibliotecas ni voces de Acapela. Quien lo use debe aportar
un SDK/runtime y una licencia que autoricen la integración en su aplicación.
"""

from __future__ import annotations

import ctypes
import html
import logging
import os
import queue
import re
import struct
import subprocess
import threading
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path


log = logging.getLogger("visor.motor.acapela")

try:
    from paths import HOST32
except ImportError:  # Permite probar el fuente antes de armar el paquete.
    HOST32 = (Path(__file__).resolve().parent / "archivos" / "puente32"
              / "acapela_host32.exe")


# Modos y parámetros públicos de la API BabTTS observada.
BABTTS_ASYNC = 0x40000000
BABTTS_TEXT = 0x00000000
BABTTS_TXT_UC2 = 0x00000004
BABTTS_TAG_SAPI = 0x00000040
BABTTS_USEDEFDICT = 0x00000004
BABTTS_USEDEFAULT = 0xFFFFFFFF

BABTTS_CB_FUNCTION = 0x00000002
BABTTS_MSG_TEXTBEGIN = 0x2008
BABTTS_MSG_TEXTEND = 0x2009

PARAM_VOICE = 1
PARAM_PITCH = 2
PARAM_SPEED = 3
PARAM_WAVEFORMAT = 4
PARAM_VOLUME = 5
PARAM_MAXPITCH = 9
PARAM_MINPITCH = 10
PARAM_VOLUMERATIO = 11
PARAM_LEADINGSILENCE = 13
PARAM_TRAILINGSILENCE = 15
PARAM_DEVICE = 16
PARAM_READINGMODE = 18
PARAM_PAUSEPUNCT = 19
PARAM_PAUSESEMICOLON = 20
PARAM_PAUSECOMMA = 21
PARAM_PAUSEBRACKET = 22
PARAM_PAUSESPELL = 23
PARAM_USEFILTER = 24
PARAM_FILTERVALUE1 = 25
PARAM_FILTERVALUE2 = 26
PARAM_FILTERVALUE3 = 27
PARAM_FILTERVALUE4 = 28
PARAM_VOCALTRACT = 29

ERRORES = {
    -27: "los datos de la voz no son compatibles con esta versión del motor",
    -26: "el diccionario de la voz es demasiado antiguo",
    -25: "la biblioteca no está inicializada",
    -24: "la licencia no es válida para esta función o esta voz",
    -23: "no se encuentra el diccionario de pronunciación",
    -22: "falta un archivo de datos de la voz",
    -21: "esa función no está implementada por esta versión",
    -15: "no se puede abrir un archivo necesario",
    -13: "el texto contiene una etiqueta que el motor no admite",
    -12: "el módulo de idioma no está disponible",
    -10: "un parámetro tiene un valor no válido",
    -9: "el runtime necesita una configuración de Registro que aquí no existe",
    -8: "la configuración del runtime en el Registro no es válida",
    -7: "el proceso interno del motor ha fallado",
    -6: "el dispositivo de sonido no está disponible",
    -5: "no se puede escribir en el dispositivo de sonido",
    -4: "el motor no ha podido sintetizar el texto",
    -3: "el motor ya está hablando",
    -2: "el motor no ha podido liberar memoria",
    -1: "el motor no tiene memoria suficiente",
}

IDIOMAS = {
    "arabic": "ar",
    "australianenglish": "en-AU",
    "belgiandutch": "nl-BE",
    "brazilian": "pt-BR",
    "british": "en-GB",
    "canadianfrench": "fr-CA",
    "catalan": "ca-ES",
    "czech": "cs-CZ",
    "danish": "da-DK",
    "dutch": "nl-NL",
    "faroese": "fo-FO",
    "finnish": "fi-FI",
    "finlandswedish": "sv-FI",
    "french": "fr-FR",
    "german": "de-DE",
    "greek": "el-GR",
    "italian": "it-IT",
    "northsami": "se-NO",
    "norwegian": "nb-NO",
    "polish": "pl-PL",
    "portuguese": "pt-PT",
    "russian": "ru-RU",
    "scottishenglish": "en-GB",
    "spanish": "es-ES",
    "spanishspain": "es-ES",
    "swedish": "sv-SE",
    "turkish": "tr-TR",
    "usenglish": "en-US",
    "usspanish": "es-US",
}


class ErrorAcapela(RuntimeError):
    """Error de la API con una explicación preparada para el usuario."""


def _explicar(codigo: int, operacion: str) -> str:
    detalle = ERRORES.get(int(codigo), "error no documentado")
    return "%s: %s (código %d)" % (operacion, detalle, int(codigo))


def _comprobar(codigo: int, operacion: str) -> int:
    codigo = int(codigo)
    if codigo < 0:
        raise ErrorAcapela(_explicar(codigo, operacion))
    return codigo


def _entero(valor, defecto: int, minimo: int | None = None,
            maximo: int | None = None) -> int:
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        numero = defecto
    if minimo is not None:
        numero = max(minimo, numero)
    if maximo is not None:
        numero = min(maximo, numero)
    return numero


def _normalizar(nombre: str) -> str:
    return re.sub(r"[^a-z0-9]", "", nombre.lower())


def _arquitectura_pe(ruta: Path) -> str:
    """Devuelve ``x86``, ``x64`` o una cadena vacía sin cargar el binario."""
    try:
        with Path(ruta).open("rb") as archivo:
            if archivo.read(2) != b"MZ":
                return ""
            archivo.seek(0x3C)
            desplazamiento = struct.unpack("<I", archivo.read(4))[0]
            archivo.seek(desplazamiento)
            if archivo.read(4) != b"PE\0\0":
                return ""
            maquina = struct.unpack("<H", archivo.read(2))[0]
    except (OSError, struct.error):
        return ""
    return {0x014C: "x86", 0x8664: "x64", 0xAA64: "arm64"}.get(maquina, "")


class _VS_FIXEDFILEINFO(ctypes.Structure):
    _fields_ = [
        ("dwSignature", wintypes.DWORD),
        ("dwStrucVersion", wintypes.DWORD),
        ("dwFileVersionMS", wintypes.DWORD),
        ("dwFileVersionLS", wintypes.DWORD),
        ("dwProductVersionMS", wintypes.DWORD),
        ("dwProductVersionLS", wintypes.DWORD),
        ("dwFileFlagsMask", wintypes.DWORD),
        ("dwFileFlags", wintypes.DWORD),
        ("dwFileOS", wintypes.DWORD),
        ("dwFileType", wintypes.DWORD),
        ("dwFileSubtype", wintypes.DWORD),
        ("dwFileDateMS", wintypes.DWORD),
        ("dwFileDateLS", wintypes.DWORD),
    ]


def _version_archivo(ruta: Path) -> tuple[int, int, int, int]:
    """Lee la versión PE con version.dll, sin ejecutar la biblioteca."""
    try:
        version = ctypes.WinDLL("version", use_last_error=True)
        version.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR,
                                                    ctypes.POINTER(wintypes.DWORD)]
        version.GetFileVersionInfoSizeW.restype = wintypes.DWORD
        version.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                                                wintypes.DWORD, wintypes.LPVOID]
        version.GetFileVersionInfoW.restype = wintypes.BOOL
        version.VerQueryValueW.argtypes = [wintypes.LPCVOID, wintypes.LPCWSTR,
                                           ctypes.POINTER(wintypes.LPVOID),
                                           ctypes.POINTER(wintypes.UINT)]
        version.VerQueryValueW.restype = wintypes.BOOL
        sobrante = wintypes.DWORD()
        tamano = version.GetFileVersionInfoSizeW(str(ruta), ctypes.byref(sobrante))
        if not tamano:
            return ()
        bloque = ctypes.create_string_buffer(tamano)
        if not version.GetFileVersionInfoW(str(ruta), 0, tamano, bloque):
            return ()
        puntero = wintypes.LPVOID()
        longitud = wintypes.UINT()
        if not version.VerQueryValueW(bloque, "\\", ctypes.byref(puntero),
                                      ctypes.byref(longitud)):
            return ()
        fija = ctypes.cast(puntero, ctypes.POINTER(_VS_FIXEDFILEINFO)).contents
        return (fija.dwFileVersionMS >> 16, fija.dwFileVersionMS & 0xFFFF,
                fija.dwFileVersionLS >> 16, fija.dwFileVersionLS & 0xFFFF)
    except (AttributeError, OSError, ValueError):
        return ()


def _ruta(texto) -> Path | None:
    valor = os.path.expandvars(str(texto or "").strip().strip('"'))
    return Path(valor).expanduser().resolve() if valor else None


def _resolver_dll(valor, arquitectura: str, datos: Path | None) -> Path | None:
    ruta = _ruta(valor)
    if ruta is None:
        return None
    if ruta.is_file():
        return ruta
    if not ruta.is_dir():
        return ruta / "AcaTts.dll"

    raiz_datos = datos or ruta
    modulos_x86 = False
    if raiz_datos and (raiz_datos / "bin").is_dir():
        modulos = list((raiz_datos / "bin").glob("*.dll"))
        modulos_x86 = bool(modulos) and all(_arquitectura_pe(uno) == "x86"
                                            for uno in modulos)
    if arquitectura == "puente32" or (arquitectura == "auto" and modulos_x86):
        nombres = ("AcaTts.dll", "acatts.dll")
        subcarpetas = (Path(), Path("bin"), Path("bin/x86"), Path("x86"))
    elif arquitectura == "nativo64":
        nombres = ("AcaTts.64.dll", "AcaTts64.dll", "AcaTts.dll")
        subcarpetas = (Path(), Path("bin"), Path("bin/x64"), Path("x64"))
    else:
        nombres = ("AcaTts.64.dll", "AcaTts64.dll", "AcaTts.dll")
        subcarpetas = (Path(), Path("bin"), Path("bin/x64"), Path("x64"),
                       Path("bin/x86"), Path("x86"))
    for subcarpeta in subcarpetas:
        for nombre in nombres:
            candidato = ruta / subcarpeta / nombre
            if candidato.is_file():
                return candidato
    return ruta / nombres[0]


def _componentes_alterados(carpeta: Path) -> list[str]:
    encontrados = []
    for nombre in ("CLKERN.DLL", "INFOVOX3.EXE.cracklock"):
        if (carpeta / nombre).exists():
            encontrados.append(nombre)
    return encontrados


@dataclass(frozen=True)
class Diagnostico:
    dll: Path | None
    datos: Path | None
    arquitectura: str
    version: tuple[int, ...]
    problema: str = ""
    aviso: str = ""


def diagnosticar(ruta_motor, ruta_datos="", arquitectura="auto",
                 permitir_version_distinta=False) -> Diagnostico:
    """Analiza compatibilidad sin cargar ni ejecutar ningún binario."""
    datos = _ruta(ruta_datos)
    dll = _resolver_dll(ruta_motor, str(arquitectura), datos)
    if dll is None:
        return Diagnostico(None, datos, "", (),
                           "falta indicar la carpeta o DLL del runtime oficial de Acapela")
    if not dll.is_file():
        return Diagnostico(dll, datos, "", (),
                           "no se encuentra la biblioteca del motor: %s" % dll)
    if datos is None:
        motor = _ruta(ruta_motor)
        datos = motor if motor is not None and motor.is_dir() else dll.parent
    alterados = _componentes_alterados(dll.parent)
    if alterados:
        return Diagnostico(
            dll, datos, _arquitectura_pe(dll), _version_archivo(dll),
            "esa carpeta contiene componentes de activación alterados (%s); "
            "utiliza un runtime y una licencia oficiales" % ", ".join(alterados))

    maquina = _arquitectura_pe(dll)
    version = _version_archivo(dll)
    if maquina not in ("x86", "x64"):
        return Diagnostico(dll, datos, maquina, version,
                           "la biblioteca no es un PE x86 o x64 compatible")
    if str(arquitectura) == "nativo64" and maquina != "x64":
        return Diagnostico(dll, datos, maquina, version,
                           "se pidió modo nativo de 64 bits, pero la DLL es x86")
    if str(arquitectura) == "puente32" and maquina != "x86":
        return Diagnostico(dll, datos, maquina, version,
                           "se pidió el puente de 32 bits, pero la DLL es x64")

    if datos is not None and not datos.is_dir():
        return Diagnostico(dll, datos, maquina, version,
                           "no se encuentra la carpeta de datos y voces: %s" % datos)

    aviso = ""
    if datos and (datos / "bin").is_dir():
        modulos = [uno for uno in (datos / "bin").glob("*.dll") if uno.is_file()]
        incompatibles = [uno.name for uno in modulos
                         if _arquitectura_pe(uno) not in ("", maquina)]
        if incompatibles:
            return Diagnostico(
                dll, datos, maquina, version,
                "el runtime es %s y los módulos de las voces son de otra "
                "arquitectura: %s" % (maquina, ", ".join(incompatibles)))
        versiones = [(uno.name, _version_archivo(uno)) for uno in modulos]
        nuevas = [(nombre, cual) for nombre, cual in versiones
                  if version and cual and cual[0] > version[0]]
        if nuevas and not permitir_version_distinta:
            detalle = ", ".join("%s %s" % (nombre, ".".join(map(str, cual[:2])))
                                for nombre, cual in nuevas)
            return Diagnostico(
                dll, datos, maquina, version,
                "el kernel Acapela %s es anterior a los módulos de voz %s; "
                "hace falta un runtime de la misma generación"
                % (".".join(map(str, version[:2])), detalle))
        if nuevas:
            aviso = "se intentará una combinación de versiones distintas por petición expresa"
    return Diagnostico(dll, datos, maquina, version, aviso=aviso)


def _voces_en_datos(datos: Path | None) -> list[tuple[str, str]]:
    """Extrae nombres e idiomas de los `.conf` sin cargar el motor."""
    if datos is None or not datos.is_dir():
        return []
    voces: dict[str, str] = {}
    patron = re.compile(r"^\[\\Speechfonts\\([^\]]+)\]", re.MULTILINE)
    for archivo in datos.rglob("*.conf"):
        try:
            texto = archivo.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        coincidencia = patron.search(texto)
        if not coincidencia:
            continue
        nombre = coincidencia.group(1).strip()
        idioma = ""
        for parte in archivo.parts:
            codigo = IDIOMAS.get(_normalizar(parte))
            if codigo:
                idioma = codigo
                break
        voces.setdefault(nombre, idioma)
    return sorted(voces.items(), key=lambda item: item[0].lower())


class _Nativo:
    """Enlace ctypes con el runtime x64 oficial."""

    _Callback = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint32,
                                   ctypes.c_void_p, ctypes.c_size_t)

    def __init__(self, dll: Path, datos: Path | None) -> None:
        if ctypes.sizeof(ctypes.c_void_p) != 8 or _arquitectura_pe(dll) != "x64":
            raise ErrorAcapela("el modo nativo necesita Python y AcaTTS de 64 bits")
        self._dll_dirs = []
        self._entorno_anterior = os.environ.get("ACATTS")
        self._instancia = None
        self._buffer_texto = None
        self._hablando = threading.Event()
        self._pausada = False
        self._callback = self._Callback(self._evento)
        self._inicializado = False
        try:
            self._dll_dirs.append(os.add_dll_directory(str(dll.parent)))
            if datos and (datos / "bin").is_dir():
                # Colibri y el procesador lingüístico se cargan dinámicamente
                # al inicializar una voz; no son imports estáticos de AcaTTS.
                self._dll_dirs.append(os.add_dll_directory(str(datos / "bin")))
            if datos:
                os.environ["ACATTS"] = str(datos)
            self._lib = ctypes.WinDLL(str(dll), winmode=0x00001100)
            self._enlazar()
            _comprobar(self._init(), "inicializando Acapela")
            self._inicializado = True
            self._voces = self._enumerar()
        except Exception:
            if self._inicializado:
                try:
                    self._uninit()
                except Exception:
                    pass
                self._inicializado = False
            self._restaurar_entorno()
            raise

    def _restaurar_entorno(self) -> None:
        if self._entorno_anterior is None:
            os.environ.pop("ACATTS", None)
        else:
            os.environ["ACATTS"] = self._entorno_anterior
        for directorio in reversed(self._dll_dirs):
            directorio.close()
        self._dll_dirs.clear()

    def _enlazar(self) -> None:
        def funcion(nombre, argumentos, resultado=ctypes.c_int):
            encontrada = getattr(self._lib, nombre)
            encontrada.argtypes = argumentos
            encontrada.restype = resultado
            return encontrada

        self._init = funcion("BabTTS_Init", [])
        self._uninit = funcion("BabTTS_Uninit", [])
        self._create = funcion("BabTTS_Create", [], ctypes.c_void_p)
        self._close = funcion("BabTTS_Close", [ctypes.c_void_p])
        self._open = funcion("BabTTS_Open", [ctypes.c_void_p, ctypes.c_char_p,
                                               ctypes.c_uint32])
        self._speak = funcion("BabTTS_Speak", [ctypes.c_void_p, ctypes.c_void_p,
                                                 ctypes.c_uint32])
        self._reset = funcion("BabTTS_Reset", [ctypes.c_void_p])
        self._pause = funcion("BabTTS_Pause", [ctypes.c_void_p])
        self._resume = funcion("BabTTS_Resume", [ctypes.c_void_p])
        self._set = funcion("BabTTS_SetSettings", [ctypes.c_void_p,
                                                     ctypes.c_uint32,
                                                     ctypes.c_uint32])
        self._num_voices = funcion("BabTTS_GetNumVoices", [])
        self._enum_voice = funcion("BabTTS_EnumVoices", [ctypes.c_int,
                                                           ctypes.c_char_p])
        self._set_callback = funcion("BabTTS_SetCallback", [ctypes.c_void_p,
                                                              self._Callback,
                                                              ctypes.c_uint32])

    def _enumerar(self) -> list[str]:
        total = _comprobar(self._num_voices(), "enumerando las voces")
        voces = []
        for indice in range(total):
            buffer = ctypes.create_string_buffer(512)
            _comprobar(self._enum_voice(indice, buffer), "leyendo una voz")
            nombre = buffer.value.decode("cp1252", errors="replace").strip()
            if nombre:
                voces.append(nombre)
        return voces

    def _evento(self, _instancia, mensaje, _contexto, _informacion) -> None:
        if mensaje == BABTTS_MSG_TEXTBEGIN:
            self._hablando.set()
        elif mensaje == BABTTS_MSG_TEXTEND:
            self._hablando.clear()
            self._buffer_texto = None

    @property
    def voces(self) -> list[str]:
        return list(self._voces)

    def elegir_voz(self, nombre: str) -> None:
        if nombre not in self._voces:
            raise ErrorAcapela("la voz «%s» no aparece en el runtime" % nombre)
        if self._instancia:
            self.detener()
            _comprobar(self._close(self._instancia), "cerrando la voz anterior")
            self._instancia = None
        instancia = self._create()
        if not instancia:
            raise ErrorAcapela("Acapela no ha podido crear una instancia de voz")
        try:
            _comprobar(self._open(instancia, nombre.encode("cp1252"),
                                  BABTTS_USEDEFDICT), "abriendo la voz «%s»" % nombre)
            _comprobar(self._set_callback(instancia, self._callback,
                                          BABTTS_CB_FUNCTION),
                        "conectando las notificaciones de la voz")
        except Exception:
            self._close(instancia)
            raise
        self._instancia = instancia

    def parametro(self, clave: int, valor: int) -> None:
        if self._instancia:
            _comprobar(self._set(self._instancia, clave, valor & 0xFFFFFFFF),
                        "aplicando el parámetro %d" % clave)

    def decir(self, texto: str, etiquetas: bool) -> None:
        if not self._instancia:
            raise ErrorAcapela("no hay ninguna voz abierta")
        self.detener()
        datos = texto.encode("utf-16-le") + b"\0\0"
        self._buffer_texto = ctypes.create_string_buffer(datos)
        modo = BABTTS_ASYNC | BABTTS_TEXT | BABTTS_TXT_UC2
        if etiquetas:
            modo |= BABTTS_TAG_SAPI
        self._hablando.set()
        try:
            _comprobar(self._speak(self._instancia,
                                   ctypes.cast(self._buffer_texto, ctypes.c_void_p),
                                   modo), "enviando el texto a Acapela")
        except Exception:
            self._hablando.clear()
            self._buffer_texto = None
            raise

    def pausar(self) -> None:
        if self._instancia and not self._pausada:
            _comprobar(self._pause(self._instancia), "pausando Acapela")
            self._pausada = True

    def continuar(self) -> None:
        if self._instancia and self._pausada:
            _comprobar(self._resume(self._instancia), "continuando Acapela")
            self._pausada = False

    def detener(self) -> None:
        if not self._instancia:
            return
        if self._pausada:
            self._resume(self._instancia)
            self._pausada = False
        _comprobar(self._reset(self._instancia), "deteniendo Acapela")
        self._hablando.clear()
        self._buffer_texto = None

    @property
    def hablando(self) -> bool:
        return self._pausada or self._hablando.is_set()

    @property
    def pausada(self) -> bool:
        return self._pausada

    def cerrar(self) -> None:
        try:
            if self._instancia:
                self.detener()
                self._close(self._instancia)
                self._instancia = None
            if getattr(self, "_inicializado", False):
                self._uninit()
                self._inicializado = False
        finally:
            self._restaurar_entorno()


class _Puente32:
    """Cliente del proceso x86, con protocolo binario por stdin/stdout."""

    ENUMERAR = 1
    ELEGIR = 2
    PARAMETRO = 3
    DECIR = 4
    PAUSAR = 5
    CONTINUAR = 6
    DETENER = 7
    ESTADO = 8
    CERRAR = 9

    def __init__(self, ejecutable: Path, dll: Path, datos: Path | None,
                 espera: float = 12.0) -> None:
        if not ejecutable.is_file():
            raise ErrorAcapela("falta el puente de 32 bits: %s" % ejecutable)
        orden = [str(ejecutable), "--dll", str(dll)]
        if datos:
            orden += ["--data", str(datos)]
        opciones = {
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.DEVNULL,
            "bufsize": 0,
        }
        if os.name == "nt":
            opciones["creationflags"] = subprocess.CREATE_NO_WINDOW
        self._proceso = subprocess.Popen(orden, **opciones)
        self._respuestas: queue.Queue = queue.Queue()
        self._cerrado = False
        self._bloqueo = threading.Lock()
        self._lector = threading.Thread(target=self._leer, name="AcapelaHost32",
                                        daemon=True)
        self._lector.start()
        exito, mensaje = self._esperar(espera)
        if not exito:
            self.cerrar()
            raise ErrorAcapela(mensaje or "el puente de 32 bits no ha arrancado")
        self._voces = [uno for uno in mensaje.split("\n") if uno]
        self._pausada = False

    @staticmethod
    def _exactos(canal, cuantos: int) -> bytes:
        partes = []
        faltan = cuantos
        while faltan:
            bloque = canal.read(faltan)
            if not bloque:
                raise EOFError("el proceso de 32 bits ha cerrado la comunicación")
            partes.append(bloque)
            faltan -= len(bloque)
        return b"".join(partes)

    def _leer(self) -> None:
        try:
            canal = self._proceso.stdout
            while canal:
                cabecera = self._exactos(canal, 5)
                estado, longitud = struct.unpack("<BI", cabecera)
                if longitud > 16 * 1024 * 1024:
                    raise ErrorAcapela("respuesta desmesurada del puente de 32 bits")
                cuerpo = self._exactos(canal, longitud)
                self._respuestas.put((estado == 0,
                                      cuerpo.decode("utf-8", errors="replace")))
        except Exception as error:
            self._respuestas.put((False, str(error)))

    def _esperar(self, espera: float = 5.0) -> tuple[bool, str]:
        try:
            return self._respuestas.get(timeout=max(0.1, float(espera)))
        except queue.Empty as error:
            raise ErrorAcapela("el puente de 32 bits no responde") from error

    def _pedir(self, orden: int, carga=b"", espera: float = 5.0) -> str:
        if self._cerrado or self._proceso.poll() is not None:
            raise ErrorAcapela("el puente de 32 bits ya no está disponible")
        if len(carga) > 16 * 1024 * 1024:
            raise ErrorAcapela("el texto es demasiado grande para el puente")
        with self._bloqueo:
            try:
                self._proceso.stdin.write(struct.pack("<BI", orden, len(carga)) + carga)
                self._proceso.stdin.flush()
            except (BrokenPipeError, OSError) as error:
                raise ErrorAcapela("se ha perdido la comunicación con el puente") from error
            exito, mensaje = self._esperar(espera)
        if not exito:
            raise ErrorAcapela(mensaje)
        return mensaje

    @property
    def voces(self) -> list[str]:
        return list(self._voces)

    def elegir_voz(self, nombre: str) -> None:
        self._pedir(self.ELEGIR, nombre.encode("utf-8"))

    def parametro(self, clave: int, valor: int) -> None:
        self._pedir(self.PARAMETRO, struct.pack("<II", clave, valor & 0xFFFFFFFF))

    def decir(self, texto: str, etiquetas: bool) -> None:
        modo = BABTTS_ASYNC | BABTTS_TEXT | BABTTS_TXT_UC2
        if etiquetas:
            modo |= BABTTS_TAG_SAPI
        self._pedir(self.DECIR, struct.pack("<I", modo) + texto.encode("utf-8"))

    def pausar(self) -> None:
        self._pedir(self.PAUSAR)
        self._pausada = True

    def continuar(self) -> None:
        self._pedir(self.CONTINUAR)
        self._pausada = False

    def detener(self) -> None:
        self._pedir(self.DETENER)
        self._pausada = False

    @property
    def hablando(self) -> bool:
        if self._pausada:
            return True
        try:
            return self._pedir(self.ESTADO, espera=1.0) == "1"
        except ErrorAcapela:
            return False

    @property
    def pausada(self) -> bool:
        return self._pausada

    def cerrar(self) -> None:
        if self._cerrado:
            return
        self._cerrado = True
        try:
            if self._proceso.poll() is None and self._proceso.stdin:
                carga = struct.pack("<BI", self.CERRAR, 0)
                self._proceso.stdin.write(carga)
                self._proceso.stdin.flush()
                self._proceso.wait(timeout=2)
        except Exception:
            if self._proceso.poll() is None:
                self._proceso.terminate()
        finally:
            for canal in (self._proceso.stdin, self._proceso.stdout):
                try:
                    if canal:
                        canal.close()
                except OSError:
                    pass


class MotorAcapela:
    """La cara del motor que cumple el contrato del Visor Universal."""

    def __init__(self, carpeta: Path, ajustes: dict) -> None:
        self._carpeta = Path(carpeta)
        self._ajustes = dict(ajustes or {})
        self._backend = None
        self._intentado = False
        self._problema = ""
        self._aviso = ""
        self._voz = str(self._ajustes.get("_voz_elegida", "") or "")
        self._velocidad = 0
        self._volumen = 100
        self._datos = _ruta(self._ajustes.get("ruta_datos", ""))
        if self._datos is None:
            runtime = _ruta(self._ajustes.get("ruta_motor", ""))
            if runtime is not None:
                self._datos = runtime if runtime.is_dir() else runtime.parent
        self._voces_estaticas = _voces_en_datos(self._datos)

    def _asegurar(self) -> bool:
        if self._backend is not None:
            return True
        if self._intentado:
            return False
        self._intentado = True
        if not bool(self._ajustes.get("runtime_portatil_autorizado", False)):
            self._problema = (
                "el motor está en modo seguro; confirma en sus ajustes que el "
                "runtime es oficial, tiene licencia para esta aplicación y está "
                "preparado para funcionar sin Registro")
            return False
        diagnostico = diagnosticar(
            self._ajustes.get("ruta_motor", ""),
            self._ajustes.get("ruta_datos", ""),
            self._ajustes.get("arquitectura", "auto"),
            bool(self._ajustes.get("permitir_version_distinta", False)),
        )
        if diagnostico.problema:
            self._problema = diagnostico.problema
            return False
        self._aviso = diagnostico.aviso
        try:
            if diagnostico.arquitectura == "x64":
                self._backend = _Nativo(diagnostico.dll, diagnostico.datos)
            elif diagnostico.arquitectura == "x86":
                self._backend = _Puente32(
                    Path(HOST32), diagnostico.dll, diagnostico.datos,
                    self.espera_maxima)
            else:
                raise ErrorAcapela("arquitectura de motor desconocida")
            disponibles = self._backend.voces
            if not disponibles:
                raise ErrorAcapela("el runtime no ha encontrado ninguna voz autorizada")
            elegida = self._voz if self._voz in disponibles else disponibles[0]
            self._backend.elegir_voz(elegida)
            self._voz = elegida
            self._aplicar_ajustes()
            self.establecer_velocidad(self._velocidad)
            self.establecer_volumen(self._volumen)
            self._problema = ""
            return True
        except Exception as error:
            log.error("Acapela no ha podido arrancar: %s", error)
            self._problema = str(error)
            if self._backend is not None:
                try:
                    self._backend.cerrar()
                except Exception:
                    pass
            self._backend = None
            return False

    def _aplicar_ajustes(self) -> None:
        valores = {
            PARAM_PITCH: _entero(self._ajustes.get("tono"), 110, 30, 500),
            PARAM_MAXPITCH: _entero(self._ajustes.get("tono_maximo"), 500, 30, 500),
            PARAM_MINPITCH: _entero(self._ajustes.get("tono_minimo"), 30, 30, 500),
            PARAM_WAVEFORMAT: _entero(self._ajustes.get("formato_onda"), 1),
            PARAM_LEADINGSILENCE: _entero(self._ajustes.get("silencio_inicial"), 0, 0),
            PARAM_TRAILINGSILENCE: _entero(self._ajustes.get("silencio_final"), 0, 0),
            PARAM_DEVICE: _entero(self._ajustes.get("dispositivo"), BABTTS_USEDEFAULT),
            PARAM_READINGMODE: _entero(self._ajustes.get("modo_lectura"), 0, 0, 2),
            PARAM_PAUSEPUNCT: _entero(self._ajustes.get("pausa_puntuacion"), 0, 0, 5),
            PARAM_PAUSESEMICOLON: _entero(self._ajustes.get("pausa_punto_coma"), 0, 0, 5),
            PARAM_PAUSECOMMA: _entero(self._ajustes.get("pausa_coma"), 0, 0, 5),
            PARAM_PAUSEBRACKET: _entero(self._ajustes.get("pausa_parentesis"), 0, 0, 5),
            PARAM_PAUSESPELL: _entero(self._ajustes.get("pausa_deletreo"), 0, 0, 5),
            PARAM_USEFILTER: int(bool(self._ajustes.get("usar_filtro", False))),
            PARAM_FILTERVALUE1: _entero(self._ajustes.get("filtro_1"), 0),
            PARAM_FILTERVALUE2: _entero(self._ajustes.get("filtro_2"), 0),
            PARAM_FILTERVALUE3: _entero(self._ajustes.get("filtro_3"), 0),
            PARAM_FILTERVALUE4: _entero(self._ajustes.get("filtro_4"), 0),
            PARAM_VOCALTRACT: _entero(self._ajustes.get("tracto_vocal"), 100, 0, 200),
        }
        minimo, maximo = valores[PARAM_MINPITCH], valores[PARAM_MAXPITCH]
        if minimo > maximo:
            valores[PARAM_MINPITCH], valores[PARAM_MAXPITCH] = maximo, minimo
        for clave, valor in valores.items():
            try:
                self._backend.parametro(clave, valor)
            except ErrorAcapela as error:
                # Las versiones antiguas no implementan todos los parámetros.
                log.warning("Ajuste Acapela omitido: %s", error)

    @property
    def disponible(self) -> bool:
        return self._asegurar() and bool(self._backend.voces)

    def voces(self) -> list[str]:
        if self._asegurar():
            return self._backend.voces
        return [nombre for nombre, _idioma in self._voces_estaticas]

    def elegir_voz(self, nombre: str) -> bool:
        if not nombre:
            return False
        if not self._asegurar():
            if nombre in self.voces():
                self._voz = nombre
            return False
        try:
            self._backend.elegir_voz(nombre)
            self._voz = nombre
            self._aplicar_ajustes()
            self.establecer_velocidad(self._velocidad)
            self.establecer_volumen(self._volumen)
            return True
        except Exception as error:
            self._problema = str(error)
            log.error("No se ha podido elegir la voz Acapela: %s", error)
            return False

    def voz_actual(self) -> str:
        return self._voz

    def voces_con_idioma(self) -> list[tuple[str, str]]:
        idiomas = dict(self._voces_estaticas)
        return [(nombre, idiomas.get(nombre, "")) for nombre in self.voces()]

    def voz_para_idioma(self, codigo: str) -> str:
        pedido = str(codigo or "").lower()
        if not pedido:
            return ""
        idioma_base = pedido.split("-")[0]
        aproximada = ""
        for nombre, idioma in self.voces_con_idioma():
            actual = idioma.lower()
            if actual == pedido:
                return nombre
            if actual.split("-")[0] == idioma_base and not aproximada:
                aproximada = nombre
        return aproximada

    @staticmethod
    def _velocidad_acapela(valor: int) -> int:
        valor = _entero(valor, 0, -10, 10)
        normal = 100
        if valor >= 0:
            return int(normal + valor * (300 - normal) / 10.0)
        return int(normal + valor * (normal - 30) / 10.0)

    def establecer_velocidad(self, valor: int) -> None:
        self._velocidad = _entero(valor, 0, -10, 10)
        if self._backend is not None:
            try:
                self._backend.parametro(PARAM_SPEED,
                                        self._velocidad_acapela(self._velocidad))
            except ErrorAcapela as error:
                log.warning("No se ha podido cambiar la velocidad: %s", error)

    def establecer_volumen(self, valor: int) -> None:
        self._volumen = _entero(valor, 100, 0, 100)
        if self._backend is not None:
            try:
                self._backend.parametro(PARAM_VOLUMERATIO,
                                        round(self._volumen * 1.5))
            except ErrorAcapela as error:
                log.warning("No se ha podido cambiar el volumen: %s", error)

    def decir(self, texto: str, con_marcas: bool = False) -> bool:
        if not texto or not self._asegurar():
            return False
        etiquetas = bool(con_marcas and self._ajustes.get("etiquetas_sapi", True))
        if con_marcas and not etiquetas:
            texto = html.unescape(re.sub(r"<[^>]+>", "", texto))
        try:
            self._backend.decir(texto, etiquetas)
            return True
        except Exception as error:
            self._problema = str(error)
            log.error("Acapela no ha podido hablar: %s", error)
            return False

    def con_tono(self, texto: str, tono: int) -> str:
        if not tono or not bool(self._ajustes.get("etiquetas_sapi", True)):
            return texto
        base = _entero(self._ajustes.get("tono"), 110, 30, 500)
        cambiado = _entero(base + int(tono) * 15, base, 30, 500)
        return "\\pit=%d\\%s\\pit=%d\\" % (cambiado, texto, base)

    def pausar(self) -> None:
        if self._backend is not None:
            try:
                self._backend.pausar()
            except ErrorAcapela as error:
                log.warning("No se ha podido pausar Acapela: %s", error)

    def continuar(self) -> None:
        if self._backend is not None:
            try:
                self._backend.continuar()
            except ErrorAcapela as error:
                log.warning("No se ha podido continuar Acapela: %s", error)

    def detener(self) -> None:
        if self._backend is not None:
            try:
                self._backend.detener()
            except ErrorAcapela as error:
                log.warning("No se ha podido detener Acapela: %s", error)

    @property
    def pausada(self) -> bool:
        return bool(self._backend and self._backend.pausada)

    @property
    def hablando(self) -> bool:
        return bool(self._backend and self._backend.hablando)

    @property
    def espera_maxima(self) -> float:
        return float(_entero(self._ajustes.get("espera_maxima"), 5, 1, 15))

    def problema(self) -> str:
        return self._problema or self._aviso

    def cerrar(self) -> None:
        if self._backend is not None:
            try:
                self._backend.cerrar()
            finally:
                self._backend = None


def crear(carpeta, ajustes):
    """Entrada del paquete para el sistema de motores del visor."""
    return MotorAcapela(Path(carpeta), dict(ajustes or {}))
