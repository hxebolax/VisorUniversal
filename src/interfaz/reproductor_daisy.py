# -*- coding: utf-8 -*-
"""Reproductor de libros DAISY: escuchar la grabación y navegar por ella.

Un libro DAISY grabado no se escucha como un archivo de música.  Se escucha
como un libro: se salta al capítulo cinco, se retrocede una frase porque no se
ha entendido, se va a la página 87 porque lo dice el profesor, se sube la
velocidad porque el narrador va lento.  Todo eso está en la norma —los ``<par>``
del SMIL y los puntos del NCC son exactamente eso— y es lo que este módulo
convierte en algo que se maneja con el teclado.

Los niveles
-----------

Los reproductores DAISY de toda la vida —los aparatos de sobremesa, el
Victor Reader— tienen un mando de **nivel**: se elige si «anterior» y
«siguiente» significan capítulo, sección, página o frase, y luego se navega con
dos teclas.  Es un sistema muy bueno para manejar de oído, porque con dos dedos
se recorre un libro entero, y aquí está igual: :meth:`ReproductorDaisy.cambiar_nivel`
elige la unidad y :meth:`punto_anterior` y :meth:`punto_siguiente` se mueven por
ella.  Los niveles que se ofrecen son los que el libro tenga de verdad.

El cursor y la voz
------------------

El texto y la grabación van cosidos: al montar el libro, cada frase del SMIL
dejó en el texto un ancla ``daisy-N`` (véase :mod:`formatos.daisy`).  Con eso,
:meth:`posicion_de` y :meth:`frase_en` traducen en los dos sentidos, y de ahí
salen las dos cosas que se esperan: que al darle a reproducir empiece **por
donde está el cursor**, y que mientras suena el cursor **vaya siguiendo** a la
voz para que el lector de pantalla pueda consultar lo que se está oyendo.

Por qué no se corta el sonido entre frases
------------------------------------------

Casi siempre, la frase siguiente es el trozo contiguo del mismo archivo.  En
ese caso no se hace nada: se deja sonar y solo se anota que ya vamos por la
frase siguiente.  Solo se toca la reproducción cuando de verdad hay que saltar.
Sin ese cuidado, un libro con seis mil frases sonaría con seis mil cortes.
"""

from __future__ import annotations

import bisect
import shutil
import tempfile
from pathlib import Path

import wx

from interfaz.dialogos import ayuda_opcion
from interfaz.accesible import etiquetar, fila_etiquetada
from interfaz.anuncios import Voz
from nucleo import audio
from nucleo.daisy import Punto
from nucleo.idioma import _
from nucleo.registro import obtener_registro, registrar_excepcion

log = obtener_registro(__name__)

MARGEN = 8

#: Cada cuánto se mira por dónde va la grabación, en milisegundos.  Con 100 el
#: paso de frase se nota inmediato y el gasto es inapreciable.
LATIDO = 100

#: Margen con el que se da por terminada una frase.  BASS devuelve la posición
#: con un pelo de retraso, y sin este margen la última frase de un archivo se
#: quedaría esperando un final que ya ha pasado.
HOLGURA = 0.05

#: Cuánto sube o baja la velocidad de una vez, en puntos porcentuales.  Es el
#: mismo para las teclas y para el control de la ventana: si fueran distintos,
#: la velocidad acabaría en valores como 91 y sumarle un paso daría 101, que es
#: exactamente lo que pasaba.
PASO_VELOCIDAD = 5

#: Cuánto sube o baja el volumen de una vez.
PASO_VOLUMEN = 5


class Nivel:
    """Una unidad de navegación: capítulos, secciones, páginas o frases."""

    __slots__ = ("clave", "nombre", "posiciones")

    def __init__(self, clave: str, nombre: str, posiciones: list[int]) -> None:
        self.clave = clave
        self.nombre = nombre
        self.posiciones = posiciones


