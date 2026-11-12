# -*- coding: utf-8 -*-
"""Correo guardado y páginas web archivadas: EML, MHT y MHTML.

Es de lo que más llega y de lo que peor se leía.  Un correo guardado desde
Outlook o Thunderbird es un ``.eml``; una página web guardada «en un solo
archivo» desde Edge, Chrome o Internet Explorer es un ``.mht``.  Los dos son
**lo mismo por dentro**: un mensaje MIME, con sus cabeceras y con el contenido
repartido en partes.

Hasta ahora había que convertirlos aparte —abrirlos en otro programa, copiar el
texto, pegarlo— y por el camino se perdían los encabezados, los enlaces y las
tablas.  Aquí se leen tal cual, con toda su estructura, porque una vez sacada la
parte de HTML el trabajo lo hace el conversor de siempre.

Qué se lee de un correo
-----------------------

Primero **quién escribe, a quién, cuándo y de qué**, que es lo que uno quiere
oír antes de nada y lo que en un volcado de texto plano queda enterrado entre
las cuarenta cabeceras técnicas del mensaje.  Después el cuerpo, y al final la
lista de lo que venía adjunto, con su nombre y su tamaño: saber que había un
archivo adjunto importa aunque no se pueda abrir desde aquí.

Los mensajes con respuestas encadenadas —los ``.eml`` que llevan otro ``.eml``
dentro— se leen enteros, cada mensaje con su cabecera y su encabezado propio,
de modo que se puedan recorrer con ``H`` como capítulos de un libro.

Las imágenes
------------

En un archivo así las imágenes van dentro, en sus propias partes, y el HTML las
llama por su identificador (``cid:algo``) o por su dirección original.  Se
recogen las dos formas, de manera que las ilustraciones de un correo o de una
página guardada se puedan ver con ``Control+I`` y describir con la inteligencia
artificial igual que las de un libro.
"""

from __future__ import annotations

import email
import email.policy
import re
from email.message import EmailMessage
from pathlib import Path

from nucleo.documento import Metadatos
from nucleo.idioma import _
from nucleo.registro import obtener_registro

from .base import Analizador, ErrorFormato, OpcionesAnalisis, registrar
from .ensamblador import envolver, escapar, montar

log = obtener_registro(__name__)

#: Cabeceras que se enseñan y en qué orden.  Son las que contestan a «de quién
#: es esto y de qué va»; las demás —los identificadores, las rutas por las que
#: pasó, las firmas— son ruido para quien lee.
CABECERAS = (
    ("subject", _("Asunto")),
    ("from", _("De")),
    ("to", _("Para")),
    ("cc", _("Copia")),
    ("date", _("Fecha")),
)

#: Tipos de parte que se toman por cuerpo del mensaje, en orden de preferencia.
#: El HTML va primero porque conserva la estructura; el texto plano es el
#: respaldo de los mensajes que no traen otra cosa.
CUERPOS = ("text/html", "text/plain")

#: Cuántos mensajes encadenados se leen como mucho.  Un hilo de correo
#: reenviado treinta veces existe, y montarlo entero no aporta nada.
MENSAJES_MAXIMOS = 50


class AnalizadorCorreo(Analizador):
    """Correo guardado y páginas web archivadas en un solo archivo."""

    extensiones = (".eml", ".mht", ".mhtml")
    descripcion = _("Correo y páginas guardadas")

    def analizar(self, ruta, opciones: OpcionesAnalisis):
        """Convierte el archivo MIME en un documento con su estructura."""
        destino = Path(ruta)
        mensaje = _leer(destino)
        secciones = []
        for numero, parte in enumerate(_mensajes(mensaje), start=1):
            titulo = _asunto(parte) or _("Mensaje %d") % numero
            secciones.append((titulo, envolver(
                _cuerpo_completo(parte, numero > 1, opciones.solo_articulo))))
        if not secciones:
            raise ErrorFormato(_("El archivo no contiene ningún mensaje que se pueda leer."))

        metadatos = _metadatos(mensaje, destino)
        documento = montar(secciones, metadatos, destino, opciones)
        log.info("Correo analizado: %s | %d mensajes", destino.name, len(secciones))
        return documento

    def extraer_recurso(self, ruta, interna: str):
        """Saca del archivo la imagen que pida el documento.

        Se busca por las dos formas en que el HTML puede nombrarla: su
        identificador de contenido y su dirección original.
        """
        buscada = str(interna or "")
        if not buscada:
            return None
        try:
            mensaje = _leer(Path(ruta))
        except ErrorFormato:
            return None
        for parte in mensaje.walk():
            if parte.get_content_maintype() == "multipart":
                continue
            if buscada in _nombres_de(parte):
                try:
                    return parte.get_payload(decode=True)
                except Exception as error:            # pragma: no cover
                    log.debug("No se ha podido extraer %s: %s", buscada, error)
                    return None
        return None


