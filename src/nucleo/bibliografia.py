# -*- coding: utf-8 -*-
"""La bibliografía entera de los libros que se han usado, en un archivo.

Citar un pasaje ya se podía (:mod:`nucleo.citas`). Lo que faltaba era el último
paso de un trabajo: **la lista de referencias del final**, con todos los libros
consultados, en el estilo elegido y ordenada alfabéticamente. Hasta ahora había
que montarla a mano, libro por libro, y es lo que más se equivoca justo cuando
uno ya no tiene tiempo de repasarlo.

Se sacan seis formatos, y no es por hacer bulto: sirven para tres cosas
distintas.

- **Texto, Markdown y HTML** son la lista tal cual, para pegarla al final del
  trabajo.
- **BibTeX y RIS** no se leen: se **importan**. Son lo que entienden Zotero,
  Mendeley, EndNote y LaTeX, y con ellos las referencias entran en el gestor
  con sus campos separados, no como un párrafo de texto que después hay que
  volver a trocear. Para quien escribe una tesis, esto es la diferencia entre
  media hora y un minuto.
- **CSV** entra en una hoja de cálculo, que es como mucha gente lleva la
  lista de lecturas de una asignatura.

**Qué libros entran.** Los que se le pasen: la ventana de la biblioteca deja
marcar unos cuantos, y si no hay ninguno marcado se entienden todos los que se
estén viendo, que suele ser lo que se busca después de haber filtrado.

**De dónde salen los datos.** De la biblioteca, sin abrir nada: desde la
1.3.5 guarda de cada libro de calibre o de cada EPUB importado su editorial, su
fecha y su ISBN, además del título y el autor. Hasta la 1.3.5 se abría y se
analizaba cada libro entero para sacarlos, y con una biblioteca de calibre de
doscientos mil libros eso eran horas con la ventana colgada; ahora es un par de
segundos. Solo los libros sueltos incompletos se miran por dentro —de un EPUB,
sus metadatos y nada más—, y abrir los libros enteros queda como opción para
quien la pida (ver :func:`reunir`). Lo que no se encuentre se deja en blanco y
**se dice cuál falta**: una bibliografía con un año inventado es peor que una
con un hueco.
"""

from __future__ import annotations

import csv
import html as _html
import io
import os
import re
import unicodedata
from pathlib import Path

from . import citas
from .idioma import _
from .registro import obtener_registro

log = obtener_registro(__name__)

#: Formatos en los que se puede sacar la bibliografía.
FORMATOS = ("txt", "md", "html", "bibtex", "ris", "csv")


def _sin_tildes(texto: str) -> str:
    """Un texto sin acentos, para ordenar como se ordena en un diccionario.

    Sin esto, «Álvarez» iría detrás de «Zamora», porque la letra con tilde vale
    más que cualquier letra sin ella en el orden de los caracteres.
    """
    plano = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in plano if not unicodedata.combining(c))


def nombres() -> dict[str, tuple[str, str, str]]:
    """Rótulo, extensión y filtro de archivo de cada formato.

    Se construye al llamarla y no como constante porque los rótulos van
    traducidos y la traducción se instala después de importar el módulo.
    """
    return {
        "txt": (_("Texto plano (.txt)"), ".txt",
                _("Archivos de texto (*.txt)|*.txt")),
        "md": (_("Markdown (.md)"), ".md",
               _("Archivos Markdown (*.md)|*.md")),
        "html": (_("Página web (.html)"), ".html",
                 _("Páginas web (*.html)|*.html")),
        "bibtex": (_("BibTeX, para Zotero o LaTeX (.bib)"), ".bib",
                   _("Archivos BibTeX (*.bib)|*.bib")),
        "ris": (_("RIS, para Mendeley o EndNote (.ris)"), ".ris",
                _("Archivos RIS (*.ris)|*.ris")),
        "csv": (_("Hoja de cálculo (.csv)"), ".csv",
                _("Archivos CSV (*.csv)|*.csv")),
    }


