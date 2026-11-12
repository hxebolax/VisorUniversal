# -*- coding: utf-8 -*-
"""Pruebas de la inteligencia artificial local y de la conversación con memoria.

Aquí no se descarga nada ni se arranca ningún servidor: eso necesita varios
gigas y una conexión, y una prueba que tarda diez minutos no la lanza nadie.
Lo que se comprueba es lo que sí se puede romper sin darse cuenta: que el
puerto no sea el de Ollama de toda la vida, que un progreso a medias se
traduzca a una frase que se entienda, que la conversación no repita el
documento entero en cada vuelta y que no se quede una pregunta sin respuesta
arrastrándose por los turnos siguientes.
"""

import os
import sys

import pytest

from nucleo.ia import modelos_vision, ollama
from nucleo.ia.preguntas import Conversacion, Trozo


# ---------------------------------------------------------------------------
# Que no se le pise nada a quien ya tenga Ollama
# ---------------------------------------------------------------------------

def test_el_puerto_no_es_el_de_ollama_de_siempre():
    """Es lo que separa «tener nuestra IA» de «robarle el servidor al usuario»."""
    assert ollama.PUERTO != ollama.PUERTO_ESTANDAR
    assert ollama.PUERTO_ESTANDAR == 11434


def test_todo_vive_dentro_de_la_carpeta_data():
    """El programa es portable: la IA se va con él en la memoria USB."""
    from nucleo import rutas

    datos = str(rutas.directorio_datos()).lower()
    assert str(ollama.carpeta_ollama()).lower().startswith(datos)
    assert str(ollama.carpeta_modelos()).lower().startswith(datos)


def test_la_direccion_es_la_que_espera_el_cliente():
    assert ollama.url_openai() == ollama.url_servidor() + "/v1"
    assert str(ollama.PUERTO) in ollama.url_servidor()


# ---------------------------------------------------------------------------
# El progreso, que es lo que el usuario oye durante veinte minutos
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("paso, espera", [
    ({"status": "pulling manifest"}, "Preguntando"),
    ({"status": "verifying sha256 digest"}, "entero"),
    ({"status": "success"}, "listo"),
    ({"status": "pulling", "total": 1000, "completed": 500}, "50 por ciento"),
])
def test_el_progreso_de_la_descarga_se_dice_en_castellano(paso, espera):
    """«pulling manifest» no le dice nada a nadie."""
    _porcentaje, mensaje = ollama.Ollama._paso_legible(paso)
    assert espera.lower() in mensaje.lower()


def test_un_fallo_de_red_se_explica_en_vez_de_soltarlo_en_ingles():
    """El mensaje de Ollama es una línea en inglés con una URL de cien letras.

    Los modelos se bajan de un almacén distinto del servidor de Ollama, y ese
    salto es el que bloquean algunos antivirus y cortafuegos: todo lo demás
    funciona y solo la descarga se queda parada.  Quien lo oiga tiene que poder
    saber qué mirar.
    """
    crudo = ('max retries exceeded: Get "https://algo.r2.cloudflarestorage.com/x": '
             'dial tcp 172.64.66.1:443: i/o timeout')
    explicado = ollama._explicar(crudo)
    assert crudo in explicado                    # no se oculta lo que dijo Ollama
    assert "conexión" in explicado
    assert "cortafuegos" in explicado or "antivirus" in explicado


def test_un_fallo_que_no_es_de_red_se_deja_como_esta():
    """Adornar un «no existe ese modelo» con consejos de red despista."""
    assert ollama._explicar("model not found") == "model not found"


def test_mientras_no_llega_nada_se_dice_el_tamano(): 
    """«pulling e554c6b9de01» no significa nada y suena a error."""
    _porcentaje, mensaje = ollama.Ollama._paso_legible(
        {"status": "pulling e554c6b9de01", "digest": "x", "total": 828_661_152},
        {"x": (0, 828_661_152)})
    assert "MB" in mensaje and "e554" not in mensaje


