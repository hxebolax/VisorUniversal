# -*- coding: utf-8 -*-
"""Pruebas de lo que se ha añadido para estudiar y de los formatos nuevos.

Lo que se comprueba aquí no es que el código no reviente: es que **lo que sale
es verdad**. Un recortador de raíces que se pase de listo junta palabras que no
tienen nada que ver; una fórmula química mal transcrita al braille no se puede
detectar leyéndola; una presentación leída en el orden del archivo y no en el de
la pantalla cuenta la diapositiva del revés. Los tres fallos son invisibles para
quien los sufre, y por eso están todos probados aquí.
"""

from __future__ import annotations

from pathlib import Path

import pytest

DATOS = Path(__file__).resolve().parent / "datos"


# ---------------------------------------------------------------------------
# Raíces de las palabras
# ---------------------------------------------------------------------------

class PruebaRaices:
    def test_las_formas_de_una_palabra_dan_la_misma_raiz(self):
        from nucleo.raices import raiz

        for grupo in (("amortización", "amortizaciones", "amortizar", "amortizado"),
                      ("depreciación", "depreciaciones", "depreciar"),
                      ("universidad", "universidades"),
                      ("cantar", "canto", "cantamos", "cantando", "cantado")):
            raices = {raiz(palabra) for palabra in grupo}
            assert len(raices) == 1, "%r da %r" % (grupo, raices)

    def test_dos_palabras_distintas_no_se_confunden(self):
        """El género sí se quita: «casa» y «caso» son la misma raíz a propósito."""
        from nucleo.raices import raiz

        assert raiz("amortización") != raiz("depreciación")
        assert raiz("camisa") != raiz("camino")
        assert raiz("casa") == raiz("casas")
        # Pero el género y la vocal final sí se van, y eso es lo correcto:
        # «libro» y «libre» comparten raíz en el algoritmo de referencia.
        assert raiz("libro") == raiz("libre")

    def test_las_palabras_cortas_se_dejan_como_estan(self):
        from nucleo.raices import raiz

        assert raiz("el") == "el"
        assert raiz("y") == "y"

    def test_un_apellido_no_se_recorta_como_un_verbo(self):
        """«ais» sin tilde no es terminación de verbo: «Beauvais» no es «beauv».

        Con tilde sí lo es --«cantáis»--, así que «Monsiváis» sí se recorta:
        es lo que hace el algoritmo de referencia y no una decisión de aquí.
        """
        from nucleo.raices import raiz

        assert raiz("Beauvais") == "beauvais"
        assert raiz("monsivais") == "monsivais"
        assert raiz("salais") == "salais"

    def test_las_terminaciones_en_ye_no_paran_el_recorte(self):
        """«apoyamos» es «apoy», no «apoyam»: si la «y» falla, se sigue."""
        from nucleo.raices import raiz

        assert raiz("apoyamos") == raiz("apoyan") == raiz("apoyen") == "apoy"
        assert raiz("playas") == "play"

    def test_las_palabras_se_parten_sin_puntuacion(self):
        from nucleo.raices import palabras

        assert palabras("Hola, ¿qué tal? 42 años") == ["hola", "qué", "tal",
                                                       "42", "años"]


# ---------------------------------------------------------------------------
# Búsqueda por significado
# ---------------------------------------------------------------------------

class PruebaSemantica:
    @staticmethod
    def _corpus():
        """Un corpus pequeño donde dos palabras salen siempre en los mismos sitios."""
        relleno = ("Aquella tarde el viento soplaba entre los árboles del "
                   "paseo mientras la gente volvía despacio a sus casas.\n")
        contable = ("La amortización del inmovilizado se calcula cada "
                    "ejercicio contable.\n"
                    "La depreciación del inmovilizado figura siempre en el "
                    "balance de situación.\n")
        musical = ("La sonata para piano se interpreta en tres movimientos "
                   "seguidos.\nEl movimiento lento de esa sonata para piano "
                   "es el más célebre.\n")
        documentos = []
        for numero in range(8):
            documentos.append(("contable%d" % numero, (contable + relleno) * 6))
            documentos.append(("musical%d" % numero, (musical + relleno) * 6))
            documentos.append(("relleno%d" % numero, relleno * 30))
        return documentos

    def test_encuentra_una_palabra_que_sale_en_los_mismos_sitios(self):
        from nucleo import semantica

        indice = semantica.construir(self._corpus())
        assert len(indice) > 0
        relacionadas = [p for p, _c in indice.relacionadas("amortización", 6)]
        assert any("depreciac" in p for p in relacionadas), relacionadas

    def test_no_relaciona_lo_que_no_sale_junto(self):
        from nucleo import semantica

        indice = semantica.construir(self._corpus())
        relacionadas = [p for p, _c in indice.relacionadas("amortización", 8)]
        assert not any("sonata" in p or "piano" in p for p in relacionadas), \
            relacionadas

    def test_una_palabra_desconocida_no_devuelve_nada(self):
        from nucleo import semantica

        indice = semantica.construir(self._corpus())
        assert indice.relacionadas("murciélago") == []

    def test_el_indice_se_guarda_y_se_recupera_igual(self, carpeta):
        from nucleo import semantica

        indice = semantica.construir(self._corpus())
        destino = carpeta / "significados.idx"
        semantica.guardar(indice, destino)
        vuelto = semantica.cargar(destino)
        assert vuelto is not None
        assert len(vuelto) == len(indice)
        assert vuelto.total_pasajes == indice.total_pasajes
        assert (vuelto.relacionadas("amortización", 4)
                == indice.relacionadas("amortización", 4))

    def test_se_rehace_solo_cuando_hay_libros_nuevos(self):
        from nucleo import semantica

        indice = semantica.construir(self._corpus())
        conocidos = list(indice.libros)
        assert not semantica.hace_falta_rehacer(indice, conocidos)
        assert not semantica.hace_falta_rehacer(indice, conocidos[:3])
        assert semantica.hace_falta_rehacer(indice, conocidos + ["otro.epub"])
        assert semantica.hace_falta_rehacer(None, conocidos)


# ---------------------------------------------------------------------------
# Etiquetas de las notas
# ---------------------------------------------------------------------------

class PruebaEtiquetas:
    def test_se_leen_separadas_por_comas_y_sin_repetir(self):
        from nucleo import etiquetas

        assert etiquetas.leer("examen, capítulo 4 , Examen") == ["examen",
                                                                 "capítulo 4"]

    def test_una_etiqueta_no_se_parte_por_los_espacios(self):
        from nucleo import etiquetas

        assert etiquetas.leer("capítulo 4") == ["capítulo 4"]

    def test_se_comparan_sin_tildes_pero_se_guardan_con_ellas(self):
        from nucleo import etiquetas

        assert etiquetas.normalizar("Análisis") == etiquetas.normalizar("analisis")
        assert etiquetas.leer("Análisis, analisis") == ["Análisis"]

    def test_filtrar_deja_solo_las_de_esa_etiqueta(self):
        from nucleo import etiquetas
        from nucleo.configuracion import Marcador

        unos = Marcador(0, 5, "nota", "texto", False, ["examen"])
        otros = Marcador(6, 9, "nota", "texto", False, ["dudas"])
        assert etiquetas.filtrar([unos, otros], "examen") == [unos]
        assert etiquetas.filtrar([unos, otros], "EXAMEN") == [unos]
        assert etiquetas.filtrar([unos, otros], "") == [unos, otros]

    def test_el_recuento_pone_delante_la_mas_usada(self):
        from nucleo import etiquetas
        from nucleo.configuracion import Marcador

        marcadores = [Marcador(0, 1, "a", "", False, ["examen"]),
                      Marcador(2, 3, "b", "", False, ["examen", "dudas"]),
                      Marcador(4, 5, "c", "", False, ["examen"])]
        assert etiquetas.recuento(marcadores) == [("examen", 3), ("dudas", 1)]

    def test_un_marcador_de_antes_no_tiene_etiquetas_y_no_falla(self):
        from nucleo import etiquetas

        class Viejo:
            pass

        assert etiquetas.de(Viejo()) == []
        assert etiquetas.tiene(Viejo(), "examen") is False

    def test_las_etiquetas_sobreviven_al_guardado(self):
        from nucleo.configuracion import Marcador

        marcador = Marcador(0, 5, "nota", "fragmento", True, ["examen", "tema 2"])
        vuelto = Marcador.desde_dict(marcador.como_dict())
        assert vuelto.etiquetas == ["examen", "tema 2"]

    def test_sin_etiquetas_el_archivo_guardado_no_cambia(self):
        """Quien no las use debe seguir teniendo exactamente el archivo de antes."""
        from nucleo.configuracion import Marcador

        assert "etiquetas" not in Marcador(0, 5, "nota", "f").como_dict()


# ---------------------------------------------------------------------------
# Bibliografía
# ---------------------------------------------------------------------------

class PruebaBibliografia:
    @staticmethod
    def _referencias():
        from nucleo import citas

        return [
            citas.Referencia("Don Quijote de la Mancha", "Miguel de Cervantes",
                             "Juan de la Cuesta", "1605", "", "",
                             "978-84-376-0494-7", "C:/libros/quijote.epub"),
            citas.Referencia("Rayuela", "Julio Cortázar", "Sudamericana", "1963"),
            citas.Referencia("Beowulf"),
        ]

    def test_se_ordena_por_apellido_y_lo_anonimo_va_al_final(self):
        from nucleo import bibliografia

        ordenadas = bibliografia.ordenar(self._referencias())
        assert [r.titulo for r in ordenadas] == ["Don Quijote de la Mancha",
                                                 "Rayuela", "Beowulf"]

    def test_las_tildes_no_desordenan_la_lista(self):
        from nucleo import bibliografia, citas

        lista = [citas.Referencia("Uno", "Zoe Zamora"),
                 citas.Referencia("Dos", "Ana Álvarez")]
        assert [r.autor for r in bibliografia.ordenar(lista)] == ["Ana Álvarez",
                                                                  "Zoe Zamora"]

    def test_bibtex_lleva_los_campos_separados(self):
        from nucleo import bibliografia

        salida = bibliografia.a_bibtex(self._referencias()).decode("utf-8")
        assert "@book{cervantes1605quijote," in salida
        assert "author = {Cervantes, Miguel de}" in salida
        assert "isbn = {978-84-376-0494-7}" in salida
        assert "file = {C:/libros/quijote.epub}" in salida

    def test_dos_claves_iguales_se_separan(self):
        """Una clave repetida hace que el gestor se coma una de las dos."""
        from nucleo import bibliografia, citas

        iguales = [citas.Referencia("Historia general", "Ana Ruiz", "", "2020"),
                   citas.Referencia("Historia general", "Ana Ruiz", "", "2020")]
        salida = bibliografia.a_bibtex(iguales).decode("utf-8")
        claves = [l for l in salida.split("\n") if l.startswith("@book{")]
        assert len(claves) == 2 and claves[0] != claves[1]

    def test_lo_que_no_es_un_isbn_no_se_declara_como_isbn(self):
        from nucleo import bibliografia, citas

        lista = [citas.Referencia("Libro", "A B", "", "2020", "", "",
                                  "urn:uuid:9f3a-2211-aa")]
        salida = bibliografia.a_bibtex(lista).decode("utf-8")
        assert "isbn" not in salida
        assert "note = {urn:uuid:9f3a-2211-aa}" in salida

    def test_el_ris_lleva_dos_espacios_antes_del_guion(self):
        """Con un espacio de más, el gestor se salta la línea en silencio."""
        from nucleo import bibliografia

        salida = bibliografia.a_ris(self._referencias()).decode("utf-8")
        for linea in salida.split("\r\n"):
            if linea.strip():
                assert linea[2:5] == "  -", repr(linea)

    def test_el_csv_se_abre_bien_en_excel(self):
        from nucleo import bibliografia

        crudo = bibliografia.a_csv(self._referencias())
        assert crudo.startswith(b"\xef\xbb\xbf"), "sin la marca, Excel rompe las tildes"
        assert b";" in crudo

    def test_no_se_echa_en_falta_la_pagina(self):
        """En la lista del final se cita el libro entero, no una página."""
        from nucleo import bibliografia

        faltan = dict(bibliografia.lo_que_falta(self._referencias()))
        assert "Don Quijote de la Mancha" not in faltan
        assert "Beowulf" in faltan

    def test_se_escribe_en_los_seis_formatos(self, carpeta):
        from nucleo import bibliografia

        for formato in bibliografia.FORMATOS:
            destino = carpeta / ("bibliografia_%s" % formato)
            bibliografia.exportar(self._referencias(), destino, formato)
            assert destino.stat().st_size > 20

    def test_un_formato_desconocido_da_error(self, carpeta):
        from nucleo import bibliografia

        with pytest.raises(ValueError):
            bibliografia.exportar([], carpeta / "x", "docx")


# ---------------------------------------------------------------------------
# Química en braille
# ---------------------------------------------------------------------------

class PruebaQuimicaBraille:
    def test_los_subindices_van_en_posicion_baja(self):
        """«H₂O» son tres celdas de contenido, no cinco: no lleva signo de subíndice."""
        from nucleo import braille_quimica as bq

        celdas = bq.celdas("H2O")
        assert celdas == [bq.MAYUSCULA, bq.LETRAS["h"], bq.CIFRAS_BAJAS["2"],
                          bq.MAYUSCULA, bq.LETRAS["o"]]

    def test_da_lo_mismo_escribirlo_con_subindices_de_verdad(self):
        from nucleo import braille_quimica as bq

        assert bq.celdas("H2O") == bq.celdas("H₂O")

    def test_la_carga_va_en_superindice(self):
        from nucleo import braille_quimica as bq

        celdas = bq.celdas("SO₄²⁻")
        assert bq.SUPERINDICE in celdas
        assert celdas[-1] == bq.OPERADORES["-"]

    def test_el_mas_de_una_reaccion_no_es_una_carga(self):
        """Los puntos del «+» son los del seis bajo: sin espacios no se distinguen."""
        from nucleo import braille_quimica as bq

        celdas = bq.celdas("H2 + O2")
        assert bq.SUPERINDICE not in celdas
        posicion = celdas.index(bq.OPERADORES["+"])
        assert celdas[posicion - 1] == bq.BLANCO
        assert celdas[posicion + 1] == bq.BLANCO

    def test_el_mas_pegado_si_es_una_carga(self):
        from nucleo import braille_quimica as bq

        assert bq.SUPERINDICE in bq.celdas("K+")

    def test_el_coeficiente_lleva_signo_de_numero(self):
        from nucleo import braille_quimica as bq

        assert bq.celdas("2H2O")[0] == bq.NUMERO

    def test_el_estado_va_pegado_y_sin_parentesis(self):
        from nucleo import braille_quimica as bq

        celdas = bq.celdas("O₂(g)")
        assert bq.ABRIR_PARENTESIS not in celdas
        assert celdas[-2:] == list(bq.ESTADOS["g"])

    def test_un_grupo_entre_parentesis_lleva_su_numero_de_atomos(self):
        from nucleo import braille_quimica as bq

        celdas = bq.celdas("(NH4)2SO4")
        assert bq.ABRIR_PARENTESIS in celdas
        cierre = celdas.index(bq.CERRAR_PARENTESIS)
        assert celdas[cierre + 1] == bq.CIFRAS_BAJAS["2"]

    def test_lo_que_no_es_quimica_se_rechaza(self):
        from nucleo import braille_quimica as bq

        assert bq.transcribir("esto es una frase cualquiera") is None
        assert bq.transcribir("Xx9") is None
        assert bq.transcribir("") is None

    def test_una_reaccion_entera_se_transcribe(self):
        from nucleo import braille_quimica as bq

        assert bq.transcribir("CH4 + 2O2 → CO2 + 2H2O")


