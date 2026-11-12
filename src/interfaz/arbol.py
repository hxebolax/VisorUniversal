# -*- coding: utf-8 -*-
"""Árbol de contenido: el índice y los elementos del documento, siempre a mano.

La lista de elementos (`F7`) y el índice (`Control+T`) enseñan lo mismo que
este panel, pero en un diálogo que hay que abrir, mirar y cerrar.  Para
consultar de vez en cuando está bien; para **trabajar** con un documento
—estudiar, comparar, saltar veinte veces de un apartado a otro— es un estorbo,
porque cada salto son tres pasos y una pérdida de contexto.

Este panel deja ese mismo contenido abierto a la izquierda del texto, en un
árbol que se pliega y se despliega.  Se va a él con `F6` y se vuelve con `F6`,
sin cerrar nada, y al llegar **el árbol ya está colocado por donde va la
lectura**: eso es lo que lo convierte en un mapa del documento y no en otra
lista más.

Es opcional, y por buenos motivos: quien lee una novela de cabo a rabo no
necesita un mapa, y una zona de más por la que pasar con `F6` es una molestia
diaria a cambio de nada.

Tres decisiones que se notan al usarlo:

* **Las ramas se llenan cuando se abren.** Un libro puede tener catorce mil
  elementos de lista; construirlos todos al abrir el documento costaría más que
  analizarlo entero.  Cada rama se llena la primera vez que se despliega, en el
  tiempo que tarda la propia animación de despliegue.
* **Moverse por el árbol no mueve el documento.** Se salta con Intro, a
  propósito: si cada flecha arrastrara la lectura, recorrer el árbol para ver
  qué hay dentro sería imposible sin perder el sitio.
* **El índice manda sobre los encabezados.** Cuando el documento trae índice
  propio —el de un EPUB, los marcadores de un PDF— esa es la rama que se
  sincroniza, porque es la que hizo quien escribió el documento.
"""

from __future__ import annotations

import bisect
from typing import Callable

import wx

from nucleo.idioma import _
from nucleo.marcas import NOMBRES, TipoMarca, nivel_de_encabezado
from nucleo.registro import obtener_registro

from .accesible import etiquetar

log = obtener_registro(__name__)

#: Categorías de elementos que se ofrecen como ramas, en orden de utilidad.
#: Es la misma lista que la de `F7`, para que quien conozca una conozca la otra.
CATEGORIAS: tuple[tuple[str, object], ...] = (
    (_("Encabezados"), None),
    ("Enlaces", TipoMarca.ENLACE),
    (_("Imágenes"), TipoMarca.IMAGEN),
    ("Figuras", TipoMarca.FIGURA),
    ("Tablas", TipoMarca.TABLA),
    ("Listas", TipoMarca.LISTA),
    (_("Elementos de lista"), TipoMarca.ELEMENTO_LISTA),
    ("Citas", TipoMarca.CITA),
    (_("Fórmulas"), TipoMarca.FORMULA),
    (_("Bloques de código"), TipoMarca.CODIGO),
    (_("Llamadas de nota"), TipoMarca.NOTA_PIE),
    ("Separadores", TipoMarca.SEPARADOR),
    (_("Páginas"), TipoMarca.SALTO_PAGINA),
    ("Secciones", TipoMarca.SALTO_SECCION),
)

#: Cuántos elementos como mucho se meten en una rama.  Una lista de veinte mil
#: entradas no la recorre nadie y sí deja el árbol pesado; a partir de aquí se
#: dice cuántos se han dejado fuera y se remite a `F7`, que busca sobre todos.
TOPE_POR_RAMA = 3000

#: Longitud a la que se recorta el rótulo de una entrada.
LARGO_ROTULO = 150


