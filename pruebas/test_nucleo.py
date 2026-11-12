# -*- coding: utf-8 -*-
"""Pruebas de las piezas del núcleo que llevaban más tiempo sin batería.

Son las que sostienen todo lo demás: partir en frases, convertir a texto,
guardar y recuperar los ajustes, y saber dónde está cada cosa dentro del
documento.  Un fallo aquí no se nota en una pantalla concreta: se nota en todas.
"""

import pytest

import pathlib

from nucleo import idioma, marcado, segmentador, texto as util_texto
from nucleo.marcas import ColeccionMarcas, Marca, TipoMarca, es_encabezado, tipo_de_encabezado


# --- partir en frases ---------------------------------------------------------

def test_frase_simple():
    inicio, fin = segmentador.siguiente_frase("Hola. Adiós.", 0)
    assert "Hola." == "Hola. Adiós."[inicio:fin].strip()


def test_las_abreviaturas_no_parten_la_frase():
    frase = "Vino el Sr. Pérez a las ocho. Después se fue."
    inicio, fin = segmentador.siguiente_frase(frase, 0)
    assert frase[inicio:fin].strip() == "Vino el Sr. Pérez a las ocho."


def test_los_decimales_no_parten_la_frase():
    frase = "Costó 3.50 euros. Y sobró."
    inicio, fin = segmentador.siguiente_frase(frase, 0)
    assert frase[inicio:fin].strip() == "Costó 3.50 euros."


def test_frase_anterior():
    """Desde dentro de una frase se vuelve al principio de esa misma frase.

    Es lo que hace que «frase anterior» sirva para releer lo que no se ha
    entendido: si saltara a la frase de antes, habría que dar dos veces.
    """
    frase = "Una. Dos. Tres."
    destino, _fin = segmentador.frase_anterior(frase, 12)
    assert frase[destino:].startswith("Tres.")
    # Y desde el principio de una frase sí se retrocede a la anterior.
    destino, _fin = segmentador.frase_anterior(frase, destino)
    assert frase[destino:].startswith("Dos.")


def test_para_decir_colapsa_espacios():
    assert segmentador.para_decir("Hola\n\n  mundo\t.") == "Hola mundo ."


def test_frase_al_final_del_texto():
    inicio, fin = segmentador.siguiente_frase("Sin punto final", 0)
    assert "Sin punto final"[inicio:fin] == "Sin punto final"


def test_frase_en_texto_vacio():
    inicio, fin = segmentador.siguiente_frase("", 0)
    assert inicio >= fin


# --- partir en renglones ------------------------------------------------------
#
# Esto es lo que hace que la lectura continua del lector de pantalla deje el
# cursor en la frase que sonaba y no al principio del párrafo.  La condición que
# lo sostiene todo es que el texto no cambie de longitud: si cambiara, cada
# marcador, cada nota y cada resaltado del libro apuntaría a otro sitio.

def test_cada_frase_queda_en_su_renglon():
    partido = segmentador.partir_en_renglones("Una cosa clara. Y otra distinta.")
    assert partido.split("\n") == ["Una cosa clara.", "Y otra distinta."]


def test_partir_en_renglones_no_mueve_ni_una_posicion():
    """La condición de la que depende todo lo demás."""
    original = ("Vino el Sr. Pérez a las ocho. Costó 3.50 euros. «Ya me voy.» Dijo eso.\n"
                "IV. La guerra del Peloponeso duró casi treinta años. 1. Primero esto.\n")
    partido = segmentador.partir_en_renglones(original)
    assert len(partido) == len(original)
    # Lo único que cambia es que algunos espacios pasan a ser saltos de línea.
    for antes, despues in zip(original, partido):
        assert antes == despues or (antes == " " and despues == "\n")


def test_no_se_parte_donde_la_voz_tampoco_partiria():
    """Las abreviaturas, los decimales y las enumeraciones no son frases."""
    partido = segmentador.partir_en_renglones(
        "Vino el Sr. Pérez a las ocho. Costó 3.50 euros. Y pág. 45 lo dice.")
    assert partido.split("\n") == ["Vino el Sr. Pérez a las ocho.",
                                   "Costó 3.50 euros.",
                                   "Y pág. 45 lo dice."]


def test_la_enumeracion_del_principio_no_es_una_frase():
    partido = segmentador.partir_en_renglones("IV. La guerra del Peloponeso.")
    assert partido == "IV. La guerra del Peloponeso."


def test_un_parrafo_sin_puntuacion_tambien_se_parte():
    """Poesía, listas y textos antiguos: sin esto seguirían siendo un renglón."""
    largo = "palabra, " * 200
    partido = segmentador.partir_en_renglones(largo)
    assert len(partido) == len(largo)
    renglones = partido.split("\n")
    assert len(renglones) > 1
    assert all(len(renglon) <= segmentador.LARGO_MAXIMO for renglon in renglones)


def test_los_saltos_del_libro_se_respetan():
    """Un párrafo no se junta con el siguiente ni se parte por su salto."""
    original = "Primer párrafo entero.\nSegundo párrafo entero.\n"
    assert segmentador.partir_en_renglones(original) == original


def test_los_cortes_apuntan_siempre_a_un_espacio():
    """De ahí sale que la longitud no cambie: se cambia un espacio, no se añade."""
    texto = "Una. Dos.\tTres.  Cuatro. " + "sin puntuacion " * 60
    for corte in segmentador.cortes_de_renglon(texto):
        assert texto[corte] in " \t"


# --- marcas -------------------------------------------------------------------

