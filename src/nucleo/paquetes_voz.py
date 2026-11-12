# -*- coding: utf-8 -*-
"""Instalar y quitar paquetes de motor de voz.

Un paquete es **un solo archivo** con extensión ``.motorvoz``. Por dentro es un
ZIP, y esa es toda la magia: se puede abrir con cualquier cosa para mirar qué
lleva, que es justo lo que hay que poder hacer antes de meter en un programa
código que va a ejecutarse.

Qué lleva dentro
----------------

::

    motor.json      quién es, qué ajustes tiene y qué explica cada uno
    motor.pyc       la función «crear», que devuelve el sintetizador
    LEEME.md        de dónde sale cada cosa y con qué licencia
    ...             lo que ese motor necesite: DLL, voces, datos

Y nada más. Lo que el programa ya pone —el reproductor de audio, el registro,
las rutas— no se duplica: un paquete que trajera su propia copia de todo eso
pesaría diez veces más y se quedaría desfasado a la primera actualización.

Por qué se comprueba tanto antes de instalar
--------------------------------------------

Porque un paquete **trae código que se va a ejecutar**. No se puede impedir que
alguien instale algo que no debía —igual que no se puede impedir abrir un
programa descargado—, pero sí se puede:

* comprobar que el archivo es lo que dice ser antes de tocar nada;
* rechazar los nombres de archivo con «..» o con rutas absolutas, que es el
  truco de toda la vida para escribir fuera de donde toca;
* enseñar de antemano **qué motor es, de dónde sale y qué ocupa**, y pedir
  confirmación;
* dejarlo todo como estaba si algo sale mal a mitad.

Se instala en ``data/motores/<identificador>``, que es una carpeta del propio
programa: no toca el sistema, no escribe en el registro de Windows y quitarlo es
borrar esa carpeta. Un programa portátil que ensucia el equipo deja de ser
portátil, y llevárselo en un lápiz de memoria tiene que llevarse sus voces.
"""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

from .idioma import _
from . import motores_voz
from . import sistema_motores
from .motores_voz import (MANIFIESTO, SAPI5, VERSION_CONTRATO, Motor,
                          leer_manifiesto)
from .registro import obtener_registro

log = obtener_registro(__name__)

#: Extensión de un paquete de motor de voz.
EXTENSION = ".motorvoz"

#: Filtro para el diálogo de abrir archivo.
FILTRO = _("Paquetes de motor de voz (*.motorvoz)|*.motorvoz|"
           "Todos los archivos|*.*")

#: Tope de lo que se deja descomprimir, en bytes.  Un ZIP de cuatro kilobytes
#: puede declarar cuarenta gigas de contenido —es un truco viejo y conocido— y
#: sin este tope el disco se llenaría antes de que nadie pudiera cancelar.
MAXIMO_DESCOMPRIMIDO = 3 * 1024 * 1024 * 1024

#: Y cuántos archivos como mucho, por lo mismo.
MAXIMOS_ARCHIVOS = 20000


class ErrorPaquete(Exception):
    """El paquete no se puede instalar, y el mensaje dice por qué.

    El mensaje va escrito para leerlo en voz alta, no para un registro: quien lo
    oiga tiene que poder decidir qué hacer sin saber qué es un ZIP.
    """


class Ficha:
    """Lo que se sabe de un paquete **sin haberlo instalado**.

    Es lo que se le enseña a quien va a instalarlo para que decida. Se saca
    leyendo el manifiesto de dentro del ZIP, sin descomprimir nada al disco.
    """

    __slots__ = ("identificador", "nombre", "descripcion", "version", "autor",
                 "origen", "licencia", "archivos", "tamano", "ruta", "efectos")

    def __init__(self, **datos) -> None:
        for nombre in self.__slots__:
            setattr(self, nombre, datos.get(nombre, ""))
        if not self.efectos:
            self.efectos = sistema_motores.Efectos()

    def resumen(self) -> str:
        """Una descripción corta y completa, para leerla antes de instalar."""
        partes = [self.nombre]
        if self.version:
            partes.append(_("versión %s") % self.version)
        if self.autor:
            partes.append(_("de %s") % self.autor)
        cabecera = ", ".join(partes)
        cuerpo = [cabecera + "."]
        if self.descripcion:
            cuerpo.append(self.descripcion)
        if self.origen:
            cuerpo.append(_("De dónde sale: %s") % self.origen)
        if self.licencia:
            cuerpo.append(_("Licencia: %s") % self.licencia)
        cuerpo.append(_("Ocupa %(megas).1f MB en %(cuantos)d archivos.")
                      % {"megas": self.tamano / 1048576.0,
                         "cuantos": self.archivos})
        # Lo que toca fuera de su carpeta va **al final y aparte**: es lo último
        # que se oye antes de decidir, que es donde tiene que estar.
        aviso = sistema_motores.describir(self.efectos)
        if aviso:
            cuerpo.append(aviso)
        return "\n\n".join(cuerpo)


