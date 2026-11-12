# -*- coding: utf-8 -*-
"""Gestor del diccionario de pronunciación.

Dos listas: las reglas **de este documento** —los nombres propios de esta saga—
y las **generales**, que valen para todos.  Se recorren y se editan igual, y en
las dos se puede probar una regla antes de guardarla, que es lo que evita tener
que cerrar, leer un párrafo, volver y corregir.

Las listas son de varias columnas y se recorren como todas las del programa:
arriba y abajo entre reglas, izquierda y derecha entre columnas.
"""

from __future__ import annotations

import wx

from interfaz.accesible import etiquetar, fila_etiquetada
from interfaz.anuncios import Voz
from interfaz.dialogos import ayuda_opcion
from interfaz.listas import ListaAccesible
from nucleo import pronunciacion
from nucleo.idioma import _
from nucleo.registro import obtener_registro
from nucleo.voz import Sintetizador

log = obtener_registro(__name__)

MARGEN = 8


class DialogoRegla(wx.Dialog):
    """Crea o modifica una regla.

    :param regla: La regla que se edita, o ``None`` para crear una nueva.
    :param sintetizador: Voz con la que probar cómo suena.
    """

    def __init__(self, padre: wx.Window, regla: pronunciacion.Regla | None,
                 sintetizador: Sintetizador) -> None:
        super().__init__(padre, title=_("Regla de pronunciación")
                         if regla is None else _("Modificar la regla"),
                         style=wx.DEFAULT_DIALOG_STYLE)
        self.sintetizador = sintetizador
        self.voz = Voz(self)
        original = regla or pronunciacion.Regla("", "")

        contenedor = wx.BoxSizer(wx.VERTICAL)
        self.buscar = fila_etiquetada(
            self, contenedor, _("Lo que está &escrito en el libro:"),
            lambda p: wx.TextCtrl(p, value=original.buscar),
            margen=MARGEN, horizontal=True, proporcion=1)
        self.decir = fila_etiquetada(
            self, contenedor, _("Cómo hay que &decirlo:"),
            lambda p: wx.TextCtrl(p, value=original.decir),
            margen=MARGEN, horizontal=True, proporcion=1)
        contenedor.Add(wx.StaticText(self, label=_(
            "Escríbelo tal y como suena: «Danerís» por «Daenerys». Si lo dejas vacío,\n"
            "eso no se dice: sirve para los adornos que el libro trae y estorban."
        )), 0, wx.ALL, MARGEN)

        self.completa = wx.CheckBox(self, label=_("Solo cuando sea la &palabra entera"))
        self.completa.SetValue(original.palabra_completa)
        contenedor.Add(self.completa, 0, wx.ALL, MARGEN)
        contenedor.Add(wx.StaticText(self, label=_(
            "Casi siempre conviene: sin esto, cambiar «Ana» por «Anna» convertiría\n"
            "«mañana» en «mañAnna»."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, MARGEN)

        self.mayusculas = wx.CheckBox(self, label=_("Distinguir &mayúsculas de minúsculas"))
        self.mayusculas.SetValue(original.distingue_mayusculas)
        contenedor.Add(self.mayusculas, 0, wx.ALL, MARGEN)

        botones = wx.BoxSizer(wx.HORIZONTAL)
        boton_probar = wx.Button(self, label=_("&Probar cómo suena"))
        boton_probar.Bind(wx.EVT_BUTTON, self._al_probar)
        botones.Add(boton_probar, 0, wx.ALL, 5)
        aceptar = wx.Button(self, wx.ID_OK, _("&Aceptar"))
        aceptar.SetDefault()
        botones.Add(aceptar, 0, wx.ALL, 5)
        botones.Add(wx.Button(self, wx.ID_CANCEL, _("&Cancelar")), 0, wx.ALL, 5)
        contenedor.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 4)

        self.SetSizerAndFit(contenedor)
        self.CenterOnParent()
        ayuda_opcion.enganchar(self)
        self.buscar.SetFocus()

    def _al_probar(self, evento) -> None:
        """Dice en voz alta cómo quedará la palabra."""
        dicho = self.decir.GetValue().strip()
        if not dicho:
            self.voz.decir(_("Con esta regla eso no se dice."))
            return
        if not self.sintetizador.disponible:
            self.voz.decir(_("Este equipo no tiene ninguna voz instalada."))
            return
        self.sintetizador.decir(dicho)

    def regla(self) -> pronunciacion.Regla:
        """Devuelve la regla tal y como ha quedado."""
        return pronunciacion.Regla(
            buscar=self.buscar.GetValue().strip(),
            decir=self.decir.GetValue().strip(),
            palabra_completa=self.completa.GetValue(),
            distingue_mayusculas=self.mayusculas.GetValue(),
        )


class DialogoPronunciacion(wx.Dialog):
    """Lista de reglas de pronunciación, del documento y generales.

    :param padre: Ventana principal.
    """

    def __init__(self, padre: wx.Window) -> None:
        super().__init__(padre, title=_("Diccionario de pronunciación"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.ventana = padre
        self.configuracion = padre.configuracion
        self.ruta = getattr(padre, "ruta_actual", "")
        self.sintetizador = Sintetizador()
        self.voz = Voz(self)

        self.del_documento = pronunciacion.del_documento(self.configuracion, self.ruta)
        self.generales = pronunciacion.generales(self.configuracion)

        contenedor = wx.BoxSizer(wx.VERTICAL)

        self.activa = wx.CheckBox(self, label=_("&Aplicar el diccionario de pronunciación"))
        self.activa.SetValue(bool(self.configuracion.obtener("pronunciacion_activa", True)))
        contenedor.Add(self.activa, 0, wx.ALL, MARGEN)

        self.cuaderno = wx.Notebook(self)
        etiquetar(self.cuaderno, _("Reglas"))
        self.pagina_documento, self.lista_documento = self._pagina(
            _("De este documento"),
            _("Los nombres propios de este libro. Se guardan con él y vuelven al abrirlo."))
        self.pagina_general, self.lista_general = self._pagina(
            _("Generales"),
            _("Se aplican a todos los documentos: siglas, símbolos, palabras extranjeras."))
        contenedor.Add(self.cuaderno, 1, wx.EXPAND | wx.ALL, MARGEN)

        if not self.ruta:
            self.cuaderno.SetSelection(1)

        botones = wx.BoxSizer(wx.HORIZONTAL)
        for etiqueta, manejador in (
                (_("&Nueva..."), self._al_nueva),
                (_("&Modificar..."), self._al_modificar),
                (_("&Eliminar"), self._al_eliminar)):
            boton = wx.Button(self, label=etiqueta)
            boton.Bind(wx.EVT_BUTTON, manejador)
            botones.Add(boton, 0, wx.ALL, 5)
        contenedor.Add(botones, 0, wx.ALL, 4)

        cierre = wx.BoxSizer(wx.HORIZONTAL)
        aceptar = wx.Button(self, wx.ID_OK, _("&Guardar"))
        aceptar.Bind(wx.EVT_BUTTON, self._al_guardar)
        aceptar.SetDefault()
        cierre.Add(aceptar, 0, wx.ALL, 5)
        cierre.Add(wx.Button(self, wx.ID_CANCEL, _("&Cancelar")), 0, wx.ALL, 5)
        contenedor.Add(cierre, 0, wx.ALIGN_RIGHT | wx.ALL, 4)

        self.SetSizerAndFit(contenedor)
        self.SetSize((720, 480))
        self.CenterOnParent()
        ayuda_opcion.enganchar(self)
        self._refrescar()
        self.cuaderno.SetFocus()

    # -- construcción ---------------------------------------------------------

    def _pagina(self, titulo: str, explicacion: str):
        """Crea una de las dos pestañas, con su lista."""
        panel = wx.Panel(self.cuaderno)
        caja = wx.BoxSizer(wx.VERTICAL)
        caja.Add(wx.StaticText(panel, label=explicacion), 0, wx.ALL, MARGEN)
        lista = ListaAccesible(panel, self.configuracion,
                               style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        etiquetar(lista, _("Reglas de pronunciación"))
        lista.InsertColumn(0, _("Escrito"), width=200)
        lista.InsertColumn(1, _("Se dice"), width=200)
        lista.InsertColumn(2, _("Cómo se aplica"), width=220)
        lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._al_modificar)
        caja.Add(lista, 1, wx.EXPAND | wx.ALL, MARGEN)
        panel.SetSizer(caja)
        self.cuaderno.AddPage(panel, titulo)
        return panel, lista

    # -- estado ---------------------------------------------------------------

    def _reglas_actuales(self) -> list[pronunciacion.Regla]:
        """Las reglas de la pestaña que está delante."""
        return (self.del_documento if self.cuaderno.GetSelection() == 0
                else self.generales)

    def _lista_actual(self) -> ListaAccesible:
        """La lista de la pestaña que está delante."""
        return (self.lista_documento if self.cuaderno.GetSelection() == 0
                else self.lista_general)

    def _refrescar(self, seleccionar: int = -1) -> None:
        """Vuelve a pintar las dos listas."""
        for reglas, lista in ((self.del_documento, self.lista_documento),
                              (self.generales, self.lista_general)):
            lista.DeleteAllItems()
            for numero, regla in enumerate(reglas):
                lista.InsertItem(numero, regla.buscar)
                lista.SetItem(numero, 1, regla.decir or _("(no se dice)"))
                detalles = []
                if regla.palabra_completa:
                    detalles.append(_("palabra entera"))
                if regla.distingue_mayusculas:
                    detalles.append(_("distingue mayúsculas"))
                lista.SetItem(numero, 2, ", ".join(detalles) or _("en cualquier sitio"))
        lista = self._lista_actual()
        if lista.GetItemCount():
            indice = seleccionar if 0 <= seleccionar < lista.GetItemCount() else 0
            lista.Select(indice)
            lista.Focus(indice)

    def _seleccionada(self) -> int:
        """Índice de la regla enfocada, o -1."""
        return self._lista_actual().GetFirstSelected()

    # -- acciones --------------------------------------------------------------

    def _al_nueva(self, evento) -> None:
        """Añade una regla."""
        reglas = self._reglas_actuales()
        if len(reglas) >= pronunciacion.MAXIMO:
            wx.MessageBox(
                _("No caben más de %d reglas en una lista.") % pronunciacion.MAXIMO,
                _("Diccionario de pronunciación"), wx.OK | wx.ICON_INFORMATION, self)
            return
        with DialogoRegla(self, None, self.sintetizador) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                return
            regla = dialogo.regla()
        if not regla.valida():
            self.voz.decir(_("Hay que escribir qué palabra se cambia."))
            return
        reglas.append(regla)
        self._refrescar(len(reglas) - 1)
        self.voz.decir(_("Regla añadida: %s") % regla.descripcion())

    def _al_modificar(self, evento) -> None:
        """Cambia la regla enfocada."""
        indice = self._seleccionada()
        reglas = self._reglas_actuales()
        if not 0 <= indice < len(reglas):
            self.voz.decir(_("No hay ninguna regla seleccionada."))
            return
        with DialogoRegla(self, reglas[indice], self.sintetizador) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                return
            nueva = dialogo.regla()
        if not nueva.valida():
            self.voz.decir(_("Hay que escribir qué palabra se cambia."))
            return
        reglas[indice] = nueva
        self._refrescar(indice)
        self.voz.decir(_("Regla modificada: %s") % nueva.descripcion())

    def _al_eliminar(self, evento) -> None:
        """Quita la regla enfocada, preguntando antes."""
        indice = self._seleccionada()
        reglas = self._reglas_actuales()
        if not 0 <= indice < len(reglas):
            self.voz.decir(_("No hay ninguna regla seleccionada."))
            return
        regla = reglas[indice]
        respuesta = wx.MessageBox(
            _("¿Eliminar la regla «%s»?") % regla.descripcion(),
            _("Diccionario de pronunciación"), wx.YES_NO | wx.ICON_QUESTION, self)
        if respuesta != wx.YES:
            return
        del reglas[indice]
        self._refrescar(min(indice, len(reglas) - 1))
        self.voz.decir(_("Regla eliminada."))

    def _al_guardar(self, evento) -> None:
        """Guarda las dos listas y vuelve a compilar la tabla en uso."""
        self.configuracion.establecer("pronunciacion_activa", self.activa.GetValue())
        pronunciacion.guardar_generales(self.configuracion, self.generales)
        if self.ruta:
            pronunciacion.guardar_del_documento(self.configuracion, self.ruta,
                                                self.del_documento)
        self.configuracion.guardar()
        # La tabla en uso se rehace ahora: si no, las reglas nuevas no se
        # notarían hasta volver a abrir el documento.
        self.ventana.lectura_voz.refrescar_pronunciacion()
        log.info("Diccionario de pronunciación guardado: %d del documento, %d generales",
                 len(self.del_documento), len(self.generales))
        self.EndModal(wx.ID_OK)
