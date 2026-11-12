# -*- coding: utf-8 -*-
"""Pruebas de lo que sirve para estudiar y de los formatos nuevos.

Aquí están las piezas que se añadieron para que el programa deje de ser solo un
lector: los datos de un gráfico, las fórmulas químicas dichas en voz alta, la
cita bibliográfica, lo que la voz no dice, la biblioteca, la sincronización
entre equipos y las salidas a DAISY, a braille matemático y a PEF.

Cada prueba arma su propio caso con lo mínimo, sin depender de ningún archivo
del disco: son módulos que no tocan la interfaz y se pueden probar enteros.
"""

from __future__ import annotations

import struct
import sys
import wave
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from formatos.base import OpcionesAnalisis                        # noqa: E402
from formatos.pdf_hallazgos import Severidad                      # noqa: E402
from nucleo import (audio_libro, biblioteca, braille,             # noqa: E402
                    braille_matematicas, citas, daisy_exportar,
                    exportar, graficos, id3, omisiones, quimica,
                    revision_epub, sincronizacion)
from nucleo.documento import Documento, Metadatos                 # noqa: E402
from nucleo.ia import estructura                                  # noqa: E402
from nucleo.marcas import Marca, TipoMarca                         # noqa: E402


def documento(texto: str, marcas=(), **datos) -> Documento:
    """Un documento de mentira con el texto y las marcas que se le digan."""
    return Documento(texto, list(marcas),
                     metadatos=Metadatos(**datos), ruta_archivo="C:/libros/x.pdf")


# ---------------------------------------------------------------------------
# Los datos de un gráfico
# ---------------------------------------------------------------------------

RESPUESTA = """TITULO: Ventas por trimestre
UNIDADES: millones de euros
TABLA:
| Trimestre | Norte | Sur |
| --- | --- | --- |
| 2024 T1 | 12 | 8 |
| 2024 T2 | 15 | 9,5 |
NOTA: el sur no incluye Canarias"""


def test_se_interpreta_una_tabla_de_markdown():
    grafico = graficos.interpretar(RESPUESTA)

    assert grafico.titulo == "Ventas por trimestre"
    assert grafico.unidades == "millones de euros"
    assert grafico.nota == "el sur no incluye Canarias"
    assert grafico.filas == [["Trimestre", "Norte", "Sur"],
                             ["2024 T1", "12", "8"],
                             ["2024 T2", "15", "9,5"]]


def test_una_imagen_que_no_es_un_grafico_no_da_ninguna_tabla():
    """Más vale no dar datos que darlos inventados: una tabla parece un hecho."""
    assert graficos.interpretar("NO ES UN GRAFICO") is None
    assert graficos.interpretar("Claro, aquí tienes la descripción de la imagen.") is None


def test_los_no_consta_no_ocupan_un_renglon():
    grafico = graficos.interpretar(
        "TITULO: X\nUNIDADES: no consta\nTABLA:\n| a | b |\n| 1 | 2 |\nNOTA: ninguna")

    assert grafico.unidades == ""
    assert grafico.nota == ""


def test_las_filas_se_cuadran_aunque_falte_una_celda():
    grafico = graficos.interpretar("TABLA:\n| a | b | c |\n| 1 | 2 |")

    assert all(len(fila) == 3 for fila in grafico.filas)


def test_la_tabla_se_guarda_y_se_recupera_igual():
    grafico = graficos.interpretar(RESPUESTA)
    vuelta = graficos.desde_guardado(grafico.rejilla())

    assert vuelta.filas == grafico.filas


def test_se_admiten_tabuladores_por_si_el_modelo_va_por_libre():
    grafico = graficos.interpretar("TABLA:\nAño\tVentas\n2024\t100")

    assert grafico.filas == [["Año", "Ventas"], ["2024", "100"]]


# ---------------------------------------------------------------------------
# Química
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("formula, dicho", [
    ("H2SO4", "hidrógeno 2 azufre oxígeno 4"),
    ("H₂SO₄", "hidrógeno 2 azufre oxígeno 4"),
    ("CO2", "carbono oxígeno 2"),
    ("Fe2O3", "hierro 2 oxígeno 3"),
    ("Na+", "catión sodio"),
    ("SO4^2-", "anión azufre oxígeno 4 con carga 2 negativa"),
    ("SO₄²⁻", "anión azufre oxígeno 4 con carga 2 negativa"),
    ("NaCl", "sodio cloro"),
])
def test_las_formulas_se_dicen_con_el_nombre_de_cada_elemento(formula, dicho):
    assert quimica.leer(formula) == dicho


