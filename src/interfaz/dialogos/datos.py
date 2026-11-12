# -*- coding: utf-8 -*-
"""Gestión de lo que el programa va guardando de cada libro.

Al leer, el programa deja rastro: el análisis en la caché para que el libro
vuelva a abrirse al instante, las descripciones que hizo la inteligencia
artificial, los marcadores y las notas, y por dónde se iba leyendo.  Todo eso
es útil, pero no es igual de valioso ni cuesta lo mismo rehacerlo:

* La **caché** se regenera sola con solo volver a abrir el libro.  Ocupa
  bastante y se puede tirar sin pensarlo.
* Las **descripciones** costaron una petición a la inteligencia artificial cada
  una, y algunas costaron dinero.  Perderlas duele.
* Los **marcadores y las notas** los puso una persona a mano.  No se rehacen.
* La **posición de lectura** es pequeña pero es lo que evita tener que buscar
  por dónde ibas en un libro de mil páginas.

Por eso aquí no hay un único botón de borrar.  Hay una lista de libros y, al
lado, casillas para elegir **qué** se quita de cada uno: se puede tirar la
caché de un libro y conservar sus descripciones, que es justo lo que se quiere
cuando un libro se ha analizado mal y hay que volver a abrirlo.

La lista de casillas es :class:`~interfaz.listas.ListaCasillas`, que anuncia el
estado de cada una al marcarla; una hilera de opciones sueltas sería más lenta
de recorrer y más fácil de perder de vista.
"""

from __future__ import annotations

import wx

from interfaz.accesible import etiquetar
from interfaz.anuncios import Voz
from interfaz.dialogos import ayuda_opcion
from interfaz.dialogos.espera import ejecutar_esperando
from interfaz.listas import ListaAccesible, ListaCasillas, rellenar_columnas
from nucleo import cache, descripciones
from nucleo.idioma import _, _n
from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

MARGEN = 8

#: Qué se puede borrar de un libro.  El orden es el de menos a más valioso, que
#: es el orden en el que alguien decide qué tirar.
COSAS = ("cache", "descripciones", "posicion", "marcadores")


def nombres_de_cosa() -> dict[str, str]:
    """Cómo se llama cada cosa que se guarda, ya traducido."""
    return {
        "cache": _("La caché del análisis (se rehace sola al volver a abrir el documento)"),
        "descripciones": _("Las descripciones de las imágenes hechas con IA"),
        "posicion": _("La posición de lectura y el historial de saltos"),
        "marcadores": _("Los marcadores y las notas (no se pueden recuperar)"),
    }


class Libro:
    """Lo que el programa guarda de un libro, ya contado y medido."""

    __slots__ = ("ruta", "titulo", "existe", "cache_cuantas", "cache_bytes",
                 "descripciones", "descripciones_bytes", "marcadores", "posicion")

    def __init__(self, ruta: str, datos) -> None:
        from pathlib import Path

        self.ruta = ruta
        self.titulo = datos.titulo or Path(ruta).stem
        self.existe = Path(ruta).exists()
        self.cache_cuantas, self.cache_bytes = cache.datos_de(ruta)
        self.descripciones, self.descripciones_bytes = descripciones.datos_de(ruta)
        self.marcadores = len(datos.marcadores or [])
        self.posicion = int(datos.posicion or 0)

    @property
    def bytes(self) -> int:
        """Lo que ocupa en total todo lo guardado de este libro."""
        return self.cache_bytes + self.descripciones_bytes

    def tiene(self, cosa: str) -> bool:
        """Si hay algo de ese tipo que borrar."""
        return {
            "cache": self.cache_cuantas > 0,
            "descripciones": self.descripciones > 0,
            "marcadores": self.marcadores > 0,
            "posicion": self.posicion > 0,
        }.get(cosa, False)


def _medida(bytes_: int) -> str:
    """Escribe un tamaño como lo diría una persona."""
    if bytes_ <= 0:
        return "-"
    if bytes_ < 1024:
        return _("%d bytes") % bytes_
    if bytes_ < 1024 * 1024:
        return _("%.0f KB") % (bytes_ / 1024)
    return _("%.1f MB") % (bytes_ / 1048576)