def test_encabezados():
    assert es_encabezado(TipoMarca.ENCABEZADO1)
    assert es_encabezado(TipoMarca.ENCABEZADO6)
    assert not es_encabezado(TipoMarca.TABLA)
    assert tipo_de_encabezado(3) is TipoMarca.ENCABEZADO3
    # Los niveles fuera de rango se acotan en vez de reventar.
    assert tipo_de_encabezado(0) is TipoMarca.ENCABEZADO1
    assert tipo_de_encabezado(99) is TipoMarca.ENCABEZADO6


def test_la_formula_es_un_tipo_nuevo_al_final():
    """Los valores se guardan en la caché: solo se puede añadir al final."""
    assert int(TipoMarca.FORMULA) == 19
    assert int(TipoMarca.ENCABEZADO1) == 0
    assert int(TipoMarca.CITA) == 18


def test_grupo_de_marcas_encuentra_la_siguiente():
    marcas = [Marca(TipoMarca.TABLA, posicion, "t", "", 0, 1)
              for posicion in (10, 50, 90)]
    coleccion = ColeccionMarcas(marcas)
    grupo = coleccion.grupo(TipoMarca.TABLA)
    assert len(grupo) == 3
    assert grupo.indice_siguiente(0) == 0
    assert grupo.indice_siguiente(10) == 1
    assert grupo.indice_siguiente(90) == -1


# --- conversión a HTML del manual ------------------------------------------------

def test_marcado_encabezados_con_ancla():
    html = marcado.a_html("# Título\n\n## Uno dos\n", "T")
    assert '<h2 id="uno-dos"' in html


def test_marcado_tabla():
    html = marcado.a_html("| a | b |\n|---|---|\n| 1 | 2 |\n", "T")
    assert "<table>" in html
    assert "<td>1</td>" in html


def test_marcado_lista_y_cita():
    html = marcado.a_html("- uno\n- dos\n\n> una cita\n", "T")
    assert "<ul>" in html and "<li>uno</li>" in html
    assert "<blockquote>" in html


def test_marcado_escapa_lo_que_parece_html():
    html = marcado.a_html("Un <script>alert(1)</script> suelto\n", "T")
    assert "<script>" not in html


# --- utilidades de texto ----------------------------------------------------------

def test_colapsar_espacios():
    """Los saltos de línea se vuelven espacios; los de los bordes se respetan.

    Se respetan a propósito: el conversor pega trozos uno detrás de otro, y
    perder el espacio del borde pegaría la última palabra de un trozo con la
    primera del siguiente.
    """
    assert util_texto.colapsar_espacios("  a \n b  ") == " a b "
    assert util_texto.colapsar_espacios("a\n\nb") == "a b"


# --- idioma y plurales ------------------------------------------------------------

def test_plural_en_espanol():
    idioma.instalar("es")
    from nucleo.idioma import _n

    assert _n("%d imagen", "%d imágenes", 1) % 1 == "1 imagen"
    assert _n("%d imagen", "%d imágenes", 0) % 0 == "0 imágenes"
    assert _n("%d imagen", "%d imágenes", 7) % 7 == "7 imágenes"


def test_plural_traducido():
    """El catálogo inglés trae las dos formas y elige la que toca."""
    idioma.instalar("en")
    from nucleo.idioma import _n

    assert _n("Lista con %d elemento.", "Lista con %d elementos.", 1) % 1 == "List with 1 item."
    assert _n("Lista con %d elemento.", "Lista con %d elementos.", 3) % 3 == "List with 3 items."
    idioma.instalar("es")


def test_todo_lo_traducible_esta_traducido_al_ingles():
    """Un texto sin traducir sale en español en medio de la interfaz inglesa."""
    import sys
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(raiz / "herramientas"))
    import textos

    simples, plurales = textos.recoger()
    traducidos, traducidos_plurales = textos._leer_po(
        textos.IDIOMAS / "en" / "LC_MESSAGES" / "visor.po")
    faltan = sorted(t for t in simples if t not in traducidos and t.strip())
    faltan_plurales = [s for (s, _p) in plurales if s not in traducidos_plurales]
    assert not faltan, "sin traducir al inglés: %r" % faltan[:5]
    assert not faltan_plurales, "plurales sin traducir: %r" % faltan_plurales


# --- configuración -----------------------------------------------------------------

def test_los_ajustes_se_guardan_y_vuelven(configuracion, carpeta):
    configuracion.establecer("voz_rapidez", 77)
    configuracion.guardar()

    from nucleo.configuracion import Configuracion

    otra = Configuracion()
    assert otra.obtener("voz_rapidez") == 77


def test_valor_por_omision_si_no_esta(configuracion):
    assert configuracion.obtener("no_existe_este_ajuste", "por omisión") == "por omisión"


def test_datos_de_un_documento(configuracion, carpeta):
    ruta = str(carpeta / "libro.epub")
    datos = configuracion.datos_de(ruta)
    datos.posicion = 1234
    datos.pronunciacion = [{"buscar": "a", "decir": "b", "palabra": True,
                            "mayusculas": False}]
    configuracion.guardar()

    from nucleo.configuracion import Configuracion

    otra = Configuracion()
    recuperados = otra.datos_de(ruta)
    assert recuperados.posicion == 1234
    assert recuperados.pronunciacion[0]["buscar"] == "a"


def test_recientes_no_se_repiten(configuracion, carpeta):
    ruta = str(carpeta / "uno.epub")
    configuracion.anadir_reciente(ruta)
    configuracion.anadir_reciente(ruta)
    assert configuracion.recientes().count(ruta) == 1


