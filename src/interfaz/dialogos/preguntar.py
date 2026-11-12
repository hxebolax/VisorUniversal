# -*- coding: utf-8 -*-
"""Ventana para preguntarle cosas a la IA sobre el documento.

Resumir el capítulo, saber quién era un personaje, entender un párrafo espeso.
Se elige **qué se pregunta** y **sobre qué trozo**, y la respuesta aparece en un
cuadro que se recorre con las flechas y se lee entera al llegar.

La respuesta anterior no se borra: las preguntas se van encadenando en el mismo
cuadro, con la pregunta delante de cada una, de modo que al final queda una
conversación que se puede releer y copiar de una vez.  Es lo que hace falta
cuando uno pregunta tres cosas seguidas sobre el mismo capítulo.
"""

from __future__ import annotations

import threading

import wx

from interfaz.accesible import etiquetar, fila_etiquetada
from interfaz.anuncios import Voz
from interfaz.dialogos import ayuda_opcion
from nucleo.ia import preguntas as tabla_preguntas
from nucleo.idioma import _
from nucleo.registro import obtener_registro, registrar_excepcion

log = obtener_registro(__name__)

MARGEN = 8


class DialogoPreguntar(wx.Dialog):
    """Pregunta a la IA sobre el documento abierto.

    :param padre: Ventana principal.
    :param servicio: Servicio de IA ya construido.
    :param inicial: Identificador de la pregunta que viene elegida, si se llega
                    aquí desde una orden concreta como «Resumir el capítulo».
    """

    def __init__(self, padre: wx.Window, servicio, inicial: str = "resumen") -> None:
        super().__init__(padre, title=_("Preguntar sobre el documento"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.ventana = padre
        self.servicio = servicio
        self.configuracion = padre.configuracion
        self.documento = padre.documento
        self._trabajando = False
        #: Lo que se lleva hablado, para que las preguntas siguientes
        #: sepan de qué se estaba hablando.
        self.conversacion = None
        self._turno = 0
        self.voz = Voz(self)

        contenedor = wx.BoxSizer(wx.VERTICAL)

        self._claves_pregunta = [clave for clave, _n, _t in tabla_preguntas.PREGUNTAS]
        self.pregunta = fila_etiquetada(
            self, contenedor, _("&Qué quieres saber:"),
            lambda p: wx.Choice(p, choices=[nombre for _c, nombre, _t
                                            in tabla_preguntas.PREGUNTAS]),
            margen=MARGEN, horizontal=True, proporcion=1)
        self.pregunta.SetSelection(self._claves_pregunta.index(inicial)
                                   if inicial in self._claves_pregunta else 0)
        self.pregunta.Bind(wx.EVT_CHOICE, self._al_cambiar_pregunta)

        self.propia = fila_etiquetada(
            self, contenedor, _("&Tu pregunta:"),
            lambda p: wx.TextCtrl(p, style=wx.TE_PROCESS_ENTER),
            margen=MARGEN, horizontal=True, proporcion=1)
        self.propia.Bind(wx.EVT_TEXT_ENTER, lambda evento: self._preguntar())

        self._claves_ambito = [clave for clave, _n in tabla_preguntas.AMBITOS]
        self.ambito = fila_etiquetada(
            self, contenedor, _("&Sobre qué parte:"),
            lambda p: wx.Choice(p, choices=[nombre for _c, nombre
                                            in tabla_preguntas.AMBITOS]),
            margen=MARGEN, horizontal=True, proporcion=1)
        guardado = str(self.configuracion.obtener("ia_ambito", "capitulo"))
        self.ambito.SetSelection(self._claves_ambito.index(guardado)
                                 if guardado in self._claves_ambito else 0)

        self.respuesta = wx.TextCtrl(
            self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP,
            size=(700, 360))
        etiquetar(self.respuesta, _("Respuesta"))
        contenedor.Add(self.respuesta, 1, wx.EXPAND | wx.ALL, MARGEN)

        botones = wx.BoxSizer(wx.HORIZONTAL)
        self.boton_preguntar = wx.Button(self, label=_("&Preguntar"))
        self.boton_preguntar.Bind(wx.EVT_BUTTON, lambda evento: self._preguntar())
        self.boton_preguntar.SetDefault()
        botones.Add(self.boton_preguntar, 0, wx.ALL, 5)
        boton_copiar = wx.Button(self, label=_("&Copiar"))
        boton_copiar.Bind(wx.EVT_BUTTON, self._al_copiar)
        botones.Add(boton_copiar, 0, wx.ALL, 5)
        boton_limpiar = wx.Button(self, label=_("&Vaciar"))
        boton_limpiar.Bind(wx.EVT_BUTTON, self._al_vaciar)
        botones.Add(boton_limpiar, 0, wx.ALL, 5)
        botones.Add(wx.Button(self, wx.ID_CANCEL, _("Ce&rrar")), 0, wx.ALL, 5)
        contenedor.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 4)

        self.SetSizerAndFit(contenedor)
        self.SetSize((820, 620))
        self.CenterOnParent()
        self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar_tecla)
        ayuda_opcion.enganchar(self)
        self._al_cambiar_pregunta(None)
        self.pregunta.SetFocus()

    # -- teclado ---------------------------------------------------------------

    def _asegurar_conversacion(self):
        """La conversación en curso, creándola la primera vez.

        Vive mientras el diálogo esté abierto: al cerrarlo se acaba, que es lo
        que se espera de «preguntar sobre el documento». Para empezar de cero
        sin cerrar está el botón de vaciar.
        """
        if getattr(self, "conversacion", None) is None:
            metadatos = self.documento.metadatos
            self.conversacion = tabla_preguntas.Conversacion(
                getattr(metadatos, "titulo", ""), getattr(metadatos, "autor", ""))
        return self.conversacion

    def _al_pulsar_tecla(self, evento: wx.KeyEvent) -> None:
        """Escape cierra, pero no mientras se está esperando la respuesta."""
        if evento.GetKeyCode() == wx.WXK_ESCAPE and not self._trabajando:
            self.EndModal(wx.ID_CANCEL)
            return
        evento.Skip()

    def _al_cambiar_pregunta(self, evento) -> None:
        """El cuadro de escribir solo se usa con la pregunta libre."""
        libre = self._clave_pregunta() == "libre"
        self.propia.Enable(libre)
        if libre:
            self.propia.SetFocus()

    def _al_copiar(self, evento) -> None:
        """Lleva la conversación entera al portapapeles."""
        texto = self.respuesta.GetValue().strip()
        if not texto:
            self.voz.decir(_("No hay nada que copiar."))
            return
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(texto))
            wx.TheClipboard.Close()
            self.voz.decir(_("Copiado."))

    def _al_vaciar(self, evento) -> None:
        """Empieza de cero: se borra lo escrito y también lo que la IA recordaba."""
        self.respuesta.SetValue("")
        self._olvidar_conversacion()
        self.voz.decir(_("Vaciado. La siguiente pregunta empieza una conversación nueva."))

    # -- la pregunta ------------------------------------------------------------

    def _olvidar_conversacion(self) -> None:
        """Empieza de cero: la próxima pregunta volverá a llevar el documento."""
        if getattr(self, "conversacion", None) is not None:
            self.conversacion.olvidar()

    def _clave_pregunta(self) -> str:
        return self._claves_pregunta[max(0, self.pregunta.GetSelection())]

    def _clave_ambito(self) -> str:
        return self._claves_ambito[max(0, self.ambito.GetSelection())]

    def _preguntar(self) -> None:
        """Arma la petición y la manda en otro hilo."""
        if self._trabajando:
            return
        clave = self._clave_pregunta()
        instruccion = tabla_preguntas.texto_de_pregunta(clave)
        rotulo = tabla_preguntas.nombre_de_pregunta(clave)
        if clave == "libre":
            instruccion = self.propia.GetValue().strip()
            rotulo = instruccion
            if not instruccion:
                self.voz.decir(_("Escribe qué quieres preguntar."))
                self.propia.SetFocus()
                return

        motivo = self.servicio.motivo_no_disponible()
        if motivo:
            wx.MessageBox(motivo, _("Preguntar sobre el documento"),
                          wx.OK | wx.ICON_INFORMATION, self)
            return

        ambito = self._clave_ambito()
        self.configuracion.establecer("ia_ambito", ambito)
        trozo = tabla_preguntas.trozo_para(
            ambito, self.documento, self.ventana.lector.posicion(),
            self.ventana.lector.texto_seleccionado())
        if not trozo.texto.strip():
            self.voz.decir(_("Ahí no hay texto sobre el que preguntar."))
            return

        # El texto del documento solo viaja en la primera pregunta de la
        # conversación: después ya está en lo que se manda, y repetirlo
        # multiplicaría el coste sin añadir nada.
        conversacion = self._asegurar_conversacion()
        seguimiento = not conversacion.vacia
        turnos = conversacion.preparar(instruccion, None if seguimiento else trozo)
        log.info("Pregunta a la IA (%s, %s, %d caracteres, turno %d)",
                 clave, ambito, len(trozo.texto), len(turnos))

        self._trabajando = True
        self._turno += 1
        turno = self._turno
        self.boton_preguntar.Disable()
        if seguimiento:
            self._anadir(_("Pregunta: %s — siguiendo la conversación") % rotulo)
        else:
            self._anadir(_("Pregunta: %(que)s — sobre %(sobre)s") % {
                "que": rotulo, "sobre": trozo.rotulo})
        self._anadir(_("Preguntando..."), decir=True)

        def trabajo() -> None:
            try:
                texto = self.servicio.conversar(turnos)
                wx.CallAfter(self._con_respuesta, turno, texto, "")
            except Exception as error:
                registrar_excepcion(log, "La IA no ha podido responder", error)
                wx.CallAfter(self._con_respuesta, turno, "", str(error))

        threading.Thread(target=trabajo, name="pregunta_ia", daemon=True).start()

    def _con_respuesta(self, turno: int, texto: str, error: str) -> None:
        """Enseña la respuesta o el fallo."""
        self._trabajando = False
        if not self:
            return
        self.boton_preguntar.Enable()
        if turno != self._turno:
            return
        # Se quita el «Preguntando...» y se pone lo que haya llegado.
        contenido = self.respuesta.GetValue()
        marca = _("Preguntando...")
        if contenido.rstrip().endswith(marca):
            contenido = contenido.rstrip()[:-len(marca)].rstrip()
            self.respuesta.SetValue(contenido)
        if error:
            # La pregunta que no ha llegado a contestarse sale de la
            # conversación: si se quedara, todas las siguientes arrastrarían un
            # turno sin respuesta y el modelo respondería peor.
            self._olvidar_turno_fallido()
            self._anadir(_("No se ha podido responder: %s") % error, decir=True)
            return
        if getattr(self, "conversacion", None) is not None:
            self.conversacion.responder(texto.strip())
        self._anadir(texto.strip(), decir=True)
        self.respuesta.SetInsertionPointEnd()

    def _olvidar_turno_fallido(self) -> None:
        """Quita de la conversación la pregunta que no llegó a contestarse."""
        if getattr(self, "conversacion", None) is not None:
            self.conversacion.deshacer_ultima()

    def _anadir(self, texto: str, decir: bool = False) -> None:
        """Añade un bloque al final de la conversación."""
        if not texto:
            return
        anterior = self.respuesta.GetValue()
        separador = "\n\n" if anterior.strip() else ""
        self.respuesta.SetValue(anterior + separador + texto)
        self.respuesta.SetInsertionPointEnd()
        if decir:
            self.voz.decir(texto)
