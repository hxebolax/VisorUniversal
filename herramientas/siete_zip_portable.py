# -*- coding: utf-8 -*-
"""Deja el 7-Zip portable en ``data/bin``, listo para viajar con el programa.

**Por qué va dentro y no se pide instalado.**  El caso es siempre el mismo: un
cómic en RAR, o partido en `album.part1.rar`, `album.part2.rar`…  El ``tar`` que
trae Windows saca las páginas del primer volumen, dice que ha ido bien, y quien
lo lee llega a la quinta entendiendo que ahí se acaba.  El programa sabe
detectarlo y avisar, pero avisar no es abrirlo, y pedirle a alguien que instale
otro programa para poder leer su propio cómic es exactamente lo que este
programa no quiere hacer.

Son dos megas y medio.  Al lado de los noventa de Tesseract —que está ahí por la
misma razón, para no pedir nada— no es nada.

**Qué se copia y por qué esos dos archivos.**  ``7z.exe`` es la versión de
consola y ``7z.dll`` es donde viven los formatos: sin la biblioteca, el ejecutable
solo entiende 7z y ZIP, y justamente el RAR se queda fuera.  Va también su
``License.txt``, que es lo que hay que hacer al distribuir un programa ajeno.

**Licencia.**  7-Zip es de Igor Pavlov y se distribuye bajo la LGPL, salvo el
código que lee RAR, que tiene la licencia de unRAR: permite repartirlo y prohíbe
usarlo para *crear* archivos RAR.  Aquí solo se leen, así que no hay problema.
El texto completo viaja al lado del programa.

Uso::

    python herramientas/siete_zip_portable.py            # descarga la última
    python herramientas/siete_zip_portable.py 26.03      # una versión concreta

Si no hay conexión, también sirve pasarle un instalador ya descargado::

    python herramientas/siete_zip_portable.py --desde C:/descargas/7z2603-x64.exe
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

#: Versión que se descarga si no se dice otra.  Se deja escrita —y no se
#: averigua sola— para que compilar dos veces el mismo código dé exactamente el
#: mismo ejecutable: una versión que cambia sola es una fuente de sorpresas.
VERSION = "26.03"

#: De dónde se descarga. Es el repositorio oficial del propio 7-Zip.
PLANTILLA = "https://github.com/ip7z/7zip/releases/download/%(version)s/7z%(corta)s-x64.exe"

#: Lo que hay que quedarse del instalador.
NECESARIOS = ("7z.exe", "7z.dll", "License.txt")

#: Cuánto se espera a la descarga.
ESPERA = 180


def destino() -> Path:
    return RAIZ / "data" / "bin"


def _direccion(version: str) -> str:
    return PLANTILLA % {"version": version, "corta": version.replace(".", "")}


def descargar(version: str, carpeta: Path) -> Path:
    """Trae el instalador oficial. Devuelve dónde ha quedado."""
    direccion = _direccion(version)
    archivo = carpeta / ("7z%s-x64.exe" % version.replace(".", ""))
    print("Descargando %s" % direccion)
    with urllib.request.urlopen(direccion, timeout=ESPERA) as respuesta:
        archivo.write_bytes(respuesta.read())
    print("   %.1f MB" % (archivo.stat().st_size / 1048576))
    return archivo


def _extractor() -> str:
    """Con qué abrir el instalador, que es un autoextraíble de 7-Zip.

    Se usa el 7-Zip que ya haya en el equipo o el que ya esté en ``data/bin``:
    esto es una herramienta de desarrollo y se ejecuta una vez por versión, así
    que aquí sí se puede pedir. Lo que no se puede pedir es al usuario final.
    """
    propio = destino() / "7z.exe"
    if propio.is_file():
        return str(propio)
    for nombre in ("7z", "7za", "7zz"):
        ruta = shutil.which(nombre)
        if ruta:
            return ruta
    return ""


def extraer(instalador: Path, carpeta: Path) -> bool:
    """Saca el contenido del instalador a una carpeta."""
    programa = _extractor()
    if not programa:
        print("No hay ningún 7-Zip con el que abrir el instalador.")
        print("Instala uno, o descomprímelo a mano y usa --desde con la carpeta.")
        return False
    orden = [programa, "x", "-y", "-o%s" % carpeta, str(instalador)]
    resultado = subprocess.run(orden, capture_output=True)
    if resultado.returncode != 0:
        print(resultado.stderr.decode("utf-8", "replace")[:400])
        return False
    return True


def instalar(origen: Path) -> bool:
    """Copia a ``data/bin`` lo que hace falta. Dice si ha salido bien."""
    salida = destino()
    salida.mkdir(parents=True, exist_ok=True)
    faltan = []
    for nombre in NECESARIOS:
        candidato = origen / nombre
        if not candidato.is_file():
            # En algunos paquetes los archivos van dentro de una subcarpeta.
            encontrados = list(origen.rglob(nombre))
            candidato = encontrados[0] if encontrados else None
        if candidato is None or not candidato.is_file():
            faltan.append(nombre)
            continue
        if candidato.resolve() != (salida / nombre).resolve():
            shutil.copy2(candidato, salida / nombre)
        print("   %-14s %7.1f KB" % (nombre, candidato.stat().st_size / 1024))
    if faltan:
        print("Faltan estos archivos en lo descargado: %s" % ", ".join(faltan))
        return False
    return True


def comprobar() -> bool:
    """Ejecuta el 7-Zip recién puesto y mira que sepa de RAR.

    Es lo que de verdad importa: un 7-Zip sin la biblioteca al lado arranca,
    dice su versión y **no abre un RAR**, que es justo para lo que está aquí.
    """
    programa = destino() / "7z.exe"
    if not programa.is_file():
        return False
    try:
        resultado = subprocess.run([str(programa), "i"], capture_output=True,
                                   timeout=60)
    except (OSError, subprocess.SubprocessError) as error:
        print("No se ha podido ejecutar: %s" % error)
        return False
    salida = resultado.stdout.decode("utf-8", "replace")
    formatos = [linea for linea in salida.splitlines()
                if " Rar" in linea or " Rar5" in linea]
    primera = next((linea for linea in salida.splitlines() if linea.strip()),
                   "(sin respuesta)")
    print(primera.strip())
    if not formatos:
        print("AVISO: este 7-Zip no reconoce RAR. Falta 7z.dll a su lado.")
        return False
    print("Reconoce RAR y RAR5: los cómics se abrirán sin instalar nada.")
    return True


def main(argumentos) -> int:
    version = VERSION
    desde = None
    resto = []
    numero = 0
    while numero < len(argumentos):
        if argumentos[numero] == "--desde" and numero + 1 < len(argumentos):
            desde = Path(argumentos[numero + 1])
            numero += 2
            continue
        resto.append(argumentos[numero])
        numero += 1
    if resto:
        version = resto[0]

    with tempfile.TemporaryDirectory(prefix="7zip-") as temporal:
        carpeta = Path(temporal)
        if desde is not None and desde.is_dir():
            origen = desde
        else:
            instalador = desde if desde is not None else None
            if instalador is None:
                try:
                    instalador = descargar(version, carpeta)
                except Exception as error:
                    print("No se ha podido descargar: %s" % error)
                    return 1
            origen = carpeta / "contenido"
            origen.mkdir(exist_ok=True)
            if not extraer(instalador, origen):
                return 1
        print("Copiando a %s" % destino())
        if not instalar(origen):
            return 1
    return 0 if comprobar() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
