# -*- coding: utf-8 -*-
"""Un motor que toca el registro lo dice antes y se va del todo al quitarlo.

Estas pruebas escriben **en el registro de verdad**, en la rama del usuario y
bajo un nombre propio del programa, porque es lo único que comprueba lo que hay
que comprobar: que después de quitar un motor no queda nada. Preguntárselo a la
función que borra no vale; hay que preguntárselo a Windows.

Cada prueba limpia lo suyo pase lo que pase.
"""

import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from nucleo import motores_voz, paquetes_voz, sistema_motores  # noqa: E402

winreg = pytest.importorskip("winreg", reason="el registro es cosa de Windows")

#: Dónde escriben las pruebas.  Es una rama del programa, con su nombre, para
#: que si algún día quedara algo se sepa de dónde salió.
RAMA = r"Software\VisorUniversalPruebas\MotorDePrueba"
PADRE = r"Software\VisorUniversalPruebas"

CREAR = "def crear(carpeta, ajustes):\n    return object()\n"

MANIFIESTO = {
    "id": "prueba",
    "nombre": "Motor de prueba",
    "contrato": 1,
    "modulo": "motor",
    "sistema": {
        "resumen": "Necesita apuntar sus voces en el registro para encontrarlas.",
        "registro": [{"raiz": "HKCU", "clave": RAMA,
                      "porque": "Es donde busca la lista de sus voces."}],
    },
}


def _paquete(carpeta: Path, manifiesto: dict) -> Path:
    ruta = carpeta / "prueba.motorvoz"
    with zipfile.ZipFile(ruta, "w") as paquete:
        paquete.writestr("motor.py", CREAR)
        paquete.writestr("motor.json", json.dumps(manifiesto, ensure_ascii=False))
    return ruta


def _escribir(clave: str, valores=(("Voz", "Maria22k_HQ"),)) -> None:
    """Deja unas claves puestas, como haría el motor al arrancar."""
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, clave, 0,
                            winreg.KEY_WRITE) as abierta:
        for nombre, valor in valores:
            winreg.SetValueEx(abierta, nombre, 0, winreg.REG_SZ, valor)


def _existe(clave: str) -> bool:
    try:
        winreg.OpenKey(winreg.HKEY_CURRENT_USER, clave).Close()
        return True
    except OSError:
        return False


def _borrar_todo() -> None:
    for clave in (RAMA, PADRE):
        try:
            sistema_motores._borrar_recursivo(clave)
        except OSError:
            pass


@pytest.fixture(autouse=True)
def registro_limpio():
    """Ni se empieza con basura ni se deja."""
    _borrar_todo()
    yield
    _borrar_todo()


class PruebaLoQueSeDeclara:
    """Qué se admite declarar, y qué no."""

    def test_una_rama_normal_se_admite(self):
        efectos = sistema_motores.leer(MANIFIESTO)
        assert [rama.clave for rama in efectos.ramas] == [RAMA]
        assert efectos.ramas[0].completa == "HKCU\\" + RAMA

    @pytest.mark.parametrize("clave", [
        "Software",                       # un solo nivel: media configuración
        r"Software\Microsoft\Windows",    # de Windows
        "Environment",                    # las variables de entorno
        r"Software\..\..\otra",           # saliéndose por arriba
        "",
    ])
    def test_las_ramas_peligrosas_se_rechazan(self, clave):
        efectos = sistema_motores.leer(
            {"sistema": {"registro": [{"raiz": "HKCU", "clave": clave}]}})
        assert not efectos

    def test_la_rama_del_equipo_no_se_admite(self):
        """HKLM haría falta ser administrador y valdría para todas las cuentas.

        Un lector de libros no tiene por qué pedir eso ni dejarlo puesto para
        los demás.
        """
        efectos = sistema_motores.leer(
            {"sistema": {"registro": [{"raiz": "HKLM",
                                       "clave": r"Software\Cosa\Otra"}]}})
        assert not efectos

    def test_un_motor_normal_no_declara_nada(self):
        """Lo corriente es no tocar nada, y entonces no se avisa de nada."""
        efectos = sistema_motores.leer({"id": "x", "nombre": "X"})
        assert not efectos
        assert sistema_motores.describir(efectos) == ""


