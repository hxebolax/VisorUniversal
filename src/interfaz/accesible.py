# -*- coding: utf-8 -*-
"""Utilidades para que todos los controles tengan nombre accesible.

Cuando el usuario llega a un control con el tabulador, el lector de pantalla
anuncia su **nombre accesible**.  Si ese nombre falta, se oye solo el tipo de
control («cuadro de edición», «botón») y no hay forma de saber para qué sirve.

En Windows, la mayoría de los controles toman el nombre del texto estático que
tienen justo delante, siempre que ese texto se haya **creado antes** que el
control (el orden de creación es el que cuenta, no el del organizador).  Eso
funciona con cuadros de edición, listas, listas desplegables y deslizadores.

Pero hay excepciones comprobadas en este proyecto:

===========================  ========================================
Control                      Nombre que anunciaba
===========================  ========================================
``wx.SpinCtrl``              ninguno (``None``)
``wx.ColourPickerCtrl``      ``colourpicker``
``wx.Slider`` con etiquetas  ``70`` (su propio valor)
``wx.SpinCtrlDouble``        ``text``
===========================  ========================================

El último merece una advertencia: **no se usa en este programa y conviene no
empezar**.  ``wx.SpinCtrlDouble`` es un control compuesto —por dentro son un
``wx.TextCtrl`` y un ``wx.SpinButton``— y el foco cae en el cuadro de texto
interno.  Ni ponerle el nombre al contenedor con ``SetName``, ni pasarlo como
``name=`` al construirlo, ni forzarlo con un ``wx.Accessible`` propio hacen que
el lector de pantalla lo anuncie: lo que lee es el nombre de fábrica de la
pieza interior.  Donde hacía falta un número con decimales se usa ahora un
``wx.Choice`` con las opciones escritas, que además se elige más rápido.

El caso del deslizador merece una nota, porque no se arregla con este módulo
sino cambiando cómo se crea: el estilo ``wx.SL_LABELS`` le añade unas
etiquetas con el valor, y Windows deduce el nombre del control a partir del
texto que tiene justo delante, que pasa a ser esa etiqueta.  Un deslizador
creado **sin** ese estilo y precedido de su texto estático se anuncia
correctamente.

Por eso :func:`etiquetar` fija el nombre de forma explícita en lugar de
confiar en la deducción automática.  Aplicarlo a todos los controles, y no
solo a los problemáticos, cuesta lo mismo y evita que un cambio futuro de
disposición deje alguno mudo sin que nadie se dé cuenta.
"""

from __future__ import annotations

from typing import Callable, TypeVar

import wx

from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

C = TypeVar("C", bound=wx.Window)


class _NombreForzado(wx.Accessible):
    """Objeto de accesibilidad que fija el nombre **del propio control**.

    El detalle decisivo está en :meth:`GetName`: solo responde cuando se le
    pregunta por el control en sí (``id_hijo == 0``).  Para cualquier otro
    número devuelve «no implementado», con lo que el sistema recurre al
    comportamiento nativo.

    Sin esa distinción, un contenedor con nombre forzado se lo impone a todos
    sus hijos: cada pestaña, cada elemento de una lista y cada capítulo del
    índice se anunciarían con el nombre del contenedor en lugar del suyo.
    """

    #: Identificador con el que el sistema pregunta por el control en sí.
    CONTROL_EN_SI = 0

    def __init__(self, nombre: str) -> None:
        super().__init__()
        self._nombre = nombre

    def GetName(self, id_hijo):  # noqa: N802 (nombre impuesto por wxPython)
        """Devuelve el nombre del control, o cede el paso para sus hijos."""
        if id_hijo != self.CONTROL_EN_SI:
            return (wx.ACC_NOT_IMPLEMENTED, "")
        return (wx.ACC_OK, self._nombre)


def limpiar_etiqueta(texto: str) -> str:
    """Convierte el texto de una etiqueta en un nombre para anunciar.

    Quita el ampersand que marca la tecla de acceso rápido y los dos puntos
    finales, que al leerse en voz alta solo estorban.
    """
    return texto.replace("&", "").rstrip(": ").strip()


