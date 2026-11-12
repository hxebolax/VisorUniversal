# -*- coding: utf-8 -*-
"""Buscar por lo que significa, no solo por cómo se escribe.

Buscar en la biblioteca funciona bien cuando uno recuerda **la palabra exacta**
del libro. Estudiando, casi nunca es así: los apuntes de clase dicen
«amortización» y el manual dice «depreciación», el profesor dice «flujo de caja»
y el libro dice «tesorería». Buscando por letras, esas búsquedas no devuelven
nada, y lo que no aparece se da por que no está.

Aquí se resuelve con lo que ya hay en el equipo: **los propios libros**. Dos
palabras que significan casi lo mismo aparecen en los mismos sitios —los mismos
capítulos, los mismos párrafos—, y eso se puede medir. Con veinte libros de
contabilidad delante, «amortización» y «depreciación» comparten cientos de
pasajes; «amortización» y «sonata» no comparten ninguno.

**Por qué se hace así y no con inteligencia artificial.** Un modelo de lenguaje
sabría que las dos palabras se parecen sin haber leído estos libros, pero
costaría cientos de megabytes, o una cuenta y una conexión, y devolvería
relaciones de un castellano general que no tienen por qué ser las de esta
asignatura. Midiendo sobre la biblioteca de cada uno, lo que sale son **las
relaciones de sus libros**: en una biblioteca de derecho, «prescripción» sale
junto a «caducidad»; en una de medicina, junto a «receta».

**Lo que hace que no devuelva ruido**, que es el único riesgo de esto:

- Se compara por **raíces** (:mod:`nucleo.raices`), no por palabras, así que
  «amortizar» y «amortizaciones» son lo mismo desde el principio.
- Las palabras que salen en todas partes no relacionan nada: si una raíz aparece
  en más de un tercio de los pasajes, se descarta. Así no hace falta una lista
  de palabras vacías escrita a mano, ni que esté bien en cinco idiomas.
- Se exige un **mínimo de pasajes compartidos** además de la proporción. Sin él,
  dos palabras rarísimas que coinciden una vez saldrían con la puntuación más
  alta de todas, que es el error clásico de esta medida.
- Y sobre todo: **lo relacionado se ofrece, no se impone**. La búsqueda sigue
  encontrando lo que se ha escrito; las palabras emparentadas se enseñan aparte,
  diciendo cuáles son, para que quien busca decida. Una búsqueda que devuelve
  cosas que uno no ha pedido, sin avisar, es peor que una que no encuentra.
"""

from __future__ import annotations

import math
import pickle
from array import array
from pathlib import Path

from . import raices, rutas
from .idioma import _
from .registro import obtener_registro

log = obtener_registro(__name__)

#: Caracteres de cada pasaje. Un pasaje es la unidad en la que se mide «salen
#: juntas»: más corto y dos palabras del mismo párrafo dejarían de verse; más
#: largo y acabarían pareciendo parientes dos palabras del mismo capítulo que no
#: tienen nada que ver.
PASAJE = 1200

#: Raíces distintas que se guardan como mucho. Es el tope de memoria: por
#: encima, la lista deja de tener palabras que alguien vaya a buscar.
MAXIMO_VOCABULARIO = 8000

#: En cuántos pasajes tiene que salir una raíz para contar. Con menos, no hay
#: forma de distinguir una relación de una casualidad.
MINIMOS_PASAJES = 3

#: Por encima de esta proporción de pasajes, una raíz es de relleno: sale en
#: todas partes y por tanto no relaciona nada con nada.
DEMASIADO_COMUN = 0.34

#: Pasajes que dos raíces tienen que compartir como mínimo para considerarlas
#: emparentadas.
MINIMOS_COMPARTIDOS = 4

#: Cuántas veces más de lo que saldría por puro azar tienen que coincidir dos
#: raíces. Es lo que separa una relación de verdad de un encuentro casual:
#: «aquello» y «mientras» salen junto a todo, así que coinciden mucho con
#: cualquier palabra **sin significar nada**; lo que las delata no es que
#: coincidan poco, sino que coinciden justo lo que se esperaría de dos palabras
#: que no tuvieran ninguna relación.
MINIMO_EXCESO = 1.3