class Entrada:
    """Qué hay detrás de un nodo del árbol.

    Antes solo se guardaba la posición, que basta para saltar.  Para ofrecer
    acciones hace falta saber además **qué es**: una imagen y un encabezado se
    saltan igual, pero no se hace lo mismo con ellos.

    :param posicion: Dónde está en el texto, o ``None`` si el nodo no lleva a
                     ningún sitio (la cabecera de una rama, por ejemplo).
    :param tipo: Tipo de marca, o ``None`` si es del índice o de encabezados.
    :param marca: La marca original, cuando la hay.  Las órdenes de imagen y de
                  tabla la necesitan entera, no solo su posición.
    :param rama: Nombre de la categoría si el nodo **es** la cabecera de una
                 rama. Es lo que distingue «actuar sobre uno» de «sobre todos».
    """

    __slots__ = ("posicion", "tipo", "marca", "rama", "marcador", "clase")

    def __init__(self, posicion=None, tipo=None, marca=None, rama="",
                 marcador=None, clase="") -> None:
        self.posicion = posicion
        self.tipo = tipo
        self.marca = marca
        self.rama = rama
        #: Lo que puso quien lee, cuando el nodo es suyo y no del documento.
        self.marcador = marcador
        #: De qué clase es esa rama de las suyas: «marcadores», «notas» o
        #: «resaltados».  Es lo que decide qué se ofrece en lote.
        self.clase = clase

    @property
    def es_rama(self) -> bool:
        return bool(self.rama)


