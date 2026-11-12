# -*- coding: utf-8 -*-
"""Lo que un motor de voz toca **fuera de su carpeta**, y cómo se deshace.

Casi todos los motores viven enteros dentro de su carpeta y no dejan rastro en
ninguna parte: se instalan copiando y se quitan borrando. Alguno no puede: hay
sintetizadores que buscan la lista de sus voces en el registro de Windows y no
arrancan sin ella.

Eso plantea dos problemas, y los dos son de quien usa el programa, no del motor:

**No saberlo antes.** Instalar un motor es aceptar que se ejecute código ajeno,
y el programa ya enseña de quién es y de dónde sale antes de instalar nada. Si
además va a escribir en el registro, hay que decirlo ahí mismo y con nombres
concretos, no en una nota al pie.

**Que no se vaya del todo.** Un motor que se quita tiene que irse entero. Dejar
claves sueltas en el registro de alguien es de las cosas que más molestan de un
programa, y las deja precisamente el que se desinstala mal.

Cómo funciona
-------------

El paquete **declara** en su manifiesto qué ramas del registro necesita y por
qué. Con eso, el programa hace tres cosas que el motor no puede hacer por sí
mismo:

1. Lo cuenta antes de instalar, con la rama entera escrita.
2. Antes de tocar nada, **apunta qué había ya**. Si quien lo instala tenía ese
   sintetizador puesto por su cuenta, esa rama no la creamos nosotros y no es
   nuestra.
3. Al quitar el motor, borra lo que sí creamos, subiendo también por las claves
   padre que se queden vacías. Y lo hace **el programa**, no el motor: un motor
   roto es justo el que no se puede cargar para pedirle que se limpie, y es
   cuando más falta hace.

Solo la rama del usuario
------------------------

Se admite ``HKCU`` y nada más. En ``HKLM`` haría falta ser administrador y lo
que se escribiera valdría para todas las cuentas del equipo: un lector de libros
no tiene por qué pedir eso ni dejarlo puesto para los demás. Un motor que de
verdad necesite ``HKLM`` no se instala desde aquí; lo instala quien lo hizo, con
su propio instalador, y el usuario sabe lo que hace.
"""

from __future__ import annotations

import json
import logging

from .idioma import _

log = logging.getLogger("visor.sistema_motores")

try:
    import winreg
except ImportError:                                   # pragma: sin Windows
    winreg = None

#: Cómo se llama en el manifiesto lo que el motor toca fuera de su carpeta.
CLAVE = "sistema"

#: Dónde se apunta, dentro de la carpeta del motor, qué había antes de
#: instalarlo.  Va con el motor para que quitarlo no dependa de ningún otro
#: archivo que se pueda perder.
APUNTE = "_sistema.json"

#: La única raíz que se admite: la del usuario.
RAIZ = "HKCU"

#: Ramas que no se dejan tocar por mucho que las declare un paquete.  Son las
#: de Windows y las de la configuración de la propia cuenta: un motor de voz no
#: tiene nada que hacer ahí, y un paquete que lo pida está equivocado o miente.
PROHIBIDAS = (
    "software\\microsoft",
    "software\\classes",
    "software\\policies",
    "environment",
    "control panel",
    "console",
    "keyboard layout",
    "network",
    "system",
    "volatile environment",
)

#: Lo menos que puede declarar una rama: fabricante y producto.  Con un solo
#: nivel —«Software»— se estaría pidiendo permiso para borrar la mitad de la
#: configuración del equipo al desinstalar.
NIVELES_MINIMOS = 2


class Rama:
    """Una rama del registro que un motor necesita, y por qué la necesita."""

    __slots__ = ("clave", "porque")

    def __init__(self, clave: str, porque: str = "") -> None:
        self.clave = clave
        self.porque = porque

    def __repr__(self) -> str:
        return "Rama(%r)" % self.clave

    @property
    def completa(self) -> str:
        """La rama tal como se escribe para leerla: con su raíz delante."""
        return "%s\\%s" % (RAIZ, self.clave)


