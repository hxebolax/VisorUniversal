# -*- coding: utf-8 -*-
"""Definir la palabra que hay bajo el cursor.

Leyendo aparecen palabras que uno no conoce, y salir del programa a buscarlas
rompe la lectura.  Este módulo las define sin moverse del libro, con tres
fuentes que se complementan:

* **El Diccionario de la lengua española**, de la Real Academia.  Es la
  referencia para el español: da la etimología, las acepciones numeradas con su
  categoría gramatical y los sinónimos y antónimos.  Se lee de ``dle.rae.es``,
  que no ofrece una API pública, así que hay que interpretar su página.
* **El Wikcionario**, que sí tiene API y cubre **cualquier idioma**: la misma
  consulta vale para el inglés, el francés o el catalán cambiando el subdominio.
  Es la fuente para un libro que no esté en español.
* **La inteligencia artificial ya configurada**, que es la única que entiende
  *el contexto*: sabe distinguir el «banco» de sentarse del de dinero porque se
  le pasa la frase entera, y define también las locuciones y los nombres
  propios, que no salen en ningún diccionario.

Ninguna de las tres es siempre la mejor, y por eso se eligen desde el propio
diálogo sin tener que volver a las opciones.

La lógica de lectura del DLE está tomada del complemento **DLEChecker** para
NVDA, del mismo autor.  Aquí se interpreta con ``lxml`` en vez de con
BeautifulSoup —``lxml`` ya viene con el programa— y se ha comprobado que el
sitio responde sin necesidad de ``cloudscraper``; si algún día dejara de
hacerlo, quedan las otras dos fuentes.
"""

from __future__ import annotations

import copy
import json
import re
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from .idioma import _
from .registro import obtener_registro

log = obtener_registro(__name__)

#: Identificadores de las fuentes.  Se guardan en la configuración, así que no
#: pueden cambiar de nombre a la ligera.
RAE = "rae"
WIKCIONARIO = "wikcionario"
IA = "ia"

#: Fuentes en el orden en que se ofrecen, con su nombre visible.
FUENTES: tuple[tuple[str, str], ...] = (
    (RAE, _("Diccionario de la lengua española (RAE)")),
    (WIKCIONARIO, _("Wikcionario")),
    (IA, _("Inteligencia artificial")),
)

#: Cabeceras de las peticiones.  Los sitios que rechazan a los programas
#: automáticos miran el «User-Agent»; se declara uno de navegador porque de
#: otro modo el DLE responde con una página de comprobación en vez de con la
#: definición.
CABECERAS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept-Language": "es-ES,es;q=0.9",
}

#: Segundos que se espera a cada servicio.
ESPERA = 20

#: Dirección del DLE.  La consulta es la palabra sin más: ``dle.rae.es/casa``.
URL_RAE = "https://dle.rae.es"

#: Caracteres que pueden formar parte de una palabra.  Incluye el guion y el
#: apóstrofo porque «arco-iris» y «l'home» son palabras, y las letras con tilde
#: y la eñe porque sin ellas «acción» se partiría en dos.
LETRAS = re.compile(r"[^\W\d_]", re.UNICODE)

#: Lo que se recorta de los bordes de una palabra copiada del texto.
BORDES = " \t\r\n\"'“”«»‘’()[]{}.,;:¡!¿?…-–—*_/\\|<>+=%&#@~^`´¨·"

#: Longitud máxima razonable de una palabra.  Más que eso es que se ha
#: seleccionado un párrafo entero, y ningún diccionario va a saber qué hacer.
MAXIMO = 60


@dataclass
class Acepcion:
    """Una acepción de una palabra, tal y como la da el diccionario."""

    texto: str
    numero: int = 0
    categoria: str = ""
    sinonimos: list[str] = field(default_factory=list)
    antonimos: list[str] = field(default_factory=list)

    def legible(self) -> str:
        """La acepción en una o varias líneas, listas para leer en voz alta."""
        cabeza = "%d. " % self.numero if self.numero else ""
        if self.categoria:
            cabeza += "(%s) " % self.categoria
        lineas = [cabeza + self.texto]
        if self.sinonimos:
            lineas.append(_("   Sinónimos: %s.") % ", ".join(self.sinonimos))
        if self.antonimos:
            lineas.append(_("   Antónimos: %s.") % ", ".join(self.antonimos))
        return "\n".join(lineas)


