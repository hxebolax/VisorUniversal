# -*- coding: utf-8 -*-
"""eSpeak NG con voces MBROLA para el Visor Universal.

MBROLA no calcula la voz: **la pega**. Cada voz es una grabación de una persona
real troceada en difonos —el paso de un sonido al siguiente—, y hablar consiste
en enganchar los trozos que tocan. Es de los años noventa y se nota en las
uniones, pero es una persona la que suena, no una máquina imitándola, y en un
libro de doscientas páginas esa diferencia se agradece.

El trabajo se reparte: eSpeak lee el texto y decide qué sonidos hay que hacer y
con qué entonación; MBROLA los hace. Por eso este motor habla español correcto
—las reglas de pronunciación son las de eSpeak, que las tiene muy trabajadas—
con una voz que no es la de eSpeak.

Siete voces en español: cuatro de España, dos de México y una de Venezuela. Y
más de setenta en otros idiomas, que se pueden bajar desde aquí mismo.

Qué lo diferencia del paquete de eSpeak
---------------------------------------

Son dos paquetes y no uno porque cada biblioteca hace bien una cosa distinta, y
no hay ninguna que haga las dos:

* **eSpeak** usa la biblioteca de NVDA, compilada con «sonic», que es lo que
  deja triplicar la velocidad máxima. Medido con la misma frase: 1,55 segundos
  contra 5,21. Mucha gente usa eSpeak exactamente por eso.
* **Este** usa la oficial de eSpeak NG, que es la única de Windows compilada con
  MBROLA, y no lleva sonic. La velocidad llega hasta donde llega eSpeak solo.

Así que uno corre y el otro suena mejor. Están los dos y se elige.

Cómo suena
----------

Igual que en el paquete de eSpeak: la biblioteca **entrega el sonido** en trozos
y lo reproduce BASS, que el visor ya lleva para los libros DAISY. Se hace así, y
no dejando que reproduzca ella, por la pausa: reproduciendo ella no hay manera
de pausar sin perder el sitio, y pausar en mitad de un párrafo y seguir donde se
dejó es lo primero que se le pide a un lector de libros.
"""

from __future__ import annotations

import ctypes
import logging
import sys
import threading
from pathlib import Path

log = logging.getLogger("visor.motor.espeak_mbrola")

_AQUI = Path(__file__).resolve().parent
if str(_AQUI) not in sys.path:
    sys.path.insert(0, str(_AQUI))

#: Los parámetros de eSpeak, por su número.  Son los de su propia interfaz.
RATE = 1
VOLUME = 2
PITCH = 3
RANGE = 4

#: Los límites de cada uno.  El de la velocidad llega a 449 y no a 450 a
#: propósito: en 450 eSpeak enciende su propio acelerador y la voz cambia de
#: carácter justo en el borde de la escala.
VELOCIDAD_MINIMA = 80
VELOCIDAD_MAXIMA = 449
TONO_MINIMO = 0
TONO_MAXIMO = 99

#: Cómo se le pide el sonido.  El 0 es «reproduce tú», que es lo que **no** se
#: quiere.  El 2 es «sintetiza y ve entregando», que es este.
SALIDA_SINCRONA = 2

#: Y que si algo va mal no cierre el programa entero, que es lo que hace por
#: omisión y sería catastrófico dentro de un lector de libros.
NO_SALIR = 0x8000

#: Cómo hay que decirle que el texto viene en UTF-8.  Sin esto lo adivina, y a
#: veces adivina mal: una eñe pasa a ser dos letras raras.
TEXTO_UTF8 = 1

#: Cómo empiezan los nombres de las voces MBROLA dentro de eSpeak.
MARCA = "mb-"

#: De dónde se bajan las voces de otros idiomas, cuando se piden.
DESCARGA = "https://github.com/numediart/MBROLA-voices/raw/master/data/%s/%s"

#: Cuánto se espera a que una voz se baje.  Son entre uno y seis megas: con una
#: conexión mala tarda, y cortar a la mitad dejaría un archivo roto que luego
#: haría fallar la voz sin explicación.
ESPERA_DESCARGA = 180


def _por_ciento(valor: int, minimo: int, maximo: int) -> int:
    """De la escala de eSpeak a un porcentaje de 0 a 100."""
    return int(round((valor - minimo) * 100.0 / (maximo - minimo)))


def _desde_por_ciento(porcentaje: int, minimo: int, maximo: int) -> int:
    """Y al revés."""
    acotado = max(0, min(100, int(porcentaje)))
    return int(round(minimo + acotado * (maximo - minimo) / 100.0))


