# -*- coding: utf-8 -*-
"""Elegir del disco un modelo GGUF y su proyector de visión.

Quien se baja un modelo por su cuenta —de Hugging Face, casi siempre— acaba
con uno o dos archivos ``.gguf`` en una carpeta y sin manera de usarlos, porque
Ollama no abre archivos sueltos: trabaja con su propio almacén.  Este diálogo
recoge lo que hay que saber para meterlos ahí.

Son dos archivos y no uno porque un modelo que ve son dos cosas distintas: los
**pesos**, que escriben y razonan, y el **proyector**, que convierte la imagen
en algo que los pesos entiendan.  Vienen sueltos y con nombres que no ayudan
—el proyector suele llamarse ``mmproj-algo.gguf``—, así que aquí se dice cuál
es cuál con todas las letras, y se avisa de que sin el segundo el modelo queda
solo para texto, que en un lector de libros es media herramienta.

La importación de verdad la hace :meth:`nucleo.ia.ollama.Ollama.importar_modelo`;
esto solo pregunta.
"""

from __future__ import annotations

import wx

from interfaz.dialogos import ayuda_opcion
from interfaz.accesible import fila_etiquetada
from nucleo.idioma import _

#: Lo que se ofrece en el explorador de archivos.  Solo GGUF: cualquier otra
#: cosa no le sirve a Ollama, y filtrar aquí evita elegir por error el archivo
#: de pesos original, que pesa cuatro veces más y no vale.
FILTRO = _("Modelos GGUF (*.gguf)|*.gguf|Todos los archivos|*.*")

#: Cómo se suele llamar el proyector.  Sirve para reconocerlo solo y para
#: avisar cuando los dos archivos parecen puestos al revés.
MARCAS_DE_PROYECTOR = ("mmproj", "mm-proj", "projector", "vision-encoder")


