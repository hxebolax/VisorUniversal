# -*- coding: utf-8 -*-
"""Modelo local: cualquier servidor que hable la API de OpenAI.

Es lo que exponen ``llama.cpp`` (``llama-server``), Ollama y LM Studio: un
``POST /v1/chat/completions`` con mensajes.  Al ser un estándar de hecho, con
un solo cliente valen los tres, y para describir imágenes basta con que el
modelo cargado sea multimodal (LLaVA, Qwen-VL, MiniCPM-V, Gemma multimodal...).

Frente a Gemini tiene dos ventajas que aquí pesan: **no sale nada del equipo**
—el libro y sus ilustraciones no viajan a ningún servidor— y **no hay cuota**.
A cambio hay que tener el servidor en marcha.

Como en el resto del paquete, solo se usa la biblioteca estándar.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request

from ..idioma import _
from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

#: Dirección donde escucha ``llama-server`` con sus valores de fábrica.
URL_POR_OMISION = "http://localhost:8080/v1"

#: Nombre de modelo que se manda cuando el usuario no indica ninguno.  Los
#: servidores locales suelen tener uno solo cargado y no miran este campo, pero
#: la API lo exige.
MODELO_POR_OMISION = "local"


def _normalizar(url: str) -> str:
    """Convierte lo que escriba el usuario en la dirección completa.

    Se admite tanto ``http://localhost:8080`` como ``.../v1`` o la ruta entera,
    porque cada servidor la documenta a su manera y no merece la pena que un
    detalle así impida usar la función.
    """
    limpia = (url or URL_POR_OMISION).strip().rstrip("/")
    if limpia.endswith("/chat/completions"):
        return limpia
    if not limpia.endswith("/v1"):
        limpia += "/v1"
    return limpia + "/chat/completions"


def _mensaje_de_error(error: Exception) -> str:
    """Traduce el fallo a algo que se pueda enseñar."""
    if isinstance(error, urllib.error.HTTPError):
        try:
            detalle = json.loads(error.read().decode("utf-8", errors="replace"))
            mensaje = detalle.get("error") or {}
            if isinstance(mensaje, dict):
                mensaje = mensaje.get("message", "")
            if mensaje:
                return _("%s (código %d)") % (mensaje, error.code)
        except Exception:
            pass
        return _("el servidor ha respondido con el código %d") % error.code
    if isinstance(error, urllib.error.URLError):
        return (_("no se ha podido conectar con el servidor local (%s). "
                "Comprueba que está en marcha y que la dirección es correcta.")
                % error.reason)
    return str(error)


class Local:
    """Cliente de un servidor local compatible con OpenAI.

    :param url: Dirección del servidor.
    :param modelo: Nombre del modelo que se pide.
    :param tiempo_espera: Segundos de espera.  Conviene que sea generoso: en
                          una tarjeta modesta, describir una imagen puede
                          tardar bastante más que en la nube.
    """

    def __init__(self, url: str = URL_POR_OMISION, modelo: str = MODELO_POR_OMISION,
                 tiempo_espera: float = 180.0) -> None:
        self.url = _normalizar(url)
        self.modelo = (modelo or MODELO_POR_OMISION).strip()
        self.tiempo_espera = tiempo_espera

    def _pedir(self, mensajes: list, tiempo: float | None = None) -> str:
        """Manda los mensajes al servidor y devuelve el texto de la respuesta."""
        cuerpo = json.dumps({"model": self.modelo, "messages": mensajes}).encode("utf-8")
        peticion = urllib.request.Request(
            self.url, data=cuerpo,
            headers={"Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(peticion, timeout=tiempo or self.tiempo_espera) as r:
                respuesta = json.loads(r.read().decode("utf-8", errors="replace"))
        except Exception as error:
            raise ConnectionError(_mensaje_de_error(error)) from error
        opciones = respuesta.get("choices") or []
        if not opciones:
            raise ValueError(_("El servidor local no ha devuelto ninguna respuesta."))
        mensaje = opciones[0].get("message") or {}
        return str(mensaje.get("content") or "").strip()

    def listar_modelos(self) -> list[str]:
        """Pregunta al servidor qué modelos tiene cargados.

        No todos los servidores implementan ``/models``; si no contesta, se
        devuelve una lista vacía y el usuario escribe el nombre a mano.
        """
        url = self.url.replace("/chat/completions", "/models")
        try:
            with urllib.request.urlopen(url, timeout=10.0) as r:
                respuesta = json.loads(r.read().decode("utf-8", errors="replace"))
        except Exception as error:
            log.info("El servidor local no ha dado la lista de modelos: %s", error)
            return []
        # ``or []`` y no un valor por omisión: cuando no hay ningún modelo
        # instalado, Ollama no omite la clave, la manda a ``null``, y el
        # valor por omisión de ``get`` solo actúa si la clave falta.
        modelos = respuesta.get("data") or []
        return sorted(str(m.get("id", "")) for m in modelos if m.get("id"))

    def describir(self, datos: bytes, tipo_mime: str, prompt: str) -> str:
        """Manda una imagen y una instrucción al modelo local."""
        codificada = base64.b64encode(datos).decode("ascii")
        mensajes = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url",
                 "image_url": {"url": "data:%s;base64,%s" % (tipo_mime, codificada)}},
            ],
        }]
        texto = self._pedir(mensajes)
        if not texto:
            raise ValueError(
                _("El modelo local no ha devuelto ninguna descripción. Comprueba que el modelo "
                "cargado admite imágenes: los modelos de solo texto aceptan la petición pero "
                "no ven la ilustración."))
        return texto

    def preguntar(self, pregunta: str) -> str:
        """Manda una pregunta de solo texto al modelo local.

        Aquí sirve cualquier modelo, también los que no admiten imágenes: es
        la única función del programa que no necesita que el modelo vea.
        """
        texto = self._pedir([{"role": "user", "content": pregunta}])
        if not texto:
            raise ValueError(_("El modelo local no ha devuelto ninguna respuesta."))
        return texto

    def conversar(self, turnos: list) -> str:
        """Sigue una conversación y devuelve la respuesta.

        :param turnos: Lista de ``(quién, qué)``, donde «quién» es ``"usuario"``
                       o ``"asistente"``, en orden y acabando en el usuario.

        Mandar la conversación entera en cada vuelta es lo que hace que el
        modelo recuerde: estos servicios no guardan nada entre peticiones,
        así que «lo que hablamos antes» es literalmente lo que se les vuelve
        a contar.
        """
        mensajes = [{"role": "assistant" if quien == "asistente" else "user",
                     "content": texto} for quien, texto in turnos]
        texto = self._pedir(mensajes)
        if not texto:
            raise ValueError(_("El modelo local no ha devuelto ninguna respuesta."))
        return texto

    def probar(self) -> str:
        """Comprueba que el servidor responde.

        :return: Lo que haya contestado, para enseñárselo al usuario.
        """
        texto = self._pedir(
            [{"role": "user", "content": _("Responde solo con la palabra: correcto.")}],
            tiempo=20.0)
        return texto or _("el servidor responde, pero sin texto")
