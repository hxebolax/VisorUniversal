# -*- coding: utf-8 -*-
"""Word, Excel y PowerPoint de 1997: los formatos binarios que siguen ahí.

`.doc`, `.xls` y `.ppt` llevan más de veinte años siendo el formato antiguo, y
siguen circulando: apuntes escaneados y pasados a Word hace dos décadas, temarios
de oposición, hojas de cálculo de una asignatura, presentaciones de un profesor
que nunca actualizó nada.  Word y Excel de hoy ya avisan de que algún día
dejarán de abrirlos, y el que se los encuentra sin poder verlos no tiene a quién
pedirle que se los convierta.

Los tres viven dentro del mismo envoltorio, que lee :mod:`formatos.ole`. Lo que
cambia es qué hay dentro:

**Word** guarda el texto de una manera que no se puede leer de corrido, y esa es
la parte que cuesta. El documento está partido en **trozos** —el «piece table»—
y cada uno dice por su cuenta si está en Latin-1 o en UTF-16, porque Word 97
guardaba en un byte lo que cupiera en un byte. Leer el archivo de principio a
fin sin mirar esa tabla da un texto que parece bien y **está mal**: los trozos
salen desordenados y con la mitad de las tildes rotas. Es justo lo que hacen las
herramientas de línea de órdenes de toda la vida, y por eso avisan de que en un
documento «guardado rápido» se pierde información.

**Excel** es una ristra de registros con su número y su longitud —el formato
BIFF—, y las cadenas van casi todas en una tabla común al principio, que además
puede estar partida en trozos con un byte de cambio de codificación en cada
costura. Aquí se leen las hojas, sus nombres y sus celdas.

**PowerPoint** es un árbol de registros, y el texto está en dos clases de
átomo: uno para lo que cabía en Latin-1 y otro para lo que no.

**Lo que se saca es el texto, no el diseño.** Ni tipografías, ni colores, ni
posiciones. Es lo que hace falta para leerlo, y es lo honrado: reconstruir la
maqueta de un archivo de 1997 daría una imitación, no el documento.
"""

from __future__ import annotations

import struct
from pathlib import Path

from nucleo.documento import Metadatos
from nucleo.idioma import _
from nucleo.idioma import _n
from nucleo.registro import obtener_registro

from . import ole
from .base import Analizador, ErrorFormato, OpcionesAnalisis, registrar
from .ensamblador import escapar, montar
# Las hojas modernas ya saben poner una rejilla en una tabla de verdad y
# decidir si su primera fila son los títulos. Es el mismo problema, así que
# es el mismo código: una hoja de 1997 y una de ahora se leen igual.
from .hojas import _envolver, _recortar, _tabla_html

log = obtener_registro(__name__)

#: Cuánto texto se acepta como mucho.  Un `.doc` de esta época no pasa de unos
#: pocos megabytes de texto; más que eso significa que se ha interpretado mal
#: algo y que lo que sale es basura.
MAXIMO_TEXTO = 40 * 1024 * 1024


# ---------------------------------------------------------------------------
# Word 97 (.doc)
# ---------------------------------------------------------------------------

#: Caracteres de control de Word y qué se hace con cada uno.  Los que no están
#: aquí se dejan pasar; los que valen "" se tiran.
_CONTROLES = {
    0x07: "\n",     # fin de celda de tabla
    0x0B: "\n",     # salto de línea forzado
    0x0C: "\n",     # salto de página
    0x0D: "\n",     # fin de párrafo
    0x0E: "\n",     # fin de columna
    0x1E: "-",      # guion que no se parte
    0x1F: "",       # guion opcional: no se ve si no hace falta
    0x01: "",       # imagen incrustada
    0x02: "",       # marca de nota al pie
    0x05: "",       # marca de anotación
    0x08: "",       # dibujo
    0x13: "",       # empieza un campo
    0x14: "",       # separa el código del campo de su resultado
    0x15: "",       # acaba el campo
    0xA0: " ",      # espacio que no se parte
}


