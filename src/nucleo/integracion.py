# -*- coding: utf-8 -*-
"""Integración con el explorador de archivos de Windows.

Sirve para dos cosas que el usuario elige por separado, formato a formato:

* Que al pulsar el botón derecho sobre un archivo aparezca **«Abrir con Visor
  Universal»**, y que aparezca **solo en los archivos que el programa sabe
  abrir**, sin tocar con qué programa se abren por defecto.
* Que el programa figure en el **«Abrir con»** de Windows, para poder elegirlo
  ahí y, si se quiere, ponerlo como predeterminado.

Todo se escribe en ``HKEY_CURRENT_USER``, así que **no hace falta ser
administrador** y no se toca nada de los demás usuarios del equipo.

Lo que Windows no deja hacer
----------------------------

**Ponerse como programa predeterminado por las bravas no se puede**, y no es
una limitación de este programa: desde Windows 8, la clave que dice qué
programa abre cada extensión va firmada con un resumen que depende del usuario
y del equipo, y Windows la descarta si la escribe alguien que no sea él mismo.
Lo que sí se puede —y es lo que se hace— es aparecer en la lista de «Abrir
con» para que el usuario lo elija en dos clics.

En Windows 11, además, el menú que sale al primer clic derecho es el corto: la
orden aparece en **«Mostrar más opciones»** (o con `Mayús+F10`).  Salir en el
menú corto exige empaquetar el programa como aplicación instalada, cosa que no
encaja con un programa portátil.

Programa portátil
-----------------

El registro guarda la ruta del ejecutable, así que al mover la carpeta las
órdenes apuntarían a donde ya no hay nada.  Por eso se guarda también qué ruta
se registró: al arrancar, :func:`revisar` compara y **vuelve a registrar sola**
si el programa ha cambiado de sitio.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .idioma import _
from .registro import obtener_registro

log = obtener_registro(__name__)

#: Nombre interno del tipo de archivo del programa.  Va con punto y sin
#: espacios porque es lo que Windows espera de un identificador de programa, y
#: lleva el nombre del programa delante para no chocar con nadie.
PROGRAMA = "VisorUniversal.Documento"

#: Nombre del verbo que se añade al menú contextual.
VERBO = "VisorUniversal.Abrir"

#: Dónde se apunta con qué ruta se registró, para saber si el programa se ha
#: movido de carpeta.
CLAVE_PROPIA = r"Software\VisorUniversal"


def disponible() -> bool:
    """Indica si esta máquina admite la integración."""
    return sys.platform == "win32"


def _registro():
    """Devuelve el módulo del registro de Windows, o ``None``."""
    if not disponible():
        return None
    try:
        import winreg

        return winreg
    except ImportError:                  # pragma: no cover - solo fuera de Windows
        return None


def ejecutable() -> str:
    """Ruta del programa tal como hay que escribirla en el registro.

    Compilado es el propio ``.exe``; en código fuente es el intérprete con el
    guion detrás, que es lo que hace que la integración se pueda probar sin
    compilar.
    """
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve())
    guion = Path(sys.argv[0]).resolve() if sys.argv and sys.argv[0] else None
    if guion and guion.exists():
        return '"%s" "%s"' % (Path(sys.executable).resolve(), guion)
    return str(Path(sys.executable).resolve())


def _orden() -> str:
    """La orden completa que Windows ejecutará, con el archivo detrás."""
    programa = ejecutable()
    if programa.startswith('"'):
        return "%s \"%%1\"" % programa
    return '"%s" "%%1"' % programa


def formatos_disponibles() -> list[tuple[str, str]]:
    """Devuelve ``(extensión, nombre del formato)`` de todo lo que se abre.

    Sale de los analizadores registrados, así que **no hay una lista que
    mantener**: un formato nuevo aparece aquí en cuanto su analizador existe.
    """
    from formatos import base

    salida = []
    for extension in base.extensiones_admitidas():
        analizador = base._REGISTRO.get(extension)
        nombre = getattr(analizador, "descripcion", "") or ""
        salida.append((extension.lower(), nombre))
    return salida


# ---------------------------------------------------------------------------
# Escribir y borrar
# ---------------------------------------------------------------------------

def aplicar(extensiones, menu: bool = True, abrir_con: bool = True) -> bool:
    """Deja la integración exactamente como pide la lista de extensiones.

    Se hace en dos pasos —borrar todo y volver a poner lo pedido— porque es lo
    único que deja el registro **igual que la lista**, sin restos de una
    configuración anterior.

    :param extensiones: Extensiones con punto, en minúsculas.
    :param menu: Si se añade la orden al menú del botón derecho.
    :param abrir_con: Si el programa aparece en el «Abrir con» de Windows.
    :return: ``True`` si se ha podido escribir.
    """
    winreg = _registro()
    if winreg is None:
        return False
    deseadas = sorted({str(e).lower() for e in extensiones if str(e).startswith(".")})
    try:
        _quitar_todo(winreg)
        if deseadas:
            _escribir_programa(winreg)
        for extension in deseadas:
            if menu:
                _escribir_verbo(winreg, extension)
            if abrir_con:
                _escribir_abrir_con(winreg, extension)
        _anotar_estado(winreg, deseadas, menu, abrir_con)
        _avisar_al_explorador()
        log.info("Integración con el sistema: %d formatos, menú=%s, abrir con=%s",
                 len(deseadas), menu, abrir_con)
        return True
    except OSError as error:
        log.warning("No se ha podido escribir la integración: %s", error)
        return False


def quitar() -> bool:
    """Deshace toda la integración y no deja rastro en el registro."""
    winreg = _registro()
    if winreg is None:
        return False
    try:
        _quitar_todo(winreg)
        _borrar_arbol(winreg, winreg.HKEY_CURRENT_USER, CLAVE_PROPIA)
        _avisar_al_explorador()
        log.info("Integración con el sistema retirada")
        return True
    except OSError as error:
        log.warning("No se ha podido quitar la integración: %s", error)
        return False


def revisar(extensiones, menu: bool = True, abrir_con: bool = True) -> bool:
    """Vuelve a registrar si el programa ha cambiado de carpeta.

    Es lo que hace que la integración siga funcionando en un programa
    portátil: al arrancar se compara la ruta con la que se registró y, si no
    es la misma, se rehace sola.  Devuelve ``True`` si ha hecho falta rehacerla.
    """
    winreg = _registro()
    if winreg is None or not extensiones:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLAVE_PROPIA) as clave:
            anterior, _tipo = winreg.QueryValueEx(clave, "RutaRegistrada")
    except OSError:
        anterior = ""
    if anterior == ejecutable():
        return False
    log.info("El programa ha cambiado de carpeta: se rehace la integración")
    return aplicar(extensiones, menu, abrir_con)


# ---------------------------------------------------------------------------
# Las piezas del registro
# ---------------------------------------------------------------------------

def _escribir_programa(winreg) -> None:
    """Crea el tipo de archivo del programa, con su orden de apertura."""
    ruta = r"Software\Classes\%s" % PROGRAMA
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, ruta) as clave:
        winreg.SetValueEx(clave, "", 0, winreg.REG_SZ, _("Documento del %s") % "Visor Universal")
        winreg.SetValueEx(clave, "FriendlyTypeName", 0, winreg.REG_SZ,
                          _("Documento del %s") % "Visor Universal")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, ruta + r"\shell\open\command") as clave:
        winreg.SetValueEx(clave, "", 0, winreg.REG_SZ, _orden())
    if not getattr(sys, "frozen", False):
        return
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, ruta + r"\DefaultIcon") as clave:
        winreg.SetValueEx(clave, "", 0, winreg.REG_SZ, "%s,0" % ejecutable())


def _escribir_verbo(winreg, extension: str) -> None:
    """Añade la orden del menú contextual para **esa** extensión.

    Se pone bajo ``SystemFileAssociations``, que es la rama que Windows
    consulta por la extensión sin mirar con qué programa está asociada.  Es lo
    que hace que la orden salga en los archivos del programa y **solo** en
    ellos, sin cambiarle a nadie su programa de siempre.
    """
    ruta = r"Software\Classes\SystemFileAssociations\%s\shell\%s" % (extension, VERBO)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, ruta) as clave:
        winreg.SetValueEx(clave, "", 0, winreg.REG_SZ,
                          _("Abrir con %s") % "Visor Universal")
        if getattr(sys, "frozen", False):
            winreg.SetValueEx(clave, "Icon", 0, winreg.REG_SZ, "%s,0" % ejecutable())
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, ruta + r"\command") as clave:
        winreg.SetValueEx(clave, "", 0, winreg.REG_SZ, _orden())


def _escribir_abrir_con(winreg, extension: str) -> None:
    """Apunta el programa en el «Abrir con» de esa extensión.

    No cambia el programa predeterminado —Windows no deja—, pero pone el
    programa en la lista para poder elegirlo, que es el único camino que el
    sistema admite.
    """
    ruta = r"Software\Classes\%s\OpenWithProgids" % extension
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, ruta) as clave:
        winreg.SetValueEx(clave, PROGRAMA, 0, winreg.REG_NONE, b"")


def _quitar_todo(winreg) -> None:
    """Borra todo lo que este programa haya escrito, esté donde esté."""
    _borrar_arbol(winreg, winreg.HKEY_CURRENT_USER, r"Software\Classes\%s" % PROGRAMA)
    raiz = r"Software\Classes\SystemFileAssociations"
    for extension in _extensiones_con_verbo(winreg, raiz):
        _borrar_arbol(winreg, winreg.HKEY_CURRENT_USER,
                      r"%s\%s\shell\%s" % (raiz, extension, VERBO))
    for extension in _extensiones_con_abrir_con(winreg):
        try:
            ruta = r"Software\Classes\%s\OpenWithProgids" % extension
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, ruta, 0,
                                winreg.KEY_SET_VALUE) as clave:
                winreg.DeleteValue(clave, PROGRAMA)
        except OSError:
            continue


def _extensiones_con_verbo(winreg, raiz: str) -> list[str]:
    """Extensiones que ahora mismo llevan la orden del programa."""
    salida = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, raiz) as clave:
            for numero in range(winreg.QueryInfoKey(clave)[0]):
                nombre = winreg.EnumKey(clave, numero)
                try:
                    with winreg.OpenKey(clave, r"%s\shell\%s" % (nombre, VERBO)):
                        salida.append(nombre)
                except OSError:
                    continue
    except OSError:
        return []
    return salida


def _extensiones_con_abrir_con(winreg) -> list[str]:
    """Extensiones en cuyo «Abrir con» figura el programa."""
    salida = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes") as clave:
            for numero in range(winreg.QueryInfoKey(clave)[0]):
                nombre = winreg.EnumKey(clave, numero)
                if not nombre.startswith("."):
                    continue
                try:
                    with winreg.OpenKey(clave, r"%s\OpenWithProgids" % nombre) as hija:
                        winreg.QueryValueEx(hija, PROGRAMA)
                    salida.append(nombre)
                except OSError:
                    continue
    except OSError:
        return []
    return salida


def _anotar_estado(winreg, extensiones: list, menu: bool, abrir_con: bool) -> None:
    """Guarda con qué ruta y con qué formatos se registró."""
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, CLAVE_PROPIA) as clave:
        winreg.SetValueEx(clave, "RutaRegistrada", 0, winreg.REG_SZ, ejecutable())
        winreg.SetValueEx(clave, "Formatos", 0, winreg.REG_SZ, " ".join(extensiones))
        winreg.SetValueEx(clave, "Menu", 0, winreg.REG_DWORD, 1 if menu else 0)
        winreg.SetValueEx(clave, "AbrirCon", 0, winreg.REG_DWORD, 1 if abrir_con else 0)


def _borrar_arbol(winreg, raiz, ruta: str) -> None:
    """Borra una clave y todo lo que cuelga de ella.

    El registro no deja borrar una clave que tenga hijas, así que hay que
    bajar hasta el fondo e ir borrando de vuelta.
    """
    try:
        with winreg.OpenKey(raiz, ruta) as clave:
            hijas = [winreg.EnumKey(clave, numero)
                     for numero in range(winreg.QueryInfoKey(clave)[0])]
    except OSError:
        return
    for hija in hijas:
        _borrar_arbol(winreg, raiz, "%s\\%s" % (ruta, hija))
    try:
        winreg.DeleteKey(raiz, ruta)
    except OSError as error:
        log.debug("No se ha podido borrar %s: %s", ruta, error)


def _avisar_al_explorador() -> None:
    """Le dice a Windows que las asociaciones han cambiado.

    Sin este aviso, el menú del botón derecho sigue enseñando lo de antes
    hasta que se reinicia el explorador.
    """
    if not disponible():
        return
    try:
        import ctypes

        SHCNE_ASSOCCHANGED, SHCNF_IDLIST = 0x08000000, 0x0000
        ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None)
    except Exception as error:
        log.debug("No se ha podido avisar al explorador: %s", error)


def abrir_ajustes_de_predeterminados() -> bool:
    """Abre la ventana de Windows donde se eligen los programas predeterminados.

    Es el único camino que el sistema admite para ponerse como programa
    predeterminado: lo tiene que elegir el usuario en su propia ventana.
    """
    if not disponible():
        return False
    try:
        import subprocess

        subprocess.Popen(["cmd", "/c", "start", "", "ms-settings:defaultapps"],
                         shell=False, creationflags=0x08000000)
        return True
    except Exception as error:
        log.debug("No se han podido abrir los ajustes de Windows: %s", error)
        return False
