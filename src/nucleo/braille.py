# -*- coding: utf-8 -*-
"""Transcripción a braille y escritura de archivos BRF.

Sirve para lo que ningún lector de pantalla puede hacer por sí solo: **sacar
el libro del ordenador**.  Quien lee en braille tiene su línea braille
conectada al lector y lee lo que este le manda, sí, pero para llevarse un
documento a una impresora braille, a un anotador o a otro equipo hace falta un
archivo, y el archivo es un BRF.

Qué se transcribe
-----------------

**Braille de grado 1**, es decir, sin abreviar: cada letra es su signo.  Es lo
que corresponde a un programa que transcribe texto cualquiera —apuntes,
informes, un PDF recién reconocido— porque la estenografía tiene reglas de
palabra que dependen del idioma y aplicarlas mal sería peor que no aplicarlas.

Se transcriben las letras del español con sus tildes y su eñe, los números con
su signo delante, las mayúsculas con el suyo y los signos de puntuación
corrientes.  Lo que no esté en la tabla se deja pasar en claro en vez de
perderse, que es lo que menos daño hace.

Cómo se guarda
--------------

Un BRF es texto de toda la vida: cada celda braille se escribe con el carácter
ASCII que le corresponde según la tabla que usan las impresoras braille desde
hace cuarenta años.  Las líneas se cortan a lo ancho de la página y las páginas
se separan con un salto de página, que es lo que la impresora entiende.

También se puede pedir el braille en **Unicode** (⠁⠃⠉…), que es lo que hace
falta para leerlo en pantalla o pegarlo en un correo.
"""

from __future__ import annotations

from .idioma import _

#: Tabla de braille ASCII: qué carácter escribe cada celda.  El índice es el
#: patrón de puntos —el punto 1 vale 1, el 2 vale 2, el 3 vale 4, el 4 vale 8,
#: el 5 vale 16 y el 6 vale 32—, y esta cadena es la correspondencia que usan
#: las impresoras braille y los archivos BRF de todo el mundo.
ASCII_BRAILLE = (" A1B'K2L@CIF/MSP\"E3H9O6R^DJG>NTQ,*5<-U8V.%[$+X!&;:4\\0Z7(_?W]#Y)=")

#: Primer carácter de los signos braille de Unicode.  Sumándole el patrón de
#: puntos se obtiene el signo, que es como está pensado el bloque.
UNICODE_BRAILLE = 0x2800

#: Signo de número: lo que se pone delante de una cifra para que sus letras se
#: lean como dígitos.  Puntos 3, 4, 5 y 6.
SIGNO_NUMERO = 0b111100

#: Signo de mayúscula, que va delante de cada letra que lo sea.  Puntos 4 y 6.
SIGNO_MAYUSCULA = 0b101000


def _puntos(*numeros: int) -> int:
    """Convierte una lista de puntos —«1, 2, 4»— en su patrón."""
    patron = 0
    for numero in numeros:
        patron |= 1 << (numero - 1)
    return patron


#: Braille español de grado 1.  Las veintiséis letras del alfabeto latino son
#: las mismas en todos los braille del mundo; lo propio del español son la eñe,
#: las vocales con tilde y la diéresis.
LETRAS = {
    "a": _puntos(1), "b": _puntos(1, 2), "c": _puntos(1, 4), "d": _puntos(1, 4, 5),
    "e": _puntos(1, 5), "f": _puntos(1, 2, 4), "g": _puntos(1, 2, 4, 5),
    "h": _puntos(1, 2, 5), "i": _puntos(2, 4), "j": _puntos(2, 4, 5),
    "k": _puntos(1, 3), "l": _puntos(1, 2, 3), "m": _puntos(1, 3, 4),
    "n": _puntos(1, 3, 4, 5), "o": _puntos(1, 3, 5), "p": _puntos(1, 2, 3, 4),
    "q": _puntos(1, 2, 3, 4, 5), "r": _puntos(1, 2, 3, 5), "s": _puntos(2, 3, 4),
    "t": _puntos(2, 3, 4, 5), "u": _puntos(1, 3, 6), "v": _puntos(1, 2, 3, 6),
    "w": _puntos(2, 4, 5, 6), "x": _puntos(1, 3, 4, 6), "y": _puntos(1, 3, 4, 5, 6),
    "z": _puntos(1, 3, 5, 6),
    "ñ": _puntos(1, 2, 4, 5, 6),
    "á": _puntos(1, 2, 3, 5, 6), "é": _puntos(2, 3, 4, 6), "í": _puntos(3, 4),
    "ó": _puntos(3, 4, 6), "ú": _puntos(2, 3, 4, 5, 6), "ü": _puntos(1, 2, 5, 6),
}

