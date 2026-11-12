# -*- coding: utf-8 -*-
"""Editor de traducciones: crear y corregir los idiomas del programa.

Traducir un programa con un editor de ``.po`` corriente es incómodo para
cualquiera y directamente hostil con un lector de pantalla: rejillas de varias
columnas, campos que no dicen su nombre y listas que no anuncian en cuál de las
mil setecientas entradas estás.  Esta ventana hace lo mismo con controles
normales de Windows, que son los que el lector de pantalla sabe leer.

Qué hace
--------

* **Crea el catálogo de un idioma** a partir de los textos del programa, o abre
  uno que ya exista y le añade lo que se haya añadido al código desde entonces.
* **Traduce automáticamente** (:mod:`herramientas.traductor`) la entrada
  actual, las que falten o el idioma entero, respetando las variables, las
  combinaciones de teclas y los aceleradores de menú.
* **Deja corregir a mano** lo que la máquina no acierte, que es a lo que se
  dedica el noventa por ciento del tiempo y para lo que existe esto.
* **Compila** los catálogos a ``.mo``, que es lo que el programa carga.

Cómo está pensada para oírse
----------------------------

* La lista de entradas es una lista normal, y cada línea dice ya si está
  traducida o pendiente: no hay que ir al otro campo para saberlo.
* El original y la traducción son dos cuadros de texto con su etiqueta delante,
  recorribles con las flechas.
* Todo tiene atajo, y las órdenes largas avisan al empezar y al terminar en vez
  de dejar la ventana muda mientras trabajan.
* Lo que tarda —traducir el idioma entero— va en un hilo aparte con su barra de
  progreso, para que la ventana siga respondiendo y se pueda cancelar.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
for carpeta in (RAIZ / "herramientas", RAIZ / "src"):
    if str(carpeta) not in sys.path:
        sys.path.insert(0, str(carpeta))

import wx                                                        # noqa: E402

import textos as catalogos                                       # noqa: E402
import traductor                                                 # noqa: E402

#: Separación estándar entre controles, en píxeles.
MARGEN = 8

#: Cómo se marca en la lista una entrada según su estado.  Va **delante** del
#: texto a propósito: el lector de pantalla lee la línea de izquierda a
#: derecha, así que lo primero que se oye es si está hecha o no.
MARCAS = {"hecha": "[ok]", "pendiente": "[  ]"}


def etiquetar(control: wx.Window, nombre: str) -> wx.Window:
    """Le pone al control el nombre con el que el lector de pantalla lo anuncia."""
    control.SetName(nombre)
    return control


def fila(padre: wx.Window, caja: wx.Sizer, etiqueta: str, fabrica,
         proporcion: int = 0, horizontal: bool = False):
    """Añade una etiqueta y su control, en ese orden.

    El orden importa: el lector de pantalla nombra un control por la etiqueta
    que tiene **delante**, así que ponerla después lo dejaría sin nombre.
    """
    texto = wx.StaticText(padre, label=etiqueta)
    control = fabrica(padre)
    etiquetar(control, etiqueta.replace("&", ""))
    if horizontal:
        linea = wx.BoxSizer(wx.HORIZONTAL)
        linea.Add(texto, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, MARGEN)
        linea.Add(control, 1, wx.EXPAND)
        caja.Add(linea, 0, wx.EXPAND | wx.ALL, MARGEN)
    else:
        caja.Add(texto, 0, wx.LEFT | wx.TOP, MARGEN)
        caja.Add(control, proporcion, wx.EXPAND | wx.ALL, MARGEN)
    return control


class VentanaTraduccion(wx.Frame):
    """Ventana principal del editor de idiomas."""

    def __init__(self) -> None:
        super().__init__(None, title="Traducciones del Visor Universal", size=(1000, 700))
        #: Textos del programa, que son las claves de todo.
        self.originales, self.originales_plural = catalogos.recoger()
        self.claves = sorted(self.originales)
        #: Traducciones del idioma que se está editando.
        self.traducciones: dict[str, str] = {}
        self.plurales: dict[str, tuple] = {}
        self.codigo = ""
        self.sucio = False
        #: Entradas que se ven ahora en la lista, en su orden.
        self.visibles: list[str] = []
        self._trabajando = False
        self._cancelar = False

        self._crear_menu()
        self._crear_ventana()
        self.CreateStatusBar(1)
        self._decir("Elige un idioma para empezar.")
        self.Centre()
        self.Bind(wx.EVT_CLOSE, self._al_cerrar)

    # -- construcción ---------------------------------------------------------

    def _crear_menu(self) -> None:
        """Menú con todo lo que se puede hacer, cada cosa con su atajo."""
        barra = wx.MenuBar()

        archivo = wx.Menu()
        self._orden(archivo, "&Abrir un idioma...\tCtrl+O", self._al_abrir)
        self._orden(archivo, "&Nuevo idioma...\tCtrl+N", self._al_nuevo)
        archivo.AppendSeparator()
        self._orden(archivo, "&Guardar\tCtrl+G", self._al_guardar)
        self._orden(archivo, "&Compilar todos los idiomas\tCtrl+B", self._al_compilar)
        archivo.AppendSeparator()
        self._orden(archivo, "&Actualizar con los textos nuevos del programa\tF5",
                    self._al_actualizar)
        self._orden(archivo, "&Salir\tAlt+F4", lambda evento: self.Close())
        barra.Append(archivo, "&Archivo")

        traducir = wx.Menu()
        self._orden(traducir, "Traducir esta &entrada\tCtrl+T", self._al_traducir_una)
        self._orden(traducir, "Traducir las que &falten\tCtrl+Shift+T",
                    self._al_traducir_pendientes)
        self._orden(traducir, "Traducir &todo otra vez", self._al_traducir_todo)
        traducir.AppendSeparator()
        self._orden(traducir, "&Copiar el original en la traducción\tCtrl+D", self._al_copiar)
        self._orden(traducir, "&Vaciar esta traducción\tCtrl+Del", self._al_vaciar)
        barra.Append(traducir, "&Traducir")

        ver = wx.Menu()
        self._orden(ver, "&Todas las entradas\tCtrl+1", lambda evento: self._filtrar("todas"))
        self._orden(ver, "Solo las &pendientes\tCtrl+2",
                    lambda evento: self._filtrar("pendientes"))
        self._orden(ver, "Solo las &hechas\tCtrl+3", lambda evento: self._filtrar("hechas"))
        ver.AppendSeparator()
        self._orden(ver, "&Buscar...\tCtrl+F", self._al_buscar)
        self._orden(ver, "&Siguiente pendiente\tF3", self._al_siguiente_pendiente)
        self._orden(ver, "&Estadísticas\tCtrl+I", self._al_estadisticas)
        barra.Append(ver, "&Ver")

        ayuda = wx.Menu()
        self._orden(ayuda, "&Cómo se usa\tF1", self._al_ayuda)
        barra.Append(ayuda, "A&yuda")
        self.SetMenuBar(barra)

    def _orden(self, menu: wx.Menu, etiqueta: str, manejador):
        """Añade una entrada de menú y engancha lo que hace."""
        elemento = menu.Append(wx.ID_ANY, etiqueta)
        self.Bind(wx.EVT_MENU, manejador, elemento)
        return elemento

    def _crear_ventana(self) -> None:
        """Los controles: idioma, filtro, lista, original y traducción."""
        panel = wx.Panel(self)
        caja = wx.BoxSizer(wx.VERTICAL)

        self.idiomas = fila(
            panel, caja, "&Idioma:",
            lambda p: wx.Choice(p, choices=self._idiomas_disponibles()), horizontal=True)
        self.idiomas.Bind(wx.EVT_CHOICE, self._al_elegir_idioma)

        self.filtro = fila(
            panel, caja, "&Mostrar:",
            lambda p: wx.Choice(p, choices=["Todas las entradas", "Solo las pendientes",
                                            "Solo las hechas"]), horizontal=True)
        self.filtro.SetSelection(0)
        self.filtro.Bind(wx.EVT_CHOICE, lambda evento: self._llenar_lista())

        self.lista = fila(
            panel, caja, "&Entradas:",
            lambda p: wx.ListBox(p, style=wx.LB_SINGLE), proporcion=3)
        self.lista.Bind(wx.EVT_LISTBOX, self._al_elegir_entrada)

        self.original = fila(
            panel, caja, "Original en es&pañol:",
            lambda p: wx.TextCtrl(p, style=wx.TE_MULTILINE | wx.TE_READONLY
                                  | wx.TE_WORDWRAP), proporcion=2)
        self.traduccion = fila(
            panel, caja, "&Traducción:",
            lambda p: wx.TextCtrl(p, style=wx.TE_MULTILINE | wx.TE_WORDWRAP), proporcion=2)
        self.traduccion.Bind(wx.EVT_KILL_FOCUS, self._al_salir_de_la_traduccion)

        fila_botones = wx.BoxSizer(wx.HORIZONTAL)
        for etiqueta, manejador in (("Traducir esta entra&da", self._al_traducir_una),
                                    ("Traducir las que fa&lten", self._al_traducir_pendientes),
                                    ("G&uardar", self._al_guardar),
                                    ("&Compilar", self._al_compilar)):
            boton = wx.Button(panel, label=etiqueta)
            boton.Bind(wx.EVT_BUTTON, manejador)
            fila_botones.Add(boton, 0, wx.RIGHT, MARGEN)
        caja.Add(fila_botones, 0, wx.ALL, MARGEN)

        self.progreso = wx.Gauge(panel, range=100)
        etiquetar(self.progreso, "Progreso")
        self.progreso.Hide()
        caja.Add(self.progreso, 0, wx.EXPAND | wx.ALL, MARGEN)

        panel.SetSizer(caja)

    @staticmethod
    def _idiomas_disponibles() -> list[str]:
        """Idiomas que ya tienen catálogo, con su nombre y su código."""
        encontrados = []
        for carpeta in sorted(catalogos.IDIOMAS.glob("*/LC_MESSAGES/visor.po")):
            codigo = carpeta.parent.parent.name
            encontrados.append("%s (%s)" % (traductor.IDIOMAS.get(codigo, codigo), codigo))
        return encontrados

    # -- estado ---------------------------------------------------------------

    def _decir(self, mensaje: str) -> None:
        """Escribe en la barra de estado.  Es lo que el lector lee al consultarla."""
        self.SetStatusText(mensaje)

    def _titulo(self) -> None:
        """Pone en el título el idioma, cuánto lleva hecho y si falta guardar."""
        if not self.codigo:
            self.SetTitle("Traducciones del Visor Universal")
            return
        hechas = sum(1 for clave in self.claves if self.traducciones.get(clave))
        self.SetTitle("%s (%s) — %d de %d traducidas%s — Traducciones del Visor Universal"
                      % (traductor.IDIOMAS.get(self.codigo, self.codigo), self.codigo,
                         hechas, len(self.claves), " — SIN GUARDAR" if self.sucio else ""))

    def _estado_de(self, clave: str) -> str:
        """«hecha» o «pendiente», según tenga traducción o no."""
        return "hecha" if self.traducciones.get(clave) else "pendiente"

    # -- lista ----------------------------------------------------------------

    def _llenar_lista(self, elegir: str = "") -> None:
        """Vuelve a montar la lista con el filtro que esté puesto."""
        cual = max(self.filtro.GetSelection(), 0)
        self.visibles = [
            clave for clave in self.claves
            if cual == 0
            or (cual == 1 and self._estado_de(clave) == "pendiente")
            or (cual == 2 and self._estado_de(clave) == "hecha")
        ]
        entradas = ["%s %s" % (MARCAS[self._estado_de(clave)],
                               clave.replace("\n", " ")[:120]) for clave in self.visibles]
        self.lista.Set(entradas or ["(no hay ninguna entrada que enseñar)"])
        if self.visibles:
            indice = self.visibles.index(elegir) if elegir in self.visibles else 0
            self.lista.SetSelection(indice)
            self._mostrar_entrada(indice)
        else:
            self.original.SetValue("")
            self.traduccion.SetValue("")
        self._titulo()

    def _mostrar_entrada(self, indice: int) -> None:
        """Vuelca en los dos cuadros la entrada elegida."""
        if not 0 <= indice < len(self.visibles):
            return
        clave = self.visibles[indice]
        self.original.SetValue(clave)
        self.traduccion.SetValue(self.traducciones.get(clave, ""))

    def _clave_actual(self) -> str:
        """La entrada que está seleccionada, o cadena vacía."""
        indice = self.lista.GetSelection()
        return self.visibles[indice] if 0 <= indice < len(self.visibles) else ""

    def _guardar_lo_escrito(self) -> None:
        """Se queda con lo que haya en el cuadro de traducción."""
        clave = self._clave_actual()
        if not clave:
            return
        nueva = self.traduccion.GetValue()
        if nueva != self.traducciones.get(clave, ""):
            if nueva:
                self.traducciones[clave] = nueva
            else:
                self.traducciones.pop(clave, None)
            self.sucio = True
            indice = self.lista.GetSelection()
            self.lista.SetString(indice, "%s %s" % (MARCAS[self._estado_de(clave)],
                                                    clave.replace("\n", " ")[:120]))
            self._titulo()

    # -- eventos --------------------------------------------------------------

    def _al_elegir_entrada(self, evento) -> None:
        self._mostrar_entrada(self.lista.GetSelection())

    def _al_salir_de_la_traduccion(self, evento) -> None:
        evento.Skip()
        self._guardar_lo_escrito()

    def _al_elegir_idioma(self, evento) -> None:
        """Carga el idioma elegido en el desplegable."""
        elegido = self.idiomas.GetStringSelection()
        if "(" in elegido:
            self._cargar(elegido.rsplit("(", 1)[1].rstrip(")"))

    def _cargar(self, codigo: str) -> None:
        """Trae a la ventana el catálogo de un idioma."""
        if self.sucio and not self._confirmar_perder_cambios():
            return
        self.codigo = codigo
        self.traducciones, self.plurales = catalogos.cargar_po(codigo)
        self.sucio = False
        self._llenar_lista()
        hechas = sum(1 for clave in self.claves if self.traducciones.get(clave))
        self._decir("Idioma %s cargado: %d de %d traducidas."
                    % (codigo, hechas, len(self.claves)))
        self.lista.SetFocus()

    def _confirmar_perder_cambios(self) -> bool:
        """Pregunta antes de tirar lo que no se ha guardado."""
        respuesta = wx.MessageBox(
            "Hay cambios sin guardar en este idioma.\n\n¿Quieres guardarlos?",
            "Cambios sin guardar", wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION, self)
        if respuesta == wx.CANCEL:
            return False
        if respuesta == wx.YES:
            self._al_guardar(None)
        return True

    def _al_abrir(self, evento) -> None:
        """Elige un idioma de los que ya tienen catálogo."""
        disponibles = self._idiomas_disponibles()
        if not disponibles:
            wx.MessageBox("Todavía no hay ningún idioma. Crea uno con «Nuevo idioma».",
                          "Abrir un idioma", wx.OK | wx.ICON_INFORMATION, self)
            return
        with wx.SingleChoiceDialog(self, "Elige el idioma que quieres traducir:",
                                   "Abrir un idioma", disponibles) as dialogo:
            if dialogo.ShowModal() == wx.ID_OK:
                self._cargar(dialogo.GetStringSelection().rsplit("(", 1)[1].rstrip(")"))
                self.idiomas.Set(self._idiomas_disponibles())
                self.idiomas.SetSelection(disponibles.index(dialogo.GetStringSelection()))

    def _al_nuevo(self, evento) -> None:
        """Crea el catálogo de un idioma que todavía no está."""
        existentes = {carpeta.parent.parent.name
                      for carpeta in catalogos.IDIOMAS.glob("*/LC_MESSAGES/visor.po")}
        opciones = ["%s (%s)" % (nombre, codigo)
                    for codigo, nombre in sorted(traductor.IDIOMAS.items(),
                                                 key=lambda par: par[1])
                    if codigo not in existentes]
        if not opciones:
            wx.MessageBox("Ya están creados todos los idiomas que se ofrecen.",
                          "Nuevo idioma", wx.OK | wx.ICON_INFORMATION, self)
            return
        with wx.SingleChoiceDialog(self, "Elige el idioma que quieres crear:",
                                   "Nuevo idioma", opciones) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                return
            codigo = dialogo.GetStringSelection().rsplit("(", 1)[1].rstrip(")")
        catalogos.crear_idioma(codigo)
        self.idiomas.Set(self._idiomas_disponibles())
        self._cargar(codigo)
        self._decir("Idioma %s creado con %d entradas pendientes. "
                    "Tradúcelas con Control+Mayús+T." % (codigo, len(self.claves)))

    def _al_guardar(self, evento) -> None:
        """Escribe el catálogo en el disco."""
        if not self.codigo:
            return
        self._guardar_lo_escrito()
        destino = catalogos.escribir_po(self.codigo, self.traducciones, self.plurales)
        self.sucio = False
        self._titulo()
        self._decir("Guardado en %s" % destino)

    def _al_compilar(self, evento) -> None:
        """Convierte a .mo todos los catálogos, que es lo que el programa carga."""
        if self.sucio:
            self._al_guardar(None)
        cuantos = catalogos.compilar()
        self._decir("Compilados %d idiomas. Ya se pueden elegir en el programa." % cuantos)
        wx.MessageBox("Compilados %d idiomas.\n\nYa se pueden elegir en el programa, en "
                      "Opciones, Avanzado." % cuantos,
                      "Compilar", wx.OK | wx.ICON_INFORMATION, self)

    def _al_actualizar(self, evento) -> None:
        """Vuelve a leer los textos del programa, por si se han añadido."""
        antes = len(self.claves)
        self.originales, self.originales_plural = catalogos.recoger()
        self.claves = sorted(self.originales)
        self._llenar_lista()
        self._decir("Textos del programa: %d (antes había %d)." % (len(self.claves), antes))

    def _al_copiar(self, evento) -> None:
        """Deja el original como traducción: para lo que no se traduce."""
        clave = self._clave_actual()
        if clave:
            self.traduccion.SetValue(clave)
            self._guardar_lo_escrito()
            self._decir("Original copiado.")

    def _al_vaciar(self, evento) -> None:
        """Borra la traducción de esta entrada."""
        if self._clave_actual():
            self.traduccion.SetValue("")
            self._guardar_lo_escrito()
            self._decir("Traducción vaciada.")

    def _filtrar(self, cual: str) -> None:
        """Cambia el filtro de la lista desde el menú."""
        self.filtro.SetSelection({"todas": 0, "pendientes": 1, "hechas": 2}[cual])
        self._llenar_lista()
        self._decir("%d entradas." % len(self.visibles))

    def _al_buscar(self, evento) -> None:
        """Busca un texto entre los originales y las traducciones."""
        with wx.TextEntryDialog(self, "Texto que buscar:", "Buscar") as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                return
            buscado = dialogo.GetValue().strip().lower()
        if not buscado:
            return
        desde = self.lista.GetSelection() + 1
        for salto in range(len(self.visibles)):
            indice = (desde + salto) % len(self.visibles)
            clave = self.visibles[indice]
            if buscado in clave.lower() or buscado in self.traducciones.get(clave, "").lower():
                self.lista.SetSelection(indice)
                self._mostrar_entrada(indice)
                self.lista.SetFocus()
                self._decir("Encontrado en la entrada %d." % (indice + 1))
                return
        self._decir("No se ha encontrado «%s»." % buscado)

    def _al_siguiente_pendiente(self, evento) -> None:
        """Salta a la siguiente entrada sin traducir."""
        desde = self.lista.GetSelection() + 1
        for salto in range(len(self.visibles)):
            indice = (desde + salto) % len(self.visibles)
            if self._estado_de(self.visibles[indice]) == "pendiente":
                self.lista.SetSelection(indice)
                self._mostrar_entrada(indice)
                self.lista.SetFocus()
                self._decir("Entrada %d de %d, pendiente." % (indice + 1, len(self.visibles)))
                return
        self._decir("No queda ninguna pendiente.")

    def _al_estadisticas(self, evento) -> None:
        """Cuánto lleva traducido cada idioma."""
        lineas = ["Textos del programa: %d" % len(self.claves), ""]
        for carpeta in sorted(catalogos.IDIOMAS.glob("*/LC_MESSAGES/visor.po")):
            codigo = carpeta.parent.parent.name
            hechas, _plurales = catalogos.cargar_po(codigo)
            cuantas = sum(1 for clave in self.claves if hechas.get(clave))
            lineas.append("%s (%s): %d de %d, el %d por ciento"
                          % (traductor.IDIOMAS.get(codigo, codigo), codigo, cuantas,
                             len(self.claves), round(100 * cuantas / max(len(self.claves), 1))))
        wx.MessageBox("\n".join(lineas), "Estadísticas", wx.OK | wx.ICON_INFORMATION, self)

    def _al_ayuda(self, evento) -> None:
        """Explica de qué va esto y cómo se usa."""
        wx.MessageBox(
            "Cómo traducir el programa a un idioma nuevo:\n\n"
            "1. Archivo, Nuevo idioma: crea el catálogo con los textos pendientes.\n"
            "2. Traducir, Traducir las que falten: las traduce todas de una vez, "
            "respetando las variables, las combinaciones de teclas y los aceleradores "
            "de los menús. Tarda unos minutos y se puede cancelar.\n"
            "3. Repasa la lista con las flechas y corrige lo que no cuadre. Con "
            "Control+2 se ven solo las pendientes y con F3 se salta a la siguiente.\n"
            "4. Archivo, Compilar: deja los idiomas listos para el programa.\n"
            "5. En el Visor Universal, Opciones, Avanzado, elige el idioma. El cambio "
            "se aplica al reiniciar.\n\n"
            "La traducción automática es un punto de partida, no un traductor humano: "
            "lo que salga hay que repasarlo.",
            "Cómo se usa", wx.OK | wx.ICON_INFORMATION, self)

    # -- traducción automática ------------------------------------------------

    def _al_traducir_una(self, evento) -> None:
        """Traduce la entrada que esté seleccionada."""
        clave = self._clave_actual()
        if not clave or not self.codigo:
            return
        self._decir("Traduciendo...")
        try:
            traducida = traductor.traducir(clave, self.codigo)
        except traductor.ErrorTraduccion as error:
            self._decir("No se ha podido traducir: %s" % error)
            return
        self.traduccion.SetValue(traducida)
        self._guardar_lo_escrito()
        self._decir("Traducida.")

    def _al_traducir_pendientes(self, evento) -> None:
        """Traduce todo lo que falte, en un hilo aparte."""
        self._traducir_lote(rehacer=False)

    def _al_traducir_todo(self, evento) -> None:
        """Vuelve a traducir el idioma entero, incluso lo ya hecho."""
        if wx.MessageBox("Se va a volver a traducir TODO, incluidas las entradas que ya "
                         "tienes corregidas a mano.\n\n¿Seguro?",
                         "Traducir todo otra vez",
                         wx.YES_NO | wx.ICON_WARNING, self) != wx.YES:
            return
        self._traducir_lote(rehacer=True)

    def _traducir_lote(self, rehacer: bool) -> None:
        """Lanza la traducción automática con barra de progreso y cancelación."""
        if not self.codigo:
            wx.MessageBox("Elige antes un idioma.", "Traducir",
                          wx.OK | wx.ICON_INFORMATION, self)
            return
        if self._trabajando:
            return
        self._guardar_lo_escrito()
        if rehacer:
            self.traducciones.clear()
            self.plurales.clear()
            catalogos.escribir_po(self.codigo, self.traducciones, self.plurales)
        pendientes = sum(1 for clave in self.claves if not self.traducciones.get(clave))
        if not pendientes:
            self._decir("No queda ninguna entrada pendiente.")
            return
        self._trabajando = True
        self._cancelar = False
        self.progreso.SetRange(pendientes)
        self.progreso.SetValue(0)
        self.progreso.Show()
        self.Layout()
        self._decir("Traduciendo %d entradas. Pulsa Escape para cancelar." % pendientes)
        codigo = self.codigo

        def avisar(hechas, total, original, traduccion):
            wx.CallAfter(self._avanzar, hechas, total)

        def trabajo():
            try:
                resultado = traductor.traducir_catalogo(
                    codigo, avisar=avisar, parar=lambda: self._cancelar)
            except Exception as error:                  # pragma: no cover - red
                wx.CallAfter(self._fin_traduccion, 0, 0, str(error))
                return
            wx.CallAfter(self._fin_traduccion, resultado[0], resultado[1], "")

        threading.Thread(target=trabajo, name="traduccion", daemon=True).start()

    def _avanzar(self, hechas: int, total: int) -> None:
        """Mueve la barra de progreso desde el hilo de la interfaz."""
        self.progreso.SetValue(min(hechas, self.progreso.GetRange()))
        if hechas % 100 == 0:
            self._decir("Traducidas %d de %d." % (hechas, total))

    def _fin_traduccion(self, hechas: int, fallidas: int, error: str) -> None:
        """Recoge el resultado y vuelve a dejar la ventana como estaba."""
        self._trabajando = False
        self.progreso.Hide()
        self.Layout()
        self.traducciones, self.plurales = catalogos.cargar_po(self.codigo)
        self.sucio = False
        self._llenar_lista()
        if error:
            self._decir("La traducción ha fallado: %s" % error)
            wx.MessageBox("No se ha podido traducir:\n\n%s\n\nComprueba la conexión a "
                          "Internet." % error, "Traducir", wx.OK | wx.ICON_ERROR, self)
            return
        mensaje = ("Traducidas %d entradas%s.\n\nRepásalas: la traducción automática es un "
                   "punto de partida. Con Control+2 ves solo las que faltan."
                   % (hechas, ", %d fallidas" % fallidas if fallidas else ""))
        self._decir("Traducidas %d, fallidas %d." % (hechas, fallidas))
        wx.MessageBox(mensaje, "Traducir", wx.OK | wx.ICON_INFORMATION, self)
        self.lista.SetFocus()

    # -- cierre ---------------------------------------------------------------

    def _al_cerrar(self, evento) -> None:
        """Pide guardar antes de irse."""
        if self._trabajando:
            self._cancelar = True
        self._guardar_lo_escrito()
        if self.sucio and not self._confirmar_perder_cambios():
            evento.Veto()
            return
        evento.Skip()


def main() -> int:
    """Abre el editor."""
    aplicacion = wx.App(False)
    ventana = VentanaTraduccion()
    ventana.Show()
    aplicacion.MainLoop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
