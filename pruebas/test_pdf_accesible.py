# -*- coding: utf-8 -*-
"""Pruebas de la lectura accesible de los PDF etiquetados.

Aquí no se abre ningún PDF: montar uno etiquetado a mano sería más código que
lo que se prueba, y el motor que lo lee es de otros.  Lo que sí es propio, y lo
que se rompe al tocarlo, es todo lo de alrededor: cómo se normalizan los
códigos de idioma, cómo se elige la voz de un fragmento, cómo se convierten los
marcadores del PDF en el índice del documento y cómo el conversor recoge los
cambios de idioma del XHTML.
"""

import pytest

from formatos import pdf_etiquetado
from formatos.conversor import ConversorXHTML
from formatos.pdf import AnalizadorPDF
from nucleo import voz
from nucleo.documento import Documento
from nucleo.marcas import Marca, TipoMarca


# ---------------------------------------------------------------------------
# Códigos de idioma
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("crudo, esperado", [
    ("ES", "es"),
    ("EN-GB", "en-GB"),
    ("pt_br", "pt-BR"),
    ("  fr-FR  ", "fr-FR"),
    ("", ""),
    ("-", ""),
])
def test_los_codigos_de_idioma_se_escriben_todos_igual(crudo, esperado):
    """Los PDF los escriben de cualquier manera y hay que poder compararlos."""
    assert pdf_etiquetado.normalizar_idioma(crudo) == esperado


@pytest.mark.parametrize("lcid, esperado", [
    ("40a", "es-ES"),
    ("809", "en-GB"),
    ("409", "en-US"),
    ("416", "pt-BR"),
    ("409;9", "en-US"),      # una voz que sirve para varios idiomas
    ("", ""),
    ("zz", ""),
])
def test_el_idioma_de_una_voz_sale_de_su_identificador(lcid, esperado):
    assert voz.idioma_de_lcid(lcid) == esperado


@pytest.mark.parametrize("de_la_voz, buscado, nota", [
    ("en-GB", "en-GB", 2),
    ("en-US", "en-GB", 1),
    ("en", "en-GB", 1),
    ("es-ES", "en-GB", 0),
    ("", "en", 0),
    ("en", "", 0),
])
def test_se_prefiere_la_voz_del_pais_exacto(de_la_voz, buscado, nota):
    assert voz.parecido(de_la_voz, buscado) == nota


# ---------------------------------------------------------------------------
# El conversor recoge los cambios de idioma
# ---------------------------------------------------------------------------

def _convertir(cuerpo: str, idioma: str = "es"):
    """Convierte un cuerpo XHTML suelto, como el de un capítulo de EPUB."""
    documento = ('<?xml version="1.0" encoding="utf-8"?>'
                 '<html xmlns="http://www.w3.org/1999/xhtml" lang="%s"><body>%s</body></html>'
                 % (idioma, cuerpo))
    return ConversorXHTML().convertir(documento.encode("utf-8"))


def test_se_marca_el_tramo_que_esta_en_otro_idioma():
    resultado = _convertir('<p>Dijo <span lang="en-GB">to be or not to be</span> y calló.</p>')
    idiomas = [m for m in resultado.marcas if m.tipo is TipoMarca.IDIOMA]
    assert len(idiomas) == 1
    marca = idiomas[0]
    assert marca.texto == "en-GB"
    tramo = resultado.texto[marca.posicion:marca.posicion + marca.longitud]
    assert tramo.strip() == "to be or not to be"


def test_el_idioma_que_no_cambia_no_deja_marca():
    """Marcar cada párrafo con el idioma del libro no diría nada y costaría."""
    resultado = _convertir('<div lang="es"><p lang="es">Hola</p></div>')
    assert [m for m in resultado.marcas if m.tipo is TipoMarca.IDIOMA] == []


def test_los_idiomas_anidados_se_marcan_por_dentro_y_por_fuera():
    resultado = _convertir(
        '<blockquote lang="fr-FR">Je pense <span lang="la">cogito</span> donc.</blockquote>')
    codigos = sorted(m.texto for m in resultado.marcas if m.tipo is TipoMarca.IDIOMA)
    assert codigos == ["fr-FR", "la"]