# ---------------------------------------------------------------------------
# El manual y las teclas
# ---------------------------------------------------------------------------
#
# El manual se escribe a mano y la tabla de atajos cambia con el programa, así
# que sin esto acabarían diciendo cosas distintas: se añade una orden, se le
# pone un atajo y el manual sigue sin mencionarlo durante meses.  Aquí se
# comprueba que están todas.

def _manual() -> str:
    """El manual de usuario en español, que es el original.

    Vive en la carpeta de su idioma, junto a las traducciones, para que
    traducirlo sea dejar el archivo en la carpeta de la lengua que toque.  Se
    comprueba el español a propósito: los demás llegan traducidos cuando
    llegan, y exigirles que mencionen cada tecla nueva sería tener las pruebas
    en rojo desde el día que se añade un atajo hasta el día que alguien
    traduce.
    """
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent
    manual = raiz / "data" / "idiomas" / "es" / "docs" / "MANUAL_USUARIO.md"
    return manual.read_text(encoding="utf-8")


def _como_lo_escribe_el_manual(atajo: str) -> str:
    """Traduce un atajo de la tabla a como se escribe en el manual.

    La tabla usa las abreviaturas cortas que caben en un menú («Ctrl», «Mayús»,
    «RePag»); el manual las escribe enteras, porque ahí se leen en voz alta y
    «Ctrl» no se pronuncia solo.
    """
    return (atajo.replace("Ctrl", "Control").replace("Shift", "Mayús")
                 .replace("RePag", "Re Pág").replace("AvPag", "Av Pág"))


def test_el_manual_documenta_todos_los_atajos():
    from interfaz import atajos

    manual = _manual()
    faltan = [
        "%s (%s)" % (orden.identificador, orden.atajo)
        for orden in atajos.ORDENES
        if orden.atajo and _como_lo_escribe_el_manual(orden.atajo) not in manual
    ]
    assert not faltan, "atajos que el manual no menciona: %s" % faltan


def test_el_manual_documenta_todas_las_teclas_de_una_letra():
    """Las teclas de navegación son lo más usado del programa: no puede faltar ninguna."""
    from interfaz import atajos

    manual = _manual()
    letras = {atajo.tecla for atajo in atajos.NAVEGACION}
    letras.update({atajos.SECCION_SIGUIENTE, atajos.CONTENEDOR_INICIO,
                   atajos.CONTENEDOR_FIN, atajos.MARCADOR_SIGUIENTE,
                   atajos.NOTA_SIGUIENTE, atajos.DESCRIBIR_IMAGEN,
                   atajos.DEFINIR_PALABRA, atajos.DONDE_ESTOY,
                   atajos.REPETIR_ANUNCIO})
    # Los niveles de encabezado se documentan juntos, que es como se entienden.
    assert "`1` a `6`" in manual
    faltan = sorted(tecla for tecla in letras
                    if not tecla.isdigit() and "`%s`" % tecla not in manual)
    assert not faltan, "teclas de una letra que el manual no menciona: %s" % faltan


def test_el_indice_del_manual_apunta_a_secciones_que_existen():
    import re

    def sin_tildes(texto: str) -> str:
        """Quita las tildes **antes** de armar el ancla.

        El orden importa: quitándolas después, la «á» ya se habría convertido
        en un guion y «Imágenes» daría «im-genes» en lugar de «imagenes».
        """
        for con, sin in zip("áéíóúñ", "aeioun"):
            texto = texto.replace(con, sin)
        return texto

    manual = _manual()
    anclas = {"#" + re.sub(r"[^a-z0-9]+", "-", sin_tildes(linea[3:].lower())).strip("-")
              for linea in manual.splitlines() if linea.startswith("## ")}
    enlaces = set(re.findall(r"\]\((#[a-z0-9\-]+)\)", manual))
    rotos = sorted(enlace for enlace in enlaces if enlace not in anclas)
    assert not rotos, "enlaces internos del manual que no llevan a ninguna parte: %s" % rotos


# ---------------------------------------------------------------------------
# Dónde se busca el manual
# ---------------------------------------------------------------------------
#
# El manual de cada idioma vive en «data/idiomas/<código>/docs», de modo que
# traducirlo es dejar el archivo en su carpeta.  Lo que hay que asegurar es el
# camino de vuelta: un idioma que todavía no lo tenga —que es lo normal
# mientras las traducciones van llegando— no puede dejar a nadie sin ayuda.

def test_el_manual_de_un_idioma_esta_en_su_carpeta():
    from nucleo import rutas

    español = rutas.ruta_manual("es")
    assert español.is_file()
    assert español.parent.name == rutas.NOMBRE_CARPETA_DOCS
    assert español.parent.parent.name == "es"


def test_un_idioma_sin_manual_abre_el_espanol():
    """Más vale el manual en otro idioma que ningún manual."""
    from nucleo import rutas

    # Un código que no va a existir nunca, para que la prueba no se rompa el
    # día que alguien traduzca el manual al francés.
    caido = rutas.ruta_manual("xx")
    assert caido == rutas.ruta_manual(rutas.IDIOMA_BASE)
    assert caido.is_file()


def test_una_variante_regional_usa_el_manual_de_su_idioma():
    """A quien tiene «es_MX» le sirve el manual en español."""
    from nucleo import rutas

    assert rutas.ruta_manual("es_MX") == rutas.ruta_manual("es")
    assert rutas.ruta_manual("es-MX") == rutas.ruta_manual("es")


def test_sin_manual_en_ninguna_parte_se_senala_donde_ponerlo(tmp_path, monkeypatch):
    """El aviso tiene que llevar a la carpeta buena, no a la del usuario."""
    from nucleo import rutas

    monkeypatch.setattr(rutas, "directorio_datos", lambda: tmp_path)
    perdido = rutas.ruta_manual("xx")
    assert not perdido.exists()
    assert perdido.parent.parent.name == rutas.IDIOMA_BASE


