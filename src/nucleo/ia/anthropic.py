# -*- coding: utf-8 -*-
"""Cliente de Claude, de Anthropic.

Se habla con la API de mensajes directamente por HTTP, **sin la biblioteca
oficial**.  Es a propósito: el paquete ``anthropic`` arrastra media docena de
dependencias —un cliente HTTP entero, validación de datos, tipos— para hacer lo
que aquí son treinta líneas con :mod:`urllib`.  En un programa que se distribuye
compilado, cada dependencia es peso en el instalador y una cosa más que puede
romperse al empaquetar.

Lo que hace falta saber de esa API:

* La dirección es ``https://api.anthropic.com/v1/messages``.
* La clave va en la cabecera ``x-api-key``, no como ``Authorization``.
* Hay que declarar la versión de la API en ``anthropic-version``; sin ella la
  petición se rechaza.
* Las imágenes van dentro del mensaje, como un bloque ``image`` con los datos
  en base64 y su tipo declarado.
* Hay que mandar ``max_tokens`` sí o sí, al contrario que en otras API.
* La respuesta trae el texto en ``content``, que es una lista de bloques.
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

#: Dirección de la API.
BASE = "https://api.anthropic.com/v1"

#: Versión de la API que se declara.  Anthropic la exige y la usa para no
#: romper a quien ya estaba: cambiarla es cosa de revisar la documentación.
VERSION_API = "2023-06-01"

#: Modelo que se usa si no se elige otro.  El «más pequeño que sirve»: describir
#: una lámina no necesita el modelo más caro, y este responde deprisa.
MODELO_POR_OMISION = "claude-haiku-4-5-20251001"

#: Modelos que se ofrecen cuando el servidor no da la lista.  Se consulta la
#: API igualmente; esto es el respaldo.
MODELOS_CONOCIDOS = (
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-5-20250929",
    "claude-opus-4-1-20250805",
)

#: Tope de palabras de la respuesta.  Generoso: una descripción larga de una
#: lámina o un resumen de capítulo caben de sobra, y no se paga por el tope
#: sino por lo que se use.
MAXIMO_RESPUESTA = 4096


def _peticion(camino: str, clave: str, cuerpo: dict | None, tiempo: float) -> dict:
    """Hace una petición a la API y devuelve la respuesta ya interpretada."""
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    peticion = urllib.request.Request(
        "%s/%s" % (BASE, camino.lstrip("/")),
        data=datos,
        headers={
            "x-api-key": clave,
            "anthropic-version": VERSION_API,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST" if datos is not None else "GET")
    with urllib.request.urlopen(peticion, timeout=tiempo) as respuesta:
        return json.loads(respuesta.read().decode("utf-8", errors="replace"))


def _es_de_cuota(error: Exception) -> bool:
    """Indica si el fallo es «has gastado la cuota» y no otra cosa.

    El 429 es el límite de peticiones por minuto y el 529 es la sobrecarga del
    servicio; en los dos casos, probar con otra clave tiene sentido.
    """
    return isinstance(error, urllib.error.HTTPError) and error.code in (429, 529)


def _mensaje_de_error(error: Exception) -> str:
    """Traduce el fallo a algo que se pueda enseñar."""
    if isinstance(error, urllib.error.HTTPError):
        try:
            detalle = json.loads(error.read().decode("utf-8", errors="replace"))
            texto = (detalle.get("error") or {}).get("message", "")
            if texto:
                return _("%s (código %d)") % (texto, error.code)
        except Exception:
            pass
        if error.code == 401:
            return _("la clave API no es válida")
        if error.code == 429:
            return _("se ha agotado la cuota de esta clave")
        return _("el servidor ha respondido con el código %d") % error.code
    if isinstance(error, urllib.error.URLError):
        return _("no se ha podido conectar (%s)") % error.reason
    return str(error)


def admite_imagen(nombre: str) -> bool:
    """Indica si ese modelo puede ver imágenes.

    Todos los Claude del 3 en adelante las admiten; los anteriores no existen
    ya en la API, pero la comprobación es barata y evita una sorpresa.
    """
    corto = (nombre or "").lower()
    return "claude-" in corto and not corto.startswith("claude-instant")


class Anthropic:
    """Cliente de Claude.

    :param claves: Claves API.  Se admiten varias, como en Gemini: cuando una
                   agota su cuota se pasa a la siguiente sin avisar, que para
                   quien está describiendo un libro entero es una sola
                   operación que tarda un poco más.
    :param modelo: Nombre del modelo.
    :param tiempo_espera: Segundos de espera.
    """

    def __init__(self, claves, modelo: str = MODELO_POR_OMISION,
                 tiempo_espera: float = 90.0) -> None:
        if isinstance(claves, str):
            claves = [claves]
        self.claves = [str(clave).strip() for clave in (claves or []) if str(clave).strip()]
        self.modelo = (modelo or MODELO_POR_OMISION).strip()
        self.tiempo_espera = tiempo_espera
        #: Lo que ha costado la última petición, en unidades de texto.  Lo lee
        #: el contador de consumo.
        self.ultimo_gasto = (0, 0)

    # -- lo común a todas las peticiones -------------------------------------

    def _enviar(self, contenido: list) -> str:
        """Manda un mensaje y devuelve el texto, probando todas las claves."""
        if not self.claves:
            raise ValueError(_("No hay ninguna clave API de Anthropic configurada."))
        cuerpo = {
            "model": self.modelo,
            "max_tokens": MAXIMO_RESPUESTA,
            "messages": [{"role": "user", "content": contenido}],
        }
        ultimo = None
        for numero, clave in enumerate(self.claves, start=1):
            try:
                respuesta = _peticion("messages", clave, cuerpo, self.tiempo_espera)
            except Exception as error:
                ultimo = error
                if _es_de_cuota(error) and numero < len(self.claves):
                    log.info("La clave %d de Anthropic no admite más peticiones; "
                             "se prueba la siguiente", numero)
                    continue
                raise ConnectionError(_mensaje_de_error(error)) from error
            self._anotar_gasto(respuesta)
            texto = self._texto_de(respuesta)
            if texto:
                return texto
            raise ValueError(self._motivo_de_respuesta_vacia(respuesta))
        detalle = _mensaje_de_error(ultimo) if ultimo else "sin detalles"
        raise ConnectionError(
            _("Todas las claves de Anthropic han agotado su cuota. Último aviso: %s") % detalle)

    def _anotar_gasto(self, respuesta: dict) -> None:
        """Se queda con lo que ha costado la petición, si el servidor lo dice."""
        uso = respuesta.get("usage") or {}
        self.ultimo_gasto = (int(uso.get("input_tokens", 0) or 0),
                             int(uso.get("output_tokens", 0) or 0))

    @staticmethod
    def _texto_de(respuesta: dict) -> str:
        """Junta los bloques de texto de la respuesta."""
        partes = []
        for bloque in respuesta.get("content") or []:
            if isinstance(bloque, dict) and bloque.get("type") == "text":
                partes.append(str(bloque.get("text", "")))
        return "\n".join(partes).strip()

    @staticmethod
    def _motivo_de_respuesta_vacia(respuesta: dict) -> str:
        """Explica por qué no ha venido texto."""
        motivo = str(respuesta.get("stop_reason", "") or "")
        if motivo == "max_tokens":
            return _("La respuesta se ha cortado por ser demasiado larga.")
        if motivo:
            return _("El modelo no ha respondido nada (motivo: %s).") % motivo
        return _("El modelo no ha devuelto ninguna respuesta.")

    # -- operaciones -----------------------------------------------------------

    def describir(self, datos: bytes, tipo_mime: str, prompt: str) -> str:
        """Manda una imagen con su instrucción y devuelve el texto."""
        return self._enviar([
            {"type": "image", "source": {
                "type": "base64",
                "media_type": tipo_mime,
                "data": base64.b64encode(datos).decode("ascii"),
            }},
            {"type": "text", "text": prompt},
        ])

    def preguntar(self, pregunta: str) -> str:
        """Manda una pregunta de solo texto."""
        return self._enviar([{"type": "text", "text": pregunta}])

    def listar_modelos(self, solo_imagen: bool = True) -> list[str]:
        """Pide la lista de modelos disponibles.

        Si la API no contesta se devuelven los conocidos: es mejor ofrecer una
        lista corta que dejar al usuario escribiendo nombres a ciegas.
        """
        if not self.claves:
            raise ValueError(_("No hay ninguna clave API de Anthropic configurada."))
        try:
            respuesta = _peticion("models?limit=100", self.claves[0], None,
                                  min(self.tiempo_espera, 30.0))
            nombres = [str(ficha.get("id", "")) for ficha in respuesta.get("data") or []]
            nombres = [nombre for nombre in nombres if nombre]
        except Exception as error:
            log.info("Anthropic no ha dado la lista de modelos (%s); se usan los conocidos",
                     _mensaje_de_error(error))
            nombres = list(MODELOS_CONOCIDOS)
        if solo_imagen:
            nombres = [nombre for nombre in nombres if admite_imagen(nombre)]
        return sorted(set(nombres), reverse=True)

    def probar(self) -> str:
        """Comprueba que la clave y el modelo funcionan."""
        return self.preguntar(_("Responde solo con la palabra: correcto."))
