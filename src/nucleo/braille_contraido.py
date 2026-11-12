# -*- coding: utf-8 -*-
"""Braille contraído español, o de grado 2.

Lo que se exporta a braille es, por omisión, **integral**: una celda por letra.
El contraído ocupa alrededor de un tercio menos y es lo que lee con soltura
quien aprendió braille de pequeño; en una impresora, un tercio menos de papel es
un tercio menos de tomos.

Se sigue el **documento técnico B 16-1 de la Comisión Braille Española**,
«Braille contraído español y criterios didácticos para su aprendizaje», en su
revisión de 2025. Sus tablas están en :mod:`nucleo.braille_contraido_tablas`,
generadas del documento y no tecleadas.

**Por qué esto no se podía hacer a medias, y qué se hizo al respecto.** La norma
dice, sobre saltarse un paso del proceso: «la transcripción resultante no sería
válida; no se trata de elegir entre dos abreviaturas alternativas, sino de
hacerlo correctamente». Y un texto contraído a medias no lo distingue de uno
correcto quien lo lee con los dedos. Por eso, en lugar de escribir lo que
pareciera razonable, se implementa **el proceso que el documento especifica**, en
su orden, y se comprueba contra **los ejemplos resueltos del propio documento**:
ciento veintitrés palabras con su transcripción, extraídas del PDF y guardadas en
``pruebas/datos/contraido_ejemplos.json``.

El proceso, palabra por palabra y en este orden:

1. Si la palabra está en la lista de abreviadas —o es una variante de género o
   número de una de ellas—, se usa esa y se pasa a la siguiente.
2. Si no, se mira si empieza por uno de los diez **principios**.
3. Después, si acaba en uno de los dieciocho **finales**.
4. Después, si lo que queda contiene una de las cuatro **secuencias**.
5. Y por último, las **contracciones**: pares de letras que se escriben con una
   sola celda.

El orden no es decorativo. «importante» está en la lista y baja de diez celdas a
tres; saltándose el primer paso y aplicando los demás saldría de ocho, y esa
transcripción **no sería válida**.
"""

from __future__ import annotations

import re

from . import braille_contraido_tablas as tablas
from .idioma import _
from .registro import obtener_registro

log = obtener_registro(__name__)

#: Vocales, con y sin tilde. Hacen falta para dos reglas distintas: un principio
#: no puede ir delante de una vocal, y una secuencia mira si lo que tiene al
#: lado es consonante.
VOCALES = frozenset("aeiouáéíóúü")

#: Vocales **sin** tilde. Una contracción que lleva vocal solo vale si esa vocal
#: es átona: «al» sirve en «alabar» y no en «álamo», donde la a lleva el acento.
#: Como aquí se compara letra a letra y las tablas están escritas sin tildes,
#: la regla se cumple sola: «á» no encaja con «a».
VOCALES_LLANAS = frozenset("aeiou")

#: Contracciones que no se usan al final de una palabra. «ab» comparte celda con
#: la coma, y «baobab» acabado en «ab» se leería «baobab,».
NO_AL_FINAL = frozenset(("ab",))

#: Lo que cuenta como una palabra al recorrer un texto.
_PALABRA = re.compile(r"[^\W\d_]+", re.UNICODE)


def _celdas_de_letras(texto: str) -> list[int]:
    """Las letras, una celda cada una, sin abreviar nada."""
    salida = []
    for letra in texto:
        celda = tablas.LETRAS.get(letra)
        if celda is None:
            return []
        salida.append(celda)
    return salida


def _sin_tildes(palabra: str) -> str:
    """La palabra sin acentos, solo para comparar unas con otras."""
    return palabra.translate(_LLANAS)


_LLANAS = str.maketrans("áéíóú", "aeiou")


def _marca(texto: str) -> list[int]:
    """Escribe una marca de plural o de género.

    Las de dos letras —«as», «os», «es»— tienen signo propio de una celda; la
    ese suelta no lo tiene y va como letra. De ahí que «mimbres» acabe en una
    ese y «asientos», en el signo de «-os».
    """
    propia = tablas.GENERO_Y_NUMERO.get(texto)
    if propia:
        return list(propia)
    return [tablas.LETRAS[letra] for letra in texto]


def _encaja_con_la_base(trozo: str, base: str) -> bool:
    """Dice si lo que queda delante del final es la palabra de la lista.

    Se admite que sobre o falte **una sola letra**: la vocal de enlace entre la
    palabra y el final —«anterior» más «-dad» se escribe «anterioridad»— y la
    vocal final que la variante pierde. Con más margen, «ocasionalmente» pasaría
    por «ocasión» más «-mente» y se perdería la ele por el camino.
    """
    if trozo in (base, base[:-1]):
        return True
    for vocal in VOCALES_LLANAS:
        if trozo in (base + vocal, base[:-1] + vocal):
            return True
    return False


