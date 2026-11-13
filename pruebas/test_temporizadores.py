# -*- coding: utf-8 -*-
"""Los temporizadores con dueño se paran cuando se destruye su ventana.

Si siguieran en marcha, su siguiente aviso iría a memoria ya liberada: era la
causa de los cierres de golpe (``0xc0000374``) al salir con documentos
abiertos.
"""

import pytest

wx = pytest.importorskip("wx")

from interfaz.temporizadores import parar_al_destruir  # noqa: E402


@pytest.fixture(scope="module")
def aplicacion():
    app = wx.App(False)
    yield app


def test_se_para_al_destruir_su_ventana(aplicacion):
    marco = wx.Frame(None)
    panel = wx.Panel(marco)
    temporizador = wx.Timer(panel)
    parar_al_destruir(panel, temporizador)
    temporizador.Start(50)
    assert temporizador.IsRunning()
    panel.Destroy()
    wx.SafeYield()
    assert not temporizador.IsRunning()
    marco.Destroy()


def test_se_para_al_destruir_la_ventana_de_arriba(aplicacion):
    """Es lo que pasa al cerrar el programa: se destruye el marco con todo dentro."""
    marco = wx.Frame(None)
    panel = wx.Panel(marco)
    del_panel = wx.Timer(panel)
    del_marco = wx.Timer(marco)
    parar_al_destruir(panel, del_panel)
    parar_al_destruir(marco, del_marco)
    del_panel.Start(50)
    del_marco.Start(50)
    marco.Destroy()
    wx.SafeYield()
    assert not del_panel.IsRunning()
    assert not del_marco.IsRunning()


def test_destruir_una_hija_no_para_el_del_padre(aplicacion):
    marco = wx.Frame(None)
    hija = wx.Panel(marco)
    temporizador = wx.Timer(marco)
    parar_al_destruir(marco, temporizador)
    temporizador.Start(50)
    hija.Destroy()
    wx.SafeYield()
    assert temporizador.IsRunning()
    temporizador.Stop()
    marco.Destroy()


def test_el_panel_de_lectura_para_su_vigilancia_al_destruirse(aplicacion):
    """El caso real: el temporizador que vigila el cursor de cada pestaña."""
    from nucleo.documento import Documento
    from interfaz.lector import PanelLectura

    class Configuracion:
        def obtener(self, clave, por_omision=None):
            return por_omision

    class Nadie:
        def __getattr__(self, nombre):
            return lambda *a, **k: None

    marco = wx.Frame(None)
    panel = PanelLectura(marco, Configuracion(), Nadie(), Nadie())
    panel.cargar_documento(Documento(texto="Hola.\nAdiós.\n", marcas=[]), 0)
    assert panel._vigilante.IsRunning()
    vigilante = panel._vigilante
    marco.Destroy()
    wx.SafeYield()
    assert not vigilante.IsRunning()
