# -*- coding: utf-8 -*-
"""Dónde se guarda la biblioteca: una base de datos SQLite propia.

Hasta la versión 1.3.4 la biblioteca no se guardaba: cada vez que se abría la
ventana se volvían a recorrer **todas** las carpetas añadidas, archivo por
archivo, y se consultaba el disco por cada libro para saber si seguía ahí.  Con
trescientos libros eso no se nota; con ciento noventa mil en un disco de los de
girar son minutos con la ventana colgada, y por eso había un tope de cinco mil.

Ahora la exploración se hace **una vez**, al añadir la carpeta o al pedir que
se actualice, y lo encontrado se apunta aquí.  Abrir la biblioteca es leer esta
base de datos, que con ciento noventa mil libros tarda un par de segundos, y se
hace en segundo plano con la ventana ya abierta.

Qué hay dentro
--------------

* ``fuentes``: de dónde salen los libros.  Una carpeta corriente o una
  biblioteca de calibre, con su nombre, su ruta y cuándo se actualizó.
* ``libros``: un libro por fila, con **todo lo que se sabe de él**: título,
  autores, serie y número, etiquetas, editorial, fecha de publicación, idioma,
  identificadores, sinopsis, valoración, formatos y las columnas propias que el
  usuario tenga en calibre.  Cada libro guarda además su ruta **relativa** a la
  fuente: si la biblioteca cambia de disco o de letra basta con decirle la ruta
  nueva a la fuente, sin volver a importar nada.
* ``excluidos``: libros que el usuario ha quitado a mano, para que al
  actualizar la fuente no vuelvan a aparecer.

Lo que **no** está aquí es por dónde va la lectura, los marcadores ni la
colección de cada libro: eso sigue en ``documentos.json``, que es lo que se
sincroniza entre equipos.  La biblioteca es lo que hay en el disco; aquello es
lo que el usuario ha hecho con ello.

El archivo vive en ``data/config`` junto al resto de la configuración, así que
un programa portátil se lleva su biblioteca consigo.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import time
import zipfile
from pathlib import Path

from . import rutas
from .registro import obtener_registro

log = obtener_registro(__name__)

#: Nombre del archivo dentro de ``data/config``.
ARCHIVO = "biblioteca.db"

#: Versión del esquema.  Si cambia, :func:`_poner_al_dia` sabe qué añadir.
VERSION_ESQUEMA = 2

#: Tipos de fuente.
CARPETA = "carpeta"
CALIBRE = "calibre"

#: Columnas de la tabla ``libros`` que llenan los importadores, en orden.
#: Están en una sola lista para que insertar y actualizar no se descuadren.
CAMPOS = (
    "fuente", "clave", "ruta", "relativa", "titulo", "orden_titulo", "autor",
    "orden_autor", "autores_orden", "serie", "serie_indice", "etiquetas",
    "editorial", "publicado", "idioma", "isbn", "identificadores", "comentarios",
    "valoracion", "formato", "formatos", "tamano", "fecha", "anadido", "calibre_id",
    "uuid", "portada", "extra", "busqueda", "firma",
)

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS meta (
    clave TEXT PRIMARY KEY,
    valor TEXT
);
CREATE TABLE IF NOT EXISTS fuentes (
    id INTEGER PRIMARY KEY,
    tipo TEXT NOT NULL,
    ruta TEXT NOT NULL,
    clave TEXT NOT NULL UNIQUE,
    nombre TEXT NOT NULL DEFAULT '',
    anadida REAL NOT NULL DEFAULT 0,
    actualizada REAL NOT NULL DEFAULT 0,
    libros INTEGER NOT NULL DEFAULT 0,
    uuid TEXT NOT NULL DEFAULT '',
    pendiente INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS libros (
    id INTEGER PRIMARY KEY,
    fuente INTEGER NOT NULL REFERENCES fuentes(id) ON DELETE CASCADE,
    clave TEXT NOT NULL UNIQUE,
    ruta TEXT NOT NULL,
    relativa TEXT NOT NULL DEFAULT '',
    titulo TEXT NOT NULL DEFAULT '',
    orden_titulo TEXT NOT NULL DEFAULT '',
    autor TEXT NOT NULL DEFAULT '',
    orden_autor TEXT NOT NULL DEFAULT '',
    autores_orden TEXT NOT NULL DEFAULT '',
    serie TEXT NOT NULL DEFAULT '',
    serie_indice REAL NOT NULL DEFAULT 0,
    etiquetas TEXT NOT NULL DEFAULT '',
    editorial TEXT NOT NULL DEFAULT '',
    publicado TEXT NOT NULL DEFAULT '',
    idioma TEXT NOT NULL DEFAULT '',
    isbn TEXT NOT NULL DEFAULT '',
    identificadores TEXT NOT NULL DEFAULT '',
    comentarios TEXT NOT NULL DEFAULT '',
    valoracion INTEGER NOT NULL DEFAULT 0,
    formato TEXT NOT NULL DEFAULT '',
    formatos TEXT NOT NULL DEFAULT '',
    tamano INTEGER NOT NULL DEFAULT 0,
    fecha REAL NOT NULL DEFAULT 0,
    anadido TEXT NOT NULL DEFAULT '',
    calibre_id INTEGER NOT NULL DEFAULT 0,
    uuid TEXT NOT NULL DEFAULT '',
    portada TEXT NOT NULL DEFAULT '',
    extra TEXT NOT NULL DEFAULT '',
    busqueda TEXT NOT NULL DEFAULT '',
    firma TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS libros_fuente ON libros(fuente);
CREATE TABLE IF NOT EXISTS excluidos (
    clave TEXT PRIMARY KEY,
    fuente INTEGER NOT NULL DEFAULT 0
);
"""


