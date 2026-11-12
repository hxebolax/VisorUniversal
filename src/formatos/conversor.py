# -*- coding: utf-8 -*-
"""Conversor de XHTML a texto plano con marcas de estructura.

Este módulo es el corazón del rendimiento del visor.  Recibe el contenido de
un capítulo (un archivo XHTML del EPUB) y devuelve:

* el **texto plano** de ese capítulo, ya con los espacios normalizados;
* la lista de **marcas** (encabezados, enlaces, imágenes, listas, tablas...)
  con su posición dentro de ese texto;
* el **mapa de identificadores** (``id="..."``) a posiciones, necesario para
  que los enlaces internos y el índice del libro salten al punto exacto.

Decisiones de diseño que explican por qué es rápido:

* El análisis del XML lo hace **lxml** (libxml2, escrito en C).
* El recorrido se hace con ``iterwalk``, un iterador de eventos
  ``inicio``/``fin`` que evita la recursión en Python.
* La posición dentro del texto se mantiene **de forma incremental**: nunca se
  recalcula la longitud de lo escrito hasta el momento.  Esta es la
  diferencia entre un coste lineal y uno cuadrático.
* Los espacios se colapsan al vuelo con ``str.split()``, que se ejecuta en C.
* El espacio final de una línea se emite de forma **diferida**, lo que
  garantiza que la longitud registrada coincide siempre con el texto final.
"""

from __future__ import annotations

import re
from typing import NamedTuple

from lxml import etree

from nucleo import texto as util_texto
from nucleo.marcas import Marca, TipoMarca, tipo_de_encabezado
from nucleo.registro import obtener_registro

from . import matematicas
from . import tablas
from .lectura_xml import crear_parser_html, crear_parser_xml

log = obtener_registro(__name__)

#: A partir de cuántos bytes tiene sentido sospechar que un documento se ha
#: leído mal. Por debajo, un archivo con poco texto es simplemente un archivo
#: con poco texto.
_MINIMO_PARA_SOSPECHAR = 4000

#: Qué proporción del archivo tiene que ser texto como mínimo para no
#: sospechar. Es deliberadamente bajísima: una página web llena de marcas puede
#: tener un dos por ciento de texto y estar perfectamente leída, mientras que
#: una mal leída se queda en centésimas de eso.
_PROPORCION_MINIMA = 0.002

#: El ``<!DOCTYPE html>`` moderno, el de las páginas web sueltas.
_DOCTIPO_HTML5 = re.compile(rb"<!DOCTYPE\s+html\s*>", re.IGNORECASE)

#: La declaración de espacio de nombres que llevan los capítulos de un EPUB.
_ESPACIO_XHTML = b"http://www.w3.org/1999/xhtml"


def _es_html5_suelto(datos: bytes) -> bool:
    """Dice si esto es una página web guardada y no un capítulo de un libro."""
    cabecera = datos[:4000]
    if _DOCTIPO_HTML5.search(cabecera) is None:
        return False
    return _ESPACIO_XHTML not in cabecera


# ---------------------------------------------------------------------------
# Constantes de etiquetas
# ---------------------------------------------------------------------------

#: Etiquetas cuyo contenido nunca se muestra al lector.
IGNORADAS = frozenset({"script", "style", "noscript", "iframe", "object", "embed", "head", "svg"})

#: Etiquetas de bloque: al cerrarlas se termina la línea en curso.
BLOQUE = frozenset({
    "div", "p", "pre", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote",
    "ul", "ol", "li", "dl", "dt", "dd", "section", "article", "header",
    "footer", "nav", "aside", "main", "figure", "figcaption", "address",
    "hr", "table", "thead", "tbody", "tfoot", "tr", "td", "th", "caption",
    "body", "center", "form", "fieldset", "legend", "details", "summary",
})

#: Etiquetas que abren una lista.
LISTAS = frozenset({"ul", "ol"})

#: Correspondencia entre etiquetas de énfasis y su tipo de marca.
_ENFASIS = {
    "b": TipoMarca.NEGRITA,
    "strong": TipoMarca.NEGRITA,
    "i": TipoMarca.CURSIVA,
    "em": TipoMarca.CURSIVA,
    "u": TipoMarca.SUBRAYADO,
    "ins": TipoMarca.SUBRAYADO,
}

#: Texto que puede tener la llamada de una nota: un número de hasta cuatro
#: cifras o un signo de los que se usan para las notas, con o sin corchetes,
#: paréntesis o llaves alrededor.  Nada más: en cuanto lleva una palabra, es un
#: enlace normal.  Los números romanos se quedan fuera a propósito, porque un
#: «IV» casi siempre es un capítulo.
_LLAMADA_POR_SU_FORMA = re.compile(
    r"^[\[\(\{]?\s*(?:\d{1,4}|[*†‡§¶]{1,3})\s*[\]\)\}]?$")

#: Detecta entidades HTML que el analizador XML no conoce (``&nbsp;`` y
#: compañía).  Si aparece alguna, hay que usar el analizador de HTML, que sí
#: las entiende; de lo contrario el texto perdería caracteres en silencio.
_PATRON_ENTIDADES = re.compile(rb"&(?!amp;|lt;|gt;|quot;|apos;|#)[A-Za-z][A-Za-z0-9]*;")

