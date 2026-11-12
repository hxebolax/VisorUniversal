# -*- coding: utf-8 -*-
"""Perfiles de lectura: juegos de ajustes con nombre.

No se lee igual una novela que un manual técnico.  Con la novela uno quiere la
voz cómoda, deprisa, sin sonidos que interrumpan y sin las tablas volcadas en el
texto; con el manual quiere lo contrario: despacio, con todos los sonidos para
enterarse de dónde hay una tabla o un código, y las descripciones de las figuras
leídas al pasar.

Cambiar eso a mano son ocho ajustes repartidos por cuatro pestañas, así que en
la práctica no se cambia: uno se queda con lo que tenga puesto y lee peor la
mitad de las veces.  Un perfil guarda los ocho de una vez y se cambia de uno a
otro con dos pulsaciones.

**Solo se guardan los ajustes que cambian según lo que se lee.**  El idioma de
la interfaz, el proveedor de IA o las claves API no van en un perfil: no
dependen del libro, y meterlos ahí sería una forma cómoda de perderlos.
"""

from __future__ import annotations

from typing import Any

from .idioma import _

#: Ajustes que guarda un perfil.  Son los que cambian según lo que se lee, y
#: solo esos: lo demás vale igual para todos los documentos.
AJUSTES = (
    # --- la voz ------------------------------------------------------------
    "voz_nombre",
    "voz_rapidez",
    "voz_volumen",
    "voz_mover_cursor",
    "voz_resaltar_frase",
    "voz_leer_descripciones",
    # --- los sonidos --------------------------------------------------------
    "sonidos_activados",
    "sonidos_volumen",
    "sonidos_solo_al_navegar",
    # --- cómo se presenta el texto -------------------------------------------
    "ajuste_de_linea",
    "mostrar_formato",
    "tablas_en_linea",
    # --- las grabaciones DAISY ------------------------------------------------
    "daisy_velocidad",
    "daisy_volumen",
    "daisy_mover_cursor",
    # --- la inteligencia artificial --------------------------------------------
    # Solo el prompt preferido: una lámina de un manual de botánica no se
    # describe como la ilustración de una novela.  El proveedor y las claves no
    # son cosa del perfil.
    "ia_prompt_preferido",
)

#: Ajustes cuyo cambio obliga a volver a convertir el documento.  Se avisa al
#: aplicar un perfil que los toque, en vez de dejar el libro a medio camino
#: entre dos formas de presentarlo.
CAMBIAN_EL_TEXTO = ("tablas_en_linea", "mostrar_formato")

#: Clave con la que se guardan los perfiles en las preferencias.
AJUSTE = "perfiles"

#: Nombre del perfil que está puesto.
AJUSTE_ACTIVO = "perfil_activo"

#: Tope de perfiles.  Más que esto deja de ser una lista que se recorre de oído.
MAXIMO = 30


def sugeridos() -> dict[str, dict[str, Any]]:
    """Perfiles de ejemplo, para no empezar con la lista vacía.

    No se crean solos: se ofrecen desde la ventana de perfiles con un botón,
    porque llenar la configuración de alguien con cosas que no ha pedido es
    justo lo que no hay que hacer.  Están para enseñar de qué va esto.
    """
    return {
        _("Novela"): {
            "voz_rapidez": 60,
            "voz_leer_descripciones": False,
            "sonidos_activados": True,
            "sonidos_solo_al_navegar": True,
            "tablas_en_linea": False,
            "mostrar_formato": False,
            "ia_prompt_preferido": "novela",
        },
        _("Libro técnico"): {
            "voz_rapidez": 45,
            "voz_leer_descripciones": True,
            "sonidos_activados": True,
            "sonidos_solo_al_navegar": False,
            "tablas_en_linea": False,
            "mostrar_formato": True,
            "ia_prompt_preferido": "tecnico",
        },
        _("Escuchar sin mirar"): {
            "voz_rapidez": 55,
            "voz_mover_cursor": False,
            "voz_resaltar_frase": False,
            "voz_leer_descripciones": True,
            "sonidos_activados": True,
            "sonidos_solo_al_navegar": True,
            "ajuste_de_linea": False,
        },
    }