def _fib(crudo: bytes) -> dict:
    """Los datos del bloque de información del archivo de Word.

    Las posiciones **no se dan por sabidas**: se calculan recorriendo el bloque
    como manda su propia estructura, que es de longitud variable.  Los números
    fijos que circulan por ahí —0x1A2 para la tabla de trozos— valen para el
    Word 97 corriente y fallan con los archivos de otras versiones.
    """
    if len(crudo) < 96:
        raise ErrorFormato(_("El documento de Word está incompleto."))
    datos = {"nFib": struct.unpack_from("<H", crudo, 2)[0],
             "banderas": struct.unpack_from("<H", crudo, 10)[0]}
    datos["tabla"] = "1Table" if datos["banderas"] & 0x0200 else "0Table"
    datos["cifrado"] = bool(datos["banderas"] & 0x0100)
    datos["complejo"] = bool(datos["banderas"] & 0x0004)
    # Word 6 y 95 no tienen las tres tablas de longitud variable: el texto va
    # seguido entre dos posiciones y ya está.
    datos["fcMin"] = struct.unpack_from("<I", crudo, 24)[0]
    datos["fcMac"] = struct.unpack_from("<I", crudo, 28)[0]
    datos["ccpText"] = 0
    datos["fcClx"] = datos["lcbClx"] = 0
    if datos["nFib"] < 193:
        return datos
    (csw,) = struct.unpack_from("<H", crudo, 32)
    base_lw = 32 + 2 + csw * 2
    if base_lw + 2 > len(crudo):
        return datos
    (cslw,) = struct.unpack_from("<H", crudo, base_lw)
    lw = base_lw + 2
    if lw + 16 <= len(crudo):
        datos["ccpText"] = struct.unpack_from("<I", crudo, lw + 12)[0]
    base_fc = lw + cslw * 4
    if base_fc + 2 > len(crudo):
        return datos
    (pares,) = struct.unpack_from("<H", crudo, base_fc)
    fc = base_fc + 2
    # El par número 33 es el que dice dónde está la tabla de trozos.
    if pares > 33 and fc + 33 * 8 + 8 <= len(crudo):
        datos["fcClx"], datos["lcbClx"] = struct.unpack_from(
            "<II", crudo, fc + 33 * 8)
    return datos


def _trozos(clx: bytes) -> list[tuple[int, int, int, bool]]:
    """La tabla de trozos: qué parte del texto está dónde y en qué código.

    Devuelve una lista de ``(carácter inicial, carácter final, posición en el
    archivo, si va comprimido a un byte)``.

    El «comprimido» es lo que hace falta entender: Word guarda en Latin-1 los
    trozos que caben en Latin-1 y en UTF-16 los que no, **dentro del mismo
    documento**, y lo dice con un bit de la propia posición.
    """
    posicion = 0
    # Antes de la tabla puede haber propiedades de formato, que aquí no hacen
    # falta: se saltan por su longitud.
    while posicion < len(clx) and clx[posicion] == 0x01:
        if posicion + 3 > len(clx):
            return []
        (largo,) = struct.unpack_from("<H", clx, posicion + 1)
        posicion += 3 + largo
    if posicion >= len(clx) or clx[posicion] != 0x02:
        return []
    (largo,) = struct.unpack_from("<I", clx, posicion + 1)
    tabla = clx[posicion + 5:posicion + 5 + largo]
    if len(tabla) < 16:
        return []
    cuantos = (len(tabla) - 4) // 12
    if cuantos <= 0:
        return []
    puntos = list(struct.unpack_from("<%dI" % (cuantos + 1), tabla, 0))
    salida = []
    base = (cuantos + 1) * 4
    for numero in range(cuantos):
        (fc,) = struct.unpack_from("<I", tabla, base + numero * 8 + 2)
        comprimido = bool(fc & 0x40000000)
        donde = (fc & 0x3FFFFFFF) // 2 if comprimido else (fc & 0x3FFFFFFF)
        salida.append((puntos[numero], puntos[numero + 1], donde, comprimido))
    return salida


def _limpiar(texto: str) -> str:
    """Cambia los caracteres de control de Word por lo que significan."""
    salida = []
    saltando = False
    for letra in texto:
        codigo = ord(letra)
        if codigo == 0x13:
            # Empieza el código de un campo —«PAGE», «REF»—, que no es texto
            # del documento: se salta hasta el separador.
            saltando = True
            continue
        if codigo in (0x14, 0x15):
            saltando = False
            continue
        if saltando:
            continue
        if codigo in _CONTROLES:
            salida.append(_CONTROLES[codigo])
        elif codigo < 0x20 and codigo not in (0x09, 0x0A):
            continue
        else:
            salida.append(letra)
    return "".join(salida)


