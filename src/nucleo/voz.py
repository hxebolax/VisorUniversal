# -*- coding: utf-8 -*-
"""Sintetizador de voz del sistema (SAPI 5 de Windows).

Es una voz **propia del programa**, distinta de la del lector de pantalla.  Eso
es justo lo que hace falta para escuchar un libro entero: el lector de pantalla
está para manejar la aplicación —los menús, los diálogos, los avisos— y esta
voz está para leer, con su propia velocidad y, si se quiere, con otra voz que
se distinga de la del sistema.

Se habla con SAPI a través de COM, con ``win32com``, que ya viene instalado
como parte de ``pywin32``.  No hace falta ningún paquete nuevo.

**Todo esto se usa desde el hilo de la interfaz.**  wxPython inicializa COM en
ese hilo, y SAPI hace su propio trabajo en segundo plano: ``Speak`` vuelve al
instante y la voz sigue hablando.  Llamarlo desde otro hilo obligaría a
inicializar COM allí y no aportaría nada.
"""

from __future__ import annotations

from .registro import obtener_registro

log = obtener_registro(__name__)

#: Banderas de ``SpVoice.Speak``.
_ASINCRONO = 1     # no bloquear: la voz habla mientras el programa sigue
_ES_XML = 8        # el texto lleva marcas: <pitch>, <rate>, <volume>...
_VACIAR = 2        # descartar lo que hubiera en la cola

#: Valor de ``Status.RunningState`` mientras SAPI está pronunciando algo.
_HABLANDO = 2

#: Límites de la velocidad en SAPI.  Es una escala propia y poco intuitiva, de
#: -10 a 10, donde 0 es la velocidad normal de la voz.  Hacia fuera el programa
#: usa un porcentaje de 0 a 100, que es lo que se puede poner en un deslizador
#: y decir en voz alta sin que haya que explicarlo.
VELOCIDAD_MINIMA = -10
VELOCIDAD_MAXIMA = 10

#: Porcentaje que corresponde a la velocidad normal de la voz.
RAPIDEZ_NORMAL = 50


def sapi_desde_porcentaje(porcentaje: int) -> int:
    """Convierte una rapidez de 0 a 100 en la escala de SAPI.

    50 es la velocidad normal de la voz, 0 la más lenta y 100 la más rápida.
    """
    acotado = max(0, min(100, int(porcentaje)))
    return round((acotado - RAPIDEZ_NORMAL) * VELOCIDAD_MAXIMA / RAPIDEZ_NORMAL)


# ---------------------------------------------------------------------------
# Idiomas de las voces
# ---------------------------------------------------------------------------

#: Idioma principal de cada identificador de idioma de Windows.  SAPI no dice
#: «español»: dice ``40a``, que es un LCID en hexadecimal cuyos diez bits bajos
#: son el idioma y el resto la variante.  Esta tabla traduce esos diez bits al
#: código de dos letras con el que vienen escritos los libros.
IDIOMAS_PRINCIPALES = {
    0x01: "ar", 0x02: "bg", 0x03: "ca", 0x04: "zh", 0x05: "cs", 0x06: "da",
    0x07: "de", 0x08: "el", 0x09: "en", 0x0A: "es", 0x0B: "fi", 0x0C: "fr",
    0x0D: "he", 0x0E: "hu", 0x0F: "is", 0x10: "it", 0x11: "ja", 0x12: "ko",
    0x13: "nl", 0x14: "no", 0x15: "pl", 0x16: "pt", 0x18: "ro", 0x19: "ru",
    0x1A: "hr", 0x1B: "sk", 0x1C: "sq", 0x1D: "sv", 0x1E: "th", 0x1F: "tr",
    0x20: "ur", 0x21: "id", 0x22: "uk", 0x23: "be", 0x24: "sl", 0x25: "et",
    0x26: "lv", 0x27: "lt", 0x29: "fa", 0x2A: "vi", 0x2B: "hy", 0x2D: "eu",
    0x2F: "mk", 0x36: "af", 0x37: "ka", 0x39: "hi", 0x3E: "ms", 0x3F: "kk",
    0x40: "ky", 0x41: "sw", 0x45: "bn", 0x49: "ta", 0x4A: "te", 0x4B: "kn",
    0x4C: "ml", 0x4E: "mr", 0x50: "mn", 0x56: "gl", 0x5E: "am", 0x61: "ne",
    0x6A: "yo", 0x7E: "br", 0x91: "gd",
}

