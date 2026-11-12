# -*- coding: utf-8 -*-
"""Sacar los pasajes resaltados de un documento a un archivo aparte.

Resaltar sirve para dos momentos distintos. Mientras se lee, para señalar lo que
importa. **Después**, para repasar solo eso sin volver a recorrer las doscientas
páginas: las ideas principales de un tema, las definiciones de un manual, las
citas que hacen falta para un trabajo.

Ese segundo momento casi nunca ocurre dentro del programa que leyó el documento,
y por eso los resaltados se pueden sacar fuera. A tres formatos, porque los tres
sirven para cosas distintas:

=========  =====================================================
Formato    Para qué
=========  =====================================================
TXT        Lo universal.  Se pega en cualquier sitio, lo abre
           cualquier programa y se seguirá leyendo dentro de
           veinte años.
Markdown   Para una libreta de notas (Obsidian, Joplin, Notion) o
           para un repositorio; sigue siendo texto que se lee tal
           cual si no hay nada que lo interprete.
HTML       Para abrirlo en el navegador o mandárselo a alguien,
           con sus enlaces al documento original.
=========  =====================================================

Qué lleva cada pasaje
---------------------

Su texto y **dónde estaba**: la página si el documento las tiene, y si no el
porcentaje. Esa referencia no es un adorno: un resaltado sin ella no se puede
volver a encontrar en el original, y volver al original es la mitad de para lo
que se resalta —para comprobar, para citar, para leer lo que había alrededor—.

Se escribe lo que se guardó al resaltar, no lo que diga hoy el documento.  Así
el archivo sale bien aunque el documento se haya vuelto a analizar con otras
opciones y las posiciones ya no coincidan exactamente.
"""

from __future__ import annotations

import html as _html
from pathlib import Path

from . import etiquetas
from .idioma import _
from .marcas import TipoMarca
from .registro import obtener_registro

log = obtener_registro(__name__)

#: Formatos a los que se pueden sacar los resaltados, en el orden del menú: de
#: lo más sencillo a lo más elaborado.
FORMATOS = ("txt", "md", "html")


def nombres() -> dict[str, tuple[str, str, str]]:
    """``{clave: (nombre de menú, extensión, filtro del diálogo)}``."""
    return {
        "txt": (_("Texto plano (.txt)"), ".txt",
                _("Archivos de texto (*.txt)|*.txt")),
        "md": (_("Markdown (.md)"), ".md",
               _("Archivos Markdown (*.md)|*.md")),
        "html": (_("Página web (.html)"), ".html",
                 _("Páginas web (*.html)|*.html")),
    }


class Pasaje:
    """Un resaltado ya resuelto: su texto y dónde estaba, sin más.

    Se separa del :class:`~nucleo.configuracion.Marcador` a propósito.  El
    marcador guarda posiciones dentro del texto, que solo significan algo con el
    documento delante; aquí hace falta lo contrario: algo que se pueda escribir
    en un archivo y siga entendiéndose sin el programa ni el documento.
    """

    __slots__ = ("texto", "sitio", "posicion", "nota", "etiquetas")

    def __init__(self, texto: str, sitio: str, posicion: int = 0,
                 nota: str = "", etiquetas_puestas=None) -> None:
        self.texto = " ".join((texto or "").split())
        #: Los temas a los que se apunto esto. Se exportan con el pasaje para
        #: que el archivo siga sirviendo fuera del programa: un cuaderno de
        #: estudio sin saber de que tema es cada cosa vuelve a ser una lista.
        self.etiquetas = list(etiquetas_puestas or [])
        #: Lo que el lector escribió sobre este pasaje.  Va con él y no aparte
        #: porque una nota sin el pasaje al que se refiere no se entiende: al
        #: repasar hace falta leer lo que decía el libro y lo que uno pensó,
        #: seguidos y en ese orden.
        self.nota = (nota or "").strip()
        self.sitio = sitio
        self.posicion = posicion