#: Pasajes que se indexan como mucho. Una biblioteca de trescientos libros son
#: cuarenta mil pasajes, y guardarlos todos costaría más memoria de la que se
#: puede pedir en un programa portátil. Con este tope se indexa lo que quepa y
#: se dice cuánto ha entrado.
MAXIMOS_PASAJES = 40000

#: Longitud mínima de una palabra para entrar. Las de tres letras o menos son
#: artículos, preposiciones y siglas sueltas.
MINIMA_PALABRA = 4

#: Versión del formato guardado. Si cambia cómo se construye el índice, esto
#: sube y el índice viejo se descarta en lugar de leerse mal.
VERSION = 1


class Indice:
    """Qué raíces salen en qué pasajes, y con eso, cuáles se parecen."""

    __slots__ = ("raiz_a_numero", "escritura", "pasajes_de", "raices_de",
                 "total_pasajes", "libros")

    def __init__(self) -> None:
        #: Raíz -> número interno con el que se guarda.
        self.raiz_a_numero: dict[str, int] = {}
        #: Número -> la palabra entera más corta con la que apareció. Es lo que
        #: se le enseña al usuario: nadie busca «amortiz», busca «amortización».
        self.escritura: list[str] = []
        #: Número de raíz -> pasajes en los que sale.
        self.pasajes_de: list[array] = []
        #: Pasaje -> raíces que salen en él.
        self.raices_de: list[array] = []
        self.total_pasajes = 0
        #: Rutas de los libros con los que se construyó, para saber si hay que
        #: rehacerlo.
        self.libros: list[str] = []

    def __len__(self) -> int:
        return len(self.raiz_a_numero)

    def conoce(self, palabra: str) -> bool:
        """Dice si esa palabra entra en el índice."""
        return raices.raiz(palabra) in self.raiz_a_numero

    def relacionadas(self, palabra: str, cuantas: int = 6) -> list[tuple[str, float]]:
        """Las palabras que salen en los mismos sitios que esta.

        Devuelve pares ``(palabra, parecido)`` de más a menos parecido. El
        parecido va de 0 a 1 y es la proporción de pasajes compartidos,
        ponderada para que no ganen las palabras que salen en todas partes.
        """
        numero = self.raiz_a_numero.get(raices.raiz(palabra))
        if numero is None:
            return []
        mios = self.pasajes_de[numero]
        if len(mios) < MINIMOS_PASAJES:
            return []

        compartidos: dict[int, int] = {}
        for pasaje in mios:
            for otro in self.raices_de[pasaje]:
                if otro != numero:
                    compartidos[otro] = compartidos.get(otro, 0) + 1

        candidatos = []
        for otro, juntos in compartidos.items():
            if juntos < MINIMOS_COMPARTIDOS:
                continue
            suyos = len(self.pasajes_de[otro])
            # Cuántos pasajes compartirían dos palabras que no tuvieran nada
            # que ver, solo por lo frecuentes que son cada una.
            por_azar = len(mios) * suyos / self.total_pasajes
            if por_azar > 0 and juntos < por_azar * MINIMO_EXCESO:
                continue
            # Coseno sobre presencias: los pasajes compartidos, divididos por la
            # raíz de lo que sale cada una por su cuenta. Es lo que impide que
            # una palabra frecuentísima parezca pariente de todas.
            parecido = juntos / math.sqrt(len(mios) * suyos)
            candidatos.append((parecido, otro))
        candidatos.sort(reverse=True)
        return [(self.escritura[otro], round(parecido, 3))
                for parecido, otro in candidatos[:cuantas]]

    def ampliar(self, texto: str, cuantas: int = 4) -> list[str]:
        """Las palabras con las que conviene ampliar una búsqueda.

        Se le pasa lo que el usuario ha escrito y devuelve palabras
        emparentadas que **no** están ya en lo escrito. Si lo buscado son varias
        palabras, se amplía la más significativa, que es la que menos veces sale
        en la biblioteca: ampliar «de» no le sirve a nadie.
        """
        candidatas = [p for p in raices.palabras(texto) if len(p) >= MINIMA_PALABRA]
        if not candidatas:
            return []
        conocidas = [(len(self.pasajes_de[self.raiz_a_numero[raices.raiz(p)]]), p)
                     for p in candidatas if self.conoce(p)]
        if not conocidas:
            return []
        conocidas.sort()
        ya_puestas = {raices.raiz(p) for p in candidatas}
        salida = []
        for palabra, _parecido in self.relacionadas(conocidas[0][1], cuantas * 3):
            if raices.raiz(palabra) in ya_puestas:
                continue
            salida.append(palabra)
            if len(salida) >= cuantas:
                break
        return salida


