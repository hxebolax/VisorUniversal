# -*- coding: utf-8 -*-
"""Reproducción de audio, para las grabaciones de los libros DAISY.

Por debajo está **basskit**, la biblioteca del propio autor que envuelve BASS
de Un4seen.  Se eligió esa y no otra por tres cosas que un audiolibro necesita
y que las alternativas sencillas no dan:

* **Posicionar con precisión.**  Un libro DAISY no reproduce archivos, sino
  *recortes*: «de este MP3, del segundo 41,924 al 46,911».  Hay que poder
  saltar a un punto exacto y saber en todo momento por dónde va.
* **Cambiar la velocidad sin cambiar el tono.**  Escuchar a 1,5× o a 2× es lo
  normal entre quienes leen de oído, y hacerlo acelerando la reproducción a
  secas convierte al narrador en un pato.  BASS_FX lo hace bien.
* **Abrir lo que traiga el libro.**  MP3 de 1998, WAV, y también los formatos
  nuevos.  BASS los abre todos.

Este módulo no sabe nada de DAISY: recibe archivos y segundos.  La lógica del
libro está en :mod:`interfaz.reproductor_daisy`.
"""

from __future__ import annotations

import ctypes
import threading
from pathlib import Path

from nucleo.idioma import _
from nucleo.registro import obtener_registro, registrar_excepcion

log = obtener_registro(__name__)

#: Velocidad normal, en porcentaje.  Es la referencia de toda la escala.
VELOCIDAD_NORMAL = 100

#: Hasta dónde se deja llegar.  BASS admite mucho más, pero por debajo de la
#: mitad la voz se vuelve pastosa y por encima del triple es ininteligible.
VELOCIDAD_MINIMA = 50
VELOCIDAD_MAXIMA = 300

#: Cuánto se salta con «avanzar» y «retroceder», en segundos.
SALTO = 10.0

_cerrojo = threading.Lock()
_iniciado = False
_fallo_al_iniciar = ""


def disponible() -> bool:
    """Indica si se puede reproducir audio en este equipo."""
    try:
        import basskit  # noqa: F401
    except Exception:
        return False
    return True


def motivo_no_disponible() -> str:
    """Explica qué falta para poder reproducir, o cadena vacía si no falta nada."""
    if not disponible():
        return _(
            "Para escuchar la grabación de un libro DAISY hace falta el complemento "
            "«basskit», que no está instalado.\n\n"
            "Instálalo con: pip install basskit")
    if _fallo_al_iniciar:
        return _("No se ha podido abrir la tarjeta de sonido:\n\n%s") % _fallo_al_iniciar
    return ""


def iniciar() -> bool:
    """Arranca el sistema de sonido.  Se puede llamar las veces que haga falta.

    :return: Si quedó listo para reproducir.
    """
    global _iniciado, _fallo_al_iniciar
    with _cerrojo:
        if _iniciado:
            return True
        try:
            from basskit.alto_nivel.reproductor import inicializar, obtener_version

            inicializar()
            _iniciado = True
            _fallo_al_iniciar = ""
            log.info("Sonido listo con BASS %s", obtener_version())
            return True
        except Exception as error:
            _fallo_al_iniciar = str(error)
            registrar_excepcion(log, "No se ha podido iniciar el sonido", error)
            return False


def terminar() -> None:
    """Suelta la tarjeta de sonido al cerrar el programa."""
    global _iniciado
    with _cerrojo:
        if not _iniciado:
            return
        try:
            from basskit.alto_nivel.reproductor import liberar

            liberar()
        except Exception as error:
            registrar_excepcion(log, "Fallo al soltar el sonido", error)
        _iniciado = False


