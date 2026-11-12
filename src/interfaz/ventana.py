# -*- coding: utf-8 -*-
"""Ventana principal de la aplicación.

Reúne todas las piezas: el panel de lectura, los menús, los atajos de
teclado, los diálogos, los sonidos y el guardado de la sesión.

Dos detalles importantes de comportamiento:

* **El análisis del libro se hace en un hilo aparte.**  Aunque abrir un libro
  enorme cuesta poco más de un segundo, durante ese tiempo la ventana debe
  seguir respondiendo y anunciando que está trabajando.  Cuando el análisis
  termina, el resultado vuelve al hilo de la interfaz con ``wx.CallAfter``,
  que es la única forma segura de tocar la interfaz desde otro hilo.

* **Las teclas de una sola letra se interceptan en la ventana**, no en el
  control de texto, mediante ``EVT_CHAR_HOOK``.  Así funcionan siempre, y las
  combinaciones con Control o Alt se dejan pasar para que las procesen los
  aceleradores de los menús.
"""

from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path

import wx

from formatos import base as formatos
from interfaz import atajos as tabla_atajos
from interfaz import anuncios
from interfaz.anuncios import Anunciador
from interfaz.dialogos import actualizacion as dialogos_actualizacion
from interfaz.dialogos import audio as dialogos_audio
from interfaz.dialogos import ayuda as dialogos_ayuda
from interfaz.dialogos import buscar as dialogos_buscar
from interfaz.dialogos import contenido as dialogos_contenido
from interfaz.dialogos import diccionario as dialogos_diccionario
from interfaz.dialogos import navegacion as dialogos_navegacion
from interfaz.dialogos import notas_al_pie as dialogos_notas_al_pie
from interfaz.dialogos import opciones as dialogos_opciones
from interfaz.dialogos import perfiles as dialogos_perfiles
from interfaz.dialogos import preguntar as dialogos_preguntar
from interfaz.dialogos import primer_uso as dialogos_primer_uso
from interfaz.dialogos import progreso as dialogos_progreso
from interfaz.dialogos import pronunciacion as dialogos_pronunciacion
from interfaz.dialogos.espera import ejecutar_esperando
from interfaz.dialogos import registro as dialogos_registro
from interfaz.dialogos import visor_html
from interfaz.arbol import PanelArbol
from interfaz.lector import PanelLectura
from interfaz.pestanas import Pestanas
from interfaz.dialogos.voz import DialogoVoz
from interfaz.lectura_voz import LectorEnVozAlta
from interfaz.reproductor_daisy import DialogoReproductor, ReproductorDaisy
from interfaz import teclas_globales
from interfaz.temporizador import DialogoTemporizador, Temporizador
from interfaz.bandeja import IconoBandeja
from nucleo import actualizaciones, audio, cache, daisy as lector_daisy
from nucleo import descripciones, diccionario, estadisticas, html_elementos
from nucleo import sincronizacion
from nucleo import instancia, marcado, notas
from nucleo.audio_libro import nombre_seguro
from nucleo import navegacion, rutas
from nucleo.busqueda import Buscador, OpcionesBusqueda
from nucleo.configuracion import Marcador
from nucleo.documento import Documento
from nucleo.ia.servicio import Servicio
from nucleo.idioma import _, _n
from nucleo.marcas import TipoMarca
from nucleo.navegacion import Objetivo
from nucleo.registro import cronometro, obtener_registro, registrar_excepcion
from sonidos.gestor import GestorSonidos
from version import NOMBRE, VERSION

log = obtener_registro(__name__)

#: Ancho mínimo que puede quedarle a una zona al arrastrar el divisor.  Por
#: debajo de esto el árbol deja de poder leerse y el texto se parte en una
#: columna inservible, así que no se permite.
ANCHO_MINIMO_ZONA = 180

#: Nombre con el que se anuncia cada zona al llegar a ella con F6.  Se dice
#: siempre, aunque el lector de pantalla vaya a anunciar el control: el nombre
#: de la zona es lo que orienta, y el del control llega después.
NOMBRES_DE_ZONA = {
    "arbol": _("Árbol de contenido"),
    "pestanas": _("Pestañas"),
    "documento": _("Texto del documento"),
}

#: Segundos durante los que, tras cerrarse un menú, los avisos «inmediatos» se
#: tratan como normales.  El paso del menú al manejador es instantáneo, así que
#: con medio segundo sobra; más tiempo empezaría a retrasar avisos de teclas
#: pulsadas justo después de usar un menú.
ESPERA_TRAS_MENU = 0.5

#: Cuántos caracteres de una nota al pie se dicen de una vez.  Una nota normal
#: cabe entera; una que sea media página se recorta, porque un aviso hablado que
#: dura cinco minutos no se puede parar ni releer.  Para esas está saltar a la
#: nota con Intro.
LARGO_NOTA = 700

#: Longitud del fragmento de texto que se guarda con cada marcador.
LONGITUD_FRAGMENTO = 120

#: Longitud máxima del texto que se guarda con un resaltado.  Es mucho mayor
#: que la de un marcador porque aquí el fragmento **es** el contenido: es lo
#: que se exporta después, y recortarlo a ciento veinte caracteres dejaría
#: media idea fuera.
LONGITUD_RESALTADO = 4000


class _SoltarArchivo(wx.FileDropTarget):
    """Permite abrir un libro arrastrándolo sobre la ventana.

    Si se sueltan varios archivos a la vez se abre el primero, porque la
    aplicación muestra un libro cada vez.
    """

    def __init__(self, ventana: "VentanaPrincipal") -> None:
        super().__init__()
        self._ventana = ventana

    def OnDropFiles(self, x, y, nombres):  # noqa: N802 (nombre impuesto por wx)
        """Recibe la lista de archivos soltados."""
        if not nombres:
            return False
        log.info("Archivo soltado en la ventana: %s", nombres[0])
        wx.CallAfter(self._ventana.abrir_libro, nombres[0])
        return True


