# -*- coding: utf-8 -*-
"""Puerta de entrada a la IA: elige proveedor, arma el prompt y describe.

Todo lo que el resto del programa necesita saber está aquí.  El servicio se
construye a partir de las preferencias, de modo que cambiar de Gemini a un
modelo local no obliga a tocar ni la ventana ni los diálogos.

Las llamadas son **lentas** (de un segundo a un minuto largo) y **bloquean**,
así que nunca deben hacerse en el hilo de la interfaz; los diálogos las lanzan
en un hilo aparte y recogen el resultado con ``wx.CallAfter``.
"""

from __future__ import annotations

from ..idioma import _
from nucleo.ia import consumo as contador
from nucleo.ia import prompts as tabla_prompts
from nucleo.ia.anthropic import Anthropic, MODELO_POR_OMISION as MODELO_ANTHROPIC
from nucleo.ia.gemini import Gemini, MODELO_POR_OMISION as MODELO_GEMINI
from nucleo.ia.local import Local, MODELO_POR_OMISION as MODELO_LOCAL, URL_POR_OMISION
from nucleo.ia.openai import (OpenAI, MODELO_POR_OMISION as MODELO_OPENAI,
                              URL_POR_OMISION as URL_OPENAI)
from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

#: Proveedores que se ofrecen, con la etiqueta que se ve en las preferencias.
#: Las claves son estables: se guardan en la configuración.
PROVEEDORES = (
    ("off", _("Desactivada")),
    ("gemini", _("Google Gemini (por internet)")),
    ("anthropic", _("Anthropic Claude (por internet)")),
    ("openai", _("OpenAI y compatibles: Groq, DeepSeek, OpenRouter... (por internet)")),
    ("local", _("Modelo local (llama.cpp, Ollama, LM Studio)")),
    # Este no está en la lista de fábrica: aparece en cuanto el asistente ha
    # instalado el Ollama del programa.  Ponerlo antes sería ofrecer algo que
    # todavía no existe y que al elegirlo solo daría un error.
    ("ollama_propio", _("IA local del programa (Ollama incluido)")),
)

#: Los que necesitan clave API y hablan por internet.
DE_INTERNET = ("gemini", "anthropic", "openai")


def nombre_de_proveedor(clave: str) -> str:
    """Etiqueta visible de un proveedor."""
    for identificador, etiqueta in PROVEEDORES:
        if identificador == clave:
            return etiqueta
    return clave


def nombres_de_proveedores() -> dict:
    """``{clave: nombre}`` de todos los proveedores, para el contador."""
    return {clave: nombre for clave, nombre in PROVEEDORES}

#: Tipos MIME por extensión de archivo.  Se resuelve a mano y no con
#: :mod:`mimetypes` porque el módulo depende del registro de Windows, que en
#: algunos equipos devuelve tipos raros para el mismo ``.jpg``.
TIPOS = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".jpe": "image/jpeg",
    ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp",
    ".bmp": "image/bmp", ".heic": "image/heic", ".heif": "image/heif",
}

#: Tipo que se manda cuando la extensión no dice nada.  Los proveedores lo
#: aceptan y deducen el formato real de los primeros bytes.
TIPO_GENERICO = "image/jpeg"

#: Tamaño máximo de imagen que se envía, en bytes.  Por encima, los servidores
#: suelen rechazar la petición; avisar antes es mejor que un error opaco.
MAXIMO = 18 * 1024 * 1024


class ErrorIA(Exception):
    """Algo ha impedido obtener la descripción.

    Lleva siempre un mensaje redactado para el usuario, porque acaba tal cual
    en un cuadro de diálogo y leído por el lector de pantalla.
    """


def tipo_mime(referencia: str) -> str:
    """Deduce el tipo MIME de una imagen por su nombre de archivo."""
    nombre = (referencia or "").lower()
    for extension, tipo in TIPOS.items():
        if nombre.endswith(extension):
            return tipo
    return TIPO_GENERICO


def nombre_corto_de_modelo(modelo: str) -> str:
    """Deja de un nombre de modelo solo la parte que lo identifica.

    Los servidores locales suelen dar como identificador la ruta completa del
    archivo del modelo; aquí se queda en ``gemma-4-E2B-it``, que es lo que hay
    que decir y lo que cabe en un aviso.
    """
    corto = (modelo or "").replace("\\", "/").rsplit("/", 1)[-1]
    for extension in (".gguf", ".bin", ".safetensors"):
        if corto.lower().endswith(extension):
            corto = corto[: -len(extension)]
    return corto or modelo