def ruta_archivo() -> Path:
    """Dónde está la base de datos de la biblioteca."""
    return rutas.ruta_config() / ARCHIVO


def clave(ruta) -> str:
    """Cómo se compara si dos rutas son el mismo archivo.

    Windows no distingue mayúsculas ni el sentido de las barras, así que se
    igualan las dos cosas.  ``casefold`` y no ``lower`` para que dos nombres con
    letras como la «ß» se reconozcan igual que los compara el sistema.
    """
    return os.path.normpath(str(ruta)).replace("/", "\\").casefold()


def conectar(ruta: str | os.PathLike | None = None) -> sqlite3.Connection:
    """Abre la base de datos, creándola o poniéndola al día si hace falta.

    Cada hilo abre la suya: una conexión de SQLite no se comparte entre hilos,
    y abrirla cuesta milisegundos.
    """
    destino = Path(ruta) if ruta is not None else ruta_archivo()
    destino.parent.mkdir(parents=True, exist_ok=True)
    nueva = not destino.exists()
    conexion = sqlite3.connect(str(destino), timeout=30)
    conexion.row_factory = sqlite3.Row
    # El diario WAL deja leer mientras otro hilo escribe: es lo que permite
    # abrir la biblioteca mientras se está importando una carpeta.  Hay
    # sistemas de archivos donde no se puede (algunas unidades de red), y ahí
    # se sigue con el diario normal, que también vale, solo que más a turnos.
    try:
        conexion.execute("PRAGMA journal_mode=WAL")
    except sqlite3.DatabaseError as error:                  # pragma: no cover
        log.info("La biblioteca sigue sin WAL: %s", error)
    conexion.execute("PRAGMA synchronous=NORMAL")
    conexion.execute("PRAGMA foreign_keys=ON")
    # El esquema se comprueba una vez por archivo y por sesión: la ventana abre
    # conexiones cortas a menudo, a veces mientras otro hilo está importando, y
    # no hace falta repetirlo cada vez.
    if nueva or str(destino) not in _PREPARADAS:
        conexion.executescript(_ESQUEMA)
        _poner_al_dia(conexion)
        _PREPARADAS.add(str(destino))
    return conexion


#: Archivos de base de datos cuyo esquema ya se ha comprobado en esta sesión.
_PREPARADAS: set[str] = set()


