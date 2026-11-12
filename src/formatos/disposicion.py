# -*- coding: utf-8 -*-
"""Análisis de la disposición de una página: en qué orden se lee lo que se ve.

Un OCR devuelve palabras con sus coordenadas.  Convertir eso en texto legible
parece trivial —ordenar por fila y luego por columna— y no lo es en cuanto la
página deja de ser un bloque corrido:

* Un **folleto** con una rejilla de tarjetas: leer por bandas horizontales
  mezcla los tres productos de cada fila, y sale «Sandía Melocotón Pitaya
  0,90 € 3,35 € 2,15 €».
* Un **periódico** a tres columnas: leer por filas salta de una columna a otra
  a media frase.
* Una **tabla**: hay que saber qué celda va con qué encabezado, o los números
  no significan nada.

Estos tres casos son justo los que peor lleva un lector de pantalla, porque
quien no ve la página no tiene forma de reconstruir mentalmente el orden.

Aquí se resuelven con el **corte recursivo en X e Y** (el clásico *XY-cut* del
análisis de documentos): se busca el hueco blanco más ancho que parta la
región, se corta por ahí, y se repite en cada mitad.  Cortar primero por un
hueco vertical da las columnas; por uno horizontal, las bandas.  La recursión
termina cuando ya no queda ningún hueco que valga, y el recorrido en ese orden
**es** el orden de lectura.

Encima de eso, una región cuyas líneas se alinean en columnas consistentes se
reconoce como tabla y se escribe como ``<table>``, que es lo que hace que un
lector de pantalla la pueda recorrer celda a celda.

El módulo no sabe de qué OCR vienen las palabras: recibe cajas con texto.
"""

from __future__ import annotations

from typing import NamedTuple

from nucleo.idioma import _
from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

#: Hueco mínimo, en múltiplos de la altura de línea, para partir una región.
#: Por debajo de esto, el «hueco» es el espacio normal entre palabras o entre
#: renglones y cortar por ahí trocearía un párrafo.
HUECO_VERTICAL = 1.2
HUECO_HORIZONTAL = 0.8

#: Cuántas partes como mucho se buscan en un corte.  Es un tope de seguridad
#: para páginas con mucho ruido.
CORTES_MAXIMOS = 40

#: Profundidad máxima de la recursión.
PROFUNDIDAD_MAXIMA = 12

#: Confianza por debajo de la cual se descarta una palabra.  Tesseract marca
#: con valores muy bajos los adornos que ha intentado leer como texto.
CONFIANZA_MINIMA = 30.0

#: Para dar una región por tabla: filas que tiene que haber como mínimo y en
#: qué proporción deben coincidir sus columnas.
FILAS_TABLA = 3
COINCIDENCIA_TABLA = 0.75


class Palabra(NamedTuple):
    """Una palabra reconocida, con dónde está en la página."""

    texto: str
    x: int
    y: int
    ancho: int
    alto: int
    confianza: float = 100.0

    @property
    def derecha(self) -> int:
        """Coordenada del borde derecho."""
        return self.x + self.ancho

    @property
    def abajo(self) -> int:
        """Coordenada del borde inferior."""
        return self.y + self.alto

    @property
    def centro_y(self) -> float:
        """Altura del centro de la palabra."""
        return self.y + self.alto / 2.0


class Linea:
    """Un renglón: las palabras que van seguidas a la misma altura."""

    __slots__ = ("palabras",)

    def __init__(self, palabras: list[Palabra]) -> None:
        self.palabras = sorted(palabras, key=lambda p: p.x)

    @property
    def texto(self) -> str:
        """Lo que dice el renglón."""
        return " ".join(palabra.texto for palabra in self.palabras).strip()

    @property
    def x(self) -> int:
        """Dónde empieza."""
        return min(palabra.x for palabra in self.palabras)

    @property
    def derecha(self) -> int:
        """Dónde acaba."""
        return max(palabra.derecha for palabra in self.palabras)

    @property
    def y(self) -> int:
        """Altura de su borde superior."""
        return min(palabra.y for palabra in self.palabras)

    @property
    def abajo(self) -> int:
        """Altura de su borde inferior."""
        return max(palabra.abajo for palabra in self.palabras)

    @property
    def alto(self) -> int:
        """Lo que mide de alto."""
        return max(1, self.abajo - self.y)

    def __repr__(self) -> str:
        return "<Linea %r>" % self.texto[:40]