def _leer(destino: Path) -> EmailMessage:
    """Lee el archivo como mensaje MIME."""
    try:
        datos = destino.read_bytes()
    except OSError as error:
        raise ErrorFormato(_("No se ha podido leer el archivo: %s") % error) from error
    try:
        return email.message_from_bytes(datos, policy=email.policy.default)
    except Exception as error:
        raise ErrorFormato(
            _("El archivo no es un correo ni una página guardada: %s") % error) from error


def _mensajes(mensaje: EmailMessage) -> list[EmailMessage]:
    """Devuelve el mensaje y los que lleve dentro, en orden de lectura."""
    salida = [mensaje]
    for parte in mensaje.walk():
        if parte is mensaje:
            continue
        if parte.get_content_type() == "message/rfc822":
            dentro = parte.get_payload()
            if isinstance(dentro, list) and dentro:
                salida.append(dentro[0])
            elif isinstance(dentro, EmailMessage):
                salida.append(dentro)
        if len(salida) >= MENSAJES_MAXIMOS:
            break
    return salida


def _asunto(mensaje) -> str:
    """El asunto del mensaje, limpio de saltos de línea."""
    try:
        return " ".join(str(mensaje.get("subject", "") or "").split())
    except Exception:                                # pragma: no cover
        return ""


def _cabecera(mensaje, nombre: str) -> str:
    """Una cabecera legible, o cadena vacía."""
    try:
        valor = mensaje.get(nombre, "")
    except Exception:                                # pragma: no cover
        return ""
    return " ".join(str(valor or "").split())


def _cuerpo_completo(mensaje, con_titulo: bool, solo_articulo: bool = False) -> str:
    """Arma el HTML de un mensaje: sus cabeceras, su cuerpo y sus adjuntos."""
    partes = []
    asunto = _asunto(mensaje)
    if con_titulo and asunto:
        partes.append("<h1>%s</h1>" % escapar(asunto))
    partes.append(_tabla_de_cabeceras(mensaje))
    partes.append(_cuerpo(mensaje, solo_articulo))
    adjuntos = _lista_de_adjuntos(mensaje)
    if adjuntos:
        partes.append(adjuntos)
    return "\n".join(parte for parte in partes if parte)


def _tabla_de_cabeceras(mensaje) -> str:
    """Escribe de quién es el mensaje, para quién y cuándo.

    Va como lista de definiciones y no como tabla: es un puñado de pares
    etiqueta-valor, y una tabla de dos columnas obligaría a recorrerla con las
    órdenes de tabla para oír algo que se lee de corrido en tres segundos.
    """
    filas = []
    for clave, etiqueta in CABECERAS:
        valor = _cabecera(mensaje, clave)
        if valor:
            filas.append("<p><strong>%s:</strong> %s</p>"
                         % (escapar(etiqueta), escapar(valor)))
    return "\n".join(filas)


def _cuerpo(mensaje, solo_articulo: bool = False) -> str:
    """Devuelve el cuerpo del mensaje como HTML.

    Se prefiere la parte de HTML porque conserva encabezados, listas, tablas y
    enlaces.  Solo cuando el mensaje no la trae se recurre al texto plano, y
    entonces se envuelve párrafo a párrafo para que al menos no salga todo
    pegado en una línea.
    """
    elegido = None
    for tipo in CUERPOS:
        elegido = _parte_de_tipo(mensaje, tipo)
        if elegido is not None:
            break
    if elegido is None:
        return ""
    texto = _texto_de(elegido)
    if elegido.get_content_type() == "text/html":
        if solo_articulo:
            # Un «.mht» es una página web guardada, y le sobra lo mismo que a
            # cualquier otra: los menús y el aviso de las galletas.
            from . import articulo

            recortada = articulo.extraer(texto.encode("utf-8"))
            if recortada is not None:
                texto = recortada.decode("utf-8", "replace")
        return _con_imagenes(_solo_el_cuerpo(texto))
    return "\n".join("<p>%s</p>" % escapar(parrafo.strip())
                     for parrafo in re.split(r"\n\s*\n", texto) if parrafo.strip())


def _parte_de_tipo(mensaje, tipo: str):
    """La primera parte de ese tipo que no sea un archivo adjunto."""
    for parte in mensaje.walk():
        if parte.get_content_type() != tipo:
            continue
        disposicion = str(parte.get("content-disposition", "") or "").lower()
        if "attachment" in disposicion:
            continue
        return parte
    return None


