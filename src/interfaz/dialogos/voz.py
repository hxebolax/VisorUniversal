# -*- coding: utf-8 -*-
"""Lectura en voz alta: la ventana donde se ajusta todo lo que suena.

Antes esto era **una sola columna con trece ajustes seguidos**. Con la vista se
recorre de un vistazo; de oído hay que atravesarla entera con la flecha abajo
para llegar al último, y cada vez que se abre se vuelve a atravesar. Ahora va en
pestañas, que es lo que un lector de pantalla anuncia por su nombre y entre las
que se salta con Control+Tabulador:

* **Voz**: cuál habla, a qué velocidad y a qué volumen. Es lo que se toca a
  diario, así que va primero y es la que se abre.
* **Motores de voz**: qué programa pone la voz. Aquí se añaden y se quitan.
* **Al leer**: qué hace la ventana mientras suena —el cursor, el resaltado—.
* **Qué se dice**: lo que se lee y lo que se calla —las notas, los folios, las
  fórmulas químicas—.
* **Diálogos**: el cambio de tono en las novelas.

La pestaña de los motores
-------------------------

El programa lee con la voz que trae Windows, y para muchas cosas basta. Para
escuchar un libro entero no siempre: quien lleva treinta años oyendo Eloquence
la entiende al doble de velocidad que cualquier otra, y quien quiere una novela
bien leída prefiere una voz neuronal. Ninguna de las dos se puede meter dentro
del programa —una no se puede distribuir y la otra son cientos de megas—, así
que se instalan como paquete.

Lo que se puede ajustar de cada motor **lo dice el motor**, no esta ventana:
llega en su manifiesto y aquí se pinta. Por eso añadir un motor nuevo no obliga
a tocar este archivo, y por eso cada ajuste trae su explicación de Control+F1
escrita por quien hizo el paquete, que es quien sabe qué hace.
"""

from __future__ import annotations

import wx

from interfaz import ayuda_control
from interfaz.accesible import etiquetar, fila_etiquetada
from interfaz.dialogos import ayuda_opcion
from nucleo import motores_voz, paquetes_voz, quimica
from nucleo.idioma import _
from nucleo.registro import obtener_registro, registrar_excepcion
from nucleo.voz import RAPIDEZ_NORMAL, sapi_desde_porcentaje

log = obtener_registro(__name__)

#: Margen alrededor de los controles.
MARGEN = 8

#: Clave donde se guarda qué motor está elegido.
CLAVE_MOTOR = "voz_motor"

#: Y dónde se guardan los ajustes propios de cada uno, por identificador.  Van
#: todos juntos en un diccionario y no en claves sueltas para que desinstalar un
#: motor y volver a instalarlo recupere lo que tenía puesto: quien configuró la
#: variante de voz y la frecuencia de Eloquence no quiere volver a hacerlo.
CLAVE_AJUSTES = "voz_ajustes_motores"

#: Con qué nombre viven dentro de la ventana los controles de los ajustes del
#: motor.  Hace falta un prefijo fijo para poder quitarlos todos al cambiar de
#: motor sin tocar los demás.
PREFIJO_AJUSTE = "ajuste_motor_"