#: Región de los identificadores completos que de verdad se distinguen al oído:
#: un texto en inglés británico leído con voz estadounidense se entiende, pero
#: no es lo que pone el documento, y esa es justamente la diferencia que hace
#: un lector de pantalla cuando el libro declara sus idiomas.
REGIONES = {
    0x0409: "US", 0x0809: "GB", 0x0C09: "AU", 0x1009: "CA", 0x1409: "NZ",
    0x1809: "IE", 0x1C09: "ZA", 0x2009: "IN",
    # El español tiene **dos** números para España: el antiguo, 040A, y el que
    # llevan las voces modernas de Windows 10 y 11, C0A.  Sin el segundo, las
    # voces de Helena, Laura y Pablo salían sin país y el programa podía
    # preferirles una voz de otro país que sí lo llevara escrito.
    0x040A: "ES", 0x0C0A: "ES",
    0x080A: "MX", 0x2C0A: "AR", 0x200A: "VE", 0x240A: "CO", 0x280A: "PE",
    0x140A: "CR", 0x180A: "PA", 0x300A: "EC", 0x380A: "UY", 0x3C0A: "PY",
    0x340A: "CL", 0x400A: "BO", 0x1C0A: "DO", 0x100A: "GT", 0x440A: "SV",
    0x480A: "HN", 0x4C0A: "NI", 0x500A: "PR", 0x540A: "US",
    0x0416: "BR", 0x0816: "PT",
    0x040C: "FR", 0x0C0C: "CA", 0x080C: "BE", 0x100C: "CH",
    0x0407: "DE", 0x0807: "CH", 0x0C07: "AT",
    0x0410: "IT", 0x0810: "CH",
    0x0413: "NL", 0x0813: "BE",
    0x0804: "CN", 0x0404: "TW", 0x0C04: "HK",
}


def idioma_de_lcid(texto: str) -> str:
    """Traduce el identificador de idioma de una voz a un código como ``en-GB``.

    SAPI puede dar varios separados por punto y coma cuando una voz sirve para
    más de un idioma; se toma el primero, que es el suyo de verdad.
    """
    primero = (texto or "").split(";")[0].strip()
    if not primero:
        return ""
    try:
        lcid = int(primero, 16)
    except ValueError:
        return ""
    principal = IDIOMAS_PRINCIPALES.get(lcid & 0x3FF, "")
    if not principal:
        return ""
    region = REGIONES.get(lcid, "")
    return "%s-%s" % (principal, region) if region else principal


def parecido(voz: str, buscado: str) -> int:
    """Cuánto se parecen dos códigos de idioma.

    * 2: coinciden del todo, región incluida (``en-GB`` con ``en-GB``).
    * 1: coincide la lengua pero no la variante (``en-GB`` con ``en-US``).
    * 0: no tienen nada que ver.

    Con esto se elige la voz de un fragmento: la del país exacto si está
    instalada y, si no, cualquiera del mismo idioma, que es mucho mejor que
    oír una frase inglesa leída por una voz española.
    """
    if not voz or not buscado:
        return 0
    partes_voz = voz.split("-")
    partes_buscado = buscado.split("-")
    if partes_voz[0].lower() != partes_buscado[0].lower():
        return 0
    if len(partes_voz) > 1 and len(partes_buscado) > 1 \
            and partes_voz[1].upper() == partes_buscado[1].upper():
        return 2
    return 1


