# -*- coding: utf-8 -*-
"""Prepara el Tesseract portable que viaja con el programa.

Tesseract no publica un ZIP portable para Windows: solo un instalador.  Pero el
programa que instala **es** portable —un ejecutable y sus bibliotecas al lado,
sin nada en el registro—, así que basta con reunir esas piezas en
``data/tesseract`` para que el usuario no tenga que instalar nada.

Este guion hace eso: busca una instalación de Tesseract en el equipo, copia lo
que hace falta y descarga los idiomas de partida.  Se ejecuta **una vez**, al
preparar una copia del programa para distribuir::

    python herramientas/tesseract_portable.py

Opciones::

    --desde RUTA     Carpeta donde está el tesseract.exe que se quiere copiar.
    --idiomas a,b,c  Idiomas que se instalan (por omisión, los básicos).
    --mejor          Descarga la colección precisa en vez de la rápida.
    --solo-idiomas   No copia el ejecutable, solo añade idiomas.

Si en el equipo no hay ningún Tesseract, el guion lo dice y explica de dónde
sacarlo.  La fuente recomendada es el instalador de UB Mannheim, que es la
compilación oficial para Windows:

    https://github.com/UB-Mannheim/tesseract/wiki

De ese instalador se pueden extraer los archivos sin llegar a instalar nada,
con 7-Zip («Extraer aquí» sobre el .exe), y luego pasarle la carpeta resultante
con ``--desde``.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from nucleo import tesseract as motor        # noqa: E402

#: Lo que hay que llevarse además del ejecutable.  Tesseract arrastra bastantes
#: bibliotecas —imagen, compresión, tipografía— y todas hacen falta.
PATRONES = ("tesseract.exe", "*.dll")

#: Carpetas de ``tessdata`` que hay que copiar aparte de los idiomas.  Son
#: archivos de texto diminutos, pero sin ellos Tesseract no sabe producir nada
#: que no sea texto plano: el formato TSV —el que trae las coordenadas de cada
#: palabra, y con ellas el orden de lectura y las tablas— se pide nombrando el
#: archivo de configuración ``configs/tsv``, y si falta, Tesseract se queja de
#: que no puede abrirlo y no escribe la salida.
CONFIGURACIONES = ("configs", "tessconfigs")

#: Archivos sueltos de ``tessdata`` que conviene llevarse: la tipografía con la
#: que Tesseract compone los PDF con capa de texto.
EXTRAS = ("pdf.ttf",)

#: Carpetas donde se suele encontrar una instalación de Tesseract.
CANDIDATAS = (
    r"%PROGRAMFILES%\Tesseract-OCR",
    r"%PROGRAMFILES(X86)%\Tesseract-OCR",
    r"%LOCALAPPDATA%\Programs\Tesseract-OCR",
    r"%USERPROFILE%\scoop\apps\tesseract\current",
    r"%USERPROFILE%\AppData\Local\Tesseract-OCR",
)


def buscar_instalacion() -> Path | None:
    """Busca una carpeta con un ``tesseract.exe`` dentro."""
    encontrado = shutil.which("tesseract.exe") or shutil.which("tesseract")
    if encontrado:
        real = Path(encontrado).resolve()
        # Un «shim» de scoop es un lanzador diminuto: lo que interesa es la
        # carpeta de verdad, donde están las bibliotecas.
        if real.stat().st_size > 40000 and (real.parent / "tesseract.exe").exists():
            hermanas = list(real.parent.glob("*.dll"))
            if hermanas:
                return real.parent
    for plantilla in CANDIDATAS:
        carpeta = Path(os.path.expandvars(plantilla))
        if (carpeta / "tesseract.exe").exists() and list(carpeta.glob("*.dll")):
            return carpeta
    return None


def copiar(origen: Path, destino: Path) -> int:
    """Copia el ejecutable, sus bibliotecas y las configuraciones.

    :return: Los bytes copiados.
    """
    destino.mkdir(parents=True, exist_ok=True)
    total = 0
    for patron in PATRONES:
        for archivo in sorted(origen.glob(patron)):
            objetivo = destino / archivo.name
            if objetivo.exists() and objetivo.stat().st_size == archivo.stat().st_size:
                total += archivo.stat().st_size
                continue
            shutil.copy2(archivo, objetivo)
            total += archivo.stat().st_size

    datos_origen = origen / "tessdata"
    datos_destino = destino / "tessdata"
    datos_destino.mkdir(parents=True, exist_ok=True)
    for nombre in CONFIGURACIONES:
        if (datos_origen / nombre).is_dir():
            shutil.copytree(datos_origen / nombre, datos_destino / nombre,
                            dirs_exist_ok=True)
            total += sum(a.stat().st_size
                         for a in (datos_destino / nombre).rglob("*") if a.is_file())
    for nombre in EXTRAS:
        if (datos_origen / nombre).exists():
            shutil.copy2(datos_origen / nombre, datos_destino / nombre)
            total += (datos_destino / nombre).stat().st_size
    return total


def main() -> int:
    """Prepara el portable según lo que se le pida."""
    analizador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analizador.add_argument("--desde", help="carpeta con el tesseract.exe a copiar")
    analizador.add_argument("--idiomas", default=",".join(motor.BASICOS),
                            help="idiomas separados por comas")
    analizador.add_argument("--mejor", action="store_true",
                            help="descargar la colección precisa (más grande y lenta)")
    analizador.add_argument("--solo-idiomas", action="store_true",
                            help="no copiar el ejecutable, solo añadir idiomas")
    opciones = analizador.parse_args()

    destino = motor.carpeta()
    print("Destino: %s" % destino)

    if not opciones.solo_idiomas:
        origen = Path(opciones.desde) if opciones.desde else buscar_instalacion()
        if origen is None:
            print()
            print("No se ha encontrado ninguna instalación de Tesseract en este equipo.")
            print()
            print("Descarga el instalador oficial para Windows de UB Mannheim:")
            print("   https://github.com/UB-Mannheim/tesseract/wiki")
            print()
            print("No hace falta instalarlo: con 7-Zip, «Extraer aquí» sobre el .exe deja")
            print("los archivos sueltos.  Después vuelve a ejecutar este guion así:")
            print()
            print("   python herramientas/tesseract_portable.py --desde RUTA_EXTRAIDA")
            return 1
        if not (origen / "tesseract.exe").exists():
            print("En %s no hay ningún tesseract.exe." % origen)
            return 1
        print("Copiando desde: %s" % origen)
        copiados = copiar(origen, destino)
        print("   %d archivos, %.1f MB" % (len(list(destino.glob('*'))) - 1,
                                           copiados / 1048576))

    codigos = [c.strip() for c in opciones.idiomas.split(",") if c.strip()]
    if codigos:
        print()
        print("Idiomas (%s):" % ("precisos" if opciones.mejor else "rápidos"))
        puestos = set(motor.instalados())
        for codigo in codigos:
            if codigo in puestos:
                print("   %-8s %-28s ya estaba" % (codigo, motor.nombre_de(codigo)))
                continue
            try:
                ruta = motor.descargar_idioma(codigo, mejor=opciones.mejor)
            except RuntimeError as error:
                print("   %-8s %-28s FALLO: %s" % (codigo, motor.nombre_de(codigo), error))
                continue
            print("   %-8s %-28s %.1f MB" % (codigo, motor.nombre_de(codigo),
                                             ruta.stat().st_size / 1048576))

    print()
    version = motor.version()
    print("Tesseract listo: %s" % (version or "no responde"))
    print("   portable: %s" % ("sí" if motor.es_portable() else "no, se usa el del sistema"))
    print("   idiomas : %s" % ", ".join(motor.instalados()) or "ninguno")
    print("   ocupan  : %.1f MB" % (motor.tamano_idiomas() / 1048576))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
