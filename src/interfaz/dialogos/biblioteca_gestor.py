# -*- coding: utf-8 -*-
"""Gestionar de dónde salen los libros: carpetas y bibliotecas de calibre.

La biblioteca junta libros de varias **fuentes**: carpetas corrientes y
bibliotecas de calibre.  Esta ventana las enseña todas en una lista, con
cuántos libros trae cada una, cuándo se actualizó y si ahora mismo está al
alcance, y deja hacer con ellas lo que hace falta **de varias en varias**:

* **Añadir** una carpeta.  Si es una biblioteca de calibre se reconoce sola y
  se importa con todos los datos de calibre.
* **Actualizar** las marcadas, o todas: se traen los libros nuevos, se ponen al
  día los que han cambiado y se quitan los que ya no están.
* **Editar** una: cambiarle el nombre o llevarla a otra ruta cuando el disco
  cambia de letra, sin volver a importar.
* **Quitar** las marcadas con todos sus libros.  No se borra nada del disco.
* Hacer una **copia de seguridad** de la biblioteca entera y restaurarla.

Todo lo que tarda se hace en segundo plano: la ventana sigue respondiendo, el
avance se ve en una barra y se dice en voz alta cada pocos segundos, se puede
detener, y al terminar se enseña un resumen de lo hecho.

Aquí están también las piezas que comparte con la ventana de la biblioteca:
:class:`Tarea` (trabajo en segundo plano con su avance) y
:func:`anadir_carpeta`.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time

import wx

from interfaz.accesible import etiquetar, fila_etiquetada
from interfaz.anuncios import Voz
from interfaz.dialogos import ayuda_opcion
from interfaz.listas import ListaAccesible, rellenar_columnas
from nucleo import biblioteca_datos as datos
from nucleo import biblioteca_importar as importar
from nucleo.idioma import _, _n
from nucleo.registro import obtener_registro, registrar_excepcion

log = obtener_registro(__name__)

MARGEN = 8


# -- trabajo en segundo plano ----------------------------------------------------


class Tarea:
    """Hace un trabajo largo en otro hilo y lo va contando en una ventana.

    Junta lo que necesita cualquier ventana con trabajo largo: una barra de
    avance, un texto con por dónde va, un botón para detener y un aviso
    hablado cada pocos segundos (cada cuántos, o nunca, se elige en Opciones).

    :param ventana: Ventana dueña; si se cierra, los avisos se descartan.
    :param barra: ``wx.Gauge`` donde se pinta el avance.
    :param estado: ``wx.StaticText`` donde se escribe por dónde va.
    :param detener: Botón que lo para; se activa solo mientras hay trabajo.
    """

    def __init__(self, ventana: wx.Window, barra: wx.Gauge, estado: wx.StaticText,
                 detener: wx.Button, configuracion) -> None:
        self.ventana = ventana
        self.barra = barra
        self.estado = estado
        self.detener = detener
        self.configuracion = configuracion
        self.voz = Voz(ventana)
        self.parar = threading.Event()
        self.activa = False
        self._ultimo_aviso = 0.0
        self._detalle = ""
        detener.Bind(wx.EVT_BUTTON, lambda evento: self.pedir_parada())

    def pedir_parada(self) -> None:
        """Pide que se pare lo que esté en marcha."""
        if self.activa:
            self.parar.set()
            self.voz.decir(_("Deteniendo..."))

    def ocupada(self) -> bool:
        """Si hay un trabajo en marcha; si lo hay, lo dice."""
        if self.activa:
            self.voz.decir(_("Espera a que termine lo que está en marcha, o detenlo."))
        return self.activa

    def lanzar(self, trabajo, al_terminar, aviso: str = "") -> bool:
        """Empieza un trabajo en otro hilo.

        :param trabajo: Función ``(progreso, cancelado) -> resultado``.
        :param al_terminar: Se llama en el hilo de la ventana con
                            ``(resultado, error)``; ``error`` es un texto vacío
                            si todo ha ido bien.
        :return: ``False`` si ya había otro trabajo en marcha.
        """
        if self.activa:
            self.voz.decir(_("Espera a que termine lo que está en marcha, o detenlo."))
            return False
        self.activa = True
        self.parar.clear()
        self.detener.Enable(True)
        self.barra.SetValue(0)
        self._detalle = ""
        self._ultimo_aviso = time.monotonic()
        if aviso:
            self.estado.SetLabel(aviso)
            self.voz.decir(aviso)

        ultimo = [0.0]

        def progreso(hecho: int, total: int, detalle: str) -> None:
            # Se filtra aquí, en el hilo que trabaja: buscar en ciento noventa
            # mil libros avisa una vez por libro, y mandar cada aviso a la
            # ventana llenaría su cola hasta dejarla sin responder.
            ahora = time.monotonic()
            if ahora - ultimo[0] < 0.2 and not (total and hecho >= total):
                return
            ultimo[0] = ahora
            wx.CallAfter(self._avance, hecho, total, detalle)

        def en_hilo() -> None:
            try:
                resultado = trabajo(progreso, self.parar.is_set)
            except Exception as error:               # pragma: no cover
                registrar_excepcion(log, "Error en un trabajo de la biblioteca", error)
                wx.CallAfter(self._fin, al_terminar, None, str(error) or repr(error))
            else:
                wx.CallAfter(self._fin, al_terminar, resultado, "")

        threading.Thread(target=en_hilo, name="biblioteca-tarea", daemon=True).start()
        return True

    def _avance(self, hecho: int, total: int, detalle: str) -> None:
        """Pinta el avance y, de vez en cuando, lo dice."""
        if not self.ventana or not self.activa:
            return
        if total > 0:
            self.barra.SetRange(1000)
            self.barra.SetValue(int(min(hecho, total) * 1000 / total))
        else:
            self.barra.Pulse()
        if detalle:
            self._detalle = detalle
        # El porcentaje va también en el texto y no solo en la barra: la barra
        # el lector de pantalla la dice con pitidos o no la dice, y el texto se
        # puede leer cuando uno quiera.
        if self._detalle:
            if total > 0:
                self.estado.SetLabel("%s (%d %%)" % (
                    self._detalle, int(min(hecho, total) * 100 / total)))
            else:
                self.estado.SetLabel(self._detalle)
        cada = int(self.configuracion.obtener("biblioteca_anunciar_avance", 10) or 0)
        ahora = time.monotonic()
        if cada > 0 and ahora - self._ultimo_aviso >= cada and self._detalle:
            self._ultimo_aviso = ahora
            frase = self._detalle
            if total > 0:
                frase = "%d %%. %s" % (int(min(hecho, total) * 100 / total), frase)
            self.voz.decir(frase, interrumpir=False)

    def _fin(self, al_terminar, resultado, error: str) -> None:
        """Deja la ventana como estaba y entrega el resultado."""
        if not self.ventana:
            return
        self.activa = False
        self.detener.Enable(False)
        self.barra.SetRange(1000)
        self.barra.SetValue(0 if error else 1000)
        try:
            al_terminar(resultado, error)
        except Exception as fallo:                   # pragma: no cover
            registrar_excepcion(log, "Error al recoger un trabajo de la biblioteca", fallo)


def crear_barra(ventana: wx.Window, contenedor: wx.Sizer):
    """La fila de avance: texto, barra y botón de detener.

    :return: ``(estado, barra, detener)``.
    """
    estado = wx.StaticText(ventana, label="")
    contenedor.Add(estado, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, MARGEN)
    fila = wx.BoxSizer(wx.HORIZONTAL)
    barra = etiquetar(wx.Gauge(ventana, range=1000, size=(-1, 18)), _("Avance"))
    fila.Add(barra, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, MARGEN)
    detener = wx.Button(ventana, label=_("Dete&ner"))
    detener.Enable(False)
    fila.Add(detener, 0)
    contenedor.Add(fila, 0, wx.EXPAND | wx.ALL, MARGEN)
    return estado, barra, detener


def trabajo_importar(fuente_ids, configuracion):
    """El trabajo de importar o actualizar fuentes, listo para :meth:`Tarea.lanzar`."""
    opciones = importar.OpcionesImportacion.desde_configuracion(configuracion)
    ids = list(fuente_ids)

    def trabajo(progreso, cancelado):
        return importar.importar(ids, opciones, progreso=progreso, cancelado=cancelado)

    return trabajo


# -- añadir ----------------------------------------------------------------------


def anadir_carpeta(padre: wx.Window, configuracion, voz: Voz) -> int | None:
    """Pide una carpeta y la da de alta como fuente.  No importa nada todavía.

    Si la carpeta es una biblioteca de calibre (tiene ``metadata.db``) se da de
    alta como tal, se pregunta o se trata como carpeta corriente, según lo
    elegido en Opciones.

    :return: El número de la fuente que hay que importar, o ``None``.
    """
    with wx.DirDialog(padre, _("Carpeta con libros o biblioteca de calibre")) as dialogo:
        if dialogo.ShowModal() != wx.ID_OK:
            return None
        carpeta = os.path.normpath(dialogo.GetPath())
    conexion = datos.conectar()
    try:
        ya = datos.fuente_que_contiene(conexion, carpeta)
        if ya is not None:
            if datos.clave(ya.ruta) == datos.clave(carpeta):
                respuesta = wx.MessageBox(
                    _("«%s» ya está en la biblioteca.\n\n¿Quieres actualizarla ahora?")
                    % ya.nombre, _("Añadir a la biblioteca"),
                    wx.YES_NO | wx.ICON_QUESTION, padre)
                return ya.id if respuesta == wx.YES else None
            wx.MessageBox(
                _("Esa carpeta ya está dentro de «%(fuente)s», que ya forma parte de "
                  "la biblioteca:\n\n%(ruta)s\n\nSus libros ya están; para traer lo "
                  "nuevo, actualiza «%(fuente)s».")
                % {"fuente": ya.nombre, "ruta": ya.ruta},
                _("Añadir a la biblioteca"), wx.OK | wx.ICON_INFORMATION, padre)
            return None
        tipo = datos.CARPETA
        if importar.es_biblioteca_calibre(carpeta):
            modo = str(configuracion.obtener("biblioteca_calibre_modo", "calibre") or "calibre")
            if modo == "calibre":
                tipo = datos.CALIBRE
                voz.decir(_("Es una biblioteca de calibre: se importa con todos sus datos."))
            elif modo == "preguntar":
                respuesta = wx.MessageBox(
                    _("Esta carpeta es una biblioteca de calibre.\n\n"
                      "Sí: importarla con todos los datos de calibre (autores, series, "
                      "etiquetas, sinopsis, columnas propias...).\n"
                      "No: tratarla como una carpeta corriente."),
                    _("Biblioteca de calibre"),
                    wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION, padre)
                if respuesta == wx.CANCEL:
                    return None
                if respuesta == wx.YES:
                    tipo = datos.CALIBRE
        nombre = (importar.nombre_de_calibre(carpeta) if tipo == datos.CALIBRE
                  else os.path.basename(carpeta) or carpeta)
        return datos.anadir_fuente(conexion, tipo, carpeta, nombre, pendiente=True)
    finally:
        conexion.close()


# -- el resumen --------------------------------------------------------------------


class DialogoResumen(wx.Dialog):
    """Enseña el resumen de lo hecho en un cuadro que se puede recorrer.

    Un aviso corriente se lee de una tirada y se cierra; aquí el resumen va en
    un cuadro de solo lectura para poder ir línea a línea con las flechas,
    volver sobre un número y copiarlo.
    """

    def __init__(self, padre: wx.Window, titulo: str, texto: str) -> None:
        super().__init__(padre, title=titulo,
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        contenedor = wx.BoxSizer(wx.VERTICAL)
        self.texto = fila_etiquetada(
            self, contenedor, _("&Resumen:"),
            lambda p: wx.TextCtrl(p, value=texto, size=(560, 300),
                                  style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_NOHIDESEL),
            margen=MARGEN, proporcion=1)
        pie = wx.StdDialogButtonSizer()
        cerrar = wx.Button(self, wx.ID_OK, _("&Cerrar"))
        cerrar.SetDefault()
        pie.AddButton(cerrar)
        pie.Realize()
        contenedor.Add(pie, 0, wx.EXPAND | wx.ALL, MARGEN)
        self.SetSizerAndFit(contenedor)
        self.SetEscapeId(wx.ID_OK)
        self.CentreOnParent()
        self.texto.SetFocus()
        self.texto.SetInsertionPoint(0)
        ayuda_opcion.enganchar(self)


def mostrar_resumen(padre: wx.Window, resumenes, error: str = "") -> None:
    """Enseña el resumen de una importación."""
    texto = importar.texto_resumen(resumenes or [])
    if error:
        texto = _("Ha habido un error: %s") % error + "\n\n" + texto
    with DialogoResumen(padre, _("Resumen de la importación"), texto) as dialogo:
        dialogo.ShowModal()


# -- editar una fuente -----------------------------------------------------------


class DialogoEditarFuente(wx.Dialog):
    """Cambia el nombre, la ruta o el tipo de una fuente."""

    def __init__(self, padre: wx.Window, fuente: datos.Fuente) -> None:
        super().__init__(padre, title=_("Editar «%s»") % fuente.nombre,
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.fuente = fuente
        contenedor = wx.BoxSizer(wx.VERTICAL)
        self.nombre = fila_etiquetada(
            self, contenedor, _("&Nombre:"),
            lambda p: wx.TextCtrl(p, value=fuente.nombre, size=(420, -1)),
            margen=MARGEN)
        self.ruta = fila_etiquetada(
            self, contenedor, _("&Ruta de la carpeta:"),
            lambda p: wx.TextCtrl(p, value=fuente.ruta, size=(420, -1)),
            margen=MARGEN)
        self.boton_elegir = wx.Button(self, label=_("&Elegir otra carpeta..."))
        contenedor.Add(self.boton_elegir, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, MARGEN)
        self._tipos = [(datos.CALIBRE, _("Biblioteca de calibre, con sus datos")),
                       (datos.CARPETA, _("Carpeta corriente"))]
        self.tipo = fila_etiquetada(
            self, contenedor, _("&Tipo:"),
            lambda p: wx.Choice(p, choices=[n for _c, n in self._tipos]),
            margen=MARGEN)
        self.tipo.SetSelection(0 if fuente.es_calibre else 1)
        contenedor.Add(wx.StaticText(self, label=_(
            "Cambiar la ruta recoloca todos sus libros sin volver a importarlos: es\n"
            "para cuando el disco cambia de letra o la carpeta se ha movido entera.\n"
            "Cambiar el tipo obliga a importarla otra vez.")), 0, wx.ALL, MARGEN)
        pie = wx.StdDialogButtonSizer()
        aceptar = wx.Button(self, wx.ID_OK, _("&Aceptar"))
        aceptar.SetDefault()
        pie.AddButton(aceptar)
        pie.AddButton(wx.Button(self, wx.ID_CANCEL, _("&Cancelar")))
        pie.Realize()
        contenedor.Add(pie, 0, wx.EXPAND | wx.ALL, MARGEN)
        self.SetSizerAndFit(contenedor)
        self.CentreOnParent()
        self.boton_elegir.Bind(wx.EVT_BUTTON, self._al_elegir)
        self.nombre.SetFocus()
        self.nombre.SelectAll()
        ayuda_opcion.enganchar(self)

    def _al_elegir(self, evento) -> None:
        """Abre el selector de carpetas en la ruta actual."""
        del evento
        with wx.DirDialog(self, _("Nueva ruta de «%s»") % self.fuente.nombre,
                          defaultPath=self.ruta.GetValue()) as dialogo:
            if dialogo.ShowModal() == wx.ID_OK:
                self.ruta.SetValue(dialogo.GetPath())
                self.ruta.SetFocus()

    def tipo_elegido(self) -> str:
        """El tipo marcado en el desplegable."""
        return self._tipos[max(0, self.tipo.GetSelection())][0]


# -- la ventana de gestión ---------------------------------------------------------


class DialogoFuentes(wx.Dialog):
    """Todas las carpetas y bibliotecas de calibre, para gestionarlas de varias en varias.

    :ivar cambios: Si se ha cambiado algo; la biblioteca se recarga al volver.
    :ivar importar_al_abrir: Fuentes que hay que importar nada más abrir.
    """

    COLUMNAS = (_("Nombre"), _("Tipo"), _("Libros"), _("Actualizada"), _("Estado"),
                _("Ruta"))
    ANCHOS = (200, 140, 80, 130, 110, 320)

    def __init__(self, padre: wx.Window, configuracion,
                 importar_al_abrir=None) -> None:
        super().__init__(padre, title=_("Bibliotecas y carpetas"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.configuracion = configuracion
        self.cambios = False
        self._voz = Voz(self)
        self._fuentes: list[datos.Fuente] = []

        contenedor = wx.BoxSizer(wx.VERTICAL)
        contenedor.Add(wx.StaticText(self, label=_(
            "De aquí salen los libros de la biblioteca. Marca una o varias (con Control o\n"
            "Mayús, o todas con Control+E) y elige qué hacer con ellas. Quitar una no borra\n"
            "nada del disco: solo dejan de aparecer sus libros.")), 0, wx.ALL, MARGEN)

        self.lista = fila_etiquetada(
            self, contenedor, _("&Bibliotecas y carpetas:"),
            lambda p: ListaAccesible(p, configuracion, _("Bibliotecas y carpetas"),
                                     size=(900, 220), style=0),
            margen=MARGEN, proporcion=1)
        rellenar_columnas(self.lista, self.COLUMNAS, self.ANCHOS)

        fila = wx.BoxSizer(wx.HORIZONTAL)
        self.boton_anadir = wx.Button(self, label=_("&Añadir carpeta o calibre..."))
        self.boton_actualizar = wx.Button(self, label=_("Act&ualizar las marcadas"))
        self.boton_actualizar_todas = wx.Button(self, label=_("Actualizar &todas"))
        self.boton_editar = wx.Button(self, label=_("&Editar..."))
        self.boton_quitar = wx.Button(self, label=_("&Quitar las marcadas..."))
        for boton in (self.boton_anadir, self.boton_actualizar,
                      self.boton_actualizar_todas, self.boton_editar, self.boton_quitar):
            fila.Add(boton, 0, wx.RIGHT, MARGEN)
        contenedor.Add(fila, 0, wx.LEFT | wx.RIGHT, MARGEN)

        fila2 = wx.BoxSizer(wx.HORIZONTAL)
        self.boton_abrir_carpeta = wx.Button(self, label=_("Abrir la ca&rpeta"))
        self.boton_readmitir = wx.Button(self, label=_("Devolver los &libros quitados..."))
        self.boton_copia = wx.Button(self, label=_("Copia de &seguridad..."))
        self.boton_restaurar = wx.Button(self, label=_("Restaurar una co&pia..."))
        for boton in (self.boton_abrir_carpeta, self.boton_readmitir, self.boton_copia,
                      self.boton_restaurar):
            fila2.Add(boton, 0, wx.RIGHT, MARGEN)
        contenedor.Add(fila2, 0, wx.ALL, MARGEN)

        self.estado, self.barra, self.boton_detener = crear_barra(self, contenedor)
        self.tarea = Tarea(self, self.barra, self.estado, self.boton_detener, configuracion)

        pie = wx.StdDialogButtonSizer()
        self.boton_cerrar = wx.Button(self, wx.ID_CANCEL, _("&Cerrar"))
        pie.AddButton(self.boton_cerrar)
        pie.Realize()
        contenedor.Add(pie, 0, wx.EXPAND | wx.ALL, MARGEN)
        self.SetSizerAndFit(contenedor)
        self.CentreOnParent()

        self.boton_anadir.Bind(wx.EVT_BUTTON, self._al_anadir)
        self.boton_actualizar.Bind(wx.EVT_BUTTON, lambda e: self._actualizar(False))
        self.boton_actualizar_todas.Bind(wx.EVT_BUTTON, lambda e: self._actualizar(True))
        self.boton_editar.Bind(wx.EVT_BUTTON, self._al_editar)
        self.boton_quitar.Bind(wx.EVT_BUTTON, self._al_quitar)
        self.boton_abrir_carpeta.Bind(wx.EVT_BUTTON, self._al_abrir_carpeta)
        self.boton_readmitir.Bind(wx.EVT_BUTTON, self._al_readmitir)
        self.boton_copia.Bind(wx.EVT_BUTTON, self._al_copia)
        self.boton_restaurar.Bind(wx.EVT_BUTTON, self._al_restaurar)
        self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._al_editar)
        self.lista.Bind(wx.EVT_KEY_DOWN, self._al_tecla_lista)
        self.Bind(wx.EVT_BUTTON, self._al_cerrar, id=wx.ID_CANCEL)
        self.Bind(wx.EVT_CLOSE, self._al_cerrar)

        self._refrescar()
        self.lista.SetFocus()
        ayuda_opcion.enganchar(self)
        if importar_al_abrir:
            wx.CallAfter(self._importar, list(importar_al_abrir))

    # -- la lista ------------------------------------------------------------

    def _refrescar(self, conservar=None) -> None:
        """Vuelve a leer las fuentes y las enseña."""
        marcadas = set(conservar if conservar is not None
                       else [f.id for f in self._marcadas()])
        conexion = datos.conectar()
        try:
            self._fuentes = datos.fuentes(conexion)
        finally:
            conexion.close()
        self.lista.DeleteAllItems()
        if not self._fuentes:
            self.lista.InsertItem(0, _("(Todavía no hay ninguna; usa «Añadir carpeta o "
                                       "calibre»)"))
            return
        for numero, fuente in enumerate(self._fuentes):
            self.lista.InsertItem(numero, fuente.nombre)
            self.lista.SetItem(numero, 1, _("Biblioteca de calibre") if fuente.es_calibre
                               else _("Carpeta"))
            self.lista.SetItem(numero, 2, str(fuente.libros))
            self.lista.SetItem(numero, 3, fuente.fecha_legible()
                               or (_("pendiente") if fuente.pendiente else ""))
            self.lista.SetItem(numero, 4, _("disponible") if fuente.disponible
                               else _("no disponible"))
            self.lista.SetItem(numero, 5, fuente.ruta)
            if fuente.id in marcadas:
                self.lista.Select(numero)
        primera = self.lista.GetFirstSelected()
        self.lista.Focus(primera if primera >= 0 else 0)
        if primera < 0:
            self.lista.Select(0)

    def _marcadas(self) -> list[datos.Fuente]:
        """Las fuentes seleccionadas, o la que tenga el foco si no hay ninguna."""
        elegidas = []
        if not self._fuentes:
            return elegidas
        indice = self.lista.GetFirstSelected()
        while indice != -1:
            if 0 <= indice < len(self._fuentes):
                elegidas.append(self._fuentes[indice])
            indice = self.lista.GetNextSelected(indice)
        if not elegidas:
            foco = self.lista.GetFocusedItem()
            if 0 <= foco < len(self._fuentes):
                elegidas.append(self._fuentes[foco])
        return elegidas

    def _al_tecla_lista(self, evento: wx.KeyEvent) -> None:
        """Control+E marca todas; Suprimir quita las marcadas."""
        codigo = evento.GetKeyCode()
        if evento.GetModifiers() == wx.MOD_CONTROL and codigo in (ord("E"), ord("A")):
            for indice in range(len(self._fuentes)):
                self.lista.Select(indice)
            self._voz.decir(_n("%d marcada.", "%d marcadas.", len(self._fuentes))
                            % len(self._fuentes))
            return
        if evento.GetModifiers() == wx.MOD_NONE and codigo == wx.WXK_DELETE:
            self._al_quitar(None)
            return
        evento.Skip()

    # -- importar ------------------------------------------------------------

    def _importar(self, ids) -> None:
        """Importa o actualiza esas fuentes en segundo plano."""
        if not ids:
            return
        self.cambios = True
        self.tarea.lanzar(trabajo_importar(ids, self.configuracion), self._importado,
                          _n("Actualizando %d fuente...", "Actualizando %d fuentes...",
                             len(ids)) % len(ids))

    def _importado(self, resumenes, error: str) -> None:
        """Al terminar: se refresca la lista y se enseña el resumen."""
        self._refrescar()
        self.estado.SetLabel(_("Terminado."))
        mostrar_resumen(self, resumenes, error)
        self.lista.SetFocus()

    def _al_anadir(self, evento) -> None:
        """Añade una carpeta o una biblioteca de calibre y la importa."""
        del evento
        if self.tarea.ocupada():
            return
        numero = anadir_carpeta(self, self.configuracion, self._voz)
        if numero is None:
            return
        self._refrescar(conservar=[numero])
        self._importar([numero])

    def _actualizar(self, todas: bool) -> None:
        """Actualiza las marcadas o todas."""
        elegidas = self._fuentes if todas else self._marcadas()
        if not elegidas:
            self._voz.decir(_("No hay ninguna que actualizar."))
            return
        self._importar([f.id for f in elegidas])

    # -- editar --------------------------------------------------------------

    def _al_editar(self, evento) -> None:
        """Cambia el nombre, la ruta o el tipo de la fuente con el foco."""
        del evento
        if self.tarea.ocupada():
            return
        elegidas = self._marcadas()
        if not elegidas:
            return
        fuente = elegidas[0]
        with DialogoEditarFuente(self, fuente) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                return
            nombre = dialogo.nombre.GetValue().strip()
            ruta = os.path.normpath(dialogo.ruta.GetValue().strip() or fuente.ruta)
            tipo = dialogo.tipo_elegido()
        if datos.clave(ruta) != datos.clave(fuente.ruta) and not os.path.isdir(ruta):
            if wx.MessageBox(_("Ahora mismo no hay ninguna carpeta en:\n\n%s\n\n"
                               "¿Cambiar la ruta de todas formas?") % ruta,
                             _("Editar"), wx.YES_NO | wx.ICON_QUESTION, self) != wx.YES:
                return
        conexion = datos.conectar()
        try:
            otra = datos.fuente_por_ruta(conexion, ruta)
            if otra is not None and otra.id != fuente.id:
                wx.MessageBox(_("Esa ruta ya es la de «%s».") % otra.nombre, _("Editar"),
                              wx.OK | wx.ICON_INFORMATION, self)
                return
            movidos = datos.editar_fuente(conexion, fuente.id, nombre, ruta)
            if tipo != fuente.tipo:
                conexion.execute("UPDATE fuentes SET tipo=? WHERE id=?", (tipo, fuente.id))
                conexion.commit()
        finally:
            conexion.close()
        self.cambios = True
        self._refrescar(conservar=[fuente.id])
        if tipo != fuente.tipo:
            self._importar([fuente.id])
        elif movidos:
            self._voz.decir(_n("Ruta cambiada; %d libro recolocado.",
                               "Ruta cambiada; %d libros recolocados.", movidos) % movidos)
        else:
            self._voz.decir(_("Cambios guardados."))

    # -- quitar --------------------------------------------------------------

    def _al_quitar(self, evento) -> None:
        """Quita las fuentes marcadas con todos sus libros."""
        del evento
        if self.tarea.ocupada():
            return
        elegidas = self._marcadas()
        if not elegidas:
            return
        libros = sum(f.libros for f in elegidas)
        if len(elegidas) == 1:
            pregunta = (_("¿Quitar «%(nombre)s» de la biblioteca, con sus %(libros)d "
                          "libros?") % {"nombre": elegidas[0].nombre, "libros": libros})
        else:
            pregunta = (_("¿Quitar %(fuentes)d bibliotecas y carpetas, con %(libros)d "
                          "libros en total?") % {"fuentes": len(elegidas), "libros": libros})
        pregunta += "\n\n" + _("No se borra ningún archivo del disco ni nada de lo que "
                               "hayas hecho en los libros: solo dejan de aparecer aquí.")
        if wx.MessageBox(pregunta, _("Quitar"), wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
                         self) != wx.YES:
            return
        ids = [f.id for f in elegidas]
        nombres = ", ".join(f.nombre for f in elegidas)

        def trabajo(progreso, cancelado):
            del cancelado
            progreso(0, 0, _("Quitando..."))
            conexion = datos.conectar()
            try:
                return datos.quitar_fuentes(conexion, ids)
            finally:
                conexion.close()

        def hecho(quitados, error: str) -> None:
            self.cambios = True
            self._refrescar(conservar=[])
            if error:
                self.estado.SetLabel(_("No se ha podido quitar: %s") % error)
                self._voz.decir(self.estado.GetLabel())
                return
            mensaje = (_n("Quitado: %(nombres)s. Han salido %(libros)d libro de la "
                          "biblioteca.",
                          "Quitado: %(nombres)s. Han salido %(libros)d libros de la "
                          "biblioteca.", quitados or 0)
                       % {"nombres": nombres, "libros": quitados or 0})
            self.estado.SetLabel(mensaje)
            self._voz.decir(mensaje)
            self.lista.SetFocus()

        self.tarea.lanzar(trabajo, hecho, _("Quitando de la biblioteca..."))

    def _al_readmitir(self, evento) -> None:
        """Olvida los libros quitados a mano para que vuelvan al actualizar."""
        del evento
        conexion = datos.conectar()
        try:
            cuantos = len(datos.excluidas(conexion))
            if not cuantos:
                self._voz.decir(_("No has quitado ningún libro a mano."))
                return
            if wx.MessageBox(
                    _n("Has quitado %d libro a mano. ¿Devolverlo a la biblioteca?\n\n"
                       "Vuelve al actualizar su biblioteca o carpeta; se actualizan ahora.",
                       "Has quitado %d libros a mano. ¿Devolverlos a la biblioteca?\n\n"
                       "Vuelven al actualizar sus bibliotecas y carpetas; se actualizan "
                       "ahora.", cuantos) % cuantos,
                    _("Devolver libros"), wx.YES_NO | wx.ICON_QUESTION, self) != wx.YES:
                return
            fuentes_afectadas = {fila[0] for fila in conexion.execute(
                "SELECT DISTINCT fuente FROM excluidos WHERE fuente<>0")}
            datos.readmitir_todos(conexion)
        finally:
            conexion.close()
        self.cambios = True
        if fuentes_afectadas:
            self._importar(sorted(fuentes_afectadas))
        else:
            self._voz.decir(_("Hecho. Vuelven a estar en la biblioteca."))

    def _al_abrir_carpeta(self, evento) -> None:
        """Abre en el Explorador la carpeta de la fuente con el foco."""
        del evento
        elegidas = self._marcadas()
        if not elegidas:
            return
        if not elegidas[0].disponible:
            self._voz.decir(_("Esa carpeta no está disponible ahora."))
            return
        try:
            os.startfile(elegidas[0].ruta)                   # noqa: S606
        except OSError as error:
            self._voz.decir(_("No se ha podido abrir: %s") % error)

    # -- copia de seguridad ----------------------------------------------------

    def _al_copia(self, evento) -> None:
        """Guarda en un ZIP la biblioteca y lo hecho en cada libro."""
        del evento
        if self.tarea.ocupada():
            return
        nombre = "biblioteca_%s.zip" % time.strftime("%Y-%m-%d")
        with wx.FileDialog(self, _("Guardar la copia de seguridad"), defaultFile=nombre,
                           wildcard=_("Copia de la biblioteca (*.zip)|*.zip"),
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                return
            destino = dialogo.GetPath()
        # Lo que esté en memoria se escribe antes, o la copia saldría con las
        # posiciones de la última vez que se guardó.
        self.configuracion.guardar()

        def trabajo(progreso, cancelado):
            del cancelado
            progreso(0, 0, _("Haciendo la copia de seguridad..."))
            return datos.copia_de_seguridad(destino, progreso=progreso)

        def hecho(libros, error: str) -> None:
            if error:
                mensaje = _("No se ha podido hacer la copia: %s") % error
            else:
                mensaje = (_("Copia guardada, con %(libros)d libros, en:\n%(ruta)s")
                           % {"libros": libros or 0, "ruta": destino})
            self.estado.SetLabel(mensaje.replace("\n", " "))
            wx.MessageBox(mensaje, _("Copia de seguridad"),
                          wx.OK | (wx.ICON_ERROR if error else wx.ICON_INFORMATION), self)

        self.tarea.lanzar(trabajo, hecho, _("Haciendo la copia de seguridad..."))

    def _al_restaurar(self, evento) -> None:
        """Pone una copia de seguridad en lugar de la biblioteca actual."""
        del evento
        if self.tarea.ocupada():
            return
        with wx.FileDialog(self, _("Elegir la copia de seguridad"),
                           wildcard=_("Copia de la biblioteca (*.zip)|*.zip"),
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                return
            origen = dialogo.GetPath()
        try:
            ficha_copia = datos.leer_copia(origen)
        except Exception as error:
            wx.MessageBox(_("Ese archivo no es una copia de la biblioteca:\n\n%s") % error,
                          _("Restaurar"), wx.OK | wx.ICON_ERROR, self)
            return
        fecha = ficha_copia.get("fecha")
        cuando = time.strftime("%d/%m/%Y %H:%M", time.localtime(fecha)) if fecha else "?"
        pregunta = (_("La copia es del %(fecha)s y tiene %(libros)s libros.\n\n"
                      "Restaurarla sustituye la biblioteca actual") %
                    {"fecha": cuando, "libros": ficha_copia.get("libros", "?")})
        if ficha_copia.get("documentos"):
            pregunta += _(" y también las posiciones de lectura, los marcadores, las notas "
                          "y las colecciones")
        pregunta += _(".\n\n¿Restaurarla?")
        if wx.MessageBox(pregunta, _("Restaurar"),
                         wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self) != wx.YES:
            return
        try:
            libros = datos.restaurar_copia(origen)
            self.configuracion.recargar_documentos()
        except Exception as error:
            registrar_excepcion(log, "No se ha podido restaurar la copia", error)
            wx.MessageBox(_("No se ha podido restaurar la copia:\n\n%s") % error,
                          _("Restaurar"), wx.OK | wx.ICON_ERROR, self)
            return
        self.cambios = True
        self._refrescar(conservar=[])
        mensaje = _("Copia restaurada. La biblioteca tiene %d libros.") % libros
        self.estado.SetLabel(mensaje)
        self._voz.decir(mensaje)

    # -- cerrar ----------------------------------------------------------------

    def _al_cerrar(self, evento) -> None:
        """Si hay algo en marcha, se pregunta antes de cortarlo."""
        if self.tarea.activa:
            if wx.MessageBox(_("Hay un trabajo en marcha. Si cierras, se detiene y lo "
                               "hecho hasta ahora se queda guardado.\n\n¿Cerrar?"),
                             _("Bibliotecas y carpetas"),
                             wx.YES_NO | wx.ICON_QUESTION, self) != wx.YES:
                return
            self.tarea.parar.set()
        if self.IsModal():
            self.EndModal(wx.ID_CANCEL)
        else:
            evento.Skip()


def abrir_carpeta_de(ruta: str) -> bool:
    """Abre el Explorador en la carpeta de un archivo, con el archivo marcado."""
    try:
        subprocess.Popen(["explorer", "/select,", os.path.normpath(ruta)])  # noqa: S603,S607
        return True
    except OSError as error:                                 # pragma: no cover
        log.info("No se ha podido abrir el Explorador: %s", error)
        return False
