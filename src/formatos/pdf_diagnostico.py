# -*- coding: utf-8 -*-
"""Diagnóstico de un PDF: qué es el archivo antes de intentar leerlo.

Abrir un PDF a ciegas y ver qué sale funciona casi siempre y falla justo en los
casos que más importan: el archivo cifrado que sí se podía abrir, el que está
dañado y se arregla con una copia normalizada, el que tiene texto pero es una
fotografía con un número de página encima, el que declara estar etiquetado y no
lo está.

Este módulo mira el archivo **antes** y responde a cuatro preguntas:

1. **¿Se puede abrir?**  Distinguiendo las dos maneras de cifrar un PDF, que se
   confunden constantemente y no se parecen en nada (véase :class:`Cifrado`).
2. **¿Qué trae?**  Estructura, idioma, marcadores, formularios, firmas,
   adjuntos, JavaScript, fuentes incrustadas, metadatos.
3. **¿Qué clase de página es cada una?**  Digital, escaneada, híbrida o vacía,
   que es lo que decide si hay que reconocerla con OCR.
4. **¿Qué habría que arreglar?**  En forma de :class:`~formatos.pdf_hallazgos.Hallazgo`.

Reparto de trabajo entre los dos motores
----------------------------------------

**PDFium** —el que ya usa el programa— sabe sacar texto, rasterizar y leer el
árbol de estructura, y es rápido.  Lo que no expone es el interior del archivo:
el catálogo, el diccionario de cifrado, los campos de formulario, las fuentes.

**pypdf** sí, porque es Python puro y le da igual el rendimiento.  Y ahí está la
trampa: recorrer las mil páginas de un informe con pypdf para contar sus
fuentes cuesta más que convertir el documento entero.  Por eso aquí:

* lo del **documento** —una sola lectura del catálogo— se hace con pypdf;
* lo de **cada página** se hace con la geometría que PDFium ya ha sacado, sin
  volver a abrir nada;
* lo que exigiría recorrerlo todo —las fuentes— se hace **sobre una muestra**,
  igual que ya se hace con el etiquetado, porque un PDF usa las mismas cuatro
  fuentes de la primera a la última página.

pypdf es opcional: si no está, el diagnóstico se queda en lo que PDFium sabe y
el programa funciona igual.  Lo que no se puede comprobar no se afirma.

Cómo se decide que una página está escaneada
--------------------------------------------

No por contar caracteres.  Una página escaneada suele traer texto de verdad: el
número de página, una marca de agua, el sello de la biblioteca que digitalizó
el libro.  Contando caracteres, esa página parece tener texto y se queda sin
reconocer.

Lo que se mira es **dónde** está el texto.  Se descarta el marco exterior de la
página —donde viven encabezados, pies y numeración— y se pregunta si queda algo
dentro.  Si el cuerpo de la página está vacío y además la ocupa una imagen
grande, es un escaneado, tenga los caracteres que tenga.
"""

from __future__ import annotations

import hashlib
import re
from enum import IntEnum
from pathlib import Path
from typing import Iterable, NamedTuple

from nucleo.idioma import _
from nucleo.registro import obtener_registro, registrar_excepcion

from .pdf_hallazgos import ColeccionHallazgos, Hallazgo, Severidad, aviso, grave, informativo

log = obtener_registro(__name__)

#: Proporción de la página, por cada lado, que se considera margen y no cuenta
#: como cuerpo.  Con 0,125 el marco descartado es la octava parte de cada
#: borde, que es donde caben un encabezado, un pie y la numeración sin comerse
#: el texto de un documento maquetado con márgenes normales.
MARGEN = 0.125

#: Caracteres dentro del cuerpo por debajo de los cuales la página no se
#: considera legible.  Es el mismo umbral que usaba el analizador, conservado a
#: propósito para no cambiar el comportamiento de los documentos que ya
#: funcionaban.
MINIMO_CUERPO = 40

#: Proporción de la página cubierta por imágenes a partir de la cual se
#: sospecha de un escaneado.  Una lámina a sangre ocupa casi el 100 %; una
#: figura de un artículo, entre el 20 y el 40 %.
IMAGEN_DOMINANTE = 0.55

#: Cuántas páginas se muestrean para las comprobaciones caras (fuentes).  Una
#: docena repartida por todo el documento: un PDF usa las mismas fuentes de
#: principio a fin porque las incrusta el programa que lo generó.
MUESTRA = 12

#: Profundidad máxima al buscar una clave dentro del catálogo.  Un PDF dañado
#: puede traer ciclos y sin tope el recorrido no termina.
PROFUNDIDAD = 12

#: Nombres de las catorce fuentes estándar del PDF, que no se incrustan porque
#: el lector las tiene que tener.  No incrustarlas no es un defecto.
_ESTANDAR = frozenset({
    "helvetica", "courier", "times-roman", "times", "symbol", "zapfdingbats",
    "arial",
})