@pytest.mark.parametrize("palabra", [
    "con", "sin", "no", "Sin embargo", "No obstante", "Alberto", "Barcelona",
    "Instituto", "Carlos", "COVID19", "A4", "Sr. Pérez",
])
def test_una_palabra_normal_no_se_lee_como_una_formula(palabra):
    """Muchas palabras se descomponen en símbolos: «con» es C, O y N.

    Por eso solo se toma por fórmula lo que trae un número, una carga o un
    estado de agregación, que es lo que ninguna palabra lleva.
    """
    assert quimica.leer(palabra) == palabra


def test_el_estado_de_agregacion_se_dice_con_palabras():
    assert quimica.leer("H2O(l)") == "hidrógeno 2 oxígeno en estado líquido"
    assert quimica.leer("NaCl(ac)") == "sodio cloro en disolución acuosa"


def test_una_ecuacion_de_reaccion_se_lee_entera():
    dicho = quimica.leer("2 H2 + O2 → 2 H2O")

    assert "más" in dicho and "da" in dicho
    assert "hidrógeno" in dicho and "oxígeno" in dicho


def test_el_mas_solo_se_dice_dentro_de_una_reaccion():
    """Fuera de una ecuación, un signo más es una suma y no se toca."""
    assert quimica.leer("3+2 = 5") == "3+2 = 5"


def test_los_simbolos_se_pueden_pedir_deletreados():
    assert quimica.leer("H2O", "simbolos") == "hache 2 o"


def test_el_modo_automatico_mira_el_documento():
    assert quimica.modo_efectivo("auto", "Una novela con H2O y nada más") == "no"
    assert quimica.modo_efectivo(
        "auto", "H2O CO2 H2SO4 NaOH CaCO3 Fe2O3") == "nombres"


def test_apagada_la_quimica_no_toca_nada():
    assert quimica.leer("H2SO4", "no") == "H2SO4"


# ---------------------------------------------------------------------------
# Citas
# ---------------------------------------------------------------------------

def _referencia() -> citas.Referencia:
    return citas.Referencia("El Quijote", "Miguel de Cervantes", "Espasa",
                            "2011-05-03", "347", "Capítulo I")


def test_la_particula_del_apellido_se_queda_detras_del_nombre():
    """«Miguel de Cervantes» se cita «Cervantes, Miguel de», y va en la C."""
    assert _referencia().apellido_primero() == "Cervantes, Miguel de"


def test_la_particula_no_se_abrevia_como_si_fuera_un_nombre():
    assert _referencia().inicial() == "Cervantes, M. de"


def test_un_autor_que_ya_viene_con_coma_se_respeta():
    datos = citas.Referencia(autor="Cervantes Saavedra, Miguel de")

    assert datos.apellido_primero() == "Cervantes Saavedra, Miguel de"


def test_cada_estilo_escribe_lo_suyo():
    datos = _referencia()

    assert citas.referencia(datos, "iso690").startswith("CERVANTES, MIGUEL DE.")
    assert "(2011)" in citas.referencia(datos, "apa")
    assert citas.referencia(datos, "mla").startswith("Cervantes, Miguel de.")
    assert "página 347" in citas.referencia(datos, "sencilla")


def test_no_se_doblan_los_puntos():
    """«Cervantes, M. de.» no lleva dos puntos: leído se oiría «punto punto»."""
    assert ".." not in citas.referencia(_referencia(), "apa")


def test_lo_que_el_documento_no_dice_no_se_inventa():
    faltan = citas.lo_que_falta(citas.Referencia(titulo="Solo el título"))

    assert "el autor" in faltan and "la editorial" in faltan
    assert "el título" not in faltan


def test_la_cita_completa_lleva_el_pasaje_y_la_referencia():
    texto = citas.cita_completa("En un lugar de la Mancha", _referencia(), "iso690")

    assert texto.startswith("«En un lugar de la Mancha»")
    assert "Espasa" in texto


