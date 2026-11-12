# -*- coding: utf-8 -*-
"""Creación de los analizadores XML y HTML que usa la aplicación.

Están centralizados aquí por dos motivos:

* **Tolerancia.**  Los EPUB del mundo real incumplen la norma con frecuencia,
  así que los analizadores se configuran en modo de recuperación: ante un
  error, siguen adelante con lo que puedan leer en lugar de rendirse.

* **Nada de red.**  Casi todos los libros declaran una DTD alojada en un
  servidor de Internet.  El analizador no necesita descargarla para nada, y
  hacerlo supondría esperas de varios segundos —o bloqueos— si el equipo no
  tiene conexión.  El resolvedor que se instala aquí intercepta cualquier
  petición de recurso externo y devuelve un documento vacío, con lo que el
  intento de acceso a la red no llega a producirse.
"""

from __future__ import annotations

from lxml import etree


class ResolvedorSinRed(etree.Resolver):
    """Intercepta las referencias a recursos externos y las anula.

    Devolver una cadena vacía es suficiente: el documento no depende de la
    DTD para nada de lo que hace la aplicación (solo se extraen texto y
    estructura, no se valida).
    """

    def resolve(self, url, identificador, contexto):  # noqa: N802 (API de lxml)
        """Responde a cualquier recurso externo con contenido vacío."""
        return self.resolve_string("", contexto)


def crear_parser_xml() -> etree.XMLParser:
    """Crea un analizador XML tolerante y sin acceso a la red."""
    parser = etree.XMLParser(
        recover=True,          # continúa pese a los errores de sintaxis
        resolve_entities=False,  # no expande entidades definidas en el documento
        load_dtd=False,        # no carga la definición de tipo de documento
        no_network=True,       # prohíbe cualquier acceso a la red
        huge_tree=True,        # admite documentos muy grandes
        collect_ids=False,     # no construye el índice de identificadores de lxml
    )
    parser.resolvers.add(ResolvedorSinRed())
    return parser


def crear_parser_html() -> etree.HTMLParser:
    """Crea un analizador HTML tolerante, para los documentos mal formados.

    El analizador de HTML entiende las entidades como ``&nbsp;``, que el
    analizador XML descartaría en silencio.
    """
    parser = etree.HTMLParser(recover=True, no_network=True, huge_tree=True)
    parser.resolvers.add(ResolvedorSinRed())
    return parser
