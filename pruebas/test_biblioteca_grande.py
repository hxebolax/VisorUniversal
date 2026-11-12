# -*- coding: utf-8 -*-
"""Pruebas de la biblioteca guardada: carpetas, calibre y gestión en lote.

La biblioteca de calibre se fabrica aquí con lo justo de su esquema
(``resources/metadata_sqlite.sql`` de calibre): las tablas que se leen y un
índice con la colación ``PYNOCASE``, que es lo que obliga a registrarla antes
de poder consultar nada.
"""

from __future__ import annotations

import json
import os
import sqlite3
import zipfile

import pytest

from nucleo import bibliografia, biblioteca
from nucleo import biblioteca_datos as datos
from nucleo import biblioteca_importar as importar


def _pynocase(a, b):
    a, b = a.lower(), b.lower()
    return (a > b) - (a < b)


ESQUEMA_CALIBRE = """
CREATE TABLE books ( id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL DEFAULT 'Unknown' COLLATE NOCASE, sort TEXT COLLATE NOCASE,
    timestamp TIMESTAMP, pubdate TIMESTAMP, series_index REAL NOT NULL DEFAULT 1.0,
    author_sort TEXT COLLATE NOCASE, path TEXT NOT NULL DEFAULT '', uuid TEXT,
    has_cover BOOL DEFAULT 0, last_modified TIMESTAMP);
CREATE TABLE authors ( id INTEGER PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE,
    sort TEXT COLLATE NOCASE, link TEXT NOT NULL DEFAULT '', UNIQUE(name));
CREATE INDEX authors_idx ON authors (name COLLATE PYNOCASE);
CREATE TABLE books_authors_link ( id INTEGER PRIMARY KEY, book INTEGER NOT NULL,
    author INTEGER NOT NULL, UNIQUE(book, author));
CREATE TABLE series ( id INTEGER PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE,
    sort TEXT COLLATE NOCASE, link TEXT NOT NULL DEFAULT '', UNIQUE (name));
CREATE TABLE books_series_link ( id INTEGER PRIMARY KEY, book INTEGER NOT NULL,
    series INTEGER NOT NULL, UNIQUE(book));
CREATE TABLE tags ( id INTEGER PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE,
    link TEXT NOT NULL DEFAULT '', UNIQUE (name));
CREATE TABLE books_tags_link ( id INTEGER PRIMARY KEY, book INTEGER NOT NULL,
    tag INTEGER NOT NULL, UNIQUE(book, tag));
CREATE TABLE publishers ( id INTEGER PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE,
    sort TEXT COLLATE NOCASE, link TEXT NOT NULL DEFAULT '', UNIQUE(name));
CREATE TABLE books_publishers_link ( id INTEGER PRIMARY KEY, book INTEGER NOT NULL,
    publisher INTEGER NOT NULL, UNIQUE(book));
CREATE TABLE ratings ( id INTEGER PRIMARY KEY, rating INTEGER, link TEXT NOT NULL DEFAULT '',
    UNIQUE (rating));
CREATE TABLE books_ratings_link ( id INTEGER PRIMARY KEY, book INTEGER NOT NULL,
    rating INTEGER NOT NULL, UNIQUE(book, rating));
CREATE TABLE languages ( id INTEGER PRIMARY KEY, lang_code TEXT NOT NULL COLLATE NOCASE,
    link TEXT NOT NULL DEFAULT '', UNIQUE(lang_code));
CREATE TABLE books_languages_link ( id INTEGER PRIMARY KEY, book INTEGER NOT NULL,
    lang_code INTEGER NOT NULL, item_order INTEGER NOT NULL DEFAULT 0,
    UNIQUE(book, lang_code));
CREATE TABLE comments ( id INTEGER PRIMARY KEY, book INTEGER NOT NULL,
    text TEXT NOT NULL COLLATE NOCASE, UNIQUE(book));
CREATE TABLE identifiers ( id INTEGER PRIMARY KEY, book INTEGER NOT NULL,
    type TEXT NOT NULL DEFAULT 'isbn' COLLATE NOCASE, val TEXT NOT NULL COLLATE NOCASE,
    UNIQUE(book, type));
CREATE TABLE data ( id INTEGER PRIMARY KEY, book INTEGER NOT NULL,
    format TEXT NOT NULL COLLATE NOCASE, uncompressed_size INTEGER NOT NULL,
    name TEXT NOT NULL, UNIQUE(book, format));
CREATE TABLE library_id ( id INTEGER PRIMARY KEY, uuid TEXT NOT NULL, UNIQUE(uuid));
CREATE TABLE custom_columns ( id INTEGER PRIMARY KEY AUTOINCREMENT, label TEXT NOT NULL,
    name TEXT NOT NULL, datatype TEXT NOT NULL, mark_for_delete BOOL DEFAULT 0 NOT NULL,
    editable BOOL DEFAULT 1 NOT NULL, display TEXT DEFAULT '{}' NOT NULL,
    is_multiple BOOL DEFAULT 0 NOT NULL, normalized BOOL NOT NULL, UNIQUE(label));
CREATE TABLE custom_column_1 (id INTEGER PRIMARY KEY, value TEXT NOT NULL COLLATE NOCASE,
    link TEXT NOT NULL DEFAULT '', UNIQUE(value));
CREATE INDEX custom_column_1_idx ON custom_column_1 (value COLLATE PYNOCASE);
CREATE TABLE books_custom_column_1_link (id INTEGER PRIMARY KEY, book INTEGER NOT NULL,
    value INTEGER NOT NULL, UNIQUE(book, value));
CREATE TABLE custom_column_2 (id INTEGER PRIMARY KEY, book INTEGER, value INT NOT NULL,
    UNIQUE(book));
"""


