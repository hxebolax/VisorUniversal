# -*- coding: utf-8 -*-
"""Asistente para montar la inteligencia artificial local, paso a paso.

Tener IA en el propio ordenador es lo mejor que le puede pasar a este programa:
nada sale del equipo y no hay cuota que se agote.  Pero montarla, hasta ahora,
pedía saber qué es un servidor de modelos, cuál instalar, qué es un GGUF y qué
puerto usa cada cosa.  Eso deja fuera exactamente a quien más falta le hace.

Este asistente lo hace por el usuario.  Cinco pantallas, y al final del camino
hay una IA funcionando **sin haber instalado nada en el sistema ni haber
abierto una consola**:

1. **Qué es esto**, qué hace falta y qué se queda en el equipo.
2. **Qué ordenador tienes**: memoria y tarjeta gráfica.  De aquí sale qué
   modelos se le ofrecen y si va a trabajar con la gráfica o con el procesador.
3. **Descargar el motor** (Ollama portable), con su barra de progreso.
4. **Elegir y descargar el modelo**, de una lista corta en la que cada opción
   dice para qué es buena y qué pide.
5. **Probarlo** de verdad, con una pregunta real, y dejarlo activado.

Está hecho a imagen del recorrido guiado (:mod:`interfaz.dialogos.primer_uso`):
un título, una explicación que se recorre con las flechas y los botones al pie.
Lo que cambia es que aquí los pasos **hacen cosas**, y las cosas que hacen
tardan: por eso cada una tiene su barra de progreso, se puede cancelar y avisa
al terminar.  Una descarga de siete gigas sin decir por dónde va es una ventana
muda durante veinte minutos.
"""

from __future__ import annotations

import threading

import wx

from interfaz.dialogos import ayuda_opcion
from interfaz.accesible import etiquetar
from interfaz.anuncios import Voz
from nucleo.ia import modelos_vision, ollama
from nucleo.idioma import _
from nucleo.registro import obtener_registro, registrar_excepcion

log = obtener_registro(__name__)

#: Separación estándar entre controles.
MARGEN = 8

#: Cada cuánto se anuncia el progreso en voz alta, en por ciento.  Cada uno por
#: ciento serían cien interrupciones seguidas; cada diez se sigue sabiendo por
#: dónde va sin que la voz tape nada más.
PASO_ANUNCIO = 10


