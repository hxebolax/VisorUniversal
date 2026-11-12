# -*- coding: utf-8 -*-
"""Listas de varias columnas que se pueden recorrer con las flechas.

Un ``wx.ListCtrl`` en modo informe muestra una rejilla de filas y columnas,
pero el teclado solo permite moverse de fila en fila: al bajar, el lector de
pantalla lee la fila entera y no hay forma de volver sobre una columna
concreta.  En una lista con una columna de texto largo —una nota, el
contenido de una celda— eso obliga a oír todo lo demás cada vez.

:class:`ListaAccesible` añade un **cursor de columna**:

* ``Flecha izquierda`` y ``Flecha derecha`` lo mueven y dicen la celda;
* ``Control+1`` a ``Control+9`` saltan directamente a una columna;
* ``Inicio`` y ``Fin``, con Control, van a la primera y a la última columna.

El cursor de columna es propio de la aplicación: no cambia la selección ni el
foco, de modo que el lector de pantalla no dice nada por su cuenta y no hay
doble lectura.  Lo que se anuncia de cada celda es configurable desde
**Opciones → Accesibilidad**.

La clase guarda además el texto **íntegro** de cada celda.  Windows recorta a
unos 511 caracteres el texto que se le pasa a un ``wx.ListCtrl``, así que
``GetItemText`` no sirve para leer en voz alta una nota larga; el texto real
se conserva aquí.
"""

from __future__ import annotations

import wx

from interfaz.anuncios import Voz
from nucleo.idioma import _
from nucleo.registro import obtener_registro

log = obtener_registro(__name__)
#: Lo que se anuncia cuando la celda está vacía.  Callar dejaría al usuario
#: sin saber si la celda está en blanco o si la tecla no ha hecho nada.
CELDA_VACIA = _("en blanco")