def desde_libro(libro, documento=None) -> citas.Referencia:
    """Monta la referencia de un libro de la biblioteca.

    Primero va lo que la biblioteca ya sabe sin abrir nada: el título y el
    autor y, si el libro viene de calibre o de un EPUB importado, también la
    editorial, la fecha de publicación y el ISBN.  Con el documento delante, lo
    que falte se completa con lo que traiga el archivo; lo que ya había no se
    toca, porque lo que el usuario ve en la biblioteca —y lo que ha cuidado en
    calibre— manda sobre lo que diga el archivo.
    """
    datos = citas.Referencia(
        titulo=libro.titulo, autor=libro.autor,
        editorial=getattr(libro, "editorial", "") or "",
        fecha=getattr(libro, "publicado", "") or "",
        identificador=getattr(libro, "isbn", "") or "",
        autor_orden=getattr(libro, "autores_orden", "") or "",
        ruta=libro.ruta)
    if documento is not None:
        del_archivo = citas.desde_documento(documento, 0)
        for campo in ("titulo", "autor", "editorial", "fecha", "identificador"):
            if not getattr(datos, campo):
                setattr(datos, campo, getattr(del_archivo, campo))
    return datos


def incompleta(datos: citas.Referencia) -> bool:
    """Si a una referencia de la lista final le falta algún dato.

    La página no cuenta: en la lista de referencias se cita el libro entero.
    """
    return not (datos.autor and datos.titulo and datos.editorial and datos.ano)


#: Cada cuántos libros se avisa del avance al montar las referencias.
_CADA = 2000


def reunir(libros, opciones=None, progreso=None, cancelado=None,
           abrir: bool = False) -> list[citas.Referencia]:
    """Saca la referencia de cada libro, en tres pasos de más rápido a más lento.

    1. **Lo que ya sabe la biblioteca.**  Con una biblioteca de calibre eso es
       casi todo: título, autores, editorial, fecha e ISBN.  No se abre nada y
       ciento noventa mil libros salen en un par de segundos.
    2. **Los libros sueltos** (abiertos alguna vez, pero que no salen de ninguna
       carpeta ni biblioteca de calibre) a los que les falte algo: de un EPUB se
       leen solo sus metadatos, que son unos kilobytes; de los demás, lo que
       haya en la caché si ya se analizaron.
    3. **Solo si se pide** (``abrir``): los que sigan incompletos se abren y se
       analizan enteros.  Es lo único lento de verdad —horas con una biblioteca
       entera—, y por eso no se hace sin que el usuario lo diga.

    :param progreso: Se llama con ``(hecho, total, detalle)``.
    :param cancelado: Se consulta a menudo; si devuelve verdadero, se para y se
                      devuelve lo que haya.
    :return: Una referencia por libro, en el mismo orden.
    """
    total = len(libros)

    def avisar(hecho, cuantos, texto):
        if progreso is not None:
            progreso(hecho, cuantos, texto)

    salida: list[citas.Referencia] = []
    for numero, libro in enumerate(libros):
        if numero % _CADA == 0:
            if cancelado is not None and cancelado():
                return salida
            avisar(numero, total, _("Preparando las referencias: %(hecho)d de %(total)d")
                   % {"hecho": numero, "total": total})
        salida.append(desde_libro(libro))

    sueltos = [i for i, datos in enumerate(salida)
               if incompleta(datos) and not getattr(libros[i], "fuente", 0)]
    for paso, indice in enumerate(sueltos):
        if cancelado is not None and cancelado():
            return salida
        avisar(paso, len(sueltos), _("Completando los libros sueltos: %(hecho)d de "
                                     "%(total)d") % {"hecho": paso, "total": len(sueltos)})
        salida[indice] = _completar_rapido(libros[indice], salida[indice], opciones)

    if abrir and opciones is not None:
        from nucleo import cache
        from .biblioteca import _abrir

        pendientes = [i for i, datos in enumerate(salida) if incompleta(datos)]
        for paso, indice in enumerate(pendientes):
            if cancelado is not None and cancelado():
                return salida
            libro = libros[indice]
            avisar(paso, len(pendientes),
                   _("Abriendo los libros a los que les faltan datos: %(hecho)d de "
                     "%(total)d. %(titulo)s")
                   % {"hecho": paso, "total": len(pendientes), "titulo": libro.titulo})
            if not os.path.exists(libro.ruta):
                continue
            try:
                documento = _abrir(libro, opciones, cache, solo_cacheados=False)
            except Exception as error:               # pragma: no cover
                log.info("No se han podido leer los datos de %s: %s", libro.ruta, error)
                continue
            if documento is not None:
                salida[indice] = desde_libro(libro, documento)
    avisar(total, total, _("Bibliografía preparada."))
    return salida