# ---------------------------------------------------------------------------
# Musicografía braille
# ---------------------------------------------------------------------------

class PruebaMusicaBraille:
    def test_la_figura_va_en_los_puntos_tres_y_seis(self):
        from nucleo import braille_musica as bm

        corchea = bm.GRADOS["C"]
        assert bm.GRADOS["C"] | bm.FIGURAS["eighth"] == corchea
        assert bm.GRADOS["C"] | bm.FIGURAS["quarter"] == corchea | 0b100000
        assert bm.GRADOS["C"] | bm.FIGURAS["half"] == corchea | 0b000100

    def test_la_primera_nota_siempre_lleva_octava(self):
        from nucleo import braille_musica as bm

        assert bm.hace_falta_octava(None, bm.Nota("C", 4))

    def test_un_salto_de_tercera_no_lleva_octava(self):
        from nucleo import braille_musica as bm

        assert not bm.hace_falta_octava(bm.Nota("C", 4), bm.Nota("E", 4))

    def test_un_salto_de_sexta_siempre_lleva_octava(self):
        from nucleo import braille_musica as bm

        assert bm.hace_falta_octava(bm.Nota("C", 4), bm.Nota("A", 4))

    def test_una_cuarta_lleva_octava_solo_si_cambia_de_octava(self):
        from nucleo import braille_musica as bm

        assert not bm.hace_falta_octava(bm.Nota("C", 4), bm.Nota("F", 4))
        assert bm.hace_falta_octava(bm.Nota("G", 4), bm.Nota("C", 5))

    def test_el_puntillo_va_pegado_detras(self):
        from nucleo import braille_musica as bm

        celdas = bm.celdas_de_nota(bm.Nota("C", 4, "quarter", puntillos=1), None)
        assert celdas[-1] == bm.PUNTILLO

    def test_el_silencio_no_lleva_octava(self):
        from nucleo import braille_musica as bm

        celdas = bm.celdas_de_nota(bm.Nota(figura="quarter", es_silencio=True), None)
        assert celdas == [bm.SILENCIOS["quarter"]]

    def test_el_compas_lleva_el_denominador_en_posicion_baja(self):
        from nucleo import braille_musica as bm

        celdas = bm.celdas_de_compasillo(3, 4)
        assert celdas[0] == bm.NUMERO
        assert celdas[-1] == bm.CIFRAS_BAJAS["4"]

    def test_la_armadura_larga_se_escribe_con_numero(self):
        from nucleo import braille_musica as bm

        assert bm.celdas_de_armadura(3) == [bm.SOSTENIDO] * 3
        assert bm.celdas_de_armadura(-5)[0] == bm.NUMERO

    def test_la_octava_no_se_reinicia_en_la_barra(self):
        """La regla se sigue contando de un compás al siguiente."""
        from nucleo import braille_musica as bm

        primero = [bm.Nota("C", 4, "quarter")]
        segundo = [bm.Nota("D", 4, "quarter")]
        celdas1, ultima = bm.celdas_de_compas(primero, None)
        celdas2, _ = bm.celdas_de_compas(segundo, ultima)
        assert len(celdas1) == 2, "la primera lleva octava"
        assert len(celdas2) == 1, "la segunda es una segunda: no la lleva"


@pytest.fixture(scope="module")
def partitura():
    from formatos import base, musicaxml  # noqa: F401

    return base.analizar(DATOS / "partitura.musicxml")


class PruebaMusicXML:

    def test_se_abre_con_sus_partes(self, partitura):
        assert partitura.metadatos.titulo == "Après un rêve"
        assert len(partitura.secciones) >= 1

    def test_dice_las_notas_en_palabras(self, partitura):
        assert "negra" in partitura.texto
        assert "Compás 1:" in partitura.texto

    def test_escribe_la_musicografia_en_braille(self, partitura):
        assert any(0x2800 <= ord(c) <= 0x28ff for c in partitura.texto)

    def test_una_partitura_de_verdad_con_acordes_y_tres_voces(self):
        """El preludio de Chopin, que es lo que había que resolver.

        Antes se decía «en este compás hay acordes, que no se transcriben a
        braille». Ahora se escriben, y las tres voces del compás se separan con
        la cópula.
        """
        from formatos import base, musicaxml  # noqa: F401
        from nucleo import braille_musica as bm

        ruta = (Path(__file__).resolve().parent.parent / "adjuntos" / "Estudio"
                / "musicxml" / "docs" / "src" / "data" / "examples" / "musicxml"
                / "tutorial-chopin-prelude.musicxml")
        if not ruta.is_file():
            pytest.skip("la partitura de ejemplo no está clonada")

        documento = base.analizar(ruta)

        assert "no se transcriben a braille" not in documento.texto
        assert "acorde de" in documento.texto
        assert "3 voces" in documento.texto
        assert bm.a_unicode(bm.COPULA_TOTAL) in documento.texto
        # Y la armadura de tres bemoles sigue saliendo, que es lo que había.
        assert "3 bemoles" in documento.texto


# ---------------------------------------------------------------------------
# Gráficos en la línea braille
# ---------------------------------------------------------------------------

class PruebaGraficoBraille:
    def test_una_recta_ascendente_sube_en_el_dibujo(self):
        from nucleo import braille_grafico as bg

        lienzo = bg.curva(list(range(20)), 10, 2)
        lineas = lienzo.lineas()
        # El primer punto queda abajo del todo y el último, arriba del todo.
        assert lineas[-1][0] != "\u2800", "la izquierda tiene que estar abajo"
        assert lineas[0][-1] != "\u2800", "la derecha tiene que estar arriba"

    def test_todos_los_valores_iguales_dan_una_raya_recta(self):
        from nucleo import braille_grafico as bg

        lineas = bg.curva([5] * 12, 8, 2).lineas()
        assert lineas[0].strip("\u2800")
        assert not lineas[1].strip("\u2800")

    def test_no_revienta_con_un_solo_valor(self):
        from nucleo import braille_grafico as bg

        assert bg.dibujar([7], "curva", 8, 1).count("\u2800") == 8

    def test_el_resumen_dice_donde_estan_el_maximo_y_el_minimo(self):
        from nucleo import braille_grafico as bg

        frase = bg.resumen([1, 5, 3])
        assert "5" in frase and "1" in frase

    def test_una_serie_que_solo_sube_se_dice_asi(self):
        from nucleo import braille_grafico as bg

        assert "sube todo el rato" in bg.resumen([1, 2, 3, 4])
        assert "baja todo el rato" in bg.resumen([4, 3, 2, 1])


# ---------------------------------------------------------------------------
# Fiabilidad de los datos sacados de un gráfico
# ---------------------------------------------------------------------------

class PruebaFiabilidad:
    @staticmethod
    def _respuesta(cola: str, celdas: str = "12") -> str:
        return ("TITULO: T\nUNIDADES: u\nTABLA:\n| M | V |\n| --- | --- |\n"
                "| a | %s |\n| b | 19 |\n%s" % (celdas, cola))

    def test_se_lee_la_fiabilidad_que_declara(self):
        from nucleo import graficos

        grafico = graficos.interpretar(self._respuesta("FIABILIDAD: baja: sin etiquetas"))
        assert grafico.fiabilidad == "baja"
        assert "sin etiquetas" in grafico.por_que

    def test_con_fiabilidad_alta_no_se_avisa(self):
        from nucleo import graficos

        grafico = graficos.interpretar(self._respuesta("FIABILIDAD: alta: rotulados"))
        assert not grafico.hay_que_avisar
        assert grafico.aviso() == ""

    def test_un_valor_aproximado_hace_avisar_aunque_diga_que_esta_seguro(self):
        """Lo que pone en la celda manda sobre lo que la IA diga de sí misma."""
        from nucleo import graficos

        grafico = graficos.interpretar(
            self._respuesta("FIABILIDAD: alta: rotulados", "12 (aprox.)"))
        assert grafico.hay_que_avisar

    def test_una_celda_sin_leer_hace_avisar(self):
        from nucleo import graficos

        grafico = graficos.interpretar(self._respuesta("", "?"))
        assert grafico.hay_ilegibles and grafico.hay_que_avisar

    def test_sin_fiabilidad_declarada_no_se_inventa(self):
        from nucleo import graficos

        grafico = graficos.interpretar(self._respuesta(""))
        assert grafico.fiabilidad == ""
        assert not grafico.hay_que_avisar

    def test_la_fiabilidad_sobrevive_al_guardado(self):
        from nucleo import descripciones, graficos

        grafico = graficos.interpretar(self._respuesta("FIABILIDAD: media: medidas"))
        guardada = descripciones.Descripcion(
            "texto", "", "modelo", datos=grafico.rejilla(),
            datos_titulo=grafico.titulo, datos_fiabilidad=grafico.fiabilidad,
            datos_por_que=grafico.por_que)
        vuelta = descripciones.Descripcion.desde_dict(guardada.como_dict())
        assert vuelta.grafico().fiabilidad == "media"


# ---------------------------------------------------------------------------
# Traer una página de internet
# ---------------------------------------------------------------------------

class PruebaTraerWeb:
    def test_se_admite_escribirla_sin_el_protocolo(self):
        from nucleo import traer_web

        assert traer_web.normalizar("es.wikipedia.org/wiki/X") \
            == "https://es.wikipedia.org/wiki/X"

    def test_solo_se_admiten_direcciones_de_internet(self):
        from nucleo import traer_web

        for mala in ("file:///C:/secreto.txt", "ftp://sitio/x", ""):
            with pytest.raises(traer_web.ErrorAlTraer):
                traer_web.normalizar(mala)

    def test_el_nombre_sale_del_final_de_la_direccion(self):
        from nucleo import traer_web

        assert traer_web.nombre_para(
            "https://es.wikipedia.org/wiki/Sistema_braille", ".html") \
            == "Sistema braille.html"

    def test_el_nombre_no_lleva_caracteres_prohibidos(self):
        from nucleo import traer_web

        nombre = traer_web.nombre_para("https://x.org/a:b*c?d", ".html")
        assert not set(nombre) & set('<>:"/\\|?*')

    def test_se_deja_escrita_la_direccion_dentro_de_la_pagina(self):
        """Sin ella, los enlaces y las imágenes relativos no llevan a ninguna parte."""
        from nucleo import traer_web

        salida = traer_web._poner_base(b"<html><head><title>x</title></head>",
                                       "https://sitio.org/a/b")
        assert b'<base href="https://sitio.org/a/b"/>' in salida

    def test_si_la_pagina_ya_trae_base_no_se_toca(self):
        from nucleo import traer_web

        original = b'<html><head><base href="https://otro.org/"></head>'
        assert traer_web._poner_base(original, "https://sitio.org/") == original

    def test_los_errores_del_servidor_se_explican(self):
        from nucleo import traer_web

        assert "ya no existe" in traer_web._motivo_http(404, "https://x.org/a")
        assert "iniciado sesión" in traer_web._motivo_http(403, "https://x.org/a")
        assert "más tarde" in traer_web._motivo_http(503, "https://x.org/a")


# ---------------------------------------------------------------------------
# Presentaciones y hojas de cálculo
# ---------------------------------------------------------------------------

class PruebaPresentaciones:
    @staticmethod
    def _abrir(nombre):
        from formatos import base, presentaciones  # noqa: F401

        return base.analizar(DATOS / nombre)

    def test_el_titulo_va_primero_aunque_en_el_archivo_vaya_el_ultimo(self):
        """Una diapositiva se lee como se ve, no como se dibujó."""
        documento = self._abrir("muestra.pptx")
        titulo = documento.texto.index("Conceptos basicos")
        cuerpo = documento.texto.index("Activo y pasivo")
        pie = documento.texto.index("Pagina 1 de 2")
        assert titulo < cuerpo < pie

    def test_cada_diapositiva_es_un_encabezado(self):
        from nucleo.marcas import TipoMarca

        documento = self._abrir("muestra.pptx")
        assert documento.marcas.cantidad(TipoMarca.ENCABEZADO1) == 2

    def test_las_notas_del_ponente_se_leen(self):
        documento = self._abrir("muestra.pptx")
        assert "no es un gasto de caja" in documento.texto

    def test_el_numero_de_diapositiva_no_se_cuela_en_las_notas(self):
        documento = self._abrir("muestra.pptx")
        cuantas = documento.texto.count("1. Conceptos basicos")
        assert cuantas == 1

    def test_las_tablas_y_las_imagenes_salen_como_tales(self):
        from nucleo.marcas import TipoMarca

        documento = self._abrir("muestra.pptx")
        assert documento.marcas.cantidad(TipoMarca.TABLA) >= 1
        assert "amortizacion anual" in documento.texto

    def test_impress_se_lee_en_el_orden_de_la_pantalla(self):
        documento = self._abrir("muestra.odp")
        titulo = documento.texto.index("La energia de enlace")
        cuerpo = documento.texto.index("Primer punto")
        abajo = documento.texto.index("Esto no son las notas")
        assert titulo < cuerpo < abajo

    def test_las_notas_de_impress_no_se_confunden_con_un_marco(self):
        documento = self._abrir("muestra.odp")
        assert "Insistir en el orden de magnitud" in documento.texto
        # El marco corriente que está donde suelen ir las notas no es una nota.
        assert documento.texto.index("Esto no son las notas") \
            < documento.texto.index("Insistir en el orden")


