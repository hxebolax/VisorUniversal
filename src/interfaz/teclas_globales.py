# -*- coding: utf-8 -*-
"""Teclas globales para manejar la lectura en voz alta desde cualquier sitio.

Escuchar un libro mientras se trabaja en otra cosa solo sirve de verdad si se
puede pausar, retroceder una frase o cambiar la velocidad **sin volver al
programa**.  Eso son teclas globales: las registra Windows y llegan a la
aplicación aunque el foco esté en el navegador o en el correo.

Se hace con ``wx.Window.RegisterHotKey``, que por debajo es la ``RegisterHotKey``
de Windows.  Dos detalles de esa API mandan sobre todo el diseño:

* Quiere **códigos de tecla virtuales** de Windows (VK), que no son los de
  wxPython: la flecha arriba es 0x26 en VK y ``wx.WXK_UP`` (315) en wx.  Por eso
  hay aquí un mapa propio.  Los modificadores sí coinciden: ``wx.MOD_CONTROL``,
  ``MOD_ALT``, ``MOD_SHIFT`` y ``MOD_WIN`` valen 2, 1, 4 y 8, igual que en Win32.
* **Falla si la combinación ya está cogida**, sea por otro programa o por el
  propio Windows (error 1409, ``ERROR_HOTKEY_ALREADY_REGISTERED``).  Eso
  convierte un intento de registro en la comprobación definitiva: no hace falta
  adivinar qué tiene ocupado el sistema, basta con pedirlo y ver si lo da.

Comprobación en cuatro niveles
------------------------------

1. **La combinación es válida**: tiene una tecla de verdad y lleva Windows, o
   Control y Alt juntos.  Sin esa exigencia, una tecla global se tragaría
   pulsaciones normales en cualquier programa donde se estuviera escribiendo.
2. **No está en la lista negra**: ni combinaciones que reserva Windows ni las
   teclas de los lectores de pantalla (Insert, Bloq Mayús), que estos capturan
   por debajo y que por tanto el registro *sí* concedería, engañando al usuario.
3. **No choca con otra acción del programa.**
4. **Windows la concede**: se registra de prueba y se libera al momento.  Este
   es el que descubre que la combinación la tiene cogida otra aplicación.

Todo esto es exclusivo de Windows.  En otros sistemas ``RegisterHotKey`` no
existe y el módulo se limita a no registrar nada.
"""

from __future__ import annotations

from typing import NamedTuple

import wx

from nucleo.idioma import _
from nucleo.registro import obtener_registro

log = obtener_registro(__name__)


class AccionGlobal(NamedTuple):
    """Una acción que se puede lanzar con una tecla global.

    :param identificador: Clave con la que se guarda en las preferencias.
    :param etiqueta: Nombre que se ve en la lista de teclas.
    :param combinacion: Combinación de fábrica.
    """

    identificador: str
    etiqueta: str
    combinacion: str


