# -*- coding: utf-8 -*-
"""Diálogos de navegación: índice, lista de elementos, saltos y marcadores.

Todos siguen las mismas reglas de accesibilidad:

* cada control lleva delante una etiqueta que lo describe;
* al abrirse, el foco va al control principal y queda ya seleccionada la
  entrada correspondiente al punto donde se está leyendo;
* ``Intro`` acepta, ``Escape`` cancela y una doble pulsación en la lista
  equivale a aceptar;
* se devuelve la posición elegida, o ``None`` si el usuario cancela.
"""

from __future__ import annotations

import unicodedata

import wx

from interfaz.accesible import etiquetar, fila_etiquetada
from interfaz.dialogos import ayuda_opcion
from interfaz.listas import ListaAccesible, rellenar_columnas
from nucleo import etiquetas
from nucleo.configuracion import Marcador
from nucleo.resaltados import nombres as resaltados_exportar
from nucleo.documento import Documento
from nucleo.idioma import _
from nucleo.marcas import NOMBRES, TipoMarca, nivel_de_encabezado
from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

#: Separación estándar entre los elementos de un diálogo, en píxeles.
MARGEN = 8


def _botones(dialogo: wx.Dialog, contenedor: wx.Sizer, etiqueta_aceptar: str = "&Ir") -> wx.Button:
    """Añade los botones «Aceptar» y «Cancelar» al pie de un diálogo."""
    fila = wx.StdDialogButtonSizer()
    aceptar = wx.Button(dialogo, wx.ID_OK, etiqueta_aceptar)
    aceptar.SetDefault()
    cancelar = wx.Button(dialogo, wx.ID_CANCEL, _("&Cancelar"))
    fila.AddButton(aceptar)
    fila.AddButton(cancelar)
    fila.Realize()
    contenedor.Add(fila, 0, wx.EXPAND | wx.ALL, MARGEN)
    return aceptar


class DialogoIndice(wx.Dialog):
    """Muestra el índice de contenidos del libro como un árbol.

    Si el libro no trae índice se construye uno con sus encabezados, de modo
    que el diálogo siempre resulta útil.
    """

    def __init__(self, padre: wx.Window, documento: Documento, posicion: int) -> None:
        super().__init__(padre, title=_("Índice del documento"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.documento = documento
        self.posicion_elegida: int | None = None
        self._posiciones: dict = {}

        contenedor = wx.BoxSizer(wx.VERTICAL)
        # La etiqueta se crea antes que el árbol a propósito: ese orden es el
        # que usa Windows para saber a qué control pertenece cada texto.
        contenedor.Add(wx.StaticText(self, label=_("&Contenido del documento:")), 0,
                       wx.LEFT | wx.RIGHT | wx.TOP, MARGEN)
        self.arbol = etiquetar(wx.TreeCtrl(
            self, size=(520, 460),
            style=wx.TR_HAS_BUTTONS | wx.TR_HIDE_ROOT | wx.TR_LINES_AT_ROOT | wx.TR_SINGLE,
        ), _("Contenido del documento"))
        contenedor.Add(self.arbol, 1, wx.EXPAND | wx.ALL, MARGEN)
        _botones(self, contenedor)
        self.SetSizerAndFit(contenedor)

        self._rellenar(posicion)
        self.arbol.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self._al_activar)
        self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)
        self.arbol.SetFocus()
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    def _rellenar(self, posicion: int) -> None:
        """Vuelca el índice en el árbol y selecciona la entrada actual."""
        raiz = self.arbol.AddRoot("Libro")
        entradas = self.documento.indice
        if not entradas:
            entradas = self._indice_desde_encabezados()
        mas_cercano = None
        mejor_distancia = None

        def anadir(padre, lista):
            nonlocal mas_cercano, mejor_distancia
            for entrada in lista:
                nodo = self.arbol.AppendItem(padre, entrada.titulo)
                self._posiciones[nodo] = entrada.posicion
                if entrada.posicion <= posicion:
                    distancia = posicion - entrada.posicion
                    if mejor_distancia is None or distancia <= mejor_distancia:
                        mejor_distancia = distancia
                        mas_cercano = nodo
                if entrada.hijos:
                    anadir(nodo, entrada.hijos)

        anadir(raiz, entradas)
        if mas_cercano is not None:
            self.arbol.EnsureVisible(mas_cercano)
            self.arbol.SelectItem(mas_cercano)
        elif self.arbol.GetChildrenCount(raiz, False):
            primero, _ = self.arbol.GetFirstChild(raiz)
            if primero.IsOk():
                self.arbol.SelectItem(primero)

    def _indice_desde_encabezados(self):
        """Construye un índice a partir de los encabezados del libro.

        Se usa cuando el EPUB no incluye tabla de contenidos.  Los niveles se
        anidan respetando la jerarquía de los encabezados.
        """
        from nucleo.documento import ElementoIndice

        raices: list[ElementoIndice] = []
        pila: list[tuple[int, ElementoIndice]] = []
        for marca in self.documento.marcas.encabezados:
            nivel = marca.nivel or nivel_de_encabezado(marca.tipo)
            entrada = ElementoIndice(marca.texto or _("(sin título)"), marca.posicion)
            while pila and pila[-1][0] >= nivel:
                pila.pop()
            if pila:
                pila[-1][1].hijos.append(entrada)
            else:
                raices.append(entrada)
            pila.append((nivel, entrada))
        return raices

    def _al_activar(self, evento: wx.TreeEvent) -> None:
        """Doble pulsación o Intro sobre una entrada: equivale a aceptar."""
        self._al_aceptar(evento)

    def _al_aceptar(self, evento) -> None:
        """Guarda la posición elegida y cierra el diálogo."""
        nodo = self.arbol.GetSelection()
        if nodo.IsOk() and nodo in self._posiciones:
            self.posicion_elegida = self._posiciones[nodo]
            self.EndModal(wx.ID_OK)
        else:
            self.EndModal(wx.ID_CANCEL)


