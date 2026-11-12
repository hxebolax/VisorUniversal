# -*- coding: utf-8 -*-
"""Motores de voz: el de siempre y los que se añaden como paquete.

El programa lee en voz alta con **SAPI 5**, que es la voz que trae Windows.
Funciona, está siempre y es la que ya usa el lector de pantalla de quien maneja
el programa.  Pero no es la única que hay, y para escuchar un libro entero la
diferencia entre una voz y otra es la diferencia entre acabarlo y dejarlo:

* **Eloquence** es la voz que muchos usuarios de lector de pantalla llevan
  usando treinta años.  Suena metálica y a nadie le parece bonita, y aun así es
  la que se pide una y otra vez, porque aguanta velocidades a las que ninguna
  otra se entiende y porque pronuncia las abreviaturas y los símbolos como quien
  lleva media vida oyéndola espera que suenen.
* Las voces **neuronales** —las de Edge, las de Chrome— suenan muchísimo mejor
  para una novela, y a cambio necesitan conexión o cientos de megas.

Meterlas todas dentro del programa no tiene sentido: son cientos de megabytes
que la mayoría no va a usar, y algunas ni siquiera se pueden distribuir.  Por
eso este módulo define **un contrato** y un sitio donde dejarlos: quien quiera
otra voz instala su paquete y aparece en la lista; quien no, no paga nada.

Qué es un motor
---------------

Un motor es un objeto que sabe hacer exactamente lo que
:class:`nucleo.voz.Sintetizador` sabe hacer.  El contrato no se ha inventado
aquí: **es el que ya usaba el programa**, y por eso el lector en voz alta no ha
tenido que cambiar ni una línea para admitir motores nuevos.  Lo que hace falta
está en :data:`CONTRATO`.

Cómo se declara lo que se puede ajustar
--------------------------------------

Un motor no solo habla: tiene ajustes propios, y son distintos en cada uno.
Eloquence tiene idioma, variante de voz y frecuencia de muestreo; las voces de
Edge tienen tono; SAPI 5 no tiene ninguna de las tres.

El programa **no sabe nada de eso**, y no debe: si lo supiera, añadir un motor
obligaría a tocar el diálogo de la voz.  Lo que hace es preguntarle al motor qué
ajustes tiene, y el motor los declara en su manifiesto con una lista de
:class:`Ajuste`.  Con esa lista, el diálogo pinta los controles, los guarda y
—esto no es opcional en este programa— **explica cada uno con Control+F1**.

Por eso un manifiesto sin la explicación de un ajuste se rechaza: un control que
no se puede explicar es un control que nadie que no vea va a tocar.
"""

from __future__ import annotations

import json
from pathlib import Path

from .idioma import _
from .registro import obtener_registro, registrar_excepcion

log = obtener_registro(__name__)

#: Identificador del motor de siempre: SAPI 5, la voz que trae Windows.  Es el
#: que se usa cuando no hay ninguno instalado, cuando el que había se ha quitado
#: y cuando el elegido falla al arrancar.  **Nunca se puede desinstalar**: es el
#: suelo del que el programa no se cae.
SAPI5 = "sapi5"

#: Lo que un motor tiene que saber hacer.  Es, letra por letra, lo que el lector
#: en voz alta le pide al sintetizador de siempre; de ahí que no haya habido que
#: cambiar nada para admitir motores nuevos.
CONTRATO = (
    "voces", "elegir_voz", "voces_con_idioma", "voz_para_idioma", "voz_actual",
    "establecer_velocidad", "establecer_volumen", "decir", "con_tono",
    "pausar", "continuar", "detener",
)

#: Y las tres propiedades que además tiene que tener.
PROPIEDADES = ("disponible", "pausada", "hablando")

