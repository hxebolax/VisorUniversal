# -*- coding: utf-8 -*-
"""La ventana de la biblioteca: todos los libros, y buscar en todos.

Arriba, **los libros**, con las columnas que se elijan (título, autor, serie,
colección, formato, por dónde va la lectura...), agrupados y ordenados como se
quiera y filtrados escribiendo, sin pulsar nada.  Abajo, **lo encontrado** al
buscar en todos a la vez, con el trozo de texto donde aparece y en qué página
de qué libro está.

Abrir un resultado abre el libro **en ese punto**, no en el principio.  Es lo
que convierte la búsqueda en algo aprovechable: se busca una cita, se pulsa
Intro y se está leyendo el párrafo donde estaba.

Con bibliotecas grandes, la ventana no se cuelga
------------------------------------------------

La ventana se abre al momento y los libros se cargan **después**, en otro hilo,
con su barra de avance; mientras tanto se puede ir escribiendo en el filtro.
La lista es virtual —solo se pide el texto de las filas que se ven—, así que
ciento noventa mil libros caben igual que diez.  Añadir una carpeta o una
biblioteca de calibre también se hace en segundo plano: se puede seguir
usando la ventana, el avance se dice cada pocos segundos y al final se enseña
un resumen de lo hecho.

La búsqueda tiene dos velocidades, y la ventana lo dice
-------------------------------------------------------

Los libros ya analizados están en la caché y se buscan al instante.  Los que no
se han abierto nunca hay que analizarlos, y eso tarda —un PDF grande, bastante—.
Por eso la primera búsqueda mira solo lo que ya está y después ofrece mirar en
el resto, con su barra de progreso y su botón de detener.  Así una búsqueda
normal es inmediata y la exhaustiva es una decisión consciente.
"""

from __future__ import annotations

import os
import time

import wx

from interfaz.accesible import fila_etiquetada
from interfaz.anuncios import Voz
from interfaz.dialogos import ayuda_opcion
from interfaz.dialogos.biblioteca_gestor import (DialogoFuentes, Tarea, abrir_carpeta_de,
                                                 anadir_carpeta, crear_barra,
                                                 mostrar_resumen, trabajo_importar)
from interfaz.listas import ListaAccesible, ListaCasillas, ListaVirtual, rellenar_columnas
from nucleo import biblioteca
from nucleo import biblioteca_ficha as fichas
from nucleo import biblioteca_datos as datos
from nucleo.idioma import _, _n
from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

MARGEN = 8

#: Ancho de cada columna de la lista de libros, en píxeles.
ANCHOS = {"titulo": 300, "autor": 190, "serie": 170, "coleccion": 130,
          "etiquetas": 170, "editorial": 140, "publicado": 80, "idioma": 90,
          "formato": 70, "tamano": 80, "valoracion": 100, "fuente": 140,
          "anadido": 90, "lectura": 100, "ruta": 420}

#: Milisegundos que se espera tras la última tecla del filtro antes de filtrar.
#: Con ciento noventa mil libros, filtrar en cada pulsación haría que escribir
#: deprisa se notara a trompicones.
ESPERA_FILTRO = 250