def texto_de_doc(contenedor) -> str:
    """El texto de un documento de Word 97, siguiendo su tabla de trozos."""
    principal = contenedor.flujo("WordDocument")
    if not principal:
        raise ErrorFormato(_("Este archivo no lleva dentro un documento de Word."))
    datos = _fib(principal)
    if datos["cifrado"]:
        raise ErrorFormato(_(
            "Este documento de Word está protegido con contraseña y no se puede "
            "leer. El programa no quita protecciones de ningún archivo."))
    clx = b""
    if datos["lcbClx"]:
        tabla = contenedor.flujo(datos["tabla"]) or contenedor.flujo(
            "1Table" if datos["tabla"] == "0Table" else "0Table")
        clx = tabla[datos["fcClx"]:datos["fcClx"] + datos["lcbClx"]]
    piezas = _trozos(clx) if clx else []

    if not piezas:
        # Word 6, Word 95, o un archivo al que le falta la tabla: el texto va
        # seguido entre las dos posiciones que da la cabecera. Es peor, y es
        # mejor que no leer nada.
        crudo = principal[datos["fcMin"]:datos["fcMac"]]
        return _limpiar(crudo.decode("cp1252", "replace"))

    tope = datos["ccpText"] or piezas[-1][1]
    partes = []
    for desde, hasta, donde, comprimido in piezas:
        if desde >= tope:
            break
        hasta = min(hasta, tope)
        cuantos = hasta - desde
        if cuantos <= 0:
            continue
        if comprimido:
            crudo = principal[donde:donde + cuantos]
            partes.append(crudo.decode("cp1252", "replace"))
        else:
            crudo = principal[donde:donde + cuantos * 2]
            partes.append(crudo.decode("utf-16-le", "replace"))
        if sum(len(parte) for parte in partes) > MAXIMO_TEXTO:
            log.info("El documento de Word se corta en %d caracteres", MAXIMO_TEXTO)
            break
    return _limpiar("".join(partes))


# ---------------------------------------------------------------------------
# Excel 97 (.xls)
# ---------------------------------------------------------------------------

_BOF = 0x0809
_EOF = 0x000A
_BOUNDSHEET = 0x0085
_SST = 0x00FC
_CONTINUE = 0x003C
_LABELSST = 0x00FD
_LABEL = 0x0204
_RSTRING = 0x00D6
_NUMBER = 0x0203
_RK = 0x027E
_MULRK = 0x00BD
_FORMULA = 0x0006
_STRING = 0x0207
_BOOLERR = 0x0205
_FILEPASS = 0x002F

#: Los números con los que puede empezar un libro, uno por versión del formato.
#: Los tres primeros son de Excel 2, 3 y 4; el último, del 5 en adelante, que es
#: el que va dentro de un envoltorio y el que aquí se lee.
_INICIOS_BIFF = (0x0009, 0x0209, 0x0409, 0x0809)


def parece_biff_suelto(datos: bytes) -> bool:
    """Dice si el archivo es una hoja de las de antes del envoltorio.

    Excel 2, 3 y 4 escribían sus registros directamente en el archivo, sin el
    sistema de archivos dentro del archivo que llegó con Excel 5.  Se reconocen
    y se dicen: es más útil saber que un archivo es de 1992 que oír que «no es
    un documento de Office».
    """
    if len(datos) < 4:
        return False
    numero, largo = struct.unpack_from("<HH", datos, 0)
    return numero in _INICIOS_BIFF and 4 <= largo <= 4096


#: Cuántas filas se leen como mucho de una hoja.  Es el mismo tope que el de las
#: hojas modernas y por la misma razón: una hoja de cien mil filas no es un
#: documento que nadie recorra de oído.
MAXIMAS_FILAS = 5000


def _registros(flujo: bytes, desde: int = 0):
    """Recorre los registros de un flujo BIFF: número, datos y dónde acaba."""
    posicion = desde
    while posicion + 4 <= len(flujo):
        numero, largo = struct.unpack_from("<HH", flujo, posicion)
        cuerpo = flujo[posicion + 4:posicion + 4 + largo]
        yield numero, cuerpo, posicion + 4 + largo
        posicion += 4 + largo


