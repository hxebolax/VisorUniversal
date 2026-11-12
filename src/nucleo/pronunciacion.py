# -*- coding: utf-8 -*-
"""Diccionario de pronunciación: cómo se dice cada nombre.

Una saga de fantasía está llena de nombres propios inventados, y la voz del
sistema los destroza uno por uno.  Con un libro de setecientas páginas eso deja
de ser una anécdota y se vuelve agotador: el mismo nombre mal dicho aparece
cuatrocientas veces.

La solución es una tabla de sustituciones que se aplica **justo antes de mandar
el texto a la voz**, y solo ahí: el libro no se toca, el texto que se ve y se
copia sigue siendo el del autor, y buscar sigue encontrando lo que está escrito.
Solo cambia lo que se oye.

Hay dos tablas y se aplican las dos, primero la del libro:

* **La del libro**, que es donde van los nombres de esa saga concreta.  Se
  guarda junto a los marcadores, así que vuelve al abrirlo otra vez.
* **La general**, para lo que se repite en todos: siglas, símbolos, palabras
  extranjeras de uso corriente.

Cada regla puede pedir **palabra completa**, que es lo que casi siempre se
quiere: sin eso, cambiar «Ana» por «Anna» convertiría «manana» en «mAnnana».
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from .idioma import _
from .registro import obtener_registro

log = obtener_registro(__name__)

#: Tope de reglas por tabla.  Cada una es una expresión regular que se aplica a
#: cada frase; con unos cientos no se nota, con decenas de miles sí.  El tope
#: está para que un archivo de configuración estropeado no vuelva la lectura
#: lentísima sin que se entienda por qué.
MAXIMO = 500


@dataclass
class Regla:
    """Una sustitución: qué se escribe y cómo hay que decirlo."""

    buscar: str
    decir: str
    palabra_completa: bool = True
    distingue_mayusculas: bool = False

    def como_dict(self) -> dict[str, Any]:
        """Representación para guardar en JSON."""
        return {
            "buscar": self.buscar,
            "decir": self.decir,
            "palabra": self.palabra_completa,
            "mayusculas": self.distingue_mayusculas,
        }

    @classmethod
    def desde_dict(cls, datos: dict[str, Any]) -> "Regla":
        """Reconstruye una regla a partir del JSON."""
        return cls(
            buscar=str(datos.get("buscar", "")),
            decir=str(datos.get("decir", "")),
            palabra_completa=bool(datos.get("palabra", True)),
            distingue_mayusculas=bool(datos.get("mayusculas", False)),
        )

    def valida(self) -> bool:
        """Indica si la regla sirve para algo.

        Se exige que haya algo que buscar; que lo que se dice esté vacío es
        legítimo: así se silencian los adornos que el conversor no ha sabido
        quitar.
        """
        return bool(self.buscar.strip())

    def descripcion(self) -> str:
        """Cómo se enseña la regla en la lista."""
        if self.decir.strip():
            texto = _("«%(buscar)s» se dice «%(decir)s»") % {
                "buscar": self.buscar, "decir": self.decir}
        else:
            texto = _("«%s» no se dice") % self.buscar
        detalles = []
        if self.palabra_completa:
            detalles.append(_("palabra completa"))
        if self.distingue_mayusculas:
            detalles.append(_("distingue mayúsculas"))
        return "%s (%s)" % (texto, ", ".join(detalles)) if detalles else texto


class Tabla:
    """Un conjunto de reglas ya compiladas y listas para aplicar.

    Las expresiones regulares se compilan **una vez** al construir la tabla y no
    en cada frase: leyendo un libro entero, ese detalle es la diferencia entre
    que se note y que no.
    """

    def __init__(self, reglas: Iterable[Regla] = ()) -> None:
        self.reglas: list[Regla] = [r for r in reglas if r.valida()][:MAXIMO]
        self._compiladas: list[tuple[re.Pattern, str]] = []
        self._compilar()

    def _compilar(self) -> None:
        """Prepara las expresiones regulares de todas las reglas."""
        self._compiladas = []
        for regla in self.reglas:
            patron = re.escape(regla.buscar.strip())
            if regla.palabra_completa:
                # \b no sirve cuando lo buscado empieza o acaba en un signo
                # («D.ª», «S.A.»): ahí no hay frontera de palabra y la regla no
                # se dispararía nunca.  Se pone solo donde tiene sentido.
                if regla.buscar[:1].isalnum():
                    patron = r"\b" + patron
                if regla.buscar[-1:].isalnum():
                    patron = patron + r"\b"
            banderas = 0 if regla.distingue_mayusculas else re.IGNORECASE
            try:
                self._compiladas.append((re.compile(patron, banderas), regla.decir))
            except re.error as error:
                log.warning("Regla de pronunciación imposible de compilar (%s): %s",
                            regla.buscar, error)

    def __len__(self) -> int:
        return len(self.reglas)

    def __bool__(self) -> bool:
        return bool(self._compiladas)

    def aplicar(self, texto: str) -> str:
        """Devuelve el texto con las sustituciones hechas.

        Las reglas se aplican **en orden**, de modo que una posterior puede
        actuar sobre lo que dejó la anterior.  Es lo que permite escribir
        primero la excepción y después la regla general.
        """
        if not texto or not self._compiladas:
            return texto
        for patron, reemplazo in self._compiladas:
            # Se escapa la barra invertida del reemplazo: sin eso, decir que
            # algo se pronuncia «\1» haría que re lo tomara por una referencia
            # a un grupo y reventara la lectura.
            texto = patron.sub(reemplazo.replace("\\", r"\\"), texto)
        return texto


#: Tabla vacía compartida, para no crear una por frase cuando no hay reglas.
VACIA = Tabla()


def desde_lista(datos: Any) -> list[Regla]:
    """Convierte lo guardado en JSON en una lista de reglas."""
    if not isinstance(datos, list):
        return []
    reglas = []
    for elemento in datos[:MAXIMO]:
        if isinstance(elemento, dict):
            regla = Regla.desde_dict(elemento)
            if regla.valida():
                reglas.append(regla)
    return reglas


def como_lista(reglas: Iterable[Regla]) -> list[dict[str, Any]]:
    """Convierte una lista de reglas en algo que se pueda guardar."""
    return [regla.como_dict() for regla in reglas if regla.valida()]


def generales(configuracion) -> list[Regla]:
    """Reglas que se aplican a todos los documentos."""
    return desde_lista(configuracion.obtener("pronunciacion_general", []))


def guardar_generales(configuracion, reglas: Iterable[Regla]) -> None:
    """Guarda las reglas generales."""
    configuracion.establecer("pronunciacion_general", como_lista(reglas))


def del_documento(configuracion, ruta: str) -> list[Regla]:
    """Reglas propias de un documento."""
    if not ruta:
        return []
    return desde_lista(configuracion.datos_de(ruta).pronunciacion)


def guardar_del_documento(configuracion, ruta: str, reglas: Iterable[Regla]) -> None:
    """Guarda las reglas propias de un documento."""
    if not ruta:
        return
    configuracion.datos_de(ruta).pronunciacion = como_lista(reglas)


def tabla_para(configuracion, ruta: str) -> Tabla:
    """Construye la tabla que hay que aplicar a un documento.

    Van primero las del libro y después las generales: así una regla del libro
    puede afinar un nombre que la general dejaría de otra manera, que es el
    orden en el que uno espera que manden.
    """
    if not bool(configuracion.obtener("pronunciacion_activa", True)):
        return VACIA
    reglas = del_documento(configuracion, ruta) + generales(configuracion)
    return Tabla(reglas) if reglas else VACIA