#: Acciones que se ofrecen, en el orden en que aparecen en las opciones.
#:
#: Las combinaciones de fábrica llevan todas ``Control+Alt+Mayús``.  Se
#: eligieron probando de verdad qué concede Windows, porque las alternativas
#: obvias están cogidas: ``Control+Windows`` con las flechas cambia de
#: escritorio virtual, ``Alt+Windows`` con las flechas ajusta la ventana, y
#: ``Control+Alt`` a secas lo usan ya los atajos de esta misma aplicación, de
#: modo que una tecla global con esa forma dejaría sin efecto el atajo normal.
#: Son cuatro dedos, sí; a cambio no pisan nada y se pueden cambiar todas.
CATALOGO: tuple[AccionGlobal, ...] = (
    AccionGlobal("leer_pausar", _("Leer en voz alta o pausar"), "ctrl+alt+shift+space"),
    AccionGlobal("detener", _("Detener la lectura"), "ctrl+alt+shift+end"),
    AccionGlobal("frase_anterior", _("Frase anterior"), "ctrl+alt+shift+left"),
    AccionGlobal("frase_siguiente", _("Frase siguiente"), "ctrl+alt+shift+right"),
    AccionGlobal("mas_rapido", _("Leer más deprisa"), "ctrl+alt+shift+up"),
    AccionGlobal("mas_lento", _("Leer más despacio"), "ctrl+alt+shift+down"),
    AccionGlobal("mostrar_ocultar", _("Mostrar u ocultar la ventana"), "ctrl+alt+shift+v"),
    # Las cinco siguientes valen para las dos formas de escuchar un libro: en
    # un libro DAISY grabado mandan sobre el reproductor y en cualquier otro
    # sobre la lectura con voz sintética.
    AccionGlobal("salto_atras", _("Retroceder diez segundos"), "ctrl+alt+shift+z"),
    AccionGlobal("salto_adelante", _("Avanzar diez segundos"), "ctrl+alt+shift+x"),
    AccionGlobal("punto_anterior", _("Punto de navegación anterior"), "ctrl+alt+shift+pageup"),
    AccionGlobal("punto_siguiente", _("Punto de navegación siguiente"), "ctrl+alt+shift+pagedown"),
    AccionGlobal("donde_estoy", _("Decir por dónde va la lectura"), "ctrl+alt+shift+j"),
)

#: Modificadores admitidos, con su valor en wxPython (que es el de Win32).
MODIFICADORES = {
    "ctrl": wx.MOD_CONTROL, "control": wx.MOD_CONTROL,
    "alt": wx.MOD_ALT,
    "shift": wx.MOD_SHIFT, "mayus": wx.MOD_SHIFT,
    "win": wx.MOD_WIN, "windows": wx.MOD_WIN,
}

#: Orden en el que se escriben siempre, para poder comparar combinaciones.
ORDEN = ("ctrl", "alt", "shift", "win")

#: Cómo se lee cada modificador en español.
NOMBRES_MODIFICADOR = {"ctrl": "Control", "alt": "Alt", "shift": _("Mayús"), "win": "Windows"}

#: Teclas con nombre: ``clave interna -> (código virtual de Windows, nombre)``.
TECLAS = {
    "up": (0x26, "Flecha arriba"), "down": (0x28, "Flecha abajo"),
    "left": (0x25, "Flecha izquierda"), "right": (0x27, "Flecha derecha"),
    "home": (0x24, "Inicio"), "end": (0x23, "Fin"),
    "pageup": (0x21, _("Re Pág")), "pagedown": (0x22, _("Av Pág")),
    "return": (0x0D, "Intro"), "space": (0x20, "Espacio"),
    "delete": (0x2E, "Suprimir"), "insert": (0x2D, "Insertar"),
    "escape": (0x1B, "Escape"), "tab": (0x09, "Tabulador"),
    "back": (0x08, "Retroceso"),
    "multiply": (0x6A, _("Asterisco del teclado numérico")),
    "add": (0x6B, _("Más del teclado numérico")),
    "subtract": (0x6D, _("Menos del teclado numérico")),
}
for _numero in range(1, 25):
    TECLAS["f%d" % _numero] = (0x6F + _numero, "F%d" % _numero)

#: Códigos de wxPython que corresponden a cada tecla con nombre, para poder
#: reconocer la pulsación cuando el usuario elige la combinación.
DESDE_WX = {
    wx.WXK_UP: "up", wx.WXK_DOWN: "down", wx.WXK_LEFT: "left", wx.WXK_RIGHT: "right",
    wx.WXK_HOME: "home", wx.WXK_END: "end",
    wx.WXK_PAGEUP: "pageup", wx.WXK_PAGEDOWN: "pagedown",
    wx.WXK_RETURN: "return", wx.WXK_NUMPAD_ENTER: "return",
    wx.WXK_SPACE: "space", wx.WXK_DELETE: "delete", wx.WXK_INSERT: "insert",
    wx.WXK_ESCAPE: "escape", wx.WXK_TAB: "tab", wx.WXK_BACK: "back",
    wx.WXK_MULTIPLY: "multiply", wx.WXK_ADD: "add", wx.WXK_SUBTRACT: "subtract",
}
for _numero in range(1, 25):
    DESDE_WX[getattr(wx, "WXK_F%d" % _numero)] = "f%d" % _numero

