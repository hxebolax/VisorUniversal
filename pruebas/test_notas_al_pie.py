# -*- coding: utf-8 -*-
"""Pruebas del recorte de una nota al pie.

Leer una nota con «Alt+Mayús+N» significa sacar del documento el trozo que le
corresponde, y saber dónde acaba no es evidente. En un libro corriente cada nota
es su propio párrafo; en una edición muy anotada van todas seguidas dentro del
mismo, y quedarse en el final del párrafo era leer la nota pedida y las tres
siguientes. Lo reportó un lector de los «Discursos» de Isócrates.

Los dos riesgos son simétricos y aquí están los dos: quedarse largo —leer de
más— y quedarse corto, que es peor, porque se come el final de la nota sin que
nadie se entere.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ / "src"))


def leer_la_nota(texto: str, donde: int) -> str:
    """El recorte de la ventana, sin la ventana.

    ``documento`` es una propiedad de la ventana principal y construirla entera
    para esto pediría una interfaz montada. Lo que se prueba es el recorte.
    """
    from interfaz import ventana

    class DocumentoDePrueba:
        def __init__(self, texto, donde):
            self.texto = texto
            self._donde = donde

        def resolver_referencia(self, referencia):
            return self._donde if referencia == "aqui" else -1

    class Marca:
        referencia = "aqui"

    class VentanaFalsa:
        documento = DocumentoDePrueba(texto, donde)
        _texto_de_la_nota = ventana.VentanaPrincipal._texto_de_la_nota

    return VentanaFalsa()._texto_de_la_nota(Marca())


#: Las notas tal como vienen en una edición anotada: seguidas, en un solo
#: párrafo, cada una con su número delante y su enlace de vuelta detrás.
SEGUIDAS = (
    "El cuerpo del capítulo, con su texto normal.\n\n"
    "[18] Igual que Platón, Isócrates parte de lo generalmente reconocido; a "
    "este sistema le llama «hipótesis» y de ella arranca la deducción "
    "(JAEGER, Paideia\u2026, pág. 880, n. 57). << "
    "[19] El objetivo de la cultura retórica es crear el estado de perfección "
    "de la vida humana. << "
    "[20] La tercera, para comprobar que tampoco se cuela.\n\n"
    "Y sigue el libro."
)


class PruebaDondeAcabaUnaNota:
    """Que se lea la nota pedida y solo esa."""

    def test_no_se_cuela_la_nota_siguiente(self):
        """El fallo que lo empezó todo: pedías la 18 y te daban la 18 y la 19."""
        leido = leer_la_nota(SEGUIDAS, SEGUIDAS.index("[18]"))

        assert leido.startswith("[18] Igual que Platón")
        assert "[19]" not in leido
        assert "[20]" not in leido

    def test_no_se_lee_el_enlace_de_vuelta(self):
        """El «<<» es un botón para volver, y en voz alta no dice nada."""
        leido = leer_la_nota(SEGUIDAS, SEGUIDAS.index("[18]"))

        assert "<<" not in leido
        assert leido.rstrip().endswith("n. 57).")

    def test_la_nota_sale_entera(self):
        """Quedarse corto es peor que quedarse largo: no se nota."""
        leido = leer_la_nota(SEGUIDAS, SEGUIDAS.index("[18]"))

        assert "«hipótesis»" in leido
        assert "JAEGER" in leido

    def test_una_comilla_de_apertura_no_termina_la_nota(self):
        """En español « abre una cita, y hay notas llenas de ellas.

        Estuvo un rato en la lista de marcas de vuelta, y cortaba la nota en la
        primera palabra entrecomillada.
        """
        texto = "[1] Lo que él llama «areté» y nosotros virtud, sin más.\n\n"

        leido = leer_la_nota(texto, 0)

        assert "virtud" in leido

    def test_una_enumeracion_entre_parentesis_no_termina_la_nota(self):
        """Una nota puede enumerar: «(1) seguridad, (2) prosperidad»."""
        texto = ("[7] Este concepto encierra los siguientes postulados: "
                 "(1) seguridad, (2) prosperidad, (3) armonía interior.\n\n")

        leido = leer_la_nota(texto, 0)

        assert "armonía interior" in leido

    def test_la_nota_que_es_su_propio_parrafo_sigue_igual(self):
        """Lo de siempre, que es lo que hace casi cualquier libro."""
        texto = ("Cuerpo.\n\n[3] Una nota corriente, en su párrafo.\n\n"
                 "Más cuerpo que no se lee.")

        leido = leer_la_nota(texto, texto.index("[3]"))

        assert leido == "[3] Una nota corriente, en su párrafo."

    def test_una_nota_larguisima_se_corta_y_lo_dice(self):
        """No se puede soltar un aviso hablado de cinco minutos."""
        from interfaz import ventana

        texto = "[9] " + ("palabra " * 400) + "\n\n"

        leido = leer_la_nota(texto, 0)

        assert len(leido) < len(texto)
        assert "Intro" in leido
        assert len(leido) >= ventana.LARGO_NOTA - 1

    def test_una_referencia_que_no_lleva_a_ninguna_parte_no_revienta(self):
        """Un enlace roto es cosa de todos los días en un libro."""
        from interfaz import ventana

        class DocumentoSinDestino:
            texto = "lo que sea"

            @staticmethod
            def resolver_referencia(referencia):
                return -1

        class Marca:
            referencia = "no existe"

        class VentanaFalsa:
            documento = DocumentoSinDestino()
            _texto_de_la_nota = ventana.VentanaPrincipal._texto_de_la_nota

        assert VentanaFalsa()._texto_de_la_nota(Marca()) == ""


def documento_falso(texto: str):
    """Un documento con lo justo: su texto y sus notas.

    Montar un EPUB de verdad para esto pediría un archivo de prueba y un
    analizador; lo que se comprueba aquí es qué se saca del texto.
    """
    from nucleo.marcas import Marca, TipoMarca

    donde_notas = texto.index("NOTAS")
    marcas = []
    for rotulo in ("[1]", "[2]", "[3]"):
        llamada = texto.find(rotulo)
        if 0 <= llamada < donde_notas:
            marcas.append(Marca(TipoMarca.NOTA_PIE, llamada, rotulo, rotulo))

    class Grupo:
        def __init__(self, marcas):
            self.marcas = marcas

    class Marcas:
        @staticmethod
        def grupo(tipo):
            return Grupo([uno for uno in marcas if uno.tipo == tipo])

    class Documento:
        def __init__(self):
            self.texto = texto
            self.marcas = Marcas()

        @staticmethod
        def resolver_referencia(referencia):
            return texto.find(referencia, donde_notas)

    return Documento()


class PruebaTodasLasNotas:
    """Sacar de un documento todas sus notas con su texto, de una vez.

    Es lo que alimenta el visor de notas, y tiene que ser barato: en un libro
    anotado son quinientas, y recorrerlas con las flechas no puede volver al
    texto una por una.
    """

    def test_saca_cada_nota_con_su_texto(self):
        from nucleo import notas

        doc = documento_falso(
            "Cuerpo con [1] y con [2] dentro.\n\nNOTAS\n\n"
            "[1] La primera. << [2] La segunda.\n\n")

        salida = notas.todas(doc)

        assert [uno.rotulo for uno in salida] == ["[1]", "[2]"]
        assert salida[0].texto == "[1] La primera."
        assert salida[1].texto == "[2] La segunda."

    def test_la_llamada_y_la_nota_son_sitios_distintos(self):
        """Los dos hacen falta: uno es el pasaje y el otro el texto de la nota."""
        from nucleo import notas

        doc = documento_falso(
            "Cuerpo con [1] dentro.\n\nNOTAS\n\n[1] La primera.\n\n")

        una = notas.todas(doc)[0]

        assert una.llamada < una.destino
        assert doc.texto[una.llamada:].startswith("[1] dentro")
        assert doc.texto[una.destino:].startswith("[1] La primera")

    def test_las_notas_del_visor_salen_enteras(self):
        """El visor no recorta: para eso está el aviso hablado, no esto."""
        from nucleo import notas

        larga = "palabra " * 300
        doc = documento_falso(
            "Cuerpo con [1] dentro.\n\nNOTAS\n\n[1] " + larga + "\n\n")

        una = notas.todas(doc)[0]

        assert "Intro" not in una.texto
        assert len(una.texto) > 1000

    def test_una_nota_con_el_enlace_roto_no_entra_ni_revienta(self):
        """Un enlace que no lleva a ninguna parte es cosa de todos los días."""
        from nucleo import notas
        from nucleo.marcas import Marca, TipoMarca

        class Documento:
            texto = "Cuerpo.\n\nNOTAS\n\nsin nada.\n\n"

            class marcas:
                @staticmethod
                def grupo(tipo):
                    return type("G", (), {"marcas": [
                        Marca(TipoMarca.NOTA_PIE, 0, "[1]", "no existe")]})()

            @staticmethod
            def resolver_referencia(referencia):
                return -1

        assert notas.todas(Documento()) == []


class PruebaBuscarEnLasNotas:
    """El filtro del visor, que es lo que lo hace útil con quinientas."""

    def test_no_distingue_tildes_ni_mayusculas(self):
        """Quien escribe «isocrates» busca «Isócrates», y en un clásico eso manda."""
        from interfaz.dialogos.notas_al_pie import _sin_tildes

        assert _sin_tildes("Isócrates") == "isocrates"
        assert _sin_tildes("EUDAIMONÍA") == "eudaimonia"
        assert _sin_tildes("Paideia…") == "paideia…"

    def test_la_enye_se_conserva_como_letra(self):
        """La ñ no es una n con adorno: quien busca «año» no busca «ano»."""
        from interfaz.dialogos.notas_al_pie import _sin_tildes

        assert "n" + chr(0x303) not in _sin_tildes("Año")
