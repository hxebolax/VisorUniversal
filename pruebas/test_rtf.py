# -*- coding: utf-8 -*-
"""Pruebas del lector de RTF.

Los documentos se escriben aquí mismo, que en RTF es cómodo: es texto plano.
Así cada prueba enseña exactamente qué construcción del formato comprueba.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from formatos.rtf import ErrorRTF, LectorRTF  # noqa: E402

CABECERA = (r"{\rtf1\ansi\ansicpg1252\deff0"
            r"{\fonttbl{\f0\froman Times;}}")


def convertir(cuerpo: str, cabecera: str = CABECERA) -> str:
    """Convierte un trozo de RTF y devuelve su XHTML."""
    return LectorRTF((cabecera + cuerpo + "}").encode("cp1252")).a_html()


# ---------------------------------------------------------------------------
# Lo básico
# ---------------------------------------------------------------------------

def test_un_parrafo_sale_como_parrafo():
    assert convertir(r"\pard Hola.\par") == "<p>Hola.</p>"


def test_lo_que_no_es_rtf_se_rechaza():
    with pytest.raises(ErrorRTF):
        LectorRTF(b"{\\algo esto no es un RTF}")


def test_los_bytes_de_la_pagina_de_codigos_se_traducen():
    r"""«\'f1» es una eñe en la página 1252 y otra letra en otra página."""
    assert convertir(r"\pard A\'f1o.\par") == "<p>Año.</p>"


def test_se_respeta_la_pagina_de_codigos_que_declara_el_documento():
    cabecera = r"{\rtf1\ansi\ansicpg1251"
    # En la página cirílica, el mismo byte es otra letra.
    salida = LectorRTF((cabecera + r"\pard \'f1.\par}").encode("cp1252")).a_html()
    assert salida == "<p>с.</p>"


def test_un_caracter_unicode_no_sale_dos_veces():
    r"""Detrás de «\uN» va su repuesto para quien no entienda Unicode."""
    assert convertir(r"\pard \u241 \'f1.\par") == "<p>ñ.</p>"


def test_se_respeta_cuantos_caracteres_de_repuesto_hay():
    assert convertir(r"\pard \uc0\u241 .\par") == "<p>ñ.</p>"


# ---------------------------------------------------------------------------
# Formato del texto
# ---------------------------------------------------------------------------

def test_negrita_cursiva_y_subrayado():
    salida = convertir(r"\pard \b n\b0  \i c\i0  \ul s\ulnone .\par")

    assert "<strong>n</strong>" in salida
    assert "<em>c</em>" in salida
    assert "<u>s</u>" in salida


def test_un_trozo_partido_por_una_tilde_no_sale_en_tres_negritas():
    """El archivo parte el texto en cada byte raro; hay que volver a juntarlo."""
    salida = convertir(r"\pard \b Ma\'f1ana entera\b0 .\par")

    assert salida.count("<strong>") == 1
    assert "<strong>Mañana entera</strong>" in salida


def test_el_formato_se_devuelve_al_cerrar_la_llave():
    """Cada llave hereda el formato de fuera y lo devuelve al cerrarse."""
    salida = convertir(r"\pard normal {\b dentro} fuera\par")

    assert salida == "<p>normal <strong>dentro</strong> fuera</p>"


def test_el_texto_oculto_no_se_lee():
    assert convertir(r"\pard visible {\v escondido}.\par") == "<p>visible .</p>"


# ---------------------------------------------------------------------------
# Títulos
# ---------------------------------------------------------------------------

def test_el_nivel_de_esquema_hace_el_titulo():
    """Es el dato fiable: un número que dice de qué nivel es el párrafo."""
    assert convertir(r"\pard\outlinelevel0 Capítulo\par") == "<h1>Capítulo</h1>"
    assert convertir(r"\pard\outlinelevel2 Apartado\par") == "<h3>Apartado</h3>"


