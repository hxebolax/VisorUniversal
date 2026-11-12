# -*- coding: utf-8 -*-
"""Motor de traducción automática para los catálogos de idioma.

Traducir a mano los mil setecientos textos del programa es un trabajo de
semanas, y hacerlo pegándolos uno a uno en un traductor de la web es peor:
además de eterno, se rompen por el camino las cosas que un ``.po`` no puede
perder.  Este módulo traduce respetando esas cosas.

Qué se protege, y por qué
-------------------------

* **Las variables** (``%s``, ``%d``, ``%(nombre)s``, ``{ruta}``).  Si un
  traductor las toca —y las toca: convierte ``%s`` en ``% s``— el programa
  revienta al formatear el texto, y encima en el idioma de otro.
* **Los saltos de línea y los tabuladores.**  Muchos textos de ayuda están
  partidos en renglones a propósito, para que quepan en su cuadro.
* **Las combinaciones de teclas** (``Control+Alt+O``, ``F7``, ``Mayús+F6``).
  Son lo que el usuario tiene que pulsar: traducir «Control» por «Controllo»
  deja una instrucción que no lleva a ninguna parte.
* **Las rutas y las extensiones** (``data\\config``, ``.epub``).
* **Los aceleradores de menú** (``&Archivo``).  Estos no se protegen: se
  **reubican**, porque el subrayado tiene que caer en una letra de la palabra
  ya traducida.  Mantener la letra original sería subrayar una letra que en
  «Apri» no está.

Cómo se traduce
---------------

Con la API pública de Google Translate, la misma que usa el traductor de la
página web, por HTTPS y sin clave.  Se prueban cuatro direcciones distintas
porque cada una tiene su propio límite de peticiones: cuando una responde
«demasiadas peticiones» se pasa a la siguiente en lugar de abandonar.

Y se manda **mucho de una vez**.  Una petición por texto son cuatro segundos
por entrada y casi seis horas para los tres idiomas; agrupando cuarenta
renglones en cada petición son tres minutos por idioma.  La diferencia entre
una herramienta que se usa y una que se deja a medias.

**Es automático, no es un traductor humano.**  Sirve para tener el programa
utilizable en un idioma en una tarde; lo que salga hay que repasarlo, y para
eso está el editor (:mod:`herramientas.editor_idiomas`), que permite corregir
entrada por entrada.
"""

from __future__ import annotations

import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

#: Direcciones que se prueban, en orden.  La primera es la del diccionario de
#: Chrome: responde con menos límite que las demás y devuelve el resultado en
#: un formato más simple.  Las otras tres son las del traductor de la web.
DIRECCIONES = (
    "https://clients5.google.com/translate_a/t?client=dict-chrome-ex"
    "&sl={origen}&tl={destino}&q={texto}",
    "https://translate.googleapis.com/translate_a/single?client=gtx"
    "&sl={origen}&tl={destino}&dt=t&q={texto}&dj=1",
    "https://translate.google.com/translate_a/single?client=gtx"
    "&sl={origen}&tl={destino}&dt=t&q={texto}&dj=1",
    "https://translate.google.es/translate_a/single?client=gtx"
    "&sl={origen}&tl={destino}&dt=t&q={texto}&dj=1",
)

#: Cuántas veces se reintenta un texto antes de darlo por perdido, y cuánto se
#: espera entre intentos.  La espera crece a propósito: cuando el servidor
#: contesta «demasiadas peticiones», insistir al momento solo confirma que sí.
INTENTOS = 4
ESPERA_BASE = 1.5

#: Espera entre dos peticiones seguidas.  Sin ella, unos cientos de peticiones
#: seguidas se ganan un bloqueo temporal.
ESPERA_ENTRE_LOTES = 0.2

#: Cuántos renglones como mucho van en una misma petición, y cuánto puede
#: ocupar la dirección resultante.  El tope de tamaño manda sobre el de
#: cantidad: una dirección demasiado larga la rechaza el servidor sin más
#: explicación.
MAXIMO_POR_LOTE = 40
MAXIMO_URL = 3500

