# -*- coding: utf-8 -*-
"""Anuncios para lectores de pantalla.

La aplicación se comunica con el lector de pantalla por tres vías, que se
complementan:

1. **Movimiento del cursor.**  El texto del libro está en un control de
   edición real, así que al mover el cursor el lector de pantalla lee la
   nueva línea por sí solo, sin que la aplicación haga nada.  Esta es la vía
   principal y funciona con todos los lectores.

2. **Región activa.**  Para la información añadida («encabezado de nivel 2»,
   «no hay más imágenes», «se continúa desde el principio») se usa una
   etiqueta invisible marcada como *región activa*.  Al cambiar su texto se
   avisa al sistema de accesibilidad de Windows con ``NotifyWinEvent``, y el
   lector de pantalla lo lee sin robar el foco.

3. **Biblioteca de voz directa.**  Si está instalado ``accessible_output2``,
   se habla directamente con NVDA, JAWS o el narrador del sistema, que es la
   vía más fiable.  Es opcional: si no está, se usan las dos anteriores.

4. **Línea braille.**  Esa misma biblioteca sabe mandar el aviso a la línea
   braille del lector de pantalla, y es una vía **distinta** de la voz: hablar
   no braillea.  Sin esto, quien lee en braille se pierde justo lo que no está
   escrito en el documento —«encabezado de nivel 2», «no hay más imágenes»,
   «marcador puesto»—, que es la mitad de lo que el programa cuenta.

Además, todo lo que se anuncia se escribe también en la barra de estado, de
modo que un usuario con resto visual pueda leerlo.
"""

from __future__ import annotations

import sys

import wx

from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

#: Evento de Windows que informa del cambio de una región activa.
_EVENT_OBJECT_LIVEREGIONCHANGED = 0x8019

#: Identificadores del objeto y del hijo en la API de accesibilidad de Windows.
_OBJID_CLIENT = -4
_CHILDID_SELF = 0

#: Espera, en milisegundos, antes de decir un aviso.  Da tiempo a que el foco
#: termine de moverse (al cerrarse un menú o un diálogo) para que el lector de
#: pantalla no tape el aviso con el nombre del control que recibe el foco.
RETARDO_NORMAL = 350

#: Sin espera: para avisos que no van seguidos de ningún cambio de foco.
RETARDO_INMEDIATO = 0

#: Biblioteca de voz directa.  Se carga una sola vez para toda la aplicación
#: porque la usan tanto el anunciador de la ventana principal como las voces
#: propias de los diálogos.
_voz_compartida = None
_voz_intentada = False


class SalidaAutomatica:
    """Elige sola por dónde hablar, como ``Auto`` de ``accessible_output2``.

    La diferencia está en la voz de Windows (SAPI 5).  ``Auto`` prepara al
    empezar **todas** las salidas, y la de SAPI 5 abre el sintetizador por COM
    y recorre las voces instaladas: unas décimas al arrancar —más con muchas
    voces, como las de Eloquence o Vocalizer— que se pagaban siempre, aunque
    hubiera un lector de pantalla delante y SAPI no se fuera a usar nunca.

    Aquí los lectores de pantalla se preparan al empezar, como antes, y la voz
    de Windows solo la primera vez que no haya ninguno activo.  El orden en que
    se prueban es el mismo que el de ``Auto``.
    """

    def __init__(self) -> None:
        import accessible_output2  # type: ignore
        from accessible_output2.outputs.base import OutputError  # type: ignore

        self._lectores = []
        self._clases_del_sistema = []
        for clase in accessible_output2.get_output_classes():
            if getattr(clase, "system_output", False):
                self._clases_del_sistema.append(clase)
                continue
            try:
                self._lectores.append(clase())
            except OutputError:
                pass
        self._del_sistema = None

    def _salidas_del_sistema(self) -> list:
        """Las salidas propias de Windows, preparadas la primera vez que hacen falta."""
        if self._del_sistema is None:
            self._del_sistema = []
            for clase in self._clases_del_sistema:
                try:
                    self._del_sistema.append(clase())
                except Exception as error:
                    log.debug("No se ha podido preparar %s: %s",
                              getattr(clase, "name", clase), error)
        return self._del_sistema

    def get_first_available_output(self):  # noqa: N802 (nombre de accessible_output2)
        """La primera salida activa: un lector de pantalla y, si no hay, Windows."""
        for salida in self._lectores:
            if salida.is_active():
                return salida
        for salida in self._salidas_del_sistema():
            if salida.is_active():
                return salida
        return None

    def speak(self, *args, **kwargs) -> None:
        """Dice el texto por la primera salida activa."""
        salida = self.get_first_available_output()
        if salida:
            salida.speak(*args, **kwargs)

    def braille(self, *args, **kwargs) -> None:
        """Escribe el texto en la línea braille de la primera salida activa."""
        salida = self.get_first_available_output()
        if salida:
            salida.braille(*args, **kwargs)

    def output(self, *args, **kwargs) -> None:
        """Igual que :meth:`speak`, como en ``Auto``."""
        self.speak(*args, **kwargs)

    def is_system_output(self):  # noqa: N802 (nombre de accessible_output2)
        """Si la salida que se usaría es la de Windows y no un lector."""
        salida = self.get_first_available_output()
        if salida:
            return salida.is_system_output()
        return None


