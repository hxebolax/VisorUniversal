# -*- coding: utf-8 -*-
"""Corregir lo que el programa ha deducido mal de un PDF.

En un PDF sin etiquetar no hay más remedio que **deducir** qué es cada cosa
midiendo cómo está escrita: un título por su tamaño de letra, un pie de página
por repetirse en todas las páginas.  Acierta casi siempre y se equivoca de vez
en cuando, y hasta ahora, cuando se equivocaba, el error volvía cada vez que se
abría el documento.

Esta ventana permite decir la verdad una vez: «esto no era un título», «esto sí
lo era y es de nivel dos», «este renglón sobra».  La corrección se guarda atada
al contenido del archivo (:mod:`nucleo.correcciones`) y se vuelve a aplicar
siempre que se abra ese mismo documento, aunque cambie de carpeta o de nombre.

Se trabaja **sobre la línea del cursor**, que es lo que la persona acaba de
oír.  Es la única referencia que no hay que explicar: quien nota que un título
se ha leído como un párrafo está justo encima de él.
"""

from __future__ import annotations

import wx

from interfaz.dialogos import ayuda_opcion
from interfaz.accesible import etiquetar, fila_etiquetada
from nucleo.idioma import _
from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

MARGEN = 8

#: Qué se puede decir que era el elemento, con el nombre que se anuncia.  El
#: orden es el de lo más frecuente a lo menos: la equivocación que más se nota
#: es un título que no lo era, y la segunda un título que no se detectó.
OPCIONES = (
    ("parrafo", _("Un &párrafo normal, no un título")),
    ("encabezado", _("Un &título")),
    ("artefacto", _("&Nada: es un encabezado o un pie de página que sobra")),
    ("cita", _("Una &cita")),
)


class DialogoCorregir(wx.Dialog):
    """Dice qué es de verdad el elemento en el que está el cursor.

    :param padre: Ventana principal.
    :param texto: Lo que dice la línea.
    :param pagina: Página en la que está, empezando en 1.
    :param correcciones: Correcciones del documento abierto.
    """

    def __init__(self, padre: wx.Window, texto: str, pagina: int, correcciones) -> None:
        super().__init__(padre, title=_("Corregir este elemento"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.correcciones = correcciones
        self.texto = texto
        self.pagina = pagina
        contenedor = wx.BoxSizer(wx.VERTICAL)

        contenedor.Add(wx.StaticText(self, label=_(
            "El programa ha deducido lo que es cada cosa midiendo cómo está escrita\n"
            "la página. Si se ha equivocado con esta, dilo aquí: se guardará y se\n"
            "aplicará cada vez que abras este documento.")), 0, wx.ALL, MARGEN)

        muestra = fila_etiquetada(
            self, contenedor, _("&Elemento (página %d):") % pagina,
            lambda p: wx.TextCtrl(p, value=texto, size=(460, 70),
                                  style=wx.TE_MULTILINE | wx.TE_READONLY))
        muestra.SetInsertionPoint(0)

        self.tipo = fila_etiquetada(
            self, contenedor, _("&Esto en realidad es:"),
            lambda p: wx.RadioBox(p, choices=[etiqueta for _clave, etiqueta in OPCIONES],
                                  majorDimension=1, style=wx.RA_SPECIFY_COLS))
        self.tipo.Bind(wx.EVT_RADIOBOX, self._al_cambiar_tipo)

        self.nivel = fila_etiquetada(
            self, contenedor, _("&Nivel del título:"),
            lambda p: wx.Choice(p, choices=[_("Nivel %d") % n for n in range(1, 7)]),
            horizontal=True)
        self.nivel.SetSelection(1)

        guardada = correcciones.elementos.get("%d %s" % (pagina, _clave_de(texto)))
        if guardada:
            for indice, (clave, _etiqueta) in enumerate(OPCIONES):
                if clave == guardada.get("tipo"):
                    self.tipo.SetSelection(indice)
            if guardada.get("nivel"):
                self.nivel.SetSelection(max(0, min(5, int(guardada["nivel"]) - 1)))
        self._al_cambiar_tipo(None)

        self.quitar = wx.CheckBox(self, label=_("&Olvidar la corrección de este elemento"))
        etiquetar(self.quitar, _("Olvidar la corrección de este elemento"))
        self.quitar.Enable(bool(guardada))
        contenedor.Add(self.quitar, 0, wx.ALL, MARGEN)

        botones = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        if botones is not None:
            contenedor.Add(botones, 0, wx.EXPAND | wx.ALL, MARGEN)
        self.SetSizerAndFit(contenedor)
        self.CentreOnParent()
        self.tipo.SetFocus()
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    def _al_cambiar_tipo(self, _evento) -> None:
        """El nivel solo tiene sentido si lo que se dice es que era un título."""
        self.nivel.Enable(OPCIONES[self.tipo.GetSelection()][0] == "encabezado")

    def aplicar(self) -> bool:
        """Guarda lo elegido.  Devuelve si algo ha cambiado de verdad."""
        if self.quitar.IsChecked():
            return self.correcciones.olvidar(self.pagina, self.texto)
        clave = OPCIONES[self.tipo.GetSelection()][0]
        nivel = self.nivel.GetSelection() + 1
        return self.correcciones.marcar(self.pagina, self.texto, clave, nivel)


def _clave_de(texto: str) -> str:
    """Igual que la del sidecar, para poder buscar la corrección ya guardada."""
    from nucleo.correcciones import clave_de

    return clave_de(texto)