def test_se_sabe_que_idiomas_traen_manual():
    from nucleo import rutas

    assert rutas.IDIOMA_BASE in rutas.idiomas_con_manual()


# ---------------------------------------------------------------------------
# Los catálogos de idioma
# ---------------------------------------------------------------------------
#
# Un «%d» que se pierde al traducir no se ve leyendo el catálogo: revienta el
# programa el día que a alguien le toque ese mensaje, en un idioma que quien lo
# escribió probablemente no habla.  Por eso se comprueba aquí, que es donde se
# ve antes de publicar.

def _catalogos():
    """Los idiomas que hay, con sus traducciones ya leídas."""
    import sys
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent
    if str(raiz / "herramientas") not in sys.path:
        sys.path.insert(0, str(raiz / "herramientas"))
    import textos as catalogos

    originales, _plurales = catalogos.recoger()
    encontrados = {}
    for po in sorted((raiz / "data" / "idiomas").glob("*/LC_MESSAGES/visor.po")):
        codigo = po.parent.parent.name
        encontrados[codigo] = catalogos.cargar_po(codigo)
    return originales, encontrados


def _variables(texto: str):
    """Las variables de formato que lleva un texto, contadas."""
    import collections
    import re

    patron = re.compile(r"%\([^)]+\)[sdifgxXoerc]|%[-+ #0-9.]*[sdifgxXoerc]|\{[^{}]*\}")
    return collections.Counter(patron.findall(texto))


def test_ninguna_traduccion_pierde_una_variable():
    originales, catalogos = _catalogos()
    rotas = []
    for codigo, (simples, plurales) in catalogos.items():
        for original, traduccion in simples.items():
            if original in originales and _variables(original) != _variables(traduccion):
                rotas.append("%s: %r" % (codigo, original[:60]))
        for singular, (plural, formas) in plurales.items():
            for forma in formas:
                if forma and _variables(singular) != _variables(forma):
                    rotas.append("%s (plural): %r" % (codigo, singular[:60]))
    assert not rotas, "traducciones que han perdido una variable: %s" % rotas[:5]


def test_los_catalogos_no_traen_textos_que_el_programa_ya_no_tiene():
    """Sobran al cambiar un texto en el código: son peso muerto y despistan."""
    originales, catalogos = _catalogos()
    sobrantes = {codigo: [clave for clave in simples if clave not in originales]
                 for codigo, (simples, _plurales) in catalogos.items()}
    sobrantes = {codigo: cuales for codigo, cuales in sobrantes.items() if cuales}
    assert not sobrantes, ("catálogos con entradas de textos que ya no existen: %s. "
                           "Se limpian con: python herramientas/textos.py --nuevo <código>"
                           % {codigo: len(cuales) for codigo, cuales in sobrantes.items()})


def test_los_aceleradores_sobreviven_a_la_traduccion():
    """Un menú sin su letra subrayada deja de poder abrirse con Alt."""
    originales, catalogos = _catalogos()
    perdidos = []
    for codigo, (simples, _plurales) in catalogos.items():
        for original, traduccion in simples.items():
            if original not in originales or not traduccion:
                continue
            if "&" in original and "&" not in traduccion:
                perdidos.append("%s: %r" % (codigo, original[:50]))
    assert not perdidos, "traducciones que han perdido el acelerador: %s" % perdidos[:5]


def test_la_plantilla_tiene_todos_los_textos_del_programa():
    """El «.pot» es lo que se le da a quien quiera traducir: no puede ir corto."""
    import sys
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent
    if str(raiz / "herramientas") not in sys.path:
        sys.path.insert(0, str(raiz / "herramientas"))
    import textos as catalogos

    originales, plurales = catalogos.recoger()
    plantilla = (raiz / "data" / "idiomas" / "visor.pot").read_text(encoding="utf-8")
    faltan = [texto for texto in list(originales)[:400]
              if 'msgid "%s"' % catalogos._escapar(texto) not in plantilla]
    assert not faltan, ("la plantilla va por detrás del programa: faltan %d textos. "
                        "Se rehace con: python herramientas/textos.py" % len(faltan))


# --- resaltados -------------------------------------------------------------

def test_un_resaltado_es_un_marcador_con_un_pasaje_dentro():
    from nucleo.configuracion import Marcador

    resaltado = Marcador(10, 40, "", "La idea principal del apartado", True)

    assert resaltado.es_resaltado
    assert not resaltado.es_nota


def test_un_marcador_normal_no_es_un_resaltado():
    from nucleo.configuracion import Marcador

    assert not Marcador(10, 10).es_resaltado
    assert not Marcador(10, 40, "una nota").es_resaltado


def test_un_resaltado_sin_pasaje_no_cuenta():
    """Sin selección no hay pasaje que exportar, así que no es un resaltado."""
    from nucleo.configuracion import Marcador

    assert not Marcador(10, 10, "", "", True).es_resaltado


def test_los_resaltados_sobreviven_a_guardar_y_volver_a_leer():
    from nucleo.configuracion import Marcador

    original = Marcador(5, 60, "", "Un pasaje que interesa", True)
    vuelto = Marcador.desde_dict(original.como_dict())

    assert vuelto == original
    assert vuelto.es_resaltado


def test_un_marcador_de_siempre_se_sigue_leyendo_igual():
    """Los archivos de quien no use resaltados no cambian ni se rompen."""
    from nucleo.configuracion import Marcador

    antiguo = {"inicio": 3, "fin": 3, "nota": "recordar esto", "fragmento": "algo"}
    marcador = Marcador.desde_dict(antiguo)

    assert marcador.es_nota
    assert not marcador.es_resaltado
    assert "resaltado" not in marcador.como_dict()


