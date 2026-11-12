# -*- coding: utf-8 -*-
"""Exportar el documento a audio.

Primero se pregunta lo poco que hay que decidir —un archivo por capítulo o uno
solo, con qué voz y a qué velocidad, y dónde se deja— y después se genera con
progreso y se puede cancelar.

La generación tarda: un libro de trescientas páginas son varios minutos, aunque
la voz no suene por los altavoces y trabaje a toda máquina.  Por eso va en otro
hilo, con la ventana de progreso de siempre diciendo por qué capítulo va, y por
eso se puede parar en cualquier momento sin dejar archivos a medias.
"""

from __future__ import annotations

import threading
from pathlib import Path

import wx

from interfaz.accesible import etiquetar, fila_etiquetada
from interfaz.dialogos import ayuda_opcion
from interfaz.dialogos import progreso as dialogos_progreso
from nucleo import audio_libro, pronunciacion, rutas
from nucleo.idioma import _, _n
from nucleo.registro import obtener_registro, registrar_excepcion
from nucleo.voz import RAPIDEZ_NORMAL, Sintetizador

log = obtener_registro(__name__)

MARGEN = 8


class DialogoExportarAudio(wx.Dialog):
    """Pregunta cómo se quiere el audio y lo genera.

    :param padre: Ventana principal, de donde salen documento y preferencias.
    """

    def __init__(self, padre: wx.Window) -> None:
        super().__init__(padre, title=_("Exportar a audio"),
                         style=wx.DEFAULT_DIALOG_STYLE)
        self.ventana = padre
        self.configuracion = padre.configuracion
        self.documento = padre.documento
        self._cancelado = False
        self._progreso = None
        self.generados: list[Path] = []

        contenedor = wx.BoxSizer(wx.VERTICAL)

        capitulos = audio_libro.capitulos_de(self.documento)
        self._capitulos = capitulos
        resumen = _("El documento tiene %(capitulos)d capítulos y %(caracteres)s "
                    "caracteres.") % {
            "capitulos": len(capitulos),
            "caracteres": "{:,}".format(len(self.documento.texto)).replace(",", ".")}
        contenedor.Add(wx.StaticText(self, label=resumen), 0, wx.ALL, MARGEN)

        # El tercer reparto es el que faltaba: un archivo, pero con las marcas
        # de capítulo dentro.  Es lo que hace que en el reproductor del móvil o
        # del coche se pueda saltar de capítulo en capítulo, en lugar de tener
        # diez horas seguidas por las que solo se avanza a ciegas.
        self._reparto = [
            (True, _n("Un archivo por capítulo (%d archivo)",
                      "Un archivo por capítulo (%d archivos)",
                      len(capitulos)) % len(capitulos)),
            ("marcado", _n("Un solo archivo con marcas de capítulo (%d marca)",
                           "Un solo archivo con marcas de capítulo (%d marcas)",
                           len(capitulos)) % len(capitulos)),
            (False, _("Un solo archivo, sin marcas")),
        ]
        self.reparto = fila_etiquetada(
            self, contenedor, _("&Cómo se reparte:"),
            lambda p: wx.Choice(p, choices=[rotulo for _clave, rotulo in self._reparto]),
            margen=MARGEN, horizontal=True, proporcion=1)
        self.reparto.SetSelection(0 if len(capitulos) > 1 else 2)
        if len(capitulos) < 2:
            # Sin capítulos que marcar, la opción no dice nada; se quita de
            # en medio en vez de dejarla para que alguien la elija en balde.
            self.reparto.Delete(1)
            self._reparto.pop(1)
            self.reparto.SetSelection(1)
        contenedor.Add(wx.StaticText(self, label=_(
            "Las marcas de capítulo las entienden los reproductores de audiolibros y de\n"
            "pódcast, VLC y foobar2000. En MP3 van dentro del archivo; en WAV se deja al\n"
            "lado una hoja de pistas .cue, porque un WAV no puede llevarlas dentro."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, MARGEN)

        self._formatos = [(audio_libro.MP3, _("MP3 (ocupa poco, lo abre cualquier cosa)")),
                          (audio_libro.WAV, _("WAV sin comprimir (ocupa muchísimo más)"))]
        self.formato = fila_etiquetada(
            self, contenedor, _("&Formato:"),
            lambda p: wx.Choice(p, choices=[rotulo for _clave, rotulo in self._formatos]),
            margen=MARGEN, horizontal=True, proporcion=1)
        self.formato.SetSelection(0)
        if not audio_libro.hay_codificador():
            self.formato.SetSelection(1)
            self.formato.Disable()
            contenedor.Add(wx.StaticText(self, label=_(
                "No se ha podido cargar el compresor de MP3, así que se dejará en WAV."
            )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, MARGEN)

        sintetizador = Sintetizador()
        voces = sintetizador.voces()
        self.voz = fila_etiquetada(
            self, contenedor, _("&Voz:"),
            lambda p: wx.Choice(p, choices=voces or [_("(no hay ninguna voz instalada)")]),
            margen=MARGEN, horizontal=True, proporcion=1)
        preferida = str(self.configuracion.obtener("voz_nombre", "") or "")
        self.voz.SetSelection(voces.index(preferida) if preferida in voces else 0)
        if not voces:
            self.voz.Disable()

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
        boton_carpeta = wx.Button(self, label=_("Ele&gir carpeta..."))
        boton_carpeta.Bind(wx.EVT_BUTTON, self._al_elegir_carpeta)
        contenedor.Add(boton_carpeta, 0, wx.LEFT | wx.BOTTOM, MARGEN)

        aviso = wx.StaticText(self, label=_(
            "Se lee con la misma voz y el mismo diccionario de pronunciación que dentro\n"
            "del programa. Un libro largo puede tardar varios minutos; se puede cancelar."))
        contenedor.Add(aviso, 0, wx.ALL, MARGEN)

        botones = wx.BoxSizer(wx.HORIZONTAL)
        self.boton_generar = wx.Button(self, label=_("&Generar"))
        self.boton_generar.Bind(wx.EVT_BUTTON, self._al_generar)
        self.boton_generar.SetDefault()
        botones.Add(self.boton_generar, 0, wx.ALL, 5)
        botones.Add(wx.Button(self, wx.ID_CANCEL, _("Cancela&r")), 0, wx.ALL, 5)
        contenedor.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 4)

        self.SetSizerAndFit(contenedor)
        self.CenterOnParent()
        ayuda_opcion.enganchar(self)
        self.reparto.SetFocus()

    # -- destino --------------------------------------------------------------

    def _carpeta_inicial(self) -> str:
        """Carpeta que se propone: la última usada, o la del documento."""
        guardada = str(self.configuracion.obtener("audio_carpeta", "") or "")
        if guardada and Path(guardada).is_dir():
            return guardada
        ruta = getattr(self.ventana, "ruta_actual", "")
        if ruta:
            padre = Path(ruta).parent
            if padre.is_dir():
                return str(padre)
        return str(rutas.directorio_datos())

    def _al_elegir_carpeta(self, evento) -> None:
        """Abre el selector de carpetas."""
        with wx.DirDialog(self, _("Carpeta donde dejar el audio"),
                          defaultPath=self.carpeta.GetValue()) as dialogo:
            if dialogo.ShowModal() == wx.ID_OK:
                self.carpeta.SetValue(dialogo.GetPath())

    # -- generación -----------------------------------------------------------

    def _al_generar(self, evento) -> None:
        """Comprueba lo elegido y arranca la generación."""
        destino = Path(self.carpeta.GetValue().strip())
        if not destino.parent.exists():
            wx.MessageBox(_("Esa carpeta no existe. Elige otra."),
                          _("Exportar a audio"), wx.OK | wx.ICON_INFORMATION, self)
            self.carpeta.SetFocus()
            return
        try:
            destino.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            wx.MessageBox(_("No se puede escribir en esa carpeta:\n\n%s") % error,
                          _("Exportar a audio"), wx.OK | wx.ICON_ERROR, self)
            return

        reparto = self._reparto[max(0, self.reparto.GetSelection())][0]
        # «marcado» genera los capítulos por separado y los pega al final: es la
        # única forma de saber cuánto dura cada uno, que es lo que hace falta
        # para escribir las marcas.
        un_solo_archivo = reparto == "marcado"
        capitulos = (self._capitulos if reparto in (True, "marcado")
                     else audio_libro.documento_entero(self.documento))
        formato = self._formatos[max(0, self.formato.GetSelection())][0]
        voz = self.voz.GetStringSelection() if self.voz.IsEnabled() else ""
        velocidad = self.velocidad.GetValue()
        volumen = int(self.configuracion.obtener("voz_volumen", 100))
        tabla = pronunciacion.tabla_para(self.configuracion,
                                         getattr(self.ventana, "ruta_actual", ""))
        self.configuracion.establecer("audio_carpeta", str(destino))

        self._cancelado = False
        self.Hide()
        self._progreso = dialogos_progreso.DialogoProgreso(
            self.ventana, _("Exportar a audio"),
            _("Generando el audio del documento..."),
            al_cancelar=self._al_cancelar)
        self._progreso.mostrar_tras(0)

        documento = self.documento

        def trabajo() -> None:
            try:
                generados = audio_libro.exportar(
                    documento, destino, capitulos, formato=formato, voz=voz,
                    velocidad=velocidad, volumen=volumen, tabla=tabla,
                    progreso=lambda hecho, total, detalle: self._avanzar(hecho, total, detalle),
                    cancelado=lambda: self._cancelado,
                    un_solo_archivo=un_solo_archivo,
                    titulo=documento.metadatos.titulo,
                    autor=documento.metadatos.autor)
                wx.CallAfter(self._terminado, generados, "")
            except Exception as error:
                registrar_excepcion(log, "Error al exportar a audio", error)
                wx.CallAfter(self._terminado, [], str(error))

        threading.Thread(target=trabajo, name="audio_libro", daemon=True).start()

    def _avanzar(self, hecho: int, total: int, detalle: str) -> None:
        """Lleva el avance a la ventana de progreso."""
        if self._progreso is not None:
            self._progreso.avanzar(hecho, total, detalle)

    def _al_cancelar(self) -> None:
        """El usuario ha pulsado Escape o Cancelar en la ventana de progreso."""
        self._cancelado = True

    def _terminado(self, generados: list[Path], error: str) -> None:
        """Cierra el progreso y cuenta cómo ha ido."""
        if self._progreso is not None:
            self._progreso.cerrar()
            self._progreso = None
        self.generados = generados

        if error:
            wx.MessageBox(_("No se ha podido exportar a audio:\n\n%s") % error,
                          _("Exportar a audio"), wx.OK | wx.ICON_ERROR, self.ventana)
        elif self._cancelado:
            hechos = len(generados)
            wx.MessageBox(
                _n("Exportación cancelada. Se había generado %d archivo, que se conserva.",
                   "Exportación cancelada. Se habían generado %d archivos, que se "
                   "conservan.", hechos) % hechos,
                _("Exportar a audio"), wx.OK | wx.ICON_INFORMATION, self.ventana)
        elif not generados:
            wx.MessageBox(_("No se ha generado ningún archivo."),
                          _("Exportar a audio"), wx.OK | wx.ICON_INFORMATION, self.ventana)
        else:
            megas = audio_libro.tamano_total(generados) / (1024 * 1024)
            respuesta = wx.MessageBox(
                _("Listo: %(archivos)d archivos, %(megas).1f MB en total.\n\n"
                  "¿Quieres abrir la carpeta?") % {"archivos": len(generados),
                                                   "megas": megas},
                _("Exportar a audio"), wx.YES_NO | wx.ICON_INFORMATION, self.ventana)
            if respuesta == wx.YES:
                rutas.abrir_en_explorador(generados[0].parent)
        try:
            self.EndModal(wx.ID_OK)
        except Exception:
            pass