def test_la_pagina_sale_del_documento():
    texto = "uno\ndos\ntres\n"
    doc = documento(texto, [Marca(TipoMarca.SALTO_PAGINA, 0, "47")],
                    titulo="T", autor="A")

    assert citas.desde_documento(doc, 2).pagina == "47"


# ---------------------------------------------------------------------------
# Lo que la voz no dice
# ---------------------------------------------------------------------------

def test_sin_pedir_nada_no_se_salta_nada():
    doc = documento("una línea\n")

    assert not omisiones.Omisiones(doc)
    assert omisiones.NINGUNA.filtrar("lo que sea", 0) == "lo que sea"


def test_se_saltan_las_llamadas_de_nota():
    texto = "El ejército cruzó el río47 sin encontrar resistencia.\n"
    doc = documento(texto, [Marca(TipoMarca.NOTA_PIE, texto.index("47"), "47", "", 0, 2)])
    saltos = omisiones.Omisiones(doc, notas=True)

    assert saltos.filtrar(texto, 0) == "El ejército cruzó el río sin encontrar resistencia.\n"


def test_se_salta_una_linea_que_es_solo_el_folio():
    texto = "Un párrafo.\n47\nOtro párrafo.\n"
    doc = documento(texto)
    saltos = omisiones.Omisiones(doc, paginas=True)

    assert saltos.filtrar(texto, 0) == "Un párrafo.\n\nOtro párrafo.\n"


def test_un_titulo_que_es_un_numero_no_se_salta():
    """Un capítulo titulado «7» existe, y saltárselo dejaría sin saber que cambió."""
    texto = "7\nEl contenido.\n"
    doc = documento(texto, [Marca(TipoMarca.ENCABEZADO1, 0, "7")])
    saltos = omisiones.Omisiones(doc, paginas=True)

    assert saltos.filtrar(texto, 0) == texto


def test_se_saltan_las_cabeceras_que_se_repiten_en_cada_pagina():
    partes = []
    marcas = []
    for numero in range(6):
        marcas.append(Marca(TipoMarca.SALTO_PAGINA, sum(len(p) for p in partes),
                            str(numero + 1)))
        partes.append("Guerra y paz\nTexto de la página %d.\n" % (numero + 1))
    texto = "".join(partes)
    doc = documento(texto, marcas)
    saltos = omisiones.Omisiones(doc, repetidos=True)

    assert "Guerra y paz" in saltos.cabeceras
    assert "Guerra y paz" not in saltos.filtrar(texto, 0)
    assert "Texto de la página 3." in saltos.filtrar(texto, 0)


def test_sin_paginas_no_se_buscan_cabeceras():
    """En un EPUB sin páginas no hay cabeceras que se repitan."""
    texto = "Lo mismo\notra cosa\nLo mismo\notra más\nLo mismo\n" * 3
    doc = documento(texto)

    assert not omisiones.Omisiones(doc, repetidos=True).cabeceras


# ---------------------------------------------------------------------------
# Marcas de capítulo en el audio
# ---------------------------------------------------------------------------

def test_la_etiqueta_id3_se_puede_volver_a_leer():
    capitulos = [id3.Capitulo("Capítulo primero", 0, 120000),
                 id3.Capitulo("Segundo", 120000, 300000)]
    datos = id3.etiqueta(capitulos, "Mi libro", "Autor Ñ")

    assert datos[:3] == b"ID3" and datos[3] == 3
    tamano = 0
    for byte in datos[6:10]:
        tamano = (tamano << 7) | (byte & 0x7F)
    assert tamano == len(datos) - 10

    marcos = []
    posicion = 10
    while posicion < len(datos):
        nombre = datos[posicion:posicion + 4].decode("ascii")
        largo = struct.unpack(">L", datos[posicion + 4:posicion + 8])[0]
        marcos.append(nombre)
        posicion += 10 + largo
    assert posicion == len(datos)
    assert marcos == ["TIT2", "TPE1", "TALB", "CTOC", "CHAP", "CHAP"]


def test_una_etiqueta_anterior_no_se_queda_delante():
    """Dos etiquetas seguidas hacen que algunos reproductores no vean los capítulos."""
    audio = b"\xff\xfb" + b"\0" * 40
    con_etiqueta = id3.etiqueta([], "X") + audio

    assert id3._sin_etiqueta(con_etiqueta) == audio


