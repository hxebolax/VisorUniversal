# -*- coding: utf-8 -*-
"""Pruebas de la exportación a audio.

No se graba nada: hablar con SAPI y comprimir a MP3 depende del equipo.  Lo que
se prueba es el reparto en capítulos, los nombres de archivo y el troceado del
texto, que es donde puede perderse contenido sin que nadie lo note.
"""

import pytest

from nucleo import audio_libro
from nucleo.marcas import ColeccionMarcas, Marca, TipoMarca


class Metadatos:
    titulo = "El libro"


class DocumentoDePrueba:
    """Lo mínimo que el exportador necesita de un documento."""

    def __init__(self, texto, marcas=()):
        self.texto = texto
        self.metadatos = Metadatos()
        self.marcas = ColeccionMarcas(marcas)

    def primera_linea_con_texto(self, posicion):
        return self.texto[posicion:posicion + 20].split("\n")[0]


# --- nombres de archivo -------------------------------------------------------

@pytest.mark.parametrize("crudo, esperado", [
    ("Capítulo 1", "Capítulo 1"),
    ('Cap: 1 <El "reino"> / final', "Cap 1 El reino  final"),
    ("   ", "Sin título"),
    ("", "Sin título"),
    ("punto final.", "punto final"),
])
def test_nombre_seguro(crudo, esperado):
    assert audio_libro.nombre_seguro(crudo) == esperado


def test_nombre_seguro_recorta_sin_partir_palabras():
    nombre = audio_libro.nombre_seguro("palabra " * 30, maximo=20)
    assert len(nombre) <= 20
    assert not nombre.endswith("pala")


# --- reparto en capítulos ------------------------------------------------------

def test_sin_marcas_todo_es_un_capitulo():
    documento = DocumentoDePrueba("Un texto cualquiera.")
    capitulos = audio_libro.capitulos_de(documento)
    assert len(capitulos) == 1
    assert capitulos[0].titulo == "El libro"
    assert capitulos[0].inicio == 0
    assert capitulos[0].fin == len(documento.texto)


def test_se_parte_por_secciones():
    texto = "Portada.\nUno dos tres.\nCuatro cinco seis."
    marcas = [
        Marca(TipoMarca.SALTO_SECCION, 9, "Primero", "", 0, 0),
        Marca(TipoMarca.SALTO_SECCION, 23, "Segundo", "", 0, 0),
    ]
    capitulos = audio_libro.capitulos_de(DocumentoDePrueba(texto, marcas))
    # Lo que hay antes del primer corte no se pierde: es un capítulo más.
    assert len(capitulos) == 3
    assert capitulos[0].inicio == 0 and capitulos[0].fin == 9
    assert capitulos[1].titulo == "Primero"
    assert capitulos[2].fin == len(texto)


def test_una_sola_seccion_no_sirve_para_partir():
    """Con un único corte no hay nada que repartir; se usa todo el documento."""
    texto = "Uno dos tres."
    marcas = [Marca(TipoMarca.SALTO_SECCION, 0, "Único", "", 0, 0)]
    capitulos = audio_libro.capitulos_de(DocumentoDePrueba(texto, marcas))
    assert len(capitulos) == 1


def test_se_usan_los_encabezados_si_no_hay_secciones():
    texto = "Uno dos tres. Cuatro cinco seis."
    marcas = [
        Marca(TipoMarca.ENCABEZADO1, 0, "Uno", "", 1, 3),
        Marca(TipoMarca.ENCABEZADO1, 14, "Cuatro", "", 1, 6),
    ]
    capitulos = audio_libro.capitulos_de(DocumentoDePrueba(texto, marcas))
    assert [c.titulo for c in capitulos] == ["Uno", "Cuatro"]


def test_los_capitulos_cubren_el_documento_entero():
    """Ni un carácter fuera: lo que no se exporta, no se oye."""
    texto = "Cero. " + "Uno dos tres. " * 5
    marcas = [Marca(TipoMarca.SALTO_SECCION, posicion, "C", "", 0, 0)
              for posicion in (6, 20, 48)]
    capitulos = audio_libro.capitulos_de(DocumentoDePrueba(texto, marcas))
    cubierto = sum(capitulo.largo for capitulo in capitulos)
    assert cubierto == len(texto)
    assert capitulos[0].inicio == 0
    assert capitulos[-1].fin == len(texto)


def test_documento_entero():
    documento = DocumentoDePrueba("Uno.\nDos.")
    capitulos = audio_libro.documento_entero(documento)
    assert len(capitulos) == 1
    assert capitulos[0].largo == len(documento.texto)


def test_documento_vacio():
    assert audio_libro.capitulos_de(DocumentoDePrueba("")) == []


# --- troceado del texto ---------------------------------------------------------

def test_los_trozos_no_pierden_texto():
    texto = "Una frase. Otra frase. Y una tercera. " * 30
    trozos = audio_libro._trozos(texto)
    juntos = " ".join(trozos)
    # Las palabras están todas, aunque los espacios se hayan normalizado.
    assert len(juntos.split()) == len(texto.split())


def test_los_trozos_cortan_por_frases():
    texto = "Frase una. Frase dos. " * 200
    trozos = audio_libro._trozos(texto)
    assert len(trozos) > 1
    for trozo in trozos:
        assert trozo.strip().endswith(".")


def test_texto_sin_frases_reconocibles_se_dice_igual():
    texto = "1 2 3 4 5"
    assert audio_libro._trozos(texto) == ["1 2 3 4 5"]


def test_texto_vacio_no_da_trozos():
    assert audio_libro._trozos("   ") == []


def test_tamano_total_ignora_lo_que_no_existe(carpeta):
    uno = carpeta / "a.mp3"
    uno.write_bytes(b"12345")
    total = audio_libro.tamano_total([uno, carpeta / "no_existe.mp3"])
    assert total == 5
