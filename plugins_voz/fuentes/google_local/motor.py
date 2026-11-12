# -*- coding: utf-8 -*-
"""Voces de Google para el Visor Universal, sin conexión.

Son las voces que suenan a persona, y con una particularidad que las hace
valiosas de verdad: **se generan dentro del equipo**. No hace falta internet y
nada de lo que se lee sale de aquí. Es el motor que Chrome lleva para su lector
de páginas, funcionando por su cuenta.

Lo que cuestan son cuarenta y ocho megas de paquete y unos segundos de arranque
la primera vez. Para escuchar una novela entera compensa; para oír un aviso de
dos palabras, la voz de Windows sigue siendo mejor idea.

Vienen las quince voces de español —de España y de América— y dentro viaja
además el catálogo entero de Google: doscientos diecisiete hablantes en treinta
y cuatro idiomas. Los demás no ocupan nada hasta que se piden: al elegir uno se
baja su paquete, se comprueba su firma y se levanta el motor con él dentro.

El sonido no se reproduce aquí: el motor lo devuelve en trozos y los reproduce
BASS, que el visor ya lleva para los libros DAISY. Este archivo no hace más que
**traducir** entre lo que el visor le pide a una voz y lo que este motor sabe.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger("visor.motor.google_local")

_AQUI = str(Path(__file__).resolve().parent)
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

from base import TTSState                        # noqa: E402

#: La velocidad del visor va de -10 a 10 y la de estos motores de 0 a 100, con
#: la normal en la mitad.  Aquí sí es una regla de tres: su 50 es su velocidad
#: normal, igual que el 0 del visor.
VELOCIDAD_NORMAL = 50

#: Qué se enseña en la lista de voces.
SOLO_INSTALADAS = "instaladas"
TODOS_LOS_IDIOMAS = "todos"


def _a_cien(velocidad: int) -> int:
    """De la escala del visor (-10 a 10) a la de estos motores (0 a 100)."""
    return max(0, min(100, int(VELOCIDAD_NORMAL + int(velocidad) * 5)))


class MotorGoogleLocal:
    """Las voces locales de Google, con la cara que el visor maneja.

    El motor de debajo se levanta **al construirse** y no la primera vez que
    hable: tarda unos segundos, y pagar esa espera en mitad de la primera frase
    se oiría como que el programa se ha colgado.
    """

    def __init__(self, carpeta: Path, ajustes: dict) -> None:
        self._carpeta = Path(carpeta)
        self._ajustes = dict(ajustes)
        self._pausado = False
        self._voces = []
        #: Las que se pueden usar ahora mismo, por su nombre.  Se llena al
        #: arrancar; vacío aquí para que exista aunque el motor no llegue a
        #: levantarse.
        self._instaladas: set = set()
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
            from provider import GoogleChromeProvider

            self._proveedor = GoogleChromeProvider(config)
        except Exception as error:
            self._fallo = str(error)
            log.warning("No se ha podido arrancar la voz local: %s", error)
            return
        try:
            self._voces = list(self._proveedor.voices())
        except Exception as error:
            log.debug("Al listar las voces: %s", error)
            self._voces = []
        self._instaladas = {voz.name for voz in self._voces}
        if str(self._ajustes.get("que_voces", SOLO_INSTALADAS)) != SOLO_INSTALADAS:
            self._voces = self._con_las_que_faltan(self._voces)
        guardada = str(self._ajustes.get("_voz_elegida", ""))
        for voz in self._voces:
            if voz.name == guardada:
                self._voz = voz.id
                break
        if not self._voz and self._instaladas:
            # La primera **instalada**, no la primera de la lista: con el
            # catálogo entero abierto, arrancar el motor se pondría a bajar
            # megas que nadie ha pedido.  Solo se baja lo que alguien elige.
            for voz in self._voces:
                if voz.name in self._instaladas:
                    self._voz = voz.id
                    break

    def _con_las_que_faltan(self, puestas: list) -> list:
        """Añade a la lista las voces del catálogo que no están bajadas.

        El catálogo completo viene dentro del paquete: son sesenta y seis
        paquetes de voz en treinta y cuatro idiomas, con la dirección de cada
        uno.  Enseñarlos no cuesta nada; lo que cuesta megas es bajarlos, y eso
        pasa solo cuando alguien elige uno.

        Las instaladas se quedan primero: son las que funcionan ahora mismo.
        """
        try:
            from catalog import VoiceCatalog

            entero = VoiceCatalog.load()
        except Exception as error:
            log.warning("No se ha podido leer el catálogo de voces: %s", error)
            return puestas
        try:
            from base import VoiceInfo
        except Exception as error:
            log.debug("No se ha podido preparar la lista larga: %s", error)
            return puestas
        salida = list(puestas)
        for hablante in entero.speakers:
            nombre = "%s (%s)" % (hablante.name, hablante.language)
            if nombre in self._instaladas:
                continue
            salida.append(VoiceInfo(hablante.id, nombre, hablante.language))
        return salida

    def _bajar_el_paquete_de(self, identificador: str) -> bool:
        """Trae el paquete de voz al que pertenece esa voz.

        Es la descarga que ya traía el motor, la misma que usa Chrome: baja a un
        archivo aparte, comprueba el tamaño y la firma SHA-256, y solo entonces
        lo pone en su sitio.  Un paquete a medio bajar no llega a instalarse.
        """
        try:
            from catalog import VoiceCatalog
            import voice_store

            entero = VoiceCatalog.load()
            paquete = entero.package_for_voice(identificador)
        except Exception as error:
            log.warning("No se sabe de qué paquete es la voz «%s»: %s",
                        identificador, error)
            return False
        log.info("Bajando el paquete de voz «%s» (%.1f MB)...", paquete.id,
                 paquete.compressedSize / 1048576.0)
        try:
            voice_store.download_package(paquete)
        except Exception as error:
            log.warning("No se ha podido bajar «%s»: %s", paquete.id, error)
            return False
        log.info("Paquete «%s» listo", paquete.id)
        return True

    def _rehacer(self, elegida: str = "") -> None:
        """Vuelve a levantar el motor con los paquetes que haya ahora.

        Hay que rehacerlo entero, y no hay atajo: el catálogo de voces se le
        pasa al puente al construirlo, y el puente se lo sirve al motor de
        Chrome cuando arranca.  Un paquete nuevo no existe para nadie hasta que
        todo eso se vuelve a montar.

        ``elegida`` es con qué voz tiene que quedarse.  Se pide a propósito: la
        que está puesta ahora es justamente la que se quiere dejar de usar
        cuando esto se llama después de bajar otra.
        """
        quedarse = elegida or self.voz_actual()
        self.cerrar()
        self._proveedor = None
        self._voces = []
        self._instaladas = set()
        self._fallo = ""
        if quedarse:
            self._ajustes["_voz_elegida"] = quedarse
        self._arrancar()

    # -- qué voces hay -------------------------------------------------------

    @property
    def disponible(self) -> bool:
        return self._proveedor is not None and bool(self._voces)

    def voces(self) -> list:
        return [voz.name for voz in self._voces]

    def elegir_voz(self, nombre: str) -> bool:
        for voz in self._voces:
            if voz.name != nombre:
                continue
            if nombre not in self._instaladas:
                # Es una del catálogo que no está bajada.  Se trae y se levanta
                # el motor otra vez con ella dentro.
                if not self._bajar_el_paquete_de(voz.id):
                    return False
                self._rehacer(nombre)
                return self.voz_actual() == nombre
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
            # Solo entre las que están, y a propósito: cambiar de voz al vuelo
            # es para leer una cita en otra lengua, y pararse a bajar quince
            # megas en ese momento no es lo que nadie espera.  Vale más leerla
            # con acento.
            if voz.name not in self._instaladas:
                continue
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
        Aquí importa de verdad: esta voz genera el sonido de la
        frase entera antes de reproducirla, y la primera vez levanta
        además su motor. Son unos segundos, no unas décimas.
        """
        try:
            return float(self._ajustes.get("espera_maxima", 10.0))
        except (TypeError, ValueError):
            return 10.0

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
        """Cierra el motor. Hay que llamarlo: si no, deja procesos vivos."""
        if self._proveedor is None:
            return
        try:
            self._proveedor.close()
        except Exception as error:
            log.debug("Al cerrar: %s", error)


def crear(carpeta, ajustes):
    """Lo que el visor llama para poner esta voz. Es la única entrada."""
    return MotorGoogleLocal(Path(carpeta), dict(ajustes or {}))