def _cadena_biff(datos: bytes, posicion: int, con_largo_corto: bool = False):
    """Lee una cadena de las de BIFF8. Devuelve ``(texto, dónde sigue)``.

    El formato guarda **cuántos caracteres** hay y después un byte de banderas
    que dice si van en un byte o en dos, y si detrás vienen datos de formato que
    hay que saltarse.  Contar bytes en vez de caracteres es el error clásico y
    da una cadena cortada a la mitad de una tilde.
    """
    if con_largo_corto:
        if posicion >= len(datos):
            return "", posicion
        cuantos = datos[posicion]
        posicion += 1
    else:
        if posicion + 2 > len(datos):
            return "", posicion
        (cuantos,) = struct.unpack_from("<H", datos, posicion)
        posicion += 2
    if posicion >= len(datos):
        return "", posicion
    banderas = datos[posicion]
    posicion += 1
    anchas = bool(banderas & 0x01)
    trozos = 0
    extra = 0
    if banderas & 0x08:                       # texto con formato
        (trozos,) = struct.unpack_from("<H", datos, posicion)
        posicion += 2
    if banderas & 0x04:                       # datos de otro alfabeto
        (extra,) = struct.unpack_from("<I", datos, posicion)
        posicion += 4
    largo = cuantos * (2 if anchas else 1)
    crudo = datos[posicion:posicion + largo]
    posicion += largo
    posicion += trozos * 4 + extra
    texto = (crudo.decode("utf-16-le", "replace") if anchas
             else crudo.decode("cp1252", "replace"))
    return texto, posicion


def _tabla_de_cadenas(flujo: bytes, inicio: int, cuerpo: bytes) -> list[str]:
    """La tabla común de cadenas, con sus trozos pegados.

    La tabla puede no caber en un registro y seguir en otros.  Y en cada
    costura, el primer byte del trozo siguiente **vuelve a decir** si lo que
    viene va en uno o en dos bytes, porque una cadena puede empezar en un trozo
    y acabar en el siguiente cambiando de codificación por el camino. Es el
    detalle que hace que la tabla se lea entera o se lea rota.
    """
    juntos = bytearray(cuerpo)
    costuras = [len(cuerpo)]
    posicion = inicio
    for numero, siguiente, fin in _registros(flujo, inicio):
        if numero != _CONTINUE:
            break
        juntos.extend(siguiente)
        costuras.append(len(juntos))
        posicion = fin
    datos = bytes(juntos)
    if len(datos) < 8:
        return []
    (_total, cuantas) = struct.unpack_from("<II", datos, 0)
    cadenas = []
    donde = 8
    for _numero in range(min(cuantas, 1 << 20)):
        if donde >= len(datos):
            break
        texto, donde = _cadena_biff(datos, donde)
        cadenas.append(texto)
    return cadenas


def _valor_rk(crudo: int) -> float:
    """Deshace un número de los que Excel guarda en cuatro bytes.

    Es una compresión con nombre propio: si el número era un entero pequeño o un
    decimal con dos cifras, cabe en cuatro bytes en vez de en ocho.
    """
    if crudo & 0x02:
        valor = float(crudo >> 2 if crudo >> 2 < (1 << 29)
                      else (crudo >> 2) - (1 << 30))
    else:
        valor = struct.unpack("<d", struct.pack("<Q", (crudo & 0xFFFFFFFC) << 32))[0]
    return valor / 100 if crudo & 0x01 else valor


def _como_texto(valor: float) -> str:
    """Un número tal y como conviene leerlo."""
    if valor == int(valor) and abs(valor) < 1e15:
        return str(int(valor))
    return ("%.10g" % valor)


def esta_cifrado(flujo: bytes) -> bool:
    """Dice si el libro va cifrado.

    Lo dice un registro que va casi al principio.  Detectarlo importa porque sin
    ello el libro **se abre igual**: los registros siguen ahí, pero su contenido
    es ruido, y lo que sale son nombres de hoja como «䉽퉶捠». Un archivo que se
    abre y dice disparates es peor que uno que dice claramente que no puede.
    """
    for numero, _cuerpo, _fin in _registros(flujo):
        if numero == _FILEPASS:
            return True
        if numero == _BOUNDSHEET or numero == _EOF:
            return False
    return False


