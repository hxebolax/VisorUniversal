# -*- coding: utf-8 -*-
"""Convertir un documento en audio para escucharlo fuera del programa.

Genera un **MP3 por capítulo** —para pasarlo al móvil o al coche— o **un solo
archivo** con el documento entero.  Lo lee la misma voz del sistema que lee
dentro del programa, con la misma velocidad, el mismo volumen y el mismo
diccionario de pronunciación, de manera que lo que se escucha en el coche suena
exactamente igual que lo que se oía en casa.

Cómo funciona, que tiene su miga:

1. **SAPI escribe a un archivo** en vez de a los altavoces.  Se le da un
   ``SpFileStream`` como salida y habla igual que siempre, solo que en silencio
   y a máxima velocidad de proceso: un capítulo de media hora se genera en unos
   segundos.
2. **El WAV se convierte a MP3** con BASS, a través de *basskit*, que es la
   misma biblioteca con la que suenan los libros DAISY.  Un WAV de un libro
   entero ocupa gigas; en MP3 son unas decenas de megas.

Todo esto es largo, así que va con progreso y se puede cancelar entre trozo y
trozo.  El avance se mide en **caracteres dichos** y no en capítulos: los
capítulos son de tamaños muy distintos y una barra que salta del 10 al 40 por
ciento no dice nada.

Se ejecuta siempre desde un hilo aparte, y por eso el módulo inicializa COM por
su cuenta: SAPI es un objeto COM y cada hilo que lo use tiene que anunciarse.
"""

from __future__ import annotations

import os
import re
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from . import segmentador
from .idioma import _
from .marcas import TipoMarca
from .registro import obtener_registro
from .voz import VELOCIDAD_MAXIMA, VELOCIDAD_MINIMA, sapi_desde_porcentaje

log = obtener_registro(__name__)

#: Formato de audio con el que habla SAPI: 44 kHz, 16 bits, mono.  Es el valor
#: 34 de la enumeración ``SpeechAudioFormatType``.  Mono porque una voz
#: sintética no tiene nada que decir en estéreo, y 44 kHz porque es lo que el
#: codificador de MP3 espera sin remuestrear.
FORMATO_SAPI = 34

#: Modo de apertura del archivo de SAPI: crear para escribir.
CREAR_PARA_ESCRIBIR = 3

#: Calidad del MP3, en kilobits por segundo.  96 es de sobra para una voz:
#: subirlo engorda el archivo sin que se note, y bajarlo empieza a sonar a
#: teléfono.
CALIDAD = 96

#: Tamaño de los trozos en que se parte el texto antes de dárselo a la voz, en
#: caracteres.  Trozos grandes van más rápido; trozos pequeños permiten
#: cancelar antes y dar el avance con más detalle.  Con dos mil caracteres, un
#: cancelado responde en menos de un segundo.
TROZO = 2000

#: Caracteres que Windows no admite en un nombre de archivo.
PROHIBIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

#: Formatos de salida que se ofrecen.
MP3 = "mp3"
WAV = "wav"


@dataclass
class Capitulo:
    """Un tramo del documento que se convierte en un archivo."""

    titulo: str
    inicio: int
    fin: int

    @property
    def largo(self) -> int:
        """Caracteres que tiene, que es lo que mide cuánto va a tardar."""
        return max(0, self.fin - self.inicio)


def nombre_seguro(texto: str, maximo: int = 60) -> str:
    """Convierte un título en un nombre de archivo que Windows acepte."""
    limpio = PROHIBIDOS.sub("", " ".join(str(texto or "").split())).strip(" .")
    if len(limpio) > maximo:
        limpio = limpio[:maximo].rsplit(" ", 1)[0]
    return limpio or _("Sin título")


