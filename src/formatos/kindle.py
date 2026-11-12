# -*- coding: utf-8 -*-
"""Libros de Kindle: KFX, AZW3, AZW y MOBI.

Amazon ha usado tres formatos distintos en veinte años, y los tres siguen
circulando, así que el programa abre los tres:

* **KFX** (``.kfx``, ``.kfx-zip``), el de ahora.  No lleva HTML dentro: es un
  contenedor binario del que hay que reconstruir el libro pieza a pieza.  Lo
  hace :mod:`formatos.kindle_kfx`.
* **AZW3 / KF8** (``.azw3``, ``.azw``), el anterior.  Dentro lleva XHTML de
  verdad, partido en trozos, y lo que hace falta es recomponerlo.
* **MOBI** (``.mobi``, ``.prc``, ``.azw``), el original.  Es un HTML enorme
  comprimido, con las anclas puestas por posición de byte.
* **AZW4**, el «Print Replica» de los libros de texto: por fuera es un
  contenedor de Kindle y por dentro **un PDF entero**.  Se saca el PDF y se lee
  con el lector de PDF del programa, con todo lo que eso trae: estructura
  deducida, reconocimiento óptico si hace falta e informe de accesibilidad.

Los tres acaban en lo mismo —secciones XHTML para el ensamblador común—, de
modo que **un libro de Kindle se recorre igual que un EPUB**: con las mismas
teclas de encabezado, de enlace y de imagen, con su índice, sus marcadores y
su lectura en voz alta.

Sobre el DRM
------------

Este módulo **no descifra nada**.  Un libro comprado en Amazon y sin abrir
viene cifrado, y al encontrarse uno así el programa lo dice y no lo abre.  Lo
que se lee aquí son archivos que ya vienen sin protección: los que Amazon
distribuye así, los que el propio autor reparte y los que el usuario ha
liberado por su cuenta con las herramientas que use para eso.
"""

from __future__ import annotations

from pathlib import Path

from nucleo.documento import Documento, ElementoIndice, Metadatos
from nucleo.idioma import _
from nucleo.registro import obtener_registro

from .base import Analizador, ErrorFormato, OpcionesAnalisis, registrar
from .epub import _encabezados_desde_indice
from .ensamblador import montar

log = obtener_registro(__name__)

#: Primeros bytes de un contenedor KFX.
MARCA_KFX = b"CONT"

#: Los formatos viejos van dentro de una base de datos Palm, que dice en su
#: cabecera qué clase de libro es.  Estos son los tipos que interesan.
TIPOS_PALM = (b"BOOKMOBI", b"TEXtREAd")


