# -*- coding: utf-8 -*-
"""Pruebas del sistema de actualizaciones.

Lo que se comprueba aquí no es que descargue —eso necesita un servidor— sino
lo que puede salir mal sin que nadie se dé cuenta: comparar versiones, aceptar
un paquete que no es, y dejar que un ZIP escriba fuera de su carpeta.
"""

import zipfile

import pytest

from nucleo import actualizaciones


# --- comparación de versiones -----------------------------------------------

@pytest.mark.parametrize("remota, local, esperado", [
    ("1.2.0", "1.1.0", True),
    ("1.1.0", "1.1.0", False),
    ("1.0.9", "1.1.0", False),
    # El caso que rompe cualquier comparación hecha con cadenas de texto.
    ("1.2.10", "1.2.9", True),
    ("1.2.9", "1.2.10", False),
    ("2.0", "1.9.9", True),
    ("1.2.0-beta", "1.1.0", True),
    ("", "1.0.0", False),
    (None, "1.0.0", False),
])
def test_comparacion_de_versiones(remota, local, esperado):
    assert actualizaciones.es_mas_nueva(remota, local) is esperado


def test_numeros_de_version_ilegible():
    assert actualizaciones._numeros("sin números") == (0,)
    assert actualizaciones._numeros("") == (0,)


# --- comprobación del paquete -------------------------------------------------

def test_sha256_correcto_pasa(carpeta):
    archivo = carpeta / "paquete.zip"
    archivo.write_bytes(b"contenido de prueba")
    resumen = actualizaciones._sha256(archivo)
    actualizaciones.comprobar_paquete(archivo, resumen)   # no debe lanzar


def test_sha256_distinto_se_rechaza(carpeta):
    archivo = carpeta / "paquete.zip"
    archivo.write_bytes(b"contenido de prueba")
    with pytest.raises(ValueError):
        actualizaciones.comprobar_paquete(archivo, "0" * 64)


def test_sin_sha256_se_acepta_con_aviso(carpeta):
    """Un servidor antiguo no lo publica; no se puede comprobar, pero no se rompe."""
    archivo = carpeta / "paquete.zip"
    archivo.write_bytes(b"x")
    actualizaciones.comprobar_paquete(archivo, "")


# --- descompresión ------------------------------------------------------------

def _hacer_zip(destino, miembros):
    with zipfile.ZipFile(destino, "w") as paquete:
        for nombre, contenido in miembros.items():
            paquete.writestr(nombre, contenido)
    return destino


def test_descomprimir_quita_la_carpeta_raiz(carpeta):
    origen = _hacer_zip(carpeta / "p.zip", {
        "VisorUniversal/VisorUniversal.exe": "x",
        "VisorUniversal/data/algo.txt": "y",
    })
    salida = carpeta / "salida"
    actualizaciones.descomprimir(origen, salida)
    assert (salida / "VisorUniversal.exe").exists()
    assert (salida / "data" / "algo.txt").exists()


def test_descomprimir_rechaza_lo_que_no_es_el_programa(carpeta):
    origen = _hacer_zip(carpeta / "p.zip", {"cualquiera.txt": "x"})
    with pytest.raises(ValueError):
        actualizaciones.descomprimir(origen, carpeta / "salida")


def test_zip_slip_no_escribe_fuera(carpeta):
    """Un miembro con «..» intenta escribir fuera de la carpeta de destino."""
    origen = _hacer_zip(carpeta / "p.zip", {
        "main.py": "x",
        "../fuera.txt": "no debería aparecer",
    })
    salida = carpeta / "salida"
    actualizaciones.descomprimir(origen, salida)
    assert (salida / "main.py").exists()
    assert not (carpeta / "fuera.txt").exists()


def test_demasiados_archivos(carpeta, monkeypatch):
    monkeypatch.setattr(actualizaciones, "MAX_ARCHIVOS", 2)
    origen = _hacer_zip(carpeta / "p.zip",
                        {"main.py": "x", "a": "1", "b": "2", "c": "3"})
    with pytest.raises(ValueError):
        actualizaciones.descomprimir(origen, carpeta / "salida")


def test_expansion_desmedida(carpeta, monkeypatch):
    monkeypatch.setattr(actualizaciones, "MAX_TOTAL", 10)
    origen = _hacer_zip(carpeta / "p.zip", {"main.py": "x" * 1000})
    with pytest.raises(ValueError):
        actualizaciones.descomprimir(origen, carpeta / "salida")


def test_prefijo_comun():
    assert actualizaciones._prefijo_comun(["a/x", "a/y"]) == "a/"
    assert actualizaciones._prefijo_comun(["a/x", "b/y"]) == ""
    assert actualizaciones._prefijo_comun([]) == ""


# --- guion de actualización -----------------------------------------------------

