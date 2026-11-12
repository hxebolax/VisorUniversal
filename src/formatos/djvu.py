# -*- coding: utf-8 -*-
"""DjVu: sacar el libro de un archivo pensado para mirarlo.

DjVu es el formato en el que se digitalizó buena parte de los fondos técnicos y
universitarios: manuales agotados, tesis, colecciones de revistas. En los
repositorios sigue habiendo muchísimos, y hasta ahora eran un archivo que no se
podía abrir.

**No hace falta descomprimir las imágenes.** Un DjVu de biblioteca casi siempre
lleva dentro el texto que se reconoció al digitalizarlo, y para quien no ve, ese
texto es el libro entero. Las imágenes de las páginas van en otros dos
algoritmos —JB2 para el blanco y negro y ondículas para el color— que aquí no
aportarían nada: lo que hace falta es el texto.

Un DjVu es un archivo IFF, es decir, trozos con nombre de cuatro letras metidos
unos dentro de otros:

- ``DIRM`` es el índice del documento: cuántas páginas hay, cómo se llaman y
  cuáles son páginas de verdad y cuáles piezas compartidas.
- ``NAVM`` es el índice de contenido —los marcadores del libro—, si lo trae.
- Cada página es un ``FORM:DJVU`` y su texto va en un ``TXTz``.

Los tres van comprimidos en BZZ (:mod:`formatos.bzz`).

**Lo que hace que se lea como un libro y no como un volcado de OCR** es la
jerarquía de zonas del ``TXTz``. El texto reconocido viene con un salto de línea
en cada renglón de la página, que leído en voz alta corta las frases por la
mitad. Pero el trozo trae además el árbol de zonas —página, columna, región,
párrafo, línea, palabra— y con él se sabe qué renglones son el mismo párrafo.
Uniéndolos, y deshaciendo los guiones de partición de palabra al final de
renglón, sale prosa de verdad.
"""

from __future__ import annotations

import os
import re
import struct
from pathlib import Path

from nucleo.documento import ElementoIndice, Metadatos
from nucleo.idioma import _
from nucleo.registro import obtener_registro, registrar_excepcion

from . import bzz, ensamblador, iw44, jb2
from .base import Analizador, ErrorFormato, OpcionesAnalisis, registrar

log = obtener_registro(__name__)

#: Tipos de zona del árbol de texto, tal como los numera el formato.
PAGINA, COLUMNA, REGION, PARRAFO, LINEA, PALABRA, CARACTER = range(1, 8)

#: Marca que abre cualquier archivo DjVu.
FIRMA = b"AT&T"

#: Un ``FORM`` de estos tipos es un documento entero.
RAICES = (b"DJVM", b"DJVU", b"DJVI", b"THUM")

#: Bandera del ``DIRM`` que dice que ese archivo interno tiene nombre propio.
_TIENE_NOMBRE = 0x80

#: Con qué nombre se piden las imágenes de página.  No es «pagina» a secas
#: porque así se llaman ya las secciones del documento, y dos cosas distintas
#: con el mismo nombre se confunden justo el día que hay que depurarlas.
_IMAGEN = "imagen"

#: Bandera del ``DIRM`` que dice que trae además un título legible.
_TIENE_TITULO = 0x40

#: Tipo de archivo interno dentro del ``DIRM``: 1 es una página de verdad; los
#: demás son miniaturas o piezas compartidas entre páginas.
_ES_PAGINA = 1


class Trozo:
    """Un trozo IFF: su nombre, dónde empieza su cuerpo y cuánto ocupa."""

    __slots__ = ("nombre", "inicio", "largo")

    def __init__(self, nombre: bytes, inicio: int, largo: int) -> None:
        self.nombre = nombre
        self.inicio = inicio
        self.largo = largo


def trozos(datos: bytes, inicio: int, fin: int):
    """Recorre los trozos IFF que hay entre dos posiciones.

    Cada trozo son cuatro letras, cuatro bytes de tamaño en orden de red, y el
    cuerpo. Los cuerpos de tamaño impar llevan un byte de relleno detrás que no
    cuenta como contenido pero sí para saber dónde empieza el siguiente.
    """
    posicion = inicio
    while posicion + 8 <= fin:
        nombre = datos[posicion:posicion + 4]
        largo = struct.unpack(">I", datos[posicion + 4:posicion + 8])[0]
        cuerpo = posicion + 8
        if cuerpo + largo > fin:
            # Trozo truncado: se devuelve lo que hay y se para, en vez de
            # abandonar el archivo entero. Un DjVu al que le falta el último
            # trozo sigue teniendo todas las páginas anteriores.
            largo = max(0, fin - cuerpo)
            if largo:
                yield Trozo(nombre, cuerpo, largo)
            return
        yield Trozo(nombre, cuerpo, largo)
        posicion = cuerpo + largo + (largo & 1)