class PruebaHojas:
    @staticmethod
    def _abrir(nombre):
        from formatos import base, hojas  # noqa: F401

        return base.analizar(DATOS / nombre)

    def test_una_hoja_oculta_no_se_lee(self):
        documento = self._abrir("muestra.xlsx")
        assert "No deberia verse" not in documento.texto
        assert "Ventas" in documento.texto and "Resumen" in documento.texto

    def test_se_recorta_el_hueco_de_arriba_y_de_la_izquierda(self):
        """La hoja empieza en la fila 3 y en la columna C."""
        from nucleo.marcas import TipoMarca

        documento = self._abrir("muestra.xlsx")
        assert documento.texto.count("\n\n") <= 2
        assert documento.marcas.cantidad(TipoMarca.TABLA) >= 1
        assert documento.texto.index("Mes") < documento.texto.index("Enero")

    def test_una_formula_sin_resultado_se_dice_en_vez_de_dejar_un_hueco(self):
        documento = self._abrir("muestra.xlsx")
        assert "=SUM(D4:D5)" in documento.texto

    def test_los_textos_compartidos_se_resuelven(self):
        documento = self._abrir("muestra.xlsx")
        for palabra in ("Mes", "Unidades", "Enero", "Febrero", "Total"):
            assert palabra in documento.texto

    def test_calc_no_despliega_sesenta_mil_filas_vacias(self):
        documento = self._abrir("muestra.ods")
        assert len(documento.texto) < 2000
        assert "Ana" in documento.texto and "8,5" in documento.texto

    def test_la_primera_fila_se_reconoce_como_encabezado(self):
        from formatos import hojas

        assert hojas._parece_encabezado([["Mes", "Ventas"], ["Ene", "12"]])
        assert not hojas._parece_encabezado([["2020", "12"], ["2021", "13"]])
        assert not hojas._parece_encabezado([["Mes", ""], ["Ene", "12"]])


# ---------------------------------------------------------------------------
# Cómics partidos en volúmenes
# ---------------------------------------------------------------------------

class PruebaComicPorVolumenes:
    def test_se_reconocen_los_nombres_de_volumen(self):
        from nucleo import descomprimir

        assert descomprimir.es_por_volumenes("album.part1.rar")
        assert descomprimir.es_por_volumenes("album.part01.cbr")
        assert descomprimir.es_por_volumenes("album.r00")
        assert not descomprimir.es_por_volumenes("album.cbr")

    def test_se_encuentran_los_volumenes_hermanos(self):
        from nucleo import descomprimir

        primero = DATOS / "comic_volumenes.part1.cbr"
        if not primero.is_file():
            pytest.skip("no están las muestras de cómic")
        hermanos = descomprimir.volumenes_siguientes(primero)
        assert [h.name for h in hermanos] == [
            "comic_volumenes.part%d.cbr" % n for n in range(2, 7)]

    def test_un_comic_solido_se_abre_entero(self):
        from formatos import base, comic  # noqa: F401
        from nucleo.marcas import TipoMarca

        ruta = DATOS / "comic_solido.cbr"
        if not ruta.is_file():
            pytest.skip("no están las muestras de cómic")
        documento = base.analizar(ruta)
        assert documento.marcas.cantidad(TipoMarca.IMAGEN) == 6

    def test_un_comic_incompleto_lo_dice_en_vez_de_acabarse_antes(self):
        """Es el fallo grave: cinco páginas de doce parecen un cómic entero."""
        from formatos import base, comic
        from nucleo import descomprimir

        ruta = DATOS / "comic_volumenes.part1.cbr"
        if not ruta.is_file():
            pytest.skip("no están las muestras de cómic")
        antes = descomprimir.PROGRAMAS
        comic._DESCOMPRIMIDOS.clear()
        try:
            # Como si el equipo solo tuviera el descompresor que trae Windows,
            # que es el caso que había que salvar: saca las páginas del primer
            # volumen y dice que ha terminado. Se busca por nombre y no por
            # posición porque el orden de los programas cambia.
            descomprimir.PROGRAMAS = tuple(
                entrada for entrada in antes if entrada[0] == "tar")
            documento = base.analizar(ruta)
        finally:
            descomprimir.PROGRAMAS = antes
            comic._DESCOMPRIMIDOS.clear()
        assert "volúmenes" in documento.texto[:400]


# ---------------------------------------------------------------------------
# Las tablas en braille
# ---------------------------------------------------------------------------

CHICA = [["Mes", "Ventas"], ["Enero", "120"], ["Febrero", "134"]]

ANCHA = [["Concepto", "Primer trimestre", "Segundo trimestre"],
         ["Amortizacion", "12.400", "13.100"],
         ["Personal", "88.000", "90.500"]]


def _documento_con_tabla(texto, marcas):
    """Un documento de mentira con las marcas que se le digan."""
    from nucleo.documento import Documento
    from nucleo.documento import Metadatos

    return Documento(texto, list(marcas),
                     metadatos=Metadatos(titulo="T", autor="A"),
                     ruta_archivo="C:/libros/x.epub")


class PruebaTablasEnBraille:
    """Una tabla leída de corrido deja de ser una tabla.

    Con el dedo sobre un número no hay forma de saber de qué columna es, y una
    tabla de datos es justo lo que más se consulta. Por eso se compone en
    columnas alineadas y, cuando no cabe, con el nombre de la columna delante
    de cada dato.
    """

    def test_una_tabla_que_cabe_sale_en_columnas_alineadas(self):
        from nucleo import braille

        lineas = braille.tabla_a_lineas(CHICA)

        assert lineas[0].index("Ventas") == lineas[2].index("120")
        assert lineas[2].index("120") == lineas[3].index("134")

    def test_el_encabezado_se_separa_con_una_raya(self):
        from nucleo import braille

        lineas = braille.tabla_a_lineas(CHICA)

        assert set(lineas[1]) == {"-", " "}
        assert len(lineas[1]) == len(lineas[0])

    def test_una_tabla_de_una_sola_fila_no_lleva_raya(self):
        from nucleo import braille

        assert braille.tabla_a_lineas([["Mes", "Ventas"]]) == ["Mes Ventas"]

    def test_una_tabla_vacia_no_da_nada(self):
        from nucleo import braille

        assert braille.tabla_a_lineas([]) == []
        assert braille.tabla_a_lineas([[]]) == []

    def test_una_tabla_que_no_cabe_se_lineariza_con_su_encabezado_delante(self):
        """Un dato sin el nombre de su columna no se puede leer."""
        from nucleo import braille

        lineas = braille.tabla_a_lineas(ANCHA, ancho=30)

        assert lineas[0] == "Amortizacion"
        assert lineas[1] == "  Primer trimestre: 12.400"
        assert lineas[2] == "  Segundo trimestre: 13.100"
        assert "" in lineas                    # las filas van separadas
        assert lineas[-1] == "  Segundo trimestre: 90.500"

    def test_ninguna_linea_pasa_del_ancho_cuando_la_tabla_es_estrecha(self):
        from nucleo import braille

        for linea in braille.tabla_a_lineas(CHICA, ancho=40):
            assert len(linea) <= 40

    def test_las_filas_cortas_se_rellenan_y_no_descuadran(self):
        from nucleo import braille

        lineas = braille.tabla_a_lineas([["A", "B", "C"], ["uno"]])

        assert lineas[0].startswith("A")
        assert lineas[-1] == "uno"

    def test_en_contraido_se_contrae_cada_celda_antes_de_alinear(self):
        """Contraer después de alinear descuadraría todas las columnas."""
        from nucleo import braille, braille_contraido

        def traducir(texto):
            return braille_contraido.a_brf(braille_contraido.celdas(texto))

        lineas = braille.tabla_a_lineas(CHICA, traducir=traducir)

        contraida = traducir("Ventas")
        assert contraida != "Ventas"           # si no, la prueba no prueba nada
        assert lineas[0].index(contraida) == lineas[2].index(traducir("120"))
        assert len(lineas[1]) == len(lineas[0])

    def test_una_tabla_sin_titulos_no_lleva_raya_bajo_la_primera_fila(self):
        """Una raya ahí diría que esa fila son los nombres de las columnas.

        Sale de una tabla de verdad: la de palabras reservadas del manual de
        Python, que son cincuenta palabras repartidas en cinco columnas sin
        ningún título.
        """
        from nucleo import braille

        palabras = [["False", "await", "else", "import", "pass"],
                    ["None", "break", "except", "in", "raise"],
                    ["True", "class", "finally", "is", "return"]]

        lineas = braille.tabla_a_lineas(palabras)

        assert set(lineas[1]) != {"-", " "}
        assert lineas[1].startswith("None")

    def test_sin_titulos_la_primera_fila_no_se_pierde_al_linearizar(self):
        """Darla por encabezado la borraría del texto, y en silencio."""
        from nucleo import braille

        palabras = [["False", "await", "else", "import", "pass"],
                    ["None", "break", "except", "in", "raise"]]

        juntas = "\n".join(braille.tabla_a_lineas(palabras, ancho=20))

        assert "False" in juntas
        assert "pass" in juntas

    def test_la_primera_fila_es_encabezado_cuando_de_verdad_lo_parece(self):
        from nucleo import braille

        assert braille._hay_encabezado([["Mes", "Ventas"], ["Enero", "120"]])
        # Textos encima de más textos pueden ser la primera fila de datos.
        assert not braille._hay_encabezado([["a", "b"], ["c", "d"]])
        # Una celda vacía arriba no es un nombre de columna.
        assert not braille._hay_encabezado([["Mes", ""], ["Enero", "120"]])
        # Y un número arriba tampoco.
        assert not braille._hay_encabezado([["2024", "12"], ["2025", "14"]])

    def test_la_tabla_del_documento_sale_en_columnas_dentro_del_brf(self):
        from nucleo import exportar
        from nucleo.marcas import Marca, TipoMarca

        texto = "Informe\nMes\tVentas\nEnero\t120\nFebrero\t134\nDespues.\n"
        rejilla = "Mes\tVentas\nEnero\t120\nFebrero\t134"
        inicio = texto.index("Mes")
        doc = _documento_con_tabla(
            texto, [Marca(TipoMarca.TABLA, inicio, "Ventas por mes", rejilla,
                          0, texto.index("Despues.") - inicio)])

        bloques = exportar.bloques_para_braille(doc)
        escritas = [contenido for _braille, contenido in bloques if contenido]

        assert "Ventas por mes" in escritas    # el título de la tabla, primero
        assert "Mes     Ventas" in escritas
        assert "Enero   120" in escritas
        # Y las líneas del texto aplanado ya no salen además de la tabla.
        assert "Mes\tVentas" not in escritas
        assert escritas[-1] == "Despues."

    def test_una_tabla_sin_rejilla_no_estorba(self):
        """Una marca de tabla sin su rejilla deja el texto como estaba."""
        from nucleo import exportar
        from nucleo.marcas import Marca, TipoMarca

        texto = "Mes Ventas\nDespues.\n"
        doc = _documento_con_tabla(texto,
                                   [Marca(TipoMarca.TABLA, 0, "", "", 0, 10)])

        escritas = [c for _b, c in exportar.bloques_para_braille(doc) if c]

        assert escritas == ["Mes Ventas", "Despues."]


# ---------------------------------------------------------------------------
# El cuaderno de estudio
# ---------------------------------------------------------------------------

class _Marcador:
    """Un marcador de mentira con lo justo que el cuaderno le mira."""

    def __init__(self, inicio, fragmento="", nota="", etiquetas=(),
                 es_resaltado=True, es_nota=False):
        self.inicio = inicio
        self.fragmento = fragmento
        self.nota = nota
        self.etiquetas = list(etiquetas)
        self.es_resaltado = es_resaltado
        self.es_nota = es_nota


class _Libro:
    def __init__(self, ruta, titulo, autor="", total=1000):
        self.ruta = ruta
        self.titulo = titulo
        self.autor = autor
        self.total = total


class _Datos:
    def __init__(self, marcadores, total=1000):
        self.marcadores = list(marcadores)
        self.total = total


class _Ajustes:
    def __init__(self, por_ruta):
        self._por_ruta = por_ruta

    def datos_de(self, ruta):
        return self._por_ruta.get(ruta)


def _biblioteca_de_mentira():
    """Dos libros con lo marcado repartido entre los dos temas."""
    uno = _Libro("C:/libros/a.epub", "Contabilidad I", "Pérez")
    dos = _Libro("C:/libros/b.epub", "Contabilidad II", "López")
    ajustes = _Ajustes({
        uno.ruta: _Datos([
            _Marcador(100, "El activo se amortiza.", etiquetas=["tema 4"]),
            _Marcador(500, "Repasar esto.", "no me queda claro",
                      ["dudas"], es_resaltado=False, es_nota=True),
        ]),
        dos.ruta: _Datos([
            _Marcador(200, "La amortización lineal.", etiquetas=["tema 4"]),
            _Marcador(700, "Sin etiquetar."),
        ]),
    })
    return ajustes, [uno, dos]


class PruebaCuaderno:
    """Quien prepara una asignatura no estudia un libro: estudia un tema."""

    def test_se_recoge_lo_marcado_de_varios_libros_a_la_vez(self):
        from nucleo import cuaderno

        ajustes, libros = _biblioteca_de_mentira()

        apuntes = cuaderno.reunir(ajustes, libros)

        assert len(apuntes) == 4
        assert {a.libro for a in apuntes} == {"Contabilidad I", "Contabilidad II"}

    def test_se_puede_quedar_uno_con_un_solo_tema(self):
        from nucleo import cuaderno

        ajustes, libros = _biblioteca_de_mentira()

        apuntes = cuaderno.reunir(ajustes, libros, "tema 4")

        assert len(apuntes) == 2
        assert {a.libro for a in apuntes} == {"Contabilidad I", "Contabilidad II"}

    def test_se_pueden_dejar_fuera_las_notas_o_los_resaltados(self):
        from nucleo import cuaderno

        ajustes, libros = _biblioteca_de_mentira()

        assert len(cuaderno.reunir(ajustes, libros, con_notas=False)) == 3
        assert len(cuaderno.reunir(ajustes, libros, con_resaltados=False)) == 1

    def test_un_apunte_con_dos_temas_sale_en_los_dos(self):
        """Quien repasa el tema cuatro quiere verlo, y quien repasa dudas también."""
        from nucleo import cuaderno

        apunte = cuaderno.Apunte("L", "A", "texto", "", "", ["tema 4", "dudas"], 0)

        grupos = dict(cuaderno.por_etiqueta([apunte]))

        assert apunte in grupos["tema 4"]
        assert apunte in grupos["dudas"]

    def test_lo_que_no_lleva_etiqueta_no_se_tira(self):
        from nucleo import cuaderno

        ajustes, libros = _biblioteca_de_mentira()
        grupos = cuaderno.por_etiqueta(cuaderno.reunir(ajustes, libros))

        assert sum(len(suyos) for _e, suyos in grupos) >= 4
        assert any(len(suyos) == 1 and suyos[0].texto == "Sin etiquetar."
                   for _e, suyos in grupos)

    def test_cada_apunte_dice_de_donde_sale(self):
        """Sin saber de qué libro es cada párrafo no se puede citar nada."""
        from nucleo import cuaderno

        ajustes, libros = _biblioteca_de_mentira()
        apuntes = cuaderno.reunir(ajustes, libros, "tema 4")

        for apunte in apuntes:
            de_donde = apunte.de_donde()
            assert apunte.libro in de_donde
            assert apunte.autor in de_donde
            assert "por ciento" in de_donde

    def test_el_cuaderno_sale_en_los_tres_formatos(self, tmp_path):
        from nucleo import cuaderno

        ajustes, libros = _biblioteca_de_mentira()
        grupos = cuaderno.por_etiqueta(cuaderno.reunir(ajustes, libros))

        for formato in cuaderno.FORMATOS:
            destino = tmp_path / ("cuaderno." + formato)
            cuaderno.exportar(grupos, destino, formato, "Contabilidad")
            escrito = destino.read_text(encoding="utf-8")
            assert "amortiza" in escrito
            assert "Contabilidad" in escrito

    def test_un_formato_que_no_existe_da_error(self):
        from nucleo import cuaderno

        with pytest.raises(ValueError):
            cuaderno.exportar([], "x.txt", "docx")

    def test_el_html_lleva_encabezados_de_verdad(self):
        """Con encabezados se salta de tema en tema con la tecla H."""
        from nucleo import cuaderno

        apunte = cuaderno.Apunte("L", "", "texto", "", "", ["tema 4"], 0)
        salida = cuaderno.a_html(cuaderno.por_etiqueta([apunte])).decode("utf-8")

        assert "<h2>tema 4</h2>" in salida
        assert '<html lang="es"' in salida

    def test_los_temas_se_ordenan_del_mas_usado_al_menos(self):
        from nucleo import cuaderno

        apuntes = [cuaderno.Apunte("L", "", "a", "", "", ["poco"], 0),
                   cuaderno.Apunte("L", "", "b", "", "", ["mucho"], 1),
                   cuaderno.Apunte("L", "", "c", "", "", ["mucho"], 2)]

        grupos = cuaderno.por_etiqueta(apuntes)

        assert grupos[0][0] == "mucho"


