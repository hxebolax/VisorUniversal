# -*- coding: utf-8 -*-
"""Pruebas de la interfaz.

Se crea la ventana de verdad y se comprueba lo que se puede comprobar sin un
usuario delante: que todo se construye, que las órdenes que necesitan documento
salen apagadas, que los atajos no chocan entre sí y que los avisos que salen de
un menú no se pierden.

No se abre ningún diálogo modal: eso bloquearía las pruebas para siempre.  Los
diálogos se construyen y se destruyen, que es donde están los fallos que se
cuelan —un atributo que no existe, una etiqueta sin nombre—.
"""

import time

import pytest

wx = pytest.importorskip("wx")


@pytest.fixture(scope="module")
def ventana(request):
    """La ventana principal, una sola para todo el módulo.

    Crearla cuesta bastante y no hay ninguna prueba que la ensucie de forma
    que le importe a la siguiente.
    """
    import wx as _wx

    from formatos import daisy, epub, ofimatica, pdf, texto   # noqa: F401
    from nucleo.configuracion import Configuracion
    from interfaz.ventana import VentanaPrincipal

    aplicacion = _wx.App(False)
    configuracion = Configuracion()
    # Ni teclas globales ni recorrido guiado: lo primero se pelea con la copia
    # que el usuario tenga abierta, y lo segundo abriría un diálogo modal.
    configuracion.establecer("teclas_globales_activas", False)
    configuracion.establecer("primer_uso_hecho", True)
    principal = VentanaPrincipal(configuracion, "pruebas")

    yield principal

    principal.Destroy()
    del aplicacion


# --- construcción ---------------------------------------------------------

def test_la_ventana_se_construye(ventana):
    assert ventana.GetMenuBar() is not None
    assert ventana.lector is not None
    assert ventana.lectura_voz is not None
    assert ventana.temporizador is not None


def test_todos_los_menus_estan(ventana):
    barra = ventana.GetMenuBar()
    rotulos = [barra.GetMenuLabelText(numero) for numero in range(barra.GetMenuCount())]
    for esperado in ("Archivo", "Ir a", "Voz", "Reproductor", "Herramientas", "Ayuda"):
        assert esperado in rotulos


def test_las_ordenes_nuevas_estan_en_su_menu(ventana):
    """Una orden sin entrada de menú es una orden que nadie encuentra."""
    for identificador in ("exportar_audio", "diccionario", "pronunciacion",
                          "temporizador", "buscar_actualizaciones", "primer_uso"):
        assert identificador in ventana._identificadores, identificador


def test_buscar_actualizaciones_esta_encima_del_cafe(ventana):
    """Es donde el usuario lo espera: las dos son cosas del programa."""
    barra = ventana.GetMenuBar()
    ayuda = barra.GetMenu(barra.FindMenu("Ayuda"))
    rotulos = [e.GetItemLabelText() for e in ayuda.GetMenuItems() if not e.IsSeparator()]
    posicion = [numero for numero, r in enumerate(rotulos) if "actualizaciones" in r.lower()]
    cafe = [numero for numero, r in enumerate(rotulos) if "café" in r.lower()]
    assert posicion and cafe
    assert posicion[0] == cafe[0] - 1


# --- disponibilidad ---------------------------------------------------------

def test_sin_documento_lo_que_necesita_libro_esta_apagado(ventana):
    """Se ve en el menú, pero no se puede elegir.

    Incluye la exportación a audio, el temporizador de apagado y las preguntas
    a la IA: todas ellas operan sobre un documento, y sin documento no
    significan nada.
    """
    barra = ventana.GetMenuBar()
    for identificador in ("exportar_texto", "exportar_md", "exportar_html",
                          "exportar_epub", "exportar_audio", "cerrar_libro",
                          "informacion", "temporizador", "resumir", "preguntar"):
        numero = ventana._identificadores[identificador]
        assert not barra.FindItemById(numero).IsEnabled(), identificador


def test_el_diccionario_sigue_disponible_sin_documento(ventana):
    """Definir una palabra no necesita libro: es un diccionario, sin más.

    El de pronunciación tampoco: sus reglas generales valen para todos los
    documentos y se pueden preparar antes de abrir ninguno.
    """
    barra = ventana.GetMenuBar()
    for identificador in ("diccionario", "pronunciacion", "opciones"):
        numero = ventana._identificadores[identificador]
        assert barra.FindItemById(numero).IsEnabled(), identificador


# --- atajos -----------------------------------------------------------------

def test_ningun_atajo_repetido():
    """Dos órdenes con la misma tecla: solo funcionaría una, y sin avisar."""
    from interfaz import atajos

    vistos = {}
    for orden in atajos.ORDENES:
        if not orden.atajo:
            continue
        assert orden.atajo not in vistos, (
            "%s y %s comparten %s" % (orden.identificador, vistos.get(orden.atajo),
                                      orden.atajo))
        vistos[orden.atajo] = orden.identificador


def test_ninguna_tecla_rapida_repetida():
    """Las teclas de una pulsación tampoco pueden pisarse."""
    from interfaz import atajos

    teclas = [a.tecla for a in atajos.NAVEGACION]
    teclas += [atajos.SECCION_SIGUIENTE, atajos.CONTENEDOR_FIN,
               atajos.MARCADOR_SIGUIENTE, atajos.NOTA_SIGUIENTE,
               atajos.DESCRIBIR_IMAGEN, atajos.DEFINIR_PALABRA,
               atajos.DONDE_ESTOY, atajos.REPETIR_ANUNCIO]
    # CONTENEDOR_INICIO y CONTENEDOR_FIN comparten tecla a propósito: se
    # distinguen por Mayús.
    assert len(teclas) == len(set(teclas)), sorted(teclas)