def test_el_guion_espera_y_copia(carpeta):
    guion = actualizaciones.crear_guion(carpeta, carpeta / "temp", carpeta / "p.zip")
    contenido = guion.read_text(encoding="utf-8")
    assert "tasklist" in contenido          # espera a que muera el programa
    assert "robocopy" in contenido          # copia sin borrar lo que no trae
    assert "taskkill" in contenido          # y si no se cierra, lo cierra
    assert contenido.startswith("@echo off")


def test_sin_url_no_se_consulta_nada():
    """Sin servidor configurado no se pregunta a nadie, ni por error."""
    assert actualizaciones.activadas() == bool(actualizaciones.URL_ACTUALIZACIONES.strip())
    if not actualizaciones.activadas():
        assert actualizaciones.consultar() is None


def test_limpiar_restos_no_falla_sin_nada_que_limpiar(carpeta):
    actualizaciones.limpiar_restos(carpeta)


# --- notas de la versión -----------------------------------------------------
#
# El «version.json» es un archivo generado, así que las notas se escriben en
# «NOVEDADES.md» y el empaquetador las copia.  Si esto se rompe, la versión se
# publicaría sin nada que contar y nadie se enteraría hasta verlo en el
# actualizador de un usuario.

def _empaquetador():
    """Importa el guion de empaquetado, que vive fuera de «src»."""
    import sys
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent
    if str(raiz / "herramientas") not in sys.path:
        sys.path.insert(0, str(raiz / "herramientas"))
    import empaquetar

    return empaquetar


def test_las_notas_salen_del_apartado_de_su_version(carpeta):
    novedades = carpeta / "NOVEDADES.md"
    novedades.write_text(
        "# Novedades\n\n## 1.2.0\n\nLo **nuevo** de esta.\n\nY un segundo párrafo.\n\n"
        "## 1.1.0\n\nLo de la anterior, que aquí no pinta nada.\n",
        encoding="utf-8")
    notas = _empaquetador().notas_de("1.2.0", novedades)
    assert notas == "Lo nuevo de esta.\n\nY un segundo párrafo."


def test_una_version_sin_apartado_se_queda_sin_notas(carpeta):
    novedades = carpeta / "NOVEDADES.md"
    novedades.write_text("## 1.1.0\n\nLo de la anterior.\n", encoding="utf-8")
    assert _empaquetador().notas_de("1.2.0", novedades) == ""


def test_sin_archivo_de_novedades_no_se_falla(carpeta):
    assert _empaquetador().notas_de("1.2.0", carpeta / "no_existe.md") == ""


def test_la_version_publicada_tiene_sus_novedades_escritas():
    """La red de seguridad: publicar sin notas es publicar a ciegas."""
    from version import VERSION

    notas = _empaquetador().notas_de(VERSION)
    assert notas, "NOVEDADES.md no tiene ningún apartado «## %s»" % VERSION
    assert len(notas) > 200


# --- la copia de las novedades que ve quien usa el programa -------------------
#
# El «NOVEDADES.md» de la raíz empieza explicando de dónde salen las notas de la
# actualización: eso le sirve a quien publica una versión y estorba a quien abre
# las novedades desde el menú de ayuda.  La compilación deja en «docs» una copia
# que empieza en la versión más reciente.

def test_las_novedades_publicas_empiezan_en_la_primera_version(carpeta):
    novedades = carpeta / "NOVEDADES.md"
    novedades.write_text(
        "# Novedades\n\nEsto lo lee empaquetar.py y no le importa a nadie más.\n\n"
        "---\n\n## 1.2.0\n\nLo nuevo de esta.\n\n## 1.1.0\n\nLo de la anterior.\n",
        encoding="utf-8")
    texto = _empaquetador().novedades_publicas(novedades)
    assert "empaquetar.py" not in texto
    assert texto.index("## 1.2.0") < texto.index("## 1.1.0")
    assert "Lo de la anterior." in texto, "no se recorta nada por abajo: van todas"


def test_sin_ninguna_version_escrita_no_se_inventa_un_archivo(carpeta):
    """Más vale que la compilación avise a que salga un menú que no abre nada."""
    novedades = carpeta / "NOVEDADES.md"
    novedades.write_text("# Novedades\n\nTodavía no hay ninguna.\n", encoding="utf-8")
    assert _empaquetador().novedades_publicas(novedades) == ""
    assert _empaquetador().novedades_publicas(carpeta / "no_existe.md") == ""


def test_las_novedades_publicadas_traen_la_version_de_ahora():
    """Lo que se compila hoy tiene que contar lo que trae la versión de hoy."""
    from version import VERSION

    texto = _empaquetador().novedades_publicas()
    assert texto.count("\n## ") >= 1
    assert "## %s\n" % VERSION in texto


def test_desde_el_codigo_fuente_las_novedades_son_las_de_la_raiz():
    """En «docs» solo está la copia que hace la compilación, y es la anterior."""
    import sys
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent
    if str(raiz / "src") not in sys.path:
        sys.path.insert(0, str(raiz / "src"))
    from nucleo import rutas

    assert not rutas.esta_congelado(), "las pruebas no corren desde el ejecutable"
    assert rutas.ruta_novedades() == raiz / rutas.NOMBRE_NOVEDADES
    # Y el nombre de la página web que se genera sale del idioma original, no
    # de la carpeta en la que esté el archivo.
    assert rutas.codigo_de_documento(rutas.ruta_novedades()) == rutas.IDIOMA_BASE
    assert rutas.codigo_de_documento(rutas.ruta_manual()) == rutas.IDIOMA_BASE