def _crear_calibre(raiz, libros):
    """Fabrica una biblioteca de calibre con esos libros.

    :param libros: ``[(id, título, [autores], serie, índice, [etiquetas], formatos)]``.
    """
    raiz.mkdir(parents=True, exist_ok=True)
    conexion = sqlite3.connect(str(raiz / "metadata.db"))
    conexion.create_collation("PYNOCASE", _pynocase)
    conexion.executescript(ESQUEMA_CALIBRE)
    conexion.execute("INSERT INTO library_id(uuid) VALUES('biblio-1')")
    conexion.execute("INSERT INTO custom_columns(label, name, datatype, is_multiple, "
                     "normalized, display) VALUES('estado', 'Estado', 'text', 0, 1, '{}')")
    conexion.execute("INSERT INTO custom_columns(label, name, datatype, is_multiple, "
                     "normalized, display) VALUES('pages', 'Páginas', 'int', 0, 0, '{}')")
    conexion.execute("INSERT INTO custom_column_1(value) VALUES('Leído')")
    conexion.execute("INSERT INTO languages(lang_code) VALUES('spa')")
    _poner_libros(conexion, raiz, libros)
    conexion.commit()
    conexion.close()


def _poner_libros(conexion, raiz, libros):
    for numero, titulo, autores, serie, indice, etiquetas, formatos in libros:
        carpeta = "%s/%s (%d)" % (autores[0], titulo, numero)
        conexion.execute(
            "INSERT INTO books(id, title, sort, timestamp, pubdate, series_index, "
            "author_sort, path, uuid, has_cover) VALUES(?,?,?,?,?,?,?,?,?,1)",
            (numero, titulo, titulo, "2021-06-25 22:00:00+00:00",
             "1880-01-01 00:00:00+00:00" if numero % 2 else "0101-01-01 00:00:00+00:00",
             indice, autores[0], carpeta, "uuid-%d" % numero))
        for autor in autores:
            conexion.execute("INSERT OR IGNORE INTO authors(name, sort) VALUES(?, ?)",
                             (autor, FORMAS_DE_CITA.get(autor, autor)))
            conexion.execute("INSERT INTO books_authors_link(book, author) "
                             "SELECT ?, id FROM authors WHERE name=?", (numero, autor))
        if serie:
            conexion.execute("INSERT OR IGNORE INTO series(name, sort) VALUES(?, ?)",
                             (serie, serie))
            conexion.execute("INSERT INTO books_series_link(book, series) "
                             "SELECT ?, id FROM series WHERE name=?", (numero, serie))
        for etiqueta in etiquetas:
            conexion.execute("INSERT OR IGNORE INTO tags(name) VALUES(?)", (etiqueta,))
            conexion.execute("INSERT INTO books_tags_link(book, tag) "
                             "SELECT ?, id FROM tags WHERE name=?", (numero, etiqueta))
        conexion.execute("INSERT INTO books_languages_link(book, lang_code) VALUES(?, 1)",
                         (numero,))
        conexion.execute("INSERT INTO comments(book, text) VALUES(?, ?)",
                         (numero, "<p>Primera &amp; parte.</p><p>Segunda.</p>"))
        conexion.execute("INSERT INTO identifiers(book, type, val) VALUES(?, 'isbn', ?)",
                         (numero, "97884%05d" % numero))
        conexion.execute("INSERT INTO books_custom_column_1_link(book, value) VALUES(?, 1)",
                         (numero,))
        conexion.execute("INSERT INTO custom_column_2(book, value) VALUES(?, ?)",
                         (numero, 100 + numero))
        nombre = "%s - %s" % (titulo, autores[0])
        for formato in formatos:
            conexion.execute("INSERT INTO data(book, format, uncompressed_size, name) "
                             "VALUES(?,?,?,?)", (numero, formato, 1234, nombre))
            destino = raiz / carpeta / ("%s.%s" % (nombre, formato.lower()))
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(b"x")


