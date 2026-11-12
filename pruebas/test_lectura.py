# -*- coding: utf-8 -*-
"""Pruebas de lo que se ha añadido a la lectura.

Estadísticas, perfiles, notas al pie, el capítulo como HTML y el reparto del
texto que se le manda a la inteligencia artificial.
"""

import time
from unittest import mock

import pytest

from nucleo import estadisticas, perfiles
from nucleo.ia import preguntas
from nucleo.marcas import ColeccionMarcas, Marca, TipoMarca


# ---------------------------------------------------------------------------
# Estadísticas de lectura
# ---------------------------------------------------------------------------

def _leer_durante(crono, latidos, segundos_por_latido, caracteres_por_latido):
    """Simula una lectura con el reloj controlado."""
    base = 1000.0
    with mock.patch("nucleo.estadisticas.time.monotonic") as reloj:
        for numero in range(latidos):
            reloj.return_value = base + numero * segundos_por_latido
            crono.latido(numero * caracteres_por_latido)
    return crono


def test_se_cuenta_el_tiempo_leido():
    crono = _leer_durante(estadisticas.Cronometro(), 61, 10, 250)
    # Sesenta huecos de diez segundos.
    assert 590 <= crono.segundos <= 610
    assert crono.caracteres == 60 * 250


def test_un_hueco_largo_no_cuenta():
    """Quien deja el programa abierto toda la noche no ha leído toda la noche."""
    crono = estadisticas.Cronometro()
    with mock.patch("nucleo.estadisticas.time.monotonic") as reloj:
        reloj.return_value = 0.0
        crono.latido(0)
        reloj.return_value = 10.0
        crono.latido(1000)
        # Se ha ido a cenar: dos horas.
        reloj.return_value = 7200.0
        crono.latido(1000)
        reloj.return_value = 7210.0
        crono.latido(2000)
    assert crono.segundos == pytest.approx(20.0)


def test_volver_atras_no_infla_el_ritmo():
    """Releer no es texto nuevo."""
    crono = estadisticas.Cronometro()
    with mock.patch("nucleo.estadisticas.time.monotonic") as reloj:
        reloj.return_value = 0.0
        crono.latido(1000)
        reloj.return_value = 10.0
        crono.latido(2000)     # avanza mil
        reloj.return_value = 20.0
        crono.latido(500)      # vuelve atrás: no suma
        reloj.return_value = 30.0
        crono.latido(1500)     # avanza mil desde 500
    assert crono.caracteres == 2000


def test_sin_datos_no_se_inventa_un_ritmo():
    crono = estadisticas.Cronometro()
    assert not crono.hay_datos
    assert crono.ritmo() == 0.0
    assert crono.queda(100000) == 0.0
    lineas = estadisticas.resumen(crono, 0, 1000)
    assert any("más" in linea for linea in lineas)


def test_ritmo_y_lo_que_queda():
    crono = estadisticas.Cronometro(segundos=600.0, caracteres=15000)
    # 25 caracteres por segundo, unas 250 palabras por minuto.
    assert crono.palabras_por_minuto() == 250
    # Quedan 15000 caracteres: otros 600 segundos.
    assert crono.queda(15000) == pytest.approx(600.0)


def test_salto_explicito_no_cuenta_y_lectura_posterior_si():
    crono = estadisticas.Cronometro()
    with mock.patch("nucleo.estadisticas.time.monotonic", side_effect=[0, 60, 120]):
        crono.latido(0)
        crono.latido(3000, salto=True)
        crono.latido(4500)
    assert crono.segundos == 60
    assert crono.caracteres == 1500
    assert crono.palabras_por_minuto() == 250


def test_salto_de_14069_ppm_se_descarta_sin_contaminar_siguiente_intervalo():
    crono = estadisticas.Cronometro()
    with mock.patch("nucleo.estadisticas.time.monotonic", side_effect=[0, 60, 120]):
        crono.latido(0)
        crono.latido(84414)
        assert not crono.hay_datos
        crono.latido(85914)
    assert crono.segundos == 60
    assert crono.palabras_por_minuto() == 250


