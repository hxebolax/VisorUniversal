# -*- coding: utf-8 -*-
"""Voces Vocalizer Expressive para el Visor Universal.

Vocalizer es el motor de Nuance que llevan media docena de lectores de pantalla
y casi todos los móviles. Suena a persona, va rápido, aguanta velocidades altas
y no necesita conexión. En español las voces habituales son Jorge, Marisol y
Mónica, en calidad «premium-high» a 22 kHz.

Las voces, y cómo se añaden más
-------------------------------

Vienen tres dentro —Jorge, Marisol y Mónica— y **se detectan solas**: cada
subcarpeta de ``voces`` se le ofrece a Vocalizer al arrancar y lo que reconozca
aparece en la lista. Añadir una cuarta es copiarla ahí con la misma forma que
las que ya están, y volver a abrir la ventana de la voz. No hay nada que
registrar, ni que declarar, ni que reinstalar.

Las carpetas se llaman ``spe_jorge_premium-high``: idioma, voz y calidad. A
Vocalizer el nombre le da igual —mira dentro y reconoce lo que hay— así que se
aprovecha para que diga algo y para que sirva de plantilla. Lo que sí mira es lo
de dentro: las carpetas ``spe/speech/components`` y ``spe/speech/ve``, y los
nombres de los dos archivos.

Y como ``voces`` va declarada en el manifiesto, actualizar el paquete no se
lleva por delante las que se hayan añadido.

Cómo suena
----------

Vocalizer sabe reproducir por su cuenta, y aquí no se le deja: **devuelve el
sonido** y lo reproduce BASS, que el visor ya lleva para los libros DAISY. Es
por la pausa. Reproduciendo él no hay manera de pausar sin perder el sitio, y
pausar en mitad de un párrafo y seguir donde se dejó es lo primero que se le
pide a un lector de libros.

El sonido se recoge en dos pasos, que es como lo pide: primero avisa de que
necesita dónde escribir y se le dan los buffers, y luego avisa de que ya ha
escrito y se copia lo que haya.
"""

from __future__ import annotations

import ctypes
import logging
import sys
import threading
from ctypes import (POINTER, Structure, Union, c_byte, c_char, c_char_p, c_int,
                    c_size_t, c_uint, c_uint8, c_ushort, c_void_p, c_wchar_p)
from pathlib import Path

log = logging.getLogger("visor.motor.vocalizer")


def _(texto: str) -> str:
    """Los textos del motor, tal cual.

    El paquete se carga en marcha y fuera del programa, así que no tiene a mano
    su sistema de traducción; los rótulos que se generan aquí van en español,
    igual que los del manifiesto.
    """
    return texto

_AQUI = Path(__file__).resolve().parent
if str(_AQUI) not in sys.path:
    sys.path.insert(0, str(_AQUI))

# ---------------------------------------------------------------------------
# La interfaz de Vocalizer.  Son sus nombres y sus números, que no se pueden
# cambiar: es lo que la biblioteca espera recibir.
# ---------------------------------------------------------------------------

VERSION_INSTALL = 0x0520
VERSION_PLATAFORMA = 0x0200
LARGO_CADENA = 128

#: Códigos de respuesta.  Todo lo que no sea correcto o «lo ha parado el
#: usuario» es un fallo de verdad.
CORRECTO = 0
PARADO_POR_EL_USUARIO = 0x80000807

#: Los parámetros que se le pueden poner a una voz.
PARAM_IDIOMA = 1
PARAM_VOZ = 2
PARAM_VARIANTE = 3
PARAM_FRECUENCIA = 4
PARAM_TIPO_DE_CARACTER = 7
PARAM_VOLUMEN = 8
PARAM_VELOCIDAD = 9
PARAM_TONO = 10
PARAM_FACTOR_ESPERA = 11
PARAM_MODO_LECTURA = 12
PARAM_MODO_TEXTO = 13
PARAM_ALCANCE_IDIOMA = 15
PARAM_CAMBIO_DE_VOZ = 16
PARAM_MODO_IDIOMA = 17
PARAM_MARCAS = 19
PARAM_MODO_INICIO = 20
PARAM_SIN_SILENCIO_FINAL = 22

#: Y los límites de cada uno, tal como los declara la propia biblioteca.
TONO_MINIMO, TONO_MAXIMO = 50, 200
VELOCIDAD_MINIMA, VELOCIDAD_MAXIMA = 50, 400
VOLUMEN_MINIMO, VOLUMEN_MAXIMO = 0, 100
ESPERA_MINIMA, ESPERA_MAXIMA_PARAM = 0, 9

#: Valores con nombre.
MODO_INICIO_CARGAR_UNA_VEZ = 0xC
TEXTO_NORMAL = 0
MODO_TEXTO_ESTANDAR = 1
MODO_TEXTO_SMS = 2
LECTURA_FRASE = 1
LECTURA_CARACTER = 2
LECTURA_PALABRA = 3
LECTURA_LINEA = 4
MARCAS_NO = 0
MARCAS_SI = 1
CARACTERES_UTF8 = 2
CAMBIO_DE_VOZ_NO = 0
CAMBIO_DE_VOZ_SI = 1
IDIOMA_POR_MEMORIA = 0
IDIOMA_FORZADO = 1