class _Voz(ctypes.Structure):
    """Lo que eSpeak cuenta de cada una de sus voces."""

    _fields_ = [
        ("name", ctypes.c_char_p),
        ("languages", ctypes.c_char_p),
        ("identifier", ctypes.c_char_p),
        ("gender", ctypes.c_byte),
        ("age", ctypes.c_byte),
        ("variant", ctypes.c_byte),
        ("xx1", ctypes.c_byte),
        ("score", ctypes.c_int),
        ("spare", ctypes.c_void_p),
    ]


_RETORNO = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(ctypes.c_short),
                            ctypes.c_int, ctypes.c_void_p)


def _texto(crudo) -> str:
    """Una cadena de eSpeak, ya legible."""
    if not crudo:
        return ""
    if isinstance(crudo, bytes):
        return crudo.decode("utf-8", "replace")
    return str(crudo)


class MotorEspeakMbrola:
    """eSpeak NG hablando con voces MBROLA."""

    def __init__(self, carpeta: Path, ajustes: dict) -> None:
        self._carpeta = Path(carpeta)
        self._ajustes = dict(ajustes)
        self._dll = None
        self._muestreo = 0
        self._voces: list = []
        self._variantes: dict = {}
        self._voz = ""
        self._variante = str(self._ajustes.get("variante", "none"))
        self._pcm = bytearray()
        self._cerrojo = threading.RLock()
        self._canal = 0
        self._pausado = False
        self._bass = False
        self._arrancar()

    # -- arranque ------------------------------------------------------------

    @property
    def _carpeta_de_voces(self) -> Path:
        """Donde viven los archivos de voz de MBROLA."""
        return self._carpeta / "espeak-ng-data" / "mbrola"

    def _arrancar(self) -> None:
        """Carga las dos bibliotecas y le pregunta a eSpeak qué voces tiene."""
        try:
            # MBROLA primero, y a mano.  eSpeak la carga por su nombre a
            # secas, y Windows la buscaría junto al ejecutable del programa,
            # no junto a eSpeak: cargándola aquí ya está en memoria y la
            # encuentra.  Sin esto, elegir una voz falla con «Could not load
            # the mbrola.dll file» y no hay forma de saber por qué.
            ctypes.cdll.LoadLibrary(str(self._carpeta / "mbrola.dll"))
        except Exception as error:
            log.warning("No se ha podido cargar MBROLA: %s", error)
            return
        try:
            self._dll = ctypes.cdll.LoadLibrary(str(self._carpeta / "espeak.dll"))
        except Exception as error:
            log.warning("No se ha podido cargar eSpeak: %s", error)
            self._dll = None
            return
        self._dll.espeak_Info.restype = ctypes.c_char_p
        self._dll.espeak_ListVoices.restype = ctypes.POINTER(ctypes.POINTER(_Voz))
        self._dll.espeak_GetCurrentVoice.restype = ctypes.POINTER(_Voz)
        self._dll.espeak_SetVoiceByName.argtypes = (ctypes.c_char_p,)
        self._muestreo = self._dll.espeak_Initialize(
            SALIDA_SINCRONA, 300, str(self._carpeta).encode("mbcs", "replace"),
            NO_SALIR)
        if self._muestreo <= 0:
            log.warning("eSpeak no ha arrancado (código %d)", self._muestreo)
            self._dll = None
            return
        self._retorno = _RETORNO(self._recibir)
        self._dll.espeak_SetSynthCallback(self._retorno)
        self._voces = self._listar_voces()
        self._variantes = self._listar_variantes()
        log.info("eSpeak NG %s con %d voces MBROLA",
                 _texto(self._dll.espeak_Info()), len(self._voces))
        self._aplicar_ajustes()
        guardada = str(self._ajustes.get("_voz_elegida", ""))
        if guardada:
            self.elegir_voz(guardada)
        else:
            self._elegir_la_primera_que_este()

    def _elegir_la_primera_que_este(self) -> None:
        """Pone la primera voz que ya esté en el equipo.

        La primera de la lista a secas no vale: con «más idiomas» puesto la
        lista empieza por el afrikáans, y arrancar el motor se pondría a bajar
        ocho megas que nadie ha pedido. Solo se baja lo que alguien elige.
        """
        for identificador, nombre, _idioma in self._voces:
            if self._esta_instalada(identificador):
                self._poner_voz(identificador)
                return
        if self._voces:
            self._poner_voz(self._voces[0][0])

    def _listar_voces(self) -> list:
        """Las voces MBROLA: ``(identificador, nombre, idioma)``.

        eSpeak declara noventa aunque no esté ninguna instalada: las definiciones
        vienen con él y los archivos de voz son otra cosa.  Aquí se enseñan solo
        las que se pueden usar de verdad —las que tienen su archivo—, porque una
        lista con noventa nombres de los que funcionan siete es una lista que
        engaña.

        Con «más idiomas» puesto se enseñan todas, y la que no esté se baja al
        elegirla.
        """
        salida = []
        todas = bool(self._ajustes.get("mas_idiomas"))
        try:
            fichas = self._dll.espeak_ListVoices(None)
        except Exception as error:
            log.debug("No se han podido listar las voces: %s", error)
            return salida
        numero = 0
        while fichas[numero]:
            ficha = fichas[numero].contents
            identificador = _texto(ficha.identifier).replace("\\", "/")
            identificador = identificador.split("/")[-1].lower()
            if identificador.startswith(MARCA):
                # El primer byte de «languages» es la prioridad, no el idioma.
                idioma = _texto(ficha.languages[1:] if ficha.languages else b"")
                if todas or self._esta_instalada(identificador):
                    salida.append((identificador, _texto(ficha.name), idioma))
            numero += 1
        return salida

    def _esta_instalada(self, identificador: str) -> bool:
        """Si el archivo de esa voz está en el equipo."""
        archivo = self._carpeta_de_voces / identificador[len(MARCA):]
        return archivo.is_file() and archivo.stat().st_size > 0

    def _listar_variantes(self) -> dict:
        """Las variantes de voz, leídas de sus archivos como hace NVDA.

        Sí, también valen con MBROLA: una variante cambia el tono y el timbre
        por encima de la voz grabada, así que la misma voz española suena más
        aguda, más grave o susurrando.
        """
        variantes = {"none": "Sin variante"}
        carpeta = self._carpeta / "espeak-ng-data" / "voices" / "!v"
        if not carpeta.is_dir():
            return variantes
        for archivo in sorted(carpeta.iterdir()):
            if not archivo.is_file():
                continue
            nombre = None
            try:
                # En latín-1 y no en UTF-8, igual que NVDA: la codificación de
                # estos archivos no está declarada en ninguna parte y así al
                # menos no revientan nunca.
                with archivo.open("r", encoding="latin-1") as texto:
                    for linea in texto:
                        if linea.startswith("name "):
                            partes = linea.split(" ")
                            if len(partes) == 2:
                                nombre = partes[1].rstrip()
                            break
            except OSError as error:
                log.debug("Variante %s ilegible: %s", archivo.name, error)
                continue
            if nombre:
                variantes[archivo.name] = nombre
        return variantes

    def _aplicar_ajustes(self) -> None:
        """Lleva a eSpeak el tono y la entonación."""
        if self._dll is None:
            return
        self._poner(PITCH, _desde_por_ciento(
            int(self._ajustes.get("tono", 50)), TONO_MINIMO, TONO_MAXIMO))
        self._poner(RANGE, _desde_por_ciento(
            int(self._ajustes.get("entonacion", 75)), TONO_MINIMO, TONO_MAXIMO))

    def _poner(self, parametro: int, valor: int) -> None:
        try:
            self._dll.espeak_SetParameter(parametro, int(valor), 0)
        except Exception as error:
            log.debug("No se ha podido poner el parámetro %d: %s", parametro, error)

    # -- qué voces hay -------------------------------------------------------

    @property
    def disponible(self) -> bool:
        return self._dll is not None and bool(self._voces)

    def voces(self) -> list:
        """Los nombres de las voces, como los enseña eSpeak."""
        return [nombre for _identificador, nombre, _idioma in self._voces]

    def variantes(self) -> dict:
        """Las variantes disponibles, por si alguien las quiere listar."""
        return dict(self._variantes)

    def elegir_voz(self, nombre: str) -> bool:
        for identificador, cual, _idioma in self._voces:
            if cual == nombre:
                if not self._esta_instalada(identificador):
                    self._bajar(identificador)
                return self._poner_voz(identificador)
        return False

    def _bajar(self, identificador: str) -> bool:
        """Trae de internet el archivo de una voz que no está.

        Solo pasa con «más idiomas» puesto: sin eso, las que se ofrecen son las
        que ya están y aquí no se entra nunca.

        Se baja a un archivo aparte y se renombra al final.  Cortar la descarga
        a la mitad dejaría un archivo del tamaño equivocado, y MBROLA con un
        archivo roto no dice que esté roto: se calla o suena mal.
        """
        import urllib.request

        cual = identificador[len(MARCA):]
        destino = self._carpeta_de_voces / cual
        medias = destino.with_name(cual + ".bajando")
        log.info("Bajando la voz MBROLA «%s»...", cual)
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(DESCARGA % (cual, cual),
                                        timeout=ESPERA_DESCARGA) as respuesta:
                medias.write_bytes(respuesta.read())
            if medias.stat().st_size <= 0:
                raise OSError("ha llegado vacía")
            medias.replace(destino)
        except Exception as error:
            log.warning("No se ha podido bajar la voz «%s»: %s", cual, error)
            try:
                medias.unlink(missing_ok=True)
            except OSError:
                pass
            return False
        log.info("Voz «%s» lista (%.1f MB)", cual,
                 destino.stat().st_size / 1048576)
        return True

    def _poner_voz(self, identificador: str) -> bool:
        """Pone la voz con su variante, que en eSpeak van juntas.

        Se le pasan pegadas con un signo de más —``mb-es1+Andrea``— porque
        eSpeak no tiene dos ajustes: tiene un nombre de voz que puede llevar
        variante.
        """
        if self._dll is None:
            return False
        cual = identificador
        if self._variante and self._variante != "none":
            cual = "%s+%s" % (identificador, self._variante)
        try:
            fallo = self._dll.espeak_SetVoiceByName(cual.encode("utf-8"))
            if fallo:
                log.warning("eSpeak ha rechazado la voz «%s» (código %d)",
                            cual, fallo)
                return False
            self._voz = identificador
            return True
        except Exception as error:
            log.debug("No se ha podido poner la voz «%s»: %s", cual, error)
            return False

    def voz_actual(self) -> str:
        for identificador, nombre, _idioma in self._voces:
            if identificador == self._voz:
                return nombre
        return ""

    def voces_con_idioma(self) -> list:
        """Cada voz con su idioma, que eSpeak trae bien puesto."""
        return [(nombre, idioma)
                for _identificador, nombre, idioma in self._voces]

    def voz_para_idioma(self, codigo: str) -> str:
        """La voz que mejor lee ese idioma.

        Con las siete de español instaladas, un libro en español lo lee entero;
        una cita en inglés solo se lee con voz propia si esa voz está bajada, y
        si no, se queda con la que haya, que es lo correcto: vale más leerlo con
        acento que no leerlo.
        """
        if not codigo:
            return ""
        pedido = codigo.replace("_", "-").lower()
        lengua = pedido.split("-")[0]
        aproximada = ""
        for _identificador, nombre, idioma in self._voces:
            suyo = (idioma or "").replace("_", "-").lower()
            if not suyo:
                continue
            if suyo == pedido:
                return nombre
            if suyo.split("-")[0] == lengua and not aproximada:
                aproximada = nombre
        return aproximada

    # -- lo que se puede tocar -----------------------------------------------

    def establecer_velocidad(self, valor: int) -> None:
        """La velocidad, de la escala del visor a la de eSpeak.

        El visor va de -10 a 10 con el 0 en la normal; eSpeak va de 80 a 449
        palabras por minuto.  Aquí no hay aceleración al triple como en el
        paquete de eSpeak: esa la pone «sonic», que la biblioteca oficial no
        lleva.  Quien la quiera tiene el otro paquete.
        """
        if self._dll is None:
            return
        porcentaje = max(0, min(100, 50 + int(valor) * 5))
        self._poner(RATE, _desde_por_ciento(porcentaje, VELOCIDAD_MINIMA,
                                            VELOCIDAD_MAXIMA))

    def establecer_volumen(self, valor: int) -> None:
        """El volumen. eSpeak llega a 200, pero por encima de 100 satura."""
        if self._dll is None:
            return
        self._poner(VOLUME, max(0, min(100, int(valor))))

    @property
    def espera_maxima(self) -> float:
        """Cuánto puede tardar en empezar a sonar.

        MBROLA tarda algo más que eSpeak solo: hay que ir a buscar los trozos
        grabados y pegarlos, y eso es leer de disco.  Sigue siendo cosa de
        décimas, pero la primera frase después de cambiar de voz carga la voz
        entera y eso sí se nota.
        """
        try:
            return float(self._ajustes.get("espera_maxima", 6))
        except (TypeError, ValueError):
            return 6.0

    # -- hablar --------------------------------------------------------------

    def _recibir(self, muestras, cuantas, eventos) -> int:
        """eSpeak entrega el sonido por aquí, en trozos, mientras sintetiza."""
        if cuantas > 0 and muestras:
            self._pcm += ctypes.string_at(muestras, cuantas * 2)
        return 0

    def decir(self, texto: str, con_marcas: bool = False) -> bool:
        """Sintetiza la frase entera y la reproduce.

        ``con_marcas`` se ignora: son marcas de SAPI.  eSpeak tiene las suyas
        —admite SSML— pero no son las mismas, y colar unas por otras haría que
        leyera las etiquetas en voz alta.
        """
        if not texto or self._dll is None:
            return False
        self.detener()
        with self._cerrojo:
            self._pcm = bytearray()
            try:
                crudo = texto.encode("utf-8")
                self._dll.espeak_Synth(crudo, len(crudo) + 1, 0, 0, 0,
                                       TEXTO_UTF8, None, None)
            except Exception as error:
                log.error("eSpeak no ha podido sintetizar: %s", error)
                return False
            if not self._pcm:
                return False
            return self._reproducir(bytes(self._pcm))

    def _reproducir(self, pcm: bytes) -> bool:
        """Manda el sonido a BASS, que es quien lo saca por el altavoz."""
        try:
            from basskit.alto_nivel.reproductor import inicializar
            from basskit.constantes.bass import BASS_STREAM_PRESCAN
            from basskit.dlls.bass import bass
        except Exception as error:
            log.error("No está el reproductor de sonido: %s", error)
            return False
        if not self._bass:
            try:
                inicializar(-1, 44100)
            except Exception as error:
                # Puede estar ya inicializado por el reproductor DAISY, y
                # entonces esto falla y da igual: el sonido sale lo mismo.
                log.debug("BASS ya estaba listo: %s", error)
            self._bass = True
        onda = _envolver_en_wav(pcm, self._muestreo)
        self._memoria = ctypes.create_string_buffer(onda)
        canal = bass.BASS_StreamCreateFile(True, self._memoria, 0, len(onda),
                                           BASS_STREAM_PRESCAN)
        if not canal:
            log.error("BASS no ha podido abrir el sonido de MBROLA")
            return False
        self._canal = canal
        self._pausado = False
        return bool(bass.BASS_ChannelPlay(canal, True))

    @staticmethod
    def con_tono(texto: str, tono: int) -> str:
        """El texto tal cual: el tono se ajusta en los ajustes del motor."""
        return texto

    def pausar(self) -> None:
        if self._canal and not self._pausado:
            from basskit.dlls.bass import bass

            bass.BASS_ChannelPause(self._canal)
            self._pausado = True

    def continuar(self) -> None:
        if self._canal and self._pausado:
            from basskit.dlls.bass import bass

            bass.BASS_ChannelPlay(self._canal, False)
            self._pausado = False

    def detener(self) -> None:
        self._pausado = False
        if self._canal:
            try:
                from basskit.dlls.bass import bass

                bass.BASS_ChannelStop(self._canal)
                bass.BASS_StreamFree(self._canal)
            except Exception as error:
                log.debug("Al detener MBROLA: %s", error)
            self._canal = 0

    @property
    def pausada(self) -> bool:
        return self._pausado

    @property
    def hablando(self) -> bool:
        """Si está sonando ahora mismo.

        Una pausa cuenta como «sigue»: si dijera que no, el visor daría la frase
        por terminada y se saltaría el resto en cuanto alguien pausara.
        """
        if self._pausado:
            return True
        if not self._canal:
            return False
        try:
            from basskit.constantes.bass import BASS_ACTIVE_PLAYING
            from basskit.dlls.bass import bass

            return int(bass.BASS_ChannelIsActive(self._canal)) == BASS_ACTIVE_PLAYING
        except Exception:
            return False

    def cerrar(self) -> None:
        """Suelta el canal de sonido y cierra eSpeak."""
        self.detener()
        if self._dll is not None:
            try:
                self._dll.espeak_Terminate()
            except Exception as error:
                log.debug("Al cerrar eSpeak: %s", error)
            self._dll = None


def _envolver_en_wav(pcm: bytes, muestreo: int) -> bytes:
    """Le pone a los datos crudos la cabecera que espera un reproductor.

    eSpeak devuelve muestras a secas —mono, dieciséis bits— y BASS quiere un
    archivo.  La cabecera de un WAV son cuarenta y cuatro bytes y escribirlos
    aquí evita pasar por un archivo temporal en cada frase.
    """
    import struct

    canales, bits = 1, 16
    alineacion = canales * bits // 8
    return (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt "
            + struct.pack("<IHHIIHH", 16, 1, canales, muestreo,
                          muestreo * alineacion, alineacion, bits)
            + b"data" + struct.pack("<I", len(pcm)) + pcm)


def crear(carpeta, ajustes):
    """Lo que el visor llama para poner esta voz. Es la única entrada."""
    return MotorEspeakMbrola(Path(carpeta), dict(ajustes or {}))
