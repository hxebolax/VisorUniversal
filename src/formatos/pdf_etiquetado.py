# -*- coding: utf-8 -*-
"""Estructura de los PDF etiquetados: leer un PDF como se lee un EPUB.

Un PDF corriente no tiene estructura: es una lista de instrucciones para pintar
letras en una hoja.  Sacar el texto de ahí da un churro de líneas donde no se
sabe qué era un título, qué una celda de una tabla y qué el encabezado de
página que se repite doscientas veces.  Eso es lo que convierte al PDF en el
formato más incómodo de leer con un lector de pantalla.

Pero desde PDF 1.4 existe el **PDF etiquetado** (*tagged PDF*), y desde 2012 la
norma **PDF/UA** (ISO 14289-1) que lo exige: además de las instrucciones de
dibujo, el archivo lleva un **árbol de estructura** paralelo —el
``StructTreeRoot``— que dice exactamente lo mismo que dice el HTML de una
página web: esto es un ``H2``, esto un párrafo, esto una tabla con su fila de
encabezados, esta imagen se describe así.  Es lo que hace que Adobe Reader o
NVDA puedan recorrer un PDF por encabezados, y es lo que este módulo lee.

La idea es la de todo el programa: **no se inventa nada**.  Se traduce el árbol
de estructura del PDF a XHTML —que es su equivalente casi exacto— y se le pasa
al conversor de siempre (:mod:`formatos.conversor`), el mismo que procesa los
EPUB.  A partir de ahí un PDF etiquetado se navega igual que un libro: con H
los encabezados, con T las tablas, con L las listas, con Q las citas, con I las
imágenes, con F7 la lista de elementos y con Ctrl+H el visor web accesible.

Qué se aprovecha del árbol
--------------------------

* **Encabezados** (``H1``..``H6``, y ``H`` deduciendo el nivel del anidamiento).
* **Párrafos**, **citas en bloque** (``BlockQuote``) y **código** (``Code``).
* **Listas** (``L``, ``LI``, ``Lbl``, ``LBody``), ordenadas o no según el
  atributo ``ListNumbering`` o la forma de sus viñetas.
* **Tablas** (``Table``, ``THead``, ``TBody``, ``TFoot``, ``TR``, ``TH``,
  ``TD``) con ``Scope``, ``ColSpan``, ``RowSpan`` y el ``Summary`` como título.
* **Imágenes y figuras** (``Figure``) con su texto alternativo ``Alt``.
* **Enlaces** (``Link``), cruzados con las anotaciones de la página para saber
  a dónde llevan: a una dirección de Internet o a otra página del documento.
* **Notas al pie** (``Note``) y sus llamadas (``Reference``), enlazadas entre
  sí por su número para que Alt+Mayús+N pueda leerlas.
* **Índice del propio documento** (``TOC``, ``TOCI``) y el idioma de cada
  fragmento (``Lang``), que es lo que permite que un párrafo en inglés dentro
  de un informe en español se anuncie como tal.

Y sobre todo, lo que **no** se aprovecha: todo lo que el PDF marca como
*artefacto* —encabezados y pies de página, números de página, filetes, marcas
de agua— se queda fuera del árbol y por tanto fuera del texto.  Solo con eso,
un informe de doscientas páginas se libra de doscientas repeticiones de su
propio título.

Cómo se saca el texto de cada etiqueta
--------------------------------------

El árbol no contiene texto: contiene **números de contenido marcado** (los
*MCID*).  El texto está en la página, y cada trozo lleva pegado el MCID al que
pertenece.  Así que hay dos recorridos por página:

1. Los objetos de la página (``FPDFPage_CountObjects``), preguntando a cada uno
   su MCID (``FPDFPageObj_GetMarkedContentID``) y su texto
   (``FPDFTextObj_GetText``).  Sale un diccionario MCID → texto.
2. El árbol de estructura, que se traduce a XHTML poniendo en cada etiqueta el
   texto de los MCID que cuelgan de ella.

Todo con **pypdfium2**, que es el motor de Chrome: no hace falta ninguna
biblioteca nueva ni cambiar la licencia del programa.
"""

from __future__ import annotations

import ctypes
import re
from typing import NamedTuple

from nucleo.registro import obtener_registro

from .ensamblador import escapar

log = obtener_registro(__name__)

#: Profundidad máxima a la que se desciende en el árbol de estructura.  Un
#: árbol legítimo no pasa de veinte o treinta niveles; un archivo dañado puede
#: traer ciclos, y sin tope el recorrido se comería la pila.
PROFUNDIDAD_MAXIMA = 60

#: Proporción del texto de la página que el árbol tiene que cubrir para darlo
#: por bueno.  Por debajo de esto el etiquetado está incompleto —hay contenido
#: de verdad fuera del árbol— y se prefiere el texto plano de siempre, que al
#: menos no pierde nada.  No es 1,0 porque los artefactos (encabezados y pies)
#: se quedan fuera a propósito y son texto que no cuenta.
COBERTURA_MINIMA = 0.55

#: Etiquetas de agrupación que no aportan nada al texto: se atraviesan y ya.
TRANSPARENTES = frozenset({
    "Document", "DocumentFragment", "Part", "Art", "Article", "Sect", "Section",
    "Div", "NonStruct", "Private", "LBody", "Annot", "Ruby", "RB", "Warichu",
    "WT", "Form",
})

#: Etiquetas que abren y cierran una sección lógica.  Sirven para deducir el
#: nivel de un encabezado ``H`` sin número, que en PDF significa «el que le
#: toque por dónde está».
SECCIONADORAS = frozenset({"Part", "Art", "Article", "Sect", "Section"})

#: Traducción directa de etiqueta PDF a etiqueta HTML.  Es casi toda la norma:
#: el vocabulario de estructura del PDF se diseñó calcado del de HTML, y ahí
#: está la suerte de todo esto.
EQUIVALENTES = {
    "P": "p",
    "H1": "h1", "H2": "h2", "H3": "h3", "H4": "h4", "H5": "h5", "H6": "h6",
    # PDF 2.0 permite niveles por encima de seis; HTML no, así que se recortan.
    "H7": "h6", "H8": "h6", "H9": "h6",
    "Title": "h1",
    "BlockQuote": "blockquote",
    "Quote": "q",
    "Code": "code",
    "Caption": "caption",
    "Table": "table",
    "THead": "thead", "TBody": "tbody", "TFoot": "tfoot",
    "TR": "tr", "TH": "th", "TD": "td",
    "LI": "li",
    "TOC": "ul", "TOCI": "li",
    "Index": "div",
    "Aside": "aside",
    "BibEntry": "p",
    "Span": "span",
    "Em": "em", "Strong": "strong",
    "Sub": "sub", "Sup": "sup",
    "RT": "span", "RP": "span", "WP": "span",
}