def hojas_de_xls(flujo: bytes) -> list[tuple[str, list[list[str]]]]:
    """Las hojas de un libro de Excel 97, con su nombre y sus celdas."""
    cadenas: list[str] = []
    hojas: list[tuple[str, int]] = []
    for numero, cuerpo, fin in _registros(flujo):
        try:
            if numero == _BOUNDSHEET and len(cuerpo) >= 6:
                (donde,) = struct.unpack_from("<I", cuerpo, 0)
                nombre, _sigue = _cadena_biff(cuerpo, 6, con_largo_corto=True)
                hojas.append((nombre or _("Hoja"), donde))
            elif numero == _SST:
                cadenas = _tabla_de_cadenas(flujo, fin, cuerpo)
            elif numero == _EOF and hojas:
                break
        except (struct.error, IndexError, ValueError) as error:
            log.debug("Registro %04X ilegible: %s", numero, error)
    if not hojas:
        return [(_("Hoja"), _celdas_de_hoja(flujo, 0, cadenas))]
    return [(nombre, _celdas_de_hoja(flujo, donde, cadenas))
            for nombre, donde in hojas]

def _celdas_de_hoja(flujo: bytes, inicio: int, cadenas: list[str]):
    """Las celdas de una hoja, ya puestas en su fila y su columna."""
    rejilla: dict[int, dict[int, str]] = {}

    def poner(fila: int, columna: int, texto: str) -> None:
        if texto == "" or fila > 1 << 20 or columna > 1 << 14:
            return
        rejilla.setdefault(fila, {})[columna] = texto

    #: La última celda que trajo una fórmula cuyo resultado es texto. Ese texto
    #: no viene con la fórmula: viene en el registro siguiente, y sin guardar
    #: dónde iba se perdería.
    pendiente = None
    for numero, cuerpo, _fin in _registros(flujo, inicio):
        if numero == _EOF:
            break
        try:
            pendiente = _una_celda(numero, cuerpo, cadenas, poner, pendiente)
        except (struct.error, IndexError, ValueError) as error:
            # Un registro roto se salta y el resto de la hoja se lee igual. Es
            # lo que hay que hacer con un archivo de hace veinte años sacado de
            # un disquete: perder una celda es mucho mejor que perder la hoja.
            log.debug("Celda ilegible en el registro %04X: %s", numero, error)
    if not rejilla:
        return []
    ultima_fila = min(max(rejilla), MAXIMAS_FILAS - 1)
    ancho = max((max(columnas) for columnas in rejilla.values()), default=0)
    return [[rejilla.get(fila, {}).get(columna, "")
             for columna in range(ancho + 1)]
            for fila in range(ultima_fila + 1)]


def _una_celda(numero: int, cuerpo: bytes, cadenas: list[str], poner,
               pendiente):
    """Interpreta un registro de celda y lo pone en su sitio.

    Devuelve dónde quedó pendiente un resultado de fórmula, si lo hay.
    """
    if numero == _LABELSST and len(cuerpo) >= 10:
        fila, columna, _xf, indice = struct.unpack_from("<HHHI", cuerpo, 0)
        if 0 <= indice < len(cadenas):
            poner(fila, columna, cadenas[indice])
    elif numero in (_LABEL, _RSTRING) and len(cuerpo) >= 8:
        fila, columna, _xf = struct.unpack_from("<HHH", cuerpo, 0)
        texto, _sigue = _cadena_biff(cuerpo, 6)
        poner(fila, columna, texto)
    elif numero == _NUMBER and len(cuerpo) >= 14:
        fila, columna, _xf, valor = struct.unpack_from("<HHHd", cuerpo, 0)
        poner(fila, columna, _como_texto(valor))
    elif numero == _RK and len(cuerpo) >= 10:
        fila, columna, _xf, crudo = struct.unpack_from("<HHHI", cuerpo, 0)
        poner(fila, columna, _como_texto(_valor_rk(crudo)))
    elif numero == _MULRK and len(cuerpo) >= 10:
        fila, primera = struct.unpack_from("<HH", cuerpo, 0)
        cuantas = (len(cuerpo) - 6) // 6
        for indice in range(cuantas):
            (crudo,) = struct.unpack_from("<I", cuerpo, 4 + indice * 6 + 2)
            poner(fila, primera + indice, _como_texto(_valor_rk(crudo)))
    elif numero == _FORMULA and len(cuerpo) >= 14:
        fila, columna, _xf = struct.unpack_from("<HHH", cuerpo, 0)
        (marca,) = struct.unpack_from("<H", cuerpo, 12)
        if marca == 0xFFFF:
            # El resultado no es un número. Llega en el registro siguiente.
            return (fila, columna)
        (valor,) = struct.unpack_from("<d", cuerpo, 6)
        poner(fila, columna, _como_texto(valor))
    elif numero == _STRING and pendiente is not None:
        texto, _sigue = _cadena_biff(cuerpo, 0)
        poner(pendiente[0], pendiente[1], texto)
    return None


