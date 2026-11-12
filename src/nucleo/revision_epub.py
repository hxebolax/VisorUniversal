# -*- coding: utf-8 -*-
"""Revisar el EPUB que acabamos de escribir, antes de dárselo a nadie.

Había un informe de accesibilidad para lo que **leemos** —cuarenta y una
comprobaciones sobre los PDF— y no había ninguno para lo que **escribimos**.
Es una asimetría incómoda: el programa exporta EPUB accesibles a partir de PDF
sin etiquetar, y hasta ahora nadie comprobaba que lo exportado cumpliera lo que
dice cumplir.

Este módulo abre el EPUB recién escrito y lo mira por dentro con las mismas
reglas que se le exigen a cualquier otro: el envoltorio, los metadatos, la
navegación y el contenido.  Después dice qué ha encontrado, con la misma clase
de hallazgos que el informe de los PDF, de modo que se lea igual y se entienda
igual.

Qué se comprueba
----------------

**El envoltorio** (norma EPUB 3): que el ``mimetype`` sea el primer archivo y
vaya sin comprimir, que exista el ``container.xml`` y que apunte a un paquete
que esté de verdad dentro.  Un EPUB que falle aquí no lo abre ningún lector, y
es el fallo más fácil de cometer escribiendo el ZIP a mano.

**Los metadatos** (EPUB Accessibility 1.1, que es lo que pide la ley europea de
accesibilidad desde junio de 2025): título, autor, idioma, identificador, el
modo de acceso, el resumen de accesibilidad y la declaración de conformidad.
Sin ellos, el libro se puede leer pero **no se puede encontrar**: una librería o
una biblioteca no sabrá decir que es accesible.

**La navegación**: que haya un documento de navegación marcado como tal, que su
índice tenga entradas y que esas entradas lleven a sitios que existan dentro del
libro.  Un índice cuyas entradas apunten todas al principio es peor que no tener
índice, porque parece que funciona.

**El contenido**: que los encabezados no salten niveles, que las imágenes lleven
texto alternativo y que las tablas tengan encabezados de columna.

Qué no es esto
--------------

No es una certificación.  Es la misma honestidad que en el informe de los PDF:
se citan las cláusulas para poder ir al texto original, y lo que se dice es «he
mirado esto y he encontrado aquello», no «este libro cumple la norma».
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from formatos.pdf_hallazgos import (ColeccionHallazgos, Severidad, aviso, error,
                                    grave, informativo)

from .idioma import _
from .registro import obtener_registro

log = obtener_registro(__name__)

#: Espacio de nombres del paquete OPF.
OPF = "http://www.idpf.org/2007/opf"

#: Rasgos de accesibilidad que un libro de texto debería declarar.  No se
#: exigen todos: se avisa de los que faltan y que el libro sí tiene.
RASGOS_ESPERADOS = ("readingOrder", "structuralNavigation", "tableOfContents")

#: Cuántos enlaces del índice se comprueban.  Con más, revisar un libro de mil
#: capítulos tardaría más que escribirlo, y con veinte ya se ve si el
#: mecanismo funciona o no funciona.
ANCLAS_COMPROBADAS = 200


def revisar(ruta) -> ColeccionHallazgos:
    """Mira por dentro un EPUB y devuelve lo que encuentra."""
    hallazgos = ColeccionHallazgos()
    destino = Path(ruta)
    try:
        with zipfile.ZipFile(destino) as archivo:
            _revisar_envoltorio(hallazgos, archivo)
            paquete = _ruta_del_paquete(hallazgos, archivo)
            if paquete is None:
                return hallazgos
            _revisar_paquete(hallazgos, archivo, paquete)
    except zipfile.BadZipFile:
        hallazgos.anadir(grave("EPUB_NO_ES_ZIP",
                               _("El archivo no es un EPUB válido: no es un ZIP.")))
    except OSError as fallo:
        hallazgos.anadir(grave("EPUB_NO_SE_LEE",
                               _("No se ha podido leer el EPUB: %s") % fallo))
    return hallazgos


# ---------------------------------------------------------------------------
# El envoltorio
# ---------------------------------------------------------------------------

def _revisar_envoltorio(hallazgos: ColeccionHallazgos, archivo: zipfile.ZipFile) -> None:
    """Comprueba lo que exige la norma del propio ZIP."""
    nombres = archivo.namelist()
    if not nombres or nombres[0] != "mimetype":
        hallazgos.anadir(error(
            "EPUB_MIMETYPE_NO_ES_PRIMERO",
            _("El archivo «mimetype» no es el primero del EPUB."),
            remedio=_("Algunos lectores no reconocerán el libro."),
            norma="EPUB 3.3, 4.2"))
    else:
        info = archivo.getinfo("mimetype")
        if info.compress_type != zipfile.ZIP_STORED:
            hallazgos.anadir(error(
                "EPUB_MIMETYPE_COMPRIMIDO",
                _("El archivo «mimetype» va comprimido, y tiene que ir sin comprimir."),
                norma="EPUB 3.3, 4.2"))
        contenido = archivo.read("mimetype").decode("ascii", "replace").strip()
        if contenido != "application/epub+zip":
            hallazgos.anadir(error(
                "EPUB_MIMETYPE_MAL",
                _("El «mimetype» dice «%s» y debería decir «application/epub+zip».")
                % contenido[:60], norma="EPUB 3.3, 4.2"))
    if "META-INF/container.xml" not in nombres:
        hallazgos.anadir(grave(
            "EPUB_SIN_CONTENEDOR",
            _("Falta «META-INF/container.xml», sin el cual ningún lector sabe por "
              "dónde empezar."), norma="EPUB 3.3, 4.1"))


def _ruta_del_paquete(hallazgos: ColeccionHallazgos,
                      archivo: zipfile.ZipFile) -> str | None:
    """Devuelve dónde está el OPF, según el contenedor."""
    try:
        datos = archivo.read("META-INF/container.xml")
    except KeyError:
        return None
    encontrado = re.search(rb'full-path="([^"]+)"', datos)
    if not encontrado:
        hallazgos.anadir(grave(
            "EPUB_CONTENEDOR_SIN_RUTA",
            _("El contenedor no dice dónde está el paquete del libro."),
            norma="EPUB 3.3, 4.1"))
        return None
    ruta = encontrado.group(1).decode("utf-8", "replace")
    if ruta not in archivo.namelist():
        hallazgos.anadir(grave(
            "EPUB_PAQUETE_QUE_NO_ESTA",
            _("El contenedor apunta a «%s», que no está dentro del EPUB.") % ruta,
            norma="EPUB 3.3, 4.1"))
        return None
    return ruta


# ---------------------------------------------------------------------------
# El paquete: metadatos, navegación y contenido
# ---------------------------------------------------------------------------

def _revisar_paquete(hallazgos: ColeccionHallazgos, archivo: zipfile.ZipFile,
                     paquete: str) -> None:
    """Revisa los metadatos, el índice y los documentos de contenido."""
    texto = archivo.read(paquete).decode("utf-8", "replace")
    _revisar_metadatos(hallazgos, texto)
    _revisar_accesibilidad(hallazgos, texto)

    base = paquete.rsplit("/", 1)[0] if "/" in paquete else ""
    recursos = dict(re.findall(r'id="([^"]+)"[^>]*href="([^"]+)"', texto))
    navegacion = _archivo_de_navegacion(texto, recursos)
    if navegacion is None:
        hallazgos.anadir(error(
            "EPUB_SIN_NAVEGACION",
            _("El libro no trae documento de navegación, así que no tendrá índice."),
            remedio=_("Sin él no se puede saltar de capítulo en capítulo."),
            norma="EPUB 3.3, 6.3"))
    else:
        _revisar_navegacion(hallazgos, archivo, _junto_a(base, navegacion), base)

    _revisar_contenido(hallazgos, archivo, texto, recursos, base)


def _junto_a(base: str, relativa: str) -> str:
    """Resuelve una ruta relativa dentro del ZIP."""
    if not base:
        return relativa
    return "%s/%s" % (base, relativa)


def _revisar_metadatos(hallazgos: ColeccionHallazgos, texto: str) -> None:
    """Comprueba los datos mínimos que identifican el libro."""
    for etiqueta, codigo, mensaje in (
            ("dc:title", "EPUB_SIN_TITULO", _("El libro no declara título.")),
            ("dc:language", "EPUB_SIN_IDIOMA", _("El libro no declara idioma.")),
            ("dc:identifier", "EPUB_SIN_IDENTIFICADOR",
             _("El libro no declara identificador.")),
    ):
        if "<%s" % etiqueta not in texto:
            hallazgos.anadir(error(codigo, mensaje, norma="EPUB 3.3, 5.4"))
    if "<dc:creator" not in texto:
        hallazgos.anadir(aviso(
            "EPUB_SIN_AUTOR", _("El libro no declara autor."),
            remedio=_("Se puede corregir en el propio documento antes de exportarlo."),
            norma="EPUB 3.3, 5.4"))


def _revisar_accesibilidad(hallazgos: ColeccionHallazgos, texto: str) -> None:
    """Comprueba lo que pide la norma de accesibilidad de EPUB."""
    if "schema:accessMode" not in texto:
        hallazgos.anadir(error(
            "EPUB_SIN_MODO_DE_ACCESO",
            _("El libro no declara su modo de acceso."),
            remedio=_("Sin esto, una librería no puede decir si el libro es accesible."),
            norma="EPUB Accessibility 1.1, 2.2"))
    if "accessModeSufficient" not in texto:
        hallazgos.anadir(aviso(
            "EPUB_SIN_MODO_SUFICIENTE",
            _("El libro no declara con qué basta para leerlo entero."),
            remedio=_("Es el dato que busca quien no ve: «con el texto basta»."),
            norma="EPUB Accessibility 1.1, 2.3"))
    if "accessibilitySummary" not in texto:
        hallazgos.anadir(aviso(
            "EPUB_SIN_RESUMEN",
            _("El libro no trae resumen de accesibilidad."),
            norma="EPUB Accessibility 1.1, 2.6"))
    if "accessibilityHazard" not in texto:
        hallazgos.anadir(aviso(
            "EPUB_SIN_PELIGROS",
            _("El libro no dice si tiene destellos o sonidos que puedan dañar."),
            norma="EPUB Accessibility 1.1, 2.5"))
    if "dcterms:conformsTo" not in texto:
        hallazgos.anadir(aviso(
            "EPUB_SIN_CONFORMIDAD",
            _("El libro no declara a qué norma de accesibilidad se ajusta."),
            norma="EPUB Accessibility 1.1, 3"))
    faltan = [rasgo for rasgo in RASGOS_ESPERADOS if rasgo not in texto]
    if faltan:
        hallazgos.anadir(informativo(
            "EPUB_RASGOS_NO_DECLARADOS",
            _("El libro no declara estos rasgos de accesibilidad: %s.")
            % ", ".join(faltan),
            cantidad=len(faltan), norma="EPUB Accessibility 1.1, 2.4"))


def _archivo_de_navegacion(texto: str, recursos: dict) -> str | None:
    """Encuentra el documento marcado con ``properties="nav"``."""
    encontrado = re.search(
        r'<item\b[^>]*properties="[^"]*\bnav\b[^"]*"[^>]*>', texto)
    if not encontrado:
        return None
    destino = re.search(r'href="([^"]+)"', encontrado.group(0))
    return destino.group(1) if destino else None


def _revisar_navegacion(hallazgos: ColeccionHallazgos, archivo: zipfile.ZipFile,
                        ruta: str, base: str) -> None:
    """Comprueba que el índice tiene entradas y que llevan a algún sitio."""
    try:
        texto = archivo.read(ruta).decode("utf-8", "replace")
    except KeyError:
        hallazgos.anadir(error(
            "EPUB_NAVEGACION_QUE_NO_ESTA",
            _("El documento de navegación «%s» no está dentro del EPUB.") % ruta,
            norma="EPUB 3.3, 6.3"))
        return
    if 'epub:type="toc"' not in texto:
        hallazgos.anadir(error(
            "EPUB_SIN_INDICE",
            _("El documento de navegación no contiene ningún índice."),
            norma="EPUB 3.3, 6.3"))
    enlaces = re.findall(r'<a\b[^>]*href="([^"]+)"', texto)
    if not enlaces:
        hallazgos.anadir(error(
            "EPUB_INDICE_VACIO", _("El índice del libro no tiene ninguna entrada."),
            norma="EPUB 3.3, 6.3"))
        return

    rotos = 0
    sin_ancla = 0
    nombres = set(archivo.namelist())
    contenidos: dict[str, str] = {}
    for enlace in enlaces[:ANCLAS_COMPROBADAS]:
        destino, _sep, ancla = enlace.partition("#")
        completo = _junto_a(base, destino) if destino else ruta
        if completo not in nombres:
            rotos += 1
            continue
        if not ancla:
            sin_ancla += 1
            continue
        if completo not in contenidos:
            contenidos[completo] = archivo.read(completo).decode("utf-8", "replace")
        if ('id="%s"' % ancla) not in contenidos[completo]:
            rotos += 1
    if rotos:
        hallazgos.anadir(error(
            "EPUB_INDICE_ROTO",
            _("%d entradas del índice llevan a un sitio que no existe.") % rotos,
            cantidad=rotos,
            remedio=_("Al pulsarlas no pasará nada, o se irá al principio del libro."),
            norma="EPUB 3.3, 6.3"))
    if sin_ancla > 1:
        # Una sola entrada sin ancla es el propio libro; varias significan que
        # todas llevan al principio, que es el fallo clásico.
        hallazgos.anadir(aviso(
            "EPUB_INDICE_SIN_ANCLAS",
            _("%d entradas del índice llevan al principio del archivo y no a su "
              "capítulo.") % sin_ancla, cantidad=sin_ancla,
            norma="EPUB 3.3, 6.3"))
    hallazgos.anadir(informativo(
        "EPUB_INDICE", _("El índice tiene %d entradas.") % len(enlaces),
        cantidad=len(enlaces)))


#: Un encabezado con su nivel.
_ENCABEZADO = re.compile(r"<h([1-6])\b", re.IGNORECASE)

#: Una imagen con todos sus atributos.
_IMAGEN = re.compile(r"<img\b[^>]*>", re.IGNORECASE)

#: Una tabla entera, para mirarle dentro.
_TABLA = re.compile(r"<table\b.*?</table>", re.IGNORECASE | re.DOTALL)


def _revisar_contenido(hallazgos: ColeccionHallazgos, archivo: zipfile.ZipFile,
                       paquete: str, recursos: dict, base: str) -> None:
    """Revisa los documentos de contenido: encabezados, imágenes y tablas."""
    nombres = set(archivo.namelist())
    documentos = [_junto_a(base, href) for href in recursos.values()
                  if href.lower().endswith((".xhtml", ".html", ".htm"))]
    sin_alternativa = 0
    tablas_sin_encabezado = 0
    saltos = 0
    anterior = 0
    encabezados = 0

    for ruta in documentos:
        if ruta not in nombres:
            hallazgos.anadir(error(
                "EPUB_RECURSO_QUE_NO_ESTA",
                _("El paquete declara «%s», que no está dentro del EPUB.") % ruta,
                norma="EPUB 3.3, 5.5"))
            continue
        texto = archivo.read(ruta).decode("utf-8", "replace")
        for nivel in _ENCABEZADO.findall(texto):
            encabezados += 1
            numero = int(nivel)
            if anterior and numero > anterior + 1:
                saltos += 1
            anterior = numero
        for etiqueta in _IMAGEN.findall(texto):
            alternativa = re.search(r'alt="([^"]*)"', etiqueta)
            if alternativa is None or not alternativa.group(1).strip():
                sin_alternativa += 1
        for tabla in _TABLA.findall(texto):
            if "<th" not in tabla.lower():
                tablas_sin_encabezado += 1

    if not encabezados:
        hallazgos.anadir(aviso(
            "EPUB_SIN_ENCABEZADOS",
            _("El libro no tiene ningún encabezado, así que no se podrá recorrer "
              "con la tecla H."),
            norma="EPUB Accessibility 1.1, 4.2"))
    if saltos:
        hallazgos.anadir(aviso(
            "EPUB_NIVELES_SALTADOS",
            _("%d encabezados se saltan un nivel (de h1 a h3, por ejemplo).") % saltos,
            cantidad=saltos,
            remedio=_("Al recorrer el libro parecerá que falta un apartado."),
            norma="WCAG 2.2, 1.3.1"))
    if sin_alternativa:
        hallazgos.anadir(aviso(
            "EPUB_IMAGENES_SIN_ALTERNATIVA",
            _("%d imágenes del libro no llevan texto alternativo.") % sin_alternativa,
            cantidad=sin_alternativa,
            remedio=_("Descríbelas con Control+Alt+D antes de exportar y saldrán con "
                      "su descripción."),
            norma="WCAG 2.2, 1.1.1"))
    if tablas_sin_encabezado:
        hallazgos.anadir(aviso(
            "EPUB_TABLAS_SIN_ENCABEZADO",
            _("%d tablas no marcan su fila de encabezados.") % tablas_sin_encabezado,
            cantidad=tablas_sin_encabezado,
            remedio=_("Al recorrerlas no se anunciará de qué columna es cada celda."),
            norma="WCAG 2.2, 1.3.1"))


# ---------------------------------------------------------------------------
# Cómo se cuenta
# ---------------------------------------------------------------------------

def redactar(hallazgos: ColeccionHallazgos, maximo: int = 8) -> str:
    """Escribe el resultado de la revisión para decírselo al usuario."""
    if not hallazgos:
        return _("El libro exportado ha pasado todas las comprobaciones.")
    peor = hallazgos.peor()
    if peor <= Severidad.INFORMACION:
        return _("El libro exportado está bien. %s") % hallazgos.redactar(
            maximo=2, minima=Severidad.INFORMACION)
    cabecera = (_("El libro exportado tiene problemas graves:") if peor >= Severidad.ERROR
                else _("El libro exportado está bien, con estas observaciones:"))
    return "%s\n%s" % (cabecera, hallazgos.redactar(maximo=maximo))