class Cifrado(IntEnum):
    """Cómo está cifrado un PDF, que no es una pregunta de sí o no.

    Un PDF puede llevar **dos** contraseñas y se confunden todo el tiempo:

    * La de **propietario** solo limita imprimir, copiar o modificar.  El
      archivo se abre sin ella: cualquier lector lo hace, y el programa
      también.  Es el caso de casi todos los documentos «protegidos» que
      circulan —artículos de revista, boletines oficiales—, y tratarlos como
      inaccesibles sería dejar fuera buena parte de la literatura académica por
      un permiso que ni siquiera nos afecta: leer no es ni imprimir ni copiar.
    * La de **usuario** sí hace falta para descifrar el contenido.  Sin ella no
      hay nada que leer y hay que pedírsela a quien abre el documento.
    """

    #: Sin cifrar.
    NINGUNO = 0

    #: Cifrado con contraseña de propietario: se abre igual.
    PROPIETARIO = 1

    #: Cifrado con contraseña de usuario: hace falta para leerlo.
    USUARIO = 2


class ClasePagina(IntEnum):
    """Qué clase de página es, que es lo que decide si hay que reconocerla."""

    #: Texto de verdad en el cuerpo.  Se lee tal cual.
    DIGITAL = 0

    #: Texto en el cuerpo y además una imagen grande.  Un artículo con una
    #: figura a toda página, o un escaneado al que ya se le pasó un OCR.
    HIBRIDA = 1

    #: Sin texto útil y con una imagen que ocupa la página.  Hay que
    #: reconocerla.
    ESCANEADA = 2

    #: Algo de texto, pero muy poco para lo que ocupa la página.  Una
    #: digitalización a la que se le escapó media plana, o una portada.
    TEXTO_PARCIAL = 3

    #: Ni texto ni imagen.  Una separadora en blanco.  No hay nada que hacer.
    VACIA = 4


#: Frase con la que se anuncia cada clase de página.
_CLASES = {
    ClasePagina.DIGITAL: lambda: _("con texto"),
    ClasePagina.HIBRIDA: lambda: _("con texto e imagen"),
    ClasePagina.ESCANEADA: lambda: _("escaneada"),
    ClasePagina.TEXTO_PARCIAL: lambda: _("con poco texto"),
    ClasePagina.VACIA: lambda: _("en blanco"),
}


def nombre_clase(clase: ClasePagina) -> str:
    """Devuelve el nombre de una clase de página en el idioma de la interfaz."""
    return _CLASES.get(clase, lambda: _("desconocida"))()


def contar(cantidad: int, singular: str, plural: str) -> str:
    """Escribe «1 fuente» o «6 fuentes», que no es lo mismo al oído.

    Un informe de accesibilidad se escucha, y «1 fuentes sin incrustar» suena a
    programa mal hecho justo cuando lo que se pide es confianza en lo que
    cuenta.  Las dos formas se pasan enteras y traducidas porque en otros
    idiomas el plural no se hace añadiendo una letra al final.
    """
    return (singular if abs(cantidad) == 1 else plural) % cantidad


class Caja(NamedTuple):
    """Rectángulo en el sistema del PDF: origen abajo a la izquierda, en puntos."""

    izquierda: float
    abajo: float
    derecha: float
    arriba: float

    @property
    def ancho(self) -> float:
        """Anchura, nunca negativa."""
        return max(0.0, self.derecha - self.izquierda)

    @property
    def alto(self) -> float:
        """Altura, nunca negativa."""
        return max(0.0, self.arriba - self.abajo)

    @property
    def area(self) -> float:
        """Superficie en puntos cuadrados."""
        return self.ancho * self.alto

    def corta(self, otra: "Caja") -> bool:
        """Indica si dos rectángulos se solapan aunque sea en un punto."""
        return (self.izquierda < otra.derecha and self.derecha > otra.izquierda
                and self.abajo < otra.arriba and self.arriba > otra.abajo)