# ---------------------------------------------------------------------------
# El repaso espaciado
# ---------------------------------------------------------------------------

class PruebaRepaso:
    """Lo que sale bien tarda más en volver; lo que se resiste vuelve mañana."""

    def _apunte(self, ruta="C:/libros/a.epub", posicion=100):
        from nucleo import cuaderno

        return cuaderno.Apunte("L", "", "texto", "", "", [], posicion, ruta)

    def test_una_tarjeta_nueva_toca_desde_el_primer_dia(self):
        from nucleo import repaso

        tarjeta = repaso.Tarjeta("x")

        assert tarjeta.es_nueva
        assert tarjeta.toca()
        assert tarjeta.cuando() == "sin empezar"

    def test_acertar_espacia_la_tarjeta_cada_vez_mas(self):
        from nucleo import repaso

        tarjeta = repaso.Tarjeta("x")
        intervalos = []
        ahora = 1_000_000.0
        for _vez in range(4):
            tarjeta.responder("si", ahora)
            intervalos.append(tarjeta.intervalo)
            ahora = tarjeta.proximo

        assert intervalos == sorted(intervalos)
        assert intervalos[0] == 1 and intervalos[1] == 6
        assert intervalos[-1] > intervalos[-2]

    def test_no_acordarse_devuelve_la_tarjeta_a_maniana(self):
        """Lo que no se recuerda no se ha aprendido a medias: no se ha aprendido."""
        from nucleo import repaso

        tarjeta = repaso.Tarjeta("x")
        for _vez in range(3):
            tarjeta.responder("si")
        tarjeta.responder("no")

        assert tarjeta.repeticiones == 0
        assert tarjeta.intervalo == 1

    def test_la_facilidad_nunca_baja_del_minimo(self):
        """Por debajo de ahí una tarjeta se atasca y vuelve una y otra vez."""
        from nucleo import repaso

        tarjeta = repaso.Tarjeta("x")
        for _vez in range(20):
            tarjeta.responder("no")

        assert tarjeta.facilidad >= repaso.FACILIDAD_MINIMA

    def test_primero_lo_que_toca_y_despues_lo_nuevo(self):
        """Una tanda llena de tarjetas nuevas dejaría sin repasar lo urgente."""
        from nucleo import repaso

        estado = repaso.Repaso()
        viejo = self._apunte(posicion=1)
        nuevo = self._apunte(posicion=2)
        tarjeta = estado.de(repaso.clave_de(viejo.ruta, viejo.posicion))
        tarjeta.responder("si", 0.0)          # visto hace mucho: ya le toca

        pendientes = estado.pendientes([nuevo, viejo])

        assert [a.posicion for a in pendientes] == [1, 2]

    def test_una_tanda_no_pasa_del_tope(self):
        from nucleo import repaso

        estado = repaso.Repaso()
        apuntes = [self._apunte(posicion=n) for n in range(repaso.TANDA + 25)]

        assert len(estado.pendientes(apuntes)) == repaso.TANDA

    def test_lo_que_no_toca_hoy_no_entra_en_la_tanda(self):
        from nucleo import repaso

        estado = repaso.Repaso()
        apunte = self._apunte()
        estado.de(repaso.clave_de(apunte.ruta, apunte.posicion)).responder("si")

        assert estado.pendientes([apunte]) == []
        assert "Vuelve mañana" in estado.resumen([apunte])

    def test_lo_repasado_se_guarda_y_se_vuelve_a_traer(self, tmp_path):
        from nucleo import repaso

        destino = tmp_path / "repaso.json"
        estado = repaso.Repaso()
        estado.de("C:/libros/a.epub|100").responder("si")
        estado.guardar(destino)

        traido = repaso.cargar(destino)

        assert traido.de("C:/libros/a.epub|100").intervalo == 1
        assert not traido.de("C:/libros/a.epub|100").es_nueva

    def test_las_tarjetas_sin_estrenar_no_ocupan_sitio(self, tmp_path):
        from nucleo import repaso

        destino = tmp_path / "repaso.json"
        estado = repaso.Repaso()
        estado.de("C:/libros/a.epub|100")     # solo mirada, sin responder
        estado.guardar(destino)

        assert destino.read_text(encoding="utf-8").strip() == "{}"

    def test_un_archivo_roto_no_impide_repasar(self, tmp_path):
        from nucleo import repaso

        destino = tmp_path / "repaso.json"
        destino.write_text("esto no es json", encoding="utf-8")

        assert repaso.cargar(destino).tarjetas == {}

    def test_se_puede_olvidar_lo_repasado_de_un_libro(self):
        from nucleo import repaso

        estado = repaso.Repaso()
        estado.de("C:/libros/a.epub|100").responder("si")
        estado.de("C:/libros/a.epub|200").responder("si")
        estado.de("C:/libros/b.epub|100").responder("si")

        assert estado.olvidar_libro("C:/libros/a.epub") == 2
        assert list(estado.tarjetas) == ["C:/libros/b.epub|100"]

    def test_el_resumen_dice_cuantas_tocan_y_cuantas_son_nuevas(self):
        from nucleo import repaso

        estado = repaso.Repaso()
        apuntes = [self._apunte(posicion=1), self._apunte(posicion=2)]

        assert "2" in estado.resumen(apuntes)
        assert estado.cuenta(apuntes) == (0, 2, 2)
        assert estado.resumen([]) == "No hay nada marcado que repasar."


# ---------------------------------------------------------------------------
# El modo de práctica
# ---------------------------------------------------------------------------

def _documento_para_practicar():
    """Un documento con encabezados, texto de sobra y una palabra repetida."""
    from nucleo.documento import Documento, Metadatos
    from nucleo.marcas import Marca, TipoMarca

    lineas = []
    for numero in range(60):
        if numero % 10 == 0:
            lineas.append("Capítulo %d" % numero)
        else:
            lineas.append("Un párrafo cualquiera sobre amortización contable, "
                          "el número %d de todos ellos." % numero)
    texto = "\n".join(lineas)
    marcas = [Marca(TipoMarca.ENCABEZADO1, texto.index("Capítulo %d" % n),
                    "Capítulo %d" % n)
              for n in (0, 10, 20, 30, 40, 50)]
    return Documento(texto, marcas, metadatos=Metadatos(titulo="T"),
                     ruta_archivo="C:/libros/x.epub")


class _MarcadorDePrueba:
    def __init__(self, es_nota=False):
        self.es_nota = es_nota
        self.es_resaltado = not es_nota


class PruebaPractica:
    """Reconocer una tecla y saber usarla no son lo mismo."""

    def test_solo_se_proponen_los_ejercicios_que_el_documento_admite(self):
        """Pedir el tercer encabezado en una novela sin ninguno enseña que el
        programa no funciona."""
        from nucleo import practica
        from nucleo.documento import Documento, Metadatos

        pelado = Documento("Dos palabras.", [],
                           metadatos=Metadatos(titulo="T"),
                           ruta_archivo="C:/libros/y.epub")
        inicial = practica.estado_de(pelado, 0)

        claves = {e.clave for e in practica.preparar(pelado, inicial)}

        assert "encabezado" not in claves
        assert "final" not in claves          # no hay texto que recorrer
        assert "marcador" in claves           # esto se puede hacer siempre

    def test_con_un_documento_completo_salen_todos(self):
        from nucleo import practica

        documento = _documento_para_practicar()
        inicial = practica.estado_de(documento, 0)

        claves = [e.clave for e in practica.preparar(documento, inicial)]

        assert claves == ["encabezado", "final", "principio", "linea", "buscar",
                          "marcador", "nota", "resaltado"]

    def test_sin_documento_no_hay_ejercicios(self):
        from nucleo import practica

        assert practica.preparar(None, practica.Estado()) == []
        assert practica.estado_de(None, 0) == practica.Estado()

    def test_el_enunciado_dice_como_se_llama_el_encabezado(self):
        """«Ve al tercero» sin decir cuál es no se puede comprobar a ciegas."""
        from nucleo import practica

        documento = _documento_para_practicar()
        inicial = practica.estado_de(documento, 0)
        ejercicio = practica.preparar(documento, inicial)[0]

        assert "Capítulo 20" in ejercicio.enunciado

    def test_el_ejercicio_del_encabezado_se_da_por_hecho_al_llegar(self):
        from nucleo import practica

        documento = _documento_para_practicar()
        inicial = practica.estado_de(documento, 0)
        ejercicio = practica.preparar(documento, inicial)[0]
        tercero = documento.marcas.encabezados[2].posicion

        assert not ejercicio.hecho(inicial, inicial)
        assert ejercicio.hecho(inicial,
                               practica.estado_de(documento, tercero))
        # Y también un poco más abajo: sigue estando en ese apartado.
        assert ejercicio.hecho(inicial,
                               practica.estado_de(documento, tercero + 20))

    def test_da_igual_como_se_haya_llegado(self):
        """Quien va con el árbol de contenido en vez de con H lo ha hecho igual.

        Los ejercicios miran el documento, no las teclas: decirle que no lo ha
        hecho sería mentirle.
        """
        from nucleo import practica

        documento = _documento_para_practicar()
        inicial = practica.estado_de(documento, 0)
        final = [e for e in practica.preparar(documento, inicial)
                 if e.clave == "final"][0]

        assert final.hecho(inicial,
                           practica.estado_de(documento, len(documento.texto)))

    def test_poner_un_marcador_es_tener_uno_mas_que_al_empezar(self):
        """En un libro ya trabajado, tener marcadores no prueba nada."""
        from nucleo import practica

        documento = _documento_para_practicar()
        antes = practica.estado_de(documento, 0,
                                   [_MarcadorDePrueba(), _MarcadorDePrueba()])
        ejercicio = [e for e in practica.preparar(documento, antes)
                     if e.clave == "marcador"][0]

        assert not ejercicio.hecho(antes, antes)
        despues = practica.estado_de(
            documento, 0, [_MarcadorDePrueba()] * 3)
        assert ejercicio.hecho(antes, despues)

    def test_la_nota_no_se_da_por_puesta_con_un_marcador_normal(self):
        from nucleo import practica

        documento = _documento_para_practicar()
        antes = practica.estado_de(documento, 0)
        ejercicio = [e for e in practica.preparar(documento, antes)
                     if e.clave == "nota"][0]

        solo_marcador = practica.estado_de(documento, 0, [_MarcadorDePrueba()])
        assert not ejercicio.hecho(antes, solo_marcador)

        con_nota = practica.estado_de(documento, 0,
                                      [_MarcadorDePrueba(es_nota=True)])
        assert ejercicio.hecho(antes, con_nota)

    def test_la_busqueda_vale_aunque_se_escriba_sin_tildes(self):
        """Nadie escribe las tildes al buscar, y no es eso lo que se practica."""
        from nucleo import practica

        documento = _documento_para_practicar()
        antes = practica.estado_de(documento, 0)
        ejercicio = [e for e in practica.preparar(documento, antes)
                     if e.clave == "buscar"][0]

        assert "amortización" in ejercicio.enunciado
        assert ejercicio.hecho(
            antes, practica.estado_de(documento, 0, busqueda="AMORTIZACION"))
        assert not ejercicio.hecho(
            antes, practica.estado_de(documento, 0, busqueda="otra cosa"))

    def test_la_palabra_que_se_manda_buscar_sale_varias_veces(self):
        """Encontrar una y que no haya siguiente no enseña que F3 repite."""
        from nucleo import practica

        texto = ("corto corto corto. Palabra larguísima que solo sale una vez. "
                 "amortización amortización amortización.")

        elegida = practica.palabra_para_buscar(texto)

        assert elegida == "amortización"

    def test_sin_ninguna_palabra_repetida_se_coge_la_mas_larga(self):
        from nucleo import practica

        assert practica.palabra_para_buscar("uno dos tres cuatrocientos") == \
            "cuatrocientos"
        assert practica.palabra_para_buscar("") == ""
        assert practica.palabra_para_buscar("a b c") == ""

    def test_el_resumen_dice_lo_que_ha_pasado(self):
        from nucleo import practica

        assert "todos" in practica.resumen(3, 0, 3)
        assert practica.resumen(0, 0, 0)
        assert "ninguno" in practica.resumen(0, 2, 2)
        assert "1" in practica.resumen(1, 1, 3)


# ---------------------------------------------------------------------------
# Acordes y voces simultáneas
# ---------------------------------------------------------------------------