#: Lo que un motor **puede** tener además, y que si tiene se usa.  No entra en
#: el contrato porque un motor sin esto funciona perfectamente.
#:
#: ``opciones_de(clave)`` devuelve las opciones que de verdad tiene uno de sus
#: ajustes de lista, como ``[(valor, texto), ...]``, o ``None`` para que se usen
#: las del manifiesto.  Hace falta cuando las opciones no se pueden saber al
#: armar el paquete: las calidades de voz de Vocalizer dependen de las voces que
#: se hayan copiado, y esas se copian después.
#: ``problema()`` devuelve, en una frase y para leer, por qué el motor no puede
#: hablar aunque haya arrancado: le falta la clave de las voces, no encuentra
#: ninguna, la biblioteca no cargó.  Devuelve cadena vacía si no pasa nada.  Sin
#: esto, pulsar «Probar» en uno de esos casos no hace nada de nada.
OPCIONALES = ("opciones_de", "espera_maxima", "cerrar", "problema")

#: Cómo se llama el archivo que describe un motor dentro de su carpeta.
MANIFIESTO = "motor.json"

#: Con qué extensiones puede venir el módulo de un motor, por orden de
#: preferencia.  Los paquetes que se distribuyen van **compilados** —``.pyc``,
#: bytecode—; el código fuente se admite para poder probar un motor mientras se
#: escribe, sin tener que armar el paquete en cada cambio.
EXTENSIONES_DE_MODULO = (".pyc", ".py")

#: Versión del contrato.  Un paquete dice contra qué versión está escrito, y si
#: no es esta se rechaza en vez de cargarlo y ver qué pasa: un motor a medio
#: encajar deja la lectura muda sin decir por qué.
VERSION_CONTRATO = 1

#: Qué clases de ajuste sabe pintar el diálogo.  Son pocas a propósito: con
#: estas cuatro se describen todos los ajustes de todos los motores que se han
#: mirado, y cada una que se añadiera habría que saber además cómo se anuncia.
CLASES_DE_AJUSTE = ("lista", "deslizador", "casilla", "texto")


class Ajuste:
    """Un ajuste que el motor deja tocar, tal como lo declara su manifiesto.

    :param clave: Con qué nombre se guarda.  Se guarda dentro de la sección del
        motor, así que dos motores pueden tener ambos un ajuste ``velocidad``
        sin pisarse.
    :param etiqueta: Lo que se lee en el diálogo.  Lleva su ``&`` si quiere
        letra de acceso.
    :param clase: Una de :data:`CLASES_DE_AJUSTE`.
    :param ayuda: Qué es, qué consigue y qué conviene poner.  Es lo que sale con
        Control+F1, y **es obligatorio**.
    :param opciones: Para ``lista``: pares ``(valor, texto)``.
    :param minimo, maximo: Para ``deslizador``.
    :param defecto: Valor de fábrica.
    """

    __slots__ = ("clave", "etiqueta", "clase", "ayuda", "opciones", "minimo",
                 "maximo", "defecto")

    def __init__(self, clave: str, etiqueta: str, clase: str, ayuda: str,
                 opciones=(), minimo: int = 0, maximo: int = 100,
                 defecto=None) -> None:
        self.clave = clave
        self.etiqueta = etiqueta
        self.clase = clase
        self.ayuda = ayuda
        self.opciones = list(opciones)
        self.minimo = minimo
        self.maximo = maximo
        self.defecto = defecto

    @classmethod
    def desde_json(cls, datos: dict) -> "Ajuste":
        """Lee un ajuste del manifiesto, comprobando que está completo."""
        clave = str(datos.get("clave", "")).strip()
        clase = str(datos.get("clase", "")).strip()
        etiqueta = str(datos.get("etiqueta", "")).strip()
        ayuda = str(datos.get("ayuda", "")).strip()
        if not clave or not etiqueta:
            raise ValueError("un ajuste sin clave o sin etiqueta")
        if clase not in CLASES_DE_AJUSTE:
            raise ValueError("clase de ajuste desconocida: %s" % clase)
        if not ayuda:
            # No es una formalidad: en este programa cada control se explica con
            # Control+F1, y un ajuste que no trae su explicación dejaría un
            # hueco justo donde alguien que no ve iría a preguntar qué es.
            raise ValueError("el ajuste «%s» no trae su explicación" % clave)
        opciones = [(item.get("valor"), str(item.get("texto", "")))
                    for item in datos.get("opciones", [])]
        if clase == "lista" and not opciones:
            raise ValueError("la lista «%s» no tiene opciones" % clave)
        return cls(clave, etiqueta, clase, ayuda, opciones,
                   int(datos.get("minimo", 0)), int(datos.get("maximo", 100)),
                   datos.get("defecto"))

    def valor_valido(self, valor):
        """Devuelve el valor si vale para este ajuste, o el de fábrica.

        Se comprueba al cargar porque la configuración es un archivo de texto
        que alguien puede haber editado, y porque un motor puede haberse
        actualizado y ya no tener la voz que estaba elegida.
        """
        if self.clase == "lista":
            posibles = [posible for posible, _texto in self.opciones]
            return valor if valor in posibles else (
                self.defecto if self.defecto in posibles
                else (posibles[0] if posibles else None))
        if self.clase == "deslizador":
            try:
                return max(self.minimo, min(self.maximo, int(valor)))
            except (TypeError, ValueError):
                return self.defecto if self.defecto is not None else self.minimo
        if self.clase == "casilla":
            return bool(valor)
        return str(valor if valor is not None else (self.defecto or ""))