class ListaAccesible(wx.ListCtrl):
    """Lista de varias columnas que se recorre también con izquierda y derecha.

    :param padre: Ventana donde se crea.
    :param configuracion: Preferencias de la aplicación, de donde salen los
                          ajustes de qué anunciar.  Si es ``None`` se usan los
                          valores por omisión.
    :param nombre: Nombre accesible de la lista.
    :param size: Tamaño inicial, como en cualquier control de wxPython.
    :param style: Estilos añadidos.  ``wx.LC_REPORT`` se pone siempre, porque
                  es el único modo con columnas.
    """

    def __init__(self, padre: wx.Window, configuracion=None, nombre: str = "Lista",
                 size=wx.DefaultSize, style: int = wx.LC_SINGLE_SEL) -> None:
        super().__init__(padre, size=size, style=style | wx.LC_REPORT, name=nombre)
        self.configuracion = configuracion
        #: Texto completo de cada celda: ``{fila: {columna: texto}}``.
        self._celdas: dict[int, dict[int, str]] = {}
        #: Columna sobre la que está el cursor de lectura.
        self.columna = 0
        self._voz = Voz(self)
        self.Bind(wx.EVT_KEY_DOWN, self._al_pulsar)

    # -- volcado de datos ----------------------------------------------------

    def InsertItem(self, *args, **kwargs):  # noqa: N802 (nombre de wxPython)
        """Inserta una fila y recuerda el texto íntegro de su primera celda."""
        indice = super().InsertItem(*args, **kwargs)
        if len(args) >= 2 and isinstance(args[0], int) and isinstance(args[1], str):
            self._celdas.setdefault(args[0], {})[0] = args[1]
        return indice

    def SetItem(self, *args, **kwargs):  # noqa: N802 (nombre de wxPython)
        """Fija el texto de una celda y recuerda su versión íntegra."""
        resultado = super().SetItem(*args, **kwargs)
        if (len(args) >= 3 and isinstance(args[0], int)
                and isinstance(args[1], int) and isinstance(args[2], str)):
            self._celdas.setdefault(args[0], {})[args[1]] = args[2]
        return resultado

    def DeleteAllItems(self):  # noqa: N802 (nombre de wxPython)
        """Vacía la lista y olvida el texto guardado."""
        self._celdas.clear()
        self.columna = 0
        return super().DeleteAllItems()

    def ClearAll(self):  # noqa: N802 (nombre de wxPython)
        """Quita filas y columnas, y olvida el texto guardado."""
        self._celdas.clear()
        self.columna = 0
        return super().ClearAll()

    def texto_completo(self, fila: int, columna: int) -> str:
        """Devuelve el texto íntegro de una celda, sin el recorte de Windows."""
        guardado = self._celdas.get(fila, {}).get(columna)
        if guardado is not None:
            return guardado
        return self.GetItemText(fila, columna)

    # -- lectura por columnas ------------------------------------------------

    def fila_actual(self) -> int:
        """Fila donde está el foco, o la seleccionada si no hay foco marcado."""
        fila = self.GetFocusedItem()
        if fila == wx.NOT_FOUND:
            fila = self.GetFirstSelected()
        return fila

    def _ajuste(self, clave: str) -> bool:
        """Consulta un ajuste de lectura, con ``True`` como valor por omisión."""
        if self.configuracion is None:
            return True
        return bool(self.configuracion.obtener(clave, True))

    def texto_de_celda(self, fila: int, columna: int) -> str:
        """Redacta lo que hay que decir de una celda, según las preferencias."""
        decir_fila = self._ajuste("columnas_decir_fila")
        decir_encabezado = self._ajuste("columnas_decir_encabezado")
        decir_contenido = self._ajuste("columnas_decir_contenido")
        if not (decir_fila or decir_encabezado or decir_contenido):
            decir_contenido = True
        partes: list[str] = []
        if decir_fila:
            partes.append(_("Fila %d de %d") % (fila + 1, self.GetItemCount()))
        if decir_encabezado and columna < self.GetColumnCount():
            partes.append(self.GetColumn(columna).GetText())
        if decir_contenido:
            partes.append(self.texto_completo(fila, columna).strip() or CELDA_VACIA)
        return ", ".join(parte for parte in partes if parte)

    def decir_celda(self, fila: int, columna: int) -> None:
        """Anuncia una celda al lector de pantalla."""
        self._voz.decir(self.texto_de_celda(fila, columna))

    def _mover_columna(self, destino: int) -> None:
        """Lleva el cursor de columna a otra columna y la lee.

        Si ya se está en el extremo, se vuelve a leer la misma celda en lugar
        de callar: así el usuario oye dónde está y entiende que no hay más.
        """
        fila = self.fila_actual()
        if fila == wx.NOT_FOUND:
            return
        self.columna = max(0, min(destino, self.GetColumnCount() - 1))
        self.decir_celda(fila, self.columna)

    def _al_pulsar(self, evento: wx.KeyEvent) -> None:
        """Interpreta las teclas de lectura por columnas."""
        codigo = evento.GetKeyCode()
        modificadores = evento.GetModifiers()
        combinacion = combinacion_de(evento)
        if combinacion:
            tecla_posicion, tecla_ir_a = self._teclas()
            if combinacion == tecla_posicion:
                self.decir_posicion()
                return
            if combinacion == tecla_ir_a:
                self.preguntar_ir_a()
                return
        if self.GetColumnCount() < 1 or self.GetItemCount() < 1:
            evento.Skip()
            return

        if modificadores == wx.MOD_NONE and codigo in (wx.WXK_LEFT, wx.WXK_RIGHT):
            self._mover_columna(self.columna + (1 if codigo == wx.WXK_RIGHT else -1))
            return
        if modificadores == wx.MOD_CONTROL and codigo in (wx.WXK_HOME, wx.WXK_END):
            self._mover_columna(0 if codigo == wx.WXK_HOME else self.GetColumnCount() - 1)
            return
        # Control+1 a Control+9: ir directamente a una columna por su número.
        if modificadores == wx.MOD_CONTROL and ord("1") <= codigo <= ord("9"):
            self._mover_columna(codigo - ord("1"))
            return
        evento.Skip()

    # -- dónde estoy e ir a ----------------------------------------------------

    def _teclas(self) -> tuple[str, str]:
        """Las combinaciones elegidas en Opciones: ``(dónde estoy, ir a)``."""
        if self.configuracion is None:
            from nucleo.configuracion import AJUSTES_POR_OMISION as fabrica

            return (str(fabrica.get("lista_tecla_posicion", "") or ""),
                    str(fabrica.get("lista_tecla_ir_a", "") or ""))
        return (str(self.configuracion.obtener("lista_tecla_posicion", "") or ""),
                str(self.configuracion.obtener("lista_tecla_ir_a", "") or ""))

    def esta_vacia(self) -> bool:
        """Si la lista no tiene nada de verdad.

        Las ventanas dejan una sola fila entre paréntesis —«(Ningún libro
        coincide)»— cuando no hay nada que enseñar; esa fila no cuenta.
        """
        cuantas = self.GetItemCount()
        if cuantas == 0:
            return True
        if cuantas == 1:
            texto = self.texto_completo(0, 0).strip()
            return texto.startswith("(") and texto.endswith(")")
        return False

    def decir_posicion(self) -> None:
        """Dice en qué elemento se está y de cuántos: «Libros: 1 de 2484»."""
        if self.esta_vacia():
            self._voz.decir(_("%s: la lista está vacía.") % self._nombre_corto())
            return
        fila = self.fila_actual()
        total = self.GetItemCount()
        if fila < 0:
            frase = _("%(nombre)s: ningún elemento elegido de %(total)d.") % {
                "nombre": self._nombre_corto(), "total": total}
        else:
            frase = _("%(nombre)s: %(fila)d de %(total)d.") % {
                "nombre": self._nombre_corto(), "fila": fila + 1, "total": total}
        seleccionadas = self.GetSelectedItemCount()
        if seleccionadas > 1:
            frase += " " + _("%d seleccionados.") % seleccionadas
        self._voz.decir(frase)

    def _nombre_corto(self) -> str:
        """El nombre de la lista, para encabezar lo que se dice de ella."""
        return self.GetName() or _("Lista")

    def preguntar_ir_a(self) -> None:
        """Pregunta a qué número de elemento ir y lleva allí el foco."""
        if self.esta_vacia():
            self._voz.decir(_("%s: la lista está vacía.") % self._nombre_corto())
            return
        total = self.GetItemCount()
        actual = max(0, self.fila_actual()) + 1
        with DialogoIrA(self, total, actual, self._nombre_corto()) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                self.SetFocus()
                return
            destino = dialogo.numero
        self.ir_a(destino - 1)
        self.SetFocus()

    def ir_a(self, fila: int) -> None:
        """Deja seleccionado y con el foco el elemento de esa fila."""
        total = self.GetItemCount()
        if total <= 0:
            return
        fila = max(0, min(int(fila), total - 1))
        if self.GetSelectedItemCount():
            self.SetItemState(-1, 0, wx.LIST_STATE_SELECTED)
        self.Select(fila)
        self.Focus(fila)
        self.EnsureVisible(fila)