def test_media_antigua_disparada_conserva_tiempo_y_reaprende():
    crono = estadisticas.Cronometro.desde_dict({"segundos": 60, "caracteres": 84414})
    assert crono.segundos == 60
    assert not crono.hay_datos
    # Guardar y abrir de nuevo antes de reunir una muestra completa.
    crono = estadisticas.Cronometro.desde_dict(crono.como_dict())
    with mock.patch("nucleo.estadisticas.time.monotonic", side_effect=[0, 30, 60]):
        crono.latido(0)
        crono.latido(750)
        assert not crono.hay_datos
        crono.latido(1500)
    assert crono.segundos == 120
    assert crono.palabras_por_minuto() == 250
    copia = estadisticas.Cronometro.desde_dict(crono.como_dict())
    assert copia.palabras_por_minuto() == 250


def test_porcentaje_independiente_del_ritmo_y_final_claro():
    documento = DocumentoDePrueba("x" * 10000)
    lento = estadisticas.Cronometro(segundos=600, caracteres=15000)
    rapido = estadisticas.Cronometro(segundos=600, caracteres=30000)
    for crono in (lento, rapido, estadisticas.Cronometro()):
        aviso = estadisticas.cuanto_queda(crono, documento, 1000)
        assert "Posición en el documento: 10 por ciento" in aviso
        final = estadisticas.cuanto_queda(crono, documento, 10000)
        assert "Has llegado al final" in final
        assert "100 por ciento" in final
        assert "menos de un minuto" not in final


@pytest.mark.parametrize("datos", [
    {"segundos": float("nan"), "caracteres": 10},
    {"segundos": float("inf"), "caracteres": 10},
    {"segundos": -1, "caracteres": 10},
    {"segundos": 60, "caracteres": -1},
])
def test_estadisticas_invalidas_no_producen_ritmo(datos):
    assert not estadisticas.Cronometro.desde_dict(datos).hay_datos


@pytest.mark.parametrize("segundos, esperado", [
    (30, "menos de un minuto"),
    (60, "1 minuto"),
    (120, "2 minutos"),
    (3600, "1 hora"),
    (7200, "2 horas"),
    (3660, "1 hora y 1 minuto"),
    (7500, "2 horas y 5 minutos"),
])
def test_duracion_legible(segundos, esperado):
    """Nada de «02:47:13»: eso son once números seguidos leídos en voz alta."""
    assert estadisticas.duracion(segundos) == esperado


def test_el_cronometro_va_y_vuelve_del_json():
    crono = estadisticas.Cronometro(segundos=123.4, caracteres=5678)
    copia = estadisticas.Cronometro.desde_dict(crono.como_dict())
    assert copia.segundos == pytest.approx(123.4)
    assert copia.caracteres == 5678


def test_un_json_estropeado_no_revienta():
    assert estadisticas.Cronometro.desde_dict("esto no es un dict").segundos == 0
    assert estadisticas.Cronometro.desde_dict({"segundos": "x"}).caracteres == 0


# ---------------------------------------------------------------------------
# Perfiles de lectura
# ---------------------------------------------------------------------------

def test_guardar_y_aplicar_un_perfil(configuracion):
    configuracion.establecer("voz_rapidez", 70)
    configuracion.establecer("sonidos_activados", False)
    assert perfiles.guardar(configuracion, "Novela")

    configuracion.establecer("voz_rapidez", 30)
    configuracion.establecer("sonidos_activados", True)
    perfiles.aplicar(configuracion, "Novela")

    assert configuracion.obtener("voz_rapidez") == 70
    assert configuracion.obtener("sonidos_activados") is False
    assert perfiles.activo(configuracion) == "Novela"


def test_un_perfil_no_toca_lo_que_no_es_suyo(configuracion):
    """Las claves API y el idioma no son cosa del perfil."""
    configuracion.establecer("ia_gemini_claves", ["secreta"])
    configuracion.establecer("idioma", "en")
    perfiles.guardar(configuracion, "Uno")
    configuracion.establecer("ia_gemini_claves", ["otra"])
    perfiles.aplicar(configuracion, "Uno")
    assert configuracion.obtener("ia_gemini_claves") == ["otra"]
    assert configuracion.obtener("idioma") == "en"


def test_aplicar_avisa_de_lo_que_obliga_a_reabrir(configuracion):
    configuracion.establecer("tablas_en_linea", True)
    perfiles.guardar(configuracion, "Con tablas")
    configuracion.establecer("tablas_en_linea", False)
    assert perfiles.aplicar(configuracion, "Con tablas") == ["tablas_en_linea"]


