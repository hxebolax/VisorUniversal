# -*- coding: utf-8 -*-
"""Cuadro de diálogo de preferencias.

Las opciones se agrupan en pestañas (``wx.Notebook``), que los lectores de
pantalla anuncian correctamente y se recorren con Control+Tabulador.

Todos los controles reciben su nombre accesible de forma explícita mediante
:mod:`interfaz.accesible`, en lugar de confiar en que Windows lo deduzca del
texto que tienen al lado.  Se comprobó leyendo el nombre real que expone cada
control: ``wx.SpinCtrl`` no exponía ninguno y el selector de color del sistema
anunciaba solo «colourpicker».

Los colores se eligen de una lista con nombres («Amarillo», «Negro»,
«Azul cielo»…) y no de la rejilla del sistema, que sin ver la pantalla es
inservible.  Véase :mod:`interfaz.colores`.

Algunas opciones exigen volver a analizar el libro (las que cambian cómo se
convierte el texto).  El diálogo las señala en su propia etiqueta y avisa al
cerrarse, en lugar de rehacer el trabajo por sorpresa.
"""

from __future__ import annotations

import threading

import wx

from formatos import ocr
from interfaz import colores
from interfaz.accesible import etiquetar, fila_etiquetada
from interfaz import teclas_globales
from interfaz.dialogos import ayuda_opcion
from interfaz.dialogos import progreso as dialogos_progreso
from interfaz.dialogos.espera import ejecutar_esperando
from interfaz.listas import ListaAccesible, ListaCasillas, rellenar_columnas
from nucleo import actualizaciones, cache, descripciones, idioma, integracion
from nucleo import registro as modulo_registro
from nucleo.ia import consumo as ia_consumo
from nucleo.ia import openai as ia_openai
from nucleo.ia import servicio as ia_servicio
from nucleo.idioma import _, _n
from nucleo.registro import obtener_registro, registrar_excepcion

log = obtener_registro(__name__)

MARGEN = 8

#: Opciones cuyo cambio obliga a analizar el libro otra vez.
#:
#: Las tres primeras cambian el texto de cualquier documento.  Las demás son de
#: PDF y de reconocimiento, y están aquí por un motivo distinto: **no forman
#: parte de la firma con la que se guarda el análisis**, así que el libro que
#: ya estaba abierto seguiría saliendo exactamente igual por bueno que sea el
#: ajuste nuevo.  Quien enciende el reconocimiento de texto o sube el tope de
#: páginas lo hace por el documento que tiene delante, y tenía que ir a borrar
#: sus datos guardados para verlo.  Ahora se le ofrece releerlo, que es lo
#: mismo sin perder los marcadores.
OPCIONES_QUE_REANALIZAN = ("tablas_en_linea", "anunciar_imagenes_sin_texto",
                           "marcar_llamadas_de_nota", "solo_articulo",
                           "pdf_estructura", "pdf_geometria",
                           "pdf_ocr_modo", "pdf_ocr_maximo", "pdf_ocr_idiomas",
                           "pdf_ocr_escala", "pdf_ocr_psm", "pdf_ocr_oem",
                           "pdf_ocr_dpi", "pdf_ocr_confianza", "pdf_ocr_gris",
                           "pdf_ocr_contraste", "pdf_ocr_binarizar",
                           "pdf_ocr_umbral", "pdf_ocr_quitar_simbolos",
                           "pdf_ocr_tablas", "pdf_ocr_esmerado")


class SelectorColor:
    """Lista desplegable para elegir un color por su nombre.

    Sustituye al selector del sistema.  La última opción, «Otro color…», sí
    abre el selector del sistema para quien quiera un tono exacto; al elegirlo
    se añade a la lista con su valor, de modo que después se pueda reconocer.

    :param padre: Ventana donde se crea.
    :param contenedor: Organizador al que se añade la fila.
    :param etiqueta: Texto de la etiqueta, por ejemplo ``"&Color del texto:"``.
    :param valor: Color inicial en hexadecimal, o cadena vacía.
    """

    def __init__(self, padre: wx.Window, contenedor: wx.Sizer, etiqueta: str, valor: str) -> None:
        self._padre = padre
        self._personalizado = ""
        self.control = fila_etiquetada(
            padre, contenedor, etiqueta,
            lambda p: wx.Choice(p, choices=colores.nombres()),
            horizontal=True, proporcion=1,
        )
        self.control.Bind(wx.EVT_CHOICE, self._al_elegir)
        self.establecer(valor)

    def establecer(self, valor: str) -> None:
        """Selecciona en la lista el color indicado."""
        indice = colores.indice_de(valor)
        if indice >= 0:
            self.control.SetSelection(indice)
            self._personalizado = ""
            return
        if valor:
            # Un color que no está en la paleta se añade con su nombre
            # descriptivo para que quede seleccionable y se anuncie.
            self._personalizado = valor
            self._refrescar_personalizado()
        else:
            self.control.SetSelection(0)

    def _refrescar_personalizado(self) -> None:
        """Coloca el color propio como última opción y lo selecciona."""
        entradas = colores.nombres()
        entradas[-1] = colores.nombre_de(self._personalizado)
        entradas.append(colores.PERSONALIZADO)
        self.control.Set(entradas)
        self.control.SetSelection(len(entradas) - 2)

    def _al_elegir(self, evento) -> None:
        """Si se elige «Otro color…», abre el selector del sistema."""
        if self.control.GetStringSelection() != colores.PERSONALIZADO:
            return
        datos = wx.ColourData()
        datos.SetChooseFull(True)
        if self._personalizado:
            datos.SetColour(wx.Colour(self._personalizado))
        with wx.ColourDialog(self._padre, datos) as dialogo:
            if dialogo.ShowModal() == wx.ID_OK:
                color = dialogo.GetColourData().GetColour()
                self._personalizado = color.GetAsString(wx.C2S_HTML_SYNTAX)
                self._refrescar_personalizado()
            else:
                self.establecer(self.valor() or "")

    def valor(self) -> str:
        """Color elegido en hexadecimal, o cadena vacía si no hay ninguno."""
        seleccion = self.control.GetStringSelection()
        if seleccion == colores.PERSONALIZADO:
            return self._personalizado
        directo = colores.valor_de(seleccion)
        return directo if directo else self._personalizado


