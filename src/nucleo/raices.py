# -*- coding: utf-8 -*-
"""La raíz de una palabra en español, para que buscar encuentre de verdad.

Buscar «amortización» y que no salga «amortizaciones» —ni «amortizar», ni
«amortizado»— es el fallo más frecuente de cualquier buscador, y en un libro de
estudio es el que más cuesta: los apuntes usan el verbo, el enunciado usa el
sustantivo y el índice usa el plural.

Aquí se recorta cada palabra hasta su raíz, y se compara por la raíz. Con eso,
las cuatro formas de arriba son la misma cosa.

Es el **algoritmo de Snowball para español** (Martin Porter y Richard Boulton),
que es el que usan los buscadores desde hace veinte años, escrito aquí en
Python siguiendo su definición al pie de la letra. Se hace propio y no se trae
una biblioteca porque son doscientas líneas sin nada que instalar, y porque así
las reglas están escritas donde se pueden leer y corregir.

**El detalle que decide si esto ayuda o estorba** es dónde se puede cortar. El
algoritmo define tres regiones —``R1``, ``R2`` y ``RV``— y **cada sufijo solo se
quita si empieza dentro de la suya**. Sin esa condición, «casa» se quedaría en
«c» y «los» en «l», y entonces todas las palabras cortas se parecerían entre sí
y la búsqueda devolvería el libro entero.
"""

from __future__ import annotations

VOCALES = "aeiouáéíóúü"

#: Sufijos que se quitan enteros si empiezan dentro de R2.
_R2_BORRAR = (
    "amientos", "imientos", "amiento", "imiento", "anzas", "anza",
    "icos", "icas", "ismos", "ables", "ibles", "istas", "osos", "osas",
    "ico", "ica", "ismo", "able", "ible", "ista", "oso", "osa",
)

#: Sufijos de agente y de acción. Se quitan si están en R2 y, además, si
#: dejan un «ic» detrás también dentro de R2, se quita ese «ic».
_R2_BORRAR_IC = (
    "aciones", "adoras", "adores", "ancias", "antes", "ación", "acion",
    "adora", "ancia", "ador", "ante",
)

#: Sufijos que no se borran: se **sustituyen** por otra cosa.
_R2_CAMBIAR = (
    ("logías", "log"), ("logía", "log"),
    ("uciones", "u"), ("ución", "u"), ("ucion", "u"),
    ("encias", "ente"), ("encia", "ente"),
)

#: Terminaciones de verbo que empiezan por «y» y solo se quitan tras una «u».
_VERBO_Y = ("yeron", "yendo", "yamos", "yais", "yan", "yen", "yas", "yes",
            "ya", "ye", "yo", "yó")

#: Terminaciones de verbo. Van de la más larga a la más corta porque el
#: algoritmo pide **la coincidencia más larga**: buscando la corta primero,
#: «cantábamos» se quedaría en «cantáb» en vez de en «cant».
_VERBO = (
    "iésemos", "iéramos", "ásemos", "áramos", "ábamos", "ieseis", "ierais",
    "iríamos", "eríamos", "aríamos", "isteis", "asteis", "ieses", "ieras",
    "iendo", "ieron", "iesen", "ieran", "iera", "iese", "iste", "idos",
    "idas", "iría", "irías", "irían", "iríais", "iremos", "iréis", "irás",
    "irán", "irá", "iré", "imos", "ido", "ida", "ió", "ir", "id",
    "eríais", "eremos", "erías", "erían", "eréis", "erás", "erán",
    "ería", "erá", "eré", "emos", "éis", "ed", "er", "en", "es",
    "aríais", "aremos", "arías", "arían", "aréis", "arás", "arán",
    "aría", "ará", "aré", "abais", "ábais", "arais", "aseis", "asen",
    "aran", "aras", "ases", "aron", "ados", "adas", "abas", "aban", "ando",
    "aste", "ase", "ara", "ada", "ado", "aba", "an", "as", "ad",
    "ar", "amos", "ían", "ías", "íais", "íamos", "ía", "ís", "áis",
)
# Ojo con lo que **no** está en esta lista: «ais» sin tilde no es una
# terminación de verbo en español, y meterla dejaría «Beauvais» en «beauv» y
# «Monsiváis» en «monsiv». Los apellidos son justo lo que más se busca en un
# índice, así que un recorte de más ahí se nota enseguida.

