# -*- coding: utf-8 -*-
"""Ventana de perfiles de lectura.

Una lista de perfiles con lo que caracteriza a cada uno, y cuatro botones:
poner, guardar los ajustes de ahora con un nombre, cambiarle el nombre y
borrar.  Con la lista vacía se ofrecen tres de ejemplo, que es la única forma
de que se entienda para qué sirve esto sin leerse el manual.
"""

from __future__ import annotations

import wx

from interfaz.accesible import etiquetar
from interfaz.anuncios import Voz
from interfaz.dialogos import ayuda_opcion
from interfaz.listas import ListaAccesible
from nucleo import perfiles
from nucleo.idioma import _
from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

MARGEN = 8


class DialogoPerfiles(wx.Dialog):
    """Gestiona los perfiles de lectura.

    :param padre: Ventana principal, que es quien sabe aplicar los ajustes.
    """

    def __init__(self, padre: wx.Window) -> None:
        super().__init__(padre, title=_("Perfiles de lectura"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.ventana = padre
        self.configuracion = padre.configuracion
        self.voz = Voz(self)

        contenedor = wx.BoxSizer(wx.VERTICAL)
        contenedor.Add(wx.StaticText(self, label=_(
            "Un perfil guarda de una vez la voz, la velocidad, los sonidos y cómo se\n"
            "presenta el texto. Sirve para leer una novela y un manual técnico sin tener\n"
            "que cambiar ocho ajustes a mano cada vez.")), 0, wx.ALL, MARGEN)

        self.lista = ListaAccesible(self, self.configuracion,
                                    style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        etiquetar(self.lista, _("Perfiles de lectura"))
        self.lista.InsertColumn(0, _("Perfil"), width=180)
        self.lista.InsertColumn(1, _("Qué tiene"), width=420)
        self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._al_poner)
        contenedor.Add(self.lista, 1, wx.EXPAND | wx.ALL, MARGEN)

        botones = wx.BoxSizer(wx.HORIZONTAL)
        for etiqueta, manejador in (
                (_("&Poner este perfil"), self._al_poner),
                (_("&Guardar los ajustes de ahora..."), self._al_guardar),
                (_("Cambiar el &nombre..."), self._al_renombrar),
                (_("&Eliminar"), self._al_eliminar)):
            boton = wx.Button(self, label=etiqueta)
            boton.Bind(wx.EVT_BUTTON, manejador)
            botones.Add(boton, 0, wx.ALL, 4)
        contenedor.Add(botones, 0, wx.ALL, 4)

        self.boton_ejemplos = wx.Button(self, label=_("Crear tres perfiles de &ejemplo"))
        self.boton_ejemplos.Bind(wx.EVT_BUTTON, self._al_crear_ejemplos)
        contenedor.Add(self.boton_ejemplos, 0, wx.LEFT | wx.BOTTOM, MARGEN)

        cierre = wx.StdDialogButtonSizer()
        cerrar = wx.Button(self, wx.ID_OK, _("&Cerrar"))
        cerrar.SetDefault()
        cierre.AddButton(cerrar)
        cierre.Realize()
        contenedor.Add(cierre, 0, wx.EXPAND | wx.ALL, MARGEN)

        self.SetSizerAndFit(contenedor)
        self.SetSize((720, 460))
        self.CenterOnParent()
        ayuda_opcion.enganchar(self)
        self._refrescar()
        self.lista.SetFocus()

    # -- estado ----------------------------------------------------------------

    def _refrescar(self, seleccionar: str = "") -> None:
        """Vuelve a pintar la lista."""
        todos = perfiles.leer(self.configuracion)
        puesto = perfiles.activo(self.configuracion)
        self.lista.DeleteAllItems()
        self._nombres = perfiles.nombres(self.configuracion)
        for numero, nombre in enumerate(self._nombres):
            rotulo = nombre + (_(" (puesto ahora)") if nombre == puesto else "")
            self.lista.InsertItem(numero, rotulo)
            self.lista.SetItem(numero, 1, perfiles.descripcion(todos[nombre]))
        self.boton_ejemplos.Enable(not self._nombres)
        if self._nombres:
            indice = (self._nombres.index(seleccionar)
                      if seleccionar in self._nombres else 0)
            self.lista.Select(indice)
            self.lista.Focus(indice)

    def _seleccionado(self) -> str:
        """Nombre del perfil enfocado, o cadena vacía."""
        indice = self.lista.GetFirstSelected()
        return self._nombres[indice] if 0 <= indice < len(self._nombres) else ""

    # -- acciones ----------------------------------------------------------------

    def _al_poner(self, evento) -> None:
        """Aplica el perfil enfocado."""
        nombre = self._seleccionado()
        if not nombre:
            self.voz.decir(_("No hay ningún perfil seleccionado."))
            return
        hay_que_reabrir = perfiles.aplicar(self.configuracion, nombre)
        self.configuracion.guardar()
        self.ventana.aplicar_preferencias(reabrir=bool(hay_que_reabrir))
        log.info("Perfil de lectura aplicado: %s", nombre)
        self._refrescar(nombre)
        self.voz.decir(_("Perfil «%s» puesto.") % nombre)

    def _al_guardar(self, evento) -> None:
        """Guarda los ajustes actuales con un nombre."""
        propuesto = self._seleccionado() or _("Mi perfil")
        with wx.TextEntryDialog(self, _("Nombre del perfil:"),
                                _("Guardar los ajustes de ahora"), propuesto) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                return
            nombre = dialogo.GetValue().strip()
        if not nombre:
            self.voz.decir(_("Hay que ponerle un nombre."))
            return
        if nombre in perfiles.nombres(self.configuracion):
            respuesta = wx.MessageBox(
                _("Ya hay un perfil que se llama «%s». ¿Lo sustituyo por los ajustes "
                  "de ahora?") % nombre,
                _("Perfiles de lectura"), wx.YES_NO | wx.ICON_QUESTION, self)
            if respuesta != wx.YES:
                return
        if not perfiles.guardar(self.configuracion, nombre):
            wx.MessageBox(_("No caben más de %d perfiles.") % perfiles.MAXIMO,
                          _("Perfiles de lectura"), wx.OK | wx.ICON_INFORMATION, self)
            return
        self.configuracion.guardar()
        self._refrescar(nombre)
        self.voz.decir(_("Guardado el perfil «%s».") % nombre)

    def _al_renombrar(self, evento) -> None:
        """Le cambia el nombre al perfil enfocado."""
        nombre = self._seleccionado()
        if not nombre:
            self.voz.decir(_("No hay ningún perfil seleccionado."))
            return
        with wx.TextEntryDialog(self, _("Nombre nuevo:"),
                                _("Cambiar el nombre"), nombre) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                return
            nuevo = dialogo.GetValue().strip()
        if not nuevo or nuevo == nombre:
            return
        valores = perfiles.leer(self.configuracion).get(nombre, {})
        perfiles.borrar(self.configuracion, nombre)
        perfiles.guardar(self.configuracion, nuevo, valores)
        self.configuracion.guardar()
        self._refrescar(nuevo)
        self.voz.decir(_("Ahora se llama «%s».") % nuevo)

    def _al_eliminar(self, evento) -> None:
        """Quita el perfil enfocado, preguntando antes."""
        nombre = self._seleccionado()
        if not nombre:
            self.voz.decir(_("No hay ningún perfil seleccionado."))
            return
        respuesta = wx.MessageBox(
            _("¿Eliminar el perfil «%s»?\n\nLos ajustes que tengas puestos ahora no se "
              "tocan: solo se borra el perfil guardado.") % nombre,
            _("Perfiles de lectura"), wx.YES_NO | wx.ICON_QUESTION, self)
        if respuesta != wx.YES:
            return
        perfiles.borrar(self.configuracion, nombre)
        self.configuracion.guardar()
        self._refrescar()
        self.voz.decir(_("Perfil eliminado."))

    def _al_crear_ejemplos(self, evento) -> None:
        """Crea tres perfiles de ejemplo para empezar.

        Se parte de los ajustes que hay puestos y solo se cambia lo que
        caracteriza a cada perfil: así los ejemplos respetan la voz que la
        persona ya tiene elegida en vez de imponer una.
        """
        base = perfiles.capturar(self.configuracion)
        for nombre, cambios in perfiles.sugeridos().items():
            perfiles.guardar(self.configuracion, nombre, dict(base, **cambios))
        # Ninguno queda puesto: crearlos no es elegirlos.
        self.configuracion.establecer(perfiles.AJUSTE_ACTIVO, "")
        self.configuracion.guardar()
        self._refrescar()
        self.voz.decir(_("Creados tres perfiles de ejemplo. Elige uno y pulsa "
                         "«Poner este perfil»."))