#: Combinaciones que no se dejan usar aunque Windows llegara a concederlas.
#:
#: Son de dos clases.  Unas las reserva el sistema y el registro fallaría de
#: todos modos; decirlo antes ahorra el intento y da un mensaje mejor.  Otras
#: —las de los lectores de pantalla— **sí** se registrarían, porque NVDA y JAWS
#: capturan el teclado por debajo: el usuario creería haberlas asignado y
#: después no funcionarían nunca.
LISTA_NEGRA = {
    # Windows
    "win+l", "win+d", "win+e", "win+r", "win+m", "win+x", "win+i", "win+a",
    "win+s", "win+tab", "win+up", "win+down", "win+left", "win+right",
    "ctrl+win+left", "ctrl+win+right", "ctrl+win+d", "ctrl+win+f4",
    "ctrl+win+return",
    "alt+tab", "alt+f4", "alt+escape", "alt+space", "ctrl+escape",
    "ctrl+alt+delete", "ctrl+shift+escape",
    # Lectores de pantalla
    "ctrl+alt+n",          # arranque de NVDA
    "ctrl+alt+j",          # arranque de JAWS
}
for _digito in "0123456789":
    LISTA_NEGRA.add("win+%s" % _digito)

#: Teclas que no pueden ser la tecla base: las usan los lectores de pantalla
#: como tecla modificadora propia.
BASES_PROHIBIDAS = {"insert", "capslock", "numlock"}

#: Primer identificador de los que se piden a Windows.  Se reserva un rango
#: propio para no chocar con ningún otro registro de la aplicación.
ID_BASE = 0xC100

#: Identificador que se usa solo para las pruebas de registro.
ID_PRUEBA = 0xC1FF


# ---------------------------------------------------------------------------
# Lectura y escritura de combinaciones
# ---------------------------------------------------------------------------

def trocear(combinacion: str) -> tuple[list[str], str]:
    """Separa una combinación en sus modificadores y su tecla base."""
    partes = [parte.strip().lower() for parte in (combinacion or "").split("+") if parte.strip()]
    if not partes:
        return [], ""
    base = partes[-1]
    modificadores = []
    for parte in partes[:-1]:
        for nombre in ORDEN:
            if MODIFICADORES.get(parte) == MODIFICADORES.get(nombre):
                if nombre not in modificadores:
                    modificadores.append(nombre)
                break
    return modificadores, base


def canonica(combinacion: str) -> str:
    """Devuelve la combinación en su forma normalizada, para comparar."""
    modificadores, base = trocear(combinacion)
    if not base:
        return ""
    return "+".join([m for m in ORDEN if m in modificadores] + [base])


def legible(combinacion: str) -> str:
    """Devuelve la combinación escrita en español, para verla y oírla."""
    modificadores, base = trocear(combinacion)
    if not base:
        return "(sin asignar)"
    nombres = [NOMBRES_MODIFICADOR[m] for m in ORDEN if m in modificadores]
    if base in TECLAS:
        nombres.append(TECLAS[base][1])
    else:
        nombres.append(base.upper())
    return "+".join(nombres)


def desde_evento(evento: wx.KeyEvent) -> str:
    """Convierte una pulsación en una combinación, o devuelve cadena vacía.

    Se usa al capturar la tecla que elige el usuario: pulsa la combinación y el
    programa la reconoce, en lugar de tener que escribirla.
    """
    codigo = evento.GetKeyCode()
    base = DESDE_WX.get(codigo, "")
    if not base:
        if codigo in (wx.WXK_SHIFT, wx.WXK_CONTROL, wx.WXK_ALT, wx.WXK_WINDOWS_LEFT,
                      wx.WXK_WINDOWS_RIGHT, wx.WXK_WINDOWS_MENU):
            return ""      # solo un modificador: todavía no hay combinación
        caracter = evento.GetUnicodeKey()
        if caracter == wx.WXK_NONE or caracter < 32:
            return ""
        base = chr(caracter).lower()
        if not base.isalnum():
            return ""
    partes = []
    if evento.ControlDown():
        partes.append("ctrl")
    if evento.AltDown():
        partes.append("alt")
    if evento.ShiftDown():
        partes.append("shift")
    if evento.MetaDown():
        partes.append("win")
    return "+".join(partes + [base])


