# -*- coding: utf-8 -*-
"""Busca los nombres rotos que Python no descubre hasta ejecutar esa línea.

``compileall`` comprueba la sintaxis y no ve nada de esto: un nombre que no
existe solo da la cara cuando alguien pasa justo por ahí, que puede ser meses
después y en el ordenador de otro.  Estos tres han aparecido de verdad en este
programa:

1. **Usar ``_`` como variable de descarte.**  Escribir ``_, tipo = pareja`` o
   ``for _ in range(20)`` convierte ``_`` en una variable **local a toda la
   función**, incluidas las líneas de más arriba.  A partir de ahí, cualquier
   ``_("...")`` de esa misma función revienta con ``UnboundLocalError`` o con
   ``TypeError: 'str' object is not callable``.

2. **Llamar a ``_()`` sin haberla importado**, que da ``NameError``.

3. **Cualquier otro nombre global que no exista**: una constante que se usa y
   no se importa, una función que se renombró en un sitio y no en otro.

Se ejecuta así::

    python herramientas/revisar_textos.py

Devuelve 1 si encuentra algo, para poder encadenarlo con otras comprobaciones.
"""

from __future__ import annotations

import ast
import builtins
import io
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FUENTE = RAIZ / "src"


def _asignaciones_locales(funcion: ast.AST) -> set[str]:
    """Nombres que la función asigna en su propio ámbito.

    Se excluyen a propósito las comprensiones y las funciones anidadas: tienen
    ámbito propio, así que un ``_`` dentro de ellas no tapa nada de fuera.
    """
    nombres: set[str] = set()

    def recorrer(nodo: ast.AST) -> None:
        """Baja por el árbol sin entrar en los ámbitos que son independientes."""
        for hijo in ast.iter_child_nodes(nodo):
            if isinstance(hijo, (ast.ListComp, ast.SetComp, ast.DictComp,
                                 ast.GeneratorExp, ast.Lambda,
                                 ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
                continue
            if isinstance(hijo, ast.Name) and isinstance(hijo.ctx, ast.Store):
                nombres.add(hijo.id)
            recorrer(hijo)

    recorrer(funcion)
    return nombres


def _llama_a_traducir(nodo: ast.AST) -> bool:
    """Si en algún punto de este nodo se llama a ``_()``."""
    for hijo in ast.walk(nodo):
        if (isinstance(hijo, ast.Call) and isinstance(hijo.func, ast.Name)
                and hijo.func.id == "_"):
            return True
    return False


def revisar(ruta: Path) -> list[str]:
    """Revisa un archivo y devuelve los problemas encontrados."""
    try:
        arbol = ast.parse(io.open(ruta, encoding="utf-8").read(), filename=str(ruta))
    except SyntaxError as error:
        return ["%s:%s  no se puede analizar: %s" % (ruta, error.lineno, error.msg)]

    problemas = []
    relativa = ruta.relative_to(RAIZ).as_posix()

    # -- 1. ¿se llama a _() sin importarla? ----------------------------------
    if _llama_a_traducir(arbol):
        importada = False
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ImportFrom):
                if any(alias.name == "_" or alias.asname == "_" for alias in nodo.names):
                    importada = True
                    break
            elif isinstance(nodo, ast.FunctionDef) and nodo.name == "_":
                importada = True
                break
        if not importada:
            problemas.append(
                "%s  llama a _() pero no la importa "
                "(añade «from nucleo.idioma import _»)" % relativa)

    # -- 2. ¿alguna función usa «_» como variable y además traduce? ----------
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if "_" in _asignaciones_locales(nodo) and _llama_a_traducir(nodo):
            problemas.append(
                "%s:%d  la función %s() usa «_» como variable y también para traducir: "
                "renombra la variable" % (relativa, nodo.lineno, nodo.name))

    # -- 3. ¿se usa algún nombre global que no existe? -----------------------
    for nombre, linea in _nombres_sueltos(arbol):
        problemas.append("%s:%d  usa «%s» y no está definido ni importado"
                         % (relativa, linea, nombre))
    return problemas


def _nombres_definidos(arbol: ast.Module) -> set[str]:
    """Todo lo que un módulo define o importa en su propio ámbito."""
    definidos: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Import, ast.ImportFrom)):
            for alias in nodo.names:
                definidos.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(nodo, ast.Name) and isinstance(nodo.ctx, ast.Store):
            definidos.add(nodo.id)
        elif isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            definidos.add(nodo.name)
        elif isinstance(nodo, ast.arg):
            definidos.add(nodo.arg)
        elif isinstance(nodo, ast.ExceptHandler) and nodo.name:
            definidos.add(nodo.name)
        elif isinstance(nodo, (ast.Global, ast.Nonlocal)):
            definidos.update(nodo.names)
    return definidos


def _nombres_sueltos(arbol: ast.Module) -> list[tuple[str, int]]:
    """Nombres que se leen y que el módulo no define, importa ni hereda.

    No pretende ser un analizador completo —para eso están las herramientas de
    verdad— sino cazar el descuido corriente: usar una constante en un módulo
    y olvidarse de importarla en otro.  Se comparan solo los nombres que no
    están en ningún sitio, de modo que un falso positivo es muy improbable.
    """
    definidos = _nombres_definidos(arbol)
    sueltos: list[tuple[str, int]] = []
    vistos: set[str] = set()
    for nodo in ast.walk(arbol):
        if not (isinstance(nodo, ast.Name) and isinstance(nodo.ctx, ast.Load)):
            continue
        if nodo.id in definidos or nodo.id in _INTEGRADOS or nodo.id in vistos:
            continue
        vistos.add(nodo.id)
        sueltos.append((nodo.id, nodo.lineno))
    return sueltos


#: Todo lo que Python trae puesto y que por tanto nunca hay que importar.  Se
#: pide al módulo ``builtins`` y no a ``__builtins__``: esa variable es el
#: módulo solo en el archivo que se ejecuta, y un diccionario en todos los
#: demás, de modo que ``dir()`` sobre ella devolvería los métodos de un
#: diccionario y daría por rotos ``len``, ``sorted`` o ``Exception``.
_INTEGRADOS = set(dir(builtins)) | {
    "__file__", "__name__", "__doc__", "__package__", "__builtins__", "__spec__",
    "__debug__", "__loader__", "__path__", "self", "cls",
}


def main() -> int:
    """Revisa todo el código fuente."""
    problemas: list[str] = []
    revisados = 0
    for ruta in sorted(FUENTE.rglob("*.py")):
        if "__pycache__" in ruta.parts:
            continue
        revisados += 1
        problemas.extend(revisar(ruta))

    print("Archivos revisados: %d" % revisados)
    if not problemas:
        print("Sin problemas: no hay ningún nombre roto.")
        return 0
    print()
    print("PROBLEMAS (%d):" % len(problemas))
    for problema in problemas:
        print("  ", problema)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
