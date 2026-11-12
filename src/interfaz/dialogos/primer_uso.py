# -*- coding: utf-8 -*-
"""Recorrido guiado de la primera vez.

Un programa que se maneja con cincuenta teclas es rapidísimo cuando ya te lo
sabes e impenetrable el primer día.  La pantalla de bienvenida las lista todas,
pero una lista de cincuenta atajos leída de corrido no se retiene: se oye, se
olvida y hay que volver a buscarla.

Este recorrido las enseña **de una en una**, cada una en su pantalla, contando
para qué sirve y, sobre todo, **dejándola probar ahí mismo**: en los pasos que
enseñan una tecla hay un recuadro donde pulsarla, y el programa dice si era esa.
Aprender una tecla pulsándola cuesta una vez; leyéndola en una lista, varias.

Se ofrece solo la primera vez que se abre el programa, se puede saltar de
principio a fin, y queda para siempre en **Ayuda → Recorrido guiado**, porque a
las tres semanas uno quiere repasar justo la parte que no usó.
"""

from __future__ import annotations

from typing import NamedTuple

import wx

from interfaz import atajos as tabla_atajos
from interfaz.dialogos import ayuda_opcion
from interfaz.accesible import etiquetar
from interfaz.anuncios import Voz
from nucleo.idioma import _
from nucleo.registro import obtener_registro
from version import NOMBRE

log = obtener_registro(__name__)

MARGEN = 10


class Paso(NamedTuple):
    """Una pantalla del recorrido.

    :param titulo: Encabezado corto, que es lo primero que se oye.
    :param texto: La explicación.
    :param tecla: Tecla que se puede practicar, si el paso enseña una.  Va como
                  código de wxPython o como carácter suelto en mayúscula.
    :param descripcion_tecla: Cómo se dice esa tecla en voz alta.
    :param ajustes: Ajustes que se pueden encender o apagar **desde el propio
                    recorrido**, cada uno como
                    ``(clave, etiqueta, valor encendido, valor apagado)``.
                    Existe porque las encuestas insisten en algo incómodo: la
                    función de accesibilidad que hay que activar no la
                    encuentra quien la necesita.  Explicarla y no dejar
                    activarla aquí mismo es la mitad del trabajo.
    :param apartado: A qué parte del recorrido pertenece este paso.  Sirve para
                     poder **volver a una sola parte**: la primera vez se hace
                     entero, pero al mes uno quiere repasar solo lo de la voz, y
                     atravesar diecisiete pantallas para llegar no lo hace nadie.
    """

    titulo: str
    texto: str
    tecla: object = None
    descripcion_tecla: str = ""
    ajustes: tuple = ()
    apartado: str = ""


def apartados() -> list[str]:
    """Las partes del recorrido, en el orden en que aparecen.

    Se sacan de los propios pasos y no de una lista aparte: así, al añadir un
    paso nuevo, su apartado aparece solo y no hay dos sitios que puedan
    contradecirse.
    """
    vistos = []
    for paso in pasos():
        if paso.apartado and paso.apartado not in vistos:
            vistos.append(paso.apartado)
    return vistos


def pasos_de(apartado: str) -> list[Paso]:
    """Los pasos de un apartado. Sin apartado, el recorrido entero."""
    todos = pasos()
    if not apartado:
        return todos
    elegidos = [paso for paso in todos if paso.apartado == apartado]
    return elegidos or todos


