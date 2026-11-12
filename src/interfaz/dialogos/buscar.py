# -*- coding: utf-8 -*-
"""Cuadro de diálogo de búsqueda.

Ofrece las mismas opciones que cualquier buscador conocido —distinguir
mayúsculas, palabra completa, expresión regular y búsqueda circular— y
recuerda los términos usados anteriormente en un desplegable editable.

El diálogo **no** es modal: se queda abierto mientras se busca, de modo que
se puedan encadenar varias búsquedas sin volver a abrirlo.  La ventana
principal recibe el resultado a través de la función que se le pasa en
``al_buscar``.
"""

from __future__ import annotations

from typing import Callable

import wx

from interfaz.dialogos import ayuda_opcion
from interfaz.accesible import etiquetar
from nucleo.busqueda import OpcionesBusqueda
from nucleo.idioma import _
from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

MARGEN = 8


class DialogoBuscar(wx.Dialog):
    """Diálogo de búsqueda no modal.

    :param padre: Ventana principal.
    :param configuracion: Preferencias, de donde salen las opciones guardadas
                          y el historial de búsquedas.
    :param al_buscar: Función ``(termino, hacia_adelante, opciones) -> bool``
                      que realiza la búsqueda y devuelve si hubo éxito.
    """

    def __init__(self, padre: wx.Window, configuracion,
                 al_buscar: Callable[[str, bool, OpcionesBusqueda], bool]) -> None:
        super().__init__(padre, title=_("Buscar"))
        self.configuracion = configuracion
        self._al_buscar = al_buscar

        contenedor = wx.BoxSizer(wx.VERTICAL)
        contenedor.Add(wx.StaticText(self, label=_("&Buscar:")), 0, wx.ALL, MARGEN)
        self.campo = etiquetar(wx.ComboBox(
            self, choices=list(configuracion.obtener("buscar_historial", [])),
            style=wx.CB_DROPDOWN, size=(380, -1),
        ), _("Texto que se busca"))
        contenedor.Add(self.campo, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, MARGEN)

        opciones = wx.StaticBoxSizer(wx.VERTICAL, self, _("Opciones"))
        self.mayusculas = wx.CheckBox(opciones.GetStaticBox(), label=_("Distinguir &mayúsculas y minúsculas"))
        self.palabra = wx.CheckBox(opciones.GetStaticBox(), label=_("Solo &palabras completas"))
        self.regular = wx.CheckBox(opciones.GetStaticBox(), label=_("&Expresión regular"))
        self.circular = wx.CheckBox(opciones.GetStaticBox(), label=_("&Continuar desde el principio al llegar al final"))
        self.mayusculas.SetValue(bool(configuracion.obtener("buscar_mayusculas")))
        self.palabra.SetValue(bool(configuracion.obtener("buscar_palabra_completa")))
        self.regular.SetValue(bool(configuracion.obtener("buscar_expresion_regular")))
        self.circular.SetValue(True)
        for casilla in (self.mayusculas, self.palabra, self.regular, self.circular):
            opciones.Add(casilla, 0, wx.ALL, 4)
        contenedor.Add(opciones, 0, wx.EXPAND | wx.ALL, MARGEN)

        fila = wx.BoxSizer(wx.HORIZONTAL)
        self.boton_siguiente = wx.Button(self, label=_("Buscar &siguiente"))
        self.boton_anterior = wx.Button(self, label=_("Buscar &anterior"))
        self.boton_contar = wx.Button(self, label=_("Con&tar"))
        cerrar = wx.Button(self, wx.ID_CANCEL, _("&Cerrar"))
        self.boton_siguiente.SetDefault()
        for boton in (self.boton_siguiente, self.boton_anterior, self.boton_contar, cerrar):
            fila.Add(boton, 0, wx.RIGHT, 4)
        contenedor.Add(fila, 0, wx.ALL, MARGEN)

        self.estado = wx.StaticText(self, label="")
        contenedor.Add(self.estado, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, MARGEN)

        self.SetSizerAndFit(contenedor)

        self.boton_siguiente.Bind(wx.EVT_BUTTON, lambda evento: self.buscar(True))
        self.boton_anterior.Bind(wx.EVT_BUTTON, lambda evento: self.buscar(False))
        self.boton_contar.Bind(wx.EVT_BUTTON, self._al_contar)
        self.Bind(wx.EVT_CLOSE, self._al_cerrar)
        self.campo.Bind(wx.EVT_TEXT_ENTER, lambda evento: self.buscar(True))
        self.campo.SetFocus()
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    # -- utilidades ----------------------------------------------------------

    def opciones(self) -> OpcionesBusqueda:
        """Recoge las opciones marcadas en el diálogo."""
        return OpcionesBusqueda(
            distinguir_mayusculas=self.mayusculas.GetValue(),
            palabra_completa=self.palabra.GetValue(),
            expresion_regular=self.regular.GetValue(),
            circular=self.circular.GetValue(),
        )

    def termino(self) -> str:
        """Texto escrito en el campo de búsqueda."""
        return self.campo.GetValue()

    def buscar(self, hacia_adelante: bool) -> None:
        """Lanza la búsqueda en la dirección indicada."""
        texto = self.termino().strip()
        if not texto:
            self.mostrar_estado(_("Escribe qué quieres buscar."))
            self.campo.SetFocus()
            return
        self._guardar_opciones(texto)
        self._al_buscar(texto, hacia_adelante, self.opciones())

    def _al_contar(self, evento) -> None:
        """Cuenta las apariciones del término en todo el libro."""
        ventana = wx.GetTopLevelParent(self)
        contador = getattr(ventana, "contar_apariciones", None)
        if contador is None:
            return
        texto = self.termino().strip()
        if not texto:
            return
        total = contador(texto, self.opciones())
        if total == 1:
            self.mostrar_estado(_("Se ha encontrado 1 aparición."))
        else:
            self.mostrar_estado(_("Se han encontrado %d apariciones.") % total)

    def _guardar_opciones(self, texto: str) -> None:
        """Recuerda las opciones y el término usados."""
        self.configuracion.establecer("buscar_mayusculas", self.mayusculas.GetValue())
        self.configuracion.establecer("buscar_palabra_completa", self.palabra.GetValue())
        self.configuracion.establecer("buscar_expresion_regular", self.regular.GetValue())
        self.configuracion.anadir_busqueda(texto)
        if self.campo.FindString(texto) == wx.NOT_FOUND:
            self.campo.Insert(texto, 0)

    def mostrar_estado(self, mensaje: str) -> None:
        """Muestra el resultado de la búsqueda dentro del propio diálogo."""
        self.estado.SetLabel(mensaje)

    def _al_cerrar(self, evento) -> None:
        """Oculta el diálogo en lugar de destruirlo, para poder reutilizarlo.

        Y avisa a la ventana de que ya se puede seguir leyendo: si se estaba
        escuchando el libro, la voz se calló al abrir esto y ahora sigue —desde
        el resultado si se encontró algo—.
        """
        self.Hide()
        seguir = getattr(self.GetParent(), "reanudar_lectura_tras_buscar", None)
        if callable(seguir):
            seguir()
