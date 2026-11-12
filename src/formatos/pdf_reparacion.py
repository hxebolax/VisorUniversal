# -*- coding: utf-8 -*-
"""Reparar un PDF roto sin instalar nada y sin tocar el original.

Un PDF no es un archivo lineal: es un montón de objetos numerados y, al final,
una **tabla de referencias cruzadas** que dice en qué byte empieza cada uno.
Esa tabla es lo primero que se rompe.  Basta con que alguien corte una descarga,
que un servidor añada una línea, que un programa guarde mal una versión
incremental, y el índice deja de apuntar a donde debe.  El contenido sigue
entero; lo que se ha perdido es el mapa.

Cuando eso pasa, cada lector reacciona distinto y esa diferencia se nota:

* **PDFium** —el motor del programa— reconstruye el mapa por su cuenta y abre
  el archivo sin decir nada.  Por eso muchos PDF «rotos» se leen aquí.
* **pdfminer**, que es de donde salen el tamaño de letra y las tablas
  (:mod:`formatos.pdf_geometria`), es estricto y se niega: *Unexpected EOF*.

O sea que en un archivo con el índice roto el programa lee el texto pero pierde
los encabezados y las tablas, que es justo lo que hace falta.  De ahí este
módulo: **reconstruye el mapa** y escribe una copia sana.

Cómo se reconstruye
-------------------

El truco es que los objetos no se han movido: siguen en el mismo byte del
archivo.  Lo único que falta es la lista de dónde está cada uno, y esa lista se
puede volver a levantar leyendo el archivo de principio a fin y anotando cada
``12 0 obj`` que aparece.  Con eso se escribe una tabla nueva **al final**, sin
tocar un solo byte de los originales, y se apunta a ella.  Es la misma técnica
que usa un lector tolerante, solo que dejándola escrita en un archivo.

Lo que no se intenta
--------------------

Si el archivo guarda sus objetos dentro de *flujos de objetos* comprimidos
—lo normal desde PDF 1.5— los que estén ahí dentro no aparecen como
``N 0 obj`` y no se pueden localizar así.  En ese caso la reconstrucción se
queda en lo que encuentre y se comprueba **si sirve** antes de darla por buena:
una copia que no se abre mejor que el original no se devuelve.  Esa
comprobación es lo que separa reparar de estropear.

Si está instalado **pikepdf**, se usa primero: reescribe el archivo entero con
QPDF por debajo y arregla cosas que esto no puede.  Es opcional y no hace falta
para lo normal.

Garantías
---------

* El original **nunca** se toca, ni se sobrescribe, ni se mueve.
* La copia va a la carpeta temporal del programa y se borra sola.
* Si el archivo está firmado digitalmente, la copia deja de estarlo: se avisa,
  porque una copia reparada no es el documento firmado.
"""

from __future__ import annotations

import re
from pathlib import Path

from nucleo.idioma import _
from nucleo.registro import obtener_registro, registrar_excepcion

from .pdf_hallazgos import Hallazgo, Severidad

log = obtener_registro(__name__)

#: Tamaño máximo que se intenta reparar leyendo el archivo entero en memoria.
#: Por encima de esto la reparación se salta: un PDF de más de medio giga con
#: el índice roto es un caso raro, y cargarlo entero para arreglarlo costaría
#: más memoria de la que conviene pedirle a un equipo modesto.
TAMANO_MAXIMO = 512 * 1024 * 1024

#: Definición de un objeto de nivel superior: «12 0 obj».  Se exige que vaya
#: precedida de un salto de línea o del principio del archivo para no confundir
#: con la misma secuencia dentro de un flujo comprimido.
_OBJETO = re.compile(rb"(?:^|[\r\n])\s*(\d{1,10})\s+(\d{1,5})\s+obj\b")

#: Diccionario ``trailer`` clásico.  Puede haber varios —uno por cada versión
#: incremental— y vale el último que nombre la raíz del documento.
_TRAILER = re.compile(rb"trailer\s*<<", re.IGNORECASE)

#: Objeto que declara ser el catálogo, para cuando no hay ningún ``trailer``
#: aprovechable y hay que fabricar uno.
_CATALOGO = re.compile(rb"/Type\s*/Catalog\b")