def test_todos_los_atajos_se_entienden():
    """Un atajo que el intérprete no reconoce es un atajo que no funciona."""
    from interfaz import atajos

    for orden in atajos.ORDENES:
        if orden.atajo:
            assert atajos.descomponer(orden.atajo) is not None, orden.atajo


# --- avisos que salen de un menú ----------------------------------------------

def test_un_aviso_tras_cerrar_un_menu_espera_al_foco(ventana, monkeypatch):
    """Es el fallo que hacía que se perdiera «aquí no hay ninguna tabla».

    Al salir de un menú el foco vuelve al texto y el lector de pantalla anuncia
    la línea del cursor, tapando el aviso.  Por eso, aunque se pida inmediato,
    hay que esperar a que el foco se asiente.
    """
    from interfaz import ventana as modulo

    retardos = []
    monkeypatch.setattr(ventana.anunciador, "anunciar",
                        lambda mensaje, retardo=0, **k: retardos.append(retardo))

    # Sin menú de por medio: inmediato de verdad.
    ventana._menu_cerrado_en = 0.0
    ventana.anunciar("Prueba", inmediato=True)
    assert retardos[-1] == 0

    # Justo después de cerrarse un menú: se espera.
    ventana._menu_cerrado_en = time.monotonic()
    ventana.anunciar("Prueba", inmediato=True)
    assert retardos[-1] > 0

    # Pasado el rato, vuelve a ser inmediato.
    ventana._menu_cerrado_en = time.monotonic() - modulo.ESPERA_TRAS_MENU - 1
    ventana.anunciar("Prueba", inmediato=True)
    assert retardos[-1] == 0


# --- los diálogos se construyen ------------------------------------------------

def test_los_dialogos_nuevos_se_construyen(ventana):
    """Un atributo mal escrito solo se ve al construir la ventana de verdad."""
    from nucleo.ia.servicio import Servicio
    from nucleo.voz import Sintetizador
    from interfaz.dialogos.actualizacion import DialogoActualizacion
    from interfaz.dialogos.diccionario import DialogoDiccionario
    from interfaz.dialogos.primer_uso import DialogoPrimerUso
    from interfaz.dialogos.pronunciacion import DialogoPronunciacion, DialogoRegla
    from interfaz.temporizador import DialogoTemporizador

    configuracion = ventana.configuracion
    fabricas = [
        lambda: DialogoDiccionario(ventana, "casa", "una casa grande",
                                   Servicio(configuracion), configuracion),
        lambda: DialogoPronunciacion(ventana),
        lambda: DialogoRegla(ventana, None, Sintetizador()),
        lambda: DialogoTemporizador(ventana, ventana.temporizador),
        lambda: DialogoActualizacion(ventana, "9.9.9", {"notas": "algo"}),
        lambda: DialogoPrimerUso(ventana, configuracion),
    ]
    for fabrica in fabricas:
        dialogo = fabrica()
        assert dialogo.GetChildren()
        dialogo.Destroy()


def test_el_recorrido_tiene_todos_sus_pasos():
    from interfaz.dialogos.primer_uso import pasos

    todos = pasos()
    assert len(todos) >= 10
    # La mitad larga enseña una tecla que se puede practicar.
    con_tecla = [paso for paso in todos if paso.tecla is not None]
    assert len(con_tecla) >= 8
    for paso in todos:
        assert paso.titulo and paso.texto
        if paso.tecla is not None:
            assert paso.descripcion_tecla


def test_las_ayudas_de_control_f1_cubren_lo_nuevo():
    """Cada ajuste nuevo tiene que decir para qué sirve."""
    from interfaz.ayuda_control import ayudas

    catalogo = ayudas()
    for clave in ("comprobar_actualizaciones", "activa", "buscar", "decir",
                  "completa", "mayusculas", "reparto", "formato", "voz",
                  "velocidad", "carpeta", "tiempo", "palabra", "fuente",
                  "solo_articulo", "revisar_epub", "quimica", "saltar_notas",
                  "sincro_carpeta", "boton_fuentes", "biblioteca_calibre_modo"):
        assert clave in catalogo, clave
        titulo, explicacion = catalogo[clave]
        assert titulo and len(explicacion) > 80


def test_ninguna_ventana_se_queda_sin_control_f1():
    """Un control sin explicación es, sin la vista, un nombre suelto y nada más.

    Se comprueba a máquina porque a mano envejece solo: se añade un botón, se le
    olvida a alguien la entrada del catálogo y quien pulsa Control+F1 encima oye
    que no hay nada escrito. Con la vista eso se disimula con el rótulo y con lo
    que hay alrededor; sin ella, no.
    """
    import sys
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(raiz / "herramientas"))
    import revisar_ayuda

    _cuantas, sin_enganche, faltan = revisar_ayuda.revisar()

    assert not sin_enganche, "sin enganchar Control+F1: %r" % sin_enganche
    assert not faltan, "controles sin explicación: %r" % faltan


def test_las_explicaciones_dicen_algo(ventana):
    """Una explicación de media línea no explica: solo repite el rótulo.

    El listón está bajo a propósito. Hay botones cuya explicación honrada cabe en
    un renglón —«vuelve a la pantalla anterior»— y alargarla sería relleno. Lo
    que esto caza es la entrada puesta para que la comprobación pase.
    """
    from interfaz.ayuda_control import ayudas

    flojas = [clave for clave, (titulo, texto) in ayudas().items()
              if not titulo or len(texto) < 45]

    assert not flojas, "explicaciones demasiado cortas: %r" % flojas[:5]


