# -*- coding: utf-8 -*-
"""Texto de presentación que se muestra cuando no hay ningún libro abierto.

En lugar de dejar la ventana vacía, el control de texto muestra un resumen de
lo que se puede hacer.  Como es texto normal dentro del mismo control de
lectura, se puede recorrer con las flechas y con las órdenes de lectura del
lector de pantalla, igual que un libro.

El resumen de teclas **no está escrito a mano**: se genera a partir de
:mod:`interfaz.atajos`, que es la misma tabla que interpreta las pulsaciones.
Así no puede quedarse desfasado respecto al comportamiento real.
"""

from __future__ import annotations

from interfaz import atajos
from nucleo.idioma import _
from version import NOMBRE


def _linea(tecla: str, descripcion: str) -> str:
    """Da formato a una fila de «tecla: qué hace»."""
    return "  %-22s %s" % (tecla, descripcion)


def texto_de_bienvenida(version: str = "") -> str:
    """Construye el texto de presentación completo.

    :param version: Versión del programa, para la primera línea.
    """
    lineas: list[str] = []
    # El nombre sale de version.py y en mayúsculas, como el resto del rótulo.
    # No se escribe aquí a mano: cambiarlo era cambiarlo en un sitio, y este se
    # quedó atrás la última vez.
    titulo = NOMBRE.upper() + (" %s" % version if version else "")
    lineas.append(titulo)
    lineas.append("=" * len(titulo))
    lineas.append("")
    lineas.append(_("Visor accesible de documentos, para usarlo con el teclado y con lector de pantalla."))
    lineas.append("")
    lineas.append(_("PARA EMPEZAR"))
    lineas.append(_linea("Control+O", _("Abrir un documento.")))
    lineas.append(_linea("Alt+A, R", _("Volver a abrir uno de los últimos documentos.")))
    lineas.append(_linea("", _("También puedes arrastrar un archivo hasta aquí.")))
    lineas.append("")
    lineas.append("LEER")
    lineas.append(_linea(_("Flechas arriba y abajo"), _("Párrafo anterior o siguiente.")))
    lineas.append(_linea(_("Re Pág y Av Pág"), _("Pantalla anterior o siguiente.")))
    lineas.append(_linea("Control+Inicio / Fin", _("Principio o final del documento.")))
    lineas.append(_linea(atajos.DONDE_ESTOY, _("Decir por dónde voy.")))
    lineas.append(_linea(atajos.REPETIR_ANUNCIO, _("Repetir el último aviso.")))
    lineas.append("")
    lineas.append(_("SALTAR DE UN ELEMENTO A OTRO (con Mayús, hacia atrás)"))
    for atajo in atajos.NAVEGACION:
        lineas.append(_linea(atajo.tecla, atajo.descripcion + " siguiente."))
    lineas.append(_linea(atajos.SECCION_SIGUIENTE, _("Capítulo siguiente.")))
    lineas.append(_linea(atajos.MARCADOR_SIGUIENTE, "Marcador siguiente."))
    lineas.append(_linea(atajos.NOTA_SIGUIENTE, "Nota siguiente."))
    lineas.append(_linea(atajos.CONTENEDOR_FIN, _("Salir de la lista o tabla actual.")))
    lineas.append(_linea("Intro", _("Seguir el enlace, o abrir la imagen o la tabla.")))
    lineas.append("")
    lineas.append(_("BUSCAR Y MOVERSE"))
    for identificador in ("buscar", "buscar_siguiente", "ir_linea", "ir_porcentaje",
                          "ir_pagina", "indice", "elementos", "marcadores", "atras"):
        orden = atajos.orden(identificador)
        lineas.append(_linea(orden.atajo, orden.descripcion))
    lineas.append("")
    lineas.append("HERRAMIENTAS")
    for identificador in ("poner_marcador", "poner_nota", "ver_imagen", "ver_tabla",
                          "informacion", "ajuste_linea", "sonidos", "opciones"):
        orden = atajos.orden(identificador)
        lineas.append(_linea(orden.atajo, orden.descripcion))
    lineas.append("")
    lineas.append("AYUDA")
    for identificador in ("manual", "atajos_ayuda"):
        orden = atajos.orden(identificador)
        lineas.append(_linea(orden.atajo, orden.descripcion))
    lineas.append("")
    lineas.append("SONIDOS")
    lineas.append(_("  Cada tipo de elemento suena distinto al pasar por él: los encabezados"))
    lineas.append(_("  son un tono cuya altura baja según el nivel, las imágenes dos toques"))
    lineas.append(_("  ascendentes, las tablas un acorde grave, las listas tres toques breves,"))
    lineas.append(_("  y los separadores y las páginas un roce de papel."))
    lineas.append("")
    lineas.append(_("Pulsa Control+O para abrir tu primer documento."))
    return "\n".join(lineas)


def texto_breve(version: str = "") -> str:
    """Presentación mínima, para quien ha apagado el resumen de teclas.

    No se deja el control **vacío** a propósito.  Una ventana en blanco no dice
    nada con un lector de pantalla: al llegar a ella se oye el nombre del
    control y ya está, y no hay forma de saber si el programa está listo, si el
    documento no se ha abierto o si se ha quedado colgado.  Con dos líneas se
    sabe dónde se está y cómo empezar, y sigue siendo algo que se recorre en un
    segundo en lugar de una pantalla entera de teclas.

    :param version: Versión del programa, para la primera línea.
    """
    titulo = NOMBRE.upper() + (" %s" % version if version else "")
    return "\n".join((
        titulo,
        "",
        _("No hay ningún documento abierto. Pulsa Control+O para abrir uno."),
        _("El resumen de teclas está apagado en Opciones, en «Personalización»."),
    ))