def capitulos_de(documento) -> list[Capitulo]:
    """Parte el documento en capítulos.

    Se usan los saltos de sección, que es lo que el conversor pone entre los
    archivos de un EPUB.  Si el documento no los trae —un PDF, un texto suelto—
    se prueba con los encabezados de nivel 1, y si tampoco los hay se devuelve
    el documento entero como un único capítulo: es preferible un archivo grande
    a partirlo por donde no toca.
    """
    texto = documento.texto
    largo = len(texto)
    if not largo:
        return []

    cortes: list[tuple[int, str]] = []
    for tipo in (TipoMarca.SALTO_SECCION, TipoMarca.ENCABEZADO1):
        grupo = documento.marcas.grupo(tipo)
        if len(grupo) >= 2:
            for marca in grupo.marcas:
                rotulo = marca.texto.strip() or documento.primera_linea_con_texto(marca.posicion)
                cortes.append((marca.posicion, rotulo))
            break

    if not cortes:
        titulo = documento.metadatos.titulo or _("Documento")
        return [Capitulo(titulo, 0, largo)]

    # Lo que haya antes del primer corte —portada, créditos— es un capítulo
    # más: dejarlo fuera perdería texto sin avisar.
    capitulos: list[Capitulo] = []
    if cortes[0][0] > 0:
        capitulos.append(Capitulo(_("Principio"), 0, cortes[0][0]))
    for numero, (posicion, rotulo) in enumerate(cortes):
        fin = cortes[numero + 1][0] if numero + 1 < len(cortes) else largo
        if fin > posicion:
            capitulos.append(Capitulo(rotulo or _("Capítulo %d") % (numero + 1), posicion, fin))
    return capitulos


def documento_entero(documento) -> list[Capitulo]:
    """El documento como un único capítulo, para exportarlo a un solo archivo."""
    titulo = documento.metadatos.titulo or _("Documento")
    return [Capitulo(titulo, 0, len(documento.texto))]


def _trozos(texto: str) -> list[str]:
    """Parte un texto en trozos que se puedan decir de uno en uno.

    Se corta **por frases** y no por caracteres: partir a mitad de frase deja
    una pausa antinatural justo ahí, y con un libro entero eso son cientos de
    pausas donde no van.
    """
    partes: list[str] = []
    actual: list[str] = []
    cuenta = 0
    posicion = 0
    largo = len(texto)
    while posicion < largo:
        inicio, fin = segmentador.siguiente_frase(texto, posicion)
        if inicio >= fin:
            break
        frase = segmentador.para_decir(texto[inicio:fin])
        if frase:
            actual.append(frase)
            cuenta += len(frase)
            if cuenta >= TROZO:
                partes.append(" ".join(actual))
                actual = []
                cuenta = 0
        posicion = fin
    if actual:
        partes.append(" ".join(actual))
    # Un texto sin ninguna frase reconocible (una tabla de números, por
    # ejemplo) se dice tal cual antes que quedarse en silencio.
    if not partes and texto.strip():
        partes.append(segmentador.para_decir(texto))
    return partes


class Locutor:
    """La voz de Windows escribiendo a un archivo en vez de a los altavoces.

    Se usa como contexto, de forma que el archivo se cierre pase lo que pase:
    un ``SpFileStream`` que se queda abierto deja un WAV sin cabecera válida y,
    peor, retiene el archivo hasta que muere el programa.
    """

    def __init__(self, voz: str = "", velocidad: int = 50, volumen: int = 100) -> None:
        self.nombre_voz = voz
        self.velocidad = velocidad
        self.volumen = volumen
        self._voz = None
        self._flujo = None

    def preparar(self) -> None:
        """Conecta con SAPI en este hilo y ajusta voz, velocidad y volumen."""
        import pythoncom
        import win32com.client

        # Cada hilo que use COM tiene que anunciarse.  El de la interfaz ya lo
        # hace wxPython; este es nuestro, así que nos toca.
        pythoncom.CoInitialize()
        self._voz = win32com.client.Dispatch("SAPI.SpVoice")
        if self.nombre_voz:
            fichas = self._voz.GetVoices()
            for numero in range(fichas.Count):
                if fichas.Item(numero).GetDescription() == self.nombre_voz:
                    self._voz.Voice = fichas.Item(numero)
                    break
        self._voz.Rate = max(VELOCIDAD_MINIMA,
                             min(VELOCIDAD_MAXIMA, sapi_desde_porcentaje(self.velocidad)))
        self._voz.Volume = max(0, min(100, int(self.volumen)))

    def abrir(self, destino: Path) -> None:
        """Empieza a escribir en un archivo WAV."""
        import win32com.client

        self.cerrar()
        flujo = win32com.client.Dispatch("SAPI.SpFileStream")
        flujo.Format.Type = FORMATO_SAPI
        flujo.Open(str(destino), CREAR_PARA_ESCRIBIR)
        self._voz.AudioOutputStream = flujo
        self._flujo = flujo

    def decir(self, texto: str) -> None:
        """Escribe un trozo de texto en el archivo abierto.

        Es una llamada **síncrona**: vuelve cuando el trozo está escrito, que es
        justo lo que hace falta para poder ir informando del avance.
        """
        if texto.strip():
            self._voz.Speak(texto)

    def cerrar(self) -> None:
        """Cierra el archivo que estuviera abierto."""
        if self._flujo is not None:
            try:
                self._flujo.Close()
            except Exception as error:
                log.warning("No se ha podido cerrar el archivo de audio: %s", error)
            self._flujo = None

    def soltar(self) -> None:
        """Cierra todo y suelta COM en este hilo."""
        self.cerrar()
        self._voz = None
        try:
            import pythoncom

            pythoncom.CoUninitialize()
        except Exception:
            pass


