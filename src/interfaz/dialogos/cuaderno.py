# -*- coding: utf-8 -*-
"""Ventana del cuaderno de estudio: lo marcado en varios libros, por temas.

Lo que se ve es la lista de apuntes agrupada por etiqueta, con el libro y el
punto del que sale cada uno. Arriba, un desplegable para quedarse con un solo
tema; abajo, el formato en el que guardarlo.

Se abre desde la biblioteca y actúa sobre **los libros que se estén viendo**, de
modo que filtrar por asignatura y sacar el cuaderno de esa asignatura son dos
pasos seguidos y no una función aparte.
"""

from __future__ import annotations

import wx

from interfaz.accesible import fila_etiquetada
from interfaz.dialogos import ayuda_opcion
from interfaz.listas import ListaAccesible, rellenar_columnas
from nucleo import cuaderno, etiquetas
from nucleo.idioma import _, _n
from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

MARGEN = 8


class DialogoCuaderno(wx.Dialog):
    """Reúne lo marcado en varios libros y lo saca a un archivo."""

    COLUMNAS = (_("Tema"), _("De dónde"), _("Lo marcado"))
    ANCHOS = (140, 250, 440)

    def __init__(self, padre: wx.Window, libros, configuracion) -> None:
        super().__init__(padre, title=_("Cuaderno de estudio"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.configuracion = configuracion
        self.libros = list(libros)
        self._todos = cuaderno.reunir(configuracion, self.libros)
        self._grupos: list = []

        self.SetSize((900, 620))
        contenedor = wx.BoxSizer(wx.VERTICAL)

        cuantos_libros = len({a.libro for a in self._todos})
        self.resumen = wx.StaticText(
            self, label=cuaderno.resumen(self._todos, cuantos_libros))
        contenedor.Add(self.resumen, 0, wx.ALL, MARGEN)

        fila = wx.BoxSizer(wx.HORIZONTAL)
        self._etiquetas = [""] + [e for e, _c in etiquetas.recuento(
            [_ConEtiquetas(a.etiquetas) for a in self._todos])]
        rotulos = [_("Todos los temas")] + [
            _("%(etiqueta)s (%(cuantas)d)") % {"etiqueta": e, "cuantas": c}
            for e, c in etiquetas.recuento(
                [_ConEtiquetas(a.etiquetas) for a in self._todos])]
        self.tema = fila_etiquetada(
            self, fila, _("&Tema:"), lambda p: wx.Choice(p, choices=rotulos),
            margen=MARGEN, horizontal=True)
        self.tema.SetSelection(0)

        self.casilla_notas = wx.CheckBox(self, label=_("Incluir las &notas"))
        self.casilla_notas.SetValue(True)
        fila.Add(self.casilla_notas, 0, wx.ALL, MARGEN)
        self.casilla_resaltados = wx.CheckBox(
            self, label=_("Incluir los &resaltados"))
        self.casilla_resaltados.SetValue(True)
        fila.Add(self.casilla_resaltados, 0, wx.ALL, MARGEN)
        contenedor.Add(fila, 0, wx.LEFT | wx.RIGHT, MARGEN)

        self.lista = fila_etiquetada(
            self, contenedor, _("&Apuntes:"),
            lambda p: ListaAccesible(p, configuracion, _("Apuntes del cuaderno"),
                                     size=(860, 380)),
            margen=MARGEN, proporcion=1)
        rellenar_columnas(self.lista, self.COLUMNAS, self.ANCHOS)

        pie = wx.BoxSizer(wx.HORIZONTAL)
        self._formatos = [(clave,) + datos
                          for clave, datos in cuaderno.nombres().items()]
        self.formato = fila_etiquetada(
            self, pie, _("&Guardar como:"),
            lambda p: wx.Choice(p, choices=[r for _c, r, _e, _f in self._formatos]),
            margen=MARGEN, horizontal=True)
        self.formato.SetSelection(0)
        self.boton_guardar = wx.Button(self, label=_("Guardar en un &archivo..."))
        pie.Add(self.boton_guardar, 0, wx.RIGHT, MARGEN)
        self.boton_repasar = wx.Button(self, label=_("Re&pasar..."))
        pie.Add(self.boton_repasar, 0, wx.RIGHT, MARGEN)
        pie.AddStretchSpacer()
        pie.Add(wx.Button(self, wx.ID_CANCEL, _("&Cerrar")), 0)
        contenedor.Add(pie, 0, wx.EXPAND | wx.ALL, MARGEN)
        self.SetSizer(contenedor)
        self.Layout()

        self.tema.Bind(wx.EVT_CHOICE, lambda evento: self._rellenar())
        self.casilla_notas.Bind(wx.EVT_CHECKBOX, lambda evento: self._rellenar())
        self.casilla_resaltados.Bind(wx.EVT_CHECKBOX,
                                     lambda evento: self._rellenar())
        self.boton_guardar.Bind(wx.EVT_BUTTON, self._al_guardar)
        self.boton_repasar.Bind(wx.EVT_BUTTON, self._al_repasar)

        self._rellenar()
        self.lista.SetFocus()
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    # -- la lista ------------------------------------------------------------

    def _tema_elegido(self) -> str:
        indice = self.tema.GetSelection()
        if 0 <= indice < len(self._etiquetas):
            return self._etiquetas[indice]
        return ""

    def _rellenar(self) -> None:
        """Rehace la lista con lo que se haya pedido."""
        apuntes = cuaderno.reunir(
            self.configuracion, self.libros, self._tema_elegido(),
            self.casilla_notas.GetValue(), self.casilla_resaltados.GetValue())
        self._grupos = cuaderno.por_etiqueta(apuntes)
        self.lista.DeleteAllItems()
        numero = 0
        for etiqueta, suyos in self._grupos:
            for apunte in suyos:
                self.lista.InsertItem(numero, etiqueta)
                self.lista.SetItem(numero, 1, apunte.de_donde())
                self.lista.SetItem(numero, 2, apunte.texto or apunte.nota)
                numero += 1
        cuantos_libros = len({a.libro for a in apuntes})
        self.resumen.SetLabel(cuaderno.resumen(apuntes, cuantos_libros))
        if numero:
            self.lista.Select(0)
            self.lista.Focus(0)
        else:
            self.lista.InsertItem(0, _("(No hay nada marcado con ese tema)"))
        self.boton_guardar.Enable(bool(numero))

    # -- repasar ---------------------------------------------------------------

    def _al_repasar(self, evento) -> None:
        """Abre una tanda de repaso con lo que se está viendo.

        Se pasa **lo que hay en la lista**, con su filtro de tema puesto: quien
        acaba de quedarse con el tema cuatro quiere repasar el tema cuatro.
        """
        del evento
        from interfaz.dialogos.repaso import DialogoRepaso
        from nucleo import repaso as motor

        apuntes = [apunte for _etiqueta, suyos in self._grupos for apunte in suyos]
        # Un apunte con dos etiquetas sale en dos grupos; para repasar hay que
        # verlo una sola vez.
        vistos = set()
        unicos = []
        for apunte in apuntes:
            clave = (apunte.ruta, apunte.posicion)
            if clave in vistos:
                continue
            vistos.add(clave)
            unicos.append(apunte)
        if not unicos:
            return
        estado = motor.cargar()
        if not estado.pendientes(unicos):
            wx.MessageBox(estado.resumen(unicos), _("Repasar"),
                          wx.OK | wx.ICON_INFORMATION, self)
            return
        with DialogoRepaso(self, unicos, self.configuracion) as dialogo:
            dialogo.ShowModal()

    # -- guardar -------------------------------------------------------------

    def _al_guardar(self, evento) -> None:
        del evento
        if not self._grupos:
            return
        indice = max(self.formato.GetSelection(), 0)
        formato, _rotulo, extension, filtro = self._formatos[indice]
        tema = self._tema_elegido()
        titulo = (_("Cuaderno de estudio: %s") % tema if tema
                  else _("Cuaderno de estudio"))
        with wx.FileDialog(self, _("Guardar el cuaderno"),
                           defaultFile=_("cuaderno") + extension,
                           wildcard=filtro,
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                return
            destino = dialogo.GetPath()
        try:
            cuaderno.exportar(self._grupos, destino, formato, titulo,
                              str(self.configuracion.obtener("idioma", "es")))
        except (OSError, ValueError) as error:
            wx.MessageBox(_("No se ha podido guardar el cuaderno:\n%s") % error,
                          _("Cuaderno de estudio"), wx.OK | wx.ICON_ERROR, self)
            return
        cuantos = sum(len(suyos) for _e, suyos in self._grupos)
        wx.MessageBox(
            _n("Se ha guardado %d apunte.", "Se han guardado %d apuntes.",
               cuantos) % cuantos,
            _("Cuaderno de estudio"), wx.OK | wx.ICON_INFORMATION, self)


class _ConEtiquetas:
    """Envoltorio mínimo para poder contar etiquetas de un apunte.

    :func:`nucleo.etiquetas.recuento` espera algo con el atributo
    ``etiquetas``, que es lo que tienen los marcadores; un apunte del cuaderno
    también lo tiene, pero pasarlo por aquí deja claro que solo se está usando
    eso y evita atar los dos módulos.
    """

    __slots__ = ("etiquetas",)

    def __init__(self, sus_etiquetas) -> None:
        self.etiquetas = list(sus_etiquetas or [])