def test_el_idioma_se_lee_tambien_del_xml_lang():
    resultado = _convertir(
        '<p>Una <span xml:lang="IT-it">citazione</span> corta.</p>')
    idiomas = [m for m in resultado.marcas if m.tipo is TipoMarca.IDIOMA]
    assert [m.texto for m in idiomas] == ["it-IT"]


# ---------------------------------------------------------------------------
# Saber en qué idioma está el cursor
# ---------------------------------------------------------------------------

def test_se_encuentra_la_marca_de_idioma_que_cubre_una_posicion():
    documento = Documento(
        texto="a" * 100,
        marcas=[
            Marca(TipoMarca.IDIOMA, 10, "en-GB", "", 0, 20),
            Marca(TipoMarca.IDIOMA, 60, "fr-FR", "", 0, 10),
        ],
    )
    dentro = documento.marcas.marca_que_cubre(TipoMarca.IDIOMA, 15)
    assert dentro is not None and dentro.texto == "en-GB"
    assert documento.marcas.marca_que_cubre(TipoMarca.IDIOMA, 40) is None
    assert documento.marcas.marca_que_cubre(TipoMarca.IDIOMA, 65).texto == "fr-FR"


def test_entre_idiomas_anidados_gana_el_de_dentro():
    documento = Documento(
        texto="a" * 100,
        marcas=[
            Marca(TipoMarca.IDIOMA, 0, "fr-FR", "", 0, 50),
            Marca(TipoMarca.IDIOMA, 20, "la", "", 0, 10),
        ],
    )
    assert documento.marcas.marca_que_cubre(TipoMarca.IDIOMA, 25).texto == "la"


# ---------------------------------------------------------------------------
# El índice sale de los marcadores del PDF
# ---------------------------------------------------------------------------

def _libro_con_paginas(cuantas: int) -> Documento:
    """Documento de mentira con un ancla por página, como los que monta el PDF."""
    documento = Documento(texto="x" * (cuantas * 100), marcas=[])
    documento.posiciones_id = {
        "pagina-%d" % numero: (numero - 1) * 100 for numero in range(1, cuantas + 1)
    }
    return documento


def test_los_marcadores_del_pdf_se_vuelven_indice_con_su_jerarquia():
    marcadores = [
        (0, "Portada", 1),
        (0, "1. Introducción", 3),
        (1, "1.1. Antecedentes", 4),
        (1, "1.2. Objetivos", 5),
        (0, "2. Resultados", 8),
    ]
    indice = AnalizadorPDF._indice(marcadores, _libro_con_paginas(10))
    assert [entrada.titulo for entrada in indice] == [
        "Portada", "1. Introducción", "2. Resultados"]
    assert [hijo.titulo for hijo in indice[1].hijos] == ["1.1. Antecedentes", "1.2. Objetivos"]
    assert indice[1].posicion == 200          # la página 3 empieza en el carácter 200


def test_un_marcador_a_una_pagina_que_no_existe_se_descarta():
    """Pasa en los PDF a los que se les han quitado páginas: el destino se queda huérfano."""
    indice = AnalizadorPDF._indice([(0, "Capítulo perdido", 99)], _libro_con_paginas(3))
    assert indice == []


def test_sin_marcadores_no_se_toca_el_indice_que_ya_hubiera():
    assert AnalizadorPDF._indice([], _libro_con_paginas(3)) == []


# ---------------------------------------------------------------------------
# El informe de accesibilidad
# ---------------------------------------------------------------------------

def test_el_informe_dice_que_el_pdf_no_esta_etiquetado():
    from formatos.pdf import Etiquetado

    informe = Etiquetado()
    informe.paginas_miradas = 12
    assert "sin etiquetar" in informe.resumen()


def test_el_informe_avisa_cuando_la_estructura_se_ha_descartado():
    from formatos.pdf import Etiquetado

    informe = Etiquetado()
    informe.marcado = True
    informe.paginas_miradas = 12
    informe.paginas_con_arbol = 12
    informe.cobertura = 0.20
    informe.usar = False
    resumen = informe.resumen()
    assert "20 %" in resumen
    assert "descartada" in resumen
