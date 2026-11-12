# -*- coding: utf-8 -*-
"""Extrae los textos traducibles y genera la plantilla de traducción.

Recorre el código, recoge todo lo que pasa por ``_()`` y escribe
``data/idiomas/visor.pot``, la plantilla desde la que se traduce.

Uso, desde la carpeta del programa::

    python herramientas/textos.py

Después, para traducir a un idioma:

1. Copia ``visor.pot`` a ``data/idiomas/<código>/LC_MESSAGES/visor.po``
   (por ejemplo ``en`` para el inglés) y traduce cada ``msgstr``.  Sirve
   cualquier editor de texto, aunque **Poedit** lo hace mucho más cómodo.
2. Compílalo a ``visor.mo`` en esa misma carpeta.  Con Poedit se hace solo al
   guardar; a mano, con ``msgfmt visor.po -o visor.mo``, o con este mismo guion::

       python herramientas/textos.py --compilar

3. Elige el idioma en **Opciones → Avanzado** y reinicia el programa.

No hace falta ninguna herramienta externa: la extracción se hace leyendo el
árbol sintáctico de los archivos, y la compilación con :mod:`msgfmt` de la
biblioteca estándar de Python.
"""

from __future__ import annotations

import ast
import io
import os
import re
import struct
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FUENTE = RAIZ / "src"
IDIOMAS = RAIZ / "data" / "idiomas"
DOMINIO = "visor"

CABECERA = '''# Traducción de Visor Universal.
# Los textos originales están en español: son la clave de cada traducción.
#
msgid ""
msgstr ""
"Project-Id-Version: Visor Universal\\n"
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Content-Transfer-Encoding: 8bit\\n"
"Language: \\n"
"Plural-Forms: nplurals=2; plural=(n != 1);\\n"

'''


def _escapar(texto: str) -> str:
    """Deja un texto listo para escribirlo en un archivo .po."""
    return (texto.replace("\\", "\\\\").replace('"', '\\"')
            .replace("\n", "\\n").replace("\t", "\\t"))


def _constante(nodo) -> str | None:
    """Devuelve el texto de un argumento si es una constante de texto."""
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
        return nodo.value
    return None


def recoger() -> tuple[dict[str, list[str]], dict[tuple[str, str], list[str]]]:
    """Recoge todo lo traducible del código.

    :return: Dos diccionarios, ``{texto: [dónde]}`` con lo que pasa por ``_()``
             y ``{(singular, plural): [dónde]}`` con lo que pasa por ``_n()``.
             Van separados porque en un ``.po`` son entradas de distinta forma:
             las de plural llevan ``msgid_plural`` y tantas traducciones como
             formas tenga el idioma.
    """
    textos: dict[str, list[str]] = {}
    plurales: dict[tuple[str, str], list[str]] = {}
    for base, carpetas, nombres in os.walk(FUENTE):
        carpetas[:] = [c for c in carpetas if c != "__pycache__"]
        for nombre in sorted(nombres):
            if not nombre.endswith(".py"):
                continue
            ruta = Path(base) / nombre
            arbol = ast.parse(io.open(ruta, encoding="utf-8").read(), str(ruta))
            relativa = ruta.relative_to(RAIZ).as_posix()
            for nodo in ast.walk(arbol):
                if not isinstance(nodo, ast.Call) or not isinstance(nodo.func, ast.Name):
                    continue
                donde = "%s:%d" % (relativa, nodo.lineno)
                if nodo.func.id == "_" and nodo.args:
                    valor = _constante(nodo.args[0])
                    if valor is not None:
                        textos.setdefault(valor, []).append(donde)
                elif nodo.func.id == "_n" and len(nodo.args) >= 2:
                    singular = _constante(nodo.args[0])
                    plural = _constante(nodo.args[1])
                    if singular is not None and plural is not None:
                        plurales.setdefault((singular, plural), []).append(donde)
    return textos, plurales