def _completar_rapido(libro, datos: citas.Referencia, opciones) -> citas.Referencia:
    """Completa una referencia sin analizar el libro entero."""
    if libro.ruta.lower().endswith((".epub", ".kepub")):
        from .biblioteca_importar import metadatos_epub

        leidos = metadatos_epub(libro.ruta) or {}
        if not datos.titulo:
            datos.titulo = leidos.get("titulo", "")
        if not datos.autor:
            datos.autor = leidos.get("autor", "")
            datos.autor_orden = leidos.get("autores_orden", "")
        if not datos.editorial:
            datos.editorial = leidos.get("editorial", "")
        if not datos.fecha:
            datos.fecha = leidos.get("publicado", "")
        if not datos.identificador:
            datos.identificador = leidos.get("isbn", "")
        return datos
    if opciones is None:
        return datos
    from nucleo import cache

    try:
        documento = cache.cargar(libro.ruta, opciones.firma())
    except Exception:                                # pragma: no cover
        documento = None
    return desde_libro(libro, documento) if documento is not None else datos


def ordenar(referencias) -> list[citas.Referencia]:
    """Alfabéticamente por autor, y a igualdad de autor por título.

    Se ordena por **el apellido**, no por el nombre de pila, porque es como se
    alfabetiza una bibliografía y como se busca en ella. Lo que no tiene autor
    va al final: en una lista ordenada por autores, las obras anónimas no
    tienen dónde meterse por delante sin desordenar el resto.
    """
    def clave(datos):
        apellido = _sin_tildes(datos.apellido_primero()).lower()
        return (0 if apellido else 1, apellido,
                _sin_tildes(datos.titulo).lower())

    return sorted(referencias, key=clave)


def lo_que_falta(referencias) -> list[tuple[str, list[str]]]:
    """Qué datos le faltan a cada referencia, para poder avisar antes.

    Devuelve solo las que tienen algo incompleto: ``[(título, [qué falta])]``.
    Es lo que evita entregar una bibliografía con seis años en blanco sin
    haberse enterado.
    """
    avisos = []
    pagina = _("la página")
    for datos in referencias:
        # La página **no** se echa en falta aquí. En una cita concreta hace
        # falta porque señala de dónde salen las palabras citadas; en la lista
        # de referencias del final se cita el libro entero, y ahí una página
        # suelta no significaría nada.
        faltan = [q for q in citas.lo_que_falta(datos) if q != pagina]
        if faltan:
            avisos.append((datos.titulo or _("(sin título)"), faltan))
    return avisos


# ---------------------------------------------------------------------------
# Los formatos que se leen
# ---------------------------------------------------------------------------

def a_txt(referencias, estilo: str = "iso690", titulo: str = "") -> bytes:
    """La lista tal cual, una referencia por párrafo."""
    lineas = [titulo or _("Bibliografía"), ""]
    for datos in referencias:
        lineas.append(citas.referencia(datos, estilo))
        lineas.append("")
    return "\n".join(lineas).encode("utf-8")


def a_markdown(referencias, estilo: str = "iso690", titulo: str = "") -> bytes:
    """Markdown con la lista como viñetas, listo para pegar en un trabajo."""
    partes = ["# %s" % (titulo or _("Bibliografía")), ""]
    for datos in referencias:
        partes.append("- %s" % citas.referencia(datos, estilo))
    partes.append("")
    return "\n".join(partes).encode("utf-8")