# ---------------------------------------------------------------------------
# PowerPoint 97 (.ppt)
# ---------------------------------------------------------------------------

_PPT_DIAPOSITIVA = 1006
_PPT_NOTAS = 1008
_PPT_GUION = 4080          # la lista de diapositivas con su texto (el esquema)
_PPT_TEXTO_ANCHO = 4000
_PPT_TEXTO_ESTRECHO = 4008

#: Textos internos que PowerPoint guarda dentro de las diapositivas y que no son
#: de la presentación: marcas de versión del programa y nombres de los objetos
#: incrustados. Salen en el mismo sitio que el texto de verdad, y leerlos en voz
#: alta sería leer la maquinaria.
_BASURA = ("___ppt", "objekt-manager", "package", "paket", "ole", "shellobjekt")


def _recorrer_ppt(datos: bytes, desde: int, hasta: int, salida: list,
                  dentro: int = 0) -> None:
    """Recorre el árbol de registros de una presentación.

    Un registro dice en su cabecera si es un contenedor —lo dice el primer medio
    byte— y en ese caso lo que sigue son más registros.  Recorrerlo como árbol y
    no de corrido es lo que hace que el texto salga **en el orden de las
    diapositivas** y no en el que se guardó.

    Y solo se recoge lo que está **dentro de una diapositiva o de sus notas**.
    Por el mismo archivo andan el texto de la plantilla —«Haga clic para editar
    el título»—, los nombres de los objetos incrustados y las marcas de versión
    del programa. Todo eso está en átomos idénticos a los del texto de verdad, y
    recogerlo de corrido daría una presentación llena de ruido en la que hay que
    adivinar qué escribió una persona.
    """
    posicion = desde
    while posicion + 8 <= hasta:
        version, tipo, largo = struct.unpack_from("<HHI", datos, posicion)
        cuerpo = posicion + 8
        fin = min(cuerpo + largo, hasta)
        if fin <= posicion:
            return
        if (version & 0x000F) == 0x000F:
            propio = dentro
            if tipo in (_PPT_DIAPOSITIVA, _PPT_NOTAS) or (
                    tipo == _PPT_GUION and dentro == 0 and salida is not None
                    and getattr(salida, "guion", False)):
                salida.append(["", _PPT_NOTAS if tipo == _PPT_NOTAS
                               else _PPT_DIAPOSITIVA])
                propio = tipo if tipo != _PPT_GUION else _PPT_DIAPOSITIVA
            _recorrer_ppt(datos, cuerpo, fin, salida, propio)
        elif dentro and tipo == _PPT_TEXTO_ESTRECHO:
            _anotar(salida, datos[cuerpo:fin].decode("cp1252", "replace"))
        elif dentro and tipo == _PPT_TEXTO_ANCHO:
            _anotar(salida, datos[cuerpo:fin].decode("utf-16-le", "replace"))
        posicion = fin


def _anotar(salida: list, texto: str) -> None:
    """Añade un texto a la diapositiva que se esté recorriendo."""
    limpio = texto.replace("\r", "\n").replace("\x0b", "\n").strip("\x00").strip()
    if not limpio:
        return
    plano = limpio.lower()
    if any(plano.startswith(marca) for marca in _BASURA):
        return
    if not salida:
        salida.append(["", _PPT_DIAPOSITIVA])
    salida[-1][0] = (salida[-1][0] + "\n" + limpio) if salida[-1][0] else limpio


class _Recogida(list):
    """Una lista que además dice si se está recogiendo del guion.

    Hace falta porque la misma función recorre el archivo dos veces: la primera
    buscando el texto donde debería estar —dentro de cada diapositiva— y, si no
    aparece, la segunda buscándolo en el guion.
    """

    guion = False