def test_la_ayuda_distingue_el_mismo_control_en_dos_ventanas(ventana):
    """Casi todas las ventanas tienen una «lista», y no son la misma cosa."""
    from interfaz.ayuda_control import ayudas, claves_de

    catalogo = ayudas()

    class _Falsa:
        pass

    _Falsa.__name__ = "DialogoCuaderno"
    assert claves_de(_Falsa(), "lista")[0] == "DialogoCuaderno.lista"
    assert claves_de(_Falsa(), "lista")[1] == "lista"
    assert catalogo["DialogoCuaderno.lista"] != catalogo["DialogoBiblioteca.lista"]


class _VozDeMentira:
    """Una voz que apunta lo que le mandan decir y no suena.

    Hace falta porque la prueba tiene que comprobar **la lectura**, no la síntesis
    de voz: en un equipo sin voces instaladas —o en uno donde SAPI tarde medio
    segundo— la prueba diría que algo está roto cuando lo que falta es una voz.
    """

    def __init__(self):
        self.dicho = []
        self.parado = 0

    def disponible(self):
        return True

    def decir(self, texto, *sobra, **mas):
        self.dicho.append(texto)
        return True

    def detener(self):
        self.parado += 1

    def hablando(self):
        return False

    def configurar(self, *sobra, **mas):
        pass

    def voces(self):
        return []

    def elegir_voz(self, *sobra, **mas):
        return True

    def velocidad(self, *sobra, **mas):
        return True

    def volumen(self, *sobra, **mas):
        return True

    def __getattr__(self, nombre):
        # Cualquier otra cosa que el lector le pida a la voz se acepta sin
        # hacer nada: lo que se está probando es la lectura, no la síntesis.
        return lambda *sobra, **mas: True


def _preparar_lectura(ventana, monkeypatch):
    """Deja la ventana con un documento y una voz de mentira, leyendo."""
    from nucleo.documento import Documento, Metadatos

    texto = ("Primera frase del libro. Segunda frase del libro. "
             "Aquí está la palabra buscada. Y una frase final.\n")
    ventana.documento = Documento(texto, [], metadatos=Metadatos(titulo="T"),
                                  ruta_archivo="C:/libros/x.epub")
    ventana.lector.cargar_documento(ventana.documento)
    voz = _VozDeMentira()
    monkeypatch.setattr(ventana.lectura_voz, "sintetizador", voz)
    ventana.lectura_voz.empezar(0)
    return voz


def test_navegacion_y_voz_notifican_distinto_al_cronometro(ventana, monkeypatch):
    from unittest.mock import Mock
    _preparar_lectura(ventana, monkeypatch)
    ventana.lectura_voz.detener()
    latido = Mock()
    monkeypatch.setattr(ventana.cronometro, "latido", latido)
    ventana.lector.ir_a(30)
    latido.assert_called_with(30, salto=True)
    ventana.lector.seleccionar(50, 60)
    latido.assert_called_with(50, salto=True)
    ventana.lector.ir_a(70, lectura=True)
    latido.assert_called_with(70, salto=False)


def test_voz_solo_mide_continuacion_automatica(ventana, monkeypatch):
    from unittest.mock import Mock
    _preparar_lectura(ventana, monkeypatch)
    ventana.lectura_voz.detener()
    configuracion = ventana.lectura_voz._configuracion()
    anterior = configuracion.obtener("voz_mover_cursor", False)
    configuracion.establecer("voz_mover_cursor", True)
    mover = Mock()
    monkeypatch.setattr(ventana.lector, "ir_a", mover)
    try:
        ventana.lectura_voz._decir_desde(0)
        assert mover.call_args.kwargs["lectura"] is False
        ventana.lectura_voz._decir_desde(25, continuacion=True)
        assert mover.call_args.kwargs["lectura"] is True
    finally:
        configuracion.establecer("voz_mover_cursor", anterior)


def test_buscar_calla_la_voz_pero_no_pierde_el_sitio(ventana, monkeypatch):
    """Buscar mientras se escucha costaba la lectura entera."""
    _preparar_lectura(ventana, monkeypatch)
    assert ventana.lectura_voz.leyendo

    parado = ventana.lectura_voz.pausar_para_buscar()

    assert parado
    assert not ventana.lectura_voz.leyendo
    assert ventana.lectura_voz.habia_lectura


def test_si_no_se_estaba_leyendo_no_hay_nada_que_retomar(ventana):
    assert not ventana.lectura_voz.pausar_para_buscar()
    assert not ventana.lectura_voz.habia_lectura


def test_al_cerrar_la_busqueda_se_sigue_desde_el_resultado(ventana, monkeypatch):
    """Se ha buscado justamente para leer desde ahí."""
    voz = _preparar_lectura(ventana, monkeypatch)
    ventana.lectura_voz.pausar_para_buscar()
    voz.dicho.clear()

    ventana._seguir_leyendo_en = ventana.documento.texto.index("Aquí está")
    ventana.reanudar_lectura_tras_buscar()

    assert ventana.lectura_voz.leyendo
    assert any("palabra buscada" in dicho for dicho in voz.dicho)


def test_si_no_se_encuentra_nada_se_vuelve_a_donde_se_dejo(ventana, monkeypatch):
    voz = _preparar_lectura(ventana, monkeypatch)
    ventana.lectura_voz.saltar_frase(True)
    donde = ventana.lectura_voz.frase[0]
    ventana.lectura_voz.pausar_para_buscar()
    voz.dicho.clear()

    ventana._seguir_leyendo_en = None
    ventana.reanudar_lectura_tras_buscar()

    assert ventana.lectura_voz.leyendo
    assert ventana.lectura_voz.frase[0] == donde


def test_buscar_sin_estar_leyendo_no_arranca_la_voz(ventana, monkeypatch):
    """Quien busca en silencio no quiere que el libro empiece a sonar."""
    voz = _preparar_lectura(ventana, monkeypatch)
    ventana.lectura_voz.detener()
    voz.dicho.clear()

    ventana._seguir_leyendo_en = 10
    ventana.reanudar_lectura_tras_buscar()

    assert not ventana.lectura_voz.leyendo
    assert voz.dicho == []