def para_windows(combinacion: str) -> tuple[int, int] | None:
    """Traduce una combinación a ``(modificadores, código virtual)``.

    :return: ``None`` si la combinación no se puede registrar.
    """
    modificadores, base = trocear(combinacion)
    if not base:
        return None
    banderas = 0
    for nombre in modificadores:
        banderas |= MODIFICADORES.get(nombre, 0)
    if base in TECLAS:
        virtual = TECLAS[base][0]
    elif len(base) == 1 and base.isalnum():
        # En letras y cifras el código virtual coincide con el ASCII en
        # mayúscula, que es justo lo que espera RegisterHotKey.
        virtual = ord(base.upper())
    else:
        return None
    return banderas, virtual


# ---------------------------------------------------------------------------
# Comprobaciones
# ---------------------------------------------------------------------------

def revisar_forma(combinacion: str) -> str:
    """Niveles 1 y 2.  Devuelve el motivo del rechazo, o cadena vacía."""
    modificadores, base = trocear(combinacion)
    if not base:
        return _("No has pulsado ninguna tecla.")
    if base in MODIFICADORES:
        return (_("«%s» es un modificador, no una tecla. Mantén los modificadores y pulsa "
                "además una letra, un número o una tecla como F8 o Inicio.")
                % NOMBRES_MODIFICADOR.get(base, base))
    if para_windows(combinacion) is None:
        return (_("Esa tecla no se puede usar como tecla global. Usa una letra, un número, "
                "una tecla de función o una como Inicio, Fin o las flechas."))
    tiene_windows = "win" in modificadores
    tiene_ctrl_alt = "ctrl" in modificadores and "alt" in modificadores
    if not (tiene_windows or tiene_ctrl_alt):
        return (_("Una tecla global tiene que llevar Windows, o Control y Alt juntos. Si no, "
                "se tragaría esa pulsación en cualquier programa donde estuvieras escribiendo."))
    if base in BASES_PROHIBIDAS:
        return _("Esa tecla la usan los lectores de pantalla como tecla propia. Elige otra.")
    if canonica(combinacion) in LISTA_NEGRA:
        return _("Esa combinación ya la usan Windows o los lectores de pantalla. Elige otra.")
    return ""


def revisar_choque(combinacion: str, asignadas: dict, salvo: str = "") -> str:
    """Nivel 3.  Comprueba que no la tenga ya otra acción del programa.

    :param asignadas: ``{identificador: combinación}`` de lo asignado ahora.
    :param salvo: Acción que se está cambiando, que no cuenta como choque.
    """
    clave = canonica(combinacion)
    for identificador, otra in asignadas.items():
        if identificador == salvo or not otra:
            continue
        if canonica(otra) == clave:
            etiqueta = next((accion.etiqueta for accion in CATALOGO
                             if accion.identificador == identificador), identificador)
            return _("Esa combinación ya está asignada a «%s».") % etiqueta
    return ""


def revisar_en_windows(ventana: wx.Window, combinacion: str) -> str:
    """Nivel 4.  Pide la combinación a Windows y la suelta al momento.

    Es la comprobación que de verdad zanja el asunto: si otro programa la tiene
    cogida, ``RegisterHotKey`` falla y aquí se sabe sin tener que adivinar nada.
    """
    partes = para_windows(combinacion)
    if partes is None:
        return _("Esa combinación no se puede registrar.")
    try:
        if not ventana.RegisterHotKey(ID_PRUEBA, partes[0], partes[1]):
            return (_("Windows no concede esa combinación: la tiene cogida el sistema u otro "
                    "programa que está abierto. Elige otra, o cierra ese programa y vuelve "
                    "a intentarlo."))
        ventana.UnregisterHotKey(ID_PRUEBA)
    except Exception as error:      # pragma: no cover - fuera de Windows
        log.debug("No se ha podido probar la tecla global %s: %s", combinacion, error)
        return _("Este sistema no admite teclas globales.")
    return ""


