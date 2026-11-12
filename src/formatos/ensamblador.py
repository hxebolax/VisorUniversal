# -*- coding: utf-8 -*-
"""Montaje de un documento a partir de secciones en XHTML.

Casi todos los formatos que abre el programa acaban siendo lo mismo: una
sucesión de trozos de XHTML.  Un EPUB los trae ya así; un DOCX, un ODT, un FB2
o un libro DAISY se convierten a XHTML con unas pocas reglas propias de cada
uno.  A partir de ahí el trabajo es idéntico —convertir cada trozo a texto,
recolocar las marcas y sumar los desplazamientos— y **estaba escrito solo dentro
del analizador de EPUB**.

Aquí está ese trabajo una sola vez.  Un analizador nuevo se reduce a lo suyo:
sacar del archivo los trozos de XHTML y los metadatos, y llamar a :func:`montar`.

Es lo que hace que añadir un formato sea escribir un módulo pequeño en lugar de
repetir doscientas líneas delicadas de aritmética de posiciones.
"""

from __future__ import annotations

import html as _html
import re
from pathlib import Path

from nucleo import accesibilidad
from nucleo.documento import Documento, ElementoIndice, Metadatos, Seccion
from nucleo.idioma import _
from nucleo.marcas import Marca, TipoMarca
from nucleo.registro import obtener_registro, registrar_excepcion

from .base import OpcionesAnalisis
from .conversor import ConversorXHTML

log = obtener_registro(__name__)

#: Tipos de marca cuya referencia es una ruta dentro del documento y que, por
#: tanto, hay que dejar apuntando al recurso correcto.
TIPOS_CON_RUTA = (TipoMarca.IMAGEN, TipoMarca.FIGURA, TipoMarca.ENLACE)

#: Encabezados a partir de los cuales se construye el índice cuando el formato
#: no trae uno propio.
_NIVEL_DE = {
    TipoMarca.ENCABEZADO1: 1, TipoMarca.ENCABEZADO2: 2, TipoMarca.ENCABEZADO3: 3,
    TipoMarca.ENCABEZADO4: 4, TipoMarca.ENCABEZADO5: 5, TipoMarca.ENCABEZADO6: 6,
}


def escapar(texto: str) -> str:
    """Deja un texto listo para meterlo dentro del XHTML que se va a convertir."""
    return _html.escape(texto or "", quote=True)


def envolver(cuerpo: str, titulo: str = "") -> bytes:
    """Envuelve un cuerpo en un documento XHTML completo, listo para convertir."""
    cabecera = "<title>%s</title>" % escapar(titulo) if titulo else ""
    return ("<?xml version=\"1.0\" encoding=\"utf-8\"?>"
            "<html xmlns=\"http://www.w3.org/1999/xhtml\"><head>"
            "<meta charset=\"utf-8\"/>%s</head><body>%s</body></html>"
            % (cabecera, cuerpo)).encode("utf-8")


def parrafos_de_texto(texto: str) -> str:
    """Convierte texto plano en párrafos XHTML.

    Las líneas en blanco separan párrafos; dentro de un párrafo, los saltos de
    línea sueltos se respetan solo si el bloque parece verso o lista, porque en
    un texto corrido son un artefacto del ancho de línea del archivo, no una
    decisión del autor.
    """
    bloques = re.split(r"\n\s*\n", (texto or "").replace("\r\n", "\n").replace("\r", "\n"))
    partes = []
    for bloque in bloques:
        lineas = [linea.rstrip() for linea in bloque.split("\n") if linea.strip()]
        if not lineas:
            continue
        cortas = sum(1 for linea in lineas if len(linea) < 60)
        if len(lineas) > 1 and cortas >= len(lineas) * 0.8:
            # Verso, lista o tabla de contenidos: cada línea va aparte.
            partes.append("<p>%s</p>" % "<br/>".join(escapar(linea) for linea in lineas))
        else:
            partes.append("<p>%s</p>" % escapar(" ".join(lineas)))
    return "".join(partes) or "<p></p>"