def _es_forma_verbal(base: str) -> bool:
    """Dice si una palabra de la lista es una forma de verbo.

    Se deduce de sus propias variantes: si alguna acaba en ene, es una tercera
    persona del plural, y eso solo lo hace un verbo. «estaba» tiene «estaban»;
    «breve» no tiene nada parecido.
    """
    if base in _VERBALES_CACHE:
        return _VERBALES_CACHE[base]
    llana = _sin_tildes(base)
    verbal = any(_sin_tildes(variante) == llana + "n"
                 for variante, suya in tablas.VARIANTES.items() if suya == base)
    _VERBALES_CACHE[base] = verbal
    return verbal


_VERBALES_CACHE: dict[str, bool] = {}


def _derivada(palabra: str):
    """Si la palabra es variante de una de la lista, cómo se escribe.

    La norma **enumera** las variantes aceptadas de cada palabra en vez de
    dejarlas a una regla, porque la derivación no siempre es mecánica. Aquí se
    usa esa lista para saber *cuáles* son variantes, y las reglas documentadas
    para saber *cómo* se escribe cada una:

    - **Marca de género o número** (``-a``, ``-as``, ``-o``, ``-os``, ``-es``):
      se añade al signo abreviado y **sustituye** a la terminación de la palabra
      escrita. De «este» sale «estas», no «estes».
    - **Terminación de verbo** (``-s``, ``-n``): se añade como letra suelta.
      «estaba» da «estabas» y «estaban».
    - **Un final de los de la tabla**: «anterior» más «-dad» da «anterioridad»,
      con la vocal de enlace absorbida.

    Devuelve ``None`` cuando la palabra es variante pero su derivación no es
    ninguna de esas tres: entonces no se contrae, porque escribirla como se nos
    ocurra sería inventarse una abreviatura que la norma no reconoce.
    """
    base = tablas.VARIANTES.get(palabra)
    if base is None or base not in tablas.PALABRAS:
        return None
    signo = list(tablas.PALABRAS[base])
    llana_base = _sin_tildes(base)
    llana = _sin_tildes(palabra)

    # 1. Terminación de verbo, **solo si la base es una forma verbal**. Las dos
    #    reglas encajan en «estabas» —la de género daría «estab» más «as»— y no
    #    hay forma de distinguir un verbo de un adjetivo mirando la palabra. Lo
    #    que sí lo dice es la propia lista de variantes: si entre las de esa
    #    palabra hay alguna acabada en ene, es un verbo, porque el plural de un
    #    nombre no acaba nunca así.
    if _es_forma_verbal(base):
        for marca in tablas.VERBALES:
            if llana == llana_base + marca:
                return signo + [tablas.LETRAS[marca]]

    # 2. Género y número.
    for marca in ("es", "as", "os", "a", "o"):
        if not llana.endswith(marca):
            continue
        tronco = llana[:-len(marca)]
        if tronco in (llana_base, llana_base[:-1]):
            return signo + list(tablas.GENERO_Y_NUMERO[marca])

    # 3. Uno o varios finales de la tabla. La vocal de enlace entre la palabra
    #    y el final se absorbe: de «anterior» sale «anterioridad» con el signo
    #    de la palabra y el del final «-dad», sin la i de por medio.
    #
    #    La marca de plural se escribe **con el signo de género**, no con la
    #    letra que le tocaría al final por su cuenta: esto sigue siendo la
    #    variante de una palabra de la lista, y ahí manda la regla de la lista.
    cola: list[int] = []
    trozo = llana
    for _vuelta in range(2):
        final, marca = _final_de(trozo)
        if not final:
            break
        if marca:
            cola = list(tablas.GENERO_Y_NUMERO.get(marca)
                        or tablas.GENERO_Y_NUMERO["es"]) + cola
        cola = list(tablas.FINALES[final]) + cola
        trozo = trozo[:len(trozo) - _cuanto_ocupa(trozo, final, marca)]
        if _encaja_con_la_base(trozo, llana_base):
            return signo + cola

    # 4. La palabra derivada añadiendo letras: «persona» da «personal».
    #    Cuando la base acaba en consonante, la vocal de enlace se pierde:
    #    «ocasión» da «ocasional», escrito con el signo de la palabra y una ele.
    if llana.startswith(llana_base) and len(llana) > len(llana_base):
        extra = llana[len(llana_base):]
        if llana_base[-1:] not in VOCALES_LLANAS and extra[:1] in VOCALES_LLANAS:
            extra = extra[1:]
        if not extra:
            return signo
        # Lo añadido pasa por los mismos pasos que una palabra cualquiera: sus
        # finales primero y sus contracciones después. Sin esto, «ocasional»
        # más «-mente» acabaría escribiendo la palabra «mente» letra a letra.
        rabo: list[int] = []
        for _vuelta in range(2):
            final, marca = _final_de(extra)
            if not final:
                break
            rabo = list(tablas.FINALES[final]) + _marca(marca) + rabo
            extra = extra[:len(extra) - _cuanto_ocupa(extra, final, marca)]
        medio = _contraer(extra, False, not rabo) if extra else []
        if extra and not medio:
            return None
        return signo + medio + rabo
    return None