#: Mensajes del retorno de llamada.
MENSAJE_PIDE_BUFFER = 0x00000008
MENSAJE_BUFFER_LLENO = 0x00000010

#: Tamaño de los buffers que se le prestan, en bytes y en marcas.  Son los
#: mismos que usa el controlador de NVDA y van bien: con menos, el retorno de
#: llamada se dispara demasiadas veces por frase.
TAMANO_PCM = 8192
TAMANO_MARCAS = 100

#: De kilohercios a hercios, que es como lo cuenta la biblioteca y como lo
#: necesita un archivo de sonido.
FRECUENCIAS = {8: 8000, 11: 11025, 16: 16000, 22: 22050}


class VE_HSAFE(Structure):
    _fields_ = (("pHandleData", c_void_p), ("u32Check", c_uint))


class VE_INSTALL(Structure):
    _fields_ = (("fmtVersion", c_ushort), ("pBinBrokerInfo", c_char_p),
                ("pIHeap", c_void_p), ("hHeap", c_void_p),
                ("pICritSec", c_void_p), ("hCSClass", c_void_p),
                ("pIDataStream", c_void_p), ("pIDataMapping", c_void_p),
                ("hDataClass", c_void_p), ("pILog", c_void_p),
                ("hLog", c_void_p))


class VPLATFORM_MEMBLOCK(Structure):
    _fields_ = (("start", c_void_p), ("cByte", c_uint), ("cFlags", c_uint))


class VPLATFORM_RESOURCES(Structure):
    _fields_ = (("fmtVersion", c_ushort), ("u16NbrOfDataInstall", c_ushort),
                ("apDataInstall", POINTER(c_wchar_p)),
                ("stHeap", VPLATFORM_MEMBLOCK), ("pDatPtr_Table", c_void_p),
                ("szBinaryBrokerFile", c_wchar_p),
                ("szFileListFile", c_wchar_p),
                ("rfu1", c_uint), ("rfu2", c_uint))


class VE_INTEXT(Structure):
    _fields_ = (("eTextFormat", c_int), ("cntTextLength", c_size_t),
                ("szInText", c_void_p))


class VE_PARAM_VALUE(Union):
    _fields_ = (("usValue", c_ushort), ("szStringValue", c_char * LARGO_CADENA))


class VE_PARAM(Structure):
    _fields_ = (("ID", c_uint), ("uValue", VE_PARAM_VALUE))


class VE_CALLBACKMSG(Structure):
    _fields_ = (("eMessage", c_uint), ("lValue", c_int), ("pParam", c_void_p))


RETORNO = ctypes.CFUNCTYPE(c_uint, VE_HSAFE, c_void_p, POINTER(VE_CALLBACKMSG))


class VE_OUTDEVINFO(Structure):
    _fields_ = (("userData", c_void_p), ("pfOutNotify", RETORNO))


class VE_LANGUAGE(Structure):
    _fields_ = (("szLanguage", c_char * LARGO_CADENA),
                ("szLanguageTLW", c_char * 4),
                ("szVersion", c_char * LARGO_CADENA))


class VE_VOICEINFO(Structure):
    _fields_ = (("szVersion", c_char * LARGO_CADENA),
                ("szLanguage", c_char * LARGO_CADENA),
                ("szVoiceName", c_char * LARGO_CADENA),
                ("szVoiceAge", c_char * LARGO_CADENA),
                ("szVoiceType", c_char * LARGO_CADENA))


class VE_SPEECHDBINFO(Structure):
    _fields_ = (("szVersion", c_char * LARGO_CADENA),
                ("szLanguage", c_char * LARGO_CADENA),
                ("szVoiceName", c_char * LARGO_CADENA),
                ("szVoiceOperatingPoint", c_char * LARGO_CADENA),
                ("u16Freq", c_ushort))


class VE_MARKINFO(Structure):
    _fields_ = (("ulMrkInfo", c_uint), ("eMrkType", c_uint),
                ("cntSrcPos", c_size_t), ("cntSrcTextLen", c_size_t),
                ("cntDestPos", c_size_t), ("cntDestLen", c_size_t),
                ("usPhoneme", c_ushort), ("ulMrkId", c_uint),
                ("ulParam", c_uint), ("szPromptID", c_char_p))


class VE_OUTDATA(Structure):
    _fields_ = (("eAudioFormat", c_uint), ("cntPcmBufLen", c_size_t),
                ("pOutPcmBuf", c_void_p), ("cntMrkListLen", c_size_t),
                ("pMrkList", POINTER(VE_MARKINFO)))


class VE_PRODUCT_VERSION(Structure):
    _fields_ = (("major", c_uint8), ("minor", c_uint8), ("maint", c_uint8))