# --- exportar los resaltados ------------------------------------------------

class _DocumentoSinPaginas:
    """Lo mínimo que la exportación le pregunta a un documento."""

    texto = "Primera idea. Segunda idea."
    total_paginas = 0

    @staticmethod
    def indice_de_pagina(posicion):
        return -1

    @staticmethod
    def porcentaje_en(posicion):
        return 12


def _pasajes():
    from nucleo import resaltados
    from nucleo.configuracion import Marcador

    marcadores = [
        Marcador(0, 14, "", "La idea principal del apartado", True),
        Marcador(20, 40, "", "Una definición que hay que repasar", True),
        Marcador(50, 50, "", "un marcador normal"),
    ]
    return resaltados.pasajes_de(_DocumentoSinPaginas(), marcadores)


def test_solo_se_exportan_los_resaltados_y_no_los_marcadores():
    pasajes = _pasajes()

    assert len(pasajes) == 2
    assert "La idea principal" in pasajes[0].texto


def test_cada_pasaje_lleva_donde_estaba():
    """Un resaltado sin referencia no se puede volver a encontrar."""
    assert _pasajes()[0].sitio == "12 por ciento"


def test_el_texto_plano_lleva_titulo_sitio_y_pasaje():
    from nucleo import resaltados

    salida = resaltados.a_txt(_pasajes(), "Mi documento", "Un autor").decode("utf-8")

    assert salida.startswith("Mi documento\nUn autor\n2 resaltados")
    assert "12 por ciento\nLa idea principal del apartado" in salida


def test_el_markdown_escribe_los_pasajes_como_citas():
    """Son palabras de otro documento, y al pegarlas tiene que notarse."""
    from nucleo import resaltados

    salida = resaltados.a_markdown(_pasajes(), "Mi documento").decode("utf-8")

    assert salida.startswith("# Mi documento")
    assert "> La idea principal del apartado" in salida
    assert "**12 por ciento**" in salida


def test_el_html_pone_cada_pasaje_en_su_cita_con_su_referencia():
    from nucleo import resaltados

    salida = resaltados.a_html(_pasajes(), "Mi documento", idioma="es").decode("utf-8")

    assert '<html lang="es">' in salida
    assert "<blockquote>" in salida
    assert "<cite>12 por ciento</cite>" in salida


def test_el_html_escapa_lo_que_venga_del_documento():
    from nucleo import resaltados

    pasaje = resaltados.Pasaje("<script>alert(1)</script>", "")
    salida = resaltados.a_html([pasaje], "Título <con> símbolos").decode("utf-8")

    assert "<script>" not in salida
    assert "&lt;script&gt;" in salida


def test_no_se_admite_un_formato_inventado(carpeta):
    import pytest as _pytest
    from nucleo import resaltados

    with _pytest.raises(ValueError):
        resaltados.exportar(_pasajes(), carpeta / "x.zzz", "zzz", "Documento")


def test_los_tres_formatos_se_escriben_de_verdad(carpeta):
    from nucleo import resaltados

    for clave, (_rotulo, extension, _filtro) in resaltados.nombres().items():
        destino = carpeta / ("resaltados" + extension)
        resaltados.exportar(_pasajes(), destino, clave, "Mi documento", "Un autor")
        assert destino.stat().st_size > 0
        assert "idea principal" in destino.read_text(encoding="utf-8")


def test_ninguna_traduccion_de_menu_lleva_una_entidad_html_a_medias():
    """Lo mismo que se comprueba en las etiquetas, en todos los idiomas.

    Una traducción puede caer en la misma trampa que el original: poner el «&»
    de la letra de acceso justo delante de «lt», «gt», «amp» o «quot» deja
    escrito el principio de una entidad HTML.
    """
    _originales, catalogos = _catalogos()
    peligrosas = ("&lt", "&gt", "&amp", "&quot")
    rotas = {}
    for codigo, (simples, plurales) in catalogos.items():
        cuales = [t for t in list(simples.values()) + [f for _p, formas in plurales.values()
                                                       for f in formas]
                  if t and any(marca in t.lower() for marca in peligrosas)]
        cuales += [t for t in simples.values() if t and ("<" in t or ">" in t)
                   and t not in cuales]
        if cuales:
            rotas[codigo] = cuales[:3]
    assert not rotas, "traducciones con una entidad HTML a medias: %s" % rotas


# --- avisar de los elementos de una línea -----------------------------------

def test_una_llamada_de_nota_suena_distinto_que_un_enlace():
    """Era el fallo: las dos sonaban igual y no había forma de distinguirlas.

    Una llamada de nota **es** un enlace —se marca como las dos cosas— y la
    tabla de prioridad no incluía la llamada, así que ganaba el enlace y las
    dos hacían el mismo pitido.  En un texto clásico, eso es no poder separar
    el número de una nota del número del pasaje.
    """
    from nucleo.marcas import TipoMarca
    from sonidos.gestor import PRIORIDAD, SONIDO_POR_MARCA

    assert TipoMarca.NOTA_PIE in PRIORIDAD
    assert PRIORIDAD.index(TipoMarca.NOTA_PIE) < PRIORIDAD.index(TipoMarca.ENLACE)
    assert SONIDO_POR_MARCA[TipoMarca.NOTA_PIE] != SONIDO_POR_MARCA[TipoMarca.ENLACE]


