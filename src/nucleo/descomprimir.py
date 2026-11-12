# -*- coding: utf-8 -*-
"""Abrir comprimidos que Python no sabe abrir: RAR y 7z.

Python trae ZIP y TAR y nada más.  El RAR es un formato cerrado y el 7z necesita
su propia biblioteca, así que un cómic en ``.cbr`` de verdad —comprimido con
RAR, no con ZIP y la extensión cambiada— no se podía abrir.

La solución no es traerse una biblioteca de decenas de megas: es **usar lo que
Windows ya trae**.  Desde Windows 10 (1803) el sistema incluye ``tar.exe``, que
no es el tar de toda la vida sino **bsdtar**, construido sobre *libarchive*, y
libarchive sabe leer RAR, RAR5 y 7z además de ZIP y TAR.  Está en
``C:\\Windows\\System32``, no hay que instalar nada y no ocupa nada.

Por si acaso, se prueban también ``unrar`` y ``7z`` si el usuario los tiene en
el PATH: quien ya los tenga instalados abrirá incluso los archivos que bsdtar no
alcanza.

Qué no se puede
---------------

bsdtar no abre los RAR **sólidos** ni los partidos en varios volúmenes, y lo
dice.  En esos casos se avisa con claridad de qué pasa y qué hacer, que es
mucho mejor que fallar sin explicación: quien lee sabe entonces que el archivo
no está roto y que con volver a comprimirlo en ZIP lo tendrá resuelto.

Nada de esto se ejecuta a la ligera: solo se lanza el programa externo cuando
hace falta de verdad, con un tiempo máximo, y siempre sobre una carpeta
temporal propia.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .idioma import _, _n
from .registro import obtener_registro

log = obtener_registro(__name__)

#: Cuánto se espera como mucho a que termine de descomprimir.  Un cómic son
#: unos megas y se hace en segundos; pasado esto, algo va mal.
ESPERA = 180

#: Programas que se prueban, en orden, con los argumentos con los que se les
#: pide extraer todo a una carpeta.
#:
#: **7-Zip va primero, y viaja con el programa.**  Está en ``data/bin`` y se
#: distribuye con el ejecutable, así que no hay que instalar nada y no depende
#: de lo que cada equipo tenga puesto.  Es el que abre de verdad todo lo que
#: puede llegar: RAR de las dos versiones y partido en volúmenes, 7z, ZIP, CAB,
#: CHM y una veintena más.
#:
#: Detrás quedan los otros dos como red: el ``tar`` de Windows —que está
#: siempre pero se para a la mitad de un RAR partido sin decirlo— y el
#: ``unrar`` de quien lo tenga instalado.
PROGRAMAS = (
    ("7z", ("x", "-y", "-o{carpeta}", "{archivo}")),
    ("unrar", ("x", "-y", "-inul", "{archivo}", "{carpeta}")),
    ("tar", ("-xf", "{archivo}", "-C", "{carpeta}")),
)

#: Cómo se le pide a cada programa **la lista** de lo que hay dentro, sin
#: sacarlo. Con ella se sabe si la extracción ha salido completa, que es una
#: pregunta distinta de si ha salido bien: hay comprimidos de los que el
#: descompresor del sistema saca la mitad y termina diciendo que ha terminado.
#:
#: El orden importa y es el mismo que arriba: **7-Zip primero**. El ``tar`` del
#: sistema, ante un RAR partido, lista solo lo que hay en el primer volumen y no
#: dice que se está dejando el resto; si se le preguntara a él, la comparación
#: entre lo listado y lo extraído daría «completo» faltando media historieta.
LISTADOS = {
    "7z": ("l", "-ba", "-slt", "{archivo}"),
    "unrar": ("lb", "-inul", "{archivo}"),
    "tar": ("-tf", "{archivo}"),
}

#: Nombres que delatan un comprimido partido en varios archivos.
_VOLUMENES = re.compile(r"\.part0*(\d+)\.(?:rar|cbr)$|\.r(\d\d)$|\.(\d\d\d)$",
                        re.IGNORECASE)


class Extraccion:
    """Cómo ha ido una extracción: dónde ha quedado y qué se ha quedado dentro.

    Se separa de :func:`extraer` porque hay una diferencia que importa mucho y
    que un simple <<ha ido bien o no>> no recoge: un cómic del que salen cinco
    páginas de doce **parece** bien abierto. Quien lo lea llegará a la quinta y
    entenderá que ahí se acaba, sin ninguna razón para sospechar. Por eso
    ``faltan`` viaja con el resultado y quien lo enseña está obligado a mirarlo.
    """

    __slots__ = ("carpeta", "faltan", "programa", "por_volumenes")

    def __init__(self, carpeta=None, faltan=None, programa: str = "",
                 por_volumenes: bool = False) -> None:
        self.carpeta = carpeta
        self.faltan = list(faltan or [])
        self.programa = programa
        self.por_volumenes = por_volumenes

    def __bool__(self) -> bool:
        return self.carpeta is not None

    @property
    def completa(self) -> bool:
        """Dice si ha salido todo lo que había dentro."""
        return self.carpeta is not None and not self.faltan


def es_por_volumenes(archivo) -> bool:
    """Dice si el archivo parece una parte de un comprimido partido."""
    return _VOLUMENES.search(Path(archivo).name) is not None


def volumenes_siguientes(archivo) -> list[Path]:
    """Los demás volúmenes del conjunto que están en la misma carpeta.

    **Por qué hace falta mirar el disco** y no basta con leer el comprimido: el
    descompresor del sistema, ante un RAR partido, se para al final del primer
    volumen sin decir nada útil, y **también se para al listarlo**. Un RAR de
    doce páginas partido en tres se lista con cinco entradas y se extrae con
    cinco archivos, así que comparar lo listado con lo extraído da «completo».
    Lo único que delata que falta la mitad es que al lado hay más volúmenes.

    Se reconocen los tres modos de partir que hay: ``.part1.rar``, ``.r00`` y
    ``.001``. Se busca por su número, no por el orden alfabético del nombre,
    porque el volumen diez va detrás del nueve y no entre el uno y el dos.
    """
    origen = Path(archivo)
    encaje = _VOLUMENES.search(origen.name)
    if encaje is None:
        return []
    inicio, fin = encaje.span()
    antes, marca, despues = (origen.name[:inicio], origen.name[inicio:fin],
                             origen.name[fin:])
    cifras = "".join(c for c in marca if c.isdigit())
    if not cifras:
        return []
    numero = int(cifras)

    encontrados: list[Path] = []
    for siguiente in range(numero + 1, numero + _MAXIMOS_VOLUMENES):
        # Se prueban dos anchuras: la del original --«part01» sigue en
        # «part02»-- y la natural, porque «part9» sigue en «part10».
        anchuras = {len(cifras), len(str(siguiente))}
        for ancho in sorted(anchuras):
            nombre = antes + marca.replace(cifras, "%0*d" % (ancho, siguiente), 1) \
                + despues
            candidato = origen.with_name(nombre)
            if candidato.is_file():
                encontrados.append(candidato)
                break
        else:
            break
    return encontrados


#: Hasta cuántos volúmenes se buscan detrás del primero. Con más, un nombre
#: raro podría poner a mirar el disco cien mil veces sin encontrar nada.
_MAXIMOS_VOLUMENES = 100


def _sin_ventana() -> dict:
    """Ajustes para que el programa externo no abra una consola.

    Sin esto, cada extracción haría parpadear una ventana negra en pantalla y,
    lo que es peor, robaría el foco al lector de pantalla a media lectura.
    """
    if sys.platform != "win32":
        return {}
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return {"startupinfo": info,
            "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def ruta_del_7zip() -> str:
    """El 7-Zip que viaja con el programa, si está.

    Va en ``data/bin`` y se distribuye con el ejecutable.  Se busca ahí **antes**
    que en el sistema por dos razones: es el que sabemos que funciona —el del
    sistema puede ser una versión vieja sin RAR5— y es el que hace que abrir un
    cómic no dependa de lo que cada uno tenga instalado.
    """
    from . import rutas

    if sys.platform != "win32":
        return ""
    propio = rutas.directorio_datos() / "bin" / "7z.exe"
    return str(propio) if propio.is_file() else ""


def _ruta_de(programa: str) -> str:
    """Dónde está el programa, o cadena vacía si no está.

    Para ``7z`` manda el que viaja con el programa; si no estuviera —alguien que
    haya borrado ``data/bin``— se usa el del sistema.

    Para ``tar`` se mira primero el de ``System32`` con su ruta completa: si el
    usuario tiene otro ``tar`` en el PATH —el de Git, por ejemplo— puede no ser
    bsdtar y no saber de RAR.
    """
    if programa == "7z":
        propio = ruta_del_7zip()
        if propio:
            return propio
    if programa == "tar" and sys.platform == "win32":
        propio = Path(r"C:\Windows\System32\tar.exe")
        if propio.exists():
            return str(propio)
    return shutil.which(programa) or ""


def hay_extractor() -> bool:
    """Indica si en este equipo hay con qué abrir un RAR o un 7z."""
    return any(_ruta_de(programa) for programa, _argumentos in PROGRAMAS)


def nombre_del_extractor() -> str:
    """El primero de los programas que hay, para poder decirlo."""
    for programa, _argumentos in PROGRAMAS:
        if _ruta_de(programa):
            return programa
    return ""


def contenido(archivo) -> list[str]:
    """Los nombres de lo que hay dentro del comprimido, sin sacarlo.

    Devuelve la lista vacía cuando no se ha podido leer. Es rápido incluso en
    los comprimidos de los que después no se puede sacar todo: el índice de un
    RAR partido está entero en su primer volumen aunque los datos no lo estén,
    y eso es justo lo que permite darse cuenta de que falta algo.
    """
    origen = Path(archivo)
    for programa, plantilla in LISTADOS.items():
        ruta = _ruta_de(programa)
        if not ruta:
            continue
        orden = [ruta] + [parte.format(archivo=str(origen)) for parte in plantilla]
        try:
            resultado = subprocess.run(orden, capture_output=True, timeout=ESPERA,
                                       **_sin_ventana())
        except (OSError, subprocess.SubprocessError):
            continue
        salida = resultado.stdout.decode("utf-8", "replace")
        nombres = []
        for linea in salida.splitlines():
            linea = linea.strip()
            if programa == "7z":
                if not linea.startswith("Path = "):
                    continue
                linea = linea[len("Path = "):].strip()
                if linea == str(origen):
                    continue
            if not linea or linea.endswith("/") or linea.endswith("\\"):
                continue
            nombres.append(linea.replace("\\", "/"))
        if nombres:
            return nombres
    return []


def extraer_detallado(archivo, carpeta=None) -> Extraccion:
    """Descomprime y dice **además** si ha salido todo.

    Se prueban los programas por orden y **no se para en el primero que saque
    algo**: se para en el primero que lo saque *todo*. Es la diferencia entre
    abrir un cómic de doce páginas y abrir uno que enseña cinco y parece que se
    acaba ahí. Si ninguno lo saca entero, se devuelve el que más haya sacado,
    con la lista de lo que falta para que quien lo enseñe pueda decirlo.
    """
    origen = Path(archivo)
    dentro = contenido(origen)
    esperados = {n.rsplit("/", 1)[-1] for n in dentro}

    mejor = Extraccion(por_volumenes=es_por_volumenes(origen))
    mejor_cuantos = -1
    propias: list[Path] = []

    # Primero se prueba por nuestra cuenta. No siempre se puede —solo con lo que
    # va guardado sin comprimir—, y cuando se puede resuelve justo el caso peor:
    # un cómic partido en volúmenes en un equipo donde no hay ni WinRAR ni
    # 7-Zip, que es donde hoy se pierde media historieta sin avisar.
    propia = _extraer_rar_propio(origen, carpeta, esperados)
    if propia is not None:
        if propia.completa:
            return propia
        if carpeta is None:
            propias.append(propia.carpeta)
        mejor, mejor_cuantos = propia, len(list(propia.carpeta.rglob("*")))

    for programa, argumentos in PROGRAMAS:
        ruta = _ruta_de(programa)
        if not ruta:
            continue
        if carpeta is not None:
            destino = Path(carpeta)
        else:
            destino = Path(tempfile.mkdtemp(prefix="visor-comprimido-"))
            propias.append(destino)
        destino.mkdir(parents=True, exist_ok=True)
        orden = [ruta] + [parte.format(archivo=str(origen), carpeta=str(destino))
                          for parte in argumentos]
        try:
            resultado = subprocess.run(orden, capture_output=True, timeout=ESPERA,
                                       **_sin_ventana())
        except (OSError, subprocess.SubprocessError) as error:
            log.debug("%s no ha podido con %s: %s", programa, origen.name, error)
            continue
        # Se mira lo que ha salido y no el código de retorno: bsdtar devuelve
        # error cuando se deja **un** archivo del comprimido, y con un cómic al
        # que le falte una página es mejor enseñar las demás que no enseñar
        # ninguna --diciéndolo--.
        sacados = [hijo for hijo in destino.rglob("*") if hijo.is_file()]
        if not sacados:
            log.debug("%s no ha sacado nada de %s: %s", programa, origen.name,
                      resultado.stderr.decode("utf-8", "replace").strip()[:200])
            continue
        salieron = {hijo.name for hijo in sacados}
        faltan = sorted(esperados - salieron) if esperados else []
        if not faltan and programa == "tar":
            # El descompresor del sistema no junta volúmenes, y ni al listar ni
            # al extraer da a entender que se está dejando la mitad. Si al lado
            # hay más volúmenes, aquí falta contenido con seguridad.
            faltan = [h.name for h in volumenes_siguientes(origen)]
        if len(sacados) > mejor_cuantos:
            mejor_cuantos = len(sacados)
            mejor = Extraccion(destino, faltan, programa, es_por_volumenes(origen))
        if not faltan:
            log.info("%s ha sacado %d archivos de %s", programa, len(sacados),
                     origen.name)
            break
        log.info("%s solo ha sacado %d de %d archivos de %s", programa,
                 len(sacados), len(esperados), origen.name)
        if carpeta is not None:
            # Con carpeta fija no hay dónde probar otro programa sin mezclar lo
            # de los dos, así que se deja lo que haya.
            break

    for sobrante in propias:
        if mejor.carpeta != sobrante:
            _borrar(sobrante)
    if mejor.carpeta is None and carpeta is None:
        pass
    return mejor


def _extraer_rar_propio(origen: Path, carpeta, esperados) -> Extraccion | None:
    """Intenta sacar el RAR con el lector propio. ``None`` si no es un RAR.

    Devuelve una extracción incluso cuando falta algo: lo que se haya podido
    sacar sirve, y lo que falte va escrito en ``faltan`` para que quien lo
    enseñe esté obligado a decirlo.
    """
    from . import rar as lector_rar

    if not lector_rar.es_rar(origen):
        return None
    volumenes = [origen] + volumenes_siguientes(origen)
    destino = (Path(carpeta) if carpeta is not None
               else Path(tempfile.mkdtemp(prefix="visor-rar-")))
    try:
        salidos, comprimidos = lector_rar.extraer(volumenes, destino)
    except lector_rar.ErrorRAR as error:
        log.debug("El lector propio no ha podido con %s: %s", origen.name, error)
        if carpeta is None:
            _borrar(destino)
        return None
    except OSError as error:                             # pragma: no cover
        log.info("No se ha podido escribir al abrir %s: %s", origen.name, error)
        if carpeta is None:
            _borrar(destino)
        return None
    if not salidos:
        # Todo iba comprimido de verdad: aquí no hay nada que hacer, y lo
        # correcto es dejar que lo intenten WinRAR o 7-Zip.
        log.debug("%s va comprimido entero; se prueba con los programas",
                  origen.name)
        if carpeta is None:
            _borrar(destino)
        return None
    salieron = {nombre.rsplit("/", 1)[-1] for nombre in salidos}
    faltan = sorted(esperados - salieron) if esperados else sorted(
        nombre.rsplit("/", 1)[-1] for nombre in comprimidos)
    log.info("Lector propio: %d archivos de %s%s", len(salidos), origen.name,
             ", faltan %d" % len(faltan) if faltan else "")
    return Extraccion(destino, faltan, "propio", es_por_volumenes(origen))


def extraer(archivo, carpeta=None) -> Path | None:
    """Descomprime el archivo y devuelve la carpeta, o ``None``.

    Es la forma corta de :func:`extraer_detallado` para quien solo necesita el
    contenido. Quien vaya a **enseñárselo a alguien** debe usar la larga y
    mirar ``faltan``.
    """
    return extraer_detallado(archivo, carpeta).carpeta


def _borrar(carpeta: Path) -> None:
    """Borra una carpeta temporal sin dar guerra si no se puede."""
    try:
        shutil.rmtree(carpeta, ignore_errors=True)
    except OSError:                                  # pragma: no cover
        pass


def motivo_de_fallo(nombre: str) -> str:
    """Explica por qué no se ha podido abrir, y qué hacer.

    Se distingue el equipo que no tiene con qué del archivo que no se deja: son
    dos problemas distintos y tienen soluciones distintas, y decir «no se ha
    podido» a secas no ayuda a ninguno de los dos.
    """
    if not hay_extractor():
        return _("Este archivo está comprimido en RAR o en 7z y no se ha encontrado "
                 "con qué abrirlo. El programa trae su propio 7-Zip en la carpeta "
                 "«data/bin»: si esa carpeta se ha borrado, vuelve a copiarla desde "
                 "la descarga del programa.")
    return _("No se ha podido abrir «%s»: el archivo parece dañado. Si tienes otra "
             "copia, pruébala; si no, vuelve a comprimirlo en ZIP y cámbiale la "
             "extensión a «.cbz».") % nombre


def motivo_de_lo_que_falta(extraccion: Extraccion, nombre: str) -> str:
    """Explica por qué la extracción se ha quedado a medias, y qué hacer.

    Se distingue el comprimido partido en volúmenes del que simplemente venía
    estropeado, porque el primero tiene arreglo y el segundo no.
    """
    cuantos = len(extraccion.faltan)
    if extraccion.por_volumenes:
        # Con el 7-Zip propio esto ya casi no pasa. Cuando pasa es porque falta
        # de verdad un volumen en la carpeta, y entonces lo que hay que decir es
        # eso y no «instala un programa».
        return _n("Este archivo está partido en varios volúmenes y falta %d "
                  "archivo. Comprueba que están todos los volúmenes en la misma "
                  "carpeta: hace falta el primero y todos los siguientes, sin "
                  "saltarse ninguno.",
                  "Este archivo está partido en varios volúmenes y faltan %d "
                  "archivos. Comprueba que están todos los volúmenes en la misma "
                  "carpeta: hace falta el primero y todos los siguientes, sin "
                  "saltarse ninguno.", cuantos) % cuantos
    return _n("Del archivo «%(nombre)s» no ha salido %(cuantos)d de sus páginas: "
              "puede estar dañado.",
              "Del archivo «%(nombre)s» no han salido %(cuantos)d de sus páginas: "
              "puede estar dañado.", cuantos) % {"nombre": nombre, "cuantos": cuantos}