def escribir_plantilla() -> Path:
    """Escribe ``visor.pot`` con todos los textos encontrados."""
    textos, plurales = recoger()
    IDIOMAS.mkdir(parents=True, exist_ok=True)
    destino = IDIOMAS / ("%s.pot" % DOMINIO)
    with io.open(destino, "w", encoding="utf-8", newline="\n") as archivo:
        archivo.write(CABECERA)
        for texto in sorted(textos):
            for donde in textos[texto]:
                archivo.write("#: %s\n" % donde)
            archivo.write('msgid "%s"\n' % _escapar(texto))
            archivo.write('msgstr ""\n\n')
        # Las entradas de plural van al final y con dos huecos de traducción,
        # que es lo que espera cualquier editor de .po (Poedit las presenta
        # como una sola entrada con varias pestañas).
        for singular, plural in sorted(plurales):
            for donde in plurales[(singular, plural)]:
                archivo.write("#: %s\n" % donde)
            archivo.write('msgid "%s"\n' % _escapar(singular))
            archivo.write('msgid_plural "%s"\n' % _escapar(plural))
            archivo.write('msgstr[0] ""\n')
            archivo.write('msgstr[1] ""\n\n')
    print("Textos traducibles: %d (%d con plural)" % (len(textos) + len(plurales),
                                                      len(plurales)))
    print("Plantilla escrita en: %s" % destino)
    return destino


#: Regla de plural de cada idioma, para la cabecera del catálogo.  Sin ella,
#: :mod:`gettext` usa siempre la primera forma y todos los plurales saldrían en
#: singular.  Los que no estén aquí usan la regla del español, que es la más
#: extendida: una forma para el uno y otra para todo lo demás.
PLURALES = {
    "ar": "nplurals=6; plural=(n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 "
          ": n%100>=11 ? 4 : 5);",
    "cs": "nplurals=3; plural=(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2;",
    "fr": "nplurals=2; plural=(n > 1);",
    "hu": "nplurals=2; plural=(n != 1);",
    "ja": "nplurals=1; plural=0;",
    "ko": "nplurals=1; plural=0;",
    "pl": "nplurals=3; plural=(n==1 ? 0 : n%10>=2 && n%10<=4 && (n%100<12 || n%100>14) ? 1 : 2);",
    "pt": "nplurals=2; plural=(n > 1);",
    "ro": "nplurals=3; plural=(n==1 ? 0 : (n==0 || (n%100 > 0 && n%100 < 20)) ? 1 : 2);",
    "ru": "nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 "
          "&& (n%100<12 || n%100>14) ? 1 : 2);",
    "tr": "nplurals=2; plural=(n > 1);",
    "uk": "nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 "
          "&& (n%100<12 || n%100>14) ? 1 : 2);",
    "zh-CN": "nplurals=1; plural=0;",
}

#: Cuántas formas de plural tiene cada regla.  Se saca del propio texto para no
#: tener que escribirlo dos veces y que puedan discrepar.
def formas_de_plural(codigo: str) -> int:
    """Número de formas de plural que usa un idioma."""
    regla = PLURALES.get(codigo, "nplurals=2;")
    encontrado = re.search(r"nplurals\s*=\s*(\d+)", regla)
    return int(encontrado.group(1)) if encontrado else 2


def ruta_de_idioma(codigo: str) -> Path:
    """Dónde vive el catálogo de un idioma."""
    return IDIOMAS / codigo / "LC_MESSAGES" / ("%s.po" % DOMINIO)


def cabecera_de(codigo: str, nombre: str = "") -> str:
    """Cabecera del catálogo de un idioma, con su regla de plural."""
    return (
        'Project-Id-Version: %s\n'
        'MIME-Version: 1.0\n'
        'Content-Type: text/plain; charset=UTF-8\n'
        'Content-Transfer-Encoding: 8bit\n'
        'Plural-Forms: %s\n'
        'Language: %s\n'
    ) % (nombre or "Visor Universal", PLURALES.get(codigo, "nplurals=2; plural=(n != 1);"),
         codigo)


