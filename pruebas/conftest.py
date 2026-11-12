# -*- coding: utf-8 -*-
"""Preparación común de las pruebas.

Aquí se hacen tres cosas, y las tres hay que hacerlas **antes** de que
``pytest`` importe ningún módulo del programa:

1. Poner ``src`` en la ruta de importación, porque el programa se importa como
   ``nucleo.algo`` y no como ``src.nucleo.algo``.
2. Elegir el idioma, porque las tablas de atajos y los nombres de los prompts
   se construyen al importar sus módulos y para entonces la traducción tiene
   que estar puesta.  Se fija **español** a propósito: las pruebas comparan
   textos y no deben depender del idioma del equipo donde se lancen.
3. Arrancar el registro en un nivel que no llene la salida.

Además se ofrecen dos accesorios: ``carpeta`` para escribir archivos de usar y
tirar, y ``aplicacion`` para las pruebas que necesitan una ventana de wxPython.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ / "src"))

from nucleo import idioma, registro, rutas  # noqa: E402

rutas.preparar_estructura()
registro.iniciar("ERROR", "pruebas")
idioma.instalar("es")


@pytest.fixture
def carpeta(tmp_path: Path) -> Path:
    """Carpeta vacía donde escribir lo que haga falta durante una prueba."""
    return tmp_path


@pytest.fixture(scope="session")
def aplicacion():
    """Una única aplicación de wxPython para toda la sesión de pruebas.

    Se crea una sola porque wxPython no admite dos ``wx.App`` en el mismo
    proceso, y se deja viva hasta el final: destruirla entre pruebas deja el
    proceso en un estado del que no se recupera.
    """
    import wx

    aplicacion = wx.App(False)
    yield aplicacion


@pytest.fixture
def configuracion(carpeta, monkeypatch):
    """Configuración limpia, escrita en una carpeta temporal.

    Se desvía la carpeta de datos para que las pruebas no toquen los ajustes ni
    los marcadores de verdad: una prueba que borra la configuración del usuario
    es peor que no tener pruebas.
    """
    monkeypatch.setattr(rutas, "directorio_base", lambda: carpeta)
    from nucleo.configuracion import Configuracion

    return Configuracion()