def test_aplicar_no_avisa_si_no_cambia_nada(configuracion):
    perfiles.guardar(configuracion, "Igual")
    assert perfiles.aplicar(configuracion, "Igual") == []


def test_borrar_un_perfil(configuracion):
    perfiles.guardar(configuracion, "Uno")
    perfiles.borrar(configuracion, "Uno")
    assert perfiles.nombres(configuracion) == []
    assert perfiles.activo(configuracion) == ""


def test_no_se_guarda_un_perfil_sin_nombre(configuracion):
    assert not perfiles.guardar(configuracion, "   ")
    assert perfiles.nombres(configuracion) == []


def test_tope_de_perfiles(configuracion):
    for numero in range(perfiles.MAXIMO):
        assert perfiles.guardar(configuracion, "Perfil %d" % numero)
    assert not perfiles.guardar(configuracion, "Uno de más")
    # Pero sí se puede sustituir uno que ya existe.
    assert perfiles.guardar(configuracion, "Perfil 0")


def test_un_perfil_viejo_con_ajustes_que_ya_no_existen(configuracion):
    configuracion.establecer("perfiles", {"Viejo": {"voz_rapidez": 40,
                                                    "ajuste_inventado": 1}})
    guardado = perfiles.leer(configuracion)["Viejo"]
    assert "ajuste_inventado" not in guardado
    assert guardado["voz_rapidez"] == 40


def test_los_ejemplos_se_describen(configuracion):
    for _nombre, valores in perfiles.sugeridos().items():
        assert perfiles.descripcion(valores)


# ---------------------------------------------------------------------------
# El texto que se le manda a la IA
# ---------------------------------------------------------------------------

class Metadatos:
    titulo = "El libro"
    autor = "Quien sea"


class DocumentoDePrueba:
    def __init__(self, texto, marcas=()):
        self.texto = texto
        self.metadatos = Metadatos()
        self.marcas = ColeccionMarcas(marcas)

    def primera_linea_con_texto(self, posicion):
        return self.texto[posicion:posicion + 30]


def test_el_capitulo_es_el_que_toca():
    texto = "Portada.\nCapítulo uno y su texto.\nCapítulo dos y el suyo."
    marcas = [Marca(TipoMarca.SALTO_SECCION, 9, "Uno", "", 0, 0),
              Marca(TipoMarca.SALTO_SECCION, 33, "Dos", "", 0, 0)]
    documento = DocumentoDePrueba(texto, marcas)
    trozo = preguntas.capitulo_en(documento, 15)
    assert "Capítulo uno" in trozo.texto
    assert "Capítulo dos" not in trozo.texto
    assert "Uno" in trozo.rotulo


def test_lo_leido_no_destripa_el_final():
    """Es lo que hace que se pueda pedir «resúmeme lo que llevo»."""
    texto = "Empieza bien. " * 10 + "Y al final muere el mayordomo."
    trozo = preguntas.leido_hasta(DocumentoDePrueba(texto), 100)
    assert "mayordomo" not in trozo.texto


def test_un_texto_enorme_se_recorta_y_se_dice():
    texto = "Una frase larguísima que se repite. " * 5000
    trozo = preguntas.documento_entero(DocumentoDePrueba(texto))
    assert trozo.recortado
    assert len(trozo.texto) <= preguntas.MAXIMO
    # Y se corta en un final de frase, no a mitad de palabra.
    assert trozo.texto.rstrip().endswith(".")


def test_la_peticion_lleva_todo_lo_que_hace_falta():
    trozo = preguntas.Trozo("El texto del capítulo.", "este capítulo")
    peticion = preguntas.armar("Resume esto.", trozo, "El libro", "Quien sea")
    assert "El libro" in peticion
    assert "Quien sea" in peticion
    assert "El texto del capítulo." in peticion
    assert "Resume esto." in peticion
    # Y le dice que no invente ni use markdown, que es lo que estropea la
    # respuesta cuando se escucha con un lector de pantalla.
    assert "markdown" in peticion.lower()


