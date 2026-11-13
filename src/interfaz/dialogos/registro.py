# -*- coding: utf-8 -*-
"""Visor de registros: la ventana que abre «Ayuda → Ver registro de la aplicación».

Abrir el archivo de registro en el Bloc de notas obligaba a leer miles de
líneas seguidas, sin filtro y sin forma de volver a una en concreto.  Este
visor lo presenta como una lista de varias columnas —hora, nivel, módulo,
mensaje— que se recorre con las flechas y, gracias a
:class:`interfaz.listas.ListaAccesible`, también columna a columna.

Detalles que importan cuando el registro crece:

* Se lee **solo el final** del archivo (:data:`MAXIMO_COLA` bytes).  En modo
  DEBUG un registro pasa de varios megabytes con facilidad y lo interesante
  está siempre al final.
* La lectura y el troceo se hacen **en otro hilo**, de modo que abrir el visor
  no congela la aplicación.  Un número de carga descarta el resultado si el
  usuario cambia de sesión antes de que termine.
* **Seguir en vivo**: con la casilla marcada se relee cada pocos segundos y,
  si hay entradas nuevas, se pinta y el foco baja a la última.  Es lo que
  convierte el visor en una herramienta de diagnóstico: se deja abierto,
  se reproduce el fallo y se ve aparecer el error.

La ventana **no es modal**: se puede seguir usando el programa con el visor
delante, que es justo lo que hace falta para reproducir un problema.
"""

from __future__ import annotations

import os
import re
import time
import threading

import wx

from interfaz.temporizadores import parar_al_destruir
from interfaz.accesible import etiquetar, fila_etiquetada
from interfaz.anuncios import Voz
from interfaz.dialogos import ayuda_opcion
from interfaz.listas import ListaAccesible, rellenar_columnas
from nucleo import registro as modulo_registro
from nucleo import rutas
from nucleo.idioma import _, _n
from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

MARGEN = 8

#: Cuánto se lee del final del archivo.  Un megabyte y pico son varios miles
#: de entradas: de sobra para diagnosticar, e instantáneo de cargar.
MAXIMO_COLA = 1_200_000

#: Cada cuánto se relee el archivo con «Seguir en vivo», en milisegundos.
INTERVALO_VIVO = 2000

#: Niveles ordenados de menos a más grave.  El orden es el que decide qué
#: entra al filtrar por nivel mínimo.
NIVELES = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
_ORDEN = {nombre: numero for numero, nombre in enumerate(NIVELES)}

#: Cabecera de una entrada, tal y como la escribe :mod:`nucleo.registro`:
#: ``2026-08-29 09:20:11,123 | INFO     | interfaz.ventana | MainThread | abrir:42 | mensaje``
_CABECERA = re.compile(
    r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)[,.]?\d*\s*\|\s*([A-Z]+)\s*\|\s*([^|]*)\|"
    r"\s*([^|]*)\|\s*([^|]*)\|\s?(.*)$"
)

#: Columnas del visor, con su ancho.  El título es lo que se anuncia al
#: recorrer la fila con las flechas izquierda y derecha.
COLUMNAS = ("Hora", "Nivel", _("Módulo"), "Origen", "Mensaje")
ANCHOS = (150, 90, 220, 170, 700)


class Entrada:
    """Una entrada del registro ya troceada en sus campos.

    Las líneas de continuación (las trazas de un error, que ocupan varias
    líneas) se pegan al mensaje de la entrada a la que pertenecen: si no, la
    lista se llenaría de filas sueltas sin hora ni nivel.
    """

    __slots__ = ("hora", "nivel", "modulo", "origen", "mensaje")

    def __init__(self, hora: str, nivel: str, modulo: str, origen: str, mensaje: str) -> None:
        self.hora = hora
        self.nivel = nivel
        self.modulo = modulo
        self.origen = origen
        self.mensaje = mensaje

    def campo(self, numero: int) -> str:
        """Texto de una columna, por su número."""
        return (self.hora, self.nivel, self.modulo, self.origen, self.mensaje)[numero]

    def como_linea(self) -> str:
        """Reconstruye la entrada en una sola línea, para copiarla."""
        partes = [self.hora, self.nivel, self.modulo, self.origen, self.mensaje]
        return " | ".join(parte for parte in partes if parte)


