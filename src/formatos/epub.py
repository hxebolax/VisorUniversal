# -*- coding: utf-8 -*-
"""Analizador de libros EPUB (versiones 2 y 3).

Un EPUB es un archivo ZIP con esta estructura:

* ``META-INF/container.xml`` indica dónde está el archivo *OPF*.
* El **OPF** contiene los metadatos, el *manifiesto* (todos los archivos del
  libro) y el *lomo* o *spine* (el orden de lectura de los capítulos).
* El **índice** viene en un documento de navegación (EPUB 3) o en un archivo
  ``.ncx`` (EPUB 2).  Se prefiere el primero y se recurre al segundo.

El proceso de análisis es:

1. Leer el OPF y averiguar el orden de los capítulos.
2. Convertir cada capítulo a texto con :mod:`formatos.conversor`.
3. Unir todos los textos en uno solo, desplazando las marcas de cada capítulo
   a su posición definitiva.
4. Construir el índice y la lista de páginas resolviendo sus enlaces contra
   las posiciones obtenidas en el paso anterior.

El paso 3 es el que permite que la navegación sea instantánea después: todo
queda en un único texto con marcas ya ordenadas.
"""

from __future__ import annotations

import os
import posixpath
import zipfile
from pathlib import Path
from urllib.parse import unquote

from lxml import etree

from nucleo import accesibilidad
from nucleo.documento import Documento, ElementoIndice, Metadatos, Seccion
from nucleo.marcas import Marca, TipoMarca
from nucleo.registro import cronometro, obtener_registro, registrar_excepcion

from .base import Analizador, ErrorFormato, OpcionesAnalisis, registrar
from .conversor import ConversorXHTML
from .lectura_xml import crear_parser_xml
from .tablas import nombre_local
from nucleo.idioma import _

log = obtener_registro(__name__)

#: Analizador XML tolerante y sin acceso a la red, compartido por las
#: funciones que leen el OPF, el documento de navegación y el NCX.
_PARSER = crear_parser_xml()

#: Marcas cuya referencia es una ruta interna del libro y hay que resolver.
_TIPOS_CON_RUTA = frozenset({TipoMarca.ENLACE, TipoMarca.IMAGEN, TipoMarca.FIGURA})

#: Tipos de medio que corresponden a documentos de contenido.
_TIPOS_CONTENIDO = frozenset({
    "application/xhtml+xml", "text/html", "application/x-dtbook+xml", "text/x-oeb1-document",
})


# ---------------------------------------------------------------------------
# Utilidades de rutas dentro del ZIP
# ---------------------------------------------------------------------------

def resolver_ruta(carpeta_base: str, destino: str) -> str:
    """Resuelve una ruta relativa dentro del EPUB.

    Las rutas del OPF son relativas a la carpeta donde está el propio OPF, y
    pueden contener ``../``.  ``posixpath.normpath`` las normaliza igual que
    haría un navegador.
    """
    if not destino:
        return ""
    if destino.startswith("/"):
        return destino.lstrip("/")
    combinada = posixpath.join(carpeta_base, destino) if carpeta_base else destino
    return posixpath.normpath(combinada).replace("\\", "/").lstrip("./")


def es_url_externa(destino: str) -> bool:
    """Indica si un enlace apunta fuera del libro."""
    minuscula = destino.lower()
    return minuscula.startswith(("http://", "https://", "mailto:", "ftp://", "tel:"))


def separar_destino(destino: str) -> tuple[str, str]:
    """Separa un destino en (ruta, ancla), descodificando el porcentaje."""
    limpio = unquote(destino)
    if "#" in limpio:
        ruta, ancla = limpio.split("#", 1)
        return ruta, ancla
    return limpio, ""


def resolver_destino(ruta_actual: str, destino: str) -> str:
    """Convierte el destino de un enlace en una referencia absoluta del libro.

    :param ruta_actual: Archivo donde se encontró el enlace.
    :param destino: Valor del atributo ``href``.
    """
    if not destino or es_url_externa(destino):
        return destino
    ruta, ancla = separar_destino(destino)
    if not ruta:
        # Enlace a un ancla del mismo archivo.
        return "%s#%s" % (ruta_actual, ancla) if ancla else ruta_actual
    carpeta = posixpath.dirname(ruta_actual)
    absoluta = resolver_ruta(carpeta, ruta)
    return "%s#%s" % (absoluta, ancla) if ancla else absoluta


