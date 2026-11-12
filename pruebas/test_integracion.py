# -*- coding: utf-8 -*-
"""Pruebas de la integración con el explorador de Windows.

Las pruebas que escriben lo hacen en una clave **propia y de prueba**, nunca en
la del programa: la suite se ejecuta en el equipo del usuario, y si tuviera
integración configurada, una prueba que llamara a ``quitar()`` se la borraría.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from nucleo import integracion  # noqa: E402

windows = pytest.mark.skipif(sys.platform != "win32", reason="solo en Windows")

#: Clave aparte para las pruebas que escriben.  No se toca la del programa.
CLAVE_PRUEBA = r"Software\VisorUniversalPruebas"


def test_la_orden_lleva_el_archivo_entre_comillas():
    """Sin comillas, una ruta con espacios llega partida en trozos."""
    orden = integracion._orden()

    assert orden.endswith('"%1"')
    assert orden.count('"%1"') == 1


def test_se_ofrecen_los_formatos_que_el_programa_abre_de_verdad():
    """La lista sale de los analizadores: no hay una copia que mantener."""
    import formatos.epub    # noqa: F401
    import formatos.kindle  # noqa: F401

    extensiones = {extension for extension, _nombre in integracion.formatos_disponibles()}
    assert ".epub" in extensiones
    assert ".kfx" in extensiones
    assert all(extension.startswith(".") for extension in extensiones)


def test_cada_formato_viene_con_el_nombre_de_su_analizador():
    import formatos.kindle  # noqa: F401

    nombres = dict(integracion.formatos_disponibles())
    assert nombres[".azw3"] == nombres[".mobi"] != ""


def test_sin_windows_la_integracion_se_declara_no_disponible(monkeypatch):
    monkeypatch.setattr(integracion.sys, "platform", "linux")

    assert not integracion.disponible()
    assert integracion.aplicar([".epub"]) is False
    assert integracion.quitar() is False


@windows
def test_una_extension_que_no_se_pide_no_se_toca(monkeypatch):
    """Es la condición de la que depende todo: solo los formatos elegidos."""
    escritas = []
    monkeypatch.setattr(integracion, "_quitar_todo", lambda winreg: None)
    monkeypatch.setattr(integracion, "_escribir_programa", lambda winreg: None)
    monkeypatch.setattr(integracion, "_anotar_estado",
                        lambda winreg, e, m, a: None)
    monkeypatch.setattr(integracion, "_avisar_al_explorador", lambda: None)
    monkeypatch.setattr(integracion, "_escribir_verbo",
                        lambda winreg, extension: escritas.append(extension))
    monkeypatch.setattr(integracion, "_escribir_abrir_con", lambda winreg, e: None)

    integracion.aplicar([".epub", ".kfx"], menu=True, abrir_con=False)
    assert escritas == [".epub", ".kfx"]


@windows
def test_lo_que_no_es_una_extension_se_descarta(monkeypatch):
    escritas = []
    monkeypatch.setattr(integracion, "_quitar_todo", lambda winreg: None)
    monkeypatch.setattr(integracion, "_escribir_programa", lambda winreg: None)
    monkeypatch.setattr(integracion, "_anotar_estado", lambda winreg, e, m, a: None)
    monkeypatch.setattr(integracion, "_avisar_al_explorador", lambda: None)
    monkeypatch.setattr(integracion, "_escribir_verbo",
                        lambda winreg, extension: escritas.append(extension))
    monkeypatch.setattr(integracion, "_escribir_abrir_con", lambda winreg, e: None)

    integracion.aplicar([".epub", "epub", "", None, "C:/algo"], menu=True)
    assert escritas == [".epub"]


@windows
def test_se_borra_un_arbol_entero_del_registro():
    """El registro no deja borrar una clave que tenga hijas."""
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, CLAVE_PRUEBA + r"\una\otra\mas"):
        pass
    integracion._borrar_arbol(winreg, winreg.HKEY_CURRENT_USER, CLAVE_PRUEBA)

    with pytest.raises(OSError):
        winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLAVE_PRUEBA)


@windows
def test_al_moverse_el_programa_se_vuelve_a_registrar(monkeypatch):
    """Es lo que mantiene viva la integración en un programa portátil."""
    rehechas = []
    monkeypatch.setattr(integracion, "aplicar",
                        lambda e, m=True, a=True: rehechas.append(list(e)) or True)
    monkeypatch.setattr(integracion, "ejecutable", lambda: r"D:\otro\sitio\visor.exe")

    assert integracion.revisar([".epub"]) is True
    assert rehechas == [[".epub"]]


@windows
def test_sin_formatos_no_se_revisa_nada(monkeypatch):
    monkeypatch.setattr(integracion, "aplicar",
                        lambda *a, **k: pytest.fail("no debería registrarse"))

    assert integracion.revisar([]) is False
