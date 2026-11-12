# -*- coding: utf-8 -*-
"""Pruebas del soporte robusto de PDF.

Lo que se prueba aquí es lo que se puede probar sin depender de ningún archivo
de fuera: las decisiones.  Si una página está escaneada o no, si una línea es
un encabezado y de qué nivel, si dos columnas son texto o una tabla, si un
archivo con el índice roto se puede reconstruir, si una corrección del usuario
se vuelve a aplicar al reabrir.

Los PDF de prueba se escriben aquí mismo, byte a byte.  Cuesta unas líneas más
que traerse un archivo, y a cambio la batería no depende de ninguna carpeta que
pueda no estar, se puede romper el archivo exactamente por donde interesa, y
queda escrito en el propio código qué tenía de particular cada caso.
"""

from __future__ import annotations

import pytest

from formatos import pdf_auditoria, pdf_diagnostico, pdf_geometria, pdf_reparacion
from formatos.pdf_diagnostico import Caja, ClasePagina
from formatos.pdf_hallazgos import ColeccionHallazgos, Hallazgo, Severidad
from nucleo.correcciones import Correcciones


# ---------------------------------------------------------------------------
# PDF mínimos escritos a mano
# ---------------------------------------------------------------------------

def _pdf_minimo(texto: str = "Hola") -> bytes:
    """Escribe el PDF más pequeño que se puede leer: una página con texto."""
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        None,   # el contenido, que se arma abajo porque lleva su longitud
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    flujo = ("BT /F1 12 Tf 72 700 Td (%s) Tj ET" % texto).encode("ascii")
    objetos[3] = b"<< /Length %d >>\nstream\n%s\nendstream" % (len(flujo), flujo)

    salida = bytearray(b"%PDF-1.4\n")
    posiciones = []
    for numero, cuerpo in enumerate(objetos, start=1):
        posiciones.append(len(salida))
        salida += b"%d 0 obj\n%s\nendobj\n" % (numero, cuerpo)
    inicio = len(salida)
    salida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
    for posicion in posiciones:
        salida += b"%010d 00000 n \n" % posicion
    salida += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objetos) + 1, inicio)
    return bytes(salida)


def _romper_indice(datos: bytes) -> bytes:
    """Estropea el índice del PDF dejando el contenido intacto.

    Es la avería más común de todas: el archivo entero está ahí y lo único que
    miente es la tabla que dice dónde empieza cada objeto.
    """
    return datos.replace(b"0000000009 00000 n", b"0000009999 00000 n")


@pytest.fixture
def pdf(carpeta):
    """Un PDF de una página, sano, escrito en la carpeta de la prueba."""
    destino = carpeta / "libro.pdf"
    destino.write_bytes(_pdf_minimo("Documento de prueba"))
    return destino


# ---------------------------------------------------------------------------
# Hallazgos
# ---------------------------------------------------------------------------

def test_dos_hallazgos_iguales_se_cuentan_juntos():
    """Doce imágenes sin describir son un aviso con doce, no doce avisos."""
    hallazgos = ColeccionHallazgos()
    for _ in range(12):
        hallazgos.anadir(Hallazgo("IMAGEN", "Falta la descripción."))

    assert len(hallazgos) == 1
    assert hallazgos.cuantos("IMAGEN") == 12


def test_el_mismo_hallazgo_en_paginas_distintas_no_se_junta():
    """La página forma parte de la identidad: si no, se perdería dónde pasa."""
    hallazgos = ColeccionHallazgos([
        Hallazgo("IMAGEN", "Falta.", pagina=3),
        Hallazgo("IMAGEN", "Falta.", pagina=7),
    ])

    assert len(hallazgos) == 2


def test_al_repetirse_un_hallazgo_manda_la_severidad_peor():
    """Si una página falló del todo, da igual que otra vez solo avisara."""
    hallazgos = ColeccionHallazgos([
        Hallazgo("PAGINA", "Aviso.", Severidad.AVISO),
        Hallazgo("PAGINA", "Error.", Severidad.ERROR),
    ])

    assert hallazgos.peor() is Severidad.ERROR


def test_los_hallazgos_se_cuentan_de_lo_mas_grave_a_lo_menos():
    hallazgos = ColeccionHallazgos([
        Hallazgo("A", "Informativo.", Severidad.INFORMACION),
        Hallazgo("B", "Error.", Severidad.ERROR),
        Hallazgo("C", "Aviso.", Severidad.AVISO),
    ])

    codigos = [h.codigo for h in hallazgos.de_severidad(Severidad.AVISO)]
    assert codigos == ["B", "C"]


def test_un_hallazgo_se_lee_con_su_pagina_y_su_remedio():
    hallazgo = Hallazgo("X", "Falta la descripción.", pagina=4,
                        remedio="Se puede describir con la IA.")

    frase = hallazgo.redactar()
    assert "Página 4." in frase and "IA" in frase


# ---------------------------------------------------------------------------
# Clasificación de páginas
# ---------------------------------------------------------------------------

def test_una_pagina_con_texto_en_el_cuerpo_es_digital():
    cajas = [(Caja(100, 400, 500, 420), 200)]

    clase, dentro = pdf_diagnostico.clasificar_pagina(cajas, 0.0, 612, 792)
    assert clase is ClasePagina.DIGITAL
    assert dentro == 200


def test_una_pagina_escaneada_con_su_numero_impreso_sigue_siendo_escaneada():
    """El caso que fallaba: hay texto de verdad, pero solo en el margen.

    Contando caracteres, esta página «tiene texto» y se quedaba sin reconocer;
    el usuario recibía una página en la que solo se leía el número.
    """
    numero_de_pagina = [(Caja(300, 30, 320, 45), 3)]

    clase, _dentro = pdf_diagnostico.clasificar_pagina(
        numero_de_pagina, 612 * 792 * 0.9, 612, 792)
    assert clase is ClasePagina.ESCANEADA


def test_una_pagina_con_texto_y_una_lamina_grande_es_hibrida():
    cajas = [(Caja(100, 400, 500, 420), 300)]

    clase, _dentro = pdf_diagnostico.clasificar_pagina(
        cajas, 612 * 792 * 0.8, 612, 792)
    assert clase is ClasePagina.HIBRIDA


def test_una_pagina_sin_nada_es_una_pagina_en_blanco():
    clase, dentro = pdf_diagnostico.clasificar_pagina([], 0.0, 612, 792)

    assert clase is ClasePagina.VACIA
    assert dentro == 0