#: Cómo guarda calibre el orden de un autor (su «sort»).
FORMAS_DE_CITA = {"Benito Pérez Galdós": "Pérez Galdós, Benito"}

LIBROS = [
    (1, "Trafalgar", ["Benito Pérez Galdós"], "Episodios nacionales", 1.0,
     ["Novela", "Historia"], ["EPUB", "PDF"]),
    (2, "La Corte de Carlos IV", ["Benito Pérez Galdós"], "Episodios nacionales", 2.0,
     ["Novela"], ["EPUB"]),
    (3, "Fortunata y Jacinta", ["Benito Pérez Galdós", "Otro Autor"], "", 0,
     [], ["PDF", "EPUB"]),
    (4, "Solo en LIT", ["Nadie"], "", 0, [], ["LIT"]),
]


@pytest.fixture
def opciones():
    return importar.OpcionesImportacion(admitidas=[".epub", ".pdf"])


def _importar_nueva(bd, tipo, ruta, opciones):
    conexion = datos.conectar(bd)
    numero = datos.anadir_fuente(conexion, tipo, ruta)
    conexion.close()
    return numero, importar.importar([numero], opciones, ruta_bd=bd)[0]


def test_se_importa_una_biblioteca_de_calibre_con_todos_sus_datos(tmp_path, opciones):
    raiz = tmp_path / "Calibre"
    _crear_calibre(raiz, LIBROS)
    bd = tmp_path / "biblioteca.db"

    _numero, resumen = _importar_nueva(bd, datos.CALIBRE, raiz, opciones)

    assert resumen.nuevos == 3 and resumen.sin_formato == 1 and not resumen.error
    conexion = datos.conectar(bd)
    ruta = os.path.join(str(raiz), "Benito Pérez Galdós", "Trafalgar (1)",
                        "Trafalgar - Benito Pérez Galdós.epub")
    ficha = datos.ficha(conexion, ruta)
    conexion.close()
    assert ficha is not None, "el EPUB es el formato preferido y tiene su ruta exacta"
    assert ficha["titulo"] == "Trafalgar"
    assert ficha["serie"] == "Episodios nacionales" and ficha["serie_indice"] == 1.0
    assert ficha["etiquetas"] == "Historia, Novela"
    assert ficha["idioma"] == "Español"
    assert ficha["isbn"] == "9788400001"
    assert ficha["publicado"] == "1880-01-01"
    assert ficha["comentarios"] == "Primera & parte.\n\nSegunda."
    assert ficha["formatos"] == "EPUB, PDF"
    assert ficha["extra"] == {"Estado": "Leído", "Páginas": "101"}
    assert ficha["portada"].endswith("cover.jpg")


def test_actualizar_distingue_lo_igual_lo_cambiado_y_lo_que_ya_no_esta(tmp_path, opciones):
    raiz = tmp_path / "Calibre"
    _crear_calibre(raiz, LIBROS)
    bd = tmp_path / "biblioteca.db"
    numero, _resumen = _importar_nueva(bd, datos.CALIBRE, raiz, opciones)

    calibre = sqlite3.connect(str(raiz / "metadata.db"))
    calibre.create_collation("PYNOCASE", _pynocase)
    calibre.execute("UPDATE books SET title='Trafalgar (revisado)' WHERE id=1")
    calibre.execute("DELETE FROM data WHERE book=2")
    calibre.execute("DELETE FROM books WHERE id=2")
    calibre.commit()
    calibre.close()

    resumen = importar.importar([numero], opciones, ruta_bd=bd)[0]

    assert (resumen.nuevos, resumen.actualizados, resumen.iguales, resumen.quitados) == \
        (0, 1, 1, 1)
    assert resumen.total == 2
    assert "Puestos al día: 1" in resumen.texto()