class Diagnostico:
    """Lo que se sabe de un PDF sin haberlo leído todavía.

    Es también lo que se anota en el registro al abrir y lo que alimenta la
    ventana de información del documento.
    """

    __slots__ = ("ruta", "huella", "tamano", "paginas", "cifrado", "danado",
                 "reparado", "linealizado", "marcado", "arbol_logico", "suspects",
                 "idioma", "titulo_xmp", "mostrar_titulo", "marcadores",
                 "formularios", "firmas", "adjuntos", "javascript", "version",
                 "fuentes", "fuentes_sin_incrustar", "fuentes_sin_unicode",
                 "hallazgos", "con_pypdf", "declara_pdfua", "role_map",
                 "xfa_dinamico", "capas_conmutables", "fuentes_mal_codificadas",
                 "con_metadatos")

    def __init__(self, ruta: Path) -> None:
        self.ruta = ruta
        self.huella = ""
        self.tamano = 0
        self.paginas = 0
        self.cifrado = Cifrado.NINGUNO
        self.danado = False
        self.reparado = False
        self.linealizado = False
        self.marcado = False
        self.arbol_logico = False
        self.suspects = False
        self.idioma = ""
        self.titulo_xmp = ""
        self.mostrar_titulo = False
        self.marcadores = 0
        self.formularios = 0
        self.firmas = 0
        self.adjuntos = 0
        self.javascript = False
        self.version = ""
        self.fuentes: set[str] = set()
        self.fuentes_sin_incrustar: set[str] = set()
        self.fuentes_sin_unicode: set[str] = set()
        #: Parte de PDF/UA que el archivo dice cumplir (0 si no dice nada).
        #: Es lo único que distingue un PDF etiquetado a conciencia de uno que
        #: salió etiquetado por casualidad (ISO 14289-1, 5).
        self.declara_pdfua = 0
        #: Si el catálogo trae flujo de metadatos XMP (ISO 14289-1, 7.1).
        self.con_metadatos = False
        #: Correspondencia que el documento declara entre sus etiquetas propias
        #: y las de la norma (ISO 14289-1, 7.1).
        self.role_map: dict[str, str] = {}
        #: Si el formulario es un XFA dinámico, que no se puede leer.
        self.xfa_dinamico = False
        #: Si hay capas de contenido opcional que se pueden encender y apagar
        #: solas, con lo que el texto que se lee puede no ser el que se ve.
        self.capas_conmutables = False
        #: Fuentes TrueType con la codificación mal declarada.
        self.fuentes_mal_codificadas: set[str] = set()
        self.hallazgos = ColeccionHallazgos()
        #: Si el diagnóstico pudo usar pypdf.  Sin él, lo que no se ve no se
        #: afirma: ``arbol_logico`` a ``False`` querría decir «no lo sé», y
        #: eso confundiría, así que se dice aparte.
        self.con_pypdf = False

    def resumen(self) -> str:
        """Frase para el registro y la ventana de información.

        Solo se cuenta lo que hay: enumerar los ceros esconde lo que importa.
        """
        partes: list[str] = []
        if self.version:
            partes.append(_("PDF %s") % self.version)
        if self.paginas:
            partes.append(contar(self.paginas, _("%d página"), _("%d páginas")))
        if self.cifrado is Cifrado.PROPIETARIO:
            partes.append(_("cifrado solo contra impresión o copia: se abre igual"))
        elif self.cifrado is Cifrado.USUARIO:
            partes.append(_("cifrado con contraseña"))
        if self.reparado:
            partes.append(_("abierto desde una copia reparada"))
        if self.marcadores:
            partes.append(contar(self.marcadores, _("%d marcador"), _("%d marcadores")))
        if self.formularios:
            partes.append(contar(self.formularios, _("%d campo de formulario"),
                                 _("%d campos de formulario")))
        if self.firmas:
            partes.append(contar(self.firmas, _("%d firma digital"),
                                 _("%d firmas digitales")))
        if self.adjuntos:
            partes.append(contar(self.adjuntos, _("%d archivo adjunto"),
                                 _("%d archivos adjuntos")))
        if self.javascript:
            partes.append(_("contiene JavaScript, que no se ejecuta"))
        if self.fuentes_sin_incrustar:
            partes.append(contar(len(self.fuentes_sin_incrustar),
                                 _("%d fuente sin incrustar"),
                                 _("%d fuentes sin incrustar")))
        if not partes:
            return ""
        return "; ".join(partes) + "."


def huella_sha256(ruta: Path, tope: int = 64 * 1024 * 1024) -> str:
    """Calcula el SHA-256 del archivo, que es su nombre verdadero.

    Sirve para atar las correcciones del usuario a **este** archivo y no a su
    ruta: un libro renombrado o movido sigue siendo el mismo, y un archivo
    distinto con el mismo nombre no debe heredar las correcciones del anterior.

    :param tope: Máximo de bytes que se leen.  Un PDF de dos gigas tardaría
                 varios segundos en resumirse entero y no haría falta: los
                 primeros sesenta y cuatro megas más el tamaño total ya
                 distinguen dos archivos que no sean el mismo.
    """
    resumen = hashlib.sha256()
    leidos = 0
    try:
        with open(ruta, "rb") as archivo:
            while leidos < tope:
                trozo = archivo.read(min(1024 * 1024, tope - leidos))
                if not trozo:
                    break
                resumen.update(trozo)
                leidos += len(trozo)
        resumen.update(str(ruta.stat().st_size).encode("ascii"))
    except OSError as error:
        log.debug("No se ha podido resumir %s: %s", ruta, error)
        return ""
    return resumen.hexdigest()