def leer(configuracion) -> dict[str, dict[str, Any]]:
    """Todos los perfiles guardados, como ``{nombre: {ajuste: valor}}``."""
    guardados = configuracion.obtener(AJUSTE, {}) or {}
    if not isinstance(guardados, dict):
        return {}
    limpios: dict[str, dict[str, Any]] = {}
    for nombre, valores in list(guardados.items())[:MAXIMO]:
        if isinstance(valores, dict) and str(nombre).strip():
            # Se filtra por la lista de ajustes conocidos: un perfil guardado
            # por una versión anterior puede traer ajustes que ya no existen, y
            # devolverlos tal cual los volvería a escribir en la configuración.
            limpios[str(nombre)] = {clave: valores[clave]
                                    for clave in AJUSTES if clave in valores}
    return limpios


def nombres(configuracion) -> list[str]:
    """Nombres de los perfiles, ordenados como se van a enseñar."""
    return sorted(leer(configuracion), key=str.lower)


def activo(configuracion) -> str:
    """Nombre del perfil que está puesto, o cadena vacía."""
    nombre = str(configuracion.obtener(AJUSTE_ACTIVO, "") or "")
    return nombre if nombre in leer(configuracion) else ""


def capturar(configuracion) -> dict[str, Any]:
    """Se queda con los ajustes actuales, para guardarlos como perfil."""
    return {clave: configuracion.obtener(clave) for clave in AJUSTES}


def guardar(configuracion, nombre: str, valores: dict[str, Any] | None = None) -> bool:
    """Guarda un perfil con los ajustes de ahora, o con los que se le pasen.

    :return: ``False`` si no cabe ninguno más o el nombre está vacío.
    """
    nombre = (nombre or "").strip()
    if not nombre:
        return False
    todos = leer(configuracion)
    if nombre not in todos and len(todos) >= MAXIMO:
        return False
    todos[nombre] = valores if valores is not None else capturar(configuracion)
    configuracion.establecer(AJUSTE, todos)
    configuracion.establecer(AJUSTE_ACTIVO, nombre)
    return True


def borrar(configuracion, nombre: str) -> None:
    """Quita un perfil."""
    todos = leer(configuracion)
    todos.pop(nombre, None)
    configuracion.establecer(AJUSTE, todos)
    if activo(configuracion) == nombre:
        configuracion.establecer(AJUSTE_ACTIVO, "")


def aplicar(configuracion, nombre: str) -> list[str]:
    """Pone los ajustes de un perfil.

    :return: Los ajustes que han cambiado **y que obligan a volver a abrir el
             documento**, para que quien llama pueda preguntarlo.  Lista vacía
             si no hace falta.
    """
    valores = leer(configuracion).get(nombre)
    if not valores:
        return []
    hay_que_reabrir = []
    for clave, valor in valores.items():
        if clave in CAMBIAN_EL_TEXTO and configuracion.obtener(clave) != valor:
            hay_que_reabrir.append(clave)
        configuracion.establecer(clave, valor)
    configuracion.establecer(AJUSTE_ACTIVO, nombre)
    return hay_que_reabrir


def descripcion(valores: dict[str, Any]) -> str:
    """Frase corta con lo más característico de un perfil.

    Sirve para la lista: leer «Novela» y nada más no dice si es el que uno
    quiere.  Se enseñan los tres o cuatro ajustes que de verdad se notan.
    """
    partes = []
    if "voz_rapidez" in valores:
        partes.append(_("voz al %d") % int(valores["voz_rapidez"] or 0))
    if "sonidos_activados" in valores:
        partes.append(_("sonidos sí") if valores["sonidos_activados"]
                      else _("sonidos no"))
    if valores.get("sonidos_solo_al_navegar"):
        partes.append(_("solo al saltar"))
    if valores.get("voz_leer_descripciones"):
        partes.append(_("lee las imágenes"))
    if valores.get("voz_resaltar_frase"):
        partes.append(_("resalta la frase"))
    if valores.get("mostrar_formato"):
        partes.append(_("con negrita y cursiva"))
    return ", ".join(partes) or _("sin nada característico")
