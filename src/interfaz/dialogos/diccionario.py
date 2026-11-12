# -*- coding: utf-8 -*-
"""Ventana para definir una palabra sin salir del documento.

Se abre con la palabra del cursor ya puesta y **la consulta ya en marcha**: en
la inmensa mayoría de los casos no hay que escribir ni elegir nada, solo
escuchar.  La palabra se puede cambiar para buscar otra, y la fuente —RAE,
Wikcionario o inteligencia artificial— se cambia sin cerrar nada, porque
ninguna de las tres es siempre la mejor: la RAE es la referencia del español,
el Wikcionario cubre los demás idiomas y la IA es la única que entiende en qué
sentido se usa la palabra *en esta frase*.

La definición va en un cuadro de texto de solo lectura y no en una etiqueta,
para poder recorrerla con las flechas y releer una acepción concreta, que es
como se consulta un diccionario de oído.
"""

from __future__ import annotations

import threading

import wx

from interfaz.accesible import etiquetar, fila_etiquetada
from interfaz.anuncios import Voz
from interfaz.dialogos import ayuda_opcion
from nucleo import diccionario
from nucleo.idioma import _
from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

MARGEN = 8


class DialogoDiccionario(wx.Dialog):
    """Consulta una palabra y enseña lo que diga la fuente elegida.

    :param padre: Ventana principal.
    :param palabra: Palabra con la que empezar, normalmente la del cursor.
    :param contexto: Frase del documento donde aparece, que es lo que se le
                     pasa a la inteligencia artificial para que sepa de qué
                     acepción se habla.
    :param servicio_ia: Servicio de IA de la aplicación, o ``None``.
    :param configuracion: Preferencias, de donde sale y a donde vuelve la
                          última fuente usada.
    """

    def __init__(self, padre: wx.Window, palabra: str, contexto: str,
                 servicio_ia, configuracion) -> None:
        super().__init__(padre, title=_("Diccionario"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.servicio_ia = servicio_ia
        self.configuracion = configuracion
        self.contexto = contexto
        self._consultando = False
        #: Número de consulta.  Al llegar una respuesta se comprueba que es la
        #: de la última petición: si no, la respuesta lenta de una consulta
        #: anterior pisaría a la nueva.
        self._turno = 0
        self.voz = Voz(self)
        self.entrada: diccionario.Entrada | None = None

        contenedor = wx.BoxSizer(wx.VERTICAL)

        self.palabra = fila_etiquetada(
            self, contenedor, _("&Palabra:"),
            lambda p: wx.TextCtrl(p, value=palabra or "", style=wx.TE_PROCESS_ENTER),
            margen=MARGEN, horizontal=True, proporcion=1)
        self.palabra.Bind(wx.EVT_TEXT_ENTER, lambda evento: self._consultar())

        claves = [clave for clave, _nombre in diccionario.FUENTES]
        self.fuente = fila_etiquetada(
            self, contenedor, _("&Buscar en:"),
            lambda p: wx.Choice(p, choices=[nombre for _clave, nombre in diccionario.FUENTES]),
            margen=MARGEN, horizontal=True)
        guardada = str(configuracion.obtener("diccionario_fuente", diccionario.RAE))
        self.fuente.SetSelection(claves.index(guardada) if guardada in claves else 0)
        self.fuente.Bind(wx.EVT_CHOICE, lambda evento: self._consultar())

        self.resultado = wx.TextCtrl(
            self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP,
            size=(620, 320))
        etiquetar(self.resultado, _("Definición"))
        contenedor.Add(self.resultado, 1, wx.EXPAND | wx.ALL, MARGEN)

        botones = wx.BoxSizer(wx.HORIZONTAL)
        self.boton_buscar = wx.Button(self, label=_("&Buscar"))
        self.boton_buscar.Bind(wx.EVT_BUTTON, lambda evento: self._consultar())
        self.boton_buscar.SetDefault()
        botones.Add(self.boton_buscar, 0, wx.ALL, 5)
        boton_copiar = wx.Button(self, label=_("&Copiar"))
        boton_copiar.Bind(wx.EVT_BUTTON, self._al_copiar)
        botones.Add(boton_copiar, 0, wx.ALL, 5)
        boton_cerrar = wx.Button(self, wx.ID_CANCEL, _("Ce&rrar"))
        botones.Add(boton_cerrar, 0, wx.ALL, 5)
        contenedor.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 4)

        self.SetSizerAndFit(contenedor)
        self.CenterOnParent()
        self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar_tecla)
        ayuda_opcion.enganchar(self)
        self.palabra.SetFocus()
        self.palabra.SelectAll()

        # Con una palabra delante no hay nada que preguntar: se busca sola.
        if diccionario.es_valida(diccionario.limpiar(palabra or "")):
            wx.CallAfter(self._consultar)

    # -- teclado --------------------------------------------------------------

    def _al_pulsar_tecla(self, evento: wx.KeyEvent) -> None:
        """Escape cierra; F5 vuelve a consultar."""
        codigo = evento.GetKeyCode()
        if codigo == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
            return
        if codigo == wx.WXK_F5:
            self._consultar()
            return
        evento.Skip()

    def _al_copiar(self, evento) -> None:
        """Deja la definición en el portapapeles."""
        texto = self.resultado.GetValue().strip()
        if not texto:
            self.voz.decir(_("No hay nada que copiar."))
            return
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(texto))
            wx.TheClipboard.Close()
            self.voz.decir(_("Definición copiada."))

    # -- consulta -------------------------------------------------------------

    def _clave_fuente(self) -> str:
        """Identificador de la fuente elegida en el desplegable."""
        indice = max(0, self.fuente.GetSelection())
        return diccionario.FUENTES[indice][0]

    def _consultar(self) -> None:
        """Lanza la consulta en otro hilo.

        En otro hilo porque son peticiones de red: hacerlas aquí dejaría la
        ventana congelada, y con ella al lector de pantalla, justo mientras se
        espera la respuesta.
        """
        if self._consultando:
            return
        palabra = diccionario.limpiar(self.palabra.GetValue())
        if not diccionario.es_valida(palabra):
            self._mostrar(_("Escribe una palabra para buscarla."))
            self.palabra.SetFocus()
            return
        fuente = self._clave_fuente()
        self.configuracion.establecer("diccionario_fuente", fuente)
        if fuente == diccionario.IA and (self.servicio_ia is None
                                         or not self.servicio_ia.activa):
            self._mostrar(_(
                "La inteligencia artificial no está configurada.\n\n"
                "Se configura en Opciones, pestaña Inteligencia artificial. Mientras "
                "tanto puedes usar la RAE o el Wikcionario, que no necesitan nada."))
            return

        self._consultando = True
        self._turno += 1
        turno = self._turno
        self.boton_buscar.Disable()
        self._mostrar(_("Buscando «%s»...") % palabra)

        idioma_wiki = str(self.configuracion.obtener("diccionario_idioma", "es") or "es")
        contexto = self.contexto

        def trabajo() -> None:
            entrada = diccionario.definir(
                palabra, fuente, servicio=self.servicio_ia,
                contexto=contexto, idioma_wiki=idioma_wiki)
            wx.CallAfter(self._con_respuesta, turno, entrada)

        threading.Thread(target=trabajo, name="diccionario", daemon=True).start()

    def _con_respuesta(self, turno: int, entrada: diccionario.Entrada) -> None:
        """Enseña lo que haya contestado la fuente."""
        self._consultando = False
        if not self:
            return
        self.boton_buscar.Enable()
        if turno != self._turno:
            # Ha llegado tarde: mientras tanto se ha pedido otra cosa.
            return
        self.entrada = entrada
        if entrada.error and entrada.vacia:
            self._mostrar(entrada.error)
            return
        self._mostrar(entrada.legible())

    def _mostrar(self, texto: str) -> None:
        """Pone el texto en el cuadro y lo dice.

        Se dice **entero**: una definición es justo lo que se ha venido a oír, y
        cortarla en el primer renglón obligaría a ir a buscarla con el cursor.
        """
        self.resultado.SetValue(texto)
        self.resultado.SetInsertionPoint(0)
        self.voz.decir(texto)
