# -*- coding: utf-8 -*-
"""Localización de carpetas de la aplicación.

Toda la información que la aplicación genera o necesita vive dentro de una
única carpeta ``data`` situada junto al programa.  Esto hace que la
aplicación sea *portable*: basta con copiar la carpeta del programa (con su
``data`` dentro) a otro equipo para llevarse la configuración, los registros
y la caché.

Estructura creada dentro de ``data``:

===================  ====================================================
Subcarpeta           Contenido
===================  ====================================================
``config``           Ajustes de la aplicación y datos por documento (JSON).
``logs``             Registros de actividad y de errores.
``cache``            Caché de libros ya analizados (apertura instantánea).
``sonidos``          Sonidos de navegación en formato WAV.
``temp``             Archivos temporales (imágenes extraídas, etc.).
===================  ====================================================

El módulo funciona igual ejecutando desde el código fuente que desde el
ejecutable generado con cx_Freeze, porque detecta el modo «congelado»
mediante ``sys.frozen``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

#: Nombre de la carpeta que contiene todo lo que genera la aplicación.
NOMBRE_CARPETA_DATOS = "data"

#: Subcarpetas que siempre deben existir dentro de ``data``.
SUBCARPETAS = ("config", "logs", "cache", "sonidos", "temp", "correcciones",
               "motores")

#: Nombre de la carpeta donde viven las traducciones y la documentación.
NOMBRE_CARPETA_IDIOMAS = "idiomas"

#: Nombre del archivo del manual de usuario.
NOMBRE_MANUAL = "MANUAL_USUARIO.md"

#: Nombre del archivo con las novedades de cada versión.  Vive en la raíz del
#: proyecto mientras se escribe, y la compilación deja una copia recortada —sin
#: las notas internas de la cabecera— junto al manual de cada idioma.
NOMBRE_NOVEDADES = "NOVEDADES.md"

#: Carpeta, dentro de cada idioma, donde va su documentación.  El manual no
#: está suelto en ``data`` sino en ``data/idiomas/<código>/docs``: así, traducir
#: la documentación es dejar el archivo en la carpeta de ese idioma y nada más.
NOMBRE_CARPETA_DOCS = "docs"

#: Idioma en el que se escribe la documentación original.  Es el que se abre
#: cuando el idioma activo todavía no tiene su manual traducido, que es lo
#: normal mientras las traducciones van llegando.
IDIOMA_BASE = "es"


def esta_congelado() -> bool:
    """Indica si la aplicación se está ejecutando desde un ejecutable.

    cx_Freeze (igual que PyInstaller) añade el atributo ``frozen`` al módulo
    ``sys`` cuando el programa corre desde un ``.exe`` compilado.
    """
    return bool(getattr(sys, "frozen", False))


def directorio_base() -> Path:
    """Devuelve la carpeta raíz de la aplicación.

    * Ejecutando desde el código fuente: la carpeta del proyecto, es decir
      la carpeta *padre* de ``src``.
    * Ejecutando desde el ejecutable: la carpeta donde está el ``.exe``.
    """
    if esta_congelado():
        return Path(sys.executable).resolve().parent
    # rutas.py está en <proyecto>/src/nucleo/rutas.py -> subimos dos niveles.
    return Path(__file__).resolve().parent.parent.parent


def carpeta_idiomas() -> Path:
    """Carpeta con las traducciones y la documentación de cada idioma."""
    return directorio_datos() / NOMBRE_CARPETA_IDIOMAS


def carpeta_docs(codigo: str) -> Path:
    """Carpeta con la documentación de un idioma, existe o no.

    :param codigo: Código del idioma, por ejemplo ``"es"`` o ``"pt"``.
    """
    return carpeta_idiomas() / codigo / NOMBRE_CARPETA_DOCS


def idiomas_con_manual() -> list[str]:
    """Códigos de los idiomas que tienen el manual traducido."""
    encontrados = []
    try:
        for hijo in sorted(carpeta_idiomas().iterdir()):
            if hijo.is_dir() and (hijo / NOMBRE_CARPETA_DOCS / NOMBRE_MANUAL).is_file():
                encontrados.append(hijo.name)
    except OSError:
        pass
    return encontrados


def _documento_traducido(nombre: str, codigo: str = "") -> Path:
    """Archivo de ``docs`` en el idioma que corresponda.

    :param nombre: Nombre del archivo, por ejemplo ``"MANUAL_USUARIO.md"``.
    :param codigo: Idioma que se quiere.  Vacío, el que esté puesto.

    Se busca por este orden y se devuelve el primero que exista:

    #. el idioma pedido tal cual (``pt_BR``);
    #. su idioma base sin la variante (``pt``), porque un manual en portugués
       le sirve igual a quien tiene puesto el de Brasil;
    #. el español, que es en el que se escribe el original.

    Si no existe ninguno se devuelve **la ruta del español de todos modos**, y
    no la del idioma del usuario: así el aviso de «no se encuentra» señala la
    carpeta donde de verdad hay que ponerlo.
    """
    if not codigo:
        # Perezoso a propósito: ``idioma`` importa este módulo, y hacerlo
        # arriba dejaría las dos importaciones dándose vueltas.
        try:
            from . import idioma

            codigo = idioma.activo()
        except Exception:                           # pragma: no cover - arranque
            codigo = IDIOMA_BASE

    intentos = [codigo]
    if "_" in codigo or "-" in codigo:
        intentos.append(codigo.replace("-", "_").split("_")[0])
    intentos.append(IDIOMA_BASE)

    vistos = set()
    for cual in intentos:
        if cual in vistos:
            continue
        vistos.add(cual)
        candidato = carpeta_docs(cual) / nombre
        if candidato.is_file():
            return candidato
    return carpeta_docs(IDIOMA_BASE) / nombre


def ruta_manual(codigo: str = "") -> Path:
    """Archivo del manual de usuario, en el idioma que corresponda.

    :param codigo: Idioma que se quiere.  Vacío, el que esté puesto.
    """
    return _documento_traducido(NOMBRE_MANUAL, codigo)


def ruta_novedades(codigo: str = "") -> Path:
    """Archivo con las novedades de cada versión.

    :param codigo: Idioma que se quiere.  Vacío, el que esté puesto.

    Este archivo está en dos sitios y a propósito.  Mientras se desarrolla vive
    **en la raíz del proyecto**, que es donde se escribe cada versión y donde lo
    lee ``herramientas/empaquetar.py`` para redactar el aviso de actualización;
    esa copia lleva arriba unas notas que solo le importan a quien programa.  La
    compilación deja en ``docs`` una copia **recortada**, que empieza en la
    versión más reciente y es la que ve quien usa el programa.

    Por eso se mira primero la de la raíz cuando se está ejecutando desde el
    código fuente: ahí la de ``docs`` no existe, y si algún día existiera sería
    una copia vieja de la compilación anterior.
    """
    if not esta_congelado():
        suelto = directorio_base() / NOMBRE_NOVEDADES
        if suelto.is_file():
            return suelto
    return _documento_traducido(NOMBRE_NOVEDADES, codigo)


def codigo_de_documento(ruta: Path) -> str:
    """Idioma del que ha salido un documento de ``docs``.

    Sirve para nombrar la página web que se genera al abrirlo: si se ha caído
    al español porque el idioma puesto no tenía traducción, la página es la
    española y tiene que llamarse así, o al cambiar de idioma se seguiría
    abriendo la que se convirtió con el anterior.

    Un archivo que no está en ``docs`` —el ``NOVEDADES.md`` de la raíz cuando
    se ejecuta desde el código fuente— se da por escrito en el idioma original.
    """
    if ruta.parent.name == NOMBRE_CARPETA_DOCS:
        return ruta.parent.parent.name
    return IDIOMA_BASE


def directorio_datos() -> Path:
    """Devuelve (creándola si hace falta) la carpeta ``data``."""
    destino = directorio_base() / NOMBRE_CARPETA_DATOS
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def subcarpeta(nombre: str) -> Path:
    """Devuelve (creándola si hace falta) una subcarpeta de ``data``.

    :param nombre: Nombre de la subcarpeta, por ejemplo ``"logs"``.
    """
    destino = directorio_datos() / nombre
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def preparar_estructura() -> Path:
    """Crea la carpeta ``data`` con todas sus subcarpetas.

    Se llama una sola vez al arrancar, antes incluso de inicializar el
    sistema de registro (que necesita que exista ``data/logs``).

    :return: La ruta de la carpeta ``data``.
    """
    raiz = directorio_datos()
    for nombre in SUBCARPETAS:
        (raiz / nombre).mkdir(parents=True, exist_ok=True)
    return raiz


def ruta_config() -> Path:
    """Carpeta de configuración."""
    return subcarpeta("config")


def ruta_logs() -> Path:
    """Carpeta de registros."""
    return subcarpeta("logs")


def ruta_cache() -> Path:
    """Carpeta de caché de libros analizados."""
    return subcarpeta("cache")


def ruta_sonidos() -> Path:
    """Carpeta de sonidos de navegación."""
    return subcarpeta("sonidos")


def ruta_temp() -> Path:
    """Carpeta de archivos temporales."""
    return subcarpeta("temp")


def limpiar_temporales(edad_maxima_dias: int = 3) -> int:
    """Borra archivos antiguos de ``data/temp``.

    Evita que la carpeta de temporales crezca sin control con las imágenes
    que se extraen de los libros para poder mostrarlas.

    :param edad_maxima_dias: Antigüedad a partir de la cual se borra.
    :return: Número de archivos eliminados.
    """
    import time

    limite = time.time() - edad_maxima_dias * 86400
    eliminados = 0
    carpeta = ruta_temp()
    for elemento in carpeta.iterdir():
        try:
            if elemento.is_file() and elemento.stat().st_mtime < limite:
                elemento.unlink()
                eliminados += 1
        except OSError:
            # Un archivo bloqueado por otro proceso no debe impedir el arranque.
            continue
    return eliminados


def abrir_en_explorador(ruta: os.PathLike | str) -> None:
    """Abre el explorador de archivos del sistema en la ruta indicada."""
    destino = Path(ruta)
    if sys.platform == "win32":
        if destino.is_file():
            os.system(f'explorer /select,"{destino}"')
        else:
            os.startfile(str(destino))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        os.system(f'open "{destino}"')
    else:
        os.system(f'xdg-open "{destino}"')
