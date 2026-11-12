# -*- coding: utf-8 -*-
"""Partido del texto en frases, para leerlo en voz alta.

La lectura continua no manda el libro entero al sintetizador de golpe: lo va
diciendo **frase a frase**.  Esa es la unidad que hace falta para que el lector
sea manejable de verdad:

* pausar y continuar responde al instante, sin esperar a que termine un
  párrafo de veinte líneas;
* «frase anterior» y «frase siguiente» sirven para releer algo que no se ha
  entendido, que es lo que uno hace de forma natural al escuchar;
* al detener la lectura se sabe **exactamente** por dónde iba, y el cursor
  puede quedarse ahí.

El partido se hace sobre el texto del libro y devuelve siempre posiciones
absolutas, las mismas que usa el resto del programa, de modo que la frase que
se está diciendo se puede convertir en un marcador o en un punto de lectura sin
ninguna conversión.

No hay ninguna dependencia externa: es un recorrido del texto con unas cuantas
reglas del español.
"""

from __future__ import annotations

from .idioma import _
import re

#: Signos que pueden terminar una frase.
FINALES = ".?!…:;"

#: Signos de cierre que pueden ir *después* del punto y que todavía forman
#: parte de la misma frase: «Se marchó.» y (Se marchó.) terminan en el cierre,
#: no en el punto.
CIERRES = '"\'»)]}”’'

#: Abreviaturas frecuentes tras las cuales un punto **no** termina la frase.
#: Sin esto, «D. Quijote» o «pág. 45» se leerían en dos trozos, con una pausa
#: en medio que suena a error.
#:
#: Pasa por :func:`_` porque **es un dato del idioma**, no texto de interfaz: al
#: traducir el programa al francés o al alemán hay que poner las abreviaturas de
#: esa lengua, o su lectura en voz alta sonará entrecortada.
ABREVIATURAS = frozenset(_("""
sr sra srta sres dr dra dres d dna dña prof profa lic ing arq
pag pág págs pags num núm nums núms cap caps art arts vol vols ed eds
ej ej etc aprox aprox fig figs tab tabs pta ptas
a.c d.c ac dc ss vv aa
ee uu ss mm rr
""").split())

#: Longitud a partir de la cual una frase se parte aunque no haya llegado a
#: ningún signo.  Hay libros —listas, poesía, textos antiguos— con párrafos
#: enteros sin puntuación; sin este tope, pausar dejaría de responder.
LARGO_MAXIMO = 320

#: Sitios por donde se corta una frase demasiado larga, en orden de
#: preferencia: siempre es mejor cortar en una coma que a mitad de palabra.
CORTES_BLANDOS = ",;— —"

_ESPACIOS = re.compile(r"\s")


def _es_abreviatura(texto: str, punto: int) -> bool:
    """Indica si el punto de esa posición cierra una abreviatura.

    Se mira la palabra que hay justo antes.  También se considera abreviatura
    una inicial suelta («J. Benítez»): una sola letra antes del punto casi
    nunca termina una frase de verdad.
    """
    inicio = punto
    while inicio > 0 and not _ESPACIOS.match(texto[inicio - 1]):
        inicio -= 1
    palabra = texto[inicio:punto].lower().strip("(«\"'¿¡")
    if not palabra:
        return False
    if len(palabra) == 1 and palabra.isalpha():
        return True          # una inicial: «J.», «D.»
    if palabra.rstrip(".") in ABREVIATURAS:
        return True
    # Un número seguido de punto suele ser un decimal o una enumeración
    # («1. Introducción»), no el final de una frase.
    return palabra.isdigit()


def _termina_aqui(texto: str, posicion: int) -> bool:
    """Indica si en esa posición hay un final de frase de verdad."""
    caracter = texto[posicion]
    if caracter not in FINALES:
        return False
    if caracter == "." and _es_abreviatura(texto, posicion):
        return False
    # Detrás tiene que venir un espacio, un salto o el final del texto.  Así
    # «3.14» o «www.ejemplo.com» no se parten por la mitad.
    siguiente = posicion + 1
    while siguiente < len(texto) and texto[siguiente] in CIERRES:
        siguiente += 1
    if siguiente >= len(texto):
        return True
    return bool(_ESPACIOS.match(texto[siguiente]))


def _fin_con_cierres(texto: str, posicion: int) -> int:
    """Devuelve el final de la frase incluyendo comillas y paréntesis."""
    fin = posicion + 1
    while fin < len(texto) and texto[fin] in CIERRES:
        fin += 1
    return fin