def escribir_po(codigo: str, simples: dict, plurales: dict, ruta: Path | None = None) -> Path:
    """Escribe el catálogo de un idioma con las traducciones que se le den.

    Se escriben **todas** las entradas del programa, tengan traducción o no:
    una entrada vacía es lo que hace que el editor la enseñe como pendiente, y
    :mod:`gettext` la resuelve devolviendo el original en español, así que un
    catálogo a medias funciona sin romper nada.

    :param codigo: Idioma (``it``, ``fr``...).
    :param simples: ``{original: traducción}``.
    :param plurales: ``{singular: (plural, [formas])}``.
    :param ruta: Dónde escribirlo; por omisión, el sitio que le toca.
    """
    originales, originales_plural = recoger()
    destino = Path(ruta) if ruta is not None else ruta_de_idioma(codigo)
    destino.parent.mkdir(parents=True, exist_ok=True)
    cuantas = formas_de_plural(codigo)
    with io.open(destino, "w", encoding="utf-8", newline="\n") as archivo:
        archivo.write("# Traducción de %s al %s.\n" % ("Visor Universal", codigo))
        archivo.write("# Los textos originales están en español: son la clave de cada"
                      " traducción.\n#\n")
        archivo.write('msgid ""\nmsgstr ""\n')
        for linea in cabecera_de(codigo).rstrip("\n").split("\n"):
            archivo.write('"%s\\n"\n' % linea)
        archivo.write("\n")
        for original in sorted(originales):
            archivo.write('msgid "%s"\n' % _escapar(original))
            archivo.write('msgstr "%s"\n\n' % _escapar(simples.get(original, "")))
        for singular, plural in sorted(originales_plural):
            archivo.write('msgid "%s"\n' % _escapar(singular))
            archivo.write('msgid_plural "%s"\n' % _escapar(plural))
            formas = list(plurales.get(singular, ("", []))[1])
            while len(formas) < cuantas:
                formas.append("")
            for numero in range(cuantas):
                archivo.write('msgstr[%d] "%s"\n' % (numero, _escapar(formas[numero])))
            archivo.write("\n")
    return destino


def cargar_po(codigo: str) -> tuple[dict, dict]:
    """Lee el catálogo de un idioma; devuelve dos diccionarios vacíos si no hay."""
    destino = ruta_de_idioma(codigo)
    if not destino.exists():
        return {}, {}
    simples, plurales = _leer_po(destino)
    simples.pop("", None)          # la cabecera no es una traducción
    return simples, plurales


def crear_idioma(codigo: str) -> Path:
    """Crea el catálogo de un idioma nuevo, vacío y listo para traducir.

    Si ya existe **no se pisa**: se rellena con lo que haya y se le añaden las
    entradas nuevas del programa.  Es lo que hace falta después de tocar el
    código: los textos que se añadieron aparecen pendientes y lo ya traducido
    sigue donde estaba.
    """
    simples, plurales = cargar_po(codigo)
    destino = escribir_po(codigo, simples, plurales)
    originales, originales_plural = recoger()
    print("Idioma %s: %d textos, %d traducidos, %d pendientes"
          % (codigo, len(originales), len(simples), len(originales) - len(simples)))
    print("Catálogo: %s" % destino)
    return destino


def _leer_po(ruta: Path) -> tuple[dict[str, str], dict[str, tuple[str, list[str]]]]:
    """Lee un archivo .po y devuelve sus traducciones.

    :return: Dos diccionarios: ``{msgid: traducción}`` con las entradas
             normales y ``{msgid: (msgid_plural, [traducciones])}`` con las de
             plural.

    Se conserva la entrada de ``msgid`` vacío, que es la **cabecera** del
    catálogo.  Parece prescindible y no lo es: de ahí saca :mod:`gettext` la
    codificación y, desde que hay plurales, también la regla que decide qué
    forma toca para cada número.

    El análisis es a propósito tolerante: una línea mal escrita se salta con un
    aviso en vez de tirar la compilación entera, porque un ``.po`` lo edita una
    persona y siempre acaba habiendo alguna.
    """
    simples: dict[str, str] = {}
    plurales: dict[str, tuple[str, list[str]]] = {}

    clave = ""
    plural_de = None
    valor = ""
    formas: list[str] = []
    donde = None

    def guardar() -> None:
        """Cierra la entrada que se estaba leyendo."""
        if clave is None:
            return
        if plural_de is not None:
            if any(f for f in formas):
                plurales[clave] = (plural_de, list(formas))
        elif valor:
            simples[clave] = valor

    for linea in io.open(ruta, encoding="utf-8"):
        linea = linea.strip()
        if linea.startswith("#") :
            continue
        if linea.startswith("msgid_plural "):
            plural_de = ast.literal_eval(linea[13:])
            donde = "plural"
            continue
        if linea.startswith("msgid "):
            guardar()
            clave, plural_de, valor, formas = ast.literal_eval(linea[6:]), None, "", []
            donde = "id"
            continue
        if linea.startswith("msgstr["):
            corchete = linea.index("]")
            numero = int(linea[7:corchete])
            texto = ast.literal_eval(linea[corchete + 2:].strip())
            while len(formas) <= numero:
                formas.append("")
            formas[numero] = texto
            donde = "forma%d" % numero
            continue
        if linea.startswith("msgstr "):
            valor, donde = ast.literal_eval(linea[7:]), "str"
            continue
        if linea.startswith('"') and donde:
            try:
                trozo = ast.literal_eval(linea)
            except (SyntaxError, ValueError):
                print("  (línea ignorada en %s: %s)" % (ruta.name, linea[:50]))
                continue
            if donde == "id":
                clave = (clave or "") + trozo
            elif donde == "plural":
                plural_de = (plural_de or "") + trozo
            elif donde.startswith("forma"):
                numero = int(donde[5:])
                formas[numero] += trozo
            else:
                valor = (valor or "") + trozo
            continue
        if not linea:
            guardar()
            clave, plural_de, valor, formas, donde = "", None, "", [], None
    guardar()
    return simples, plurales