class Efectos:
    """Todo lo que un motor toca fuera de su carpeta.

    Vacío es lo normal: de los motores que trae el programa, ninguno toca nada.
    """

    __slots__ = ("resumen", "ramas")

    def __init__(self, resumen: str = "", ramas=()) -> None:
        self.resumen = resumen
        self.ramas = list(ramas)

    def __bool__(self) -> bool:
        return bool(self.ramas)


def leer(datos: dict) -> Efectos:
    """Saca del manifiesto lo que el motor dice que va a tocar.

    Lo que no se entienda se deja fuera y se apunta en el registro del
    programa. No se rechaza el paquete por ello: un manifiesto con un campo de
    más no es un paquete roto, y quedarse sin motor por eso sería peor.
    """
    crudo = datos.get(CLAVE)
    if not isinstance(crudo, dict):
        return Efectos()
    ramas = []
    for una in crudo.get("registro", []) or []:
        if not isinstance(una, dict):
            continue
        clave = str(una.get("clave", "")).strip().strip("\\")
        raiz = str(una.get("raiz", RAIZ)).strip().upper()
        if not clave:
            continue
        if raiz != RAIZ:
            log.warning("Un paquete pide la rama %s y solo se admite %s: %s",
                        raiz, RAIZ, clave)
            continue
        if not _rama_admisible(clave):
            log.warning("Un paquete pide una rama que no se admite: %s", clave)
            continue
        ramas.append(Rama(clave, str(una.get("porque", "")).strip()))
    return Efectos(str(crudo.get("resumen", "")).strip(), ramas)


def _rama_admisible(clave: str) -> bool:
    """Si una rama declarada se puede tocar.

    Se mira que tenga niveles suficientes, que no sea de Windows y que no se
    salga por arriba con «..», que en el registro también funciona.
    """
    partes = [uno for uno in clave.replace("/", "\\").split("\\") if uno]
    if len(partes) < NIVELES_MINIMOS or ".." in partes:
        return False
    bajo = "\\".join(partes).lower()
    return not any(bajo == mala or bajo.startswith(mala + "\\")
                   for mala in PROHIBIDAS)


def describir(efectos: Efectos) -> str:
    """Lo que se le lee a quien va a instalar el motor.

    Se escribe entero y sin adornos: la rama completa, para qué es, y qué pasa
    al quitarlo. Quien lo oiga tiene que poder decidir sin saber qué es el
    registro de Windows.
    """
    if not efectos:
        return ""
    lineas = [_("ESTE MOTOR TOCA EL REGISTRO DE WINDOWS.")]
    if efectos.resumen:
        lineas.append(efectos.resumen)
    for rama in efectos.ramas:
        if rama.porque:
            lineas.append(_("Creará «%(rama)s». %(porque)s")
                          % {"rama": rama.completa, "porque": rama.porque})
        else:
            lineas.append(_("Creará «%s».") % rama.completa)
    lineas.append(_(
        "Es la parte del registro de tu cuenta, así que no hace falta ser "
        "administrador y no afecta a nadie más que use este equipo."))
    lineas.append(_(
        "Al quitar el motor se borra todo esto, incluidas las claves que "
        "queden vacías. Lo que ya estuviera ahí antes de instalarlo no se "
        "toca."))
    return "\n".join(lineas)


# -- antes y después ---------------------------------------------------------

def apuntar_lo_que_habia(efectos: Efectos, carpeta) -> None:
    """Guarda qué ramas existían **antes** de instalar este motor.

    Es lo que después distingue lo que hay que borrar de lo que no. Sin esto,
    quitar el motor le borraría su propia instalación a quien ya tuviera ese
    sintetizador puesto por su cuenta, que es la clase de destrozo que nadie
    perdona.
    """
    if not efectos or winreg is None:
        return
    ya_estaban = [rama.clave for rama in efectos.ramas if _existe(rama.clave)]
    try:
        (carpeta / APUNTE).write_text(
            json.dumps({"ya_estaban": ya_estaban}, ensure_ascii=False, indent=2),
            encoding="utf-8")
    except OSError as error:
        log.warning("No se ha podido apuntar el estado del registro: %s", error)