def test_un_libro_por_formato_si_se_pide(tmp_path):
    raiz = tmp_path / "Calibre"
    _crear_calibre(raiz, LIBROS)
    bd = tmp_path / "biblioteca.db"
    opciones = importar.OpcionesImportacion(admitidas=[".epub", ".pdf"],
                                            un_libro_por_formato=True,
                                            formatos_preferidos="PDF, EPUB")

    _numero, resumen = _importar_nueva(bd, datos.CALIBRE, raiz, opciones)

    assert resumen.nuevos == 5


def test_una_carpeta_se_recorre_entera_y_lee_los_epub(tmp_path, opciones):
    carpeta = tmp_path / "Libros"
    (carpeta / "sub" / "subsub").mkdir(parents=True)
    with zipfile.ZipFile(carpeta / "sub" / "subsub" / "libro.epub", "w") as epub:
        epub.writestr("META-INF/container.xml",
                      '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                      '<rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles>'
                      '</container>')
        epub.writestr("OEBPS/content.opf",
                      '<package xmlns="http://www.idpf.org/2007/opf" '
                      'xmlns:dc="http://purl.org/dc/elements/1.1/"><metadata>'
                      '<dc:title>Misericordia</dc:title><dc:creator>Galdós</dc:creator>'
                      '<dc:language>es</dc:language><dc:subject>Novela</dc:subject>'
                      '<dc:identifier>urn:isbn:9781234567897</dc:identifier>'
                      '<meta name="calibre:series" content="Novelas españolas"/>'
                      '<meta name="calibre:series_index" content="4"/>'
                      '</metadata></package>')
    (carpeta / "suelto.pdf").write_bytes(b"%PDF")
    (carpeta / "nota.xyz").write_bytes(b"no")
    bd = tmp_path / "biblioteca.db"

    numero, resumen = _importar_nueva(bd, datos.CARPETA, carpeta, opciones)

    assert resumen.nuevos == 2
    conexion = datos.conectar(bd)
    ficha = datos.ficha(conexion, carpeta / "sub" / "subsub" / "libro.epub")
    conexion.close()
    assert ficha["titulo"] == "Misericordia" and ficha["autor"] == "Galdós"
    assert ficha["serie"] == "Novelas españolas" and ficha["serie_indice"] == 4
    assert ficha["isbn"] == "9781234567897" and ficha["idioma"] == "Español"

    resumen = importar.importar([numero], opciones, ruta_bd=bd)[0]
    assert resumen.iguales == 2 and resumen.nuevos == 0, "lo que no cambia no se relee"


def test_las_bibliotecas_de_calibre_dentro_de_una_carpeta_se_importan_aparte(tmp_path,
                                                                           opciones):
    carpeta = tmp_path / "Todo"
    _crear_calibre(carpeta / "Calibre", LIBROS)
    (carpeta / "otro.epub").write_bytes(b"x")
    bd = tmp_path / "biblioteca.db"
    conexion = datos.conectar(bd)
    numero = datos.anadir_fuente(conexion, datos.CARPETA, carpeta)
    conexion.close()

    resumenes = importar.importar([numero], opciones, ruta_bd=bd)

    assert [r.tipo for r in resumenes] == [datos.CARPETA, datos.CALIBRE]
    assert resumenes[0].nuevos == 1 and resumenes[1].nuevos == 3


def test_detener_deja_lo_hecho_y_no_quita_nada(tmp_path, opciones):
    raiz = tmp_path / "Calibre"
    _crear_calibre(raiz, LIBROS)
    bd = tmp_path / "biblioteca.db"
    numero, _resumen = _importar_nueva(bd, datos.CALIBRE, raiz, opciones)

    resumen = importar.importar([numero], opciones, cancelado=lambda: True, ruta_bd=bd)[0]

    assert resumen.detenido and resumen.quitados == 0
    conexion = datos.conectar(bd)
    assert datos.contar_libros(conexion) == 3
    conexion.close()


