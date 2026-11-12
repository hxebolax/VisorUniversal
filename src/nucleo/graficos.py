# -*- coding: utf-8 -*-
"""Sacar los **datos** de un gráfico, no solo su descripción.

Describir un gráfico no basta.  Un lector de pantalla puede decir «gráfico de
barras de ventas por trimestre» y quien escucha sigue sin saber ni un solo
número.  La práctica que se recomendó durante años —unas frases de descripción
y, con suerte, un enlace a la tabla— está reconocida como muy inferior a lo que
ve una persona vidente de un vistazo.

Lo que hace falta son **los números**, y en una tabla que se pueda recorrer con
las órdenes de tabla del lector de pantalla: fila a fila, columna a columna,
oyendo el encabezado de cada celda.

Las tres piezas ya estaban hechas por separado
----------------------------------------------

1. El programa **ya recorta la figura** de la página y sabe mandarla a la
   inteligencia artificial (es lo que hace la descripción de imágenes).
2. La inteligencia artificial de hoy **sabe leer los valores** de un gráfico.
3. El programa **ya sabe enseñar una tabla** de verdad, con ``Control+H``.

Este módulo es la pieza que faltaba entre las tres: la instrucción que pide los
datos en un formato fijo, y el intérprete que convierte la respuesta en una
rejilla de celdas.  A partir de ahí, la tabla viaja por los mismos caminos que
cualquier otra tabla del libro.

Por qué se pide una tabla de Markdown
-------------------------------------

Se probó a pedir tabuladores y a pedir un JSON.  Lo primero se pierde: casi
ningún modelo respeta el tabulador y lo convierte en espacios.  Lo segundo sale
bien, pero cuando falla, falla entero —una coma de más y no hay nada que
salvar—.  Una tabla de Markdown es lo que mejor escriben todos los modelos, y
sobre todo **se degrada bien**: si el modelo se despista en una fila, esa fila
se pierde y las demás siguen valiendo.

De todos modos se admiten también los tabuladores y el punto y coma, por si
acaso: interpretar de más no cuesta nada y evita perder una respuesta buena por
un detalle de formato.

Y no sustituye a la descripción: se añade
-----------------------------------------

La descripción dice **de qué va** el gráfico —qué compara, qué tendencia hay,
qué conclusión se saca—.  La tabla dice **cuánto**.  Hacen falta las dos, y por
eso se guardan juntas y se enseñan juntas.
"""

from __future__ import annotations

import re

from .idioma import _
from .registro import obtener_registro

log = obtener_registro(__name__)

#: Instrucción que se le manda a la IA junto con la imagen.  Es deliberadamente
#: minuciosa en dos puntos: que **no** escriba nada fuera de las líneas
#: previstas —lo que sobra hay que adivinarlo después— y que si la imagen no es
#: un gráfico lo diga con una palabra concreta en lugar de inventarse una tabla,
#: que es el fallo que más caro sale: una tabla inventada parece un dato.
INSTRUCCION = _(
    "Esta imagen es un gráfico, un diagrama de datos o una tabla. Tu tarea es "
    "extraer LOS DATOS, no describirla.\n\n"
    "Responde EXACTAMENTE con este formato y con nada más:\n\n"
    "TITULO: el título del gráfico, o de qué trata si no lo lleva escrito\n"
    "UNIDADES: qué mide y en qué unidades (por ejemplo «millones de euros»); "
    "si no consta, escribe «no consta»\n"
    "TABLA:\n"
    "| Encabezado 1 | Encabezado 2 |\n"
    "| --- | --- |\n"
    "| valor | valor |\n"
    "NOTA: una sola frase con lo que no quepa en la tabla, o «ninguna»\n"
    "FIABILIDAD: alta, media o baja, seguida de dos puntos y de una frase corta "
    "diciendo por qué\n\n"
    "Reglas:\n"
    "- La primera columna es la categoría del eje horizontal (los años, los "
    "países, las categorías...). Cada serie del gráfico es una columna más.\n"
    "- Escribe los números tal como se leen en el gráfico, sin redondear más de "
    "lo que se vea. Si un valor hay que estimarlo porque no está rotulado, "
    "escríbelo seguido de «(aprox.)».\n"
    "- Si un valor no se puede leer, escribe «?» en su celda. No lo inventes.\n"
    "- En FIABILIDAD, pon «alta» solo si has podido leer cada valor de una "
    "etiqueta escrita o de una escala clara. Pon «media» si has tenido que "
    "estimar alguno midiendo la altura de una barra o la posición de un punto. "
    "Pon «baja» si el gráfico tiene tantos puntos, tan juntos o tan poco "
    "rotulados que los valores son aproximaciones tuyas. **No te pongas alta por "
    "cortesía**: es más útil un «baja» sincero que unos números que parezcan "
    "medidos y no lo sean.\n"
    "- Si la imagen NO contiene datos que quepan en una tabla, responde "
    "únicamente: NO ES UN GRAFICO")