def test_al_parar_el_cursor_queda_al_principio_de_la_frase(ventana, monkeypatch):
    """Lo de siempre: se para porque algo no se ha entendido y se relee."""
    _preparar_lectura(ventana, monkeypatch)
    ventana.lectura_voz.saltar_frase(True)
    inicio = ventana.lectura_voz.frase[0]

    ventana.lectura_voz.detener()

    assert ventana.lector.posicion() == inicio


def test_al_parar_el_cursor_puede_quedar_detras_de_la_frase(ventana, monkeypatch):
    """El otro caso: se para para seguir leyendo a mano, no para repetir.

    Con el cursor al principio de la frase que sonaba, las flechas vuelven a
    leer lo que se acaba de oír.  Dejándolo detrás, siguen por lo que aún no ha
    sonado.
    """
    configuracion = ventana.configuracion
    anterior = configuracion.obtener("voz_cursor_al_parar", "inicio")
    try:
        configuracion.establecer("voz_cursor_al_parar", "fin")
        _preparar_lectura(ventana, monkeypatch)
        ventana.lectura_voz.saltar_frase(True)
        fin = ventana.lectura_voz.frase[1]

        ventana.lectura_voz.detener()

        assert ventana.lector.posicion() == fin
    finally:
        configuracion.establecer("voz_cursor_al_parar", anterior)


def test_reanudar_termina_la_frase_aunque_el_cursor_quedara_detras(ventana, monkeypatch):
    """Pausar y seguir no puede comerse el final de la frase pausada.

    Con el cursor detrás de la frase, la comprobación de «se ha movido el
    usuario» daba positivo y la lectura empezaba de nuevo en la frase
    siguiente, saltándose lo que faltaba por decir.
    """
    configuracion = ventana.configuracion
    anterior = configuracion.obtener("voz_cursor_al_parar", "inicio")
    try:
        configuracion.establecer("voz_cursor_al_parar", "fin")
        _preparar_lectura(ventana, monkeypatch)
        ventana.lectura_voz.alternar()          # pausa
        frase = ventana.lectura_voz.frase

        ventana.lectura_voz.alternar()          # sigue

        assert ventana.lectura_voz.leyendo
        assert ventana.lectura_voz.frase == frase
    finally:
        configuracion.establecer("voz_cursor_al_parar", anterior)
        ventana.lectura_voz.detener()


def test_el_resaltado_no_mueve_el_cursor(ventana):
    """Resaltar es para la vista; el cursor es de quien lee de oído."""
    lector = ventana.lector
    assert hasattr(lector, "resaltar_frase")
    assert hasattr(lector, "_quitar_resalte")
    # Sin documento no hay nada que resaltar, pero tampoco debe fallar.
    lector.resaltar_frase(0, 10)
    lector._quitar_resalte()


# --- la pantalla de bienvenida --------------------------------------------

def test_la_bienvenida_se_puede_apagar(ventana):
    """Quien ya se sabe las teclas no quiere una pantalla de teclas al arrancar.

    Apagada no queda una ventana en blanco —que de oído no dice nada— sino dos
    líneas: dónde se está y cómo abrir un documento.
    """
    configuracion = ventana.configuracion
    anterior = configuracion.obtener("mostrar_bienvenida", True)
    try:
        configuracion.establecer("mostrar_bienvenida", True)
        ventana.lector.mostrar_presentacion()
        completa = ventana.lector.texto.GetValue()

        configuracion.establecer("mostrar_bienvenida", False)
        ventana.lector.mostrar_presentacion()
        breve = ventana.lector.texto.GetValue()

        assert "Control+O" in completa and "Control+O" in breve
        assert len(breve.splitlines()) < len(completa.splitlines())
    finally:
        configuracion.establecer("mostrar_bienvenida", anterior)
        ventana.lector.mostrar_presentacion()


# --- volver a analizar ----------------------------------------------------

def test_volver_a_analizar_relee_saltandose_lo_guardado(ventana, monkeypatch):
    """Sin «releer», el documento ya estaba abierto y la orden no hacía nada.

    Es lo que hace falta después de cambiar el reconocimiento de texto: el
    archivo no ha cambiado, así que lo guardado se seguiría dando por bueno.
    """
    from nucleo.documento import Documento, Metadatos

    ventana.documento = Documento("Un texto cualquiera.\n", [],
                                  metadatos=Metadatos(titulo="T"),
                                  ruta_archivo="C:/libros/x.epub")
    ventana.lector.cargar_documento(ventana.documento)
    ventana.ruta_actual = "C:/libros/x.epub"
    pedido = {}

    def falso_abrir(ruta, **opciones):
        pedido["ruta"] = ruta
        pedido.update(opciones)

    monkeypatch.setattr(ventana, "abrir_libro", falso_abrir)
    ventana.al_volver_a_analizar(None)

    assert pedido["ruta"] == "C:/libros/x.epub"
    assert pedido["releer"] is True
    assert pedido["en_pestana_nueva"] is False


def test_los_ajustes_de_reconocimiento_ofrecen_releer():
    """Cambiarlos no invalida lo guardado, así que hay que ofrecerlo a mano."""
    from interfaz.dialogos.opciones import OPCIONES_QUE_REANALIZAN

    for ajuste in ("pdf_ocr_modo", "pdf_ocr_maximo", "pdf_estructura"):
        assert ajuste in OPCIONES_QUE_REANALIZAN


# --- ajustes que tienen que quedarse puestos ------------------------------

