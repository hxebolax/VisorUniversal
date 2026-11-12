# -*- coding: utf-8 -*-
"""Qué modelos de visión se ofrecen, y para qué sirve cada uno.

Para describir la ilustración de un libro o leer la tabla de un informe hace
falta un modelo **multimodal**: uno que además de escribir, vea.  Los hay a
cientos, y elegir entre ellos es justo lo que no puede pedírsele a quien solo
quiere que su lector le cuente las imágenes.

Esta lista es corta a propósito.  Son modelos que:

* **caben en un ordenador normal**, sin tarjeta gráfica: el más pequeño
  funciona con dos gigas de memoria libre;
* **están en la biblioteca de Ollama**, así que se instalan con una orden y sin
  buscar archivos sueltos por Internet;
* **sirven para lo que hace este programa**: describir ilustraciones y, sobre
  todo, **leer documentos** —tablas, gráficos, diagramas, letra escaneada—, que
  es donde la mayoría de los modelos pequeños fallan.

Cada uno lleva escrito para qué es bueno y qué pide, porque «2B» no le dice
nada a nadie y «funciona con 4 GB de memoria y tarda medio minuto por imagen»,
sí.

Los tamaños son los de la descarga que hace Ollama, redondeados.  La memoria
que se pide es la que hay que tener **libre**, no la del equipo.
"""

from __future__ import annotations

from typing import NamedTuple

from ..idioma import _


class ModeloVision(NamedTuple):
    """Un modelo de la lista, con lo que hace falta saber para elegirlo.

    :param etiqueta: Nombre con el que Ollama lo descarga (``ollama pull``).
    :param nombre: Cómo se enseña en la lista.
    :param descarga_mb: Cuánto ocupa la descarga, en megas.
    :param memoria_gb: Memoria libre que necesita para funcionar.
    :param recomendado: Si es el que se propone de entrada.
    :param fuerte_en: Para qué es bueno, en una línea.
    :param detalle: Explicación completa, la que se lee al elegirlo.
    """

    etiqueta: str
    nombre: str
    descarga_mb: int
    memoria_gb: float
    recomendado: bool
    fuerte_en: str
    detalle: str


#: Los modelos que se ofrecen, del más ligero al más exigente.  El orden es el
#: de la lista que ve el usuario, y está pensado así: quien no sepa qué elegir
#: se queda con el primero que le quepa, y ese orden hace que sea una elección
#: razonable.
MODELOS: tuple[ModeloVision, ...] = (
    ModeloVision(
        etiqueta="moondream",
        nombre=_("Moondream (el más ligero)"),
        descarga_mb=1700,
        memoria_gb=2.0,
        recomendado=False,
        fuerte_en=_("describir imágenes en equipos muy justos"),
        detalle=_(
            "El más pequeño de todos: funciona con dos gigas de memoria libre y "
            "responde rápido incluso sin tarjeta gráfica.\n\n"
            "Describe bien una fotografía o una ilustración, pero **no leas con él "
            "documentos escaneados**: la letra pequeña y las tablas se le dan mal. "
            "Es la opción para un equipo antiguo o con poca memoria, donde lo "
            "demás no cabría."),
    ),
    ModeloVision(
        etiqueta="granite3.2-vision",
        nombre=_("Granite Vision de IBM (documentos)"),
        descarga_mb=2400,
        memoria_gb=4.0,
        recomendado=True,
        fuerte_en=_("tablas, gráficos, diagramas y documentos escaneados"),
        detalle=_(
            "Está hecho **expresamente para entender documentos**: tablas, gráficos, "
            "infografías, diagramas y planos, que es justo lo que un lector de "
            "pantalla no puede contarte por su cuenta.\n\n"
            "Es el que se recomienda para este programa: con dos mil millones de "
            "parámetros cabe en cuatro gigas, va bien sin tarjeta gráfica y acierta "
            "en lo que aquí más se pide. Si solo vas a instalar uno, que sea este."),
    ),
    ModeloVision(
        etiqueta="qwen2.5vl:3b",
        nombre=_("Qwen 2.5 VL 3B (el que mejor lee sin tarjeta)"),
        descarga_mb=3200,
        memoria_gb=5.0,
        recomendado=False,
        fuerte_en=_("leer texto dentro de las imágenes"),
        detalle=_(
            "El mejor leyendo **texto dentro de una imagen** de todos los de su "
            "tamaño: facturas, formularios, recibos, capturas de pantalla y páginas "
            "escaneadas.\n\n"
            "Elígelo si lo que más haces es sacar el texto de documentos que llegan "
            "como fotografías. Pide algo más de memoria que Granite y tarda un poco "
            "más en un equipo sin tarjeta gráfica."),
    ),
    ModeloVision(
        etiqueta="gemma4:e2b-it-qat",
        nombre=_("Gemma 4 pequeño de Google (muchos idiomas)"),
        descarga_mb=4400,
        memoria_gb=5.0,
        recomendado=False,
        fuerte_en=_("leer y describir en cualquier idioma, sin tarjeta gráfica"),
        detalle=_(
            "Lo último de Google en la versión pensada para equipos modestos. "
            "Entiende más de ciento cuarenta idiomas, así que es el que mejor "
            "responde cuando el libro no está en español ni en inglés, y lee con "
            "soltura el texto de una página escaneada, una captura de pantalla o "
            "un gráfico.\n\n"
            "Es la versión **QAT**: se entrenó ya sabiendo que iba a comprimirse, "
            "de manera que ocupa poco más de cuatro gigas conservando la calidad "
            "del modelo entero. Cuenta con unos cinco gigas de memoria libre, "
            "aunque Google dice que puede apañarse con tres.\n\n"
            "Buena elección si lees en varios idiomas y no tienes tarjeta gráfica. "
            "En tablas y diagramas sigue acertando más Granite."),
    ),
    ModeloVision(
        etiqueta="llava-phi3",
        nombre=_("LLaVA Phi-3 (descripciones largas)"),
        descarga_mb=2900,
        memoria_gb=6.0,
        recomendado=False,
        fuerte_en=_("descripciones detalladas de ilustraciones"),
        detalle=_(
            "Cuenta las imágenes con más detalle y mejor redacción que los demás de "
            "su tamaño, lo que se agradece en una novela ilustrada o en un libro de "
            "arte.\n\n"
            "A cambio es más lento y con los documentos rinde peor que Granite o "
            "Qwen. Si lo tuyo son las ilustraciones y no las tablas, es el suyo."),
    ),
    ModeloVision(
        etiqueta="qwen2.5vl:7b",
        nombre=_("Qwen 2.5 VL 7B (el que mejor lee, con tarjeta)"),
        descarga_mb=6000,
        memoria_gb=10.0,
        recomendado=False,
        fuerte_en=_("sacar el texto de las imágenes, si hay tarjeta gráfica"),
        detalle=_(
            "El que mejor saca el texto de una imagen de toda la lista: gana a "
            "modelos mucho más grandes leyendo facturas, formularios, tablas "
            "cruzadas y letra manuscrita.\n\n"
            "Pide diez gigas libres y **una tarjeta gráfica decente**: sin ella "
            "funciona, pero cada imagen puede llevar varios minutos. Instálalo solo "
            "si tu equipo va sobrado."),
    ),
    ModeloVision(
        etiqueta="gemma4:12b-it-qat",
        nombre=_("Gemma 4 grande de Google (para tarjeta gráfica)"),
        descarga_mb=7300,
        memoria_gb=12.0,
        recomendado=False,
        fuerte_en=_("lo mejor con tarjeta gráfica, y trozos muy largos"),
        detalle=_(
            "El hermano mayor del Gemma 4 pequeño, para quien tenga una tarjeta "
            "gráfica con doce gigas. Con ella describe una imagen en segundos y "
            "entiende documentos difíciles —gráficos, diagramas, formularios— "
            "mejor que ningún otro de esta lista.\n\n"
            "Además abarca de una vez el doble de texto que los demás, lo que se "
            "nota al preguntar sobre un capítulo entero en lugar de sobre unos "
            "párrafos.\n\n"
            "También es versión QAT, comprimida sin perder calidad. **Sin tarjeta "
            "gráfica no lo instales**: cada imagen se iría a varios minutos."),
    ),
)