@pytest.mark.parametrize("cantidad, esperado", [(1, "1 página"), (2, "2 páginas")])
def test_lo_que_se_cuenta_se_escribe_en_singular_o_en_plural(cantidad, esperado):
    """Un informe se escucha, y «1 páginas» suena a programa mal hecho."""
    assert pdf_diagnostico.contar(cantidad, "%d página", "%d páginas") == esperado


# ---------------------------------------------------------------------------
# Diagnóstico del archivo
# ---------------------------------------------------------------------------

def test_un_pdf_normal_se_diagnostica_sin_cifrado(pdf):
    informe = pdf_diagnostico.diagnosticar(pdf)

    assert informe.cifrado is pdf_diagnostico.Cifrado.NINGUNO
    assert informe.paginas == 1
    assert informe.version == "1.4"
    assert informe.huella


def test_la_huella_cambia_con_el_contenido_y_no_con_el_nombre(carpeta):
    """Las correcciones se atan a la huella: un libro renombrado es el mismo."""
    uno = carpeta / "uno.pdf"
    uno.write_bytes(_pdf_minimo("Igual"))
    copia = carpeta / "otro-nombre.pdf"
    copia.write_bytes(uno.read_bytes())
    distinto = carpeta / "distinto.pdf"
    distinto.write_bytes(_pdf_minimo("Diferente"))

    assert pdf_diagnostico.huella_sha256(uno) == pdf_diagnostico.huella_sha256(copia)
    assert pdf_diagnostico.huella_sha256(uno) != pdf_diagnostico.huella_sha256(distinto)


def test_un_pdf_sin_estructura_se_diagnostica_como_tal(pdf):
    informe = pdf_diagnostico.diagnosticar(pdf)

    assert not informe.arbol_logico
    assert not informe.marcado


# ---------------------------------------------------------------------------
# Reparación
# ---------------------------------------------------------------------------

def test_se_reconstruye_el_indice_de_un_pdf_roto(carpeta):
    """El contenido no se ha movido: lo que falta es el mapa, y se rehace."""
    roto = carpeta / "roto.pdf"
    roto.write_bytes(_romper_indice(_pdf_minimo("Texto que hay que salvar")))
    destino = carpeta / "reparado.pdf"

    resultado = pdf_reparacion.reparar(roto, destino)

    assert resultado is not None
    assert b"Texto que hay que salvar" in destino.read_bytes()


def test_la_reparacion_no_toca_el_archivo_original(carpeta):
    roto = carpeta / "roto.pdf"
    antes = _romper_indice(_pdf_minimo())
    roto.write_bytes(antes)

    pdf_reparacion.reparar(roto, carpeta / "reparado.pdf")

    assert roto.read_bytes() == antes


def test_la_reparacion_se_niega_a_escribir_sobre_el_original(carpeta):
    ruta = carpeta / "libro.pdf"
    ruta.write_bytes(_pdf_minimo())

    assert pdf_reparacion.reparar(ruta, ruta) is None


def test_se_localizan_todos_los_objetos_de_un_pdf():
    posiciones = pdf_reparacion._localizar_objetos(_pdf_minimo())

    assert sorted(posiciones) == [1, 2, 3, 4, 5]


def test_de_un_objeto_repetido_vale_la_ultima_version():
    """Es lo que pasa en un archivo guardado por partes: manda lo último."""
    datos = b"\n1 0 obj\n<< /A 1 >>\nendobj\n1 0 obj\n<< /A 2 >>\nendobj\n"

    posiciones = pdf_reparacion._localizar_objetos(datos)
    assert posiciones[1] > 20


def test_un_pdf_sin_final_parece_roto(carpeta):
    truncado = carpeta / "truncado.pdf"
    truncado.write_bytes(_pdf_minimo()[:200])

    assert pdf_reparacion.parece_roto(truncado)


def test_un_pdf_entero_no_parece_roto(pdf):
    assert not pdf_reparacion.parece_roto(pdf)


# ---------------------------------------------------------------------------
# Estructura deducida de la geometría
# ---------------------------------------------------------------------------

def test_la_escala_de_titulos_da_niveles_seguidos():
    """Tres tamaños de título son h1, h2 y h3, midan lo que midan.

    Comparando contra el cuerpo por tramos, 24, 18 y 14 sobre un cuerpo de 12
    daban h1, h2 y h4: un nivel saltado, que rompe el árbol del documento.
    """
    candidatos = [("Título del documento", 24.0), ("Primera sección", 18.0),
                  ("Segunda sección", 18.0), ("Un apartado", 14.0),
                  ("texto normal y corriente que sigue.", 12.0)]

    escala = pdf_geometria._escala_de_encabezados(candidatos, 12.0)
    assert escala == (24.0, 18.0, 14.0)
    assert pdf_geometria._nivel_en_escala(24.0, escala) == 1
    assert pdf_geometria._nivel_en_escala(18.0, escala) == 2
    assert pdf_geometria._nivel_en_escala(14.0, escala) == 3


def test_el_tamano_del_cuerpo_no_entra_en_la_escala_de_titulos():
    escala = pdf_geometria._escala_de_encabezados([("Un párrafo.", 12.0)], 12.0)

    assert escala == ()


def test_medio_punto_de_diferencia_es_el_mismo_nivel():
    """El mismo estilo puede medir 13,98 en una página y 14,03 en otra."""
    assert pdf_geometria._nivel_en_escala(14.03, (18.0, 14.0)) == 2


def test_una_linea_repetida_en_muchas_paginas_es_un_pie_de_pagina():
    claves = [pdf_geometria.normalizar("Informe anual — página %d" % n)
              for n in range(1, 11)]

    repetidos = pdf_geometria._repetidos(claves, 10)
    assert pdf_geometria.normalizar("Informe anual — página 4") in repetidos


def test_no_se_borra_nada_en_un_documento_de_pocas_paginas():
    """Con tres páginas, dos coincidencias son casualidad, no un pie."""
    assert pdf_geometria._repetidos(["igual", "igual"], 2) == frozenset()


def test_los_numeros_no_impiden_reconocer_un_pie_repetido():
    """Sin esto, «página 1» y «página 2» serían dos líneas distintas."""
    assert pdf_geometria.normalizar("Página 12") == pdf_geometria.normalizar("Página 340")


