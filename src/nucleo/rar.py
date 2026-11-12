# -*- coding: utf-8 -*-
"""Abrir un RAR por nuestra cuenta, incluso partido en volúmenes.

Un cómic partido en `album.part1.rar`, `album.part2.rar`… es el caso en el que
el descompresor que trae Windows falla **en silencio**: saca las páginas del
primer volumen, dice que ha ido bien, y quien lo lee llega a la quinta página
entendiendo que ahí se acaba el cómic. Hoy eso se detecta mirando si al lado hay
más volúmenes y, si están WinRAR o 7-Zip, se usan. Pero pedirle a alguien que
instale un programa para poder leer su propio cómic es pedirle demasiado.

**Qué hace este módulo, y qué no.**  Lee el envoltorio del RAR —las dos
versiones, la 4 y la 5— y saca los archivos que estén **guardados sin
comprimir**, juntando los trozos que crucen de un volumen al siguiente. No
descomprime: eso es un trabajo enorme y de otra naturaleza.

Y resulta que con eso basta para casi todos los cómics, por una razón que no es
casualidad: **las páginas de un cómic son JPEG o PNG, que ya están comprimidos**,
y comprimir de nuevo algo comprimido no ahorra nada. Los programas lo saben y
los guardan tal cual. Medido sobre los cómics que circulan, la inmensa mayoría
va «almacenado».

Cuando un archivo sí está comprimido de verdad, aquí se dice y no se inventa
nada: se sigue con WinRAR o 7-Zip si están, y si no, se avisa en la primera
línea del documento, que es lo que ya se hacía.

**Sobre el formato.** RAR es propietario y su descompresión solo está descrita
en el código de `unrar`. Lo que hay aquí no descomprime: lee cabeceras y copia
bytes, que es información de estructura y está descrita en los propios archivos
—cada cabecera dice cuánto ocupa la siguiente—. No se escribe ningún RAR.
"""

from __future__ import annotations

import struct
from pathlib import Path

from .registro import obtener_registro

log = obtener_registro(__name__)

#: Las dos firmas: la de RAR 1.5 a 4.x y la de RAR 5.
FIRMA4 = b"Rar!\x1a\x07\x00"
FIRMA5 = b"Rar!\x1a\x07\x01\x00"

#: Método de compresión «guardado tal cual» en RAR 4.
GUARDADO4 = 0x30

#: Tope de lo que se saca de un archivo, por si una cabecera dice un disparate.
MAXIMO = 512 * 1024 * 1024

#: Cuántas entradas se leen como mucho.
MAXIMAS_ENTRADAS = 20000


class ErrorRAR(Exception):
    """El archivo no es un RAR o su envoltorio no se entiende."""


class Entrada:
    """Un archivo dentro del RAR, y de dónde salen sus bytes.

    :param nombre: Su ruta dentro del comprimido, con barras normales.
    :param tamano: Cuánto ocupa entero, ya juntando todos sus trozos.
    :param guardado: Si está sin comprimir y por tanto se puede sacar.
    :param trozos: Lista de ``(archivo, posición, cuántos bytes)``.  Son varios
        cuando el archivo cruza de un volumen al siguiente, que es justo el caso
        que se venía perdiendo.
    """

    __slots__ = ("nombre", "tamano", "guardado", "trozos", "es_carpeta")

    def __init__(self, nombre: str, tamano: int = 0, guardado: bool = True,
                 es_carpeta: bool = False) -> None:
        self.nombre = nombre
        self.tamano = tamano
        self.guardado = guardado
        self.es_carpeta = es_carpeta
        self.trozos: list[tuple[Path, int, int]] = []

    def datos(self) -> bytes:
        """Los bytes del archivo, juntando sus trozos en orden."""
        if not self.guardado:
            raise ErrorRAR("«%s» está comprimido y aquí solo se copian los "
                           "archivos guardados tal cual" % self.nombre)
        partes = []
        for ruta, posicion, cuantos in self.trozos:
            with open(ruta, "rb") as archivo:
                archivo.seek(posicion)
                partes.append(archivo.read(cuantos))
        return b"".join(partes)


def _numero_variable(datos: bytes, posicion: int) -> tuple[int, int]:
    """Lee uno de los números de longitud variable que usa RAR 5.

    Siete bits por byte, y el octavo dice si sigue.  Es el mismo truco que usan
    media docena de formatos, y por lo mismo: casi todos los números que hay que
    guardar son pequeños.
    """
    valor = 0
    desplazamiento = 0
    while posicion < len(datos) and desplazamiento < 64:
        byte = datos[posicion]
        posicion += 1
        valor |= (byte & 0x7F) << desplazamiento
        if not byte & 0x80:
            return valor, posicion
        desplazamiento += 7
    raise ErrorRAR("número de longitud variable sin final")