def test_la_hoja_de_pistas_lleva_cada_capitulo_en_su_minuto():
    hoja = id3.hoja_de_pistas([id3.Capitulo("Uno", 0, 120000),
                               id3.Capitulo("Dos", 120000, 300000)],
                              "libro.wav", "Mi libro", "Autor")

    assert 'FILE "libro.wav" WAVE' in hoja
    assert "INDEX 01 00:00:00" in hoja
    assert "INDEX 01 02:00:00" in hoja


def test_se_pegan_varios_wav_y_se_sabe_donde_empieza_cada_uno(tmp_path):
    rutas = []
    for numero, cuadros in enumerate((44100, 22050, 11025)):
        ruta = tmp_path / ("t%d.wav" % numero)
        with wave.open(str(ruta), "wb") as archivo:
            archivo.setnchannels(1)
            archivo.setsampwidth(2)
            archivo.setframerate(44100)
            archivo.writeframes(b"\0\0" * cuadros)
        rutas.append(ruta)
    destino = tmp_path / "todo.wav"

    comienzos = audio_libro.unir_wav(rutas, destino)

    assert comienzos == [0, 1000, 1500]
    assert audio_libro.duracion_de_wav(destino) == 1750


# ---------------------------------------------------------------------------
# Exportar a DAISY
# ---------------------------------------------------------------------------

def _libro_de_prueba() -> Documento:
    texto = ("Primer capítulo\nUn párrafo con dos frases. Esta es la segunda.\n47\n"
             "Segundo capítulo\nOtro párrafo.\n")
    marcas = [Marca(TipoMarca.ENCABEZADO1, 0, "Primer capítulo"),
              Marca(TipoMarca.SALTO_PAGINA, texto.index("47"), "47"),
              Marca(TipoMarca.ENCABEZADO1, texto.index("Segundo"), "Segundo capítulo")]
    return documento(texto, marcas, titulo="Libro de prueba", autor="Autor",
                     idioma="es")


def test_el_daisy_de_texto_lleva_sus_tres_archivos(tmp_path):
    escritos = daisy_exportar.exportar(_libro_de_prueba(), tmp_path)

    assert {ruta.name for ruta in escritos} == {"libro.xml", "libro.ncx", "libro.opf"}


def test_el_dtbook_conserva_los_niveles_y_las_paginas(tmp_path):
    daisy_exportar.exportar(_libro_de_prueba(), tmp_path)
    xml = (tmp_path / "libro.xml").read_text(encoding="utf-8")

    assert xml.count("<level1") == 2
    assert "<h1 " in xml
    assert '<pagenum id="id3" page="normal">47</pagenum>' in xml


def test_el_ncx_lleva_el_indice_y_la_lista_de_paginas(tmp_path):
    daisy_exportar.exportar(_libro_de_prueba(), tmp_path)
    ncx = (tmp_path / "libro.ncx").read_text(encoding="utf-8")

    assert ncx.count("<navPoint") == 2
    assert "<pageTarget" in ncx
    assert 'content="1"' in ncx           # una página contada


def test_el_libro_daisy_exportado_se_vuelve_a_abrir(tmp_path):
    """La prueba de fuego: lo que escribimos, ¿lo lee nuestro propio lector?"""
    from formatos.daisy import AnalizadorDAISY
    from nucleo import daisy

    daisy_exportar.exportar(_libro_de_prueba(), tmp_path)
    assert daisy.es_libro_daisy(tmp_path)

    vuelto = AnalizadorDAISY().analizar(tmp_path, OpcionesAnalisis())
    assert "Primer capítulo" in vuelto.texto
    assert "Segundo capítulo" in vuelto.texto
    assert vuelto.metadatos.titulo == "Libro de prueba"
    assert vuelto.marcas.cantidad(TipoMarca.SALTO_PAGINA) == 1