def _renglon(palabras, texto, x, y, cuantas=6, ancho=30):
    """Añade un renglón de varias palabras seguidas, como el de un párrafo."""
    for indice in range(cuantas):
        palabras.append(_palabra(texto, x + indice * (ancho + 4), y, ancho))


def test_un_texto_a_dos_columnas_se_parte_en_dos():
    """Y se lee entera la izquierda antes que la derecha, no renglón a renglón."""
    palabras = []
    for fila in range(6):
        y = 100 + fila * 15
        _renglon(palabras, "izquierda", 72, y)
        _renglon(palabras, "derecha", 340, y)

    cortes, columnas = pdf_geometria._partir_en_columnas(palabras, 612)
    assert len(cortes) == 1
    assert len(columnas) == 2
    assert all(p.x < cortes[0] for p in columnas[0])


def test_una_tabla_sin_lineas_no_se_confunde_con_dos_columnas():
    """La diferencia está en cuántas palabras lleva cada renglón."""
    palabras = []
    for fila in range(6):
        y = 100 + fila * 15
        palabras.append(_palabra("dato", 72, y, 24))
        palabras.append(_palabra("dato", 340, y, 24))

    cortes, columnas = pdf_geometria._partir_en_columnas(palabras, 612)
    assert cortes == ()
    assert len(columnas) == 1


def test_una_tabla_de_muchas_columnas_no_se_parte():
    """Más de dos pasillos no es una maquetación: es una tabla o un formulario."""
    palabras = []
    for fila in range(6):
        y = 100 + fila * 15
        for columna in range(5):
            _renglon(palabras, "dato", 40 + columna * 110, y, cuantas=2, ancho=20)

    cortes, columnas = pdf_geometria._partir_en_columnas(palabras, 612)
    assert cortes == ()
    assert len(columnas) == 1


def test_una_rejilla_de_renglones_larguisimos_no_es_una_tabla():
    """Un gráfico junto a una lista de cifras se alinea, pero no es una tabla."""
    class _Linea:
        def __init__(self, texto):
            self.texto = texto

    assert not pdf_geometria._tabla_creible([_Linea("x" * 400)])
    assert pdf_geometria._tabla_creible([_Linea("Nombre"), _Linea("Edad")])


def test_una_palabra_partida_por_el_final_del_renglon_se_une():
    unido = pdf_geometria._unir([("Esto es infor-", "Esto es infor-"),
                                 ("mación útil", "mación útil")])

    assert unido == "Esto es información útil"


def test_un_guion_de_verdad_no_se_come():
    """«Madrid-Barcelona» al final de un renglón sigue llevando su guion."""
    unido = pdf_geometria._unir([("Trayecto Madrid-", "Trayecto Madrid-"),
                                 ("Barcelona", "Barcelona")])

    assert unido == "Trayecto Madrid- Barcelona"


def test_las_palabras_bajo_un_enlace_se_marcan_como_enlace():
    """Un PDF sin etiquetar se leía sin un solo enlace que seguir."""
    palabras = [_palabra("Visita", 72, 100, 40), _palabra("esta", 120, 100, 30),
                _palabra("página", 155, 100, 40)]
    pagina = _pagina(palabras, enlaces=[(115.0, 95.0, 200.0, 115.0, "https://ejemplo.org")])

    marcado = pdf_geometria._texto_con_enlaces(_LineaFalsa(palabras), pagina)
    assert marcado == 'Visita <a href="https://ejemplo.org">esta página</a>'


def test_sin_enlaces_el_texto_solo_se_escapa():
    palabras = [_palabra("a<b", 72, 100, 20)]

    assert pdf_geometria._texto_con_enlaces(
        _LineaFalsa(palabras), _pagina(palabras)) == "a&lt;b"


def test_una_palabra_en_negrita_dentro_de_un_renglon_se_marca():
    """La negrita es una marca navegable, igual que en un EPUB."""
    palabras = [_palabra("Esto", 72, 100, 30), _palabra("importa", 105, 100, 50),
                _palabra("mucho", 160, 100, 40)]
    pagina = _pagina(palabras, negritas={"importa"})

    marcado = pdf_geometria._texto_con_enlaces(_LineaFalsa(palabras), pagina)
    assert marcado == "Esto <strong>importa</strong> mucho"


def test_un_renglon_entero_en_negrita_no_lleva_negrita_dentro():
    """Marcarlo entero sería anunciar una negrita en cada línea del documento."""
    palabras = [_palabra("Todo", 72, 100, 30), _palabra("negrita", 105, 100, 50)]
    pagina = _pagina(palabras, negritas={"Todo", "negrita"})

    marcado = pdf_geometria._texto_con_enlaces(_LineaFalsa(palabras), pagina)
    assert "<strong>" not in marcado


def _renglon_falso(x, y, cuantas=5):
    """Un renglón sangrado con varias palabras, como el de una cita."""
    return _LineaFalsa([_palabra("palabra", x + n * 40, y, 35) for n in range(cuantas)])


def test_un_bloque_apartado_del_margen_es_una_cita():
    contexto = pdf_geometria.Contexto(12.0, frozenset(), (), 72.0, frozenset())

    assert pdf_geometria._bloque_sangrado(
        [_renglon_falso(150, 100), _renglon_falso(150, 115)], contexto)


def test_un_solo_renglon_sangrado_no_es_una_cita():
    """Es la sangría de primera línea de un párrafo, y hay una en cada uno."""
    contexto = pdf_geometria.Contexto(12.0, frozenset(), (), 72.0, frozenset())

    assert not pdf_geometria._bloque_sangrado([_renglon_falso(150, 100)], contexto)


def test_una_columna_de_cifras_sangrada_no_es_una_cita():
    """En una tabla, la columna de la derecha empieza muy a la derecha."""
    contexto = pdf_geometria.Contexto(12.0, frozenset(), (), 72.0, frozenset())
    cifras = [_LineaFalsa([_palabra("1.234", 150, 100 + n * 15, 40)]) for n in range(4)]

    assert not pdf_geometria._bloque_sangrado(cifras, contexto)


def test_los_filetes_de_cabecera_y_pie_no_son_separadores():
    """Están en todas las páginas: son mobiliario, no separan secciones."""
    contexto = pdf_geometria.Contexto(12.0, frozenset(), (), 72.0, frozenset({"47", "738"}))

    assert pdf_geometria._separadores_utiles([47.0, 400.0, 738.0], contexto) == [400.0]