class PanelArbol(wx.Panel):
    """Árbol del contenido del documento, a la izquierda del texto.

    :param padre: Ventana que lo contiene.
    :param al_elegir: Se llama con la posición del texto cuando se activa una
                      entrada (Intro o doble clic).
    :param posicion_actual: Función que devuelve por dónde va la lectura.  Se
                            consulta al recibir el foco, que es cuando hay que
                            colocar el árbol.
    :param acciones: Quién sabe hacer lo que el menú ofrece.  Es la ventana
                     principal: las órdenes de ver una imagen o describirla ya
                     existen ahí y no hay ninguna razón para tener dos.
    """

    def __init__(self, padre: wx.Window, al_elegir: Callable[[int], None],
                 posicion_actual: Callable[[], int], acciones=None,
                 marcadores=None) -> None:
        super().__init__(padre)
        self._al_elegir = al_elegir
        self._posicion_actual = posicion_actual
        self._acciones = acciones
        #: De dónde salen los marcadores, las notas y los resaltados.  Es una
        #: función y no una lista porque cambian mientras se lee.
        self._marcadores = marcadores or (lambda: [])
        #: Las ramas de lo que puso quien lee, para poder rehacerlas solas.
        self._ramas_propias: list = []
        self.documento = None
        #: Posiciones del índice, ordenadas, con el nodo de cada una.  Es lo
        #: que permite responder «¿por dónde voy?» con una búsqueda binaria.
        self._referencias: list[int] = []
        self._nodos: list = []
        #: Ramas que todavía no se han llenado: nodo → tipo de marca.
        self._pendientes: dict = {}
        self._sincronizando = False

        contenedor = wx.BoxSizer(wx.VERTICAL)
        self.arbol = etiquetar(
            wx.TreeCtrl(self, style=wx.TR_HAS_BUTTONS | wx.TR_HIDE_ROOT
                        | wx.TR_LINES_AT_ROOT | wx.TR_SINGLE | wx.TR_FULL_ROW_HIGHLIGHT),
            _("Contenido del documento"))
        contenedor.Add(self.arbol, 1, wx.EXPAND)
        self.SetSizer(contenedor)

        self.arbol.Bind(wx.EVT_TREE_ITEM_EXPANDING, self._al_desplegar)
        self.arbol.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self._al_activar)
        # Un solo aviso para las tres formas de pedirlo: la tecla de
        # aplicaciones, Mayúsculas+F10 y el botón derecho.
        self.arbol.Bind(wx.EVT_TREE_ITEM_MENU, self._al_menu)
        # Al llegar al árbol se coloca solo por donde va la lectura: es lo que
        # lo hace un mapa del documento y no una lista suelta.
        self.arbol.Bind(wx.EVT_SET_FOCUS, self._al_recibir_foco)
        self.raiz = self.arbol.AddRoot(_("Documento"))
        self.limpiar()

    # -- contenido -----------------------------------------------------------

    def limpiar(self) -> None:
        """Deja el árbol vacío, como cuando no hay ningún documento abierto."""
        self.documento = None
        self._referencias = []
        self._nodos = []
        self._pendientes = {}
        self.arbol.DeleteChildren(self.raiz)
        self.arbol.AppendItem(self.raiz, _("(No hay ningún documento abierto)"))

    def cargar(self, documento) -> None:
        """Vuelca en el árbol el índice y las categorías de un documento."""
        self.documento = documento
        self._referencias = []
        self._nodos = []
        self._pendientes = {}
        arbol = self.arbol
        arbol.Freeze()
        try:
            arbol.DeleteChildren(self.raiz)
            if documento is None:
                arbol.AppendItem(self.raiz, _("(No hay ningún documento abierto)"))
                return
            self._construir_indice(documento)
            self._construir_propias()
            self._construir_categorias(documento)
        finally:
            arbol.Thaw()

    def _construir_indice(self, documento) -> None:
        """Cuelga el índice propio del documento, entero y ya desplegado.

        Entero porque es la rama que se sincroniza con la lectura y hay que
        poder buscar en ella sin desplegar nada; desplegado un nivel porque lo
        primero que se quiere ver al llegar es de qué partes consta el
        documento.
        """
        entradas = documento.indice
        if not entradas:
            return
        rama = self.arbol.AppendItem(
            self.raiz, _("Índice del documento (%d)") % len(documento.indice_plano()))
        self.arbol.SetItemData(rama, Entrada(rama=_("Índice del documento")))
        self._colgar_indice(rama, entradas)
        # Las entradas del índice vienen en orden de lectura, pero un documento
        # mal hecho puede traerlas desordenadas, y entonces la búsqueda binaria
        # de «¿por dónde voy?» daría cualquier cosa.  Ordenarlas aquí cuesta
        # nada y lo evita.
        emparejadas = sorted(zip(self._referencias, range(len(self._nodos))))
        self._nodos = [self._nodos[numero] for _posicion, numero in emparejadas]
        self._referencias = [posicion for posicion, _numero in emparejadas]
        self.arbol.Expand(rama)

    def _colgar_indice(self, padre, entradas) -> None:
        """Cuelga recursivamente las entradas del índice bajo un nodo."""
        for entrada in entradas:
            nodo = self.arbol.AppendItem(padre, entrada.titulo[:LARGO_ROTULO] or _("(sin título)"))
            self.arbol.SetItemData(nodo, Entrada(int(entrada.posicion)))
            self._referencias.append(int(entrada.posicion))
            self._nodos.append(nodo)
            if entrada.hijos:
                self._colgar_indice(nodo, entrada.hijos)

    #: Las tres clases de cosas que pone quien lee, con cómo se llaman y cómo
    #: se reconocen.  Un mismo apunte puede salir en dos —una nota sobre un
    #: pasaje resaltado es las dos cosas— y está bien: son dos formas de
    #: buscarlo, no dos copias.
    PROPIAS: tuple = (
        ("marcadores", lambda uno: not uno.es_nota and not uno.es_resaltado),
        ("notas", lambda uno: uno.es_nota),
        ("resaltados", lambda uno: uno.es_resaltado),
    )

    @staticmethod
    def _nombre_de_rama_propia(clase: str, cuantos: int) -> str:
        nombres = {"marcadores": _("Marcadores"), "notas": _("Notas"),
                   "resaltados": _("Resaltados")}
        return "%s (%d)" % (nombres.get(clase, clase), cuantos)

    def _construir_propias(self) -> None:
        """Cuelga lo que ha puesto quien lee: marcadores, notas y resaltados.

        Van enteras y no al desplegarlas: de estas hay las que uno haya escrito,
        y esas son pocas por definición.
        """
        self._ramas_propias = []
        try:
            todos = list(self._marcadores() or [])
        except Exception as error:      # pragma: no cover - documento cerrándose
            log.debug("No se han podido leer los marcadores: %s", error)
            return
        if not todos:
            return
        for clase, es_de_esta in self.PROPIAS:
            suyos = sorted((uno for uno in todos if es_de_esta(uno)),
                           key=lambda uno: uno.inicio)
            if not suyos:
                continue
            rama = self.arbol.AppendItem(
                self.raiz, self._nombre_de_rama_propia(clase, len(suyos)))
            self.arbol.SetItemData(rama, Entrada(
                rama=self._nombre_de_rama_propia(clase, len(suyos)), clase=clase))
            self._ramas_propias.append(rama)
            for uno in suyos:
                hijo = self.arbol.AppendItem(rama, self._rotulo_propio(uno))
                self.arbol.SetItemData(
                    hijo, Entrada(int(uno.inicio), marcador=uno, clase=clase))
            self.arbol.Expand(rama)

    def _rotulo_propio(self, marcador) -> str:
        """Cómo se lee un marcador en el árbol.

        Primero lo que se escribió, que es lo que uno recuerda; si no hay nota,
        el trozo señalado; y si tampoco, por dónde está, que al menos sitúa.
        """
        texto = (marcador.nota or "").strip() or (marcador.fragmento or "").strip()
        if not texto and self.documento is not None:
            texto = self.documento.texto_de_linea(marcador.inicio).strip()
        if not texto:
            if self.documento is not None:
                return _("En el %d por ciento") % self.documento.porcentaje_en(
                    marcador.inicio)
            return _("(sin texto)")
        return texto[:LARGO_ROTULO]

    def refrescar_propias(self) -> None:
        """Rehace las ramas de marcadores, notas y resaltados.

        Se llama cuando se pone o se quita alguno.  Se rehacen solo esas ramas
        y no el árbol entero: reconstruirlo perdería el sitio, las ramas
        desplegadas y la selección, que es justo lo que uno tiene puesto cuando
        está trabajando con un libro.
        """
        if self.documento is None:
            return
        arbol = self.arbol
        arbol.Freeze()
        try:
            for rama in self._ramas_propias:
                if rama.IsOk():
                    arbol.Delete(rama)
            self._ramas_propias = []
            # Se vuelven a colgar al final; las de las categorías se quedan
            # donde estaban, que es lo que evita que el árbol dé un salto.
            self._construir_propias()
        except Exception as error:      # pragma: no cover - árbol rehaciéndose
            log.debug("No se han podido rehacer las ramas propias: %s", error)
        finally:
            arbol.Thaw()

    def _construir_categorias(self, documento) -> None:
        """Cuelga una rama por cada clase de elemento que el documento tenga."""
        for nombre, tipo in CATEGORIAS:
            cantidad = (len(documento.marcas.encabezados) if tipo is None
                        else documento.marcas.cantidad(tipo))
            if not cantidad:
                continue
            rama = self.arbol.AppendItem(self.raiz, "%s (%d)" % (nombre, cantidad))
            # La rama se llena al desplegarla: construir aquí los catorce mil
            # elementos de lista de un manual costaría más que abrir el libro.
            self.arbol.SetItemHasChildren(rama, True)
            self.arbol.SetItemData(rama, Entrada(tipo=tipo, rama=nombre))
            self._pendientes[rama] = tipo

    def _al_desplegar(self, evento) -> None:
        """Llena una rama la primera vez que se abre."""
        nodo = evento.GetItem()
        if nodo not in self._pendientes or self.documento is None:
            return
        tipo = self._pendientes.pop(nodo)
        grupo = (self.documento.marcas.encabezados if tipo is None
                 else self.documento.marcas.grupo(tipo))
        self.arbol.Freeze()
        try:
            for numero, marca in enumerate(grupo, start=1):
                if numero > TOPE_POR_RAMA:
                    aviso = self.arbol.AppendItem(
                        nodo, _("(y %d más: búscalos con F7)") % (len(grupo) - TOPE_POR_RAMA))
                    self.arbol.SetItemData(aviso, None)
                    break
                hijo = self.arbol.AppendItem(nodo, self._rotulo(marca, tipo, numero))
                self.arbol.SetItemData(hijo, Entrada(int(marca.posicion),
                                                     marca.tipo, marca))
        finally:
            self.arbol.Thaw()

    def _rotulo(self, marca, tipo, numero: int) -> str:
        """Texto con el que se enseña un elemento en el árbol."""
        texto = (marca.texto or "").strip()
        if not texto and self.documento is not None:
            texto = self.documento.texto_de_linea(marca.posicion).strip()
        if not texto:
            texto = NOMBRES.get(marca.tipo, _("elemento"))
        if tipo is None:
            nivel = marca.nivel or nivel_de_encabezado(marca.tipo)
            return _("%s (nivel %d)") % (texto[:LARGO_ROTULO], nivel)
        if tipo is TipoMarca.SALTO_PAGINA:
            return _("Página %s") % (texto[:60] or numero)
        return texto[:LARGO_ROTULO]

    # -- interacción ---------------------------------------------------------

    def _al_activar(self, evento) -> None:
        """Salta en el documento a la entrada activada con Intro o doble clic."""
        entrada = self.arbol.GetItemData(evento.GetItem())
        if entrada is None or entrada.posicion is None:
            evento.Skip()
            return
        self._al_elegir(int(entrada.posicion))

    def _al_menu(self, evento) -> None:
        """Abre el menú de lo que se puede hacer con el nodo que tiene el foco.

        Se selecciona antes lo que se va a usar: con el botón derecho se puede
        pedir el menú de un nodo que no era el seleccionado, y actuar sobre uno
        distinto del que se ve marcado sería de las cosas más desconcertantes
        que puede hacer un programa.
        """
        nodo = evento.GetItem()
        if not nodo.IsOk():
            return
        self.arbol.SelectItem(nodo)
        entrada = self.arbol.GetItemData(nodo)
        if entrada is None or self.documento is None:
            return
        menu = wx.Menu()
        cuantas = (self._menu_de_rama(menu, entrada) if entrada.es_rama
                   else self._menu_de_elemento(menu, entrada))
        if not cuantas:
            menu.Destroy()
            return
        self.arbol.PopupMenu(menu)
        menu.Destroy()

    def _anadir(self, menu, texto: str, orden) -> None:
        """Una orden del menú, con lo que hace al elegirla."""
        elemento = menu.Append(wx.ID_ANY, texto)
        self.arbol.Bind(wx.EVT_MENU, lambda evento: orden(), elemento)

    def _menu_de_elemento(self, menu, entrada) -> int:
        """Lo que se puede hacer con un elemento concreto."""
        acciones = self._acciones
        puestas = 0
        if entrada.posicion is not None:
            self._anadir(menu, _("&Ir aquí"),
                         lambda: self._al_elegir(int(entrada.posicion)))
            puestas += 1
            if acciones is not None and hasattr(acciones, "leer_desde"):
                self._anadir(menu, _("&Leer en voz alta desde aquí"),
                             lambda: acciones.leer_desde(int(entrada.posicion)))
                puestas += 1

        if acciones is None:
            return puestas

        if entrada.marcador is not None:
            return puestas + self._ordenes_de_marcador(menu, entrada, acciones)

        tipo = entrada.tipo
        if tipo in (TipoMarca.IMAGEN, TipoMarca.FIGURA):
            menu.AppendSeparator()
            self._anadir(menu, _("&Ver la imagen"),
                         lambda: acciones.ver_imagen_del_arbol(entrada.marca))
            self._anadir(menu, _("&Describir con inteligencia artificial"),
                         lambda: acciones.describir_del_arbol(entrada.marca))
            puestas += 2
        elif tipo is TipoMarca.TABLA:
            menu.AppendSeparator()
            self._anadir(menu, _("Abrir la &tabla"),
                         lambda: acciones.ver_tabla_del_arbol(entrada.marca))
            puestas += 1
        elif tipo is TipoMarca.ENLACE:
            menu.AppendSeparator()
            self._anadir(menu, _("&Seguir el enlace"),
                         lambda: acciones.seguir_enlace_del_arbol(entrada.marca))
            puestas += 1

        menu.AppendSeparator()
        self._anadir(menu, _("&Copiar el texto de esta entrada"),
                     lambda: acciones.copiar_al_portapapeles(
                         self.arbol.GetItemText(self.arbol.GetSelection())))
        if entrada.posicion is not None and hasattr(acciones, "poner_marcador_en"):
            self._anadir(menu, _("Poner un &marcador aquí"),
                         lambda: acciones.poner_marcador_en(int(entrada.posicion)))
            puestas += 1
        return puestas + 1

    def _ordenes_de_marcador(self, menu, entrada, acciones) -> int:
        """Lo que se puede hacer con un marcador, una nota o un resaltado."""
        marcador = entrada.marcador
        menu.AppendSeparator()
        if marcador.es_nota:
            self._anadir(menu, _("&Editar la nota..."),
                         lambda: acciones.editar_nota_del_arbol(marcador))
            self._anadir(menu, _("Copiar la &nota"),
                         lambda: acciones.copiar_al_portapapeles(marcador.nota))
        else:
            self._anadir(menu, _("Escribir una &nota aquí..."),
                         lambda: acciones.editar_nota_del_arbol(marcador))
        if (marcador.fragmento or "").strip():
            self._anadir(menu, _("Copiar el &texto señalado"),
                         lambda: acciones.copiar_al_portapapeles(marcador.fragmento))
        menu.AppendSeparator()
        self._anadir(menu, _("&Quitar"),
                     lambda: acciones.quitar_marcador_del_arbol(marcador))
        return 3

    def _menu_de_rama(self, menu, entrada) -> int:
        """Lo que se puede hacer con **todos** los de una rama.

        Es lo que convierte el árbol en algo con lo que se trabaja: describir de
        una vez las ochenta imágenes de un cómic, o sacar la lista de todas las
        tablas de un manual, sin ir una por una.
        """
        acciones = self._acciones
        if acciones is None:
            return 0
        puestas = 0
        if entrada.clase:
            return self._ordenes_de_rama_propia(menu, entrada, acciones)
        if entrada.tipo in (TipoMarca.IMAGEN, TipoMarca.FIGURA):
            self._anadir(menu, _("&Describir todas las que falten con IA"),
                         acciones.describir_todo_del_arbol)
            menu.AppendSeparator()
            puestas += 1
        self._anadir(menu, _("&Copiar la lista de esta rama"),
                     lambda: acciones.copiar_al_portapapeles(
                         self._lista_de_la_rama(entrada)))
        self._anadir(menu, _("&Guardar la lista en un archivo..."),
                     lambda: acciones.guardar_lista_del_arbol(
                         entrada.rama, self._lista_de_la_rama(entrada)))
        return puestas + 2

    def _ordenes_de_rama_propia(self, menu, entrada, acciones) -> int:
        """Lo que se hace con **todos** los marcadores, notas o resaltados.

        La lista completa de cada clase ya tiene su ventana, con búsqueda y con
        exportación; desde aquí se abre esa, en vez de hacer una segunda a
        medias que acabaría comportándose distinto.
        """
        if entrada.clase == "resaltados":
            self._anadir(menu, _("Abrir la lista de &resaltados..."),
                         acciones.abrir_resaltados_del_arbol)
        else:
            self._anadir(menu, _("Abrir la lista de &marcadores y notas..."),
                         acciones.abrir_marcadores_del_arbol)
        menu.AppendSeparator()
        self._anadir(menu, _("&Copiar la lista de esta rama"),
                     lambda: acciones.copiar_al_portapapeles(
                         self._lista_de_la_rama(entrada)))
        self._anadir(menu, _("&Guardar la lista en un archivo..."),
                     lambda: acciones.guardar_lista_del_arbol(
                         entrada.rama, self._lista_de_la_rama(entrada)))
        menu.AppendSeparator()
        self._anadir(menu, _("&Quitar todos los de esta rama..."),
                     lambda: acciones.quitar_todos_del_arbol(
                         entrada.clase, self._marcadores_de(entrada.clase)))
        return 4

    def _marcadores_de(self, clase: str) -> list:
        """Los marcadores de una de las tres clases."""
        try:
            todos = list(self._marcadores() or [])
        except Exception:
            return []
        for nombre, es_de_esta in self.PROPIAS:
            if nombre == clase:
                return sorted((uno for uno in todos if es_de_esta(uno)),
                              key=lambda uno: uno.inicio)
        return []

    def _lista_de_la_rama(self, entrada) -> str:
        """El contenido de una rama, en texto, una entrada por línea.

        Se saca del documento y no de los nodos del árbol: la rama puede no
        estar desplegada —entonces no hay nodos— y de todas formas al llegar a
        tres mil se corta, y aquí interesa la lista entera.
        """
        if self.documento is None:
            return ""
        lineas = [entrada.rama]
        if entrada.clase:
            for uno in self._marcadores_de(entrada.clase):
                lineas.append("%3d%%  %s" % (
                    self.documento.porcentaje_en(uno.inicio),
                    self._rotulo_propio(uno)))
            return "\n".join(lineas)
        if entrada.tipo is None and not entrada.rama.startswith(_("Índice")):
            grupo = self.documento.marcas.encabezados
        elif entrada.tipo is None:
            return "\n".join([entrada.rama] + [
                "%s%s" % ("  " * una.nivel, una.titulo)
                for una in self.documento.indice_plano()])
        else:
            grupo = self.documento.marcas.grupo(entrada.tipo)
        for numero, marca in enumerate(grupo, start=1):
            lineas.append(self._rotulo(marca, entrada.tipo, numero))
        return "\n".join(lineas)

    def _al_recibir_foco(self, evento) -> None:
        """Coloca el árbol por donde va la lectura antes de entregar el foco."""
        evento.Skip()
        if self.documento is not None:
            wx.CallAfter(self._sincronizar_pendiente)

    def _sincronizar_pendiente(self) -> None:
        """Sincroniza con la posición que tenga ahora el documento."""
        try:
            self.sincronizar(int(self._posicion_actual()))
        except Exception as error:      # pragma: no cover - documento cerrándose
            log.debug("No se ha podido saber por dónde va la lectura: %s", error)

    def sincronizar(self, posicion: int) -> None:
        """Selecciona la entrada del índice bajo la que se está leyendo.

        Con :mod:`bisect` sobre las posiciones del índice, así que responde
        igual de rápido en un documento de diez apartados que en uno de mil.
        """
        if not self._referencias or self._sincronizando:
            return
        indice = bisect.bisect_right(self._referencias, int(posicion)) - 1
        if indice < 0:
            indice = 0
        nodo = self._nodos[indice]
        self._sincronizando = True
        try:
            padre = self.arbol.GetItemParent(nodo)
            while padre.IsOk() and padre != self.raiz:
                self.arbol.Expand(padre)
                padre = self.arbol.GetItemParent(padre)
            self.arbol.SelectItem(nodo)
            self.arbol.EnsureVisible(nodo)
        except Exception as error:      # pragma: no cover - árbol en construcción
            log.debug("No se ha podido sincronizar el árbol: %s", error)
        finally:
            self._sincronizando = False

    def enfocar(self) -> bool:
        """Lleva el foco al árbol."""
        if not self.IsShown():
            return False
        self.arbol.SetFocus()
        return True