def test_el_porcentaje_sale_de_sumar_todas_las_capas():
    """Un modelo son varias capas y cada una cuenta desde cero.

    Mirando solo la línea que acaba de llegar, el porcentaje sube dentro de una
    capa y vuelve atrás al empezar la siguiente.  Lo que el usuario entiende
    por «cuánto falta» es la suma.
    """
    capas = {"pesos": (3_000_000_000, 3_000_000_000),   # entera
             "vision": (0, 1_000_000_000)}              # sin empezar
    porcentaje, _mensaje = ollama.Ollama._paso_legible(
        {"status": "pulling vision", "digest": "vision",
         "total": 1_000_000_000, "completed": 0}, capas)
    # Tres cuartos del total, no el cero de la capa que arranca.
    assert porcentaje == 75


def test_una_capa_que_empieza_no_borra_lo_ya_descargado():
    """El fallo tal cual lo vio el usuario: el porcentaje no se movía."""
    solo_esta_capa = ollama.Ollama._paso_legible(
        {"status": "pulling abc", "digest": "abc", "total": 5_000_000, "completed": 0})[0]
    assert solo_esta_capa == 0                  # sin memoria de capas, cero
    con_memoria = ollama.Ollama._paso_legible(
        {"status": "pulling abc", "digest": "abc", "total": 5_000_000, "completed": 0},
        {"otra": (9_000_000, 10_000_000), "abc": (0, 5_000_000)})[0]
    assert con_memoria == 60                    # con memoria, lo que hay de verdad


def test_comprobar_el_archivo_no_tira_la_barra_al_suelo():
    """Ver la barra caer a cero al final parece que algo ha salido mal."""
    capas = {"pesos": (2_000_000_000, 2_000_000_000)}
    porcentaje, mensaje = ollama.Ollama._paso_legible(
        {"status": "verifying sha256 digest"}, capas)
    assert porcentaje == 99
    assert "entero" in mensaje.lower()


def test_el_porcentaje_nunca_llega_a_cien_antes_de_tiempo():
    """Una barra que dice 100 y sigue trabajando es peor que no tenerla."""
    porcentaje, _mensaje = ollama.Ollama._paso_legible(
        {"status": "pulling", "total": 1000, "completed": 1000})
    assert porcentaje == 99


def test_los_tamanos_se_dicen_como_se_dicen():
    assert ollama._tamano(2 * 1024 ** 3).endswith("GB")
    assert "," in ollama._tamano(int(2.5 * 1024 ** 3))     # decimales con coma
    assert ollama._tamano(500 * 1024).endswith("KB")


def test_el_tramo_coloca_cada_fase_en_su_trozo_de_la_barra():
    """Descargar son varios pasos y cada uno cree que va del 0 al 100."""
    visto = []
    informar = ollama._tramo(lambda porcentaje, mensaje: visto.append(porcentaje), 20, 60)
    informar(0, "")
    informar(50, "")
    informar(100, "")
    assert visto == [20, 40, 60]


# ---------------------------------------------------------------------------
# Importar un modelo que ya está en el disco
# ---------------------------------------------------------------------------
#
# Aquí no se importa nada de verdad: copiar cuatro gigas al almacén de Ollama
# no es una prueba que nadie vaya a lanzar.  Lo que se comprueba es lo que
# decide si la importación va a salir bien o va a fallar después de diez
# minutos de copia: que el nombre sea uno que Ollama admita, que el archivo sea
# lo que dice ser, y que los dos archivos no estén cambiados.

@pytest.mark.parametrize("escrito, guardado", [
    ("Qwen visión 3B", "qwen-vision-3b"),        # espacios y tilde
    ("MiModelo:v2", "mimodelo:v2"),              # la etiqueta se conserva
    ("ñandú", "nandu"),
    ("  con  espacios  ", "con--espacios"),
    ("¿?¡!", ""),                                # nada aprovechable
])
def test_el_nombre_se_arregla_en_vez_de_regañar(escrito, guardado):
    """Ollama solo admite letras, números, puntos, guiones y barras bajas.

    Un nombre con espacios o acentos —«Qwen visión 3B», que es lo que uno
    escribiría— lo rechaza con un error que no explica nada.  Se arregla.
    """
    assert ollama._nombre_de_modelo(escrito) == guardado