def test_el_pitido_y_la_voz_usan_el_mismo_orden():
    """Dos listas separadas acabarían diciendo cosas distintas."""
    from nucleo.marcas import ORDEN_DE_INTERES
    from sonidos.gestor import PRIORIDAD

    assert PRIORIDAD is ORDEN_DE_INTERES


def test_la_voz_nombra_todos_los_elementos_y_el_pitido_solo_uno():
    """Es la ventaja de la voz: el pitido tiene que elegir y ella no."""
    from nucleo.marcas import TipoMarca, nombrar

    presentes = {TipoMarca.SALTO_PAGINA, TipoMarca.NOTA_PIE, TipoMarca.ENLACE}

    dicho = nombrar(presentes)
    assert "llamada de nota" in dicho
    assert "enlace" in dicho
    assert "página" in dicho


def test_los_elementos_se_nombran_de_lo_que_mas_dice_a_lo_que_menos():
    from nucleo.marcas import TipoMarca, nombrar

    dicho = nombrar({TipoMarca.ENLACE, TipoMarca.ENCABEZADO2})
    assert dicho.startswith("encabezado de nivel 2")


def test_no_se_nombran_mas_de_tres_elementos():
    """Más de tres seguidos no se retienen y retrasan la línea."""
    from nucleo.marcas import TipoMarca, nombrar

    muchos = {TipoMarca.TABLA, TipoMarca.IMAGEN, TipoMarca.LISTA,
              TipoMarca.SALTO_PAGINA, TipoMarca.ENLACE}

    assert len(nombrar(muchos).split(", ")) == 3


def test_la_negrita_y_el_idioma_no_se_anuncian():
    """Aparecen en casi cada línea: anunciarlos sería un ruido continuo."""
    from nucleo.marcas import TipoMarca, nombrar

    assert nombrar({TipoMarca.NEGRITA, TipoMarca.CURSIVA, TipoMarca.IDIOMA}) == ""


def test_sin_elementos_no_hay_nada_que_decir():
    from nucleo.marcas import nombrar

    assert nombrar(()) == ""


# --- llamadas de nota que el libro no declara -------------------------------

def _convertir(cuerpo: str, marcar: bool = False):
    """Convierte un fragmento XHTML y devuelve ``(texto, marcas)``."""
    from formatos.conversor import ConversorXHTML

    conversor = ConversorXHTML(marcar_llamadas_de_nota=marcar)
    datos = ('<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml">'
             "<body>%s</body></html>" % cuerpo).encode("utf-8")
    resultado = conversor.convertir(datos)
    return resultado.texto, resultado.marcas


def _tipos(marcas):
    from nucleo.marcas import TipoMarca

    return {TipoMarca(marca.tipo) for marca in marcas}


def test_un_numero_entre_corchetes_que_lleva_a_las_notas_es_una_llamada():
    """El patrón de casi todos los libros anotados que circulan.

    No declaran «epub:type="noteref"» ni nada parecido: son un enlace normal a
    la sección de notas, y sin reconocerlos la tecla de notas no encontraba
    ninguna en un libro con quinientas.
    """
    from nucleo.marcas import TipoMarca

    _texto, marcas = _convertir(
        '<p>Texto<a href="notas.xhtml#nt12"><sup>[12]</sup></a> y sigue.</p>')

    assert TipoMarca.NOTA_PIE in _tipos(marcas)


def test_un_numero_en_superindice_sin_corchetes_tambien():
    from nucleo.marcas import TipoMarca

    _texto, marcas = _convertir('<p>Texto<sup><a href="#n3">3</a></sup>.</p>')

    assert TipoMarca.NOTA_PIE in _tipos(marcas)


def test_un_enlace_con_palabras_no_es_una_llamada_de_nota():
    from nucleo.marcas import TipoMarca

    _texto, marcas = _convertir('<p>Ver <a href="cap.xhtml#c2">el capítulo dos</a>.</p>')

    assert TipoMarca.NOTA_PIE not in _tipos(marcas)


def test_un_numero_suelto_sin_corchetes_ni_superindice_no_lo_es():
    """Así el índice onomástico, donde cada página es un enlace, se salva."""
    from nucleo.marcas import TipoMarca

    _texto, marcas = _convertir('<p>Alcibíades, <a href="p.xhtml#p254">254</a>.</p>')

    assert TipoMarca.NOTA_PIE not in _tipos(marcas)


def test_un_enlace_a_internet_nunca_es_una_llamada_de_nota():
    from nucleo.marcas import TipoMarca

    _texto, marcas = _convertir('<p>Ver <sup><a href="https://x.org/#12">12</a></sup>.</p>')

    assert TipoMarca.NOTA_PIE not in _tipos(marcas)


def test_un_numero_romano_no_es_una_llamada_de_nota():
    """Un «IV» casi siempre es un capítulo."""
    from nucleo.marcas import TipoMarca

    _texto, marcas = _convertir('<p>Libro <sup><a href="l.xhtml#l4">IV</a></sup>.</p>')

    assert TipoMarca.NOTA_PIE not in _tipos(marcas)


def test_la_vuelta_de_una_nota_al_texto_no_es_otra_llamada():
    """En la sección de notas, «<<» vuelve al texto: es un enlace, no una nota."""
    from nucleo.marcas import TipoMarca

    _texto, marcas = _convertir('<p id="nt1">[1] La nota. <a href="c.xhtml#rf1">&lt;&lt;</a></p>')

    assert TipoMarca.NOTA_PIE not in _tipos(marcas)


def test_lo_que_el_libro_si_declara_sigue_valiendo():
    from nucleo.marcas import TipoMarca

    _texto, marcas = _convertir(
        '<p>Texto<a class="noteref" href="#n1">nota uno</a>.</p>')

    assert TipoMarca.NOTA_PIE in _tipos(marcas)


