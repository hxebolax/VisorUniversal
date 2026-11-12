# -*- coding: utf-8 -*-
"""Ventana de repaso: lo marcado vuelve cuando toca.

Cada tarjeta se enseña en dos tiempos. Primero, **de dónde sale** y, si la
escribiste, tu nota: eso es la pregunta. Después de intentar recordarlo, se
descubre el pasaje. Y entonces se responde con una de tres teclas.

Los dos tiempos no son un adorno: recordar y reconocer no son lo mismo, y una
tarjeta que enseña la respuesta a la vez que la pregunta no enseña nada. Por eso
la respuesta está detrás de una tecla y no debajo, donde el cursor la leería
sola al bajar.

**Se maneja entero con el teclado y sin mirar.** Espacio descubre; después, las
teclas 1, 2 y 3 son las tres respuestas, en el orden en que están los botones.
"""

from __future__ import annotations

import wx

from interfaz.dialogos import ayuda_opcion
from interfaz.accesible import etiquetar
from nucleo import repaso as motor
from nucleo.idioma import _, _n
from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

MARGEN = 8


class DialogoRepaso(wx.Dialog):
    """Pasa una tanda de repaso por lo marcado en los libros que se le den."""

    def __init__(self, padre: wx.Window, apuntes, configuracion) -> None:
        super().__init__(padre, title=_("Repasar"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.configuracion = configuracion
        self.repaso = motor.cargar()
        self.tanda = self.repaso.pendientes(apuntes)
        self.actual = 0
        self.descubierta = False
        #: Cuántas se han respondido de cada manera, para decirlo al acabar.
        self.cuenta = {"no": 0, "regular": 0, "si": 0}

        self.SetSize((720, 520))
        contenedor = wx.BoxSizer(wx.VERTICAL)

        self.avance = wx.StaticText(self, label="")
        fuente = self.avance.GetFont()
        self.avance.SetFont(fuente.Bold())
        contenedor.Add(self.avance, 0, wx.ALL, MARGEN)

        # Cuadro de solo lectura y no una etiqueta: así el texto se recorre con
        # las flechas y se puede releer el trozo que interese, que es lo que
        # hace falta para intentar recordar algo y no solo para oírlo pasar.
        self.tarjeta = etiquetar(
            wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY
                        | wx.TE_WORDWRAP, size=(680, 300)),
            _("La tarjeta"))
        contenedor.Add(self.tarjeta, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, MARGEN)

        self.boton_descubrir = wx.Button(self, label=_("&Descubrir (Espacio)"))
        contenedor.Add(self.boton_descubrir, 0, wx.ALL, MARGEN)

        fila = wx.BoxSizer(wx.HORIZONTAL)
        self.botones = []
        for numero, (clave, rotulo) in enumerate(motor.nombres_de_respuesta(),
                                                 start=1):
            boton = wx.Button(self, label="&%d %s" % (numero, rotulo))
            boton.Bind(wx.EVT_BUTTON,
                       lambda evento, c=clave: self._responder(c))
            fila.Add(boton, 0, wx.RIGHT, MARGEN)
            self.botones.append(boton)
        contenedor.Add(fila, 0, wx.LEFT | wx.RIGHT, MARGEN)

        pie = wx.BoxSizer(wx.HORIZONTAL)
        pie.AddStretchSpacer()
        pie.Add(wx.Button(self, wx.ID_CANCEL, _("Dejarlo por &hoy")), 0)
        contenedor.Add(pie, 0, wx.EXPAND | wx.ALL, MARGEN)
        self.SetSizer(contenedor)
        self.Layout()

        self.boton_descubrir.Bind(wx.EVT_BUTTON, lambda evento: self._descubrir())
        self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar)
        self.Bind(wx.EVT_BUTTON, self._al_cerrar, id=wx.ID_CANCEL)

        self._pintar()
        self.tarjeta.SetFocus()
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    # -- las tarjetas --------------------------------------------------------

    def _pintar(self) -> None:
        """Escribe la tarjeta que toca, tapada."""
        if self.actual >= len(self.tanda):
            self._terminar()
            return
        apunte = self.tanda[self.actual]
        tarjeta = self.repaso.de(motor.clave_de(apunte.ruta, apunte.posicion))
        self.avance.SetLabel(_("%(numero)d de %(total)d · %(estado)s") % {
            "numero": self.actual + 1, "total": len(self.tanda),
            "estado": _("sin empezar") if tarjeta.es_nueva else _("repaso")})

        piezas = [apunte.de_donde()]
        if apunte.etiquetas:
            piezas.append(_("Etiquetas: %s") % ", ".join(apunte.etiquetas))
        if apunte.nota:
            piezas.append("")
            piezas.append(_("Tu nota: %s") % apunte.nota)
        piezas.append("")
        piezas.append(_("¿Qué decía este pasaje? Pulsa Espacio para verlo."))
        self.tarjeta.SetValue("\n".join(piezas))
        self.descubierta = False
        self._habilitar(False)

    def _descubrir(self) -> None:
        """Enseña el pasaje y deja responder."""
        if self.descubierta or self.actual >= len(self.tanda):
            return
        apunte = self.tanda[self.actual]
        piezas = [apunte.de_donde()]
        if apunte.nota:
            piezas.append(_("Tu nota: %s") % apunte.nota)
        piezas.append("")
        piezas.append(apunte.texto or _("(este apunte solo tenía tu nota)"))
        self.tarjeta.SetValue("\n".join(piezas))
        self.descubierta = True
        self._habilitar(True)
        self.botones[0].SetFocus()

    def _habilitar(self, descubierta: bool) -> None:
        self.boton_descubrir.Enable(not descubierta)
        for boton in self.botones:
            boton.Enable(descubierta)

    def _responder(self, clave: str) -> None:
        """Apunta la respuesta y pasa a la siguiente."""
        if not self.descubierta or self.actual >= len(self.tanda):
            return
        apunte = self.tanda[self.actual]
        tarjeta = self.repaso.de(motor.clave_de(apunte.ruta, apunte.posicion))
        tarjeta.responder(clave)
        self.cuenta[clave] = self.cuenta.get(clave, 0) + 1
        self.actual += 1
        self._guardar()
        self._pintar()
        self.tarjeta.SetFocus()

    def _guardar(self) -> None:
        """Escribe lo repasado **después de cada tarjeta**.

        No al cerrar: si el programa se cae o se cierra la ventana con la cruz,
        lo repasado hasta ahí no se pierde. Son unos pocos kilobytes.
        """
        try:
            self.repaso.guardar()
        except OSError as error:                     # pragma: no cover
            log.info("No se ha podido guardar lo repasado: %s", error)

    def _terminar(self) -> None:
        """Dice cómo ha ido y cierra."""
        hechas = sum(self.cuenta.values())
        if not hechas:
            self.tarjeta.SetValue(_("Hoy no toca repasar nada. Vuelve mañana."))
            self.avance.SetLabel("")
            self._habilitar(False)
            self.boton_descubrir.Enable(False)
            return
        wx.MessageBox(
            _n("Repasada %d tarjeta.", "Repasadas %d tarjetas.", hechas) % hechas
            + "\n\n"
            + _("Lo sabías: %(si)d. Te ha costado: %(regular)d. No te acordabas: "
                "%(no)d.") % self.cuenta,
            _("Repasar"), wx.OK | wx.ICON_INFORMATION, self)
        self.EndModal(wx.ID_OK)

    # -- teclado -------------------------------------------------------------

    def _al_pulsar(self, evento: wx.KeyEvent) -> None:
        """Espacio descubre; 1, 2 y 3 responden."""
        codigo = evento.GetKeyCode()
        if codigo == wx.WXK_ESCAPE:
            self._al_cerrar(None)
            return
        if codigo == wx.WXK_SPACE and not self.descubierta:
            self._descubrir()
            return
        if self.descubierta and ord("1") <= codigo <= ord("3"):
            self._responder(motor.RESPUESTAS[codigo - ord("1")][0])
            return
        evento.Skip()

    def _al_cerrar(self, evento) -> None:
        del evento
        self._guardar()
        self.EndModal(wx.ID_CANCEL)
