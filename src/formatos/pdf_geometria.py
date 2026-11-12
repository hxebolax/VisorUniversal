# -*- coding: utf-8 -*-
"""Estructura deducida de la geometría: los PDF que no dicen nada de sí mismos.

Un PDF etiquetado dice qué es cada cosa y se lee como un EPUB
(:mod:`formatos.pdf_etiquetado`).  El problema es el otro, que es la inmensa
mayoría: el PDF **con texto pero sin etiquetar**.  Ahí el archivo solo dice
«pon estas letras en este sitio», y de ahí hay que sacar qué era un título, qué
un punto de una lista y qué una tabla.

Hasta ahora eso se resolvía mirando la forma del texto ya aplanado: una línea
corta, suelta y sin punto final se daba por título.  Es lo único que se puede
hacer **con el texto**, y falla en el caso más común: PDFium devuelve las
líneas seguidas, sin una línea en blanco entre el título y el párrafo, así que
el título ni siquiera se distinguía como bloque aparte.  Medido sobre un PDF
con cuatro encabezados evidentes, se detectaban cero.

Lo que falta no es una heurística mejor: es **el dato**.  Un título no se
reconoce porque sea corto, se reconoce porque **está escrito más grande**.  Y
el tamaño de letra está en el archivo; lo que pasa es que PDFium no lo expone
por palabra.  pdfminer sí, a través de pdfplumber, y con eso el problema deja
de ser adivinatorio:

* **Encabezados**: por tamaño de letra respecto al del cuerpo del documento
  —no al de la página, que en una portada sería el del propio título—, por
  negrita y por numeración («3.2 Resultados»).
* **Nivel** del encabezado: por lo grande que sea respecto al cuerpo, o por la
  profundidad de su numeración, que es más fiable cuando la hay.
* **Listas**: por la viñeta o el ordinal con que empieza la línea.
* **Tablas**: primero las que tienen líneas dibujadas, que son inequívocas; y
  para las que no, el corte recursivo que el programa ya usa con el OCR
  (:mod:`formatos.disposicion`), que reconoce una rejilla porque sus columnas
  tienen las mismas filas a las mismas alturas.
* **Encabezados y pies de página**: por repetirse igual en muchas páginas.  Un
  informe de doscientas páginas repite su propio título doscientas veces, y
  quitarlo es la diferencia entre poder escucharlo y no.

Por qué el tamaño del cuerpo se calcula del documento y no de la página
-----------------------------------------------------------------------

Una portada tiene una sola línea, enorme.  Comparada consigo misma no destaca,
así que no sería un título.  Una página de índice tiene veinte líneas del mismo
tamaño y ninguna destacaría tampoco.  El tamaño normal del cuerpo es una
propiedad **del documento**, se calcula una vez sobre una muestra de páginas
repartida por todo él, y a partir de ahí cada página se juzga contra esa
referencia.

pdfplumber es opcional.  Sin él, este módulo dice que no puede y el analizador
sigue por el camino de siempre, que es peor pero funciona.
"""

from __future__ import annotations

import re
from statistics import median
from typing import Iterable, NamedTuple

from nucleo.registro import obtener_registro, registrar_excepcion

from . import disposicion

log = obtener_registro(__name__)

#: Cuánto más grande que el cuerpo tiene que ser una línea para ser un
#: encabezado.  Un 15 % es aproximadamente el salto de 11 a 13 puntos, que es
#: el más pequeño que usa un maquetador para marcar un título; por debajo se
#: cuelan los pies de figura, que muchas veces van medio punto más grandes.
SALTO_ENCABEZADO = 1.15

#: Saltos de tamaño a los que corresponde cada nivel de encabezado, del más
#: grande al más pequeño.  Solo se usan cuando el título no viene numerado: la
#: numeración es un dato del autor y manda sobre cualquier medida.
NIVELES = ((1.8, 1), (1.5, 2), (1.28, 3), (1.15, 4))

#: Largo máximo, en caracteres, de una línea que aspire a ser un encabezado.
#: Un título de más de doscientos caracteres es un párrafo escrito en grande,
#: normalmente una cita destacada.
LARGO_ENCABEZADO = 200

#: Proporción de páginas en las que tiene que repetirse una línea para darla
#: por encabezado o pie de página.  Con la mitad basta: hay documentos que
#: cambian el encabezado por capítulos y aun así conviene quitarlo.
REPETICION = 0.5

#: Cuántas líneas de arriba y de abajo de cada página se miran buscando
#: encabezados y pies repetidos.
FRANJA = 3

#: Cuántas páginas se muestrean para calcular el tamaño del cuerpo y encontrar
#: los encabezados repetidos.  Repartidas por todo el documento.
MUESTRA = 24

#: Viñetas con las que puede empezar un punto de una lista.  El guion y la raya
#: no están: en un texto normal empiezan diálogos, rangos de páginas y palabras
#: partidas, y tomarlos por viñetas destroza más de lo que arregla.
_VINETAS = "•·▪◦●○■□‣⁃∙*"

#: Punto de una lista: una viñeta o un ordinal, y detrás un espacio y algo.
_LISTA = re.compile(
    r"^\s*(?P<marca>[" + re.escape(_VINETAS) + r"]"
    r"|\(?\d{1,3}[.)]"
    r"|\(?[a-zA-Z][.)]"
    r"|\(?[ivxlcdmIVXLCDM]{1,6}[.)])\s+(?P<texto>\S.*)$"
)

#: Encabezado numerado: «3», «3.2», «3.2.1», «IV», y detrás el título.  El
#: nivel sale de cuántos números lleva, que es lo que quiso decir quien escribió
#: el documento.
_NUMERADO = re.compile(r"^\s*(?P<numero>\d{1,2}(?:\.\d{1,2}){0,5})\.?\s+(?P<texto>\S.*)$")

#: Marcas de fuente en negrita y cursiva.  Los nombres de fuente del PDF no
#: siguen ninguna norma, pero estas cadenas aparecen en casi todos.
_NEGRITA = ("bold", "black", "heavy", "semibold", "demibold", "-bd", "extrabold")
_CURSIVA = ("italic", "oblique", "-it")

#: Terminaciones que descartan una línea como encabezado: un título no acaba en
#: coma ni en punto y coma, y casi nunca en punto.
_FIN_DE_FRASE = (".", ",", ";", ":")

#: Hueco que tiene que haber entre dos letras para que sean dos palabras, medido
#: en proporción al cuerpo de la letra y no en puntos.
#:
#: El extractor lo mide en puntos y de fábrica pide tres, que es más de lo que
#: ocupa un espacio en letra pequeña: en un texto a nueve puntos —notas al pie,
#: manuales técnicos, documentos a dos columnas— el espacio mide dos y pico, no
#: llegaba al mínimo y el renglón salía escrito de corrido, como
#: «Solaris2.2mayrequiresetting».  En proporción al cuerpo, el espacio de un
#: texto pequeño sigue siendo un espacio, y el de un titular también.
SEPARACION_PALABRAS = 0.20


class Estilo(NamedTuple):
    """Con qué letra está escrita una línea."""

    tamano: float
    negrita: bool
    cursiva: bool
    fuente: str


class PaginaGeometrica(NamedTuple):
    """Una página ya medida: sus palabras, su estilo y sus tablas dibujadas.

    :param palabras: Cajas listas para :mod:`formatos.disposicion`, en
                     coordenadas de pantalla (el origen arriba a la izquierda),
                     que es lo que ese módulo espera.
    :param estilos: Estilo de cada palabra, indexado por su posición y texto.
                    Va aparte porque :class:`formatos.disposicion.Palabra` es
                    una tupla cerrada y compartida con el OCR, y añadirle
                    campos que el OCR nunca podrá rellenar solo serviría para
                    que estuvieran siempre vacíos.
    :param tablas: Tablas con líneas dibujadas, ya en rejilla, con su caja.
    :param enlaces: Enlaces de la página, cada uno con el rectángulo que ocupa
                    y su destino, en coordenadas de pantalla.  Los pone quien
                    llama (el analizador, que es quien tiene abierto PDFium),
                    porque los enlaces de un PDF no son texto sino anotaciones
                    dibujadas encima y pdfminer no los da con su destino
                    interno resuelto.
    """

    numero: int
    ancho: float
    alto: float
    palabras: list
    estilos: dict
    tablas: list
    enlaces: tuple = ()
    #: Figuras de la página: fotografías, gráficos y esquemas, con la caja que
    #: ocupan y el pie que se les haya encontrado.
    figuras: tuple = ()
    #: Filetes horizontales que separan secciones.
    separadores: tuple = ()
    #: Comentarios y notas adhesivas que alguien dejó en el PDF.
    comentarios: tuple = ()


class Contexto(NamedTuple):
    """Lo que solo se sabe mirando el documento entero, no una página.

    :param cuerpo: Tamaño de letra del texto normal del documento.
    :param artefactos: Líneas que se repiten en muchas páginas —el título del
                       informe, la numeración— y que por tanto no son
                       contenido.
    :param escala: Tamaños de letra de los encabezados del documento, de mayor
                   a menor.  El sitio que ocupa un tamaño en esta lista **es**
                   su nivel: el más grande es ``h1``, el siguiente ``h2``, y
                   así.  Véase :func:`_escala_de_encabezados`.
    """

    cuerpo: float
    artefactos: frozenset
    escala: tuple = ()
    #: Coordenada donde empieza el texto normal del documento.  Lo que empieza
    #: bastante más a la derecha está sangrado a propósito, y eso es una cita.
    margen: float = 0.0
    #: Alturas a las que hay un filete en casi todas las páginas.  Son las
    #: rayas de la cabecera y del pie, que son mobiliario de la página y no
    #: separan nada, igual que el texto que se repite arriba y abajo.
    filetes: frozenset = frozenset()
    #: Si en la muestra había alguna imagen o algún dibujo.  Sirve para saber
    #: si merece la pena medir un documento sin texto: si tampoco tiene nada
    #: dibujado, no hay absolutamente nada que sacar de su maquetación.
    hay_dibujos: bool = False
    #: Fuentes del documento en las que todas las letras ocupan lo mismo.  Es
    #: como se reconoce el código: en un manual de programación va en esa letra
    #: y en ninguna otra parte.  Véase :func:`_fuentes_monoespaciadas`.
    monoespaciadas: frozenset = frozenset()


#: Contexto vacío, para cuando no se ha podido medir el documento.
SIN_CONTEXTO = Contexto(0.0, frozenset(), (), 0.0, frozenset(), False, frozenset())


def disponible() -> bool:
    """Indica si se puede deducir la estructura de la geometría."""
    try:
        import pdfplumber  # noqa: F401
    except ImportError:
        return False
    return True


def abrir(ruta, contrasena: str = ""):
    """Abre el PDF para medirlo, o devuelve ``None`` si no se puede.

    Nunca lanza: este camino es una mejora, y si falla el analizador tiene que
    poder seguir por el de siempre sin enterarse.
    """
    try:
        import pdfplumber
    except ImportError:
        return None
    try:
        return pdfplumber.open(str(ruta), password=contrasena or "")
    except Exception as error:
        log.debug("pdfplumber no ha podido abrir %s: %s", ruta, error)
        return None


