# -*- coding: utf-8 -*-
"""Pruebas de la firma del aviso de versión y del empaquetado.

Lo importante aquí es que la firma **sirva de algo**: que una firma buena se
acepte, que una mala se rechace, y que un aviso sin firma no cuele cuando el
programa lleva clave pública.  Una firma que se acepta siempre es peor que no
tenerla, porque da una seguridad que no existe.
"""

import base64
import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "herramientas"))

pytest.importorskip("cryptography")

import empaquetar          # noqa: E402
import firmar_version      # noqa: E402
from nucleo import actualizaciones   # noqa: E402


@pytest.fixture
def par_de_claves(carpeta):
    """Genera un par de claves nuevo y devuelve (ruta privada, pública en hex)."""
    privada = carpeta / "clave.key"
    publica = firmar_version.generar(privada)
    return privada, publica


def _aviso(carpeta, version="1.2.0", sha="a" * 64):
    ruta = carpeta / "version.json"
    ruta.write_text(json.dumps({"version": version, "sha256": sha}),
                    encoding="utf-8")
    return ruta


def test_generar_da_una_clave_de_32_bytes(par_de_claves):
    privada, publica = par_de_claves
    assert privada.stat().st_size == 32
    assert len(publica) == 64            # 32 bytes en hexadecimal
    bytes.fromhex(publica)               # y es hexadecimal de verdad


def test_no_se_pisa_una_clave_ya_existente(par_de_claves):
    """Generar otra invalidaría todas las versiones firmadas con la anterior."""
    privada, _publica = par_de_claves
    with pytest.raises(SystemExit):
        firmar_version.generar(privada)


def test_firma_y_verificacion(carpeta, par_de_claves, monkeypatch):
    privada, publica = par_de_claves
    ruta = _aviso(carpeta)
    firmar_version.firmar(ruta, privada)

    manifiesto = json.loads(ruta.read_text(encoding="utf-8"))
    assert manifiesto["firma_ed25519"]

    monkeypatch.setattr(actualizaciones, "CLAVE_PUBLICA", publica)
    actualizaciones.comprobar_firma(manifiesto)      # no debe lanzar


def test_una_firma_manipulada_se_rechaza(carpeta, par_de_claves, monkeypatch):
    privada, publica = par_de_claves
    ruta = _aviso(carpeta)
    firmar_version.firmar(ruta, privada)
    manifiesto = json.loads(ruta.read_text(encoding="utf-8"))

    # Se cambia el resumen: la firma cubría el anterior.
    manifiesto["sha256"] = "b" * 64
    monkeypatch.setattr(actualizaciones, "CLAVE_PUBLICA", publica)
    with pytest.raises(ValueError):
        actualizaciones.comprobar_firma(manifiesto)


def test_una_firma_de_otra_clave_se_rechaza(carpeta, par_de_claves, monkeypatch):
    privada, _publica = par_de_claves
    otra = carpeta / "otra.key"
    publica_de_otra = firmar_version.generar(otra)

    ruta = _aviso(carpeta)
    firmar_version.firmar(ruta, privada)
    manifiesto = json.loads(ruta.read_text(encoding="utf-8"))

    monkeypatch.setattr(actualizaciones, "CLAVE_PUBLICA", publica_de_otra)
    with pytest.raises(ValueError):
        actualizaciones.comprobar_firma(manifiesto)


def test_sin_firma_con_clave_publica_puesta_se_rechaza(monkeypatch, par_de_claves):
    """Es el punto de tener clave: lo que no viene firmado no se instala."""
    _privada, publica = par_de_claves
    monkeypatch.setattr(actualizaciones, "CLAVE_PUBLICA", publica)
    with pytest.raises(ValueError):
        actualizaciones.comprobar_firma({"version": "1.2.0", "sha256": "a" * 64})


def test_sin_clave_publica_no_se_exige_firma(monkeypatch):
    """Es lo que permite publicar desde el primer día y firmar más adelante."""
    monkeypatch.setattr(actualizaciones, "CLAVE_PUBLICA", "")
    actualizaciones.comprobar_firma({"version": "1.2.0"})


