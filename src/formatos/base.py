# -*- coding: utf-8 -*-
"""Interfaz común de los analizadores de formato y su registro.

La aplicación está pensada para admitir más formatos en el futuro (PDF, MOBI,
DOCX, texto plano...).  Para añadir uno basta con:

1. Escribir una clase que herede de :class:`Analizador`.
2. Registrarla con :func:`registrar`.

El resto de la aplicación no cambia: pide un documento a :func:`analizar` y
recibe siempre un :class:`~nucleo.documento.Documento`, sea cual sea el
formato de origen.
"""

from __future__ import annotations

import os
from pathlib import Path

from nucleo.documento import Documento
from nucleo.idioma import _
from nucleo.registro import obtener_registro

log = obtener_registro(__name__)


class ErrorFormato(Exception):
    """El archivo no se puede leer: está dañado, protegido o no es válido.

    El mensaje de esta excepción se muestra tal cual al usuario, así que debe
    estar redactado en español y ser comprensible.
    """


class Cancelado(Exception):
    """El usuario ha cancelado la operación.

    No es un error: quien la lance no debe anotarlo como fallo ni enseñar un
    mensaje de avería, solo dejar las cosas como estaban.
    """


class Progreso:
    """Cuenta cómo va una operación larga y deja cancelarla.

    Abrir un libro puede tardar desde una décima —un EPUB normal— hasta varios
    minutos —un PDF escaneado que hay que reconocer página a página—.  Sin algo
    así, esos minutos son un silencio en el que no se sabe si el programa está
    trabajando o se ha colgado, y no hay forma de echarse atrás.

    Los analizadores llaman a :meth:`paso` mientras avanzan.  Quien pide el
    análisis pasa una función ``aviso(hecho, total, mensaje)`` que dibuja el
    progreso, y puede pedir la cancelación desde otro hilo con :meth:`cancelar`;
    el análisis se entera en el paso siguiente y para.

    :param aviso: Función a la que se le cuenta cada paso.  Se llama **desde el
                  hilo del análisis**, así que si dibuja algo tiene que
                  aplazarlo al hilo de la interfaz.
    """

    __slots__ = ("_aviso", "_cancelado")

    def __init__(self, aviso=None) -> None:
        self._aviso = aviso
        self._cancelado = False

    def conectar(self, aviso) -> None:
        """Pone quién recibe los avisos, después de haberlo creado.

        Hace falta porque el canal y la ventana que lo dibuja se necesitan el
        uno al otro: la ventana quiere el ``cancelar`` del canal y el canal
        quiere el ``avanzar`` de la ventana.
        """
        self._aviso = aviso

    def paso(self, hecho: int, total: int, mensaje: str = "") -> None:
        """Anota un paso del avance.

        :raises Cancelado: Si mientras tanto se ha pedido cancelar.
        """
        if self._cancelado:
            raise Cancelado()
        if self._aviso is not None:
            self._aviso(hecho, total, mensaje)

    def cancelar(self) -> None:
        """Pide que la operación pare.  Se puede llamar desde otro hilo."""
        self._cancelado = True

    @property
    def cancelado(self) -> bool:
        """Indica si se ha pedido cancelar."""
        return self._cancelado


class OpcionesAnalisis:
    """Ajustes que influyen en cómo se convierte un documento a texto.

    :param tablas_en_linea: Volcar las tablas completas o solo un marcador.
    :param anunciar_imagenes_sin_texto: Incluir las imágenes que no tienen
                                        texto alternativo.
    :param solo_articulo: En una página web guardada, quedarse solo con el
                          artículo y tirar los menús, los avisos de galletas y
                          las columnas laterales.  Cambia el texto que sale, así
                          que forma parte de la firma.
    :param estructura_pdf: Aprovechar el árbol de estructura de los PDF
                           etiquetados.  Cambia por completo el texto que sale
                           de un PDF accesible, así que forma parte de la firma
                           y hace que el documento se vuelva a analizar.
    :param geometria_pdf: Deducir la estructura de los PDF **sin** etiquetar
                          midiendo cómo están escritos.  Cambia el texto igual
                          de radicalmente que la opción anterior —con ella un
                          PDF corriente sale con encabezados y tablas, y sin
                          ella, como texto corrido—, así que también forma
                          parte de la firma.
    :param progreso: Canal por el que el analizador cuenta cómo va y por el que
                     se le puede pedir que pare.  No forma parte de la firma:
                     no cambia el resultado, así que no debe invalidar la caché.
    """

    __slots__ = ("tablas_en_linea", "anunciar_imagenes_sin_texto", "estructura_pdf",
                 "geometria_pdf", "marcar_llamadas_de_nota", "solo_articulo",
                 "progreso")

    def __init__(self, tablas_en_linea: bool = True, anunciar_imagenes_sin_texto: bool = True,
                 estructura_pdf: bool = True, geometria_pdf: bool = True,
                 marcar_llamadas_de_nota: bool = False, solo_articulo: bool = True,
                 progreso: "Progreso | None" = None) -> None:
        self.tablas_en_linea = tablas_en_linea
        self.anunciar_imagenes_sin_texto = anunciar_imagenes_sin_texto
        self.estructura_pdf = estructura_pdf
        self.geometria_pdf = geometria_pdf
        self.marcar_llamadas_de_nota = marcar_llamadas_de_nota
        self.solo_articulo = solo_articulo
        self.progreso = progreso or Progreso()

    def firma(self) -> str:
        """Cadena que identifica esta combinación de ajustes.

        Forma parte de la clave de la caché: si el usuario cambia el modo de
        las tablas, el documento debe volver a analizarse.
        """
        firma = "t%d-i%d" % (int(self.tablas_en_linea),
                             int(self.anunciar_imagenes_sin_texto))
        # Solo se añade cuando está apagado, que es lo raro: así las firmas de
        # los documentos que no son PDF siguen siendo las de siempre y no se
        # tira a la basura la caché de toda la biblioteca por este ajuste.
        if not self.estructura_pdf:
            firma += "-sinestructura"
        if not self.geometria_pdf:
            firma += "-singeometria"
        if self.marcar_llamadas_de_nota:
            firma += "-connotas"
        if not self.solo_articulo:
            firma += "-paginaentera"
        return firma


