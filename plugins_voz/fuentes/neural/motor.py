# -*- coding: utf-8 -*-
"""Voces neuronales de Microsoft, sin conexión, para el Visor Universal.

Son las voces neuronales de Azure funcionando **dentro del equipo**: el modo
«embebido» de la biblioteca de voz de Microsoft. Las mismas que se oyen en sus
servicios en línea, pero sin que salga nada de aquí y sin necesitar internet.

En español de España vienen Abril, Álvaro, Arnau, Elvira y Jenny; en catalán,
Enric y Joana. Y se le pueden añadir todas las que se quieran, de cualquier
idioma: cada voz trae su código de idioma dentro, así que al copiarla aparece
sola y el visor ya sabe para qué lengua sirve.

Las voces van fuera
-------------------

Cada voz ocupa unos veinticinco megas, así que el paquete trae **el motor y
nada más**. Las voces se dejan en la carpeta ``voces`` y **se detectan solas**:
se busca dentro de ella cualquier carpeta que tenga un ``data``, así que da
igual cómo se organicen —sueltas, o agrupadas por idioma como vienen—.

Hace falta una clave
--------------------

Los modelos de voz vienen cifrados y Microsoft entrega la clave con la licencia.
El motor la busca en su carpeta ``licencia``, en un archivo ``SynthModel.key``
—o ``SynthModel.license`` si las voces no están cifradas—, que es exactamente
donde y como la busca el controlador de NVDA del que sale este motor.

Sin ella, las voces **se ven** —salen sus nombres y sus idiomas— pero no suenan:
la biblioteca falla al abrir el modelo. Por eso, si falta, el motor lo dice al
arrancar en vez de dejar que se descubra en mitad de un libro.

Cómo suena
----------

La biblioteca **devuelve el sonido** en trozos, a 24 kHz, y lo reproduce BASS,
que el visor ya lleva para los libros DAISY. Como en los demás motores, eso es
lo que permite pausar en mitad de un párrafo y seguir donde se dejó.
"""

from __future__ import annotations

import ctypes
import gc
import logging
import os
import queue
import sys
import threading
from pathlib import Path
from xml.sax.saxutils import escape

log = logging.getLogger("visor.motor.neural")

_AQUI = Path(__file__).resolve().parent
if str(_AQUI) not in sys.path:
    sys.path.insert(0, str(_AQUI))

#: Cómo se llama el archivo con la clave de las voces, y el de la licencia de
#: las que no van cifradas.  Son los nombres que usa el controlador de NVDA del
#: que sale este motor, para que valga el mismo archivo sin renombrar nada.
CLAVE = "SynthModel.key"
LICENCIA = "SynthModel.license"

#: A cuántos hercios devuelve el sonido.  Es el formato que se le pide, y el
#: mismo número hace falta después para reproducirlo bien.
FRECUENCIAS = {24000: "Raw24Khz16BitMonoPcm",
               16000: "Raw16Khz16BitMonoPcm",
               8000: "Raw8Khz16BitMonoPcm"}

#: Los límites de la biblioteca para lo que se puede ajustar de una voz.  La
#: velocidad llega mucho más arriba que abajo a propósito: es de las pocas voces
#: neuronales que aguantan el triple sin deshacerse.
VELOCIDAD_MINIMA, VELOCIDAD_MAXIMA = -100, 200
TONO_MINIMO, TONO_MAXIMO = -100, 100
VOLUMEN_MINIMO, VOLUMEN_MAXIMO = -100, 100


def _desde_por_ciento(porcentaje: int, minimo: int, maximo: int) -> int:
    """De la escala de 0 a 100 del visor a la que use la biblioteca."""
    acotado = max(0, min(100, int(porcentaje)))
    return int(round(minimo + acotado * (maximo - minimo) / 100.0))


