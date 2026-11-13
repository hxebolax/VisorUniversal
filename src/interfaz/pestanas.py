# -*- coding: utf-8 -*-
"""Los documentos abiertos a la vez, con o sin pestañas a la vista.

Quien estudia o compara no lee un documento: lee tres. Tener que cerrar uno
para mirar otro —y perder por el camino por dónde iba— es lo que convierte esa
tarea en un suplicio.  De ahí las pestañas.

Pero son **opcionales a propósito**.  Un lector que abre una novela cada tarde
no quiere una barra de pestañas ni una zona más por la que pasar con F6, y
obligarle a ella sería empeorarle el programa para arreglarle un problema que
no tiene.  Así que este módulo presenta la misma colección de dos maneras:

* con las pestañas a la vista, en un ``wx.Notebook``, que es un control nativo
  y que por eso el lector de pantalla anuncia como lo que es («pestaña 2 de 4»)
  y recorre con las flechas sin que haya que programar nada;
* sin ellas, en un ``wx.Simplebook``, que es el mismo contenedor sin lengüetas:
  un solo documento y ni una tecla ni un anuncio de más.

Los dos son ``wx.BookCtrlBase`` y se manejan igual, así que el resto del
programa no distingue en cuál está.

Cada página es un panel de lectura completo, con su documento, su posición y su
historial de saltos (:class:`interfaz.sesion.Sesion`).  Volver a una pestaña es
encontrarla como se dejó, sin recargar ni recolocar nada: es la diferencia
entre unas pestañas de verdad y un menú de documentos recientes.
"""

from __future__ import annotations

from typing import Callable

import wx

from nucleo.idioma import _
from nucleo.registro import obtener_registro

from .sesion import Sesion

log = obtener_registro(__name__)