def obtener_voz():
    """Devuelve la biblioteca de voz directa, cargándola la primera vez.

    :return: El objeto que habla con el lector de pantalla, o ``None`` si
             ``accessible_output2`` no está; en ese caso se anuncia por
             regiones activas.
    """
    global _voz_compartida, _voz_intentada
    if _voz_intentada:
        return _voz_compartida
    _voz_intentada = True
    try:
        _voz_compartida = SalidaAutomatica()
        log.info("Anuncios: se usará accessible_output2 (Auto)")
    except Exception as error:
        _voz_compartida = None
        log.info("accessible_output2 no disponible (%s); se usarán regiones activas", error)
    return _voz_compartida


def a_braille(voz, mensaje: str) -> bool:
    """Manda un aviso a la línea braille, si la hay.

    Es una llamada aparte de la de hablar porque son dos canales distintos:
    ``speak`` no braillea nada y ``braille`` no dice nada.  Quien usa una línea
    braille sin voz depende por completo de esta.

    Los saltos de línea se convierten en espacios: una línea braille es una
    sola línea, y un aviso de tres renglones se quedaría en el primero.

    :return: Si se ha podido entregar.  No dice si había una línea braille
             conectada: ``accessible_output2`` no devuelve nada de eso, y
             preguntárselo al lector de pantalla no está en su interfaz.  Con
             el lector delante, escribir en braille sin línea conectada no hace
             nada y no molesta a nadie.
    """
    if voz is None or not mensaje:
        return False
    try:
        voz.braille(" ".join(mensaje.split()))
        return True
    except Exception as error:
        log.debug("No se ha podido escribir en la línea braille: %s", error)
        return False


class RegionActiva:
    """Etiqueta invisible que hace de región activa de una ventana.

    Al cambiar su texto se avisa al sistema de accesibilidad de Windows y el
    lector de pantalla lo lee sin robar el foco.

    :param ventana: Ventana donde se crea la etiqueta.
    """

    def __init__(self, ventana: wx.Window) -> None:
        # Se le da tamaño cero y no se muestra, pero debe existir como ventana
        # real para que el sistema de accesibilidad pueda referirse a ella.
        self._etiqueta = wx.StaticText(ventana, label="", size=(1, 1))
        self._etiqueta.Hide()
        self._usuario32 = None
        if sys.platform != "win32":
            return
        try:
            import ctypes

            self._usuario32 = ctypes.windll.user32
        except Exception as error:  # pragma: no cover - entorno sin Windows
            log.debug("No se ha podido acceder a user32: %s", error)

    def anunciar(self, mensaje: str) -> None:
        """Cambia el texto de la etiqueta y avisa al sistema de accesibilidad."""
        try:
            # Un texto idéntico al anterior puede no generar evento, así que
            # se añade un espacio alterno para forzar siempre el cambio.
            actual = self._etiqueta.GetLabel()
            self._etiqueta.SetLabel(mensaje + (" " if actual == mensaje else ""))
        except RuntimeError:
            return  # la ventana ya se ha destruido
        if self._usuario32 is None:
            return
        try:
            identificador = self._etiqueta.GetHandle()
            if identificador:
                self._usuario32.NotifyWinEvent(
                    _EVENT_OBJECT_LIVEREGIONCHANGED, identificador, _OBJID_CLIENT, _CHILDID_SELF
                )
        except Exception as error:  # pragma: no cover
            log.debug("NotifyWinEvent ha fallado: %s", error)