def _acortar(texto: str, inicio: int, fin: int) -> int:
    """Recorta una frase demasiado larga por un sitio razonable."""
    tope = inicio + LARGO_MAXIMO
    if fin <= tope:
        return fin
    for posicion in range(tope, inicio + LARGO_MAXIMO // 3, -1):
        if texto[posicion] in CORTES_BLANDOS:
            return posicion + 1
    return tope


def siguiente_frase(texto: str, desde: int) -> tuple[int, int]:
    """Devuelve el tramo ``(inicio, fin)`` de la frase que empieza en ``desde``.

    Se saltan los espacios y los saltos de línea iniciales, de modo que
    ``inicio`` cae siempre en el primer carácter que se va a decir.  Un salto
    de línea cierra la frase aunque no haya signo: en este programa cada línea
    del libro es un párrafo completo, y leer dos párrafos seguidos sin pausa
    los mezcla.

    :return: ``(inicio, fin)``, o ``(len(texto), len(texto))`` si ya no queda
             nada por leer.
    """
    total = len(texto)
    inicio = max(0, min(desde, total))
    while inicio < total and texto[inicio].isspace():
        inicio += 1
    if inicio >= total:
        return total, total
    posicion = inicio
    while posicion < total:
        if texto[posicion] == "\n":
            return inicio, _acortar(texto, inicio, posicion)
        if _termina_aqui(texto, posicion):
            return inicio, _acortar(texto, inicio, _fin_con_cierres(texto, posicion))
        if posicion - inicio >= LARGO_MAXIMO:
            return inicio, _acortar(texto, inicio, posicion)
        posicion += 1
    return inicio, total


def frase_anterior(texto: str, desde: int) -> tuple[int, int]:
    """Devuelve el tramo de la frase que hay **antes** de ``desde``.

    Se resuelve retrocediendo hasta el principio del párrafo y avanzando desde
    ahí, en lugar de partir el texto hacia atrás: las reglas de las
    abreviaturas solo funcionan bien leyendo en el sentido normal.  El párrafo
    es corto, así que el coste es irrelevante.
    """
    if desde <= 0:
        return 0, 0
    principio = texto.rfind("\n", 0, desde) + 1
    if principio >= desde:
        # Estamos justo al empezar un párrafo: se busca en el anterior.
        anterior = texto.rfind("\n", 0, max(principio - 1, 0)) + 1
        principio = anterior
    ultimo = (principio, principio)
    cursor = principio
    while cursor < desde:
        inicio, fin = siguiente_frase(texto, cursor)
        if fin <= inicio or inicio >= desde:
            break
        ultimo = (inicio, fin)
        cursor = fin
    return ultimo


def para_decir(texto: str) -> str:
    """Limpia una frase antes de mandarla al sintetizador.

    Se colapsan los espacios y los saltos de línea: el sintetizador los lee
    como pausas raras, y en un libro convertido a texto abundan.
    """
    return " ".join(texto.split())


# ---------------------------------------------------------------------------
# Renglones: la misma frase, pero para el cursor
# ---------------------------------------------------------------------------
#
# Todo lo de arriba parte el texto para **decirlo**.  Lo que sigue lo parte
# para **mirarlo con el cursor**, que es un problema distinto y que solo
# aparece con un lector de pantalla delante.
#
# La lectura continua de un lector de pantalla (`NVDA+A`) va diciendo el texto
# renglón a renglón y deja el cursor **al principio del renglón que está
# sonando**.  Con cada párrafo en una sola línea —que es como se lee un libro
# sin ajuste de línea—, eso quiere decir que al parar la lectura el cursor
# aparece al principio del párrafo entero: se han oído veinte líneas y hay que
# volver a bajar por ellas para seguir a mano.
#
# La cura es que el renglón sea la frase.  Y se consigue **cambiando un espacio
# por un salto de línea**: el que separa una frase de la siguiente.  Es
# importante que sea un cambio y no una inserción, porque así el texto que ve
# el control mide exactamente lo mismo que el del libro y **ninguna posición se
# mueve**: los marcadores, las notas, los resaltados y por dónde ibas siguen
# apuntando al mismo carácter.

#: Signos que cierran una frase a efectos de renglón.  Es un subconjunto de
#: :data:`FINALES`: los dos puntos y el punto y coma parten bien para decir
#: —dan una pausa— pero como renglón trocean demasiado, y una enumeración de
#: diez elementos separados por punto y coma acabaría en diez renglones de tres
#: palabras.
FINALES_DE_RENGLON = ".?!…"

#: Un final de frase seguido de sus cierres y de los espacios que lo separan de
#: la siguiente.  El texto se recorre con una expresión regular y no carácter a
#: carácter porque aquí se parten cientos de miles de caracteres de una vez, al
#: cargar el texto en el control, y hacerlo en Python costaría segundos.
_FIN_DE_RENGLON = re.compile(r"[.?!…][\"'»)\]}”’]*([ \t]+)(?=\S)")

#: Un final de frase muy cerca del principio del párrafo casi nunca es una
#: frase: es el número o la letra con que se enumera («IV. La guerra del
#: Peloponeso»).  Los números ya los descarta :func:`_es_abreviatura`; esto
#: recoge los romanos y las letras de un índice.
MARGEN_ENUMERACION = 8


def _cortes_blandos(texto: str, inicio: int, fin: int) -> list[int]:
    """Parte por dentro un tramo sin puntuación que se ha quedado larguísimo.

    Hay párrafos —listas volcadas en una línea, poesía, textos antiguos— que
    no traen un solo punto en dos mil caracteres.  Sin esto seguirían siendo un
    renglón único y el problema que se quería arreglar seguiría ahí, solo que
    en menos sitios.

    Se corta por donde menos se nota: detrás de una coma, un punto y coma o una
    raya; y si no hay ninguna, por el último espacio que quepa.
    """
    cortes: list[int] = []
    desde = inicio
    while fin - desde > LARGO_MAXIMO:
        tope = desde + LARGO_MAXIMO
        minimo = desde + LARGO_MAXIMO // 3
        elegido = -1
        for posicion in range(tope, minimo, -1):
            if texto[posicion] in " \t" and texto[posicion - 1] in CORTES_BLANDOS:
                elegido = posicion
                break
        if elegido < 0:
            for posicion in range(tope, minimo, -1):
                if texto[posicion] in " \t":
                    elegido = posicion
                    break
        if elegido < 0:
            return cortes          # una palabra kilométrica: no hay por dónde
        cortes.append(elegido)
        desde = elegido + 1
    return cortes


def cortes_de_renglon(texto: str) -> list[int]:
    """Devuelve las posiciones de los espacios que deben pasar a salto de línea.

    Cada posición de la lista apunta a un espacio —nunca a otra cosa—, de modo
    que quien las use puede cambiar ese carácter por ``\n`` sabiendo que el
    texto conserva exactamente su longitud.

    :param texto: Texto del libro, o el tramo de él que se vaya a enseñar.
    :return: Posiciones ordenadas de menor a mayor.
    """
    cortes: list[int] = []
    principio_de_parrafo = 0
    ultimo_corte = 0
    for coincidencia in _FIN_DE_RENGLON.finditer(texto):
        signo = coincidencia.start()
        # El salto de línea anterior manda: es el principio del párrafo, y
        # desde ahí se cuentan tanto la enumeración como el tramo largo.
        salto = texto.rfind("\n", ultimo_corte, signo)
        if salto >= 0:
            principio_de_parrafo = salto + 1
            ultimo_corte = max(ultimo_corte, principio_de_parrafo)
        if signo - principio_de_parrafo < MARGEN_ENUMERACION:
            continue
        if texto[signo] == "." and _es_abreviatura(texto, signo):
            continue
        # El último de los espacios es el que se convierte: así el renglón
        # nuevo empieza en la primera letra y no en un hueco.
        corte = coincidencia.end(1) - 1
        cortes.extend(_cortes_blandos(texto, ultimo_corte, corte))
        cortes.append(corte)
        ultimo_corte = corte + 1
    final = texto.find("\n", ultimo_corte)
    cortes.extend(_cortes_blandos(texto, ultimo_corte,
                                  len(texto) if final < 0 else final))
    return cortes


def partir_en_renglones(texto: str) -> str:
    """Devuelve el texto con cada frase en su propio renglón.

    **Mide exactamente lo mismo que el original**: lo único que cambia es que
    algunos espacios pasan a ser saltos de línea.  De eso depende que las
    posiciones del libro sigan valiendo tal cual dentro del control de texto,
    así que está comprobado en las pruebas.
    """
    cortes = cortes_de_renglon(texto)
    if not cortes:
        return texto
    trozos: list[str] = []
    anterior = 0
    for corte in cortes:
        trozos.append(texto[anterior:corte])
        trozos.append("\n")
        anterior = corte + 1
    trozos.append(texto[anterior:])
    partido = "".join(trozos)
    if len(partido) != len(texto):     # pragma: no cover - red de seguridad
        return texto
    return partido