class Zona:
    """Una zona del árbol de texto: qué trozo del texto ocupa y de qué tipo es."""

    __slots__ = ("tipo", "inicio", "largo", "hijas")

    def __init__(self, tipo: int, inicio: int, largo: int) -> None:
        self.tipo = tipo
        self.inicio = inicio
        self.largo = largo
        self.hijas: list = []


def _leer_zona(datos: bytes, posicion: int, padre, anterior, limite: int):
    """Lee una zona y las suyas. Devuelve ``(zona, posición siguiente)``.

    Las posiciones dentro del texto van **en diferencias**: cada zona dice
    cuánto se separa de su hermana anterior o, si es la primera, de su madre.
    Sin deshacer esa cuenta, los trozos de texto salen todos del principio.
    """
    # Diecisiete bytes justos: tipo, cuatro coordenadas, dónde empieza su
    # texto y cuánto ocupa, y cuántas zonas cuelgan de ella. Ni uno más: la
    # última zona del árbol acaba pegada al final del trozo, así que pedir
    # dieciocho tira el árbol entero de un archivo perfectamente sano.
    if posicion + 17 > limite:
        raise ErrorFormato(_("El árbol de texto del DjVu está incompleto."))
    tipo = datos[posicion]
    if tipo < PAGINA or tipo > CARACTER:
        raise ErrorFormato(_("El árbol de texto del DjVu no es válido."))
    # Las cuatro coordenadas del rectángulo no se usan: aquí interesa el texto,
    # no dónde está dibujado. Se saltan sin leerlas.
    inicio = struct.unpack(">H", datos[posicion + 9:posicion + 11])[0] - 0x8000
    largo = int.from_bytes(datos[posicion + 11:posicion + 14], "big")
    cuantas = int.from_bytes(datos[posicion + 14:posicion + 17], "big")
    posicion += 17

    if anterior is not None:
        inicio += anterior.inicio + anterior.largo
    elif padre is not None:
        inicio += padre.inicio

    zona = Zona(tipo, inicio, largo)
    hermana = None
    for _numero in range(cuantas):
        hija, posicion = _leer_zona(datos, posicion, zona, hermana, limite)
        zona.hijas.append(hija)
        hermana = hija
    return zona, posicion


def _capa_de_texto(crudo: bytes):
    """Descompone un trozo ``TXT`` en ``(texto, zona de la página)``.

    La zona puede ser ``None``: hay archivos con texto y sin árbol.
    """
    if len(crudo) < 3:
        return "", None
    tamano = int.from_bytes(crudo[:3], "big")
    bruto = crudo[3:3 + tamano]
    # El texto suele acabar en un cero que forma parte del tamaño declarado.
    texto = bruto.rstrip(b"\x00").decode("utf-8", "replace")
    zona = None
    resto = 3 + tamano
    if resto < len(crudo):
        # Detrás del texto va un byte de versión y luego el árbol.
        try:
            zona, _fin = _leer_zona(crudo, resto + 1, None, None, len(crudo))
        except Exception as error:
            log.debug("El DjVu trae texto pero no un árbol legible: %s", error)
    return texto, zona


#: Separadores que el DjVu mete dentro del texto plano para indicar dónde
#: acaba una columna, una región o un párrafo. Son caracteres de control, así
#: que leídos en voz alta no son nada y en pantalla ensucian; se convierten en
#: saltos de línea, que es lo que significan.
_SEPARADORES = str.maketrans({codigo: "\n" for codigo in
                              (0x0b, 0x0c, 0x1c, 0x1d, 0x1e, 0x1f)})