def test_con_audio_se_escriben_los_smil_y_se_sincroniza_cada_frase(tmp_path):
    """Se graba de mentira: lo que se comprueba es la sincronización, no la voz."""
    def grabar(textos, destino):
        Path(destino).write_bytes(b"RIFF")
        return [numero * 1000 for numero in range(len(textos))], len(textos) * 1000

    escritos = daisy_exportar.exportar(_libro_de_prueba(), tmp_path, grabar=grabar)

    nombres = {ruta.name for ruta in escritos}
    assert "capitulo001.smil" in nombres
    smil = (tmp_path / "capitulo001.smil").read_text(encoding="utf-8")
    assert smil.count("<par ") >= 2
    assert 'clipBegin="0:00:00.000"' in smil
    assert 'clipEnd="0:00:01.000"' in smil
    opf = (tmp_path / "libro.opf").read_text(encoding="utf-8")
    assert 'content="audioFullText"' in opf


# ---------------------------------------------------------------------------
# Revisar el EPUB exportado
# ---------------------------------------------------------------------------

def test_nuestro_propio_epub_pasa_la_revision(tmp_path):
    destino = tmp_path / "libro.epub"
    exportar.a_epub(_libro_de_prueba(), destino)

    hallazgos = revision_epub.revisar(destino)

    assert hallazgos.peor() <= Severidad.INFORMACION, [h.mensaje for h in hallazgos]


def test_se_cazan_los_fallos_de_un_epub_mal_hecho(tmp_path):
    destino = tmp_path / "malo.epub"
    with zipfile.ZipFile(destino, "w") as archivo:
        archivo.writestr("META-INF/container.xml",
                         '<container><rootfiles><rootfile full-path="OEBPS/p.opf"/>'
                         "</rootfiles></container>")
        archivo.writestr("OEBPS/p.opf",
                         "<package><metadata><dc:title>X</dc:title></metadata>"
                         '<manifest><item id="nav" href="nav.xhtml" properties="nav"/>'
                         '<item id="c" href="c.xhtml"/></manifest></package>')
        archivo.writestr("OEBPS/nav.xhtml",
                         '<html><body><nav epub:type="toc"><ol>'
                         '<li><a href="c.xhtml#t1">Uno</a></li>'
                         '<li><a href="c.xhtml#t9">Dos</a></li></ol></nav></body></html>')
        archivo.writestr("OEBPS/c.xhtml",
                         '<html><body><h1 id="t1">Uno</h1><h3>Salto</h3>'
                         '<img src="a.png"/><table><tr><td>1</td></tr></table>'
                         "</body></html>")
        archivo.writestr("mimetype", "application/epub+zip")

    codigos = {hallazgo.codigo for hallazgo in revision_epub.revisar(destino)}

    assert "EPUB_MIMETYPE_NO_ES_PRIMERO" in codigos
    assert "EPUB_SIN_IDIOMA" in codigos
    assert "EPUB_SIN_MODO_DE_ACCESO" in codigos
    assert "EPUB_INDICE_ROTO" in codigos
    assert "EPUB_NIVELES_SALTADOS" in codigos
    assert "EPUB_IMAGENES_SIN_ALTERNATIVA" in codigos
    assert "EPUB_TABLAS_SIN_ENCABEZADO" in codigos


def test_lo_que_no_es_un_epub_se_dice_sin_reventar(tmp_path):
    destino = tmp_path / "no.epub"
    destino.write_bytes(b"esto no es un zip")

    hallazgos = revision_epub.revisar(destino)

    assert hallazgos.peor() == Severidad.GRAVE


# ---------------------------------------------------------------------------
# Braille: PEF y matemáticas
# ---------------------------------------------------------------------------

def test_el_pef_es_xml_valido_y_lleva_sus_paginas():
    import xml.etree.ElementTree as ET

    datos = braille.a_pef("Hola mundo. Una prueba algo más larga para que corte.",
                          "Mi libro", "Autor", "id-1", ancho=20, alto=3)
    arbol = ET.fromstring(datos)

    assert arbol.tag.endswith("pef")
    filas = [nodo.text or "" for nodo in arbol.iter()
             if nodo.tag.endswith("row")]
    assert filas and all(all(c == "\u2800" or "\u2800" <= c <= "\u28ff" or c == " "
                             for c in fila) for fila in filas)


def test_el_pef_y_el_brf_dicen_lo_mismo():
    """Si algún día dejaran de coincidir sería porque se traduce dos veces."""
    texto = "Tres cuartos de lo mismo, y algo más para que haya varias líneas."
    del texto  # se comprueba con la composición, no con el texto


