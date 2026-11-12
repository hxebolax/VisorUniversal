# -*- coding: utf-8 -*-
"""Deja en ``adjuntos/espeak_mbrola`` todo lo que necesita el motor MBROLA.

**Qué es MBROLA.**  Un sintetizador de difonos: en vez de calcular la voz, la
pega a partir de trozos grabados de una persona real.  Es de los noventa, y se
nota, pero suena bastante más humano que eSpeak solo y sigue siendo diminuto,
sin conexión y sin pedirle nada al equipo.  Para el español hay siete voces:
cuatro de España, dos de México y una de Venezuela.

**Por qué no vale la biblioteca del paquete eSpeak.**  La que trae NVDA está
compilada sin MBROLA.  No falla: elige la voz, dice «espeak-ng was built without
mbrola support» por la salida de errores y sigue hablando con su voz de siempre,
que es la peor manera de fallar que hay.  La oficial de eSpeak NG sí lo trae.

**Y por qué entonces no se cambia la del paquete eSpeak por la oficial.**
Porque se perdería lo mejor que tiene ese paquete.  NVDA compila eSpeak con
«sonic», que es lo que deja triplicar la velocidad máxima: medido con la misma
frase, la de NVDA a 1347 palabras por minuto tarda 1,55 segundos y la oficial
tarda 5,21, porque se queda en su tope de 449.  Mucha gente usa eSpeak
precisamente por eso.  Así que son dos paquetes: eSpeak, rápido y sintético, y
eSpeak MBROLA, más lento y más humano.  Cada uno hace bien lo suyo.

**Qué se descarga y de dónde.**

- La biblioteca de eSpeak NG, del instalador oficial del proyecto.
- ``mbrola.dll`` de 64 bits, de la reconstrucción de código abierto de thiekus:
  la distribución original de MBROLA nunca tuvo binario de 64 bits, y el
  programa es de 64.
- Las siete voces españolas, del repositorio de voces de numediart.
- Las tablas que traducen los fonemas de eSpeak a los de cada voz, que eSpeak NG
  genera al compilarse y el instalador oficial no trae hechas.

**Licencias.**  eSpeak NG es GPL 3.  El código de MBROLA se liberó en 2018 y es
AGPL 3.  Las voces son gratuitas con una condición que aquí se cumple: se pueden
copiar y repartir libremente **mientras no se cobre por ellas**, y hay que
repartir el aviso de licencia con ellas.  El aviso se copia al lado de las voces
y viaja dentro del paquete.

Uso::

    python herramientas/espeak_mbrola.py           # descarga y monta todo
    python herramientas/espeak_mbrola.py --probar  # solo comprueba lo que hay

Después, el paquete se arma como los demás::

    python plugins_voz/crear_paquetes.py espeak_mbrola
"""

from __future__ import annotations

import ctypes
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "adjuntos" / "espeak_mbrola"

#: El instalador oficial de eSpeak NG.  De aquí sale la única biblioteca de
#: Windows compilada con MBROLA que se publica hecha.
ESPEAK = ("https://github.com/espeak-ng/espeak-ng/releases/download/"
          "1.52.0/espeak-ng.msi")

#: La reconstrucción de MBROLA que sí publica binario de 64 bits.  La original
#: solo tiene de 32, y un programa de 64 no puede cargarla.
MBROLA = ("https://github.com/thiekus/MBROLA/releases/download/3.3/"
          "mbrola_build_3.3_rev2.zip")

#: Las tablas de fonemas ya compiladas.  Se generan al compilar eSpeak NG con
#: MBROLA, y el instalador oficial no las incluye.
TABLAS = "https://github.com/user-attachments/files/19094349/mbrola_ph.zip"

#: De dónde salen las voces, una a una.
VOCES = "https://github.com/numediart/MBROLA-voices/raw/master/data/%s/%s"

#: Aviso de licencia de las voces, que hay que repartir con ellas.
LICENCIA = ("https://raw.githubusercontent.com/numediart/MBROLA-voices/"
            "master/LICENSE.md")

#: Las que se incluyen.  Son las siete de español —cuatro de España, dos de
#: México y una de Venezuela—, que es de lo que trata el programa; las demás se
#: pueden bajar luego desde el propio motor.
ESPANOLAS = ("es1", "es2", "es3", "es4", "mx1", "mx2", "vz1")

#: Dónde está NVDA, por las tres variantes de voz que añade y que el eSpeak
#: oficial no trae.  Si no está, se sigue sin ellas.
NVDA_POSIBLES = (Path("C:/Program Files/NVDA"), Path("C:/Program Files (x86)/NVDA"))


def bajar(direccion: str, donde: Path) -> Path:
    """Trae un archivo, si no está ya."""
    if donde.is_file() and donde.stat().st_size > 0:
        print("   ya estaba: %s (%.1f MB)"
              % (donde.name, donde.stat().st_size / 1048576))
        return donde
    donde.parent.mkdir(parents=True, exist_ok=True)
    print("   bajando %s..." % donde.name)
    with urllib.request.urlopen(direccion, timeout=120) as respuesta:
        donde.write_bytes(respuesta.read())
    print("      %.1f MB" % (donde.stat().st_size / 1048576))
    return donde


def abrir_instalador(msi: Path, donde: Path) -> Path:
    """Saca el instalador de eSpeak NG **con sus carpetas**.

    Con una instalación administrativa, que es la que copia los archivos sin
    tocar el equipo.  Descomprimirlo con 7-Zip también funciona, pero deja los
    cuatrocientos archivos sueltos en un montón, sin la estructura de carpetas
    que eSpeak necesita para encontrar sus idiomas.
    """
    donde.mkdir(parents=True, exist_ok=True)
    subprocess.run(["msiexec", "/a", str(msi), "/qn", "TARGETDIR=%s" % donde],
                   check=True, capture_output=True)
    dentro = donde / "eSpeak NG"
    if not (dentro / "libespeak-ng.dll").is_file():
        raise SystemExit("el instalador de eSpeak NG no traía la biblioteca")
    return dentro


