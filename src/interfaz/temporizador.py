# -*- coding: utf-8 -*-
"""Temporizador de apagado: dejar de leer al cabo de un rato.

Para dormirse escuchando.  Se pide un tiempo, se sigue leyendo y cuando se
cumple el plazo la lectura se para sola: la voz sintética si es lo que suena, o
la grabación si el libro es un DAISY.  Manda sobre las dos porque quien se está
durmiendo no distingue —ni tiene por qué— qué motor está sonando.

Dos detalles pensados para lo que es esto:

* **Se avisa un minuto antes**, con voz.  Sin ese aviso, quien todavía está
  despierto se encuentra con que el libro se corta de golpe y no sabe si es el
  temporizador o un fallo.
* **El sonido se apaga bajando el volumen**, no de un tajo.  Cortar en mitad de
  una frase despierta; bajar durante los últimos segundos, no.  En una
  grabación DAISY el volumen baja de forma continua; con la voz sintética baja
  frase a frase, porque SAPI fija el volumen al recibir cada texto y lo que ya
  está sonando conserva el suyo.
"""

from __future__ import annotations

import time

import wx

from interfaz.accesible import fila_etiquetada
from interfaz.dialogos import ayuda_opcion
from nucleo.idioma import _
from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

MARGEN = 8

#: Cada cuánto se mira si ha llegado la hora, en milisegundos.  Un segundo
#: basta y no se nota: nadie va a echar en falta la precisión de la décima
#: quedándose dormido.
LATIDO = 1000

#: Segundos antes del final en que se avisa de que queda poco.
AVISO = 60

#: Segundos durante los que se va bajando el volumen antes de callar.
DESVANECIDO = 20

#: Tiempos que se ofrecen, en minutos.  Para quitarlo está su propio botón, que
#: se entiende mejor que un «cero minutos» en la lista.
MINUTOS = (10, 15, 20, 30, 45, 60, 90, 120)


class Temporizador:
    """Cuenta atrás que detiene la lectura al terminar.

    :param ventana: Ventana principal, de la que salen el lector de voz, el
                    reproductor DAISY y los anuncios.
    """

    def __init__(self, ventana) -> None:
        self.ventana = ventana
        self._fin = 0.0
        self._avisado = False
        self._volumen_original = -1
        self._reloj = wx.Timer(ventana)
        ventana.Bind(wx.EVT_TIMER, self._al_latir, self._reloj)

    # -- estado --------------------------------------------------------------

    @property
    def activo(self) -> bool:
        """Indica si hay una cuenta atrás en marcha."""
        return self._reloj.IsRunning()

    def restante(self) -> float:
        """Segundos que quedan, o cero si no hay nada en marcha."""
        return max(0.0, self._fin - time.monotonic()) if self.activo else 0.0

    def descripcion(self) -> str:
        """Cuánto queda, dicho de forma que se entienda al oírlo."""
        if not self.activo:
            return _("El temporizador está apagado.")
        segundos = int(self.restante())
        if segundos >= 60:
            minutos = segundos // 60
            return _("La lectura se detendrá dentro de %d minutos.") % minutos
        return _("La lectura se detendrá dentro de %d segundos.") % segundos

    # -- gobierno ------------------------------------------------------------

    def poner(self, minutos: int) -> None:
        """Arranca la cuenta atrás, o la quita si se piden cero minutos."""
        self.quitar(anunciar=False)
        if minutos <= 0:
            self.ventana.anunciar(_("Temporizador quitado."), inmediato=True)
            return
        self._fin = time.monotonic() + minutos * 60
        self._avisado = False
        self._volumen_original = -1
        self._reloj.Start(LATIDO)
        log.info("Temporizador de apagado puesto en %d minutos", minutos)
        self.ventana.anunciar(
            _("La lectura se detendrá dentro de %d minutos.") % minutos, inmediato=True)

    def quitar(self, anunciar: bool = True) -> None:
        """Cancela la cuenta atrás y deja el volumen como estaba."""
        estaba = self.activo
        self._reloj.Stop()
        self._restaurar_volumen()
        self._fin = 0.0
        self._avisado = False
        if estaba and anunciar:
            self.ventana.anunciar(_("Temporizador quitado."), inmediato=True)

    # -- funcionamiento ------------------------------------------------------

    def _al_latir(self, evento) -> None:
        """Mira si toca avisar, bajar el volumen o parar.

        El temporizador de la ventana es compartido, así que hay que comprobar
        que el aviso es el de este reloj y no el del latido de la voz.
        """
        if evento.GetTimer() is not self._reloj:
            evento.Skip()
            return
        quedan = self.restante()
        if quedan <= 0:
            self._parar()
            return
        if not self._avisado and quedan <= AVISO:
            self._avisado = True
            self.ventana.anunciar(_("Queda un minuto de lectura."), inmediato=True)
        if quedan <= DESVANECIDO:
            self._bajar_volumen(quedan)

    def _bajar_volumen(self, quedan: float) -> None:
        """Va apagando el sonido durante los últimos segundos."""
        proporcion = max(0.0, min(1.0, quedan / DESVANECIDO))
        reproductor = getattr(self.ventana, "reproductor_daisy", None)
        if reproductor is not None and reproductor.sonando:
            if self._volumen_original < 0:
                self._volumen_original = reproductor.altavoz.volumen
            reproductor.altavoz.volumen = int(self._volumen_original * proporcion)
            return
        voz = self.ventana.lectura_voz
        if voz.leyendo:
            if self._volumen_original < 0:
                self._volumen_original = int(
                    self.ventana.configuracion.obtener("voz_volumen", 100))
            voz.sintetizador.establecer_volumen(int(self._volumen_original * proporcion))

    def _restaurar_volumen(self) -> None:
        """Devuelve el volumen que había antes de empezar a bajarlo."""
        if self._volumen_original < 0:
            return
        reproductor = getattr(self.ventana, "reproductor_daisy", None)
        if reproductor is not None and reproductor.activo:
            reproductor.altavoz.volumen = self._volumen_original
        self.ventana.lectura_voz.sintetizador.establecer_volumen(self._volumen_original)
        self._volumen_original = -1

    def _parar(self) -> None:
        """Se acabó el tiempo: se detiene lo que estuviera sonando."""
        self._reloj.Stop()
        reproductor = getattr(self.ventana, "reproductor_daisy", None)
        if reproductor is not None and reproductor.sonando:
            reproductor.detener()
        self.ventana.lectura_voz.detener()
        self._restaurar_volumen()
        self._fin = 0.0
        log.info("El temporizador de apagado ha detenido la lectura")
        self.ventana.anunciar(_("Se acabó el tiempo. Lectura detenida."), inmediato=True)