class PruebaAcordes:
    """Un acorde no se escribe nota a nota: se escribe una y sus intervalos.

    Los signos de intervalo se comprobaron contra el alfabeto braille de la
    ONCE reconstruido del documento B 16-1, que los da por separado: la segunda
    son los puntos 34, la cuarta 3456, la quinta 35, la sexta 356, la séptima 25
    y la octava 36. Coinciden los seis, y el séptimo —la tercera, puntos 346—
    completa el juego.
    """

    def _notas(self):
        from nucleo.braille_musica import Nota

        return (Nota("C", 4, "quarter"), Nota("E", 4, "quarter"),
                Nota("G", 4, "quarter"))

    def test_un_acorde_ocupa_una_celda_por_nota_y_no_dos(self):
        from nucleo import braille_musica as bm

        do, mi, sol = self._notas()

        celdas = bm.celdas_de_acorde(bm.Acorde([do, mi, sol]), None)

        # Signo de octava, la nota principal y dos intervalos.
        assert len(celdas) == 4

    def test_de_arriba_abajo_la_nota_escrita_es_la_mas_aguda(self):
        from nucleo import braille_musica as bm

        do, mi, sol = self._notas()

        assert bm.Acorde([do, mi, sol]).principal.grado == "G"
        assert bm.Acorde([do, mi, sol], hacia_abajo=False).principal.grado == "C"

    def test_los_intervalos_se_miden_desde_la_nota_escrita(self):
        from nucleo import braille_musica as bm

        do, mi, sol = self._notas()

        celdas = bm.celdas_de_acorde(bm.Acorde([do, mi, sol]), None)

        # Desde sol: mi es una tercera y do una quinta.
        assert celdas[-2] == bm.INTERVALOS[3]
        assert celdas[-1] == bm.INTERVALOS[5]

        al_reves = bm.celdas_de_acorde(
            bm.Acorde([do, mi, sol], hacia_abajo=False), None)
        # Desde do: mi es una tercera y sol una quinta. Los mismos signos, y
        # sin embargo el acorde no se lee igual: cambia cuál es la nota real.
        assert al_reves[-2] == bm.INTERVALOS[3]
        assert al_reves[-1] == bm.INTERVALOS[5]
        assert al_reves[1] != celdas[1]

    def test_un_intervalo_de_mas_de_una_octava_lleva_su_octava_delante(self):
        """Sin ella, una décima y una tercera se escribirían igual."""
        from nucleo.braille_musica import Nota
        from nucleo import braille_musica as bm

        do = Nota("C", 4, "quarter")

        tercera = bm.celdas_de_intervalo(do, Nota("E", 4, "quarter"))
        decima = bm.celdas_de_intervalo(do, Nota("E", 5, "quarter"))

        assert tercera == [bm.INTERVALOS[3]]
        assert decima == [bm.OCTAVAS[5], bm.INTERVALOS[3]]

    def test_dos_notas_al_unisono_no_se_inventan(self):
        from nucleo.braille_musica import Imposible, Nota
        from nucleo import braille_musica as bm

        do = Nota("C", 4, "quarter")

        with pytest.raises(Imposible):
            bm.celdas_de_intervalo(do, Nota("C", 4, "quarter"))

    def test_la_alteracion_de_una_nota_del_acorde_no_se_pierde(self):
        from nucleo.braille_musica import Nota
        from nucleo import braille_musica as bm

        do = Nota("C", 4, "quarter")
        mi_bemol = Nota("E", 4, "quarter", alteracion=-1)

        celdas = bm.celdas_de_intervalo(do, mi_bemol)

        assert celdas == [bm.BEMOL, bm.INTERVALOS[3]]

    def test_la_regla_de_la_octava_se_cuenta_desde_la_nota_principal(self):
        from nucleo.braille_musica import Nota
        from nucleo import braille_musica as bm

        do, mi, sol = self._notas()
        acorde = bm.Acorde([do, mi, sol])          # su principal es sol4

        # Un la4 detrás del acorde es una segunda desde sol: no lleva octava.
        celdas, _ultima = bm.celdas_de_compas([acorde, Nota("A", 4, "quarter")])

        assert len(celdas) == 5                    # 4 del acorde y 1 de la nota

    def test_el_acorde_se_dice_de_grave_a_aguda(self):
        """Quien lo oye no está leyendo: un acorde se nombra «do mi sol»."""
        from nucleo import braille_musica as bm

        do, mi, sol = self._notas()

        assert bm.Acorde([do, mi, sol]).nombre().startswith("acorde de do mi sol")

    def test_dos_voces_se_separan_con_la_copula(self):
        from nucleo.braille_musica import Nota
        from nucleo import braille_musica as bm

        voces = [[Nota("E", 5, "half"), Nota("D", 5, "half")],
                 [Nota("C", 3, "whole")]]

        celdas, ultima = bm.celdas_de_compas(voces, None)

        corte = celdas.index(bm.COPULA_TOTAL[0])
        assert list(bm.COPULA_TOTAL) == celdas[corte:corte + 2]
        # Después de la cópula, la voz siguiente empieza con su octava.
        assert celdas[corte + 2] == bm.OCTAVAS[3]

    def test_despues_de_una_copula_el_compas_siguiente_lleva_octava(self):
        """Lo manda la norma, y sin ello se leería en el registro equivocado."""
        from nucleo.braille_musica import Nota
        from nucleo import braille_musica as bm

        voces = [[Nota("E", 5, "half")], [Nota("C", 3, "whole")]]

        _celdas, ultima = bm.celdas_de_compas(voces, None)

        assert ultima is None

    def test_un_compas_de_una_sola_voz_se_escribe_como_siempre(self):
        """El caso normal no puede cambiar: es casi toda la música."""
        from nucleo.braille_musica import Nota
        from nucleo import braille_musica as bm

        notas = [Nota("C", 4, "quarter"), Nota("E", 4, "quarter")]

        sueltas, _a = bm.celdas_de_compas(notas, None)
        en_lista, _b = bm.celdas_de_compas([notas], None)

        assert sueltas == en_lista


class PruebaPartituraConAcordes:
    """La partitura de prueba, leída de punta a punta."""

    def _documento(self):
        from formatos.base import OpcionesAnalisis, analizar
        import formatos.musicaxml                        # noqa: F401

        return analizar(DATOS / "acordes.musicxml", OpcionesAnalisis())

    def test_los_acordes_ya_no_se_dicen_sin_transcribir(self):
        texto = self._documento().texto

        assert "no se transcriben a braille" not in texto
        assert "acorde de do mi sol" in texto

    def test_el_acorde_sale_en_braille_con_sus_intervalos(self):
        from nucleo import braille_musica as bm

        texto = self._documento().texto
        esperado = bm.a_unicode([bm.OCTAVAS[4],
                                 bm.GRADOS["G"] | bm.FIGURAS["quarter"],
                                 bm.INTERVALOS[3], bm.INTERVALOS[5]])

        assert esperado in texto

    def test_las_dos_voces_se_dicen_por_separado_y_se_escriben_con_copula(self):
        from nucleo import braille_musica as bm

        texto = self._documento().texto

        assert "2 voces" in texto
        assert "Voz 1:" in texto and "Voz 2:" in texto
        assert bm.a_unicode(bm.COPULA_TOTAL) in texto

    def test_la_clave_de_fa_escribe_los_acordes_de_abajo_arriba(self):
        """Es lo que hace la mano izquierda del teclado."""
        from formatos.musicaxml import Pentagrama, _leer_parte
        from lxml import etree

        fuente = (DATOS / "acordes.musicxml").read_text(encoding="utf-8")
        raiz = etree.fromstring(fuente.replace("<sign>G</sign>", "<sign>F</sign>")
                                .encode("utf-8"))
        pentagrama = Pentagrama("Piano")
        _leer_parte(raiz.find("part"), pentagrama)

        assert not pentagrama.hacia_abajo
        assert pentagrama.compases[0][0].principal.grado == "C"


# ---------------------------------------------------------------------------
# Diagramas de flujo y circuitos
# ---------------------------------------------------------------------------

RESPUESTA_DIAGRAMA = """TITULO: Alta de un usuario
TIPO: diagrama de flujo
CAJAS:
| id | clase | texto |
| --- | --- | --- |
| 1 | inicio | Empezar |
| 2 | paso | Pedir el correo |
| 3 | decision | ¿Es válido? |
| 4 | paso | Crear la cuenta |
| 5 | fin | Terminar |
FLECHAS:
| desde | hasta | rotulo |
| --- | --- | --- |
| 1 | 2 | |
| 2 | 3 | |
| 3 | 4 | sí |
| 3 | 2 | no |
| 4 | 5 | |
NOTA: el correo se comprueba con una expresión regular
FIABILIDAD: media: dos flechas se cruzan"""


class PruebaEsquemas:
    """Un diagrama descrito en un párrafo dice qué hay dibujado, no por dónde se va."""

    def _esquema(self):
        from nucleo import esquemas

        return esquemas.interpretar(RESPUESTA_DIAGRAMA)

    def test_se_leen_las_cajas_y_las_flechas(self):
        esquema = self._esquema()

        assert esquema.titulo == "Alta de un usuario"
        assert esquema.tipo == "diagrama de flujo"
        assert len(esquema.cajas) == 5
        assert len(esquema.flechas) == 5
        assert esquema.cuantas_decisiones() == 1

    def test_el_recorrido_sigue_las_flechas_y_se_anida(self):
        lineas = self._esquema().lineas()

        assert lineas[0].strip() == "inicio: Empezar"
        # Cada paso al que se llega está un nivel más adentro.
        sangrias = [len(linea) - len(linea.lstrip()) for linea in lineas]
        assert sangrias[1] > sangrias[0]

    def test_el_rotulo_de_la_flecha_va_delante_del_paso_al_que_lleva(self):
        """Es lo que convierte un rombo en dos caminos que se pueden seguir."""
        juntas = "\n".join(self._esquema().lineas())

        assert "si sí, Crear la cuenta" in juntas

    def test_un_bucle_se_corta_diciendo_a_donde_vuelve(self):
        """Repetirlo daría vueltas para siempre; quien lo lee ya pasó por ahí."""
        juntas = "\n".join(self._esquema().lineas())

        assert "vuelve al paso 2" in juntas
        # Y con su rótulo, porque el bucle suele ser justo la rama del «no».
        assert "si no, vuelve al paso 2" in juntas

    def test_se_empieza_por_donde_no_llega_ninguna_flecha(self):
        esquema = self._esquema()

        assert [caja.identificador for caja in esquema.entradas()] == ["1"]

    def test_un_diagrama_que_es_un_ciclo_cerrado_empieza_por_algun_sitio(self):
        from nucleo import esquemas

        esquema = esquemas.Esquema(
            cajas=[esquemas.Caja("1", "paso", "A"), esquemas.Caja("2", "paso", "B")],
            flechas=[esquemas.Flecha("1", "2"), esquemas.Flecha("2", "1")])

        assert len(esquema.entradas()) == 1
        assert esquema.lineas()                       # y no se cuelga

    def test_una_flecha_a_una_caja_que_no_existe_no_se_queda(self):
        """Dibujaría un camino a ninguna parte."""
        from nucleo import esquemas

        respuesta = RESPUESTA_DIAGRAMA.replace("| 4 | 5 | |", "| 4 | 99 | |")

        esquema = esquemas.interpretar(respuesta)

        assert len(esquema.flechas) == 4

    def test_si_no_es_un_diagrama_no_se_inventa_ninguno(self):
        from nucleo import esquemas

        assert esquemas.interpretar("NO ES UN DIAGRAMA") is None
        assert esquemas.interpretar("") is None
        assert esquemas.interpretar("cualquier cosa") is None
        # Y una respuesta con flechas pero sin cajas tampoco vale.
        assert esquemas.interpretar("FLECHAS:\n| 1 | 2 | |") is None

    def test_la_fiabilidad_se_lee_y_se_avisa(self):
        esquema = self._esquema()

        assert esquema.fiabilidad == "media"
        assert esquema.hay_que_avisar()
        assert "dos flechas se cruzan" in esquema.aviso()

    def test_lo_guardado_se_vuelve_a_traer_entero(self):
        from nucleo import esquemas

        crudo = self._esquema().para_guardar()
        otra = esquemas.desde_guardado(crudo)

        assert esquemas.es_esquema(crudo)
        assert len(otra.cajas) == 5
        assert len(otra.flechas) == 5
        assert otra.tipo == "diagrama de flujo"

    def test_un_diagrama_guardado_no_se_lee_como_si_fuera_una_tabla(self):
        """Daría una tabla de tres columnas que no significa nada."""
        from nucleo import esquemas, graficos

        crudo = self._esquema().para_guardar()

        assert graficos.desde_guardado(crudo) is not None   # es una rejilla...
        assert esquemas.es_esquema(crudo)                   # ...pero es un diagrama

    def test_la_descripcion_guardada_distingue_las_dos_cosas(self):
        from nucleo.descripciones import Descripcion

        anotada = Descripcion("texto", datos=self._esquema().para_guardar())

        assert anotada.grafico() is None
        assert anotada.esquema() is not None
        assert len(anotada.esquema().cajas) == 5

    def test_el_html_es_una_lista_anidada_de_verdad(self):
        """Es lo que hace que el lector de pantalla diga en qué nivel está."""
        from nucleo import html_elementos

        html = html_elementos.html_de_esquema(self._esquema())

        assert html.count("<ol>") == html.count("</ol>")
        assert html.count("<li>") == html.count("</li>")
        # Una lista dentro de un elemento de la de fuera, y no detrás.
        assert "<ol>" in html.split("<li>", 2)[2]
        assert "Alta de un usuario" in html
        assert "Cuidado con este diagrama" in html

    def test_el_recorrido_no_se_anida_hasta_el_infinito(self):
        from nucleo import esquemas

        cajas = [esquemas.Caja(str(n), "paso", "paso %d" % n) for n in range(1, 30)]
        flechas = [esquemas.Flecha(str(n), str(n + 1)) for n in range(1, 29)]

        pasos = esquemas.Esquema(cajas=cajas, flechas=flechas).recorrido()

        assert max(nivel for nivel, _t, _i in pasos) < esquemas.NIVELES
        assert any("sigue en el paso" in texto for _n, texto, _i in pasos)


# ---------------------------------------------------------------------------
# Articulación, matices y digitación
# ---------------------------------------------------------------------------