def pasos() -> list[Paso]:
    """Construye el recorrido.

    Es una función y no una constante porque los textos van traducidos y el
    idioma se elige después de importar el módulo.
    """
    return [
        Paso(_("Bienvenido"), _(
            "Esto es %(nombre)s, un visor de documentos pensado para leer con el teclado y "
            "con lector de pantalla.\n\n"
            "Este recorrido enseña lo esencial en unos minutos, una tecla por pantalla. "
            "Puedes probar cada tecla aquí mismo antes de seguir.\n\n"
            "Para moverte: el botón «Siguiente» avanza y «Anterior» retrocede. Puedes "
            "salir cuando quieras con Escape o con el botón «Salir del recorrido»; y si lo "
            "dejas a medias, vuelve a estar entero en Ayuda, Recorrido guiado.") % {
                "nombre": NOMBRE},
             apartado=_("Lo primero")),

        Paso(_("Abrir un documento"), _(
            "Con Control+O se elige un documento del disco. También puedes arrastrar el "
            "archivo sobre la ventana, o abrirlo desde el explorador de Windows.\n\n"
            "Se abren EPUB, PDF, Word, LibreOffice, DAISY, FictionBook, RTF, páginas web, "
            "Markdown y texto. Si el PDF está escaneado, el programa lo reconoce con OCR "
            "para que haya algo que leer.\n\n"
            "Los libros DAISY son una carpeta entera, no un archivo: para esos está "
            "Control+Mayús+O.\n\n"
            "Pruébalo aquí: pulsa Control+O."),
            tecla=("O", wx.MOD_CONTROL), descripcion_tecla=_("Control+O"),
             apartado=_("Lo primero")),

        Paso(_("Leer"), _(
            "El documento aparece en un cuadro de texto normal de Windows, así que valen "
            "todas las órdenes de lectura de tu lector de pantalla.\n\n"
            "Hay un detalle importante: **aquí una línea es un párrafo entero**. La flecha "
            "abajo avanza un párrafo completo y el lector lo lee de una vez, que es como se "
            "lee un libro y no como se lee una pantalla.\n\n"
            "El programa recuerda por dónde ibas en cada documento y vuelve ahí al abrirlo.\n\n"
            "Pruébalo: pulsa la flecha abajo."),
            tecla=(wx.WXK_DOWN, 0), descripcion_tecla=_("flecha abajo"),
             apartado=_("Moverse por el texto")),

        Paso(_("Saltar de un elemento a otro"), _(
            "Esta es la parte más útil del programa, y la que más tiempo ahorra.\n\n"
            "Con **una sola tecla** saltas al siguiente elemento de un tipo: H al siguiente "
            "encabezado, T a la siguiente tabla, G a la siguiente imagen, L a la siguiente "
            "lista, K al siguiente enlace, P a la página siguiente. Con Mayús, hacia atrás.\n\n"
            "Son las mismas teclas que ya usas en las páginas web con tu lector de "
            "pantalla, así que no hay nada nuevo que aprender.\n\n"
            "Pruébalo: pulsa H."),
            tecla=("H", 0), descripcion_tecla=_("H"),
             apartado=_("Moverse por el texto")),

        Paso(_("Los sonidos"), _(
            "Cada vez que el cursor entra en una línea donde empieza un elemento suena un "
            "aviso corto y distinto: un tono limpio para un encabezado, dos toques para una "
            "imagen, un acorde grave para una tabla.\n\n"
            "Sirve para saberlo **sin esperar** a que la voz lo diga, que es lo que hace "
            "que recorrer un documento sea rápido.\n\n"
            "Se silencian con Control+Alt+S, y en Opciones, pestaña Sonidos, puedes "
            "escucharlos uno a uno para aprenderlos y ajustar su volumen."),
             apartado=_("La voz y los sonidos")),

        Paso(_("Saber dónde estás"), _(
            "La tecla D dice por dónde vas: capítulo, página, porcentaje y línea. Es la "
            "tecla que más se acaba usando.\n\n"
            "La tecla R repite el último aviso, para cuando el lector de pantalla se ha "
            "pisado a sí mismo y no te ha dado tiempo a oírlo.\n\n"
            "Pruébalo: pulsa D."),
            tecla=("D", 0), descripcion_tecla=_("D"),
             apartado=_("Moverse por el texto")),

        Paso(_("Ver qué hay dentro del documento"), _(
            "Control+T abre el índice de capítulos, ya colocado en el capítulo que estás "
            "leyendo. Si el documento no trae índice, se construye con sus encabezados.\n\n"
            "F7 abre la lista de elementos: eliges arriba qué quieres ver —encabezados, "
            "enlaces, imágenes, tablas— y debajo salen todos con su número. Es la forma "
            "más rápida de hacerte una idea de un documento que no conoces.\n\n"
            "Pruébalo: pulsa Control+T."),
            tecla=("T", wx.MOD_CONTROL), descripcion_tecla=_("Control+T"),
             apartado=_("Moverse por el texto")),

        Paso(_("Buscar"), _(
            "Control+F abre el cuadro de búsqueda. Escribes, pulsas Intro y el cuadro se "
            "queda abierto para encadenar búsquedas; F3 busca la siguiente y Mayús+F3 la "
            "anterior.\n\n"
            "El botón «Contar» dice cuántas veces aparece la palabra en todo el documento, "
            "que muchas veces es justo lo que se quería saber.\n\n"
            "Pruébalo: pulsa Control+F."),
            tecla=("F", wx.MOD_CONTROL), descripcion_tecla=_("Control+F"),
             apartado=_("Moverse por el texto")),

        Paso(_("Marcadores y notas"), _(
            "Control+M pone o quita un marcador donde esté el cursor. Control+Mayús+M "
            "escribe una nota, que es un marcador con un texto tuyo.\n\n"
            "Después, la tecla B salta al marcador siguiente y la N a la nota siguiente. "
            "Control+B abre la lista completa.\n\n"
            "Todo se guarda por documento y sigue ahí la próxima vez.\n\n"
            "Pruébalo: pulsa Control+M."),
            tecla=("M", wx.MOD_CONTROL), descripcion_tecla=_("Control+M"),
             apartado=_("Estudiar")),

        Paso(_("Escuchar el documento"), _(
            "Además de tu lector de pantalla, el programa tiene su propia voz para leer el "
            "documento seguido.\n\n"
            "Control+Espacio empieza a leer desde el cursor; si ya está leyendo, pausa; si "
            "está en pausa, continúa. Control+Mayús+Espacio detiene.\n\n"
            "Las flechas Control+Alt izquierda y derecha van frase a frase, y Control+Alt "
            "arriba y abajo cambian la velocidad sin cortar la lectura.\n\n"
            "En un libro DAISY con grabación, esas mismas teclas mandan sobre la voz del "
            "narrador.\n\n"
            "Pruébalo: pulsa Control+Espacio."),
            tecla=(wx.WXK_SPACE, wx.MOD_CONTROL), descripcion_tecla=_("Control+Espacio"),
             apartado=_("La voz y los sonidos")),

        Paso(_("Las imágenes"), _(
            "En el texto, una imagen aparece como «Imagen» seguido de su descripción, si es "
            "que el documento trae alguna. Muchas veces no la trae, o son tres palabras que "
            "no dicen nada.\n\n"
            "Con la tecla A, sobre una imagen, se le pide a una inteligencia artificial que "
            "cuente lo que se ve. La descripción se guarda y vuelve con el documento, así "
            "que se paga una vez y sirve siempre.\n\n"
            "Viene desactivado y se configura en Opciones, pestaña Inteligencia artificial: "
            "hay una opción gratuita y otra que funciona sin conexión.\n\n"
            "Pruébalo: pulsa A."),
            tecla=("A", 0), descripcion_tecla=_("A"),
             apartado=_("Las imágenes")),

        Paso(_("Definir una palabra"), _(
            "Leyendo aparecen palabras que uno no conoce. Con la tecla V se define la "
            "palabra del cursor sin salir del documento.\n\n"
            "Se puede buscar en el diccionario de la Real Academia, en el Wikcionario —que "
            "cubre cualquier idioma— o preguntándoselo a la inteligencia artificial, que es "
            "la única que entiende en qué sentido se usa la palabra en esa frase.\n\n"
            "Pruébalo: pulsa V."),
            tecla=("V", 0), descripcion_tecla=_("V"),
             apartado=_("Estudiar")),

        Paso(_("El cuaderno y el repaso"), _(
            "Lo que marcas en un libro no se queda en ese libro. En la biblioteca "
            "(Control+Mayús+B), el botón «Cuaderno de estudio» junta las notas y los "
            "resaltados de todos los libros que estés viendo y los agrupa por tema, "
            "diciendo de qué libro sale cada cosa.\n\n"
            "Y desde ahí, el botón «Repasar» te los va devolviendo cuando toca: cada "
            "resaltado es una tarjeta. Primero ves de dónde sale, pulsas Espacio para "
            "descubrir el pasaje y respondes con 1, 2 o 3. Lo que sabes tarda cada vez "
            "más en volver; lo que no, vuelve mañana.\n\n"
            "Pruébalo: pulsa Control+Mayús+B."),
            tecla=("B", wx.MOD_CONTROL | wx.MOD_SHIFT),
            descripcion_tecla=_("Control+Mayús+B"),
             apartado=_("Estudiar")),

        Paso(_("Las opciones"), _(
            "Control+Alt+O abre las opciones. Son nueve pestañas y te mueves entre ellas "
            "con Control+Tabulador.\n\n"
            "Hay una cosa que conviene saber: **Control+F1 sobre cualquier ajuste** abre "
            "una ventana que explica qué es, qué consigue y qué conviene poner. No hace "
            "falta adivinar para qué sirve nada.\n\n"
            "Pruébalo: pulsa Control+Alt+O."),
            tecla=("O", wx.MOD_CONTROL | wx.MOD_ALT), descripcion_tecla=_("Control+Alt+O"),
             apartado=_("Ajustes y ayuda")),

        Paso(_("Dónde está la ayuda"), _(
            "F1, o Control+F1 si algún otro programa te captura F1, abre el manual completo "
            "en el navegador.\n\n"
            "Mayús+F1 muestra la lista de todos los atajos, siempre al día porque se genera "
            "del propio programa.\n\n"
            "Y este recorrido queda en Ayuda, Recorrido guiado, por si quieres repasarlo.\n\n"
            "Al lado hay otra cosa que conviene conocer: Ayuda, Practicar. Ahí el "
            "programa te va pidiendo cosas cortas —ve al tercer encabezado, pon un "
            "marcador— sobre el libro que tengas abierto, y te avisa en cuanto "
            "salen. Leer una tecla y usarla no son lo mismo.\n\n"
            "Pruébalo: pulsa Mayús+F1."),
            tecla=(wx.WXK_F1, wx.MOD_SHIFT), descripcion_tecla=_("Mayús+F1"),
             apartado=_("Ajustes y ayuda")),

        Paso(_("Las cinco que más cambian"), _(
            "Estas cinco cosas son las que más se agradecen, y las que más gente no "
            "llega a encontrar. Puedes encenderlas o apagarlas aquí mismo, ahora, y "
            "cambiarlas después en Opciones cuando quieras.\n\n"
            "Muévete con el tabulador hasta las casillas y márcalas con la barra "
            "espaciadora."),
            ajustes=(
                ("sonidos_activados",
                 _("&Sonidos al pasar por un título, una tabla o una imagen"),
                 True, False),
                ("ia_anunciar_descripcion",
                 _("&Decir la descripción guardada al llegar a una imagen"),
                 True, False),
                ("voz_leer_descripciones",
                 _("Leer también la descripción de las imágenes al escuchar el &libro"),
                 True, False),
                ("ancho_maximo_linea",
                 _("Renglones de &ancho cómodo (unos 80 caracteres) en vez de toda "
                   "la ventana"),
                 80, 0),
                ("marcar_llamadas_de_nota",
                 _("Señalar las llamadas de &nota al pie, para saltar de una a otra "
                   "con la O"),
                 True, False),
            ),
             apartado=_("Ajustes y ayuda")),

        Paso(_("Ya está"), _(
            "Eso es lo esencial. Lo demás se descubre solo, y siempre está el manual.\n\n"
            "Tres cosas que la gente agradece encontrar:\n\n"
            "Control+Alt+V ajusta la voz, la velocidad y el volumen de la lectura.\n\n"
            "En el menú Voz hay un diccionario de pronunciación, para que los nombres de "
            "una saga dejen de sonar mal, y un temporizador de apagado para dormirse "
            "escuchando.\n\n"
            "En Archivo, Exportar, el documento se puede pasar a texto, Markdown, página "
            "web, EPUB o audio en MP3.\n\n"
            "Y si quieres afianzarlo, en Ayuda, Practicar el programa te propone "
            "ejercicios cortos sobre el documento que tengas abierto.\n\n"
            "Pulsa «Terminar» para empezar a leer."),
             apartado=_("Ajustes y ayuda")),
    ]