#: Valores de ``ListNumbering`` que significan «lista numerada».
NUMERACIONES_ORDENADAS = frozenset({
    "decimal", "upperroman", "lowerroman", "upperalpha", "loweralpha", "ordered",
})

#: Etiqueta de lista que sí es un número o una letra («3.», «b)», «iv.»).  Con
#: una de estas la lista se da por ordenada y se deja que el conversor la
#: numere él, que es lo que hace en un EPUB.
_ETIQUETA_ORDINAL = re.compile(
    r"^\s*[(\[]?(\d{1,3}|[a-zA-Z]|[ivxlcdmIVXLCDM]{1,6})[.)\]]?\s*$")

#: Número con el que empieza una nota al pie o una llamada de nota.  Es lo que
#: permite emparejar la llamada del texto con la nota del pie de la página.
_NUMERO_INICIAL = re.compile(r"^[\s(\[]*(\d{1,4})")

#: Texto de una llamada de nota: corto y básicamente un número o un símbolo.
#: Sirve para distinguir un ``Reference`` que es una llamada de nota de uno que
#: es una cita bibliográfica entera.
_LLAMADA_CORTA = re.compile(r"^[\s(\[]*[\d*†‡§]{1,4}[)\].\s]*$")


# ---------------------------------------------------------------------------
# Acceso al API de PDFium
# ---------------------------------------------------------------------------

def _cadena(funcion, *argumentos) -> str:
    """Lee una cadena UTF-16 de las que devuelve PDFium con el patrón habitual.

    Todas estas funciones se llaman dos veces: la primera con un búfer nulo,
    que devuelve cuántos bytes hacen falta (terminador incluido), y la segunda
    con el búfer ya del tamaño justo.
    """
    try:
        largo = funcion(*argumentos, None, 0)
    except Exception:
        return ""
    if not largo or largo <= 2:
        return ""
    buffer = ctypes.create_string_buffer(largo)
    funcion(*argumentos, buffer, largo)
    return buffer.raw[:largo].decode("utf-16-le", "replace").rstrip("\x00")


def _texto_de_objeto(objeto, pagina_texto) -> str:
    """Texto de un objeto de texto de la página, con su codificación resuelta.

    Se le pasa la «página de texto» porque es la que sabe traducir los códigos
    de la fuente a caracteres de verdad: sin ella saldrían los índices internos
    del tipo de letra en lugar de las letras.
    """
    from pypdfium2 import raw as C

    largo = C.FPDFTextObj_GetText(objeto, pagina_texto, None, 0)
    if not largo or largo <= 2:
        return ""
    buffer = ctypes.create_string_buffer(largo)
    C.FPDFTextObj_GetText(
        objeto, pagina_texto,
        ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ushort)), largo)
    return buffer.raw[:largo].decode("utf-16-le", "replace").rstrip("\x00")


def _atributo(elemento, nombre: str) -> str:
    """Devuelve un atributo de texto del elemento (``Scope``, ``Summary``...)."""
    from pypdfium2 import raw as C

    return _cadena(C.FPDF_StructElement_GetStringAttribute, elemento,
                   nombre.encode("ascii"))


def _numero(elemento, nombre: str) -> int:
    """Devuelve un atributo numérico del elemento (``ColSpan``, ``RowSpan``).

    No hay una función directa para esto: hay que recorrer los diccionarios de
    atributos del elemento buscando el nombre y pedir su valor como número.
    Devuelve 0 si el atributo no está.
    """
    from pypdfium2 import raw as C

    for indice in range(max(C.FPDF_StructElement_GetAttributeCount(elemento), 0)):
        atributos = C.FPDF_StructElement_GetAttributeAtIndex(elemento, indice)
        if not atributos:
            continue
        valor = C.FPDF_StructElement_Attr_GetValue(atributos, nombre.encode("ascii"))
        if not valor:
            continue
        resultado = ctypes.c_float(0)
        if C.FPDF_StructElement_Attr_GetNumberValue(valor, ctypes.byref(resultado)):
            return int(resultado.value)
    return 0


def normalizar_idioma(codigo: str) -> str:
    """Deja un código de idioma en la forma que usa la web: ``es``, ``en-GB``.

    Los PDF los escriben de cualquier manera —«ES», «EN-GB», «pt-br»—, y para
    poder compararlos y elegir una voz con ellos tienen que estar todos
    escritos igual: la lengua en minúsculas y la región en mayúsculas, que es
    lo que dice la norma BCP 47.
    """
    partes = (codigo or "").strip().replace("_", "-").split("-")
    if not partes or not partes[0]:
        return ""
    resultado = partes[0].lower()
    if len(partes) > 1 and partes[1]:
        resultado += "-" + partes[1].upper()
    return resultado


# ---------------------------------------------------------------------------
# Lo que se sabe de una página antes de recorrer su árbol
# ---------------------------------------------------------------------------

class ContextoPagina:
    """Todo lo que hay que saber de una página para traducir su estructura.

    Se construye una vez por página y se consulta desde el recorrido del árbol.
    """

    __slots__ = ("numero", "documento", "pagina", "textos", "limites", "bordes",
                 "caracteres")

    def __init__(self, documento, pagina, numero: int) -> None:
        #: Manejadores de PDFium, que hacen falta para resolver los enlaces.
        self.documento = documento
        self.pagina = pagina
        #: Número de página empezando en 1.
        self.numero = numero
        #: MCID → texto de la página que le corresponde.
        self.textos: dict[int, str] = {}
        #: MCID → rectángulo que ocupa, en el sistema de coordenadas de la
        #: página.  Sirve para dos cosas: recortar las figuras y averiguar a
        #: dónde lleva un enlace.
        self.limites: dict[int, tuple[float, float, float, float]] = {}
        #: MCID → rectángulo del primer y del último trozo que lo componen.  Con
        #: ellos se sabe si entre dos contenidos marcados seguidos hace falta un
        #: espacio, que es lo que evita leer «Solucióncomún».
        self.bordes: dict[int, tuple] = {}
        #: Caracteres de texto marcado que tiene la página en total.
        self.caracteres = 0

    def texto_de(self, mcid: int) -> str:
        """Texto de un contenido marcado, o cadena vacía si no es de esta página."""
        return self.textos.get(mcid, "")

    def rectangulo_de(self, mcids) -> tuple[float, float, float, float] | None:
        """Rectángulo que engloba a todos esos contenidos marcados."""
        union = None
        for mcid in mcids:
            rectangulo = self.limites.get(mcid)
            if rectangulo is None:
                continue
            if union is None:
                union = rectangulo
            else:
                union = (min(union[0], rectangulo[0]), min(union[1], rectangulo[1]),
                         max(union[2], rectangulo[2]), max(union[3], rectangulo[3]))
        return union

    def enlace_en(self, rectangulo) -> str:
        """Destino del enlace que hay bajo ese rectángulo, si hay alguno.

        El árbol de estructura marca *dónde* está un enlace, pero no a dónde
        lleva: eso vive en las anotaciones de la página, que son otra lista
        aparte.  El puente entre las dos es la posición, así que se pregunta
        por el punto que ocupa el texto del enlace.

        Se prueban tres puntos —el principio, el medio y el final del renglón—
        porque la anotación no siempre cubre todo el texto que el árbol marca
        como enlace, y con uno solo se perderían los que la tienen recortada.
        """
        from pypdfium2 import raw as C

        if rectangulo is None:
            return ""
        izquierda, abajo, derecha, arriba = rectangulo
        medio = (abajo + arriba) / 2.0
        for x in (izquierda + 1.0, (izquierda + derecha) / 2.0, derecha - 1.0):
            anotacion = C.FPDFLink_GetLinkAtPoint(self.pagina, x, medio)
            if not anotacion:
                continue
            destino = _destino_de_enlace(self.documento, anotacion)
            if destino:
                return destino
        return ""