def pasajes_de(documento, marcadores, con_notas: bool = False,
               etiqueta: str = "") -> list[Pasaje]:
    """Convierte los resaltados de un documento en pasajes exportables.

    :param documento: Documento abierto, para averiguar la página de cada uno.
    :param marcadores: Marcadores del documento; se toman solo los resaltados y
                       se ordenan por su sitio.
    :param con_notas: Si se incluyen también las notas escritas, cada una con
                      el trozo de texto al que está anclada.  Es lo que
                      convierte esto en un cuaderno de estudio: lo subrayado y
                      lo pensado, juntos y en el orden del libro.
    :param etiqueta: Si se da, solo salen los que lleven esa etiqueta.  Es lo
                     que permite sacar «todo lo del tema cuatro» en vez de
                     todo lo del libro.
    """
    elegidos = []
    for marcador in marcadores:
        if getattr(marcador, "es_resaltado", False):
            elegidos.append(marcador)
        elif con_notas and getattr(marcador, "es_nota", False):
            elegidos.append(marcador)
    if etiqueta:
        elegidos = etiquetas.filtrar(elegidos, etiqueta)
    elegidos.sort(key=lambda m: m.inicio)

    pasajes = []
    for marcador in elegidos:
        texto = marcador.fragmento
        if not texto and documento is not None:
            texto = documento.texto[marcador.inicio:marcador.fin]
        nota = getattr(marcador, "nota", "") if con_notas else ""
        pasajes.append(Pasaje(texto, sitio_de(documento, marcador.inicio),
                              marcador.inicio, nota, etiquetas.de(marcador)))
    return pasajes


def sitio_de(documento, posicion: int) -> str:
    """Dice dónde está una posición, de la forma más útil que se pueda.

    La página es lo que sirve para volver al original y lo que se pone en una
    cita, así que manda.  Cuando el documento no tiene numeración —un EPUB sin
    marcas de página, una página web— se recurre al porcentaje, que al menos
    sitúa.
    """
    if documento is None:
        return ""
    try:
        indice = documento.indice_de_pagina(posicion)
        if indice >= 0 and documento.total_paginas:
            marcas = documento.marcas.grupo(TipoMarca.SALTO_PAGINA).marcas
            if 0 <= indice < len(marcas):
                return _("Página %s") % (marcas[indice].texto or str(indice + 1))
        return _("%d por ciento") % documento.porcentaje_en(posicion)
    except Exception:
        return ""


def a_txt(pasajes: list, titulo: str, autor: str = "",
          referencia: str = "", etiqueta: str = "") -> bytes:
    """Texto plano: el sitio, el pasaje y una línea en blanco entre medias."""
    lineas = [titulo]
    if autor:
        lineas.append(autor)
    if referencia:
        lineas.append(referencia)
    lineas.append(_cabecera(pasajes, etiqueta))
    lineas.append("")
    for pasaje in pasajes:
        if pasaje.sitio:
            lineas.append(pasaje.sitio)
        if pasaje.texto:
            lineas.append(pasaje.texto)
        if pasaje.nota:
            lineas.append(_("Nota: %s") % pasaje.nota)
        if pasaje.etiquetas:
            lineas.append(_("Etiquetas: %s") % etiquetas.escribir(pasaje.etiquetas))
        lineas.append("")
    return "\n".join(lineas).encode("utf-8")


def a_markdown(pasajes: list, titulo: str, autor: str = "",
               referencia: str = "", etiqueta: str = "") -> bytes:
    """Markdown: cada pasaje como cita, con su sitio en cursiva encima.

    Se escriben como **citas** (``>``) y no como párrafos porque eso es lo que
    son: palabras de otro documento.  Al pegarlas en una libreta de notas se ve
    de un vistazo qué es cita y qué es cosecha propia, que es justo lo que se
    pierde al copiar y pegar a mano.
    """
    partes = ["# %s" % titulo]
    if autor:
        partes.append("*%s*" % autor)
    partes.append("")
    if referencia:
        partes.append("> %s" % referencia)
        partes.append("")
    partes.append(_cabecera(pasajes, etiqueta))
    partes.append("")
    for pasaje in pasajes:
        if pasaje.sitio:
            partes.append("**%s**" % pasaje.sitio)
            partes.append("")
        # Una cita de varias líneas lleva el signo en todas: si no, la segunda
        # se sale de la cita y aparece como texto normal.
        if pasaje.texto:
            for renglon in (pasaje.texto or "").split("\n"):
                partes.append("> %s" % renglon)
            partes.append("")
        if pasaje.nota:
            # La nota va **fuera** de la cita: es cosecha propia, y en una
            # libreta de notas esa diferencia es lo que más importa.
            partes.append(pasaje.nota)
            partes.append("")
        if pasaje.etiquetas:
            partes.append("*%s*" % (_("Etiquetas: %s")
                                    % etiquetas.escribir(pasaje.etiquetas)))
            partes.append("")
    return "\n".join(partes).encode("utf-8")