def test_dos_filetes_muy_juntos_son_una_tabla_y_no_dos_separadores():
    contexto = pdf_geometria.Contexto(12.0, frozenset(), (), 72.0, frozenset())

    assert pdf_geometria._separadores_utiles([200.0, 212.0], contexto) == []


def test_un_pie_que_solo_numera_la_figura_no_cuenta_como_descripcion():
    """«Figura 7-26.» es una etiqueta: no dice nada de lo que se ve."""
    assert not pdf_geometria._pie_descriptivo("Figure 7-26.")
    assert not pdf_geometria._pie_descriptivo("Figura 3")
    assert pdf_geometria._pie_descriptivo(
        "Figura 4. Ventas por trimestre en la región norte")


def test_una_linea_pequena_y_numerada_al_pie_es_una_nota():
    """Las tres condiciones a la vez: abajo, en letra menor y numerada."""
    palabras = [_palabra("1", 72, 700, 6)] + [
        _palabra("Aclaración", 82 + n * 60, 700, 55) for n in range(4)]
    linea = _LineaFalsa(palabras)
    pagina = _pagina(palabras, tamano=8.0)
    contexto = pdf_geometria.Contexto(12.0, frozenset(), (), 72.0, frozenset())

    notas = pdf_geometria._notas_al_pie([linea], pagina, contexto)
    assert notas.cuerpos[id(linea)] == "nota-1-1"
    assert notas.numeros["1"] == "nota-1-1"


def test_un_parrafo_numerado_en_medio_de_la_pagina_no_es_una_nota():
    """Ahí empieza cualquier lista numerada, y convertirla en notas la rompe."""
    palabras = [_palabra("1", 72, 200, 6)] + [
        _palabra("Primer", 82 + n * 60, 200, 55) for n in range(4)]
    linea = _LineaFalsa(palabras)
    pagina = _pagina(palabras, tamano=8.0)
    contexto = pdf_geometria.Contexto(12.0, frozenset(), (), 72.0, frozenset())

    assert not pdf_geometria._notas_al_pie([linea], pagina, contexto).cuerpos


def test_un_parrafo_al_pie_con_letra_normal_tampoco_es_una_nota():
    palabras = [_palabra("1", 72, 700, 6)] + [
        _palabra("Texto", 82 + n * 60, 700, 55) for n in range(4)]
    linea = _LineaFalsa(palabras)
    pagina = _pagina(palabras, tamano=12.0)
    contexto = pdf_geometria.Contexto(12.0, frozenset(), (), 72.0, frozenset())

    assert not pdf_geometria._notas_al_pie([linea], pagina, contexto).cuerpos


def test_un_numero_volado_se_marca_como_llamada_de_nota():
    """Sin marcarlo se lee pegado a la palabra anterior y parece parte de ella."""
    grandes = [_palabra("Una", 72, 100, 30), _palabra("afirmación", 105, 100, 70)]
    volado = _palabra("3", 178, 100, 5)
    palabras = grandes + [volado]
    estilos = {
        pdf_geometria._clave(p): pdf_geometria.Estilo(12.0, False, False, "")
        for p in grandes}
    estilos[pdf_geometria._clave(volado)] = pdf_geometria.Estilo(7.0, False, False, "")
    pagina = pdf_geometria.PaginaGeometrica(
        numero=1, ancho=612.0, alto=792.0, palabras=palabras, estilos=estilos,
        tablas=[], enlaces=())
    notas = pdf_geometria.Notas({}, {"3": "nota-1-3"})

    marcado = pdf_geometria._texto_con_enlaces(_LineaFalsa(palabras), pagina, notas)
    assert '<a class="noteref" href="#nota-1-3">3</a>' in marcado


def test_un_numero_del_mismo_tamano_no_es_una_llamada():
    """«Capítulo 3» no lleva ninguna nota detrás."""
    palabras = [_palabra("Capítulo", 72, 100, 60), _palabra("3", 135, 100, 8)]
    pagina = _pagina(palabras, tamano=12.0)
    notas = pdf_geometria.Notas({}, {"3": "nota-1-3"})

    marcado = pdf_geometria._texto_con_enlaces(_LineaFalsa(palabras), pagina, notas)
    assert "noteref" not in marcado


def test_una_figura_sin_pie_descriptivo_se_queda_pendiente_de_describir():
    """Su «alt» va vacío para que la orden de describir con IA la incluya."""
    figura = pdf_geometria.Figura((10.0, 20.0, 110.0, 120.0), "Figura 3", 0.0, False)

    html = pdf_geometria._figura_a_html(figura, 5)
    assert 'alt=""' in html
    assert "pdf-figura:5:10.00,20.00,110.00,120.00" in html
    assert "<figcaption>Figura 3</figcaption>" in html


def test_la_referencia_de_una_figura_permite_recortarla_despues():
    """Es el mismo contrato que usa el camino etiquetado, sin tocar nada más."""
    from formatos.pdf import _FIGURA

    figura = pdf_geometria.Figura((10.5, 20.25, 110.0, 120.0), "", 0.0, True)
    referencia = pdf_geometria._figura_a_html(figura, 3).split('src="')[1].split('"')[0]

    assert _FIGURA.match(referencia)


def test_un_trazo_fino_y_largo_es_un_filete_y_no_parte_de_un_dibujo():
    assert pdf_geometria._es_filete(400.0, 0.7)
    assert not pdf_geometria._es_filete(200.0, 150.0)


def test_dos_figuras_que_se_pisan_se_anuncian_una_vez():
    """Un gráfico con una foto dentro aparece como imagen y como trazos."""
    cajas = [(10.0, 10.0, 200.0, 200.0, True), (50.0, 50.0, 100.0, 100.0, False)]

    assert len(pdf_geometria._sin_solapes(cajas)) == 1


# ---------------------------------------------------------------------------
# Palabras que no deben partirse
# ---------------------------------------------------------------------------

def test_el_estilo_de_una_palabra_sale_de_sus_letras():
    """Pedirle el tamaño al extractor partía las palabras en versalitas.

    En «INCLUDING» la I inicial va a 14 puntos y el resto a 11, y pdfplumber
    parte una palabra en cuanto cambia un atributo que se le haya pedido: la
    línea salía como «I NCLUDING A LL S TUDENTS».
    """
    letras = {
        25: [
            {"top": 74.0, "x0": 72.0, "x1": 75.9, "size": 14.0, "fontname": "Times"},
            {"top": 76.4, "x0": 75.9, "x1": 83.8, "size": 11.0, "fontname": "Times"},
            {"top": 76.4, "x0": 83.8, "x1": 91.8, "size": 11.0, "fontname": "Times"},
        ],
    }
    palabra = {"top": 74.0, "x0": 72.0, "x1": 91.8, "text": "INC"}

    estilo = pdf_geometria._estilo_de_palabra(letras, palabra)
    assert estilo.tamano == 14.0
    assert estilo.fuente == "Times"