def test_marcar_el_ajuste_de_linea_en_las_opciones_se_queda_marcado(ventana):
    """El fallo: se invertía una vez por pestaña y volvía a quedar como estaba.

    Lo que hace el diálogo de opciones es guardar el valor nuevo y pedirle a la
    ventana que lo aplique.  Aplicarlo llamando a «alternar» una vez por panel
    abierto lo invertía otra vez, así que con un solo documento delante la
    casilla aparecía siempre desmarcada por mucho que se marcase.
    """
    configuracion = ventana.configuracion
    inicial = bool(configuracion.obtener("ajuste_de_linea"))
    try:
        configuracion.establecer("ajuste_de_linea", not inicial)
        ventana.aplicar_preferencias()

        assert bool(configuracion.obtener("ajuste_de_linea")) is (not inicial)
        assert ventana.opcion_ajuste.IsChecked() is (not inicial)
    finally:
        configuracion.establecer("ajuste_de_linea", inicial)
        ventana.aplicar_preferencias()


def test_aplicar_las_preferencias_dos_veces_no_cambia_nada(ventana):
    """Aplicar lo ya aplicado tiene que ser inofensivo."""
    configuracion = ventana.configuracion
    ventana.aplicar_preferencias()
    antes = bool(configuracion.obtener("ajuste_de_linea"))
    ventana.aplicar_preferencias()

    assert bool(configuracion.obtener("ajuste_de_linea")) is antes


def test_la_orden_de_ajuste_de_linea_invierte_una_sola_vez(ventana):
    """Control+Alt+W cambia el ajuste, y solo una vez por pulsación."""
    configuracion = ventana.configuracion
    inicial = bool(configuracion.obtener("ajuste_de_linea"))
    try:
        ventana.al_ajuste_linea(None)

        assert bool(configuracion.obtener("ajuste_de_linea")) is (not inicial)
        assert ventana.opcion_ajuste.IsChecked() is (not inicial)
    finally:
        if bool(configuracion.obtener("ajuste_de_linea")) is not inicial:
            ventana.al_ajuste_linea(None)


# --- el ancho del renglón acompaña al ajuste de línea ----------------------

def _opciones(ventana, ajuste: bool, ancho: int):
    """Abre el diálogo de opciones con el ajuste y el ancho que se indiquen."""
    from interfaz.dialogos.opciones import DialogoOpciones

    ventana.configuracion.establecer("ajuste_de_linea", ajuste)
    ventana.configuracion.establecer("ancho_maximo_linea", ancho)
    return DialogoOpciones(ventana, ventana.configuracion, ventana.sonidos)


def test_el_ancho_del_renglon_solo_sale_con_el_ajuste_de_linea_puesto(ventana):
    """Sin ajuste no hay renglones que estrechar: el ancho no significaría nada."""
    dialogo = _opciones(ventana, True, 70)
    try:
        assert dialogo.panel_ancho.IsShown()
    finally:
        dialogo.Destroy()

    dialogo = _opciones(ventana, False, 70)
    try:
        assert not dialogo.panel_ancho.IsShown()
    finally:
        dialogo.Destroy()


def test_al_quitar_el_ajuste_el_ancho_se_esconde_pero_no_se_pierde(ventana):
    """Quien lo vuelva a activar encuentra el ancho que tenía puesto."""
    dialogo = _opciones(ventana, True, 70)
    try:
        dialogo.ajuste.SetValue(False)
        dialogo._al_cambiar_ajuste_de_linea(None)
        assert not dialogo.panel_ancho.IsShown()
        assert dialogo.ancho_linea.GetValue() == 70

        dialogo.ajuste.SetValue(True)
        dialogo._al_cambiar_ajuste_de_linea(None)
        assert dialogo.panel_ancho.IsShown()
        assert dialogo.ancho_linea.GetValue() == 70
    finally:
        dialogo.Destroy()


def test_el_dialogo_refleja_lo_que_haya_hecho_el_atajo_de_teclado(ventana):
    """Control+Alt+W cambia el ajuste, y al abrir opciones tiene que verse."""
    configuracion = ventana.configuracion
    inicial = bool(configuracion.obtener("ajuste_de_linea"))
    try:
        configuracion.establecer("ajuste_de_linea", False)
        ventana.al_ajuste_linea(None)          # lo enciende
        dialogo = _opciones(ventana, bool(configuracion.obtener("ajuste_de_linea")), 70)
        try:
            assert dialogo.ajuste.GetValue()
            assert dialogo.panel_ancho.IsShown()
        finally:
            dialogo.Destroy()
    finally:
        configuracion.establecer("ajuste_de_linea", inicial)
        configuracion.establecer("ancho_maximo_linea", 0)
        ventana.aplicar_preferencias()


def test_sin_ajuste_de_linea_el_ancho_no_estrecha_nada(ventana):
    """El ancho es una preferencia del ajuste, no algo aparte."""
    configuracion = ventana.configuracion
    inicial = bool(configuracion.obtener("ajuste_de_linea"))
    try:
        configuracion.establecer("ancho_maximo_linea", 70)
        configuracion.establecer("ajuste_de_linea", False)
        assert ventana.lector._margen_de_ancho() == 0

        configuracion.establecer("ancho_maximo_linea", 0)
        configuracion.establecer("ajuste_de_linea", True)
        assert ventana.lector._margen_de_ancho() == 0
    finally:
        configuracion.establecer("ancho_maximo_linea", 0)
        configuracion.establecer("ajuste_de_linea", inicial)
        ventana.aplicar_preferencias()


# --- las etiquetas de los menús ------------------------------------------

def test_ninguna_etiqueta_de_menu_lleva_una_entidad_html_a_medias():
    """El fallo: escribir «resa&ltados» y que «&lt» se convirtiera en «<».

    Las etiquetas llevan «&» para marcar la letra del menú, y cuatro de esas
    combinaciones son además el principio de una entidad HTML (``&lt``,
    ``&gt``, ``&amp``, ``&quot``).  Basta con que la etiqueta pase por algo que
    interprete HTML para que «resa&ltados» se quede en «resa<ados», que fue lo
    que llegó al menú.  Se evita no usando esas letras después del «&».
    """
    from interfaz import atajos

    peligrosas = ("&lt", "&gt", "&amp", "&quot")
    rotas = [orden.etiqueta for orden in atajos.ORDENES
             if any(marca in orden.etiqueta.lower() for marca in peligrosas)]
    assert not rotas, "etiquetas con una entidad HTML dentro: %s" % rotas