class MotorNeural:
    """Las voces neuronales de Microsoft con la cara que el visor maneja."""

    def __init__(self, carpeta: Path, ajustes: dict) -> None:
        self._carpeta = Path(carpeta)
        self._ajustes = dict(ajustes)
        self._api = None
        #: Los sintetizadores levantados, con su configuración y su salida.  Se
        #: guardan los tres juntos porque la biblioteca conserva punteros a los
        #: dos últimos: si el recolector se los lleva, lee basura.
        self._sintetizadores: list = []
        self._sintetizador = None
        self._voces: list = []
        self._voz = ""
        self._trozos: list = []
        self._cerrojo = threading.RLock()
        #: Las frases pendientes, que atiende un hilo aparte.  La biblioteca no
        #: se puede llamar desde el hilo de la interfaz: en el programa
        #: compilado eso tumbaba la aplicación entera.
        self._cola = queue.Queue()
        self._hilo = None
        #: Sube cada vez que se manda callar.  Lo que estuviera generándose
        #: cuando subió ya no vale y se tira: si no, al pasar página se oiría
        #: la frase anterior encima de la nueva.
        self._turno = 0
        #: Si hay una frase generándose ahora mismo.  Cuenta como «hablando»,
        #: porque si no el visor daría la frase por terminada antes de oírla.
        self._preparando = False
        #: Si ya ha hablado alguna vez desde que arrancó.  Solo sirve para que
        #: la primera frase deje más rastro en el registro que las demás.
        self._ha_hablado = False
        self._canal = 0
        self._pausado = False
        self._bass = False
        self._volumen = 100
        self._velocidad = 50
        self._fallo = ""
        self._arrancar()

    # -- arranque ------------------------------------------------------------

    @property
    def _carpeta_de_voces(self) -> Path:
        donde = self._carpeta / "voces"
        donde.mkdir(parents=True, exist_ok=True)
        return donde

    @property
    def _carpeta_de_licencia(self) -> Path:
        donde = self._carpeta / "licencia"
        donde.mkdir(parents=True, exist_ok=True)
        return donde

    def _leer_la_clave(self, junto_a: Path | None = None) -> str:
        """La clave con la que se descifran los modelos de una voz.

        Se busca en tres sitios, en este orden:

        1. Lo escrito a mano en los ajustes, para quien la tenga apuntada.
        2. **Junto a la propia voz**, que es donde la pone quien las reparte:
           cada voz viene con la suya.
        3. La carpeta ``licencia`` del motor, para quien tenga una sola que
           valga para todas.

        Y de los dos nombres, primero la clave y después la licencia: una voz
        cifrada necesita la clave, y la licencia solo vale para las que no lo
        están.  Se distinguen además al usarlas: una clave se pasa con ``Key:``
        delante, y sin eso una clave correcta se rechaza.
        """
        escrita = str(self._ajustes.get("clave", "") or "").strip()
        if escrita:
            return escrita
        donde = []
        if junto_a is not None:
            donde.append(junto_a)
        donde.append(self._carpeta_de_licencia)
        for carpeta in donde:
            for nombre in (CLAVE, LICENCIA):
                archivo = carpeta / nombre
                if not archivo.is_file():
                    continue
                try:
                    contenido = archivo.read_text(encoding="utf-8").strip()
                except OSError as error:
                    log.warning("No se ha podido leer %s: %s", archivo, error)
                    continue
                # Una clave lleva «Key:» delante; una licencia va tal cual.
                return ("Key:" + contenido if nombre == CLAVE else contenido)
        return ""

    def _carpetas_de_voz(self) -> list:
        """Todas las carpetas de voz que haya, se organicen como se organicen.

        Una voz se reconoce por su ``Tokens.xml``, que es lo que la biblioteca
        busca de verdad; una carpeta llamada ``data`` puede ser cualquier cosa.
        Se devuelve la carpeta que lo contiene y, con ella, dónde buscar su
        licencia: la raíz de la voz, que es la que tiene el ``data`` dentro.

        Da igual cómo estén organizadas las voces —sueltas, o agrupadas por
        idioma como vienen—: se busca hasta el fondo.
        """
        rutas = []
        donde = [self._carpeta_de_voces]
        extra = str(self._ajustes.get("carpeta_extra", "") or "").strip()
        if extra:
            fuera = Path(extra)
            if fuera.is_dir():
                donde.append(fuera)
            else:
                log.warning("La carpeta de voces «%s» no existe", extra)
        vistas = set()
        for raiz in donde:
            for ficha in sorted(raiz.rglob("Tokens.xml")):
                datos = ficha.parent
                if str(datos) in vistas:
                    continue
                vistas.add(str(datos))
                # La raíz de la voz es la que contiene el «data»: subiendo desde
                # el «Tokens.xml», es la abuela.
                suya = datos.parent.parent if datos.parent.name == "data" \
                    else datos.parent
                rutas.append((str(datos), suya))
        return rutas

    def _arrancar(self) -> None:
        """Carga la biblioteca, le dice dónde mirar y pregunta qué voces hay."""
        aqui = self._carpeta / "speechapi"
        if not (aqui / "Microsoft.CognitiveServices.Speech.core.dll").is_file():
            self._fallo = "no está la biblioteca de voz"
            log.warning("No está la biblioteca en %s", aqui)
            return
        try:
            # Las bibliotecas se llaman entre ellas por su nombre, así que su
            # carpeta tiene que estar donde Windows las busque.
            os.add_dll_directory(str(aqui))
            if str(self._carpeta) not in sys.path:
                sys.path.insert(0, str(self._carpeta))
            import speechapi
        except Exception as error:
            self._fallo = str(error)
            log.warning("No se ha podido cargar la biblioteca de voz: %s", error)
            return

        # ¿Es esta biblioteca la de esta instalación?  Si el motor se ha vuelto
        # a instalar con el programa abierto, la de antes sigue cargada desde
        # una carpeta que ya no se llama así, y pedirle una frase tumba el
        # proceso entero.  Aquí se ve y se para a tiempo.
        cargada = Path(getattr(speechapi, "__file__", "") or "").parent
        if cargada and not _misma_carpeta(cargada, aqui):
            self._fallo = ("el motor se ha vuelto a instalar: cierra el "
                           "programa y ábrelo otra vez para usar estas voces")
            log.warning("La biblioteca cargada es la de %s y esta instalación "
                        "está en %s. Hay que reiniciar el programa.",
                        cargada, aqui)
            return
        self._api = speechapi

        encontradas = self._carpetas_de_voz()
        if not encontradas:
            self._fallo = "no hay ninguna voz"
            log.warning("No hay ninguna voz en %s", self._carpeta_de_voces)
            return

        # Cada voz con la clave que le corresponda: normalmente cada una viene
        # con la suya, junto a ella.  Las que comparten clave se agrupan, que es
        # lo que evita levantar la biblioteca una vez por voz.
        por_clave: dict = {}
        sin_clave = []
        for datos, suya in encontradas:
            clave = self._leer_la_clave(suya)
            if clave:
                por_clave.setdefault(clave, []).append(datos)
            else:
                sin_clave.append(Path(datos).name)
        if sin_clave:
            log.warning("Sin clave para %d voces (%s). Ponla junto a cada voz "
                        "o en %s", len(sin_clave), ", ".join(sin_clave[:3]),
                        self._carpeta_de_licencia)
            self._fallo = ("falta la clave de las voces: ponla junto a cada voz "
                           "o en %s" % self._carpeta_de_licencia)
        if not por_clave:
            # Sin ninguna clave se levanta igual, para poder ver qué voces hay
            # instaladas.  Lo que no van a hacer es sonar, y eso ya está dicho.
            por_clave[""] = [datos for datos, _suya in encontradas]

        self._sintetizadores = []
        self._voces = []
        for clave, rutas in por_clave.items():
            try:
                config = speechapi.EmbeddedSpeechConfig(rutas)
                if clave:
                    config.set_property(
                        speechapi.lib.SpeechServiceConnection_SynthModelKey, clave)
                config.set_audio_output_format(self._formato())
                salida = speechapi.StreamAudioConfig(self._recoger)
                uno = speechapi.SpeechSynthesizer(config, salida)
            except Exception as error:
                self._fallo = str(error)
                log.warning("La biblioteca de voz no ha arrancado: %s", error)
                continue
            # Se guardan los tres juntos: la biblioteca se queda con punteros a
            # la salida y a la configuración, y si el recolector se los lleva
            # antes de tiempo, lo que lee después es basura.
            self._sintetizadores.append((uno, config, salida))
            for voz in uno.voices:
                self._voces.append((voz.name, voz.locale, uno))
        if not self._sintetizadores:
            return
        self._sintetizador = self._sintetizadores[0][0]
        log.info("Voces neuronales: %d encontradas en %d carpetas",
                 len(self._voces), len(encontradas))
        guardada = str(self._ajustes.get("_voz_elegida", ""))
        nombres = [self._nombre_corto(uno[0]) for uno in self._voces]
        if guardada in nombres:
            self._voz = self._voces[nombres.index(guardada)][0]
        elif self._voces:
            self._voz = self._voces[0][0]

    def _formato(self):
        """El identificador del formato de sonido que se le pide."""
        hercios = self._entero("frecuencia", 24000)
        nombre = FRECUENCIAS.get(hercios, FRECUENCIAS[24000])
        return getattr(self._api.lib, "SpeechSynthesisOutputFormat_" + nombre)

    @property
    def _muestreo(self) -> int:
        hercios = self._entero("frecuencia", 24000)
        return hercios if hercios in FRECUENCIAS else 24000

    # -- qué voces hay -------------------------------------------------------

    @staticmethod
    def _nombre_corto(largo: str) -> str:
        """El nombre de una voz, sin la retahíla de delante.

        La biblioteca las llama «Microsoft Server Speech Text to Speech Voice
        (es-ES, ElviraNeural)», que dicho en voz alta son ocho palabras antes de
        llegar a lo único que distingue una voz de otra.  Aquí se lee «Elvira
        (es-ES)».
        """
        dentro = largo
        if "(" in largo and largo.endswith(")"):
            dentro = largo[largo.rindex("(") + 1:-1]
        partes = [uno.strip() for uno in dentro.split(",")]
        if len(partes) == 2:
            idioma, nombre = partes
            if nombre.endswith("Neural"):
                nombre = nombre[:-len("Neural")]
            return "%s (%s)" % (nombre, idioma)
        return largo

    @property
    def disponible(self) -> bool:
        return self._sintetizador is not None and bool(self._voces)

    def problema(self) -> str:
        """Por qué no va a sonar, si es que no va a sonar.

        Lo normal es que falte la clave: las voces se ven en la lista y los
        modelos no se pueden abrir.  Callárselo hace que probar la voz no haga
        nada y que no haya forma de saber qué falta.
        """
        return self._fallo or ""

    def voces(self) -> list:
        return [self._nombre_corto(uno[0]) for uno in self._voces]

    def voces_con_idioma(self) -> list:
        """Cada voz con su idioma, que estas lo traen dentro y bien puesto.

        Es lo que hace que al añadir una voz de otro idioma el visor la use sola
        para las citas en esa lengua, sin configurar nada.
        """
        return [(self._nombre_corto(cual), idioma)
                for cual, idioma, _suyo in self._voces]

    def voz_actual(self) -> str:
        return self._nombre_corto(self._voz) if self._voz else ""

    def elegir_voz(self, nombre: str) -> bool:
        for cual, _idioma, suyo in self._voces:
            if self._nombre_corto(cual) == nombre:
                self._voz = cual
                # Con quién se habla esta voz: puede no ser el mismo de antes si
                # cada una vino con su propia clave.
                self._sintetizador = suyo
                return True
        return False

    def voz_para_idioma(self, codigo: str) -> str:
        """La voz que mejor lee ese idioma.

        Se prefiere la del país exacto y, si no la hay, cualquiera de la misma
        lengua: oír una frase inglesa con voz inglesa de otro país es mucho
        mejor que oírla con voz española.
        """
        if not codigo:
            return ""
        pedido = codigo.replace("_", "-").lower()
        lengua = pedido.split("-")[0]
        aproximada = ""
        for cual, idioma, _quien in self._voces:
            suyo = (idioma or "").replace("_", "-").lower()
            if not suyo:
                continue
            if suyo == pedido:
                return self._nombre_corto(cual)
            if suyo.split("-")[0] == lengua and not aproximada:
                aproximada = self._nombre_corto(cual)
        return aproximada

    def opciones_de(self, clave: str):
        """Las frecuencias que la biblioteca admite de verdad.

        Las voces no se remuestrean: la biblioteca entrega a la que se le pida,
        y estas tres son las que sabe dar.  Del resto de ajustes manda el
        manifiesto.
        """
        if clave == "frecuencia":
            return [(hercios, _("%d kHz") % round(hercios / 1000))
                    for hercios in sorted(FRECUENCIAS, reverse=True)]
        return None

    # -- lo que se puede tocar -----------------------------------------------

    def _entero(self, clave: str, defecto: int) -> int:
        try:
            return int(self._ajustes.get(clave, defecto))
        except (TypeError, ValueError):
            return defecto

    def establecer_velocidad(self, valor: int) -> None:
        """La velocidad, de la escala del visor a la de la biblioteca.

        Se guarda y se aplica al hablar, dentro del propio texto: aquí no hay un
        parámetro que poner, la velocidad va escrita en cada petición.
        """
        self._velocidad = max(0, min(100, 50 + int(valor) * 5))

    def establecer_volumen(self, valor: int) -> None:
        self._volumen = max(0, min(100, int(valor)))

    @property
    def espera_maxima(self) -> float:
        """Cuánto puede tardar en empezar a sonar.

        Estas voces generan la frase entera antes de entregarla, y la primera
        con una voz recién elegida carga además su modelo.  Son unos segundos la
        primera vez y décimas después.
        """
        try:
            return float(self._ajustes.get("espera_maxima", 10))
        except (TypeError, ValueError):
            return 10.0

    # -- hablar --------------------------------------------------------------

    def _recoger(self, datos: bytes) -> None:
        """La biblioteca entrega el sonido por aquí, en trozos.

        Esto lo llama un hilo de la propia biblioteca, así que no puede fallar:
        una excepción que se escape por aquí no sube a Python, sale por una
        llamada de retorno nativa, y Windows mata el proceso entero.
        """
        try:
            if datos:
                self._trozos.append(datos)
        except Exception:
            pass

    def _asegurar_el_hilo(self) -> None:
        """Levanta el hilo que sintetiza, si no estaba ya."""
        if self._hilo is not None and self._hilo.is_alive():
            return
        self._hilo = threading.Thread(target=self._atender, daemon=True,
                                      name="voz neuronal")
        self._hilo.start()

    def _atender(self) -> None:
        """Va sacando frases de la cola y las dice, una detrás de otra.

        Todo lo que pase aquí dentro se queda aquí dentro: este hilo llama a la
        biblioteca nativa, y una excepción que suba sin capturar acaba
        atravesando código de Microsoft.  Por eso el ``except`` es de todo.
        """
        soltar_com = _apartamento_propio()
        try:
            self._ir_atendiendo()
        finally:
            if soltar_com:
                _soltar_el_apartamento()

    def _ir_atendiendo(self) -> None:
        """El bucle en sí, ya con el apartamento de COM puesto."""
        while True:
            tarea = self._cola.get()
            if tarea is None:
                return
            texto, turno = tarea
            try:
                self._decir_de_verdad(texto, turno)
            except Exception as error:
                log.error("La voz no ha podido hablar: %s", error)
                self._fallo = str(error)
            finally:
                if turno == self._turno:
                    self._preparando = False

    def _decir_de_verdad(self, texto: str, turno: int) -> None:
        """Genera la frase y la reproduce, ya en el hilo que toca."""
        # La primera de cada arranque se apunta entera: si el proceso se cayera
        # dentro de la biblioteca no habría excepción ni traza, y estas dos
        # líneas serían la única forma de saber dónde estaba.
        apuntar = log.debug if self._ha_hablado else log.info
        with self._cerrojo:
            if turno != self._turno:
                return                      # han mandado callar mientras tanto
            self._trozos = []
            apuntar("Generando con «%s» (%d caracteres)", self._voz, len(texto))
            razon = self._sintetizador.speak_ssml(self._pedir(texto))
            audio = b"".join(self._trozos)
            self._trozos = []
            self._ha_hablado = True
            apuntar("Generada: %d bytes de sonido", len(audio))
        if turno != self._turno:
            return
        if not audio:
            completo = getattr(self._api.lib,
                               "ResultReason_SynthesizingAudioComplete", None)
            if completo is not None and razon != completo:
                log.warning("La voz no ha dado sonido (razón %s). Si falta la "
                            "clave, los modelos no se pueden abrir.", razon)
            return
        # El orden importa: entre que se acaba de generar y BASS arranca hay
        # unas décimas en las que no hay canal todavía.  Bajar la bandera antes
        # de eso hace que «hablando» diga que no en mitad de la frase, y el
        # visor se salta la siguiente sin haber oído esta.
        self._reproducir(audio)
        self._preparando = False

    def _pedir(self, texto: str) -> str:
        """Escribe la petición tal como la quiere la biblioteca.

        Todo va en el propio texto —la voz, la velocidad, el tono, el volumen—
        porque es la única forma que tiene de recibirlo. El texto se escapa: un
        libro con un «<» dentro rompería la petición entera y no sonaría nada.
        """
        idioma = "es-ES"
        for cual, suyo, _quien in self._voces:
            if cual == self._voz:
                idioma = suyo or idioma
                break
        velocidad = _desde_por_ciento(self._velocidad, VELOCIDAD_MINIMA,
                                      VELOCIDAD_MAXIMA)
        tono = _desde_por_ciento(self._entero("tono", 50), TONO_MINIMO,
                                 TONO_MAXIMO)
        volumen = _desde_por_ciento(self._volumen, VOLUMEN_MINIMO,
                                    VOLUMEN_MAXIMO)
        estilo = str(self._ajustes.get("estilo", "") or "").strip()
        dentro = escape(texto)
        if estilo:
            # No todas las voces tienen estilos; la que no lo tenga lo ignora.
            grado = self._entero("fuerza_estilo", 100) / 100.0
            dentro = ('<mstts:express-as style="%s" styledegree="%.2f">%s'
                      '</mstts:express-as>' % (escape(estilo), grado, dentro))
        return (
            '<speak version="1.0" '
            'xmlns="http://www.w3.org/2001/10/synthesis" '
            'xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="%s">'
            '<voice name="%s">'
            '<prosody rate="%d%%" pitch="%d%%" volume="%d%%">%s</prosody>'
            '</voice></speak>'
            % (escape(idioma), escape(self._voz), velocidad, tono, volumen,
               dentro))

    def decir(self, texto: str, con_marcas: bool = False) -> bool:
        """Genera la frase entera y la reproduce.

        ``con_marcas`` se ignora: son marcas de SAPI. Esta biblioteca entiende
        las suyas, que no son las mismas, y colar unas por otras haría que
        leyera las etiquetas en voz alta.
        """
        if not texto or self._sintetizador is None:
            return False
        if self._fallo:
            # Se sabe de antemano que no va a sonar —falta la clave, no cargó la
            # biblioteca—.  Decirlo aquí es lo que hace que «Probar» avise en
            # vez de quedarse callado.
            return False
        self.detener()
        self._preparando = True
        self._asegurar_el_hilo()
        self._cola.put((texto, self._turno))
        return True

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
            log.error("BASS no ha podido abrir el sonido")
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
        # Al subir el turno, lo que se esté generando ahora deja de valer: el
        # hilo lo comprueba y lo tira en vez de ponerlo a sonar tarde.
        self._turno += 1
        self._preparando = False
        self._pausado = False
        try:
            while True:
                self._cola.get_nowait()
        except queue.Empty:
            pass
        if self._canal:
            try:
                from basskit.dlls.bass import bass

                bass.BASS_ChannelStop(self._canal)
                bass.BASS_StreamFree(self._canal)
            except Exception as error:
                log.debug("Al detener: %s", error)
            self._canal = 0

    @property
    def pausada(self) -> bool:
        return self._pausado

    @property
    def hablando(self) -> bool:
        """Si está sonando ahora mismo.

        Una pausa cuenta como «sigue»: si dijera que no, el visor daría la frase
        por terminada y se saltaría el resto en cuanto alguien pausara.  Y lo
        que se está generando también, porque entre que se pide una frase y
        empieza a sonar hay unas décimas en las que aún no hay canal: decir que
        no ahí haría que el visor pasara a la frase siguiente sin oír esta.
        """
        if self._pausado or self._preparando:
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
        """Suelta el sonido, despide al hilo y cierra la biblioteca."""
        self.detener()
        if self._hilo is not None and self._hilo.is_alive():
            self._cola.put(None)
            # Con espera: si el hilo se quedara dentro de la biblioteca, soltar
            # los sintetizadores mientras los está usando sería peor.
            self._hilo.join(timeout=10)
        self._hilo = None
        for uno, _config, _salida in self._sintetizadores:
            try:
                uno.stop_async()
            except Exception as error:
                log.debug("Al parar la voz: %s", error)

        # Y ahora el orden, que aquí no da igual.  La salida de sonido tiene
        # enganchada una llamada de retorno y la desengancha al destruirse; el
        # sintetizador es quien llama por ella.  Si el recolector se lleva la
        # salida primero, la biblioteca se queda apuntando a un contexto que ya
        # no existe y el proceso se cae —una violación de acceso dentro de una
        # llamada de retorno, que Windows no perdona—.  Así que se sueltan uno
        # a uno y en orden: primero quien llama, después lo llamado.
        sueltos = self._sintetizadores
        self._sintetizadores = []
        self._sintetizador = None
        for uno, config, salida in sueltos:
            del uno
            gc.collect()          # que se vaya ahora, no cuando toque
            del salida
            gc.collect()
            del config
        gc.collect()