def indice_desde_encabezados(marcas, texto: str) -> list[ElementoIndice]:
    """Construye un índice con los encabezados, para formatos que no traen uno.

    Es lo que convierte un DOCX o un PDF en algo navegable: sin índice propio,
    el árbol de «Contenido del libro» sale de su propia estructura de títulos.
    """
    raices: list[ElementoIndice] = []
    pila: list[tuple[int, ElementoIndice]] = []
    for marca in marcas:
        nivel = _NIVEL_DE.get(marca.tipo)
        if nivel is None:
            continue
        titulo = (marca.texto or "").strip() or _("(sin título)")
        entrada = ElementoIndice(titulo[:200], marca.posicion)
        while pila and pila[-1][0] >= nivel:
            pila.pop()
        if pila:
            pila[-1][1].hijos.append(entrada)
        else:
            raices.append(entrada)
        pila.append((nivel, entrada))
    return raices


def montar(secciones, metadatos: Metadatos, ruta, opciones: OpcionesAnalisis,
           indice: list[ElementoIndice] | None = None,
           resolver_ruta=None) -> Documento:
    """Convierte una lista de secciones XHTML en un :class:`Documento`.

    :param secciones: Pares ``(ruta_lógica, datos_xhtml)``.  La ruta lógica
                      identifica la sección y es lo que se guarda en las marcas
                      de imagen y de enlace.
    :param metadatos: Datos del libro ya extraídos del archivo.
    :param ruta: Archivo de origen, para el documento resultante.
    :param opciones: Ajustes de conversión.
    :param indice: Índice propio del formato.  Si no se pasa, se construye con
                   los encabezados.
    :param resolver_ruta: Función ``(seccion, referencia) -> referencia`` para
                          convertir las rutas relativas de imágenes y enlaces
                          en rutas absolutas dentro del documento.
    """
    conversor = ConversorXHTML(
        tablas_en_linea=opciones.tablas_en_linea,
        anunciar_imagenes_sin_texto=opciones.anunciar_imagenes_sin_texto,
        marcar_llamadas_de_nota=getattr(opciones, "marcar_llamadas_de_nota", False),
    )
    partes: list[str] = []
    marcas: list[Marca] = []
    posiciones_id: dict[str, int] = {}
    lista_secciones: list[Seccion] = []
    paginas: list[tuple[int, str]] = []
    desplazamiento = 0

    total = len(secciones)
    for numero, (nombre, datos) in enumerate(secciones, start=1):
        opciones.progreso.paso(numero - 1, total,
                               _("Convirtiendo %d de %d") % (numero, total))
        try:
            resultado = conversor.convertir(datos)
        except Exception as error:
            registrar_excepcion(log, "Error convirtiendo la sección %s" % nombre, error)
            continue
        if not resultado.texto:
            continue

        inicio = desplazamiento
        partes.append(resultado.texto)
        desplazamiento += len(resultado.texto) + 1     # el salto que las separa

        marcas.append(Marca(TipoMarca.SALTO_SECCION, inicio, _("Sección %d") % numero, nombre))
        for marca in resultado.marcas:
            if marca.referencia and marca.tipo in TIPOS_CON_RUTA and resolver_ruta is not None:
                marcas.append(marca._replace(
                    posicion=marca.posicion + inicio,
                    referencia=resolver_ruta(nombre, marca.referencia)))
            else:
                marcas.append(marca._replace(posicion=marca.posicion + inicio))
        for identificador, posicion in resultado.posiciones_id.items():
            posiciones_id.setdefault("%s#%s" % (nombre, identificador), posicion + inicio)
            posiciones_id.setdefault(identificador, posicion + inicio)
        for posicion, rotulo in resultado.paginas:
            paginas.append((posicion + inicio, rotulo))
        lista_secciones.append(Seccion(nombre, inicio, desplazamiento - 1))

    texto = "\n".join(partes)
    if not texto.strip():
        return Documento(texto="", marcas=[], indice=[], posiciones_id={}, secciones=[],
                         metadatos=metadatos, ruta_archivo=str(ruta))

    for posicion, rotulo in paginas:
        marcas.append(Marca(TipoMarca.SALTO_PAGINA, posicion, rotulo))
    marcas.sort(key=lambda marca: marca.posicion)

    if not metadatos.titulo:
        metadatos.titulo = Path(ruta).stem

    libro = Documento(
        texto=texto,
        marcas=marcas,
        indice=indice if indice is not None else indice_desde_encabezados(marcas, texto),
        posiciones_id=posiciones_id,
        secciones=lista_secciones,
        metadatos=metadatos,
        ruta_archivo=str(ruta),
    )
    # El informe de accesibilidad se hace aquí, que es por donde pasan todos
    # los formatos: así un DOCX o un EPUB dicen lo mismo que un PDF sobre lo
    # que traen para poder leerse, sin que cada analizador tenga que repetirlo.
    # El analizador puede ampliarlo después con lo suyo.
    metadatos.accesibilidad = accesibilidad.resumen(libro)
    return libro