def test_un_archivo_que_no_es_gguf_se_detecta_antes_de_copiarlo(tmp_path):
    """Mejor decirlo en el acto que tras diez minutos copiando."""
    bueno = tmp_path / "modelo.gguf"
    bueno.write_bytes(b"GGUF" + b"\x00" * 100)
    malo = tmp_path / "otro.gguf"
    malo.write_bytes(b"PK\x03\x04" + b"\x00" * 100)     # un ZIP disfrazado
    assert ollama._parece_gguf(bueno)
    assert not ollama._parece_gguf(malo)
    assert not ollama._parece_gguf(tmp_path / "no-existe.gguf")


def test_importar_con_un_archivo_que_no_vale_falla_antes_de_tocar_nada(tmp_path):
    malo = tmp_path / "modelo.gguf"
    malo.write_bytes(b"no soy un gguf")
    with pytest.raises(ollama.ErrorOllama) as fallo:
        ollama.gestor.importar_modelo("prueba", malo)
    assert "GGUF" in str(fallo.value)


def test_importar_sin_nombre_no_se_intenta(tmp_path):
    bueno = tmp_path / "modelo.gguf"
    bueno.write_bytes(b"GGUF" + b"\x00" * 100)
    with pytest.raises(ollama.ErrorOllama):
        ollama.gestor.importar_modelo("¿?", bueno)


def test_la_firma_es_la_de_sha256(tmp_path):
    """Es como Ollama identifica cada archivo en su almacén."""
    import hashlib

    archivo = tmp_path / "trozo.gguf"
    archivo.write_bytes(b"GGUF" + b"unos datos cualesquiera")
    esperada = "sha256:" + hashlib.sha256(archivo.read_bytes()).hexdigest()
    assert ollama._firma_de(archivo) == esperada


def test_los_dos_archivos_cambiados_se_notan(tmp_path):
    """El error fácil: el proyector aparece antes por orden alfabético."""
    from interfaz.dialogos.importar_modelo import DialogoImportarModelo

    proyector = tmp_path / "mmproj-F16.gguf"
    proyector.write_bytes(b"GGUF" + b"\x00" * 10)
    pesos = tmp_path / "modelo-Q4.gguf"
    pesos.write_bytes(b"GGUF" + b"\x00" * 5000)
    # Puestos al revés: el proyector en el hueco del modelo.
    assert DialogoImportarModelo._parecen_cambiados(proyector, pesos)
    # Y bien puestos, no se molesta al usuario.
    assert not DialogoImportarModelo._parecen_cambiados(pesos, proyector)


# ---------------------------------------------------------------------------
# Un «null» donde se esperaba una lista
# ---------------------------------------------------------------------------
#
# Sin ningún modelo instalado, Ollama contesta {"object":"list","data":null} a
# /v1/models.  El valor por omisión de ``get`` no protege de eso —solo actúa si
# la clave falta, no si vale null—, así que la lista se recorría sobre None y el
# usuario veía «No se han podido obtener los modelos: NoneType object is not
# iterable», que además de romper no explica nada.

def _respuesta_falsa(monkeypatch, cuerpo: bytes):
    """Hace que la siguiente petición devuelva ese JSON."""
    import urllib.request

    class _Respuesta:
        def read(self):
            return cuerpo

        def __enter__(self):
            return self

        def __exit__(self, *_datos):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda *_a, **_k: _Respuesta())


def test_sin_modelos_instalados_la_lista_sale_vacia(monkeypatch):
    """Es lo que contesta Ollama recién instalado, antes de descargar nada."""
    from nucleo.ia.local import Local

    _respuesta_falsa(monkeypatch, b'{"object":"list","data":null}')
    assert Local("http://127.0.0.1:11436/v1", "", 5.0).listar_modelos() == []