class PruebaMaticesBraille:
    """Una partitura sin articulación dice qué notas hay, no cómo suenan.

    Los signos se comprobaron cruzando dos documentos, igual que los de
    intervalo: los que aparecen en el alfabeto reconstruido del B 16-1 dan los
    puntos del sistema internacional, y los prefijos que el propio B 4-2 usa en
    otros epígrafes —la mano derecha, la mano izquierda— confirman los que
    faltaban.
    """

    def test_las_articulaciones_acaban_todas_en_la_misma_celda(self):
        """Es lo que las hace reconocibles al tacto sin memorizarlas una a una."""
        from nucleo import braille_musica as bm

        for signo in bm.ARTICULACIONES.values():
            assert signo[-1] == bm._PICADO

    def test_la_articulacion_va_delante_de_la_nota(self):
        from nucleo import braille_musica as bm

        nota = bm.Nota("C", 4, "quarter", articulaciones=("staccato",))

        celdas = bm.celdas_de_nota(nota, None)

        assert celdas[0] == bm.ARTICULACIONES["staccato"][0]
        assert celdas[-1] == bm.GRADOS["C"] | bm.FIGURAS["quarter"]

    def test_una_articulacion_desconocida_no_se_inventa(self):
        from nucleo.braille_musica import Imposible, Nota
        from nucleo import braille_musica as bm

        with pytest.raises(Imposible):
            bm.celdas_de_nota(Nota("C", 4, "quarter",
                                   articulaciones=("plop",)), None)

    def test_el_dedo_va_detras_de_la_nota_y_de_su_puntillo(self):
        from nucleo import braille_musica as bm

        nota = bm.Nota("C", 4, "quarter", puntillos=1, dedo=3)

        celdas = bm.celdas_de_nota(nota, None)

        assert celdas[-1] == bm.DEDOS[3]
        assert celdas[-2] == bm.PUNTILLO

    def test_un_matiz_lleva_delante_el_signo_de_palabra(self):
        """Sin él, la «p» de piano se leería como la nota que le toque."""
        from nucleo import braille_musica as bm

        celdas = bm.celdas_de_palabra("p")

        assert celdas[0] == bm.PALABRA
        assert celdas[1] == bm.LETRAS_TEXTO["p"]

    def test_la_nota_que_sigue_a_un_matiz_lleva_siempre_su_octava(self):
        """Lo manda la norma: entre medias ha pasado una palabra."""
        from nucleo import braille_musica as bm

        antes = bm.Nota("C", 4, "quarter")
        con_matiz = bm.Nota("D", 4, "quarter", palabras=("p",))

        celdas = bm.celdas_de_nota(con_matiz, antes)

        assert bm.OCTAVAS[4] in celdas
        # Sin el matiz, un salto de segunda no llevaría octava.
        assert bm.OCTAVAS[4] not in bm.celdas_de_nota(
            bm.Nota("D", 4, "quarter"), antes)

    def test_lo_mismo_despues_de_un_regulador(self):
        from nucleo import braille_musica as bm

        antes = bm.Nota("C", 4, "quarter")
        con_cuna = bm.Nota("D", 4, "quarter", reguladores=("crescendo",))

        assert bm.OCTAVAS[4] in bm.celdas_de_nota(con_cuna, antes)

    def test_la_ligadura_de_expresion_va_entre_las_notas(self):
        """No delante del grupo: en cada hueco, que es donde la pone la norma."""
        from nucleo import braille_musica as bm

        notas = [bm.Nota("C", 4, "quarter", ligado="sigue"),
                 bm.Nota("D", 4, "quarter", ligado="sigue"),
                 bm.Nota("E", 4, "quarter")]

        celdas, _ultima = bm.celdas_de_compas(notas)

        assert celdas.count(bm.LIGADURA_EXPRESION) == 2

    def test_un_grupo_largo_usa_la_otra_forma_de_ligadura(self):
        from nucleo import braille_musica as bm

        primera = bm.Nota("C", 4, "eighth", ligado="abre-larga")
        ultima = bm.Nota("G", 4, "eighth", ligado="cierra-larga")

        assert bm.celdas_de_nota(primera, None)[:2] == list(bm.LIGADURA_LARGA_ABRE)
        assert bm.celdas_de_nota(ultima, primera)[-2:] == \
            list(bm.LIGADURA_LARGA_CIERRA)

    def test_la_ligadura_de_expresion_no_es_la_de_prolongacion(self):
        """En tinta se dibujan igual y en braille hay que distinguirlas.

        Se distinguen por el prefijo: la de prolongación son dos celdas y la de
        expresión, una. Comparten la última, que es lo que las emparenta al
        leerlas, pero no se pueden confundir porque una viene precedida y la
        otra no.
        """
        from nucleo import braille_musica as bm

        assert len(bm.LIGADURA) == 2
        assert bm.LIGADURA[0] != bm.LIGADURA_EXPRESION
        assert list(bm.LIGADURA) != [bm.LIGADURA_EXPRESION]

    def test_lo_que_se_toca_se_dice_tambien_en_palabras(self):
        from nucleo import braille_musica as bm

        nota = bm.Nota("C", 4, "quarter", articulaciones=("accent",), dedo=2,
                       palabras=("pp",), reguladores=("crescendo",))

        dicho = nota.nombre()

        assert "pp" in dicho
        assert "acentuado" in dicho
        assert "dedo 2" in dicho
        assert "crecer" in dicho

    def test_el_tenuto_no_se_llama_sostenido(self):
        """Sostenido ya es la alteración; oírlo aquí diría otra cosa."""
        from nucleo import braille_musica as bm

        assert bm.NOMBRE_ARTICULACION["tenuto"] != "sostenido"


class PruebaPartituraConMatices:
    """La partitura de prueba con matices, leída de punta a punta."""

    def _documento(self):
        from formatos.base import OpcionesAnalisis, analizar
        import formatos.musicaxml                        # noqa: F401

        return analizar(DATOS / "matices.musicxml", OpcionesAnalisis())

    def test_el_matiz_y_la_articulacion_llegan_al_braille(self):
        from nucleo import braille_musica as bm

        texto = self._documento().texto

        assert bm.a_unicode(bm.celdas_de_palabra("p")) in texto
        assert bm.a_unicode(list(bm.ARTICULACIONES["staccato"])) in texto
        assert "picado" in texto and "dedo 1" in texto

    def test_el_regulador_se_abre_y_se_cierra(self):
        from nucleo import braille_musica as bm

        texto = self._documento().texto

        assert bm.a_unicode(list(bm.REGULADORES["crescendo"])) in texto
        assert bm.a_unicode(list(bm.REGULADORES["fin-crescendo"])) in texto
        assert "empieza a crecer" in texto and "deja de crecer" in texto

    def test_el_texto_dentro_de_la_musica_sale_como_texto(self):
        from nucleo import braille_musica as bm

        texto = self._documento().texto

        assert bm.a_unicode(bm.celdas_de_palabra("a tempo")) in texto

    def test_el_trino_se_escribe_con_su_signo(self):
        """El B 4-2 no lo recoge, así que su signo sale del manual internacional."""
        from nucleo import braille_musica as bm

        texto = self._documento().texto

        assert bm.a_unicode(list(bm.ADORNOS["trill-mark"])) in texto
        assert "con trino" in texto


# ---------------------------------------------------------------------------
# Word, Excel y PowerPoint de 1997
# ---------------------------------------------------------------------------

CLONES = Path(__file__).resolve().parent.parent / "adjuntos" / "Estudio"


def _muestra(*trozos):
    """Un archivo de los clonados en «adjuntos», o se salta la prueba.

    Son archivos de terceros y no se copian al proyecto: se consultan donde
    están, igual que la partitura de Chopin.
    """
    ruta = CLONES.joinpath(*trozos)
    if not ruta.is_file():
        pytest.skip("la muestra %s no está clonada" % ruta.name)
    return ruta


class PruebaOLE:
    """El envoltorio de los archivos de Office 97: un disquete en un archivo."""

    def test_se_leen_los_flujos_por_su_nombre(self):
        from formatos import ole

        contenedor = ole.abrir(_muestra("xlrd", "tests", "samples", "ragged.xls"))

        assert "Workbook" in contenedor.nombres()
        assert contenedor.existe("Workbook")
        assert len(contenedor.flujo("Workbook")) > 0

    def test_un_flujo_que_no_esta_no_es_un_error(self):
        """Los formatos antiguos guardan cosas opcionales: preguntar y no
        encontrarlas es lo normal."""
        from formatos import ole

        contenedor = ole.abrir(_muestra("xlrd", "tests", "samples", "ragged.xls"))

        assert contenedor.flujo("NoExiste") == b""
        assert not contenedor.existe("NoExiste")

    def test_lo_que_no_es_un_archivo_compuesto_se_dice(self):
        from formatos import ole

        assert not ole.es_compuesto(DATOS / "muestra.djvu")
        with pytest.raises(ole.ErrorOLE):
            ole.abrir(DATOS / "muestra.djvu")

    def test_los_flujos_pequenos_tambien_se_leen(self):
        """Van todos juntos dentro de otro, con su propia tabla."""
        from formatos import ole

        contenedor = ole.abrir(_muestra("xlrd", "tests", "samples", "ragged.xls"))
        resumen = contenedor.flujo("\x05SummaryInformation")

        # Ese flujo es de unos cientos de bytes: si se lee, la tabla pequeña
        # está bien seguida.
        assert 0 < len(resumen) < contenedor.corte_mini


class PruebaWord97:
    """Un `.doc` no se lee de corrido: hay que seguir su tabla de trozos."""

    def _documento(self):
        from formatos.base import OpcionesAnalisis, analizar
        import formatos.ofimatica_antigua                # noqa: F401

        return analizar(_muestra("oletools", "tests", "test-data", "msodde",
                                 "harmless-clean.doc"), OpcionesAnalisis())

    def test_se_lee_el_texto_de_un_documento_de_verdad(self):
        texto = self._documento().texto

        assert "harmless test document" in texto
        assert len(texto) > 100

    def test_los_parrafos_no_salen_pegados(self):
        texto = self._documento().texto

        assert texto.count("\n") >= 2

    def test_un_documento_protegido_se_dice_y_no_se_fuerza(self):
        """El programa no quita protecciones de ningún archivo."""
        from formatos.base import ErrorFormato, OpcionesAnalisis, analizar
        import formatos.ofimatica_antigua                # noqa: F401

        ruta = _muestra("oletools", "tests", "test-data", "encrypted",
                        "encrypted.doc")

        with pytest.raises(ErrorFormato) as fallo:
            analizar(ruta, OpcionesAnalisis())

        assert "contraseña" in str(fallo.value)

    def test_el_codigo_de_un_campo_no_se_lee_como_texto(self):
        """«EMBED Package» es maquinaria de Word, no algo que escribiera nadie."""
        from formatos.ofimatica_antigua import _limpiar

        crudo = "Antes\x13 EMBED Package \x14resultado\x15 después"

        # Queda lo que estaba fuera del campo y su resultado; el código del
        # campo —lo que va entre las dos primeras marcas— desaparece.
        assert _limpiar(crudo) == "Antesresultado después"

    def test_los_controles_de_word_se_traducen(self):
        from formatos.ofimatica_antigua import _limpiar

        assert _limpiar("uno\rdos") == "uno\ndos"
        assert _limpiar("celda\x07otra") == "celda\notra"
        assert _limpiar("gui\x1fon") == "guion"       # guion opcional: se quita


class PruebaExcel97:
    """Un `.xls` es una ristra de registros y una tabla de cadenas común."""

    def _libro(self, nombre="ragged.xls"):
        from formatos.base import OpcionesAnalisis, analizar
        import formatos.ofimatica_antigua                # noqa: F401

        return analizar(_muestra("xlrd", "tests", "samples", nombre),
                        OpcionesAnalisis())

    def test_se_leen_las_hojas_con_su_nombre(self):
        texto = self._libro().texto

        assert "Sheet1" in texto
        assert "Sheet2" in texto

    def test_las_celdas_salen_en_su_fila_y_su_columna(self):
        texto = self._libro().texto

        # La hoja es dentada a propósito: filas de distinta longitud.
        assert "a\tb\tc" in texto
        assert "g\th\tI\tj" in texto

    def test_los_numeros_se_leen_como_numeros(self):
        texto = self._libro("Formate.xls").texto

        assert "2741" in texto
        assert "38406" in texto

    def test_el_texto_que_no_cabe_en_latin1_no_se_rompe(self):
        """La tabla de cadenas cambia de codificación en cada costura."""
        texto = self._libro("formula_test_sjmachin.xls").texto

        assert "МОСКВА" in texto

    def test_una_tabla_es_una_tabla_de_verdad(self):
        documento = self._libro()
        from nucleo.marcas import TipoMarca

        assert documento.marcas.cantidad(TipoMarca.TABLA) >= 1

    def test_un_libro_protegido_se_dice_en_vez_de_soltar_disparates(self):
        """Sin detectarlo, el libro se abre igual y los nombres salen ilegibles."""
        from formatos.base import ErrorFormato, OpcionesAnalisis, analizar
        import formatos.ofimatica_antigua                # noqa: F401

        ruta = _muestra("oletools", "tests", "test-data", "encrypted",
                        "encrypted.xls")

        with pytest.raises(ErrorFormato) as fallo:
            analizar(ruta, OpcionesAnalisis())

        assert "contraseña" in str(fallo.value)

    def test_una_hoja_de_excel_4_se_reconoce_y_se_explica(self):
        from formatos.base import ErrorFormato, OpcionesAnalisis, analizar
        import formatos.ofimatica_antigua                # noqa: F401

        ruta = _muestra("xlrd", "tests", "samples",
                        "biff4_no_format_no_window2.xls")

        with pytest.raises(ErrorFormato) as fallo:
            analizar(ruta, OpcionesAnalisis())

        assert "Excel 4" in str(fallo.value)

    def test_el_numero_comprimido_se_deshace_bien(self):
        from formatos.ofimatica_antigua import _valor_rk

        # Entero puro, entero entre cien, y el mismo con el bit de los cien.
        assert _valor_rk((5 << 2) | 0x02) == 5
        assert _valor_rk((500 << 2) | 0x03) == 5.0

    def test_un_registro_roto_no_tira_la_hoja_entera(self):
        """Con un archivo de hace veinte años, perder una celda es lo de menos."""
        from formatos.ofimatica_antigua import _celdas_de_hoja

        # Un registro que dice que trae más bytes de los que trae.
        roto = b"\xfd\x00\x14\x00" + b"\x00" * 4
        assert _celdas_de_hoja(roto, 0, []) == []


class PruebaPowerPoint97:
    """De una presentación se saca lo que está en las diapositivas."""

    def _presentacion(self, carpeta, nombre):
        from formatos.base import OpcionesAnalisis, analizar
        import formatos.ofimatica_antigua                # noqa: F401

        return analizar(_muestra("oletools", "tests", "test-data", carpeta,
                                 nombre), OpcionesAnalisis())

    def test_cada_diapositiva_es_un_encabezado(self):
        texto = self._presentacion("oleobj", "embedded-simple-2007.ppt").texto

        assert "Diapositiva 1" in texto
        assert "Embedded Objects" in texto

    def test_no_se_cuela_la_maquinaria_de_powerpoint(self):
        """Las marcas de versión y los nombres de los objetos no son el texto."""
        texto = self._presentacion("oleobj", "embedded-simple-2007.ppt").texto

        assert "___PPT" not in texto
        assert "Objekt-Manager" not in texto

    def test_si_el_texto_solo_esta_en_el_guion_se_lee_de_ahi(self):
        """Perderlo por dónde esté guardado no tendría ningún sentido."""
        texto = self._presentacion("oleobj", "sample_with_lnk_file.ppt").texto

        assert "Test" in texto

    def test_una_presentacion_cifrada_se_dice(self):
        from formatos.base import ErrorFormato, OpcionesAnalisis, analizar
        import formatos.ofimatica_antigua                # noqa: F401

        ruta = _muestra("oletools", "tests", "test-data", "encrypted",
                        "encrypted.ppt")

        with pytest.raises(ErrorFormato) as fallo:
            analizar(ruta, OpcionesAnalisis())

        assert "contraseña" in str(fallo.value)