class Analizador:
    """Clase base de todos los analizadores de formato."""

    #: Extensiones que reconoce este analizador, en minúsculas y con punto.
    extensiones: tuple[str, ...] = ()

    #: Nombre del formato tal como se muestra en el diálogo de apertura.
    descripcion: str = ""

    def reconoce(self, ruta: str | os.PathLike) -> bool:
        """Dice si este analizador reclama el archivo, mire lo que mire la extensión.

        Se pregunta **antes** que el reparto por extensión, y sirve para los
        formatos que no se distinguen por el nombre.  El caso real es DAISY
        2.02: se abre por su ``ncc.html``, que es un ``.html`` como otro
        cualquiera, y lo que lo delata es lo que tiene al lado en la carpeta.

        Tiene que ser barato: se llama al abrir cualquier archivo.
        """
        return False

    def analizar(self, ruta: str | os.PathLike, opciones: OpcionesAnalisis) -> Documento:
        """Analiza un archivo y devuelve el documento resultante."""
        raise NotImplementedError

    def extraer_recurso(self, ruta: str | os.PathLike, interna: str) -> bytes | None:
        """Extrae un archivo interno del documento (una imagen, por ejemplo).

        Devuelve ``None`` si el formato no contiene recursos o no existe.
        """
        return None


#: Analizadores registrados, indexados por extensión.
_REGISTRO: dict[str, Analizador] = {}


#: Analizadores que saben reconocer lo suyo por sí mismos, en el orden en que
#: se les pregunta.  Son pocos y su ``reconoce`` es barato.
_RECONOCEDORES: list[Analizador] = []


def registrar(analizador: Analizador) -> None:
    """Da de alta un analizador para las extensiones que declara."""
    for extension in analizador.extensiones:
        _REGISTRO[extension.lower()] = analizador
    if type(analizador).reconoce is not Analizador.reconoce:
        _RECONOCEDORES.append(analizador)
    log.debug("Analizador registrado para %s", ", ".join(analizador.extensiones))


def analizador_para(ruta: str | os.PathLike) -> Analizador | None:
    """Devuelve el analizador adecuado para un archivo, o ``None``.

    Primero se pregunta a los que saben reconocer lo suyo mirando la carpeta, y
    solo después se reparte por extensión.  Sin ese primer paso, el ``ncc.html``
    de un libro DAISY 2.02 lo cogería el analizador de HTML y el libro se
    abriría como una página web con el índice dentro y nada más.
    """
    for analizador in _RECONOCEDORES:
        try:
            if analizador.reconoce(ruta):
                return analizador
        except Exception as error:
            log.debug("El reconocedor %s ha fallado: %s", type(analizador).__name__, error)
    return _REGISTRO.get(Path(ruta).suffix.lower())


def extensiones_admitidas() -> list[str]:
    """Lista ordenada de todas las extensiones que la aplicación abre."""
    return sorted(_REGISTRO)


def filtro_dialogo() -> str:
    """Construye el filtro de archivos del diálogo «Abrir» de wxPython."""
    vistos: dict[str, Analizador] = {}
    for extension, analizador in _REGISTRO.items():
        vistos.setdefault(analizador.descripcion, analizador)
    partes = []
    todas = ";".join("*" + extension for extension in extensiones_admitidas())
    partes.append(_("Todos los documentos admitidos (%s)|%s") % (todas, todas))
    for descripcion, analizador in vistos.items():
        patrones = ";".join("*" + extension for extension in analizador.extensiones)
        partes.append("%s (%s)|%s" % (descripcion, patrones, patrones))
    partes.append(_("Todos los archivos (*.*)|*.*"))
    return "|".join(partes)


def analizar(ruta: str | os.PathLike, opciones: OpcionesAnalisis | None = None) -> Documento:
    """Analiza un archivo con el analizador que le corresponda.

    :raises ErrorFormato: Si no hay ningún analizador para esa extensión o si
                          el archivo no se puede leer.
    """
    destino = Path(ruta)
    if not destino.exists():
        raise ErrorFormato(_("El archivo no existe: %s") % destino)
    elegido = analizador_para(destino)
    if elegido is None:
        raise ErrorFormato(
            _("Todavía no se admite el formato «%s». Formatos disponibles: %s")
            % (destino.suffix or _("sin extensión"), ", ".join(extensiones_admitidas()))
        )
    return elegido.analizar(destino, opciones or OpcionesAnalisis())


def extraer_recurso(ruta: str | os.PathLike, interna: str) -> bytes | None:
    """Extrae un recurso interno usando el analizador del formato."""
    elegido = analizador_para(ruta)
    if elegido is None:
        return None
    return elegido.extraer_recurso(ruta, interna)
