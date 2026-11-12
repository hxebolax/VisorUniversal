# -*- coding: utf-8 -*-
"""Deja en ``adjuntos/piper`` todo lo que necesita el motor de voces Piper.

**Qué es Piper.**  Voces neuronales que se generan **dentro del equipo**, sin
conexión y sin tarjeta gráfica.  Suenan a persona, no a sintetizador, y lo hacen
más rápido de lo que se oyen: medido aquí, cinco centésimas de segundo por
frase.  Es lo que usa media domótica libre para hablar, y hay ciento setenta y
seis voces en más de treinta idiomas.

Nueve de ellas son en español: cinco de España, dos de México y una de
Argentina.  En el paquete va una y las demás se bajan desde el propio motor
cuando se piden.

**Por qué el programa de línea de órdenes y no la biblioteca de Python.**
Porque la biblioteca no se puede instalar aquí: `piper-tts` depende de
`onnxruntime`, y de eso no hay versión para el Python que usa el visor.  Y
porque, aunque la hubiera, atar el paquete a una versión de Python significa que
deja de funcionar cuando el visor suba de versión.  El programa suelto no
depende de eso: es un ejecutable con sus bibliotecas al lado.

**Cómo se le habla.**  El modelo de una voz son sesenta megas, así que cargarlo
en cada frase no es una opción.  Piper sabe quedarse esperando: se le manda una
línea de JSON con la frase y dónde dejar el sonido, y contesta con la ruta
cuando lo tiene.  El proceso vive mientras dure la voz elegida.

**Licencias.**  Piper es MIT.  Cada voz tiene la suya, casi todas de conjuntos
de grabaciones públicos, y viaja con su ficha —el ``MODEL_CARD``— dentro del
paquete.

Uso::

    python herramientas/piper.py               # descarga y monta todo
    python herramientas/piper.py --probar       # solo comprueba lo que hay
    python herramientas/piper.py --voz es_MX-ald-medium   # con otra voz dentro

Después, el paquete se arma como los demás::

    python plugins_voz/crear_paquetes.py --reunir piper
    python plugins_voz/crear_paquetes.py piper
"""

from __future__ import annotations

import json
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "adjuntos" / "piper"

#: El programa de Piper para Windows, con sus bibliotecas.
PROGRAMA = ("https://github.com/rhasspy/piper/releases/download/"
            "2023.11.14-2/piper_windows_amd64.zip")

#: El catálogo de las ciento setenta y seis voces, con su idioma, su calidad y
#: dónde está cada archivo.  Va dentro del paquete: así la lista de voces se
#: puede enseñar sin conexión, y solo hace falta red para bajar una.
CATALOGO = "https://huggingface.co/rhasspy/piper-voices/resolve/main/voices.json"

#: De dónde se baja cada archivo de voz.
VOZ = "https://huggingface.co/rhasspy/piper-voices/resolve/main/%s"

#: La voz que va dentro del paquete.  Es la de referencia en español de España:
#: calidad media, sesenta megas, y suena bien de verdad.  Poner una más pequeña
#: ahorraría cuarenta megas y quitaría la razón de instalar este motor.
POR_OMISION = "es_ES-davefx-medium"

#: Lo que no se copia del programa.  El modelo de vocalización del árabe son
#: diez megas y solo lo usa Piper si se le pasa a propósito, cosa que este motor
#: no hace.
SOBRA = ("libtashkeel_model.ort",)


def bajar(direccion: str, donde: Path) -> Path:
    """Trae un archivo, si no está ya."""
    if donde.is_file() and donde.stat().st_size > 0:
        print("   ya estaba: %s (%.1f MB)"
              % (donde.name, donde.stat().st_size / 1048576))
        return donde
    donde.parent.mkdir(parents=True, exist_ok=True)
    print("   bajando %s..." % donde.name)
    with urllib.request.urlopen(direccion, timeout=300) as respuesta:
        donde.write_bytes(respuesta.read())
    print("      %.1f MB" % (donde.stat().st_size / 1048576))
    return donde


def voces_en_espanol(catalogo: dict) -> list:
    """Las voces del catálogo que hablan español, ordenadas por calidad."""
    orden = {"high": 0, "medium": 1, "low": 2, "x_low": 3}
    salida = [clave for clave, ficha in catalogo.items()
              if ficha.get("language", {}).get("family") == "es"]
    return sorted(salida, key=lambda uno: (orden.get(
        catalogo[uno].get("quality", ""), 9), uno))


