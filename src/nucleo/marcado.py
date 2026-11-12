# -*- coding: utf-8 -*-
"""Conversor de Markdown a HTML.

El manual de usuario se guarda en Markdown, que es cómodo de escribir y se
puede leer tal cual con cualquier editor de texto.  Para consultarlo se
convierte a HTML y se abre en el navegador, que es donde mejor se lee y donde
los lectores de pantalla se manejan con más soltura (encabezados, tablas y
listas con sus órdenes de navegación propias).

La conversión la hace este módulo y no una biblioteca externa por dos motivos:
el programa no necesita nada más de una biblioteca así, y una dependencia
menos es un problema menos al compilar.  Se admite el subconjunto de Markdown
que el manual utiliza:

* encabezados de ``#`` a ``######``, con enlace propio para el índice;
* párrafos, separados por líneas en blanco;
* listas con viñeta y numeradas, con un nivel de anidamiento;
* tablas con barras verticales;
* citas con ``>``, que se usan para los avisos y los trucos;
* **bloques de código** vallados con tres comillas invertidas o tres
  virgulillas, con su lenguaje si se declara.  Es lo que lleva el LÉAME de
  cualquier repositorio, y sin entenderlo las vallas se leían como texto y
  cada renglón del ejemplo salía como un párrafo suelto;
* líneas horizontales con ``---``;
* dentro del texto: ``**negrita**``, ``*cursiva*``, ``` `teclas` ``` y
  ``[enlaces](destino)``.
"""

from __future__ import annotations

import html
import re
import unicodedata

#: Encabezado: uno a seis almohadillas, un espacio y el texto.
_ENCABEZADO = re.compile(r"^(#{1,6})\s+(.*)$")

#: Elemento de lista con viñeta, con posible sangría de dos o cuatro espacios.
_VINETA = re.compile(r"^(\s*)[-*]\s+(.*)$")

#: Elemento de lista numerada.
_NUMERADO = re.compile(r"^(\s*)\d+[.)]\s+(.*)$")

#: Fila de tabla: empieza y acaba por barra vertical.
_FILA = re.compile(r"^\s*\|(.+)\|\s*$")

#: Fila separadora de la cabecera de una tabla: solo guiones, dos puntos y barras.
_SEPARADOR_TABLA = re.compile(r"^\s*\|[\s:|-]+\|\s*$")

#: Línea horizontal.
_REGLA = re.compile(r"^\s*([-*_])\1{2,}\s*$")

#: Valla de un bloque de código: tres o más comillas invertidas o virgulillas
#: y, detrás, el nombre del lenguaje si se declara.
_VALLA = re.compile(r"^\s*(?P<valla>`{3,}|~{3,})\s*(?P<lenguaje>[^`\s]*)\s*$")

#: Cita: empieza por «mayor que».
_CITA = re.compile(r"^\s*>\s?(.*)$")


def _identificador(texto: str) -> str:
    """Convierte el texto de un encabezado en un identificador para enlazar.

    Se quitan los acentos y todo lo que no sea letra o número, de modo que el
    resultado sirva como destino de un enlace dentro de la propia página.
    """
    plano = unicodedata.normalize("NFKD", texto)
    plano = "".join(c for c in plano if not unicodedata.combining(c))
    limpio = re.sub(r"[^a-zA-Z0-9]+", "-", plano).strip("-").lower()
    return limpio or "seccion"


def _en_linea(texto: str) -> str:
    """Aplica el formato que va dentro de una línea de texto.

    El orden importa: primero se escapa el HTML del texto original, y solo
    después se introducen las etiquetas propias.  Así, un texto que contenga
    ``<`` o ``&`` se muestra tal cual en lugar de romper la página.
    """
    resultado = html.escape(texto, quote=False)
    # Código y teclas.  Se hace antes que el resto para que lo que va entre
    # comillas invertidas no sufra ninguna otra transformación.
    trozos: list[str] = []

    def guardar(coincidencia: re.Match) -> str:
        trozos.append(coincidencia.group(1))
        return "\x00%d\x00" % (len(trozos) - 1)

    resultado = re.sub(r"`([^`]+)`", guardar, resultado)
    resultado = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', resultado)
    resultado = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", resultado)
    resultado = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", resultado)
    for numero, contenido in enumerate(trozos):
        resultado = resultado.replace("\x00%d\x00" % numero, "<code>%s</code>" % contenido)
    return resultado