def _nombre_limpio(crudo: bytes, unicode_: bool) -> str:
    """El nombre de un archivo, tal cual se pueda leer.

    RAR 4 guarda los nombres que no son ASCII de una manera propia; cuando no se
    entiende, se cae a Latin-1, que al menos no pierde bytes. El nombre solo se
    usa para saber qué es cada cosa y ordenarlo, así que una tilde rara no
    estropea nada.
    """
    if unicode_ and b"\x00" in crudo:
        crudo = crudo.split(b"\x00")[0]
    try:
        texto = crudo.decode("utf-8")
    except UnicodeDecodeError:
        texto = crudo.decode("cp1252", "replace")
    return texto.replace("\\", "/").strip("\x00")


def _leer_rar4(rutas: list[Path]) -> list[Entrada]:
    """Recorre las cabeceras de un RAR 4 y sus volúmenes."""
    entradas: list[Entrada] = []
    pendiente: Entrada | None = None
    for ruta in rutas:
        datos = ruta.read_bytes()
        posicion = datos.find(FIRMA4)
        if posicion < 0:
            continue
        posicion += len(FIRMA4)
        while posicion + 7 <= len(datos) and len(entradas) < MAXIMAS_ENTRADAS:
            (_crc, tipo, banderas, tamano) = struct.unpack_from("<HBHH", datos,
                                                                posicion)
            if tamano < 7:
                break
            extra = 0
            if banderas & 0x8000:
                if posicion + 11 > len(datos):
                    break
                (extra,) = struct.unpack_from("<I", datos, posicion + 7)
            if tipo != 0x74:
                posicion += tamano + extra
                continue
            entrada, donde, cuantos = _cabecera4(datos, posicion, tamano, extra,
                                                 ruta)
            if entrada is None:
                posicion += tamano + extra
                continue
            sigue_antes = bool(banderas & 0x01)
            sigue_despues = bool(banderas & 0x02)
            if sigue_antes and pendiente is not None:
                pendiente.trozos.append((ruta, donde, cuantos))
                if not sigue_despues:
                    pendiente = None
            else:
                entrada.trozos.append((ruta, donde, cuantos))
                entradas.append(entrada)
                pendiente = entrada if sigue_despues else None
            posicion += tamano + extra
    return entradas


def _cabecera4(datos: bytes, posicion: int, tamano: int, extra: int, ruta: Path):
    """Los datos de una entrada de RAR 4. Devuelve ``(entrada, dónde, cuántos)``."""
    if posicion + 32 > len(datos):
        return None, 0, 0
    (empaquetado, sin_empaquetar) = struct.unpack_from("<II", datos, posicion + 7)
    metodo = datos[posicion + 25]
    (largo_nombre,) = struct.unpack_from("<H", datos, posicion + 26)
    (atributos,) = struct.unpack_from("<I", datos, posicion + 28)
    inicio_nombre = posicion + 32
    (banderas,) = struct.unpack_from("<H", datos, posicion + 3)
    if banderas & 0x0100:
        # Archivo de más de cuatro gigabytes: la parte alta va aparte.
        if inicio_nombre + 8 > len(datos):
            return None, 0, 0
        (alto_emp, alto_sin) = struct.unpack_from("<II", datos, inicio_nombre)
        empaquetado |= alto_emp << 32
        sin_empaquetar |= alto_sin << 32
        inicio_nombre += 8
    crudo = datos[inicio_nombre:inicio_nombre + largo_nombre]
    nombre = _nombre_limpio(crudo, bool(banderas & 0x0200))
    if not nombre:
        return None, 0, 0
    es_carpeta = (atributos & 0x10) != 0 or (banderas & 0xE0) == 0xE0
    entrada = Entrada(nombre, min(sin_empaquetar, MAXIMO),
                      metodo == GUARDADO4, es_carpeta)
    return entrada, posicion + tamano, min(extra or empaquetado, MAXIMO)


def _leer_rar5(rutas: list[Path]) -> list[Entrada]:
    """Recorre las cabeceras de un RAR 5 y sus volúmenes."""
    entradas: list[Entrada] = []
    pendiente: Entrada | None = None
    for ruta in rutas:
        datos = ruta.read_bytes()
        posicion = datos.find(FIRMA5)
        if posicion < 0:
            continue
        posicion += len(FIRMA5)
        while posicion + 8 <= len(datos) and len(entradas) < MAXIMAS_ENTRADAS:
            try:
                siguiente, entrada, donde, cuantos, antes, despues = _cabecera5(
                    datos, posicion, ruta)
            except ErrorRAR:
                break
            if siguiente <= posicion:
                break
            if entrada is not None:
                if antes and pendiente is not None:
                    pendiente.trozos.append((ruta, donde, cuantos))
                    if not despues:
                        pendiente = None
                else:
                    entrada.trozos.append((ruta, donde, cuantos))
                    entradas.append(entrada)
                    pendiente = entrada if despues else None
            posicion = siguiente
    return entradas


