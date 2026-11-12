# -*- coding: utf-8 -*-
"""Que la inteligencia artificial revise la estructura que se dedujo.

Cuando el programa abre un PDF que no trae etiquetas, deduce su estructura
midiendo cómo está escrito: el tamaño de la letra, la fuente, la sangría, la
posición.  Acierta casi siempre, y cuando falla, falla de formas reconocibles:

* un índice cuyas líneas se toman por encabezados, y salen cincuenta títulos
  seguidos que no son capítulos;
* un pie de página que se repite y que se toma por un título de nivel uno;
* un título en dos renglones que sale como dos encabezados;
* un párrafo en cursiva que se toma por una cita.

Un modelo de lenguaje reconoce eso de un vistazo, y para hacerlo **no necesita
el texto del libro**: le basta con el esqueleto —«página 12, encabezado de nivel
2, “Resultados”; tabla de 4 por 7; tres párrafos»—.  Eso son unos pocos miles de
fichas para un libro entero, cuesta céntimos y no manda el contenido a ningún
sitio: solo los títulos, que son lo que hay que mirar.

La máquina propone, la persona dispone
--------------------------------------

Nada se aplica solo.  Lo que vuelve es **una lista de sospechas**, cada una con
lo que el modelo cree que pasa y qué debería ser en su lugar.  Quien lee decide
cuáles acepta, y las aceptadas se guardan por el camino que ya existía para
corregir a mano (``Control+Alt+C``, :mod:`nucleo.correcciones`), así que se
aplican al volver a abrir el documento y se pueden deshacer una a una.

Esto es deliberado y no es prudencia de más: una corrección automática que se
equivoque **esconde texto del libro**, y eso no se puede hacer sin permiso.
"""

from __future__ import annotations

import re

from ..idioma import _
from ..marcas import TipoMarca, es_encabezado, nivel_de_encabezado
from ..registro import obtener_registro

log = obtener_registro(__name__)

#: Cuántas líneas del esqueleto se mandan como mucho.  Un libro de mil
#: capítulos no cabe en una petición, y con las primeras seiscientas entradas
#: ya se ve si la deducción va bien o va mal.
LINEAS_MAXIMAS = 600

#: Cuánto se recorta cada título en el esqueleto.  Lo que hay que juzgar es si
#: eso es un título, y para eso sobra con el principio.
TITULO_MAXIMO = 90

#: Qué se le pide al modelo.  Es minucioso en el formato porque lo que vuelve
#: hay que poder leerlo con un programa, y en el criterio porque un modelo al
#: que se le pide que busque fallos encuentra fallos aunque no los haya.
INSTRUCCION = _(
    "Eres un revisor de la estructura de documentos. Abajo va el esqueleto de un "
    "documento del que un programa ha deducido la estructura midiendo cómo está "
    "escrito. NO tienes el texto completo: solo los títulos y el tipo de cada bloque.\n\n"
    "Tu tarea es señalar SOLO lo que claramente está mal etiquetado. Estos son los "
    "fallos que se cometen:\n"
    "- Un índice o un sumario cuyas entradas se han tomado por encabezados.\n"
    "- Una cabecera o un pie de página repetidos que se han tomado por un título.\n"
    "- Un título partido en dos renglones que ha salido como dos encabezados.\n"
    "- Un nivel de encabezado que no encaja con los de alrededor.\n"
    "- Un número de página suelto tomado por un encabezado.\n\n"
    "Reglas de la respuesta:\n"
    "- Una línea por sospecha, con este formato exacto:\n"
    "  LINEA [número] | [artefacto, encabezado, parrafo o cita] | [nivel o 0] | [por qué]\n"
    "- El número es el de la línea del esqueleto, tal como va escrito abajo.\n"
    "- «artefacto» significa que eso no debería leerse (una cabecera repetida, un "
    "número de página suelto).\n"
    "- El nivel solo cuenta cuando dices «encabezado»; en los demás casos, 0.\n"
    "- El «por qué» es una frase corta, en %(idioma)s.\n"
    "- Si no ves nada claramente mal, responde exactamente: SIN CAMBIOS\n"
    "- No expliques nada más, no saludes y no resumas el documento.")

#: Una línea de la respuesta del modelo.
_RESPUESTA = re.compile(
    r"(?i)^\s*(?:l[ií]nea|line)\s*(\d+)\s*\|\s*([a-zé]+)\s*\|\s*(\d+)\s*\|\s*(.*)$")