class DialogoOpciones(wx.Dialog):
    """Preferencias de la aplicación.

    :param padre: Ventana principal.
    :param configuracion: Objeto de configuración que se va a modificar.
    :param sonidos: Gestor de sonidos, para poder probarlos y ajustar el volumen.
    """

    def __init__(self, padre: wx.Window, configuracion, sonidos) -> None:
        super().__init__(padre, title=_("Opciones"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.configuracion = configuracion
        self.sonidos = sonidos
        self.hay_que_reanalizar = False
        self._valores_previos = {
            clave: configuracion.obtener(clave) for clave in OPCIONES_QUE_REANALIZAN
        }

        contenedor = wx.BoxSizer(wx.VERTICAL)
        # El cuaderno de pestañas NO lleva nombre forzado: el lector de
        # pantalla anuncia el nombre de la pestaña seleccionada, y ponerle uno
        # propio lo sustituiría por él en todas las pestañas.
        self.cuaderno = wx.Notebook(self)
        self.cuaderno.AddPage(self._pagina_lectura(), _("Lectura"))
        self.cuaderno.AddPage(self._pagina_personalizacion(), _("Personalización"))
        self.cuaderno.AddPage(self._pagina_accesibilidad(), _("Accesibilidad"))
        self.cuaderno.AddPage(self._pagina_exportar(), _("Exportar"))
        self.cuaderno.AddPage(self._pagina_ocr(), _("Reconocimiento"))
        self.cuaderno.AddPage(self._pagina_daisy(), _("DAISY"))
        self.cuaderno.AddPage(self._pagina_ia(), _("Inteligencia artificial"))
        self.cuaderno.AddPage(self._pagina_ollama(), _("IA local"))
        self.cuaderno.AddPage(self._pagina_apariencia(), _("Apariencia"))
        self.cuaderno.AddPage(self._pagina_sonidos(), _("Sonidos"))
        self.cuaderno.AddPage(self._pagina_biblioteca(), _("Biblioteca y sincronización"))
        self.cuaderno.AddPage(self._pagina_globales(), _("Teclas globales"))
        if integracion.disponible():
            self.cuaderno.AddPage(self._pagina_integracion(),
                                  _("Integración con el sistema"))
        self.cuaderno.AddPage(self._pagina_avanzado(), _("Avanzado"))
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
        # Control+F1 sobre cualquier control explica para qué sirve: una línea
        # de etiqueta no da para decir qué consigue el ajuste ni qué conviene
        # poner, y quien no ve la pantalla no tiene el contexto de alrededor.
        ayuda_opcion.enganchar(self)
        self.cuaderno.SetFocus()

    # -- construcción de las páginas -----------------------------------------

    def _pagina_personalizacion(self) -> wx.Panel:
        """Cómo se reparte la ventana: pestañas, árbol de contenido y barra de estado.

        Todo lo de esta pestaña viene apagado o en lo más sencillo a propósito.
        Son ajustes que añaden **zonas** a la ventana, y una zona de más es una
        parada de más cada vez que se recorre con F6: útil para quien estudia o
        compara documentos, y un estorbo diario para quien lee una novela de un
        tirón.  Que cada cual encienda lo suyo.
        """
        panel = wx.ScrolledWindow(self.cuaderno, style=wx.VSCROLL)
        panel.SetScrollRate(0, 12)
        caja = wx.BoxSizer(wx.VERTICAL)

        # -- idioma -----------------------------------------------------------
        # Va lo primero de todo y no en «Avanzado», que es donde estaba: elegir
        # en qué idioma habla el programa es de lo primero que se busca, y es lo
        # que hace que el resto de las opciones se entienda.
        #
        # Los idiomas se detectan solos: los que haya en data/idiomas aparecen
        # aquí sin tocar nada.  Por eso no hay ninguna lista que mantener.
        caja.Add(wx.StaticText(panel, label=_("IDIOMA")), 0, wx.ALL, 6)
        self._idiomas = idioma.disponibles()
        self.idioma = fila_etiquetada(
            panel, caja, _("&Idioma de la interfaz:"),
            lambda p: wx.Choice(p, choices=[nombre for _clave, nombre
                                            in self._idiomas]),
            horizontal=True, proporcion=1)
        codigos = [clave for clave, _nombre in self._idiomas]
        actual_idioma = str(self.configuracion.obtener("idioma", "auto"))
        self.idioma.SetSelection(
            codigos.index(actual_idioma) if actual_idioma in codigos else 0)
        instalados = idioma.instalados()
        caja.Add(wx.StaticText(panel, label=(
            _("El cambio de idioma se aplica al reiniciar el programa.")
            + "\n"
            + (_("Traducciones encontradas: %s.") % ", ".join(
                idioma.nombre_de(c) for c in instalados) if instalados
               else _("No hay ninguna traducción instalada; se ve en español.")))
        ), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        # -- pestañas ---------------------------------------------------------
        caja.Add(wx.StaticText(panel, label=_("PESTAÑAS")), 0, wx.ALL, 6)
        self.usar_pestanas = wx.CheckBox(
            panel, label=_("Abrir cada documento en su propia &pestaña"))
        self.usar_pestanas.SetValue(bool(self.configuracion.obtener("usar_pestanas", False)))
        caja.Add(self.usar_pestanas, 0, wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_(
            "Con esto puedes tener varios documentos abiertos a la vez, cada uno con su\n"
            "posición de lectura, sus marcadores y su historial: al volver a una pestaña la\n"
            "encuentras justo como la dejaste. Es lo que hace falta para estudiar o para\n"
            "comparar dos textos.\n\n"
            "Se manejan como en un navegador: Control+N abre un documento en una pestaña\n"
            "nueva, Control+W cierra la actual, Control+Tabulador pasa a la siguiente y\n"
            "Control+F6 enseña la lista para saltar a cualquiera. Con F6 se va de una zona a\n"
            "otra de la ventana y con Mayús+F6 se vuelve."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        self.restaurar_documentos = wx.CheckBox(
            panel, label=_("Al abrir el programa, volver a abrir los &documentos que quedaron abiertos"))
        self.restaurar_documentos.SetValue(
            bool(self.configuracion.obtener("restaurar_documentos", False)))
        caja.Add(self.restaurar_documentos, 0, wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_(
            "Al cerrar se apunta qué documentos tenías abiertos y en cuál estabas, y al volver\n"
            "a abrir el programa se recuperan tal cual, cada uno por donde ibas. Se abren de\n"
            "uno en uno, así que con varios tarda un poco en estar todo.\n"
            "\n"
            "Si abres el programa haciendo doble clic en un libro, se abre ese y no se recupera\n"
            "nada: en ese momento querías ese libro. Los que ya no estén en su sitio se saltan\n"
            "sin decir nada."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        self._donde_abrir = (
            ("preguntar", _("Preguntarme cada vez")),
            ("nueva", _("Abrirlo siempre en una pestaña nueva")),
            ("actual", _("Abrirlo siempre en la pestaña de delante")),
        )
        self.pestanas_al_abrir = fila_etiquetada(
            panel, caja, _("Al abrir un &documento con otro ya abierto:"),
            lambda p: wx.Choice(p, choices=[rotulo for _clave, rotulo in self._donde_abrir]),
            horizontal=True)
        elegido = str(self.configuracion.obtener("pestanas_al_abrir", "preguntar"))
        claves = [clave for clave, _rotulo in self._donde_abrir]
        self.pestanas_al_abrir.SetSelection(claves.index(elegido) if elegido in claves else 0)

        # -- árbol de contenido ----------------------------------------------
        caja.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_("ÁRBOL DE CONTENIDO")), 0, wx.ALL, 6)
        self.mostrar_arbol = wx.CheckBox(
            panel, label=_("Enseñar el ár&bol de contenido a la izquierda del texto"))
        self.mostrar_arbol.SetValue(bool(self.configuracion.obtener("mostrar_arbol", False)))
        caja.Add(self.mostrar_arbol, 0, wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_(
            "Deja siempre a la vista el índice del documento y sus elementos —encabezados,\n"
            "enlaces, imágenes, tablas, listas...— en un árbol que se pliega y se despliega,\n"
            "que es lo mismo que enseña F7 pero sin tener que abrir y cerrar un diálogo cada\n"
            "vez. Se va a él con F6 y al llegar ya está colocado por donde vas leyendo; con\n"
            "Intro se salta a lo que elijas. También se enciende y se apaga con Control+Alt+B."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        # -- pantalla de bienvenida -------------------------------------------
        caja.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_("PANTALLA DE BIENVENIDA")), 0, wx.ALL, 6)
        self.mostrar_bienvenida = wx.CheckBox(
            panel, label=_("Enseñar el resumen de &teclas mientras no hay ningún "
                           "documento abierto"))
        self.mostrar_bienvenida.SetValue(
            bool(self.configuracion.obtener("mostrar_bienvenida", True)))
        caja.Add(self.mostrar_bienvenida, 0, wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_(
            "Mientras no hay libro abierto, el cuadro de lectura enseña un resumen de todo lo\n"
            "que se puede hacer y con qué tecla. Es lo que hace falta el primer día; cuando ya\n"
            "te las sabes, es una pantalla por la que pasar cada vez que arrancas.\n"
            "\n"
            "Desmarcándolo quedan dos líneas: el nombre del programa y cómo abrir un\n"
            "documento. El resumen entero sigue estando en Mayús+F1, con todas las teclas y su\n"
            "descripción."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        # -- barra de estado --------------------------------------------------
        caja.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_("BARRA DE ESTADO")), 0, wx.ALL, 6)
        self.barra_recuentos = wx.CheckBox(
            panel, label=_("Enseñar cuántas palabras y cuántas pá&ginas tiene el documento"))
        self.barra_recuentos.SetValue(bool(self.configuracion.obtener("barra_recuentos", True)))
        caja.Add(self.barra_recuentos, 0, wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_(
            "La barra de estado dice siempre por qué línea vas, por qué porcentaje del\n"
            "documento y en qué página. Con esto marcado añade el tamaño total: las palabras\n"
            "que tiene y sus páginas, y con varias pestañas abiertas, en cuál estás. El\n"
            "informe completo, con las estadísticas de lectura, sigue en Control+D."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        panel.SetSizer(caja)
        return panel

    def _pagina_lectura(self) -> wx.Panel:
        """Cómo se lee y cómo se convierte el documento."""
        panel = wx.Panel(self.cuaderno)
        caja = wx.BoxSizer(wx.VERTICAL)
        self.tablas = wx.CheckBox(
            panel, label=_("Mostrar las &tablas completas dentro del texto "
                         "(requiere volver a abrir el libro)"))
        self.ajuste = wx.CheckBox(
            panel, label=_("&Ajustar las líneas al ancho de la ventana "
                         "(si se desactiva, cada línea es un párrafo completo)"))

        # El ancho del renglón va **debajo** del ajuste de línea y solo aparece
        # cuando este está activado: sin ajuste no hay renglones que estrechar,
        # así que el ancho no significaría nada y estorbaría al recorrer la
        # pestaña con el tabulador.  Se mete en su propio panel para poder
        # esconderlo entero —etiqueta, control y explicación— de una vez.
        self.panel_ancho = wx.Panel(panel)
        caja_ancho = wx.BoxSizer(wx.VERTICAL)
        self.ancho_linea = fila_etiquetada(
            self.panel_ancho, caja_ancho,
            _("A&ncho máximo del renglón, en caracteres (0 = todo el ancho):"),
            lambda p: wx.SpinCtrl(p, min=0, max=250, initial=int(
                self.configuracion.obtener("ancho_maximo_linea", 0) or 0)),
            horizontal=True)
        caja_ancho.Add(wx.StaticText(self.panel_ancho, label=_(
            "Un renglón muy largo es incómodo de seguir: al llegar al final hay que volver\n"
            "al principio del siguiente, y cuanto más largo sea más fácil es perderse por el\n"
            "camino. En papel casi nunca se pasa de setenta caracteres por línea; en una\n"
            "ventana maximizada salen fácilmente el doble. Con esto se estrecha la columna\n"
            "de texto dejando márgenes a los lados.\n"
            "\n"
            "No cambia el texto ni una sola posición: los marcadores, las notas y por dónde\n"
            "ibas siguen donde estaban."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        self.panel_ancho.SetSizer(caja_ancho)

        self.renglon_frase = wx.CheckBox(
            panel, label=_("Empezar cada &frase en un renglón nuevo "
                           "(para la lectura continua del lector de pantalla)"))
        self.circular = wx.CheckBox(
            panel, label=_("Al llegar al final, &continuar la navegación desde el principio"))
        self.recordar = wx.CheckBox(panel, label=_("&Recordar la posición de lectura de cada documento"))
        self.formato = wx.CheckBox(
            panel, label=_("Mostrar la &negrita y la cursiva del libro "
                         "(hace más lento el desplazamiento)"))
        # El extractor de artículo sí va aquí: cambia el texto del documento
        # que se abre, que es de lo que trata esta pestaña.  Lo que cambia el
        # archivo **que sale** —el braille contraído, la revisión del EPUB— está
        # en «Exportar».
        self.solo_articulo = wx.CheckBox(
            panel, label=_("En las páginas web guardadas, quedarse solo con el "
                           "&artículo (requiere volver a abrir la página)"))
        self.solo_articulo.SetValue(bool(self.configuracion.obtener("solo_articulo", True)))
        caja.Add(self.solo_articulo, 0, wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_(
            "Quita los menús, el aviso de galletas, la columna de «lo más leído» y el pie\n"
            "con cincuenta enlaces. Si el recorte no se puede decidir con seguridad, la\n"
            "página se lee entera, así que no hay nada que perder."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        self.marcar_notas = wx.CheckBox(
            panel, label=_("Decir «&nota» en las llamadas de nota "
                         "(requiere volver a abrir el libro)"))
        self.marcar_notas.SetValue(
            bool(self.configuracion.obtener("marcar_llamadas_de_nota", False)))

        self.tablas.SetValue(bool(self.configuracion.obtener("tablas_en_linea")))
        self.ajuste.SetValue(bool(self.configuracion.obtener("ajuste_de_linea")))
        self.circular.SetValue(bool(self.configuracion.obtener("navegacion_circular")))
        self.recordar.SetValue(bool(self.configuracion.obtener("recordar_posicion")))
        self.formato.SetValue(bool(self.configuracion.obtener("mostrar_formato")))
        self.renglon_frase.SetValue(bool(self.configuracion.obtener("renglon_por_frase", False)))

        for casilla in (self.tablas, self.ajuste, self.renglon_frase, self.circular,
                        self.recordar, self.formato,
                        self.marcar_notas):
            caja.Add(casilla, 0, wx.ALL, 6)
            if casilla is self.ajuste:
                caja.Add(self.panel_ancho, 0, wx.EXPAND | wx.LEFT, 18)
            if casilla is self.renglon_frase:
                caja.Add(wx.StaticText(panel, label=_(
                    "La lectura continua del lector de pantalla (NVDA+A) va diciendo el texto\n"
                    "renglón a renglón y deja el cursor al principio del que está sonando. Con cada\n"
                    "párrafo en una sola línea, eso significa que al parar la lectura el cursor\n"
                    "aparece al principio del párrafo entero: se han oído veinte líneas y hay que\n"
                    "volver a bajar por ellas para seguir a mano. Con esto marcado el renglón es la\n"
                    "frase, y el cursor se queda en la frase que estaba sonando.\n"
                    "\n"
                    "No cambia el texto ni una sola posición: lo único que pasa es que el espacio\n"
                    "que separa dos frases se enseña como un salto de línea. Los marcadores, las\n"
                    "notas, los resaltados y por dónde ibas siguen exactamente donde estaban, y lo\n"
                    "que se copia sale con sus espacios."
                )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        self.ajuste.Bind(wx.EVT_CHECKBOX, self._al_cambiar_ajuste_de_linea)
        self._al_cambiar_ajuste_de_linea(None)

        caja.Add(wx.StaticText(panel, label=_(
            "En un libro anotado, la llamada de una nota es un número suelto —«[12]»— y leído\n"
            "en voz alta suena igual que cualquier otro número del texto, que en una edición\n"
            "clásica es justo el de la cita. Con la casilla de arriba se dice «nota 12».\n"
            "\n"
            "Es lo único que se oye en la lectura continua del lector de pantalla: los sonidos\n"
            "del programa acompañan al cursor, y en la lectura continua el cursor no se mueve.\n"
            "A cambio alarga el texto, así que viene apagado."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        caja.Add(wx.StaticText(panel, label=_(
            "Los PDF escaneados y los libros DAISY grabados tienen sus propias pestañas,\n"
            "«Reconocimiento» y «DAISY»."
        )), 0, wx.ALL, 6)
        panel.SetSizer(caja)
        return panel

    def _al_cambiar_ajuste_de_linea(self, evento) -> None:
        """Enseña u oculta el ancho del renglón según el ajuste de línea.

        Sin ajuste de línea cada párrafo es una sola línea que se desplaza a lo
        ancho, así que un ancho máximo no partiría nada.  Se oculta en vez de
        desactivarse porque un control apagado sigue estando en el recorrido del
        tabulador y hay que pasar por él para nada.

        El valor **no se toca** al ocultarlo: quien apaga el ajuste, lo vuelve a
        encender y encuentra el ancho que tenía puesto, en vez de tener que
        acordarse de volver a escribirlo.
        """
        activo = self.ajuste.GetValue()
        if self.panel_ancho.IsShown() != activo:
            self.panel_ancho.Show(activo)
            self.panel_ancho.GetParent().Layout()

    def _pagina_exportar(self) -> wx.Panel:
        """Lo que cambia el archivo que sale, no el que se lee.

        Son dos ajustes y tienen pestaña propia por dónde se buscan: quien va a
        imprimir en braille entra aquí, no en «Lectura». Y es donde irá lo que
        se añada de exportación, que hoy son seis formatos.
        """
        panel = wx.Panel(self.cuaderno)
        caja = wx.BoxSizer(wx.VERTICAL)

        self.braille_contraido = wx.CheckBox(
            panel, label=_("Escribir el braille en &contraído (grado 2)"))
        self.braille_contraido.SetValue(
            bool(self.configuracion.obtener("braille_contraido", False)))
        caja.Add(self.braille_contraido, 0, wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_(
            "Usa las abreviaturas del braille contraído español y ocupa alrededor de un\n"
            "tercio menos. Solo afecta al BRF y al PEF. Viene apagado: quien no haya\n"
            "estudiado el contraído no lo entiende."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        self.revisar_epub = wx.CheckBox(
            panel, label=_("Comprobar la accesibilidad del libro &EPUB al exportarlo"))
        self.revisar_epub.SetValue(bool(self.configuracion.obtener("revisar_epub", True)))
        caja.Add(self.revisar_epub, 0, wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_(
            "Pasa el EPUB recién escrito por las mismas comprobaciones que se le hacen a\n"
            "cualquier otro libro: el envoltorio, los metadatos de accesibilidad, el índice\n"
            "y las imágenes sin describir. Tarda una décima."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        panel.SetSizer(caja)
        return panel

    def _pagina_ocr(self) -> wx.Panel:
        """Todo lo que decide cómo se lee un PDF escaneado.

        Tiene bastantes ajustes y por eso está en su propia pestaña, con la
        barra de desplazamiento: son los que deciden si un documento difícil
        sale legible o sale inservible, y merecen sitio para explicarse.
        """
        panel = wx.ScrolledWindow(self.cuaderno, style=wx.VSCROLL)
        panel.SetScrollRate(0, 12)
        caja = wx.BoxSizer(wx.VERTICAL)

        # -- estructura de los PDF etiquetados -------------------------------
        caja.Add(wx.StaticText(panel, label=_("ESTRUCTURA")), 0, wx.ALL, 6)
        self.pdf_estructura = wx.CheckBox(
            panel, label=_("&Aprovechar la estructura de los PDF accesibles"))
        self.pdf_estructura.SetValue(bool(self.configuracion.obtener("pdf_estructura", True)))
        caja.Add(self.pdf_estructura, 0, wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_(
            "Un PDF accesible (etiquetado, según la norma PDF/UA) lleva dentro la misma\n"
            "información que una página web: qué es un encabezado, qué una lista, qué una\n"
            "tabla con sus encabezados de columna, qué describe cada imagen y en qué idioma\n"
            "está cada trozo. Con esto activado el documento se recorre igual que un EPUB,\n"
            "con H, T, L, Q, I, con F7 y con Ctrl+H, y desaparecen los encabezados y pies\n"
            "que se repiten en cada página. Desactívalo solo si un PDF concreto sale peor\n"
            "así que como texto corrido."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        self.pdf_geometria = wx.CheckBox(
            panel, label=_("&Deducir la estructura de los PDF que no la traen"))
        self.pdf_geometria.SetValue(bool(self.configuracion.obtener("pdf_geometria", True)))
        caja.Add(self.pdf_geometria, 0, wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_(
            "La mayoría de los PDF no están etiquetados: dentro solo dicen dónde pintar\n"
            "cada letra. Con esto activado el programa mide cómo está escrita cada página\n"
            "y deduce lo que el archivo no dice: los títulos por su tamaño de letra y su\n"
            "numeración, las listas por sus viñetas, las tablas por cómo se alinean sus\n"
            "columnas, los enlaces por dónde están dibujados, y las columnas de un texto\n"
            "a dos columnas para leerlas enteras una detrás de otra en vez de saltando de\n"
            "una a otra en cada renglón. Un documento así se recorre con H y con T como si\n"
            "estuviera etiquetado. Cuesta alrededor de medio segundo cada diez páginas y\n"
            "no se aplica a los PDF que sí traen estructura, que no lo necesitan."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        caja.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.ALL, 6)

        caja.Add(wx.StaticText(panel, label=_("RECONOCIMIENTO DE LAS PÁGINAS ESCANEADAS")),
                 0, wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_(
            "Un PDF o un DjVu escaneados son fotografías de las páginas: sin reconocerlos\n"
            "se abren vacíos. Hay tres motores y ninguno sobra, porque fallan en sitios\n"
            "distintos. Estos ajustes valen para los dos formatos."
        )), 0, wx.ALL, 6)

        # -- motor -----------------------------------------------------------
        caja.Add(wx.StaticText(panel, label=_("MOTOR")), 0, wx.ALL, 6)
        self._modos_ocr = ocr.nombres_de_modo()
        self.pdf_modo = fila_etiquetada(
            panel, caja, _("&Cómo se reconocen las páginas escaneadas:"),
            lambda p: wx.Choice(p, choices=[rotulo for _clave, rotulo in self._modos_ocr]),
            horizontal=True)
        elegido = str(self.configuracion.obtener("pdf_ocr_modo", "auto"))
        claves = [clave for clave, _rotulo in self._modos_ocr]
        self.pdf_modo.SetSelection(claves.index(elegido) if elegido in claves else 0)
        caja.Add(wx.StaticText(panel, label=_(
            "• Tesseract viene incluido, va sin conexión, no gasta cuota y es el que mejor\n"
            "  conserva las columnas y las tablas.\n"
            "• La inteligencia artificial lee mejor la letra difícil, pero necesita conexión,\n"
            "  gasta cuota y manda la página a un servidor.\n"
            "• El de Windows ya está en el sistema y es el más rápido."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        fila_idiomas = wx.BoxSizer(wx.HORIZONTAL)
        self.etiqueta_tesseract = wx.StaticText(panel, label=self._estado_de_tesseract())
        fila_idiomas.Add(self.etiqueta_tesseract, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        boton_idiomas = wx.Button(panel, label=_("&Idiomas del reconocimiento..."))
        boton_idiomas.Bind(wx.EVT_BUTTON, self._al_idiomas_tesseract)
        fila_idiomas.Add(boton_idiomas, 0)
        caja.Add(fila_idiomas, 0, wx.EXPAND | wx.ALL, 6)

        self.pdf_maximo = fila_etiquetada(
            panel, caja, _("&Páginas que se reconocen como mucho (0 = sin tope):"),
            lambda p: wx.SpinCtrl(p, min=0, max=5000,
                                  initial=int(self.configuracion.obtener("pdf_ocr_maximo", 100))),
            horizontal=True)
        caja.Add(wx.StaticText(panel, label=_(
            "Reconocer es lento. El tope evita que un libro escaneado de quinientas páginas\n"
            "deje el programa abriendo durante horas."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        # -- preparación de la imagen ----------------------------------------
        caja.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_("PREPARAR LA IMAGEN")), 0, wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_(
            "Un OCR no lee la página que se ve: lee la que se le da. Medido sobre un folleto\n"
            "en color, pasarla a gris y subirle el contraste llevó los productos leídos con su\n"
            "precio de 7 a 10 sobre 14, y la basura de 31 líneas a 7. Es lo que más ayuda."
        )), 0, wx.LEFT | wx.RIGHT, 6)

        self.ocr_gris = wx.CheckBox(panel, label=_("Pasar la página a escala de &grises"))
        self.ocr_gris.SetValue(bool(self.configuracion.obtener("pdf_ocr_gris", True)))
        caja.Add(self.ocr_gris, 0, wx.ALL, 6)

        self.ocr_contraste = fila_etiquetada(
            panel, caja, _("Con&traste, de 10 a 60 (10 es el normal, 30 el recomendado):"),
            lambda p: wx.SpinCtrl(
                p, min=10, max=60,
                initial=int(float(self.configuracion.obtener("pdf_ocr_contraste", 3.0)) * 10)),
            horizontal=True)
        self.ocr_contraste.SetIncrement(5)

        self.ocr_binarizar = wx.CheckBox(
            panel, label=_("Dejar la página en &blanco y negro puro"))
        self.ocr_binarizar.SetValue(bool(self.configuracion.obtener("pdf_ocr_binarizar", False)))
        caja.Add(self.ocr_binarizar, 0, wx.ALL, 6)
        self.ocr_umbral = fila_etiquetada(
            panel, caja, _("&Umbral del blanco y negro (0 a 255):"),
            lambda p: wx.SpinCtrl(p, min=1, max=254,
                                  initial=int(self.configuracion.obtener("pdf_ocr_umbral", 160))),
            horizontal=True)
        caja.Add(wx.StaticText(panel, label=_(
            "El blanco y negro puro viene apagado a propósito: rompe la letra fina y en las\n"
            "pruebas salió peor que el gris con contraste. Puede ayudar en un escaneado muy\n"
            "sucio o con manchas."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        # -- afinado ---------------------------------------------------------
        caja.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_("AFINAR EL RECONOCIMIENTO")), 0, wx.ALL, 6)

        self._psm = ocr.modos_de_segmentacion()
        self.ocr_psm = fila_etiquetada(
            panel, caja, _("Cómo se &segmenta la página:"),
            lambda p: wx.Choice(p, choices=[rotulo for _valor, rotulo in self._psm]),
            horizontal=True, proporcion=1)
        valores_psm = [valor for valor, _rotulo in self._psm]
        actual = int(self.configuracion.obtener("pdf_ocr_psm", 1))
        self.ocr_psm.SetSelection(valores_psm.index(actual) if actual in valores_psm else 0)

        self._oem = ocr.motores_de_tesseract()
        self.ocr_oem = fila_etiquetada(
            panel, caja, _("&Motor interno de Tesseract:"),
            lambda p: wx.Choice(p, choices=[rotulo for _valor, rotulo in self._oem]),
            horizontal=True, proporcion=1)
        valores_oem = [valor for valor, _rotulo in self._oem]
        actual = int(self.configuracion.obtener("pdf_ocr_oem", 3))
        self.ocr_oem.SetSelection(valores_oem.index(actual) if actual in valores_oem else 0)

        # Una lista y no un control de decimales: «wx.SpinCtrlDouble» es un
        # control compuesto —por dentro son un cuadro de texto y unas flechas—
        # y el foco cae en el cuadro interno, que el lector de pantalla anuncia
        # como «text».  No hay forma de arreglarlo desde fuera, y además elegir
        # entre cinco aumentos es más cómodo que teclear un número con coma.
        self._escalas = [
            (0.0, _("El que convenga a cada motor (recomendado)")),
            (2.0, _("2 aumentos: rápido, vale para un escaneado limpio")),
            (2.5, _("2,5 aumentos")),
            (3.0, _("3 aumentos: lo que mejor resultado dio en las pruebas")),
            (3.5, _("3,5 aumentos")),
            (4.0, _("4 aumentos: lento, y de aquí en adelante no mejora")),
        ]
        self.ocr_escala = fila_etiquetada(
            panel, caja, _("Au&mento de la página:"),
            lambda p: wx.Choice(p, choices=[rotulo for _valor, rotulo in self._escalas]),
            horizontal=True, proporcion=1)
        valores = [valor for valor, _rotulo in self._escalas]
        actual = float(self.configuracion.obtener("pdf_ocr_escala", 0) or 0)
        self.ocr_escala.SetSelection(valores.index(actual) if actual in valores else 0)
        caja.Add(wx.StaticText(panel, label=_(
            "De fábrica se rasteriza a 3 aumentos para Tesseract y a 2 para los demás. Subirlo\n"
            "más no mejora: el desenfoque pesa más que el detalle que aporta."
        )), 0, wx.LEFT | wx.RIGHT, 6)

        self.ocr_dpi = fila_etiquetada(
            panel, caja, _("&Resolución que se le declara a Tesseract (0 = que la deduzca):"),
            lambda p: wx.SpinCtrl(p, min=0, max=1200,
                                  initial=int(self.configuracion.obtener("pdf_ocr_dpi", 0))),
            horizontal=True)

        self.ocr_confianza = fila_etiquetada(
            panel, caja, _("Con&fianza mínima para quedarse con una palabra, de 0 a 90:"),
            lambda p: wx.SpinCtrl(
                p, min=0, max=90,
                initial=int(float(self.configuracion.obtener("pdf_ocr_confianza", 30)))),
            horizontal=True)
        self.ocr_confianza.SetIncrement(5)
        caja.Add(wx.StaticText(panel, label=_(
            "Subirla limpia el ruido, pero con cuidado: en un folleto los precios sobre fondo\n"
            "de color se reconocen con poca confianza y se perderían."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        # -- qué se hace con lo leído ----------------------------------------
        caja.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_("QUÉ SE HACE CON LO LEÍDO")), 0, wx.ALL, 6)

        self.ocr_esmerado = wx.CheckBox(panel, label=_(
            "Leer cada página &dos veces y juntar lo leído (tarda el doble)"))
        self.ocr_esmerado.SetValue(bool(self.configuracion.obtener("pdf_ocr_esmerado", True)))
        caja.Add(self.ocr_esmerado, 0, wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_(
            "Es lo que más mejora el resultado en documentos difíciles. Las dos lecturas se\n"
            "hacen con la página preparada de forma distinta, así que no fallan en los mismos\n"
            "sitios: medido sobre un folleto en color, pasó de 15 a 19 productos leídos con su\n"
            "precio de 23."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        self.ocr_simbolos = wx.CheckBox(panel, label=_(
            "Descartar los &adornos y símbolos sueltos (flechas, marcos, iconos)"))
        self.ocr_simbolos.SetValue(
            bool(self.configuracion.obtener("pdf_ocr_quitar_simbolos", True)))
        caja.Add(self.ocr_simbolos, 0, wx.ALL, 6)

        self.ocr_tablas = wx.CheckBox(panel, label=_(
            "Reconstruir las ta&blas como tablas de verdad"))
        self.ocr_tablas.SetValue(bool(self.configuracion.obtener("pdf_ocr_tablas", True)))
        caja.Add(self.ocr_tablas, 0, wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_(
            "El orden de lectura se reconstruye siempre: sin él, un documento a varias\n"
            "columnas se lee cruzando de una a otra y no hay manera de entenderlo."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        # El tope solo significa algo si se reconoce: con «No reconocer» se
        # apaga, para que no parezca que hace algo cuando no hace nada.
        self.pdf_modo.Bind(wx.EVT_CHOICE, lambda evento: self._refrescar_tope_ocr())
        self.ocr_binarizar.Bind(wx.EVT_CHECKBOX, lambda evento: self._refrescar_tope_ocr())
        self._refrescar_tope_ocr()

        panel.SetSizer(caja)
        panel.SetVirtualSize(caja.GetMinSize())
        return panel

    def _pagina_daisy(self) -> wx.Panel:
        """Cómo suenan los libros DAISY grabados."""
        panel = wx.Panel(self.cuaderno)
        caja = wx.BoxSizer(wx.VERTICAL)

        caja.Add(wx.StaticText(panel, label=_(
            "Casi todo lo que prestan las bibliotecas para personas ciegas viene en DAISY, y\n"
            "la mayoría son grabaciones con voz humana en vez de texto. Aquí se ajusta cómo\n"
            "suenan y cómo se navegan."
        )), 0, wx.ALL, 6)

        caja.Add(wx.StaticText(panel, label=_("LA VOZ DEL NARRADOR")), 0, wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_(
            "Esto ajusta la GRABACIÓN: la voz humana que viene dentro del libro DAISY.\n"
            "No tiene nada que ver con la voz sintética que lee los demás documentos, que\n"
            "se ajusta en el menú «Voz», en «Voz y velocidad de la voz sintética»\n"
            "(Control+Alt+V)."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        # Controles de número y no deslizadores: un deslizador de 50 a 300 lo
        # anuncia el lector de pantalla como el porcentaje de su recorrido, de
        # modo que con la velocidad en 100 decía «20».
        self.daisy_velocidad = fila_etiquetada(
            panel, caja, _("&Velocidad de la grabación, en por ciento (100 es la "
                           "del narrador):"),
            lambda p: wx.SpinCtrl(p, min=50, max=300,
                                  initial=int(self.configuracion.obtener("daisy_velocidad", 100))),
            horizontal=True)
        self.daisy_velocidad.SetIncrement(5)
        self.daisy_volumen = fila_etiquetada(
            panel, caja, _("Vo&lumen de la grabación, de 0 a 100:"),
            lambda p: wx.SpinCtrl(p, min=0, max=100,
                                  initial=int(self.configuracion.obtener("daisy_volumen", 100))),
            horizontal=True)
        self.daisy_volumen.SetIncrement(5)
        caja.Add(wx.StaticText(panel, label=_(
            "La velocidad se cambia sin alterar el tono de la voz, así que subirla no\n"
            "convierte al narrador en un pato. También se cambia mientras suena, con\n"
            "Control+Alt+Arriba y Control+Alt+Abajo: con un libro DAISY grabado abierto,\n"
            "esas teclas mandan sobre la grabación y no sobre la voz sintética."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        caja.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.ALL, 6)
        self.daisy_cursor = wx.CheckBox(
            panel, label=_("Mover el &cursor siguiendo a la grabación"))
        self.daisy_cursor.SetValue(bool(self.configuracion.obtener("daisy_mover_cursor", True)))
        caja.Add(self.daisy_cursor, 0, wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_(
            "Con esto, en cualquier momento puedes consultar con el lector de pantalla lo\n"
            "que se está oyendo. En un libro de solo audio es además la única forma de\n"
            "saber por dónde va."
        )), 0, wx.LEFT | wx.RIGHT, 6)

        self.daisy_al_abrir = wx.CheckBox(
            panel, label=_("&Empezar a reproducir en cuanto se abre un libro DAISY grabado"))
        self.daisy_al_abrir.SetValue(
            bool(self.configuracion.obtener("daisy_reproducir_al_abrir", False)))
        caja.Add(self.daisy_al_abrir, 0, wx.ALL, 6)

        caja.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_(
            "Los mandos completos están en el menú «Reproductor» (Control+Alt+R), con la\n"
            "lista de capítulos y páginas y el nivel de navegación. Las teclas globales\n"
            "manejan la grabación desde cualquier programa."
        )), 0, wx.ALL, 6)

        caja.Add(wx.StaticText(panel, label=self._estado_del_sonido()), 0, wx.ALL, 6)
        panel.SetSizer(caja)
        return panel

    def _estado_del_sonido(self) -> str:
        """Dice si se puede reproducir audio y con qué."""
        from nucleo import audio

        motivo = audio.motivo_no_disponible()
        if motivo:
            return motivo.split("\n")[0]
        return _("El sonido está listo.")

    def _refrescar_tope_ocr(self) -> None:
        """Apaga lo que no tiene sentido según lo que esté elegido."""
        clave = self._modos_ocr[max(0, self.pdf_modo.GetSelection())][0]
        activo = clave != "ninguno"
        self.pdf_maximo.Enable(activo)
        # El umbral solo significa algo si se va a binarizar.
        self.ocr_umbral.Enable(activo and self.ocr_binarizar.GetValue())

    def _estado_de_tesseract(self) -> str:
        """Resume en una línea qué Tesseract hay y con qué idiomas."""
        from nucleo import tesseract

        if not tesseract.disponible():
            return _("Tesseract: no disponible.")
        puestos = tesseract.instalados()
        donde = _("incluido con el programa") if tesseract.es_portable() else _("del sistema")
        if not puestos:
            return _("Tesseract %s, sin ningún idioma.") % donde
        nombres = ", ".join(tesseract.nombre_de(codigo) for codigo in puestos[:5])
        if len(puestos) > 5:
            nombres += _(" y %d más") % (len(puestos) - 5)
        return _("Tesseract %s, con %d idiomas: %s") % (donde, len(puestos), nombres)

    def _al_idiomas_tesseract(self, evento) -> None:
        """Abre el gestor de idiomas del reconocimiento."""
        from interfaz.dialogos.idiomas_ocr import DialogoIdiomasOCR

        with DialogoIdiomasOCR(self, self.configuracion) as dialogo:
            dialogo.ShowModal()
        self.etiqueta_tesseract.SetLabel(self._estado_de_tesseract())
        self.Layout()

    def _al_elegir_tecla_lista(self, elegida: wx.Choice, otra: wx.Choice) -> None:
        """Una tecla no puede servir para las dos órdenes de las listas.

        Si se elige para una la que ya tenía la otra, la otra se queda sin
        tecla y se dice en el momento, no al guardar.
        """
        indice = elegida.GetSelection()
        if indice < 0 or not self._teclas_lista[indice][0]:
            return
        if otra.GetSelection() == indice:
            otra.SetSelection(len(self._teclas_lista) - 1)
            from interfaz.anuncios import Voz

            Voz(self).decir(_("%s ya era la tecla de la otra orden, que se queda sin "
                              "tecla.") % self._teclas_lista[indice][1])

    def _pagina_accesibilidad(self) -> wx.Panel:
        """Todo lo que decide qué se le dice al lector de pantalla.

        Reúne en un solo sitio los ajustes que solo tienen sentido cuando se
        lee de oído: qué se anuncia al recorrer las columnas de una lista y si
        se señalan las imágenes que el libro no describe.
        """
        panel = wx.Panel(self.cuaderno)
        caja = wx.BoxSizer(wx.VERTICAL)

        caja.Add(wx.StaticText(panel, label=(
            _("LECTURA DE LAS LISTAS POR COLUMNAS\n\n"
            "En las listas de varias columnas (los marcadores y notas, o la ventana de\n"
            "una tabla) las flechas izquierda y derecha recorren las columnas de la fila\n"
            "en la que estés, y Control+1 a Control+9 van directamente a una de ellas.\n"
            "Elige aquí qué quieres oír de cada celda:")
        )), 0, wx.ALL, 6)

        self.decir_fila = wx.CheckBox(
            panel, label=_("Decir el &número de fila («Fila 3 de 20»)"))
        self.decir_encabezado = wx.CheckBox(
            panel, label=_("Decir el nombre de la &columna («Tipo», «Contenido»...)"))
        self.decir_contenido = wx.CheckBox(
            panel, label=_("Decir el conteni&do de la celda"))
        self.decir_fila.SetValue(bool(self.configuracion.obtener("columnas_decir_fila", True)))
        self.decir_encabezado.SetValue(
            bool(self.configuracion.obtener("columnas_decir_encabezado", True)))
        self.decir_contenido.SetValue(
            bool(self.configuracion.obtener("columnas_decir_contenido", True)))
        for casilla in (self.decir_fila, self.decir_encabezado, self.decir_contenido):
            caja.Add(casilla, 0, wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=(
            _("Si las desactivas las tres se dirá de todos modos el contenido de la celda:\n"
            "una lista que no dice nada al recorrerla no serviría de nada.")
        )), 0, wx.ALL, 6)

        from interfaz.listas import TECLAS_DE_LISTA

        self._teclas_lista = list(TECLAS_DE_LISTA)
        claves_teclas = [c for c, _n in self._teclas_lista]
        self.lista_tecla_posicion = fila_etiquetada(
            panel, caja, _("Tecla para decir en qué &elemento estás y de cuántos:"),
            lambda p: wx.Choice(p, choices=[n for _c, n in self._teclas_lista]),
            horizontal=True)
        self.lista_tecla_ir_a = fila_etiquetada(
            panel, caja, _("&Tecla para ir a un elemento por su número:"),
            lambda p: wx.Choice(p, choices=[n for _c, n in self._teclas_lista]),
            horizontal=True)
        guardadas = (
            (self.lista_tecla_posicion,
             str(self.configuracion.obtener("lista_tecla_posicion", "") or "")),
            (self.lista_tecla_ir_a,
             str(self.configuracion.obtener("lista_tecla_ir_a", "") or "")))
        for control, valor in guardadas:
            control.SetSelection(claves_teclas.index(valor) if valor in claves_teclas
                                 else len(claves_teclas) - 1)
        self.lista_tecla_posicion.Bind(
            wx.EVT_CHOICE, lambda e: self._al_elegir_tecla_lista(self.lista_tecla_posicion,
                                                                 self.lista_tecla_ir_a))
        self.lista_tecla_ir_a.Bind(
            wx.EVT_CHOICE, lambda e: self._al_elegir_tecla_lista(self.lista_tecla_ir_a,
                                                                 self.lista_tecla_posicion))

        caja.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_("LECTURA DEL LIBRO")), 0, wx.ALL, 6)
        self.imagenes = wx.CheckBox(
            panel, label=_("Señalar también las &imágenes que no tienen descripción "
                         "(requiere volver a abrir el libro)"))
        self.imagenes.SetValue(bool(self.configuracion.obtener("anunciar_imagenes_sin_texto")))
        caja.Add(self.imagenes, 0, wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=(
            _("Si lo desactivas, las imágenes decorativas dejan de estorbar la lectura,\n"
            "pero tampoco podrás saltar a ellas con la tecla G.")
        )), 0, wx.ALL, 6)

        panel.SetSizer(caja)
        return panel

    def _pagina_ia(self) -> wx.Panel:
        """Proveedor de IA, claves, modelo y prompts para describir imágenes.

        Los modelos que devuelve el proveedor **se guardan**: pedirlos es una
        consulta por internet, y no tiene sentido repetirla cada vez que se
        abren las opciones.  El botón vuelve a pedirlos cuando el usuario
        quiera refrescarlos.
        """
        panel = wx.ScrolledWindow(self.cuaderno)
        panel.SetScrollRate(0, 12)
        caja = wx.BoxSizer(wx.VERTICAL)

        caja.Add(wx.StaticText(panel, label=(
            _("La inteligencia artificial se usa aquí para una sola cosa: describir las imágenes\n"
            "del libro. Con Gemini la imagen se envía a los servidores de Google; con un modelo\n"
            "local no sale nada del equipo, pero hay que tener el servidor en marcha.")
        )), 0, wx.ALL, 6)

        self.ia_proveedor = fila_etiquetada(
            panel, caja, "&Proveedor:",
            lambda p: wx.Choice(p, choices=[nombre for _clave, nombre in ia_servicio.PROVEEDORES]),
            horizontal=True, proporcion=1)
        actual = str(self.configuracion.obtener("ia_proveedor", "off"))
        claves = [clave for clave, _nombre in ia_servicio.PROVEEDORES]
        self.ia_proveedor.SetSelection(claves.index(actual) if actual in claves else 0)
        self.ia_proveedor.Bind(wx.EVT_CHOICE, lambda evento: self._al_cambiar_proveedor())

        # --- Gemini ---------------------------------------------------------
        self.caja_gemini = wx.StaticBoxSizer(wx.VERTICAL, panel, _("Google Gemini"))
        marco_gemini = self.caja_gemini.GetStaticBox()
        self.caja_gemini.Add(wx.StaticText(marco_gemini, label=(
            _("Claves &API, una por línea. Si pones varias y una agota su cuota,\n"
            "se pasa sola a la siguiente:"))), 0, wx.ALL, 6)
        self.ia_claves = etiquetar(wx.TextCtrl(
            marco_gemini, style=wx.TE_MULTILINE, size=(520, 70)), _("Claves API de Gemini"))
        guardadas = self.configuracion.obtener("ia_gemini_claves", []) or []
        if isinstance(guardadas, str):
            guardadas = guardadas.splitlines()
        self.ia_claves.SetValue("\n".join(str(clave).strip() for clave in guardadas))
        self.caja_gemini.Add(self.ia_claves, 0, wx.EXPAND | wx.ALL, 6)
        self.ia_modelo_gemini = self._fila_modelo(
            marco_gemini, self.caja_gemini, _("Mo&delo de Gemini:"),
            self.configuracion.obtener("ia_gemini_modelos", []),
            str(self.configuracion.obtener("ia_gemini_modelo",
                                           ia_servicio.MODELO_GEMINI) or ""))
        caja.Add(self.caja_gemini, 0, wx.EXPAND | wx.ALL, 6)

        # --- Anthropic --------------------------------------------------------
        self.caja_anthropic = wx.StaticBoxSizer(wx.VERTICAL, panel, _("Anthropic Claude"))
        marco_anthropic = self.caja_anthropic.GetStaticBox()
        self.caja_anthropic.Add(wx.StaticText(marco_anthropic, label=(
            _("Claves A&PI de Anthropic, una por línea. Se sacan en console.anthropic.com:"))),
            0, wx.ALL, 6)
        self.ia_claves_anthropic = etiquetar(wx.TextCtrl(
            marco_anthropic, style=wx.TE_MULTILINE, size=(520, 70)),
            _("Claves API de Anthropic"))
        self.ia_claves_anthropic.SetValue(
            self._claves_guardadas("ia_anthropic_claves"))
        self.caja_anthropic.Add(self.ia_claves_anthropic, 0, wx.EXPAND | wx.ALL, 6)
        self.ia_modelo_anthropic = self._fila_modelo(
            marco_anthropic, self.caja_anthropic, _("Modelo de &Claude:"),
            self.configuracion.obtener("ia_anthropic_modelos", []),
            str(self.configuracion.obtener("ia_anthropic_modelo",
                                           ia_servicio.MODELO_ANTHROPIC) or ""))
        caja.Add(self.caja_anthropic, 0, wx.EXPAND | wx.ALL, 6)

        # --- OpenAI y compatibles ----------------------------------------------
        self.caja_openai = wx.StaticBoxSizer(
            wx.VERTICAL, panel, _("OpenAI y servicios compatibles"))
        marco_openai = self.caja_openai.GetStaticBox()
        self.caja_openai.Add(wx.StaticText(marco_openai, label=(
            _("Vale cualquier servicio que hable la API de OpenAI, que hoy son casi todos:\n"
              "OpenAI, Groq, DeepSeek, Mistral, OpenRouter, xAI o Together. Elige uno de la\n"
              "lista o escribe la dirección que te den."))), 0, wx.ALL, 6)
        self._servicios_openai = list(ia_openai.SERVICIOS)
        self.ia_servicio_openai = fila_etiquetada(
            marco_openai, self.caja_openai, _("Ser&vicio:"),
            lambda p: wx.Choice(p, choices=[nombre for nombre, _url
                                            in self._servicios_openai]),
            horizontal=True)
        self.ia_servicio_openai.SetSelection(0)
        self.ia_servicio_openai.Bind(wx.EVT_CHOICE, self._al_elegir_servicio_openai)
        self.ia_url_openai = fila_etiquetada(
            marco_openai, self.caja_openai, _("Dirección del ser&vidor:"),
            lambda p: wx.TextCtrl(p, value=str(self.configuracion.obtener(
                "ia_openai_url", ia_openai.URL_POR_OMISION) or "")),
            horizontal=True, proporcion=1)
        self.caja_openai.Add(wx.StaticText(marco_openai, label=(
            _("Claves API, &una por línea:"))), 0, wx.ALL, 6)
        self.ia_claves_openai = etiquetar(wx.TextCtrl(
            marco_openai, style=wx.TE_MULTILINE, size=(520, 70)),
            _("Claves API del servicio compatible con OpenAI"))
        self.ia_claves_openai.SetValue(self._claves_guardadas("ia_openai_claves"))
        self.caja_openai.Add(self.ia_claves_openai, 0, wx.EXPAND | wx.ALL, 6)
        self.ia_modelo_openai = self._fila_modelo(
            marco_openai, self.caja_openai, _("Mode&lo:"),
            self.configuracion.obtener("ia_openai_modelos", []),
            str(self.configuracion.obtener("ia_openai_modelo",
                                           ia_servicio.MODELO_OPENAI) or ""))
        caja.Add(self.caja_openai, 0, wx.EXPAND | wx.ALL, 6)

        # --- Modelo local ---------------------------------------------------
        self.caja_local = wx.StaticBoxSizer(wx.VERTICAL, panel, _("Modelo local"))
        marco_local = self.caja_local.GetStaticBox()
        self.ia_url = fila_etiquetada(
            marco_local, self.caja_local, _("&Dirección del servidor:"),
            lambda p: wx.TextCtrl(p, value=str(self.configuracion.obtener(
                "ia_local_url", ia_servicio.URL_POR_OMISION) or ""), size=(420, -1)),
            horizontal=True, proporcion=1)
        self.ia_modelo_local = self._fila_modelo(
            marco_local, self.caja_local, "&Modelo cargado:",
            self.configuracion.obtener("ia_local_modelos", []),
            str(self.configuracion.obtener("ia_local_modelo",
                                           ia_servicio.MODELO_LOCAL) or ""))
        self.caja_local.Add(wx.StaticText(marco_local, label=(
            _("Vale cualquier servidor que hable la API de OpenAI: llama.cpp, Ollama o LM Studio.\n"
            "El modelo cargado tiene que admitir imágenes (LLaVA, Qwen-VL, MiniCPM-V...):\n"
            "los de solo texto aceptan la petición pero no ven la ilustración.")
        )), 0, wx.ALL, 6)
        # Aquí es donde se planta quien quiere IA local y no sabe montarla: ha
        # elegido «modelo local» y se encuentra teniendo que dar la dirección de un
        # servidor que no tiene.  El botón lleva al asistente, que se lo monta.
        self.boton_montar_ia = wx.Button(
            marco_local, label=_("¿No sabes montar tu IA local? &Pulsa aquí"))
        self.boton_montar_ia.Bind(wx.EVT_BUTTON, self._al_asistente_ia)
        self.caja_local.Add(self.boton_montar_ia, 0, wx.ALL, 6)
        self.caja_local.Add(wx.StaticText(marco_local, label=(
            _("El programa puede instalarte una inteligencia artificial completa dentro de\n"
            "su carpeta «data»: el motor, un modelo que ve y todo lo demás. Sin instalar\n"
            "nada en Windows y sin tocar el Ollama que puedas tener ya."))),
            0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        caja.Add(self.caja_local, 0, wx.EXPAND | wx.ALL, 6)

        # --- IA local del programa -------------------------------------------
        self.caja_ollama = wx.StaticBoxSizer(wx.VERTICAL, panel,
                                             _("IA local del programa"))
        marco_ollama = self.caja_ollama.GetStaticBox()
        self.ollama_resumen = etiquetar(wx.TextCtrl(
            marco_ollama, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP,
            size=(520, 70)), _("Estado de la IA local del programa"))
        self.caja_ollama.Add(self.ollama_resumen, 0, wx.EXPAND | wx.ALL, 6)
        self.caja_ollama.Add(wx.StaticText(marco_ollama, label=(
            _("No hay nada que rellenar: la dirección, el puerto y el modelo los pone el\n"
            "programa. Todo lo demás —arrancar, parar, instalar modelos— está en la\n"
            "pestaña «IA local»."))), 0, wx.ALL, 6)
        caja.Add(self.caja_ollama, 0, wx.EXPAND | wx.ALL, 6)

        # --- Comunes --------------------------------------------------------
        fila = wx.BoxSizer(wx.HORIZONTAL)
        self.boton_modelos = wx.Button(panel, label=_("&Obtener los modelos disponibles"))
        self.boton_probar = wx.Button(panel, label=_("Pro&bar la conexión"))
        self.boton_prompts = wx.Button(panel, label=_("&Gestor de prompts..."))
        self.boton_consumo = wx.Button(panel, label=_("Ver el consu&mo..."))
        self.boton_consumo.Bind(wx.EVT_BUTTON, self._al_ver_consumo)
        for boton in (self.boton_modelos, self.boton_probar, self.boton_prompts,
                      self.boton_consumo):
            fila.Add(boton, 0, wx.ALL, 6)
        caja.Add(fila, 0)
        self.boton_modelos.Bind(wx.EVT_BUTTON, self._al_obtener_modelos)
        self.boton_probar.Bind(wx.EVT_BUTTON, self._al_probar_ia)
        self.boton_prompts.Bind(wx.EVT_BUTTON, self._al_gestor_prompts)

        self.estado_ia = wx.StaticText(panel, label="")
        caja.Add(self.estado_ia, 0, wx.ALL, 6)

        self.ia_espera = fila_etiquetada(
            panel, caja, _("&Segundos de espera a la respuesta:"),
            lambda p: wx.SpinCtrl(p, min=10, max=600,
                                  initial=int(self.configuracion.obtener("ia_tiempo_espera", 90))),
            horizontal=True)

        self.ia_guardar = wx.CheckBox(
            panel, label=_("&Guardar las descripciones y recuperarlas al volver a abrir el documento"))
        self.ia_guardar.SetValue(bool(self.configuracion.obtener("ia_guardar_descripciones", True)))
        caja.Add(self.ia_guardar, 0, wx.ALL, 6)

        self.ia_anunciar = wx.CheckBox(
            panel, label=_("Decir la descripción guardada al &llegar a una imagen"))
        self.ia_anunciar.SetValue(bool(self.configuracion.obtener("ia_anunciar_descripcion", True)))
        caja.Add(self.ia_anunciar, 0, wx.ALL, 6)

        self.etiqueta_descripciones = wx.StaticText(panel, label=self._texto_descripciones())
        caja.Add(self.etiqueta_descripciones, 0, wx.ALL, 6)
        boton_borrar = wx.Button(panel, label=_("Borrar &todas las descripciones guardadas"))
        boton_borrar.Bind(wx.EVT_BUTTON, self._al_borrar_descripciones)
        caja.Add(boton_borrar, 0, wx.ALL, 6)

        panel.SetSizer(caja)
        self._al_cambiar_proveedor()
        return panel

    def _fila_modelo(self, padre, caja, etiqueta: str, modelos, actual: str) -> wx.ComboBox:
        """Crea la fila «modelo», que es lista y campo de texto a la vez.

        Se usa un ``wx.ComboBox`` y no un desplegable cerrado a propósito: los
        modelos nuevos salen antes de que el programa se entere, así que hay
        que poder escribir uno a mano aunque no esté en la lista guardada.
        """
        caja.Add(wx.StaticText(padre, label=etiqueta), 0, wx.LEFT | wx.RIGHT | wx.TOP, 6)
        opciones = [str(modelo) for modelo in (modelos or [])]
        if actual and actual not in opciones:
            opciones.insert(0, actual)
        control = etiquetar(wx.ComboBox(padre, value=actual, choices=opciones, size=(420, -1)),
                            etiqueta)
        caja.Add(control, 0, wx.EXPAND | wx.ALL, 6)
        return control

    def _clave_proveedor(self) -> str:
        """Clave del proveedor de IA elegido ahora mismo en la pestaña."""
        indice = max(self.ia_proveedor.GetSelection(), 0)
        return ia_servicio.PROVEEDORES[indice][0]

    def _claves_guardadas(self, ajuste: str) -> str:
        """Las claves API guardadas, listas para el cuadro de texto."""
        guardadas = self.configuracion.obtener(ajuste, []) or []
        if isinstance(guardadas, str):
            guardadas = guardadas.splitlines()
        return "\n".join(str(clave).strip() for clave in guardadas)

    @staticmethod
    def _lineas(control) -> list:
        """Las líneas con texto de un cuadro de varias líneas."""
        return [linea.strip() for linea in control.GetValue().splitlines() if linea.strip()]

    def _al_elegir_servicio_openai(self, evento) -> None:
        """Pone la dirección del servicio elegido en la lista."""
        indice = max(0, self.ia_servicio_openai.GetSelection())
        self.ia_url_openai.SetValue(self._servicios_openai[indice][1])

    def _al_ver_consumo(self, evento) -> None:
        """Enseña cuántas peticiones se han hecho y cuánto han gastado."""
        self._configuracion_de_ia()
        servicio = ia_servicio.Servicio(self.configuracion)
        respuesta = wx.MessageBox(
            servicio.consumo() + "\n\n" + _("¿Quieres poner el contador a cero?"),
            _("Consumo de la inteligencia artificial"),
            wx.YES_NO | wx.ICON_INFORMATION, self)
        if respuesta == wx.YES:
            ia_consumo.poner_a_cero(self.configuracion)
            self.configuracion.guardar()
            wx.MessageBox(_("Contador puesto a cero."),
                          _("Consumo de la inteligencia artificial"),
                          wx.OK | wx.ICON_INFORMATION, self)

    def _al_cambiar_proveedor(self) -> None:
        """Muestra solo los ajustes del proveedor elegido."""
        clave = self._clave_proveedor()
        for caja, quien in ((self.caja_gemini, "gemini"),
                            (self.caja_anthropic, "anthropic"),
                            (self.caja_openai, "openai"),
                            (self.caja_local, "local"),
                            (self.caja_ollama, "ollama_propio")):
            caja.GetStaticBox().Show(clave == quien)
            caja.ShowItems(clave == quien)
        if clave == "ollama_propio":
            self._resumir_ia_local()
        activo = clave != "off"
        self.boton_modelos.Enable(activo)
        self.boton_probar.Enable(activo)
        self.cuaderno.GetCurrentPage().Layout()

    def _resumir_ia_local(self) -> None:
        """Escribe en la pestaña de IA en qué estado está la local del programa."""
        from nucleo.ia import ollama

        if not ollama.instalado():
            self.ollama_resumen.SetValue(_(
                "Todavía no está instalada. Ve a la pestaña «IA local» y usa el asistente: "
                "en unos minutos la tienes funcionando."))
            return
        modelo = str(self.configuracion.obtener("ollama_modelo", "") or "")
        estado = _("en marcha") if ollama.gestor.estado().activo else _("parada")
        self.ollama_resumen.SetValue(_(
            "Instalada y %s, en %s.\nModelo con el que trabaja: %s.")
            % (estado, ollama.url_servidor(), modelo or _("ninguno elegido todavía")))

    def _configuracion_de_ia(self):
        """Vuelca a la configuración lo escrito en la pestaña.

        Hace falta antes de consultar modelos o de probar la conexión, porque
        el servicio lee siempre de la configuración y no de los controles.
        """
        establecer = self.configuracion.establecer
        establecer("ia_proveedor", self._clave_proveedor())
        establecer("ollama_calculo",
                   self._modos_calculo[max(0, self.ollama_calculo.GetSelection())][0])
        establecer("ollama_mantener_cargado", self.ollama_mantener.GetValue())
        establecer("ollama_contexto", self.ollama_contexto.GetValue())
        establecer("ollama_atencion_rapida", self.ollama_atencion.GetValue())
        establecer("ollama_arrancar_al_abrir", self.ollama_al_abrir.GetValue())
        establecer("ollama_cerrar_al_salir", self.ollama_al_salir.GetValue())
        _modelo_ollama = self.ollama_modelo.GetStringSelection()
        if _modelo_ollama and not _modelo_ollama.startswith("("):
            establecer("ollama_modelo", _modelo_ollama)
        establecer("ia_gemini_claves", self._lineas(self.ia_claves))
        establecer("ia_gemini_modelo", self.ia_modelo_gemini.GetValue().strip())
        establecer("ia_anthropic_claves", self._lineas(self.ia_claves_anthropic))
        establecer("ia_anthropic_modelo", self.ia_modelo_anthropic.GetValue().strip())
        establecer("ia_openai_claves", self._lineas(self.ia_claves_openai))
        establecer("ia_openai_url", self.ia_url_openai.GetValue().strip())
        establecer("ia_openai_modelo", self.ia_modelo_openai.GetValue().strip())
        establecer("ia_local_url", self.ia_url.GetValue().strip())
        establecer("ia_local_modelo", self.ia_modelo_local.GetValue().strip())
        establecer("ia_tiempo_espera", self.ia_espera.GetValue())

    def _resultado(self, texto: str, titulo: str, error: bool = False) -> None:
        """Enseña el resultado de una operación de IA.

        Va a un cuadro de mensaje y no solo a la etiqueta de estado: el texto
        de una etiqueta que cambia no lo lee el lector de pantalla, y el
        resultado de consultar los modelos o de probar la conexión es
        justamente lo que hay que oír.
        """
        self.estado_ia.SetLabel(texto)
        wx.MessageBox(texto, titulo, wx.OK | (wx.ICON_ERROR if error else wx.ICON_INFORMATION),
                      self)

    def _al_obtener_modelos(self, evento) -> None:
        """Pide al proveedor la lista de modelos y la guarda."""
        self._configuracion_de_ia()
        clave = self._clave_proveedor()
        servicio = ia_servicio.Servicio(self.configuracion)
        motivo = servicio.motivo_no_disponible()
        if motivo:
            self._resultado(motivo, _("Obtener los modelos"), error=True)
            return
        bien, resultado = ejecutar_esperando(
            self, _("Consultando los modelos disponibles. Puede tardar unos segundos..."),
            servicio.listar_modelos, _("Obteniendo los modelos"))
        if not bien:
            self._resultado(_("No se han podido obtener los modelos:\n\n%s") % resultado,
                            _("Obtener los modelos"), error=True)
            return
        modelos = list(resultado or [])
        if not modelos:
            if clave == "ollama_propio":
                # Con la IA local, «escribe el nombre a mano» no vale de nada:
                # no hay campo donde escribirlo y el modelo tiene que estar
                # descargado.  Lo que pasa es que todavía no hay ninguno.
                self._resultado(
                    _("Todavía no tienes ningún modelo descargado. Ve a la pestaña «IA "
                      "local» para instalar uno, o usa el asistente si es la primera "
                      "vez."), _("Obtener los modelos"))
            else:
                self._resultado(
                    _("El proveedor no ha devuelto ninguna lista de modelos. Escribe el "
                      "nombre del modelo a mano en el campo «Modelo»."),
                    _("Obtener los modelos"))
            return
        # A cada proveedor le corresponde su desplegable y su ajuste: la lista
        # se guarda para no tener que volver a pedirla, y cada uno tiene la suya.
        controles = {
            "gemini": (self.ia_modelo_gemini, "ia_gemini_modelos"),
            "anthropic": (self.ia_modelo_anthropic, "ia_anthropic_modelos"),
            "openai": (self.ia_modelo_openai, "ia_openai_modelos"),
            "local": (self.ia_modelo_local, "ia_local_modelos"),
        }
        control, ajuste = controles.get(clave, (self.ia_modelo_local, "ia_local_modelos"))
        elegido = control.GetValue().strip()
        control.Set(modelos)
        control.SetValue(elegido if elegido in modelos else modelos[0])
        self.configuracion.establecer(ajuste, modelos)
        self.configuracion.guardar()
        self._resultado(
            _("%d modelos disponibles para describir imágenes. Quedan guardados, así que no "
            "hace falta volver a pedirlos: el primero es %s.")
            % (len(modelos), modelos[0]), "Modelos obtenidos")

    def _al_probar_ia(self, evento) -> None:
        """Comprueba que el proveedor contesta."""
        self._configuracion_de_ia()
        servicio = ia_servicio.Servicio(self.configuracion)
        motivo = servicio.motivo_no_disponible()
        if motivo:
            self._resultado(motivo, _("Probar la conexión"), error=True)
            return
        bien, resultado = ejecutar_esperando(
            self, _("Probando la conexión con la inteligencia artificial..."),
            servicio.probar, _("Probando la conexión"))
        if not bien:
            self._resultado(_("La prueba ha fallado:\n\n%s") % resultado,
                            _("Probar la conexión"), error=True)
            return
        self._resultado(
            _("Conexión correcta con %s.\n\nHa respondido: %s")
            % (servicio.descripcion_del_modelo(), str(resultado)[:200]),
            _("Conexión correcta"))

    def _al_gestor_prompts(self, evento) -> None:
        """Abre el gestor de prompts de descripción."""
        from interfaz.dialogos.ia import DialogoPrompts

        with DialogoPrompts(self, self.configuracion) as dialogo:
            dialogo.ShowModal()

    @staticmethod
    def _texto_descripciones() -> str:
        """Describe cuánto ocupan las descripciones guardadas."""
        return (_("Las descripciones guardadas de todos los documentos ocupan %.0f KB.")
                % (descripciones.tamano_total() / 1024))

    def _al_borrar_descripciones(self, evento) -> None:
        """Borra las descripciones guardadas de todos los libros."""
        if wx.MessageBox(
                _("¿Borrar las descripciones guardadas de todos los libros?\n\n"
                "Habrá que volver a pedirlas a la inteligencia artificial."),
                _("Borrar las descripciones"),
                wx.YES_NO | wx.ICON_QUESTION | wx.NO_DEFAULT, self) != wx.YES:
            return
        # Son muchos archivos pequeños: con una biblioteca grande el borrado
        # tarda lo bastante como para que la ventana parezca colgada.
        ok, resultado = ejecutar_esperando(
            self, _("Borrando las descripciones guardadas..."), descripciones.vaciar_todo)
        if not ok:
            wx.MessageBox(_("No se han podido borrar las descripciones:\n\n%s") % resultado,
                          _("Borrar las descripciones"), wx.OK | wx.ICON_ERROR, self)
            return
        self.etiqueta_descripciones.SetLabel(
            _("Se han borrado las descripciones de %d documentos.") % resultado)

    def _pagina_ollama(self) -> wx.Panel:
        """La IA local que instala el programa: servidor, modelos y motor.

        Aquí se maneja todo lo que el asistente deja montado.  Está en su
        propia pestaña y no dentro de «Inteligencia artificial» porque son dos
        cosas distintas: allí se elige **con quién** se habla, y aquí se
        gobierna **un programa que corre en este ordenador** —arrancarlo,
        pararlo, darle modelos, decidir si usa la tarjeta gráfica—, que es más
        parecido a administrar un servicio que a rellenar unos ajustes.
        """
        panel = wx.ScrolledWindow(self.cuaderno, style=wx.VSCROLL)
        panel.SetScrollRate(0, 12)
        caja = wx.BoxSizer(wx.VERTICAL)

        caja.Add(wx.StaticText(panel, label=_(
            "El programa puede traer su propia inteligencia artificial, funcionando dentro\n"
            "de este ordenador: nada sale del equipo y no hay cuota. Se instala con el\n"
            "asistente y se maneja desde aquí."
        )), 0, wx.ALL, 6)

        self.ollama_asistente = wx.Button(
            panel, label=_("&Asistente: instalar la IA local paso a paso..."))
        self.ollama_asistente.Bind(wx.EVT_BUTTON, self._al_asistente_ia)
        caja.Add(self.ollama_asistente, 0, wx.ALL, 6)

        # -- estado del servidor ----------------------------------------------
        caja.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_("EL SERVIDOR")), 0, wx.ALL, 6)

        self.ollama_estado = etiquetar(wx.TextCtrl(
            panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP,
            size=(560, 90)), _("Estado de la IA local"))
        caja.Add(self.ollama_estado, 0, wx.EXPAND | wx.ALL, 6)

        fila = wx.BoxSizer(wx.HORIZONTAL)
        for etiqueta, manejador in (
                (_("&Comprobar"), self._al_comprobar_ollama),
                (_("&Arrancar"), self._al_arrancar_ollama),
                (_("&Detener"), self._al_detener_ollama),
                (_("&Reiniciar"), self._al_reiniciar_ollama),
                (_("Buscar &versión nueva"), self._al_actualizar_ollama)):
            boton = wx.Button(panel, label=etiqueta)
            boton.Bind(wx.EVT_BUTTON, manejador)
            fila.Add(boton, 0, wx.RIGHT, 6)
        caja.Add(fila, 0, wx.ALL, 6)

        # -- modelos -----------------------------------------------------------
        caja.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_("LOS MODELOS")), 0, wx.ALL, 6)

        self.ollama_modelo = fila_etiquetada(
            panel, caja, _("&Modelo con el que se trabaja:"),
            lambda p: wx.Choice(p, choices=[]), horizontal=True, proporcion=1)

        # Cada botón se guarda con su nombre porque la ayuda de Control+F1
        # busca los controles por el nombre con el que viven en el diálogo: uno
        # creado y soltado dentro del bucle no tiene nada que contar.
        fila_modelos = wx.BoxSizer(wx.HORIZONTAL)
        for nombre, etiqueta, manejador in (
                ("ollama_listar", _("Ac&tualizar la lista"), self._al_listar_modelos),
                ("ollama_instalar", _("&Instalar otro modelo..."),
                 self._al_instalar_modelo),
                ("ollama_importar", _("Importar uno del &disco..."),
                 self._al_importar_modelo),
                ("ollama_borrar", _("&Borrar el modelo elegido"),
                 self._al_borrar_modelo)):
            boton = wx.Button(panel, label=etiqueta)
            boton.Bind(wx.EVT_BUTTON, manejador)
            fila_modelos.Add(boton, 0, wx.RIGHT, 6)
            setattr(self, nombre, boton)
        caja.Add(fila_modelos, 0, wx.ALL, 6)

        caja.Add(wx.StaticText(panel, label=_(
            "Para describir imágenes el modelo tiene que admitirlas. Los que instala el\n"
            "asistente las admiten todos; si añades uno por tu cuenta, comprueba que sea\n"
            "de visión o solo servirá para preguntas de texto.\n"
            "«Importar uno del disco» mete un modelo que ya tengas descargado en formato\n"
            "GGUF, con su archivo de visión si lo tiene."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        # -- el motor ----------------------------------------------------------
        caja.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_("CÓMO TRABAJA EL MOTOR")), 0, wx.ALL, 6)

        self._modos_calculo = (
            ("auto", _("Usar la tarjeta gráfica si la hay (recomendado)")),
            ("cpu", _("Usar solo el procesador")),
        )
        self.ollama_calculo = fila_etiquetada(
            panel, caja, _("Con &qué calcula:"),
            lambda p: wx.Choice(p, choices=[rotulo for _clave, rotulo in self._modos_calculo]),
            horizontal=True)
        elegido = str(self.configuracion.obtener("ollama_calculo", "auto"))
        claves = [clave for clave, _rotulo in self._modos_calculo]
        self.ollama_calculo.SetSelection(claves.index(elegido) if elegido in claves else 0)

        self.ollama_mantener = fila_etiquetada(
            panel, caja, _("Minutos que el modelo se queda &cargado en memoria:"),
            lambda p: wx.SpinCtrl(p, min=0, max=120, initial=int(
                self.configuracion.obtener("ollama_mantener_cargado", 5))),
            horizontal=True)

        self.ollama_contexto = fila_etiquetada(
            panel, caja, _("Tamaño del conte&xto en fichas (0 = el del modelo):"),
            lambda p: wx.SpinCtrl(p, min=0, max=131072, initial=int(
                self.configuracion.obtener("ollama_contexto", 0))),
            horizontal=True)

        self.ollama_atencion = wx.CheckBox(
            panel, label=_("Atención rápida (ahorra memoria en las tarjetas que la admiten)"))
        self.ollama_atencion.SetValue(
            bool(self.configuracion.obtener("ollama_atencion_rapida", False)))
        caja.Add(self.ollama_atencion, 0, wx.ALL, 6)

        # -- arranque y cierre --------------------------------------------------
        caja.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_("ARRANQUE Y CIERRE")), 0, wx.ALL, 6)

        self.ollama_al_abrir = wx.CheckBox(
            panel, label=_("Arrancar el servidor al a&brir el programa"))
        self.ollama_al_abrir.SetValue(
            bool(self.configuracion.obtener("ollama_arrancar_al_abrir", False)))
        caja.Add(self.ollama_al_abrir, 0, wx.ALL, 6)

        self.ollama_al_salir = wx.CheckBox(
            panel, label=_("Cerrar el servidor al &salir del programa"))
        self.ollama_al_salir.SetValue(
            bool(self.configuracion.obtener("ollama_cerrar_al_salir", True)))
        caja.Add(self.ollama_al_salir, 0, wx.ALL, 6)

        caja.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.ALL, 6)
        self.ollama_desinstalar = wx.Button(
            panel, label=_("&Quitar la IA local y sus modelos del disco"))
        self.ollama_desinstalar.Bind(wx.EVT_BUTTON, self._al_desinstalar_ollama)
        caja.Add(self.ollama_desinstalar, 0, wx.ALL, 6)

        panel.SetSizer(caja)
        self._refrescar_ollama()
        return panel

    # -- IA local: acciones ---------------------------------------------------

    def _gestor_ollama(self):
        """El gestor de la IA local, con la configuración puesta."""
        from nucleo.ia import ollama

        ollama.gestor.configuracion = self.configuracion
        return ollama.gestor

    def _refrescar_ollama(self) -> None:
        """Vuelve a escribir el estado y la lista de modelos."""
        from nucleo.ia import ollama

        gestor = self._gestor_ollama()
        lineas = []
        if not ollama.instalado():
            lineas.append(_("La IA local no está instalada todavía."))
            lineas.append(_("Usa el asistente de arriba: te lleva de la mano y en unos "
                            "minutos la tienes funcionando."))
        else:
            lineas.append(_("Motor: Ollama %s, en la carpeta «data» del programa.")
                          % (ollama.version_instalada() or _("(versión desconocida)")))
            estado = gestor.estado()
            if estado.activo and estado.propio:
                lineas.append(_("Servidor: en marcha, en %s.") % ollama.url_servidor())
            elif estado.activo:
                lineas.append(_("Atención: en el puerto %d contesta otro servidor de Ollama "
                                "que no es el de este programa. No se va a usar ni a "
                                "cerrar.") % ollama.PUERTO)
            else:
                lineas.append(_("Servidor: parado. Se arranca solo la primera vez que se "
                                "le pida algo."))
            ocupado = gestor.espacio_de_los_modelos()
            if ocupado:
                lineas.append(_("Los modelos ocupan %s en el disco.")
                              % _tamano_en_disco(ocupado))
        self.ollama_estado.SetValue("\n".join(lineas))
        self._llenar_modelos_ollama()
        hay = ollama.instalado()
        for control in (self.ollama_desinstalar, self.ollama_modelo):
            control.Enable(hay)

    def _llenar_modelos_ollama(self) -> None:
        """Pone en el desplegable los modelos descargados."""
        from nucleo.ia import ollama

        elegido = str(self.configuracion.obtener("ollama_modelo", "") or "")
        nombres = []
        if ollama.instalado():
            try:
                if self._gestor_ollama().estado().activo:
                    nombres = [ficha["nombre"] for ficha in self._gestor_ollama().modelos()]
            except Exception as error:
                log.debug("No se han podido listar los modelos: %s", error)
        if elegido and elegido not in nombres:
            nombres.append(elegido)
        self.ollama_modelo.Set(nombres or [_("(ninguno todavía)")])
        if nombres:
            self.ollama_modelo.SetSelection(
                nombres.index(elegido) if elegido in nombres else 0)
        else:
            self.ollama_modelo.SetSelection(0)

    def _al_asistente_ia(self, evento) -> None:
        """Abre el asistente de instalación."""
        from interfaz.dialogos import asistente_ia

        with asistente_ia.DialogoAsistenteIA(self, self.configuracion) as dialogo:
            dialogo.ShowModal()
        self._refrescar_ollama()
        # El asistente puede haber activado la IA local: hay que reflejarlo en
        # la otra pestaña, o al aceptar se guardaría el proveedor de antes.
        claves = [clave for clave, _nombre in ia_servicio.PROVEEDORES]
        actual = str(self.configuracion.obtener("ia_proveedor", "off"))
        if actual in claves:
            self.ia_proveedor.SetSelection(claves.index(actual))
            self._al_cambiar_proveedor()

    def _al_comprobar_ollama(self, evento) -> None:
        """Vuelve a mirar el estado del servidor."""
        self._refrescar_ollama()
        self._anunciar_ollama(self.ollama_estado.GetValue().replace("\n", " "))

    def _al_arrancar_ollama(self, evento) -> None:
        """Arranca el servidor, esperando a que conteste."""
        from nucleo.ia import ollama

        def trabajo():
            self._gestor_ollama().iniciar()
            return _("Servidor arrancado en %s.") % ollama.url_servidor()

        self._tarea_ollama(trabajo, _("Arrancando el servidor..."))

    def _al_detener_ollama(self, evento) -> None:
        """Para el servidor."""
        def trabajo():
            resultado = self._gestor_ollama().detener(forzar=True)
            return {
                "detenido": _("Servidor detenido."),
                "no_habia": _("No había ningún servidor en marcha."),
                "ajeno": _("El servidor del puerto no es el de este programa: no se toca."),
                "fallo": _("No se ha podido detener; sigue contestando."),
            }.get(resultado, resultado)

        self._tarea_ollama(trabajo, _("Deteniendo el servidor..."))

    def _al_reiniciar_ollama(self, evento) -> None:
        """Para y vuelve a arrancar, que es lo que hace falta tras cambiar ajustes."""
        from nucleo.ia import ollama

        def trabajo():
            gestor = self._gestor_ollama()
            gestor.detener(forzar=True)
            gestor.iniciar()
            return _("Servidor reiniciado con los ajustes de ahora.")

        self._guardar_ajustes_ollama()
        self._tarea_ollama(trabajo, _("Reiniciando el servidor..."))

    def _al_actualizar_ollama(self, evento) -> None:
        """Mira si hay versión nueva de Ollama y la instala si el usuario quiere."""
        from nucleo.ia import ollama

        if not ollama.instalado():
            wx.MessageBox(_("Primero hay que instalar la IA local con el asistente."),
                          _("Buscar versión nueva"), wx.OK | wx.ICON_INFORMATION, self)
            return
        try:
            hay, instalada, ultima = self._gestor_ollama().hay_actualizacion()
        except Exception as error:
            wx.MessageBox(str(error), _("Buscar versión nueva"), wx.OK | wx.ICON_WARNING, self)
            return
        if not hay:
            wx.MessageBox(_("Ya tienes la última versión de Ollama (%s).") % instalada,
                          _("Buscar versión nueva"), wx.OK | wx.ICON_INFORMATION, self)
            return
        if wx.MessageBox(
                _("Hay una versión nueva de Ollama.\n\nTienes la %s y la última es la %s.\n\n"
                  "¿Quieres instalarla ahora? Se descarga algo más de un giga y el servidor "
                  "se reiniciará.") % (instalada or _("desconocida"), ultima),
                _("Buscar versión nueva"), wx.YES_NO | wx.ICON_QUESTION, self) != wx.YES:
            return
        self._descargar_con_progreso(
            _("Actualizando Ollama"),
            lambda progreso, cancelar: self._gestor_ollama().instalar(progreso, cancelar))
        self._refrescar_ollama()

    def _al_listar_modelos(self, evento) -> None:
        """Vuelve a preguntar al servidor qué modelos hay."""
        def trabajo():
            self._gestor_ollama().asegurar_en_marcha()
            return _("Lista de modelos actualizada.")

        self._tarea_ollama(trabajo, _("Preguntando por los modelos..."))

    def _al_instalar_modelo(self, evento) -> None:
        """Ofrece la lista de modelos y descarga el que se elija."""
        from nucleo.ia import modelos_vision, ollama

        if not ollama.instalado():
            wx.MessageBox(_("Primero hay que instalar la IA local con el asistente."),
                          _("Instalar un modelo"), wx.OK | wx.ICON_INFORMATION, self)
            return
        opciones = [modelos_vision.resumen(modelo) for modelo in modelos_vision.MODELOS]
        opciones.append(_("Otro: escribir el nombre a mano"))
        with wx.SingleChoiceDialog(self, _("Elige el modelo que quieres instalar:"),
                                   _("Instalar un modelo"), opciones) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                return
            elegido = dialogo.GetSelection()
        if elegido >= len(modelos_vision.MODELOS):
            with wx.TextEntryDialog(
                    self, _("Nombre del modelo tal como aparece en ollama.com,\n"
                            "por ejemplo «llava:7b»:"), _("Instalar un modelo")) as dialogo:
                if dialogo.ShowModal() != wx.ID_OK:
                    return
                etiqueta = dialogo.GetValue().strip()
            if not etiqueta:
                return
        else:
            etiqueta = modelos_vision.MODELOS[elegido].etiqueta
        gestor = self._gestor_ollama()
        self._descargar_con_progreso(
            _("Descargando %s") % etiqueta,
            lambda progreso, cancelar: gestor.descargar_modelo(etiqueta, progreso, cancelar))
        self.configuracion.establecer("ollama_modelo", etiqueta)
        self.configuracion.guardar()
        self._refrescar_ollama()

    def _al_importar_modelo(self, evento) -> None:
        """Mete en la IA local un modelo GGUF que el usuario ya tenga.

        Es el mismo hueco que llena «Instalar otro modelo», pero para quien no
        va a descargar nada: el que ya tiene el archivo bajado, el que lo lleva
        en un disco externo o el que usa un modelo que no está en la biblioteca
        de Ollama.  Con su proyector de visión, para que sirva de verdad aquí.
        """
        from interfaz.dialogos.importar_modelo import DialogoImportarModelo
        from nucleo.ia import ollama

        if not ollama.instalado():
            wx.MessageBox(_("Primero hay que instalar la IA local con el asistente."),
                          _("Importar un modelo"), wx.OK | wx.ICON_INFORMATION, self)
            return
        with DialogoImportarModelo(self) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                return
            nombre = dialogo.nombre
            modelo, vision = dialogo.ruta_modelo, dialogo.ruta_vision

        gestor = self._gestor_ollama()
        if not self._descargar_con_progreso(
                _("Importando %s") % nombre,
                lambda progreso, cancelar: gestor.importar_modelo(
                    nombre, modelo, vision, progreso, cancelar)):
            return
        # Se deja elegido: quien acaba de importarlo lo quiere usar, y si no
        # hubiera que buscarlo otra vez en la lista.
        self.configuracion.establecer("ollama_modelo", nombre)
        self.configuracion.guardar()
        self._refrescar_ollama()
        self._resultado(_("Modelo «%s» importado y elegido.") % nombre,
                        _("Importar un modelo"))

    def _al_borrar_modelo(self, evento) -> None:
        """Quita del disco el modelo elegido."""
        modelo = self.ollama_modelo.GetStringSelection()
        if not modelo or modelo.startswith("("):
            return
        if wx.MessageBox(
                _("¿Borrar el modelo «%s» del disco?\n\nSe puede volver a descargar cuando "
                  "quieras.") % modelo, _("Borrar el modelo"),
                wx.YES_NO | wx.ICON_QUESTION, self) != wx.YES:
            return

        def trabajo():
            self._gestor_ollama().borrar_modelo(modelo)
            return _("Modelo %s borrado.") % modelo

        self._tarea_ollama(trabajo, _("Borrando el modelo..."))

    def _al_desinstalar_ollama(self, evento) -> None:
        """Borra el motor y todos los modelos."""
        if wx.MessageBox(
                _("Se van a borrar del disco el motor y todos los modelos descargados.\n\n"
                  "Se puede volver a instalar cuando quieras con el asistente, pero habrá "
                  "que descargarlo todo otra vez.\n\n¿Seguir?"),
                _("Quitar la IA local"), wx.YES_NO | wx.ICON_WARNING, self) != wx.YES:
            return

        def trabajo():
            self._gestor_ollama().desinstalar()
            return _("La IA local y sus modelos se han borrado del disco.")

        self._tarea_ollama(trabajo, _("Borrando..."))
        if str(self.configuracion.obtener("ia_proveedor", "")) == "ollama_propio":
            self.configuracion.establecer("ia_proveedor", "off")
            claves = [clave for clave, _nombre in ia_servicio.PROVEEDORES]
            self.ia_proveedor.SetSelection(claves.index("off"))
            self._al_cambiar_proveedor()

    def _guardar_ajustes_ollama(self) -> None:
        """Lleva a la configuración lo que haya en esta pestaña.

        Hace falta antes de reiniciar el servidor: los ajustes del motor son
        variables de entorno que solo se leen al arrancarlo, así que reiniciar
        sin guardarlos primero volvería a levantarlo como estaba.
        """
        establecer = self.configuracion.establecer
        establecer("ollama_calculo",
                   self._modos_calculo[max(0, self.ollama_calculo.GetSelection())][0])
        establecer("ollama_mantener_cargado", self.ollama_mantener.GetValue())
        establecer("ollama_contexto", self.ollama_contexto.GetValue())
        establecer("ollama_atencion_rapida", self.ollama_atencion.GetValue())
        modelo = self.ollama_modelo.GetStringSelection()
        if modelo and not modelo.startswith("("):
            establecer("ollama_modelo", modelo)
        self.configuracion.guardar()

    def _tarea_ollama(self, trabajo, mensaje: str) -> None:
        """Ejecuta algo corto de la IA local esperando con el cursor de reloj.

        Lo corto va así y lo largo con barra de progreso: arrancar el servidor
        son dos segundos, y montar una ventana de progreso para eso sería más
        aparato que espera.
        """
        self._anunciar_ollama(mensaje)
        wx.BeginBusyCursor()
        try:
            resultado = trabajo()
        except Exception as error:
            wx.EndBusyCursor()
            self._anunciar_ollama(str(error))
            wx.MessageBox(str(error), _("IA local"), wx.OK | wx.ICON_WARNING, self)
            self._refrescar_ollama()
            return
        wx.EndBusyCursor()
        self._refrescar_ollama()
        self._anunciar_ollama(resultado)

    def _anunciar_ollama(self, mensaje: str) -> None:
        """Deja el mensaje donde el lector de pantalla lo va a encontrar."""
        actual = self.ollama_estado.GetValue()
        self.ollama_estado.SetValue("%s\n\n%s" % (mensaje, actual) if actual else mensaje)
        self.ollama_estado.SetInsertionPoint(0)

    def _descargar_con_progreso(self, titulo: str, tarea) -> bool:
        """Lanza una descarga larga con barra de progreso y cancelación.

        Se usa la misma ventana de progreso que al abrir un documento, para que
        quien ya la conozca sepa lo que tiene delante: la barra, el detalle y
        Escape para cancelar.
        """
        from nucleo.ia import ollama

        cancelado = {"si": False}
        dialogo = dialogos_progreso.DialogoProgreso(
            self, titulo, _("Preparando..."),
            al_cancelar=lambda: cancelado.__setitem__("si", True))
        dialogo.mostrar_tras(0)
        resultado = {"error": ""}

        def avisar(porcentaje, mensaje):
            wx.CallAfter(dialogo.avanzar, int(porcentaje), 100, mensaje)

        def hilo():
            try:
                tarea(avisar, lambda: cancelado["si"])
            except ollama.Cancelado:
                resultado["error"] = _("Cancelado. Lo descargado se conserva.")
            except Exception as error:
                registrar_excepcion(log, "Fallo en la descarga de la IA local", error)
                resultado["error"] = str(error)
            wx.CallAfter(terminar)

        def terminar():
            dialogo.cerrar()
            if resultado["error"]:
                wx.MessageBox(resultado["error"], titulo, wx.OK | wx.ICON_WARNING, self)

        threading.Thread(target=hilo, name="ollama", daemon=True).start()
        while dialogo:
            wx.Yield()
            if not dialogo.IsShown():
                break
            wx.MilliSleep(50)
        return not resultado["error"]

    def _pagina_apariencia(self) -> wx.Panel:
        """Fuente, tamaño y colores del texto."""
        panel = wx.Panel(self.cuaderno)
        caja = wx.BoxSizer(wx.VERTICAL)

        fuentes = [_("Fuente del sistema")] + sorted(set(wx.FontEnumerator.GetFacenames()))
        self.fuente = fila_etiquetada(
            panel, caja, _("&Fuente del texto:"),
            lambda p: wx.Choice(p, choices=fuentes), horizontal=True, proporcion=1,
        )
        actual = self.configuracion.obtener("fuente_nombre") or ""
        self.fuente.SetSelection(fuentes.index(actual) if actual in fuentes else 0)

        self.tamano = fila_etiquetada(
            panel, caja, _("&Tamaño de la letra:"),
            lambda p: wx.SpinCtrl(p, min=6, max=48,
                                  initial=int(self.configuracion.obtener("fuente_tamano") or 11)),
            horizontal=True,
        )

        self.usar_colores = wx.CheckBox(
            panel, label=_("Usar &colores propios en lugar de los del sistema"))
        self.usar_colores.SetValue(bool(self.configuracion.obtener("color_texto")
                                        or self.configuracion.obtener("color_fondo")))
        caja.Add(self.usar_colores, 0, wx.ALL, 6)

        self.color_texto = SelectorColor(
            panel, caja, _("Color de la &letra:"),
            self.configuracion.obtener("color_texto") or "#000000")
        self.color_fondo = SelectorColor(
            panel, caja, _("Color del f&ondo:"),
            self.configuracion.obtener("color_fondo") or "#FFFFFF")

        caja.Add(wx.StaticText(panel, label=(
            _("Los colores se eligen por su nombre. Las combinaciones de más contraste\n"
            "son letra amarilla o blanca sobre fondo negro, y letra negra sobre fondo\n"
            "crema o amarillo pálido.")
        )), 0, wx.ALL, 6)

        panel.SetSizer(caja)
        return panel

    def _pagina_sonidos(self) -> wx.Panel:
        """Activación, volumen y prueba de los sonidos de navegación."""
        panel = wx.Panel(self.cuaderno)
        caja = wx.BoxSizer(wx.VERTICAL)

        self.sonidos_activos = wx.CheckBox(panel, label=_("Reproducir &sonidos de navegación"))
        self.sonidos_activos.SetValue(bool(self.configuracion.obtener("sonidos_activados")))
        caja.Add(self.sonidos_activos, 0, wx.ALL, 6)

        self.solo_navegar = wx.CheckBox(
            panel, label=_("Sonar &solo al usar las teclas de navegación por elementos, "
                         "no al moverse con las flechas"))
        self.solo_navegar.SetValue(bool(self.configuracion.obtener("sonidos_solo_al_navegar")))
        caja.Add(self.solo_navegar, 0, wx.ALL, 6)

        self._avisos = (
            ("sonido", _("Con un sonido")),
            ("voz", _("Diciéndolos con la voz")),
            ("ambos", _("Con un sonido y diciéndolos")),
            ("ninguno", _("No avisar de los elementos")),
        )
        self.avisar_elementos = fila_etiquetada(
            panel, caja, _("A&visar de los elementos por los que pasa el cursor:"),
            lambda p: wx.Choice(p, choices=[rotulo for _clave, rotulo in self._avisos]),
            horizontal=True)
        _elegido_aviso = str(self.configuracion.obtener("avisar_elementos", "sonido"))
        self.avisar_elementos.SetSelection(max(0, next(
            (indice for indice, (clave, _r) in enumerate(self._avisos)
             if clave == _elegido_aviso), 0)))
        caja.Add(wx.StaticText(panel, label=_(
            "El pitido es lo más rápido de interpretar cuando ya se conoce, pero solo puede\n"
            "sonar uno por línea: en una línea que lleva un salto de página y una llamada de\n"
            "nota suena el salto de página, y la nota se queda sin señalar. En un libro muy\n"
            "anotado eso es la mitad de las notas.\n"
            "\n"
            "Dichos con la voz se oyen todos, y además se distingue una llamada de nota de un\n"
            "enlace normal, que en un texto clásico es la diferencia entre el número de una\n"
            "nota y el número del pasaje."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        # Deslizador de volumen.  Dos detalles importantes, comprobados
        # midiendo el nombre que anuncia el lector de pantalla:
        #
        #  * **Sin el estilo wx.SL_LABELS.**  Ese estilo añade al deslizador
        #    unas etiquetas con el valor, y Windows toma esa etiqueta como
        #    nombre del control: en lugar de «Volumen de los sonidos» se
        #    anunciaba «70», que no dice nada de para qué sirve.
        #  * El nombre se pasa **al construirlo** y además va precedido de su
        #    texto estático, que es de donde Windows lo deduce.
        #
        # El valor se muestra aparte, en un texto a la derecha, para que quien
        # lea la pantalla vea el número sin estorbar al nombre del control.
        valor_inicial = int(self.configuracion.obtener("sonidos_volumen") or 70)
        caja.Add(wx.StaticText(panel, label=_("&Volumen de los sonidos, de 0 a 100:")),
                 0, wx.LEFT | wx.RIGHT | wx.TOP, 6)
        fila_volumen = wx.BoxSizer(wx.HORIZONTAL)
        self.volumen = wx.Slider(panel, value=valor_inicial, minValue=0, maxValue=100,
                                 style=wx.SL_HORIZONTAL, name=_("Volumen de los sonidos"))
        fila_volumen.Add(self.volumen, 1, wx.EXPAND | wx.RIGHT, MARGEN)
        self.etiqueta_volumen = wx.StaticText(panel, label="%d %%" % valor_inicial)
        fila_volumen.Add(self.etiqueta_volumen, 0, wx.ALIGN_CENTER_VERTICAL)
        caja.Add(fila_volumen, 0, wx.EXPAND | wx.ALL, 6)
        self.volumen.Bind(wx.EVT_SLIDER, self._al_mover_volumen)

        nombres = self.sonidos.sonidos_disponibles() or ["(no hay sonidos)"]
        self.sonido_prueba = fila_etiquetada(
            panel, caja, _("&Escuchar un sonido para reconocerlo:"),
            lambda p: wx.Choice(p, choices=nombres), horizontal=True, proporcion=1,
        )
        self.sonido_prueba.SetSelection(0)
        boton = wx.Button(panel, label=_("&Reproducir el sonido elegido"))
        boton.Bind(wx.EVT_BUTTON, self._al_probar)
        caja.Add(boton, 0, wx.ALL, 6)

        caja.Add(wx.StaticText(panel, label=(
            _("Cada tipo de elemento tiene su propio sonido: los encabezados son un tono\n"
            "cuya altura baja según el nivel, las imágenes dos toques ascendentes, las\n"
            "tablas un acorde grave, las listas tres toques breves, y los separadores y\n"
            "las páginas un roce de papel.")
        )), 0, wx.ALL, 6)
        panel.SetSizer(caja)
        return panel

    def _pagina_integracion(self) -> wx.Panel:
        """Qué formatos abre el programa desde el explorador de Windows.

        Viene todo apagado de fábrica y a propósito: un programa portátil no
        tiene por qué tocar el equipo de nadie hasta que se lo pidan.
        """
        panel = wx.ScrolledWindow(self.cuaderno, style=wx.VSCROLL)
        panel.SetScrollRate(0, 12)
        caja = wx.BoxSizer(wx.VERTICAL)

        caja.Add(wx.StaticText(panel, label=_(
            "Marca los formatos que quieras abrir con este programa desde el\n"
            "explorador de archivos. Lo que no marques se queda como está.")),
            0, wx.ALL, 6)

        self._formatos_sistema = integracion.formatos_disponibles()
        etiquetas = ["%s   (%s)" % (extension, nombre) if nombre else extension
                     for extension, nombre in self._formatos_sistema]
        self.integracion_formatos = fila_etiquetada(
            panel, caja, _("&Formatos:"),
            lambda p: ListaCasillas(p, nombre=_("Formatos"), choices=etiquetas,
                                    size=(-1, 220)),
            proporcion=1)
        elegidas = {str(e).lower() for e in
                    (self.configuracion.obtener("integracion_formatos", []) or [])}
        for numero, (extension, _nombre) in enumerate(self._formatos_sistema):
            if extension in elegidas:
                self.integracion_formatos.Check(numero, True)
        caja.Add(wx.StaticText(panel, label=_(
            "Control+E marca todos y Control+D los desmarca.")), 0, wx.ALL, 6)

        self.integracion_menu = wx.CheckBox(panel, label=_(
            "Añadir «Abrir con %s» al &menú del botón derecho") % "Visor Universal")
        self.integracion_menu.SetValue(
            bool(self.configuracion.obtener("integracion_menu", True)))
        caja.Add(self.integracion_menu, 0, wx.ALL, 6)

        self.integracion_abrir_con = wx.CheckBox(panel, label=_(
            "Aparecer en el «&Abrir con» de Windows"))
        self.integracion_abrir_con.SetValue(
            bool(self.configuracion.obtener("integracion_abrir_con", True)))
        caja.Add(self.integracion_abrir_con, 0, wx.ALL, 6)

        caja.Add(wx.StaticText(panel, label=_(
            "En Windows 11 la orden del menú aparece en «Mostrar más opciones»,\n"
            "o directamente pulsando Mayús+F10.")), 0, wx.ALL, 6)

        predeterminado = wx.Button(panel, label=_("&Elegir programas predeterminados..."))
        predeterminado.Bind(wx.EVT_BUTTON, self._al_abrir_predeterminados)
        caja.Add(predeterminado, 0, wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_(
            "Windows no deja que un programa se ponga como predeterminado por su\n"
            "cuenta: hay que elegirlo en su propia ventana. Este botón la abre.")),
            0, wx.ALL, 6)

        panel.SetSizer(caja)
        return panel

    def _al_abrir_predeterminados(self, evento) -> None:
        """Abre la ventana de Windows donde se eligen los predeterminados."""
        if not integracion.abrir_ajustes_de_predeterminados():
            wx.MessageBox(
                _("No se ha podido abrir la ventana de Windows. Búscala en "
                  "Configuración, «Aplicaciones», «Aplicaciones predeterminadas»."),
                _("Integración con el sistema"), wx.OK | wx.ICON_INFORMATION, self)

    def _pagina_biblioteca(self) -> wx.Panel:
        """La biblioteca y la sincronización entre equipos.

        Las dos cosas van juntas porque son la misma idea vista desde dos
        sitios: dónde están mis libros y cómo llevo conmigo por dónde iba.
        """
        panel = wx.ScrolledWindow(self.cuaderno, style=wx.VSCROLL)
        panel.SetScrollRate(0, 12)
        caja = wx.BoxSizer(wx.VERTICAL)

        caja.Add(wx.StaticText(panel, label=_("LA BIBLIOTECA")), 0, wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_(
            "La biblioteca (Control+Mayús+B) reúne todos los libros que has abierto alguna\n"
            "vez y, además, los de las carpetas y bibliotecas de calibre que añadas. Desde\n"
            "ella se puede buscar una frase en todos los libros a la vez."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        self.boton_fuentes = wx.Button(panel, label=_("&Bibliotecas y carpetas..."))
        self.boton_fuentes.Bind(wx.EVT_BUTTON, self._al_gestionar_fuentes)
        caja.Add(self.boton_fuentes, 0, wx.ALL, 6)

        from nucleo import biblioteca as nucleo_biblioteca

        self._modos_calibre = [
            ("calibre", _("Importarla con todos los datos de calibre")),
            ("preguntar", _("Preguntar cada vez")),
            ("carpeta", _("Tratarla como una carpeta corriente")),
        ]
        claves_modo = [c for c, _n in self._modos_calibre]
        modo = str(self.configuracion.obtener("biblioteca_calibre_modo", "calibre"))
        self.biblioteca_calibre_modo = fila_etiquetada(
            panel, caja, _("Al añadir una carpeta que es una biblioteca de ca&libre:"),
            lambda p: wx.Choice(p, choices=[n for _c, n in self._modos_calibre]),
            horizontal=True)
        self.biblioteca_calibre_modo.SetSelection(
            claves_modo.index(modo) if modo in claves_modo else 0)

        self.biblioteca_calibre_anidadas = wx.CheckBox(panel, label=_(
            "Importar con sus datos las bibliotecas de calibre que haya &dentro de una carpeta"))
        self.biblioteca_calibre_anidadas.SetValue(
            bool(self.configuracion.obtener("biblioteca_calibre_anidadas", True)))
        caja.Add(self.biblioteca_calibre_anidadas, 0, wx.ALL, 6)

        self.biblioteca_leer_metadatos = wx.CheckBox(panel, label=_(
            "Leer los &metadatos de los EPUB al importar carpetas (título, autores, serie...)"))
        self.biblioteca_leer_metadatos.SetValue(
            bool(self.configuracion.obtener("biblioteca_leer_metadatos", True)))
        caja.Add(self.biblioteca_leer_metadatos, 0, wx.ALL, 6)

        self.biblioteca_importar_sinopsis = wx.CheckBox(panel, label=_(
            "Importar las si&nopsis"))
        self.biblioteca_importar_sinopsis.SetValue(
            bool(self.configuracion.obtener("biblioteca_importar_sinopsis", True)))
        caja.Add(self.biblioteca_importar_sinopsis, 0, wx.ALL, 6)

        self.biblioteca_un_libro_por_formato = wx.CheckBox(panel, label=_(
            "Si un libro de calibre está en varios formatos, poner &uno por formato"))
        self.biblioteca_un_libro_por_formato.SetValue(
            bool(self.configuracion.obtener("biblioteca_un_libro_por_formato", False)))
        caja.Add(self.biblioteca_un_libro_por_formato, 0, wx.ALL, 6)

        self.biblioteca_formatos_preferidos = fila_etiquetada(
            panel, caja, _("&Formatos preferidos, por orden:"),
            lambda p: wx.TextCtrl(p, value=str(self.configuracion.obtener(
                "biblioteca_formatos_preferidos", "") or "")),
            horizontal=True, proporcion=1)

        self.biblioteca_actualizar_al_abrir = wx.CheckBox(panel, label=_(
            "&Poner al día las bibliotecas de calibre al abrir la biblioteca"))
        self.biblioteca_actualizar_al_abrir.SetValue(
            bool(self.configuracion.obtener("biblioteca_actualizar_al_abrir", False)))
        caja.Add(self.biblioteca_actualizar_al_abrir, 0, wx.ALL, 6)

        self.biblioteca_anunciar_avance = fila_etiquetada(
            panel, caja, _("Decir el a&vance cada (segundos; 0 para no decirlo):"),
            lambda p: wx.SpinCtrl(p, min=0, max=600, initial=int(
                self.configuracion.obtener("biblioteca_anunciar_avance", 10) or 0)),
            horizontal=True)

        self._columnas_biblioteca = list(nucleo_biblioteca.COLUMNAS)
        elegidas = nucleo_biblioteca.columnas_elegidas(
            self.configuracion.obtener("biblioteca_columnas", None))
        caja.Add(wx.StaticText(panel, label=_("Columnas de la lis&ta de libros:")), 0,
                 wx.LEFT | wx.RIGHT | wx.TOP, 6)
        self.biblioteca_columnas = ListaCasillas(
            panel, _("Columnas de la lista de libros"),
            choices=[n for _c, n in self._columnas_biblioteca], size=(560, 150))
        for numero, (clave, _nombre) in enumerate(self._columnas_biblioteca):
            self.biblioteca_columnas.Check(numero, clave in elegidas)
        caja.Add(self.biblioteca_columnas, 0, wx.EXPAND | wx.ALL, 6)

        caja.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_("SEGUIR DONDE LO DEJASTE, EN OTRO EQUIPO")),
                 0, wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_(
            "Elige una carpeta que ya sincronices por tu cuenta —Dropbox, OneDrive, Drive,\n"
            "un pendrive o una carpeta de red— y el programa dejará ahí una copia de por\n"
            "dónde vas en cada libro, de tus marcadores, de tus notas y de las descripciones\n"
            "de imágenes. Al abrirlo en el otro equipo, se junta con lo que haya.\n\n"
            "No se sincronizan las preferencias: la voz y los atajos son de cada equipo.\n"
            "No se manda nada a ningún servidor: solo se escribe en esa carpeta."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        self.sincro_carpeta = fila_etiquetada(
            panel, caja, _("Carpeta &compartida (déjala vacía para no sincronizar):"),
            lambda p: wx.TextCtrl(p, value=str(
                self.configuracion.obtener("sincronizacion_carpeta", "") or "")),
            horizontal=True, proporcion=1)
        fila2 = wx.BoxSizer(wx.HORIZONTAL)
        elegir = wx.Button(panel, label=_("&Elegir carpeta..."))
        ahora = wx.Button(panel, label=_("&Sincronizar ahora"))
        elegir.Bind(wx.EVT_BUTTON, self._al_elegir_carpeta_sincro)
        ahora.Bind(wx.EVT_BUTTON, self._al_sincronizar_ahora)
        fila2.Add(elegir, 0, wx.RIGHT, 6)
        fila2.Add(ahora, 0)
        caja.Add(fila2, 0, wx.LEFT | wx.BOTTOM, 6)

        self.sincro_auto = wx.CheckBox(
            panel, label=_("Sincronizar sola al &arrancar y al cerrar"))
        self.sincro_auto.SetValue(
            bool(self.configuracion.obtener("sincronizacion_automatica", True)))
        caja.Add(self.sincro_auto, 0, wx.ALL, 6)

        panel.SetSizer(caja)
        return panel

    def _al_gestionar_fuentes(self, evento) -> None:
        """Abre la gestión de bibliotecas y carpetas."""
        del evento
        from interfaz.dialogos.biblioteca_gestor import DialogoFuentes

        with DialogoFuentes(self, self.configuracion) as dialogo:
            dialogo.ShowModal()

    def _guardar_biblioteca(self, establecer) -> None:
        """Guarda los ajustes de la biblioteca."""
        establecer("biblioteca_calibre_modo", self._modos_calibre[
            max(0, self.biblioteca_calibre_modo.GetSelection())][0])
        establecer("biblioteca_calibre_anidadas", self.biblioteca_calibre_anidadas.GetValue())
        establecer("biblioteca_leer_metadatos", self.biblioteca_leer_metadatos.GetValue())
        establecer("biblioteca_importar_sinopsis",
                   self.biblioteca_importar_sinopsis.GetValue())
        establecer("biblioteca_un_libro_por_formato",
                   self.biblioteca_un_libro_por_formato.GetValue())
        formatos = self.biblioteca_formatos_preferidos.GetValue().strip()
        if formatos:
            establecer("biblioteca_formatos_preferidos", formatos)
        establecer("biblioteca_actualizar_al_abrir",
                   self.biblioteca_actualizar_al_abrir.GetValue())
        establecer("biblioteca_anunciar_avance",
                   int(self.biblioteca_anunciar_avance.GetValue()))
        columnas = [self._columnas_biblioteca[i][0]
                    for i in self.biblioteca_columnas.marcados()]
        establecer("biblioteca_columnas", columnas or ["titulo"])

    def _al_elegir_carpeta_sincro(self, evento) -> None:
        """Abre el selector para la carpeta compartida."""
        del evento
        with wx.DirDialog(self, _("Carpeta que sincronizas por tu cuenta"),
                          defaultPath=self.sincro_carpeta.GetValue()) as dialogo:
            if dialogo.ShowModal() == wx.ID_OK:
                self.sincro_carpeta.SetValue(dialogo.GetPath())

    def _al_sincronizar_ahora(self, evento) -> None:
        """Sincroniza al momento con lo que haya escrito en el campo."""
        del evento
        from nucleo import sincronizacion

        carpeta = self.sincro_carpeta.GetValue().strip()
        if not carpeta:
            wx.MessageBox(_("Elige antes una carpeta compartida."),
                          _("Sincronizar"), wx.OK | wx.ICON_INFORMATION, self)
            return
        self.configuracion.establecer("sincronizacion_carpeta", carpeta)
        self.configuracion.guardar()
        resultado = sincronizacion.sincronizar(self.configuracion)
        wx.MessageBox(resultado.frase(), _("Sincronizar"),
                      wx.OK | (wx.ICON_ERROR if not resultado else wx.ICON_INFORMATION),
                      self)

    def _pagina_globales(self) -> wx.Panel:
        """Bandeja del sistema y teclas que funcionan desde cualquier programa."""
        panel = wx.Panel(self.cuaderno)
        caja = wx.BoxSizer(wx.VERTICAL)

        self.a_bandeja = wx.CheckBox(
            panel, label=_("Al &minimizar, dejar el programa solo en la bandeja del sistema"))
        self.a_bandeja.SetValue(bool(self.configuracion.obtener("minimizar_a_bandeja", False)))
        caja.Add(self.a_bandeja, 0, wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=(
            _("Con esto, al minimizar la ventana desaparece de la barra de tareas y del\n"
            "Alt+Tab, y queda un icono en la bandeja. La lectura en voz alta sigue sonando.\n"
            "Para volver: doble clic en el icono, su menú, o la tecla global de mostrar.")
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        caja.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.ALL, 6)

        self.globales_activas = wx.CheckBox(
            panel, label=_("&Usar teclas globales para manejar la lectura en voz alta"))
        self.globales_activas.SetValue(
            bool(self.configuracion.obtener("teclas_globales_activas", False)))
        caja.Add(self.globales_activas, 0, wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=(
            _("Las teclas globales las registra Windows y llegan aquí aunque estés en otro\n"
            "programa. Sirven para escuchar un libro mientras haces otra cosa: pausar,\n"
            "retroceder una frase o cambiar la velocidad sin volver al programa.")
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        caja.Add(wx.StaticText(panel, label=_("&Teclas asignadas:")), 0,
                 wx.LEFT | wx.RIGHT | wx.TOP, 6)
        self.lista_globales = etiquetar(ListaAccesible(
            panel, self.configuracion, "Teclas globales asignadas", size=(620, 200)),
            _("Teclas globales asignadas"))
        rellenar_columnas(self.lista_globales, (_("Acción"), "Tecla global"), (280, 320))
        caja.Add(self.lista_globales, 1, wx.EXPAND | wx.ALL, 6)

        fila = wx.BoxSizer(wx.HORIZONTAL)
        self.boton_cambiar_tecla = wx.Button(panel, label=_("&Cambiar la tecla..."))
        self.boton_quitar_tecla = wx.Button(panel, label=_("&Quitar la tecla"))
        self.boton_teclas_fabrica = wx.Button(panel, label=_("&Valores de fábrica"))
        self.boton_comprobar_teclas = wx.Button(panel, label=_("Com&probar todas"))
        for boton in (self.boton_cambiar_tecla, self.boton_quitar_tecla,
                      self.boton_teclas_fabrica, self.boton_comprobar_teclas):
            fila.Add(boton, 0, wx.ALL, 6)
        caja.Add(fila, 0)

        self.boton_cambiar_tecla.Bind(wx.EVT_BUTTON, self._al_cambiar_tecla)
        self.boton_quitar_tecla.Bind(wx.EVT_BUTTON, self._al_quitar_tecla)
        self.boton_teclas_fabrica.Bind(wx.EVT_BUTTON, self._al_teclas_de_fabrica)
        self.boton_comprobar_teclas.Bind(wx.EVT_BUTTON, self._al_comprobar_teclas)
        self.lista_globales.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._al_cambiar_tecla)

        self._globales = teclas_globales.combinaciones(self.configuracion)
        self._rellenar_globales()
        panel.SetSizer(caja)
        return panel

    def _rellenar_globales(self, seleccionar: int = 0) -> None:
        """Vuelca en la lista las teclas globales asignadas."""
        self.lista_globales.DeleteAllItems()
        for numero, accion in enumerate(teclas_globales.CATALOGO):
            self.lista_globales.InsertItem(numero, accion.etiqueta)
            self.lista_globales.SetItem(
                numero, 1, teclas_globales.legible(self._globales.get(accion.identificador, "")))
        indice = min(max(seleccionar, 0), len(teclas_globales.CATALOGO) - 1)
        self.lista_globales.Select(indice)
        self.lista_globales.Focus(indice)

    def _accion_global_elegida(self):
        """Acción sobre la que está el foco en la lista, o ``None``."""
        indice = self.lista_globales.fila_actual()
        if 0 <= indice < len(teclas_globales.CATALOGO):
            return indice, teclas_globales.CATALOGO[indice]
        return -1, None

    def _al_cambiar_tecla(self, evento) -> None:
        """Pide una combinación nueva para la acción elegida."""
        from interfaz.dialogos.teclas import DialogoCapturarTecla

        indice, accion = self._accion_global_elegida()
        if accion is None:
            return
        ventana = wx.GetTopLevelParent(self)
        principal = ventana.GetParent() or ventana
        # Mientras se captura hay que soltar las teclas globales: si no, la que
        # el usuario pulse la interceptaría Windows y nunca llegaría al diálogo.
        registro = getattr(principal, "registro_global", None)
        if registro is not None:
            registro.soltar()
        try:
            with DialogoCapturarTecla(self, accion, self._globales, principal) as dialogo:
                if dialogo.ShowModal() == wx.ID_OK and dialogo.combinacion:
                    self._globales[accion.identificador] = dialogo.combinacion
                    self._rellenar_globales(indice)
        finally:
            if registro is not None:
                registro.aplicar(self.configuracion)

    def _al_quitar_tecla(self, evento) -> None:
        """Deja una acción sin tecla global."""
        indice, accion = self._accion_global_elegida()
        if accion is None:
            return
        self._globales[accion.identificador] = ""
        self._rellenar_globales(indice)

    def _al_teclas_de_fabrica(self, evento) -> None:
        """Devuelve todas las teclas globales a sus valores de fábrica."""
        self._globales = {accion.identificador: accion.combinacion
                          for accion in teclas_globales.CATALOGO}
        self._rellenar_globales(self.lista_globales.fila_actual())

    def _al_comprobar_teclas(self, evento) -> None:
        """Prueba una a una si Windows concede las combinaciones asignadas.

        Es la comprobación que de verdad zanja el asunto: se piden al sistema y
        se sueltan al momento, de modo que se sabe cuáles están cogidas por
        otros programas **antes** de cerrar las opciones.
        """
        ventana = wx.GetTopLevelParent(self)
        principal = ventana.GetParent() or ventana
        registro = getattr(principal, "registro_global", None)
        if registro is not None:
            registro.soltar()
        lineas = []
        try:
            for accion in teclas_globales.CATALOGO:
                combinacion = self._globales.get(accion.identificador, "")
                if not combinacion:
                    lineas.append("%s: sin tecla." % accion.etiqueta)
                    continue
                motivo = (teclas_globales.revisar_forma(combinacion)
                          or teclas_globales.revisar_en_windows(principal, combinacion))
                lineas.append("%s (%s): %s" % (accion.etiqueta,
                                               teclas_globales.legible(combinacion),
                                               motivo or "libre."))
        finally:
            if registro is not None:
                registro.aplicar(self.configuracion)
        wx.MessageBox("\n".join(lineas), _("Comprobación de las teclas globales"),
                      wx.OK | wx.ICON_INFORMATION, self)

    def _pagina_avanzado(self) -> wx.Panel:
        """Registro de actividad y mantenimiento de la caché."""
        panel = wx.Panel(self.cuaderno)
        caja = wx.BoxSizer(wx.VERTICAL)

        self.nivel = fila_etiquetada(
            panel, caja, _("&Detalle del registro de actividad:"),
            lambda p: wx.Choice(p, choices=list(modulo_registro.NIVELES)),
            horizontal=True,
        )
        actual = str(self.configuracion.obtener("nivel_registro") or "INFO")
        self.nivel.SetSelection(
            list(modulo_registro.NIVELES).index(actual) if actual in modulo_registro.NIVELES else 1
        )
        caja.Add(wx.StaticText(panel, label=(
            _("Usa «DEBUG» solo para averiguar la causa de un problema: genera muchísima\n"
            "información y hace el programa algo más lento.")
        )), 0, wx.ALL, 6)

        # La casilla de usar la caché va **aquí** y no en «Lectura»: no es una
        # opción de cómo se lee sino de rendimiento, y va pegada al botón que
        # vacía esa misma caché, que es lo que se busca cuando se viene a esto.
        self.cache = wx.CheckBox(
            panel, label=_("Usar la ca&ché para que los documentos ya leídos se "
                           "abran al instante"))
        self.cache.SetValue(bool(self.configuracion.obtener("usar_cache")))
        caja.Add(self.cache, 0, wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_(
            "La primera vez que se abre un documento se analiza entero; con la caché, la\n"
            "segunda vez se abre al instante. Apagarla solo tiene sentido si andas muy justo\n"
            "de disco: el análisis se repetiría cada vez."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        self.etiqueta_cache = wx.StaticText(panel, label=self._texto_cache())
        caja.Add(self.etiqueta_cache, 0, wx.ALL, 6)
        boton_cache = wx.Button(panel, label=_("&Vaciar la caché"))
        boton_cache.Bind(wx.EVT_BUTTON, self._al_vaciar_cache)
        caja.Add(boton_cache, 0, wx.ALL, 6)

        boton_carpeta = wx.Button(panel, label=_("Abrir la carpeta de &datos"))
        boton_carpeta.Bind(wx.EVT_BUTTON, self._al_abrir_carpeta)
        caja.Add(boton_carpeta, 0, wx.ALL, 6)

        caja.Add(wx.StaticText(panel, label=_("ACTUALIZACIONES")), 0, wx.ALL, 6)
        self.comprobar_actualizaciones = wx.CheckBox(
            panel, label=_("Comprobar al arrancar si hay una versión &nueva"))
        self.comprobar_actualizaciones.SetValue(
            bool(self.configuracion.obtener("comprobar_actualizaciones", True)))
        caja.Add(self.comprobar_actualizaciones, 0, wx.ALL, 6)
        caja.Add(wx.StaticText(panel, label=_(
            "Es una consulta diminuta que no retrasa la apertura, y solo dice algo\n"
            "cuando hay una versión nueva de verdad."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        self._origenes = list(actualizaciones.ORIGENES)
        claves_origen = [clave for clave, _nombre in self._origenes]
        origen = str(self.configuracion.obtener("actualizaciones_origen", "") or "")
        url_propia = str(self.configuracion.obtener("actualizaciones_url", "") or "")
        self.actualizaciones_origen = fila_etiquetada(
            panel, caja, _("Buscar las actualizaciones &en:"),
            lambda p: wx.Choice(p, choices=[nombre for _c, nombre in self._origenes]),
            horizontal=True)
        self.actualizaciones_origen.SetSelection(
            claves_origen.index(origen) if origen in claves_origen else 0)
        self.actualizaciones_url = fila_etiquetada(
            panel, caja, _("Dirección &personalizada:"),
            lambda p: wx.TextCtrl(p, value=url_propia),
            horizontal=True, proporcion=1)
        caja.Add(wx.StaticText(panel, label=_(
            "La dirección personalizada puede ser una carpeta web con version.json y el\n"
            "paquete, o la de un repositorio de GitHub. Venga de donde venga, solo se\n"
            "instala un paquete firmado por el autor."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        self.actualizaciones_origen.Bind(wx.EVT_CHOICE, self._al_cambiar_origen)
        self._al_cambiar_origen(None)

        panel.SetSizer(caja)
        return panel

    # -- acciones ------------------------------------------------------------

    def _al_cambiar_origen(self, evento) -> None:
        """La dirección personalizada solo se puede escribir si es la elegida."""
        del evento
        clave = self._origenes[max(0, self.actualizaciones_origen.GetSelection())][0]
        self.actualizaciones_url.Enable(clave == "personalizada")

    @staticmethod
    def _texto_cache() -> str:
        """Describe cuánto ocupa la caché."""
        return _("La caché ocupa ahora %.1f MB.") % (cache.tamano_actual() / 1048576)

    def _al_mover_volumen(self, evento) -> None:
        """Actualiza el número que acompaña al deslizador de volumen.

        El lector de pantalla anuncia el valor por su cuenta al moverlo con
        las flechas, así que aquí solo se refresca el texto de la pantalla.
        """
        self.etiqueta_volumen.SetLabel("%d %%" % self.volumen.GetValue())

    def _al_probar(self, evento) -> None:
        """Reproduce el sonido seleccionado con el volumen elegido."""
        self.sonidos.establecer_volumen(self.volumen.GetValue())
        self.sonidos.activado = True
        nombre = self.sonido_prueba.GetStringSelection()
        if nombre and not nombre.startswith("("):
            self.sonidos.reproducir(nombre)

    def _al_vaciar_cache(self, evento) -> None:
        """Borra la caché de libros analizados."""
        # La caché puede tener cientos de megas; borrarla no es instantáneo.
        ok, resultado = ejecutar_esperando(
            self, _("Vaciando la caché..."), cache.vaciar)
        if not ok:
            wx.MessageBox(_("No se ha podido vaciar la caché:\n\n%s") % resultado,
                          _("Vaciar la caché"), wx.OK | wx.ICON_ERROR, self)
            return
        self.etiqueta_cache.SetLabel(
            _n("Se ha eliminado %d archivo de la caché.",
               "Se han eliminado %d archivos de la caché.", resultado) % resultado
        )

    def _al_abrir_carpeta(self, evento) -> None:
        """Abre la carpeta ``data`` en el explorador de archivos."""
        from nucleo import rutas

        rutas.abrir_en_explorador(rutas.directorio_datos())

    def _guardar_integracion(self, establecer) -> None:
        """Guarda los formatos elegidos y los escribe en el registro.

        Se escribe aquí y no al arrancar porque es lo que el usuario espera:
        aceptar el diálogo deja el explorador como acaba de decir.
        """
        if not hasattr(self, "integracion_formatos"):
            return
        elegidos = [self._formatos_sistema[numero][0]
                    for numero in range(len(self._formatos_sistema))
                    if self.integracion_formatos.IsChecked(numero)]
        menu = self.integracion_menu.GetValue()
        abrir_con = self.integracion_abrir_con.GetValue()
        establecer("integracion_formatos", elegidos)
        establecer("integracion_menu", menu)
        establecer("integracion_abrir_con", abrir_con)
        if elegidos:
            integracion.aplicar(elegidos, menu, abrir_con)
        else:
            integracion.quitar()

    def _al_aceptar(self, evento) -> None:
        """Guarda todos los ajustes y avisa si hay que reabrir el libro."""
        establecer = self.configuracion.establecer
        establecer("tablas_en_linea", self.tablas.GetValue())
        establecer("anunciar_imagenes_sin_texto", self.imagenes.GetValue())
        establecer("ajuste_de_linea", self.ajuste.GetValue())
        establecer("renglon_por_frase", self.renglon_frase.GetValue())
        establecer("ancho_maximo_linea", int(self.ancho_linea.GetValue()))
        establecer("navegacion_circular", self.circular.GetValue())
        establecer("recordar_posicion", self.recordar.GetValue())
        establecer("mostrar_formato", self.formato.GetValue())
        establecer("usar_cache", self.cache.GetValue())
        establecer("marcar_llamadas_de_nota", self.marcar_notas.GetValue())
        establecer("solo_articulo", self.solo_articulo.GetValue())
        establecer("revisar_epub", self.revisar_epub.GetValue())
        establecer("braille_contraido", self.braille_contraido.GetValue())
        establecer("sincronizacion_carpeta", self.sincro_carpeta.GetValue().strip())
        establecer("sincronizacion_automatica", self.sincro_auto.GetValue())
        self._guardar_biblioteca(establecer)
        establecer("usar_pestanas", self.usar_pestanas.GetValue())
        self._guardar_integracion(establecer)
        establecer("restaurar_documentos", self.restaurar_documentos.GetValue())
        establecer("pestanas_al_abrir",
                   self._donde_abrir[max(0, self.pestanas_al_abrir.GetSelection())][0])
        establecer("mostrar_arbol", self.mostrar_arbol.GetValue())
        establecer("barra_recuentos", self.barra_recuentos.GetValue())
        establecer("mostrar_bienvenida", self.mostrar_bienvenida.GetValue())
        establecer("pdf_estructura", self.pdf_estructura.GetValue())
        establecer("pdf_geometria", self.pdf_geometria.GetValue())
        establecer("pdf_ocr_modo", self._modos_ocr[max(0, self.pdf_modo.GetSelection())][0])
        establecer("pdf_ocr_gris", self.ocr_gris.GetValue())
        establecer("pdf_ocr_contraste", self.ocr_contraste.GetValue() / 10.0)
        establecer("pdf_ocr_binarizar", self.ocr_binarizar.GetValue())
        establecer("pdf_ocr_umbral", self.ocr_umbral.GetValue())
        establecer("pdf_ocr_psm", self._psm[max(0, self.ocr_psm.GetSelection())][0])
        establecer("pdf_ocr_oem", self._oem[max(0, self.ocr_oem.GetSelection())][0])
        establecer("pdf_ocr_escala", self._escalas[max(0, self.ocr_escala.GetSelection())][0])
        establecer("pdf_ocr_dpi", self.ocr_dpi.GetValue())
        establecer("pdf_ocr_confianza", self.ocr_confianza.GetValue())
        establecer("pdf_ocr_quitar_simbolos", self.ocr_simbolos.GetValue())
        establecer("pdf_ocr_tablas", self.ocr_tablas.GetValue())
        establecer("pdf_ocr_esmerado", self.ocr_esmerado.GetValue())
        establecer("daisy_velocidad", self.daisy_velocidad.GetValue())
        establecer("daisy_volumen", self.daisy_volumen.GetValue())
        establecer("daisy_mover_cursor", self.daisy_cursor.GetValue())
        establecer("daisy_reproducir_al_abrir", self.daisy_al_abrir.GetValue())
        establecer("pdf_ocr_maximo", self.pdf_maximo.GetValue())

        establecer("columnas_decir_fila", self.decir_fila.GetValue())
        posicion = self._teclas_lista[max(0, self.lista_tecla_posicion.GetSelection())][0]
        ir_a = self._teclas_lista[max(0, self.lista_tecla_ir_a.GetSelection())][0]
        # Por si acaso: las dos con la misma tecla no pueden funcionar.
        if posicion and posicion == ir_a:
            posicion = ""
        establecer("lista_tecla_posicion", posicion)
        establecer("lista_tecla_ir_a", ir_a)
        establecer("columnas_decir_encabezado", self.decir_encabezado.GetValue())
        establecer("columnas_decir_contenido", self.decir_contenido.GetValue())

        self._configuracion_de_ia()
        establecer("ia_guardar_descripciones", self.ia_guardar.GetValue())
        establecer("ia_anunciar_descripcion", self.ia_anunciar.GetValue())

        establecer("comprobar_actualizaciones", self.comprobar_actualizaciones.GetValue())
        establecer("actualizaciones_origen", self._origenes[
            max(0, self.actualizaciones_origen.GetSelection())][0])
        establecer("actualizaciones_url", self.actualizaciones_url.GetValue().strip())

        establecer("minimizar_a_bandeja", self.a_bandeja.GetValue())
        establecer("teclas_globales_activas", self.globales_activas.GetValue())
        teclas_globales.guardar(self.configuracion, self._globales)

        eleccion = self.fuente.GetStringSelection()
        establecer("fuente_nombre", "" if eleccion == _("Fuente del sistema") else eleccion)
        establecer("fuente_tamano", self.tamano.GetValue())
        if self.usar_colores.GetValue():
            establecer("color_texto", self.color_texto.valor())
            establecer("color_fondo", self.color_fondo.valor())
        else:
            establecer("color_texto", "")
            establecer("color_fondo", "")

        establecer("sonidos_activados", self.sonidos_activos.GetValue())
        establecer("sonidos_solo_al_navegar", self.solo_navegar.GetValue())
        establecer("avisar_elementos",
                   self._avisos[max(0, self.avisar_elementos.GetSelection())][0])
        establecer("sonidos_volumen", self.volumen.GetValue())
        self.sonidos.activado = self.sonidos_activos.GetValue()
        self.sonidos.establecer_volumen(self.volumen.GetValue())

        establecer("idioma", self._idiomas[max(self.idioma.GetSelection(), 0)][0])

        nivel = self.nivel.GetStringSelection() or "INFO"
        establecer("nivel_registro", nivel)
        modulo_registro.cambiar_nivel(nivel)

        self.hay_que_reanalizar = any(
            self.configuracion.obtener(clave) != self._valores_previos[clave]
            for clave in OPCIONES_QUE_REANALIZAN
        )
        self.configuracion.guardar()
        log.info("Opciones guardadas (reanalizar=%s)", self.hay_que_reanalizar)
        self.EndModal(wx.ID_OK)


def _tamano_en_disco(bytes_: int) -> str:
    """«3,4 GB», para decir lo que ocupan los modelos."""
    for unidad, salto in ((_("GB"), 1024 ** 3), (_("MB"), 1024 ** 2)):
        if bytes_ >= salto:
            return "%s %s" % (("%.1f" % (bytes_ / salto)).replace(".", ","), unidad)
    return _("%d KB") % (bytes_ // 1024)
