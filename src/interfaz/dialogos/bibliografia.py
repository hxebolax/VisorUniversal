# -*- coding: utf-8 -*-
"""Ventana para sacar la bibliografía de varios libros a la vez.

Es el último paso de un trabajo y hasta ahora había que montarlo a mano. Lo que
se ve aquí es, en este orden: **qué se va a escribir** —la lista ya montada, que
se puede recorrer y leer antes de guardar nada—, **en qué estilo** y **en qué
formato**. Y encima de todo, un aviso si a alguna referencia le falta un dato,
porque una bibliografía con un año en blanco hay que arreglarla antes de
entregarla, no después.

Con una biblioteca entera, sin colgarse
---------------------------------------

Hasta la 1.3.5 esta ventana abría y analizaba **cada libro** para sacar su
editorial y su año, y lo hacía en el hilo de la ventana: con una biblioteca de
calibre de doscientos mil libros eran horas con todo parado y una barra que
solo decía el título del libro de turno. Ahora:

* Los datos salen de la biblioteca, que ya los tiene de calibre o del EPUB,
  así que no se abre nada (:func:`nucleo.bibliografia.reunir`).
* Se reúnen en otro hilo, con la ventana ya abierta, una barra, el porcentaje y
  qué se está haciendo escritos al lado, el avance dicho cada pocos segundos y
  un botón para detener.
* La lista es virtual: solo se monta la cita de las filas que se ven, y cambiar
  de estilo es instantáneo tenga las referencias que tenga.
* Copiar y guardar también van en segundo plano.

Abrir los libros a los que les falten datos sigue siendo posible, pero es una
casilla que hay que marcar: es lo único lento de verdad.
"""

from __future__ import annotations

import wx

from interfaz.accesible import fila_etiquetada
from interfaz.anuncios import Voz
from interfaz.dialogos import ayuda_opcion
from interfaz.dialogos.biblioteca_gestor import Tarea, crear_barra
from interfaz.listas import ListaVirtual, rellenar_columnas
from nucleo import bibliografia, citas
from nucleo.idioma import _, _n
from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

MARGEN = 8

#: A partir de cuántas referencias incompletas se pregunta antes de abrir los
#: libros para completarlas.
MUCHAS = 500


