# -*- coding: utf-8 -*-
"""Objeto de aplicación de wxPython.

Se encarga de crear la ventana principal, conectar el registro de wxWidgets y
abrir el libro que se haya indicado en la línea de órdenes (que es lo que
ocurre al asociar la extensión ``.epub`` con el programa).
"""

from __future__ import annotations

import wx

from interfaz.ventana import VentanaPrincipal
from nucleo import instancia
from nucleo.registro import conectar_registro_wx, obtener_registro
from version import NOMBRE, NOMBRE_ARCHIVO

log = obtener_registro(__name__)


class Aplicacion(wx.App):
    """Aplicación del programa.

    :param configuracion: Preferencias ya cargadas.
    :param version: Versión del programa.
    :param archivo_inicial: Libro que hay que abrir al arrancar, si lo hay.
    """

    def __init__(self, configuracion, version: str, archivo_inicial: str | None = None) -> None:
        self.configuracion = configuracion
        self.version = version
        self.archivo_inicial = archivo_inicial
        self.ventana: VentanaPrincipal | None = None
        super().__init__(redirect=False)

    def OnInit(self) -> bool:  # noqa: N802 (nombre impuesto por wxPython)
        """Prepara la aplicación.  wxPython lo llama automáticamente."""
        conectar_registro_wx()
        self.SetAppName(NOMBRE)
        # Fijar el idioma español hace dos cosas: traduce los textos propios de
        # wxWidgets (botones de los diálogos del sistema, mensajes de error) y,
        # sobre todo, permite que reconozca los nombres españoles de las teclas
        # («Inicio», «Izquierda»...) al interpretar los atajos de los menús.
        # El objeto debe conservarse mientras viva la aplicación.
        self._idioma = wx.Locale(wx.LANGUAGE_SPANISH)
        if not self._idioma.IsOk():
            log.warning("No se ha podido fijar el idioma español en wxWidgets")
        else:
            log.debug("Idioma de wxWidgets: %s", self._idioma.GetCanonicalName())
        # Una sola copia del programa a la vez.  Si ya hay otra en marcha, se
        # le deja el encargo del libro que se quería abrir, se trae su ventana
        # al frente y esta copia termina sin llegar a crear ninguna ventana.
        # El comprobador se guarda como atributo porque debe seguir vivo
        # mientras dure el programa: al destruirse deja de reservar el nombre.
        self._comprobador = wx.SingleInstanceChecker(
            "%s-%s" % (NOMBRE_ARCHIVO, wx.GetUserId()))
        if self._comprobador.IsAnotherRunning():
            log.info("El programa ya estaba abierto; se le pasa el libro y esta copia termina")
            instancia.dejar_encargo(self.archivo_inicial)
            if not instancia.traer_al_frente():
                log.warning("No se ha podido traer al frente la ventana que ya estaba abierta")
            return False

        # Necesario para que se puedan mostrar imágenes JPEG, PNG y GIF de los libros.
        wx.InitAllImageHandlers()

        self.ventana = VentanaPrincipal(self.configuracion, self.version)
        self.SetTopWindow(self.ventana)
        self.ventana.Show()
        log.info("Ventana principal mostrada")

        # Se hace después de mostrar la ventana para que el aviso de
        # «Abriendo...» se vea desde el primer momento.
        if self.archivo_inicial:
            # Con la sesión pedida, se recupera **y** se abre el libro nuevo:
            # quien ha pedido que le devuelvan sus documentos no deja de
            # quererlos por abrir uno más desde el explorador.  Sin ella, solo
            # el libro, que es lo que se pidió.
            wx.CallAfter(self.ventana.abrir_con_la_sesion, self.archivo_inicial)
        else:
            wx.CallAfter(self.ventana.restaurar_documentos_abiertos)
        return True

    def OnExit(self) -> int:  # noqa: N802 (nombre impuesto por wxPython)
        """Se ejecuta al terminar la aplicación."""
        log.info("Aplicación finalizada")
        return 0