#: Los tres niveles de fiabilidad que puede declarar la IA, de más a menos.
FIABILIDADES = ("alta", "media", "baja")

#: Por debajo de este nivel se avisa en voz alta al enseñar los datos. Se avisa
#: de «media» en adelante y no solo de «baja» a propósito: un valor estimado
#: midiendo la altura de una barra puede equivocarse en un diez por ciento, y en
#: un trabajo eso es la diferencia entre una conclusión y otra.
AVISAR_DESDE = "media"

#: Lo que responde la IA cuando la imagen no tiene datos que sacar.  Se compara
#: sin acentos y sin mayúsculas, porque cada modelo lo escribe a su manera.
SIN_DATOS = "no es un grafico"

#: Cuántas filas y columnas se admiten como mucho.  Un gráfico de verdad no
#: tiene doscientas filas; si salen, es que el modelo se ha desbocado y lo que
#: viene detrás no son datos.
MAXIMO_FILAS = 200
MAXIMO_COLUMNAS = 40

#: Fila separadora de la cabecera de una tabla de Markdown: solo guiones, dos
#: puntos, espacios y barras.  No es un dato: se tira.
_SEPARADORA = re.compile(r"^[\s:|+-]+$")

#: Rótulos de las líneas con las que empieza cada parte de la respuesta.  Se
#: aceptan con acento y sin él porque los modelos se dejan los acentos.
_ROTULOS = {
    "titulo": ("titulo", "título", "title"),
    "unidades": ("unidades", "units"),
    "tabla": ("tabla", "table"),
    "nota": ("nota", "note", "notas"),
    "fiabilidad": ("fiabilidad", "confianza", "reliability", "confidence"),
}


def _sin_tildes(texto: str) -> str:
    """Deja el texto en minúsculas y sin acentos, para poder compararlo."""
    import unicodedata

    plano = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in plano if not unicodedata.combining(c)).lower().strip()


def _rotulo_de(linea: str) -> tuple[str, str] | None:
    """Si la línea empieza por uno de los rótulos, devuelve ``(cual, resto)``."""
    if ":" not in linea:
        return None
    delante, detras = linea.split(":", 1)
    # Los modelos ponen a veces el rótulo en negrita o con viñeta delante.
    limpio = _sin_tildes(delante.strip().strip("*_-# "))
    for clave, formas in _ROTULOS.items():
        if limpio in formas:
            return clave, detras.strip()
    return None


def _celdas(linea: str) -> list[str] | None:
    """Parte una línea en celdas, sea tabla de Markdown, tabuladores o punto y coma.

    Devuelve ``None`` si la línea no parece una fila de tabla.  Se mira primero
    la barra vertical porque es lo que se ha pedido; los otros dos separadores
    están por si el modelo decide ir por libre.
    """
    cruda = (linea or "").strip()
    if not cruda:
        return None
    if cruda.count("|") >= 2 or (cruda.startswith("|") and cruda.endswith("|")):
        interior = cruda.strip().strip("|")
        return [celda.strip() for celda in interior.split("|")]
    if "\t" in cruda:
        return [celda.strip() for celda in cruda.split("\t")]
    if cruda.count(";") >= 1:
        return [celda.strip() for celda in cruda.split(";")]
    return None


