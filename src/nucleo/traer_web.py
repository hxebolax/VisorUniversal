# -*- coding: utf-8 -*-
"""Pegar una dirección y que el programa traiga la página, limpia y lista.

El programa ya sabe quitarle a una página guardada los menús, el aviso de las
galletas y el pie con cincuenta enlaces (:mod:`formatos.articulo`). Lo que
faltaba era el paso de antes: **traerla**. Sin esto hay que abrir el navegador,
buscar «guardar como», elegir «página web completa», acordarse de dónde se ha
guardado y abrirlo aquí; y ese rodeo, con un lector de pantalla, son cinco
diálogos que no tienen nada que ver con leer un artículo.

**Lo que se trae y lo que no.** Solo ``http`` y ``https``, y solo lo que el
servidor devuelva como HTML o como texto. Un PDF enlazado se guarda tal cual y
se abre con el lector de PDF, que es lo que hace falta; cualquier otra cosa
—un vídeo, un instalador— se rechaza diciéndolo, porque descargar a ciegas lo
que haya al otro lado de un enlace no es leer una página.

**Lo que no hace, a propósito:** no ejecuta JavaScript. Una página que no
escribe nada sin ejecutar guiones se traerá vacía, y entonces se dice claramente
en vez de abrir un documento en blanco. Traer un navegador entero para eso serían
doscientos megabytes y un motor de red que actualizar cada mes.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .idioma import _
from .registro import obtener_registro

log = obtener_registro(__name__)

#: Con qué se presenta el programa. Se pone un navegador reconocible porque
#: muchos servidores devuelven una página de error a lo que no lo parezca, y
#: quien está leyendo no tiene forma de saber que el problema es ese.
CABECERAS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.5",
    "Accept-Language": "es,en;q=0.8",
}

#: Cuánto se espera al servidor, en segundos.
ESPERA = 30

#: Lo más grande que se admite traer. Una página de texto son unos cientos de
#: kilobytes; por encima de esto ya no es un artículo.
MAXIMO = 25 * 1024 * 1024

#: Tipos de contenido que valen, y con qué extensión se guardan.
ADMITIDOS = {
    "text/html": ".html",
    "application/xhtml+xml": ".html",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "application/pdf": ".pdf",
    "application/epub+zip": ".epub",
}

#: Caracteres que no pueden ir en un nombre de archivo de Windows.
_PROHIBIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class ErrorAlTraer(Exception):
    """No se ha podido traer la página. El mensaje se le enseña al usuario."""


def normalizar(direccion: str) -> str:
    """Deja una dirección lista para pedirla, o levanta un error claro.

    Se admite escribirla sin el ``https://`` delante, que es como la dicta
    todo el mundo y como se copia de la mitad de los sitios.
    """
    texto = (direccion or "").strip().strip("<>").strip()
    if not texto:
        raise ErrorAlTraer(_("Escribe una dirección."))
    if "://" not in texto:
        texto = "https://" + texto
    partes = urllib.parse.urlsplit(texto)
    if partes.scheme not in ("http", "https"):
        raise ErrorAlTraer(
            _("Solo se pueden traer direcciones que empiecen por http o https."))
    if not partes.netloc:
        raise ErrorAlTraer(_("Esa dirección no está completa: le falta el sitio."))
    return urllib.parse.urlunsplit(partes)


def nombre_para(direccion: str, extension: str) -> str:
    """Un nombre de archivo que se pueda leer, sacado de la dirección.

    Del final de la ruta si lo tiene —que suele ser el titular del artículo— y
    del sitio si no. Se limpia de lo que Windows no admite y se recorta, porque
    hay direcciones de trescientos caracteres.
    """
    partes = urllib.parse.urlsplit(direccion)
    cola = urllib.parse.unquote(partes.path.rstrip("/").rsplit("/", 1)[-1])
    cola = re.sub(r"\.(html?|php|aspx?|jsp)$", "", cola, flags=re.IGNORECASE)
    if not cola or len(cola) < 3:
        cola = partes.netloc
    cola = _PROHIBIDOS.sub(" ", cola.replace("-", " ").replace("_", " "))
    cola = " ".join(cola.split())[:80].strip(". ")
    return (cola or _("pagina")) + extension


def traer(direccion: str, carpeta, progreso=None) -> Path:
    """Trae la página y la deja escrita en un archivo. Devuelve la ruta.

    :param carpeta: Dónde guardarla.
    :param progreso: Función ``(bytes_traídos, total_o_cero)``.
    :raises ErrorAlTraer: Con un mensaje ya redactado para enseñárselo al
                          usuario. **Nunca** se deja escapar el error de red en
                          crudo: «HTTP Error 403: Forbidden» no le dice a nadie
                          qué hacer.
    """
    completa = normalizar(direccion)
    peticion = urllib.request.Request(completa, headers=CABECERAS)
    try:
        respuesta = urllib.request.urlopen(peticion, timeout=ESPERA)
    except urllib.error.HTTPError as error:
        raise ErrorAlTraer(_motivo_http(error.code, completa)) from error
    except urllib.error.URLError as error:
        raise ErrorAlTraer(
            _("No se ha podido conectar con «%(sitio)s». Comprueba la conexión y "
              "que la dirección esté bien escrita.\n\nDetalle: %(detalle)s")
            % {"sitio": urllib.parse.urlsplit(completa).netloc,
               "detalle": getattr(error, "reason", error)}) from error
    except (OSError, ValueError) as error:
        raise ErrorAlTraer(_("No se ha podido traer la página: %s") % error) from error

    with respuesta:
        tipo = (respuesta.headers.get_content_type() or "").lower()
        extension = ADMITIDOS.get(tipo)
        if extension is None:
            raise ErrorAlTraer(
                _("Lo que hay en esa dirección no es una página ni un documento que "
                  "el programa pueda leer: es «%s». Si es un archivo que quieres "
                  "guardar, descárgalo con el navegador y ábrelo desde aquí.") % tipo)
        try:
            declarado = int(respuesta.headers.get("Content-Length") or 0)
        except ValueError:
            declarado = 0
        if declarado > MAXIMO:
            raise ErrorAlTraer(_("Esa página ocupa demasiado para traerla."))
        trozos = []
        traidos = 0
        while True:
            trozo = respuesta.read(64 * 1024)
            if not trozo:
                break
            trozos.append(trozo)
            traidos += len(trozo)
            if traidos > MAXIMO:
                raise ErrorAlTraer(_("Esa página ocupa demasiado para traerla."))
            if progreso is not None:
                progreso(traidos, declarado)
        datos = b"".join(trozos)
        # La dirección **de verdad** puede no ser la pedida: casi todos los
        # sitios redirigen. Es la que hay que usar para el nombre y, sobre
        # todo, la que hay que dejar escrita dentro de la página para que los
        # enlaces y las imágenes relativos sigan apuntando a alguna parte.
        final = respuesta.geturl() or completa

    if not datos.strip():
        raise ErrorAlTraer(
            _("Esa dirección ha devuelto una página vacía. Suele pasar con las "
              "páginas que se escriben solas con JavaScript: guárdala desde el "
              "navegador con «Guardar como» y ábrela desde aquí."))

    if extension == ".html":
        datos = _poner_base(datos, final)

    destino = Path(carpeta) / nombre_para(final, extension)
    destino = _sin_pisar(destino)
    destino.write_bytes(datos)
    log.info("Traída %s (%d bytes) en %s", final, len(datos), destino.name)
    return destino


def _sin_pisar(destino: Path) -> Path:
    """Si ya existe un archivo con ese nombre, se numera el nuevo."""
    if not destino.exists():
        return destino
    for numero in range(2, 1000):
        candidato = destino.with_name("%s (%d)%s" % (destino.stem, numero,
                                                     destino.suffix))
        if not candidato.exists():
            return candidato
    return destino


#: Dónde acaba la cabecera del HTML, para poder meter algo dentro.
_CABEZA = re.compile(rb"<head[^>]*>", re.IGNORECASE)


def _poner_base(datos: bytes, direccion: str) -> bytes:
    """Deja escrita la dirección de origen dentro de la propia página.

    Una página guardada tiene rutas relativas: ``imagenes/foto.jpg``,
    ``/seccion/otro-articulo``. Al abrirla desde el disco, esas rutas no llevan
    a ninguna parte. Con una etiqueta ``<base>`` apuntando al sitio de origen,
    los enlaces vuelven a funcionar y las imágenes se pueden localizar.

    Si la página ya trae su propia ``<base>``, no se toca: la suya sabe más.
    """
    if b"<base" in datos[:4000].lower():
        return datos
    etiqueta = ('<base href="%s"/>' % direccion.replace('"', "%22")).encode("utf-8")
    encaje = _CABEZA.search(datos)
    if encaje is None:
        return etiqueta + datos
    return datos[:encaje.end()] + etiqueta + datos[encaje.end():]


def _motivo_http(codigo: int, direccion: str) -> str:
    """Explica un error del servidor en términos de qué hacer.

    Los códigos se agrupan por lo que significan **para quien está intentando
    leer**, que no es lo mismo que lo que significan para un programador.
    """
    sitio = urllib.parse.urlsplit(direccion).netloc
    if codigo == 404:
        return _("En «%s» no hay nada: esa página ya no existe o la dirección "
                 "tiene una errata.") % direccion
    if codigo in (401, 403):
        return _("«%s» no deja entrar sin haber iniciado sesión. Ábrela en el "
                 "navegador, inicia sesión y guárdala con «Guardar como»; después "
                 "se abre desde aquí.") % sitio
    if codigo == 429:
        return _("«%s» está pidiendo que se espere: se le han hecho demasiadas "
                 "peticiones seguidas. Prueba dentro de un rato.") % sitio
    if 500 <= codigo < 600:
        return _("«%s» está fallando ahora mismo (error %d del servidor). No es "
                 "cosa tuya: prueba más tarde.") % (sitio, codigo)
    return _("«%(sitio)s» ha respondido con el error %(codigo)d y no ha dado la "
             "página.") % {"sitio": sitio, "codigo": codigo}