def contexto_de_pagina(documento, pagina, pagina_texto, numero: int) -> ContextoPagina:
    """Recorre los objetos de una página y monta su :class:`ContextoPagina`.

    El recorrido es uno solo y saca a la vez las dos cosas que hacen falta: el
    texto de cada contenido marcado y el rectángulo que ocupa, que es lo que
    después permite recortar una figura para enseñarla y averiguar a dónde
    lleva un enlace.
    """
    from pypdfium2 import raw as C

    contexto = ContextoPagina(documento, pagina, numero)
    total = C.FPDFPage_CountObjects(pagina)
    piezas: dict[int, list[str]] = {}
    ultimo: dict[int, tuple[str, tuple[float, float, float, float] | None]] = {}
    for indice in range(max(total, 0)):
        objeto = C.FPDFPage_GetObject(pagina, indice)
        if not objeto:
            continue
        mcid = C.FPDFPageObj_GetMarkedContentID(objeto)
        if mcid < 0:
            # Artefacto o contenido sin marcar: no pertenece a la estructura.
            continue
        rectangulo = _limites_de(objeto)
        _acumular_limites(contexto, mcid, rectangulo)
        if C.FPDFPageObj_GetType(objeto) != C.FPDF_PAGEOBJ_TEXT:
            continue
        fragmento = _texto_de_objeto(objeto, pagina_texto)
        if not fragmento:
            continue
        anterior_texto, anterior_rectangulo = ultimo.get(mcid, ("", None))
        separador = _separacion(anterior_texto, anterior_rectangulo,
                                fragmento, rectangulo)
        if separador:
            piezas.setdefault(mcid, []).append(separador)
            contexto.caracteres += len(separador)
        piezas.setdefault(mcid, []).append(fragmento)
        contexto.caracteres += len(fragmento)
        ultimo[mcid] = (fragmento, rectangulo)
        primero, _ = contexto.bordes.get(mcid, (None, None))
        contexto.bordes[mcid] = (primero or rectangulo, rectangulo)
    for mcid, partes in piezas.items():
        contexto.textos[mcid] = "".join(partes)
    return contexto


def _separacion(anterior: str, rectangulo_anterior, siguiente: str, rectangulo) -> str:
    """Decide si entre dos trozos de texto seguidos falta un espacio.

    Dentro de un mismo contenido marcado, el texto viene partido en un objeto
    por renglón, y a veces por columna: una entrada de índice son dos objetos,
    el título y el número de página, con los puntitos de relleno en medio, que
    son un artefacto y desaparecen.  Sin esta comprobación quedaría
    «Resumen ejecutivo10».

    La mayoría de los PDF dejan ya el espacio al final de cada trozo, así que
    esto solo actúa cuando de verdad falta: se mira si los dos rectángulos van
    en el mismo renglón y están separados, o si están en renglones distintos.
    """
    if not anterior or not siguiente:
        return ""
    if anterior[-1].isspace() or siguiente[0].isspace():
        return ""
    if anterior.endswith(("-", "‐", "­")):
        # Palabra partida a final de renglón: pegarla es justo lo que toca.
        return ""
    if rectangulo_anterior is None or rectangulo is None:
        return ""
    alto = min(rectangulo_anterior[3] - rectangulo_anterior[1],
               rectangulo[3] - rectangulo[1])
    solapan = (min(rectangulo_anterior[3], rectangulo[3])
               - max(rectangulo_anterior[1], rectangulo[1])) > alto * 0.5
    if not solapan:
        return " "                       # renglones distintos
    # El hueco se mide **en proporción a la letra**, no en puntos absolutos.
    # Un espacio ocupa alrededor de un tercio del cuerpo de la fuente, así que
    # con una medida fija pasaba lo siguiente: en un título grande, la
    # separación normal entre letras superaba el punto y medio y se colaban
    # espacios dentro de las palabras.  Ese es el fallo de «I NSTITUTO», que
    # aparece en los documentos compuestos en versalitas, donde la inicial va
    # unos puntos más grande y por tanto más separada.
    return " " if rectangulo[0] - rectangulo_anterior[2] > max(1.5, alto * 0.22) else ""


def _limites_de(objeto):
    """Rectángulo que ocupa un objeto de la página, o ``None`` si no tiene."""
    from pypdfium2 import raw as C

    izquierda = ctypes.c_float(0)
    abajo = ctypes.c_float(0)
    derecha = ctypes.c_float(0)
    arriba = ctypes.c_float(0)
    if not C.FPDFPageObj_GetBounds(objeto, ctypes.byref(izquierda), ctypes.byref(abajo),
                                   ctypes.byref(derecha), ctypes.byref(arriba)):
        return None
    resultado = (izquierda.value, abajo.value, derecha.value, arriba.value)
    if resultado[2] <= resultado[0] or resultado[3] <= resultado[1]:
        return None
    return resultado


def _acumular_limites(contexto: ContextoPagina, mcid: int, nuevo) -> None:
    """Amplía el rectángulo asociado a un MCID con el de un objeto más.

    Una figura suele estar hecha de muchos objetos —una imagen de fondo, unas
    líneas, unos rótulos—, todos con el mismo MCID, y un párrafo, de un objeto
    por renglón.  El rectángulo que interesa es el que los engloba a todos.
    """
    if nuevo is None:
        return
    anterior = contexto.limites.get(mcid)
    if anterior is None:
        contexto.limites[mcid] = nuevo
    else:
        contexto.limites[mcid] = (
            min(anterior[0], nuevo[0]), min(anterior[1], nuevo[1]),
            max(anterior[2], nuevo[2]), max(anterior[3], nuevo[3]),
        )


