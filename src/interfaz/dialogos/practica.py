# -*- coding: utf-8 -*-
"""Ventana del modo de práctica: se practica sobre el documento de verdad.

Esta ventana **no es modal**, y es la única decisión que de verdad importa aquí:
el ejercicio se hace en el documento, no en un recuadro. Se dice lo que hay que
hacer, se vuelve al texto con F6, se hace, y el programa avisa en cuanto sale.

Cómo se sabe que ha salido: se mira el documento cada poco —dónde está el
cursor, cuántos marcadores hay, qué se ha buscado— y se le pregunta al ejercicio
si ya está (:mod:`nucleo.practica`). Mirar cada poco, y no engancharse a cada
tecla, tiene una ventaja que no es de comodidad: da igual **cómo** se haya hecho.
Quien va al tercer encabezado con el árbol de contenido en vez de con `H` ha
hecho el ejercicio, y decirle que no lo ha hecho sería mentirle.

Todo lo que el programa dice aquí se anuncia por la ventana principal, que es
donde está el foco mientras se practica: un aviso dicho por una ventana que no
tiene el foco no lo oye nadie.
"""

from __future__ import annotations

import wx

from interfaz.temporizadores import parar_al_destruir
from interfaz.dialogos import ayuda_opcion
from interfaz.accesible import etiquetar
from nucleo import practica
from nucleo.idioma import _
from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

MARGEN = 8

#: Cada cuánto se mira el documento, en milisegundos. Un cuarto de segundo se
#: nota inmediato al hacer algo y no cuesta nada: lo que se mira son unos pocos
#: enteros que ya están calculados.
LATIDO = 250