def test_el_estilo_de_una_palabra_sin_letras_conocidas_queda_vacio():
    assert pdf_geometria._estilo_de_palabra({}, {"top": 1.0, "x0": 0.0, "x1": 9.0}).tamano == 0.0


@pytest.mark.parametrize("hueco, espera", [(0.05, ""), (0.9, ""), (5.0, " ")])
def test_entre_dos_trozos_solo_se_pone_espacio_si_el_hueco_es_de_espacio(hueco, espera):
    """La versalita deja un hueco mayor que el normal y no es un espacio.

    El hueco se mide en proporción a la letra: con una medida fija en puntos,
    la separación normal de un título grande pasaba por espacio y partía sus
    palabras.
    """
    from formatos.pdf_etiquetado import _separacion

    anterior = (10.0, 100.0, 20.0, 114.0)
    siguiente = (20.0 + hueco, 100.0, 40.0, 114.0)
    assert _separacion("I", anterior, "NSTITUTO", siguiente) == espera


def test_dos_trozos_en_renglones_distintos_siempre_se_separan():
    from formatos.pdf_etiquetado import _separacion

    assert _separacion("uno", (10.0, 100.0, 20.0, 112.0),
                       "dos", (10.0, 80.0, 20.0, 92.0)) == " "


def test_una_palabra_partida_por_guion_no_lleva_espacio():
    from formatos.pdf_etiquetado import _separacion

    assert _separacion("infor-", (10.0, 100.0, 30.0, 112.0),
                       "mación", (10.0, 80.0, 40.0, 92.0)) == ""


# ---------------------------------------------------------------------------
# Auditoría de accesibilidad
# ---------------------------------------------------------------------------

class _DiagnosticoFalso:
    """Lo mínimo que la auditoría le pregunta a un diagnóstico."""

    def __init__(self, **campos):
        self.con_pypdf = True
        self.arbol_logico = True
        self.marcado = True
        self.suspects = False
        self.idioma = "es"
        self.titulo_xmp = "Un título"
        self.mostrar_titulo = True
        self.__dict__.update(campos)


class _EtiquetadoFalso:
    """Lo mínimo que la auditoría le pregunta al informe de etiquetado."""

    def __init__(self, **campos):
        self.desactivado = False
        self.usar = True
        self.cobertura = 1.0
        self.paginas_con_arbol = 1
        self.etiquetas = {}
        self.figuras = 0
        self.figuras_sin_alt = 0
        self.idioma = "es"
        self.idiomas = {}
        self.__dict__.update(campos)


def _codigos(hallazgos):
    """Los códigos encontrados, para poder afirmar sobre ellos."""
    return {h.codigo for h in hallazgos}


def test_un_pdf_bien_hecho_no_produce_quejas():
    hallazgos = pdf_auditoria.auditar(_DiagnosticoFalso(), _EtiquetadoFalso())

    assert not _codigos(hallazgos)


def test_se_avisa_de_un_pdf_sin_estructura():
    hallazgos = pdf_auditoria.auditar(_DiagnosticoFalso(arbol_logico=False))

    assert "SIN_ARBOL" in _codigos(hallazgos)


def test_se_avisa_de_un_documento_sin_idioma():
    hallazgos = pdf_auditoria.auditar(_DiagnosticoFalso(idioma=""))

    assert "SIN_IDIOMA" in _codigos(hallazgos)


def test_se_avisa_de_las_tablas_sin_celdas_de_encabezado():
    """Sin encabezados, cada número de la tabla se oye sin saber de qué es."""
    etiquetado = _EtiquetadoFalso(etiquetas={"Table": 3, "TR": 9, "TD": 27})

    hallazgos = pdf_auditoria.auditar(None, etiquetado)
    assert "TABLAS_SIN_ENCABEZADO" in _codigos(hallazgos)


def test_una_tabla_con_encabezados_no_se_denuncia():
    etiquetado = _EtiquetadoFalso(etiquetas={"Table": 1, "TR": 3, "TH": 3, "TD": 6})

    assert "TABLAS_SIN_ENCABEZADO" not in _codigos(pdf_auditoria.auditar(None, etiquetado))


def test_se_cuentan_las_imagenes_sin_describir():
    etiquetado = _EtiquetadoFalso(figuras=10, figuras_sin_alt=4)

    hallazgos = pdf_auditoria.auditar(None, etiquetado)
    assert hallazgos.cuantos("FIGURAS_SIN_ALTERNATIVA") == 4


def test_bajar_dos_niveles_de_golpe_es_un_salto():
    assert pdf_auditoria._saltos_de_nivel([1, 2, 4]) == 1


def test_subir_dos_niveles_de_golpe_no_lo_es():
    """Cerrar dos secciones a la vez es correcto y no debe denunciarse."""
    assert pdf_auditoria._saltos_de_nivel([1, 2, 3, 1]) == 0


def test_el_informe_siempre_avisa_de_que_es_parcial():
    """Un informe sin fallos no puede leerse como un certificado."""
    texto = pdf_auditoria.redactar(ColeccionHallazgos())

    assert "no garantizan" in texto


# ---------------------------------------------------------------------------
# Correcciones del usuario
# ---------------------------------------------------------------------------

@pytest.fixture
def correcciones(carpeta, monkeypatch):
    """Correcciones que se guardan en la carpeta de la prueba."""
    from nucleo import rutas

    monkeypatch.setattr(rutas, "directorio_base", lambda: carpeta)
    return Correcciones("f" * 64)


CUERPO = ('<h2>Esto no era un título</h2><p>Texto normal.</p>'
          '<p>Esto sí lo era</p><p>Pie repetido</p>')


def test_lo_que_no_era_un_titulo_deja_de_serlo(correcciones):
    correcciones.marcar(1, "Esto no era un título", "parrafo")

    assert "<p>Esto no era un título</p>" in correcciones.corregir_pagina(CUERPO, 1)