def parece_roto(ruta: Path) -> bool:
    """Comprueba barato si al archivo le falta el final o el índice.

    Solo mira los últimos bytes: un PDF entero termina en ``%%EOF`` precedido
    de ``startxref`` y un desplazamiento.  Es una comprobación de descarte, no
    un diagnóstico: hay archivos que pasan esto y aun así tienen el índice mal.
    """
    try:
        with open(ruta, "rb") as archivo:
            archivo.seek(0, 2)
            tamano = archivo.tell()
            archivo.seek(max(0, tamano - 2048))
            final = archivo.read()
    except OSError:
        return True
    return b"startxref" not in final or b"%%EOF" not in final


def reparar(origen: Path, destino: Path) -> Path | None:
    """Escribe una copia sana del PDF y devuelve su ruta, o ``None``.

    Se prueban los procedimientos de más a menos capaz y el primero que
    produzca un archivo **que se abra mejor que el original** gana.  Que la
    copia se abra no se supone: se comprueba, porque una reparación que empeora
    las cosas es peor que no reparar.

    :param origen: El PDF con problemas.  No se modifica.
    :param destino: Dónde escribir la copia.  Tiene que ser distinto del
                    origen; si coincide, no se hace nada.
    """
    origen = Path(origen)
    destino = Path(destino)
    if origen.resolve() == destino.resolve():
        log.warning("La reparación no puede escribir sobre el archivo original.")
        return None
    try:
        if origen.stat().st_size > TAMANO_MAXIMO:
            log.info("El PDF es demasiado grande para repararlo: %s", origen)
            return None
    except OSError:
        return None
    destino.parent.mkdir(parents=True, exist_ok=True)

    for nombre, procedimiento in (("pikepdf", _con_pikepdf),
                                  ("reconstrucción propia", _reconstruir_indice)):
        try:
            if not procedimiento(origen, destino):
                continue
        except Exception as error:
            registrar_excepcion(log, "La reparación con %s ha fallado" % nombre, error)
            continue
        if _mejor_que(destino, origen):
            log.info("PDF reparado con %s: %s", nombre, destino.name)
            return destino
        log.debug("La copia hecha con %s no mejora el original.", nombre)
        _borrar(destino)
    return None


def hallazgo_reparado(firmado: bool = False) -> Hallazgo:
    """Devuelve el aviso que se anota cuando se ha reparado un PDF."""
    if firmado:
        return Hallazgo(
            "REPARADO_FIRMADO",
            _("El archivo estaba dañado y se ha leído desde una copia reparada. "
              "Esa copia ya no conserva la firma digital del original."),
            Severidad.AVISO,
            remedio=_("El archivo original no se ha modificado."))
    return Hallazgo(
        "REPARADO",
        _("El archivo tenía el índice interno dañado y se ha leído desde una "
          "copia reparada."),
        Severidad.INFORMACION,
        remedio=_("El archivo original no se ha modificado."))


# ---------------------------------------------------------------------------
# Procedimientos
# ---------------------------------------------------------------------------

def _con_pikepdf(origen: Path, destino: Path) -> bool:
    """Reescribe el archivo con pikepdf, si está instalado.

    Es el mejor de los dos: QPDF, que es lo que pikepdf lleva dentro, entiende
    los flujos de objetos comprimidos y puede recuperar objetos que la
    reconstrucción propia no ve.  Como es opcional, su ausencia no es un error.
    """
    try:
        import pikepdf
    except ImportError:
        return False
    with pikepdf.open(str(origen), attempt_recovery=True) as pdf:
        pdf.save(str(destino), linearize=True)
    return destino.is_file()


