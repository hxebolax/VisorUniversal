# -*- coding: utf-8 -*-
"""Una sesión de lectura: un documento abierto y todo lo que le pertenece.

Hasta ahora la ventana principal guardaba directamente el documento, su
buscador, sus marcadores, su cronómetro y su panel de lectura, porque solo
podía haber uno abierto a la vez.  Con las pestañas ya no: puede haber cinco
documentos abiertos y **cada uno tiene lo suyo**, incluida la posición por la
que va la lectura, que es justamente lo que hace útiles las pestañas —abrir el
manual al lado del libro, comparar dos informes— y lo que se pierde si el
programa se limita a cambiar el texto de la pantalla.

Una :class:`Sesion` es ese conjunto.  La ventana sigue hablando de
``self.documento`` o ``self.marcadores`` como siempre, pero ahora esos nombres
son propiedades que van a parar a la sesión activa.  El resto del programa no
se ha enterado del cambio, que era justo la idea: mil líneas de ventana no
tenían por qué saber que ahora hay pestañas.
"""

from __future__ import annotations

from pathlib import Path

from nucleo import descripciones, estadisticas
from nucleo.idioma import _


class Sesion:
    """Un documento abierto, con su panel de lectura y su estado.

    :param panel: Panel de lectura propio de esta sesión.  Cada pestaña tiene
                  el suyo, y con él se lleva su posición, su historial de
                  saltos y su ventana de texto cargada; volver a una pestaña es
                  encontrarla como se dejó, sin recargar nada.
    """

    __slots__ = ("panel", "documento", "ruta", "cronometro", "buscador", "marcadores",
                 "descripciones", "libro_daisy", "ultima_busqueda", "linea_descrita",
                 "_estadisticas", "huella_archivo")

    def __init__(self, panel) -> None:
        self.panel = panel
        self.documento = None
        self.ruta = ""
        #: Fecha y tamaño que tenía el archivo al abrirlo.  Con esto se sabe si
        #: ha cambiado en el disco desde entonces, que es lo que decide si al
        #: volver a pedirlo hay que releerlo o basta con ir a su pestaña.
        self.huella_archivo = None
        #: Cronómetro de lectura.  Se crea vacío para que el cursor pueda
        #: moverse por la pantalla de bienvenida sin que haya que comprobar en
        #: cada paso si existe.
        self.cronometro = estadisticas.Cronometro()
        self.buscador = None
        self.marcadores: list = []
        self.descripciones = descripciones.Coleccion()
        self.libro_daisy = None
        self.ultima_busqueda = None
        #: Última línea cuya descripción guardada se ha anunciado, para no
        #: repetirla a cada movimiento del cursor dentro del mismo párrafo.
        self.linea_descrita = -1
        self._estadisticas = None

    @property
    def vacia(self) -> bool:
        """Indica si la pestaña no tiene ningún documento dentro."""
        return self.documento is None

    @property
    def recuentos(self):
        """Palabras, líneas y caracteres del documento, contados una sola vez.

        La barra de estado los enseña mientras se lee, y contar las palabras de
        un libro de treinta millones de caracteres en cada movimiento del
        cursor dejaría el programa inservible.  Se cuentan al pedirlos por
        primera vez y se guardan hasta que cambie el documento.
        """
        if self.documento is None:
            return None
        if self._estadisticas is None:
            self._estadisticas = self.documento.estadisticas()
        return self._estadisticas

    def olvidar_recuentos(self) -> None:
        """Tira los recuentos guardados: el documento ha cambiado."""
        self._estadisticas = None

    def titulo(self) -> str:
        """Rótulo con el que se nombra esta pestaña.

        Se usa el título del documento, que es lo que el lector reconoce; si el
        archivo no trae ninguno queda su nombre, y si no hay documento, la
        palabra que dice que la pestaña está libre.
        """
        if self.documento is None:
            return _("(Vacía)")
        titulo = (self.documento.metadatos.titulo or "").strip()
        if not titulo and self.ruta:
            titulo = Path(self.ruta).stem
        return titulo or _("(Sin título)")

    def rotulo_corto(self, limite: int = 28) -> str:
        """Título recortado, para que quepa en la lengüeta de la pestaña.

        El título entero se sigue anunciando en el menú de pestañas y en el
        diálogo de cambio rápido: aquí solo se recorta lo que se dibuja, porque
        una lengüeta con el título completo de un informe anual dejaría sin
        sitio a las demás.
        """
        titulo = self.titulo()
        if len(titulo) <= limite:
            return titulo
        return titulo[:limite - 1].rstrip() + "…"