#: Los diez dígitos se escriben con las diez primeras letras, precedidas del
#: signo de número.
DIGITOS = {
    "1": LETRAS["a"], "2": LETRAS["b"], "3": LETRAS["c"], "4": LETRAS["d"],
    "5": LETRAS["e"], "6": LETRAS["f"], "7": LETRAS["g"], "8": LETRAS["h"],
    "9": LETRAS["i"], "0": LETRAS["j"],
}

#: Signos de puntuación del braille español.
PUNTUACION = {
    ",": _puntos(2), ";": _puntos(2, 3), ":": _puntos(2, 5), ".": _puntos(3),
    "?": _puntos(2, 6), "¿": _puntos(2, 6), "!": _puntos(2, 3, 5),
    "¡": _puntos(2, 3, 5), "(": _puntos(1, 2, 6), ")": _puntos(3, 4, 5),
    "-": _puntos(3, 6), "—": _puntos(3, 6), "–": _puntos(3, 6),
    '"': _puntos(2, 3, 6), "«": _puntos(2, 3, 6), "»": _puntos(3, 5, 6),
    "*": _puntos(3, 5), "'": _puntos(3), "/": _puntos(3, 4),
    "…": _puntos(3), " ": 0,
}

#: Ancho y alto de una página braille corriente, en celdas y en líneas.  Es lo
#: que cabe en una hoja A4 con la interlínea normal, y lo que esperan las
#: impresoras si no se les dice otra cosa.
ANCHO = 40
ALTO = 25


def a_celdas(texto: str) -> list[int]:
    """Traduce un texto a la lista de celdas braille que le corresponde.

    Lo que no está en la tabla no se pierde: se deja el propio carácter, que
    en un BRF se verá raro pero permite saber qué había ahí.  Perder texto
    callando es lo único que no se puede hacer.
    """
    celdas: list[int] = []
    en_numero = False
    for letra in texto:
        if letra in DIGITOS:
            if not en_numero:
                celdas.append(SIGNO_NUMERO)
                en_numero = True
            celdas.append(DIGITOS[letra])
            continue
        # El número sigue vivo mientras siga habiendo cifras o los signos que
        # van dentro de un número; con cualquier otra cosa se acaba.
        if en_numero and letra not in (",", "."):
            en_numero = False
        minuscula = letra.lower()
        if minuscula in LETRAS:
            if letra != minuscula:
                celdas.append(SIGNO_MAYUSCULA)
            celdas.append(LETRAS[minuscula])
            continue
        if letra in PUNTUACION:
            celdas.append(PUNTUACION[letra])
            continue
        if letra == "\n":
            celdas.append(-1)                # marca de fin de línea
            en_numero = False
            continue
        if letra == "\t":
            celdas.extend([0, 0])
            continue
        celdas.append(-2 - ord(letra) if ord(letra) < 0x110000 else 0)
    return celdas


def a_unicode(texto: str) -> str:
    """Devuelve el texto en signos braille de Unicode, para leerlo en pantalla."""
    salida = []
    for celda in a_celdas(texto):
        if celda == -1:
            salida.append("\n")
        elif celda < -1:
            salida.append(chr(-(celda + 2)))
        else:
            salida.append(chr(UNICODE_BRAILLE + celda))
    return "".join(salida)


def _caracter_brf(celda: int) -> str:
    """El carácter ASCII con el que se escribe una celda en un BRF."""
    if celda < -1:
        return chr(-(celda + 2))
    return ASCII_BRAILLE[celda] if 0 <= celda < len(ASCII_BRAILLE) else " "


