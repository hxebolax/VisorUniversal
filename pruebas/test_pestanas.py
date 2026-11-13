# -*- coding: utf-8 -*-
"""Pruebas de las pestañas, del árbol de contenido y del informe de accesibilidad.

Lo que se comprueba aquí es lo que se rompería sin darse cuenta: que cada
pestaña se queda con su documento y su posición, que el árbol sabe decir por
dónde va la lectura, que F6 recorre las zonas que hay y no las que no, y que un
DOCX o un ODT bien hechos entregan sus imágenes descritas, sus tablas con
encabezados y sus listas de verdad.
"""

import zipfile

import pytest

from nucleo import accesibilidad
from nucleo.documento import Documento, ElementoIndice, Metadatos
from nucleo.marcas import Marca, TipoMarca

wx = pytest.importorskip("wx")


# ---------------------------------------------------------------------------
# Informe de accesibilidad
# ---------------------------------------------------------------------------

def _documento(marcas, indice=(), idioma="") -> Documento:
    """Documento de mentira con las marcas que se le den."""
    return Documento(texto="x" * 500, marcas=list(marcas), indice=list(indice),
                     metadatos=Metadatos(idioma=idioma))


def test_se_cuentan_las_imagenes_sin_describir():
    documento = _documento([
        Marca(TipoMarca.IMAGEN, 10, "Un gato", "gato.png", 1, 8),
        Marca(TipoMarca.IMAGEN, 30, "Imagen", "otra.png", 0, 8),
        Marca(TipoMarca.FIGURA, 60, "Un gráfico", "g.png", 1, 8),
    ])
    informe = accesibilidad.examinar(documento)
    assert informe.imagenes == 3
    assert informe.imagenes_descritas == 2
    assert informe.imagenes_sin_describir == 1
    assert "1 sin descripción" in accesibilidad.redactar(informe)


def test_un_documento_sin_encabezados_ni_indice_lo_dice():
    informe = accesibilidad.examinar(_documento([]))
    assert not informe.navegable
    assert "no se puede recorrer" in accesibilidad.redactar(informe)


def test_lo_que_no_hay_no_se_menciona():
    """Una lista de ceros no informa de nada y esconde lo que sí importa."""
    documento = _documento([Marca(TipoMarca.ENCABEZADO1, 0, "Uno", "", 1, 3)], idioma="es")
    frase = accesibilidad.redactar(accesibilidad.examinar(documento), "es")
    assert "1 encabezados" in frase
    assert "tablas" not in frase and "imágenes" not in frase
    assert "idioma es" in frase


def test_el_analizador_puede_poner_lo_suyo_delante():
    documento = _documento([], indice=[ElementoIndice("Uno", 0)])
    frase = accesibilidad.resumen(documento, "PDF etiquetado.")
    assert frase.startswith("PDF etiquetado.")
    assert "índice de 1 entradas" in frase


# ---------------------------------------------------------------------------
# Sesiones
# ---------------------------------------------------------------------------

def test_una_sesion_vacia_se_llama_vacia():
    from interfaz.sesion import Sesion

    sesion = Sesion(panel=None)
    assert sesion.vacia
    assert sesion.titulo() == "(Vacía)"


def test_el_rotulo_de_la_pestana_se_recorta(monkeypatch):
    from interfaz.sesion import Sesion

    sesion = Sesion(panel=None)
    sesion.documento = _documento([])
    sesion.documento.metadatos.titulo = "Informe anual de gobierno corporativo del ejercicio 2025"
    assert sesion.titulo().startswith("Informe anual")
    corto = sesion.rotulo_corto(20)
    assert len(corto) <= 20 and corto.endswith("…")


def test_los_recuentos_se_calculan_una_sola_vez():
    from interfaz.sesion import Sesion

    sesion = Sesion(panel=None)
    sesion.documento = _documento([])
    assert sesion._estadisticas is None
    primero = sesion.recuentos
    assert sesion._estadisticas is primero       # queda guardado, no se recuenta
    assert sesion.recuentos is primero
    sesion.olvidar_recuentos()
    assert sesion._estadisticas is None          # el documento ha cambiado