def test_lo_que_si_era_un_titulo_pasa_a_serlo(correcciones):
    correcciones.marcar(1, "Esto sí lo era", "encabezado", 3)

    assert "<h3>Esto sí lo era</h3>" in correcciones.corregir_pagina(CUERPO, 1)


def test_un_artefacto_desaparece_de_la_lectura(correcciones):
    correcciones.marcar(1, "Pie repetido", "artefacto")

    assert "Pie repetido" not in correcciones.corregir_pagina(CUERPO, 1)


def test_una_correccion_solo_afecta_a_su_pagina(correcciones):
    """La misma frase en otra página puede querer decir otra cosa."""
    correcciones.marcar(1, "Esto sí lo era", "encabezado", 3)

    assert correcciones.corregir_pagina(CUERPO, 2) == CUERPO


def test_las_correcciones_sobreviven_a_cerrar_el_libro(correcciones):
    correcciones.marcar(2, "Un título", "encabezado", 1)
    correcciones.describir("pdf-figura:1:0,0,10,10", "Gráfico de ventas")
    correcciones.guardar()

    vueltas = Correcciones.cargar(correcciones.huella)
    assert vueltas.descripcion_de("pdf-figura:1:0,0,10,10") == "Gráfico de ventas"
    assert "<h1>Un título</h1>" in vueltas.corregir_pagina("<p>Un título</p>", 2)


def test_un_documento_distinto_no_hereda_correcciones(correcciones):
    correcciones.marcar(1, "Algo", "artefacto")
    correcciones.guardar()

    assert not Correcciones.cargar("a" * 64)


def test_olvidar_deshace_una_correccion(correcciones):
    correcciones.marcar(1, "Esto sí lo era", "encabezado", 3)

    assert correcciones.olvidar(1, "Esto sí lo era")
    assert correcciones.corregir_pagina(CUERPO, 1) == CUERPO


def test_un_texto_que_ya_no_esta_no_rompe_nada(correcciones):
    """Si mejora el reconocimiento, la corrección deja de aplicarse y ya."""
    correcciones.marcar(1, "Una frase que ha cambiado", "encabezado", 2)

    assert correcciones.corregir_pagina(CUERPO, 1) == CUERPO


def test_no_se_admite_un_tipo_inventado(correcciones):
    assert not correcciones.marcar(1, "Algo", "chorrada")


# ---------------------------------------------------------------------------
# Utilidades de las pruebas
# ---------------------------------------------------------------------------

def _palabra(texto: str, x: int, y: int, ancho: int):
    """Una palabra con su caja, como las que produce la medida de una página."""
    from formatos import disposicion

    return disposicion.Palabra(texto, x, y, ancho, 12)


class _LineaFalsa:
    """Un renglón con lo que mira el marcado de un renglón."""

    def __init__(self, palabras):
        self.palabras = palabras

    @property
    def texto(self) -> str:
        return " ".join(palabra.texto for palabra in self.palabras)

    @property
    def x(self) -> int:
        return min(palabra.x for palabra in self.palabras)

    @property
    def y(self) -> int:
        return min(palabra.y for palabra in self.palabras)


def _pagina(palabras, enlaces=(), negritas=frozenset(), tamano=12.0, fuente=""):
    """Una página medida de mentira, con el estilo que pida cada prueba."""
    estilos = {
        pdf_geometria._clave(palabra): pdf_geometria.Estilo(
            tamano, palabra.texto in negritas, False, fuente)
        for palabra in palabras
    }
    return pdf_geometria.PaginaGeometrica(
        numero=1, ancho=612.0, alto=792.0, palabras=list(palabras),
        estilos=estilos, tablas=[], enlaces=tuple(enlaces))


# ---------------------------------------------------------------------------
# Cuándo merece la pena medir la maquetación
# ---------------------------------------------------------------------------

class _PaginaConDibujos:
    """Una página de mentira con lo que mira la comprobación de dibujos."""

    def __init__(self, images=(), curves=(), rects=()):
        self.images = list(images)
        self.curves = list(curves)
        self.rects = list(rects)


class _DocumentoDeMentira:
    def __init__(self, paginas):
        self.pages = list(paginas)


def test_una_pagina_con_una_imagen_tiene_algo_que_medir():
    documento = _DocumentoDeMentira([_PaginaConDibujos(images=[{"x0": 0}])])

    assert pdf_geometria._tiene_dibujos(documento, 0)


def test_una_pagina_con_trazos_tambien():
    documento = _DocumentoDeMentira([_PaginaConDibujos(curves=[{"x0": 0}])])

    assert pdf_geometria._tiene_dibujos(documento, 0)


def test_una_pagina_escaneada_sin_nada_dibujado_no_tiene_que_medirse():
    """La fotografía de la página se descarta por ocupar la página entera."""
    documento = _DocumentoDeMentira([_PaginaConDibujos()])

    assert not pdf_geometria._tiene_dibujos(documento, 0)


def test_una_pagina_que_no_existe_no_rompe_la_comprobacion():
    assert not pdf_geometria._tiene_dibujos(_DocumentoDeMentira([]), 5)


def test_un_pdf_solo_de_imagenes_se_mide_aunque_no_tenga_texto():
    """Es lo único que tiene, y son figuras que se pueden describir con IA.

    Saltarse la medida por no encontrar letra dejaba esos documentos sin una
    sola figura, y por tanto fuera del alcance de la orden de describirlas.
    """
    contexto = pdf_geometria.Contexto(0.0, frozenset(), (), 0.0, frozenset(), True)

    assert contexto.hay_dibujos
    assert not contexto.cuerpo


# ---------------------------------------------------------------------------
# El código de los manuales de programación
# ---------------------------------------------------------------------------

def test_se_reconoce_por_la_medida_una_letra_de_maquina_de_escribir():
    """No por el nombre: llega con el prefijo del subconjunto y no dice nada."""
    iguales = {"GAAAAA+Menlo-Regular": {letra: 0.6 for letra in "abcdefghi"},
               "CAAAAA+Times": dict(zip("abcdefghi", [0.28, 0.5, 0.44, 0.5, 0.44,
                                                      0.33, 0.5, 0.5, 0.28]))}
    cuantas = {"GAAAAA+Menlo-Regular": 200, "CAAAAA+Times": 3000}

    assert pdf_geometria._fuentes_monoespaciadas(iguales, cuantas) == frozenset(
        {"GAAAAA+Menlo-Regular"})


