# -*- coding: utf-8 -*-
"""Deja en ``adjuntos/vocalizer`` el motor de Vocalizer, en su versión de 64 bits.

**Qué es Vocalizer.**  El motor de síntesis de Nuance que llevan media docena de
lectores de pantalla y casi todos los móviles.  Suena a persona, va rápido,
aguanta velocidades altas y no necesita conexión.  En español las voces
habituales son Jorge, Marisol y Mónica, a 22 kHz.

**Qué se copia.**  El motor —la biblioteca, la capa de plataforma, el tiempo de
ejecución de Visual C++ que necesita y los datos comunes— y las voces que haya.

Cada voz va en su carpeta, con un nombre que la nombra: ``spe_jorge_premium-high``,
o sea idioma, voz y calidad.  A Vocalizer el nombre de la carpeta le da igual
—mira dentro y reconoce lo que hay, comprobado renombrando una— así que se
aprovecha para que diga algo, y para que las que ya están sirvan de plantilla a
quien añada la siguiente.

Con ``--sin-voces`` se prepara solo el motor, que son once megas.  Las voces
pesan de verdad: entre cien y quinientos megas cada una.

**Solo la de 64 bits.**  El controlador trae ``lib/x86`` y ``lib/AMD64``.  El
programa es de 64, así que la de 32 no serviría ni guardándola, y ocuparía otros
cuatro megas y medio.

**Licencia.**  Vocalizer y sus voces son de Nuance Communications y llevan su
propia licencia: hay que tenerla para usarlas.  Esta herramienta no instala
voces ni las reparte: prepara el motor a partir de lo que ya haya en el equipo.

Uso::

    python herramientas/vocalizer.py                    # motor y voces
    python herramientas/vocalizer.py --sin-voces        # solo el motor
    python herramientas/vocalizer.py --desde C:/ruta    # driver en otro sitio
    python herramientas/vocalizer.py --voces C:/voces   # voces en otro sitio
    python herramientas/vocalizer.py --probar           # solo comprobar

Después, el paquete se arma como los demás::

    python plugins_voz/crear_paquetes.py --reunir vocalizer
    python plugins_voz/crear_paquetes.py vocalizer
"""

from __future__ import annotations

import ctypes
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "adjuntos" / "vocalizer"

#: Dónde se busca el controlador si no se dice otra cosa.
POR_OMISION = Path(r"E:\Vocalizer\Driver\synthDrivers\vocalizer_expressive2")

#: Las tres bibliotecas, de la carpeta de 64 bits.
BIBLIOTECAS = ("ve.dll", "vplatform.dll", "msvcr110.dll")


def montar(origen: Path) -> None:
    """Copia el motor a ``adjuntos/vocalizer``."""
    lib = origen / "ve2" / "lib" / "AMD64"
    comunes = origen / "ve2" / "common"
    if not (lib / "ve.dll").is_file():
        raise SystemExit("no está la biblioteca de 64 bits en %s" % lib)
    if not comunes.is_dir():
        raise SystemExit("no están los datos comunes en %s" % comunes)

    # Se vacía por dentro y no se borra la carpeta: en Windows basta con que
    # alguien la tenga abierta para que borrarla falle.
    DESTINO.mkdir(parents=True, exist_ok=True)
    for uno in DESTINO.iterdir():
        if uno.is_dir():
            shutil.rmtree(uno, ignore_errors=True)
        else:
            uno.unlink(missing_ok=True)

    (DESTINO / "lib").mkdir()
    for nombre in BIBLIOTECAS:
        una = lib / nombre
        if not una.is_file():
            raise SystemExit("falta %s" % una)
        shutil.copy2(una, DESTINO / "lib" / nombre)
        print("   %-16s %.1f MB" % (nombre, una.stat().st_size / 1048576))
    shutil.copytree(comunes, DESTINO / "common")
    megas = sum(uno.stat().st_size for uno in (DESTINO / "common").rglob("*")
                if uno.is_file()) / 1048576
    print("   datos comunes    %.1f MB en %d archivos"
          % (megas, len(list((DESTINO / "common").iterdir()))))


def nombre_de_la_carpeta(voz: Path) -> str:
    """Cómo se llamará la carpeta de una voz dentro del paquete.

    A Vocalizer el nombre le da igual —mira dentro y reconoce lo que hay—, así
    que se aprovecha para que diga algo: se toma el del propio archivo de la voz
    quitándole la versión y la extensión.  De ``spe_jorge_premium-high_1-0-1.dat``
    sale ``spe_jorge_premium-high``: idioma, nombre y calidad.

    Si no aparece ese archivo se deja el nombre que traía la carpeta.  Vale más
    una carpeta con nombre feo que una voz que no se copia.
    """
    for dat in sorted(voz.rglob("*.dat")):
        partes = dat.stem.split("_")
        # El último trozo es la versión, del estilo «1-0-1».
        if len(partes) > 2 and partes[-1].replace("-", "").isdigit():
            partes = partes[:-1]
        return "_".join(partes)
    return voz.name