def esta_cifrada(contenedor) -> bool:
    """Dice si la presentación va cifrada.

    Lo dice un número del flujo «Current User», que PowerPoint escribe con un
    valor cuando el archivo está cifrado y con otro cuando no.  Es más fiable
    que ir buscando el registro del cifrado por el archivo: ese está anidado
    donde le toque y este número está siempre en el mismo sitio.
    """
    crudo = contenedor.flujo("Current User")
    if len(crudo) < 16:
        return False
    (marca,) = struct.unpack_from("<I", crudo, 12)
    return marca == 0xF3D1C4DF


def diapositivas_de_ppt(flujo: bytes) -> list[tuple[str, bool]]:
    """El texto de cada diapositiva, y si lo que trae son notas del ponente.

    Se mira primero dentro de las diapositivas, que es donde vive el texto de
    una presentación normal.  Algunas —según con qué versión se guardaran— lo
    tienen únicamente en **el guion**, que es la lista con la que PowerPoint
    dibuja la vista de esquema; entonces se lee de ahí, porque el texto está y
    perderlo por dónde esté guardado no tendría ningún sentido.
    """
    crudo = _Recogida()
    _recorrer_ppt(flujo, 0, len(flujo), crudo)
    salida = [(texto.strip(), tipo == _PPT_NOTAS)
              for texto, tipo in crudo if texto.strip()]
    if salida:
        return salida
    otra = _Recogida()
    otra.guion = True
    _recorrer_ppt(flujo, 0, len(flujo), otra)
    return [(texto.strip(), tipo == _PPT_NOTAS)
            for texto, tipo in otra if texto.strip()]


# ---------------------------------------------------------------------------
# Los analizadores
# ---------------------------------------------------------------------------

def _metadatos(contenedor, ruta: Path) -> Metadatos:
    """El título y el autor, del resumen que Office guarda aparte.

    Es un flujo con nombre de carácter de control, y dentro hay una tabla de
    propiedades numeradas: la 2 es el título y la 4 el autor.  Si no está o no
    se entiende, se usa el nombre del archivo, que siempre dice algo.
    """
    titulo = autor = ""
    crudo = contenedor.flujo("\x05SummaryInformation")
    if len(crudo) > 48:
        try:
            titulo, autor = _resumen(crudo)
        except Exception as error:                      # pragma: no cover
            log.debug("Resumen del archivo ilegible: %s", error)
    return Metadatos(titulo=titulo or ruta.stem, autor=autor)


def _resumen(crudo: bytes) -> tuple[str, str]:
    """Saca el título y el autor de la tabla de propiedades."""
    (secciones,) = struct.unpack_from("<I", crudo, 24)
    if secciones < 1:
        return "", ""
    (inicio,) = struct.unpack_from("<I", crudo, 44)
    if inicio + 8 > len(crudo):
        return "", ""
    (_tam, cuantas) = struct.unpack_from("<II", crudo, inicio)
    valores = {}
    for numero in range(min(cuantas, 64)):
        base = inicio + 8 + numero * 8
        if base + 8 > len(crudo):
            break
        identificador, donde = struct.unpack_from("<II", crudo, base)
        sitio = inicio + donde
        if sitio + 8 > len(crudo):
            continue
        (tipo,) = struct.unpack_from("<I", crudo, sitio)
        if tipo not in (30, 31):                       # cadena de 8 o de 16 bits
            continue
        (largo,) = struct.unpack_from("<I", crudo, sitio + 4)
        bytes_ = crudo[sitio + 8:sitio + 8 + largo * (2 if tipo == 31 else 1)]
        texto = (bytes_.decode("utf-16-le", "replace") if tipo == 31
                 else bytes_.decode("cp1252", "replace"))
        valores[identificador] = texto.split("\x00")[0].strip()
    return valores.get(2, ""), valores.get(4, "")


def _parrafos_a_html(texto: str) -> list[str]:
    """Los párrafos de un texto, ya escapados y en su etiqueta."""
    partes = []
    for parrafo in texto.split("\n"):
        limpio = parrafo.strip()
        if limpio:
            partes.append("<p>%s</p>" % escapar(limpio))
    return partes


