# -*- coding: utf-8 -*-
"""Meter libros en la biblioteca: de una carpeta o de una biblioteca de calibre.

Todo lo de aquí se hace **en un hilo aparte** y avisando de por dónde va.  Con
ciento noventa mil libros nada de esto cabe en el hilo de la ventana: la
interfaz se quedaría colgada y el lector de pantalla callado, que es lo peor
que puede pasar a quien no ve la pantalla, porque no sabe si el programa
trabaja o se ha muerto.

Dos maneras de traer libros
---------------------------

**Una carpeta corriente.**  Se recorre entera, sin tope, con ``os.scandir``,
que en Windows trae el tamaño y la fecha de cada archivo en la misma llamada
que lo lista y no obliga a preguntar al disco por cada uno.  De los EPUB se
leen sus propios metadatos —título, autores, serie, fecha, idioma, editorial,
materias, identificadores y sinopsis—, que van dentro del archivo.  Al
actualizar solo se vuelven a leer los que han cambiado de tamaño o de fecha.

**Una biblioteca de calibre.**  Se reconoce por su ``metadata.db`` y no se
recorre el disco: calibre ya sabe qué libros tiene, dónde está cada formato y
todos sus datos, y los guarda en una base de datos SQLite que aquí se lee
**sin escribir nada en ella** (se abre en solo lectura y, si calibre la tiene
bloqueada, se lee una copia).  Se traen todos los campos: título, autores con
su orden, serie y número, etiquetas, editorial, fecha de publicación, fecha en
que se añadió, idiomas, valoración, identificadores (ISBN y los demás),
sinopsis, formatos, si tiene portada y **las columnas propias** que el usuario
haya creado en calibre.

El esquema que se lee es el de ``resources/metadata_sqlite.sql`` de calibre:
``books`` con sus tablas de enlace (``books_authors_link``,
``books_series_link``…), ``data`` para los formatos —el archivo de cada uno es
``<biblioteca>/<books.path>/<data.name>.<formato>``— y ``custom_columns`` con
sus ``custom_column_N`` y ``books_custom_column_N_link``.

Al terminar se devuelve un :class:`Resumen` con lo hecho: cuántos libros son
nuevos, cuántos se han puesto al día, cuántos seguían igual y cuántos ya no
estaban.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import sqlite3
import threading
import time
import unicodedata
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import biblioteca_datos as datos
from .idioma import _, _n
from .registro import obtener_registro

log = obtener_registro(__name__)

#: Cuántos libros se escriben en la base de datos de una vez.
TANDA = 2000

#: Cada cuánto, como poco, se avisa del avance (segundos).  Avisar en cada
#: libro saturaría la cola de la ventana con ciento noventa mil mensajes.
INTERVALO_AVANCE = 0.25

#: Cuántos EPUB se leen a la vez.  Leer un EPUB es sobre todo esperar al disco,
#: así que unos pocos a la vez aprovechan el tiempo sin ahogar un disco de los
#: de girar.
HILOS_LECTURA = 4

#: Carpetas que no se recorren nunca: son del sistema o de la papelera.
CARPETAS_IGNORADAS = {"$recycle.bin", "system volume information", ".caltrash",
                      ".calnotes", "$windows.~bt", "$windows.~ws"}

#: Orden de preferencia de formatos por omisión cuando un libro de calibre
#: tiene varios: primero los que mejor se leen con el programa.
FORMATOS_PREFERIDOS = "EPUB, KEPUB, AZW3, KFX, MOBI, AZW, FB2, DOCX, ODT, RTF, HTMLZ, HTML, PDF, DJVU, TXT"

#: Fecha que calibre usa como «sin fecha» (el año 101).
_SIN_FECHA = 101


class OpcionesImportacion:
    """Cómo se traen los libros.  Sale de la configuración del usuario."""

    def __init__(self, formatos_preferidos: str = FORMATOS_PREFERIDOS,
                 un_libro_por_formato: bool = False, leer_metadatos: bool = True,
                 calibre_anidadas: bool = True, sinopsis: bool = True,
                 admitidas=None) -> None:
        if admitidas is None:
            from formatos import base

            admitidas = base.extensiones_admitidas()
        #: Extensiones que el programa sabe abrir, con su punto.
        self.admitidas = {e.lower() for e in admitidas}
        orden = [p.strip().lower().lstrip(".") for p in
                 re.split(r"[,;\s]+", formatos_preferidos or "") if p.strip()]
        #: Formatos por orden de preferencia, sin punto y en minúsculas.
        self.preferidos = orden
        self.un_libro_por_formato = bool(un_libro_por_formato)
        self.leer_metadatos = bool(leer_metadatos)
        self.calibre_anidadas = bool(calibre_anidadas)
        self.sinopsis = bool(sinopsis)

    @classmethod
    def desde_configuracion(cls, configuracion) -> "OpcionesImportacion":
        """Las opciones tal como las tenga puestas el usuario."""
        return cls(
            formatos_preferidos=str(configuracion.obtener(
                "biblioteca_formatos_preferidos", FORMATOS_PREFERIDOS) or FORMATOS_PREFERIDOS),
            un_libro_por_formato=bool(configuracion.obtener(
                "biblioteca_un_libro_por_formato", False)),
            leer_metadatos=bool(configuracion.obtener("biblioteca_leer_metadatos", True)),
            calibre_anidadas=bool(configuracion.obtener("biblioteca_calibre_anidadas", True)),
            sinopsis=bool(configuracion.obtener("biblioteca_importar_sinopsis", True)),
        )

    def puesto(self, formato: str) -> int:
        """Lugar de un formato en el orden de preferencia (menos es mejor)."""
        formato = formato.lower()
        try:
            return self.preferidos.index(formato)
        except ValueError:
            return len(self.preferidos)


class Resumen:
    """Lo que ha hecho una importación, para contárselo al usuario."""

    def __init__(self, nombre: str, tipo: str, ruta: str = "") -> None:
        self.nombre = nombre
        self.tipo = tipo
        self.ruta = ruta
        self.nuevos = 0
        self.actualizados = 0
        self.iguales = 0
        self.quitados = 0
        self.sin_formato = 0
        self.ilegibles = 0
        self.excluidos = 0
        self.archivos = 0
        self.total = 0
        self.detenido = False
        self.error = ""
        self.segundos = 0.0
        #: Bibliotecas de calibre encontradas dentro de una carpeta.
        self.calibres: list[str] = []

    def texto(self) -> str:
        """Las líneas del resumen, listas para leer."""
        if self.tipo == datos.CALIBRE:
            cabecera = _("Biblioteca de calibre «%s»") % self.nombre
        else:
            cabecera = _("Carpeta «%s»") % self.nombre
        lineas = [cabecera]
        if self.error:
            lineas.append(_("No se ha podido completar: %s") % self.error)
        if self.detenido:
            lineas.append(_("Se ha detenido antes de terminar. Lo hecho hasta ahí se "
                            "queda guardado; al actualizar se sigue."))
        lineas.append(_("Libros en la biblioteca: %d") % self.total)
        lineas.append(_("Nuevos: %d") % self.nuevos)
        lineas.append(_("Puestos al día: %d") % self.actualizados)
        lineas.append(_("Sin cambios: %d") % self.iguales)
        if self.quitados:
            lineas.append(_("Quitados porque ya no están: %d") % self.quitados)
        if self.sin_formato:
            lineas.append(_("Sin ningún formato que el programa sepa abrir: %d")
                          % self.sin_formato)
        if self.ilegibles:
            lineas.append(_("Con metadatos ilegibles (se usa el nombre del archivo): %d")
                          % self.ilegibles)
        if self.excluidos:
            lineas.append(_("Quitados por ti antes, que no se vuelven a poner: %d")
                          % self.excluidos)
        if self.calibres:
            lineas.append(_n("Dentro había %d biblioteca de calibre, importada aparte "
                             "con sus metadatos.",
                             "Dentro había %d bibliotecas de calibre, importadas "
                             "aparte con sus metadatos.",
                             len(self.calibres)) % len(self.calibres))
        lineas.append(_("Tiempo: %s") % duracion_legible(self.segundos))
        return "\n".join(lineas)


def duracion_legible(segundos: float) -> str:
    """Una duración escrita como se dice: «2 minutos y 5 segundos»."""
    segundos = int(round(segundos))
    if segundos < 60:
        return _n("%d segundo", "%d segundos", segundos) % segundos
    minutos, resto = divmod(segundos, 60)
    if minutos < 60:
        if not resto:
            return _n("%d minuto", "%d minutos", minutos) % minutos
        return (_n("%d minuto", "%d minutos", minutos) % minutos + _(" y ")
                + _n("%d segundo", "%d segundos", resto) % resto)
    horas, minutos = divmod(minutos, 60)
    return (_n("%d hora", "%d horas", horas) % horas + _(" y ")
            + _n("%d minuto", "%d minutos", minutos) % minutos)


class Detenido(Exception):
    """Se ha pedido parar."""


class _Avance:
    """Reparte los avisos de avance sin saturar la ventana y mira si hay que parar."""

    def __init__(self, progreso, cancelado) -> None:
        self._progreso = progreso
        self._cancelado = cancelado
        self._ultimo = 0.0

    def __call__(self, hecho: int, total: int, detalle: str, forzar: bool = False) -> None:
        if self._cancelado is not None and self._cancelado():
            raise Detenido()
        if self._progreso is None:
            return
        ahora = time.monotonic()
        if forzar or ahora - self._ultimo >= INTERVALO_AVANCE:
            self._ultimo = ahora
            self._progreso(hecho, total, detalle)


# -- utilidades ----------------------------------------------------------------


def sin_tildes(texto: str) -> str:
    """Minúsculas y sin acentos, para buscar y ordenar sin sorpresas."""
    plano = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in plano if not unicodedata.combining(c)).casefold().strip()


_SALTO = re.compile(r"<\s*br\b[^>]*>", re.IGNORECASE)
_ETIQUETA_BLOQUE = re.compile(r"<\s*/(?:p|div|li|h[1-6]|tr|blockquote)\s*>", re.IGNORECASE)
_ETIQUETA = re.compile(r"<[^>]+>")
_ESPACIOS = re.compile(r"[ \t\r\f\v]+")
_LINEAS = re.compile(r"\n\s*\n+")


def html_a_texto(contenido: str) -> str:
    """Convierte la sinopsis de calibre (HTML) en texto que se lee bien.

    No se usa un analizador de HTML a propósito: son ciento setenta mil
    sinopsis y con una expresión regular se convierten en segundos.  Lo único
    que importa conservar son los saltos de párrafo.
    """
    if not contenido:
        return ""
    if "<" not in contenido:
        return html.unescape(contenido).strip()
    texto = _SALTO.sub("\n", contenido)
    texto = _ETIQUETA_BLOQUE.sub("\n\n", texto)
    texto = _ETIQUETA.sub("", texto)
    texto = html.unescape(texto)
    texto = _ESPACIOS.sub(" ", texto)
    texto = "\n".join(linea.strip() for linea in texto.split("\n"))
    return _LINEAS.sub("\n\n", texto).strip()


def _fecha(valor) -> str:
    """Fecha de calibre (``2007-10-25 22:00:00+00:00``) como ``AAAA-MM-DD``."""
    texto = str(valor or "")[:10]
    if len(texto) < 4 or not texto[:4].isdigit() or int(texto[:4]) <= _SIN_FECHA:
        return ""
    return texto


def _nombre_idioma(codigo: str) -> str:
    """Nombre de un idioma a partir de su código ISO 639 de tres o dos letras."""
    from . import tesseract

    codigo = (codigo or "").strip().lower()
    equivalentes = {"zho": "chi_sim", "chi": "chi_sim", "arb": "ara", "ger": "deu",
                    "fre": "fra", "dut": "nld", "cze": "ces", "gre": "ell",
                    "baq": "eus", "rum": "ron", "slo": "slk", "es": "spa",
                    "en": "eng", "ca": "cat", "fr": "fra", "de": "deu", "it": "ita",
                    "pt": "por", "gl": "glg", "eu": "eus", "ru": "rus", "nl": "nld"}
    clave = equivalentes.get(codigo, codigo)
    clave = equivalentes.get(clave.split("-")[0], clave.split("-")[0])
    return tesseract.IDIOMAS.get(clave, codigo)


def _firma(valores: dict) -> str:
    """Huella de los datos de un libro, para saber si han cambiado."""
    partes = [str(valores.get(campo, "")) for campo in datos.CAMPOS
              if campo not in ("firma", "fuente")]
    return hashlib.blake2b("\x1f".join(partes).encode("utf-8", "replace"),
                           digest_size=10).hexdigest()


def _completar(valores: dict) -> dict:
    """Rellena lo que se deduce de lo demás: el orden, la búsqueda y la firma."""
    for campo in datos.CAMPOS:
        valores.setdefault(campo, "" if campo not in ("serie_indice", "valoracion",
                                                      "tamano", "fecha", "calibre_id")
                           else 0)
    if not valores["titulo"]:
        valores["titulo"] = Path(valores["ruta"]).stem
    valores["orden_titulo"] = sin_tildes(valores["titulo"])
    valores["orden_autor"] = sin_tildes(valores.get("orden_autor") or valores["autor"])
    valores["busqueda"] = sin_tildes(" ".join((
        valores["titulo"], valores["autor"], valores["serie"], valores["etiquetas"],
        valores["editorial"], Path(valores["ruta"]).name)))
    valores["firma"] = _firma(valores)
    return valores


class _Escritor:
    """Escribe los libros de una fuente a tandas y lleva la cuenta.

    Sabe qué había antes de esa fuente, así que distingue lo nuevo de lo que
    solo hay que poner al día y de lo que sigue igual, y al terminar puede
    quitar lo que ya no estaba.
    """

    def __init__(self, conexion, fuente_id: int, resumen: Resumen) -> None:
        self.conexion = conexion
        self.fuente = fuente_id
        self.resumen = resumen
        self.excluidos = datos.excluidas(conexion)
        self.antes: dict[str, tuple] = {
            fila[0]: (fila[1], fila[2], fila[3], fila[4]) for fila in conexion.execute(
                "SELECT clave, id, firma, tamano, fecha FROM libros WHERE fuente=?",
                (fuente_id,))}
        self.vistos: set[str] = set()
        self._insertar: list[tuple] = []
        self._actualizar: list[tuple] = []

    def sin_cambios(self, ruta: str, tamano: int, fecha: float) -> bool:
        """Si el archivo es el mismo de la vez anterior; entonces no se relee."""
        clave = datos.clave(ruta)
        antes = self.antes.get(clave)
        if antes is None or clave in self.excluidos:
            return False
        if int(antes[2] or 0) == int(tamano) and abs(float(antes[3] or 0) - fecha) < 2:
            self.vistos.add(clave)
            self.resumen.iguales += 1
            return True
        return False

    def poner(self, valores: dict) -> None:
        """Apunta un libro; se escribe al llenarse la tanda."""
        clave = valores["clave"]
        if clave in self.excluidos:
            self.resumen.excluidos += 1
            return
        if clave in self.vistos:
            return
        self.vistos.add(clave)
        valores["fuente"] = self.fuente
        _completar(valores)
        fila = tuple(valores[campo] for campo in datos.CAMPOS)
        antes = self.antes.get(clave)
        if antes is None:
            self._insertar.append(fila)
            self.resumen.nuevos += 1
        elif antes[1] != valores["firma"]:
            self._actualizar.append(fila + (antes[0],))
            self.resumen.actualizados += 1
        else:
            self.resumen.iguales += 1
        if len(self._insertar) + len(self._actualizar) >= TANDA:
            self.vaciar()

    def vaciar(self) -> None:
        """Escribe lo pendiente en una sola transacción."""
        if not (self._insertar or self._actualizar):
            return
        columnas = ", ".join(datos.CAMPOS)
        marcas = ", ".join("?" * len(datos.CAMPOS))
        asignar = ", ".join("%s=excluded.%s" % (c, c) for c in datos.CAMPOS if c != "clave")
        with self.conexion:
            if self._insertar:
                # Si el mismo archivo estaba ya en otra fuente, pasa a esta: es
                # la que se acaba de importar y la que mejor lo describe.
                self.conexion.executemany(
                    "INSERT INTO libros(%s) VALUES(%s) ON CONFLICT(clave) DO UPDATE SET %s"
                    % (columnas, marcas, asignar), self._insertar)
            if self._actualizar:
                self.conexion.executemany(
                    "UPDATE libros SET %s WHERE id=?"
                    % ", ".join("%s=?" % c for c in datos.CAMPOS), self._actualizar)
        self._insertar.clear()
        self._actualizar.clear()

    def terminar(self, completo: bool) -> None:
        """Escribe lo último y, si se ha llegado al final, quita lo que no estaba.

        Solo se quita si el recorrido ha sido completo: si se ha parado a
        medias, lo que no se ha visto no es que no exista, es que no se ha
        llegado.
        """
        self.vaciar()
        if completo:
            sobran = [(antes[0],) for clave, antes in self.antes.items()
                      if clave not in self.vistos]
            if sobran:
                with self.conexion:
                    self.conexion.executemany("DELETE FROM libros WHERE id=?", sobran)
                self.resumen.quitados += len(sobran)
        self.resumen.total = datos.recontar(self.conexion, self.fuente)


# -- calibre -------------------------------------------------------------------


def es_biblioteca_calibre(carpeta) -> bool:
    """Si en esa carpeta hay una biblioteca de calibre."""
    try:
        return os.path.isfile(os.path.join(str(carpeta), "metadata.db"))
    except OSError:                                          # pragma: no cover
        return False


def nombre_de_calibre(carpeta) -> str:
    """El nombre con el que se conoce una biblioteca de calibre: su carpeta."""
    return Path(str(carpeta)).name or str(carpeta)


def _comparar_sin_mayusculas(uno: str, otro: str) -> int:
    """La colación ``PYNOCASE`` de calibre, para poder leer sus índices."""
    a, b = (uno or "").casefold(), (otro or "").casefold()
    return (a > b) - (a < b)


def _preparar_conexion_calibre(conexion: sqlite3.Connection) -> None:
    """Registra lo que calibre añade a SQLite y que su base de datos nombra.

    Sus tablas e índices usan la colación ``PYNOCASE`` y sus disparadores
    llaman a funciones propias como ``title_sort``.  Sin registrarlas, SQLite
    rechaza cualquier consulta que pase por un índice con esa colación.  Como
    aquí no se escribe nada, a las funciones les basta con existir.
    """
    conexion.create_collation("PYNOCASE", _comparar_sin_mayusculas)
    conexion.create_collation("icucollate", _comparar_sin_mayusculas)
    conexion.create_function("title_sort", 1, lambda x: x)
    conexion.create_function("author_to_author_sort", 1, lambda x: x)
    conexion.create_function("uuid4", 0, lambda: "")
    conexion.create_function("books_list_filter", 1, lambda x: 1)


def abrir_calibre(carpeta) -> tuple[sqlite3.Connection, Path | None]:
    """Abre el ``metadata.db`` de una biblioteca de calibre sin poder escribir.

    Primero se abre tal cual, en solo lectura.  Si no se puede —calibre lo
    tiene bloqueado en mitad de una escritura, o está en un medio raro— se
    copia a la carpeta temporal y se lee la copia.

    :return: La conexión y, si se ha hecho una copia, dónde está para borrarla.
    """
    archivo = Path(str(carpeta)) / "metadata.db"
    try:
        conexion = sqlite3.connect(archivo.as_uri() + "?mode=ro", uri=True, timeout=10)
        _preparar_conexion_calibre(conexion)
        conexion.execute("SELECT COUNT(*) FROM books").fetchone()
        return conexion, None
    except sqlite3.Error as error:
        log.info("No se puede leer %s en su sitio (%s); se lee una copia", archivo, error)
    from . import rutas

    copia = rutas.ruta_temp() / ("calibre_%d_%d.db" % (os.getpid(), threading.get_ident()))
    shutil.copyfile(archivo, copia)
    conexion = sqlite3.connect(copia.as_uri() + "?mode=ro", uri=True)
    _preparar_conexion_calibre(conexion)
    conexion.execute("SELECT COUNT(*) FROM books").fetchone()
    return conexion, copia


def _consulta(conexion, sql: str, argumentos=()) -> list:
    """Hace una consulta y devuelve vacío si la tabla no existe.

    Las bibliotecas de calibre muy antiguas no tienen todas las tablas de las
    de ahora; lo que falte simplemente no se trae.
    """
    try:
        return conexion.execute(sql, argumentos).fetchall()
    except sqlite3.OperationalError as error:
        log.debug("Consulta de calibre sin resultado (%s): %s", error, sql[:80])
        return []


def _agrupar(filas) -> dict:
    """``[(libro, valor), ...]`` a ``{libro: [valor, ...]}``, conservando el orden."""
    grupos: dict = {}
    for fila in filas:
        grupos.setdefault(fila[0], []).append(fila[1] if len(fila) == 2 else fila[1:])
    return grupos


class _ColumnaPropia:
    """Una columna que el usuario ha creado en calibre (``custom_columns``)."""

    def __init__(self, fila) -> None:
        self.numero = int(fila[0])
        self.etiqueta = str(fila[1])
        self.nombre = str(fila[2] or fila[1])
        self.tipo = str(fila[3])
        self.multiple = bool(fila[4])
        self.normalizada = bool(fila[5])
        try:
            self.vista = json.loads(fila[6] or "{}")
        except ValueError:
            self.vista = {}

    def consulta(self) -> str:
        """La consulta que trae sus valores para una tanda de libros."""
        n = self.numero
        if self.normalizada:
            extra = ", l.extra" if self.tipo == "series" else ""
            return ("SELECT l.book, v.value%s FROM books_custom_column_%d_link l "
                    "JOIN custom_column_%d v ON v.id=l.value "
                    "WHERE l.book BETWEEN ? AND ? ORDER BY l.id" % (extra, n, n))
        return ("SELECT book, value FROM custom_column_%d WHERE book BETWEEN ? AND ?" % n)

    def texto(self, valores) -> str:
        """El valor de la columna para un libro, escrito como se lee."""
        if self.tipo == "series":
            partes = []
            for valor in valores:
                if isinstance(valor, tuple):
                    nombre, numero = valor[0], valor[1]
                    partes.append("%s [%s]" % (nombre, _numero(numero)) if numero is not None
                                  else str(nombre))
                else:
                    partes.append(str(valor))
            return ", ".join(partes)
        salida = []
        for valor in valores:
            if isinstance(valor, tuple):
                valor = valor[0]
            if valor is None or valor == "":
                continue
            if self.tipo == "bool":
                salida.append(_("Sí") if valor else _("No"))
            elif self.tipo == "datetime":
                salida.append(_fecha(valor))
            elif self.tipo == "rating":
                salida.append(_estrellas(valor))
            elif self.tipo == "comments":
                salida.append(html_a_texto(str(valor)))
            elif self.tipo in ("int", "float"):
                salida.append(_numero(valor))
            else:
                salida.append(str(valor))
        separador = " & " if self.vista.get("is_names") else ", "
        return separador.join(s for s in salida if s)


def _numero(valor) -> str:
    """Un número sin decimales de sobra: 3.0 es «3» y 2.5 es «2,5»."""
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return str(valor)
    if numero.is_integer():
        return str(int(numero))
    return ("%g" % numero).replace(".", ",")


def _estrellas(valor) -> str:
    """Una valoración de calibre (de 0 a 10) en estrellas."""
    try:
        numero = int(valor or 0)
    except (TypeError, ValueError):
        return ""
    if numero <= 0:
        return ""
    estrellas = numero / 2
    return _n("%s estrella", "%s estrellas", max(1, int(estrellas))) % _numero(estrellas)


def importar_calibre(conexion, fuente: datos.Fuente, opciones: OpcionesImportacion,
                     avance: _Avance, resumen: Resumen) -> None:
    """Trae todos los libros de una biblioteca de calibre."""
    raiz = fuente.ruta
    if not es_biblioteca_calibre(raiz):
        resumen.error = _("no se encuentra el metadata.db de calibre en %s") % raiz
        return
    try:
        avance(0, 0, _("Abriendo la base de datos de calibre..."), forzar=True)
    except Detenido:
        resumen.detenido = True
        return
    calibre, copia = abrir_calibre(raiz)
    escritor = _Escritor(conexion, fuente.id, resumen)
    completo = False
    try:
        uuid_biblioteca = ""
        filas = _consulta(calibre, "SELECT uuid FROM library_id")
        if filas:
            uuid_biblioteca = str(filas[0][0] or "")
        propias = [_ColumnaPropia(f) for f in _consulta(
            calibre, "SELECT id, label, name, datatype, is_multiple, normalized, display "
                     "FROM custom_columns WHERE mark_for_delete=0 AND datatype<>'composite'")]
        identificadores = [fila[0] for fila in
                           _consulta(calibre, "SELECT id FROM books ORDER BY id")]
        total = len(identificadores)
        avance(0, total, _("Leyendo %d libros de calibre...") % total, forzar=True)
        for inicio in range(0, total, TANDA):
            tramo = identificadores[inicio:inicio + TANDA]
            _tanda_calibre(calibre, raiz, tramo[0], tramo[-1], propias, opciones,
                           escritor, resumen)
            hecho = min(total, inicio + len(tramo))
            avance(hecho, total, _("Calibre: %(hecho)d de %(total)d libros")
                   % {"hecho": hecho, "total": total})
        completo = True
        datos.marcar_actualizada(conexion, fuente.id, uuid_biblioteca)
    except Detenido:
        resumen.detenido = True
    finally:
        try:
            escritor.terminar(completo)
        finally:
            calibre.close()
            if copia is not None:
                try:
                    copia.unlink()
                except OSError:                              # pragma: no cover
                    pass


def _tanda_calibre(calibre, raiz: str, desde: int, hasta: int, propias, opciones,
                   escritor: _Escritor, resumen: Resumen) -> None:
    """Lee y apunta los libros de calibre con número entre ``desde`` y ``hasta``."""
    rango = (desde, hasta)
    libros = _consulta(calibre,
                       "SELECT id, title, sort, timestamp, pubdate, series_index, "
                       "author_sort, path, uuid, has_cover FROM books "
                       "WHERE id BETWEEN ? AND ?", rango)
    autores = _agrupar(_consulta(
        calibre, "SELECT l.book, a.name, a.sort FROM books_authors_link l "
                 "JOIN authors a ON a.id=l.author WHERE l.book BETWEEN ? AND ? "
                 "ORDER BY l.id", rango))
    series = _agrupar(_consulta(
        calibre, "SELECT l.book, s.name FROM books_series_link l "
                 "JOIN series s ON s.id=l.series WHERE l.book BETWEEN ? AND ?", rango))
    etiquetas = _agrupar(_consulta(
        calibre, "SELECT l.book, t.name FROM books_tags_link l "
                 "JOIN tags t ON t.id=l.tag WHERE l.book BETWEEN ? AND ?", rango))
    editoriales = _agrupar(_consulta(
        calibre, "SELECT l.book, p.name FROM books_publishers_link l "
                 "JOIN publishers p ON p.id=l.publisher WHERE l.book BETWEEN ? AND ?", rango))
    valoraciones = _agrupar(_consulta(
        calibre, "SELECT l.book, r.rating FROM books_ratings_link l "
                 "JOIN ratings r ON r.id=l.rating WHERE l.book BETWEEN ? AND ?", rango))
    idiomas = _agrupar(_consulta(
        calibre, "SELECT l.book, g.lang_code FROM books_languages_link l "
                 "JOIN languages g ON g.id=l.lang_code WHERE l.book BETWEEN ? AND ? "
                 "ORDER BY l.item_order", rango))
    sinopsis = {}
    if opciones.sinopsis:
        sinopsis = dict(_consulta(calibre, "SELECT book, text FROM comments "
                                           "WHERE book BETWEEN ? AND ?", rango))
    ids_externos = _agrupar(_consulta(
        calibre, "SELECT book, type, val FROM identifiers WHERE book BETWEEN ? AND ?",
        rango))
    formatos = _agrupar(_consulta(
        calibre, "SELECT book, format, name, uncompressed_size FROM data "
                 "WHERE book BETWEEN ? AND ?", rango))
    valores_propios = [(columna, _agrupar(_consulta(calibre, columna.consulta(), rango)))
                       for columna in propias]

    for fila in libros:
        numero, titulo, _orden, anadido, publicado, indice, orden_autor, carpeta, \
            uuid, portada = fila
        disponibles = []
        for formato, nombre, tamano in formatos.get(numero, []):
            extension = "." + str(formato or "").lower()
            if extension in opciones.admitidas and nombre:
                disponibles.append((opciones.puesto(formato), str(formato).upper(),
                                    str(nombre), int(tamano or 0)))
        if not disponibles:
            resumen.sin_formato += 1
            continue
        disponibles.sort()
        elegidos = disponibles if opciones.un_libro_por_formato else disponibles[:1]

        # Cada autor con su nombre y su forma de cita («Fuentes Aguirre,
        # Armando»), que calibre ya tiene y que es mejor que cualquier
        # suposición sobre dónde empieza el apellido.
        lista_autores = [str(a[0]).replace("|", ",") for a in autores.get(numero, [])]
        formas_cita = [str(a[1] or "").replace("|", ",").strip()
                       for a in autores.get(numero, [])]
        externos = {str(t): str(v) for t, v in ids_externos.get(numero, [])}
        extra = {}
        for columna, valores in valores_propios:
            texto = columna.texto(valores.get(numero, []))
            if texto:
                extra[columna.nombre] = texto
        nombre_serie = (series.get(numero) or [""])[0]
        comunes = {
            "titulo": str(titulo or ""),
            "autor": " & ".join(lista_autores),
            "orden_autor": str(orden_autor or ""),
            "autores_orden": " & ".join(formas_cita) if all(formas_cita) else "",
            "serie": str(nombre_serie or ""),
            "serie_indice": float(indice or 0) if nombre_serie else 0,
            "etiquetas": ", ".join(sorted((str(t) for t in etiquetas.get(numero, [])),
                                          key=str.casefold)),
            "editorial": ", ".join(str(e) for e in editoriales.get(numero, [])),
            "publicado": _fecha(publicado),
            "anadido": _fecha(anadido),
            "idioma": ", ".join(_nombre_idioma(c) for c in idiomas.get(numero, [])),
            "isbn": externos.get("isbn", ""),
            "identificadores": json.dumps(externos, ensure_ascii=False) if externos else "",
            "comentarios": html_a_texto(str(sinopsis.get(numero) or "")),
            "valoracion": int((valoraciones.get(numero) or [0])[0] or 0),
            "formatos": ", ".join(d[1] for d in disponibles),
            "calibre_id": int(numero),
            "uuid": str(uuid or ""),
            "portada": (os.path.join(raiz, str(carpeta).replace("/", os.sep), "cover.jpg")
                        if portada else ""),
            "extra": json.dumps(extra, ensure_ascii=False) if extra else "",
        }
        for _puesto, formato, nombre, tamano in elegidos:
            relativa = os.path.join(str(carpeta).replace("/", os.sep),
                                    "%s.%s" % (nombre, formato.lower()))
            ruta = os.path.join(raiz, relativa)
            valores = dict(comunes)
            valores.update(clave=datos.clave(ruta), ruta=ruta, relativa=relativa,
                           formato=formato, tamano=tamano)
            escritor.poner(valores)


# -- carpetas corrientes -------------------------------------------------------


def recorrer(raiz: str, admitidas, saltar: set[str], avance: _Avance,
             calibres: list[str] | None):
    """Da los archivos de libro de una carpeta y todas sus subcarpetas.

    :param saltar: Claves de carpetas que no se recorren porque ya son otra
                   fuente de la biblioteca.
    :param calibres: Si no es ``None``, las bibliotecas de calibre que haya
                     dentro **no se recorren** y se apuntan aquí, para
                     importarlas aparte con sus metadatos.
    :return: Generador de ``(ruta, tamaño, fecha)``.
    """
    pila = [raiz]
    encontrados = 0
    carpetas = 0
    while pila:
        carpeta = pila.pop()
        carpetas += 1
        try:
            with os.scandir(carpeta) as entradas:
                lista = list(entradas)
        except OSError as error:
            log.info("No se ha podido explorar %s: %s", carpeta, error)
            continue
        if calibres is not None and carpeta != raiz and any(
                e.name.lower() == "metadata.db" for e in lista):
            calibres.append(carpeta)
            continue
        for entrada in lista:
            try:
                if entrada.is_dir(follow_symlinks=False):
                    if (entrada.name.lower() not in CARPETAS_IGNORADAS
                            and datos.clave(entrada.path) not in saltar):
                        pila.append(entrada.path)
                    continue
                extension = os.path.splitext(entrada.name)[1].lower()
                if extension not in admitidas:
                    continue
                estado = entrada.stat(follow_symlinks=False)
            except OSError:
                continue
            encontrados += 1
            yield entrada.path, int(estado.st_size), float(estado.st_mtime)
        avance(encontrados, 0, _("Explorando: %(libros)d libros en %(carpetas)d carpetas")
               % {"libros": encontrados, "carpetas": carpetas})


_LECTORES = threading.local()


def _parser():
    """Un analizador XML por hilo: los de lxml no se comparten entre hilos."""
    parser = getattr(_LECTORES, "parser", None)
    if parser is None:
        from formatos.lectura_xml import crear_parser_xml

        parser = _LECTORES.parser = crear_parser_xml()
    return parser


def _local(etiqueta) -> str:
    """El nombre de una etiqueta XML sin su espacio de nombres."""
    if not isinstance(etiqueta, str):
        return ""
    return etiqueta.rsplit("}", 1)[-1].split(":")[-1].lower()


def metadatos_epub(ruta: str) -> dict | None:
    """Lee los metadatos que trae un EPUB dentro, sin analizar el libro.

    Solo se abre el ``container.xml`` y el OPF, que son unos pocos kilobytes:
    es lo que permite leer los de miles de libros en un rato razonable.
    Se entienden los de EPUB 2 y 3 y los que añade calibre (``calibre:series``).

    :return: Diccionario con lo encontrado, o ``None`` si no se ha podido leer.
    """
    from lxml import etree

    try:
        with zipfile.ZipFile(ruta) as archivo:
            nombres = {n.lower(): n for n in archivo.namelist()}
            opf = None
            contenedor = nombres.get("meta-inf/container.xml")
            if contenedor:
                raiz = etree.fromstring(archivo.read(contenedor), _parser())
                if raiz is not None:
                    for nodo in raiz.iter():
                        if _local(nodo.tag) == "rootfile" and nodo.get("full-path"):
                            opf = nombres.get(nodo.get("full-path").lower())
                            break
            if opf is None:
                opf = next((n for clave, n in nombres.items() if clave.endswith(".opf")),
                           None)
            if opf is None:
                return None
            paquete = etree.fromstring(archivo.read(opf), _parser())
    except (OSError, zipfile.BadZipFile, ValueError, KeyError, RuntimeError,
            etree.LxmlError, EOFError) as error:
        log.debug("Metadatos ilegibles en %s: %s", ruta, error)
        return None
    if paquete is None:
        return None

    autores, materias, editoriales, idiomas = [], [], [], []
    #: La forma de cita de cada autor (``opf:file-as``), en el mismo orden.
    formas: list[str] = []
    titulo = publicado = descripcion = serie = ""
    indice = 0.0
    externos: dict[str, str] = {}
    refinos: dict[str, dict[str, str]] = {}
    colecciones: list[tuple[str, str]] = []
    for nodo in paquete.iter():
        nombre = _local(nodo.tag)
        texto = " ".join("".join(nodo.itertext()).split()) if nombre else ""
        if nombre == "title" and not titulo:
            titulo = texto
        elif nombre == "creator" and texto:
            papel = ""
            forma = ""
            for atributo, valor in nodo.attrib.items():
                if _local(atributo) == "role":
                    papel = (valor or "").lower()
                elif _local(atributo) == "file-as":
                    forma = " ".join((valor or "").split())
            if papel in ("", "aut") and texto not in autores:
                autores.append(texto)
                formas.append(forma)
        elif nombre == "subject" and texto:
            materias.append(texto)
        elif nombre == "publisher" and texto:
            editoriales.append(texto)
        elif nombre == "language" and texto:
            idiomas.append(texto)
        elif nombre == "date" and texto and not publicado:
            publicado = texto[:10]
        elif nombre == "description" and texto and not descripcion:
            descripcion = html_a_texto("".join(nodo.itertext()))
        elif nombre == "identifier" and texto:
            esquema = ""
            for atributo, valor in nodo.attrib.items():
                if _local(atributo) == "scheme":
                    esquema = (valor or "").lower()
            if texto.lower().startswith("urn:isbn:"):
                esquema, texto = "isbn", texto[9:]
            elif texto.lower().startswith("isbn:"):
                esquema, texto = "isbn", texto[5:]
            if esquema and esquema not in externos:
                externos[esquema] = texto
        elif nombre == "meta":
            propiedad = (nodo.get("property") or "").lower()
            if (nodo.get("name") or "").lower() == "calibre:series":
                serie = nodo.get("content") or serie
            elif (nodo.get("name") or "").lower() == "calibre:series_index":
                try:
                    indice = float(nodo.get("content") or 0)
                except ValueError:
                    pass
            elif propiedad == "belongs-to-collection" and texto:
                colecciones.append(((nodo.get("id") or ""), texto))
            elif propiedad in ("group-position", "collection-type") and nodo.get("refines"):
                refinos.setdefault(nodo.get("refines").lstrip("#"), {})[propiedad] = texto
    if not serie and colecciones:
        for identificador, nombre_coleccion in colecciones:
            refino = refinos.get(identificador, {})
            if refino.get("collection-type", "series") == "series":
                serie = nombre_coleccion
                try:
                    indice = float(refino.get("group-position") or 0)
                except ValueError:
                    pass
                break
    if publicado and (not publicado[:4].isdigit() or int(publicado[:4]) <= _SIN_FECHA):
        publicado = ""
    return {
        "titulo": titulo,
        "autor": " & ".join(autores),
        "autores_orden": " & ".join(formas) if formas and all(formas) else "",
        "serie": serie,
        "serie_indice": indice if serie else 0,
        "etiquetas": ", ".join(dict.fromkeys(materias)),
        "editorial": ", ".join(dict.fromkeys(editoriales)),
        "publicado": publicado,
        "idioma": ", ".join(_nombre_idioma(c) for c in dict.fromkeys(idiomas)),
        "isbn": externos.get("isbn", ""),
        "identificadores": json.dumps(externos, ensure_ascii=False) if externos else "",
        "comentarios": descripcion,
    }


def importar_carpeta(conexion, fuente: datos.Fuente, opciones: OpcionesImportacion,
                     avance: _Avance, resumen: Resumen) -> None:
    """Recorre una carpeta entera y apunta sus libros."""
    raiz = fuente.ruta
    if not os.path.isdir(raiz):
        resumen.error = _("la carpeta no está disponible: %s") % raiz
        return
    # Las otras fuentes que caigan dentro no se recorren: ya se traen solas, y
    # si son de calibre, con mejores datos que los que da el disco.
    saltar = {datos.clave(otra.ruta) for otra in datos.fuentes(conexion)
              if otra.id != fuente.id}
    calibres: list[str] | None = [] if opciones.calibre_anidadas else None
    escritor = _Escritor(conexion, fuente.id, resumen)
    completo = False
    try:
        avance(0, 0, _("Explorando la carpeta..."), forzar=True)
        archivos = list(recorrer(raiz, opciones.admitidas, saltar, avance, calibres))
        resumen.archivos = len(archivos)
        resumen.calibres = list(calibres or [])
        total = len(archivos)
        # Los que no han cambiado desde la última vez no se vuelven a leer.
        pendientes = [a for a in archivos if not escritor.sin_cambios(*a)]
        hechos = total - len(pendientes)
        avance(hechos, total, _("Leyendo los datos de %d libros...") % len(pendientes),
               forzar=True)

        def leer(archivo):
            ruta, tamano, fecha = archivo
            leidos = None
            if opciones.leer_metadatos and ruta.lower().endswith((".epub", ".kepub")):
                leidos = metadatos_epub(ruta)
                if leidos is None:
                    leidos = {"_ilegible": True}
            return ruta, tamano, fecha, leidos

        with ThreadPoolExecutor(max_workers=HILOS_LECTURA) as hilos:
            for inicio in range(0, len(pendientes), TANDA // 4):
                tramo = pendientes[inicio:inicio + TANDA // 4]
                for ruta, tamano, fecha, leidos in hilos.map(leer, tramo):
                    valores = {}
                    if leidos:
                        if leidos.pop("_ilegible", False):
                            resumen.ilegibles += 1
                        valores.update(leidos)
                    valores.update(
                        clave=datos.clave(ruta), ruta=ruta,
                        relativa=os.path.relpath(ruta, raiz),
                        formato=os.path.splitext(ruta)[1].lstrip(".").upper(),
                        tamano=tamano, fecha=fecha,
                        anadido=time.strftime("%Y-%m-%d", time.localtime(fecha)))
                    valores["formatos"] = valores["formato"]
                    escritor.poner(valores)
                    hechos += 1
                    avance(hechos, total, _("Leyendo: %(hecho)d de %(total)d libros")
                           % {"hecho": hechos, "total": total})
        completo = True
        datos.marcar_actualizada(conexion, fuente.id)
    except Detenido:
        resumen.detenido = True
    finally:
        escritor.terminar(completo)


# -- la orden de importar ------------------------------------------------------


def importar(fuente_ids, opciones: OpcionesImportacion, progreso=None, cancelado=None,
             ruta_bd=None) -> list[Resumen]:
    """Importa o actualiza una o varias fuentes, una detrás de otra.

    Las bibliotecas de calibre que aparezcan dentro de una carpeta se dan de
    alta como fuentes propias y se importan a continuación, de modo que una
    sola orden deja todo dentro.

    :param progreso: Se llama con ``(hecho, total, detalle)``; ``total`` es 0
                     mientras no se sabe cuántos hay (al explorar).
    :param cancelado: Se consulta a menudo; si devuelve verdadero, se para.
    :return: Un resumen por fuente.
    """
    conexion = datos.conectar(ruta_bd)
    avance = _Avance(progreso, cancelado)
    resumenes: list[Resumen] = []
    cola = [int(i) for i in fuente_ids]
    hechas: set[int] = set()
    try:
        while cola:
            numero = cola.pop(0)
            if numero in hechas:
                continue
            hechas.add(numero)
            fuente = datos.fuente(conexion, numero)
            if fuente is None:
                continue
            resumen = Resumen(fuente.nombre, fuente.tipo, fuente.ruta)
            resumenes.append(resumen)
            inicio = time.monotonic()
            if progreso is not None:
                progreso(0, 0, (_("Importando la biblioteca de calibre «%s»...")
                                if fuente.es_calibre else
                                _("Importando la carpeta «%s»...")) % fuente.nombre)
            try:
                if fuente.es_calibre:
                    importar_calibre(conexion, fuente, opciones, avance, resumen)
                else:
                    importar_carpeta(conexion, fuente, opciones, avance, resumen)
            except Detenido:
                resumen.detenido = True
            except Exception as error:
                log.exception("Error al importar %s", fuente.ruta)
                resumen.error = str(error)
            resumen.segundos = time.monotonic() - inicio
            log.info("Importada %s «%s» (%s): %d libros, %d nuevos, %d puestos al día, "
                     "%d iguales, %d quitados, %d sin formato, %d ilegibles%s%s, %.1f s",
                     fuente.tipo, fuente.nombre, fuente.ruta, resumen.total,
                     resumen.nuevos, resumen.actualizados, resumen.iguales,
                     resumen.quitados, resumen.sin_formato, resumen.ilegibles,
                     ", detenida" if resumen.detenido else "",
                     (", error: %s" % resumen.error) if resumen.error else "",
                     resumen.segundos)
            if resumen.detenido:
                break
            for anidada in resumen.calibres:
                if datos.fuente_por_ruta(conexion, anidada) is None:
                    cola.append(datos.anadir_fuente(conexion, datos.CALIBRE, anidada,
                                                    nombre_de_calibre(anidada)))
                else:
                    cola.append(datos.fuente_por_ruta(conexion, anidada).id)
    finally:
        conexion.close()
    return resumenes


def texto_resumen(resumenes) -> str:
    """El resumen de varias importaciones juntas, para enseñarlo al final."""
    if not resumenes:
        return _("No se ha importado nada.")
    bloques = [r.texto() for r in resumenes]
    if len(resumenes) > 1:
        nuevos = sum(r.nuevos for r in resumenes)
        actualizados = sum(r.actualizados for r in resumenes)
        quitados = sum(r.quitados for r in resumenes)
        bloques.insert(0, _("En total: %(nuevos)d nuevos, %(actualizados)d puestos al "
                            "día y %(quitados)d quitados.")
                       % {"nuevos": nuevos, "actualizados": actualizados,
                          "quitados": quitados})
    return "\n\n".join(bloques)