def test_sin_nivel_de_esquema_manda_el_nombre_del_estilo():
    """Hay documentos que no traen el nivel; ahí solo queda el nombre."""
    cabecera = CABECERA + r"{\stylesheet{\s0 Normal;}{\s3 heading 2;}}"
    assert convertir(r"\pard\s3 Un título\par", cabecera) == "<h2>Un título</h2>"


def test_el_nombre_del_estilo_vale_en_español():
    """Word traduce el nombre del estilo al idioma del que escribe."""
    cabecera = CABECERA + r"{\stylesheet{\s0 Normal;}{\s4 T\'edtulo 1;}}"
    assert convertir(r"\pard\s4 Capítulo\par", cabecera) == "<h1>Capítulo</h1>"


def test_el_nivel_nueve_quiere_decir_texto_normal():
    assert convertir(r"\pard\outlinelevel9 Solo un párrafo\par") == "<p>Solo un párrafo</p>"


# ---------------------------------------------------------------------------
# Listas, tablas y enlaces
# ---------------------------------------------------------------------------

def test_una_lista_con_vinetas():
    salida = convertir(r"\pard\ilvl0\ls1 Uno\par \pard\ilvl0\ls1 Dos\par")

    assert salida == "<ul><li>Uno</li><li>Dos</li></ul>"


def test_una_tabla_con_su_fila_de_encabezados():
    salida = convertir(
        r"\trowd\cellx3000\cellx6000"
        r"\pard\intbl A\cell\pard\intbl B\cell\row"
        r"\trowd\cellx3000\cellx6000"
        r"\pard\intbl 1\cell\pard\intbl 2\cell\row")

    assert "<th>A</th><th>B</th>" in salida
    assert "<td>1</td><td>2</td>" in salida


def test_un_enlace_conserva_su_direccion():
    salida = convertir(
        r"\pard Ir {\field{\*\fldinst{HYPERLINK \"https://ejemplo.org\"}}"
        r"{\fldrslt ahí}} ahora.\par")

    assert '<a href="https://ejemplo.org">ahí</a>' in salida


def test_un_campo_que_no_es_un_enlace_deja_su_texto():
    salida = convertir(
        r"\pard Página {\field{\*\fldinst{PAGE}}{\fldrslt 7}}.\par")

    assert "<a " not in salida
    assert "7" in salida


# ---------------------------------------------------------------------------
# Metadatos e imágenes
# ---------------------------------------------------------------------------

def test_se_leen_el_titulo_y_el_autor():
    lector = LectorRTF(
        (CABECERA + r"{\info{\title Un libro}{\author Mu\'f1oz}}"
         r"\pard Texto.\par}").encode("cp1252"))
    lector.a_html()

    assert lector.metadatos["titulo"] == "Un libro"
    assert lector.metadatos["autor"] == "Muñoz"


def test_una_imagen_se_guarda_y_deja_su_hueco():
    """Las imágenes van escritas en hexadecimal dentro del propio archivo."""
    png = ("89504e470d0a1a0a" + "00" * 24)
    lector = LectorRTF(
        (CABECERA + r"\pard {\pict\pngblip " + png + r"}\par}").encode("cp1252"))
    salida = lector.a_html()

    assert len(lector.imagenes) == 1
    assert lector.imagenes[0].startswith(b"\x89PNG")
    assert '<img src="rtf:0"' in salida


# ---------------------------------------------------------------------------
# Aguantar lo imperfecto
# ---------------------------------------------------------------------------

def test_un_archivo_con_las_llaves_sin_cerrar_se_lee_igual():
    """Un RTF a medias tiene que dar lo que tenga, no un error."""
    salida = LectorRTF(rb"{\rtf1\ansi\pard Empieza y no termina.\par").a_html()

    assert "Empieza y no termina." in salida


def test_las_tablas_de_fuentes_y_estilos_no_salen_en_el_texto():
    salida = convertir(r"\pard Texto.\par")

    assert "Times" not in salida