class DialogoPractica(wx.Dialog):
    """Propone ejercicios sobre el documento abierto y avisa cuando salen.

    :param padre: La ventana principal.  Se le pregunta por el documento y se
                  le pide que anuncie, así que no vale cualquier ventana.
    :param configuracion: Preferencias, para anotar que ya se ha practicado.
    """

    def __init__(self, padre, configuracion) -> None:
        super().__init__(padre, title=_("Practicar"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.ventana = padre
        self.configuracion = configuracion
        self.inicial = self._mirar()
        self.ejercicios = practica.preparar(self._documento(), self.inicial)
        self.actual = 0
        self.hechos = 0
        self.saltados = 0
        #: El estado de cuando empezó **el ejercicio actual**. Se rehace en cada
        #: uno porque «pon un marcador» se mide contra los que había al empezar
        #: ese ejercicio, no contra los que había al abrir la ventana.
        self.desde = self.inicial

        contenedor = wx.BoxSizer(wx.VERTICAL)

        self.avance = wx.StaticText(self, label="")
        fuente = self.avance.GetFont()
        self.avance.SetFont(fuente.Bold())
        contenedor.Add(self.avance, 0, wx.ALL, MARGEN)

        # Cuadro de solo lectura y no una etiqueta: el enunciado se relee con
        # las flechas sin tener que pedir que lo repitan.
        self.enunciado = etiquetar(
            wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY
                        | wx.TE_WORDWRAP, size=(560, 180)),
            _("El ejercicio"))
        contenedor.Add(self.enunciado, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, MARGEN)

        pie = wx.BoxSizer(wx.HORIZONTAL)
        self.boton_repetir = wx.Button(self, label=_("&Repetir el enunciado"))
        pie.Add(self.boton_repetir, 0, wx.RIGHT, MARGEN)
        self.boton_saltar = wx.Button(self, label=_("&Saltar este"))
        pie.Add(self.boton_saltar, 0, wx.RIGHT, MARGEN)
        pie.AddStretchSpacer()
        pie.Add(wx.Button(self, wx.ID_CANCEL, _("&Terminar")), 0)
        contenedor.Add(pie, 0, wx.EXPAND | wx.ALL, MARGEN)
        self.SetSizerAndFit(contenedor)
        self.SetSize((640, 380))
        self.CenterOnParent()

        self.boton_repetir.Bind(wx.EVT_BUTTON, lambda evento: self._decir_enunciado())
        self.boton_saltar.Bind(wx.EVT_BUTTON, lambda evento: self._saltar())
        self.Bind(wx.EVT_BUTTON, self._al_terminar, id=wx.ID_CANCEL)
        self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar)
        self.Bind(wx.EVT_CLOSE, self._al_cerrar_ventana)

        self.reloj = wx.Timer(self)
        parar_al_destruir(self, self.reloj)
        self.Bind(wx.EVT_TIMER, lambda evento: self._comprobar(), self.reloj)

        self._pintar()
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    # -- mirar el documento ---------------------------------------------------

    def _documento(self):
        return getattr(self.ventana, "documento", None)

    def _mirar(self) -> practica.Estado:
        """Toma la foto del documento tal y como está ahora."""
        documento = self._documento()
        if documento is None:
            return practica.Estado()
        ultima = getattr(self.ventana, "_ultima_busqueda", None)
        termino = ultima[0] if ultima else ""
        try:
            posicion = self.ventana.lector.posicion()
        except Exception:                                # pragma: no cover
            posicion = 0
        return practica.estado_de(documento, posicion,
                                  getattr(self.ventana, "marcadores", ()),
                                  getattr(self.ventana, "resaltados", ()), termino)

    def _anunciar(self, mensaje: str) -> None:
        """Lo dice por la ventana principal, que es donde está el foco."""
        decir = getattr(self.ventana, "anunciar", None)
        if callable(decir):
            decir(mensaje, True)

    # -- los ejercicios -------------------------------------------------------

    def _pintar(self) -> None:
        """Enseña el ejercicio que toca y se pone a mirar."""
        if not self.ejercicios:
            self.avance.SetLabel("")
            self.enunciado.SetValue(practica.resumen(0, 0, 0))
            self.boton_repetir.Enable(False)
            self.boton_saltar.Enable(False)
            return
        if not self._buscar_uno_que_falte():
            self._terminar()
            return
        ejercicio = self.ejercicios[self.actual]
        self.avance.SetLabel(_("Ejercicio %(numero)d de %(total)d") % {
            "numero": self.actual + 1, "total": len(self.ejercicios)})
        self.enunciado.SetValue(
            "%s\n\n%s\n\n%s" % (ejercicio.enunciado, ejercicio.pista,
                                _("Vuelve al documento con F6 y hazlo. "
                                  "Te aviso en cuanto salga.")))
        self.enunciado.SetInsertionPoint(0)
        self._decir_enunciado()
        self.reloj.Start(LATIDO)

    def _buscar_uno_que_falte(self) -> bool:
        """Avanza hasta el primer ejercicio que no esté ya cumplido.

        El cursor está donde uno lo dejó, así que el primer ejercicio puede
        estar cumplido antes de empezar: quien se quedó leyendo dentro del
        tercer apartado ya está en el tercer encabezado.  Dar eso por hecho y
        decir «¡eso es!» sería felicitar a alguien por no haber hecho nada, así
        que se dice lo que pasa y se pasa al siguiente.

        Devuelve si ha quedado alguno por hacer.
        """
        while self.actual < len(self.ejercicios):
            ejercicio = self.ejercicios[self.actual]
            self.desde = self._mirar()
            try:
                cumplido = ejercicio.hecho(self.desde, self.desde)
            except Exception:                            # pragma: no cover
                cumplido = False
            if not cumplido:
                return True
            log.info("Práctica: %s ya estaba cumplido", ejercicio.clave)
            self._anunciar(_("Este ya lo tenías hecho: %s Pasamos al siguiente.")
                           % ejercicio.enunciado)
            self.saltados += 1
            self.actual += 1
        return False

    def _decir_enunciado(self) -> None:
        """Repite lo que hay que hacer, con su pista."""
        if self.actual >= len(self.ejercicios):
            return
        ejercicio = self.ejercicios[self.actual]
        self._anunciar("%s %s" % (ejercicio.enunciado, ejercicio.pista))

    def _comprobar(self) -> None:
        """Mira si el ejercicio ya está hecho."""
        if self.actual >= len(self.ejercicios):
            return
        ejercicio = self.ejercicios[self.actual]
        try:
            if not ejercicio.hecho(self.desde, self._mirar()):
                return
        except Exception as error:                       # pragma: no cover
            log.info("El ejercicio %s no se ha podido comprobar: %s",
                     ejercicio.clave, error)
            return
        self.reloj.Stop()
        self.hechos += 1
        log.info("Práctica: ejercicio %s hecho", ejercicio.clave)
        self._anunciar(_("¡Eso es!"))
        self.actual += 1
        self._pintar()

    def _saltar(self) -> None:
        """Deja este ejercicio y pasa al siguiente."""
        if self.actual >= len(self.ejercicios):
            return
        self.reloj.Stop()
        self.saltados += 1
        self.actual += 1
        self._pintar()

    # -- cierre ---------------------------------------------------------------

    def _terminar(self) -> None:
        """Dice cómo ha ido y cierra."""
        self.reloj.Stop()
        self.configuracion.establecer("practica_hecha", True)
        self.configuracion.guardar()
        wx.MessageBox(practica.resumen(self.hechos, self.saltados,
                                       len(self.ejercicios)),
                      _("Practicar"), wx.OK | wx.ICON_INFORMATION, self)
        self.Destroy()

    def _al_terminar(self, evento) -> None:
        del evento
        if self.actual >= len(self.ejercicios) or not self.ejercicios:
            self.reloj.Stop()
            self.Destroy()
            return
        self._terminar()

    def _al_cerrar_ventana(self, evento) -> None:
        del evento
        self.reloj.Stop()
        self.Destroy()

    def _al_pulsar(self, evento: wx.KeyEvent) -> None:
        if evento.GetKeyCode() == wx.WXK_ESCAPE:
            self._al_terminar(None)
            return
        evento.Skip()