def _nombre_seguro(nombre: str) -> bool:
    """Si un archivo del ZIP se puede escribir sin salirse de su carpeta.

    Un nombre con «..», con unidad o que empieza por barra escribiría donde le
    pareciera. Es un problema viejo y la respuesta es igual de vieja: mirarlo
    antes, no después.
    """
    if not nombre or nombre.startswith(("/", "\\")):
        return False
    if ":" in nombre:
        return False
    partes = nombre.replace("\\", "/").split("/")
    return ".." not in partes and "" not in partes[:-1]


def examinar(ruta) -> Ficha:
    """Mira un paquete sin instalarlo y devuelve su ficha.

    Lanza :class:`ErrorPaquete` con un mensaje legible a la primera pega.
    """
    camino = Path(ruta)
    if not camino.is_file():
        raise ErrorPaquete(_("Ese archivo no existe."))
    try:
        with zipfile.ZipFile(camino) as paquete:
            danado = paquete.testzip()
            if danado:
                raise ErrorPaquete(_("El paquete está dañado: no se puede leer "
                                     "«%s».") % danado)
            nombres = paquete.namelist()
            if MANIFIESTO not in nombres:
                raise ErrorPaquete(_(
                    "Este archivo no es un paquete de motor de voz: no lleva "
                    "dentro su «motor.json»."))
            if len(nombres) > MAXIMOS_ARCHIVOS:
                raise ErrorPaquete(_("El paquete trae demasiados archivos."))
            total = 0
            for ficha in paquete.infolist():
                if not _nombre_seguro(ficha.filename):
                    raise ErrorPaquete(_(
                        "El paquete quiere escribir fuera de su carpeta "
                        "(«%s»), así que no se instala.") % ficha.filename)
                total += ficha.file_size
                if total > MAXIMO_DESCOMPRIMIDO:
                    raise ErrorPaquete(_("El paquete ocupa demasiado al "
                                         "descomprimirse."))
            datos = json.loads(paquete.read(MANIFIESTO).decode("utf-8"))
    except zipfile.BadZipFile:
        raise ErrorPaquete(_("Ese archivo no es un paquete de motor de voz."))
    except json.JSONDecodeError as error:
        raise ErrorPaquete(_("El paquete trae un «motor.json» ilegible: %s")
                           % error)
    except ErrorPaquete:
        raise
    except OSError as error:
        raise ErrorPaquete(_("No se ha podido leer el paquete: %s") % error)

    identificador = str(datos.get("id", "")).strip()
    if not identificador:
        raise ErrorPaquete(_("El paquete no dice cómo se llama su motor."))
    if identificador == SAPI5:
        raise ErrorPaquete(_("Ese paquete quiere reemplazar la voz de Windows, "
                             "que es la que queda cuando todo lo demás falla."))
    if int(datos.get("contrato", 0)) != VERSION_CONTRATO:
        raise ErrorPaquete(_(
            "Este paquete está hecho para otra versión del programa."))
    return Ficha(identificador=identificador,
                 efectos=sistema_motores.leer(datos),
                 nombre=str(datos.get("nombre", identificador)),
                 descripcion=str(datos.get("descripcion", "")),
                 version=str(datos.get("version", "")),
                 autor=str(datos.get("autor", "")),
                 origen=str(datos.get("origen", "")),
                 licencia=str(datos.get("licencia", "")),
                 archivos=len(nombres), tamano=total, ruta=camino)