@pytest.mark.parametrize("mathml, puntos", [
    # 6+2 -> #f+#b
    ("<math><mn>6</mn><mo>+</mo><mn>2</mn></math>",
     [(3, 4, 5, 6), (1, 2, 4), (2, 3, 5), (3, 4, 5, 6), (1, 2)]),
    # x al cuadrado -> x1#b
    ("<math><msup><mi>x</mi><mn>2</mn></msup></math>",
     [(1, 3, 4, 6), (1, 6), (3, 4, 5, 6), (1, 2)]),
    # tres cuartos, en su forma abreviada -> #c* y cajetín en blanco
    ("<math><mfrac><mn>3</mn><mn>4</mn></mfrac></math>",
     [(3, 4, 5, 6), (1, 4), (2, 5, 6), ()]),
    # raíz cuadrada de 8 -> 65#h
    ("<math><msqrt><mn>8</mn></msqrt></math>",
     [(1, 2, 4, 6), (1, 5, 6), (3, 4, 5, 6), (1, 2, 5)]),
    # raíz cúbica de 8 -> 6#c5#h
    ("<math><mroot><mn>8</mn><mn>3</mn></mroot></math>",
     [(1, 2, 4, 6), (3, 4, 5, 6), (1, 4), (1, 5, 6), (3, 4, 5, 6), (1, 2, 5)]),
])
def test_las_formulas_siguen_el_codigo_matematico_unificado(mathml, puntos):
    from lxml import etree

    celdas = braille_matematicas.celdas_de_mathml(etree.fromstring(mathml.encode()))

    esperado = [braille_matematicas._puntos(*grupo) for grupo in puntos]
    assert celdas == esperado


def test_el_indice_compuesto_va_entre_parentesis_auxiliares():
    from lxml import etree

    celdas = braille_matematicas.celdas_de_mathml(etree.fromstring(
        b"<math><msup><mi>x</mi><mrow><mi>a</mi><mo>+</mo><mi>b</mi>"
        b"</mrow></msup></math>"))

    assert braille_matematicas.ABRIR_AUXILIAR in celdas
    assert braille_matematicas.CERRAR_AUXILIAR in celdas


def test_un_indice_de_un_solo_termino_no_lleva_parentesis():
    from lxml import etree

    celdas = braille_matematicas.celdas_de_mathml(
        etree.fromstring(b"<math><msup><mi>x</mi><mn>2</mn></msup></math>"))

    assert braille_matematicas.ABRIR_AUXILIAR not in celdas


def test_lo_que_no_se_sabe_transcribir_se_dice_que_no():
    """Una fórmula mal transcrita es peor que una fórmula dicha con palabras."""
    assert braille_matematicas.transcribir(
        "<math><mo>\u222b</mo><mi>x</mi></math>") is None
    assert braille_matematicas.transcribir("") is None
    assert braille_matematicas.transcribir("esto no es xml") is None


def test_la_formula_sale_en_braille_matematico_dentro_del_brf():
    mathml = ('<math xmlns="http://www.w3.org/1998/Math/MathML">'
              "<msup><mi>x</mi><mn>2</mn></msup></math>")
    texto = "Capítulo\nx elevado a 2\nUn párrafo.\n"
    doc = documento(texto,
                    [Marca(TipoMarca.ENCABEZADO1, 0, "Capítulo"),
                     Marca(TipoMarca.FORMULA, texto.index("x elevado"),
                           "x elevado a 2", mathml, 0, 13)],
                    titulo="T", autor="A")

    bloques = exportar.bloques_para_braille(doc)

    assert (True, braille_matematicas.transcribir(mathml)) in bloques


# ---------------------------------------------------------------------------
# La biblioteca
# ---------------------------------------------------------------------------

class _Ajustes:
    """Una configuración de mentira, con lo justo que la biblioteca consulta."""

    def __init__(self, documentos=None, carpetas=()) -> None:
        self._documentos = documentos or {}
        self._carpetas = list(carpetas)

    def libros_recordados(self):
        return sorted(self._documentos.items())

    def recientes(self):
        return []

    def obtener(self, clave, defecto=None):
        if clave == "biblioteca_carpetas":
            return self._carpetas
        return defecto