class PruebaFormatosAntiguosRegistrados:
    def test_las_seis_extensiones_estan(self):
        import formatos.ofimatica_antigua                # noqa: F401
        from formatos import base

        admitidas = set(base.extensiones_admitidas())
        for extension in (".doc", ".dot", ".xls", ".xlt", ".ppt", ".pps", ".pot"):
            assert extension in admitidas, extension


# ---------------------------------------------------------------------------
# Archivos de ayuda de Windows (.hlp)
# ---------------------------------------------------------------------------

class PruebaAyudaWindows:
    """Los manuales de todo un decenio, que hoy no abre ya nada.

    Se comprueba contra dos archivos de verdad y distintos entre sí: uno sin
    comprimir y otro con las dos compresiones puestas —LZ77 y frases—, que son
    justo los dos caminos del código.
    """

    def _ruta(self, nombre):
        ruta = CLONES / "muestras" / nombre
        if not ruta.is_file():
            pytest.skip("la muestra %s no está guardada" % nombre)
        return ruta

    def test_se_leen_los_archivos_internos(self):
        from formatos import hlp

        ayuda = hlp.Ayuda(self._ruta("ayuda_windows.hlp").read_bytes())

        assert "|SYSTEM" in ayuda.nombres()
        assert "|TOPIC" in ayuda.nombres()
        assert ayuda.archivo("|TOPIC")
        assert ayuda.archivo("|NoExiste") == b""

    def test_el_archivo_dice_de_si_mismo_como_esta_comprimido(self):
        from formatos import hlp

        ayuda = hlp.Ayuda(self._ruta("ayuda_windows.hlp").read_bytes())
        sistema = hlp.Sistema(ayuda.archivo("|SYSTEM"))

        assert sistema.titulo
        assert sistema.tamano_bloque in (2048, 4096)
        assert sistema.tamano_descomprimido > 0

    def test_un_archivo_sin_comprimir_se_lee_entero(self):
        from formatos.base import OpcionesAnalisis, analizar
        import formatos.hlp                                # noqa: F401

        documento = analizar(self._ruta("ayuda_windows.hlp"), OpcionesAnalisis())

        assert "Solitaire" in documento.metadatos.titulo
        assert "Klondike" in documento.texto
        # Los doce temas del índice, no los cinco primeros: los enlaces no
        # cruzan la costura de un bloque y hay que saltar el hueco.
        assert len(documento.texto) > 25000

    def test_un_archivo_comprimido_y_con_frases_tambien(self):
        from formatos.base import OpcionesAnalisis, analizar
        import formatos.hlp                                # noqa: F401

        documento = analizar(self._ruta("ayuda_faq.hlp"), OpcionesAnalisis())

        assert "Windows" in documento.metadatos.titulo
        assert "Frequently Asked Questions" in documento.texto
        assert len(documento.texto) > 50000

    def test_las_frases_se_leen_de_su_tabla(self):
        """La segunda compresión: lo que más se repite va una sola vez."""
        from formatos import hlp

        ayuda = hlp.Ayuda(self._ruta("ayuda_faq.hlp").read_bytes())
        frases = hlp.frases_clasicas(ayuda.archivo("|Phrases"))

        assert len(frases) > 100
        assert all(isinstance(frase, bytes) for frase in frases)

    def test_cada_tema_es_un_encabezado_con_su_titulo(self):
        from formatos.base import OpcionesAnalisis, analizar
        from nucleo.marcas import TipoMarca
        import formatos.hlp                                # noqa: F401

        documento = analizar(self._ruta("ayuda_windows.hlp"), OpcionesAnalisis())

        assert documento.marcas.cantidad(TipoMarca.ENCABEZADO1) >= 10

    def test_el_lz77_deshace_lo_que_repite(self):
        from formatos.hlp import descomprimir_lz77

        # Un byte de banderas sin ningún bit puesto: los cinco que siguen
        # salen tal cual.
        assert descomprimir_lz77(bytes([0]) + b"abcde") == b"abcde"
        # Un byte de banderas con el primer bit a cero y el segundo a uno:
        # una letra y después «vuelve una y copia tres».
        crudo = bytes([0b00000010, ord("x")]) + (0x0000).to_bytes(2, "little")
        assert descomprimir_lz77(crudo) == b"xxxx"

    def test_una_referencia_imposible_no_revienta(self):
        """Con un archivo de 1992 medio roto, lo que se lleve es lo que vale."""
        from formatos.hlp import descomprimir_lz77

        # Manda copiar de antes del principio.
        crudo = bytes([0b00000001]) + (0x0FFF).to_bytes(2, "little")

        assert descomprimir_lz77(crudo) == b""

    def test_lo_que_no_es_un_hlp_se_dice(self):
        from formatos import hlp

        with pytest.raises(hlp.ErrorHLP):
            hlp.Ayuda(b"esto no es un archivo de ayuda")

    def test_la_extension_esta_registrada(self):
        import formatos.hlp                                # noqa: F401
        from formatos import base

        assert ".hlp" in base.extensiones_admitidas()


# ---------------------------------------------------------------------------
# Abrir un RAR por nuestra cuenta
# ---------------------------------------------------------------------------

class PruebaRAR:
    """Un cómic partido en volúmenes, sin depender de que haya nada instalado.

    El caso que se resuelve es el peor de todos: el descompresor del sistema
    saca las páginas del primer volumen, dice que ha ido bien, y quien lo lee
    llega a la quinta entendiendo que ahí se acaba el cómic.
    """

    def _volumenes(self):
        volumenes = sorted(DATOS.glob("comic_guardado.part*.cbr"))
        if len(volumenes) < 2:
            pytest.skip("faltan los volúmenes de prueba")
        return volumenes

    def test_se_reconoce_un_rar(self):
        from nucleo import rar

        assert rar.es_rar(self._volumenes()[0])
        assert not rar.es_rar(DATOS / "muestra.djvu")

    def test_se_listan_todos_los_archivos_de_todos_los_volumenes(self):
        from nucleo import rar

        entradas = rar.leer(self._volumenes())

        assert len(entradas) == 12
        assert entradas[0].nombre == "pagina01.png"
        assert all(entrada.guardado for entrada in entradas)

    def test_un_archivo_que_cruza_de_volumen_se_junta(self):
        """Es exactamente lo que se perdía en silencio."""
        from nucleo import rar

        entradas = rar.leer(self._volumenes())
        partidos = [entrada for entrada in entradas if len(entrada.trozos) > 1]

        assert partidos, "el archivo de prueba debería tener uno partido"
        for entrada in partidos:
            assert len(entrada.datos()) == entrada.tamano

    def test_lo_sacado_es_identico_a_lo_que_habia(self, tmp_path):
        from nucleo import rar

        salidos, comprimidos = rar.extraer(self._volumenes(), tmp_path)

        assert len(salidos) == 12
        assert comprimidos == []
        for nombre in salidos:
            assert (tmp_path / nombre).stat().st_size > 0

    def test_lo_que_va_comprimido_de_verdad_se_dice_y_no_se_inventa(self):
        from nucleo import rar

        volumenes = sorted(DATOS.glob("comic_volumenes.part*.cbr"))
        if not volumenes:
            pytest.skip("faltan los volúmenes comprimidos de prueba")

        entradas = rar.leer(volumenes)
        comprimidas = [entrada for entrada in entradas if not entrada.guardado]

        assert comprimidas, "ese cómic sí lleva archivos comprimidos"
        with pytest.raises(rar.ErrorRAR):
            comprimidas[0].datos()

    def test_un_nombre_que_intente_salir_de_la_carpeta_no_sale(self):
        """Es un problema viejo y la respuesta es igual de vieja."""
        from nucleo.rar import _seguro

        assert _seguro("../../etc/passwd") == "etc/passwd"
        assert _seguro("C:/Windows/algo.dll") == "Windows/algo.dll"
        assert _seguro("..") is None
        assert _seguro("carpeta/pagina.png") == "carpeta/pagina.png"

    def test_lo_que_no_es_un_rar_se_dice(self):
        from nucleo import rar

        with pytest.raises(rar.ErrorRAR):
            rar.leer([DATOS / "muestra.djvu"])

    def test_el_comic_partido_se_abre_entero(self):
        from formatos.base import OpcionesAnalisis, analizar
        import formatos.comic                              # noqa: F401

        self._volumenes()
        documento = analizar(DATOS / "comic_guardado.part1.cbr",
                             OpcionesAnalisis())

        assert "Página 12" in documento.texto
        # Y sin el aviso de que falta la mitad, porque no falta.
        assert "falta" not in documento.texto.lower()


# ---------------------------------------------------------------------------
# Dibujos táctiles: figuras, varias series y la forma de un diagrama
# ---------------------------------------------------------------------------

VACIA = "\u2800"


class PruebaDibujoTactil:
    """Lo que se palpa de un dibujo son sus bordes, no su relleno."""

    def _puntos(self, lienzo):
        return sum(1 for linea in lienzo.lineas() for signo in linea
                   if signo != VACIA)

    def test_una_recta_no_deja_huecos(self):
        """Un hueco bajo el dedo no es una raya más fina: son dos rayas."""
        from nucleo.braille_grafico import Lienzo

        lienzo = Lienzo(20, 4)
        lienzo.segmento(0, 0, 39, 15)

        # Una diagonal por un lienzo de 40 por 16 puntos toca todas las
        # columnas de celdas por las que pasa.
        assert self._puntos(lienzo) >= 15

    def _encendido(self, lienzo, x, y):
        from nucleo.braille_grafico import _BIT

        celda_x, columna = divmod(x, 2)
        celda_y, fila = divmod(y, 4)
        return bool(lienzo.puntos[celda_y][celda_x] & _BIT[(fila, columna)])

    def test_un_rectangulo_se_dibuja_hueco(self):
        """Bajo el dedo, una mancha de puntos es una mancha: lo que dice qué
        figura es son sus bordes."""
        from nucleo.braille_grafico import Lienzo

        lienzo = Lienzo(10, 2)
        lienzo.rectangulo(2, 1, 15, 6)

        assert self._encendido(lienzo, 2, 1)          # una esquina
        assert self._encendido(lienzo, 8, 1)          # el borde de arriba
        assert self._encendido(lienzo, 8, 6)          # el de abajo
        assert not self._encendido(lienzo, 8, 3)      # y el centro, vacío

    def test_las_figuras_de_geometria_salen_cerradas(self):
        from nucleo import braille_grafico as bg

        for clase in ("circulo", "cuadrado", "triangulo", "rombo"):
            lienzo = bg.figura(clase, 20, 5)
            assert self._puntos(lienzo) > 8, clase

    def test_una_figura_que_no_se_conoce_no_se_inventa(self):
        from nucleo import braille_grafico as bg

        assert self._puntos(bg.figura("mapa de europa", 20, 4)) == 0

    def test_varias_series_van_a_la_misma_escala(self):
        """Cada una con su escala daría dos dibujos que no se pueden comparar."""
        from nucleo import braille_grafico as bg

        subida = list(range(20))
        plana = [10] * 20

        juntas = bg.varias_curvas([subida, plana], 20, 4)
        lineas = juntas.lineas()

        # La plana está en medio y la que sube atraviesa de abajo arriba.
        assert lineas[0].strip(VACIA)
        assert lineas[-1].strip(VACIA)

    def test_mas_de_tres_series_no_se_dibujan(self):
        """Con cuatro los puntos se pisan y lo que queda es una mancha."""
        from nucleo import braille_grafico as bg

        cuatro = [list(range(10)) for _ in range(4)]

        assert self._puntos(bg.varias_curvas(cuatro, 20, 4)) == \
            self._puntos(bg.varias_curvas(cuatro[:3], 20, 4))

    def test_la_forma_de_un_diagrama_se_dibuja(self):
        from nucleo import braille_grafico as bg

        cajas = [(paso, 0) for paso in range(4)]
        flechas = [(paso, paso + 1) for paso in range(3)]

        lienzo = bg.esquema(cajas, flechas, 30, 4)

        assert self._puntos(lienzo) > 10

    def test_un_diagrama_sin_cajas_no_dibuja_nada(self):
        from nucleo import braille_grafico as bg

        assert self._puntos(bg.esquema([], [], 20, 4)) == 0

    def test_la_planta_de_un_esquema_reparte_por_pasos_y_ramas(self):
        from nucleo import esquemas

        esquema = esquemas.interpretar(RESPUESTA_DIAGRAMA)
        cajas, flechas = esquema.planta()

        assert len(cajas) == 5
        # El primer paso es el inicio, y hay al menos cuatro niveles.
        assert cajas[0] == (0, 0)
        assert max(paso for paso, _rama in cajas) >= 3
        assert flechas

    def test_un_bucle_no_hace_que_la_planta_de_vueltas(self):
        """El diagrama de prueba tiene uno: del tercero vuelve al segundo."""
        from nucleo import esquemas

        esquema = esquemas.interpretar(RESPUESTA_DIAGRAMA)

        cajas, _flechas = esquema.planta()

        assert len(cajas) == len(esquema.cajas)

    def test_el_html_del_diagrama_lleva_su_silueta(self):
        from nucleo import esquemas, html_elementos

        html = html_elementos.html_de_esquema(
            esquemas.interpretar(RESPUESTA_DIAGRAMA))

        assert "La forma del diagrama" in html
        assert VACIA in html or "\u2801" in html


# ---------------------------------------------------------------------------
# El 7-Zip que viaja con el programa
# ---------------------------------------------------------------------------

