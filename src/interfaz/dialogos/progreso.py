# -*- coding: utf-8 -*-
"""Ventana de progreso para las operaciones que tardan.

Abrir un libro va de una décima de segundo —un EPUB normal— a varios minutos
—un PDF escaneado que hay que reconocer página a página—.  Sin nada que lo
cuente, esos minutos son un silencio en el que no se sabe si el programa está
trabajando o se ha colgado, y no hay forma de echarse atrás.

Esta ventana resuelve las tres cosas: **dice por dónde va**, **deja cancelar** y
lo hace de forma que se entienda de oído.

Ese último punto obliga a un detalle que no es evidente: **no se anuncia cada
paso**.  Un PDF de trescientas páginas dispararía trescientos avisos, y el
lector de pantalla se pasaría el rato cortándose a sí mismo sin que se entienda
ninguno.  Se anuncia al empezar, al terminar y de tanto en tanto por el camino
(:data:`SALTO_ANUNCIO`).  La barra, en cambio, se actualiza siempre: quien la
consulte a propósito verá el número exacto.
"""

from __future__ import annotations

import time

import wx

from interfaz.dialogos import ayuda_opcion
from interfaz.accesible import etiquetar
from interfaz.anuncios import Voz
from nucleo.idioma import _
from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

MARGEN = 12

#: Cada cuántos puntos porcentuales se dice en voz alta cómo va.
SALTO_ANUNCIO = 10

#: Segundos que como mínimo pasan entre dos anuncios, para que un trabajo muy
#: rápido no dispare varios seguidos.
ESPERA_ANUNCIO = 3.0

#: Milisegundos que se espera antes de enseñar la ventana.  Véase
#: :meth:`DialogoProgreso.mostrar_tras`.
RETARDO = 500