# ---------------------------------------------------------------------------
# Lectura del paquete OPF
# ---------------------------------------------------------------------------

class _ElementoManifiesto:
    """Una entrada del manifiesto del EPUB."""

    __slots__ = ("identificador", "ruta", "tipo_medio", "propiedades")

    def __init__(self, identificador: str, ruta: str, tipo_medio: str, propiedades: list[str]) -> None:
        self.identificador = identificador
        self.ruta = ruta
        self.tipo_medio = tipo_medio
        self.propiedades = propiedades


class _Paquete:
    """Resultado de leer el archivo OPF."""

    __slots__ = ("manifiesto", "lomo", "ruta_nav", "ruta_ncx", "metadatos", "carpeta",
                 "accesibilidad")

    def __init__(self) -> None:
        self.manifiesto: dict[str, _ElementoManifiesto] = {}
        self.lomo: list[str] = []
        self.ruta_nav: str = ""
        self.ruta_ncx: str = ""
        self.metadatos = Metadatos()
        self.carpeta = ""
        #: Lo que el libro declara sobre su propia accesibilidad, tal como pide
        #: la norma EPUB Accessibility.
        self.accesibilidad = ""


def _leer_entrada(archivo: zipfile.ZipFile, nombre: str) -> bytes:
    """Lee una entrada del ZIP, tolerando diferencias de mayúsculas.

    Algunos EPUB declaran rutas con una capitalización distinta de la real.
    """
    try:
        return archivo.read(nombre)
    except KeyError:
        objetivo = nombre.lower()
        for interno in archivo.namelist():
            if interno.lower() == objetivo:
                return archivo.read(interno)
        raise


#: Algoritmos de ``encryption.xml`` que solo ofuscan las fuentes tipográficas
#: incrustadas (el del IDPF y el de Adobe).  No tocan el texto: el libro se lee
#: entero, así que no son motivo de aviso.
_OFUSCACION_DE_FUENTES = frozenset((
    "http://www.idpf.org/2008/embedding",
    "http://ns.adobe.com/pdf/enc#rc",
))


def _avisar_del_cifrado(archivo: zipfile.ZipFile) -> None:
    """Dice qué declara ``META-INF/encryption.xml``, con el peso que le toca.

    Muchísimos EPUB lo traen solo para ofuscar sus fuentes, y eso no impide
    leer nada: se apunta como información.  Lo que sí se avisa es otro
    algoritmo, que suele ser DRM y puede dejar el texto ilegible.
    """
    try:
        raiz = etree.fromstring(_leer_entrada(archivo, "META-INF/encryption.xml"), _PARSER)
    except Exception:                                # pragma: no cover - defensivo
        raiz = None
    algoritmos = set()
    if raiz is not None:
        for nodo in raiz.iter():
            if nombre_local(nodo.tag) == "encryptionmethod" and nodo.get("Algorithm"):
                algoritmos.add(nodo.get("Algorithm").strip().lower())
    if algoritmos and algoritmos <= _OFUSCACION_DE_FUENTES:
        log.info("El libro ofusca sus fuentes tipográficas (no afecta al texto)")
    else:
        log.warning("El libro declara cifrado en META-INF/encryption.xml: %s",
                    ", ".join(sorted(algoritmos)) or "sin algoritmo legible")


def _localizar_opf(archivo: zipfile.ZipFile) -> str:
    """Devuelve la ruta del archivo OPF leyendo ``META-INF/container.xml``."""
    try:
        contenido = _leer_entrada(archivo, "META-INF/container.xml")
    except KeyError:
        raise ErrorFormato(
            _("El archivo no parece un EPUB válido: falta META-INF/container.xml.")
        )
    raiz = etree.fromstring(contenido, _PARSER)
    if raiz is not None:
        for nodo in raiz.iter():
            if nombre_local(nodo.tag) == "rootfile":
                completo = nodo.get("full-path")
                if completo:
                    return completo
    # Último recurso: buscar cualquier .opf dentro del archivo.
    for interno in archivo.namelist():
        if interno.lower().endswith(".opf"):
            log.warning("container.xml sin rootfile; se usa %s", interno)
            return interno
    raise ErrorFormato(_("El archivo no contiene ningún documento OPF con la descripción del contenido."))