@dataclass
class Entrada:
    """Todo lo que se ha averiguado de una palabra."""

    palabra: str
    fuente: str = RAE
    etimologia: str = ""
    acepciones: list[Acepcion] = field(default_factory=list)
    #: Texto sin estructurar, para las fuentes que no dan acepciones sueltas
    #: (el Wikcionario y la IA devuelven prosa).
    texto: str = ""
    error: str = ""

    @property
    def vacia(self) -> bool:
        """Indica si no se ha encontrado nada que enseñar."""
        return not self.acepciones and not self.texto.strip()

    def nombre_fuente(self) -> str:
        """Nombre visible de la fuente de la que salió."""
        for clave, nombre in FUENTES:
            if clave == self.fuente:
                return nombre
        return self.fuente

    def legible(self) -> str:
        """La entrada entera como texto corrido, para leerla o copiarla."""
        if self.error:
            return self.error
        partes = [_("%(palabra)s — %(fuente)s") % {"palabra": self.palabra,
                                                   "fuente": self.nombre_fuente()}]
        if self.etimologia:
            partes.append("")
            partes.append(_("Etimología: %s") % self.etimologia)
        if self.acepciones:
            partes.append("")
            partes.extend(acepcion.legible() for acepcion in self.acepciones)
        if self.texto.strip():
            partes.append("")
            partes.append(self.texto.strip())
        return "\n".join(partes)


# ---------------------------------------------------------------------------
# La palabra que se va a consultar
# ---------------------------------------------------------------------------

def limpiar(texto: str) -> str:
    """Deja una palabra suelta a partir de lo que haya seleccionado el usuario.

    Se quitan los signos de los bordes —una palabra a final de frase viene con
    el punto pegado— y se recorta a la primera si venían varias.  Las
    locuciones de dos o tres palabras se respetan: «a la sazón» está en el
    diccionario y partirla lo estropearía.
    """
    limpio = " ".join(str(texto or "").split()).strip(BORDES)
    if len(limpio) > MAXIMO:
        limpio = limpio[:MAXIMO].rsplit(" ", 1)[0]
    return limpio.strip(BORDES)


def es_valida(palabra: str) -> bool:
    """Indica si merece la pena consultar eso.

    Basta con que tenga alguna letra y no sea absurdamente larga: un número
    suelto, un signo o una línea entera no llevan a ninguna parte y consultarlos
    solo consigue una espera y un «no encontrado».
    """
    if not palabra or len(palabra) > MAXIMO:
        return False
    return bool(LETRAS.search(palabra))


#: Cuántos caracteres se miran hacia delante buscando una palabra cuando el
#: cursor está sobre un signo.  Corto y sin pasar de la línea: los signos que
#: abren —«, ¿, (, comillas— van pegados a la palabra, así que con unos pocos
#: caracteres se llega.  Ir más lejos acabaría definiendo una palabra que está
#: en otro renglón y que no es la que se tenía delante.
ALCANCE = 30


def palabra_en(texto: str, posicion: int) -> str:
    """Devuelve la palabra que hay en esa posición del texto.

    Si el cursor está justo encima de una palabra, es esa.  Si está en un
    espacio o en un signo —el punto de una frase, las comillas o el «¿» que
    abre, la sangría del principio de una línea—, se busca **la palabra más
    cercana en la misma línea**, mirando a los dos lados a la vez; empatando,
    manda la de la izquierda, que es la que se acaba de leer.

    Una palabra puede llevar dentro un guion («arco-iris») o un apóstrofo
    («l'home»): esos no la cortan.  Los saltos de línea sí, porque la palabra
    del renglón de al lado no es la que se tenía delante.  La excepción es el
    cursor puesto **sobre** un salto de línea —el final de una línea, o una
    línea en blanco—: ahí no hay ninguna palabra propia que ofrecer, así que se
    coge la del renglón siguiente.
    """
    if not texto:
        return ""
    largo = len(texto)
    posicion = max(0, min(largo - 1, posicion))

    def es_parte(indice: int) -> bool:
        if not 0 <= indice < largo:
            return False
        caracter = texto[indice]
        return bool(LETRAS.match(caracter)) or caracter in "-'’"

    if not es_parte(posicion):
        encontrada = -1
        izquierda = derecha = True
        for salto in range(1, ALCANCE + 1):
            antes, despues = posicion - salto, posicion + salto
            # Se deja de mirar hacia un lado en cuanto se cruza un salto de
            # línea: a partir de ahí ya es otro renglón.
            if izquierda and (antes < 0 or texto[antes] == "\n"):
                izquierda = False
            if derecha and (despues >= largo or texto[despues] == "\n"):
                derecha = False
            if izquierda and es_parte(antes):
                encontrada = antes
                break
            if derecha and es_parte(despues):
                encontrada = despues
                break
            if not izquierda and not derecha:
                break
        if encontrada < 0:
            return ""
        posicion = encontrada

    inicio = posicion
    while es_parte(inicio - 1):
        inicio -= 1
    fin = posicion
    while es_parte(fin + 1):
        fin += 1
    return limpiar(texto[inicio:fin + 1])


