# -*- coding: utf-8 -*-
"""Localiza los intérpretes de Python instalados en el equipo.

Lo usa ``VisorUniversal.bat`` para ofrecer una lista donde elegir con cuál se
crea el entorno virtual.  Se hace en Python y no en el propio archivo por
lotes porque las rutas de Windows pueden contener espacios («C:\\Program
Files\\Python312»), y trocear esas líneas en un ``.bat`` es frágil.

Imprime una línea por intérprete, con los campos separados por barras
verticales, que es un carácter que no puede aparecer en una ruta::

    3.13.13|64 bits|si|C:\\Python313-64\\python.exe

El tercer campo dice si sirve para este programa:

``si``
    Sirve.
``nueva``
    Sirve, pero es una versión tan reciente que puede que wxPython todavía no
    tenga paquete para ella.  Se avisa antes de usarla.
``no``
    No sirve.  Son las compilaciones «sin GIL» (*free-threading*), para las
    que wxPython no publica paquetes.

La lista sale ordenada de la versión más reciente a la más antigua.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

#: Cuánto se espera, como mucho, a que un intérprete conteste.
ESPERA = 6

#: Orden que se pide a cada candidato para identificarse.  Se imprime en el
#: mismo formato de salida, así que el trabajo lo hace el propio intérprete.
CONSULTA = (
    "import sys, sysconfig;"
    "v='.'.join(str(n) for n in sys.version_info[:3]);"
    "b='64 bits' if sys.maxsize > 2**32 else '32 bits';"
    "g=' sin GIL' if sysconfig.get_config_var('Py_GIL_DISABLED') else '';"
    "print(v+'|'+b+g)"
)

#: Ultima version de Python para la que se da por segura la existencia de un
#: paquete de wxPython.  Las mas nuevas se marcan como "nueva" para avisar,
#: no para impedirlas: en cuanto wxPython publique el paquete funcionaran.
ULTIMA_VERSION_SEGURA = (3, 13)


def candidatos() -> list[str]:
    """Reúne todas las rutas donde puede haber un intérprete.

    Se consultan tres fuentes, de la más fiable a la menos:

    1. El lanzador ``py``, que conoce todas las instalaciones registradas.
    2. El propio intérprete que está ejecutando este script.
    3. Los ``python.exe`` que haya en la variable ``PATH`` y en las carpetas
       de instalación habituales.
    """
    rutas: list[str] = []

    # 1) El lanzador de Python para Windows.
    try:
        salida = subprocess.run(
            ["py", "-0p"], capture_output=True, text=True, timeout=ESPERA,
            errors="replace",
        ).stdout
        for linea in salida.splitlines():
            # Formato: " -V:3.13 *        C:\Python313-64\python.exe"
            coincidencia = re.match(r"\s*-V:\S+\s+\*?\s*(.+?)\s*$", linea)
            if coincidencia:
                rutas.append(coincidencia.group(1))
    except Exception:
        pass

    # 2) El intérprete actual.
    if sys.executable:
        rutas.append(sys.executable)

    # 3) El PATH y las carpetas de instalación más comunes.
    for nombre in ("python", "python3"):
        encontrado = shutil.which(nombre)
        if encontrado:
            rutas.append(encontrado)
    for base in (r"C:\\", os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python")):
        try:
            for entrada in os.listdir(base):
                if entrada.lower().startswith("python"):
                    candidato = os.path.join(base, entrada, "python.exe")
                    if os.path.isfile(candidato):
                        rutas.append(candidato)
        except OSError:
            continue
    return rutas


def identificar(ruta: str) -> tuple[str, str] | None:
    """Pregunta a un intérprete su versión y arquitectura.

    Devuelve ``None`` si la ruta no es un intérprete utilizable: así se
    descartan los accesos directos de la Tienda de Windows, que existen pero
    no funcionan hasta que se instala algo.
    """
    try:
        resultado = subprocess.run(
            [ruta, "-c", CONSULTA], capture_output=True, text=True,
            timeout=ESPERA, errors="replace",
        )
    except Exception:
        return None
    if resultado.returncode != 0:
        return None
    linea = resultado.stdout.strip()
    if "|" not in linea:
        return None
    version, etiqueta = linea.split("|", 1)
    return version.strip(), etiqueta.strip()


def aptitud(version: str, etiqueta: str) -> str:
    """Dice si un intérprete sirve para este programa.

    :return: ``"no"`` si es una compilación sin GIL (wxPython no publica
             paquetes para ellas), ``"nueva"`` si es más reciente que
             :data:`ULTIMA_VERSION_SEGURA`, y ``"si"`` en los demás casos.
    """
    if "sin GIL" in etiqueta:
        return "no"
    if clave_de_orden(version)[:2] > ULTIMA_VERSION_SEGURA:
        return "nueva"
    return "si"


def clave_de_orden(version: str) -> tuple:
    """Convierte «3.13.13» en una tupla para poder ordenar por versión."""
    partes = []
    for trozo in version.split("."):
        try:
            partes.append(int(trozo))
        except ValueError:
            partes.append(0)
    return tuple(partes)


def main() -> int:
    """Imprime la lista de intérpretes encontrados."""
    vistos: set[str] = set()
    encontrados: list[tuple[str, str, str]] = []
    for ruta in candidatos():
        try:
            normalizada = os.path.normcase(os.path.realpath(ruta))
        except OSError:
            continue
        if normalizada in vistos or not os.path.isfile(ruta):
            continue
        vistos.add(normalizada)
        datos = identificar(ruta)
        if datos is None:
            continue
        version, etiqueta = datos
        encontrados.append((version, etiqueta, aptitud(version, etiqueta), ruta))

    encontrados.sort(key=lambda fila: clave_de_orden(fila[0]), reverse=True)
    for version, etiqueta, apto, ruta in encontrados:
        print("%s|%s|%s|%s" % (version, etiqueta, apto, ruta))
    return 0 if encontrados else 1


if __name__ == "__main__":
    sys.exit(main())