def cifrado_de(ruta: Path, contrasena: str = "") -> tuple[Cifrado, object]:
    """Averigua cómo está cifrado un PDF y lo deja abierto si se puede.

    Devuelve ``(clase de cifrado, lector de pypdf o None)``.  El lector se
    devuelve ya descifrado para no repetir el trabajo.

    La clave está en probar **la contraseña vacía** antes de rendirse: es lo
    que distingue el PDF que solo prohíbe imprimir —que se abre— del que hay
    que pedirle la contraseña al usuario.  Un lector que no lo intenta rechaza
    documentos perfectamente legibles.
    """
    lector = _lector_pypdf(ruta)
    if lector is None:
        return Cifrado.NINGUNO, None
    try:
        if not lector.is_encrypted:
            return Cifrado.NINGUNO, lector
    except Exception:
        return Cifrado.NINGUNO, lector
    for intento in ([contrasena] if contrasena else []) + [""]:
        try:
            resultado = int(lector.decrypt(intento))
        except Exception as error:
            log.debug("El descifrado ha fallado: %s", error)
            continue
        if resultado == 2:      # contraseña de propietario aceptada
            return Cifrado.PROPIETARIO, lector
        if resultado == 1:      # contraseña de usuario aceptada
            # Si la que valió fue la vacía, el documento no tiene contraseña de
            # usuario de verdad: es de propietario y se abre solo.
            return (Cifrado.PROPIETARIO if not intento else Cifrado.USUARIO), lector
    return Cifrado.USUARIO, lector


def diagnosticar(ruta: Path, contrasena: str = "", lector=None) -> Diagnostico:
    """Inventaría el archivo con una sola lectura de su catálogo.

    :param lector: Lector de pypdf ya abierto y descifrado, si lo hay.  Lo pasa
                   :func:`cifrado_de` para no volver a leer el archivo.
    """
    informe = Diagnostico(ruta)
    try:
        informe.tamano = ruta.stat().st_size
    except OSError:
        informe.tamano = 0
    informe.huella = huella_sha256(ruta)
    informe.version = _version_de_cabecera(ruta)
    informe.linealizado = _esta_linealizado(ruta)

    if lector is None:
        informe.cifrado, lector = cifrado_de(ruta, contrasena)
    if lector is None:
        # Sin pypdf no se puede mirar dentro.  No es un fallo: el programa lee
        # el PDF igual con PDFium, solo que sin informe.
        return informe
    informe.con_pypdf = True
    _inventariar(informe, lector)
    _redactar_hallazgos(informe)
    return informe


def clasificar_pagina(cajas_texto: Iterable[Caja], area_imagenes: float,
                      ancho: float, alto: float) -> tuple[ClasePagina, int]:
    """Decide qué clase de página es a partir de su geometría.

    Es una función pura —sin motor de PDF por medio— para poder probarla y para
    que dé lo mismo si el texto viene de PDFium, de pdfplumber o de un OCR.

    :param cajas_texto: Rectángulos del texto de la página, con su contenido ya
                        medido: lo que interesa es dónde caen, no qué dicen.
    :param area_imagenes: Superficie total en puntos cuadrados que ocupan las
                          imágenes de la página.
    :return: ``(clase, caracteres que hay dentro del cuerpo)``.
    """
    if ancho <= 0 or alto <= 0:
        return ClasePagina.VACIA, 0
    cuerpo = Caja(ancho * MARGEN, alto * MARGEN,
                  ancho * (1 - MARGEN), alto * (1 - MARGEN))
    dentro = 0
    for caja, largo in _con_longitud(cajas_texto):
        if caja.corta(cuerpo):
            dentro += largo
    proporcion = area_imagenes / (ancho * alto) if ancho * alto else 0.0
    dominante = proporcion >= IMAGEN_DOMINANTE

    if dentro >= MINIMO_CUERPO:
        return (ClasePagina.HIBRIDA if dominante else ClasePagina.DIGITAL), dentro
    if dominante:
        return ClasePagina.ESCANEADA, dentro
    if dentro or area_imagenes:
        return ClasePagina.TEXTO_PARCIAL, dentro
    return ClasePagina.VACIA, dentro


# ---------------------------------------------------------------------------
# Interior
# ---------------------------------------------------------------------------

def _con_longitud(cajas: Iterable[Caja]):
    """Empareja cada caja con la longitud del texto que se le asocia.

    Se admiten dos formas de llamar a :func:`clasificar_pagina`: con cajas a
    secas —y entonces cada una cuenta como un carácter, que basta para saber si
    hay algo— o con pares ``(caja, caracteres)``, que es lo que da el conteo
    real.  Aceptar las dos evita obligar a quien solo tiene la geometría a
    inventarse una longitud.
    """
    for elemento in cajas:
        if isinstance(elemento, Caja):
            yield elemento, 1
        else:
            caja, largo = elemento
            yield caja, int(largo)


