# -*- coding: utf-8 -*-
"""Google Gemini por su API REST, sin instalar nada.

Google publica un SDK de Python, pero para lo que aquí hace falta —mandar una
imagen y un texto, y recoger la respuesta— la API REST es una petición HTTP con
un JSON, así que se resuelve con :mod:`urllib.request`.  Eso evita añadir una
dependencia al programa y al ejecutable compilado.

Dos detalles pensados para el uso real:

* **Varias claves.**  La capa gratuita de Gemini tiene cuota por clave.  Se
  admiten varias, una por línea, y cuando una se agota (error 429) se pasa
  sola a la siguiente.
* **Modelos que admiten imagen.**  La lista que devuelve la API incluye
  modelos que no sirven aquí (los de voz, los de incrustaciones, los que
  *generan* imágenes en vez de leerlas).  Se filtran, para que en el
  desplegable solo aparezca lo que de verdad puede describir una foto.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request

from ..idioma import _
from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

#: Raíz de la API pública de Gemini.
BASE = "https://generativelanguage.googleapis.com/v1beta"

#: Modelo que se propone cuando el usuario todavía no ha elegido ninguno.
MODELO_POR_OMISION = "gemini-2.5-flash"

#: Trozos de nombre que descartan un modelo para describir imágenes.  La API no
#: dice qué modalidades admite de entrada, así que el filtro va por el nombre,
#: que en Gemini es sistemático:
#:
#: * ``embedding``/``aqa``: no generan texto libre.
#: * ``-tts``, ``-live``, ``transcribe``: voz, no imagen.
#: * ``-image``: son los que **producen** imágenes (la familia «Nano Banana»);
#:   para describir hace falta lo contrario, uno que devuelva texto.
#: * ``imagen-``, ``veo-``: generadores de imagen y de vídeo.
EXCLUIDOS = ("embedding", "aqa", "-tts", "-live", "transcribe", "-image",
             "imagen-", "veo-", "learnlm")


def _peticion(url: str, cuerpo: dict | None, tiempo: float) -> dict:
    """Hace una petición HTTP y devuelve el JSON de la respuesta.

    :param cuerpo: Si es ``None`` se hace un GET; si no, un POST con ese JSON.
    :raises urllib.error.HTTPError: Si el servidor responde con un error.
    """
    datos = None
    cabeceras = {"Accept": "application/json"}
    if cuerpo is not None:
        datos = json.dumps(cuerpo).encode("utf-8")
        cabeceras["Content-Type"] = "application/json"
    peticion = urllib.request.Request(url, data=datos, headers=cabeceras)
    with urllib.request.urlopen(peticion, timeout=tiempo) as respuesta:
        return json.loads(respuesta.read().decode("utf-8", errors="replace"))


def _es_de_cuota(error: Exception) -> bool:
    """Indica si el error significa que esa clave ha agotado su cuota."""
    if isinstance(error, urllib.error.HTTPError) and error.code in (429, 403):
        return True
    texto = str(error).lower()
    return "quota" in texto or "rate limit" in texto or "resource_exhausted" in texto


def _mensaje_de_error(error: Exception) -> str:
    """Saca del error el texto que le sirve al usuario.

    Gemini contesta los errores con un JSON que explica bien qué pasa («API key
    not valid»); mostrar eso ahorra muchísimo tiempo frente a un «Error 400».
    """
    if isinstance(error, urllib.error.HTTPError):
        try:
            detalle = json.loads(error.read().decode("utf-8", errors="replace"))
            mensaje = (detalle.get("error") or {}).get("message") or ""
            if mensaje:
                return _("%s (código %d)") % (mensaje, error.code)
        except Exception:
            pass
        return _("el servidor ha respondido con el código %d") % error.code
    return str(error)


def admite_imagen(nombre: str) -> bool:
    """Indica si un modelo de Gemini puede recibir una imagen y describirla."""
    minusculas = nombre.lower()
    return not any(trozo in minusculas for trozo in EXCLUIDOS)


class Gemini:
    """Cliente mínimo de Gemini.

    :param claves: Claves API, en el orden en que se van a probar.
    :param modelo: Modelo que se usa para describir.
    :param tiempo_espera: Segundos que se espera a cada respuesta.
    """

    def __init__(self, claves, modelo: str = MODELO_POR_OMISION,
                 tiempo_espera: float = 90.0) -> None:
        self.claves = [str(clave).strip() for clave in claves if str(clave).strip()]
        self.modelo = modelo or MODELO_POR_OMISION
        self.tiempo_espera = tiempo_espera

    # -- consultas -----------------------------------------------------------

    def listar_modelos(self, solo_imagen: bool = True) -> list[str]:
        """Pide a Google la lista de modelos disponibles para la clave.

        :param solo_imagen: Si se descartan los que no pueden describir una
                            imagen.  Es lo normal: en este programa la IA solo
                            se usa para eso.
        :return: Nombres de modelo (``gemini-2.5-flash``), ordenados.
        """
        if not self.claves:
            raise ValueError(_("No hay ninguna clave API de Gemini configurada."))
        clave = self.claves[0]
        nombres: list[str] = []
        pagina = ""
        # La API pagina de 50 en 50; se recorren todas las páginas.  La
        # variable del bucle no se llama «_»: eso la haría local a toda la
        # función y dejaría sin usar la «_» de las traducciones, que se llama
        # más arriba.
        for _pagina_numero in range(20):
            url = "%s/models?key=%s&pageSize=200" % (BASE, urllib.parse.quote(clave))
            if pagina:
                url += "&pageToken=" + urllib.parse.quote(pagina)
            try:
                respuesta = _peticion(url, None, self.tiempo_espera)
            except Exception as error:
                raise ConnectionError(_mensaje_de_error(error)) from error
            for modelo in respuesta.get("models") or []:
                nombre = str(modelo.get("name", "")).replace("models/", "")
                metodos = modelo.get("supportedGenerationMethods") or []
                if not nombre or (metodos and "generateContent" not in metodos):
                    continue
                if solo_imagen and not admite_imagen(nombre):
                    continue
                nombres.append(nombre)
            pagina = respuesta.get("nextPageToken") or ""
            if not pagina:
                break
        log.info("Gemini: %d modelos disponibles para describir imágenes", len(nombres))
        return sorted(set(nombres))

    def describir(self, datos: bytes, tipo_mime: str, prompt: str) -> str:
        """Manda una imagen y una instrucción, y devuelve el texto de vuelta.

        Si una clave agota su cuota se prueba la siguiente sin avisar: para el
        usuario es una sola operación que tarda un poco más.
        """
        if not self.claves:
            raise ValueError(_("No hay ninguna clave API de Gemini configurada."))
        cuerpo = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {
                        "mime_type": tipo_mime,
                        "data": base64.b64encode(datos).decode("ascii"),
                    }},
                ],
            }],
        }
        ultimo = None
        for numero, clave in enumerate(self.claves, start=1):
            url = "%s/models/%s:generateContent?key=%s" % (
                BASE, urllib.parse.quote(self.modelo), urllib.parse.quote(clave))
            try:
                respuesta = _peticion(url, cuerpo, self.tiempo_espera)
            except Exception as error:
                ultimo = error
                if _es_de_cuota(error) and numero < len(self.claves):
                    log.info("La clave %d de Gemini no admite más peticiones; se prueba la siguiente",
                             numero)
                    continue
                raise ConnectionError(_mensaje_de_error(error)) from error
            texto = self._texto_de(respuesta)
            if texto:
                return texto
            raise ValueError(self._motivo_de_respuesta_vacia(respuesta))
        detalle = _mensaje_de_error(ultimo) if ultimo else "sin detalles"
        raise ConnectionError(
            _("Todas las claves de Gemini han agotado su cuota. Último aviso: %s") % detalle)

    def preguntar(self, pregunta: str) -> str:
        """Manda una pregunta de solo texto y devuelve la respuesta.

        Es lo mismo que :meth:`describir` sin imagen.  Se reparte igual entre
        las claves configuradas: si una agota su cuota, se prueba la siguiente.
        """
        if not self.claves:
            raise ValueError(_("No hay ninguna clave API de Gemini configurada."))
        cuerpo = {"contents": [{"parts": [{"text": pregunta}]}]}
        ultimo = None
        for numero, clave in enumerate(self.claves, start=1):
            url = "%s/models/%s:generateContent?key=%s" % (
                BASE, urllib.parse.quote(self.modelo), urllib.parse.quote(clave))
            try:
                respuesta = _peticion(url, cuerpo, self.tiempo_espera)
            except Exception as error:
                ultimo = error
                if _es_de_cuota(error) and numero < len(self.claves):
                    continue
                raise ConnectionError(_mensaje_de_error(error)) from error
            texto = self._texto_de(respuesta)
            if texto:
                return texto
            raise ValueError(self._motivo_de_respuesta_vacia(respuesta))
        detalle = _mensaje_de_error(ultimo) if ultimo else "sin detalles"
        raise ConnectionError(
            _("Todas las claves de Gemini han agotado su cuota. Último aviso: %s") % detalle)

    def probar(self) -> str:
        """Comprueba que la clave y el modelo funcionan.

        :return: Un mensaje corto para enseñárselo al usuario.
        """
        if not self.claves:
            raise ValueError(_("No hay ninguna clave API de Gemini configurada."))
        url = "%s/models/%s:generateContent?key=%s" % (
            BASE, urllib.parse.quote(self.modelo), urllib.parse.quote(self.claves[0]))
        cuerpo = {"contents": [{"parts": [{"text": _("Responde solo con la palabra: correcto.")}]}]}
        try:
            respuesta = _peticion(url, cuerpo, min(self.tiempo_espera, 30.0))
        except Exception as error:
            raise ConnectionError(_mensaje_de_error(error)) from error
        return self._texto_de(respuesta) or "sin respuesta"

    # -- lectura de la respuesta ---------------------------------------------

    @staticmethod
    def _texto_de(respuesta: dict) -> str:
        """Extrae el texto de la respuesta de Gemini."""
        trozos = []
        for candidato in respuesta.get("candidates") or []:
            # Gemini devuelve candidatos sin contenido cuando el filtro le corta
            # la respuesta, y ahí «content» llega a null, no ausente.
            for parte in (candidato.get("content") or {}).get("parts") or []:
                if "text" in parte:
                    trozos.append(str(parte["text"]))
        return "\n".join(trozos).strip()

    @staticmethod
    def _motivo_de_respuesta_vacia(respuesta: dict) -> str:
        """Explica por qué no ha venido texto.

        El caso habitual es que los filtros de seguridad de Google hayan
        bloqueado la imagen; decirlo con claridad evita pensar que el programa
        está roto.
        """
        candidatos = respuesta.get("candidates") or []
        if candidatos:
            motivo = candidatos[0].get("finishReason", "")
            if motivo == "SAFETY":
                return (_("Gemini ha bloqueado esta imagen por sus filtros de contenido "
                        "y no ha devuelto ninguna descripción."))
            if motivo == "MAX_TOKENS":
                return _("La respuesta se ha cortado por longitud antes de decir nada.")
            if motivo:
                return _("Gemini ha terminado sin dar descripción (motivo: %s).") % motivo
        bloqueo = respuesta.get("promptFeedback", {}).get("blockReason", "")
        if bloqueo:
            return _("Gemini ha rechazado la petición (motivo: %s).") % bloqueo
        return _("Gemini no ha devuelto ninguna descripción.")