def _cabecera_valida(cabecera: str) -> str:
    """Completa la cabecera del catálogo con lo imprescindible.

    Sin ``Content-Type``, :mod:`gettext` lee el catálogo como ASCII y falla en
    el primer acento.  Sin ``Plural-Forms``, no sabe qué forma elegir y usa
    siempre la primera, de modo que todos los plurales saldrían en singular.
    """
    if not cabecera:
        cabecera = ""
    if "content-type" not in cabecera.lower():
        cabecera += "Content-Type: text/plain; charset=UTF-8\\n"
    if "plural-forms" not in cabecera.lower():
        cabecera += "Plural-Forms: nplurals=2; plural=(n != 1);\\n"
    return cabecera


def compilar() -> int:
    """Convierte a ``.mo`` todos los ``.po`` que haya en ``data/idiomas``.

    El formato ``.mo`` guarda los plurales dentro de las mismas dos tablas que
    el resto: el original es ``singular\\0plural`` y la traducción, todas las
    formas separadas por ceros.  Es la convención de GNU gettext y lo que el
    módulo de Python espera encontrar.
    """
    # La plantilla se rehace aquí porque este es el paso por el que se pasa
    # siempre: al compilar el ejecutable y al pulsar «Compilar» en el editor de
    # traducciones.  Así el «visor.pot» que se publica nunca va por detrás de
    # los textos que el programa tiene de verdad.
    escribir_plantilla()

    hechos = 0
    for po in sorted(IDIOMAS.glob("*/LC_MESSAGES/%s.po" % DOMINIO)):
        simples, plurales = _leer_po(po)
        simples[""] = _cabecera_valida(simples.get("", ""))

        entradas: list[tuple[bytes, bytes]] = []
        for clave in simples:
            entradas.append((clave.encode("utf-8"), simples[clave].encode("utf-8")))
        for clave, (plural, formas) in plurales.items():
            original = clave.encode("utf-8") + b"\x00" + plural.encode("utf-8")
            traduccion = b"\x00".join(forma.encode("utf-8") for forma in formas)
            entradas.append((original, traduccion))
        # La tabla del .mo tiene que ir ordenada por el original: el lector
        # hace una búsqueda binaria sobre ella.
        entradas.sort(key=lambda par: par[0])

        cantidad = len(entradas)
        inicio = 7 * 4 + 16 * cantidad
        posiciones_o, posiciones_t = [], []
        datos = b""
        for original, _traduccion in entradas:
            posiciones_o.append((len(original), inicio + len(datos)))
            datos += original + b"\x00"
        for _original, traduccion in entradas:
            posiciones_t.append((len(traduccion), inicio + len(datos)))
            datos += traduccion + b"\x00"
        salida = struct.pack("<7I", 0x950412DE, 0, cantidad,
                             7 * 4, 7 * 4 + cantidad * 8, 0, 0)
        for largo, desplazamiento in posiciones_o + posiciones_t:
            salida += struct.pack("<2I", largo, desplazamiento)
        salida += datos
        destino = po.with_suffix(".mo")
        destino.write_bytes(salida)
        print("Compilado: %s (%d textos, %d con plural)"
              % (destino, cantidad, len(plurales)))
        hechos += 1
    if not hechos:
        print("No hay ningún .po en %s" % IDIOMAS)
    return hechos


if __name__ == "__main__":
    if "--compilar" in sys.argv:
        compilar()
    elif "--nuevo" in sys.argv:
        posicion = sys.argv.index("--nuevo")
        if posicion + 1 >= len(sys.argv):
            print("Uso: python herramientas/textos.py --nuevo <código>   (por ejemplo: it)")
            sys.exit(1)
        crear_idioma(sys.argv[posicion + 1])
    else:
        escribir_plantilla()