def lineas_de_bloques(bloques, ancho: int = ANCHO) -> list[str]:
    """Compone en renglones de braille ASCII una mezcla de texto y braille.

    Cada bloque es ``(ya_en_braille, contenido)``.  Los que vienen ya en
    braille se dejan tal cual —son las fórmulas transcritas con el Código
    Matemático Unificado, que no se pueden volver a traducir— y los demás se
    traducen como siempre.

    Es lo que permite que un libro de matemáticas salga con su texto en
    braille literario y sus fórmulas en braille matemático, que es como se
    escribe de verdad.
    """
    lineas: list[str] = []
    for ya_en_braille, contenido in bloques:
        crudas = [contenido] if ya_en_braille else _lineas_de(contenido)
        for cruda in crudas:
            lineas.extend(_cortar(cruda, ancho) or [""])
    return lineas


def tabla_a_lineas(filas, ancho: int = ANCHO, traducir=None) -> list[str]:
    """Compone una tabla en braille, en columnas alineadas.

    Una tabla escrita como texto seguido deja de ser una tabla: no hay forma de
    saber, con el dedo en un número, de qué columna es. En braille se resuelve
    **alineando las columnas**, que es lo que permite recorrer una hoja hacia
    abajo siguiendo la misma.

    Y cuando no cabe —que pasa a menudo, porque el renglón tiene cuarenta celdas
    y una tabla de seis columnas no entra— se escribe **linealizada**: una fila
    por bloque y, dentro, un renglón por celda con el nombre de su columna
    delante. Ocupa más papel, pero ningún dato se queda sin decir de qué es, que
    es lo único que no se puede perder.

    La primera fila se toma como encabezado **solo si lo parece** (véase
    :func:`_hay_encabezado`), y entonces se separa del resto con una línea de
    guiones.  Darla por encabezado siempre saldría caro: en una tabla de datos
    sin títulos, la primera fila desaparecería del texto linealizado, y una fila
    perdida en silencio es exactamente lo que no puede pasar.

    :param traducir: Si se da, se aplica al **texto de cada celda antes de
        medirla**.  Hace falta para el braille contraído: ahí «Ventas» ocupa
        cinco celdas y no seis, así que alinear primero y contraer después
        descuadraría todas las columnas.
    """
    paso = traducir or (lambda texto: texto)
    crudas = [[" ".join((celda or "").split()) for celda in fila]
              for fila in filas if fila]
    if not crudas:
        return []
    columnas = max(len(fila) for fila in crudas)
    for fila in crudas:
        fila.extend([""] * (columnas - len(fila)))
    # Si hay encabezado se decide sobre el texto y no sobre el braille ya
    # escrito: en braille un número lleva delante su signo y no parecería un
    # número, con lo que ninguna tabla tendría encabezado.
    con_titulos = _hay_encabezado(crudas)
    limpias = [[paso(celda) for celda in fila] for fila in crudas]

    anchos = [max(len(fila[numero]) for fila in limpias)
              for numero in range(columnas)]
    # Una celda de separación entre columnas, que es lo que las despega al tacto.
    if sum(anchos) + (columnas - 1) <= ancho:
        return _tabla_en_columnas(limpias, anchos, paso, con_titulos)
    return _tabla_linealizada(filas, paso, con_titulos)


def _hay_encabezado(filas) -> bool:
    """Dice si la primera fila son los nombres de las columnas.

    Se pide que no tenga ninguna celda vacía, que ninguna sea un número y que
    debajo haya al menos uno: una fila de textos encima de más textos puede ser
    perfectamente la primera fila de datos —una tabla de palabras reservadas, por
    ejemplo, donde subrayar la primera fila diría algo que no es—.
    """
    if len(filas) < 2:
        return False
    if not all(celda.strip() for celda in filas[0]):
        return False
    if any(_es_cifra(celda) for celda in filas[0]):
        return False
    return any(_es_cifra(celda) for fila in filas[1:] for celda in fila)


def _es_cifra(texto: str) -> bool:
    """Dice si lo escrito en una celda es un número."""
    limpio = (texto or "").strip().replace(" ", "").replace(".", "")
    limpio = limpio.replace(",", ".").lstrip("-+").rstrip("%\u20ac$")
    if not limpio:
        return False
    try:
        float(limpio)
    except ValueError:
        return False
    return True