#: Lo que responde cuando no ve nada que corregir.
SIN_CAMBIOS = "sin cambios"

#: Tipos que se aceptan en la respuesta.  Son los mismos que admite la
#: corrección a mano: lo que el modelo propone se guarda por ese camino y no
#: por otro nuevo.
TIPOS = ("artefacto", "encabezado", "parrafo", "cita")


class Entrada:
    """Una línea del esqueleto: qué es, qué dice y dónde está."""

    __slots__ = ("numero", "clase", "texto", "pagina", "posicion", "nivel")

    def __init__(self, numero: int, clase: str, texto: str, pagina: int,
                 posicion: int, nivel: int = 0) -> None:
        self.numero = numero
        self.clase = clase
        self.texto = texto
        self.pagina = pagina
        self.posicion = posicion
        self.nivel = nivel

    def linea(self) -> str:
        """Cómo se escribe esta entrada en el esqueleto que se manda."""
        sitio = "p%d" % self.pagina if self.pagina else "-"
        if self.texto:
            return "%d | %s | %s | %s" % (self.numero, sitio, self.clase,
                                          self.texto[:TITULO_MAXIMO])
        return "%d | %s | %s" % (self.numero, sitio, self.clase)


def esqueleto(documento) -> list[Entrada]:
    """Reduce el documento a la lista de sus bloques con estructura.

    Se toman los encabezados, las tablas, las listas, las citas y las figuras
    —lo que **tiene tipo**— y se cuentan los párrafos que hay entre unos y
    otros.  Los párrafos no se mandan uno a uno: su texto no hace falta para
    juzgar si un título es un título, y mandarlos multiplicaría por cien el
    coste sin añadir nada.
    """
    interesantes = {
        TipoMarca.TABLA: "tabla", TipoMarca.LISTA: "lista",
        TipoMarca.CITA: "cita", TipoMarca.FIGURA: "figura",
        TipoMarca.IMAGEN: "imagen", TipoMarca.CODIGO: "codigo",
    }
    marcas = []
    for marca in documento.marcas.todas():
        if es_encabezado(marca.tipo) or marca.tipo in interesantes:
            marcas.append(marca)
    marcas.sort(key=lambda marca: marca.posicion)

    entradas: list[Entrada] = []
    numero = 0
    anterior = 0
    for marca in marcas:
        if len(entradas) >= LINEAS_MAXIMAS:
            break
        parrafos = _parrafos_entre(documento, anterior, marca.posicion)
        if parrafos:
            numero += 1
            entradas.append(Entrada(numero, "%d parrafos" % parrafos, "",
                                    _pagina_de(documento, anterior), anterior))
        numero += 1
        if es_encabezado(marca.tipo):
            nivel = nivel_de_encabezado(marca.tipo)
            entradas.append(Entrada(numero, "h%d" % nivel,
                                    _limpio(marca.texto or _texto_en(documento, marca)),
                                    _pagina_de(documento, marca.posicion),
                                    marca.posicion, nivel))
        else:
            entradas.append(Entrada(numero, interesantes[marca.tipo],
                                    _limpio(marca.texto),
                                    _pagina_de(documento, marca.posicion),
                                    marca.posicion))
        anterior = _fin_del_bloque(documento, marca)
    return entradas


def _fin_del_bloque(documento, marca) -> int:
    """Dónde acaba una marca, para no contar su propia línea como párrafo.

    Un encabezado no guarda su longitud —ocupa la línea entera y el texto lo
    dice— así que avanzar un solo carácter dejaría el resto del título contado
    como un párrafo suelto detrás de cada título.
    """
    if marca.longitud > 0:
        return marca.posicion + marca.longitud
    final = documento.texto.find("\n", marca.posicion)
    return len(documento.texto) if final < 0 else final + 1


def _limpio(texto: str) -> str:
    """Un texto en una sola línea y sin espacios de más."""
    return " ".join((texto or "").split())


def _texto_en(documento, marca) -> str:
    """El texto de la línea donde empieza una marca."""
    try:
        return documento.texto_de_linea(marca.posicion)
    except Exception:                                # pragma: no cover
        return ""


def _parrafos_entre(documento, desde: int, hasta: int) -> int:
    """Cuántas líneas con texto hay entre dos posiciones."""
    if hasta <= desde:
        return 0
    trozo = documento.texto[desde:hasta]
    return sum(1 for linea in trozo.split("\n") if linea.strip())