class DialogoElementos(wx.Dialog):
    """Lista todos los elementos de un tipo (encabezados, enlaces, imágenes...).

    Equivale a la «lista de elementos» de los lectores de pantalla: permite
    ver de un vistazo todo lo que hay en el libro y saltar a ello.
    """

    #: Las tres clases de cosas que pone quien lee.  Se identifican con una
    #: cadena y no con un ``TipoMarca`` porque no son del documento: son suyas.
    PROPIOS: tuple = (
        ("marcadores", lambda uno: not uno.es_nota and not uno.es_resaltado),
        ("notas", lambda uno: uno.es_nota),
        ("resaltados", lambda uno: uno.es_resaltado),
    )

    #: Tipos que se ofrecen en el desplegable, en orden de utilidad.  Lo que
    #: uno mismo ha puesto va primero: al volver a un libro ya trabajado es lo
    #: primero que se busca.
    TIPOS = (
        (_("Marcadores"), "marcadores"),
        (_("Notas"), "notas"),
        (_("Resaltados"), "resaltados"),
        ("Encabezados", None),
        # Las llamadas de nota van antes que los enlaces a propósito: en un
        # libro anotado son la mitad de los enlaces, y quien las busca no las
        # encuentra si tiene que ir mirándolas entre trescientas más.
        (_("Llamadas de nota"), TipoMarca.NOTA_PIE),
        ("Enlaces", TipoMarca.ENLACE),
        (_("Imágenes"), TipoMarca.IMAGEN),
        ("Figuras", TipoMarca.FIGURA),
        ("Tablas", TipoMarca.TABLA),
        ("Listas", TipoMarca.LISTA),
        (_("Elementos de lista"), TipoMarca.ELEMENTO_LISTA),
        ("Citas", TipoMarca.CITA),
        ("Separadores", TipoMarca.SEPARADOR),
        (_("Páginas"), TipoMarca.SALTO_PAGINA),
        ("Secciones", TipoMarca.SALTO_SECCION),
    )

    def __init__(self, padre: wx.Window, documento: Documento, posicion: int,
                 marcadores=()) -> None:
        super().__init__(padre, title=_("Lista de elementos"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.documento = documento
        self.marcadores = list(marcadores or [])
        self.posicion_actual = posicion
        self.posicion_elegida: int | None = None
        self._posiciones: list[int] = []

        contenedor = wx.BoxSizer(wx.VERTICAL)
        self.tipos = fila_etiquetada(
            self, contenedor, _("&Tipo de elemento:"),
            lambda p: wx.Choice(p, choices=[self._rotulo(nombre, tipo)
                                            for nombre, tipo in self.TIPOS]),
            margen=MARGEN, horizontal=True, proporcion=1,
        )
        self.tipos.SetSelection(0)
        self.lista = fila_etiquetada(
            self, contenedor, "&Elementos encontrados:",
            lambda p: wx.ListBox(p, size=(560, 420)), margen=MARGEN, proporcion=1,
        )
        _botones(self, contenedor)
        self.SetSizerAndFit(contenedor)

        self.tipos.Bind(wx.EVT_CHOICE, lambda evento: self._rellenar())
        self.lista.Bind(wx.EVT_LISTBOX_DCLICK, self._al_aceptar)
        self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)
        self._rellenar()
        self.tipos.SetFocus()
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    def _rotulo(self, nombre: str, tipo) -> str:
        """Añade al nombre del tipo cuántos elementos hay de él."""
        if isinstance(tipo, str):
            cantidad = len(self._propios_de(tipo))
        elif tipo is None:
            cantidad = len(self.documento.marcas.encabezados)
        else:
            cantidad = self.documento.marcas.cantidad(tipo)
        return "%s (%d)" % (nombre, cantidad)

    def _propios_de(self, clase: str) -> list:
        """Los marcadores, las notas o los resaltados, en orden de lectura."""
        for nombre, es_de_esta in self.PROPIOS:
            if nombre == clase:
                return sorted((uno for uno in self.marcadores if es_de_esta(uno)),
                              key=lambda uno: uno.inicio)
        return []

    def _rellenar_propios(self, clase: str) -> None:
        """Vuelca en la lista lo que ha puesto quien lee.

        Con el porcentaje delante: es lo que sitúa un apunte dentro del libro
        cuando el texto por sí solo no basta para reconocerlo.
        """
        entradas = []
        self._posiciones = []
        for uno in self._propios_de(clase):
            texto = (uno.nota or "").strip() or (uno.fragmento or "").strip()
            if not texto:
                texto = self.documento.texto_de_linea(uno.inicio).strip()
            entradas.append("%3d%%  %s" % (
                self.documento.porcentaje_en(uno.inicio),
                texto[:180] or _("(sin texto)")))
            self._posiciones.append(uno.inicio)
        vacio = {"marcadores": _("(No hay ningún marcador en este documento)"),
                 "notas": _("(No hay ninguna nota en este documento)"),
                 "resaltados": _("(No hay ningún resaltado en este documento)")}
        self.lista.Set(entradas or [vacio.get(clase, _("(No hay nada)"))])
        if self._posiciones:
            # El más cercano a por donde se iba leyendo, que es el que se
            # estaba buscando nueve de cada diez veces.
            cercano = min(range(len(self._posiciones)),
                          key=lambda numero: abs(self._posiciones[numero]
                                                 - self.posicion_actual))
            self.lista.SetSelection(cercano)
            self.lista.EnsureVisible(cercano)

    def _rellenar(self) -> None:
        """Vuelca en la lista los elementos del tipo seleccionado."""
        indice = max(self.tipos.GetSelection(), 0)
        # Sin nombrar la primera parte: llamarla «_» la haría local y taparía
        # la función de traducción para el resto del método.
        tipo = self.TIPOS[indice][1]
        if isinstance(tipo, str):
            self._rellenar_propios(tipo)
            return
        grupo = self.documento.marcas.encabezados if tipo is None else self.documento.marcas.grupo(tipo)
        entradas: list[str] = []
        self._posiciones = []
        for numero, marca in enumerate(grupo, start=1):
            texto = (marca.texto or "").strip()
            if not texto:
                texto = self.documento.texto_de_linea(marca.posicion).strip()
            if not texto:
                texto = NOMBRES.get(marca.tipo, "elemento")
            if tipo is None:
                nivel = marca.nivel or nivel_de_encabezado(marca.tipo)
                entradas.append("%s  (nivel %d)" % (texto[:150], nivel))
            elif tipo is TipoMarca.SALTO_PAGINA:
                entradas.append(_("Página %s") % (texto[:60] or numero))
            else:
                entradas.append(texto[:180])
            self._posiciones.append(marca.posicion)
        self.lista.Set(entradas or [_("(No hay elementos de este tipo)")])
        if self._posiciones:
            cercano = grupo.indice_mas_cercano(self.posicion_actual)
            self.lista.SetSelection(max(cercano, 0))
            self.lista.EnsureVisible(max(cercano, 0))

    def _al_aceptar(self, evento) -> None:
        """Guarda la posición elegida y cierra."""
        indice = self.lista.GetSelection()
        if 0 <= indice < len(self._posiciones):
            self.posicion_elegida = self._posiciones[indice]
            self.EndModal(wx.ID_OK)
        else:
            self.EndModal(wx.ID_CANCEL)


class DialogoPestanas(wx.Dialog):
    """Cambio rápido entre los documentos abiertos.

    Con dos o tres pestañas basta con Control+Tabulador, pero con siete no:
    hay que pasar por todas para llegar a la que se quiere, y cada paso cambia
    el documento y lo anuncia.  Esta lista las enseña todas de golpe, se
    recorre en silencio y salta de una vez, que es lo que hace falta cuando se
    está comparando media docena de textos.

    :param rotulos: Títulos de los documentos abiertos, en su orden.
    :param actual: Cuál está delante ahora mismo.
    """

    def __init__(self, padre: wx.Window, rotulos: list[str], actual: int) -> None:
        super().__init__(padre, title=_("Documentos abiertos"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.elegida: int | None = None
        contenedor = wx.BoxSizer(wx.VERTICAL)
        self.lista = fila_etiquetada(
            self, contenedor, _("&Pestañas abiertas:"),
            lambda p: wx.ListBox(p, size=(480, 280),
                                 choices=["%d. %s" % (numero, rotulo)
                                          for numero, rotulo in enumerate(rotulos, start=1)]),
            margen=MARGEN, proporcion=1,
        )
        _botones(self, contenedor, _("&Ir a la pestaña"))
        self.SetSizerAndFit(contenedor)
        if rotulos:
            self.lista.SetSelection(max(0, min(actual, len(rotulos) - 1)))
        self.lista.Bind(wx.EVT_LISTBOX_DCLICK, self._al_aceptar)
        self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)
        self.lista.SetFocus()
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    def _al_aceptar(self, evento) -> None:
        """Guarda la pestaña elegida y cierra."""
        indice = self.lista.GetSelection()
        if indice >= 0:
            self.elegida = indice
            self.EndModal(wx.ID_OK)
        else:
            self.EndModal(wx.ID_CANCEL)


class DialogoDondeAbrir(wx.Dialog):
    """Pregunta si el documento que se abre va en una pestaña nueva o en esta.

    Se pregunta en lugar de decidir porque las dos respuestas son razonables y
    cuál toca depende de lo que se esté haciendo: quien estudia quiere el
    documento nuevo al lado del que tiene, y quien acaba de terminar una novela
    quiere sustituirla.  Quien lo tenga claro marca la casilla y no vuelve a
    ver la pregunta.

    :param titulo_actual: Título del documento que hay ahora en la pestaña, que
                          es el dato que falta para poder decidir.
    """

    def __init__(self, padre: wx.Window, titulo_actual: str) -> None:
        super().__init__(padre, title=_("Abrir el documento"))
        self.en_pestana_nueva = True
        contenedor = wx.BoxSizer(wx.VERTICAL)
        contenedor.Add(wx.StaticText(self, label=_(
            "En esta pestaña ya tienes abierto:\n\n%s\n\n¿Dónde quieres abrir el "
            "documento nuevo?") % titulo_actual), 0, wx.ALL, MARGEN)
        self.recordarlo = wx.CheckBox(
            self, label=_("Hacerlo siempre así y no volver a &preguntar"))
        contenedor.Add(self.recordarlo, 0, wx.ALL, MARGEN)

        fila = wx.StdDialogButtonSizer()
        nueva = wx.Button(self, wx.ID_OK, _("En una pestaña &nueva"))
        nueva.SetDefault()
        esta = wx.Button(self, wx.ID_NO, _("En &esta pestaña"))
        cancelar = wx.Button(self, wx.ID_CANCEL, _("&Cancelar"))
        fila.AddButton(nueva)
        fila.AddButton(cancelar)
        fila.Realize()
        # El botón «en esta pestaña» va aparte del organizador estándar: no es
        # ni aceptar ni cancelar, sino la segunda respuesta a la pregunta.
        botones = wx.BoxSizer(wx.HORIZONTAL)
        botones.Add(esta, 0, wx.RIGHT, MARGEN)
        botones.Add(fila, 1, wx.EXPAND)
        contenedor.Add(botones, 0, wx.EXPAND | wx.ALL, MARGEN)
        self.SetSizerAndFit(contenedor)

        self.Bind(wx.EVT_BUTTON, self._al_elegir, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self._al_elegir, id=wx.ID_NO)
        nueva.SetFocus()
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    @property
    def recordar(self) -> bool:
        """Indica si hay que dejar de preguntar a partir de ahora."""
        return bool(self.recordarlo.GetValue())

    def _al_elegir(self, evento) -> None:
        """Anota la respuesta y cierra aceptando."""
        self.en_pestana_nueva = evento.GetId() == wx.ID_OK
        self.EndModal(wx.ID_OK)


class DialogoSalto(wx.Dialog):
    """Diálogo genérico para saltar a una línea, un porcentaje o una página."""

    def __init__(self, padre: wx.Window, titulo: str, etiqueta: str,
                 minimo: int, maximo: int, actual: int) -> None:
        super().__init__(padre, title=titulo)
        self.valor: int | None = None
        contenedor = wx.BoxSizer(wx.VERTICAL)
        # wx.SpinCtrl no expone ningún nombre accesible por sí solo (se
        # comprobó leyendo el nombre real que anuncia el sistema), así que
        # aquí se le fija de forma explícita.
        self.campo = fila_etiquetada(
            self, contenedor, etiqueta,
            lambda p: wx.SpinCtrl(p, min=minimo, max=max(maximo, minimo),
                                  initial=max(minimo, min(actual, maximo))),
            margen=MARGEN,
        )
        _botones(self, contenedor)
        self.SetSizerAndFit(contenedor)
        self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)
        self.campo.SetFocus()
        self.campo.SetSelection(-1, -1)
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    def _al_aceptar(self, evento) -> None:
        """Recoge el valor introducido."""
        self.valor = self.campo.GetValue()
        self.EndModal(wx.ID_OK)


def _sin_tildes(texto: str) -> str:
    """Deja el texto en minúsculas y sin acentos, para poder buscar en él.

    Se busca así porque escribir con acentos en un campo de búsqueda mientras
    se oye la lista es una fuente de fallos tonta: «análisis» y «analisis»
    tienen que encontrar lo mismo.
    """
    plano = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in plano if not unicodedata.combining(c)).lower().strip()