def a_html(referencias, estilo: str = "iso690", titulo: str = "",
           idioma: str = "es") -> bytes:
    """Página web con la lista.

    Va en una lista de verdad (``<ul>``) y no en párrafos sueltos: así un
    lector de pantalla anuncia cuántas referencias hay antes de empezar a
    leerlas, que es lo primero que uno quiere saber.
    """
    rotulo = _html.escape(titulo or _("Bibliografía"))
    filas = "\n".join("<li>%s</li>" % _html.escape(citas.referencia(datos, estilo))
                      for datos in referencias)
    return ("<!DOCTYPE html>\n"
            '<html lang="%s"><head><meta charset="utf-8">\n'
            "<title>%s</title>\n"
            "<style>body{font-family:sans-serif;max-width:42em;margin:2em auto;"
            "line-height:1.6;padding:0 1em}"
            "li{margin-bottom:.8em}</style>\n"
            "</head><body>\n<h1>%s</h1>\n<ul>\n%s\n</ul>\n</body></html>\n"
            % (idioma or "es", rotulo, rotulo, filas)).encode("utf-8")


# ---------------------------------------------------------------------------
# Los formatos que se importan
# ---------------------------------------------------------------------------

#: Caracteres que no pueden ir en una clave de BibTeX.
_NO_EN_CLAVE = re.compile(r"[^A-Za-z0-9]+")


def clave_bibtex(datos: citas.Referencia, usadas=None) -> str:
    """La etiqueta con la que se cita en LaTeX: ``\\cite{cervantes1605quijote}``.

    Se monta con el apellido, el año y la primera palabra larga del título, que
    es la costumbre y lo que la hace reconocible al leerla. Si dos salen
    iguales se les añade una letra, porque **una clave repetida hace que el
    gestor se quede con una sola de las dos referencias** y la otra desaparece
    sin decir nada.
    """
    apellido = _sin_tildes(datos.apellido_primero().split(",")[0])
    apellido = _NO_EN_CLAVE.sub("", apellido).lower()[:20]
    palabras = [p for p in _sin_tildes(datos.titulo).split() if len(p) > 3]
    palabra = _NO_EN_CLAVE.sub("", palabras[0]).lower()[:15] if palabras else ""
    base = "".join(p for p in (apellido, datos.ano, palabra) if p) or "referencia"
    if usadas is None:
        return base
    clave = base
    letra = ord("a")
    while clave in usadas:
        clave = "%s%s" % (base, chr(letra))
        letra += 1
    usadas.add(clave)
    return clave


def _escapar_bibtex(texto: str) -> str:
    """Protege los caracteres que en BibTeX significan otra cosa."""
    for viejo, nuevo in (("\\", "\\textbackslash "), ("{", "\\{"), ("}", "\\}"),
                         ("&", "\\&"), ("%", "\\%"), ("$", "\\$"),
                         ("#", "\\#"), ("_", "\\_")):
        texto = texto.replace(viejo, nuevo)
    return texto


def a_bibtex(referencias, titulo: str = "") -> bytes:
    """BibTeX, que es lo que importan Zotero, JabRef y LaTeX.

    Cada libro es una entrada ``@book`` con sus campos separados. El campo
    ``file`` guarda dónde está el archivo en este equipo: al importar, el gestor
    enlaza la referencia con el libro y se abre desde ahí.
    """
    del titulo
    usadas: set[str] = set()
    trozos = []
    for datos in referencias:
        campos = []
        if datos.autor:
            # BibTeX separa los autores con «and»; con punto y coma los
            # tomaría por uno solo con un nombre muy largo.
            campos.append(("author", " and ".join(datos.autores_invertidos())))
        if datos.titulo:
            campos.append(("title", datos.titulo))
        if datos.editorial:
            campos.append(("publisher", datos.editorial))
        if datos.ano:
            campos.append(("year", datos.ano))
        if datos.identificador:
            # Un ISBN de verdad se declara como tal; lo que no lo es --el
            # identificador interno de un EPUB-- iría a parar a un campo que
            # el gestor enseña como si fuera un ISBN, y no lo es.
            clave = "isbn" if _parece_isbn(datos.identificador) else "note"
            campos.append((clave, datos.identificador))
        if datos.ruta:
            campos.append(("file", datos.ruta))
        cuerpo = ",\n".join("  %s = {%s}" % (nombre, _escapar_bibtex(valor))
                            for nombre, valor in campos)
        trozos.append("@book{%s,\n%s\n}\n" % (clave_bibtex(datos, usadas), cuerpo))
    return "\n".join(trozos).encode("utf-8")


