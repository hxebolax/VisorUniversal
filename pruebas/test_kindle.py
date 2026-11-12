# -*- coding: utf-8 -*-
"""Pruebas de los formatos de Kindle: KFX, AZW3 y MOBI.

Se prueban las piezas de bajo nivel con archivos armados aquí mismo, byte a
byte.  Es la única forma de probar un formato binario sin depender de tener un
libro concreto en el disco: se escribe el archivo más pequeño que sea válido,
se lee, y se comprueba que sale lo que se metió.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from formatos import kindle, kindle_kfx, kindle_mobi  # noqa: E402


# ---------------------------------------------------------------------------
# El Ion binario del KFX
# ---------------------------------------------------------------------------

def _ion(cuerpo: bytes) -> bytes:
    """Un flujo Ion con su marca de comienzo."""
    return kindle_kfx.ION + cuerpo


def test_se_lee_una_cadena():
    assert kindle_kfx._Ion(_ion(b"\x84" + b"hola")).decodificar() == "hola"


def test_se_lee_un_entero_y_un_booleano():
    assert kindle_kfx._Ion(_ion(b"\x21\x2a")).decodificar() == 42
    assert kindle_kfx._Ion(_ion(b"\x11")).decodificar() is True


def test_se_lee_un_simbolo_como_su_numero():
    """La tabla que traduce los símbolos no viaja dentro del archivo."""
    assert kindle_kfx._Ion(_ion(b"\x71\x92")).decodificar() == "$146"


def test_se_lee_una_estructura_con_su_clave_y_su_valor():
    """El nombre va antes que el valor, y los dos avanzan sobre los mismos bytes.

    Es la prueba de un fallo real: escrito como «objeto[clave()] = valor()»,
    Python llama antes a «valor()» que a «clave()» y la estructura entera sale
    del revés.
    """
    # Estructura de 7 bytes: clave $10 -> "eh", clave $11 -> 5.
    cuerpo = b"\x8a\x82eh" + b"\x8b\x21\x05"
    datos = bytes([0xD0 | len(cuerpo)]) + cuerpo

    assert kindle_kfx._Ion(_ion(datos)).decodificar() == {"$10": "eh", "$11": 5}


def test_se_lee_una_lista():
    cuerpo = b"\x21\x01\x21\x02"
    datos = bytes([0xB0 | len(cuerpo)]) + cuerpo

    assert kindle_kfx._Ion(_ion(datos)).decodificar() == [1, 2]


def test_un_flujo_sin_su_marca_se_rechaza():
    with pytest.raises(kindle_kfx.ErrorKFX):
        kindle_kfx._Ion(b"esto no es Ion").decodificar()


# ---------------------------------------------------------------------------
# El contenedor KFX
# ---------------------------------------------------------------------------

def _contenedor(entidades: list[tuple[int, int, bytes]]) -> bytes:
    """Arma un contenedor KFX con las entidades que se le den."""
    tabla = b""
    cuerpo = b""
    for tipo, ident, datos in entidades:
        entidad = kindle_kfx.ENTIDAD + struct.pack("<H", 1) + struct.pack("<L", 10) + datos
        tabla += struct.pack("<LLQQ", ident, tipo, len(cuerpo), len(entidad))
        cuerpo += entidad
    cabecera = kindle_kfx.CONTENEDOR + struct.pack("<H", 2)
    relleno = kindle_kfx.ION + b"\x20"          # la información del contenedor
    largo = len(cabecera) + 4 + 8 + len(tabla) + len(relleno)
    return cabecera + struct.pack("<L", largo) + b"\0" * 8 + tabla + relleno + cuerpo


def test_se_leen_las_entidades_de_un_contenedor():
    datos = _contenedor([(145, 995, _ion(b"\x83abc")), (260, 854, _ion(b"\x83xyz"))])

    entidades = kindle_kfx._entidades(datos)
    assert [(tipo, ident) for tipo, ident, _d in entidades] == [(145, 995), (260, 854)]
    assert kindle_kfx._decodificar_entidad(entidades[0][2]) == "abc"


def test_un_archivo_que_no_es_kfx_se_rechaza():
    with pytest.raises(kindle_kfx.ErrorKFX):
        kindle_kfx._entidades(b"PK\x03\x04 esto es un zip")


def test_una_entidad_sin_ion_no_se_decodifica_pero_no_estorba():
    """Las que no llevan estructura son recursos: imágenes y fuentes."""
    entidad = kindle_kfx.ENTIDAD + struct.pack("<H", 1) + struct.pack("<L", 10) + b"\xff\xd8jpeg"

    assert kindle_kfx._decodificar_entidad(entidad) is None
    assert kindle_kfx._datos_de_entidad(entidad) == b"\xff\xd8jpeg"


# ---------------------------------------------------------------------------
# Las medidas de una imagen
# ---------------------------------------------------------------------------

def test_se_leen_las_medidas_de_un_png():
    png = b"\x89PNG\r\n\x1a\n" + b"\0" * 8 + struct.pack(">LL", 320, 240)

    assert kindle_kfx._medidas(png) == (320, 240)


def test_se_leen_las_medidas_de_un_jpeg():
    # Marcador de comienzo de cuadro con el alto y el ancho detrás.
    jpeg = b"\xff\xd8" + b"\xff\xc0" + struct.pack(">H", 17) + b"\x08" + \
        struct.pack(">HH", 200, 400) + b"\0" * 8

    assert kindle_kfx._medidas(jpeg) == (400, 200)


def test_de_una_imagen_desconocida_no_se_afirma_ninguna_medida():
    assert kindle_kfx._medidas(b"GIF89a....") == (None, None)


# ---------------------------------------------------------------------------
# La base de datos Palm de los MOBI
# ---------------------------------------------------------------------------

def _palm(registros: list[bytes]) -> bytes:
    """Arma una base de datos Palm con esos registros."""
    cabecera = b"prueba".ljust(32, b"\0") + b"\0" * 28 + b"BOOKMOBI" + b"\0" * 8
    cabecera += struct.pack(">H", len(registros))
    inicio = len(cabecera) + len(registros) * 8
    tabla = b""
    posicion = inicio
    for registro in registros:
        tabla += struct.pack(">L", posicion) + b"\0\0\0\0"
        posicion += len(registro)
    return cabecera + tabla + b"".join(registros)


def test_se_parte_una_base_de_datos_palm_en_sus_registros():
    datos = _palm([b"primero", b"segundo", b"tercero"])

    assert kindle_mobi._registros(datos) == [b"primero", b"segundo", b"tercero"]


def test_un_archivo_recortado_no_revienta():
    with pytest.raises(kindle_mobi.ErrorMobi):
        kindle_mobi._registros(b"cuatro")


# ---------------------------------------------------------------------------
# La compresión PalmDOC
# ---------------------------------------------------------------------------

def test_se_descomprime_un_texto_sin_comprimir():
    assert kindle_mobi._descomprimir_palmdoc(b"hola") == b"hola"


def test_se_descomprime_una_repeticion():
    """La orden de dos bytes dice «vuelve tanto atrás y copia tanto»."""
    # «abcabc»: se escribe «abc» y luego se copia desde tres atrás, tres bytes.
    orden = 0x8000 | (3 << 3) | (3 - 3)
    datos = b"abc" + struct.pack(">H", orden)

    assert kindle_mobi._descomprimir_palmdoc(datos) == b"abcabc"


def test_se_descomprime_el_atajo_del_espacio():
    """De 0xc0 a 0xff, un byte vale por un espacio y una letra."""
    assert kindle_mobi._descomprimir_palmdoc(bytes([0xC0 | ord("a")])) == b" a"


# ---------------------------------------------------------------------------
# Los datos de cola de cada registro
# ---------------------------------------------------------------------------

def test_sin_banderas_no_se_quita_nada():
    assert kindle_mobi._sin_cola(b"texto", 0) == b"texto"


def test_se_quitan_los_caracteres_partidos_entre_dos_registros():
    """El último bit dice que al final hay bytes de un carácter a medias."""
    # El byte de la cuenta dice cuántos bytes sobran **además de él**, así que
    # con dos bytes de sobra pone un dos y se quitan tres en total.
    registro = b"texto" + b"XY" + bytes([2])

    assert kindle_mobi._sin_cola(registro, 1) == b"texto"


def test_se_quita_un_dato_de_cola_con_su_tamano_al_final():
    """Cada dato de cola guarda cuánto ocupa, escrito del revés."""
    # Tres bytes de datos más el byte que dice «cuatro en total».
    registro = b"texto" + b"abc" + bytes([0x80 | 4])

    assert kindle_mobi._sin_cola(registro, 0b10) == b"texto"


# ---------------------------------------------------------------------------
# El armado de las secciones
# ---------------------------------------------------------------------------

def test_un_azw3_vuelve_a_coser_sus_fragmentos_dentro_del_cuerpo():
    """El esqueleto trae el cuerpo vacío y los párrafos van detrás."""
    trozo = (b"<html><head><title>x</title></head><body></body></html>"
             b"<p>uno</p><p>dos</p>")

    cosido = kindle_mobi._coser_fragmentos(trozo)
    assert b"<body><p>uno</p><p>dos</p></body>" in cosido


def test_la_hoja_de_estilo_del_final_no_se_lee_como_texto():
    """Detrás del último archivo van los flujos, que no son marcado."""
    trozo = (b"<html><body></body></html><p>uno</p>"
             b"@page { margin: 0 } @font-face { font-family: X }")

    cosido = kindle_mobi._coser_fragmentos(trozo)
    assert b"@page" not in cosido
    assert b"<p>uno</p>" in cosido


def test_un_trozo_sin_declaracion_xml_recibe_una_sola():
    datos = kindle_mobi._preparar(b"<html><body><p>hola</p></body></html>", "utf-8")

    assert datos.count(b"<?xml") == 1


def test_un_trozo_con_su_propia_declaracion_no_recibe_otra():
    """Dos declaraciones seguidas no son XML válido y el archivo se pierde."""
    crudo = b'<?xml version="1.0" encoding="UTF-8"?>\n<html><body><p>a</p></body></html>'

    assert kindle_mobi._preparar(crudo, "utf-8").count(b"<?xml") == 1


def test_el_ancla_de_mobi_y_el_destino_de_un_enlace_se_llaman_igual():
    """Un enlace «filepos» y una entrada del índice llegan al mismo sitio."""
    preparado = kindle_mobi._preparar(
        b'<html><body><a filepos=0000001234>ir</a></body></html>', "utf-8")

    assert b'href="#%s"' % kindle_mobi.ancla_de(1234).encode() in preparado


# ---------------------------------------------------------------------------
# Reconocer el formato
# ---------------------------------------------------------------------------

def test_se_reconoce_un_kfx_por_dentro_y_no_por_su_nombre(tmp_path):
    """Un «.azw» puede ser lo viejo o un KFX: lo dicen los primeros bytes."""
    destino = tmp_path / "libro.azw"
    destino.write_bytes(kindle_kfx.CONTENEDOR + b"\x02\x00" + b"\0" * 40)

    assert kindle._clase_de(destino) == "kfx"


def test_se_reconoce_un_mobi_por_su_tipo_de_base_de_datos(tmp_path):
    destino = tmp_path / "libro.azw"
    destino.write_bytes(_palm([b"algo"]))

    assert kindle._clase_de(destino) == "palm"


def test_un_archivo_cualquiera_no_pasa_por_libro_de_kindle(tmp_path):
    destino = tmp_path / "cosa.azw3"
    destino.write_bytes(b"esto no es un libro" + b"\0" * 80)

    assert kindle._clase_de(destino) == ""


def test_el_analizador_reclama_las_extensiones_de_kindle():
    analizador = kindle.AnalizadorKindle()

    for extension in (".kfx", ".kfx-zip", ".azw", ".azw3", ".mobi", ".prc"):
        assert extension in analizador.extensiones
