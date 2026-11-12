# -*- coding: utf-8 -*-
"""Pruebas de lectura del formato BRA en texto de tinta."""

from pathlib import Path
import sys

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from formatos import braille  # noqa: E402,F401  registra el analizador
from formatos.base import ErrorFormato, analizar  # noqa: E402
from nucleo.marcas import TipoMarca  # noqa: E402


def test_traduce_la_tabla_bra_espanola_a_texto_normal():
    # En BRA: A empieza con {, ñ es A4, á es (, ú es ) y ó es 0.
    datos = b"{hola, se\xa4or. #abc (rbol, m)sica y acci0n."

    assert braille.a_tinta(datos) == [
        "Hola, señor. 123 árbol, música y acción."
    ]


def test_interpreta_mayusculas_interrogaciones_y_ordinales():
    datos = b"{{titulo\r\n\r\n?{qu$ tal? {es la #:a prueba a|."

    assert braille.a_tinta(datos) == [
        "TITULO\n\n¿Qué tal? Es la 3ª prueba a)."
    ]


def test_interpreta_la_variante_bra_antigua_de_la_once():
    datos = (
        b"{el {se7or escribi0 #aj.jjj p(ginas en el a7o #aiih.\r\n"
        b"{ling8ista. 2{sud(frica|. }{obra}. <{hola<. !{bien!"
    )

    assert braille.a_tinta(datos) == [
        'El Señor escribió 10.000 páginas en el año 1998. Lingüista. '
        '(Sudáfrica). Obra. "Hola". ¡Bien!'
    ]


def test_recompone_lineas_y_palabras_partidas_por_el_ancho_braille():
    datos = (b"{este es un p(rrafo que contin)a en la\r\n"
             b"l/nea siguiente y una palabra par-\r\n"
             b"tida.\r\n\r\n  {nuevo p(rrafo.")

    assert braille.a_tinta(datos) == [
        "Este es un párrafo que continúa en la línea siguiente y una palabra "
        "partida.\n\nNuevo párrafo."
    ]


def test_el_analizador_conserva_las_paginas(tmp_path):
    ruta = tmp_path / "libro.bra"
    ruta.write_bytes(b"{primera p(gina.\f{segunda p(gina.")

    documento = analizar(ruta)

    assert documento.texto == "Primera página.\nSegunda página."
    assert documento.metadatos.idioma == "es"
    assert documento.marcas.cantidad(TipoMarca.SALTO_PAGINA) == 2


def test_detecta_paginas_fijas_y_quita_folios_mecanicos(tmp_path):
    ruta = tmp_path / "antiguo.bra"
    pagina_1 = [b"  {primera p(gina."] + [b""] * 27 + [b"                          #cjcf-#a{i"]
    pagina_2 = [b"                                #b"] + [b"  {segunda p(gina."] + [b""] * 27
    ruta.write_bytes(b"\r\n".join(pagina_1 + pagina_2))

    documento = analizar(ruta)

    assert documento.texto == "Primera página.\nSegunda página."
    assert documento.marcas.cantidad(TipoMarca.SALTO_PAGINA) == 2
    assert "3036" not in documento.texto


def test_una_pagina_html_renombrada_no_se_hace_pasar_por_bra(tmp_path):
    ruta = tmp_path / "descarga.bra"
    ruta.write_bytes(
        b"<!DOCTYPE html><html><head><title>Pagina no encontrada - Wormhole"
        b"</title></head><body>Error</body></html>"
    )

    with pytest.raises(ErrorFormato, match="no contiene braille"):
        analizar(ruta)