def _zonas_de_parrafo(zona) -> list:
    """Las zonas más finas que agrupan renglones, en orden de lectura.

    Se prefieren las de párrafo. Hay archivos cuyo OCR solo llegó a marcar
    regiones o columnas; entonces se usan esas, que siguen siendo mejor que
    nada. Y hay archivos con texto y sin árbol, que se resuelven fuera.
    """
    for buscado in (PARRAFO, REGION, COLUMNA):
        encontradas: list = []

        def recorrer(nodo) -> None:
            if nodo.tipo == buscado:
                encontradas.append(nodo)
                return
            for hija in nodo.hijas:
                recorrer(hija)

        recorrer(zona)
        if encontradas:
            return encontradas
    return [zona]


def parrafos_de(zona, texto: str) -> list:
    """Reparte el texto de una página en párrafos, cada uno con sus renglones.

    **Por qué se corta por zonas de párrafo y no por zonas de línea**, que
    sería lo natural: porque los rangos de texto de las zonas no respetan los
    límites de palabra. Las zonas trocean el texto plano en tramos seguidos, y
    el tramo de una línea puede empezar a media palabra: en una página con una
    nota al margen, el texto plano intercala la nota con el cuerpo, y la línea
    que geométricamente las cruza acaba en «Jam» y la siguiente empieza en
    «es». Cortando por ahí y uniendo con un espacio sale «Jam es Caldwell».

    Cortando por zonas de párrafo el problema es mucho más raro, pero no
    desaparece: por eso, además, **una zona que no acaba en un espacio no es un
    párrafo de verdad**, sino una palabra partida, y se pega a la siguiente sin
    poner nada en medio. Así «Rea» + «d Mar. 22» vuelve a ser «Read Mar. 22».

    Dentro de un párrafo ya sí mandan los saltos de línea del texto plano, que
    son los renglones que había en el papel.
    """
    tramos: list[str] = []
    for nodo in _zonas_de_parrafo(zona):
        trozo = texto[nodo.inicio:nodo.inicio + nodo.largo]
        if not trozo:
            continue
        if tramos and tramos[-1] and not tramos[-1][-1].isspace():
            # La zona anterior acabó a media palabra: esto es su continuación.
            tramos[-1] += trozo
        else:
            tramos.append(trozo)

    parrafos: list[list[str]] = []
    for tramo in tramos:
        lineas = [linea.strip()
                  for linea in tramo.translate(_SEPARADORES).split("\n")]
        lineas = [linea for linea in lineas if linea]
        if lineas:
            parrafos.append(lineas)
    return parrafos


#: Guion de partición al final de un renglón, con la palabra partida delante.
#: Delante tiene que haber una **letra**: un guion detrás de una cifra casi
#: nunca parte una palabra —es una fecha, un intervalo o una raya— y unirlo
#: pegaría dos palabras que no van juntas.
_PARTIDA = re.compile(r"([^\W\d_])[-­]$", re.UNICODE)


def juntar(lineas) -> str:
    """Une los renglones de un párrafo en una frase seguida.

    El OCR corta donde acababa el renglón en el papel, no donde acaba la frase,
    así que leído en voz alta corta las frases por la mitad. Al unir hay que
    deshacer además los **guiones de partición de palabra**: si un renglón
    acaba en guion detrás de una letra, la palabra sigue en el siguiente y el
    guion sobra —«na-» y «tura» son «natura»—.

    Dos excepciones, las dos por lo mismo: hay guiones de final de renglón que
    no parten nada.

    - Detrás de una cifra —«1759-»— casi siempre es una raya o un intervalo.
    - Dentro de una dirección de internet o de una ruta el guion es parte del
      texto: quitarlo deja una dirección que no lleva a ninguna parte. Ahí se
      junta sin espacio pero **conservando el guion**.
    """
    salida = ""
    for linea in lineas:
        linea = linea.strip()
        if not linea:
            continue
        if not salida:
            salida = linea
            continue
        if _PARTIDA.search(salida):
            if _direccion(salida):
                salida += linea
            else:
                salida = salida[:-1] + linea
        else:
            salida += " " + linea
    return salida


def _direccion(texto: str) -> bool:
    """Dice si lo último que hay escrito parece una dirección o una ruta."""
    ultima = texto.rsplit(" ", 1)[-1]
    return "/" in ultima or "@" in ultima or ultima.startswith("www.")