def unir_wav(origenes: list[Path], destino: Path) -> list[int]:
    """Pega varios WAV en uno solo y dice dónde empieza cada uno.

    Se hace con la biblioteca estándar y sobre los datos crudos, sin
    descodificar nada: todos los trozos los ha escrito la misma voz con el
    mismo formato, así que basta con copiar sus muestras una detrás de otra.

    :return: El instante de comienzo de cada trozo, en milisegundos.  Es lo que
             hace falta para escribir las marcas de capítulo.
    """
    comienzos: list[int] = []
    salida = None
    acumulado = 0
    try:
        for origen in origenes:
            with wave.open(str(origen), "rb") as entrada:
                if salida is None:
                    salida = wave.open(str(destino), "wb")
                    salida.setparams(entrada.getparams())
                cuadros = entrada.getnframes()
                velocidad = entrada.getframerate() or 1
                comienzos.append(int(acumulado * 1000 / velocidad))
                acumulado += cuadros
                # Se copia por trozos y no de una vez: un libro entero en WAV
                # son varios gigabytes y no caben en memoria.
                restantes = cuadros
                while restantes > 0:
                    lote = entrada.readframes(min(restantes, 1 << 20))
                    if not lote:
                        break
                    salida.writeframes(lote)
                    restantes -= min(restantes, 1 << 20)
    finally:
        if salida is not None:
            salida.close()
    return comienzos


def _duraciones(comienzos: list[int], total: int) -> list[tuple[int, int]]:
    """Convierte los comienzos en pares ``(inicio, fin)`` en milisegundos."""
    pares = []
    for numero, inicio in enumerate(comienzos):
        fin = comienzos[numero + 1] if numero + 1 < len(comienzos) else total
        pares.append((inicio, max(inicio, fin)))
    return pares


def duracion_de_wav(archivo: Path) -> int:
    """Cuánto dura un WAV, en milisegundos."""
    try:
        with wave.open(str(archivo), "rb") as entrada:
            return int(entrada.getnframes() * 1000 / (entrada.getframerate() or 1))
    except Exception as error:                     # pragma: no cover
        log.debug("No se ha podido medir %s: %s", archivo, error)
        return 0


def grabador_de_frases(voz: str = "", velocidad: int = 50, volumen: int = 100,
                       tabla=None, cancelado=None):
    """Devuelve una función que graba una lista de frases en un solo archivo.

    Es lo que hace falta para escribir un libro DAISY con el texto y el audio
    sincronizados: cada frase se graba por separado —que es la única forma de
    saber **cuánto dura cada una**—, se mide, y todas se pegan en un archivo por
    capítulo.  El resultado es un audio corrido con una tabla de instantes que
    dice qué frase suena en cada momento.

    La función devuelta recibe ``(textos, destino)`` y devuelve
    ``(comienzos, duración total)``, los dos en milisegundos.

    :param cancelado: Se consulta entre frase y frase.
    """
    locutor = Locutor(voz, velocidad, volumen)
    locutor.preparar()

    def grabar(textos: list[str], destino: Path) -> tuple[list[int], int]:
        destino = Path(destino)
        trozos_carpeta = destino.parent / ".frases"
        trozos_carpeta.mkdir(parents=True, exist_ok=True)
        trozos: list[Path] = []
        try:
            for numero, texto in enumerate(textos):
                if cancelado is not None and cancelado():
                    break
                trozo = trozos_carpeta / ("%06d.wav" % numero)
                locutor.abrir(trozo)
                locutor.decir(tabla.aplicar(texto) if tabla is not None else texto)
                locutor.cerrar()
                trozos.append(trozo)
            if not trozos:
                return [], 0
            comienzos = unir_wav(trozos, destino)
            return comienzos, duracion_de_wav(destino)
        finally:
            for trozo in trozos:
                try:
                    trozo.unlink(missing_ok=True)
                except OSError:
                    pass
            try:
                trozos_carpeta.rmdir()
            except OSError:
                pass

    grabar.soltar = locutor.soltar
    return grabar