def _principios_de(palabra: str):
    """Los principios encadenados con los que empieza la palabra.

    Devuelve ``(lista de principios, lo que queda)``. Hay tres reglas y las tres
    salen de los ejemplos del documento:

    - **Se encadenan**: «sobreinterpretar» son tres seguidos —«sobre», «inter»
      y «pre»— más «t» y el final «-ar».
    - **Solo el último tiene que preceder a una consonante.** Entre dos
      principios no hay confusión posible, así que «re-» vale delante de la «i»
      de «reinterpretación» aunque no valdría delante de la de «reactivo».
    - **Un principio tiene que preceder a algo.** En «recompre», el «pre» final
      no es un principio: no le sigue nada, así que ahí se escribe con la
      contracción «pr» y la letra «e».
    """
    usados: list[str] = []
    resto = palabra
    while True:
        candidato = ""
        for principio in tablas.PRINCIPIOS:
            # Detrás del principio tienen que quedar **al menos dos letras**.
            # Con una sola no compensa: la norma escribe «compren» como com-
            # más las contracciones «pr» y «en», no como com- más pre- más
            # una ene; y «entren», como en-tr-en y no como entre- más ene.
            if resto.startswith(principio) and len(principio) > len(candidato) \
                    and len(resto) >= len(principio) + 2:
                candidato = principio
        if not candidato:
            break
        usados.append(candidato)
        resto = resto[len(candidato):]
    # Y ahora, hacia atrás: el último no puede quedar delante de una vocal.
    while usados and resto[:1] in VOCALES:
        resto = usados.pop() + resto
    return usados, resto


def _final_de(palabra: str):
    """El final de la palabra, si lo tiene. Devuelve ``(final, marca de plural)``.

    La marca de plural **se escribe con sus letras**, no con la marca de género
    de las palabras de la lista: «mimbre» hace «mimbres» con el signo de «-bre»
    y una ese, no con el signo de «-es». Cuál le toca a cada final está en su
    propia tabla, porque no todos hacen el plural igual: «-ión» lo hace en
    «-iones».
    """
    llana = _sin_tildes(palabra)
    mejor = ("", "")

    def mejor_que(final, marca):
        return len(final) + len(marca) > len(mejor[0]) + len(mejor[1])

    for final in tablas.FINALES:
        # Se compara sin tildes: en la tabla el final es «-ión» y en la palabra
        # está escrito «-ion» en cuanto lleva algo detrás («ocasiones»).
        llano = _sin_tildes(final)
        if llana.endswith(llano) and len(llana) > len(llano) \
                and mejor_que(final, ""):
            mejor = (final, "")
        marca = tablas.PLURAL_FINALES.get(final, "s")
        # La marca se pega detrás del final o **sustituye a su vocal**, según
        # cuál sea: «-bre» hace «-bres» y «-iento» hace «-ientos», que es
        # «-ient» más «-os». Se prueban las dos formas.
        for cuerpo in (llano, llano[:-1] if llano[-1:] in VOCALES_LLANAS else ""):
            if not cuerpo:
                continue
            completo = cuerpo + marca
            if llana.endswith(completo) and len(llana) > len(completo) \
                    and mejor_que(final, marca):
                mejor = (final, marca)
    return mejor


def _cuanto_ocupa(palabra: str, final: str, marca: str) -> int:
    """Cuántas letras de la palabra ocupan ese final y su marca."""
    llano = _sin_tildes(final)
    llana = _sin_tildes(palabra)
    if marca and llana.endswith(llano[:-1] + marca) \
            and not llana.endswith(llano + marca):
        return len(llano) - 1 + len(marca)
    return len(llano) + len(marca)