def _destino_de_enlace(documento, anotacion) -> str:
    """Traduce una anotación de enlace al destino que entiende el programa.

    Un enlace de un PDF puede ser una dirección de Internet —y entonces se
    devuelve tal cual— o un salto a otro sitio del propio documento.  En el
    segundo caso se devuelve ``#pagina-N``, que es el ancla que el analizador
    pone al principio de cada página: así el índice de un informe salta de
    verdad al capítulo, en lugar de avisar de que el destino no existe.
    """
    from pypdfium2 import raw as C

    accion = C.FPDFLink_GetAction(anotacion)
    if accion:
        tipo = C.FPDFAction_GetType(accion)
        if tipo == C.PDFACTION_URI:
            largo = C.FPDFAction_GetURIPath(documento, accion, None, 0)
            if largo > 1:
                buffer = ctypes.create_string_buffer(largo)
                C.FPDFAction_GetURIPath(documento, accion, buffer, largo)
                # La ruta URI es una cadena de bytes, no UTF-16: se decodifica
                # como UTF-8 y, si el archivo no la escribió así, como latin-1,
                # que nunca falla.
                crudo = buffer.raw[:largo].rstrip(b"\x00")
                try:
                    direccion = crudo.decode("utf-8")
                except UnicodeDecodeError:
                    direccion = crudo.decode("latin-1")
                if direccion.strip():
                    return direccion.strip()
        if tipo in (C.PDFACTION_GOTO, C.PDFACTION_UNSUPPORTED):
            destino = C.FPDFAction_GetDest(documento, accion)
            if destino:
                indice = C.FPDFDest_GetDestPageIndex(documento, destino)
                if indice >= 0:
                    return "#pagina-%d" % (indice + 1)
    destino = C.FPDFLink_GetDest(documento, anotacion)
    if destino:
        indice = C.FPDFDest_GetDestPageIndex(documento, destino)
        if indice >= 0:
            return "#pagina-%d" % (indice + 1)
    return ""


# ---------------------------------------------------------------------------
# Traducción del árbol de estructura a XHTML
# ---------------------------------------------------------------------------

class ResultadoPagina(NamedTuple):
    """Lo que sale de traducir la estructura de una página.

    :param cuerpo: XHTML equivalente al árbol de estructura de la página.
    :param caracteres: Cuántos caracteres de texto ha recogido el árbol.
    :param etiquetas: Cuántas veces aparece cada etiqueta PDF, para el informe
                      de accesibilidad.
    :param figuras: Figuras encontradas.
    :param figuras_sin_alt: De ellas, cuántas no tienen texto alternativo.
    :param idiomas: Códigos de idioma declarados en la página y cuántas veces
                    aparece cada uno.  Contarlos es lo que después permite
                    saber cuál es el idioma principal del documento, que no es
                    el primero que sale sino el que más se repite.
    :param pares: Cuántas veces cuelga cada etiqueta de cada otra, como
                  ``{("Table", "TR"): 12}``.  Contar etiquetas sueltas dice si
                  hay tablas; contar pares dice si esas tablas están **bien
                  formadas**, que es la mitad de las reglas de PDF/UA sobre
                  tablas y listas.  Sale gratis: el recorrido ya pasa por cada
                  hijo de cada elemento.
    """

    cuerpo: str
    caracteres: int
    etiquetas: dict
    figuras: int
    figuras_sin_alt: int
    idiomas: dict
    pares: dict


class _Estado:
    """Datos que se van acumulando mientras se recorre el árbol de una página."""

    __slots__ = ("contexto", "idioma_base", "etiquetas", "figuras", "figuras_sin_alt",
                 "idiomas", "notas", "cuenta_notas", "caracteres", "pares")

    def __init__(self, contexto: ContextoPagina, notas: set, idioma_base: str) -> None:
        self.contexto = contexto
        #: Idioma del documento entero.  Los elementos que declaran este mismo
        #: idioma no lo escriben en el XHTML: en un informe en español eso son
        #: casi todos los párrafos, y anotarlos uno por uno llenaría el
        #: documento de marcas de idioma que no dicen nada.
        self.idioma_base = idioma_base
        self.etiquetas: dict[str, int] = {}
        #: Cuántas veces cuelga cada etiqueta de cada otra.
        self.pares: dict[tuple, int] = {}
        self.figuras = 0
        self.figuras_sin_alt = 0
        self.idiomas: dict[str, int] = {}
        #: Números de las notas al pie que hay en esta página.  Solo se enlaza
        #: una llamada cuando su nota existe de verdad, para no dejar enlaces
        #: que al pulsarlos digan que el destino no está en el documento.
        self.notas = notas
        self.cuenta_notas = 0
        self.caracteres = 0

    def anotar(self, etiqueta: str) -> None:
        self.etiquetas[etiqueta] = self.etiquetas.get(etiqueta, 0) + 1

    def anotar_par(self, padre: str, hijo: str) -> None:
        """Anota que una etiqueta cuelga de otra."""
        if padre and hijo:
            clave = (padre, hijo)
            self.pares[clave] = self.pares.get(clave, 0) + 1


def _hijos(elemento):
    """Recorre los hijos de un elemento en orden de lectura.

    Un hijo es o bien otro elemento de estructura, o bien un trozo de contenido
    marcado de la página (un MCID).  PDFium los numera juntos, así que el orden
    del recorrido es ya el orden en que hay que leerlos.

    Los hijos que devuelven ``NULL`` sin MCID son elementos que están en otra
    página: el árbol que se pide es el de esta, y de los demás solo queda el
    hueco.  Se ignoran.
    """
    from pypdfium2 import raw as C

    total = C.FPDF_StructElement_CountChildren(elemento)
    for indice in range(max(total, 0)):
        hijo = C.FPDF_StructElement_GetChildAtIndex(elemento, indice)
        if hijo:
            yield True, hijo
            continue
        mcid = C.FPDF_StructElement_GetChildMarkedContentID(elemento, indice)
        if mcid >= 0:
            yield False, mcid


def _tipo(elemento) -> str:
    """Nombre de la etiqueta de estructura, ya limpio."""
    from pypdfium2 import raw as C

    return _cadena(C.FPDF_StructElement_GetType, elemento).strip()