def _poner_al_dia(conexion: sqlite3.Connection) -> None:
    """Pone al día una base de datos hecha con una versión anterior.

    * **Esquema 2 (1.3.6)**: cada libro guarda además sus autores en la forma
      de cita —«Fuentes Aguirre, Armando»—, que calibre tiene de cada autor y
      los EPUB traen en ``opf:file-as``.  Las bibliotecas de calibre que ya
      estaban se apuntan para volver a leerlas, y así lo traen.
    """
    fila = conexion.execute("SELECT valor FROM meta WHERE clave='esquema'").fetchone()
    columnas = {f[1] for f in conexion.execute("PRAGMA table_info(libros)")}
    if "autores_orden" not in columnas:
        conexion.execute("ALTER TABLE libros ADD COLUMN autores_orden "
                         "TEXT NOT NULL DEFAULT ''")
        if fila is not None:
            conexion.execute("INSERT OR REPLACE INTO meta(clave, valor) "
                             "VALUES('releer_calibre', '1')")
    conexion.execute("INSERT OR REPLACE INTO meta(clave, valor) VALUES('esquema', ?)",
                     (str(VERSION_ESQUEMA),))
    conexion.commit()


def leer_meta(conexion, nombre: str, por_omision: str = "") -> str:
    """Un valor suelto guardado en la tabla ``meta``."""
    fila = conexion.execute("SELECT valor FROM meta WHERE clave=?", (nombre,)).fetchone()
    return fila[0] if fila is not None and fila[0] is not None else por_omision


def escribir_meta(conexion, nombre: str, valor: str) -> None:
    """Guarda un valor suelto en la tabla ``meta``."""
    conexion.execute("INSERT OR REPLACE INTO meta(clave, valor) VALUES(?, ?)",
                     (nombre, str(valor)))
    conexion.commit()


# -- fuentes -------------------------------------------------------------------


class Fuente:
    """Una carpeta o una biblioteca de calibre de las que salen libros."""

    __slots__ = ("id", "tipo", "ruta", "nombre", "anadida", "actualizada",
                 "libros", "uuid", "pendiente")

    def __init__(self, fila) -> None:
        self.id = int(fila["id"])
        self.tipo = str(fila["tipo"])
        self.ruta = str(fila["ruta"])
        self.nombre = str(fila["nombre"] or "") or Path(self.ruta).name or self.ruta
        self.anadida = float(fila["anadida"] or 0)
        self.actualizada = float(fila["actualizada"] or 0)
        self.libros = int(fila["libros"] or 0)
        self.uuid = str(fila["uuid"] or "")
        self.pendiente = bool(fila["pendiente"])

    @property
    def es_calibre(self) -> bool:
        """Si es una biblioteca de calibre y no una carpeta corriente."""
        return self.tipo == CALIBRE

    @property
    def disponible(self) -> bool:
        """Si la carpeta está ahora mismo al alcance (el disco enchufado)."""
        try:
            return os.path.isdir(self.ruta)
        except OSError:                                      # pragma: no cover
            return False

    def fecha_legible(self) -> str:
        """Cuándo se actualizó por última vez, escrito como se lee."""
        if not self.actualizada:
            return ""
        return time.strftime("%d/%m/%Y %H:%M", time.localtime(self.actualizada))


def fuentes(conexion) -> list[Fuente]:
    """Todas las fuentes, por orden de nombre."""
    filas = conexion.execute("SELECT * FROM fuentes").fetchall()
    return sorted((Fuente(f) for f in filas), key=lambda f: f.nombre.casefold())


def fuente(conexion, identificador: int) -> Fuente | None:
    """Una fuente por su número, o ``None`` si ya no está."""
    fila = conexion.execute("SELECT * FROM fuentes WHERE id=?",
                            (int(identificador),)).fetchone()
    return Fuente(fila) if fila is not None else None


def fuente_por_ruta(conexion, ruta) -> Fuente | None:
    """La fuente que tiene exactamente esa ruta, si la hay."""
    fila = conexion.execute("SELECT * FROM fuentes WHERE clave=?",
                            (clave(ruta),)).fetchone()
    return Fuente(fila) if fila is not None else None


def fuente_que_contiene(conexion, ruta) -> Fuente | None:
    """La fuente dentro de la cual cae esa ruta (o que es esa misma)."""
    buscada = clave(ruta)
    for candidata in fuentes(conexion):
        base = clave(candidata.ruta)
        if buscada == base or buscada.startswith(base.rstrip("\\") + "\\"):
            return candidata
    return None