def _pagina_a_xhtml(texto: str, zona, rotulo: str, imagen: int = 0) -> bytes:
    """Convierte el texto de una página en XHTML con su marca de página.

    :param imagen: Número de página cuya imagen hay que dejar puesta, o 0.  Se
        pone cuando la página no tiene texto ninguno: sin ella el documento
        tendría un hueco mudo donde hay una lámina.
    """
    partes = ["<span epub:type=\"pagebreak\" title=\"%s\"></span>"
              % ensamblador.escapar(rotulo)]
    if imagen:
        partes.append("<img src=\"%s%d.png\"/>" % (_IMAGEN, imagen))
    parrafos = parrafos_de(zona, texto) if zona is not None else []
    if parrafos:
        for lineas in parrafos:
            frase = juntar(lineas)
            if frase:
                partes.append("<p>%s</p>" % ensamblador.escapar(frase))
    elif texto.strip():
        # Sin árbol de zonas no se sabe qué renglones son el mismo párrafo, así
        # que se aplica la regla general de los textos planos.
        partes.append(ensamblador.parrafos_de_texto(
            texto.translate(_SEPARADORES)))
    return ("<?xml version=\"1.0\" encoding=\"utf-8\"?>"
            "<html xmlns=\"http://www.w3.org/1999/xhtml\" "
            "xmlns:epub=\"http://www.idpf.org/2007/ops\"><head>"
            "<meta charset=\"utf-8\"/></head><body>%s</body></html>"
            % "".join(partes)).encode("utf-8")


def _diccionario_de(datos: bytes, pagina: Trozo, por_id: dict, guardados: dict):
    """El diccionario de formas que necesita esta página, si necesita alguno.

    Un libro escaneado guarda la «a» **una vez para todo el tomo** en un trozo
    ``Djbz`` aparte, y cada página dice con un ``INCL`` cuál le toca.  Sin
    resolver esa referencia la página no se puede descomprimir: le faltarían
    justamente las letras.
    """
    for interno in trozos(datos, pagina.inicio + 4, pagina.inicio + pagina.largo):
        if interno.nombre != b"INCL":
            continue
        cual = datos[interno.inicio:interno.inicio + interno.largo]
        cual = cual.split(b"\x00")[0].decode("utf-8", "replace").strip()
        if cual in guardados:
            return guardados[cual]
        compartido = por_id.get(cual)
        if compartido is None:
            continue
        for pieza in trozos(datos, compartido.inicio + 4,
                            compartido.inicio + compartido.largo):
            if pieza.nombre != b"Djbz":
                continue
            try:
                diccionario = jb2.leer_diccionario(
                    datos, pieza.inicio, pieza.inicio + pieza.largo)
            except Exception as error:
                log.debug("Djbz %s ilegible (%s)", cual, error)
                diccionario = None
            guardados[cual] = diccionario
            return diccionario
    return None


def mascara_de(datos: bytes, pagina: Trozo, diccionario=None):
    """La página en blanco y negro, o ``None`` si no la trae.

    Es la capa que en un escaneado lleva **el texto y los dibujos de línea**;
    el color va en otras dos que aquí no hacen falta.  Para reconocer una
    página, la máscara no es un apaño: es mejor que la fotografía en color,
    porque ya viene separada del papel amarillento y de las manchas.
    """
    for interno in trozos(datos, pagina.inicio + 4, pagina.inicio + pagina.largo):
        if interno.nombre != b"Sjbz":
            continue
        pieza = jb2.leer_mascara(datos, interno.inicio,
                                 interno.inicio + interno.largo, diccionario)
        return jb2.componer(pieza)
    return None


class Envoltorios:
    """Lo que hay dentro de un DjVu: sus páginas, su índice y sus marcadores."""

    __slots__ = ("paginas", "formularios", "archivos", "marcadores")

    def __init__(self, paginas, formularios, archivos, marcadores) -> None:
        self.paginas = paginas
        self.formularios = formularios
        self.archivos = archivos
        self.marcadores = marcadores


