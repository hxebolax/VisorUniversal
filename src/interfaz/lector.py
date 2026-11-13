# -*- coding: utf-8 -*-
"""Panel de lectura: el control de texto y todo lo que ocurre dentro de él.

Dos ideas sostienen este módulo:

**1. Ventana deslizante.**  Un libro puede tener treinta millones de
caracteres.  Volcarlos de golpe en el control de texto de Windows hace que
cada movimiento del cursor tarde segundos, porque el control recalcula la
disposición desde el principio del contenido cargado.  La solución es cargar
solo un tramo de unos cuantos cientos de miles de caracteres alrededor de
donde está leyendo el usuario, y recargarlo cuando se acerca a un borde.

Para el resto de la aplicación esto es invisible: todas las posiciones que se
manejan fuera de este módulo son **absolutas dentro del libro**.  Aquí, y
solo aquí, se traducen a las coordenadas del control.

**2. El control de texto hace el trabajo accesible.**  Al ser un control de
edición de verdad, el lector de pantalla lee la línea al mover el cursor,
permite seleccionar, copiar y usar sus propias órdenes de lectura.  No hay
que reinventar nada de eso.
"""

from __future__ import annotations

from typing import Callable

import wx

from interfaz.temporizadores import parar_al_destruir
from interfaz.accesible import etiquetar
from interfaz.bienvenida import texto_breve, texto_de_bienvenida
from interfaz.ventanas_win32 import suprimir_menu_contextual
from nucleo.documento import Documento
from nucleo.idioma import _
from nucleo.marcas import TipoMarca
from nucleo.navegacion import elementos_en_linea
from nucleo.registro import cronometro, obtener_registro
from nucleo.segmentador import partir_en_renglones
from nucleo.texto import MapaUtf16

log = obtener_registro(__name__)

#: Por debajo de este tamaño el libro se carga **entero** y no hay ventana
#: deslizante.  El valor está medido: cargar tres millones de caracteres en el
#: control cuesta unos 340 ms y, una vez cargados, mover el cursor cuesta lo
#: mismo que con cuatrocientos mil.  Como una novela de mil quinientas páginas
#: no llega a esa cifra, en la práctica casi ningún libro se divide en tramos,
#: y así todas las teclas propias del control (Control+Fin, Av Pág, la barra de
#: desplazamiento, seleccionar todo) abarcan el libro completo.
UMBRAL_COMPLETO = 3_000_000

#: Tamaño del tramo que se mantiene cargado en los libros que sí superan el
#: umbral.  Cargarlo cuesta unos 110 ms, que es el precio de cada recarga.
TAMANO_VENTANA = 1_200_000

#: Distancia a un borde del tramo a partir de la cual se vuelve a centrar.
#: Es la cuarta parte del tamaño: al recentrar, el cursor queda a 600.000
#: caracteres de cada borde, así que se lee mucho antes de volver a recargar.
MARGEN_RECARGA = TAMANO_VENTANA // 4

#: Número máximo de tramos con formato que se aplican de una vez.  Cada uno
#: obliga al control de Windows a rehacer la disposición del texto y cuesta
#: unos tres milisegundos, así que el límite es bajo a propósito.
MAXIMO_TRAMOS_FORMATO = 120

#: Radio, en caracteres alrededor del cursor, al que se aplica el formato.
RADIO_FORMATO = 6_000

#: Cada cuántos milisegundos se comprueba si el cursor ha cambiado de sitio.
INTERVALO_VIGILANCIA = 120

#: Cuánto tiene que llevar el cursor quieto para aplicar el formato.  Dar
#: estilo obliga al control de Windows a rehacer la disposición del texto, y
#: hacerlo mientras el lector de pantalla está leyendo justo por ahí se nota.
#: Esperando a que el cursor pare, ese trabajo cae en los huecos.
RETARDO_FORMATO = 500