def _estilo_de_lista(elemento, contexto: "ContextoPagina") -> tuple[str, str]:
    """Decide si una lista ``L`` es numerada y por qué número empieza.

    El PDF lo dice en el atributo ``ListNumbering``, pero muchos generadores no
    lo ponen.  Cuando falta se mira la primera etiqueta (``Lbl``) de la lista:
    si es «1.», «a)» o «iv.» la lista es numerada, y si es un punto o un guion
    es de viñetas.

    Las etiquetas se descartan después, porque el conversor pone las suyas y si
    no cada punto empezaría con dos marcadores seguidos.  Pero antes de tirarlas
    se les saca un dato que no está en ninguna otra parte: **por dónde va la
    numeración**.  Una lista partida entre dos páginas empieza en la segunda por
    el 22, y como cada página es una sección aparte, sin esto se renumeraría
    desde el uno y el documento diría algo distinto de lo que pone.

    :return: ``(etiqueta HTML, valor del atributo start o cadena vacía)``.
    """
    numeracion = _atributo(elemento, "ListNumbering").strip().lower()
    etiqueta = _primera_etiqueta(elemento, contexto)
    if numeracion in ("none", "unordered", "disc", "circle", "square"):
        return "ul", ""
    if numeracion not in NUMERACIONES_ORDENADAS:
        if not etiqueta or not _ETIQUETA_ORDINAL.match(etiqueta):
            return "ul", ""
    coincidencia = _NUMERO_INICIAL.match(etiqueta or "")
    inicio = coincidencia.group(1) if coincidencia else ""
    return "ol", inicio if inicio not in ("", "1") else ""


def _primera_etiqueta(elemento, contexto: "ContextoPagina", profundidad: int = 0) -> str:
    """Texto del primer ``Lbl`` que cuelga de una lista, para adivinar su estilo.

    Hace falta el contexto de la página porque el árbol no guarda el texto: lo
    que cuelga del ``Lbl`` es un número de contenido marcado, y sin el
    diccionario de la página no se puede saber si pone «•» o pone «22.».
    """
    if profundidad > 4:
        return ""
    for es_elemento, hijo in _hijos(elemento):
        if not es_elemento:
            continue
        if _tipo(hijo) == "Lbl":
            return _texto_llano(hijo, contexto).strip()
        encontrado = _primera_etiqueta(hijo, contexto, profundidad + 1)
        if encontrado:
            return encontrado
    return ""


def _texto_llano(elemento, contexto: ContextoPagina | None = None,
                 profundidad: int = 0) -> str:
    """Todo el texto que cuelga de un elemento, sin ninguna etiqueta.

    Se usa para lo que hay que saber *antes* de escribir el XHTML: el rótulo de
    un enlace —que es lo que lo empareja con su anotación—, la etiqueta de una
    lista o el número de una nota.
    """
    from pypdfium2 import raw as C

    if profundidad > PROFUNDIDAD_MAXIMA:
        return ""
    partes: list[str] = []
    for es_elemento, hijo in _hijos(elemento):
        if es_elemento:
            partes.append(_texto_llano(hijo, contexto, profundidad + 1))
        elif contexto is not None:
            partes.append(contexto.texto_de(hijo))
    if not partes and contexto is None:
        # Sin contexto no se puede resolver el texto de los MCID; queda el
        # texto de reemplazo que el propio elemento pueda declarar.
        return _cadena(C.FPDF_StructElement_GetActualText, elemento)
    return "".join(partes)


def _es_codigo_en_bloque(interior: str) -> bool:
    """Indica si un «Code» trae bloques dentro y no es código de una frase."""
    return any(marca in interior for marca in ("<p", "<div", "<br"))


def _renglones_de_codigo(interior: str) -> str:
    """Convierte los párrafos de un bloque de código en renglones.

    Dentro de un ``<pre>`` los párrafos no pintan nada: lo que hace falta es un
    salto de renglón donde había uno, que es lo que el conversor entiende y lo
    que conserva la sangría de cada línea.
    """
    texto = re.sub(r"</p\s*>\s*<p[^>]*>", "<br/>", interior)
    texto = re.sub(r"</?p[^>]*>", "", texto)
    return re.sub(r"</?div[^>]*>", "", texto)


def _abrir(etiqueta: str, atributos: dict) -> str:
    """Escribe la etiqueta de apertura con sus atributos ya escapados."""
    partes = [etiqueta]
    for nombre, valor in atributos.items():
        if valor:
            partes.append('%s="%s"' % (nombre, escapar(str(valor))))
    return "<%s>" % " ".join(partes)