class Motor:
    """Un motor instalado: lo que dice su manifiesto y dónde vive.

    No carga nada al construirse.  Un motor con voces neuronales tarda segundos
    en arrancar y ocupa memoria, y la lista de motores se consulta cada vez que
    se abre el diálogo de la voz: cargarlos todos para enseñar sus nombres sería
    pagar por lo que no se va a usar.
    """

    __slots__ = ("identificador", "nombre", "descripcion", "carpeta", "ajustes",
                 "modulo", "version", "propio", "conservar", "reiniciar",
                 "precargar")

    def __init__(self, identificador: str, nombre: str, descripcion: str = "",
                 carpeta: Path | None = None, ajustes=(), modulo: str = "",
                 version: str = "", propio: bool = False, conservar=(),
                 precargar=()) -> None:
        self.identificador = identificador
        self.nombre = nombre
        self.descripcion = descripcion
        self.carpeta = carpeta
        self.ajustes = list(ajustes)
        self.modulo = modulo
        self.version = version
        #: Los motores «propios» vienen con el programa y no se desinstalan.
        self.propio = propio
        #: Carpetas suyas que en realidad son de quien lo usa: donde deja lo que
        #: haya bajado.  Al reinstalar el motor se conserva lo que haya ahí, que
        #: si no se perdería por actualizar.  Lo declara el paquete: el programa
        #: no sabe qué guarda un motor dentro y no tiene por qué suponerlo.
        self.conservar = tuple(conservar or ())
        #: Bibliotecas que hay que meter en el proceso **antes que nada**, en
        #: este orden.  Ver :func:`precargar_bibliotecas`.
        self.precargar = tuple(precargar or ())
        #: Si hace falta cerrar y abrir el programa para que este motor sirva.
        #: Lo pone :func:`paquetes_voz.instalar` cuando el motor estaba en uso:
        #: sus bibliotecas siguen cargadas y Windows no las suelta en marcha.
        self.reiniciar = False

    def __repr__(self) -> str:
        return "Motor(%r, %r)" % (self.identificador, self.nombre)

    def ajuste(self, clave: str) -> "Ajuste | None":
        for uno in self.ajustes:
            if uno.clave == clave:
                return uno
        return None

    def valores_de_fabrica(self) -> dict:
        return {uno.clave: uno.defecto for uno in self.ajustes
                if uno.defecto is not None}


def motor_sapi5() -> Motor:
    """El motor de siempre, descrito como cualquier otro.

    Se declara aquí y no en un archivo aparte porque tiene que existir aunque no
    haya carpeta de datos, aunque el disco esté lleno y aunque alguien haya
    borrado lo que no debía: es el que se usa cuando todo lo demás falla.
    """
    return Motor(
        SAPI5,
        _("SAPI 5 de Windows"),
        _("La voz que trae Windows. Está siempre, arranca al instante y es la "
          "misma que usa tu lector de pantalla, así que suena a lo que ya "
          "conoces. Las voces se añaden desde Configuración de Windows, en "
          "«Hora e idioma», «Voz»."),
        propio=True,
    )