class DialogoBibliografia(wx.Dialog):
    """La bibliografía de unos libros, en el estilo y el formato que se elija."""

    COLUMNAS = (_("Referencia"), _("Le falta"))
    ANCHOS = (640, 200)

    def __init__(self, padre: wx.Window, libros, configuracion, opciones) -> None:
        super().__init__(padre, title=_("Bibliografía"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.configuracion = configuracion
        self.opciones = opciones
        self.libros = list(libros)
        self._voz = Voz(self)
        #: Todas las referencias, ya ordenadas.
        self._referencias: list = []
        #: Las que se enseñan (todas, o solo las incompletas).
        self._visibles: list = []
        self._incompletas = 0
        self._reunido = False

        self.SetSize((920, 640))
        contenedor = wx.BoxSizer(wx.VERTICAL)

        self.resumen = wx.StaticText(
            self, label=_n("Bibliografía de %d libro.",
                           "Bibliografía de %d libros.", len(self.libros))
            % len(self.libros))
        contenedor.Add(self.resumen, 0, wx.ALL, MARGEN)

        fila = wx.BoxSizer(wx.HORIZONTAL)
        self._estilos = citas.nombres()
        self.estilo = fila_etiquetada(
            self, fila, _("&Estilo de cita:"),
            lambda p: wx.Choice(p, choices=[rotulo for _c, rotulo in self._estilos]),
            margen=MARGEN, horizontal=True)
        guardado = str(self.configuracion.obtener("cita_estilo", "iso690"))
        claves = [clave for clave, _r in self._estilos]
        self.estilo.SetSelection(claves.index(guardado) if guardado in claves else 0)

        self._formatos = [(clave,) + datos
                          for clave, datos in bibliografia.nombres().items()]
        self.formato = fila_etiquetada(
            self, fila, _("&Guardar como:"),
            lambda p: wx.Choice(p, choices=[r for _c, r, _e, _f in self._formatos]),
            margen=MARGEN, horizontal=True)
        self.formato.SetSelection(0)
        contenedor.Add(fila, 0, wx.LEFT | wx.RIGHT, MARGEN)

        self._modos = [("todas", _("Todas las referencias")),
                       ("incompletas", _("Solo las que tienen datos sin rellenar"))]
        self.mostrar = fila_etiquetada(
            self, contenedor, _("&Mostrar:"),
            lambda p: wx.Choice(p, choices=[n for _c, n in self._modos]),
            margen=MARGEN, horizontal=True)
        self.mostrar.SetSelection(0)

        self.abrir_libros = wx.CheckBox(self, label=_(
            "Abrir los &libros a los que les falten datos (mucho más lento)"))
        self.abrir_libros.SetValue(
            bool(self.configuracion.obtener("bibliografia_abrir_libros", False)))
        contenedor.Add(self.abrir_libros, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, MARGEN)

        self.aviso = wx.StaticText(self, label="")
        contenedor.Add(self.aviso, 0, wx.ALL, MARGEN)

        self.lista = fila_etiquetada(
            self, contenedor, _("&Referencias:"),
            lambda p: ListaVirtual(p, configuracion, _("Referencias"), size=(880, 320),
                                   multiple=False),
            margen=MARGEN, proporcion=1)
        rellenar_columnas(self.lista, self.COLUMNAS, self.ANCHOS)
        self._poner_aviso_en_lista(_("(Preparando las referencias...)"))

        self.estado, self.barra, self.boton_detener = crear_barra(self, contenedor)
        self.tarea = Tarea(self, self.barra, self.estado, self.boton_detener, configuracion)

        pie = wx.BoxSizer(wx.HORIZONTAL)
        self.boton_copiar = wx.Button(self, label=_("Co&piar al portapapeles"))
        pie.Add(self.boton_copiar, 0, wx.RIGHT, MARGEN)
        self.boton_guardar = wx.Button(self, label=_("Guardar en un &archivo..."))
        pie.Add(self.boton_guardar, 0, wx.RIGHT, MARGEN)
        pie.AddStretchSpacer()
        pie.Add(wx.Button(self, wx.ID_CANCEL, _("&Cerrar")), 0)
        contenedor.Add(pie, 0, wx.EXPAND | wx.ALL, MARGEN)
        self.SetSizer(contenedor)
        self.Layout()

        self.estilo.Bind(wx.EVT_CHOICE, lambda evento: self._rellenar())
        self.mostrar.Bind(wx.EVT_CHOICE, lambda evento: self._rellenar())
        self.abrir_libros.Bind(wx.EVT_CHECKBOX, self._al_abrir_libros)
        self.boton_copiar.Bind(wx.EVT_BUTTON, self._al_copiar)
        self.boton_guardar.Bind(wx.EVT_BUTTON, self._al_guardar)
        self.Bind(wx.EVT_BUTTON, self._al_cerrar, id=wx.ID_CANCEL)

        self._activar_salidas(False)
        self.lista.SetFocus()
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)
        # Se reúne después de enseñar la ventana, para que aparezca al momento.
        wx.CallAfter(self._reunir)

    # -- los datos -----------------------------------------------------------

    def _poner_aviso_en_lista(self, texto: str) -> None:
        """Deja en la lista una sola fila con un aviso."""
        self.lista.poner_filas(1, lambda fila, columna: texto if columna == 0 else "")

    def _activar_salidas(self, activas: bool) -> None:
        """Copiar y guardar solo tienen sentido con las referencias ya hechas."""
        self.boton_copiar.Enable(activas)
        self.boton_guardar.Enable(activas)

    def _reunir(self) -> None:
        """Monta las referencias en segundo plano."""
        if not self or self.tarea.ocupada():
            return
        libros = self.libros
        opciones = self.opciones
        abrir = self.abrir_libros.GetValue()

        def trabajo(progreso, cancelado):
            reunidas = bibliografia.reunir(libros, opciones, progreso=progreso,
                                           cancelado=cancelado, abrir=abrir)
            progreso(0, 0, _("Ordenando las referencias..."))
            ordenadas = bibliografia.ordenar(reunidas)
            incompletas = sum(1 for datos in ordenadas if bibliografia.incompleta(datos))
            return ordenadas, incompletas, cancelado()

        self._activar_salidas(False)
        self.abrir_libros.Enable(False)
        self.tarea.lanzar(trabajo, self._reunido_fin,
                          _("Preparando las referencias de %d libros...") % len(libros)
                          if len(libros) > 200 else "")

    def _reunido_fin(self, resultado, error: str) -> None:
        """Enseña lo reunido y dice cómo ha quedado."""
        self.abrir_libros.Enable(True)
        if error or resultado is None:
            self.estado.SetLabel(_("No se han podido preparar las referencias: %s") % error)
            self._voz.decir(self.estado.GetLabel())
            self._poner_aviso_en_lista(self.estado.GetLabel())
            return
        self._referencias, self._incompletas, detenido = resultado
        self._reunido = True
        self._rellenar()
        self._activar_salidas(bool(self._referencias))
        mensaje = self._frase_resumen()
        if detenido and len(self._referencias) < len(self.libros):
            mensaje = (_("Detenido: hay %(hechas)d referencias de %(total)d libros.")
                       % {"hechas": len(self._referencias), "total": len(self.libros)}
                       + " " + mensaje)
        self.estado.SetLabel(mensaje)
        self._voz.decir(mensaje, interrumpir=False)

    def _frase_resumen(self) -> str:
        """Cuántas referencias hay y a cuántas les falta algo."""
        if self._incompletas:
            return _n("A %d referencia le faltan datos: revísala antes de entregarla.",
                      "A %d referencias les faltan datos: revísalas antes de entregarlas.",
                      self._incompletas) % self._incompletas
        return _("Todas las referencias están completas.")

    def _estilo_elegido(self) -> str:
        indice = max(self.estilo.GetSelection(), 0)
        return self._estilos[indice][0] if indice < len(self._estilos) else "iso690"

    def _rellenar(self) -> None:
        """Pone en la lista las referencias, en el estilo elegido.

        Es instantáneo aunque sean ciento noventa mil: la lista solo pide la
        cita de las filas que enseña.
        """
        if not self._reunido:
            return
        solo_incompletas = self._modos[max(0, self.mostrar.GetSelection())][0] == "incompletas"
        if solo_incompletas:
            self._visibles = [d for d in self._referencias if bibliografia.incompleta(d)]
        else:
            self._visibles = list(self._referencias)
        self.aviso.SetLabel(self._frase_resumen())
        if not self._visibles:
            self._poner_aviso_en_lista(_("(Ninguna referencia que enseñar)"))
            return
        visibles = self._visibles
        estilo = self._estilo_elegido()
        pagina = _("la página")

        def celda(fila: int, columna: int) -> str:
            datos = visibles[fila]
            if columna == 0:
                return citas.referencia(datos, estilo)
            return ", ".join(q for q in citas.lo_que_falta(datos) if q != pagina)

        self.lista.poner_filas(len(visibles), celda)
        self.lista.seleccionar_solo(0)

    def _al_abrir_libros(self, evento) -> None:
        """Marcar la casilla vuelve a reunir, abriendo los libros incompletos."""
        del evento
        marcada = self.abrir_libros.GetValue()
        self.configuracion.establecer("bibliografia_abrir_libros", marcada)
        if not marcada or not self._reunido or not self._incompletas:
            return
        if self._incompletas > MUCHAS and wx.MessageBox(
                _("A %d referencias les faltan datos. Abrir tantos libros puede tardar "
                  "mucho; se puede detener cuando quieras y lo completado hasta ahí se "
                  "queda.\n\n¿Abrirlos ahora?") % self._incompletas,
                _("Bibliografía"), wx.YES_NO | wx.ICON_QUESTION, self) != wx.YES:
            self.abrir_libros.SetValue(False)
            self.configuracion.establecer("bibliografia_abrir_libros", False)
            return
        self._reunir()

    # -- salidas -------------------------------------------------------------

    def _al_copiar(self, evento) -> None:
        """Copia al portapapeles las referencias que se ven, en el estilo elegido."""
        del evento
        if not self._visibles or self.tarea.ocupada():
            return
        visibles = list(self._visibles)
        estilo = self._estilo_elegido()

        def trabajo(progreso, cancelado):
            partes = []
            for numero, datos in enumerate(visibles):
                if numero % 2000 == 0:
                    if cancelado():
                        return None
                    progreso(numero, len(visibles), _("Preparando el texto: %(hecho)d de "
                                                     "%(total)d") % {"hecho": numero,
                                                                     "total": len(visibles)})
                partes.append(citas.referencia(datos, estilo))
            return "\n\n".join(partes)

        def hecho(texto, error: str) -> None:
            if error or texto is None:
                self.estado.SetLabel(error or _("Detenido."))
                return
            if wx.TheClipboard.Open():
                try:
                    wx.TheClipboard.SetData(wx.TextDataObject(texto))
                finally:
                    wx.TheClipboard.Close()
            mensaje = _n("Se ha copiado %d referencia al portapapeles.",
                         "Se han copiado %d referencias al portapapeles.",
                         len(visibles)) % len(visibles)
            self.estado.SetLabel(mensaje)
            wx.MessageBox(mensaje, _("Bibliografía"), wx.OK | wx.ICON_INFORMATION, self)

        self.tarea.lanzar(trabajo, hecho, "")

    def _al_guardar(self, evento) -> None:
        """Escribe en un archivo las referencias que se ven."""
        del evento
        if not self._visibles or self.tarea.ocupada():
            return
        indice = max(self.formato.GetSelection(), 0)
        formato, _rotulo, extension, filtro = self._formatos[indice]
        with wx.FileDialog(self, _("Guardar la bibliografía"),
                           defaultFile=_("bibliografia") + extension,
                           wildcard=filtro,
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                return
            destino = dialogo.GetPath()
        visibles = list(self._visibles)
        estilo = self._estilo_elegido()
        idioma = str(self.configuracion.obtener("idioma", "es"))

        def trabajo(progreso, cancelado):
            del cancelado
            progreso(0, 0, _("Guardando la bibliografía..."))
            bibliografia.exportar(visibles, destino, formato, estilo, "", idioma)
            return len(visibles)

        def hecho(cuantas, error: str) -> None:
            if error:
                wx.MessageBox(_("No se ha podido guardar la bibliografía:\n%s") % error,
                              _("Bibliografía"), wx.OK | wx.ICON_ERROR, self)
                return
            mensaje = _n("Se ha guardado %d referencia.",
                         "Se han guardado %d referencias.", cuantas) % cuantas
            self.estado.SetLabel(mensaje)
            wx.MessageBox(mensaje, _("Bibliografía"), wx.OK | wx.ICON_INFORMATION, self)

        self.tarea.lanzar(trabajo, hecho, "")

    def _al_cerrar(self, evento) -> None:
        """Al cerrar se para lo que siga en marcha; no se pierde nada."""
        del evento
        self.tarea.parar.set()
        if self.IsModal():
            self.EndModal(wx.ID_CANCEL)
        else:
            self.Destroy()

    def Destroy(self):                               # noqa: N802 - lo pide wx
        """Al cerrar, se para cualquier trabajo que siguiera vivo."""
        self.tarea.parar.set()
        return super().Destroy()
