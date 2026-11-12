# -*- coding: utf-8 -*-
"""Prompts para describir imágenes, agrupados por tipo de libro.

Una misma imagen se describe de forma muy distinta según lo que sea el libro:
en una novela interesa la escena y el ambiente; en un manual técnico, lo que
el diagrama explica; en un cómic, quién aparece en cada viñeta y qué dice.
Por eso la instrucción que se le da a la IA es elegible, y no una sola fija.

Hay dos clases de prompts:

* Los **predefinidos** (:data:`PREDEFINIDOS`), que vienen con el programa.  Se
  pueden leer y duplicar, pero no editar ni borrar: son la red de seguridad a
  la que se vuelve si los propios acaban dando mal resultado.
* Los **propios**, que el usuario crea —a menudo duplicando uno predefinido y
  retocándolo— y que se guardan en las preferencias.

Uno de todos ellos es el **preferido**, y es el que se usa cuando se pide una
descripción sin elegir ninguno, que es el caso de la tecla rápida.
"""

from __future__ import annotations

from ..idioma import _
from typing import NamedTuple

#: Instrucción común a todos los prompts.  Se antepone siempre para que la
#: respuesta sirva tal cual: sin preámbulos («Claro, aquí tienes...»), sin
#: markdown y en español, que es lo que hace falta para leerla en voz alta.
#: Cabecera que se antepone a cualquier prompt.  El idioma **no está escrito
#: aquí**: se interpola el de la interfaz, de modo que quien tenga el programa
#: en inglés reciba las descripciones en inglés.  Antes pedía español siempre, y
#: era la única parte del programa que se quedaba sin traducir de verdad: el
#: texto de la interfaz cambiaba y lo que decía la IA, no.
CABECERA = _(
    "Eres un asistente que describe imágenes de libros para personas ciegas, que van a "
    "escuchar tu respuesta con un lector de pantalla. Responde SIEMPRE en %(idioma)s, en "
    "texto corrido, sin markdown, sin viñetas, sin encabezados y sin ninguna introducción "
    "del tipo «Claro» o «Aquí tienes»: empieza directamente por la descripción.")


def cabecera() -> str:
    """La cabecera con el idioma de la interfaz ya puesto."""
    from ..idioma import nombre_activo

    return CABECERA % {"idioma": nombre_activo()}


class Prompt(NamedTuple):
    """Una instrucción con nombre.

    :param identificador: Clave estable con la que se guarda cuál es el
                          preferido.  En los propios se genera al crearlos.
    :param nombre: Cómo se ve en la lista.
    :param texto: La instrucción en sí, sin la :data:`CABECERA`.
    :param predefinido: Si viene con el programa (no se puede borrar).
    """

    identificador: str
    nombre: str
    texto: str
    predefinido: bool = False


