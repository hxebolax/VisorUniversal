# -*- coding: utf-8 -*-
"""Pruebas del diccionario.

Las consultas de red no se prueban aquí: dependen de que el servicio esté
levantado y de que no haya cambiado su página, y una prueba que falla por eso
no dice nada del programa.  Lo que sí se prueba es todo lo que decide **qué se
consulta** y **cómo se interpreta lo que llega**, con páginas guardadas.
"""

import pytest

from nucleo import diccionario


# --- la palabra que hay bajo el cursor ---------------------------------------

TEXTO = "El niño corría por el parque hasta que se cansó."


@pytest.mark.parametrize("posicion, esperado", [
    (0, "El"),
    (3, "niño"),
    (8, "corría"),
    (2, "El"),        # en el espacio: se coge la palabra de detrás
    (46, "cansó"),    # el punto final no forma parte de la palabra
])
def test_palabra_en_una_posicion(posicion, esperado):
    assert diccionario.palabra_en(TEXTO, posicion) == esperado


def test_palabra_con_guion():
    assert diccionario.palabra_en("un arco-iris bonito", 5) == "arco-iris"


def test_palabra_en_texto_vacio():
    assert diccionario.palabra_en("", 0) == ""


def test_palabra_fuera_de_rango():
    assert diccionario.palabra_en(TEXTO, 9999) == "cansó"


@pytest.mark.parametrize("texto, posicion, esperado", [
    # Sobre un signo de abrir: la palabra a la que va pegado.
    ("dijo «resiliencia» y calló", 5, "resiliencia"),
    ("¿Qué pasa?", 0, "Qué"),
    ("(nota) al margen", 0, "nota"),
    # Sobre uno de cerrar: la misma palabra, que queda a la izquierda.
    ("dijo «resiliencia» y calló", 17, "resiliencia"),
    # En la sangría del principio de una línea: la primera palabra.
    ("  Control  Abrir", 0, "Control"),
    # Entre dos palabras separadas por un punto: manda la de la izquierda,
    # que es la que se acaba de leer.
    ("hola.  mundo", 5, "hola"),
])
def test_palabra_pegada_a_un_signo(texto, posicion, esperado):
    """El cursor casi nunca cae justo encima de la letra que interesa."""
    assert diccionario.palabra_en(texto, posicion) == esperado


def test_en_la_pantalla_de_bienvenida():
    """El título de la bienvenida también es texto del que definir palabras."""
    assert diccionario.palabra_en("VISOR UNIVERSAL 1.1.0", 0) == "VISOR"
    assert diccionario.palabra_en("VISOR UNIVERSAL 1.1.0", 5) == "VISOR"
    assert diccionario.palabra_en("VISOR UNIVERSAL 1.1.0", 6) == "UNIVERSAL"


def test_no_se_salta_de_renglon_buscando_palabra():
    """La palabra del renglón de al lado no es la que se tenía delante."""
    # El cursor está en la sangría de la segunda línea: coge «dos», no «uno».
    assert diccionario.palabra_en("uno\n  dos", 4) == "dos"
    # Pero puesto sobre el propio salto de línea, al final de «uno», es «uno».
    assert diccionario.palabra_en("uno\n  dos", 3) == "uno"


def test_una_linea_sin_palabras_no_inventa_nada():
    assert diccionario.palabra_en("-- ** --", 3) == ""


@pytest.mark.parametrize("crudo, esperado", [
    ("  «Casa».  ", "Casa"),
    ('"palabra"', "palabra"),
    ("¿qué?", "qué"),
    ("...puntos...", "puntos"),
])
def test_limpiar(crudo, esperado):
    assert diccionario.limpiar(crudo) == esperado


def test_limpiar_recorta_lo_larguisimo():
    largo = "palabra " * 40
    assert len(diccionario.limpiar(largo)) <= diccionario.MAXIMO


@pytest.mark.parametrize("palabra, vale", [
    ("casa", True),
    ("Ana", True),
    ("42", False),
    ("...", False),
    ("", False),
    ("a" * 100, False),
])
def test_es_valida(palabra, vale):
    assert diccionario.es_valida(palabra) is vale


def test_frase_alrededor():
    contexto = diccionario.frase_en(TEXTO, 10, margen=8)
    assert "corría" in contexto
    assert len(contexto) <= 20


# --- lectura de la página del DLE ---------------------------------------------

PAGINA_DLE = """<html><body><article>
  <div class="n2 c-text-intro">Del lat. <i>casa</i> 'choza'.</div>
  <ol class="c-definitions">
    <li class="j" id="a1"><div role="definition"><div>
      <span class="n_acep">1. </span><abbr class="d" title="femenino">f.</abbr>
      Edificio para habitar.</div></div>
      <div class="c-definitions__item-footer"><div class="c-word-list">
        <abbr class="sin-header-inline">Sin.:</abbr>
        <span class="sin">vivienda</span>, <span class="sin">hogar</span>
      </div></div>
    </li>
    <li class="j" id="a2"><div role="definition"><div>
      <span class="n_acep">2. </span><abbr class="d">f.</abbr>
      Familia o linaje.</div></div>
      <div class="c-definitions__item-footer"><div class="c-word-list">
        <abbr class="sin-header-inline">Ant.:</abbr>
        <span class="sin">plebe</span>
      </div></div>
    </li>
  </ol>
</article></body></html>"""