class Grafico:
    """Los datos que se han sacado de una imagen.

    :param titulo: De qué es el gráfico.
    :param unidades: Qué mide y en qué unidades, si consta.
    :param filas: La rejilla completa, **con su fila de encabezados la
                  primera**, que es como la guardan las tablas del libro.
    :param nota: Lo que no cabía en la tabla.
    :param fiabilidad: ``alta``, ``media``, ``baja`` o cadena vacía si no lo ha
                       dicho. Es lo que separa un dato leído de una estimación.
    :param por_que: La frase con la que la IA explica esa fiabilidad.
    """

    __slots__ = ("titulo", "unidades", "filas", "nota", "fiabilidad", "por_que")

    def __init__(self, titulo: str = "", unidades: str = "",
                 filas: list[list[str]] | None = None, nota: str = "",
                 fiabilidad: str = "", por_que: str = "") -> None:
        self.titulo = (titulo or "").strip()
        self.unidades = (unidades or "").strip()
        self.filas: list[list[str]] = filas or []
        self.nota = (nota or "").strip()
        self.fiabilidad = (fiabilidad or "").strip().lower()
        self.por_que = (por_que or "").strip()

    @property
    def hay_que_avisar(self) -> bool:
        """Dice si estos datos no se pueden dar por medidos sin más.

        También se avisa cuando **la propia tabla** trae valores marcados como
        aproximados o sin leer, aunque la IA se haya declarado segura: lo que
        está escrito en las celdas manda sobre lo que diga de sí misma.
        """
        if self.fiabilidad in ("media", "baja"):
            return True
        return self.hay_estimados or self.hay_ilegibles

    @property
    def hay_estimados(self) -> bool:
        """Si alguna celda viene marcada como aproximada."""
        return any("aprox" in (celda or "").lower()
                   for fila in self.filas for celda in fila)

    @property
    def hay_ilegibles(self) -> bool:
        """Si alguna celda quedó sin leer."""
        return any((celda or "").strip() == "?"
                   for fila in self.filas[1:] for celda in fila)

    def aviso(self) -> str:
        """La frase que hay que decir antes de dar estos datos por buenos."""
        if not self.hay_que_avisar:
            return ""
        piezas = []
        if self.fiabilidad == "baja":
            piezas.append(_("Estos valores son aproximaciones: el gráfico no "
                            "trae las cifras escritas."))
        elif self.fiabilidad == "media":
            piezas.append(_("Algunos valores están estimados midiendo el "
                            "gráfico, no leídos de una etiqueta."))
        elif self.hay_estimados:
            piezas.append(_("Los valores marcados «aprox.» están estimados, no "
                            "leídos."))
        if self.hay_ilegibles:
            piezas.append(_("Las celdas con interrogación no se han podido leer."))
        if self.por_que:
            piezas.append(self.por_que)
        piezas.append(_("Compruébalos en el original antes de usarlos en un "
                        "trabajo."))
        return " ".join(piezas)

    def __bool__(self) -> bool:
        """Un gráfico vale si tiene al menos una fila de datos además del encabezado."""
        return len(self.filas) >= 2 and any(len(fila) >= 2 for fila in self.filas)

    @property
    def columnas(self) -> int:
        """Cuántas columnas tiene la fila más ancha."""
        return max((len(fila) for fila in self.filas), default=0)

    def rejilla(self) -> str:
        """La tabla como la guardan las marcas: filas con salto, celdas con tabulador.

        Es el mismo formato que usa el conversor para las tablas del libro, de
        modo que esta tabla se pueda enseñar con la maquinaria que ya existe sin
        escribir ni una línea nueva de dibujado.
        """
        return "\n".join("\t".join(fila) for fila in self.filas)

    def resumen(self) -> str:
        """Frase corta con lo que hay, para anunciarlo en voz alta."""
        if not self:
            return ""
        return _("Tabla de %(filas)d filas y %(columnas)d columnas.") % {
            "filas": len(self.filas) - 1, "columnas": self.columnas}