# ---------------------------------------------------------------------------
# Pestañas y zonas, con ventana de verdad
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ventana_con_pestanas(request):
    """Ventana principal con las pestañas y el árbol encendidos."""
    import wx as _wx

    from formatos import epub, ofimatica, pdf, texto   # noqa: F401
    from nucleo.configuracion import Configuracion
    from interfaz.ventana import VentanaPrincipal

    aplicacion = _wx.App(False)
    configuracion = Configuracion()
    configuracion.establecer("teclas_globales_activas", False)
    configuracion.establecer("primer_uso_hecho", True)
    configuracion.establecer("comprobar_actualizaciones", False)
    configuracion.establecer("usar_pestanas", True)
    configuracion.establecer("mostrar_arbol", True)
    principal = VentanaPrincipal(configuracion, "pruebas")
    # La aplicación se cuelga de la ventana a propósito: si se queda solo en
    # una variable local, Python la recoge al salir de la función y wxPython
    # deja de poder crear controles a mitad de las pruebas.
    principal._aplicacion_de_pruebas = aplicacion

    def cerrar():
        principal.Destroy()
        _wx.SafeYield()

    request.addfinalizer(cerrar)
    return principal


def test_arranca_con_una_pestana_vacia(ventana_con_pestanas):
    ventana = ventana_con_pestanas
    assert len(ventana.pestanas) == 1
    assert ventana.documento is None
    assert ventana.sesion.vacia


def test_las_tres_zonas_estan_a_la_vista(ventana_con_pestanas):
    nombres = [nombre for nombre, _ir in ventana_con_pestanas._zonas()]
    assert nombres == ["arbol", "pestanas", "documento"]


def test_cada_pestana_guarda_su_documento_y_su_posicion(ventana_con_pestanas):
    """Es la razón de ser de las pestañas: volver y encontrarlo como se dejó."""
    ventana = ventana_con_pestanas
    primera = ventana.pestanas.actual
    primera.documento = _documento([])
    primera.documento.metadatos.titulo = "Primero"
    primera.ruta = "primero.txt"
    segunda = ventana.pestanas.nueva()
    segunda.documento = _documento([])
    segunda.documento.metadatos.titulo = "Segundo"
    segunda.ruta = "segundo.txt"

    assert len(ventana.pestanas) == 2
    assert ventana.documento is segunda.documento
    ventana.pestanas.seleccionar(0)
    assert ventana.documento is primera.documento
    assert ventana.ruta_actual == "primero.txt"
    ventana.pestanas.seleccionar(1)
    assert ventana.ruta_actual == "segundo.txt"
    assert ventana.pestanas.rotulos() == ["Primero", "Segundo"]


def test_la_ultima_pestana_no_se_cierra(ventana_con_pestanas):
    """Siempre tiene que quedar un panel: es donde vive la pantalla de bienvenida."""
    ventana = ventana_con_pestanas
    while len(ventana.pestanas) > 1:
        assert ventana.pestanas.cerrar(ventana.pestanas.indice_actual)
    assert not ventana.pestanas.cerrar(0)
    assert len(ventana.pestanas) == 1


def test_apagar_las_pestanas_no_pierde_el_documento(ventana_con_pestanas):
    ventana = ventana_con_pestanas
    ventana.pestanas.actual.documento = _documento([])
    assert ventana.pestanas.cambiar_modo(False)
    assert not ventana.pestanas.con_pestanas
    assert ventana.documento is not None
    assert [n for n, _f in ventana._zonas()] == ["arbol", "documento"]
    assert ventana.pestanas.cambiar_modo(True)
    assert ventana.documento is not None
    ventana.pestanas.actual.documento = None


# ---------------------------------------------------------------------------
# Árbol de contenido
# ---------------------------------------------------------------------------

def test_el_arbol_sabe_por_donde_va_la_lectura(ventana_con_pestanas):
    ventana = ventana_con_pestanas
    documento = _documento(
        [Marca(TipoMarca.ENCABEZADO1, 0, "Uno", "", 1, 3),
         Marca(TipoMarca.ENCABEZADO1, 200, "Dos", "", 1, 3)],
        indice=[ElementoIndice("Uno", 0, hijos=[ElementoIndice("Uno bis", 100)]),
                ElementoIndice("Dos", 200)])
    ventana.panel_arbol.cargar(documento)
    assert ventana.panel_arbol._referencias == [0, 100, 200]
    ventana.panel_arbol.sincronizar(150)
    elegido = ventana.panel_arbol.arbol.GetSelection()
    assert ventana.panel_arbol.arbol.GetItemText(elegido) == "Uno bis"
    ventana.panel_arbol.sincronizar(250)
    assert ventana.panel_arbol.arbol.GetItemText(
        ventana.panel_arbol.arbol.GetSelection()) == "Dos"


