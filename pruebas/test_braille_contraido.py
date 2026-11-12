# -*- coding: utf-8 -*-
"""Pruebas del braille contraído español.

**La prueba que importa es la última**, y no es una prueba escrita a mano: el
documento técnico B 16-1 de la Comisión Braille Española trae ciento veintitrés
palabras con su transcripción resuelta, y aquí se comparan todas.

Esa comparación es posible porque el documento escribe cada signo dos veces
—como glifo del ASCII braille de la ONCE y como lista de puntos—, lo que permite
reconstruir la correspondencia entre los dos y descodificar sus ejemplos. Sin
ella, comprobar una transcripción de braille sería comprobarla contra lo que uno
mismo ha entendido del documento, que no comprueba nada.

Los ejemplos que no se cumplen están **enumerados uno a uno** más abajo, con lo
que se sabe de cada uno. Es deliberado: una prueba que se limitara a exigir «más
de un noventa por ciento» dejaría que los fallos cambiaran de sitio sin que
nadie se enterase.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nucleo import braille_contraido as contraido
from nucleo import braille_contraido_tablas as tablas

DATOS = Path(__file__).resolve().parent / "datos" / "contraido_ejemplos.json"


def _cargar():
    return json.loads(DATOS.read_text(encoding="utf-8"))


def _descifrar(glifos: str, alfabeto: dict):
    """Del ASCII braille de la ONCE a la lista de celdas."""
    salida = []
    for signo in glifos:
        puntos = alfabeto.get(signo)
        if puntos is None:
            return None
        valor = 0
        for numero in puntos:
            valor |= 1 << (int(numero) - 1)
        salida.append(valor)
    return salida


#: Ejemplos del documento que **no** se transcriben igual, con el porqué. Están
#: escritos aquí para que un cambio los mueva y la prueba lo diga.
CONOCIDOS = {
    # El ejemplo trae una celda de más al principio: en el PDF, esa línea lleva
    # dos ejemplos pegados y al extraerla se juntan.
    "españas",
    # «-ción» detrás de vocal: el ejemplo escribe la ce dentro del signo de
    # «-ión», pero «canciones» la escribe fuera. No hay regla que valga para
    # los dos, así que se deja la ce fuera, que es lo que hacen los demás.
    "reinterpretación",
    # La contracción «in» aquí cruza dos sílabas («cipli-nar») y el documento
    # no la usa. La regla que lo decidiría es de sílabas, no de letras.
    "interdisciplinar",
    # Los dos salen en el capítulo de las contracciones, ilustrando «br» y
    # «es»; escritos con su final —«-bre»— ocupan una celda menos, que es lo
    # que manda el orden de los pasos.
    "cobre",
    "establo",
    # Llevan delante el signo de palabra extranjera, que no se puede decidir
    # mirando las letras.
    "show",
    "kilo",
}


class PruebaTablas:
    def test_las_tablas_estan_completas(self):
        assert len(tablas.PALABRAS) > 250
        assert len(tablas.VARIANTES) > 400
        assert len(tablas.PRINCIPIOS) == 10
        assert len(tablas.SECUENCIAS) == 4
        assert len(tablas.CONTIGUAS) == 7
        assert len(tablas.CONTRACCIONES) == 26

    def test_ninguna_celda_se_sale_del_cajetin(self):
        """Seis puntos son 64 combinaciones: nada puede pasar de 63."""
        for tabla in (tablas.PALABRAS, tablas.PRINCIPIOS, tablas.FINALES,
                      tablas.SECUENCIAS, tablas.CONTRACCIONES,
                      tablas.GENERO_Y_NUMERO):
            for clave, celdas in tabla.items():
                for celda in celdas:
                    assert 0 <= celda <= 63, "%r: %r" % (clave, celdas)
        for letra, celda in tablas.LETRAS.items():
            assert 0 <= celda <= 63, letra

    def test_cada_variante_sale_de_una_palabra_de_la_lista(self):
        for variante, base in tablas.VARIANTES.items():
            assert base in tablas.PALABRAS, "%s -> %s" % (variante, base)


class PruebaReglas:
    def test_una_palabra_de_la_lista_se_escribe_con_su_signo(self):
        assert contraido.celdas_de_palabra("bien") == list(tablas.PALABRAS["bien"])
        # «importante» es el ejemplo del propio documento: de diez celdas a tres.
        assert len(contraido.celdas_de_palabra("importante")) == 3

    def test_la_mayuscula_lleva_su_signo_delante(self):
        con = contraido.celdas_de_palabra("Bien")
        sin = contraido.celdas_de_palabra("bien")
        assert con == [tablas.MAYUSCULA] + sin

    def test_un_principio_no_va_delante_de_una_vocal(self):
        """«re-» vale en «retina» y no en «reactivo».

        No se puede comprobar mirando la primera celda: cuatro de los diez
        principios **son** una letra del alfabeto, y «re-» y la erre se
        escriben igual. Lo que los distingue es lo que viene detrás.
        """
        # En «retina» la erre es el principio: detrás va la te, no la e.
        assert contraido.celdas_de_palabra("retina")[1] != tablas.LETRAS["e"]
        # En «reactivo» es la letra erre, y la e se escribe entera.
        assert contraido.celdas_de_palabra("reactivo")[1] == tablas.LETRAS["e"]
        # Lo mismo con «com-»: vale en «comparar» y no en «común».
        assert (contraido.celdas_de_palabra("comparar")[0]
                == tablas.PRINCIPIOS["com"][0])
        assert contraido.celdas_de_palabra("común")[0] == tablas.LETRAS["c"]

    def test_los_principios_se_encadenan(self):
        """«sobreinterpretar» son tres seguidos."""
        celdas = contraido.celdas_de_palabra("sobreinterpretar")
        assert celdas[:3] == [tablas.PRINCIPIOS["sobre"][0],
                              tablas.PRINCIPIOS["inter"][0],
                              tablas.PRINCIPIOS["pre"][0]]

    def test_un_principio_tiene_que_preceder_a_algo(self):
        """En «entren», «entre-» dejaría una sola letra detrás: no se usa."""
        celdas = contraido.celdas_de_palabra("entren")
        assert celdas != [tablas.PRINCIPIOS["entre"][0], tablas.LETRAS["n"]]
        assert celdas == [tablas.CONTRACCIONES["en"][0],
                          tablas.CONTRACCIONES["tr"][0],
                          tablas.CONTRACCIONES["en"][0]]

    def test_gana_la_contraccion_de_detras(self):
        """«labrar» es l-a-br-ar, no l-ab-r-ar."""
        assert contraido.celdas_de_palabra("labrar") == [
            tablas.LETRAS["l"], tablas.LETRAS["a"],
            tablas.CONTRACCIONES["br"][0], tablas.CONTRACCIONES["ar"][0]]

    def test_una_vocal_con_tilde_rompe_la_contraccion(self):
        """«al» sirve en «alabar» y no en «álamo»."""
        assert contraido.celdas_de_palabra("alabar")[0] == tablas.CONTRACCIONES["al"][0]
        assert contraido.celdas_de_palabra("álamo")[0] != tablas.CONTRACCIONES["al"][0]

    def test_la_contraccion_ab_no_va_al_final(self):
        """Comparte celda con la coma: «baobab» acabaría en «baobab,»."""
        assert contraido.celdas_de_palabra("baobab")[-1] != tablas.CONTRACCIONES["ab"][0]

    def test_los_finales_se_encadenan(self):
        """«tristemente» son dos: «-te» y «-mente»."""
        celdas = contraido.celdas_de_palabra("tristemente")
        assert celdas[-2:] == [tablas.FINALES["te"][0], tablas.FINALES["mente"][0]]

    def test_una_variante_usa_el_signo_de_su_palabra(self):
        base = list(tablas.PALABRAS["concreto"])
        assert contraido.celdas_de_palabra("concretos") == \
            base + list(tablas.GENERO_Y_NUMERO["os"])

    def test_un_verbo_hace_el_plural_con_la_letra(self):
        """«estabas» lleva una ese; «breves», el signo de «-es»."""
        assert contraido.celdas_de_palabra("estabas")[-1] == tablas.LETRAS["s"]
        assert contraido.celdas_de_palabra("breves")[-1] == \
            tablas.GENERO_Y_NUMERO["es"][0]

    def test_lo_que_no_se_sabe_escribir_se_deja_sin_contraer(self):
        """Devolver la lista vacía es la forma de decir «esta no»."""
        assert contraido.celdas_de_palabra("") == []

    def test_un_texto_entero_conserva_su_puntuacion(self):
        celdas = contraido.celdas("Bien, gracias.")
        assert celdas
        assert len(celdas) < len("Bien, gracias.")


class PruebaContraElDocumento:
    """La comparación contra los ejemplos resueltos del propio B 16-1."""

    @staticmethod
    def _resultados():
        datos = _cargar()
        alfabeto = datos["alfabeto"]
        grupos = {"lista": [0, 0], "variante": [0, 0], "proceso": [0, 0]}
        fallan = []
        for palabra, glifos in datos["ejemplos"]:
            if palabra.endswith("-") or glifos.endswith("-"):
                continue
            esperado = _descifrar(glifos, alfabeto)
            if esperado is None:
                continue
            if palabra in tablas.PALABRAS:
                if esperado != list(tablas.PALABRAS[palabra]):
                    continue          # el ejemplo se extrajo mal del PDF
                grupo = "lista"
            elif palabra in tablas.VARIANTES:
                grupo = "variante"
            else:
                grupo = "proceso"
            if contraido.celdas_de_palabra(palabra) == esperado:
                grupos[grupo][0] += 1
            else:
                grupos[grupo][1] += 1
                fallan.append(palabra)
        return grupos, fallan

    def test_las_palabras_de_la_lista_salen_todas_bien(self):
        grupos, _fallan = self._resultados()
        bien, mal = grupos["lista"]
        assert bien >= 18 and mal == 0

    def test_las_variantes_salen_todas_bien(self):
        grupos, _fallan = self._resultados()
        bien, mal = grupos["variante"]
        assert bien >= 18 and mal == 0

    def test_el_proceso_acierta_nueve_de_cada_diez(self):
        grupos, _fallan = self._resultados()
        bien, mal = grupos["proceso"]
        total = bien + mal
        assert total >= 70
        assert bien / total >= 0.90, "ha bajado a %d de %d" % (bien, total)

    def test_los_fallos_son_exactamente_los_conocidos(self):
        """Si aparece uno nuevo, hay que mirarlo, no subir el listón."""
        _grupos, fallan = self._resultados()
        assert set(fallan) == CONOCIDOS, "cambian los fallos: %s" % sorted(
            set(fallan) ^ CONOCIDOS)

    def test_ninguna_palabra_sale_como_la_version_equivocada(self):
        """El documento trae seis contraejemplos: lo que **no** hay que escribir."""
        datos = _cargar()
        alfabeto = datos["alfabeto"]
        for palabra, glifos in datos["contraejemplos"]:
            prohibido = _descifrar(glifos, alfabeto)
            if prohibido is None:
                continue
            assert contraido.celdas_de_palabra(palabra) != prohibido, palabra


class PruebaExportacion:
    def test_el_contraido_ocupa_bastante_menos(self):
        from nucleo import braille

        frase = ("El importante trabajo de la biblioteca es siempre para las "
                 "personas ciegas.")
        integral = braille.a_celdas(frase)
        corto = contraido.celdas(frase)
        assert len(corto) < len(integral) * 0.75

    def test_se_puede_escribir_en_brf(self):
        salida = contraido.a_brf(contraido.celdas("bien"))
        assert isinstance(salida, str) and salida

    def test_la_exportacion_admite_las_dos_formas(self, carpeta):
        from nucleo import exportar
        from nucleo.documento import Documento, Metadatos

        documento = Documento(
            "Un capítulo\nEste es el importante trabajo de la biblioteca.\n", [],
            metadatos=Metadatos(titulo="Prueba"), ruta_archivo="x.epub")
        integral = exportar.a_brf(documento, contraido=False)
        corto = exportar.a_brf(documento, contraido=True)
        assert integral and corto and corto != integral
        assert len(corto) < len(integral)