def _texto_de(nodo) -> str:
    """Texto plano de un nodo XML, sin espacios sobrantes."""
    return " ".join("".join(nodo.itertext()).split())


def _leer_paquete(contenido: bytes, carpeta: str) -> _Paquete:
    """Analiza el archivo OPF y extrae manifiesto, lomo y metadatos."""
    raiz = etree.fromstring(contenido, _PARSER)
    if raiz is None:
        raise ErrorFormato(_("No se ha podido leer la descripción interna del documento (OPF dañado)."))

    paquete = _Paquete()
    paquete.carpeta = carpeta

    for seccion in raiz:
        nombre = nombre_local(seccion.tag)
        if nombre == "metadata":
            _leer_metadatos(seccion, paquete.metadatos)
            paquete.accesibilidad = _leer_accesibilidad(seccion)
        elif nombre == "manifest":
            for elemento in seccion:
                if nombre_local(elemento.tag) != "item":
                    continue
                identificador = elemento.get("id")
                destino = elemento.get("href")
                if not identificador or not destino:
                    continue
                ruta = resolver_ruta(carpeta, unquote(destino))
                propiedades = (elemento.get("properties") or "").split()
                entrada = _ElementoManifiesto(
                    identificador, ruta, (elemento.get("media-type") or "").lower(), propiedades
                )
                paquete.manifiesto[identificador] = entrada
                if "nav" in propiedades:
                    paquete.ruta_nav = ruta
                if entrada.tipo_medio == "application/x-dtbncx+xml":
                    paquete.ruta_ncx = ruta
        elif nombre == "spine":
            referencia_ncx = seccion.get("toc")
            if referencia_ncx and not paquete.ruta_ncx:
                entrada = paquete.manifiesto.get(referencia_ncx)
                if entrada:
                    paquete.ruta_ncx = entrada.ruta
            for elemento in seccion:
                if nombre_local(elemento.tag) != "itemref":
                    continue
                referencia = elemento.get("idref")
                if referencia:
                    paquete.lomo.append(referencia)
    return paquete


#: Propiedades de accesibilidad que la norma EPUB Accessibility pide declarar
#: en el paquete, con el nombre corto con el que se enseñan.  Son las que
#: permiten saber **antes de abrirlo** si un libro se va a poder leer: si trae
#: texto alternativo en sus imágenes, si tiene índice, y a qué nivel de las
#: WCAG dice ajustarse.
PROPIEDADES_ACCESIBILIDAD = {
    "schema:accessibilitysummary": _("resumen"),
    "schema:accessibilityfeature": _("recursos"),
    "schema:accessmode": _("modos de acceso"),
    "schema:accessibilityhazard": _("riesgos"),
    "dcterms:conformsto": _("conformidad"),
    "a11y:certifiedby": _("certificado por"),
}


def _leer_accesibilidad(nodo) -> str:
    """Reúne lo que el EPUB declara sobre su propia accesibilidad.

    Un EPUB bien hecho lo dice en sus metadatos, y desde 2025 la ley europea lo
    exige: qué recursos de accesibilidad trae, con qué sentidos se puede leer,
    si tiene algo que pueda provocar una crisis y a qué nivel de las WCAG se
    ajusta.  Es información que el archivo ya trae y que hasta ahora se tiraba.
    """
    encontrado: dict[str, list[str]] = {}
    for elemento in nodo.iter():
        nombre = nombre_local(elemento.tag)
        if nombre == "meta":
            propiedad = (elemento.get("property") or "").strip().lower()
            valor = _texto_de(elemento)
        elif nombre == "link":
            propiedad = (elemento.get("rel") or "").strip().lower()
            valor = (elemento.get("href") or "").strip()
        else:
            continue
        rotulo = PROPIEDADES_ACCESIBILIDAD.get(propiedad)
        if rotulo and valor:
            encontrado.setdefault(rotulo, []).append(valor)
    if not encontrado:
        return ""
    partes = ["%s: %s" % (rotulo, ", ".join(valores[:8]))
              for rotulo, valores in encontrado.items()]
    aviso = _aviso_de_riesgos(encontrado.get(PROPIEDADES_ACCESIBILIDAD["schema:accessibilityhazard"], ()))
    declaracion = _("El libro declara — %s.") % "; ".join(partes)
    return "%s %s" % (aviso, declaracion) if aviso else declaracion


