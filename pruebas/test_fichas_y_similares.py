# -*- coding: utf-8 -*-
"""Pruebas de la ficha a la carta y de los libros similares.

Lo que se comprueba es lo que se notaría sin que nadie supiera por qué: que una
elección guardada con datos que ya no existen deje la ficha vacía, que la
sinopsis se pegue al dato de al lado, que el CSV llegue a Excel con las tildes
rotas o que «De la misma serie» no encuentre la serie por una tilde.
"""

from __future__ import annotations

import csv

from nucleo import biblioteca
from nucleo import biblioteca_ficha as fichas


def _libro(**datos):
    libro = biblioteca.Libro(datos.pop("ruta", "C:/libros/harry1.epub"),
                             titulo=datos.pop("titulo", "Harry Potter y la piedra filosofal"),
                             autor=datos.pop("autor", "J. K. Rowling"))
    libro.serie = datos.pop("serie", "Harry Potter")
    libro.serie_indice = datos.pop("serie_indice", 1.0)
    for nombre, valor in datos.items():
        setattr(libro, nombre, valor)
    libro.existe = True
    return libro


FICHA = {
    "comentarios": "Un niño descubre que es mago.",
    "editorial": "Salamandra",
    "isbn": "9788478884452",
    "identificadores": {"isbn": "9788478884452", "goodreads": "3"},
    "extra": {"Leído en": "2001"},
}


# --- qué datos y en qué orden ---------------------------------------------------

def test_sin_eleccion_salen_todos_en_el_orden_de_fabrica():
    campos = fichas.campos_elegidos(None)
    assert campos[:4] == ["titulo", "serie", "autor", "sinopsis"]
    assert len(campos) == len(fichas.CAMPOS)


def test_lo_guardado_que_no_vale_se_descarta():
    assert fichas.campos_elegidos(["autor", "inventado", "autor", "titulo"]) == [
        "autor", "titulo"]
    # Si no queda nada, todos: una ficha vacía no le sirve a nadie.
    assert fichas.campos_elegidos(["inventado"]) == fichas.campos_elegidos(None)
    assert fichas.campos_elegidos("titulo") == fichas.campos_elegidos(None)


def test_orden_completo_pone_primero_los_visibles():
    orden = fichas.orden_completo(["sinopsis", "titulo"])
    assert orden[:2] == [("sinopsis", True), ("titulo", True)]
    assert all(not visible for _clave, visible in orden[2:])
    assert len(orden) == len(fichas.CAMPOS)


# --- componer -----------------------------------------------------------------------

def test_la_ficha_corta_lleva_solo_lo_elegido_y_en_su_orden():
    texto = fichas.componer(_libro(), FICHA, ["autor", "titulo"])
    assert texto.splitlines() == ["Autores: J. K. Rowling",
                                  "Título: Harry Potter y la piedra filosofal"]


def test_la_sinopsis_va_en_su_propio_parrafo():
    texto = fichas.componer(_libro(), FICHA, ["titulo", "sinopsis", "editorial"])
    assert texto.splitlines() == [
        "Título: Harry Potter y la piedra filosofal",
        "",
        "Sinopsis:",
        "Un niño descubre que es mago.",
        "",
        "Editorial: Salamandra",
    ]


def test_los_datos_vacios_no_dejan_lineas():
    libro = _libro(serie="")
    texto = fichas.componer(libro, {}, ["serie", "sinopsis", "editorial"])
    assert texto == ""


def test_identificadores_y_columnas_propias():
    texto = fichas.componer(_libro(), FICHA, ["identificadores", "extra"])
    assert "ISBN: 9788478884452" in texto
    assert "Identificador goodreads: 3" in texto
    assert "Leído en: 2001" in texto


# --- exportar -----------------------------------------------------------------------

