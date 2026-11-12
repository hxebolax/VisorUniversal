# -*- coding: utf-8 -*-
"""Empaqueta la compilación y prepara lo que hay que subir al servidor.

Después de compilar con cx_Freeze queda una carpeta ``build/VisorUniversal``.
Este guion la convierte en las **dos cosas que el actualizador necesita**:

* ``VisorUniversal_v<version>.zip``, con todo dentro de una carpeta del mismo
  nombre.  Esa carpeta la quita el actualizador al descomprimir, y su presencia
  es lo que permite abrir el ZIP a mano sin que se desparrame por el escritorio.
* ``version.json``, con la versión, el nombre del archivo, su ``sha256``, su
  tamaño, la fecha y las **notas de la versión**.  El programa lo consulta para
  saber si hay versión nueva, para comprobar la descarga antes de instalarla y
  para enseñar como «Novedades» lo que trae.

Las notas salen de ``NOVEDADES.md``, del apartado que lleve el número de la
versión que se está publicando.  Se hace así y no rellenando el JSON a mano por
lo de siempre: el ``version.json`` es un archivo **generado**, y lo que se
escribe a mano en un archivo generado se pierde en la compilación siguiente.

Si hay una clave privada en ``herramientas/claves`` el aviso se **firma**
además con ella.  La firma es obligatoria en cuanto se pone una clave pública en
``src/version.py``: sin ella, los clientes rechazarían el paquete.  Por eso, si
hay clave pública y no hay privada, este guion se para en vez de dejar publicar
algo que nadie podría instalar.

Se lanza solo desde la opción de compilar del menú, o a mano::

    python herramientas/empaquetar.py
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import zipfile
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "herramientas"))

#: Carpeta que deja cx_Freeze y nombre con el que se publica.
NOMBRE = "VisorUniversal"
ORIGEN = RAIZ / "build" / NOMBRE

#: Archivo del que salen las notas de cada versión.
NOVEDADES = RAIZ / "NOVEDADES.md"


def notas_de(version: str, ruta: Path | None = None) -> str:
    """Devuelve las novedades de una versión, tal como se van a anunciar.

    Se busca en ``NOVEDADES.md`` el apartado que empieza por ``## `` seguido del
    número, y se toma todo lo que va debajo hasta el apartado siguiente.  Los
    asteriscos del formato Markdown se quitan: esto no se lee en un navegador,
    se lee en voz alta y en un cuadro de texto, y ahí un asterisco solo estorba.

    Devuelve la cadena vacía si no hay archivo o si esa versión no está escrita,
    que es exactamente lo que había antes y no rompe nada.
    """
    origen = Path(ruta) if ruta is not None else NOVEDADES
    try:
        texto = origen.read_text(encoding="utf-8")
    except OSError:
        return ""
    patron = re.compile(r"^##\s+%s\s*$" % re.escape(version.strip()), re.MULTILINE)
    encontrado = patron.search(texto)
    if not encontrado:
        return ""
    resto = texto[encontrado.end():]
    siguiente = re.search(r"^##\s+", resto, re.MULTILINE)
    if siguiente:
        resto = resto[:siguiente.start()]
    lineas = []
    for linea in resto.strip().splitlines():
        limpia = linea.strip().strip("-").strip()
        if not limpia:
            # Una línea en blanco separa párrafos; más de una no aporta nada.
            if lineas and lineas[-1] != "":
                lineas.append("")
            continue
        lineas.append(limpia.replace("**", "").replace("`", ""))
    # Los párrafos vuelven a juntarse en una línea cada uno: el ancho al que
    # están partidos aquí es el del editor, no el del cuadro que los enseña.
    parrafos: list[str] = []
    actual: list[str] = []
    for linea in lineas:
        if linea:
            actual.append(linea)
        elif actual:
            parrafos.append(" ".join(actual))
            actual = []
    if actual:
        parrafos.append(" ".join(actual))
    return "\n\n".join(parrafos).strip()


#: Cabecera de la copia de ``NOVEDADES.md`` que viaja con el programa.  La del
#: archivo original explica de dónde salen las notas de la actualización y cómo
#: hay que escribirlas: eso le sirve a quien publica una versión y a nadie más.
#: Quien abre las novedades desde el menú de ayuda quiere leer qué ha cambiado,
#: así que lo primero que se encuentra es eso y no el funcionamiento interno.
CABECERA_NOVEDADES = """# Novedades del Visor Universal

