# -*- coding: utf-8 -*-
"""Idiomas del reconocimiento óptico: cuáles hay y cómo añadir más.

Tesseract reconoce el texto con un archivo de entrenamiento por idioma.  Sin el
del idioma correcto, un documento en catalán o en gallego se lee como si fuera
español y sale plagado de erratas; con él, sale bien.

El Tesseract que trae el programa viene con unos pocos —los de aquí— y desde
esta ventana se pueden **añadir los que hagan falta**, que se descargan del
repositorio oficial del proyecto Tesseract.  Cada uno es un archivo suelto de
uno a quince megas, así que quitarlos y ponerlos no tiene ninguna consecuencia.

Hay dos calidades y merece la pena entender la diferencia antes de elegir:

* **Rápida**: uno o dos megas por idioma, y reconoce bien un documento normal.
  Es la de partida.
* **Precisa**: bastante más grande y notablemente más lenta, pero acierta más
  en escaneados difíciles o con letra pequeña.  Vale la pena para un libro
  entero que se va a leer de verdad.

Aquí también se elige **con qué idiomas se lee**.  Se pueden marcar varios a la
vez, y sale a cuenta: un documento en catalán suele llevar nombres y citas en
español, y darle los dos mejora el resultado sin coste apreciable.
"""

from __future__ import annotations

import wx

from interfaz.accesible import etiquetar
from interfaz.anuncios import Voz
from interfaz.dialogos import ayuda_opcion
from interfaz.dialogos.progreso import DialogoProgreso
from interfaz.listas import ListaCasillas
from nucleo import tesseract
from nucleo.idioma import _, _n
from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

MARGEN = 8