class DialogoBiblioteca(wx.Dialog):
    """Todos los libros del usuario, con búsqueda en todos a la vez."""

    COLUMNAS_RESULTADOS = (_("Libro"), _("Punto"), _("Texto"))
    ANCHOS_RESULTADOS = (230, 110, 380)

    def __init__(self, padre: wx.Window) -> None:
        super().__init__(padre, title=_("Biblioteca"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.ventana = padre
        self.configuracion = padre.configuracion
        self._voz = Voz(self)
        #: Lo que se ha elegido abrir: ``(ruta, posición)``.
        self.elegido: tuple[str, int] | None = None

        self.libros: list = []
        self._visibles: list = []
        self._fuentes: list = []
        self._nombres_fuente: dict[int, str] = {}
        self._cargado = False
        self._resultados: list = []
        #: Índice de significados, si se ha llegado a construir en esta sesión.
        self._significados = None
        self._columnas = biblioteca.columnas_elegidas(
            self.configuracion.obtener("biblioteca_columnas", None))
        claves_agrupar = [c for c, _n in biblioteca.AGRUPACIONES]
        self._agrupar = str(self.configuracion.obtener("biblioteca_agrupar", "coleccion"))
        if self._agrupar not in claves_agrupar:
            self._agrupar = "coleccion"
        claves_orden = [c for c, _n in biblioteca.ORDENES]
        self._orden = str(self.configuracion.obtener("biblioteca_orden", "titulo"))
        if self._orden not in claves_orden:
            self._orden = "titulo"
        #: Claves de los grupos en el orden de la lista; la primera, vacía, es «Todos».
        self._grupos: list[str] = [""]
        self._filas_grupo: list[tuple[str, int]] = []
        #: Los libros de cada grupo, ya repartidos: ``{clave: [libros]}``.
        self._reparto: dict = {}
        self._espera_filtro = None
        self._espera_grupo = None
        self._sin_eventos_grupo = False

        self.SetSize((1000, 740))
        contenedor = wx.BoxSizer(wx.VERTICAL)

        self.resumen = wx.StaticText(self, label=_("Cargando la biblioteca..."))
        contenedor.Add(self.resumen, 0, wx.ALL, MARGEN)

        # Dos columnas, como el explorador de etiquetas de calibre: a la
        # izquierda los grupos (autores, series, etiquetas...) y a la derecha
        # los libros del grupo elegido.  Los grupos van en una lista virtual y
        # no en un desplegable: un desplegable de Windows con sesenta mil
        # autores tarda segundos en llenarse.
        columnas = wx.BoxSizer(wx.HORIZONTAL)
        izquierda = wx.BoxSizer(wx.VERTICAL)
        derecha = wx.BoxSizer(wx.VERTICAL)
        self.agrupar = fila_etiquetada(
            self, izquierda, _("Agr&upar por:"),
            lambda p: wx.Choice(p, choices=[n for _c, n in biblioteca.AGRUPACIONES]),
            margen=MARGEN)
        self.agrupar.SetSelection(claves_agrupar.index(self._agrupar))
        self.grupo = fila_etiquetada(
            self, izquierda, _("&Grupo:"),
            lambda p: ListaVirtual(p, self.configuracion, _("Grupos"), size=(270, 280),
                                   multiple=False),
            margen=MARGEN, proporcion=1)
        rellenar_columnas(self.grupo, (_("Grupo"), _("Libros")), (190, 60))
        self.grupo.poner_filas(1, lambda fila, columna: _("Todos") if columna == 0 else "")

        self.orden = fila_etiquetada(
            self, derecha, _("&Ordenar por:"),
            lambda p: wx.Choice(p, choices=[n for _c, n in biblioteca.ORDENES]),
            margen=MARGEN, horizontal=True)
        self.orden.SetSelection(claves_orden.index(self._orden))

        self.filtro = fila_etiquetada(
            self, derecha, _("&Filtrar por título, autor, serie, etiqueta o colección:"),
            lambda p: wx.TextCtrl(p), margen=MARGEN, horizontal=True, proporcion=1)

        self.lista = fila_etiquetada(
            self, derecha, _("&Libros:"),
            lambda p: ListaVirtual(p, self.configuracion, _("Libros de la biblioteca"),
                                   size=(700, 280)),
            margen=MARGEN, proporcion=1)
        columnas.Add(izquierda, 0, wx.EXPAND)
        columnas.Add(derecha, 1, wx.EXPAND)
        contenedor.Add(columnas, 1, wx.EXPAND)
        rellenar_columnas(self.lista,
                          tuple(dict(biblioteca.COLUMNAS)[c] for c in self._columnas),
                          tuple(ANCHOS.get(c, 120) for c in self._columnas))
        self.lista.poner_filas(1, lambda fila, columna:
                               _("(Cargando la biblioteca...)") if columna == 0 else "")

        self.busqueda = fila_etiquetada(
            self, contenedor, _("&Buscar en todos los libros:"),
            lambda p: wx.TextCtrl(p, style=wx.TE_PROCESS_ENTER),
            margen=MARGEN, horizontal=True, proporcion=1)

        fila = wx.BoxSizer(wx.HORIZONTAL)
        self.boton_buscar = wx.Button(self, label=_("Buscar en los anali&zados"))
        self.boton_buscar_todo = wx.Button(self, label=_("Buscar en &todos (tarda)"))
        # Ampliar por significado es **otro botón** y no una casilla que
        # cambie los otros dos: así lo que devuelve cada búsqueda es siempre
        # previsible, y quien no lo use no tiene que enterarse de que existe.
        self.boton_relacionadas = wx.Button(self, label=_("Palabras &relacionadas..."))
        for boton in (self.boton_buscar, self.boton_buscar_todo, self.boton_relacionadas):
            fila.Add(boton, 0, wx.RIGHT, MARGEN)
        contenedor.Add(fila, 0, wx.LEFT | wx.RIGHT, MARGEN)

        # Una sola barra para todo lo que tarda —cargar, importar, buscar— y un
        # solo botón de detener: nunca hay dos cosas largas a la vez.
        self.estado, self.barra, self.boton_parar = crear_barra(self, contenedor)
        self.tarea = Tarea(self, self.barra, self.estado, self.boton_parar,
                           self.configuracion)

        self.resultados = fila_etiquetada(
            self, contenedor, _("Re&sultados de la búsqueda:"),
            lambda p: ListaAccesible(p, self.configuracion, _("Resultados de la búsqueda"),
                                     size=(960, 170)),
            margen=MARGEN, proporcion=1)
        rellenar_columnas(self.resultados, self.COLUMNAS_RESULTADOS,
                          self.ANCHOS_RESULTADOS)

        pie = wx.BoxSizer(wx.HORIZONTAL)
        self.boton_ficha = wx.Button(self, label=_("Fic&ha del libro..."))
        # Un botón que abre un menú y no cinco botones: los libros parecidos a
        # uno se buscan por serie, por autor, por colección... y cada libro
        # tiene los suyos.  El mismo menú sale con la tecla de aplicaciones
        # sobre la lista.
        self.boton_similares = wx.Button(self, label=_("Libros si&milares..."))
        self.boton_quitar = wx.Button(self, label=_("&Quitar de la biblioteca..."))
        self.boton_coleccion = wx.Button(self, label=_("&Poner colección..."))
        self.boton_bibliografia = wx.Button(self, label=_("B&ibliografía..."))
        self.boton_exportar = wx.Button(self, label=_("E&xportar fichas..."))
        self.boton_cuaderno = wx.Button(self, label=_("Cuaderno de &estudio..."))
        for boton in (self.boton_ficha, self.boton_similares, self.boton_quitar,
                      self.boton_coleccion, self.boton_bibliografia, self.boton_exportar,
                      self.boton_cuaderno):
            pie.Add(boton, 0, wx.RIGHT, MARGEN)
        contenedor.Add(pie, 0, wx.LEFT | wx.RIGHT | wx.TOP, MARGEN)

        pie2 = wx.BoxSizer(wx.HORIZONTAL)
        self.boton_carpeta = wx.Button(self, label=_("Aña&dir carpeta o biblioteca de "
                                                     "calibre..."))
        self.boton_gestor = wx.Button(self, label=_("Bibliotecas &y carpetas..."))
        for boton in (self.boton_carpeta, self.boton_gestor):
            pie2.Add(boton, 0, wx.RIGHT, MARGEN)
        pie2.AddStretchSpacer()
        abrir = wx.Button(self, wx.ID_OK, _("&Abrir"))
        abrir.SetDefault()
        pie2.Add(abrir, 0, wx.RIGHT, MARGEN)
        pie2.Add(wx.Button(self, wx.ID_CANCEL, _("&Cerrar")), 0)
        contenedor.Add(pie2, 0, wx.EXPAND | wx.ALL, MARGEN)
        self.SetSizer(contenedor)
        self.Layout()

        self.filtro.Bind(wx.EVT_TEXT, self._al_escribir_filtro)
        self.busqueda.Bind(wx.EVT_TEXT_ENTER, lambda evento: self._al_buscar(False))
        self.boton_buscar.Bind(wx.EVT_BUTTON, lambda evento: self._al_buscar(False))
        self.boton_buscar_todo.Bind(wx.EVT_BUTTON, lambda evento: self._al_buscar(True))
        self.boton_carpeta.Bind(wx.EVT_BUTTON, self._al_anadir_carpeta)
        self.boton_gestor.Bind(wx.EVT_BUTTON, self._al_gestor)
        self.boton_ficha.Bind(wx.EVT_BUTTON, lambda evento: self._al_ficha())
        self.boton_similares.Bind(wx.EVT_BUTTON, self._al_boton_similares)
        self.boton_exportar.Bind(wx.EVT_BUTTON, lambda evento: self._al_exportar_fichas())
        self.lista.Bind(wx.EVT_CONTEXT_MENU, self._al_menu_lista)
        self.boton_quitar.Bind(wx.EVT_BUTTON, lambda evento: self._al_quitar_libros())
        self.boton_coleccion.Bind(wx.EVT_BUTTON, self._al_poner_coleccion)
        self.boton_bibliografia.Bind(wx.EVT_BUTTON, self._al_bibliografia)
        self.boton_cuaderno.Bind(wx.EVT_BUTTON, self._al_cuaderno)
        self.boton_relacionadas.Bind(wx.EVT_BUTTON, self._al_relacionadas)
        self.agrupar.Bind(wx.EVT_CHOICE, self._al_cambiar_agrupacion)
        self.grupo.Bind(wx.EVT_LIST_ITEM_SELECTED, self._al_elegir_grupo)
        self.grupo.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda evento: self.lista.SetFocus())
        self.orden.Bind(wx.EVT_CHOICE, self._al_cambiar_orden)
        self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda evento: self._abrir_libro())
        self.lista.Bind(wx.EVT_KEY_DOWN, self._al_tecla_lista)
        self.resultados.Bind(wx.EVT_LIST_ITEM_ACTIVATED,
                             lambda evento: self._abrir_resultado())
        self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self._al_cerrar, id=wx.ID_CANCEL)
        self.Bind(wx.EVT_CLOSE, self._al_cerrar)

        self._bloquear(True)
        self.filtro.SetFocus()
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)
        # La carga va después de enseñar la ventana: así aparece al momento y
        # el lector de pantalla puede decir dónde está mientras se leen los
        # libros.
        wx.CallAfter(self._cargar, True)

    # -- cargar --------------------------------------------------------------

    def _cargar(self, al_abrir: bool = False) -> None:
        """Lee la biblioteca en segundo plano."""
        configuracion = self.configuracion

        def trabajo(progreso, cancelado):
            libros, fuentes = biblioteca.cargar(configuracion, progreso, cancelado)
            return libros, fuentes, biblioteca.resumen(libros)

        def hecho(resultado, error: str) -> None:
            self._cargado_fin(resultado, error, al_abrir)

        # Al abrir no se dice nada: el lector de pantalla está diciendo dónde
        # está el foco y cortarle sería peor que esperar dos segundos.
        self.tarea.lanzar(trabajo, hecho, "" if al_abrir else _("Recargando la biblioteca..."))
        self.estado.SetLabel(_("Cargando la biblioteca..."))

    def _cargado_fin(self, resultado, error: str, al_abrir: bool) -> None:
        """Pone en la lista lo cargado y, la primera vez, lo que quede pendiente."""
        if error or resultado is None:
            self.estado.SetLabel(_("No se ha podido cargar la biblioteca: %s") % error)
            self._voz.decir(self.estado.GetLabel())
            self._bloquear(False)
            return
        libros, fuentes, frase = resultado
        clave_actual = self._clave_actual()
        self._fuentes = fuentes
        self._nombres_fuente = {f.id: f.nombre for f in fuentes}
        self.libros = biblioteca.ordenar(libros, self._orden)
        self._cargado = True
        self.resumen.SetLabel(frase)
        self.estado.SetLabel(frase)
        self._refrescar_grupos()
        self._rellenar(clave_actual)
        self._bloquear(False)
        self._voz.decir(frase, interrumpir=False)
        if al_abrir:
            wx.CallAfter(self._pendientes_al_abrir)

    def _pendientes_al_abrir(self) -> None:
        """Lo que hay que hacer nada más abrir, si hay algo.

        Dos cosas: las carpetas que se añadieron con una versión anterior —que
        se exploraban cada vez y ahora se importan una sola— y, si el usuario
        lo ha pedido, poner al día sus bibliotecas de calibre.
        """
        antiguas = list(self.configuracion.obtener("biblioteca_carpetas", []) or [])
        ids: list[int] = []
        if antiguas:
            from nucleo import biblioteca_importar

            modo = str(self.configuracion.obtener("biblioteca_calibre_modo", "calibre"))
            conexion = datos.conectar()
            try:
                for carpeta in antiguas:
                    if datos.fuente_que_contiene(conexion, carpeta) is not None:
                        continue
                    calibre = (modo != "carpeta"
                               and biblioteca_importar.es_biblioteca_calibre(carpeta))
                    ids.append(datos.anadir_fuente(
                        conexion, datos.CALIBRE if calibre else datos.CARPETA, carpeta,
                        pendiente=True))
            finally:
                conexion.close()
            self.configuracion.establecer("biblioteca_carpetas", [])
            self.configuracion.guardar()
            if ids:
                self._importar(ids, _("Las carpetas de la biblioteca ahora se guardan. "
                                      "Importándolas por primera vez..."))
                return
        calibres = [f.id for f in self._fuentes if f.es_calibre and f.disponible]
        # Tras actualizar el programa a una versión que guarda algo nuevo de
        # cada libro (en la 1.3.6, la forma de cita de cada autor), las
        # bibliotecas de calibre se vuelven a leer una vez para traerlo.
        conexion = datos.conectar()
        try:
            releer = datos.leer_meta(conexion, "releer_calibre") == "1"
            if releer:
                datos.escribir_meta(conexion, "releer_calibre", "0")
        finally:
            conexion.close()
        if releer and calibres:
            self._importar(calibres, _("Poniendo al día las bibliotecas de calibre con "
                                       "lo nuevo de esta versión..."), silencioso=True)
            return
        if self.configuracion.obtener("biblioteca_actualizar_al_abrir", False) and calibres:
            self._importar(calibres, "", silencioso=True)

    # -- la lista de libros --------------------------------------------------

    def _al_cambiar_agrupacion(self, evento) -> None:
        """Cambia por qué se agrupa y rehace la lista de grupos."""
        del evento
        self._agrupar = biblioteca.AGRUPACIONES[max(0, self.agrupar.GetSelection())][0]
        self.configuracion.establecer("biblioteca_agrupar", self._agrupar)
        self._refrescar_grupos(conservar=False)
        self._rellenar()
        self._voz.decir(_n("%d grupo.", "%d grupos.", len(self._grupos) - 1)
                        % (len(self._grupos) - 1), interrumpir=False)

    def _al_cambiar_orden(self, evento) -> None:
        """Ordena la lista de otra manera."""
        del evento
        self._orden = biblioteca.ORDENES[max(0, self.orden.GetSelection())][0]
        self.configuracion.establecer("biblioteca_orden", self._orden)
        clave = self._clave_actual()
        self.libros = biblioteca.ordenar(self.libros, self._orden)
        # Los grupos guardan sus libros en el orden de antes: se rehacen.
        self._refrescar_grupos()
        self._rellenar(clave)

    def _refrescar_grupos(self, conservar: bool = True) -> None:
        """Rehace la lista de grupos, conservando el elegido si sigue existiendo."""
        elegida = self._grupo_elegido() if conservar else ""
        grupos, self._reparto = biblioteca.indice_de_grupos(self.libros, self._agrupar,
                                                            self._nombres_fuente)
        self._grupos = [""]
        self._filas_grupo = [(_("Todos"), len(self.libros))]
        for nombre, clave, cuantos in grupos:
            self._grupos.append(clave)
            self._filas_grupo.append(
                (_("Sin este dato") if clave == biblioteca.SIN_GRUPO else nombre, cuantos))
        filas = self._filas_grupo
        self.grupo.poner_filas(len(filas), lambda fila, columna:
                               filas[fila][0] if columna == 0 else str(filas[fila][1]))
        try:
            destino = self._grupos.index(elegida)
        except ValueError:
            destino = 0
        # Se elige sin provocar el aviso de selección: si no, el grupo
        # volvería a rellenar la lista de libros por su cuenta.
        self._sin_eventos_grupo = True
        try:
            self.grupo.seleccionar_solo(destino)
        finally:
            self._sin_eventos_grupo = False

    def _refrescar_colecciones(self) -> None:
        """Lo llaman las órdenes que cambian colecciones: rehace los grupos."""
        self._refrescar_grupos()

    def _grupo_elegido(self) -> str:
        """La clave del grupo elegido en la lista de grupos."""
        indice = self.grupo.fila_actual()
        if 0 <= indice < len(self._grupos):
            return self._grupos[indice]
        return ""

    def _al_elegir_grupo(self, evento) -> None:
        """Al bajar por los grupos, la lista de libros se pone al poco."""
        evento.Skip()
        if getattr(self, "_sin_eventos_grupo", False) or not self._cargado:
            return
        if self._espera_grupo is not None and self._espera_grupo.IsRunning():
            self._espera_grupo.Stop()
        self._espera_grupo = wx.CallLater(ESPERA_FILTRO, self._grupo_ya)

    def _grupo_ya(self) -> None:
        """Enseña los libros del grupo elegido."""
        if self:
            self._rellenar("")

    def _al_escribir_filtro(self, evento) -> None:
        """Filtra un poco después de la última tecla, no en cada una."""
        del evento
        if self._espera_filtro is not None and self._espera_filtro.IsRunning():
            self._espera_filtro.Stop()
        self._espera_filtro = wx.CallLater(ESPERA_FILTRO, self._filtrar_ya)

    def _filtrar_ya(self) -> None:
        """Aplica el filtro y dice cuántos quedan."""
        if not self:
            return
        self._rellenar()
        if self._cargado and self.filtro.GetValue().strip():
            self._voz.decir(_n("%d libro.", "%d libros.", len(self._visibles))
                            % len(self._visibles), interrumpir=False)

    def _rellenar(self, clave_foco: str | None = None) -> None:
        """Vuelca en la lista los libros que pasan el grupo y el filtro."""
        if not self._cargado:
            return
        if clave_foco is None:
            clave_foco = self._clave_actual()
        clave_grupo = self._grupo_elegido()
        del_grupo = self._reparto.get(clave_grupo, []) if clave_grupo else self.libros
        self._visibles = biblioteca.filtrar(del_grupo, self.filtro.GetValue())
        if not self._visibles:
            self.lista.poner_filas(1, lambda fila, columna:
                                   _("(Ningún libro coincide)") if columna == 0 else "")
            return
        visibles = self._visibles
        columnas = self._columnas
        nombres = self._nombres_fuente
        self.lista.poner_filas(
            len(visibles),
            lambda fila, columna: biblioteca.texto_columna(visibles[fila], columnas[columna],
                                                           nombres))
        destino = 0
        if clave_foco:
            for numero, libro in enumerate(visibles):
                if libro.clave == clave_foco:
                    destino = numero
                    break
        self.lista.seleccionar_solo(destino)

    def _clave_actual(self) -> str:
        """La clave del libro con el foco, para no perderlo al refrescar."""
        libro = self._libro_actual()
        return libro.clave if libro is not None else ""

    def _libro_actual(self):
        """El libro seleccionado, o ``None``."""
        indice = self.lista.fila_actual()
        if 0 <= indice < len(self._visibles):
            return self._visibles[indice]
        return None

    def _al_tecla_lista(self, evento: wx.KeyEvent) -> None:
        """Alt+Intro abre la ficha; Suprimir quita los marcados."""
        codigo = evento.GetKeyCode()
        modificadores = evento.GetModifiers()
        if modificadores == wx.MOD_ALT and codigo in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self._al_ficha()
            return
        if modificadores == wx.MOD_NONE and codigo == wx.WXK_DELETE:
            self._al_quitar_libros()
            return
        evento.Skip()

    # -- carpetas y bibliotecas ------------------------------------------------

    def _al_anadir_carpeta(self, evento) -> None:
        """Añade una carpeta o una biblioteca de calibre y la importa."""
        del evento
        if self.tarea.ocupada():
            return
        numero = anadir_carpeta(self, self.configuracion, self._voz)
        if numero is not None:
            self._importar([numero])

    def _importar(self, ids, aviso: str = "", silencioso: bool = False) -> None:
        """Importa o actualiza fuentes en segundo plano y recarga al terminar."""

        def hecho(resumenes, error: str) -> None:
            cambios = any(r.nuevos or r.actualizados or r.quitados
                          for r in (resumenes or []))
            if silencioso and not error:
                if cambios:
                    self._voz.decir(_("Bibliotecas de calibre puestas al día."),
                                    interrumpir=False)
                    self._cargar()
                else:
                    self.estado.SetLabel(_("Las bibliotecas de calibre están al día."))
                    self._bloquear(False)
                return
            mostrar_resumen(self, resumenes, error)
            self._cargar()

        self._bloquear(True)
        lanzado = self.tarea.lanzar(
            trabajo_importar(ids, self.configuracion), hecho,
            aviso or ("" if silencioso else _("Importando en segundo plano. Puedes seguir "
                                              "usando la biblioteca mientras tanto.")))
        if not lanzado:
            self._bloquear(False)

    def _al_gestor(self, evento) -> None:
        """Abre la gestión de bibliotecas y carpetas."""
        del evento
        if self.tarea.ocupada():
            return
        with DialogoFuentes(self, self.configuracion) as dialogo:
            dialogo.ShowModal()
            cambios = dialogo.cambios
        if cambios:
            self._bloquear(True)
            self._cargar()

    # -- la ficha ----------------------------------------------------------------

    def _al_ficha(self) -> None:
        """Enseña todo lo que se sabe del libro con el foco."""
        libro = self._libro_actual()
        if libro is None:
            return
        with DialogoFicha(self, libro, self._nombres_fuente, self.configuracion) as dialogo:
            if dialogo.ShowModal() == wx.ID_OK:
                self._abrir_libro()

    # -- libros similares ------------------------------------------------------

    def _menu_similares(self, menu: wx.Menu, libro) -> int:
        """Añade a un menú las maneras de buscar libros parecidos a uno.

        :return: Cuántas entradas se han añadido.
        """
        nombres = dict(biblioteca.SIMILARES)
        opciones = biblioteca.similares(libro)
        for campo, valor, clave in opciones:
            # «&» en un menú subraya la letra siguiente; doblado se escribe tal cual.
            rotulo = "%s: %s" % (nombres[campo], valor.replace("&", "&&"))
            entrada = menu.Append(wx.ID_ANY, rotulo)
            self.Bind(wx.EVT_MENU,
                      lambda evento, c=campo, v=valor, k=clave, l=libro.clave:
                      self._ir_a_similares(c, v, k, l),
                      entrada)
        return len(opciones)

    def _al_boton_similares(self, evento) -> None:
        """Abre, junto al botón, el menú de libros parecidos al que tiene el foco."""
        del evento
        libro = self._libro_actual()
        if libro is None:
            self._voz.decir(_("Elige antes un libro en la lista."))
            return
        menu = wx.Menu()
        if not self._menu_similares(menu, libro):
            menu.Destroy()
            self._voz.decir(_("Este libro no tiene serie, autor, colección, etiquetas "
                              "ni editorial con los que buscar otros parecidos."))
            return
        self.boton_similares.PopupMenu(menu)
        menu.Destroy()

    def _al_menu_lista(self, evento) -> None:
        """Menú de la lista de libros: ficha, libros similares y exportar.

        Sale con el botón derecho, con la tecla de aplicaciones o con
        Mayús+F10, sobre el libro que tenga el foco.
        """
        del evento
        libro = self._libro_actual()
        if libro is None:
            return
        menu = wx.Menu()
        ficha = menu.Append(wx.ID_ANY, _("Fic&ha del libro..."))
        self.Bind(wx.EVT_MENU, lambda evento: self._al_ficha(), ficha)
        submenu = wx.Menu()
        if not self._menu_similares(submenu, libro):
            vacio = submenu.Append(wx.ID_ANY, _("(Sin datos con los que buscar)"))
            vacio.Enable(False)
        menu.AppendSubMenu(submenu, _("Libros si&milares"))
        exportar = menu.Append(wx.ID_ANY, _("E&xportar fichas..."))
        self.Bind(wx.EVT_MENU, lambda evento: self._al_exportar_fichas(), exportar)
        self.lista.PopupMenu(menu)
        menu.Destroy()

    def _ir_a_similares(self, campo: str, valor: str, clave: str, clave_libro: str) -> None:
        """Enseña los libros que comparten un dato con uno: su serie, su autor...

        No es una búsqueda aparte: se agrupa por ese dato y se elige su grupo,
        igual que se haría a mano con «Agrupar por» y la lista de grupos.  Así
        lo que queda en la lista se puede ordenar, filtrar, exportar o buscar
        dentro como cualquier otro grupo, y volver a verlo todo es elegir
        «Todos» en la lista de grupos.

        Con la serie se ordena además por su número: los libros de una saga se
        quieren en el orden en que se leen, no por orden alfabético.
        """
        if not self._cargado:
            return
        claves_agrupar = [c for c, _n in biblioteca.AGRUPACIONES]
        if campo not in claves_agrupar:
            return
        if self._espera_filtro is not None and self._espera_filtro.IsRunning():
            self._espera_filtro.Stop()
        if self._espera_grupo is not None and self._espera_grupo.IsRunning():
            self._espera_grupo.Stop()
        # ChangeValue y no SetValue: no debe disparar el filtro diferido.
        self.filtro.ChangeValue("")
        self._agrupar = campo
        self.agrupar.SetSelection(claves_agrupar.index(campo))
        self.configuracion.establecer("biblioteca_agrupar", campo)
        if campo == "serie" and self._orden != "serie":
            self._orden = "serie"
            self.orden.SetSelection([c for c, _n in biblioteca.ORDENES].index("serie"))
            self.configuracion.establecer("biblioteca_orden", "serie")
            self.libros = biblioteca.ordenar(self.libros, "serie")
        self._refrescar_grupos(conservar=False)
        try:
            destino = self._grupos.index(clave)
        except ValueError:
            self._rellenar(clave_libro)
            self._voz.decir(_("No se encuentran otros libros con ese dato."))
            return
        self._sin_eventos_grupo = True
        try:
            self.grupo.seleccionar_solo(destino)
        finally:
            self._sin_eventos_grupo = False
        self._rellenar(clave_libro)
        self.lista.SetFocus()
        cuantos = len(self._visibles)
        self._voz.decir("%s: %s. %s" % (
            dict(biblioteca.SIMILARES).get(campo, ""), valor,
            _n("%d libro.", "%d libros.", cuantos) % cuantos))

    # -- exportar fichas -----------------------------------------------------------

    def _al_exportar_fichas(self) -> None:
        """Guarda en un archivo de texto o CSV las fichas de los libros.

        Actúa como la bibliografía: sobre los marcados si hay varios, y si no
        sobre todos los que se están viendo.  Para la ficha de un solo libro ya
        está «Copiar la ficha».
        """
        if self.tarea.ocupada():
            return
        elegidos = self._libros_marcados()
        libros = elegidos if len(elegidos) > 1 else list(self._visibles)
        if not libros:
            self._voz.decir(_("No hay libros de los que exportar las fichas."))
            return
        aviso = _n("Se exportará la ficha de %d libro.",
                   "Se exportarán las fichas de %d libros.", len(libros)) % len(libros)
        with DialogoCamposFicha(self, self.configuracion, fichas.AJUSTE_EXPORTAR,
                                _("Exportar fichas"), aviso) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                return
        campos = fichas.campos_elegidos(
            self.configuracion.obtener(fichas.AJUSTE_EXPORTAR, None))
        filtro = (_("Texto (*.txt)") + "|*.txt|" +
                  _("Hoja de cálculo, CSV (*.csv)") + "|*.csv")
        with wx.FileDialog(self, _("Guardar las fichas"),
                           defaultFile=_("fichas") + ".txt", wildcard=filtro,
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                return
            destino = dialogo.GetPath()
            indice = dialogo.GetFilterIndex()
        formato = fichas.formato_por_nombre(destino, indice)
        if formato == fichas.CSV and not destino.lower().endswith(".csv"):
            destino += ".csv"

        def trabajo(progreso, cancelado):
            return fichas.exportar(libros, campos, destino, formato,
                                   progreso=progreso, cancelado=cancelado)

        def hecho(cuantas, error: str) -> None:
            if error:
                self.estado.SetLabel(_("No se han podido exportar las fichas."))
                wx.MessageBox(_("No se han podido guardar las fichas:\n\n%s") % error,
                              _("Exportar fichas"), wx.OK | wx.ICON_ERROR, self)
                return
            cuantas = cuantas or 0
            frase = _n("%d ficha exportada.", "%d fichas exportadas.", cuantas) % cuantas
            self.estado.SetLabel(frase)
            self._voz.decir(frase)

        self.tarea.lanzar(trabajo, hecho, _("Exportando las fichas..."))

    # -- quitar libros -----------------------------------------------------------

    def _al_quitar_libros(self) -> None:
        """Saca de la biblioteca los libros marcados.  No borra ningún archivo."""
        if self.tarea.ocupada():
            return
        elegidos = self._libros_marcados()
        if not elegidos:
            return
        if len(elegidos) == 1:
            pregunta = _("¿Quitar «%s» de la biblioteca?") % elegidos[0].titulo
        else:
            pregunta = _("¿Quitar %d libros de la biblioteca?") % len(elegidos)
        pregunta += "\n\n" + _(
            "No se borra ningún archivo ni nada de lo que hayas hecho en ellos. Al "
            "actualizar su biblioteca no vuelven; para recuperarlos, «Devolver los "
            "libros quitados» en Bibliotecas y carpetas.")
        if wx.MessageBox(pregunta, _("Quitar de la biblioteca"),
                         wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self) != wx.YES:
            return
        pares = [(libro.ruta, libro.fuente) for libro in elegidos]
        quitadas = {libro.clave for libro in elegidos}

        def trabajo(progreso, cancelado):
            del cancelado
            progreso(0, 0, _("Quitando de la biblioteca..."))
            conexion = datos.conectar()
            try:
                return datos.excluir(conexion, pares)
            finally:
                conexion.close()

        def hecho(cuantos, error: str) -> None:
            self._bloquear(False)
            if error:
                self.estado.SetLabel(_("No se ha podido quitar: %s") % error)
                self._voz.decir(self.estado.GetLabel())
                return
            posicion = max(0, self.lista.fila_actual())
            self.libros = [l for l in self.libros if l.clave not in quitadas]
            self._refrescar_grupos()
            self._rellenar("")
            if self._visibles:
                self.lista.seleccionar_solo(min(posicion, len(self._visibles) - 1))
            frase = biblioteca.resumen(self.libros)
            self.resumen.SetLabel(frase)
            mensaje = _n("%d libro quitado.", "%d libros quitados.", cuantos or 0) % (
                cuantos or 0)
            self.estado.SetLabel(mensaje)
            self._voz.decir(mensaje)

        self._bloquear(True)
        self.tarea.lanzar(trabajo, hecho, "")

    # -- colecciones ---------------------------------------------------------

    def _al_poner_coleccion(self, evento) -> None:
        """Asigna una colección a los libros marcados en la lista.

        Se aplica a **todos los seleccionados**, no solo al que tiene el foco:
        clasificar una asignatura entera de uno en uno son veinte diálogos, y
        entonces no se clasifica nada.
        """
        del evento
        elegidos = self._libros_marcados()
        if not elegidos:
            self._voz.decir(_("Marca antes los libros a los que quieras ponerles "
                              "una colección."))
            self.lista.SetFocus()
            return
        ya_hay = [n for n, _c in biblioteca.colecciones(self.libros)]
        actual = elegidos[0].coleccion if len(elegidos) == 1 else ""
        if len(elegidos) == 1:
            pregunta = (_("Colección o asignatura para «%s».\n"
                          "Déjalo en blanco para quitársela.")
                        % elegidos[0].titulo)
        else:
            pregunta = _n("Colección o asignatura para %d libro elegido.\n"
                          "Déjalo en blanco para quitársela.",
                          "Colección o asignatura para %d libros elegidos.\n"
                          "Déjalo en blanco para quitársela.",
                          len(elegidos)) % len(elegidos)
        with wx.TextEntryDialog(self, pregunta, _("Poner colección"),
                                actual) as dialogo:
            if ya_hay:
                # No hay un TextEntry con desplegable, así que las que ya
                # existen se dicen: sin verlas, cada libro acaba en una
                # colección escrita de una manera distinta.
                dialogo.SetHelpText(", ".join(ya_hay))
            if dialogo.ShowModal() != wx.ID_OK:
                return
            nombre = " ".join(dialogo.GetValue().split())[:60]
        for libro in elegidos:
            libro.coleccion = nombre
            self.configuracion.recordar_coleccion(libro.ruta, nombre)
        self.configuracion.guardar()
        self._refrescar_colecciones()
        self._rellenar()
        if nombre:
            # Las dos formas llevan las mismas variables y en el mismo orden:
            # es lo único que garantiza que el texto se pueda formatear en
            # cualquier idioma, incluidos los que usan la forma plural para el
            # uno o para el cero.
            self._voz.decir(_n("%(cuantos)d libro puesto en «%(nombre)s».",
                               "%(cuantos)d libros puestos en «%(nombre)s».",
                               len(elegidos))
                            % {"cuantos": len(elegidos), "nombre": nombre})
        else:
            self._voz.decir(_("Colección quitada."))

    def _libros_marcados(self) -> list:
        """Los libros seleccionados, o el que tenga el foco si no hay ninguno."""
        if not self._cargado or not self._visibles:
            return []
        if (self.lista.GetSelectedItemCount() == self.lista.GetItemCount()
                and self.lista.GetItemCount() > 1):
            return list(self._visibles)
        elegidos = [self._visibles[i] for i in self.lista.seleccionadas()
                    if 0 <= i < len(self._visibles)]
        if not elegidos:
            uno = self._libro_actual()
            if uno is not None:
                elegidos.append(uno)
        return elegidos

    # -- bibliografía --------------------------------------------------------

    def _al_bibliografia(self, evento) -> None:
        """Saca la bibliografía de los libros que se están viendo."""
        del evento
        from interfaz.dialogos.bibliografia import DialogoBibliografia

        elegidos = self._libros_marcados()
        # Con un solo libro con el foco se entiende que se quiere la lista
        # entera: nadie abre una ventana de bibliografía para una referencia
        # suelta, que es lo que hace Control+Mayús+C.
        libros = elegidos if len(elegidos) > 1 else list(self._visibles)
        if not libros:
            self._voz.decir(_("No hay ningún libro del que sacar la bibliografía."))
            return
        with DialogoBibliografia(self, libros, self.configuracion,
                                 self._opciones()) as dialogo:
            dialogo.ShowModal()

    # -- cuaderno de estudio ---------------------------------------------------

    def _al_cuaderno(self, evento) -> None:
        """Junta lo marcado en los libros que se están viendo.

        Actúa sobre **lo que hay en la lista**, no sobre lo seleccionado, por lo
        mismo que la bibliografía: quien acaba de filtrar por una asignatura
        quiere el cuaderno de esa asignatura, no el del libro que tenga el foco.
        """
        del evento
        from interfaz.dialogos.cuaderno import DialogoCuaderno

        elegidos = self._libros_marcados()
        libros = elegidos if len(elegidos) > 1 else list(self._visibles)
        if not libros:
            self._voz.decir(_("No hay libros de los que sacar el cuaderno."))
            return
        with DialogoCuaderno(self, libros, self.configuracion) as dialogo:
            dialogo.ShowModal()

    # -- palabras relacionadas -----------------------------------------------

    def _al_relacionadas(self, evento) -> None:
        """Enseña qué palabras salen en los mismos sitios que la buscada."""
        del evento
        from nucleo import semantica

        texto = self.busqueda.GetValue().strip()
        if not texto:
            self._voz.decir(_("Escribe antes una palabra en el campo de buscar."))
            self.busqueda.SetFocus()
            return
        indice = self._indice_de_significados()
        if indice is None or not len(indice):
            return
        relacionadas = []
        for palabra in indice.ampliar(texto, 8):
            relacionadas.append(palabra)
        if not relacionadas:
            if not indice.conoce(texto.split()[0]):
                self._voz.decir(
                    _("«%s» no sale lo bastante en tus libros como para saber con "
                      "qué se relaciona.") % texto)
            else:
                self._voz.decir(
                    _("«%s» sale en demasiados sitios: no hay ninguna palabra que "
                      "se le parezca en particular.") % texto)
            return
        with wx.MultiChoiceDialog(
            self,
            _("En tus libros, estas palabras salen en los mismos pasajes que "
              "«%s».\nMarca las que quieras añadir a la búsqueda.") % texto,
            _("Palabras relacionadas"), relacionadas
        ) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                return
            anadidas = [relacionadas[i] for i in dialogo.GetSelections()]
        if not anadidas:
            return
        self.busqueda.SetValue(" ".join(anadidas))
        self.busqueda.SetFocus()
        self._voz.decir(_("Ahora se buscará: %s") % " ".join(anadidas))

    def _indice_de_significados(self):
        """Trae el índice de significados, construyéndolo si hace falta.

        Se construye **una vez** y se guarda en el disco junto a la caché. La
        primera vez tarda —hay que leer los libros enteros—, así que se avisa
        antes y se puede decir que no.
        """
        from nucleo import semantica

        if self._significados is not None:
            return self._significados
        guardado = semantica.cargar()
        rutas_visibles = [libro.ruta for libro in self._visibles if libro.existe]
        if guardado is not None and not semantica.hace_falta_rehacer(guardado,
                                                                    rutas_visibles):
            self._significados = guardado
            return guardado

        respuesta = wx.MessageBox(
            _("Para saber qué palabras se relacionan entre sí hay que leer los "
              "libros una vez y apuntar qué palabras salen juntas.\n\n"
              "Son %d libros y puede tardar un par de minutos. Después queda "
              "guardado y ya es instantáneo.\n\n¿Se hace ahora?")
            % len(rutas_visibles),
            _("Palabras relacionadas"), wx.YES_NO | wx.ICON_QUESTION, self)
        if respuesta != wx.YES:
            return None

        documentos = []
        opciones = self._opciones()
        from nucleo import cache

        progreso = wx.ProgressDialog(
            _("Palabras relacionadas"), _("Leyendo los libros..."),
            maximum=max(1, len(rutas_visibles) * 2), parent=self,
            style=wx.PD_APP_MODAL | wx.PD_CAN_ABORT | wx.PD_AUTO_HIDE)
        parado = [False]
        try:
            for numero, libro in enumerate(
                    [l for l in self._visibles if l.existe]):
                sigue, _saltar = progreso.Update(
                    numero, _("Leyendo: %s") % libro.titulo)
                if not sigue:
                    parado[0] = True
                    break
                documento = biblioteca._abrir(libro, opciones, cache, False)
                if documento is not None and documento.texto:
                    documentos.append((libro.ruta, documento.texto))
            if not parado[0] and documentos:
                indice = semantica.construir(
                    documentos,
                    progreso=lambda hecho, total, detalle: progreso.Update(
                        min(len(rutas_visibles) + hecho // 2,
                            max(1, len(rutas_visibles) * 2) - 1), detalle),
                    cancelado=lambda: parado[0])
            else:
                indice = None
        finally:
            progreso.Destroy()
        if indice is None or not len(indice):
            self._voz.decir(_("No se ha podido preparar el índice de palabras "
                              "relacionadas."))
            return None
        try:
            semantica.guardar(indice)
        except OSError as error:                     # pragma: no cover
            log.info("No se ha podido guardar el índice de significados: %s", error)
        self._significados = indice
        return indice

    # -- la búsqueda ---------------------------------------------------------

    def _opciones(self):
        """Los ajustes de análisis con los que se abren los libros aquí.

        Tienen que ser **los mismos** que usa la ventana principal, o la caché
        no valdría y todos los libros habría que analizarlos otra vez.
        """
        from formatos import base

        return base.OpcionesAnalisis(
            tablas_en_linea=bool(self.configuracion.obtener("tablas_en_linea")),
            anunciar_imagenes_sin_texto=bool(
                self.configuracion.obtener("anunciar_imagenes_sin_texto")),
            estructura_pdf=bool(self.configuracion.obtener("pdf_estructura", True)),
            geometria_pdf=bool(self.configuracion.obtener("pdf_geometria", True)),
            marcar_llamadas_de_nota=bool(
                self.configuracion.obtener("marcar_llamadas_de_nota", False)),
            solo_articulo=bool(self.configuracion.obtener("solo_articulo", True)),
        )

    def _al_buscar(self, todos: bool) -> None:
        """Lanza la búsqueda en otro hilo."""
        if self.tarea.ocupada():
            return
        texto = self.busqueda.GetValue().strip()
        if not texto:
            self._voz.decir(_("Escribe antes lo que quieres buscar."))
            self.busqueda.SetFocus()
            return
        libros = list(self._visibles)
        if not libros:
            return

        aviso = (_("Buscando «%s» en todos los libros. Puede tardar.") % texto if todos
                 else _("Buscando «%s» en los libros ya analizados...") % texto)
        opciones = self._opciones()

        def trabajo(progreso, cancelado):
            return biblioteca.buscar_en_todos(libros, texto, opciones, progreso=progreso,
                                              cancelado=cancelado, solo_cacheados=not todos)

        self._bloquear(True)
        self.tarea.lanzar(trabajo, self._buscado, aviso)

    def _bloquear(self, trabajando: bool) -> None:
        """Deja activo solo lo que tiene sentido mientras se trabaja."""
        for control in (self.boton_buscar, self.boton_buscar_todo,
                        self.boton_carpeta, self.boton_gestor, self.boton_quitar,
                        self.boton_relacionadas):
            control.Enable(not trabajando)

    def _buscado(self, encontrados, error: str) -> None:
        """Recoge los resultados y los enseña."""
        self._bloquear(False)
        self._resultados = list(encontrados or [])
        self.resultados.DeleteAllItems()
        if error:
            self.estado.SetLabel(_("No se ha podido buscar: %s") % error)
            return
        if not self._resultados:
            self.resultados.InsertItem(0, _("(No se ha encontrado nada)"))
            self.estado.SetLabel(
                _("Sin resultados. Prueba con «Buscar en todos» para mirar también en "
                  "los libros que aún no se han analizado."))
            self._voz.decir(_("No se ha encontrado nada."))
            return
        libros = len({resultado.libro.ruta for resultado in self._resultados})
        for numero, resultado in enumerate(self._resultados):
            self.resultados.InsertItem(numero, resultado.libro.titulo)
            self.resultados.SetItem(numero, 1, resultado.sitio)
            self.resultados.SetItem(numero, 2, resultado.contexto)
        self.resultados.Select(0)
        self.resultados.Focus(0)
        mensaje = _("%(cuantos)d resultados en %(libros)d libros.") % {
            "cuantos": len(self._resultados), "libros": libros}
        self.estado.SetLabel(mensaje)
        self._voz.decir(mensaje)
        self.resultados.SetFocus()

    # -- abrir ---------------------------------------------------------------

    def _abrir_libro(self) -> None:
        """Abre el libro seleccionado por donde se quedó."""
        libro = self._libro_actual()
        if libro is None:
            return
        # Se mira ahora y no al cargar: preguntar por ciento noventa mil
        # archivos al abrir la ventana es lo que la hacía lenta.
        libro.existe = os.path.exists(libro.ruta)
        if not libro.existe:
            wx.MessageBox(_("Ese archivo ya no está donde estaba:\n\n%s\n\n"
                            "Si es de un disco que no está conectado, conéctalo. Si se "
                            "ha movido la carpeta entera, cambia su ruta en «Bibliotecas "
                            "y carpetas».") % libro.ruta,
                          _("Biblioteca"), wx.OK | wx.ICON_INFORMATION, self)
            return
        self.elegido = (libro.ruta, -1)
        self._terminar(wx.ID_OK)

    def _abrir_resultado(self) -> None:
        """Abre el libro del resultado, y en el punto donde aparece."""
        indice = self.resultados.fila_actual()
        if not (0 <= indice < len(self._resultados)):
            return
        resultado = self._resultados[indice]
        self.elegido = (resultado.libro.ruta, resultado.posicion)
        self._terminar(wx.ID_OK)

    def _al_aceptar(self, evento) -> None:
        """El botón «Abrir» respeta en qué lista está el foco."""
        del evento
        if self.FindFocus() is self.resultados and self._resultados:
            self._abrir_resultado()
            return
        self._abrir_libro()

    def _al_cerrar(self, evento) -> None:
        """Si se está importando, se pregunta antes de cortarlo."""
        if self.tarea.activa and self._cargado:
            if wx.MessageBox(_("Hay un trabajo en marcha. Si cierras, se detiene y lo "
                               "hecho hasta ahora se queda guardado.\n\n¿Cerrar?"),
                             _("Biblioteca"), wx.YES_NO | wx.ICON_QUESTION,
                             self) != wx.YES:
                return
        self._terminar(wx.ID_CANCEL)

    def _terminar(self, codigo: int) -> None:
        """Para lo que siga en marcha, guarda cómo se dejó la vista y cierra."""
        self.tarea.parar.set()
        self.configuracion.guardar()
        if self.IsModal():
            self.EndModal(codigo)
        else:
            self.Destroy()

    def Destroy(self):                               # noqa: N802 - lo pide wx
        """Al cerrar, se para cualquier trabajo que siguiera vivo."""
        self.tarea.parar.set()
        return super().Destroy()


class DialogoFicha(wx.Dialog):
    """Todo lo que se sabe de un libro: los datos de calibre o del EPUB, y más.

    Va en un cuadro de solo lectura, una línea por dato, para poder recorrerlo
    con las flechas y copiar lo que haga falta.  Qué datos lleva y en qué
    orden se elige con «Elegir los datos»; de fábrica van primero el título, la
    serie, los autores y la sinopsis, y después lo técnico.

    ``nombres_fuente`` se sigue admitiendo por compatibilidad, pero ya no hace
    falta: el nombre de la biblioteca sale de la base de datos.
    """

    def __init__(self, padre: wx.Window, libro, nombres_fuente=None,
                 configuracion=None) -> None:
        super().__init__(padre, title=_("Ficha: %s") % libro.titulo,
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        del nombres_fuente
        self.libro = libro
        self.configuracion = (configuracion if configuracion is not None
                              else getattr(padre, "configuracion", None))
        self._voz = Voz(self)
        texto = self._componer(libro, self._campos())
        contenedor = wx.BoxSizer(wx.VERTICAL)
        self.texto = fila_etiquetada(
            self, contenedor, _("&Datos del libro:"),
            lambda p: wx.TextCtrl(p, value=texto, size=(640, 420),
                                  style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_NOHIDESEL),
            margen=MARGEN, proporcion=1)
        fila = wx.BoxSizer(wx.HORIZONTAL)
        self.boton_abrir = wx.Button(self, wx.ID_OK, _("&Abrir el libro"))
        self.boton_carpeta = wx.Button(self, label=_("Abrir la &carpeta"))
        self.boton_copiar = wx.Button(self, label=_("C&opiar la ficha"))
        self.boton_datos = wx.Button(self, label=_("&Elegir los datos..."))
        self.boton_cerrar = wx.Button(self, wx.ID_CANCEL, _("Ce&rrar"))
        for boton in (self.boton_abrir, self.boton_carpeta, self.boton_copiar,
                      self.boton_datos, self.boton_cerrar):
            fila.Add(boton, 0, wx.RIGHT, MARGEN)
        contenedor.Add(fila, 0, wx.ALL, MARGEN)
        self.SetSizerAndFit(contenedor)
        self.CentreOnParent()
        self.boton_carpeta.Bind(wx.EVT_BUTTON, self._al_carpeta)
        self.boton_copiar.Bind(wx.EVT_BUTTON, self._al_copiar)
        self.boton_datos.Bind(wx.EVT_BUTTON, self._al_elegir_datos)
        self.texto.SetFocus()
        self.texto.SetInsertionPoint(0)
        ayuda_opcion.enganchar(self)

    def _campos(self) -> list[str]:
        """Los datos que se han elegido para la ficha, en su orden."""
        guardado = (self.configuracion.obtener(fichas.AJUSTE_FICHA, None)
                    if self.configuracion is not None else None)
        return fichas.campos_elegidos(guardado)

    @staticmethod
    def _componer(libro, campos) -> str:
        """Escribe la ficha con los datos elegidos, en su orden."""
        conexion = datos.conectar()
        try:
            ficha = fichas.leer_ficha(conexion, libro)
        finally:
            conexion.close()
        return fichas.componer(libro, ficha, campos) or _("(No hay datos que enseñar.)")

    def _al_elegir_datos(self, evento) -> None:
        """Deja elegir qué datos lleva la ficha y en qué orden, y la rehace."""
        del evento
        if self.configuracion is None:
            return
        with DialogoCamposFicha(self, self.configuracion, fichas.AJUSTE_FICHA,
                                _("Datos de la ficha")) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                return
        self.texto.SetValue(self._componer(self.libro, self._campos()))
        self.texto.SetInsertionPoint(0)
        self.texto.SetFocus()
        self._voz.decir(_("Ficha rehecha con los datos elegidos."))

    def _al_carpeta(self, evento) -> None:
        """Abre el Explorador con el archivo marcado."""
        del evento
        if not os.path.exists(self.libro.ruta):
            self._voz.decir(_("El archivo no está ahora en su sitio."))
            return
        abrir_carpeta_de(self.libro.ruta)

    def _al_copiar(self, evento) -> None:
        """Copia la ficha entera al portapapeles."""
        del evento
        if wx.TheClipboard.Open():
            try:
                wx.TheClipboard.SetData(wx.TextDataObject(self.texto.GetValue()))
            finally:
                wx.TheClipboard.Close()
            self._voz.decir(_("Ficha copiada."))


class DialogoCamposFicha(wx.Dialog):
    """Elige qué datos lleva una ficha y en qué orden.

    Una lista de casillas, una por dato: marcado sale, desmarcado no.  El orden
    de la lista es el de la ficha, y se cambia con «Subir» y «Bajar» o con
    Alt+flecha arriba y Alt+flecha abajo sobre la lista, que mueven el dato con
    el foco sin tener que ir a los botones.

    :param ajuste: Dónde se guarda la elección: la ficha que se ve
                   (``fichas.AJUSTE_FICHA``) o las que se exportan
                   (``fichas.AJUSTE_EXPORTAR``).
    :param aviso: Frase que se pone arriba, si hace falta contar algo más.
    """

    def __init__(self, padre: wx.Window, configuracion, ajuste: str,
                 titulo: str, aviso: str = "") -> None:
        super().__init__(padre, title=titulo,
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.configuracion = configuracion
        self.ajuste = ajuste
        self._voz = Voz(self)
        visibles = fichas.campos_elegidos(configuracion.obtener(ajuste, None))
        self._orden: list[tuple[str, bool]] = fichas.orden_completo(visibles)

        contenedor = wx.BoxSizer(wx.VERTICAL)
        if aviso:
            contenedor.Add(wx.StaticText(self, label=aviso), 0, wx.ALL, MARGEN)
        self.lista = fila_etiquetada(
            self, contenedor, _("&Datos, en el orden en que salen:"),
            lambda p: ListaCasillas(p, _("Datos de la ficha"), size=(420, 330)),
            margen=MARGEN, proporcion=1)
        self._volcar(0)

        fila = wx.BoxSizer(wx.HORIZONTAL)
        self.boton_subir = wx.Button(self, label=_("S&ubir"))
        self.boton_bajar = wx.Button(self, label=_("&Bajar"))
        self.boton_fabrica = wx.Button(self, label=_("Valores de &fábrica"))
        for boton in (self.boton_subir, self.boton_bajar, self.boton_fabrica):
            fila.Add(boton, 0, wx.RIGHT, MARGEN)
        contenedor.Add(fila, 0, wx.LEFT | wx.RIGHT, MARGEN)

        pie = wx.BoxSizer(wx.HORIZONTAL)
        pie.AddStretchSpacer()
        self.boton_aceptar = wx.Button(self, wx.ID_OK, _("&Aceptar"))
        self.boton_aceptar.SetDefault()
        pie.Add(self.boton_aceptar, 0, wx.RIGHT, MARGEN)
        self.boton_cancelar = wx.Button(self, wx.ID_CANCEL, _("&Cancelar"))
        pie.Add(self.boton_cancelar, 0)
        contenedor.Add(pie, 0, wx.EXPAND | wx.ALL, MARGEN)
        self.SetSizerAndFit(contenedor)
        self.CentreOnParent()

        self.boton_subir.Bind(wx.EVT_BUTTON, lambda evento: self._mover(-1))
        self.boton_bajar.Bind(wx.EVT_BUTTON, lambda evento: self._mover(1))
        self.boton_fabrica.Bind(wx.EVT_BUTTON, self._al_fabrica)
        self.lista.Bind(wx.EVT_KEY_DOWN, self._al_tecla)
        self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)
        self.lista.SetFocus()
        ayuda_opcion.enganchar(self)

    def _recoger(self) -> None:
        """Pasa a ``_orden`` lo que esté marcado ahora en la lista."""
        self._orden = [(clave, self.lista.IsChecked(numero))
                       for numero, (clave, _visible) in enumerate(self._orden)]

    def _volcar(self, foco: int) -> None:
        """Escribe ``_orden`` en la lista y deja el foco en una fila."""
        self.lista.Set([fichas.nombre_de(clave) for clave, _visible in self._orden])
        for numero, (_clave, visible) in enumerate(self._orden):
            self.lista.Check(numero, visible)
        if self._orden:
            self.lista.SetSelection(max(0, min(foco, len(self._orden) - 1)))

    def _mover(self, paso: int) -> None:
        """Sube o baja un puesto el dato elegido."""
        indice = self.lista.GetSelection()
        if indice == wx.NOT_FOUND:
            return
        nuevo = indice + paso
        if not 0 <= nuevo < len(self._orden):
            self._voz.decir(_("Ya está el primero.") if paso < 0 else _("Ya está el último."))
            return
        self._recoger()
        self._orden[indice], self._orden[nuevo] = self._orden[nuevo], self._orden[indice]
        self._volcar(nuevo)
        self.lista.SetFocus()
        self._voz.decir(_("%(dato)s, puesto %(puesto)d de %(total)d") % {
            "dato": fichas.nombre_de(self._orden[nuevo][0]),
            "puesto": nuevo + 1, "total": len(self._orden)})

    def _al_tecla(self, evento: wx.KeyEvent) -> None:
        """Alt+flecha arriba y Alt+flecha abajo mueven el dato con el foco."""
        if evento.GetModifiers() == wx.MOD_ALT:
            if evento.GetKeyCode() == wx.WXK_UP:
                self._mover(-1)
                return
            if evento.GetKeyCode() == wx.WXK_DOWN:
                self._mover(1)
                return
        evento.Skip()

    def _al_fabrica(self, evento) -> None:
        """Vuelve a todos los datos, en el orden de fábrica."""
        del evento
        self._orden = fichas.orden_completo(fichas.campos_elegidos(None))
        self._volcar(0)
        self.lista.SetFocus()
        self._voz.decir(_("Todos los datos, en el orden de fábrica."))

    def _al_aceptar(self, evento) -> None:
        """Guarda la elección; no deja cerrar sin ningún dato marcado."""
        self._recoger()
        visibles = [clave for clave, visible in self._orden if visible]
        if not visibles:
            self._voz.decir(_("Marca al menos un dato."))
            self.lista.SetFocus()
            return
        self.configuracion.establecer(self.ajuste, visibles)
        try:
            self.configuracion.guardar()
        except Exception as error:                   # pragma: no cover
            log.warning("No se ha podido guardar la elección de la ficha: %s", error)
        evento.Skip()
