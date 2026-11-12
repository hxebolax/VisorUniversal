# -*- coding: utf-8 -*-
"""Pruebas del adaptador Acapela que no cargan software propietario."""

from __future__ import annotations

import importlib.util
import json
import struct
import sys
import zipfile
from pathlib import Path


RAIZ = Path(__file__).resolve().parent.parent
FUENTE = RAIZ / "plugins_voz" / "fuentes" / "acapela"


def _modulo():
    nombre = "motor_acapela_en_pruebas"
    if nombre in sys.modules:
        return sys.modules[nombre]
    especificacion = importlib.util.spec_from_file_location(nombre, FUENTE / "motor.py")
    modulo = importlib.util.module_from_spec(especificacion)
    sys.modules[nombre] = modulo
    especificacion.loader.exec_module(modulo)
    return modulo


def _pe(ruta: Path, maquina: int) -> None:
    """Escribe la cabecera PE mínima que usa el diagnóstico estático."""
    datos = bytearray(256)
    datos[0:2] = b"MZ"
    datos[0x3C:0x40] = struct.pack("<I", 0x80)
    datos[0x80:0x84] = b"PE\0\0"
    datos[0x84:0x86] = struct.pack("<H", maquina)
    ruta.write_bytes(datos)


def test_modo_seguro_no_carga_ninguna_dll():
    motor = _modulo().crear(FUENTE, {})
    assert not motor.disponible
    assert "modo seguro" in motor.problema()
    assert not motor.hablando
    assert not motor.pausada


def test_arquitectura_pe_se_lee_sin_ejecutar(tmp_path):
    modulo = _modulo()
    x86 = tmp_path / "x86.dll"
    x64 = tmp_path / "x64.dll"
    _pe(x86, 0x014C)
    _pe(x64, 0x8664)
    assert modulo._arquitectura_pe(x86) == "x86"
    assert modulo._arquitectura_pe(x64) == "x64"


def test_no_se_mezcla_runtime_x64_con_modulos_x86(tmp_path):
    modulo = _modulo()
    runtime = tmp_path / "runtime"
    datos = tmp_path / "voces"
    (datos / "bin").mkdir(parents=True)
    runtime.mkdir()
    _pe(runtime / "AcaTts.64.dll", 0x8664)
    _pe(datos / "bin" / "Colibri.dll", 0x014C)
    diagnostico = modulo.diagnosticar(runtime, datos, "nativo64")
    assert "otra arquitectura" in diagnostico.problema


def test_las_voces_y_su_idioma_se_extraen_de_los_conf(tmp_path):
    modulo = _modulo()
    carpeta = tmp_path / "data" / "Spanish" / "Ines22k_CO"
    carpeta.mkdir(parents=True)
    (carpeta / "Ines22k_CO.conf").write_text(
        "[\\Speechfonts\\Ines22k_CO]\nVersion=10_300_1\n", encoding="utf-8")
    assert modulo._voces_en_datos(tmp_path) == [("Ines22k_CO", "es-ES")]


def test_runtime_portatil_usa_su_carpeta_como_datos_si_no_se_indica_otra(tmp_path):
    modulo = _modulo()
    _pe(tmp_path / "AcaTts.64.dll", 0x8664)
    voz = tmp_path / "data" / "Spanish" / "Maria22k_HQ"
    voz.mkdir(parents=True)
    (voz / "Maria22k_HQ.conf").write_text(
        "[\\Speechfonts\\Maria22k_HQ]\nVersion=7_0_31060_1\n",
        encoding="utf-8")
    diagnostico = modulo.diagnosticar(tmp_path, arquitectura="nativo64")
    assert diagnostico.datos == tmp_path
    motor = modulo.crear(FUENTE, {"ruta_motor": str(tmp_path)})
    assert motor.voces() == ["Maria22k_HQ"]


def test_la_velocidad_del_visor_se_convierte_en_toda_la_escala():
    clase = _modulo().MotorAcapela
    assert clase._velocidad_acapela(-10) == 30
    assert clase._velocidad_acapela(0) == 100
    assert clase._velocidad_acapela(10) == 300


def test_manifiesto_fuente_completo_y_en_espanol():
    datos = json.loads((FUENTE / "motor.json").read_text(encoding="utf-8"))
    assert datos["id"] == "acapela"
    assert datos["contrato"] == 1
    assert len(datos["ajustes"]) == 26
    assert all(ajuste.get("ayuda") for ajuste in datos["ajustes"])


def test_el_puente_compilado_es_x86():
    modulo = _modulo()
    puente = FUENTE / "archivos" / "puente32" / "acapela_host32.exe"
    assert puente.is_file()
    assert modulo._arquitectura_pe(puente) == "x86"


def test_paquete_no_contiene_binarios_ni_voces_de_acapela():
    paquete = RAIZ / "plugins_voz" / "acapela.motorvoz"
    assert paquete.is_file()
    with zipfile.ZipFile(paquete) as archivo:
        nombres = set(archivo.namelist())
        manifiesto = json.loads(archivo.read("motor.json").decode("utf-8"))
    assert manifiesto["id"] == "acapela"
    assert "puente32/acapela_host32.exe" in nombres
    assert "ANALISIS_Y_USO.md" in nombres
    assert "SOLICITUD_SDK_ACAPELA.md" in nombres
    assert not any(nombre.lower().endswith("acatts.dll") for nombre in nombres)
    assert not any("colibri.dll" in nombre.lower() for nombre in nombres)
    assert not any(nombre.lower().endswith((".erf", ".alf", ".qvcu"))
                   for nombre in nombres)


def test_el_paquete_compilado_se_importa_en_modo_seguro(tmp_path):
    paquete = RAIZ / "plugins_voz" / "acapela.motorvoz"
    with zipfile.ZipFile(paquete) as archivo:
        archivo.extractall(tmp_path)
    nombre = "motor_acapela_paquete_en_pruebas"
    sys.path.insert(0, str(tmp_path))
    try:
        especificacion = importlib.util.spec_from_file_location(
            nombre, tmp_path / "motor_acapela.pyc")
        modulo = importlib.util.module_from_spec(especificacion)
        sys.modules[nombre] = modulo
        especificacion.loader.exec_module(modulo)
        motor = modulo.crear(tmp_path, {})
        assert not motor.disponible
        assert "modo seguro" in motor.problema()
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop(nombre, None)
        sys.modules.pop("aca_rutas", None)