def anadir_fuente(conexion, tipo: str, ruta, nombre: str = "",
                  pendiente: bool = False) -> int:
    """Da de alta una fuente y devuelve su número.  Si ya existía, la reutiliza."""
    ruta = os.path.normpath(str(ruta))
    existente = fuente_por_ruta(conexion, ruta)
    if existente is not None:
        conexion.execute("UPDATE fuentes SET tipo=? WHERE id=?", (tipo, existente.id))
        conexion.commit()
        return existente.id
    cursor = conexion.execute(
        "INSERT INTO fuentes(tipo, ruta, clave, nombre, anadida, pendiente) "
        "VALUES(?, ?, ?, ?, ?, ?)",
        (tipo, ruta, clave(ruta), (nombre or "").strip() or Path(ruta).name or ruta,
         time.time(), 1 if pendiente else 0))
    conexion.commit()
    return int(cursor.lastrowid)


def editar_fuente(conexion, identificador: int, nombre: str | None = None,
                  ruta_nueva: str | None = None) -> int:
    """Cambia el nombre de una fuente o la lleva a otra ruta.

    Llevarla a otra ruta es para cuando el disco cambia de letra o la carpeta
    se mueve entera: cada libro guarda su ruta **relativa** a la fuente, así
    que basta con recomponerlas, sin volver a explorar ni a importar nada.

    :return: Cuántos libros se han recolocado.
    """
    actual = fuente(conexion, identificador)
    if actual is None:
        return 0
    if nombre is not None and nombre.strip():
        conexion.execute("UPDATE fuentes SET nombre=? WHERE id=?",
                         (nombre.strip(), actual.id))
    movidos = 0
    if ruta_nueva and clave(ruta_nueva) != clave(actual.ruta):
        ruta_nueva = os.path.normpath(str(ruta_nueva))
        conexion.execute("UPDATE fuentes SET ruta=?, clave=? WHERE id=?",
                         (ruta_nueva, clave(ruta_nueva), actual.id))
        filas = conexion.execute(
            "SELECT id, relativa FROM libros WHERE fuente=?", (actual.id,)).fetchall()
        cambios = []
        for fila in filas:
            nueva = os.path.join(ruta_nueva, fila["relativa"])
            cambios.append((nueva, clave(nueva), fila["id"]))
        # OR REPLACE por si la ruta nueva ya estaba en la biblioteca por otra
        # fuente: gana la que se está recolocando.
        conexion.executemany(
            "UPDATE OR REPLACE libros SET ruta=?, clave=? WHERE id=?", cambios)
        movidos = len(cambios)
    conexion.commit()
    return movidos


def quitar_fuentes(conexion, identificadores) -> int:
    """Quita fuentes con todos sus libros.  No toca ningún archivo del disco.

    :return: Cuántos libros han salido de la biblioteca.
    """
    numeros = [int(i) for i in identificadores]
    if not numeros:
        return 0
    marcas = ",".join("?" * len(numeros))
    quitados = conexion.execute(
        "SELECT COUNT(*) FROM libros WHERE fuente IN (%s)" % marcas, numeros).fetchone()[0]
    conexion.execute("DELETE FROM libros WHERE fuente IN (%s)" % marcas, numeros)
    conexion.execute("DELETE FROM excluidos WHERE fuente IN (%s)" % marcas, numeros)
    conexion.execute("DELETE FROM fuentes WHERE id IN (%s)" % marcas, numeros)
    conexion.commit()
    return int(quitados)


def recontar(conexion, identificador: int) -> int:
    """Vuelve a contar los libros de una fuente y lo apunta."""
    total = conexion.execute("SELECT COUNT(*) FROM libros WHERE fuente=?",
                             (int(identificador),)).fetchone()[0]
    conexion.execute("UPDATE fuentes SET libros=? WHERE id=?", (total, int(identificador)))
    conexion.commit()
    return int(total)


def marcar_actualizada(conexion, identificador: int, uuid: str = "") -> None:
    """Apunta que la fuente se acaba de actualizar."""
    conexion.execute(
        "UPDATE fuentes SET actualizada=?, pendiente=0, "
        "uuid=CASE WHEN ?<>'' THEN ? ELSE uuid END WHERE id=?",
        (time.time(), uuid, uuid, int(identificador)))
    conexion.commit()


# -- libros quitados a mano -----------------------------------------------------