#: Cuántas entradas del catálogo se traducen antes de guardarlo en el disco.
TANDA = 20

#: Tiempo máximo que se espera una respuesta.
ESPERA_RED = 20

#: Idiomas a los que se ofrece traducir, con su nombre en español.  Son los
#: que Google admite y que tienen sentido para este programa; añadir uno es
#: escribir su línea.
IDIOMAS = {
    "en": "Inglés", "fr": "Francés", "it": "Italiano", "pt": "Portugués",
    "de": "Alemán", "ca": "Catalán", "gl": "Gallego", "eu": "Euskera",
    "nl": "Neerlandés", "pl": "Polaco", "ro": "Rumano", "sv": "Sueco",
    "da": "Danés", "fi": "Finés", "no": "Noruego", "cs": "Checo",
    "el": "Griego", "hu": "Húngaro", "tr": "Turco", "ru": "Ruso",
    "uk": "Ucraniano", "ar": "Árabe", "he": "Hebreo", "hi": "Hindi",
    "ja": "Japonés", "ko": "Coreano", "zh-CN": "Chino simplificado",
}

#: Lo que no se traduce nunca.  Se saca del texto antes de mandarlo y se vuelve
#: a poner después, para que el traductor no pueda tocarlo.
_INTOCABLE = re.compile(
    r"(%\([^)]+\)[sdifgxXoerc%])"          # %(nombre)s
    r"|(%[-+ #0-9.]*[sdifgxXoerc%])"       # %s, %d, %.1f, %%
    r"|(\{[^{}]*\})"                       # {variable}
    r"|(\\[nrt])"                          # saltos y tabuladores escritos
    r"|((?:Control|Ctrl|Alt|May[úu]s|Shift|Cmd|Win)"
    r"(?:\+(?:[A-Za-z0-9]|F\d{1,2}|Espacio|Intro|Inicio|Fin|Tabulador|"
    r"Izquierda|Derecha|Arriba|Abajo|Re\s?Pág|Av\s?Pág|Escape|Suprimir))+)"
    r"|(\bF\d{1,2}\b)"                     # F1, F12
    r"|([A-Za-z_][\w-]*[\\/][\w\\/.-]+)"   # data\config, data/idiomas
    r"|(\b\w+\.(?:epub|pdf|docx?|odt|txt|md|html?|json|py|mo|po|pot|zip|mp3|"
    r"ncx|opf|fb2|rtf|log|nfo|bat|exe)\b)"
)

#: Acelerador de menú: el ampersand y la letra que subraya.
_ACELERADOR = re.compile(r"&([^\s&])")

#: Por dónde se puede partir un texto demasiado largo para una sola petición.
_CORTE = re.compile(r"[.,;:!?]")

#: Tamaño máximo que se manda de una vez.
_MAXIMO = 1800

#: Con qué se sustituye lo intocable mientras el texto viaja.  La forma
#: importa más de lo que parece: probando salió que con «XQV0VQX» el
#: traductor se comía la frase entera alrededor del token, y con este no.
#: Por eso, además de elegirlo con cuidado, se **comprueba** después que
#: siga estando: es la única garantía de que no se pierde una variable.
_SENAL = "ZZQ%dQZZ"


class ErrorTraduccion(Exception):
    """No se ha podido traducir: sin conexión, o el servidor no contesta."""


# ---------------------------------------------------------------------------
# Aceleradores de menú
# ---------------------------------------------------------------------------

def _quitar_aceleradores(texto: str) -> tuple[str, list[tuple[int, str]]]:
    """Saca los ``&`` del texto y anota en qué palabra estaba cada uno.

    :return: ``(texto sin ampersands, [(número de palabra, letra)])``.
    """
    encontrados: list[tuple[int, str]] = []
    for numero, palabra in enumerate(texto.split()):
        for hallazgo in _ACELERADOR.finditer(palabra):
            encontrados.append((numero, hallazgo.group(1)))
    return _ACELERADOR.sub(r"\1", texto), encontrados


