# -*- coding: utf-8 -*-
"""Comprueba que lo que un motor de voz promete es lo que hace.

Un paquete de voz declara sus ajustes en un archivo y los usa en otro, y nada
obliga a que coincidan. Es fácil que se separen: se añade un ajuste al manifiesto
y se olvida leerlo, o se lee uno que nadie declaró y por tanto nadie puede tocar.
Las dos cosas fallan calladas —el ajuste está ahí y no hace nada— y solo se
descubren usándolo y sospechando.

Esto lo mira por las cuatro vías en las que puede torcerse:

1. **Ajustes declarados que el motor no lee.** Salen en la ventana, se pueden
   cambiar, y no hacen nada.
2. **Ajustes que el motor lee y nadie declaró.** Existen, funcionan, y no hay
   forma de tocarlos.
3. **Opciones que no están.** Una lista que ofrece siete calidades cuando las
   voces solo tienen una. Se compara lo declarado con lo que el propio motor
   dice tener, si sabe decirlo.
4. **El contrato**: que estén los doce métodos y las tres propiedades, que
   arranque, y que ofrezca alguna voz.

Uso::

    python herramientas/revisar_motores.py            # los instalados
    python herramientas/revisar_motores.py vocalizer  # solo uno
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from nucleo import motores_voz                         # noqa: E402

#: Claves que el visor le pasa al motor sin que este las declare, porque son
#: suyas y no del motor.  Que un motor las lea es correcto.
DEL_VISOR = {"_voz_elegida", "velocidad", "volumen", "tono"}


def textos_de(carpeta: Path) -> set:
    """Todas las cadenas que aparecen en el código de un motor.

    Se miran **todos** sus archivos y no solo el adaptador: los motores que
    vienen de otra aplicación pasan los ajustes enteros a un proveedor, y quien
    lee la clave es ese, en otro archivo.

    Se sacan del árbol de sintaxis y no con una búsqueda de texto: así no cuenta
    lo que esté dentro de un comentario, que es donde suelen quedarse las
    menciones de un ajuste que ya se quitó.
    """
    salida: set = set()
    for fuente in sorted(carpeta.rglob("*.py")):
        try:
            arbol = ast.parse(fuente.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
                salida.add(nodo.value)
    return salida


def leidas_por(carpeta: Path) -> set:
    """Qué claves lee el adaptador de un motor con nombre propio.

    Solo del adaptador y solo las que se leen a las claras
    —``self._ajustes.get("algo")``—, porque es lo único que se puede afirmar sin
    equivocarse.  Sirve para lo contrario que :func:`textos_de`: encontrar
    ajustes que el motor usa y nadie declaró.
    """
    claves: set = set()
    fuente = carpeta / "motor.py"
    try:
        arbol = ast.parse(fuente.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return claves
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call) or not isinstance(nodo.func, ast.Attribute):
            continue
        if nodo.func.attr != "get" or not nodo.args:
            continue
        objeto = nodo.func.value
        nombre = getattr(objeto, "attr", None) or getattr(objeto, "id", None)
        if nombre not in ("_ajustes", "ajustes"):
            continue
        primero = nodo.args[0]
        if isinstance(primero, ast.Constant) and isinstance(primero.value, str):
            claves.add(primero.value)
    return claves


def revisar(motor, carpeta: Path) -> list:
    """Todo lo que esté mal en un motor, dicho para leerlo en voz alta."""
    problemas = []
    declarados = {ajuste.clave for ajuste in motor.ajustes}

    if (carpeta / "motor.py").is_file():
        aparecen = textos_de(carpeta)
        for clave in sorted(declarados - aparecen):
            problemas.append(
                "el ajuste «%s» se declara y no aparece en su código: sale en "
                "la ventana y no hace nada" % clave)
        for clave in sorted(leidas_por(carpeta) - declarados - DEL_VISOR):
            problemas.append(
                "el motor lee «%s» y no está declarado: funciona pero no hay "
                "forma de tocarlo" % clave)
    else:
        problemas.append("no se encuentra su código en %s" % carpeta)

    # Lo que hay que construir para lo demás.  Un motor que no arranca no es un
    # fallo de esta revisión: puede que le falten sus voces.
    try:
        sintetizador, aviso = motores_voz.crear(motor.identificador, {})
    except Exception as error:
        problemas.append("no se ha podido construir: %s" % error)
        return problemas
    try:
        for nombre in motores_voz.CONTRATO:
            if not callable(getattr(sintetizador, nombre, None)):
                problemas.append("le falta el método «%s» del contrato" % nombre)
        for nombre in motores_voz.PROPIEDADES:
            if not hasattr(sintetizador, nombre):
                problemas.append("le falta la propiedad «%s»" % nombre)

        if not getattr(sintetizador, "disponible", False):
            return problemas + ["no está disponible%s"
                                % (": %s" % aviso if aviso else "")]

        cuantas = len(list(sintetizador.voces()))
        if not cuantas:
            problemas.append("no ofrece ninguna voz")

        # Y las listas: lo declarado contra lo que el propio motor dice tener.
        preguntar = getattr(sintetizador, "opciones_de", None)
        if callable(preguntar):
            for ajuste in motor.ajustes:
                if ajuste.clase != "lista":
                    continue
                try:
                    suyas = preguntar(ajuste.clave)
                except Exception as error:
                    problemas.append("«opciones_de» ha fallado con «%s»: %s"
                                     % (ajuste.clave, error))
                    continue
                if suyas is None:
                    # El motor no sabe decir las de este ajuste, así que manda
                    # el manifiesto y no hay nada que comparar.
                    continue
                if not suyas:
                    problemas.append(
                        "el ajuste «%s» se queda sin ninguna opción: el motor "
                        "dice que no tiene" % ajuste.clave)
                # Que el manifiesto declare de más no es un fallo: es el
                # respaldo para cuando el motor no ha podido arrancar y decir
                # las suyas.  Lo que sí lo sería es que el motor no ofreciera
                # ninguna, y eso ya está mirado arriba.
    finally:
        cerrar = getattr(sintetizador, "cerrar", None)
        if callable(cerrar):
            try:
                cerrar()
            except Exception:
                pass
    return problemas


def main(argumentos) -> int:
    pedidos = [uno for uno in argumentos if not uno.startswith("-")]
    motores = [motor for motor in motores_voz.instalados()
               if not pedidos or motor.identificador in pedidos]
    if not motores:
        print("No hay ningún motor instalado que revisar.")
        return 0

    total = 0
    for motor in motores:
        carpeta = RAIZ / "plugins_voz" / "fuentes" / motor.identificador
        problemas = revisar(motor, carpeta)
        estado = "%d avisos" % len(problemas) if problemas else "bien"
        print("%-16s %2d ajustes  %s" % (motor.identificador,
                                         len(motor.ajustes), estado))
        for uno in problemas:
            print("      - %s" % uno)
        total += len(problemas)

    print()
    if total:
        print("Hay %d cosas que mirar." % total)
        return 1
    print("Sin problemas: cada motor hace lo que su manifiesto dice.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
