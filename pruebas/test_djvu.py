# -*- coding: utf-8 -*-
"""Pruebas del lector de DjVu y de su descompresor BZZ.

La prueba de verdad es la última: se abre un DjVu real digitalizado en una
biblioteca y se compara **palabra por palabra** con el texto que el propio
archivo declara. Un descompresor casi bien devuelve basura que parece texto, y
eso es peor que no tener el formato: quien lo escuche no tiene forma de saber
que lo que oye no es lo que pone el libro.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from formatos import base, bzz, djvu  # noqa: F401  registra el analizador

DATOS = Path(__file__).resolve().parent / "datos"
MUESTRA = DATOS / "muestra.djvu"
REFERENCIA = DATOS / "muestra_djvu.txt"


@pytest.fixture(scope="module")
def documento():
    return base.analizar(MUESTRA)


# --- El envoltorio ---------------------------------------------------------

def test_los_trozos_se_recorren_en_orden():
    datos = MUESTRA.read_bytes()
    assert datos.startswith(djvu.FIRMA)
    nombres = [t.nombre for t in djvu.trozos(datos, 16, len(datos))]
    assert b"DIRM" in nombres
    assert nombres.count(b"FORM") == 4


def test_un_trozo_truncado_no_tira_el_archivo():
    """Un DjVu al que le falta el final conserva todo lo anterior."""
    datos = MUESTRA.read_bytes()
    enteros = list(djvu.trozos(datos, 16, len(datos)))
    recortados = list(djvu.trozos(datos, 16, len(datos) - 5000))
    assert 0 < len(recortados) <= len(enteros)


# --- El descompresor -------------------------------------------------------

def _primer_txtz(datos):
    """El primer trozo de texto del archivo. Es BZZ desde su primer byte."""
    for trozo in djvu.trozos(datos, 16, len(datos)):
        if trozo.nombre != b"FORM":
            continue
        for interno in djvu.trozos(datos, trozo.inicio + 4,
                                   trozo.inicio + trozo.largo):
            if interno.nombre == b"TXTz":
                return interno
    raise AssertionError("la muestra ya no trae capa de texto")


def test_acotar_el_chorro_da_lo_mismo_que_recortarlo():
    datos = MUESTRA.read_bytes()
    trozo = _primer_txtz(datos)
    acotado = bzz.descomprimir(datos, trozo.inicio, trozo.inicio + trozo.largo)
    aparte = bzz.descomprimir(datos[trozo.inicio:trozo.inicio + trozo.largo])
    assert acotado == aparte
    assert b"JSTOR" in acotado


def test_sin_acotar_el_chorro_se_come_lo_que_hay_detras():
    """Es el fallo que dejaba el indice de un DjVu en basura.

    El descompresor solo para al leer un tamano de bloque cero. Si se le deja
    seguir mas alla de su trozo, lo primero que encuentra detras lo toma por
    otro bloque; aqui el guardia del tamano maximo lo caza.
    """
    datos = MUESTRA.read_bytes()
    trozo = _primer_txtz(datos)
    bueno = bzz.descomprimir(datos, trozo.inicio, trozo.inicio + trozo.largo)
    try:
        suelto = bzz.descomprimir(datos, trozo.inicio)
    except bzz.Corrupto:
        return
    assert suelto != bueno, "sin acotar deberia salir algo distinto"


def test_un_chorro_truncado_da_error_y_no_basura_infinita():
    datos = MUESTRA.read_bytes()
    trozo = _primer_txtz(datos)
    with pytest.raises(bzz.Corrupto):
        bzz.descomprimir(datos[trozo.inicio:trozo.inicio + 40])


def test_la_tabla_de_estados_esta_completa():
    assert len(bzz._P) == len(bzz._M) == len(bzz._SUBE) == len(bzz._BAJA) == 251
    assert max(max(bzz._SUBE), max(bzz._BAJA)) < 251


# --- Juntar los renglones --------------------------------------------------

def test_se_deshacen_los_guiones_de_particion():
    assert djvu.juntar(["una na-", "turaleza rara"]) == "una naturaleza rara"


def test_un_guion_detras_de_una_cifra_no_parte_ninguna_palabra():
    assert djvu.juntar(["marzo de 1759-", "Leido el 22"]) == "marzo de 1759- Leido el 22"


def test_en_una_direccion_el_guion_se_conserva():
    juntado = djvu.juntar(["http://ejemplo.org/cosas/early-", "journal-content"])
    assert juntado == "http://ejemplo.org/cosas/early-journal-content"


def test_los_renglones_normales_se_unen_con_un_espacio():
    assert djvu.juntar(["primera linea", "segunda linea"]) == "primera linea segunda linea"


# --- El documento ----------------------------------------------------------

def test_se_abre_con_sus_paginas(documento):
    assert len(documento.secciones) == 4
    from nucleo.marcas import TipoMarca
    assert documento.marcas.cantidad(TipoMarca.SALTO_PAGINA) == 4
    assert documento.marcas.cantidad(TipoMarca.SALTO_SECCION) == 4


def test_el_texto_coincide_con_el_del_propio_archivo(documento):
    """Palabra por palabra contra el texto que el archivo declara.

    Las únicas diferencias admitidas son a nuestro favor: donde el volcado
    corriente deja «na-» y «turaleza» en dos palabras, aquí sale «naturaleza».
    """
    def desnudo(texto):
        """Solo las letras: sin espacios, sin saltos y sin guiones.

        Se quitan los guiones y los espacios porque ahi es justo donde los dos
        textos tienen que diferir: donde el volcado corriente deja <<na->> y
        <<turaleza>> en dos palabras, aqui sale <<naturaleza>>. Lo que no puede
        cambiar es **ni una letra**, y eso es lo que se compara.
        """
        return "".join(texto.split()).replace("-", "")

    nuestro = desnudo(documento.texto)
    suyo = desnudo(REFERENCIA.read_text(encoding="utf-8"))
    assert nuestro == suyo, "el texto no coincide letra por letra"

    # Y las palabras partidas tienen que haberse recompuesto, no perdido.
    palabras = " ".join(documento.texto.split()).split()
    suyas = " ".join(REFERENCIA.read_text(encoding="utf-8").split()).split()
    partidas = [p for p in suyas if p.endswith("-") and len(p) > 2]
    assert len(partidas) >= 10, "la muestra ya no sirve para comprobar esto"
    assert len(palabras) < len(suyas), "no se ha unido ninguna palabra partida"


def test_los_parrafos_se_reconstruyen_sin_partir_palabras(documento):
    """Los rangos de las zonas cortan a media palabra; no debe notarse."""
    for rota in ("Jam es", "you ng", "Lor dfliip", "tur e"):
        assert rota not in documento.texto


def test_un_archivo_que_no_es_djvu_lo_dice_claro(carpeta):
    falso = carpeta / "falso.djvu"
    falso.write_bytes(b"esto no es un DjVu, ni de lejos")
    with pytest.raises(base.ErrorFormato):
        base.analizar(falso)


# --- La máscara en blanco y negro ------------------------------------------


def _paginas(datos: bytes):
    """Los envoltorios de página del archivo de muestra."""
    salida = []
    for trozo in djvu.trozos(datos, 16, len(datos)):
        if trozo.nombre == b"FORM" and datos[trozo.inicio:trozo.inicio + 4] == b"DJVU":
            salida.append(trozo)
    return salida


class PruebaMascara:
    """El trozo ``Sjbz``: el texto y los dibujos de línea de cada página.

    Es lo que convierte un DjVu **sin** capa de texto de «no se puede abrir» a
    un libro: descomprimida la máscara, la página se puede reconocer aquí
    mismo. Hasta ahora no había forma de sacarla.
    """

    def test_todas_las_paginas_dan_su_mapa(self):
        datos = MUESTRA.read_bytes()
        paginas = _paginas(datos)
        assert len(paginas) == 4
        for numero, trozo in enumerate(paginas, start=1):
            mapa = djvu.mascara_de(datos, trozo)
            assert mapa is not None, numero
            assert mapa.ancho > 1000 and mapa.alto > 1000, numero

    def test_el_tamano_es_el_que_declara_el_archivo(self):
        """El ``INFO`` dice el tamaño de la página; la máscara tiene que darlo.

        Es la comprobación más barata de que no se ha perdido el paso en medio
        del flujo: el tamaño sale del principio del JB2, y si el resto se
        descolocara seguiría saliendo bien, pero al revés no.
        """
        import struct

        datos = MUESTRA.read_bytes()
        for trozo in _paginas(datos):
            declarado = None
            for interno in djvu.trozos(datos, trozo.inicio + 4,
                                       trozo.inicio + trozo.largo):
                if interno.nombre == b"INFO":
                    declarado = struct.unpack(
                        ">HH", datos[interno.inicio:interno.inicio + 4])
                    break
            mapa = djvu.mascara_de(datos, trozo)
            assert (mapa.ancho, mapa.alto) == declarado

    def test_hay_tinta_y_no_toda_la_pagina_es_tinta(self):
        """Una página de texto tiene poca tinta, pero tiene.

        Los dos errores que de verdad pasan al escribir esto dan justo los dos
        extremos: un mapa en blanco —el descodificador se perdió en el primer
        registro— o un mapa casi negro —los contextos se desincronizaron y todo
        salió a uno—. Ninguno de los dos revienta; los dos se ven aquí.
        """
        datos = MUESTRA.read_bytes()
        for trozo in _paginas(datos):
            mapa = djvu.mascara_de(datos, trozo)
            tinta = sum(sum(fila) for fila in mapa.filas)
            parte = tinta / (mapa.ancho * mapa.alto)
            assert 0.005 < parte < 0.35, parte

    def test_el_png_que_sale_es_un_png_de_un_bit(self):
        import struct

        from formatos import jb2

        datos = MUESTRA.read_bytes()
        mapa = djvu.mascara_de(datos, _paginas(datos)[0])
        imagen = jb2.a_png(mapa)
        assert imagen.startswith(b"\x89PNG\r\n\x1a\n")
        ancho, alto, profundidad, color = struct.unpack(">IIBB", imagen[16:26])
        assert (ancho, alto) == (mapa.ancho, mapa.alto)
        assert profundidad == 1 and color == 0
        # Una página de texto en blanco y negro **tiene** que comprimir mucho:
        # si saliera del tamaño de la imagen sin comprimir, lo que hay dentro
        # es ruido y no letras.
        assert len(imagen) < ancho * alto // 8 // 10

    def test_una_pagina_que_no_trae_mascara_lo_dice(self):
        """No todas las traen: una lámina a color va solo en ondículas.

        Devolver ``None`` es la respuesta correcta, y es lo que deja que quien
        llama decida.  Inventarse una página en blanco haría que el reconocedor
        trabajara sobre nada y devolviera nada, sin que nadie supiera por qué.
        """
        datos = MUESTRA.read_bytes()
        pagina = _paginas(datos)[0]
        sin_sjbz = bytearray(datos)
        for interno in djvu.trozos(datos, pagina.inicio + 4,
                                   pagina.inicio + pagina.largo):
            if interno.nombre == b"Sjbz":
                sin_sjbz[interno.inicio - 8:interno.inicio - 4] = b"FREE"
        assert djvu.mascara_de(bytes(sin_sjbz), pagina) is None

    def test_una_mascara_rota_no_se_lee_a_medias(self):
        """Cortada por la mitad se avisa, no se devuelve media página.

        Media página descomprimida y media en blanco no se distingue de una
        página que acaba ahí, y quien la lea creerá que el capítulo termina en
        mitad de una frase.
        """
        from formatos import jb2

        datos = MUESTRA.read_bytes()
        pagina = _paginas(datos)[0]
        for interno in djvu.trozos(datos, pagina.inicio + 4,
                                   pagina.inicio + pagina.largo):
            if interno.nombre == b"Sjbz":
                mitad = interno.inicio + interno.largo // 2
                roto = bytearray(datos)
                # Se cambia el contenido, no el tamaño: así el flujo sigue
                # teniendo la longitud que dice y el fallo es de verdad del
                # descodificador y no del recorrido de trozos.
                roto[interno.inicio + 20:mitad] = b"\x5a" * (mitad - interno.inicio - 20)
                with pytest.raises(Exception):
                    jb2.componer(jb2.leer_mascara(
                        bytes(roto), interno.inicio, interno.inicio + interno.largo))
                return
        pytest.fail("la muestra ya no trae Sjbz")

    def test_una_forma_que_no_esta_se_dice(self):
        """Pedir una forma que no existe es un error, no un mapa en blanco.

        Es la guarda que separa «este archivo está roto» de «esta letra salió
        vacía»: lo segundo no se nota al leer y lo primero sí.
        """
        from formatos.bzz import Corrupto
        from formatos import jb2

        with pytest.raises(Corrupto):
            jb2.Coleccion().forma(7)

    def test_un_mapa_imposible_no_se_reserva(self):
        """Un tamaño absurdo se rechaza antes de pedir la memoria.

        Un archivo corrupto puede declarar una forma de dos mil millones de
        píxeles.  Reservarla deja el programa sin memoria antes de que nadie
        pueda cancelar nada, así que el tamaño se mira primero.
        """
        from formatos.bzz import Corrupto
        from formatos import jb2

        with pytest.raises(Corrupto):
            jb2.Mapa(200000, 200000)

    def test_sin_INCL_no_se_busca_diccionario(self):
        """Casi ningún DjVu lleva diccionario compartido, y no pasa nada.

        La mayoría de los compresores meten el diccionario **dentro** del
        propio ``Sjbz`` de cada página.  El compartido existe y hay que saber
        resolverlo, pero no tenerlo es lo normal.
        """
        datos = MUESTRA.read_bytes()
        for trozo in _paginas(datos):
            assert djvu._diccionario_de(datos, trozo, {}, {}) is None


    def test_la_pagina_descomprimida_se_puede_leer(self):
        """Se reconoce y se compara con el texto que trae el propio archivo.

        Es la única prueba que distingue una máscara correcta de una que
        simplemente no revienta.  Se pide poco —la mitad de las palabras
        largas—, porque lo que se comprueba es la imagen y no el acierto del
        reconocedor: un OCR se equivoca en letras sueltas, pero sobre una
        página desplazada o invertida no acierta ni una palabra.
        """
        from formatos import ocr

        if "tesseract" not in ocr.motores_disponibles(None, "tesseract"):
            pytest.skip("Tesseract no está disponible en este equipo")

        datos = MUESTRA.read_bytes()
        mapa = djvu.mascara_de(datos, _paginas(datos)[0])
        from formatos import jb2

        leido = ocr.reconocer(jb2.a_png(mapa), None, modo="tesseract")
        salen = set(_palabras_largas(leido.texto))

        esperadas = _palabras_largas(REFERENCIA.read_text(encoding="utf-8")[:1200])
        aciertos = sum(1 for palabra in esperadas if palabra in salen)
        assert aciertos >= len(esperadas) // 2, (aciertos, len(esperadas))


def _palabras_largas(texto: str) -> list:
    """Las palabras de seis letras o más, en minúsculas y sin puntuación.

    Las cortas no valen para comparar: «de», «la» y «en» salen de cualquier
    ruido, y acertarlas no diría nada sobre si la página está bien.
    """
    import re

    return [p for p in re.findall(r"[^\W\d_]{6,}", texto.lower())]

# --- Las capas de color ----------------------------------------------------


class PruebaOndiculas:
    """El trozo ``BG44``: el papel, las fotografías y las láminas.

    Es la capa que hace que una página **sin una sola letra** deje de ser un
    hueco mudo en el documento. Comprobar que no revienta no vale de nada: una
    transformada mal deshecha devuelve una imagen del tamaño correcto y con
    ruido dentro, así que lo que se comprueba es que se parezca a una página.
    """

    def test_el_fondo_tiene_el_tamano_que_le_toca(self):
        """El fondo va submuestreado, y por un número entero de veces.

        DjVu guarda el papel a un tercio o a un quinto del tamaño de la página
        porque el papel no tiene detalle fino: el detalle está en la máscara.
        Si saliera a otra escala, sería que la cabecera se ha leído mal.
        """
        datos = MUESTRA.read_bytes()
        pagina = _paginas(datos)[0]
        capa = djvu.fondo_de(datos, pagina)
        assert capa is not None
        mapa = djvu.mascara_de(datos, pagina)
        veces = round(mapa.ancho / capa.ancho)
        assert veces in (1, 2, 3, 4, 5, 6, 12)
        assert abs(capa.ancho * veces - mapa.ancho) <= veces
        assert abs(capa.alto * veces - mapa.alto) <= veces

    def test_el_papel_es_claro_y_no_uniforme(self):
        """Una página escaneada es papel claro con manchas, no un rectángulo.

        Los dos fallos que de verdad pasan salen aquí: una imagen plana —la
        transformada no se aplicó— y una imagen oscura o en negativo, que es lo
        que sale al confundir la luz con la tinta.
        """
        datos = MUESTRA.read_bytes()
        capa = djvu.fondo_de(datos, _paginas(datos)[0])
        _ancho, _alto, filas = capa.imagen()
        valores = [fila[i] for fila in filas[::17] for i in range(0, len(fila), 51)]
        medio = sum(valores) / len(valores)
        assert medio > 200, medio
        assert min(valores) < medio - 20, (min(valores), medio)

    def test_el_fondo_de_esta_pagina_lleva_color(self):
        """Y el color no se inventa: el logotipo de la portada es de color.

        Si la transformada de color se hiciera con la del JPEG en vez de con la
        de DjVu, la página saldría reconocible y con los colores cambiados, que
        es la peor manera de equivocarse porque no se nota mirando el tamaño.
        """
        datos = MUESTRA.read_bytes()
        capa = djvu.fondo_de(datos, _paginas(datos)[0])
        assert not capa.gris
        _ancho, _alto, filas = capa.imagen()
        coloreados = 0
        for fila in filas:
            for i in range(0, len(fila), 3):
                rojo, verde, azul = fila[i], fila[i + 1], fila[i + 2]
                if max(rojo, verde, azul) - min(rojo, verde, azul) > 40:
                    coloreados += 1
        assert coloreados > 100, coloreados

    def test_una_pagina_sin_texto_ni_mascara_queda_como_imagen(self):
        """Es el caso que motivó todo esto: una lámina suelta.

        Antes esa página no existía en el documento: ni texto que leer ni
        imagen que ver. Ahora se recorre con `G` y se puede describir.
        """
        datos = MUESTRA.read_bytes()
        pagina = _paginas(datos)[0]
        sin_mascara = bytearray(datos)
        for interno in djvu.trozos(datos, pagina.inicio + 4,
                                   pagina.inicio + pagina.largo):
            if interno.nombre == b"Sjbz":
                sin_mascara[interno.inicio - 8:interno.inicio - 4] = b"FREE"
        imagen, es_mascara = djvu.imagen_de(bytes(sin_mascara), pagina)
        assert imagen is not None
        assert not es_mascara
        assert imagen.startswith(b"\x89PNG\r\n\x1a\n")

    def test_se_prefiere_la_mascara_cuando_la_hay(self):
        """Y no por comodidad: es más nítida y ocupa una décima parte."""
        datos = MUESTRA.read_bytes()
        pagina = _paginas(datos)[0]
        imagen, es_mascara = djvu.imagen_de(datos, pagina)
        assert es_mascara
        assert imagen == djvu_jb2().a_png(djvu.mascara_de(datos, pagina))

    def test_los_trozos_desordenados_se_rechazan(self):
        """Cada trozo continúa el anterior, así que el orden es el contenido.

        Leerlos cambiados no da un error del descompresor: da una imagen mal, y
        eso no se nota mirándola si uno no sabe cómo era.
        """
        from formatos.bzz import Corrupto
        from formatos import iw44

        datos = MUESTRA.read_bytes()
        piezas = [interno for interno in djvu.trozos(
            datos, _paginas(datos)[0].inicio + 4,
            _paginas(datos)[0].inicio + _paginas(datos)[0].largo)
            if interno.nombre == b"BG44"]
        capa = iw44.Capa()
        with pytest.raises(Corrupto):
            capa.trozo(datos, piezas[1].inicio, piezas[1].inicio + piezas[1].largo)

    def test_el_zigzag_es_una_permutacion(self):
        """Mil veinticuatro sitios, cada uno una vez.

        La tabla no se copia: se genera entrelazando los bits del índice.  Si
        la fórmula estuviera mal, la tabla repetiría sitios y dejaría otros sin
        cubrir, y eso se ve aquí sin necesidad de descomprimir nada.
        """
        from formatos import iw44

        assert len(iw44.ZIGZAG) == 1024
        assert sorted(iw44.ZIGZAG) == list(range(1024))
        # Los cuatro primeros son las esquinas del bloque de dos por dos de la
        # escala más gruesa, que es por donde empieza el formato.
        assert iw44.ZIGZAG[:3] == (0, 16, 512)


def djvu_jb2():
    from formatos import jb2

    return jb2


class PruebaDjVuSinTexto:
    """Un DjVu que no trae texto dentro se reconoce al abrirlo."""

    def test_sin_capa_de_texto_y_sin_ocr_se_explica(self, tmp_path):
        """Con el reconocimiento apagado se dice qué pasa, no se abre vacío."""
        datos = bytearray(MUESTRA.read_bytes())
        for trozo in _paginas(bytes(datos)):
            for interno in djvu.trozos(bytes(datos), trozo.inicio + 4,
                                       trozo.inicio + trozo.largo):
                if interno.nombre == b"TXTz":
                    datos[interno.inicio - 8:interno.inicio - 4] = b"FREE"
        destino = tmp_path / "sin_texto.djvu"
        destino.write_bytes(bytes(datos))

        analizador = djvu.AnalizadorDjVu()
        analizador.ocr_modo = "ninguno"
        with pytest.raises(base.ErrorFormato) as fallo:
            analizador.analizar(destino, base.OpcionesAnalisis())
        assert "reconoc" in str(fallo.value).lower()

    def test_el_tope_de_paginas_se_respeta(self, tmp_path):
        """Reconocer es lento; el tope está para que no se eternice."""
        analizador = djvu.AnalizadorDjVu()
        assert analizador.ocr_maximo == 100
        assert analizador.ocr_modo == "auto"


# --- El diccionario compartido entre páginas -------------------------------

COMPARTIDO = (Path(__file__).resolve().parent.parent / "adjuntos" / "Estudio"
              / "muestras" / "diccionario_compartido.djvu")


@pytest.mark.lenta
class PruebaDiccionarioCompartido:
    """Un libro que guarda la «a» una vez para el tomo entero.

    Es el camino que más tardó en poder probarse: de los cincuenta y pico DjVu
    mirados no lo llevaba ninguno, porque casi todos los compresores meten el
    diccionario dentro de la propia página. El archivo de aquí es la portada de
    *Le Petit Parisien* del 18 de marzo de 1883, digitalizada por la Biblioteca
    Nacional de Francia y publicada en Wikimedia Commons: cuatro páginas de
    periódico que comparten **treinta y cinco mil formas**.
    """

    def _datos(self):
        if not COMPARTIDO.is_file():
            pytest.skip("la muestra con diccionario compartido no está guardada")
        return COMPARTIDO.read_bytes()

    def _preparar(self, datos):
        dentro = djvu.envoltorios(datos)
        por_id = {archivo.identificador: dentro.formularios[numero]
                  for numero, archivo in enumerate(dentro.archivos)
                  if numero < len(dentro.formularios)}
        return dentro, por_id

    def test_el_diccionario_se_encuentra_y_se_lee(self):
        datos = self._datos()
        dentro, por_id = self._preparar(datos)

        diccionario = djvu._diccionario_de(datos, dentro.paginas[0], por_id, {})

        assert diccionario is not None
        # Treinta y cinco mil formas para cuatro páginas: eso es exactamente lo
        # que un diccionario compartido sirve para ahorrar.
        assert diccionario.cuantas() > 30000

    def test_todas_las_paginas_usan_el_mismo(self):
        """Y se lee **una sola vez**: cada página lo pide por su nombre."""
        datos = self._datos()
        dentro, por_id = self._preparar(datos)
        guardados: dict = {}

        cuales = [djvu._diccionario_de(datos, pagina, por_id, guardados)
                  for pagina in dentro.paginas]

        assert len(guardados) == 1
        assert all(cual is cuales[0] for cual in cuales)

    def test_sin_el_diccionario_la_pagina_se_niega(self):
        """Y así tiene que ser: sin las formas heredadas faltan las letras.

        Una página que siguiera adelante saldría con manchas donde va el texto,
        y eso no se nota leyéndola. Vale más una página que no sale.
        """
        from formatos.bzz import Corrupto
        from formatos import jb2

        datos = self._datos()
        dentro, _por_id = self._preparar(datos)
        pagina = dentro.paginas[0]

        for interno in djvu.trozos(datos, pagina.inicio + 4,
                                   pagina.inicio + pagina.largo):
            if interno.nombre == b"Sjbz":
                with pytest.raises(Corrupto):
                    jb2.leer_mascara(datos, interno.inicio,
                                     interno.inicio + interno.largo, None)
                return
        pytest.fail("la muestra ya no trae Sjbz")

    def test_la_portada_del_periodico_sale_entera(self):
        """Ocho mil por doce mil ochocientos, con sus seis columnas.

        Se comprueba la proporción de tinta: un periódico de 1883 a plomo tiene
        mucha más que un libro, pero muy lejos de la mitad. Un mapa en blanco o
        uno casi negro —los dos fallos que de verdad pasan— caen aquí.
        """
        datos = self._datos()
        dentro, por_id = self._preparar(datos)
        pagina = dentro.paginas[0]

        mapa = djvu.mascara_de(
            datos, pagina, djvu._diccionario_de(datos, pagina, por_id, {}))

        assert mapa.ancho > 8000 and mapa.alto > 12000
        tinta = sum(sum(fila) for fila in mapa.filas)
        parte = tinta / (mapa.ancho * mapa.alto)
        assert 0.05 < parte < 0.35, parte

    def test_una_forma_del_tamano_de_la_pagina_cabe(self):
        """El grabado de la cabecera es **una sola forma** de página entera.

        Por eso el tope de tamaño es uno y no dos: separar «forma pequeña» de
        «página grande» dejaba fuera este archivo por una regla inventada.
        """
        from formatos import jb2

        assert jb2._MAXIMO_MAPA > 8600 * 12900