class DialogoMarcadores(wx.Dialog):
    """Lista los marcadores y notas del libro y permite ir a ellos o borrarlos.

    :param configuracion: Preferencias, para los ajustes de lectura por
                          columnas de la lista.
    """

    #: Filtros del desplegable, con el texto que se muestra cuando ese filtro
    #: no deja nada.  El mensaje tiene que decir qué es lo que falta: un
    #: «no hay marcadores ni notas» cuando el filtro es «Solo notas» y el
    #: libro sí tiene marcadores lleva a pensar que se han perdido.
    FILTROS = (
        ("Todo", _("(No hay marcadores ni notas en este documento)")),
        ("Solo marcadores", _("(No hay marcadores en este documento)")),
        ("Solo notas", _("(No hay notas en este documento)")),
    )

    #: Columnas de la lista.  Sus títulos son lo que se anuncia al recorrerla
    #: con las flechas izquierda y derecha.
    COLUMNAS = ("Tipo", _("Punto del documento"), "Contenido")
    ANCHOS = (90, 120, 380)

    def __init__(self, padre: wx.Window, documento: Documento,
                 marcadores: list[Marcador], posicion: int, configuracion=None) -> None:
        super().__init__(padre, title=_("Marcadores y notas"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.documento = documento
        self.marcadores = sorted(marcadores, key=lambda m: m.inicio)
        self.posicion_elegida: int | None = None
        self.eliminados: list[Marcador] = []

        contenedor = wx.BoxSizer(wx.VERTICAL)
        self.filtro = fila_etiquetada(
            self, contenedor, "&Mostrar:",
            lambda p: wx.Choice(p, choices=[nombre for nombre, _ in self.FILTROS]),
            margen=MARGEN, horizontal=True, proporcion=1,
        )
        self.filtro.SetSelection(0)
        # Buscar entre las notas es lo que hace que sirvan de algo pasado un
        # tiempo: en un manual con sesenta notas, recorrerlas una a una para
        # encontrar la que hablaba de un concepto es más trabajo que volver a
        # buscarlo en el libro.  Se busca en la nota y en el texto marcado.
        self.busqueda = fila_etiquetada(
            self, contenedor, _("&Buscar entre las notas:"),
            lambda p: wx.TextCtrl(p, style=wx.TE_PROCESS_ENTER),
            margen=MARGEN, horizontal=True, proporcion=1,
        )
        self.lista = fila_etiquetada(
            self, contenedor, _("&Marcadores y notas del documento:"),
            lambda p: ListaAccesible(p, configuracion, _("Marcadores y notas del documento"),
                                     size=(600, 380)),
            margen=MARGEN, proporcion=1,
        )
        rellenar_columnas(self.lista, self.COLUMNAS, self.ANCHOS)

        pie = wx.BoxSizer(wx.HORIZONTAL)
        self.boton_borrar = wx.Button(self, label=_("&Eliminar"))
        pie.Add(self.boton_borrar, 0, wx.RIGHT, MARGEN)
        contenedor.Add(pie, 0, wx.LEFT | wx.RIGHT, MARGEN)
        self.boton_ir = _botones(self, contenedor)
        self.SetSizerAndFit(contenedor)

        self.filtro.Bind(wx.EVT_CHOICE, lambda evento: self._rellenar())
        self.busqueda.Bind(wx.EVT_TEXT, lambda evento: self._rellenar())
        # Con Intro se salta a la lista, que es lo que uno quiere después de
        # escribir lo que busca.
        self.busqueda.Bind(wx.EVT_TEXT_ENTER, lambda evento: self.lista.SetFocus())
        self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._al_aceptar)
        self.boton_borrar.Bind(wx.EVT_BUTTON, self._al_borrar)
        self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)
        self._visibles: list[Marcador] = []
        self._rellenar(posicion)
        self.lista.SetFocus()
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    def _rellenar(self, posicion: int | None = None, seleccionar: int = 0) -> None:
        """Vuelca en la lista los marcadores que pasan el filtro.

        :param posicion: Punto de lectura actual; si se indica, se selecciona
                         la entrada más cercana que quede por detrás.
        :param seleccionar: Fila que hay que dejar seleccionada cuando no se
                            indica ninguna posición (tras borrar, por ejemplo).
        """
        eleccion = max(self.filtro.GetSelection(), 0)
        if eleccion == 1:
            self._visibles = [m for m in self.marcadores if not m.es_nota]
        elif eleccion == 2:
            self._visibles = [m for m in self.marcadores if m.es_nota]
        else:
            self._visibles = list(self.marcadores)

        buscado = _sin_tildes(self.busqueda.GetValue())
        if buscado:
            self._visibles = [m for m in self._visibles
                              if buscado in _sin_tildes("%s %s" % (m.nota, m.fragmento))]

        self.lista.DeleteAllItems()
        if not self._visibles:
            # La lista vacía se deja con una sola fila explicativa: un control
            # sin ninguna fila no da al lector de pantalla nada que anunciar.
            self.lista.InsertItem(0, _("(Nada coincide con «%s»)") % self.busqueda.GetValue()
                                  if buscado else self.FILTROS[eleccion][1])
            self._habilitar_acciones(False)
            return
        self._habilitar_acciones(True)
        for numero, marcador in enumerate(self._visibles):
            self.lista.InsertItem(numero, "Nota" if marcador.es_nota else "Marcador")
            self.lista.SetItem(numero, 1, "%d %%" % self.documento.porcentaje_en(marcador.inicio))
            self.lista.SetItem(numero, 2, self._detalle(marcador))

        indice = min(max(seleccionar, 0), len(self._visibles) - 1)
        if posicion is not None:
            indice = 0
            for numero, marcador in enumerate(self._visibles):
                if marcador.inicio <= posicion:
                    indice = numero
        self.lista.Select(indice)
        self.lista.Focus(indice)
        self.lista.EnsureVisible(indice)

    def _habilitar_acciones(self, hay: bool) -> None:
        """Activa o desactiva los botones que necesitan una entrada elegida.

        Con la lista vacía no hay adónde ir ni nada que borrar, y un botón
        activo que no hace nada al pulsarlo desorienta a quien no ve la lista.
        """
        self.boton_borrar.Enable(hay)
        self.boton_ir.Enable(hay)

    @staticmethod
    def _detalle(marcador: Marcador) -> str:
        """Texto de la columna de contenido: la nota, o el trozo marcado."""
        detalle = marcador.nota if marcador.es_nota else marcador.fragmento
        return (detalle or "").strip() or "(sin texto)"

    def _al_borrar(self, evento) -> None:
        """Pide confirmación y elimina el marcador o la nota seleccionados."""
        indice = self.lista.fila_actual()
        if not (0 <= indice < len(self._visibles)):
            return
        marcador = self._visibles[indice]
        nombre = "esta nota" if marcador.es_nota else "este marcador"
        respuesta = wx.MessageBox(
            _("¿Seguro que quieres eliminar %s?\n\n%s\n\nEsta acción no se puede deshacer.")
            % (nombre, self._detalle(marcador)[:200]),
            _("Eliminar"), wx.YES_NO | wx.ICON_QUESTION | wx.NO_DEFAULT, self)
        if respuesta != wx.YES:
            return
        self.eliminados.append(marcador)
        self.marcadores.remove(marcador)
        # Tras borrar se deja el foco donde estaba, que suele ser la entrada
        # siguiente; si se ha borrado la última, en la que pasa a serlo.
        self._rellenar(seleccionar=indice)
        self.lista.SetFocus()

    def _al_aceptar(self, evento) -> None:
        """Guarda la posición elegida y cierra."""
        indice = self.lista.fila_actual()
        if 0 <= indice < len(self._visibles):
            self.posicion_elegida = self._visibles[indice].inicio
            self.EndModal(wx.ID_OK)
        else:
            self.EndModal(wx.ID_CANCEL)