def envoltorios(datos: bytes) -> Envoltorios:
    """Recorre el archivo y separa lo que hay dentro.

    Se apuntan **todos** los envoltorios, no solo las páginas, porque el índice
    los numera todos y una página busca su diccionario de formas por el sitio
    que ocupa en esa lista.
    """
    raiz = Trozo(datos[4:8], 12, struct.unpack(">I", datos[8:12])[0])
    tipo = datos[12:16]
    if raiz.nombre != b"FORM" or tipo not in RAICES:
        raise ErrorFormato(_("El archivo no es un DjVu válido."))
    if tipo == b"DJVU":
        # Un DjVu de una sola página no lleva índice ni envoltorio: el documento
        # entero *es* la página, y sus trozos cuelgan de la raíz.
        return Envoltorios([raiz], [], [], [])

    fin = min(len(datos), raiz.inicio + raiz.largo)
    paginas, formularios, archivos, marcadores = [], [], [], []
    for trozo in trozos(datos, 16, fin):
        if trozo.nombre == b"DIRM":
            try:
                archivos = _leer_dirm(datos, trozo)
            except Exception as error:
                registrar_excepcion(log, "DIRM ilegible", error)
        elif trozo.nombre == b"NAVM":
            try:
                marcadores = _leer_navm(datos, trozo)
            except Exception as error:
                registrar_excepcion(log, "NAVM ilegible", error)
        elif trozo.nombre == b"FORM":
            formularios.append(trozo)
            if datos[trozo.inicio:trozo.inicio + 4] == b"DJVU":
                paginas.append(trozo)
    return Envoltorios(paginas, formularios, archivos, marcadores)


def fondo_de(datos: bytes, pagina: Trozo):
    """La capa de color de una página, o ``None`` si no la trae.

    Es la que lleva el papel y las fotografías.  Va repartida en varios trozos
    seguidos que se van afinando unos a otros, así que hay que dárselos todos y
    en orden: quedarse con el primero da la página desenfocada.
    """
    capa = iw44.Capa()
    alguno = False
    for interno in trozos(datos, pagina.inicio + 4, pagina.inicio + pagina.largo):
        if interno.nombre not in (b"BG44", b"BGjp", b"BG2k"):
            continue
        if interno.nombre != b"BG44":
            # Hay DjVu que meten el fondo en JPEG o en JPEG 2000. Son rarísimos
            # y no son ondículas de DjVu: se dice y se deja.
            return None
        capa.trozo(datos, interno.inicio, interno.inicio + interno.largo)
        alguno = True
    return capa if alguno else None


def imagen_de(datos: bytes, pagina: Trozo, diccionario=None):
    """La página como PNG, con lo mejor que tenga: ``(imagen, es_mascara)``.

    Se prefiere la **máscara** cuando la hay, y no por comodidad: es la capa en
    blanco y negro donde está el texto, llega ya separada del papel y ocupa una
    décima parte.  El fondo en color se usa cuando no hay máscara, que es
    justamente el caso de una lámina fotográfica o de un mapa: una página que no
    tiene ni una letra y que hasta ahora no se podía ni ver.
    """
    mapa = mascara_de(datos, pagina, diccionario)
    if mapa is not None:
        return jb2.a_png(mapa), True
    capa = fondo_de(datos, pagina)
    if capa is not None:
        return iw44.a_png(capa), False
    return None, False


class Archivo:
    """Un archivo interno del DjVu, tal como lo describe el ``DIRM``."""

    __slots__ = ("identificador", "titulo", "es_pagina")

    def __init__(self, identificador: str, titulo: str, es_pagina: bool) -> None:
        self.identificador = identificador
        self.titulo = titulo
        self.es_pagina = es_pagina


def _leer_dirm(datos: bytes, trozo: Trozo):
    """Lee el índice del documento. Devuelve la lista de archivos internos."""
    posicion = trozo.inicio
    cabecera = datos[posicion]
    empaquetado = bool(cabecera & 0x80)
    version = cabecera & 0x7f
    posicion += 1
    cuantos = struct.unpack(">H", datos[posicion:posicion + 2])[0]
    posicion += 2
    if not cuantos:
        return []
    if empaquetado:
        # Dónde empieza cada archivo dentro del DjVu. Aquí no hacen falta,
        # porque los trozos se recorren en orden; se saltan. En la versión 0
        # cada uno lleva detrás su tamaño, tres bytes más.
        posicion += (7 if version == 0 else 4) * cuantos
    crudo = bzz.descomprimir(datos, posicion, trozo.inicio + trozo.largo)
    # En la versión 1 van primero los tamaños, tres bytes cada uno, y después
    # las banderas. En la 0 los tamaños iban arriba, sin comprimir.
    corte = 3 * cuantos if version > 0 else 0
    banderas = crudo[corte:corte + cuantos]
    nombres = crudo[corte + cuantos:].split(b"\x00")
    archivos = []
    indice = 0
    for numero in range(cuantos):
        bandera = banderas[numero] if numero < len(banderas) else 0
        if version == 0:
            # Las banderas antiguas eran otras: el bit 0 decía «es página» y
            # los bits 1 y 2, si traía nombre y título.
            bandera = ((_ES_PAGINA if bandera & 1 else 0)
                       | (_TIENE_NOMBRE if bandera & 2 else 0)
                       | (_TIENE_TITULO if bandera & 4 else 0))
        identificador = nombres[indice].decode("utf-8", "replace") if indice < len(nombres) else ""
        indice += 1
        if bandera & _TIENE_NOMBRE:
            indice += 1
        titulo = ""
        if bandera & _TIENE_TITULO:
            titulo = nombres[indice].decode("utf-8", "replace") if indice < len(nombres) else ""
            indice += 1
        archivos.append(Archivo(identificador, titulo,
                                (bandera & 0x3f) == _ES_PAGINA))
    return archivos