def revisar(ventana: wx.Window, combinacion: str, asignadas: dict, salvo: str = "") -> str:
    """Pasa una combinación por las cuatro comprobaciones, en orden.

    :return: El motivo del rechazo, o cadena vacía si la combinación vale.
    """
    return (revisar_forma(combinacion)
            or revisar_choque(combinacion, asignadas, salvo)
            or revisar_en_windows(ventana, combinacion))


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------

def combinaciones(configuracion) -> dict:
    """Devuelve ``{identificador: combinación}`` con lo guardado y lo de fábrica."""
    guardadas = configuracion.obtener("teclas_globales", {}) or {}
    if not isinstance(guardadas, dict):
        guardadas = {}
    return {accion.identificador: str(guardadas.get(accion.identificador, accion.combinacion))
            for accion in CATALOGO}


def guardar(configuracion, asignadas: dict) -> None:
    """Guarda solo lo que difiere de fábrica, para que el archivo no crezca."""
    de_fabrica = {accion.identificador: accion.combinacion for accion in CATALOGO}
    configuracion.establecer("teclas_globales", {
        identificador: combinacion
        for identificador, combinacion in asignadas.items()
        if de_fabrica.get(identificador) != combinacion
    })


class Registro:
    """Mantiene registradas las teclas globales de una ventana.

    :param ventana: Ventana que recibe los avisos de Windows.
    :param despachar: Función ``despachar(identificador)`` que ejecuta la acción.
    """

    def __init__(self, ventana: wx.Window, despachar) -> None:
        self.ventana = ventana
        self.despachar = despachar
        self._identificadores: dict[str, int] = {}
        #: Acciones que no se han podido registrar, con el motivo.
        self.fallidas: dict[str, str] = {}

    def aplicar(self, configuracion) -> int:
        """Registra las teclas configuradas.  Devuelve cuántas han entrado.

        Se puede llamar en caliente cuantas veces haga falta: antes de nada
        suelta lo que hubiera registrado.
        """
        self.soltar()
        if not configuracion.obtener("teclas_globales_activas", False):
            return 0
        asignadas = combinaciones(configuracion)
        registradas = 0
        for numero, accion in enumerate(CATALOGO):
            combinacion = asignadas.get(accion.identificador, "")
            if not combinacion:
                continue
            motivo = revisar_forma(combinacion)
            if motivo:
                self.fallidas[accion.identificador] = motivo
                continue
            partes = para_windows(combinacion)
            identificador = ID_BASE + numero
            try:
                if not self.ventana.RegisterHotKey(identificador, partes[0], partes[1]):
                    self.fallidas[accion.identificador] = (
                        _("Windows no la concede: la tiene cogida otro programa."))
                    continue
            except Exception as error:   # pragma: no cover - fuera de Windows
                self.fallidas[accion.identificador] = str(error)
                continue
            self.ventana.Bind(
                wx.EVT_HOTKEY,
                lambda evento, clave=accion.identificador: self.despachar(clave),
                id=identificador)
            self._identificadores[accion.identificador] = identificador
            registradas += 1
        log.info("Teclas globales registradas: %d de %d", registradas, len(CATALOGO))
        return registradas

    def soltar(self) -> None:
        """Devuelve a Windows todas las teclas registradas."""
        for identificador in self._identificadores.values():
            try:
                self.ventana.UnregisterHotKey(identificador)
                self.ventana.Unbind(wx.EVT_HOTKEY, id=identificador)
            except Exception:            # pragma: no cover - cierre defensivo
                pass
        self._identificadores = {}
        self.fallidas = {}

    @property
    def activas(self) -> int:
        """Número de teclas globales registradas ahora mismo."""
        return len(self._identificadores)
