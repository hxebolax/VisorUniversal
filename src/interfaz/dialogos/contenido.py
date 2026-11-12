# -*- coding: utf-8 -*-
"""Diálogos que muestran contenido del libro: imágenes, tablas, datos y notas.

El visor de imágenes es la respuesta a una limitación del texto plano: en la
lectura, una fotografía aparece como ``[Imagen: descripción]``, lo que permite
localizarla y saber qué es; con este diálogo se ve además la imagen real.

El visor de tablas presenta la rejilla en una lista de varias columnas, que es
la forma en que los lectores de pantalla anuncian correctamente «fila 3,
columna 2» al desplazarse.  Esa lista es una :class:`interfaz.listas.ListaAccesible`,
de modo que las flechas izquierda y derecha recorren las celdas de la fila.
"""

from __future__ import annotations

import io

import wx

from formatos import base as formatos
from interfaz.accesible import etiquetar
from interfaz.dialogos import ayuda_opcion
from interfaz.listas import ListaAccesible
from interfaz.ventanas_win32 import suprimir_menu_contextual
from nucleo import etiquetas
from nucleo.documento import Documento
from nucleo.idioma import _
from nucleo.marcas import Marca
from nucleo.registro import obtener_registro, registrar_excepcion

log = obtener_registro(__name__)

MARGEN = 8