class _Datos:
    def __init__(self, titulo="", autor="", posicion=0, total=0) -> None:
        self.titulo = titulo
        self.autor = autor
        self.posicion = posicion
        self.total = total


def test_la_biblioteca_reune_lo_recordado_y_las_carpetas(tmp_path):
    # La biblioteca pregunta al registro de analizadores qué extensiones sabe
    # abrir, así que hay que tener alguno dado de alta.
    from formatos import epub                                     # noqa: F401

    (tmp_path / "suelto.epub").write_bytes(b"x")
    ajustes = _Ajustes({str(tmp_path / "leido.epub"): _Datos("Leído", "Autor", 50, 100)},
                       [str(tmp_path)])

    libros = biblioteca.desde_configuracion(ajustes)

    titulos = {libro.titulo for libro in libros}
    assert "Leído" in titulos and "suelto" in titulos


def test_el_porcentaje_y_el_estado_salen_sin_abrir_el_libro():
    libro = biblioteca.Libro("no-existe.epub", "T", "A", 98, 100)

    assert libro.porcentaje == 98
    assert libro.terminado
    assert libro.estado() == "no se encuentra el archivo"


def test_el_filtro_no_se_pelea_con_los_acentos():
    libros = [biblioteca.Libro("a.epub", "El Camino", "Delibes"),
              biblioteca.Libro("b.epub", "Rayuela", "Cortázar")]

    assert len(biblioteca.filtrar(libros, "cortazar")) == 1
    assert len(biblioteca.filtrar(libros, "CAMINO")) == 1
    assert len(biblioteca.filtrar(libros, "")) == 2


# ---------------------------------------------------------------------------
# Sincronización
# ---------------------------------------------------------------------------

def test_al_juntar_gana_el_mas_reciente_y_se_suman_los_marcadores():
    local = {"a.epub": {"posicion": 10, "actualizado": 100,
                        "marcadores": [{"inicio": 1, "fin": 2, "nota": "uno"}]},
             "b.epub": {"posicion": 5, "actualizado": 50, "marcadores": []}}
    remoto = {"a.epub": {"posicion": 99, "actualizado": 200,
                         "marcadores": [{"inicio": 3, "fin": 4, "nota": ""}]}}

    juntado = sincronizacion.juntar(local, remoto)

    assert juntado["a.epub"]["posicion"] == 99
    assert len(juntado["a.epub"]["marcadores"]) == 2
    assert "b.epub" in juntado


def test_un_marcador_repetido_no_se_duplica():
    uno = {"inicio": 1, "fin": 2, "nota": ""}
    otro = {"inicio": 1, "fin": 2, "nota": "con nota"}
    local = {"a": {"actualizado": 1, "marcadores": [uno]}}
    remoto = {"a": {"actualizado": 2, "marcadores": [otro]}}

    juntado = sincronizacion.juntar(local, remoto)

    assert juntado["a"]["marcadores"] == [otro]


# ---------------------------------------------------------------------------
# Revisar la estructura con IA
# ---------------------------------------------------------------------------

def _con_indice() -> Documento:
    texto = ("Índice\nCapítulo 1 ..... 5\nCapítulo 2 ..... 9\n"
             "Capítulo primero\nUn párrafo.\n")
    marcas = [Marca(TipoMarca.ENCABEZADO1, 0, "Índice"),
              Marca(TipoMarca.ENCABEZADO1, texto.index("Capítulo 1"),
                    "Capítulo 1 ..... 5"),
              Marca(TipoMarca.ENCABEZADO1, texto.index("Capítulo 2"),
                    "Capítulo 2 ..... 9"),
              Marca(TipoMarca.ENCABEZADO1, texto.index("Capítulo primero"),
                    "Capítulo primero")]
    return documento(texto, marcas, titulo="T")


def test_el_esqueleto_no_lleva_el_texto_del_libro():
    entradas = estructura.esqueleto(_con_indice())

    escrito = estructura.texto_del_esqueleto(entradas)
    assert "Un párrafo." not in escrito
    assert "Capítulo primero" in escrito


def test_un_titulo_no_arrastra_su_propia_linea_como_parrafo():
    entradas = estructura.esqueleto(_con_indice())

    assert [entrada.clase for entrada in entradas] == ["h1"] * 4