class DialogoPrimerUso(wx.Dialog):
    """El recorrido guiado, una pantalla por paso.

    :param padre: Ventana principal.
    :param configuracion: Preferencias, donde se anota que ya se ha hecho.
    :param apartado: Parte que se quiere repasar.  Vacío es el recorrido
                     entero, que es lo que se hace la primera vez.
    """

    def __init__(self, padre: wx.Window, configuracion,
                 apartado: str = "") -> None:
        titulo = (_("Recorrido guiado: %s") % apartado if apartado
                  else _("Recorrido guiado"))
        super().__init__(padre, title=titulo,
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.configuracion = configuracion
        self.apartado = apartado
        self.pasos = pasos_de(apartado)
        self.actual = 0
        self.voz = Voz(self)

        contenedor = wx.BoxSizer(wx.VERTICAL)

        self.titulo = wx.StaticText(self, label="")
        fuente = self.titulo.GetFont()
        fuente.SetPointSize(fuente.GetPointSize() + 3)
        self.titulo.SetFont(fuente.Bold())
        contenedor.Add(self.titulo, 0, wx.ALL, MARGEN)

        # Cuadro de solo lectura y no una etiqueta: así el texto se recorre con
        # las flechas y se puede releer la parte que interese, que es lo que
        # hace falta para aprender algo y no solo para oírlo pasar.
        self.texto = wx.TextCtrl(
            self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP,
            size=(640, 300))
        etiquetar(self.texto, _("Explicación del paso"))
        contenedor.Add(self.texto, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, MARGEN)

        self.practica = wx.TextCtrl(self, style=wx.TE_READONLY | wx.TE_CENTER,
                                    value="")
        etiquetar(self.practica, _("Recuadro para practicar la tecla"))
        #: Casillas del paso que trae ajustes.  Se crean y se destruyen con el
        #: paso, porque solo uno los tiene.
        self._casillas: list = []
        self._caja_ajustes = wx.BoxSizer(wx.VERTICAL)
        self.practica.Bind(wx.EVT_CHAR_HOOK, self._al_practicar)
        contenedor.Add(self.practica, 0, wx.EXPAND | wx.ALL, MARGEN)
        contenedor.Add(self._caja_ajustes, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, MARGEN)
        #: Hace falta guardarlo para poder recolocar las casillas al cambiar de
        #: paso: las casillas se crean y se destruyen con el paso que las trae.
        self._contenedor = contenedor

        botones = wx.BoxSizer(wx.HORIZONTAL)
        self.boton_anterior = wx.Button(self, label=_("&Anterior"))
        self.boton_anterior.Bind(wx.EVT_BUTTON, lambda evento: self._mover(-1))
        botones.Add(self.boton_anterior, 0, wx.ALL, 5)
        self.boton_siguiente = wx.Button(self, label=_("&Siguiente"))
        self.boton_siguiente.Bind(wx.EVT_BUTTON, lambda evento: self._mover(1))
        self.boton_siguiente.SetDefault()
        botones.Add(self.boton_siguiente, 0, wx.ALL, 5)
        self.boton_salir = wx.Button(self, wx.ID_CANCEL, _("Salir del &recorrido"))
        botones.Add(self.boton_salir, 0, wx.ALL, 5)
        contenedor.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 4)

        self.SetSizerAndFit(contenedor)
        self.SetSize((720, 560))
        self.CenterOnParent()
        self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar_tecla)
        self._pintar()
        self.texto.SetFocus()
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    # -- movimiento -----------------------------------------------------------

    def _al_pulsar_tecla(self, evento: wx.KeyEvent) -> None:
        """Escape sale del recorrido; el resto sigue su camino."""
        if evento.GetKeyCode() == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
            return
        evento.Skip()

    def _mover(self, salto: int) -> None:
        """Pasa al paso siguiente o al anterior; al final, cierra."""
        destino = self.actual + salto
        if destino >= len(self.pasos):
            self.EndModal(wx.ID_OK)
            return
        self.actual = max(0, destino)
        self._pintar()

    def _pintar(self) -> None:
        """Enseña el paso actual y lo dice entero."""
        paso = self.pasos[self.actual]
        cuenta = _("Paso %(numero)d de %(total)d") % {
            "numero": self.actual + 1, "total": len(self.pasos)}
        self.titulo.SetLabel("%s — %s" % (cuenta, paso.titulo))
        self.texto.SetValue(paso.texto)
        self.texto.SetInsertionPoint(0)

        if paso.tecla is not None:
            self.practica.SetValue(_("Pulsa aquí %s") % paso.descripcion_tecla)
            self.practica.Show()
        else:
            self.practica.SetValue("")
            self.practica.Hide()
        self._pintar_ajustes(paso)
        self.Layout()

        self.boton_anterior.Enable(self.actual > 0)
        ultimo = self.actual == len(self.pasos) - 1
        self.boton_siguiente.SetLabel(_("&Terminar") if ultimo else _("&Siguiente"))
        self.voz.decir("%s. %s" % (self.titulo.GetLabel(), paso.texto))
        self.texto.SetFocus()

    # -- ajustes que se pueden encender aquí mismo -----------------------------

    def _pintar_ajustes(self, paso: Paso) -> None:
        """Pone —o quita— las casillas del paso.

        Cada casilla escribe su ajuste **en cuanto se marca**, sin botón de
        aceptar: el recorrido se puede abandonar en cualquier momento y lo que
        se haya encendido tiene que quedar encendido.
        """
        for casilla in self._casillas:
            casilla.Destroy()
        self._casillas = []
        self._caja_ajustes.Clear()
        for clave, etiqueta, encendido, apagado in paso.ajustes:
            casilla = wx.CheckBox(self, label=etiqueta)
            casilla.SetValue(self.configuracion.obtener(clave) == encendido)
            casilla.Bind(wx.EVT_CHECKBOX,
                         lambda evento, c=clave, si=encendido, no=apagado:
                         self._al_marcar(c, si, no, evento.IsChecked()))
            self._caja_ajustes.Add(casilla, 0, wx.ALL, 4)
            self._casillas.append(casilla)

    def _al_marcar(self, clave: str, encendido, apagado, marcada: bool) -> None:
        """Guarda el ajuste que se acaba de marcar o desmarcar."""
        self.configuracion.establecer(clave, encendido if marcada else apagado)
        self.configuracion.guardar()
        log.info("Recorrido guiado: %s = %r", clave, encendido if marcada else apagado)
        padre = self.GetParent()
        aplicar = getattr(padre, "aplicar_preferencias", None)
        if callable(aplicar):
            # Se aplica al momento: encender los sonidos y no oírlos hasta
            # reiniciar haría dudar de si se ha encendido algo.
            aplicar()

    # -- práctica --------------------------------------------------------------

    def _al_practicar(self, evento: wx.KeyEvent) -> None:
        """Comprueba si la tecla pulsada en el recuadro es la del paso.

        Se atiende con ``EVT_CHAR_HOOK`` para ver también las combinaciones con
        Control, que un cuadro de texto normal no llega a recibir.
        """
        paso = self.pasos[self.actual]
        if paso.tecla is None:
            evento.Skip()
            return
        codigo = evento.GetKeyCode()
        if codigo == wx.WXK_ESCAPE or codigo == wx.WXK_TAB:
            evento.Skip()
            return

        esperada, modificadores = paso.tecla
        puestos = 0
        if evento.ControlDown():
            puestos |= wx.MOD_CONTROL
        if evento.AltDown():
            puestos |= wx.MOD_ALT
        if evento.ShiftDown():
            puestos |= wx.MOD_SHIFT

        if isinstance(esperada, str):
            acierto = (chr(codigo).upper() == esperada if 32 <= codigo < 0x110000 else False)
        else:
            acierto = codigo == esperada
        acierto = acierto and puestos == modificadores

        if acierto:
            self.practica.SetValue(_("¡Eso es! %s") % paso.descripcion_tecla)
            self.voz.decir(_("Correcto: %(tecla)s. Pulsa Tabulador y luego Intro en "
                             "«Siguiente» para continuar.") % {
                                 "tecla": paso.descripcion_tecla})
        else:
            # Solo se corrige si la pulsación era algo, no si era un modificador
            # suelto: al componer Control+O se ve pasar primero el Control.
            if codigo not in (wx.WXK_CONTROL, wx.WXK_ALT, wx.WXK_SHIFT):
                self.voz.decir(_("Esa no. Prueba con %s.") % paso.descripcion_tecla)

    # -- cierre ----------------------------------------------------------------

    def marcar_hecho(self) -> None:
        """Anota que el recorrido ya se ha ofrecido, para no repetirlo."""
        self.configuracion.establecer("primer_uso_hecho", True)
        self.configuracion.guardar()
        log.info("Recorrido guiado completado o cerrado")


def hace_falta(configuracion) -> bool:
    """Indica si hay que ofrecer el recorrido.

    Solo la primera vez.  Se comprueba una marca propia y no la ausencia de
    documentos recientes: quien abre el programa, mira y lo cierra sin abrir
    nada no debería encontrarse el recorrido otra vez al día siguiente.
    """
    return not bool(configuracion.obtener("primer_uso_hecho", False))