def test_el_arbol_vacio_no_estorba(ventana_con_pestanas):
    ventana_con_pestanas.panel_arbol.limpiar()
    assert ventana_con_pestanas.panel_arbol._referencias == []
    ventana_con_pestanas.panel_arbol.sincronizar(10)   # no debe fallar


# ---------------------------------------------------------------------------
# Restaurar la sesión anterior sin abrirlo todo de golpe
# ---------------------------------------------------------------------------

def _esperar(condicion, segundos=15.0):
    """Atiende eventos hasta que se cumpla la condición o se agote el plazo."""
    import time

    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        wx.SafeYield()
        if condicion():
            return True
        time.sleep(0.02)
    return False


def test_al_restaurar_solo_se_abre_el_documento_de_delante(ventana_con_pestanas, tmp_path):
    """Los demás quedan reservados en su pestaña y se abren al entrar en ella."""
    ventana = ventana_con_pestanas
    while len(ventana.pestanas) > 1:
        ventana.pestanas.cerrar(ventana.pestanas.indice_actual)
    ventana.pestanas.actual.documento = None
    ventana.pestanas.actual.ruta = ""

    rutas = []
    for numero in range(3):
        archivo = tmp_path / ("libro%d.txt" % numero)
        archivo.write_text("Texto del libro %d.\n" % numero, encoding="utf-8")
        rutas.append(str(archivo))
    configuracion = ventana.configuracion
    recientes = configuracion.recientes()
    configuracion.guardar = lambda: None          # la prueba no escribe en disco
    configuracion.establecer("restaurar_documentos", True)
    configuracion.establecer("documentos_abiertos", rutas)
    configuracion.establecer("documento_activo", 1)
    try:
        assert ventana.restaurar_documentos_abiertos()
        assert _esperar(lambda: not ventana._cargando and ventana.documento is not None)

        sesiones = ventana.pestanas.sesiones
        assert len(sesiones) == 3
        assert ventana.pestanas.indice_actual == 1
        assert sesiones[1].documento is not None
        # Las otras dos tienen su documento reservado, sin abrir.
        assert sesiones[0].documento is None and sesiones[0].ruta_pendiente == rutas[0]
        assert sesiones[2].documento is None and sesiones[2].ruta_pendiente == rutas[2]
        assert not sesiones[0].vacia
        assert ventana.pestanas.rotulos()[0] == "libro0"

        # Al cerrar, la sesión se apunta entera y con la misma de delante.
        ventana.anotar_documentos_abiertos()
        assert configuracion.obtener("documentos_abiertos") == rutas
        assert configuracion.obtener("documento_activo") == 1

        # Entrar en una pestaña reservada abre su documento.
        ventana.pestanas.seleccionar(2)
        assert _esperar(lambda: sesiones[2].documento is not None and not ventana._cargando)
        assert sesiones[2].ruta_pendiente == ""
        assert sesiones[0].documento is None            # esta sigue esperando

        # Pedir desde fuera un documento reservado lleva a su pestaña y lo abre.
        assert ventana._ir_a_lo_ya_abierto(rutas[0])
        assert _esperar(lambda: sesiones[0].documento is not None and not ventana._cargando)
        assert ventana.pestanas.indice_actual == 0
    finally:
        _esperar(lambda: not ventana._cargando, 5)
        while len(ventana.pestanas) > 1:
            ventana.pestanas.cerrar(ventana.pestanas.indice_actual)
        ventana.pestanas.actual.documento = None
        ventana.pestanas.actual.ruta = ""
        configuracion.establecer("documentos_abiertos", [])
        configuracion.establecer("restaurar_documentos", False)
        configuracion.establecer("documentos_recientes", recientes)
        del configuracion.guardar