def test_una_letra_normal_no_pasa_por_maquina_de_escribir():
    """En una letra normal la «i» y la «m» no ocupan ni de lejos lo mismo."""
    variada = {"CAAAAA+Times": dict(zip("abcdefghi", [0.28, 0.5, 0.44, 0.5, 0.44,
                                                     0.33, 0.5, 0.5, 0.28]))}

    assert pdf_geometria._fuentes_monoespaciadas(variada, {"CAAAAA+Times": 3000}) == frozenset()


def test_con_pocas_letras_vistas_no_se_opina_de_una_fuente():
    """Las cifras van a la misma anchura en casi todas: no prueban nada."""
    pocas = {"X+Loquesea": {"a": 0.6, "b": 0.6, "c": 0.6}}

    assert pdf_geometria._fuentes_monoespaciadas(pocas, {"X+Loquesea": 3000}) == frozenset()


def test_un_documento_escrito_entero_a_maquina_no_es_un_documento_de_codigo():
    """Un listado o un informe antiguo: esa es su letra normal y no señala nada.

    Sin esta salvedad el documento entero se daba por código y se perdían sus
    encabezados, sus listas y sus citas.
    """
    todo = {"Courier": {letra: 0.6 for letra in "abcdefghi"}}

    assert pdf_geometria._fuentes_monoespaciadas(todo, {"Courier": 3000}) == frozenset()


def _renglon_de_codigo(texto, x, y):
    """Un renglón escrito entero en letra de máquina de escribir."""
    return _LineaFalsa([_palabra(trozo, x + n * 60, y, len(trozo) * 6)
                        for n, trozo in enumerate(texto.split())])


CONTEXTO_CODIGO = pdf_geometria.Contexto(
    12.0, frozenset(), (), 72.0, frozenset(), False, frozenset({"Menlo"}))


def test_un_bloque_de_codigo_conserva_sus_renglones():
    """Unidos con espacios, diez sentencias se leen como una frase sin sentido."""
    lineas = [_renglon_de_codigo("n = 7", 72, 100),
              _renglon_de_codigo("radius = 60", 72, 115)]
    pagina = _pagina([p for linea in lineas for p in linea.palabras], fuente="Menlo")

    html = pdf_geometria._bloque_a_html(lineas, pagina, CONTEXTO_CODIGO)
    assert html == "<pre>n = 7<br/>radius = 60</pre>"


def test_un_bloque_de_codigo_conserva_su_sangria():
    """En Python la sangría es la sintaxis: sin ella no se sabe qué va dentro."""
    lineas = [_renglon_de_codigo("for word in seq:", 72, 100),
              _renglon_de_codigo("print(word)", 96, 115)]
    pagina = _pagina([p for linea in lineas for p in linea.palabras], fuente="Menlo")

    html = pdf_geometria._bloque_a_html(lineas, pagina, CONTEXTO_CODIGO)
    assert html == "<pre>for word in seq:<br/>    print(word)</pre>"


def test_un_parrafo_con_un_nombre_de_funcion_dentro_sigue_siendo_un_parrafo():
    """Manda la letra dominante del renglón, no la de una palabra suelta."""
    palabras = [_palabra("Llama", 72, 100, 45), _palabra("a", 120, 100, 8),
                _palabra("print", 132, 100, 30), _palabra("para", 166, 100, 35),
                _palabra("mostrarlo", 205, 100, 75)]
    estilos = {}
    for palabra in palabras:
        estilos[pdf_geometria._clave(palabra)] = pdf_geometria.Estilo(
            12.0, False, False, "Menlo" if palabra.texto == "print" else "Times")
    pagina = pdf_geometria.PaginaGeometrica(
        numero=1, ancho=612.0, alto=792.0, palabras=list(palabras),
        estilos=estilos, tablas=[], enlaces=())

    html = pdf_geometria._bloque_a_html([_LineaFalsa(palabras)], pagina, CONTEXTO_CODIGO)
    assert html.startswith("<p>") and "<pre>" not in html


def test_el_fondo_de_un_bloque_de_codigo_no_es_una_figura():
    """Un rectángulo gris con texto encima no tiene nada que ver ni que describir."""
    # La caja va en coordenadas del PDF —origen abajo— y los renglones en
    # coordenadas de pantalla, que es como los devuelve la extracción.
    renglones = [("linea %d" % n, 60.0, 300.0, 360.0 + n * 14, 372.0 + n * 14)
                 for n in range(12)]

    assert pdf_geometria._es_fondo((48.0, 200.0, 588.0, 430.0), 792.0, renglones)


def test_un_grafico_con_sus_rotulos_sigue_siendo_una_figura():
    """Los rótulos de un gráfico son líneas sueltas, una por marca del eje.

    Aunque sean muchas y sumen alto, entre ellas hay hueco: sin exigir que
    vayan seguidas, un gráfico con los ejes rotulados se borraba entero.
    """
    renglones = [("eje %d" % n, 60.0, 120.0, 365.0 + n * 30, 377.0 + n * 30)
                 for n in range(10)]

    assert not pdf_geometria._es_fondo((48.0, 200.0, 588.0, 430.0), 792.0, renglones)


def test_un_rectangulo_pintado_cuatro_veces_no_llega_a_figura():
    """Los PDF hechos desde HTML repiten el mismo relleno, y contaba cuatro veces."""
    caja = {"x0": 100.0, "y0": 300.0, "x1": 400.0, "y1": 500.0}
    pagina = _PaginaConDibujos(rects=[dict(caja) for _ in range(9)])

    assert pdf_geometria._dibujos_agrupados(pagina, 612.0, 792.0, 612.0 * 792.0, []) == []


def test_un_punto_de_lista_en_letra_de_maquina_no_es_codigo():
    """En un manual técnico hay listas de rutas y opciones, y siguen siendo listas."""
    linea = _renglon_de_codigo("• usa /usr/local/lib", 72, 100)
    pagina = _pagina(linea.palabras, fuente="Menlo")

    html = pdf_geometria._bloque_a_html([linea], pagina, CONTEXTO_CODIGO)
    assert "<pre>" not in html and "<li>" in html


# ---------------------------------------------------------------------------
# Las reglas de PDF/UA sobre anidamiento y equivalencias
# ---------------------------------------------------------------------------

class _EtiquetadoConPares:
    """Un etiquetado de mentira con los pares padre-hijo que se quieran."""

    def __init__(self, pares=None, etiquetas=None):
        self.pares = dict(pares or {})
        self.etiquetas = dict(etiquetas or {})
        self.usar = True
        self.desactivado = False
        self.paginas_con_arbol = 1
        self.cobertura = 1.0
        self.figuras = 0
        self.figuras_sin_alt = 0
        self.idioma = "es"
        self.idiomas = {}