#: Combinaciones que se pueden elegir en Opciones para «dónde estoy» e «ir a»
#: en las listas.  Son pocas a propósito: todas son libres dentro de una lista
#: (ni el lector de pantalla ni Windows las usan ahí) y no chocan con las letras
#: de acceso de las ventanas, que van con Alt.
TECLAS_DE_LISTA = (
    ("ctrl+i", "Control+I"),
    ("ctrl+g", "Control+G"),
    ("ctrl+j", "Control+J"),
    ("ctrl+p", "Control+P"),
    ("ctrl+shift+i", _("Control+Mayús+I")),
    ("ctrl+shift+g", _("Control+Mayús+G")),
    ("f2", "F2"),
    ("f4", "F4"),
    ("", _("Ninguna")),
)


def combinacion_de(evento: wx.KeyEvent) -> str:
    """La tecla pulsada escrita como en :data:`TECLAS_DE_LISTA` («ctrl+g»)."""
    codigo = evento.GetKeyCode()
    if wx.WXK_F1 <= codigo <= wx.WXK_F24:
        tecla = "f%d" % (codigo - wx.WXK_F1 + 1)
    elif ord("A") <= codigo <= ord("Z"):
        tecla = chr(codigo).lower()
    else:
        return ""
    modificadores = evento.GetModifiers()
    partes = []
    if modificadores & wx.MOD_CONTROL:
        partes.append("ctrl")
    if modificadores & wx.MOD_ALT:
        partes.append("alt")
    if modificadores & wx.MOD_SHIFT:
        partes.append("shift")
    return "+".join(partes + [tecla])