def test_con_la_opcion_puesta_la_llamada_se_oye_como_nota():
    """Es lo único audible en la lectura continua del lector de pantalla."""
    texto, _marcas = _convertir(
        '<p>Texto<a href="notas.xhtml#nt12"><sup>[12]</sup></a>.</p>', marcar=True)

    assert "[nota 12]" in texto


def test_sin_la_opcion_el_texto_no_cambia():
    texto, _marcas = _convertir(
        '<p>Texto<a href="notas.xhtml#nt12"><sup>[12]</sup></a>.</p>')

    assert "[12]" in texto
    assert "nota" not in texto


def test_una_llamada_con_asterisco_se_dice_solo_nota():
    """«nota asterisco» no añade nada a «nota»."""
    texto, _marcas = _convertir(
        '<p>Texto<a href="n.xhtml#n1"><sup>[*]</sup></a>.</p>', marcar=True)

    assert "[nota]" in texto


def test_marcar_las_llamadas_obliga_a_volver_a_analizar():
    """Cambia el texto, así que la caché anterior ya no vale."""
    from formatos.base import OpcionesAnalisis

    assert (OpcionesAnalisis(marcar_llamadas_de_nota=True).firma()
            != OpcionesAnalisis(marcar_llamadas_de_nota=False).firma())


def test_una_ecuacion_entre_parentesis_no_es_una_llamada_de_nota():
    """Salió probando con un libro técnico de verdad.

    «la ecuación (6)», con el «(6)» enlazado a la ecuación, se estaba
    marcando como nota: los paréntesis son la forma normal de numerar
    ecuaciones, y en ese libro había dieciséis notas que no existían.
    """
    from nucleo.marcas import TipoMarca

    _texto, marcas = _convertir(
        '<p>De la ecuación <a href="#eq-cubo">(6)</a> se deduce que...</p>')

    assert TipoMarca.NOTA_PIE not in _tipos(marcas)


def test_entre_parentesis_y_en_superindice_si_lo_es():
    """Con las dos cosas ya no queda duda de que es una llamada."""
    from nucleo.marcas import TipoMarca

    _texto, marcas = _convertir('<p>Texto<sup><a href="#n6">(6)</a></sup>.</p>')

    assert TipoMarca.NOTA_PIE in _tipos(marcas)


# ---------------------------------------------------------------------------
# Bloques de código
# ---------------------------------------------------------------------------

def _documento_con_codigo():
    """Un documento de mentira con un bloque de código dentro."""
    from formatos.conversor import ConversorXHTML

    xhtml = (b'<?xml version="1.0" encoding="utf-8"?>'
             b'<html xmlns="http://www.w3.org/1999/xhtml"><body>'
             b'<p>Antes.</p>'
             b'<pre><code class="language-python">def f(x):<br/>'
             b'    return x</code></pre>'
             b'<p>Despu\xc3\xa9s.</p></body></html>')
    return ConversorXHTML().convertir(xhtml)


def test_un_bloque_pre_deja_marca_de_codigo():
    """Sin marca no se puede saltar a él, ni verlo, ni copiarlo."""
    from nucleo.marcas import TipoMarca

    resultado = _documento_con_codigo()
    codigos = [m for m in resultado.marcas if m.tipo is TipoMarca.CODIGO]
    assert len(codigos) == 1
    assert codigos[0].longitud > 0


def test_el_bloque_de_codigo_conserva_la_sangria():
    """En Python la sangría no es presentación: es lo que dice qué va dentro."""
    from nucleo.marcas import TipoMarca

    resultado = _documento_con_codigo()
    marca = next(m for m in resultado.marcas if m.tipo is TipoMarca.CODIGO)
    trozo = resultado.texto[marca.posicion:marca.posicion + marca.longitud]
    assert "    return x" in trozo


def test_se_recuerda_el_lenguaje_declarado_del_bloque():
    """«Bloque de código Python» dice mucho más que «bloque de código»."""
    from nucleo.marcas import TipoMarca

    resultado = _documento_con_codigo()
    marca = next(m for m in resultado.marcas if m.tipo is TipoMarca.CODIGO)
    assert marca.referencia == "python"


def test_un_pre_vacio_no_es_un_bloque_de_codigo():
    """Los hay usados como separación, y saltar a ellos sería saltar a la nada."""
    from formatos.conversor import ConversorXHTML
    from nucleo.marcas import TipoMarca

    xhtml = (b'<html xmlns="http://www.w3.org/1999/xhtml"><body>'
             b'<pre></pre><p>Texto.</p></body></html>')
    resultado = ConversorXHTML().convertir(xhtml)
    assert not [m for m in resultado.marcas if m.tipo is TipoMarca.CODIGO]


def test_el_markdown_entiende_las_vallas_de_codigo():
    """Es lo que lleva el LÉAME de cualquier repositorio."""
    from nucleo import marcado

    fuente = "Texto.\n\n```python\ndef f():\n    return 1\n```\n\nMás texto.\n"
    html = marcado.a_html(fuente, "")
    assert '<pre><code class="language-python">def f():\n    return 1</code></pre>' in html
    assert "```" not in html


def test_una_valla_sin_cerrar_no_se_come_el_resto_del_documento():
    """Un LÉAME mal escrito no debe dejar el documento sin texto."""
    from nucleo import marcado

    html = marcado.a_html("Texto.\n\n```\ncodigo\n", "")
    assert "<p>Texto.</p>" in html
    assert "<pre><code>codigo</code></pre>" in html