def copiar_voces(origen: Path) -> int:
    """Trae las voces al motor preparado, cada una en su carpeta con nombre.

    Se copia lo que haya: si una carpeta no es una voz, Vocalizer la ignorará
    luego y no pasa nada.  Aquí no se adivina, porque quien sabe reconocer una
    voz es él.
    """
    destino = DESTINO / "voces"
    destino.mkdir(exist_ok=True)
    cuantas = 0
    for una in sorted(origen.iterdir()):
        if not una.is_dir():
            continue
        como = nombre_de_la_carpeta(una)
        fin = destino / como
        if fin.exists():
            shutil.rmtree(fin, ignore_errors=True)
        shutil.copytree(una, fin)
        megas = sum(uno.stat().st_size for uno in fin.rglob("*")
                    if uno.is_file()) / 1048576
        print("   voz: %-34s %6.0f MB" % (como, megas))
        cuantas += 1
    return cuantas


def comprobar(voces: Path | None) -> bool:
    """Arranca el motor y enseña qué voces encuentra.

    Si se le dice dónde hay voces, se comprueba además que las ve y que las
    lista con su idioma. Sin voces también vale: el motor arranca igual, y es
    lo que hay que verificar antes de armar el paquete.
    """
    sys.path.insert(0, str(RAIZ / "plugins_voz" / "fuentes" / "vocalizer"))
    import importlib.util

    entrada = RAIZ / "plugins_voz" / "fuentes" / "vocalizer" / "motor.py"
    ficha = importlib.util.spec_from_file_location("motor_vocalizer", entrada)
    modulo = importlib.util.module_from_spec(ficha)
    ficha.loader.exec_module(modulo)

    # El adaptador busca las voces en «voces», dentro de su carpeta.  Para la
    # prueba se le apunta a las de verdad con el ajuste que existe para eso.
    ajustes = {"carpeta_extra": str(voces)} if voces else {}
    motor = modulo.crear(DESTINO, ajustes)
    if motor is None or not getattr(motor, "_ve", None):
        print("   el motor no ha arrancado")
        return False
    print("   motor arrancado, versión %s" % motor._version())
    lista = motor.voces()
    if not lista:
        print("   no encuentra ninguna voz (normal si aún no has copiado "
              "ninguna)")
        motor.cerrar()
        return True
    print("   voces que encuentra: %d" % len(lista))
    for nombre, idioma in motor.voces_con_idioma():
        print("      %-12s %-8s calidades: %s"
              % (nombre, idioma or "?",
                 ", ".join(motor._variantes_declaradas(nombre)) or "?"))
    motor.establecer_velocidad(0)
    motor.establecer_volumen(90)
    bien = bool(motor.decir("Hola, esta es la voz que leerá tus libros."))
    print("   habla: %s" % ("sí" if bien else "no"))
    import time

    time.sleep(3)
    motor.cerrar()
    return bien


def main(argumentos) -> int:
    origen = POR_OMISION
    if "--desde" in argumentos:
        origen = Path(argumentos[argumentos.index("--desde") + 1])
    voces = None
    if "--voces" in argumentos:
        voces = Path(argumentos[argumentos.index("--voces") + 1])
    elif Path(r"E:\Vocalizer\voces").is_dir():
        voces = Path(r"E:\Vocalizer\voces")

    if "--probar" not in argumentos:
        print("Montando el motor desde %s" % origen)
        montar(origen)
        if voces and voces.is_dir() and "--sin-voces" not in argumentos:
            print("Copiando las voces desde %s" % voces)
            print("   (son cientos de megas: tarda un rato)")
            cuantas = copiar_voces(voces)
            print("   %d voces copiadas" % cuantas)
        else:
            (DESTINO / "voces").mkdir(exist_ok=True)
            print("Sin voces: el paquete irá solo con el motor")
        total = sum(uno.stat().st_size for uno in DESTINO.rglob("*")
                    if uno.is_file()) / 1048576
        print("Montado en %s (%.0f MB)" % (DESTINO, total))
    print("Comprobando:")
    if not comprobar(voces):
        print("Algo no ha ido bien.")
        return 1
    print("Todo correcto. El paquete se arma con:")
    print("   python plugins_voz/crear_paquetes.py --reunir vocalizer")
    print("   python plugins_voz/crear_paquetes.py vocalizer")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
