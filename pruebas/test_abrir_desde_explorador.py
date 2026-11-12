# -*- coding: utf-8 -*-
"""Abrir un libro desde el explorador: qué pasa con lo que ya había.

Son tres situaciones distintas y hasta ahora dos se resolvían mal:

1. El programa **cerrado**, con la sesión pedida. Se abría el libro y se perdían
   las pestañas que quedaron abiertas.
2. El libro **ya estaba** en la sesión anterior. Se abría dos veces: una al
   restaurar y otra por haberlo pedido.
3. El libro **ya está abierto** en una pestaña. Se abría una segunda con el
   mismo documento, y a partir de ahí dos sitios donde marcar y guardar la
   posición del mismo libro.

Se prueban las decisiones, no la ventana: qué documentos se ponen en la cola y en
qué orden, y si se reconoce lo que ya estaba. Levantar la interfaz para esto
haría una prueba lenta que además fallaría por motivos que no son estos.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from interfaz.ventana import _ha_cambiado_en_disco, _misma_ruta  # noqa: E402


class SesionDeMentira:
    """Lo justo de una sesión para estas comprobaciones."""

    def __init__(self, ruta="", huella=None):
        self.ruta = str(ruta)
        self.huella_archivo = huella


class PruebaMismaRuta:
    """Reconocer que dos rutas son el mismo archivo."""

    def test_la_misma_escrita_de_dos_formas(self, tmp_path):
        uno = tmp_path / "libro.epub"
        uno.write_text("x", encoding="utf-8")
        assert _misma_ruta(str(uno), str(uno).replace("\\", "/"))

    def test_mayusculas_y_minusculas(self, tmp_path):
        """En Windows da igual, y el explorador puede mandarla de cualquier forma."""
        uno = tmp_path / "Libro.epub"
        uno.write_text("x", encoding="utf-8")
        assert _misma_ruta(str(uno), str(uno).upper())

    def test_dos_archivos_distintos_no_son_el_mismo(self, tmp_path):
        uno = tmp_path / "uno.epub"
        otro = tmp_path / "otro.epub"
        for cual in (uno, otro):
            cual.write_text("x", encoding="utf-8")
        assert not _misma_ruta(str(uno), str(otro))

    def test_una_ruta_imposible_no_revienta(self):
        """Comparar no puede fallar: se llama antes de comprobar que existe."""
        assert not _misma_ruta("Z:/no/existe.epub", "Y:/tampoco.epub")


class PruebaHaCambiado:
    """Saber si el archivo es el mismo que se abrió."""

    def test_sin_tocar_nada_no_ha_cambiado(self, tmp_path):
        libro = tmp_path / "libro.epub"
        libro.write_text("contenido", encoding="utf-8")
        estado = libro.stat()
        sesion = SesionDeMentira(libro, (estado.st_mtime_ns, estado.st_size))
        assert not _ha_cambiado_en_disco(sesion)

    def test_reescribirlo_cuenta_como_cambio(self, tmp_path):
        """Es el caso de verdad: alguien vuelve a exportar el documento."""
        libro = tmp_path / "libro.epub"
        libro.write_text("contenido", encoding="utf-8")
        estado = libro.stat()
        sesion = SesionDeMentira(libro, (estado.st_mtime_ns, estado.st_size))
        libro.write_text("contenido distinto y más largo", encoding="utf-8")
        assert _ha_cambiado_en_disco(sesion)

    def test_sin_huella_se_da_por_bueno(self, tmp_path):
        """Releer por si acaso, cada vez, sería peor que el problema."""
        libro = tmp_path / "libro.epub"
        libro.write_text("x", encoding="utf-8")
        assert not _ha_cambiado_en_disco(SesionDeMentira(libro, None))

    def test_si_el_archivo_ya_no_esta_no_se_dice_que_cambio(self, tmp_path):
        """Que se haya borrado es otro problema, y lo avisa quien lo abre."""
        sesion = SesionDeMentira(tmp_path / "se_fue.epub", (1, 1))
        assert not _ha_cambiado_en_disco(sesion)


class PruebaLaCola:
    """Qué se restaura y en qué orden al arrancar con un libro pedido.

    Se comprueba la decisión tal como la toma la ventana, sin levantarla: qué
    lista de documentos queda por abrir y cuál se pone delante.
    """

    @staticmethod
    def _cola(guardados, activo, ademas):
        """Repite lo que hace la ventana al preparar la restauración."""
        pendientes = list(guardados)
        if ademas:
            iguales = [numero for numero, uno in enumerate(pendientes)
                       if _misma_ruta(uno, ademas)]
            if iguales:
                activo = iguales[0]
            else:
                pendientes.append(ademas)
                activo = len(pendientes) - 1
        return pendientes, max(0, min(activo, len(pendientes) - 1))

    def test_el_libro_pedido_se_suma_y_queda_delante(self, tmp_path):
        guardados = [str(tmp_path / ("uno%d.epub" % numero)) for numero in range(3)]
        nuevo = str(tmp_path / "nuevo.epub")
        cola, activo = self._cola(guardados, 1, nuevo)
        assert len(cola) == 4
        assert cola[-1] == nuevo
        assert cola[activo] == nuevo

    def test_si_ya_estaba_no_se_abre_dos_veces(self, tmp_path):
        """Y se queda delante la pestaña que ya lo tenía."""
        guardados = [str(tmp_path / ("uno%d.epub" % numero)) for numero in range(3)]
        cola, activo = self._cola(guardados, 0, guardados[2])
        assert len(cola) == 3
        assert cola[activo] == guardados[2]

    def test_sin_libro_pedido_manda_el_que_estaba_delante(self, tmp_path):
        guardados = [str(tmp_path / ("uno%d.epub" % numero)) for numero in range(3)]
        cola, activo = self._cola(guardados, 2, "")
        assert cola == guardados
        assert activo == 2

    def test_sin_nada_guardado_queda_solo_el_pedido(self, tmp_path):
        nuevo = str(tmp_path / "nuevo.epub")
        cola, activo = self._cola([], 0, nuevo)
        assert cola == [nuevo]
        assert activo == 0