def _leer_navm(datos: bytes, trozo: Trozo):
    """Lee los marcadores del libro. Devuelve ``[(sangría, título, destino)]``.

    El destino es lo que el marcador apunta: o el identificador de un archivo
    interno, o ``#`` más un número de página.
    """
    crudo = bzz.descomprimir(datos, trozo.inicio, trozo.inicio + trozo.largo)
    if len(crudo) < 2:
        return []
    cuantos = struct.unpack(">H", crudo[:2])[0]
    posicion = 2
    salida = []
    for _numero in range(cuantos):
        if posicion + 4 > len(crudo):
            break
        # Cuántos hijos cuelgan de este marcador. Es el único número del
        # formato que va con el byte bajo delante; todo lo demás es orden de
        # red, así que conviene no «arreglarlo» al leerlo.
        hijos = crudo[posicion] | (crudo[posicion + 1] << 8)
        largo_titulo = struct.unpack(">H", crudo[posicion + 2:posicion + 4])[0]
        posicion += 4
        titulo = crudo[posicion:posicion + largo_titulo].decode("utf-8", "replace")
        posicion += largo_titulo
        if posicion + 3 > len(crudo):
            break
        # El destino sí lleva su tamaño en tres bytes, no en dos.
        largo_destino = int.from_bytes(crudo[posicion:posicion + 3], "big")
        posicion += 3
        destino = crudo[posicion:posicion + largo_destino].decode("utf-8", "replace")
        posicion += largo_destino
        salida.append((hijos, titulo.strip(), destino.strip()))
    return salida


def _arbol_de_marcadores(plana, posiciones, por_identificador):
    """Convierte la lista plana de marcadores en el índice jerárquico.

    Los marcadores vienen en preorden: cada uno dice cuántos hijos tiene y esos
    hijos son los siguientes de la lista. Se reconstruye con una pila de
    «cuántos me quedan por recoger».
    """
    raices: list[ElementoIndice] = []
    pila: list[tuple[int, ElementoIndice]] = []
    for hijos, titulo, destino in plana:
        pagina = None
        if destino.startswith("#"):
            resto = destino[1:]
            if resto.isdigit():
                pagina = int(resto) - 1
            else:
                pagina = por_identificador.get(resto)
        else:
            pagina = por_identificador.get(destino)
        if pagina is None or not (0 <= pagina < len(posiciones)):
            posicion = posiciones[0] if posiciones else 0
        else:
            posicion = posiciones[pagina]
        entrada = ElementoIndice(titulo or _("(sin título)"), posicion)
        if pila:
            pila[-1][1].hijos.append(entrada)
        else:
            raices.append(entrada)
        # Se apila aunque no tenga hijos, para descontar bien a los padres.
        pila.append((hijos, entrada))
        while pila and pila[-1][0] == 0:
            pila.pop()
            if pila:
                pila[-1] = (pila[-1][0] - 1, pila[-1][1])
    return raices


def _pagina_reconocida(reconocido, numero: int, rotulos) -> bytes:
    """Arma la página con lo que ha devuelto el reconocedor."""
    rotulo = ""
    if numero - 1 < len(rotulos):
        rotulo = rotulos[numero - 1].titulo
    marca = ("<span epub:type=\"pagebreak\" title=\"%s\"></span>"
             % ensamblador.escapar(rotulo or str(numero)))
    cuerpo = reconocido.html or ensamblador.parrafos_de_texto(reconocido.texto)
    return ("<?xml version=\"1.0\" encoding=\"utf-8\"?>"
            "<html xmlns=\"http://www.w3.org/1999/xhtml\" "
            "xmlns:epub=\"http://www.idpf.org/2007/ops\"><head>"
            "<meta charset=\"utf-8\"/></head><body>%s%s</body></html>"
            % (marca, cuerpo)).encode("utf-8")