def test_lectura_del_dle(monkeypatch):
    monkeypatch.setattr(diccionario, "_descargar", lambda url, espera=20: PAGINA_DLE)
    entrada = diccionario.consultar_rae("casa")
    assert not entrada.error
    assert entrada.etimologia.startswith("Del lat.")
    assert len(entrada.acepciones) == 2
    primera = entrada.acepciones[0]
    assert primera.numero == 1
    assert primera.categoria == "f."
    assert primera.texto == "Edificio para habitar."
    assert primera.sinonimos == ["vivienda", "hogar"]
    assert entrada.acepciones[1].antonimos == ["plebe"]


def test_el_numero_y_la_abreviatura_no_ensucian_la_definicion(monkeypatch):
    """Se quitan del texto porque van en sus propios campos."""
    monkeypatch.setattr(diccionario, "_descargar", lambda url, espera=20: PAGINA_DLE)
    entrada = diccionario.consultar_rae("casa")
    assert "1." not in entrada.acepciones[0].texto
    assert "f." not in entrada.acepciones[0].texto


def test_palabra_que_no_esta_en_el_dle(monkeypatch):
    monkeypatch.setattr(
        diccionario, "_descargar",
        lambda url, espera=20: "<html>La entrada no se encuentra en el Diccionario</html>")
    entrada = diccionario.consultar_rae("qwertyasdf")
    assert entrada.error
    assert entrada.vacia


def test_sin_conexion_no_lanza(monkeypatch):
    def caer(url, espera=20):
        raise OSError("sin red")

    monkeypatch.setattr(diccionario, "_descargar", caer)
    entrada = diccionario.consultar_rae("casa")
    assert entrada.error
    assert "sin red" in entrada.error


# --- Wikcionario ----------------------------------------------------------------

def test_lectura_del_wikcionario(monkeypatch):
    respuesta = ('{"query": {"pages": [{"title": "casa", "extract": '
                 '"== Espa\\u00f1ol ==\\n\\n=== Sustantivo ===\\nEdificio.\\n'
                 '\\n=== Traducciones ===\\nen: house"}]}}')
    monkeypatch.setattr(diccionario, "_descargar", lambda url, espera=20: respuesta)
    entrada = diccionario.consultar_wikcionario("casa")
    assert not entrada.error
    assert "Edificio." in entrada.texto
    # Las traducciones no interesan a quien está leyendo un libro.
    assert "house" not in entrada.texto
    # Los signos de igual de los encabezados no se leen uno a uno.
    assert "===" not in entrada.texto


def test_wikcionario_sin_la_palabra(monkeypatch):
    monkeypatch.setattr(
        diccionario, "_descargar",
        lambda url, espera=20: '{"query": {"pages": [{"missing": true}]}}')
    entrada = diccionario.consultar_wikcionario("qwertyasdf")
    assert entrada.error
    assert entrada.vacia


# --- inteligencia artificial ------------------------------------------------------

class ServicioDePrueba:
    """Un servicio de IA de mentira, que devuelve lo que se le diga."""

    def __init__(self, respuesta="", error=None):
        self.respuesta = respuesta
        self.error = error
        self.pregunta = ""

    def preguntar(self, pregunta):
        self.pregunta = pregunta
        if self.error:
            raise self.error
        return self.respuesta


def test_la_ia_recibe_el_contexto():
    servicio = ServicioDePrueba("(sustantivo) Asiento largo.")
    entrada = diccionario.consultar_ia("banco", servicio,
                                       contexto="Se sentó en el banco del parque")
    assert "banco" in servicio.pregunta
    assert "parque" in servicio.pregunta
    assert entrada.texto.startswith("(sustantivo)")


def test_la_ia_sin_contexto_usa_la_otra_pregunta():
    servicio = ServicioDePrueba("algo")
    diccionario.consultar_ia("banco", servicio)
    assert "fragmento" not in servicio.pregunta


def test_error_de_la_ia_se_cuenta():
    servicio = ServicioDePrueba(error=RuntimeError("sin cuota"))
    entrada = diccionario.consultar_ia("banco", servicio)
    assert "sin cuota" in entrada.error


# --- reparto ---------------------------------------------------------------------

def test_definir_rechaza_lo_que_no_es_palabra():
    entrada = diccionario.definir("42", diccionario.RAE)
    assert entrada.error


def test_definir_sin_servicio_de_ia():
    entrada = diccionario.definir("casa", diccionario.IA, servicio=None)
    assert entrada.error


def test_legible_incluye_todo(monkeypatch):
    monkeypatch.setattr(diccionario, "_descargar", lambda url, espera=20: PAGINA_DLE)
    texto = diccionario.consultar_rae("casa").legible()
    assert "casa" in texto
    assert "Etimología" in texto
    assert "Edificio para habitar." in texto
    assert "vivienda" in texto
