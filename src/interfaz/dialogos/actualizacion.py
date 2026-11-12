# -*- coding: utf-8 -*-
"""Ventana que ofrece instalar una versión nueva.

Avisa de que hay versión nueva, y si se acepta descarga el paquete con barra de
progreso, comprueba que es el que publica el servidor, lo descomprime y deja
todo listo para que el programa se cierre y vuelva a abrirse ya actualizado.

Todo el trabajo pesado va en otro hilo: descargar decenas de megas dejaría la
ventana congelada —y muda, que es lo grave— si se hiciera en el de la interfaz.
Los avisos vuelven al hilo de la interfaz con ``wx.CallAfter``, que es la única
forma segura de tocar un control de wxPython desde fuera.
"""

from __future__ import annotations

import threading
from pathlib import Path

import wx

from interfaz.dialogos import ayuda_opcion
from interfaz.accesible import etiquetar
from interfaz.anuncios import Voz
from nucleo import actualizaciones, rutas
from nucleo.idioma import _
from nucleo.registro import obtener_registro, registrar_excepcion
from version import VERSION

log = obtener_registro(__name__)

MARGEN = 12


def tamano_legible(cantidad: int) -> str:
    """Convierte un número de bytes en algo que se entienda al oírlo."""
    if cantidad < 1024:
        return _("%d bytes") % cantidad
    if cantidad < 1024 * 1024:
        return _("%.1f KB") % (cantidad / 1024)
    return _("%.1f MB") % (cantidad / (1024 * 1024))


