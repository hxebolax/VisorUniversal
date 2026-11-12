# -*- coding: utf-8 -*-
"""Preparar una página antes de reconocerla.

Un OCR no lee la página que se ve: lee la que se le da.  Y darle la imagen tal
cual sale del PDF no siempre es lo mejor, sobre todo cuando el documento tiene
color, que es justo el caso de un folleto: letra blanca sobre rojo, precios
sobre un círculo amarillo, títulos sobre una foto.

Con las medidas hechas sobre un folleto real, pasar la página a **gris y
subirle el contraste** llevó los productos leídos con su precio de 7 a 9 sobre
14, y la basura —símbolos sueltos que el motor saca de los adornos— de 8 a 2.
Es la mejora más grande de todas las que se probaron, por encima de cambiar el
modo de segmentación o el motor.

Por qué funciona: al pasar a gris, un fondo de color saturado y una letra clara
acaban a distancias de luminosidad razonables, y el contraste separa lo que
queda.  Binarizar del todo también se probó y sale peor: la letra fina se
rompe.

Todo esto es opcional y se ajusta desde Opciones, porque el documento perfecto
para un ajuste es el peor para otro: un escaneado en blanco y negro de un libro
antiguo no necesita nada de esto y sale mejor sin tocarlo.

Necesita Pillow.  Si no está, no pasa nada: se devuelve la imagen sin tocar y
el reconocimiento sigue su curso.
"""

from __future__ import annotations

import io

from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

#: Contraste que mejor resultado dio en las pruebas.  1 es no tocar nada.
CONTRASTE_NORMAL = 3.0

#: Umbral de binarización de fábrica, sobre 255.
UMBRAL_NORMAL = 160


def disponible() -> bool:
    """Si se puede preparar la imagen antes de reconocerla."""
    try:
        import PIL  # noqa: F401

        return True
    except Exception:
        return False


def preparar(datos_png: bytes, gris: bool = True, contraste: float = CONTRASTE_NORMAL,
             binarizar: bool = False, umbral: int = UMBRAL_NORMAL) -> bytes:
    """Devuelve la imagen lista para el OCR.

    :param datos_png: Imagen en PNG.
    :param gris: Pasar a escala de grises.
    :param contraste: Cuánto se sube el contraste.  1 es no tocarlo.
    :param binarizar: Dejar la imagen en blanco y negro puro.
    :param umbral: A partir de qué luminosidad se considera blanco.
    :return: La imagen preparada, o la de entrada si no se pudo hacer nada.
    """
    if not (gris or binarizar or abs(contraste - 1.0) > 0.01):
        return datos_png
    try:
        from PIL import Image, ImageEnhance
    except ImportError:
        log.debug("Sin Pillow: la página se reconoce sin preparar")
        return datos_png

    try:
        imagen = Image.open(io.BytesIO(datos_png))
        if gris or binarizar:
            imagen = imagen.convert("L")
        if abs(contraste - 1.0) > 0.01:
            imagen = ImageEnhance.Contrast(imagen).enhance(float(contraste))
        if binarizar:
            limite = max(1, min(254, int(umbral)))
            imagen = imagen.point(lambda valor: 255 if valor > limite else 0, mode="L")
        salida = io.BytesIO()
        imagen.save(salida, format="PNG", optimize=False)
        return salida.getvalue()
    except Exception as error:
        log.debug("No se ha podido preparar la imagen: %s", error)
        return datos_png