#: El que se propone cuando el usuario no elige.  Es el que mejor encaja con lo
#: que hace este programa: leer documentos.
POR_OMISION = "granite3.2-vision"


def por_etiqueta(etiqueta: str) -> ModeloVision | None:
    """Busca un modelo de la lista por su etiqueta de Ollama."""
    limpia = (etiqueta or "").strip()
    for modelo in MODELOS:
        if modelo.etiqueta == limpia:
            return modelo
    return None


def recomendado() -> ModeloVision:
    """El modelo que se propone de entrada."""
    return por_etiqueta(POR_OMISION) or MODELOS[0]


def caben_en(memoria_gb: float) -> list[ModeloVision]:
    """Modelos que funcionan con esa memoria libre, del más capaz al más ligero.

    Se ordena así y no al revés porque quien tiene memoria de sobra quiere el
    mejor que le quepa, y quien va justo solo va a ver uno o dos.
    """
    posibles = [modelo for modelo in MODELOS if modelo.memoria_gb <= memoria_gb]
    return sorted(posibles, key=lambda modelo: modelo.memoria_gb, reverse=True)


def resumen(modelo: ModeloVision) -> str:
    """Línea con la que se enseña un modelo en una lista.

    Lleva delante el nombre y detrás lo que pide, en ese orden: el lector de
    pantalla lee de izquierda a derecha y lo primero que hace falta saber es
    cuál es, no cuánto ocupa.
    """
    return _("%s — %s. Descarga %s, necesita %s de memoria libre.") % (
        modelo.nombre, modelo.fuerte_en,
        tamano_legible(modelo.descarga_mb), memoria_legible(modelo.memoria_gb))


def tamano_legible(megas: int) -> str:
    """«2,4 GB» o «700 MB», que es como se dice un tamaño."""
    if megas >= 1024:
        return _("%s GB") % ("%.1f" % (megas / 1024)).replace(".", ",")
    return _("%d MB") % megas


def memoria_legible(gigas: float) -> str:
    """«4 GB», sin decimales cuando no hacen falta."""
    if gigas == int(gigas):
        return _("%d GB") % int(gigas)
    return _("%s GB") % ("%.1f" % gigas).replace(".", ",")