def _tabla_en_columnas(filas, anchos, paso, con_titulos) -> list[str]:
    """La tabla con sus columnas alineadas y una raya bajo el encabezado."""
    lineas = []
    for numero, fila in enumerate(filas):
        lineas.append(" ".join(celda.ljust(anchos[indice])
                               for indice, celda in enumerate(fila)).rstrip())
        if numero == 0 and con_titulos:
            lineas.append(" ".join(paso("-" * medida) for medida in anchos))
    return lineas


def _tabla_linealizada(filas, paso, con_titulos=True) -> list[str]:
    """La tabla fila a fila, con el nombre de la columna delante de cada dato.

    Es la forma que se usa cuando la tabla no cabe a lo ancho, y la única en la
    que un dato no puede quedarse huérfano de su encabezado.

    Se traduce **el renglón entero de una vez**, con sus dos puntos dentro: la
    puntuación tiene su propio signo en braille y ponerla luego a mano dejaría
    un carácter que no significa lo que parece.
    """
    if con_titulos:
        cabecera = [" ".join((celda or "").split()) for celda in filas[0]]
        cuerpo = filas[1:]
    else:
        # Sin títulos, la columna se nombra por su número: es lo único honrado
        # que se puede decir, y desde luego mejor que quedarse sin la primera
        # fila o que llamarla como no se llama.
        cabecera = [_("Columna %d") % (numero + 1)
                    for numero in range(max(len(fila) for fila in filas))]
        cuerpo = filas
    lineas = []
    for fila in cuerpo:
        celdas = [" ".join((celda or "").split()) for celda in fila]
        lineas.append(paso(celdas[0]) if celdas and celdas[0] else paso("-"))
        for numero, celda in enumerate(celdas[1:], start=1):
            if not celda:
                continue
            titulo = cabecera[numero] if numero < len(cabecera) else ""
            lineas.append("  " + paso("%s: %s" % (titulo, celda) if titulo
                                      else celda))
        lineas.append("")
    while lineas and not lineas[-1]:
        lineas.pop()
    return lineas


def _paginar(lineas: list[str], alto: int) -> list[str]:
    """Reparte los renglones en páginas."""
    paginas = []
    for numero in range(0, len(lineas), alto):
        paginas.append("\r\n".join(lineas[numero:numero + alto]))
    return paginas


def a_brf(texto: str, ancho: int = ANCHO, alto: int = ALTO) -> bytes:
    """Escribe el texto como archivo BRF, ya paginado.

    Las líneas se cortan **por donde acaba una palabra**, nunca por medio: una
    palabra partida entre dos líneas en braille se lee dos veces mal.  Las
    páginas se separan con un salto de página, que es lo que dice a la
    impresora que empiece una hoja nueva.
    """
    return brf_de_bloques([(False, texto)], ancho, alto)


def brf_de_bloques(bloques, ancho: int = ANCHO, alto: int = ALTO) -> bytes:
    """Como :func:`a_brf`, pero admitiendo trozos ya escritos en braille."""
    paginas = _paginar(lineas_de_bloques(bloques, ancho), alto)
    return ("\r\n\x0c".join(paginas) + "\r\n").encode("ascii", "replace")


def _lineas_de(texto: str) -> list[str]:
    """Traduce el texto y lo devuelve como líneas de braille ASCII."""
    salida = []
    actual: list[str] = []
    for celda in a_celdas(texto):
        if celda == -1:
            salida.append("".join(actual))
            actual = []
            continue
        actual.append(_caracter_brf(celda))
    salida.append("".join(actual))
    return salida


def _cortar(linea: str, ancho: int) -> list[str]:
    """Parte una línea larga sin cortar ninguna palabra."""
    if len(linea) <= ancho:
        return [linea] if linea else []
    salida = []
    resto = linea
    while len(resto) > ancho:
        corte = resto.rfind(" ", 0, ancho + 1)
        if corte <= 0:
            corte = ancho              # una palabra más larga que la línea
        salida.append(resto[:corte].rstrip())
        resto = resto[corte:].lstrip()
    if resto:
        salida.append(resto)
    return salida


