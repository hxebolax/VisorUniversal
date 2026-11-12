# -*- coding: utf-8 -*-
"""Ventana para escribir el documento como un libro DAISY 3.

Un libro DAISY no es un archivo: es **una carpeta** con el texto, la navegación
y, si se quiere, la grabación.  Por eso aquí se pide una carpeta y no un nombre
de archivo, y por eso la ventana avisa de lo que va a dejar dentro.

La decisión que hay que tomar es una sola, y la ventana la pone delante sin
adornos: **texto solo o texto y voz**.  El texto solo sale en un segundo y se
lee con la voz del propio reproductor.  Con voz tarda lo que tarde en grabarse
—que en un libro largo son minutos, no segundos— y a cambio da un libro hablado
que se puede seguir a la vez en la línea braille, frase a frase, que es la razón
de ser de DAISY.
"""

from __future__ import annotations

import threading
from pathlib import Path

import wx

from interfaz.dialogos import ayuda_opcion
from interfaz.accesible import fila_etiquetada
from interfaz.dialogos import progreso as dialogos_progreso
from nucleo import audio_libro, daisy_exportar, pronunciacion
from nucleo.idioma import _, _n
from nucleo.registro import obtener_registro, registrar_excepcion
from nucleo.voz import RAPIDEZ_NORMAL, Sintetizador

log = obtener_registro(__name__)

MARGEN = 8