class DialogoResaltados(wx.Dialog):
    """Lista los pasajes resaltados del documento, para ir a ellos o sacarlos.

    Es hermano del de marcadores y a propósito no es el mismo: un marcador
    señala **un punto** al que volver, y un resaltado señala **un pasaje** que
    interesa conservar.  Mezclarlos en una lista obligaría a filtrar cada vez
    para encontrar lo que se busca, y son dos formas de trabajar distintas: el
    marcador se pone mientras se lee, el resaltado se repasa después.

    :param resaltados: Pasajes ya ordenados por su sitio en el documento.
    """

    #: Columnas de la lista.  Sus títulos son lo que se anuncia al recorrerla
    #: con las flechas izquierda y derecha.
    COLUMNAS = (_("Punto del documento"), _("Texto resaltado"), _("Etiquetas"))
    ANCHOS = (130, 430, 120)

    def __init__(self, padre: wx.Window, documento: Documento,
                 resaltados: list, posicion: int, configuracion=None) -> None:
        super().__init__(padre, title=_("Resaltados"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.documento = documento
        self.resaltados = list(resaltados)
        self.posicion_elegida: int | None = None
        self.eliminados: list = []
        #: Formato al que hay que sacarlos al cerrar, o cadena vacía si no.
        #: Lo mira la ventana, que es quien sabe pedir el archivo y escribirlo.
        self.exportar = ""
        #: Si en el archivo van también las notas escritas.  Lo lee la ventana
        #: junto con el formato.
        self.con_notas = False
        #: Etiqueta por la que se está filtrando, o cadena vacía.  La ventana la
        #: lee al exportar para sacar solo el material de ese tema.
        self.etiqueta = ""
        self._todos = list(resaltados)

        contenedor = wx.BoxSizer(wx.VERTICAL)
        self.lista = fila_etiquetada(
            self, contenedor, _("&Pasajes resaltados:"),
            lambda p: ListaAccesible(p, configuracion or getattr(padre, "configuracion", None),
                                     _("Pasajes resaltados"), size=(680, 380)),
            margen=MARGEN, proporcion=1,
        )
        rellenar_columnas(self.lista, self.COLUMNAS, self.ANCHOS)

        # El filtro por tema es lo que convierte esto en material de estudio:
        # para preparar el capítulo cuatro no hacen falta los ciento veinte
        # resaltados del libro, hacen falta los once de ese tema.
        self._etiquetas = [""] + [e for e, _cuantas
                                  in etiquetas.recuento(self._todos)]
        if len(self._etiquetas) > 1:
            rotulos = [_("Todas")] + [
                _("%(etiqueta)s (%(cuantas)d)") % {"etiqueta": e, "cuantas": c}
                for e, c in etiquetas.recuento(self._todos)]
            self.filtro = fila_etiquetada(
                self, contenedor, _("Mostrar solo la e&tiqueta:"),
                lambda p: wx.Choice(p, choices=rotulos),
                margen=MARGEN, horizontal=True)
            self.filtro.SetSelection(0)
            self.filtro.Bind(wx.EVT_CHOICE, self._al_filtrar)
        else:
            self.filtro = None

        pie = wx.BoxSizer(wx.HORIZONTAL)
        self.boton_borrar = wx.Button(self, label=_("&Eliminar"))
        pie.Add(self.boton_borrar, 0, wx.RIGHT, MARGEN)
        # El formato se elige **antes** de pulsar «Guardar», y no en el diálogo
        # de archivo: allí habría que saber que el desplegable de tipos cambia
        # lo que se escribe y no solo la extensión, y no todo el mundo lo sabe.
        self._formatos = [(clave,) + datos
                          for clave, datos in resaltados_exportar().items()]
        self.formato = fila_etiquetada(
            self, pie, _("&Guardar como:"),
            lambda p: wx.Choice(p, choices=[rotulo for _c, rotulo, _e, _f in self._formatos]),
            margen=MARGEN, horizontal=True)
        self.formato.SetSelection(0)
        self.boton_exportar = wx.Button(self, label=_("&Guardar en un archivo..."))
        pie.Add(self.boton_exportar, 0, wx.RIGHT, MARGEN)
        contenedor.Add(pie, 0, wx.LEFT | wx.RIGHT, MARGEN)
        # Lo subrayado y lo pensado, juntos: es lo que convierte el archivo en
        # un cuaderno de estudio en vez de en una lista de citas sueltas.
        self.casilla_notas = wx.CheckBox(
            self, label=_("Incluir también las &notas que hayas escrito, y la cita del "
                          "documento"))
        self.casilla_notas.SetValue(True)
        contenedor.Add(self.casilla_notas, 0, wx.ALL, MARGEN)
        self.boton_ir = _botones(self, contenedor)
        self.SetSizerAndFit(contenedor)

        self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._al_aceptar)
        self.boton_borrar.Bind(wx.EVT_BUTTON, self._al_borrar)
        self.boton_exportar.Bind(wx.EVT_BUTTON, self._al_exportar)
        self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)
        self._rellenar(posicion)
        self.lista.SetFocus()
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    def _rellenar(self, posicion: int | None = None, seleccionar: int = 0) -> None:
        """Vuelca los resaltados en la lista y coloca la selección."""
        self.lista.DeleteAllItems()
        if not self.resaltados:
            self.lista.InsertItem(0, _("(Ya no queda ningún resaltado)"))
            self.boton_borrar.Enable(False)
            self.boton_exportar.Enable(False)
            self.boton_ir.Enable(False)
            return
        for numero, marcador in enumerate(self.resaltados):
            self.lista.InsertItem(numero, self._sitio(marcador.inicio))
            self.lista.SetItem(numero, 1, self._detalle(marcador))
            self.lista.SetItem(numero, 2, etiquetas.escribir(etiquetas.de(marcador)))
        indice = min(max(seleccionar, 0), len(self.resaltados) - 1)
        if posicion is not None:
            indice = 0
            for numero, marcador in enumerate(self.resaltados):
                if marcador.inicio <= posicion:
                    indice = numero
        self.lista.Select(indice)
        self.lista.Focus(indice)
        self.lista.EnsureVisible(indice)

    def _sitio(self, posicion: int) -> str:
        """Dónde está el pasaje: su página si el documento las tiene."""
        indice = self.documento.indice_de_pagina(posicion)
        if indice >= 0 and self.documento.total_paginas:
            marcas = self.documento.marcas.grupo(TipoMarca.SALTO_PAGINA).marcas
            if 0 <= indice < len(marcas):
                return _("Página %s") % (marcas[indice].texto or str(indice + 1))
        return "%d %%" % self.documento.porcentaje_en(posicion)

    @staticmethod
    def _detalle(marcador) -> str:
        """El texto resaltado, en una línea para que quepa en la lista."""
        return " ".join((marcador.fragmento or "").split()) or _("(sin texto)")

    def _al_filtrar(self, evento) -> None:
        """Deja en la lista solo lo del tema elegido."""
        del evento
        indice = max(self.filtro.GetSelection(), 0)
        self.etiqueta = self._etiquetas[indice] if indice < len(self._etiquetas) else ""
        self.resaltados = etiquetas.filtrar(self._todos, self.etiqueta)
        self._rellenar()
        self.lista.SetFocus()

    def _al_borrar(self, evento) -> None:
        """Quita el resaltado elegido, tras confirmarlo."""
        indice = self.lista.fila_actual()
        if not (0 <= indice < len(self.resaltados)):
            return
        marcador = self.resaltados[indice]
        respuesta = wx.MessageBox(
            _("¿Seguro que quieres quitar este resaltado?\n\n%s\n\n"
              "Esta acción no se puede deshacer.") % self._detalle(marcador)[:300],
            _("Quitar el resaltado"), wx.YES_NO | wx.ICON_QUESTION | wx.NO_DEFAULT, self)
        if respuesta != wx.YES:
            return
        self.eliminados.append(marcador)
        self.resaltados.remove(marcador)
        if marcador in self._todos:
            self._todos.remove(marcador)
        self._rellenar(seleccionar=indice)
        self.lista.SetFocus()

    def _al_exportar(self, evento) -> None:
        """Cierra pidiendo que se guarden en el formato elegido."""
        indice = max(self.formato.GetSelection(), 0)
        self.exportar = self._formatos[indice][0]
        self.con_notas = self.casilla_notas.GetValue()
        self.EndModal(wx.ID_CANCEL)

    def _al_aceptar(self, evento) -> None:
        """Guarda la posición elegida y cierra."""
        indice = self.lista.fila_actual()
        if 0 <= indice < len(self.resaltados):
            self.posicion_elegida = self.resaltados[indice].inicio
            self.EndModal(wx.ID_OK)
        else:
            self.EndModal(wx.ID_CANCEL)
