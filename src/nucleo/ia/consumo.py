# -*- coding: utf-8 -*-
"""Cuánto se lleva gastado con la inteligencia artificial.

Con una cuota gratuita, saber cuántas peticiones se han hecho **importa**: la
diferencia entre describir un libro entero y que a mitad deje de funcionar está
en enterarse a tiempo.  Y con una clave de pago, más todavía.

Se lleva la cuenta de tres cosas por proveedor: peticiones, unidades de texto
enviadas y recibidas —lo que los servicios llaman *tokens*— y fallos.  Los
servicios que informan de su gasto lo dicen en cada respuesta; los que no —un
modelo local, por ejemplo— dejan esos números a cero, y entonces lo que cuenta
es el número de peticiones.

**El dinero no se calcula.** Cada proveedor tiene sus precios, cambian con el
tiempo y son distintos por modelo: poner aquí una tarifa sería dar una cifra
falsa con aire de exacta.  Lo que se enseña es el consumo real, que es lo que
se puede comparar con lo que diga la web del proveedor.

Todo se guarda en las preferencias, así que sobrevive a cerrar el programa, y
se puede poner a cero cuando empieza un mes nuevo de cuota.
"""

from __future__ import annotations

from typing import Any

from ..idioma import _, _n

#: Clave con la que se guarda el contador en las preferencias.
AJUSTE = "ia_consumo"


def _vacio() -> dict[str, Any]:
    """Un contador recién puesto a cero."""
    return {"peticiones": 0, "entrada": 0, "salida": 0, "fallos": 0,
            "imagenes": 0, "preguntas": 0, "desde": ""}


def leer(configuracion) -> dict[str, dict[str, Any]]:
    """Devuelve el contador de todos los proveedores."""
    guardado = configuracion.obtener(AJUSTE, {}) or {}
    if not isinstance(guardado, dict):
        return {}
    return {str(clave): dict(_vacio(), **valor)
            for clave, valor in guardado.items() if isinstance(valor, dict)}


def de(configuracion, proveedor: str) -> dict[str, Any]:
    """Contador de un proveedor concreto."""
    return leer(configuracion).get(proveedor, _vacio())


def anotar(configuracion, proveedor: str, entrada: int = 0, salida: int = 0,
           clase: str = "", fallo: bool = False) -> None:
    """Suma una petición al contador.

    :param proveedor: Clave del proveedor (``gemini``, ``anthropic``...).
    :param entrada: Unidades de texto enviadas, si el servicio las dice.
    :param salida: Unidades de texto recibidas.
    :param clase: ``"imagen"`` o ``"pregunta"``, para poder distinguir en qué
                  se va la cuota: describir un libro entero y preguntarle cosas
                  gastan de forma muy distinta.
    :param fallo: Si la petición terminó en error.  Se cuentan aparte porque un
                  fallo también consume cuota en algunos servicios, y porque
                  muchos fallos seguidos son en sí mismos la información.
    """
    if not proveedor or proveedor == "off":
        return
    from datetime import date

    todos = leer(configuracion)
    contador = todos.get(proveedor) or _vacio()
    contador["peticiones"] += 1
    contador["entrada"] += max(0, int(entrada or 0))
    contador["salida"] += max(0, int(salida or 0))
    if fallo:
        contador["fallos"] += 1
    if clase == "imagen":
        contador["imagenes"] += 1
    elif clase == "pregunta":
        contador["preguntas"] += 1
    if not contador.get("desde"):
        contador["desde"] = date.today().isoformat()
    todos[proveedor] = contador
    configuracion.establecer(AJUSTE, todos)


def poner_a_cero(configuracion, proveedor: str = "") -> None:
    """Vacía el contador de un proveedor, o el de todos si no se dice cuál."""
    if not proveedor:
        configuracion.establecer(AJUSTE, {})
        return
    todos = leer(configuracion)
    todos.pop(proveedor, None)
    configuracion.establecer(AJUSTE, todos)


def _miles(numero: int) -> str:
    """Un número con sus puntos de millar, que de oído se entiende mejor."""
    return "{:,}".format(int(numero)).replace(",", ".")


def resumen(configuracion, proveedor: str, nombre: str = "") -> str:
    """Frase con lo que lleva gastado un proveedor.

    Está pensada para leerse en voz alta de una tirada, así que no lleva tablas
    ni abreviaturas: dice los números con palabras alrededor.
    """
    contador = de(configuracion, proveedor)
    peticiones = int(contador.get("peticiones", 0))
    if not peticiones:
        return _("%s: todavía no se ha hecho ninguna petición.") % (nombre or proveedor)

    partes = [_n("%s: %d petición", "%s: %d peticiones", peticiones)
              % (nombre or proveedor, peticiones)]
    detalle = []
    imagenes = int(contador.get("imagenes", 0))
    preguntas = int(contador.get("preguntas", 0))
    if imagenes:
        detalle.append(_n("%d imagen descrita", "%d imágenes descritas", imagenes) % imagenes)
    if preguntas:
        detalle.append(_n("%d pregunta", "%d preguntas", preguntas) % preguntas)
    fallos = int(contador.get("fallos", 0))
    if fallos:
        detalle.append(_n("%d fallo", "%d fallos", fallos) % fallos)
    if detalle:
        partes.append("(%s)" % ", ".join(detalle))

    entrada = int(contador.get("entrada", 0))
    salida = int(contador.get("salida", 0))
    if entrada or salida:
        partes.append(_("Texto: %(entrada)s unidades enviadas y %(salida)s recibidas.")
                      % {"entrada": _miles(entrada), "salida": _miles(salida)})
    desde = str(contador.get("desde", ""))
    if desde:
        partes.append(_("Desde el %s.") % desde)
    return " ".join(partes)


def resumen_completo(configuracion, nombres: dict[str, str]) -> str:
    """Lo gastado con cada proveedor que se haya llegado a usar.

    :param nombres: ``{clave: nombre visible}`` de los proveedores.
    """
    todos = leer(configuracion)
    usados = [clave for clave in todos if int(todos[clave].get("peticiones", 0))]
    if not usados:
        return _("Todavía no se ha hecho ninguna petición a la inteligencia artificial.")
    lineas = [resumen(configuracion, clave, nombres.get(clave, clave))
              for clave in sorted(usados)]
    lineas.append("")
    lineas.append(_(
        "El coste en dinero no se calcula: cada proveedor tiene sus precios, cambian con "
        "el tiempo y son distintos según el modelo. Estos números son los que puedes "
        "comparar con lo que diga la web de tu proveedor."))
    return "\n".join(lineas)