def test_con_modelos_se_listan_ordenados(monkeypatch):
    from nucleo.ia.local import Local

    _respuesta_falsa(monkeypatch,
                     b'{"data":[{"id":"qwen2.5vl:3b"},{"id":"moondream"},{"id":""}]}')
    assert Local("http://127.0.0.1:11436/v1", "", 5.0).listar_modelos() == [
        "moondream", "qwen2.5vl:3b"]


# ---------------------------------------------------------------------------
# De quién es el servidor que contesta en el puerto
# ---------------------------------------------------------------------------
#
# De esto depende no tocar un Ollama ajeno.  Iba con «wmic», que ya no viene
# con Windows 11, y al fallar respondía siempre «no se sabe»: el programa no
# reconocía ni su propio servidor.  Una prueba con el proceso de la propia
# prueba lo habría cazado.

@pytest.mark.skipif(os.name != "nt", reason="la comprobación es de Windows")
def test_se_sabe_que_programa_hay_detras_de_un_proceso():
    """Se pregunta por el proceso de la propia prueba, que sabemos cuál es.

    No se compara con ``sys.executable``: en un entorno virtual esa ruta es un
    lanzador y la imagen que corre de verdad es otra.  Lo que hace falta es que
    salga una ruta y que sea un programa que existe.
    """
    ruta = ollama.Ollama._ruta_del_proceso(os.getpid())
    assert ruta, "sin esto no se distingue nuestro servidor del de otro"
    assert os.path.isfile(ruta)
    assert "python" in os.path.basename(ruta).lower()


@pytest.mark.skipif(os.name != "nt", reason="la comprobación es de Windows")
def test_la_via_de_respaldo_dice_lo_mismo():
    """Si PowerShell no estuviera, se pregunta a la API de Windows."""
    assert ollama.Ollama._misma_ruta(
        ollama.Ollama._ruta_por_api(os.getpid()),
        ollama.Ollama._ruta_del_proceso(os.getpid()))


@pytest.mark.parametrize("pid", [0, 999999999])
def test_un_proceso_que_no_existe_deja_la_duda_y_no_se_toca(pid):
    """Vacío significa «no se sabe», y sin saberlo no se adopta ni se mata."""
    assert ollama.Ollama._ruta_del_proceso(pid) == ""
    assert not ollama.Ollama._misma_ruta("", "cualquier/cosa")


# ---------------------------------------------------------------------------
# Qué tarjeta gráfica se ve
# ---------------------------------------------------------------------------
#
# Esto falló en un equipo con una RTX 3060 de doce gigas, que se anunciaba como
# «sin tarjeta gráfica dedicada».  Tres motivos a la vez, y ninguno daba error:
# «wmic» ya no viene con Windows 11, Windows enumeraba tres monitores virtuales
# antes que la tarjeta, y la memoria que da WMI es de 32 bits y se queda en
# 4 GB.  Un fallo que no se queja es el que más tarda en verse, así que aquí se
# comprueba con nombres de verdad.

@pytest.mark.parametrize("nombre", [
    "Virtual Display Driver",
    "Parsec Virtual Display Adapter",
    "Microsoft Basic Display Adapter",
    "spacedesk Graphics Adapter",
])
def test_un_monitor_de_mentira_no_es_una_tarjeta(nombre):
    """Windows los enumera igual, y salen antes que la tarjeta buena."""
    assert ollama._es_falsa(nombre)


@pytest.mark.parametrize("nombre", [
    "NVIDIA GeForce RTX 3060",
    "AMD Radeon RX 7600",
    "Intel Arc A770 Graphics",
])
def test_una_tarjeta_de_verdad_se_reconoce(nombre):
    assert not ollama._es_falsa(nombre)
    assert not ollama._es_integrada(nombre)


@pytest.mark.parametrize("nombre", [
    "Intel(R) UHD Graphics 620",
    "Intel(R) Iris(R) Xe Graphics",
    "AMD Radeon(TM) Graphics",
])
def test_la_grafica_del_procesador_no_cuenta_como_tarjeta(nombre):
    """Funcionan, pero para esto suelen ir peor que el propio procesador."""
    assert ollama._es_integrada(nombre)