def _altura_tipica(lineas: list[Linea]) -> float:
    """Altura de línea representativa de un conjunto.

    Se usa la mediana y no la media: un titular enorme o una errata de una sola
    letra desplazarían la media y con ella todos los umbrales.
    """
    if not lineas:
        return 10.0
    alturas = sorted(linea.alto for linea in lineas)
    return float(alturas[len(alturas) // 2]) or 10.0


# ---------------------------------------------------------------------------
# De palabras a líneas
# ---------------------------------------------------------------------------

def limpiar(palabras: list[Palabra], confianza: float = CONFIANZA_MINIMA,
            quitar_simbolos: bool = True) -> list[Palabra]:
    """Quita de la lista lo que no es texto de verdad.

    Un folleto está lleno de adornos —flechas, iconos, marcos, degradados— y el
    motor intenta leerlos igual, sacando renglones enteros con ``>``, ``_=`` o
    ``«``.  En un documento que se lee de oído eso no es un detalle estético:
    son líneas que hay que oír y descartar una a una.

    Se quita lo que **no tiene ninguna letra ni ningún número**, que es un
    criterio seguro —no se pierde nada que se pueda leer en voz alta— y se
    lleva por delante casi todo el ruido.

    :param confianza: Por debajo de esto se descarta la palabra.  Conviene no
                      subirlo mucho: en un folleto, los precios sobre fondo de
                      color salen con confianza baja y se perderían.
    :param quitar_simbolos: Si se descartan los adornos.
    """
    limpias = []
    for palabra in palabras:
        texto = palabra.texto.strip()
        if not texto or palabra.confianza < confianza or palabra.alto <= 0:
            continue
        if quitar_simbolos and not any(c.isalnum() for c in texto):
            continue
        limpias.append(palabra._replace(texto=texto))
    return limpias


def fusionar(principal: list[Palabra], secundaria: list[Palabra],
             holgura: float = 0.5) -> list[Palabra]:
    """Añade a un reconocimiento lo que solo vio el otro.

    Dos pasadas del mismo motor con la página preparada de forma distinta no
    fallan en los mismos sitios: una lee bien el texto negro sobre blanco y se
    come el precio que va sobre un círculo rojo, y la otra al revés.  Medido
    sobre un folleto real, cada pasada por separado sacaba 15 y 17 productos
    con su precio de 23, y **las dos juntas, 20**.

    La fusión es por sitio, no por texto: de la segunda pasada se añade solo lo
    que cae donde la primera no encontró nada.  Así no se duplica ni una
    palabra, que es lo que pasaría concatenando los dos textos, y no hay que
    decidir cuál de dos lecturas distintas de la misma palabra es la buena.

    :param principal: Reconocimiento que manda.
    :param secundaria: De donde se sacan los huecos.
    :param holgura: Cuánto se pueden solapar dos cajas sin darse por la misma,
                    en fracción del área de la palabra nueva.
    """
    if not secundaria:
        return principal
    if not principal:
        return secundaria
    añadidas = 0
    resultado = list(principal)
    for palabra in secundaria:
        if not _hay_hueco(palabra, principal, holgura):
            continue
        resultado.append(palabra)
        añadidas += 1
    log.debug("Fusión de pasadas: %d palabras + %d que solo vio la segunda",
              len(principal), añadidas)
    return resultado


def _hay_hueco(palabra: Palabra, otras: list[Palabra], holgura: float) -> bool:
    """Si en el sitio de esa palabra no hay ya otra reconocida."""
    area = max(1, palabra.ancho * palabra.alto)
    for otra in otras:
        ancho = min(palabra.derecha, otra.derecha) - max(palabra.x, otra.x)
        alto = min(palabra.abajo, otra.abajo) - max(palabra.y, otra.y)
        if ancho > 0 and alto > 0 and (ancho * alto) > area * holgura:
            return False
    return True


def quitar_sueltas(palabras: list[Palabra], distancia: float = 2.0) -> list[Palabra]:
    """Quita las letras sueltas que no tienen nada alrededor.

    Un adorno leído como texto casi siempre sale así: una o dos letras solas en
    mitad de un espacio vacío, lejos de cualquier palabra de verdad.  El texto
    legítimo, en cambio, vive acompañado: una inicial, una preposición o una
    viñeta tienen siempre otra palabra al lado, en la misma línea.

    Se mira solo eso —si hay vecinos cerca— y no la confianza, porque el motor
    le pone confianza alta a muchos adornos: está seguro de haber visto una
    «A», y la ha visto, solo que era la punta de un icono.

    :param distancia: Cuánto se busca alrededor, en múltiplos de la altura de
                      la palabra.
    """
    if len(palabras) < 2:
        return palabras
    limpias = []
    for palabra in palabras:
        texto = palabra.texto
        if len(texto) > 2 or any(c.isdigit() for c in texto):
            limpias.append(palabra)
            continue
        radio = palabra.alto * distancia
        acompañada = False
        for otra in palabras:
            if otra is palabra:
                continue
            if (abs(otra.centro_y - palabra.centro_y) < palabra.alto
                    and (otra.x - palabra.derecha < radio)
                    and (palabra.x - otra.derecha < radio)):
                acompañada = True
                break
        if acompañada:
            limpias.append(palabra)
    quitadas = len(palabras) - len(limpias)
    if quitadas:
        log.debug("Descartadas %d letras sueltas sin nada alrededor", quitadas)
    return limpias


def montar_lineas(palabras: list[Palabra]) -> list[Linea]:
    """Agrupa las palabras en renglones por su altura.

    Dos palabras van en el mismo renglón si sus alturas se solapan más de la
    mitad.  Comparar el centro no basta: en una misma línea conviven mayúsculas
    grandes y minúsculas pequeñas, y sus centros no coinciden.
    """
    # No se filtra aquí por confianza: de eso se encarga :func:`limpiar`, con
    # el umbral que haya elegido el usuario.  Volver a filtrar con la constante
    # anularía su ajuste sin que nada lo dijera.
    limpias = [p for p in palabras if p.texto.strip() and p.alto > 0]
    if not limpias:
        return []
    limpias.sort(key=lambda p: (p.y, p.x))
    lineas: list[list[Palabra]] = []
    for palabra in limpias:
        for grupo in reversed(lineas[-6:] or []):
            alto_grupo = max(g.abajo for g in grupo) - min(g.y for g in grupo)
            solape = (min(palabra.abajo, max(g.abajo for g in grupo))
                      - max(palabra.y, min(g.y for g in grupo)))
            if solape > 0.5 * min(palabra.alto, max(alto_grupo, 1)):
                grupo.append(palabra)
                break
        else:
            lineas.append([palabra])
    return [Linea(grupo) for grupo in lineas if grupo]


# ---------------------------------------------------------------------------
# Corte recursivo en X e Y
# ---------------------------------------------------------------------------

def _huecos(intervalos: list[tuple[int, int]], minimo: float) -> list[tuple[int, int]]:
    """Encuentra los espacios en blanco de una proyección.

    :param intervalos: Pares ``(inicio, fin)`` ocupados, en cualquier orden.
    :param minimo: Anchura mínima que ha de tener un hueco para contar.
    """
    if not intervalos:
        return []
    ordenados = sorted(intervalos)
    huecos = []
    fin_actual = ordenados[0][1]
    for inicio, fin in ordenados[1:]:
        if inicio - fin_actual >= minimo:
            huecos.append((fin_actual, inicio))
        fin_actual = max(fin_actual, fin)
    return huecos


def _altura_de_palabras(palabras: list[Palabra]) -> float:
    """Altura de letra representativa de un conjunto de palabras."""
    if not palabras:
        return 10.0
    alturas = sorted(palabra.alto for palabra in palabras)
    return float(alturas[len(alturas) // 2]) or 10.0


def _partir(palabras: list[Palabra], profundidad: int = 0) -> list[list[Palabra]]:
    """Parte las palabras de una página en el orden en que se leen.

    El corte se hace sobre las **palabras** y no sobre renglones ya montados, y
    ese detalle es lo que hace que funcione.  Si primero se juntan las palabras
    en líneas por su altura, las tres tarjetas de una fila de un folleto pasan
    a ser un único renglón que cruza la página entera; a partir de ahí ya no
    hay hueco vertical que encontrar y el orden se pierde sin remedio.  Cortando
    antes, las columnas aparecen solas.

    Se intenta primero el corte vertical —el que separa columnas— porque
    equivocarse ahí es lo que de verdad estropea el resultado: leer una rejilla
    por bandas mezcla el contenido de unas tarjetas con otras, mientras que
    partir de más solo altera el orden de dos párrafos vecinos.
    """
    if len(palabras) <= 1 or profundidad >= PROFUNDIDAD_MAXIMA:
        return [palabras] if palabras else []

    altura = _altura_de_palabras(palabras)

    # -- corte vertical: ¿hay columnas? --------------------------------------
    huecos = _huecos([(p.x, p.derecha) for p in palabras], altura * HUECO_VERTICAL)
    if huecos and len(huecos) < CORTES_MAXIMOS:
        columnas = _repartir(palabras, huecos, horizontal=True)
        if len(columnas) > 1:
            # Una tabla también tiene columnas separadas por huecos, y si se
            # cortara por ellos se leería columna entera a columna entera: los
            # encabezados por un lado y los números por otro, sin saber cuál va
            # con cuál.  Así que primero se mira si eso es una rejilla, y si lo
            # es se deja entera para escribirla como tabla de verdad.
            if _es_rejilla(columnas):
                _REJILLAS.add(id(palabras))
                return [palabras]
            partes: list[list[Palabra]] = []
            for columna in columnas:
                partes.extend(_partir(columna, profundidad + 1))
            return partes

    # -- corte horizontal: ¿hay bandas? --------------------------------------
    huecos = _huecos([(p.y, p.abajo) for p in palabras], altura * HUECO_HORIZONTAL)
    if huecos and len(huecos) < CORTES_MAXIMOS:
        bandas = _repartir(palabras, huecos, horizontal=False)
        if len(bandas) > 1:
            partes = []
            for banda in bandas:
                partes.extend(_partir(banda, profundidad + 1))
            return partes

    return [palabras]


class Bloque:
    """Un trozo de página ya ordenado, y si resultó ser una tabla.

    El dato de «esto era una tabla» se decide al **cortar** la página, mirando
    si todas las columnas tenían las mismas filas a las mismas alturas, y viaja
    con el bloque hasta que se escribe.  Volver a deducirlo después, ya sobre
    las líneas montadas, es lo que hacía que un párrafo justificado —donde las
    palabras se alinean por casualidad— acabara escrito como una tabla.
    """

    __slots__ = ("lineas", "es_tabla")

    def __init__(self, lineas: list[Linea], es_tabla: bool = False) -> None:
        self.lineas = lineas
        self.es_tabla = es_tabla

    def __iter__(self):
        return iter(self.lineas)

    def __len__(self) -> int:
        return len(self.lineas)

    def __repr__(self) -> str:
        return "<Bloque %d líneas%s>" % (len(self.lineas), ", tabla" if self.es_tabla else "")


def _es_rejilla(columnas: list[list[Palabra]]) -> bool:
    """Dice si unas columnas forman una tabla y no textos independientes.

    La diferencia entre una tabla y un folleto con tarjetas en rejilla es sutil
    de ver y fácil de comprobar: en una tabla, **todas las columnas tienen el
    mismo número de filas y a las mismas alturas**.  En una rejilla de
    tarjetas, cada una tiene el texto que tiene —una lleva una oferta, otra un
    origen— y las alturas no coinciden.

    Importa acertar porque el error es visible en las dos direcciones: tomar
    una tabla por columnas la vuelve ilegible, y tomar unas tarjetas por tabla
    mete cada frase en una celda que no le corresponde.
    """
    if len(columnas) < 2:
        return False
    filas_por_columna = [montar_lineas(columna) for columna in columnas]
    if any(len(filas) < FILAS_TABLA for filas in filas_por_columna):
        return False
    cuantas = {len(filas) for filas in filas_por_columna}
    if len(cuantas) != 1:
        return False        # no todas tienen el mismo número de filas

    # Las filas de todas las columnas tienen que estar a la misma altura.
    referencia = filas_por_columna[0]
    altura = _altura_tipica(referencia)
    for filas in filas_por_columna[1:]:
        for una, otra in zip(referencia, filas):
            if abs(una.y - otra.y) > altura:
                return False
    return True


def _repartir(palabras: list[Palabra], huecos: list[tuple[int, int]],
              horizontal: bool) -> list[list[Palabra]]:
    """Reparte las palabras entre las partes que dejan los huecos."""
    cortes = [(a + b) // 2 for a, b in huecos]
    grupos: list[list[Palabra]] = [[] for _parte in range(len(cortes) + 1)]
    for palabra in palabras:
        centro = (palabra.x + palabra.derecha) / 2 if horizontal else palabra.centro_y
        destino = len(cortes)
        for numero, corte in enumerate(cortes):
            if centro < corte:
                destino = numero
                break
        grupos[destino].append(palabra)
    return [grupo for grupo in grupos if grupo]


#: Regiones que el corte ha reconocido como rejilla, anotadas por identidad.
#: La recursión devuelve listas de palabras y no hay dónde colgar el dato hasta
#: que se montan las líneas, justo después; el conjunto se limpia enseguida.
_REJILLAS: set[int] = set()


def ordenar_lectura(palabras: list[Palabra]) -> list[Bloque]:
    """Agrupa las palabras en bloques de líneas, en orden de lectura."""
    if not palabras:
        return []
    _REJILLAS.clear()
    bloques = []
    for region in _partir(palabras):
        lineas = montar_lineas(region)
        if lineas:
            bloques.append(Bloque(lineas, id(region) in _REJILLAS))
    _REJILLAS.clear()
    return bloques


# ---------------------------------------------------------------------------
# Tablas
# ---------------------------------------------------------------------------

def _columnas_de(bloque: list[Linea], tolerancia: float) -> list[int] | None:
    """Busca los ejes de columna de una región, o ``None`` si no es una tabla.

    Se mira dónde empieza cada palabra: en una tabla, las de una misma columna
    arrancan casi en la misma vertical fila tras fila.  Si esa coincidencia se
    da en la mayoría de las filas, la región es una tabla.
    """
    filas = [linea for linea in bloque if len(linea.palabras) >= 2]
    if len(filas) < FILAS_TABLA:
        return None

    # Se toman los comienzos de palabra de la fila con más columnas y se
    # comprueba cuántas filas los respetan.
    referencia = max(filas, key=lambda linea: len(linea.palabras))
    ejes = sorted({palabra.x for palabra in referencia.palabras})
    if len(ejes) < 2:
        return None

    aciertos = 0
    for fila in filas:
        comienzos = [palabra.x for palabra in fila.palabras]
        encajan = sum(1 for eje in ejes
                      if any(abs(eje - comienzo) <= tolerancia for comienzo in comienzos))
        if encajan >= max(2, len(ejes) - 1):
            aciertos += 1
    if aciertos < len(filas) * COINCIDENCIA_TABLA:
        return None
    return ejes


def _fila_en_celdas(linea: Linea, ejes: list[int], tolerancia: float) -> list[str]:
    """Reparte las palabras de una fila entre las columnas de la tabla."""
    celdas = ["" for _columna in ejes]
    for palabra in linea.palabras:
        destino = 0
        for numero, eje in enumerate(ejes):
            if palabra.x >= eje - tolerancia:
                destino = numero
        celdas[destino] = (celdas[destino] + " " + palabra.texto).strip()
    return celdas


def _escapar(texto: str) -> str:
    """Deja un texto listo para meterlo en el HTML que se genera."""
    return (texto.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def bloque_a_html(bloque, tablas: bool = True) -> str:
    """Escribe un bloque como XHTML, en tabla si lo es y en párrafos si no."""
    lineas = list(bloque)
    if not lineas:
        return ""
    altura = _altura_tipica(lineas)
    # Solo se escribe como tabla lo que el corte reconoció como rejilla: mismas
    # filas en todas las columnas y a las mismas alturas.  Deducirlo aquí, de
    # cómo se alinean las palabras, convertía en tabla cualquier párrafo
    # justificado, donde se alinean por casualidad.
    es_tabla = tablas and getattr(bloque, "es_tabla", False)
    ejes = _columnas_de(lineas, altura * 1.5) if es_tabla else None
    if ejes:
        filas = []
        for linea in lineas:
            celdas = _fila_en_celdas(linea, ejes, altura * 1.5)
            filas.append("<tr>%s</tr>" % "".join(
                "<td>%s</td>" % _escapar(celda) for celda in celdas))
        return "<table>%s</table>" % "".join(filas)

    partes = []
    for linea in lineas:
        texto = linea.texto
        if texto:
            partes.append("<p>%s</p>" % _escapar(texto))
    return "".join(partes)


def a_html(palabras: list[Palabra], tablas: bool = True) -> str:
    """Convierte las palabras de una página en XHTML ordenado y estructurado.

    Es la puerta de entrada del módulo: se le dan las cajas que ha devuelto el
    OCR y devuelve el cuerpo de la página, con sus párrafos en orden de lectura
    y sus tablas como tablas.
    """
    bloques = ordenar_lectura(palabras)
    if not bloques:
        return ""
    log.debug("Disposición: %d palabras en %d bloques", len(palabras), len(bloques))
    return "".join(bloque_a_html(bloque, tablas) for bloque in bloques)


def a_texto(palabras: list[Palabra]) -> str:
    """Lo mismo, pero en texto plano, con una línea en blanco entre bloques."""
    trozos = []
    for bloque in ordenar_lectura(palabras):
        texto = "\n".join(linea.texto for linea in bloque if linea.texto)
        if texto.strip():
            trozos.append(texto)
    return "\n\n".join(trozos)


def resumen(palabras: list[Palabra]) -> str:
    """Describe en una frase lo que se ha encontrado, para el registro."""
    bloques = ordenar_lectura(palabras)
    lineas = sum(len(bloque) for bloque in bloques)
    tablas = sum(1 for bloque in bloques if bloque.es_tabla)
    return _("%d palabras, %d líneas, %d bloques, %d tablas") % (
        len(palabras), lineas, len(bloques), tablas)