def _pagina_de(documento, posicion: int) -> int:
    """En qué página cae una posición, o 0 si el documento no tiene páginas."""
    try:
        if not getattr(documento, "total_paginas", 0):
            return 0
        indice = documento.indice_de_pagina(posicion)
        if indice < 0:
            return 0
        marca = documento.marcas.grupo(TipoMarca.SALTO_PAGINA)[indice]
        rotulo = (marca.texto or "").strip()
        return int(rotulo) if rotulo.isdigit() else indice + 1
    except Exception:                                # pragma: no cover
        return 0


def texto_del_esqueleto(entradas: list[Entrada]) -> str:
    """El esqueleto tal como se le manda al modelo."""
    cabecera = _("Formato de cada línea: número | página | tipo | texto")
    return cabecera + "\n" + "\n".join(entrada.linea() for entrada in entradas)


class Sospecha:
    """Algo que el modelo cree que está mal etiquetado.

    :param entrada: La línea del esqueleto a la que se refiere.
    :param tipo: Qué dice que debería ser.
    :param nivel: Nivel del encabezado, cuando lo propone.
    :param motivo: Por qué lo dice, en una frase.
    """

    __slots__ = ("entrada", "tipo", "nivel", "motivo")

    def __init__(self, entrada: Entrada, tipo: str, nivel: int, motivo: str) -> None:
        self.entrada = entrada
        self.tipo = tipo
        self.nivel = nivel
        self.motivo = _limpio(motivo)

    def descripcion(self) -> str:
        """Cómo se enseña en la lista."""
        actual = self.entrada.clase
        propuesto = self.tipo
        if self.tipo == "encabezado" and self.nivel:
            propuesto = "h%d" % self.nivel
        return _("«%(texto)s»: ahora es %(actual)s y debería ser %(propuesto)s. "
                 "%(motivo)s") % {
            "texto": self.entrada.texto[:70] or _("(sin texto)"),
            "actual": actual, "propuesto": propuesto, "motivo": self.motivo}


def interpretar(respuesta: str, entradas: list[Entrada]) -> list[Sospecha]:
    """Convierte la respuesta del modelo en sospechas comprobadas.

    Se descarta todo lo que no encaje: una línea que no exista, un tipo que no
    se admita o una propuesta que no cambie nada.  Es la parte que impide que
    una respuesta creativa acabe convertida en correcciones sobre el documento.
    """
    if not respuesta:
        return []
    if SIN_CAMBIOS in respuesta.strip().lower()[:60]:
        return []
    por_numero = {entrada.numero: entrada for entrada in entradas}
    sospechas: list[Sospecha] = []
    vistos = set()
    for linea in respuesta.splitlines():
        encaje = _RESPUESTA.match(linea)
        if encaje is None:
            continue
        numero = int(encaje.group(1))
        tipo = encaje.group(2).lower().replace("á", "a").replace("é", "e")
        nivel = int(encaje.group(3))
        entrada = por_numero.get(numero)
        if entrada is None or tipo not in TIPOS or numero in vistos:
            continue
        if not entrada.texto:
            continue      # un recuento de párrafos no se puede corregir
        # Proponer lo que ya es no es una sospecha, es ruido.
        if tipo == "encabezado" and entrada.nivel == nivel:
            continue
        if tipo == "parrafo" and entrada.clase.startswith("h") is False:
            continue
        vistos.add(numero)
        sospechas.append(Sospecha(entrada, tipo, nivel, encaje.group(4)))
    log.info("La revisión de estructura ha devuelto %d sospechas", len(sospechas))
    return sospechas


def instruccion() -> str:
    """La instrucción con el idioma de la interfaz ya puesto."""
    from ..idioma import nombre_activo

    return INSTRUCCION % {"idioma": nombre_activo()}


def revisar(servicio, documento) -> tuple[list[Sospecha], list[Entrada]]:
    """Le manda el esqueleto al modelo y devuelve lo que sospecha.

    :param servicio: :class:`~nucleo.ia.servicio.Servicio` ya comprobado.
    :raises ErrorIA: Con un mensaje ya redactado para el usuario.
    """
    entradas = esqueleto(documento)
    if not entradas:
        return [], []
    pregunta = "%s\n\n%s" % (instruccion(), texto_del_esqueleto(entradas))
    respuesta = servicio.preguntar(pregunta)
    return interpretar(respuesta, entradas), entradas