class AnalizadorKindle(Analizador):
    """Libros de Kindle en cualquiera de sus formatos."""

    extensiones = (".kfx", ".kfx-zip", ".azw", ".azw3", ".azw4", ".azw8",
                   ".mobi", ".prc")
    descripcion = _("Libros de Kindle")

    def analizar(self, ruta, opciones: OpcionesAnalisis):
        """Abre el libro con el lector que corresponda a su formato."""
        destino = Path(ruta)
        clase = _clase_de(destino)
        if clase == "kfx":
            return self._analizar_kfx(destino, opciones)
        if clase == "pdf":
            return self._analizar_azw4(destino, opciones)
        if clase == "palm":
            return self._analizar_palm(destino, opciones)
        raise ErrorFormato(
            _("Este archivo no es un libro de Kindle que se pueda leer."))

    # -- AZW4 -----------------------------------------------------------------

    def _analizar_azw4(self, destino: Path, opciones: OpcionesAnalisis):
        """Saca el PDF de dentro del contenedor y lo lee con el lector de PDF.

        No se convierte nada: el PDF que hay dentro es un PDF completo, así que
        se guarda tal cual en la carpeta temporal y se abre con el analizador de
        siempre.  Así un «Print Replica» trae de golpe todo lo que el programa
        sabe hacer con un PDF, sin escribir una línea de más.
        """
        from nucleo import rutas

        from .base import analizador_para

        crudo = _pdf_de_dentro(destino)
        if not crudo:
            raise ErrorFormato(
                _("Este archivo no es un libro de Kindle que se pueda leer."))
        temporal = rutas.ruta_temp() / ("%s.pdf" % destino.stem)
        try:
            temporal.write_bytes(crudo)
        except OSError as error:
            raise ErrorFormato(_("No se ha podido preparar el PDF del libro: %s")
                               % error) from error
        analizador = analizador_para(temporal)
        if analizador is None:
            raise ErrorFormato(_("Este archivo no es un libro de Kindle que se pueda leer."))
        documento = analizador.analizar(temporal, opciones)
        # El documento tiene que decir de qué archivo salió, no del temporal:
        # es lo que se guarda en los recientes y en la posición de lectura.
        documento.ruta_archivo = str(destino)
        if not documento.metadatos.titulo or documento.metadatos.titulo == temporal.stem:
            documento.metadatos.titulo = destino.stem
        log.info("AZW4 analizado: %s | %d caracteres",
                 documento.metadatos.titulo, len(documento.texto))
        return documento

    # -- KFX ------------------------------------------------------------------

    def _analizar_kfx(self, destino: Path, opciones: OpcionesAnalisis):
        """Lee un libro KFX y lo convierte en documento."""
        from . import kindle_kfx

        try:
            libro = kindle_kfx.LibroKFX(destino)
        except kindle_kfx.ErrorKFX as error:
            raise ErrorFormato(str(error)) from error
        secciones = libro.secciones()
        if not secciones:
            raise ErrorFormato(
                _("El libro no contiene texto legible. Puede estar protegido con DRM."))
        documento = montar(secciones, _metadatos_de(libro.metadatos), destino, opciones)
        if not documento.texto.strip():
            raise ErrorFormato(
                _("El libro no contiene texto legible. Puede estar protegido con DRM."))
        indice = _indice_kfx(libro, documento.posiciones_id)
        if indice:
            documento.indice = indice
        log.info("KFX analizado: %s | %d caracteres | %d secciones | %d entradas de índice",
                 documento.metadatos.titulo, len(documento.texto), len(secciones),
                 len(documento.indice_plano()))
        return documento

    # -- MOBI y AZW3 ----------------------------------------------------------

    def _analizar_palm(self, destino: Path, opciones: OpcionesAnalisis):
        """Lee un MOBI o un AZW3 y lo convierte en documento."""
        from . import kindle_mobi

        try:
            libro = kindle_mobi.LibroMobi(destino)
        except kindle_mobi.ErrorMobi as error:
            raise ErrorFormato(str(error)) from error
        secciones = libro.secciones()
        if not secciones:
            raise ErrorFormato(
                _("El libro no contiene texto legible. Puede estar protegido con DRM."))
        documento = montar(secciones, _metadatos_de(libro.metadatos), destino, opciones,
                           resolver_ruta=kindle_mobi.resolver_ruta)
        if not documento.texto.strip():
            raise ErrorFormato(
                _("El libro no contiene texto legible. Puede estar protegido con DRM."))
        indice = _indice_mobi(libro, documento.posiciones_id)
        if indice:
            documento = _con_indice(documento, indice)
        log.info("%s analizado: %s | %d caracteres | %d secciones | %d entradas de índice",
                 libro.formato, documento.metadatos.titulo, len(documento.texto),
                 len(secciones), len(documento.indice_plano()))
        self._recursos[str(destino)] = libro
        return documento

    #: Libros ya abiertos, para poder sacarles después una imagen sin volver a
    #: leer el archivo entero.
    _recursos: dict = {}

    def extraer_recurso(self, ruta, interna: str) -> bytes | None:
        """Devuelve una imagen del libro, para poder verla o describirla."""
        libro = self._recursos.get(str(Path(ruta)))
        if libro is not None:
            return libro.recurso(interna)
        clase = _clase_de(Path(ruta))
        if clase == "kfx":
            from . import kindle_kfx

            try:
                return kindle_kfx.LibroKFX(Path(ruta)).recurso(interna)
            except Exception as error:
                log.debug("No se ha podido sacar %s del KFX: %s", interna, error)
                return None
        if clase == "palm":
            from . import kindle_mobi

            try:
                return kindle_mobi.LibroMobi(Path(ruta)).recurso(interna)
            except Exception as error:
                log.debug("No se ha podido sacar %s del MOBI: %s", interna, error)
        return None


def _clase_de(destino: Path) -> str:
    """Dice si el archivo es «kfx», «palm» o nada de eso.

    Se mira **dentro** y no la extensión: un ``.azw`` puede ser lo viejo o un
    KFX con el nombre de siempre, y es lo que hay en los primeros bytes lo que
    lo dice sin lugar a dudas.
    """
    try:
        with open(destino, "rb") as archivo:
            cabecera = archivo.read(80)
    except OSError:
        return ""
    if cabecera[:4] == MARCA_KFX:
        return "kfx"
    if cabecera[60:68] in TIPOS_PALM:
        # Un «Print Replica» es un contenedor de Kindle con un PDF dentro.  Se
        # distingue mirando si lo hay, que es más fiable que fiarse del nombre
        # del archivo: los hay con extensión «.azw» de toda la vida.
        return "pdf" if _pdf_de_dentro(destino) else "palm"
    if cabecera[:2] == b"PK":
        # Un zip: puede ser un KFX empaquetado.
        import zipfile

        try:
            with zipfile.ZipFile(str(destino)) as archivo:
                for nombre in archivo.namelist()[:20]:
                    with archivo.open(nombre) as dentro:
                        if dentro.read(4) == MARCA_KFX:
                            return "kfx"
        except Exception:
            return ""
    return ""


