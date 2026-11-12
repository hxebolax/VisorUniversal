# -*- coding: utf-8 -*-
"""Ollama propio: una inteligencia artificial local que se instala sola.

Tener IA en el propio ordenador es lo mejor que le puede pasar a este programa:
**no sale nada del equipo** —ni el libro, ni sus ilustraciones— y **no hay
cuota** que se agote a mitad de un documento.  El problema es montarla: buscar
un servidor, instalarlo, elegir un modelo, saber qué es un GGUF y qué puerto
usa cada cosa.  Eso deja fuera a casi todo el mundo, que es justo lo contrario
de lo que este programa pretende.

Este módulo se encarga de todo eso.  Descarga **Ollama portable** dentro de
``data``, lo arranca cuando hace falta, descarga los modelos que se elijan y lo
apaga al salir.  El usuario no instala nada en su sistema ni toca una consola.

Tres decisiones que evitan pisarle nada a nadie
-----------------------------------------------

* **Puerto propio.**  Ollama usa el 11434, y quien ya lo tenga instalado lo
  tiene ahí.  Este usa el **11436**, y comprueba que quien contesta en él es
  *su* ejecutable y no otro: nunca adopta un servidor ajeno solo porque
  responda, ni lo mata como efecto secundario.
* **Almacén propio.**  Los modelos van a ``data/ollama_modelos``, no al del
  sistema.  Así ni se mezclan con los del usuario ni se borran al desinstalar.
* **Todo dentro de ``data``.**  El programa sigue siendo portable: se copia la
  carpeta a una memoria USB y la inteligencia artificial se va con ella.

Y una que se nota al usarlo: **todo lo que tarda informa de cómo va**.
Descargar Ollama es más de un giga y un modelo puede ser seis; sin decir por
dónde va, eso es una ventana muda durante veinte minutos en la que no se sabe
si el programa trabaja o se ha colgado.

Solo biblioteca estándar, como el resto del paquete.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import unicodedata
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import NamedTuple

from ..idioma import _
from ..registro import obtener_registro
from .. import rutas

log = obtener_registro(__name__)

#: Dónde escucha nuestro servidor.  El 11434 es el de Ollama de toda la vida y
#: **no se toca**: quien lo tenga instalado sigue con el suyo intacto.
HOST = "127.0.0.1"
PUERTO = 11436
PUERTO_ESTANDAR = 11434

#: De dónde se saca la última versión publicada de Ollama.
API_VERSIONES = "https://api.github.com/repos/ollama/ollama/releases/latest"

#: El paquete de Windows, y el añadido para las gráficas AMD.
PAQUETE_WINDOWS = "ollama-windows-amd64.zip"
PAQUETE_AMD = "ollama-windows-amd64-rocm.zip"

#: Cuánto se lee de golpe al descargar.  Un cuarto de mega: bastante para que
#: el disco no sea el cuello de botella y poco para que el progreso se mueva.
BLOQUE = 262144

#: Cada cuánto se avisa del progreso, en segundos.  Más a menudo no aporta y
#: llena de anuncios al lector de pantalla.
CADA = 1.0

#: Segundos sin que el porcentaje se mueva a partir de los cuales se avisa de
#: que la descarga está parada.  Sin este aviso, una conexión que se corta suena
#: exactamente igual que una descarga que va despacio.
PARADA = 30.0

#: Nombre con el que nos presentamos al pedir cosas por internet.
AGENTE = "VisorUniversal"


class ErrorOllama(Exception):
    """Algo ha ido mal con el servidor local.  El mensaje se enseña tal cual."""


class Cancelado(Exception):
    """El usuario ha cancelado la descarga.  No es un error."""


class EstadoServidor:
    """Quién está escuchando en nuestro puerto, si es que hay alguien.

    Distinguir «nuestro servidor» de «un servidor» es lo que permite no
    apropiarse de lo ajeno: si en el puerto contesta un Ollama que no es el
    nuestro, no se usa ni se mata; se avisa.
    """

    __slots__ = ("activo", "version", "pid", "ejecutable", "propio")

    def __init__(self, activo: bool = False, version: str = "", pid: int = 0,
                 ejecutable: str = "", propio: bool = False) -> None:
        self.activo = activo
        self.version = version
        self.pid = pid
        self.ejecutable = ejecutable
        self.propio = propio

    def __bool__(self) -> bool:
        return self.activo


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

def carpeta_ollama() -> Path:
    """Dónde vive el Ollama portable."""
    return rutas.directorio_datos() / "ollama"


def carpeta_modelos() -> Path:
    """Dónde se guardan los modelos descargados."""
    return rutas.directorio_datos() / "ollama_modelos"


def ejecutable() -> Path:
    """El programa que hay que lanzar."""
    return carpeta_ollama() / "ollama.exe"


def url_servidor() -> str:
    """Dirección de nuestro servidor."""
    return "http://%s:%d" % (HOST, PUERTO)


def url_openai() -> str:
    """Dirección compatible con OpenAI, que es la que usa el resto del programa."""
    return url_servidor() + "/v1"


def instalado() -> bool:
    """Indica si Ollama portable ya está descargado."""
    return ejecutable().is_file()


def version_instalada() -> str:
    """Versión que hay en disco, o cadena vacía."""
    ficha = carpeta_ollama() / "VERSION.txt"
    try:
        return ficha.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# Descargas con progreso
# ---------------------------------------------------------------------------

#: Lo que dicen los fallos de red de Ollama, que van en inglés y no le dicen
#: nada a nadie.  Se reconocen para poder explicar qué hacer, porque la causa
#: casi siempre es la misma y tiene arreglo.
SENALES_DE_RED = (
    "i/o timeout", "dial tcp", "connection refused", "connection reset",
    "no such host", "timeout", "unexpected eof", "tls handshake",
    "max retries exceeded", "network is unreachable",
)


def _parece_gguf(ruta) -> bool:
    """Mira si el archivo empieza por la marca de los GGUF.

    Vale la pena mirarlo antes de copiar varios gigas: si alguien elige por
    error el archivo de pesos original o un ZIP, es mejor decírselo en el acto
    que después de diez minutos de copia y con un error de Ollama en inglés.
    """
    try:
        with open(ruta, "rb") as fichero:
            return fichero.read(4) == b"GGUF"
    except OSError:
        return False


def _nombre_de_modelo(nombre: str) -> str:
    """Deja el nombre como Ollama lo admite.

    Ollama solo acepta letras, números, puntos, guiones y barras bajas, más una
    etiqueta opcional detrás de dos puntos.  Un nombre con espacios o acentos
    —«Qwen visión 3B», que es lo que uno escribiría— lo rechaza con un error
    que no explica nada, así que se arregla aquí en vez de regañar al usuario.
    """
    limpio = unicodedata.normalize("NFKD", (nombre or "").strip())
    limpio = "".join(letra for letra in limpio if not unicodedata.combining(letra))
    limpio = limpio.lower().replace(" ", "-")
    # La etiqueta va detrás de los dos puntos y se conserva; los demás signos
    # raros se caen.
    partes = limpio.split(":", 1)
    partes = [re.sub(r"[^a-z0-9._-]", "", trozo).strip("-.") for trozo in partes]
    if not partes[0]:
        return ""
    return partes[0] + (":" + partes[1] if len(partes) > 1 and partes[1] else "")


def _firma_de(ruta, progreso=None, cancelar=None) -> str:
    """La huella ``sha256`` del archivo, que es como Ollama lo identifica.

    Se lee por bloques de un mega: un GGUF de siete gigas no cabe en memoria y
    tampoco haría falta, y así se puede ir contando por dónde va.
    """
    total = ruta.stat().st_size or 1
    cuenta = hashlib.sha256()
    leido = 0
    ultimo = -1
    with open(ruta, "rb") as fichero:
        while True:
            if cancelar is not None and cancelar():
                raise Cancelado()
            bloque = fichero.read(1024 * 1024)
            if not bloque:
                break
            cuenta.update(bloque)
            leido += len(bloque)
            if progreso is not None:
                cuanto = min(99, int(leido * 100 / total))
                if cuanto != ultimo:
                    ultimo = cuanto
                    progreso(cuanto, _("Comprobando %(que)s: %(cuanto)d por ciento.")
                             % {"que": ruta.name, "cuanto": cuanto})
    return "sha256:" + cuenta.hexdigest()


def _detalle_http(fallo) -> str:
    """Saca el mensaje que venga en el cuerpo de un error HTTP."""
    try:
        cuerpo = json.loads(fallo.read().decode("utf-8", "replace"))
        detalle = str(cuerpo.get("error") or "").strip()
        if detalle:
            return detalle
    except Exception:
        pass
    return str(fallo)


def _explicar(fallo: str) -> str:
    """Añade al fallo de Ollama qué se puede hacer, cuando se sabe.

    Los archivos de los modelos **no se bajan del mismo sitio** que el resto:
    Ollama consulta su registro y luego redirige a un almacén aparte.  Ese
    salto es el que fallan algunos cortafuegos, antivirus y conexiones, con lo
    que todo lo demás funciona —la lista de modelos, el servidor, las
    respuestas— y solo la descarga se queda parada sin decir por qué.

    Merece la pena reconocerlo porque el mensaje de Ollama es una línea en
    inglés con una dirección de cien caracteres, y quien la oye no tiene manera
    de saber que lo que pasa es que algo le está bloqueando un servidor.
    """
    bajo = fallo.lower()
    if not any(senal in bajo for senal in SENALES_DE_RED):
        return fallo
    return _(
        "%(fallo)s\n\nEs un problema de conexión, no del modelo ni del programa. Los "
        "archivos de los modelos se descargan de un almacén aparte del servidor de "
        "Ollama, y hay cortafuegos, antivirus, VPN y conexiones que bloquean ese "
        "almacén aunque el resto de Internet vaya bien.\n\nQué probar: permitir "
        "«r2.cloudflarestorage.com» en el antivirus o el cortafuegos; si usas una "
        "VPN, apagarla —o encenderla, si no la tenías—; y volver a intentarlo, "
        "porque la descarga sigue donde se quedó.") % {"fallo": fallo}


def _tamano(bytes_: float) -> str:
    """«2,4 GB», «700 MB», que es como se dice un tamaño en voz alta."""
    for unidad, salto in ((_("GB"), 1024 ** 3), (_("MB"), 1024 ** 2), (_("KB"), 1024)):
        if bytes_ >= salto:
            return "%s %s" % (("%.1f" % (bytes_ / salto)).replace(".", ","), unidad)
    return _("%d bytes") % int(bytes_)


def _pedir_json(direccion: str, espera: float = 30.0) -> dict:
    """Pide un JSON por internet con nuestro nombre puesto."""
    peticion = urllib.request.Request(direccion, headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(peticion, timeout=espera) as respuesta:
        return json.loads(respuesta.read().decode("utf-8", "replace"))


def _descargar(direccion: str, destino: Path, progreso=None, cancelar=None,
               etiqueta: str = "", sha256: str = "", tamano: int = 0) -> Path:
    """Descarga un archivo diciendo por dónde va, y **reanudando** si se cortó.

    Reanudar importa aquí más que en ningún otro sitio: es más de un giga de
    servidor y hasta siete de modelo, y quien tiene una conexión regular no
    puede permitirse empezar de cero cada vez que se corta.

    :param progreso: ``(porcentaje, mensaje)``.
    :param cancelar: Función que devuelve ``True`` cuando hay que parar.
    """
    etiqueta = etiqueta or destino.name
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_suffix(destino.suffix + ".parte")
    llevado = parcial.stat().st_size if parcial.is_file() else 0

    def abrir(desde: int):
        cabeceras = {"User-Agent": AGENTE}
        if desde:
            cabeceras["Range"] = "bytes=%d-" % desde
        return urllib.request.urlopen(
            urllib.request.Request(direccion, headers=cabeceras), timeout=60)

    try:
        respuesta = abrir(llevado)
    except urllib.error.HTTPError as error:
        # 416: lo que había ya no vale (el archivo del servidor ha cambiado, o
        # estaba entero).  Se tira y se empieza otra vez, en lugar de dejar al
        # usuario atascado con un trozo inservible.
        if error.code == 416 and llevado:
            parcial.unlink(missing_ok=True)
            llevado = 0
            respuesta = abrir(0)
        else:
            raise

    with respuesta:
        if llevado and respuesta.status != 206:
            llevado = 0                     # el servidor no sabe reanudar
        modo = "ab" if llevado else "wb"
        total = llevado + int(respuesta.headers.get("Content-Length") or 0)
        ultimo = 0.0
        with open(parcial, modo) as archivo:
            while True:
                if cancelar is not None and cancelar():
                    raise Cancelado()
                trozo = respuesta.read(BLOQUE)
                if not trozo:
                    break
                archivo.write(trozo)
                llevado += len(trozo)
                ahora = time.monotonic()
                if progreso is not None and ahora - ultimo >= CADA:
                    ultimo = ahora
                    if total:
                        porcentaje = min(99, int(llevado * 100 / total))
                        progreso(porcentaje, _("Descargando %s: %d por ciento, %s de %s.")
                                 % (etiqueta, porcentaje, _tamano(llevado), _tamano(total)))
                    else:
                        progreso(0, _("Descargando %s: %s.") % (etiqueta, _tamano(llevado)))

    if tamano and parcial.stat().st_size != tamano:
        parcial.unlink(missing_ok=True)
        raise ErrorOllama(_("La descarga de %s ha salido incompleta. Vuelve a intentarlo.")
                          % etiqueta)
    if sha256:
        if progreso is not None:
            progreso(99, _("Comprobando que %s ha llegado entero...") % etiqueta)
        if _resumen(parcial, cancelar).lower() != sha256.lower():
            parcial.unlink(missing_ok=True)
            raise ErrorOllama(
                _("La comprobación de %s ha fallado: el archivo no es el que publica "
                  "Ollama. No se instala nada.") % etiqueta)
    destino.unlink(missing_ok=True)
    parcial.replace(destino)
    return destino


def _resumen(ruta: Path, cancelar=None) -> str:
    """SHA-256 de un archivo, sin cargarlo entero en memoria."""
    digestor = hashlib.sha256()
    with open(ruta, "rb") as archivo:
        while True:
            if cancelar is not None and cancelar():
                raise Cancelado()
            trozo = archivo.read(BLOQUE)
            if not trozo:
                break
            digestor.update(trozo)
    return digestor.hexdigest()


def _extraer(archivo_zip: Path, destino: Path, progreso=None, cancelar=None,
             desde: int = 85, hasta: int = 99) -> None:
    """Descomprime comprobando que nada se salga de su carpeta.

    Un ZIP puede traer rutas como ``..\\..\\Windows\\system32``; descomprimirlo
    a lo tonto es dejar que un archivo bajado de internet escriba donde quiera.
    """
    destino.mkdir(parents=True, exist_ok=True)
    raiz = destino.resolve()
    with zipfile.ZipFile(archivo_zip) as paquete:
        entradas = paquete.infolist()
        for numero, entrada in enumerate(entradas, start=1):
            if cancelar is not None and cancelar():
                raise Cancelado()
            salida = (destino / entrada.filename).resolve()
            if not str(salida).startswith(str(raiz)):
                raise ErrorOllama(_("El paquete de Ollama trae rutas que se salen de su "
                                    "carpeta. No se instala."))
            paquete.extract(entrada, destino)
            if progreso is not None and numero % 25 == 0:
                tanto = desde + int((hasta - desde) * numero / max(len(entradas), 1))
                progreso(tanto, _("Descomprimiendo Ollama: %d de %d archivos.")
                         % (numero, len(entradas)))


# ---------------------------------------------------------------------------
# El gestor
# ---------------------------------------------------------------------------

class Ollama:
    """Instala, arranca, para y alimenta de modelos el Ollama de la aplicación.

    Se crea uno solo y vive en la ventana principal, porque el servidor también
    es uno solo: dos gestores lanzarían dos servidores en el mismo puerto.
    """

    def __init__(self, configuracion=None) -> None:
        self.configuracion = configuracion
        self._proceso = None
        self._registro = None
        self._cerrojo = threading.Lock()
        #: Si el servidor que hay en marcha lo arrancó otro y solo lo usamos.
        self._adoptado = False

    # -- versiones -----------------------------------------------------------

    def ultima_version(self) -> dict:
        """Consulta cuál es la última versión publicada de Ollama.

        :return: ``{"version", "url", "tamano", "sha256"}`` y, si la hay, la
                 entrada ``"amd"`` con lo mismo del paquete para gráficas AMD.
        """
        try:
            datos = _pedir_json(API_VERSIONES)
        except Exception as error:
            raise ErrorOllama(
                _("No se ha podido consultar si hay versión nueva de Ollama: %s") % error)
        resultado = {"version": str(datos.get("tag_name") or "").lstrip("v")}
        for recurso in datos.get("assets") or []:
            nombre = str(recurso.get("name", "")).lower()
            resumen = str(recurso.get("digest") or "")
            if resumen.startswith("sha256:"):
                resumen = resumen[7:]
            ficha = {"url": str(recurso.get("browser_download_url") or ""),
                     "tamano": int(recurso.get("size") or 0), "sha256": resumen}
            if nombre == PAQUETE_WINDOWS.lower():
                resultado.update(ficha)
            elif nombre == PAQUETE_AMD.lower():
                resultado["amd"] = ficha
        if not resultado.get("url"):
            raise ErrorOllama(_("La publicación de Ollama no trae el paquete de Windows."))
        return resultado

    def hay_actualizacion(self) -> tuple[bool, str, str]:
        """``(hay una nueva, la instalada, la última)``."""
        instalada = version_instalada()
        ultima = self.ultima_version().get("version", "")
        return bool(ultima and instalada != ultima), instalada, ultima

    # -- instalación ---------------------------------------------------------

    def instalar(self, progreso=None, cancelar=None, con_amd: bool | None = None) -> str:
        """Descarga e instala Ollama portable dentro de ``data``.

        Si ya está la última versión no se descarga nada y se dice.  La
        instalación se hace **a un lado y se cambia al final**: si algo falla a
        mitad, lo que había sigue funcionando.

        :return: La versión que ha quedado instalada.
        """
        meta = self.ultima_version()
        actual = version_instalada()
        if actual and actual == meta["version"] and instalado():
            if progreso is not None:
                progreso(100, _("Ollama %s ya estaba instalado y al día.") % actual)
            return actual

        if con_amd is None:
            con_amd = self._hay_grafica_amd()
        extra = meta.get("amd") if con_amd else None
        fin_base = 55 if extra else 85

        descargas = rutas.directorio_datos() / "temp"
        paquete = descargas / ("ollama-%s.zip" % meta["version"])
        _descargar(meta["url"], paquete, _tramo(progreso, 0, fin_base), cancelar,
                   _("Ollama"), meta.get("sha256", ""), meta.get("tamano", 0))
        paquete_amd = None
        if extra and extra.get("url"):
            paquete_amd = descargas / ("ollama-amd-%s.zip" % meta["version"])
            _descargar(extra["url"], paquete_amd, _tramo(progreso, 55, 85), cancelar,
                       _("complemento para gráficas AMD"), extra.get("sha256", ""),
                       extra.get("tamano", 0))

        nueva = carpeta_ollama().with_name("ollama_nueva")
        vieja = carpeta_ollama().with_name("ollama_anterior")
        for carpeta in (nueva, vieja):
            shutil.rmtree(carpeta, ignore_errors=True)
        _extraer(paquete, nueva, progreso, cancelar, 85, 92 if paquete_amd else 99)
        if paquete_amd:
            _extraer(paquete_amd, nueva, progreso, cancelar, 92, 99)
        if not (nueva / "ollama.exe").is_file():
            shutil.rmtree(nueva, ignore_errors=True)
            raise ErrorOllama(_("El paquete descargado no trae el programa de Ollama."))
        (nueva / "VERSION.txt").write_text(meta["version"], encoding="utf-8")

        # Solo se para lo que es nuestro: un servidor ajeno en el puerto no
        # bloquea esta carpeta y no tiene por qué morir por esto.
        if self.estado().propio:
            self.detener(forzar=True)
        try:
            if carpeta_ollama().is_dir():
                os.replace(carpeta_ollama(), vieja)
            os.replace(nueva, carpeta_ollama())
            shutil.rmtree(vieja, ignore_errors=True)
        except OSError:
            if not carpeta_ollama().is_dir() and vieja.is_dir():
                os.replace(vieja, carpeta_ollama())
            raise
        paquete.unlink(missing_ok=True)
        if paquete_amd:
            paquete_amd.unlink(missing_ok=True)
        if progreso is not None:
            progreso(100, _("Ollama %s instalado.") % meta["version"])
        log.info("Ollama portable instalado: version %s", meta["version"])
        return meta["version"]

    @staticmethod
    def _hay_grafica_amd() -> bool:
        """Mira si el equipo tiene una gráfica AMD que merezca el complemento.

        Se apoya en la misma detección que el resto.  Antes preguntaba por su
        cuenta con ``wmic``, que ya no existe en Windows 11: la orden fallaba,
        la respuesta era siempre «no» y quien tuviera una Radeon se quedaba sin
        el complemento que hace que su tarjeta se use.
        """
        return any("amd" in nombre.lower() or "radeon" in nombre.lower()
                   for nombre, _vram in graficas())

    def desinstalar(self) -> None:
        """Borra Ollama y sus modelos.  Se usa desde «Datos guardados»."""
        self.detener(forzar=True)
        shutil.rmtree(carpeta_ollama(), ignore_errors=True)
        shutil.rmtree(carpeta_modelos(), ignore_errors=True)

    # -- el servidor ---------------------------------------------------------

    def _consultar(self, ruta: str, espera: float = 3.0) -> dict:
        """Pregunta algo a la API del servidor.  Devuelve ``{}`` si no contesta."""
        try:
            peticion = urllib.request.Request(url_servidor() + ruta,
                                              headers={"User-Agent": AGENTE})
            with urllib.request.urlopen(peticion, timeout=espera) as respuesta:
                datos = json.loads(respuesta.read().decode("utf-8", "replace"))
            return datos if isinstance(datos, dict) else {}
        except Exception:
            return {}

    def estado(self) -> EstadoServidor:
        """Quién está escuchando en nuestro puerto.

        Se comprueba **qué programa** es y no solo que conteste: adoptar un
        servidor ajeno sería usar sus modelos sin permiso, y matarlo, peor.
        """
        datos = self._consultar("/api/version", espera=2.0)
        if not datos:
            return EstadoServidor()
        pid = self._pid_en_el_puerto()
        ruta = self._ruta_del_proceso(pid) if pid else ""
        propio = bool(ruta) and self._misma_ruta(ruta, str(ejecutable()))
        return EstadoServidor(True, str(datos.get("version", "")), pid, ruta, propio)

    @staticmethod
    def _misma_ruta(una: str, otra: str) -> bool:
        """Compara dos rutas sin fiarse de cómo estén escritas."""
        if not una or not otra:
            return False
        try:
            return os.path.samefile(una, otra)
        except OSError:
            return os.path.normcase(os.path.abspath(una)) == \
                os.path.normcase(os.path.abspath(otra))

    @staticmethod
    def _pid_en_el_puerto() -> int:
        """Qué proceso escucha en nuestro puerto, según Windows.

        Se busca por puerto y no por nombre: matar «todos los ollama.exe» del
        equipo sería llevarse por delante el del usuario.
        """
        if os.name != "nt":
            return 0
        try:
            salida = subprocess.run(
                ["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True,
                errors="replace", timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            for linea in (salida.stdout or "").splitlines():
                partes = linea.split()
                if len(partes) >= 5 and partes[3].upper() == "LISTENING" \
                        and partes[1].endswith(":%d" % PUERTO):
                    return int(partes[4])
        except Exception:
            log.debug("No se ha podido mirar quién ocupa el puerto", exc_info=True)
        return 0

    @staticmethod
    def _ruta_del_proceso(pid: int) -> str:
        """Ruta del programa de un proceso, para saber si es el nuestro.

        De esto depende que no se toque un servidor ajeno, así que importa que
        funcione: iba con ``wmic``, que **ya no viene con Windows 11**, y al
        fallar la respuesta era siempre «no se sabe».  Con eso, el programa no
        llegaba a reconocer ni su propio servidor —lo daba por ajeno y se
        negaba a usarlo o a pararlo—.

        Se pregunta con PowerShell, y si eso falla, por la API de Windows.  Una
        cadena vacía significa **no se sabe**, y quien llama no adopta ni mata
        nada cuando no se sabe: equivocarse aquí es usar los modelos de otro
        sin permiso, o cerrarle el servidor en mitad de su trabajo.
        """
        if not pid or os.name != "nt":
            return ""
        try:
            salida = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                 "(Get-Process -Id %d -ErrorAction SilentlyContinue).Path" % pid],
                capture_output=True, text=True, errors="replace", timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            for linea in (salida.stdout or "").splitlines():
                if linea.strip():
                    return linea.strip()
        except Exception:
            log.debug("No se ha podido saber qué programa es el PID %s", pid, exc_info=True)
        return Ollama._ruta_por_api(pid)

    @staticmethod
    def _ruta_por_api(pid: int) -> str:
        """Lo mismo, preguntándoselo a Windows directamente.

        Sirve de red por si PowerShell no está disponible o tarda demasiado.
        """
        try:
            import ctypes
            from ctypes import wintypes

            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            # Solo consulta: pedir menos permisos de los justos hace que
            # funcione también con procesos que no son nuestros.
            acceso = 0x1000                          # PROCESS_QUERY_LIMITED_INFORMATION
            asa = kernel.OpenProcess(acceso, False, pid)
            if not asa:
                return ""
            try:
                tamano = wintypes.DWORD(32768)
                sitio = ctypes.create_unicode_buffer(tamano.value)
                if kernel.QueryFullProcessImageNameW(asa, 0, sitio,
                                                     ctypes.byref(tamano)):
                    return sitio.value
            finally:
                kernel.CloseHandle(asa)
        except Exception:
            log.debug("Tampoco por la API se sabe qué es el PID %s", pid, exc_info=True)
        return ""

    def _entorno(self) -> dict:
        """Variables con las que se lanza el servidor.

        Aquí es donde se le dice que use **nuestro** puerto y **nuestro**
        almacén, y donde se aplican los ajustes del motor: si trabaja con la
        tarjeta gráfica o solo con el procesador, cuánto tiempo deja el modelo
        cargado y cuánta memoria de contexto le da.
        """
        entorno = os.environ.copy()
        entorno["OLLAMA_HOST"] = "%s:%d" % (HOST, PUERTO)
        entorno["OLLAMA_MODELS"] = str(carpeta_modelos())
        obtener = (self.configuracion.obtener if self.configuracion is not None
                   else lambda clave, omision=None: omision)

        modo = str(obtener("ollama_calculo", "auto") or "auto")
        if modo == "cpu":
            # Sin esto, Ollama usa la gráfica en cuanto la ve.  Hay equipos
            # donde eso es peor que el procesador: gráficas integradas con poca
            # memoria que acaban tirando por falta de sitio.
            entorno["CUDA_VISIBLE_DEVICES"] = "-1"
            entorno["HIP_VISIBLE_DEVICES"] = "-1"
            entorno["GGML_VK_VISIBLE_DEVICES"] = "-1"

        minutos = int(obtener("ollama_mantener_cargado", 5) or 5)
        entorno["OLLAMA_KEEP_ALIVE"] = "%dm" % max(0, minutos)

        contexto = int(obtener("ollama_contexto", 0) or 0)
        if contexto:
            entorno["OLLAMA_CONTEXT_LENGTH"] = str(contexto)
        if obtener("ollama_atencion_rapida", False):
            entorno["OLLAMA_FLASH_ATTENTION"] = "1"
        # Nunca se sale a internet a buscar modelos remotos: lo que se instala
        # aquí se instala a mano y a propósito.
        entorno["OLLAMA_NO_CLOUD"] = "1"
        return entorno

    def iniciar(self, esperar: bool = True, espera_maxima: float = 45.0) -> None:
        """Arranca el servidor, o reutiliza el nuestro si ya estaba.

        :raises ErrorOllama: Si el puerto lo ocupa un servidor que no es el
                             nuestro, o si el nuestro no llega a responder.
        """
        with self._cerrojo:
            if self._proceso is not None and self._proceso.poll() is None:
                return
            actual = self.estado()
            if actual.activo:
                if not actual.propio:
                    raise ErrorOllama(_(
                        "El puerto %d lo está usando otro servidor de Ollama (proceso %s). "
                        "El programa no va a usarlo ni a cerrarlo: ciérralo tú y vuelve a "
                        "intentarlo.") % (PUERTO, actual.pid or _("desconocido")))
                self._adoptado = True
                return
            if not instalado():
                raise ErrorOllama(_(
                    "Ollama no está instalado todavía. Ve a Opciones, «IA local», y usa el "
                    "asistente para instalarlo."))
            carpeta_modelos().mkdir(parents=True, exist_ok=True)
            registro = rutas.ruta_logs() / "ollama.log"
            try:
                if registro.is_file() and registro.stat().st_size > 5 * 1024 * 1024:
                    os.replace(registro, registro.with_suffix(".log.anterior"))
            except OSError:
                pass
            self._registro = open(registro, "a", encoding="utf-8")
            self._proceso = subprocess.Popen(
                [str(ejecutable()), "serve"], cwd=str(carpeta_ollama()),
                env=self._entorno(), stdout=self._registro,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self._adoptado = False
            log.info("Servidor Ollama lanzado (proceso %s) en %s",
                     self._proceso.pid, url_servidor())
        if esperar:
            self._esperar(espera_maxima)

    def _esperar(self, segundos: float) -> None:
        """Espera a que el servidor conteste, o explica por qué no lo hace."""
        limite = time.monotonic() + segundos
        while time.monotonic() < limite:
            if self.estado().activo:
                return
            if self._proceso is not None and self._proceso.poll() is not None:
                raise ErrorOllama(_(
                    "El servidor de Ollama se ha cerrado nada más arrancar. En "
                    "data\\logs\\ollama.log está lo que ha dicho."))
            time.sleep(0.3)
        raise ErrorOllama(_("El servidor de Ollama no ha respondido a tiempo."))

    def detener(self, forzar: bool = False) -> str:
        """Para el servidor.  Devuelve qué ha pasado de verdad.

        * ``"detenido"``: estaba en marcha y ya no lo está.
        * ``"no_habia"``: no había nada que parar.
        * ``"ajeno"``: hay un servidor, pero no lo arrancamos nosotros y no se
          toca.
        * ``"fallo"``: se ha intentado y sigue contestando.
        """
        with self._cerrojo:
            proceso, self._proceso = self._proceso, None
            registro, self._registro = self._registro, None
        estado = self.estado()
        if not estado.activo and proceso is None:
            return "no_habia"
        if estado.activo and not estado.propio and proceso is None:
            return "ajeno"
        if proceso is not None and proceso.poll() is None:
            self._matar_arbol(proceso.pid, forzar)
        elif estado.pid:
            self._matar_arbol(estado.pid, forzar)
        if registro is not None:
            try:
                registro.close()
            except OSError:
                pass
        for _intento in range(20):
            if not self.estado().activo:
                self._adoptado = False
                return "detenido"
            time.sleep(0.2)
        return "fallo"

    @staticmethod
    def _matar_arbol(pid: int, forzar: bool) -> None:
        """Cierra el proceso **y los suyos**.

        Ollama lanza un ayudante por cada modelo cargado.  Matando solo al
        padre, esos ayudantes se quedan vivos reteniendo la memoria de la
        tarjeta gráfica, y el siguiente arranque falla por falta de sitio.
        """
        if not pid:
            return
        if os.name == "nt":
            orden = ["taskkill", "/PID", str(pid), "/T"]
            if forzar:
                orden.append("/F")
            try:
                subprocess.run(orden, capture_output=True, timeout=20,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                return
            except Exception:
                log.debug("taskkill no ha podido con el proceso %s", pid, exc_info=True)
        try:
            os.kill(pid, 9 if forzar else 15)
        except OSError:
            pass

    def asegurar_en_marcha(self) -> bool:
        """Arranca el servidor si hace falta.  Devuelve si está listo.

        Es lo que llama el resto del programa antes de pedirle algo: así el
        usuario no tiene que acordarse de encenderlo.
        """
        try:
            if self.estado().activo:
                return True
            self.iniciar()
            return True
        except ErrorOllama as error:
            log.warning("No se ha podido arrancar Ollama: %s", error)
            return False

    # -- modelos -------------------------------------------------------------

    def modelos(self) -> list[dict]:
        """Los modelos que hay descargados, con su tamaño.

        :return: Lista de ``{"nombre", "tamano", "familia", "vision"}``.
        """
        datos = self._consultar("/api/tags", espera=10.0)
        salida = []
        for ficha in datos.get("models", []) or []:
            detalles = ficha.get("details") or {}
            salida.append({
                "nombre": str(ficha.get("name", "")),
                "tamano": int(ficha.get("size") or 0),
                "familia": str(detalles.get("family", "")),
                "vision": self._parece_de_vision(ficha),
            })
        return sorted(salida, key=lambda ficha: ficha["nombre"])

    @staticmethod
    def _parece_de_vision(ficha: dict) -> bool:
        """Adivina si un modelo ve, mirando cómo se llama y de qué familia es.

        Ollama no lo dice en ``/api/tags``, y preguntarlo modelo a modelo
        costaría una consulta por cada uno.  Con los nombres basta: los que ven
        lo llevan escrito.
        """
        detalles = ficha.get("details") or {}
        texto = " ".join((str(ficha.get("name", "")), str(detalles.get("family", "")),
                          " ".join(detalles.get("families") or []))).lower()
        señales = ("vision", "vl", "llava", "moondream", "minicpm-v", "gemma3",
                   "clip", "mllama", "granite3.2-vision")
        return any(señal in texto for señal in señales)

    def importar_modelo(self, nombre: str, modelo, vision=None,
                        progreso=None, cancelar=None) -> str:
        """Mete en Ollama un modelo que ya está en el disco, en formato GGUF.

        :param nombre: Con qué nombre quedará guardado.
        :param modelo: Archivo ``.gguf`` con el modelo.
        :param vision: Archivo ``.gguf`` del **proyector de visión**, el que le
                       da la capacidad de ver imágenes.  Sin él, el modelo
                       queda solo para texto.
        :param progreso: ``funcion(porcentaje, mensaje)``.
        :param cancelar: ``funcion()`` que devuelve si hay que parar.
        :return: El nombre con el que ha quedado guardado.
        :raises ErrorOllama: Si los archivos no valen o Ollama los rechaza.

        Un modelo con visión son **dos archivos**: los pesos, que escriben y
        razonan, y el proyector, que traduce la imagen a algo que los pesos
        entiendan.  Quien se baja uno de estos por su cuenta acaba con dos
        ``.gguf`` en una carpeta y sin manera de usarlos, porque Ollama no lee
        archivos sueltos: trabaja con su propio almacén.

        Meterlos ahí son tres pasos por archivo, y se hacen aquí:

        #. **Firmarlo.**  El almacén de Ollama guarda cada archivo por su
           huella ``sha256``, no por su nombre.
        #. **Copiarlo**, si no estaba ya.  Como la huella es del contenido, un
           archivo que ya esté no se vuelve a copiar: importar dos veces el
           mismo modelo con nombres distintos no ocupa el doble.
        #. **Crear el modelo**, diciéndole a Ollama qué archivo es cada cosa.
           Cuál de los dos es el proyector lo reconoce él solo, por lo que el
           propio GGUF lleva escrito dentro.

        Todo va con progreso porque un GGUF son varios gigas: leerlo entero
        para firmarlo y volver a escribirlo en el almacén lleva su rato, y sin
        avisos parece que el programa se ha quedado colgado.
        """
        nombre = _nombre_de_modelo(nombre)
        if not nombre:
            raise ErrorOllama(_("Hace falta un nombre para el modelo."))

        piezas: dict[str, str] = {}
        archivos = [("model.gguf", Path(modelo))]
        if vision:
            archivos.append(("mmproj.gguf", Path(vision)))
        for papel, ruta in archivos:
            if not ruta.is_file():
                raise ErrorOllama(_("No se encuentra el archivo: %s") % ruta)
            if not _parece_gguf(ruta):
                raise ErrorOllama(_(
                    "«%s» no es un archivo GGUF. Los modelos para Ollama son archivos "
                    "con extensión .gguf; si lo has bajado de Hugging Face, es el que "
                    "pone «GGUF» y no el de pesos originales.") % ruta.name)
        # Con un solo archivo se conserva su nombre, que es lo que luego se ve
        # al mirar el modelo por dentro.  Con dos hacen falta los nombres que
        # Ollama espera para distinguir los papeles.
        if len(archivos) == 1:
            archivos = [(archivos[0][1].name, archivos[0][1])]

        if not self.asegurar_en_marcha():
            raise ErrorOllama(_("El servidor de Ollama no está en marcha."))

        # El reparto de la barra va por tamaño: el proyector suele ser diez
        # veces más pequeño que los pesos, y darle la mitad del recorrido haría
        # que la barra se plantara en el 50 % durante casi toda la importación.
        tamanos = [ruta.stat().st_size for _papel, ruta in archivos]
        total = sum(tamanos) or 1
        desde = 0.0
        for (papel, ruta), tamano in zip(archivos, tamanos):
            parte = 90.0 * tamano / total
            mitad = desde + parte / 2
            firma = _firma_de(ruta, _tramo(progreso, int(desde), int(mitad)), cancelar)
            if self._blob_esta(firma):
                if progreso is not None:
                    progreso(int(desde + parte),
                             _("%s ya estaba en el almacén: no hace falta copiarlo.")
                             % ruta.name)
            else:
                self._subir_blob(ruta, firma,
                                 _tramo(progreso, int(mitad), int(desde + parte)), cancelar)
            piezas[papel] = firma
            desde += parte

        if progreso is not None:
            progreso(92, _("Creando el modelo en Ollama..."))
        self._crear_modelo(nombre, piezas, cancelar)
        if progreso is not None:
            progreso(100, _("Modelo «%s» importado.") % nombre)
        log.info("Modelo importado del disco: %s (%d archivos)", nombre, len(piezas))
        return nombre

    def _blob_esta(self, firma: str) -> bool:
        """Si el almacén de Ollama ya tiene ese archivo."""
        peticion = urllib.request.Request(
            url_servidor() + "/api/blobs/" + firma, method="HEAD",
            headers={"User-Agent": AGENTE})
        try:
            with urllib.request.urlopen(peticion, timeout=30):
                return True
        except urllib.error.HTTPError:
            return False
        except Exception:
            return False

    def _subir_blob(self, ruta, firma: str, progreso=None, cancelar=None) -> None:
        """Copia el archivo al almacén de Ollama, sin cargarlo en memoria.

        Se manda con un lector por bloques y con ``Content-Length`` puesto a
        mano: un GGUF son varios gigas y leerlo entero para enviarlo dejaría al
        programa sin memoria en el peor momento.
        """
        total = ruta.stat().st_size

        class _PorBloques:
            """Lo que urllib va leyendo, contando por dónde va."""

            def __init__(self, fichero):
                self.fichero = fichero
                self.leido = 0
                self.ultimo = -1

            def read(self, cuantos=-1):
                if cancelar is not None and cancelar():
                    raise Cancelado()
                datos = self.fichero.read(cuantos)
                self.leido += len(datos)
                if progreso is not None and total:
                    cuanto = min(99, int(self.leido * 100 / total))
                    if cuanto != self.ultimo:
                        self.ultimo = cuanto
                        progreso(cuanto, _("Copiando %(que)s al almacén: %(cuanto)d "
                                           "por ciento.") % {"que": ruta.name,
                                                             "cuanto": cuanto})
                return datos

        with open(ruta, "rb") as fichero:
            peticion = urllib.request.Request(
                url_servidor() + "/api/blobs/" + firma, data=_PorBloques(fichero),
                headers={"User-Agent": AGENTE, "Content-Length": str(total)},
                method="POST")
            try:
                with urllib.request.urlopen(peticion, timeout=3600):
                    pass
            except Cancelado:
                raise
            except urllib.error.HTTPError as fallo:
                raise ErrorOllama(_("Ollama no ha aceptado el archivo %(que)s: %(fallo)s")
                                  % {"que": ruta.name, "fallo": _detalle_http(fallo)})
            except Exception as fallo:
                raise ErrorOllama(_("No se ha podido copiar %(que)s: %(fallo)s")
                                  % {"que": ruta.name, "fallo": _explicar(str(fallo))})

    def _crear_modelo(self, nombre: str, piezas: dict, cancelar=None) -> None:
        """Le dice a Ollama que arme el modelo con los archivos ya copiados."""
        cuerpo = json.dumps({"model": nombre, "files": piezas,
                             "stream": True}).encode("utf-8")
        peticion = urllib.request.Request(
            url_servidor() + "/api/create", data=cuerpo,
            headers={"Content-Type": "application/json", "User-Agent": AGENTE})
        try:
            with urllib.request.urlopen(peticion, timeout=1800) as respuesta:
                for linea in respuesta:
                    if cancelar is not None and cancelar():
                        raise Cancelado()
                    linea = linea.strip()
                    if not linea:
                        continue
                    try:
                        paso = json.loads(linea.decode("utf-8", "replace"))
                    except ValueError:
                        continue
                    if paso.get("error"):
                        raise ErrorOllama(_("Ollama no ha podido crear el modelo: %s")
                                          % paso["error"])
        except (Cancelado, ErrorOllama):
            raise
        except Exception as fallo:
            raise ErrorOllama(_("Ollama no ha podido crear el modelo: %s") % fallo)

    def descargar_modelo(self, etiqueta: str, progreso=None, cancelar=None) -> None:
        """Descarga un modelo, contando por dónde va.

        Ollama devuelve el progreso en un flujo de líneas JSON, y el detalle
        que lo cambia todo es que **cada línea habla de una capa, no del
        modelo**.  Un modelo son varias capas —los pesos, el proyector de
        visión, la plantilla— y cada una empieza a contar desde cero.

        Quedarse con lo que dice la última línea, que es lo que se hacía, da un
        porcentaje inservible: sube dentro de una capa, vuelve a cero cuando
        empieza la siguiente y se queda plantado en cero mientras una capa
        arranca, que es justo cuando el usuario mira si aquello avanza.  Aquí
        se anota **lo que lleva cada capa**, identificada por su ``digest``, y
        se suma todo: eso sí es «cuánto falta».

        Se anota en cada línea y se informa cada :data:`CADA` segundos.  Anotar
        solo al informar dejaría fuera lo que pasa entre dos avisos y el total
        saldría corto.
        """
        if not self.asegurar_en_marcha():
            raise ErrorOllama(_("El servidor de Ollama no está en marcha."))
        cuerpo = json.dumps({"model": etiqueta, "stream": True}).encode("utf-8")
        peticion = urllib.request.Request(
            url_servidor() + "/api/pull", data=cuerpo,
            headers={"Content-Type": "application/json", "User-Agent": AGENTE})
        capas: dict[str, tuple[int, int]] = {}
        ultimo = 0.0
        avance = 0.0
        anterior = -1
        try:
            with urllib.request.urlopen(peticion, timeout=3600) as respuesta:
                for linea in respuesta:
                    if cancelar is not None and cancelar():
                        raise Cancelado()
                    linea = linea.strip()
                    if not linea:
                        continue
                    try:
                        paso = json.loads(linea.decode("utf-8", "replace"))
                    except ValueError:
                        continue
                    if paso.get("error"):
                        raise ErrorOllama(_("Ollama no ha podido descargar el modelo: %s")
                                          % _explicar(str(paso["error"])))
                    digest = str(paso.get("digest") or "")
                    total = int(paso.get("total") or 0)
                    hecho = int(paso.get("completed") or 0)
                    if digest and total:
                        capas[digest] = (hecho, total)
                    ahora = time.monotonic()
                    if progreso is None or ahora - ultimo < CADA:
                        continue
                    ultimo = ahora
                    cuanto, mensaje = self._paso_legible(paso, capas)
                    # Una descarga que se para no da ningún aviso: Ollama deja
                    # de mandar líneas nuevas o las manda con el mismo número,
                    # y quien escucha oye la misma frase una y otra vez sin
                    # saber si aquello sigue vivo.  Se dice.
                    if cuanto != anterior:
                        anterior, avance = cuanto, ahora
                    elif ahora - avance >= PARADA:
                        mensaje = _("%(que)s Lleva %(cuanto)d segundos sin avanzar; "
                                    "puede ser la conexión.") % {
                            "que": mensaje, "cuanto": int(ahora - avance)}
                    progreso(cuanto, mensaje)
        except Cancelado:
            raise
        except ErrorOllama:
            raise
        except Exception as error:
            raise ErrorOllama(_("Se ha cortado la descarga del modelo: %s")
                              % _explicar(str(error)))
        if progreso is not None:
            progreso(100, _("Modelo %s descargado.") % etiqueta)

    @staticmethod
    def _paso_legible(paso: dict, capas: dict | None = None) -> tuple[int, str]:
        """Traduce un paso de la descarga a porcentaje y frase.

        :param paso: La línea que acaba de llegar.
        :param capas: Lo que lleva descargado cada capa, ``{digest: (hecho,
                      total)}``.  Es de donde sale el porcentaje de verdad; sin
                      esto solo se puede mirar la capa que toque ahora.
        """
        hecho = total = 0
        if capas:
            hecho = sum(cuanto for cuanto, _todo in capas.values())
            total = sum(todo for _cuanto, todo in capas.values())
        if not total:
            total = int(paso.get("total") or 0)
            hecho = int(paso.get("completed") or 0)
        porcentaje = min(99, int(hecho * 100 / total)) if total else 0

        estado = str(paso.get("status", "")).strip()
        traducciones = {
            "pulling manifest": _("Preguntando por el modelo..."),
            "verifying sha256 digest": _("Comprobando que ha llegado entero..."),
            "writing manifest": _("Terminando de guardarlo..."),
            "removing any unused layers": _("Limpiando lo que ya no hace falta..."),
            "removing unused layers": _("Limpiando lo que ya no hace falta..."),
            "success": _("Modelo listo."),
        }
        frase = traducciones.get(estado.lower())
        if frase:
            # Se conserva el porcentaje alcanzado en lugar de volver a cero:
            # ver la barra caer mientras se comprueba el archivo parece que
            # algo ha salido mal, y lo que pasa es lo contrario.
            return (99 if estado.lower() == "success" else porcentaje), frase
        if total and hecho:
            return porcentaje, _("Descargando el modelo: %d por ciento, %s de %s.") % (
                porcentaje, _tamano(hecho), _tamano(total))
        if total:
            # Se sabe lo que ocupa pero todavía no ha llegado nada.  Decirlo
            # así es mejor que soltar «pulling e554c6b9de01», que además de no
            # significar nada suena a error.
            return porcentaje, _("Empezando la descarga del modelo: %s.") % _tamano(total)
        return porcentaje, _("Trabajando: %s") % estado

    def borrar_modelo(self, etiqueta: str) -> None:
        """Quita un modelo del disco."""
        if not self.asegurar_en_marcha():
            raise ErrorOllama(_("El servidor de Ollama no está en marcha."))
        cuerpo = json.dumps({"model": etiqueta}).encode("utf-8")
        peticion = urllib.request.Request(
            url_servidor() + "/api/delete", data=cuerpo, method="DELETE",
            headers={"Content-Type": "application/json", "User-Agent": AGENTE})
        try:
            with urllib.request.urlopen(peticion, timeout=60):
                pass
        except Exception as error:
            raise ErrorOllama(_("No se ha podido borrar el modelo: %s") % error)

    def espacio_de_los_modelos(self) -> int:
        """Cuánto ocupan en disco los modelos descargados, en bytes."""
        total = 0
        for carpeta, _subcarpetas, archivos in os.walk(carpeta_modelos()):
            for nombre in archivos:
                try:
                    total += (Path(carpeta) / nombre).stat().st_size
                except OSError:
                    pass
        return total


def _tramo(progreso, desde: int, hasta: int):
    """Acota un progreso a un tramo del total.

    Descargar Ollama son varios pasos, y cada uno cree que va del 0 al 100.
    Esto los coloca en su trozo de la barra para que avance una sola vez.
    """
    if progreso is None:
        return None

    def informar(porcentaje: int, mensaje: str) -> None:
        acotado = max(0, min(100, int(porcentaje)))
        progreso(desde + int((hasta - desde) * acotado / 100), mensaje)

    return informar


#: Gestor único de la aplicación.  Se le pasa la configuración al arrancar.
gestor = Ollama()


# ---------------------------------------------------------------------------
# Qué equipo hay debajo
# ---------------------------------------------------------------------------

class Equipo(NamedTuple):
    """Lo que hace falta saber del ordenador para elegir modelo y modo.

    :param memoria_gb: Memoria total del equipo.
    :param libre_gb: La que hay libre ahora mismo, que es la que de verdad
                     limita: un modelo no entra en la memoria que ocupa el
                     navegador.
    :param grafica: Nombre de la tarjeta, o cadena vacía si no se ha visto
                    ninguna.
    :param vram_gb: Memoria de la tarjeta.  Vale ``0.0`` cuando no se ha
                    podido averiguar, que **no** es lo mismo que no tenerla.
    :param dedicada: Si es una tarjeta aparte y no la del propio procesador.
    """

    memoria_gb: float
    libre_gb: float
    grafica: str
    vram_gb: float
    dedicada: bool = False

    @property
    def hay_grafica(self) -> bool:
        """Si hay una tarjeta que merezca la pena usar.

        Una memoria desconocida no descarta la tarjeta.  Antes sí, y con eso
        bastaba para que un equipo con una tarjeta buena acabara tirando del
        procesador: si no se sabe cuánta memoria tiene, se usa y que sea el
        propio motor quien decida, que para eso sabe mirarlo mejor.
        """
        if not self.dedicada:
            return False
        return self.vram_gb >= 2.0 or self.vram_gb == 0.0

    def resumen(self) -> str:
        """Frase que describe el equipo, para enseñarla en el asistente."""
        partes = [_("%s de memoria, %s libres ahora")
                  % (_gigas(self.memoria_gb), _gigas(self.libre_gb))]
        if self.hay_grafica and self.vram_gb:
            partes.append(_("tarjeta gráfica %s con %s")
                          % (self.grafica, _gigas(self.vram_gb)))
        elif self.hay_grafica:
            partes.append(_("tarjeta gráfica %s, de memoria desconocida")
                          % self.grafica)
        elif self.grafica:
            partes.append(_("gráfica %s, integrada en el procesador: será él quien "
                            "trabaje") % self.grafica)
        else:
            partes.append(_("sin tarjeta gráfica dedicada: se usará el procesador"))
        return "; ".join(partes) + "."


def _gigas(valor: float) -> str:
    """«8 GB», «3,5 GB»."""
    if valor <= 0:
        return _("desconocida")
    if abs(valor - round(valor)) < 0.05:
        return _("%d GB") % round(valor)
    return _("%s GB") % ("%.1f" % valor).replace(".", ",")


#: Lo que Windows enumera como tarjeta gráfica sin serlo: monitores virtuales,
#: escritorio remoto, capturadoras.  Salen antes que la tarjeta de verdad más
#: veces de las que uno creería —quien tenga tres monitores virtuales verá tres
#: de estos primero—, así que quedarse con la primera de la lista es quedarse
#: con un monitor de mentira.
GRAFICAS_FALSAS = (
    "virtual", "remote", "parsec", "displaylink", "spacedesk", "mirror",
    "citrix", "vmware", "basic display", "basic render", "oray", "sunshine",
)

#: Marcas por las que se reconoce una tarjeta dedicada.  Se comprueban antes
#: que las integradas porque hay nombres que están en las dos listas: una Intel
#: Arc lleva la marca de Intel y no es la gráfica del procesador.
GRAFICAS_DEDICADAS = (
    "geforce", "rtx", "gtx", "quadro", "tesla", "titan", "radeon rx",
    "radeon pro", "firepro", "instinct", "arc a", "arc b",
)

#: Marcas de las gráficas que van dentro del procesador.  Funcionar, funcionan,
#: pero suelen ser más lentas que el propio procesador para esto y se quedan
#: sin memoria a mitad, así que no cuentan como «tener tarjeta».
GRAFICAS_INTEGRADAS = (
    "intel", "uhd graphics", "hd graphics", "iris", "radeon graphics",
    "vega 3", "vega 6", "vega 7", "vega 8", "vega 10", "vega 11",
)

#: Dónde guarda Windows la información de las tarjetas.  Este identificador es
#: la clase de dispositivo «adaptadores de pantalla» y no cambia nunca.
CLASE_GRAFICAS = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"


def _limpiar(nombre: str) -> str:
    """Deja el nombre de una tarjeta como para poder compararlo.

    Los fabricantes los escriben con símbolos de marca por medio —«AMD
    Radeon(TM) Graphics», «Intel(R) Iris(R) Xe Graphics»—, y ese «(TM)» basta
    para que «radeon graphics» no encuentre a la Radeon integrada y se la
    tome por una tarjeta aparte.
    """
    bajo = nombre.lower()
    for simbolo in ("(tm)", "(r)", "(c)", "®", "™"):
        bajo = bajo.replace(simbolo, " ")
    return " ".join(bajo.split())


def _es_falsa(nombre: str) -> bool:
    """Si lo que Windows llama tarjeta no es una tarjeta."""
    if not nombre.strip():
        return True
    limpio = _limpiar(nombre)
    return any(marca in limpio for marca in GRAFICAS_FALSAS)


def _es_integrada(nombre: str) -> bool:
    """Si la gráfica es la que viene dentro del procesador."""
    limpio = _limpiar(nombre)
    if any(marca in limpio for marca in GRAFICAS_DEDICADAS):
        return False
    return any(marca in limpio for marca in GRAFICAS_INTEGRADAS)


def _graficas_del_registro() -> list[tuple[str, float]]:
    """Las tarjetas según el registro de Windows, con su memoria de verdad.

    Es la fuente buena, por dos motivos.  La memoria está en un valor de 64
    bits (``qwMemorySize``), mientras que la que da WMI es de 32 y se queda
    clavada en 4 GB: una tarjeta de doce gigas se ve como de cuatro, y con eso
    el programa acaba desaconsejando modelos que le cabrían de sobra.  Y los
    monitores virtuales se delatan solos, porque no tienen memoria ninguna.
    """
    if os.name != "nt":
        return []
    encontradas: list[tuple[str, float]] = []
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, CLASE_GRAFICAS) as clase:
            for indice in range(64):
                try:
                    rama = winreg.EnumKey(clase, indice)
                except OSError:
                    break
                if not rama.isdigit():
                    continue
                try:
                    with winreg.OpenKey(clase, rama) as tarjeta:
                        def dato(nombre):
                            try:
                                return winreg.QueryValueEx(tarjeta, nombre)[0]
                            except OSError:
                                return None

                        descripcion = dato("DriverDesc") or ""
                        memoria = dato("HardwareInformation.qwMemorySize")
                except OSError:
                    continue
                if descripcion:
                    encontradas.append(
                        (descripcion, float(memoria or 0) / (1024 ** 3)))
    except Exception:
        log.debug("No se ha podido leer el registro de tarjetas", exc_info=True)
    return encontradas


def _graficas_nvidia() -> list[tuple[str, float]]:
    """Lo que dice «nvidia-smi», que para las suyas es quien mejor lo sabe."""
    try:
        salida = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, errors="replace", timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        return []                                   # no hay controlador NVIDIA
    encontradas = []
    for linea in (salida.stdout or "").splitlines():
        partes = [trozo.strip() for trozo in linea.split(",")]
        if len(partes) < 2 or not partes[0]:
            continue
        try:
            megas = float(partes[1])
        except ValueError:
            megas = 0.0
        encontradas.append((partes[0], megas / 1024))
    return encontradas


def _graficas_del_sistema() -> list[tuple[str, float]]:
    """Último recurso: preguntárselo a Windows.

    Se usa PowerShell y ``Get-CimInstance``, no ``wmic``: **wmic ya no viene
    con Windows 11**, de modo que la orden falla y la detección entera se
    quedaba sin ver nada —que es justo lo que pasaba—.

    La memoria se devuelve a cero a propósito.  La que da aquí Windows se corta
    en 4 GB, y más vale no saberla que creerse una cifra falsa: sin dato se
    usa la tarjeta igualmente, con el dato falso se le acabaría diciendo a
    alguien que su tarjeta de doce gigas no da para un modelo de cinco.
    """
    if os.name != "nt":
        return []
    try:
        salida = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Get-CimInstance Win32_VideoController | "
             "ForEach-Object { $_.Name }"],
            capture_output=True, text=True, errors="replace", timeout=25,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        log.debug("No se ha podido preguntar por las tarjetas", exc_info=True)
        return []
    return [(linea.strip(), 0.0) for linea in (salida.stdout or "").splitlines()
            if linea.strip()]


def graficas() -> list[tuple[str, float]]:
    """Las tarjetas de verdad del equipo, con su memoria en gigas.

    La memoria vale ``0.0`` cuando no se ha podido averiguar, que no es lo
    mismo que «no tiene».
    """
    encontradas = [(nombre, vram) for nombre, vram in _graficas_del_registro()
                   if not _es_falsa(nombre)]

    # Para las NVIDIA manda «nvidia-smi»: si el registro no traía la memoria,
    # la pone; y si la tarjeta no salió, la añade.
    for nombre, vram in _graficas_nvidia():
        for indice, (tenia, suya) in enumerate(encontradas):
            if tenia.lower() == nombre.lower():
                encontradas[indice] = (tenia, suya or vram)
                break
        else:
            encontradas.append((nombre, vram))

    if not encontradas:
        encontradas = [(nombre, vram) for nombre, vram in _graficas_del_sistema()
                       if not _es_falsa(nombre)]
    return encontradas


def equipo() -> Equipo:
    """Mira cuánta memoria y qué tarjeta gráfica hay.

    Se pregunta al sistema y no se estima: proponerle a alguien un modelo de
    siete gigas en un equipo de cuatro es hacerle perder media hora de descarga
    para que al final no arranque.
    """
    total = libre = 0.0
    if os.name == "nt":
        try:
            import ctypes

            class _Memoria(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong),
                            ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            datos = _Memoria()
            datos.dwLength = ctypes.sizeof(_Memoria)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(datos)):
                total = datos.ullTotalPhys / (1024 ** 3)
                libre = datos.ullAvailPhys / (1024 ** 3)
        except Exception:
            log.debug("No se ha podido leer la memoria del equipo", exc_info=True)

    nombre, vram, dedicada = "", 0.0, False
    for candidata, memoria in graficas():
        suya = not _es_integrada(candidata)
        # Una dedicada gana siempre a una integrada, tenga la memoria que
        # tenga; entre dos del mismo tipo, la que más memoria declare.
        if not nombre or (suya, memoria) > (dedicada, vram):
            nombre, vram, dedicada = candidata, memoria, suya
    return Equipo(round(total, 1), round(libre, 1), nombre, round(vram, 1), dedicada)
