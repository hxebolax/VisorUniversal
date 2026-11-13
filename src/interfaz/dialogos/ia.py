# -*- coding: utf-8 -*-
"""Diálogos de la descripción de imágenes con inteligencia artificial.

Cuatro ventanas:

* :class:`DialogoPrompts`, el gestor de prompts: la lista de instrucciones
  disponibles, con las predefinidas del programa y las que añada el usuario.
* :class:`DialogoEditarPrompt`, para escribir o retocar una instrucción propia.
* :class:`DialogoDescripcion`, la que hace el trabajo: pide la descripción y la
  muestra.
* :class:`DialogoDescribirTodo`, la herramienta que describe el libro entero de
  una vez, con progreso y sin repetir lo ya hecho.

La petición a la IA tarda entre uno y sesenta segundos y **bloquea**, así que
siempre se hace en un hilo aparte.  Mientras tanto el diálogo dice que está
trabajando, mantiene el foco donde está y deja cancelar.  El resultado vuelve
al hilo de la interfaz con ``wx.CallAfter``, que es la única forma segura de
tocar los controles desde otro hilo.
"""

from __future__ import annotations

import threading

import wx

from interfaz.temporizadores import parar_al_destruir
from interfaz.accesible import etiquetar, fila_etiquetada
from interfaz.anuncios import Voz
from interfaz.dialogos import ayuda_opcion
from interfaz.listas import ListaAccesible, rellenar_columnas
from interfaz.ventanas_win32 import suprimir_menu_contextual
from nucleo import esquemas
from nucleo import graficos
from nucleo.descripciones import Descripcion
from nucleo.ia import prompts as tabla_prompts
from nucleo.ia.servicio import ErrorIA, Servicio
from nucleo.idioma import _, _n
from nucleo.registro import obtener_registro, registrar_excepcion

log = obtener_registro(__name__)

MARGEN = 8