#: Atributos donde puede venir el idioma de un elemento.  El primero es el
#: ``xml:lang`` con su espacio de nombres, que es el que obliga a poner el
#: XHTML; el segundo, el ``lang`` a secas del HTML de toda la vida.
_ATRIBUTOS_IDIOMA = (
    "{http://www.w3.org/XML/1998/namespace}lang",
    "lang",
)

#: Atributos donde puede venir el tipo semántico EPUB de un elemento.
_ATRIBUTOS_TIPO = (
    "{http://www.idpf.org/2007/ops}type",
    "epub:type",
    "role",
)


class ResultadoSeccion(NamedTuple):
    """Todo lo que se obtiene al convertir un capítulo del libro.

    Las posiciones son **locales** al capítulo; el analizador de EPUB las
    desplaza después al ensamblar el libro completo.
    """

    texto: str
    marcas: list[Marca]
    posiciones_id: dict[str, int]
    paginas: list[tuple[int, str]]


# ---------------------------------------------------------------------------
# Construcción de líneas
# ---------------------------------------------------------------------------

class ConstructorLineas:
    """Acumula el texto de salida y lleva la cuenta exacta de la posición.

    Reglas que garantizan que la posición registrada en una marca coincide
    con el texto definitivo:

    * Los espacios ya vienen colapsados al añadirse: no se vuelve a tocar la
      línea al cerrarla.
    * Un espacio al final de un fragmento no se escribe: queda «pendiente» y
      solo se materializa si después llega más texto en la misma línea.  Así
      ninguna línea termina en espacio y no hay que recortarla.
    * Las líneas que quedan vacías se descartan, igual que hace el navegador
      con los párrafos sin contenido.
    """

    __slots__ = ("lineas", "_partes", "_long_linea", "_long_total", "_espacio_pendiente", "_preservar")

    def __init__(self) -> None:
        self.lineas: list[str] = []
        self._partes: list[str] = []
        self._long_linea = 0
        self._long_total = 0
        self._espacio_pendiente = False
        self._preservar = 0

    @property
    def posicion(self) -> int:
        """Posición actual de escritura, en caracteres desde el inicio."""
        return self._long_total + self._long_linea

    @property
    def linea_vacia(self) -> bool:
        """Indica si todavía no se ha escrito nada en la línea en curso."""
        return self._long_linea == 0

    def preservar_espacios(self, activar: bool) -> None:
        """Activa o desactiva la conservación literal de espacios (``<pre>``)."""
        if activar:
            self._preservar += 1
        elif self._preservar > 0:
            self._preservar -= 1

    def agregar_texto(self, fragmento: str) -> None:
        """Añade texto del documento a la línea en curso, colapsando espacios."""
        if not fragmento:
            return
        if self._preservar:
            self._partes.append(fragmento)
            self._long_linea += len(fragmento)
            return
        if fragmento.isspace():
            # Un fragmento solo de espacios se convierte en un espacio
            # pendiente, que solo se escribirá si luego llega más texto.
            if self._long_linea:
                self._espacio_pendiente = True
            return
        palabras = fragmento.split()
        prefijo = " " if (self._espacio_pendiente or fragmento[0].isspace()) and self._long_linea else ""
        trozo = prefijo + " ".join(palabras)
        self._partes.append(trozo)
        self._long_linea += len(trozo)
        self._espacio_pendiente = fragmento[-1].isspace()

    def agregar_literal(self, fragmento: str) -> None:
        """Añade texto generado por el visor (viñetas, sangrías, rótulos).

        No se colapsa ni se recorta: se escribe exactamente como llega.
        """
        if not fragmento:
            return
        self._partes.append(fragmento)
        self._long_linea += len(fragmento)
        self._espacio_pendiente = False

    def terminar_linea(self) -> None:
        """Cierra la línea en curso y la añade al texto.

        Si la línea está vacía se descarta, de modo que el texto resultante
        no acumula líneas en blanco por cada ``<div>`` de maquetación.

        Y si lo que hay es **una letra capitular** —la inicial grande con la
        que empieza un capítulo, que muchos libros ponen en su propio bloque—
        la línea **no se cierra**: se deja abierta para que la inicial se pegue
        a lo que sigue.  Sin esto se lee «E. rase una vez», que es de las
        molestias más repetidas por quien lee con lector de pantalla.
        """
        if self._long_linea == 1 and self._es_capitular():
            return
        if self._long_linea == 0:
            self._espacio_pendiente = False
            if self._partes:
                self._partes.clear()
            return
        self.lineas.append("".join(self._partes))
        self._long_total += self._long_linea + 1  # el +1 es el salto de línea
        self._partes = []
        self._long_linea = 0
        self._espacio_pendiente = False

    def _es_capitular(self) -> bool:
        """Indica si lo que hay en la línea es una inicial suelta de capítulo.

        Se pide que sea **una sola letra y may\u00fascula**: cualquier otra cosa de
        un solo car\u00e1cter —un n\u00famero de p\u00e1gina, una vi\u00f1eta, un asterisco— es un
        elemento de verdad y juntarlo con el p\u00e1rrafo siguiente lo estropear\u00eda.
        """
        unico = "".join(self._partes)
        return len(unico) == 1 and unico.isalpha() and unico.isupper()

    def agregar_linea_completa(self, linea: str) -> None:
        """Inserta una línea ya terminada (por ejemplo, una fila de tabla).

        Se conserva literalmente para que los tabuladores y las celdas vacías
        no se pierdan.
        """
        self.lineas.append(linea)
        self._long_total += len(linea) + 1

    def obtener_texto(self) -> str:
        """Devuelve el texto completo acumulado."""
        return "\n".join(self.lineas)