def test_quitar_editar_y_excluir_en_lote(tmp_path, opciones):
    raiz = tmp_path / "Calibre"
    _crear_calibre(raiz, LIBROS)
    bd = tmp_path / "biblioteca.db"
    numero, _resumen = _importar_nueva(bd, datos.CALIBRE, raiz, opciones)
    conexion = datos.conectar(bd)

    # Llevarla a otra ruta recoloca los libros sin volver a importar.
    nueva = tmp_path / "Movida"
    assert datos.editar_fuente(conexion, numero, "Mi calibre", str(nueva)) == 3
    rutas_libros = [f[0] for f in conexion.execute("SELECT ruta FROM libros")]
    assert all(r.startswith(str(nueva)) for r in rutas_libros)
    assert datos.fuente(conexion, numero).nombre == "Mi calibre"
    datos.editar_fuente(conexion, numero, None, str(raiz))

    # Lo quitado a mano no vuelve al actualizar... hasta que se devuelve.
    uno = conexion.execute("SELECT ruta FROM libros LIMIT 1").fetchone()[0]
    datos.excluir(conexion, [(uno, numero)])
    conexion.close()
    resumen = importar.importar([numero], opciones, ruta_bd=bd)[0]
    assert resumen.excluidos == 1 and resumen.total == 2
    conexion = datos.conectar(bd)
    datos.readmitir_todos(conexion)
    conexion.close()
    assert importar.importar([numero], opciones, ruta_bd=bd)[0].nuevos == 1

    conexion = datos.conectar(bd)
    assert datos.quitar_fuentes(conexion, [numero]) == 3
    assert datos.contar_libros(conexion) == 0 and not datos.fuentes(conexion)
    conexion.close()


def test_la_copia_de_seguridad_va_y_vuelve(tmp_path, opciones, monkeypatch):
    bd = tmp_path / "config" / "biblioteca.db"
    monkeypatch.setattr(datos, "ruta_archivo", lambda: bd)
    raiz = tmp_path / "Calibre"
    _crear_calibre(raiz, LIBROS)
    _importar_nueva(bd, datos.CALIBRE, raiz, opciones)
    documentos = tmp_path / "config" / "documentos.json"
    documentos.write_text(json.dumps({"a.epub": {"posicion": 7}}), encoding="utf-8")
    copia = tmp_path / "copia.zip"

    assert datos.copia_de_seguridad(copia, documentos) == 3
    conexion = datos.conectar(bd)
    datos.quitar_fuentes(conexion, [f.id for f in datos.fuentes(conexion)])
    conexion.close()
    documentos.write_text("{}", encoding="utf-8")

    assert datos.leer_copia(copia)["libros"] == 3
    assert datos.restaurar_copia(copia, documentos) == 3
    assert json.loads(documentos.read_text(encoding="utf-8"))["a.epub"]["posicion"] == 7


class _Configuracion:
    def __init__(self, recordados):
        self._recordados = recordados

    def libros_recordados(self):
        return list(self._recordados.items())

    def recientes(self):
        return []

    def obtener(self, clave, defecto=None):
        return defecto


class _Datos:
    def __init__(self, titulo="", posicion=0, total=0, coleccion=""):
        self.titulo, self.autor = titulo, ""
        self.posicion, self.total, self.coleccion = posicion, total, coleccion
        self.actualizado = 0


def test_cargar_junta_la_base_de_datos_con_lo_leido(tmp_path, opciones):
    raiz = tmp_path / "Calibre"
    _crear_calibre(raiz, LIBROS)
    bd = tmp_path / "biblioteca.db"
    _importar_nueva(bd, datos.CALIBRE, raiz, opciones)
    leido = os.path.join(str(raiz), "Benito Pérez Galdós", "Trafalgar (1)",
                         "Trafalgar - Benito Pérez Galdós.epub")
    configuracion = _Configuracion({leido: _Datos("Trafalgar", 50, 100, "Clase"),
                                    str(tmp_path / "suelto.epub"): _Datos("Suelto")})
    avisos = []

    libros, fuentes = biblioteca.cargar(configuracion, progreso=lambda *a: avisos.append(a),
                                        ruta_bd=bd)

    assert len(libros) == 4 and len(fuentes) == 1 and avisos
    trafalgar = next(l for l in libros if l.titulo == "Trafalgar")
    assert trafalgar.porcentaje == 50 and trafalgar.coleccion == "Clase"
    assert trafalgar.serie_legible() == "Episodios nacionales 1"
    assert len(biblioteca.filtrar(libros, "galdos episodios")) == 2
    assert len(biblioteca.filtrar(libros, "clase")) == 1
    grupos, reparto = biblioteca.indice_de_grupos(libros, "autor")
    galdos = next(clave for nombre, clave, n in grupos if nombre == "Benito Pérez Galdós")
    assert len(reparto[galdos]) == 3
    assert grupos[-1][1] == biblioteca.SIN_GRUPO, "el suelto no tiene autor"
    por_autor = biblioteca.ordenar(libros, "autor")
    assert [l.titulo for l in por_autor[:2]] == ["Trafalgar", "La Corte de Carlos IV"]