class ErrorVocalizer(RuntimeError):
    """Algo que la biblioteca ha rechazado, con su código."""

    def __init__(self, codigo: int, donde: str) -> None:
        self.codigo = codigo
        super().__init__("Vocalizer: %s ha devuelto 0x%x" % (donde, codigo))


def _texto(crudo) -> str:
    """Una cadena de la biblioteca, ya legible."""
    if isinstance(crudo, bytes):
        return crudo.decode("utf-8", "replace")
    return str(crudo or "")


def _por_ciento(valor: int, minimo: int, maximo: int) -> int:
    return int(round((valor - minimo) * 100.0 / (maximo - minimo)))


def _desde_por_ciento(porcentaje: int, minimo: int, maximo: int) -> int:
    acotado = max(0, min(100, int(porcentaje)))
    return int(round(minimo + acotado * (maximo - minimo) / 100.0))


class MotorVocalizer:
    """Vocalizer Expressive con la cara que el visor sabe manejar."""

    def __init__(self, carpeta: Path, ajustes: dict) -> None:
        self._carpeta = Path(carpeta)
        self._ajustes = dict(ajustes)
        self._ve = None
        self._plataforma = None
        self._msvcr = None
        self._clase = None
        self._instalacion = None
        self._instancia = None
        self._voces: list = []
        self._voz = ""
        self._muestreo = 22050
        self._pcm = (c_byte * TAMANO_PCM)()
        self._marcas = (VE_MARKINFO * TAMANO_MARCAS)()
        self._trozos: list = []
        self._cerrojo = threading.RLock()
        self._canal = 0
        self._pausado = False
        self._bass = False
        self._volumen = 100
        self._arrancar()

    # -- arranque ------------------------------------------------------------

    @property
    def _carpeta_de_voces(self) -> Path:
        """Donde se dejan las voces. Cada una en su propia subcarpeta."""
        donde = self._carpeta / "voces"
        donde.mkdir(parents=True, exist_ok=True)
        return donde

    def _donde_buscar(self) -> list:
        """Todas las carpetas en las que Vocalizer tiene que mirar.

        Primero los datos comunes, que hacen falta siempre, y después cada
        subcarpeta de «voces». Se le pasan todas sin mirar qué hay dentro: quien
        sabe si una carpeta es una voz es él, y adivinarlo aquí solo serviría
        para dejar fuera alguna que sí valía.
        """
        rutas = [str(self._carpeta / "common")]
        for uno in sorted(self._carpeta_de_voces.iterdir()):
            if uno.is_dir():
                rutas.append(str(uno))
        # Y una carpeta más, si alguien la ha puesto en los ajustes: es para
        # quien ya tenga las voces en otro sitio y no quiera duplicar gigas.
        extra = str(self._ajustes.get("carpeta_extra", "") or "").strip()
        if extra:
            fuera = Path(extra)
            if fuera.is_dir():
                rutas.append(str(fuera))
                for uno in sorted(fuera.iterdir()):
                    if uno.is_dir():
                        rutas.append(str(uno))
            else:
                log.warning("La carpeta de voces «%s» no existe", extra)
        return rutas

    def _arrancar(self) -> None:
        """Carga las bibliotecas, le dice dónde mirar y pregunta qué hay."""
        try:
            self._cargar_bibliotecas()
        except Exception as error:
            log.warning("No se ha podido cargar Vocalizer: %s", error)
            self._ve = None
            return
        try:
            self._iniciar(self._donde_buscar())
        except Exception as error:
            log.warning("Vocalizer no ha arrancado: %s", error)
            self._ve = None
            return
        self._voces = self._listar_voces()
        log.info("Vocalizer %s con %d voces", self._version(), len(self._voces))
        if not self._voces:
            log.warning("No hay ninguna voz en %s", self._carpeta_de_voces)
            return
        guardada = str(self._ajustes.get("_voz_elegida", ""))
        elegir = guardada if any(uno[0] == guardada for uno in self._voces) \
            else self._voces[0][0]
        self.elegir_voz(elegir)

    def _cargar_bibliotecas(self) -> None:
        """Las tres bibliotecas, en su orden.

        El tiempo de ejecución de Visual C++ va primero porque ``ve.dll`` lo
        necesita, y si no está cargado la carga de ``ve.dll`` falla con un error
        que no dice nada.
        """
        lib = self._carpeta / "lib"
        self._msvcr = ctypes.cdll.LoadLibrary(str(lib / "msvcr110.dll"))
        self._ve = ctypes.cdll.LoadLibrary(str(lib / "ve.dll"))
        self._plataforma = ctypes.cdll.LoadLibrary(str(lib / "vplatform.dll"))
        for nombre in ("ve_ttsInitialize", "ve_ttsUnInitialize", "ve_ttsOpen",
                       "ve_ttsClose", "ve_ttsProcessText2Speech", "ve_ttsStop",
                       "ve_ttsPause", "ve_ttsResume", "ve_ttsSetParamList",
                       "ve_ttsGetParamList", "ve_ttsGetLanguageList",
                       "ve_ttsGetVoiceList", "ve_ttsGetSpeechDBList",
                       "ve_ttsSetOutDevice", "ve_ttsGetProductVersion"):
            getattr(self._ve, nombre).restype = c_uint
        self._plataforma.vplatform_GetInterfaces.restype = c_uint
        self._plataforma.vplatform_GetInterfaces.argtypes = (
            POINTER(VE_INSTALL), POINTER(VPLATFORM_RESOURCES))
        self._plataforma.vplatform_ReleaseInterfaces.restype = c_uint
        self._plataforma.vplatform_ReleaseInterfaces.argtypes = (
            POINTER(VE_INSTALL),)

    def _comprobar(self, codigo: int, donde: str) -> None:
        if codigo not in (CORRECTO, PARADO_POR_EL_USUARIO):
            raise ErrorVocalizer(codigo, donde)

    def _iniciar(self, rutas: list) -> None:
        """Le dice dónde están sus datos y arranca la clase de voz."""
        self._instalacion = VE_INSTALL()
        self._instalacion.fmtVersion = VERSION_INSTALL
        self._instalacion.pBinBrokerInfo = None
        recursos = VPLATFORM_RESOURCES()
        recursos.fmtVersion = VERSION_PLATAFORMA
        recursos.u16NbrOfDataInstall = c_ushort(len(rutas))
        # La lista se guarda en el objeto: la biblioteca se queda con el
        # puntero, y si el recolector se lleva el array antes de tiempo, lo que
        # lee después es basura.
        self._rutas = (c_wchar_p * len(rutas))()
        for numero, ruta in enumerate(rutas):
            self._rutas[numero] = c_wchar_p(ruta)
        recursos.apDataInstall = self._rutas
        recursos.pDatPtr_Table = None
        self._comprobar(
            self._plataforma.vplatform_GetInterfaces(
                ctypes.byref(self._instalacion), ctypes.byref(recursos)),
            "vplatform_GetInterfaces")
        self._clase = VE_HSAFE()
        self._comprobar(
            self._ve.ve_ttsInitialize(ctypes.byref(self._instalacion),
                                      ctypes.byref(self._clase)),
            "ve_ttsInitialize")

    def _version(self) -> str:
        version = VE_PRODUCT_VERSION()
        try:
            self._ve.ve_ttsGetProductVersion(ctypes.byref(version))
        except Exception:
            return "?"
        return "%d.%d.%d" % (version.major, version.minor, version.maint)

    # -- qué voces hay -------------------------------------------------------

    def _idiomas(self) -> list:
        cuantos = c_ushort()
        self._ve.ve_ttsGetLanguageList(self._clase, None, ctypes.byref(cuantos))
        lista = (VE_LANGUAGE * cuantos.value)()
        self._ve.ve_ttsGetLanguageList(self._clase, ctypes.byref(lista),
                                       ctypes.byref(cuantos))
        return [lista[i] for i in range(cuantos.value)]

    def _listar_voces(self) -> list:
        """Las voces que hay: ``(nombre, idioma, sexo, variantes)``.

        El idioma se devuelve en el código de dos letras y país que usa el
        visor, sacado de las tres letras que da Vocalizer.
        """
        salida = []
        try:
            idiomas = self._idiomas()
        except Exception as error:
            log.warning("No se han podido listar los idiomas: %s", error)
            return salida
        for idioma in idiomas:
            crudo = idioma.szLanguage
            codigo = _codigo_de_idioma(_texto(idioma.szLanguageTLW))
            cuantas = c_ushort()
            try:
                self._ve.ve_ttsGetVoiceList(self._clase, c_char_p(crudo), None,
                                            ctypes.byref(cuantas))
                fichas = (VE_VOICEINFO * cuantas.value)()
                self._ve.ve_ttsGetVoiceList(self._clase, c_char_p(crudo),
                                            ctypes.byref(fichas),
                                            ctypes.byref(cuantas))
            except Exception as error:
                log.debug("Sin voces para %s: %s", _texto(crudo), error)
                continue
            for numero in range(cuantas.value):
                ficha = fichas[numero]
                nombre = _texto(ficha.szVoiceName)
                salida.append((nombre, codigo, _texto(ficha.szVoiceType),
                               self._variantes_de(crudo, ficha.szVoiceName)))
        return salida

    def _variantes_de(self, idioma: bytes, voz: bytes) -> list:
        """Las calidades de una voz, cada una con su frecuencia.

        La frecuencia importa: no es un ajuste que la voz obedezca, es un dato
        suyo. Pedirle otra la deja muda.
        """
        cuantas = c_ushort()
        try:
            self._ve.ve_ttsGetSpeechDBList(self._clase, c_char_p(idioma),
                                           c_char_p(voz), None,
                                           ctypes.byref(cuantas))
            fichas = (VE_SPEECHDBINFO * cuantas.value)()
            self._ve.ve_ttsGetSpeechDBList(self._clase, c_char_p(idioma),
                                           c_char_p(voz), ctypes.byref(fichas),
                                           ctypes.byref(cuantas))
        except Exception as error:
            log.debug("Sin variantes para %s: %s", _texto(voz), error)
            return []
        return [(_texto(fichas[i].szVoiceOperatingPoint), int(fichas[i].u16Freq))
                for i in range(cuantas.value)]

    @property
    def disponible(self) -> bool:
        return self._ve is not None and bool(self._voces)

    def voces(self) -> list:
        return [nombre for nombre, _idioma, _sexo, _variantes in self._voces]

    def voces_con_idioma(self) -> list:
        return [(nombre, idioma)
                for nombre, idioma, _sexo, _variantes in self._voces]

    def voz_actual(self) -> str:
        return self._voz

    def voz_para_idioma(self, codigo: str) -> str:
        """La voz que mejor lee ese idioma.

        Se prefiere la del país exacto y, si no, cualquiera de la misma lengua:
        oír una frase inglesa con voz inglesa de otro país es mucho mejor que
        oírla con voz española.
        """
        if not codigo:
            return ""
        pedido = codigo.replace("_", "-").lower()
        lengua = pedido.split("-")[0]
        aproximada = ""
        for nombre, idioma, _sexo, _variantes in self._voces:
            suyo = (idioma or "").lower()
            if not suyo:
                continue
            if suyo == pedido:
                return nombre
            if suyo.split("-")[0] == lengua and not aproximada:
                aproximada = nombre
        return aproximada

    def elegir_voz(self, nombre: str) -> bool:
        """Abre una instancia con esa voz y le pone todos los ajustes.

        Se cierra la anterior y se abre otra, que es lo que la biblioteca
        espera: la voz no se cambia sobre la marcha, se abre con ella.
        """
        if self._ve is None:
            return False
        if not any(uno[0] == nombre for uno in self._voces):
            return False
        with self._cerrojo:
            self.detener()
            self._cerrar_instancia()
            instancia = VE_HSAFE()
            try:
                self._comprobar(
                    self._ve.ve_ttsOpen(self._clase, self._instalacion.hHeap,
                                        self._instalacion.hLog,
                                        ctypes.byref(instancia)),
                    "ve_ttsOpen")
            except Exception as error:
                log.warning("No se ha podido abrir la voz «%s»: %s", nombre,
                            error)
                return False
            self._instancia = instancia
            self._voz = nombre
            self._retorno = RETORNO(self._recibir)
            salida = VE_OUTDEVINFO()
            salida.pfOutNotify = self._retorno
            try:
                self._ve.ve_ttsSetOutDevice(instancia, ctypes.byref(salida))
                self._aplicar_ajustes(nombre)
            except Exception as error:
                log.warning("No se han podido poner los ajustes: %s", error)
            return True

    # -- los ajustes ---------------------------------------------------------

    def _poner(self, *parejas) -> None:
        """Le pasa una lista de parámetros, que es como los quiere."""
        if self._ve is None or self._instancia is None:
            return
        lista = (VE_PARAM * len(parejas))()
        for numero, (cual, valor) in enumerate(parejas):
            lista[numero].ID = c_uint(cual)
            if isinstance(valor, str):
                lista[numero].uValue.szStringValue = valor.encode("utf-8")
            else:
                lista[numero].uValue.usValue = c_ushort(int(valor))
        try:
            self._comprobar(
                self._ve.ve_ttsSetParamList(self._instancia,
                                            ctypes.byref(lista),
                                            c_ushort(len(parejas))),
                "ve_ttsSetParamList")
        except Exception as error:
            log.debug("No se han podido poner unos parámetros: %s", error)

    def _entero(self, clave: str, defecto: int) -> int:
        try:
            return int(self._ajustes.get(clave, defecto))
        except (TypeError, ValueError):
            return defecto

    def _aplicar_ajustes(self, nombre: str) -> None:
        """Todo lo que se puede configurar, de una vez."""
        calidades = self._calidades_de(nombre)
        nombres = [cual for cual, _hercios in calidades]
        pedida = str(self._ajustes.get("variante", "") or "").strip()
        # Si la calidad pedida no la tiene esta voz, se usa la primera que
        # tenga: vale más que suene con otra calidad que que no suene.
        variante = pedida if pedida in nombres else (
            nombres[0] if nombres else "")
        frecuencia = self._frecuencia_de(calidades, variante)

        parametros = [
            (PARAM_VOZ, nombre),
            (PARAM_MARCAS, MARCAS_SI),
            (PARAM_MODO_INICIO, MODO_INICIO_CARGAR_UNA_VEZ),
            (PARAM_TIPO_DE_CARACTER, CARACTERES_UTF8),
            (PARAM_FRECUENCIA, frecuencia),
            (PARAM_TONO, _desde_por_ciento(self._entero("tono", 50),
                                           TONO_MINIMO, TONO_MAXIMO)),
            (PARAM_FACTOR_ESPERA, max(ESPERA_MINIMA,
                                      min(ESPERA_MAXIMA_PARAM,
                                          self._entero("factor_espera", 1)))),
            (PARAM_MODO_LECTURA, self._entero("modo_lectura", LECTURA_FRASE)),
            (PARAM_MODO_TEXTO, self._entero("modo_texto", MODO_TEXTO_ESTANDAR)),
            (PARAM_SIN_SILENCIO_FINAL,
             1 if self._ajustes.get("sin_silencio_final") else 0),
            (PARAM_CAMBIO_DE_VOZ,
             CAMBIO_DE_VOZ_SI if self._ajustes.get("cambiar_voz_por_idioma")
             else CAMBIO_DE_VOZ_NO),
            (PARAM_MODO_IDIOMA,
             IDIOMA_FORZADO if self._ajustes.get("idioma_forzado")
             else IDIOMA_POR_MEMORIA),
            (PARAM_ALCANCE_IDIOMA, self._entero("alcance_idioma", 0)),
        ]
        if variante:
            parametros.insert(1, (PARAM_VARIANTE, variante))
        self._poner(*parametros)
        self._muestreo = FRECUENCIAS.get(frecuencia, 22050)

    def _frecuencia_de(self, calidades: list, variante: str) -> int:
        """Con qué frecuencia se le habla a esta voz, en kilohercios.

        La de los ajustes solo se usa si **esta voz la tiene**. Las premium
        están grabadas a 22 y no se remuestrean: pedirles 11 hace que acepten el
        parámetro y luego fallen al hablar, sin decir por qué.
        """
        suyas = [hercios for cual, hercios in calidades if cual == variante]
        if not suyas:
            suyas = [hercios for _cual, hercios in calidades]
        pedida = self._entero("frecuencia", 22)
        if pedida in suyas:
            return pedida
        if suyas:
            if pedida != suyas[0]:
                log.info("La voz no admite %d kHz; se usa la suya, %d kHz",
                         pedida, suyas[0])
            return suyas[0]
        return pedida

    def _variantes_declaradas(self, nombre: str) -> list:
        """Los nombres de las calidades de una voz."""
        return [calidad for calidad, _hercios in self._calidades_de(nombre)]

    def _calidades_de(self, nombre: str) -> list:
        """Las calidades de una voz con su frecuencia, tal como las declara."""
        for cual, _idioma, _sexo, variantes in self._voces:
            if cual == nombre:
                return list(variantes)
        return []

    def variantes(self) -> list:
        """Las calidades de la voz puesta, por si alguien las quiere listar."""
        return self._variantes_declaradas(self._voz)

    def opciones_de(self, clave: str):
        """Qué opciones tiene de verdad uno de sus ajustes de lista.

        El manifiesto no puede saberlo: las calidades y las frecuencias son de
        las voces, y las voces se copian después de armar el paquete. Ofrecer
        siete calidades cuando las voces solo tienen una es enseñar seis cosas
        que no hacen nada.

        Se miran **todas** las voces instaladas y no solo la puesta: si hay una
        compacta, su calidad tiene que poder elegirse aunque ahora mismo esté
        sonando otra.

        Devolver ``None`` deja las del manifiesto, que es lo que pasa con los
        ajustes que no dependen de las voces.
        """
        if clave == "variante":
            calidades = []
            for _nombre, _idioma, _sexo, suyas in self._voces:
                for cual, _hercios in suyas:
                    if cual not in calidades:
                        calidades.append(cual)
            if not calidades:
                return None
            salida = [("", _texto_de_calidad(""))]
            salida.extend((cual, _texto_de_calidad(cual))
                          for cual in sorted(calidades))
            return salida
        if clave == "frecuencia":
            hercios = sorted({uno for _n, _i, _s, suyas in self._voces
                              for _cual, uno in suyas})
            if not hercios:
                return None
            return [(uno, _("%d kHz") % uno) for uno in hercios]
        return None

    def establecer_velocidad(self, valor: int) -> None:
        """La velocidad, de la escala del visor a la de Vocalizer (50 a 400)."""
        porcentaje = max(0, min(100, 50 + int(valor) * 5))
        self._poner((PARAM_VELOCIDAD,
                     _desde_por_ciento(porcentaje, VELOCIDAD_MINIMA,
                                       VELOCIDAD_MAXIMA)))

    def establecer_volumen(self, valor: int) -> None:
        """El volumen, que aquí sí lo pone el propio motor."""
        self._volumen = max(0, min(100, int(valor)))
        self._poner((PARAM_VOLUMEN, self._volumen))

    @property
    def espera_maxima(self) -> float:
        """Cuánto puede tardar en empezar a sonar.

        Vocalizer sintetiza rápido, pero la primera frase con una voz recién
        elegida carga su base de datos, que son cientos de megas de disco.
        """
        try:
            return float(self._ajustes.get("espera_maxima", 8))
        except (TypeError, ValueError):
            return 8.0

    # -- hablar --------------------------------------------------------------

    def _recibir(self, instancia, usuario, mensaje) -> int:
        """El sonido llega por aquí, en dos pasos.

        Primero pide dónde escribir y se le prestan nuestros buffers; después
        avisa de que ya ha escrito y se copia lo que haya puesto. Los buffers
        son del objeto y se reutilizan: reservarlos en cada aviso sería
        reservar memoria cientos de veces por frase.
        """
        try:
            datos = ctypes.cast(mensaje.contents.pParam, POINTER(VE_OUTDATA))
            cual = mensaje.contents.eMessage
            if cual == MENSAJE_PIDE_BUFFER:
                datos.contents.pOutPcmBuf = ctypes.cast(self._pcm, c_void_p)
                datos.contents.cntPcmBufLen = c_size_t(TAMANO_PCM)
                datos.contents.pMrkList = ctypes.cast(self._marcas,
                                                      POINTER(VE_MARKINFO))
                datos.contents.cntMrkListLen = c_size_t(
                    TAMANO_MARCAS * ctypes.sizeof(VE_MARKINFO))
            elif cual == MENSAJE_BUFFER_LLENO:
                if datos.contents.cntPcmBufLen > 0:
                    self._trozos.append(
                        ctypes.string_at(datos.contents.pOutPcmBuf,
                                         datos.contents.cntPcmBufLen))
        except Exception as error:
            log.error("Fallo recogiendo el sonido de Vocalizer: %s", error)
        return CORRECTO

    def decir(self, texto: str, con_marcas: bool = False) -> bool:
        """Sintetiza la frase entera y la reproduce.

        ``con_marcas`` se ignora: son marcas de SAPI. Vocalizer entiende SSML,
        pero no es lo mismo, y colar unas por otras haría que leyera las
        etiquetas en voz alta.
        """
        if not texto or self._ve is None or self._instancia is None:
            return False
        self.detener()
        with self._cerrojo:
            self._trozos = []
            crudo = texto.encode("utf-8", "replace")
            entrada = VE_INTEXT()
            entrada.eTextFormat = TEXTO_NORMAL
            entrada.cntTextLength = c_size_t(len(crudo))
            # El texto se guarda en el objeto mientras dura la llamada: la
            # biblioteca lee del puntero y no se queda con una copia.
            self._texto_crudo = ctypes.create_string_buffer(crudo)
            entrada.szInText = ctypes.cast(self._texto_crudo, c_void_p)
            try:
                self._comprobar(
                    self._ve.ve_ttsProcessText2Speech(self._instancia,
                                                      ctypes.byref(entrada)),
                    "ve_ttsProcessText2Speech")
            except Exception as error:
                log.error("Vocalizer no ha podido sintetizar: %s", error)
                return False
            audio = b"".join(self._trozos)
            if not audio:
                return False
            return self._reproducir(audio)

    def _reproducir(self, pcm: bytes) -> bool:
        """Manda el sonido a BASS, que es quien lo saca por el altavoz."""
        try:
            from basskit.alto_nivel.reproductor import inicializar
            from basskit.constantes.bass import BASS_STREAM_PRESCAN
            from basskit.dlls.bass import bass
        except Exception as error:
            log.error("No está el reproductor de sonido: %s", error)
            return False
        if not self._bass:
            try:
                inicializar(-1, 44100)
            except Exception as error:
                # Puede estar ya inicializado por el reproductor DAISY, y
                # entonces esto falla y da igual: el sonido sale lo mismo.
                log.debug("BASS ya estaba listo: %s", error)
            self._bass = True
        onda = _envolver_en_wav(pcm, self._muestreo)
        self._memoria = ctypes.create_string_buffer(onda)
        canal = bass.BASS_StreamCreateFile(True, self._memoria, 0, len(onda),
                                           BASS_STREAM_PRESCAN)
        if not canal:
            log.error("BASS no ha podido abrir el sonido de Vocalizer")
            return False
        self._canal = canal
        self._pausado = False
        return bool(bass.BASS_ChannelPlay(canal, True))

    @staticmethod
    def con_tono(texto: str, tono: int) -> str:
        """El texto tal cual: el tono se ajusta en los ajustes del motor."""
        return texto

    def pausar(self) -> None:
        if self._canal and not self._pausado:
            from basskit.dlls.bass import bass

            bass.BASS_ChannelPause(self._canal)
            self._pausado = True

    def continuar(self) -> None:
        if self._canal and self._pausado:
            from basskit.dlls.bass import bass

            bass.BASS_ChannelPlay(self._canal, False)
            self._pausado = False

    def detener(self) -> None:
        self._pausado = False
        if self._canal:
            try:
                from basskit.dlls.bass import bass

                bass.BASS_ChannelStop(self._canal)
                bass.BASS_StreamFree(self._canal)
            except Exception as error:
                log.debug("Al detener Vocalizer: %s", error)
            self._canal = 0

    @property
    def pausada(self) -> bool:
        return self._pausado

    @property
    def hablando(self) -> bool:
        """Si está sonando ahora mismo.

        Una pausa cuenta como «sigue»: si dijera que no, el visor daría la frase
        por terminada y se saltaría el resto en cuanto alguien pausara.
        """
        if self._pausado:
            return True
        if not self._canal:
            return False
        try:
            from basskit.constantes.bass import BASS_ACTIVE_PLAYING
            from basskit.dlls.bass import bass

            return int(bass.BASS_ChannelIsActive(self._canal)) == BASS_ACTIVE_PLAYING
        except Exception:
            return False

    # -- cerrar --------------------------------------------------------------

    def _cerrar_instancia(self) -> None:
        if self._instancia is None:
            return
        try:
            self._ve.ve_ttsClose(self._instancia)
        except Exception as error:
            log.debug("Al cerrar la instancia: %s", error)
        self._instancia = None

    def cerrar(self) -> None:
        """Suelta el sonido y cierra Vocalizer entero."""
        self.detener()
        self._cerrar_instancia()
        if self._ve is None:
            return
        try:
            if self._clase is not None:
                self._ve.ve_ttsUnInitialize(self._clase)
            if self._instalacion is not None:
                self._plataforma.vplatform_ReleaseInterfaces(
                    ctypes.byref(self._instalacion))
        except Exception as error:
            log.debug("Al cerrar Vocalizer: %s", error)
        # Las bibliotecas no se descargan a mano: la de Vocalizer deja hilos
        # suyos en marcha y descargarla mientras corren cierra el programa
        # entero sin decir nada.  Se sueltan las referencias y ya.
        self._clase = None
        self._instalacion = None
        self._ve = None
        self._plataforma = None
        self._msvcr = None