class PanelLectura(wx.Panel):
    """Muestra el texto del libro y controla la posición de lectura.

    :param padre: Ventana contenedora.
    :param configuracion: Preferencias de la aplicación.
    :param sonidos: Gestor de sonidos de navegación.
    :param anunciador: Canal de comunicación con el lector de pantalla.
    :param al_moverse: Función que se llama al cambiar la posición del cursor.
    """

    def __init__(self, padre: wx.Window, configuracion, sonidos, anunciador,
                 al_moverse: Callable[..., None] | None = None,
                 version: str = "") -> None:
        super().__init__(padre)
        self.version = version
        self.configuracion = configuracion
        self.sonidos = sonidos
        self.anunciador = anunciador
        self._al_moverse = al_moverse

        self.documento: Documento | None = None
        self._inicio_ventana = 0
        self._fin_ventana = 0
        self._mapa = MapaUtf16("")
        #: Tramo del control que está resaltado por la lectura en voz alta, en
        #: posiciones del control (no del libro), o None.
        self._resalte: tuple[int, int] | None = None
        self._ultima_linea = -1
        self._ultima_posicion = -1
        self._rango_formateado = (0, 0)
        #: Petición de formato aplazada hasta que el cursor deje de moverse.
        self._formateo_pendiente: wx.CallLater | None = None
        self._historial: list[int] = []
        self._indice_historial = -1
        self._cargando = False
        self._fabrica_soltar: Callable[[], wx.DropTarget] | None = None
        # Windows guarda un puntero a la función que filtra los mensajes del
        # control, así que hay que mantenerla viva mientras el panel exista.
        self._menus_suprimidos: list = []

        self._contenedor = wx.BoxSizer(wx.VERTICAL)
        self.texto = self._crear_control()
        self._contenedor.Add(self.texto, 1, wx.EXPAND)
        self.SetSizer(self._contenedor)
        self.Bind(wx.EVT_SIZE, self._al_cambiar_tamano)

        self._vigilante = wx.Timer(self)
        parar_al_destruir(self, self._vigilante)
        self.Bind(wx.EVT_TIMER, self._al_vigilar, self._vigilante)

    # -- creación del control ------------------------------------------------

    def _crear_control(self) -> wx.TextCtrl:
        """Crea el control de texto con el estilo que indican las preferencias.

        El ajuste de línea no se puede cambiar en caliente en Windows, así que
        cambiar esa opción obliga a recrear el control (véase
        :meth:`alternar_ajuste_de_linea`).
        """
        estilo = wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 | wx.TE_NOHIDESEL
        estilo |= wx.TE_WORDWRAP if self.configuracion.obtener("ajuste_de_linea") else wx.TE_DONTWRAP
        control = etiquetar(wx.TextCtrl(self, style=estilo), _("Texto del documento"))
        # El menú contextual se bloquea por las TRES vías que puede tomar,
        # porque ninguna basta por sí sola:
        #
        # 1. El mensaje WM_CONTEXTMENU del sistema.  Es la vía principal: el
        #    control de texto de Windows muestra su menú por su cuenta, sin
        #    pasar por el sistema de eventos de wxPython (la documentación de
        #    wxWidgets lo dice expresamente: wx.TextCtrl no entrega
        #    EVT_CONTEXT_MENU y aparece el menú del sistema).
        # 2. El botón derecho del ratón.  En Windows el menú se genera tras
        #    soltar el botón derecho *solo si nadie ha atendido ese evento*,
        #    así que atenderlo lo corta antes de que llegue a producirse.
        # 3. La tecla Aplicaciones y Mayús+F10, que se filtran en la ventana
        #    principal junto con el resto de las teclas.
        control.Bind(wx.EVT_CONTEXT_MENU, self._al_menu_contextual)
        control.Bind(wx.EVT_RIGHT_DOWN, self._al_boton_derecho)
        control.Bind(wx.EVT_RIGHT_UP, self._al_boton_derecho)
        control.Bind(wx.EVT_RIGHT_DCLICK, self._al_boton_derecho)
        self._menus_suprimidos.append(suprimir_menu_contextual(control))
        self._aplicar_apariencia(control)
        # El destino de arrastrar y soltar pertenece al control, así que hay
        # que crear uno nuevo cada vez que el control se rehace (al cambiar el
        # ajuste de línea); de lo contrario, soltar un libro dejaría de
        # funcionar tras usar esa opción.
        if self._fabrica_soltar is not None:
            control.SetDropTarget(self._fabrica_soltar())
        return control

    # -- ancho de la línea ---------------------------------------------------

    def _al_cambiar_tamano(self, evento) -> None:
        """Recalcula el ancho del texto cuando cambia el de la ventana."""
        self.ajustar_ancho()
        evento.Skip()

    def ajustar_ancho(self) -> None:
        """Estrecha la columna de texto si el usuario ha pedido un ancho máximo.

        Un renglón muy largo es incómodo de seguir: al llegar al final hay que
        volver al principio de la línea siguiente, y cuanto más largo sea el
        renglón más fácil es perderse por el camino.  En papel nadie compone a
        más de unos setenta caracteres por línea, y en una ventana maximizada
        salen fácilmente el doble.

        **No se toca el texto.**  Lo que se estrecha es el control, dejando
        márgenes a los lados, así que el ajuste de línea lo sigue haciendo
        Windows y **ninguna posición cambia**: las marcas, los marcadores, la
        posición de lectura y la navegación siguen apuntando exactamente a
        donde apuntaban.  Escribir saltos de línea en el texto para acortarlo
        habría sido más sencillo y habría movido todas las posiciones del
        libro, que es justo lo que no puede pasar.

        Con el ajuste de línea apagado no se hace nada: ahí cada párrafo es una
        línea y se desplaza a lo ancho, que es lo que se ha pedido.
        """
        elemento = self._contenedor.GetItem(self.texto) if self._contenedor else None
        if elemento is None:
            return
        margen = self._margen_de_ancho()
        if elemento.GetBorder() == margen:
            return
        elemento.SetBorder(margen)
        elemento.SetFlag(wx.EXPAND | wx.LEFT | wx.RIGHT)
        self.Layout()

    def _margen_de_ancho(self) -> int:
        """Cuántos píxeles hay que dejar a cada lado del texto.

        El ancho se pide en **caracteres**, que es como se piensa en esto y lo
        único que no depende del tamaño de la letra ni de la pantalla.  Se
        traduce a píxeles midiendo el ancho de un carácter con la fuente que
        esté puesta.
        """
        try:
            columnas = int(self.configuracion.obtener("ancho_maximo_linea", 0) or 0)
        except (TypeError, ValueError):
            columnas = 0
        if columnas <= 0 or not self.configuracion.obtener("ajuste_de_linea"):
            return 0
        disponible = self.GetClientSize().width
        if disponible <= 0:
            return 0
        try:
            ancho_caracter = self.texto.GetTextExtent("0123456789")[0] / 10.0
        except Exception:
            ancho_caracter = 0.0
        if ancho_caracter <= 0:
            return 0
        # Se suma un poco de aire para la barra de desplazamiento y el marco
        # del control: sin ese margen, la última letra de cada renglón se
        # quedaría justo debajo de la barra.
        deseado = int(columnas * ancho_caracter) + 32
        if deseado >= disponible:
            return 0
        return max(0, (disponible - deseado) // 2)

    def admitir_soltar_archivos(self, fabrica: Callable[[], wx.DropTarget]) -> None:
        """Permite abrir libros arrastrándolos sobre el texto.

        :param fabrica: Función que crea un destino de arrastre nuevo cada vez
                        que se le pide, porque wxWidgets destruye el anterior
                        junto con el control al que estaba asociado.
        """
        self._fabrica_soltar = fabrica
        self.texto.SetDropTarget(fabrica())

    def _aplicar_apariencia(self, control: wx.TextCtrl) -> None:
        """Aplica fuente y colores elegidos por el usuario."""
        nombre = self.configuracion.obtener("fuente_nombre") or ""
        tamano = int(self.configuracion.obtener("fuente_tamano") or 11)
        fuente = wx.Font(wx.FontInfo(tamano).FaceName(nombre) if nombre else wx.FontInfo(tamano))
        control.SetFont(fuente)
        color_texto = self.configuracion.obtener("color_texto") or ""
        color_fondo = self.configuracion.obtener("color_fondo") or ""
        if color_fondo:
            control.SetBackgroundColour(wx.Colour(color_fondo))
        else:
            control.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW))
        if color_texto:
            control.SetForegroundColour(wx.Colour(color_texto))
        else:
            control.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT))
        # El estilo por omisión debe repetir fuente y colores: en el control
        # enriquecido de Windows, SetFont por sí solo no afecta al texto ya
        # escrito ni al que se escriba después.
        atributos = wx.TextAttr()
        atributos.SetFont(fuente)
        if color_texto:
            atributos.SetTextColour(wx.Colour(color_texto))
        if color_fondo:
            atributos.SetBackgroundColour(wx.Colour(color_fondo))
        control.SetDefaultStyle(atributos)

    def refrescar_apariencia(self) -> None:
        """Vuelve a aplicar fuente, colores y ancho tras cambiarlos en Opciones."""
        posicion = self.posicion()
        self._aplicar_apariencia(self.texto)
        # El ancho se pide en caracteres, así que cambiar el tamaño de la letra
        # cambia cuántos píxeles ocupan.
        self.ajustar_ancho()
        if self.documento is not None:
            self._cargar_ventana(posicion, forzar=True)
            self.ir_a(posicion, mover_foco=False)
        self.texto.Refresh()

    def alternar_ajuste_de_linea(self) -> bool:
        """Invierte el ajuste de línea y lo aplica a este panel.

        Cambia el ajuste **una vez** y lo aplica aquí.  Quien tenga más paneles
        abiertos debe aplicarles el cambio con :meth:`aplicar_ajuste_de_linea`,
        que no vuelve a invertirlo: llamar a este método una vez por panel
        invertía el ajuste tantas veces como paneles hubiera y lo dejaba como
        estaba, que es justo lo que hacía que la casilla de las opciones
        apareciera siempre desmarcada por mucho que se marcara.

        :return: El nuevo estado del ajuste de línea.
        """
        nuevo = not bool(self.configuracion.obtener("ajuste_de_linea"))
        self.configuracion.establecer("ajuste_de_linea", nuevo)
        # Este panel es el que está delante y acaba de perder su control, que
        # se ha destruido para rehacerlo: el foco tiene que volver a él.
        self.aplicar_ajuste_de_linea(mover_foco=True)
        return nuevo

    def aplicar_ajuste_de_linea(self, mover_foco: bool = False) -> None:
        """Rehace el control con el ajuste de línea que digan las preferencias.

        El ajuste de línea no se puede cambiar en caliente en Windows: hay que
        crear el control otra vez con el estilo nuevo y volver a colocar el
        texto donde estaba.

        :param mover_foco: Si el control rehecho debe quedarse con el foco.
                           **Va apagado por omisión y es importante que lo
                           esté**: este método se aplica también a los
                           documentos que están detrás, y llevarles el foco
                           hace que el teclado acabe escribiendo en un
                           documento que no se ve, mientras el título de la
                           ventana sigue diciendo el que sí.  Solo lo pide el
                           panel que está delante, que es el único que tenía el
                           foco antes de rehacerse.
        """
        posicion = self.posicion()
        anterior = self.texto
        self._contenedor.Detach(anterior)
        anterior.Destroy()
        self.texto = self._crear_control()
        self._contenedor.Add(self.texto, 1, wx.EXPAND)
        self.ajustar_ancho()
        self.Layout()
        if self.documento is not None:
            self._cargar_ventana(posicion, forzar=True)
            self.ir_a(posicion, mover_foco=mover_foco)

    def aplicar_renglones(self, mover_foco: bool = False) -> None:
        """Vuelve a enseñar el texto con el partido en renglones que toque.

        No hay que rehacer el control —esto no es un estilo de ventana, como el
        ajuste de línea, sino el texto que se le da—: basta con volver a cargar
        el tramo y dejar el cursor donde estaba.  Y donde estaba es la misma
        posición de siempre, porque partir en renglones no mueve ninguna.

        :param mover_foco: Si el control debe quedarse con el foco.  Solo lo
                           pide el panel que está delante; véase
                           :meth:`aplicar_ajuste_de_linea`.
        """
        if self.documento is None:
            return
        posicion = self.posicion()
        self._cargar_ventana(posicion, forzar=True)
        self.ir_a(posicion, mover_foco=mover_foco)

    # -- carga del documento -------------------------------------------------

    def cargar_documento(self, documento: Documento, posicion: int = 0) -> None:
        """Muestra un libro y coloca el cursor en una posición.

        :param documento: Libro ya analizado.
        :param posicion: Posición absoluta donde empezar a leer.
        """
        self.documento = documento
        self._historial = [posicion]
        self._indice_historial = 0
        self._ultima_linea = -1
        self._ultima_posicion = -1
        with cronometro(log, "carga del texto en el control") as datos:
            self._cargar_ventana(posicion, forzar=True)
            datos["ventana"] = "%d-%d" % (self._inicio_ventana, self._fin_ventana)
        self.ir_a(posicion)
        self._vigilante.Start(INTERVALO_VIGILANCIA)

    def cerrar_documento(self) -> None:
        """Descarga el libro actual y vuelve a mostrar la presentación."""
        self._vigilante.Stop()
        if self._formateo_pendiente is not None and self._formateo_pendiente.IsRunning():
            self._formateo_pendiente.Stop()
        self.documento = None
        self._inicio_ventana = self._fin_ventana = 0
        self._mapa = MapaUtf16("")
        self.mostrar_presentacion()

    def mostrar_presentacion(self) -> None:
        """Muestra en el control el resumen de lo que se puede hacer.

        Se usa mientras no hay ningún libro abierto.  Al ser texto corriente
        dentro del mismo control de lectura, se recorre con las flechas y con
        las órdenes de lectura del lector de pantalla igual que un libro.

        Quien ya se lo sabe puede apagarlo en las opciones, y entonces sale la
        presentación breve: el resumen es lo que hace falta el primer día y lo
        que sobra el día doscientos, cuando lo único que se quiere es abrir un
        libro y en medio hay una pantalla de teclas por la que pasar.

        Si lo que ya hay puesto es exactamente esto, no se toca nada.  Volver a
        escribirlo devolvería el cursor al principio, y esto se llama también al
        aceptar las opciones: quien estaba leyendo la presentación por la mitad
        se encontraría de vuelta arriba por haber cambiado cualquier ajuste.
        """
        nuevo = (texto_de_bienvenida(self.version)
                 if self.configuracion.obtener("mostrar_bienvenida", True)
                 else texto_breve(self.version))
        if self.texto.GetValue() == nuevo:
            return
        self._cargando = True
        try:
            self.texto.ChangeValue(nuevo)
            self.texto.SetInsertionPoint(0)
        finally:
            self._cargando = False

    # -- ventana deslizante --------------------------------------------------

    def _limites_ventana(self, centro: int) -> tuple[int, int]:
        """Calcula el tramo que hay que cargar para contener una posición.

        La ventana se mantiene siempre del mismo tamaño y se desplaza hacia
        dentro cerca de los extremos del libro, en vez de encogerse.  Así, al
        saltar al final con Control+Fin, el cursor no queda pegado a un borde
        que provocaría otra recarga en el primer movimiento.
        """
        assert self.documento is not None
        total = len(self.documento)
        if total <= UMBRAL_COMPLETO:
            return 0, total
        mitad = TAMANO_VENTANA // 2
        fin = min(centro + mitad, total)
        fin = max(fin, min(TAMANO_VENTANA, total))
        inicio = max(fin - TAMANO_VENTANA, 0)
        return inicio, fin

    def _cargar_ventana(self, centro: int, forzar: bool = False) -> None:
        """Carga en el control el tramo de texto que rodea a una posición."""
        documento = self.documento
        if documento is None:
            return
        inicio, fin = self._limites_ventana(centro)
        if not forzar and inicio == self._inicio_ventana and fin == self._fin_ventana:
            return
        # Se ajustan los bordes a principio de línea para no partir párrafos.
        inicio = documento.inicio_de_linea(documento.linea_de(inicio))
        if fin < len(documento):
            fin = documento.inicio_de_linea(documento.linea_de(fin) + 1)
        fragmento = documento.texto[inicio:fin]
        visible = self._para_el_control(fragmento)
        self._cargando = True
        try:
            self.texto.ChangeValue(visible)
        finally:
            self._cargando = False
        self._inicio_ventana = inicio
        self._fin_ventana = inicio + len(fragmento)
        self._mapa = MapaUtf16(visible)
        # Al recargar la ventana de texto, el resalte anterior apuntaba a
        # posiciones de un fragmento que ya no está: se olvida sin más.
        self._resalte = None
        self._rango_formateado = (0, 0)
        log.debug("Ventana cargada: %d-%d (%d caracteres)", inicio, self._fin_ventana, len(fragmento))

    def _para_el_control(self, fragmento: str) -> str:
        """Adapta el texto del libro a como se va a enseñar en el control.

        Hoy hace una sola cosa: si está puesto «cada frase en un renglón»,
        cambia por un salto de línea el espacio que separa una frase de la
        siguiente.

        Es un **cambio** y no una inserción a propósito, y de eso depende todo
        lo demás: el texto que ve el control mide exactamente lo mismo que el
        del libro, así que ninguna posición se mueve y los marcadores, las
        notas, los resaltados y por dónde ibas siguen apuntando al mismo
        carácter.  Por eso esto puede quedarse aquí dentro sin que el resto del
        programa se entere de nada.
        """
        if not self.configuracion.obtener("renglon_por_frase", False):
            return fragmento
        with cronometro(log, "partido en renglones") as datos:
            partido = partir_en_renglones(fragmento)
            datos["caracteres"] = len(fragmento)
        return partido

    def _necesita_recarga(self, posicion: int) -> bool:
        """Indica si hay que mover la ventana para alcanzar una posición."""
        if self.documento is None:
            return False
        if posicion < self._inicio_ventana or posicion > self._fin_ventana:
            return True
        total = len(self.documento)
        cerca_del_inicio = self._inicio_ventana > 0 and posicion - self._inicio_ventana < MARGEN_RECARGA
        cerca_del_fin = self._fin_ventana < total and self._fin_ventana - posicion < MARGEN_RECARGA
        return cerca_del_inicio or cerca_del_fin

    def _aplicar_formato(self, inicio: int, fin: int) -> None:
        """Marca en negrita y cursiva los tramos comprendidos en un rango.

        Aplicar un estilo al control de texto de Windows obliga a rehacer la
        disposición de todo lo que hay debajo, y con el ajuste de línea activo
        cuesta unos tres milisegundos por tramo.  En un libro con miles de
        cursivas eso significaría varios segundos por cada salto.

        Por eso el formato **no** se aplica a toda la ventana cargada, sino
        solo al entorno del cursor (véase :meth:`_formatear_alrededor`), que es
        lo único que el lector puede estar viendo.
        """
        documento = self.documento
        if documento is None or not self.configuracion.obtener("mostrar_formato", True):
            return
        tramos = documento.marcas.formato_en_rango(inicio, fin, MAXIMO_TRAMOS_FORMATO)
        if tramos is None:
            log.debug("Se omite el formato: más de %d tramos en el rango", MAXIMO_TRAMOS_FORMATO)
            return
        if not tramos:
            return
        base = self.texto.GetFont()
        estilos = {
            TipoMarca.NEGRITA: base.Bold(),
            TipoMarca.CURSIVA: base.Italic(),
            TipoMarca.SUBRAYADO: base.Underlined(),
        }
        self.texto.Freeze()
        try:
            for marca in tramos:
                fuente = estilos.get(marca.tipo)
                if fuente is None:
                    continue
                desde = self._mapa.a_control(
                    max(marca.posicion, inicio) - self._inicio_ventana)
                hasta = self._mapa.a_control(
                    min(marca.posicion + marca.longitud, fin) - self._inicio_ventana)
                if hasta > desde:
                    self.texto.SetStyle(desde, hasta,
                                        wx.TextAttr(wx.NullColour, wx.NullColour, fuente))
        finally:
            self.texto.Thaw()

    def _formatear_mas_tarde(self) -> None:
        """Aplaza el formato hasta que el cursor lleve un momento quieto.

        Mientras se lee, el cursor se mueve, y cada movimiento pasaba por aquí:
        el estilo se aplicaba **justo por donde el lector de pantalla estaba
        leyendo**.  Cada aviso nuevo cancela el anterior, así que recorrer un
        capítulo entero con las flechas ya no aplica formato ni una sola vez:
        se aplica al parar.
        """
        if self._formateo_pendiente is not None and self._formateo_pendiente.IsRunning():
            self._formateo_pendiente.Stop()
        self._formateo_pendiente = wx.CallLater(RETARDO_FORMATO, self._formatear_al_parar)

    def _formatear_al_parar(self) -> None:
        """Aplica el formato aplazado, si el panel sigue existiendo."""
        try:
            if self.documento is None or self._cargando:
                return
            self._formatear_alrededor(self.posicion())
        except RuntimeError:
            pass          # el panel se ha destruido mientras se esperaba

    def _formatear_alrededor(self, posicion: int, tras_salto: bool = False) -> None:
        """Aplica el formato al entorno del cursor si aún no se había aplicado.

        Se avanza a saltos de :data:`RADIO_FORMATO` caracteres y se recuerda
        el tramo ya tratado, de modo que leer seguido no vuelve a aplicar
        estilos sobre el mismo texto.

        **Leyendo no se vuelve a dar estilo al párrafo donde está el cursor**,
        y eso es lo importante.  Una negrita o una cursiva ocupan más ancho que
        la letra normal, así que aplicarlas cambia por dónde se parte el
        párrafo en renglones; y si eso pasa en el párrafo que se está leyendo,
        los renglones dejan de estar donde estaban: la flecha abajo repite lo
        que se acababa de oír, o se salta un trozo.  Solo se notaba con el
        ajuste de línea activado, que es cuando hay renglones que mover.

        Con el cursor fuera del tramo que se retoca no hay nada que descolocar:
        cada párrafo se parte en renglones por su cuenta, así que otro párrafo
        puede cambiar de anchura cuantas veces quiera.

        :param tras_salto: Verdadero cuando se acaba de llegar de un salto.
                           Entonces sí se formatea también el párrafo del
                           cursor: el lector de pantalla va a leer esa línea de
                           nuevo de todas formas, así que no hay ninguna
                           lectura seguida a la que descolocar.
        """
        if self._formateo_pendiente is not None and self._formateo_pendiente.IsRunning():
            self._formateo_pendiente.Stop()
        if self.documento is None or not self.configuracion.obtener("mostrar_formato", True):
            return
        ya_inicio, ya_fin = self._rango_formateado
        if ya_inicio <= posicion - RADIO_FORMATO // 2 and \
                posicion + RADIO_FORMATO // 2 <= ya_fin:
            return
        inicio = max(posicion - RADIO_FORMATO, self._inicio_ventana)
        fin = min(posicion + RADIO_FORMATO, self._fin_ventana)
        # Sin nada formateado todavía, habiendo llegado de un salto, o habiendo
        # aparecido el cursor fuera del tramo ya tratado —un clic, la barra de
        # desplazamiento—, se formatea el entorno entero de una vez: en ninguno
        # de los tres casos hay una lectura seguida en marcha.
        if tras_salto or ya_fin <= ya_inicio or not ya_inicio <= posicion <= ya_fin:
            self._aplicar_formato(inicio, fin)
            self._rango_formateado = (inicio, fin)
            return
        linea = self.documento.linea_de(posicion)
        nuevo_inicio, nuevo_fin = ya_inicio, ya_fin
        if fin > ya_fin:
            desde = max(ya_fin, self.documento.fin_de_linea(linea))
            if fin > desde:
                self._aplicar_formato(desde, fin)
                nuevo_fin = fin
        if inicio < ya_inicio:
            hasta = min(ya_inicio, self.documento.inicio_de_linea(linea))
            if hasta > inicio:
                self._aplicar_formato(inicio, hasta)
                nuevo_inicio = inicio
        self._rango_formateado = (nuevo_inicio, nuevo_fin)

    # -- posiciones ----------------------------------------------------------

    def posicion(self) -> int:
        """Posición absoluta del cursor dentro del libro."""
        if self.documento is None:
            return 0
        return self._inicio_ventana + self._mapa.desde_control(self.texto.GetInsertionPoint())

    def seleccion(self) -> tuple[int, int]:
        """Selección actual como posiciones absolutas del libro."""
        if self.documento is None:
            return 0, 0
        desde, hasta = self.texto.GetSelection()
        return (self._inicio_ventana + self._mapa.desde_control(desde),
                self._inicio_ventana + self._mapa.desde_control(hasta))

    def texto_seleccionado(self) -> str:
        """Texto seleccionado, tal y como está escrito en el libro.

        Se devuelve el del **documento** y no el del control porque no tienen
        por qué ser iguales: con «cada frase en un renglón», donde el libro
        tiene un espacio el control enseña un salto de línea.  Lo que se copia,
        se cita, se busca en el diccionario o se le manda a la inteligencia
        artificial tiene que ser el texto del libro.
        """
        if self.documento is None:
            return self.texto.GetStringSelection()
        inicio, fin = self.seleccion()
        return self.documento.texto[inicio:fin]

    def ir_a(self, posicion: int, mover_foco: bool = True, registrar: bool = False,
             lectura: bool = False) -> None:
        """Coloca el cursor en una posición absoluta del libro.

        Es el único punto por el que pasan todos los saltos, de modo que la
        recarga de la ventana queda resuelta de una vez para toda la
        aplicación.

        :param posicion: Destino absoluto.
        :param mover_foco: Si el control de texto debe recibir el foco.
        :param registrar: Si el salto debe quedar en el historial de posiciones.
        :param lectura: Avance automático de la voz, en vez de navegación.
        """
        if self.documento is None:
            return
        posicion = max(0, min(posicion, len(self.documento)))
        if self._necesita_recarga(posicion):
            self._cargar_ventana(posicion)
        local = self._mapa.a_control(posicion - self._inicio_ventana)
        if mover_foco:
            self.texto.SetFocus()
        self.texto.SetInsertionPoint(local)
        self.texto.ShowPosition(local)
        if registrar:
            self.registrar_en_historial(posicion)
        self._formatear_alrededor(posicion, tras_salto=True)
        self._ultima_posicion = posicion
        self._ultima_linea = self.documento.linea_de(posicion)
        self._notificar_movimiento(posicion, salto=not lectura)

    def resaltar_frase(self, inicio: int, fin: int) -> None:
        """Marca con un fondo de color la frase que se está leyendo.

        **No mueve el cursor ni el foco**, a propósito: quien lee de oído tiene
        el cursor donde lo dejó y moverlo haría que el lector de pantalla se
        pusiera a hablar encima de la voz.  Esto es para quien conserva resto
        visual y quiere seguir con la vista lo que se está oyendo.

        Se pinta el fondo y se despinta el de la frase anterior; si el tramo
        cae fuera de la ventana de texto cargada, simplemente no se pinta nada:
        el cursor no se mueve, así que la ventana tampoco se recarga.
        """
        self._quitar_resalte()
        if self.documento is None:
            return
        if not (self._inicio_ventana <= inicio < self._fin_ventana):
            return
        desde = self._mapa.a_control(max(inicio - self._inicio_ventana, 0))
        hasta = self._mapa.a_control(
            max(min(fin, self._fin_ventana) - self._inicio_ventana, 0))
        if hasta <= desde:
            return
        fondo = wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT)
        letra = wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHTTEXT)
        self.texto.SetStyle(desde, hasta, wx.TextAttr(letra, fondo))
        self._resalte = (desde, hasta)

    def _quitar_resalte(self) -> None:
        """Devuelve a sus colores el tramo resaltado, si lo había."""
        if self._resalte is None:
            return
        desde, hasta = self._resalte
        self._resalte = None
        largo = self.texto.GetLastPosition()
        if desde >= largo:
            return
        letra, fondo = self._colores_actuales()
        try:
            self.texto.SetStyle(desde, min(hasta, largo), wx.TextAttr(letra, fondo))
        except Exception:
            pass

    def _colores_actuales(self):
        """Los colores normales del texto, sean los del sistema o los elegidos."""
        propio_letra = str(self.configuracion.obtener("color_texto", "") or "")
        propio_fondo = str(self.configuracion.obtener("color_fondo", "") or "")
        letra = wx.Colour(propio_letra) if propio_letra else self.texto.GetForegroundColour()
        fondo = wx.Colour(propio_fondo) if propio_fondo else self.texto.GetBackgroundColour()
        return letra, fondo

    def seleccionar(self, inicio: int, fin: int) -> None:
        """Selecciona un tramo del libro (por ejemplo, un resultado de búsqueda)."""
        if self.documento is None:
            return
        if self._necesita_recarga(inicio):
            self._cargar_ventana(inicio)
        desde = self._mapa.a_control(max(inicio - self._inicio_ventana, 0))
        hasta = self._mapa.a_control(max(min(fin, self._fin_ventana) - self._inicio_ventana, 0))
        self.texto.SetFocus()
        self.texto.SetSelection(desde, hasta)
        self.texto.ShowPosition(desde)
        self._ultima_posicion = inicio
        self._ultima_linea = self.documento.linea_de(inicio)
        self._notificar_movimiento(inicio, salto=True)

    # -- historial de posiciones ---------------------------------------------

    def registrar_en_historial(self, posicion: int) -> None:
        """Anota un salto en el historial de navegación.

        Solo se registran los saltos «grandes» (más de una pantalla), para que
        el historial recoja los movimientos deliberados y no cada pulsación de
        flecha abajo.
        """
        if self._historial and abs(self._historial[self._indice_historial] - posicion) < 200:
            return
        del self._historial[self._indice_historial + 1:]
        self._historial.append(posicion)
        if len(self._historial) > 100:
            self._historial.pop(0)
        self._indice_historial = len(self._historial) - 1

    def retroceder(self) -> bool:
        """Vuelve a la posición anterior del historial."""
        if self._indice_historial <= 0:
            return False
        self._indice_historial -= 1
        self.ir_a(self._historial[self._indice_historial])
        return True

    def avanzar(self) -> bool:
        """Avanza a la siguiente posición del historial."""
        if self._indice_historial >= len(self._historial) - 1:
            return False
        self._indice_historial += 1
        self.ir_a(self._historial[self._indice_historial])
        return True

    def historial(self) -> tuple[list[int], int]:
        """Devuelve el historial y la posición actual dentro de él."""
        return list(self._historial), self._indice_historial

    def restaurar_historial(self, posiciones: list[int], indice: int) -> None:
        """Restaura un historial guardado de una sesión anterior."""
        if posiciones:
            self._historial = list(posiciones)
            self._indice_historial = max(0, min(indice, len(posiciones) - 1))

    # -- vigilancia del cursor -----------------------------------------------

    def _al_vigilar(self, evento: wx.TimerEvent) -> None:
        """Comprueba periódicamente si el cursor ha cambiado de sitio.

        wxWidgets no avisa cuando el cursor se mueve dentro de un control de
        texto, así que se consulta cada pocas centésimas.  El coste es
        insignificante y permite reaccionar igual al teclado, al ratón y a la
        barra de desplazamiento.
        """
        if self.documento is None or self._cargando:
            return
        # Una pestaña de fondo no se mueve sola: no hace falta preguntarle al
        # control cada pocas centésimas por un cursor que nadie está moviendo.
        if not self.IsShown():
            return
        posicion = self.posicion()
        if posicion == self._ultima_posicion:
            return
        # Las teclas propias del control (flechas, Av Pág, Control+Fin, la
        # barra de desplazamiento) solo conocen el tramo cargado: al llegar a
        # su borde el cursor se quedaría bloqueado sin poder seguir avanzando
        # por el libro.  Aquí se detecta esa aproximación al borde y se vuelve
        # a centrar el tramo, de modo que la lectura continúa sin cortes.
        if self._necesita_recarga(posicion):
            posicion = self._recentrar(posicion)
        self._ultima_posicion = posicion
        self._formatear_mas_tarde()
        linea = self.documento.linea_de(posicion)
        if linea != self._ultima_linea:
            self._ultima_linea = linea
            self._sonar_por_linea(posicion)
        self._notificar_movimiento(posicion)

    def _recentrar(self, posicion: int) -> int:
        """Vuelve a cargar el tramo dejando el cursor en su centro.

        Se llama cuando el cursor, movido por el propio control, se acerca a
        un borde del tramo cargado.  Devuelve la posición del cursor después
        de la recarga, que es la misma en la que estaba.

        Si hay una selección activa no se hace nada: recargar la borraría, y
        una selección no puede abarcar más que el tramo cargado de todas
        formas.
        """
        desde, hasta = self.texto.GetSelection()
        if desde != hasta:
            return posicion
        anterior = (self._inicio_ventana, self._fin_ventana)
        self._cargar_ventana(posicion)
        if (self._inicio_ventana, self._fin_ventana) == anterior:
            return posicion  # no había margen para moverse
        local = self._mapa.a_control(posicion - self._inicio_ventana)
        self.texto.SetInsertionPoint(local)
        self.texto.ShowPosition(local)
        log.debug("Tramo recentrado alrededor de la posición %d", posicion)
        return posicion

    def _sonar_por_linea(self, posicion: int) -> None:
        """Avisa de los elementos que hay en la línea a la que se ha llegado.

        Se puede avisar con un **pitido**, con la **voz**, con los dos o con
        ninguno (``avisar_elementos`` en las preferencias).  El pitido es lo de
        siempre y es lo más rápido de interpretar cuando ya se conoce, pero
        tiene un límite: solo puede sonar uno por línea, así que en una línea
        que lleva un salto de página y una llamada de nota suena el salto de
        página y la nota se queda sin señalar.  Dicha, se oyen las dos, que es
        justo lo que hacía falta en los libros muy anotados.
        """
        if self.documento is None:
            return
        modo = str(self.configuracion.obtener("avisar_elementos", "sonido") or "sonido")
        if modo == "ninguno":
            return
        if self.configuracion.obtener("sonidos_solo_al_navegar"):
            return
        elementos = elementos_en_linea(self.documento, posicion)
        if not elementos:
            return
        if modo in ("sonido", "ambos") and self.configuracion.obtener("sonidos_activados"):
            self.sonidos.reproducir_para_elementos(elementos)
        if modo in ("voz", "ambos"):
            self._decir_elementos(elementos)

    def _decir_elementos(self, elementos) -> None:
        """Dice en voz alta qué elementos hay en la línea.

        Se dice **sin retardo y sin interrumpir**: el lector de pantalla está a
        punto de leer la línea a la que se ha llegado, y lo que se quiere es
        que el aviso vaya delante y no que corte la lectura por la mitad.
        """
        from nucleo.marcas import nombrar

        if self.anunciador is None:
            return
        nombres = nombrar(marca.tipo for marca in elementos)
        if nombres:
            self.anunciador.anunciar(nombres, interrumpir=False, retardo=0)

    def _notificar_movimiento(self, posicion: int, salto: bool = False) -> None:
        """Avisa a la ventana principal de que el cursor se ha movido."""
        if self._al_moverse is not None:
            try:
                self._al_moverse(posicion, salto=salto)
            except Exception:
                log.exception("Error al notificar el movimiento del cursor")

    # -- menú contextual -----------------------------------------------------

    def _al_menu_contextual(self, evento: wx.ContextMenuEvent) -> None:
        """Descarta la petición de menú contextual sobre el texto.

        El menú que ofrece por su cuenta el control de Windows («Copiar»,
        «Seleccionar todo», «Deshacer»...) no aporta nada aquí y confunde,
        porque la mayoría de sus opciones no tienen sentido en un texto de
        solo lectura.  Al no propagar el evento, ese menú no llega a
        mostrarse.

        Queda pendiente sustituirlo por un menú que dependa de dónde esté el
        cursor: seguir el enlace si está sobre un enlace, ver la imagen si
        está sobre una imagen, mostrar la tabla si está dentro de una tabla.
        Ese menú se construirá aquí mismo cuando se aborde.
        """
        log.debug("Petición de menú contextual descartada")

    def _al_boton_derecho(self, evento: wx.MouseEvent) -> None:
        """Consume el botón derecho para que no se genere el menú del sistema.

        No se llama a ``Skip()`` a propósito: en Windows el menú contextual
        solo se genera si el evento del botón derecho queda sin atender.
        """
        log.debug("Botón derecho consumido en el texto del libro")

    # -- utilidades ----------------------------------------------------------

    def linea_actual(self) -> str:
        """Texto de la línea donde está el cursor."""
        if self.documento is None:
            return ""
        return self.documento.texto_de_linea(self.posicion())

    def copiar(self) -> None:
        """Copia al portapapeles la selección, con el texto tal cual está en el libro."""
        if self.documento is None:
            if self.texto.CanCopy():
                self.texto.Copy()
            return
        seleccionado = self.texto_seleccionado()
        if not seleccionado:
            return
        if wx.TheClipboard.Open():
            try:
                wx.TheClipboard.SetData(wx.TextDataObject(seleccionado))
            finally:
                wx.TheClipboard.Close()