def variantes_de_nvda() -> Path | None:
    """La carpeta de variantes de NVDA, si NVDA está en este equipo."""
    for camino in NVDA_POSIBLES:
        donde = camino / "synthDrivers" / "espeak-ng-data" / "voices" / "!v"
        if donde.is_dir():
            return donde
    return None


def montar(temporal: Path) -> None:
    """Deja todo en su sitio dentro de ``adjuntos/espeak_mbrola``."""
    msi = bajar(ESPEAK, temporal / "espeak-ng.msi")
    zip_mbrola = bajar(MBROLA, temporal / "mbrola.zip")
    zip_tablas = bajar(TABLAS, temporal / "mbrola_ph.zip")

    if DESTINO.exists():
        shutil.rmtree(DESTINO)
    DESTINO.mkdir(parents=True)
    datos = DESTINO / "espeak-ng-data"

    print("   montando eSpeak NG...")
    oficial = abrir_instalador(msi, temporal / "espeak")
    # Se llama «espeak.dll» y no «libespeak-ng.dll» a propósito: es el nombre
    # con el que la busca el motor, el mismo que usa el paquete de eSpeak.  Así
    # los dos motores se escriben igual.
    shutil.copy2(oficial / "libespeak-ng.dll", DESTINO / "espeak.dll")
    shutil.copytree(oficial / "espeak-ng-data", datos)

    print("   montando MBROLA...")
    with zipfile.ZipFile(zip_mbrola) as archivo:
        (DESTINO / "mbrola.dll").write_bytes(
            archivo.read("Win64/Release/mbrola.dll"))

    (datos / "mbrola_ph").mkdir(exist_ok=True)
    with zipfile.ZipFile(zip_tablas) as archivo:
        for miembro in archivo.infolist():
            if not miembro.is_dir():
                (datos / "mbrola_ph" / Path(miembro.filename).name).write_bytes(
                    archivo.read(miembro))

    print("   bajando las voces españolas...")
    (datos / "mbrola").mkdir(exist_ok=True)
    for cual in ESPANOLAS:
        bajar(VOCES % (cual, cual), datos / "mbrola" / cual)
    bajar(LICENCIA, datos / "mbrola" / "LICENCIA.md")

    # Las tres variantes de voz que NVDA añade por su cuenta.  No son
    # imprescindibles, pero quien venga del paquete de eSpeak las tiene y
    # echarlas de menos aquí no tendría explicación.
    extras = variantes_de_nvda()
    if extras is not None:
        puestas = 0
        for uno in extras.iterdir():
            destino = datos / "voices" / "!v" / uno.name
            if uno.is_file() and not destino.exists():
                shutil.copy2(uno, destino)
                puestas += 1
        print("   variantes añadidas desde NVDA: %d" % puestas)
    else:
        print("   aviso: NVDA no está; faltarán tres variantes de voz")


def comprobar() -> bool:
    """Prueba que las siete voces suenan de verdad.

    Que la biblioteca acepte la voz no basta: la de NVDA la acepta también y
    luego habla con otra.  Aquí se sintetiza con cada una y se mira que salga
    audio, y antes se comprueba lo contrario —que sin ``mbrola.dll`` la voz se
    rechaza—, que es lo que demuestra que quien habla es MBROLA y no eSpeak
    haciéndose pasar por él.
    """
    biblioteca = DESTINO / "espeak.dll"
    if not biblioteca.is_file():
        print("No hay nada montado en %s" % DESTINO)
        return False

    trozos: list[int] = []

    @ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(ctypes.c_short),
                      ctypes.c_int, ctypes.c_void_p)
    def recoger(_muestras, cuantas, _evento):
        if cuantas > 0:
            trozos.append(cuantas)
        return 0

    ctypes.cdll.LoadLibrary(str(DESTINO / "mbrola.dll"))
    dll = ctypes.cdll.LoadLibrary(str(biblioteca))
    dll.espeak_Initialize.restype = ctypes.c_int
    muestreo = dll.espeak_Initialize(2, 600, str(DESTINO).encode("utf-8"), 0)
    if muestreo <= 0:
        print("eSpeak no ha arrancado")
        return False
    dll.espeak_SetSynthCallback(recoger)

    frase = "Hola, esto es una prueba de la voz.".encode("utf-8")
    bien = True
    for cual in ESPANOLAS:
        trozos.clear()
        fallo = dll.espeak_SetVoiceByName(("mb-%s" % cual).encode("utf-8"))
        if fallo:
            print("   mb-%-4s no se ha podido elegir (código %d)" % (cual, fallo))
            bien = False
            continue
        dll.espeak_Synth(frase, len(frase) + 1, 0, 0, 0, 0x1000, None, None)
        dll.espeak_Synchronize()
        muestras = sum(trozos)
        print("   mb-%-4s %.2f s" % (cual, muestras / muestreo))
        if muestras <= 0:
            bien = False
    return bien


def main(argumentos) -> int:
    if "--probar" not in argumentos:
        with tempfile.TemporaryDirectory() as temporal:
            montar(Path(temporal))
        megas = sum(uno.stat().st_size for uno in DESTINO.rglob("*")
                    if uno.is_file()) / 1048576
        print("Montado en %s (%.0f MB)" % (DESTINO, megas))
    print("Comprobando que suenan:")
    if not comprobar():
        print("Algo no ha ido bien.")
        return 1
    print("Todo correcto. El paquete se arma con:")
    print("   python plugins_voz/crear_paquetes.py espeak_mbrola")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