def trocear(texto: str) -> list[Entrada]:
    """Convierte el texto de un registro en una lista de :class:`Entrada`."""
    entradas: list[Entrada] = []
    actual: Entrada | None = None
    for linea in texto.splitlines():
        encontrado = _CABECERA.match(linea)
        if encontrado:
            if actual is not None:
                entradas.append(actual)
            hora, nivel, modulo, hilo, origen, mensaje = encontrado.groups()
            actual = Entrada(
                hora.strip(),
                nivel.strip() if nivel.strip() in _ORDEN else "INFO",
                modulo.strip(),
                "%s (%s)" % (origen.strip(), hilo.strip()) if hilo.strip() else origen.strip(),
                mensaje.strip(),
            )
        elif actual is not None:
            actual.mensaje = (actual.mensaje + "\n" + linea) if actual.mensaje else linea
        elif linea.strip():
            # Texto anterior a la primera cabecera (la cabecera de sesión).
            actual = Entrada("", "INFO", "", "", linea)
    if actual is not None:
        entradas.append(actual)
    return entradas


def leer_cola(ruta) -> tuple[str, bool, int]:
    """Lee el final de un archivo de registro.

    :return: ``(texto, recortado, tamaño_total)``.  Si el archivo pasa de
             :data:`MAXIMO_COLA` se salta el principio y se descarta la primera
             línea leída, que casi seguro está partida por la mitad.
    """
    tamano = os.path.getsize(ruta)
    with open(ruta, "rb") as archivo:
        if tamano > MAXIMO_COLA:
            archivo.seek(tamano - MAXIMO_COLA)
            datos = archivo.read()
            corte = datos.find(b"\n")
            if corte != -1:
                datos = datos[corte + 1:]
            recortado = True
        else:
            datos = archivo.read()
            recortado = False
    return datos.decode("utf-8", errors="replace"), recortado, tamano


