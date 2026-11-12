# -*- coding: utf-8 -*-
"""Qué trae un documento para poder leerse de forma accesible.

Un archivo puede llamarse EPUB, DOCX o PDF y estar bien o estar mal hecho, y la
diferencia no se ve hasta que se intenta leerlo: un informe de trescientas
páginas sin un solo encabezado no se puede recorrer con la tecla ``H``, y una
imagen sin texto alternativo es un agujero en la lectura por muy buena que sea
la maquetación.  El programa lo sabe en cuanto termina de convertir el
documento —lo tiene todo en sus marcas— pero hasta ahora no lo decía.

Este módulo lo dice.  Mira el documento ya convertido y redacta una frase con
lo que ha encontrado: cuántos encabezados hay, si las imágenes llevan
descripción, si las tablas tienen fila de encabezados, si trae índice propio,
páginas e idioma.  Esa frase aparece en «Información del documento»
(``Control+D``) y queda en el registro.

Sirve para dos cosas distintas:

* **Al lector**, para saber a qué atenerse antes de empezar: si el documento no
  tiene encabezados, no merece la pena buscarlos con ``H``, y si sus imágenes
  vienen sin describir, ahí está la orden de describirlas con inteligencia
  artificial.
* **A quien publica**, para poder arreglarlo: «doce imágenes sin texto
  alternativo» es un dato con el que se puede volver al original.

Se calcula igual para todos los formatos, porque todos acaban en el mismo
modelo de documento (:mod:`nucleo.documento`).  Cada analizador puede añadir
delante lo suyo: el de PDF cuenta si el archivo está etiquetado y cuánto de su
texto cubre la estructura, y el de EPUB, los metadatos de accesibilidad que la
norma EPUB Accessibility pide declarar.
"""

from __future__ import annotations

from typing import NamedTuple

from .idioma import _
from .marcas import TipoMarca


class Informe(NamedTuple):
    """Recuento de lo que hace navegable un documento."""

    encabezados: int
    entradas_indice: int
    imagenes: int
    imagenes_descritas: int
    tablas: int
    listas: int
    enlaces: int
    notas: int
    paginas: int
    idiomas: int
    formulas: int

    @property
    def imagenes_sin_describir(self) -> int:
        """Imágenes que no traen texto alternativo."""
        return max(self.imagenes - self.imagenes_descritas, 0)

    @property
    def navegable(self) -> bool:
        """Indica si el documento se puede recorrer por su estructura.

        Con encabezados o con índice basta: son las dos formas de saltar de un
        sitio a otro sin leerlo todo, que es lo que separa un documento de un
        churro de texto.
        """
        return bool(self.encabezados or self.entradas_indice)


def examinar(documento) -> Informe:
    """Cuenta lo que trae un documento ya convertido."""
    marcas = documento.marcas
    imagenes = 0
    descritas = 0
    for tipo in (TipoMarca.IMAGEN, TipoMarca.FIGURA):
        for marca in marcas.grupo(tipo):
            imagenes += 1
            # El conversor deja el nivel a 1 cuando la imagen traía texto
            # alternativo o pie, que son las dos formas válidas de describirla.
            if marca.nivel:
                descritas += 1
    return Informe(
        encabezados=len(marcas.encabezados),
        entradas_indice=len(documento.indice_plano()),
        imagenes=imagenes,
        imagenes_descritas=descritas,
        tablas=marcas.cantidad(TipoMarca.TABLA),
        listas=marcas.cantidad(TipoMarca.LISTA),
        enlaces=marcas.cantidad(TipoMarca.ENLACE),
        notas=marcas.cantidad(TipoMarca.NOTA_PIE),
        paginas=marcas.cantidad(TipoMarca.SALTO_PAGINA),
        idiomas=marcas.cantidad(TipoMarca.IDIOMA),
        formulas=marcas.cantidad(TipoMarca.FORMULA),
    )


def redactar(informe: Informe, idioma: str = "") -> str:
    """Escribe en una frase lo que el informe ha encontrado.

    Se empieza por lo que decide si el documento se puede recorrer —los
    encabezados y el índice— y se sigue por lo que puede faltar.  Lo que no hay
    no se menciona: una lista de ceros no informa de nada y esconde lo que sí
    importa.
    """
    partes: list[str] = []
    if informe.encabezados:
        partes.append(_("%d encabezados") % informe.encabezados)
    if informe.entradas_indice:
        partes.append(_("índice de %d entradas") % informe.entradas_indice)
    if not informe.navegable:
        partes.append(_("sin encabezados ni índice: no se puede recorrer con la tecla H"))
    for cantidad, texto in ((informe.tablas, _("%d tablas")),
                            (informe.listas, _("%d listas")),
                            (informe.enlaces, _("%d enlaces")),
                            (informe.notas, _("%d notas al pie")),
                            (informe.formulas, _("%d fórmulas"))):
        if cantidad:
            partes.append(texto % cantidad)
    if informe.imagenes:
        if not informe.imagenes_sin_describir:
            partes.append(_("%d imágenes, todas descritas") % informe.imagenes)
        else:
            partes.append(_("%d imágenes, %d sin descripción")
                          % (informe.imagenes, informe.imagenes_sin_describir))
    if informe.paginas:
        partes.append(_("%d páginas") % informe.paginas)
    if informe.idiomas:
        partes.append(_("%d cambios de idioma marcados") % informe.idiomas)
    if idioma:
        partes.append(_("idioma %s") % idioma)
    if not partes:
        return _("Documento sin estructura: solo texto corrido.")
    return "; ".join(partes) + "."


def resumen(documento, delante: str = "") -> str:
    """Frase completa de accesibilidad del documento.

    :param delante: Lo que el analizador del formato quiera decir antes, que es
                    lo único que este módulo no puede saber por sí solo: si un
                    PDF está etiquetado, o qué declara un EPUB en sus metadatos
                    de accesibilidad.
    """
    frase = redactar(examinar(documento), documento.metadatos.idioma)
    return ("%s %s" % (delante.strip(), frase)).strip() if delante else frase