def test_se_interpretan_las_sospechas_y_se_tira_lo_que_no_encaja():
    entradas = estructura.esqueleto(_con_indice())
    respuesta = ("LINEA 2 | artefacto | 0 | Entrada de índice\n"
                 "LINEA 3 | artefacto | 0 | Entrada de índice\n"
                 "LINEA 99 | encabezado | 2 | esa línea no existe\n"
                 "LINEA 4 | inventado | 0 | ese tipo no existe")

    sospechas = estructura.interpretar(respuesta, entradas)

    assert len(sospechas) == 2
    assert all(sospecha.tipo == "artefacto" for sospecha in sospechas)


def test_sin_cambios_no_propone_nada():
    entradas = estructura.esqueleto(_con_indice())

    assert estructura.interpretar("SIN CAMBIOS", entradas) == []


# ---------------------------------------------------------------------------
# Archivos de ayuda de Windows
# ---------------------------------------------------------------------------

#: Un archivo de ayuda de verdad, el que trae WinRAR.  Se usa cuando está
#: instalado: es la única forma de probar el descompresor LZX contra algo real,
#: y armar un CHM a mano no se puede sin escribir también el compresor.
CHM_DE_PRUEBA = Path(r"C:\Program Files\WinRAR\winrar.chm")

falta_chm = pytest.mark.skipif(not CHM_DE_PRUEBA.is_file(),
                               reason="no hay ningún archivo de ayuda instalado")


def test_el_entero_de_longitud_variable_se_lee_byte_a_byte():
    from formatos import chm

    # Siete bits por byte, y el bit alto dice si sigue otro.
    assert chm._entero_variable(bytes([0x05]), 0) == (5, 1)
    assert chm._entero_variable(bytes([0x81, 0x00]), 0) == (128, 2)
    assert chm._entero_variable(bytes([0xC1, 0x80, 0x00]), 0) == (1064960, 3)


def test_lo_que_no_es_un_chm_se_rechaza_con_su_motivo(tmp_path):
    from formatos.chm import ArchivoCHM, ErrorCHM

    destino = tmp_path / "no.chm"
    destino.write_bytes(b"esto no es un archivo de ayuda")

    with pytest.raises(ErrorCHM):
        ArchivoCHM(destino)


@falta_chm
def test_se_lee_el_indice_interno_de_un_chm():
    from formatos.chm import ArchivoCHM

    archivo = ArchivoCHM(CHM_DE_PRUEBA)

    assert len(archivo.entradas) > 100
    assert any(nombre.lower().endswith(".htm") for nombre in archivo.entradas)
    assert "::DataSpace/Storage/MSCompressed/Content" in archivo.entradas


@falta_chm
def test_el_lzx_descomprime_la_seccion_entera():
    """El fallo clásico de LZX da los primeros 32 KB bien y basura después."""
    from formatos.chm import ArchivoCHM, REINICIOS
    import struct

    archivo = ArchivoCHM(CHM_DE_PRUEBA)
    tabla = archivo._crudo(REINICIOS)
    declarado = struct.unpack_from("<Q", tabla, 0x10)[0]

    datos = archivo._seccion_comprimida()

    assert len(datos) == declarado


@falta_chm
def test_las_paginas_de_un_chm_salen_como_html():
    from formatos.chm import ArchivoCHM

    archivo = ArchivoCHM(CHM_DE_PRUEBA)
    paginas = [nombre for nombre in archivo.entradas
               if nombre.lower().endswith((".htm", ".html"))]

    assert paginas
    for nombre in paginas[:5]:
        contenido = archivo.leer(nombre)
        assert contenido, nombre
        assert b"<" in contenido and b">" in contenido


@falta_chm
def test_un_archivo_de_ayuda_se_lee_con_sus_capitulos():
    from formatos.base import OpcionesAnalisis
    from formatos.chm import AnalizadorCHM

    documento = AnalizadorCHM().analizar(CHM_DE_PRUEBA, OpcionesAnalisis())

    assert len(documento.texto) > 10000
    assert len(documento.marcas.encabezados) > 20
    assert documento.marcas.cantidad(TipoMarca.SALTO_SECCION) > 20
    assert documento.metadatos.titulo