class DialogoImagen(wx.Dialog):
    """Muestra una imagen del libro junto con su descripción.

    Si hay una descripción hecha con inteligencia artificial guardada para esa
    imagen, se muestra esa en lugar de la del EPUB: es la que de verdad cuenta
    lo que se ve.  El botón «Describir con IA» permite pedir otra en cualquier
    momento, con el prompt que se prefiera.

    :param padre: Ventana principal.
    :param ruta_libro: Archivo EPUB del que hay que extraer la imagen.
    :param marca: Marca de imagen o figura que se quiere ver.
    :param configuracion: Preferencias.  Si es ``None``, el diálogo funciona
                          igual pero sin la parte de inteligencia artificial.
    :param coleccion: Descripciones guardadas del libro.
    :param contexto: Datos del libro que se le pasan a la IA como contexto.
    """

    def __init__(self, padre: wx.Window, ruta_libro: str, marca: Marca,
                 configuracion=None, coleccion=None, contexto: str = "") -> None:
        super().__init__(padre, title=_("Imagen del documento"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.marca = marca
        self.ruta_libro = ruta_libro
        self.configuracion = configuracion
        self.coleccion = coleccion
        self.contexto = contexto
        self._datos: bytes | None = None

        contenedor = wx.BoxSizer(wx.VERTICAL)

        guardada = coleccion.obtener(marca.referencia or "") if coleccion is not None else None
        if guardada is not None and guardada.texto.strip():
            descripcion = guardada.texto.strip()
        else:
            descripcion = ((marca.texto or "").strip()
                           or _("Esta imagen no tiene descripción en el documento."))
        contenedor.Add(wx.StaticText(self, label=_("&Descripción:")), 0, wx.ALL, MARGEN)
        self.campo_descripcion = etiquetar(wx.TextCtrl(
            self, value=descripcion, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_NOHIDESEL,
            size=(560, 60),
        ), _("Descripción de la imagen"))
        self._sin_menu = [suprimir_menu_contextual(self.campo_descripcion)]
        contenedor.Add(self.campo_descripcion, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, MARGEN)

        self.lienzo = etiquetar(wx.StaticBitmap(self, size=(560, 380)), _("Imagen del documento"))
        contenedor.Add(self.lienzo, 1, wx.EXPAND | wx.ALL, MARGEN)

        self.estado = wx.StaticText(self, label="")
        contenedor.Add(self.estado, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, MARGEN)

        fila = wx.StdDialogButtonSizer()
        self.boton_describir = wx.Button(self, label=_("&Describir con IA..."))
        self.boton_guardar = wx.Button(self, label=_("&Guardar imagen..."))
        cerrar = wx.Button(self, wx.ID_OK, _("&Cerrar"))
        cerrar.SetDefault()
        fila.Add(self.boton_describir, 0, wx.RIGHT, MARGEN)
        fila.Add(self.boton_guardar, 0, wx.RIGHT, MARGEN)
        fila.AddButton(cerrar)
        fila.Realize()
        contenedor.Add(fila, 0, wx.EXPAND | wx.ALL, MARGEN)

        self.SetSizerAndFit(contenedor)
        self.boton_guardar.Bind(wx.EVT_BUTTON, self._al_guardar)
        self.boton_describir.Bind(wx.EVT_BUTTON, self._al_describir)
        self.boton_describir.Enable(configuracion is not None)
        self._cargar_imagen()
        self.campo_descripcion.SetFocus()
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    def _al_describir(self, evento) -> None:
        """Abre el diálogo de descripción con inteligencia artificial.

        A diferencia de la tecla rápida, aquí **no** se lanza la petición sola:
        quien llega por este camino ya está mirando la imagen y puede querer
        elegir antes el tipo de descripción.
        """
        from interfaz.dialogos.ia import DialogoDescripcion

        if self.configuracion is None or not self._datos:
            wx.MessageBox(_("No se ha podido extraer esta imagen del libro, así que no se puede "
                          "describir."), _("Describir la imagen"), wx.OK | wx.ICON_INFORMATION, self)
            return
        guardada = (self.coleccion.obtener(self.marca.referencia or "")
                    if self.coleccion is not None else None)
        with DialogoDescripcion(self, self._datos, self.marca, self.configuracion,
                                self.coleccion, self.contexto, guardada) as dialogo:
            dialogo.ShowModal()
        # Al volver, la descripción que se ve en el visor es la que acabe de
        # quedar guardada, para que las dos ventanas digan lo mismo.
        nueva = (self.coleccion.obtener(self.marca.referencia or "")
                 if self.coleccion is not None else None)
        if nueva is not None and nueva.texto.strip():
            self.campo_descripcion.SetValue(nueva.texto.strip())
            self.campo_descripcion.SetInsertionPoint(0)

    def _cargar_imagen(self) -> None:
        """Extrae la imagen del libro y la muestra ajustada al espacio disponible."""
        if not self.marca.referencia:
            self.estado.SetLabel(_("El documento no indica qué archivo contiene esta imagen."))
            self.boton_guardar.Disable()
            return
        try:
            self._datos = formatos.extraer_recurso(self.ruta_libro, self.marca.referencia)
        except Exception as error:
            registrar_excepcion(log, "Error extrayendo la imagen %s" % self.marca.referencia, error)
            self._datos = None
        if not self._datos:
            self.estado.SetLabel(_("No se ha podido extraer la imagen «%s» del documento.")
                                 % self.marca.referencia)
            self.boton_guardar.Disable()
            return
        try:
            imagen = wx.Image(io.BytesIO(self._datos))
            if not imagen.IsOk():
                raise ValueError(_("formato de imagen no reconocido"))
        except Exception as error:
            registrar_excepcion(log, "Imagen ilegible: %s" % self.marca.referencia, error)
            self.estado.SetLabel(_("El formato de esta imagen no se puede mostrar."))
            return
        ancho_original, alto_original = imagen.GetWidth(), imagen.GetHeight()
        ancho_max, alto_max = 560, 380
        escala = min(ancho_max / ancho_original, alto_max / alto_original, 1.0)
        if escala < 1.0:
            imagen = imagen.Scale(int(ancho_original * escala), int(alto_original * escala),
                                  wx.IMAGE_QUALITY_HIGH)
        self.lienzo.SetBitmap(wx.Bitmap(imagen))
        self.estado.SetLabel(_("Archivo: %s  |  %d por %d píxeles")
                             % (self.marca.referencia, ancho_original, alto_original))
        self.Layout()

    def _al_guardar(self, evento) -> None:
        """Guarda la imagen en el disco."""
        if not self._datos:
            return
        nombre = self.marca.referencia.rsplit("/", 1)[-1] or "imagen"
        with wx.FileDialog(self, "Guardar imagen", defaultFile=nombre,
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                return
            try:
                with open(dialogo.GetPath(), "wb") as archivo:
                    archivo.write(self._datos)
                self.estado.SetLabel(_("Imagen guardada."))
            except OSError as error:
                wx.MessageBox(_("No se ha podido guardar la imagen: %s") % error,
                              _("Error"), wx.OK | wx.ICON_ERROR, self)


class DialogoTabla(wx.Dialog):
    """Muestra una tabla del libro en forma de rejilla.

    La rejilla se recorre por filas con las flechas arriba y abajo, y **por
    celdas** con las flechas izquierda y derecha, que es la única manera de
    consultar una casilla concreta sin oír la fila entera.

    :param configuracion: Preferencias, para los ajustes de lectura por
                          columnas.
    """

    def __init__(self, padre: wx.Window, marca: Marca, configuracion=None) -> None:
        super().__init__(padre, title="Tabla: %s" % (marca.texto or _("sin título")),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.marca = marca
        contenedor = wx.BoxSizer(wx.VERTICAL)
        contenedor.Add(wx.StaticText(self, label=_("Contenido de la &tabla:")), 0, wx.ALL, MARGEN)

        self.rejilla = etiquetar(ListaAccesible(
            self, configuracion, _("Contenido de la tabla"), size=(680, 420),
            style=wx.LC_SINGLE_SEL | wx.LC_HRULES | wx.LC_VRULES,
        ), _("Contenido de la tabla"))
        contenedor.Add(self.rejilla, 1, wx.EXPAND | wx.ALL, MARGEN)

        fila = wx.StdDialogButtonSizer()
        self.boton_html = wx.Button(self, label=_("Ver como &HTML..."))
        cerrar = wx.Button(self, wx.ID_OK, _("&Cerrar"))
        cerrar.SetDefault()
        fila.Add(self.boton_html, 0, wx.RIGHT, MARGEN)
        fila.AddButton(cerrar)
        fila.Realize()
        contenedor.Add(fila, 0, wx.EXPAND | wx.ALL, MARGEN)
        self.SetSizerAndFit(contenedor)

        self.boton_html.Bind(wx.EVT_BUTTON, self._al_ver_html)
        self._rellenar(marca.referencia or "")
        self.rejilla.SetFocus()
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    def _al_ver_html(self, evento) -> None:
        """Abre la misma tabla en el visor HTML.

        La rejilla y el visor se complementan: la rejilla es rápida y va con el
        resto del programa, y el visor devuelve a la tabla su condición de
        tabla, con las órdenes de tabla del lector de pantalla.
        """
        from interfaz.dialogos import visor_html

        visor_html.mostrar(self, None, self.marca)

    def _rellenar(self, rejilla_texto: str) -> None:
        """Vuelca la rejilla, tomando la primera fila como encabezado."""
        filas = [linea.split("\t") for linea in rejilla_texto.split("\n") if linea != ""]
        if not filas:
            self.rejilla.InsertColumn(0, _("Tabla"))
            self.rejilla.InsertItem(0, _("(La tabla no tiene contenido legible)"))
            return
        columnas = max(len(fila) for fila in filas)
        encabezados = filas[0]
        for numero in range(columnas):
            titulo = encabezados[numero] if numero < len(encabezados) else ""
            self.rejilla.InsertColumn(numero, titulo.strip() or "Columna %d" % (numero + 1), width=180)
        for indice, fila in enumerate(filas[1:]):
            posicion = self.rejilla.InsertItem(indice, fila[0] if fila else "")
            for numero in range(1, columnas):
                self.rejilla.SetItem(posicion, numero, fila[numero] if numero < len(fila) else "")
        if self.rejilla.GetItemCount():
            self.rejilla.Select(0)
            self.rejilla.Focus(0)


class DialogoInformacion(wx.Dialog):
    """Muestra los datos del libro y sus estadísticas."""

    def __init__(self, padre: wx.Window, documento: Documento,
                 cronometro=None, posicion: int = 0) -> None:
        super().__init__(padre, title=_("Información del documento"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        contenedor = wx.BoxSizer(wx.VERTICAL)
        contenedor.Add(wx.StaticText(self, label=_("&Datos del documento:")), 0, wx.ALL, MARGEN)
        campo = etiquetar(wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_NOHIDESEL,
                                      size=(560, 400)), _("Datos del documento"))
        self._sin_menu = [suprimir_menu_contextual(campo)]
        campo.SetValue(self._construir_texto(documento, cronometro, posicion))
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
    def _construir_texto(documento: Documento, cronometro=None, posicion: int = 0) -> str:
        """Redacta el informe con los metadatos, los recuentos y la lectura."""
        from nucleo import estadisticas as medidas
        from nucleo.marcas import TipoMarca

        lineas: list[str] = []
        for etiqueta, valor in documento.metadatos.como_lista():
            lineas.append("%s: %s" % (etiqueta, valor))
        lineas.append("Archivo: %s" % documento.ruta_archivo)
        lineas.append("")
        lineas.append(_("ESTADÍSTICAS"))
        estadisticas = documento.estadisticas()
        lineas.append("Palabras: %s" % format(estadisticas.palabras, ",d").replace(",", "."))
        lineas.append("Caracteres: %s" % format(estadisticas.caracteres, ",d").replace(",", "."))
        lineas.append("Caracteres sin espacios: %s"
                      % format(estadisticas.caracteres_sin_espacios, ",d").replace(",", "."))
        lineas.append(_("Líneas: %s") % format(estadisticas.lineas, ",d").replace(",", "."))
        lineas.append(_("Capítulos (secciones): %d") % len(documento.secciones))
        lineas.append(_("Entradas del índice: %d") % len(documento.indice_plano()))
        lineas.append(_("Páginas: %d") % documento.total_paginas)

        # --- lo que se lleva leído de este documento -------------------------
        if cronometro is not None:
            total = len(documento.texto)
            lineas.append("")
            lineas.append(_("TU LECTURA"))
            lineas.append(_("Vas por el %d por ciento del documento.")
                          % documento.porcentaje_en(posicion))
            lineas.extend(medidas.resumen(cronometro, posicion, total))

        lineas.append("")
        lineas.append("ELEMENTOS")
        etiquetas = (
            ("Encabezados", None),
            ("Enlaces", TipoMarca.ENLACE),
            (_("Imágenes"), TipoMarca.IMAGEN),
            ("Figuras", TipoMarca.FIGURA),
            ("Tablas", TipoMarca.TABLA),
            ("Listas", TipoMarca.LISTA),
            (_("Elementos de lista"), TipoMarca.ELEMENTO_LISTA),
            ("Citas", TipoMarca.CITA),
            (_("Fórmulas"), TipoMarca.FORMULA),
            (_("Bloques de código"), TipoMarca.CODIGO),
            (_("Llamadas de nota al pie"), TipoMarca.NOTA_PIE),
            ("Separadores", TipoMarca.SEPARADOR),
        )
        for nombre, tipo in etiquetas:
            cantidad = (len(documento.marcas.encabezados) if tipo is None
                        else documento.marcas.cantidad(tipo))
            lineas.append("%s: %d" % (nombre, cantidad))
        return "\n".join(lineas)


class DialogoNota(wx.Dialog):
    """Permite escribir o editar la nota asociada a una posición del libro.

    Debajo del texto hay un campo de **etiquetas**, que es lo que después
    permite juntar todo lo de un tema aunque esté repartido por varios libros.
    Va aquí y no en un diálogo aparte a propósito: una etiqueta que cuesta
    ponerla no se pone.
    """

    def __init__(self, padre: wx.Window, texto_inicial: str = "", fragmento: str = "",
                 etiquetas_iniciales=None, ya_usadas=None) -> None:
        super().__init__(padre, title=_("Nota"))
        self.nota = ""
        self.etiquetas: list[str] = []
        contenedor = wx.BoxSizer(wx.VERTICAL)
        if fragmento:
            contenedor.Add(wx.StaticText(self, label=_("Texto marcado:")), 0, wx.ALL, MARGEN)
            muestra = etiquetar(wx.TextCtrl(self, value=fragmento[:400],
                                            style=wx.TE_MULTILINE | wx.TE_READONLY,
                                            size=(460, 60)), _("Texto marcado"))
            contenedor.Add(muestra, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, MARGEN)
        contenedor.Add(wx.StaticText(self, label=_("&Nota:")), 0, wx.ALL, MARGEN)
        self.campo = etiquetar(wx.TextCtrl(self, value=texto_inicial, style=wx.TE_MULTILINE,
                                           size=(460, 160)), _("Texto de la nota"))
        self._sin_menu = [suprimir_menu_contextual(self.campo)]
        contenedor.Add(self.campo, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, MARGEN)

        contenedor.Add(wx.StaticText(self, label=_("&Etiquetas, separadas por comas:")),
                       0, wx.ALL, MARGEN)
        # Es un ComboBox y no un cuadro de texto para que las etiquetas que ya
        # se usan estén a un cursor abajo: sin eso se acaba teniendo <<examen>>,
        # <<exámenes>> y <<para el examen>> como tres temas distintos.
        self.campo_etiquetas = etiquetar(
            wx.ComboBox(self, value=etiquetas.escribir(etiquetas_iniciales or []),
                        choices=list(ya_usadas or []), size=(460, -1)),
            _("Etiquetas de la nota, separadas por comas"))
        contenedor.Add(self.campo_etiquetas, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, MARGEN)

        fila = wx.StdDialogButtonSizer()
        aceptar = wx.Button(self, wx.ID_OK, _("&Guardar"))
        aceptar.SetDefault()
        fila.AddButton(aceptar)
        fila.AddButton(wx.Button(self, wx.ID_CANCEL, _("&Cancelar")))
        fila.Realize()
        contenedor.Add(fila, 0, wx.EXPAND | wx.ALL, MARGEN)
        self.SetSizerAndFit(contenedor)
        self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)
        self.campo.SetFocus()
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    def _al_aceptar(self, evento) -> None:
        """Recoge el texto escrito y las etiquetas."""
        del evento
        self.nota = self.campo.GetValue().strip()
        self.etiquetas = etiquetas.leer(self.campo_etiquetas.GetValue())
        self.EndModal(wx.ID_OK)