def test_no_se_firma_un_aviso_incompleto(carpeta, par_de_claves):
    privada, _publica = par_de_claves
    ruta = carpeta / "version.json"
    ruta.write_text(json.dumps({"version": "1.2.0"}), encoding="utf-8")
    with pytest.raises(SystemExit):
        firmar_version.firmar(ruta, privada)


def test_sin_clave_privada_no_se_puede_firmar(carpeta):
    ruta = _aviso(carpeta)
    with pytest.raises(SystemExit):
        firmar_version.firmar(ruta, carpeta / "no_existe.key")


# --- empaquetado -------------------------------------------------------------

def test_el_zip_lleva_todo_bajo_una_carpeta(carpeta):
    """El actualizador quita esa carpeta al descomprimir, y tiene que estar."""
    import zipfile

    origen = carpeta / "VisorUniversal"
    (origen / "data").mkdir(parents=True)
    (origen / "VisorUniversal.exe").write_bytes(b"exe")
    (origen / "data" / "algo.txt").write_text("x", encoding="utf-8")

    destino = carpeta / "paquete.zip"
    total = empaquetar.comprimir(origen, destino)
    assert total == 2
    with zipfile.ZipFile(destino) as paquete:
        nombres = paquete.namelist()
    assert all(nombre.startswith("VisorUniversal/") for nombre in nombres)


def test_el_paquete_generado_lo_acepta_el_actualizador(carpeta):
    """Ida y vuelta completa: se empaqueta y se descomprime como lo haría el
    programa al actualizarse."""
    origen = carpeta / "VisorUniversal"
    origen.mkdir()
    (origen / "VisorUniversal.exe").write_bytes(b"exe")
    (origen / "otro.dll").write_bytes(b"dll")

    destino = carpeta / "p.zip"
    empaquetar.comprimir(origen, destino)

    resumen = empaquetar.sha256_de(destino)
    actualizaciones.comprobar_paquete(destino, resumen)

    salida = carpeta / "extraido"
    actualizaciones.descomprimir(destino, salida)
    assert (salida / "VisorUniversal.exe").exists()
    assert (salida / "otro.dll").exists()


def test_la_version_se_lee_del_codigo():
    version, _publica = empaquetar.version_y_clave()
    from version import VERSION

    assert version == VERSION


# --- la firma automática al compilar -------------------------------------------

def test_la_clave_publica_se_deduce_de_la_privada(par_de_claves):
    """No se guardan por separado: así no pueden desincronizarse."""
    privada, publica = par_de_claves
    assert firmar_version.clave_publica_de(privada) == publica


def test_no_se_regenera_una_clave_que_ya_existe(par_de_claves):
    """Cambiar de clave deja sin actualizaciones a quien ya tenga la anterior."""
    privada, publica = par_de_claves
    with pytest.raises(SystemExit):
        firmar_version.generar(privada)
    # Y la que había sigue intacta.
    assert firmar_version.clave_publica_de(privada) == publica


def test_escribir_la_clave_en_version_py(carpeta, monkeypatch):
    """La compilación la mete sola en version.py antes de empaquetar."""
    falso = carpeta / "version.py"
    falso.write_text(
        '# comentario que hay que respetar\n'
        'VERSION = "1.2.3"\n'
        'CLAVE_PUBLICA = ""\n'
        '# otro comentario\n', encoding="utf-8")
    monkeypatch.setattr(firmar_version, "VERSION_PY", falso)

    assert firmar_version.clave_en_version() == ""
    assert firmar_version.escribir_en_version("a" * 64) is True
    assert firmar_version.clave_en_version() == "a" * 64
    # Y no ha tocado nada más del archivo.
    contenido = falso.read_text(encoding="utf-8")
    assert "# comentario que hay que respetar" in contenido
    assert 'VERSION = "1.2.3"' in contenido
    assert "# otro comentario" in contenido


def test_escribir_la_misma_clave_no_toca_el_archivo(carpeta, monkeypatch):
    falso = carpeta / "version.py"
    falso.write_text('CLAVE_PUBLICA = "%s"\n' % ("b" * 64), encoding="utf-8")
    monkeypatch.setattr(firmar_version, "VERSION_PY", falso)
    antes = falso.stat().st_mtime_ns
    assert firmar_version.escribir_en_version("b" * 64) is False
    assert falso.stat().st_mtime_ns == antes


