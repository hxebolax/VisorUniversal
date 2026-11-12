# -*- coding: utf-8 -*-
"""Preguntarle cosas a la IA sobre el documento que se está leyendo.

Resumir el capítulo, saber quién era un personaje que aparece cincuenta páginas
después de su presentación, entender un párrafo difícil.  Todo eso es la misma
operación: coger un trozo del documento, mandarlo con una pregunta y leer la
respuesta.

El único problema de verdad es **cuánto texto se manda**.  Un libro entero no
cabe en una petición, y aunque cupiera costaría una fortuna y tardaría un rato
largo.  Por eso hay que elegir el trozo:

* **El capítulo** donde está el cursor: lo que se quiere el 90 % de las veces.
* **Lo que hay alrededor** del cursor, para una pregunta sobre lo que se acaba
  de leer.
* **Lo seleccionado**, para preguntar por un párrafo concreto.
* **Todo lo leído hasta aquí**, que es lo que hace falta para «resúmeme lo que
  llevo» sin destripar el final.

Y si el trozo elegido sigue siendo enorme se recorta, avisando de que se ha
recortado: es preferible una respuesta sobre parte del capítulo que un error.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..idioma import _
from ..marcas import TipoMarca
from ..registro import obtener_registro

log = obtener_registro(__name__)

#: Cuánto texto se manda como mucho, en caracteres.  Unas veinte páginas: entra
#: de sobra en cualquier modelo actual, cuesta poco y tarda poco.  Subirlo haría
#: cada pregunta más cara sin mejorar casi nunca la respuesta.
MAXIMO = 60000

#: Caracteres a cada lado del cursor cuando se pregunta «por aquí».
ALREDEDOR = 6000


@dataclass
class Trozo:
    """El texto que se le manda a la IA, con su nombre."""

    texto: str
    rotulo: str
    recortado: bool = False


def _recortar(texto: str, rotulo: str) -> Trozo:
    """Deja el texto en algo que se pueda mandar, avisando si se ha recortado.

    Se corta por el **final** y no por el principio: en un capítulo, lo que hay
    al empezar es lo que da el contexto, y perder eso deja la respuesta sin
    apoyo.
    """
    limpio = texto.strip()
    if len(limpio) <= MAXIMO:
        return Trozo(limpio, rotulo)
    cortado = limpio[:MAXIMO]
    # Se corta en el último final de frase, para no dejar una a medias.
    punto = max(cortado.rfind(". "), cortado.rfind(".\n"))
    if punto > MAXIMO // 2:
        cortado = cortado[:punto + 1]
    return Trozo(cortado, rotulo, recortado=True)


# ---------------------------------------------------------------------------
# De dónde se saca el texto
# ---------------------------------------------------------------------------

def capitulo_en(documento, posicion: int) -> Trozo:
    """El capítulo donde cae esa posición.

    Se buscan primero los saltos de sección, que es lo que separa los archivos
    de un EPUB, y si el documento no los trae, los encabezados de nivel 1.  Sin
    ninguna de las dos cosas —un texto suelto, un PDF sin estructura— se manda
    lo que hay alrededor, que es lo más parecido a «este capítulo» que existe.
    """
    texto = documento.texto
    for tipo in (TipoMarca.SALTO_SECCION, TipoMarca.ENCABEZADO1):
        grupo = documento.marcas.grupo(tipo)
        if len(grupo) < 2:
            continue
        inicio, fin, titulo = 0, len(texto), ""
        for marca in grupo.marcas:
            if marca.posicion <= posicion:
                inicio, titulo = marca.posicion, marca.texto.strip()
            elif marca.posicion > posicion:
                fin = marca.posicion
                break
        rotulo = _("el capítulo «%s»") % titulo if titulo else _("este capítulo")
        return _recortar(texto[inicio:fin], rotulo)
    return alrededor_de(documento, posicion)


def alrededor_de(documento, posicion: int, margen: int = ALREDEDOR) -> Trozo:
    """Lo que hay a los dos lados del cursor."""
    texto = documento.texto
    inicio = max(0, posicion - margen)
    fin = min(len(texto), posicion + margen)
    return _recortar(texto[inicio:fin], _("lo que hay alrededor de donde estás leyendo"))


def leido_hasta(documento, posicion: int) -> Trozo:
    """Todo lo que va desde el principio hasta el cursor.

    Es lo que hace falta para pedir un resumen de por dónde va la historia **sin
    que la IA destripe el final**: no se le manda lo que todavía no se ha leído,
    así que no puede contarlo.
    """
    return _recortar(documento.texto[:posicion],
                     _("todo lo que llevas leído hasta aquí"))


def documento_entero(documento) -> Trozo:
    """El documento completo, recortado si hace falta."""
    return _recortar(documento.texto, _("el documento entero"))


def seleccion(texto: str) -> Trozo:
    """El texto que el usuario tenía seleccionado."""
    return _recortar(texto, _("el fragmento que has seleccionado"))


#: Ámbitos que se ofrecen, con su nombre y de dónde sacan el texto.  El orden es
#: el de lo más pedido a lo menos.
AMBITOS = (
    ("capitulo", _("El capítulo donde estoy")),
    ("alrededor", _("Lo que hay alrededor del cursor")),
    ("seleccion", _("Solo lo que tengo seleccionado")),
    ("leido", _("Todo lo que llevo leído (sin destripar el final)")),
    ("todo", _("El documento entero")),
)


def trozo_para(ambito: str, documento, posicion: int, texto_seleccionado: str = "") -> Trozo:
    """Devuelve el trozo que corresponde a un ámbito."""
    if ambito == "seleccion" and texto_seleccionado.strip():
        return seleccion(texto_seleccionado)
    if ambito == "alrededor":
        return alrededor_de(documento, posicion)
    if ambito == "leido":
        return leido_hasta(documento, posicion)
    if ambito == "todo":
        return documento_entero(documento)
    return capitulo_en(documento, posicion)


# ---------------------------------------------------------------------------
# Las preguntas
# ---------------------------------------------------------------------------

#: Preguntas hechas, para no tener que escribirlas.  La primera es la que más
#: se usa con diferencia, y por eso va primera.
PREGUNTAS = (
    ("resumen", _("Resúmeme esto"),
     _("Resume el texto en unos pocos párrafos, contando lo que pasa y lo que "
       "importa. No añadas opiniones ni interpretaciones tuyas.")),
    ("puntos", _("¿Cuáles son las ideas principales?"),
     _("Enumera las ideas principales del texto, una por línea, empezando cada "
       "una por su número y un punto. Sé conciso.")),
    ("personajes", _("¿Quién es quién?"),
     _("Di qué personas o personajes aparecen en el texto y qué papel tiene cada "
       "uno, en una línea por cada uno. Si no aparece ninguno, dilo.")),
    ("explicar", _("Explícamelo más sencillo"),
     _("Explica el texto con palabras llanas, como se lo contarías a alguien que "
       "no es del tema. Mantén todo lo que dice, sin quitarle nada.")),
    ("dificil", _("¿Qué palabras o términos difíciles hay?"),
     _("Señala las palabras, tecnicismos o expresiones poco corrientes que "
       "aparecen en el texto y explica brevemente cada una.")),
    ("libre", _("Escribir mi propia pregunta"), ""),
)


def texto_de_pregunta(identificador: str) -> str:
    """La instrucción de una pregunta hecha, o cadena vacía si es libre."""
    for clave, _nombre, instruccion in PREGUNTAS:
        if clave == identificador:
            return instruccion
    return ""


def nombre_de_pregunta(identificador: str) -> str:
    """Nombre visible de una pregunta hecha."""
    for clave, nombre, _instruccion in PREGUNTAS:
        if clave == identificador:
            return nombre
    return identificador


def armar(pregunta: str, trozo: Trozo, titulo: str = "", autor: str = "") -> str:
    """Arma la petición completa que se le manda a la IA.

    Se le dice **qué es** lo que recibe —un trozo de un libro, con su título y
    su autor—, **qué trozo es** y qué tiene que hacer con él.  Y se le pide la
    respuesta en el idioma del programa y sin markdown, porque va a leerse en
    voz alta con un lector de pantalla y los asteriscos y las almohadillas se
    leen uno a uno.
    """
    from ..idioma import nombre_activo

    encabezado = [_(
        "Eres un asistente que ayuda a leer documentos a personas ciegas, que van a "
        "escuchar tu respuesta con un lector de pantalla.\n\n"
        "Responde SIEMPRE en %(idioma)s, en texto corrido, sin markdown, sin "
        "asteriscos, sin almohadillas y sin viñetas: esos signos se leen uno a uno "
        "y estorban. Puedes numerar con «1.», «2.» si hace falta una lista.\n\n"
        "No inventes nada que no esté en el texto. Si el texto no da para "
        "responder, dilo claramente en una frase."
    ) % {"idioma": nombre_activo()}]

    datos = []
    if titulo:
        datos.append(_("Título: %s") % titulo)
    if autor:
        datos.append(_("Autor: %s") % autor)
    if datos:
        encabezado.append("\n".join(datos))

    aviso = ""
    if trozo.recortado:
        aviso = _(" (recortado: es solo el principio, no cabía entero)")
    encabezado.append(_("Lo que viene a continuación es %(cual)s%(aviso)s:")
                      % {"cual": trozo.rotulo, "aviso": aviso})
    encabezado.append("«««\n%s\n»»»" % trozo.texto)
    encabezado.append(_("Tu tarea: %s") % pregunta.strip())
    return "\n\n".join(encabezado)


# ---------------------------------------------------------------------------
# La conversación
# ---------------------------------------------------------------------------

#: Cuántos turnos se conservan.  Cada vuelta se manda la conversación entera,
#: así que dejarla crecer sin fin acaba costando tiempo y cuota, y en un modelo
#: local, chocando con el tamaño del contexto.  Con veinte turnos se cubre de
#: sobra una conversación de estudio sobre un capítulo.
TURNOS_MAXIMOS = 20


class Conversacion:
    """Lo que se lleva hablado con la inteligencia artificial sobre un documento.

    Preguntar una cosa y que la respuesta se quede sola sirve para una duda
    suelta.  Pero quien estudia no tiene una duda suelta: pregunta por una
    fórmula, no entiende un paso y vuelve a preguntar sobre **esa respuesta**.
    Sin memoria, esa segunda pregunta obliga a repetir de qué se hablaba.

    Aquí se guardan los turnos y se arma cada envío.  El texto del documento
    solo viaja **la primera vez**: es lo más largo con diferencia, y repetirlo
    en cada vuelta multiplicaría el coste sin añadir nada, porque ya está en la
    conversación que se manda entera.
    """

    __slots__ = ("turnos", "titulo", "autor", "_con_contexto")

    def __init__(self, titulo: str = "", autor: str = "") -> None:
        #: Pares ``(quién, qué)`` con «usuario» o «asistente».
        self.turnos: list[tuple[str, str]] = []
        self.titulo = titulo
        self.autor = autor
        self._con_contexto = False

    def __len__(self) -> int:
        return len(self.turnos)

    @property
    def vacia(self) -> bool:
        """Si todavía no se ha preguntado nada."""
        return not self.turnos

    def preparar(self, pregunta: str, trozo=None) -> list:
        """Añade la pregunta y devuelve lo que hay que mandar.

        :param trozo: El texto del documento sobre el que se pregunta.  Solo se
                      mete en el primer turno.
        """
        if trozo is not None and not self._con_contexto:
            texto = armar(pregunta, trozo, self.titulo, self.autor)
            self._con_contexto = True
        else:
            texto = pregunta
        self.turnos.append(("usuario", texto))
        self._podar()
        return list(self.turnos)

    def responder(self, respuesta: str) -> None:
        """Anota lo que ha contestado la inteligencia artificial."""
        self.turnos.append(("asistente", respuesta))
        self._podar()

    def deshacer_ultima(self) -> None:
        """Quita la última pregunta cuando no ha llegado a contestarse.

        Sin esto, una pregunta que falla se quedaría en la conversación y todas
        las siguientes irían arrastrando un turno sin respuesta.
        """
        if self.turnos and self.turnos[-1][0] == "usuario":
            self.turnos.pop()

    def olvidar(self) -> None:
        """Empieza una conversación nueva."""
        self.turnos.clear()
        self._con_contexto = False

    def _podar(self) -> None:
        """Deja solo los últimos turnos, sin cortar por la mitad de un par."""
        sobran = len(self.turnos) - TURNOS_MAXIMOS
        if sobran > 0:
            # Se quita un número par para que no quede una respuesta sin su
            # pregunta, que confunde al modelo más que ayudarle.
            del self.turnos[:sobran + (sobran % 2)]

    def como_texto(self) -> str:
        """La conversación entera, para copiarla o releerla."""
        lineas = []
        for quien, texto in self.turnos:
            lineas.append("%s: %s" % (_("Tú") if quien == "usuario" else _("IA"), texto))
        return "\n\n".join(lineas)