def _convertir(elemento, estado: "_Estado", profundidad: int, nivel_seccion: int,
               contenedor: str, heredado: str = "") -> tuple[str, str]:
    """Traduce un elemento de estructura y todo lo que cuelga de él.

    :return: ``(xhtml, texto llano)``.  El texto llano se devuelve además del
             XHTML porque hay decisiones que solo se pueden tomar cuando ya se
             sabe qué dice el elemento: a qué anotación corresponde un enlace,
             qué número lleva una nota o si una etiqueta de lista es una viñeta.
    """
    from pypdfium2 import raw as C

    if profundidad > PROFUNDIDAD_MAXIMA:
        return "", ""
    tipo = _tipo(elemento)
    if not tipo:
        return "", ""
    estado.anotar(tipo)
    if tipo == "Artifact":
        # Contenido decorativo: encabezados y pies, filetes, marcas de agua.
        # Es justo lo que hay que dejar fuera.
        return "", ""

    idioma = normalizar_idioma(_cadena(C.FPDF_StructElement_GetLang, elemento))
    if idioma:
        estado.idiomas[idioma] = estado.idiomas.get(idioma, 0) + 1
    else:
        idioma = heredado
    # El atributo solo se escribe donde el idioma cambia de verdad respecto a
    # lo que ya está en vigor, que es como se escribe en HTML y lo que hace
    # que después la lectura en voz alta solo cambie de voz donde toca.
    declarado = idioma if idioma and idioma != heredado else ""

    if tipo in ("Figure", "Formula"):
        return _convertir_figura(elemento, estado, declarado, idioma)
    if tipo == "L":
        return _convertir_lista(elemento, estado, profundidad, nivel_seccion,
                                declarado, idioma)
    if tipo == "Lbl" and contenedor == "lista":
        # La viñeta o el número de un punto de lista: el conversor pone el
        # suyo, así que este sobra y solo duplicaría el marcador.
        return "", ""
    if tipo == "Link":
        return _convertir_enlace(elemento, estado, profundidad, nivel_seccion,
                                 declarado, idioma)
    if tipo == "Reference":
        return _convertir_llamada(elemento, estado, profundidad, nivel_seccion,
                                  declarado, idioma)
    if tipo == "Note":
        return _convertir_nota(elemento, estado, profundidad, nivel_seccion,
                               declarado, idioma)
    if tipo == "Table":
        return _convertir_tabla(elemento, estado, profundidad, nivel_seccion,
                                declarado, idioma)

    # --- caso general -------------------------------------------------------
    siguiente_seccion = nivel_seccion + 1 if tipo in SECCIONADORAS else nivel_seccion
    interior, llano = _contenido(elemento, estado, profundidad, siguiente_seccion,
                                 contenedor, idioma)
    if tipo in TRANSPARENTES:
        return interior, llano
    if tipo == "H":
        # Encabezado sin número: su nivel es el de la sección donde está, que
        # es exactamente lo que dice la norma para esta etiqueta.
        etiqueta = "h%d" % max(1, min(6, nivel_seccion))
    elif tipo == "Code" and _es_codigo_en_bloque(interior):
        # «Code» está definido en la norma como etiqueta de dentro del texto
        # —un nombre de función en mitad de una frase—, pero los generadores la
        # usan también para el bloque de código entero, con sus párrafos
        # dentro.  Cuando viene así, sale como bloque preformateado: es lo que
        # conserva los renglones y lo que permite después saltar de bloque en
        # bloque y copiarlo entero.
        etiqueta = "pre"
        interior = _renglones_de_codigo(interior)
    elif tipo == "Caption" and contenedor != "tabla":
        # Un «Caption» solo es el pie de una tabla cuando está dentro de una.
        # Fuera —el pie de una figura, por ejemplo— es un párrafo normal, y
        # dejarlo como <caption> suelto lo sacaría de su sitio.
        etiqueta = "p"
    else:
        etiqueta = EQUIVALENTES.get(tipo, "")
    if not etiqueta:
        # Etiqueta propia del generador (un «Portada» o un «Destacado») que no
        # está en el vocabulario de la norma.  Se conserva el texto como
        # párrafo: perder la semántica es un problema, perder el texto sería
        # un desastre.
        if not llano.strip():
            return interior, llano
        etiqueta = "p"
    atributos: dict[str, object] = {}
    identificador = _cadena(C.FPDF_StructElement_GetID, elemento).strip()
    if identificador:
        atributos["id"] = identificador
    if declarado:
        atributos["lang"] = declarado
    if etiqueta == "th":
        alcance = _atributo(elemento, "Scope").strip().lower()
        if alcance in ("row", "column", "both"):
            atributos["scope"] = "col" if alcance == "column" else alcance
    if etiqueta in ("th", "td"):
        for nombre_pdf, nombre_html in (("ColSpan", "colspan"), ("RowSpan", "rowspan")):
            cuantas = _numero(elemento, nombre_pdf)
            if cuantas > 1:
                atributos[nombre_html] = cuantas
    return "%s%s</%s>" % (_abrir(etiqueta, atributos), interior, etiqueta), llano


def _contenido(elemento, estado: "_Estado", profundidad: int, nivel_seccion: int,
               contenedor: str, heredado: str = "") -> tuple[str, str]:
    """Traduce los hijos de un elemento: los de estructura y los de texto.

    Entre dos contenidos marcados seguidos se mira si falta un espacio, por lo
    mismo que se mira dentro de cada uno: el PDF guarda el texto por renglones
    y por columnas, y donde había un salto de línea puede no haber nada.
    """
    partes: list[str] = []
    llanas: list[str] = []
    anterior_texto = ""
    anterior_rectangulo = None
    # El tipo del padre se pide una vez para todos sus hijos.  Se anota aquí y
    # no dentro de :func:`_convertir` porque aquí es donde se sabe quién cuelga
    # de quién, y así no hay que arrastrar el padre por toda la recursión.
    padre = _tipo(elemento)
    for es_elemento, hijo in _hijos(elemento):
        if es_elemento:
            estado.anotar_par(padre, _tipo(hijo))
            trozo, llano = _convertir(hijo, estado, profundidad + 1, nivel_seccion,
                                      contenedor, heredado)
            if trozo:
                partes.append(trozo)
            if llano:
                llanas.append(llano)
            anterior_texto = ""
            anterior_rectangulo = None
            continue
        texto = estado.contexto.texto_de(hijo)
        if not texto:
            continue
        primero, ultimo = estado.contexto.bordes.get(hijo, (None, None))
        separador = _separacion(anterior_texto, anterior_rectangulo, texto, primero)
        if separador:
            partes.append(separador)
            llanas.append(separador)
            estado.caracteres += len(separador)
        estado.caracteres += len(texto)
        partes.append(escapar(texto))
        llanas.append(texto)
        anterior_texto = texto
        anterior_rectangulo = ultimo
    return "".join(partes), "".join(llanas)


def _convertir_figura(elemento, estado: "_Estado", declarado: str,
                      idioma: str) -> tuple[str, str]:
    """Traduce una ``Figure`` o una ``Formula`` a una imagen con su descripción.

    El texto alternativo es lo único que hace legible una imagen, así que se
    busca donde la norma permite ponerlo: ``Alt`` primero y ``ActualText``
    después.  Si la figura no lo trae se recurre al texto que haya dentro —los
    rótulos de un gráfico, por ejemplo— antes que dejarla muda.
    """
    from pypdfium2 import raw as C

    estado.figuras += 1
    descripcion = (_cadena(C.FPDF_StructElement_GetAltText, elemento).strip()
                   or _cadena(C.FPDF_StructElement_GetActualText, elemento).strip())
    interior, llano = _contenido(elemento, estado, PROFUNDIDAD_MAXIMA - 8, 1, "", idioma)
    if not descripcion:
        estado.figuras_sin_alt += 1
        descripcion = re.sub(r"\s+", " ", llano).strip()
    atributos: dict[str, object] = {
        "src": _origen_de_figura(elemento, estado),
        "alt": descripcion,
    }
    if declarado:
        atributos["lang"] = declarado
    imagen = "%s</img>" % _abrir("img", atributos)
    pie = _pie_de_figura(elemento, estado)
    if pie:
        return ('<figure alt="%s">%s<figcaption>%s</figcaption></figure>'
                % (escapar(descripcion), imagen, escapar(pie)), descripcion)
    return imagen, descripcion


def _pie_de_figura(elemento, estado: "_Estado") -> str:
    """Texto del ``Caption`` que cuelgue de la figura, si lo tiene."""
    for es_elemento, hijo in _hijos(elemento):
        if es_elemento and _tipo(hijo) == "Caption":
            return re.sub(r"\s+", " ", _texto_llano(hijo, estado.contexto)).strip()
    return ""


