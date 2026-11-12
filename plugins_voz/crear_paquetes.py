# -*- coding: utf-8 -*-
"""Construye los paquetes de motor de voz. Se ejecuta y ya está.

    python plugins_voz/crear_paquetes.py

Un paquete no se escribe a mano: se **arma** juntando tres cosas.

1. El **adaptador**, que es código propio y vive en ``fuentes/<motor>``, aquí al
   lado. Es lo único que hay que escribir: unas doscientas líneas que traducen
   entre lo que el visor le pide a una voz y lo que ese motor sabe hacer.
2. El **motor de verdad**, que se trae de ``RSS-TTS-CODEX`` —la otra aplicación
   del mismo autor, donde estos motores ya estaban escritos y probados—.
3. Los **binarios y las voces**, que son la parte gorda.

Cada motor con sus propios nombres
----------------------------------

En la aplicación de origen los motores viven cada uno en su carpeta, así que dos
pueden tener un ``provider.py`` y un ``catalog.py`` sin estorbarse. Aquí cada
paquete es una carpeta plana y **todo lleva el prefijo de su motor**:
``eloq_engine``, ``glocal_bridge``, ``edgeol_catalog``. No es cosmética:

* Dos paquetes instalados a la vez tendrían módulos llamados igual, y el segundo
  en cargarse taparía al primero. Se vería como que las voces de uno salen con
  el nombre del otro, que es la clase de fallo que parece funcionar.
* Al mirar la carpeta de un motor instalado se ve de quién es cada archivo. Con
  nombres genéricos, un ``catalog.pyc`` suelto no dice nada.

Los nombres se ponen aquí y las importaciones de dentro se reescriben solas: los
módulos que se traen no se editan a mano nunca.

Van compilados
--------------

Dentro del paquete no hay código fuente: los ``.py`` se convierten en ``.pyc``
al armarlo. El paquete sigue siendo un ZIP que cualquiera puede abrir para ver
qué archivos trae, pero el código ya no se lee de un vistazo.

Eso ata el paquete a **la versión de Python del programa**: un ``.pyc`` de
Python 3.15 no lo carga Python 3.16, y no a medias sino nada. Por eso el
manifiesto declara con qué versión se compiló y el instalador lo comprueba antes
de copiar nada.

Cómo queda la carpeta::

    plugins_voz/
        crear_paquetes.py       esto
        fuentes/<motor>/        el código de cada motor: motor.py y motor.json
        <motor>.motorvoz        el paquete ya armado, listo para instalar

Uso::

    python plugins_voz/crear_paquetes.py                  # todos
    python plugins_voz/crear_paquetes.py eloquence        # solo ese
    python plugins_voz/crear_paquetes.py --origen D:/RSS-TTS-CODEX
    python plugins_voz/crear_paquetes.py --sin-compilar   # deja el fuente
    python plugins_voz/crear_paquetes.py --listar         # qué se puede armar

**Hay que ejecutarlo con el Python del propio visor** —``entorno/Scripts/python.exe``—
y no con cualquiera: los paquetes salen compilados, y el bytecode solo lo carga
la versión de Python con la que se compiló.
"""

from __future__ import annotations

import io
import json
import py_compile
import re
import shutil
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

#: Dónde está la otra aplicación, de la que salen los motores ya escritos.
ORIGEN_POR_OMISION = Path("E:/Antigravity/RSS-TTS-CODEX")

#: Y dónde está NVDA, de donde sale eSpeak.  Se miran los dos sitios de siempre;
#: si está en otro, se le dice con ``--nvda``.
NVDA_POSIBLES = (
    Path("C:/Program Files/NVDA"),
    Path("C:/Program Files (x86)/NVDA"),
)


#: Y dónde deja la herramienta lo del motor MBROLA.  No sale de NVDA: la
#: biblioteca de NVDA está compilada sin MBROLA y no vale.
MBROLA_PREPARADO = RAIZ / "adjuntos" / "espeak_mbrola"


def carpeta_de_mbrola() -> Path | None:
    """Dónde está lo del motor MBROLA, ya preparado, o ``None``."""
    if (MBROLA_PREPARADO / "espeak.dll").is_file() and \
            (MBROLA_PREPARADO / "mbrola.dll").is_file():
        return MBROLA_PREPARADO
    return None


def voces_de_mbrola(carpeta: Path) -> int:
    """Cuántas voces MBROLA lleva la carpeta preparada."""
    donde = carpeta / "espeak-ng-data" / "mbrola"
    if not donde.is_dir():
        return 0
    return len([uno for uno in donde.iterdir()
                if uno.is_file() and uno.suffix == ""])


def completar_mbrola(datos: dict, trabajo: Path) -> None:
    """Mete en el manifiesto las variantes, igual que en eSpeak."""
    completar_espeak(datos, trabajo)
    print("   voces MBROLA incluidas: %d" % voces_de_mbrola(trabajo))


def carpeta_de_nvda(pedida=None) -> Path | None:
    """Dónde está la instalación de NVDA, o ``None`` si no aparece."""
    if pedida:
        camino = Path(pedida)
        return camino if (camino / "synthDrivers" / "espeak.dll").is_file() else None
    for camino in NVDA_POSIBLES:
        if (camino / "synthDrivers" / "espeak.dll").is_file():
            return camino
    return None


def variantes_de_espeak(carpeta: Path) -> list:
    """Las variantes de voz, leídas de sus archivos como hace NVDA.

    Cada variante es un archivo de texto y su nombre está en la línea ``name``.
    Se leen en latín-1 y no en UTF-8, igual que NVDA: la codificación de estos
    archivos no está declarada en ninguna parte y así al menos no revientan.
    """
    salida = [{"valor": "none", "texto": "Sin variante"}]
    donde = carpeta / "espeak-ng-data" / "voices" / "!v"
    if not donde.is_dir():
        return salida
    for archivo in sorted(donde.iterdir(), key=lambda uno: uno.name.lower()):
        if not archivo.is_file():
            continue
        nombre = None
        try:
            with archivo.open("r", encoding="latin-1") as texto:
                for linea in texto:
                    if linea.startswith("name "):
                        partes = linea.split(" ")
                        if len(partes) == 2:
                            nombre = partes[1].rstrip()
                        break
        except OSError:
            continue
        if nombre:
            salida.append({"valor": archivo.name, "texto": nombre})
    return salida


def completar_espeak(datos: dict, trabajo: Path) -> None:
    """Mete en el manifiesto las variantes que trae esta instalación."""
    variantes = variantes_de_espeak(trabajo)
    for ajuste in datos.get("ajustes", []):
        if ajuste.get("clave") == "variante":
            ajuste["opciones"] = variantes
    print("   variantes encontradas: %d" % (len(variantes) - 1))

#: Dónde se escribe el adaptador de cada motor, que es lo único propio.
FUENTES = Path(__file__).resolve().parent / "fuentes"

#: Y dónde quedan los paquetes ya armados.
DESTINO = Path(__file__).resolve().parent

#: Extensión de un paquete.
EXTENSION = ".motorvoz"