def hay_codificador() -> bool:
    """Indica si se puede convertir a MP3.

    Sin BASS solo se puede dejar el WAV, que ocupa muchísimo más pero sigue
    siendo un archivo de audio que cualquier reproductor abre.
    """
    try:
        from basskit.alto_nivel.codificador import Codificador  # noqa: F401
    except Exception:
        return False
    return True


def _a_mp3(origen: Path, destino: Path) -> None:
    """Convierte un WAV en MP3 y borra el WAV."""
    from basskit.alto_nivel.codificador import Codificador
    from basskit.alto_nivel.reproductor import inicializar

    # BASS necesita estar inicializado aunque solo se vaya a codificar; si el
    # reproductor DAISY ya lo hizo, llamarlo otra vez no molesta.
    try:
        inicializar()
    except Exception:
        pass
    Codificador().convertir(str(origen), str(destino), "-b %d" % CALIDAD)
    try:
        origen.unlink(missing_ok=True)
    except OSError:
        pass


def exportar(documento, carpeta: Path, capitulos: list[Capitulo],
             formato: str = MP3, voz: str = "", velocidad: int = 50,
             volumen: int = 100, tabla=None,
             progreso: Optional[Callable[[int, int, str], None]] = None,
             cancelado: Optional[Callable[[], bool]] = None,
             un_solo_archivo: bool = False, titulo: str = "",
             autor: str = "") -> list[Path]:
    """Convierte los capítulos indicados en archivos de audio.

    :param carpeta: Dónde se dejan los archivos.
    :param capitulos: Tramos que hay que generar; uno solo si se quiere un
                      único archivo con todo.
    :param un_solo_archivo: Si los capítulos se pegan en un único archivo con
                            **marcas de capítulo** dentro.  Es lo que permite
                            saltar de uno a otro en el reproductor del móvil o
                            del coche, en lugar de tener diez horas seguidas
                            por las que solo se puede avanzar a ciegas.
    :param titulo: Título del libro, para la etiqueta del archivo.
    :param autor: Autor del libro, para la etiqueta del archivo.
    :param formato: ``"mp3"`` o ``"wav"``.
    :param tabla: Tabla de pronunciación que aplicar, o ``None``.
    :param progreso: Se llama con ``(hecho, total, detalle)`` en caracteres.
    :param cancelado: Se consulta entre trozo y trozo; devolviendo ``True`` se
                      para y se borra lo que quedara a medias.
    :return: Los archivos generados, en orden.
    :raises RuntimeError: Si no hay voz con la que hablar.
    """
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    texto = documento.texto
    total = sum(capitulo.largo for capitulo in capitulos) or 1
    hecho = 0
    generados: list[Path] = []
    ancho = max(2, len(str(len(capitulos))))

    # Con un solo archivo los trozos se generan igual, uno por capítulo, y se
    # pegan al final: es la única forma de saber **cuánto dura cada uno**, que
    # es exactamente lo que hace falta para poner las marcas.
    trabajo = carpeta / ".trozos" if un_solo_archivo and len(capitulos) > 1 else carpeta
    if trabajo is not carpeta:
        trabajo.mkdir(parents=True, exist_ok=True)

    locutor = Locutor(voz, velocidad, volumen)
    try:
        locutor.preparar()
    except Exception as error:
        locutor.soltar()
        raise RuntimeError(
            _("No se ha podido usar la voz del sistema para grabar: %s") % error) from error

    a_medias: Optional[Path] = None
    try:
        for numero, capitulo in enumerate(capitulos, start=1):
            if cancelado is not None and cancelado():
                break
            if len(capitulos) == 1:
                base = nombre_seguro(capitulo.titulo)
            else:
                base = "%s - %s" % (str(numero).zfill(ancho), nombre_seguro(capitulo.titulo))
            temporal = trabajo / (base + ".wav")
            a_medias = temporal
            if progreso is not None:
                progreso(hecho, total, _("Grabando: %s") % capitulo.titulo)
            locutor.abrir(temporal)
            for trozo in _trozos(texto[capitulo.inicio:capitulo.fin]):
                if cancelado is not None and cancelado():
                    break
                locutor.decir(tabla.aplicar(trozo) if tabla is not None else trozo)
                hecho += len(trozo)
                if progreso is not None:
                    progreso(min(hecho, total), total, _("Grabando: %s") % capitulo.titulo)
            locutor.cerrar()

            if cancelado is not None and cancelado():
                temporal.unlink(missing_ok=True)
                break

            if un_solo_archivo and len(capitulos) > 1:
                # Los trozos se comprimen al final, ya pegados: comprimir cada
                # uno y luego juntarlos daría un archivo con un corte audible
                # en cada empalme.
                a_medias = None
                generados.append(temporal)
                continue

            if formato == MP3 and hay_codificador():
                final = carpeta / (base + ".mp3")
                if progreso is not None:
                    progreso(min(hecho, total), total,
                             _("Comprimiendo: %s") % capitulo.titulo)
                try:
                    _a_mp3(temporal, final)
                except Exception as error:
                    # Si la compresión falla nos quedamos con el WAV: peor es
                    # perder media hora de grabación por no poder comprimirla.
                    log.warning("No se ha podido comprimir «%s» a MP3: %s", base, error)
                    final = temporal
            else:
                final = temporal
            a_medias = None
            generados.append(final)
            log.info("Audio generado: %s", final.name)
    finally:
        locutor.soltar()
        # Un archivo a medias no vale para nada y confunde: se borra.
        if a_medias is not None:
            try:
                a_medias.unlink(missing_ok=True)
            except OSError:
                pass

    if un_solo_archivo and len(capitulos) > 1:
        if cancelado is not None and cancelado():
            _borrar_todos(generados, trabajo)
            return []
        if progreso is not None:
            progreso(total, total, _("Uniendo los capítulos..."))
        return _juntar(generados, capitulos, carpeta, trabajo, formato,
                       titulo, autor, progreso, total)
    return generados