class DialogoEditarPrompt(wx.Dialog):
    """Escribe o modifica una instrucción propia.

    :param prompt: Prompt que se edita, o ``None`` para crear uno nuevo.
    """

    def __init__(self, padre: wx.Window, prompt=None) -> None:
        super().__init__(padre, title="Prompt nuevo" if prompt is None else _("Editar el prompt"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.resultado: tuple[str, str] | None = None

        contenedor = wx.BoxSizer(wx.VERTICAL)
        self.nombre = fila_etiquetada(
            self, contenedor, _("&Nombre (para reconocerlo en la lista):"),
            lambda p: wx.TextCtrl(p, value=prompt.nombre if prompt else ""),
            margen=MARGEN)
        contenedor.Add(wx.StaticText(self, label=_("&Instrucción para la inteligencia artificial:")),
                       0, wx.LEFT | wx.RIGHT | wx.TOP, MARGEN)
        self.texto = etiquetar(wx.TextCtrl(
            self, value=prompt.texto if prompt else "",
            style=wx.TE_MULTILINE | wx.TE_NOHIDESEL, size=(620, 260)),
            _("Instrucción para la inteligencia artificial"))
        contenedor.Add(self.texto, 1, wx.EXPAND | wx.ALL, MARGEN)
        contenedor.Add(wx.StaticText(self, label=(
            _("Escribe qué quieres que cuente de la imagen y con cuánto detalle. No hace falta\n"
            "pedir que responda en español ni sin markdown: el programa ya lo añade.")
        )), 0, wx.ALL, MARGEN)

        fila = wx.StdDialogButtonSizer()
        aceptar = wx.Button(self, wx.ID_OK, _("&Guardar"))
        aceptar.SetDefault()
        fila.AddButton(aceptar)
        fila.AddButton(wx.Button(self, wx.ID_CANCEL, _("&Cancelar")))
        fila.Realize()
        contenedor.Add(fila, 0, wx.EXPAND | wx.ALL, MARGEN)
        self.SetSizerAndFit(contenedor)
        self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)
        self.nombre.SetFocus()
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    def _al_aceptar(self, evento) -> None:
        """Comprueba que hay nombre e instrucción antes de cerrar."""
        nombre = self.nombre.GetValue().strip()
        texto = self.texto.GetValue().strip()
        if not nombre:
            wx.MessageBox(_("Ponle un nombre al prompt para poder reconocerlo en la lista."),
                          _("Falta el nombre"), wx.OK | wx.ICON_INFORMATION, self)
            self.nombre.SetFocus()
            return
        if not texto:
            wx.MessageBox(_("Escribe la instrucción que se le va a dar a la inteligencia artificial."),
                          _("Falta la instrucción"), wx.OK | wx.ICON_INFORMATION, self)
            self.texto.SetFocus()
            return
        self.resultado = (nombre, texto)
        self.EndModal(wx.ID_OK)


class DialogoPrompts(wx.Dialog):
    """Gestor de prompts: los que trae el programa y los del usuario.

    Los predefinidos no se pueden editar ni borrar, pero sí **duplicar**: es la
    forma cómoda de partir de uno que ya funciona y cambiarle lo justo.  Que
    sigan intactos permite volver a ellos cuando un prompt propio no acaba de
    dar el resultado esperado.
    """

    COLUMNAS = ("Nombre", "Clase", _("Instrucción"))
    ANCHOS = (240, 110, 460)

    def __init__(self, padre: wx.Window, configuracion) -> None:
        super().__init__(padre, title=_("Gestor de prompts de descripción"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.configuracion = configuracion
        self._voz = Voz(self)
        self.prompts = tabla_prompts.desde_configuracion(configuracion)
        self.preferido = str(configuracion.obtener("ia_prompt_preferido",
                                                   tabla_prompts.POR_OMISION))

        contenedor = wx.BoxSizer(wx.VERTICAL)
        contenedor.Add(wx.StaticText(self, label=(
            _("Cada libro se describe mejor con una instrucción distinta: no se cuenta igual una\n"
            "lámina de botánica que una viñeta de cómic. Elige aquí cuál se usa por omisión.")
        )), 0, wx.ALL, MARGEN)
        contenedor.Add(wx.StaticText(self, label=_("&Prompts disponibles:")), 0,
                       wx.LEFT | wx.RIGHT | wx.TOP, MARGEN)
        self.lista = etiquetar(ListaAccesible(
            self, configuracion, "Prompts disponibles", size=(820, 320)), _("Prompts disponibles"))
        rellenar_columnas(self.lista, self.COLUMNAS, self.ANCHOS)
        contenedor.Add(self.lista, 1, wx.EXPAND | wx.ALL, MARGEN)

        self.detalle = wx.StaticText(self, label="")
        contenedor.Add(self.detalle, 0, wx.LEFT | wx.RIGHT, MARGEN)

        fila = wx.BoxSizer(wx.HORIZONTAL)
        self.boton_preferido = wx.Button(self, label=_("&Usar este por omisión"))
        self.boton_nuevo = wx.Button(self, label=_("&Nuevo..."))
        self.boton_duplicar = wx.Button(self, label=_("&Duplicar"))
        self.boton_editar = wx.Button(self, label=_("&Editar..."))
        self.boton_eliminar = wx.Button(self, label=_("E&liminar"))
        for boton in (self.boton_preferido, self.boton_nuevo, self.boton_duplicar,
                      self.boton_editar, self.boton_eliminar):
            fila.Add(boton, 0, wx.ALL, MARGEN)
        contenedor.Add(fila, 0)

        pie = wx.StdDialogButtonSizer()
        aceptar = wx.Button(self, wx.ID_OK, _("&Aceptar"))
        aceptar.SetDefault()
        pie.AddButton(aceptar)
        pie.AddButton(wx.Button(self, wx.ID_CANCEL, _("&Cancelar")))
        pie.Realize()
        contenedor.Add(pie, 0, wx.EXPAND | wx.ALL, MARGEN)
        self.SetSizerAndFit(contenedor)

        self.boton_preferido.Bind(wx.EVT_BUTTON, self._al_preferir)
        self.boton_nuevo.Bind(wx.EVT_BUTTON, self._al_nuevo)
        self.boton_duplicar.Bind(wx.EVT_BUTTON, self._al_duplicar)
        self.boton_editar.Bind(wx.EVT_BUTTON, self._al_editar)
        self.boton_eliminar.Bind(wx.EVT_BUTTON, self._al_eliminar)
        self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._al_editar)
        self.lista.Bind(wx.EVT_LIST_ITEM_FOCUSED, lambda evento: self._actualizar_botones())
        self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)
        self._rellenar()
        self.lista.SetFocus()
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    # -- lista ---------------------------------------------------------------

    def _rellenar(self, seleccionar: int = 0) -> None:
        """Vuelca los prompts en la lista y marca cuál es el preferido."""
        self.lista.DeleteAllItems()
        for numero, prompt in enumerate(self.prompts):
            clase = "Predefinido" if prompt.predefinido else "Propio"
            if prompt.identificador == self.preferido:
                clase += _(", por omisión")
            self.lista.InsertItem(numero, prompt.nombre)
            self.lista.SetItem(numero, 1, clase)
            self.lista.SetItem(numero, 2, prompt.texto.replace("\n", " "))
        if self.prompts:
            indice = min(max(seleccionar, 0), len(self.prompts) - 1)
            self.lista.Select(indice)
            self.lista.Focus(indice)
            self.lista.EnsureVisible(indice)
        self._actualizar_botones()

    def _elegido(self):
        """Prompt sobre el que está el foco, o ``None``."""
        indice = self.lista.fila_actual()
        return self.prompts[indice] if 0 <= indice < len(self.prompts) else None

    def _actualizar_botones(self) -> None:
        """Activa solo lo que se puede hacer con el prompt elegido."""
        prompt = self._elegido()
        propio = prompt is not None and not prompt.predefinido
        self.boton_editar.Enable(propio)
        self.boton_eliminar.Enable(propio)
        self.boton_duplicar.Enable(prompt is not None)
        self.boton_preferido.Enable(
            prompt is not None and prompt.identificador != self.preferido)
        if prompt is None:
            self.detalle.SetLabel("")
        elif prompt.predefinido:
            self.detalle.SetLabel(
                _("Los prompts predefinidos no se editan ni se borran. Duplícalo para cambiarlo."))
        else:
            self.detalle.SetLabel(_("Prompt propio: se puede editar y eliminar."))

    # -- acciones ------------------------------------------------------------

    def _al_preferir(self, evento) -> None:
        """Marca el prompt elegido como el que se usa por omisión."""
        prompt = self._elegido()
        if prompt is None:
            return
        self.preferido = prompt.identificador
        self._rellenar(self.lista.fila_actual())
        self._voz.decir(_("«%s» pasa a ser el prompt por omisión.") % prompt.nombre)

    def _al_nuevo(self, evento) -> None:
        """Crea un prompt propio desde cero."""
        self._crear(None)

    def _al_duplicar(self, evento) -> None:
        """Crea un prompt propio partiendo del elegido."""
        prompt = self._elegido()
        if prompt is None:
            return
        self._crear(prompt._replace(nombre="%s (copia)" % prompt.nombre))

    def _crear(self, plantilla) -> None:
        """Abre el editor y añade el prompt que salga de él."""
        with DialogoEditarPrompt(self, plantilla) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK or dialogo.resultado is None:
                return
            nombre, texto = dialogo.resultado
        nuevo = tabla_prompts.Prompt(
            tabla_prompts.identificador_libre(self.prompts), nombre, texto, False)
        self.prompts.append(nuevo)
        self._rellenar(len(self.prompts) - 1)
        self._voz.decir(_("Prompt «%s» añadido.") % nombre)

    def _al_editar(self, evento) -> None:
        """Modifica un prompt propio."""
        prompt = self._elegido()
        if prompt is None or prompt.predefinido:
            if prompt is not None:
                self._voz.decir(_("Este prompt viene con el programa y no se puede editar. "
                                "Duplícalo para cambiarlo."))
            return
        indice = self.lista.fila_actual()
        with DialogoEditarPrompt(self, prompt) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK or dialogo.resultado is None:
                return
            nombre, texto = dialogo.resultado
        self.prompts[indice] = prompt._replace(nombre=nombre, texto=texto)
        self._rellenar(indice)

    def _al_eliminar(self, evento) -> None:
        """Borra un prompt propio, tras confirmarlo."""
        prompt = self._elegido()
        if prompt is None or prompt.predefinido:
            return
        if wx.MessageBox(
                _("¿Seguro que quieres eliminar el prompt «%s»?\n\nEsta acción no se puede deshacer.")
                % prompt.nombre, _("Eliminar el prompt"),
                wx.YES_NO | wx.ICON_QUESTION | wx.NO_DEFAULT, self) != wx.YES:
            return
        indice = self.lista.fila_actual()
        self.prompts.pop(indice)
        if self.preferido == prompt.identificador:
            # Si se borra el preferido hay que dejar otro, o no habría con qué
            # describir: se vuelve al primero de los predefinidos.
            self.preferido = tabla_prompts.POR_OMISION
        self._rellenar(indice)
        self._voz.decir(_("Prompt eliminado."))

    def _al_aceptar(self, evento) -> None:
        """Guarda los prompts propios y cuál es el preferido."""
        tabla_prompts.guardar_propios(self.configuracion, self.prompts)
        self.configuracion.establecer("ia_prompt_preferido", self.preferido)
        self.configuracion.guardar()
        log.info("Prompts guardados: %d propios, preferido «%s»",
                 sum(1 for p in self.prompts if not p.predefinido), self.preferido)
        self.EndModal(wx.ID_OK)


class DialogoDescripcion(wx.Dialog):
    """Pide a la IA que describa una imagen y muestra el resultado.

    :param padre: Ventana principal.
    :param datos: Bytes de la imagen sacados del EPUB.
    :param marca: Marca de la imagen, de donde salen su nombre de archivo y la
                  descripción que ya trae el libro.
    :param configuracion: Preferencias.
    :param coleccion: Descripciones guardadas del libro, donde se anota la nueva.
    :param contexto: Datos del libro que se le pasan a la IA como contexto.
    :param guardada: Descripción anterior, si la había.  Se muestra de entrada
                     y evita gastar una petición cuando ya está hecha.
    :param al_vuelo: Si se pide la descripción nada más abrirse.  Es lo que
                     hace la tecla rápida.
    """

    def __init__(self, padre: wx.Window, datos: bytes, marca, configuracion,
                 coleccion, contexto: str = "", guardada=None,
                 al_vuelo: bool = False) -> None:
        super().__init__(padre, title=_("Descripción de la imagen"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.datos = datos
        self.marca = marca
        self.configuracion = configuracion
        self.coleccion = coleccion
        self.contexto = contexto
        self.servicio = Servicio(configuracion)
        self._voz = Voz(self)
        self._trabajando = False
        self._peticion = 0

        contenedor = wx.BoxSizer(wx.VERTICAL)

        original = (getattr(marca, "texto", "") or "").strip()
        contenedor.Add(wx.StaticText(self, label=(
            _("Descripción que trae el documento: %s") % (original or "ninguna"))[:200]),
            0, wx.ALL, MARGEN)

        self.prompts = tabla_prompts.desde_configuracion(configuracion)
        preferido = tabla_prompts.preferido(configuracion)
        self.eleccion = fila_etiquetada(
            self, contenedor, _("&Tipo de descripción:"),
            lambda p: wx.Choice(p, choices=[prompt.nombre for prompt in self.prompts]),
            margen=MARGEN, horizontal=True, proporcion=1)
        indices = [numero for numero, prompt in enumerate(self.prompts)
                   if prompt.identificador == preferido.identificador]
        self.eleccion.SetSelection(indices[0] if indices else 0)

        contenedor.Add(wx.StaticText(self, label=_("&Descripción:")), 0,
                       wx.LEFT | wx.RIGHT | wx.TOP, MARGEN)
        self.campo = etiquetar(wx.TextCtrl(
            self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_NOHIDESEL, size=(620, 300)),
            _("Descripción de la imagen"))
        self._sin_menu = [suprimir_menu_contextual(self.campo)]
        contenedor.Add(self.campo, 1, wx.EXPAND | wx.ALL, MARGEN)

        self.estado = wx.StaticText(self, label="")
        contenedor.Add(self.estado, 0, wx.LEFT | wx.RIGHT, MARGEN)

        # Describir tarda entre unos segundos y casi un minuto, y no hay forma
        # de saber cuánto queda: la barra no marca un porcentaje, solo late
        # para que se vea que el programa sigue trabajando.  Aparece únicamente
        # mientras dura, para no dejar un adorno permanente por el que tenga
        # que pasar el cursor del lector de pantalla.
        self.barra = etiquetar(wx.Gauge(self, range=100, size=(-1, 16)),
                               _("Describiendo"))
        contenedor.Add(self.barra, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, MARGEN)
        self.barra.Hide()
        self._latido = wx.Timer(self)
        parar_al_destruir(self, self._latido)
        self.Bind(wx.EVT_TIMER, lambda evento: self.barra.Pulse(), self._latido)

        fila = wx.BoxSizer(wx.HORIZONTAL)
        self.boton_describir = wx.Button(self, label=_("&Describir con IA"))
        # Sacar los datos es una acción distinta de describir, y por eso tiene
        # su propio botón: la descripción dice de qué va el gráfico y la tabla
        # dice cuánto.  Se guardan las dos y se pueden pedir por separado.
        self.boton_datos = wx.Button(self, label=_("Sacar los &datos"))
        self.boton_tabla = wx.Button(self, label=_("Ver la &tabla"))
        self.boton_copiar = wx.Button(self, label=_("Cop&iar"))
        self.boton_olvidar = wx.Button(self, label=_("&Olvidar la guardada"))
        for boton in (self.boton_describir, self.boton_datos, self.boton_tabla,
                      self.boton_copiar, self.boton_olvidar):
            fila.Add(boton, 0, wx.ALL, MARGEN)
        contenedor.Add(fila, 0)

        pie = wx.StdDialogButtonSizer()
        cerrar = wx.Button(self, wx.ID_OK, _("&Cerrar"))
        cerrar.SetDefault()
        pie.AddButton(cerrar)
        pie.Realize()
        contenedor.Add(pie, 0, wx.EXPAND | wx.ALL, MARGEN)
        self.SetSizerAndFit(contenedor)

        self.boton_describir.Bind(wx.EVT_BUTTON, self._al_describir)
        self.boton_datos.Bind(wx.EVT_BUTTON, self._al_sacar_datos)
        self.boton_tabla.Bind(wx.EVT_BUTTON, self._al_ver_tabla)
        self.boton_copiar.Bind(wx.EVT_BUTTON, self._al_copiar)
        self.boton_olvidar.Bind(wx.EVT_BUTTON, self._al_olvidar)
        self.Bind(wx.EVT_CLOSE, self._al_cerrar)
        # El botón «Cerrar» de un diálogo modal no pasa por EVT_CLOSE, así que
        # se atiende también aquí para no dejar el hilo escribiendo sobre
        # controles ya destruidos.
        self.Bind(wx.EVT_BUTTON, self._al_pulsar_cerrar, id=wx.ID_OK)

        #: Lo último que se sacó del gráfico, para poder verlo y guardarlo.
        self.grafico = guardada.grafico() if guardada is not None else None
        #: Y lo mismo si lo que había era un diagrama con estructura. Son dos
        #: cosas distintas —una tabla y un grafo— y solo puede haber una de las
        #: dos para la misma imagen, que es lo que se guardó de ella.
        self.esquema = guardada.esquema() if guardada is not None else None
        self._rotulo_tabla = self.boton_tabla.GetLabel()
        if guardada is not None:
            self.campo.SetValue(guardada.texto)
            self.estado.SetLabel(_("Descripción guardada · %s. Pulsa «Describir con IA» para "
                                 "pedir otra.") % guardada.resumen())
        elif original:
            self.campo.SetValue(original)
            self.estado.SetLabel(_("Esta es la descripción que trae el libro. "
                                 "Pulsa «Describir con IA» para pedir una más detallada."))
        else:
            self.estado.SetLabel(_("Esta imagen no tiene descripción en el documento."))
        self._actualizar_botones()
        self.campo.SetInsertionPoint(0)
        self.campo.SetFocus()
        if al_vuelo and guardada is None:
            # La tecla rápida abre el diálogo ya pidiendo la descripción, para
            # que baste con una pulsación.
            wx.CallAfter(self._al_describir, None)
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    # -- estado --------------------------------------------------------------

    def _mostrar_actividad(self, encendida: bool) -> None:
        """Enciende o apaga la barra que late mientras se describe."""
        if not self:
            return
        self.barra.Show(encendida)
        if encendida:
            self._latido.Start(120)
        else:
            self._latido.Stop()
        self.Layout()

    def _actualizar_botones(self) -> None:
        """Deja activo solo lo que tiene sentido en cada momento."""
        hay_texto = bool(self.campo.GetValue().strip())
        self.boton_describir.Enable(not self._trabajando)
        self.boton_datos.Enable(not self._trabajando)
        self.boton_tabla.Enable(bool(self.grafico or self.esquema)
                                and not self._trabajando)
        # El botón se llama según lo que haya: «Ver la tabla» para un gráfico y
        # «Ver el esquema» para un diagrama. Un rótulo que no dice lo que va a
        # salir obliga a pulsarlo para averiguarlo.
        self.boton_tabla.SetLabel(_("Ver el es&quema") if self.esquema
                                  else self._rotulo_tabla)
        self.boton_copiar.Enable(hay_texto and not self._trabajando)
        self.boton_olvidar.Enable(
            not self._trabajando
            and self.coleccion is not None
            and self.coleccion.obtener(getattr(self.marca, "referencia", "")) is not None)
        self.eleccion.Enable(not self._trabajando)

    # -- descripción ---------------------------------------------------------

    def _al_describir(self, evento) -> None:
        """Pide la descripción a la IA en un hilo aparte."""
        if self._trabajando:
            return
        motivo = self.servicio.motivo_no_disponible()
        if motivo:
            wx.MessageBox(motivo, _("Inteligencia artificial"), wx.OK | wx.ICON_INFORMATION, self)
            return
        indice = max(self.eleccion.GetSelection(), 0)
        prompt = self.prompts[indice] if indice < len(self.prompts) else None

        self._trabajando = True
        self._peticion += 1
        numero = self._peticion
        self._actualizar_botones()
        self._mostrar_actividad(True)
        aviso = _("Describiendo la imagen con %s. Puede tardar un poco...") % (
            self.servicio.descripcion_del_modelo())
        self.estado.SetLabel(aviso)
        self._voz.decir(aviso)

        def trabajo():
            """Habla con la IA fuera del hilo de la interfaz."""
            try:
                texto = self.servicio.describir(
                    self.datos, getattr(self.marca, "referencia", ""), prompt, self.contexto)
            except ErrorIA as error:
                wx.CallAfter(self._fallo, numero, str(error))
            except Exception as error:  # pragma: no cover - salvaguarda
                registrar_excepcion(log, "Fallo inesperado al describir la imagen", error)
                wx.CallAfter(self._fallo, numero, str(error))
            else:
                wx.CallAfter(self._listo, numero, texto, prompt)

        threading.Thread(target=trabajo, name="describir", daemon=True).start()

    def _listo(self, numero: int, texto: str, prompt) -> None:
        """Recibe la descripción, la muestra y la guarda."""
        if numero != self._peticion or not self:
            return
        self._trabajando = False
        self._mostrar_actividad(False)
        self.campo.SetValue(texto)
        self.campo.SetInsertionPoint(0)
        descripcion = Descripcion(texto, prompt.nombre if prompt else "",
                                  self.servicio.descripcion_del_modelo())
        if self.coleccion is not None and self.configuracion.obtener("ia_guardar_descripciones", True):
            self.coleccion.guardar(getattr(self.marca, "referencia", ""), descripcion)
            self.estado.SetLabel(_("Descripción hecha y guardada · %s") % descripcion.resumen())
        else:
            self.estado.SetLabel(_("Descripción hecha · %s") % descripcion.resumen())
        self._actualizar_botones()
        self.campo.SetFocus()
        self._voz.decir(_("Descripción lista. ") + texto)

    # -- los datos del gráfico ----------------------------------------------

    def _al_sacar_datos(self, evento) -> None:
        """Le pide a la IA los **valores** del gráfico, no su descripción.

        Es la diferencia entre oír «un gráfico de barras de ventas por
        trimestre» y poder recorrer los doce números que hay dentro.  Se manda
        la misma imagen con otra instrucción, y lo que vuelve se interpreta como
        una tabla; si no era un gráfico, se dice y no se guarda nada.
        """
        if self._trabajando:
            return
        motivo = self.servicio.motivo_no_disponible()
        if motivo:
            wx.MessageBox(motivo, _("Inteligencia artificial"), wx.OK | wx.ICON_INFORMATION, self)
            return

        self._trabajando = True
        self._peticion += 1
        numero = self._peticion
        self._actualizar_botones()
        self._mostrar_actividad(True)
        aviso = _("Leyendo los datos del gráfico con %s. Puede tardar un poco...") % (
            self.servicio.descripcion_del_modelo())
        self.estado.SetLabel(aviso)
        self._voz.decir(aviso)

        instruccion = tabla_prompts.Prompt("datos", _("Datos del gráfico"),
                                           graficos.INSTRUCCION, True)
        otra = tabla_prompts.Prompt("esquema", _("Estructura del diagrama"),
                                    esquemas.INSTRUCCION, True)

        def trabajo():
            """Habla con la IA fuera del hilo de la interfaz.

            Se pregunta dos veces cuando hace falta, y en este orden: primero
            por los datos y, **solo si la imagen no era un gráfico**, por la
            estructura. Con un botón y no con dos, porque quien tiene delante
            una imagen no siempre sabe si lo que hay dentro es una tabla o un
            diagrama: eso es justo lo que no puede ver.
            """
            try:
                respuesta = self.servicio.describir(
                    self.datos, getattr(self.marca, "referencia", ""), instruccion,
                    self.contexto)
                if graficos.interpretar(respuesta) is None:
                    respuesta = self.servicio.describir(
                        self.datos, getattr(self.marca, "referencia", ""), otra,
                        self.contexto)
            except ErrorIA as error:
                wx.CallAfter(self._fallo, numero, str(error))
            except Exception as error:  # pragma: no cover - salvaguarda
                registrar_excepcion(log, "Fallo inesperado al leer el gráfico", error)
                wx.CallAfter(self._fallo, numero, str(error))
            else:
                wx.CallAfter(self._datos_listos, numero, respuesta)

        threading.Thread(target=trabajo, name="datos-grafico", daemon=True).start()

    def _datos_listos(self, numero: int, respuesta: str) -> None:
        """Interpreta la respuesta, la guarda y ofrece verla como tabla."""
        if numero != self._peticion or not self:
            return
        self._trabajando = False
        self._mostrar_actividad(False)
        grafico = graficos.interpretar(respuesta)
        esquema = esquemas.interpretar(respuesta) if grafico is None else None
        if grafico is None and esquema is None:
            # No haber sacado datos no es un fallo: hay imágenes que no los
            # tienen.  Se dice y se deja la descripción como estaba.
            self.grafico = self.esquema = None
            self.estado.SetLabel(_("De esta imagen no se han podido sacar datos: no parece "
                                   "un gráfico con valores ni un diagrama con "
                                   "estructura."))
            self._actualizar_botones()
            self._voz.decir(_("De esta imagen no se han podido sacar datos."))
            return
        self.grafico, self.esquema = grafico, esquema
        if esquema is not None:
            self._guardar_esquema(esquema)
            aviso = _("Diagrama leído y guardado. %s Pulsa «Ver el esquema».") \
                % esquema.resumen()
            self.estado.SetLabel(aviso)
            self._actualizar_botones()
            self.boton_tabla.SetFocus()
            self._voz.decir(_("Diagrama leído. %s") % esquema.resumen())
            return
        self._guardar_datos(grafico)
        self.estado.SetLabel(_("Datos leídos y guardados. %s Pulsa «Ver la tabla».")
                             % grafico.resumen())
        self._actualizar_botones()
        self.boton_tabla.SetFocus()
        self._voz.decir(_("Datos leídos. %s") % grafico.resumen())

    def _guardar_datos(self, grafico) -> None:
        """Anota la tabla junto a la descripción de esta imagen.

        Si todavía no había descripción se crea una vacía: los datos son de la
        imagen, no de la descripción, y perderlos por no haber pedido antes una
        descripción no tendría ningún sentido.
        """
        if self.coleccion is None:
            return
        if not self.configuracion.obtener("ia_guardar_descripciones", True):
            return
        referencia = getattr(self.marca, "referencia", "")
        anterior = self.coleccion.obtener(referencia)
        descripcion = Descripcion(
            anterior.texto if anterior is not None else self.campo.GetValue().strip(),
            anterior.prompt if anterior is not None else "",
            self.servicio.descripcion_del_modelo(),
            datos=grafico.rejilla(), datos_titulo=grafico.titulo,
            datos_unidades=grafico.unidades, datos_nota=grafico.nota,
            datos_fiabilidad=grafico.fiabilidad, datos_por_que=grafico.por_que)
        self.coleccion.guardar(referencia, descripcion)

    def _guardar_esquema(self, esquema) -> None:
        """Anota el diagrama junto a la descripción de esta imagen.

        Se guarda en el mismo sitio que la tabla de un gráfico, porque para una
        imagen solo puede haber una de las dos cosas: o tiene valores o tiene
        estructura. Lo guardado lleva su marca delante para saber cuál es.
        """
        if self.coleccion is None:
            return
        if not self.configuracion.obtener("ia_guardar_descripciones", True):
            return
        referencia = getattr(self.marca, "referencia", "")
        anterior = self.coleccion.obtener(referencia)
        descripcion = Descripcion(
            anterior.texto if anterior is not None else self.campo.GetValue().strip(),
            anterior.prompt if anterior is not None else "",
            self.servicio.descripcion_del_modelo(),
            datos=esquema.para_guardar(), datos_titulo=esquema.titulo,
            datos_unidades=esquema.tipo, datos_nota=esquema.nota,
            datos_fiabilidad=esquema.fiabilidad, datos_por_que=esquema.por_que)
        self.coleccion.guardar(referencia, descripcion)

    def _al_ver_tabla(self, evento) -> None:
        """Abre la tabla —o el diagrama— en el visor HTML.

        Ahí el lector de pantalla trata la tabla como una tabla de verdad —se va
        de celda en celda oyendo el encabezado de cada columna— y el diagrama
        como la lista anidada que es, diciendo en qué nivel está. Ninguna de las
        dos cosas se puede hacer oyendo una frase.
        """
        from .visor_html import DialogoHtml
        from nucleo import html_elementos

        if self.esquema:
            titulo = self.esquema.titulo or _("Diagrama")
            cuerpo = html_elementos.html_de_esquema(self.esquema)
        elif self.grafico:
            titulo = self.grafico.titulo or _("Datos del gráfico")
            cuerpo = html_elementos.html_de_grafico(self.grafico)
        else:
            return
        with DialogoHtml(self, None, None, titulo=titulo, cuerpo=cuerpo) as dialogo:
            dialogo.ShowModal()

    def _fallo(self, numero: int, mensaje: str) -> None:
        """Avisa de que no se ha podido describir."""
        if numero != self._peticion or not self:
            return
        self._trabajando = False
        self._mostrar_actividad(False)
        self.estado.SetLabel(_("No se ha podido describir la imagen."))
        self._actualizar_botones()
        wx.MessageBox(_("No se ha podido describir la imagen:\n\n%s") % mensaje,
                      _("Inteligencia artificial"), wx.OK | wx.ICON_ERROR, self)

    # -- otras acciones ------------------------------------------------------

    def _al_copiar(self, evento) -> None:
        """Copia la descripción al portapapeles."""
        texto = self.campo.GetValue().strip()
        if not texto or not wx.TheClipboard.Open():
            return
        try:
            wx.TheClipboard.SetData(wx.TextDataObject(texto))
        finally:
            wx.TheClipboard.Close()
        self._voz.decir(_("Descripción copiada al portapapeles."))

    def _al_olvidar(self, evento) -> None:
        """Borra la descripción guardada de esta imagen."""
        if self.coleccion is None:
            return
        if wx.MessageBox(_("¿Olvidar la descripción guardada de esta imagen?\n\n"
                         "La próxima vez habrá que volver a pedirla."),
                         _("Olvidar la descripción"),
                         wx.YES_NO | wx.ICON_QUESTION | wx.NO_DEFAULT, self) != wx.YES:
            return
        self.coleccion.olvidar(getattr(self.marca, "referencia", ""))
        self.estado.SetLabel(_("Descripción olvidada."))
        self._actualizar_botones()
        self._voz.decir(_("Descripción olvidada."))

    def _al_cerrar(self, evento) -> None:
        """Impide cerrar mientras se está describiendo.

        El hilo seguiría vivo y escribiría sobre controles ya destruidos.  Como
        la petición tiene su propio tiempo de espera, basta con avisar.
        """
        if self._trabajando:
            self._voz.decir(_("Espera a que termine la descripción."))
            if evento.CanVeto():
                evento.Veto()
            return
        evento.Skip()

    def _al_pulsar_cerrar(self, evento) -> None:
        """Atiende el botón «Cerrar» con la misma protección."""
        if self._trabajando:
            self._voz.decir(_("Espera a que termine la descripción."))
            return
        self.EndModal(wx.ID_OK)


class DialogoDescribirTodo(wx.Dialog):
    """Describe de una vez todas las imágenes del libro.

    Describir imagen por imagen está bien mientras se lee, pero en un libro
    ilustrado se acaba parando la lectura cada dos páginas.  Esta herramienta
    lo hace todo de una tacada: se lanza, se deja trabajando y al volver el
    libro está descrito entero.

    Tres cosas la hacen utilizable de verdad:

    * **Se puede parar y retomar.**  Solo se describen las imágenes que aún no
      lo están, así que detenerla a la mitad y volver a lanzarla mañana
      continúa por donde iba, sin repetir ni gastar de más.
    * **Cada imagen se describe una sola vez.**  Una misma ilustración puede
      aparecer en varios sitios del libro; se agrupan por archivo.
    * **Un fallo suelto no tira el trabajo.**  Se anota y se sigue; solo se
      abandona si fallan tres seguidas, que ya indica que algo va mal de
      verdad (la cuota agotada, el servidor caído).

    :param padre: Ventana principal.
    :param marcas: Imágenes del libro, ya sin repetir y ordenadas.
    :param configuracion: Preferencias.
    :param coleccion: Descripciones guardadas del libro.
    :param extraer: Función ``marca -> bytes`` que saca la imagen del EPUB.
    :param contexto: Función ``marca -> str`` con los datos del libro para la IA.
    """

    #: Fallos seguidos tras los cuales se deja de insistir.
    FALLOS_SEGUIDOS = 3

    def __init__(self, padre: wx.Window, marcas, configuracion, coleccion,
                 extraer, contexto) -> None:
        super().__init__(padre, title=_("Describir todas las imágenes"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.marcas = list(marcas)
        self.configuracion = configuracion
        self.coleccion = coleccion
        self._extraer = extraer
        self._contexto = contexto
        self.servicio = Servicio(configuracion)
        self._voz = Voz(self)
        self._parar = threading.Event()
        self._trabajando = False
        self._pendientes: list = []
        self.hechas = 0
        self.fallidas = 0

        contenedor = wx.BoxSizer(wx.VERTICAL)
        self.resumen = wx.StaticText(self, label="")
        contenedor.Add(self.resumen, 0, wx.ALL, MARGEN)

        self.prompts = tabla_prompts.desde_configuracion(configuracion)
        preferido = tabla_prompts.preferido(configuracion)
        self.eleccion = fila_etiquetada(
            self, contenedor, _("&Tipo de descripción para todas:"),
            lambda p: wx.Choice(p, choices=[prompt.nombre for prompt in self.prompts]),
            margen=MARGEN, horizontal=True, proporcion=1)
        indices = [numero for numero, prompt in enumerate(self.prompts)
                   if prompt.identificador == preferido.identificador]
        self.eleccion.SetSelection(indices[0] if indices else 0)

        self.saltar_con_texto = wx.CheckBox(
            self, label=_("Saltar también las que ya traen &descripción en el documento"))
        contenedor.Add(self.saltar_con_texto, 0, wx.ALL, MARGEN)

        # Sacar los datos gasta una petición más por imagen, así que viene
        # apagado: en un libro ilustrado la mayoría de las imágenes no son
        # gráficos y sería tirar la mitad de la cuota.  En un informe, en
        # cambio, es justo lo que hay que encender.
        self.con_datos = wx.CheckBox(
            self, label=_("Sacar también los &datos de los gráficos (una petición más "
                          "por imagen)"))
        self.con_datos.SetValue(bool(configuracion.obtener("ia_datos_en_lote", False)))
        contenedor.Add(self.con_datos, 0, wx.ALL, MARGEN)

        self.pausa = fila_etiquetada(
            self, contenedor, _("Segundos de espera &entre imágenes:"),
            lambda p: wx.SpinCtrl(p, min=0, max=60,
                                  initial=int(configuracion.obtener("ia_pausa_lote", 0))),
            margen=MARGEN, horizontal=True)
        contenedor.Add(wx.StaticText(self, label=(
            _("Déjalo en 0 salvo que el proveedor se queje de cuota: la capa gratuita de Gemini\n"
            "limita las peticiones por minuto, y esperar unos segundos entre imágenes lo evita.")
        )), 0, wx.LEFT | wx.RIGHT, MARGEN)

        contenedor.Add(wx.StaticText(self, label=_("&Progreso:")), 0,
                       wx.LEFT | wx.RIGHT | wx.TOP, MARGEN)
        self.barra = etiquetar(wx.Gauge(self, range=100, size=(560, 22)), _("Progreso"))
        contenedor.Add(self.barra, 0, wx.EXPAND | wx.ALL, MARGEN)
        self.estado = wx.StaticText(self, label="")
        contenedor.Add(self.estado, 0, wx.LEFT | wx.RIGHT, MARGEN)

        contenedor.Add(wx.StaticText(self, label=_("&Resultado:")), 0,
                       wx.LEFT | wx.RIGHT | wx.TOP, MARGEN)
        self.registro = etiquetar(wx.TextCtrl(
            self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_NOHIDESEL, size=(620, 220)),
            _("Resultado de la descripción"))
        self._sin_menu = [suprimir_menu_contextual(self.registro)]
        contenedor.Add(self.registro, 1, wx.EXPAND | wx.ALL, MARGEN)

        fila = wx.StdDialogButtonSizer()
        self.boton_empezar = wx.Button(self, label=_("&Empezar"))
        self.boton_empezar.SetDefault()
        self.boton_parar = wx.Button(self, label=_("De&tener"))
        cerrar = wx.Button(self, wx.ID_CANCEL, _("&Cerrar"))
        fila.Add(self.boton_empezar, 0, wx.RIGHT, MARGEN)
        fila.Add(self.boton_parar, 0, wx.RIGHT, MARGEN)
        fila.AddButton(cerrar)
        fila.Realize()
        contenedor.Add(fila, 0, wx.EXPAND | wx.ALL, MARGEN)
        self.SetSizerAndFit(contenedor)

        self.boton_empezar.Bind(wx.EVT_BUTTON, self._al_empezar)
        self.boton_parar.Bind(wx.EVT_BUTTON, self._al_parar)
        self.saltar_con_texto.Bind(wx.EVT_CHECKBOX, lambda evento: self._recontar())
        self.Bind(wx.EVT_CLOSE, self._al_cerrar)
        self.Bind(wx.EVT_BUTTON, self._al_pulsar_cerrar, id=wx.ID_CANCEL)

        self._recontar()
        self.boton_empezar.SetFocus()
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    # -- recuento ------------------------------------------------------------

    def _calcular_pendientes(self) -> list:
        """Imágenes que hay que describir con los filtros elegidos."""
        saltar_con_texto = self.saltar_con_texto.GetValue()
        pendientes = []
        for marca in self.marcas:
            if self.coleccion.obtener(marca.referencia or "") is not None:
                continue      # ya descrita: se respeta lo hecho
            if saltar_con_texto and (marca.texto or "").strip():
                continue
            pendientes.append(marca)
        return pendientes

    def _recontar(self) -> None:
        """Actualiza el resumen y el estado de los botones."""
        self._pendientes = self._calcular_pendientes()
        descritas = sum(1 for marca in self.marcas
                        if self.coleccion.obtener(marca.referencia or "") is not None)
        self.resumen.SetLabel(
            _("El libro tiene %d imágenes distintas. %d ya están descritas y quedan %d por "
            "describir con %s.") % (len(self.marcas), descritas, len(self._pendientes),
                                   self.servicio.descripcion_del_modelo()))
        self.barra.SetRange(max(len(self._pendientes), 1))
        self.barra.SetValue(0)
        self.boton_empezar.Enable(bool(self._pendientes) and not self._trabajando)
        self.boton_parar.Enable(self._trabajando)
        if not self._pendientes:
            self.estado.SetLabel(_("No queda ninguna imagen por describir."))
        else:
            self.estado.SetLabel(_("Listo para empezar."))

    # -- trabajo -------------------------------------------------------------

    def _al_empezar(self, evento) -> None:
        """Lanza la descripción de todas las pendientes en otro hilo."""
        motivo = self.servicio.motivo_no_disponible()
        if motivo:
            wx.MessageBox(motivo, _("Describir todas las imágenes"),
                          wx.OK | wx.ICON_INFORMATION, self)
            return
        if not self._pendientes:
            return
        indice = max(self.eleccion.GetSelection(), 0)
        prompt = self.prompts[indice] if indice < len(self.prompts) else None
        pausa = self.pausa.GetValue()
        self.configuracion.establecer("ia_pausa_lote", pausa)
        self.configuracion.establecer("ia_datos_en_lote", self.con_datos.GetValue())
        self.configuracion.guardar()

        self._parar.clear()
        self._trabajando = True
        self.hechas = 0
        self.fallidas = 0
        self._bloquear(True)
        total = len(self._pendientes)
        self.estado.SetLabel(
            _n("Describiendo %d imagen...", "Describiendo %d imágenes...", total) % total)
        self._voz.decir(_n("Describiendo %d imagen. Te avisaré al terminar.",
                           "Describiendo %d imágenes. Te avisaré al terminar.",
                           total) % total)
        log.info("Descripción por lotes: %d imágenes pendientes", total)

        pendientes = list(self._pendientes)
        threading.Thread(target=self._trabajo,
                         args=(pendientes, prompt, pausa, self.con_datos.GetValue()),
                         name="describir-lote", daemon=True).start()

    def _trabajo(self, pendientes, prompt, pausa: int, con_datos: bool = False) -> None:
        """Recorre las imágenes.  Se ejecuta fuera del hilo de la interfaz."""
        seguidos = 0
        for numero, marca in enumerate(pendientes, start=1):
            if self._parar.is_set():
                break
            referencia = marca.referencia or ""
            wx.CallAfter(self._avisar_de_la_imagen, numero, len(pendientes), referencia)
            try:
                datos = self._extraer(marca)
                if not datos:
                    raise ErrorIA(_("no se ha podido extraer del documento"))
                texto = self.servicio.describir(datos, referencia, prompt, self._contexto(marca))
            except Exception as error:
                seguidos += 1
                wx.CallAfter(self._resultado, numero, referencia, "", str(error))
                if seguidos >= self.FALLOS_SEGUIDOS:
                    wx.CallAfter(self._abandonar, str(error))
                    return
            else:
                seguidos = 0
                grafico = self._sacar_datos(datos, referencia) if con_datos else None
                descripcion = Descripcion(
                    texto, prompt.nombre if prompt else "",
                    self.servicio.descripcion_del_modelo(),
                    datos=grafico.rejilla() if grafico else "",
                    datos_titulo=grafico.titulo if grafico else "",
                    datos_unidades=grafico.unidades if grafico else "",
                    datos_nota=grafico.nota if grafico else "",
                    datos_fiabilidad=grafico.fiabilidad if grafico else "",
                    datos_por_que=grafico.por_que if grafico else "")
                self.coleccion.guardar(referencia, descripcion)
                if grafico:
                    texto = "%s [%s]" % (texto, grafico.resumen())
                wx.CallAfter(self._resultado, numero, referencia, texto, "")
            if pausa and not self._parar.is_set():
                self._parar.wait(pausa)
        wx.CallAfter(self._terminar)

    def _sacar_datos(self, datos: bytes, referencia: str):
        """Pide los valores del gráfico, si la imagen los tiene.

        Un fallo aquí no estropea nada: la descripción ya está hecha y se
        guarda igual, solo que sin tabla.  Por eso se traga la excepción en vez
        de contarla como imagen fallida.
        """
        instruccion = tabla_prompts.Prompt("datos", _("Datos del gráfico"),
                                           graficos.INSTRUCCION, True)
        try:
            respuesta = self.servicio.describir(datos, referencia, instruccion,
                                                "")
        except Exception as error:
            log.debug("No se han podido sacar los datos de %s: %s", referencia, error)
            return None
        return graficos.interpretar(respuesta)

    # -- avisos desde el hilo ------------------------------------------------

    def _avisar_de_la_imagen(self, numero: int, total: int, referencia: str) -> None:
        """Dice por qué imagen va."""
        if not self:
            return
        self.estado.SetLabel(_("Describiendo la imagen %d de %d: %s")
                             % (numero, total, referencia.rsplit("/", 1)[-1]))

    def _resultado(self, numero: int, referencia: str, texto: str, error: str) -> None:
        """Anota en el registro cómo ha ido una imagen."""
        if not self:
            return
        nombre = referencia.rsplit("/", 1)[-1]
        if error:
            self.fallidas += 1
            self.registro.AppendText(_("%d. %s: NO se ha podido describir (%s)\n")
                                     % (numero, nombre, error))
        else:
            self.hechas += 1
            self.registro.AppendText("%d. %s: %s\n" % (numero, nombre, texto.replace("\n", " ")))
        self.barra.SetValue(min(numero, self.barra.GetRange()))

    def _abandonar(self, error: str) -> None:
        """Deja el trabajo tras varios fallos seguidos."""
        if not self:
            return
        self.registro.AppendText(
            _("\nSe deja de insistir: han fallado %d imágenes seguidas.\n") % self.FALLOS_SEGUIDOS)
        self._terminar(abandonado=error)

    def _terminar(self, abandonado: str = "") -> None:
        """Recoge el trabajo y cuenta cómo ha ido."""
        if not self:
            return
        self._trabajando = False
        self._bloquear(False)
        self._recontar()
        if abandonado:
            mensaje = (_("Se ha interrumpido tras varios fallos seguidos. Descritas %d, fallidas "
                       "%d.\n\nÚltimo aviso: %s") % (self.hechas, self.fallidas, abandonado))
            titulo = _("Descripción interrumpida")
        elif self._parar.is_set():
            mensaje = (_("Detenido. Se han descrito %d imágenes y quedan %d por describir; "
                       "puedes volver a lanzarlo y seguirá por donde iba.")
                       % (self.hechas, len(self._pendientes)))
            titulo = _("Descripción detenida")
        else:
            mensaje = _n("Terminado. Descrita %d imagen", "Terminado. Descritas %d imágenes",
                         self.hechas) % self.hechas
            mensaje += (_(" y %d no se han podido describir.") % self.fallidas
                        if self.fallidas else ", todas correctamente.")
            titulo = _("Descripción terminada")
        self.estado.SetLabel(mensaje.split("\n")[0])
        log.info("Descripción por lotes terminada: %d hechas, %d fallidas",
                 self.hechas, self.fallidas)
        wx.MessageBox(mensaje, titulo, wx.OK | wx.ICON_INFORMATION, self)

    def _bloquear(self, trabajando: bool) -> None:
        """Deja activo solo lo que se puede tocar en cada momento."""
        for control in (self.eleccion, self.saltar_con_texto, self.pausa):
            control.Enable(not trabajando)
        self.boton_empezar.Enable(not trabajando and bool(self._pendientes))
        self.boton_parar.Enable(trabajando)

    # -- parada y cierre -----------------------------------------------------

    def _al_parar(self, evento) -> None:
        """Pide que se pare en cuanto termine la imagen en curso."""
        if not self._trabajando:
            return
        self._parar.set()
        self.estado.SetLabel(_("Deteniendo: se parará al terminar la imagen en curso..."))
        self._voz.decir(_("Deteniendo. Se parará al terminar la imagen en curso."))

    def _al_pulsar_cerrar(self, evento) -> None:
        """El botón «Cerrar» de un diálogo modal no pasa por EVT_CLOSE."""
        if self._trabajando:
            self._al_parar(None)
            return
        self.EndModal(wx.ID_CANCEL)

    def _al_cerrar(self, evento) -> None:
        """No deja cerrar mientras se trabaja: primero hay que detenerlo."""
        if self._trabajando:
            self._al_parar(None)
            if evento.CanVeto():
                evento.Veto()
            return
        evento.Skip()