class Sintetizador:
    """Voz del sistema, con lo justo para leer un libro.

    La conexión con SAPI se hace **la primera vez que se necesita** y no al
    arrancar: crear el objeto COM cuesta unas décimas de segundo, y quien no
    use la lectura en voz alta no tiene por qué pagarlas.
    """

    def __init__(self) -> None:
        self._voz = None
        self._intentado = False
        self._pausado = False
        self._por_idioma = None

    # -- preparación ---------------------------------------------------------

    def _asegurar(self) -> bool:
        """Conecta con SAPI si hace falta.  Devuelve si hay voz utilizable."""
        if self._voz is not None:
            return True
        if self._intentado:
            return False
        self._intentado = True
        try:
            import win32com.client

            self._voz = win32com.client.Dispatch("SAPI.SpVoice")
            log.info("Voz del sistema preparada (SAPI 5)")
            return True
        except Exception as error:
            log.warning("No hay ninguna voz SAPI 5 disponible: %s", error)
            self._voz = None
            return False

    @property
    def disponible(self) -> bool:
        """Indica si el equipo tiene voces con las que leer."""
        return self._asegurar() and bool(self.voces())

    def voces(self) -> list[str]:
        """Nombres de las voces instaladas, en el orden en que las da Windows."""
        if not self._asegurar():
            return []
        nombres: list[str] = []
        try:
            fichas = self._voz.GetVoices()
            for numero in range(fichas.Count):
                nombres.append(fichas.Item(numero).GetDescription())
        except Exception as error:
            log.debug("No se han podido listar las voces: %s", error)
        return nombres

    # -- ajustes -------------------------------------------------------------

    def elegir_voz(self, nombre: str) -> bool:
        """Selecciona una voz por su nombre.  Devuelve si se ha podido.

        Se busca por nombre y no por número porque el orden de las voces cambia
        al instalar o quitar alguna, y guardar un número en la configuración
        haría que un día el programa hablara con otra voz sin motivo aparente.
        """
        if not nombre or not self._asegurar():
            return False
        try:
            fichas = self._voz.GetVoices()
            for numero in range(fichas.Count):
                if fichas.Item(numero).GetDescription() == nombre:
                    self._voz.Voice = fichas.Item(numero)
                    return True
        except Exception as error:
            log.debug("No se ha podido elegir la voz «%s»: %s", nombre, error)
        return False

    def voces_con_idioma(self) -> list[tuple[str, str]]:
        """Las voces instaladas con el idioma de cada una: ``(nombre, código)``.

        Se pregunta una sola vez y se guarda: recorrer las fichas de SAPI por
        COM cuesta unas décimas, y esto se consulta en cada frase que se lee.
        """
        if self._por_idioma is not None:
            return self._por_idioma
        self._por_idioma = []
        if not self._asegurar():
            return self._por_idioma
        try:
            fichas = self._voz.GetVoices()
            for numero in range(fichas.Count):
                ficha = fichas.Item(numero)
                try:
                    idioma = idioma_de_lcid(ficha.GetAttribute("Language"))
                except Exception:
                    idioma = ""
                self._por_idioma.append((ficha.GetDescription(), idioma))
        except Exception as error:
            log.debug("No se han podido leer los idiomas de las voces: %s", error)
        return self._por_idioma

    def voz_para_idioma(self, codigo: str) -> str:
        """Nombre de la voz instalada que mejor lee ese idioma, o cadena vacía.

        Devolver el nombre en lugar de cambiar la voz aquí es a propósito: quien
        llama necesita saber **si** hay voz antes de decidir si cambia, y así
        puede además no tocar nada cuando la que ya está puesta sirve.
        """
        if not codigo:
            return ""
        mejor = ""
        mejor_nota = 0
        for nombre, idioma in self.voces_con_idioma():
            nota = parecido(idioma, codigo)
            if nota > mejor_nota:
                mejor, mejor_nota = nombre, nota
        return mejor

    def voz_actual(self) -> str:
        """Nombre de la voz que está puesta ahora mismo."""
        if not self._asegurar():
            return ""
        try:
            return self._voz.Voice.GetDescription()
        except Exception:
            return ""

    def establecer_velocidad(self, valor: int) -> None:
        """Ajusta la velocidad, entre -10 y 10."""
        if not self._asegurar():
            return
        try:
            self._voz.Rate = max(VELOCIDAD_MINIMA, min(VELOCIDAD_MAXIMA, int(valor)))
        except Exception as error:
            log.debug("No se ha podido cambiar la velocidad: %s", error)

    def establecer_volumen(self, valor: int) -> None:
        """Ajusta el volumen, entre 0 y 100."""
        if not self._asegurar():
            return
        try:
            self._voz.Volume = max(0, min(100, int(valor)))
        except Exception as error:
            log.debug("No se ha podido cambiar el volumen: %s", error)

    # -- reproducción --------------------------------------------------------

    def decir(self, texto: str, con_marcas: bool = False) -> bool:
        """Empieza a decir un texto, descartando lo que hubiera antes.

        :param con_marcas: Si el texto lleva marcas de SAPI —``<pitch>`` y
            compañía— que hay que interpretar en vez de leer en voz alta.  Va
            apagado por omisión porque el texto de un libro puede traer signos
            de menor y mayor, y leerlos como marcas se comería trozos de frase.
        :return: ``True`` si la voz ha aceptado el texto.
        """
        if not texto or not self._asegurar():
            return False
        try:
            self.detener()
            self._voz.Speak(texto, _ASINCRONO | (_ES_XML if con_marcas else 0))
            return True
        except Exception as error:
            log.error("No se ha podido leer en voz alta: %s", error)
            return False

    @staticmethod
    def con_tono(texto: str, tono: int) -> str:
        """Envuelve un texto en una marca que le cambia el tono.

        El tono va de -10 a 10 y es una escala propia de SAPI, como la de la
        velocidad.  Lo que hay que saber es que ±3 se nota sin sonar raro y ±8
        convierte la voz en un dibujo animado.

        El texto se escapa siempre: un libro trae signos de menor y de
        ampersand, y sin escaparlos la marca se rompe y se pierde la frase.
        """
        limpio = (texto.replace("&", "&amp;").replace("<", "&lt;")
                  .replace(">", "&gt;"))
        if not tono:
            return limpio
        return '<pitch middle="%d">%s</pitch>' % (max(-10, min(10, tono)), limpio)

    def pausar(self) -> None:
        """Detiene la voz dejándola donde está."""
        if self._voz is None or self._pausado:
            return
        try:
            self._voz.Pause()
            self._pausado = True
        except Exception as error:
            log.debug("No se ha podido pausar: %s", error)

    def continuar(self) -> None:
        """Reanuda una voz pausada."""
        if self._voz is None or not self._pausado:
            return
        try:
            self._voz.Resume()
            self._pausado = False
        except Exception as error:
            log.debug("No se ha podido continuar: %s", error)

    def detener(self) -> None:
        """Calla y vacía la cola."""
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
            log.debug("No se ha podido detener la voz: %s", error)

    @property
    def pausada(self) -> bool:
        """Indica si la voz está pausada."""
        return self._pausado

    @property
    def hablando(self) -> bool:
        """Indica si la voz está diciendo algo ahora mismo.

        Es lo que permite encadenar la lectura: cuando deja de hablar, se le
        pasa la frase siguiente.
        """
        if self._voz is None or self._pausado:
            return self._pausado
        try:
            return int(self._voz.Status.RunningState) == _HABLANDO
        except Exception:
            return False