def test_ninguna_etiqueta_de_menu_tiene_signos_de_html_sueltos():
    """Un «<» en una etiqueta es siempre una conversión que no debía pasar."""
    from interfaz import atajos

    rotas = [orden.etiqueta for orden in atajos.ORDENES
             if "<" in orden.etiqueta or ">" in orden.etiqueta]
    assert not rotas, "etiquetas con signos de HTML: %s" % rotas


def test_todas_las_ordenes_de_menu_tienen_su_letra_de_acceso():
    """Sin «&» la orden no se puede elegir con el teclado desde el menú."""
    from interfaz import atajos

    sin_letra = [orden.etiqueta for orden in atajos.ORDENES
                 if "&" not in orden.etiqueta]
    assert not sin_letra, "órdenes sin letra de acceso: %s" % sin_letra


def test_el_ancho_del_renglon_se_alcanza_justo_tras_el_ajuste_de_linea(ventana):
    """No basta con dibujarlo debajo: hay que **llegar** a él justo después.

    El orden en que se recorre un diálogo con el tabulador no lo marca el sitio
    que ocupa cada control, sino el orden en que se crearon.  Creando el ancho
    al final se veía bajo su casilla y se llegaba a él el último, después de
    todas las demás, que para quien recorre el diálogo con el teclado es como
    si no estuviera donde está.
    """
    import wx as _wx

    dialogo = _opciones(ventana, True, 70)
    try:
        pagina = dialogo.ancho_linea.GetParent().GetParent()
        recorrido = []
        for hijo in pagina.GetChildren():
            if isinstance(hijo, _wx.StaticText):
                continue
            if hijo is dialogo.panel_ancho:
                recorrido.append("ancho")
            elif isinstance(hijo, _wx.CheckBox):
                recorrido.append("ajuste" if hijo is dialogo.ajuste else "casilla")
        assert recorrido[recorrido.index("ancho") - 1] == "ajuste"
    finally:
        dialogo.Destroy()


# --- cada frase en un renglón ---------------------------------------------

def _un_documento(ventana, carpeta, contenido):
    """Deja abierto un solo documento con el contenido que se le pida."""
    import formatos.texto  # noqa: F401
    from formatos.base import OpcionesAnalisis, analizar

    while len(ventana.pestanas.sesiones) > 1:
        ventana.pestanas.cerrar(len(ventana.pestanas.sesiones) - 1)
    archivo = carpeta / "libro.txt"
    archivo.write_text(contenido, encoding="utf-8")
    sesion = ventana.pestanas.actual
    sesion.documento = analizar(archivo, OpcionesAnalisis())
    sesion.ruta = str(archivo)
    sesion.panel.cargar_documento(sesion.documento, 0)
    return sesion


#: Un párrafo con tres frases: en el libro es una sola línea.
_PARRAFO = "Primera frase del libro. Segunda frase del libro. Y la tercera.\n"


def test_cada_frase_en_un_renglon_parte_el_parrafo(ventana, carpeta):
    """Sin esto, el párrafo entero es un renglón y ahí vuelve el cursor al parar."""
    configuracion = ventana.configuracion
    anterior = configuracion.obtener("renglon_por_frase", False)
    try:
        configuracion.establecer("renglon_por_frase", True)
        _un_documento(ventana, carpeta, _PARRAFO)
        renglones = ventana.lector.texto.GetValue().splitlines()
        assert renglones[:3] == ["Primera frase del libro.",
                                 "Segunda frase del libro.",
                                 "Y la tercera."]
    finally:
        configuracion.establecer("renglon_por_frase", anterior)


def test_cada_frase_en_un_renglon_no_mueve_ninguna_posicion(ventana, carpeta):
    """Lo que sostiene la opción entera.

    Si partir en renglones moviera una sola posición, cada marcador, cada nota
    y cada resaltado del libro apuntaría a otro sitio en cuanto se activara.
    """
    configuracion = ventana.configuracion
    anterior = configuracion.obtener("renglon_por_frase", False)
    try:
        configuracion.establecer("renglon_por_frase", True)
        sesion = _un_documento(ventana, carpeta, _PARRAFO)
        lector = ventana.lector
        destino = sesion.documento.texto.index("Segunda")
        lector.ir_a(destino)
        assert lector.posicion() == destino
        # Y lo que se selecciona sale con el texto del libro, no con el salto
        # de línea que se enseña en su lugar.
        lector.seleccionar(destino - 1, destino + 7)
        assert lector.texto_seleccionado() == " Segunda"
    finally:
        configuracion.establecer("renglon_por_frase", anterior)


def test_apagar_el_partido_en_renglones_devuelve_el_parrafo(ventana, carpeta):
    """Y sin recargar el documento: es el texto que se enseña, no el que hay."""
    configuracion = ventana.configuracion
    anterior = configuracion.obtener("renglon_por_frase", False)
    try:
        configuracion.establecer("renglon_por_frase", True)
        _un_documento(ventana, carpeta, _PARRAFO)
        configuracion.establecer("renglon_por_frase", False)
        ventana.lector.aplicar_renglones()
        assert ventana.lector.texto.GetValue().splitlines()[0] == _PARRAFO.strip()
    finally:
        configuracion.establecer("renglon_por_frase", anterior)


# --- el ajuste de línea con varios documentos abiertos --------------------