def montar(temporal: Path, cual: str) -> None:
    """Deja el programa, el catálogo y una voz en ``adjuntos/piper``."""
    programa = bajar(PROGRAMA, temporal / "piper.zip")

    # Se vacía por dentro y no se borra la carpeta: en Windows basta con que
    # alguien la tenga abierta —una consola, el explorador— para que borrarla
    # falle, y no hay razón para que eso pare el trabajo.
    DESTINO.mkdir(parents=True, exist_ok=True)
    for uno in DESTINO.iterdir():
        if uno.is_dir():
            shutil.rmtree(uno, ignore_errors=True)
        else:
            uno.unlink(missing_ok=True)

    print("   montando el programa...")
    with zipfile.ZipFile(programa) as archivo:
        for miembro in archivo.infolist():
            if miembro.is_dir():
                continue
            nombre = miembro.filename.replace("\\", "/")
            if ".." in nombre.split("/") or nombre.startswith("/"):
                continue
            # El ZIP lo trae todo dentro de una carpeta «piper»; aquí va suelto.
            partes = nombre.split("/")
            if partes[0] == "piper":
                partes = partes[1:]
            if not partes or partes[-1] in SOBRA:
                continue
            salida = DESTINO.joinpath(*partes)
            salida.parent.mkdir(parents=True, exist_ok=True)
            with archivo.open(miembro) as origen, salida.open("wb") as escribir:
                shutil.copyfileobj(origen, escribir)
    if not (DESTINO / "piper.exe").is_file():
        raise SystemExit("el paquete de Piper no traía el programa")

    catalogo = bajar(CATALOGO, DESTINO / "voces" / "catalogo.json")
    fichas = json.loads(catalogo.read_text(encoding="utf-8"))
    print("   catálogo: %d voces, %d en español"
          % (len(fichas), len(voces_en_espanol(fichas))))

    if cual not in fichas:
        raise SystemExit("no existe la voz «%s». Las de español son: %s"
                         % (cual, ", ".join(voces_en_espanol(fichas))))
    print("   bajando la voz que va dentro (%s)..." % cual)
    for relativa in fichas[cual]["files"]:
        nombre = relativa.rsplit("/", 1)[-1]
        # La ficha de la voz —quién la grabó y con qué licencia— viaja con ella.
        if nombre.startswith(cual) or nombre == "MODEL_CARD":
            destino = nombre if nombre != "MODEL_CARD" else (cual + ".MODEL_CARD")
            bajar(VOZ % relativa, DESTINO / "voces" / destino)


def comprobar() -> bool:
    """Prueba que Piper habla, y que se queda esperando a la frase siguiente.

    Lo segundo es lo que importa: hablar una vez lo hace cualquiera.  Si hubiera
    que levantar el proceso y cargar sesenta megas de modelo en cada frase, este
    motor no serviría para leer un libro.
    """
    programa = DESTINO / "piper.exe"
    if not programa.is_file():
        print("No hay nada montado en %s" % DESTINO)
        return False
    modelos = sorted((DESTINO / "voces").glob("*.onnx"))
    if not modelos:
        print("No hay ninguna voz en %s" % (DESTINO / "voces"))
        return False

    import time

    orden = [str(programa), "--model", str(modelos[0]),
             "--espeak_data", str(DESTINO / "espeak-ng-data"),
             "--json-input", "--quiet"]
    with tempfile.TemporaryDirectory() as temporal:
        proceso = subprocess.Popen(
            orden, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, creationflags=0x08000000)
        bien = True
        for numero, frase in enumerate((
                "Hola, esta es la voz que leerá tus libros.",
                "Y esta es la segunda frase, sin volver a cargar nada.")):
            salida = Path(temporal) / ("prueba%d.wav" % numero)
            empieza = time.monotonic()
            proceso.stdin.write(
                (json.dumps({"text": frase, "output_file": str(salida)}) + "\n")
                .encode("utf-8"))
            proceso.stdin.flush()
            proceso.stdout.readline()
            tarda = time.monotonic() - empieza
            if not salida.is_file() or salida.stat().st_size <= 44:
                print("   frase %d: no ha salido sonido" % numero)
                bien = False
                continue
            crudo = salida.read_bytes()
            muestreo = struct.unpack("<I", crudo[24:28])[0]
            print("   frase %d: %.2f s de audio a %d Hz, en %.2f s"
                  % (numero, (len(crudo) - 44) / 2 / muestreo, muestreo, tarda))
        proceso.stdin.close()
        proceso.terminate()
    return bien


def main(argumentos) -> int:
    cual = POR_OMISION
    if "--voz" in argumentos:
        cual = argumentos[argumentos.index("--voz") + 1]
    if "--probar" not in argumentos:
        with tempfile.TemporaryDirectory() as temporal:
            montar(Path(temporal), cual)
        megas = sum(uno.stat().st_size for uno in DESTINO.rglob("*")
                    if uno.is_file()) / 1048576
        print("Montado en %s (%.0f MB)" % (DESTINO, megas))
    print("Comprobando que habla:")
    if not comprobar():
        print("Algo no ha ido bien.")
        return 1
    print("Todo correcto. El paquete se arma con:")
    print("   python plugins_voz/crear_paquetes.py --reunir piper")
    print("   python plugins_voz/crear_paquetes.py piper")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