def _cabecera5(datos: bytes, posicion: int, ruta: Path):
    """Una cabecera de RAR 5, que va casi entera en números variables."""
    lugar = posicion + 4                       # los cuatro del CRC
    tamano, lugar = _numero_variable(datos, lugar)
    fin_cabecera = lugar + tamano
    tipo, lugar = _numero_variable(datos, lugar)
    banderas, lugar = _numero_variable(datos, lugar)
    if banderas & 0x0001:                      # área añadida
        _extra, lugar = _numero_variable(datos, lugar)
    tamano_datos = 0
    if banderas & 0x0002:
        tamano_datos, lugar = _numero_variable(datos, lugar)
    siguiente = fin_cabecera + tamano_datos
    if tipo != 2:                              # 2 es «un archivo»
        return siguiente, None, 0, 0, False, False
    banderas_archivo, lugar = _numero_variable(datos, lugar)
    sin_empaquetar, lugar = _numero_variable(datos, lugar)
    atributos, lugar = _numero_variable(datos, lugar)
    if banderas_archivo & 0x0002:              # lleva fecha
        lugar += 4
    if banderas_archivo & 0x0004:              # lleva suma de comprobación
        lugar += 4
    compresion, lugar = _numero_variable(datos, lugar)
    _sistema, lugar = _numero_variable(datos, lugar)
    largo_nombre, lugar = _numero_variable(datos, lugar)
    crudo = datos[lugar:lugar + min(largo_nombre, 4096)]
    nombre = _nombre_limpio(crudo, True)
    if not nombre:
        return siguiente, None, 0, 0, False, False
    # El método va en los bits 7 a 9; cero es «guardado tal cual».
    metodo = (compresion >> 7) & 0x07
    es_carpeta = bool(banderas_archivo & 0x0001) or bool(atributos & 0x10)
    entrada = Entrada(nombre, min(sin_empaquetar, MAXIMO), metodo == 0,
                      es_carpeta)
    return (siguiente, entrada, fin_cabecera, min(tamano_datos, MAXIMO),
            bool(banderas & 0x0008), bool(banderas & 0x0010))


def es_rar(ruta) -> bool:
    """Dice si el archivo es un RAR, de cualquiera de las dos versiones."""
    try:
        with open(ruta, "rb") as archivo:
            cabecera = archivo.read(8)
    except OSError:
        return False
    return cabecera.startswith(FIRMA5) or cabecera.startswith(FIRMA4)


def leer(rutas) -> list[Entrada]:
    """Las entradas de un RAR, siguiendo todos los volúmenes que se le den.

    :param rutas: El primer volumen y los siguientes, en orden.
    :raises ErrorRAR: Si no es un RAR.
    """
    lista = [Path(ruta) for ruta in rutas]
    if not lista:
        raise ErrorRAR("no se ha dado ningún archivo")
    try:
        with open(lista[0], "rb") as archivo:
            cabecera = archivo.read(8)
    except OSError as error:
        raise ErrorRAR("no se ha podido leer: %s" % error) from error
    if cabecera.startswith(FIRMA5):
        return _leer_rar5(lista)
    if cabecera.startswith(FIRMA4):
        return _leer_rar4(lista)
    raise ErrorRAR("no empieza por la firma de un RAR")


def extraer(rutas, destino, solo=None) -> tuple[list[str], list[str]]:
    """Saca a una carpeta lo que se pueda sacar.

    :param solo: Si se da, solo se sacan los archivos cuyo nombre acabe en una
        de esas extensiones.  Sirve para no volcar el `.nfo` ni la miniatura de
        un cómic.
    :return: ``(lo que ha salido, lo que no se ha podido sacar)``.  Lo segundo
        es lo que va comprimido de verdad, y hay que decirlo: un cómic con la
        mitad de las páginas parece un cómic entero.
    """
    carpeta = Path(destino)
    carpeta.mkdir(parents=True, exist_ok=True)
    salidos: list[str] = []
    fallidos: list[str] = []
    for entrada in leer(rutas):
        if entrada.es_carpeta or not entrada.nombre:
            continue
        if solo and not entrada.nombre.lower().endswith(tuple(solo)):
            continue
        if not entrada.guardado:
            fallidos.append(entrada.nombre)
            continue
        limpio = _seguro(entrada.nombre)
        if limpio is None:
            log.info("Nombre sospechoso dentro del RAR: %r", entrada.nombre)
            continue
        archivo = carpeta / limpio
        archivo.parent.mkdir(parents=True, exist_ok=True)
        try:
            archivo.write_bytes(entrada.datos())
        except (OSError, ErrorRAR) as error:
            log.info("No se ha podido sacar «%s»: %s", entrada.nombre, error)
            fallidos.append(entrada.nombre)
            continue
        salidos.append(limpio)
    return salidos, fallidos


def _seguro(nombre: str):
    """Deja el nombre en algo que no pueda escribir fuera de la carpeta.

    Un comprimido puede traer rutas con «..» o absolutas, y escribirlas tal cual
    dejaría que un archivo cualquiera pusiera cosas donde le pareciera. Es un
    problema viejo y conocido, y la respuesta es igual de vieja: quedarse solo
    con los nombres, sin nada que suba ni salga.
    """
    partes = []
    for trozo in nombre.replace("\\", "/").split("/"):
        limpio = trozo.strip().strip(".")
        if not limpio or limpio in (".", "..") or ":" in limpio:
            continue
        partes.append(limpio)
    return "/".join(partes) if partes else None