def cerrar(documento) -> None:
    """Cierra el documento de medida sin protestar si ya estaba cerrado."""
    if documento is None:
        return
    try:
        documento.close()
    except Exception:
        pass


def medir_documento(documento, total: int) -> Contexto:
    """Calcula el tamaño del cuerpo y las líneas que se repiten en el documento.

    Es una pasada previa sobre una muestra de páginas.  Cuesta lo que cuesten
    veinticuatro páginas y ahorra dos errores que se notan mucho: tomar por
    título cada línea de una portada, y leer doscientas veces el encabezado de
    un informe.
    """
    if documento is None:
        return SIN_CONTEXTO
    paso = max(1, total // MUESTRA)
    numeros = list(range(0, total, paso))[:MUESTRA]
    tamanos: list[float] = []
    candidatos: list[tuple[str, float]] = []
    franjas: list[str] = []
    margenes: list[float] = []
    filetes: list[float] = []
    anchos: dict[str, dict[str, float]] = {}
    letras_por_fuente: dict[str, int] = {}
    dibujos = False
    paginas_vistas = 0
    for numero in numeros:
        lineas = _lineas_muestreadas(documento, numero)
        if lineas is None:
            continue
        paginas_vistas += 1
        for texto, tamano, cuantos, inicio in lineas:
            # Cada línea pesa lo que mide: si no, un documento con muchos
            # titulillos cortos y pocos párrafos largos daría un «cuerpo»
            # demasiado grande y no detectaría ningún encabezado.
            tamanos.extend([tamano] * max(1, cuantos // 10))
            candidatos.append((texto, tamano))
            if cuantos >= 40:
                # Solo los renglones largos dicen dónde está el margen: los
                # cortos son títulos centrados, números de página y pies.
                margenes.append(round(inicio))
        franjas.extend(_franja(lineas))
        filetes.extend(_alturas_de_filete(documento, numero))
        _anchos_por_fuente(documento, numero, anchos, letras_por_fuente)
        dibujos = dibujos or _tiene_dibujos(documento, numero)
    cuerpo = float(median(tamanos)) if tamanos else 0.0
    artefactos = _repetidos(franjas, paginas_vistas)
    escala = _escala_de_encabezados(candidatos, cuerpo)
    margen = _margen_habitual(margenes)
    repetidos = _repetidos(["%.0f" % altura for altura in filetes], paginas_vistas)
    monoespaciadas = _fuentes_monoespaciadas(anchos, letras_por_fuente)
    log.debug("Geometría: cuerpo %.1f pt, margen %.0f, escala %s, %d líneas repetidas, "
              "%d filetes de página, %d fuentes de máquina de escribir, en %d páginas",
              cuerpo, margen, ["%.1f" % t for t in escala], len(artefactos),
              len(repetidos), len(monoespaciadas), paginas_vistas)
    return Contexto(cuerpo, artefactos, escala, margen, repetidos, dibujos, monoespaciadas)

#: Cuánto pueden diferir dos letras de una fuente para seguir teniéndola por
#: monoespaciada, en proporción al cuerpo.  En una de verdad la diferencia es
#: cero; el margen es para los redondeos de las coordenadas.
HOLGURA_MONOESPACIADA = 0.02

#: Letras distintas que hay que haber visto de una fuente para poder opinar
#: sobre ella.  Con menos se equivocaría: las cifras van a la misma anchura en
#: casi todas las fuentes, y por eso aquí solo cuentan las letras.
LETRAS_PARA_JUZGAR = 6

#: Proporción de letra de máquina de escribir a partir de la cual esa **es** la
#: letra del documento y por tanto no señala nada.
CUERPO_MONOESPACIADO = 0.6


def _anchos_por_fuente(documento, indice: int, anchos: dict, cuantas: dict) -> None:
    """Anota lo que ocupa cada letra de una página, por fuente y por carácter.

    Se guarda la primera vez que se ve cada letra de cada fuente y no todas:
    con una basta, porque lo que se quiere saber es si la «i» y la «m» miden lo
    mismo, y eso no cambia de una página a otra.

    De paso se cuenta cuántas letras lleva escritas cada fuente, que es lo que
    dice si una es la letra del documento o la excepción dentro de él.
    """
    try:
        pagina = documento.pages[indice]
        letras = getattr(pagina, "chars", None) or ()
    except Exception:
        return
    for letra in letras:
        try:
            texto = str(letra.get("text") or "")
            tamano = float(letra.get("size") or 0.0)
            ancho = float(letra["x1"]) - float(letra["x0"])
        except (KeyError, TypeError, ValueError):
            continue
        if len(texto) != 1 or not texto.isalpha() or tamano <= 0 or ancho <= 0:
            continue
        fuente = str(letra.get("fontname") or "")
        anchos.setdefault(fuente, {}).setdefault(texto, ancho / tamano)
        cuantas[fuente] = cuantas.get(fuente, 0) + 1


def _fuentes_monoespaciadas(anchos: dict, cuantas: dict) -> frozenset:
    """Devuelve las fuentes del documento en las que todas las letras miden igual.

    Se **mide**, en lugar de mirar el nombre.  El nombre no sirve de nada: llega
    con el prefijo del subconjunto («GAAAAA+Menlo-Regular»), cada familia se
    llama de una manera —Menlo, Consolas, Courier, cmtt, Inconsolata— y una
    fuente puede llamarse «Mono» sin serlo.  Que la «i» y la «m» ocupen lo
    mismo, en cambio, es lo que define una letra de máquina de escribir y no
    admite discusión.

    Hace falta para reconocer el código, que en un PDF no está marcado en
    ninguna parte: lo único que lo distingue del texto es esa letra.
    """
    monoespaciadas = set()
    for fuente, letras in anchos.items():
        if len(letras) < LETRAS_PARA_JUZGAR:
            continue
        medidas = letras.values()
        if max(medidas) - min(medidas) <= HOLGURA_MONOESPACIADA:
            monoespaciadas.add(fuente)
    # Si el documento **está escrito** en letra de máquina de escribir —un
    # listado, un informe antiguo, un texto plano pasado a PDF—, esa letra es
    # su letra normal y no distingue nada.  Sin esta salvedad, el documento
    # entero se daba por código: se perdían sus encabezados y sus listas.
    total = sum(cuantas.values())
    escritas = sum(cuantas.get(fuente, 0) for fuente in monoespaciadas)
    if total and escritas / total >= CUERPO_MONOESPACIADO:
        return frozenset()
    return frozenset(monoespaciadas)


def _tiene_dibujos(documento, indice: int) -> bool:
    """Indica si una página trae alguna imagen o algún trazo.

    Es una comprobación de nada —mirar si tres listas están vacías— y sirve
    para no medir un documento del que no se puede sacar nada: uno escaneado no
    tiene ni texto ni dibujos que agrupar, porque la fotografía de la página se
    descarta por ocupar la página entera.
    """
    try:
        pagina = documento.pages[indice]
        return any(getattr(pagina, nombre, None) for nombre in ("images", "curves", "rects"))
    except Exception:
        return False


def _alturas_de_filete(documento, indice: int) -> list:
    """Alturas de los filetes largos de una página, para ver cuáles se repiten.

    Se miden aparte de :func:`_separadores_de_pagina` porque aquí no interesa
    qué separa cada uno, solo a qué altura está: los que aparecen a la misma
    altura en casi todas las páginas son la raya de la cabecera y la del pie.
    """
    try:
        pagina = documento.pages[indice]
        ancho = float(getattr(pagina, "width", 0.0) or 0.0)
    except Exception:
        return []
    if ancho <= 0:
        return []
    alturas = []
    for tipo in ("lines", "rects"):
        for trazo in getattr(pagina, tipo, None) or ():
            try:
                if abs(float(trazo["bottom"]) - float(trazo["top"])) > GROSOR_FILETE:
                    continue
                if (float(trazo["x1"]) - float(trazo["x0"])) < ancho * FILETE_LARGO:
                    continue
                alturas.append(round((float(trazo["top"]) + float(trazo["bottom"])) / 2.0))
            except (KeyError, TypeError, ValueError):
                continue
    return sorted(set(alturas))


def _margen_habitual(margenes: list) -> float:
    """Dónde empieza el texto normal del documento.

    Es la moda y no la media: un documento tiene un margen y unos cuantos
    bloques sangrados, y la media caería entre los dos, en una posición donde
    no empieza nada.
    """
    if not margenes:
        return 0.0
    cuenta: dict[float, int] = {}
    for margen in margenes:
        cuenta[margen] = cuenta.get(margen, 0) + 1
    return float(max(cuenta, key=lambda clave: (cuenta[clave], -clave)))


def _escala_de_encabezados(candidatos, cuerpo: float) -> tuple:
    """Averigua qué tamaños de letra usa el documento para sus títulos.

    Deducir el nivel de un encabezado de lo grande que sea —«un 80 % más que el
    cuerpo es un ``h1``»— tiene un defecto que se nota enseguida: los niveles
    **se saltan**.  Un documento cuyos títulos van a 16, 14 y 13 puntos sobre un
    cuerpo de 12 produce ``h1``, ``h2`` y ``h4``, porque 13 sobre 12 cae en un
    tramo y 14 en otro.  Y saltarse un nivel no es un detalle estético: rompe
    el árbol del documento, es un fallo de la norma (ISO 14289-1, 7.4) y hace
    que al recorrerlo con las órdenes de encabezado por nivel falte un peldaño.

    Lo que se hace en su lugar es mirar **qué tamaños usa este documento** para
    titular, ordenarlos de mayor a menor y numerarlos.  El más grande es el
    nivel uno, el siguiente el dos, sin huecos, sean cuales sean los puntos.
    Es lo que hace quien maqueta: no elige «un 80 % más», elige *el* tamaño de
    los títulos de capítulo.

    Los tamaños se agrupan con una tolerancia de medio punto porque el mismo
    estilo puede salir como 13,98 y 14,02 según cómo se escalara la página.
    """
    if cuerpo <= 0:
        return ()
    cuenta: dict[float, int] = {}
    for texto, tamano in candidatos:
        if tamano < cuerpo * SALTO_ENCABEZADO or len(texto) > LARGO_ENCABEZADO:
            continue
        if texto.endswith(_FIN_DE_FRASE[:2]):
            continue
        clave = round(tamano * 2) / 2.0
        cuenta[clave] = cuenta.get(clave, 0) + 1
    if not cuenta:
        return ()
    # Todos los tamaños cuentan, incluidos los que aparecen una sola vez: el
    # título del documento sale una vez y es precisamente el nivel uno.
    # Descartar lo poco frecuente dejaba fuera el ``h1`` y hundía un nivel toda
    # la jerarquía.
    tamanos = sorted(cuenta, reverse=True)
    if len(tamanos) > 6:
        # Con más de seis candidatos hay ruido —un número de página en grande,
        # una fecha en la portada—, y entonces sí conviene quedarse con los que
        # se repiten, que son los estilos de verdad del documento.
        repetidos = sorted((t for t in tamanos if cuenta[t] >= 2), reverse=True)
        tamanos = repetidos or tamanos
    return tuple(tamanos[:6])


def leer_pagina(documento, numero: int, enlaces=()) -> PaginaGeometrica | None:
    """Mide una página: sus palabras con estilo y sus tablas dibujadas.

    :param numero: Número de página empezando en 1.
    """
    if documento is None:
        return None
    try:
        pagina = documento.pages[numero - 1]
    except Exception as error:
        log.debug("No se ha podido acceder a la página %d: %s", numero, error)
        return None
    try:
        palabras_crudas = pagina.extract_words(
            keep_blank_chars=False,
            use_text_flow=False,
            x_tolerance_ratio=SEPARACION_PALABRAS,
        )
        letras = _letras_por_renglon(pagina)
    except Exception as error:
        registrar_excepcion(log, "Error midiendo la página %d" % numero, error)
        return None
    palabras: list = []
    estilos: dict = {}
    for cruda in palabras_crudas:
        texto = str(cruda.get("text") or "").strip()
        if not texto:
            continue
        try:
            x = int(round(float(cruda["x0"])))
            y = int(round(float(cruda["top"])))
            ancho = max(1, int(round(float(cruda["x1"]) - float(cruda["x0"]))))
            alto = max(1, int(round(float(cruda["bottom"]) - float(cruda["top"]))))
        except (KeyError, TypeError, ValueError):
            continue
        palabra = disposicion.Palabra(texto, x, y, ancho, alto)
        palabras.append(palabra)
        estilos[_clave(palabra)] = _estilo_de_palabra(letras, cruda)
    alto = float(getattr(pagina, "height", 0.0) or 0.0)
    tablas = _tablas_dibujadas(pagina, numero)
    figuras = _figuras_de_pagina(pagina, numero)
    return PaginaGeometrica(
        numero=numero,
        ancho=float(getattr(pagina, "width", 0.0) or 0.0),
        alto=alto,
        palabras=palabras,
        estilos=estilos,
        tablas=tablas,
        enlaces=tuple(enlaces or ()),
        figuras=figuras,
        separadores=_separadores_de_pagina(pagina, _zonas_ocupadas(tablas, figuras, alto)),
        comentarios=_comentarios_de_pagina(pagina),
    )


def estructurar(pagina: PaginaGeometrica, contexto: Contexto = SIN_CONTEXTO,
                tablas: bool = True) -> str:
    """Convierte una página medida en XHTML con encabezados, listas y tablas.

    El orden de operaciones importa y no es arbitrario:

    1. Se apartan las **tablas dibujadas**, que son inequívocas, y las palabras
       que caen dentro de ellas.  Si no se hiciera primero, sus celdas se
       leerían como párrafos sueltos y además engañarían al corte de columnas.
    2. Lo que queda se ordena con el corte recursivo, que además reconoce las
       **rejillas sin líneas**.
    3. Cada bloque se escribe: en tabla si lo es, y si no, línea a línea
       decidiendo encabezado, punto de lista o párrafo.
    4. Se intercalan las **figuras**, los **filetes** y los **comentarios** por
       la altura a la que están.

    Y todo se emite en el orden vertical de la página, para que cada cosa salga
    donde estaba y no al principio ni al final.
    """
    if not (pagina.palabras or pagina.tablas or pagina.figuras or pagina.comentarios):
        return ""
    sueltas = _fuera_de_tablas(pagina) if tablas else list(pagina.palabras)
    if not contexto.cuerpo:
        # Sin medida del documento se usa la de la página, que es peor pero
        # sigue siendo mejor que no tener referencia ninguna.
        contexto = contexto._replace(cuerpo=_cuerpo_de_pagina(pagina, sueltas))
    cortes, columnas = _partir_en_columnas(sueltas, pagina.ancho)
    piezas: list[tuple[float, float, str]] = []
    if tablas:
        for caja, html in pagina.tablas:
            centro = (caja[0] + caja[2]) / 2.0
            piezas.append((float(_columna_de(centro, cortes)), caja[1], html))
    for figura in pagina.figuras:
        centro = (figura.caja[0] + figura.caja[2]) / 2.0
        piezas.append((float(_columna_de(centro, cortes)), figura.arriba,
                       _figura_a_html(figura, pagina.numero)))
    for altura in _separadores_utiles(pagina.separadores, contexto):
        piezas.append((0.0, float(altura), "<hr/>"))
    for altura, autor, texto in pagina.comentarios:
        piezas.append((0.0, float(altura), _comentario_a_html(autor, texto)))
    for orden, columna in enumerate(columnas):
        # La sangría se mide contra el margen de **esta** columna, no contra el
        # del documento.  En un texto a dos columnas, la de la derecha empieza
        # decenas de puntos más allá del margen del documento, y comparándola
        # con él la columna entera pasaba por cita.
        propio = contexto._replace(margen=_margen_de_columna(columna, contexto))
        for bloque in disposicion.ordenar_lectura(columna):
            lineas = [linea for linea in bloque if linea.texto.strip()]
            if not lineas:
                continue
            arriba = float(min(linea.y for linea in lineas))
            if tablas and getattr(bloque, "es_tabla", False) and _tabla_creible(lineas):
                html = disposicion.bloque_a_html(bloque, tablas=True)
            else:
                html = _bloque_a_html(lineas, pagina, propio)
            if html:
                # La columna manda sobre la altura: en un texto a dos columnas
                # se lee entera la izquierda y después entera la derecha, no
                # saltando de una a otra renglón a renglón.
                piezas.append((float(orden), arriba, html))
    piezas.sort(key=lambda pieza: (pieza[0], pieza[1]))
    return "".join(html for _columna, _arriba, html in piezas)


# ---------------------------------------------------------------------------
# Medida del documento
# ---------------------------------------------------------------------------

def _letras_por_renglon(pagina) -> dict:
    """Agrupa las letras de la página por renglón, ordenadas de izquierda a derecha.

    Sirve para averiguar con qué letra está escrita cada palabra **sin pedírselo
    al extractor**.  Y eso hace falta por una razón muy concreta: pdfplumber
    parte una palabra en dos en cuanto cambia cualquier atributo que se le pida
    —incluido el tamaño—, de modo que pedirle el tamaño para poder reconocer
    los títulos partía todas las palabras compuestas en versalitas.  Una línea
    que dice «INCLUDING ALL STUDENTS» salía como «I NCLUDING A LL S TUDENTS»,
    porque la mayúscula inicial va un par de puntos más grande que el resto.

    Se le piden las palabras sin atributos —que es como las parte bien— y el
    estilo se busca aquí, mirando qué letras caen dentro de cada palabra.
    """
    renglones: dict[int, list] = {}
    for letra in getattr(pagina, "chars", None) or ():
        try:
            clave = int(round(float(letra["top"]) / 3.0))
            renglones.setdefault(clave, []).append(letra)
        except (KeyError, TypeError, ValueError):
            continue
    for grupo in renglones.values():
        grupo.sort(key=lambda letra: float(letra.get("x0") or 0.0))
    return renglones


def _estilo_de_palabra(letras: dict, cruda: dict) -> Estilo:
    """Averigua tamaño, negrita y cursiva de una palabra por sus letras.

    Se toma el tamaño **más grande** de la palabra y no la media: en una
    palabra en versalitas la inicial es la que marca el tamaño del renglón, y
    promediarla con el resto daría un tamaño intermedio que no existe y que
    estropearía la escala de encabezados.
    """
    try:
        clave = int(round(float(cruda["top"]) / 3.0))
        izquierda = float(cruda["x0"]) - 0.5
        derecha = float(cruda["x1"]) + 0.5
    except (KeyError, TypeError, ValueError):
        return Estilo(0.0, False, False, "")
    tamanos: list[float] = []
    fuentes: list[str] = []
    for vecino in (clave - 1, clave, clave + 1):
        for letra in letras.get(vecino, ()):
            try:
                centro = (float(letra["x0"]) + float(letra["x1"])) / 2.0
            except (KeyError, TypeError, ValueError):
                continue
            if not izquierda <= centro <= derecha:
                continue
            if letra.get("size"):
                tamanos.append(float(letra["size"]))
            fuentes.append(str(letra.get("fontname") or ""))
    if not tamanos and not fuentes:
        return Estilo(0.0, False, False, "")
    # Se ordena antes de elegir para que un empate se resuelva siempre igual:
    # sin ordenar, el ganador dependía del orden en que el conjunto guardara
    # las cadenas, que cambia de una ejecución a otra.
    fuente = max(sorted(set(fuentes)), key=fuentes.count) if fuentes else ""
    minuscula = fuente.lower()
    return Estilo(
        tamano=max(tamanos) if tamanos else 0.0,
        negrita=any(marca in minuscula for marca in _NEGRITA),
        cursiva=any(marca in minuscula for marca in _CURSIVA),
        fuente=fuente,
    )


def _clave(palabra) -> tuple:
    """Identifica una palabra dentro de su página.

    Posición y texto bastan: dos palabras distintas no pueden ocupar el mismo
    punto exacto de la misma página.
    """
    return (palabra.x, palabra.y, palabra.texto)


def _lineas_muestreadas(documento, indice: int):
    """Devuelve ``(texto, tamaño, caracteres, x0)`` de cada renglón de una página.

    Es una versión barata de :func:`leer_pagina` para la pasada previa: no
    monta cajas ni busca tablas, solo necesita medir.
    """
    try:
        pagina = documento.pages[indice]
        palabras = pagina.extract_words(
            keep_blank_chars=False, x_tolerance_ratio=SEPARACION_PALABRAS)
        letras = _letras_por_renglon(pagina)
    except Exception as error:
        log.debug("No se ha podido medir la página %d: %s", indice + 1, error)
        return None
    renglones: dict[int, list] = {}
    for palabra in palabras:
        try:
            fila = int(round(float(palabra["top"]) / 3.0))
        except (KeyError, TypeError, ValueError):
            continue
        renglones.setdefault(fila, []).append(palabra)
    resultado = []
    for fila in sorted(renglones):
        grupo = sorted(renglones[fila], key=lambda p: float(p.get("x0") or 0.0))
        texto = " ".join(str(p.get("text") or "") for p in grupo).strip()
        if not texto:
            continue
        # El tamaño se busca por las letras y no se le pide al extractor: si se
        # le pide, parte las palabras en versalitas (véase
        # :func:`_letras_por_renglon`).
        tamanos = [_estilo_de_palabra(letras, p).tamano for p in grupo]
        tamanos = [tamano for tamano in tamanos if tamano > 0]
        resultado.append((texto, median(tamanos) if tamanos else 0.0, len(texto),
                          min(float(p.get("x0") or 0.0) for p in grupo)))
    return resultado


def _franja(lineas) -> list[str]:
    """Devuelve las líneas de arriba y de abajo de una página, normalizadas."""
    if not lineas:
        return []
    borde = [renglon[0] for renglon in lineas[:FRANJA] + lineas[-FRANJA:]]
    return [clave for clave in (normalizar(texto) for texto in borde) if clave]


def normalizar(texto: str) -> str:
    """Reduce una línea a lo que la identifica aunque cambie de página.

    Los números se sustituyen por un signo: el pie «Informe anual — página 12»
    es el mismo en las doscientas páginas salvo por el número, y sin esta
    sustitución no se reconocería ni una sola repetición.
    """
    return " ".join(re.sub(r"\d+", "#", texto.casefold()).split())


def _repetidos(claves: Iterable[str], paginas: int) -> frozenset:
    """Devuelve las líneas que se repiten en bastantes páginas.

    Se exige un mínimo absoluto de tres además de la proporción: en un
    documento de cuatro páginas, dos coincidencias son casualidad —dos
    capítulos que empiezan igual— y borrarlas quitaría contenido de verdad.
    """
    if paginas < 3:
        return frozenset()
    cuenta: dict[str, int] = {}
    for clave in claves:
        cuenta[clave] = cuenta.get(clave, 0) + 1
    minimo = max(3, int(paginas * REPETICION))
    return frozenset(clave for clave, veces in cuenta.items() if veces >= minimo)


def _cuerpo_de_pagina(pagina: PaginaGeometrica, palabras) -> float:
    """Tamaño de letra normal de una sola página, como último recurso.

    Solo se usa cuando no se pudo medir el documento entero.  Es peor —una
    portada no tiene «cuerpo»— pero es mejor que no tener referencia.
    """
    tamanos = [pagina.estilos[_clave(p)].tamano
               for p in palabras if _clave(p) in pagina.estilos]
    tamanos = [t for t in tamanos if t > 0]
    return float(median(tamanos)) if tamanos else 0.0


# ---------------------------------------------------------------------------
# Tablas dibujadas
# ---------------------------------------------------------------------------

def _tablas_dibujadas(pagina, numero: int) -> list:
    """Busca las tablas que traen sus líneas pintadas y las escribe ya.

    Una tabla con líneas no admite discusión: alguien dibujó la rejilla a
    propósito.  Se resuelven aquí, aparte del corte recursivo, porque la
    detección por líneas acierta donde la geométrica duda —celdas vacías,
    celdas combinadas, filas de una sola columna— y porque conocer su
    rectángulo permite quitar sus palabras del resto de la página.

    :return: Lista de ``((x0, arriba, x1, abajo), XHTML)``.
    """
    try:
        encontradas = pagina.find_tables()
    except Exception as error:
        log.debug("No se han podido buscar tablas en la página %d: %s", numero, error)
        return []
    resultado = []
    for tabla in encontradas:
        try:
            filas = tabla.extract()
            caja = tuple(float(valor) for valor in tabla.bbox)
        except Exception:
            continue
        html = _rejilla_a_html(filas)
        if html:
            resultado.append((caja, html))
    return resultado


def _rejilla_a_html(filas) -> str:
    """Escribe una rejilla de celdas como tabla XHTML.

    La primera fila se marca como encabezado solo si lo parece: todas sus
    celdas con texto y ninguna con pinta de dato numérico.  Marcar como
    encabezado una fila de números hace que el lector de pantalla anuncie «12»
    como nombre de la columna en cada celda, que es peor que no marcar nada.
    """
    limpias = []
    for fila in filas or ():
        celdas = [" ".join(str(celda or "").split()) for celda in fila]
        if any(celda for celda in celdas):
            limpias.append(celdas)
    if len(limpias) < 2 or len(limpias[0]) < 2:
        return ""
    con_encabezado = _parece_encabezado(limpias[0])
    partes = []
    for indice, fila in enumerate(limpias):
        etiqueta = "th" if indice == 0 and con_encabezado else "td"
        atributo = ' scope="col"' if etiqueta == "th" else ""
        partes.append("<tr>%s</tr>" % "".join(
            "<%s%s>%s</%s>" % (etiqueta, atributo, _escapar(celda), etiqueta)
            for celda in fila))
    return "<table>%s</table>" % "".join(partes)


def _parece_encabezado(fila: list) -> bool:
    """Indica si esa fila son nombres de columna y no datos."""
    utiles = [celda for celda in fila if celda]
    if len(utiles) < len(fila):
        return False
    numericas = sum(1 for celda in utiles
                    if re.fullmatch(r"[\d.,%€$\s+-]+", celda))
    return numericas * 2 < len(utiles)


def _fuera_de_tablas(pagina: PaginaGeometrica) -> list:
    """Quita las palabras que ya se han escrito dentro de una tabla dibujada."""
    if not pagina.tablas:
        return list(pagina.palabras)
    cajas = [caja for caja, _html in pagina.tablas]
    fuera = []
    for palabra in pagina.palabras:
        centro_x = palabra.x + palabra.ancho / 2.0
        centro_y = palabra.y + palabra.alto / 2.0
        if any(x0 <= centro_x <= x1 and arriba <= centro_y <= abajo
               for x0, arriba, x1, abajo in cajas):
            continue
        fuera.append(palabra)
    return fuera


# ---------------------------------------------------------------------------
# Figuras, filetes y comentarios
# ---------------------------------------------------------------------------

#: Superficie mínima de una figura, en proporción de la página.  Por debajo de
#: esto son viñetas, logotipos de cabecera, iconos y adornos: anunciarlos uno
#: por uno llenaría el documento de «[Imagen]» sin contenido.
FIGURA_MINIMA = 0.012

#: Superficie a partir de la cual una imagen es el fondo de la página y no una
#: figura.  Una página escaneada es una sola imagen que la ocupa entera, y
#: anunciarla como figura sería decir «[Imagen]» delante de todo el texto que
#: el reconocimiento óptico acaba de sacar de ella.
FIGURA_MAXIMA = 0.9

#: Cuántos trazos hacen falta para que un grupo de dibujo sea una figura.  Un
#: gráfico de un informe son decenas de líneas, rellenos y rótulos; dos o tres
#: trazos sueltos son un adorno o el borde de un recuadro.
TRAZOS_MINIMOS = 8

#: Separación máxima entre trazos para considerarlos parte del mismo dibujo, en
#: proporción del ancho de la página.
CERCANIA = 0.05

#: Grosor máximo, en puntos, de un trazo que sea un filete y no un relleno.
GROSOR_FILETE = 3.0

#: Cuánto de su alto tiene que llevar ocupado de texto un trazo para tenerlo
#: por el fondo de ese texto y no por un dibujo.  Véase :func:`_es_fondo`.
COBERTURA_FONDO = 0.4

#: Proporción del ancho de la página que tiene que cubrir un filete para
#: contarlo como separador de secciones.  Uno más corto es el subrayado de un
#: título o el borde de una celda.
FILETE_LARGO = 0.35

#: Palabras con las que empieza el pie de una figura.  Se aceptan en español y
#: en inglés porque un pie mal reconocido no rompe nada —la figura se queda sin
#: pie— pero uno reconocido convierte «[Imagen]» en «[Figura: Ventas por
#: trimestre]», que es toda la diferencia.
_PIES = (
    "figura", "fig.", "fig ", "gráfico", "grafico", "cuadro", "ilustración",
    "ilustracion", "imagen", "esquema", "lámina", "lamina", "mapa", "foto",
    "figure", "chart", "image", "diagram", "photo", "plate", "map", "graph",
)

#: Distancia máxima, en múltiplos de la altura de una línea, a la que se busca
#: el pie de una figura por encima o por debajo de ella.
DISTANCIA_PIE = 2.5

#: El rótulo con el que empieza el pie de una figura: la palabra, su número y
#: el separador.  Se quita para poder ver si detrás queda una descripción o si
#: el pie era solo el rótulo.
_SOLO_ROTULO = re.compile(
    r"^(?:%s)\s*[\w.\-]*\s*[.:\-—–]?\s*" % "|".join(
        re.escape(palabra.strip()) for palabra in _PIES),
    re.IGNORECASE)


class Figura(NamedTuple):
    """Una figura de la página, con dónde está y cómo se llama.

    :param caja: ``(x0, abajo, x1, arriba)`` en coordenadas del PDF, con el
                 origen abajo a la izquierda.  Es el sistema que espera
                 ``AnalizadorPDF.extraer_recurso`` para recortarla, y por eso
                 no se convierte a coordenadas de pantalla como todo lo demás.
    :param pie: Texto del pie, si se ha encontrado alguno.
    :param arriba: Coordenada superior en pantalla, para colocar la figura
                   entre los párrafos en el orden en que aparece.
    :param vectorial: Si es un dibujo hecho de trazos y no una fotografía.
    """

    caja: tuple
    pie: str
    arriba: float
    vectorial: bool


def _figuras_de_pagina(pagina, numero: int) -> tuple:
    """Encuentra las figuras de una página y les busca su pie.

    En un PDF etiquetado las figuras vienen marcadas y con su texto
    alternativo.  Aquí no hay nada de eso, así que se buscan las dos formas en
    que una figura existe dentro de un PDF:

    * **Fotografías e ilustraciones**, que son imágenes incrustadas y aparecen
      como tales.
    * **Gráficos y esquemas**, que no son ninguna imagen: son decenas de
      líneas, rellenos y rótulos dibujados uno a uno.  Se reconocen porque esos
      trazos se agrupan en una zona de la página y son muchos.

    No se quita el texto que caiga dentro de una figura, al contrario que en el
    camino etiquetado.  Allí el árbol dice con certeza qué pertenece a la
    figura; aquí es una deducción, y equivocarse borrando texto es mucho peor
    que dejar los rótulos de un gráfico leyéndose detrás de él.  De propina,
    los rótulos de un gráfico dicen bastante de lo que el gráfico enseña.
    """
    ancho = float(getattr(pagina, "width", 0.0) or 0.0)
    alto = float(getattr(pagina, "height", 0.0) or 0.0)
    if ancho <= 0 or alto <= 0:
        return ()
    superficie = ancho * alto
    lineas = _renglones_de(pagina)
    cajas = _imagenes_incrustadas(pagina, superficie)
    cajas.extend(_dibujos_agrupados(pagina, ancho, alto, superficie, lineas))
    cajas = _sin_solapes(cajas)
    if not cajas:
        return ()
    figuras = []
    for x0, abajo, x1, arriba, vectorial in cajas:
        figuras.append(Figura(
            caja=(round(x0, 2), round(abajo, 2), round(x1, 2), round(arriba, 2)),
            pie=_pie_de(lineas, x0, x1, alto - arriba, alto - abajo),
            arriba=alto - arriba,
            vectorial=vectorial,
        ))
    del numero
    return tuple(sorted(figuras, key=lambda figura: figura.arriba))


def _imagenes_incrustadas(pagina, superficie: float) -> list:
    """Devuelve las imágenes de verdad de la página, sin adornos ni fondos."""
    resultado = []
    for imagen in getattr(pagina, "images", None) or ():
        try:
            x0, abajo = float(imagen["x0"]), float(imagen["y0"])
            x1, arriba = float(imagen["x1"]), float(imagen["y1"])
        except (KeyError, TypeError, ValueError):
            continue
        area = max(0.0, x1 - x0) * max(0.0, arriba - abajo)
        if not superficie or not FIGURA_MINIMA <= area / superficie <= FIGURA_MAXIMA:
            continue
        resultado.append((x0, abajo, x1, arriba, False))
    return resultado


def _dibujos_agrupados(pagina, ancho: float, alto: float, superficie: float,
                       lineas: list) -> list:
    """Agrupa los trazos sueltos de la página en los dibujos que forman.

    Se juntan los trazos que están cerca unos de otros y se conserva el grupo
    si tiene bastantes y ocupa bastante.  Antes de agrupar se quitan tres cosas
    que no son dibujo:

    * Los **filetes** largos y finos: son separadores y bordes de tabla, y si
      entraran unirían por su cuenta media página en un solo «dibujo».
    * Los trazos **repetidos**: un mismo rectángulo pintado cuatro veces —cosa
      corriente en los PDF hechos a partir de HTML— contaba como cuatro trazos
      y por sí solo alcanzaba el mínimo para pasar por figura.
    Los **fondos** —un relleno con texto seguido encima, véase :func:`_es_fondo`—
    no se quitan, pero **no cuentan** para el mínimo: un fondo no es prueba de
    que haya un dibujo, aunque sí forma parte de su extensión.  Así el fondo de
    un bloque de código no llega por sí solo a figura, y el recuadro de la
    leyenda de un gráfico no le resta al gráfico los trazos que necesita.
    """
    trazos = []
    vistos = set()
    for tipo in ("curves", "rects"):
        for trazo in getattr(pagina, tipo, None) or ():
            try:
                x0, abajo = float(trazo["x0"]), float(trazo["y0"])
                x1, arriba = float(trazo["x1"]), float(trazo["y1"])
            except (KeyError, TypeError, ValueError):
                continue
            if _es_filete(x1 - x0, arriba - abajo):
                continue
            clave = (round(x0, 1), round(abajo, 1), round(x1, 1), round(arriba, 1))
            if clave in vistos:
                continue
            vistos.add(clave)
            fondo = _es_fondo((x0, abajo, x1, arriba), alto, lineas)
            trazos.append([x0, abajo, x1, arriba, fondo])
    if len(trazos) < TRAZOS_MINIMOS:
        return []
    resultado = []
    for grupo in _agrupar_cercanos(trazos, ancho * CERCANIA):
        if sum(1 for trazo in grupo if not trazo[4]) < TRAZOS_MINIMOS:
            continue
        x0 = min(t[0] for t in grupo)
        abajo = min(t[1] for t in grupo)
        x1 = max(t[2] for t in grupo)
        arriba = max(t[3] for t in grupo)
        area = max(0.0, x1 - x0) * max(0.0, arriba - abajo)
        if superficie and FIGURA_MINIMA <= area / superficie <= FIGURA_MAXIMA:
            resultado.append((x0, abajo, x1, arriba, True))
    return resultado


def _es_filete(ancho: float, alto: float) -> bool:
    """Indica si un trazo es una raya y no parte de un dibujo."""
    return min(abs(ancho), abs(alto)) <= GROSOR_FILETE


def _es_fondo(caja, alto_pagina: float, lineas: list) -> bool:
    """Indica si un trazo es el fondo de un texto y no parte de un dibujo.

    Un bloque de código, un recuadro de aviso o una fila sombreada se pintan
    como un rectángulo relleno con el texto encima.  Ese rectángulo no es una
    figura —no hay nada que ver en él—, y darlo por tal metía una imagen falsa
    en medio del documento, la anunciaba al leer y la ofrecía para describirla
    con la inteligencia artificial, que no habría sabido qué decir de un
    rectángulo gris.

    Se distingue de un dibujo de verdad por cuánto de su alto ocupa el texto de
    dentro, pero contando solo el que va **seguido**, renglón tras renglón como
    un párrafo.  Esa es justo la diferencia: los rótulos de un gráfico son
    líneas sueltas repartidas por una zona grande —una por cada marca del eje,
    con su hueco entre medias—, y sin pedir que vayan seguidas sumaban tanto
    como un bloque de texto y borraban gráficos de verdad.

    Se mide el alto y no la superficie porque un bloque de código son renglones
    cortos en una caja ancha, y por superficie no llegaría nunca.
    """
    x0, abajo, x1, arriba = caja
    altura = arriba - abajo
    if altura <= 0 or x1 <= x0:
        return False
    # Los trazos vienen con el origen abajo, como los guarda el PDF, y los
    # renglones con el origen arriba, como se ven: hay que darles la vuelta.
    techo, suelo = alto_pagina - arriba, alto_pagina - abajo
    dentro = sorted((rtop, rbottom) for _texto, rx0, rx1, rtop, rbottom in lineas
                    if rx0 >= x0 and rx1 <= x1
                    and rtop >= techo - 1.0 and rbottom <= suelo + 1.0)
    seguido = 0.0
    mayor = 0.0
    anterior = None
    for rtop, rbottom in dentro:
        if anterior is not None and rtop - anterior > max(1.0, rbottom - rtop):
            seguido = 0.0        # hay un hueco: empieza otra racha
        seguido += rbottom - rtop
        mayor = max(mayor, seguido)
        anterior = rbottom
    return mayor / altura >= COBERTURA_FONDO


def _agrupar_cercanos(trazos: list, distancia: float) -> list:
    """Junta en un mismo grupo los trazos que se tocan o casi.

    Es una unión por vecindad hecha a mano y en un solo sentido: se recorre en
    orden y cada trazo o amplía el último grupo con el que se solapa o abre uno
    nuevo.  No es el agrupamiento perfecto, pero es lineal y no necesita más:
    un gráfico es una mancha compacta de trazos, no una constelación.
    """
    if not trazos:
        return []
    trazos.sort(key=lambda t: (-t[3], t[0]))
    grupos: list[list] = []
    cajas: list[list] = []
    for trazo in trazos:
        for indice, caja in enumerate(cajas):
            if (trazo[0] <= caja[2] + distancia and trazo[2] >= caja[0] - distancia
                    and trazo[1] <= caja[3] + distancia and trazo[3] >= caja[1] - distancia):
                grupos[indice].append(trazo)
                caja[0] = min(caja[0], trazo[0])
                caja[1] = min(caja[1], trazo[1])
                caja[2] = max(caja[2], trazo[2])
                caja[3] = max(caja[3], trazo[3])
                break
        else:
            grupos.append([trazo])
            cajas.append(list(trazo))
    return grupos


def _sin_solapes(cajas: list) -> list:
    """Funde las figuras que se pisan, que son la misma vista dos veces.

    Un gráfico con una fotografía incrustada aparece dos veces: como imagen y
    como grupo de trazos.  Anunciarlo dos veces sería peor que no anunciarlo.
    """
    resultado: list = []
    for caja in sorted(cajas, key=lambda c: -(c[2] - c[0]) * (c[3] - c[1])):
        for previa in resultado:
            if (caja[0] < previa[2] and caja[2] > previa[0]
                    and caja[1] < previa[3] and caja[3] > previa[1]):
                break
        else:
            resultado.append(list(caja))
    return [tuple(caja) for caja in resultado]


#: Separación mínima entre dos filetes para que sean dos separadores y no la
#: rejilla de una tabla, en puntos.  Dos rayas a doce puntos una de otra son
#: dos renglones de una tabla; dos secciones no se separan así.
SEPARACION_FILETES = 40.0


def _separadores_utiles(alturas, contexto: "Contexto") -> list:
    """Deja solo los filetes que de verdad separan una sección de otra.

    Se quitan dos clases de rayas que no separan nada y que, sin quitarlas,
    llenaban de separadores un manual entero:

    * Las de la **cabecera y el pie**, que están a la misma altura en todas las
      páginas.  Son mobiliario, igual que el título repetido que ya se quitaba.
    * Las que van **muy juntas**, que son la rejilla de una tabla a la que no
      se le han reconocido los bordes.
    """
    sueltas = [altura for altura in alturas
               if "%.0f" % altura not in contexto.filetes]
    resultado = []
    for altura in sorted(sueltas):
        if resultado and altura - resultado[-1] < SEPARACION_FILETES:
            resultado.pop()
            continue
        resultado.append(altura)
    return resultado


def _figura_a_html(figura: Figura, numero: int) -> str:
    """Escribe una figura como la escribe el camino etiquetado.

    Se emite la misma referencia ``pdf-figura:`` que produce
    :mod:`formatos.pdf_etiquetado`, y por eso todo lo que ya existía funciona
    sin tocar nada: verla con ``Ctrl+I``, describirla con inteligencia
    artificial y que esa descripción se guarde y vuelva con el documento, igual
    que en un EPUB.  La referencia es el rectángulo que ocupa, no un archivo,
    porque un gráfico de un informe no es ninguna imagen: son decenas de trazos
    que hay que rasterizar juntos.

    El texto alternativo se deja **vacío** salvo que el pie diga algo de
    verdad.  No es un descuido: es lo que hace que el documento cuente esa
    imagen entre las que están sin describir y que la orden de describirlas
    todas la incluya.  Y por eso «Figura 7-26.» no cuenta como descripción: es
    una etiqueta, no dice qué se ve, y darla por buena dejaría esa figura fuera
    del alcance de la inteligencia artificial para siempre.  El pie se escribe
    igualmente como pie, que es donde va y donde se lee.
    """
    referencia = "pdf-figura:%d:%.2f,%.2f,%.2f,%.2f" % (
        numero, figura.caja[0], figura.caja[1], figura.caja[2], figura.caja[3])
    alternativo = figura.pie if _pie_descriptivo(figura.pie) else ""
    imagen = '<img src="%s" alt="%s"/>' % (_escapar(referencia), _escapar(alternativo))
    if not figura.pie:
        return imagen
    return "<figure>%s<figcaption>%s</figcaption></figure>" % (
        imagen, _escapar(figura.pie))


def _pie_descriptivo(pie: str) -> bool:
    """Indica si un pie describe la figura o solo la numera.

    «Figura 3» y «Fig. 7-26.» son rótulos: sirven para citarla desde el texto y
    no dicen absolutamente nada de lo que se ve.  Se les quita el rótulo y se
    mira si queda algo que merezca llamarse descripción.
    """
    resto = _SOLO_ROTULO.sub("", " ".join((pie or "").split())).strip(" .:-—–")
    return len(resto) >= 25 and len(resto.split()) >= 4


def _comentario_a_html(autor: str, texto: str) -> str:
    """Escribe un comentario del PDF como una nota al pie.

    Se marca como nota y no como párrafo porque eso es lo que es: algo que
    alguien añadió al margen y que no forma parte del texto.  Marcado así se
    puede saltar de un comentario a otro con la orden de notas, y no se
    confunde con lo que dice el documento.
    """
    from nucleo.idioma import _

    rotulo = _("Comentario de %s") % autor if autor else _("Comentario")
    return ('<aside class="footnote"><a class="noteref" href="#">%s</a>: %s</aside>'
            % (_escapar(rotulo), _escapar(texto)))


def _renglones_de(pagina) -> list:
    """Devuelve los renglones de la página como ``(texto, x0, x1, top, bottom)``.

    Se monta aparte de las palabras que usa el resto del módulo porque aquí
    solo hace falta para buscar pies de figura, y se necesita en coordenadas de
    pantalla y con los renglones ya juntos.
    """
    try:
        palabras = pagina.extract_words(
            keep_blank_chars=False, x_tolerance_ratio=SEPARACION_PALABRAS)
    except Exception:
        return []
    filas: dict[int, list] = {}
    for palabra in palabras:
        try:
            filas.setdefault(int(round(float(palabra["top"]) / 3.0)), []).append(palabra)
        except (KeyError, TypeError, ValueError):
            continue
    renglones = []
    for clave in sorted(filas):
        grupo = sorted(filas[clave], key=lambda p: float(p["x0"]))
        texto = " ".join(str(p.get("text") or "") for p in grupo).strip()
        if not texto:
            continue
        renglones.append((
            texto,
            min(float(p["x0"]) for p in grupo),
            max(float(p["x1"]) for p in grupo),
            min(float(p["top"]) for p in grupo),
            max(float(p["bottom"]) for p in grupo),
        ))
    return renglones


def _pie_de(renglones: list, x0: float, x1: float, arriba: float, abajo: float) -> str:
    """Busca el pie de una figura justo encima o justo debajo de ella.

    Un pie es un renglón corto, pegado a la figura, que empieza por una de las
    palabras con que se nombran las figuras («Figura 3», «Gráfico 2»).  Se
    exige esa palabra a propósito: sin ella, la primera línea del párrafo
    siguiente pasaría por pie de la figura anterior en todo el documento.
    """
    altura = 12.0
    mejor = ""
    for texto, texto_x0, texto_x1, texto_arriba, texto_abajo in renglones:
        if texto_x1 < x0 or texto_x0 > x1:
            continue
        distancia = min(abs(texto_arriba - abajo), abs(arriba - texto_abajo))
        if distancia > altura * DISTANCIA_PIE:
            continue
        limpio = " ".join(texto.split())
        if len(limpio) > 300:
            continue
        if limpio.casefold().startswith(_PIES):
            return limpio
    return mejor


def _zonas_ocupadas(tablas, figuras, alto: float) -> tuple:
    """Franjas verticales de la página que ya son una tabla o una figura.

    Sirven para no contar sus bordes como separadores de sección: la rejilla de
    una tabla son rayas finas y largas, exactamente lo que se busca, y sin
    apartarlas un documento con tablas salía lleno de separadores donde solo
    había líneas de tabla.
    """
    zonas = []
    for caja, _html in tablas or ():
        zonas.append((float(caja[1]), float(caja[3])))
    for figura in figuras or ():
        zonas.append((float(figura.arriba),
                      float(alto - figura.caja[1]) if alto else float(figura.arriba)))
    return tuple(zonas)


def _separadores_de_pagina(pagina, zonas=()) -> tuple:
    """Encuentra los filetes que separan unas secciones de otras.

    Se buscan entre las rayas finas y largas, y se dejan fuera las que caen
    dentro de una tabla o de una figura, que son sus bordes y no separan nada.
    Un filete de verdad es una decisión de maquetación que en un EPUB sería un
    ``<hr>``, y anunciarlo permite recorrer el documento por bloques con la
    orden de separadores.
    """
    ancho = float(getattr(pagina, "width", 0.0) or 0.0)
    alto = float(getattr(pagina, "height", 0.0) or 0.0)
    if ancho <= 0 or alto <= 0:
        return ()
    alturas = []
    for tipo in ("lines", "rects"):
        for trazo in getattr(pagina, tipo, None) or ():
            try:
                x0, x1 = float(trazo["x0"]), float(trazo["x1"])
                arriba, abajo = float(trazo["top"]), float(trazo["bottom"])
            except (KeyError, TypeError, ValueError):
                continue
            if abs(abajo - arriba) > GROSOR_FILETE:
                continue
            if (x1 - x0) < ancho * FILETE_LARGO:
                continue
            centro = (arriba + abajo) / 2.0
            if any(inicio - 2 <= centro <= final + 2 for inicio, final in zonas):
                continue
            alturas.append(round(centro, 1))
    # Las rejillas de una tabla son muchos filetes seguidos y no separan
    # secciones: si hay más de cuatro en la página, no son separadores.
    unicas = sorted(set(alturas))
    return tuple(unicas) if len(unicas) <= 4 else ()


def _comentarios_de_pagina(pagina) -> tuple:
    """Recoge las notas y comentarios que alguien haya dejado en el PDF.

    Un PDF revisado lleva notas adhesivas, subrayados con comentario y
    correcciones.  Son contenido de verdad —muchas veces el más importante de
    la página, porque es lo que alguien quería decir— y hasta ahora se perdían
    enteros: no forman parte del texto de la página, son anotaciones.

    :return: Tuplas ``(arriba, autor, texto)`` en coordenadas de pantalla.
    """
    resultado = []
    for anotacion in getattr(pagina, "annots", None) or ():
        try:
            contenido = " ".join(str(anotacion.get("contents") or "").split())
            if not contenido:
                continue
            resultado.append((
                float(anotacion.get("top") or 0.0),
                " ".join(str(anotacion.get("title") or "").split()),
                contenido[:2000],
            ))
        except (TypeError, ValueError):
            continue
    return tuple(sorted(resultado, key=lambda comentario: comentario[0]))


# ---------------------------------------------------------------------------
# Columnas de la página
# ---------------------------------------------------------------------------

#: Anchura mínima del pasillo entre columnas, en proporción de la página.  Por
#: debajo de esto no es un pasillo: es la sangría de un párrafo o el hueco
#: entre las celdas de una tabla.
PASILLO = 0.035

#: Anchura mínima de una columna, en proporción de la página.  Una franja más
#: estrecha que esto es un margen con una nota al lado, no una columna.
COLUMNA_MINIMA = 0.15

#: Palabras por renglón, como mínimo, para que una franja sea texto y no una
#: columna de tabla.  Es lo que distingue las dos cosas sin depender de lo ancha
#: que sea la página: un renglón de una columna de texto lleva media docena de
#: palabras porque es una frase partida; una celda lleva un dato —un nombre,
#: una cifra, una fecha—.  Sin esta comprobación, cualquier tabla sin líneas se
#: leería columna por columna, que es exactamente el error que hay que evitar.
PALABRAS_POR_RENGLON = 3

#: Cuántas columnas como mucho se reconocen.  Más de tres en una página de
#: texto no existe; lo que sí existe es una tabla de seis columnas que no
#: conviene tomar por una maquetación.
COLUMNAS_MAXIMAS = 3


def _partir_en_columnas(palabras, ancho: float):
    """Separa las columnas de texto de una página, si las hay.

    El caso que resuelve es el del artículo o el periódico a dos columnas.  El
    módulo de disposición ya corta la página en regiones, pero cuando las dos
    columnas tienen sus renglones a las mismas alturas —que es lo normal, porque
    comparten interlineado— las reconoce como una rejilla y las mantiene juntas.
    Para un folleto de productos eso es lo correcto; para un texto a dos
    columnas hace que se lea «Columna izquierda primera línea. Columna derecha
    primera línea.», saltando de una a otra en cada renglón.

    Se busca un **pasillo vertical vacío** de lado a lado de la mancha de texto
    y se comprueba que lo que queda a cada lado se comporta como texto: que sus
    renglones llenan la columna.  Si no lo hacen, es una tabla y no se toca.

    :return: ``(cortes, columnas)``.  Los cortes son las coordenadas donde se
             partió, para poder situar también las tablas; las columnas van en
             orden de lectura.  Sin columnas, ``((), [palabras])``.
    """
    if len(palabras) < 6 or ancho <= 0:
        return (), [list(palabras)]
    cortes = _pasillos(palabras, ancho)
    if not cortes or len(cortes) > COLUMNAS_MAXIMAS - 1:
        # Más de dos pasillos verticales en una página no es una maquetación a
        # columnas: es una tabla o un formulario.  Partir por ahí leería la
        # tabla columna por columna, que es el peor resultado posible.
        return (), [list(palabras)]
    grupos: list[list] = [[] for _ in range(len(cortes) + 1)]
    for palabra in palabras:
        grupos[_columna_de(palabra.x + palabra.ancho / 2.0, cortes)].append(palabra)
    grupos = [grupo for grupo in grupos if grupo]
    if len(grupos) < 2 or not all(_parece_texto(grupo) for grupo in grupos):
        return (), [list(palabras)]
    return cortes, grupos


def _pasillos(palabras, ancho: float) -> tuple:
    """Busca las verticales por las que se puede partir la página.

    Se marca cada punto horizontal que alguna palabra ocupa y se buscan los
    tramos libres suficientemente anchos.  Los tramos pegados a los bordes son
    los márgenes de la página y no separan nada, así que se descartan.
    """
    izquierda = min(p.x for p in palabras)
    derecha = max(p.derecha for p in palabras)
    if derecha - izquierda < ancho * 0.4:
        # La mancha de texto no llega ni a media página: no hay columnas que
        # separar, hay una sola estrecha.
        return ()
    ocupado = bytearray(int(derecha - izquierda) + 2)
    for palabra in palabras:
        inicio = max(0, int(palabra.x - izquierda))
        fin = min(len(ocupado) - 1, int(palabra.derecha - izquierda))
        for punto in range(inicio, fin + 1):
            ocupado[punto] = 1
    minimo = max(ancho * PASILLO, 10.0)
    cortes: list[float] = []
    inicio_hueco = None
    for punto, lleno in enumerate(ocupado):
        if not lleno:
            if inicio_hueco is None:
                inicio_hueco = punto
            continue
        if inicio_hueco is not None:
            if punto - inicio_hueco >= minimo and inicio_hueco > 0:
                cortes.append(izquierda + (inicio_hueco + punto) / 2.0)
            inicio_hueco = None
    if not cortes:
        return ()
    bordes = [izquierda, *cortes, derecha]
    anchura_minima = ancho * COLUMNA_MINIMA
    if any(bordes[indice + 1] - bordes[indice] < anchura_minima
           for indice in range(len(bordes) - 1)):
        return ()
    return tuple(cortes)


#: Largo, en caracteres, a partir del cual un renglón deja de poder ser una
#: fila de tabla.  Una celda es un dato: un nombre, una cifra, una fecha.  Un
#: renglón de trescientos caracteres es prosa, y escribirlo como fila hace que
#: el lector de pantalla anuncie «tabla, fila 1, columna 1» delante de un
#: párrafo entero.
LARGO_CELDA = 250


def _tabla_creible(lineas) -> bool:
    """Descarta las rejillas que en realidad son texto corrido.

    El corte recursivo reconoce una rejilla porque las columnas tienen sus
    filas a las mismas alturas, y eso lo cumple también una página donde un
    gráfico convive con una lista de cifras: el resultado es una «tabla» con
    una celda de cuatrocientos caracteres.  Se comprueba antes de escribirla.
    """
    return bool(lineas) and all(len(linea.texto) <= LARGO_CELDA for linea in lineas)


def _margen_de_columna(palabras, contexto: "Contexto") -> float:
    """Dónde empieza el texto de una columna concreta.

    Se toma el punto donde arrancan más renglones, que es el margen, y no el
    más a la izquierda de todos, que sería el de un número de lista o el de un
    título colgado.  Si la columna es la única de la página se conserva el
    margen del documento, que está medido sobre muchas más páginas y por tanto
    es más fiable que el de una sola.
    """
    if not palabras:
        return contexto.margen
    renglones: dict[int, float] = {}
    for palabra in palabras:
        clave = int(palabra.y / 3)
        renglones[clave] = min(renglones.get(clave, palabra.x), palabra.x)
    if len(renglones) < 3:
        return contexto.margen
    cuenta: dict[int, int] = {}
    for inicio in renglones.values():
        redondeado = int(round(inicio))
        cuenta[redondeado] = cuenta.get(redondeado, 0) + 1
    moda = float(max(cuenta, key=lambda clave: (cuenta[clave], -clave)))
    # Si el margen del documento cae dentro de esta columna, manda él: está
    # medido sobre veinticuatro páginas y no sobre una.
    if contexto.margen and abs(contexto.margen - moda) <= SANGRIA_CITA:
        return contexto.margen
    return moda


def _columna_de(x: float, cortes) -> int:
    """Dice a qué columna pertenece una coordenada horizontal."""
    return sum(1 for corte in cortes if x > corte)


def _parece_texto(palabras) -> bool:
    """Comprueba que un grupo de palabras se lee como texto y no como tabla.

    Se cuenta cuántas palabras hay por renglón.  Es una medida que no depende
    del tamaño de la página ni de lo ancha que sea la columna, y separa
    limpiamente los dos casos: una columna de texto son frases partidas y sus
    renglones llevan media docena de palabras; una columna de tabla lleva un
    dato por celda.
    """
    renglones: dict[int, int] = {}
    for palabra in palabras:
        clave = int(palabra.y / 3)
        renglones[clave] = renglones.get(clave, 0) + 1
    if len(renglones) < 3:
        return False
    return median(renglones.values()) >= PALABRAS_POR_RENGLON


# ---------------------------------------------------------------------------
# Encabezados, listas y párrafos
# ---------------------------------------------------------------------------

def _bloque_a_html(lineas, pagina: PaginaGeometrica, contexto: "Contexto") -> str:
    """Escribe un bloque de texto corrido decidiendo qué es cada renglón."""
    partes: list[str] = []
    parrafo: list[str] = []
    lista: list[str] = []
    codigo: list[tuple] = []
    ordenada = False
    sangrado = _bloque_sangrado(lineas, contexto)
    notas = _notas_al_pie(lineas, pagina, contexto)

    def cerrar_codigo() -> None:
        """Vuelca el bloque de código acumulado, con sus renglones y su sangría."""
        if codigo:
            partes.append(_codigo_a_html(codigo))
            codigo.clear()

    def cerrar_parrafo() -> None:
        """Vuelca el párrafo acumulado, uniendo palabras partidas por guion."""
        if parrafo:
            etiqueta = "blockquote" if sangrado else "p"
            partes.append("<%s>%s</%s>" % (etiqueta, _unir(parrafo), etiqueta))
            parrafo.clear()

    def cerrar_lista() -> None:
        """Vuelca la lista acumulada con la etiqueta que le corresponde."""
        if lista:
            etiqueta = "ol" if ordenada else "ul"
            partes.append("<%s>%s</%s>" % (
                etiqueta,
                "".join("<li>%s</li>" % punto for punto in lista),
                etiqueta))
            lista.clear()

    for linea in lineas:
        texto = " ".join(linea.texto.split())
        if not texto or normalizar(texto) in contexto.artefactos:
            continue
        estilo = _estilo_de(linea, pagina)
        if _es_codigo(texto, estilo, contexto):
            # El código va antes que todo lo demás: sus renglones no son
            # párrafo —unirlos con espacios convierte diez sentencias en una
            # frase ilegible—, ni lista aunque empiecen por un número, ni
            # encabezado aunque sean cortos.
            cerrar_parrafo()
            cerrar_lista()
            codigo.append((float(linea.x), _escapar(texto), _ancho_de_letra(linea)))
            continue
        cerrar_codigo()
        marcado = _texto_con_enlaces(linea, pagina, notas)
        ancla = notas.cuerpos.get(id(linea))
        if ancla:
            cerrar_parrafo()
            cerrar_lista()
            partes.append('<aside class="footnote" id="%s">%s</aside>' % (ancla, marcado))
            continue
        punto = _LISTA.match(texto)
        if punto:
            cerrar_parrafo()
            marca = punto.group("marca")
            nueva = marca[0] not in _VINETAS
            if lista and nueva != ordenada:
                cerrar_lista()
            ordenada = nueva
            lista.append(_sin_marca(marcado, marca))
            continue
        cerrar_lista()
        nivel = _nivel_encabezado(texto, estilo, contexto)
        if nivel:
            cerrar_parrafo()
            partes.append("<h%d>%s</h%d>" % (nivel, marcado, nivel))
            continue
        parrafo.append((texto, marcado))
    cerrar_parrafo()
    cerrar_lista()
    cerrar_codigo()
    return "".join(partes)


#: Viñetas que descartan un renglón como código.  El asterisco no está: en un
#: renglón de código es un operador o un puntero, no el punto de una lista.
_VINETA_DE_LISTA = tuple(v for v in _VINETAS if v != "*")


def _es_codigo(texto: str, estilo: Estilo, contexto: "Contexto") -> bool:
    """Indica si un renglón está escrito entero en letra de máquina de escribir.

    Se mira el estilo **dominante** del renglón, así que una frase normal con
    un nombre de función dentro no cuenta: lo que cuenta es un renglón que es
    código de principio a fin.

    Un punto de lista no lo es aunque vaya en esa letra: en un manual técnico
    hay listas cuyos puntos son casi todo rutas y opciones, y darlas por código
    las dejaba sin marcar como lista.
    """
    if not estilo.fuente or estilo.fuente not in contexto.monoespaciadas:
        return False
    return not texto.startswith(_VINETA_DE_LISTA)


def _ancho_de_letra(linea) -> float:
    """Lo que ocupa una letra en un renglón de letra de máquina de escribir.

    Se mide palabra a palabra y se toma la mediana, no del renglón entero: los
    huecos entre palabras de un renglón de código pueden ser varios espacios
    seguidos, y dividir el ancho total por las letras daría una letra más
    gorda de lo que es.
    """
    medidas = [palabra.ancho / len(palabra.texto)
               for palabra in linea.palabras if palabra.texto]
    return float(median(medidas)) if medidas else 0.0


def _codigo_a_html(renglones: list) -> str:
    """Escribe un bloque de código conservando sus renglones y su sangría.

    Las dos cosas son contenido, no presentación.  Un bloque de código leído
    como un párrafo dice «jump(-60) n = 7 radius = 60», que no es lo que pone;
    y la sangría, en Python, **es** la sintaxis: sin ella no se sabe qué hay
    dentro de un bucle y qué hay fuera.

    En el PDF no hay espacios de sangría —lo que hay es una coordenada—, así
    que se reconstruyen midiendo cuánto se aparta cada renglón del que más a la
    izquierda empieza y dividiéndolo por lo que ocupa una letra, que en esta
    clase de letra es siempre lo mismo.

    Los renglones se separan con ``<br/>`` porque es lo que el conversor
    entiende como final de renglón; dentro de un ``<pre>`` conserva además los
    espacios del principio tal cual.
    """
    izquierda = min(x for x, _texto, _ancho in renglones)
    anchos = [ancho for _x, _texto, ancho in renglones if ancho > 0]
    letra = float(median(anchos)) if anchos else 0.0
    escritos = []
    for x, texto, _ancho in renglones:
        sangria = int(round((x - izquierda) / letra)) if letra > 0 else 0
        escritos.append(" " * max(0, sangria) + texto)
    return "<pre>%s</pre>" % "<br/>".join(escritos)


#: Cuánto tiene que sangrarse un bloque respecto al margen del documento para
#: darlo por cita, en puntos.  Una sangría de primera línea son 12 o 18; una
#: cita en bloque se aparta bastante más, y pedir 30 evita confundirlas.
SANGRIA_CITA = 30.0


def _bloque_sangrado(lineas, contexto: "Contexto") -> bool:
    """Indica si un bloque está apartado del margen, es decir, si es una cita.

    Una cita en bloque no está marcada en ninguna parte: lo único que la
    distingue de un párrafo es que **todo** el bloque empieza más a la derecha.
    Se piden tres cosas a la vez, y las tres hacen falta:

    * Que **todos** sus renglones estén sangrados, no solo el primero: un
      renglón suelto sangrado es la primera línea de un párrafo normal, y darlo
      por cita convertiría en cita medio documento.
    * Que sean **al menos dos**, por lo mismo.
    * Que el bloque **sea prosa**: que sus renglones lleven varias palabras.
      Sin esta condición, la columna de cifras de una tabla —que también
      empieza muy a la derecha y también tiene varios renglones— se marcaba
      como cita, y en un documento con datos salían decenas.
    """
    if not contexto.margen or len(lineas) < 2:
        return False
    if not all(linea.x - contexto.margen >= SANGRIA_CITA for linea in lineas):
        return False
    palabras = [len(linea.palabras) for linea in lineas]
    return median(palabras) >= PALABRAS_POR_RENGLON


def _estilo_de(linea, pagina: PaginaGeometrica) -> Estilo:
    """Devuelve el estilo dominante de un renglón.

    Dominante y no medio: si un párrafo lleva dos palabras en negrita, la línea
    no es negrita.  Se pesa por longitud de palabra, que es lo que se ve.
    """
    tamanos: list[float] = []
    fuentes: dict[str, int] = {}
    negritas = 0
    cursivas = 0
    letras = 0
    for palabra in linea.palabras:
        estilo = pagina.estilos.get(_clave(palabra))
        if estilo is None:
            continue
        cuantas = max(1, len(palabra.texto))
        letras += cuantas
        if estilo.tamano > 0:
            tamanos.append(estilo.tamano)
        if estilo.fuente:
            fuentes[estilo.fuente] = fuentes.get(estilo.fuente, 0) + cuantas
        if estilo.negrita:
            negritas += cuantas
        if estilo.cursiva:
            cursivas += cuantas
    if not letras:
        return Estilo(0.0, False, False, "")
    # La fuente dominante decide, igual que la negrita: un párrafo con dos
    # palabras de código dentro sigue siendo un párrafo, no un trozo de código.
    return Estilo(
        tamano=float(median(tamanos)) if tamanos else 0.0,
        negrita=negritas * 2 > letras,
        cursiva=cursivas * 2 > letras,
        fuente=max(fuentes, key=lambda nombre: fuentes[nombre]) if fuentes else "",
    )


def _nivel_encabezado(texto: str, estilo: Estilo, contexto: "Contexto") -> int:
    """Decide si un renglón es un encabezado y de qué nivel.  ``0`` si no lo es.

    Se exige que sea corto y que no acabe como acaba una frase, porque un
    párrafo entero escrito en grande —una cita destacada, un resumen inicial—
    no es un título aunque lo parezca por el tamaño.

    El nivel se decide por dos caminos, y el orden entre ellos no es capricho:

    1. **La numeración**, si la hay.  Quien escribió «3.2.1 Resultados» ya dijo
       que era un nivel tres; ninguna medida va a saberlo mejor.
    2. **El sitio del tamaño en la escala del documento**
       (:func:`_escala_de_encabezados`), que da niveles consecutivos y sin
       saltos.

    Y solo si no hay escala se cae en comparar contra el cuerpo por tramos, que
    es lo que produce huecos en la jerarquía y por eso es el último recurso.
    """
    cuerpo = contexto.cuerpo
    if len(texto) > LARGO_ENCABEZADO or texto.endswith(_FIN_DE_FRASE[:2]):
        return 0
    numerado = _NUMERADO.match(texto)
    grande = bool(cuerpo > 0 and estilo.tamano >= cuerpo * SALTO_ENCABEZADO)
    if numerado and (grande or estilo.negrita):
        return min(6, numerado.group("numero").count(".") + 1)
    if not grande:
        # La negrita sola no basta: en un texto corrido hay frases enteras en
        # negrita que no son títulos.  Con negrita y además corto, sí.  El
        # nivel es el último de la escala más uno, para que un titulillo en
        # negrita quede por debajo de los títulos de verdad y no compita con
        # ellos en la navegación por niveles.
        if estilo.negrita and len(texto) <= 80 and not texto.endswith(_FIN_DE_FRASE):
            return min(6, len(contexto.escala) + 1) if contexto.escala else 3
        return 0
    nivel = _nivel_en_escala(estilo.tamano, contexto.escala)
    if nivel:
        return nivel
    razon = estilo.tamano / cuerpo if cuerpo else 0.0
    for limite, tramo in NIVELES:
        if razon >= limite:
            return tramo
    return 4


def _nivel_en_escala(tamano: float, escala: tuple) -> int:
    """Busca a qué peldaño de la escala del documento pertenece un tamaño.

    Se admite medio punto de holgura por lado: el mismo estilo puede medir
    13,98 en una página y 14,03 en otra según cómo se escalara, y si eso
    contara como dos niveles distintos la jerarquía saldría inventada.
    """
    for indice, peldano in enumerate(escala):
        if abs(tamano - peldano) <= 0.5:
            return min(6, indice + 1)
    return 0


def _unir(renglones: list) -> str:
    """Une los renglones de un parrafo deshaciendo los cortes de linea.

    Un guion al final de renglon seguido de minuscula es una palabra partida
    por el ancho de la caja, no un guion del autor: se une y se lee entera, que
    es lo que hace la diferencia entre oir «informacion» y oir «infor» y luego
    «macion».

    Cada renglon llega dos veces, en texto plano y ya marcado con sus enlaces.
    La decision de unir o separar se toma **sobre el texto plano**, porque
    mirar el marcado obligaria a distinguir un guion del final de una etiqueta;
    lo que se concatena es el marcado, que es lo que se escribe.
    """
    plano = ""
    resultado = ""
    for texto, marcado in renglones:
        if not resultado:
            plano, resultado = texto, marcado
            continue
        if (plano.endswith("-") and len(plano) > 2
                and plano[-2].isalpha() and texto[:1].islower()):
            plano = plano[:-1] + texto
            resultado = _quitar_guion_final(resultado) + marcado
        else:
            plano = "%s %s" % (plano, texto)
            resultado = "%s %s" % (resultado, marcado)
    return resultado


def _quitar_guion_final(marcado: str) -> str:
    """Quita el guion de corte de linea sin romper una etiqueta abierta."""
    posicion = marcado.rfind("-")
    if posicion < 0 or ">" in marcado[posicion:]:
        return marcado
    return marcado[:posicion] + marcado[posicion + 1:]


def _sin_marca(marcado: str, marca: str) -> str:
    """Quita del marcado la vineta o el ordinal, que ya lo pone la lista.

    Se busca en el texto visible y no a ciegas por longitud: si la vineta
    estuviera dentro de un enlace —cosa rara pero posible—, cortar por posicion
    partiria la etiqueta por la mitad.
    """
    posicion = marcado.find(marca)
    if posicion < 0 or "<" in marcado[:posicion]:
        return marcado
    return marcado[posicion + len(marca):].strip()


class Notas(NamedTuple):
    """Las notas al pie de una página, con su cuerpo y sus llamadas.

    :param cuerpos: Renglón del pie de página (por su identidad) → ancla con la
                    que se le llama.
    :param numeros: Número de la nota → esa misma ancla, para poder marcar la
                    llamada que aparece volada en el texto.
    """

    cuerpos: dict
    numeros: dict


#: Notas vacías, para las páginas que no tienen ninguna.
SIN_NOTAS = Notas({}, {})

#: Franja inferior de la página donde viven las notas al pie, en proporción de
#: la altura.  Una nota al pie está al pie: más arriba de esto es texto normal.
FRANJA_NOTAS = 0.30

#: Cuánto más pequeña que el cuerpo tiene que ser la letra de una nota al pie.
#: Las notas se componen siempre en un cuerpo menor; sin esta condición, el
#: último párrafo de cada página pasaría por nota.
TAMANO_NOTA = 0.92

#: Cuánto más pequeña que el cuerpo es la letra de una llamada volada.
TAMANO_LLAMADA = 0.8

#: Renglón que empieza por el número o el símbolo de una nota al pie.
_INICIO_NOTA = re.compile(r"^\s*(?P<marca>\d{1,3}|[*†‡§¶])[.)\]]?\s+(?P<texto>\S.*)$")


def _notas_al_pie(lineas, pagina: PaginaGeometrica, contexto: "Contexto") -> Notas:
    """Encuentra las notas al pie de una página y con qué número se llaman.

    Una nota al pie no está marcada en ninguna parte de un PDF sin etiquetar:
    es un párrafo más, y lo único que la delata es **dónde está y cómo está
    escrita**.  Se piden las tres cosas a la vez, porque cada una por separado
    se equivoca: abajo del todo (ahí está el pie de página), con letra más
    pequeña que el cuerpo (ahí están los créditos de una figura) y empezando
    por un número o un asterisco (ahí empieza cualquier lista numerada).

    Reconocerlas cambia dos cosas: dejan de leerse como si fueran la
    continuación del último párrafo —que es lo que pasaba, y descoloca— y se
    pueden recorrer con la orden de notas, como en un EPUB.
    """
    if not contexto.cuerpo or pagina.alto <= 0:
        return SIN_NOTAS
    limite = pagina.alto * (1.0 - FRANJA_NOTAS)
    cuerpos: dict = {}
    numeros: dict = {}
    for linea in lineas:
        if linea.y < limite:
            continue
        coincidencia = _INICIO_NOTA.match(" ".join(linea.texto.split()))
        if not coincidencia:
            continue
        estilo = _estilo_de(linea, pagina)
        if not (0 < estilo.tamano <= contexto.cuerpo * TAMANO_NOTA):
            continue
        marca = coincidencia.group("marca")
        ancla = "nota-%d-%s" % (pagina.numero, re.sub(r"\W", "", marca) or str(len(cuerpos) + 1))
        cuerpos[id(linea)] = ancla
        numeros[marca] = ancla
    return Notas(cuerpos, numeros) if cuerpos else SIN_NOTAS


def _texto_con_enlaces(linea, pagina: PaginaGeometrica,
                       notas: "Notas" = SIN_NOTAS) -> str:
    """Escribe el texto de un renglón con sus enlaces, énfasis y llamadas.

    Tres cosas que en un PDF sin etiquetar no están en el texto y que en un
    EPUB sí, y que son las que faltaban para poder recorrerlo igual:

    * **Los enlaces** no son texto: son cajas dibujadas encima de la página.
      Se mira qué palabras caen debajo de cada caja y se envuelven juntas las
      que van seguidas y comparten destino, para que salga un enlace y no una
      palabra enlazada por cada palabra.
    * **La negrita y la cursiva** están en el nombre de la fuente de cada
      palabra.  Solo se marcan cuando distinguen un trozo del resto del
      renglón: un título entero en negrita no lleva negrita dentro, porque
      entonces la marca no señalaría nada.
    * **Las llamadas de nota** son números volados, más pequeños que el
      cuerpo.  Marcadas, la orden de notas salta a la nota; sin marcar, se
      leen pegadas a la palabra anterior y parecen parte de ella.
    """
    grupos: list = []
    for palabra in linea.palabras:
        estilo = pagina.estilos.get(_clave(palabra))
        clave = (
            _enlace_de(palabra, pagina.enlaces),
            bool(estilo and estilo.negrita),
            bool(estilo and estilo.cursiva),
        )
        if grupos and grupos[-1][0] == clave:
            grupos[-1][1].append(palabra)
        else:
            grupos.append((clave, [palabra]))
    # Si todo el renglón comparte estilo, ese estilo es del renglón y no de un
    # trozo suyo: marcarlo entero sería anunciar una negrita en cada línea de
    # un documento compuesto en negrita.
    uniforme = len({(clave[1], clave[2]) for clave, _p in grupos}) <= 1
    tamano_linea = _estilo_de(linea, pagina).tamano
    partes = []
    for (destino, negrita, cursiva), palabras in grupos:
        texto = _con_llamadas(palabras, pagina, notas, tamano_linea)
        if destino:
            texto = '<a href="%s">%s</a>' % (_escapar(destino), texto)
        elif not uniforme:
            if negrita:
                texto = "<strong>%s</strong>" % texto
            if cursiva:
                texto = "<em>%s</em>" % texto
        partes.append(texto)
    return " ".join(parte for parte in partes if parte).strip()


def _con_llamadas(palabras, pagina: PaginaGeometrica, notas: "Notas",
                  tamano_linea: float) -> str:
    """Escapa un grupo de palabras marcando las llamadas de nota que lleve.

    La referencia con la que se decide si un número está volado es el tamaño
    del **renglón**, no el del grupo: un grupo puede ser justamente la llamada,
    y compararla consigo misma nunca la encontraría.
    """
    partes = []
    for palabra in palabras:
        ancla = ""
        if notas.numeros and palabra.texto.strip("[]()").isdigit():
            estilo = pagina.estilos.get(_clave(palabra))
            if estilo and 0 < estilo.tamano <= tamano_linea * TAMANO_LLAMADA:
                ancla = notas.numeros.get(palabra.texto.strip("[]()"), "")
        if ancla:
            partes.append('<a class="noteref" href="#%s">%s</a>'
                          % (_escapar(ancla), _escapar(palabra.texto)))
        else:
            partes.append(_escapar(palabra.texto))
    return " ".join(partes)



def _enlace_de(palabra, enlaces) -> str:
    """Devuelve el destino del enlace bajo una palabra, si lo hay.

    Se comprueba con el **centro** de la palabra y no con su caja entera: las
    cajas de enlace suelen quedarse cortas por un par de puntos respecto al
    texto que subrayan, y exigir que la contengan del todo dejaria fuera la
    primera y la ultima palabra de casi todos los enlaces.
    """
    x = palabra.x + palabra.ancho / 2.0
    y = palabra.y + palabra.alto / 2.0
    for izquierda, arriba, derecha, abajo, destino in enlaces:
        if izquierda <= x <= derecha and arriba <= y <= abajo:
            return destino
    return ""


def _escapar(texto: str) -> str:
    """Deja un texto listo para meterlo en el XHTML que se genera."""
    return (texto.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))