class DialogoRegistro(wx.Dialog):
    """Visor de registros, no modal y con seguimiento en vivo.

    :param padre: Ventana principal.
    :param configuracion: Preferencias, para el nivel que se guarda en disco y
                          para los ajustes de lectura por columnas de la lista.
    """

    #: Etiquetas del filtro de nivel mínimo, en el mismo orden que se usan.
    FILTROS = (_("Todo"), _("Depuración (DEBUG) o superior"),
               _("Información (INFO) o superior"), _("Avisos (WARNING) o superior"),
               _("Solo errores"))
    #: Nivel mínimo que corresponde a cada filtro (``None`` = sin filtro).
    UMBRALES = (None, "DEBUG", "INFO", "WARNING", "ERROR")

    def __init__(self, padre: wx.Window, configuracion) -> None:
        super().__init__(padre, title=_("Registro de la aplicación"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.configuracion = configuracion
        self._voz = Voz(self)
        self._archivos: list = []
        self._entradas: list[Entrada] = []
        self._visibles: list[Entrada] = []
        self._recortado = False
        self._tamano = 0
        self._carga = 0            # número de carga, para descartar resultados viejos
        self._releyendo = False

        self._construir()
        self._temporizador = wx.Timer(self)
        parar_al_destruir(self, self._temporizador)
        self.Bind(wx.EVT_TIMER, self._al_latir, self._temporizador)
        self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar)
        self.Bind(wx.EVT_CLOSE, self._al_cerrar)

        self._cargar_sesiones()
        self._cargar()
        self.lista.SetFocus()
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    # -- construcción --------------------------------------------------------

    def _construir(self) -> None:
        """Monta los controles del visor."""
        contenedor = wx.BoxSizer(wx.VERTICAL)

        fila = wx.BoxSizer(wx.HORIZONTAL)
        self.sesiones = fila_etiquetada(
            self, fila, _("&Sesión:"), lambda p: wx.Choice(p, choices=[_("(cargando)")]),
            margen=MARGEN, horizontal=True, proporcion=2)
        self.filtro = fila_etiquetada(
            self, fila, _("&Nivel mínimo:"), lambda p: wx.Choice(p, choices=list(self.FILTROS)),
            margen=MARGEN, horizontal=True, proporcion=1)
        self.filtro.SetSelection(0)
        contenedor.Add(fila, 0, wx.EXPAND)

        fila_busqueda = wx.BoxSizer(wx.HORIZONTAL)
        self.busqueda = fila_etiquetada(
            self, fila_busqueda, "&Buscar:",
            lambda p: wx.TextCtrl(p, style=wx.TE_PROCESS_ENTER),
            margen=MARGEN, horizontal=True, proporcion=1)
        self.boton_anterior = wx.Button(self, label=_("Buscar &anterior"))
        self.boton_siguiente = wx.Button(self, label=_("Buscar si&guiente"))
        fila_busqueda.Add(self.boton_anterior, 0, wx.ALL, MARGEN)
        fila_busqueda.Add(self.boton_siguiente, 0, wx.ALL, MARGEN)
        contenedor.Add(fila_busqueda, 0, wx.EXPAND)

        contenedor.Add(wx.StaticText(self, label=_("&Entradas del registro:")), 0,
                       wx.LEFT | wx.RIGHT | wx.TOP, MARGEN)
        self.lista = etiquetar(ListaAccesible(
            self, self.configuracion, _("Entradas del registro"), size=(900, 420)),
            _("Entradas del registro"))
        rellenar_columnas(self.lista, COLUMNAS, ANCHOS)
        contenedor.Add(self.lista, 1, wx.EXPAND | wx.ALL, MARGEN)

        self.estado = wx.StaticText(self, label="")
        contenedor.Add(self.estado, 0, wx.LEFT | wx.RIGHT, MARGEN)

        fila_ajustes = wx.BoxSizer(wx.HORIZONTAL)
        self.nivel_guardado = fila_etiquetada(
            self, fila_ajustes, _("&Guardar en disco a partir de:"),
            lambda p: wx.Choice(p, choices=list(modulo_registro.NIVELES)),
            margen=MARGEN, horizontal=True, proporcion=1)
        actual = str(self.configuracion.obtener("nivel_registro") or "INFO")
        self.nivel_guardado.SetSelection(
            list(modulo_registro.NIVELES).index(actual) if actual in modulo_registro.NIVELES else 1)
        self.en_vivo = wx.CheckBox(self, label=_("Seguir en &vivo"))
        fila_ajustes.Add(self.en_vivo, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, MARGEN)
        contenedor.Add(fila_ajustes, 0, wx.EXPAND)

        fila_botones = wx.BoxSizer(wx.HORIZONTAL)
        self.boton_recargar = wx.Button(self, label=_("&Recargar"))
        self.boton_copiar = wx.Button(self, label=_("&Copiar lo mostrado"))
        self.boton_carpeta = wx.Button(self, label=_("Abrir la ca&rpeta"))
        self.boton_vaciar = wx.Button(self, label=_("&Vaciar esta sesión"))
        for boton in (self.boton_recargar, self.boton_copiar,
                      self.boton_carpeta, self.boton_vaciar):
            fila_botones.Add(boton, 0, wx.ALL, MARGEN)
        fila_botones.AddStretchSpacer()
        cerrar = wx.Button(self, wx.ID_CANCEL, "Cerrar")
        cerrar.SetDefault()
        fila_botones.Add(cerrar, 0, wx.ALL, MARGEN)
        contenedor.Add(fila_botones, 0, wx.EXPAND)

        self.SetSizerAndFit(contenedor)

        self.sesiones.Bind(wx.EVT_CHOICE, lambda evento: self._cargar())
        self.filtro.Bind(wx.EVT_CHOICE, lambda evento: self._pintar(anunciar=True))
        self.busqueda.Bind(wx.EVT_TEXT_ENTER, lambda evento: self._buscar(1))
        self.boton_siguiente.Bind(wx.EVT_BUTTON, lambda evento: self._buscar(1))
        self.boton_anterior.Bind(wx.EVT_BUTTON, lambda evento: self._buscar(-1))
        self.boton_recargar.Bind(wx.EVT_BUTTON, lambda evento: self._cargar())
        self.boton_copiar.Bind(wx.EVT_BUTTON, self._al_copiar)
        self.boton_carpeta.Bind(wx.EVT_BUTTON, self._al_abrir_carpeta)
        self.boton_vaciar.Bind(wx.EVT_BUTTON, self._al_vaciar)
        self.nivel_guardado.Bind(wx.EVT_CHOICE, self._al_cambiar_nivel)
        self.en_vivo.Bind(wx.EVT_CHECKBOX, self._al_seguir)

    # -- sesiones ------------------------------------------------------------

    def _cargar_sesiones(self) -> None:
        """Rellena el desplegable con los archivos de registro que hay."""
        carpeta = rutas.ruta_logs()
        try:
            archivos = sorted(carpeta.glob("sesion_*.log"),
                              key=lambda ruta: ruta.stat().st_mtime, reverse=True)
            archivos += sorted(carpeta.glob("errores_*.log"),
                               key=lambda ruta: ruta.stat().st_mtime, reverse=True)
        except OSError as error:
            log.warning("No se ha podido listar la carpeta de registros: %s", error)
            archivos = []
        self._archivos = archivos
        etiquetas = []
        for numero, ruta in enumerate(archivos):
            momento = time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(ruta.stat().st_mtime))
            clase = "errores" if ruta.name.startswith("errores_") else _("sesión")
            etiqueta = _("%s de %s") % (clase.capitalize(), momento)
            if numero == 0:
                etiqueta += _("  (la de ahora)")
            etiquetas.append(etiqueta)
        self.sesiones.Set(etiquetas or [_("(todavía no hay ningún registro)")])
        self.sesiones.SetSelection(0)

    def _ruta_actual(self):
        """Archivo de registro que se está viendo, o ``None``."""
        indice = self.sesiones.GetSelection()
        return self._archivos[indice] if 0 <= indice < len(self._archivos) else None

    def _es_la_de_ahora(self) -> bool:
        """Indica si lo que se ve es el registro de la sesión en curso."""
        return self.sesiones.GetSelection() == 0 and bool(self._archivos)

    # -- carga ---------------------------------------------------------------

    def _cargar(self) -> None:
        """Lee y trocea el registro en otro hilo, y lo pinta al terminar."""
        ruta = self._ruta_actual()
        if ruta is None or not ruta.exists():
            self._entradas = []
            self._pintar()
            return
        self._carga += 1
        numero = self._carga
        self.estado.SetLabel(_("Leyendo el registro..."))

        def trabajo():
            """Lee el archivo fuera del hilo de la interfaz."""
            try:
                texto, recortado, tamano = leer_cola(ruta)
                entradas = trocear(texto)
            except OSError as error:
                wx.CallAfter(self._fallo_de_carga, numero, str(error))
                return
            wx.CallAfter(self._carga_lista, numero, entradas, recortado, tamano)

        threading.Thread(target=trabajo, name="registro", daemon=True).start()

    def _carga_lista(self, numero: int, entradas, recortado: bool, tamano: int,
                     al_final: bool = False) -> None:
        """Recibe el resultado de la lectura, si sigue siendo el que se pidió."""
        if numero != self._carga:
            return   # el usuario cambió de sesión mientras se leía
        self._entradas = entradas
        self._recortado = recortado
        self._tamano = tamano
        self._pintar(al_final=al_final)

    def _fallo_de_carga(self, numero: int, mensaje: str) -> None:
        """Avisa de que el archivo no se ha podido leer."""
        if numero != self._carga:
            return
        self.estado.SetLabel(_("No se ha podido leer el registro: %s") % mensaje)

    # -- pintado -------------------------------------------------------------

    def _filtradas(self) -> list[Entrada]:
        """Entradas que pasan el filtro de nivel mínimo."""
        umbral = self.UMBRALES[max(self.filtro.GetSelection(), 0)]
        if umbral is None:
            return list(self._entradas)
        minimo = _ORDEN[umbral]
        return [entrada for entrada in self._entradas
                if _ORDEN.get(entrada.nivel, 1) >= minimo]

    def _pintar(self, anunciar: bool = False, al_final: bool = False) -> None:
        """Vuelca en la lista las entradas que pasan el filtro."""
        self._visibles = self._filtradas()
        self.lista.DeleteAllItems()
        for numero, entrada in enumerate(self._visibles):
            # En la rejilla, un mensaje de varias líneas se muestra en una
            # sola; el texto completo se conserva para leerlo y para copiarlo.
            self.lista.InsertItem(numero, entrada.hora)
            for columna in range(1, len(COLUMNAS)):
                self.lista.SetItem(numero, columna,
                                   entrada.campo(columna).replace("\n", "   ·   "))
        self._actualizar_estado()
        self.boton_vaciar.Enable(self._ruta_actual() is not None)
        if self._visibles:
            fila = len(self._visibles) - 1 if al_final else 0
            self.lista.Select(fila)
            self.lista.Focus(fila)
            self.lista.EnsureVisible(fila)
        if anunciar:
            self._voz.decir(_n("%d entrada.", "%d entradas.", len(self._visibles))
                            % len(self._visibles))

    def _actualizar_estado(self) -> None:
        """Escribe debajo de la lista cuántas entradas hay y de qué archivo."""
        partes = [_("%d entradas de %d") % (len(self._visibles), len(self._entradas))]
        if self._recortado:
            partes.append(_("el archivo ocupa %.1f MB y solo se ha leído el final")
                          % (self._tamano / 1_000_000.0))
        self.estado.SetLabel(". ".join(partes) + ".")

    # -- búsqueda ------------------------------------------------------------

    def _buscar(self, direccion: int) -> None:
        """Busca un texto en las entradas visibles y se coloca en la que salga.

        La búsqueda es circular y mira en todos los campos, que es lo que se
        espera al buscar en un registro: unas veces se busca un módulo, otras
        una hora y otras un trozo del mensaje.
        """
        aguja = (self.busqueda.GetValue() or "").strip().lower()
        if not aguja:
            self._voz.decir(_("Escribe primero lo que quieres buscar."))
            self.busqueda.SetFocus()
            return
        total = len(self._visibles)
        if not total:
            self._voz.decir(_("No hay ninguna entrada donde buscar."))
            return
        desde = self.lista.fila_actual()
        if desde == wx.NOT_FOUND:
            desde = -1 if direccion > 0 else total
        if direccion > 0:
            orden = list(range(desde + 1, total)) + list(range(0, desde + 1))
        else:
            orden = list(range(desde - 1, -1, -1)) + list(range(total - 1, desde - 1, -1))
        for numero in orden:
            entrada = self._visibles[numero]
            if aguja in entrada.como_linea().lower():
                self.lista.SetFocus()
                self.lista.Select(numero)
                self.lista.Focus(numero)
                self.lista.EnsureVisible(numero)
                return
        self._voz.decir(_("No se ha encontrado «%s».") % self.busqueda.GetValue())

    # -- acciones ------------------------------------------------------------

    def _al_copiar(self, evento) -> None:
        """Copia al portapapeles lo que se ve con el filtro puesto."""
        if not self._visibles:
            self._voz.decir(_("No hay nada que copiar con este filtro."))
            return
        texto = "\n".join(entrada.como_linea() for entrada in self._visibles)
        if wx.TheClipboard.Open():
            try:
                wx.TheClipboard.SetData(wx.TextDataObject(texto))
            finally:
                wx.TheClipboard.Close()
            self._voz.decir(_("Copiadas %d entradas al portapapeles.") % len(self._visibles))
        else:
            self._voz.decir(_("No se ha podido usar el portapapeles."))

    def _al_abrir_carpeta(self, evento) -> None:
        """Abre en el explorador la carpeta donde están los registros."""
        rutas.abrir_en_explorador(rutas.ruta_logs())

    def _al_vaciar(self, evento) -> None:
        """Vacía el archivo que se está viendo, tras confirmarlo."""
        ruta = self._ruta_actual()
        if ruta is None:
            return
        aviso = _("¿Seguro que quieres vaciar este archivo de registro?")
        if self._es_la_de_ahora():
            aviso += (_("\n\nEs el de la sesión en curso: se seguirán añadiendo entradas "
                      "nuevas a partir de ahora."))
        if wx.MessageBox(aviso, _("Vaciar el registro"),
                         wx.YES_NO | wx.ICON_QUESTION | wx.NO_DEFAULT, self) != wx.YES:
            return
        try:
            with open(ruta, "w", encoding="utf-8"):
                pass
        except OSError as error:
            wx.MessageBox(_("No se ha podido vaciar el archivo:\n%s") % error,
                          _("Vaciar el registro"), wx.OK | wx.ICON_ERROR, self)
            return
        self._cargar()
        self._voz.decir(_("Archivo de registro vaciado."))

    def _al_cambiar_nivel(self, evento) -> None:
        """Cambia el nivel de detalle que se guarda en disco."""
        nivel = self.nivel_guardado.GetStringSelection() or "INFO"
        self.configuracion.establecer("nivel_registro", nivel)
        self.configuracion.guardar()
        modulo_registro.cambiar_nivel(nivel)
        self._voz.decir(_("A partir de ahora se guardará desde el nivel %s.") % nivel)

    # -- seguimiento en vivo -------------------------------------------------

    def _al_seguir(self, evento) -> None:
        """Activa o desactiva el seguimiento en vivo del registro."""
        if not self.en_vivo.GetValue():
            self._temporizador.Stop()
            self._voz.decir(_("Se deja de seguir el registro."))
            return
        if not self._es_la_de_ahora():
            # Seguir en vivo solo tiene sentido sobre el archivo que se está
            # escribiendo, así que se cambia a él sin más ceremonia.
            self.sesiones.SetSelection(0)
            self._cargar()
        self._temporizador.Start(INTERVALO_VIVO)
        self._voz.decir(_("Siguiendo el registro en vivo."))

    def _al_latir(self, evento) -> None:
        """Relee el archivo y, si hay entradas nuevas, las pinta."""
        if not self._es_la_de_ahora():
            self._temporizador.Stop()
            self.en_vivo.SetValue(False)
            return
        if self._releyendo:
            return   # la relectura anterior todavía no ha terminado
        ruta = self._ruta_actual()
        if ruta is None or not ruta.exists():
            return
        self._releyendo = True

        def trabajo():
            """Relee el archivo fuera del hilo de la interfaz."""
            try:
                texto, recortado, tamano = leer_cola(ruta)
                entradas = trocear(texto)
            except OSError:
                wx.CallAfter(setattr, self, "_releyendo", False)
                return
            wx.CallAfter(self._latido_listo, entradas, recortado, tamano)

        threading.Thread(target=trabajo, name="registro-vivo", daemon=True).start()

    def _latido_listo(self, entradas, recortado: bool, tamano: int) -> None:
        """Pinta lo releído, pero solo si de verdad ha cambiado algo."""
        self._releyendo = False
        if not self.en_vivo.GetValue():
            return
        if len(entradas) == len(self._entradas):
            return   # nada nuevo: no se toca la lista ni se mueve el foco
        self._entradas = entradas
        self._recortado = recortado
        self._tamano = tamano
        self._pintar(al_final=True)

    # -- teclado y cierre ----------------------------------------------------

    def _al_pulsar(self, evento: wx.KeyEvent) -> None:
        """Atajos propios del visor."""
        codigo = evento.GetKeyCode()
        if codigo == wx.WXK_ESCAPE:
            self.Close()
            return
        if codigo == wx.WXK_F3:
            self._buscar(-1 if evento.ShiftDown() else 1)
            return
        if codigo == wx.WXK_F5:
            self._cargar()
            return
        if codigo == ord("F") and evento.ControlDown():
            self.busqueda.SetFocus()
            self.busqueda.SelectAll()
            return
        evento.Skip()

    def _al_cerrar(self, evento) -> None:
        """Para el temporizador y avisa a la ventana principal."""
        self._temporizador.Stop()
        padre = self.GetParent()
        if getattr(padre, "visor_registro", None) is self:
            padre.visor_registro = None
        self.Destroy()