def _origen_de_figura(elemento, estado: "_Estado") -> str:
    """Referencia con la que después se podrá recortar la figura de la página.

    No se extrae la imagen aquí: una figura de un informe casi nunca es «una»
    imagen, sino un gráfico hecho de decenas de líneas, textos y rellenos.  Lo
    que se guarda es el rectángulo que ocupa, y cuando el usuario pida verla
    (Ctrl+I) o describirla con inteligencia artificial se recorta ese trozo de
    la página y se rasteriza.
    """
    limites = estado.contexto.rectangulo_de(_mcids(elemento, 0))
    if limites is None:
        return ""
    return "pdf-figura:%d:%.2f,%.2f,%.2f,%.2f" % (
        estado.contexto.numero, limites[0], limites[1], limites[2], limites[3])


def _mcids(elemento, profundidad: int):
    """Todos los contenidos marcados que cuelgan de un elemento."""
    if profundidad > 12:
        return
    for es_elemento, hijo in _hijos(elemento):
        if es_elemento:
            yield from _mcids(hijo, profundidad + 1)
        else:
            yield hijo


def _convertir_lista(elemento, estado: "_Estado", profundidad: int, nivel_seccion: int,
                     declarado: str, idioma: str) -> tuple[str, str]:
    """Traduce una lista ``L`` a ``<ul>`` o ``<ol>`` con sus puntos."""
    etiqueta, inicio = _estilo_de_lista(elemento, estado.contexto)
    interior, llano = _contenido(elemento, estado, profundidad, nivel_seccion,
                                 "lista", idioma)
    if not interior:
        return "", ""
    atributos: dict[str, object] = {}
    if inicio:
        atributos["start"] = inicio
    if declarado:
        atributos["lang"] = declarado
    return "%s%s</%s>" % (_abrir(etiqueta, atributos), interior, etiqueta), llano


def _convertir_enlace(elemento, estado: "_Estado", profundidad: int, nivel_seccion: int,
                      declarado: str, idioma: str) -> tuple[str, str]:
    """Traduce un ``Link`` a un ``<a>`` con el destino de su anotación.

    El destino se busca por la posición: el árbol de estructura sabe dónde está
    el enlace y las anotaciones de la página saben a dónde lleva cada punto, así
    que se pregunta por el punto que ocupa el texto marcado como enlace.
    """
    interior, llano = _contenido(elemento, estado, profundidad, nivel_seccion, "")
    if not interior:
        return "", ""
    destino = estado.contexto.enlace_en(
        estado.contexto.rectangulo_de(_mcids(elemento, 0)))
    atributos: dict[str, object] = {}
    # Muchos PDF marcan la llamada de una nota al pie como un enlace corriente
    # al pie de la página, sin usar «Reference».  Si el enlace es solo un
    # número y hay una nota con ese número en la página, es una llamada: se
    # anota como tal y se le hace apuntar a la nota, no a la página.
    numero = _NUMERO_INICIAL.match(llano.strip())
    if (numero and numero.group(1) in estado.notas
            and _LLAMADA_CORTA.match(llano.strip())):
        atributos["class"] = "noteref"
        destino = "#nota-%d-%s" % (estado.contexto.numero, numero.group(1))
    if not destino:
        return interior, llano
    atributos["href"] = destino
    if declarado:
        atributos["lang"] = declarado
    return "%s%s</a>" % (_abrir("a", atributos), interior), llano


def _convertir_llamada(elemento, estado: "_Estado", profundidad: int, nivel_seccion: int,
                       declarado: str, idioma: str) -> tuple[str, str]:
    """Traduce un ``Reference``: la llamada de una nota, o una remisión.

    Un ``Reference`` corto y numérico es la llamada volada que remite a una
    nota al pie; uno largo es una remisión dentro del texto («véase el
    apartado 4.2»).  Solo el primero se marca como llamada de nota, que es lo
    que hace que la tecla de notas y Alt+Mayús+N sirvan para algo.
    """
    interior, llano = _contenido(elemento, estado, profundidad, nivel_seccion, "")
    if not interior:
        return "", ""
    if not _LLAMADA_CORTA.match(llano.strip()):
        return "<span>%s</span>" % interior, llano
    # La llamada suele traer dentro su propio enlace a la nota.  Se le quita,
    # porque el enlace que vale es el de fuera: el del PDF apunta a la página
    # donde está la nota y este apunta a la nota misma.
    interior = re.sub(r"</?a\b[^>]*>", "", interior)
    atributos: dict[str, object] = {"class": "noteref"}
    numero = _NUMERO_INICIAL.match(llano.strip())
    if numero and numero.group(1) in estado.notas:
        atributos["href"] = "#nota-%d-%s" % (estado.contexto.numero, numero.group(1))
    else:
        destino = estado.contexto.enlace_en(
            estado.contexto.rectangulo_de(_mcids(elemento, 0)))
        if destino:
            atributos["href"] = destino
    if declarado:
        atributos["lang"] = declarado
    return "%s%s</a>" % (_abrir("a", atributos), interior), llano


def _convertir_nota(elemento, estado: "_Estado", profundidad: int, nivel_seccion: int,
                    declarado: str, idioma: str) -> tuple[str, str]:
    """Traduce una ``Note`` al pie, dándole el ancla a la que apunta su llamada."""
    interior, llano = _contenido(elemento, estado, profundidad, nivel_seccion, "")
    if not interior:
        return "", ""
    estado.cuenta_notas += 1
    numero = _NUMERO_INICIAL.match(llano.strip())
    clave = numero.group(1) if numero else str(estado.cuenta_notas)
    atributos: dict[str, object] = {
        "id": "nota-%d-%s" % (estado.contexto.numero, clave),
        "class": "nota",
        "role": "doc-footnote",
    }
    if declarado:
        atributos["lang"] = declarado
    return "%s%s</aside>" % (_abrir("aside", atributos), interior), llano


def _convertir_tabla(elemento, estado: "_Estado", profundidad: int, nivel_seccion: int,
                     declarado: str, idioma: str) -> tuple[str, str]:
    """Traduce una ``Table``, poniéndole como título su ``Summary`` si no tiene pie.

    El ``Summary`` es la descripción que la norma pide para las tablas
    complejas, y es justo lo que hay que oír al llegar a ella: sin él lo que se
    anuncia es la primera fila de encabezados, que muchas veces no dice de qué
    va la tabla.
    """
    interior, llano = _contenido(elemento, estado, profundidad, nivel_seccion,
                                 "tabla", idioma)
    if not interior:
        return "", ""
    if "<caption" not in interior:
        resumen = _atributo(elemento, "Summary").strip()
        if resumen:
            interior = "<caption>%s</caption>%s" % (escapar(resumen), interior)
            llano = resumen + " " + llano
    atributos: dict[str, object] = {"lang": declarado} if declarado else {}
    return "%s%s</table>" % (_abrir("table", atributos), interior), llano


