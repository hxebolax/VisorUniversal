# -*- coding: utf-8 -*-
"""Síntesis de los sonidos de navegación.

Los sonidos no se distribuyen como archivos: se **generan** la primera vez
que arranca la aplicación y se guardan en ``data/sonidos``.  Así:

* la aplicación no depende de archivos externos que puedan faltar;
* el volumen se aplica al generarlos, sin necesidad de un mezclador;
* añadir un sonido nuevo es añadir una línea a :data:`PERFILES`.

Cada sonido es una secuencia de fragmentos elementales (un tono, un
deslizamiento entre dos frecuencias o un golpe de ruido) que se concatenan.
Todos duran menos de una décima de segundo: la señal debe informar sin
estorbar a la voz del lector de pantalla.

El diseño acústico sigue una lógica sencilla para que sea fácil de aprender:

* **Encabezados**: un tono limpio cuya altura baja al aumentar el nivel, de
  modo que el nivel 1 suena agudo y el 6 grave.
* **Imágenes y figuras**: dos toques ascendentes, como un obturador.
* **Tablas**: un acorde grave y estable, «sólido» como una rejilla.
* **Listas**: varios toques breves; un solo toque para cada elemento.
* **Separadores y páginas**: ruido filtrado, como el roce de una hoja.
* **Avisos**: tonos graves, claramente distintos de los de contenido.
"""

from __future__ import annotations

import array
import math
import random
import wave
from pathlib import Path

from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

#: Frecuencia de muestreo de los archivos generados.
MUESTREO = 44100

#: Amplitud máxima de una muestra de 16 bits con algo de margen.
MAXIMO = 30000


# ---------------------------------------------------------------------------
# Fragmentos elementales
# ---------------------------------------------------------------------------

def _envolvente(posicion: int, total: int, ataque: int, caida: int) -> float:
    """Curva de volumen de un fragmento, para que no suene un chasquido.

    Un tono que empieza y acaba de golpe produce un «clic» audible.  Subir y
    bajar el volumen en unos pocos milisegundos lo evita.
    """
    if posicion < ataque:
        return posicion / ataque
    restante = total - posicion
    if restante < caida:
        return restante / caida
    return 1.0


def tono(frecuencia_inicial: float, frecuencia_final: float, duracion: float,
         amplitud: float = 1.0, armonico: float = 0.0) -> list[float]:
    """Genera un tono, opcionalmente deslizándose entre dos frecuencias.

    :param frecuencia_inicial: Frecuencia en hercios al empezar.
    :param frecuencia_final: Frecuencia en hercios al terminar.
    :param duracion: Duración en segundos.
    :param amplitud: Volumen relativo (0 a 1).
    :param armonico: Proporción del segundo armónico, que da un timbre menos
                     plano que el de una onda senoidal pura.
    """
    total = max(int(MUESTREO * duracion), 1)
    ataque = max(int(MUESTREO * 0.004), 1)
    caida = max(int(MUESTREO * 0.020), 1)
    muestras: list[float] = []
    fase = 0.0
    for indice in range(total):
        avance = indice / total
        frecuencia = frecuencia_inicial + (frecuencia_final - frecuencia_inicial) * avance
        fase += 2.0 * math.pi * frecuencia / MUESTREO
        valor = math.sin(fase)
        if armonico:
            valor += armonico * math.sin(2.0 * fase)
        muestras.append(valor * amplitud * _envolvente(indice, total, ataque, caida))
    return muestras


def acorde(frecuencias: tuple[float, ...], duracion: float, amplitud: float = 1.0) -> list[float]:
    """Genera varias frecuencias sonando a la vez."""
    total = max(int(MUESTREO * duracion), 1)
    ataque = max(int(MUESTREO * 0.005), 1)
    caida = max(int(MUESTREO * 0.030), 1)
    factor = amplitud / max(len(frecuencias), 1)
    muestras: list[float] = []
    for indice in range(total):
        valor = 0.0
        for frecuencia in frecuencias:
            valor += math.sin(2.0 * math.pi * frecuencia * indice / MUESTREO)
        muestras.append(valor * factor * _envolvente(indice, total, ataque, caida))
    return muestras


def ruido(duracion: float, amplitud: float = 1.0, suavizado: float = 0.35,
          semilla: int = 1) -> list[float]:
    """Genera un golpe de ruido filtrado, parecido al roce de una hoja.

    El suavizado es un filtro de paso bajo de primer orden: cuanto menor es
    el valor, más grave y apagado suena el ruido.  La semilla fija garantiza
    que el sonido sea siempre idéntico.
    """
    total = max(int(MUESTREO * duracion), 1)
    ataque = max(int(MUESTREO * 0.003), 1)
    caida = max(int(MUESTREO * 0.040), 1)
    generador = random.Random(semilla)
    muestras: list[float] = []
    anterior = 0.0
    for indice in range(total):
        crudo = generador.uniform(-1.0, 1.0)
        anterior = anterior + suavizado * (crudo - anterior)
        muestras.append(anterior * amplitud * _envolvente(indice, total, ataque, caida))
    return muestras


def silencio(duracion: float) -> list[float]:
    """Genera una pausa."""
    return [0.0] * max(int(MUESTREO * duracion), 1)


# ---------------------------------------------------------------------------
# Catálogo de sonidos
# ---------------------------------------------------------------------------