#: Riesgos declarados de los que hay que avisar por delante de todo lo demás.
#: No son una molestia: un destello puede provocar una crisis a quien tenga
#: epilepsia fotosensible, y eso se dice antes de abrir el libro, no dentro
#: de una lista de propiedades.
RIESGOS_SERIOS = {
    "flashing": _("destellos"),
    "flashinghazard": _("destellos"),
    "motionsimulation": _("simulación de movimiento"),
    "motionsimulationhazard": _("simulación de movimiento"),
    "sound": _("sonidos"),
    "soundhazard": _("sonidos"),
}


def _aviso_de_riesgos(valores) -> str:
    """Escribe el aviso de los riesgos que el libro declare tener."""
    hallados = []
    for valor in valores:
        nombre = RIESGOS_SERIOS.get(str(valor).strip().lower())
        if nombre and nombre not in hallados:
            hallados.append(nombre)
    if not hallados:
        return ""
    return _("AVISO: el libro declara que contiene %s.") % ", ".join(hallados)


def _leer_metadatos(nodo, destino: Metadatos) -> None:
    """Rellena los metadatos del libro a partir del bloque ``<metadata>``."""
    equivalencias = {
        "title": "titulo",
        "creator": "autor",
        "language": "idioma",
        "publisher": "editorial",
        "date": "fecha",
        "identifier": "identificador",
        "description": "descripcion",
    }
    for elemento in nodo.iter():
        nombre = nombre_local(elemento.tag)
        atributo = equivalencias.get(nombre)
        if not atributo:
            continue
        if getattr(destino, atributo):
            continue  # se conserva el primer valor encontrado
        valor = _texto_de(elemento)
        if valor:
            setattr(destino, atributo, valor)


# ---------------------------------------------------------------------------
# Índice y lista de páginas
# ---------------------------------------------------------------------------

def _posicion_de_referencia(referencia: str, secciones: list[Seccion],
                            posiciones_id: dict[str, int]) -> int:
    """Traduce el destino de una entrada del índice a una posición del texto."""
    ruta, ancla = separar_destino(referencia)
    seccion = next((s for s in secciones if s.ruta == ruta), None)
    if seccion is not None:
        if ancla:
            posicion = posiciones_id.get("%s#%s" % (ruta, ancla))
            if posicion is None:
                posicion = posiciones_id.get(ancla)
            if posicion is not None and seccion.inicio <= posicion < seccion.fin:
                return posicion
        return seccion.inicio
    if ancla and ancla in posiciones_id:
        return posiciones_id[ancla]
    # Respaldo: comparar solo el nombre del archivo.
    nombre = ruta.rsplit("/", 1)[-1].lower()
    for candidata in secciones:
        if candidata.ruta.rsplit("/", 1)[-1].lower() == nombre:
            return candidata.inicio
    return 0


def _buscar_nav(raiz, tipos: tuple[str, ...]):
    """Busca un elemento ``<nav>`` de un tipo semántico concreto."""
    for nodo in raiz.iter():
        if nombre_local(nodo.tag) != "nav":
            continue
        for atributo, valor in nodo.attrib.items():
            nombre_atributo = nombre_local(atributo) or str(atributo).lower()
            if nombre_atributo.endswith("type") or nombre_atributo == "role":
                partes = str(valor).lower().split()
                if any(parte in tipos for parte in partes):
                    return nodo
    return None


def _leer_lista_nav(lista, ruta_nav: str, secciones, posiciones_id) -> list[ElementoIndice]:
    """Convierte una lista ``<ol>``/``<ul>`` del documento de navegación."""
    entradas: list[ElementoIndice] = []
    for elemento in lista:
        if nombre_local(elemento.tag) != "li":
            continue
        entrada = _leer_elemento_nav(elemento, ruta_nav, secciones, posiciones_id)
        if entrada is not None:
            entradas.append(entrada)
    return entradas