#: Un ISBN son diez o trece cifras, con guiones o sin ellos y quizá con una X
#: final de control.
_ISBN = re.compile(r"^(?:isbn[: ]*)?[0-9][0-9\- ]{8,16}[0-9Xx]$", re.IGNORECASE)


def _parece_isbn(texto: str) -> bool:
    """Dice si un identificador es un ISBN y no un número interno del archivo."""
    limpio = (texto or "").strip()
    if not _ISBN.match(limpio):
        return False
    cifras = re.sub(r"[^0-9Xx]", "", limpio)
    return len(cifras) in (10, 13)


def a_ris(referencias, titulo: str = "") -> bytes:
    """RIS, que es lo que importan Mendeley, EndNote y RefWorks.

    Es un formato de líneas ``ETIQUETA  - valor``, con **dos espacios exactos**
    antes del guion. No es un capricho de estilo: los lectores de RIS miran las
    columnas fijas, y con un espacio de más la línea se ignora en silencio.
    """
    del titulo
    lineas = []
    for datos in referencias:
        lineas.append("TY  - BOOK")
        # RIS lleva una línea por autor: es lo que hace que el gestor los
        # reconozca por separado.
        for autor in datos.autores_invertidos():
            lineas.append("AU  - %s" % autor)
        if datos.titulo:
            lineas.append("TI  - %s" % datos.titulo)
        if datos.editorial:
            lineas.append("PB  - %s" % datos.editorial)
        if datos.ano:
            lineas.append("PY  - %s" % datos.ano)
        if datos.identificador and _parece_isbn(datos.identificador):
            lineas.append("SN  - %s" % datos.identificador)
        if datos.ruta:
            lineas.append("L1  - %s" % datos.ruta)
        lineas.append("ER  - ")
        lineas.append("")
    return "\r\n".join(lineas).encode("utf-8")


def a_csv(referencias, estilo: str = "iso690", titulo: str = "") -> bytes:
    """Hoja de cálculo con una columna por dato y la cita ya montada.

    Se escribe con **punto y coma** y con la marca de orden de bytes porque es
    lo que abre bien Excel en español haciendo doble clic; con comas y sin
    marca, se ve todo en la primera columna y con las tildes rotas, y ahí ya no
    hay quien lo arregle sin saber de importaciones.
    """
    del titulo
    memoria = io.StringIO()
    escritor = csv.writer(memoria, delimiter=";", quoting=csv.QUOTE_MINIMAL,
                          lineterminator="\r\n")
    escritor.writerow([_("Autor"), _("Título"), _("Editorial"), _("Año"),
                       _("Identificador"), _("Referencia"), _("Archivo")])
    for datos in referencias:
        escritor.writerow([datos.apellido_primero(), datos.titulo,
                           datos.editorial, datos.ano, datos.identificador,
                           citas.referencia(datos, estilo), datos.ruta])
    return b"\xef\xbb\xbf" + memoria.getvalue().encode("utf-8")


def exportar(referencias, destino, formato: str, estilo: str = "iso690",
             titulo: str = "", idioma: str = "es") -> None:
    """Escribe la bibliografía en el formato pedido.

    :raises ValueError: Si el formato no es uno de :data:`FORMATOS`.
    :raises OSError: Si no se puede escribir el archivo.
    """
    if formato not in FORMATOS:
        raise ValueError("Formato desconocido: %r" % formato)
    if formato == "md":
        datos = a_markdown(referencias, estilo, titulo)
    elif formato == "html":
        datos = a_html(referencias, estilo, titulo, idioma)
    elif formato == "bibtex":
        datos = a_bibtex(referencias, titulo)
    elif formato == "ris":
        datos = a_ris(referencias, titulo)
    elif formato == "csv":
        datos = a_csv(referencias, estilo, titulo)
    else:
        datos = a_txt(referencias, estilo, titulo)
    ruta = Path(destino)
    ruta.write_bytes(datos)
    log.info("Exportadas %d referencias a %s (%s)",
             len(referencias), ruta.name, formato)