#: Controles a los que se les puede fijar el nombre a la fuerza sin efectos
#: secundarios, porque no tienen elementos propios que el lector deba nombrar
#: por separado.  La lista sale de medir el comportamiento real de cada tipo:
#: en los controles con elementos (listas, desplegables, árboles, pestañas,
#: deslizadores) wxWidgets contesta con el nombre del contenedor **también**
#: cuando el sistema pregunta por cada elemento, de modo que forzarlo haría
#: que todos los capítulos del índice se anunciaran igual.
_CONTROLES_SIN_ELEMENTOS = (wx.SpinCtrl, wx.SpinCtrlDouble, wx.TextCtrl,
                            wx.StaticBitmap, wx.Gauge)


def etiquetar(control: C, nombre: str) -> C:
    """Da nombre accesible a un control y lo devuelve.

    En la mayoría de los controles basta con el texto estático que tienen
    delante, así que aquí solo se guarda el nombre.  El nombre se impone por
    la fuerza únicamente en los tipos de :data:`_CONTROLES_SIN_ELEMENTOS`,
    donde se comprobó que hace falta —``wx.SpinCtrl`` no anuncia nada por sí
    solo— y donde no puede perjudicar a ningún elemento interior.

    :param control: Control al que se le pone nombre.
    :param nombre: Texto que debe anunciar el lector de pantalla.
    """
    limpio = limpiar_etiqueta(nombre)
    control.SetName(limpio)
    if isinstance(control, _CONTROLES_SIN_ELEMENTOS):
        try:
            control.SetAccessible(_NombreForzado(limpio))
            _nombrar_interiores(control, limpio)
        except Exception as error:  # pragma: no cover - plataformas sin MSAA
            log.debug("No se ha podido fijar el nombre accesible de %s: %s", limpio, error)
    return control


#: Piezas de las que se componen por dentro algunos controles y que son las que
#: de verdad reciben el foco.
_PIEZAS_INTERNAS = (wx.TextCtrl, wx.SpinButton)


def _nombrar_interiores(control: wx.Window, nombre: str) -> None:
    """Le pone el nombre también a las piezas internas del control.

    Hay controles que parecen uno solo y por dentro son varios.  El caso que lo
    destapó fue ``wx.SpinCtrlDouble``: en Windows se compone de un ``TextCtrl``
    y un ``SpinButton``, y **el foco cae en el cuadro de texto interno**, no en
    el contenedor.  Por eso, aunque el contenedor tuviera su nombre bien puesto,
    el lector de pantalla anunciaba «text»: estaba leyendo el nombre de fábrica
    de esa pieza interior.

    ``wx.SpinCtrl`` no tiene este problema porque en Windows es un control
    nativo único, así que el fallo solo se veía en los pocos sitios donde hace
    falta un número con decimales.
    """
    for hijo in control.GetChildren():
        if not isinstance(hijo, _PIEZAS_INTERNAS):
            continue
        hijo.SetName(nombre)
        try:
            hijo.SetAccessible(_NombreForzado(nombre))
        except Exception:      # pragma: no cover - plataformas sin MSAA
            pass


def fila_etiquetada(padre: wx.Window, contenedor: wx.Sizer, etiqueta: str,
                    fabrica: Callable[[wx.Window], C], margen: int = 6,
                    horizontal: bool = False, proporcion: int = 0) -> C:
    """Crea una etiqueta y su control, en el orden correcto y ya enlazados.

    :param padre: Ventana donde se crean.
    :param contenedor: Organizador al que se añaden.
    :param etiqueta: Texto visible de la etiqueta, con su ``&`` si procede.
    :param fabrica: Función que crea el control.
    :param margen: Separación en píxeles.
    :param horizontal: Si la etiqueta va al lado en vez de encima.
    :param proporcion: Proporción del control dentro de su fila.
    :return: El control ya creado y con nombre.
    """
    # La etiqueta se crea **antes** que el control a propósito: ese orden es
    # el que usa Windows para deducir a qué control pertenece cada texto.
    texto = wx.StaticText(padre, label=etiqueta)
    control = fabrica(padre)
    etiquetar(control, etiqueta)
    if horizontal:
        fila = wx.BoxSizer(wx.HORIZONTAL)
        fila.Add(texto, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, margen)
        fila.Add(control, max(proporcion, 1), wx.EXPAND)
        contenedor.Add(fila, 0, wx.EXPAND | wx.ALL, margen)
    else:
        contenedor.Add(texto, 0, wx.LEFT | wx.RIGHT | wx.TOP, margen)
        contenedor.Add(control, proporcion, wx.EXPAND | wx.ALL, margen)
    return control