class _EstiloLista:
    """Estado de numeración de una lista abierta (``<ol>`` o ``<ul>``)."""

    __slots__ = ("ordenada", "numero", "tipo")

    def __init__(self, ordenada: bool, inicio: str | None, tipo: str | None) -> None:
        self.ordenada = ordenada
        self.numero = 1
        self.tipo = "1"
        if ordenada:
            if inicio:
                try:
                    self.numero = int(inicio)
                except ValueError:
                    self.numero = 1
            if tipo:
                self.tipo = tipo


# ---------------------------------------------------------------------------
# Conversor
# ---------------------------------------------------------------------------

class ConversorXHTML:
    """Convierte un documento XHTML en texto plano con marcas.

    Una misma instancia puede reutilizarse para varios capítulos llamando de
    nuevo a :meth:`convertir`, lo que evita recrear los analizadores.

    :param tablas_en_linea: Si las tablas se vuelcan completas o se sustituyen
                            por un marcador.
    :param anunciar_imagenes_sin_texto: Si las imágenes sin texto alternativo
                                        aparecen igualmente como ``[Imagen]``.
                                        Conviene dejarlo activado para poder
                                        navegar hasta ellas y verlas.
    """

    def __init__(self, tablas_en_linea: bool = True, anunciar_imagenes_sin_texto: bool = True,
                 marcar_llamadas_de_nota: bool = False) -> None:
        self.tablas_en_linea = tablas_en_linea
        self.anunciar_imagenes_sin_texto = anunciar_imagenes_sin_texto
        self.marcar_llamadas_de_nota = marcar_llamadas_de_nota
        self._parser_xml = crear_parser_xml()
        self._parser_html = crear_parser_html()
        self._cache_nombres: dict[object, str] = {}

    # -- utilidades internas -------------------------------------------------

    def _nombre(self, etiqueta) -> str:
        """Nombre de etiqueta en minúsculas y sin espacio de nombres, con caché.

        El número de etiquetas distintas en un libro es pequeño (unas pocas
        decenas), así que la caché acierta prácticamente siempre y evita
        millones de operaciones de texto.
        """
        cacheado = self._cache_nombres.get(etiqueta)
        if cacheado is not None:
            return cacheado
        nombre = tablas.nombre_local(etiqueta)
        self._cache_nombres[etiqueta] = nombre
        return nombre

    def _analizar(self, datos: bytes) -> etree._Element | None:
        """Analiza el documento eligiendo el analizador adecuado.

        Se prefiere el analizador **XML**, que es más fiel a lo que trae un
        EPUB. Se cambia al de HTML en tres casos, y los tres son necesarios:

        1. Cuando hay entidades HTML como ``&nbsp;``, que el XML no conoce y
           descartaría en silencio.
        2. Cuando el documento es **HTML5 suelto**: lleva el ``<!DOCTYPE html>``
           moderno y **no** declara el espacio de nombres de XHTML. Eso es una
           página guardada del navegador, no un capítulo de un libro. El
           analizador XML, que perdona los errores, se la traga sin protestar y
           devuelve un árbol casi vacío: un artículo de la Wikipedia de
           doscientas cuarenta mil letras se quedaba en cuatrocientas.
        3. Cuando, pese a todo, el árbol que sale tiene mucho menos texto del
           que cabría esperar por el tamaño del archivo. Es la red de seguridad
           para lo que no encaje en las dos reglas anteriores.

        La segunda condición mira el espacio de nombres **a propósito**: un
        capítulo de EPUB 3 también lleva ``<!DOCTYPE html>``, y ese sí tiene que
        seguir leyéndose como XML o cambiaría lo que sale de todos los libros.
        """
        usar_html = (_PATRON_ENTIDADES.search(datos) is not None
                     or _es_html5_suelto(datos))
        if not usar_html:
            try:
                raiz = etree.fromstring(datos, self._parser_xml)
                if raiz is not None and not self._sospechosamente_vacio(raiz, datos):
                    return raiz
                if raiz is not None:
                    log.debug("El árbol XML sale casi vacío; se prueba con HTML")
            except etree.XMLSyntaxError as error:
                log.debug("El analizador XML falló (%s); se prueba con HTML", error)
        try:
            return etree.fromstring(datos, self._parser_html)
        except Exception as error:  # pragma: no cover - documento irrecuperable
            log.warning("No se pudo analizar la sección: %s", error)
            return None

    @staticmethod
    def _sospechosamente_vacio(raiz, datos: bytes) -> bool:
        """Dice si del árbol ha salido mucho menos texto del que había.

        Se compara con el tamaño del archivo y no con nada más fino porque lo
        que se busca es un desastre, no un matiz: un documento de cien mil
        bytes del que salen cien letras no está mal medido, está mal leído.
        """
        if len(datos) < _MINIMO_PARA_SOSPECHAR:
            return False
        try:
            texto = "".join(raiz.itertext())
        except Exception:                            # pragma: no cover
            return False
        return len(texto.strip()) < len(datos) * _PROPORCION_MINIMA

    @staticmethod
    def _idioma_de(elemento) -> str:
        """Código de idioma declarado en el elemento, en la forma de la norma.

        Los libros lo escriben de cualquier manera —«ES», «en_GB», «pt-br»—, y
        para poder compararlos entre sí y elegir una voz con ellos tienen que
        estar todos escritos igual: la lengua en minúsculas y la región en
        mayúsculas, que es lo que dice BCP 47.
        """
        for atributo in _ATRIBUTOS_IDIOMA:
            valor = (elemento.get(atributo) or "").strip()
            if not valor:
                continue
            partes = valor.replace("_", "-").split("-")
            if not partes[0]:
                continue
            codigo = partes[0].lower()
            if len(partes) > 1 and partes[1]:
                codigo += "-" + partes[1].upper()
            return codigo
        return ""

    @staticmethod
    def _tipo_semantico(elemento) -> str:
        """Devuelve el valor de ``epub:type`` o ``role`` en minúsculas."""
        for atributo in _ATRIBUTOS_TIPO:
            valor = elemento.get(atributo)
            if valor:
                return valor.lower()
        return ""

    @classmethod
    def _es_llamada_de_nota(cls, elemento) -> bool:
        """Indica si ese enlace es la llamada de una nota al pie.

        Se reconocen primero las tres formas en que un libro **lo dice**: el
        ``epub:type="noteref"`` del EPUB 3, el ``role="doc-noteref"`` de las
        recomendaciones de accesibilidad de la web, y la clase ``noteref`` o
        ``footnote`` de muchos EPUB 2, que son anteriores a las otras dos y
        siguen siendo la mayoría de lo que hay en las bibliotecas.

        Y si no lo dice ninguna, se mira **cómo está hecho**
        (:meth:`_parece_llamada_de_nota`), porque la inmensa mayoría de los
        libros anotados que circulan no lo declaran de ninguna de las tres
        maneras: son un enlace corriente a la sección de notas.
        """
        for atributo in _ATRIBUTOS_TIPO:
            valor = (elemento.get(atributo) or "").lower()
            if any(marca in valor for marca in
                   ("noteref", "footnote", "endnote", "rearnote")):
                return True
        clase = (elemento.get("class") or "").lower()
        if any(marca in clase for marca in
               ("noteref", "footnote", "endnote", "rearnote", "nota")):
            return True
        return cls._parece_llamada_de_nota(elemento)

    @classmethod
    def _parece_llamada_de_nota(cls, elemento) -> bool:
        """Reconoce una llamada de nota por su forma, no por lo que declare.

        Un libro anotado de verdad —unos discursos clásicos, un manual de
        matemáticas, una edición crítica— tiene cientos de llamadas de nota y
        casi nunca las declara: son un enlace normal a la sección de notas.
        Sin reconocerlas, la tecla de notas no encuentra ninguna, la de enlaces
        encuentra cientos, y las dos clases de número que salen en el texto —el
        de la nota y el de la cita, que en un clásico es universal— suenan y se
        anuncian igual.

        Se piden **tres** cosas a la vez, y las tres hacen falta:

        * Que apunte **dentro del documento**, a un sitio concreto: una llamada
          de nota lleva a su nota, no a una página web.
        * Que su texto sea **solo un número o un signo de nota**: si lleva
          palabras es un enlace normal.  Los números romanos quedan fuera a
          propósito: un «IV» suele ser un capítulo, no una nota.
        * Que vaya **entre corchetes o en superíndice**, que es como se
          escriben.  Sin esta condición, el índice onomástico de un libro
          —donde cada número de página es un enlace— se llenaría de notas que
          no lo son.

        Los **paréntesis** no cuentan por sí solos, y eso costó una prueba con
        un libro de verdad: en un texto técnico, «la ecuación (6)» es un enlace
        a la ecuación, no una nota, y los paréntesis son justo la forma normal
        de numerar ecuaciones.  Entre paréntesis y además en superíndice, sí.
        """
        destino = (elemento.get("href") or "").strip()
        if "#" not in destino or destino.lower().startswith(("http:", "https:", "mailto:")):
            return False
        rotulo = " ".join("".join(elemento.itertext()).split())
        if not _LLAMADA_POR_SU_FORMA.match(rotulo):
            return False
        if rotulo[:1] == "[":
            return True
        return cls._va_en_superindice(elemento)

    @staticmethod
    def _rotular_llamada(rotulo: str) -> str:
        """Convierte «[12]» en «[nota 12]» para que se oiga lo que es.

        Se conserva el número, que es lo que ata la llamada con su nota y lo
        que el lector necesita para buscarla.  Si la llamada no es un número
        —un asterisco, una daga— se dice solo «[nota]»: leer «nota asterisco»
        no añade nada.
        """
        from nucleo.idioma import _ as traducir

        numero = rotulo.strip().strip("[](){}").strip()
        if numero.isdigit():
            return traducir("[nota %s]") % numero
        return traducir("[nota]")

    @staticmethod
    def _va_en_superindice(elemento) -> bool:
        """Comprueba si el enlace está en superíndice, dentro o fuera.

        Los libros lo escriben de las dos maneras —``<sup><a>12</a></sup>`` y
        ``<a><sup>12</sup></a>``— y las dos quieren decir lo mismo.
        """
        padre = elemento.getparent()
        if padre is not None and tablas.nombre_local(padre.tag) in ("sup", "sub"):
            return True
        return any(tablas.nombre_local(hijo.tag) in ("sup", "sub") for hijo in elemento)

    # -- conversión principal ------------------------------------------------

    def convertir(self, datos: bytes) -> ResultadoSeccion:
        """Convierte el contenido de un capítulo a texto con marcas.

        :param datos: Bytes del archivo XHTML tal como vienen del EPUB.
        :return: Un :class:`ResultadoSeccion` con posiciones locales.
        """
        raiz = self._analizar(datos)
        if raiz is None:
            return ResultadoSeccion("", [], {}, [])

        # Los saltos de página del EPUB 3 se marcan con epub:type="pagebreak".
        # Comprobar en los bytes si la palabra aparece siquiera cuesta una
        # única búsqueda en C y evita interrogar tres atributos en cada uno de
        # los cientos de miles de elementos del capítulo.
        buscar_paginas = b"pagebreak" in datos
        # Lo mismo con el idioma: mirar dos atributos en cada elemento de un
        # capítulo cuesta, y la mayoría de los libros no cambian de idioma ni
        # una vez.
        buscar_idiomas = b"lang" in datos

        constructor = ConstructorLineas()
        marcas: list[Marca] = []
        posiciones_id: dict[str, int] = {}
        paginas: list[tuple[int, str]] = []

        # Estado del recorrido.
        en_cuerpo = False
        profundidad_ignorada = 0
        nivel_lista = 0
        pila_estilos: list[_EstiloLista] = []
        pila_listas: list[int | None] = []   # índice en «marcas» de cada lista abierta
        pila_enfasis: dict[int, list[int]] = {}
        pila_citas: list[int] = []
        # Cada entrada es (elemento que lo abrió, código, posición de inicio).
        pila_idiomas: list[tuple[object, str, int]] = []
        if buscar_idiomas:
            # El idioma del capítulo entero, el del <html>, se mete en la pila
            # sin elemento que lo cierre: así los párrafos que lo repiten no
            # dejan marca —serían una por párrafo y no dirían nada— y solo se
            # anota lo que de verdad cambia de idioma.
            idioma_raiz = self._idioma_de(raiz)
            if idioma_raiz:
                pila_idiomas.append((None, idioma_raiz, 0))
        profundidad_figura = 0
        # Índices de las marcas (encabezados y elementos de lista) cuya
        # longitud solo se conoce al cerrar la etiqueta correspondiente.
        pila_pendientes: list[int] = []
        # Bloques de código abiertos.  Un ``<pre>`` no se anida dentro de otro,
        # pero se lleva en pila igual que los demás por si un documento mal
        # formado lo intenta.
        pila_codigo: list[int] = []

        agregar_texto = constructor.agregar_texto
        agregar_literal = constructor.agregar_literal
        terminar_linea = constructor.terminar_linea
        nombre_de = self._nombre

        recorrido = etree.iterwalk(raiz, events=("start", "end"))
        for evento, elemento in recorrido:
            etiqueta = elemento.tag
            if not isinstance(etiqueta, str):
                # Comentario o instrucción de proceso: solo interesa el texto
                # que va detrás de él.
                if evento == "end" and elemento.tail and en_cuerpo and not profundidad_ignorada:
                    agregar_texto(elemento.tail)
                continue
            nombre = nombre_de(etiqueta)

            # ---------------------------------------------------------------
            # Elementos ignorados por completo (scripts, estilos, cabecera).
            # ---------------------------------------------------------------
            if profundidad_ignorada:
                if evento == "start":
                    if nombre in IGNORADAS:
                        profundidad_ignorada += 1
                else:
                    if nombre in IGNORADAS:
                        profundidad_ignorada -= 1
                    if not profundidad_ignorada and elemento.tail and en_cuerpo:
                        agregar_texto(elemento.tail)
                continue
            if evento == "start" and nombre in IGNORADAS:
                profundidad_ignorada = 1
                recorrido.skip_subtree()
                continue

            # ---------------------------------------------------------------
            # Apertura de elemento
            # ---------------------------------------------------------------
            if evento == "start":
                if nombre == "body":
                    en_cuerpo = True
                    if elemento.text:
                        agregar_texto(elemento.text)
                    continue
                if not en_cuerpo:
                    # Fuera de <body> no hay nada que mostrar, pero puede que
                    # el documento no tenga <body> en absoluto (fragmentos);
                    # en cuanto aparece contenido real se activa el cuerpo.
                    if nombre in BLOQUE or nombre in ("span", "a", "img"):
                        en_cuerpo = True
                    else:
                        continue

                identificador = elemento.get("id") or elemento.get("name")

                # --- idioma del fragmento -----------------------------------
                if buscar_idiomas:
                    idioma = self._idioma_de(elemento)
                    if idioma and idioma != (pila_idiomas[-1][1] if pila_idiomas else ""):
                        pila_idiomas.append((elemento, idioma, constructor.posicion))

                # --- salto de página semántico del EPUB 3 -------------------
                if buscar_paginas and "pagebreak" in self._tipo_semantico(elemento):
                    rotulo = (elemento.get("title") or "".join(elemento.itertext()).strip()
                              or (identificador or "").replace("page", "").strip("_- "))
                    paginas.append((constructor.posicion, rotulo))

                # --- fórmula matemática -------------------------------------
                # Va antes que nada porque dentro de una fórmula hay etiquetas
                # (mtable, mtr, mtd) que se llaman casi igual que las de una
                # tabla y que, sueltas, el conversor trataría como texto normal
                # y dejaría la fórmula convertida en una ristra de símbolos.
                if nombre == "math":
                    inicio = constructor.posicion
                    if identificador:
                        posiciones_id.setdefault(identificador, inicio)
                    leida = matematicas.a_texto(elemento)
                    agregar_texto(leida)
                    marcas.append(
                        Marca(TipoMarca.FORMULA, inicio, leida,
                              matematicas.a_html(elemento), 0,
                              constructor.posicion - inicio)
                    )
                    recorrido.skip_subtree()
                    # El texto que va detrás de la fórmula se recoge en el
                    # evento «end», que lxml sigue emitiendo aunque se haya
                    # saltado el subárbol.
                    continue

                # --- tabla --------------------------------------------------
                if nombre == "table":
                    terminar_linea()
                    inicio = constructor.posicion
                    if identificador:
                        posiciones_id.setdefault(identificador, inicio)
                    self._registrar_ids_internos(elemento, inicio, posiciones_id)
                    render = tablas.renderizar(elemento, self.tablas_en_linea)
                    longitud = 0
                    for linea in render.lineas:
                        constructor.agregar_linea_completa(linea)
                        longitud += len(linea) + 1
                    # La rejilla completa se guarda en el campo de referencia
                    # (que las tablas no usan para otra cosa) para que la
                    # ventana «ver tabla» pueda mostrarla aunque en el texto
                    # solo aparezca el marcador «[Tabla]».
                    rejilla = "\n".join("\t".join(fila) for fila in render.filas)
                    marcas.append(Marca(TipoMarca.TABLA, inicio, render.titulo, rejilla, 0, longitud))
                    recorrido.skip_subtree()
                    continue

                # --- separador horizontal -----------------------------------
                if nombre == "hr":
                    terminar_linea()
                    inicio = constructor.posicion
                    if identificador:
                        posiciones_id.setdefault(identificador, inicio)
                    agregar_literal(util_texto.LINEA_SEPARADOR)
                    terminar_linea()
                    marcas.append(
                        Marca(TipoMarca.SEPARADOR, inicio, "", "", 0, len(util_texto.LINEA_SEPARADOR))
                    )
                    continue

                if identificador:
                    posiciones_id.setdefault(identificador, constructor.posicion)

                # --- enlace -------------------------------------------------
                if nombre == "a":
                    rotulo = util_texto.colapsar_espacios("".join(elemento.itertext()))
                    if rotulo.strip():
                        destino = elemento.get("href") or ""
                        es_nota = self._es_llamada_de_nota(elemento)
                        # La llamada de una nota es un número suelto —«[12]»— y
                        # leído en voz alta suena igual que cualquier otro
                        # número del texto, que en una edición clásica es
                        # precisamente el de la cita.  Con esto se dice «nota
                        # 12», y así se distingue **oyendo el texto**, que es lo
                        # único que se oye en la lectura continua del lector de
                        # pantalla: los sonidos del programa van con el cursor,
                        # y en la lectura continua el cursor no se mueve.
                        if es_nota and self.marcar_llamadas_de_nota:
                            rotulo = self._rotular_llamada(rotulo)
                        inicio = constructor.posicion
                        agregar_texto(rotulo)
                        marcas.append(
                            Marca(TipoMarca.ENLACE, inicio, rotulo.strip(), destino, 0,
                                  constructor.posicion - inicio)
                        )
                        # Una llamada de nota al pie es un enlace, pero no uno
                        # cualquiera: se marca **además** como llamada de nota,
                        # de modo que siga activándose con Intro como cualquier
                        # enlace y a la vez se pueda saltar de nota en nota y
                        # leerla sin moverse del sitio.  En un libro anotado,
                        # las llamadas son la mitad de los enlaces y mezclarlas
                        # con los demás hace inservible la tecla de enlaces.
                        if es_nota:
                            marcas.append(
                                Marca(TipoMarca.NOTA_PIE, inicio, rotulo.strip(), destino,
                                      0, constructor.posicion - inicio)
                            )
                        self._registrar_ids_internos(elemento, inicio, posiciones_id)
                        recorrido.skip_subtree()
                        # El texto posterior al enlace (tail) se procesa en el
                        # evento «end», que lxml sigue emitiendo.
                        continue

                # --- imágenes y figuras -------------------------------------
                if nombre in ("img", "image", "figure"):
                    if nombre == "figure":
                        # La figura ya representa a la imagen que contiene, así
                        # que se anota para no anunciar las dos por separado.
                        profundidad_figura += 1
                        terminar_linea()
                        self._procesar_imagen(nombre, elemento, constructor, marcas)
                        terminar_linea()
                    elif not profundidad_figura:
                        self._procesar_imagen(nombre, elemento, constructor, marcas)
                        continue
                    else:
                        continue

                # --- encabezados --------------------------------------------
                if len(nombre) == 2 and nombre[0] == "h" and nombre[1] in "123456":
                    terminar_linea()
                    inicio = constructor.posicion
                    if identificador:
                        posiciones_id[identificador] = inicio
                    rotulo = util_texto.colapsar_espacios("".join(elemento.itertext())).strip()
                    if rotulo:
                        nivel = int(nombre[1])
                        # La longitud definitiva se conoce al cerrar la etiqueta,
                        # así que se apunta el índice de la marca para completarla.
                        pila_pendientes.append(len(marcas))
                        marcas.append(Marca(tipo_de_encabezado(nivel), inicio, rotulo, "", nivel))
                    else:
                        pila_pendientes.append(-1)
                    if elemento.text:
                        agregar_texto(elemento.text)
                    continue

                # --- listas --------------------------------------------------
                if nombre in LISTAS:
                    nivel_lista += 1
                    pila_estilos.append(
                        _EstiloLista(nombre == "ol", elemento.get("start"), elemento.get("type"))
                    )
                    elementos = sum(1 for hijo in elemento if nombre_de(hijo.tag) == "li")
                    if elementos:
                        terminar_linea()
                        inicio = constructor.posicion
                        if identificador:
                            posiciones_id[identificador] = inicio
                        pila_listas.append(len(marcas))
                        marcas.append(Marca(TipoMarca.LISTA, inicio, "", "", elementos, 0))
                    else:
                        pila_listas.append(None)
                    if elemento.text:
                        agregar_texto(elemento.text)
                    continue

                if nombre == "li":
                    terminar_linea()
                    inicio = constructor.posicion
                    if identificador:
                        posiciones_id[identificador] = inicio
                    rotulo = util_texto.colapsar_espacios("".join(elemento.itertext())).strip()
                    pila_pendientes.append(len(marcas))
                    marcas.append(
                        Marca(TipoMarca.ELEMENTO_LISTA, inicio, rotulo, "", max(nivel_lista, 1))
                    )
                    agregar_literal("  " * max(nivel_lista - 1, 0))
                    if pila_estilos and pila_estilos[-1].ordenada:
                        estilo = pila_estilos[-1]
                        agregar_literal(
                            util_texto.formatear_elemento_lista(estilo.numero, estilo.tipo) + ". "
                        )
                        estilo.numero += 1
                    else:
                        agregar_literal(util_texto.vinneta_para_nivel(max(nivel_lista, 1)) + " ")
                    if elemento.text:
                        agregar_texto(elemento.text)
                    continue

                # --- citas en bloque ------------------------------------------
                if nombre == "blockquote":
                    terminar_linea()
                    pila_citas.append(constructor.posicion)
                    if elemento.text:
                        agregar_texto(elemento.text)
                    continue

                # --- saltos de línea y texto preformateado ---------------------
                if nombre == "br":
                    # El texto posterior (tail) lo añade el evento de cierre,
                    # que lxml emite igualmente para los elementos vacíos.
                    terminar_linea()
                    continue
                if nombre == "pre":
                    terminar_linea()
                    # El bloque de código se marca como elemento propio: es lo
                    # que permite saltar de uno a otro, verlo aparte y copiarlo
                    # entero.  El lenguaje, si el documento lo declara, viaja en
                    # la referencia de la marca.
                    pila_codigo.append(len(marcas))
                    marcas.append(Marca(TipoMarca.CODIGO, constructor.posicion, "",
                                        self._lenguaje_del_codigo(elemento), 0, 0))
                    constructor.preservar_espacios(True)
                elif nombre == "code":
                    constructor.preservar_espacios(True)

                # --- énfasis --------------------------------------------------
                tipo_enfasis = _ENFASIS.get(nombre)
                if tipo_enfasis is not None:
                    pila_enfasis.setdefault(int(tipo_enfasis), []).append(constructor.posicion)

                if elemento.text:
                    agregar_texto(elemento.text)
                continue

            # ---------------------------------------------------------------
            # Cierre de elemento
            # ---------------------------------------------------------------
            if not en_cuerpo:
                continue

            if nombre == "pre":
                terminar_linea()
                constructor.preservar_espacios(False)
                if pila_codigo:
                    indice = pila_codigo.pop()
                    marca = marcas[indice]
                    marcas[indice] = marca._replace(
                        longitud=max(constructor.posicion - marca.posicion, 0))
            elif nombre == "code":
                constructor.preservar_espacios(False)
            else:
                tipo_enfasis = _ENFASIS.get(nombre)
                if tipo_enfasis is not None:
                    pila = pila_enfasis.get(int(tipo_enfasis))
                    if pila:
                        inicio = pila.pop()
                        longitud = constructor.posicion - inicio
                        if longitud > 0:
                            marcas.append(Marca(tipo_enfasis, inicio, "", "", 0, longitud))
                if nombre == "li" or (len(nombre) == 2 and nombre[0] == "h" and nombre[1] in "123456"):
                    # Se completa la longitud de la marca abierta al empezar
                    # la etiqueta, ahora que ya se sabe cuánto texto ocupa.
                    if pila_pendientes:
                        indice = pila_pendientes.pop()
                        if indice >= 0:
                            marca = marcas[indice]
                            marcas[indice] = marca._replace(
                                longitud=max(constructor.posicion - marca.posicion, 0)
                            )
                if nombre in BLOQUE:
                    terminar_linea()

            if nombre in LISTAS:
                nivel_lista = max(nivel_lista - 1, 0)
                if pila_estilos:
                    pila_estilos.pop()
                if pila_listas:
                    indice = pila_listas.pop()
                    if indice is not None:
                        terminar_linea()
                        marca = marcas[indice]
                        marcas[indice] = marca._replace(
                            longitud=max(constructor.posicion - marca.posicion, 0)
                        )
            elif nombre == "blockquote" and pila_citas:
                inicio = pila_citas.pop()
                longitud = max(constructor.posicion - inicio, 0)
                if longitud > 0:
                    marcas.append(Marca(TipoMarca.CITA, inicio, "", "", 0, longitud))
            elif nombre == "figure" and profundidad_figura:
                profundidad_figura -= 1

            if pila_idiomas and pila_idiomas[-1][0] is elemento:
                _abridor, codigo, inicio = pila_idiomas.pop()
                longitud = max(constructor.posicion - inicio, 0)
                if longitud > 0:
                    marcas.append(Marca(TipoMarca.IDIOMA, inicio, codigo, "", 0, longitud))

            if elemento.tail:
                agregar_texto(elemento.tail)

        terminar_linea()
        # Un ``<pre>`` vacío —que los hay, usados como separación— no es un
        # bloque de código.  Se descarta aquí y no al cerrarlo, porque quitar
        # una marca en mitad del recorrido correría los índices que otras
        # etiquetas todavía abiertas tienen apuntados.
        marcas = [marca for marca in marcas
                  if marca.tipo is not TipoMarca.CODIGO or marca.longitud > 0]
        return ResultadoSeccion(constructor.obtener_texto(), marcas, posiciones_id, paginas)

    # -- auxiliares ----------------------------------------------------------

    @staticmethod
    def _lenguaje_del_codigo(elemento) -> str:
        """Lenguaje declarado de un bloque de código, si lo declara.

        Es la costumbre de Markdown y de la mayoría de los generadores de
        documentación: ``<pre><code class="language-python">``.  Sirve para
        poder decir «bloque de código Python» en vez de «bloque de código», que
        en un manual con ejemplos en tres lenguajes es información de verdad.
        """
        for hijo in list(elemento)[:1]:
            clases = str(hijo.get("class") or "")
            for clase in clases.split():
                for prefijo in ("language-", "lang-", "brush:", "highlight-"):
                    if clase.lower().startswith(prefijo):
                        return clase[len(prefijo):].strip(": ")[:30]
        return ""

    def _procesar_imagen(self, nombre: str, elemento, constructor: ConstructorLineas,
                         marcas: list[Marca]) -> None:
        """Inserta el texto que representa una imagen o figura.

        Se busca la descripción en ``alt``, ``aria-label``, ``aria-describedby``
        o ``title``; en una ``<figure>`` se recurre además a su ``<figcaption>``.
        Si no hay ninguna descripción se inserta ``[Imagen]`` a secas, de modo
        que la imagen siga siendo localizable y visualizable.
        """
        descripcion = ""
        for atributo in ("alt", "aria-label", "aria-description", "title"):
            valor = elemento.get(atributo)
            if valor and valor.strip():
                descripcion = util_texto.colapsar_espacios(valor).strip()
                break
        origen = (
            elemento.get("src")
            or elemento.get("{http://www.w3.org/1999/xlink}href")
            or elemento.get("href")
            or ""
        )
        es_figura = nombre == "figure"
        # Descripción que se usará al anunciar el elemento durante la
        # navegación.  En una figura puede venir del pie, que además se
        # leerá a continuación como texto normal: por eso el pie no se
        # inserta también dentro del rótulo, para no repetirlo.
        anuncio = descripcion
        if es_figura:
            for hijo in elemento.iter():
                nombre_hijo = self._nombre(hijo.tag)
                if not anuncio and nombre_hijo == "figcaption":
                    anuncio = util_texto.colapsar_espacios("".join(hijo.itertext())).strip()
                if not origen and nombre_hijo in ("img", "image"):
                    origen = hijo.get("src") or hijo.get("{http://www.w3.org/1999/xlink}href") or ""
                if anuncio and origen:
                    break
        if not descripcion and not anuncio and not self.anunciar_imagenes_sin_texto:
            return
        etiqueta = "Figura" if es_figura else "Imagen"
        rotulo = "[%s: %s]" % (etiqueta, descripcion) if descripcion else "[%s]" % etiqueta
        if not constructor.linea_vacia:
            constructor.agregar_literal(" ")
        inicio = constructor.posicion
        constructor.agregar_literal(rotulo)
        tipo = TipoMarca.FIGURA if es_figura else TipoMarca.IMAGEN
        # El nivel se usa aquí como bandera: 1 si la imagen traía texto
        # alternativo o pie, 0 si no.  Es lo que después permite decir cuántas
        # imágenes del documento se han quedado sin describir, que sin esto
        # habría que adivinar comparando el rótulo con la palabra «Imagen».
        marcas.append(Marca(tipo, inicio, anuncio or descripcion or etiqueta, origen,
                            1 if (descripcion or anuncio) else 0, len(rotulo)))

    def _registrar_ids_internos(self, elemento, posicion: int, destino: dict[str, int]) -> None:
        """Registra los ``id`` de los descendientes de un elemento no recorrido.

        Los enlaces y las tablas se vuelcan de una sola vez sin recorrer su
        interior, así que sus identificadores internos se anotarían nunca.
        Se les asigna la posición del elemento contenedor, que es el destino
        correcto cuando el índice del libro apunta a uno de ellos.
        """
        for descendiente in elemento.iterdescendants():
            identificador = descendiente.get("id") if isinstance(descendiente.tag, str) else None
            if identificador:
                destino.setdefault(identificador, posicion)