def _codigos(hallazgos):
    return {hallazgo.codigo for hallazgo in hallazgos}


def test_una_celda_fuera_de_su_fila_se_detecta():
    """Sin fila no hay columna, y sin columna no hay encabezado que anunciar."""
    hallazgos = pdf_auditoria.ColeccionHallazgos()
    pdf_auditoria._revisar_anidamiento(hallazgos, {("Table", "TD"): 7})

    assert "TABLA_MAL_FORMADA" in _codigos(hallazgos)


def test_una_tabla_bien_anidada_no_se_queja():
    hallazgos = pdf_auditoria.ColeccionHallazgos()
    pdf_auditoria._revisar_anidamiento(hallazgos, {
        ("Table", "TBody"): 3, ("TBody", "TR"): 30, ("TR", "TD"): 120,
        ("TR", "TH"): 30, ("Table", "Caption"): 1})

    assert not _codigos(hallazgos)


def test_un_punto_de_lista_sin_cuerpo_se_detecta():
    """El texto cuelga del LI en vez de su LBody: la viñeta no se separa."""
    hallazgos = pdf_auditoria.ColeccionHallazgos()
    pdf_auditoria._revisar_anidamiento(hallazgos, {("LI", "P"): 18})

    assert "LISTA_MAL_FORMADA" in _codigos(hallazgos)


def test_un_envoltorio_por_medio_no_cuenta_como_mal_anidado():
    """«Span» y «Div» no cambian lo que un elemento es."""
    hallazgos = pdf_auditoria.ColeccionHallazgos()
    pdf_auditoria._revisar_anidamiento(hallazgos, {("TR", "Span"): 4, ("Span", "TD"): 4})

    assert not _codigos(hallazgos)


class _DiagnosticoConMapa:
    """Un diagnóstico de mentira para las reglas de equivalencias."""

    def __init__(self, role_map=None):
        self.con_pypdf = True
        self.role_map = dict(role_map or {})


def test_una_etiqueta_inventada_sin_equivalencia_se_detecta():
    """Sin decir a qué equivale, el elemento existe y no significa nada."""
    hallazgos = pdf_auditoria.ColeccionHallazgos()
    pdf_auditoria._revisar_equivalencias(
        hallazgos, _EtiquetadoConPares(etiquetas={"Portada": 1, "P": 40}),
        _DiagnosticoConMapa())

    assert "ETIQUETAS_SIN_EQUIVALENCIA" in _codigos(hallazgos)


def test_una_etiqueta_inventada_con_equivalencia_no_se_queja():
    hallazgos = pdf_auditoria.ColeccionHallazgos()
    pdf_auditoria._revisar_equivalencias(
        hallazgos, _EtiquetadoConPares(etiquetas={"Portada": 1, "P": 40}),
        _DiagnosticoConMapa({"Portada": "Sect"}))

    assert "ETIQUETAS_SIN_EQUIVALENCIA" not in _codigos(hallazgos)


def test_cambiar_una_etiqueta_de_la_norma_que_no_se_usa_no_se_avisa():
    """Casi todo lo que sale de Word remapea «Artifact» sin usarlo nunca."""
    hallazgos = pdf_auditoria.ColeccionHallazgos()
    pdf_auditoria._revisar_equivalencias(
        hallazgos, _EtiquetadoConPares(etiquetas={"P": 40}),
        _DiagnosticoConMapa({"Artifact": "P"}))

    assert "ETIQUETAS_NORMALES_CAMBIADAS" not in _codigos(hallazgos)


def test_cambiar_una_etiqueta_de_la_norma_que_si_se_usa_se_avisa():
    hallazgos = pdf_auditoria.ColeccionHallazgos()
    pdf_auditoria._revisar_equivalencias(
        hallazgos, _EtiquetadoConPares(etiquetas={"Artifact": 12, "P": 40}),
        _DiagnosticoConMapa({"Artifact": "P"}))

    assert "ETIQUETAS_NORMALES_CAMBIADAS" in _codigos(hallazgos)


def test_una_equivalencia_circular_se_detecta():
    assert pdf_auditoria._mapa_circular({"Uno": "Dos", "Dos": "Uno"})
    assert not pdf_auditoria._mapa_circular({"Uno": "Sect", "Dos": "P"})


def test_mezclar_las_dos_formas_de_titular_se_avisa():
    """O «H» a secas o «H1» a «H6», pero no las dos: la norma lo dice así."""
    hallazgos = pdf_auditoria.ColeccionHallazgos()
    pdf_auditoria._revisar_niveles_mezclados(hallazgos, {"H", "H2", "P"})

    assert "TITULOS_MEZCLADOS" in _codigos(hallazgos)

    solo_una = pdf_auditoria.ColeccionHallazgos()
    pdf_auditoria._revisar_niveles_mezclados(solo_una, {"H1", "H2", "P"})
    assert not _codigos(solo_una)


# ---------------------------------------------------------------------------
# El modo gráfico: ver un PDF escaneado sin reconocerlo
# ---------------------------------------------------------------------------

def test_el_modo_grafico_esta_entre_los_que_se_pueden_elegir():
    """Un cómic o un manga no tienen texto que sacar: se ven, no se reconocen."""
    from formatos import ocr

    claves = [clave for clave, _rotulo in ocr.nombres_de_modo()]
    assert "grafico" in claves


def test_el_aviso_de_pdf_escaneado_ofrece_ver_las_paginas():
    """Quien apaga el reconocimiento tiene que saber que hay otra salida."""
    from formatos import ocr

    aviso = ocr.motivo_sin_ocr("ninguno")
    assert "im" in aviso.lower()
    assert "Control+I" in aviso


def test_una_pagina_entera_se_escribe_como_una_imagen_de_toda_la_pagina():
    """Se reutiliza la referencia de las figuras: ver y describir ya funcionan."""
    class _PaginaFalsa:
        @staticmethod
        def get_size():
            return (612.0, 792.0)

    from formatos.pdf import AnalizadorPDF

    html = AnalizadorPDF()._pagina_como_imagen([_PaginaFalsa()], 0)
    assert 'src="pdf-figura:1:0.00,0.00,612.00,792.00"' in html
    assert "alt=" in html