class DialogoProgreso(wx.Dialog):
    """Muestra el avance de una operación larga y permite cancelarla.

    Se usa así: se crea, se muestra sin bloquear (``Show``), y quien hace el
    trabajo llama a :meth:`avanzar` desde su hilo —el método ya se encarga de
    saltar al hilo de la interfaz—.  Al terminar se llama a :meth:`cerrar`.

    :param padre: Ventana desde la que se abre.
    :param titulo: Título de la ventana.
    :param mensaje: Qué se está haciendo, para el primer aviso.
    :param al_cancelar: Función que se llama si el usuario cancela.
    """

    def __init__(self, padre: wx.Window, titulo: str, mensaje: str, al_cancelar=None) -> None:
        super().__init__(padre, title=titulo, style=wx.CAPTION | wx.RESIZE_BORDER)
        self._al_cancelar = al_cancelar
        self._voz = Voz(self)
        self._mensaje = mensaje
        self._retardo = None
        self._ultimo_anuncio = 0.0
        self._ultimo_porcentaje = -SALTO_ANUNCIO
        self.cancelado = False

        contenedor = wx.BoxSizer(wx.VERTICAL)
        self.mensaje = wx.StaticText(self, label=mensaje)
        contenedor.Add(self.mensaje, 0, wx.ALL, MARGEN)

        # La barra lleva nombre accesible propio: al consultarla con el cursor
        # del lector de pantalla debe decir de qué es, no solo un número.
        self.barra = etiquetar(wx.Gauge(self, range=100, size=(380, 22)), _("Progreso"))
        contenedor.Add(self.barra, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, MARGEN)

        self.detalle = wx.StaticText(self, label="")
        contenedor.Add(self.detalle, 0, wx.ALL, MARGEN)

        fila = wx.StdDialogButtonSizer()
        self.boton = wx.Button(self, wx.ID_CANCEL, _("&Cancelar"))
        self.boton.SetDefault()
        fila.AddButton(self.boton)
        fila.Realize()
        contenedor.Add(fila, 0, wx.EXPAND | wx.ALL, MARGEN)
        self.SetSizerAndFit(contenedor)
        self.CentreOnParent()

        self.boton.Bind(wx.EVT_BUTTON, self._al_pulsar_cancelar)
        self.Bind(wx.EVT_CLOSE, self._al_pulsar_cancelar)
        self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar_tecla)
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    # -- aparición -----------------------------------------------------------

    def mostrar_tras(self, milisegundos: int = RETARDO) -> None:
        """Enseña la ventana, pero solo si la operación pasa de un instante.

        Un EPUB normal se abre en una décima de segundo.  Sacar y quitar una
        ventana en ese tiempo es un parpadeo que no informa de nada y que
        además le roba el foco al lector de pantalla justo cuando va a leer el
        libro.  Con este retardo la ventana aparece únicamente cuando hay una
        espera de verdad —un PDF escaneado, un libro enorme—, que es cuando
        hace falta.
        """
        self._retardo = wx.CallLater(milisegundos, self._mostrar_ahora)

    def _mostrar_ahora(self) -> None:
        """Saca la ventana y dice de qué es."""
        try:
            if not self or self.IsShown():
                return
            self.Show()
            self._voz.decir(self._mensaje)
        except RuntimeError:
            pass

    # -- avance --------------------------------------------------------------

    def avanzar(self, hecho: int, total: int, detalle: str = "") -> None:
        """Actualiza el progreso.  Se puede llamar desde cualquier hilo."""
        wx.CallAfter(self._pintar, hecho, total, detalle)

    def _pintar(self, hecho: int, total: int, detalle: str) -> None:
        """Refresca la ventana.  Corre siempre en el hilo de la interfaz."""
        if not self:
            return
        try:
            if total > 0:
                porcentaje = max(0, min(100, int(hecho * 100 / total)))
                self.barra.SetValue(porcentaje)
            else:
                # Sin total conocido, la barra solo puede latir.
                porcentaje = -1
                self.barra.Pulse()
            if detalle:
                self.detalle.SetLabel(detalle)
            self._quizas_anunciar(porcentaje, detalle)
        except RuntimeError:
            pass        # la ventana ya se está destruyendo

    def _quizas_anunciar(self, porcentaje: int, detalle: str) -> None:
        """Dice cómo va, pero solo de vez en cuando.

        Anunciar cada paso llenaría el oído de avisos cortados; anunciar cada
        pocos puntos, y nunca dos veces seguidas en menos de unos segundos,
        mantiene la sensación de avance sin estorbar.
        """
        ahora = time.monotonic()
        if porcentaje < 0 or not self.IsShown():
            # Mientras la ventana está escondida no hay a quién decírselo: el
            # aviso va por su región activa, que solo se lee si se ve.
            return
        if porcentaje < self._ultimo_porcentaje + SALTO_ANUNCIO:
            return
        if ahora - self._ultimo_anuncio < ESPERA_ANUNCIO:
            return
        self._ultimo_porcentaje = porcentaje
        self._ultimo_anuncio = ahora
        self._voz.decir("%d %%. %s" % (porcentaje, detalle) if detalle else "%d %%." % porcentaje)

    # -- cierre --------------------------------------------------------------

    def _al_pulsar_cancelar(self, evento) -> None:
        """Pide la cancelación y deja la ventana avisando de que va a parar."""
        if self.cancelado:
            return
        self.cancelado = True
        self.boton.Enable(False)
        self.detalle.SetLabel(_("Cancelando..."))
        self._voz.decir(_("Cancelando. Se parará en cuanto termine el paso en curso."))
        log.info("El usuario ha cancelado la operación en curso")
        if self._al_cancelar is not None:
            self._al_cancelar()

    def _al_pulsar_tecla(self, evento: wx.KeyEvent) -> None:
        """Escape cancela, como en cualquier otro diálogo."""
        if evento.GetKeyCode() == wx.WXK_ESCAPE:
            self._al_pulsar_cancelar(None)
            return
        evento.Skip()

    def cerrar(self) -> None:
        """Cierra la ventana.  Se puede llamar desde cualquier hilo."""
        wx.CallAfter(self._destruir)

    def _destruir(self) -> None:
        """Destruye la ventana si sigue viva."""
        try:
            if self._retardo is not None:
                self._retardo.Stop()
                self._retardo = None
            if self:
                self.Destroy()
        except RuntimeError:
            pass