def leer_manifiesto(carpeta: Path) -> Motor:
    """Lee el ``motor.json`` de una carpeta y devuelve el motor que describe.

    Se comprueba todo aquí y se lanza excepción a la primera pega.  Un motor mal
    descrito no se carga «a ver si va»: se rechaza al instalarlo, que es cuando
    hay alguien delante mirando y se le puede decir qué le pasa.
    """
    ruta = Path(carpeta) / MANIFIESTO
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    identificador = str(datos.get("id", "")).strip()
    if not identificador or not identificador.replace("_", "").isalnum():
        raise ValueError(_("El paquete no dice cómo se llama su motor."))
    if identificador == SAPI5:
        raise ValueError(_("Ese identificador es el de la voz de Windows y no "
                           "se puede reemplazar."))
    version = int(datos.get("contrato", 0))
    if version != VERSION_CONTRATO:
        raise ValueError(_(
            "Este paquete está hecho para otra versión del programa "
            "(pide la %(pide)d y esta es la %(hay)d).")
            % {"pide": version, "hay": VERSION_CONTRATO})
    nombre = str(datos.get("nombre", "")).strip()
    if not nombre:
        raise ValueError(_("El paquete no dice cómo se llama su motor."))
    modulo = str(datos.get("modulo", "motor")).strip()
    if archivo_del_modulo(Path(carpeta), modulo) is None:
        raise ValueError(_("Al paquete le falta su archivo «%s».") % modulo)
    exigida = str(datos.get("python", "")).strip()
    if exigida and not _mismo_python(exigida):
        raise ValueError(_(
            "Este paquete está compilado para Python %(pide)s y este programa "
            "lleva Python %(hay)s. Hay que volver a armarlo.")
            % {"pide": exigida, "hay": _version_de_python()})
    ajustes = [Ajuste.desde_json(uno) for uno in datos.get("ajustes", [])]
    conservar = [str(uno) for uno in datos.get("conservar", [])
                 if str(uno).strip()]
    # Las rutas de «precargar» son relativas a la carpeta del motor y no pueden
    # salirse de ella: un paquete no tiene por qué cargar nada de fuera, y esto
    # se ejecuta al arrancar el programa, antes que ninguna otra cosa.
    precargar = []
    for uno in datos.get("precargar", []):
        texto = str(uno).strip().replace("\\", "/")
        if not texto or texto.startswith("/") or ".." in texto.split("/"):
            log.warning("El motor %s pide precargar una ruta que no vale: %r",
                        identificador, uno)
            continue
        precargar.append(texto)
    return Motor(identificador, nombre, str(datos.get("descripcion", "")),
                 Path(carpeta), ajustes, modulo,
                 str(datos.get("version", "")), conservar=conservar,
                 precargar=precargar)


def archivo_del_modulo(carpeta: Path, modulo: str) -> "Path | None":
    """El archivo del módulo de un motor, compilado o en fuente."""
    for extension in EXTENSIONES_DE_MODULO:
        candidato = Path(carpeta) / (modulo + extension)
        if candidato.is_file():
            return candidato
    return None


def _version_de_python() -> str:
    """La versión de Python con la que corre el programa, como «3.15»."""
    import sys

    return "%d.%d" % sys.version_info[:2]


def _mismo_python(pedida: str) -> bool:
    """Si el bytecode compilado para esa versión lo puede cargar esta.

    Se comparan solo los dos primeros números. El bytecode cambia de formato
    entre versiones mayores de Python y **no** entre correcciones: un paquete
    compilado con 3.15.0 vale en 3.15.4 y no vale en 3.16.
    """
    partes = pedida.replace(",", ".").split(".")
    return ".".join(partes[:2]) == _version_de_python()


def carpeta_de_motores() -> Path:
    """Dónde se instalan los motores que se añaden: ``data/motores``.

    Cada uno en su propia subcarpeta y con **todo** lo que necesita dentro: sus
    bibliotecas, sus voces y sus datos. Así instalar es copiar una carpeta y
    quitar es borrarla, sin tocar el sistema ni el registro de Windows. Un
    programa portátil que ensucia el equipo deja de ser portátil, y llevárselo
    en un lápiz de memoria tiene que llevarse también sus voces.
    """
    from . import rutas

    return rutas.subcarpeta("motores")