def test_html_de_calibre_a_texto():
    assert importar.html_a_texto("<div><p>Uno<br/>dos</p><p>&iquest;Tres?</p></div>") == \
        "Uno\ndos\n\n¿Tres?"
    assert importar.html_a_texto("") == ""


# ---------------------------------------------------------------------------
# 1.3.6: bibliografía sin abrir libros, varios autores, listas
# ---------------------------------------------------------------------------

def test_varios_autores_en_cada_estilo():
    from nucleo import citas

    datos = citas.Referencia(titulo="Obra", autor="Ana Pérez Gil & Luis Gil",
                             autor_orden="Pérez Gil, Ana & Luis Gil",
                             editorial="Ed", fecha="2020")
    assert datos.autores_invertidos() == ["Pérez Gil, Ana", "Gil, Luis"]
    assert datos.apellido_primero() == "Pérez Gil, Ana; Gil, Luis"
    assert datos.inicial() == "Pérez Gil, A. y Gil, L."
    assert datos.para_mla() == "Pérez Gil, Ana y Luis Gil"
    assert datos.legibles() == "Ana Pérez Gil y Luis Gil"
    tres = citas.Referencia(titulo="T", autor="A B & C D & E F")
    assert tres.para_mla() == "B, A et al."
    bib = bibliografia.a_bibtex([datos]).decode()
    assert "author = {Pérez Gil, Ana and Gil, Luis}" in bib
    ris = bibliografia.a_ris([datos]).decode()
    assert ris.count("AU  - ") == 2


def test_la_bibliografia_sale_de_la_biblioteca_sin_abrir_nada(tmp_path, opciones,
                                                              monkeypatch):
    raiz = tmp_path / "Calibre"
    _crear_calibre(raiz, LIBROS)
    bd = tmp_path / "biblioteca.db"
    _importar_nueva(bd, datos.CALIBRE, raiz, opciones)
    libros, _fuentes = biblioteca.cargar(_Configuracion({}), ruta_bd=bd)

    def no_abrir(*args, **kwargs):
        raise AssertionError("no hay que abrir ningún libro")

    monkeypatch.setattr(biblioteca, "_abrir", no_abrir)
    referencias = bibliografia.reunir(libros, object())

    trafalgar = next(r for r in referencias if r.titulo == "Trafalgar")
    assert trafalgar.ano == "1880" and trafalgar.identificador == "9788400001"
    assert trafalgar.apellido_primero() == "Pérez Galdós, Benito"


def test_una_base_de_datos_antigua_se_pone_al_dia(tmp_path):
    bd = tmp_path / "vieja.db"
    conexion = sqlite3.connect(str(bd))
    conexion.executescript(datos._ESQUEMA.replace(
        "    autores_orden TEXT NOT NULL DEFAULT '',\n", ""))
    conexion.execute("INSERT INTO meta(clave, valor) VALUES('esquema', '1')")
    conexion.commit()
    conexion.close()
    datos._PREPARADAS.discard(str(bd))

    conexion = datos.conectar(bd)
    columnas = {f[1] for f in conexion.execute("PRAGMA table_info(libros)")}
    assert "autores_orden" in columnas
    assert datos.leer_meta(conexion, "releer_calibre") == "1"
    assert datos.leer_meta(conexion, "esquema") == str(datos.VERSION_ESQUEMA)
    conexion.close()