#: Lo que queda al final, cuando ya no hay sufijo de verbo ni de derivación.
_RESIDUALES = ("os", "a", "o", "á", "í", "ó", "e", "é")

#: Pronombres que se pegan detrás del verbo: «dárselo», «cantándola».
_PRONOMBRES = ("selas", "selos", "sela", "selo", "las", "les", "los", "nos",
               "me", "se", "la", "le", "lo")

#: Formas de verbo que admiten llevar un pronombre pegado detrás, con lo que
#: hay que dejar escrito al quitarlo: «dárselo» deja «dar», no «dár».
_ANTES_DEL_PRONOMBRE = (("iéndo", "iendo"), ("ándo", "ando"), ("ár", "ar"),
                        ("ér", "er"), ("ír", "ir"), ("iendo", "iendo"),
                        ("ando", "ando"), ("ar", "ar"), ("er", "er"),
                        ("ir", "ir"))

_SIN_TILDE = str.maketrans("áéíóú", "aeiou")


def _es_vocal(letra: str) -> bool:
    return letra in VOCALES


def _regiones(palabra: str) -> tuple[int, int, int]:
    """Dónde empiezan R1, R2 y RV.

    - **R1** empieza detrás de la primera vocal seguida de consonante.
    - **R2** es lo mismo, buscado dentro de R1.
    - **RV** tiene su propia regla, más suelta, porque las terminaciones de
      verbo caen mucho más cerca del principio de la palabra.
    """
    largo = len(palabra)

    def tras_vocal_consonante(desde: int) -> int:
        indice = desde
        while indice < largo and not _es_vocal(palabra[indice]):
            indice += 1
        while indice < largo and _es_vocal(palabra[indice]):
            indice += 1
        return min(indice + 1, largo) if indice < largo else largo

    r1 = tras_vocal_consonante(0)
    r2 = tras_vocal_consonante(r1)

    rv = largo
    if largo >= 3:
        if not _es_vocal(palabra[1]):
            # Consonante en segundo lugar: RV empieza tras la vocal siguiente.
            indice = 2
            while indice < largo and not _es_vocal(palabra[indice]):
                indice += 1
            rv = min(indice + 1, largo)
        elif _es_vocal(palabra[0]) and _es_vocal(palabra[1]):
            # Dos vocales al principio: tras la consonante siguiente.
            indice = 2
            while indice < largo and _es_vocal(palabra[indice]):
                indice += 1
            rv = min(indice + 1, largo)
        else:
            rv = 3
    return r1, r2, rv


def _quitar(palabra: str, sufijos, desde: int):
    """Quita el sufijo más largo que empiece en ``desde`` o más allá."""
    for sufijo in sorted(sufijos, key=len, reverse=True):
        if palabra.endswith(sufijo) and len(palabra) - len(sufijo) >= desde:
            return palabra[:-len(sufijo)], sufijo
    return palabra, ""


def _pronombre_pegado(palabra: str, rv: int) -> str:
    """Le quita al verbo el pronombre que lleve pegado detrás."""
    for pronombre in sorted(_PRONOMBRES, key=len, reverse=True):
        if not palabra.endswith(pronombre):
            continue
        tronco = palabra[:-len(pronombre)]
        for terminacion, escrito in _ANTES_DEL_PRONOMBRE:
            if tronco.endswith(terminacion) and len(tronco) - len(terminacion) >= rv:
                return tronco[:-len(terminacion)] + escrito
        if tronco.endswith("yendo") and len(tronco) - 5 >= rv \
                and tronco[:-5].endswith("u"):
            return tronco
        return palabra
    return palabra


