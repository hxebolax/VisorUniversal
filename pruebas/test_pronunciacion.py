# -*- coding: utf-8 -*-
"""Pruebas del diccionario de pronunciación."""

from nucleo import pronunciacion


def test_sustitucion_simple():
    tabla = pronunciacion.Tabla([pronunciacion.Regla("Daenerys", "Danerís")])
    assert tabla.aplicar("Daenerys llegó") == "Danerís llegó"


def test_palabra_completa_no_se_cuela_dentro_de_otra():
    """Es el fallo clásico: «Ana» dentro de «mañana»."""
    tabla = pronunciacion.Tabla([pronunciacion.Regla("Ana", "Anna")])
    assert tabla.aplicar("Ana vino mañana") == "Anna vino mañana"


def test_sin_palabra_completa_si_se_cuela():
    tabla = pronunciacion.Tabla([
        pronunciacion.Regla("ana", "ANA", palabra_completa=False)])
    assert tabla.aplicar("mañana") == "mañANA"


def test_no_distingue_mayusculas_por_omision():
    tabla = pronunciacion.Tabla([pronunciacion.Regla("ana", "Anna")])
    assert tabla.aplicar("ANA y Ana") == "Anna y Anna"


def test_distinguiendo_mayusculas():
    tabla = pronunciacion.Tabla([
        pronunciacion.Regla("US", "Estados Unidos", distingue_mayusculas=True)])
    assert tabla.aplicar("US y us") == "Estados Unidos y us"


def test_siglas_con_puntos():
    """«S.A.» no tiene frontera de palabra al final: la regla debe saltar igual."""
    tabla = pronunciacion.Tabla([pronunciacion.Regla("S.A.", "sociedad anónima")])
    assert tabla.aplicar("Ferretería S.A. cerrada") == "Ferretería sociedad anónima cerrada"


def test_decir_vacio_silencia():
    tabla = pronunciacion.Tabla([
        pronunciacion.Regla("★", "", palabra_completa=False)])
    assert tabla.aplicar("uno ★ dos").replace("  ", " ") == "uno dos"


def test_reglas_en_orden():
    """Una regla posterior actúa sobre lo que dejó la anterior."""
    tabla = pronunciacion.Tabla([
        pronunciacion.Regla("uno", "dos"),
        pronunciacion.Regla("dos", "tres"),
    ])
    assert tabla.aplicar("uno") == "tres"


def test_barra_invertida_en_el_reemplazo_no_revienta():
    """Sin escapar, «\\1» se tomaría por una referencia a un grupo."""
    tabla = pronunciacion.Tabla([pronunciacion.Regla("x", "\\1")])
    assert tabla.aplicar("x") == "\\1"


def test_regla_invalida_se_descarta():
    tabla = pronunciacion.Tabla([pronunciacion.Regla("  ", "algo")])
    assert len(tabla) == 0
    assert not tabla


def test_tabla_vacia_devuelve_el_texto_tal_cual():
    assert pronunciacion.VACIA.aplicar("hola") == "hola"


def test_tope_de_reglas():
    muchas = [pronunciacion.Regla("p%d" % numero, "q") for numero in range(1000)]
    tabla = pronunciacion.Tabla(muchas)
    assert len(tabla) == pronunciacion.MAXIMO


def test_ida_y_vuelta_por_json():
    original = pronunciacion.Regla("Ana", "Anna", palabra_completa=False,
                                   distingue_mayusculas=True)
    copia = pronunciacion.Regla.desde_dict(original.como_dict())
    assert copia == original


def test_desde_lista_ignora_lo_que_no_sea_regla():
    reglas = pronunciacion.desde_lista(
        [{"buscar": "a", "decir": "b"}, "esto no", 42, {"buscar": ""}])
    assert len(reglas) == 1
    assert reglas[0].buscar == "a"


def test_descripcion_dice_lo_que_hace():
    assert "se dice" in pronunciacion.Regla("Ana", "Anna").descripcion()
    assert "no se dice" in pronunciacion.Regla("★", "").descripcion()


def test_tabla_para_un_documento(configuracion, carpeta):
    """Las del libro van delante de las generales."""
    ruta = str(carpeta / "libro.epub")
    pronunciacion.guardar_generales(
        configuracion, [pronunciacion.Regla("gen", "GENERAL")])
    pronunciacion.guardar_del_documento(
        configuracion, ruta, [pronunciacion.Regla("libro", "LIBRO")])
    tabla = pronunciacion.tabla_para(configuracion, ruta)
    assert tabla.aplicar("libro y gen") == "LIBRO y GENERAL"


def test_tabla_desactivada(configuracion, carpeta):
    ruta = str(carpeta / "libro.epub")
    pronunciacion.guardar_del_documento(
        configuracion, ruta, [pronunciacion.Regla("a", "b")])
    configuracion.establecer("pronunciacion_activa", False)
    assert pronunciacion.tabla_para(configuracion, ruta).aplicar("a") == "a"
