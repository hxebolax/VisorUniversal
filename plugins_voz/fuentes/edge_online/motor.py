# -*- coding: utf-8 -*-
"""Voces de Edge para el Visor Universal, por internet.

Son las voces neuronales que usa el navegador Edge para leer páginas en voz
alta. Suenan a persona, hay muchas y el paquete no ocupa nada, porque las voces
no están aquí: **están en un servidor de Microsoft**.

Eso es lo que hay que saber antes de elegirlas, y por eso lo dice también la
ayuda del programa: **cada frase que se lee viaja a ese servidor**, y sin
conexión no hay voz. Para un libro publicado da lo mismo; para un informe médico
o un documento del trabajo, no. Quien necesite que nada salga del equipo tiene
las voces locales de Google o la voz de Windows.

El sonido no se reproduce aquí: el motor lo devuelve en trozos y los reproduce
BASS, que el visor ya lleva para los libros DAISY. Este archivo no hace más que
**traducir** entre lo que el visor le pide a una voz y lo que este motor sabe.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger("visor.motor.edge_online")

_AQUI = str(Path(__file__).resolve().parent)
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

# Las bibliotecas que este motor necesita van dentro del paquete, en su propia
# carpeta: el visor no las trae y no tiene por qué traerlas si nadie usa estas
# voces.  Se añaden **al final** de la ruta de importación a propósito, para que
# no puedan tapar a nada del programa que se llame igual.
_DEPS = str(Path(__file__).resolve().parent / "edgeol_deps")
if _DEPS not in sys.path:
    sys.path.append(_DEPS)

from base import TTSState                        # noqa: E402

#: La velocidad del visor va de -10 a 10 y la de estos motores de 0 a 100, con
#: la normal en la mitad.  Aquí sí es una regla de tres: su 50 es su velocidad
#: normal, igual que el 0 del visor.
VELOCIDAD_NORMAL = 50


def _a_cien(velocidad: int) -> int:
    """De la escala del visor (-10 a 10) a la de estos motores (0 a 100)."""
    return max(0, min(100, int(VELOCIDAD_NORMAL + int(velocidad) * 5)))


class MotorEdgeOnline:
    """Las voces de Edge, con la cara que el visor maneja.

    El proveedor de debajo se crea **al construirse**: así se sabe desde el
    principio si hay conexión y si el catálogo de voces está, en vez de
    descubrirlo en mitad de la primera frase.
    """

    def __init__(self, carpeta: Path, ajustes: dict) -> None:
        self._carpeta = Path(carpeta)
        self._ajustes = dict(ajustes)
        self._pausado = False
        self._voces = []
        self._voz = ""
        self._proveedor = None
        self._fallo = ""
        self._arrancar()

    def _arrancar(self) -> None:
        """Crea el proveedor elegido. Si no puede, lo apunta y sigue vivo.

        No se lanza excepción: el visor comprueba :attr:`disponible` y, si no lo
        está, vuelve a la voz de Windows y lo dice. Reventar aquí dejaría la
        lectura muda sin explicar por qué.
        """
        config = dict(self._ajustes)
        config.setdefault("velocidad", VELOCIDAD_NORMAL)
        config.setdefault("volumen", 100)
        config["_cache_enabled"] = False
        config["_cache_max_mb"] = 0
        try:
            from provider import EdgeTTSProvider

            self._proveedor = EdgeTTSProvider(config)
        except Exception as error:
            self._fallo = str(error)
            log.warning("No se han podido preparar las voces de Edge: %s", error)
            return
        try:
            self._voces = list(self._proveedor.voices())
        except Exception as error:
            log.debug("Al listar las voces: %s", error)
            self._voces = []
        guardada = str(self._ajustes.get("_voz_elegida", ""))
        for voz in self._voces:
            if voz.name == guardada:
                self._voz = voz.id
                break
        if not self._voz and self._voces:
            self._voz = self._voces[0].id

    # -- qué voces hay -------------------------------------------------------

    @property
    def disponible(self) -> bool:
        return self._proveedor is not None and bool(self._voces)

    def voces(self) -> list:
        return [voz.name for voz in self._voces]

    def elegir_voz(self, nombre: str) -> bool:
        for voz in self._voces:
            if voz.name == nombre:
                self._voz = voz.id
                if self._proveedor is not None:
                    self._proveedor.set_voice(voz.id)
                return True
        return False

    def voz_actual(self) -> str:
        for voz in self._voces:
            if voz.id == self._voz:
                return voz.name
        return ""

    def voces_con_idioma(self) -> list:
        """Cada voz con su idioma, que aquí sí viene de verdad.

        Estas voces traen su código de idioma completo —``es-ES``, ``es-MX``—,
        así que el visor puede cambiar de voz al llegar a una cita en otra
        lengua igual que hace con las de Windows.
        """
        return [(voz.name, str(voz.language or "")) for voz in self._voces]

    def voz_para_idioma(self, codigo: str) -> str:
        """La voz que mejor lee ese idioma, o cadena vacía si no hay ninguna.

        Se prefiere la del país exacto y, si no la hay, cualquiera de la misma
        lengua: oír una frase inglesa con voz inglesa de otro país es mucho
        mejor que oírla con voz española.
        """
        if not codigo:
            return ""
        pedido = codigo.replace("_", "-").lower()
        lengua = pedido.split("-")[0]
        aproximada = ""
        for voz in self._voces:
            suyo = str(voz.language or "").replace("_", "-").lower()
            if not suyo:
                continue
            if suyo == pedido:
                return voz.name
            if suyo.split("-")[0] == lengua and not aproximada:
                aproximada = voz.name
        return aproximada

    # -- ajustes -------------------------------------------------------------

    def establecer_velocidad(self, valor: int) -> None:
        if self._proveedor is not None:
            self._proveedor.set_rate(_a_cien(valor))

    def establecer_volumen(self, valor: int) -> None:
        if self._proveedor is not None:
            self._proveedor.set_volume(max(0, min(100, int(valor))))


    @property
    def espera_maxima(self) -> float:
        """Cuánto puede tardar esta voz en empezar a sonar, en segundos.

        El lector lo usa para no dar una frase por terminada antes de tiempo.
        Aquí depende de la conexión y no del equipo: la frase se genera
        en un servidor y tiene que llegar.
        """
        try:
            return float(self._ajustes.get("espera_maxima", 12.0))
        except (TypeError, ValueError):
            return 12.0

    # -- hablar --------------------------------------------------------------

    def decir(self, texto: str, con_marcas: bool = False) -> bool:
        """Dice un texto, descartando lo que hubiera antes.

        ``con_marcas`` se ignora: son marcas de SAPI y estos motores no las
        entienden. El texto llega ya limpio desde :meth:`con_tono`.
        """
        if not texto or self._proveedor is None:
            return False
        try:
            self._pausado = False
            self._proveedor.speak(texto)
            return True
        except Exception as error:
            log.error("La voz no ha podido hablar: %s", error)
            return False

    @staticmethod
    def con_tono(texto: str, tono: int) -> str:
        """El texto tal cual: el tono se ajusta en los ajustes del motor.

        Estas voces sí saben cambiar de tono, pero no frase a frase: el tono es
        un ajuste del motor y cambiarlo obligaría a rehacer la síntesis. Así que
        el diálogo se oye con la voz de siempre y no se pierde ni una palabra,
        que es lo que importa.
        """
        return texto

    def pausar(self) -> None:
        if not self._pausado and self._proveedor is not None:
            self._proveedor.pause()
            self._pausado = True

    def continuar(self) -> None:
        if self._pausado and self._proveedor is not None:
            self._proveedor.resume()
            self._pausado = False

    def detener(self) -> None:
        self._pausado = False
        if self._proveedor is None:
            return
        try:
            self._proveedor.stop()
        except Exception as error:
            log.debug("Al detener: %s", error)

    @property
    def pausada(self) -> bool:
        return self._pausado

    @property
    def hablando(self) -> bool:
        """Si está diciendo algo ahora mismo.

        Una pausa cuenta como «sigue»: si dijera que no, el visor daría la frase
        por terminada y se saltaría el resto en cuanto alguien pausara.

        Y hay un detalle propio de estas voces: entre que se les pasa el texto y
        empiezan a sonar pasa **casi un segundo**, porque hay que sintetizar
        antes de reproducir. Durante esa espera el estado no es «reproduciendo»,
        pero tampoco ha acabado, así que también cuenta como que sigue: si no,
        el visor le pasaría la frase siguiente antes de oír la primera.
        """
        if self._pausado:
            return True
        if self._proveedor is None:
            return False
        return self._proveedor.state in (TTSState.PLAYING, TTSState.PAUSED)

    # -- cerrar --------------------------------------------------------------

    def cerrar(self) -> None:
        """Cierra el motor y suelta la conexión."""
        if self._proveedor is None:
            return
        try:
            self._proveedor.close()
        except Exception as error:
            log.debug("Al cerrar: %s", error)


def crear(carpeta, ajustes):
    """Lo que el visor llama para poner esta voz. Es la única entrada."""
    return MotorEdgeOnline(Path(carpeta), dict(ajustes or {}))