class Receta:
    """Cómo se arma un paquete: qué se trae, con qué nombre y de dónde.

    :param identificador: El del motor. Es el nombre de su carpeta al instalarse.
    :param prefijo: Con qué empiezan todos sus módulos.
    :param modulo: El punto de entrada, el que trae la función ``crear``.
    :param modulos: ``{nombre_logico: ruta_en_el_origen}``. El nombre lógico es
        con el que los módulos se importan entre sí allí; aquí pasa a ser
        ``<prefijo>_<nombre>``.
    :param rutas: Contenido del módulo de rutas del paquete, que dice dónde está
        cada cosa una vez instalado.
    :param datos: ``{nombre_destino: ruta_en_el_origen}`` de carpetas enteras.
    :param archivos: ``{ruta_destino: ruta_en_el_origen}`` de archivos sueltos.
    :param vendor: Carpeta de dependencias que se copia tal cual, si la hay.
    :param pip: Bibliotecas que se traen con pip y se meten dentro del paquete.
    """

    def __init__(self, identificador, prefijo, modulo, modulos, rutas,
                 datos=None, archivos=None, vendor=None, pip=(),
                 completar=None, descargas=(), reunido=None) -> None:
        self.identificador = identificador
        self.prefijo = prefijo
        self.modulo = modulo
        self.modulos = dict(modulos)
        self.rutas = rutas
        self.datos = dict(datos or {})
        self.archivos = dict(archivos or {})
        self.vendor = vendor
        #: Bibliotecas de terceros que hay que traer con pip y meter dentro del
        #: paquete.  Van en su propia carpeta y el adaptador la añade a la ruta
        #: de importación: así el visor no carga con ellas si nadie usa este
        #: motor.
        self.pip = tuple(pip)
        #: Lo que hay que **bajar de internet** para armar el paquete, como
        #: ``(url, qué hacer con ello)``.  Solo lo usa RHVoice, que es libre y
        #: se publica en sus repositorios en vez de estar ya en el equipo.
        self.descargas = tuple(descargas)
        #: Función que completa el manifiesto con lo que solo se sabe al armar.
        #: eSpeak la usa para sus variantes, que son archivos de la instalación
        #: y no una lista que se pueda escribir a mano.
        self.completar = completar
        #: Y lo que hay que hacer con lo reunido antes de darlo por bueno.
        #: RHVoice la usa: se baja como complemento de NVDA, que trae las dos
        #: arquitecturas y un montón de cosas que aquí no pintan nada.
        self.reunido = reunido

    def nombre_de(self, logico: str) -> str:
        """Con qué nombre queda un módulo dentro del paquete."""
        return "%s_%s" % (self.prefijo, logico)


def _sin_paquete(texto: str) -> str:
    """Deja las importaciones de un módulo que ya no vive dentro de un paquete.

    En la aplicación de origen estos módulos son parte de ``rss_tts.tts``, así
    que se importan unos a otros con puntos: ``from ..base import``. Aquí van
    sueltos en una carpeta, y esos puntos no significan nada.
    """
    texto = re.sub(r"^from \.\.?\.?paths import", "from paths import", texto,
                   flags=re.MULTILINE)
    texto = re.sub(r"^from \.\.\.(\w[\w.]*) import", r"from \1 import", texto,
                   flags=re.MULTILINE)
    texto = re.sub(r"^from \.\.(\w[\w.]*) import", r"from \1 import", texto,
                   flags=re.MULTILINE)
    texto = re.sub(r"^from \.(\w[\w.]*) import", r"from \1 import", texto,
                   flags=re.MULTILINE)
    texto = re.sub(r"^from \. import", "import", texto, flags=re.MULTILINE)
    return texto


def _con_prefijo(texto: str, receta: Receta) -> str:
    """Reescribe las importaciones para que apunten a los nombres de este motor.

    Se hace sobre las importaciones y no con un reemplazo a lo bruto: ``catalog``
    aparece también dentro del código como palabra corriente, y cambiarla ahí
    rompería el módulo.
    """
    nombres = dict(receta.modulos)
    nombres["paths"] = None                     # el módulo de rutas del paquete
    if receta.vendor:
        # Las dependencias que el motor trae consigo también se renombran: dos
        # paquetes pueden traer cada uno su versión de la misma biblioteca, y
        # con el mismo nombre el segundo se comería al primero.
        nombres["_vendor"] = None
    for logico in nombres:
        if logico == "paths":
            nuevo = receta.nombre_de("rutas")
        elif logico == "_vendor":
            nuevo = receta.prefijo + "_vendor"
        else:
            nuevo = receta.nombre_de(logico)
        # La sangría se conserva: una importación dentro de una función va
        # indentada, y hay motivos para ponerla ahí —un paquete que solo carga
        # lo que de verdad va a usar—.  Sin esto se quedaban justo esas sin
        # reescribir, y el módulo «no aparecía» al arrancar el motor.
        texto = re.sub(r"^([ \t]*)from %s import" % re.escape(logico),
                       r"\1from %s import" % nuevo, texto, flags=re.MULTILINE)
        texto = re.sub(r"^([ \t]*)import %s$" % re.escape(logico),
                       r"\1import %s as %s" % (nuevo, logico), texto,
                       flags=re.MULTILINE)
        texto = re.sub(r"^([ \t]*)from %s\." % re.escape(logico),
                       r"\1from %s." % nuevo, texto, flags=re.MULTILINE)
    return texto


#: Cómo se reparte lo de un motor dentro de su carpeta de fuentes.  Cada clase
#: de cosa en su sitio, para que se vea de un vistazo qué trae un motor.
CODIGO = "codigo"          # los módulos que se importan
DATOS = "datos"            # las carpetas de datos y de voces
ARCHIVOS = "archivos"      # los binarios sueltos, con su ruta de destino
VENDOR = "vendor"          # dependencias que vienen con el motor
BIBLIOTECA = "biblioteca"  # dependencias que se traen con pip


def reunir(receta: Receta, origen: Path) -> None:
    """Trae a ``fuentes/<motor>`` todo lo que ese motor necesita.

    Es el paso que se hace una vez, en el equipo que tenga los orígenes a mano.
    Después, armar el paquete no necesita nada más que esta carpeta.

    Los módulos se copian **tal cual**, sin tocarles las importaciones.  Se
    reescriben al armar, que es cuando se sabe con qué prefijo va cada uno;
    guardarlos ya reescritos ataría esta carpeta a un prefijo y haría imposible
    volver a traerlos cuando cambien en su origen.
    """
    fuente = FUENTES / receta.identificador
    if not (fuente / "motor.py").is_file():
        raise SystemExit("falta el adaptador en %s" % fuente)

    for cual in (CODIGO, DATOS, ARCHIVOS, VENDOR, BIBLIOTECA):
        shutil.rmtree(fuente / cual, ignore_errors=True)

    # Lo que se baja va primero: lo que traiga ya está en su sitio y no hay
    # que ir a buscarlo a ninguna parte. RHVoice es entero así.
    if receta.descargas:
        _traer_de_internet(receta, fuente)
    if receta.reunido is not None:
        receta.reunido(fuente)

    cuantos = 0
    for logico, relativa in receta.modulos.items():
        camino = origen / relativa
        if not camino.is_file():
            raise SystemExit("falta %s" % camino)
        salida = fuente / CODIGO / (logico + ".py")
        salida.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(camino, salida)
        cuantos += 1
    if cuantos:
        print("   código: %d módulos" % cuantos)

    for destino, relativa in receta.datos.items():
        if (fuente / DATOS / destino).is_dir():
            continue          # ya lo ha dejado la descarga
        camino = origen / relativa
        if not camino.is_dir():
            raise SystemExit("falta la carpeta %s" % camino)
        shutil.copytree(camino, fuente / DATOS / destino, dirs_exist_ok=True)
        print("   datos: %s" % destino)

    for destino, relativa in receta.archivos.items():
        if (fuente / ARCHIVOS / destino).is_file():
            continue          # ya lo ha dejado la descarga
        camino = origen / relativa
        if not camino.is_file():
            raise SystemExit("falta %s" % camino)
        salida = fuente / ARCHIVOS / destino
        salida.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(camino, salida)
        print("   archivo: %s" % destino)

    if receta.vendor:
        camino = origen / receta.vendor
        if camino.is_dir():
            shutil.copytree(camino, fuente / VENDOR, dirs_exist_ok=True)
            print("   dependencias que vienen con el motor")

    if receta.pip:
        _traer_con_pip(receta, fuente / BIBLIOTECA)
        print("   dependencias de pip: %s" % ", ".join(receta.pip))

    megas = sum(uno.stat().st_size for uno in fuente.rglob("*")
                if uno.is_file()) / 1048576
    print("   reunido en %s (%.1f MB)" % (fuente, megas))