def _reconstruir_indice(origen: Path, destino: Path) -> bool:
    """Reconstruye la tabla de referencias cruzadas al final de una copia.

    No se reescribe nada: se copian los bytes originales tal cual y se les
    añade detrás un índice nuevo, calculado leyendo dónde empieza cada objeto.
    Así los desplazamientos que se anotan son válidos por construcción, y
    ningún contenido puede perderse por el camino, que es el riesgo de
    cualquier reparación que reescriba.
    """
    datos = origen.read_bytes()
    objetos = _localizar_objetos(datos)
    if not objetos:
        return False
    raiz = _referencia_a_raiz(datos, objetos)
    if raiz is None:
        return False
    mayor = max(objetos)
    inicio_indice = len(datos) + 1
    lineas = [b"\n", b"xref\n", b"0 %d\n" % (mayor + 1),
              b"0000000000 65535 f \n"]
    for numero in range(1, mayor + 1):
        posicion = objetos.get(numero)
        if posicion is None:
            # Un hueco en la numeración es legítimo: el objeto se borró en una
            # versión anterior.  Se marca como libre para que la tabla siga
            # siendo una secuencia completa desde el cero, que es lo que exige
            # el formato.
            lineas.append(b"0000000000 65535 f \n")
        else:
            lineas.append(b"%010d 00000 n \n" % posicion)
    lineas.append(b"trailer\n<< /Size %d /Root %s >>\n" % (mayor + 1, raiz))
    lineas.append(b"startxref\n%d\n%%%%EOF\n" % inicio_indice)
    destino.write_bytes(datos + b"".join(lineas))
    return True


def _localizar_objetos(datos: bytes) -> dict:
    """Anota en qué byte empieza cada objeto de nivel superior.

    Cuando el mismo número aparece varias veces —que es lo que pasa en un
    archivo con versiones incrementales— vale **la última**, que es la versión
    vigente del objeto.  Quedarse con la primera resucitaría contenido que el
    autor había sustituido.
    """
    posiciones: dict[int, int] = {}
    for coincidencia in _OBJETO.finditer(datos):
        try:
            numero = int(coincidencia.group(1))
        except ValueError:
            continue
        if numero <= 0 or numero > 10_000_000:
            continue
        # El desplazamiento tiene que apuntar al número, no al salto de línea
        # que lo precede, o el lector no encontrará el objeto donde se le dice.
        posiciones[numero] = coincidencia.start(1)
    return posiciones


def _referencia_a_raiz(datos: bytes, objetos: dict) -> bytes | None:
    """Averigua qué objeto es el catálogo del documento.

    Primero se busca en los ``trailer`` que ya trae el archivo, de atrás hacia
    delante, porque el último es el vigente.  Si no hay ninguno utilizable
    —cosa normal en los PDF modernos, que guardan el índice como un flujo— se
    busca el objeto que se declara catálogo y se fabrica la referencia.
    """
    for coincidencia in reversed(list(_TRAILER.finditer(datos))):
        trozo = datos[coincidencia.end():coincidencia.end() + 2048]
        raiz = re.search(rb"/Root\s+(\d{1,10})\s+(\d{1,5})\s*R", trozo)
        if raiz and int(raiz.group(1)) in objetos:
            return b"%s %s R" % (raiz.group(1), raiz.group(2))
    for numero, posicion in sorted(objetos.items(), key=lambda par: -par[1]):
        if _CATALOGO.search(datos[posicion:posicion + 4096]):
            return b"%d 0 R" % numero
    return None


# ---------------------------------------------------------------------------
# Comprobación
# ---------------------------------------------------------------------------

def _mejor_que(copia: Path, original: Path) -> bool:
    """Comprueba que la copia se abre y que no ha perdido páginas.

    Las dos condiciones importan.  Que abra, porque una copia ilegible no
    sirve de nada.  Y que tenga **al menos** tantas páginas como el original,
    porque una reconstrucción incompleta puede producir un archivo
    perfectamente válido con la mitad del libro dentro, y eso es un desastre
    silencioso: el usuario leería medio documento creyendo que es entero.
    """
    paginas_copia = _paginas(copia)
    if paginas_copia <= 0:
        return False
    paginas_original = _paginas(original)
    if paginas_original <= 0:
        # El original no se dejaba abrir ni para contar: cualquier copia
        # legible es una mejora.
        return True
    return paginas_copia >= paginas_original


def _paginas(ruta: Path) -> int:
    """Cuenta las páginas con PDFium, o devuelve ``0`` si no se puede abrir."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return 0
    try:
        documento = pdfium.PdfDocument(str(ruta))
    except Exception:
        return 0
    try:
        return len(documento)
    except Exception:
        return 0
    finally:
        try:
            documento.close()
        except Exception:
            pass


def _borrar(ruta: Path) -> None:
    """Borra un archivo temporal sin protestar si ya no está."""
    try:
        ruta.unlink()
    except OSError:
        pass
