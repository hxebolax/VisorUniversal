# -*- coding: utf-8 -*-
"""El cuaderno de estudio: lo marcado en varios libros, junto y por temas.

Las notas y los resaltados ya se sacan a un archivo, y ya se pueden filtrar por
etiqueta (:mod:`nucleo.etiquetas`). Pero eso es **libro por libro**, y quien
prepara una asignatura no estudia un libro: estudia un tema que está repartido
por seis.

Aquí se juntan. Se recoge lo marcado en todos los libros que se le digan —o en
los de una colección—, se agrupa **por etiqueta** y sale un solo archivo con
todo lo del tema, diciendo de qué libro y de qué página viene cada cosa.

**No hace falta abrir ningún libro.** Cada marcador guarda consigo el trozo de
texto al que está pegado (``Marcador.fragmento``), y por eso se puede montar el
cuaderno de una biblioteca de trescientos libros al instante y sin que ninguno
esté a mano. Lo único que se pierde es el número de página exacto, que solo se
sabe con el documento delante; en su lugar va el porcentaje, que es lo que ya
guarda el marcador.

**Por qué se agrupa por etiqueta y no por libro.** Agrupado por libro ya está: es
lo que sale al exportar los resaltados de cada uno. Lo que no había, y es lo que
hace falta al preparar un examen, es «todo lo del tema cuatro», leído seguido,
sin importar de qué libro salga cada párrafo.
"""

from __future__ import annotations

import html as _html
from pathlib import Path

from . import etiquetas
from .idioma import _
from .idioma import _n
from .registro import obtener_registro

log = obtener_registro(__name__)

#: Formatos en los que se puede sacar el cuaderno. Son los mismos que los de
#: los resaltados de un libro suelto, a propósito: quien ya sepa cuál quiere no
#: tiene que volver a decidirlo.
FORMATOS = ("txt", "md", "html")


def nombres() -> dict[str, tuple[str, str, str]]:
    """Rótulo, extensión y filtro de archivo de cada formato."""
    return {
        "txt": (_("Texto plano (.txt)"), ".txt",
                _("Archivos de texto (*.txt)|*.txt")),
        "md": (_("Markdown (.md)"), ".md",
               _("Archivos Markdown (*.md)|*.md")),
        "html": (_("Página web (.html)"), ".html",
                 _("Páginas web (*.html)|*.html")),
    }


class Apunte:
    """Una cosa marcada, con de dónde viene.

    Es lo mismo que un :class:`~nucleo.resaltados.Pasaje` más el libro, que es
    justo lo que hace falta cuando lo marcado sale de varios sitios: sin saber
    de qué libro es cada párrafo, un cuaderno de seis libros no se puede usar
    para citar nada.
    """

    __slots__ = ("libro", "autor", "texto", "nota", "sitio", "etiquetas",
                 "posicion", "ruta")

    def __init__(self, libro: str, autor: str, texto: str, nota: str,
                 sitio: str, sus_etiquetas, posicion: int,
                 ruta: str = "") -> None:
        self.libro = libro
        #: Dónde está el archivo. Hace falta para poder volver a él y para que
        #: el repaso sepa de qué apunte se trata entre una sesión y otra.
        self.ruta = ruta
        self.autor = autor
        self.texto = " ".join((texto or "").split())
        self.nota = (nota or "").strip()
        self.sitio = sitio
        self.etiquetas = list(sus_etiquetas or [])
        self.posicion = posicion

    def de_donde(self) -> str:
        """De qué libro y de qué punto viene, en una línea."""
        piezas = [self.libro]
        if self.autor:
            piezas.append(self.autor)
        if self.sitio:
            piezas.append(self.sitio)
        return " · ".join(piezas)


def _sitio(marcador, total: int) -> str:
    """Por dónde va, sin abrir el libro.

    Con el documento delante se sabría la página; aquí solo se tiene el total
    de caracteres que la biblioteca guarda de cada libro, así que se da el
    porcentaje, que al menos sitúa.
    """
    if total > 0:
        return _("%d por ciento") % max(0, min(100, int(marcador.inicio * 100 / total)))
    return ""


def reunir(configuracion, libros, etiqueta: str = "",
           con_notas: bool = True, con_resaltados: bool = True) -> list[Apunte]:
    """Recoge lo marcado en esos libros.

    :param libros: Los :class:`~nucleo.biblioteca.Libro` de los que recoger.
    :param etiqueta: Si se da, solo lo que la lleve.
    :param con_notas: Incluir las notas escritas.
    :param con_resaltados: Incluir los pasajes resaltados.
    """
    apuntes: list[Apunte] = []
    for libro in libros:
        datos = configuracion.datos_de(libro.ruta)
        if datos is None or not datos.marcadores:
            continue
        for marcador in sorted(datos.marcadores, key=lambda m: m.inicio):
            es_resaltado = getattr(marcador, "es_resaltado", False)
            es_nota = getattr(marcador, "es_nota", False)
            if not ((es_resaltado and con_resaltados) or (es_nota and con_notas)):
                continue
            if etiqueta and not etiquetas.tiene(marcador, etiqueta):
                continue
            apuntes.append(Apunte(
                libro.titulo, libro.autor, marcador.fragmento,
                marcador.nota if es_nota else "",
                _sitio(marcador, libro.total or datos.total),
                etiquetas.de(marcador), marcador.inicio, libro.ruta))
    return apuntes


