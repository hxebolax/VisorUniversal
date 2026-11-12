# -*- coding: utf-8 -*-
"""Visor HTML para los elementos estructurados del libro.

El libro se lee como texto plano, y eso tiene una consecuencia conocida: una
tabla deja de ser una tabla para el lector de pantalla.  En el texto es una
rejilla de tabuladores, así que las órdenes de tabla del lector —moverse por
filas y columnas, oír el encabezado de cada celda— no tienen nada sobre lo que
actuar.

Esta ventana lo resuelve mostrando el elemento en un **navegador de verdad**
empotrado (``wx.html2.WebView``), con el HTML reconstruido por
:mod:`nucleo.html_elementos`.  Dentro de él, una tabla se recorre exactamente
como en una página web.

Se apoya en el paquete ``wx-accessible-webview``, que resuelve el problema de
fondo del control nativo: al ser un control del sistema creado por una
factoría, no se puede heredar de él para arreglarlo, y empotrado en wxPython se
leía de forma irregular en NVDA y casi nunca en JAWS.  La solución de ese
paquete es no pelearse con el control, sino **generar dentro un documento HTML
semántico**, que es lo que el lector de pantalla sigue sin problemas.

Si el equipo no tiene el motor de WebView (Edge WebView2 en Windows), el
paquete degrada a un control de texto de solo lectura y la ventana sigue
sirviendo: se ve el contenido y se puede guardar el HTML igualmente.
"""

from __future__ import annotations

import wx

from interfaz.dialogos import ayuda_opcion
from interfaz.anuncios import Voz
from nucleo import html_elementos
from nucleo.idioma import _
from nucleo.marcas import TipoMarca
from nucleo.registro import obtener_registro, registrar_excepcion

log = obtener_registro(__name__)

MARGEN = 8