def frase_en(texto: str, posicion: int, margen: int = 160) -> str:
    """Trozo de texto alrededor de una posición, para dárselo a la IA.

    Sin contexto, «banco» tiene cinco significados y la IA elige uno al azar;
    con la frase delante elige el que toca.  No se usa el segmentador de frases
    a propósito: aquí vale un trozo generoso, y cuanto menos se dependa de
    dónde acaba exactamente la frase, mejor.
    """
    if not texto:
        return ""
    inicio = max(0, posicion - margen)
    fin = min(len(texto), posicion + margen)
    return " ".join(texto[inicio:fin].split())


# ---------------------------------------------------------------------------
# El Diccionario de la lengua española
# ---------------------------------------------------------------------------

def _descargar(url: str, espera: int = ESPERA) -> str:
    """Descarga una página como texto, o lanza una excepción."""
    peticion = urllib.request.Request(url, headers=CABECERAS)
    with urllib.request.urlopen(peticion, timeout=espera) as respuesta:
        datos = respuesta.read()
    return datos.decode("utf-8", errors="replace")


def _sin_tildes(texto: str) -> str:
    """Quita las tildes, para comparar sin que estorben."""
    plano = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in plano if not unicodedata.combining(c))


def consultar_rae(palabra: str, espera: int = ESPERA) -> Entrada:
    """Busca una palabra en el diccionario de la Real Academia.

    La página del DLE tiene esta forma: un ``<article>`` por entrada, dentro de
    él la etimología en un ``div`` de clase ``n2`` y las acepciones en una
    ``<ol class="c-definitions">``, una por ``<li class="j">``, con el número en
    un ``span`` de clase ``n_acep``, la categoría gramatical en un ``<abbr>`` y
    los sinónimos y antónimos en un pie aparte.

    :return: La entrada, con ``error`` puesto si no se ha podido consultar.  No
             lanza excepciones: quien llama solo tiene que enseñar lo que
             venga.
    """
    from lxml import html as lector_html

    palabra = limpiar(palabra)
    entrada = Entrada(palabra=palabra, fuente=RAE)
    try:
        pagina = _descargar("%s/%s" % (URL_RAE, urllib.parse.quote(palabra)), espera)
    except Exception as error:
        log.info("No se ha podido consultar el DLE: %s", error)
        entrada.error = _("No se ha podido consultar el diccionario de la RAE: %s") % error
        return entrada

    if "La entrada no se encuentra en el Diccionario" in pagina:
        entrada.error = _("«%s» no está en el diccionario de la RAE.") % palabra
        return entrada
    try:
        arbol = lector_html.fromstring(pagina)
    except Exception as error:
        entrada.error = _("No se ha entendido la respuesta del diccionario: %s") % error
        return entrada

    articulos = arbol.xpath("//article")
    if not articulos:
        entrada.error = _("«%s» no está en el diccionario de la RAE.") % palabra
        return entrada
    articulo = articulos[0]

    etimologias = articulo.xpath(".//div[contains(@class,'n2')]")
    if etimologias:
        entrada.etimologia = " ".join(etimologias[0].text_content().split())

    elementos = articulo.xpath(".//ol[contains(@class,'c-definitions')]"
                               "/li[contains(@class,'j')]")
    for numero, elemento in enumerate(elementos, start=1):
        entrada.acepciones.append(_acepcion_rae(elemento, numero))
    if not entrada.acepciones:
        entrada.error = _("«%s» aparece en el DLE, pero sin ninguna acepción legible.") % palabra
    return entrada