def excluir(conexion, pares) -> int:
    """Saca libros de la biblioteca y los apunta para que no vuelvan solos.

    :param pares: ``(ruta, fuente)`` de cada libro; la fuente puede ser 0 para
                  los que solo se conocen por haberlos abierto.
    """
    filas = [(clave(ruta), int(numero or 0)) for ruta, numero in pares]
    conexion.executemany("INSERT OR REPLACE INTO excluidos(clave, fuente) VALUES(?, ?)",
                         filas)
    conexion.executemany("DELETE FROM libros WHERE clave=?", [(c,) for c, _f in filas])
    conexion.commit()
    for numero in {f for _c, f in filas if f}:
        recontar(conexion, numero)
    return len(filas)


def readmitir(conexion, ruta) -> None:
    """Olvida que un libro se había quitado.  Se llama al volver a abrirlo."""
    conexion.execute("DELETE FROM excluidos WHERE clave=?", (clave(ruta),))
    conexion.commit()


def excluidas(conexion, fuente_id: int | None = None) -> set[str]:
    """Claves de los libros quitados a mano, de una fuente o de todas."""
    if fuente_id is None:
        filas = conexion.execute("SELECT clave FROM excluidos").fetchall()
    else:
        filas = conexion.execute("SELECT clave FROM excluidos WHERE fuente=?",
                                 (int(fuente_id),)).fetchall()
    return {fila[0] for fila in filas}


def readmitir_todos(conexion, fuente_id: int | None = None) -> int:
    """Devuelve a la biblioteca lo quitado a mano (al actualizar se recupera)."""
    if fuente_id is None:
        cursor = conexion.execute("DELETE FROM excluidos")
    else:
        cursor = conexion.execute("DELETE FROM excluidos WHERE fuente=?", (int(fuente_id),))
    conexion.commit()
    return int(cursor.rowcount or 0)


# -- lectura -------------------------------------------------------------------

#: Lo que se lee de cada libro para enseñar la lista.  La sinopsis, los
#: identificadores y las columnas propias se quedan fuera: ocupan mucho y solo
#: hacen falta al abrir la ficha de **un** libro.
CAMPOS_LISTA = ("id", "fuente", "clave", "ruta", "titulo", "orden_titulo", "autor",
                "orden_autor", "autores_orden", "serie", "serie_indice", "etiquetas",
                "editorial", "publicado", "idioma", "formato", "tamano", "fecha",
                "anadido", "valoracion", "busqueda", "isbn")


def contar_libros(conexion) -> int:
    """Cuántos libros hay apuntados en total."""
    return int(conexion.execute("SELECT COUNT(*) FROM libros").fetchone()[0])


def leer_libros(conexion, tanda: int = 5000):
    """Recorre los libros a tandas, para poder ir avisando del avance."""
    cursor = conexion.execute("SELECT %s FROM libros" % ", ".join(CAMPOS_LISTA))
    while True:
        filas = cursor.fetchmany(tanda)
        if not filas:
            break
        yield filas


def ficha(conexion, ruta) -> dict | None:
    """Todo lo que se sabe de un libro, para enseñar su ficha."""
    fila = conexion.execute(
        "SELECT l.*, f.nombre AS nombre_fuente, f.tipo AS tipo_fuente, "
        "f.ruta AS ruta_fuente FROM libros l LEFT JOIN fuentes f ON f.id=l.fuente "
        "WHERE l.clave=?", (clave(ruta),)).fetchone()
    if fila is None:
        return None
    datos = dict(fila)
    for nombre in ("extra", "identificadores"):
        try:
            datos[nombre] = json.loads(datos.get(nombre) or "{}")
        except ValueError:
            datos[nombre] = {}
    return datos


# -- copia de seguridad ----------------------------------------------------------

#: Nombres de los archivos dentro de la copia.
_EN_COPIA_BD = "biblioteca.db"
_EN_COPIA_DOCUMENTOS = "documentos.json"
_EN_COPIA_FICHA = "copia.json"