class AnalizadorDjVu(Analizador):
    """Abre un DjVu quedándose con su capa de texto."""

    extensiones = (".djvu", ".djv")
    descripcion = _("Documento DjVu escaneado")

    #: Servicio de IA con el que reconocer, si lo hay.  Lo pone la ventana antes
    #: de abrir, igual que en el analizador de PDF.
    servicio_ia = None

    #: Con qué se reconocen las páginas que no traen texto: «auto», «ia»,
    #: «windows», «tesseract» o «ninguno».
    ocr_modo = "auto"

    #: Idiomas de Tesseract, separados por «+».
    ocr_idiomas = ""

    #: Ajustes completos del reconocimiento.
    ocr_ajustes = None

    #: Cuántas páginas como mucho se reconocen (0 = sin tope).
    ocr_maximo = 100

    def extraer_recurso(self, ruta, interna: str) -> bytes | None:
        """Devuelve la imagen de una página, para verla o describirla.

        Se vuelve a descomprimir cada vez en lugar de guardarla: una página son
        unas décimas de segundo y guardarlas todas serían cientos de megas en
        memoria por un libro que casi nadie va a mirar entero.
        """
        if not interna.startswith(_IMAGEN) or not interna.endswith(".png"):
            return None
        try:
            numero = int(interna[len(_IMAGEN):-4])
        except ValueError:
            return None
        try:
            datos = Path(ruta).read_bytes()
            dentro = envoltorios(datos)
            if not 1 <= numero <= len(dentro.paginas):
                return None
            pagina = dentro.paginas[numero - 1]
            por_id = {archivo.identificador: dentro.formularios[cual]
                      for cual, archivo in enumerate(dentro.archivos)
                      if cual < len(dentro.formularios)}
            imagen, _es_mascara = imagen_de(
                datos, pagina, _diccionario_de(datos, pagina, por_id, {}))
            return imagen
        except Exception as error:
            log.debug("No se ha podido sacar la página %d del DjVu: %s",
                      numero, error)
            return None

    def _reconocer(self, mapa):
        """Manda una máscara ya descomprimida al reconocedor.

        Recibe el PNG ya hecho.  No se escala: la máscara viene a la resolución
        con la que se digitalizó el libro, que en un escaneado de biblioteca son
        trescientos puntos por pulgada o más.  Ampliar una imagen de un bit no
        añade información y sí multiplica por cuatro lo que tarda.
        """
        from . import ocr

        return ocr.reconocer(mapa, self.servicio_ia,
                             modo=self.ocr_modo,
                             idiomas_tesseract=self.ocr_idiomas,
                             ajustes=self.ocr_ajustes)

    def analizar(self, ruta, opciones: OpcionesAnalisis):
        camino = Path(ruta)
        try:
            datos = camino.read_bytes()
        except OSError as error:
            raise ErrorFormato(_("No se ha podido leer el archivo: %s") % error)
        if not datos.startswith(FIRMA):
            raise ErrorFormato(_("El archivo no es un DjVu válido."))
        if len(datos) < 16:
            raise ErrorFormato(_("El archivo DjVu está vacío o truncado."))

        dentro = envoltorios(datos)
        solo_paginas = dentro.paginas
        archivos = dentro.archivos
        marcadores = dentro.marcadores
        paginas: list[tuple[str, bytes]] = []
        con_texto = 0

        # El índice y los envoltorios van en el mismo orden dentro del archivo,
        # que es de lo que se fía DjVuLibre para resolver las referencias.
        por_id = {archivo.identificador: dentro.formularios[numero]
                  for numero, archivo in enumerate(archivos)
                  if numero < len(dentro.formularios)}
        diccionarios: dict = {}

        por_identificador: dict[str, int] = {}
        interesantes = [a for a in archivos if a.es_pagina]
        for numero, archivo in enumerate(interesantes):
            por_identificador[archivo.identificador] = numero

        total = len(solo_paginas)
        reconocidas = 0
        con_imagen = 0
        avisado_sin_ocr = False
        avisado_tope = False
        for numero, trozo in enumerate(solo_paginas, start=1):
            opciones.progreso.paso(numero - 1, total,
                                   _("Leyendo la página %d de %d") % (numero, total))
            texto, zona = "", None
            for interno in trozos(datos, trozo.inicio + 4, trozo.inicio + trozo.largo):
                if interno.nombre == b"TXTz":
                    try:
                        crudo = bzz.descomprimir(
                            datos, interno.inicio,
                            interno.inicio + interno.largo)
                    except Exception as error:
                        log.debug("Página %d: TXTz ilegible (%s)", numero, error)
                        continue
                    texto, zona = _capa_de_texto(crudo)
                elif interno.nombre == b"TXTa":
                    texto, zona = _capa_de_texto(
                        datos[interno.inicio:interno.inicio + interno.largo])
            if texto.strip():
                con_texto += 1
            elif self.ocr_modo != "ninguno":
                # Sin texto reconocido dentro no hay nada que leer, así que se
                # reconoce aquí.  Es lo que convierte medio archivo digitalizado
                # de «no se puede abrir» en un libro.
                if self.ocr_maximo and reconocidas >= self.ocr_maximo:
                    if not avisado_tope:
                        log.info("DjVu: tope de %d páginas reconocidas",
                                 self.ocr_maximo)
                        avisado_tope = True
                else:
                    opciones.progreso.paso(
                        numero - 1, total,
                        _("Reconociendo la página %d de %d...") % (numero, total))
                    imagen = None
                    try:
                        imagen, _es_mascara = imagen_de(
                            datos, trozo,
                            _diccionario_de(datos, trozo, por_id, diccionarios))
                        reconocido = self._reconocer(imagen) if imagen else None
                    except RuntimeError as error:
                        if not avisado_sin_ocr:
                            log.warning("Sin OCR disponible: %s", error)
                            avisado_sin_ocr = True
                        reconocido = None
                    except Exception as error:
                        registrar_excepcion(
                            log, "Error reconociendo la página %d" % numero, error)
                        reconocido = None
                    if reconocido:
                        # El XHTML del motor conserva las columnas y las tablas
                        # que se deducen de dónde está cada palabra; volver a
                        # deducirlas del texto ya aplanado las perdería.
                        paginas.append(("pagina%d" % numero,
                                        _pagina_reconocida(reconocido, numero,
                                                           interesantes)))
                        con_texto += 1
                        reconocidas += 1
                        continue
                    if imagen:
                        # Ni texto dentro ni texto reconocido: es una lámina, un
                        # mapa o una fotografía. Se deja como imagen, que se
                        # recorre con G, se ve con Control+I y se describe con
                        # la IA como la de cualquier otro documento. Antes esta
                        # página no existía.
                        con_imagen += 1
            rotulo = ""
            if numero - 1 < len(interesantes):
                rotulo = interesantes[numero - 1].titulo
            rotulo = rotulo or str(numero)
            paginas.append(("pagina%d" % numero,
                            _pagina_a_xhtml(texto, zona, rotulo,
                                            numero if not texto.strip() else 0)))

        if not paginas:
            raise ErrorFormato(_("El archivo DjVu no tiene páginas."))
        if not con_texto and not con_imagen:
            raise ErrorFormato(_(
                "Este DjVu son solo imágenes escaneadas, no lleva dentro el texto "
                "reconocido y tampoco se ha podido reconocer aquí. Revisa el "
                "motor de reconocimiento en Opciones."))

        metadatos = Metadatos(titulo=camino.stem, autor="", idioma="")
        documento = ensamblador.montar(paginas, metadatos, camino, opciones)

        if marcadores and documento.secciones:
            posiciones = [seccion.inicio for seccion in documento.secciones]
            try:
                indice = _arbol_de_marcadores(marcadores, posiciones, por_identificador)
            except Exception as error:
                registrar_excepcion(log, "Marcadores del DjVu ilegibles", error)
                indice = []
            if indice:
                documento.indice = indice

        if con_texto < total:
            log.info("DjVu: %d de %d páginas con texto (%d reconocidas aquí, "
                     "%d solo imagen)", con_texto, total, reconocidas, con_imagen)
        return documento


#: La instancia registrada.  Tiene nombre propio porque la ventana le pone
#: los ajustes de reconocimiento antes de abrir cada documento.
analizador_djvu = AnalizadorDjVu()
registrar(analizador_djvu)