class DialogoDatos(wx.Dialog):
    """Ventana para ver y limpiar lo que el programa guarda de cada libro.

    :param padre: Ventana principal.
    :param configuracion: Preferencias, de donde salen los libros recordados.
    :param ruta_abierta: Libro abierto ahora mismo, para dejarlo señalado.
    """

    COLUMNAS = (_("Documento"), _("Caché"), _("Descripciones"), _("Marcadores"),
                _("Posición"), _("Archivo"))
    ANCHOS = (250, 80, 110, 90, 80, 320)

    def __init__(self, padre: wx.Window, configuracion, ruta_abierta: str = "") -> None:
        super().__init__(padre, title=_("Datos guardados"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.configuracion = configuracion
        self.ruta_abierta = ruta_abierta
        self._voz = Voz(self)
        self.libros: list[Libro] = []
        self.hubo_cambios = False

        contenedor = wx.BoxSizer(wx.VERTICAL)
        contenedor.Add(wx.StaticText(self, label=_(
            "Aquí está todo lo que el programa ha guardado de cada libro. Elige los libros,\n"
            "marca qué quieres quitarles y pulsa «Borrar lo marcado»."
        )), 0, wx.ALL, MARGEN)

        self.resumen = wx.StaticText(self, label="")
        contenedor.Add(self.resumen, 0, wx.LEFT | wx.RIGHT, MARGEN)

        contenedor.Add(wx.StaticText(self, label=_("&Documentos (se pueden elegir varios):")), 0,
                       wx.LEFT | wx.RIGHT | wx.TOP, MARGEN)
        self.lista = ListaAccesible(
            self, configuracion=configuracion, nombre=_("Documentos con datos guardados"),
            size=(880, 240), style=wx.LC_HRULES)
        rellenar_columnas(self.lista, self.COLUMNAS, self.ANCHOS)
        contenedor.Add(self.lista, 1, wx.EXPAND | wx.ALL, MARGEN)

        contenedor.Add(wx.StaticText(self, label=_("&Qué quitar de los documentos elegidos:")), 0,
                       wx.LEFT | wx.RIGHT | wx.TOP, MARGEN)
        nombres = nombres_de_cosa()
        self.casillas = etiquetar(ListaCasillas(
            self, choices=[nombres[cosa] for cosa in COSAS], size=(-1, 110)),
            _("Qué borrar"))
        # De entrada solo la caché: es lo único que se rehace solo, así que es
        # lo único que se puede marcar por omisión sin arriesgar nada.
        self.casillas.Check(COSAS.index("cache"), True)
        contenedor.Add(self.casillas, 0, wx.EXPAND | wx.ALL, MARGEN)

        fila = wx.BoxSizer(wx.HORIZONTAL)
        self.boton_borrar = wx.Button(self, label=_("&Borrar lo marcado"))
        self.boton_sobrantes = wx.Button(self, label=_("Limpiar lo &sobrante"))
        self.boton_actualizar = wx.Button(self, label=_("&Actualizar"))
        for boton in (self.boton_borrar, self.boton_sobrantes, self.boton_actualizar):
            fila.Add(boton, 0, wx.ALL, 4)
        contenedor.Add(fila, 0, wx.LEFT | wx.RIGHT, MARGEN - 4)

        pie = wx.StdDialogButtonSizer()
        cerrar = wx.Button(self, wx.ID_OK, _("&Cerrar"))
        cerrar.SetDefault()
        pie.AddButton(cerrar)
        pie.Realize()
        contenedor.Add(pie, 0, wx.EXPAND | wx.ALL, MARGEN)
        self.SetSizerAndFit(contenedor)
        self.CentreOnParent()

        self.boton_borrar.Bind(wx.EVT_BUTTON, self._al_borrar)
        self.boton_sobrantes.Bind(wx.EVT_BUTTON, self._al_limpiar_sobrantes)
        self.boton_actualizar.Bind(wx.EVT_BUTTON, lambda evento: self._recargar())
        self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar_tecla)
        ayuda_opcion.enganchar(self)
        self._recargar()
        self.lista.SetFocus()

    # -- carga ---------------------------------------------------------------

    def _recargar(self) -> None:
        """Vuelve a mirar el disco y rehace la lista."""
        ok, resultado = ejecutar_esperando(
            self, _("Mirando qué hay guardado..."), self._recoger)
        self.libros = resultado if ok and isinstance(resultado, list) else []
        self._pintar()

    def _recoger(self) -> list[Libro]:
        """Reúne los datos de todos los libros recordados.

        Va en un hilo aparte porque abre y mide cada archivo de la caché, y con
        una biblioteca grande eso no es instantáneo.
        """
        return [Libro(ruta, datos)
                for ruta, datos in self.configuracion.libros_recordados()]

    def _pintar(self) -> None:
        """Vuelca los libros en la lista."""
        self.lista.DeleteAllItems()
        for numero, libro in enumerate(self.libros):
            titulo = libro.titulo
            if not libro.existe:
                titulo = _("%s (el archivo ya no está)") % titulo
            fila = self.lista.InsertItem(numero, titulo)
            self.lista.SetItem(fila, 1, _medida(libro.cache_bytes))
            self.lista.SetItem(fila, 2, str(libro.descripciones) if libro.descripciones else "-")
            self.lista.SetItem(fila, 3, str(libro.marcadores) if libro.marcadores else "-")
            self.lista.SetItem(fila, 4, _("sí") if libro.posicion else "-")
            self.lista.SetItem(fila, 5, libro.ruta)
        if self.libros:
            self.lista.Select(0)
            self.lista.Focus(0)
        self._actualizar_resumen()
        self._actualizar_botones()

    def _actualizar_resumen(self) -> None:
        """Escribe cuánto ocupa todo y cuánto sobra."""
        total = sum(libro.bytes for libro in self.libros)
        sobrantes = sum(1 for libro in self.libros if not libro.existe)
        texto = _n("%d documento, %s en total.", "%d documentos, %s en total.",
                   len(self.libros)) % (len(self.libros), _medida(total))
        if sobrantes:
            texto += " " + _("%d ya no están en el disco.") % sobrantes
        self.resumen.SetLabel(texto)

    def _actualizar_botones(self) -> None:
        """Apaga lo que no tiene nada que hacer."""
        self.boton_borrar.Enable(bool(self.libros))
        self.boton_sobrantes.Enable(any(not libro.existe for libro in self.libros))

    # -- selección -----------------------------------------------------------

    def _elegidos(self) -> list[Libro]:
        """Libros seleccionados en la lista."""
        elegidos = []
        indice = self.lista.GetFirstSelected()
        while indice >= 0:
            if 0 <= indice < len(self.libros):
                elegidos.append(self.libros[indice])
            indice = self.lista.GetNextSelected(indice)
        return elegidos

    def _marcadas(self) -> list[str]:
        """Qué cosas se han marcado para borrar."""
        return [COSAS[indice] for indice in self.casillas.marcados()]

    # -- acciones ------------------------------------------------------------

    def _al_borrar(self, evento) -> None:
        """Borra de los libros elegidos lo que esté marcado."""
        libros = self._elegidos()
        cosas = self._marcadas()
        if not libros:
            self._voz.decir(_("Elige antes al menos un documento."))
            return
        if not cosas:
            self._voz.decir(_("Marca antes qué quieres borrar."))
            return

        nombres = nombres_de_cosa()
        detalle = "\n".join("• " + nombres[cosa] for cosa in cosas)
        aviso = _n("Se va a borrar esto de %d libro:\n\n%s\n\n¿Seguir?",
                   "Se va a borrar esto de %d libros:\n\n%s\n\n¿Seguir?",
                   len(libros)) % (len(libros), detalle)
        if "marcadores" in cosas:
            aviso += "\n\n" + _("Los marcadores y las notas no se pueden recuperar.")
        if wx.MessageBox(aviso, _("Borrar datos guardados"),
                         wx.YES_NO | wx.ICON_QUESTION | wx.NO_DEFAULT, self) != wx.YES:
            return

        ok, resultado = ejecutar_esperando(
            self, _("Borrando..."), lambda: self._borrar(libros, cosas))
        if not ok:
            wx.MessageBox(_("No se ha podido borrar:\n\n%s") % resultado,
                          _("Borrar datos guardados"), wx.OK | wx.ICON_ERROR, self)
            return
        self.hubo_cambios = True
        self.configuracion.guardar()
        wx.MessageBox(_("Listo. %s") % resultado, _("Borrar datos guardados"),
                      wx.OK | wx.ICON_INFORMATION, self)
        self._recargar()

    def _borrar(self, libros: list[Libro], cosas: list[str]) -> str:
        """Hace el borrado y devuelve un resumen de lo hecho."""
        cuentas = dict.fromkeys(cosas, 0)
        for libro in libros:
            if "cache" in cosas:
                cuentas["cache"] += cache.olvidar(libro.ruta)
            if "descripciones" in cosas:
                cuentas["descripciones"] += 1 if descripciones.olvidar_libro(libro.ruta) else 0
            if "marcadores" in cosas or "posicion" in cosas:
                self.configuracion.olvidar_documento(
                    libro.ruta,
                    marcadores="marcadores" in cosas,
                    posicion="posicion" in cosas)
                for cosa in ("marcadores", "posicion"):
                    if cosa in cosas:
                        cuentas[cosa] += 1
        partes = []
        if cuentas.get("cache"):
            partes.append(_("%d entradas de caché") % cuentas["cache"])
        if cuentas.get("descripciones"):
            partes.append(_("descripciones de %d documentos") % cuentas["descripciones"])
        if cuentas.get("marcadores"):
            partes.append(_n("marcadores de %d documento", "marcadores de %d documentos",
                             cuentas["marcadores"]) % cuentas["marcadores"])
        if cuentas.get("posicion"):
            partes.append(_("posición de %d documentos") % cuentas["posicion"])
        return ", ".join(partes) if partes else _("no había nada que borrar")

    def _al_limpiar_sobrantes(self, evento) -> None:
        """Tira la caché de los libros que ya no están en el disco."""
        if wx.MessageBox(
                _("Se va a borrar la caché de los libros que ya no están en el disco.\n\n"
                  "Los marcadores y las descripciones se conservan, por si el libro vuelve "
                  "a aparecer.\n\n¿Seguir?"),
                _("Limpiar lo sobrante"),
                wx.YES_NO | wx.ICON_QUESTION, self) != wx.YES:
            return
        ok, resultado = ejecutar_esperando(self, _("Limpiando..."), self._limpiar)
        if ok:
            self.hubo_cambios = True
            wx.MessageBox(_("Se han borrado %d entradas sobrantes.") % resultado,
                          _("Limpiar lo sobrante"), wx.OK | wx.ICON_INFORMATION, self)
        self._recargar()

    def _limpiar(self) -> int:
        """Borra las entradas de caché sin libro.  Devuelve cuántas."""
        borradas = 0
        for _origen, archivo, _tamano in cache.sobrantes():
            try:
                archivo.unlink()
                archivo.with_suffix(".origen").unlink(missing_ok=True)
                borradas += 1
            except OSError as error:
                log.warning("No se ha podido borrar %s: %s", archivo, error)
        return borradas

    def _al_pulsar_tecla(self, evento: wx.KeyEvent) -> None:
        """Escape cierra; Suprimir borra lo marcado."""
        codigo = evento.GetKeyCode()
        if codigo == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_OK)
            return
        if codigo == wx.WXK_DELETE and self.FindFocus() is self.lista:
            self._al_borrar(None)
            return
        evento.Skip()