# --- de dónde se descarga ---------------------------------------------------------

def test_las_fuentes_de_cada_origen():
    nombres = lambda origen, url="": [f.manifiesto for f in actualizaciones.fuentes(origen, url)]
    servidor = actualizaciones.URL_ACTUALIZACIONES.rstrip("/") + "/version.json"
    github = ("https://github.com/%s/releases/latest/download/version.json"
              % actualizaciones.REPOSITORIO_GITHUB)
    assert nombres("servidor") == [servidor]
    assert nombres("github") == [github]
    assert nombres("ambos") == [servidor, github]
    # Lo que no vale se trata como el origen de fábrica.
    assert nombres("inventado") == nombres(actualizaciones.ORIGEN_POR_OMISION)
    # Una dirección personalizada vacía no deja ninguna fuente.
    assert nombres("personalizada", "") == []
    assert not actualizaciones.activadas("personalizada", "  ")


def test_direccion_personalizada_de_carpeta_y_de_github():
    carpeta = actualizaciones.fuente_personalizada("mi-servidor.lan/Visor/")
    assert carpeta.manifiesto == "https://mi-servidor.lan/Visor/version.json"
    assert carpeta.url_del_paquete("2.0.0") == \
        "https://mi-servidor.lan/Visor/VisorUniversal_v2.0.0.zip"
    github = actualizaciones.fuente_personalizada("https://github.com/alguien/espejo.git")
    assert github.manifiesto == \
        "https://github.com/alguien/espejo/releases/latest/download/version.json"
    assert github.url_del_paquete("2.0.0", "VisorUniversal_v2.0.0.zip") == \
        "https://github.com/alguien/espejo/releases/download/v2.0.0/VisorUniversal_v2.0.0.zip"


def test_con_dos_fuentes_gana_la_mas_nueva(monkeypatch):
    respuestas = {
        "el servidor del autor": {"version": "1.4.0", "sha256": "aa", "file": "V.zip"},
        "GitHub": {"version": "1.4.1", "sha256": "bb", "file": "V.zip"},
    }
    monkeypatch.setattr(actualizaciones, "_leer_manifiesto",
                        lambda fuente, espera: respuestas.get(fuente.nombre))
    datos = actualizaciones.consultar(origen="ambos")
    assert datos["version"] == "1.4.1"
    assert datos["_origen"] == "GitHub"
    # La otra fuente anuncia otro paquete: no sirve de reserva.
    assert len(datos["_paquetes"]) == 1


def test_con_el_mismo_paquete_la_otra_fuente_queda_de_reserva(monkeypatch):
    mismo = {"version": "1.4.0", "sha256": "aa", "file": "V.zip"}
    monkeypatch.setattr(actualizaciones, "_leer_manifiesto",
                        lambda fuente, espera: dict(mismo))
    datos = actualizaciones.consultar(origen="ambos")
    assert datos["_origen"] == "el servidor del autor"
    assert len(datos["_paquetes"]) == 2
    assert "github.com" in datos["_paquetes"][1]


def test_si_una_fuente_esta_caida_se_usa_la_otra(monkeypatch):
    monkeypatch.setattr(
        actualizaciones, "_leer_manifiesto",
        lambda fuente, espera: None if fuente.nombre == "GitHub" else {"version": "1.5"})
    assert actualizaciones.consultar(origen="ambos")["version"] == "1.5"
    monkeypatch.setattr(actualizaciones, "_leer_manifiesto", lambda fuente, espera: None)
    assert actualizaciones.consultar(origen="ambos") is None


def test_la_descarga_prueba_la_siguiente_direccion(monkeypatch, carpeta):
    intentadas = []

    def falsa(direccion, destino, progreso, cancelado, espera):
        intentadas.append(direccion)
        if direccion == "https://uno/V.zip":
            raise OSError("caído")
        return destino

    monkeypatch.setattr(actualizaciones, "_descargar_de", falsa)
    destino = carpeta / "p.zip"
    salida = actualizaciones.descargar("1.0", destino,
                                       direcciones=["https://uno/V.zip", "https://dos/V.zip"])
    assert salida == destino
    assert intentadas == ["https://uno/V.zip", "https://dos/V.zip"]


def test_si_fallan_todas_se_cuenta_el_error(monkeypatch, carpeta):
    def falsa(direccion, destino, progreso, cancelado, espera):
        raise OSError("caído")

    monkeypatch.setattr(actualizaciones, "_descargar_de", falsa)
    with pytest.raises(OSError):
        actualizaciones.descargar("1.0", carpeta / "p.zip", direcciones=["https://a", "https://b"])