def instalados() -> list[Motor]:
    """Los motores añadidos que están bien.  Los rotos se saltan y se apuntan.

    Un motor que no se deja leer no puede tumbar la lista entera: quien tenga
    tres instalados y uno estropeado tiene que poder seguir usando los otros dos
    y, sobre todo, poder entrar a quitar el que falla.
    """
    salida = []
    raiz = carpeta_de_motores()
    if not raiz.is_dir():
        return salida
    for carpeta in sorted(raiz.iterdir()):
        if not (carpeta / MANIFIESTO).is_file():
            continue
        try:
            salida.append(leer_manifiesto(carpeta))
        except Exception as error:
            log.warning("Motor de voz ilegible en %s: %s", carpeta.name, error)
    return salida


#: Lo que ya se ha precargado, para no hacerlo dos veces.
_YA_PRECARGADO: list = []


def precargar_bibliotecas() -> int:
    """Mete en el proceso las bibliotecas que los motores instalados pidan.

    Hay que llamarla **al arrancar el programa y antes de tocar nada de voz**.
    El motivo es una regla de Windows que no perdona: cuando una biblioteca pide
    otra por su nombre, recibe la primera que ya esté cargada con ese nombre,
    sin mirar de dónde salió. Si otro programa del equipo tiene una copia más
    vieja de la misma biblioteca y esa entra antes —y entra, porque los
    adaptadores de voz se cargan solos en cuanto alguien usa la voz del
    sistema—, el motor acabará usándola. Y cuando las versiones no casan, eso no
    da un error: tira el proceso entero, sin excepción y sin una línea en el
    registro.

    Llegar antes lo arregla, y cuesta unas centésimas.

    :return: Cuántas bibliotecas han entrado.
    """
    import ctypes
    import os

    if _YA_PRECARGADO:
        return len(_YA_PRECARGADO)
    puestas = 0
    for motor in instalados():
        if not motor.precargar or motor.carpeta is None:
            continue
        try:
            os.add_dll_directory(str(motor.carpeta))
        except OSError as error:
            log.debug("No se ha podido añadir %s a la búsqueda de bibliotecas: "
                      "%s", motor.carpeta, error)
        for relativa in motor.precargar:
            cual = motor.carpeta / relativa
            if not cual.is_file():
                log.warning("El motor %s pide precargar %s y no está",
                            motor.identificador, relativa)
                continue
            try:
                # Se guarda la referencia: si el recolector se lleva el objeto,
                # la biblioteca se descarga y todo esto no habría servido.
                _YA_PRECARGADO.append(ctypes.CDLL(str(cual)))
                puestas += 1
            except OSError as error:
                # Alguna no carga suelta porque le falta una hermana suya, y da
                # igual: la que importa es la que provoca el choque, y esa sí.
                log.debug("No se ha podido precargar %s: %s", relativa, error)
    if puestas:
        log.info("Bibliotecas de motores precargadas: %d", puestas)
    return puestas


def catalogo() -> list[Motor]:
    """Todos los motores utilizables, con SAPI 5 siempre el primero."""
    return [motor_sapi5()] + instalados()


def buscar(identificador: str) -> Motor | None:
    """El motor que tenga ese identificador, o ``None``."""
    for motor in catalogo():
        if motor.identificador == identificador:
            return motor
    return None