def test_exportar_a_csv_con_bom_y_punto_y_coma(carpeta):
    destino = carpeta / "fichas.csv"
    libros = [_libro(), _libro(ruta="C:/libros/harry2.epub",
                              titulo="Harry Potter y la cámara secreta", serie_indice=2.0)]
    escritas = fichas.exportar(libros, ["titulo", "serie", "editorial"], destino,
                               fichas.CSV, conexion=_ConexionFalsa())
    assert escritas == 2
    crudo = destino.read_bytes()
    assert crudo.startswith(b"\xef\xbb\xbf")         # BOM, para que Excel lea las tildes
    filas = list(csv.reader(destino.read_text(encoding="utf-8-sig").splitlines(),
                            delimiter=";"))
    assert filas[0] == ["Título", "Serie", "Editorial"]
    assert filas[2][:2] == ["Harry Potter y la cámara secreta", "Harry Potter 2"]


def test_exportar_a_texto_separa_las_fichas(carpeta):
    destino = carpeta / "fichas.txt"
    libros = [_libro(), _libro(ruta="C:/libros/otro.epub", titulo="Otro")]
    fichas.exportar(libros, ["titulo"], destino, fichas.TEXTO, conexion=_ConexionFalsa())
    texto = destino.read_text(encoding="utf-8")
    assert fichas.SEPARADOR in texto
    assert "Título: Otro" in texto


def test_exportar_se_puede_cancelar(carpeta):
    destino = carpeta / "fichas.txt"
    libros = [_libro(ruta="C:/libros/%d.epub" % n) for n in range(5)]
    escritas = fichas.exportar(libros, ["titulo"], destino, cancelado=lambda: True,
                               conexion=_ConexionFalsa())
    assert escritas == 0


def test_formato_por_nombre():
    assert fichas.formato_por_nombre("a.CSV", 0) == fichas.CSV
    assert fichas.formato_por_nombre("a.txt", 1) == fichas.TEXTO
    assert fichas.formato_por_nombre("a", 1) == fichas.CSV
    assert fichas.formato_por_nombre("a", 0) == fichas.TEXTO


class _ConexionFalsa:
    """Una base de datos sin ningún libro: la ficha sale solo de lo que sabe el libro."""

    def execute(self, *argumentos):
        return self

    def fetchone(self):
        return None

    def close(self):
        pass


# --- libros similares -------------------------------------------------------------

def test_similares_ofrece_serie_cada_autor_y_coleccion():
    libro = _libro(autor="Terry Pratchett & Neil Gaiman", serie="", coleccion="Fantasía",
                   etiquetas="humor, fantasía")
    opciones = biblioteca.similares(libro)
    campos = [(campo, valor) for campo, valor, _clave in opciones]
    assert ("autor", "Terry Pratchett") in campos
    assert ("autor", "Neil Gaiman") in campos
    assert ("coleccion", "Fantasía") in campos
    assert ("etiquetas", "humor") in campos
    assert not any(campo == "serie" for campo, _valor in campos)


def test_la_clave_de_similares_es_la_del_grupo():
    """La clave tiene que ser la misma con la que indice_de_grupos reparte los libros."""
    libros = [_libro(), _libro(ruta="C:/b.epub", serie="HARRY POTTER"),
              _libro(ruta="C:/c.epub", serie="Mundodisco")]
    _grupos, reparto = biblioteca.indice_de_grupos(libros, "serie")
    clave = [k for campo, _v, k in biblioteca.similares(libros[0]) if campo == "serie"][0]
    assert len(reparto[clave]) == 2


def test_las_etiquetas_ofrecidas_tienen_tope():
    libro = _libro(etiquetas=", ".join("etiqueta %d" % n for n in range(40)))
    etiquetas = [v for campo, v, _k in biblioteca.similares(libro) if campo == "etiquetas"]
    assert len(etiquetas) == biblioteca.MAX_ETIQUETAS_SIMILARES


def test_todas_las_maneras_de_similares_son_agrupaciones():
    agrupaciones = {clave for clave, _nombre in biblioteca.AGRUPACIONES}
    assert {campo for campo, _nombre in biblioteca.SIMILARES} <= agrupaciones