class DialogoTemporizador(wx.Dialog):
    """Pregunta cuánto tiempo se quiere seguir escuchando.

    :param padre: Ventana principal.
    :param temporizador: El temporizador al que hay que dar la orden.
    """

    def __init__(self, padre: wx.Window, temporizador: Temporizador) -> None:
        super().__init__(padre, title=_("Temporizador de apagado"),
                         style=wx.DEFAULT_DIALOG_STYLE)
        self.temporizador = temporizador
        self.configuracion = padre.configuracion

        contenedor = wx.BoxSizer(wx.VERTICAL)
        contenedor.Add(wx.StaticText(self, label=temporizador.descripcion()),
                       0, wx.ALL, MARGEN)

        opciones = [_("%d minutos") % minutos for minutos in MINUTOS]
        self.tiempo = fila_etiquetada(
            self, contenedor, _("&Detener la lectura dentro de:"),
            lambda p: wx.Choice(p, choices=opciones),
            margen=MARGEN, horizontal=True, proporcion=1)
        guardados = int(self.configuracion.obtener("voz_temporizador_minutos", 30))
        self.tiempo.SetSelection(MINUTOS.index(guardados) if guardados in MINUTOS
                                 else MINUTOS.index(30))

        contenedor.Add(wx.StaticText(self, label=_(
            "Se avisa un minuto antes y el sonido se apaga poco a poco en los últimos\n"
            "segundos, para no despertar a nadie de golpe. Vale igual para la voz\n"
            "sintética y para las grabaciones DAISY.")), 0, wx.ALL, MARGEN)

        botones = wx.BoxSizer(wx.HORIZONTAL)
        aceptar = wx.Button(self, wx.ID_OK, _("&Poner"))
        aceptar.SetDefault()
        botones.Add(aceptar, 0, wx.ALL, 5)
        self.boton_quitar = wx.Button(self, label=_("&Quitar el temporizador"))
        self.boton_quitar.Bind(wx.EVT_BUTTON, self._al_quitar)
        self.boton_quitar.Enable(temporizador.activo)
        botones.Add(self.boton_quitar, 0, wx.ALL, 5)
        botones.Add(wx.Button(self, wx.ID_CANCEL, _("&Cancelar")), 0, wx.ALL, 5)
        contenedor.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 4)

        self.SetSizerAndFit(contenedor)
        self.CenterOnParent()
        ayuda_opcion.enganchar(self)
        self.tiempo.SetFocus()

    def _al_quitar(self, evento) -> None:
        """Cancela la cuenta atrás y cierra."""
        self.temporizador.quitar()
        self.EndModal(wx.ID_CANCEL)

    def minutos(self) -> int:
        """Los minutos elegidos."""
        return MINUTOS[max(0, self.tiempo.GetSelection())]