class DialogoHtml(wx.Dialog):
    """Muestra un elemento del libro como HTML navegable.

    :param padre: Ventana principal.
    :param documento: Libro abierto, de donde sale el contenido.
    :param marca: Elemento que se quiere ver (tabla, lista o cita).
    """

    def __init__(self, padre: wx.Window, documento, marca, titulo: str = "",
                 cuerpo: str = "") -> None:
        # Se admiten dos formas de llamarlo: con una **marca** —una tabla, una
        # lista, una cita, una fórmula—, que es de donde sale el contenido; o
        # con el título y el cuerpo ya montados, que es lo que hace falta para
        # enseñar un capítulo entero, que no es ninguna marca concreta.
        titulo = titulo or html_elementos.titulo_de(marca)
        super().__init__(padre, title=titulo,
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.documento = documento
        self.marca = marca
        #: Título y cuerpo con los que se abrió, si venían montados.  Con una
        #: marca están vacíos y todo se saca de ella; con un capítulo son la
        #: única fuente, porque un capítulo no es ninguna marca.
        self._titulo = titulo
        self._cuerpo_propio = cuerpo
        self._voz = Voz(self)
        self.SetSize((820, 600))

        contenedor = wx.BoxSizer(wx.VERTICAL)
        contenedor.Add(wx.StaticText(self, label=_("&Contenido:")), 0,
                       wx.LEFT | wx.RIGHT | wx.TOP, MARGEN)

        cuerpo = cuerpo or html_elementos.cuerpo_html(documento, marca)
        self.vista = self._crear_vista(titulo, cuerpo)
        contenedor.Add(self.vista.control, 1, wx.EXPAND | wx.ALL, MARGEN)

        fila = wx.BoxSizer(wx.HORIZONTAL)
        self.boton_guardar = wx.Button(self, label=_("&Guardar como HTML..."))
        self.boton_navegador = wx.Button(self, label=_("Abrir en el &navegador"))
        # Del código se copia el código, no «el texto»: es una diferencia
        # real, porque el código se copia con su sangría intacta.
        es_codigo = marca is not None and marca.tipo is TipoMarca.CODIGO
        self.boton_copiar = wx.Button(
            self, label=_("Copiar el &código") if es_codigo else _("Copiar el &texto"))
        for boton in (self.boton_guardar, self.boton_navegador, self.boton_copiar):
            fila.Add(boton, 0, wx.ALL, MARGEN)
        fila.AddStretchSpacer()
        cerrar = wx.Button(self, wx.ID_CANCEL, _("&Cerrar"))
        cerrar.SetDefault()
        fila.Add(cerrar, 0, wx.ALL, MARGEN)
        contenedor.Add(fila, 0, wx.EXPAND)

        self.estado = wx.StaticText(self, label=self._texto_de_estado())
        contenedor.Add(self.estado, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, MARGEN)

        self.SetSizer(contenedor)
        self.Layout()
        self.CentreOnParent()

        self.boton_guardar.Bind(wx.EVT_BUTTON, self._al_guardar)
        self.boton_navegador.Bind(wx.EVT_BUTTON, self._al_abrir_navegador)
        self.boton_copiar.Bind(wx.EVT_BUTTON, self._al_copiar)
        # Escape cierra desde cualquier control de la ventana.  Dentro del
        # navegador empotrado la tecla no llega hasta aquí —el control nativo
        # se la queda—, así que además se puentea desde la propia página; ver
        # ``escape_to_close`` más abajo.
        self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar)

        self.vista.focus()
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    # -- construcción --------------------------------------------------------

    def _crear_vista(self, titulo: str, cuerpo: str):
        """Crea la vista HTML, o un texto de solo lectura si no se puede."""
        from wx_accessible_webview import AccessibleWebView

        return AccessibleWebView(
            self,
            title=titulo,
            lang="es",
            # No es un registro al que se le añadan cosas, sino un documento
            # que se muestra una vez: sin región activa, que solo estorbaría.
            live_region=False,
            handler_name="visor",
            escape_to_close=True,
            on_close=self._cerrar_desde_la_pagina,
            # Los libros traen enlaces a internet; que abran el navegador del
            # sistema en lugar de sacar al usuario del elemento que estaba
            # consultando.
            open_links_externally=True,
            # El botón «Copiar el código» que va dentro de la página avisa por
            # aquí: la página se carga sin origen y en esas condiciones el
            # portapapeles del navegador no está disponible, así que copia la
            # aplicación, con el portapapeles del sistema.
            on_message=self._al_mensaje_de_la_pagina,
            initial_html=cuerpo,
        )

    def _texto_de_estado(self) -> str:
        """Frase que explica cómo se está mostrando el contenido."""
        if self.vista.using_webview:
            return (_("Recórrelo como una página web: con una tabla valen las órdenes de tabla "
                    "de tu lector de pantalla. Escape cierra esta ventana."))
        return (_("Este equipo no tiene el motor de navegador de Windows, así que el contenido "
                "se muestra como texto. Puedes guardarlo como HTML y abrirlo en tu navegador."))

    def _cuerpo(self) -> str:
        """El HTML que se está mostrando, venga de donde venga."""
        if self._cuerpo_propio:
            return self._cuerpo_propio
        return html_elementos.cuerpo_html(self.documento, self.marca)

    def _documento_completo(self, titulo_libro: str) -> str:
        """La página HTML entera, para guardarla o abrirla en el navegador."""
        if self._cuerpo_propio:
            return html_elementos.envolver_html(
                self._titulo or _("Capítulo"), self._cuerpo_propio, titulo_libro)
        return html_elementos.documento_html(self.documento, self.marca, titulo_libro)

    # -- acciones ------------------------------------------------------------

    def _nombre_propuesto(self) -> str:
        """Nombre de archivo razonable para guardar el elemento."""
        limpio = "".join(
            caracter if caracter.isalnum() or caracter in " -_" else " "
            for caracter in (self._titulo or html_elementos.titulo_de(self.marca))
        )
        return " ".join(limpio.split())[:60] + ".html"

    def _al_guardar(self, evento) -> None:
        """Guarda el elemento como un archivo HTML independiente."""
        titulo_libro = ""
        if self.documento is not None:
            titulo_libro = self.documento.metadatos.titulo or ""
        with wx.FileDialog(self, "Guardar como HTML", defaultFile=self._nombre_propuesto(),
                           wildcard=_("Páginas web (*.html)|*.html|Todos los archivos|*.*"),
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                return
            destino = dialogo.GetPath()
        try:
            with open(destino, "w", encoding="utf-8") as archivo:
                archivo.write(self._documento_completo(titulo_libro))
        except OSError as error:
            registrar_excepcion(log, "No se ha podido guardar el HTML", error)
            wx.MessageBox(_("No se ha podido guardar el archivo:\n\n%s") % error,
                          _("Guardar como HTML"), wx.OK | wx.ICON_ERROR, self)
            return
        log.info("Elemento guardado como HTML en %s", destino)
        self.estado.SetLabel(_("Guardado en %s") % destino)
        self._voz.decir(_("Guardado."))

    def _al_abrir_navegador(self, evento) -> None:
        """Escribe el HTML en la carpeta temporal y lo abre en el navegador.

        Es la salida para cuando hace falta más de lo que da esta ventana:
        buscar dentro con las órdenes del navegador, ampliar, imprimir o
        guardar la tabla desde ahí.
        """
        from nucleo import rutas

        titulo_libro = self.documento.metadatos.titulo if self.documento is not None else ""
        destino = rutas.ruta_temp() / "elemento.html"
        try:
            destino.write_text(self._documento_completo(titulo_libro), encoding="utf-8")
        except OSError as error:
            registrar_excepcion(log, "No se ha podido preparar el HTML temporal", error)
            wx.MessageBox(_("No se ha podido preparar el archivo:\n\n%s") % error,
                          _("Abrir en el navegador"), wx.OK | wx.ICON_ERROR, self)
            return
        wx.LaunchDefaultBrowser(destino.as_uri())
        self.estado.SetLabel(_("Abierto en el navegador."))

    def _al_copiar(self, evento) -> None:
        """Copia al portapapeles el contenido en texto plano."""
        from wx_accessible_webview import strip_tags

        if self.marca is not None and self.marca.tipo is TipoMarca.CODIGO:
            # Un bloque de código se copia **tal cual**: quitarle la sangría
            # sería entregar algo que no se puede pegar y ejecutar, que es para
            # lo que se copia.
            self._copiar_texto(self._codigo(0), _("Código copiado al portapapeles."))
            return
        texto = strip_tags(self._cuerpo())
        texto = "\n".join(linea.strip() for linea in texto.splitlines() if linea.strip())
        self._copiar_texto(texto, _("Contenido copiado al portapapeles."))

    def _codigo(self, indice: int) -> str:
        """Texto exacto del bloque de código número ``indice`` de la página."""
        bloques = html_elementos.codigos_de(self._cuerpo())
        if 0 <= indice < len(bloques):
            return bloques[indice]
        return ""

    def _copiar_texto(self, texto: str, aviso: str) -> None:
        """Deja un texto en el portapapeles del sistema y lo dice."""
        if not texto or not wx.TheClipboard.Open():
            return
        try:
            wx.TheClipboard.SetData(wx.TextDataObject(texto))
        finally:
            wx.TheClipboard.Close()
        self.estado.SetLabel(aviso)
        self._voz.decir(aviso)

    def _al_mensaje_de_la_pagina(self, datos) -> None:
        """Atiende lo que pide la página: por ahora, copiar un bloque de código."""
        if not isinstance(datos, dict) or datos.get("type") != "copiar":
            return
        try:
            indice = int(datos.get("indice") or 0)
        except (TypeError, ValueError):
            indice = 0
        codigo = self._codigo(indice)
        if not codigo:
            return
        # Llega desde el hilo de la página: se aplaza para tocar el
        # portapapeles y la interfaz desde el hilo de siempre.
        wx.CallAfter(self._copiar_texto, codigo, _("Código copiado al portapapeles."))

    # -- cierre --------------------------------------------------------------

    def _cerrar_desde_la_pagina(self) -> None:
        """Cierra la ventana cuando el Escape llega desde el navegador."""
        # Llega desde el hilo de la página; se aplaza para no cerrar la ventana
        # en mitad de la atención de un evento del control nativo.
        wx.CallAfter(self.EndModal, wx.ID_CANCEL)

    def _al_pulsar(self, evento: wx.KeyEvent) -> None:
        """Escape cierra; el resto de teclas siguen su camino."""
        if evento.GetKeyCode() == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
            return
        evento.Skip()


def mostrar_capitulo(padre: wx.Window, documento, posicion: int) -> None:
    """Abre el visor con el capítulo donde cae esa posición."""
    titulo, cuerpo = html_elementos.html_de_capitulo(documento, posicion)
    with DialogoHtml(padre, documento, None, titulo=titulo, cuerpo=cuerpo) as dialogo:
        dialogo.ShowModal()


def mostrar(padre: wx.Window, documento, marca) -> bool:
    """Abre el visor HTML para un elemento, si es de los que se pueden ver.

    :return: ``True`` si se ha mostrado.
    """
    if not html_elementos.se_puede_convertir(marca, documento):
        return False
    with DialogoHtml(padre, documento, marca) as dialogo:
        dialogo.ShowModal()
    return True