def armar(receta: Receta, compilar: bool = True) -> Path:
    """Arma el paquete de un motor y lo deja en ``plugins_voz``.

    Lee **solo** de ``fuentes/<motor>``.  No necesita la aplicación de origen,
    ni NVDA, ni conexión: eso es cosa de reunir, y ya está hecho.
    """
    fuente = FUENTES / receta.identificador
    entrada = fuente / "motor.py"
    if not entrada.is_file():
        raise SystemExit("falta el adaptador en %s" % fuente)
    trabajo = RAIZ / "data" / "temp" / ("paquete_" + receta.identificador)
    if trabajo.exists():
        shutil.rmtree(trabajo)
    trabajo.mkdir(parents=True)

    # -- el adaptador, con el nombre de módulo que declara el manifiesto ------
    texto = _con_prefijo(entrada.read_text(encoding="utf-8"), receta)
    (trabajo / (receta.modulo + ".py")).write_text(texto, encoding="utf-8")

    # -- el módulo de rutas, que es distinto en cada paquete ------------------
    (trabajo / (receta.nombre_de("rutas") + ".py")).write_text(
        receta.rutas, encoding="utf-8")

    # -- los módulos que se traen --------------------------------------------
    # Aquí es donde se les cambia el nombre y se les reescriben las
    # importaciones: en las fuentes están tal como vinieron de su origen.
    for logico in receta.modulos:
        camino = fuente / CODIGO / (logico + ".py")
        if not camino.is_file():
            raise SystemExit(_falta(camino, receta))
        contenido = _con_prefijo(_sin_paquete(camino.read_text(encoding="utf-8")),
                                 receta)
        (trabajo / (receta.nombre_de(logico) + ".py")).write_text(
            contenido, encoding="utf-8")

    # -- los datos y los binarios --------------------------------------------
    for destino in receta.datos:
        camino = fuente / DATOS / destino
        if not camino.is_dir():
            raise SystemExit(_falta(camino, receta))
        shutil.copytree(camino, trabajo / destino, dirs_exist_ok=True)
    for destino in receta.archivos:
        camino = fuente / ARCHIVOS / destino
        if not camino.is_file():
            raise SystemExit(_falta(camino, receta))
        salida = trabajo / destino
        salida.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(camino, salida)
    if receta.vendor and (fuente / VENDOR).is_dir():
        shutil.copytree(fuente / VENDOR, trabajo / (receta.prefijo + "_vendor"),
                        dirs_exist_ok=True)
    if receta.pip:
        camino = fuente / BIBLIOTECA
        if not camino.is_dir():
            raise SystemExit(_falta(camino, receta))
        shutil.copytree(camino, trabajo / (receta.prefijo + "_deps"),
                        dirs_exist_ok=True)

    # -- el manifiesto, con la versión de Python con la que se compila --------
    datos = json.loads((fuente / "motor.json").read_text(encoding="utf-8"))
    if receta.completar is not None:
        receta.completar(datos, trabajo)
    datos["modulo"] = receta.modulo
    # Lo que este motor necesita de Python, leído de su propio código.  El
    # compilador del programa lee esto para meterlo en el ejecutable: sin ello,
    # un motor que use algo poco común arranca en desarrollo y falla compilado.
    datos["necesita"] = modulos_que_necesita(trabajo)
    print("   necesita %d módulos de Python" % len(datos["necesita"]))
    datos["python"] = "%d.%d" % sys.version_info[:2] if compilar else ""
    (trabajo / "motor.json").write_text(
        json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if compilar:
        _compilar(trabajo)
    salida = comprimir(trabajo, DESTINO / (receta.identificador + EXTENSION))
    shutil.rmtree(trabajo, ignore_errors=True)
    return salida


def _traer_con_pip(receta: Receta, destino: Path) -> None:
    """Instala dentro del paquete las bibliotecas que el motor necesita.

    Se instalan con **el mismo Python del visor**, que es lo que garantiza que
    valgan: pip elige entonces las versiones que sirven para esa versión, y si
    alguna trae partes compiladas coge la variante sin ellas.

    ``AIOHTTP_NO_EXTENSIONS`` va puesto a propósito: sin eso, pip intentaría
    compilar las partes en C de aiohttp, lo que pide un compilador instalado y
    ataría el resultado a la versión de Python de quien arme el paquete.
    """
    import os
    import subprocess

    entorno = dict(os.environ, AIOHTTP_NO_EXTENSIONS="1")
    orden = [sys.executable, "-m", "pip", "install", *receta.pip,
             "--target", str(destino), "--no-compile", "--quiet",
             "--disable-pip-version-check"]
    resultado = subprocess.run(orden, env=entorno, capture_output=True,
                               text=True)
    if resultado.returncode:
        raise SystemExit("pip ha fallado: %s" % (resultado.stderr or "").strip()[:200])
    # Fuera lo que no hace falta para funcionar: los metadatos de instalación y
    # los guiones de línea de órdenes son megas que nadie va a usar.
    for basura in list(destino.glob("*.dist-info")) + list(destino.glob("bin")):
        shutil.rmtree(basura, ignore_errors=True)


def _traer_de_internet(receta: Receta, fuente: Path) -> None:
    """Baja lo que el paquete necesite y lo deja donde toca.

    Cada descarga dice su dirección y en qué carpeta del paquete se
    descomprime. Si no hay conexión se para aquí y se dice: es preferible no
    tener el paquete a tenerlo sin voces, que es lo mismo pero descubierto más
    tarde.
    """
    import urllib.request
    import zipfile

    for direccion, destino in receta.descargas:
        salida = fuente / destino
        salida.mkdir(parents=True, exist_ok=True)
        print("   bajando %s" % direccion.rsplit("/", 1)[-1])
        try:
            peticion = urllib.request.Request(
                direccion, headers={"User-Agent": "VisorUniversal"})
            datos = urllib.request.urlopen(peticion, timeout=300).read()
        except Exception as error:
            raise SystemExit("no se ha podido bajar %s: %s" % (direccion, error))
        try:
            with zipfile.ZipFile(io.BytesIO(datos)) as paquete:
                for interno in paquete.infolist():
                    if interno.is_dir():
                        continue
                    nombre = interno.filename.replace("\\", "/")
                    if ".." in nombre.split("/") or nombre.startswith("/"):
                        continue
                    fin = salida / nombre
                    fin.parent.mkdir(parents=True, exist_ok=True)
                    with paquete.open(interno) as origen, fin.open("wb") as escribir:
                        shutil.copyfileobj(origen, escribir)
        except zipfile.BadZipFile:
            raise SystemExit("lo bajado de %s no es un ZIP" % direccion)


def _falta(camino: Path, receta: Receta) -> str:
    """El aviso de cuando falta una pieza, con lo que hay que hacer.

    Falta siempre por lo mismo: nadie ha reunido las fuentes de ese motor en
    este equipo.  Decirlo así ahorra ir a buscar por qué.
    """
    return ("falta %s\n"
            "   Las fuentes de este motor no están reunidas. Se traen con:\n"
            "      python plugins_voz/crear_paquetes.py --reunir %s"
            % (camino, receta.identificador))


#: Módulos que un motor puede necesitar sin que se vea en sus importaciones:
#: los que se cargan por su nombre, en una cadena, y que ningún analizador
#: encuentra.  Se añaden a lo que se detecte.
SIEMPRE = ("encodings.idna", "encodings.utf_8", "encodings.latin_1")


def modulos_que_necesita(carpeta: Path) -> list:
    """Qué módulos de Python importa el código de un paquete.

    Se lee el árbol de sintaxis de cada archivo, que es lo único fiable: buscar
    la palabra «import» con una expresión regular se traga los que están dentro
    de una cadena y se deja los que van con sangría.

    Se apuntan **con su paquete raíz y completos**: ``http.server`` hace falta
    entero, y anotar solo ``http`` no basta porque cx_Freeze incluye el paquete
    sin sus submódulos.
    """
    import ast

    propios = _lo_que_trae(carpeta)
    salida: set = set(SIEMPRE)
    for archivo in sorted(carpeta.rglob("*.py")):
        try:
            arbol = ast.parse(archivo.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                nombres = [alias.name for alias in nodo.names]
            elif isinstance(nodo, ast.ImportFrom):
                # Las relativas son del propio paquete y no se apuntan.
                nombres = [nodo.module] if nodo.module and not nodo.level else []
            else:
                continue
            for nombre in nombres:
                raiz = nombre.split(".")[0]
                if raiz in propios or raiz in ("basskit",):
                    continue
                salida.add(nombre)
    return sorted(salida)


def _lo_que_trae(carpeta: Path) -> set:
    """Nombres de módulo que el propio paquete aporta.

    No hay que pedirle al compilador lo que ya viaja dentro: el motor de Edge
    lleva su ``aiohttp`` y su ``certifi``, y pedirlos rompía la compilación
    porque en el entorno del visor no están.

    Se miran **todas** las carpetas, no solo la raíz, porque un motor puede
    poner en la ruta de búsqueda la subcarpeta donde guarda sus dependencias, y
    entonces lo que hay ahí dentro también se importa por su nombre a secas.
    """
    salida: set = set()
    for donde in [carpeta] + [uno for uno in carpeta.rglob("*") if uno.is_dir()]:
        for cosa in donde.iterdir():
            if cosa.is_dir():
                salida.add(cosa.name)
            elif cosa.suffix in (".py", ".pyc", ".pyd", ".so"):
                salida.add(cosa.name.split(".")[0])
    return salida


def _compilar(carpeta: Path) -> int:
    """Convierte a bytecode los módulos del paquete y borra el fuente.

    Se compila **al lado** de cada archivo y no en ``__pycache__``, que es lo
    que espera un módulo que se importa por su ruta. Y se comprueba uno a uno:
    un módulo que no compila tiene un error de sintaxis, y armar el paquete con
    él dentro sería empaquetar algo que no puede funcionar.
    """
    cuantos = 0
    for uno in sorted(carpeta.rglob("*.py")):
        try:
            py_compile.compile(str(uno), cfile=str(uno.with_suffix(".pyc")),
                               doraise=True, optimize=0)
        except py_compile.PyCompileError as error:
            raise SystemExit("no compila %s: %s" % (uno.name, error))
        uno.unlink()
        cuantos += 1
    for basura in carpeta.rglob("__pycache__"):
        shutil.rmtree(basura, ignore_errors=True)
    return cuantos


def comprimir(carpeta: Path, salida: Path) -> Path:
    """Mete la carpeta en un solo archivo.

    Se comprime con ``deflate`` a propósito: un paquete es un ZIP corriente para
    que cualquiera pueda abrirlo y mirar qué lleva antes de instalarlo.
    """
    salida.parent.mkdir(parents=True, exist_ok=True)
    if salida.exists():
        salida.unlink()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zip:
        for uno in sorted(carpeta.rglob("*")):
            if uno.is_file() and "__pycache__" not in uno.parts:
                zip.write(uno, uno.relative_to(carpeta).as_posix())
    return salida


def _rutas(prefijo: str, lineas: str) -> str:
    return '''# -*- coding: utf-8 -*-
"""Dónde está cada cosa dentro del paquete ya instalado.

En la aplicación de origen estas rutas apuntaban a carpetas suyas. Aquí todo
vive dentro de la carpeta del propio motor, que es lo que hace que instalarlo y
quitarlo sea copiar y borrar una carpeta y nada más.
"""
from pathlib import Path

AQUI = Path(__file__).resolve().parent
%s
''' % lineas


# ---------------------------------------------------------------------------
# Las recetas
# ---------------------------------------------------------------------------

RECETAS = {}

def completar_eloquence(_datos: dict, trabajo) -> None:
    """Deja el ECI.INI del paquete sin la ruta del equipo donde se armó.

    Tal como viene de su origen, cada línea ``Path=`` trae la ruta absoluta de
    la carpeta de voces **de ese equipo**, que en cualquier otro no existe. El
    motor la reescribe al activarse (``assets.update_eci_ini``), pero repartir
    el archivo con la ruta de un disco ajeno es pedir que el día que esa
    reescritura no se pueda hacer —un ECI.INI de solo lectura— el motor busque
    las voces en una unidad E que aquí es un lápiz de memoria de otro.

    Así que en el paquete van **los nombres a secas**. El proceso de 32 bits
    arranca siempre con la carpeta de las voces como directorio de trabajo, de
    modo que un nombre suelto se resuelve solo, y esa es la red que queda
    debajo de todo lo demás.
    """
    ini = trabajo / "voces_eloquence" / "ECI.INI"
    if not ini.is_file():
        raise SystemExit("falta el ECI.INI de Eloquence: %s" % ini)
    crudo = ini.read_bytes()
    try:
        texto = crudo.decode("cp1252", errors="strict")
    except UnicodeDecodeError:
        raise SystemExit("el ECI.INI de Eloquence no se puede leer como ANSI")

    def _solo_el_nombre(linea):
        clave, _igual, valor = linea.group(0).partition("=")
        return "%s=%s" % (clave, re.split(r"[\\/]", valor.strip().strip('"'))[-1])

    limpio = re.sub(r"^\s*Path(?:_Rom)?\s*=.*$", _solo_el_nombre, texto,
                    flags=re.MULTILINE | re.IGNORECASE)
    if limpio != texto:
        ini.write_bytes(limpio.encode("cp1252"))
        print("   ECI.INI: rutas de voces dejadas en nombres sueltos")


RECETAS["eloquence"] = Receta(
    identificador="eloquence",
    prefijo="eloq",
    modulo="motor_eloquence",
    modulos={
        "base": "rss_tts/tts/base.py",
        "bass_session": "rss_tts/tts/bass_session.py",
        "assets": "rss_tts/tts/eloquence/assets.py",
        "eci_proxy": "rss_tts/tts/eloquence/eci_proxy.py",
        "engine": "rss_tts/tts/eloquence/engine.py",
        "ipc_client": "rss_tts/tts/eloquence/ipc_client.py",
        "provider": "rss_tts/tts/eloquence/provider.py",
    },
    rutas=_rutas("eloq", 'LIB_DIR = AQUI / "puente32"\n'
                         'ELOQUENCE_DATA_DIR = AQUI / "voces_eloquence"'),
    datos={"voces_eloquence": "data/eloquence"},
    archivos={"puente32/ibmtts_host32.dll": "lib/ibmtts_host32.dll"},
    completar=completar_eloquence,
)


def preparar_puente_acapela(fuente: Path) -> None:
    """Compila el puente x86 propio, sin traer ni ejecutar nada de Acapela."""
    import subprocess

    manifiesto = fuente / "puente32_src" / "Cargo.toml"
    if not manifiesto.is_file():
        raise SystemExit("falta el fuente del puente Acapela: %s" % manifiesto)
    destino_compilacion = RAIZ / "data" / "temp" / "acapela_host32_rust"
    orden = [
        "cargo", "build", "--release", "--target", "i686-pc-windows-msvc",
        "--manifest-path", str(manifiesto),
        "--target-dir", str(destino_compilacion),
    ]
    # Cargo solo busca `.cargo/config.toml` desde el directorio de trabajo y
    # sus padres, no desde `--manifest-path`. Entrar aquí aplica el CRT estático
    # del puente x86 y evita pedir el redistribuible de Visual C++ al usuario.
    resultado = subprocess.run(orden, cwd=fuente / "puente32_src",
                               capture_output=True, text=True)
    if resultado.returncode:
        detalle = (resultado.stderr or resultado.stdout or "").strip()
        raise SystemExit("no se ha podido compilar el puente x86 de Acapela:\n%s"
                         % detalle[-4000:])
    compilado = (destino_compilacion / "i686-pc-windows-msvc" / "release"
                 / "acapela_host32.exe")
    if not compilado.is_file():
        raise SystemExit("Cargo no ha producido %s" % compilado)
    salida = fuente / ARCHIVOS / "puente32" / "acapela_host32.exe"
    salida.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(compilado, salida)
    print("   puente Acapela: x86, compilado desde el fuente Rust del proyecto")


def completar_acapela(_datos: dict, trabajo: Path) -> None:
    """Incluye el análisis sin meter DLL ni voces propietarias."""
    for nombre in ("ANALISIS_Y_USO.md", "SOLICITUD_SDK_ACAPELA.md"):
        documento = FUENTES / "acapela" / nombre
        if documento.is_file():
            shutil.copy2(documento, trabajo / nombre)


RECETAS["acapela"] = Receta(
    identificador="acapela",
    prefijo="aca",
    modulo="motor_acapela",
    modulos={},
    rutas=_rutas("aca", 'HOST32 = AQUI / "puente32" / "acapela_host32.exe"'),
    # El valor de origen solo documenta el nombre. ``preparar_puente_acapela``
    # lo compila dentro de las fuentes antes de que reunir llegue a copiarlo.
    archivos={"puente32/acapela_host32.exe": "acapela_host32.exe"},
    completar=completar_acapela,
    reunido=preparar_puente_acapela,
)

RECETAS["google_local"] = Receta(
    identificador="google_local",
    prefijo="glocal",
    modulo="motor_google_local",
    modulos={
        "base": "rss_tts/tts/base.py",
        "bass_session": "rss_tts/tts/bass_session.py",
        "cache": "rss_tts/tts/cache.py",
        "pcm_provider": "rss_tts/tts/pcm_provider.py",
        "assets": "rss_tts/tts/google_chrome/assets.py",
        "bridge": "rss_tts/tts/google_chrome/bridge.py",
        "catalog": "rss_tts/tts/google_chrome/catalog.py",
        "provider": "rss_tts/tts/google_chrome/provider.py",
        "voice_store": "rss_tts/tts/google_chrome/voice_store.py",
    },
    rutas=_rutas("glocal",
                 'GOOGLE_TTS_DATA_DIR = AQUI / "voces_google"\n'
                 'TTS_CACHE_DIR = AQUI / "cache"'),
    datos={"voces_google": "data/google_tts"},
    vendor="rss_tts/tts/google_chrome/_vendor",
)

RECETAS["edge_online"] = Receta(
    identificador="edge_online",
    prefijo="edgeol",
    modulo="motor_edge_online",
    modulos={
        "base": "rss_tts/tts/base.py",
        "bass_session": "rss_tts/tts/bass_session.py",
        "cache": "rss_tts/tts/cache.py",
        "pcm_provider": "rss_tts/tts/pcm_provider.py",
        "assets": "rss_tts/tts/edge/assets.py",
        "catalog": "rss_tts/tts/edge/catalog.py",
        "provider": "rss_tts/tts/edge/provider.py",
    },
    rutas=_rutas("edgeol",
                 'EDGE_TTS_DATA_DIR = AQUI / "voces_edge"\n'
                 'TTS_CACHE_DIR = AQUI / "cache"'),
    datos={"voces_edge": "data/edge_tts"},
    pip=("edge-tts",),
)


RECETAS["espeak"] = Receta(
    identificador="espeak",
    prefijo="esp",
    modulo="motor_espeak",
    # No trae ningún módulo de la otra aplicación: el motor está escrito aquí,
    # mirando cómo lo hace NVDA.  Es el único paquete que no depende de ella.
    modulos={},
    rutas=_rutas("esp", 'ESPEAK_DATA_DIR = AQUI / "espeak-ng-data"'),
    # Los datos van enteros: veintitrés megas con los más de cien idiomas que
    # eSpeak habla. Recortarlos al español ahorraría veinte, y a cambio un libro
    # con una cita en inglés dejaría de leerse: cambiar de idioma al vuelo es
    # justo lo que este motor hace mejor que ningún otro.
    datos={"espeak-ng-data": "synthDrivers/espeak-ng-data"},
    archivos={"espeak.dll": "synthDrivers/espeak.dll",
              "sonic.dll": "synthDrivers/sonic.dll"},
    completar=completar_espeak,
)


RECETAS["espeak_mbrola"] = Receta(
    identificador="espeak_mbrola",
    prefijo="mbes",
    modulo="motor_espeak_mbrola",
    # Como el de eSpeak: el motor está escrito aquí y no toma nada de la otra
    # aplicación.
    modulos={},
    rutas=_rutas("mbes", 'ESPEAK_DATA_DIR = AQUI / "espeak-ng-data"'),
    # Los datos van enteros, con las voces MBROLA dentro.  Recortarlos al
    # español ahorraría veinte megas, y a cambio bajar una voz de otro idioma
    # —que es lo que este motor deja hacer— no serviría de nada, porque
    # faltarían las reglas de pronunciación de ese idioma.
    datos={"espeak-ng-data": "espeak-ng-data"},
    archivos={"espeak.dll": "espeak.dll", "mbrola.dll": "mbrola.dll"},
    completar=completar_mbrola,
)


def carpeta_de_piper() -> Path | None:
    """Dónde está lo de Piper, ya preparado, o ``None``."""
    donde = RAIZ / "adjuntos" / "piper"
    return donde if (donde / "piper.exe").is_file() else None


def completar_piper(datos: dict, trabajo: Path) -> None:
    """Cuenta qué voces han entrado en el paquete."""
    donde = trabajo / "voces"
    modelos = sorted(uno.name[:-len(".onnx")]
                     for uno in donde.glob("*.onnx")) if donde.is_dir() else []
    print("   voces incluidas: %s" % (", ".join(modelos) or "ninguna"))


RECETAS["piper"] = Receta(
    identificador="piper",
    prefijo="pip",
    modulo="motor_piper",
    # No trae ningún módulo de la otra aplicación: Piper es un programa aparte y
    # el adaptador solo le habla por una tubería.
    modulos={},
    rutas=_rutas("pip", 'PIPER = AQUI / "piper.exe"'),
    # El programa entero: el ejecutable, sus bibliotecas y los datos de eSpeak
    # que usa para saber cómo se pronuncia cada idioma.  Y las voces, con la
    # ficha de cada una.
    datos={"espeak-ng-data": "espeak-ng-data", "voces": "voces"},
    archivos={"piper.exe": "piper.exe",
              "onnxruntime.dll": "onnxruntime.dll",
              "onnxruntime_providers_shared.dll": "onnxruntime_providers_shared.dll",
              "piper_phonemize.dll": "piper_phonemize.dll",
              "espeak-ng.dll": "espeak-ng.dll"},
    completar=completar_piper,
)


def carpeta_de_vocalizer() -> Path | None:
    """Dónde está el motor de Vocalizer, o ``None``.

    Se busca la parte de 64 bits, que es la única que sirve: el programa lo es.
    """
    donde = RAIZ / "adjuntos" / "vocalizer"
    return donde if (donde / "lib" / "ve.dll").is_file() else None


def completar_vocalizer(datos: dict, trabajo: Path) -> None:
    """Deja lista la carpeta donde se dejarán las voces, y avisa de que va vacía."""
    (trabajo / "voces").mkdir(exist_ok=True)
    dentro = sorted(uno.name for uno in (trabajo / "voces").iterdir()
                    if uno.is_dir())
    # Un archivo dentro para que la carpeta viaje en el ZIP —que no guarda
    # carpetas vacías— y de paso para que quien la abra sepa qué hacer con ella.
    (trabajo / "voces" / "LEEME.txt").write_text(
        "\r\n".join([
            "VOCES DE VOCALIZER",
            "==================",
            "",
            "Aquí va cada voz en su propia carpeta. Las que ya están sirven de",
            "plantilla: copia una voz nueva con esta misma forma y aparecerá",
            "sola la próxima vez que abras Voz, Lectura en voz alta.",
            "",
            "Cada voz son dos archivos:",
            "",
            "   spe_jorge_premium-high\\",
            "      spe\\speech\\components\\spe_jorge_premium-high_1-0-1.dat",
            "      spe\\speech\\ve\\ve_pipeline_spe_jorge_22_premium-high_1-0-1.hdr",
            "",
            "El «.dat» es la voz y ocupa casi todo; el «.hdr» es su cabecera.",
            "",
            "Qué significa cada trozo del nombre:",
            "",
            "   spe            el idioma. SPE es español de España, SPM el de",
            "                  México, ENU el inglés de Estados Unidos...",
            "   jorge          el nombre de la voz",
            "   premium-high   la calidad",
            "   22             la frecuencia, en kilohercios",
            "   1-0-1          la versión",
            "",
            "La carpeta de arriba se llama igual que el archivo de la voz sin la",
            "versión. Es solo para que se entienda al mirarla: a Vocalizer el",
            "nombre de la carpeta le da igual, mira dentro y reconoce lo que hay.",
            "Lo que NO puedes cambiar son las carpetas «spe\\speech\\components» y",
            "«spe\\speech\\ve», ni los nombres de los dos archivos: eso sí lo mira.",
            "",
            "Copia la voz tal como venga y no le cambies nada de dentro.",
            "",
            "Si prefieres tener las voces en otro sitio del disco y no duplicar",
            "gigas, no las copies aquí: pon esa carpeta en el ajuste «otra",
            "carpeta donde buscar voces», en los ajustes de este motor.",
            "",
            "Al actualizar el motor, lo que haya aquí se conserva.",
            "",
        ]), encoding="utf-8")
    if dentro:
        megas = sum(uno.stat().st_size for uno in (trabajo / "voces").rglob("*")
                    if uno.is_file()) / 1048576
        print("   voces incluidas: %s (%.0f MB)" % (", ".join(dentro), megas))
    else:
        print("   el paquete va sin voces: se copian luego en su carpeta «voces»")


RECETAS["vocalizer"] = Receta(
    identificador="vocalizer",
    prefijo="voc",
    modulo="motor_vocalizer",
    # El envoltorio está escrito aquí, contra la biblioteca de Nuance.  El del
    # complemento de NVDA no se usa: mezcla tipos —unas funciones quieren texto
    # y otras bytes— y su función de cierre está rota.
    modulos={},
    rutas=_rutas("voc", 'VOCES = AQUI / "voces"'),
    # Los datos comunes del motor.  Las voces **no** van dentro: cada una son
    # entre cien y quinientos megas, y meterlas haría un paquete de gigas que
    # además habría que rehacer cada vez que alguien añade una.
    datos={"common": "common", "voces": "voces"},
    archivos={"lib/ve.dll": "lib/ve.dll",
              "lib/vplatform.dll": "lib/vplatform.dll",
              "lib/msvcr110.dll": "lib/msvcr110.dll"},
    completar=completar_vocalizer,
)


#: Lo que se deja dentro de las dos carpetas que llegan vacías.  Sin esto, quien
#: abra la carpeta «licencia» se encuentra con nada y tiene que adivinar.
TEXTO_VOCES_NEURAL = "\r\n".join([
    "VOCES NEURONALES",
    "================",
    "",
    "Las voces que venían con el motor ya están aquí. Para añadir más,",
    "copia cada una tal como venga, con su carpeta «data» dentro y su",
    "licencia al lado, y aparecerá sola la próxima vez que abras",
    "Voz, Lectura en voz alta.",
    "",
    "Da igual cómo las organices: se busca aquí dentro, hasta el fondo,",
    "cualquier carpeta que tenga un «data». Valen las dos formas:",
    "",
    "   voces\\es-ES-ElviraNeural\\data\\...",
    "   voces\\Spanish-Spain\\es-ES-ElviraNeural\\data\\...",
    "",
    "Cada voz ocupa unos veinticinco megas y trae dentro su idioma, así",
    "que al copiar una de otra lengua el programa ya sabe para qué sirve:",
    "la usará sola al llegar a una cita en ese idioma.",
    "",
    "Si prefieres tenerlas en otro sitio del disco y no duplicar espacio,",
    "no las copies aquí: pon esa carpeta en el ajuste «otra carpeta donde",
    "buscar voces», en los ajustes de este motor.",
    "",
    "Al actualizar el motor, lo que haya aquí se conserva.",
    "",
])

TEXTO_LICENCIA_NEURAL = "\r\n".join([
    "LA CLAVE DE LAS VOCES",
    "=====================",
    "",
    "Los modelos de voz vienen cifrados y hace falta una clave para",
    "abrirlos. Sin ella las voces se ven en la lista pero NO SUENAN.",
    "",
    "Las voces que trae el motor ya vienen con la suya al lado, así que",
    "aquí no hace falta nada. Esta carpeta es para cuando añadas voces",
    "que no la traigan, o si tienes una sola que vale para todas.",
    "",
    "Deja aquí el archivo que te dieron con la licencia, con su nombre:",
    "",
    "   SynthModel.key       si tus voces están cifradas (lo normal)",
    "   SynthModel.license   si no lo están",
    "",
    "No hay que hacer nada más: se lee solo al arrancar el motor.",
    "",
    "Si la tienes apuntada en otro sitio y prefieres pegarla, hay un",
    "campo para ello en los ajustes de este motor. Lo que escribas ahí",
    "manda sobre este archivo.",
    "",
    "Cuando falta, el motor lo dice al arrancar y lo apunta en el",
    "registro con la ruta exacta donde hay que dejarla.",
    "",
    "Al actualizar el motor, lo que haya aquí se conserva.",
    "",
])


def carpeta_de_neural() -> Path | None:
    """Dónde está el motor de las voces neuronales, o ``None``."""
    donde = RAIZ / "adjuntos" / "neural"
    nucleo = donde / "speechapi" / "Microsoft.CognitiveServices.Speech.core.dll"
    return donde if nucleo.is_file() else None


def completar_neural(datos: dict, trabajo: Path) -> None:
    """Explica las dos carpetas y dice cuántas voces van dentro."""
    for cual, texto in (("voces", TEXTO_VOCES_NEURAL),
                        ("licencia", TEXTO_LICENCIA_NEURAL)):
        (trabajo / cual).mkdir(exist_ok=True)
        (trabajo / cual / "LEEME.txt").write_text(texto, encoding="utf-8")
    cuantas = len(list((trabajo / "voces").rglob("Tokens.xml")))
    mudas = [ficha.parent.parent.parent
             for ficha in (trabajo / "voces").rglob("Tokens.xml")]
    mudas = [uno.name for uno in mudas
             if not any((uno / nombre).is_file()
                        for nombre in ("SynthModel.key", "SynthModel.license"))]
    print("   %d voces dentro del paquete" % cuantas)
    if mudas:
        # Una voz sin su clave viaja igual y no suena.  Mejor decirlo al armar
        # que dejar que lo descubra quien lo instale.
        print("   AVISO: sin clave y por tanto mudas: %s" % ", ".join(mudas))


RECETAS["neural"] = Receta(
    identificador="neural",
    prefijo="neu",
    modulo="motor_neural",
    # El envoltorio de la biblioteca viene con ella, dentro de «speechapi», así
    # que no hay módulos sueltos que traer de ninguna parte.
    modulos={},
    rutas=_rutas("neu", 'VOCES = AQUI / "voces"'),
    # Las ocho bibliotecas, el envoltorio de Python que las llama y las voces
    # con la licencia de cada una.  Son casi doscientos megas, y van dentro
    # porque un motor de voz sin voces no sirve de nada: quien lo instale lo
    # tiene todo y no tiene que copiar nada a mano.
    datos={"speechapi": "speechapi", "voces": "voces"},
    completar=completar_neural,
)


RECETAS["onecore"] = Receta(
    identificador="onecore",
    prefijo="onec",
    modulo="motor_onecore",
    # No trae nada: las voces ya están en Windows y lo único que hace este
    # paquete es saber en qué tres sitios buscarlas.  Pesa unos kilobytes.
    modulos={},
    rutas=_rutas("onec", "# este motor no necesita archivos propios"),
)


#: De dónde sale RHVoice. Se fijan las versiones a propósito: un paquete que se
#: arma distinto cada día no se puede reproducir ni comparar con el anterior.
RHVOICE_MOTOR = ("https://github.com/RHVoice/RHVoice/releases/download/"
                 "1.18.2/RHVoice-1.18.201.nvda-addon")
RHVOICE_ESPANOL = ("https://github.com/RHVoice/spanish-bin/releases/download/"
                   "1.44/RHVoice-language-Spanish-v1.44.zip")
RHVOICE_MATEO = ("https://github.com/RHVoice/mateo-spa/releases/download/"
                 "4.14/RHVoice-voice-Spanish-Mateo-v4.14.zip")


def reunido_rhvoice(fuente: Path) -> None:
    """Se queda con la DLL de 64 bits y tira el resto del complemento.

    RHVoice se publica como complemento de NVDA, que trae las dos
    arquitecturas, sus propios guiones y su documentación.  De todo eso aquí
    vale una biblioteca y un archivo de licencia; lo demás son megas de un
    programa que no es este.

    La de 32 bits no sirve ni guardándola: el visor es de 64 y no la podría
    cargar.
    """
    addon = fuente / "_addon"
    salida = fuente / ARCHIVOS
    salida.mkdir(parents=True, exist_ok=True)
    dll = addon / "synthDrivers" / "RHVoice" / "lib" / "x64" / "RHVoice.dll"
    if dll.is_file():
        shutil.copy2(dll, salida / "RHVoice.dll")
    licencia = addon / "synthDrivers" / "RHVoice" / "gpl-3.0.txt"
    if licencia.is_file():
        shutil.copy2(licencia, salida / "LICENCIA-RHVoice.txt")
    shutil.rmtree(addon, ignore_errors=True)


def completar_rhvoice(datos: dict, trabajo: Path) -> None:
    """Cuenta qué idiomas y qué voces han entrado en el paquete."""
    idiomas = [uno.name for uno in (trabajo / "datos" / "languages").iterdir()
               if uno.is_dir()] if (trabajo / "datos" / "languages").is_dir() else []
    voces = [uno.name for uno in (trabajo / "datos" / "voices").iterdir()
             if uno.is_dir()] if (trabajo / "datos" / "voices").is_dir() else []
    print("   idiomas: %s | voces: %s" % (idiomas or "ninguno", voces or "ninguna"))


RECETAS["rhvoice"] = Receta(
    identificador="rhvoice",
    prefijo="rhv",
    modulo="motor_rhvoice",
    modulos={},
    rutas=_rutas("rhv", 'DATOS = AQUI / "datos"'),
    datos={"datos": "datos"},
    archivos={"RHVoice.dll": "RHVoice.dll",
              "LICENCIA-RHVoice.txt": "LICENCIA-RHVoice.txt"},
    # Al reunir se baja de sus repositorios: es libre y se publica ahí, en vez
    # de estar ya en el equipo como los demás.
    descargas=(
        (RHVOICE_MOTOR, "_addon"),
        (RHVOICE_ESPANOL, "datos/datos/languages/Spanish"),
        (RHVOICE_MATEO, "datos/datos/voices/Mateo"),
    ),
    reunido=reunido_rhvoice,
    completar=completar_rhvoice,
)


def esta_reunido(receta: Receta) -> bool:
    """Si las fuentes de ese motor están completas en este equipo."""
    fuente = FUENTES / receta.identificador
    if not (fuente / "motor.py").is_file():
        return False
    for logico in receta.modulos:
        if not (fuente / CODIGO / (logico + ".py")).is_file():
            return False
    for destino in receta.datos:
        if not (fuente / DATOS / destino).is_dir():
            return False
    for destino in receta.archivos:
        if not (fuente / ARCHIVOS / destino).is_file():
            return False
    if receta.pip and not (fuente / BIBLIOTECA).is_dir():
        return False
    return True


def origen_de(receta: Receta, aplicacion: Path, nvda=None):
    """De dónde salen las piezas de un motor al reunirlas.

    Casi todos vienen de la otra aplicación. eSpeak sale de una instalación de
    NVDA, porque su biblioteca está compilada allí con lo que hace falta; el de
    MBROLA, de la carpeta que prepara su herramienta; y los que no traen nada de
    fuera —Core, RHVoice— no necesitan origen ninguno.

    Devuelve ``(carpeta, motivo)``: si la carpeta es ``None``, el motivo dice
    qué hacer.
    """
    if receta.identificador == "espeak":
        donde = carpeta_de_nvda(nvda)
        if donde is None:
            return None, ("no está NVDA, y de ahí sale eSpeak. Se le puede "
                          "decir dónde con --nvda <carpeta>")
        return donde, ""
    if receta.identificador == "espeak_mbrola":
        donde = carpeta_de_mbrola()
        if donde is None:
            return None, ("falta lo de MBROLA. Se prepara con: "
                          "python herramientas/espeak_mbrola.py")
        return donde, ""
    if receta.identificador == "piper":
        donde = carpeta_de_piper()
        if donde is None:
            return None, ("falta lo de Piper. Se prepara con: "
                          "python herramientas/piper.py")
        return donde, ""
    if receta.identificador == "neural":
        donde = carpeta_de_neural()
        if donde is None:
            return None, ("falta el motor de las voces neuronales. Se prepara "
                          "con: python herramientas/neural.py")
        return donde, ""
    if receta.identificador == "vocalizer":
        donde = carpeta_de_vocalizer()
        if donde is None:
            return None, ("falta el motor de Vocalizer. Se prepara con: "
                          "python herramientas/vocalizer.py")
        return donde, ""
    if receta.descargas or not (receta.modulos or receta.datos or receta.archivos
                                or receta.vendor or receta.pip):
        # No hay nada que ir a buscar: o se lo baja todo, o no trae nada.
        return RAIZ, ""
    if not aplicacion.is_dir():
        return None, ("no está la aplicación de origen: %s. Se le puede decir "
                      "dónde con --origen <carpeta>" % aplicacion)
    return aplicacion, ""


def _avisar_del_python() -> bool:
    """Comprueba que se está armando con el Python del programa.

    Cada paquete apunta para qué versión está compilado y el programa rechaza el
    que no coincida.  Armar con otro Python no falla aquí —salen los diez, con
    su tamaño y su resumen— y deja diez paquetes que no cargan, cosa que solo se
    descubre instalándolos uno por uno.

    :return: ``True`` si se puede seguir.
    """
    entorno = RAIZ / "entorno" / "Scripts" / "python.exe"
    if not entorno.is_file():
        return True          # sin entorno no hay con qué comparar
    if Path(sys.executable).resolve() == entorno.resolve():
        return True
    suya = "%d.%d" % sys.version_info[:2]
    try:
        import subprocess
        dice = subprocess.run(
            [str(entorno), "-c",
             "import sys;print('%d.%d' % sys.version_info[:2])"],
            capture_output=True, text=True, timeout=30)
        del_programa = dice.stdout.strip()
    except Exception:
        return True
    if not del_programa or del_programa == suya:
        return True
    print("Este Python es el %s y el del programa es el %s." % (suya, del_programa))
    print("Los paquetes saldrían compilados para el %s y el programa los" % suya)
    print("rechazaría al instalarlos, sin que aquí falle nada.")
    print()
    print("Ármalos con el Python del entorno:")
    print(r"   entorno\Scripts\python.exe plugins_voz/crear_paquetes.py")
    return False


def main(argumentos: list) -> int:
    if not _avisar_del_python():
        return 1
    if "--listar" in argumentos:
        print("Motores que se pueden armar:")
        for nombre, receta in RECETAS.items():
            if not (FUENTES / nombre / "motor.py").is_file():
                estado = "SIN CÓDIGO"
            elif esta_reunido(receta):
                estado = "listo"
            else:
                estado = "SIN REUNIR"
            print("   %-14s %-11s prefijo «%s», módulo «%s»"
                  % (nombre, estado, receta.prefijo, receta.modulo))
        return 0
    origen = ORIGEN_POR_OMISION
    if "--origen" in argumentos:
        origen = Path(argumentos[argumentos.index("--origen") + 1])
    nvda = None
    if "--nvda" in argumentos:
        nvda = argumentos[argumentos.index("--nvda") + 1]
    compilar = "--sin-compilar" not in argumentos
    cuales = [uno for uno in argumentos
              if not uno.startswith("--") and uno in RECETAS] or list(RECETAS)

    if "--reunir" in argumentos:
        return _reunir_varios(cuales, origen, nvda)

    if str(RAIZ / "src") not in sys.path:
        sys.path.insert(0, str(RAIZ / "src"))
    from nucleo import paquetes_voz

    fallos = 0
    for nombre in cuales:
        print("=== %s" % nombre)
        try:
            salida = armar(RECETAS[nombre], compilar)
        except SystemExit as error:
            print("   no se ha podido: %s" % error)
            fallos += 1
            continue
        megas = salida.stat().st_size / 1048576.0
        print("   %s (%.1f MB)" % (salida.name, megas))
        # Se comprueba lo que acaba de salir con el mismo código que lo instala:
        # descubrir aquí que un paquete no se deja examinar cuesta un segundo, y
        # descubrirlo al instalarlo cuesta la tarde.
        try:
            ficha = paquetes_voz.examinar(salida)
        except paquetes_voz.ErrorPaquete as error:
            print("   NO VALE: %s" % error)
            fallos += 1
            continue
        print("   comprobado: %s" % ficha.resumen().splitlines()[0])
    return 1 if fallos else 0


def _reunir_varios(cuales: list, origen: Path, nvda) -> int:
    """Reúne las fuentes de los motores que se pidan."""
    fallos = 0
    for nombre in cuales:
        receta = RECETAS[nombre]
        print("=== %s" % nombre)
        donde, motivo = origen_de(receta, origen, nvda)
        if donde is None:
            print("   no se ha podido: %s" % motivo)
            fallos += 1
            continue
        try:
            reunir(receta, donde)
        except SystemExit as error:
            print("   no se ha podido: %s" % error)
            fallos += 1
    if not fallos:
        print("\nListo. Los paquetes se arman ya sin nada más:")
        print("   python plugins_voz/crear_paquetes.py")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