class DialogoIrA(wx.Dialog):
    """Pregunta a qué número de elemento de una lista ir.

    Solo deja escribir cifras, y al aceptar comprueba que el número está entre
    1 y el total: si no, lo dice y no cierra.  Las flechas arriba y abajo suben
    y bajan el número sin salirse del margen.
    """

    def __init__(self, padre: wx.Window, total: int, actual: int, nombre: str) -> None:
        super().__init__(padre, title=_("Ir al elemento"))
        self.total = int(total)
        self.numero = max(1, min(int(actual), self.total))
        self._voz = Voz(self)
        contenedor = wx.BoxSizer(wx.VERTICAL)
        rotulo = (_("&Número del elemento de «%(lista)s» (del 1 al %(total)d):")
                  % {"lista": nombre, "total": self.total})
        contenedor.Add(wx.StaticText(self, label=rotulo), 0,
                       wx.LEFT | wx.RIGHT | wx.TOP, 8)
        self.campo = wx.TextCtrl(self, value=str(self.numero), size=(160, -1),
                                 style=wx.TE_PROCESS_ENTER, name=rotulo.replace("&", ""))
        contenedor.Add(self.campo, 0, wx.ALL, 8)
        pie = wx.StdDialogButtonSizer()
        aceptar = wx.Button(self, wx.ID_OK, _("&Ir"))
        aceptar.SetDefault()
        pie.AddButton(aceptar)
        pie.AddButton(wx.Button(self, wx.ID_CANCEL, _("&Cancelar")))
        pie.Realize()
        contenedor.Add(pie, 0, wx.EXPAND | wx.ALL, 8)
        self.SetSizerAndFit(contenedor)
        self.CentreOnParent()
        self.campo.Bind(wx.EVT_CHAR, self._al_escribir)
        self.campo.Bind(wx.EVT_TEXT_ENTER, self._al_aceptar)
        self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)
        self.campo.SetFocus()
        self.campo.SelectAll()
        from interfaz.dialogos import ayuda_opcion

        ayuda_opcion.enganchar(self)

    def _al_escribir(self, evento: wx.KeyEvent) -> None:
        """Deja pasar cifras y teclas de edición; las flechas suben y bajan."""
        codigo = evento.GetKeyCode()
        if codigo in (wx.WXK_UP, wx.WXK_DOWN):
            numero = self._leido() or self.numero
            numero += 1 if codigo == wx.WXK_UP else -1
            numero = max(1, min(numero, self.total))
            self.campo.SetValue(str(numero))
            self.campo.SetInsertionPointEnd()
            self._voz.decir(str(numero))
            return
        caracter = evento.GetUnicodeKey()
        if (evento.ControlDown() or evento.AltDown() or caracter == wx.WXK_NONE
                or caracter < wx.WXK_SPACE or caracter == wx.WXK_DELETE
                or chr(caracter) in "0123456789"):
            evento.Skip()
            return
        # Cualquier otra cosa no se escribe: un número de elemento solo lleva
        # cifras.
        wx.Bell()

    def _leido(self) -> int:
        """El número escrito, o 0 si no hay un número."""
        texto = self.campo.GetValue().strip()
        return int(texto) if texto.isdigit() else 0

    def _al_aceptar(self, evento) -> None:
        """Acepta solo un número entre 1 y el total."""
        del evento
        numero = self._leido()
        if not 1 <= numero <= self.total:
            wx.Bell()
            self._voz.decir(_("Escribe un número del 1 al %d.") % self.total)
            self.campo.SetFocus()
            self.campo.SelectAll()
            return
        self.numero = numero
        self.EndModal(wx.ID_OK)