Lo que cambia en cada versión, contado para quien lo va a usar.  Arriba del
todo está lo más reciente.

Cada versión es un encabezado, así que saltando de encabezado en encabezado se
pasa de una a otra sin tener que recorrer el texto entero.

---

"""


def novedades_publicas(ruta: Path | None = None) -> str:
    """Devuelve ``NOVEDADES.md`` tal como se le entrega a quien usa el programa.

    Es el archivo entero **desde la primera versión escrita**, con una cabecera
    nueva delante.  Lo que se queda fuera es justo lo de arriba: la explicación
    de que ``empaquetar.py`` lee de aquí las notas de la actualización y de qué
    formato tienen que llevar los apartados.  Eso es documentación de cómo se
    publica el programa, no una novedad.

    Si no hay ninguna versión escrita se devuelve la cadena vacía, y quien llama
    decide qué hacer: aquí no se inventa un archivo vacío que luego alguien
    abriría desde el menú sin entender por qué no pone nada.
    """
    origen = Path(ruta) if ruta is not None else NOVEDADES
    try:
        texto = origen.read_text(encoding="utf-8")
    except OSError:
        return ""
    primera = re.search(r"^##\s+", texto, re.MULTILINE)
    if not primera:
        return ""
    return CABECERA_NOVEDADES + texto[primera.start():].strip() + "\n"


def version_y_clave() -> tuple[str, str]:
    """Lee la versión y la clave pública de ``src/version.py`` como texto.

    Como texto y no importándolo: ``version.py`` no importa nada a propósito
    para poder leerse así, y este guion se ejecuta antes de que exista ningún
    entorno con el programa dentro.
    """
    fuente = (RAIZ / "src" / "version.py").read_text(encoding="utf-8")
    version = re.search(r'^VERSION\s*=\s*["\']([^"\']+)["\']', fuente, re.M)
    publica = re.search(r'^CLAVE_PUBLICA\s*=\s*["\']([^"\']*)["\']', fuente, re.M)
    return (version.group(1) if version else "0.0.0",
            publica.group(1) if publica else "")


#: Nombres que **nunca** pueden acabar dentro del paquete.  La clave privada
#: vive fuera de lo que se compila, así que no debería llegar aquí ni por
#: casualidad; la comprobación cuesta nada y protege de un cambio futuro que
#: copie más cosas a la carpeta de compilación.  Publicar la clave privada sería
#: el peor fallo posible: cualquiera podría firmar actualizaciones falsas.
PROHIBIDOS = (".key", ".pem", "claves")


def comprimir(origen: Path, destino: Path) -> int:
    """Comprime la carpeta compilada al máximo y devuelve cuántos archivos van.

    Al máximo porque el paquete se descarga entero por Internet cada vez que
    alguien actualiza: lo que se ahorre aquí se ahorra en cada descarga.

    :raises SystemExit: Si en la carpeta compilada aparece algo que parezca una
                        clave privada.
    """
    # Se recorre entero **antes** de crear el ZIP: así, si hay algo que no debe
    # publicarse, no llega a existir un archivo a medias con ello dentro.
    contenido: list[tuple[Path, Path]] = []
    for raiz, _carpetas, archivos in os.walk(origen):
        for archivo in sorted(archivos):
            ruta = Path(raiz) / archivo
            # Todo cuelga de una carpeta con el nombre del programa.
            interno = Path(NOMBRE) / ruta.relative_to(origen)
            if any(marca in str(interno).lower() for marca in PROHIBIDOS):
                raise SystemExit(
                    "ALTO: en la carpeta compilada hay algo que parece una clave "
                    "privada:\n   %s\n"
                    "No se empaqueta nada. Quítalo de %s antes de publicar."
                    % (interno, origen))
            contenido.append((ruta, interno))

    destino.unlink(missing_ok=True)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as paquete:
        for ruta, interno in contenido:
            paquete.write(ruta, str(interno))
    return len(contenido)


def sha256_de(ruta: Path) -> str:
    """Resumen del archivo, leído por trozos."""
    resumen = hashlib.sha256()
    with open(ruta, "rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            resumen.update(bloque)
    return resumen.hexdigest()


def main() -> int:
    """Empaqueta, escribe el aviso de versión y lo firma si procede."""
    if not ORIGEN.is_dir():
        print("No se encuentra la carpeta compilada: %s" % ORIGEN)
        print("Compila primero con cx_Freeze (opción 3 del menú).")
        return 1

    version, clave_publica = version_y_clave()
    destino = RAIZ / "build" / ("%s_v%s.zip" % (NOMBRE, version))

    print("Comprimiendo %s -> %s" % (ORIGEN.name, destino.name))
    archivos = comprimir(ORIGEN, destino)
    tamano = destino.stat().st_size
    print("   %d archivos, %.1f MB" % (archivos, tamano / (1024 * 1024)))

    print("Calculando el sha256 del paquete...")
    aviso = {
        "version": version,
        "file": destino.name,
        "sha256": sha256_de(destino),
        "size": tamano,
        "date": date.today().isoformat(),
        # Lo que el programa enseña como «Novedades» al ofrecer la versión.
        # Sale de NOVEDADES.md, para que lo que se anuncia y lo que está escrito
        # no puedan desincronizarse.
        "notas": notas_de(version),
    }
    ruta_json = RAIZ / "build" / "version.json"
    ruta_json.write_text(json.dumps(aviso, indent=2, ensure_ascii=False),
                         encoding="utf-8")
    print("   %s escrito" % ruta_json.name)

    # --- firma --------------------------------------------------------------
    # Al compilar, «preparar» ya ha creado la clave si no la había y ha dejado
    # la pública dentro de version.py, así que aquí normalmente solo queda
    # firmar.  Se comprueba de todos modos: empaquetar a mano una compilación
    # vieja no habría pasado por ese paso.
    from firmar_version import CLAVE, clave_publica_de, firmar, hay_clave, preparar

    if not hay_clave():
        if clave_publica:
            # El programa lleva clave pública pero falta la privada: firmar es
            # imposible y publicar sin firma dejaría un paquete que ningún
            # cliente aceptaría instalar.
            print()
            print("ERROR: src/version.py lleva una clave pública, así que los programas")
            print("       ya instalados RECHAZARÁN cualquier paquete sin firmar, y no se")
            print("       encuentra la clave privada en %s." % CLAVE)
            print("       Restáurala desde tu copia de seguridad antes de publicar.")
            return 1
        preparar()

    real = clave_publica_de()
    if clave_publica and clave_publica != real:
        print()
        print("ERROR: la clave pública que lleva el ejecutable compilado no es la de")
        print("       la clave privada con la que se iba a firmar. Vuelve a compilar")
        print("       para que el programa se lleve la correcta.")
        return 1

    print("Firmando el aviso de versión...")
    firmar(ruta_json)

    print()
    print("Listo. Sube al servidor ESTOS DOS archivos, en la misma carpeta:")
    print("   1) %s" % destino)
    print("   2) %s" % ruta_json)
    print()
    print("Esa carpeta es la que hay que poner en URL_ACTUALIZACIONES, en")
    print("src/version.py, sin la barra final.")
    print()
    print("Y en GitHub, una release con la etiqueta v%s y esos mismos dos archivos" % version)
    print("adjuntos, por ejemplo con:")
    print('   gh release create v%s "%s" "%s" --title "Visor Universal %s" '
          '--notes-file <notas>' % (version, destino, ruta_json, version))
    if not aviso["notas"]:
        print()
        print("AVISO: NOVEDADES.md no tiene ningún apartado «## %s», así que la" % version)
        print("       versión se ofrecerá sin novedades que contar. Escríbelas ahí y")
        print("       vuelve a empaquetar; no hace falta compilar otra vez.")
    else:
        print()
        print("Novedades que se anunciarán (%d caracteres):" % len(aviso["notas"]))
        print("   %s..." % aviso["notas"][:120].replace("\n", " "))
    return 0


if __name__ == "__main__":
    sys.exit(main())
