# -*- coding: utf-8 -*-
"""Voces Piper para el Visor Universal.

Piper genera la voz con una red neuronal **dentro del equipo**: sin conexión,
sin tarjeta gráfica y sin que una sola línea de lo que leas salga de aquí. Suena
a persona leyendo, no a sintetizador, y va más rápido de lo que se oye: medido
con la voz que viene dentro, tres segundos de audio en trece centésimas.

Nueve voces en español —cinco de España, dos de México y una de Argentina—, y
ciento setenta y seis en más de treinta idiomas. En el paquete va una; las demás
se bajan desde aquí cuando se piden.

Cómo funciona por dentro
------------------------

Piper es un programa aparte, no una biblioteca. Se le levanta una vez y **se
queda esperando**: se le manda una línea de JSON con la frase y dónde dejar el
sonido, y contesta con la ruta cuando lo tiene. El proceso vive mientras dure la
voz elegida.

Eso es lo que hace que sirva para un libro. El modelo de una voz son sesenta
megas: cargarlo en cada frase costaría medio segundo por frase, y un capítulo
son cientos. Cargado una vez, cada frase cuesta centésimas.

Cambiar de voz o de velocidad sí obliga a levantarlo otra vez, porque las dos
cosas van en la línea de órdenes. Se hace en la frase siguiente y cuesta medio
segundo, una vez.

Por qué el programa y no la biblioteca de Python
------------------------------------------------

Por dos razones, y la segunda pesa más que la primera. La biblioteca `piper-tts`
necesita `onnxruntime`, y de eso no hay versión para el Python que usa el visor.
Y aunque la hubiera: un paquete atado a una versión de Python deja de funcionar
en cuanto el visor sube de versión, y este motor no tiene por qué enterarse de
eso nunca.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import threading
from pathlib import Path

log = logging.getLogger("visor.motor.piper")

_AQUI = Path(__file__).resolve().parent
if str(_AQUI) not in sys.path:
    sys.path.insert(0, str(_AQUI))

#: Para que el programa no abra una ventana de consola al arrancar.  Sin esto,
#: cada cambio de voz haría parpadear una ventana negra sobre el libro.
SIN_VENTANA = 0x08000000

#: Cuánto se estira o se encoge una frase, de la velocidad más lenta a la más
#: rápida.  Piper lo llama «length_scale» y va al revés que la intuición: más
#: número, más largo, o sea más lento.
LARGO_LENTO = 1.6
LARGO_NORMAL = 1.0
LARGO_RAPIDO = 0.5

#: De dónde se bajan las voces que no están.
DESCARGA = "https://huggingface.co/rhasspy/piper-voices/resolve/main/%s"

#: Cuánto se espera a que una voz se baje.  Son entre veinte y ciento diez
#: megas: con una conexión mala tarda de verdad.
ESPERA_DESCARGA = 600

#: Qué se enseña en la lista de voces.
SOLO_INSTALADAS = "instaladas"
TODAS_EN_ESPANOL = "espanol"
TODOS_LOS_IDIOMAS = "todos"

#: Cómo se llama cada calidad, para que la lista se entienda.
CALIDADES = {"x_low": "muy baja", "low": "baja", "medium": "media",
             "high": "alta"}

#: Los cincuenta países del catálogo, en español.  El catálogo los trae en
#: inglés, y una lista de voces que dice «Español, Spain» está a medio traducir,
#: que es peor que estar entera en un idioma o en el otro.
PAISES = {
    "Albania": "Albania", "Argentina": "Argentina", "Armenia": "Armenia",
    "Bangladesh": "Bangladés", "Belgium": "Bélgica", "Brazil": "Brasil",
    "Bulgaria": "Bulgaria", "China": "China", "Czech Republic": "Chequia",
    "Democratic Republic of the Congo": "República Democrática del Congo",
    "Denmark": "Dinamarca", "Estonia": "Estonia", "Finland": "Finlandia",
    "France": "Francia", "Georgia": "Georgia", "Germany": "Alemania",
    "Great Britain": "Reino Unido", "Greece": "Grecia", "Hungary": "Hungría",
    "Iceland": "Islandia", "India": "India", "Indonesia": "Indonesia",
    "Iran": "Irán", "Israel": "Israel", "Italy": "Italia", "Japan": "Japón",
    "Jordan": "Jordania", "Kazakhstan": "Kazajistán", "Latvia": "Letonia",
    "Luxembourg": "Luxemburgo", "Mexico": "México", "Nepal": "Nepal",
    "Netherlands": "Países Bajos", "Norway": "Noruega", "Pakistan": "Pakistán",
    "Poland": "Polonia", "Portugal": "Portugal", "Romania": "Rumanía",
    "Russia": "Rusia", "Serbia": "Serbia", "Slovakia": "Eslovaquia",
    "Slovenia": "Eslovenia", "South Korea": "Corea del Sur", "Spain": "España",
    "Sweden": "Suecia", "Thailand": "Tailandia", "Turkey": "Turquía",
    "Ukraine": "Ucrania", "United States": "Estados Unidos",
    "Vietnam": "Vietnam",
}


class MotorPiper:
    """Piper con la cara que el visor sabe manejar."""

    def __init__(self, carpeta: Path, ajustes: dict) -> None:
        self._carpeta = Path(carpeta)
        self._ajustes = dict(ajustes)
        self._catalogo: dict = {}
        self._voces: list = []
        self._voz = ""
        self._proceso = None
        self._largo = LARGO_NORMAL
        self._volumen = 100
        self._cerrojo = threading.RLock()
        self._canal = 0
        self._pausado = False
        self._bass = False
        self._numero = 0
        self._arrancar()

    # -- arranque ------------------------------------------------------------

    @property
    def _programa(self) -> Path:
        return self._carpeta / "piper.exe"

    @property
    def _carpeta_de_voces(self) -> Path:
        return self._carpeta / "voces"

    @property
    def _temporal(self) -> Path:
        """Donde Piper deja el sonido de cada frase.

        Dentro de la carpeta del propio motor y no en la del sistema: el
        programa es portable y se lleva en un lápiz de memoria, y así no deja
        nada suelto en el equipo de nadie.
        """
        donde = self._carpeta / "temporal"
        donde.mkdir(parents=True, exist_ok=True)
        return donde

    def _arrancar(self) -> None:
        """Lee el catálogo y prepara la lista de voces."""
        if not self._programa.is_file():
            log.warning("No está el programa de Piper en %s", self._programa)
            return
        ficha = self._carpeta_de_voces / "catalogo.json"
        try:
            self._catalogo = json.loads(ficha.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            log.warning("No se ha podido leer el catálogo de voces: %s", error)
            self._catalogo = {}
        self._voces = self._listar_voces()
        log.info("Piper con %d voces (%d instaladas de %d en el catálogo)",
                 len(self._voces), len(self._instaladas()), len(self._catalogo))
        guardada = str(self._ajustes.get("_voz_elegida", ""))
        if guardada:
            self.elegir_voz(guardada)
        else:
            self._elegir_la_primera_que_este()

    def _instaladas(self) -> set:
        """Las voces cuyo modelo está en el equipo."""
        if not self._carpeta_de_voces.is_dir():
            return set()
        return {uno.name[:-len(".onnx")]
                for uno in self._carpeta_de_voces.glob("*.onnx")}

    def _listar_voces(self) -> list:
        """Las voces que se ofrecen: ``(clave, nombre, idioma)``.

        Cuáles se ofrecen lo decide el ajuste. De fábrica, solo las que están
        instaladas: una lista con ciento setenta y seis nombres de los que
        funciona uno es una lista que engaña.
        """
        cuales = str(self._ajustes.get("que_voces", SOLO_INSTALADAS))
        instaladas = self._instaladas()
        salida = []
        for clave, ficha in self._catalogo.items():
            idioma = ficha.get("language", {})
            familia = idioma.get("family", "")
            if cuales == SOLO_INSTALADAS and clave not in instaladas:
                continue
            if cuales == TODAS_EN_ESPANOL and familia != "es" \
                    and clave not in instaladas:
                continue
            salida.append((clave, self._nombre_de(clave, ficha),
                           str(idioma.get("code", "")).replace("_", "-")))
        # Las instaladas primero: son las que se pueden usar ahora mismo.
        salida.sort(key=lambda uno: (uno[0] not in instaladas, uno[1].lower()))
        return _sin_nombres_repetidos(salida)

    @staticmethod
    def _nombre_de(clave: str, ficha: dict) -> str:
        """Cómo se lee una voz en la lista.

        La clave del catálogo —``es_ES-davefx-medium``— dice todo lo que hay que
        saber pero no se lee bien de oído. Aquí sale «davefx (España, calidad
        media)», que es lo mismo dicho en voz alta.
        """
        idioma = ficha.get("language", {})
        crudo = idioma.get("country_english") or ""
        pais = PAISES.get(crudo, crudo) or idioma.get("region") or ""
        lengua = idioma.get("name_native") or idioma.get("name_english") or ""
        calidad = CALIDADES.get(ficha.get("quality", ""), ficha.get("quality", ""))
        donde = ", ".join(uno for uno in (lengua, pais) if uno)
        return "%s (%s, calidad %s)" % (ficha.get("name", clave), donde, calidad)

    def _elegir_la_primera_que_este(self) -> None:
        """Pone la primera voz que ya esté en el equipo.

        La primera de la lista a secas no vale: con el catálogo entero abierto,
        arrancar el motor se pondría a bajar sesenta megas que nadie ha pedido.
        Solo se baja lo que alguien elige.
        """
        instaladas = self._instaladas()
        for clave, _nombre, _idioma in self._voces:
            if clave in instaladas:
                self._poner_voz(clave)
                return

    # -- qué voces hay -------------------------------------------------------

    @property
    def disponible(self) -> bool:
        return self._programa.is_file() and bool(self._voces)

    def voces(self) -> list:
        return [nombre for _clave, nombre, _idioma in self._voces]

    def elegir_voz(self, nombre: str) -> bool:
        for clave, cual, _idioma in self._voces:
            if cual == nombre:
                return self._poner_voz(clave)
        return False

    def _poner_voz(self, clave: str) -> bool:
        """Deja puesta una voz, bajándola antes si hace falta."""
        if clave not in self._instaladas() and not self._bajar(clave):
            return False
        if clave != self._voz:
            self._soltar_proceso()
            self._voz = clave
        return True

    def _bajar(self, clave: str) -> bool:
        """Trae de internet el modelo de una voz que no está.

        Se baja a un archivo aparte y se renombra al final. Cortar a la mitad
        dejaría un modelo incompleto, y Piper con un modelo roto no dice que
        esté roto: se cierra sin hablar.
        """
        import urllib.request

        ficha = self._catalogo.get(clave)
        if not ficha:
            return False
        log.info("Bajando la voz «%s»...", clave)
        destino = self._carpeta_de_voces
        destino.mkdir(parents=True, exist_ok=True)
        traidos = []
        try:
            for relativa in ficha.get("files", []):
                nombre = relativa.rsplit("/", 1)[-1]
                if not nombre.startswith(clave):
                    continue
                medias = destino / (nombre + ".bajando")
                with urllib.request.urlopen(DESCARGA % relativa,
                                            timeout=ESPERA_DESCARGA) as respuesta:
                    medias.write_bytes(respuesta.read())
                if medias.stat().st_size <= 0:
                    raise OSError("ha llegado vacío: %s" % nombre)
                traidos.append((medias, destino / nombre))
        except Exception as error:
            log.warning("No se ha podido bajar la voz «%s»: %s", clave, error)
            for medias, _fin in traidos:
                try:
                    medias.unlink(missing_ok=True)
                except OSError:
                    pass
            return False
        # Se renombran todos al final: hasta que no está el modelo **y** su
        # configuración, la voz no existe.
        for medias, fin in traidos:
            medias.replace(fin)
        log.info("Voz «%s» lista", clave)
        return True

    def voz_actual(self) -> str:
        for clave, nombre, _idioma in self._voces:
            if clave == self._voz:
                return nombre
        return ""

    def voces_con_idioma(self) -> list:
        return [(nombre, idioma) for _clave, nombre, idioma in self._voces]

    def voz_para_idioma(self, codigo: str) -> str:
        """La voz que mejor lee ese idioma, de las que **están**.

        Solo se miran las instaladas, y a propósito: cambiar de voz al vuelo en
        mitad de un libro es para leer una cita en otro idioma, y pararse a
        bajar sesenta megas en ese momento no es lo que nadie espera. Vale más
        leerla con acento.
        """
        if not codigo:
            return ""
        instaladas = self._instaladas()
        pedido = codigo.replace("_", "-").lower()
        lengua = pedido.split("-")[0]
        aproximada = ""
        for clave, nombre, idioma in self._voces:
            if clave not in instaladas:
                continue
            suyo = (idioma or "").lower()
            if suyo == pedido:
                return nombre
            if suyo.split("-")[0] == lengua and not aproximada:
                aproximada = nombre
        return aproximada

    # -- lo que se puede tocar -----------------------------------------------

    def establecer_velocidad(self, valor: int) -> None:
        """La velocidad, que en Piper es cuánto se estira cada frase.

        Va en la línea de órdenes, así que cambiarla obliga a levantar el
        programa otra vez. No se hace aquí: se suelta el que hay y el siguiente
        arranca ya con la velocidad nueva, en la primera frase que se lea. Así
        mover el deslizador de punta a punta no levanta veinte procesos.
        """
        acotado = max(-10, min(10, int(valor)))
        if acotado < 0:
            largo = LARGO_NORMAL + (LARGO_LENTO - LARGO_NORMAL) * (-acotado / 10.0)
        else:
            largo = LARGO_NORMAL - (LARGO_NORMAL - LARGO_RAPIDO) * (acotado / 10.0)
        if abs(largo - self._largo) > 0.001:
            self._largo = largo
            self._soltar_proceso()

    def establecer_volumen(self, valor: int) -> None:
        """El volumen.

        Piper no lo tiene: saca el sonido como lo generó. Se pone al
        reproducirlo, que es donde de verdad está el mando del volumen.
        """
        self._volumen = max(0, min(100, int(valor)))
        if self._canal:
            self._poner_volumen(self._canal)

    @property
    def espera_maxima(self) -> float:
        """Cuánto puede tardar en empezar a sonar.

        Una frase son centésimas con el programa ya levantado. Lo que tarda es
        levantarlo: medio segundo la primera vez, y otro medio cada vez que se
        cambia de voz o de velocidad. Ocho segundos dan de sobra y dejan sitio
        para un equipo lento.
        """
        try:
            return float(self._ajustes.get("espera_maxima", 8))
        except (TypeError, ValueError):
            return 8.0

    # -- el programa ---------------------------------------------------------

    def _numero_ajuste(self, clave: str, defecto: float, escala: float) -> float:
        """Un ajuste del 0 al 100 llevado a la escala que usa Piper."""
        try:
            return round(float(self._ajustes.get(clave, defecto)) * escala, 4)
        except (TypeError, ValueError):
            return round(defecto * escala, 4)

    def _levantar(self):
        """Levanta Piper con la voz y la velocidad de ahora, si no está ya."""
        if self._proceso is not None and self._proceso.poll() is None:
            return self._proceso
        if not self._voz:
            return None
        modelo = self._carpeta_de_voces / (self._voz + ".onnx")
        if not modelo.is_file():
            log.warning("Falta el modelo de la voz «%s»", self._voz)
            return None
        orden = [
            str(self._programa),
            "--model", str(modelo),
            "--espeak_data", str(self._carpeta / "espeak-ng-data"),
            "--json-input", "--quiet",
            "--length_scale", "%.4f" % self._largo,
            "--noise_scale", "%.4f" % self._numero_ajuste("variacion", 67, 0.01),
            "--noise_w", "%.4f" % self._numero_ajuste("variacion_fonemas", 80, 0.01),
            "--sentence_silence",
            "%.4f" % self._numero_ajuste("silencio_frases", 20, 0.01),
        ]
        try:
            self._proceso = subprocess.Popen(
                orden, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, creationflags=SIN_VENTANA)
        except Exception as error:
            log.error("No se ha podido levantar Piper: %s", error)
            self._proceso = None
        return self._proceso

    def _soltar_proceso(self) -> None:
        """Cierra el programa, si estaba levantado."""
        proceso, self._proceso = self._proceso, None
        if proceso is None:
            return
        try:
            if proceso.stdin:
                proceso.stdin.close()
            proceso.terminate()
            proceso.wait(timeout=3)
        except Exception as error:
            log.debug("Al cerrar Piper: %s", error)
            try:
                proceso.kill()
            except Exception:
                pass

    # -- hablar --------------------------------------------------------------

    def decir(self, texto: str, con_marcas: bool = False) -> bool:
        """Genera la frase y la reproduce.

        ``con_marcas`` se ignora: son marcas de SAPI y Piper no entiende
        ninguna. Lee lo que se le da, tal cual.
        """
        if not texto:
            return False
        self.detener()
        with self._cerrojo:
            proceso = self._levantar()
            if proceso is None:
                return False
            # Una frase por línea, y Piper no entiende que una frase tenga
            # saltos de línea dentro: cada uno sería una frase suya.
            limpio = " ".join(texto.split())
            self._numero += 1
            salida = self._temporal / ("frase_%d.wav" % (self._numero % 8))
            orden = json.dumps({"text": limpio, "output_file": str(salida)},
                               ensure_ascii=False)
            try:
                proceso.stdin.write((orden + "\n").encode("utf-8"))
                proceso.stdin.flush()
                # Piper contesta con la ruta cuando el archivo está entero.  Es
                # lo que hace innecesario adivinar cuándo ha terminado.
                if not proceso.stdout.readline():
                    raise OSError("Piper se ha cerrado")
            except Exception as error:
                log.error("Piper no ha podido hablar: %s", error)
                self._soltar_proceso()
                return False
            if not salida.is_file() or salida.stat().st_size <= 44:
                return False
            return self._reproducir(salida.read_bytes())

    def _reproducir(self, onda: bytes) -> bool:
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
        import ctypes

        self._memoria = ctypes.create_string_buffer(onda)
        canal = bass.BASS_StreamCreateFile(True, self._memoria, 0, len(onda),
                                           BASS_STREAM_PRESCAN)
        if not canal:
            log.error("BASS no ha podido abrir el sonido de Piper")
            return False
        self._canal = canal
        self._pausado = False
        self._poner_volumen(canal)
        return bool(bass.BASS_ChannelPlay(canal, True))

    def _poner_volumen(self, canal: int) -> None:
        try:
            from basskit.dlls.bass import bass

            # El 2 es el volumen del canal en BASS, de 0 a 1.
            bass.BASS_ChannelSetAttribute(canal, 2, self._volumen / 100.0)
        except Exception as error:
            log.debug("No se ha podido poner el volumen: %s", error)

    @staticmethod
    def con_tono(texto: str, tono: int) -> str:
        """El texto tal cual: Piper no entiende marcas de ninguna clase."""
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
                log.debug("Al detener Piper: %s", error)
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
        """Suelta el sonido, cierra el programa y recoge lo que dejó escrito."""
        self.detener()
        self._soltar_proceso()
        try:
            for uno in self._temporal.glob("frase_*.wav"):
                uno.unlink(missing_ok=True)
        except OSError as error:
            log.debug("Al recoger los temporales de Piper: %s", error)


def _sin_nombres_repetidos(voces: list) -> list:
    """Le añade la clave a los nombres que salgan repetidos.

    Las voces se eligen **por su nombre**, así que dos con el mismo nombre serían
    una sola: la segunda no se podría poner nunca. Pasa cuando dos personas
    distintas grabaron con el mismo alias, el mismo país y la misma calidad.
    """
    cuantas: dict = {}
    for _clave, nombre, _idioma in voces:
        cuantas[nombre] = cuantas.get(nombre, 0) + 1
    return [(clave, nombre if cuantas[nombre] == 1 else "%s [%s]" % (nombre, clave),
             idioma) for clave, nombre, idioma in voces]


def crear(carpeta, ajustes):
    """Lo que el visor llama para poner esta voz. Es la única entrada."""
    return MotorPiper(Path(carpeta), dict(ajustes or {}))