def _leer_elemento_nav(elemento, ruta_nav: str, secciones, posiciones_id) -> ElementoIndice | None:
    """Convierte un ``<li>`` del documento de navegación en una entrada."""
    enlace = None
    for hijo in elemento:
        if nombre_local(hijo.tag) == "a":
            enlace = hijo
            break
    if enlace is None:
        for descendiente in elemento.iterdescendants():
            if nombre_local(descendiente.tag) == "a":
                enlace = descendiente
                break
    titulo = ""
    referencia = ""
    if enlace is not None:
        titulo = _texto_de(enlace)
        referencia = enlace.get("href") or enlace.get("{http://www.w3.org/1999/xlink}href") or ""
    else:
        # Algunas entradas son solo un rótulo sin enlace (agrupadores).
        for hijo in elemento:
            if nombre_local(hijo.tag) == "span":
                titulo = _texto_de(hijo)
                break
    if not titulo:
        return None
    absoluta = resolver_destino(ruta_nav, referencia) if referencia else ""
    posicion = _posicion_de_referencia(absoluta, secciones, posiciones_id) if absoluta else 0
    entrada = ElementoIndice(titulo, posicion, absoluta)
    for hijo in elemento:
        if nombre_local(hijo.tag) in ("ol", "ul"):
            entrada.hijos.extend(_leer_lista_nav(hijo, ruta_nav, secciones, posiciones_id))
    return entrada


def _indice_desde_nav(contenido: bytes, ruta_nav: str, secciones, posiciones_id,
                      tipos: tuple[str, ...]) -> list[ElementoIndice]:
    """Construye una lista de entradas a partir del documento de navegación."""
    raiz = etree.fromstring(contenido, _PARSER)
    if raiz is None:
        return []
    nodo = _buscar_nav(raiz, tipos)
    if nodo is None:
        return []
    entradas: list[ElementoIndice] = []
    for hijo in nodo:
        nombre = nombre_local(hijo.tag)
        if nombre in ("ol", "ul"):
            entradas.extend(_leer_lista_nav(hijo, ruta_nav, secciones, posiciones_id))
        elif nombre == "li":
            entrada = _leer_elemento_nav(hijo, ruta_nav, secciones, posiciones_id)
            if entrada is not None:
                entradas.append(entrada)
    if not entradas:
        # Algunos libros anidan la lista dentro de otro contenedor.
        for descendiente in nodo.iterdescendants():
            if nombre_local(descendiente.tag) in ("ol", "ul"):
                entradas = _leer_lista_nav(descendiente, ruta_nav, secciones, posiciones_id)
                if entradas:
                    break
    return entradas


def _convertir_punto_ncx(nodo, ruta_ncx: str, secciones, posiciones_id) -> ElementoIndice | None:
    """Convierte un ``<navPoint>`` (o ``<pageTarget>``) del NCX."""
    titulo = ""
    referencia = ""
    for hijo in nodo:
        # nombre_local() devuelve el nombre en minúsculas, así que las
        # comparaciones deben hacerse también en minúsculas.
        nombre = nombre_local(hijo.tag)
        if nombre == "navlabel" and not titulo:
            titulo = _texto_de(hijo)
        elif nombre == "content" and not referencia:
            referencia = hijo.get("src") or ""
    if not titulo or not referencia:
        return None
    absoluta = resolver_destino(ruta_ncx, referencia)
    posicion = _posicion_de_referencia(absoluta, secciones, posiciones_id)
    entrada = ElementoIndice(titulo, posicion, absoluta)
    for hijo in nodo:
        if nombre_local(hijo.tag) == "navpoint":
            anidada = _convertir_punto_ncx(hijo, ruta_ncx, secciones, posiciones_id)
            if anidada is not None:
                entrada.hijos.append(anidada)
    return entrada


