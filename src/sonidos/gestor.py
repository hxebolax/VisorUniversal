# -*- coding: utf-8 -*-
"""Reproducción de los sonidos de navegación.

El gestor mantiene en memoria un objeto de sonido por cada archivo WAV de
``data/sonidos`` y los reproduce de forma asíncrona, de modo que la lectura
nunca se detiene esperando a que termine un pitido.

La correspondencia entre lo que hay en el texto y el sonido que se oye está
en :data:`SONIDO_POR_MARCA`.  Al desplazarse por el libro, la aplicación
consulta qué elementos empiezan en la línea a la que ha llegado el cursor y
pide aquí el sonido correspondiente.  Cuando en una misma línea coinciden
varios elementos (por ejemplo, un encabezado que además contiene un enlace)
se reproduce el de mayor prioridad, para no encadenar pitidos.
"""

from __future__ import annotations

from pathlib import Path

from nucleo import rutas
from nucleo.marcas import ORDEN_DE_INTERES, Marca, TipoMarca
from nucleo.registro import obtener_registro, registrar_excepcion

from . import generador

log = obtener_registro(__name__)

#: Sonido que corresponde a cada tipo de marca.
SONIDO_POR_MARCA: dict[TipoMarca, str] = {
    TipoMarca.ENCABEZADO1: "encabezado1",
    TipoMarca.ENCABEZADO2: "encabezado2",
    TipoMarca.ENCABEZADO3: "encabezado3",
    TipoMarca.ENCABEZADO4: "encabezado4",
    TipoMarca.ENCABEZADO5: "encabezado5",
    TipoMarca.ENCABEZADO6: "encabezado6",
    TipoMarca.SALTO_PAGINA: "pagina",
    TipoMarca.SALTO_SECCION: "seccion",
    TipoMarca.ENLACE: "enlace",
    TipoMarca.LISTA: "lista",
    TipoMarca.ELEMENTO_LISTA: "elemento_lista",
    TipoMarca.TABLA: "tabla",
    TipoMarca.SEPARADOR: "separador",
    TipoMarca.IMAGEN: "imagen",
    TipoMarca.FIGURA: "figura",
    TipoMarca.CITA: "cita",
    TipoMarca.FORMULA: "formula",
    # La llamada de nota suena como la nota del usuario: las dos son «aquí hay
    # algo escrito aparte que puedes ir a leer».
    TipoMarca.NOTA_PIE: "nota",
    TipoMarca.CODIGO: "codigo",
}

#: Orden en el que se elige el pitido de una línea.  Se reproduce únicamente el
#: primero que esté presente: un acorde de pitidos no dice nada, y en un libro
#: anotado casi todas las líneas llevan dos o tres elementos.
#:
#: La lista vive en :mod:`nucleo.marcas` porque no es una decisión sobre los
#: sonidos, sino sobre los elementos: cuáles merece la pena señalar y cuál dice
#: más.  La voz usa exactamente la misma, y así las dos formas de avisar no
#: pueden acabar diciendo cosas distintas.
PRIORIDAD: tuple[TipoMarca, ...] = ORDEN_DE_INTERES


class GestorSonidos:
    """Carga, regenera y reproduce los sonidos de la aplicación.

    :param activado: Si los sonidos deben oírse.
    :param volumen: Volumen de 0 a 100.
    """

    def __init__(self, activado: bool = True, volumen: int = 70) -> None:
        self.activado = activado
        self._volumen = max(0, min(100, volumen))
        self._carpeta: Path = rutas.ruta_sonidos()
        self._sonidos: dict[str, object] = {}
        self._disponible = True
        self.preparar()

    # -- preparación ---------------------------------------------------------

    def preparar(self, forzar: bool = False) -> None:
        """Genera los archivos que falten y los carga en memoria.

        :param forzar: Regenerar todos los archivos aunque ya existan (es lo
                       que hay que hacer al cambiar el volumen).
        """
        try:
            if forzar or generador.faltan_sonidos(self._carpeta):
                generador.generar(self._carpeta, self._volumen)
            self._cargar()
        except Exception as error:
            registrar_excepcion(log, "No se han podido preparar los sonidos", error)
            self._disponible = False

    def _cargar(self) -> None:
        """Crea los objetos de sonido de wxPython a partir de los archivos."""
        try:
            import wx.adv
        except ImportError:  # pragma: no cover - entorno sin interfaz gráfica
            self._disponible = False
            log.warning("wx.adv no está disponible: los sonidos quedan desactivados")
            return
        self._sonidos.clear()
        cargados = 0
        for nombre in generador.NOMBRES:
            archivo = self._carpeta / (nombre + ".wav")
            if not archivo.exists():
                continue
            sonido = wx.adv.Sound(str(archivo))
            if sonido.IsOk():
                self._sonidos[nombre] = sonido
                cargados += 1
            else:
                log.warning("El archivo de sonido %s no se ha podido cargar", archivo.name)
        self._disponible = cargados > 0
        log.debug("Sonidos cargados: %d de %d", cargados, len(generador.NOMBRES))

    # -- ajustes -------------------------------------------------------------

    @property
    def volumen(self) -> int:
        """Volumen actual, de 0 a 100."""
        return self._volumen

    def establecer_volumen(self, volumen: int) -> None:
        """Cambia el volumen regenerando los archivos con la nueva amplitud."""
        nuevo = max(0, min(100, int(volumen)))
        if nuevo == self._volumen:
            return
        self._volumen = nuevo
        self.preparar(forzar=True)

    # -- reproducción --------------------------------------------------------

    def reproducir(self, nombre: str) -> None:
        """Reproduce un sonido por su nombre, sin bloquear la aplicación."""
        if not self.activado or not self._disponible:
            return
        sonido = self._sonidos.get(nombre)
        if sonido is None:
            log.debug("Sonido desconocido: %s", nombre)
            return
        try:
            import wx.adv
            sonido.Play(wx.adv.SOUND_ASYNC)
        except Exception as error:
            log.debug("No se ha podido reproducir %s: %s", nombre, error)

    def reproducir_marca(self, tipo: TipoMarca) -> None:
        """Reproduce el sonido correspondiente a un tipo de elemento."""
        nombre = SONIDO_POR_MARCA.get(tipo)
        if nombre:
            self.reproducir(nombre)

    def reproducir_para_elementos(self, elementos: list[Marca]) -> TipoMarca | None:
        """Reproduce un único sonido para los elementos de una línea.

        Devuelve el tipo elegido (o ``None`` si no había ninguno), para que
        quien llama pueda anunciarlo también por texto si lo desea.
        """
        if not elementos:
            return None
        presentes = {marca.tipo for marca in elementos}
        for tipo in PRIORIDAD:
            if tipo in presentes:
                self.reproducir_marca(tipo)
                return tipo
        return None

    def sonidos_disponibles(self) -> list[str]:
        """Nombres de los sonidos cargados, para el diálogo de opciones."""
        return sorted(self._sonidos)