class DialogoExportarDaisy(wx.Dialog):
    """Pregunta dónde y cómo, y escribe el libro DAISY."""

    def __init__(self, padre: wx.Window) -> None:
        super().__init__(padre, title=_("Exportar a libro DAISY"),
                         style=wx.DEFAULT_DIALOG_STYLE)
        self.ventana = padre
        self.configuracion = padre.configuracion
        self.documento = padre.documento
        self._cancelado = False
        self._progreso = None

        contenedor = wx.BoxSizer(wx.VERTICAL)
        capitulos = daisy_exportar.analizar(self.documento)
        contenedor.Add(wx.StaticText(self, label=_(
            "El documento saldrá como un libro DAISY 3 de %d capítulos, con su índice y "
            "sus páginas.") % len(capitulos)), 0, wx.ALL, MARGEN)

        self._modos = [
            (False, _("Solo el texto (rápido; lo lee la voz del reproductor)")),
            (True, _("Texto y voz sincronizados frase a frase (tarda y ocupa)")),
        ]
        self.modo = fila_etiquetada(
            self, contenedor, _("&Qué se escribe:"),
            lambda p: wx.Choice(p, choices=[rotulo for _clave, rotulo in self._modos]),
            margen=MARGEN, horizontal=True, proporcion=1)
        self.modo.SetSelection(0)

        sintetizador = Sintetizador()
        voces = sintetizador.voces()
        self.voz = fila_etiquetada(
            self, contenedor, _("&Voz para la grabación:"),
            lambda p: wx.Choice(p, choices=voces or [_("(no hay ninguna voz instalada)")]),
            margen=MARGEN, horizontal=True, proporcion=1)
        preferida = str(self.configuracion.obtener("voz_nombre", "") or "")
        self.voz.SetSelection(voces.index(preferida) if preferida in voces else 0)
        if not voces:
            self.voz.Disable()
            self.modo.SetSelection(0)

        self.velocidad = fila_etiquetada(
            self, contenedor, _("Ve&locidad, de 0 a 100 (%d es la normal):") % RAPIDEZ_NORMAL,
            lambda p: wx.SpinCtrl(p, min=0, max=100, initial=int(
                self.configuracion.obtener("voz_rapidez", RAPIDEZ_NORMAL))),
            margen=MARGEN, horizontal=True)
        self.velocidad.SetIncrement(5)

        self.carpeta = fila_etiquetada(
            self, contenedor, _("Ca&rpeta de destino:"),
            lambda p: wx.TextCtrl(p, value=self._carpeta_inicial()),
            margen=MARGEN, horizontal=True, proporcion=1)
        boton = wx.Button(self, label=_("Ele&gir carpeta..."))
        boton.Bind(wx.EVT_BUTTON, self._al_elegir_carpeta)
        contenedor.Add(boton, 0, wx.LEFT | wx.BOTTOM, MARGEN)

        contenedor.Add(wx.StaticText(self, label=_(
            "Se escriben ahí «libro.xml» con el texto, «libro.ncx» con la navegación y\n"
            "«libro.opf» con los datos del libro. Con voz se añade un archivo de sonido y\n"
            "otro de sincronización por capítulo.")), 0, wx.ALL, MARGEN)

        pie = wx.StdDialogButtonSizer()
        aceptar = wx.Button(self, wx.ID_OK, _("&Exportar"))
        aceptar.SetDefault()
        pie.AddButton(aceptar)
        pie.AddButton(wx.Button(self, wx.ID_CANCEL, _("&Cancelar")))
        pie.Realize()
        contenedor.Add(pie, 0, wx.EXPAND | wx.ALL, MARGEN)
        self.SetSizerAndFit(contenedor)

        self.Bind(wx.EVT_BUTTON, self._al_exportar, id=wx.ID_OK)
        self.modo.SetFocus()
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    # -- ayudas --------------------------------------------------------------

    def _carpeta_inicial(self) -> str:
        """Una carpeta de partida: la del último audio, o la del documento."""
        guardada = str(self.configuracion.obtener("daisy_carpeta", "") or "")
        if guardada:
            return guardada
        ruta = str(getattr(self.ventana, "ruta_actual", "") or "")
        return str(Path(ruta).parent) if ruta else str(Path.home())

    def _al_elegir_carpeta(self, evento) -> None:
        """Abre el selector de carpetas."""
        del evento
        with wx.DirDialog(self, _("Carpeta donde dejar el libro DAISY"),
                          defaultPath=self.carpeta.GetValue()) as dialogo:
            if dialogo.ShowModal() == wx.ID_OK:
                self.carpeta.SetValue(dialogo.GetPath())

    # -- trabajo -------------------------------------------------------------

    def _al_exportar(self, evento) -> None:
        """Comprueba lo elegido y lanza la escritura en otro hilo."""
        del evento
        destino = Path(self.carpeta.GetValue().strip() or ".")
        # El libro va en su propia subcarpeta: DAISY espera una carpeta por
        # libro, y dejarlo suelto entre otros archivos hace que el reproductor
        # no sepa dónde empieza.
        nombre = audio_libro.nombre_seguro(
            self.documento.metadatos.titulo
            or Path(getattr(self.ventana, "ruta_actual", "") or "libro").stem) or "libro"
        destino = destino / nombre
        try:
            destino.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            wx.MessageBox(_("No se puede escribir en esa carpeta:\n\n%s") % error,
                          _("Exportar a DAISY"), wx.OK | wx.ICON_ERROR, self)
            return

        con_audio = self._modos[max(0, self.modo.GetSelection())][0]
        self.configuracion.establecer("daisy_carpeta", str(destino.parent))
        self.configuracion.guardar()

        grabar = None
        if con_audio:
            tabla = pronunciacion.tabla_para(self.configuracion,
                                             getattr(self.ventana, "ruta_actual", ""))
            try:
                grabar = audio_libro.grabador_de_frases(
                    self.voz.GetStringSelection() if self.voz.IsEnabled() else "",
                    self.velocidad.GetValue(),
                    int(self.configuracion.obtener("voz_volumen", 100)),
                    tabla, cancelado=lambda: self._cancelado)
            except Exception as error:
                wx.MessageBox(_("No se ha podido usar la voz del sistema para grabar:"
                                "\n\n%s") % error,
                              _("Exportar a DAISY"), wx.OK | wx.ICON_ERROR, self)
                return

        self._cancelado = False
        self.Hide()
        self._progreso = dialogos_progreso.DialogoProgreso(
            self.ventana, _("Exportar a DAISY"),
            _("Escribiendo el libro DAISY..."), al_cancelar=self._al_cancelar)
        self._progreso.mostrar_tras(0)

        documento = self.documento

        def trabajo() -> None:
            try:
                escritos = daisy_exportar.exportar(
                    documento, destino, grabar=grabar,
                    progreso=lambda hecho, total, detalle: self._avanzar(
                        hecho, total, detalle),
                    cancelado=lambda: self._cancelado)
                wx.CallAfter(self._terminado, escritos, destino, "")
            except Exception as error:
                registrar_excepcion(log, "Error al exportar a DAISY", error)
                wx.CallAfter(self._terminado, [], destino, str(error))
            finally:
                soltar = getattr(grabar, "soltar", None)
                if soltar is not None:
                    soltar()

        threading.Thread(target=trabajo, name="daisy_exportar", daemon=True).start()

    def _avanzar(self, hecho: int, total: int, detalle: str) -> None:
        """Lleva el avance a la ventana de progreso."""
        if self._progreso is not None:
            self._progreso.avanzar(hecho, total, detalle)

    def _al_cancelar(self) -> None:
        """Marca que hay que parar; el hilo lo mira entre capítulos."""
        self._cancelado = True

    def _terminado(self, escritos, destino: Path, error: str) -> None:
        """Recoge el trabajo y cuenta cómo ha ido."""
        if self._progreso is not None:
            self._progreso.cerrar()
            self._progreso = None
        if error:
            wx.MessageBox(_("No se ha podido exportar a DAISY:\n\n%s") % error,
                          _("Exportar a DAISY"), wx.OK | wx.ICON_ERROR, self.ventana)
        elif self._cancelado:
            self.ventana.anunciar(_("Exportación a DAISY cancelada."))
        else:
            self.ventana.anunciar(
                _n("Libro DAISY escrito en %(carpeta)s: %(cuantos)d archivo.",
                   "Libro DAISY escrito en %(carpeta)s: %(cuantos)d archivos.",
                   len(escritos))
                % {"carpeta": destino.name, "cuantos": len(escritos)})
        if self:
            self.EndModal(wx.ID_OK)