def _acepcion_rae(elemento, numero: int) -> Acepcion:
    """Convierte un ``<li>`` del DLE en una acepción."""
    abreviaturas = elemento.xpath(".//abbr[contains(@class,'d') or contains(@class,'g')]")
    categoria = abreviaturas[0].text_content().strip() if abreviaturas else ""

    # Se trabaja sobre una copia porque hay que ir quitando trozos —el número,
    # las abreviaturas, el pie con los sinónimos— y el árbol original todavía
    # hace falta para leer justamente ese pie.
    copia = copy.deepcopy(elemento)
    sobra = copia.xpath(".//span[contains(@class,'n_acep')] | .//abbr"
                        " | .//div[contains(@class,'item-footer')]")
    for nodo in sobra:
        padre = nodo.getparent()
        if padre is not None:
            # El texto que hubiera *detrás* del nodo pertenece a la definición y
            # se perdería al quitarlo: hay que devolvérselo al padre.
            if nodo.tail:
                anterior = nodo.getprevious()
                if anterior is not None:
                    anterior.tail = (anterior.tail or "") + nodo.tail
                else:
                    padre.text = (padre.text or "") + nodo.tail
            padre.remove(nodo)
    texto = " ".join(copia.text_content().split())

    return Acepcion(
        texto=texto,
        numero=numero,
        categoria=categoria,
        sinonimos=_lista_rae(elemento, "Sin"),
        antonimos=_lista_rae(elemento, "Ant"),
    )


def _lista_rae(elemento, clase: str) -> list[str]:
    """Sinónimos o antónimos de una acepción del DLE.

    :param clase: ``"Sin"`` para los sinónimos, ``"Ant"`` para los antónimos.
                  Los dos van en el mismo tipo de bloque y solo se distinguen
                  por el rótulo.
    """
    palabras: list[str] = []
    for bloque in elemento.xpath(".//div[contains(@class,'c-word-list')]"):
        rotulos = bloque.xpath(".//abbr[contains(@class,'sin-header-inline')]")
        if not rotulos or not rotulos[0].text_content().strip().startswith(clase):
            continue
        for palabra in bloque.xpath(".//span[contains(@class,'sin')]"):
            texto = palabra.text_content().strip()
            if texto:
                palabras.append(texto)
    return palabras


# ---------------------------------------------------------------------------
# El Wikcionario
# ---------------------------------------------------------------------------

def consultar_wikcionario(palabra: str, idioma_wiki: str = "es",
                          espera: int = ESPERA) -> Entrada:
    """Busca una palabra en el Wikcionario del idioma que se le diga.

    Se usa la API de MediaWiki, que devuelve el artículo ya en texto plano: no
    hay que interpretar ninguna página, y por eso esta fuente es la que menos
    se rompe con el tiempo.

    :param idioma_wiki: Código del Wikcionario: ``es``, ``en``, ``ca``, ``fr``...
    """
    palabra = limpiar(palabra)
    entrada = Entrada(palabra=palabra, fuente=WIKCIONARIO)
    url = ("https://%s.wiktionary.org/w/api.php?action=query&prop=extracts"
           "&explaintext=1&redirects=1&format=json&formatversion=2&titles=%s"
           % (idioma_wiki, urllib.parse.quote(palabra)))
    try:
        datos = json.loads(_descargar(url, espera))
    except Exception as error:
        log.info("No se ha podido consultar el Wikcionario: %s", error)
        entrada.error = _("No se ha podido consultar el Wikcionario: %s") % error
        return entrada

    paginas = (datos.get("query") or {}).get("pages") or []
    if not paginas or paginas[0].get("missing"):
        entrada.error = _("«%s» no está en el Wikcionario.") % palabra
        return entrada
    entrada.texto = _limpiar_wiki(str(paginas[0].get("extract") or ""))
    if not entrada.texto:
        entrada.error = _("«%s» está en el Wikcionario, pero sin definición.") % palabra
    return entrada