class Pestanas(wx.Panel):
    """Contenedor de las sesiones abiertas.

    :param padre: Ventana que lo contiene.
    :param con_pestanas: Si se enseñan las lengüetas.
    :param crear_panel: Función ``(padre) -> PanelLectura`` que fabrica el panel
                        de lectura de una sesión nueva.  Se le pasa desde fuera
                        porque el panel necesita la configuración, los sonidos y
                        el anunciador de la ventana, y este módulo no tiene por
                        qué saber nada de eso.
    :param al_cambiar: Se llama cuando el usuario cambia de pestaña.
    :param al_salir: Se llama **antes** de dejar una pestaña, con ella todavía
                     delante.  Es el momento de guardar por dónde iba: hacerlo
                     después guardaría la posición de la pestaña equivocada.
    """

    def __init__(self, padre: wx.Window, con_pestanas: bool,
                 crear_panel: Callable[[wx.Window], wx.Window],
                 al_cambiar: Callable[[], None] | None = None,
                 al_salir: Callable[[], None] | None = None) -> None:
        super().__init__(padre)
        self._crear_panel = crear_panel
        self._al_cambiar = al_cambiar
        self._al_salir = al_salir
        self._con_pestanas = bool(con_pestanas)
        self.sesiones: list[Sesion] = []
        self._contenedor = wx.BoxSizer(wx.VERTICAL)
        self.libro = self._crear_libro()
        self._contenedor.Add(self.libro, 1, wx.EXPAND)
        self.SetSizer(self._contenedor)

    # -- construcción --------------------------------------------------------

    def _crear_libro(self) -> wx.BookCtrlBase:
        """Crea el contenedor de páginas que toque y engancha su evento."""
        if self._con_pestanas:
            libro = wx.Notebook(self, style=wx.NB_TOP)
        else:
            libro = wx.Simplebook(self)
        # Los dos avisan igual al cambiar de página.  Sin lengüetas también hay
        # que enterarse: se cambia de documento con Control+Tabulador, y la
        # ventana tiene que ponerse al día (y abrir el documento reservado de
        # esa página, si lo tiene).
        libro.Bind(wx.EVT_BOOKCTRL_PAGE_CHANGED, self._al_cambiar_pagina)
        libro.Bind(wx.EVT_BOOKCTRL_PAGE_CHANGING, self._al_dejar_pagina)
        libro.SetName(_("Documentos abiertos"))
        return libro

    def _al_cambiar_pagina(self, evento) -> None:
        """Avisa a la ventana de que la pestaña activa es otra."""
        evento.Skip()
        if self._al_cambiar is not None:
            # Se aplaza porque el evento llega **antes** de que wx haya movido
            # el foco: si la ventana recargara el estado aquí, el foco acabaría
            # en el panel que se está dejando.
            wx.CallAfter(self._al_cambiar)

    def _al_dejar_pagina(self, evento) -> None:
        """Avisa de que se está saliendo de la pestaña, con ella aún delante."""
        evento.Skip()
        if self._al_salir is not None:
            self._al_salir()

    @property
    def con_pestanas(self) -> bool:
        """Indica si las lengüetas están a la vista."""
        return self._con_pestanas

    def cambiar_modo(self, con_pestanas: bool) -> bool:
        """Enseña u oculta las lengüetas sin cerrar nada.

        Los paneles de lectura no se recrean: se **cambian de padre** al
        contenedor nuevo.  Recrearlos obligaría a volver a analizar los
        documentos abiertos y a perder la posición de cada uno, que es
        exactamente lo que las pestañas están para no perder.

        :return: ``True`` si se ha cambiado algo.
        """
        if bool(con_pestanas) == self._con_pestanas:
            return False
        activa = max(self.libro.GetSelection(), 0)
        antiguo = self.libro
        self._con_pestanas = bool(con_pestanas)
        nuevo = self._crear_libro()
        for sesion in self.sesiones:
            sesion.panel.Reparent(nuevo)
            nuevo.AddPage(sesion.panel, sesion.rotulo_corto())
        self._contenedor.Replace(antiguo, nuevo)
        self.libro = nuevo
        antiguo.Destroy()
        if 0 <= activa < nuevo.GetPageCount():
            nuevo.SetSelection(activa)
        self.Layout()
        return True

    # -- sesiones ------------------------------------------------------------

    @property
    def actual(self) -> Sesion | None:
        """Sesión de la pestaña activa."""
        indice = self.indice_actual
        return self.sesiones[indice] if 0 <= indice < len(self.sesiones) else None

    @property
    def indice_actual(self) -> int:
        """Número de la pestaña activa, empezando en cero."""
        return self.libro.GetSelection() if self.libro.GetPageCount() else -1

    def __len__(self) -> int:
        return len(self.sesiones)

    def nueva(self, seleccionar: bool = True) -> Sesion:
        """Abre una pestaña vacía con su panel de lectura."""
        panel = self._crear_panel(self.libro)
        sesion = Sesion(panel)
        self.sesiones.append(sesion)
        self.libro.AddPage(panel, sesion.rotulo_corto(), select=seleccionar)
        return sesion

    def cerrar(self, indice: int) -> bool:
        """Cierra una pestaña.  Devuelve si se ha podido.

        La última no se cierra nunca: el programa siempre tiene un panel de
        lectura, aunque esté vacío, porque es donde se enseña la pantalla de
        bienvenida y donde vuelve el foco al cerrar un documento.
        """
        if not 0 <= indice < len(self.sesiones) or len(self.sesiones) <= 1:
            return False
        self.sesiones.pop(indice)
        self.libro.DeletePage(indice)      # destruye también el panel
        if self.libro.GetPageCount():
            self.libro.SetSelection(min(indice, self.libro.GetPageCount() - 1))
        return True

    def seleccionar(self, indice: int) -> bool:
        """Cambia a una pestaña por su número."""
        if not 0 <= indice < len(self.sesiones) or indice == self.indice_actual:
            return False
        self.libro.SetSelection(indice)
        return True

    def girar(self, adelante: bool) -> bool:
        """Pasa a la pestaña siguiente o a la anterior, dando la vuelta al final."""
        total = len(self.sesiones)
        if total <= 1:
            return False
        paso = 1 if adelante else -1
        return self.seleccionar((self.indice_actual + paso) % total)

    def refrescar_rotulo(self, sesion: Sesion | None = None) -> None:
        """Vuelve a escribir el rótulo de una pestaña (o de todas)."""
        if not self._con_pestanas:
            return
        objetivo = self.sesiones if sesion is None else [sesion]
        for una in objetivo:
            try:
                indice = self.sesiones.index(una)
            except ValueError:
                continue
            if indice < self.libro.GetPageCount():
                self.libro.SetPageText(indice, una.rotulo_corto())

    # -- foco ----------------------------------------------------------------

    def enfocar_lenguetas(self) -> bool:
        """Lleva el foco a la fila de lengüetas, si está a la vista.

        Con el foco ahí, el lector de pantalla anuncia «pestaña 2 de 4» y las
        flechas cambian de documento, que es como funcionan las pestañas en
        cualquier otro programa y por tanto lo que se espera aquí.
        """
        if not self._con_pestanas or self.libro.GetPageCount() < 1:
            return False
        self.libro.SetFocus()
        return True

    def enfocar_documento(self) -> bool:
        """Lleva el foco al texto de la pestaña activa."""
        sesion = self.actual
        if sesion is None:
            return False
        sesion.panel.texto.SetFocus()
        return True

    def rotulos(self) -> list[str]:
        """Títulos completos de las pestañas, para el menú y el cambio rápido."""
        return [sesion.titulo() for sesion in self.sesiones]