def _pasajes_de_texto(texto: str):
    """Parte un texto en pasajes del tamaño de un par de párrafos.

    Se corta por saltos de línea y no a ciegas cada tantos caracteres: partir
    una frase en dos separaría palabras que estaban juntas, que es justo lo que
    aquí se está midiendo.

    Pero **una línea larguísima también hay que partirla**. Hay documentos
    —una página web mal montada, un texto plano sin párrafos— cuyo texto entero
    es una sola línea; sin este corte, ese libro sería un único pasaje en el que
    todas sus palabras aparecen juntas, y entonces todas parecerían parientes de
    todas. Cuando toca partir por la fuerza se busca el espacio más cercano,
    para no cortar una palabra por la mitad.
    """
    actual: list[str] = []
    cuanto = 0
    for linea in (texto or "").split("\n"):
        while len(linea) > PASAJE * 2:
            corte = linea.rfind(" ", 0, PASAJE)
            if corte <= 0:
                corte = PASAJE
            yield "\n".join(actual + [linea[:corte]])
            actual, cuanto = [], 0
            linea = linea[corte:].lstrip()
        actual.append(linea)
        cuanto += len(linea) + 1
        if cuanto >= PASAJE:
            yield "\n".join(actual)
            actual = []
            cuanto = 0
    if actual:
        yield "\n".join(actual)


def _raices_del_pasaje(pasaje: str, cortas=None):
    """Las raíces distintas que hay en un pasaje, sin repetir.

    De paso se apunta, para cada raíz, la palabra entera más corta con la que
    ha aparecido: es la que después se le enseña al usuario, porque nadie busca
    «amortiz», busca «amortización».
    """
    presentes = set()
    for palabra in raices.palabras(pasaje):
        if len(palabra) < MINIMA_PALABRA or palabra.isdigit():
            continue
        clave = raices.raiz(palabra)
        if len(clave) < 3:
            continue
        presentes.add(clave)
        if cortas is not None:
            anterior = cortas.get(clave)
            if anterior is None or len(palabra) < len(anterior):
                cortas[clave] = palabra
    return presentes