class Altavoz:
    """Reproduce un archivo de audio con control de posición y de velocidad.

    Cada archivo se abre en dos capas: un flujo de descodificación y, encima,
    un flujo de *tempo* de BASS_FX.  Esa segunda capa es la que permite
    escuchar más deprisa **sin que suba el tono de la voz**, que es lo que se
    espera de un reproductor de audiolibros y no de un reproductor de música.
    """

    def __init__(self) -> None:
        self._canal = 0
        self._archivo = ""
        self._velocidad = VELOCIDAD_NORMAL
        self._volumen = 100

    # -- apertura ------------------------------------------------------------

    @property
    def archivo(self) -> str:
        """Archivo que está abierto ahora mismo."""
        return self._archivo

    @property
    def abierto(self) -> bool:
        """Si hay algo cargado."""
        return self._canal != 0

    def abrir(self, ruta) -> bool:
        """Carga un archivo de audio.  Si ya estaba cargado, no hace nada.

        :return: Si quedó listo para sonar.
        """
        destino = Path(ruta)
        if self._canal and self._archivo == str(destino):
            return True
        if not destino.exists():
            log.warning("No existe el audio %s", destino)
            return False
        if not iniciar():
            return False

        from basskit.constantes.bass import (BASS_STREAM_DECODE, BASS_STREAM_PRESCAN,
                                             BASS_UNICODE)
        from basskit.constantes.bass_fx import BASS_FX_FREESOURCE
        from basskit.dlls.bass import bass
        from basskit.dlls.bass_fx import bass_fx

        self.cerrar()
        nombre = str(destino).encode("utf-16-le") + b"\x00\x00"
        # PRESCAN es lo que hace que un MP3 de tasa variable —casi todos los
        # libros antiguos— se posicione en el segundo exacto en vez de «por
        # ahí»: sin él, saltar a una frase concreta cae fuera.
        fuente = bass.BASS_StreamCreateFile(
            0, nombre, 0, 0, BASS_UNICODE | BASS_STREAM_DECODE | BASS_STREAM_PRESCAN)
        if not fuente:
            log.warning("BASS no ha podido abrir %s (error %d)",
                        destino.name, bass.BASS_ErrorGetCode())
            return False
        canal = bass_fx.BASS_FX_TempoCreate(fuente, BASS_FX_FREESOURCE)
        if not canal:
            log.warning("BASS_FX no ha podido preparar %s (error %d)",
                        destino.name, bass.BASS_ErrorGetCode())
            bass.BASS_StreamFree(fuente)
            return False
        self._canal = canal
        self._archivo = str(destino)
        self._aplicar_velocidad()
        self._aplicar_volumen()
        return True

    def cerrar(self) -> None:
        """Suelta el archivo que estuviera abierto."""
        if not self._canal:
            return
        try:
            from basskit.dlls.bass import bass

            bass.BASS_StreamFree(self._canal)
        except Exception:
            pass
        self._canal = 0
        self._archivo = ""

    # -- transporte ----------------------------------------------------------

    def reproducir(self) -> None:
        """Empieza a sonar, o sigue donde se quedó."""
        if not self._canal:
            return
        from basskit.dlls.bass import bass

        bass.BASS_ChannelPlay(self._canal, 0)

    def pausar(self) -> None:
        """Detiene el sonido dejando la posición donde está."""
        if not self._canal:
            return
        from basskit.dlls.bass import bass

        bass.BASS_ChannelPause(self._canal)

    def parar(self) -> None:
        """Detiene el sonido."""
        if not self._canal:
            return
        from basskit.dlls.bass import bass

        bass.BASS_ChannelStop(self._canal)

    @property
    def sonando(self) -> bool:
        """Si en este instante está saliendo sonido."""
        if not self._canal:
            return False
        from basskit.constantes.bass import BASS_ACTIVE_PLAYING
        from basskit.dlls.bass import bass

        return bass.BASS_ChannelIsActive(self._canal) == BASS_ACTIVE_PLAYING

    @property
    def terminado(self) -> bool:
        """Si el archivo ha llegado al final."""
        if not self._canal:
            return True
        from basskit.constantes.bass import BASS_ACTIVE_STOPPED
        from basskit.dlls.bass import bass

        return bass.BASS_ChannelIsActive(self._canal) == BASS_ACTIVE_STOPPED

    # -- posición ------------------------------------------------------------

    @property
    def posicion(self) -> float:
        """Segundo por el que va."""
        if not self._canal:
            return 0.0
        from basskit.constantes.bass import BASS_POS_BYTE
        from basskit.dlls.bass import bass

        bytes_ = bass.BASS_ChannelGetPosition(self._canal, BASS_POS_BYTE)
        if bytes_ < 0:
            return 0.0
        return float(bass.BASS_ChannelBytes2Seconds(self._canal, bytes_))

    @posicion.setter
    def posicion(self, segundos: float) -> None:
        """Salta a un segundo concreto del archivo."""
        if not self._canal:
            return
        from basskit.constantes.bass import BASS_POS_BYTE
        from basskit.dlls.bass import bass

        destino = max(0.0, float(segundos))
        bytes_ = bass.BASS_ChannelSeconds2Bytes(self._canal, destino)
        bass.BASS_ChannelSetPosition(self._canal, bytes_, BASS_POS_BYTE)

    @property
    def duracion(self) -> float:
        """Lo que dura el archivo abierto."""
        if not self._canal:
            return 0.0
        from basskit.constantes.bass import BASS_POS_BYTE
        from basskit.dlls.bass import bass

        bytes_ = bass.BASS_ChannelGetLength(self._canal, BASS_POS_BYTE)
        if bytes_ < 0:
            return 0.0
        return float(bass.BASS_ChannelBytes2Seconds(self._canal, bytes_))

    # -- volumen y velocidad -------------------------------------------------

    @property
    def volumen(self) -> int:
        """Volumen de 0 a 100."""
        return self._volumen

    @volumen.setter
    def volumen(self, valor: int) -> None:
        """Cambia el volumen, al momento si hay algo sonando."""
        self._volumen = max(0, min(100, int(valor)))
        self._aplicar_volumen()

    def _aplicar_volumen(self) -> None:
        """Lleva el volumen al canal."""
        if not self._canal:
            return
        from basskit.constantes.bass import BASS_ATTRIB_VOL
        from basskit.dlls.bass import bass

        bass.BASS_ChannelSetAttribute(self._canal, BASS_ATTRIB_VOL, self._volumen / 100.0)

    @property
    def velocidad(self) -> int:
        """Velocidad en porcentaje: 100 es la del narrador."""
        return self._velocidad

    @velocidad.setter
    def velocidad(self, valor: int) -> None:
        """Cambia la velocidad al vuelo, sin alterar el tono de la voz."""
        self._velocidad = max(VELOCIDAD_MINIMA, min(VELOCIDAD_MAXIMA, int(valor)))
        self._aplicar_velocidad()

    @property
    def velocidad_normal(self) -> bool:
        """Si va a la velocidad a la que se grabó."""
        return self._velocidad == VELOCIDAD_NORMAL

    def _aplicar_velocidad(self) -> None:
        """Lleva la velocidad al canal.

        BASS_FX cuenta el tempo como una **variación porcentual**: 0 es la
        velocidad original, +50 es vez y media, -25 es tres cuartos.  Aquí se
        maneja en porcentaje absoluto porque es lo que entiende quien lo usa.
        """
        if not self._canal:
            return
        from basskit.constantes.bass_fx import BASS_ATTRIB_TEMPO
        from basskit.dlls.bass import bass

        bass.BASS_ChannelSetAttribute(
            self._canal, BASS_ATTRIB_TEMPO, float(self._velocidad - VELOCIDAD_NORMAL))

    def velocidad_real(self) -> float:
        """Lo que BASS dice que está aplicando, para comprobaciones."""
        if not self._canal:
            return 0.0
        from basskit.constantes.bass_fx import BASS_ATTRIB_TEMPO
        from basskit.dlls.bass import bass

        valor = ctypes.c_float(0.0)
        bass.BASS_ChannelGetAttribute(self._canal, BASS_ATTRIB_TEMPO, ctypes.byref(valor))
        return VELOCIDAD_NORMAL + valor.value

    def __del__(self) -> None:
        self.cerrar()


def duracion_legible(segundos: float) -> str:
    """Escribe una duración como la diría una persona.

    Se usa en los anuncios de voz, así que se dice «una hora y cinco minutos»
    en vez de «1:05:00»: un lector de pantalla lee lo segundo dígito a dígito.
    """
    total = max(0, int(round(segundos)))
    horas, resto = divmod(total, 3600)
    minutos, segundos_ = divmod(resto, 60)
    partes = []
    if horas:
        partes.append(_("%d horas") % horas if horas != 1 else _("una hora"))
    if minutos:
        partes.append(_("%d minutos") % minutos if minutos != 1 else _("un minuto"))
    if segundos_ or not partes:
        partes.append(_("%d segundos") % segundos_ if segundos_ != 1 else _("un segundo"))
    if len(partes) == 1:
        return partes[0]
    return _("%s y %s") % (", ".join(partes[:-1]), partes[-1])


def reloj(segundos: float) -> str:
    """Escribe una duración como un reloj, para las etiquetas de la pantalla."""
    total = max(0, int(segundos))
    return "%d:%02d:%02d" % (total // 3600, (total % 3600) // 60, total % 60)