class ReproductorDaisy:
    """Reproduce y navega la grabación de un libro DAISY.

    :param ventana: Ventana principal, de donde salen el documento, el panel de
                    lectura y los anuncios.
    """

    def __init__(self, ventana) -> None:
        self.ventana = ventana
        self.libro = None
        self.altavoz = audio.Altavoz()
        #: Frase por la que va la reproducción.
        self.frase = 0
        #: Niveles de navegación que ofrece este libro, y en cuál estamos.
        self.niveles: list[Nivel] = []
        self.nivel = 0
        self._reproduciendo = False
        self._pausado = False
        self._fin_de_frase = 0.0
        #: Posicion en el texto de cada frase, y el orden inverso para buscar.
        self._posiciones: list[int] = []
        self._orden: list[tuple[int, int]] = []
        self._puntos_por_posicion: dict[int, int] = {}
        #: Audio ya localizado, y la carpeta donde se extrae el de un libro
        #: comprimido.  Evita rehacer el trabajo en cada cambio de pista.
        self._extraidos: dict[str, Path] = {}
        self._temporal: str | None = None
        self._temporizador = wx.Timer(ventana)
        ventana.Bind(wx.EVT_TIMER, self._al_latir, self._temporizador)

    # -- carga ---------------------------------------------------------------

    @property
    def activo(self) -> bool:
        """Si hay un libro DAISY con grabación cargado."""
        return self.libro is not None and self.libro.tiene_audio

    @property
    def reproduciendo(self) -> bool:
        """Si hay una reproducción en curso, aunque esté en pausa."""
        return self._reproduciendo

    @property
    def sonando(self) -> bool:
        """Si en este instante está saliendo sonido."""
        return self._reproduciendo and not self._pausado

    def cargar(self, libro) -> None:
        """Se queda con un libro DAISY y prepara su navegación."""
        self.descargar()
        self.libro = libro
        self.frase = 0
        self._montar_niveles()
        self.indexar()
        self.altavoz.velocidad = int(self.ventana.configuracion.obtener("daisy_velocidad", 100))
        self.altavoz.volumen = int(self.ventana.configuracion.obtener("daisy_volumen", 100))
        log.info("Reproductor DAISY listo: %s", libro)

    def descargar(self) -> None:
        """Suelta el libro y para todo."""
        self.detener()
        self.altavoz.cerrar()
        self.libro = None
        self.niveles = []
        self.nivel = 0
        self.frase = 0
        self._posiciones = []
        self._orden = []
        self._puntos_por_posicion = {}
        self._limpiar_temporales()

    def _montar_niveles(self) -> None:
        """Arma la lista de niveles con lo que el libro tenga de verdad.

        No se ofrecen niveles vacíos: si un libro no tiene subsecciones, no
        aparece un nivel 2 por el que no se movería nada.
        """
        self.niveles = []
        if self.libro is None:
            return
        profundidades = sorted({punto.nivel for punto in self.libro.puntos if punto.nivel})
        for profundidad in profundidades:
            posiciones = [punto.frase for punto in self.libro.puntos
                          if punto.nivel <= profundidad]
            self.niveles.append(Nivel(
                "nivel%d" % profundidad,
                _("Nivel %d") % profundidad if profundidad > 1 else _("Capítulos"),
                sorted(set(posiciones))))
        if self.libro.paginas:
            self.niveles.append(Nivel(
                "pagina", _("Páginas"),
                sorted({punto.frase for punto in self.libro.paginas})))
        self.niveles.append(Nivel(
            "frase", _("Frases"), list(range(len(self.libro.frases)))))
        self.nivel = 0

    @property
    def nivel_actual(self) -> Nivel | None:
        """Unidad de navegación elegida ahora mismo."""
        if 0 <= self.nivel < len(self.niveles):
            return self.niveles[self.nivel]
        return None

    # -- costura con el texto ------------------------------------------------

    def indexar(self) -> None:
        """Prepara la traducción entre frases y posiciones del texto.

        Se hace una vez al cargar y no en cada consulta: un libro grande tiene
        decenas de miles de frases, y buscar recorriéndolas todas cada vez que
        se pulsa una tecla se nota.
        """
        self._posiciones = []
        self._orden = []
        self._puntos_por_posicion = {}
        documento = self.ventana.documento
        if documento is None or self.libro is None:
            return
        anteriores: dict[int, int] = {}
        for numero in range(len(self.libro.frases)):
            donde = documento.posiciones_id.get("daisy-%d" % numero, -1)
            self._posiciones.append(donde)
            if donde < 0:
                continue
            # Varias frases seguidas pueden caer en la misma posición: en un
            # libro de solo audio, los tramos sin texto dejan anclas vacías y
            # todas comparten sitio.  Se guarda la **primera**, para que
            # reproducir desde el cursor no se salte lo que hay en medio.
            if donde not in anteriores:
                anteriores[donde] = numero
                self._orden.append((donde, numero))
        self._orden.sort()
        # Un título sí escribe texto en el libro, y cuando el cursor está justo
        # encima de uno el usuario quiere **eso**: poner el cursor en
        # «Capítulo I» y darle a reproducir tiene que empezar el capítulo I, no
        # el rabo del anterior, aunque compartan sitio.
        #
        # Las páginas no entran aquí a propósito.  Una marca de página no
        # escribe nada —es un ancla vacía—, así que no puede reclamar una
        # posición que en realidad es de las frases que la rodean; si lo
        # hiciera, un cursor en mitad de un tramo saltaría hacia adelante y se
        # perdería audio.
        for punto in self.libro.puntos:
            if 0 <= punto.frase < len(self._posiciones):
                donde = self._posiciones[punto.frase]
                if donde >= 0:
                    self._puntos_por_posicion.setdefault(donde, punto.frase)

    def posicion_de(self, frase: int) -> int:
        """Posición en el texto del libro donde empieza esa frase.

        :return: La posición, o -1 si esa frase no dejó ancla.
        """
        if 0 <= frase < len(self._posiciones):
            return self._posiciones[frase]
        documento = self.ventana.documento
        if documento is None:
            return -1
        return documento.posiciones_id.get("daisy-%d" % frase, -1)

    def frase_en(self, posicion: int) -> int:
        """Qué frase corresponde a un punto del texto.

        Es la búsqueda inversa, la que hace que darle a reproducir con el
        cursor en mitad del capítulo siete empiece a sonar el capítulo siete y
        no donde se quedó la grabación.

        En un libro de solo audio hay tramos enteros sin una palabra escrita, y
        varias frases comparten sitio en el texto.  Ahí se decide así, y en este
        orden:

        1. Si la frase que ya estaba sonando pertenece a ese mismo tramo, se
           respeta.  Sin esto, pausar y reanudar retrocedería un poco cada vez.
        2. Si el cursor está justo sobre un título o una página, esa.
        3. Si no, la primera del tramo: reproducir desde el cursor nunca se
           salta audio, como mucho repite un poco.
        """
        if not self._orden:
            self.indexar()
        if not self._orden:
            return 0
        indice = bisect.bisect_right(self._orden, (posicion, len(self._posiciones))) - 1
        if indice < 0:
            return 0
        donde, primera = self._orden[indice]
        if 0 <= self.frase < len(self._posiciones) and self._posiciones[self.frase] == donde:
            return self.frase
        return self._puntos_por_posicion.get(donde, primera)

    def _llevar_cursor(self) -> None:
        """Coloca el cursor al principio de la frase que está sonando."""
        if not self.ventana.configuracion.obtener("daisy_mover_cursor", True):
            return
        posicion = self.posicion_de(self.frase)
        if posicion >= 0:
            self.ventana.lector.ir_a(posicion, mover_foco=False)

    # -- transporte ----------------------------------------------------------

    def alternar(self) -> None:
        """Empieza a reproducir, o pausa, o reanuda.

        Al reanudar se respeta dónde está el cursor: si el usuario se ha movido
        con las flechas mientras estaba en pausa, es que quiere seguir por ahí.
        """
        if not self._comprobar():
            return
        if not self._reproduciendo:
            self.reproducir(self.frase_en(self.ventana.lector.posicion()))
            return
        if self._pausado:
            desde_cursor = self.frase_en(self.ventana.lector.posicion())
            if desde_cursor != self.frase:
                self.reproducir(desde_cursor)
            else:
                self._pausado = False
                self.altavoz.reproducir()
                self._temporizador.Start(LATIDO)
                self.ventana.anunciar(_("Reanudando."), inmediato=True)
            return
        self.pausar()

    def reproducir(self, desde: int | None = None) -> None:
        """Empieza a sonar desde una frase concreta."""
        if not self._comprobar():
            return
        if desde is not None:
            self.frase = max(0, min(desde, len(self.libro.frases) - 1))
        if not self._colocar(self.frase):
            return
        self._reproduciendo = True
        self._pausado = False
        self.altavoz.reproducir()
        self._temporizador.Start(LATIDO)
        self.ventana.sonidos.reproducir("abrir")

    def pausar(self) -> None:
        """Detiene el sonido dejando dónde estaba."""
        if not self._reproduciendo or self._pausado:
            return
        self._pausado = True
        self.altavoz.pausar()
        self._temporizador.Stop()
        self.ventana.anunciar(_("En pausa."), inmediato=True)

    def detener(self, anunciar: bool = False) -> None:
        """Para la reproducción del todo."""
        self._temporizador.Stop()
        if self._reproduciendo:
            self.altavoz.parar()
        self._reproduciendo = False
        self._pausado = False
        if anunciar:
            self.ventana.anunciar(_("Reproducción detenida."), inmediato=True)

    def _comprobar(self) -> bool:
        """Avisa si no se puede reproducir, y dice por qué."""
        if self.libro is None or not self.libro.tiene_audio:
            self.ventana.anunciar(_("Este documento no tiene grabación."), inmediato=True)
            return False
        motivo = audio.motivo_no_disponible()
        if motivo:
            wx.MessageBox(motivo, _("Reproductor DAISY"), wx.OK | wx.ICON_INFORMATION,
                          self.ventana)
            return False
        return True

    # -- colocación ----------------------------------------------------------

    def _colocar(self, numero: int) -> bool:
        """Deja el altavoz listo en el punto donde empieza esa frase."""
        recorte = self.libro.audio_de(numero)
        if recorte is None:
            # Frase sin audio —pasa en los libros de solo texto y en algún
            # hueco—: se busca la siguiente que sí tenga.
            siguiente = self._siguiente_con_audio(numero)
            if siguiente is None:
                return False
            numero = siguiente
            recorte = self.libro.audio_de(numero)
        ruta = self._ruta_de(recorte.archivo)
        if ruta is None:
            log.warning("No se encuentra el audio %s", recorte.archivo)
            self.ventana.anunciar(
                _("Falta un archivo de sonido del libro: %s") % recorte.archivo,
                inmediato=True)
            return False
        if not self.altavoz.abrir(ruta):
            self.ventana.anunciar(_("No se ha podido abrir el sonido del libro."),
                                  inmediato=True)
            return False
        self.frase = numero
        self.altavoz.posicion = recorte.inicio
        self._fin_de_frase = recorte.fin if recorte.fin is not None else self.altavoz.duracion
        self._llevar_cursor()
        return True

    def _siguiente_con_audio(self, desde: int) -> int | None:
        """Primera frase de ahí en adelante que tenga grabación."""
        for numero in range(max(0, desde), len(self.libro.frases)):
            if self.libro.frases[numero].recortes:
                return numero
        return None

    def _ruta_de(self, interno: str):
        """Ruta en el disco de un archivo de audio del libro.

        Cuando el libro está en una carpeta —lo normal— es un cálculo de
        cadenas.  Cuando viene comprimido, que es como lo manda una biblioteca,
        hay que **sacar el archivo a disco**: BASS reproduce archivos, no
        entradas de un ZIP.  Se extrae solo el audio que hace falta y solo la
        primera vez, a una carpeta temporal que se borra al salir.
        """
        if not interno:
            return None
        guardado = self._extraidos.get(interno)
        if guardado is not None:
            return guardado
        from nucleo.daisy import Origen

        try:
            with Origen(self.libro.ruta) as origen:
                directa = origen.ruta_de(interno)
                if directa is not None:
                    self._extraidos[interno] = directa
                    return directa
                datos = origen.leer(interno)
        except Exception as error:
            registrar_excepcion(log, "No se ha podido localizar %s" % interno, error)
            return None

        if self._temporal is None:
            self._temporal = tempfile.mkdtemp(prefix="daisy_")
            log.info("Audio del libro comprimido, se extrae en %s", self._temporal)
        destino = Path(self._temporal) / Path(interno).name
        try:
            destino.write_bytes(datos)
        except OSError as error:
            registrar_excepcion(log, "No se ha podido extraer %s" % interno, error)
            return None
        self._extraidos[interno] = destino
        return destino

    def _limpiar_temporales(self) -> None:
        """Borra el audio que se hubiera extraído de un libro comprimido."""
        self._extraidos = {}
        if self._temporal is None:
            return
        shutil.rmtree(self._temporal, ignore_errors=True)
        self._temporal = None

    # -- latido --------------------------------------------------------------

    def _al_latir(self, evento) -> None:
        """Pasa a la frase siguiente cuando la actual se ha terminado.

        Si la siguiente es el trozo contiguo del mismo archivo —lo normal— no
        se toca el sonido: solo se anota el avance y se mueve el cursor.  Así la
        grabación suena seguida, como la grabó el narrador.
        """
        if not self.sonando:
            return
        try:
            posicion = self.altavoz.posicion
            if not self.altavoz.terminado and posicion + HOLGURA < self._fin_de_frase:
                return
            siguiente = self.frase + 1
            if siguiente >= len(self.libro.frases):
                self.detener()
                self.ventana.sonidos.reproducir("limite")
                self.ventana.anunciar(_("Fin del libro."), inmediato=True)
                return
            recorte = self.libro.audio_de(siguiente)
            actual = self.libro.audio_de(self.frase)
            continua = (recorte is not None and actual is not None
                        and recorte.archivo == actual.archivo
                        and abs(recorte.inicio - self._fin_de_frase) < 0.25
                        and not self.altavoz.terminado)
            if continua:
                self.frase = siguiente
                self._fin_de_frase = (recorte.fin if recorte.fin is not None
                                      else self.altavoz.duracion)
                self._llevar_cursor()
                return
            if not self._colocar(siguiente):
                self.detener()
                self.ventana.anunciar(_("Fin del libro."), inmediato=True)
                return
            self.altavoz.reproducir()
        except Exception as error:      # pragma: no cover - salvaguarda
            registrar_excepcion(log, "Fallo mientras sonaba el libro", error)
            self.detener()

    # -- navegación ----------------------------------------------------------

    def ir_a_frase(self, numero: int, anunciar: bool = True) -> None:
        """Salta a una frase, siguiese o no sonando."""
        if self.libro is None or not self.libro.frases:
            return
        numero = max(0, min(numero, len(self.libro.frases) - 1))
        sonaba = self.sonando
        if not self._colocar(numero):
            return
        if sonaba:
            self.altavoz.reproducir()
        elif self._reproduciendo:
            self.altavoz.pausar()
        if anunciar:
            self._anunciar_donde()

    def saltar_frase(self, adelante: bool) -> None:
        """Una frase adelante o atrás."""
        if self.libro is None:
            return
        destino = self.frase + (1 if adelante else -1)
        if destino < 0 or destino >= len(self.libro.frases):
            self.ventana.sonidos.reproducir("limite")
            self.ventana.anunciar(
                _("Final de la grabación.") if adelante else _("Principio de la grabación."),
                inmediato=True)
            return
        self.ir_a_frase(destino, anunciar=False)
        self._anunciar_texto_de_frase()

    def saltar_segundos(self, segundos: float) -> None:
        """Avanza o retrocede dentro de la grabación.

        Salta por el reloj, no por frases: es lo que se quiere cuando uno se ha
        despistado y necesita «diez segundos atrás», sin importar dónde caiga
        eso en la estructura del libro.
        """
        if self.libro is None or not self.altavoz.abierto:
            return
        destino = self.altavoz.posicion + segundos
        recorte = self.libro.audio_de(self.frase)
        if recorte is None:
            return
        if destino < 0:
            # Antes del principio de este archivo: se va a la frase anterior.
            if self.frase > 0:
                self.ir_a_frase(self.frase - 1, anunciar=False)
                self._anunciar_donde()
            else:
                self.altavoz.posicion = 0
                self.ventana.sonidos.reproducir("limite")
            return
        if destino > self.altavoz.duracion:
            self.saltar_frase(True)
            return
        self.altavoz.posicion = destino
        self.frase = self._frase_del_reloj(recorte.archivo, destino)
        self._fin_de_frase = self._fin_de(self.frase)
        self._llevar_cursor()
        self._anunciar_donde()

    def _frase_del_reloj(self, archivo: str, segundo: float) -> int:
        """Qué frase suena en ese segundo de ese archivo."""
        for numero, frase in enumerate(self.libro.frases):
            for recorte in frase.recortes:
                if recorte.archivo != archivo:
                    continue
                fin = recorte.fin if recorte.fin is not None else float("inf")
                if recorte.inicio <= segundo < fin:
                    return numero
        return self.frase

    def _fin_de(self, numero: int) -> float:
        """Segundo en el que acaba una frase."""
        recorte = self.libro.audio_de(numero)
        if recorte is None:
            return 0.0
        return recorte.fin if recorte.fin is not None else self.altavoz.duracion

    def cambiar_nivel(self, incremento: int) -> None:
        """Cambia la unidad con la que se navega, y lo dice."""
        if not self.niveles:
            return
        self.nivel = max(0, min(self.nivel + incremento, len(self.niveles) - 1))
        nivel = self.niveles[self.nivel]
        self.ventana.anunciar(
            _("Navegación por %s. %d en el libro.") % (nivel.nombre.lower(),
                                                       len(nivel.posiciones)),
            inmediato=True)

    def punto_siguiente(self) -> None:
        """Al siguiente sitio del nivel elegido."""
        self._mover_por_nivel(True)

    def punto_anterior(self) -> None:
        """Al anterior sitio del nivel elegido."""
        self._mover_por_nivel(False)

    def _mover_por_nivel(self, adelante: bool) -> None:
        """Se mueve por el nivel de navegación que esté puesto."""
        nivel = self.nivel_actual
        if nivel is None or not nivel.posiciones:
            return
        if adelante:
            destinos = [p for p in nivel.posiciones if p > self.frase]
            destino = destinos[0] if destinos else None
        else:
            # Con un margen: si se acaba de entrar en un capítulo, «anterior»
            # va al de antes y no al principio del mismo, que es lo que hacen
            # los reproductores de verdad.
            destinos = [p for p in nivel.posiciones if p < self.frase]
            destino = destinos[-1] if destinos else None
        if destino is None:
            self.ventana.sonidos.reproducir("limite")
            self.ventana.anunciar(
                _("No hay más %s.") % nivel.nombre.lower(), inmediato=True)
            return
        self.ir_a_frase(destino, anunciar=False)
        self._anunciar_donde()

    def ir_a_punto(self, punto: Punto) -> None:
        """Salta a un punto concreto del índice o a una página."""
        self.ir_a_frase(punto.frase, anunciar=False)
        self.ventana.anunciar(punto.titulo, inmediato=True)

    # -- ajustes -------------------------------------------------------------

    def cambiar_velocidad(self, incremento: int) -> None:
        """Sube o baja la velocidad, y la aplica al momento."""
        if self.libro is None:
            return
        antes = self.altavoz.velocidad
        self.altavoz.velocidad = antes + incremento * PASO_VELOCIDAD
        ahora = self.altavoz.velocidad
        self.ventana.configuracion.establecer("daisy_velocidad", ahora)
        if ahora == antes:
            self.ventana.sonidos.reproducir("limite")
        self.ventana.anunciar(_("Velocidad %d por ciento.") % ahora, inmediato=True)

    def cambiar_volumen(self, incremento: int) -> None:
        """Sube o baja el volumen de la grabación."""
        if self.libro is None:
            return
        antes = self.altavoz.volumen
        self.altavoz.volumen = antes + incremento * PASO_VOLUMEN
        ahora = self.altavoz.volumen
        self.ventana.configuracion.establecer("daisy_volumen", ahora)
        if ahora == antes:
            self.ventana.sonidos.reproducir("limite")
        self.ventana.anunciar(_("Volumen %d por ciento.") % ahora, inmediato=True)

    # -- decir dónde estamos -------------------------------------------------

    def transcurrido(self) -> float:
        """Segundos de libro que van desde el principio."""
        if self.libro is None:
            return 0.0
        total = sum(frase.duracion for frase in self.libro.frases[:self.frase])
        recorte = self.libro.audio_de(self.frase)
        if recorte is not None and self.altavoz.abierto:
            total += max(0.0, self.altavoz.posicion - recorte.inicio)
        return total

    def _anunciar_donde(self) -> None:
        """Dice el capítulo y la página en los que estamos."""
        self.ventana.anunciar(self.resumen_corto(), inmediato=True)

    def _anunciar_texto_de_frase(self) -> None:
        """Dice el texto de la frase, o dónde estamos si no tiene."""
        posicion = self.posicion_de(self.frase)
        documento = self.ventana.documento
        if documento is not None and posicion >= 0:
            fin = documento.texto.find("\n", posicion)
            trozo = documento.texto[posicion:fin if fin > 0 else posicion + 120].strip()
            if trozo:
                self.ventana.anunciar(trozo, inmediato=True)
                return
        self._anunciar_donde()

    def resumen_corto(self) -> str:
        """Una línea con dónde estamos, para anunciar al navegar."""
        if self.libro is None:
            return ""
        partes = []
        punto = self.libro.punto_en(self.frase)
        if punto is not None and punto.titulo:
            partes.append(punto.titulo)
        pagina = self.libro.pagina_en(self.frase)
        if pagina is not None and pagina.titulo:
            partes.append(_("página %s") % pagina.titulo)
        partes.append(audio.reloj(self.transcurrido()))
        return ". ".join(partes)

    def donde_estoy(self) -> None:
        """Dice en voz alta la situación completa: capítulo, página y tiempo."""
        if self.libro is None:
            self.ventana.anunciar(_("No hay ningún libro DAISY abierto."), inmediato=True)
            return
        total = self.libro.duracion
        transcurrido = self.transcurrido()
        partes = [self.resumen_corto()]
        if total > 0:
            partes.append(_("%d por ciento") % int(transcurrido * 100 / total))
            partes.append(_("quedan %s") % audio.duracion_legible(total - transcurrido))
        nivel = self.nivel_actual
        if nivel is not None:
            partes.append(_("navegando por %s") % nivel.nombre.lower())
        self.ventana.anunciar(". ".join(p for p in partes if p), inmediato=True)


