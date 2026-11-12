# -*- coding: utf-8 -*-
"""Revisa —y arregla— las letras de acceso de los menús en cada idioma.

En un menú de Windows, la letra subrayada de una orden es lo que permite
llegar a ella de una pulsación.  Cuando **dos órdenes del mismo menú llevan la
misma letra**, esa tecla deja de activar nada: resalta una, la siguiente
pulsación resalta la otra, y hace falta pulsar Intro además.  Quien recorre el
menú de oído lo vive como que la letra «no funciona», y no tiene forma de
averiguar por qué.

En español y en inglés las letras se eligen a mano, una a una.  En los demás
idiomas no se puede: las traducciones se hacen a máquina, y el traductor coloca
la letra sobre una palabra del texto traducido **sin saber qué hay al lado en
ese menú**.  Así que dos órdenes acaban con la misma letra sin que nadie lo
haya decidido.

Esta herramienta lo resuelve mirando los menús de verdad:

1. Construye la ventana principal en el idioma que se le diga y recorre la
   barra de menús entera, submenús incluidos.
2. En cada menú, busca las letras que se repiten.
3. Para cada orden repetida elige **otra letra de su propio texto**, prefiriendo
   el principio de una palabra, que es donde se busca.
4. Escribe la corrección en el catálogo de ese idioma.

Uso::

    python herramientas/revisar_menus.py            # revisa todos los idiomas
    python herramientas/revisar_menus.py --arreglar # además los corrige
    python herramientas/revisar_menus.py es en      # solo estos

Sin ``--arreglar`` no toca nada: solo dice qué encuentra, que es lo que hace
falta para comprobarlo antes de publicar.
"""

from __future__ import annotations

import re
import subprocess
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ / "src"))
if str(RAIZ / "herramientas") not in sys.path:
    sys.path.insert(0, str(RAIZ / "herramientas"))

import textos                                                    # noqa: E402

#: Letras que no valen como acceso: se escriben con acento o no están en el
#: teclado de todo el mundo.  Se admite la eñe porque en un teclado español
#: está, pero no se elige si hay otra.
_PREFERIDAS = "abcdefghijklmnopqrstuvwxyz"


def _sin_tilde(letra: str) -> str:
    """Devuelve la letra sin su acento, para poder compararla."""
    plano = unicodedata.normalize("NFKD", letra)
    return "".join(c for c in plano if not unicodedata.combining(c)).lower()


def letra_de(etiqueta: str) -> str:
    """La letra de acceso de una etiqueta, o cadena vacía si no lleva."""
    posicion = etiqueta.find("&")
    while 0 <= posicion < len(etiqueta) - 1:
        siguiente = etiqueta[posicion + 1]
        if siguiente != "&":
            return _sin_tilde(siguiente)
        posicion = etiqueta.find("&", posicion + 2)
    return ""


def sin_letra(etiqueta: str) -> str:
    """La etiqueta sin su marca de acceso, dejando los ampersands escritos."""
    salida = []
    posicion = 0
    quitado = False
    while posicion < len(etiqueta):
        if etiqueta[posicion] == "&" and posicion + 1 < len(etiqueta):
            if etiqueta[posicion + 1] == "&":
                salida.append("&&")
                posicion += 2
                continue
            if not quitado:
                quitado = True
                posicion += 1
                continue
        salida.append(etiqueta[posicion])
        posicion += 1
    return "".join(salida)


def colocar(etiqueta: str, letra: str) -> str:
    """Devuelve la etiqueta con la marca de acceso puesta en esa letra.

    Se pone en la **primera aparición** de la letra, que es donde el ojo y el
    dedo la buscan.
    """
    limpia = sin_letra(etiqueta)
    for posicion, caracter in enumerate(limpia):
        if _sin_tilde(caracter) == letra:
            return limpia[:posicion] + "&" + limpia[posicion:]
    return limpia


def candidatas(etiqueta: str, ocupadas: set) -> list:
    """Letras libres de una etiqueta, de la más buscada a la menos.

    Primero las iniciales de palabra —que es donde se mira— y después
    cualquier otra letra del texto.  Nunca se propone una letra que ya use otra
    orden del mismo menú.
    """
    limpia = sin_letra(etiqueta)
    iniciales = []
    demas = []
    anterior = " "
    for caracter in limpia:
        letra = _sin_tilde(caracter)
        if letra in _PREFERIDAS and letra not in ocupadas:
            if not anterior.isalnum():
                if letra not in iniciales:
                    iniciales.append(letra)
            elif letra not in demas:
                demas.append(letra)
        anterior = caracter
    return iniciales + [letra for letra in demas if letra not in iniciales]


# ---------------------------------------------------------------------------
# Recorrer los menús de verdad
# ---------------------------------------------------------------------------

#: Guion que se ejecuta aparte para cada idioma.  Hace falta un proceso por
#: idioma porque las tablas de menú se construyen al importar sus módulos y ya
#: no se pueden volver a traducir.
_GUION = r'''
import json, sys
sys.path.insert(0, r"%(src)s")
from nucleo import idioma, registro, rutas
rutas.preparar_estructura()
registro.iniciar("ERROR", "menus")
idioma.instalar("%(codigo)s")
import wx
from version import VERSION
from nucleo.configuracion import Configuracion
from interfaz.ventana import VentanaPrincipal

app = wx.App()
ventana = VentanaPrincipal(Configuracion(), VERSION)
barra = ventana.GetMenuBar()

salida = []
pendientes = [(barra.GetMenuLabelText(n), barra.GetMenu(n))
              for n in range(barra.GetMenuCount())]
while pendientes:
    camino, menu = pendientes.pop(0)
    for elemento in menu.GetMenuItems():
        if elemento.IsSeparator():
            continue
        etiqueta = elemento.GetItemLabel().split("\t")[0]
        salida.append({"menu": camino, "etiqueta": etiqueta})
        sub = elemento.GetSubMenu()
        if sub is not None:
            pendientes.append((camino + " / " + elemento.GetItemLabelText(), sub))
ventana.Destroy()
print("@@MENUS@@" + json.dumps(salida, ensure_ascii=False))
'''