def _derivacion(palabra: str, r1: int, r2: int) -> tuple[str, bool]:
    """Quita los sufijos que forman palabras a partir de otras."""
    for sufijo, cambio in _R2_CAMBIAR:
        if palabra.endswith(sufijo) and len(palabra) - len(sufijo) >= r2:
            return palabra[:-len(sufijo)] + cambio, True

    tronco, sufijo = _quitar(palabra, _R2_BORRAR, r2)
    if sufijo:
        return tronco, True

    tronco, sufijo = _quitar(palabra, _R2_BORRAR_IC, r2)
    if sufijo:
        if tronco.endswith("ic") and len(tronco) - 2 >= r2:
            tronco = tronco[:-2]
        return tronco, True

    if palabra.endswith("amente") and len(palabra) - 6 >= r1:
        tronco = palabra[:-6]
        for cola in ("iv", "os", "ic", "ad"):
            if tronco.endswith(cola) and len(tronco) - len(cola) >= r2:
                tronco = tronco[:-len(cola)]
                if cola == "iv" and tronco.endswith("at") and len(tronco) - 2 >= r2:
                    tronco = tronco[:-2]
                break
        return tronco, True

    if palabra.endswith("mente") and len(palabra) - 5 >= r2:
        tronco = palabra[:-5]
        for cola in ("ante", "able", "ible"):
            if tronco.endswith(cola) and len(tronco) - len(cola) >= r2:
                tronco = tronco[:-len(cola)]
                break
        return tronco, True

    for sufijo in ("idades", "idad"):
        if palabra.endswith(sufijo) and len(palabra) - len(sufijo) >= r2:
            tronco = palabra[:-len(sufijo)]
            for cola in ("abil", "ic", "iv"):
                if tronco.endswith(cola) and len(tronco) - len(cola) >= r2:
                    tronco = tronco[:-len(cola)]
                    break
            return tronco, True

    for sufijo in ("ivas", "ivos", "iva", "ivo"):
        if palabra.endswith(sufijo) and len(palabra) - len(sufijo) >= r2:
            tronco = palabra[:-len(sufijo)]
            if tronco.endswith("at") and len(tronco) - 2 >= r2:
                tronco = tronco[:-2]
            return tronco, True
    return palabra, False


def _verbo(palabra: str, rv: int) -> tuple[str, bool]:
    """Quita las terminaciones de conjugación."""
    # Las terminaciones que empiezan por «y» solo son de verbo cuando llevan
    # una «u» delante: «construyeron», «huyendo». Si no la llevan, **no se
    # abandona**: se sigue por las terminaciones normales, y por eso «apoyamos»
    # da «apoy» y no «apoyam». Rendirse aquí era el fallo que dejaba sin
    # recortar «playas», «bueyes» y media docena de apellidos.
    for sufijo in sorted(_VERBO_Y, key=len, reverse=True):
        if palabra.endswith(sufijo) and len(palabra) - len(sufijo) >= rv:
            if palabra[:-len(sufijo)].endswith("u"):
                return palabra[:-len(sufijo)], True
            break

    tronco, sufijo = _quitar(palabra, _VERBO, rv)
    if not sufijo:
        return palabra, False
    if sufijo in ("en", "es", "éis", "emos") and tronco.endswith("gu"):
        # «distingues» es de «distinguir»: la «u» solo estaba para que la «g»
        # sonara fuerte delante de la «e», y sin la «e» sobra.
        tronco = tronco[:-1]
    return tronco, True


def raiz(palabra: str) -> str:
    """La raíz de una palabra española.

    Devuelve la palabra en minúsculas, sin tildes y recortada. Las palabras de
    menos de tres letras se dejan como están: no hay nada que recortar sin
    quedarse con una sola letra.
    """
    limpia = (palabra or "").strip().lower()
    if len(limpia) < 3:
        return limpia.translate(_SIN_TILDE)

    r1, r2, rv = _regiones(limpia)
    trabajo = _pronombre_pegado(limpia, rv)
    trabajo, hecho = _derivacion(trabajo, r1, r2)
    if not hecho:
        trabajo, hecho = _verbo(trabajo, rv)

    for sufijo in sorted(_RESIDUALES, key=len, reverse=True):
        if trabajo.endswith(sufijo) and len(trabajo) - len(sufijo) >= rv:
            trabajo = trabajo[:-len(sufijo)]
            if sufijo in ("e", "é") and trabajo.endswith("gu") \
                    and len(trabajo) - 1 >= rv:
                trabajo = trabajo[:-1]
            break

    return trabajo.translate(_SIN_TILDE)


def raices(texto: str) -> list[str]:
    """Las raíces de todas las palabras de un texto, en orden."""
    return [raiz(palabra) for palabra in palabras(texto)]


def palabras(texto: str) -> list[str]:
    """Parte un texto en palabras, quedándose solo con letras y cifras."""
    salida = []
    actual = []
    for letra in (texto or "").lower():
        if letra.isalnum():
            actual.append(letra)
        elif actual:
            salida.append("".join(actual))
            actual = []
    if actual:
        salida.append("".join(actual))
    return salida