def crear(identificador: str, ajustes: dict | None = None):
    """Construye el sintetizador de un motor, con SAPI 5 de red de seguridad.

    Si el motor elegido no está, no arranca o no cumple el contrato, se devuelve
    el de siempre **y se dice**.  Quedarse mudo sería lo peor que puede pasar:
    quien no ve no tiene forma de saber si el programa se ha colgado o si es que
    la voz no arranca.

    :return: ``(sintetizador, aviso)``.  El aviso va vacío cuando todo ha ido
        bien, y si no, cuenta qué ha pasado en una frase que se pueda leer.
    """
    from .voz import Sintetizador

    if not identificador or identificador == SAPI5:
        return Sintetizador(), ""
    motor = buscar(identificador)
    if motor is None:
        return Sintetizador(), _(
            "El motor de voz «%s» ya no está instalado. Se usará la voz de "
            "Windows.") % identificador
    try:
        objeto = _cargar(motor, dict(ajustes or {}))
    except Exception as error:
        registrar_excepcion(log, "Motor de voz %s" % motor.identificador, error)
        return Sintetizador(), _(
            "El motor de voz «%(motor)s» no ha podido arrancar: %(fallo)s. Se "
            "usará la voz de Windows.") % {"motor": motor.nombre,
                                           "fallo": error}
    falta = comprobar_contrato(objeto)
    if falta:
        log.error("El motor %s no cumple el contrato: falta %s",
                  motor.identificador, ", ".join(falta))
        return Sintetizador(), _(
            "El motor de voz «%s» no es compatible con esta versión del "
            "programa. Se usará la voz de Windows.") % motor.nombre
    return objeto, ""


def comprobar_contrato(objeto) -> list[str]:
    """Qué le falta a un objeto para poder leer un libro.  Vacío si está bien.

    Se comprueba de verdad y no se confía en el manifiesto: el manifiesto lo
    escribe quien hace el paquete y puede estar bienintencionado y equivocado.
    """
    falta = []
    for nombre in CONTRATO:
        if not callable(getattr(objeto, nombre, None)):
            falta.append(nombre)
    for nombre in PROPIEDADES:
        if not hasattr(objeto, nombre):
            falta.append(nombre)
    return falta


def _cargar(motor: Motor, ajustes: dict):
    """Importa el módulo de un motor y le pide su sintetizador.

    El módulo se carga **desde su carpeta**, sin tocar el ``sys.path`` global:
    dos motores pueden traer cada uno un módulo llamado igual, y encadenarlos en
    la ruta de importación haría que el segundo se comiera al primero.
    """
    import importlib.machinery
    import importlib.util
    import sys

    ruta = archivo_del_modulo(motor.carpeta, motor.modulo)
    if ruta is None:
        raise ImportError("no está el módulo %s" % motor.modulo)
    nombre = "motor_voz_%s" % motor.identificador
    if ruta.suffix == ".pyc":
        # El bytecode no se importa como el código fuente: hace falta decirle a
        # Python que el archivo **ya está compilado**, o buscaría un «.py» al
        # lado y no lo encontraría.
        cargador = importlib.machinery.SourcelessFileLoader(nombre, str(ruta))
        especificacion = importlib.util.spec_from_loader(nombre, cargador)
    else:
        especificacion = importlib.util.spec_from_file_location(nombre, ruta)
    if especificacion is None or especificacion.loader is None:
        raise ImportError("no se ha podido preparar %s" % ruta)
    modulo = importlib.util.module_from_spec(especificacion)
    # La carpeta del motor va **la primera** mientras se carga y se quita
    # después: es lo que deja que un paquete traiga sus propias dependencias sin
    # que se queden colgando en el programa entero.  Dos paquetes pueden traer
    # un módulo llamado igual, y con las dos carpetas puestas el segundo se
    # comería al primero.
    #
    # El margen llega hasta que el motor está **construido**, no solo importado:
    # un paquete con dos motores dentro solo importa el que esté elegido, y eso
    # pasa dentro de su constructor.
    sys.path.insert(0, str(motor.carpeta))
    try:
        sys.modules[nombre] = modulo
        especificacion.loader.exec_module(modulo)
        if not hasattr(modulo, "crear"):
            raise AttributeError(_("El paquete no trae la función «crear»."))
        completos = motor.valores_de_fabrica()
        completos.update(ajustes)
        limpios = {}
        for uno in motor.ajustes:
            limpios[uno.clave] = uno.valor_valido(completos.get(uno.clave))
        return modulo.crear(motor.carpeta, limpios)
    finally:
        try:
            sys.path.remove(str(motor.carpeta))
        except ValueError:
            pass