def test_un_documento_reservado_que_ya_no_existe_cierra_su_pestana(
        ventana_con_pestanas, tmp_path):
    """Si se borró mientras tanto, su pestaña se va sin dejar un hueco."""
    ventana = ventana_con_pestanas
    while len(ventana.pestanas) > 1:
        ventana.pestanas.cerrar(ventana.pestanas.indice_actual)
    ventana.pestanas.actual.documento = None
    ventana.pestanas.actual.ruta = ""
    rutas = []
    for numero in range(2):
        archivo = tmp_path / ("otro%d.txt" % numero)
        archivo.write_text("Hola %d.\n" % numero, encoding="utf-8")
        rutas.append(str(archivo))
    configuracion = ventana.configuracion
    recientes = configuracion.recientes()
    configuracion.guardar = lambda: None          # la prueba no escribe en disco
    configuracion.establecer("restaurar_documentos", True)
    configuracion.establecer("documentos_abiertos", rutas)
    configuracion.establecer("documento_activo", 0)
    try:
        assert ventana.restaurar_documentos_abiertos()
        assert _esperar(lambda: not ventana._cargando and ventana.documento is not None)
        assert len(ventana.pestanas) == 2
        (tmp_path / "otro1.txt").unlink()
        ventana.pestanas.seleccionar(1)
        assert _esperar(lambda: len(ventana.pestanas) == 1)
    finally:
        _esperar(lambda: not ventana._cargando, 5)
        while len(ventana.pestanas) > 1:
            ventana.pestanas.cerrar(ventana.pestanas.indice_actual)
        ventana.pestanas.actual.documento = None
        ventana.pestanas.actual.ruta = ""
        configuracion.establecer("documentos_abiertos", [])
        configuracion.establecer("restaurar_documentos", False)
        configuracion.establecer("documentos_recientes", recientes)
        del configuracion.guardar


# ---------------------------------------------------------------------------
# DOCX y ODT: lo que los hace accesibles
# ---------------------------------------------------------------------------

_W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
_R = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
_WP = 'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"'
_A = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'


@pytest.fixture
def docx(carpeta):
    """Un DOCX pequeño con todo lo que su comprobador de accesibilidad pide."""
    documento = f'''<?xml version="1.0" encoding="UTF-8"?>
<w:document {_W} {_R} {_WP} {_A}>
 <w:body>
  <w:p><w:pPr><w:pStyle w:val="Ttulo1"/></w:pPr><w:r><w:t>Título</w:t></w:r></w:p>
  <w:p><w:hyperlink r:id="rId5"><w:r><w:t>un enlace</w:t></w:r></w:hyperlink></w:p>
  <w:p><w:r><w:drawing><wp:inline><wp:docPr id="1" name="i" descr="Un gráfico"/>
    <a:blip r:embed="rId6"/></wp:inline></w:drawing></w:r></w:p>
  <w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>
    <w:r><w:t>Viñeta</w:t></w:r></w:p>
  <w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="2"/></w:numPr></w:pPr>
    <w:r><w:t>Paso uno</w:t></w:r></w:p>
  <w:tbl>
   <w:tr><w:trPr><w:tblHeader/></w:trPr>
     <w:tc><w:p><w:r><w:t>Cabecera</w:t></w:r></w:p></w:tc></w:tr>
   <w:tr><w:tc><w:p><w:r><w:t>Dato</w:t></w:r></w:p></w:tc></w:tr>
  </w:tbl>
 </w:body></w:document>'''
    relaciones = '''<?xml version="1.0"?><Relationships
 xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Id="rId5" Type="t/hyperlink" Target="https://ejemplo.org/" TargetMode="External"/>
 <Relationship Id="rId6" Type="t/image" Target="media/i.png"/></Relationships>'''
    numeracion = f'''<?xml version="1.0"?><w:numbering {_W}>
 <w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0"><w:numFmt w:val="bullet"/></w:lvl>
 </w:abstractNum>
 <w:abstractNum w:abstractNumId="1"><w:lvl w:ilvl="0"><w:numFmt w:val="decimal"/></w:lvl>
 </w:abstractNum>
 <w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
 <w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num></w:numbering>'''
    ruta = carpeta / "prueba.docx"
    with zipfile.ZipFile(ruta, "w") as archivo:
        archivo.writestr("word/document.xml", documento)
        archivo.writestr("word/_rels/document.xml.rels", relaciones)
        archivo.writestr("word/numbering.xml", numeracion)
        archivo.writestr("word/media/i.png", b"\x89PNG")
    return ruta