def _(texto: str) -> str:
    """Los textos del motor, tal cual.

    El paquete se carga en marcha y fuera del programa, así que no tiene a mano
    su sistema de traducción; los rótulos que se generan aquí van en español,
    igual que los del manifiesto.
    """
    return texto


#: Apartamento multihilo de COM.  Es el que no necesita que nadie atienda una
#: cola de mensajes, y por eso es el que le sirve a un hilo de trabajo.
_MULTIHILO = 0x0

#: «Ya estabas en otro apartamento».  No es un fallo y no hay que deshacerlo.
_YA_ESTABA = -2147417850          # RPC_E_CHANGED_MODE


def _apartamento_propio() -> bool:
    """Mete el hilo de ahora en el apartamento multihilo de COM.

    Sin esto, las llamadas de COM que hace la biblioteca de voz no se pueden
    atender aquí y Windows se las lleva al hilo de la ventana, que es de
    apartamento único.  Llegan en mitad de un mensaje suyo, Windows las rechaza
    con ``RPC_E_CANTCALLOUT_ININPUTSYNCCALL``, y como todo esto pasa dentro de
    llamadas de retorno nativas, el proceso entero se cae sin dejar excepción.

    :return: Si hay que soltarlo al terminar.
    """
    try:
        import ctypes

        cual = ctypes.windll.ole32.CoInitializeEx(None, _MULTIHILO)
    except Exception as error:
        log.debug("No se ha podido entrar en un apartamento de COM: %s", error)
        return False
    if cual == _YA_ESTABA:
        # El hilo ya vivía en otro apartamento.  No es nuestro y no se suelta.
        log.debug("El hilo ya estaba en otro apartamento de COM")
        return False
    return True


def _soltar_el_apartamento() -> None:
    """Sale del apartamento de COM al acabar el hilo."""
    try:
        import ctypes

        ctypes.windll.ole32.CoUninitialize()
    except Exception as error:
        log.debug("Al salir del apartamento de COM: %s", error)


def _misma_carpeta(una: Path, otra: Path) -> bool:
    """Si dos rutas son la misma carpeta, mirando el disco y no el texto.

    Se compara lo que el sistema dice, no las cadenas: la misma carpeta puede
    escribirse de varias formas y aquí una confusión significaría negarse a
    hablar sin motivo.
    """
    try:
        return una.resolve() == otra.resolve()
    except OSError:
        # Si una de las dos ya no existe, desde luego no son la misma.
        return False


def _envolver_en_wav(pcm: bytes, muestreo: int) -> bytes:
    """Le pone a los datos crudos la cabecera que espera un reproductor.

    La biblioteca devuelve muestras a secas —mono, dieciséis bits— y BASS quiere
    un archivo. La cabecera de un WAV son cuarenta y cuatro bytes y escribirlos
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
    return MotorNeural(Path(carpeta), dict(ajustes or {}))