class PruebaElAviso:
    """Lo que se lee antes de instalar."""

    def test_el_resumen_dice_lo_que_va_a_tocar(self, tmp_path):
        ruta = _paquete(tmp_path, MANIFIESTO)
        ficha = paquetes_voz.examinar(ruta)
        texto = ficha.resumen()
        assert "REGISTRO DE WINDOWS" in texto
        assert RAMA in texto
        # Y que se dice que al quitarlo se borra: es la otra mitad de la
        # decisión, y sin ella el aviso solo da miedo.
        assert "quitar el motor" in texto

    def test_un_motor_que_no_toca_nada_no_asusta(self, tmp_path):
        ruta = _paquete(tmp_path, {"id": "prueba", "nombre": "Motor de prueba",
                                   "contrato": 1, "modulo": "motor"})
        texto = paquetes_voz.examinar(ruta).resumen()
        assert "REGISTRO" not in texto


class PruebaQuitarLoDejaLimpio:
    """El viaje entero, con el registro de verdad."""

    def test_al_quitar_no_queda_nada_ni_la_clave_padre(self, tmp_path,
                                                       monkeypatch):
        carpeta = tmp_path / "motores"
        monkeypatch.setattr(motores_voz, "carpeta_de_motores", lambda: carpeta)
        carpeta.mkdir()
        paquetes_voz.instalar(_paquete(tmp_path, MANIFIESTO))

        # El motor escribe lo suyo, como haría al arrancar por primera vez.
        _escribir(RAMA)
        _escribir(RAMA + r"\Voces\Maria")
        assert _existe(RAMA)

        assert paquetes_voz.quitar("prueba") is True
        assert not _existe(RAMA)
        # Y el padre, que se ha quedado vacío, tampoco: irse dejando una carpeta
        # vacía en el registro de alguien es no haberse ido.
        assert not _existe(PADRE)

    def test_lo_que_ya_estaba_antes_no_se_toca(self, tmp_path, monkeypatch):
        """Si alguien ya tenía ese motor instalado por su cuenta, es suyo.

        Es el caso que convierte una desinstalación limpia en un destrozo:
        quitar nuestro motor no puede llevarse por delante lo que había.
        """
        carpeta = tmp_path / "motores"
        monkeypatch.setattr(motores_voz, "carpeta_de_motores", lambda: carpeta)
        carpeta.mkdir()

        _escribir(RAMA, (("Suyo", "de antes"),))
        paquetes_voz.instalar(_paquete(tmp_path, MANIFIESTO))
        assert paquetes_voz.quitar("prueba") is True

        assert _existe(RAMA)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RAMA) as abierta:
            assert winreg.QueryValueEx(abierta, "Suyo")[0] == "de antes"

    def test_quitar_un_motor_que_no_toca_nada_sigue_funcionando(
            self, tmp_path, monkeypatch):
        carpeta = tmp_path / "motores"
        monkeypatch.setattr(motores_voz, "carpeta_de_motores", lambda: carpeta)
        carpeta.mkdir()
        ruta = _paquete(tmp_path, {"id": "prueba", "nombre": "Motor de prueba",
                                   "contrato": 1, "modulo": "motor"})
        paquetes_voz.instalar(ruta)
        assert paquetes_voz.quitar("prueba") is True
        assert not (carpeta / "prueba").exists()

    def test_lo_que_queda_lo_dice_el_registro_y_no_nosotros(self, tmp_path,
                                                            monkeypatch):
        """La comprobación de que no queda nada se le hace a Windows."""
        carpeta = tmp_path / "motores"
        monkeypatch.setattr(motores_voz, "carpeta_de_motores", lambda: carpeta)
        carpeta.mkdir()
        paquetes_voz.instalar(_paquete(tmp_path, MANIFIESTO))
        _escribir(RAMA)

        efectos = sistema_motores.leer(MANIFIESTO)
        assert sistema_motores.lo_que_queda(efectos) == ["HKCU\\" + RAMA]
        paquetes_voz.quitar("prueba")
        assert sistema_motores.lo_que_queda(efectos) == []
