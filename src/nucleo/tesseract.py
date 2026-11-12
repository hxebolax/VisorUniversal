# -*- coding: utf-8 -*-
"""Tesseract portable: dónde está, qué idiomas tiene y cómo añadirle más.

Tesseract es el motor de reconocimiento óptico libre de referencia, y en este
programa es el que mejor lee las páginas difíciles: folletos, documentos a
varias columnas y tablas.  Pero pedirle a alguien que instale un programa
aparte para poder leer un PDF escaneado es pedirle demasiado, sobre todo a
quien no ve la pantalla y tiene que pelearse con un instalador ajeno.

Por eso aquí va **portable**: el ejecutable y sus bibliotecas viven en
``data/tesseract`` y los idiomas en ``data/tesseract/tessdata``.  No hay nada
que instalar, nada que tocar en el registro de Windows y nada que dependa de
que el equipo tenga ya Tesseract.  Se copia la carpeta y funciona.

Los idiomas
-----------

Cada idioma es un archivo ``.traineddata`` suelto, así que se pueden añadir y
quitar en caliente sin tocar nada más.  Los publica el propio proyecto
Tesseract en GitHub, en dos colecciones:

* ``tessdata_fast``: rápida y pequeña (uno o dos megas por idioma).  Es la que
  se ofrece de entrada, porque la diferencia de acierto es pequeña y la de
  velocidad no.
* ``tessdata_best``: más precisa y bastante más lenta y grande.  Vale la pena
  para un documento difícil que se vaya a leer entero.

La descarga se hace con la biblioteca estándar, sin depender de nada.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from . import rutas
from .idioma import _
from .registro import obtener_registro, registrar_excepcion

log = obtener_registro(__name__)

#: Dónde se publican los idiomas.  La colección «fast» es la de partida.
URL_FAST = "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/%s.traineddata"
URL_BEST = "https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main/%s.traineddata"

#: Segundos que se espera a la descarga de un idioma.
ESPERA_DESCARGA = 120

#: Nombre de cada idioma de Tesseract.  Sus códigos son de tres letras
#: (ISO 639-2) y no coinciden con los de dos que usa el resto del programa, así
#: que hace falta una tabla propia.  Están los que se piden de verdad para leer
#: documentos; la lista completa pasa de cien y no cabe en una ventana.
IDIOMAS = {
    "spa": "Español", "spa_old": "Español (ortografía antigua)",
    "cat": "Català", "eus": "Euskara", "glg": "Galego",
    "eng": "English", "fra": "Français", "por": "Português",
    "ita": "Italiano", "deu": "Deutsch", "nld": "Nederlands",
    "ces": "Čeština", "pol": "Polski", "ron": "Română", "rus": "Русский",
    "ukr": "Українська", "ell": "Ελληνικά", "tur": "Türkçe",
    "ara": "العربية", "heb": "עברית", "hin": "हिन्दी",
    "jpn": "日本語", "kor": "한국어", "chi_sim": "简体中文", "chi_tra": "繁體中文",
    "swe": "Svenska", "dan": "Dansk", "nor": "Norsk", "fin": "Suomi",
    "hun": "Magyar", "bul": "Български", "hrv": "Hrvatski", "srp": "Српски",
    "slk": "Slovenčina", "slv": "Slovenščina", "lit": "Lietuvių",
    "lav": "Latviešu", "est": "Eesti", "vie": "Tiếng Việt", "tha": "ไทย",
    "ind": "Bahasa Indonesia", "msa": "Bahasa Melayu", "afr": "Afrikaans",
    "lat": "Latina", "grc": "Ἑλληνικὴ (antiguo)",
    "osd": _("Detección de orientación y escritura"),
    "equ": _("Fórmulas matemáticas"),
}

#: Idiomas que conviene tener de entrada en una instalación en español.
BASICOS = ("spa", "cat", "eng", "glg", "eus", "osd")

#: Archivos de «tessdata» que **no son idiomas de texto** y que no deben ir en
#: la lista con la que se reconoce.  ``osd`` sirve para detectar la orientación
#: de la página y ``equ`` para las fórmulas; metidos entre los idiomas de
#: lectura solo hacen más lento el reconocimiento sin aportar una letra.
NO_SON_IDIOMAS = ("osd", "equ")


def carpeta() -> Path:
    """Carpeta del Tesseract portable, dentro de los datos del programa."""
    return rutas.directorio_datos() / "tesseract"


def carpeta_idiomas() -> Path:
    """Carpeta donde viven los archivos de idioma."""
    return carpeta() / "tessdata"


def ejecutable() -> Path | None:
    """Devuelve el ejecutable de Tesseract que se va a usar, o ``None``.

    Se prefiere **siempre** el portable: es el que viene con el programa, el
    que tiene los idiomas que el usuario ha ido añadiendo desde aquí y el que
    no cambia cuando alguien actualiza otra cosa en su equipo.  Solo si no está
    se busca uno instalado en el sistema, para no dejar sin OCR a quien ya lo
    tenga.
    """
    propio = carpeta() / "tesseract.exe"
    if propio.exists():
        return propio
    if sys.platform != "win32":
        encontrado = shutil.which("tesseract")
        return Path(encontrado) if encontrado else None
    encontrado = shutil.which("tesseract.exe") or shutil.which("tesseract")
    if encontrado:
        return Path(encontrado)
    for candidata in (
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Tesseract-OCR",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Tesseract-OCR",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Tesseract-OCR",
        Path(os.environ.get("USERPROFILE", "")) / "scoop" / "apps" / "tesseract" / "current",
    ):
        if (candidata / "tesseract.exe").exists():
            return candidata / "tesseract.exe"
    return None


def es_portable() -> bool:
    """Indica si el Tesseract que se va a usar es el que trae el programa."""
    binario = ejecutable()
    return binario is not None and binario.parent == carpeta()


def disponible() -> bool:
    """Si hay un Tesseract con el que reconocer."""
    return ejecutable() is not None


def version() -> str:
    """Versión de Tesseract, o cadena vacía si no se puede preguntar."""
    binario = ejecutable()
    if binario is None:
        return ""
    try:
        salida = subprocess.run(
            [str(binario), "--version"], capture_output=True, text=True,
            timeout=15, creationflags=_sin_consola())
        primera = (salida.stdout or salida.stderr or "").splitlines()
        return primera[0].strip() if primera else ""
    except Exception as error:
        log.debug("No se ha podido preguntar la versión de Tesseract: %s", error)
        return ""


def _sin_consola() -> int:
    """Bandera para que Windows no abra una ventana negra al ejecutar."""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


def directorio_datos_tesseract() -> Path | None:
    """Carpeta ``tessdata`` que hay que pasarle a Tesseract.

    Con el portable es la suya.  Con uno del sistema se deja que lo resuelva
    él, que sabe dónde tiene los suyos.
    """
    propia = carpeta_idiomas()
    if propia.exists() and any(propia.glob("*.traineddata")):
        return propia
    return None


def instalados() -> list[str]:
    """Códigos de los idiomas que hay disponibles ahora mismo, ordenados.

    Con el portable se miran **solo los suyos**, aunque el equipo tenga otro
    Tesseract con cien idiomas más.  Es a propósito: el portable tiene que
    funcionar igual en cualquier ordenador, y si aquí se contaran los del
    sistema, una copia del programa llevada a otro equipo se quedaría de
    repente sin idiomas sin que nada lo hubiera anunciado.
    """
    encontrados: set[str] = set()
    propia = carpeta_idiomas()
    if propia.exists():
        encontrados.update(archivo.stem for archivo in propia.glob("*.traineddata"))
    if encontrados or es_portable():
        return sorted(encontrados)
    # Sin portable, se le pregunta al Tesseract del sistema.
    binario = ejecutable()
    if binario is not None:
        try:
            salida = subprocess.run(
                [str(binario), "--list-langs"], capture_output=True, text=True,
                timeout=20, creationflags=_sin_consola())
            for linea in (salida.stdout or "").splitlines()[1:]:
                codigo = linea.strip()
                if codigo and "/" not in codigo and "\\" not in codigo:
                    encontrados.add(codigo)
        except Exception as error:
            log.debug("No se han podido listar los idiomas: %s", error)
    return sorted(encontrados)


def nombre_de(codigo: str) -> str:
    """Nombre legible de un idioma de Tesseract."""
    return IDIOMAS.get(codigo, codigo)


def disponibles_para_descargar() -> list[tuple[str, str]]:
    """Idiomas conocidos que **no** están instalados, con su nombre."""
    puestos = set(instalados())
    return sorted(((codigo, nombre) for codigo, nombre in IDIOMAS.items()
                   if codigo not in puestos), key=lambda par: par[1].lower())


def descargar_idioma(codigo: str, mejor: bool = False, progreso=None) -> Path:
    """Descarga un idioma y lo deja listo para usar.

    :param codigo: Código de Tesseract, por ejemplo ``spa``.
    :param mejor: Si se trae la colección precisa en vez de la rápida.
    :param progreso: Función ``(descargado, total, mensaje)`` opcional.
    :return: Ruta del archivo instalado.
    :raises RuntimeError: Si la descarga falla.
    """
    destino_carpeta = carpeta_idiomas()
    destino_carpeta.mkdir(parents=True, exist_ok=True)
    destino = destino_carpeta / ("%s.traineddata" % codigo)
    url = (URL_BEST if mejor else URL_FAST) % codigo
    log.info("Descargando el idioma %s desde %s", codigo, url)
    temporal = destino.with_suffix(".parcial")
    try:
        peticion = urllib.request.Request(url, headers={"User-Agent": "VisorUniversal"})
        with urllib.request.urlopen(peticion, timeout=ESPERA_DESCARGA) as respuesta:
            total = int(respuesta.headers.get("Content-Length") or 0)
            hecho = 0
            with open(temporal, "wb") as salida:
                while True:
                    trozo = respuesta.read(65536)
                    if not trozo:
                        break
                    salida.write(trozo)
                    hecho += len(trozo)
                    if progreso is not None:
                        progreso(hecho, total,
                                 _("Descargando %s...") % nombre_de(codigo))
        temporal.replace(destino)
        log.info("Idioma %s instalado (%d KB)", codigo, destino.stat().st_size // 1024)
        return destino
    except urllib.error.HTTPError as error:
        temporal.unlink(missing_ok=True)
        if error.code == 404:
            raise RuntimeError(_("El idioma «%s» no existe en el repositorio de Tesseract.")
                               % codigo)
        raise RuntimeError(_("No se ha podido descargar el idioma: %s") % error)
    except Exception as error:
        temporal.unlink(missing_ok=True)
        registrar_excepcion(log, "Fallo al descargar el idioma %s" % codigo, error)
        raise RuntimeError(_("No se ha podido descargar el idioma: %s") % error)


def quitar_idioma(codigo: str) -> bool:
    """Borra un idioma del Tesseract portable.

    :return: Si se ha llegado a borrar.  Los idiomas de un Tesseract instalado
             en el sistema no se tocan: no son nuestros.
    """
    destino = carpeta_idiomas() / ("%s.traineddata" % codigo)
    try:
        if destino.exists():
            destino.unlink()
            log.info("Idioma %s retirado", codigo)
            return True
    except OSError as error:
        log.warning("No se ha podido borrar el idioma %s: %s", codigo, error)
    return False


def tamano_idiomas() -> int:
    """Lo que ocupan los idiomas instalados, en bytes."""
    propia = carpeta_idiomas()
    if not propia.exists():
        return 0
    return sum(archivo.stat().st_size for archivo in propia.glob("*.traineddata"))


def motivo_no_disponible() -> str:
    """Explica qué falta, o cadena vacía si está todo listo."""
    if not disponible():
        return _(
            "Tesseract no está disponible.\n\n"
            "Debería venir con el programa, en la carpeta «data\\tesseract». Si has copiado "
            "el programa a mano puede que falte esa carpeta; vuelve a copiarla desde el "
            "original.")
    if not instalados():
        return _(
            "Tesseract está instalado pero no tiene ningún idioma.\n\n"
            "Añade al menos uno en Opciones, «Lectura», «Idiomas del reconocimiento».")
    return ""


def solo_idiomas(codigos) -> list[str]:
    """Quita de una lista lo que no es un idioma de lectura."""
    return [codigo for codigo in codigos if codigo and codigo not in NO_SON_IDIOMAS]


def idioma_por_omision(preferido: str = "") -> str:
    """Elige con qué idiomas reconocer si el usuario no ha dicho nada.

    Se combinan varios con «+», que es como Tesseract admite más de uno a la
    vez.  Sale a cuenta: un documento en catalán suele llevar también nombres y
    citas en español, y darle los dos mejora el resultado sin coste apreciable.
    """
    puestos = set(solo_idiomas(instalados()))
    pedidos = [codigo for codigo in solo_idiomas((preferido or "").split("+"))
               if codigo in puestos]
    if pedidos:
        # Se respeta lo que haya elegido el usuario, entero.  Recortar su lista
        # «porque tres bastan» le quitaría un idioma sin decírselo, y bastó una
        # prueba para ver adónde lleva eso: con la lista guardada en orden
        # alfabético, quedarse con los tres primeros dejaba fuera el español.
        # Lo que sí se hace es ponerlos en orden de probabilidad, que es el que
        # Tesseract usa para desempatar.
        preferentes = [c for c in ("spa", "cat", "eng") if c in pedidos]
        return "+".join(preferentes + [c for c in pedidos if c not in preferentes])
    elegidos = [candidato for candidato in ("spa", "cat", "eng") if candidato in puestos]
    if not elegidos and puestos:
        elegidos = [sorted(puestos)[0]]
    return "+".join(elegidos[:3])