def test_la_peticion_avisa_de_que_va_recortada():
    trozo = preguntas.Trozo("x", "este capítulo", recortado=True)
    assert "recortado" in preguntas.armar("Resume.", trozo)


def test_el_ambito_de_seleccion_manda_si_hay_seleccion():
    documento = DocumentoDePrueba("Uno dos tres.")
    trozo = preguntas.trozo_para("seleccion", documento, 0, "lo seleccionado")
    assert trozo.texto == "lo seleccionado"


def test_sin_seleccion_el_ambito_de_seleccion_cae_en_el_capitulo():
    documento = DocumentoDePrueba("Uno dos tres.")
    trozo = preguntas.trozo_para("seleccion", documento, 0, "   ")
    assert "Uno dos tres." in trozo.texto


def test_todas_las_preguntas_hechas_tienen_instruccion():
    for clave, nombre, instruccion in preguntas.PREGUNTAS:
        assert nombre
        # La libre es la única sin instrucción: la escribe el usuario.
        assert instruccion or clave == "libre"


# ---------------------------------------------------------------------------
# El capítulo como HTML
# ---------------------------------------------------------------------------

def test_el_capitulo_como_html_recupera_los_encabezados():
    from nucleo import html_elementos

    texto = "Capítulo uno\nUn párrafo.\nUn apartado\nOtro párrafo."
    marcas = [
        Marca(TipoMarca.SALTO_SECCION, 0, "Capítulo uno", "", 0, 0),
        Marca(TipoMarca.ENCABEZADO1, 0, "Capítulo uno", "", 1, 12),
        Marca(TipoMarca.ENCABEZADO2, 25, "Un apartado", "", 2, 11),
    ]
    titulo, cuerpo = html_elementos.html_de_capitulo(
        DocumentoDePrueba(texto, marcas), 5)
    assert titulo == "Capítulo uno"
    assert "<h1>Capítulo uno</h1>" in cuerpo
    assert "<h2>Un apartado</h2>" in cuerpo
    assert "<p>Un párrafo.</p>" in cuerpo
    # El título no sale dos veces.
    assert cuerpo.count("Capítulo uno") == 1


def test_el_capitulo_sin_encabezados_pone_uno():
    from nucleo import html_elementos

    documento = DocumentoDePrueba("Primera línea.\nSegunda línea.")
    _titulo, cuerpo = html_elementos.html_de_capitulo(documento, 0)
    assert cuerpo.startswith("<h1>Primera línea.</h1>")
    assert "<p>Segunda línea.</p>" in cuerpo


def test_el_html_del_capitulo_escapa_lo_que_parece_html():
    from nucleo import html_elementos

    documento = DocumentoDePrueba("Un <script>malo</script> suelto.")
    _titulo, cuerpo = html_elementos.html_de_capitulo(documento, 0)
    assert "<script>" not in cuerpo


# ---------------------------------------------------------------------------
# Notas al pie
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("atributos", [
    'epub:type="noteref"',
    'role="doc-noteref"',
    'class="footnote"',
    'class="noteref"',
    'epub:type="rearnote"',
])
def test_se_reconocen_las_llamadas_de_nota(atributos):
    """Cada libro lo dice a su manera; hay que aceptarlas todas."""
    from formatos.conversor import ConversorXHTML

    xhtml = ('<html xmlns="http://www.w3.org/1999/xhtml" '
             'xmlns:epub="http://www.idpf.org/2007/ops"><body>'
             '<p>Texto<a %s href="#n1">1</a>.</p></body></html>' % atributos)
    resultado = ConversorXHTML().convertir(xhtml.encode("utf-8"))
    tipos = [marca.tipo for marca in resultado.marcas]
    assert TipoMarca.NOTA_PIE in tipos, atributos
    # Y sigue siendo un enlace, para que Intro la active como siempre.
    assert TipoMarca.ENLACE in tipos


def test_un_enlace_normal_no_es_una_nota():
    from formatos.conversor import ConversorXHTML

    xhtml = (b'<html xmlns="http://www.w3.org/1999/xhtml"><body>'
             b'<p><a href="https://ejemplo.org">Un enlace</a>.</p></body></html>')
    resultado = ConversorXHTML().convertir(xhtml)
    assert TipoMarca.NOTA_PIE not in [marca.tipo for marca in resultado.marcas]