def _numeros_de_notas(raices, contexto: ContextoPagina) -> set:
    """Números de las notas al pie que hay en la página.

    Hace falta saberlo *antes* de escribir las llamadas, porque una llamada
    solo se enlaza si su nota existe: un enlace que al pulsarlo dijera que el
    destino no está en el documento sería peor que no ponerlo.
    """
    encontrados: set[str] = set()

    def buscar(elemento, profundidad: int) -> None:
        if profundidad > PROFUNDIDAD_MAXIMA:
            return
        if _tipo(elemento) == "Note":
            numero = _NUMERO_INICIAL.match(_texto_llano(elemento, contexto).strip())
            if numero:
                encontrados.add(numero.group(1))
            return
        for es_elemento, hijo in _hijos(elemento):
            if es_elemento:
                buscar(hijo, profundidad + 1)

    for raiz in raices:
        buscar(raiz, 0)
    return encontrados


# ---------------------------------------------------------------------------
# Entrada del módulo
# ---------------------------------------------------------------------------

def esta_marcado(documento) -> bool:
    """Dice si el catálogo del PDF se declara como etiquetado.

    Es la bandera ``MarkInfo/Marked`` que la norma PDF/UA obliga a poner.  No
    garantiza que el etiquetado sea bueno —eso se comprueba mirando el árbol—,
    pero es la declaración de intenciones del archivo y es lo que se enseña en
    el informe de accesibilidad.
    """
    from pypdfium2 import raw as C

    try:
        return bool(C.FPDFCatalog_IsTagged(documento))
    except Exception:
        return False


def idioma_del_documento(documento) -> str:
    """Idioma declarado en el catálogo del PDF (la entrada ``Lang``).

    Es el idioma que se aplica a todo el documento salvo donde se diga otra
    cosa, y por eso es el que hay que creer: dentro del árbol solo llevan
    idioma los trozos que *cambian* de idioma, así que contar esos daría el
    resultado contrario al bueno —un informe en español con cuatro citas en
    portugués saldría portugués—.

    Declararlo es, además, requisito de la norma (PDF/UA y el criterio 3.1.1
    de las WCAG), así que en un PDF accesible siempre está.
    """
    from pypdfium2 import raw as C

    try:
        largo = C.FPDFCatalog_GetLanguage(documento, None, 0)
        if not largo or largo <= 2:
            return ""
        buffer = ctypes.create_string_buffer(largo)
        C.FPDFCatalog_GetLanguage(
            documento, ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ushort)), largo)
        return normalizar_idioma(
            buffer.raw[:largo].decode("utf-16-le", "replace").rstrip(chr(0)))
    except Exception:
        return ""


def convertir_pagina(documento, pagina, pagina_texto, numero: int,
                    idioma_base: str = "") -> ResultadoPagina | None:
    """Traduce a XHTML el árbol de estructura de una página.

    :param documento: Manejador ``FPDF_DOCUMENT`` (``pdf.raw``), que hace
                      falta para resolver los destinos de los enlaces.
    :param pagina: Manejador ``FPDF_PAGE`` de la página (``page.raw``).
    :param pagina_texto: Manejador ``FPDF_TEXTPAGE`` de la misma página.
    :param numero: Número de página empezando en 1.
    :param idioma_base: Idioma del documento entero.  Los fragmentos que estén
                        en ese idioma no lo declaran en el XHTML, de modo que
                        solo queden anotados los que de verdad cambian.
    :return: El resultado, o ``None`` si la página no trae estructura.
    """
    from pypdfium2 import raw as C

    arbol = C.FPDF_StructTree_GetForPage(pagina)
    if not arbol:
        return None
    try:
        raices = []
        for indice in range(max(C.FPDF_StructTree_CountChildren(arbol), 0)):
            raiz = C.FPDF_StructTree_GetChildAtIndex(arbol, indice)
            if raiz:
                raices.append(raiz)
        if not raices:
            return None
        contexto = contexto_de_pagina(documento, pagina, pagina_texto, numero)
        estado = _Estado(contexto, _numeros_de_notas(raices, contexto), idioma_base)
        partes = []
        for raiz in raices:
            trozo, _llano = _convertir(raiz, estado, 0, 1, "", idioma_base)
            if trozo:
                partes.append(trozo)
    finally:
        C.FPDF_StructTree_Close(arbol)
    return ResultadoPagina(
        cuerpo="".join(partes),
        caracteres=estado.caracteres,
        etiquetas=estado.etiquetas,
        pares=estado.pares,
        figuras=estado.figuras,
        figuras_sin_alt=estado.figuras_sin_alt,
        idiomas=estado.idiomas,
    )


def enlaces_de_pagina(documento, pagina) -> list:
    """Devuelve los enlaces de una página con el rectángulo que ocupan.

    Los enlaces de un PDF no son parte del texto: son **anotaciones**, cajas
    dibujadas encima de la página que dicen «lo que hay aquí debajo lleva a tal
    sitio».  Cuando el PDF está etiquetado, el árbol de estructura ya trae el
    elemento ``Link`` y esto no hace falta; cuando no lo está, es la única
    forma de saber que ese trozo de texto azul es un enlace, y sin ella un PDF
    sin etiquetar se lee sin un solo enlace que seguir.

    Las coordenadas se devuelven **con el origen arriba a la izquierda**, que
    es como trabajan el módulo de disposición y el de geometría, para no dejar
    la conversión en manos de quien llame.

    :return: Lista de ``(izquierda, arriba, derecha, abajo, destino)``.
    """
    from pypdfium2 import raw as C

    resultado = []
    try:
        alto = C.FPDF_GetPageHeightF(pagina)
    except Exception:
        return resultado
    posicion = ctypes.c_int(0)
    anotacion = C.FPDF_LINK()
    # «FPDFLink_Enumerate» va devolviendo las anotaciones de enlace una a una y
    # lleva él la cuenta en «posicion»; se para cuando devuelve falso.
    while True:
        try:
            if not C.FPDFLink_Enumerate(pagina, ctypes.byref(posicion),
                                        ctypes.byref(anotacion)):
                break
        except Exception as error:
            log.debug("No se han podido enumerar los enlaces de la página: %s", error)
            break
        try:
            destino = _destino_de_enlace(documento, anotacion)
            if not destino:
                continue
            caja = C.FS_RECTF()
            if not C.FPDFLink_GetAnnotRect(anotacion, ctypes.byref(caja)):
                continue
            resultado.append((float(caja.left), float(alto - caja.top),
                              float(caja.right), float(alto - caja.bottom),
                              destino))
        except Exception as error:
            log.debug("No se ha podido leer un enlace de la página: %s", error)
            continue
    return resultado