def test_entre_varias_gana_la_dedicada(monkeypatch):
    """El portátil típico: la del procesador y la buena, en ese orden."""
    monkeypatch.setattr(ollama, "graficas", lambda: [
        ("Intel(R) UHD Graphics 630", 0.1),
        ("NVIDIA GeForce RTX 3060", 12.0),
    ])
    elegida = ollama.equipo()
    assert elegida.grafica == "NVIDIA GeForce RTX 3060"
    assert elegida.dedicada and elegida.hay_grafica


def test_sin_saber_la_memoria_la_tarjeta_se_usa_igual(monkeypatch):
    """Si no se sabe cuánta tiene, decide el motor: no se descarta la tarjeta."""
    monkeypatch.setattr(ollama, "graficas", lambda: [("AMD Radeon RX 7600", 0.0)])
    assert ollama.equipo().hay_grafica


def test_solo_con_la_integrada_trabaja_el_procesador(monkeypatch):
    monkeypatch.setattr(ollama, "graficas", lambda: [("Intel(R) Iris(R) Xe Graphics", 0.1)])
    solo_integrada = ollama.equipo()
    assert not solo_integrada.hay_grafica
    # Pero se dice cuál es: «no tienes tarjeta» a quien tiene una integrada es
    # mentira, y además no explica por qué se usa el procesador.
    assert "Iris" in solo_integrada.resumen()


def test_el_complemento_de_amd_se_pide_cuando_hay_una_amd(monkeypatch):
    """Con «wmic» esto respondía siempre que no, y la Radeon no se usaba."""
    monkeypatch.setattr(ollama, "graficas", lambda: [("AMD Radeon RX 7600", 8.0)])
    assert ollama.Ollama._hay_grafica_amd()
    monkeypatch.setattr(ollama, "graficas", lambda: [("NVIDIA GeForce RTX 3060", 12.0)])
    assert not ollama.Ollama._hay_grafica_amd()


def test_la_memoria_no_se_queda_clavada_en_cuatro_gigas():
    """WMI corta en 4 GB; por eso se lee del registro y de nvidia-smi.

    No se comprueba qué tarjeta hay —depende del equipo—, sino que ninguna
    fuente devuelva la cifra falsa de WMI, que es 4294967295 bytes.
    """
    for _nombre, vram in ollama.graficas():
        assert abs(vram - 3.99) > 0.02, "esa cifra es el tope de WMI, no la memoria real"


# ---------------------------------------------------------------------------
# El catálogo de modelos
# ---------------------------------------------------------------------------

def test_hay_un_modelo_recomendado_y_es_el_de_documentos():
    """En un lector de libros, lo que más se pide es entender documentos."""
    elegido = modelos_vision.recomendado()
    assert elegido.recomendado
    assert elegido.etiqueta == modelos_vision.POR_OMISION
    assert sum(1 for modelo in modelos_vision.MODELOS if modelo.recomendado) == 1


def test_el_mas_pequeno_cabe_en_un_equipo_modesto():
    """Si el más ligero no cupiera en 4 GB, la lista no valdría para nada."""
    assert min(modelo.memoria_gb for modelo in modelos_vision.MODELOS) <= 2.0


def test_solo_se_ofrecen_los_modelos_que_caben():
    caben = modelos_vision.caben_en(4.0)
    assert caben and all(modelo.memoria_gb <= 4.0 for modelo in caben)
    # Del más capaz al más ligero: quien tiene sitio quiere el mejor que le entre.
    assert caben == sorted(caben, key=lambda modelo: modelo.memoria_gb, reverse=True)
    assert modelos_vision.caben_en(0.5) == []


def test_cada_modelo_dice_para_que_sirve_y_qué_pide():
    for modelo in modelos_vision.MODELOS:
        assert modelo.fuerte_en and len(modelo.detalle) > 100
        assert modelo.descarga_mb > 0 and modelo.memoria_gb > 0
        linea = modelos_vision.resumen(modelo)
        assert modelo.nombre in linea and "GB" in linea


