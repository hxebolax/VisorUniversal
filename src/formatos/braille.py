# -*- coding: utf-8 -*-
"""Lectura de archivos BRA (Braille ASCII español).

Un archivo ``.bra`` no contiene letras en tinta aunque, abierto en el Bloc de
notas, muchas de ellas lo parezcan. Cada byte representa un signo braille según
la tabla ASCII española empleada por la ONCE. Además, las líneas ya vienen
partidas al ancho del papel y las páginas pueden separarse con un salto de
página.

Este analizador hace el camino inverso para que el documento llegue al
``wx.TextCtrl`` del visor como texto español corriente:

* convierte la tabla BRA a caracteres de tinta;
* interpreta los signos de mayúscula y de número;
* recompone palabras y párrafos partidos por las líneas braille;
* conserva como marcas los saltos de página que estén en el archivo.

La transcripción inversa es literaria, en español y sin abreviaturas. Las
partituras, las fórmulas y los documentos estenográficos necesitan sus códigos
especializados y no se pueden convertir de forma inequívoca con esta tabla.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path

from nucleo.documento import Metadatos
from nucleo.idioma import _

from .base import Analizador, ErrorFormato, OpcionesAnalisis, registrar
from .ensamblador import escapar, envolver, montar


# La tabla transforma cada posible byte de BRA en el byte equivalente de la
# página de códigos occidental que usa la tabla española. Está completa (no
# solo las vocales con tilde) porque también existen archivos BRA de ocho
# puntos. Mantenerla como una permutación de 256 bytes evita que Python trate
# antes de tiempo como texto lo que todavía son celdas braille.
_TABLA_BRA_A_CP1252 = base64.b64decode(
    "AMICAwTKBgcIzgoLDA0O1BAREhMU2xYXGBkawBzZHh8gISIj6SUmJ+H6KissLS7t8zEy"
    "MzQ1Njc4OTo7PD0+P0BBQkNERUZHSElKS0xNTk9QUVJTVFVWV1hZWsFc2l5fYGFiY2Rl"
    "ZmdoaWprbG1ub3BxcnN0dXZ3eHl6e8x9fn8k/Ojj5IWG5yjris2MLymPyZGSk/bT/jCY"
    "mZrvnJ2en+Ds8vnx0aa/qKmqvfutrl2whLKzu7W2t7i5urzEjr6ntJvqw7HFxt2i0ICL"
    "W5ajrAnugaB8z8jX2B2J9xvH3tbi39WU/eXmh4Olr5Xc0qsF8KEVD431AfT4gpDLpIiX/"
    "w=="
)

_DIGITOS = dict(zip("abcdefghij", "1234567890"))

# En musicografía y en algunos textos didácticos los ordinales se escriben con
# las cifras de la parte baja de la celda. Son muy frecuentes en BRA españoles
# (2.ª, 3.ª, etc.) y no deben quedar como una sucesión de signos extraños.
_ORDINALES_INFERIORES = {
    ",": "1", ";": "2", ":": "3", "*": "4", "?": "5", "+": "6",
    "=": "7",
}

_MARCA_PAGINA = re.compile(r"\ue000(\d+)\ue001")
_NUMERO_BRA = r"#[a-j]+"
_CABECERA_PAGINA = re.compile(rf"{_NUMERO_BRA}(?:\s+{_NUMERO_BRA})?")
_PIE_MECANICO = re.compile(r"#[a-j]+-#[a-j{]+")

_HTML = re.compile(br"^\s*(?:<!doctype\s+html\b|<html\b)", re.IGNORECASE)
_TITULO_HTML = re.compile(br"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def _comprobar_contenido(datos: bytes) -> None:
    """Rechaza errores de descarga y contenido que no puede ser un BRA."""
    if not datos:
        raise ErrorFormato(_("El archivo BRA está vacío."))
    if _HTML.search(datos[:4096]):
        encontrado = _TITULO_HTML.search(datos[:20000])
        titulo = ""
        if encontrado:
            titulo = encontrado.group(1).decode("utf-8", errors="replace").strip()
        detalle = _(" La página guardada se titula «%s».") % titulo if titulo else ""
        raise ErrorFormato(_(
            "Este archivo no contiene braille: es una página HTML guardada con la "
            "extensión .bra.%s Vuelve a descargar el archivo BRA original."
        ) % detalle)


def descifrar(datos: bytes) -> str:
    """Pasa los bytes de la tabla BRA española a caracteres intermedios.

    El resultado todavía conserva ``{`` como signo de mayúscula y ``#`` como
    signo de número. :func:`a_tinta` interpreta después esos signos según su
    contexto.
    """
    _comprobar_contenido(datos)
    # Algunas descargas antiguas sustituyeron una celda de espaciado no ASCII
    # por U+FFFD. En los libros afectados aparece sola, entre espacios, y no
    # contiene texto recuperable. Quitar la secuencia antes de aplicar la tabla
    # evita mostrarla después como los tres signos espurios «§Ž».
    datos = datos.replace(b"\xef\xbf\xbd", b" ")
    return datos.translate(_TABLA_BRA_A_CP1252).decode("cp1252", errors="replace")


def _es_apertura(texto: list[str]) -> bool:
    """Dice si un signo doble está abriendo interrogación o exclamación."""
    if not texto or texto[-1].isspace():
        return True
    return texto[-1] in "([{\u2014-:;\u00ab\u00bf\u00a1.!?"


def _linea_a_tinta(linea: str) -> str:
    """Interpreta los indicadores braille de una línea ya descifrada."""
    salida: list[str] = []
    numero = False
    mayuscula = False
    palabra_en_mayusculas = False
    comillas_abiertas = False
    indice = 0

    while indice < len(linea):
        caracter = linea[indice]

        if caracter == "{" and numero:
            # En números antiguos mantiene el modo numérico: #a{i = 19.
            indice += 1
            continue

        if caracter == "{":
            if indice + 1 < len(linea) and linea[indice + 1] == "{":
                palabra_en_mayusculas = True
                indice += 2
            else:
                mayuscula = True
                indice += 1
            continue

        if caracter == "#":
            numero = True
            indice += 1
            continue

        if numero:
            # Los ordinales inferiores son secuencias completas: #;a, #:a...
            # La ``a`` final no es una cifra, sino el indicador femenino.
            if (caracter in _ORDINALES_INFERIORES and indice + 1 < len(linea)
                    and linea[indice + 1].lower() in ("a", "o")):
                salida.append(_ORDINALES_INFERIORES[caracter])
                salida.append("ª" if linea[indice + 1].lower() == "a" else "º")
                numero = False
                indice += 2
                continue
            if caracter.lower() in _DIGITOS:
                salida.append(_DIGITOS[caracter.lower()])
                indice += 1
                continue
            if caracter in ",.-":
                salida.append(caracter)
                indice += 1
                continue
            numero = False

        if caracter == "2":
            salida.append("(")
            mayuscula = False
            indice += 1
            continue

        if caracter == "Ì":
            # La tabla BRA usa este código como cierre de un inciso rotulado:
            # ``a|`` y ``b|`` son «a)» y «b)» en tinta.
            salida.append(")")
            mayuscula = False
            indice += 1
            continue

        if caracter in "}>":
            # Delimitador de cursiva o énfasis, no un carácter en tinta.
            # ``>`` marca además el comienzo de ciertos párrafos continuados.
            indice += 1
            continue

        if caracter == "_":
            # Prefijo para representar literalmente el signo siguiente.
            indice += 1
            continue

        if caracter == "7":
            caracter = "ñ"
        elif caracter == "8":
            caracter = "ü"

        if caracter.isalpha():
            if palabra_en_mayusculas or mayuscula:
                caracter = caracter.upper()
            salida.append(caracter)
            mayuscula = False
            indice += 1
            continue

        if palabra_en_mayusculas and not caracter.isalpha():
            palabra_en_mayusculas = False

        if caracter == "?":
            salida.append("¿" if _es_apertura(salida) else "?")
        elif caracter == "!":
            salida.append("¡" if _es_apertura(salida) else "!")
        elif caracter == "<":
            # Normalmente es una comilla. En esta codificación también puede
            # cerrar una exclamación destacada, escrita como !}texto}<.
            texto_parcial = "".join(salida)
            if texto_parcial.rfind("¡") > texto_parcial.rfind("!"):
                salida.append("!")
            else:
                salida.append('"')
        elif caracter == "'":
            salida.append("«" if not comillas_abiertas else "»")
            comillas_abiertas = not comillas_abiertas
        else:
            # Lo que no se conoce se conserva. Es especialmente importante en
            # fórmulas y partituras: mostrar un signo raro es mejor que borrar
            # información silenciosamente.
            salida.append(caracter)
        mayuscula = False
        indice += 1

    return "".join(salida).rstrip()


def _es_decoracion(linea: str) -> bool:
    """Reconoce subrayados hechos con celdas repetidas."""
    limpia = linea.strip()
    return len(limpia) >= 3 and len(set(limpia)) == 1 and limpia[0] in ":c"


def _sangria(linea: str) -> int:
    return len(linea) - len(linea.lstrip(" "))


def _es_comienzo_de_bloque(
        original: str, traducida: str, sangria_anterior: int | None) -> bool:
    """Reconoce sangrías y listas que empiezan un párrafo nuevo."""
    limpia = traducida.lstrip()
    if limpia.startswith(("--", "—", "• ")):
        return True
    # En composición braille el primer renglón suele avanzar dos celdas. Los
    # bloques citados pueden tener margen propio, de modo que importa el salto
    # relativo y no una sangría absoluta (que partiría cada línea de una cita).
    return sangria_anterior is not None and _sangria(original) == sangria_anterior + 2


def _recomponer_pagina(pagina: str) -> str:
    """Quita el corte físico de 40 celdas y recupera los párrafos."""
    originales = pagina.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    parrafos: list[str] = []
    actual = ""
    sangria_anterior: int | None = None

    def guardar() -> None:
        nonlocal actual
        if actual.strip():
            parrafos.append(actual.strip())
        actual = ""

    for original in originales:
        traducida = _linea_a_tinta(original.rstrip())
        limpia = traducida.strip()
        if not limpia or _es_decoracion(limpia):
            guardar()
            sangria_anterior = None
            continue
        if actual and _es_comienzo_de_bloque(original, traducida, sangria_anterior):
            guardar()
        if not actual:
            actual = limpia
        elif actual.endswith("-") and limpia[:1].isalpha():
            # El guion colocado al final de un renglón por la composición
            # braille no pertenece a la palabra.
            actual = actual[:-1] + limpia
        else:
            actual += " " + limpia
        sangria_anterior = _sangria(original)
    guardar()
    return "\n\n".join(parrafos)


def _separar_paginas(texto: str) -> tuple[list[list[str]], bool]:
    """Obtiene páginas explícitas o páginas BRA antiguas de altura fija."""
    normalizado = texto.replace("\r\n", "\n").replace("\r", "\n")
    if "\x0c" in normalizado:
        return [pagina.split("\n") for pagina in normalizado.split("\x0c")], True

    lineas = normalizado.split("\n")
    # Los libros ONCE clásicos suelen estar compuestos a 29 renglones; BRF y
    # otros productores emplean también 25. Solo se infiere altura cuando hay
    # al menos dos páginas completas y el total encaja exactamente.
    for alto in (29, 25):
        variantes = [lineas]
        if lineas and not lineas[-1]:
            variantes.append(lineas[:-1])
        for candidatas in variantes:
            if len(candidatas) >= alto * 2 and len(candidatas) % alto == 0:
                return [candidatas[i:i + alto]
                        for i in range(0, len(candidatas), alto)], False
    if lineas and not lineas[-1]:
        lineas.pop()
    return [lineas], False


def _es_marca_mecanica(linea: str, fila: int, alto: int, ancho: int) -> bool:
    """Descarta folios y el identificador repetido del trabajo de impresión."""
    limpia = linea.strip()
    sangria = _sangria(linea)
    if fila == 0 and sangria >= max(10, ancho // 2):
        if _CABECERA_PAGINA.fullmatch(limpia):
            return True
    if fila == alto - 1 and sangria >= max(10, ancho // 2):
        if _PIE_MECANICO.fullmatch(limpia):
            return True
    return False


def _recomponer_documento(paginas: list[list[str]], corte_duro: bool) -> list[str]:
    """Recompone párrafos entre páginas y conserva sus posiciones como marcas."""
    parrafos: list[str] = []
    actual = ""
    pendientes = ""
    sangria_anterior: int | None = None
    ancho = max((len(linea) for pagina in paginas for linea in pagina), default=0)

    def guardar() -> None:
        nonlocal actual
        if _MARCA_PAGINA.sub("", actual).strip():
            parrafos.append(actual.strip())
        elif actual:
            # Puede contener solo marcas de una página en blanco.
            pendientes_locales.append(actual)
        actual = ""

    # Una lista permite que guardar() mueva marcas sin declarar otro nonlocal.
    pendientes_locales: list[str] = []

    for numero, pagina in enumerate(paginas, start=1):
        if numero > 1 and corte_duro:
            guardar()
            sangria_anterior = None
        marca = f"\ue000{numero}\ue001"
        if actual:
            actual += marca
        else:
            pendientes += marca

        for fila, original in enumerate(pagina):
            if _es_marca_mecanica(original, fila, len(pagina), ancho):
                continue
            traducida = _linea_a_tinta(original.rstrip())
            limpia = traducida.strip()
            if not limpia or _es_decoracion(limpia):
                guardar()
                if pendientes_locales:
                    pendientes += "".join(pendientes_locales)
                    pendientes_locales.clear()
                sangria_anterior = None
                continue
            palabra_partida = bool(
                re.search(r"-(?:\ue000\d+\ue001)*$", actual)
                and limpia[:1].isalpha()
            )
            if (actual and not palabra_partida and _es_comienzo_de_bloque(
                    original, traducida, sangria_anterior)):
                guardar()
            if not actual:
                if pendientes_locales:
                    pendientes += "".join(pendientes_locales)
                    pendientes_locales.clear()
                actual = pendientes + limpia
                pendientes = ""
            elif palabra_partida:
                # Quita el guion de composición incluso si entre ambas mitades
                # cayó una marca de página.
                actual = re.sub(
                    r"-((?:\ue000\d+\ue001)*)$", r"\1", actual) + limpia
            else:
                actual += " " + limpia
            sangria_anterior = _sangria(original)

    guardar()
    if pendientes_locales:
        pendientes += "".join(pendientes_locales)
    if pendientes:
        parrafos.append(pendientes)
    return parrafos


def _parrafos_a_xhtml(parrafos: list[str]) -> str:
    """Escapa el texto dejando las marcas de página como elementos XHTML."""
    cuerpo: list[str] = []
    for parrafo in parrafos:
        cuerpo.append("<p>")
        posicion = 0
        for encontrada in _MARCA_PAGINA.finditer(parrafo):
            cuerpo.append(escapar(parrafo[posicion:encontrada.start()]))
            numero = encontrada.group(1)
            cuerpo.append(
                '<span role="doc-pagebreak" title="%s"></span>' % numero
            )
            posicion = encontrada.end()
        cuerpo.append(escapar(parrafo[posicion:]))
        cuerpo.append("</p>")
    return "".join(cuerpo)


def a_tinta(datos: bytes) -> list[str]:
    """Devuelve las páginas de un BRA como texto español para pantalla."""
    texto = descifrar(datos)
    paginas, _ = _separar_paginas(texto)
    ancho = max((len(linea) for pagina in paginas for linea in pagina), default=0)
    resultado: list[str] = []
    for pagina in paginas:
        limpias = [
            linea for fila, linea in enumerate(pagina)
            if not _es_marca_mecanica(linea, fila, len(pagina), ancho)
        ]
        resultado.append(_recomponer_pagina("\n".join(limpias)))
    return resultado


class AnalizadorBraille(Analizador):
    """Archivos de braille ASCII español usados por la ONCE."""

    extensiones = (".bra",)
    descripcion = _("Braille ASCII español")

    def analizar(self, ruta, opciones: OpcionesAnalisis):
        destino = Path(ruta)
        texto = descifrar(destino.read_bytes())
        paginas, corte_duro = _separar_paginas(texto)
        parrafos = _recomponer_documento(paginas, corte_duro)
        if not any(_MARCA_PAGINA.sub("", parrafo).strip() for parrafo in parrafos):
            raise ErrorFormato(_("El archivo BRA no contiene texto legible."))

        metadatos = Metadatos(
            titulo=destino.stem,
            idioma="es",
            descripcion=_(
                "Texto recuperado de un archivo BRA (Braille ASCII español, "
                "transcripción literaria sin abreviaturas)."
            ),
        )
        xhtml = envolver(_parrafos_a_xhtml(parrafos))
        return montar([(destino.name, xhtml)], metadatos, destino, opciones)


registrar(AnalizadorBraille())
