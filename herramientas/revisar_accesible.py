# -*- coding: utf-8 -*-
"""Busca controles que el lector de pantalla no sabría nombrar.

Cuando el usuario llega a un control con el tabulador, el lector anuncia su
**nombre accesible**.  Si ese nombre es el de fábrica de wxWidgets —``text``,
``wxSpinButton``, ``panel``— se oye eso literalmente, o no se oye nada útil, y
no hay forma de saber para qué sirve el control.

Es un fallo que **no se ve mirando la pantalla**: la etiqueta está ahí, escrita
al lado, y todo parece correcto.  Solo aparece al recorrer la ventana con el
teclado y un lector de pantalla, y hay que llegar hasta ese control concreto
para notarlo.  De ahí este guion: abre las ventanas del programa, se pone en
cada control enfocable y comprueba qué nombre anunciaría.

El caso que lo motivó fue ``wx.SpinCtrlDouble``.  Por fuera es un control con
su etiqueta bien puesta; por dentro son un cuadro de texto y un par de flechas,
y el foco cae en el cuadro de texto, que se llama ``text`` de fábrica.  El
nombre del contenedor no llegaba a anunciarse nunca.

Se ejecuta así::

    python herramientas/revisar_accesible.py

Devuelve 1 si encuentra alguno.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import wx  # noqa: E402

#: Nombres que pone wxWidgets cuando nadie le ha puesto uno.  Oír cualquiera de
#: estos es lo mismo que no oír nada.
DE_FABRICA = {
    "", "text", "textctrl", "wxspinbutton", "spinbutton", "panel", "button",
    "wxbutton", "choice", "combobox", "checkbox", "radiobutton", "slider",
    "gauge", "listctrl", "listbox", "checklistbox", "treectrl", "notebook",
    "dialog", "frame", "scrolledwindow", "staticbox", "spinctrl",
    "spinctrldouble", "htmlwindow", "webview", "statictext",
}

#: Controles que no necesitan nombre propio porque su etiqueta visible **es**
#: su nombre: un botón se anuncia por lo que pone en él.
CON_ETIQUETA_PROPIA = (wx.Button, wx.CheckBox, wx.RadioButton, wx.ToggleButton)

#: Contenedores, que no se anuncian por su nombre sino por lo que tienen
#: dentro.  Un cuaderno de pestañas anuncia la pestaña elegida, y ponerle un
#: nombre propio lo sustituiría por él en todas: es justo lo que NO hay que
#: hacer, así que aquí tampoco se les exige.
CONTENEDORES = (wx.Notebook, wx.Panel, wx.ScrolledWindow, wx.StaticBox,
                wx.Dialog, wx.Frame, wx.SplitterWindow)


def _enfocables(ventana: wx.Window) -> list[wx.Window]:
    """Todos los controles de una ventana a los que se puede llegar tabulando."""
    encontrados = []
    for hijo in ventana.GetChildren():
        if hijo.AcceptsFocusFromKeyboard():
            encontrados.append(hijo)
        encontrados.extend(_enfocables(hijo))
    return encontrados


def _nombre_al_enfocar(control: wx.Window) -> tuple[str, str]:
    """Enfoca un control y devuelve ``(quién recibe el foco, qué anuncia)``.

    Se mira el control que **de verdad** recibe el foco y no el que se enfocó,
    porque en los controles compuestos no son el mismo y ahí está el problema.
    """
    try:
        control.SetFocus()
        wx.Yield()
    except Exception:
        return type(control).__name__, control.GetName()
    foco = wx.Window.FindFocus() or control
    return type(foco).__name__, foco.GetName()


def revisar_ventana(ventana: wx.Window, titulo: str) -> list[str]:
    """Recorre una ventana y devuelve los controles que no se anunciarían."""
    problemas = []
    for control in _enfocables(ventana):
        if isinstance(control, CON_ETIQUETA_PROPIA + CONTENEDORES):
            continue
        clase, nombre = _nombre_al_enfocar(control)
        if (nombre or "").strip().lower() in DE_FABRICA:
            problemas.append(
                "%s: un %s se anuncia como %r"
                % (titulo, type(control).__name__, nombre))
    return problemas


def main() -> int:
    """Abre las ventanas del programa y las revisa una a una."""
    import shutil

    class SinComprobador:
        """Deja arrancar aunque el programa ya esté abierto."""

        def __init__(self, *args, **argumentos) -> None:
            pass

        def IsAnotherRunning(self) -> bool:      # noqa: N802 (API de wxPython)
            """Nunca hay otra copia, a efectos de esta revisión."""
            return False

    wx.SingleInstanceChecker = SinComprobador
    wx.MessageBox = lambda *args, **argumentos: wx.OK
    # Las teclas globales las tendrá cogidas la copia que esté abierta, y aquí
    # no hacen ninguna falta: se dejan sin registrar para no llenar la salida
    # de avisos que no tienen que ver con lo que se está revisando.
    configuracion_sin_teclas = True

    from formatos import daisy, epub, ofimatica, pdf, texto  # noqa: F401
    from nucleo import rutas
    from nucleo.configuracion import Configuracion
    from sonidos.gestor import GestorSonidos
    from version import VERSION

    ajustes = rutas.ruta_config() / "ajustes.json"
    copia = str(ajustes) + ".revision"
    shutil.copy2(str(ajustes), copia)

    aplicacion = wx.App()
    configuracion = Configuracion()
    if configuracion_sin_teclas:
        configuracion.establecer("teclas_globales_activas", False)
    problemas: list[str] = []
    revisadas = 0
    try:
        from interfaz.ventana import VentanaPrincipal

        ventana = VentanaPrincipal(configuracion, VERSION)
        ventana.Show()
        wx.Yield()

        from interfaz.dialogos.actualizacion import DialogoActualizacion
        from interfaz.dialogos.ayuda import DialogoAcercaDe
        from interfaz.dialogos.buscar import DialogoBuscar
        from interfaz.dialogos.datos import DialogoDatos
        from interfaz.dialogos.diccionario import DialogoDiccionario
        from interfaz.dialogos.idiomas_ocr import DialogoIdiomasOCR
        from interfaz.dialogos.importar_modelo import DialogoImportarModelo
        from interfaz.dialogos.opciones import DialogoOpciones
        from interfaz.dialogos.perfiles import DialogoPerfiles
        from interfaz.dialogos.preguntar import DialogoPreguntar
        from interfaz.dialogos.primer_uso import DialogoPrimerUso
        from interfaz.dialogos.biblioteca import DialogoBiblioteca, DialogoFicha
        from interfaz.dialogos.biblioteca_gestor import (DialogoEditarFuente, DialogoFuentes,
                                                         DialogoResumen)
        from interfaz.listas import DialogoIrA
        from nucleo.biblioteca import Libro
        from nucleo.biblioteca_datos import Fuente
        from interfaz.dialogos.bibliografia import DialogoBibliografia
        from interfaz.dialogos.citar import DialogoCitar
        from interfaz.dialogos.cuaderno import DialogoCuaderno
        from interfaz.dialogos.practica import DialogoPractica
        from interfaz.dialogos.repaso import DialogoRepaso
        from interfaz.dialogos.daisy_exportar import DialogoExportarDaisy
        from interfaz.dialogos.estructura import DialogoEstructura
        from interfaz.dialogos.pronunciacion import DialogoPronunciacion, DialogoRegla
        from interfaz.temporizador import DialogoTemporizador
        from nucleo.correcciones import Correcciones
        from nucleo.documento import Documento, Metadatos
        from nucleo.ia.servicio import Servicio
        from nucleo.voz import Sintetizador

        def _opciones_de_analisis(configuracion):
            """Los ajustes con los que se abren los libros, para la bibliografía."""
            from formatos import base

            return base.OpcionesAnalisis()

        def _apunte_de_prueba():
            """Un apunte mínimo, que es lo que pide la ventana de repaso."""
            from nucleo.cuaderno import Apunte

            return Apunte("Libro", "Autor", "Un pasaje.", "", "10 por ciento",
                          ["tema 1"], 0, "C:/libros/prueba.epub")

        def _documento_de_prueba():
            """Un documento mínimo, que es lo que piden algunas ventanas."""
            return Documento("Capítulo\nUn párrafo.\n", [],
                             metadatos=Metadatos(titulo="Prueba", autor="Autor"),
                             ruta_archivo="C:/libros/prueba.pdf")

        # Las ventanas de estudio necesitan un documento abierto; con la
        # pestaña vacía no hay nada que citar ni que exportar.
        documento_falso = _documento_de_prueba()
        ventana.documento = documento_falso
        ventana.lector.cargar_documento(documento_falso, 0)

        ventanas = [
            (_("Ventana principal"), ventana),
            (_("Opciones"), DialogoOpciones(ventana, configuracion, GestorSonidos())),
            (_("Datos guardados"), DialogoDatos(ventana, configuracion)),
            (_("Idiomas del reconocimiento"), DialogoIdiomasOCR(ventana, configuracion)),
            (_("Acerca de"), DialogoAcercaDe(ventana, VERSION)),
            (_("Buscar"), DialogoBuscar(ventana, configuracion,
                                        lambda *argumentos: True)),
            (_("Diccionario"), DialogoDiccionario(ventana, "", "",
                                                  Servicio(configuracion), configuracion)),
            (_("Diccionario de pronunciación"), DialogoPronunciacion(ventana)),
            (_("Regla de pronunciación"), DialogoRegla(ventana, None, Sintetizador())),
            (_("Temporizador de apagado"), DialogoTemporizador(ventana,
                                                               ventana.temporizador)),
            (_("Actualización"), DialogoActualizacion(ventana, "9.9.9", {})),
            (_("Recorrido guiado"), DialogoPrimerUso(ventana, configuracion)),
            (_("Perfiles de lectura"), DialogoPerfiles(ventana)),
            (_("Preguntar sobre el documento"), DialogoPreguntar(ventana, Servicio(configuracion))),
            (_("Importar un modelo del disco"), DialogoImportarModelo(ventana)),
            (_("Biblioteca"), DialogoBiblioteca(ventana)),
            (_("Bibliotecas y carpetas"), DialogoFuentes(ventana, configuracion)),
            (_("Editar"), DialogoEditarFuente(ventana, Fuente({
                "id": 1, "tipo": "calibre", "ruta": "C:/libros", "nombre": "Prueba",
                "anadida": 0, "actualizada": 0, "libros": 0, "uuid": "",
                "pendiente": 0}))),
            (_("Ficha"), DialogoFicha(ventana, Libro("C:/libros/prueba.epub", "Prueba",
                                                     "Autor"))),
            (_("Ir al elemento"), DialogoIrA(ventana, 2484, 1, "Resultados")),
            (_("Resumen de la importación"), DialogoResumen(
                ventana, _("Resumen de la importación"), "Prueba")),
            (_("Bibliografía"), DialogoBibliografia(
                ventana, [], configuracion, _opciones_de_analisis(configuracion))),
            (_("Copiar con la cita"), DialogoCitar(ventana, documento_falso,
                                                   "un pasaje", 0, configuracion)),
            (_("Exportar a DAISY"), DialogoExportarDaisy(ventana)),
            (_("Cuaderno de estudio"),
             DialogoCuaderno(ventana, [], configuracion)),
            (_("Repasar"), DialogoRepaso(ventana, [_apunte_de_prueba()],
                                         configuracion)),
            (_("Practicar"), DialogoPractica(ventana, configuracion)),
            (_("Revisar la estructura con IA"),
             DialogoEstructura(ventana, documento_falso,
                               Correcciones("huella"), configuracion)),
        ]
        for titulo, objetivo in ventanas:
            revisadas += 1
            if isinstance(objetivo, wx.Dialog):
                objetivo.Show()
                wx.Yield()
            problemas.extend(revisar_ventana(objetivo, titulo))
            if objetivo is not ventana:
                objetivo.Destroy()
                wx.Yield()

        # Las pestañas de las opciones solo construyen sus controles cuando se
        # muestran, así que se recorren una a una aparte.
        opciones = DialogoOpciones(ventana, configuracion, GestorSonidos())
        opciones.Show()
        for numero in range(opciones.cuaderno.GetPageCount()):
            opciones.cuaderno.SetSelection(numero)
            wx.Yield()
            revisadas += 1
            problemas.extend(revisar_ventana(
                opciones.cuaderno.GetPage(numero),
                _("Opciones, pestaña «%s»") % opciones.cuaderno.GetPageText(numero)))
        opciones.Destroy()
        ventana.Destroy()
    finally:
        shutil.move(copia, str(ajustes))

    print("Ventanas revisadas: %d" % revisadas)
    if not problemas:
        print("Sin problemas: todos los controles tienen nombre que anunciar.")
        return 0
    print()
    print("CONTROLES MUDOS (%d):" % len(problemas))
    for problema in sorted(set(problemas)):
        print("  ", problema)
    return 1


def _(texto: str) -> str:
    """Aquí no se traduce nada: esto lo lee quien programa, no el usuario."""
    return texto


if __name__ == "__main__":
    raise SystemExit(main())