def _texto_de(parte) -> str:
    """El contenido de una parte, descodificado como se pueda."""
    try:
        datos = parte.get_payload(decode=True)
    except Exception:                                # pragma: no cover
        datos = None
    if datos is None:
        contenido = parte.get_payload()
        return contenido if isinstance(contenido, str) else ""
    juego = parte.get_content_charset() or "utf-8"
    for prueba in (juego, "utf-8", "cp1252", "latin-1"):
        try:
            return datos.decode(prueba)
        except (UnicodeDecodeError, LookupError):
            continue
    return datos.decode("utf-8", "replace")


#: La declaración de tipo de documento y las etiquetas que envuelven una página
#: entera. Un correo en HTML casi siempre trae una página completa, y el cuerpo
#: del mensaje se mete después **dentro** de otra: sin quitar esto, lo que se
#: ve al leerlo empieza por un «!DOCTYPE html>» suelto, que no lo escribió nadie.
_DOCTIPO = re.compile(r"(?is)<!doctype[^>]*>")
_CUERPO = re.compile(r"(?is)<body[^>]*>(.*)</body>")
_ENVOLTORIO = re.compile(r"(?is)</?(?:html|head|body)[^>]*>")
_CABECERA = re.compile(r"(?is)<head[^>]*>.*?</head>")


def _solo_el_cuerpo(html: str) -> str:
    """Se queda con lo que hay dentro del ``<body>`` de una página completa.

    Un correo en HTML trae una página entera —con su declaración de tipo, su
    ``<html>`` y su ``<head>``— y aquí se está montando otra alrededor. Anidar
    dos páginas no da un documento válido, y lo que se ve al leerlo es la
    declaración de tipo convertida en un renglón de texto.

    Si no hay ``<body>`` se quitan las etiquetas de envoltorio y ya está: es un
    trozo de HTML suelto, que también es corriente en el correo.
    """
    limpio = _DOCTIPO.sub("", html)
    encaje = _CUERPO.search(limpio)
    if encaje is not None:
        return encaje.group(1)
    limpio = _CABECERA.sub("", limpio)
    return _ENVOLTORIO.sub("", limpio)


#: Una imagen llamada por su identificador de contenido dentro del HTML.
_CID = re.compile(r'(?i)(src\s*=\s*["\']?)cid:([^"\'>\s]+)')


def _con_imagenes(html: str) -> str:
    """Deja las direcciones de las imágenes como las entiende el programa.

    Un ``cid:algo`` se convierte en ``algo`` a secas, que es la clave con la que
    después se busca la parte dentro del archivo.  Las direcciones normales se
    dejan como están: en un ``.mht`` son la ``Content-Location`` de la parte, y
    también sirven para encontrarla.
    """
    return _CID.sub(lambda encaje: encaje.group(1) + encaje.group(2), html)


def _nombres_de(parte) -> set:
    """Todas las formas en que el HTML puede llamar a esta parte."""
    nombres = set()
    identificador = str(parte.get("content-id", "") or "").strip().strip("<>")
    if identificador:
        nombres.add(identificador)
    sitio = str(parte.get("content-location", "") or "").strip()
    if sitio:
        nombres.add(sitio)
        nombres.add(sitio.rsplit("/", 1)[-1])
    try:
        archivo = parte.get_filename()
    except Exception:                                # pragma: no cover
        archivo = None
    if archivo:
        nombres.add(str(archivo))
    return nombres


def _lista_de_adjuntos(mensaje) -> str:
    """Enumera lo que venía adjunto, con su nombre y su tamaño.

    No se pueden abrir desde aquí, y por eso mismo hay que decirlos: enterarse
    de que el correo traía un archivo es la mitad de la información.
    """
    filas = []
    for parte in mensaje.walk():
        if parte.get_content_maintype() in ("multipart", "text"):
            continue
        disposicion = str(parte.get("content-disposition", "") or "").lower()
        nombre = parte.get_filename()
        if not nombre and "attachment" not in disposicion:
            continue
        try:
            datos = parte.get_payload(decode=True) or b""
        except Exception:                            # pragma: no cover
            datos = b""
        filas.append("<li>%s (%s, %d KB)</li>"
                     % (escapar(str(nombre or _("sin nombre"))),
                        escapar(parte.get_content_type()), len(datos) // 1024))
    if not filas:
        return ""
    return "<h2>%s</h2>\n<ul>\n%s\n</ul>" % (escapar(_("Archivos adjuntos")),
                                             "\n".join(filas))


def _metadatos(mensaje, destino: Path) -> Metadatos:
    """Título, autor y fecha del documento, sacados de las cabeceras."""
    asunto = _asunto(mensaje)
    # Una página guardada en MHT trae su título en «Subject»; un correo, su
    # asunto.  En los dos casos es lo que hay que enseñar como título.
    return Metadatos(
        titulo=asunto or destino.stem,
        autor=_cabecera(mensaje, "from"),
        fecha=_cabecera(mensaje, "date"),
        identificador=_cabecera(mensaje, "message-id"),
    )


registrar(AnalizadorCorreo())