def _limpiar_el_sistema(carpeta) -> None:
    """Deshace lo que el motor hubiera dejado fuera de su carpeta.

    Lo hace el programa y no el motor, y a propósito: un motor que se quita
    porque da problemas es justo el que no se puede cargar para pedirle que se
    limpie solo.  Lo declarado en su manifiesto basta para deshacerlo sin
    ejecutar una línea suya.
    """
    try:
        datos = json.loads(
            (Path(carpeta) / motores_voz.MANIFIESTO).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        log.debug("Sin manifiesto legible al quitar: %s", error)
        return
    efectos = sistema_motores.leer(datos)
    if not efectos:
        return
    quitadas = sistema_motores.limpiar(efectos, Path(carpeta))
    quedan = sistema_motores.lo_que_queda(efectos)
    log.info("Registro: %d ramas quitadas, %d siguen ahí", quitadas, len(quedan))
    for rama in quedan:
        log.warning("No se ha podido quitar del registro: %s", rama)


def _rescatar_lo_bajado(anterior, destino, motor) -> None:
    """Devuelve a su sitio lo que el motor hubiera bajado antes.

    Un motor puede declarar carpetas que no son suyas sino de quien lo usa: los
    idiomas que se hayan bajado desde él.  Piper, MBROLA y las voces de Google
    lo hacen, y ahí puede haber cientos de megas.

    Se copia solo lo que el paquete nuevo **no** trae.  Al revés sería peor:
    una versión nueva que corrige una voz se vería pisada por la vieja, y eso no
    hay manera de notarlo salvo oyéndolo.

    Si algo falla se sigue: el motor está instalado y funciona, y perder una
    descarga es molesto pero no roto.  Se apunta en el registro.
    """
    carpetas = getattr(motor, "conservar", ()) or ()
    if not anterior.is_dir() or not carpetas:
        return
    rescatados = 0
    for relativa in carpetas:
        limpia = str(relativa).replace("\\", "/").strip("/")
        if not limpia or ".." in limpia.split("/"):
            continue
        vieja = anterior / limpia
        if not vieja.is_dir():
            continue
        for uno in vieja.rglob("*"):
            if not uno.is_file():
                continue
            fin = destino / limpia / uno.relative_to(vieja)
            if fin.exists():
                continue          # lo trae el paquete nuevo, y ese manda
            try:
                fin.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(uno, fin)
                rescatados += 1
            except OSError as error:
                log.warning("No se ha podido conservar %s: %s", uno.name, error)
    if rescatados:
        log.info("Conservados %d archivos bajados del motor %s", rescatados,
                 motor.identificador)


def instalar(ruta) -> Motor:
    """Instala un paquete y devuelve el motor que ha quedado listo.

    Se descomprime **a un lado** y solo al final se pone en su sitio. Así, un
    paquete que falle a mitad no deja media instalación: o está entero o no
    está, y el que hubiera antes sigue funcionando.
    """
    ficha = examinar(ruta)
    raiz = motores_voz.carpeta_de_motores()
    destino = raiz / ficha.identificador
    provisional = raiz / ("_instalando_" + ficha.identificador)
    anterior = raiz / ("_anterior_" + ficha.identificador)
    for sobra in (provisional, anterior):
        if sobra.exists():
            shutil.rmtree(sobra, ignore_errors=True)
    try:
        provisional.mkdir(parents=True)
        with zipfile.ZipFile(ficha.ruta) as paquete:
            for interno in paquete.infolist():
                if interno.is_dir():
                    continue
                salida = provisional / interno.filename.replace("\\", "/")
                # Segunda comprobación, ya con la ruta resuelta: la primera mira
                # el nombre y esta mira dónde acaba de verdad.  Un enlace o un
                # nombre raro del sistema de archivos puede colarse entre una y
                # otra.
                if provisional.resolve() not in salida.resolve().parents:
                    raise ErrorPaquete(_("El paquete quiere escribir fuera de "
                                         "su carpeta, así que no se instala."))
                salida.parent.mkdir(parents=True, exist_ok=True)
                with paquete.open(interno) as origen, salida.open("wb") as fin:
                    shutil.copyfileobj(origen, fin)
        # Se lee el manifiesto ya descomprimido: es la comprobación de verdad,
        # porque ahora se puede mirar que el archivo del módulo esté.
        motor = leer_manifiesto(provisional)
    except ErrorPaquete:
        shutil.rmtree(provisional, ignore_errors=True)
        raise
    except Exception as error:
        shutil.rmtree(provisional, ignore_errors=True)
        raise ErrorPaquete(_("El paquete no se ha podido instalar: %s") % error)

    try:
        if destino.exists():
            destino.rename(anterior)
        provisional.rename(destino)
    except OSError as error:
        # Si el cambio de sitio falla, se devuelve lo que había.
        if anterior.exists() and not destino.exists():
            anterior.rename(destino)
        shutil.rmtree(provisional, ignore_errors=True)
        raise ErrorPaquete(_("No se ha podido dejar el motor en su sitio: %s")
                           % error)
    _rescatar_lo_bajado(anterior, destino, motor)
    shutil.rmtree(anterior, ignore_errors=True)
    # Si la de antes no se ha dejado borrar es que algo suyo está en uso, y lo
    # que se usa de un motor son sus bibliotecas.  Windows no las suelta hasta
    # que el proceso muere, así que este motor no va a funcionar hasta que se
    # reinicie: la biblioteca cargada es la de la carpeta vieja y las voces
    # están en la nueva.  Vale más decirlo ahora que dejar que se descubra al
    # pulsar «Probar».
    motor.reiniciar = anterior.exists()
    if motor.reiniciar:
        log.warning("El motor %s estaba en uso: queda %s sin borrar y hay que "
                    "reiniciar el programa para usarlo",
                    ficha.identificador, anterior.name)
    # Qué ramas del registro existían antes de este motor.  Es lo que después
    # distingue lo que hay que borrar al quitarlo de lo que ya era de alguien.
    sistema_motores.apuntar_lo_que_habia(ficha.efectos, destino)
    motor.carpeta = destino
    log.info("Motor de voz instalado: %s (%s)", motor.identificador,
             ficha.version or "sin versión")
    return motor


def quitar(identificador: str) -> bool:
    """Desinstala un motor. Devuelve si había algo que quitar.

    La voz de Windows no se puede quitar: no es una decisión de diseño sino la
    única manera de garantizar que el programa siga hablando pase lo que pase.
    """
    if identificador == SAPI5:
        raise ErrorPaquete(_("La voz de Windows no se puede quitar: es la que "
                             "queda cuando falla cualquier otra."))
    carpeta = motores_voz.carpeta_de_motores() / identificador
    if not carpeta.is_dir():
        return False
    # Primero el sistema y después la carpeta: el apunte de qué había antes
    # vive dentro de la carpeta, y borrándola primero se perdería.
    _limpiar_el_sistema(carpeta)
    shutil.rmtree(carpeta, ignore_errors=True)
    # Puede quedarse algo si el motor tenía un archivo abierto —una DLL cargada,
    # por ejemplo—.  Se marca para borrarlo al arrancar y se dice que se ha
    # quitado, porque para quien lo usa ya no está: no sale en la lista.
    if carpeta.exists():
        try:
            (carpeta / ".borrar").write_text("", encoding="utf-8")
            log.info("El motor %s se borrará del todo al reiniciar",
                     identificador)
        except OSError:
            pass
    log.info("Motor de voz quitado: %s", identificador)
    return True


def limpiar_restos() -> int:
    """Borra lo que quedó a medias. Se llama al arrancar.

    Un motor se queda a medio borrar cuando tenía una biblioteca cargada al
    quitarlo: Windows no deja borrar un archivo en uso. Al arrancar ya no lo
    está, y este es el momento de acabar.
    """
    raiz = motores_voz.carpeta_de_motores()
    if not raiz.is_dir():
        return 0
    cuantos = 0
    for carpeta in list(raiz.iterdir()):
        if not carpeta.is_dir():
            continue
        marcado = (carpeta / ".borrar").is_file()
        a_medias = carpeta.name.startswith(("_instalando_", "_anterior_"))
        if marcado or a_medias:
            shutil.rmtree(carpeta, ignore_errors=True)
            if not carpeta.exists():
                cuantos += 1
    if cuantos:
        log.info("Restos de motores de voz limpiados: %d", cuantos)
    return cuantos


def carpeta_de_paquetes() -> Path:
    """Dónde están los paquetes que vienen con el programa.

    Es ``plugins_voz`` en la raíz, al lado del ejecutable: se ve, se puede
    copiar a un lápiz de memoria y se puede borrar quien no los quiera.
    """
    from . import rutas

    return rutas.directorio_base() / "plugins_voz"


def disponibles() -> list[Path]:
    """Los paquetes que hay en ``plugins_voz``, listos para instalar."""
    carpeta = carpeta_de_paquetes()
    if not carpeta.is_dir():
        return []
    return sorted(carpeta.glob("*" + EXTENSION))