def _lector_pypdf(ruta: Path):
    """Abre el archivo con pypdf, o devuelve ``None`` si no se puede.

    Nunca lanza: el diagnóstico es un extra y no debe impedir abrir un libro
    que PDFium sí sabe leer.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        log.debug("pypdf no está instalado: el diagnóstico será el básico.")
        return None
    try:
        # «strict=False» es imprescindible: en modo estricto pypdf se niega a
        # leer archivos que el resto del mundo abre sin problema, y el objetivo
        # aquí es justamente enterarse de lo que traen los archivos imperfectos.
        return PdfReader(str(ruta), strict=False)
    except Exception as error:
        log.debug("pypdf no ha podido abrir %s: %s", ruta, error)
        return None


def _inventariar(informe: Diagnostico, lector) -> None:
    """Rellena el diagnóstico leyendo el catálogo una sola vez."""
    try:
        informe.paginas = len(lector.pages)
    except Exception as error:
        informe.danado = True
        registrar_excepcion(log, "No se ha podido contar las páginas del PDF", error)
        return
    raiz = _catalogo(lector)
    if raiz is None:
        return
    informe.arbol_logico = "/StructTreeRoot" in raiz
    marcado = _resolver(raiz.get("/MarkInfo"))
    if isinstance(marcado, dict):
        informe.marcado = bool(marcado.get("/Marked"))
        informe.suspects = bool(marcado.get("/Suspects"))
    informe.idioma = _texto(raiz.get("/Lang"))
    preferencias = _resolver(raiz.get("/ViewerPreferences"))
    if isinstance(preferencias, dict):
        informe.mostrar_titulo = bool(preferencias.get("/DisplayDocTitle"))
    informe.titulo_xmp = _titulo_xmp(lector)
    informe.javascript = _contiene(raiz, ("/JavaScript", "/JS"))
    informe.marcadores = _contar_marcadores(lector)
    informe.formularios, informe.firmas = _contar_campos(lector)
    informe.adjuntos = _contar_adjuntos(lector)
    informe.con_metadatos = "/Metadata" in raiz
    informe.declara_pdfua = _parte_pdfua(lector)
    informe.role_map = _role_map(raiz)
    informe.xfa_dinamico = _xfa_dinamico(raiz)
    informe.capas_conmutables = _capas_conmutables(raiz)
    _muestrear_fuentes(informe, lector)


def _parte_pdfua(lector) -> int:
    """Parte de PDF/UA que el archivo declara cumplir, o ``0``.

    Va en el XMP del catálogo, como ``pdfuaid:part``.  Sin buscarlo con
    espacios de nombres: el flujo se lee como texto y se busca la propiedad,
    que puede venir como atributo o como elemento según quién lo escribiera.
    Es una declaración del productor, no una comprobación: dice qué dijo
    cumplir, no qué cumple (ISO 14289-1, 5).
    """
    import re

    try:
        metadatos = getattr(lector, "xmp_metadata", None)
        crudo = getattr(metadatos, "stream", None)
        datos = crudo.get_data() if crudo is not None else b""
    except Exception:
        return 0
    if not datos:
        return 0
    try:
        texto = datos.decode("utf-8", errors="replace")
    except Exception:
        return 0
    hallado = re.search(r"pdfuaid:part\s*=\s*[\"\'](\d+)|<pdfuaid:part>\s*(\d+)", texto)
    if not hallado:
        return 0
    try:
        return int(hallado.group(1) or hallado.group(2))
    except (TypeError, ValueError):
        return 0


def _role_map(raiz) -> dict:
    """Correspondencia entre las etiquetas propias del documento y las de la norma.

    Un PDF puede inventarse nombres de etiqueta —«Titular», «Parrafo2»— si dice
    a qué etiqueta normalizada equivale cada uno.  Sin esa correspondencia, un
    lector de pantalla no sabe qué es cada cosa (ISO 14289-1, 7.1).
    """
    arbol = _resolver(raiz.get("/StructTreeRoot"))
    if not isinstance(arbol, dict):
        return {}
    mapa = _resolver(arbol.get("/RoleMap"))
    if not isinstance(mapa, dict):
        return {}
    resultado = {}
    try:
        for clave, valor in mapa.items():
            nombre = str(clave).lstrip("/")
            destino = str(_resolver(valor) or "").lstrip("/")
            if nombre and destino:
                resultado[nombre] = destino
    except Exception:
        return {}
    return resultado


def _xfa_dinamico(raiz) -> bool:
    """Indica si el formulario es un XFA dinámico.

    Un XFA dinámico no es un PDF con campos: es un formulario que se dibuja
    solo al abrirlo, y de él no se puede sacar ni texto ni estructura.  La
    norma lo prohíbe justamente por eso (ISO 14289-1, 7.15).
    """
    formulario = _resolver(raiz.get("/AcroForm"))
    if not isinstance(formulario, dict) or "/XFA" not in formulario:
        return False
    # Un XFA «estático» trae además los campos normales y las apariencias, y
    # entonces el PDF se lee igual.  El dinámico se distingue porque pide que
    # se regeneren las apariencias y no trae campos utilizables.
    if formulario.get("/NeedAppearances"):
        return True
    try:
        campos = _resolver(formulario.get("/Fields")) or []
        return len(campos) == 0
    except Exception:
        return False


def _capas_conmutables(raiz) -> bool:
    """Indica si hay capas de contenido opcional que se encienden solas.

    La clave ``AS`` de una configuración de capas hace que el visor decida qué
    se ve según el uso —pantalla, impresión, zoom—, con lo que el texto que se
    lee puede no ser el que se ve.  La norma la prohíbe (ISO 14289-1, 7.10).
    """
    propiedades = _resolver(raiz.get("/OCProperties"))
    if not isinstance(propiedades, dict):
        return False
    configuraciones = [_resolver(propiedades.get("/D"))]
    try:
        configuraciones.extend(_resolver(c) for c in (_resolver(propiedades.get("/Configs")) or []))
    except Exception:
        pass
    for configuracion in configuraciones:
        if isinstance(configuracion, dict) and "/AS" in configuracion:
            return True
    return False


def _catalogo(lector):
    """Devuelve el catálogo del documento, o ``None``."""
    for atributo in ("root_object", "trailer"):
        try:
            objeto = getattr(lector, atributo, None)
            if objeto is None:
                continue
            raiz = objeto.get("/Root") if atributo == "trailer" else objeto
            raiz = _resolver(raiz)
            if isinstance(raiz, dict):
                return raiz
        except Exception:
            continue
    return None


def _resolver(objeto):
    """Sigue una referencia indirecta de pypdf hasta el objeto real."""
    try:
        return objeto.get_object() if hasattr(objeto, "get_object") else objeto
    except Exception:
        return None


def _texto(valor) -> str:
    """Convierte un valor del PDF en una cadena limpia."""
    try:
        valor = _resolver(valor)
        return str(valor).strip() if valor is not None else ""
    except Exception:
        return ""


def _contiene(diccionario, claves: tuple[str, ...], profundidad: int = 0,
              vistos: set[int] | None = None) -> bool:
    """Busca cualquiera de esas claves dentro del catálogo, con tope.

    El tope de profundidad y el conjunto de objetos ya vistos no son
    prudencia teórica: un PDF dañado puede tener ciclos, y sin ellos esto no
    termina nunca.
    """
    if profundidad > PROFUNDIDAD:
        return False
    vistos = vistos if vistos is not None else set()
    if id(diccionario) in vistos:
        return False
    vistos.add(id(diccionario))
    try:
        elementos = diccionario.items() if hasattr(diccionario, "items") else ()
    except Exception:
        return False
    for clave, valor in elementos:
        if str(clave) in claves:
            return True
        hijo = _resolver(valor)
        if isinstance(hijo, dict) and _contiene(hijo, claves, profundidad + 1, vistos):
            return True
    return False


def _titulo_xmp(lector) -> str:
    """Lee el título declarado en los metadatos XMP, si los hay.

    Es el título que la norma PDF/UA exige y el que un lector de pantalla
    anuncia al abrir la ventana; el del diccionario ``/Info`` es el antiguo y
    muchos archivos traen los dos y distintos.
    """
    try:
        xmp = lector.xmp_metadata
        if xmp is None:
            return ""
        titulo = getattr(xmp, "dc_title", None)
        if isinstance(titulo, dict):
            return str(next(iter(titulo.values()), "")).strip()
        return str(titulo or "").strip()
    except Exception:
        return ""


def _contar_marcadores(lector) -> int:
    """Cuenta las entradas del índice del propio PDF, con anidamiento."""
    def contar(entradas, profundidad: int = 0) -> int:
        if profundidad > PROFUNDIDAD:
            return 0
        total = 0
        for entrada in entradas:
            if isinstance(entrada, list):
                total += contar(entrada, profundidad + 1)
            else:
                total += 1
        return total

    try:
        return contar(list(lector.outline))
    except Exception:
        return 0


def _contar_campos(lector) -> tuple[int, int]:
    """Cuenta campos de formulario y, de ellos, cuántos son firmas."""
    try:
        campos = lector.get_fields() or {}
    except Exception:
        return 0, 0
    firmas = 0
    for campo in campos.values():
        try:
            if str(campo.get("/FT", "")) == "/Sig":
                firmas += 1
        except Exception:
            continue
    return len(campos), firmas


def _contar_adjuntos(lector) -> int:
    """Cuenta los archivos incrustados, que nunca se abren ni se ejecutan."""
    try:
        return len(getattr(lector, "attachments", {}) or {})
    except Exception:
        return 0


def _muestrear_fuentes(informe: Diagnostico, lector) -> None:
    """Mira las fuentes de una muestra de páginas repartida por el documento.

    Una fuente **sin incrustar** obliga al lector a sustituirla, y con ello se
    pierde el aspecto pero no el texto.  Una fuente sin tabla ``ToUnicode`` es
    mucho peor: el texto que se extrae de ella no son letras sino los códigos
    internos de la fuente, y es exactamente el motivo por el que algunos PDF
    dan un galimatías al copiarlos.  Detectarlo antes explica por qué un
    documento se leerá mal aunque «tenga texto».
    """
    total = informe.paginas
    if not total:
        return
    paso = max(1, total // MUESTRA)
    for numero in range(0, total, paso):
        try:
            recursos = _resolver(lector.pages[numero].get("/Resources"))
            fuentes = _resolver(recursos.get("/Font")) if isinstance(recursos, dict) else None
            if not isinstance(fuentes, dict):
                continue
            for referencia in fuentes.values():
                _anotar_fuente(informe, _resolver(referencia))
        except Exception as error:
            log.debug("No se han podido leer las fuentes de la página %d: %s",
                      numero + 1, error)


def _anotar_fuente(informe: Diagnostico, fuente) -> None:
    """Anota una fuente y si le falta algo para que su texto sea legible."""
    if not isinstance(fuente, dict):
        return
    nombre = _texto(fuente.get("/BaseFont")).lstrip("/")
    # Las fuentes con subconjunto incrustado llevan un prefijo de seis letras
    # y un signo más («ABCDEF+Arial»); estorba para comparar y no dice nada.
    nombre = re.sub(r"^[A-Z]{6}\+", "", nombre)
    if not nombre:
        return
    informe.fuentes.add(nombre)
    if _texto_ilegible(fuente):
        informe.fuentes_sin_unicode.add(nombre)
    if _codificacion_mal_declarada(fuente):
        informe.fuentes_mal_codificadas.add(nombre)
    if nombre.split("-")[0].split(",")[0].lower() in _ESTANDAR:
        return
    descriptores = [fuente.get("/FontDescriptor")]
    for descendiente in _resolver(fuente.get("/DescendantFonts")) or []:
        hijo = _resolver(descendiente)
        if isinstance(hijo, dict):
            descriptores.append(hijo.get("/FontDescriptor"))
    for referencia in descriptores:
        descriptor = _resolver(referencia)
        if isinstance(descriptor, dict) and any(
                clave in descriptor for clave in ("/FontFile", "/FontFile2", "/FontFile3")):
            return
    informe.fuentes_sin_incrustar.add(nombre)


def _codificacion_mal_declarada(fuente: dict) -> bool:
    """Indica si una TrueType declara su codificación al revés de lo que exige la norma.

    Son dos reglas complementarias y las dos van sobre lo mismo (ISO 14289-1,
    7.21.6): una TrueType **no simbólica** tiene que decir que usa
    ``WinAnsiEncoding`` o ``MacRomanEncoding``, porque son las dos tablas
    conocidas que traducen sus códigos a letras; una TrueType **simbólica** no
    tiene que declarar codificación ninguna, porque la suya va dentro del
    propio archivo de la fuente y declarar otra la contradice.

    En los dos casos el resultado es el mismo y se nota al leer: el texto sale,
    pero con las letras cambiadas.
    """
    if str(fuente.get("/Subtype", "")) != "/TrueType":
        return False
    descriptor = _resolver(fuente.get("/FontDescriptor"))
    if not isinstance(descriptor, dict):
        return False
    try:
        # El bit 3 de las banderas (valor 4) es el que marca la fuente como
        # simbólica.
        simbolica = bool(int(descriptor.get("/Flags", 0)) & 4)
    except (TypeError, ValueError):
        return False
    codificacion = _resolver(fuente.get("/Encoding"))
    if simbolica:
        return codificacion is not None
    nombre = str(codificacion.get("/BaseEncoding", "")) if isinstance(codificacion, dict)         else str(codificacion or "")
    return nombre not in ("/WinAnsiEncoding", "/MacRomanEncoding")


def _texto_ilegible(fuente: dict) -> bool:
    """Indica si de esa fuente no se puede recuperar el texto real.

    Es la comprobación que más fácil sería exagerar, y exagerarla arruinaría el
    aviso: casi ninguna fuente trae ``ToUnicode`` y casi todas se leen
    perfectamente, porque el texto se recupera de su **codificación**.  Solo
    hay un problema de verdad cuando se juntan las tres cosas:

    * no hay ``ToUnicode`` que traduzca códigos a letras;
    * la codificación no es una de las estándar (``WinAnsi``, ``MacRoman``),
      que sí son una traducción conocida;
    * y la fuente se declara **simbólica**, es decir, sus códigos significan lo
      que le dé la gana al archivo.

    Eso es lo que produce el galimatías al copiar de ciertos PDF, y es lo único
    que merece avisar, porque su remedio —reconocer la página con OCR— es caro.
    """
    if "/ToUnicode" in fuente:
        return False
    subtipo = str(fuente.get("/Subtype", ""))
    if subtipo == "/Type0":
        # Las compuestas con codificación de identidad sí necesitan ToUnicode;
        # con una CMap con nombre, la traducción está publicada y se conoce.
        return str(fuente.get("/Encoding", "")).startswith("/Identity")
    codificacion = _resolver(fuente.get("/Encoding"))
    nombre = str(codificacion.get("/BaseEncoding", "")) if isinstance(codificacion, dict) \
        else str(codificacion or "")
    if nombre in ("/WinAnsiEncoding", "/MacRomanEncoding", "/MacExpertEncoding",
                  "/StandardEncoding"):
        return False
    descriptor = _resolver(fuente.get("/FontDescriptor"))
    if not isinstance(descriptor, dict):
        # Sin descriptor solo quedan las catorce fuentes estándar, que tienen
        # una codificación conocida por definición.
        return False
    try:
        banderas = int(descriptor.get("/Flags") or 0)
    except (TypeError, ValueError):
        return False
    # Bit 3 (valor 4) de la tabla 123 de ISO 32000-1: fuente simbólica.
    return bool(banderas & 4)


def _version_de_cabecera(ruta: Path) -> str:
    """Lee la versión declarada en los primeros bytes del archivo."""
    try:
        with open(ruta, "rb") as archivo:
            cabecera = archivo.read(1024)
    except OSError:
        return ""
    coincidencia = re.search(rb"%PDF-(\d\.\d)", cabecera)
    return coincidencia.group(1).decode("ascii") if coincidencia else ""


def _esta_linealizado(ruta: Path) -> bool:
    """Indica si el PDF está preparado para leerse por partes.

    Un PDF linealizado trae la primera página al principio del archivo.  No
    cambia nada de lo que se lee, pero explica por qué unos documentos
    aparecen al instante y otros hacen esperar, y es lo que produce una copia
    reparada.
    """
    try:
        with open(ruta, "rb") as archivo:
            return b"/Linearized" in archivo.read(2048)
    except OSError:
        return False


def _redactar_hallazgos(informe: Diagnostico) -> None:
    """Convierte el inventario en observaciones con remedio."""
    anadir = informe.hallazgos.anadir
    if informe.cifrado is Cifrado.PROPIETARIO:
        anadir(informativo(
            "CIFRADO_PROPIETARIO",
            _("El PDF está cifrado, pero solo contra la impresión o la copia: "
              "se puede leer sin contraseña.")))
    elif informe.cifrado is Cifrado.USUARIO:
        anadir(grave(
            "CIFRADO_USUARIO",
            _("El PDF está cifrado y hace falta una contraseña para leerlo."),
            remedio=_("Escribe la contraseña cuando el programa te la pida.")))
    if informe.danado:
        anadir(Hallazgo(
            "ARCHIVO_DANADO",
            _("El archivo tiene la estructura dañada."),
            Severidad.ERROR,
            remedio=_("Se intentará abrir desde una copia reparada.")))
    if informe.javascript:
        anadir(informativo(
            "JAVASCRIPT",
            _("El documento contiene JavaScript, que este programa detecta pero "
              "nunca ejecuta.")))
    if informe.adjuntos:
        anadir(informativo(
            "ADJUNTOS",
            contar(informe.adjuntos,
                   _("El documento lleva %d archivo adjunto, que no se abre."),
                   _("El documento lleva %d archivos adjuntos, que no se abren.")),
            cantidad=informe.adjuntos))
    if informe.firmas:
        anadir(informativo(
            "FIRMAS",
            _("El documento está firmado digitalmente. Si hubiera que repararlo, "
              "la copia dejaría de estar firmada."),
            cantidad=informe.firmas))
    if informe.fuentes_sin_unicode:
        anadir(aviso(
            "FUENTES_SIN_UNICODE",
            contar(len(informe.fuentes_sin_unicode),
                   _("%d fuente no dice a qué letra corresponde cada símbolo, así que "
                     "su texto puede salir ilegible."),
                   _("%d fuentes no dicen a qué letra corresponde cada símbolo, así que "
                     "su texto puede salir ilegible.")),
            cantidad=len(informe.fuentes_sin_unicode),
            remedio=_("Si el texto sale ilegible, fuerza el reconocimiento óptico "
                      "en las opciones de PDF."),
            norma="ISO 14289-1, 7.21.6",
            detalle=", ".join(sorted(informe.fuentes_sin_unicode))))
    if informe.fuentes_sin_incrustar:
        anadir(informativo(
            "FUENTES_SIN_INCRUSTAR",
            contar(len(informe.fuentes_sin_incrustar),
                   _("%d fuente no va incrustada en el archivo."),
                   _("%d fuentes no van incrustadas en el archivo.")),
            cantidad=len(informe.fuentes_sin_incrustar),
            norma="ISO 14289-1, 7.21.3",
            detalle=", ".join(sorted(informe.fuentes_sin_incrustar))))
    if informe.formularios and not informe.arbol_logico:
        anadir(aviso(
            "FORMULARIO_SIN_ESTRUCTURA",
            _("El documento tiene %d campos de formulario y ninguna estructura "
              "que diga qué es cada uno.") % informe.formularios,
            cantidad=informe.formularios,
            norma="ISO 14289-1, 7.18.1"))