def test_el_docx_entrega_su_estructura_accesible(docx):
    from formatos import base, ofimatica   # noqa: F401

    documento = base.analizar(docx, base.OpcionesAnalisis())
    marcas = documento.marcas
    assert len(marcas.encabezados) == 1
    # El enlace lleva su destino: antes se perdía y quedaba texto suelto.
    enlaces = marcas.grupo(TipoMarca.ENLACE).marcas
    assert [m.referencia for m in enlaces] == ["https://ejemplo.org/"]
    # La imagen, con el texto alternativo que puso el autor.
    imagenes = marcas.grupo(TipoMarca.IMAGEN).marcas
    assert imagenes and imagenes[0].texto == "Un gráfico"
    assert imagenes[0].nivel == 1                 # queda constancia de que sí lo tenía
    # Dos numeraciones distintas son dos listas, no una.
    assert marcas.cantidad(TipoMarca.LISTA) == 2
    assert "1. Paso uno" in documento.texto
    assert "• Viñeta" in documento.texto


def test_el_docx_conserva_la_fila_de_encabezados(docx):
    from formatos import base, ofimatica   # noqa: F401
    from nucleo import html_elementos

    documento = base.analizar(docx, base.OpcionesAnalisis())
    tabla = documento.marcas.grupo(TipoMarca.TABLA)[0]
    assert 'scope="col"' in html_elementos.cuerpo_html(documento, tabla)


@pytest.fixture
def odt(carpeta):
    """Un ODT con imagen descrita, tabla con encabezado, listas y nota al pie."""
    ns = ('xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
          'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
          'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
          'xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" '
          'xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0" '
          'xmlns:xlink="http://www.w3.org/1999/xlink"')
    contenido = f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document-content {ns}><office:body><office:text>
 <text:h text:outline-level="1">Título</text:h>
 <text:p>Con una nota<text:note><text:note-citation>1</text:note-citation>
  <text:note-body><text:p>El texto de la nota.</text:p></text:note-body></text:note>.</text:p>
 <text:p><draw:frame draw:name="i"><svg:desc>Un gráfico</svg:desc>
  <draw:image xlink:href="Pictures/i.png"/></draw:frame></text:p>
 <text:list text:style-name="ListaNumbering">
  <text:list-item><text:p>Paso uno</text:p></text:list-item></text:list>
 <table:table><table:table-header-rows><table:table-row>
   <table:table-cell><text:p>Cabecera</text:p></table:table-cell>
  </table:table-row></table:table-header-rows>
  <table:table-row><table:table-cell><text:p>Dato</text:p></table:table-cell>
  </table:table-row></table:table>
</office:text></office:body></office:document-content>'''
    ruta = carpeta / "prueba.odt"
    with zipfile.ZipFile(ruta, "w") as archivo:
        archivo.writestr("content.xml", contenido)
    return ruta


def test_el_odt_entrega_su_estructura_accesible(odt):
    from formatos import base, ofimatica   # noqa: F401

    documento = base.analizar(odt, base.OpcionesAnalisis())
    marcas = documento.marcas
    assert len(marcas.encabezados) == 1
    imagenes = marcas.grupo(TipoMarca.IMAGEN).marcas
    assert imagenes and imagenes[0].texto == "Un gráfico"
    assert marcas.cantidad(TipoMarca.NOTA_PIE) == 1
    # La nota va detrás del párrafo, no en mitad de la frase.
    assert "Con una nota1.\nEl texto de la nota." in documento.texto
    assert "1. Paso uno" in documento.texto


def test_el_odt_conserva_la_fila_de_encabezados(odt):
    from formatos import base, ofimatica   # noqa: F401
    from nucleo import html_elementos

    documento = base.analizar(odt, base.OpcionesAnalisis())
    tabla = documento.marcas.grupo(TipoMarca.TABLA)[0]
    assert 'scope="col"' in html_elementos.cuerpo_html(documento, tabla)
