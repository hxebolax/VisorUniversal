# -*- coding: utf-8 -*-
"""Diálogos de ayuda: lista de atajos e información del programa.

La lista de atajos se construye a partir de :mod:`interfaz.atajos`, que es la
misma fuente que usa la aplicación para interpretar las teclas.  De ese modo
la ayuda nunca puede quedar desfasada respecto al comportamiento real.
"""

from __future__ import annotations

import wx

from interfaz import atajos
from interfaz.dialogos import ayuda_opcion
from interfaz.accesible import etiquetar
from interfaz.ventanas_win32 import suprimir_menu_contextual
from nucleo import rutas
from nucleo.idioma import _
import version as version_programa
from version import NOMBRE

MARGEN = 8


class DialogoAtajos(wx.Dialog):
    """Muestra todos los atajos de teclado agrupados por categorías.

    Se presenta en un control de texto de solo lectura, y no en una tabla,
    porque así el usuario puede leerlo con las órdenes de lectura continua de
    su lector de pantalla y buscar dentro con las teclas del propio control.
    """

    def __init__(self, padre: wx.Window) -> None:
        super().__init__(padre, title=_("Atajos de teclado"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        contenedor = wx.BoxSizer(wx.VERTICAL)
        contenedor.Add(wx.StaticText(self, label=_("&Atajos disponibles:")), 0, wx.ALL, MARGEN)
        campo = etiquetar(wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_NOHIDESEL,
                                      size=(620, 480)), _("Lista de atajos de teclado"))
        self._sin_menu = [suprimir_menu_contextual(campo)]
        campo.SetValue(self._texto())
        contenedor.Add(campo, 1, wx.EXPAND | wx.ALL, MARGEN)

        fila = wx.StdDialogButtonSizer()
        cerrar = wx.Button(self, wx.ID_OK, _("&Cerrar"))
        cerrar.SetDefault()
        fila.AddButton(cerrar)
        fila.Realize()
        contenedor.Add(fila, 0, wx.EXPAND | wx.ALL, MARGEN)
        self.SetSizerAndFit(contenedor)
        campo.SetInsertionPoint(0)
        campo.SetFocus()
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    @staticmethod
    def _texto() -> str:
        """Redacta la lista completa de atajos."""
        lineas: list[str] = []
        for titulo, entradas in atajos.resumen_para_ayuda():
            lineas.append(titulo.upper())
            lineas.append("-" * len(titulo))
            for tecla, descripcion in entradas:
                lineas.append("%-24s %s" % (tecla, descripcion))
            lineas.append("")
        return "\n".join(lineas)


class DialogoAcercaDe(wx.Dialog):
    """Información sobre el programa y sus carpetas."""

    def __init__(self, padre: wx.Window, version: str) -> None:
        super().__init__(padre, title=_("Acerca de %s") % NOMBRE)
        contenedor = wx.BoxSizer(wx.VERTICAL)
        texto = (
            _("%s, versión %s\n"
            "\n"
            "Autor: %s\n"
            "%s\n"
            "Licencia: %s\n"
            "\n"
            "Visor de documentos pensado para usarse con el teclado y con lectores\n"
            "de pantalla. Convierte el documento entero en texto y permite recorrerlo\n"
            "por encabezados, enlaces, imágenes, tablas, listas y más, con un sonido\n"
            "distinto para cada tipo de elemento. Lo lee en voz alta, reproduce las\n"
            "grabaciones de los libros DAISY y describe sus imágenes con inteligencia\n"
            "artificial.\n"
            "\n"
            "Formatos admitidos: EPUB, PDF (con OCR de las páginas escaneadas), Word,\n"
            "LibreOffice, DAISY 2.02 y 3, FictionBook, RTF, HTML, Markdown y texto.\n"
            "\n"
            "Carpeta del programa: %s\n"
            "Carpeta de datos: %s\n"
            "\n"
            "Todo lo que genera el programa (ajustes, registros, caché y sonidos)\n"
            "se guarda en la carpeta de datos, de modo que puedes llevártelo todo\n"
            "copiando simplemente la carpeta del programa.\n"
            "\n"
            "Si el programa te resulta útil, en «Ayuda → Invítame a un café si te\n"
            "gusta mi trabajo» tienes la página de donaciones.")
        ) % (NOMBRE, version, version_programa.AUTOR, version_programa.COPYRIGHT,
             version_programa.LICENCIA, rutas.directorio_base(), rutas.directorio_datos())

        campo = etiquetar(wx.TextCtrl(self, value=texto,
                                      style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_NOHIDESEL,
                                      size=(560, 340)), _("Información del programa"))
        contenedor.Add(campo, 1, wx.EXPAND | wx.ALL, MARGEN)

        fila = wx.StdDialogButtonSizer()
        self.boton_cafe = wx.Button(self, label=_("&Invítame a un café"))
        cerrar = wx.Button(self, wx.ID_OK, _("&Cerrar"))
        cerrar.SetDefault()
        fila.Add(self.boton_cafe, 0, wx.RIGHT, MARGEN)
        fila.AddButton(cerrar)
        fila.Realize()
        contenedor.Add(fila, 0, wx.EXPAND | wx.ALL, MARGEN)
        self.SetSizerAndFit(contenedor)
        self.boton_cafe.Bind(wx.EVT_BUTTON, self._al_invitar_cafe)
        campo.SetInsertionPoint(0)
        campo.SetFocus()
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    def _al_invitar_cafe(self, evento) -> None:
        """Abre en el navegador la página de donaciones del autor."""
        wx.LaunchDefaultBrowser(version_programa.URL_DONACIONES)
