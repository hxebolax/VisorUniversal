# -*- coding: utf-8 -*-
"""Revisa que cada opción se guarde, se cargue y sirva para algo.

El diálogo de Opciones tiene más de ochenta ajustes repartidos en trece
pestañas. Con esa cantidad, tres fallos son fáciles de cometer y difíciles de
ver, porque los tres dan un ajuste que **parece** funcionar:

1. **Se lee al abrir pero no se guarda al aceptar.** Se toca, se acepta, y a la
   vuelta está como estaba. Parece que el programa «no hace caso».
2. **Se guarda pero no se lee al abrir.** Peor: el diálogo se abre con el valor
   de fábrica y, al aceptar, **borra lo que había** sin que nadie lo pida.
3. **Se guarda y no lo lee nadie más.** Un ajuste que no hace nada. Es el más
   difícil de descubrir, porque no falla: simplemente no pasa nada, y quien lo
   activó supone que sí.

Los tres se pueden comprobar leyendo el código, y eso es lo que hace esta
herramienta. Lo que **no** comprueba es si un ajuste está en la pestaña que le
toca: eso es un juicio y hay que hacerlo mirando.

Uso::

    python herramientas/revisar_opciones.py
    python herramientas/revisar_opciones.py --todo   # también las que están bien
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SRC = RAIZ / "src"
DIALOGO = SRC / "interfaz" / "dialogos" / "opciones.py"
CONFIGURACION = SRC / "nucleo" / "configuracion.py"

#: Cómo se pide un ajuste.  No basta con ``obtener("x")``: hay ayudantes que
#: envuelven la llamada —``_ajuste("x")``, ``_claves_guardadas("x")``— y contarlos
#: como «nadie lo lee» daría avisos falsos justo en los ajustes mejor escritos.
LECTURAS = (
    r'obtener\(\s*"([a-z0-9_]+)"',
    r'_ajuste\(\s*"([a-z0-9_]+)"',
    r'_claves_guardadas\(\s*"([a-z0-9_]+)"',
    r'_texto_guardado\(\s*"([a-z0-9_]+)"',
)

#: Y cómo se guarda.
ESCRITURAS = (
    r'establecer\(\s*"([a-z0-9_]+)"',
)

#: Ajustes que el programa maneja con métodos propios y no con ``obtener``: los
#: libros recientes, los perfiles, el gasto de la IA.  Tienen su propia API en
#: la configuración porque son listas que se van modificando, no valores que se
#: leen y se escriben enteros.
CON_API_PROPIA = frozenset((
    "documentos_recientes", "perfiles", "perfil_activo", "ia_consumo",
))

#: Y los que se leen o se escriben **a través de una tabla**, con el nombre en
#: una variable: cada proveedor de IA tiene su clave y su lista de modelos, y el
#: código no los nombra uno a uno sino que los busca en un diccionario.  Es lo
#: correcto —evita cuatro copias del mismo bloque— y hace que buscarlos por su
#: nombre no los encuentre.
#:
#: Se declaran con su motivo en vez de afinar la búsqueda hasta cazarlos: una
#: herramienta que avisa de algo correcto deja de leerse.
POR_TABLA = {
    "ia_gemini_claves": "las lee servicio.py por su tabla de proveedores",
    "ia_anthropic_claves": "las lee servicio.py por su tabla de proveedores",
    "ia_openai_claves": "las lee servicio.py por su tabla de proveedores",
    "ia_gemini_modelos": "los guarda «obtener los modelos» por su tabla",
    "ia_anthropic_modelos": "los guarda «obtener los modelos» por su tabla",
    "ia_openai_modelos": "los guarda «obtener los modelos» por su tabla",
    "ia_local_modelos": "los guarda «obtener los modelos» por su tabla",
    "biblioteca_ficha_campos": "lo leen y lo guardan la ficha y su ventana de datos "
                               "por la constante AJUSTE_FICHA de biblioteca_ficha.py",
    "biblioteca_exportar_campos": "lo leen y lo guardan «Exportar fichas» y su ventana "
                                  "de datos por la constante AJUSTE_EXPORTAR",
}


def _encontrar(texto: str, patrones) -> set:
    salida: set = set()
    for patron in patrones:
        salida |= set(re.findall(patron, texto))
    return salida


def leer_todo() -> dict:
    """Junta de dónde sale y a dónde va cada ajuste."""
    dialogo = DIALOGO.read_text(encoding="utf-8")
    configuracion = CONFIGURACION.read_text(encoding="utf-8")
    inicio = configuracion.index("AJUSTES_POR_OMISION")
    fin = configuracion.index("\n}", inicio)
    declaradas = set(re.findall(r'^\s*"([a-z0-9_]+)":',
                                configuracion[inicio:fin], re.MULTILINE))

    usadas: set = set()
    for archivo in sorted(SRC.rglob("*.py")):
        if archivo.name in ("opciones.py", "configuracion.py"):
            continue
        usadas |= _encontrar(archivo.read_text(encoding="utf-8"), LECTURAS)

    return {
        "leidas": _encontrar(dialogo, LECTURAS),
        "escritas": _encontrar(dialogo, ESCRITURAS),
        "declaradas": declaradas,
        "usadas": usadas,
    }


def revisar() -> list:
    """Las pegas encontradas: ``[(clase, clave, explicación)]``."""
    datos = leer_todo()
    pegas = []

    for clave in sorted(datos["leidas"] - datos["escritas"] - set(POR_TABLA)):
        # Que se lea y no se escriba solo es pega si el diálogo es quien manda:
        # hay listas —los modelos de IA— que se rellenan solas al consultar al
        # servidor y que el diálogo únicamente enseña.
        pegas.append(("no se guarda", clave,
                      "el diálogo lo enseña pero no lo escribe al aceptar"))

    for clave in sorted(datos["escritas"] - datos["leidas"]):
        pegas.append(("no se carga", clave,
                      "se guarda pero el diálogo no lo lee al abrir: se "
                      "perdería lo que hubiera"))

    for clave in sorted((datos["leidas"] | datos["escritas"])
                        - datos["declaradas"] - set(POR_TABLA)):
        pegas.append(("sin valor de fábrica", clave,
                      "no está en AJUSTES_POR_OMISION"))

    for clave in sorted(datos["escritas"] - datos["usadas"] - CON_API_PROPIA
                        - set(POR_TABLA)):
        pegas.append(("no lo usa nadie", clave,
                      "se guarda y ningún otro módulo lo lee: el ajuste no "
                      "hace nada"))

    for clave in sorted(datos["declaradas"] - datos["usadas"]
                        - datos["escritas"] - datos["leidas"] - CON_API_PROPIA
                        - set(POR_TABLA)):
        pegas.append(("de fábrica y huérfano", clave,
                      "declarado y no lo lee ni lo escribe nadie"))
    return pegas


def main(argumentos: list) -> int:
    datos = leer_todo()
    print("Opciones: %d se leen en el diálogo, %d se guardan, %d declaradas de "
          "fábrica." % (len(datos["leidas"]), len(datos["escritas"]),
                        len(datos["declaradas"])))
    pegas = revisar()
    if not pegas:
        print("\nSin problemas: todas se guardan, se cargan y las usa alguien.")
        return 0
    por_clase: dict = {}
    for clase, clave, explicacion in pegas:
        por_clase.setdefault(clase, []).append((clave, explicacion))
    for clase, cuales in por_clase.items():
        print("\n=== %s (%d)" % (clase, len(cuales)))
        for clave, explicacion in cuales:
            print("   %-32s %s" % (clave, explicacion))
    print("\nTotal: %d." % len(pegas))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