class ListaVirtual(ListaAccesible):
    """Lista de varias columnas que no guarda las filas: las pide al dibujarlas.

    Una ``wx.ListCtrl`` corriente guarda una copia de cada celda, y meterle
    ciento noventa mil filas de una en una son minutos con la ventana colgada.
    En modo virtual la lista solo sabe **cuántas** filas hay y, cuando Windows
    va a enseñar una o el lector de pantalla la pregunta, llama a
    :meth:`OnGetItemText`.  Cambiar de contenido es cambiar el número: es
    instantáneo tenga las filas que tenga.

    Para el lector de pantalla es la misma lista de siempre (la de Windows en
    modo «owner data», la que usa el propio Explorador), así que se recorre
    igual, se anuncia igual y escribir las primeras letras de un título sigue
    llevando a él.

    Admite selección múltiple; :kbd:`Control+E` selecciona todas las filas,
    como en el resto de listas del programa.
    """

    def __init__(self, padre: wx.Window, configuracion=None, nombre: str = "Lista",
                 size=wx.DefaultSize, multiple: bool = True) -> None:
        estilo = wx.LC_VIRTUAL | (0 if multiple else wx.LC_SINGLE_SEL)
        super().__init__(padre, configuracion, nombre, size=size, style=estilo)
        self._celda = lambda fila, columna: ""
        self._multiple = multiple

    def poner_filas(self, cuantas: int, celda) -> None:
        """Cambia el contenido: cuántas filas hay y cómo se saca cada celda.

        :param celda: Función ``(fila, columna) -> texto``.
        """
        self._celda = celda
        self.columna = 0
        self.SetItemCount(int(cuantas))
        self.Refresh()

    def OnGetItemText(self, fila, columna):  # noqa: N802 (lo pide wxPython)
        """Lo pide Windows al dibujar o al leer una fila."""
        try:
            return self._celda(fila, columna)
        except Exception:                                    # pragma: no cover
            return ""

    def texto_completo(self, fila: int, columna: int) -> str:
        """El texto de la celda, entero: se saca de los datos, no de Windows."""
        return self.OnGetItemText(fila, columna)

    def seleccionar_solo(self, fila: int) -> None:
        """Deja seleccionada y con el foco una sola fila."""
        if self.GetItemCount() <= 0:
            return
        fila = max(0, min(fila, self.GetItemCount() - 1))
        # De una vez y no fila a fila: con todo seleccionado serían ciento
        # noventa mil llamadas.
        if self.GetSelectedItemCount():
            self.SetItemState(-1, 0, wx.LIST_STATE_SELECTED)
        self.Select(fila)
        self.Focus(fila)
        self.EnsureVisible(fila)

    def seleccionar_todo(self) -> None:
        """Selecciona todas las filas y lo dice."""
        if not self._multiple or self.GetItemCount() <= 0:
            return
        self.SetItemState(-1, wx.LIST_STATE_SELECTED, wx.LIST_STATE_SELECTED)
        self._voz.decir(_("%d seleccionados.") % self.GetItemCount())

    def seleccionadas(self) -> list[int]:
        """Las filas seleccionadas, en orden."""
        filas = []
        fila = self.GetFirstSelected()
        while fila != -1:
            filas.append(fila)
            fila = self.GetNextSelected(fila)
        return filas

    def _al_pulsar(self, evento: wx.KeyEvent) -> None:
        """Control+E selecciona todo; lo demás, como en cualquier lista."""
        if (evento.GetModifiers() == wx.MOD_CONTROL
                and evento.GetKeyCode() in (ord("E"), ord("A"))):
            self.seleccionar_todo()
            return
        super()._al_pulsar(evento)


def rellenar_columnas(lista: ListaAccesible, encabezados: tuple[str, ...],
                      anchos: tuple[int, ...]) -> None:
    """Crea las columnas de una lista con sus títulos y sus anchos.

    Se hace aparte porque los títulos de las columnas son lo que se anuncia al
    recorrerlas: conviene que sean cortos y que digan de qué es cada columna.

    :param lista: Lista donde se crean.
    :param encabezados: Título de cada columna.
    :param anchos: Ancho de cada columna, en píxeles.
    """
    lista.ClearAll()
    for numero, titulo in enumerate(encabezados):
        ancho = anchos[numero] if numero < len(anchos) else wx.LIST_AUTOSIZE
        lista.InsertColumn(numero, titulo, width=ancho)