class DialogoVoz(wx.Dialog):
    # Nota: esta ventana ajusta **la voz sintética**, la que lee los documentos
    # que no traen grabación.  La velocidad de las grabaciones DAISY es otra
    # cosa y vive en Opciones, en su propia pestaña.
    """Ajustes de la lectura en voz alta, repartidos en pestañas.

    Deja probar la voz sin cerrar la ventana, que es la única forma de elegir
    entre varias sin verlas: se escuchan y se decide. Y deja probar **un motor
    que todavía no está puesto**, que es lo mismo un escalón más arriba.

    :param lector: Lector en voz alta, para probar con los ajustes de verdad.
    """

    #: Frase que se lee al pulsar «Probar».  Lleva números y signos a propósito:
    #: es donde más se nota la diferencia entre unas voces y otras.
    PRUEBA = (_("Esta es la voz que leerá tus libros. En el capítulo 3, página 145, "
              "el protagonista dijo: «no hay tiempo que perder»."))

    def __init__(self, padre, lector) -> None:
        super().__init__(padre, title=_("Lectura en voz alta"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.lector = lector
        self.configuracion = padre.configuracion

        #: Motor que está elegido **en la ventana**, que puede no ser el que
        #: está sonando: hasta que no se acepta, no se cambia nada.
        self._motor_elegido = str(
            self.configuracion.obtener(CLAVE_MOTOR, motores_voz.SAPI5))
        #: Ajustes de cada motor tal como se van tocando aquí.
        self._ajustes = dict(self.configuracion.obtener(CLAVE_AJUSTES, {}) or {})
        #: Sintetizador con el que se prueba.  Cuando el motor elegido es el que
        #: ya está sonando se reutiliza el del lector; si no, se crea uno aparte
        #: y se cierra al salir.
        self._prueba = None
        self._prueba_propia = False
        #: Controles de los ajustes del motor, por clave.
        self._controles_motor: dict = {}
        #: Las opciones con las que se pintó cada lista.  Pueden ser las del
        #: manifiesto o las que haya dicho el motor, y hay que leer lo elegido
        #: de la misma lista con la que se pintó.
        self._opciones_pintadas: dict = {}

        contenedor = wx.BoxSizer(wx.VERTICAL)
        # El cuaderno NO lleva nombre forzado: el lector de pantalla anuncia el
        # de la pestaña seleccionada, y ponerle uno propio lo sustituiría.
        self.cuaderno = wx.Notebook(self)
        self.cuaderno.AddPage(self._pagina_voz(), _("Voz"))
        self.cuaderno.AddPage(self._pagina_motores(), _("Motores de voz"))
        self.cuaderno.AddPage(self._pagina_al_leer(), _("Al leer"))
        self.cuaderno.AddPage(self._pagina_que_se_dice(), _("Qué se dice"))
        self.cuaderno.AddPage(self._pagina_dialogos(), _("Diálogos"))
        contenedor.Add(self.cuaderno, 1, wx.EXPAND | wx.ALL, MARGEN)

        fila = wx.StdDialogButtonSizer()
        aceptar = wx.Button(self, wx.ID_OK, _("&Aceptar"))
        aceptar.SetDefault()
        fila.AddButton(aceptar)
        fila.AddButton(wx.Button(self, wx.ID_CANCEL, _("&Cancelar")))
        fila.Realize()
        contenedor.Add(fila, 0, wx.EXPAND | wx.ALL, MARGEN)
        self.SetSizerAndFit(contenedor)

        self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)
        self.Bind(wx.EVT_CLOSE, self._al_cerrar)
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)
        self.cuaderno.SetFocus()

    # -- pestaña: voz --------------------------------------------------------

    def _pagina_voz(self) -> wx.Panel:
        """La voz concreta, la velocidad y el volumen: lo de cada día."""
        panel = wx.Panel(self.cuaderno)
        caja = wx.BoxSizer(wx.VERTICAL)

        self.motor_actual = wx.StaticText(panel, label="")
        caja.Add(self.motor_actual, 0, wx.ALL, MARGEN)

        self.voces = fila_etiquetada(
            panel, caja, _("&Voz:"), lambda p: wx.Choice(p, choices=[]),
            margen=MARGEN, horizontal=True, proporcion=1)
        self.sin_voces = wx.StaticText(panel, label="")
        caja.Add(self.sin_voces, 0, wx.ALL, MARGEN)

        self.velocidad, self.etiqueta_velocidad = self._deslizador(
            panel, caja, _("V&elocidad de lectura, de 0 a 100 (50 es la normal):"),
            _("Velocidad de lectura"),
            int(self.configuracion.obtener("voz_rapidez", RAPIDEZ_NORMAL)))
        self.volumen, self.etiqueta_volumen = self._deslizador(
            panel, caja, _("V&olumen de la voz, de 0 a 100:"),
            _("Volumen de la voz"),
            int(self.configuracion.obtener("voz_volumen", 100)))

        self.seguir_idioma = wx.CheckBox(
            panel, label=_("Cambiar de voz cuando el documento cambia de &idioma"))
        self.seguir_idioma.SetValue(
            bool(self.configuracion.obtener("voz_seguir_idioma", True)))
        caja.Add(self.seguir_idioma, 0, wx.ALL, MARGEN)
        caja.Add(wx.StaticText(panel, label=(
            _("Los documentos accesibles —un EPUB bien hecho, un PDF etiquetado— dicen en qué\n"
            "idioma está cada fragmento. Con esto marcado, al llegar a una cita en inglés se\n"
            "lee con una voz inglesa, si la tienes instalada, y se vuelve a la tuya al salir.")
        )), 0, wx.ALL, MARGEN)

        self.boton_probar = etiquetar(wx.Button(panel, label=_("&Probar la voz")),
                                      _("Probar la voz"))
        caja.Add(self.boton_probar, 0, wx.ALL, MARGEN)
        self.boton_probar.Bind(wx.EVT_BUTTON, self._al_probar)

        panel.SetSizer(caja)
        self._refrescar_voces()
        return panel

    # -- pestaña: motores ----------------------------------------------------

    def _pagina_motores(self) -> wx.Panel:
        """Qué programa pone la voz, y sus ajustes propios."""
        panel = wx.Panel(self.cuaderno)
        caja = wx.BoxSizer(wx.VERTICAL)
        caja.Add(wx.StaticText(panel, label=(
            _("El programa lee con la voz que trae Windows, que está siempre y arranca al\n"
              "instante. Se pueden añadir otros motores como paquete: cada uno trae sus\n"
              "voces y sus ajustes, y se instala y se quita desde aquí sin tocar el sistema.")
        )), 0, wx.ALL, MARGEN)

        self.motores = fila_etiquetada(
            panel, caja, _("&Motor de voz:"), lambda p: wx.Choice(p, choices=[]),
            margen=MARGEN, horizontal=True, proporcion=1)
        self.motores.Bind(wx.EVT_CHOICE, self._al_cambiar_motor)

        self.descripcion_motor = wx.StaticText(panel, label="")
        caja.Add(self.descripcion_motor, 0, wx.EXPAND | wx.ALL, MARGEN)

        fila = wx.BoxSizer(wx.HORIZONTAL)
        self.boton_motores = etiquetar(
            wx.Button(panel, label=_("&Agregar o quitar motores...")),
            _("Agregar o quitar motores de voz"))
        fila.Add(self.boton_motores, 0, wx.RIGHT, MARGEN)
        self.boton_motores.Bind(wx.EVT_BUTTON, self._al_menu_motores)
        # El mismo botón que en la pestaña «Voz», aquí también: se ajusta un
        # motor tocando lo suyo y escuchando, y mandar a la otra pestaña a cada
        # cambio convierte eso en un viaje de ida y vuelta por ajuste.
        self.boton_probar_motor = etiquetar(
            wx.Button(panel, label=_("Probar &este motor")),
            _("Probar la voz"))
        fila.Add(self.boton_probar_motor, 0)
        self.boton_probar_motor.Bind(wx.EVT_BUTTON, self._al_probar)
        caja.Add(fila, 0, wx.ALL, MARGEN)

        # Los ajustes propios del motor viven en su propio panel, que se vacía y
        # se vuelve a llenar al cambiar de motor: cada uno tiene los suyos y no
        # se parecen en nada.
        #
        # Se desplaza porque la cantidad la decide el motor y no hay tope: los
        # trece de Eloquence no caben en una pantalla baja por mucho que crezca
        # la ventana.  Así se llega a todos con el tabulador, que es como se
        # recorre esta ventana cuando no se ve.
        self.panel_ajustes = wx.ScrolledWindow(
            panel, style=wx.TAB_TRAVERSAL | wx.VSCROLL,
            name=_("Ajustes del motor de voz"))
        self.panel_ajustes.SetScrollRate(0, 10)
        self.caja_ajustes = wx.BoxSizer(wx.VERTICAL)
        self.panel_ajustes.SetSizer(self.caja_ajustes)
        caja.Add(self.panel_ajustes, 1, wx.EXPAND | wx.ALL, MARGEN)

        panel.SetSizer(caja)
        self._refrescar_motores()
        return panel

    # -- pestaña: al leer ----------------------------------------------------

    def _pagina_al_leer(self) -> wx.Panel:
        """Qué hace la ventana mientras la voz suena."""
        panel = wx.Panel(self.cuaderno)
        caja = wx.BoxSizer(wx.VERTICAL)

        self.mover = wx.CheckBox(
            panel, label=_("&Mover el cursor a la vez que se lee"))
        self.mover.SetValue(bool(self.configuracion.obtener("voz_mover_cursor", False)))
        caja.Add(self.mover, 0, wx.ALL, MARGEN)
        caja.Add(wx.StaticText(panel, label=(
            _("Viene desactivado porque, con el lector de pantalla en marcha, mover el cursor\n"
            "hace que este lea también la línea y se oigan dos voces a la vez. Actívalo si\n"
            "sigues la lectura en una línea braille. Al pausar o detener, el cursor se coloca\n"
            "de todas formas en la frase donde iba la lectura.")
        )), 0, wx.ALL, MARGEN)

        self._sitios_al_parar = (
            ("inicio", _("Al principio de la frase que se estaba diciendo")),
            ("fin", _("Justo detrás de esa frase, por donde sigue el texto")),
        )
        self.cursor_al_parar = fila_etiquetada(
            panel, caja, _("Al &pausar o detener, dejar el cursor:"),
            lambda p: wx.Choice(p, choices=[rotulo for _clave, rotulo
                                            in self._sitios_al_parar]),
            margen=MARGEN, horizontal=True, proporcion=1)
        guardado = str(self.configuracion.obtener("voz_cursor_al_parar", "inicio"))
        claves = [clave for clave, _rotulo in self._sitios_al_parar]
        self.cursor_al_parar.SetSelection(
            claves.index(guardado) if guardado in claves else 0)
        caja.Add(wx.StaticText(panel, label=(
            _("Al principio de la frase es lo de siempre, y es lo que conviene cuando paras\n"
            "porque algo no se ha entendido: la flecha arriba vuelve a leer justo eso.\n"
            "\n"
            "Detrás de la frase es lo que conviene cuando paras para seguir leyendo a mano:\n"
            "las flechas continúan por lo que aún no ha sonado, en vez de repetirte el\n"
            "párrafo que acabas de oír. Volver a dar a leer sigue retomando donde estaba.")
        )), 0, wx.ALL, MARGEN)

        self.resaltar = wx.CheckBox(
            panel, label=_("&Resaltar la frase que se está leyendo"))
        self.resaltar.SetValue(
            bool(self.configuracion.obtener("voz_resaltar_frase", False)))
        caja.Add(self.resaltar, 0, wx.ALL, MARGEN)
        caja.Add(wx.StaticText(panel, label=(
            _("Pinta con fondo de color la frase que suena, para seguirla con la vista si\n"
            "conservas resto visual. No mueve el cursor, así que no interfiere con el lector\n"
            "de pantalla: se puede tener activado a la vez que se escucha.")
        )), 0, wx.ALL, MARGEN)

        panel.SetSizer(caja)
        return panel

    # -- pestaña: qué se dice ------------------------------------------------

    def _pagina_que_se_dice(self) -> wx.Panel:
        """Lo que se lee y lo que se calla."""
        panel = wx.Panel(self.cuaderno)
        caja = wx.BoxSizer(wx.VERTICAL)

        self.descripciones = wx.CheckBox(
            panel, label=_("Leer también la &descripción de las imágenes"))
        self.descripciones.SetValue(
            bool(self.configuracion.obtener("voz_leer_descripciones", False)))
        caja.Add(self.descripciones, 0, wx.ALL, MARGEN)
        caja.Add(wx.StaticText(panel, label=(
            _("En el texto una ilustración es solo «[Imagen: Logo]», que no cuenta nada. Con\n"
            "esto marcado, al llegar ahí la lectura sigue con la descripción que le hicieras\n"
            "con inteligencia artificial (Herramientas → Describir la imagen con IA, o la\n"
            "tecla A). Las imágenes sin describir se leen igual que ahora.")
        )), 0, wx.ALL, MARGEN)

        self._modos_quimica = quimica.modos()
        self.quimica = fila_etiquetada(
            panel, caja, _("&Fórmulas químicas:"),
            lambda p: wx.Choice(p, choices=[texto for _clave, texto
                                            in self._modos_quimica]),
            margen=MARGEN, horizontal=True, proporcion=1)
        guardado = str(self.configuracion.obtener("voz_quimica", "auto"))
        claves = [clave for clave, _texto in self._modos_quimica]
        self.quimica.SetSelection(claves.index(guardado) if guardado in claves else 0)
        caja.Add(wx.StaticText(panel, label=(
            _("Una fórmula como H2SO4 se lee «hache dos ese o cuatro», que no se entiende\n"
            "y además confunde la letra O con el número cero. Con esto se dice «hidrógeno 2\n"
            "azufre oxígeno 4», que es como lo dicta un profesor.")
        )), 0, wx.ALL, MARGEN)

        caja.Add(wx.StaticText(panel, label=_("QUÉ NO SE DICE AL LEER DE CORRIDO")),
                 0, wx.LEFT | wx.RIGHT | wx.TOP, MARGEN)
        caja.Add(wx.StaticText(panel, label=(
            _("Con la vista, el ojo se salta solo la cabecera repetida de cada página, el\n"
            "número de página del pie y el numerito volado de una nota. De oído suena todo,\n"
            "y suena en medio de la frase. Esto no cambia el libro: solo lo que dice la voz.")
        )), 0, wx.ALL, MARGEN)
        self.saltar_notas = wx.CheckBox(
            panel, label=_("No decir las llamadas de &nota al pie"))
        self.saltar_notas.SetValue(
            bool(self.configuracion.obtener("voz_saltar_notas", False)))
        caja.Add(self.saltar_notas, 0, wx.LEFT | wx.RIGHT, MARGEN)
        self.saltar_folios = wx.CheckBox(
            panel, label=_("No decir los nú&meros de página sueltos"))
        self.saltar_folios.SetValue(
            bool(self.configuracion.obtener("voz_saltar_folios", False)))
        caja.Add(self.saltar_folios, 0, wx.LEFT | wx.RIGHT, MARGEN)
        self.saltar_cabeceras = wx.CheckBox(
            panel, label=_("No decir las &cabeceras y los pies que se repiten en "
                           "cada página"))
        self.saltar_cabeceras.SetValue(
            bool(self.configuracion.obtener("voz_saltar_cabeceras", False)))
        caja.Add(self.saltar_cabeceras, 0, wx.ALL, MARGEN)

        panel.SetSizer(caja)
        return panel

    # -- pestaña: diálogos ---------------------------------------------------

    def _pagina_dialogos(self) -> wx.Panel:
        """El cambio de tono en las novelas."""
        panel = wx.Panel(self.cuaderno)
        caja = wx.BoxSizer(wx.VERTICAL)

        self.dialogos = wx.CheckBox(
            panel, label=_("Cambiar de tono en los &diálogos"))
        self.dialogos.SetValue(bool(self.configuracion.obtener(
            "voz_modo_dialogo", False)))
        caja.Add(self.dialogos, 0, wx.ALL, MARGEN)
        caja.Add(wx.StaticText(panel, label=(
            _("En una novela con mucho diálogo, oírlo todo con la misma voz obliga a\n"
              "reconstruir sobre la marcha quién dice cada cosa: quien lee con los ojos ve\n"
              "las rayas en el margen, y de oído no están. Con esto, lo que dice un\n"
              "personaje suena un poco más agudo que la narración.")
        )), 0, wx.ALL, MARGEN)

        self.tono_dialogo = fila_etiquetada(
            panel, caja, _("C&uánto cambia el tono, de 1 a 10:"),
            lambda p: wx.SpinCtrl(p, min=1, max=10, initial=int(
                self.configuracion.obtener("voz_tono_dialogo", 4) or 4)),
            margen=MARGEN, horizontal=True)

        caja.Add(wx.StaticText(panel, label=(
            _("No todos los motores saben cambiar de tono. Los que no, leen el diálogo con\n"
              "la voz de siempre y no pasa nada más: no se pierde ni una palabra.")
        )), 0, wx.ALL, MARGEN)

        panel.SetSizer(caja)
        return panel

    # -- ayudantes de construcción -------------------------------------------

    def _deslizador(self, panel, contenedor, etiqueta: str, nombre: str, valor: int):
        """Crea un deslizador de 0 a 100 con su etiqueta y su valor al lado.

        Dos detalles comprobados en este proyecto: el estilo ``wx.SL_LABELS``
        hace que Windows tome el número como nombre del control (se anunciaría
        «70» en lugar de «Volumen de la voz»), y el texto estático tiene que
        crearse **antes** que el deslizador para que Windows los relacione.
        """
        contenedor.Add(wx.StaticText(panel, label=etiqueta), 0,
                       wx.LEFT | wx.RIGHT | wx.TOP, MARGEN)
        fila = wx.BoxSizer(wx.HORIZONTAL)
        control = wx.Slider(panel, value=valor, minValue=0, maxValue=100,
                            style=wx.SL_HORIZONTAL, name=nombre)
        fila.Add(control, 1, wx.EXPAND | wx.RIGHT, MARGEN)
        numero = wx.StaticText(panel, label="%d %%" % valor)
        fila.Add(numero, 0, wx.ALIGN_CENTER_VERTICAL)
        contenedor.Add(fila, 0, wx.EXPAND | wx.ALL, MARGEN)
        control.Bind(wx.EVT_SLIDER,
                     lambda evento: numero.SetLabel("%d %%" % control.GetValue()))
        return control, numero

    # -- motores -------------------------------------------------------------

    def _catalogo(self) -> list:
        if not hasattr(self, "_motores_cache") or self._motores_cache is None:
            self._motores_cache = motores_voz.catalogo()
        return self._motores_cache

    def _refrescar_motores(self) -> None:
        """Rellena la lista de motores y deja elegido el que toca."""
        self._motores_cache = None
        catalogo = self._catalogo()
        self.motores.Set([motor.nombre for motor in catalogo])
        identificadores = [motor.identificador for motor in catalogo]
        if self._motor_elegido not in identificadores:
            # El motor guardado ya no está: se ha desinstalado, o el paquete se
            # ha borrado a mano.  Se vuelve al de siempre sin decir nada aquí,
            # porque al leer ya se dijo.
            self._motor_elegido = motores_voz.SAPI5
        self.motores.SetSelection(identificadores.index(self._motor_elegido))
        self._pintar_ajustes_del_motor()

    def _motor(self):
        """El motor elegido ahora mismo en la ventana."""
        for motor in self._catalogo():
            if motor.identificador == self._motor_elegido:
                return motor
        return motores_voz.motor_sapi5()

    def _pintar_ajustes_del_motor(self) -> None:
        """Rehace los controles de los ajustes propios del motor elegido.

        Se vacía y se vuelve a llenar entero. Es más simple que ir cambiando
        controles uno a uno, y aquí pasa una vez cada vez que alguien cambia de
        motor: no hay nada que optimizar.
        """
        motor = self._motor()
        self.descripcion_motor.SetLabel(motor.descripcion)
        # Fuera los controles anteriores, sus nombres dentro de la ventana y sus
        # explicaciones: son los de otro motor y ya no están en la pantalla.
        for nombre in [n for n in vars(self) if n.startswith(PREFIJO_AJUSTE)]:
            delattr(self, nombre)
        ayuda_control.olvidar_anadidas("DialogoVoz." + PREFIJO_AJUSTE)
        self.panel_ajustes.DestroyChildren()
        self.caja_ajustes.Clear()
        self._controles_motor = {}
        self._opciones_pintadas = {}
        guardados = dict(self._ajustes.get(motor.identificador, {}))

        if not motor.ajustes:
            self.caja_ajustes.Add(wx.StaticText(self.panel_ajustes, label=_(
                "Este motor no tiene ajustes propios: la voz, la velocidad y el "
                "volumen se ponen en la pestaña «Voz».")), 0, wx.ALL, MARGEN)
        for ajuste in motor.ajustes:
            valor = ajuste.valor_valido(guardados.get(ajuste.clave, ajuste.defecto))
            control = self._control_de(ajuste, valor)
            if control is not None:
                self._controles_motor[ajuste.clave] = (ajuste, control)
        self.panel_ajustes.Layout()
        self.panel_ajustes.FitInside()
        self.Layout()
        self._crecer_para_los_ajustes()

    def _crecer_para_los_ajustes(self) -> None:
        """Agranda la ventana si los ajustes del motor no caben.

        Solo crece, y solo hasta lo que quepa en la pantalla.  Nunca encoge: si
        alguien ha agrandado la ventana a mano, o viene de un motor con más
        ajustes, dejarla como está molesta menos que moverla, y con lector de
        pantalla mucho menos, porque el tamaño de la ventana no se ve pero el
        salto del foco se nota.
        """
        falta = (self.caja_ajustes.GetMinSize().height
                 - self.panel_ajustes.GetSize().height)
        if falta <= 0:
            return
        pantalla = wx.Display(
            max(0, wx.Display.GetFromWindow(self))).GetClientArea()
        ancho, alto = self.GetSize()
        nuevo = min(alto + falta + MARGEN * 2, pantalla.height)
        if nuevo <= alto:
            return
        self.SetSize(ancho, nuevo)
        self.Layout()
        # Si la ventana se ha ido por debajo del borde de la pantalla al crecer,
        # se vuelve a subir: una ventana con los botones fuera no se acepta.
        x, y = self.GetPosition()
        if y + nuevo > pantalla.y + pantalla.height:
            self.SetPosition(wx.Point(x, max(pantalla.y,
                                             pantalla.y + pantalla.height - nuevo)))

    def _opciones_de(self, ajuste) -> list:
        """Las opciones de un ajuste de lista: las de verdad si el motor las sabe.

        El manifiesto es fijo y hay ajustes que no lo son. Las calidades de voz
        de Vocalizer dependen de las voces que se hayan copiado, y esas se
        copian después de armar el paquete: si el motor sabe cuáles hay, manda
        él.

        Si el motor no está construido —porque no ha podido arrancar— se usan
        las del manifiesto, que es lo que había antes.
        """
        declaradas = list(ajuste.opciones)
        motor = self._prueba if self._prueba is not None else getattr(
            self.lector, "sintetizador", None)
        preguntar = getattr(motor, "opciones_de", None)
        if not callable(preguntar):
            return declaradas
        try:
            suyas = preguntar(ajuste.clave)
        except Exception as error:
            log.debug("El motor no ha podido decir sus opciones: %s", error)
            return declaradas
        if not suyas:
            return declaradas
        return [(valor, str(texto)) for valor, texto in suyas]

    def _control_de(self, ajuste, valor):
        """Crea el control de un ajuste declarado por el motor.

        El nombre del control se registra además en la ayuda de Control+F1, con
        la explicación que trae el propio paquete: en este programa **todo
        control se explica**, y un motor que se añade no es una excepción.
        """
        panel, caja = self.panel_ajustes, self.caja_ajustes
        control = None
        if ajuste.clase == "lista":
            opciones = self._opciones_de(ajuste)
            textos = [texto for _valor, texto in opciones]
            control = fila_etiquetada(panel, caja, ajuste.etiqueta,
                                      lambda p: wx.Choice(p, choices=textos),
                                      margen=MARGEN, horizontal=True, proporcion=1)
            posibles = [posible for posible, _texto in opciones]
            control.SetSelection(posibles.index(valor) if valor in posibles else 0)
            # Se guardan las que se han pintado: al leer lo elegido hay que
            # mirar en la misma lista, no en la del manifiesto.
            self._opciones_pintadas[ajuste.clave] = opciones
        elif ajuste.clase == "deslizador":
            caja.Add(wx.StaticText(panel, label=ajuste.etiqueta), 0,
                     wx.LEFT | wx.RIGHT | wx.TOP, MARGEN)
            fila = wx.BoxSizer(wx.HORIZONTAL)
            control = wx.Slider(panel, value=int(valor), minValue=ajuste.minimo,
                                maxValue=ajuste.maximo, style=wx.SL_HORIZONTAL,
                                name=ajuste.etiqueta.replace("&", ""))
            fila.Add(control, 1, wx.EXPAND | wx.RIGHT, MARGEN)
            numero = wx.StaticText(panel, label=str(valor))
            fila.Add(numero, 0, wx.ALIGN_CENTER_VERTICAL)
            caja.Add(fila, 0, wx.EXPAND | wx.ALL, MARGEN)
            control.Bind(wx.EVT_SLIDER,
                         lambda evento, c=control, n=numero:
                         n.SetLabel(str(c.GetValue())))
        elif ajuste.clase == "casilla":
            control = wx.CheckBox(panel, label=ajuste.etiqueta)
            control.SetValue(bool(valor))
            caja.Add(control, 0, wx.ALL, MARGEN)
        elif ajuste.clase == "texto":
            control = fila_etiquetada(panel, caja, ajuste.etiqueta,
                                      lambda p: wx.TextCtrl(p),
                                      margen=MARGEN, horizontal=True, proporcion=1)
            control.SetValue(str(valor or ""))
        if control is not None:
            # El control se guarda con un nombre dentro de la ventana y su
            # explicación se registra con ese mismo nombre: es así como
            # Control+F1 sabe qué contestar sobre él.
            nombre = PREFIJO_AJUSTE + ajuste.clave
            setattr(self, nombre, control)
            ayuda_control.registrar("DialogoVoz." + nombre,
                                    ajuste.etiqueta.replace("&", ""), ajuste.ayuda)
        return control

    def _valores_del_motor(self) -> dict:
        """Lo que hay ahora en los controles del motor elegido."""
        salida = {}
        for clave, (ajuste, control) in self._controles_motor.items():
            if ajuste.clase == "lista":
                posicion = max(0, control.GetSelection())
                # En la lista que se pintó, que puede ser la del motor y no la
                # del manifiesto.
                opciones = self._opciones_pintadas.get(clave, ajuste.opciones)
                if posicion < len(opciones):
                    salida[clave] = opciones[posicion][0]
            elif ajuste.clase == "deslizador":
                salida[clave] = int(control.GetValue())
            elif ajuste.clase == "casilla":
                salida[clave] = bool(control.GetValue())
            else:
                salida[clave] = control.GetValue()
        return salida

    def _guardar_valores_del_motor(self) -> None:
        """Se queda con lo que hay puesto antes de cambiar de motor."""
        if self._controles_motor:
            self._ajustes[self._motor_elegido] = self._valores_del_motor()

    def _al_cambiar_motor(self, evento) -> None:
        """Cambia de motor: guarda lo del anterior y prepara el nuevo."""
        self._guardar_valores_del_motor()
        catalogo = self._catalogo()
        posicion = max(0, self.motores.GetSelection())
        if posicion >= len(catalogo):
            return
        self._motor_elegido = catalogo[posicion].identificador
        # El motor se construye **antes** de pintar sus ajustes: hay listas que
        # solo él sabe llenar de verdad —las calidades de voz de Vocalizer
        # dependen de las voces que haya copiadas— y pintarlas antes las dejaría
        # con lo que dice el manifiesto, que puede ofrecer cosas que no están.
        self._soltar_prueba()
        self._refrescar_voces()
        self._pintar_ajustes_del_motor()

    # -- agregar y quitar ----------------------------------------------------

    def _al_menu_motores(self, evento) -> None:
        """Abre el menú de agregar y quitar, junto al botón.

        Es un menú y no dos botones porque son dos órdenes que se usan una vez
        en la vida: ocupar con ellas la ventana entera, que es la que se abre
        cada vez que alguien quiere subir la velocidad, sería ponerlas de por
        medio todos los días para usarlas una.
        """
        menu = wx.Menu()
        agregar = menu.Append(wx.ID_ANY, _("&Agregar motor de voz..."))
        quitar = menu.Append(wx.ID_ANY, _("&Quitar motor de voz..."))
        # La voz de Windows no se quita: es la que queda cuando todo falla.
        quitar.Enable(bool(motores_voz.instalados()))
        self.Bind(wx.EVT_MENU, self._al_agregar, agregar)
        self.Bind(wx.EVT_MENU, self._al_quitar, quitar)
        self.boton_motores.PopupMenu(menu)
        menu.Destroy()

    def _al_agregar(self, evento) -> None:
        """Pide un paquete, lo enseña y lo instala si se confirma."""
        carpeta = paquetes_voz.carpeta_de_paquetes()
        with wx.FileDialog(
                self, _("Elige el paquete del motor de voz"),
                defaultDir=str(carpeta) if carpeta.is_dir() else "",
                wildcard=paquetes_voz.FILTRO,
                style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                return
            ruta = dialogo.GetPath()
        try:
            ficha = paquetes_voz.examinar(ruta)
        except paquetes_voz.ErrorPaquete as error:
            wx.MessageBox(str(error), _("No se puede instalar"),
                          wx.OK | wx.ICON_ERROR, self)
            return
        # Se enseña **antes** qué es y de dónde sale: un paquete trae código que
        # se va a ejecutar, y quien lo instala tiene derecho a saber qué acepta.
        pregunta = _("¿Instalar este motor de voz?\n\n%s") % ficha.resumen()
        if wx.MessageBox(pregunta, _("Agregar motor de voz"),
                         wx.YES_NO | wx.ICON_QUESTION, self) != wx.YES:
            return
        espera = wx.BusyCursor()
        try:
            motor = paquetes_voz.instalar(ruta)
        except paquetes_voz.ErrorPaquete as error:
            del espera
            wx.MessageBox(str(error), _("No se puede instalar"),
                          wx.OK | wx.ICON_ERROR, self)
            return
        except Exception as error:
            del espera
            registrar_excepcion(log, "Instalando un motor de voz", error)
            wx.MessageBox(_("No se ha podido instalar: %s") % error,
                          _("No se puede instalar"), wx.OK | wx.ICON_ERROR, self)
            return
        del espera
        # Queda elegido: quien acaba de instalar un motor lo ha hecho para
        # usarlo, y obligarle a buscarlo después en la lista sería absurdo.
        self._motor_elegido = motor.identificador
        self._refrescar_motores()
        self._soltar_prueba()
        self._refrescar_voces()
        if getattr(motor, "reiniciar", False):
            # El motor ya estaba en uso y sus bibliotecas siguen cargadas: hasta
            # que el programa se cierre y se abra, este motor no puede hablar.
            # Se dice aquí, que es cuando aún se puede hacer algo, y no cuando
            # se pulse «Probar» y no suene.
            log.warning("«%s» necesita reiniciar el programa", motor.nombre)
            wx.MessageBox(
                _("«%s» está instalado, pero ya lo estabas usando y sus "
                  "archivos siguen abiertos.\n\nCierra el programa y vuelve a "
                  "abrirlo: hasta entonces esas voces no van a sonar.")
                % motor.nombre,
                _("Hay que reiniciar el programa"),
                wx.OK | wx.ICON_WARNING, self)
            return
        wx.MessageBox(
            _("«%s» está instalado y ya es el motor elegido. Pruébalo con el "
              "botón «Probar la voz» de la pestaña «Voz».") % motor.nombre,
            _("Motor de voz agregado"), wx.OK | wx.ICON_INFORMATION, self)

    def _al_quitar(self, evento) -> None:
        """Desinstala un motor y deja puesta la voz de Windows."""
        instalados = motores_voz.instalados()
        if not instalados:
            wx.MessageBox(
                _("No hay ningún motor añadido. La voz de Windows viene con el "
                  "programa y no se puede quitar: es la que queda cuando "
                  "cualquier otra falla."),
                _("Quitar motor de voz"), wx.OK | wx.ICON_INFORMATION, self)
            return
        nombres = [motor.nombre for motor in instalados]
        with wx.SingleChoiceDialog(
                self, _("¿Qué motor de voz quieres quitar?"),
                _("Quitar motor de voz"), nombres) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                return
            elegido = instalados[dialogo.GetSelection()]
        pregunta = _("Se va a quitar «%s» y sus archivos. Los ajustes que "
                     "tengas puestos se conservan por si vuelves a "
                     "instalarlo.\n\n¿Seguro?") % elegido.nombre
        if wx.MessageBox(pregunta, _("Quitar motor de voz"),
                         wx.YES_NO | wx.ICON_WARNING, self) != wx.YES:
            return
        if self._motor_elegido == elegido.identificador:
            self._soltar_prueba()
        try:
            paquetes_voz.quitar(elegido.identificador)
        except paquetes_voz.ErrorPaquete as error:
            wx.MessageBox(str(error), _("No se puede quitar"),
                          wx.OK | wx.ICON_ERROR, self)
            return
        if self._motor_elegido == elegido.identificador:
            self._motor_elegido = motores_voz.SAPI5
        self._refrescar_motores()
        self._refrescar_voces()
        wx.MessageBox(
            _("«%s» ya no está. Queda puesta la voz de Windows.") % elegido.nombre,
            _("Motor de voz quitado"), wx.OK | wx.ICON_INFORMATION, self)

    # -- la prueba -----------------------------------------------------------

    def _sintetizador(self):
        """El sintetizador con el que probar lo que hay elegido ahora.

        Cuando el motor elegido es el que ya está sonando se usa **ese**, para
        no arrancar dos veces algo que puede tardar segundos y que puede no
        dejarse arrancar dos veces —una voz que abre un proceso aparte, por
        ejemplo—.  Si es otro, se arranca uno aparte y se cierra al salir.
        """
        activo = str(self.configuracion.obtener(CLAVE_MOTOR, motores_voz.SAPI5))
        if self._motor_elegido == activo:
            return self.lector.sintetizador
        if self._prueba is None:
            self._guardar_valores_del_motor()
            espera = wx.BusyCursor()
            try:
                self._prueba, aviso = motores_voz.crear(
                    self._motor_elegido,
                    self._ajustes.get(self._motor_elegido, {}))
                self._prueba_propia = True
            finally:
                del espera
            if aviso:
                wx.MessageBox(aviso, _("Motor de voz"),
                              wx.OK | wx.ICON_WARNING, self)
        return self._prueba

    def _soltar_prueba(self) -> None:
        """Cierra el sintetizador de prueba, si había uno propio."""
        if self._prueba is None or not self._prueba_propia:
            self._prueba = None
            self._prueba_propia = False
            return
        try:
            self._prueba.detener()
            cerrar = getattr(self._prueba, "cerrar", None)
            if callable(cerrar):
                cerrar()
        except Exception as error:
            log.debug("Al soltar el motor de prueba: %s", error)
        self._prueba = None
        self._prueba_propia = False

    def _refrescar_voces(self) -> None:
        """Pone en la lista las voces del motor elegido.

        Se pregunta al motor de verdad, no a una tabla: las voces de Eloquence
        no son las de Windows, y enseñar unas mientras suena otro sería la peor
        clase de error, porque parecería que el programa funciona.
        """
        try:
            sintetizador = self._sintetizador()
            voces = list(sintetizador.voces()) if sintetizador else []
        except Exception as error:
            registrar_excepcion(log, "Listando las voces del motor", error)
            voces = []
        self.voces.Set(voces)
        hay = bool(voces)
        self.voces.Enable(hay)
        self.boton_probar.Enable(hay)
        # El de la pestaña de motores todavía puede no existir: las pestañas se
        # construyen en orden y esta llamada sale de la primera.
        if getattr(self, "boton_probar_motor", None) is not None:
            self.boton_probar_motor.Enable(hay)
        if hay:
            actual = str(self.configuracion.obtener("voz_nombre", "") or "")
            guardada = str(self._ajustes.get(self._motor_elegido, {}).get(
                "_voz_elegida", actual))
            self.voces.SetSelection(voces.index(guardada) if guardada in voces
                                    else 0)
            self.sin_voces.SetLabel("")
        else:
            self.sin_voces.SetLabel(_(
                "Este motor no ofrece ninguna voz ahora mismo. Si es la voz de "
                "Windows, se añaden en Configuración de Windows, en «Hora e "
                "idioma», «Voz»."))
        self.motor_actual.SetLabel(_("Motor: %s") % self._motor().nombre)
        self.Layout()

    def _al_probar(self, evento) -> None:
        """Lee la frase de prueba con lo que hay ahora en la ventana."""
        sintetizador = self._sintetizador()
        if sintetizador is None:
            return
        try:
            if self.voces.IsEnabled() and self.voces.GetSelection() >= 0:
                sintetizador.elegir_voz(self.voces.GetStringSelection())
            sintetizador.establecer_velocidad(
                sapi_desde_porcentaje(self.velocidad.GetValue()))
            sintetizador.establecer_volumen(self.volumen.GetValue())
            if not sintetizador.decir(self.PRUEBA):
                # Un motor puede arrancar y aun asi no poder hablar: a las voces
                # neuronales les falta la clave, a otro le faltan las voces.  Si
                # sabe decir por que, se dice; y si no, al menos se avisa de que
                # no ha sonado, que es mejor que no pasar nada.
                motivo = ""
                if hasattr(sintetizador, "problema"):
                    try:
                        motivo = sintetizador.problema() or ""
                    except Exception as error:
                        log.debug("Al preguntar el motivo: %s", error)
                aviso = (_("La voz no ha sonado: %s") % motivo if motivo
                         else _("La voz no ha sonado."))
                log.warning("Probar la voz: %s", motivo or "sin motivo")
                wx.MessageBox(aviso, _("Probar la voz"),
                              wx.OK | wx.ICON_WARNING, self)
        except Exception as error:
            registrar_excepcion(log, "Probando la voz", error)
            wx.MessageBox(_("La voz no ha podido hablar: %s") % error,
                          _("Probar la voz"), wx.OK | wx.ICON_ERROR, self)

    # -- aceptar y cerrar ----------------------------------------------------

    def _al_aceptar(self, evento) -> None:
        """Guarda los ajustes y los aplica a la lectura en curso."""
        self._guardar_valores_del_motor()
        try:
            self.lector.sintetizador.detener()
        except Exception:
            pass
        self._soltar_prueba()
        establecer = self.configuracion.establecer
        if self.voces.IsEnabled() and self.voces.GetSelection() >= 0:
            nombre = self.voces.GetStringSelection()
            establecer("voz_nombre", nombre)
            # La voz se guarda además **dentro del motor**: cada uno tiene las
            # suyas, y volver a un motor tiene que devolver la voz que se había
            # elegido en él, no la del otro.
            self._ajustes.setdefault(self._motor_elegido, {})
            self._ajustes[self._motor_elegido]["_voz_elegida"] = nombre
        establecer(CLAVE_MOTOR, self._motor_elegido)
        establecer(CLAVE_AJUSTES, self._ajustes)
        establecer("voz_rapidez", self.velocidad.GetValue())
        establecer("voz_volumen", self.volumen.GetValue())
        establecer("voz_mover_cursor", self.mover.GetValue())
        establecer("voz_resaltar_frase", self.resaltar.GetValue())
        establecer("voz_cursor_al_parar",
                   self._sitios_al_parar[max(0, self.cursor_al_parar.GetSelection())][0])
        establecer("voz_modo_dialogo", self.dialogos.GetValue())
        establecer("voz_tono_dialogo", self.tono_dialogo.GetValue())
        establecer("voz_leer_descripciones", self.descripciones.GetValue())
        establecer("voz_seguir_idioma", self.seguir_idioma.GetValue())
        establecer("voz_quimica",
                   self._modos_quimica[max(0, self.quimica.GetSelection())][0])
        establecer("voz_saltar_notas", self.saltar_notas.GetValue())
        establecer("voz_saltar_folios", self.saltar_folios.GetValue())
        establecer("voz_saltar_cabeceras", self.saltar_cabeceras.GetValue())
        self.configuracion.guardar()
        # Cambiar de motor obliga a rehacer el sintetizador: el que había es de
        # otro programa y no se convierte en el nuevo.
        self.lector.aplicar_motor()
        self.lector.aplicar_ajustes()
        # La química y las omisiones se calculan al abrir el documento, así que
        # hay que rehacerlas ahora o el cambio no se notaría hasta el libro
        # siguiente.
        self.lector.refrescar_pronunciacion()
        self.EndModal(wx.ID_OK)

    def _al_cerrar(self, evento) -> None:
        """Calla la prueba al cerrar, para no dejar la voz hablando sola."""
        try:
            self.lector.sintetizador.detener()
        except Exception:
            pass
        self._soltar_prueba()
        evento.Skip()