def por_etiqueta(apuntes) -> list[tuple[str, list[Apunte]]]:
    """Agrupa los apuntes por etiqueta, de la más usada a la menos.

    Un apunte con dos etiquetas sale **en los dos grupos**: quien repasa el tema
    cuatro quiere verlo, y quien repasa «dudas» también. Duplicar es lo correcto
    aquí; esconderlo en uno de los dos, no.

    Lo que no lleva ninguna etiqueta va en un grupo al final, porque tirarlo
    sería perder lo que alguien marcó antes de empezar a etiquetar.
    """
    grupos: dict[str, list[Apunte]] = {}
    escritas: dict[str, str] = {}
    sueltos: list[Apunte] = []
    for apunte in apuntes:
        if not apunte.etiquetas:
            sueltos.append(apunte)
            continue
        for etiqueta in apunte.etiquetas:
            clave = etiquetas.normalizar(etiqueta)
            if not clave:
                continue
            escritas.setdefault(clave, etiqueta)
            grupos.setdefault(clave, []).append(apunte)
    salida = sorted(((escritas[clave], lista) for clave, lista in grupos.items()),
                    key=lambda par: (-len(par[1]), etiquetas.normalizar(par[0])))
    if sueltos:
        salida.append((_("Sin etiqueta"), sueltos))
    return salida


def resumen(apuntes, libros_distintos: int) -> str:
    """Frase con lo que lleva el cuaderno, para anunciarlo."""
    if not apuntes:
        return _("No hay nada marcado en esos libros.")
    return _n("%(apuntes)d apunte de %(libros)d libro.",
              "%(apuntes)d apuntes de %(libros)d libros.", len(apuntes)) % {
        "apuntes": len(apuntes), "libros": libros_distintos}


# ---------------------------------------------------------------------------
# Los formatos
# ---------------------------------------------------------------------------

def a_txt(grupos, titulo: str = "") -> bytes:
    """Texto plano, con un apartado por etiqueta."""
    lineas = [titulo or _("Cuaderno de estudio"), ""]
    for etiqueta, apuntes in grupos:
        lineas.append(etiqueta.upper())
        lineas.append("")
        for apunte in apuntes:
            lineas.append(apunte.de_donde())
            if apunte.texto:
                lineas.append(apunte.texto)
            if apunte.nota:
                lineas.append(_("Nota: %s") % apunte.nota)
            lineas.append("")
        lineas.append("")
    return "\n".join(lineas).encode("utf-8")


def a_markdown(grupos, titulo: str = "") -> bytes:
    """Markdown, con un encabezado por etiqueta y cada pasaje como cita."""
    partes = ["# %s" % (titulo or _("Cuaderno de estudio")), ""]
    for etiqueta, apuntes in grupos:
        partes.append("## %s" % etiqueta)
        partes.append("")
        for apunte in apuntes:
            partes.append("**%s**" % apunte.de_donde())
            partes.append("")
            if apunte.texto:
                for renglon in apunte.texto.split("\n"):
                    partes.append("> %s" % renglon)
                partes.append("")
            if apunte.nota:
                partes.append(apunte.nota)
                partes.append("")
    return "\n".join(partes).encode("utf-8")


def a_html(grupos, titulo: str = "", idioma: str = "es") -> bytes:
    """Página web con un apartado por etiqueta.

    Los encabezados son de verdad —``h2`` por etiqueta— para poder saltar de
    tema en tema con la tecla ``H`` del lector de pantalla, que es exactamente
    para lo que sirve un cuaderno de repaso.
    """
    rotulo = _html.escape(titulo or _("Cuaderno de estudio"))
    cuerpo = []
    for etiqueta, apuntes in grupos:
        cuerpo.append("<h2>%s</h2>" % _html.escape(etiqueta))
        for apunte in apuntes:
            fuente = "<footer><cite>%s</cite></footer>" % _html.escape(
                apunte.de_donde())
            if apunte.texto:
                cuerpo.append("<blockquote>\n<p>%s</p>\n%s\n</blockquote>"
                              % (_html.escape(apunte.texto), fuente))
            else:
                cuerpo.append("<p><cite>%s</cite></p>" % _html.escape(
                    apunte.de_donde()))
            if apunte.nota:
                cuerpo.append('<p class="nota">%s</p>' % _html.escape(apunte.nota))
    return ("<!DOCTYPE html>\n"
            '<html lang="%s"><head><meta charset="utf-8">\n'
            "<title>%s</title>\n"
            "<style>body{font-family:sans-serif;max-width:42em;margin:2em auto;"
            "line-height:1.55;padding:0 1em}"
            "blockquote{border-left:.25em solid #888;margin:1.2em 0;padding:0 1em}"
            "cite{font-style:normal;font-size:.9em}"
            ".nota{margin:0 0 1.5em 1em}</style>\n"
            "</head><body>\n<h1>%s</h1>\n%s\n</body></html>\n"
            % (idioma or "es", rotulo, rotulo, "\n".join(cuerpo))).encode("utf-8")


def exportar(grupos, destino, formato: str, titulo: str = "",
             idioma: str = "es") -> None:
    """Escribe el cuaderno en el formato pedido.

    :raises ValueError: Si el formato no es uno de :data:`FORMATOS`.
    :raises OSError: Si no se puede escribir el archivo.
    """
    if formato not in FORMATOS:
        raise ValueError("Formato desconocido: %r" % formato)
    if formato == "md":
        datos = a_markdown(grupos, titulo)
    elif formato == "html":
        datos = a_html(grupos, titulo, idioma)
    else:
        datos = a_txt(grupos, titulo)
    ruta = Path(destino)
    ruta.write_bytes(datos)
    log.info("Cuaderno de estudio con %d temas escrito en %s",
             len(grupos), ruta.name)