#: Prompts que vienen con el programa, ordenados de más general a más
#: especializado.  El primero es el que se usa mientras el usuario no elija.
PREDEFINIDOS: tuple[Prompt, ...] = (
    Prompt(
        "general", _("General (cualquier documento)"),
        _("Describe esta imagen de un libro con detalle suficiente para entenderla sin verla: "
        "qué se ve, quién o qué aparece, qué está ocurriendo y en qué entorno. Si hay texto "
        "legible dentro de la imagen, transcríbelo. Extensión: entre tres y seis frases."),
        True),
    Prompt(
        "breve", _("Breve (una o dos frases)"),
        _("Describe esta imagen en una o dos frases, quedándote solo con lo esencial. Sirve para "
        "hacerse una idea rápida sin interrumpir la lectura."),
        True),
    Prompt(
        "novela", _("Novela y literatura"),
        _("Esta imagen ilustra una obra literaria. Describe la escena como lo haría el narrador: "
        "los personajes y su aspecto, la acción, el lugar y la época que sugiere, y el ambiente "
        "o la emoción que transmite. No interpretes la trama ni adelantes acontecimientos: "
        "limítate a lo que se ve."),
        True),
    Prompt(
        "tecnico", _("Libro técnico o científico"),
        _("Esta imagen pertenece a un libro técnico o científico. Explica qué representa y, sobre "
        "todo, qué información transmite: los elementos, cómo se relacionan entre sí, el sentido "
        "de las flechas o conexiones, y las etiquetas y unidades. Transcribe literalmente todo el "
        "texto que aparezca. Si es una gráfica, indica qué hay en cada eje y cuál es la tendencia."),
        True),
    Prompt(
        "grafico", _("Gráficos, tablas y diagramas"),
        _("Esta imagen es un gráfico, una tabla o un diagrama. Di primero de qué tipo es y qué "
        "compara. Después indica los ejes o las columnas con sus unidades, y los valores o "
        "proporciones principales con sus etiquetas. Termina con la conclusión que se saca de un "
        "vistazo. Transcribe los rótulos tal cual."),
        True),
    Prompt(
        "mapa", _("Mapas y planos"),
        _("Esta imagen es un mapa o un plano. Indica qué territorio o espacio representa, su "
        "orientación y su escala si aparecen, los lugares rotulados y cómo se sitúan unos "
        "respecto a otros, y el significado de la leyenda, los colores y los símbolos."),
        True),
    Prompt(
        "comic", _("Cómic y novela gráfica"),
        _("Esta imagen es una página o una viñeta de cómic. Recórrela en el orden de lectura "
        "(de arriba abajo y de izquierda a derecha). Para cada viñeta: quién aparece, qué hace y "
        "dónde. Transcribe los bocadillos indicando quién habla, y también los carteles y las "
        "onomatopeyas."),
        True),
    Prompt(
        "arte", _("Arte, fotografía e historia"),
        _("Esta imagen es una obra de arte o una fotografía histórica. Describe qué se representa, "
        "la composición (qué ocupa el primer plano y qué el fondo), la técnica y los colores "
        "dominantes, y los detalles con significado. Si reconoces la obra, el autor o la época, "
        "dilo, pero deja claro que es una suposición."),
        True),
    Prompt(
        "infantil", _("Libro infantil"),
        _("Esta imagen ilustra un libro infantil. Descríbela con palabras sencillas y tono cercano, "
        "como se lo contarías a un niño: quién sale, qué hace, de qué colores es y qué está "
        "pasando. Dos o tres frases cortas."),
        True),
    Prompt(
        "texto", _("Solo transcribir el texto (OCR)"),
        _("Transcribe literalmente TODO el texto que aparezca en esta imagen, respetando los saltos "
        "de línea y el orden de lectura. No describas la imagen ni añadas comentarios. Si no "
        "contiene ningún texto, responde exactamente: (La imagen no contiene texto)."),
        True),
)

#: Identificador del prompt que se usa mientras el usuario no elija otro.
POR_OMISION = PREDEFINIDOS[0].identificador


def desde_configuracion(configuracion) -> list[Prompt]:
    """Devuelve todos los prompts: primero los predefinidos y luego los propios.

    :param configuracion: Preferencias de donde salen los propios.
    """
    prompts = list(PREDEFINIDOS)
    for guardado in configuracion.obtener("ia_prompts", []) or []:
        try:
            prompts.append(Prompt(str(guardado["identificador"]), str(guardado["nombre"]),
                                  str(guardado["texto"]), False))
        except (KeyError, TypeError):
            continue   # una entrada estropeada no debe impedir usar las demás
    return prompts


def guardar_propios(configuracion, prompts) -> None:
    """Guarda en las preferencias los prompts propios (los predefinidos no)."""
    configuracion.establecer("ia_prompts", [
        {"identificador": p.identificador, "nombre": p.nombre, "texto": p.texto}
        for p in prompts if not p.predefinido
    ])


def buscar(prompts, identificador: str) -> Prompt | None:
    """Devuelve el prompt con ese identificador, o ``None`` si ya no existe."""
    for prompt in prompts:
        if prompt.identificador == identificador:
            return prompt
    return None


def preferido(configuracion) -> Prompt:
    """Devuelve el prompt elegido como preferido.

    Si el guardado ya no existe —porque el usuario borró el suyo— se vuelve al
    primero de los predefinidos en lugar de fallar.
    """
    prompts = desde_configuracion(configuracion)
    elegido = buscar(prompts, str(configuracion.obtener("ia_prompt_preferido", POR_OMISION)))
    return elegido or PREDEFINIDOS[0]


def identificador_libre(prompts, base: str = "propio") -> str:
    """Inventa un identificador que no choque con ninguno de los que ya hay."""
    usados = {p.identificador for p in prompts}
    numero = 1
    while "%s-%d" % (base, numero) in usados:
        numero += 1
    return "%s-%d" % (base, numero)


def texto_completo(prompt: Prompt, contexto: str = "") -> str:
    """Arma la instrucción definitiva que se le manda a la IA.

    :param prompt: Prompt elegido.
    :param contexto: Datos del libro y de la imagen (título, autor, la
                     descripción que ya trae el EPUB...).  Ayudan mucho: saber
                     que el libro es un manual de botánica cambia por completo
                     lo que la IA destaca de una lámina.
    """
    partes = [cabecera(), prompt.texto]
    if contexto:
        partes.append(_("Datos del libro y de la imagen, por si te sirven de contexto:\n") + contexto)
    return "\n\n".join(partes)
