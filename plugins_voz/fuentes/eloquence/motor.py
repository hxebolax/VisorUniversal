# -*- coding: utf-8 -*-
"""Eloquence para el Visor Universal, a través de un puente de 32 bits.

Eloquence es un sintetizador de IBM de 1993 y sigue siendo, treinta años
después, la voz que más gente ciega elige para leer. No porque suene bien
—suena metálica y a nadie le parece bonita— sino por dos cosas que ninguna voz
moderna ha igualado:

* **Aguanta la velocidad.** A trescientas palabras por minuto una voz neuronal
  se convierte en un borrón; Eloquence se sigue entendiendo. Quien lee libros
  enteros de oído lee deprisa, y ahí no hay competencia.
* **Es predecible.** Pronuncia las abreviaturas, los números y los símbolos
  siempre igual, y quien lleva media vida oyéndola ya sabe qué significa cada
  cosa aunque esté mal dicha.

El puente de 32 bits
--------------------

La biblioteca de Eloquence, ``ECI.DLL``, es de 32 bits y no hay versión de 64.
El visor es de 64, y **un proceso de 64 bits no puede cargar una biblioteca de
32**: no es una limitación que se pueda rodear con un truco, es cómo funciona
Windows.

La solución es la de siempre: un **proceso aparte** de 32 bits que sí puede
cargarla, y una tubería por la que se le pasa el texto y devuelve el sonido. Ese
proceso es ``ibmtts_host32.dll``, escrito en Rust, y todo lo que hay debajo de
este archivo es el ir y venir por esa tubería.

Este archivo no hace nada de eso: lo que hace es **traducir**. El visor le pide
a una voz doce cosas concretas —dime tus voces, ponte a esta velocidad, di esto,
calla— y Eloquence las llama de otra manera y en otras escalas. Aquí se
convierte de una a otra, y nada más.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger("visor.motor.eloquence")

# El paquete se importa desde su propia carpeta, y sus módulos se buscan unos a
# otros por el nombre.  Añadirla aquí y quitarla al acabar deja el resto del
# programa como estaba: si se quedara puesta, un módulo de este motor podría
# tapar a uno del visor que se llamara igual.
_AQUI = str(Path(__file__).resolve().parent)
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

from provider import EloquenceProvider          # noqa: E402
from engine import LANGS, VOICE_VARIANTS         # noqa: E402
from base import TTSState                        # noqa: E402

#: Escala del visor para la velocidad: de -10 a 10, con 0 en la normal.  La de
#: Eloquence va de 0 a 100.  La conversión no es una regla de tres inocente: el
#: 0 del visor tiene que caer donde Eloquence suena a velocidad normal, que es
#: alrededor de 55, y no en la mitad de su escala.
VELOCIDAD_NORMAL = 55


def _a_eloquence(velocidad: int) -> int:
    """De la escala del visor (-10 a 10) a la de Eloquence (0 a 100)."""
    acotada = max(-10, min(10, int(velocidad)))
    if acotada >= 0:
        return int(VELOCIDAD_NORMAL + acotada * (100 - VELOCIDAD_NORMAL) / 10.0)
    return int(VELOCIDAD_NORMAL + acotada * VELOCIDAD_NORMAL / 10.0)


class MotorEloquence:
    """Eloquence con la cara que el visor sabe manejar.

    Es un traductor, no un motor: todo lo que suena lo hace ``EloquenceProvider``
    y aquí solo se convierten los nombres y las escalas. Escrito así a propósito,
    porque el motor de debajo ya estaba probado y reescribirlo habría sido
    cambiar código que funciona por código nuevo.
    """

    def __init__(self, carpeta: Path, ajustes: dict) -> None:
        self._carpeta = Path(carpeta)
        self._ajustes = dict(ajustes)
        # La velocidad y el volumen los pone el visor por su cuenta, con la
        # pestaña «Voz»; aquí solo se dejan preparados los de fábrica.
        self._ajustes.setdefault("velocidad", VELOCIDAD_NORMAL)
        self._ajustes.setdefault("volumen", 100)
        self._proveedor = EloquenceProvider(self._ajustes)
        self._pausado = False
        self._voz = int(self._ajustes.get("variante", 1) or 1)

    # -- qué voces hay -------------------------------------------------------

    @property
    def disponible(self) -> bool:
        """Eloquence está listo si su proceso de 32 bits ha arrancado."""
        return self._proveedor.state != TTSState.ERROR

    def voces(self) -> list:
        """Las ocho variantes de Eloquence, por su nombre de siempre.

        No son voces distintas en el sentido de Windows: son la misma voz con
        otro timbre. Se llaman Reed, Shelley, Sandy... desde 1993 y así las pide
        la gente, así que no se traducen ni se renumeran.
        """
        return [nombre for _numero, nombre in sorted(VOICE_VARIANTS.items())]

    def elegir_voz(self, nombre: str) -> bool:
        for numero, cual in VOICE_VARIANTS.items():
            if cual == nombre:
                self._voz = numero
                self._ajustes["variante"] = numero
                self._proveedor.set_voice(str(numero))
                return True
        return False

    def voz_actual(self) -> str:
        return VOICE_VARIANTS.get(self._voz, "")

    def voces_con_idioma(self) -> list:
        """Las variantes con el idioma que tenga puesto el motor.

        En Eloquence el idioma **no va por voz**: va por motor, y se elige en
        los ajustes. Las ocho variantes hablan el idioma que esté puesto, así
        que todas devuelven el mismo código.
        """
        clave = str(self._ajustes.get("idioma", "esp"))
        codigo = _IDIOMA_DE.get(clave, "")
        return [(nombre, codigo) for nombre in self.voces()]

    def voz_para_idioma(self, codigo: str) -> str:
        """Qué variante lee mejor ese idioma.

        La respuesta honesta casi siempre es «ninguna»: Eloquence lee el idioma
        que tiene puesto y cambiarlo a mitad de página costaría reiniciar el
        proceso de 32 bits. Se devuelve una variante solo cuando el idioma que
        se pide es justo el que ya está puesto, para que el visor no ande
        cambiando de voz sin conseguir nada.
        """
        if not codigo:
            return ""
        puesto = _IDIOMA_DE.get(str(self._ajustes.get("idioma", "esp")), "")
        if puesto and codigo.split("-")[0].lower() == puesto.split("-")[0].lower():
            return self.voz_actual()
        return ""

    # -- ajustes -------------------------------------------------------------

    def establecer_velocidad(self, valor: int) -> None:
        self._proveedor.set_rate(_a_eloquence(valor))

    def establecer_volumen(self, valor: int) -> None:
        self._proveedor.set_volume(max(0, min(100, int(valor))))


    @property
    def espera_maxima(self) -> float:
        """Cuánto puede tardar esta voz en empezar a sonar, en segundos.

        El lector lo usa para no dar una frase por terminada antes de tiempo.
        Eloquence es rápida, pero habla por una tubería con un proceso
        de 32 bits y la primera frase paga el arranque de ese proceso.
        """
        try:
            return float(self._ajustes.get("espera_maxima", 3.0))
        except (TypeError, ValueError):
            return 3.0

    # -- hablar --------------------------------------------------------------

    def decir(self, texto: str, con_marcas: bool = False) -> bool:
        """Dice un texto, descartando lo que hubiera antes.

        ``con_marcas`` se ignora a propósito: son las marcas XML de SAPI y
        Eloquence no las entiende. El visor las usa para el cambio de tono en
        los diálogos; aquí ese texto ya llega limpio desde :meth:`con_tono`, así
        que lo que se pierde es el cambio de tono y ni una palabra del libro.
        """
        if not texto:
            return False
        try:
            self._pausado = False
            self._proveedor.speak(texto)
            return True
        except Exception as error:
            log.error("Eloquence no ha podido hablar: %s", error)
            return False

    @staticmethod
    def con_tono(texto: str, tono: int) -> str:
        """Devuelve el texto tal cual: Eloquence no lleva marcas de tono.

        El visor envuelve los diálogos en una marca de SAPI para que suenen más
        agudos. Aquí no hay marca posible, así que se devuelve el texto limpio:
        el diálogo se oye con la voz de siempre y **no se pierde ni una
        palabra**, que es lo que importa. Dejar pasar la marca sí sería un
        problema: Eloquence la leería en voz alta, etiqueta incluida.
        """
        return texto

    def pausar(self) -> None:
        if not self._pausado:
            self._proveedor.pause()
            self._pausado = True

    def continuar(self) -> None:
        if self._pausado:
            self._proveedor.resume()
            self._pausado = False

    def detener(self) -> None:
        self._pausado = False
        try:
            self._proveedor.stop()
        except Exception as error:
            log.debug("Al detener Eloquence: %s", error)

    @property
    def pausada(self) -> bool:
        return self._pausado

    @property
    def hablando(self) -> bool:
        """Si está diciendo algo ahora mismo.

        Es lo que el visor mira para saber cuándo pasarle la frase siguiente, y
        por eso una pausa cuenta como «sigue»: si dijera que no, el visor daría
        la frase por terminada y se saltaría el resto en cuanto alguien pausara.
        """
        if self._pausado:
            return True
        return self._proveedor.state == TTSState.PLAYING

    # -- cerrar --------------------------------------------------------------

    def cerrar(self) -> None:
        """Cierra el proceso de 32 bits.

        Hay que llamarlo: el puente es un proceso aparte y, si no se le dice que
        acabe, se queda vivo. Al cambiar de motor tres veces habría tres.
        """
        try:
            self._proveedor.close()
        except Exception as error:
            log.debug("Al cerrar Eloquence: %s", error)


#: De qué idioma es cada paquete de voces de Eloquence, en el código de dos
#: letras con el que vienen escritos los libros.  Hace falta para que el visor
#: sepa si esta voz sirve para el fragmento que va a leer.
_IDIOMA_DE = {
    "esp": "es-ES", "esm": "es-MX", "enu": "en-US", "eng": "en-GB",
    "fra": "fr-FR", "frc": "fr-CA", "deu": "de-DE", "ita": "it-IT",
    "ptb": "pt-BR", "fin": "fi-FI", "chs": "zh-CN", "jpn": "ja-JP",
    "kor": "ko-KR",
}


def crear(carpeta, ajustes):
    """Lo que el visor llama para poner esta voz. Es la única entrada."""
    return MotorEloquence(Path(carpeta), dict(ajustes or {}))


#: Los idiomas que trae el paquete, para poder escribirlos en el manifiesto sin
#: repetirlos a mano.  Se deja aquí porque es de donde salen de verdad.
def idiomas_disponibles() -> list:
    return [(clave, nombre) for clave, (_codigo, nombre) in LANGS.items()]