def menus_de(codigo: str) -> list:
    """Devuelve ``[{menu, etiqueta}]`` de todos los menús en ese idioma."""
    guion = _GUION % {"src": str(RAIZ / "src"), "codigo": codigo}
    resultado = subprocess.run([sys.executable, "-c", guion],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", cwd=str(RAIZ))
    for linea in (resultado.stdout or "").splitlines():
        if linea.startswith("@@MENUS@@"):
            import json

            return json.loads(linea[len("@@MENUS@@"):])
    raise SystemExit("no se han podido leer los menús de «%s»:\n%s"
                     % (codigo, (resultado.stderr or "")[-2000:]))


def repetidas(entradas: list) -> dict:
    """``{menú: [etiquetas que comparten letra]}`` de lo que hay que arreglar."""
    por_menu: dict = {}
    for entrada in entradas:
        por_menu.setdefault(entrada["menu"], []).append(entrada["etiqueta"])
    problemas = {}
    for menu, etiquetas in por_menu.items():
        letras = [letra_de(e) for e in etiquetas]
        chocan = {letra for letra in letras if letra and letras.count(letra) > 1}
        if chocan:
            problemas[menu] = [e for e in etiquetas if letra_de(e) in chocan]
    return problemas


# ---------------------------------------------------------------------------
# Corregir el catálogo
# ---------------------------------------------------------------------------

def _indice_inverso(codigo: str) -> dict:
    """``{traducción: original}`` del catálogo de un idioma."""
    simples, _plurales = textos.cargar_po(codigo)
    inverso = {}
    for original, traducido in simples.items():
        if traducido:
            inverso.setdefault(traducido, original)
    return inverso


def _escribir(codigo: str, original: str, nueva: str) -> bool:
    """Cambia en el catálogo la traducción de un texto.  Dice si lo ha hecho."""
    ruta = textos.IDIOMAS / codigo / "LC_MESSAGES" / "visor.po"
    contenido = ruta.read_text(encoding="utf-8")
    patron = re.compile(
        r'(^msgid "%s"\n(?:#[^\n]*\n)*msgstr ")[^"]*(")'
        % re.escape(textos._escapar(original)), re.MULTILINE)
    contenido, cuantas = patron.subn(
        lambda encaje: encaje.group(1) + textos._escapar(nueva) + encaje.group(2),
        contenido, count=1)
    if not cuantas:
        return False
    ruta.write_text(contenido, encoding="utf-8")
    return True


def arreglar(codigo: str, entradas: list) -> list:
    """Reparte otra vez las letras que chocan.  Devuelve lo que ha cambiado."""
    inverso = _indice_inverso(codigo)
    por_menu: dict = {}
    for entrada in entradas:
        por_menu.setdefault(entrada["menu"], []).append(entrada["etiqueta"])

    cambios = []
    for menu, etiquetas in por_menu.items():
        ocupadas = set()
        for etiqueta in etiquetas:
            letra = letra_de(etiqueta)
            if letra and letra not in ocupadas:
                ocupadas.add(letra)
                continue
            # Esta orden repite la letra de otra: se le busca otra suya.
            original = inverso.get(etiqueta)
            if original is None:
                # Etiquetas armadas en marcha, como la lista de recientes.
                continue
            opciones = candidatas(etiqueta, ocupadas)
            if not opciones:
                cambios.append((menu, etiqueta, "", "sin letra libre"))
                continue
            nueva = colocar(etiqueta, opciones[0])
            if _escribir(codigo, original, nueva):
                ocupadas.add(opciones[0])
                cambios.append((menu, etiqueta, nueva, ""))
    return cambios


def main(argumentos: list) -> int:
    """Revisa los idiomas que se pidan y, si se dice, los corrige."""
    arregla = "--arreglar" in argumentos
    codigos = [a for a in argumentos if not a.startswith("--")]
    if not codigos:
        codigos = sorted(p.parent.parent.name
                         for p in textos.IDIOMAS.glob("*/LC_MESSAGES/visor.po"))

    problemas_totales = 0
    for codigo in codigos:
        entradas = menus_de(codigo)
        problemas = repetidas(entradas)
        if arregla and problemas:
            cambios = arreglar(codigo, entradas)
            for menu, antes, despues, motivo in cambios:
                print("  %s: «%s» -> «%s» %s" % (menu, antes, despues, motivo))
            if cambios:
                textos.compilar()
            entradas = menus_de(codigo)
            problemas = repetidas(entradas)
        if problemas:
            problemas_totales += len(problemas)
            print("%s: letras repetidas en %d menús" % (codigo, len(problemas)))
            for menu, etiquetas in sorted(problemas.items()):
                print("   %s: %s" % (menu, ", ".join(etiquetas)))
        else:
            print("%s: ninguna letra de acceso repetida." % codigo)
    return 1 if problemas_totales else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