#: Espacio de nombres del PEF, la norma con la que se intercambia braille ya
#: compuesto entre bibliotecas, imprentas y programas de transcripción.
PEF = "http://www.daisy.org/ns/2008/pef"


def a_paginas(texto: str, ancho: int = ANCHO, alto: int = ALTO) -> list[list[str]]:
    """Compone el braille y lo devuelve por páginas y renglones, en Unicode.

    Es el mismo trabajo que hace :func:`a_brf` —traducir, cortar por palabras y
    paginar—, pero devolviendo las líneas en lugar de un archivo, que es lo que
    hace falta para escribir un PEF.
    """
    return paginas_de_bloques([(False, texto)], ancho, alto)


def paginas_de_bloques(bloques, ancho: int = ANCHO, alto: int = ALTO) -> list[list[str]]:
    """Como :func:`a_paginas`, pero admitiendo trozos ya escritos en braille."""
    lineas = lineas_de_bloques(bloques, ancho)
    paginas = []
    for numero in range(0, len(lineas), alto):
        paginas.append([_a_unicode_desde_brf(linea)
                        for linea in lineas[numero:numero + alto]])
    return paginas


def _a_unicode_desde_brf(linea: str) -> str:
    """Pasa una línea de braille ASCII a signos braille de Unicode.

    Se hace sobre lo ya compuesto y no traduciendo otra vez desde el texto,
    para que el PEF y el BRF salgan **exactamente iguales**: mismo corte de
    palabras, misma paginación y mismos signos.  Traducir dos veces sería la
    forma segura de que un día dejaran de coincidir.
    """
    salida = []
    for caracter in linea:
        indice = ASCII_BRAILLE.find(caracter.upper())
        salida.append(chr(UNICODE_BRAILLE + indice) if indice >= 0 else caracter)
    return "".join(salida)


def a_pef(texto: str, titulo: str = "", autor: str = "", identificador: str = "",
          ancho: int = ANCHO, alto: int = ALTO, bloques=None) -> bytes:
    """Escribe el braille como archivo PEF.

    PEF (*Portable Embosser Format*) es el braille **ya compuesto** guardado en
    XML: cada página con sus renglones y cada renglón con sus celdas, escritas
    con los signos braille de Unicode.  Frente al BRF gana en dos cosas que
    importan: lleva dentro el título y el autor, y no depende de qué tabla de
    braille ASCII use quien lo abra, porque las celdas van dichas sin
    ambigüedad.  Es lo que se intercambian las bibliotecas y las imprentas
    braille de Europa.

    El BRF se sigue exportando, y se seguirá: es lo que entienden los
    anotadores y las impresoras de siempre.  Los dos hacen falta.
    """
    from xml.sax.saxutils import escape

    paginas = (paginas_de_bloques(bloques, ancho, alto) if bloques is not None
               else a_paginas(texto, ancho, alto))
    partes = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<pef version="2008-1" xmlns="%s">' % PEF,
        '<head><meta xmlns:dc="http://purl.org/dc/elements/1.1/">',
        "<dc:title>%s</dc:title>" % escape(titulo or _("Documento")),
    ]
    if autor:
        partes.append("<dc:creator>%s</dc:creator>" % escape(autor))
    partes.append("<dc:format>application/x-pef+xml</dc:format>")
    partes.append("<dc:identifier>%s</dc:identifier>"
                  % escape(identificador or "visor-braille"))
    partes.append("</meta></head>")
    partes.append('<body><volume cols="%d" rows="%d" rowgap="0" duplex="false">'
                  % (ancho, alto))
    partes.append("<section>")
    for pagina in paginas:
        partes.append("<page>")
        for linea in pagina:
            partes.append("<row>%s</row>" % escape(linea))
        partes.append("</page>")
    partes.append("</section>")
    partes.append("</volume></body>")
    partes.append("</pef>")
    return ("\n".join(partes) + "\n").encode("utf-8")


def descripcion() -> str:
    """Frase que explica qué se obtiene, para el diálogo de exportación."""
    return _("Braille de grado 1 en español, %d celdas por línea y %d líneas por "
             "página.") % (ANCHO, ALTO)
