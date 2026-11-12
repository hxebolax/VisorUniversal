# -*- coding: utf-8 -*-
"""Comprobación e instalación de versiones nuevas.

El programa consulta un ``version.json`` publicado en la dirección que haya en
:data:`version.URL_ACTUALIZACIONES`, compara la versión que anuncia con la
propia y, si hay una más nueva, descarga el ZIP correspondiente y lo aplica.

El manifiesto tiene esta pinta::

    {
      "version": "1.2.0",
      "sha256": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
      "size": 48213904,
      "notas": "Corrige el reconocimiento de tablas.",
      "firma_ed25519": "base64..."
    }

Solo ``version`` es obligatorio.  El ``sha256`` sirve para comprobar que la
descarga es exactamente el paquete publicado —una descarga a medias o
manipulada no se instala— y la firma, si se configura una clave pública en
:data:`version.CLAVE_PUBLICA`, para comprobar que el manifiesto lo escribió
quien dice, y no quien haya podido hacerse con el servidor.

La instalación es **en caliente**: se deja preparado un ``.bat`` que espera a
que este proceso muera, copia los archivos nuevos encima con ``robocopy`` y
vuelve a abrir el programa.  Se usa ``robocopy`` y no un borrado previo porque
así la carpeta ``data`` —ajustes, marcadores, caché— se queda intacta: solo se
escribe lo que trae el paquete.

Nada de esto funciona ejecutando desde el código fuente: no hay un paquete
equivalente que copiar.  Ahí se avisa de que hay versión nueva y se deja al
usuario descargarla como siempre.

De dónde se descarga
--------------------

Cada versión se publica en **dos sitios** con los mismos dos archivos: el
servidor del autor (:data:`version.URL_ACTUALIZACIONES`) y una *release* de
GitHub (:data:`version.REPOSITORIO_GITHUB`).  En Opciones se elige dónde mirar
(ajuste ``actualizaciones_origen``):

* ``servidor``: solo el servidor.
* ``github``: solo GitHub.
* ``ambos`` (de fábrica): se pregunta a los dos, se queda la versión más nueva
  que anuncie cualquiera, y si la descarga falla en uno se intenta en el otro.
  Así un servidor caído no deja a nadie sin actualizaciones.
* ``personalizada``: una dirección que pone el usuario
  (``actualizaciones_url``), con la misma forma que la del servidor —una
  carpeta con ``version.json`` y el ZIP— o la de un repositorio de GitHub.

Venga de donde venga, el paquete pasa por las **mismas comprobaciones**: el
``sha256`` y la firma Ed25519.  Una dirección personalizada sirve para un
espejo, no para instalar paquetes ajenos: sin la clave privada del autor, la
firma no cuadra y no se instala nada.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable, Optional

from version import (CLAVE_PUBLICA, NOMBRE_ARCHIVO, REPOSITORIO_GITHUB,
                     URL_ACTUALIZACIONES, VERSION)

from . import rutas
from .idioma import _
from .registro import obtener_registro

log = obtener_registro(__name__)

#: Cabeceras de las peticiones.  Identificarse permite al servidor distinguir
#: las descargas del programa de las de un navegador.
CABECERAS = {"User-Agent": "%s-Actualizador" % NOMBRE_ARCHIVO}

#: Segundos que se espera al servidor antes de darlo por inalcanzable.  Corto a
#: propósito: la comprobación al arrancar no puede retrasar la apertura.
ESPERA = 20

#: Segundos de espera de la descarga, que es larga y no debe cortarse sola.
ESPERA_DESCARGA = 120

#: Nombres de los archivos temporales que se crean junto al programa mientras
#: dura la actualización.  Empiezan por guion bajo para que queden juntos y se
#: reconozcan de un vistazo si algo sale mal y sobreviven.
NOMBRE_ZIP = "_actualizacion.zip"
NOMBRE_TEMP = "_actualizacion_temp"
NOMBRE_SCRIPT = "_actualizar.bat"

#: Límites de la descompresión.  El sha256 protege el transporte, pero si el
#: servidor mismo se viera comprometido el ZIP y su hash vendrían los dos
#: manipulados; estos topes acotan el daño de un paquete que se expanda sin
#: fin («zip bomb»).
MAX_ARCHIVOS = 30000
MAX_POR_ARCHIVO = 1 * 1024 ** 3
MAX_TOTAL = 3 * 1024 ** 3


#: De dónde se pueden buscar las actualizaciones, con el nombre que se enseña
#: en Opciones.  El primero es el de fábrica.
ORIGENES = (
    ("ambos", _("El servidor del autor y GitHub (el que tenga la más nueva)")),
    ("servidor", _("Solo el servidor del autor")),
    ("github", _("Solo GitHub")),
    ("personalizada", _("Una dirección personalizada")),
)

#: Origen que se usa si lo guardado no vale.
ORIGEN_POR_OMISION = "ambos"

_RE_GITHUB = re.compile(r"^(?:https?://)?(?:www\.)?github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$",
                        re.I)


class Fuente:
    """Un sitio donde mirar si hay versión nueva y de donde descargarla.

    :param nombre: Cómo se llama al contarlo («GitHub», «el servidor»).
    :param manifiesto: Dirección del ``version.json``.
    :param paquete: Plantilla de la dirección del ZIP, con ``{version}`` y
                    ``{archivo}`` por rellenar.
    """

    __slots__ = ("nombre", "manifiesto", "paquete")

    def __init__(self, nombre: str, manifiesto: str, paquete: str) -> None:
        self.nombre = nombre
        self.manifiesto = manifiesto
        self.paquete = paquete

    def url_del_paquete(self, version: str, archivo: str = "") -> str:
        """Dirección del ZIP de una versión."""
        archivo = archivo or "%s_v%s.zip" % (NOMBRE_ARCHIVO, version)
        return self.paquete.format(version=version, archivo=archivo)

    def __repr__(self) -> str:                       # pragma: no cover
        return "Fuente(%r, %r)" % (self.nombre, self.manifiesto)


def fuente_carpeta(url: str, nombre: str) -> Optional[Fuente]:
    """Fuente de una carpeta web con ``version.json`` y el ZIP dentro."""
    base = (url or "").strip().rstrip("/")
    if not base:
        return None
    return Fuente(nombre, base + "/version.json", base + "/{archivo}")


def fuente_github(repositorio: str) -> Optional[Fuente]:
    """Fuente de las *releases* de un repositorio de GitHub.

    No se usa la API de GitHub sino las direcciones de descarga directa, que no
    tienen límite de consultas: ``releases/latest/download/version.json`` lleva
    siempre al aviso de la última versión publicada, y el ZIP está en la
    *release* de su etiqueta, ``v<versión>``.
    """
    repositorio = (repositorio or "").strip().strip("/")
    if repositorio.count("/") != 1:
        return None
    base = "https://github.com/%s/releases" % repositorio
    return Fuente("GitHub", base + "/latest/download/version.json",
                  base + "/download/v{version}/{archivo}")


def fuente_personalizada(url: str) -> Optional[Fuente]:
    """Fuente de una dirección escrita por el usuario.

    Si es la de un repositorio de GitHub («https://github.com/alguien/algo») se
    trata como tal; si no, como una carpeta con los dos archivos.
    """
    url = (url or "").strip()
    if not url:
        return None
    coincide = _RE_GITHUB.match(url)
    if coincide:
        fuente = fuente_github("%s/%s" % (coincide.group(1), coincide.group(2)))
        if fuente is not None:
            fuente.nombre = _("la dirección personalizada")
        return fuente
    if not url.lower().startswith(("https://", "http://")):
        url = "https://" + url
    return fuente_carpeta(url, _("la dirección personalizada"))


def fuentes(origen: Optional[str] = None, url_propia: str = "") -> list[Fuente]:
    """Las fuentes donde mirar, por orden de preferencia, según lo elegido.

    :param origen: Una de las claves de :data:`ORIGENES`; si no vale, la de
                   fábrica.
    :param url_propia: La dirección personalizada, si el origen es ese.
    """
    claves = [clave for clave, _nombre in ORIGENES]
    if origen not in claves:
        origen = ORIGEN_POR_OMISION
    servidor = fuente_carpeta(URL_ACTUALIZACIONES, _("el servidor del autor"))
    github = fuente_github(REPOSITORIO_GITHUB)
    if origen == "servidor":
        salida = [servidor]
    elif origen == "github":
        salida = [github]
    elif origen == "personalizada":
        salida = [fuente_personalizada(url_propia)]
    else:
        salida = [servidor, github]
    return [fuente for fuente in salida if fuente is not None]


def de_configuracion(configuracion) -> tuple[str, str]:
    """Lee ``(origen, dirección personalizada)`` de la configuración."""
    if configuracion is None:
        return ORIGEN_POR_OMISION, ""
    origen = str(configuracion.obtener("actualizaciones_origen", ORIGEN_POR_OMISION)
                 or ORIGEN_POR_OMISION)
    url = str(configuracion.obtener("actualizaciones_url", "") or "")
    return origen, url


def activadas(origen: Optional[str] = None, url_propia: str = "") -> bool:
    """Indica si hay algún sitio donde buscar actualizaciones.

    Sin ninguno no se pregunta a nadie: un programa sin fuente de
    actualizaciones no debe hacer como que las busca.
    """
    return bool(fuentes(origen, url_propia))


def _numeros(version: str) -> tuple[int, ...]:
    """Convierte ``"1.2.10"`` en ``(1, 2, 10)`` para poder comparar.

    Se comparan números y no cadenas porque ``"1.2.10" < "1.2.9"`` como texto,
    que es justo lo contrario de lo que hace falta.  Los sufijos («1.2.0-beta»)
    se ignoran.
    """
    partes = re.findall(r"\d+", str(version or ""))
    return tuple(int(parte) for parte in partes) if partes else (0,)


def es_mas_nueva(remota: str, local: str = VERSION) -> bool:
    """Indica si la versión del servidor es posterior a la instalada."""
    if not remota:
        return False
    try:
        return _numeros(remota) > _numeros(local)
    except Exception:
        return False


def _leer_manifiesto(fuente: Fuente, espera: int) -> Optional[dict[str, Any]]:
    """Descarga y lee el ``version.json`` de una fuente, o ``None``."""
    try:
        peticion = urllib.request.Request(fuente.manifiesto, headers=CABECERAS)
        with urllib.request.urlopen(peticion, timeout=espera) as respuesta:
            # Con BOM o sin él: un manifiesto guardado con el Bloc de notas lo lleva.
            datos = json.loads(respuesta.read().decode("utf-8-sig"))
        if not isinstance(datos, dict) or not str(datos.get("version", "")).strip():
            log.warning("El manifiesto de %s no tiene versión", fuente.nombre)
            return None
        return datos
    except Exception as error:
        log.debug("No se ha podido consultar %s: %s", fuente.manifiesto, error)
        return None


def consultar(espera: int = ESPERA, origen: Optional[str] = None,
              url_propia: str = "") -> Optional[dict[str, Any]]:
    """Pregunta a las fuentes elegidas qué versión hay publicada.

    Con varias fuentes se pregunta a todas y se queda **la versión más nueva**;
    si dos anuncian la misma, manda la primera de la lista.  El manifiesto que
    se devuelve lleva además dos claves propias, que no vienen del servidor:

    * ``_paquetes``: las direcciones del ZIP, por orden, de **todas** las
      fuentes que anuncian esa misma versión con ese mismo ``sha256``.  Si la
      descarga falla en una, se intenta en la siguiente.
    * ``_origen``: el nombre de la fuente de la que sale, para el registro.

    :return: El manifiesto como diccionario, o ``None`` si no se ha podido
             consultar ninguna (sin conexión, servidores caídos, respuesta
             ilegible).  No lanza excepciones a propósito: no poder comprobar
             si hay versión nueva no es un error que deba interrumpir nada.
    """
    lista = fuentes(origen, url_propia)
    if not lista:
        return None
    # A la vez y no una detrás de otra: con un servidor caído, esperar a que
    # se agote su plazo antes de preguntar a GitHub doblaría la espera.
    if len(lista) == 1:
        leidos = [_leer_manifiesto(lista[0], espera)]
    else:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=len(lista)) as grupo:
            leidos = list(grupo.map(lambda f: _leer_manifiesto(f, espera), lista))
    respuestas: list[tuple[Fuente, dict[str, Any]]] = [
        (fuente, datos) for fuente, datos in zip(lista, leidos) if datos is not None]
    if not respuestas:
        return None
    mejor_fuente, mejor = respuestas[0]
    for fuente, datos in respuestas[1:]:
        if _numeros(datos.get("version", "")) > _numeros(mejor.get("version", "")):
            mejor_fuente, mejor = fuente, datos
    version = str(mejor.get("version", "")).strip()
    resumen = str(mejor.get("sha256", "")).strip().lower()
    archivo = str(mejor.get("file", "") or "").strip()
    paquetes = [mejor_fuente.url_del_paquete(version, archivo)]
    for fuente, datos in respuestas:
        if fuente is mejor_fuente:
            continue
        # Solo de otra fuente si es exactamente el mismo paquete: misma versión
        # y mismo resumen.  Si no, la otra descarga no pasaría la comprobación.
        if (str(datos.get("version", "")).strip() == version
                and str(datos.get("sha256", "")).strip().lower() == resumen):
            paquetes.append(fuente.url_del_paquete(version, archivo))
    salida = dict(mejor)
    salida["_paquetes"] = paquetes
    salida["_origen"] = mejor_fuente.nombre
    log.debug("Versión publicada %s, según %s", version, mejor_fuente.nombre)
    return salida


def version_publicada(espera: int = ESPERA, origen: Optional[str] = None,
                      url_propia: str = "") -> str:
    """Versión anunciada, o cadena vacía si no se ha podido consultar."""
    datos = consultar(espera, origen, url_propia)
    return str((datos or {}).get("version", "")).strip()


def url_del_paquete(version: str, origen: Optional[str] = None, url_propia: str = "") -> str:
    """Dirección del ZIP de una versión en la primera fuente elegida."""
    lista = fuentes(origen, url_propia)
    return lista[0].url_del_paquete(version) if lista else ""


def se_puede_instalar() -> bool:
    """Indica si esta copia se puede actualizar sola.

    Solo la versión compilada: desde el código fuente no hay un paquete
    equivalente que copiar encima, y sobrescribir el código a medias dejaría
    una instalación rota.
    """
    return rutas.esta_congelado()


# --- comprobaciones de seguridad -------------------------------------------

def _sha256(ruta: Path) -> str:
    """Calcula el resumen de un archivo leyéndolo por trozos.

    Por trozos y no de una vez porque el paquete pesa decenas de megas y
    cargarlo entero en memoria para resumirlo no aporta nada.
    """
    resumen = hashlib.sha256()
    with open(ruta, "rb") as archivo:
        for trozo in iter(lambda: archivo.read(1024 * 1024), b""):
            resumen.update(trozo)
    return resumen.hexdigest()


def comprobar_paquete(ruta_zip: Path, esperado: str) -> None:
    """Comprueba que el ZIP descargado es el que publica el servidor.

    :raises ValueError: Si el resumen no coincide, en cuyo caso **no debe
                        instalarse**: o la descarga se ha corrompido o el
                        archivo no es el que dice ser.
    """
    esperado = (esperado or "").strip().lower()
    if not esperado:
        log.warning("El servidor no publica sha256: no se puede comprobar el paquete")
        return
    real = _sha256(ruta_zip)
    if real != esperado:
        raise ValueError(_(
            "El paquete descargado no coincide con el publicado, así que no se "
            "instalará. Vuelve a intentarlo más tarde."))
    log.info("Paquete de actualización comprobado (sha256 correcto)")


def comprobar_firma(datos: dict[str, Any]) -> None:
    """Comprueba la firma Ed25519 del manifiesto, si hay clave configurada.

    Se firma el mensaje ``"<version>:<sha256>"``.  Sin clave configurada esto
    no hace nada; con clave, un manifiesto sin firma o con una firma que no
    cuadra se rechaza.

    :raises ValueError: Si la firma falta o no es válida.
    """
    if not CLAVE_PUBLICA:
        return
    import base64

    firma = str((datos or {}).get("firma_ed25519", "")).strip()
    if not firma:
        raise ValueError(_("El aviso de versión no viene firmado, así que no se instalará."))
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        clave = Ed25519PublicKey.from_public_bytes(bytes.fromhex(CLAVE_PUBLICA))
        mensaje = ("%s:%s" % (str(datos.get("version", "")).strip(),
                              str(datos.get("sha256", "")).strip().lower())).encode("utf-8")
        clave.verify(base64.b64decode(firma), mensaje)
    except ValueError:
        raise
    except Exception:
        raise ValueError(_("La firma del aviso de versión no es válida, así que no se instalará."))
    log.info("Manifiesto de actualización comprobado (firma correcta)")


# --- descarga y descompresión ----------------------------------------------

def descargar(version: str, destino: Path,
              progreso: Optional[Callable[[int, int], None]] = None,
              cancelado: Optional[Callable[[], bool]] = None,
              espera: int = ESPERA_DESCARGA,
              direcciones: Optional[list[str]] = None) -> Path:
    """Descarga el paquete de una versión, avisando de cómo va.

    :param progreso: Se llama con ``(bytes_descargados, bytes_totales)``.  Los
                     totales valen ``0`` si el servidor no los declara.
    :param cancelado: Se consulta a cada trozo; devolviendo ``True`` se aborta.
    :param direcciones: De dónde descargarlo, por orden: lo que trae el
                        manifiesto en ``_paquetes``.  Si falla una se intenta
                        la siguiente; sin ellas, la primera fuente de fábrica.
    """
    lista = [d for d in (direcciones or []) if d] or [url_del_paquete(version)]
    ultimo_error: Optional[BaseException] = None
    for numero, direccion in enumerate(lista):
        if cancelado is not None and cancelado():
            raise InterruptedError(_("Descarga cancelada."))
        try:
            return _descargar_de(direccion, destino, progreso, cancelado, espera)
        except InterruptedError:
            raise
        except Exception as error:
            ultimo_error = error
            if numero + 1 < len(lista):
                log.warning("Falló la descarga de %s (%s); se intenta en otro sitio",
                            direccion, error)
    assert ultimo_error is not None
    raise ultimo_error


def _descargar_de(direccion: str, destino: Path,
                  progreso: Optional[Callable[[int, int], None]],
                  cancelado: Optional[Callable[[], bool]], espera: int) -> Path:
    """Descarga un ZIP de una dirección concreta."""
    log.info("Descargando la actualización: %s", direccion)
    peticion = urllib.request.Request(direccion, headers=CABECERAS)
    respuesta = urllib.request.urlopen(peticion, timeout=espera)
    try:
        total = int(respuesta.headers.get("Content-Length", 0) or 0)
        leido = 0
        # A disco y no a memoria: el paquete pesa lo que pesa el programa entero.
        with open(destino, "wb") as archivo:
            while True:
                if cancelado is not None and cancelado():
                    raise InterruptedError(_("Descarga cancelada."))
                trozo = respuesta.read(65536)
                if not trozo:
                    break
                archivo.write(trozo)
                leido += len(trozo)
                if progreso is not None:
                    progreso(leido, total)
    finally:
        respuesta.close()
    if total and leido < total:
        # Una conexión cortada a medias no da error: simplemente se acaba.
        # Hay que decirlo aquí para poder intentarlo en otra fuente.
        raise IOError(_("La descarga se ha cortado antes de terminar."))
    return destino


def _prefijo_comun(nombres: list[str]) -> str:
    """Carpeta raíz que envuelve al paquete, si es que lo hace.

    Los ZIP suelen venir con todo dentro de una carpeta con el nombre del
    programa; hay que quitarla para que los archivos caigan donde toca y no en
    una carpeta anidada.
    """
    if not nombres:
        return ""
    primera = nombres[0].split("/")[0]
    if primera and all(n == primera or n.startswith(primera + "/") for n in nombres):
        return primera + "/"
    return ""


def descomprimir(ruta_zip: Path, destino: Path,
                 progreso: Optional[Callable[[int, int], None]] = None) -> None:
    """Extrae el paquete a una carpeta temporal, quitándole la carpeta raíz.

    Se comprueba archivo por archivo que ninguno escriba **fuera** de la
    carpeta de destino: un ZIP puede traer nombres con ``..`` o rutas absolutas
    y colocar archivos donde le parezca (el fallo conocido como *zip slip*).
    """
    if destino.exists():
        shutil.rmtree(destino, ignore_errors=True)
    destino.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(ruta_zip) as paquete:
        fichas = paquete.infolist()
        if len(fichas) > MAX_ARCHIVOS:
            raise ValueError(_("El paquete trae demasiados archivos, así que no se instalará."))
        prefijo = _prefijo_comun([ficha.filename for ficha in fichas])
        total = len(fichas) or 1
        raiz = os.path.realpath(destino)
        escrito_total = 0

        for numero, ficha in enumerate(fichas):
            nombre = ficha.filename
            relativo = nombre[len(prefijo):] if prefijo and nombre.startswith(prefijo) else nombre
            if relativo:
                salida = os.path.realpath(os.path.join(destino, relativo))
                # commonpath y no startswith: «C:\a\bc» empieza por «C:\a\b»
                # sin estar dentro, y esa comparación ingenua dejaría escapar
                # justo lo que se quiere impedir.
                if os.path.commonpath([raiz, salida]) != raiz:
                    log.warning("Archivo del paquete fuera de la carpeta (omitido): %s", nombre)
                    if progreso is not None:
                        progreso(numero + 1, total)
                    continue
                if nombre.endswith("/"):
                    os.makedirs(salida, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(salida), exist_ok=True)
                    escrito = 0
                    with paquete.open(ficha) as origen, open(salida, "wb") as archivo:
                        while True:
                            bloque = origen.read(1024 * 1024)
                            if not bloque:
                                break
                            escrito += len(bloque)
                            escrito_total += len(bloque)
                            if escrito > MAX_POR_ARCHIVO or escrito_total > MAX_TOTAL:
                                raise ValueError(_(
                                    "El paquete ocupa mucho más de lo razonable al "
                                    "descomprimirlo, así que no se instalará."))
                            archivo.write(bloque)
            if progreso is not None:
                progreso(numero + 1, total)

    # Antes de tocar nada, comprobar que lo extraído se parece a este programa.
    # Sin esto, un ZIP vacío o ajeno se copiaría encima y dejaría la
    # instalación inservible sin que nadie se hubiera dado cuenta.
    esperados = ("%s.exe" % NOMBRE_ARCHIVO, "main.py")
    if not any((destino / nombre).exists() for nombre in esperados):
        raise ValueError(_("El paquete descargado no parece este programa, así que no se aplicará."))


# --- aplicación en caliente -------------------------------------------------

def _orden_de_relanzar() -> str:
    """Orden ``start`` que vuelve a abrir el programa al terminar."""
    if rutas.esta_congelado():
        return 'start "" "%s"' % sys.executable
    guion = os.path.abspath(sys.argv[0])
    return 'start "" "%s" "%s"' % (sys.executable, guion)


def crear_guion(base: Path, temporal: Path, ruta_zip: Path) -> Path:
    """Escribe el ``.bat`` que aplica la actualización y relanza el programa.

    Es un ``.bat`` de ``cmd`` y no un guion de PowerShell porque, lanzado sin
    ventana desde un programa compilado, PowerShell no arranca bien: hereda
    unos descriptores estándar que no valen y muere sin hacer nada.  Con
    ``cmd`` funciona en las dos formas de ejecutar el programa.

    Lo que hace, por orden: esperar a que este proceso termine (hasta treinta
    segundos, y si no se cierra, cerrarlo), copiar lo nuevo encima con
    ``robocopy``, limpiar los temporales, volver a abrir el programa y
    borrarse a sí mismo.
    """
    identificador = os.getpid()
    guion = base / NOMBRE_SCRIPT
    aviso_error = base / "_actualizacion_error.log"
    contenido = (
        "@echo off\r\n"
        "chcp 65001 >nul 2>&1\r\n"
        "set /a intento=0\r\n"
        ":esperar\r\n"
        'tasklist /FI "PID eq %(pid)d" 2>NUL | find /I "%(pid)d" >NUL\r\n'
        "if not errorlevel 1 (\r\n"
        '    set /a "intento+=1"\r\n'
        "    if %%intento%% gtr 30 (\r\n"
        "        taskkill /F /PID %(pid)d >nul 2>&1\r\n"
        "    ) else (\r\n"
        "        timeout /t 1 /nobreak >nul\r\n"
        "        goto esperar\r\n"
        "    )\r\n"
        ")\r\n"
        'robocopy "%(temporal)s" "%(base)s" /E /IS /IT /R:3 /W:1 /NFL /NDL /NJH /NJS >nul 2>&1\r\n'
        # robocopy devuelve 8 o más cuando no ha podido copiar algo.  En ese
        # caso se conservan los temporales, para poder reintentar o mirar qué
        # ha pasado, y queda constancia en un archivo.
        "if errorlevel 8 (\r\n"
        '    echo robocopy fallo con codigo %%errorlevel%% > "%(aviso)s"\r\n'
        ") else (\r\n"
        '    rmdir /s /q "%(temporal)s" >nul 2>&1\r\n'
        '    del /q "%(zip)s" >nul 2>&1\r\n'
        ")\r\n"
        "timeout /t 1 /nobreak >nul\r\n"
        "%(relanzar)s\r\n"
        'del "%%~f0" >nul 2>&1\r\n'
    ) % {
        "pid": identificador,
        "temporal": temporal,
        "base": base,
        "zip": ruta_zip,
        "aviso": aviso_error,
        "relanzar": _orden_de_relanzar(),
    }
    guion.write_text(contenido, encoding="utf-8")
    return guion


def lanzar_guion(ruta_guion: Path) -> None:
    """Arranca el guion de actualización desacoplado de este proceso.

    Sin ventana y sin entrada ni salida heredadas: el guion tiene que
    sobrevivir a la muerte del programa, que es precisamente lo que espera
    para empezar a copiar.
    """
    SIN_VENTANA = 0x08000000
    subprocess.Popen(
        ["cmd", "/c", str(ruta_guion)],
        creationflags=SIN_VENTANA,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        close_fds=True,
    )


def limpiar_restos(base: Optional[Path] = None) -> None:
    """Borra lo que haya podido quedar de una actualización anterior.

    Se llama al arrancar.  Si la copia salió bien, el propio guion se encarga
    de limpiar; esto es para cuando algo se torció por el camino y quedaron el
    ZIP o la carpeta temporal ocupando sitio.
    """
    base = base or Path(rutas.directorio_base())
    for nombre in (NOMBRE_ZIP, NOMBRE_SCRIPT):
        try:
            (base / nombre).unlink(missing_ok=True)
        except OSError:
            pass
    try:
        temporal = base / NOMBRE_TEMP
        if temporal.is_dir():
            shutil.rmtree(temporal, ignore_errors=True)
    except OSError:
        pass


def error_de_la_ultima() -> str:
    """Mensaje de la última actualización que falló al copiar, si lo hay.

    Lo escribe el guion cuando ``robocopy`` no puede con algún archivo, y se
    consulta al arrancar para poder decirlo en vez de dejar al usuario con una
    versión que creía actualizada y no lo está.
    """
    aviso = Path(rutas.directorio_base()) / "_actualizacion_error.log"
    try:
        if aviso.is_file():
            texto = aviso.read_text(encoding="utf-8", errors="replace").strip()
            aviso.unlink(missing_ok=True)
            return texto
    except OSError:
        pass
    return ""