def construir(documentos, progreso=None, cancelado=None) -> Indice:
    """Monta el índice a partir de una lista de ``(ruta, texto)``.

    Se recorre el texto **dos veces**: la primera cuenta en cuántos pasajes
    sale cada raíz, y la segunda guarda solo las que merecen la pena. Recorrerlo
    una sola vez obligaría a tener a la vez en memoria el troceado de toda la
    biblioteca —trescientos libros son cuarenta mil pasajes— para tirar después
    el noventa por ciento. Volver a partir el texto cuesta unos segundos; tener
    esa memoria ocupada puede costar el programa entero.
    """
    indice = Indice()
    cuenta: dict[str, int] = {}
    cortas: dict[str, str] = {}

    total = len(documentos)
    cuantos_pasajes = 0
    for numero, (ruta, texto) in enumerate(documentos):
        if cancelado is not None and cancelado():
            break
        if progreso is not None:
            progreso(numero, total * 2, _("Leyendo: %s") % Path(ruta).name)
        indice.libros.append(str(ruta))
        for pasaje in _pasajes_de_texto(texto):
            if cuantos_pasajes >= MAXIMOS_PASAJES:
                break
            for clave in _raices_del_pasaje(pasaje, cortas):
                cuenta[clave] = cuenta.get(clave, 0) + 1
            cuantos_pasajes += 1

    if not cuantos_pasajes:
        return indice
    tope = cuantos_pasajes * DEMASIADO_COMUN
    utiles = [(numero, clave) for clave, numero in cuenta.items()
              if MINIMOS_PASAJES <= numero <= tope]
    utiles.sort(reverse=True)
    for _cuantos, clave in utiles[:MAXIMO_VOCABULARIO]:
        indice.raiz_a_numero[clave] = len(indice.escritura)
        indice.escritura.append(cortas.get(clave, clave))
    indice.pasajes_de = [array("i") for _ in indice.escritura]
    del cuenta, cortas, utiles

    pasaje_numero = 0
    for numero, (ruta, texto) in enumerate(documentos):
        if cancelado is not None and cancelado():
            break
        if progreso is not None:
            progreso(total + numero, total * 2, _("Relacionando las palabras..."))
        for pasaje in _pasajes_de_texto(texto):
            if pasaje_numero >= MAXIMOS_PASAJES:
                break
            aqui = array("i")
            for clave in sorted(_raices_del_pasaje(pasaje)):
                donde = indice.raiz_a_numero.get(clave)
                if donde is not None:
                    aqui.append(donde)
                    indice.pasajes_de[donde].append(pasaje_numero)
            indice.raices_de.append(aqui)
            pasaje_numero += 1
    indice.total_pasajes = pasaje_numero
    if progreso is not None:
        progreso(total * 2, total * 2, _("Índice preparado."))
    log.info("Índice de significados: %d raíces en %d pasajes de %d libros",
             len(indice), indice.total_pasajes, len(indice.libros))
    return indice


def ruta_guardado() -> Path:
    """Dónde se guarda el índice: junto a la caché de documentos."""
    return rutas.subcarpeta("cache") / "significados.idx"


def guardar(indice: Indice, destino=None) -> None:
    """Deja el índice en el disco para no volver a construirlo cada vez."""
    ruta = Path(destino) if destino is not None else ruta_guardado()
    contenido = {
        "version": VERSION,
        "raiz_a_numero": indice.raiz_a_numero,
        "escritura": indice.escritura,
        "pasajes_de": [p.tobytes() for p in indice.pasajes_de],
        "raices_de": [p.tobytes() for p in indice.raices_de],
        "total_pasajes": indice.total_pasajes,
        "libros": indice.libros,
    }
    temporal = ruta.with_suffix(ruta.suffix + ".tmp")
    with open(temporal, "wb") as archivo:
        pickle.dump(contenido, archivo, protocol=pickle.HIGHEST_PROTOCOL)
    temporal.replace(ruta)


def cargar(origen=None) -> Indice | None:
    """Trae el índice guardado, o ``None`` si no hay o no sirve."""
    ruta = Path(origen) if origen is not None else ruta_guardado()
    if not ruta.is_file():
        return None
    try:
        with open(ruta, "rb") as archivo:
            contenido = pickle.load(archivo)
    except Exception as error:
        log.info("El índice de significados no se puede leer: %s", error)
        return None
    if contenido.get("version") != VERSION:
        return None
    indice = Indice()
    indice.raiz_a_numero = contenido["raiz_a_numero"]
    indice.escritura = contenido["escritura"]
    indice.total_pasajes = contenido["total_pasajes"]
    indice.libros = contenido["libros"]
    for crudo in contenido["pasajes_de"]:
        trozo = array("i")
        trozo.frombytes(crudo)
        indice.pasajes_de.append(trozo)
    for crudo in contenido["raices_de"]:
        trozo = array("i")
        trozo.frombytes(crudo)
        indice.raices_de.append(trozo)
    return indice


def hace_falta_rehacer(indice: Indice | None, libros) -> bool:
    """Dice si el índice se ha quedado atrás respecto a la biblioteca.

    Se rehace cuando hay libros nuevos, no cuando falta alguno: quitar un libro
    de la lista no estropea las relaciones que ya se habían aprendido, y rehacer
    el índice entero por eso sería cobrarle al usuario un minuto por nada.
    """
    if indice is None or not indice.libros:
        return True
    conocidos = set(indice.libros)
    return any(str(ruta) not in conocidos for ruta in libros)