def _indice_desde_ncx(contenido: bytes, ruta_ncx: str, secciones, posiciones_id,
                      contenedor: str, elemento: str) -> list[ElementoIndice]:
    """Construye el índice o la lista de páginas a partir del NCX (EPUB 2)."""
    raiz = etree.fromstring(contenido, _PARSER)
    if raiz is None:
        return []
    mapa = None
    for nodo in raiz.iter():
        if nombre_local(nodo.tag) == contenedor.lower():
            mapa = nodo
            break
    if mapa is None:
        return []
    entradas: list[ElementoIndice] = []
    for hijo in mapa:
        if nombre_local(hijo.tag) == elemento.lower():
            entrada = _convertir_punto_ncx(hijo, ruta_ncx, secciones, posiciones_id)
            if entrada is not None:
                entradas.append(entrada)
    return entradas


def _encabezados_desde_indice(marcas: list[Marca],
                              indice: list[ElementoIndice]) -> list[Marca]:
    """Crea encabezados a partir del índice cuando el libro no tiene ninguno.

    Muchos libros en español maquetan los títulos de capítulo con un párrafo
    con estilo (``<p class="titulo">``) en lugar de con las etiquetas ``<h1>``
    a ``<h6>``.  El resultado es un libro perfectamente legible pero en el que
    la navegación por encabezados no llevaría a ninguna parte.

    Como esos libros sí traen índice, se aprovechan sus entradas: cada una se
    convierte en un encabezado cuyo nivel es su profundidad en el árbol.  Así
    la tecla ``H`` y la lista de elementos funcionan en cualquier libro.

    Si el libro ya tiene encabezados propios no se toca nada.
    """
    from nucleo.marcas import es_encabezado, tipo_de_encabezado

    if any(es_encabezado(marca.tipo) for marca in marcas):
        return []
    if not indice:
        return []
    generados: list[Marca] = []
    vistas: set[int] = set()
    for raiz in indice:
        for entrada, profundidad in raiz.recorrer():
            if entrada.posicion in vistas or not entrada.titulo.strip():
                continue
            vistas.add(entrada.posicion)
            nivel = min(profundidad + 1, 6)
            generados.append(
                Marca(tipo_de_encabezado(nivel), entrada.posicion, entrada.titulo.strip(),
                      "", nivel, len(entrada.titulo.strip()))
            )
    log.info("El libro no tiene encabezados propios: se han generado %d desde el índice",
             len(generados))
    return generados


# ---------------------------------------------------------------------------
# Analizador
# ---------------------------------------------------------------------------

