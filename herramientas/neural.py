# -*- coding: utf-8 -*-
"""Deja en ``adjuntos/neural`` el motor de las voces neuronales de Microsoft.

**Qué es.**  El modo embebido de la biblioteca de voz de Microsoft: las voces
neuronales de sus servicios en línea, pero corriendo **dentro del equipo**.  Sin
conexión, sin que salga nada de aquí, y aguantando la velocidad alta bastante
mejor que la mayoría de voces neuronales.

**Qué se copia.**  Las ocho bibliotecas —el núcleo, el motor embebido, el
tiempo de ejecución de redes neuronales y las extensiones— más el envoltorio de
Python que las llama.  Son unos veinte megas.

Y **las voces**, con la licencia de cada una al lado.  Son unos ciento ochenta
megas entre las siete, y van dentro para que quien instale el motor lo tenga
todo y no haya que copiar nada a mano.  Las que se añadan después se detectan
solas, buscando cualquier carpeta que tenga un ``Tokens.xml``.

**La clave.**  Los modelos vienen cifrados y no se abren sin ella: sin clave las
voces se listan y no suenan.  Cada voz trae la suya al lado, en un archivo
``SynthModel.license`` —o ``SynthModel.key`` si es una clave—, que es donde la
busca el controlador de NVDA del que sale esto.  Se admite además una sola
para todas, en la carpeta ``licencia``.  Esta herramienta comprueba voz por voz
que la tenga, y avisa de las que no: una voz sin clave viaja en el paquete para
no sonar.

**Solo la de 64 bits.**  Las ocho bibliotecas lo son, así que no hay puente que
montar: se cargan directamente.

**Licencia.**  La biblioteca y las voces son de Microsoft y llevan la suya.  El
envoltorio de Python viene del complemento de NVDA de Александр Линьков, que es
GPL.  Esta herramienta no reparte voces ni claves: prepara el motor a partir de
lo que ya haya en el equipo.

Uso::

    python herramientas/neural.py                       # con el driver por omisión
    python herramientas/neural.py --desde C:/ruta       # si está en otro sitio
    python herramientas/neural.py --voces C:/voces      # si las voces están aparte
    python herramientas/neural.py --sin-voces           # solo la biblioteca
    python herramientas/neural.py --probar              # solo comprobar
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "adjuntos" / "neural"

#: Dónde se busca el controlador si no se dice otra cosa.
POR_OMISION = Path(r"E:\Neural-dev\driver\synthDrivers\NeuralVoices")

#: Y dónde están las voces, para poder comprobar con ellas.
VOCES_POR_OMISION = Path(r"E:\Neural-dev\voces")


def montar(origen: Path, voces: Path | None) -> None:
    """Copia a ``adjuntos/neural`` el motor y, si las hay, las voces."""
    api = origen / "speechapi"
    if not (api / "Microsoft.CognitiveServices.Speech.core.dll").is_file():
        raise SystemExit("no está la biblioteca de voz en %s" % api)

    # Se vacía por dentro y no se borra la carpeta: en Windows basta con que
    # alguien la tenga abierta para que borrarla falle.
    DESTINO.mkdir(parents=True, exist_ok=True)
    for uno in DESTINO.iterdir():
        if uno.is_dir():
            shutil.rmtree(uno, ignore_errors=True)
        else:
            uno.unlink(missing_ok=True)

    shutil.copytree(api, DESTINO / "speechapi")
    (DESTINO / "voces").mkdir(exist_ok=True)
    (DESTINO / "licencia").mkdir(exist_ok=True)

    cuantas = len(list((DESTINO / "speechapi").glob("*.dll")))
    megas = sum(uno.stat().st_size for uno in (DESTINO / "speechapi").rglob("*")
                if uno.is_file()) / 1048576
    print("   %d bibliotecas y su envoltorio, %.0f MB" % (cuantas, megas))

    if voces is not None and voces.is_dir():
        copiar_voces(voces)
    else:
        print("   sin voces: se ponen luego en la carpeta «voces» del motor")


def copiar_voces(origen: Path) -> int:
    """Trae las voces junto al motor, cada una con su licencia.

    Se copian tal como estén organizadas —sueltas o agrupadas por idioma—,
    porque el motor busca hasta el fondo y da igual.  Lo que sí se mira es que
    cada una traiga su clave: sin ella la voz se lista y no suena, y eso es
    mejor saberlo aquí que después de instalar.
    """
    destino = DESTINO / "voces"
    destino.mkdir(parents=True, exist_ok=True)
    copiadas, sin_clave = 0, []
    for ficha in sorted(origen.rglob("Tokens.xml")):
        # La raíz de la voz es la que contiene el «data»: subiendo desde el
        # «Tokens.xml», es la abuela.
        datos = ficha.parent
        raiz = datos.parent.parent if datos.parent.name == "data" else datos.parent
        # Y se conserva el árbol tal cual venía, desde la carpeta de voces.
        try:
            dentro = raiz.relative_to(origen)
        except ValueError:
            dentro = Path(raiz.name)
        fuera = destino / dentro
        if fuera.exists():
            shutil.rmtree(fuera, ignore_errors=True)
        fuera.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(raiz, fuera)
        copiadas += 1
        if not any((fuera / nombre).is_file()
                   for nombre in ("SynthModel.key", "SynthModel.license")):
            sin_clave.append(raiz.name)

    megas = sum(uno.stat().st_size for uno in destino.rglob("*")
                if uno.is_file()) / 1048576
    print("   %d voces, %.0f MB" % (copiadas, megas))
    if sin_clave:
        print("   AVISO: sin clave y por tanto mudas: %s" % ", ".join(sin_clave))
        print("   Deja su SynthModel.license junto a cada una y vuelve a montar.")
    return copiadas


def comprobar(voces: Path | None) -> bool:
    """Arranca el motor y enseña qué voces encuentra y si suenan.

    Sin la clave, las voces se listan y no suenan: eso no es un fallo de la
    preparación y se dice tal cual, porque es lo que hay que saber antes de
    armar el paquete.
    """
    if not (DESTINO / "speechapi").is_dir():
        print("No hay nada montado en %s" % DESTINO)
        return False

    import importlib.util

    entrada = RAIZ / "plugins_voz" / "fuentes" / "neural" / "motor.py"
    ficha = importlib.util.spec_from_file_location("motor_neural", entrada)
    modulo = importlib.util.module_from_spec(ficha)
    ficha.loader.exec_module(modulo)

    ajustes = {"carpeta_extra": str(voces)} if voces else {}
    motor = modulo.crear(DESTINO, ajustes)
    lista = motor.voces()
    if not lista:
        print("   no encuentra ninguna voz: %s" % (motor._fallo or "sin motivo"))
        # Sin voces montadas es lo esperable; con ellas montadas, es un fallo.
        return not (DESTINO / "voces").is_dir() or not any(
            (DESTINO / "voces").rglob("Tokens.xml"))
    print("   voces que encuentra: %d" % len(lista))
    for nombre, idioma in motor.voces_con_idioma():
        print("      %-22s %s" % (nombre, idioma))

    if motor._fallo:
        print()
        print("   AVISO: %s" % motor._fallo)
        print("   Las voces se ven pero no van a sonar hasta que esté la clave.")

    motor.establecer_velocidad(0)
    motor.establecer_volumen(90)
    suena = bool(motor.decir("Hola, esta es la voz que leerá tus libros."))
    print("   habla: %s" % ("sí" if suena else "no"))
    if suena:
        import time

        time.sleep(3)
    motor.cerrar()
    # Sin clave no puede sonar, y eso no lo arregla esta herramienta: se da por
    # buena la preparación y se dice lo que falta.
    return suena or bool(motor._fallo)


def main(argumentos) -> int:
    origen = POR_OMISION
    if "--desde" in argumentos:
        origen = Path(argumentos[argumentos.index("--desde") + 1])
    voces = None
    if "--voces" in argumentos:
        voces = Path(argumentos[argumentos.index("--voces") + 1])
    elif VOCES_POR_OMISION.is_dir():
        voces = VOCES_POR_OMISION
    if "--sin-voces" in argumentos:
        voces = None

    if "--probar" not in argumentos:
        print("Montando el motor desde %s" % origen)
        montar(origen, voces)
        total = sum(uno.stat().st_size for uno in DESTINO.rglob("*")
                    if uno.is_file()) / 1048576
        print("Montado en %s (%.0f MB)" % (DESTINO, total))
    # Ya montadas, se comprueban las que van dentro: es lo que va a encontrarse
    # quien instale el paquete, y es eso lo que interesa saber si suena.
    print("Comprobando:")
    if not comprobar(None):
        print("Algo no ha ido bien.")
        return 1
    print()
    print("El paquete se arma con:")
    print("   python plugins_voz/crear_paquetes.py --reunir neural")
    print("   python plugins_voz/crear_paquetes.py neural")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