def _celdas(linea: str) -> list[str]:
    """Separa una fila de tabla en sus celdas."""
    interior = linea.strip().strip("|")
    return [celda.strip() for celda in interior.split("|")]


class _Constructor:
    """Va acumulando el HTML y recuerda qué bloque está abierto."""

    def __init__(self) -> None:
        self.partes: list[str] = []
        self._lista: str | None = None      # "ul", "ol" o None
        self._en_cita = False
        self._en_tabla = False

    def cerrar_lista(self) -> None:
        """Cierra la lista que estuviera abierta."""
        if self._lista:
            self.partes.append("</%s>" % self._lista)
            self._lista = None

    def cerrar_cita(self) -> None:
        """Cierra la cita que estuviera abierta."""
        if self._en_cita:
            self.partes.append("</blockquote>")
            self._en_cita = False

    def cerrar_tabla(self) -> None:
        """Cierra la tabla que estuviera abierta."""
        if self._en_tabla:
            self.partes.append("</tbody></table>")
            self._en_tabla = False

    def cerrar_todo(self) -> None:
        """Cierra cualquier bloque abierto."""
        self.cerrar_lista()
        self.cerrar_cita()
        self.cerrar_tabla()


def _cuerpo(texto: str) -> str:
    """Convierte el texto en Markdown al cuerpo de la página HTML."""
    constructor = _Constructor()
    partes = constructor.partes
    lineas = texto.replace("\r\n", "\n").split("\n")
    numero = 0
    while numero < len(lineas):
        linea = lineas[numero]
        numero += 1

        if not linea.strip():
            constructor.cerrar_lista()
            constructor.cerrar_cita()
            constructor.cerrar_tabla()
            continue

        valla = _VALLA.match(linea)
        if valla:
            # Dentro de la valla no se interpreta nada: el contenido es código
            # y va tal cual, con sus espacios y con sus caracteres especiales
            # escapados.  La valla de cierre ha de ser del mismo carácter, al
            # menos igual de larga y sin lenguaje detrás.
            constructor.cerrar_todo()
            abre = valla.group("valla")
            lenguaje = valla.group("lenguaje")
            dentro: list[str] = []
            while numero < len(lineas):
                actual = lineas[numero]
                numero += 1
                cierre = _VALLA.match(actual)
                if (cierre and cierre.group("valla")[0] == abre[0]
                        and len(cierre.group("valla")) >= len(abre)
                        and not cierre.group("lenguaje")):
                    break
                dentro.append(actual)
            # Los renglones vacíos del final sobran: son la separación que
            # había antes de la valla de cierre, o el final del archivo si esa
            # valla nunca llegó.
            while dentro and not dentro[-1].strip():
                dentro.pop()
            clase = ""
            if lenguaje:
                clase = ' class="language-%s"' % html.escape(lenguaje, quote=True)
            partes.append("<pre><code%s>%s</code></pre>"
                          % (clase, html.escape("\n".join(dentro), quote=False)))
            continue

        if _REGLA.match(linea):
            constructor.cerrar_todo()
            partes.append("<hr>")
            continue

        encabezado = _ENCABEZADO.match(linea)
        if encabezado:
            constructor.cerrar_todo()
            nivel = len(encabezado.group(1))
            titulo = encabezado.group(2).strip()
            partes.append('<h%d id="%s">%s</h%d>'
                          % (nivel, _identificador(titulo), _en_linea(titulo), nivel))
            continue

        # Tabla: la fila actual es la cabecera si la siguiente es la separadora.
        if (_FILA.match(linea) and numero < len(lineas)
                and _SEPARADOR_TABLA.match(lineas[numero])):
            constructor.cerrar_lista()
            constructor.cerrar_cita()
            cabecera = _celdas(linea)
            numero += 1                     # se salta la fila separadora
            partes.append("<table><thead><tr>")
            for celda in cabecera:
                partes.append("<th>%s</th>" % _en_linea(celda))
            partes.append("</tr></thead><tbody>")
            constructor._en_tabla = True
            continue
        if constructor._en_tabla and _FILA.match(linea):
            partes.append("<tr>")
            for celda in _celdas(linea):
                partes.append("<td>%s</td>" % _en_linea(celda))
            partes.append("</tr>")
            continue

        cita = _CITA.match(linea)
        if cita:
            constructor.cerrar_lista()
            constructor.cerrar_tabla()
            if not constructor._en_cita:
                partes.append("<blockquote>")
                constructor._en_cita = True
            partes.append("<p>%s</p>" % _en_linea(cita.group(1)))
            continue
        constructor.cerrar_cita()

        vineta = _VINETA.match(linea)
        numerado = _NUMERADO.match(linea) if not vineta else None
        if vineta or numerado:
            coincidencia = vineta or numerado
            etiqueta = "ul" if vineta else "ol"
            constructor.cerrar_tabla()
            if constructor._lista != etiqueta:
                constructor.cerrar_lista()
                partes.append("<%s>" % etiqueta)
                constructor._lista = etiqueta
            partes.append("<li>%s</li>" % _en_linea(coincidencia.group(2)))
            continue
        constructor.cerrar_lista()
        constructor.cerrar_tabla()

        partes.append("<p>%s</p>" % _en_linea(linea.strip()))

    constructor.cerrar_todo()
    return "\n".join(partes)