class _AccesibleCasillas(wx.Accessible):
    """Hace que una lista con casillas anuncie si cada elemento está marcado.

    ``wx.CheckListBox`` expone sus elementos como filas de lista corrientes, de
    modo que el lector de pantalla lee el texto pero **no dice si la casilla
    está marcada**, que es justo lo único que hay que saber.  Aquí cada
    elemento se declara casilla de verificación y se le añade el estado real.
    """

    def __init__(self, ventana: wx.Window) -> None:
        super().__init__(ventana)
        self._ventana = ventana

    def GetRole(self, childId):          # noqa: N802 (API de wxPython)
        """Cada elemento es una casilla, no una fila de lista."""
        if childId == 0:                 # el propio control
            return super().GetRole(childId)
        return (wx.ACC_OK, wx.ROLE_SYSTEM_CHECKBUTTON)

    def GetState(self, childId):         # noqa: N802 (API de wxPython)
        """Añade al estado si está marcado, seleccionado y con el foco."""
        if childId == 0:
            return super().GetState(childId)
        estados = wx.ACC_STATE_SYSTEM_SELECTABLE | wx.ACC_STATE_SYSTEM_FOCUSABLE
        try:
            if self._ventana.IsChecked(childId - 1):
                estados |= wx.ACC_STATE_SYSTEM_CHECKED
            if self._ventana.IsSelected(childId - 1):
                estados |= wx.ACC_STATE_SYSTEM_SELECTED
                if self._ventana.HasFocus():
                    estados |= wx.ACC_STATE_SYSTEM_FOCUSED
        except Exception:
            pass
        return (wx.ACC_OK, estados)


class ListaCasillas(wx.CheckListBox):
    """Lista de casillas que se puede manejar y entender de oído.

    Se usa donde hay que elegir **varias cosas de una lista**: qué borrar de un
    libro, qué idiomas instalar, qué sonidos activar.  Una casilla por línea es
    mucho más rápido de recorrer con el teclado que una hilera de controles
    sueltos, y con el estado bien anunciado no hay que mirar la pantalla para
    saber qué queda marcado.

    Aparte del objeto accesible, hace dos cosas más:

    * Avisa a Windows del cambio de estado (``EVENT_OBJECT_STATECHANGE``), que
      es lo que hace que el lector lo cante en el momento de pulsar espacio.
    * Lo dice además por su cuenta, por si el lector no recoge el aviso.
    * Control+E marca todo y Control+D lo desmarca, que con listas largas
      ahorra mucho.
    """

    def __init__(self, padre: wx.Window, nombre: str = "", **argumentos) -> None:
        super().__init__(padre, **argumentos)
        self._voz = Voz(self)
        if nombre:
            self.SetName(nombre)
        try:
            self.SetAccessible(_AccesibleCasillas(self))
        except Exception as error:
            log.debug("No se ha podido poner el accesible de las casillas: %s", error)
        self.Bind(wx.EVT_CHECKLISTBOX, self._al_marcar)
        self.Bind(wx.EVT_CHAR, self._al_pulsar_tecla)

    def _al_marcar(self, evento) -> None:
        """Anuncia el nuevo estado de la casilla que se acaba de cambiar."""
        evento.Skip()
        indice = evento.GetSelection()
        self._avisar_a_windows(indice)
        try:
            estado = _("marcado") if self.IsChecked(indice) else _("desmarcado")
            self._voz.decir("%s, %s" % (self.GetString(indice), estado))
        except Exception:
            pass

    def _avisar_a_windows(self, indice: int) -> None:
        """Le dice al sistema que ese elemento ha cambiado de estado.

        Sin este aviso el lector de pantalla no se entera del cambio hasta que
        el usuario vuelve a pasar por encima del elemento.
        """
        try:
            import ctypes

            EVENT_OBJECT_STATECHANGE = 0x800A
            OBJID_CLIENT = 0xFFFFFFFC
            ctypes.windll.user32.NotifyWinEvent(
                EVENT_OBJECT_STATECHANGE, int(self.GetHandle()), OBJID_CLIENT, indice + 1)
        except Exception:
            pass

    def _al_pulsar_tecla(self, evento: wx.KeyEvent) -> None:
        """Control+E marca todo; Control+D lo desmarca."""
        if evento.ControlDown() and not evento.AltDown():
            tecla = evento.GetKeyCode()
            if tecla in (5, ord("E"), ord("e")):        # Control+E
                self.marcar_todo(True)
                return
            if tecla in (4, ord("D"), ord("d")):        # Control+D
                self.marcar_todo(False)
                return
        evento.Skip()

    def marcar_todo(self, marcado: bool = True) -> None:
        """Marca o desmarca todos los elementos, y lo dice."""
        for indice in range(self.GetCount()):
            self.Check(indice, marcado)
            self._avisar_a_windows(indice)
        self._voz.decir(_("Todo marcado.") if marcado else _("Nada marcado."))

    def marcados(self) -> list[int]:
        """Índices de los elementos marcados."""
        return [indice for indice in range(self.GetCount()) if self.IsChecked(indice)]