#: Extensiones de los OpenDocument **planos**: el mismo documento en un solo
#: XML, sin el ZIP alrededor.  LibreOffice los guarda así cuando se le pide un
#: «formato plano», y se usan sobre todo para poner un documento bajo control de
#: versiones: un ZIP no se puede comparar línea a línea y un XML sí.
PLANOS = (".fodt", ".fods", ".fodp", ".fodg", ".otp", ".ots", ".ott")


class _PaqueteLlano:
    """Hace pasar un ODF plano por un ZIP, para no duplicar tres analizadores.

    En un ODF empaquetado, el contenido y los metadatos son dos archivos dentro
    del ZIP.  En uno plano están los dos en el mismo árbol, así que devolver el
    documento entero cuando piden cualquiera de los dos es exactamente lo
    correcto: quien lo lee busca su elemento dentro y lo encuentra igual.
    """

    __slots__ = ("datos",)

    def __init__(self, datos: bytes) -> None:
        self.datos = datos

    def read(self, nombre: str) -> bytes:      # noqa: N802 (imita a zipfile)
        if nombre in ("content.xml", "meta.xml", "styles.xml"):
            return self.datos
        raise KeyError(nombre)

    def namelist(self) -> list:                # noqa: N802 (imita a zipfile)
        return ["content.xml", "meta.xml"]

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *sobra) -> None:
        pass


def abrir_odf(ruta):
    """Abre un OpenDocument, venga empaquetado o plano.

    Devuelve algo que se comporta como un ``ZipFile`` para lo que hace falta:
    ``read`` y el gestor de contexto.  Así los tres analizadores —texto, hoja y
    presentación— tratan los dos casos con el mismo código.

    :raises ErrorFormato: Si el archivo no se puede abrir.
    """
    import zipfile

    from .base import ErrorFormato

    destino = Path(ruta)
    if destino.suffix.lower() in PLANOS:
        try:
            datos = destino.read_bytes()
        except OSError as error:
            raise ErrorFormato(_("No se ha podido leer el archivo: %s") % error)
        if b"office:document" not in datos[:4096]:
            # Puede ser un ODF empaquetado con una de esas extensiones: las
            # plantillas «.ott», «.ots» y «.otp» son ZIP casi siempre.
            try:
                return zipfile.ZipFile(destino)
            except (OSError, zipfile.BadZipFile) as error:
                raise ErrorFormato(
                    _("El archivo no es un OpenDocument: %s") % error)
        return _PaqueteLlano(datos)
    try:
        return zipfile.ZipFile(destino)
    except (OSError, zipfile.BadZipFile) as error:
        raise ErrorFormato(_("El archivo no se puede abrir: %s") % error)