#: Hoja de estilo de la página generada.  Se incrusta en el propio archivo para
#: que el manual sea un único documento que se pueda copiar o enviar.
_ESTILO = """
:root { color-scheme: light dark; }
body {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 18px; line-height: 1.65;
  max-width: 46rem; margin: 0 auto; padding: 1.5rem 1.25rem 4rem;
  background: #fdfdfb; color: #1b1b18;
}
@media (prefers-color-scheme: dark) {
  body { background: #16171a; color: #e6e4df; }
  code { background: #26282d; color: #e6e4df; }
  th { background: #26282d; }
  td, th { border-color: #3a3d44; }
  a { color: #8ab4f8; }
  blockquote { background: rgba(255,255,255,.05); }
}
h1 { font-size: 2rem; line-height: 1.2; margin-top: 0; }
h2 { font-size: 1.5rem; margin-top: 2.5rem; border-bottom: 2px solid currentColor;
     padding-bottom: .3rem; }
h3 { font-size: 1.2rem; margin-top: 1.8rem; }
code {
  font-family: Consolas, "Courier New", monospace; font-size: .95em;
  background: #eceae4; padding: .1em .4em; border-radius: .25em;
  border: 1px solid rgba(0,0,0,.2); white-space: nowrap;
}
table { border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: .95em; }
th, td { border: 1px solid #c9c6bd; padding: .45rem .6rem; text-align: left;
         vertical-align: top; }
th { background: #f0eee8; }
blockquote {
  border-left: 5px solid #2e7d32; background: rgba(46,125,50,.09);
  padding: .2rem 1rem; margin: 1.2rem 0;
}
blockquote p { margin: .6rem 0; }
hr { border: none; border-top: 1px solid #c9c6bd; margin: 2rem 0; }
ol, ul { padding-left: 1.6rem; }
li { margin: .3rem 0; }
a:focus, a:hover { outline: 2px solid currentColor; outline-offset: 2px; }
"""


def a_html(texto: str, titulo: str = "Manual") -> str:
    """Convierte un texto en Markdown en una página HTML completa.

    :param texto: Contenido en Markdown.
    :param titulo: Título de la página, para la pestaña del navegador.
    """
    return (
        "<!DOCTYPE html>\n"
        '<html lang="es">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>%s</title>\n<style>%s</style>\n</head>\n<body>\n%s\n</body>\n</html>\n"
        % (html.escape(titulo), _ESTILO, _cuerpo(texto))
    )