class DialogoImportarModelo(wx.Dialog):
    """Pregunta qué archivos importar y con qué nombre guardarlos."""

    def __init__(self, padre: wx.Window) -> None:
        super().__init__(padre, title=_("Importar un modelo del disco"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.ruta_modelo = ""
        self.ruta_vision = ""
        self.nombre = ""

        caja = wx.BoxSizer(wx.VERTICAL)
        caja.Add(wx.StaticText(self, label=_(
            "Se copiará a la IA local del programa y quedará como un modelo más, "
            "elegible en la lista.\n"
            "El archivo original se queda donde está; puedes borrarlo después si "
            "quieres el espacio."
        )), 0, wx.ALL, 10)

        self.campo_modelo = self._fila_de_archivo(
            caja, _("Archivo del &modelo (.gguf):"), self._al_buscar_modelo,
            _("&Buscar el modelo..."))
        caja.Add(wx.StaticText(self, label=_(
            "Son los pesos: el archivo grande, de uno a ocho gigas."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        self.campo_vision = self._fila_de_archivo(
            caja, _("Archivo del &proyector de visión (.gguf), opcional:"),
            self._al_buscar_vision, _("Buscar el pro&yector..."))
        caja.Add(wx.StaticText(self, label=_(
            "Es lo que le permite ver imágenes. Suele llamarse «mmproj-algo.gguf» y "
            "es mucho más\n"
            "pequeño, de unos cientos de megas. Sin él el modelo funciona, pero solo "
            "para texto:\n"
            "no podrá describirte las ilustraciones."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        self.campo_nombre = fila_etiquetada(
            self, caja, _("&Nombre con el que guardarlo:"),
            lambda p: wx.TextCtrl(p), horizontal=True, proporcion=1)
        caja.Add(wx.StaticText(self, label=_(
            "Se propone uno a partir del archivo. Se guarda en minúsculas y sin "
            "acentos, que es\n"
            "como Ollama admite los nombres."
        )), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        botones = wx.StdDialogButtonSizer()
        self.aceptar = wx.Button(self, wx.ID_OK, _("&Importar"))
        self.aceptar.SetDefault()
        self.aceptar.Enable(False)
        botones.AddButton(self.aceptar)
        botones.AddButton(wx.Button(self, wx.ID_CANCEL, _("&Cancelar")))
        botones.Realize()
        caja.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

        self.SetSizerAndFit(caja)
        self.CentreOnParent()
        self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)
        self.campo_modelo.SetFocus()
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    # ------------------------------------------------------------------
    def _fila_de_archivo(self, caja: wx.Sizer, etiqueta: str, manejador,
                         rotulo_boton: str) -> wx.TextCtrl:
        """Una fila con su campo de texto y su botón de buscar.

        El campo se deja editable en vez de ser solo de lectura: quien tenga la
        ruta copiada la pega y se ahorra pasear por el explorador, que con
        lector de pantalla es bastante más lento.
        """
        campo = fila_etiquetada(self, caja, etiqueta,
                                lambda p: wx.TextCtrl(p, size=(420, -1)),
                                proporcion=0)
        campo.Bind(wx.EVT_TEXT, self._al_cambiar)
        boton = wx.Button(self, label=rotulo_boton)
        boton.Bind(wx.EVT_BUTTON, manejador)
        caja.Add(boton, 0, wx.LEFT | wx.BOTTOM, 12)
        return campo

    def _elegir(self, titulo: str) -> str:
        """Abre el explorador y devuelve lo elegido, o cadena vacía."""
        with wx.FileDialog(self, titulo, wildcard=FILTRO,
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dialogo:
            if dialogo.ShowModal() != wx.ID_OK:
                return ""
            return dialogo.GetPath()

    def _al_buscar_modelo(self, evento) -> None:
        elegido = self._elegir(_("Elige el archivo del modelo"))
        if not elegido:
            return
        self.campo_modelo.SetValue(elegido)
        self._proponer_nombre(elegido)
        self._buscar_proyector_al_lado(elegido)

    def _al_buscar_vision(self, evento) -> None:
        elegido = self._elegir(_("Elige el proyector de visión"))
        if elegido:
            self.campo_vision.SetValue(elegido)

    def _al_cambiar(self, evento) -> None:
        """No se deja importar sin modelo."""
        self.aceptar.Enable(bool(self.campo_modelo.GetValue().strip()))
        evento.Skip()

    # ------------------------------------------------------------------
    def _proponer_nombre(self, ruta: str) -> None:
        """Rellena el nombre a partir del archivo, si estaba vacío.

        Se propone y no se impone: si el usuario ya había escrito algo, se
        respeta, porque elegir el archivo después de ponerle nombre es una
        manera perfectamente razonable de hacerlo.
        """
        if self.campo_nombre.GetValue().strip():
            return
        from pathlib import Path

        from nucleo.ia import ollama

        propuesto = ollama._nombre_de_modelo(Path(ruta).stem)
        if propuesto:
            self.campo_nombre.SetValue(propuesto)

    def _buscar_proyector_al_lado(self, ruta: str) -> None:
        """Busca el proyector en la misma carpeta y lo pone si lo encuentra.

        Los dos archivos casi siempre se descargan juntos, así que buscarlo
        ahorra el segundo paseo por el explorador.  Se pone en el campo, a la
        vista y borrable, en vez de usarlo a escondidas.
        """
        if self.campo_vision.GetValue().strip():
            return
        from pathlib import Path

        try:
            vecinos = sorted(Path(ruta).parent.glob("*.gguf"))
        except OSError:
            return
        for vecino in vecinos:
            if str(vecino) == ruta:
                continue
            if any(marca in vecino.name.lower() for marca in MARCAS_DE_PROYECTOR):
                self.campo_vision.SetValue(str(vecino))
                return

    # ------------------------------------------------------------------
    def _al_aceptar(self, evento) -> None:
        """Comprueba lo escrito antes de cerrar."""
        from pathlib import Path

        from nucleo.ia import ollama

        modelo = self.campo_modelo.GetValue().strip().strip('"')
        vision = self.campo_vision.GetValue().strip().strip('"')
        nombre = ollama._nombre_de_modelo(self.campo_nombre.GetValue())

        if not modelo or not Path(modelo).is_file():
            self._avisar(_("No se encuentra el archivo del modelo."), self.campo_modelo)
            return
        if vision and not Path(vision).is_file():
            self._avisar(_("No se encuentra el archivo del proyector."), self.campo_vision)
            return
        if not nombre:
            self._avisar(_("Hace falta un nombre. Puede llevar letras, números, puntos "
                           "y guiones."), self.campo_nombre)
            return

        # Los dos al revés es un error fácil: los nombres se parecen y el
        # proyector aparece antes en la carpeta por orden alfabético.  Se avisa
        # en vez de impedirlo, porque el aviso puede equivocarse y el usuario no.
        if vision and self._parecen_cambiados(Path(modelo), Path(vision)):
            if wx.MessageBox(
                    _("Parece que los dos archivos están cambiados: el que has puesto "
                      "como modelo tiene pinta de ser el proyector.\n\n¿Seguir de todos "
                      "modos?"),
                    _("Importar un modelo"), wx.YES_NO | wx.ICON_QUESTION, self) != wx.YES:
                self.campo_modelo.SetFocus()
                return
        if not vision:
            if wx.MessageBox(
                    _("No has puesto el proyector de visión, así que el modelo no podrá "
                      "describir imágenes: solo servirá para preguntas sobre el texto.\n\n"
                      "¿Importarlo así?"),
                    _("Importar un modelo"), wx.YES_NO | wx.ICON_QUESTION, self) != wx.YES:
                self.campo_vision.SetFocus()
                return

        self.ruta_modelo, self.ruta_vision, self.nombre = modelo, vision, nombre
        evento.Skip()

    @staticmethod
    def _parecen_cambiados(modelo, vision) -> bool:
        """Si el archivo puesto como modelo tiene toda la pinta de proyector."""
        por_el_nombre = (
            any(marca in modelo.name.lower() for marca in MARCAS_DE_PROYECTOR)
            and not any(marca in vision.name.lower() for marca in MARCAS_DE_PROYECTOR))
        try:
            # El proyector es siempre mucho más pequeño que los pesos.
            por_el_tamano = modelo.stat().st_size * 3 < vision.stat().st_size
        except OSError:
            por_el_tamano = False
        return por_el_nombre or por_el_tamano

    def _avisar(self, mensaje: str, donde: wx.Window) -> None:
        """Dice qué falta y deja el foco donde hay que arreglarlo."""
        wx.MessageBox(mensaje, _("Importar un modelo"), wx.OK | wx.ICON_WARNING, self)
        donde.SetFocus()