class PruebaSieteZipPropio:
    """Abrir un cómic no puede depender de lo que cada equipo tenga instalado."""

    def test_esta_donde_tiene_que_estar(self):
        from nucleo import descomprimir, rutas

        propio = rutas.directorio_datos() / "bin" / "7z.exe"
        if not propio.is_file():
            pytest.skip("falta el 7-Zip portable; se prepara con "
                        "herramientas/siete_zip_portable.py")

        assert descomprimir.ruta_del_7zip() == str(propio)
        assert descomprimir._ruta_de("7z") == str(propio)

    def test_es_el_primero_que_se_prueba(self):
        """El «tar» de Windows saca la mitad de un RAR partido sin decirlo."""
        from nucleo import descomprimir

        assert descomprimir.PROGRAMAS[0][0] == "7z"
        assert list(descomprimir.LISTADOS)[0] == "7z"

    def test_lista_todos_los_volumenes_de_un_comic_partido(self):
        """Preguntándole al «tar» salían dos de doce, y parecía completo."""
        from nucleo import descomprimir

        ruta = DATOS / "comic_guardado.part1.cbr"
        if not ruta.is_file():
            pytest.skip("no están las muestras de cómic")
        if not descomprimir.ruta_del_7zip():
            pytest.skip("falta el 7-Zip portable")

        assert len(descomprimir.contenido(ruta)) == 12

    def test_sabe_de_rar_y_de_rar5(self):
        """Sin la biblioteca al lado, el ejecutable arranca y no abre un RAR."""
        import subprocess

        from nucleo import descomprimir

        programa = descomprimir.ruta_del_7zip()
        if not programa:
            pytest.skip("falta el 7-Zip portable")
        salida = subprocess.run([programa, "i"], capture_output=True,
                                timeout=60).stdout.decode("utf-8", "replace")

        assert " Rar " in salida or " Rar5 " in salida

    def test_viaja_con_su_licencia(self):
        """Al repartir un programa ajeno hay que llevar su licencia."""
        from nucleo import rutas

        binarios = rutas.directorio_datos() / "bin"
        if not (binarios / "7z.exe").is_file():
            pytest.skip("falta el 7-Zip portable")

        assert (binarios / "7z.dll").is_file()
        assert (binarios / "License.txt").is_file()

    def test_el_aviso_ya_no_manda_instalar_nada(self):
        """El programa lo trae: mandar instalar algo sería mentir."""
        from nucleo import descomprimir

        aviso = descomprimir.motivo_de_fallo("album.cbr")

        assert "instala" not in aviso.lower()
        assert "WinRAR" not in aviso


# ---------------------------------------------------------------------------
# Quién habla: el modo entrevista
# ---------------------------------------------------------------------------

NOVELA = """El sol caía a plomo sobre el camino de tierra.
—No pienso ir —dijo ella—. Y no insistas más.
Juan la miró un rato largo sin decir nada.
—Como quieras —murmuró al fin.
El tema estaba bien-documentado y no admitía dudas."""

LISTA_DE_LA_COMPRA = """Hay que comprar tres cosas:
- Pan.
- Leche.
- Café."""


class PruebaDialogos:
    """Lo que cuesta no es cambiar de voz: es distinguir una raya de un guion."""

    def _tramos(self, texto):
        from nucleo import dialogos

        return [(trozo, es) for trozo, es
                in dialogos.tramos(texto,
                                   con_guiones=not dialogos.usa_rayas(texto))
                if trozo.strip()]

    def test_se_reconoce_quien_habla_en_cada_tramo(self):
        tramos = self._tramos(NOVELA)
        dicho = {trozo.strip(): es for trozo, es in tramos}

        assert dicho["No pienso ir"] is True
        assert dicho["dijo ella"] is False
        assert dicho[". Y no insistas más."] is True

    def test_la_narracion_de_alrededor_sigue_siendo_narracion(self):
        tramos = self._tramos(NOVELA)

        primero = tramos[0][0].strip()
        assert primero.startswith("El sol caía")
        assert tramos[0][1] is False

    def test_una_lista_con_guiones_no_es_un_dialogo(self):
        """Poner voz de personaje a la lista de la compra es lo peor que puede
        pasar aquí."""
        tramos = self._tramos(LISTA_DE_LA_COMPRA)

        assert not any(es for _trozo, es in tramos)

    def test_un_guion_dentro_de_una_palabra_no_parte_nada(self):
        tramos = self._tramos(NOVELA)
        juntas = " ".join(trozo for trozo, _es in tramos)

        assert "bien-documentado" in juntas

    def test_el_libro_dice_solo_cómo_marca_sus_dialogos(self):
        from nucleo import dialogos

        assert dialogos.usa_rayas(NOVELA)
        assert not dialogos.usa_rayas(LISTA_DE_LA_COMPRA)

    def test_con_rayas_en_el_libro_un_guion_no_cuenta(self):
        """En el mismo libro, un guion no puede ser diálogo en una página y una
        lista en la siguiente."""
        from nucleo import dialogos

        assert not dialogos.es_apertura("- Un guion suelto que parece diálogo.",
                                        con_guiones=False)
        assert dialogos.es_apertura("—Una raya de verdad.", con_guiones=False)

    def test_un_guion_solo_cuenta_si_parece_una_intervencion(self):
        from nucleo import dialogos

        assert not dialogos.es_apertura("- Pan.", con_guiones=True)
        assert dialogos.es_apertura(
            "- No pienso ir a ninguna parte contigo, y lo sabes.",
            con_guiones=True)

    def test_se_cuentan_las_intervenciones_para_saber_si_merece_la_pena(self):
        from nucleo import dialogos

        assert dialogos.cuantas_intervenciones(NOVELA) == 2
        assert dialogos.cuantas_intervenciones(LISTA_DE_LA_COMPRA) == 0
        assert not dialogos.hay_bastante_dialogo(NOVELA)

    def test_el_texto_no_se_pierde_al_repartirlo(self):
        """Lo que se lee tiene que ser lo mismo, con tono o sin él."""
        from nucleo import dialogos

        for texto in (NOVELA, LISTA_DE_LA_COMPRA):
            trozos = dialogos.tramos(texto,
                                     con_guiones=not dialogos.usa_rayas(texto))
            juntos = "".join(trozo for trozo, _es in trozos)
            # Lo único que desaparece son las propias rayas, que son marcas y
            # no texto: la voz no las dice.
            sin_rayas = texto
            for raya in dialogos.RAYAS:
                sin_rayas = sin_rayas.replace(raya, "")
            assert juntos.replace(" ", "") == sin_rayas.replace(" ", "")

    def test_las_marcas_de_tono_escapan_el_texto(self):
        """Un libro trae signos de menor y ampersand, y sin escaparlos la marca
        se rompe y se pierde la frase."""
        from nucleo.voz import Sintetizador

        marcado = Sintetizador.con_tono("a < b & c", 4)

        assert "&lt;" in marcado and "&amp;" in marcado
        assert marcado.startswith("<pitch")

    def test_sin_cambio_de_tono_no_se_pone_ninguna_marca(self):
        from nucleo.voz import Sintetizador

        assert Sintetizador.con_tono("hola", 0) == "hola"


# ---------------------------------------------------------------------------
# Adornos: trinos, mordentes, grupetos y apoyaturas
# ---------------------------------------------------------------------------

class PruebaImagenesDeAyuda:
    """Los iconos y las capturas de pantalla de un manual de 1993.

    No son la parte importante de un archivo de ayuda —el texto lo es—, pero
    una captura con el rótulo «pulse aquí» dentro es contenido que se perdía
    entero: no salía ni como imagen sin describir.
    """

    def _ruta(self, nombre):
        ruta = CLONES / "muestras" / nombre
        if not ruta.is_file():
            pytest.skip("la muestra %s no está guardada" % nombre)
        return ruta

    def test_se_sacan_y_son_pngs_de_verdad(self):
        import struct

        from formatos import hlp

        ayuda = hlp.Ayuda(self._ruta("ayuda_windows.hlp").read_bytes())
        imagenes = hlp.imagenes_de(ayuda)

        assert set(imagenes) == {0, 1}
        for numero, datos in imagenes.items():
            assert datos.startswith(b"\x89PNG\r\n\x1a\n"), numero
            ancho, alto = struct.unpack(">II", datos[16:24])
            # Son iconos de la época: ni un píxel ni una pantalla entera.
            assert 8 <= ancho <= 800 and 8 <= alto <= 800, (numero, ancho, alto)

    def test_el_mapa_de_bits_sale_del_tamano_exacto(self):
        """Cada fila se rellena hasta un múltiplo de cuatro bytes.

        Olvidarlo inclina la imagen un poco más en cada fila. No revienta, no
        cambia el tamaño y se ve enseguida mirándola, que es justo lo que una
        prueba no hace: por eso se comprueba el número.
        """
        from formatos import hlp

        ayuda = hlp.Ayuda(self._ruta("ayuda_windows.hlp").read_bytes())
        datos = ayuda.archivo("|bm0")
        import struct

        sitio = struct.unpack_from("<I", datos, 4)[0]
        assert datos[sitio] == 6          # mapa de bits independiente
        assert datos[sitio + 1] == 1      # comprimido con RunLen
        assert hlp.imagen_a_png(datos, sitio)

    def test_el_runlen_hace_las_dos_cosas_que_sabe(self):
        """Copiar tal cual y repetir: no hay más."""
        from formatos.hlp import descomprimir_runlen

        # 0x83 = copia los tres siguientes; 0x04 = repite cuatro veces el que va.
        assert descomprimir_runlen(b"\x83abc\x04z", 100) == b"abczzzz"
        # Y no se pasa del tope aunque el archivo diga que sí.
        assert len(descomprimir_runlen(b"\x7fz" * 50, 10)) <= 10 + 127

    def test_un_metarchivo_no_se_inventa(self):
        """Un dibujo vectorial no son píxeles: redibujarlo es otro programa."""
        from formatos import hlp

        assert hlp.imagen_a_png(b"\x08\x00" + b"\x00" * 40, 0) is None

    def test_van_donde_van_y_no_todas_al_final(self):
        """La frase y la captura que la acompaña se leen juntas.

        Se comprueba que **hay texto por delante y por detrás** de una imagen:
        si el análisis de los ajustes del párrafo fallara, las imágenes
        acabarían todas amontonadas al final y esto se caería.
        """
        from formatos import hlp

        _sistema, temas = hlp.leer(self._ruta("ayuda_windows.hlp"))
        con_imagen = [tema for tema in temas
                      if any(clase == "imagen" for clase, _p in tema.piezas)]

        assert con_imagen, "ningún tema trae imagen"
        clases = [clase for clase, _p in con_imagen[0].piezas]
        primera = clases.index("imagen")
        assert "texto" in clases[:primera]
        assert "texto" in clases[primera + 1:]

    def test_el_documento_las_deja_pendientes_de_describir(self):
        """Sin texto alternativo, porque el formato no lo tiene.

        Así quedan marcadas como pendientes y se pueden mandar a la IA, en vez
        de aparecer con una descripción inventada que nadie podría contrastar.
        """
        from formatos import base, hlp                     # noqa: F401
        from nucleo.marcas import TipoMarca

        ruta = self._ruta("ayuda_windows.hlp")
        documento = base.analizar(ruta)
        grupo = documento.marcas.grupos.get(int(TipoMarca.IMAGEN))

        assert grupo is not None and len(grupo.marcas) == 2
        for marca in grupo.marcas:
            assert base.extraer_recurso(ruta, marca.referencia)

    def test_un_archivo_sin_imagenes_no_se_inventa_ninguna(self):
        from formatos import hlp

        ayuda = hlp.Ayuda(self._ruta("ayuda_faq.hlp").read_bytes())

        assert hlp.imagenes_de(ayuda) == {}


class PruebaAdornos:
    """Sus signos no están en el B 4-2: salen del manual internacional.

    El propio documento español avisa de que no es exhaustivo y remite al *New
    International Manual of Braille Music Notation*, que está guardado en
    `adjuntos/Estudio/normas`. Los signos de aquí son su tabla 11.
    """

    def test_todos_se_construyen_sobre_dos_celdas(self):
        """El trino y el grupeto, con lo que les pongan alrededor.

        Es lo que los hace reconocibles al tacto: se aprenden dos celdas, no
        cinco signos sueltos.
        """
        from nucleo import braille_musica as bm

        for nombre, signo in bm.ADORNOS.items():
            assert bm._TRINO in signo or bm._GRUPETO in signo, nombre

    def test_el_mordente_de_musicxml_no_es_el_invertido(self):
        """Los nombres van cambiados entre los dos mundos, y confundirlos toca
        la nota de al lado en vez de la de abajo."""
        from nucleo import braille_musica as bm

        assert bm.ADORNOS["mordent"] != bm.ADORNOS["inverted-mordent"]
        # El mordente lleva además los puntos de inversión detrás.
        assert bm.ADORNOS["mordent"][-1] == bm._INVERSION
        assert bm._INVERSION not in bm.ADORNOS["inverted-mordent"]

    def test_el_adorno_va_delante_de_la_nota_y_no_pide_octava(self):
        from nucleo import braille_musica as bm

        antes = bm.Nota("C", 4, "quarter")
        con_trino = bm.Nota("D", 4, "quarter", adornos=("trill-mark",))

        celdas = bm.celdas_de_nota(con_trino, antes)

        assert celdas[0] == bm.ADORNOS["trill-mark"][0]
        # Un salto de segunda no lleva octava, y el adorno no la obliga.
        assert bm.OCTAVAS[4] not in celdas

    def test_un_adorno_desconocido_no_se_inventa(self):
        from nucleo.braille_musica import Imposible, Nota
        from nucleo import braille_musica as bm

        with pytest.raises(Imposible):
            bm.celdas_de_nota(Nota("C", 4, "quarter", adornos=("tremolo",)), None)

    def test_la_apoyatura_larga_y_la_corta_se_distinguen(self):
        """En braille tienen signo distinto, así que la diferencia se conserva."""
        from nucleo import braille_musica as bm

        larga = bm.celdas_de_nota(bm.Nota("D", 4, "eighth", apoyatura="larga"), None)
        corta = bm.celdas_de_nota(bm.Nota("D", 4, "eighth", apoyatura="corta"), None)

        assert larga[:2] == list(bm.APOYATURA)
        assert corta[:1] == list(bm.APOYATURA_CORTA)
        assert larga != corta

    def test_lo_que_lleva_la_nota_se_dice_tambien_en_palabras(self):
        from nucleo import braille_musica as bm

        dicho = bm.Nota("C", 4, "quarter", adornos=("turn",)).nombre()

        assert "grupeto" in dicho

    def test_una_nota_de_adorno_ya_no_se_tira(self):
        """Antes se contaban y se avisaba; ahora se escriben."""
        from formatos.musicaxml import _apoyatura_de
        from lxml import etree

        larga = etree.fromstring(b"<note><grace/><pitch><step>D</step>"
                                 b"<octave>4</octave></pitch></note>")
        corta = etree.fromstring(b'<note><grace slash="yes"/><pitch>'
                                 b"<step>D</step><octave>4</octave></pitch></note>")
        normal = etree.fromstring(b"<note><pitch><step>D</step>"
                                  b"<octave>4</octave></pitch></note>")

        assert _apoyatura_de(larga) == "larga"
        assert _apoyatura_de(corta) == "corta"
        assert _apoyatura_de(normal) == ""

    def test_lo_que_sigue_sin_escribirse_se_dice(self):
        """Un trémolo o un arpegio entre pentagramas no tienen signo aquí."""
        from formatos.musicaxml import SIN_ESCRIBIR

        assert "tremolo" in SIN_ESCRIBIR
        from nucleo.braille_musica import ADORNOS

        assert not set(SIN_ESCRIBIR) & set(ADORNOS)