def _transcribir(turnos: list) -> str:
    """Escribe la conversación para los proveedores que no admiten turnos.

    Se marca quién dijo qué con un rótulo delante, y se cierra pidiendo la
    respuesta a lo último: sin esa última línea, algunos modelos siguen la
    conversación inventando también la pregunta siguiente.
    """
    partes = []
    for quien, texto in turnos[:-1]:
        rotulo = _("Asistente") if quien == "asistente" else _("Usuario")
        partes.append("%s: %s" % (rotulo, texto))
    ultima = turnos[-1][1] if turnos else ""
    if not partes:
        return ultima
    return _("Esta es la conversación que llevamos:\n\n%s\n\n"
             "Responde ahora a esto, teniendo en cuenta todo lo anterior:\n%s") % (
        "\n\n".join(partes), ultima)


class Servicio:
    """Describe imágenes con el proveedor configurado.

    :param configuracion: Preferencias de la aplicación.
    """

    def __init__(self, configuracion) -> None:
        self.configuracion = configuracion

    # -- estado --------------------------------------------------------------

    @property
    def proveedor(self) -> str:
        """Clave del proveedor activo."""
        return str(self.configuracion.obtener("ia_proveedor", "off") or "off")

    @property
    def activa(self) -> bool:
        """Indica si hay IA configurada y lista para usarse."""
        return self.proveedor != "off"

    def motivo_no_disponible(self) -> str:
        """Explica por qué no se puede usar la IA, o cadena vacía si sí se puede.

        Se comprueba **antes** de lanzar el hilo para poder decir qué falta en
        lugar de tener que esperar a que la petición falle.
        """
        if self.proveedor == "off":
            return (_("La inteligencia artificial está desactivada. Actívala en Opciones, "
                    "pestaña «Inteligencia artificial»."))
        if self.proveedor in DE_INTERNET and not self._claves():
            return (_("Falta la clave API de %s. Escríbela en Opciones, pestaña "
                    "«Inteligencia artificial».") % nombre_de_proveedor(self.proveedor))
        return ""

    def _claves(self) -> list[str]:
        """Claves API del proveedor activo, sin las líneas vacías.

        Se admiten varias, una por línea: cuando una agota su cuota se pasa a la
        siguiente sin que el usuario se entere.  Cada proveedor guarda las suyas
        aparte, para poder cambiar de uno a otro sin volver a escribirlas.
        """
        clave_ajuste = {
            "gemini": "ia_gemini_claves",
            "anthropic": "ia_anthropic_claves",
            "openai": "ia_openai_claves",
        }.get(self.proveedor, "")
        if not clave_ajuste:
            return []
        guardadas = self.configuracion.obtener(clave_ajuste, []) or []
        if isinstance(guardadas, str):
            guardadas = guardadas.splitlines()
        return [str(clave).strip() for clave in guardadas if str(clave).strip()]

    def _cliente(self):
        """Crea el cliente del proveedor activo."""
        espera = float(self.configuracion.obtener("ia_tiempo_espera", 90) or 90)
        obtener = self.configuracion.obtener
        if self.proveedor == "gemini":
            return Gemini(self._claves(),
                          str(obtener("ia_gemini_modelo", MODELO_GEMINI) or MODELO_GEMINI),
                          espera)
        if self.proveedor == "anthropic":
            return Anthropic(self._claves(),
                             str(obtener("ia_anthropic_modelo", MODELO_ANTHROPIC)
                                 or MODELO_ANTHROPIC),
                             espera)
        if self.proveedor == "openai":
            return OpenAI(self._claves(),
                          str(obtener("ia_openai_url", URL_OPENAI) or URL_OPENAI),
                          str(obtener("ia_openai_modelo", MODELO_OPENAI) or MODELO_OPENAI),
                          espera)
        if self.proveedor == "local":
            # Más espera que los de internet: en una tarjeta modesta, describir
            # una imagen puede tardar bastante más que en la nube.
            return Local(str(obtener("ia_local_url", URL_POR_OMISION) or URL_POR_OMISION),
                         str(obtener("ia_local_modelo", MODELO_LOCAL) or MODELO_LOCAL),
                         max(espera, 120.0))
        if self.proveedor == "ollama_propio":
            # El Ollama del programa habla la misma API que los demás
            # servidores locales, así que se usa el mismo cliente.  Lo que
            # cambia es que la dirección no la escribe nadie —es siempre la
            # nuestra, en un puerto que no le pisa el suyo a quien ya tenga
            # Ollama instalado— y que el servidor se arranca solo.
            from . import ollama

            ollama.gestor.configuracion = self.configuracion
            if not ollama.gestor.asegurar_en_marcha():
                raise ErrorIA(_(
                    "La IA local del programa no está en marcha y no se ha podido "
                    "arrancar. Ve a Opciones, «IA local», y comprueba el servidor."))
            modelo = str(obtener("ollama_modelo", "") or "")
            if not modelo:
                raise ErrorIA(_(
                    "No has elegido con qué modelo trabajar. Ve a Opciones, «IA local», "
                    "y elige uno de los que tienes descargados."))
            # Un modelo local tarda mucho más que la nube en un equipo sin
            # tarjeta gráfica: la espera se cuenta en minutos, no en segundos.
            return Local(ollama.url_openai(), modelo, max(espera, 300.0))
        raise ErrorIA(self.motivo_no_disponible() or _("No hay ningún proveedor de IA activo."))

    def _anotar(self, cliente, clase: str, fallo: bool = False) -> None:
        """Suma la petición al contador de consumo.

        Nunca deja que un fallo aquí estropee una operación que ha ido bien:
        llevar la cuenta es útil, pero no al precio de perder una descripción
        que ya está hecha.
        """
        try:
            entrada, salida = getattr(cliente, "ultimo_gasto", (0, 0))
            contador.anotar(self.configuracion, self.proveedor,
                            entrada=entrada, salida=salida, clase=clase, fallo=fallo)
        except Exception as error:
            log.debug("No se ha podido anotar el consumo: %s", error)

    # -- operaciones ---------------------------------------------------------

    def describir(self, datos: bytes, referencia: str, prompt=None,
                  contexto: str = "") -> str:
        """Describe una imagen y devuelve el texto.

        Bloquea hasta que el proveedor responde, así que hay que llamarla desde
        un hilo que no sea el de la interfaz.

        :param datos: Bytes de la imagen, tal y como salen del EPUB.
        :param referencia: Nombre del archivo dentro del libro, del que se
                           deduce el tipo de imagen.
        :param prompt: Prompt que se quiere usar.  Si es ``None`` se usa el
                       preferido.
        :param contexto: Datos del libro que ayuden a describir mejor.
        :raises ErrorIA: Con un mensaje ya redactado para el usuario.
        """
        motivo = self.motivo_no_disponible()
        if motivo:
            raise ErrorIA(motivo)
        if not datos:
            raise ErrorIA(_("No se ha podido extraer la imagen del documento."))
        if len(datos) > MAXIMO:
            raise ErrorIA(
                _("La imagen ocupa %.1f MB y no se puede enviar (el máximo son %d MB).")
                % (len(datos) / 1048576, MAXIMO // 1048576))
        elegido = prompt or tabla_prompts.preferido(self.configuracion)
        instruccion = tabla_prompts.texto_completo(elegido, contexto)
        cliente = self._cliente()
        log.info("Describiendo «%s» con %s (%d KB, prompt «%s»)",
                 referencia, self.proveedor, len(datos) // 1024, elegido.nombre)
        try:
            texto = cliente.describir(datos, tipo_mime(referencia), instruccion)
        except ErrorIA:
            self._anotar(cliente, "imagen", fallo=True)
            raise
        except Exception as error:
            self._anotar(cliente, "imagen", fallo=True)
            raise ErrorIA(str(error)) from error
        self._anotar(cliente, "imagen")
        texto = (texto or "").strip()
        if not texto:
            raise ErrorIA(_("La inteligencia artificial no ha devuelto ninguna descripción."))
        return texto

    def preguntar(self, pregunta: str) -> str:
        """Hace una pregunta de solo texto y devuelve la respuesta.

        Bloquea hasta que el proveedor contesta, así que hay que llamarla desde
        un hilo que no sea el de la interfaz.

        :raises ErrorIA: Con un mensaje ya redactado para el usuario.
        """
        motivo = self.motivo_no_disponible()
        if motivo:
            raise ErrorIA(motivo)
        if not (pregunta or "").strip():
            raise ErrorIA(_("No hay nada que preguntar."))
        cliente = self._cliente()
        try:
            texto = cliente.preguntar(pregunta)
        except ErrorIA:
            self._anotar(cliente, "pregunta", fallo=True)
            raise
        except Exception as error:
            self._anotar(cliente, "pregunta", fallo=True)
            raise ErrorIA(str(error)) from error
        self._anotar(cliente, "pregunta")
        texto = (texto or "").strip()
        if not texto:
            raise ErrorIA(_("La inteligencia artificial no ha contestado nada."))
        return texto

    def conversar(self, turnos: list) -> str:
        """Sigue una conversación teniendo en cuenta lo que ya se ha hablado.

        :param turnos: Lista de ``(quién, qué)`` con «usuario» o «asistente»,
                       en orden y acabando en una pregunta del usuario.

        Es lo que convierte una respuesta suelta en una conversación: un
        estudiante pregunta por una fórmula, y sobre esa respuesta pregunta
        «¿y por qué el signo cambia?» sin tener que volver a explicar de qué
        fórmula habla.

        No todos los proveedores tienen una forma nativa de mandar varios
        turnos, así que hay dos caminos.  Con los que sí —los que hablan el
        formato de OpenAI, que son el modelo local y el propio del programa—
        se manda la conversación con sus papeles, que es lo que mejor
        entienden.  Con los demás se le pasa la conversación **escrita**, que
        funciona igual de bien y evita cuatro implementaciones distintas de lo
        mismo.
        """
        motivo = self.motivo_no_disponible()
        if motivo:
            raise ErrorIA(motivo)
        if not turnos:
            raise ErrorIA(_("No hay nada que preguntar."))
        cliente = self._cliente()
        try:
            if hasattr(cliente, "conversar"):
                texto = cliente.conversar(turnos)
            else:
                texto = cliente.preguntar(_transcribir(turnos))
        except ErrorIA:
            self._anotar(cliente, "pregunta", fallo=True)
            raise
        except Exception as error:
            self._anotar(cliente, "pregunta", fallo=True)
            raise ErrorIA(str(error)) from error
        self._anotar(cliente, "pregunta")
        texto = (texto or "").strip()
        if not texto:
            raise ErrorIA(_("La inteligencia artificial no ha contestado nada."))
        return texto

    def listar_modelos(self) -> list[str]:
        """Pregunta al proveedor qué modelos tiene disponibles.

        Solo se devuelven los que pueden describir imágenes, que es para lo
        único que este programa usa la IA.
        """
        motivo = self.motivo_no_disponible()
        if motivo:
            raise ErrorIA(motivo)
        try:
            return self._cliente().listar_modelos()
        except Exception as error:
            raise ErrorIA(str(error)) from error

    def probar(self) -> str:
        """Comprueba que el proveedor contesta, y devuelve lo que ha dicho."""
        motivo = self.motivo_no_disponible()
        if motivo:
            raise ErrorIA(motivo)
        try:
            return self._cliente().probar()
        except Exception as error:
            raise ErrorIA(str(error)) from error

    def descripcion_del_modelo(self) -> str:
        """Frase corta con el proveedor y el modelo, para los avisos.

        Del nombre del modelo se deja solo lo que identifica: los servidores
        locales suelen devolver la ruta entera del archivo ``.gguf``, y leer en
        voz alta «ce dos puntos barra usuarios barra...» cada vez que se
        describe una imagen no le sirve a nadie.
        """
        obtener = self.configuracion.obtener
        if self.proveedor == "gemini":
            return "Gemini (%s)" % obtener("ia_gemini_modelo", MODELO_GEMINI)
        if self.proveedor == "anthropic":
            return "Claude (%s)" % nombre_corto_de_modelo(
                str(obtener("ia_anthropic_modelo", MODELO_ANTHROPIC)))
        if self.proveedor == "openai":
            return "%s (%s)" % (_("servicio compatible con OpenAI"),
                                nombre_corto_de_modelo(
                                    str(obtener("ia_openai_modelo", MODELO_OPENAI))))
        if self.proveedor == "local":
            return "modelo local (%s)" % nombre_corto_de_modelo(
                str(obtener("ia_local_modelo", MODELO_LOCAL)))
        return _("sin proveedor")

    def consumo(self) -> str:
        """Frase con lo que se lleva gastado con cada proveedor."""
        return contador.resumen_completo(self.configuracion, nombres_de_proveedores())