def _borrar_todos(archivos: list[Path], carpeta_trozos: Path) -> None:
    """Limpia los trozos y la carpeta donde estaban."""
    for archivo in archivos:
        try:
            Path(archivo).unlink(missing_ok=True)
        except OSError:
            pass
    try:
        carpeta_trozos.rmdir()
    except OSError:
        pass


def _juntar(trozos: list[Path], capitulos: list[Capitulo], carpeta: Path,
            carpeta_trozos: Path, formato: str, titulo: str, autor: str,
            progreso, total: int) -> list[Path]:
    """Pega los trozos en un archivo y le pone las marcas de capítulo."""
    from . import id3

    if not trozos:
        return []
    base = nombre_seguro(titulo or capitulos[0].titulo) or "audiolibro"
    unido = carpeta / (base + ".wav")
    comienzos = unir_wav(trozos, unido)
    _borrar_todos(trozos, carpeta_trozos)

    duracion_total = duracion_de_wav(unido)
    marcas = [id3.Capitulo(capitulo.titulo, inicio, fin)
              for capitulo, (inicio, fin)
              in zip(capitulos, _duraciones(comienzos, duracion_total))]

    if formato == MP3 and hay_codificador():
        final = carpeta / (base + ".mp3")
        if progreso is not None:
            progreso(total, total, _("Comprimiendo el archivo..."))
        try:
            _a_mp3(unido, final)
        except Exception as error:
            log.warning("No se ha podido comprimir el audiolibro: %s", error)
            final = unido
    else:
        final = unido

    try:
        if final.suffix.lower() == ".mp3":
            id3.escribir_capitulos(final, marcas, titulo or base, autor)
        else:
            # Un WAV no lleva capítulos dentro, así que se deja al lado una
            # hoja de pistas, que es lo que sabe leer un reproductor de
            # escritorio.
            hoja = final.with_suffix(".cue")
            hoja.write_text(id3.hoja_de_pistas(marcas, final.name, titulo, autor),
                            encoding="utf-8")
            log.info("Hoja de pistas escrita: %s", hoja.name)
            return [final, hoja]
    except OSError as error:
        log.warning("No se han podido escribir las marcas de capítulo: %s", error)
    return [final]


def tamano_total(archivos: list[Path]) -> int:
    """Suma lo que ocupan los archivos generados."""
    total = 0
    for archivo in archivos:
        try:
            total += os.path.getsize(archivo)
        except OSError:
            pass
    return total