def copia_de_seguridad(destino, archivo_documentos=None, progreso=None) -> int:
    """Guarda en un ZIP la biblioteca y lo que se ha hecho en cada libro.

    Lleva la base de datos de la biblioteca (las fuentes y todos los libros
    con sus datos) y ``documentos.json`` (por dónde va cada libro, los
    marcadores, las notas y las colecciones).  Con las dos cosas, el programa
    se lleva a otro equipo o se reinstala sin perder nada.

    La base de datos no se copia tal cual: se usa la copia en caliente de
    SQLite, que da un archivo coherente aunque otro hilo esté escribiendo.

    :return: Cuántos libros lleva la copia.
    """
    import tempfile

    destino = Path(destino)
    if archivo_documentos is None:
        archivo_documentos = rutas.ruta_config() / "documentos.json"
    with tempfile.TemporaryDirectory(dir=str(rutas.ruta_temp())) as carpeta:
        instantanea = Path(carpeta) / _EN_COPIA_BD
        origen = conectar()
        try:
            copia = sqlite3.connect(str(instantanea))
            try:
                def avance(estado, quedan, total):
                    if progreso is not None and total:
                        progreso(total - quedan, total, "")
                origen.backup(copia, pages=4096, progress=avance)
                libros = copia.execute("SELECT COUNT(*) FROM libros").fetchone()[0]
            finally:
                copia.close()
        finally:
            origen.close()
        temporal = destino.with_name(destino.name + ".tmp")
        with zipfile.ZipFile(temporal, "w", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=6, allowZip64=True) as zip_:
            zip_.write(instantanea, _EN_COPIA_BD)
            if Path(archivo_documentos).is_file():
                zip_.write(archivo_documentos, _EN_COPIA_DOCUMENTOS)
            zip_.writestr(_EN_COPIA_FICHA, json.dumps(
                {"version": VERSION_ESQUEMA, "fecha": time.time(), "libros": libros},
                ensure_ascii=False))
        os.replace(temporal, destino)
    return int(libros)


def leer_copia(origen) -> dict:
    """Dice qué lleva una copia de seguridad, sin restaurarla."""
    with zipfile.ZipFile(origen) as zip_:
        nombres = set(zip_.namelist())
        if _EN_COPIA_BD not in nombres:
            raise ValueError("no es una copia de la biblioteca")
        ficha_copia = {}
        if _EN_COPIA_FICHA in nombres:
            try:
                ficha_copia = json.loads(zip_.read(_EN_COPIA_FICHA).decode("utf-8"))
            except ValueError:
                ficha_copia = {}
        ficha_copia["documentos"] = _EN_COPIA_DOCUMENTOS in nombres
        return ficha_copia


def restaurar_copia(origen, archivo_documentos=None) -> int:
    """Pone en su sitio una copia hecha con :func:`copia_de_seguridad`.

    Se comprueba antes de tocar nada que la base de datos de la copia se puede
    abrir y tiene libros; si no, se deja todo como estaba.

    :return: Cuántos libros hay ahora en la biblioteca.
    """
    import tempfile

    if archivo_documentos is None:
        archivo_documentos = rutas.ruta_config() / "documentos.json"
    leer_copia(origen)
    with tempfile.TemporaryDirectory(dir=str(rutas.ruta_temp())) as carpeta:
        with zipfile.ZipFile(origen) as zip_:
            zip_.extract(_EN_COPIA_BD, carpeta)
            tiene_documentos = _EN_COPIA_DOCUMENTOS in zip_.namelist()
            if tiene_documentos:
                zip_.extract(_EN_COPIA_DOCUMENTOS, carpeta)
        nueva = Path(carpeta) / _EN_COPIA_BD
        prueba = sqlite3.connect(str(nueva))
        try:
            libros = prueba.execute("SELECT COUNT(*) FROM libros").fetchone()[0]
            prueba.execute("SELECT COUNT(*) FROM fuentes").fetchone()
        finally:
            prueba.close()
        actual = ruta_archivo()
        for sobrante in (actual.with_name(actual.name + "-wal"),
                         actual.with_name(actual.name + "-shm")):
            try:
                sobrante.unlink()
            except FileNotFoundError:
                pass
        shutil.copyfile(nueva, actual.with_name(actual.name + ".tmp"))
        os.replace(actual.with_name(actual.name + ".tmp"), actual)
        if tiene_documentos:
            destino = Path(archivo_documentos)
            shutil.copyfile(Path(carpeta) / _EN_COPIA_DOCUMENTOS,
                            destino.with_name(destino.name + ".tmp"))
            os.replace(destino.with_name(destino.name + ".tmp"), destino)
    return int(libros)