def _es_consonante(letra: str) -> bool:
    return letra.isalpha() and letra not in VOCALES


def _cabe_la_secuencia(palabra: str, inicio: int, secuencia: str,
                       al_principio: bool, hasta_el_final: bool) -> bool:
    """Dice si una secuencia se puede usar en ese sitio de la palabra.

    Cada una tiene sus límites y no son adorno: «ante» y «que» no valen al
    final porque ahí mandan los finales «-te» y «-que», que es la regla de
    prioridad del documento; y «esta» pide consonante al lado para no
    confundirse con la palabra «este», que se escribe con la misma celda.
    """
    fin = inicio + len(secuencia)
    posicion = tablas.POSICION_SECUENCIA.get(secuencia, "cualquiera")
    if posicion == "no-final" and hasta_el_final and fin == len(palabra):
        return False
    if secuencia != "esta":
        return True
    # Cuando detrás de este trozo va un final --que empieza siempre por
    # consonante--, la secuencia sigue teniendo su consonante al lado aunque
    # aquí se acabe el trozo. Es lo que hace que «condestable» sea
    # «con-d-esta-ble» y no «con-d-es-t-a-ble».
    consonante_detras = (_es_consonante(palabra[fin]) if fin < len(palabra)
                         else not hasta_el_final)
    if inicio == 0 and al_principio:
        return consonante_detras
    if fin == len(palabra) and hasta_el_final:
        return inicio > 0 and _es_consonante(palabra[inicio - 1])
    return (inicio > 0 and _es_consonante(palabra[inicio - 1])
            and consonante_detras)


def _contraer(trozo: str, al_principio: bool, hasta_el_final: bool) -> list[int]:  # noqa: C901
    """Los pasos 4 y 5: secuencias y contracciones sobre lo que queda.

    Se recorre de izquierda a derecha probando primero las secuencias —que son
    más largas— y después las contracciones, con **la regla de las contiguas**:
    cuando una letra podría contraerse con la de delante y con la de detrás,
    gana la de detrás. Por eso «labrar» es ``l-a-br-ar`` y no ``l-ab-r-ar``.
    """
    salida: list[int] = []
    posicion = 0
    while posicion < len(trozo):
        elegida = ""
        for secuencia in tablas.SECUENCIAS:
            if not trozo.startswith(secuencia, posicion):
                continue
            if not _cabe_la_secuencia(trozo, posicion, secuencia,
                                      al_principio, hasta_el_final):
                continue
            if len(secuencia) > len(elegida):
                elegida = secuencia
        if elegida:
            salida.extend(tablas.SECUENCIAS[elegida])
            posicion += len(elegida)
            continue

        contigua = None
        for tres, _pierde, gana in tablas.CONTIGUAS:
            if trozo.startswith(tres, posicion):
                contigua = (tres, gana)
                break
        if contigua is not None:
            tres, gana = contigua
            letra = tablas.LETRAS.get(trozo[posicion])
            if letra is not None:
                salida.append(letra)
                salida.extend(tablas.CONTRACCIONES[gana])
                posicion += len(tres)
                continue

        contraccion = ""
        for candidata in tablas.CONTRACCIONES:
            if not trozo.startswith(candidata, posicion):
                continue
            if candidata in NO_AL_FINAL and hasta_el_final \
                    and posicion + len(candidata) == len(trozo):
                continue
            if len(candidata) > len(contraccion):
                contraccion = candidata
        if contraccion:
            salida.extend(tablas.CONTRACCIONES[contraccion])
            posicion += len(contraccion)
            continue

        letra = tablas.LETRAS.get(trozo[posicion])
        if letra is None:
            return []
        salida.append(letra)
        posicion += 1
    return salida