class DialogoIdiomasOCR(wx.Dialog):
    """Ventana para elegir, añadir y quitar idiomas del reconocimiento.

    :param padre: Ventana desde la que se abre.
    :param configuracion: Preferencias, donde se guardan los idiomas elegidos.
    """

    def __init__(self, padre: wx.Window, configuracion) -> None:
        super().__init__(padre, title=_("Idiomas del reconocimiento"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.configuracion = configuracion
        self._voz = Voz(self)
        self._instalados: list[str] = []
        self._descargables: list[str] = []

        contenedor = wx.BoxSizer(wx.VERTICAL)
        self.cabecera = wx.StaticText(self, label="")
        contenedor.Add(self.cabecera, 0, wx.ALL, MARGEN)

        contenedor.Add(wx.StaticText(self, label=_(
            "&Idiomas instalados. Marca con cuáles quieres que se lea:")), 0,
            wx.LEFT | wx.RIGHT | wx.TOP, MARGEN)
        self.lista_puestos = etiquetar(ListaCasillas(
            self, size=(430, 190)), _("Idiomas instalados"))
        contenedor.Add(self.lista_puestos, 1, wx.EXPAND | wx.ALL, MARGEN)
        self.aviso = wx.StaticText(self, label="")
        contenedor.Add(self.aviso, 0, wx.LEFT | wx.RIGHT, MARGEN)
        self.lista_puestos.Bind(wx.EVT_CHECKLISTBOX,
                                lambda evento: (evento.Skip(), self._avisar_de_cuantos()))

        fila = wx.BoxSizer(wx.HORIZONTAL)
        self.boton_quitar = wx.Button(self, label=_("&Quitar los marcados"))
        self.boton_quitar.Bind(wx.EVT_BUTTON, self._al_quitar)
        fila.Add(self.boton_quitar, 0, wx.RIGHT, 6)
        contenedor.Add(fila, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, MARGEN)

        contenedor.Add(wx.StaticText(self, label=_(
            "&Idiomas que se pueden añadir. Marca los que quieras y pulsa «Añadir»:")), 0,
            wx.LEFT | wx.RIGHT | wx.TOP, MARGEN)
        self.lista_nuevos = etiquetar(ListaCasillas(
            self, size=(430, 190)), _("Idiomas disponibles"))
        contenedor.Add(self.lista_nuevos, 1, wx.EXPAND | wx.ALL, MARGEN)

        self.precisa = wx.CheckBox(self, label=_(
            "Descargar la versión &precisa (más grande y lenta, acierta más)"))
        contenedor.Add(self.precisa, 0, wx.LEFT | wx.RIGHT, MARGEN)

        fila_nuevos = wx.BoxSizer(wx.HORIZONTAL)
        self.boton_anadir = wx.Button(self, label=_("&Añadir los marcados"))
        self.boton_anadir.Bind(wx.EVT_BUTTON, self._al_anadir)
        fila_nuevos.Add(self.boton_anadir, 0, wx.RIGHT, 6)
        contenedor.Add(fila_nuevos, 0, wx.ALL, MARGEN)

        pie = wx.StdDialogButtonSizer()
        aceptar = wx.Button(self, wx.ID_OK, _("&Aceptar"))
        aceptar.SetDefault()
        pie.AddButton(aceptar)
        pie.AddButton(wx.Button(self, wx.ID_CANCEL, _("&Cancelar")))
        pie.Realize()
        contenedor.Add(pie, 0, wx.EXPAND | wx.ALL, MARGEN)
        self.SetSizerAndFit(contenedor)
        self.CentreOnParent()

        self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)
        ayuda_opcion.enganchar(self)
        self._recargar()
        self.lista_puestos.SetFocus()

    # -- carga ---------------------------------------------------------------

    def _recargar(self) -> None:
        """Rehace las dos listas con lo que hay en el disco."""
        self._instalados = tesseract.instalados()
        elegidos = set(
            str(self.configuracion.obtener("pdf_ocr_idiomas", "") or "").split("+"))
        if not elegidos or elegidos == {""}:
            elegidos = set(tesseract.idioma_por_omision().split("+"))

        self.lista_puestos.Set([tesseract.nombre_de(codigo) for codigo in self._instalados])
        for numero, codigo in enumerate(self._instalados):
            self.lista_puestos.Check(numero, codigo in elegidos)

        disponibles = tesseract.disponibles_para_descargar()
        self._descargables = [codigo for codigo, _nombre in disponibles]
        self.lista_nuevos.Set([nombre for _codigo, nombre in disponibles])

        self.cabecera.SetLabel(_(
            "%s\nInstalados: %d idiomas, %.1f MB.") % (
                tesseract.version() or _("Tesseract no responde"),
                len(self._instalados), tesseract.tamano_idiomas() / 1048576))
        self.boton_quitar.Enable(bool(self._instalados) and tesseract.es_portable())
        self.boton_anadir.Enable(bool(self._descargables))
        self._avisar_de_cuantos()
        self.Layout()

    def _avisar_de_cuantos(self) -> None:
        """Avisa si se ha marcado más idiomas de los que conviene.

        No es una manía: medido sobre un folleto en catalán, leerlo con cinco
        idiomas marcados dio los mismos aciertos que con tres y **el triple de
        basura**, porque el motor se empeña en leer los adornos como palabras
        de alguno de los idiomas de más.  Y tardó un tercio más.
        """
        marcados = len(self.lista_puestos.marcados())
        if marcados > 3:
            self.aviso.SetLabel(_(
                "Tienes %d idiomas marcados. Con más de tres, el reconocimiento tarda más y "
                "saca más basura sin acertar más: el motor intenta leer los adornos como "
                "palabras de alguno de los idiomas de sobra. Deja marcados solo los que de "
                "verdad aparezcan en tus documentos.") % marcados)
        elif marcados == 0:
            self.aviso.SetLabel(_(
                "No has marcado ninguno: se usarán el español, el catalán y el inglés."))
        else:
            self.aviso.SetLabel("")

    # -- acciones ------------------------------------------------------------

    def _al_anadir(self, evento) -> None:
        """Descarga los idiomas marcados en la lista de disponibles."""
        elegidos = [self._descargables[indice]
                    for indice in self.lista_nuevos.marcados()]
        if not elegidos:
            self._voz.decir(_("Marca antes algún idioma."))
            return

        progreso = DialogoProgreso(
            self, _("Idiomas del reconocimiento"),
            _n("Descargando %d idioma...", "Descargando %d idiomas...",
               len(elegidos)) % len(elegidos))
        progreso.mostrar_tras(200)
        fallos: list[str] = []
        puestos = 0
        for numero, codigo in enumerate(elegidos):
            if progreso.cancelado:
                break
            progreso.avanzar(numero, len(elegidos),
                             _("%s (%d de %d)") % (tesseract.nombre_de(codigo),
                                                   numero + 1, len(elegidos)))
            wx.Yield()
            try:
                tesseract.descargar_idioma(codigo, mejor=self.precisa.GetValue())
                puestos += 1
            except RuntimeError as error:
                fallos.append("%s: %s" % (tesseract.nombre_de(codigo), error))
        progreso.cerrar()
        wx.Yield()

        if fallos:
            wx.MessageBox(
                _("Se han añadido %d idiomas.\n\nNo se han podido añadir:\n%s")
                % (puestos, "\n".join(fallos)),
                _("Idiomas del reconocimiento"), wx.OK | wx.ICON_WARNING, self)
        else:
            self._voz.decir(_("%d idiomas añadidos.") % puestos)
        self._recargar()

    def _al_quitar(self, evento) -> None:
        """Borra del disco los idiomas marcados en la lista de instalados."""
        elegidos = [self._instalados[indice]
                    for indice in self.lista_puestos.marcados()]
        if not elegidos:
            self._voz.decir(_("Marca antes algún idioma."))
            return
        nombres = ", ".join(tesseract.nombre_de(codigo) for codigo in elegidos)
        if wx.MessageBox(
                _("¿Quitar estos idiomas?\n\n%s\n\nSe pueden volver a añadir cuando "
                  "quieras.") % nombres,
                _("Quitar idiomas"), wx.YES_NO | wx.ICON_QUESTION | wx.NO_DEFAULT,
                self) != wx.YES:
            return
        quitados = sum(1 for codigo in elegidos if tesseract.quitar_idioma(codigo))
        self._voz.decir(_("%d idiomas quitados.") % quitados)
        self._recargar()

    def _al_aceptar(self, evento) -> None:
        """Guarda con qué idiomas se va a reconocer."""
        elegidos = [self._instalados[indice]
                    for indice in self.lista_puestos.marcados()]
        self.configuracion.establecer("pdf_ocr_idiomas", "+".join(elegidos))
        log.info("Idiomas de reconocimiento: %s", "+".join(elegidos) or "(automático)")
        self.EndModal(wx.ID_OK)
