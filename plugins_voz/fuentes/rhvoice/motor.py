# -*- coding: utf-8 -*-
"""RHVoice para el Visor Universal: libre, sin conexión y con idiomas a la carta.

RHVoice es el sintetizador libre que más se usa después de eSpeak, y tiene tres
cosas que ninguno de los otros reúne:

* **Suena mejor que eSpeak** sin ser neuronal. No llega a una voz de Edge, pero
  para escuchar horas es más cómoda que un robot y no necesita conexión.
* **Es libre de verdad** (GPL), así que se puede repartir con el programa sin
  pedirle permiso a nadie.
* **Los idiomas se añaden uno a uno.** El motor son un par de megas y cada
  idioma otros cuantos: se instala el español y, el día que haga falta, se añade
  el inglés o el polaco sin volver a instalar nada.

Ese último punto es la razón de que este motor exista aquí. Los demás o traen
todos los idiomas de golpe —eSpeak, veintitrés megas— o dependen de lo que
Windows tenga instalado. Este deja elegir.

Cómo funciona por dentro
------------------------

Se le pasa una frase y va llamando a una función nuestra con trozos de sonido,
igual que eSpeak. Lo reproduce BASS, que el visor ya lleva.

La diferencia está en cómo se le pide: RHVoice no tiene «voces» sino **perfiles
de voz**, que son la voz más el idioma con el que pronuncia. Un perfil puede
mezclar dos —leer español con acento ruso, por ejemplo— y por eso lo que se
elige es el perfil y no la voz suelta.
"""

from __future__ import annotations

import ctypes
import logging
import sys
import threading
from pathlib import Path

log = logging.getLogger("visor.motor.rhvoice")

_AQUI = Path(__file__).resolve().parent
if str(_AQUI) not in sys.path:
    sys.path.insert(0, str(_AQUI))

#: Los límites de RHVoice para velocidad, tono y volumen.  Son relativos: 1.0
#: es «como viene la voz» y se multiplica.
RELATIVO_MINIMO = 0.2
RELATIVO_MAXIMO = 3.0


class _Voz(ctypes.Structure):
    """Lo que RHVoice cuenta de cada voz."""

    _fields_ = [
        ("language", ctypes.c_char_p),
        ("name", ctypes.c_char_p),
        ("gender", ctypes.c_int),
        ("country", ctypes.c_char_p),
    ]


class _Retornos(ctypes.Structure):
    """Las nueve funciones que RHVoice llama mientras sintetiza.

    Solo hacen falta tres —el muestreo, el sonido y el final—; las demás son
    para seguir la lectura palabra por palabra, que aquí no se usa. Se dejan a
    cero, que es lo que el motor espera para «no me avises de esto».
    """

    _fields_ = [
        ("set_sample_rate", ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int,
                                             ctypes.c_void_p)),
        ("play_speech", ctypes.CFUNCTYPE(ctypes.c_int,
                                         ctypes.POINTER(ctypes.c_short),
                                         ctypes.c_uint, ctypes.c_void_p)),
        ("process_mark", ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_char_p,
                                          ctypes.c_void_p)),
        ("word_starts", ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_uint,
                                         ctypes.c_uint, ctypes.c_void_p)),
        ("word_ends", ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_uint,
                                       ctypes.c_uint, ctypes.c_void_p)),
        ("sentence_starts", ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_uint,
                                             ctypes.c_uint, ctypes.c_void_p)),
        ("sentence_ends", ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_uint,
                                           ctypes.c_uint, ctypes.c_void_p)),
        ("play_audio", ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_char_p,
                                        ctypes.c_void_p)),
        ("done", ctypes.CFUNCTYPE(None, ctypes.c_void_p)),
    ]


class _Arranque(ctypes.Structure):
    _fields_ = [
        ("data_path", ctypes.c_char_p),
        ("config_path", ctypes.c_char_p),
        ("resource_paths", ctypes.POINTER(ctypes.c_char_p)),
        ("callbacks", _Retornos),
        ("options", ctypes.c_uint),
    ]