def test_el_visor_escribe_el_codigo_con_su_boton_de_copiar():
    """El botón es un botón de verdad: se alcanza con el tabulador."""
    from types import SimpleNamespace

    from nucleo import html_elementos
    from nucleo.marcas import TipoMarca

    resultado = _documento_con_codigo()
    marca = next(m for m in resultado.marcas if m.tipo is TipoMarca.CODIGO)
    documento = SimpleNamespace(texto=resultado.texto)
    cuerpo = html_elementos.html_de_codigo(documento, marca)
    assert '<button type="button" class="copiar" data-codigo="0">' in cuerpo
    assert "<pre><code" in cuerpo


def test_lo_que_copia_el_boton_es_el_codigo_exacto():
    """Con su sangría: si no, no se puede pegar y ejecutar, que es para lo que se copia."""
    from types import SimpleNamespace

    from nucleo import html_elementos
    from nucleo.marcas import TipoMarca

    resultado = _documento_con_codigo()
    marca = next(m for m in resultado.marcas if m.tipo is TipoMarca.CODIGO)
    documento = SimpleNamespace(texto=resultado.texto)
    cuerpo = html_elementos.html_de_codigo(documento, marca)
    assert html_elementos.codigos_de(cuerpo) == ["def f(x):\n    return x"]


def test_el_titulo_del_bloque_dice_el_lenguaje():
    from nucleo import html_elementos
    from nucleo.marcas import Marca, TipoMarca

    marca = Marca(TipoMarca.CODIGO, 0, "", "python", 0, 10)
    assert html_elementos.titulo_de(marca) == "Bloque de código Python"
    suelto = Marca(TipoMarca.CODIGO, 0, "", "", 0, 10)
    assert html_elementos.titulo_de(suelto) == "Bloque de código"


def test_el_bloque_de_codigo_es_un_contenedor():
    """Para poder salir de un listado de cuarenta renglones con la Z."""
    from nucleo.marcas import CONTENEDORES, TipoMarca

    assert TipoMarca.CODIGO in CONTENEDORES


def test_hay_una_tecla_para_saltar_de_bloque_de_codigo_en_bloque():
    from interfaz import atajos
    from nucleo.navegacion import Objetivo

    teclas = {atajo.tecla: atajo.objetivo for atajo in atajos.NAVEGACION}
    assert teclas.get("X") is Objetivo.CODIGO


def test_un_salto_de_pagina_no_se_lleva_por_delante_la_imagen_que_hay_al_lado():
    """En un PDF, 25 imágenes caían justo en un salto de página y se perdían.

    El recorrido escribía un solo elemento por sitio, así que el primero que
    apareciera —el salto— se quedaba la línea entera.  Son cosas distintas: el
    salto es una señal y la imagen es contenido, y las dos van.
    """
    from types import SimpleNamespace

    from nucleo import html_elementos
    from nucleo.marcas import ColeccionMarcas, Marca, TipoMarca

    marcas = [Marca(TipoMarca.SALTO_PAGINA, 0, "7", ""),
              Marca(TipoMarca.IMAGEN, 0, "Un dibujo", "img/1.png")]
    documento = SimpleNamespace(texto="[Imagen: Un dibujo]\nY el texto.",
                                marcas=ColeccionMarcas(marcas),
                                ruta_archivo="")

    salida = html_elementos.html_de_tramo(documento, 0, len(documento.texto))
    assert "<img" in salida
    assert 'class="pagina"' in salida


# --- las traducciones automáticas -------------------------------------------


class PruebaTraducciones:
    """Lo que se puede comprobar de una traducción sin hablar el idioma.

    Francés, italiano y portugués están traducidos a máquina. Una máquina
    traduce bien las frases y se equivoca en lo que no sabe que es un término:
    tradujo «do» como «faire», «bemol» como «plat», «DAISY» como «Margherita» y
    «Anthropic» como «antrópico». Nada de eso se ve leyendo el programa en
    español, y quien lo lea en francés no tiene forma de saber que está mal.

    La herramienta comprueba cinco cosas objetivas —nombres propios, siglas,
    marcadores de formato, teclas y un glosario de términos musicales— y esta
    prueba la ejecuta con todo lo demás, que es lo que evita que el repaso haya
    que volver a hacerlo entero cada vez.
    """

    def _revisor(self):
        import sys

        raiz = pathlib.Path(__file__).resolve().parent.parent
        for cual in (raiz / "herramientas",):
            if str(cual) not in sys.path:
                sys.path.insert(0, str(cual))
        import revisar_traducciones

        return revisar_traducciones

    def test_ningun_catalogo_tiene_pegas(self):
        revisor = self._revisor()
        for codigo in revisor.IDIOMAS:
            pegas = revisor.revisar(codigo)
            assert not pegas, "%s: %s" % (
                codigo, "; ".join("%s %r %s" % p for p in pegas[:5]))

    def test_el_glosario_cubre_las_notas_y_las_figuras(self):
        """Si mañana se añade una figura, que no se quede sin vigilar."""
        from nucleo.braille_musica import NOMBRE_FIGURA, NOMBRES

        revisor = self._revisor()
        idioma_es = __import__("nucleo.idioma", fromlist=["instalar"])
        idioma_es.instalar("es")

        for nombre in list(NOMBRES.values()) + list(NOMBRE_FIGURA.values()):
            assert nombre in revisor.GLOSARIO, nombre

    def test_cada_termino_del_glosario_tiene_los_cuatro_idiomas(self):
        revisor = self._revisor()

        for termino, valores in revisor.GLOSARIO.items():
            assert len(valores) == len(revisor.IDIOMAS), termino
            assert all(valor.strip() for valor in valores), termino