def limpiar(efectos: Efectos, carpeta) -> int:
    """Borra del registro lo que puso este motor. Devuelve cuántas ramas quitó.

    Solo las que no estaban antes. Y después sube por las claves padre mientras
    se queden vacías, que es lo que evita dejar un «Software\\Fulanito» huérfano
    para siempre.
    """
    if not efectos or winreg is None:
        return 0
    ya_estaban = set()
    try:
        apunte = json.loads((carpeta / APUNTE).read_text(encoding="utf-8"))
        ya_estaban = {str(uno) for uno in apunte.get("ya_estaban", [])}
    except (OSError, ValueError):
        # Sin el apunte no se sabe qué había: se borra igual, porque dejar
        # claves puestas es peor, pero se dice en el registro del programa.
        log.info("No hay apunte del registro para este motor; se borra lo "
                 "declarado")
    quitadas = 0
    for rama in efectos.ramas:
        if rama.clave in ya_estaban:
            log.info("La rama %s ya existía antes; no se toca", rama.completa)
            continue
        if _borrar_rama(rama.clave):
            quitadas += 1
            _borrar_padres_vacios(rama.clave)
    return quitadas


def lo_que_queda(efectos: Efectos) -> list:
    """Qué ramas de las declaradas siguen en el registro.

    La usan las pruebas y sirve para comprobar de verdad que quitar un motor lo
    quita: preguntárselo al registro, y no fiarse de que la función que borra
    dijera que sí.
    """
    if not efectos or winreg is None:
        return []
    return [rama.completa for rama in efectos.ramas if _existe(rama.clave)]


# -- el registro, por dentro -------------------------------------------------

def _existe(clave: str) -> bool:
    try:
        winreg.OpenKey(winreg.HKEY_CURRENT_USER, clave).Close()
        return True
    except OSError:
        return False


def _borrar_rama(clave: str) -> bool:
    """Borra una clave y todo lo que cuelga de ella, de abajo arriba.

    Windows no borra una clave que tenga hijas, así que hay que bajar hasta el
    fondo y volver. Se comprueba otra vez que la rama se admite: entre que se
    leyó el manifiesto y esto han pasado cosas, y borrar del registro no es algo
    que convenga hacer fiándose de lo que se miró antes.
    """
    if not _rama_admisible(clave) or not _existe(clave):
        return False
    _borrar_recursivo(clave)
    return not _existe(clave)


def _borrar_recursivo(clave: str) -> None:
    try:
        abierta = winreg.OpenKey(winreg.HKEY_CURRENT_USER, clave, 0,
                                 winreg.KEY_ALL_ACCESS)
    except OSError:
        return
    with abierta:
        while True:
            try:
                hija = winreg.EnumKey(abierta, 0)
            except OSError:
                break
            _borrar_recursivo(clave + "\\" + hija)
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, clave)
    except OSError as error:
        log.warning("No se ha podido borrar %s\\%s: %s", RAIZ, clave, error)


def _borrar_padres_vacios(clave: str) -> None:
    """Sube borrando las claves padre que se hayan quedado vacías.

    Borrar «Software\\Fabricante\\Producto» y dejar «Fabricante» ahí, vacío para
    siempre, es no haberse ido del todo.  Se para en cuanto una tiene algo dentro
    o deja de ser admisible, que es lo que impide subir hasta «Software».
    """
    partes = [uno for uno in clave.split("\\") if uno]
    while len(partes) > NIVELES_MINIMOS:
        partes.pop()
        padre = "\\".join(partes)
        if not _rama_admisible(padre) or not _existe(padre):
            return
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, padre) as abierta:
                cuantas, valores, _fecha = winreg.QueryInfoKey(abierta)
            if cuantas or valores:
                return                      # tiene algo dentro: no es nuestro
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, padre)
            log.info("Borrada la clave vacía %s\\%s", RAIZ, padre)
        except OSError:
            return
