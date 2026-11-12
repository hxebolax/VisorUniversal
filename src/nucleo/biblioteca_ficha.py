# -*- coding: utf-8 -*-
"""La ficha de un libro: qué datos lleva, en qué orden, y cómo se exporta.

La ficha junta lo que se sabe de un libro —lo que trae calibre o el propio
EPUB y lo que sabe el programa— en un texto de un dato por línea.  Aquí está
**qué** datos hay y **cómo** se escriben; la ventana que la enseña está en
``interfaz/dialogos/biblioteca.py``.

Cada cual elige sus datos
-------------------------

No todo el mundo quiere lo mismo de una ficha.  Para decidir qué leer basta con
el título, la serie, el autor y la sinopsis; para un trabajo hacen falta
también la editorial, la fecha y el ISBN.  Por eso los datos de la ficha se
eligen y se ordenan, y el orden de fábrica pone primero **lo que le interesa a
quien lee** y después lo técnico.

Se guardan dos elecciones aparte, porque sirven para cosas distintas: la de la
ficha que se ve (``biblioteca_ficha_campos``) y la de las fichas que se
exportan a un archivo (``biblioteca_exportar_campos``).  Así se puede tener una
ficha corta para consultar y una exportación completa para trabajar.

Lo que se guarda es la lista de los datos **visibles**, en su orden.  Los que no
están en la lista no salen.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Callable, Iterable, Optional

from . import biblioteca_datos as datos
from .idioma import _

#: Ajuste donde se guarda la elección de la ficha que se ve.
AJUSTE_FICHA = "biblioteca_ficha_campos"

#: Ajuste donde se guarda la elección de las fichas que se exportan.
AJUSTE_EXPORTAR = "biblioteca_exportar_campos"

#: Todos los datos que puede llevar una ficha, en el orden de fábrica: primero
#: lo que se mira para decidir si leer un libro, después lo técnico.
CAMPOS = (
    ("titulo", _("Título")),
    ("serie", _("Serie")),
    ("autor", _("Autores")),
    ("sinopsis", _("Sinopsis")),
    ("coleccion", _("Colección")),
    ("etiquetas", _("Etiquetas")),
    ("editorial", _("Editorial")),
    ("publicado", _("Fecha de publicación")),
    ("idioma", _("Idioma")),
    ("valoracion", _("Valoración")),
    ("identificadores", _("ISBN y demás identificadores")),
    ("extra", _("Columnas propias de calibre")),
    ("formato", _("Formato")),
    ("tamano", _("Tamaño")),
    ("anadido", _("Añadido")),
    ("lectura", _("Lectura")),
    ("biblioteca", _("Biblioteca")),
    ("portada", _("Portada")),
    ("archivo", _("Archivo")),
)

#: Las claves válidas, para descartar lo que no sirva de lo guardado.
_CLAVES = tuple(clave for clave, _nombre in CAMPOS)


def nombre_de(clave: str) -> str:
    """El nombre que se enseña de un dato."""
    return dict(CAMPOS).get(clave, clave)


def campos_elegidos(guardado) -> list[str]:
    """Los datos que se quieren ver, en su orden.

    :param guardado: Lo que haya en el ajuste.  Si no es una lista o se queda
                     vacía tras quitar lo que no vale, se devuelven todos en
                     el orden de fábrica: una ficha vacía no le sirve a nadie.
    """
    if isinstance(guardado, (list, tuple)):
        vistos: list[str] = []
        for clave in guardado:
            if clave in _CLAVES and clave not in vistos:
                vistos.append(clave)
        if vistos:
            return vistos
    return list(_CLAVES)


def orden_completo(visibles: Iterable[str]) -> list[tuple[str, bool]]:
    """Todos los datos con si se ven o no, para la ventana que los elige.

    Primero los visibles, en su orden; después los demás, en el de fábrica.
    """
    visibles = [c for c in visibles if c in _CLAVES]
    salida = [(clave, True) for clave in visibles]
    salida.extend((clave, False) for clave in _CLAVES if clave not in visibles)
    return salida


# -- los valores de cada dato -------------------------------------------------

def leer_ficha(conexion, libro) -> dict:
    """Lo que hay guardado de un libro en la base de datos, o un diccionario vacío."""
    try:
        return datos.ficha(conexion, libro.ruta) or {}
    except Exception:
        return {}


def valores(libro, ficha: dict, clave: str) -> list[tuple[str, str]]:
    """Las líneas ``(rótulo, valor)`` de un dato.

    Casi todos dan una línea o ninguna; los identificadores y las columnas
    propias de calibre pueden dar varias, una por cada uno.  Los que no tienen
    valor no dan ninguna: una ficha no lleva líneas vacías.
    """
    from . import biblioteca

    def una(rotulo: str, valor) -> list[tuple[str, str]]:
        texto = ("%s" % (valor or "")).strip()
        return [(rotulo, texto)] if texto and texto != "0" else []

    if clave == "titulo":
        return una(_("Título"), ficha.get("titulo") or libro.titulo)
    if clave == "serie":
        return una(_("Serie"), libro.serie_legible())
    if clave == "autor":
        return una(_("Autores"), ficha.get("autor") or libro.autor)
    if clave == "sinopsis":
        return una(_("Sinopsis"), ficha.get("comentarios"))
    if clave == "coleccion":
        return una(_("Colección"), libro.coleccion)
    if clave == "etiquetas":
        return una(_("Etiquetas"), ficha.get("etiquetas") or libro.etiquetas)
    if clave == "editorial":
        return una(_("Editorial"), ficha.get("editorial") or libro.editorial)
    if clave == "publicado":
        return una(_("Fecha de publicación"),
                   biblioteca._fecha_corta(ficha.get("publicado") or libro.publicado or ""))
    if clave == "idioma":
        return una(_("Idioma"), ficha.get("idioma") or libro.idioma)
    if clave == "valoracion":
        valoracion = ficha.get("valoracion") or libro.valoracion
        if not valoracion:
            return []
        from .biblioteca_importar import _estrellas

        return una(_("Valoración"), _estrellas(valoracion))
    if clave == "identificadores":
        lineas = una(_("ISBN"), ficha.get("isbn") or libro.isbn)
        for tipo, valor in (ficha.get("identificadores") or {}).items():
            if tipo != "isbn":
                lineas += una(_("Identificador %s") % tipo, valor)
        return lineas
    if clave == "extra":
        lineas = []
        for nombre, valor in (ficha.get("extra") or {}).items():
            lineas += una(nombre, valor)
        return lineas
    if clave == "formato":
        lineas = una(_("Formato"), libro.formato)
        if ficha.get("formatos") and ficha.get("formatos") != libro.formato:
            lineas += una(_("Formatos en la biblioteca"), ficha.get("formatos"))
        return lineas
    if clave == "tamano":
        if not libro.tamano:
            libro.existe    # mira el disco una vez, que es lo que rellena el tamaño
        return una(_("Tamaño"), libro.tamano_legible())
    if clave == "anadido":
        return una(_("Añadido"), biblioteca._fecha_corta(ficha.get("anadido") or
                                                          libro.anadido or ""))
    if clave == "lectura":
        return una(_("Lectura"), libro.estado())
    if clave == "biblioteca":
        if ficha.get("nombre_fuente"):
            tipo = (_("biblioteca de calibre") if ficha.get("tipo_fuente") == datos.CALIBRE
                    else _("carpeta"))
            return una(_("Biblioteca"), "%s (%s)" % (ficha["nombre_fuente"], tipo))
        return una(_("Biblioteca"), _("libro abierto suelto"))
    if clave == "portada":
        return una(_("Portada"), _("sí") if ficha.get("portada") else "")
    if clave == "archivo":
        return una(_("Archivo"), libro.ruta)
    return []


def componer(libro, ficha: dict, campos: Iterable[str]) -> str:
    """Escribe la ficha de un libro con los datos elegidos, en su orden.

    Un dato por línea, «Rótulo: valor».  La sinopsis va aparte, con su rótulo
    en una línea y el texto debajo, separada por líneas en blanco: es un
    párrafo largo y pegado a los demás datos costaría ver dónde acaba.
    """
    lineas: list[str] = []
    for clave in campos:
        for rotulo, valor in valores(libro, ficha, clave):
            if clave == "sinopsis":
                if lineas and lineas[-1] != "":
                    lineas.append("")
                lineas.append("%s:" % rotulo)
                lineas.append(valor)
                lineas.append("")
            else:
                lineas.append("%s: %s" % (rotulo, valor))
    while lineas and lineas[-1] == "":
        lineas.pop()
    return "\n".join(lineas)


def valor_en_una_celda(libro, ficha: dict, clave: str) -> str:
    """Un dato en una sola cadena, para una columna de hoja de cálculo.

    Los que dan varias líneas (identificadores, columnas propias) se juntan
    con punto y coma, cada uno con su rótulo para que no se confundan.
    """
    lineas = valores(libro, ficha, clave)
    if not lineas:
        return ""
    if len(lineas) == 1 and clave not in ("identificadores", "extra"):
        return lineas[0][1]
    return "; ".join("%s: %s" % (rotulo, valor) for rotulo, valor in lineas)


# -- exportar varias fichas -----------------------------------------------------

#: Formatos en que se pueden exportar las fichas.
TEXTO = "txt"
CSV = "csv"

#: Lo que separa una ficha de la siguiente en el texto.
SEPARADOR = "-" * 40


def formato_por_nombre(ruta: str, indice_filtro: int = 0) -> str:
    """Decide el formato de exportación por la extensión escrita o el filtro.

    Manda la extensión si se ha escrito («fichas.csv» es CSV aunque el filtro
    elegido fuera el de texto); sin extensión conocida, manda el filtro del
    diálogo de guardar (0, texto; 1, CSV).
    """
    nombre = (ruta or "").lower()
    if nombre.endswith(".csv"):
        return CSV
    if nombre.endswith(".txt"):
        return TEXTO
    return CSV if indice_filtro == 1 else TEXTO


def exportar(libros, campos: Iterable[str], destino, formato: str = TEXTO,
             progreso: Optional[Callable[[int, int, str], None]] = None,
             cancelado: Optional[Callable[[], bool]] = None,
             conexion=None) -> int:
    """Guarda en un archivo las fichas de varios libros.

    :param formato: :data:`TEXTO` (una ficha detrás de otra, como se ven) o
                    :data:`CSV` (una fila por libro y una columna por dato,
                    para abrirla con una hoja de cálculo).
    :param conexion: Conexión a la base de datos; sin ella se abre una.
    :return: Cuántas fichas se han escrito.  Si se cancela, se escribe lo que
             haya dado tiempo.
    """
    campos = [c for c in campos if c in _CLAVES] or list(_CLAVES)
    libros = list(libros)
    propia = conexion is None
    if propia:
        conexion = datos.conectar()
    escritas = 0
    try:
        if formato == CSV:
            salida = io.StringIO()
            # Punto y coma y no coma: es lo que espera Excel en español al
            # abrir un CSV con doble clic, y con comas lo metería todo en una
            # sola columna.
            escritor = csv.writer(salida, delimiter=";", quoting=csv.QUOTE_MINIMAL,
                                  lineterminator="\r\n")
            escritor.writerow([nombre_de(c) for c in campos])
        else:
            partes: list[str] = []
        total = len(libros)
        for numero, libro in enumerate(libros):
            if cancelado is not None and cancelado():
                break
            ficha = leer_ficha(conexion, libro)
            if formato == CSV:
                escritor.writerow([valor_en_una_celda(libro, ficha, c) for c in campos])
            else:
                partes.append(componer(libro, ficha, campos))
            escritas += 1
            if progreso is not None:
                progreso(numero + 1, total, _("Exportando las fichas: %(hechas)d de %(total)d")
                         % {"hechas": numero + 1, "total": total})
    finally:
        if propia:
            conexion.close()

    if formato == CSV:
        texto = salida.getvalue()
        # Con la marca BOM: sin ella, Excel lee el UTF-8 como si fuera ANSI y
        # estropea todas las tildes.
        Path(destino).write_text(texto, encoding="utf-8-sig", newline="")
    else:
        texto = ("\n\n%s\n\n" % SEPARADOR).join(partes)
        Path(destino).write_text(texto + "\n", encoding="utf-8")
    return escritas