def interpretar(respuesta: str) -> Grafico | None:
    """Convierte la respuesta de la IA en un :class:`Grafico`.

    Devuelve ``None`` si la imagen no tenía datos o si lo que ha contestado no
    se parece a una tabla.  Devolver ``None`` es importante: **más vale no dar
    datos que dar unos inventados**, porque una tabla se lee como un hecho.
    """
    texto = (respuesta or "").strip()
    if not texto:
        return None
    if SIN_DATOS in _sin_tildes(texto)[:120]:
        log.info("La imagen no contiene datos que sacar")
        return None

    titulo = unidades = nota = fiabilidad = por_que = ""
    filas: list[list[str]] = []
    en_tabla = False
    for linea in texto.splitlines():
        rotulo = _rotulo_de(linea)
        if rotulo is not None:
            clave, resto = rotulo
            if clave == "titulo":
                titulo, en_tabla = resto, False
                continue
            if clave == "unidades":
                unidades, en_tabla = resto, False
                continue
            if clave == "nota":
                nota, en_tabla = resto, False
                continue
            if clave == "fiabilidad":
                fiabilidad, por_que = _fiabilidad_de(resto)
                en_tabla = False
                continue
            if clave == "tabla":
                en_tabla = True
                # Hay modelos que meten la primera fila en la misma línea.
                celdas = _celdas(resto)
                if celdas:
                    filas.append(celdas)
                continue
        celdas = _celdas(linea)
        if celdas is None:
            # Fuera de la tabla, una línea suelta no estorba; dentro, la corta.
            if en_tabla and linea.strip():
                en_tabla = False
            continue
        if _SEPARADORA.match(linea.strip()):
            continue           # la línea de guiones que va bajo la cabecera
        if len(filas) >= MAXIMO_FILAS:
            log.warning("La respuesta traía más de %d filas: se corta", MAXIMO_FILAS)
            break
        filas.append(celdas[:MAXIMO_COLUMNAS])
        en_tabla = True

    grafico = Grafico(titulo, _sin_no_consta(unidades), _cuadrar(filas),
                      _sin_no_consta(nota), fiabilidad, por_que)
    if not grafico:
        log.info("La respuesta no traía ninguna tabla aprovechable")
        return None
    if grafico.hay_que_avisar:
        log.info("Datos de gráfico con fiabilidad %s",
                 grafico.fiabilidad or "sin declarar")
    return grafico


def _fiabilidad_de(resto: str) -> tuple[str, str]:
    """Parte la línea de fiabilidad en el nivel y el porqué.

    Se busca el nivel **dentro** de la frase y no solo al principio, porque los
    modelos escriben tanto «baja: los puntos están muy juntos» como «La
    fiabilidad es baja porque...». Si no se reconoce ninguno de los tres
    niveles, se deja vacío: inventar una fiabilidad sería justo el fallo que
    esto viene a corregir.
    """
    texto = (resto or "").strip()
    if not texto:
        return "", ""
    nivel = ""
    plano = _sin_tildes(texto)
    for candidato in FIABILIDADES:
        if plano.startswith(candidato) or (" %s" % candidato) in plano[:40]:
            nivel = candidato
            break
    por_que = texto.split(":", 1)[1].strip() if ":" in texto else ""
    if not por_que and nivel:
        # «baja porque los puntos están muy juntos», sin dos puntos de por medio.
        resto_frase = texto[plano.find(nivel) + len(nivel):].strip(" ,.;")
        por_que = resto_frase[1:].strip() if resto_frase.startswith(":") else resto_frase
    return nivel, por_que[:300]


def _sin_no_consta(texto: str) -> str:
    """Vacía los «no consta» y «ninguna» con los que responde la IA.

    Enseñar «Unidades: no consta» es peor que no enseñar la línea: ocupa un
    renglón que hay que oír para enterarse de que no dice nada.
    """
    plano = _sin_tildes(texto).strip(" .")
    if plano in ("", "no consta", "ninguna", "ninguno", "n/a", "na", "none",
                 "no aplica", "sin unidades"):
        return ""
    return texto.strip()


def _cuadrar(filas: list[list[str]]) -> list[list[str]]:
    """Deja todas las filas con el mismo número de celdas.

    Un modelo se deja una celda de vez en cuando, y una tabla con filas de
    distinta longitud se lee fatal: el lector de pantalla anuncia una columna
    que no existe o se salta el encabezado que tocaba.  Las que falten se
    rellenan vacías, y las que sobren se quedan: cortar sería perder un dato.
    """
    if not filas:
        return []
    ancho = max(len(fila) for fila in filas)
    return [fila + [""] * (ancho - len(fila)) for fila in filas]


def desde_guardado(crudo: str) -> Grafico | None:
    """Reconstruye el gráfico tal y como se guardó en disco.

    Se guarda la rejilla ya interpretada —y no la respuesta cruda de la IA—
    porque lo que interesa conservar son los datos: si algún día cambia la
    forma de interpretar, lo guardado sigue siendo válido.
    """
    if not crudo:
        return None
    filas = [linea.split("\t") for linea in str(crudo).split("\n") if linea != ""]
    grafico = Grafico(filas=_cuadrar(filas))
    return grafico or None
