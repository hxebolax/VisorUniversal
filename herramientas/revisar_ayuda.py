# -*- coding: utf-8 -*-
"""Comprueba que todo control tiene su explicación de Control+F1.

Una explicación que se escribe una vez y no se vuelve a mirar envejece sola: se
añade un botón, se le olvida a alguien la entrada del catálogo, y quien pulsa
Control+F1 encima oye «este control no tiene explicación propia». Con la vista
eso se disimula —el rótulo, el grupo, lo que hay alrededor—; sin ella, ese
control es un nombre suelto y nada más.

Así que la comprobación se hace a máquina y se hace siempre. Se recorren todas
las ventanas del programa, se buscan los controles que cada una guarda en un
atributo propio y se mira si están en :mod:`interfaz.ayuda_control`, con la
clave de su ventana o con la suelta.

**No se abre ninguna ventana**: se lee el código con :mod:`ast`. Es lo que
permite pasarlo en cualquier sitio y en un segundo, y lo que evita que la
comprobación dependa de que wxPython pueda dibujar.

Uso::

    python herramientas/revisar_ayuda.py

Devuelve 0 si no falta nada y 1 si falta algo, para poder encadenarlo.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from nucleo import idioma            # noqa: E402
from nucleo import registro          # noqa: E402
from nucleo import rutas             # noqa: E402

#: Ventanas que no enganchan Control+F1, y por qué.  Están escritas aquí y no
#: simplemente omitidas para que se vea que es una decisión y no un olvido.
SIN_ENGANCHE = {
    "DialogoCapturarTecla": "recoge cualquier tecla que se pulse, Control+F1 incluida",
    "DialogoAyudaOpcion": "es la propia ventana de ayuda; se abriría sobre sí misma",
}

#: Nombres que no piden explicación: son estructura de la ventana o botones que
#: dicen lo que hacen con su propio rótulo.
OBVIOS = {"boton_cancelar", "boton_cerrar", "boton_aceptar", "barra", "estado",
          "titulo", "avance", "resumen", "sizer", "contenedor", "pie", "fila"}

#: Qué llamadas crean un control que el usuario recorre con el tabulador.
CREADORES = {"TextCtrl", "CheckBox", "Choice", "ComboBox", "SpinCtrl", "Slider",
             "ListBox", "CheckListBox", "RadioBox", "RadioButton", "ListCtrl",
             "TreeCtrl", "FilePickerCtrl", "DirPickerCtrl", "Button",
             "ListaAccesible", "SearchCtrl", "SpinCtrlDouble", "Notebook",
             "ListaCasillas"}

#: Envoltorios que crean un control por dentro y devuelven ese control.
ENVOLTORIOS = ("fila_etiquetada", "etiquetar")


def archivos() -> list[Path]:
    """Los módulos donde viven las ventanas del programa."""
    # No todas las ventanas viven en «dialogos»: unas cuantas están al lado del
    # código que las usa. Se nombran una a una a propósito, para que añadir un
    # módulo con una ventana dentro obligue a acordarse de esto.
    return sorted(list((RAIZ / "src/interfaz/dialogos").glob("*.py"))
                  + [RAIZ / "src/interfaz/temporizador.py",
                     RAIZ / "src/interfaz/reproductor_daisy.py",
                     RAIZ / "src/interfaz/lectura_voz.py",
                     RAIZ / "src/interfaz/bienvenida.py"])


def _creador(nodo) -> str:
    """La clase de control que crea esta expresión, si es que crea alguno."""
    if not isinstance(nodo, ast.Call):
        return ""
    objetivo = nodo.func
    nombre = ""
    if isinstance(objetivo, ast.Attribute):
        nombre = objetivo.attr
    elif isinstance(objetivo, ast.Name):
        nombre = objetivo.id
    if nombre in CREADORES:
        return nombre
    if nombre in ENVOLTORIOS:
        # El control de verdad está dentro, en un lambda o en otra llamada.
        for hijo in ast.walk(nodo):
            if hijo is nodo:
                continue
            dentro = _creador(hijo)
            if dentro:
                return dentro
        return "compuesto"
    return ""


def _ventanas(arbol):
    """Las clases que son una ventana del programa."""
    for clase in ast.walk(arbol):
        if not isinstance(clase, ast.ClassDef):
            continue
        bases = [ast.unparse(base) for base in clase.bases]
        if any("Dialog" in base or "Frame" in base for base in bases):
            yield clase


def _controles(clase) -> list[str]:
    """Los controles que la ventana guarda en un atributo propio."""
    nombres = []
    for nodo in ast.walk(clase):
        if not isinstance(nodo, ast.Assign):
            continue
        for destino in nodo.targets:
            if (isinstance(destino, ast.Attribute)
                    and isinstance(destino.value, ast.Name)
                    and destino.value.id == "self"
                    and destino.attr not in OBVIOS
                    and _creador(nodo.value)):
                nombres.append(destino.attr)
    return sorted(set(nombres))


def revisar() -> tuple[int, list[str], dict[str, list[str]]]:
    """Devuelve ``(ventanas, sin enganche, controles sin explicación)``."""
    rutas.preparar_estructura()
    registro.iniciar("ERROR", "revisar_ayuda")
    idioma.instalar("es")
    from interfaz.ayuda_control import ayudas

    catalogo = set(ayudas())
    cuantas = 0
    sin_enganche: list[str] = []
    faltan: dict[str, list[str]] = {}
    for archivo in archivos():
        fuente = archivo.read_text(encoding="utf-8")
        arbol = ast.parse(fuente)
        engancha = "ayuda_opcion.enganchar(self)" in fuente
        for clase in _ventanas(arbol):
            cuantas += 1
            if not engancha and clase.name not in SIN_ENGANCHE:
                sin_enganche.append("%s.%s" % (archivo.name, clase.name))
            pendientes = [nombre for nombre in _controles(clase)
                          if nombre not in catalogo
                          and "%s.%s" % (clase.name, nombre) not in catalogo]
            if pendientes:
                faltan["%s.%s" % (archivo.name, clase.name)] = pendientes
    return cuantas, sin_enganche, faltan


def main() -> int:
    cuantas, sin_enganche, faltan = revisar()
    print("Ventanas revisadas: %d" % cuantas)
    if SIN_ENGANCHE:
        print("Sin Control+F1 a propósito:")
        for nombre, motivo in sorted(SIN_ENGANCHE.items()):
            print("   %-28s %s" % (nombre, motivo))
    if sin_enganche:
        print("\nVentanas donde falta enganchar Control+F1 (%d):" % len(sin_enganche))
        for nombre in sin_enganche:
            print("   ", nombre)
    if faltan:
        cuantos = sum(len(lista) for lista in faltan.values())
        print("\nControles sin explicación (%d):" % cuantos)
        for ventana in sorted(faltan):
            print("   %-42s %s" % (ventana, " ".join(faltan[ventana])))
    if sin_enganche or faltan:
        return 1
    print("Sin problemas: todos los controles tienen su explicación de Control+F1.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