# ---------------------------------------------------------------------------
# Ventana del reproductor
# ---------------------------------------------------------------------------

class DialogoReproductor(wx.Dialog):
    """Los mandos del reproductor DAISY, todos en un sitio.

    Existe por dos razones.  Una es que las teclas hay que poder descubrirlas:
    quien no se sepa los atajos tiene aquí los botones, con su nombre dicho.
    La otra es la lista de capítulos y páginas, que es la forma más rápida de
    ir a un sitio concreto cuando se sabe adónde se quiere ir.

    :param padre: Ventana principal.
    :param reproductor: El reproductor al que manda.
    """

    def __init__(self, padre: wx.Window, reproductor: ReproductorDaisy) -> None:
        super().__init__(padre, title=_("Reproductor DAISY"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.reproductor = reproductor
        self._voz = Voz(self)

        contenedor = wx.BoxSizer(wx.VERTICAL)
        libro = reproductor.libro
        cabecera = "%s\n%s" % (libro.titulo or _("(sin título)"),
                               libro.descripcion_del_tipo())
        if libro.narrador:
            cabecera += "\n" + _("Narrado por %s") % libro.narrador
        cabecera += "\n" + _("Duración: %s") % audio.duracion_legible(libro.duracion)
        contenedor.Add(wx.StaticText(self, label=cabecera), 0, wx.ALL, MARGEN)

        self.situacion = wx.StaticText(self, label="")
        contenedor.Add(self.situacion, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, MARGEN)

        # Se dicen aquí y no solo en el manual: quien abre esta ventana quiere
        # manejarla ya, y las teclas llevan Control precisamente para que la
        # barra espaciadora siga pulsando el botón donde estés.
        contenedor.Add(wx.StaticText(self, label=_(
            "Desde cualquier punto de esta ventana: Control+Espacio reproduce o pausa,\n"
            "Control+Izquierda y Control+Derecha se mueven por el nivel elegido, y\n"
            "Control+Arriba y Control+Abajo cambian de nivel. En los botones, la barra\n"
            "espaciadora y la tecla Intro los pulsan, como en cualquier otra ventana."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, MARGEN)

        self.barra = etiquetar(wx.Gauge(self, range=1000, size=(420, 18)), _("Avance"))
        contenedor.Add(self.barra, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, MARGEN)

        # -- mandos ----------------------------------------------------------
        fila = wx.BoxSizer(wx.HORIZONTAL)
        self.boton_reproducir = wx.Button(self, label=_("&Reproducir"))
        botones = (
            (self.boton_reproducir, lambda: self.reproductor.alternar()),
            (wx.Button(self, label=_("&Atrás 10 s")), lambda: self.reproductor.saltar_segundos(-audio.SALTO)),
            (wx.Button(self, label=_("A&delante 10 s")), lambda: self.reproductor.saltar_segundos(audio.SALTO)),
            (wx.Button(self, label=_("&Frase anterior")), lambda: self.reproductor.saltar_frase(False)),
            (wx.Button(self, label=_("Frase &siguiente")), lambda: self.reproductor.saltar_frase(True)),
        )
        for boton, accion in botones:
            fila.Add(boton, 0, wx.ALL, 4)
            boton.Bind(wx.EVT_BUTTON, lambda evento, hacer=accion: self._mandar(hacer))
        contenedor.Add(fila, 0, wx.LEFT | wx.RIGHT, MARGEN - 4)

        # -- nivel de navegación ---------------------------------------------
        self.eleccion_nivel = fila_etiquetada(
            self, contenedor, _("&Navegar por:"),
            lambda p: wx.Choice(p, choices=[nivel.nombre for nivel in reproductor.niveles]),
            margen=MARGEN, horizontal=True)
        self.eleccion_nivel.SetSelection(reproductor.nivel)
        self.eleccion_nivel.Bind(wx.EVT_CHOICE, self._al_cambiar_nivel)

        fila_nivel = wx.BoxSizer(wx.HORIZONTAL)
        for etiqueta, accion in ((_("A&nterior"), reproductor.punto_anterior),
                                 (_("Si&guiente"), reproductor.punto_siguiente)):
            boton = wx.Button(self, label=etiqueta)
            boton.Bind(wx.EVT_BUTTON, lambda evento, hacer=accion: self._mandar(hacer))
            fila_nivel.Add(boton, 0, wx.ALL, 4)
        contenedor.Add(fila_nivel, 0, wx.LEFT | wx.RIGHT, MARGEN - 4)

        # -- velocidad y volumen ---------------------------------------------
        # Un control de número y no un deslizador.  Un deslizador que va de 50 a
        # 300 lo anuncia el lector de pantalla como el **porcentaje de su
        # recorrido**: con la velocidad en 100 decía «20», y hacían falta tres
        # pulsaciones para que ese número se moviera uno.  Un control de número
        # dice el valor real y cada pulsación lo cambia.
        self.velocidad = fila_etiquetada(
            self, contenedor,
            _("&Velocidad, en por ciento (%d es la del narrador):")
            % audio.VELOCIDAD_NORMAL,
            lambda p: wx.SpinCtrl(p, min=audio.VELOCIDAD_MINIMA,
                                  max=audio.VELOCIDAD_MAXIMA,
                                  initial=reproductor.altavoz.velocidad),
            margen=MARGEN, horizontal=True)
        self.velocidad.SetIncrement(PASO_VELOCIDAD)
        self.velocidad.Bind(wx.EVT_SPINCTRL, self._al_mover_velocidad)

        self.volumen = fila_etiquetada(
            self, contenedor, _("V&olumen, de 0 a 100:"),
            lambda p: wx.SpinCtrl(p, min=0, max=100,
                                  initial=reproductor.altavoz.volumen),
            margen=MARGEN, horizontal=True)
        self.volumen.SetIncrement(PASO_VOLUMEN)
        self.volumen.Bind(wx.EVT_SPINCTRL, self._al_mover_volumen)

        # -- lista de sitios --------------------------------------------------
        contenedor.Add(wx.StaticText(self, label=_("&Ir a:")), 0,
                       wx.LEFT | wx.RIGHT | wx.TOP, MARGEN)
        self.lista = etiquetar(wx.ListBox(self, size=(-1, 160)), _("Sitios del libro"))
        self._sitios: list[Punto] = []
        self._rellenar_lista()
        self.lista.Bind(wx.EVT_LISTBOX_DCLICK, self._al_elegir_sitio)
        contenedor.Add(self.lista, 1, wx.EXPAND | wx.ALL, MARGEN)

        pie = wx.StdDialogButtonSizer()
        cerrar = wx.Button(self, wx.ID_OK, _("&Cerrar"))
        cerrar.SetDefault()
        pie.AddButton(cerrar)
        pie.Realize()
        contenedor.Add(pie, 0, wx.EXPAND | wx.ALL, MARGEN)
        self.SetSizerAndFit(contenedor)
        self.CentreOnParent()

        self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar_tecla)
        self.Bind(wx.EVT_CLOSE, self._al_cerrar)
        self._refresco = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, lambda evento: self._refrescar(), self._refresco)
        self._refresco.Start(500)
        self._refrescar()
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    # -- construcción --------------------------------------------------------

    def _rellenar_lista(self) -> None:
        """Pone en la lista los sitios del nivel elegido."""
        libro = self.reproductor.libro
        nivel = self.reproductor.nivel_actual
        self._sitios = []
        rotulos = []
        if nivel is None or libro is None:
            self.lista.Set([])
            return
        if nivel.clave == "pagina":
            for punto in libro.paginas:
                self._sitios.append(punto)
                rotulos.append(_("Página %s") % punto.titulo)
        elif nivel.clave == "frase":
            for numero, _frase in enumerate(libro.frases):
                punto = Punto(_("Frase %d") % (numero + 1), 0, numero, "frase")
                self._sitios.append(punto)
                rotulos.append(punto.titulo)
        else:
            profundidad = int(nivel.clave.removeprefix("nivel"))
            for punto in libro.puntos:
                if punto.nivel > profundidad:
                    continue
                self._sitios.append(punto)
                rotulos.append("%s%s" % ("    " * (punto.nivel - 1), punto.titulo))
        self.lista.Set(rotulos)

    # -- eventos -------------------------------------------------------------

    def _mandar(self, accion) -> None:
        """Ejecuta una orden del reproductor y refresca lo que se ve."""
        accion()
        self._refrescar()

    def _al_cambiar_nivel(self, evento) -> None:
        """Cambia la unidad de navegación y rehace la lista."""
        self.reproductor.nivel = max(0, self.eleccion_nivel.GetSelection())
        self._rellenar_lista()
        nivel = self.reproductor.nivel_actual
        if nivel is not None:
            self._voz.decir(_("Navegación por %s. %d en el libro.")
                            % (nivel.nombre.lower(), len(nivel.posiciones)))

    def _al_elegir_sitio(self, evento) -> None:
        """Salta al sitio elegido en la lista."""
        indice = self.lista.GetSelection()
        if 0 <= indice < len(self._sitios):
            self.reproductor.ir_a_punto(self._sitios[indice])
            self._refrescar()

    def _al_mover_velocidad(self, evento) -> None:
        """Aplica la velocidad al momento, mientras suena."""
        self.reproductor.altavoz.velocidad = self.velocidad.GetValue()
        self.reproductor.ventana.configuracion.establecer(
            "daisy_velocidad", self.reproductor.altavoz.velocidad)

    def _al_mover_volumen(self, evento) -> None:
        """Aplica el volumen al momento."""
        self.reproductor.altavoz.volumen = self.volumen.GetValue()
        self.reproductor.ventana.configuracion.establecer(
            "daisy_volumen", self.reproductor.altavoz.volumen)

    def _al_pulsar_tecla(self, evento: wx.KeyEvent) -> None:
        """Atajos del reproductor dentro de su propia ventana.

        **Todos llevan Control**, y eso no es un capricho.  Antes la barra
        espaciadora sola pausaba y las flechas cambiaban de nivel, y el
        resultado era que estando en un botón la barra pausaba en vez de
        pulsarlo, y las flechas no movían el foco entre los botones.  Es decir,
        el teclado normal de Windows dejaba de funcionar dentro de esta ventana,
        que es de las peores cosas que le puedes hacer a quien la maneja a
        ciegas: las teclas tienen que hacer siempre lo mismo en todas partes.

        Con Control por delante conviven las dos cosas: la barra pulsa el botón
        donde estés y Control+Espacio reproduce o pausa desde cualquier sitio.
        """
        codigo = evento.GetKeyCode()
        if codigo == wx.WXK_ESCAPE and not evento.HasModifiers():
            self.Close()
            return
        if not evento.ControlDown() or evento.AltDown() or evento.ShiftDown():
            evento.Skip()
            return
        acciones = {
            wx.WXK_SPACE: self.reproductor.alternar,
            wx.WXK_LEFT: self.reproductor.punto_anterior,
            wx.WXK_RIGHT: self.reproductor.punto_siguiente,
            wx.WXK_UP: lambda: self._nivel(-1),
            wx.WXK_DOWN: lambda: self._nivel(1),
        }
        accion = acciones.get(codigo)
        if accion is None:
            evento.Skip()
            return
        accion()
        self._refrescar()

    def _nivel(self, incremento: int) -> None:
        """Cambia el nivel desde el teclado y pone al día la ventana."""
        self.reproductor.cambiar_nivel(incremento)
        self.eleccion_nivel.SetSelection(self.reproductor.nivel)
        self._rellenar_lista()

    def _refrescar(self) -> None:
        """Pone al día la situación y el botón de reproducir."""
        if not self:
            return
        reproductor = self.reproductor
        self.boton_reproducir.SetLabel(_("&Pausa") if reproductor.sonando
                                       else _("&Reproducir"))
        # La velocidad y el volumen pueden haber cambiado con las teclas
        # mientras la ventana estaba abierta.
        if self.velocidad.GetValue() != reproductor.altavoz.velocidad:
            self.velocidad.SetValue(reproductor.altavoz.velocidad)
        if self.volumen.GetValue() != reproductor.altavoz.volumen:
            self.volumen.SetValue(reproductor.altavoz.volumen)
        total = reproductor.libro.duracion if reproductor.libro else 0
        transcurrido = reproductor.transcurrido()
        self.situacion.SetLabel("%s  ·  %s / %s" % (
            reproductor.resumen_corto(), audio.reloj(transcurrido), audio.reloj(total)))
        if total > 0:
            self.barra.SetValue(max(0, min(1000, int(transcurrido * 1000 / total))))

    def _al_cerrar(self, evento) -> None:
        """Cierra la ventana dejando la reproducción como esté."""
        self._refresco.Stop()
        evento.Skip()