def a_html(pasajes: list, titulo: str, autor: str = "", idioma: str = "",
           referencia: str = "", etiqueta: str = "") -> bytes:
    """Página web con cada pasaje en su ``blockquote`` y su referencia."""
    escapado = _html.escape(titulo)
    cabecera = "<h1>%s</h1>" % escapado
    if autor:
        cabecera += "\n<p><em>%s</em></p>" % _html.escape(autor)
    if referencia:
        cabecera += "\n<p class=\"fuente\">%s</p>" % _html.escape(referencia)
    cabecera += "\n<p>%s</p>" % _html.escape(_cabecera(pasajes, etiqueta))
    cuerpo = []
    for pasaje in pasajes:
        # La referencia va dentro de la cita, en su «cite», que es donde la
        # norma dice que va y donde un lector de pantalla la anuncia como lo
        # que es: la fuente de lo que se acaba de leer.
        sitio = ("\n<footer><cite>%s</cite></footer>" % _html.escape(pasaje.sitio)
                 if pasaje.sitio else "")
        if pasaje.texto:
            cuerpo.append("<blockquote>\n<p>%s</p>%s\n</blockquote>"
                          % (_html.escape(pasaje.texto), sitio))
        elif sitio:
            cuerpo.append("<p><cite>%s</cite></p>" % _html.escape(pasaje.sitio))
        if pasaje.nota:
            cuerpo.append('<p class="nota">%s</p>' % _html.escape(pasaje.nota))
        if pasaje.etiquetas:
            cuerpo.append('<p class="etiquetas">%s</p>'
                          % _html.escape(_("Etiquetas: %s")
                                         % etiquetas.escribir(pasaje.etiquetas)))
    return ("<!DOCTYPE html>\n"
            '<html lang="%s"><head><meta charset="utf-8">\n'
            "<title>%s</title>\n"
            "<style>body{font-family:sans-serif;max-width:40em;margin:2em auto;"
            "line-height:1.5;padding:0 1em}"
            "blockquote{border-left:.25em solid #888;margin:1.5em 0;padding:0 1em}"
            "cite{font-style:normal;font-size:.9em}"
            ".nota{margin:0 0 1.5em 1em}"
            ".etiquetas{font-size:.9em;margin:-1em 0 1.5em 1em}"
            ".fuente{font-size:.95em}</style>\n"
            "</head><body>\n%s\n%s\n</body></html>\n"
            % (idioma or "es", escapado, cabecera, "\n".join(cuerpo))).encode("utf-8")


def _cabecera(pasajes: list, etiqueta: str = "") -> str:
    """Cuenta lo que lleva el archivo: resaltados, notas o las dos cosas.

    Cuando se ha sacado el material de un tema concreto se dice cuál, porque es
    lo primero que hace falta saber al abrir el archivo un mes después.
    """
    resaltados = sum(1 for pasaje in pasajes if pasaje.texto)
    notas = sum(1 for pasaje in pasajes if pasaje.nota)
    if notas and resaltados:
        cuenta = _("%(resaltados)d resaltados y %(notas)d notas") % {
            "resaltados": resaltados, "notas": notas}
    elif notas:
        cuenta = _("%d notas") % notas
    else:
        cuenta = _("%d resaltados") % resaltados
    if etiqueta:
        return _("%(cuenta)s con la etiqueta «%(etiqueta)s»") % {
            "cuenta": cuenta, "etiqueta": etiqueta}
    return cuenta


def exportar(pasajes: list, destino, formato: str, titulo: str,
             autor: str = "", idioma: str = "", referencia: str = "",
             etiqueta: str = "") -> None:
    """Escribe los pasajes en el formato pedido.

    :param referencia: Cita bibliográfica del documento, que se escribe al
                       principio.  Es lo que convierte el archivo en algo que
                       se puede usar en un trabajo: sin ella, quien lo abra
                       dentro de un mes no sabe de qué libro salió.
    :raises ValueError: Si el formato no es uno de :data:`FORMATOS`.
    :raises OSError: Si no se puede escribir el archivo.
    """
    if formato not in FORMATOS:
        raise ValueError("Formato desconocido: %r" % formato)
    if formato == "md":
        datos = a_markdown(pasajes, titulo, autor, referencia, etiqueta)
    elif formato == "html":
        datos = a_html(pasajes, titulo, autor, idioma, referencia, etiqueta)
    else:
        datos = a_txt(pasajes, titulo, autor, referencia, etiqueta)
    ruta = Path(destino)
    ruta.write_bytes(datos)
    log.info("Exportados %d resaltados a %s (%s)", len(pasajes), ruta.name, formato)