class DialogoActualizacion(wx.Dialog):
    """Pregunta si instalar la versión nueva y, si se acepta, la instala.

    :param padre: Ventana principal, que es quien sabe cerrarse y relanzarse.
    :param version: Versión que anuncia el servidor.
    :param manifiesto: El ``version.json`` completo, del que salen el resumen
                       con el que se comprueba el paquete y las notas de la
                       versión, si el servidor las publica.
    """

    def __init__(self, padre: wx.Window, version: str, manifiesto: dict) -> None:
        super().__init__(padre, title=_("Hay una versión nueva"),
                         style=wx.DEFAULT_DIALOG_STYLE)
        self.ventana = padre
        self.version = version
        self.manifiesto = manifiesto or {}
        self._cancelado = False
        self._trabajando = False
        self.voz = Voz(self)

        contenedor = wx.BoxSizer(wx.VERTICAL)

        notas = str(self.manifiesto.get("notas", "")).strip()
        mensaje = _(
            "Hay una versión nueva del programa.\n\n"
            "Versión nueva: %(nueva)s\n"
            "Versión instalada: %(actual)s") % {"nueva": version, "actual": VERSION}
        if notas:
            mensaje += _("\n\nNovedades: %s") % notas
        mensaje += _("\n\n¿Quieres descargarla e instalarla ahora? "
                     "El programa se cerrará y volverá a abrirse ya actualizado.")

        # Cuadro de solo lectura y no una etiqueta: un texto largo dentro de una
        # etiqueta solo se puede oír de una tirada, mientras que aquí se recorre
        # con las flechas y se puede releer la parte que interese.
        self.texto = wx.TextCtrl(self, value=mensaje,
                                 style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP,
                                 size=(520, 190))
        etiquetar(self.texto, _("Versión nueva disponible"))
        contenedor.Add(self.texto, 1, wx.EXPAND | wx.ALL, MARGEN)

        self.barra = wx.Gauge(self, range=100)
        etiquetar(self.barra, _("Avance de la actualización"))
        self.barra.Hide()
        contenedor.Add(self.barra, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, MARGEN)

        self.detalle = wx.StaticText(self, label="")
        self.detalle.Hide()
        contenedor.Add(self.detalle, 0, wx.ALL, MARGEN)

        botones = wx.BoxSizer(wx.HORIZONTAL)
        self.boton_instalar = wx.Button(self, label=_("&Instalar ahora"))
        self.boton_instalar.Bind(wx.EVT_BUTTON, self._al_instalar)
        self.boton_instalar.SetDefault()
        botones.Add(self.boton_instalar, 0, wx.ALL, 5)
        self.boton_cerrar = wx.Button(self, wx.ID_CANCEL, _("A&hora no"))
        self.boton_cerrar.Bind(wx.EVT_BUTTON, self._al_cerrar_boton)
        botones.Add(self.boton_cerrar, 0, wx.ALL, 5)
        contenedor.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 8)

        self.SetSizerAndFit(contenedor)
        self.CenterOnParent()
        self.Bind(wx.EVT_CLOSE, self._al_cerrar_ventana)
        self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar_tecla)
        self.boton_instalar.SetFocus()
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    # -- cierre --------------------------------------------------------------

    def _al_pulsar_tecla(self, evento: wx.KeyEvent) -> None:
        """Escape cierra, pero no mientras se está instalando."""
        if evento.GetKeyCode() == wx.WXK_ESCAPE:
            if not self._trabajando:
                self.EndModal(wx.ID_CANCEL)
            return
        evento.Skip()

    def _al_cerrar_boton(self, evento) -> None:
        """El segundo botón es «Ahora no» o «Cancelar», según lo que pase."""
        if self._trabajando:
            self._cancelado = True
            self.boton_cerrar.Disable()
            self._poner_estado(_("Cancelando la descarga..."))
        else:
            self.EndModal(wx.ID_CANCEL)

    def _al_cerrar_ventana(self, evento) -> None:
        """No se deja cerrar a medias: quedaría una actualización sin aplicar."""
        if self._trabajando:
            return
        self.EndModal(wx.ID_CANCEL)

    # -- avisos desde el hilo de trabajo --------------------------------------

    def _poner_estado(self, texto: str) -> None:
        """Cambia el texto principal y lo dice."""
        if not self:
            return
        self.texto.SetValue(texto)
        self.voz.decir(texto)

    def _poner_avance(self, porcentaje, detalle: str) -> None:
        """Actualiza la barra y el detalle.

        Con ``porcentaje`` a ``None`` la barra se mueve sola, para cuando el
        servidor no dice cuánto ocupa el paquete y no hay forma de saber
        cuánto queda.
        """
        if not self:
            return
        if not self.barra.IsShown():
            self.barra.Show()
            self.detalle.Show()
            self.Layout()
        if porcentaje is None:
            self.barra.Pulse()
        else:
            self.barra.SetValue(max(0, min(100, int(porcentaje))))
        if detalle:
            self.detalle.SetLabel(detalle)

    # -- instalación ----------------------------------------------------------

    def _al_instalar(self, evento) -> None:
        """Arranca la descarga en otro hilo."""
        if not actualizaciones.se_puede_instalar():
            wx.MessageBox(
                _("La instalación automática solo funciona en la versión compilada del "
                  "programa.\n\nEstás ejecutando desde el código fuente, así que la "
                  "versión nueva hay que traérsela como siempre."),
                _("Solo en la versión instalada"), wx.OK | wx.ICON_INFORMATION, self)
            return
        self._trabajando = True
        self.boton_instalar.Disable()
        self.boton_cerrar.SetLabel(_("&Cancelar"))
        self._poner_estado(_("Descargando la versión %s...") % self.version)
        threading.Thread(target=self._trabajo, daemon=True,
                         name="ActualizacionVisor").start()

    def _trabajo(self) -> None:
        """Descarga, comprueba, descomprime y prepara el reinicio.

        Cualquier fallo se cuenta y se limpian los archivos a medias: es
        preferible quedarse en la versión de siempre que con una instalación
        hecha a trozos.
        """
        base = Path(rutas.directorio_base())
        ruta_zip = base / actualizaciones.NOMBRE_ZIP
        temporal = base / actualizaciones.NOMBRE_TEMP
        try:
            def avance_descarga(leido: int, total: int) -> None:
                if total > 0:
                    porcentaje = int(leido / total * 100)
                    wx.CallAfter(self._poner_avance, porcentaje,
                                 _("Descargando: %(hecho)s de %(total)s (%(por)d%%)") % {
                                     "hecho": tamano_legible(leido),
                                     "total": tamano_legible(total),
                                     "por": porcentaje})
                else:
                    wx.CallAfter(self._poner_avance, None,
                                 _("Descargando: %s") % tamano_legible(leido))

            actualizaciones.descargar(self.version, ruta_zip, progreso=avance_descarga,
                                      cancelado=lambda: self._cancelado,
                                      direcciones=self.manifiesto.get("_paquetes"))

            wx.CallAfter(self._poner_estado, _("Comprobando el paquete descargado..."))
            actualizaciones.comprobar_firma(self.manifiesto)
            actualizaciones.comprobar_paquete(ruta_zip, str(self.manifiesto.get("sha256", "")))

            wx.CallAfter(self._poner_estado, _("Descomprimiendo los archivos..."))

            def avance_descompresion(hechos: int, total: int) -> None:
                porcentaje = int(hechos / total * 100) if total else 0
                wx.CallAfter(self._poner_avance, porcentaje,
                             _("Descomprimiendo: %(hecho)d de %(total)d") % {
                                 "hecho": hechos, "total": total})

            actualizaciones.descomprimir(ruta_zip, temporal, progreso=avance_descompresion)

            wx.CallAfter(self._poner_estado, _("Preparando el reinicio..."))
            guion = actualizaciones.crear_guion(base, temporal, ruta_zip)
            wx.CallAfter(self._confirmar_reinicio, guion)
        except Exception as error:
            registrar_excepcion(log, "No se ha podido instalar la actualización", error)
            self._limpiar(ruta_zip, temporal)
            wx.CallAfter(self._fallo, str(error))

    @staticmethod
    def _limpiar(ruta_zip: Path, temporal: Path) -> None:
        """Borra lo que se haya quedado a medias."""
        import shutil
        try:
            if temporal.exists():
                shutil.rmtree(temporal, ignore_errors=True)
            ruta_zip.unlink(missing_ok=True)
        except OSError:
            pass

    def _fallo(self, mensaje: str) -> None:
        """Cuenta que no se ha podido y deja el diálogo utilizable otra vez."""
        self._trabajando = False
        if not self:
            return
        if self._cancelado:
            self._poner_estado(_("Actualización cancelada. El programa sigue como estaba."))
        else:
            self._poner_estado(_("No se ha podido completar la actualización."))
            wx.MessageBox(_("No se ha podido completar la actualización:\n\n%s") % mensaje,
                          _("Actualización"), wx.OK | wx.ICON_ERROR, self)
        self.boton_instalar.Enable()
        self.boton_cerrar.Enable()
        self.boton_cerrar.SetLabel(_("&Cerrar"))
        self._cancelado = False

    def _confirmar_reinicio(self, guion: Path) -> None:
        """Avisa de que se va a reiniciar y le pasa el testigo a la ventana."""
        if not self:
            return
        self._poner_avance(100, _("Listo para instalar."))
        wx.MessageBox(
            _("La versión %s se ha descargado y comprobado correctamente.\n\n"
              "Al aceptar, el programa se cerrará y volverá a abrirse ya actualizado. "
              "Tus ajustes, marcadores y documentos no se tocan.") % self.version,
            _("Actualización lista"), wx.OK | wx.ICON_INFORMATION, self)
        try:
            self.EndModal(wx.ID_OK)
        except Exception:
            pass
        self.ventana.aplicar_actualizacion(guion)