class AnalizadorEPUB(Analizador):
    """Convierte un archivo EPUB en un :class:`~nucleo.documento.Documento`."""

    extensiones = (".epub",)
    descripcion = _("Libros EPUB")

    def analizar(self, ruta: str | os.PathLike, opciones: OpcionesAnalisis) -> Documento:
        """Analiza el EPUB completo.

        :raises ErrorFormato: Si el archivo está dañado, cifrado o vacío.
        """
        destino = Path(ruta)
        log.info("Analizando EPUB: %s (%.1f MB)", destino, destino.stat().st_size / 1048576)
        try:
            archivo = zipfile.ZipFile(destino)
        except zipfile.BadZipFile:
            raise ErrorFormato(_("El archivo está dañado o no es un EPUB (no se puede abrir como ZIP)."))
        except OSError as error:
            raise ErrorFormato(_("No se ha podido abrir el archivo: %s") % error)

        with archivo:
            if any(nombre.startswith("META-INF/encryption.xml") for nombre in archivo.namelist()):
                _avisar_del_cifrado(archivo)
            ruta_opf = _localizar_opf(archivo)
            carpeta = posixpath.dirname(ruta_opf)
            with cronometro(log, "lectura del OPF"):
                paquete = _leer_paquete(_leer_entrada(archivo, ruta_opf), carpeta)
            if not paquete.lomo:
                raise ErrorFormato(_("El documento no declara ningún capítulo en su orden de lectura."))

            texto, marcas, posiciones_id, secciones, paginas_incrustadas = self._convertir_lomo(
                archivo, paquete, opciones
            )
            if not texto.strip():
                raise ErrorFormato(
                    _("El libro no contiene texto legible. Puede estar protegido con DRM "
                    "o formado únicamente por imágenes escaneadas.")
                )

            with cronometro(log, "construccion del indice"):
                indice = self._construir_indice(archivo, paquete, secciones, posiciones_id)
                paginas = self._construir_paginas(
                    archivo, paquete, secciones, posiciones_id, paginas_incrustadas
                )

        for posicion, rotulo in paginas:
            marcas.append(Marca(TipoMarca.SALTO_PAGINA, posicion, rotulo))

        marcas.extend(_encabezados_desde_indice(marcas, indice))

        if not paquete.metadatos.titulo:
            paquete.metadatos.titulo = destino.stem

        documento = Documento(
            texto=texto,
            marcas=marcas,
            indice=indice,
            posiciones_id=posiciones_id,
            secciones=secciones,
            metadatos=paquete.metadatos,
            ruta_archivo=str(destino),
        )
        # El EPUB no pasa por «montar» —arma el documento por su cuenta, porque
        # tiene índice y páginas propios—, así que el informe de accesibilidad
        # se redacta aquí, con lo que el libro declara de sí mismo por delante.
        paquete.metadatos.accesibilidad = accesibilidad.resumen(
            documento, paquete.accesibilidad)
        log.info(
            "EPUB analizado: %s | %d caracteres | %d secciones | %d marcas | "
            "%d entradas de indice | %d paginas",
            paquete.metadatos.titulo, len(texto), len(secciones), len(marcas),
            len(documento.indice_plano()), len(paginas),
        )
        return documento

    # -- conversión del lomo -------------------------------------------------

    def _convertir_lomo(self, archivo: zipfile.ZipFile, paquete: _Paquete,
                        opciones: OpcionesAnalisis):
        """Convierte todos los capítulos y los une en un único texto.

        Cada capítulo se convierte por separado, con posiciones locales, y
        después se desplazan sus marcas al lugar que le corresponde en el
        texto global.  Es la misma estrategia que usa Paperback, y es lo que
        permite tratar el libro entero como un solo bloque de texto.
        """
        conversor = ConversorXHTML(
            tablas_en_linea=opciones.tablas_en_linea,
            anunciar_imagenes_sin_texto=opciones.anunciar_imagenes_sin_texto,
            marcar_llamadas_de_nota=getattr(opciones, "marcar_llamadas_de_nota", False),
        )
        partes: list[str] = []
        marcas: list[Marca] = []
        posiciones_id: dict[str, int] = {}
        secciones: list[Seccion] = []
        paginas: list[tuple[int, str]] = []
        desplazamiento = 0
        fallos = 0

        total_capitulos = len(paquete.lomo)
        with cronometro(log, "conversion de los capitulos") as datos:
            for numero, referencia in enumerate(paquete.lomo, start=1):
                opciones.progreso.paso(
                    numero - 1, total_capitulos,
                    _("Capítulo %d de %d") % (numero, total_capitulos))
                entrada = paquete.manifiesto.get(referencia)
                if entrada is None:
                    log.warning("El capítulo %s no está en el manifiesto", referencia)
                    fallos += 1
                    continue
                if entrada.tipo_medio and entrada.tipo_medio not in _TIPOS_CONTENIDO:
                    log.debug("Se omite %s por tipo de medio %s", entrada.ruta, entrada.tipo_medio)
                    continue
                try:
                    datos_capitulo = _leer_entrada(archivo, entrada.ruta)
                except KeyError:
                    log.warning("Falta en el archivo el capítulo %s", entrada.ruta)
                    fallos += 1
                    continue
                except Exception as error:
                    registrar_excepcion(log, "Error leyendo %s" % entrada.ruta, error)
                    fallos += 1
                    continue
                try:
                    resultado = conversor.convertir(datos_capitulo)
                except Exception as error:
                    registrar_excepcion(log, "Error convirtiendo %s" % entrada.ruta, error)
                    fallos += 1
                    continue
                if not resultado.texto:
                    continue

                inicio = desplazamiento
                partes.append(resultado.texto)
                longitud = len(resultado.texto) + 1  # el salto de línea que las separa
                desplazamiento += longitud

                marcas.append(
                    Marca(TipoMarca.SALTO_SECCION, inicio, _("Sección %d") % numero, entrada.ruta)
                )
                for marca in resultado.marcas:
                    # Los enlaces y las imágenes guardan una ruta relativa al
                    # capítulo; aquí se convierte en una ruta absoluta dentro
                    # del libro, para poder resolverla desde cualquier punto.
                    if marca.referencia and marca.tipo in _TIPOS_CON_RUTA:
                        referencia_absoluta = resolver_destino(entrada.ruta, marca.referencia)
                        marcas.append(
                            marca._replace(
                                posicion=marca.posicion + inicio, referencia=referencia_absoluta
                            )
                        )
                    else:
                        marcas.append(marca._replace(posicion=marca.posicion + inicio))
                for identificador, posicion in resultado.posiciones_id.items():
                    absoluta = posicion + inicio
                    posiciones_id.setdefault(identificador, absoluta)
                    posiciones_id["%s#%s" % (entrada.ruta, identificador)] = absoluta
                for posicion, rotulo in resultado.paginas:
                    paginas.append((posicion + inicio, rotulo))
                secciones.append(Seccion(entrada.ruta, inicio, desplazamiento))
            datos["capitulos"] = len(secciones)
            datos["fallidos"] = fallos

        texto = "\n".join(partes)
        return texto, marcas, posiciones_id, secciones, paginas

    # -- índice y páginas ----------------------------------------------------

    def _construir_indice(self, archivo, paquete, secciones, posiciones_id) -> list[ElementoIndice]:
        """Obtiene el índice del libro, del documento de navegación o del NCX."""
        if paquete.ruta_nav:
            try:
                contenido = _leer_entrada(archivo, paquete.ruta_nav)
                entradas = _indice_desde_nav(
                    contenido, paquete.ruta_nav, secciones, posiciones_id, ("toc", "doc-toc")
                )
                if entradas:
                    log.debug("Índice obtenido del documento de navegación (%d entradas)", len(entradas))
                    return entradas
            except Exception as error:
                registrar_excepcion(log, "Error leyendo el documento de navegación", error)
        if paquete.ruta_ncx:
            try:
                contenido = _leer_entrada(archivo, paquete.ruta_ncx)
                entradas = _indice_desde_ncx(
                    contenido, paquete.ruta_ncx, secciones, posiciones_id, "navMap", "navPoint"
                )
                if entradas:
                    log.debug("Índice obtenido del archivo NCX (%d entradas)", len(entradas))
                    return entradas
            except Exception as error:
                registrar_excepcion(log, "Error leyendo el NCX", error)
        log.info("El libro no tiene índice; se usarán los encabezados")
        return []

    def _construir_paginas(self, archivo, paquete, secciones, posiciones_id,
                           incrustadas: list[tuple[int, str]]) -> list[tuple[int, str]]:
        """Obtiene la lista de páginas del libro, si la tiene.

        Se prueba, en este orden: la lista de páginas del documento de
        navegación, la del NCX y, por último, las marcas ``epub:type="pagebreak"``
        encontradas dentro del propio texto.
        """
        if paquete.ruta_nav:
            try:
                contenido = _leer_entrada(archivo, paquete.ruta_nav)
                entradas = _indice_desde_nav(
                    contenido, paquete.ruta_nav, secciones, posiciones_id,
                    ("page-list", "doc-pagelist"),
                )
                if entradas:
                    return [(entrada.posicion, entrada.titulo) for entrada in entradas]
            except Exception as error:
                registrar_excepcion(log, "Error leyendo la lista de páginas", error)
        if paquete.ruta_ncx:
            try:
                contenido = _leer_entrada(archivo, paquete.ruta_ncx)
                entradas = _indice_desde_ncx(
                    contenido, paquete.ruta_ncx, secciones, posiciones_id, "pageList", "pageTarget"
                )
                if entradas:
                    return [(entrada.posicion, entrada.titulo) for entrada in entradas]
            except Exception as error:
                registrar_excepcion(log, "Error leyendo la lista de páginas del NCX", error)
        return sorted(incrustadas)

    # -- recursos ------------------------------------------------------------

    def extraer_recurso(self, ruta: str | os.PathLike, interna: str) -> bytes | None:
        """Extrae un archivo interno del EPUB (normalmente una imagen)."""
        if not interna:
            return None
        try:
            with zipfile.ZipFile(Path(ruta)) as archivo:
                return _leer_entrada(archivo, interna)
        except (KeyError, OSError, zipfile.BadZipFile) as error:
            log.debug("No se ha podido extraer %s: %s", interna, error)
            return None


registrar(AnalizadorEPUB())