def _pdf_de_dentro(destino: Path) -> bytes:
    """Devuelve el PDF que un AZW4 lleva dentro, o vacío si no lleva ninguno.

    El PDF va metido en el contenedor sin comprimir ni cifrar, así que se
    encuentra por sus dos marcas: donde empieza y donde acaba.
    """
    import re

    try:
        datos = destino.read_bytes()
    except OSError:
        return b""
    if b"%PDF" not in datos[:200000]:
        return b""
    hallado = re.search(rb"%PDF.+%%EOF", datos, re.DOTALL)
    return hallado.group() if hallado else b""


def _metadatos_de(crudos: dict) -> Metadatos:
    """Traduce los metadatos del libro a los del programa."""
    autores = crudos.get("authors") or []
    return Metadatos(
        titulo=str(crudos.get("title") or ""),
        autor=", ".join(str(a) for a in autores),
        idioma=str(crudos.get("language") or ""),
        editorial=str(crudos.get("publisher") or ""),
        fecha=str(crudos.get("issue_date") or ""),
        identificador=str(crudos.get("ASIN") or ""),
    )


def _con_indice(documento, indice: list[ElementoIndice]):
    """Devuelve el documento con su índice y con los encabezados que salen de él.

    Un MOBI no marca sus títulos, así que sin esto se abriría sin un solo
    encabezado y la tecla ``H`` no llevaría a ninguna parte.  Se rehace el
    documento en vez de tocarlo por dentro porque sus marcas van indexadas
    para poder buscarlas por posición, y añadir una a mano dejaría ese índice
    diciendo algo que ya no es verdad.
    """
    marcas = list(documento.marcas.todas())
    marcas.extend(_encabezados_desde_indice(marcas, indice))
    marcas.sort(key=lambda marca: marca.posicion)
    nuevo = Documento(
        texto=documento.texto,
        marcas=marcas,
        indice=indice,
        posiciones_id=documento.posiciones_id,
        secciones=documento.secciones,
        metadatos=documento.metadatos,
        ruta_archivo=documento.ruta_archivo,
    )
    return nuevo


def _indice_mobi(libro, posiciones: dict) -> list[ElementoIndice]:
    """Convierte el índice del MOBI en el del programa, anidando por nivel.

    Un MOBI no marca sus títulos —el generador de Amazon los deja como
    párrafos con letra grande—, así que sin esto el libro se abre sin un solo
    encabezado.  Con esto, cada entrada del índice se convierte además en un
    encabezado, que es lo que hace que la tecla ``H`` funcione.
    """
    from . import kindle_mobi

    raiz: list[ElementoIndice] = []
    pila: list[tuple[int, ElementoIndice]] = []
    for rotulo, posicion, nivel in libro.indice():
        ancla = kindle_mobi.ancla_de(posicion)
        destino = posiciones.get(ancla)
        if destino is None:
            continue
        elemento = ElementoIndice(rotulo, destino, ancla)
        while pila and pila[-1][0] >= nivel:
            pila.pop()
        if pila:
            pila[-1][1].hijos.append(elemento)
        else:
            raiz.append(elemento)
        pila.append((nivel, elemento))
    return raiz


def _indice_kfx(libro, posiciones: dict) -> list[ElementoIndice]:
    """Convierte el índice del KFX en el del programa, anidando por nivel.

    El formato guarda el índice como una lista plana en la que cada entrada
    dice de qué nivel es; aquí se vuelve a montar el árbol, que es lo que
    después se recorre con las flechas en la ventana de contenido.
    """
    from . import kindle_kfx

    raiz: list[ElementoIndice] = []
    pila: list[tuple[int, ElementoIndice]] = []
    for entrada in libro.indice:
        ancla = kindle_kfx.ancla_de(entrada.destino)
        elemento = ElementoIndice(entrada.rotulo, posiciones.get(ancla, 0), ancla)
        while pila and pila[-1][0] >= entrada.nivel:
            pila.pop()
        if pila:
            pila[-1][1].hijos.append(elemento)
        else:
            raiz.append(elemento)
        pila.append((entrada.nivel, elemento))
    return raiz


registrar(AnalizadorKindle())