#: Cómo se leen las calidades de Vocalizer.  Son sus nombres internos y no se
#: pueden cambiar; esto es solo para que la lista se entienda.
CALIDADES = {
    "": _("La mejor que tenga la voz"),
    "premium-high": _("Premium alta"),
    "premium": _("Premium"),
    "standard": _("Estándar"),
    "embedded-high": _("Compacta alta"),
    "embedded-pro": _("Compacta profesional"),
    "embedded": _("Compacta"),
}


def _texto_de_calidad(cual: str) -> str:
    """Cómo se lee una calidad. La que no se conozca sale con su nombre."""
    return CALIDADES.get(cual, cual)


#: De las tres letras que usa Vocalizer al código que usa el visor.  Solo están
#: los idiomas que Vocalizer tiene; el que no esté sale sin idioma y se puede
#: usar igual, solo que el visor no lo elegirá solo para una cita.
IDIOMAS = {
    "ARW": "ar", "BAE": "eu", "BAF": "eu", "CAE": "ca", "CAF": "ca",
    "CZC": "cs-CZ", "DAD": "da-DK", "DUB": "nl-BE", "DUN": "nl-NL",
    "ENA": "en-AU", "ENC": "en-CA", "ENE": "en-IE", "ENG": "en-GB",
    "ENI": "en-IN", "ENS": "en-ZA", "ENU": "en-US", "FIF": "fi-FI",
    "FRC": "fr-CA", "FRF": "fr-FR", "GED": "de-DE", "GRG": "el-GR",
    "HEI": "he-IL", "HIN": "hi-IN", "HUH": "hu-HU", "ITI": "it-IT",
    "JPJ": "ja-JP", "KOK": "ko-KR", "MAC": "zh-HK", "MNC": "zh-CN",
    "NON": "nb-NO", "PLP": "pl-PL", "PTB": "pt-BR", "PTP": "pt-PT",
    "ROR": "ro-RO", "RUR": "ru-RU", "SLS": "sk-SK", "SPE": "es-ES",
    "SPM": "es-MX", "SWS": "sv-SE", "THT": "th-TH", "TUT": "tr-TR",
    "TWT": "zh-TW", "VIV": "vi-VN",
}


def _codigo_de_idioma(tres: str) -> str:
    """El código del visor a partir de las tres letras de Vocalizer."""
    return IDIOMAS.get((tres or "").strip().upper(), "")


def _envolver_en_wav(pcm: bytes, muestreo: int) -> bytes:
    """Le pone a los datos crudos la cabecera que espera un reproductor.

    Vocalizer devuelve muestras a secas —mono, dieciséis bits— y BASS quiere un
    archivo. La cabecera de un WAV son cuarenta y cuatro bytes y escribirlos
    aquí evita pasar por un archivo temporal en cada frase.
    """
    import struct

    canales, bits = 1, 16
    alineacion = canales * bits // 8
    return (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt "
            + struct.pack("<IHHIIHH", 16, 1, canales, muestreo,
                          muestreo * alineacion, alineacion, bits)
            + b"data" + struct.pack("<I", len(pcm)) + pcm)


def crear(carpeta, ajustes):
    """Lo que el visor llama para poner esta voz. Es la única entrada."""
    return MotorVocalizer(Path(carpeta), dict(ajustes or {}))
