# -*- coding: utf-8 -*-
"""Copiar un pasaje con su cita bibliográfica ya hecha.

La ventana enseña tres cosas y deja tocar las tres: el pasaje, el estilo y la
referencia.  Que la referencia **se pueda editar antes de copiarla** no es un
adorno: hay datos que ningún programa puede deducir del archivo.  El caso claro
es el apellido español compuesto —«Gabriel García Márquez» se cita «García
Márquez, Gabriel», y «Juan Carlos Pérez» se cita «Pérez, Juan Carlos», y las dos
cadenas tienen tres palabras y ninguna pista que las distinga—.  El programa
propone lo más probable y quien cita corrige en un segundo, que es infinitamente
más rápido que montar la referencia desde cero.

El estilo elegido se recuerda: quien escribe en APA escribe siempre en APA.
"""

from __future__ import annotations

import wx

from interfaz.dialogos import ayuda_opcion
from interfaz.accesible import etiquetar, fila_etiquetada
from interfaz.anuncios import Voz
from interfaz.ventanas_win32 import suprimir_menu_contextual
from nucleo import citas
from nucleo.idioma import _
from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

MARGEN = 8


class DialogoCitar(wx.Dialog):
    """Enseña el pasaje con su referencia y lo copia al portapapeles.

    :param padre: Ventana principal.
    :param documento: Documento abierto, de donde salen los datos.
    :param pasaje: Texto que se quiere citar.  Puede ir vacío: entonces se
                   copia solo la referencia del documento, que es lo que hace
                   falta para la bibliografía.
    :param posicion: Punto del texto, del que salen la página y el capítulo.
    :param configuracion: Preferencias, donde se recuerda el estilo.
    """

    def __init__(self, padre: wx.Window, documento, pasaje: str, posicion: int,
                 configuracion) -> None:
        super().__init__(padre, title=_("Copiar con la cita"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.configuracion = configuracion
        self.datos = citas.desde_documento(documento, posicion)
        self._voz = Voz(self)

        contenedor = wx.BoxSizer(wx.VERTICAL)

        estilos = citas.nombres()
        self._claves = [clave for clave, _nombre in estilos]
        self.estilo = fila_etiquetada(
            self, contenedor, _("&Estilo de cita:"),
            lambda p: wx.Choice(p, choices=[nombre for _clave, nombre in estilos]),
            margen=MARGEN, horizontal=True, proporcion=1)
        guardado = str(configuracion.obtener("cita_estilo", citas.ESTILOS[0]))
        self.estilo.SetSelection(self._claves.index(guardado)
                                 if guardado in self._claves else 0)

        contenedor.Add(wx.StaticText(self, label=_("&Pasaje que se cita:")), 0,
                       wx.LEFT | wx.RIGHT | wx.TOP, MARGEN)
        self.campo_pasaje = etiquetar(wx.TextCtrl(
            self, value=" ".join((pasaje or "").split()),
            style=wx.TE_MULTILINE | wx.TE_NOHIDESEL, size=(640, 140)),
            _("Pasaje que se cita"))
        contenedor.Add(self.campo_pasaje, 1, wx.EXPAND | wx.ALL, MARGEN)

        contenedor.Add(wx.StaticText(self, label=_("&Referencia (se puede corregir):")), 0,
                       wx.LEFT | wx.RIGHT | wx.TOP, MARGEN)
        self.campo_referencia = etiquetar(wx.TextCtrl(
            self, style=wx.TE_MULTILINE | wx.TE_NOHIDESEL, size=(640, 70)),
            _("Referencia bibliográfica"))
        contenedor.Add(self.campo_referencia, 0, wx.EXPAND | wx.ALL, MARGEN)
        self._sin_menu = [suprimir_menu_contextual(self.campo_pasaje),
                          suprimir_menu_contextual(self.campo_referencia)]

        self.aviso = wx.StaticText(self, label="")
        contenedor.Add(self.aviso, 0, wx.LEFT | wx.RIGHT, MARGEN)

        fila = wx.StdDialogButtonSizer()
        self.boton_copiar = wx.Button(self, wx.ID_OK, _("&Copiar al portapapeles"))
        self.boton_copiar.SetDefault()
        self.boton_solo = wx.Button(self, label=_("Copiar solo la &referencia"))
        fila.AddButton(self.boton_copiar)
        fila.Add(self.boton_solo, 0, wx.LEFT, MARGEN)
        fila.AddButton(wx.Button(self, wx.ID_CANCEL, _("&Cancelar")))
        fila.Realize()
        contenedor.Add(fila, 0, wx.EXPAND | wx.ALL, MARGEN)
        self.SetSizerAndFit(contenedor)

        self.estilo.Bind(wx.EVT_CHOICE, self._al_cambiar_estilo)
        self.boton_copiar.Bind(wx.EVT_BUTTON, self._al_copiar)
        self.boton_solo.Bind(wx.EVT_BUTTON, self._al_copiar_referencia)

        self._rehacer_referencia()
        self.campo_pasaje.SetInsertionPoint(0)
        self.estilo.SetFocus()
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    # -- estado --------------------------------------------------------------

    def _clave(self) -> str:
        """El estilo elegido ahora mismo."""
        indice = max(self.estilo.GetSelection(), 0)
        return self._claves[indice] if indice < len(self._claves) else citas.ESTILOS[0]

    def _rehacer_referencia(self) -> None:
        """Vuelve a escribir la referencia con el estilo elegido.

        Lo que el usuario hubiera corregido a mano se pierde al cambiar de
        estilo, y tiene que ser así: la corrección va con la puntuación de un
        estilo concreto y no se puede trasladar a otro.
        """
        self.campo_referencia.SetValue(citas.referencia(self.datos, self._clave()))
        faltan = citas.lo_que_falta(self.datos)
        if faltan:
            self.aviso.SetLabel(
                _("El documento no dice %s. Complétalo aquí antes de copiar si lo necesitas.")
                % ", ".join(faltan))
        else:
            self.aviso.SetLabel(_("El documento trae todos los datos de la cita."))

    def _al_cambiar_estilo(self, evento) -> None:
        """Rehace la referencia al elegir otro estilo."""
        del evento
        self._rehacer_referencia()

    # -- copiar --------------------------------------------------------------

    def _copiar(self, texto: str, aviso: str) -> None:
        """Deja el texto en el portapapeles y lo dice."""
        if not texto.strip():
            return
        if not wx.TheClipboard.Open():
            log.warning("No se ha podido abrir el portapapeles")
            return
        try:
            wx.TheClipboard.SetData(wx.TextDataObject(texto))
        finally:
            wx.TheClipboard.Close()
        self.configuracion.establecer("cita_estilo", self._clave())
        self.configuracion.guardar()
        self._voz.decir(aviso)

    def _al_copiar(self, evento) -> None:
        """Copia el pasaje entrecomillado con su referencia debajo."""
        del evento
        pasaje = " ".join(self.campo_pasaje.GetValue().split())
        referencia = self.campo_referencia.GetValue().strip()
        if pasaje:
            texto = "«%s»\n\n%s" % (pasaje, referencia)
        else:
            texto = referencia
        self._copiar(texto, _("Copiado con la cita."))
        self.EndModal(wx.ID_OK)

    def _al_copiar_referencia(self, evento) -> None:
        """Copia solo la referencia, que es lo que va en la bibliografía."""
        del evento
        self._copiar(self.campo_referencia.GetValue().strip(),
                     _("Referencia copiada."))
        self.EndModal(wx.ID_OK)