def _limpiar_wiki(texto: str) -> str:
    """Deja el artículo del Wikcionario en algo cómodo de oír.

    Los encabezados vienen como ``=== Sustantivo ===``; los signos de igual, al
    leerlos, suenan uno a uno y no aportan nada.  Se quitan dejando el título, y
    se recortan las secciones que solo interesan al que edita el wiki
    (traducciones, referencias, información adicional), que en una palabra común
    ocupan más que la propia definición.
    """
    lineas: list[str] = []
    saltando = False
    ignorar = ("traducciones", "referencias", "información adicional",
               "véase también", "notas", "anagramas")
    for linea in texto.splitlines():
        limpia = linea.strip()
        if limpia.startswith("="):
            titulo = limpia.strip("= ").strip()
            saltando = titulo.lower() in ignorar
            if not saltando and titulo:
                lineas.append("")
                lineas.append(titulo + ":")
            continue
        if saltando or not limpia:
            continue
        lineas.append(limpia)
    return "\n".join(lineas).strip()


# ---------------------------------------------------------------------------
# La inteligencia artificial
# ---------------------------------------------------------------------------

#: Instrucción que se le da a la IA.  Pide español, sin markdown y con el
#: contexto delante, que es lo que hace falta para que la respuesta se pueda
#: leer de oído tal cual sale.
PREGUNTA_IA = _(
    "Define la palabra «%(palabra)s» tal y como se usa en este fragmento de un "
    "documento:\n\n«%(contexto)s»\n\n"
    "Responde en español y en texto llano, sin markdown, sin asteriscos y sin "
    "encabezados. Empieza por la categoría gramatical entre paréntesis y sigue "
    "con la definición. Si la palabra tiene varios significados, indica primero "
    "el que corresponde a este fragmento y añade los demás numerados. Si es un "
    "nombre propio, un tecnicismo o una locución, dilo y explícalo igual. "
    "No repitas la pregunta ni añadas comentarios sobre tu respuesta.")

#: La misma instrucción cuando no hay contexto (se consultó a mano).
PREGUNTA_IA_SIN_CONTEXTO = _(
    "Define la palabra «%(palabra)s».\n\n"
    "Responde en español y en texto llano, sin markdown, sin asteriscos y sin "
    "encabezados. Empieza por la categoría gramatical entre paréntesis y sigue "
    "con la definición, numerando los distintos significados si hay varios. "
    "No repitas la pregunta ni añadas comentarios sobre tu respuesta.")


def consultar_ia(palabra: str, servicio, contexto: str = "") -> Entrada:
    """Le pide la definición a la inteligencia artificial configurada.

    :param servicio: El :class:`nucleo.ia.servicio.Servicio` de la aplicación.
    :param contexto: Frase del documento en la que aparece la palabra.  Es lo
                     que distingue esta fuente de las otras dos: con ella la IA
                     define la acepción que toca y no la primera del
                     diccionario.
    """
    palabra = limpiar(palabra)
    entrada = Entrada(palabra=palabra, fuente=IA)
    contexto = " ".join((contexto or "").split())
    if contexto:
        pregunta = PREGUNTA_IA % {"palabra": palabra, "contexto": contexto}
    else:
        pregunta = PREGUNTA_IA_SIN_CONTEXTO % {"palabra": palabra}
    try:
        entrada.texto = servicio.preguntar(pregunta).strip()
    except Exception as error:
        log.info("La IA no ha podido definir «%s»: %s", palabra, error)
        entrada.error = str(error)
        return entrada
    if not entrada.texto:
        entrada.error = _("La inteligencia artificial no ha devuelto ninguna definición.")
    return entrada


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

def definir(palabra: str, fuente: str, servicio=None, contexto: str = "",
            idioma_wiki: str = "es", espera: int = ESPERA) -> Entrada:
    """Consulta una palabra en la fuente indicada.

    Bloquea hasta que el servicio contesta —son peticiones de red—, así que hay
    que llamarla desde un hilo que no sea el de la interfaz.
    """
    palabra = limpiar(palabra)
    if not es_valida(palabra):
        return Entrada(palabra=palabra, fuente=fuente,
                       error=_("Eso no parece una palabra que se pueda buscar."))
    if fuente == WIKCIONARIO:
        return consultar_wikcionario(palabra, idioma_wiki, espera)
    if fuente == IA:
        if servicio is None:
            return Entrada(palabra=palabra, fuente=IA,
                           error=_("La inteligencia artificial no está configurada."))
        return consultar_ia(palabra, servicio, contexto)
    return consultar_rae(palabra, espera)
