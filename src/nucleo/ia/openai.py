# -*- coding: utf-8 -*-
"""Cliente de OpenAI y de todo lo que habla su mismo idioma.

La API de OpenAI se ha convertido en el formato común: la usan OpenAI, pero
también Groq, Together, DeepSeek, Mistral, OpenRouter, xAI y prácticamente
cualquier servicio nuevo, además de los servidores locales.  Por eso este
cliente **no está atado a OpenAI**: se le puede dar cualquier dirección y
cualquier clave, y hablará con quien haya al otro lado.

Se hace por HTTP directamente, **sin la biblioteca oficial**: el paquete
``openai`` arrastra un cliente HTTP entero y una capa de validación de datos
para hacer lo que aquí son cuarenta líneas con :mod:`urllib`, y en un programa
que se distribuye compilado cada dependencia es peso e incertidumbre al
empaquetar.

La diferencia con :mod:`nucleo.ia.local` es la clave y poco más; se mantienen
separados porque lo que hay que contarle al usuario cuando algo falla no se
parece en nada: a un servidor local se le dice «comprueba que está en marcha» y
a un servicio de pago, «revisa la clave y la cuota».
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request

from ..idioma import _
from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

#: Dirección de OpenAI.  Se cambia para usar cualquier otro servicio
#: compatible: Groq, DeepSeek, OpenRouter, Together...
URL_POR_OMISION = "https://api.openai.com/v1"

#: Modelo que se usa si no se elige otro.
MODELO_POR_OMISION = "gpt-4o-mini"

#: Servicios que se ofrecen ya escritos, para no tener que buscar la dirección.
#: Son todos compatibles con la misma API; lo único que cambia es el sitio.
SERVICIOS = (
    ("OpenAI", "https://api.openai.com/v1"),
    ("Groq", "https://api.groq.com/openai/v1"),
    ("DeepSeek", "https://api.deepseek.com/v1"),
    ("Mistral", "https://api.mistral.ai/v1"),
    ("OpenRouter", "https://openrouter.ai/api/v1"),
    ("xAI (Grok)", "https://api.x.ai/v1"),
    ("Together", "https://api.together.xyz/v1"),
)

#: Trozos de nombre que delatan a un modelo que **no** ve imágenes.  Se filtra
#: por lo que se sabe que no vale en vez de por lo que sí: la lista de modelos
#: nuevos cambia cada mes y una lista blanca se queda vieja enseguida.
SIN_IMAGEN = ("whisper", "tts", "dall-e", "embedding", "moderation", "audio",
              "davinci", "babbage", "instruct", "rerank")


def normalizar(url: str) -> str:
    """Convierte lo que escriba el usuario en la dirección completa.

    Se admite tanto ``https://api.openai.com`` como ``.../v1`` o la ruta
    entera: cada servicio la documenta a su manera y no merece la pena que un
    detalle así impida usarlo.
    """
    limpia = (url or URL_POR_OMISION).strip().rstrip("/")
    if limpia.endswith("/chat/completions"):
        return limpia
    if not limpia.endswith("/v1"):
        limpia += "/v1"
    return limpia + "/chat/completions"


def _es_de_cuota(error: Exception) -> bool:
    """Indica si el fallo es de cuota o de saturación."""
    return isinstance(error, urllib.error.HTTPError) and error.code in (429, 503)


def _mensaje_de_error(error: Exception) -> str:
    """Traduce el fallo a algo que se pueda enseñar."""
    if isinstance(error, urllib.error.HTTPError):
        try:
            detalle = json.loads(error.read().decode("utf-8", errors="replace"))
            mensaje = detalle.get("error", detalle)
            if isinstance(mensaje, dict):
                mensaje = mensaje.get("message", "")
            if mensaje:
                return _("%s (código %d)") % (mensaje, error.code)
        except Exception:
            pass
        if error.code == 401:
            return _("la clave API no es válida")
        if error.code == 404:
            return _("ese modelo no existe en este servicio, o la dirección no es correcta")
        if error.code == 429:
            return _("se ha agotado la cuota de esta clave")
        return _("el servidor ha respondido con el código %d") % error.code
    if isinstance(error, urllib.error.URLError):
        return _("no se ha podido conectar (%s)") % error.reason
    return str(error)


def admite_imagen(nombre: str) -> bool:
    """Indica si ese modelo puede ver imágenes, por lo que dice su nombre."""
    corto = (nombre or "").lower()
    return bool(corto) and not any(marca in corto for marca in SIN_IMAGEN)


class OpenAI:
    """Cliente de OpenAI o de cualquier servicio con su misma API.

    :param claves: Claves API.  Se admiten varias: cuando una agota su cuota se
                   pasa a la siguiente.
    :param url: Dirección del servicio.
    :param modelo: Nombre del modelo.
    :param tiempo_espera: Segundos de espera.
    """

    def __init__(self, claves, url: str = URL_POR_OMISION,
                 modelo: str = MODELO_POR_OMISION, tiempo_espera: float = 90.0) -> None:
        if isinstance(claves, str):
            claves = [claves]
        self.claves = [str(clave).strip() for clave in (claves or []) if str(clave).strip()]
        self.url = normalizar(url)
        self.modelo = (modelo or MODELO_POR_OMISION).strip()
        self.tiempo_espera = tiempo_espera
        self.ultimo_gasto = (0, 0)

    # -- lo común ------------------------------------------------------------

    def _pedir(self, mensajes: list, tiempo: float | None = None) -> str:
        """Manda los mensajes y devuelve el texto, probando todas las claves."""
        if not self.claves:
            raise ValueError(_("No hay ninguna clave API configurada."))
        cuerpo = json.dumps({"model": self.modelo, "messages": mensajes}).encode("utf-8")
        ultimo = None
        for numero, clave in enumerate(self.claves, start=1):
            peticion = urllib.request.Request(
                self.url, data=cuerpo,
                headers={"Authorization": "Bearer %s" % clave,
                         "Content-Type": "application/json",
                         "Accept": "application/json"})
            try:
                with urllib.request.urlopen(
                        peticion, timeout=tiempo or self.tiempo_espera) as r:
                    respuesta = json.loads(r.read().decode("utf-8", errors="replace"))
            except Exception as error:
                ultimo = error
                if _es_de_cuota(error) and numero < len(self.claves):
                    log.info("La clave %d no admite más peticiones; se prueba la siguiente",
                             numero)
                    continue
                raise ConnectionError(_mensaje_de_error(error)) from error
            self._anotar_gasto(respuesta)
            opciones = respuesta.get("choices") or []
            if not opciones:
                raise ValueError(_("El servicio no ha devuelto ninguna respuesta."))
            mensaje = opciones[0].get("message") or {}
            texto = str(mensaje.get("content") or "").strip()
            if texto:
                return texto
            raise ValueError(_("El modelo no ha devuelto ninguna respuesta."))
        detalle = _mensaje_de_error(ultimo) if ultimo else "sin detalles"
        raise ConnectionError(
            _("Todas las claves han agotado su cuota. Último aviso: %s") % detalle)

    def _anotar_gasto(self, respuesta: dict) -> None:
        """Se queda con lo que ha costado la petición, si el servicio lo dice."""
        uso = respuesta.get("usage") or {}
        self.ultimo_gasto = (int(uso.get("prompt_tokens", 0) or 0),
                             int(uso.get("completion_tokens", 0) or 0))

    # -- operaciones ------------------------------------------------------------

    def describir(self, datos: bytes, tipo_mime: str, prompt: str) -> str:
        """Manda una imagen con su instrucción."""
        codificada = base64.b64encode(datos).decode("ascii")
        texto = self._pedir([{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url",
                 "image_url": {"url": "data:%s;base64,%s" % (tipo_mime, codificada)}},
            ],
        }])
        if not texto:
            raise ValueError(
                _("El modelo no ha devuelto ninguna descripción. Comprueba que el modelo "
                  "elegido admite imágenes: los de solo texto aceptan la petición pero no "
                  "ven la ilustración."))
        return texto

    def preguntar(self, pregunta: str) -> str:
        """Manda una pregunta de solo texto."""
        return self._pedir([{"role": "user", "content": pregunta}])

    def conversar(self, turnos: list) -> str:
        """Sigue una conversación y devuelve la respuesta.

        :param turnos: Lista de ``(quién, qué)``, donde «quién» es ``"usuario"``
                       o ``"asistente"``, en orden y acabando en el usuario.

        Mandar la conversación entera en cada vuelta es lo que hace que el
        modelo recuerde: estos servicios no guardan nada entre peticiones,
        así que «lo que hablamos antes» es literalmente lo que se les vuelve
        a contar.
        """
        return self._pedir([{"role": "assistant" if quien == "asistente" else "user",
                             "content": texto} for quien, texto in turnos])

    def listar_modelos(self, solo_imagen: bool = True) -> list[str]:
        """Pide la lista de modelos del servicio."""
        if not self.claves:
            raise ValueError(_("No hay ninguna clave API configurada."))
        direccion = self.url.replace("/chat/completions", "/models")
        peticion = urllib.request.Request(
            direccion, headers={"Authorization": "Bearer %s" % self.claves[0],
                                "Accept": "application/json"})
        try:
            with urllib.request.urlopen(peticion, timeout=min(self.tiempo_espera, 30.0)) as r:
                respuesta = json.loads(r.read().decode("utf-8", errors="replace"))
        except Exception as error:
            raise ConnectionError(_mensaje_de_error(error)) from error
        nombres = [str(ficha.get("id", "")) for ficha in respuesta.get("data") or []]
        nombres = [nombre for nombre in nombres if nombre]
        if solo_imagen:
            nombres = [nombre for nombre in nombres if admite_imagen(nombre)]
        return sorted(set(nombres))

    def probar(self) -> str:
        """Comprueba que la clave, la dirección y el modelo funcionan."""
        return self._pedir([{"role": "user",
                             "content": _("Responde solo con la palabra: correcto.")}],
                           tiempo=min(self.tiempo_espera, 30.0))