def celdas_de_palabra(palabra: str) -> list[int]:
    """Transcribe una palabra a braille contraído.

    Devuelve la lista vacía cuando la palabra lleva algo que estas tablas no
    cubren, o cuando es una variante cuya derivación no está documentada: en
    los dos casos hay que escribirla sin contraer, porque una abreviatura
    inventada no la distingue de una buena quien la lee.
    """
    if not palabra:
        return []
    prefijo: list[int] = []
    if palabra[:1].isupper():
        prefijo.append(tablas.MAYUSCULA)
    llana = palabra.lower()

    # --- Paso 1: la lista de palabras abreviadas y sus variantes ----------
    directa = tablas.PALABRAS.get(llana)
    if directa is not None:
        return prefijo + list(directa)
    if llana in tablas.VARIANTES:
        derivada = _derivada(llana)
        return prefijo + derivada if derivada else []

    # Una palabra de la lista con un final detrás sigue siendo una derivada,
    # aunque la lista de variantes no la recoja: «contrario» más «-mente» da
    # «contrariamente». Es el mismo paso 1, y por eso va aquí y no más abajo.
    con_final = _lista_con_final(llana)
    if con_final is not None:
        return prefijo + con_final

    # --- Paso 2: los principios, encadenados -------------------------------
    salida = list(prefijo)
    principios, resto = _principios_de(llana)
    for principio in principios:
        salida.extend(tablas.PRINCIPIOS[principio])

    # --- Paso 3: los finales, que también se encadenan ---------------------
    # «tristemente» son dos seguidos: «-te» y «-mente». Se quitan de derecha a
    # izquierda, y con un tope para que una palabra rara no dé vueltas.
    cola: list[int] = []
    hubo_final = False
    for _vuelta in range(3):
        final, marca = _final_de(resto)
        if not final:
            break
        hubo_final = True
        cola = list(tablas.FINALES[final]) + _marca(marca) + cola
        resto = resto[:len(resto) - _cuanto_ocupa(resto, final, marca)]

    # --- Pasos 4 y 5: lo que queda ----------------------------------------
    medio = _contraer(resto, not principios, not hubo_final)
    if resto and not medio:
        return []
    return salida + medio + cola


def _lista_con_final(palabra: str):
    """Si la palabra es una de la lista más uno o dos finales, cómo se escribe.

    La vocal de enlace entre la palabra y el final se absorbe: «contraria» más
    «-mente» se escribe con el signo de «contrario» y el de «-mente», sin nada
    en medio.
    """
    cola: list[int] = []
    trozo = palabra
    for _vuelta in range(2):
        final, marca = _final_de(trozo)
        if not final:
            return None
        cola = list(tablas.FINALES[final]) + _marca(marca) + cola
        trozo = trozo[:len(trozo) - _cuanto_ocupa(trozo, final, marca)]
        # **Con dos condiciones**, y las dos hacen falta. La palabra que queda
        # tiene que ser larga --si no, «comandos» acabaría siendo «como» más
        # «-ando»-- y la candidata no puede ser más corta que ella, o
        # «tembleque» acabaría siendo «te» más «-ble» y «-que».
        if len(trozo) < 5:
            continue
        candidatas = [trozo]
        for vocal in "aeiou":
            candidatas.append(trozo + vocal)
            candidatas.append(trozo[:-1] + vocal)
        for candidata in candidatas:
            if len(candidata) >= len(trozo) and candidata in tablas.PALABRAS:
                return list(tablas.PALABRAS[candidata]) + cola
    return None


def celdas(texto: str) -> list[int]:
    """Transcribe un texto entero, palabra a palabra.

    Lo que no es una palabra —la puntuación, los espacios, las cifras— se deja
    como está: las contracciones son cosa de las palabras.
    """
    salida: list[int] = []
    posicion = 0
    for encaje in _PALABRA.finditer(texto or ""):
        salida.extend(_suelto(texto[posicion:encaje.start()]))
        palabra = encaje.group()
        celdas_palabra = celdas_de_palabra(palabra)
        if not celdas_palabra:
            celdas_palabra = _celdas_de_letras(palabra.lower())
            if palabra[:1].isupper():
                celdas_palabra = [tablas.MAYUSCULA] + celdas_palabra
        salida.extend(celdas_palabra)
        posicion = encaje.end()
    salida.extend(_suelto(texto[posicion:] if texto else ""))
    return salida


def _suelto(trozo: str) -> list[int]:
    """Lo que hay entre palabras: espacios, puntuación y cifras."""
    from .braille import a_celdas

    return a_celdas(trozo) if trozo else []


def a_brf(celdas_del_texto) -> str:
    """Pasa las celdas a los caracteres con los que se escribe un archivo BRF."""
    from .braille import ASCII_BRAILLE

    return "".join(ASCII_BRAILLE[celda] if 0 <= celda < len(ASCII_BRAILLE) else " "
                   for celda in celdas_del_texto or ())


def descripcion() -> str:
    """Frase que explica qué se obtiene, para la ventana de opciones."""
    return _("El braille contraído usa las abreviaturas del documento B 16-1 de "
             "la Comisión Braille Española y ocupa alrededor de un tercio menos. "
             "Es lo que lee con soltura quien aprendió braille de pequeño; quien "
             "no lo haya estudiado no lo entenderá.")