class _Ajustes(ctypes.Structure):
    _fields_ = [
        ("voice_profile", ctypes.c_char_p),
        ("absolute_rate", ctypes.c_double),
        ("absolute_pitch", ctypes.c_double),
        ("absolute_volume", ctypes.c_double),
        ("relative_rate", ctypes.c_double),
        ("relative_pitch", ctypes.c_double),
        ("relative_volume", ctypes.c_double),
        ("punctuation_mode", ctypes.c_int),
        ("punctuation_list", ctypes.c_char_p),
        ("capitals_mode", ctypes.c_int),
        ("flags", ctypes.c_int),
    ]


#: Qué se hace con la puntuación al leer.
PUNTUACION = {"normal": 0, "ninguna": 1, "toda": 2, "algunas": 3}

#: Y qué se hace con las mayúsculas.
MAYUSCULAS = {"normal": 0, "nada": 1, "decir_mayuscula": 2, "subir_tono": 3,
              "sonido": 4}


def _texto(crudo) -> str:
    if not crudo:
        return ""
    return crudo.decode("utf-8", "replace") if isinstance(crudo, bytes) else str(crudo)


class MotorRHVoice:
    """RHVoice con la cara que el visor sabe manejar."""

    def __init__(self, carpeta: Path, ajustes: dict) -> None:
        self._carpeta = Path(carpeta)
        self._ajustes = dict(ajustes)
        self._dll = None
        self._motor = None
        self._perfiles: list = []
        self._perfil = ""
        self._idiomas: dict = {}
        self._muestreo = 24000
        self._pcm = bytearray()
        self._cerrojo = threading.RLock()
        self._canal = 0
        self._pausado = False
        self._bass = False
        self._arrancar()

    # -- arranque ------------------------------------------------------------

    def _arrancar(self) -> None:
        ruta = self._carpeta / "RHVoice.dll"
        if not ruta.is_file():
            log.warning("No está RHVoice.dll")
            return
        try:
            self._dll = ctypes.cdll.LoadLibrary(str(ruta))
        except Exception as error:
            log.warning("No se ha podido cargar RHVoice: %s", error)
            self._dll = None
            return
        self._declarar()
        # Los retornos se guardan en el objeto: si se recogen como basura
        # mientras el motor los tiene apuntados, el programa se cae al primer
        # trozo de sonido.
        self._retornos = _Retornos()
        self._retornos.set_sample_rate = type(self._retornos.set_sample_rate)(
            self._recibir_muestreo)
        self._retornos.play_speech = type(self._retornos.play_speech)(
            self._recibir_sonido)
        self._retornos.done = type(self._retornos.done)(self._acabar)

        datos = self._carpeta / "datos"
        config = self._carpeta / "config"
        config.mkdir(parents=True, exist_ok=True)
        arranque = _Arranque()
        arranque.data_path = str(datos).encode("utf-8")
        arranque.config_path = str(config).encode("utf-8")
        arranque.resource_paths = None
        arranque.callbacks = self._retornos
        arranque.options = 0
        try:
            self._motor = self._dll.RHVoice_new_tts_engine(ctypes.byref(arranque))
        except Exception as error:
            log.warning("RHVoice no ha arrancado: %s", error)
            self._motor = None
            return
        if not self._motor:
            log.warning("RHVoice no ha arrancado: ¿faltan los datos de voz?")
            self._motor = None
            return
        self._perfiles = self._listar_perfiles()
        self._idiomas = self._listar_idiomas()
        log.info("RHVoice %s con %d perfiles de voz",
                 _texto(self._dll.RHVoice_get_version()), len(self._perfiles))
        guardado = str(self._ajustes.get("_voz_elegida", ""))
        if not (guardado and self.elegir_voz(guardado)):
            if self._perfiles:
                self._perfil = self._perfiles[0]

    def _declarar(self) -> None:
        """Le dice a ctypes qué devuelve y qué recibe cada función.

        Sin esto, ctypes supone enteros de 32 bits y en 64 un puntero devuelto
        se trunca: el motor parece arrancar y se cae al usarlo.
        """
        d = self._dll
        d.RHVoice_get_version.restype = ctypes.c_char_p
        d.RHVoice_new_tts_engine.argtypes = (ctypes.POINTER(_Arranque),)
        d.RHVoice_new_tts_engine.restype = ctypes.c_void_p
        d.RHVoice_delete_tts_engine.argtypes = (ctypes.c_void_p,)
        d.RHVoice_delete_tts_engine.restype = None
        d.RHVoice_get_number_of_voices.argtypes = (ctypes.c_void_p,)
        d.RHVoice_get_number_of_voices.restype = ctypes.c_uint
        d.RHVoice_get_voices.argtypes = (ctypes.c_void_p,)
        d.RHVoice_get_voices.restype = ctypes.POINTER(_Voz)
        d.RHVoice_get_number_of_voice_profiles.argtypes = (ctypes.c_void_p,)
        d.RHVoice_get_number_of_voice_profiles.restype = ctypes.c_uint
        d.RHVoice_get_voice_profiles.argtypes = (ctypes.c_void_p,)
        d.RHVoice_get_voice_profiles.restype = ctypes.POINTER(ctypes.c_char_p)
        d.RHVoice_new_message.argtypes = (
            ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint, ctypes.c_int,
            ctypes.POINTER(_Ajustes), ctypes.c_void_p)
        d.RHVoice_new_message.restype = ctypes.c_void_p
        d.RHVoice_speak.argtypes = (ctypes.c_void_p,)
        d.RHVoice_speak.restype = ctypes.c_int
        d.RHVoice_delete_message.argtypes = (ctypes.c_void_p,)
        d.RHVoice_delete_message.restype = None

    def _listar_perfiles(self) -> list:
        cuantos = int(self._dll.RHVoice_get_number_of_voice_profiles(self._motor))
        fichas = self._dll.RHVoice_get_voice_profiles(self._motor)
        return [_texto(fichas[i]) for i in range(cuantos)]

    def _listar_idiomas(self) -> dict:
        """De qué idioma es cada perfil, en el código de dos letras.

        RHVoice da el idioma en tres letras —``spa``, ``eng``— y los libros
        vienen marcados en dos. Sin traducirlo, el visor nunca encontraría una
        voz para un fragmento en otra lengua.
        """
        de_tres_a_dos = {
            "spa": "es", "eng": "en", "rus": "ru", "ukr": "uk", "pol": "pl",
            "por": "pt", "bra": "pt", "kat": "ka", "tat": "tt", "kir": "ky",
            "mkd": "mk", "sqi": "sq", "ces": "cs", "cze": "cs", "slk": "sk",
            "srp": "sr", "hrv": "hr", "uzb": "uz", "blr": "be", "bel": "be",
            "ron": "ro", "epo": "eo", "deu": "de", "fra": "fr", "ita": "it",
        }
        cuantos = int(self._dll.RHVoice_get_number_of_voices(self._motor))
        fichas = self._dll.RHVoice_get_voices(self._motor)
        salida = {}
        for i in range(cuantos):
            ficha = fichas[i]
            nombre = _texto(ficha.name)
            crudo = _texto(ficha.language).lower()
            # RHVoice da el idioma ya en dos letras —«es»—, que es como vienen
            # marcados los libros. La traducción de tres letras se queda por si
            # alguna voz de otro origen lo diera así, pero no es lo normal.
            lengua = crudo if len(crudo) == 2 else de_tres_a_dos.get(crudo, "")
            pais = _texto(ficha.country).upper()[:2]
            if lengua:
                salida[nombre] = "%s-%s" % (lengua, pais) if pais else lengua
        return salida

    # -- voces ---------------------------------------------------------------

    @property
    def disponible(self) -> bool:
        return self._motor is not None and bool(self._perfiles)

    def voces(self) -> list:
        return list(self._perfiles)

    def elegir_voz(self, nombre: str) -> bool:
        if nombre in self._perfiles:
            self._perfil = nombre
            return True
        return False

    def voz_actual(self) -> str:
        return self._perfil

    def voces_con_idioma(self) -> list:
        """Cada perfil con su idioma.

        Un perfil puede llevar dos voces mezcladas —el nombre lleva un ``+``— y
        entonces manda la primera, que es la que pone la pronunciación.
        """
        salida = []
        for perfil in self._perfiles:
            primera = perfil.split("+")[0]
            salida.append((perfil, self._idiomas.get(primera, "")))
        return salida

    def voz_para_idioma(self, codigo: str) -> str:
        if not codigo:
            return ""
        pedido = codigo.replace("_", "-").lower()
        lengua = pedido.split("-")[0]
        aproximada = ""
        for perfil, idioma in self.voces_con_idioma():
            suyo = (idioma or "").lower()
            if not suyo:
                continue
            if suyo == pedido:
                return perfil
            if suyo.split("-")[0] == lengua and not aproximada:
                aproximada = perfil
        return aproximada

    # -- ajustes -------------------------------------------------------------

    def establecer_velocidad(self, valor: int) -> None:
        """La velocidad, de la escala del visor a un multiplicador.

        RHVoice no tiene escala propia: se le dice «multiplica por esto». El 0
        del visor es 1.0 —la voz tal como viene— y de ahí hacia arriba y hacia
        abajo.
        """
        self._velocidad = self._multiplicador(valor)

    def establecer_volumen(self, valor: int) -> None:
        self._volumen = max(0.0, min(1.0, int(valor) / 100.0))

    @staticmethod
    def _multiplicador(valor: int) -> float:
        acotado = max(-10, min(10, int(valor)))
        if acotado >= 0:
            return 1.0 + acotado * (RELATIVO_MAXIMO - 1.0) / 10.0
        return 1.0 + acotado * (1.0 - RELATIVO_MINIMO) / 10.0

    @property
    def espera_maxima(self) -> float:
        try:
            return float(self._ajustes.get("espera_maxima", 6))
        except (TypeError, ValueError):
            return 6.0

    # -- hablar --------------------------------------------------------------

    def _recibir_muestreo(self, muestreo, datos) -> int:
        self._muestreo = int(muestreo)
        return 1

    def _recibir_sonido(self, muestras, cuantas, datos) -> int:
        if cuantas > 0 and muestras:
            self._pcm += ctypes.string_at(muestras, cuantas * 2)
        return 1

    def _acabar(self, datos) -> None:
        return None

    def decir(self, texto: str, con_marcas: bool = False) -> bool:
        """Sintetiza la frase entera y la reproduce.

        ``con_marcas`` se ignora: RHVoice entiende SSML, pero lo que llega es
        marcado de SAPI y no es lo mismo. Colar uno por otro haría que leyera
        las etiquetas en voz alta.
        """
        if not texto or self._motor is None:
            return False
        self.detener()
        with self._cerrojo:
            self._pcm = bytearray()
            ajustes = _Ajustes()
            ajustes.voice_profile = (self._perfil or "").encode("utf-8")
            ajustes.absolute_rate = 0.0
            ajustes.absolute_pitch = 0.0
            ajustes.absolute_volume = 0.0
            ajustes.relative_rate = getattr(self, "_velocidad", 1.0)
            ajustes.relative_pitch = self._multiplicador(
                int(self._ajustes.get("tono", 50)) // 5 - 10)
            ajustes.relative_volume = max(0.2, getattr(self, "_volumen", 1.0))
            ajustes.punctuation_mode = PUNTUACION.get(
                str(self._ajustes.get("puntuacion", "normal")), 0)
            ajustes.punctuation_list = None
            ajustes.capitals_mode = MAYUSCULAS.get(
                str(self._ajustes.get("mayusculas", "normal")), 0)
            ajustes.flags = 0
            crudo = texto.encode("utf-8")
            mensaje = self._dll.RHVoice_new_message(
                self._motor, crudo, len(crudo), 0, ctypes.byref(ajustes), None)
            if not mensaje:
                log.error("RHVoice no ha aceptado el texto")
                return False
            try:
                self._dll.RHVoice_speak(mensaje)
            finally:
                self._dll.RHVoice_delete_message(mensaje)
            if not self._pcm:
                return False
            return self._reproducir(bytes(self._pcm))

    def _reproducir(self, pcm: bytes) -> bool:
        try:
            from basskit.alto_nivel.reproductor import inicializar
            from basskit.constantes.bass import BASS_STREAM_PRESCAN
            from basskit.dlls.bass import bass
        except Exception as error:
            log.error("No está el reproductor de sonido: %s", error)
            return False
        if not self._bass:
            try:
                inicializar(-1, 44100)
            except Exception as error:
                log.debug("BASS ya estaba listo: %s", error)
            self._bass = True
        onda = _envolver_en_wav(pcm, self._muestreo)
        self._memoria = ctypes.create_string_buffer(onda)
        canal = bass.BASS_StreamCreateFile(True, self._memoria, 0, len(onda),
                                           BASS_STREAM_PRESCAN)
        if not canal:
            log.error("BASS no ha podido abrir el sonido de RHVoice")
            return False
        self._canal = canal
        self._pausado = False
        return bool(bass.BASS_ChannelPlay(canal, True))

    @staticmethod
    def con_tono(texto: str, tono: int) -> str:
        return texto

    def pausar(self) -> None:
        if self._canal and not self._pausado:
            from basskit.dlls.bass import bass

            bass.BASS_ChannelPause(self._canal)
            self._pausado = True

    def continuar(self) -> None:
        if self._canal and self._pausado:
            from basskit.dlls.bass import bass

            bass.BASS_ChannelPlay(self._canal, False)
            self._pausado = False

    def detener(self) -> None:
        self._pausado = False
        if self._canal:
            try:
                from basskit.dlls.bass import bass

                bass.BASS_ChannelStop(self._canal)
                bass.BASS_StreamFree(self._canal)
            except Exception as error:
                log.debug("Al detener RHVoice: %s", error)
            self._canal = 0

    @property
    def pausada(self) -> bool:
        return self._pausado

    @property
    def hablando(self) -> bool:
        if self._pausado:
            return True
        if not self._canal:
            return False
        try:
            from basskit.constantes.bass import BASS_ACTIVE_PLAYING
            from basskit.dlls.bass import bass

            return int(bass.BASS_ChannelIsActive(self._canal)) == BASS_ACTIVE_PLAYING
        except Exception:
            return False

    def cerrar(self) -> None:
        self.detener()
        if self._motor is not None and self._dll is not None:
            try:
                self._dll.RHVoice_delete_tts_engine(self._motor)
            except Exception as error:
                log.debug("Al cerrar RHVoice: %s", error)
            self._motor = None


def _envolver_en_wav(pcm: bytes, muestreo: int) -> bytes:
    """Le pone a las muestras la cabecera que espera un reproductor."""
    import struct

    canales, bits = 1, 16
    alineacion = canales * bits // 8
    return (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt "
            + struct.pack("<IHHIIHH", 16, 1, canales, muestreo,
                          muestreo * alineacion, alineacion, bits)
            + b"data" + struct.pack("<I", len(pcm)) + pcm)


def crear(carpeta, ajustes):
    """Lo que el visor llama para poner esta voz. Es la única entrada."""
    return MotorRHVoice(Path(carpeta), dict(ajustes or {}))