class AnalizadorDOC(Analizador):
    """Documentos de Word 97-2003."""

    extensiones = (".doc", ".dot")
    descripcion = _("Documentos de Word 97-2003")

    def analizar(self, ruta, opciones: OpcionesAnalisis):
        camino = Path(ruta)
        contenedor = _abrir(camino)
        texto = texto_de_doc(contenedor)
        if not texto.strip():
            raise ErrorFormato(_(
                "Este documento de Word no tiene texto que leer. Puede que solo "
                "contenga imágenes."))
        cuerpo = "\n".join(_parrafos_a_html(texto))
        return montar([("documento.xhtml", _envolver(cuerpo))],
                      _metadatos(contenedor, camino), camino, opciones)


class AnalizadorXLS(Analizador):
    """Libros de Excel 97-2003."""

    extensiones = (".xls", ".xlt")
    descripcion = _("Libros de Excel 97-2003")

    def analizar(self, ruta, opciones: OpcionesAnalisis):
        camino = Path(ruta)
        contenedor = _abrir(camino)
        flujo = contenedor.flujo("Workbook") or contenedor.flujo("Book")
        if not flujo:
            raise ErrorFormato(_("Este archivo no lleva dentro un libro de Excel."))
        if esta_cifrado(flujo):
            raise ErrorFormato(_(
                "Este libro de Excel está protegido con contraseña y no se puede "
                "leer. El programa no quita protecciones de ningún archivo."))
        secciones = []
        for numero, (nombre, filas) in enumerate(hojas_de_xls(flujo), start=1):
            partes = ["<h1>%s</h1>" % escapar(nombre)]
            recortadas = _recortar(filas)
            if recortadas:
                partes.append("<p>%s</p>" % escapar(
                    _n("%d fila", "%d filas", len(recortadas)) % len(recortadas)))
                partes.append(_tabla_html(recortadas))
            else:
                partes.append("<p>%s</p>" % escapar(_("Esta hoja está vacía.")))
            secciones.append(("hoja%d.xhtml" % numero,
                              _envolver("".join(partes))))
        if not secciones:
            raise ErrorFormato(_("No se ha podido leer ninguna hoja."))
        return montar(secciones, _metadatos(contenedor, camino), camino, opciones)


class AnalizadorPPT(Analizador):
    """Presentaciones de PowerPoint 97-2003."""

    extensiones = (".ppt", ".pps", ".pot")
    descripcion = _("Presentaciones de PowerPoint 97-2003")

    def analizar(self, ruta, opciones: OpcionesAnalisis):
        camino = Path(ruta)
        contenedor = _abrir(camino)
        flujo = contenedor.flujo("PowerPoint Document")
        if not flujo:
            raise ErrorFormato(_(
                "Este archivo no lleva dentro una presentación de PowerPoint."))
        if esta_cifrada(contenedor):
            raise ErrorFormato(_(
                "Esta presentación está protegida con contraseña y no se puede "
                "leer. El programa no quita protecciones de ningún archivo."))
        diapositivas = diapositivas_de_ppt(flujo)
        if not diapositivas:
            raise ErrorFormato(_(
                "Esta presentación no tiene texto que leer. Puede que solo "
                "contenga imágenes."))
        secciones = []
        numero = 0
        for indice, (texto, son_notas) in enumerate(diapositivas, start=1):
            if son_notas:
                cabecera = "<h2>%s</h2>" % escapar(_("Notas del ponente"))
            else:
                numero += 1
                cabecera = "<h1>%s</h1>" % escapar(_("Diapositiva %d") % numero)
            cuerpo = cabecera + "".join(_parrafos_a_html(texto))
            secciones.append(("diapositiva%d.xhtml" % indice, _envolver(cuerpo)))
        return montar(secciones, _metadatos(contenedor, camino), camino, opciones)


def _abrir(camino: Path):
    """Abre el envoltorio y traduce sus fallos a los del programa."""
    try:
        return ole.abrir(camino)
    except ole.ErrorOLE as error:
        try:
            cabecera = camino.open("rb").read(8)
        except OSError:
            cabecera = b""
        if parece_biff_suelto(cabecera):
            raise ErrorFormato(_(
                "Esta hoja es de Excel 4 o anterior, de antes de 1993, y usa un "
                "formato distinto del que este programa lee. Abriéndola con "
                "Excel o con LibreOffice y guardándola otra vez se puede leer "
                "aquí.")) from error
        raise ErrorFormato(_(
            "Este archivo no es un documento de Office 97: %s") % error) from error


registrar(AnalizadorDOC())
registrar(AnalizadorXLS())
registrar(AnalizadorPPT())
