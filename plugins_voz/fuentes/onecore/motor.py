# -*- coding: utf-8 -*-
"""Las voces modernas de Windows 10 y 11, las que no salen en la lista normal.

Windows guarda sus voces en **tres sitios distintos** y el programa solo veía
uno. Las que faltan no son voces menores: son las de Windows 10 y 11 —Helena,
Laura, Pablo en español— y suenan bastante mejor que las que trae SAPI 5 de
serie, que en muchos equipos es una sola.

* ``Speech\\Voices`` son las clásicas de SAPI 5, las que ya se veían.
* ``Speech_OneCore\\Voices`` son las modernas, las que instala Windows con cada
  idioma. **Están en el equipo y no aparecen** en ningún programa que use SAPI
  del modo corriente.
* ``Speech Server\\v11.0\\Voices`` son las de servidor, que a veces deja
  instaladas Office o algún producto de Microsoft.

Por qué no salían
-----------------

Porque el modo normal de listar voces con SAPI —``GetVoices``— mira solo el
primer sitio. Las de OneCore existen, funcionan y responden a las mismas
órdenes, pero hay que ir a buscarlas a su propio catálogo.

Hay quien resuelve esto **copiando las claves del registro** de un sitio al
otro. Aquí no: el visor es portátil y no toca el registro de Windows. Se
enumeran los tres catálogos y se le pasan los tokens al mismo objeto de voz de
siempre, que los acepta sin más.

Cómo añadir voces nuevas
------------------------

Este motor no descarga nada, y es lo correcto: las voces de Windows las instala
Windows. En **Configuración → Hora e idioma → Voz** se añade un idioma y sus
voces quedan disponibles aquí en cuanto se reinicie el programa. Es un idioma
completo del sistema, no un archivo suelto, y hacerlo por fuera dejaría el
equipo a medias.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger("visor.motor.onecore")

#: Los tres catálogos donde Windows guarda voces, con el nombre que se enseña.
#: Se leen todos y se juntan: para quien lee un libro, una voz es una voz.
CATALOGOS = (
    ("onecore", r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices",
     "Windows 10/11"),
    ("clasicas", r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices",
     "SAPI 5"),
    ("servidor", r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech Server\v11.0\Voices",
     "Servidor"),
)

#: Banderas de ``Speak``.
_ASINCRONO = 1
_ES_XML = 8
_VACIAR = 2

#: Valor de ``RunningState`` mientras está pronunciando.
_HABLANDO = 2

#: Idioma principal de cada identificador de Windows.  SAPI no dice «español»:
#: dice ``c0a``, un número en hexadecimal cuyos diez bits bajos son la lengua.
IDIOMAS = {
    0x01: "ar", 0x02: "bg", 0x03: "ca", 0x04: "zh", 0x05: "cs", 0x06: "da",
    0x07: "de", 0x08: "el", 0x09: "en", 0x0A: "es", 0x0B: "fi", 0x0C: "fr",
    0x0D: "he", 0x0E: "hu", 0x10: "it", 0x11: "ja", 0x12: "ko", 0x13: "nl",
    0x14: "no", 0x15: "pl", 0x16: "pt", 0x18: "ro", 0x19: "ru", 0x1A: "hr",
    0x1B: "sk", 0x1D: "sv", 0x1E: "th", 0x1F: "tr", 0x21: "id", 0x22: "uk",
    0x24: "sl", 0x25: "et", 0x26: "lv", 0x27: "lt", 0x2A: "vi", 0x39: "hi",
    0x3E: "ms", 0x56: "gl", 0x2D: "eu",
}

#: Y la región, para los casos en que se nota al oído: un texto en inglés
#: británico leído con voz estadounidense se entiende, pero no es lo que pone.
REGIONES = {
    0x0409: "US", 0x0809: "GB", 0x0C09: "AU", 0x1009: "CA", 0x1409: "NZ",
    0x1809: "IE", 0x1C09: "ZA", 0x2009: "IN",
    # Dos números para España: el antiguo y el de las voces modernas.
    0x040A: "ES", 0x0C0A: "ES",
    0x080A: "MX", 0x2C0A: "AR", 0x200A: "VE", 0x240A: "CO", 0x280A: "PE",
    0x140A: "CR", 0x180A: "PA", 0x300A: "EC", 0x380A: "UY", 0x3C0A: "PY",
    0x340A: "CL", 0x400A: "BO", 0x1C0A: "DO", 0x100A: "GT", 0x540A: "US",
    0x0416: "BR", 0x0816: "PT",
    0x040C: "FR", 0x0C0C: "CA", 0x0407: "DE", 0x0410: "IT", 0x0413: "NL",
    0x0804: "CN", 0x0404: "TW",
}


def _idioma_de(crudo: str) -> str:
    """Traduce el identificador de idioma de una voz a algo como ``es-ES``."""
    primero = (crudo or "").split(";")[0].strip()
    if not primero:
        return ""
    try:
        numero = int(primero, 16)
    except ValueError:
        return ""
    lengua = IDIOMAS.get(numero & 0x3FF, "")
    if not lengua:
        return ""
    region = REGIONES.get(numero, "")
    return "%s-%s" % (lengua, region) if region else lengua


def _parecido(voz: str, buscado: str) -> int:
    """Cuánto se parecen dos códigos: 2 exacto, 1 misma lengua, 0 nada."""
    if not voz or not buscado:
        return 0
    una = voz.split("-")
    otra = buscado.split("-")
    if una[0].lower() != otra[0].lower():
        return 0
    if len(una) > 1 and len(otra) > 1 and una[1].upper() == otra[1].upper():
        return 2
    return 1


class MotorVocesDeWindows:
    """Las voces de los tres catálogos de Windows, en una sola lista."""

    def __init__(self, carpeta: Path, ajustes: dict) -> None:
        self._ajustes = dict(ajustes)
        self._voz = None
        self._pausado = False
        self._fichas: list = []
        self._arrancar()

    def _arrancar(self) -> None:
        """Conecta con SAPI y recoge las voces de los catálogos elegidos."""
        try:
            import win32com.client

            self._voz = win32com.client.Dispatch("SAPI.SpVoice")
        except Exception as error:
            log.warning("No hay SAPI en este equipo: %s", error)
            self._voz = None
            return
        self._fichas = self._recoger()
        if not self._fichas:
            log.warning("No se ha encontrado ninguna voz en los catálogos")
            return
        guardada = str(self._ajustes.get("_voz_elegida", ""))
        if not (guardada and self.elegir_voz(guardada)):
            self.elegir_voz(self._fichas[0][0])

    def _recoger(self) -> list:
        """Recorre los catálogos y devuelve ``(nombre, idioma, token)``.

        Una misma voz puede estar en dos catálogos —pasa con las clásicas— y se
        deja una sola: dos entradas idénticas en la lista no ayudan a nadie a
        elegir.
        """
        import win32com.client

        # Cada catálogo con su ajuste escrito entero.  Antes se armaba la clave
        # juntando «usar_» con el nombre del catálogo: funcionaba, pero una
        # clave que no aparece escrita en ninguna parte no se puede comprobar, y
        # un ajuste que dejara de leerse no lo notaría nadie.
        POR_CATALOGO = {"onecore": "usar_onecore", "clasicas": "usar_clasicas",
                        "servidor": "usar_servidor"}
        cuales = {clave for clave, _ruta, _rotulo in CATALOGOS
                  if self._ajustes.get(POR_CATALOGO.get(clave, ""), True)}
        salida = []
        vistos: set = set()
        for clave, ruta, rotulo in CATALOGOS:
            if clave not in cuales:
                continue
            try:
                catalogo = win32com.client.Dispatch("SAPI.SpObjectTokenCategory")
                catalogo.SetId(ruta, False)
                fichas = catalogo.EnumerateTokens()
            except Exception as error:
                # Que un catálogo no exista es lo normal: el de servidor solo
                # está si alguien instaló algo de Microsoft que lo trajera.
                log.debug("Catálogo %s no disponible: %s", clave, error)
                continue
            for numero in range(fichas.Count):
                ficha = fichas.Item(numero)
                try:
                    nombre = ficha.GetDescription()
                except Exception:
                    continue
                if nombre in vistos:
                    continue
                vistos.add(nombre)
                try:
                    idioma = _idioma_de(ficha.GetAttribute("Language"))
                except Exception:
                    idioma = ""
                if self._ajustes.get("decir_de_donde") and rotulo:
                    nombre = "%s [%s]" % (nombre, rotulo)
                salida.append((nombre, idioma, ficha))
        return salida

    # -- voces ---------------------------------------------------------------

    @property
    def disponible(self) -> bool:
        return self._voz is not None and bool(self._fichas)

    def voces(self) -> list:
        return [nombre for nombre, _idioma, _ficha in self._fichas]

    def elegir_voz(self, nombre: str) -> bool:
        if self._voz is None:
            return False
        for cual, _idioma, ficha in self._fichas:
            if cual == nombre:
                try:
                    self._voz.Voice = ficha
                    return True
                except Exception as error:
                    log.debug("No se ha podido poner «%s»: %s", nombre, error)
                    return False
        return False

    def voz_actual(self) -> str:
        if self._voz is None:
            return ""
        try:
            puesta = self._voz.Voice.GetDescription()
        except Exception:
            return ""
        for nombre, _idioma, _ficha in self._fichas:
            if nombre == puesta or nombre.startswith(puesta + " ["):
                return nombre
        return puesta

    def voces_con_idioma(self) -> list:
        return [(nombre, idioma) for nombre, idioma, _ficha in self._fichas]

    def voz_para_idioma(self, codigo: str) -> str:
        """La voz que mejor lee ese idioma, con la del país exacto delante."""
        if not codigo:
            return ""
        mejor, nota_mejor = "", 0
        for nombre, idioma, _ficha in self._fichas:
            nota = _parecido(idioma, codigo)
            if nota > nota_mejor:
                mejor, nota_mejor = nombre, nota
        return mejor

    # -- ajustes -------------------------------------------------------------

    def establecer_velocidad(self, valor: int) -> None:
        if self._voz is None:
            return
        try:
            self._voz.Rate = max(-10, min(10, int(valor)))
        except Exception as error:
            log.debug("Al cambiar la velocidad: %s", error)

    def establecer_volumen(self, valor: int) -> None:
        if self._voz is None:
            return
        try:
            self._voz.Volume = max(0, min(100, int(valor)))
        except Exception as error:
            log.debug("Al cambiar el volumen: %s", error)

    # -- hablar --------------------------------------------------------------

    def decir(self, texto: str, con_marcas: bool = False) -> bool:
        if not texto or self._voz is None:
            return False
        try:
            self.detener()
            self._voz.Speak(texto, _ASINCRONO | (_ES_XML if con_marcas else 0))
            return True
        except Exception as error:
            log.error("No se ha podido leer: %s", error)
            return False

    @staticmethod
    def con_tono(texto: str, tono: int) -> str:
        """Estas voces sí entienden el marcado de tono: es el de SAPI.

        El texto se escapa siempre: un libro trae signos de menor y de
        ampersand, y sin escaparlos la marca se rompe y se pierde la frase.
        """
        limpio = (texto.replace("&", "&amp;").replace("<", "&lt;")
                  .replace(">", "&gt;"))
        if not tono:
            return limpio
        return '<pitch middle="%d">%s</pitch>' % (max(-10, min(10, tono)), limpio)

    def pausar(self) -> None:
        if self._voz is None or self._pausado:
            return
        try:
            self._voz.Pause()
            self._pausado = True
        except Exception as error:
            log.debug("Al pausar: %s", error)

    def continuar(self) -> None:
        if self._voz is None or not self._pausado:
            return
        try:
            self._voz.Resume()
            self._pausado = False
        except Exception as error:
            log.debug("Al continuar: %s", error)

    def detener(self) -> None:
        if self._voz is None:
            return
        try:
            # Si estaba en pausa hay que reanudar antes de vaciar la cola: si
            # no, SAPI se queda esperando y la voz no vuelve a hablar.
            if self._pausado:
                self._voz.Resume()
                self._pausado = False
            self._voz.Speak("", _ASINCRONO | _VACIAR)
        except Exception as error:
            log.debug("Al detener: %s", error)

    @property
    def pausada(self) -> bool:
        return self._pausado

    @property
    def hablando(self) -> bool:
        if self._voz is None:
            return False
        if self._pausado:
            return True
        try:
            return int(self._voz.Status.RunningState) == _HABLANDO
        except Exception:
            return False

    def cerrar(self) -> None:
        self.detener()
        self._voz = None


def crear(carpeta, ajustes):
    """Lo que el visor llama para poner esta voz. Es la única entrada."""
    return MotorVocesDeWindows(Path(carpeta), dict(ajustes or {}))