def test_preparar_crea_la_clave_y_la_pone_en_version(carpeta, monkeypatch):
    """Es lo que hace la compilación la primera vez, sin preguntar nada."""
    privada = carpeta / "clave.key"
    falso = carpeta / "version.py"
    falso.write_text('CLAVE_PUBLICA = ""\n', encoding="utf-8")
    monkeypatch.setattr(firmar_version, "CLAVE", privada)
    monkeypatch.setattr(firmar_version, "VERSION_PY", falso)

    publica = firmar_version.preparar()
    assert privada.exists()
    assert firmar_version.clave_en_version() == publica

    # La segunda vez no crea nada nuevo ni cambia la clave.
    assert firmar_version.preparar() == publica


def test_preparar_corrige_una_clave_publica_que_no_cuadra(carpeta, monkeypatch):
    """Si version.py lleva otra clave, la compilación la deja bien."""
    privada = carpeta / "clave.key"
    falso = carpeta / "version.py"
    falso.write_text('CLAVE_PUBLICA = "%s"\n' % ("c" * 64), encoding="utf-8")
    monkeypatch.setattr(firmar_version, "CLAVE", privada)
    monkeypatch.setattr(firmar_version, "VERSION_PY", falso)

    publica = firmar_version.preparar()
    assert publica != "c" * 64
    assert firmar_version.clave_en_version() == publica


def test_ciclo_completo_de_publicacion(carpeta, monkeypatch):
    """Lo que pasa al compilar: preparar, empaquetar, firmar y comprobar.

    Es la prueba que de verdad importa: que lo que sale del empaquetado sea
    exactamente lo que el programa instalado acepta, y que un servidor
    secuestrado no pueda colar otra cosa.
    """
    privada = carpeta / "clave.key"
    falso_version = carpeta / "version.py"
    falso_version.write_text('CLAVE_PUBLICA = ""\n', encoding="utf-8")
    monkeypatch.setattr(firmar_version, "CLAVE", privada)
    monkeypatch.setattr(firmar_version, "VERSION_PY", falso_version)

    # 1. Antes de compilar.
    publica = firmar_version.preparar()

    # 2. Se empaqueta lo compilado.
    origen = carpeta / "VisorUniversal"
    origen.mkdir()
    (origen / "VisorUniversal.exe").write_bytes(b"programa")
    paquete = carpeta / "VisorUniversal_v1.2.0.zip"
    empaquetar.comprimir(origen, paquete)

    # 3. Se escribe el aviso y se firma.
    aviso = carpeta / "version.json"
    aviso.write_text(json.dumps({
        "version": "1.2.0",
        "file": paquete.name,
        "sha256": empaquetar.sha256_de(paquete),
    }), encoding="utf-8")
    firmar_version.firmar(aviso, privada)

    # 4. Lo que hace el programa instalado al encontrarlo.
    manifiesto = json.loads(aviso.read_text(encoding="utf-8"))
    monkeypatch.setattr(actualizaciones, "CLAVE_PUBLICA", publica)
    actualizaciones.comprobar_firma(manifiesto)
    actualizaciones.comprobar_paquete(paquete, manifiesto["sha256"])
    salida = carpeta / "instalado"
    actualizaciones.descomprimir(paquete, salida)
    assert (salida / "VisorUniversal.exe").read_bytes() == b"programa"

    # 5. Y lo que pasa si alguien cambia el zip en el servidor.
    paquete.write_bytes(b"un zip cualquiera")
    with pytest.raises(ValueError):
        actualizaciones.comprobar_paquete(paquete, manifiesto["sha256"])
    with pytest.raises(ValueError):
        actualizaciones.comprobar_firma(
            dict(manifiesto, sha256=empaquetar.sha256_de(paquete)))


def test_no_se_empaqueta_nunca_una_clave_privada(carpeta):
    """Publicar la clave privada sería el peor fallo posible de todo esto."""
    origen = carpeta / "VisorUniversal"
    origen.mkdir()
    (origen / "VisorUniversal.exe").write_bytes(b"exe")
    (origen / "visor_ed25519.key").write_bytes(b"secreto")

    destino = carpeta / "p.zip"
    with pytest.raises(SystemExit):
        empaquetar.comprimir(origen, destino)
    # Y no deja un zip a medias con la clave dentro.
    assert not destino.exists()