def _poner_aceleradores(texto: str, encontrados: list[tuple[int, str]]) -> str:
    """Vuelve a poner los ``&`` en el texto traducido.

    Se busca, por este orden: la misma letra dentro de la palabra que ocupa esa
    posición; su primera letra; y si esa posición ya no existe —las lenguas no
    tienen el mismo número de palabras—, la última palabra.  Nunca se subraya
    dos veces la misma, porque en un menú dos entradas con la misma letra se
    estorban.
    """
    if not encontrados:
        return texto
    palabras = _ACELERADOR.sub(r"\1", texto).split()
    if not palabras:
        return texto
    # Solo valen de destino las palabras que tienen alguna letra: en francés,
    # «Color de la &letra:» se convierte en «Couleur des lettres :», donde la
    # última «palabra» es un dos puntos suelto y ahí no se puede subrayar nada.
    con_letras = [numero for numero, palabra in enumerate(palabras)
                  if any(caracter.isalpha() for caracter in palabra)]
    if not con_letras:
        return texto
    usadas: set[int] = set()
    for numero, letra in encontrados:
        objetivo = min(numero, len(palabras) - 1)
        if objetivo not in con_letras or objetivo in usadas:
            # Se busca la palabra con letras más cercana que quede libre.
            libres = [otro for otro in con_letras if otro not in usadas]
            if not libres:
                continue
            objetivo = min(libres, key=lambda otro: (abs(otro - numero), otro))
        palabra = palabras[objetivo]
        posicion = next((indice for indice, letra_actual in enumerate(palabra)
                         if letra_actual.lower() == letra.lower() and letra_actual.isalpha()), -1)
        if posicion < 0:
            posicion = next((indice for indice, letra_actual in enumerate(palabra)
                             if letra_actual.isalpha()), -1)
        if posicion < 0:
            continue
        palabras[objetivo] = palabra[:posicion] + "&" + palabra[posicion:]
        usadas.add(objetivo)
    return " ".join(palabras)


# ---------------------------------------------------------------------------
# Petición al servidor
# ---------------------------------------------------------------------------

def _contexto_ssl():
    """Contexto de HTTPS que no falla por un certificado raro del camino."""
    contexto = ssl.create_default_context()
    contexto.check_hostname = False
    contexto.verify_mode = ssl.CERT_NONE
    return contexto