class Voz:
    """Dice mensajes al instante desde una ventana concreta.

    Cada diálogo crea la suya.  El motivo está en la región activa: la del
    :class:`Anunciador` vive en la ventana principal, y mientras hay un
    diálogo modal abierto los lectores de pantalla no leen las regiones
    activas de las ventanas que quedan detrás.  Con la voz directa daría
    igual, pero esa biblioteca es opcional y no se puede dar por supuesta.

    :param ventana: Ventana desde la que se anuncia.
    """

    def __init__(self, ventana: wx.Window, perezosa: bool = False) -> None:
        #: Con ``perezosa`` la biblioteca no se carga hasta el primer aviso.
        #: Lo pide la ventana principal, que se crea al arrancar: así la
        #: ventana sale antes y la biblioteca se prepara justo después.
        self._voz = None if perezosa else obtener_voz()
        self._perezosa = perezosa
        self._region = RegionActiva(ventana)

    def preparar(self) -> None:
        """Carga ya la biblioteca de voz, si se dejó para más tarde."""
        if self._perezosa:
            self._perezosa = False
            self._voz = obtener_voz()

    def decir(self, mensaje: str, interrumpir: bool = True) -> None:
        """Entrega el mensaje por la mejor vía disponible, sin esperas."""
        mensaje = (mensaje or "").strip()
        if not mensaje:
            return
        log.debug("Anuncio: %s", mensaje)
        self.preparar()
        if self._voz is not None:
            # A braille siempre, aunque la voz funcione: son dos canales y hay
            # quien solo usa uno de los dos.
            a_braille(self._voz, mensaje)
            try:
                self._voz.speak(mensaje, interrupt=interrumpir)
                return
            except Exception as error:
                log.debug("Fallo al hablar con el lector de pantalla: %s", error)
        self._region.anunciar(mensaje)


class Anunciador:
    """Envía mensajes al lector de pantalla del usuario.

    :param ventana: Ventana donde se creará la etiqueta de región activa.
    """

    def __init__(self, ventana: wx.Window) -> None:
        # La biblioteca de voz se carga justo después de enseñar la ventana
        # (o con el primer aviso, si llega antes), no mientras se construye.
        self._salida = Voz(ventana, perezosa=True)
        self._ultimo = ""
        self._temporizador: wx.CallLater | None = None
        wx.CallAfter(self._preparar_voz)
        # Un aviso que todavía espera su turno cuando se cierra la ventana se
        # cancela: si siguiera en marcha, su temporizador sobreviviría a la
        # ventana y avisaría a memoria ya liberada (ver ``temporizadores``).
        self._id_ventana = ventana.GetId()
        ventana.Bind(wx.EVT_WINDOW_DESTROY, self._al_destruir_ventana)

    def _al_destruir_ventana(self, evento: wx.WindowDestroyEvent) -> None:
        """Cancela el aviso pendiente al destruirse la ventana (no sus hijas)."""
        if evento.GetId() == self._id_ventana:
            temporizador, self._temporizador = self._temporizador, None
            if temporizador is not None:
                try:
                    temporizador.Stop()
                except (RuntimeError, AttributeError):
                    pass
        evento.Skip()

    def _preparar_voz(self) -> None:
        """Deja lista la biblioteca de voz en cuanto la ventana está a la vista."""
        try:
            self._salida.preparar()
        except Exception as error:   # pragma: no cover - salvaguarda
            log.debug("No se ha podido preparar la voz directa: %s", error)

    # -- anuncios ------------------------------------------------------------

    def anunciar(self, mensaje: str, interrumpir: bool = True,
                 retardo: int = RETARDO_NORMAL) -> None:
        """Hace llegar un mensaje al lector de pantalla.

        El mensaje **no se dice en el acto**, sino unas centésimas después.
        La razón es que muchos avisos se producen justo antes de que cambie el
        foco: al elegir una opción de menú, el menú se cierra y el foco vuelve
        al texto del libro, y el lector de pantalla anuncia entonces el control
        que acaba de recibir el foco, tapando lo que se hubiera dicho antes.
        Esperando a que el foco se asiente, el aviso se oye entero.

        :param mensaje: Texto que se debe leer.
        :param interrumpir: Si debe cortar lo que se esté leyendo.
        :param retardo: Milisegundos de espera.  Usa :data:`RETARDO_INMEDIATO`
                        cuando no hay ningún cambio de foco de por medio.
        """
        mensaje = (mensaje or "").strip()
        if not mensaje:
            return
        self._ultimo = mensaje
        if retardo <= 0:
            self._salida.decir(mensaje, interrumpir)
            return
        # Cada aviso nuevo cancela el anterior que estuviera esperando: si el
        # usuario encadena acciones deprisa, solo importa el último.
        if self._temporizador is not None and self._temporizador.IsRunning():
            self._temporizador.Stop()
        self._temporizador = wx.CallLater(retardo, self._salida.decir, mensaje, interrumpir)

    @property
    def ultimo_mensaje(self) -> str:
        """Último mensaje anunciado, para poder repetirlo."""
        return self._ultimo