class VentanaPrincipal(wx.Frame):
    """Ventana principal del programa.

    :param configuracion: Preferencias de la aplicación.
    :param version: Versión del programa, para el título y el diálogo «Acerca de».
    """

    def __init__(self, configuracion, version: str) -> None:
        super().__init__(
            None, title=NOMBRE,
            size=(int(configuracion.obtener("ventana_ancho")),
                  int(configuracion.obtener("ventana_alto"))),
        )
        self.configuracion = configuracion
        self.version = version
        self._dialogo_buscar: dialogos_buscar.DialogoBuscar | None = None
        #: La ventana de práctica, que no es modal y por eso hay que
        #: guardarla: sin referencia se cerraría sola al salir del método.
        self._dialogo_practica = None
        #: Dónde seguir leyendo al cerrar la búsqueda, si se encontró algo.
        self._seguir_leyendo_en = None
        #: Visor de registros abierto, si lo hay.  No es modal, así que la
        #: ventana tiene que acordarse de él para no abrir dos.
        self.visor_registro = None
        #: Ventana de progreso mientras se abre un libro, si la hay.
        self._progreso = None
        #: Sesión en la que va a caer el documento que se está abriendo.  Se
        #: apunta al empezar y no al terminar porque entre las dos cosas puede
        #: haber pasado un minuto y el usuario haber cambiado de pestaña.
        self._sesion_destino = None
        self._cargando = False
        self._identificadores: dict[str, int] = {}
        self._referencias_id: list[wx.WindowIDRef] = []

        self.sonidos = GestorSonidos(
            activado=bool(configuracion.obtener("sonidos_activados")),
            volumen=int(configuracion.obtener("sonidos_volumen")),
        )
        self.anunciador = Anunciador(self)
        self._construir_zonas()

        # Lectura en voz alta.  Se crea aquí, pero no toca el sintetizador
        # hasta que se usa por primera vez: conectar con SAPI cuesta unas
        # décimas y quien no lea en voz alta no tiene por qué pagarlas.
        self.lectura_voz = LectorEnVozAlta(self)
        # Los restos de un motor que se quitó con una biblioteca cargada se
        # borran ahora, que es cuando ya no está en uso.  Después se pone el
        # motor elegido: si no arranca, queda la voz de Windows y se dice.
        try:
            from nucleo import paquetes_voz

            paquetes_voz.limpiar_restos()
        except Exception as error:
            log.debug("Al limpiar restos de motores de voz: %s", error)
        aviso_motor = self.lectura_voz.aplicar_motor()
        if aviso_motor:
            wx.CallAfter(self.anunciar, aviso_motor)
        #: Icono de la bandeja, mientras la ventana esté escondida en ella.
        self.icono_bandeja = None
        #: Teclas globales registradas en Windows.
        self.reproductor_daisy = ReproductorDaisy(self)
        self.registro_global = teclas_globales.Registro(self, self._al_pulsar_tecla_global)

        # Dos campos: por dónde va la lectura y de qué tamaño es el documento.
        # El segundo es lo que se echa de menos al venir de otros lectores:
        # saber cuántas palabras y cuántas páginas tiene lo que se está
        # leyendo, sin abrir ningún diálogo.
        self.CreateStatusBar(2)
        self.SetStatusWidths([-3, -2])
        self.SetStatusText(_("Listo. Pulsa Control+O para abrir un documento."))
        self._construir_menus()
        self._preparar_teclas()

        # Windows trata la tecla F1 de forma especial: la convierte en una
        # petición de ayuda (un evento propio) y nunca llega a la tabla de
        # aceleradores, así que el atajo del menú no se dispara por sí solo.
        # Se comprobó probando todos los atajos uno a uno: F1 era el único que
        # no funcionaba.  Atendiendo el evento de ayuda, la tecla vuelve a
        # abrir el manual.
        # Cuándo se cerró el último menú.  Lo consulta «anunciar» para saber si
        # el foco está a punto de moverse y hay que esperarlo.
        self._menu_cerrado_en = 0.0
        self.Bind(wx.EVT_MENU_CLOSE, self._al_cerrar_menu)
        self.Bind(wx.EVT_HELP, self.al_manual)
        self.Bind(wx.EVT_CLOSE, self._al_cerrar_ventana)
        if configuracion.obtener("ventana_maximizada"):
            self.Maximize()
        self.Centre()
        # Sin libro abierto, el control muestra el resumen de lo que se puede
        # hacer en vez de quedarse en blanco.
        self.lector.mostrar_presentacion()
        self.lector.texto.SetFocus()

        # Instancia única: se anota esta ventana para que una segunda copia
        # del programa pueda traerla al frente, y se vigila si deja el encargo
        # de abrir un libro.
        # Las teclas globales se piden a Windows una vez creada la ventana:
        # RegisterHotKey necesita una ventana de verdad a la que mandar los
        # avisos.  Se hace al final del arranque para no retrasar lo que se ve.
        wx.CallAfter(self.aplicar_teclas_globales)
        self.Bind(wx.EVT_ICONIZE, self._al_minimizar)

        # Restos de una actualización anterior: si la copia salió bien el
        # propio guion se limpia, así que esto es para cuando algo se torció.
        # El recorrido guiado se ofrece después de que la ventana esté
        # entera: abrirlo antes dejaría el foco en un sitio raro si se cierra.
        if dialogos_primer_uso.hace_falta(configuracion):
            wx.CallAfter(self.al_primer_uso, None)

        actualizaciones.limpiar_restos()
        wx.CallAfter(self._revisar_actualizacion_anterior)
        if self.configuracion.obtener("comprobar_actualizaciones", True):
            wx.CallAfter(self._comprobar_actualizaciones, False)

        # El temporizador de apagado manda tanto sobre la voz sintética como
        # sobre el reproductor DAISY, así que vive aquí y no en ninguno de los
        # dos.
        self.temporizador = Temporizador(self)

        # La IA local, si se ha pedido que arranque con el programa.  Va en
        # segundo plano y al final de todo: levantar el servidor son unos
        # segundos, y no hay ninguna razón para que el usuario los espere
        # antes de poder abrir un libro.
        wx.CallAfter(self._arrancar_ia_local)

        instancia.anotar_ventana(self.GetHandle())
        #: Documentos que quedan por reabrir de la sesión anterior.  Se abren
        #: de uno en uno porque el análisis usa un solo hilo.
        self._por_restaurar = None
        self._restaurar_activo = 0
        self._vigilante_encargos = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._al_revisar_encargos, self._vigilante_encargos)
        self._vigilante_encargos.Start(700)

    # =======================================================================
    # Zonas de la ventana y sesiones abiertas
    # =======================================================================
    #
    # La ventana tiene hasta tres zonas por las que se pasa con F6: el árbol de
    # contenido, la fila de pestañas y el texto del documento.  Las dos
    # primeras son opcionales y vienen apagadas, porque quien lee una novela de
    # un tirón no las necesita y una zona de más por la que pasar cada vez es
    # una molestia diaria a cambio de nada.
    #
    # Todo lo que era «el documento abierto» vive ahora en la sesión de la
    # pestaña activa (:mod:`interfaz.sesion`).  Las propiedades que vienen a
    # continuación mantienen los nombres de siempre —``self.documento``,
    # ``self.marcadores``...— para que las mil líneas que hay debajo no tengan
    # que enterarse de que existen las pestañas.

    def _construir_zonas(self) -> None:
        """Monta el árbol, las pestañas y el panel de lectura de la ventana.

        El divisor está siempre puesto aunque el árbol esté escondido: así
        enseñarlo y esconderlo es partir o juntar el divisor, sin rehacer la
        ventana ni perder por dónde iba la lectura.
        """
        self.division = wx.SplitterWindow(
            self, style=wx.SP_LIVE_UPDATE | wx.SP_3DSASH | wx.SP_BORDER)
        self.division.SetMinimumPaneSize(ANCHO_MINIMO_ZONA)
        self.panel_arbol = PanelArbol(self.division, self._al_elegir_del_arbol,
                                      self._posicion_de_lectura, acciones=self,
                                      marcadores=lambda: self.marcadores)
        self.pestanas = Pestanas(
            self.division,
            bool(self.configuracion.obtener("usar_pestanas", False)),
            self._crear_panel_lectura, self._al_cambiar_pestana, self.guardar_sesion)
        self.pestanas.nueva()
        self.division.Initialize(self.pestanas)
        self.panel_arbol.Hide()
        # Hace falta un organizador explícito porque el marco tiene un segundo
        # hijo (la etiqueta oculta que usa el anunciador) y, cuando hay más de
        # uno, wxWidgets deja de ajustar el tamaño automáticamente: sin esto el
        # texto se mostraría en una columna de unos pocos caracteres de ancho.
        organizador = wx.BoxSizer(wx.VERTICAL)
        organizador.Add(self.division, 1, wx.EXPAND)
        self.SetSizer(organizador)
        self.aplicar_arbol(bool(self.configuracion.obtener("mostrar_arbol", False)))

    def _crear_panel_lectura(self, padre: wx.Window) -> PanelLectura:
        """Fabrica el panel de lectura de una pestaña nueva."""
        panel = PanelLectura(padre, self.configuracion, self.sonidos, self.anunciador,
                             al_moverse=self._al_moverse, version=self.version)
        panel.admitir_soltar_archivos(lambda: _SoltarArchivo(self))
        panel.mostrar_presentacion()
        return panel

    # -- estado de la sesión activa ------------------------------------------

    @property
    def sesion(self):
        """Sesión de la pestaña activa."""
        return self.pestanas.actual

    @property
    def lector(self) -> PanelLectura:
        """Panel de lectura de la pestaña activa."""
        return self.pestanas.actual.panel

    @property
    def documento(self):
        return self.pestanas.actual.documento

    @documento.setter
    def documento(self, valor) -> None:
        sesion = self.pestanas.actual
        sesion.documento = valor
        sesion.olvidar_recuentos()

    @property
    def ruta_actual(self) -> str:
        return self.pestanas.actual.ruta

    @ruta_actual.setter
    def ruta_actual(self, valor: str) -> None:
        sesion = self.pestanas.actual
        sesion.ruta = valor or ""
        # Con qué archivo se abrió, para saber luego si ha cambiado.  Es el
        # único sitio por el que pasa una ruta al abrirse, así que apuntarlo
        # aquí lo cubre todo.
        sesion.huella_archivo = None
        if sesion.ruta:
            try:
                estado = Path(sesion.ruta).stat()
                sesion.huella_archivo = (estado.st_mtime_ns, estado.st_size)
            except OSError as error:
                log.debug("No se ha podido mirar el archivo al abrirlo: %s", error)

    @property
    def cronometro(self):
        return self.pestanas.actual.cronometro

    @cronometro.setter
    def cronometro(self, valor) -> None:
        self.pestanas.actual.cronometro = valor

    @property
    def buscador(self):
        return self.pestanas.actual.buscador

    @buscador.setter
    def buscador(self, valor) -> None:
        self.pestanas.actual.buscador = valor

    @property
    def marcadores(self) -> list:
        return self.pestanas.actual.marcadores

    @marcadores.setter
    def marcadores(self, valor) -> None:
        self.pestanas.actual.marcadores = list(valor)

    @property
    def descripciones(self):
        return self.pestanas.actual.descripciones

    @descripciones.setter
    def descripciones(self, valor) -> None:
        self.pestanas.actual.descripciones = valor

    @property
    def libro_daisy(self):
        return self.pestanas.actual.libro_daisy

    @libro_daisy.setter
    def libro_daisy(self, valor) -> None:
        self.pestanas.actual.libro_daisy = valor

    @property
    def _ultima_busqueda(self):
        return self.pestanas.actual.ultima_busqueda

    @_ultima_busqueda.setter
    def _ultima_busqueda(self, valor) -> None:
        self.pestanas.actual.ultima_busqueda = valor

    @property
    def _linea_descrita(self) -> int:
        return self.pestanas.actual.linea_descrita

    @_linea_descrita.setter
    def _linea_descrita(self, valor: int) -> None:
        self.pestanas.actual.linea_descrita = int(valor)

    def _posicion_de_lectura(self) -> int:
        """Por dónde va la lectura en la pestaña activa."""
        return self.lector.posicion() if self.documento is not None else 0

    # -- árbol de contenido ---------------------------------------------------

    def aplicar_arbol(self, mostrar: bool) -> None:
        """Enseña o esconde el árbol de contenido."""
        mostrar = bool(mostrar)
        if mostrar and not self.division.IsSplit():
            ancho = int(self.configuracion.obtener("arbol_ancho", 320))
            self.panel_arbol.Show()
            self.division.SplitVertically(self.panel_arbol, self.pestanas, ancho)
            self.panel_arbol.cargar(self.documento)
        elif not mostrar and self.division.IsSplit():
            self.configuracion.establecer("arbol_ancho", self.division.GetSashPosition())
            self.division.Unsplit(self.panel_arbol)
            self.panel_arbol.Hide()
        if hasattr(self, "opcion_arbol"):
            self.opcion_arbol.Check(mostrar)

    def al_alternar_arbol(self, evento) -> None:
        """Enseña o esconde el árbol y lo deja anotado en las preferencias."""
        mostrar = not self.division.IsSplit()
        self.configuracion.establecer("mostrar_arbol", mostrar)
        self.configuracion.guardar()
        self.aplicar_arbol(mostrar)
        self.anunciar(_("Árbol de contenido a la vista. Ve a él con F6.") if mostrar
                      else _("Árbol de contenido escondido."), inmediato=True)

    def _al_elegir_del_arbol(self, posicion: int) -> None:
        """Salta en el documento a la entrada activada en el árbol."""
        if self.documento is None:
            return
        self.saltar_a(posicion, self.documento.texto_de_linea(posicion).strip())
        self.lector.texto.SetFocus()

    def _refrescar_arbol(self) -> None:
        """Vuelve a llenar el árbol con el documento de la pestaña activa."""
        if self.division.IsSplit():
            self.panel_arbol.cargar(self.documento)

    # -- pestañas -------------------------------------------------------------

    def _al_cambiar_pestana(self) -> None:
        """Pone la ventana al día cuando la pestaña activa es otra.

        Es el momento en que cambia *todo* lo que la ventana enseña del
        documento: el título, la barra de estado, el árbol, qué órdenes tienen
        sentido y con qué grabación trabaja el reproductor.  Se hace aquí de
        una vez para que no haya dos sitios donde acordarse de ello.
        """
        if self.pestanas.actual is None:
            return
        self.lectura_voz.detener()
        if self.libro_daisy is not None and self.libro_daisy.tiene_audio:
            self.reproductor_daisy.cargar(self.libro_daisy)
        else:
            self.reproductor_daisy.descargar()
        self.lectura_voz.refrescar_pronunciacion()
        self._refrescar_arbol()
        self._refrescar_titulo()
        self._menu_de_pestanas()
        self._actualizar_disponibilidad()
        if self.documento is not None:
            self._actualizar_estado(self.lector.posicion())
        else:
            self.SetStatusText(_("Listo. Pulsa Control+O para abrir un documento."))
        self.lector.texto.SetFocus()

    def _refrescar_titulo(self) -> None:
        """Escribe en el título de la ventana el documento de la pestaña activa."""
        if self.documento is None:
            self.SetTitle(NOMBRE)
            return
        titulo = self.sesion.titulo()
        if self.pestanas.con_pestanas and len(self.pestanas) > 1:
            titulo = _("%s (%d de %d)") % (titulo, self.pestanas.indice_actual + 1,
                                           len(self.pestanas))
        self.SetTitle("%s - %s" % (titulo, NOMBRE))
        self.pestanas.refrescar_rotulo(self.sesion)

    def al_nueva_pestana(self, evento) -> None:
        """Abre un documento en una pestaña nueva."""
        if not self.pestanas.con_pestanas:
            wx.MessageBox(
                _("Las pestañas están desactivadas.\n\n"
                  "Actívalas en Herramientas → Opciones → Personalización para poder tener "
                  "varios documentos abiertos a la vez."),
                _("Nueva pestaña"), wx.OK | wx.ICON_INFORMATION, self)
            return
        self.al_abrir(evento, en_pestana_nueva=True)

    def al_pestana_siguiente(self, evento) -> None:
        """Pasa a la pestaña siguiente."""
        self._girar_pestana(True)

    def al_pestana_anterior(self, evento) -> None:
        """Pasa a la pestaña anterior."""
        self._girar_pestana(False)

    def _girar_pestana(self, adelante: bool) -> None:
        """Cambia de pestaña, o avisa de que no hay a dónde ir."""
        self.guardar_sesion()
        if not self.pestanas.girar(adelante):
            self.sonidos.reproducir("limite")
            self.anunciar(_("Solo hay un documento abierto."), inmediato=True)

    def al_lista_pestanas(self, evento) -> None:
        """Enseña los documentos abiertos para saltar a uno."""
        if len(self.pestanas) <= 1:
            self.sonidos.reproducir("limite")
            self.anunciar(_("Solo hay un documento abierto."), inmediato=True)
            return
        with dialogos_navegacion.DialogoPestanas(
                self, self.pestanas.rotulos(), self.pestanas.indice_actual) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK or dialogo.elegida is None:
                return
            elegida = dialogo.elegida
        self.guardar_sesion()
        self.pestanas.seleccionar(elegida)

    def _menu_de_pestanas(self) -> None:
        """Rehace la parte del menú «Pestañas» que lista los documentos abiertos."""
        menu = getattr(self, "menu_pestanas", None)
        if menu is None:
            return
        for elemento in list(menu.GetMenuItems())[self._fijos_de_pestanas:]:
            menu.Delete(elemento)
        if len(self.pestanas) <= 1:
            return
        menu.AppendSeparator()
        for numero, rotulo in enumerate(self.pestanas.rotulos(), start=1):
            entrada = menu.AppendRadioItem(
                wx.ID_ANY, "&%d. %s" % (numero, rotulo.replace("&", "&&")[:60]))
            if numero - 1 == self.pestanas.indice_actual:
                entrada.Check(True)
            self.Bind(wx.EVT_MENU,
                      lambda evento, indice=numero - 1: self._ir_a_pestana(indice),
                      entrada)

    def _ir_a_pestana(self, indice: int) -> None:
        """Salta a una pestaña por su número."""
        self.guardar_sesion()
        self.pestanas.seleccionar(indice)

    # -- zonas ----------------------------------------------------------------

    def _zonas(self) -> list:
        """Las zonas por las que pasa F6, en orden y solo las que están a la vista."""
        zonas = []
        if self.division.IsSplit():
            zonas.append(("arbol", self.panel_arbol.enfocar))
        if self.pestanas.con_pestanas:
            zonas.append(("pestanas", self.pestanas.enfocar_lenguetas))
        zonas.append(("documento", self.pestanas.enfocar_documento))
        return zonas

    def _zona_actual(self, zonas: list) -> int:
        """En qué zona está el foco ahora mismo."""
        foco = wx.Window.FindFocus()
        nombres = [nombre for nombre, _ir in zonas]
        while foco is not None:
            if foco is getattr(self, "panel_arbol", None) or foco is self.panel_arbol.arbol:
                return nombres.index("arbol") if "arbol" in nombres else -1
            if foco is self.pestanas.libro:
                return nombres.index("pestanas") if "pestanas" in nombres else -1
            if isinstance(foco, wx.TextCtrl):
                return nombres.index("documento")
            foco = foco.GetParent()
        return -1

    def cambiar_de_zona(self, adelante: bool) -> None:
        """Lleva el foco a la zona siguiente o a la anterior.

        Con una sola zona no hay nada que hacer y se dice, en vez de dejar la
        tecla muda: quien la pulsa espera que pase algo, y saber que el árbol y
        las pestañas están apagados es justamente lo que le falta.
        """
        zonas = self._zonas()
        if len(zonas) < 2:
            self.sonidos.reproducir("limite")
            self.anunciar(
                _("Solo hay una zona. El árbol de contenido y las pestañas se activan en "
                  "Herramientas, Opciones, Personalización."), inmediato=True)
            return
        actual = self._zona_actual(zonas)
        paso = 1 if adelante else -1
        siguiente = (actual + paso) % len(zonas) if actual >= 0 else 0
        nombre, ir = zonas[siguiente]
        if ir():
            self.anunciar(NOMBRES_DE_ZONA.get(nombre, nombre), inmediato=True)

    def al_zona_siguiente(self, evento) -> None:
        """F6: pasa a la zona siguiente de la ventana."""
        self.cambiar_de_zona(True)

    def al_zona_anterior(self, evento) -> None:
        """Mayús+F6: pasa a la zona anterior de la ventana."""
        self.cambiar_de_zona(False)


    # =======================================================================
    # Construcción de la interfaz
    # =======================================================================

    def _nuevo_id(self, identificador: str) -> int:
        """Reserva un identificador numérico de wx para una orden.

        El objeto devuelto por ``wx.NewIdRef`` libera el identificador cuando
        se destruye, así que hay que conservarlo mientras exista la ventana:
        por eso se guarda en ``_referencias_id`` y no solo su número.
        """
        referencia = wx.NewIdRef()
        self._referencias_id.append(referencia)
        numero = referencia.GetId()
        self._identificadores[identificador] = numero
        return numero

    def _anadir(self, menu: wx.Menu, identificador: str, manejador, casilla: bool = False) -> wx.MenuItem:
        """Añade una opción de menú a partir de la tabla de atajos."""
        numero = self._nuevo_id(identificador)
        etiqueta = tabla_atajos.etiqueta_de_menu(identificador)
        definicion = tabla_atajos.orden(identificador)
        clase = wx.ITEM_CHECK if casilla else wx.ITEM_NORMAL
        elemento = menu.Append(numero, etiqueta, definicion.descripcion, clase)
        self.Bind(wx.EVT_MENU, manejador, id=numero)
        return elemento

    def _construir_menus(self) -> None:
        """Crea la barra de menús completa."""
        barra = wx.MenuBar()

        archivo = wx.Menu()
        self._anadir(archivo, "abrir", self.al_abrir)
        self._anadir(archivo, "abrir_carpeta", self.al_abrir_carpeta)
        self._anadir(archivo, "abrir_direccion", self.al_abrir_direccion)
        self.menu_recientes = wx.Menu()
        archivo.AppendSubMenu(self.menu_recientes, _("&Recientes"))
        archivo.AppendSeparator()
        self._anadir(archivo, "cerrar_libro", self.al_cerrar_libro)
        # Exportar es un submenú porque los destinos son varios y cada uno
        # sirve para algo distinto: texto para cualquier programa, Markdown
        # para conservar la estructura, HTML para el navegador y EPUB para el
        # móvil.  Con una sola orden habría que elegir el formato dentro del
        # diálogo de guardar, que es donde peor se encuentra.
        self.menu_exportar = wx.Menu()
        self._anadir(self.menu_exportar, "exportar_texto",
                     lambda evento: self.al_exportar("txt"))
        self._anadir(self.menu_exportar, "exportar_md",
                     lambda evento: self.al_exportar("md"))
        self._anadir(self.menu_exportar, "exportar_html",
                     lambda evento: self.al_exportar("html"))
        self._anadir(self.menu_exportar, "exportar_epub",
                     lambda evento: self.al_exportar("epub"))
        self.menu_exportar.AppendSeparator()
        self._anadir(archivo, "biblioteca", self.al_biblioteca)
        self._anadir(self.menu_exportar, "exportar_braille",
                     lambda evento: self.al_exportar("brf"))
        self._anadir(self.menu_exportar, "exportar_pef",
                     lambda evento: self.al_exportar("pef"))
        self._anadir(self.menu_exportar, "exportar_daisy", self.al_exportar_daisy)
        self._anadir(self.menu_exportar, "exportar_audio", self.al_exportar_audio)
        archivo.AppendSubMenu(self.menu_exportar, _("&Exportar"))
        archivo.AppendSeparator()
        self._anadir(archivo, "salir", lambda evento: self.Close())
        barra.Append(archivo, _("&Archivo"))

        # El menú de pestañas va aquí, pegado a «Archivo», porque abrir y
        # cerrar documentos es lo mismo que abrir y cerrar pestañas.  Está
        # siempre, aunque las pestañas estén apagadas: es donde se descubre que
        # existen, y sus órdenes lo dicen al usarlas.  Al final se le añade la
        # lista de documentos abiertos, que se rehace sola.
        self.menu_pestanas = wx.Menu()
        self._anadir(self.menu_pestanas, "nueva_pestana", self.al_nueva_pestana)
        self._anadir(self.menu_pestanas, "pestana_siguiente", self.al_pestana_siguiente)
        self._anadir(self.menu_pestanas, "pestana_anterior", self.al_pestana_anterior)
        self._anadir(self.menu_pestanas, "lista_pestanas", self.al_lista_pestanas)
        self.menu_pestanas.AppendSeparator()
        self._anadir(self.menu_pestanas, "zona_siguiente", self.al_zona_siguiente)
        self._anadir(self.menu_pestanas, "zona_anterior", self.al_zona_anterior)
        self.opcion_arbol = self._anadir(self.menu_pestanas, "arbol_contenido",
                                         self.al_alternar_arbol, casilla=True)
        self.opcion_arbol.Check(bool(self.configuracion.obtener("mostrar_arbol", False)))
        #: Cuántas entradas del menú son fijas.  Lo que venga después es la
        #: lista de documentos abiertos, que se borra y se rehace cada vez.
        self._fijos_de_pestanas = self.menu_pestanas.GetMenuItemCount()
        barra.Append(self.menu_pestanas, _("&Pestañas"))

        ir = wx.Menu()
        self._anadir(ir, "buscar", self.al_buscar)
        self._anadir(ir, "buscar_siguiente", lambda evento: self.repetir_busqueda(True))
        self._anadir(ir, "buscar_anterior", lambda evento: self.repetir_busqueda(False))
        ir.AppendSeparator()
        self._anadir(ir, "ir_linea", self.al_ir_a_linea)
        self._anadir(ir, "ir_porcentaje", self.al_ir_a_porcentaje)
        self._anadir(ir, "ir_pagina", self.al_ir_a_pagina)
        ir.AppendSeparator()
        self._anadir(ir, "ir_principio", lambda evento: self.saltar_a(0, _("Principio del documento.")))
        self._anadir(ir, "ir_final", self.al_ir_al_final)
        self._anadir(ir, "atras", self.al_atras)
        self._anadir(ir, "adelante", self.al_adelante)
        ir.AppendSeparator()
        self._anadir(ir, "indice", self.al_indice)
        self._anadir(ir, "elementos", self.al_elementos)
        self._anadir(ir, "marcadores", self.al_marcadores)
        self._anadir(ir, "notas_al_pie", self.al_notas_al_pie)
        barra.Append(ir, _("&Ir a"))

        # El menú de herramientas se reparte en submenús **por tarea**, y no en
        # una lista larga, porque había llegado a veintidós órdenes y recorrer
        # veintidós renglones con la flecha abajo para llegar a la última no lo
        # hace nadie: se acaba usando solo lo de arriba.
        #
        # Lo que **no** baja a un submenú es tan deliberado como lo que baja.
        # Se quedan arriba las tres casillas —ajuste de línea, sonidos y modo
        # lectura— y las cuatro órdenes del programa, porque son las que se
        # tocan a menudo y las que se buscan sin saber su nombre; meterlas un
        # nivel más abajo sería cambiar una lista larga por un laberinto, que
        # de oído es peor.
        #
        # Cada submenú tiene sus propias letras de acceso, así que dentro de
        # uno se llega a cualquier orden con una sola letra.
        herramientas = wx.Menu()

        marcar = wx.Menu()
        self._anadir(marcar, "poner_marcador", self.al_poner_marcador)
        self._anadir(marcar, "poner_nota", self.al_poner_nota)
        self._anadir(marcar, "resaltar", self.al_resaltar)
        self._anadir(marcar, "resaltados", self.al_resaltados)
        marcar.AppendSeparator()
        self._anadir(marcar, "citar", self.al_citar)
        herramientas.AppendSubMenu(marcar, _("&Marcar y citar"))

        ver = wx.Menu()
        self._anadir(ver, "ver_imagen", self.al_ver_imagen)
        self._anadir(ver, "ver_tabla", self.al_ver_tabla)
        self._anadir(ver, "ver_html", self.al_ver_html)
        self._anadir(ver, "ver_capitulo", self.al_ver_capitulo)
        herramientas.AppendSubMenu(ver, _("&Ver el elemento"))

        inteligencia = wx.Menu()
        self._anadir(inteligencia, "describir_imagen", self.al_describir_imagen)
        self._anadir(inteligencia, "describir_todo", self.al_describir_todo)
        inteligencia.AppendSeparator()
        self._anadir(inteligencia, "resumir", self.al_resumir)
        self._anadir(inteligencia, "preguntar", self.al_preguntar)
        herramientas.AppendSubMenu(inteligencia, _("&Inteligencia artificial"))

        # Corregir a mano y pedirle a la IA que revise son las dos formas de
        # enmendar lo que el programa dedujo de un PDF, así que van juntas
        # aunque solo sean dos.
        corregir = wx.Menu()
        self._anadir(corregir, "corregir_elemento", self.al_corregir_elemento)
        self._anadir(corregir, "revisar_estructura", self.al_revisar_estructura)
        herramientas.AppendSubMenu(corregir, _("Corre&gir el documento"))
        # Volver a analizar va pegado a «Corregir» porque es lo mismo visto por
        # el otro lado: allí se enmienda una deducción concreta y aquí se
        # rehace el análisis entero.
        self._anadir(herramientas, "volver_a_analizar", self.al_volver_a_analizar)

        consultar = wx.Menu()
        self._anadir(consultar, "leer_nota", self.al_leer_nota)
        self._anadir(consultar, "diccionario", self.al_diccionario)
        consultar.AppendSeparator()
        self._anadir(consultar, "cuanto_queda", self.al_cuanto_queda)
        self._anadir(consultar, "informacion", self.al_informacion)
        herramientas.AppendSubMenu(consultar, _("Cons&ultar"))

        herramientas.AppendSeparator()
        self.opcion_ajuste = self._anadir(herramientas, "ajuste_linea", self.al_ajuste_linea, casilla=True)
        self.opcion_ajuste.Check(bool(self.configuracion.obtener("ajuste_de_linea")))
        self.opcion_renglon_frase = self._anadir(
            herramientas, "renglon_frase", self.al_renglon_frase, casilla=True)
        self.opcion_renglon_frase.Check(
            bool(self.configuracion.obtener("renglon_por_frase", False)))
        self.opcion_sonidos = self._anadir(herramientas, "sonidos", self.al_alternar_sonidos, casilla=True)
        self.opcion_sonidos.Check(bool(self.configuracion.obtener("sonidos_activados")))
        self.opcion_modo_lectura = self._anadir(
            herramientas, "modo_lectura", self.al_modo_lectura, casilla=True)
        self.opcion_modo_lectura.Check(
            bool(self.configuracion.obtener("modo_lectura", False)))
        herramientas.AppendSeparator()
        self._anadir(herramientas, "temporizador", self.al_temporizador)
        self._anadir(herramientas, "datos_guardados", self.al_datos_guardados)
        self._anadir(herramientas, "perfiles", self.al_perfiles)
        self._anadir(herramientas, "opciones", self.al_opciones)
        voz = wx.Menu()
        self._anadir(voz, "leer_voz", self.al_leer_voz)
        self._anadir(voz, "detener_voz", self.al_detener_voz)
        voz.AppendSeparator()
        self._anadir(voz, "frase_anterior", lambda evento: self._leer_frase(False))
        self._anadir(voz, "frase_siguiente", lambda evento: self._leer_frase(True))
        self._anadir(voz, "leer_seleccion",
                     lambda evento: self.lectura_voz.leer_seleccion())
        voz.AppendSeparator()
        self._anadir(voz, "voz_mas_rapido", lambda evento: self._leer_mas_o_menos(5))
        self._anadir(voz, "voz_mas_lento", lambda evento: self._leer_mas_o_menos(-5))
        voz.AppendSeparator()
        self._anadir(voz, "pronunciacion", self.al_pronunciacion)
        self._anadir(voz, "ajustes_voz", self.al_ajustes_voz)
        barra.Append(voz, _("&Voz"))

        # El reproductor tiene menú propio porque su navegación no se parece a
        # nada de lo demás: los niveles y los saltos por tiempo solo existen
        # cuando lo que se escucha es una grabación.
        daisy = wx.Menu()
        self._anadir(daisy, "daisy_reproductor", self.al_reproductor_daisy)
        daisy.AppendSeparator()
        self._anadir(daisy, "daisy_atras",
                     lambda evento: self.reproductor_daisy.saltar_segundos(-audio.SALTO))
        self._anadir(daisy, "daisy_adelante",
                     lambda evento: self.reproductor_daisy.saltar_segundos(audio.SALTO))
        daisy.AppendSeparator()
        self._anadir(daisy, "daisy_punto_anterior",
                     lambda evento: self.reproductor_daisy.punto_anterior())
        self._anadir(daisy, "daisy_punto_siguiente",
                     lambda evento: self.reproductor_daisy.punto_siguiente())
        self._anadir(daisy, "daisy_nivel_arriba",
                     lambda evento: self.reproductor_daisy.cambiar_nivel(-1))
        self._anadir(daisy, "daisy_nivel_abajo",
                     lambda evento: self.reproductor_daisy.cambiar_nivel(1))
        daisy.AppendSeparator()
        self._anadir(daisy, "daisy_donde_estoy",
                     lambda evento: self.reproductor_daisy.donde_estoy())
        barra.Append(daisy, _("&Reproductor"))
        barra.Append(herramientas, _("&Herramientas"))

        menu_ayuda = wx.Menu()
        self._anadir(menu_ayuda, "manual", self.al_manual)
        self._anadir(menu_ayuda, "atajos_ayuda", self.al_atajos)
        self._anadir(menu_ayuda, "novedades", self.al_novedades)
        self._anadir(menu_ayuda, "primer_uso", self.al_primer_uso)
        self._anadir(menu_ayuda, "practicar", self.al_practicar)
        menu_ayuda.AppendSeparator()
        self._anadir(menu_ayuda, "carpeta_datos",
                     lambda evento: rutas.abrir_en_explorador(rutas.directorio_datos()))
        self._anadir(menu_ayuda, "ver_registro", self.al_ver_registro)
        menu_ayuda.AppendSeparator()
        # Buscar actualizaciones va aquí, justo encima de la invitación al café:
        # las dos son «cosas del programa» y no del documento.  Aparece siempre,
        # aunque no haya servidor configurado en version.py; en ese caso lo dice
        # al pulsarla, que se entiende mejor que una orden que falta.
        self._anadir(menu_ayuda, "buscar_actualizaciones", self.al_buscar_actualizaciones)
        self._anadir(menu_ayuda, "invitar_cafe", self.al_invitar_cafe)
        self._anadir(menu_ayuda, "acerca_de", self.al_acerca_de)
        barra.Append(menu_ayuda, _("A&yuda"))

        self.SetMenuBar(barra)
        self._instalar_aceleradores()
        self._refrescar_recientes()
        self._actualizar_disponibilidad()

    def _instalar_aceleradores(self) -> None:
        """Construye a mano la tabla de atajos de teclado de los menús.

        wxWidgets sabe deducir el atajo del texto que va tras el tabulador en
        la etiqueta del menú, pero solo entiende los nombres de tecla en inglés
        («Home», «Left»...).  Como la interfaz está en español, esos nombres se
        escriben en español y la tabla se construye aquí explícitamente, a
        partir de los mismos datos.  Así el texto que se ve y la tecla que
        funciona no pueden desincronizarse.
        """
        entradas: list[wx.AcceleratorEntry] = []
        for definicion in tabla_atajos.ORDENES:
            numero = self._identificadores.get(definicion.identificador)
            if numero is None:
                continue
            partes = tabla_atajos.descomponer(definicion.atajo)
            if partes is None:
                continue
            modificadores, tecla = partes
            banderas = wx.ACCEL_NORMAL
            for modificador in modificadores:
                minuscula = modificador.lower()
                if minuscula in ("ctrl", "control"):
                    banderas |= wx.ACCEL_CTRL
                elif minuscula in ("shift", _("mayús"), "mayus"):
                    banderas |= wx.ACCEL_SHIFT
                elif minuscula == "alt":
                    banderas |= wx.ACCEL_ALT
            codigo = self._codigo_de_tecla(tecla)
            if codigo is None:
                log.warning("Atajo no reconocido para «%s»: %s",
                            definicion.identificador, definicion.atajo)
                continue
            entradas.append(wx.AcceleratorEntry(banderas, codigo, numero))
            if definicion.atajo_alterno:
                alterno = self._entrada_acelerador(definicion.atajo_alterno, numero)
                if alterno is not None:
                    entradas.append(alterno)
        self.SetAcceleratorTable(wx.AcceleratorTable(entradas))
        log.debug("Tabla de aceleradores instalada con %d atajos", len(entradas))

    def _entrada_acelerador(self, atajo: str, numero: int) -> wx.AcceleratorEntry | None:
        """Convierte un atajo escrito en una entrada de la tabla de teclas."""
        partes = tabla_atajos.descomponer(atajo)
        if partes is None:
            return None
        modificadores, tecla = partes
        banderas = wx.ACCEL_NORMAL
        for modificador in modificadores:
            minuscula = modificador.lower()
            if minuscula in ("ctrl", "control"):
                banderas |= wx.ACCEL_CTRL
            elif minuscula in ("shift", _("mayús"), "mayus"):
                banderas |= wx.ACCEL_SHIFT
            elif minuscula == "alt":
                banderas |= wx.ACCEL_ALT
        codigo = self._codigo_de_tecla(tecla)
        if codigo is None:
            return None
        return wx.AcceleratorEntry(banderas, codigo, numero)

    @staticmethod
    def _codigo_de_tecla(tecla: str) -> int | None:
        """Traduce el nombre de una tecla a su código de wxPython.

        Solo admite las teclas con nombre de :data:`atajos.TECLAS_ESPECIALES`
        y las letras y cifras sueltas.  Los signos de puntuación quedan fuera a
        propósito: en una tabla de aceleradores, Windows interpreta el código
        como una tecla virtual, y el de la coma (44) es el de Impr Pant, de
        modo que un atajo así se registraría sobre otra tecla distinta.
        """
        nombre_wx = tabla_atajos.TECLAS_ESPECIALES.get(tecla)
        if nombre_wx is not None:
            return getattr(wx, nombre_wx, None)
        if len(tecla) == 1 and tecla.isalnum():
            return ord(tecla.upper())
        return None

    def _refrescar_recientes(self) -> None:
        """Rehace el submenú de libros recientes."""
        for elemento in list(self.menu_recientes.GetMenuItems()):
            self.menu_recientes.Delete(elemento)
        recientes = self.configuracion.recientes()
        if not recientes:
            elemento = self.menu_recientes.Append(wx.ID_ANY, _("(No hay documentos recientes)"))
            elemento.Enable(False)
            return
        for numero, ruta in enumerate(recientes, start=1):
            nombre = Path(ruta).name
            # Solo los nueve primeros llevan letra de acceso: del décimo en
            # adelante el subrayado caería otra vez sobre el «1», y entonces esa
            # tecla deja de llevar a ninguna parte y hay que pulsarla varias
            # veces para ir pasando por todos los que empiezan igual.
            rotulo = ("&%d  %s" % (numero, nombre) if numero < 10
                      else "%d  %s" % (numero, nombre))
            elemento = self.menu_recientes.Append(wx.ID_ANY, rotulo, ruta)
            self.Bind(wx.EVT_MENU, lambda evento, destino=ruta: self.abrir_libro(destino),
                      id=elemento.GetId())
        self.menu_recientes.AppendSeparator()
        limpiar = self.menu_recientes.Append(wx.ID_ANY, _("&Vaciar la lista"))
        self.Bind(wx.EVT_MENU, self._al_vaciar_recientes, id=limpiar.GetId())

    def _al_vaciar_recientes(self, evento) -> None:
        """Borra la lista de libros recientes."""
        self.configuracion.establecer("documentos_recientes", [])
        self.configuracion.guardar()
        self._refrescar_recientes()
        self.anunciar(_("Lista de documentos recientes vaciada."))

    def _actualizar_disponibilidad(self) -> None:
        """Activa o desactiva las opciones que necesitan un libro abierto."""
        hay_libro = self.documento is not None
        barra = self.GetMenuBar()
        if barra is None:
            return
        for identificador in ("cerrar_libro", "exportar_texto", "buscar", "buscar_siguiente",
                              "buscar_anterior", "ir_linea", "ir_porcentaje", "ir_pagina",
                              "ir_principio", "ir_final", "atras", "adelante", "indice",
                              "elementos", "marcadores", "poner_marcador", "poner_nota",
                              "resaltar", "resaltados",
                              "ver_imagen", "ver_tabla", "ver_html", "describir_imagen",
                              "describir_todo", "corregir_elemento", "informacion",
                              "leer_voz", "detener_voz", "frase_anterior", "frase_siguiente",
                              "leer_seleccion", "exportar_md", "exportar_html",
                              "exportar_epub", "exportar_braille", "exportar_pef",
                              "exportar_daisy",
                              "exportar_audio", "temporizador",
                              "resumir", "preguntar", "leer_nota", "ver_capitulo",
                              "citar", "cuanto_queda", "revisar_estructura",
                              "volver_a_analizar"):
            numero = self._identificadores.get(identificador)
            if numero is not None:
                barra.Enable(numero, hay_libro)
        # Las órdenes del reproductor solo tienen sentido con una grabación
        # delante: en cualquier otro libro se quedan apagadas en vez de decir
        # «este libro no tiene grabación» una y otra vez.
        # Las órdenes de pestañas solo tienen sentido cuando las pestañas
        # están encendidas, y las de cambiar de una a otra solo cuando hay más
        # de una: apagadas dicen más que un aviso repetido cada vez.
        con_pestanas = self.pestanas.con_pestanas
        varias = con_pestanas and len(self.pestanas) > 1
        for identificador, activo in (("nueva_pestana", con_pestanas),
                                      ("pestana_siguiente", varias),
                                      ("pestana_anterior", varias),
                                      ("lista_pestanas", varias)):
            numero = self._identificadores.get(identificador)
            if numero is not None:
                barra.Enable(numero, activo)

        hay_grabacion = self.reproductor_daisy.activo
        for identificador in ("daisy_reproductor", "daisy_atras", "daisy_adelante",
                              "daisy_punto_anterior", "daisy_punto_siguiente",
                              "daisy_nivel_arriba", "daisy_nivel_abajo",
                              "daisy_donde_estoy"):
            numero = self._identificadores.get(identificador)
            if numero is not None:
                barra.Enable(numero, hay_grabacion)

    # =======================================================================
    # Teclado
    # =======================================================================

    def _preparar_teclas(self) -> None:
        """Prepara la tabla de teclas rápidas y engancha el interceptor."""
        self._teclas_navegacion: dict[str, tuple[Objetivo, int]] = {
            atajo.tecla: (atajo.objetivo, atajo.nivel) for atajo in tabla_atajos.NAVEGACION
        }
        self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar_tecla)

    def _al_pulsar_tecla(self, evento: wx.KeyEvent) -> None:
        """Interpreta las teclas de navegación rápida de una sola pulsación."""
        if self.FindFocus() is not self.lector.texto:
            evento.Skip()   # el foco está en un menú u otro control
            return

        codigo = evento.GetKeyCode()
        mayusculas = evento.ShiftDown()
        control = evento.ControlDown()

        # Tercera vía por la que puede aparecer el menú contextual del control
        # de texto: la tecla Aplicaciones y Mayús+F10.  Se consumen aquí para
        # que no lleguen al control.  Se comprueba antes que nada, incluso sin
        # libro abierto, porque el texto de presentación está en ese mismo
        # control.  Más adelante, estas mismas teclas abrirán un menú propio
        # que dependa de dónde esté el cursor.
        if codigo == wx.WXK_WINDOWS_MENU or (codigo == wx.WXK_F10 and mayusculas):
            log.debug("Tecla de menú contextual consumida")
            return

        if self.documento is None or self._cargando:
            evento.Skip()
            return

        # Control+Inicio y Control+Fin tienen que referirse al libro entero.
        # El control de texto los atiende por su cuenta, antes que el
        # acelerador del menú, y solo conoce el tramo que tiene cargado: sin
        # esto, en un libro grande Control+Fin se detendría a mitad del libro.
        if control and not evento.AltDown() and not mayusculas:
            if codigo == wx.WXK_HOME:
                self.saltar_a(0, _("Principio del documento."), inmediato=True)
                return
            if codigo == wx.WXK_END:
                self.al_ir_al_final(None)
                return

        if control or evento.AltDown() or evento.MetaDown():
            evento.Skip()   # lo resolverán los aceleradores de los menús
            return

        if codigo in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            if self.activar_elemento():
                return
            evento.Skip()
            return

        caracter = evento.GetUnicodeKey()
        if caracter == wx.WXK_NONE or caracter < 32:
            evento.Skip()
            return
        tecla = chr(caracter).upper()

        if tecla in self._teclas_navegacion:
            objetivo, nivel = self._teclas_navegacion[tecla]
            self.navegar_a(objetivo, not mayusculas, nivel)
            return
        if tecla == tabla_atajos.SECCION_SIGUIENTE:
            self.navegar_a(Objetivo.SECCION, not mayusculas)
            return
        if tecla == tabla_atajos.CONTENEDOR_FIN:
            self.navegar_contenedor(not mayusculas)
            return
        if tecla == tabla_atajos.MARCADOR_SIGUIENTE:
            self.navegar_marcador(not mayusculas, solo_notas=False)
            return
        if tecla == tabla_atajos.NOTA_SIGUIENTE:
            self.navegar_marcador(not mayusculas, solo_notas=True)
            return
        if tecla == tabla_atajos.DESCRIBIR_IMAGEN:
            self.al_describir_imagen(None)
            return
        if tecla == tabla_atajos.DEFINIR_PALABRA:
            self.al_diccionario(None)
            return
        if tecla == tabla_atajos.DONDE_ESTOY:
            self.anunciar(navegacion.contexto_de_lectura(self.documento, self.lector.posicion()),
                          inmediato=True)
            return
        if tecla == tabla_atajos.REPETIR_ANUNCIO:
            self.anunciar(self.anunciador.ultimo_mensaje or self.lector.linea_actual(),
                          inmediato=True)
            return
        evento.Skip()

    # =======================================================================
    # Apertura y cierre de libros
    # =======================================================================

    def al_abrir(self, evento, en_pestana_nueva: bool | None = None) -> None:
        """Pide un archivo y lo abre."""
        with wx.FileDialog(self, "Abrir documento", wildcard=formatos.filtro_dialogo(),
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dialogo:
            carpeta = self.configuracion.obtener("ultima_carpeta", "")
            if carpeta and os.path.isdir(carpeta):
                dialogo.SetDirectory(carpeta)
            if dialogo.ShowModal() != wx.ID_OK:
                return
            elegido = dialogo.GetPath()
        self.abrir_libro(elegido, en_pestana_nueva=en_pestana_nueva)

    def _ir_a_lo_ya_abierto(self, ruta: str) -> bool:
        """Si ese documento ya está en una pestaña, se pasa a ella.

        Y si el archivo ha cambiado en el disco desde que se abrió, se relee: es
        lo que evita seguir leyendo un texto que ya no es el del archivo, cosa
        que pasa de verdad cuando alguien vuelve a exportar un documento o
        cuando llega una versión nueva por la sincronización.

        :return: Si se ha ido a una pestaña que ya existía.
        """
        for numero, sesion in enumerate(self.pestanas.sesiones):
            if not sesion.ruta or not _misma_ruta(sesion.ruta, ruta):
                continue
            if numero != self.pestanas.indice_actual:
                self.pestanas.seleccionar(numero)
            if _ha_cambiado_en_disco(sesion):
                log.info("El archivo ha cambiado desde que se abrió; se relee")
                self.anunciar(_("Este documento ha cambiado en el disco. "
                                "Se vuelve a leer."), inmediato=True)
                self.abrir_libro(ruta, en_pestana_nueva=False, releer=True)
                return True
            self.anunciar(_("Ya estaba abierto: %s") % sesion.titulo(),
                          inmediato=True)
            return True
        return False

    def donde_abrir(self) -> bool | None:
        """Decide si el documento que se va a abrir va en una pestaña nueva.

        Se pregunta, y no se decide por el usuario, porque las dos respuestas
        son razonables y cuál toca depende de lo que esté haciendo: quien
        estudia quiere el documento nuevo al lado del que tiene, y quien acaba
        de terminar una novela quiere sustituirla.  Quien lo tenga claro puede
        fijar la respuesta en las opciones y no volver a ver la pregunta.

        :return: ``True`` (pestaña nueva), ``False`` (esta) o ``None`` si se ha
                 cancelado.
        """
        if not self.pestanas.con_pestanas or self.sesion.vacia:
            return False
        preferencia = str(self.configuracion.obtener("pestanas_al_abrir", "preguntar"))
        if preferencia == "nueva":
            return True
        if preferencia == "actual":
            return False
        with dialogos_navegacion.DialogoDondeAbrir(self, self.sesion.titulo()) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                return None
            if dialogo.recordar:
                self.configuracion.establecer(
                    "pestanas_al_abrir", "nueva" if dialogo.en_pestana_nueva else "actual")
                self.configuracion.guardar()
            return dialogo.en_pestana_nueva

    def abrir_libro(self, ruta: str, en_pestana_nueva: bool | None = None,
                    releer: bool = False, posicion_inicial: int = -1) -> None:
        """Abre un libro, analizándolo en un hilo aparte.

        :param ruta: Ruta del archivo que se quiere abrir.
        :param posicion_inicial: Punto del texto en el que dejar el cursor al
                                 terminar, o ``-1`` para volver a donde se
                                 quedó la lectura.  Lo usa la búsqueda en toda
                                 la biblioteca: encontrar una cita y abrir el
                                 libro por el principio no serviría de nada.
        :param en_pestana_nueva: ``True`` para abrirlo en una pestaña nueva,
                                 ``False`` para usar la actual y ``None`` para
                                 decidirlo según las preferencias.
        :param releer: Analizar de nuevo aunque el libro esté en la caché.  Lo
                       usa la corrección de elementos: lo que ha cambiado no es
                       el archivo —así que la caché seguiría siendo válida—
                       sino lo que el usuario ha dicho que era cada cosa.
        """
        if self._cargando:
            self.anunciar(_("Espera: todavía se está abriendo otro documento."))
            return
        # Si ya está abierto se va a su pestaña en vez de abrir otra: dos
        # pestañas del mismo libro son dos sitios donde marcar y guardar la
        # posición, y al cerrar una pisa a la otra.
        if not releer and self._ir_a_lo_ya_abierto(ruta):
            return
        destino = Path(ruta)
        if not destino.exists():
            wx.MessageBox(_("El archivo ya no existe:\n%s") % destino,
                          _("No se encuentra el documento"), wx.OK | wx.ICON_ERROR, self)
            self.configuracion.quitar_reciente(str(destino))
            self._refrescar_recientes()
            return
        if en_pestana_nueva is None:
            en_pestana_nueva = self.donde_abrir()
            if en_pestana_nueva is None:
                return
        self.guardar_sesion()
        #: Dónde hay que dejar el cursor cuando termine de abrirse.  Se guarda
        #: aquí porque el análisis va en otro hilo y el salto solo se puede
        #: hacer cuando el documento ya está cargado.
        self._posicion_al_abrir = int(posicion_inicial)
        if en_pestana_nueva:
            self.pestanas.nueva()
        self._sesion_destino = self.pestanas.actual
        self._cargando = True
        self.SetStatusText(_("Abriendo «%s»...") % destino.name)
        self.anunciar(_("Abriendo %s. Espera un momento.") % destino.stem)

        # El OCR del PDF usa la IA que esté configurada, que es lo que mejor
        # resultado da; si no hay, queda el reconocimiento de Windows.
        self._preparar_ocr_pdf()

        # Progreso: un EPUB tarda una décima, pero un PDF escaneado son
        # minutos.  La ventana se abre siempre y se cierra sola: en lo rápido
        # apenas se ve, y en lo lento es la diferencia entre saber qué está
        # pasando y no saberlo, además de poder echarse atrás.
        canal = formatos.Progreso()
        self._progreso = dialogos_progreso.DialogoProgreso(
            self, _("Abriendo el documento"), _("Abriendo %s...") % destino.name,
            al_cancelar=canal.cancelar)
        canal.conectar(self._progreso.avanzar)
        self._progreso.mostrar_tras()

        opciones = formatos.OpcionesAnalisis(
            tablas_en_linea=bool(self.configuracion.obtener("tablas_en_linea")),
            anunciar_imagenes_sin_texto=bool(
                self.configuracion.obtener("anunciar_imagenes_sin_texto")),
            estructura_pdf=bool(self.configuracion.obtener("pdf_estructura", True)),
            geometria_pdf=bool(self.configuracion.obtener("pdf_geometria", True)),
            marcar_llamadas_de_nota=bool(
                self.configuracion.obtener("marcar_llamadas_de_nota", False)),
            solo_articulo=bool(self.configuracion.obtener("solo_articulo", True)),
            progreso=canal,
        )
        usar_cache = bool(self.configuracion.obtener("usar_cache")) and not releer

        def trabajo():
            """Analiza el libro fuera del hilo de la interfaz."""
            try:
                documento = None
                if usar_cache:
                    documento = cache.cargar(destino, opciones.firma())
                if documento is None:
                    with cronometro(log, "apertura completa de %s" % destino.name):
                        documento = formatos.analizar(destino, opciones)
                    if bool(self.configuracion.obtener("usar_cache")):
                        cache.guardar(documento, opciones.firma())
                # La grabación se lee siempre, venga el texto de la caché o no:
                # es rápido y es lo que ata cada frase con su trozo de audio.
                libro_daisy = None
                if lector_daisy.es_libro_daisy(destino):
                    try:
                        libro_daisy = lector_daisy.abrir(destino, canal)
                    except Exception as error:
                        registrar_excepcion(
                            log, "No se ha podido leer la grabación DAISY", error)
                wx.CallAfter(self._libro_listo, documento, str(destino), libro_daisy)
            except formatos.Cancelado:
                log.info("Apertura cancelada por el usuario: %s", destino)
                wx.CallAfter(self._libro_cancelado)
            except formatos.ErrorFormato as error:
                wx.CallAfter(self._libro_fallido, str(error), str(destino))
            except Exception as error:  # pragma: no cover - salvaguarda
                registrar_excepcion(log, "Fallo inesperado al abrir %s" % destino, error)
                wx.CallAfter(
                    self._libro_fallido,
                    _("Ha ocurrido un error inesperado al abrir el libro.\n"
                    "Consulta el registro para ver los detalles.\n\n%s") % error,
                    str(destino),
                )

        threading.Thread(target=trabajo, name="analisis", daemon=True).start()

    def _preparar_ocr_pdf(self) -> None:
        """Deja listos los analizadores que reconocen páginas escaneadas.

        Se hace justo antes de abrir, no al arrancar, porque el usuario puede
        haber cambiado el proveedor de IA o las opciones mientras tanto.

        Son dos: el de PDF y el de DjVu.  Comparten los mismos ajustes porque el
        usuario no elige «cómo reconozco los PDF» sino «cómo reconozco lo
        escaneado»: tener dos motores distintos según el formato del archivo
        sería una diferencia que no le importa a nadie.
        """
        from formatos import ocr
        from formatos.djvu import analizador_djvu
        from formatos.pdf import analizador_pdf
        from interfaz.dialogos import contrasena as dialogo_contrasena
        from nucleo.ia.servicio import Servicio

        servicio = Servicio(self.configuracion)
        ajustes = ocr.Ajustes.desde_configuracion(self.configuracion)
        modo = str(self.configuracion.obtener("pdf_ocr_modo", "auto"))
        idiomas = str(self.configuracion.obtener("pdf_ocr_idiomas", ""))
        maximo = int(self.configuracion.obtener("pdf_ocr_maximo", 100))
        for analizador in (analizador_pdf, analizador_djvu):
            analizador.servicio_ia = servicio if servicio.activa else None
            analizador.ocr_modo = modo
            analizador.ocr_idiomas = idiomas
            analizador.ocr_ajustes = ajustes
            analizador.ocr_maximo = maximo
        analizador_pdf.geometria = bool(self.configuracion.obtener("pdf_geometria", True))
        # La contraseña de cada documento se pide al abrirlo y no se recuerda,
        # así que se limpia la del anterior: dejarla puesta haría que el
        # siguiente PDF cifrado intentara abrirse con una clave ajena.
        analizador_pdf.contrasena = ""
        analizador_pdf.pedir_contrasena = (
            lambda ruta, intento: dialogo_contrasena.solicitar(self, ruta, intento))

    def _cerrar_progreso(self) -> None:
        """Cierra la ventana de progreso, si estaba abierta."""
        if self._progreso is not None:
            self._progreso.cerrar()
            self._progreso = None

    def _cerrar_pestana_huerfana(self) -> None:
        """Cierra la pestaña que se abrió para un documento que no llegó.

        Si la apertura se cancela o falla, la pestaña nueva se quedaría vacía y
        de por medio.  La que ya tenía algo dentro no se toca, claro.
        """
        destino = self._sesion_destino
        self._sesion_destino = None
        if destino is None or not destino.vacia or len(self.pestanas) <= 1:
            return
        if destino in self.pestanas.sesiones:
            self.pestanas.cerrar(self.pestanas.sesiones.index(destino))
            self._menu_de_pestanas()

    def _libro_cancelado(self) -> None:
        """El usuario ha cancelado la apertura: se deja todo como estaba."""
        self._cargando = False
        self._cerrar_pestana_huerfana()
        self._cerrar_progreso()
        self.SetStatusText(_("Apertura cancelada."))
        self._por_restaurar = None
        self.sonidos.reproducir("limite")
        self.lector.texto.SetFocus()
        self.anunciar(_("Apertura cancelada."))

    def _libro_listo(self, documento: Documento, ruta: str, libro_daisy=None) -> None:
        """Se ejecuta en el hilo de la interfaz cuando el libro está analizado."""
        self._cargando = False
        self._cerrar_progreso()
        if wx.IsBusy():
            wx.EndBusyCursor()
        # El documento va a la pestaña que lo pidió, no a la que esté delante:
        # analizar un PDF escaneado son minutos, y en ese rato el usuario puede
        # haberse ido a leer otra cosa.
        destino = self._sesion_destino
        self._sesion_destino = None
        if destino is not None and destino in self.pestanas.sesiones:
            self.pestanas.seleccionar(self.pestanas.sesiones.index(destino))
        self.documento = documento
        self.ruta_actual = ruta
        self.buscador = Buscador(documento)
        # Las descripciones de las imágenes viajan con el libro: al abrirlo
        # vuelven las que ya se hicieron, sin gastar otra petición de IA.
        self.descripciones = descripciones.Coleccion(ruta)
        self._linea_descrita = -1
        # Cada libro tiene sus nombres propios, así que su tabla de
        # pronunciación se rehace al abrirlo.
        self.lectura_voz.refrescar_pronunciacion()
        # El cronómetro de lectura continúa donde se quedó la última vez.
        self.cronometro = estadisticas.Cronometro.desde_dict(
            self.configuracion.datos_de(ruta).lectura)

        datos = self.configuracion.datos_de(ruta)
        datos.titulo = documento.metadatos.titulo
        self.marcadores = list(datos.marcadores)
        posicion = datos.posicion if self.configuracion.obtener("recordar_posicion") else 0
        pedida = getattr(self, "_posicion_al_abrir", -1)
        if pedida >= 0:
            posicion = pedida
        self._posicion_al_abrir = -1
        posicion = max(0, min(posicion, len(documento)))

        self.libro_daisy = libro_daisy
        if libro_daisy is not None and libro_daisy.tiene_audio:
            self.reproductor_daisy.cargar(libro_daisy)
        else:
            self.reproductor_daisy.descargar()

        self.lector.cargar_documento(documento, posicion)
        # Cómo marca sus diálogos este libro: se mira una vez, y no
        # frase a frase, porque la respuesta vale para el libro entero.
        self.lectura_voz.mirar_si_hay_dialogo()
        self.lector.restaurar_historial(datos.historial, datos.indice_historial)
        # Si la ventana de progreso llegó a aparecer, el foco estaba en ella;
        # al cerrarse tiene que volver al texto, no quedarse en el aire.
        self.lector.texto.SetFocus()
        self.configuracion.anadir_reciente(ruta)
        self.configuracion.establecer("ultima_carpeta", str(Path(ruta).parent))
        self.configuracion.guardar()
        self._refrescar_recientes()
        self._actualizar_disponibilidad()

        titulo = documento.metadatos.titulo or Path(ruta).stem
        autor = documento.metadatos.autor
        self._refrescar_titulo()
        self._refrescar_arbol()
        self._menu_de_pestanas()
        self.sonidos.reproducir("abrir")
        resumen = _("%s%s. %d por ciento leído.") % (
            titulo, _(", de %s") % autor if autor else "", documento.porcentaje_en(posicion)
        )
        self.anunciar(_("Documento abierto: %s") % resumen)
        self._actualizar_estado(posicion)
        self._presentar_grabacion(posicion)
        self._continuar_cola()

    def _presentar_grabacion(self, posicion: int) -> None:
        """Avisa de que el libro trae grabación y, si se pidió, la arranca.

        Merece un aviso propio: en un libro DAISY de solo audio, el texto que
        se ve es el índice y poco más, y sin decirlo parecería que el libro ha
        venido incompleto cuando en realidad lo que trae es una voz humana
        leyéndolo entero.
        """
        if not self.reproductor_daisy.activo:
            return
        libro = self.libro_daisy
        self.reproductor_daisy.frase = self.reproductor_daisy.frase_en(posicion)
        self.anunciar(_("%s Duración de la grabación: %s. Control+Espacio para escucharla, "
                      "Control+Alt+R para los mandos.")
                      % (libro.descripcion_del_tipo(),
                         audio.duracion_legible(libro.duracion)))
        if self.configuracion.obtener("daisy_reproducir_al_abrir"):
            self.reproductor_daisy.reproducir(self.reproductor_daisy.frase)

    def _libro_fallido(self, mensaje: str, ruta: str) -> None:
        """Informa de que un libro no se ha podido abrir."""
        self._cargando = False
        self._cerrar_pestana_huerfana()
        self._cerrar_progreso()
        if wx.IsBusy():
            wx.EndBusyCursor()
        self.SetStatusText(_("No se ha podido abrir el documento."))
        self.sonidos.reproducir("error")
        log.error("No se ha podido abrir %s: %s", ruta, mensaje)
        if getattr(self, "_por_restaurar", None):
            # Restaurando la sesión anterior no se interrumpe con un aviso por
            # cada documento que ya no se pueda abrir: se anota y se sigue.
            self._continuar_cola()
            return
        wx.MessageBox(mensaje, _("No se ha podido abrir el documento"), wx.OK | wx.ICON_ERROR, self)

    def al_abrir_carpeta(self, evento) -> None:
        """Pide una carpeta y la abre como libro DAISY.

        Hace falta una orden aparte porque un libro DAISY **no es un archivo**:
        es una carpeta con el índice, los SMIL y la grabación dentro.  Se puede
        abrir eligiendo cualquier archivo de dentro, pero eso hay que saberlo;
        así se elige el libro tal y como lo ve quien lo ha descargado.
        """
        inicial = str(self.configuracion.obtener("ultima_carpeta", "") or "")
        with wx.DirDialog(self, _("Elige la carpeta del libro DAISY"), inicial,
                          style=wx.DD_DIR_MUST_EXIST) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                return
            carpeta = dialogo.GetPath()
        if not lector_daisy.es_libro_daisy(carpeta):
            wx.MessageBox(
                _("En esa carpeta no hay ningún libro DAISY.\n\n"
                  "Un libro DAISY tiene dentro un archivo «ncc.html» (versión 2.02) o uno "
                  "con extensión «.ncx» (versión 3). Comprueba que has elegido la carpeta "
                  "del libro y no la que la contiene."),
                _("Abrir libro DAISY"), wx.OK | wx.ICON_INFORMATION, self)
            return
        self.abrir_libro(carpeta)

    def al_cerrar_libro(self, evento) -> None:
        """Cierra el documento actual, o su pestaña si hay más de una.

        Con varias pestañas abiertas, «cerrar» es cerrar la pestaña: es lo que
        se espera de Control+W en cualquier programa.  La última no se cierra
        nunca, se vacía: el programa siempre tiene un panel de lectura, que es
        donde se enseña la pantalla de bienvenida.
        """
        if self.documento is None and len(self.pestanas) <= 1:
            return
        self.lectura_voz.detener()
        self.reproductor_daisy.descargar()
        self.guardar_sesion()
        if len(self.pestanas) > 1:
            self.pestanas.cerrar(self.pestanas.indice_actual)
            self.sonidos.reproducir("cerrar")
            self._al_cambiar_pestana()
            self._menu_de_pestanas()
            self.anunciar(_("Pestaña cerrada. Quedan %d.") % len(self.pestanas))
            return
        self.libro_daisy = None
        self.documento = None
        self.ruta_actual = ""
        self.buscador = None
        self.marcadores = []
        self.descripciones = descripciones.Coleccion()
        self.lector.cerrar_documento()
        self._refrescar_arbol()
        self.pestanas.refrescar_rotulo(self.sesion)
        self.SetTitle(NOMBRE)
        self.SetStatusText(_("Listo. Pulsa Control+O para abrir un documento."))
        self._actualizar_disponibilidad()
        self.sonidos.reproducir("cerrar")
        self.anunciar(_("Documento cerrado."))

    def guardar_sesion(self, sesion=None) -> None:
        """Guarda la posición, los marcadores y el historial de una sesión.

        :param sesion: Sesión que se guarda; la activa si no se dice otra.
        """
        sesion = sesion if sesion is not None else self.pestanas.actual
        if sesion is None or sesion.documento is None or not sesion.ruta:
            return
        datos = self.configuracion.datos_de(sesion.ruta)
        datos.lectura = sesion.cronometro.como_dict()
        datos.posicion = sesion.panel.posicion()
        datos.marcadores = list(sesion.marcadores)
        historial, indice = sesion.panel.historial()
        datos.historial = historial
        datos.indice_historial = indice
        datos.titulo = sesion.documento.metadatos.titulo
        datos.autor = sesion.documento.metadatos.autor
        # El total se guarda para que la biblioteca pueda decir el porcentaje
        # leído de cada libro sin tener que abrirlos todos.
        datos.total = len(sesion.documento.texto)
        sincronizacion.marcar_ahora(datos)
        self.configuracion.guardar()
        # Si lo que ha cambiado son los marcadores, el árbol tiene que
        # enterarse.  Se mira aquí y no en cada sitio donde se ponen o se
        # quitan, que son media docena y el séptimo se olvidaría.
        if sesion is self.pestanas.actual:
            self.refrescar_arbol_propio()
        log.debug("Sesión guardada en la posición %d", datos.posicion)

    def guardar_todas_las_sesiones(self) -> None:
        """Guarda la posición de todas las pestañas, no solo la de delante.

        Al cerrar el programa hay que guardarlas todas: si no, la pestaña que
        se dejó de fondo volvería mañana al principio del documento, que es
        exactamente el trabajo que las pestañas están para no perder.
        """
        for sesion in list(self.pestanas.sesiones):
            self.guardar_sesion(sesion)

    # -- documentos abiertos de una sesión a otra ----------------------------

    def anotar_documentos_abiertos(self) -> None:
        """Apunta qué documentos quedaban abiertos, para volver a abrirlos.

        Se guarda siempre, esté o no activada la opción de restaurarlos: así,
        quien la active después encuentra ahí lo que tenía abierto la última
        vez en lugar de una lista vacía.  Lo que la opción decide es si se
        vuelven a abrir, no si se apuntan.
        """
        rutas_abiertas = []
        activa = 0
        for indice, sesion in enumerate(self.pestanas.sesiones):
            if not sesion.ruta or sesion.documento is None:
                continue
            if sesion is self.pestanas.actual:
                activa = len(rutas_abiertas)
            rutas_abiertas.append(str(sesion.ruta))
        self.configuracion.establecer("documentos_abiertos", rutas_abiertas)
        self.configuracion.establecer("documento_activo", activa)

    def restaurar_documentos_abiertos(self, ademas: str = "") -> bool:
        """Vuelve a abrir los documentos que quedaron abiertos al cerrar.

        Se abren **uno detrás de otro** y no todos a la vez: el análisis corre
        en un hilo y solo hay uno, así que pedir cinco documentos de golpe haría
        que cuatro se descartaran por «espera, todavía se está abriendo otro».
        La cola la vacía :meth:`_seguir_restaurando` según van llegando.

        Los archivos que ya no existen se saltan sin decir nada: que un libro
        se haya movido de sitio no es un error que merezca un aviso al arrancar.

        :param ademas: Un documento más que abrir al final, el que se haya
                       pedido desde el explorador.  Se pone el último y se queda
                       delante: es el que se ha pedido.
        :return: Si hay algo que restaurar.
        """
        if not self.configuracion.obtener("restaurar_documentos", False):
            return False
        guardados = self.configuracion.obtener("documentos_abiertos", []) or []
        pendientes = [str(ruta) for ruta in guardados if Path(str(ruta)).is_file()]
        try:
            activo = int(self.configuracion.obtener("documento_activo", 0) or 0)
        except (TypeError, ValueError):
            activo = 0
        if ademas:
            # Si ya estaba en la sesión no se pone dos veces: se deja donde
            # estaba y se marca como el que va delante.
            iguales = [numero for numero, uno in enumerate(pendientes)
                       if _misma_ruta(uno, ademas)]
            if iguales:
                activo = iguales[0]
            else:
                pendientes.append(ademas)
                activo = len(pendientes) - 1
        if not pendientes:
            return False
        self._por_restaurar = pendientes
        self._restaurar_activo = max(0, min(activo, len(pendientes) - 1))
        log.info("Restaurando %d documentos de la sesión anterior", len(pendientes))
        self._seguir_restaurando()
        return True

    def abrir_con_la_sesion(self, ruta: str) -> None:
        """Abre un libro y, si estaba pedido, recupera antes la sesión anterior.

        Es lo que pasa al arrancar el programa desde el explorador de archivos.
        El libro pedido va **el último de la cola** y se queda delante: es el que
        se ha pedido, y encontrarlo detrás de otros cinco sería lo mismo que no
        haberlo abierto.

        Si ya estaba en la sesión anterior no se abre dos veces: la cola lo
        detecta y se queda con esa pestaña.
        """
        if not self.restaurar_documentos_abiertos(ademas=ruta):
            self.abrir_libro(ruta)

    def _seguir_restaurando(self) -> None:
        """Abre el siguiente documento de la cola de restauración."""
        pendientes = getattr(self, "_por_restaurar", None)
        if not pendientes:
            return
        ruta = pendientes.pop(0)
        # El primero va en la pestaña que ya existe, que está vacía; los demás,
        # cada uno en la suya.
        primero = len(self.pestanas.sesiones) == 1 and self.sesion.vacia
        self.abrir_libro(ruta, en_pestana_nueva=not primero)

    def _continuar_cola(self) -> None:
        """Sigue con la restauración, o la da por terminada si ya no queda nada."""
        if getattr(self, "_por_restaurar", None) is None:
            return
        if self._por_restaurar:
            wx.CallAfter(self._seguir_restaurando)
        else:
            self._terminar_restauracion()

    def _terminar_restauracion(self) -> None:
        """Coloca delante la pestaña que lo estaba y da por hecha la cola."""
        self._por_restaurar = None
        indice = getattr(self, "_restaurar_activo", 0)
        if 0 <= indice < len(self.pestanas.sesiones):
            self.pestanas.seleccionar(indice)
        self._menu_de_pestanas()

    # =======================================================================
    # Navegación
    # =======================================================================

    def _al_cerrar_menu(self, evento) -> None:
        """Anota que acaba de cerrarse un menú, y por tanto el foco va a moverse."""
        self._menu_cerrado_en = time.monotonic()
        evento.Skip()

    def anunciar(self, mensaje: str, inmediato: bool = False) -> None:
        """Anuncia un mensaje y lo muestra en la barra de estado.

        :param mensaje: Texto que se lee y se escribe en la barra de estado.
        :param inmediato: ``True`` cuando el aviso responde a una tecla pulsada
                          dentro del texto del libro, donde el foco no se mueve
                          y no hace falta esperar.  Las órdenes de menú usan el
                          valor por omisión, que espera a que el foco vuelva del
                          menú: si no, el lector de pantalla anuncia el control
                          que recibe el foco y tapa el aviso.

        **Si el aviso llega justo después de cerrarse un menú, la espera se
        pone de todas formas**, aunque se haya pedido inmediato.  La misma
        orden se puede lanzar de dos maneras —con su tecla, sin mover el foco, o
        desde el menú, que sí lo mueve— y quien la escribe no tiene por qué
        acordarse de distinguirlo en cada llamada.  Sin esto, un aviso como «no
        hay ninguna tabla que ver como HTML» se decía mientras el foco volvía al
        texto y el lector de pantalla lo tapaba con la línea del cursor.
        """
        if not mensaje:
            return
        if inmediato and time.monotonic() - self._menu_cerrado_en < ESPERA_TRAS_MENU:
            inmediato = False
        retardo = anuncios.RETARDO_INMEDIATO if inmediato else anuncios.RETARDO_NORMAL
        self.anunciador.anunciar(mensaje, retardo=retardo)
        self.SetStatusText(mensaje.replace("\n", " ")[:200])

    def saltar_a(self, posicion: int, mensaje: str = "", inmediato: bool = False) -> None:
        """Coloca el cursor en una posición y lo anuncia."""
        if self.documento is None:
            return
        self.lector.ir_a(posicion, registrar=True)
        if mensaje:
            self.anunciar(mensaje, inmediato=inmediato)

    def navegar_a(self, objetivo: Objetivo, siguiente: bool, nivel: int = 0) -> None:
        """Salta al elemento anterior o siguiente del tipo indicado."""
        if self.documento is None:
            return
        resultado = navegacion.navegar(
            self.documento, self.lector.posicion(), objetivo, siguiente,
            circular=bool(self.configuracion.obtener("navegacion_circular")), nivel=nivel,
        )
        self._aplicar_resultado(resultado)

    def navegar_contenedor(self, al_final: bool) -> None:
        """Va al principio o más allá del final de la lista o tabla actual."""
        if self.documento is None:
            return
        resultado = navegacion.navegar_contenedor(self.documento, self.lector.posicion(), al_final)
        self._aplicar_resultado(resultado)

    def _aplicar_resultado(self, resultado) -> None:
        """Mueve el cursor y anuncia según el resultado de una navegación."""
        if not resultado.encontrado:
            self.sonidos.reproducir("limite")
            self.anunciar(resultado.mensaje, inmediato=True)
            return
        if resultado.dio_la_vuelta:
            self.sonidos.reproducir("vuelta")
        elif resultado.tipo is not None:
            self.sonidos.reproducir_marca(resultado.tipo)
        # El aviso se prepara y se marca **antes** de mover el cursor: al
        # moverlo se dispara _al_moverse, que si no lo diría por su cuenta y
        # el anuncio de la navegación lo cortaría a media frase.
        descripcion = self._descripcion_guardada_en(resultado.posicion)
        if descripcion:
            self._linea_descrita = self.documento.linea_de(resultado.posicion)
        self.lector.ir_a(resultado.posicion, registrar=True)
        self.anunciar(resultado.mensaje + descripcion, inmediato=True)

    def _descripcion_guardada_en(self, posicion: int) -> str:
        """Devuelve la descripción guardada de la imagen que hay en un punto.

        Devuelve la cadena vacía si no hay imagen, si no tiene descripción
        guardada o si el usuario ha desactivado el aviso.
        """
        if self.documento is None:
            return ""
        if not self.configuracion.obtener("ia_anunciar_descripcion", True):
            return ""
        # De las de la línea, la que empieza en ese punto o justo antes: es la
        # que se acaba de alcanzar.  Con cuatro imágenes seguidas, anunciar
        # siempre la descripción de la primera sería decir lo que no es.
        elementos = [marca for marca
                     in navegacion.elementos_en_linea(self.documento, posicion)
                     if marca.tipo in (TipoMarca.IMAGEN, TipoMarca.FIGURA)]
        alcanzadas = [marca for marca in elementos if marca.posicion <= posicion]
        for marca in reversed(alcanzadas or elementos[:1]):
            guardada = self.descripciones.obtener(getattr(marca, "referencia", ""))
            if guardada is None:
                continue
            # Que la imagen tenga los datos sacados se avisa siempre: es lo que
            # le dice a quien escucha que ahí hay una tabla que recorrer con
            # Control+H, en lugar de conformarse con la descripción.
            aviso = _(" Con datos, Control+H.") if guardada.tiene_datos else ""
            if guardada.texto.strip():
                return _(" Descripción guardada: %s") % guardada.texto.strip() + aviso
            if aviso:
                return aviso
        return ""

    def navegar_marcador(self, siguiente: bool, solo_notas: bool) -> None:
        """Salta al marcador o a la nota anterior o siguiente."""
        if self.documento is None:
            return
        candidatos = [m for m in self.marcadores if (m.es_nota if solo_notas else True)]
        if not candidatos:
            self.sonidos.reproducir("limite")
            self.anunciar(_("No hay notas en este documento.") if solo_notas
                          else _("No hay marcadores en este documento."), inmediato=True)
            return
        actual = self.lector.posicion()
        candidatos.sort(key=lambda m: m.inicio)
        elegido = None
        if siguiente:
            elegido = next((m for m in candidatos if m.inicio > actual), None)
        else:
            anteriores = [m for m in candidatos if m.inicio < actual]
            elegido = anteriores[-1] if anteriores else None
        if elegido is None:
            self.sonidos.reproducir("limite")
            self.anunciar(_("No hay %s %s.") % ("siguiente" if siguiente else "anterior",
                                             "nota" if solo_notas else "marcador"), inmediato=True)
            return
        self.sonidos.reproducir("nota" if elegido.es_nota else "marcador")
        self.lector.ir_a(elegido.inicio, registrar=True)
        if elegido.es_nota:
            self.anunciar("Nota: %s" % elegido.nota, inmediato=True)
        else:
            self.anunciar("Marcador. %s" % self.lector.linea_actual().strip(), inmediato=True)

    def al_atras(self, evento) -> None:
        """Vuelve a la posición anterior del historial."""
        if not self.lector.retroceder():
            self.sonidos.reproducir("limite")
            self.anunciar(_("No hay ninguna posición anterior."))
        else:
            self.anunciar(_("Posición anterior. ") + self.lector.linea_actual().strip())

    def al_adelante(self, evento) -> None:
        """Avanza a la siguiente posición del historial."""
        if not self.lector.avanzar():
            self.sonidos.reproducir("limite")
            self.anunciar(_("No hay ninguna posición siguiente."))
        else:
            self.anunciar(_("Posición siguiente. ") + self.lector.linea_actual().strip())

    def al_ir_al_final(self, evento) -> None:
        """Salta al final del libro."""
        if self.documento is not None:
            self.saltar_a(len(self.documento), _("Final del documento."))

    def al_ir_a_linea(self, evento) -> None:
        """Pide un número de línea y salta a ella."""
        if self.documento is None:
            return
        actual = self.documento.linea_de(self.lector.posicion()) + 1
        with dialogos_navegacion.DialogoSalto(
            self, _("Ir a la línea"), _("&Número de línea (de 1 a %d):") % self.documento.total_lineas,
            1, self.documento.total_lineas, actual,
        ) as dialogo:
            if dialogo.ShowModal() == wx.ID_OK and dialogo.valor is not None:
                destino = self.documento.inicio_de_linea(dialogo.valor - 1)
                self.saltar_a(destino, _("Línea %d.") % dialogo.valor)

    def al_ir_a_porcentaje(self, evento) -> None:
        """Pide un porcentaje y salta al punto correspondiente."""
        if self.documento is None:
            return
        actual = self.documento.porcentaje_en(self.lector.posicion())
        with dialogos_navegacion.DialogoSalto(
            self, _("Ir al porcentaje"), _("&Porcentaje del documento (de 0 a 100):"), 0, 100, actual,
        ) as dialogo:
            if dialogo.ShowModal() == wx.ID_OK and dialogo.valor is not None:
                destino = self.documento.posicion_de_porcentaje(dialogo.valor)
                self.saltar_a(destino, _("%d por ciento del documento.") % dialogo.valor)

    def al_ir_a_pagina(self, evento) -> None:
        """Pide un número de página y salta a ella."""
        if self.documento is None:
            return
        total = self.documento.total_paginas
        if not total:
            self.sonidos.reproducir("limite")
            self.anunciar(_("Este documento no tiene numeración de páginas."))
            return
        grupo = self.documento.marcas.grupo(TipoMarca.SALTO_PAGINA)
        actual = max(self.documento.indice_de_pagina(self.lector.posicion()) + 1, 1)
        with dialogos_navegacion.DialogoSalto(
            self, _("Ir a la página"), _("&Número de página (de 1 a %d):") % total, 1, total, actual,
        ) as dialogo:
            if dialogo.ShowModal() == wx.ID_OK and dialogo.valor is not None:
                marca = grupo[dialogo.valor - 1]
                self.sonidos.reproducir("pagina")
                self.saltar_a(marca.posicion, _("Página %s.") % (marca.texto or dialogo.valor))

    def al_indice(self, evento) -> None:
        """Abre el índice del libro."""
        if self.documento is None:
            return
        with dialogos_navegacion.DialogoIndice(self, self.documento, self.lector.posicion()) as dialogo:
            if dialogo.ShowModal() == wx.ID_OK and dialogo.posicion_elegida is not None:
                self.sonidos.reproducir("seccion")
                self.saltar_a(dialogo.posicion_elegida, self.lector.linea_actual().strip())

    def al_notas_al_pie(self, evento) -> None:
        """Abre el visor de notas al pie del documento.

        Dos destinos y los dos hacen falta: la llamada es el pasaje que cita la
        nota, y la nota es su texto al final del libro.  El visor devuelve el
        que se haya pedido y aquí solo se salta.
        """
        if self.documento is None:
            return
        with dialogos_notas_al_pie.DialogoNotas(
                self, self.documento, self.lector.posicion()) as dialogo:
            if (dialogo.ShowModal() == wx.ID_OK
                    and dialogo.posicion_elegida is not None):
                self.saltar_a(dialogo.posicion_elegida,
                              self.lector.linea_actual().strip())

    def al_elementos(self, evento) -> None:
        """Abre la lista de elementos del libro."""
        if self.documento is None:
            return
        with dialogos_navegacion.DialogoElementos(
                self, self.documento, self.lector.posicion(),
                marcadores=self.marcadores) as dialogo:
            if dialogo.ShowModal() == wx.ID_OK and dialogo.posicion_elegida is not None:
                self.saltar_a(dialogo.posicion_elegida, self.lector.linea_actual().strip())

    # =======================================================================
    # Búsqueda
    # =======================================================================

    def al_buscar(self, evento) -> None:
        """Abre (o vuelve a mostrar) el cuadro de búsqueda.

        Si se está escuchando el libro, la voz **se calla y se guarda el sitio**:
        buscar algo mientras se escucha es lo más normal del mundo —«¿dónde
        decía esto?»— y hasta ahora costaba la lectura entera. Al cerrar la
        búsqueda se sigue leyendo, desde el resultado si se ha encontrado algo y
        desde donde se dejó si no.
        """
        if self.documento is None:
            return
        self.lectura_voz.pausar_para_buscar()
        if self._dialogo_buscar is None:
            self._dialogo_buscar = dialogos_buscar.DialogoBuscar(
                self, self.configuracion, self.ejecutar_busqueda
            )
        seleccion = self.lector.texto_seleccionado().strip()
        if seleccion and len(seleccion) < 100:
            self._dialogo_buscar.campo.SetValue(seleccion)
        self._dialogo_buscar.Show()
        self._dialogo_buscar.Raise()
        self._dialogo_buscar.campo.SetFocus()

    def ejecutar_busqueda(self, termino: str, hacia_adelante: bool,
                          opciones: OpcionesBusqueda) -> bool:
        """Busca un término y lleva el cursor al resultado."""
        if self.documento is None or self.buscador is None:
            return False
        self._ultima_busqueda = (termino, opciones)
        desde = self.lector.posicion()
        resultado = self.buscador.buscar(termino, desde, hacia_adelante, opciones)
        if resultado.encontrado:
            self.sonidos.reproducir("encontrado")
            self.lector.seleccionar(resultado.inicio, resultado.fin)
            self.lector.registrar_en_historial(resultado.inicio)
            self.anunciar("%s %s" % (resultado.mensaje, self.lector.linea_actual().strip()))
            # Se apunta el resultado como el sitio por el que seguir leyendo: se
            # ha buscado justamente para leer desde ahí.
            self._seguir_leyendo_en = resultado.inicio
        else:
            self.sonidos.reproducir("limite")
            self.anunciar(resultado.mensaje)
        if self._dialogo_buscar is not None and self._dialogo_buscar.IsShown():
            self._dialogo_buscar.mostrar_estado(resultado.mensaje)
        return resultado.encontrado

    def reanudar_lectura_tras_buscar(self) -> None:
        """Sigue leyendo al cerrar la búsqueda, si se estaba escuchando.

        Desde el resultado cuando se ha encontrado algo, y desde donde se dejó
        cuando no: en los dos casos, quien escuchaba un libro sigue escuchándolo
        sin tener que volver a colocarse a mano.
        """
        if not self.lectura_voz.habia_lectura:
            self._seguir_leyendo_en = None
            return
        destino = self._seguir_leyendo_en
        self._seguir_leyendo_en = None
        if self.lectura_voz.seguir_desde(destino):
            self.anunciar(_("Sigo leyendo.") if destino is None
                          else _("Sigo leyendo desde aquí."))

    def repetir_busqueda(self, hacia_adelante: bool) -> None:
        """Repite la última búsqueda en la dirección indicada."""
        if self._ultima_busqueda is None:
            self.al_buscar(None)
            return
        termino, opciones = self._ultima_busqueda
        self.ejecutar_busqueda(termino, hacia_adelante, opciones)

    def contar_apariciones(self, termino: str, opciones: OpcionesBusqueda) -> int:
        """Cuenta cuántas veces aparece un término en el libro."""
        if self.buscador is None:
            return 0
        return self.buscador.contar(termino, opciones)

    # =======================================================================
    # Marcadores y notas
    # =======================================================================

    def _fragmento_actual(self) -> str:
        """Texto representativo de la posición actual, para los marcadores."""
        if self.documento is None:
            return ""
        seleccionado = self.lector.texto_seleccionado().strip()
        if seleccionado:
            return seleccionado[:LONGITUD_FRAGMENTO]
        return self.lector.linea_actual().strip()[:LONGITUD_FRAGMENTO]

    def _marcador_en(self, posicion: int) -> Marcador | None:
        """Devuelve el marcador que cubre una posición, si lo hay."""
        for marcador in self.marcadores:
            if marcador.inicio <= posicion <= max(marcador.fin, marcador.inicio):
                return marcador
            if self.documento is not None:
                if self.documento.linea_de(marcador.inicio) == self.documento.linea_de(posicion):
                    return marcador
        return None

    def al_poner_marcador(self, evento) -> None:
        """Pone o quita un marcador en la posición actual."""
        if self.documento is None:
            return
        inicio, fin = self.lector.seleccion()
        existente = self._marcador_en(inicio)
        if existente is not None and not existente.es_nota:
            self.marcadores.remove(existente)
            self.anunciar(_("Marcador eliminado."))
        else:
            self.marcadores.append(Marcador(inicio, fin, "", self._fragmento_actual()))
            self.sonidos.reproducir("marcador")
            self.anunciar(_("Marcador puesto en el %d por ciento.")
                          % self.documento.porcentaje_en(inicio))
        self.guardar_sesion()
        self.refrescar_arbol_propio()

    def al_poner_nota(self, evento) -> None:
        """Escribe o edita la nota de la posición actual."""
        if self.documento is None:
            return
        from nucleo import etiquetas as temas

        inicio, fin = self.lector.seleccion()
        existente = self._marcador_en(inicio)
        texto_previo = existente.nota if existente is not None else ""
        puestas = temas.de(existente) if existente is not None else []
        # Las etiquetas que ya se usan en **este** libro se ofrecen en el
        # desplegable. Es lo que evita acabar con «examen» y «exámenes» como
        # dos temas distintos, que es el fallo que hace inservible cualquier
        # sistema de etiquetas.
        with dialogos_contenido.DialogoNota(
            self, texto_previo, self._fragmento_actual(),
            puestas, temas.sugerencias(self.marcadores)
        ) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                return
            if not dialogo.nota:
                if existente is not None:
                    self.marcadores.remove(existente)
                    self.anunciar(_("Nota eliminada."))
                self.guardar_sesion()
                return
            if existente is not None:
                self.marcadores.remove(existente)
            self.marcadores.append(Marcador(inicio, fin, dialogo.nota,
                                            self._fragmento_actual(),
                                            etiquetas=dialogo.etiquetas))
            self.sonidos.reproducir("nota")
            if dialogo.etiquetas:
                self.anunciar(_("Nota guardada con las etiquetas %s.")
                              % temas.escribir(dialogo.etiquetas))
            else:
                self.anunciar(_("Nota guardada."))
        self.guardar_sesion()

    # -- resaltados ----------------------------------------------------------

    @property
    def resaltados(self) -> list:
        """Los pasajes resaltados del documento, en el orden en que aparecen."""
        return sorted((marcador for marcador in self.marcadores if marcador.es_resaltado),
                      key=lambda marcador: marcador.inicio)

    def al_biblioteca(self, evento) -> None:
        """Abre la biblioteca: todos los libros y la búsqueda en todos."""
        del evento
        from interfaz.dialogos.biblioteca import DialogoBiblioteca

        with DialogoBiblioteca(self) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK or dialogo.elegido is None:
                return
            ruta, posicion = dialogo.elegido
        # Se respeta lo que el usuario tenga puesto sobre pestañas: abrir desde
        # la biblioteca es abrir un documento como cualquier otro.
        self.abrir_libro(ruta, posicion_inicial=posicion)

    def al_citar(self, evento) -> None:
        """Copia lo seleccionado con su cita bibliográfica hecha.

        Sin selección no se cancela: se copia **la referencia del documento**,
        que es lo que hace falta para la bibliografía y lo que uno busca cuando
        no está citando ningún pasaje concreto.
        """
        del evento
        if self.documento is None:
            self.anunciar(_("Abre un documento para poder citarlo."), inmediato=True)
            return
        from interfaz.dialogos.citar import DialogoCitar

        inicio, fin = self.lector.seleccion()
        pasaje = self.lector.texto_seleccionado() if fin > inicio else ""
        posicion = inicio if fin > inicio else self.lector.posicion()
        with DialogoCitar(self, self.documento, pasaje, posicion,
                          self.configuracion) as dialogo:
            dialogo.ShowModal()

    def al_resaltar(self, evento) -> None:
        """Resalta el texto seleccionado, o quita el resaltado de aquí.

        Un resaltado es un **pasaje**, no un punto, así que hace falta una
        selección: sin ella no hay nada que resaltar y se dice, en vez de poner
        un resaltado vacío que después no diría nada al exportarlo.
        """
        if self.documento is None:
            return
        inicio, fin = self.lector.seleccion()
        existente = self._resaltado_en(self.lector.posicion())
        if fin <= inicio:
            if existente is not None:
                self.marcadores.remove(existente)
                self.guardar_sesion()
                self.sonidos.reproducir("limite")
                self.anunciar(_("Resaltado quitado."), inmediato=True)
                return
            self.sonidos.reproducir("limite")
            self.anunciar(_("Selecciona antes el texto que quieras resaltar."), inmediato=True)
            return
        if existente is not None:
            self.marcadores.remove(existente)
        fragmento = self.lector.texto_seleccionado().strip()
        self.marcadores.append(Marcador(inicio, fin, "", fragmento[:LONGITUD_RESALTADO], True))
        self.guardar_sesion()
        self.sonidos.reproducir("marcador")
        self.anunciar(_n("Resaltado, %d carácter.", "Resaltado, %d caracteres.",
                         fin - inicio) % (fin - inicio))

    def _resaltado_en(self, posicion: int):
        """Devuelve el resaltado que cubre una posición, si lo hay."""
        for marcador in self.marcadores:
            if marcador.es_resaltado and marcador.inicio <= posicion <= marcador.fin:
                return marcador
        return None

    def al_resaltados(self, evento) -> None:
        """Abre la lista de pasajes resaltados."""
        if self.documento is None:
            return
        resaltados = self.resaltados
        if not resaltados:
            self.sonidos.reproducir("limite")
            self.anunciar(_("Este documento no tiene ningún resaltado. Selecciona un "
                            "texto y pulsa Control+Alt+E para resaltarlo."), inmediato=True)
            return
        with dialogos_navegacion.DialogoResaltados(
            self, self.documento, resaltados, self.lector.posicion()
        ) as dialogo:
            resultado = dialogo.ShowModal()
            for eliminado in dialogo.eliminados:
                if eliminado in self.marcadores:
                    self.marcadores.remove(eliminado)
            if dialogo.eliminados:
                self.guardar_sesion()
            if dialogo.exportar:
                self.exportar_resaltados(dialogo.exportar, dialogo.con_notas,
                                         dialogo.etiqueta)
                return
            if resultado == wx.ID_OK and dialogo.posicion_elegida is not None:
                self.saltar_a(dialogo.posicion_elegida, self.lector.linea_actual().strip())

    def exportar_resaltados(self, formato: str = "txt", con_notas: bool = False,
                            etiqueta: str = "") -> None:
        """Guarda los pasajes resaltados en un archivo aparte.

        Se ofrecen tres formatos porque sirven para cosas distintas: texto
        plano para pegarlo donde sea, Markdown para una libreta de notas y HTML
        para abrirlo en el navegador o mandárselo a alguien.  Lo explica
        :mod:`nucleo.resaltados`.
        """
        from nucleo import resaltados as exportador

        if self.documento is None:
            return
        pasajes = exportador.pasajes_de(self.documento, self.marcadores, con_notas,
                                        etiqueta)
        if not pasajes:
            self.sonidos.reproducir("limite")
            self.anunciar(_("Este documento no tiene ningún resaltado."), inmediato=True)
            return
        nombres = exportador.nombres()
        if formato not in nombres:
            formato = "txt"
        rotulo, extension, filtro = nombres[formato]
        titulo = (self.documento.metadatos.titulo
                  or Path(self.ruta_actual or "documento").stem)
        propuesta = nombre_seguro("%s - resaltados" % titulo, 80) + extension
        with wx.FileDialog(self, _("Guardar los resaltados en %s") % rotulo,
                           defaultFile=propuesta, wildcard=filtro,
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                return
            destino = Path(dialogo.GetPath())
        referencia = ""
        if con_notas:
            from nucleo import citas

            referencia = citas.referencia(
                citas.desde_documento(self.documento, 0),
                str(self.configuracion.obtener("cita_estilo", "iso690")))
        try:
            exportador.exportar(pasajes, destino, formato, titulo,
                                self.documento.metadatos.autor,
                                self.documento.metadatos.idioma, referencia,
                                etiqueta)
        except (OSError, ValueError) as error:
            self.sonidos.reproducir("error")
            wx.MessageBox(_("No se han podido guardar los resaltados:\n%s") % error,
                          _("Exportar los resaltados"), wx.OK | wx.ICON_ERROR, self)
            return
        self.sonidos.reproducir("marcador")
        self.anunciar(_n("Se ha guardado %d resaltado en %s.",
                         "Se han guardado %d resaltados en %s.", len(pasajes))
                      % (len(pasajes), destino.name))


    def al_marcadores(self, evento) -> None:
        """Abre la lista de marcadores y notas."""
        if self.documento is None:
            return
        with dialogos_navegacion.DialogoMarcadores(
            self, self.documento, list(self.marcadores), self.lector.posicion(),
            self.configuracion
        ) as dialogo:
            resultado = dialogo.ShowModal()
            for eliminado in dialogo.eliminados:
                if eliminado in self.marcadores:
                    self.marcadores.remove(eliminado)
            if dialogo.eliminados:
                self.guardar_sesion()
            if resultado == wx.ID_OK and dialogo.posicion_elegida is not None:
                self.saltar_a(dialogo.posicion_elegida, self.lector.linea_actual().strip())

    # =======================================================================
    # Contenido: imágenes y tablas
    # =======================================================================

    # -- lo que el menú del árbol ejecuta ------------------------------------

    def _ir_y_hacer(self, marca, orden) -> None:
        """Salta a un elemento y ejecuta ahí una orden del texto.

        Es el patrón de todas las acciones del árbol. Saltar primero tiene dos
        motivos: se reutiliza tal cual la orden que ya existe —una sola forma de
        hacer cada cosa, que no puedan divergir— y el cursor acaba donde uno ha
        actuado.
        """
        if marca is None or self.documento is None:
            return
        self.lector.ir_a(int(marca.posicion), registrar=True)
        orden()

    def ver_imagen_del_arbol(self, marca) -> None:
        """Abre una imagen elegida en el árbol."""
        self._ir_y_hacer(marca, lambda: self.mostrar_imagen(marca))

    def describir_del_arbol(self, marca) -> None:
        """Describe con IA una imagen elegida en el árbol."""
        self._ir_y_hacer(marca, lambda: self.al_describir_imagen(None))

    def ver_tabla_del_arbol(self, marca) -> None:
        """Abre para recorrerla una tabla elegida en el árbol."""
        def abrir():
            with dialogos_contenido.DialogoTabla(
                    self, marca, self.configuracion) as dialogo:
                dialogo.ShowModal()

        self._ir_y_hacer(marca, abrir)

    def seguir_enlace_del_arbol(self, marca) -> None:
        """Sigue un enlace elegido en el árbol."""
        self._ir_y_hacer(marca, lambda: self._seguir_enlace(marca))

    def describir_todo_del_arbol(self) -> None:
        """Describe de una vez las imágenes que falten, desde el árbol."""
        self.al_describir_todo(None)

    def leer_desde(self, posicion: int) -> None:
        """Empieza a leer en voz alta desde ese punto."""
        self.lector.ir_a(int(posicion), registrar=True)
        self.lectura_voz.empezar(int(posicion))

    def poner_marcador_en(self, posicion: int) -> None:
        """Pone un marcador en ese punto, desde el árbol."""
        self.lector.ir_a(int(posicion), registrar=True)
        self.al_poner_marcador(None)

    def editar_nota_del_arbol(self, marcador) -> None:
        """Escribe o cambia la nota de un marcador elegido en el árbol."""
        if self.documento is None:
            return
        self.lector.ir_a(int(marcador.inicio), registrar=True)
        self.al_poner_nota(None)
        self.refrescar_arbol_propio()

    def quitar_marcador_del_arbol(self, marcador) -> None:
        """Quita un marcador, una nota o un resaltado desde el árbol.

        Se pregunta cuando lleva algo escrito.  Un marcador suelto se vuelve a
        poner en un segundo; una nota de tres párrafos, no.
        """
        if marcador not in self.marcadores:
            return
        if (marcador.nota or "").strip():
            respuesta = wx.MessageBox(
                _("¿Quitar esta nota?\n\n%s") % marcador.nota.strip()[:300],
                _("Quitar la nota"), wx.YES_NO | wx.ICON_QUESTION, self)
            if respuesta != wx.YES:
                return
        self.marcadores.remove(marcador)
        self.guardar_sesion()
        self.refrescar_arbol_propio()
        self.anunciar(_("Quitado."), inmediato=True)

    def quitar_todos_del_arbol(self, clase: str, cuales: list) -> None:
        """Quita de una vez todos los de una rama, preguntando antes.

        Preguntar aquí no es por costumbre: es la única orden del menú que
        borra varias cosas a la vez y no hay forma de deshacerla.
        """
        cuales = [uno for uno in cuales if uno in self.marcadores]
        if not cuales:
            self.sonidos.reproducir("limite")
            self.anunciar(_("No hay ninguno que quitar."), inmediato=True)
            return
        nombres = {"marcadores": _("marcadores"), "notas": _("notas"),
                   "resaltados": _("resaltados")}
        pregunta = _("¿Quitar los %(cuantos)d %(que)s de este documento?\n\n"
                     "No se puede deshacer.") % {
            "cuantos": len(cuales), "que": nombres.get(clase, clase)}
        if wx.MessageBox(pregunta, _("Quitar todos"),
                         wx.YES_NO | wx.ICON_WARNING, self) != wx.YES:
            return
        for uno in cuales:
            self.marcadores.remove(uno)
        self.guardar_sesion()
        self.refrescar_arbol_propio()
        self.anunciar(_("Quitados %d.") % len(cuales), inmediato=True)

    def abrir_marcadores_del_arbol(self) -> None:
        """Abre la lista de marcadores y notas desde el árbol."""
        self.al_marcadores(None)
        self.refrescar_arbol_propio()

    def abrir_resaltados_del_arbol(self) -> None:
        """Abre la lista de pasajes resaltados desde el árbol."""
        self.al_resaltados(None)
        self.refrescar_arbol_propio()

    def _huella_de_marcadores(self) -> tuple:
        """Con qué se sabe si los marcadores han cambiado.

        Basta con lo que se ve en el árbol: dónde están, qué ponen y de qué
        clase son.  Comparar los objetos enteros costaría más y no distinguiría
        nada más.
        """
        return tuple((uno.inicio, uno.fin, uno.nota, bool(uno.resaltado))
                     for uno in getattr(self, "marcadores", ()))

    def refrescar_arbol_propio(self, forzar: bool = False) -> None:
        """Rehace en el árbol las ramas de marcadores, notas y resaltados.

        Solo si de verdad han cambiado: esto se consulta cada vez que se guarda
        la sesión, y la sesión se guarda también al pasar de página.

        Si el árbol no está a la vista tampoco se hace nada, porque se construye
        entero al enseñarlo.
        """
        panel = getattr(self, "panel_arbol", None)
        if panel is None or not panel.IsShown():
            return
        huella = self._huella_de_marcadores()
        if not forzar and huella == getattr(self, "_huella_arbol", None):
            return
        self._huella_arbol = huella
        try:
            panel.refrescar_propias()
        except Exception as error:      # pragma: no cover - árbol cerrándose
            log.debug("No se ha podido refrescar el árbol: %s", error)

    def copiar_al_portapapeles(self, texto: str) -> None:
        """Deja un texto en el portapapeles y lo dice.

        Se dice porque copiar no hace ruido ni cambia nada de lo que se ve: sin
        el aviso no hay forma de saber si ha pasado algo.
        """
        texto = (texto or "").strip()
        if not texto:
            self.sonidos.reproducir("limite")
            self.anunciar(_("No hay nada que copiar."), inmediato=True)
            return
        if not wx.TheClipboard.Open():
            self.anunciar(_("No se ha podido abrir el portapapeles."), inmediato=True)
            return
        try:
            wx.TheClipboard.SetData(wx.TextDataObject(texto))
        finally:
            wx.TheClipboard.Close()
        cuantas = texto.count("\n") + 1
        self.anunciar(
            _("Copiado: %d líneas.") % cuantas if cuantas > 1 else _("Copiado."),
            inmediato=True)

    def guardar_lista_del_arbol(self, rama: str, texto: str) -> None:
        """Guarda en un archivo la lista de una rama del árbol."""
        texto = (texto or "").strip()
        if not texto:
            self.sonidos.reproducir("limite")
            self.anunciar(_("No hay nada que guardar."), inmediato=True)
            return
        propuesto = "%s - %s.txt" % (
            (self.documento.metadatos.titulo if self.documento else _("Documento")),
            rama)
        for malo in '\\/:*?"<>|':
            propuesto = propuesto.replace(malo, "-")
        with wx.FileDialog(self, _("Guardar la lista"), defaultFile=propuesto,
                           wildcard=_("Archivo de texto (*.txt)|*.txt"),
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                return
            ruta = dialogo.GetPath()
        try:
            Path(ruta).write_text(texto, encoding="utf-8")
        except OSError as error:
            self.sonidos.reproducir("error")
            wx.MessageBox(_("No se ha podido guardar: %s") % error,
                          _("Guardar la lista"), wx.OK | wx.ICON_ERROR, self)
            return
        self.anunciar(_("Lista guardada en %s") % Path(ruta).name, inmediato=True)

    def _marca_en_linea(self, tipos: tuple[TipoMarca, ...]):
        """La marca de esos tipos que hay donde está el cursor.

        Devuelve solo la marca, para quien no necesite saber si había más.
        """
        marca, _cual, _cuantas = self._marca_en_el_cursor(tipos)
        return marca

    def _marca_en_el_cursor(self, tipos: tuple[TipoMarca, ...]):
        """La marca del cursor, cuál es de las de su línea y cuántas hay.

        Con una sola por línea da igual cómo se elija.  Con varias no: una
        página de cómic escaneada puede traer cuatro imágenes seguidas en la
        misma línea, y coger siempre la primera deja las otras tres
        inalcanzables.

        Se elige la que **empieza en el cursor o justo antes**, que es donde
        deja el cursor la navegación al saltar de una a otra.  Es el mismo
        criterio que ya usaban los enlaces.

        Devuelve ``(marca, cual, cuantas)``, con ``cual`` contando desde uno, o
        ``(None, 0, 0)`` si no hay ninguna.
        """
        if self.documento is None:
            return None, 0, 0
        cursor = self.lector.posicion()
        elementos = [marca for marca
                     in navegacion.elementos_en_linea(self.documento, cursor)
                     if marca.tipo in tipos]
        if not elementos:
            return None, 0, 0
        elegida, cual = elementos[0], 1
        for numero, marca in enumerate(elementos, start=1):
            if marca.posicion <= cursor:
                elegida, cual = marca, numero
            else:
                break
        return elegida, cual, len(elementos)

    @staticmethod
    def _cual_de_la_linea(cual: int, cuantas: int) -> str:
        """Un «(imagen 3 de 4 de esta línea)» cuando hace falta decirlo.

        Solo cuando hay más de una: decir «imagen 1 de 1» sería ruido en el
        noventa y nueve por ciento de los libros.
        """
        if cuantas <= 1:
            return ""
        return _(" (imagen %(cual)d de %(cuantas)d de esta línea)") % {
            "cual": cual, "cuantas": cuantas}

    def al_ver_imagen(self, evento) -> None:
        """Muestra la imagen que hay donde está el cursor."""
        if self.documento is None:
            return
        marca, cual, cuantas = self._marca_en_el_cursor(
            (TipoMarca.IMAGEN, TipoMarca.FIGURA))
        if marca is None:
            self.sonidos.reproducir("limite")
            self.anunciar(_("No hay ninguna imagen en esta línea. "
                          "Usa la tecla G para ir a la siguiente imagen."))
            return
        aviso = self._cual_de_la_linea(cual, cuantas)
        if aviso:
            self.anunciar(_("Imagen %(cual)d de %(cuantas)d de esta línea. Con "
                            "G vas a la siguiente.")
                          % {"cual": cual, "cuantas": cuantas})
        self.mostrar_imagen(marca)

    def mostrar_imagen(self, marca) -> None:
        """Abre el visor de una imagen del libro.

        Es el **único** sitio por el que se abre, tanto desde el menú como con
        Intro sobre la ilustración.  Antes había dos llamadas y una de ellas no
        pasaba las descripciones guardadas, de modo que al entrar con Intro no
        se veía la descripción hecha con IA ni se podía pedir otra.
        """
        with dialogos_contenido.DialogoImagen(
                self, self.ruta_actual, marca, self.configuracion,
                self.descripciones, self._contexto_de_imagen(marca)) as dialogo:
            dialogo.ShowModal()

    def _contexto_de_imagen(self, marca) -> str:
        """Redacta los datos del libro que ayudan a la IA a describir mejor.

        Saber que el libro es un manual de botánica, o una novela del XIX,
        cambia por completo qué destaca la IA de una misma lámina.  Se le pasa
        también la descripción que trae el EPUB, que suele ser escueta pero
        acierta con el asunto.
        """
        if self.documento is None:
            return ""
        partes = []
        metadatos = self.documento.metadatos
        if metadatos.titulo:
            partes.append(_("Título del documento: %s") % metadatos.titulo)
        if metadatos.autor:
            partes.append("Autor: %s" % metadatos.autor)
        original = (getattr(marca, "texto", "") or "").strip()
        if original:
            partes.append(_("Descripción que trae el propio documento: %s") % original)
        referencia = getattr(marca, "referencia", "")
        if referencia:
            partes.append(_("Archivo de la imagen dentro del documento: %s") % referencia)
        return "\n".join(partes)

    def datos_de_imagen(self, marca) -> bytes:
        """Extrae del documento los bytes de una imagen.

        En un EPUB o un DOCX la imagen es un archivo dentro del documento y se
        saca tal cual.  En un PDF no lo es: una figura casi nunca es «una»
        imagen, sino un gráfico hecho de decenas de trazos, así que lo que se
        guardó al analizar fue **el rectángulo que ocupa** y aquí se rasteriza
        ese trozo de la página.  El analizador de cada formato resuelve lo suyo
        y quien llama no tiene que saber de cuál se trata.

        Devuelve una cadena de bytes vacía si no se puede, en vez de fallar:
        quien llama ya avisa con un mensaje claro.
        """
        referencia = getattr(marca, "referencia", "")
        if not referencia or not self.ruta_actual:
            return b""
        try:
            return formatos.extraer_recurso(self.ruta_actual, referencia) or b""
        except Exception as error:
            registrar_excepcion(log, "No se ha podido extraer la imagen %s" % referencia, error)
            return b""

    def al_describir_imagen(self, evento) -> None:
        """Describe con IA la imagen que hay en la línea actual.

        Es la orden de la tecla rápida: abre el diálogo y **ya lanza la
        petición**, de modo que con una sola pulsación se obtiene la
        descripción.  Si ya había una guardada se muestra esa, sin gastar otra
        petición; desde el propio diálogo se puede pedir una nueva.
        """
        if self.documento is None:
            return
        marca, cual, cuantas = self._marca_en_el_cursor(
            (TipoMarca.IMAGEN, TipoMarca.FIGURA))
        if marca is None:
            self.sonidos.reproducir("limite")
            self.anunciar(_("No hay ninguna imagen en esta línea. "
                          "Usa la tecla G para ir a la siguiente imagen."), inmediato=True)
            return
        aviso = self._cual_de_la_linea(cual, cuantas)
        if aviso:
            # Se dice antes de abrir: dentro del diálogo ya no hay forma de
            # saber que había otras tres al lado.
            self.anunciar(_("Se describe la imagen %(cual)d de %(cuantas)d de "
                            "esta línea. Con G vas a la siguiente.")
                          % {"cual": cual, "cuantas": cuantas}, inmediato=True)
        from nucleo.ia.servicio import Servicio

        guardada = self.descripciones.obtener(getattr(marca, "referencia", ""))
        if guardada is None:
            motivo = Servicio(self.configuracion).motivo_no_disponible()
            if motivo:
                self.sonidos.reproducir("limite")
                self.anunciar(motivo)
                wx.MessageBox(motivo, _("Descripción con inteligencia artificial"),
                              wx.OK | wx.ICON_INFORMATION, self)
                return
        datos = self.datos_de_imagen(marca)
        if not datos and guardada is None:
            self.sonidos.reproducir("error")
            self.anunciar(_("No se ha podido extraer esta imagen del documento."), inmediato=True)
            return
        from interfaz.dialogos.ia import DialogoDescripcion

        with DialogoDescripcion(self, datos, marca, self.configuracion, self.descripciones,
                                self._contexto_de_imagen(marca), guardada,
                                al_vuelo=True) as dialogo:
            dialogo.ShowModal()

    def al_corregir_elemento(self, evento) -> None:
        """Dice qué es de verdad la línea del cursor, y lo recuerda.

        Solo tiene sentido en un PDF, que es el único formato del que hay que
        **deducir** la estructura: en un EPUB o en un DOCX el archivo ya dice
        qué es cada cosa y corregirlo a mano sería enmendarle la plana al autor.

        Al terminar se vuelve a analizar el documento sin caché.  Hay que
        forzarlo porque lo que ha cambiado no es el archivo —su fecha y su
        tamaño son los de antes, así que la caché seguiría dándose por buena—
        sino lo que el usuario acaba de decir que era ese elemento.
        """
        if self.documento is None:
            return
        huella = getattr(self.documento.metadatos, "huella", "")
        if not huella:
            self.sonidos.reproducir("limite")
            self.anunciar(_("Solo se pueden corregir los elementos de un PDF: los demás "
                            "formatos ya dicen por sí mismos qué es cada cosa."),
                          inmediato=True)
            return
        texto = self.lector.linea_actual().strip()
        if not texto:
            self.sonidos.reproducir("limite")
            self.anunciar(_("No hay nada que corregir en esta línea."), inmediato=True)
            return
        from interfaz.dialogos.corregir import DialogoCorregir
        from nucleo.correcciones import Correcciones

        pagina = self.documento.indice_de_pagina(self.lector.posicion()) + 1
        correcciones = Correcciones.cargar(huella)
        with DialogoCorregir(self, texto, max(1, pagina), correcciones) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK or not dialogo.aplicar():
                return
        if not correcciones.guardar():
            self.sonidos.reproducir("error")
            self.anunciar(_("No se ha podido guardar la corrección."), inmediato=True)
            return
        self.anunciar(_("Corrección guardada. Volviendo a leer el documento."))
        self.abrir_libro(str(self.sesion.ruta), en_pestana_nueva=False, releer=True)

    def al_revisar_estructura(self, evento) -> None:
        """Pide a la IA que revise la estructura deducida de un PDF.

        Como la corrección a mano, solo tiene sentido donde la estructura se
        **deduce**: en un EPUB o en un DOCX el archivo ya dice qué es cada cosa.
        """
        del evento
        if self.documento is None:
            return
        huella = getattr(self.documento.metadatos, "huella", "")
        if not huella:
            self.sonidos.reproducir("limite")
            self.anunciar(_("Solo tiene sentido revisar la estructura de un PDF: los "
                            "demás formatos ya dicen por sí mismos qué es cada cosa."),
                          inmediato=True)
            return
        from interfaz.dialogos.estructura import DialogoEstructura
        from nucleo.correcciones import Correcciones

        correcciones = Correcciones.cargar(huella)
        with DialogoEstructura(self, self.documento, correcciones,
                               self.configuracion) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK or not dialogo.aplicadas:
                return
            cuantas = dialogo.aplicadas
        self.anunciar(_n("Se ha aplicado %d corrección. Volviendo a leer el documento.",
                         "Se han aplicado %d correcciones. Volviendo a leer el documento.",
                         cuantas) % cuantas)
        self.abrir_libro(str(self.sesion.ruta), en_pestana_nueva=False, releer=True)

    def al_volver_a_analizar(self, evento) -> None:
        """Convierte otra vez el documento, sin usar lo que hubiera guardado.

        Analizar un libro cuesta tiempo —y un PDF escaneado, minutos— así que
        el resultado se guarda y la segunda vez que se abre aparece al
        instante.  Lo guardado deja de valer solo cuando cambia el archivo o
        cuando cambia algo de lo que forma parte de su firma.

        Y hay ajustes que **cambian lo que sale del archivo sin formar parte de
        esa firma**: con qué se reconocen las páginas escaneadas, cuántas se
        reconocen como mucho, con qué idiomas.  El archivo es el mismo, así que
        lo guardado sigue considerándose bueno: quien abrió un PDF escaneado
        con el reconocimiento apagado, o con el tope en cien páginas, lo seguía
        abriendo igual después de arreglar los ajustes.  La única salida era ir
        a «Datos guardados» y borrar los del documento, que además se lleva por
        delante los marcadores y las notas.

        Esto es esa salida sin el destrozo: se vuelve a convertir el archivo
        desde cero, se guarda el resultado nuevo encima del viejo y el cursor
        se queda donde estaba.  Lo anotado sobre el documento no se toca.
        """
        del evento
        ruta = self.ruta_actual
        if self.documento is None or not ruta:
            self.sonidos.reproducir("limite")
            self.anunciar(_("No hay ningún documento que volver a analizar."),
                          inmediato=True)
            return
        self.anunciar(_("Volviendo a analizar el documento."), inmediato=True)
        self.abrir_libro(ruta, en_pestana_nueva=False, releer=True,
                         posicion_inicial=self.lector.posicion())

    def imagenes_del_libro(self) -> list:
        """Todas las imágenes del libro, sin repetir y en orden de aparición.

        Una misma ilustración puede salir varias veces —un logotipo al empezar
        cada capítulo, por ejemplo— y describirla una vez por aparición sería
        tirar el tiempo y la cuota: se agrupan por archivo, que es la clave con
        la que se guardan las descripciones.
        """
        if self.documento is None:
            return []
        vistas = set()
        imagenes = []
        for tipo in (TipoMarca.IMAGEN, TipoMarca.FIGURA):
            for marca in self.documento.marcas.grupo(tipo).marcas:
                referencia = marca.referencia or ""
                if not referencia or referencia in vistas:
                    continue
                vistas.add(referencia)
                imagenes.append(marca)
        imagenes.sort(key=lambda marca: marca.posicion)
        return imagenes

    def al_describir_todo(self, evento) -> None:
        """Describe de una vez todas las imágenes del libro que falten."""
        if self.documento is None:
            return
        imagenes = self.imagenes_del_libro()
        if not imagenes:
            self.sonidos.reproducir("limite")
            self.anunciar(_("Este documento no tiene ninguna imagen que describir."))
            wx.MessageBox(_("Este documento no tiene ninguna imagen que describir."),
                          _("Describir todas las imágenes"),
                          wx.OK | wx.ICON_INFORMATION, self)
            return
        from nucleo.ia.servicio import Servicio

        motivo = Servicio(self.configuracion).motivo_no_disponible()
        if motivo:
            self.sonidos.reproducir("limite")
            wx.MessageBox(motivo, _("Describir todas las imágenes"),
                          wx.OK | wx.ICON_INFORMATION, self)
            return
        from interfaz.dialogos.ia import DialogoDescribirTodo

        with DialogoDescribirTodo(self, imagenes, self.configuracion, self.descripciones,
                                  self.datos_de_imagen, self._contexto_de_imagen) as dialogo:
            dialogo.ShowModal()
            hechas = dialogo.hechas
        if hechas:
            self.anunciar(_n("Se ha descrito %d imagen del documento.",
                             "Se han descrito %d imágenes del documento.", hechas) % hechas)

    def al_ver_tabla(self, evento) -> None:
        """Muestra la tabla que hay en la línea actual."""
        if self.documento is None:
            return
        marca = self._marca_en_linea((TipoMarca.TABLA,))
        if marca is None:
            contenedor = self.documento.marcas.contenedor_en(self.lector.posicion())
            if contenedor is not None and contenedor.tipo is TipoMarca.TABLA:
                marca = contenedor
        if marca is None:
            self.sonidos.reproducir("limite")
            self.anunciar(_("No hay ninguna tabla aquí. Usa la tecla T para ir a la siguiente."))
            return
        with dialogos_contenido.DialogoTabla(self, marca, self.configuracion) as dialogo:
            dialogo.ShowModal()

    def elemento_estructurado_en_el_cursor(self):
        """Busca la tabla, la lista, la cita o la fórmula que hay en el cursor.

        Se mira primero lo que hay en la propia línea (una tabla en modo
        marcador cabe entera en una línea) y después los contenedores que
        abarcan la posición, que es como se encuentra la lista o la tabla
        dentro de la que se está leyendo.
        """
        if self.documento is None:
            return None
        posicion = self.lector.posicion()
        for marca in navegacion.elementos_en_linea(self.documento, posicion):
            if html_elementos.se_puede_convertir(marca, self.documento):
                return marca
        contenedor = self.documento.marcas.contenedor_en(posicion)
        if html_elementos.se_puede_convertir(contenedor, self.documento):
            return contenedor
        # Las citas no están entre los contenedores indexados, así que se
        # buscan aparte: son pocas y la lista está ordenada por posición.
        for marca in self.documento.marcas.grupo(TipoMarca.CITA).marcas:
            if marca.posicion <= posicion < marca.posicion + max(marca.longitud, 1):
                return marca
        return None

    def al_ver_html(self, evento) -> None:
        """Muestra en el visor HTML el elemento donde está el cursor."""
        if self.documento is None:
            return
        marca = self.elemento_estructurado_en_el_cursor()
        if marca is None:
            self.sonidos.reproducir("limite")
            self.anunciar(_("Aquí no hay ninguna tabla, lista, cita, fórmula, bloque de "
                          "código ni imagen descrita que ver como HTML. Usa la tecla T, L, "
                          "Q, E, X o I para ir al siguiente."),
                          inmediato=True)
            return
        visor_html.mostrar(self, self.documento, marca)

    def activar_elemento(self) -> bool:
        """Acciona el elemento que hay bajo el cursor (Intro).

        Sigue un enlace, abre una imagen o muestra una tabla, según lo que
        haya en la línea.  Devuelve ``True`` si ha hecho algo.
        """
        if self.documento is None:
            return False
        posicion = self.lector.posicion()
        elementos = navegacion.elementos_en_linea(self.documento, posicion)

        # Un enlace solo se activa si el cursor está realmente dentro de él.
        for marca in elementos:
            if marca.tipo is TipoMarca.ENLACE:
                dentro = marca.posicion <= posicion < marca.posicion + max(marca.longitud, 1)
                if dentro or len([m for m in elementos if m.tipo is TipoMarca.ENLACE]) == 1:
                    return self._seguir_enlace(marca)
        # La imagen que se abre es la del cursor, no la primera de la línea:
        # con varias seguidas, lo contrario deja las demás inalcanzables.
        imagenes = [marca for marca in elementos
                    if marca.tipo in (TipoMarca.IMAGEN, TipoMarca.FIGURA)]
        if imagenes:
            alcanzadas = [marca for marca in imagenes if marca.posicion <= posicion]
            self.mostrar_imagen((alcanzadas or imagenes)[-1 if alcanzadas else 0])
            return True
        for marca in elementos:
            if marca.tipo is TipoMarca.TABLA:
                with dialogos_contenido.DialogoTabla(self, marca, self.configuracion) as dialogo:
                    dialogo.ShowModal()
                return True
        return False

    def _seguir_enlace(self, marca) -> bool:
        """Sigue un enlace interno del libro, o avisa si es externo."""
        from formatos.epub import es_url_externa

        destino = marca.referencia or ""
        if not destino:
            return False
        if es_url_externa(destino):
            respuesta = wx.MessageBox(
                _("Este enlace lleva a una página de Internet:\n\n%s\n\n¿Quieres abrirlo en el "
                "navegador?") % destino,
                _("Enlace externo"), wx.YES_NO | wx.ICON_QUESTION, self,
            )
            if respuesta == wx.YES:
                wx.LaunchDefaultBrowser(destino)
            return True
        posicion = self.documento.resolver_referencia(destino)
        if posicion < 0:
            self.sonidos.reproducir("limite")
            self.anunciar(_("El destino de este enlace no está en el documento."))
            return True
        self.sonidos.reproducir("enlace")
        self.saltar_a(posicion, "Enlace seguido. " + self.documento.texto_de_linea(posicion).strip())
        return True

    # =======================================================================
    # Otras órdenes
    # =======================================================================

    def al_cuanto_queda(self, evento) -> None:
        """Dice cuánto falta para acabar el capítulo y el documento.

        Se dice y no se enseña en una ventana: es un dato que se consulta a
        media lectura y para el que abrir un diálogo sería más caro que el
        dato.  Va también al portapapeles del anuncio normal, de modo que el
        lector de pantalla lo repita si no se ha cogido a la primera.
        """
        del evento
        if self.documento is None:
            self.anunciar(_("Abre un documento para saber cuánto queda."), inmediato=True)
            return
        self.anunciar(estadisticas.cuanto_queda(
            self.cronometro, self.documento, self.lector.posicion()), inmediato=True)

    def al_informacion(self, evento) -> None:
        """Muestra los datos y las estadísticas del libro."""
        if self.documento is None:
            return
        wx.BeginBusyCursor()
        try:
            dialogo = dialogos_contenido.DialogoInformacion(
                self, self.documento, self.cronometro, self.lector.posicion())
        finally:
            wx.EndBusyCursor()
        with dialogo:
            dialogo.ShowModal()

    def al_exportar(self, formato: str = "txt") -> None:
        """Guarda el documento en el formato pedido.

        Los cuatro formatos conservan la estructura —encabezados, listas— y no
        solo el texto: es lo que permite seguir navegando el documento después
        de exportarlo.
        """
        from nucleo import exportar

        if self.documento is None:
            return
        nombres = exportar.nombres()
        if formato not in nombres:
            formato = "txt"
        rotulo, extension, filtro = nombres[formato]
        base = self.documento.metadatos.titulo or Path(self.ruta_actual).stem
        nombre = "".join(c for c in base if c not in '\\/:*?"<>|') + extension
        with wx.FileDialog(self, _("Exportar a %s") % rotulo, defaultFile=nombre,
                           wildcard=filtro,
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                return
            destino = dialogo.GetPath()
        # El braille contraído solo lo miran el BRF y el PEF; para los demás
        # formatos el ajuste no significa nada.
        contraido = bool(self.configuracion.obtener("braille_contraido", False))
        ok, resultado = ejecutar_esperando(
            self, _("Exportando a %s...") % rotulo,
            lambda: exportar.exportar(self.documento, destino, formato,
                                      contraido))
        if not ok:
            wx.MessageBox(_("No se ha podido exportar:\n%s") % resultado,
                          _("Exportar"), wx.OK | wx.ICON_ERROR, self)
            return
        if formato == "epub" and self.configuracion.obtener("revisar_epub", True):
            self._revisar_epub(destino)
            return
        self.anunciar(_("Documento exportado correctamente a %s.") % rotulo)

    def _revisar_epub(self, destino) -> None:
        """Pasa el EPUB recién escrito por las comprobaciones de accesibilidad.

        Había informe para lo que se **lee** y no lo había para lo que se
        **escribe**.  Que el programa compruebe lo que él mismo acaba de
        exportar es lo mínimo, y además es donde se cazan los fallos que solo
        aparecen con documentos raros.
        """
        from nucleo import revision_epub
        from formatos.pdf_hallazgos import Severidad

        ok, hallazgos = ejecutar_esperando(
            self, _("Comprobando el libro exportado..."),
            lambda: revision_epub.revisar(destino))
        if not ok:
            # Que falle la comprobación no invalida la exportación: el libro
            # está escrito y se dice.
            log.warning("No se ha podido revisar el EPUB exportado: %s", hallazgos)
            self.anunciar(_("Documento exportado correctamente a EPUB."))
            return
        texto = revision_epub.redactar(hallazgos)
        if hallazgos.peor() >= Severidad.ERROR:
            # Con errores de verdad se enseña una ventana: es lo que hay que
            # leer con calma antes de mandarle el libro a nadie.
            self.sonidos.reproducir("error")
            wx.MessageBox(texto, _("Revisión del libro exportado"),
                          wx.OK | wx.ICON_WARNING, self)
            return
        self.anunciar(_("Documento exportado a EPUB. %s") % texto)

    def al_exportar_daisy(self, evento) -> None:
        """Escribe el documento como un libro DAISY 3 en una carpeta."""
        del evento
        if self.documento is None:
            return
        from interfaz.dialogos.daisy_exportar import DialogoExportarDaisy

        with DialogoExportarDaisy(self) as dialogo:
            dialogo.ShowModal()

    def al_ajuste_linea(self, evento) -> None:
        """Activa o desactiva el ajuste de línea en todos los documentos abiertos."""
        activo = self.lector.alternar_ajuste_de_linea()
        # El ajuste es del programa, no de una pestaña: si solo cambiara la de
        # delante, al pasar a otra el texto aparecería con el ajuste contrario
        # y la casilla del menú diría lo que no es.
        for sesion in self.pestanas.sesiones:
            if sesion.panel is not self.lector:
                sesion.panel.aplicar_ajuste_de_linea()
        self.opcion_ajuste.Check(activo)
        self.configuracion.guardar()
        self.anunciar(_("Ajuste de línea activado.") if activo else _("Ajuste de línea desactivado."))

    def al_renglon_frase(self, evento) -> None:
        """Empieza o deja de empezar cada frase en un renglón nuevo.

        Como el ajuste de línea, es del programa y no de una pestaña: se aplica
        a todos los documentos abiertos para que al cambiar de pestaña el texto
        no aparezca del otro modo y la casilla del menú diga lo que no es.
        """
        del evento
        activo = not bool(self.configuracion.obtener("renglon_por_frase", False))
        self.configuracion.establecer("renglon_por_frase", activo)
        actual = self.pestanas.actual
        for sesion in self.pestanas.sesiones:
            sesion.panel.aplicar_renglones(mover_foco=sesion is actual)
        self.opcion_renglon_frase.Check(activo)
        self.configuracion.guardar()
        self.anunciar(_("Cada frase en un renglón.") if activo
                      else _("Cada párrafo en un renglón."))

    def al_alternar_sonidos(self, evento) -> None:
        """Activa o desactiva los sonidos de navegación."""
        activo = not self.sonidos.activado
        self.sonidos.activado = activo
        self.opcion_sonidos.Check(activo)
        self.configuracion.establecer("sonidos_activados", activo)
        self.configuracion.guardar()
        if activo:
            self.sonidos.reproducir("marcador")
        self.anunciar("Sonidos activados." if activo else "Sonidos desactivados.")

    #: Lo que se apaga en el modo lectura, con el valor que toma cada cosa.
    #: Son los cuatro ajustes que **añaden algo alrededor del texto**: los
    #: pitidos, el aviso de los elementos, la barra de estado y el árbol.  Cada
    #: uno por separado es útil; los cuatro a la vez, leyendo una novela de un
    #: tirón, son ruido.
    APAGADO_PARA_LEER = {
        "sonidos_activados": False,
        "avisar_elementos": "ninguno",
        "barra_recuentos": False,
        "mostrar_arbol": False,
    }

    def al_modo_lectura(self, evento) -> None:
        """Apaga —o vuelve a encender— todo lo que acompaña a la lectura.

        Lo que había antes se guarda tal cual, así que al salir del modo se
        recupera exactamente lo que el usuario tuviera puesto, no lo que venga
        de fábrica.  Ese detalle es lo que hace que se pueda entrar y salir sin
        miedo a perder los ajustes de uno.
        """
        del evento
        activo = not bool(self.configuracion.obtener("modo_lectura", False))
        if activo:
            anterior = {clave: self.configuracion.obtener(clave)
                        for clave in self.APAGADO_PARA_LEER}
            self.configuracion.establecer("modo_lectura_anterior", anterior)
            for clave, valor in self.APAGADO_PARA_LEER.items():
                self.configuracion.establecer(clave, valor)
        else:
            anterior = self.configuracion.obtener("modo_lectura_anterior", {}) or {}
            for clave in self.APAGADO_PARA_LEER:
                if clave in anterior:
                    self.configuracion.establecer(clave, anterior[clave])
        self.configuracion.establecer("modo_lectura", activo)
        self.configuracion.guardar()
        self.opcion_modo_lectura.Check(activo)
        self.aplicar_preferencias()
        self.anunciar(_("Modo lectura activado.") if activo
                      else _("Modo lectura desactivado."))

    def al_perfiles(self, evento) -> None:
        """Abre la ventana de perfiles de lectura."""
        with dialogos_perfiles.DialogoPerfiles(self) as dialogo:
            dialogo.ShowModal()

    def aplicar_preferencias(self, reabrir: bool = False, avisar_teclas: bool = False) -> None:
        """Lleva a la ventana los ajustes que haya en la configuración.

        Lo usan tanto el diálogo de opciones como el de perfiles: los dos
        cambian los mismos ajustes, y lo que hay que hacer después de cambiarlos
        es exactamente lo mismo.

        :param reabrir: Si alguno de los ajustes cambiados obliga a volver a
                        convertir el documento, en cuyo caso se pregunta.
        :param avisar_teclas: Si hay que avisar de las teclas globales que no
                              haya concedido Windows.
        """
        self.opcion_sonidos.Check(bool(self.configuracion.obtener("sonidos_activados")))
        # La apariencia y el ajuste de línea son de todos los paneles abiertos,
        # no solo del que esté delante: si no, cambiar el tamaño de la letra
        # dejaría las otras pestañas como estaban hasta volver a abrirlas.
        # El ajuste ya viene decidido y guardado por el diálogo: aquí solo hay
        # que **aplicarlo** a cada panel.  Invertirlo una vez por panel, que es
        # lo que se hacía, lo dejaba como estaba cuando había un solo documento
        # abierto, y por eso la casilla aparecía siempre desmarcada.
        cambiar_ajuste = (bool(self.configuracion.obtener("ajuste_de_linea"))
                          != bool(self.opcion_ajuste.IsChecked()))
        actual = self.pestanas.actual
        for sesion in self.pestanas.sesiones:
            if cambiar_ajuste:
                # Solo el documento que está delante recupera el foco: dárselo
                # a los de detrás dejaría el teclado escribiendo en uno que no
                # se ve.
                sesion.panel.aplicar_ajuste_de_linea(mover_foco=sesion is actual)
            sesion.panel.refrescar_apariencia()
            # La pantalla de bienvenida se puede haber encendido o apagado, y
            # el cambio tiene que verse en cuanto se acepta: quien la apaga
            # está mirando justo eso.  Solo se rehace donde no hay libro, que
            # es lo único que enseña la presentación.
            if sesion.panel.documento is None:
                sesion.panel.mostrar_presentacion()
        if cambiar_ajuste:
            self.opcion_ajuste.Check(bool(self.configuracion.obtener("ajuste_de_linea")))
        # El partido en renglones no necesita rehacer el control —lo aplica
        # `refrescar_apariencia` al recargar el texto—, pero sí que la casilla
        # del menú diga lo que hay puesto.
        self.opcion_renglon_frase.Check(
            bool(self.configuracion.obtener("renglon_por_frase", False)))
        if self.pestanas.cambiar_modo(bool(self.configuracion.obtener("usar_pestanas", False))):
            self._refrescar_titulo()
        self.aplicar_arbol(bool(self.configuracion.obtener("mostrar_arbol", False)))
        self._menu_de_pestanas()
        self._actualizar_disponibilidad()
        if self.documento is not None:
            self._actualizar_estado(self.lector.posicion())
        self.lectura_voz.aplicar_ajustes()
        # El gestor de sonidos guarda su estado en atributos, no lee la
        # configuración: hay que llevárselo.
        self.sonidos.activado = bool(self.configuracion.obtener("sonidos_activados", True))
        self.sonidos.establecer_volumen(int(self.configuracion.obtener("sonidos_volumen", 70)))
        if avisar_teclas:
            # Las teclas globales pueden haber cambiado: se vuelven a pedir a
            # Windows y se avisa de las que no hayan entrado.
            self.aplicar_teclas_globales(avisar=True)
        if reabrir and self.ruta_actual:
            respuesta = wx.MessageBox(
                _("Has cambiado una opción que afecta a cómo se convierte el libro.\n"
                "¿Quieres volver a abrirlo ahora para que surta efecto?"),
                _("Volver a abrir el documento"), wx.YES_NO | wx.ICON_QUESTION, self,
            )
            if respuesta == wx.YES:
                # Se relee **a la fuerza** y en la pestaña de siempre.  Sin lo
                # primero, un ajuste que no forma parte de la firma del
                # análisis —el reconocimiento de lo escaneado, por ejemplo—
                # devolvía lo que había guardado y el cambio no se notaba; sin
                # lo segundo, el documento ya estaba abierto en esta pestaña y
                # la orden se quedaba en «Ya estaba abierto».
                self.abrir_libro(self.ruta_actual, en_pestana_nueva=False,
                                 releer=True,
                                 posicion_inicial=self.lector.posicion())

    def al_opciones(self, evento) -> None:
        """Abre el diálogo de preferencias."""
        with dialogos_opciones.DialogoOpciones(self, self.configuracion, self.sonidos) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                return
            self.aplicar_preferencias(reabrir=dialogo.hay_que_reanalizar,
                                      avisar_teclas=True)

    def _abrir_documento(self, origen: Path, titulo: str, aviso: str) -> None:
        """Convierte un documento en Markdown a página web y lo abre.

        La documentación se guarda en Markdown, porque así es texto que se
        puede leer y editar con cualquier programa.  Para consultarla se
        convierte a HTML —con el conversor propio de :mod:`nucleo.marcado`, sin
        depender de ninguna biblioteca externa— y se abre en el navegador, que
        es donde mejor se leen los encabezados, las tablas y las listas con un
        lector de pantalla.

        La página convertida se guarda en ``data/temp`` y solo se vuelve a
        generar cuando el original ha cambiado.  Lleva el idioma en el nombre,
        porque si no, al cambiar de idioma se seguiría abriendo la página que
        se convirtió con el anterior.

        :param origen: Archivo Markdown que hay que abrir.
        :param titulo: Título de la página y de los mensajes de error.
        :param aviso: Qué decir si el archivo no está.  Lleva un ``%s`` donde
            va la ruta en la que debería estar, que es la única forma de que
            quien lo tenga que colocar sepa dónde.
        """
        if not origen.exists():
            wx.MessageBox(aviso % origen, titulo, wx.OK | wx.ICON_INFORMATION, self)
            return
        # El idioma del nombre es el de la carpeta de la que ha salido, no el
        # que esté puesto: si se ha caído al español, la página es la española.
        cual = rutas.codigo_de_documento(origen)
        destino = rutas.ruta_temp() / ("%s_%s.html" % (origen.stem, cual))
        try:
            if (not destino.exists()
                    or destino.stat().st_mtime < origen.stat().st_mtime):
                with cronometro(log, "conversion de %s a HTML" % origen.name):
                    texto = origen.read_text(encoding="utf-8")
                    destino.write_text(marcado.a_html(texto, titulo),
                                       encoding="utf-8")
            wx.LaunchDefaultBrowser(destino.as_uri())
            log.info("Documento abierto en el navegador: %s", destino)
        except Exception as error:
            registrar_excepcion(log, "No se ha podido preparar %s" % origen.name, error)
            wx.MessageBox(_("No se ha podido abrir el documento:\n%s") % error,
                          titulo, wx.OK | wx.ICON_ERROR, self)

    def al_manual(self, evento) -> None:
        """Abre el manual de usuario en el navegador.

        El manual vive en la carpeta de su idioma,
        ``data/idiomas/<código>/docs``: quien lo traduzca lo deja ahí y ya
        está.  Si el idioma que hay puesto todavía no lo tiene, se abre el
        español, que es el original: más vale el manual en otro idioma que
        ningún manual.
        """
        self._abrir_documento(
            rutas.ruta_manual(),
            _("Manual de %s") % NOMBRE,
            _("No se encuentra el manual de usuario.\n\nDebería estar en:\n%s"))

    def al_novedades(self, evento) -> None:
        """Abre en el navegador lo que ha cambiado en cada versión.

        Es el mismo archivo que se lee al ofrecer una actualización, pero
        entero y de una vez: el aviso de actualización solo cuenta la versión
        que llega, y esto sirve para volver a lo que se leyó por encima hace
        tres versiones.

        Ejecutando desde el código fuente se abre el ``NOVEDADES.md`` de la
        raíz del proyecto, que es el que se está escribiendo.  En el programa
        compilado se abre la copia que la compilación deja junto al manual, que
        empieza directamente en la versión más reciente: la cabecera del
        original explica cómo se publican las versiones y ahí no pinta nada.
        """
        self._abrir_documento(
            rutas.ruta_novedades(),
            _("Novedades de %s") % NOMBRE,
            _("No se encuentra el archivo de novedades.\n\nDebería estar en:\n%s"))

    def al_atajos(self, evento) -> None:
        """Muestra la lista de atajos de teclado."""
        with dialogos_ayuda.DialogoAtajos(self) as dialogo:
            dialogo.ShowModal()

    def al_ver_registro(self, evento) -> None:
        """Abre el visor de registros.

        No es modal a propósito: para diagnosticar un problema hay que poder
        dejarlo abierto, reproducir el fallo en la ventana principal y ver
        aparecer el error.  Si ya estaba abierto, se trae al frente en lugar de
        abrir un segundo visor.
        """
        if self.visor_registro is not None:
            self.visor_registro.Raise()
            self.visor_registro.SetFocus()
            return
        self.visor_registro = dialogos_registro.DialogoRegistro(self, self.configuracion)
        self.visor_registro.Show()

    def al_leer_voz(self, evento) -> None:
        """Empieza a leer, pausa o continúa.

        Con un libro DAISY grabado delante, esta orden manda sobre la grabación
        y no sobre la voz sintética.  Es deliberado: la tecla significa «lee
        esto en voz alta», y cuando el libro trae la voz de un narrador humano
        eso es lo que hay que hacer sonar.
        """
        if self.reproductor_daisy.activo:
            self.reproductor_daisy.alternar()
            return
        self.lectura_voz.alternar()

    def al_detener_voz(self, evento) -> None:
        """Corta la lectura, sea la grabación o la voz sintética."""
        if self.reproductor_daisy.activo:
            self.reproductor_daisy.detener(anunciar=True)
            return
        self.lectura_voz.detener(anunciar=True)

    def al_datos_guardados(self, evento) -> None:
        """Abre el gestor de lo que el programa guarda de cada libro."""
        from interfaz.dialogos.datos import DialogoDatos

        with DialogoDatos(self, self.configuracion, self.ruta_actual) as dialogo:
            dialogo.ShowModal()
            if dialogo.hubo_cambios:
                # Los marcadores del libro abierto pueden haberse borrado desde
                # ahí, así que se vuelven a leer en vez de dejar en memoria unos
                # que ya no están guardados.
                if self.ruta_actual:
                    datos = self.configuracion.datos_de(self.ruta_actual)
                    self.marcadores = list(datos.marcadores)
                    self.descripciones = descripciones.Coleccion(self.ruta_actual)
                self._refrescar_recientes()

    def al_donde_estoy(self) -> None:
        """Dice por dónde va la lectura, con el detalle que corresponda.

        Con una grabación delante interesa el tiempo —cuánto llevas, cuánto
        queda—; con texto, el capítulo y el porcentaje.  Es la misma pregunta
        con dos respuestas distintas.
        """
        if self.reproductor_daisy.activo:
            self.reproductor_daisy.donde_estoy()
            return
        if self.documento is None:
            self.anunciar(_("No hay ningún documento abierto."), inmediato=True)
            return
        self.anunciar(navegacion.contexto_de_lectura(self.documento, self.lector.posicion()),
                      inmediato=True)

    def al_reproductor_daisy(self, evento) -> None:
        """Abre los mandos del reproductor DAISY."""
        if not self.reproductor_daisy.activo:
            self.anunciar(_("Este documento no tiene grabación."), inmediato=True)
            return
        with DialogoReproductor(self, self.reproductor_daisy) as dialogo:
            dialogo.ShowModal()

    def _leer_frase(self, adelante: bool) -> None:
        """Una frase adelante o atrás, con el motor que toque."""
        if self.reproductor_daisy.activo:
            self.reproductor_daisy.saltar_frase(adelante)
            return
        self.lectura_voz.saltar_frase(adelante)

    def _leer_mas_o_menos(self, incremento: int) -> None:
        """Sube o baja la velocidad de lo que se esté escuchando."""
        if self.reproductor_daisy.activo:
            self.reproductor_daisy.cambiar_velocidad(1 if incremento > 0 else -1)
            return
        self.lectura_voz.cambiar_velocidad(incremento)

    def al_ajustes_voz(self, evento) -> None:
        """Abre los ajustes de la lectura en voz alta."""
        with DialogoVoz(self, self.lectura_voz) as dialogo:
            dialogo.ShowModal()

    def al_invitar_cafe(self, evento) -> None:
        """Abre en el navegador la página de donaciones del autor."""
        from version import URL_DONACIONES

        wx.LaunchDefaultBrowser(URL_DONACIONES)
        self.anunciar(_("Gracias. Se ha abierto la página de donaciones en el navegador."))

    def al_acerca_de(self, evento) -> None:
        """Muestra la información del programa."""
        with dialogos_ayuda.DialogoAcercaDe(self, self.version) as dialogo:
            dialogo.ShowModal()

    # =======================================================================
    # Barra de estado
    # =======================================================================

    # =======================================================================
    # Bandeja del sistema y teclas globales
    # =======================================================================

    def aplicar_teclas_globales(self, avisar: bool = False) -> None:
        """Registra en Windows las teclas globales configuradas.

        :param avisar: Si se informa de las que no se han podido registrar.
                       Se usa al volver de las opciones, donde el usuario acaba
                       de tocarlas y espera saber si han quedado puestas.
        """
        registradas = self.registro_global.aplicar(self.configuracion)
        fallidas = self.registro_global.fallidas
        if fallidas:
            log.warning("Teclas globales no registradas: %s", ", ".join(fallidas))
        if not avisar:
            return
        if fallidas:
            detalle = "\n".join(
                "%s: %s" % (next((a.etiqueta for a in teclas_globales.CATALOGO
                                  if a.identificador == clave), clave), motivo)
                for clave, motivo in fallidas.items())
            wx.MessageBox(
                "Han quedado puestas %d teclas globales, pero estas no:\n\n%s"
                % (registradas, detalle),
                _("Teclas globales"), wx.OK | wx.ICON_WARNING, self)
        elif registradas:
            self.anunciar("%d teclas globales puestas." % registradas)

    def _al_pulsar_tecla_global(self, accion: str) -> None:
        """Ejecuta la acción de una tecla global.

        Llega desde Windows aunque el foco esté en otro programa, así que aquí
        no se puede dar por supuesto que la ventana esté visible ni activa.
        """
        log.debug("Tecla global: %s", accion)
        if accion == "mostrar_ocultar":
            self.alternar_visibilidad()
            return
        # Las mismas teclas sirven para las dos formas de escuchar un libro:
        # mandan sobre la grabación cuando el libro es un DAISY con audio y
        # sobre la voz sintética en cualquier otro caso.  Es lo que se espera
        # de una tecla que significa «pausa» o «más deprisa».
        if self.reproductor_daisy.activo:
            reproductor = self.reproductor_daisy
            acciones = {
                "leer_pausar": reproductor.alternar,
                "detener": lambda: reproductor.detener(anunciar=True),
                "frase_anterior": lambda: reproductor.saltar_frase(False),
                "frase_siguiente": lambda: reproductor.saltar_frase(True),
                "mas_rapido": lambda: reproductor.cambiar_velocidad(1),
                "mas_lento": lambda: reproductor.cambiar_velocidad(-1),
                "salto_atras": lambda: reproductor.saltar_segundos(-audio.SALTO),
                "salto_adelante": lambda: reproductor.saltar_segundos(audio.SALTO),
                "punto_anterior": reproductor.punto_anterior,
                "punto_siguiente": reproductor.punto_siguiente,
                "donde_estoy": reproductor.donde_estoy,
            }
        else:
            acciones = {
                "leer_pausar": self.lectura_voz.alternar,
                "detener": lambda: self.lectura_voz.detener(anunciar=True),
                "frase_anterior": lambda: self.lectura_voz.saltar_frase(False),
                "frase_siguiente": lambda: self.lectura_voz.saltar_frase(True),
                "mas_rapido": lambda: self.lectura_voz.cambiar_velocidad(5),
                "mas_lento": lambda: self.lectura_voz.cambiar_velocidad(-5),
                # Sin grabación no hay «diez segundos atrás», pero sí el
                # equivalente en texto: la página y el encabezado.
                "salto_atras": lambda: self.navegar_a(Objetivo.PAGINA, False),
                "salto_adelante": lambda: self.navegar_a(Objetivo.PAGINA, True),
                "punto_anterior": lambda: self.navegar_a(Objetivo.ENCABEZADO, False),
                "punto_siguiente": lambda: self.navegar_a(Objetivo.ENCABEZADO, True),
                "donde_estoy": self.al_donde_estoy,
            }
        metodo = acciones.get(accion)
        if metodo is not None:
            metodo()

    def alternar_visibilidad(self) -> None:
        """Esconde la ventana en la bandeja, o la trae de vuelta."""
        if self.icono_bandeja is not None or not self.IsShown():
            self.restaurar_desde_bandeja()
        else:
            self.esconder_en_bandeja()

    def esconder_en_bandeja(self) -> None:
        """Quita la ventana de la pantalla y deja el icono de la bandeja."""
        if self.icono_bandeja is not None:
            return
        self.icono_bandeja = IconoBandeja(self)
        self.Hide()
        log.info("Ventana escondida en la bandeja del sistema")

    def restaurar_desde_bandeja(self) -> None:
        """Devuelve la ventana a la pantalla y quita el icono."""
        self.traer_al_frente()
        self.anunciar(_("%s.") % NOMBRE)

    def traer_al_frente(self) -> None:
        """Pone la ventana delante, venga de donde venga.

        Sirve para las tres formas de tenerla escondida —minimizada, oculta en
        la bandeja o simplemente detrás de otro programa— y hace falta llamarla
        entera en todas: ``Raise`` de wx no sortea la proteccion de primer
        plano de Windows, y forzar el primer plano por la API del sistema no
        arregla el estado interno de wx.  Hacen falta las dos cosas.
        """
        if self.IsIconized():
            self.Iconize(False)
        if not self.IsShown():
            self.Show()
        self.Raise()
        if self.icono_bandeja is not None:
            self.icono_bandeja.Destroy()
            self.icono_bandeja = None
        instancia.forzar_al_frente(self.GetHandle())
        self.lector.texto.SetFocus()

    def _al_minimizar(self, evento) -> None:
        """Al minimizar, esconde el programa en la bandeja si así se ha pedido."""
        if evento.IsIconized() and self.configuracion.obtener("minimizar_a_bandeja", False):
            # El paso a la bandeja se aplaza: hacerlo dentro del propio evento
            # de minimizar deja a Windows a medio camino y la ventana puede
            # quedarse sin repintar.
            wx.CallAfter(self.esconder_en_bandeja)
        evento.Skip()

    def _al_moverse(self, posicion: int, salto: bool = False) -> None:
        """Reacciona a que el cursor haya cambiado de sitio."""
        self.cronometro.latido(posicion, salto=salto)
        self._actualizar_estado(posicion)
        self._avisar_de_la_descripcion(posicion)

    def _avisar_de_la_descripcion(self, posicion: int) -> None:
        """Dice la descripción guardada al llegar a la línea de una imagen.

        Se hace al **cambiar de línea** y una sola vez por línea: si se dijera
        en cada movimiento del cursor, recorrer con las flechas el párrafo de
        una ilustración repetiría la descripción entera a cada paso.

        Da igual cómo se haya llegado —con la tecla G, con las flechas o desde
        el índice—: en cuanto el cursor entra en la línea de una imagen ya
        descrita, se oye lo que hay en ella.
        """
        if self.documento is None:
            return
        # Mientras lee la voz del programa, el aviso lo daría el lector de
        # pantalla **encima** de ella: dos voces a la vez diciendo lo mismo.
        # La lectura en voz alta ya dice la descripción por su cuenta si está
        # activada su opción.
        if self.lectura_voz.leyendo:
            return
        linea = self.documento.linea_de(posicion)
        if linea == self._linea_descrita:
            return
        self._linea_descrita = linea
        descripcion = self._descripcion_guardada_en(posicion)
        if descripcion:
            self.anunciar(descripcion.strip(), inmediato=True)

    def _actualizar_estado(self, posicion: int) -> None:
        """Escribe en la barra de estado la posición de lectura y los recuentos."""
        if self.documento is None:
            return
        try:
            self.SetStatusText(navegacion.resumen_posicion(self.documento, posicion))
            self.SetStatusText(self._resumen_del_documento(), 1)
        except RuntimeError:
            pass  # la ventana se está destruyendo

    def _resumen_del_documento(self) -> str:
        """Tamaño del documento: palabras, páginas y lo que se lleva leído.

        Los recuentos se calculan una sola vez por documento y se guardan en la
        sesión: contar las palabras de un libro de treinta millones de
        caracteres en cada movimiento del cursor dejaría el programa inservible.
        """
        if not self.configuracion.obtener("barra_recuentos", True):
            return ""
        sesion = self.sesion
        if sesion is None or sesion.documento is None:
            return ""
        recuentos = sesion.recuentos
        partes = [_("%s palabras") % format(recuentos.palabras, ",d").replace(",", ".")]
        if sesion.documento.total_paginas:
            partes.append(_("%d páginas") % sesion.documento.total_paginas)
        if len(self.pestanas) > 1:
            partes.append(_("pestaña %d de %d")
                          % (self.pestanas.indice_actual + 1, len(self.pestanas)))
        return " · ".join(partes)

    # =======================================================================
    # Cierre
    # =======================================================================

    def _al_revisar_encargos(self, evento) -> None:
        """Atiende la petición de otra copia del programa que acaba de arrancar.

        Cuando alguien abre un segundo libro con el programa ya en marcha, esa
        segunda copia se cierra dejando aquí el archivo que quería abrir; esta
        ventana lo recoge y lo abre ella misma.
        """
        encargo = instancia.recoger_encargo()
        if encargo is None:
            return
        log.info("Encargo recibido de otra copia del programa: %r", encargo)
        # Se restaura con el codigo propio y no solo forzando la ventana desde
        # fuera: user32 la pone en pantalla, pero no sabe quitar el icono de la
        # bandeja, devolver el foco al texto ni anunciarlo.  Eso solo puede
        # hacerlo la ventana consigo misma.
        self.traer_al_frente()
        if encargo:
            self.abrir_libro(encargo)

    def al_primer_uso(self, evento) -> None:
        """Abre el recorrido guiado.

        La primera vez se hace entero. A partir de ahí se pregunta **qué parte**
        se quiere repasar, porque nadie vuelve a atravesar diecisiete pantallas
        para recordar una tecla de la voz: sin poder entrar por la mitad, el
        recorrido se usa una vez y no se vuelve a abrir.
        """
        apartado = ""
        if evento is not None and not dialogos_primer_uso.hace_falta(self.configuracion):
            apartado = self._elegir_apartado_del_recorrido()
            if apartado is None:
                return
        with dialogos_primer_uso.DialogoPrimerUso(self, self.configuracion,
                                                  apartado) as dialogo:
            dialogo.ShowModal()
            dialogo.marcar_hecho()
        self.lector.texto.SetFocus()

    def al_practicar(self, evento) -> None:
        """Abre el modo de práctica sobre el documento que haya abierto.

        La ventana **no es modal**: el ejercicio se hace en el documento, así
        que hay que poder volver a él. Por eso, además, se le devuelve el foco
        al texto en cuanto se abre: quien practica tiene que estar en el sitio
        donde se practica, no en la ventana que lo cuenta.
        """
        del evento
        if self.documento is None:
            self.anunciar(_("Abre un documento y vuelve a intentarlo: se "
                            "practica sobre el que estés leyendo."), True)
            return
        from interfaz.dialogos.practica import DialogoPractica

        if self._dialogo_practica is not None:
            try:
                self._dialogo_practica.Destroy()
            except RuntimeError:                 # ya se había cerrado
                pass
        self._dialogo_practica = DialogoPractica(self, self.configuracion)
        self._dialogo_practica.Show()
        self.lector.texto.SetFocus()

    def al_abrir_direccion(self, evento) -> None:
        """Trae una página de internet, la limpia y la abre.

        La página se guarda en el disco antes de abrirla, y no se lee de la
        memoria, por dos razones: así se puede volver a ella sin conexión, y así
        la posición de lectura, los marcadores y las notas se guardan como los
        de cualquier otro documento. Una página que no se puede marcar no sirve
        para estudiar.
        """
        del evento
        from nucleo import rutas, traer_web

        with wx.TextEntryDialog(
            self,
            _("Pega o escribe la dirección de la página que quieres leer.\n\n"
              "Se trae, se le quitan los menús y los anuncios y se abre. Si es un "
              "PDF o un EPUB, se descarga y se abre tal cual."),
            _("Abrir una dirección de internet"),
            self._direccion_del_portapapeles()
        ) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                return
            direccion = dialogo.GetValue().strip()
        if not direccion:
            return

        carpeta = rutas.subcarpeta("temp") / "web"
        try:
            carpeta.mkdir(parents=True, exist_ok=True)
        except OSError as error:                     # pragma: no cover
            wx.MessageBox(_("No se ha podido preparar la carpeta: %s") % error,
                          _("Abrir una dirección"), wx.OK | wx.ICON_ERROR, self)
            return

        self.anunciar(_("Trayendo la página..."), inmediato=True)
        espera = wx.BusyCursor()
        try:
            destino = traer_web.traer(direccion, carpeta)
        except traer_web.ErrorAlTraer as error:
            del espera
            self.sonidos.reproducir("error")
            wx.MessageBox(str(error), _("Abrir una dirección de internet"),
                          wx.OK | wx.ICON_WARNING, self)
            return
        except Exception as error:                   # pragma: no cover
            del espera
            registrar_excepcion(log, "Error al traer una página", error)
            wx.MessageBox(_("No se ha podido traer la página: %s") % error,
                          _("Abrir una dirección de internet"),
                          wx.OK | wx.ICON_ERROR, self)
            return
        del espera
        self.abrir_libro(str(destino))

    @staticmethod
    def _direccion_del_portapapeles() -> str:
        """Lo que haya en el portapapeles, si parece una dirección.

        Casi siempre se llega aquí después de copiar el enlace en otro sitio,
        así que ofrecerlo escrito ahorra pegarlo, que con lector de pantalla es
        un paso más en el que perderse.
        """
        texto = ""
        if wx.TheClipboard.Open():
            try:
                datos = wx.TextDataObject()
                if wx.TheClipboard.GetData(datos):
                    texto = datos.GetText().strip()
            finally:
                wx.TheClipboard.Close()
        primera = texto.split()[0] if texto.split() else ""
        if primera.lower().startswith(("http://", "https://", "www.")):
            return primera[:2000]
        return ""

    def _elegir_apartado_del_recorrido(self):
        """Pregunta qué parte del recorrido se quiere repasar.

        Devuelve el nombre del apartado, la cadena vacía para hacerlo entero, o
        ``None`` si se ha cancelado. La primera opción es «todo» a propósito:
        quien no sepa qué elegir pulsa Intro y le pasa lo de siempre.
        """
        apartados = dialogos_primer_uso.apartados()
        if not apartados:
            return ""
        rotulos = [_("Todo el recorrido")] + [
            _("%(apartado)s (%(cuantos)d pantallas)")
            % {"apartado": nombre,
               "cuantos": len(dialogos_primer_uso.pasos_de(nombre))}
            for nombre in apartados]
        with wx.SingleChoiceDialog(
            self, _("¿Qué quieres repasar?"), _("Recorrido guiado"), rotulos
        ) as dialogo:
            dialogo.SetSelection(0)
            if dialogo.ShowModal() != wx.ID_OK:
                return None
            elegido = dialogo.GetSelection()
        return "" if elegido <= 0 else apartados[elegido - 1]

    def al_exportar_audio(self, evento) -> None:
        """Convierte el documento abierto en archivos de sonido.

        La orden va apagada mientras no haya documento, igual que el resto de
        las exportaciones, así que aquí solo queda comprobar que haya voz con
        la que grabar.
        """
        if self.documento is None:
            return
        if not self.lectura_voz.disponible:
            wx.MessageBox(
                _("Este equipo no tiene ninguna voz del sistema instalada, así que no hay "
                  "con qué grabar.\n\nLas voces se añaden en Configuración de Windows, en "
                  "«Hora e idioma», «Voz»."),
                _("Exportar a audio"), wx.OK | wx.ICON_INFORMATION, self)
            return
        with dialogos_audio.DialogoExportarAudio(self) as dialogo:
            dialogo.ShowModal()

    def al_ver_capitulo(self, evento) -> None:
        """Muestra el capítulo donde está el cursor en el visor HTML.

        El visor ya sabía enseñar una tabla, una lista o una cita sueltas.  Un
        capítulo entero es lo mismo a mayor escala, y resuelve algo que la
        conversión a texto no puede: dentro del visor vuelven a existir los
        encabezados, las listas anidadas y las tablas **como tales**, así que
        valen las órdenes de tabla y de encabezado del lector de pantalla.
        """
        if self.documento is None:
            return
        visor_html.mostrar_capitulo(self, self.documento, self.lector.posicion())

    def al_leer_nota(self, evento) -> None:
        """Dice la nota al pie de la llamada donde está el cursor, sin moverlo.

        Es lo que hace falta leyendo: una nota al pie interrumpe la frase, y
        tener que saltar a ella, leerla y volver rompe el hilo.  Aquí se oye la
        nota y el cursor sigue exactamente donde estaba, listo para seguir.

        Con Intro sobre la llamada se salta a la nota de verdad, y con
        Alt+Izquierda se vuelve: para las notas largas, que son las que hay que
        leer con calma.
        """
        if self.documento is None:
            return
        marca = self._llamada_de_nota_en_el_cursor()
        if marca is None:
            self.sonidos.reproducir("limite")
            self.anunciar(_("Aquí no hay ninguna llamada de nota al pie. "
                            "Usa la tecla O para ir a la siguiente."), inmediato=True)
            return
        texto = self._texto_de_la_nota(marca)
        if not texto:
            self.sonidos.reproducir("limite")
            self.anunciar(_("No se ha encontrado el texto de esa nota."), inmediato=True)
            return
        self.sonidos.reproducir("nota")
        self.anunciar(_("Nota: %s") % texto, inmediato=True)

    def _llamada_de_nota_en_el_cursor(self):
        """La llamada de nota que hay en la línea del cursor, si la hay."""
        posicion = self.lector.posicion()
        candidatas = [marca for marca in navegacion.elementos_en_linea(self.documento, posicion)
                      if marca.tipo is TipoMarca.NOTA_PIE]
        if not candidatas:
            return None
        # Si hay varias en la misma línea —lo normal en un párrafo anotado—,
        # manda aquella dentro de la que esté el cursor; si no está dentro de
        # ninguna, la primera de la línea.
        for marca in candidatas:
            if marca.posicion <= posicion < marca.posicion + max(marca.longitud, 1):
                return marca
        return candidatas[0]

    def _texto_de_la_nota(self, marca) -> str:
        """Saca el texto de la nota a la que apunta una llamada.

        La nota es un trozo del mismo documento: se resuelve el destino del
        enlace y se lee desde ahí hasta donde la nota acabe.  Se recorta a una
        longitud razonable porque un aviso hablado no puede durar cinco minutos;
        para una nota larguísima está el saltar a ella con Intro.

        Dónde acaba una nota no es evidente, y eso lo sabe :mod:`nucleo.notas`:
        aquí solo se recorta a lo que se puede escuchar de una vez.
        """
        trozo = notas.texto_de(self.documento, marca, LARGO_NOTA)
        if len(trozo) >= LARGO_NOTA - 1:
            trozo = trozo[:LARGO_NOTA]
            trozo += _("... (pulsa Intro sobre la llamada para leerla entera)")
        return trozo

    def al_resumir(self, evento) -> None:
        """Pide a la IA un resumen del capítulo donde está el cursor."""
        self._abrir_preguntas("resumen")

    def al_preguntar(self, evento) -> None:
        """Abre la ventana de preguntas sobre el documento."""
        self._abrir_preguntas("libre")

    def _abrir_preguntas(self, inicial: str) -> None:
        """Abre la ventana de preguntas con una pregunta ya elegida.

        Las dos órdenes —resumir y preguntar— llevan a la misma ventana: son la
        misma operación con distinta pregunta de partida, y tener dos ventanas
        casi iguales solo obligaría a aprenderse las dos.
        """
        if self.documento is None:
            return
        servicio = Servicio(self.configuracion)
        motivo = servicio.motivo_no_disponible()
        if motivo:
            wx.MessageBox(motivo, _("Inteligencia artificial"),
                          wx.OK | wx.ICON_INFORMATION, self)
            return
        with dialogos_preguntar.DialogoPreguntar(self, servicio, inicial) as dialogo:
            dialogo.ShowModal()

    def al_temporizador(self, evento) -> None:
        """Pone o quita el temporizador de apagado.

        La orden va apagada mientras no haya documento abierto: un temporizador
        que apaga una lectura que no existe no significa nada.
        """
        if self.documento is None:
            return
        with DialogoTemporizador(self, self.temporizador) as dialogo:
            if dialogo.ShowModal() == wx.ID_OK:
                minutos = dialogo.minutos()
                self.configuracion.establecer("voz_temporizador_minutos", minutos)
                self.temporizador.poner(minutos)

    def al_pronunciacion(self, evento) -> None:
        """Abre el diccionario de pronunciación."""
        with dialogos_pronunciacion.DialogoPronunciacion(self) as dialogo:
            dialogo.ShowModal()

    def _texto_y_posicion(self) -> tuple[str, int]:
        """Texto sobre el que está el cursor y dónde está, haya libro o no.

        Con un documento abierto se usa el suyo, que ya está en memoria: pedirle
        el texto al control obligaría a copiar millones de caracteres.  Sin
        documento se usa **lo que haya en el control**, que es la pantalla de
        bienvenida: también es texto y también se puede consultar una palabra de
        ahí, que es lo que uno espera al tener el cursor encima de una.
        """
        if self.documento is not None:
            return self.documento.texto, self.lector.posicion()
        return self.lector.texto.GetValue(), self.lector.texto.GetInsertionPoint()

    def al_diccionario(self, evento) -> None:
        """Define la palabra del cursor, la seleccionada, o la que se escriba.

        Funciona también **sin documento abierto**, sobre el texto de la
        pantalla de bienvenida.
        """
        texto, posicion = self._texto_y_posicion()
        seleccion = self.lector.texto_seleccionado()
        # Con algo seleccionado manda la selección: quien selecciona una
        # locución de tres palabras quiere definir la locución, no la palabra
        # suelta donde quedó el cursor.
        palabra = (diccionario.limpiar(seleccion) if seleccion.strip()
                   else diccionario.palabra_en(texto, posicion))
        # El contexto solo tiene sentido con un documento delante: es lo que le
        # deja a la IA saber en qué acepción se usa la palabra.  En la pantalla
        # de bienvenida no hay nada que contextualizar.
        contexto = diccionario.frase_en(texto, posicion) if self.documento is not None else ""
        with dialogos_diccionario.DialogoDiccionario(
                self, palabra, contexto, Servicio(self.configuracion),
                self.configuracion) as dialogo:
            dialogo.ShowModal()

    # =======================================================================
    # Actualizaciones
    # =======================================================================

    def _revisar_actualizacion_anterior(self) -> None:
        """Avisa si la última actualización no llegó a copiarse del todo.

        Sin esto, alguien se quedaría con una versión que cree actualizada y no
        lo está, y sin ninguna pista de por qué: el guion trabaja con el
        programa ya cerrado y nadie ve lo que pasa.
        """
        fallo = actualizaciones.error_de_la_ultima()
        if not fallo:
            return
        log.warning("La última actualización no se aplicó del todo: %s", fallo)
        wx.MessageBox(
            _("La última actualización no se pudo aplicar del todo y el programa sigue "
              "en la versión %(version)s.\n\nSuele pasar cuando algún archivo estaba en "
              "uso. Vuelve a intentarlo desde Ayuda, Buscar actualizaciones.\n\n"
              "Detalle: %(detalle)s") % {"version": VERSION, "detalle": fallo},
            _("Actualización incompleta"), wx.OK | wx.ICON_WARNING, self)

    def al_buscar_actualizaciones(self, evento) -> None:
        """Comprueba a mano si hay versión nueva, diciendo siempre el resultado."""
        self.anunciar(_("Comprobando si hay una versión nueva..."), inmediato=True)
        self._comprobar_actualizaciones(True)

    def _comprobar_actualizaciones(self, avisar_siempre: bool) -> None:
        """Pregunta al servidor en otro hilo y ofrece la actualización si la hay.

        :param avisar_siempre: Con ``True`` se dice también que ya se tiene la
                               última versión o que no se ha podido comprobar.
                               Con ``False`` —la comprobación del arranque— se
                               calla: nadie quiere que el programa le hable de
                               versiones cada vez que abre un libro.
        """
        origen, url_propia = actualizaciones.de_configuracion(self.configuracion)
        if not actualizaciones.activadas(origen, url_propia):
            if avisar_siempre:
                wx.MessageBox(
                    _("No hay ningún sitio configurado donde buscar actualizaciones.\n\n"
                      "Si has elegido una dirección personalizada, escríbela en Opciones, "
                      "«Avanzado»."),
                    _("Buscar actualizaciones"), wx.OK | wx.ICON_INFORMATION, self)
            return

        def trabajo() -> None:
            manifiesto = actualizaciones.consultar(origen=origen, url_propia=url_propia)
            wx.CallAfter(self._con_manifiesto, manifiesto, avisar_siempre)

        threading.Thread(target=trabajo, name="actualizaciones", daemon=True).start()

    def _con_manifiesto(self, manifiesto, avisar_siempre: bool) -> None:
        """Decide qué hacer con lo que ha dicho el servidor."""
        if not manifiesto:
            if avisar_siempre:
                wx.MessageBox(
                    _("No se ha podido comprobar si hay una versión nueva.\n\n"
                      "Revisa la conexión a Internet y vuelve a intentarlo."),
                    _("Buscar actualizaciones"), wx.OK | wx.ICON_INFORMATION, self)
            return
        version = str(manifiesto.get("version", "")).strip()
        if not actualizaciones.es_mas_nueva(version):
            if avisar_siempre:
                wx.MessageBox(
                    _("Ya tienes la última versión (%s).") % VERSION,
                    _("Buscar actualizaciones"), wx.OK | wx.ICON_INFORMATION, self)
            return
        log.info("Hay una versión nueva: %s", version)
        with dialogos_actualizacion.DialogoActualizacion(self, version, manifiesto) as dialogo:
            dialogo.ShowModal()

    def aplicar_actualizacion(self, guion) -> None:
        """Guarda lo imprescindible, lanza el guion y sale de inmediato.

        Hay que salir *ya*: el guion está esperando a que este proceso muera
        para poder escribir encima de los archivos del programa, que mientras
        tanto están en uso.  Por eso se termina con ``os._exit`` y no cerrando
        la ventana: cualquier ventana que pidiera confirmación dejaría la
        actualización a medias esperando una respuesta.
        """
        try:
            self.guardar_sesion()
            self.configuracion.guardar()
        except Exception as error:
            registrar_excepcion(log, "Error al guardar antes de actualizar", error)
        try:
            self.lectura_voz.detener()
            self.reproductor_daisy.descargar()
            audio.terminar()
        except Exception:
            pass
        try:
            actualizaciones.lanzar_guion(guion)
        except Exception as error:
            registrar_excepcion(log, "No se ha podido lanzar la actualización", error)
            wx.MessageBox(_("No se ha podido iniciar la actualización. Inténtalo de nuevo."),
                          _("Actualización"), wx.OK | wx.ICON_ERROR, self)
            return
        log.info("Aplicando la actualización y reiniciando")
        instancia.olvidar_ventana()
        os._exit(0)

    def _arrancar_ia_local(self) -> None:
        """Levanta el servidor de la IA local si el usuario lo tiene pedido.

        Se hace en un hilo aparte porque arrancar el servidor y esperar a que
        conteste puede llevar unos segundos, y hacerlo aquí dejaría la ventana
        muda justo al abrirse, que es cuando peor sienta.
        """
        if not self.configuracion.obtener("ollama_arrancar_al_abrir", False):
            return
        from nucleo.ia import ollama

        if not ollama.instalado():
            return

        def trabajo():
            ollama.gestor.configuracion = self.configuracion
            if ollama.gestor.asegurar_en_marcha():
                log.info("IA local arrancada al abrir el programa")
            else:
                log.warning("No se ha podido arrancar la IA local al abrir")

        threading.Thread(target=trabajo, name="ia_local", daemon=True).start()

    def _cerrar_ia_local(self) -> None:
        """Cierra el servidor de la IA local al salir, si así se ha pedido.

        Viene pedido de fábrica: dejar un servidor de inteligencia artificial
        corriendo después de cerrar el lector no es lo que nadie espera, y
        ocupa memoria hasta que se apaga el equipo.  Solo se cierra **el
        nuestro**: si en el puerto hay otro que no arrancamos, no se toca.
        """
        if not self.configuracion.obtener("ollama_cerrar_al_salir", True):
            return
        try:
            from nucleo.ia import ollama

            if ollama.instalado():
                ollama.gestor.detener(forzar=True)
        except Exception as error:
            registrar_excepcion(log, "No se ha podido cerrar la IA local", error)

    def _al_cerrar_ventana(self, evento) -> None:
        """Guarda la sesión y las preferencias antes de cerrar."""
        try:
            self.guardar_todas_las_sesiones()
            self.anotar_documentos_abiertos()
            if self.division.IsSplit():
                self.configuracion.establecer("arbol_ancho", self.division.GetSashPosition())
            self.configuracion.establecer("ventana_maximizada", self.IsMaximized())
            if not self.IsMaximized():
                ancho, alto = self.GetSize()
                self.configuracion.establecer("ventana_ancho", ancho)
                self.configuracion.establecer("ventana_alto", alto)
            self.configuracion.guardar()
            if self.configuracion.obtener("sincronizacion_automatica", True):
                # Se sincroniza con las sesiones ya guardadas: así lo que se
                # lleva al otro equipo incluye lo de este último rato.
                sincronizacion.sincronizar(self.configuracion)
            log.info("Cierre de la ventana principal")
        except Exception as error:
            registrar_excepcion(log, "Error al guardar la sesión al cerrar", error)
        # La voz sigue hablando por su cuenta aunque la ventana desaparezca:
        # hay que callarla antes de cerrar.
        self.temporizador.quitar(anunciar=False)
        self.lectura_voz.detener()
        self.reproductor_daisy.descargar()
        self._cerrar_ia_local()
        audio.terminar()
        self.registro_global.soltar()
        # Mientras exista el icono de la bandeja, wxPython considera que la
        # aplicación tiene una ventana viva y no termina: hay que destruirlo o
        # el programa se queda en memoria sin nada que mostrar.
        if self.icono_bandeja is not None:
            self.icono_bandeja.Destroy()
            self.icono_bandeja = None
        if self._dialogo_buscar is not None:
            self._dialogo_buscar.Destroy()
        if self.visor_registro is not None:
            self.visor_registro.Destroy()
        self._vigilante_encargos.Stop()
        instancia.olvidar_ventana()
        evento.Skip()


def _misma_ruta(una: str, otra: str) -> bool:
    """Si dos rutas apuntan al mismo archivo.

    Se resuelven antes de comparar: la misma carpeta puede escribirse de varias
    formas —con la unidad en minúscula, con un acceso directo por medio, con
    barras al revés— y compararlas como texto diría que son distintas.
    """
    try:
        return Path(una).resolve() == Path(otra).resolve()
    except OSError:
        return str(una).lower() == str(otra).lower()


def _ha_cambiado_en_disco(sesion) -> bool:
    """Si el archivo de una sesión no es el mismo que se abrió.

    Se mira la fecha y el tamaño, que es lo mismo con lo que se decide si sirve
    lo que hay en la caché.  Si no se sabe con qué se abrió, se dice que no ha
    cambiado: releer un documento por si acaso, cada vez que se pide abrirlo,
    sería peor que el problema.
    """
    huella = getattr(sesion, "huella_archivo", None)
    if not huella:
        return False
    try:
        estado = Path(sesion.ruta).stat()
    except OSError:
        return False
    return huella != (estado.st_mtime_ns, estado.st_size)