def test_ir_a_solo_acepta_numeros_validos(aplicacion):
    import wx

    from interfaz.listas import DialogoIrA

    marco = wx.Frame(None)
    try:
        dialogo = DialogoIrA(marco, 2484, 1, "Resultados")
        dialogo._voz.decir = lambda *a, **k: None
        cerrado = []
        dialogo.EndModal = lambda codigo: cerrado.append(dialogo.numero)
        for malo in ("0", "2485", "", "12x"):
            dialogo.campo.SetValue(malo)
            dialogo._al_aceptar(None)
        assert not cerrado
        dialogo.campo.SetValue("1425")
        dialogo._al_aceptar(None)
        assert cerrado == [1425]
        dialogo.Destroy()
    finally:
        marco.Destroy()


def test_la_lista_dice_donde_estas(aplicacion):
    import wx

    from interfaz.listas import ListaVirtual

    marco = wx.Frame(None)
    try:
        lista = ListaVirtual(marco, None, "Resultados")
        lista.InsertColumn(0, "Texto")
        dicho = []
        lista._voz.decir = lambda mensaje, *a, **k: dicho.append(mensaje)
        lista.poner_filas(2484, lambda fila, columna: "fila %d" % fila)
        lista.ir_a(1424)
        lista.decir_posicion()
        lista.poner_filas(1, lambda fila, columna: "(Nada)")
        lista.decir_posicion()
        assert dicho == ["Resultados: 1425 de 2484.", "Resultados: la lista está vacía."]
    finally:
        marco.Destroy()


def test_los_trabajos_masivos_no_llenan_el_registro():
    import logging

    from nucleo import registro

    filtro = registro._SinDetalleEnTrabajosMasivos()

    def registro_de(nombre, nivel, hilo):
        entrada = logging.LogRecord(nombre, nivel, __file__, 1, "x", None, None)
        entrada.threadName = hilo
        return entrada

    assert not filtro.filter(registro_de("visor.formatos.epub", logging.INFO,
                                         "biblioteca-tarea"))
    assert filtro.filter(registro_de("visor.formatos.epub", logging.WARNING,
                                     "biblioteca-tarea"))
    assert filtro.filter(registro_de("visor.formatos.epub", logging.INFO, "MainThread"))
    assert filtro.filter(registro_de("visor.nucleo.biblioteca_importar", logging.INFO,
                                     "biblioteca-tarea"))


def test_los_avisos_de_lxml_no_son_errores(monkeypatch):
    import logging

    from lxml import etree

    from nucleo import registro

    capturados = []
    monkeypatch.setattr(etree, "use_global_python_log",
                        lambda registro_lxml: capturados.append(registro_lxml))
    registro.conectar_registro_lxml()
    assert set(capturados[0].level_map.values()) == {logging.DEBUG}


def test_el_archivo_de_caida_solo_se_queda_si_hubo_algo_de_verdad(tmp_path):
    import main

    resuelta = "Windows fatal exception: code 0x8001010d\n\nCurrent thread ...\n"
    grave = "Windows fatal exception: access violation\n\nCurrent thread ...\n"
    for contenido, queda in ((resuelta, False), (resuelta + grave, True), ("", False)):
        destino = tmp_path / "caida.txt"
        archivo = destino.open("w", encoding="utf-8")
        archivo.write(contenido)
        archivo.flush()
        main._donde_apuntar_la_caida = archivo
        main.recoger_el_vigilante()
        assert destino.exists() == queda, contenido
        if destino.exists():
            destino.unlink()


def test_ofuscar_las_fuentes_no_es_un_aviso(caplog):
    import io
    import logging

    from formatos import epub

    def con_cifrado(algoritmo):
        memoria = io.BytesIO()
        with zipfile.ZipFile(memoria, "w") as zip_:
            zip_.writestr("META-INF/encryption.xml",
                          '<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container" '
                          'xmlns:enc="http://www.w3.org/2001/04/xmlenc#"><enc:EncryptedData>'
                          '<enc:EncryptionMethod Algorithm="%s"/></enc:EncryptedData>'
                          '</encryption>' % algoritmo)
        return zipfile.ZipFile(memoria)

    with caplog.at_level(logging.INFO, logger="visor.formatos.epub"):
        epub._avisar_del_cifrado(con_cifrado("http://ns.adobe.com/pdf/enc#RC"))
        epub._avisar_del_cifrado(con_cifrado("http://www.idpf.org/2008/embedding"))
        epub._avisar_del_cifrado(con_cifrado("http://www.w3.org/2001/04/xmlenc#aes128-cbc"))
    niveles = [r.levelno for r in caplog.records if r.name == "visor.formatos.epub"]
    assert niveles == [logging.INFO, logging.INFO, logging.WARNING]