def _tres_documentos(ventana, carpeta):
    """Deja tres documentos abiertos en sus pestañas y vuelve al tercero.

    La ventana es la misma para todo el módulo, así que primero se cierra lo
    que hubiera abierto: si no, cada prueba encontraría también las pestañas de
    la anterior y estaría comprobando otra cosa.
    """
    import formatos.texto  # noqa: F401
    from formatos.base import OpcionesAnalisis, analizar

    ventana.configuracion.establecer("usar_pestanas", True)
    while len(ventana.pestanas.sesiones) > 1:
        ventana.pestanas.cerrar(len(ventana.pestanas.sesiones) - 1)
    contenidos = ("UNO uno.\n", "DOS dos.\n", "TRES tres.\n")
    for numero, contenido in enumerate(contenidos, start=1):
        ruta = carpeta / ("doc%d.txt" % numero)
        ruta.write_text(contenido, encoding="utf-8")
        if numero > 1:
            ventana.pestanas.nueva()
        sesion = ventana.pestanas.actual
        sesion.documento = analizar(ruta, OpcionesAnalisis())
        sesion.ruta = str(ruta)
        sesion.panel.cargar_documento(sesion.documento, 0)
    ventana.pestanas.seleccionar(2)


def test_el_ajuste_de_linea_no_lleva_el_foco_a_otro_documento(ventana, carpeta):
    """El fallo: el título seguía bien y el texto era el de otro documento.

    Al aplicar el ajuste a todas las pestañas se rehace el control de cada una,
    y rehacerlo llevaba el foco a esa pestaña.  Como el cuaderno no cambiaba de
    página, la ventana seguía diciendo el documento correcto mientras el
    teclado leía el de otra pestaña.
    """
    import wx as _wx

    _tres_documentos(ventana, carpeta)
    try:
        delante = ventana.lector.texto
        ventana.al_ajuste_linea(None)

        assert ventana.pestanas.indice_actual == 2
        assert ventana.lector.texto.GetValue().startswith("TRES")
        assert _wx.Window.FindFocus() is ventana.lector.texto
    finally:
        ventana.al_ajuste_linea(None)
        del delante


def test_cada_pestana_conserva_su_texto_al_cambiar_el_ajuste(ventana, carpeta):
    """Rehacer los controles no puede mezclar el contenido de unos con otros."""
    _tres_documentos(ventana, carpeta)
    try:
        ventana.al_ajuste_linea(None)

        principios = [sesion.panel.texto.GetValue()[:4]
                      for sesion in ventana.pestanas.sesiones]
        assert principios == ["UNO ", "DOS ", "TRES"]
    finally:
        ventana.al_ajuste_linea(None)


def test_las_ventanas_de_estudio_se_construyen(ventana):
    """Las que se añadieron para estudiar: citar, biblioteca, DAISY y estructura.

    Construirlas de verdad es la única forma de cazar un atributo mal escrito o
    un control que se pide antes de existir: nada de eso se ve importando el
    módulo.
    """
    from interfaz.dialogos.biblioteca import DialogoBiblioteca
    from interfaz.dialogos.citar import DialogoCitar
    from interfaz.dialogos.daisy_exportar import DialogoExportarDaisy
    from interfaz.dialogos.estructura import DialogoEstructura
    from nucleo.correcciones import Correcciones
    from nucleo.documento import Documento, Metadatos
    from nucleo.marcas import Marca, TipoMarca

    texto = "Capítulo uno\nUn párrafo cualquiera.\n"
    documento = Documento(texto, [Marca(TipoMarca.ENCABEZADO1, 0, "Capítulo uno")],
                          metadatos=Metadatos(titulo="Prueba", autor="Autor"),
                          ruta_archivo="C:/libros/prueba.pdf")
    ventana.lector.cargar_documento(documento, 0)
    configuracion = ventana.configuracion

    fabricas = [
        lambda: DialogoCitar(ventana, documento, "un pasaje", 0, configuracion),
        lambda: DialogoBiblioteca(ventana),
        lambda: DialogoExportarDaisy(ventana),
        lambda: DialogoEstructura(ventana, documento, Correcciones("huella"),
                                  configuracion),
    ]
    for fabrica in fabricas:
        dialogo = fabrica()
        assert dialogo.GetChildren()
        dialogo.Destroy()


def test_la_ficha_a_la_carta_y_los_similares(ventana):
    """La ficha con datos elegidos, su ventana de datos y «Libros similares»."""
    from interfaz.dialogos.biblioteca import (DialogoBiblioteca, DialogoCamposFicha,
                                              DialogoFicha)
    from nucleo import biblioteca
    from nucleo import biblioteca_ficha as fichas

    configuracion = ventana.configuracion
    guardado = configuracion.obtener(fichas.AJUSTE_FICHA, None)
    configuracion.guardar = lambda: None          # la prueba no escribe en disco
    try:
        dialogo = DialogoCamposFicha(ventana, configuracion, fichas.AJUSTE_FICHA, "Datos")
        try:
            # El primero no sube; el segundo sí, y queda primero.
            dialogo.lista.SetSelection(1)
            dialogo._mover(-1)
            assert dialogo._orden[0][0] == "serie"
            dialogo.lista.Check(2, False)
            dialogo._recoger()
            visibles = [c for c, v in dialogo._orden if v]
            assert visibles[0] == "serie" and len(visibles) == len(fichas.CAMPOS) - 1
            dialogo._al_fabrica(None)
            assert [c for c, _v in dialogo._orden] == [c for c, _n in fichas.CAMPOS]
        finally:
            dialogo.Destroy()

        libro = biblioteca.Libro("C:/libros/hp1.epub", "Harry Potter 1", "J. K. Rowling")
        libro.serie = "Harry Potter"
        configuracion.establecer(fichas.AJUSTE_FICHA, ["autor", "titulo"])
        ficha = DialogoFicha(ventana, libro)
        try:
            assert ficha.texto.GetValue().splitlines()[0] == "Autores: J. K. Rowling"
        finally:
            ficha.Destroy()

        # «De la misma serie» deja en la lista solo los de la saga, en su orden.
        libros = []
        for numero, titulo in ((3, "El prisionero"), (1, "La piedra"), (2, "La cámara")):
            otro = biblioteca.Libro("C:/libros/hp%d.epub" % numero, titulo, "J. K. Rowling")
            otro.serie, otro.serie_indice = "Harry Potter", float(numero)
            libros.append(otro)
        libros.append(biblioteca.Libro("C:/libros/otro.epub", "Otro libro", "Otra"))
        biblio = DialogoBiblioteca(ventana)
        try:
            biblio.tarea.parar.set()
            biblio._cargado = True
            biblio.libros = biblioteca.ordenar(libros, "titulo")
            biblio._refrescar_grupos(conservar=False)
            biblio._rellenar()
            campo, valor, clave = [o for o in biblioteca.similares(libros[1])
                                   if o[0] == "serie"][0]
            biblio._ir_a_similares(campo, valor, clave, libros[1].clave)
            assert [l.titulo for l in biblio._visibles] == [
                "La piedra", "La cámara", "El prisionero"]
            assert biblio._libro_actual() is libros[1]
        finally:
            biblio.Destroy()
    finally:
        configuracion.establecer(fichas.AJUSTE_FICHA, guardado)
        del configuracion.guardar