def _perfiles() -> dict[str, list[float]]:
    """Construye la forma de onda de cada sonido de la aplicación."""
    catalogo: dict[str, list[float]] = {}

    # Encabezados: mismo timbre, altura decreciente según el nivel.
    alturas = (1046.5, 880.0, 740.0, 622.3, 523.3, 440.0)
    for nivel, altura in enumerate(alturas, start=1):
        catalogo["encabezado%d" % nivel] = tono(altura, altura, 0.075, 0.55, armonico=0.18)

    # Enlace: un toque agudo y muy breve.
    catalogo["enlace"] = tono(1318.5, 1318.5, 0.035, 0.42)

    # Imagen y figura: dos toques ascendentes, como un obturador.
    catalogo["imagen"] = tono(700.0, 900.0, 0.032, 0.45) + silencio(0.018) + \
        tono(1200.0, 1500.0, 0.038, 0.45)
    catalogo["figura"] = tono(600.0, 780.0, 0.036, 0.45) + silencio(0.020) + \
        tono(980.0, 1180.0, 0.036, 0.45) + silencio(0.020) + \
        tono(1400.0, 1500.0, 0.030, 0.40)

    # Tabla: acorde grave y estable.
    catalogo["tabla"] = acorde((294.0, 392.0, 587.0), 0.110, 0.55)

    # Listas: tres toques para la lista, uno para cada elemento.
    toque = tono(880.0, 880.0, 0.022, 0.38)
    pausa = silencio(0.016)
    catalogo["lista"] = toque + pausa + toque + pausa + toque
    catalogo["elemento_lista"] = tono(740.0, 740.0, 0.024, 0.30)

    # Separador y página: ruido, como el paso de una hoja.
    catalogo["separador"] = ruido(0.060, 0.30, 0.20, semilla=7)
    catalogo["pagina"] = ruido(0.095, 0.34, 0.45, semilla=11)

    # Sección: un deslizamiento ascendente, más largo, de «capítulo nuevo».
    catalogo["seccion"] = tono(392.0, 784.0, 0.130, 0.45, armonico=0.12)

    # Cita: tono cálido y suave.
    catalogo["cita"] = tono(466.0, 440.0, 0.090, 0.35, armonico=0.30)

    # Fórmula: dos toques con un salto de quinta, que suena «matemático» sin
    # parecerse a ninguno de los otros.
    catalogo["formula"] = tono(659.3, 659.3, 0.030, 0.40) + silencio(0.016) + \
        tono(987.8, 987.8, 0.040, 0.40)

    # Código: tres toques secos y a la misma altura, como una máquina de
    # escribir.  Ni sube ni baja a propósito: los sonidos que se mueven ya
    # están cogidos, y uno plano y repetido se distingue de todos ellos.
    seco = tono(880.0, 880.0, 0.022, 0.34)
    corte = silencio(0.020)
    catalogo["codigo"] = seco + corte + seco + corte + seco

    # Marcadores y notas.
    catalogo["marcador"] = tono(1174.7, 1174.7, 0.055, 0.45)
    catalogo["nota"] = tono(987.8, 987.8, 0.045, 0.42) + silencio(0.015) + \
        tono(1318.5, 1318.5, 0.055, 0.42)

    # Avisos: siempre graves, para que no se confundan con el contenido.
    catalogo["limite"] = tono(196.0, 165.0, 0.130, 0.40, armonico=0.45)
    catalogo["error"] = tono(147.0, 110.0, 0.220, 0.45, armonico=0.55)
    catalogo["vuelta"] = tono(523.3, 392.0, 0.090, 0.35)

    # Mientras la voz se prepara.  Va flojo y corto a propósito: se repite cada
    # segundo y pico hasta que la voz empieza, y un sonido que se repite tiene
    # que poder oírse veinte veces seguidas sin cansar.
    catalogo["esperando"] = tono(880.0, 880.0, 0.045, 0.22)

    # Apertura y cierre de libro.
    catalogo["abrir"] = tono(523.3, 659.3, 0.070, 0.40) + silencio(0.012) + \
        tono(784.0, 1046.5, 0.090, 0.40)
    catalogo["cerrar"] = tono(784.0, 523.3, 0.090, 0.35)
    catalogo["encontrado"] = tono(1046.5, 1318.5, 0.055, 0.40)

    return catalogo


#: Nombres de todos los sonidos que genera la aplicación.
NOMBRES = tuple(sorted(_perfiles()))


def _escribir_wav(destino: Path, muestras: list[float], volumen: float) -> None:
    """Guarda una forma de onda como archivo WAV de 16 bits."""
    escala = MAXIMO * max(0.0, min(1.0, volumen))
    datos = array.array("h", (int(max(-1.0, min(1.0, valor)) * escala) for valor in muestras))
    with wave.open(str(destino), "wb") as archivo:
        archivo.setnchannels(1)
        archivo.setsampwidth(2)
        archivo.setframerate(MUESTREO)
        archivo.writeframes(datos.tobytes())


def generar(carpeta: Path, volumen: int = 70) -> list[str]:
    """Genera (o regenera) todos los archivos de sonido.

    :param carpeta: Carpeta de destino, normalmente ``data/sonidos``.
    :param volumen: Volumen de 0 a 100, que se aplica a la amplitud.
    :return: Lista de los nombres generados.
    """
    carpeta.mkdir(parents=True, exist_ok=True)
    factor = max(0, min(100, volumen)) / 100.0
    generados: list[str] = []
    for nombre, muestras in _perfiles().items():
        destino = carpeta / (nombre + ".wav")
        try:
            _escribir_wav(destino, muestras, factor)
            generados.append(nombre)
        except OSError as error:
            log.error("No se ha podido generar el sonido %s: %s", nombre, error)
    log.info("Sonidos generados en %s (%d archivos, volumen %d%%)", carpeta, len(generados), volumen)
    return generados


def faltan_sonidos(carpeta: Path) -> bool:
    """Indica si falta algún archivo de sonido en la carpeta."""
    return any(not (carpeta / (nombre + ".wav")).exists() for nombre in NOMBRES)