class DialogoAsistenteIA(wx.Dialog):
    """El asistente completo, una pantalla por paso.

    :param padre: Ventana principal.
    :param configuracion: Preferencias, donde se anota lo que se elija.
    """

    #: Los pasos, por su nombre interno.  El orden es el del recorrido.
    PASOS = ("bienvenida", "equipo", "motor", "modelo", "prueba", "final")

    def __init__(self, padre: wx.Window, configuracion) -> None:
        super().__init__(padre, title=_("Instalar la inteligencia artificial local"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.configuracion = configuracion
        self.voz = Voz(self)
        self.gestor = ollama.gestor
        self.gestor.configuracion = configuracion
        self.actual = 0
        self.equipo = None
        self.modelo_elegido = ""
        self._trabajando = False
        self._cancelar = False
        #: Se apaga al cerrar.  El hilo de trabajo tarda en enterarse de que
        #: se ha cancelado —una descarga no se corta en el acto—, y mientras
        #: tanto sigue mandando avisos de progreso a unos controles que ya no
        #: existen.
        self._vivo = True
        #: Qué ha quedado hecho, para poder saltarse pasos ya cumplidos y para
        #: el resumen final.
        self.hecho = {"motor": ollama.instalado(), "modelo": False, "prueba": False}

        contenedor = wx.BoxSizer(wx.VERTICAL)

        self.titulo = wx.StaticText(self, label="")
        fuente = self.titulo.GetFont()
        fuente.SetPointSize(fuente.GetPointSize() + 3)
        self.titulo.SetFont(fuente.Bold())
        contenedor.Add(self.titulo, 0, wx.ALL, MARGEN)

        # Cuadro de solo lectura en vez de una etiqueta: así el texto se
        # recorre con las flechas y se puede releer la parte que interese, que
        # es lo que hace falta cuando se está decidiendo algo.
        self.texto = wx.TextCtrl(
            self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP,
            size=(660, 260))
        etiquetar(self.texto, _("Explicación del paso"))
        contenedor.Add(self.texto, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, MARGEN)

        # La lista solo se enseña en el paso del modelo.
        self.etiqueta_lista = wx.StaticText(self, label=_("&Modelos que puedes instalar:"))
        contenedor.Add(self.etiqueta_lista, 0, wx.LEFT | wx.TOP, MARGEN)
        self.lista = etiquetar(wx.ListBox(self, style=wx.LB_SINGLE),
                               _("Modelos que puedes instalar"))
        self.lista.Bind(wx.EVT_LISTBOX, self._al_elegir_modelo)
        contenedor.Add(self.lista, 1, wx.EXPAND | wx.ALL, MARGEN)

        self.progreso = etiquetar(wx.Gauge(self, range=100), _("Progreso"))
        contenedor.Add(self.progreso, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, MARGEN)
        self.estado = wx.StaticText(self, label="")
        contenedor.Add(self.estado, 0, wx.ALL, MARGEN)

        botones = wx.BoxSizer(wx.HORIZONTAL)
        self.boton_accion = wx.Button(self, label=_("&Hacerlo"))
        self.boton_accion.Bind(wx.EVT_BUTTON, self._al_accionar)
        botones.Add(self.boton_accion, 0, wx.ALL, 5)
        self.boton_anterior = wx.Button(self, label=_("&Anterior"))
        self.boton_anterior.Bind(wx.EVT_BUTTON, lambda evento: self._mover(-1))
        botones.Add(self.boton_anterior, 0, wx.ALL, 5)
        self.boton_siguiente = wx.Button(self, label=_("&Siguiente"))
        self.boton_siguiente.Bind(wx.EVT_BUTTON, lambda evento: self._mover(1))
        self.boton_siguiente.SetDefault()
        botones.Add(self.boton_siguiente, 0, wx.ALL, 5)
        self.boton_salir = wx.Button(self, wx.ID_CANCEL, _("&Dejarlo para otro rato"))
        botones.Add(self.boton_salir, 0, wx.ALL, 5)
        contenedor.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 4)

        self.SetSizerAndFit(contenedor)
        self.SetSize((760, 620))
        self.CenterOnParent()
        self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar_tecla)
        self.Bind(wx.EVT_CLOSE, self._al_cerrar)
        self._pintar()
        self.texto.SetFocus()
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    # -- navegación -----------------------------------------------------------

    @property
    def paso(self) -> str:
        """Nombre del paso en el que se está."""
        return self.PASOS[self.actual]

    def _al_pulsar_tecla(self, evento: wx.KeyEvent) -> None:
        """Escape cancela lo que esté en marcha, o cierra si no hay nada."""
        if evento.GetKeyCode() == wx.WXK_ESCAPE:
            if self._trabajando:
                self._cancelar = True
                self._decir(_("Cancelando..."))
                return
            self.Close()
            return
        evento.Skip()

    def _mover(self, salto: int) -> None:
        """Pasa al paso siguiente o al anterior."""
        if self._trabajando:
            return
        siguiente = self.actual + salto
        if siguiente < 0:
            return
        if siguiente >= len(self.PASOS):
            self.EndModal(wx.ID_OK)
            return
        self.actual = siguiente
        self._pintar()
        self.texto.SetFocus()

    def _decir(self, mensaje: str) -> None:
        """Enseña un mensaje de estado y lo anuncia."""
        self.estado.SetLabel(mensaje)
        self.voz.decir(mensaje)

    # -- pintado de cada paso -------------------------------------------------

    def _pintar(self) -> None:
        """Pone en la ventana lo que toca al paso actual."""
        constructor = getattr(self, "_paso_" + self.paso)
        titulo, cuerpo, accion = constructor()
        self.titulo.SetLabel(titulo)
        self.texto.SetValue(cuerpo)
        self.texto.SetInsertionPoint(0)
        con_lista = self.paso == "modelo"
        self.etiqueta_lista.Show(con_lista)
        self.lista.Show(con_lista)
        self.boton_accion.Show(bool(accion))
        if accion:
            self.boton_accion.SetLabel(accion)
        self.progreso.SetValue(0)
        self.estado.SetLabel("")
        self.boton_anterior.Enable(self.actual > 0)
        self.boton_siguiente.SetLabel(
            _("&Terminar") if self.paso == "final" else _("&Siguiente"))
        self.Layout()
        # El título del paso se anuncia solo: al cambiar de pantalla, el foco
        # se queda en el mismo cuadro y el lector no diría que ha cambiado.
        self.voz.decir(titulo)

    def _paso_bienvenida(self) -> tuple[str, str, str]:
        return (
            _("Tu propia inteligencia artificial, en este ordenador"),
            _("Este asistente deja montada una inteligencia artificial que funciona "
              "**dentro de tu ordenador**, sin cuenta, sin clave y sin conexión una vez "
              "instalada.\n\n"
              "Para qué sirve aquí: describir las ilustraciones de un libro, contarte lo "
              "que dice un gráfico o una tabla, resumir un capítulo y responder preguntas "
              "sobre lo que estás leyendo.\n\n"
              "Lo que gana: **nada sale de tu equipo**. Ni el libro ni sus imágenes viajan "
              "a ningún servidor, y no hay cuota que se agote a mitad de un documento.\n\n"
              "Lo que cuesta: la descarga. El motor ocupa algo más de un giga y el modelo, "
              "entre dos y siete según el que elijas. Se descarga una vez y se queda. Si se "
              "corta la conexión, se reanuda donde iba.\n\n"
              "Dónde se instala: dentro de la carpeta «data» del propio programa. **No se "
              "instala nada en Windows** y no se toca lo que ya tengas: si usas Ollama por "
              "tu cuenta, el tuyo sigue igual, porque este usa su propio puerto y su propio "
              "almacén.\n\n"
              "Pulsa Siguiente para ver qué tal anda tu equipo."),
            "")

    def _paso_equipo(self) -> tuple[str, str, str]:
        if self.equipo is None:
            self.equipo = ollama.equipo()
        caben = modelos_vision.caben_en(self.equipo.libre_gb)
        if self.equipo.hay_grafica:
            consejo = _(
                "Tienes tarjeta gráfica, así que el trabajo lo hará ella y las respuestas "
                "llegarán en segundos. El programa la usará sola; si algún día diera "
                "problemas, en Opciones puedes decirle que use solo el procesador.")
        else:
            consejo = _(
                "No se ha visto una tarjeta gráfica dedicada, así que trabajará el "
                "procesador. **Funciona igual**, solo que más despacio: describir una "
                "imagen puede llevar de medio minuto a un par de minutos según el modelo. "
                "Por eso conviene elegir uno de los pequeños.")
        if caben:
            cuales = _("Con la memoria que tienes libre ahora mismo te caben %d de los %d "
                       "modelos de la lista.") % (len(caben), len(modelos_vision.MODELOS))
        else:
            cuales = _("Con la memoria libre que hay ahora mismo no cabría ninguno. Cierra "
                       "algún programa y vuelve a este paso, o sigue de todos modos: la "
                       "descarga funciona igual y podrás usarlo cuando tengas más memoria "
                       "libre.")
        return (
            _("Qué ordenador tienes"),
            _("%s\n\n%s\n\n%s\n\nPulsa Siguiente para descargar el motor.")
            % (self.equipo.resumen(), consejo, cuales),
            _("&Volver a mirar"))

    def _paso_motor(self) -> tuple[str, str, str]:
        if ollama.instalado():
            self.hecho["motor"] = True
            return (
                _("El motor ya está instalado"),
                _("Ollama %s ya está en la carpeta «data» de este programa.\n\n"
                  "Si quieres comprobar si hay una versión más nueva, hazlo desde "
                  "Opciones, «IA local». Pulsa Siguiente para elegir el modelo.")
                % (ollama.version_instalada() or _("(versión desconocida)")),
                _("&Volver a instalarlo"))
        return (
            _("Descargar el motor"),
            _("Ahora se descarga **Ollama**, que es el programa que hace funcionar los "
              "modelos. Ocupa algo más de un giga.\n\n"
              "Se descarga de su página oficial y se comprueba que ha llegado entero "
              "antes de instalar nada. Va a parar a la carpeta «data» del programa: no "
              "se instala en Windows ni aparece en la lista de programas.\n\n"
              "Con Escape se cancela; lo descargado se conserva y la próxima vez sigue "
              "desde donde iba.\n\n"
              "Pulsa «Descargar el motor» para empezar."),
            _("&Descargar el motor"))

    def _paso_modelo(self) -> tuple[str, str, str]:
        self._llenar_modelos()
        return (
            _("Elegir el modelo"),
            _("El **modelo** es lo que de verdad ve y escribe. Cada uno es bueno en algo "
              "distinto y pide una memoria.\n\n"
              "Elige uno de la lista de abajo y se te explicará aquí para qué sirve. "
              "Después pulsa «Descargar el modelo».\n\n"
              "Si no sabes cuál, quédate con el que pone «recomendado»: está hecho para "
              "entender documentos, tablas y gráficos, que es lo que más se pide en un "
              "lector de libros.\n\n"
              "Puedes instalar más de uno y cambiar entre ellos cuando quieras."),
            _("&Descargar el modelo"))

    def _paso_prueba(self) -> tuple[str, str, str]:
        return (
            _("Probarlo"),
            _("Vamos a comprobar que funciona de verdad: se arranca el servidor y se le "
              "hace una pregunta.\n\n"
              "La primera vez tarda más de lo normal, porque tiene que cargar el modelo "
              "en memoria: entre diez segundos y un minuto según el equipo. Las veces "
              "siguientes es mucho más rápido.\n\n"
              "Pulsa «Probarlo» y espera."),
            _("&Probarlo"))

    def _paso_final(self) -> tuple[str, str, str]:
        modelo = self.modelo_elegido or str(self.configuracion.obtener("ollama_modelo", ""))
        if self.hecho["prueba"]:
            cabecera = _("Ya tienes tu inteligencia artificial local funcionando.")
        else:
            cabecera = _("Ya está instalada. No se ha llegado a probar, pero puedes "
                         "hacerlo desde Opciones, «IA local».")
        return (
            _("Listo"),
            _("%s\n\n"
              "Qué ha quedado hecho:\n\n"
              "• El motor Ollama, dentro de la carpeta «data» del programa.\n"
              "• El modelo %s, descargado y elegido.\n"
              "• La inteligencia artificial, activada con este modelo.\n\n"
              "Qué puedes hacer ahora: colócate en una imagen y pulsa la tecla A para que "
              "te la describa, Control+Alt+U para resumir el capítulo o Control+Alt+Q para "
              "preguntar sobre lo que lees.\n\n"
              "Dónde se maneja todo esto: Opciones, pestaña «IA local». Ahí puedes "
              "arrancar y parar el servidor, instalar más modelos, cambiar de uno a otro, "
              "buscar versiones nuevas de Ollama y decidir si trabaja con la tarjeta "
              "gráfica o con el procesador.\n\n"
              "Pulsa Terminar.") % (cabecera, modelo or _("(ninguno)")),
            "")

    # -- la lista de modelos --------------------------------------------------

    def _llenar_modelos(self) -> None:
        """Vuelca los modelos, marcando el recomendado y los que no caben."""
        libre = self.equipo.libre_gb if self.equipo else 0.0
        instalados = set()
        try:
            if ollama.instalado() and self.gestor.estado().activo:
                instalados = {ficha["nombre"].split(":")[0]
                              for ficha in self.gestor.modelos()}
        except Exception:
            instalados = set()
        entradas = []
        self._modelos = list(modelos_vision.MODELOS)
        for modelo in self._modelos:
            marcas = []
            if modelo.recomendado:
                marcas.append(_("recomendado"))
            if modelo.etiqueta.split(":")[0] in instalados:
                marcas.append(_("ya instalado"))
            if libre and modelo.memoria_gb > libre:
                marcas.append(_("no te cabe ahora"))
            adorno = " [%s]" % ", ".join(marcas) if marcas else ""
            entradas.append(modelos_vision.resumen(modelo) + adorno)
        self.lista.Set(entradas)
        elegido = 0
        for numero, modelo in enumerate(self._modelos):
            if modelo.etiqueta == (self.modelo_elegido or modelos_vision.POR_OMISION):
                elegido = numero
                break
        self.lista.SetSelection(elegido)
        self.modelo_elegido = self._modelos[elegido].etiqueta

    def _al_elegir_modelo(self, evento) -> None:
        """Enseña arriba la explicación del modelo elegido."""
        indice = self.lista.GetSelection()
        if not 0 <= indice < len(self._modelos):
            return
        modelo = self._modelos[indice]
        self.modelo_elegido = modelo.etiqueta
        self.texto.SetValue(
            _("%s\n\n%s\n\nDescarga: %s. Memoria que necesita: %s.\n\n"
              "Pulsa «Descargar el modelo» cuando lo tengas claro.")
            % (modelo.nombre, modelo.detalle,
               modelos_vision.tamano_legible(modelo.descarga_mb),
               modelos_vision.memoria_legible(modelo.memoria_gb)))
        self.texto.SetInsertionPoint(0)

    # -- las acciones ---------------------------------------------------------

    def _al_accionar(self, evento) -> None:
        """Hace lo que toque en este paso."""
        if self._trabajando:
            return
        if self.paso == "equipo":
            self.equipo = ollama.equipo()
            self._pintar()
            self._decir(self.equipo.resumen())
            return
        if self.paso == "motor":
            self._en_segundo_plano(self._instalar_motor, _("Descargando el motor"))
            return
        if self.paso == "modelo":
            if not ollama.instalado():
                wx.MessageBox(_("Antes hay que descargar el motor. Vuelve al paso anterior."),
                              _("Falta el motor"), wx.OK | wx.ICON_INFORMATION, self)
                return
            self._en_segundo_plano(self._instalar_modelo, _("Descargando el modelo"))
            return
        if self.paso == "prueba":
            self._en_segundo_plano(self._probar, _("Probando"))

    def _en_segundo_plano(self, tarea, titulo: str) -> None:
        """Lanza una tarea larga sin dejar la ventana colgada.

        Todo lo que tarda va en un hilo aparte: si se hiciera aquí, la ventana
        dejaría de responder y el lector de pantalla no podría ni leer la barra
        de progreso, que es justo para lo que está.
        """
        self._trabajando = True
        self._cancelar = False
        self.boton_accion.Enable(False)
        self.boton_siguiente.Enable(False)
        self.boton_anterior.Enable(False)
        self._decir(_("%s. Pulsa Escape para cancelar.") % titulo)

        def trabajo():
            try:
                resultado = tarea()
                wx.CallAfter(self._terminado, resultado, "")
            except ollama.Cancelado:
                wx.CallAfter(self._terminado, "", _("Cancelado. Lo descargado se conserva."))
            except Exception as error:
                registrar_excepcion(log, "Fallo en el asistente de IA local", error)
                wx.CallAfter(self._terminado, "", str(error))

        threading.Thread(target=trabajo, name="asistente_ia", daemon=True).start()

    def _terminado(self, resultado: str, error: str) -> None:
        """Recoge el resultado de la tarea, ya en el hilo de la interfaz.

        Como el progreso, puede llegar con el diálogo ya cerrado: el trabajo
        termina —o se cancela— después de que el usuario haya salido.  Si ya no
        está, no hay nada que contarle aquí; lo hecho está hecho y el registro
        lo recoge.
        """
        self._trabajando = False
        if not self._vivo or not self:
            return
        self.boton_accion.Enable(True)
        self.boton_siguiente.Enable(True)
        self.boton_anterior.Enable(self.actual > 0)
        self.progreso.SetValue(0 if error else 100)
        if error:
            self._decir(error)
            wx.MessageBox(error, _("No se ha podido"), wx.OK | wx.ICON_WARNING, self)
            return
        self._decir(resultado or _("Hecho."))
        # Con el paso cumplido, lo natural es seguir: se deja el foco en
        # «Siguiente» para que baste con pulsar Intro.
        self.boton_siguiente.SetFocus()

    def _avanzar(self, porcentaje: int, mensaje: str) -> None:
        """Recibe el progreso desde el hilo de trabajo."""
        wx.CallAfter(self._pintar_progreso, porcentaje, mensaje)

    def _pintar_progreso(self, porcentaje: int, mensaje: str) -> None:
        """Mueve la barra y anuncia de vez en cuando.

        Lo primero es mirar si el diálogo sigue existiendo.  Esto llega por
        ``wx.CallAfter`` desde el hilo de trabajo, y entre que se encola y que
        se ejecuta el usuario puede haber cerrado la ventana: entonces los
        controles ya están destruidos y tocarlos revienta.  Un ``wx.Gauge``
        borrado da ``False`` al evaluarlo, que es como se pregunta esto.
        """
        if not self._vivo or not self or not self.progreso:
            return
        anterior = self.progreso.GetValue()
        self.progreso.SetValue(max(0, min(100, porcentaje)))
        self.estado.SetLabel(mensaje)
        if porcentaje // PASO_ANUNCIO != anterior // PASO_ANUNCIO:
            self.voz.decir(mensaje)

    def _parar(self) -> bool:
        """Si el usuario ha pedido cancelar."""
        return self._cancelar

    def _instalar_motor(self) -> str:
        """Descarga e instala Ollama portable."""
        version = self.gestor.instalar(self._avanzar, self._parar)
        self.hecho["motor"] = True
        return _("Motor instalado: Ollama %s.") % version

    def _instalar_modelo(self) -> str:
        """Arranca el servidor si hace falta y descarga el modelo elegido."""
        self._avanzar(0, _("Arrancando el servidor..."))
        self.gestor.iniciar()
        self.gestor.descargar_modelo(self.modelo_elegido, self._avanzar, self._parar)
        self.configuracion.establecer("ollama_modelo", self.modelo_elegido)
        self.configuracion.guardar()
        self.hecho["modelo"] = True
        return _("Modelo %s instalado y elegido.") % self.modelo_elegido

    def _probar(self) -> str:
        """Le hace una pregunta de verdad y devuelve lo que conteste."""
        from nucleo.ia.local import Local

        self._avanzar(10, _("Arrancando el servidor..."))
        self.gestor.iniciar()
        modelo = self.modelo_elegido or str(self.configuracion.obtener("ollama_modelo", ""))
        if not modelo:
            raise RuntimeError(_("Todavía no hay ningún modelo instalado."))
        self._avanzar(40, _("Cargando el modelo en memoria. Esto es lo que más tarda..."))
        cliente = Local(ollama.url_openai(), modelo, 300.0)
        respuesta = cliente.probar()
        self._avanzar(100, _("Ha contestado."))
        # Con la prueba superada se deja activada: es lo que el usuario venía a
        # conseguir, y hacérselo elegir después en otra pantalla sería pedirle
        # un paso más para nada.
        self.configuracion.establecer("ia_proveedor", "ollama_propio")
        self.configuracion.establecer("ollama_modelo", modelo)
        self.configuracion.guardar()
        self.hecho["prueba"] = True
        return _("Funciona. Ha respondido: %s") % respuesta[:200]

    # -- cierre ---------------------------------------------------------------

    def _al_cerrar(self, evento) -> None:
        """No deja salir con una descarga a medias sin avisar."""
        if self._trabajando:
            respuesta = wx.MessageBox(
                _("Hay una descarga en marcha.\n\n¿Quieres cancelarla y salir? Lo "
                  "descargado se conserva y la próxima vez sigue desde ahí."),
                _("Salir del asistente"), wx.YES_NO | wx.ICON_QUESTION, self)
            if respuesta != wx.YES:
                evento.Veto()
                return
            self._cancelar = True
        # A partir de aquí los controles se van a destruir: lo que el hilo
        # mande desde ahora se descarta en vez de estrellarse contra ellos.
        self._vivo = False
        evento.Skip()


def hace_falta(configuracion) -> bool:
    """Indica si merece la pena ofrecer el asistente.

    Se ofrece cuando no hay motor instalado: quien ya lo tiene no necesita que
    se lo propongan otra vez, y quien usa un proveedor de internet puede querer
    montarlo igual, así que no se mira el proveedor.
    """
    return not ollama.instalado()