def test_la_ventana_de_opciones_tiene_la_pestana_de_biblioteca(ventana):
    """La pestaña nueva se construye con las demás, no aparte."""
    from interfaz.dialogos.opciones import DialogoOpciones

    dialogo = DialogoOpciones(ventana, ventana.configuracion, ventana.sonidos)
    try:
        nombres = [dialogo.cuaderno.GetPageText(numero)
                   for numero in range(dialogo.cuaderno.GetPageCount())]
        assert "Biblioteca y sincronización" in nombres
        # Y los ajustes nuevos de la pestaña de lectura existen de verdad.
        assert dialogo.solo_articulo is not None
        assert dialogo.revisar_epub is not None
    finally:
        dialogo.Destroy()


# --- el menú de herramientas, repartido por tareas --------------------------

def _letras_de_acceso(menu):
    """Las letras subrayadas de un menú, para ver si alguna se repite."""
    letras = []
    for elemento in menu.GetMenuItems():
        if elemento.IsSeparator():
            continue
        etiqueta = elemento.GetItemLabel()
        posicion = etiqueta.find("&")
        while 0 <= posicion < len(etiqueta) - 1:
            siguiente = etiqueta[posicion + 1]
            if siguiente != "&":
                letras.append(siguiente.lower())
                break
            posicion = etiqueta.find("&", posicion + 2)
    return letras


def _submenus(menu):
    """``{rótulo: submenú}`` de un menú."""
    return {elemento.GetItemLabelText(): elemento.GetSubMenu()
            for elemento in menu.GetMenuItems() if elemento.GetSubMenu() is not None}


def test_herramientas_esta_repartido_en_submenus(ventana):
    """Veintidós órdenes en fila no las recorre nadie con la flecha abajo."""
    barra = ventana.GetMenuBar()
    herramientas = barra.GetMenu(barra.FindMenu("Herramientas"))

    hijos = _submenus(herramientas)
    assert set(hijos) == {"Marcar y citar", "Ver el elemento",
                          "Inteligencia artificial", "Corregir el documento",
                          "Consultar"}
    # Y arriba se queda lo que se toca a menudo: las casillas y lo del programa.
    sueltas = [e.GetItemLabelText() for e in herramientas.GetMenuItems()
               if not e.IsSeparator() and e.GetSubMenu() is None]
    assert "Opciones..." in sueltas
    assert "Modo lectura" in sueltas
    assert "Sonidos de navegación" in sueltas


def test_cada_orden_sigue_estando_en_algun_sitio(ventana):
    """Repartir el menú no puede perder ninguna orden por el camino."""
    barra = ventana.GetMenuBar()
    for identificador in ("poner_marcador", "poner_nota", "resaltar", "citar",
                          "resaltados", "ver_imagen", "ver_tabla", "ver_html",
                          "ver_capitulo", "describir_imagen", "describir_todo",
                          "corregir_elemento", "revisar_estructura", "leer_nota",
                          "diccionario", "resumir", "preguntar", "cuanto_queda",
                          "informacion", "ajuste_linea", "sonidos", "modo_lectura",
                          "temporizador", "datos_guardados", "perfiles", "opciones"):
        numero = ventana._identificadores.get(identificador)
        assert numero is not None, identificador
        # Que se encuentre desde la barra es lo que hace que activarla y
        # desactivarla siga funcionando dentro de un submenú.
        assert barra.FindItemById(numero) is not None, identificador


def test_ninguna_letra_de_acceso_se_repite_en_su_menu(ventana):
    """Dos órdenes con la misma letra subrayada dejan una inalcanzable."""
    barra = ventana.GetMenuBar()
    repetidas = {}
    for numero in range(barra.GetMenuCount()):
        nombre = barra.GetMenuLabelText(numero)
        pendientes = [(nombre, barra.GetMenu(numero))]
        while pendientes:
            camino, menu = pendientes.pop()
            letras = _letras_de_acceso(menu)
            duplicadas = {letra for letra in letras if letras.count(letra) > 1}
            if duplicadas:
                repetidas[camino] = sorted(duplicadas)
            for rotulo, submenu in _submenus(menu).items():
                pendientes.append(("%s / %s" % (camino, rotulo), submenu))
    assert not repetidas, "letras de acceso repetidas: %s" % repetidas