def _pedir_lote(renglones: list[str], origen: str, destino: str) -> list[str]:
    """Manda varios renglones en una sola petición y devuelve sus traducciones.

    La dirección del diccionario de Chrome admite varios ``q``, y contesta con
    una lista en el mismo orden.  Es lo que permite traducir el programa entero
    en minutos en lugar de en horas.  Las otras direcciones no lo admiten, así
    que solo se usan de reserva y de una en una.

    :raises ErrorTraduccion: Si ninguna dirección contesta algo utilizable.
    """
    if not renglones:
        return []
    consulta = "&".join("q=" + urllib.parse.quote(renglon) for renglon in renglones)
    ultimo_error = None
    for intento in range(INTENTOS):
        direccion = DIRECCIONES[0].split("&q=")[0].format(
            origen=origen, destino=destino, texto="") + "&" + consulta
        peticion = urllib.request.Request(
            direccion, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        try:
            with urllib.request.urlopen(peticion, timeout=ESPERA_RED,
                                        context=_contexto_ssl()) as respuesta:
                datos = json.loads(respuesta.read().decode("utf-8", "replace"))
        except Exception as error:                      # red, tiempo agotado, 429
            ultimo_error = error
            time.sleep(ESPERA_BASE * (intento + 1))
            continue
        if isinstance(datos, list) and len(datos) == len(renglones) \
                and all(isinstance(pieza, str) for pieza in datos):
            return datos
        if len(renglones) == 1 and isinstance(datos, str):
            return [datos]
        ultimo_error = ValueError("la respuesta no trae tantos textos como se pidieron")
        time.sleep(ESPERA_BASE * (intento + 1))
    # Si el lote falla se prueba renglón a renglón: puede que uno solo sea el
    # que atraganta la petición, y perder cuarenta por culpa de uno sería tonto.
    if len(renglones) > 1:
        return [_pedir(renglon, origen, destino) for renglon in renglones]
    raise ErrorTraduccion(str(ultimo_error) if ultimo_error else "sin respuesta")


def _pedir(texto: str, origen: str, destino: str) -> str:
    """Manda un solo texto, probando todas las direcciones por turnos."""
    codificado = urllib.parse.quote(texto)
    ultimo_error = None
    for intento in range(INTENTOS):
        for plantilla in DIRECCIONES:
            direccion = plantilla.format(origen=origen, destino=destino, texto=codificado)
            peticion = urllib.request.Request(
                direccion, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            try:
                with urllib.request.urlopen(peticion, timeout=ESPERA_RED,
                                            context=_contexto_ssl()) as respuesta:
                    crudo = respuesta.read().decode("utf-8", "replace")
            except Exception as error:                  # red, tiempo agotado, 429
                ultimo_error = error
                continue
            traducido = _interpretar(crudo)
            if traducido is not None:
                return traducido
            ultimo_error = ValueError("respuesta que no se entiende")
        time.sleep(ESPERA_BASE * (intento + 1))
    raise ErrorTraduccion(str(ultimo_error) if ultimo_error else "sin respuesta")


def _interpretar(crudo: str) -> str | None:
    """Saca el texto traducido de la respuesta, sea del formato que sea."""
    try:
        datos = json.loads(crudo)
    except ValueError:
        return None
    if isinstance(datos, list):
        # El del diccionario de Chrome: ["Apri documento"].
        piezas = [pieza for pieza in datos if isinstance(pieza, str)]
        return "".join(piezas) if piezas else None
    if isinstance(datos, dict):
        frases = datos.get("sentences")
        if isinstance(frases, list):
            return "".join(str(frase.get("trans", "")) for frase in frases
                           if isinstance(frase, dict))
    return None


def _preparar(texto: str) -> tuple[list[str], dict, list]:
    """Deja un texto listo para mandarlo: sin aceleradores y sin lo intocable.

    :return: ``(renglones, lo apartado, los aceleradores)``.
    """
    sin_aceleradores, aceleradores = _quitar_aceleradores(texto)
    guardado: dict[str, str] = {}

    def apartar(hallazgo):
        clave = _SENAL % len(guardado)
        guardado[clave] = hallazgo.group(0)
        return clave

    protegido = _INTOCABLE.sub(apartar, sin_aceleradores)
    return protegido.split("\n"), guardado, aceleradores


def _rehacer(renglones: list[str], guardado: dict,
             aceleradores: list) -> tuple[str, bool]:
    """Vuelve a montar el texto traducido con todo lo suyo en su sitio.

    :return: ``(texto, si está entero)``.  Lo segundo es lo que evita guardar
             una traducción a la que le falta una variable: un ``%d`` perdido
             no se ve al leer el catálogo y revienta el programa el día que a
             alguien le toque ese mensaje, en un idioma que quien lo escribió
             probablemente no habla.
    """
    resultado = "\n".join(renglones)
    entero = True
    for clave, original in guardado.items():
        if not re.search(re.escape(clave), resultado, flags=re.IGNORECASE):
            entero = False
            continue
        resultado = re.sub(re.escape(clave), original.replace("\\", "\\\\"),
                           resultado, flags=re.IGNORECASE)
    return _poner_aceleradores(resultado, aceleradores), entero


def traducir_varios(textos: list[str], destino: str, origen: str = "es",
                    fallos: set | None = None) -> list[str]:
    """Traduce una lista de textos agrupándolos en pocas peticiones.

    Cada texto se parte en renglones —los saltos de línea de los textos de
    ayuda están puestos a mano y hay que respetarlos—, todos los renglones de
    todos los textos van a una misma cola, y esa cola se manda en lotes.
    Después cada texto recupera sus renglones, sus variables y sus
    aceleradores.

    :param fallos: Conjunto donde se apuntan los números de los textos que no
                   se han podido traducir.  Hace falta porque un texto que
                   vuelve igual que el original puede ser las dos cosas: un
                   fallo de red, o una palabra que en el otro idioma se escribe
                   igual —«Beige», «PDF», «Control+F»—.  Sin distinguirlas, la
                   mitad del catálogo se quedaría marcada como pendiente para
                   siempre.
    """
    preparados = [_preparar(texto) if texto and texto.strip() else (None, None, None)
                  for texto in textos]

    # La cola: cada renglón con su sitio de origen, para devolverlo después.
    cola: list[str] = []
    procedencia: list[tuple[int, int]] = []
    for numero, (renglones, _guardado, _aceleradores) in enumerate(preparados):
        if renglones is None:
            continue
        for indice, renglon in enumerate(renglones):
            if renglon.strip():
                cola.append(renglon)
                procedencia.append((numero, indice))

    traducidos: dict[tuple[int, int], str] = {}
    lote: list[str] = []
    sitios: list[tuple[int, int]] = []
    tamano = 0

    fallidos: set[int] = set()

    def vaciar():
        nonlocal lote, sitios, tamano
        if not lote:
            return
        try:
            respuesta = _pedir_lote(lote, origen, destino)
        except ErrorTraduccion:
            respuesta = lote                      # se deja el original
            fallidos.update(numero for numero, _indice in sitios)
        for sitio, texto in zip(sitios, respuesta):
            traducidos[sitio] = texto
        lote, sitios, tamano = [], [], 0
        time.sleep(ESPERA_ENTRE_LOTES)

    for renglon, sitio in zip(cola, procedencia):
        largo = len(urllib.parse.quote(renglon)) + 3
        if lote and (len(lote) >= MAXIMO_POR_LOTE or tamano + largo > MAXIMO_URL):
            vaciar()
        lote.append(renglon)
        sitios.append(sitio)
        tamano += largo
    vaciar()

    salida: list[str] = []
    for numero, (renglones, guardado, aceleradores) in enumerate(preparados):
        if renglones is None:
            salida.append(textos[numero])
            continue
        rehechos = [traducidos.get((numero, indice), renglon)
                    for indice, renglon in enumerate(renglones)]
        texto, entero = _rehacer(rehechos, guardado, aceleradores)
        if not entero:
            # Al traductor se le ha perdido una variable por el camino.  Se
            # devuelve el original sin tocar y se marca como fallo: más vale
            # una entrada sin traducir que una que rompe el programa.
            fallidos.add(numero)
            texto = textos[numero]
        salida.append(texto)
    if fallos is not None:
        fallos.update(fallidos)
    return salida


def _partir(texto: str) -> list[str]:
    """Parte un texto largo por sus signos de puntuación, para que quepa."""
    if len(texto) <= _MAXIMO:
        return [texto]
    trozos: list[str] = []
    desde = 0
    corte = 0
    for hallazgo in _CORTE.finditer(texto):
        if hallazgo.start() - desde + 1 < _MAXIMO:
            corte = hallazgo.start()
        else:
            trozos.append(texto[desde:corte + 1])
            desde = corte + 1
            corte = hallazgo.start()
    trozos.append(texto[desde:])
    return [trozo for trozo in trozos if trozo]


# ---------------------------------------------------------------------------
# Traducción de un texto completo
# ---------------------------------------------------------------------------

def traducir(texto: str, destino: str, origen: str = "es") -> str:
    """Traduce un texto respetando todo lo que un ``.po`` no puede perder.

    :param texto: El original, tal como está en el catálogo.
    :param destino: Código del idioma al que se traduce (``it``, ``fr``...).
    :param origen: Código del idioma del original.
    :raises ErrorTraduccion: Si el servidor no contesta después de reintentar.
    """
    if not texto or not texto.strip():
        return texto

    return traducir_varios([texto], destino, origen)[0]


def hay_conexion(destino: str = "en") -> bool:
    """Comprueba de un tirón si el servicio contesta.

    Es lo que el editor pregunta antes de lanzar mil setecientas peticiones:
    más vale decir «no hay conexión» que dejar una barra de progreso avanzando
    hacia mil setecientos errores.
    """
    try:
        return bool(traducir("Hola", destino))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Traducción de un catálogo entero, desde la línea de órdenes
# ---------------------------------------------------------------------------

def traducir_catalogo(codigo: str, avisar=None, parar=None) -> tuple[int, int]:
    """Traduce lo que falte del catálogo de un idioma y lo va guardando.

    **Se guarda cada pocas entradas y no al final**: mil setecientas peticiones
    son media hora larga, y si se corta la conexión a la mitad lo traducido
    hasta ese momento tiene que estar en el disco.  Volver a lanzarlo continúa
    donde se quedó, porque solo se traduce lo que está vacío.

    :param avisar: Función ``(hechas, total, original, traduccion)`` que se
                   llama en cada entrada, para dibujar el progreso.
    :param parar: Función que devuelve ``True`` cuando hay que dejarlo.
    :return: ``(cuántas se han traducido, cuántas han fallado)``.
    """
    import textos

    originales, originales_plural = textos.recoger()
    simples, plurales = textos.cargar_po(codigo)
    pendientes = [texto for texto in sorted(originales)
                  if texto.strip() and not simples.get(texto)]
    pendientes_plural = [par for par in sorted(originales_plural)
                         if not plurales.get(par[0], ("", []))[1]]
    total = len(pendientes) + len(pendientes_plural)
    hechas = fallidas = 0

    def guardar():
        textos.escribir_po(codigo, simples, plurales)

    # Se trabaja de veinte en veinte: es lo que permite guardar a menudo —una
    # conexión que se corta a la mitad no puede tirar media hora de trabajo— sin
    # renunciar a mandar varios textos por petición.
    hechas_hasta_ahora = 0
    for desde in range(0, len(pendientes), TANDA):
        if parar is not None and parar():
            break
        tanda = pendientes[desde:desde + TANDA]
        fallos: set[int] = set()
        resultado = traducir_varios(tanda, codigo, fallos=fallos)
        for numero, (original, traduccion) in enumerate(zip(tanda, resultado)):
            if numero in fallos or not traduccion:
                fallidas += 1
                continue
            # Aunque venga igual que el original se guarda: en italiano
            # «Beige» es «Beige», y dejarlo vacío lo marcaría como pendiente
            # cada vez que alguien abra el editor.
            simples[original] = traduccion
            hechas += 1
            hechas_hasta_ahora += 1
            if avisar is not None:
                avisar(hechas_hasta_ahora, total, original, traduccion)
        guardar()

    for singular, plural in pendientes_plural:
        if parar is not None and parar():
            break
        formas = traducir_varios([singular, plural], codigo)
        if any(formas):
            plurales[singular] = (plural, formas)
            hechas += 1
        else:
            fallidas += 1
        hechas_hasta_ahora += 1
        if avisar is not None:
            avisar(hechas_hasta_ahora, total, singular, formas[0] if formas else "")

    guardar()
    return hechas, fallidas


def _principal(argumentos: list[str]) -> int:
    """Traduce por lotes los idiomas que se le pidan."""
    import textos

    if not argumentos:
        print("Uso: python herramientas/traductor.py it fr pt")
        print("Traduce lo que falte del catálogo de cada idioma.")
        print("Idiomas: %s" % ", ".join(sorted(IDIOMAS)))
        return 1
    for codigo in argumentos:
        if codigo not in IDIOMAS:
            print("Idioma desconocido: %s" % codigo)
            return 1
        print("=== %s (%s) ===" % (IDIOMAS[codigo], codigo), flush=True)

        def contar(hechas, total, original, traduccion):
            if hechas % 50 == 0 or hechas == total:
                print("   %d de %d" % (hechas, total), flush=True)

        hechas, fallidas = traducir_catalogo(codigo, avisar=contar)
        simples, _plurales = textos.cargar_po(codigo)
        originales, _op = textos.recoger()
        print("   traducidas %d, fallidas %d, catálogo al %d %%"
              % (hechas, fallidas, round(100 * len(simples) / max(len(originales), 1))),
              flush=True)
    textos.compilar()
    return 0


if __name__ == "__main__":
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.exit(_principal([a for a in sys.argv[1:] if not a.startswith("-")]))
