# -*- coding: utf-8 -*-
"""Revisa las traducciones automáticas buscando lo que se puede comprobar.

Francés, italiano y portugués están traducidos a máquina. Una máquina traduce
bien las frases y se equivoca en lo que no sabe que es un término: tradujo «do»
como «faire», «bemol» como «plat», «DAISY» como «Margherita» y «doble bemol»
como «apartamento doble». Ninguno de esos errores se ve leyendo el programa en
español, y quien lee en francés no tiene forma de saber que lo que oye está mal.

**Lo que se puede comprobar sin hablar el idioma**, que es lo que hace esta
herramienta:

1. **Un nombre propio no se traduce.** Si en el original pone «Anthropic»,
   «DAISY» o «Tesseract» y en la traducción no aparece, se ha perdido.
2. **Una sigla de formato tampoco.** «PEF» pasó a ser «FEP» en francés, y eso
   estaba dentro del filtro de archivos del diálogo de guardar.
3. **Los marcadores tienen que ser los mismos.** Si el original lleva ``%s`` y
   la traducción no, el programa revienta al usarla; si lleva ``%(numero)d`` y
   la traducción escribe otro nombre, también.
4. **Los atajos de teclado no cambian.** «Control+D» es la misma tecla en todos
   los idiomas, y traducirla como «Contrôle+J» manda a quien lea a otro sitio.
5. **El vocabulario técnico tiene traducción fija.** Es el glosario de abajo:
   las notas, las figuras y las alteraciones, que es donde una máquina se
   equivoca sin remedio porque son palabras corrientes en cualquier idioma.

Lo que **no** comprueba es si una frase suena natural. Eso no se puede
automatizar y sigue haciendo falta que lo mire quien hable el idioma; esta
herramienta está para que ese repaso no tenga que empezar por lo evidente.

Uso::

    python herramientas/revisar_traducciones.py             # todos los idiomas
    python herramientas/revisar_traducciones.py fr it       # solo estos
    python herramientas/revisar_traducciones.py --arreglar  # aplica el glosario

Sin ``--arreglar`` no toca nada: solo dice qué encuentra.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ / "herramientas") not in sys.path:
    sys.path.insert(0, str(RAIZ / "herramientas"))

import textos                                            # noqa: E402

#: Idiomas traducidos a máquina.  El español es el original y el inglés se
#: repasó a mano, pero se miran todos: la comprobación no cuesta nada.
IDIOMAS = ("en", "fr", "it", "pt")

#: Lo que tiene que aparecer igual en la traducción: nombres de empresa, de
#: programa y siglas de formato.  Se comparan sin distinguir mayúsculas —eso sí
#: es cosa de cada idioma— pero la palabra no puede desaparecer.
#:
#: «RAR» y «ZIP» no están: aparecen dentro de palabras corrientes en español
#: («borrar», «restaurar») y darían cientos de avisos falsos.
INTOCABLES = (
    "Anthropic", "OpenAI", "Gemini", "Ollama", "Claude", "ChatGPT",
    "Tesseract", "7-Zip", "WinRAR", "NVDA", "JAWS", "LibreOffice",
    "Kindle", "Amazon", "Adobe", "DAISY", "EPUB", "MOBI", "DjVu", "PDF",
    "CHM", "RTF", "ODT", "XHTML", "PEF", "BRF", "MusicXML", "Markdown",
    "Snowball", "SAPI", "ONCE", "ASCII", "MathML", "OCR",
)

#: El glosario: original español -> (inglés, francés, italiano, portugués).
#:
#: No es una traducción palabra a palabra, es **el término de cada tradición**.
#: Una «redonda» es *whole note* en inglés y *ronde* en francés, pero
#: *semibreve* en italiano y en portugués: son dos maneras distintas de contar,
#: una por la forma de la figura y otra por su duración.
GLOSARIO = {
    # -- los nombres de las notas -----------------------------------------
    # Los siete vienen del himno de Guido de Arezzo y son los mismos en las
    # lenguas románicas; el inglés usa letras.  Aquí es donde una máquina hace
    # más daño: «la» y «si» también son artículo y conjunción, «mi» es un
    # posesivo y «do» es el verbo «hacer» en inglés.
    "do": ("C", "do", "do", "dó"),
    "re": ("D", "ré", "re", "ré"),
    "mi": ("E", "mi", "mi", "mi"),
    "fa": ("F", "fa", "fa", "fá"),
    "sol": ("G", "sol", "sol", "sol"),
    "la": ("A", "la", "la", "lá"),
    "si": ("B", "si", "si", "si"),

    # -- las figuras -------------------------------------------------------
    "redonda": ("whole note", "ronde", "semibreve", "semibreve"),
    "blanca": ("half note", "blanche", "minima", "mínima"),
    "negra": ("quarter note", "noire", "semiminima", "semínima"),
    "corchea": ("eighth note", "croche", "croma", "colcheia"),
    "semicorchea": ("sixteenth note", "double croche", "semicroma",
                    "semicolcheia"),
    "fusa": ("thirty-second note", "triple croche", "biscroma", "fusa"),
    "semifusa": ("sixty-fourth note", "quadruple croche", "semibiscroma",
                 "semifusa"),
    "garrapatea": ("hundred twenty-eighth note", "quintuple croche", "fusa",
                   "semifusa dupla"),
    "cuadrada": ("breve", "carrée", "breve", "breve"),
    "longa": ("longa", "longue", "lunga", "longa"),

    # -- las alteraciones --------------------------------------------------
    # «Bemol» salió como «plat», «Piatto» y «plano»: el traductor leyó el inglés
    # *flat* y lo tradujo como «llano».
    "sostenido": ("sharp", "dièse", "diesis", "sustenido"),
    "bemol": ("flat", "bémol", "bemolle", "bemol"),
    "doble sostenido": ("double sharp", "double dièse", "doppio diesis",
                        "duplo sustenido"),
    "doble bemol": ("double flat", "double bémol", "doppio bemolle",
                    "bemol dobrado"),

    # -- los adornos -------------------------------------------------------
    "trino": ("trill", "trille", "trillo", "trinado"),
    "mordente": ("mordent", "mordant", "mordente", "mordente"),
    "mordente invertido": ("inverted mordent", "mordant inversé",
                           "mordente invertito", "mordente invertido"),
    "grupeto": ("turn", "gruppetto", "gruppetto", "grupeto"),
    "grupeto invertido": ("inverted turn", "gruppetto inversé",
                          "gruppetto invertito", "grupeto invertido"),
    "apoyatura": ("appoggiatura", "appoggiature", "appoggiatura", "apojatura"),
    "apoyatura corta": ("acciaccatura", "appoggiature brève", "acciaccatura",
                        "apojatura breve"),
}

#: Lo que se ha decidido dejar así, con el motivo.  Una herramienta que avisa
#: de algo correcto deja de leerse, y entonces ya no sirve para nada.
PERDONADAS = {
    ("en", "Escribe qué quieres que cuente de la imagen y con cuánto detalle. "
           "No hace falta pedir que responda en español ni sin markdown: el "
           "programa ya lo añade."):
        "en inglés «markdown» se dice «plain text», y así está escrito",
}

def _aplanar(texto: str) -> str:
    """El texto sin depender de dónde se haya partido el renglón."""
    return " ".join(texto.split())


#: Las excepciones, ya aplanadas, para poder buscarlas.
_PERDONADAS = {(codigo, _aplanar(texto)): motivo
               for (codigo, texto), motivo in PERDONADAS.items()}

#: Los marcadores que el programa sustituye al mostrar el texto.  Tienen que
#: estar los mismos y con el mismo nombre; el orden sí puede cambiar, que es
#: justo para lo que sirven los de nombre.
_MARCADORES = re.compile(r"%(?:\([^)]*\))?[-#0-9.+ ]*[a-zA-Z%]")

#: La **tecla final** de un atajo escrito dentro de un texto, con su
#: modificador delante.  Se recoge solo la tecla: los modificadores se traducen
#: —«Mayús» es «Maj» en francés y «Maiusc» en italiano— y la tecla no.
_ATAJOS = re.compile(
    r"(?:Control|Ctrl|Alt|May[úu]s|Maj|Maiusc|Umschalt|Shift)\s*\+\s*"
    r"([A-Za-z0-9])\b", re.I)


def _palabra(cual: str) -> re.Pattern:
    """Busca ``cual`` como palabra suelta, no dentro de otra."""
    letra = r"[0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñÀ-ÿ]"
    # Se admite una «s» detrás: «los PDF» en español y «PDFs» en portugués son
    # la misma sigla, y contarlos distinto daría cientos de avisos falsos.
    return re.compile(r"(?<!%s)%ss?(?!%s)" % (letra, re.escape(cual), letra),
                      re.IGNORECASE)


_BUSCADORES = {cual: _palabra(cual) for cual in INTOCABLES}


def revisar(codigo: str) -> list:
    """Todas las pegas de un idioma. Devuelve ``[(clase, original, aviso)]``."""
    simples, plurales = textos.cargar_po(codigo)
    numero = IDIOMAS.index(codigo) if codigo in IDIOMAS else 0
    pegas = []

    for original, traducido in sorted(simples.items()):
        if not traducido or not original:
            continue

        if (codigo, _aplanar(original)) in _PERDONADAS:
            continue

        # 1 y 2 - nombres propios y siglas
        for cual, buscador in _BUSCADORES.items():
            cuantas = len(buscador.findall(original))
            if cuantas > len(buscador.findall(traducido)):
                pegas.append(("nombre", original,
                              "se pierde «%s»: %s" % (cual, traducido)))
                break

        # 3 - marcadores de formato
        antes = sorted(_MARCADORES.findall(original))
        despues = sorted(_MARCADORES.findall(traducido))
        if antes != despues:
            pegas.append(("marcador", original,
                          "%s -> %s" % (antes or "nada", despues or "nada")))

        # 4 - atajos de teclado
        teclas_antes = sorted(t.upper() for t in _ATAJOS.findall(original))
        teclas_despues = sorted(t.upper() for t in _ATAJOS.findall(traducido))
        if teclas_antes and teclas_antes != teclas_despues:
            pegas.append(("atajo", original,
                          "%s -> %s" % (teclas_antes, teclas_despues or "nada")))

        # 5 - glosario
        if original in GLOSARIO:
            debido = GLOSARIO[original][numero]
            if traducido.lower() != debido.lower():
                pegas.append(("glosario", original,
                              "«%s» debería ser «%s»" % (traducido, debido)))

    # Los plurales solo se miran por sus marcadores: es donde revientan.
    for original, (_otro, formas) in sorted(plurales.items()):
        antes = sorted(_MARCADORES.findall(original))
        for forma in formas:
            if forma and sorted(_MARCADORES.findall(forma)) != antes:
                pegas.append(("marcador", original,
                              "en plural: %s" % forma))
    return pegas


def arreglar(codigo: str, pegas: list) -> int:
    """Escribe en el catálogo lo que dice el glosario. Dice cuántas cambió."""
    numero = IDIOMAS.index(codigo) if codigo in IDIOMAS else 0
    ruta = textos.IDIOMAS / codigo / "LC_MESSAGES" / "visor.po"
    contenido = ruta.read_text(encoding="utf-8")
    cuantas = 0
    for clase, original, _aviso in pegas:
        if clase != "glosario":
            continue
        patron = re.compile(
            r'(^msgid "%s"\n(?:#[^\n]*\n)*msgstr ")[^"]*(")'
            % re.escape(textos._escapar(original)), re.MULTILINE)
        contenido, hechas = patron.subn(
            lambda encaje: (encaje.group(1)
                            + textos._escapar(GLOSARIO[original][numero])
                            + encaje.group(2)),
            contenido, count=1)
        cuantas += hechas
    if cuantas:
        ruta.write_text(contenido, encoding="utf-8")
    return cuantas


def main(argumentos: list) -> int:
    reparar = "--arreglar" in argumentos
    pedidos = [a for a in argumentos if not a.startswith("--")] or list(IDIOMAS)
    total = 0
    for codigo in pedidos:
        if not (textos.IDIOMAS / codigo / "LC_MESSAGES" / "visor.po").is_file():
            print("%s: no hay catálogo" % codigo)
            continue
        pegas = revisar(codigo)
        total += len(pegas)
        por_clase: dict = {}
        for clase, original, aviso in pegas:
            por_clase.setdefault(clase, []).append((original, aviso))
        if not pegas:
            print("%s: sin problemas." % codigo)
            continue
        print("=== %s: %d pegas" % (codigo, len(pegas)))
        for clase in ("marcador", "glosario", "nombre", "atajo"):
            cuales = por_clase.get(clase, [])
            if not cuales:
                continue
            print("   %s (%d):" % (clase, len(cuales)))
            for original, aviso in cuales[:20]:
                print("      %-38s %s" % (original[:38], aviso[:80]))
            if len(cuales) > 20:
                print("      ... y %d más" % (len(cuales) - 20))
        if reparar:
            hechas = arreglar(codigo, pegas)
            if hechas:
                print("   arregladas %d del glosario" % hechas)
    if not total:
        print("\nSin problemas: nada que se pueda comprobar está mal.")
    else:
        print("\nTotal: %d pegas." % total)
        if not reparar:
            print("Con --arreglar se aplican las del glosario; las demás hay "
                  "que mirarlas una a una.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