# ---------------------------------------------------------------------------
# La conversación con memoria
# ---------------------------------------------------------------------------

def _trozo() -> Trozo:
    return Trozo("El texto larguísimo del capítulo.", "el capítulo", False)


def test_el_documento_solo_viaja_en_la_primera_pregunta():
    """Repetirlo en cada vuelta multiplicaría el coste sin añadir nada."""
    conversacion = Conversacion("Un libro", "Alguien")
    primera = conversacion.preparar("Resume esto", _trozo())
    assert "larguísimo" in primera[0][1]
    conversacion.responder("Va de esto y de lo otro.")
    segunda = conversacion.preparar("¿Y por qué?")
    assert segunda[-1][1] == "¿Y por qué?"
    assert "larguísimo" not in segunda[-1][1]
    # Pero sigue estando en la conversación, que es lo que se manda entera.
    assert "larguísimo" in segunda[0][1]


def test_la_conversacion_alterna_usuario_y_asistente():
    conversacion = Conversacion()
    conversacion.preparar("uno", _trozo())
    conversacion.responder("respuesta uno")
    turnos = conversacion.preparar("dos")
    assert [quien for quien, _texto in turnos] == ["usuario", "asistente", "usuario"]


def test_una_pregunta_que_falla_no_se_queda_en_la_conversacion():
    """Si se quedara, todas las siguientes arrastrarían un turno sin respuesta."""
    conversacion = Conversacion()
    conversacion.preparar("uno", _trozo())
    conversacion.responder("respuesta uno")
    conversacion.preparar("dos")
    conversacion.deshacer_ultima()
    assert len(conversacion) == 2
    assert conversacion.turnos[-1][0] == "asistente"


def test_la_conversacion_se_poda_sin_dejar_respuestas_huerfanas():
    conversacion = Conversacion()
    conversacion.preparar("primera", _trozo())
    conversacion.responder("r")
    for numero in range(30):
        conversacion.preparar("p%d" % numero)
        conversacion.responder("r%d" % numero)
    from nucleo.ia import preguntas

    assert len(conversacion) <= preguntas.TURNOS_MAXIMOS
    # Tiene que seguir empezando por una pregunta: una respuesta suelta al
    # principio confunde al modelo más de lo que le ayuda.
    assert conversacion.turnos[0][0] == "usuario"


def test_olvidar_hace_que_el_documento_vuelva_a_viajar():
    conversacion = Conversacion()
    conversacion.preparar("uno", _trozo())
    conversacion.responder("r")
    conversacion.olvidar()
    assert conversacion.vacia
    primera = conversacion.preparar("otra vez", _trozo())
    assert "larguísimo" in primera[0][1]


def test_la_conversacion_se_puede_releer_entera():
    conversacion = Conversacion()
    conversacion.preparar("¿qué es esto?", _trozo())
    conversacion.responder("Pues esto.")
    texto = conversacion.como_texto()
    assert "Pues esto." in texto and texto.count("\n\n") >= 1


# ---------------------------------------------------------------------------
# El proveedor
# ---------------------------------------------------------------------------

def test_la_ia_local_del_programa_es_un_proveedor_mas():
    from nucleo.ia import servicio

    claves = [clave for clave, _nombre in servicio.PROVEEDORES]
    assert "ollama_propio" in claves
    # No pide clave API: es lo que la distingue de las de internet.
    assert "ollama_propio" not in servicio.DE_INTERNET


def test_sin_instalar_se_dice_donde_se_instala(configuracion):
    """El aviso tiene que llevar a alguna parte, no solo decir que no se puede."""
    from nucleo.ia import servicio

    configuracion.establecer("ia_proveedor", "ollama_propio")
    configuracion.establecer("ollama_modelo", "")
    activo = servicio.Servicio(configuracion)
    assert activo.activa
    with pytest.raises(Exception) as fallo:
        activo._cliente()
    mensaje = str(fallo.value).lower()
    assert "ia local" in mensaje                 # dice dónde arreglarlo
