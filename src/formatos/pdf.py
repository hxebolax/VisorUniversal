# -*- coding: utf-8 -*-
"""PDF: los etiquetados, los normales y los escaneados.

El PDF es el formato en el que circula casi toda la literatura académica y
buena parte de los documentos oficiales, y es también donde más se atasca un
lector de pantalla.  Hay tres clases muy distintas, y el analizador las trata
distinto porque no se parecen en nada:

* **PDF etiquetado** (*tagged PDF*, el que exige la norma PDF/UA): además del
  texto trae un árbol de estructura que dice qué es cada cosa —encabezado,
  párrafo, celda de una tabla, punto de una lista, imagen con su descripción—.
  Se lee ese árbol (:mod:`formatos.pdf_etiquetado`) y el documento se navega
  igual que un EPUB.  Es la diferencia entre recorrer un informe de doscientas
  páginas con la tecla H y bajar por él línea a línea.
* **PDF con texto pero sin etiquetar**: el texto está dentro del archivo pero
  no hay ninguna estructura.  Se saca el texto y se deducen los títulos por su
  forma, que es lo único que se puede hacer.
* **PDF escaneado**: son fotografías de las páginas.  No hay texto que sacar;
  hay que **reconocerlo** con OCR (:mod:`formatos.ocr`).

La decisión se toma página a página, no de una vez: es habitual que un libro
tenga las páginas de texto normales y las láminas escaneadas, o al revés, un
escaneado con una portada digital.  Cada página se resuelve por su cuenta.

Se usa **pypdfium2**, que es el motor PDF de Chrome (PDFium) empaquetado para
Python.  Se eligió por tres motivos: hace las tres cosas que hacen falta —sacar
el texto, leer el árbol de estructura y rasterizar la página para el OCR— sin
necesitar ningún programa externo instalado; es rápido; y su licencia es
permisiva (Apache y BSD), al contrario que la de otras bibliotecas de PDF, que
obligarían a cambiar la del programa.
"""

from __future__ import annotations

import ctypes
import os
import re
from pathlib import Path
from typing import NamedTuple

from nucleo import accesibilidad, rutas
from nucleo.correcciones import Correcciones
from nucleo.documento import ElementoIndice, Metadatos
from nucleo.idioma import _
from nucleo.registro import cronometro, obtener_registro, registrar_excepcion

from .base import Analizador, ErrorFormato, OpcionesAnalisis, registrar
from .ensamblador import envolver, escapar, montar, parrafos_de_texto
from .pdf_hallazgos import ColeccionHallazgos, Hallazgo, Severidad

log = obtener_registro(__name__)

#: Con menos caracteres que esto, una página se da por escaneada y se manda al
#: OCR.  No es cero a propósito: muchas páginas escaneadas llevan un número de
#: página o una marca de agua en texto de verdad, y eso no las hace legibles.
MINIMO_TEXTO = 40

#: Aumento con el que se rasteriza una página para reconocerla.  A 2 la página
#: sale a unos 200 puntos por pulgada, que es el punto donde el OCR deja de
#: mejorar y el consumo de memoria empieza a doler.
ESCALA_OCR = 2.0

#: Aumento con el que se recorta una figura de un PDF etiquetado para verla o
#: para describirla con inteligencia artificial.  Es más alto que el del OCR
#: porque una figura suele ser un gráfico con letra pequeña.
ESCALA_FIGURA = 3.0

#: Encabezados detectados por su forma cuando el PDF no marca ninguno: línea
#: corta, suelta y sin punto final.  Es una heurística, pero es lo que
#: convierte un PDF sin etiquetar en algo que se puede recorrer con la tecla H.
_LARGO_TITULO = 70

#: Cuántas páginas se miran, repartidas por todo el documento, para decidir si
#: su etiquetado sirve.  Con una docena basta: un PDF o está etiquetado de
#: principio a fin —lo hace el programa que lo genera— o no lo está.
_MUESTRA_ESTRUCTURA = 12

#: Referencia con la que se guarda el recorte de una figura de un PDF.
_FIGURA = re.compile(r"^pdf-figura:(\d+):(-?[\d.]+),(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)$")

#: Franja de caracteres en la que no está claro si una página tiene texto de
#: verdad.  Por debajo de :data:`MINIMO_TEXTO` seguro que no; por encima de
#: esto, seguro que sí.  En medio están las páginas escaneadas que traen un
#: número de página o una marca de agua en texto real, y son las únicas para
#: las que merece la pena la comprobación cara de mirar **dónde** cae ese
#: texto (:func:`formatos.pdf_diagnostico.clasificar_pagina`).
DUDA_TEXTO = 400


class _Apertura(NamedTuple):
    """El PDF ya abierto y todo lo que se ha averiguado al abrirlo.

    :param documento: Documento de PDFium, listo para leer.
    :param ruta: Archivo del que se está leyendo de verdad, que puede ser una
                 copia reparada y no el que eligió el usuario.
    :param diagnostico: Inventario técnico del archivo.
    :param temporal: Copia reparada que hay que borrar al terminar, si la hay.
    """

    documento: object
    ruta: Path
    diagnostico: object
    temporal: Path | None = None


class Etiquetado:
    """Lo que se sabe del etiquetado de un PDF: si lo tiene y si sirve.

    Es también el informe de accesibilidad que se anota en el registro al
    abrir el documento, y lo que decide por qué camino se lee.
    """

    __slots__ = ("marcado", "idioma", "paginas_con_arbol", "paginas_miradas",
                 "cobertura", "etiquetas", "pares", "figuras", "figuras_sin_alt", "idiomas",
                 "usar", "desactivado")

    def __init__(self) -> None:
        self.desactivado = False
        self.marcado = False
        self.idioma = ""
        self.paginas_con_arbol = 0
        self.paginas_miradas = 0
        self.cobertura = 0.0
        self.etiquetas: dict[str, int] = {}
        #: Cuántas veces cuelga cada etiqueta de cada otra en todo el documento.
        self.pares: dict[tuple, int] = {}
        self.figuras = 0
        self.figuras_sin_alt = 0
        self.idiomas: dict[str, int] = {}
        self.usar = False

    def resumen(self) -> str:
        """Frase para el registro y para la información del documento."""
        if self.desactivado:
            return (_("Estructura del PDF desactivada en las opciones.") if self.marcado
                    else _("PDF sin etiquetar: no trae estructura de accesibilidad."))
        if not self.paginas_con_arbol:
            if self.marcado:
                return _("El PDF se declara etiquetado pero no trae árbol de estructura.")
            return _("PDF sin etiquetar: no trae estructura de accesibilidad.")
        partes = [
            _("PDF etiquetado: %d de %d páginas con estructura")
            % (self.paginas_con_arbol, self.paginas_miradas),
            _("cobertura del texto %d %%") % round(self.cobertura * 100),
        ]
        if self.idioma:
            partes.append(_("idioma del documento: %s") % self.idioma)
        elif self.marcado:
            partes.append(_("sin idioma declarado"))
        if self.idiomas:
            partes.append(_("idiomas declarados: %s")
                          % ", ".join(sorted(self.idiomas, key=self.idiomas.get, reverse=True)))
        if not self.usar:
            partes.append(_("estructura descartada por incompleta"))
        return "; ".join(partes) + "."


class AnalizadorPDF(Analizador):
    """Documentos PDF, con o sin estructura y con o sin texto."""

    extensiones = (".pdf",)
    descripcion = _("Documentos PDF")

    #: Servicio de IA que se usará para el OCR.  Lo pone la ventana antes de
    #: abrir el libro; si es ``None`` solo queda el OCR de Windows.
    servicio_ia = None

    #: Con qué se reconocen las páginas escaneadas: «auto», «ia», «windows» o
    #: «ninguno» (:data:`formatos.ocr.MODOS`).  Lo pone la ventana al abrir el
    #: libro, leyéndolo de las opciones.
    ocr_modo = "auto"

    #: Idiomas de Tesseract, separados por «+».  Vacio deja que se elijan solos
    #: entre los instalados.
    ocr_idiomas = ""

    #: Ajustes completos del reconocimiento.  Los pone la ventana al abrir; si
    #: no hay ninguno se usan los de fábrica.
    ocr_ajustes = None

    #: Cuántas páginas como mucho se reconocen en un PDF (0 = sin tope).
    ocr_maximo = 100

    #: Contraseña con la que abrir un PDF cifrado.  La pone la ventana cuando
    #: se la ha pedido al usuario.
    contrasena = ""

    #: Informe del último documento abierto, para la ventana de información.
    ultimo_etiquetado: Etiquetado | None = None

    #: Diagnóstico técnico del último documento abierto.
    ultimo_diagnostico = None

    #: Hallazgos de accesibilidad del último documento abierto.
    ultimos_hallazgos: ColeccionHallazgos | None = None

    #: Correcciones del último documento abierto, para que la ventana pueda
    #: añadir más sin volver a cargarlas.
    ultimas_correcciones: Correcciones | None = None

    #: Deducir la estructura de la maquetación en los PDF sin etiquetar
    #: (:mod:`formatos.pdf_geometria`).  Lo pone la ventana desde las opciones.
    geometria = True

    #: Función ``(ruta, intento) -> contraseña`` con la que pedirle al usuario
    #: la contraseña de un PDF cifrado.  La pone la ventana; devolver una
    #: cadena vacía o ``None`` cancela la apertura.  Sin ella, un PDF que
    #: necesite contraseña sencillamente no se abre.
    pedir_contrasena = None

    def analizar(self, ruta, opciones: OpcionesAnalisis):
        """Convierte el PDF a texto, aprovechando todo lo que el archivo traiga."""
        destino = Path(ruta)
        self.ultimo_diagnostico = None
        self.ultimos_hallazgos = None
        self.ultimas_correcciones = None
        apertura = self._preparar(destino, opciones)
        documento = apertura.documento
        diagnostico = apertura.diagnostico
        self.ultimo_diagnostico = diagnostico
        correcciones = Correcciones.cargar(getattr(diagnostico, "huella", ""))
        self.ultimas_correcciones = correcciones

        try:
            total = len(documento)
            if not total:
                raise ErrorFormato(_("El PDF no tiene ninguna página."))
            metadatos = self._metadatos(documento, destino)
            etiquetado = self._explorar(documento, total, opciones)
            self.ultimo_etiquetado = etiquetado
            log.info("%s", etiquetado.resumen())
            secciones, reconocidas = self._paginas(
                documento, total, opciones, etiquetado, apertura, correcciones)
            marcadores = self._marcadores(documento)
        finally:
            try:
                documento.close()
            except Exception:
                pass
            self._limpiar_temporal(apertura)

        if not secciones:
            if self.ocr_modo in ("ninguno", "grafico"):
                from . import ocr
                raise ErrorFormato(ocr.motivo_sin_ocr(self.ocr_modo))
            raise ErrorFormato(_(
                "El PDF no contiene texto legible y no se ha podido reconocer ninguna página."))
        if reconocidas:
            log.info("PDF: %d de %d páginas reconocidas con OCR", reconocidas, total)
        if etiquetado.idioma:
            metadatos.idioma = etiquetado.idioma
        self._aplicar_correcciones_documento(metadatos, correcciones)

        libro = montar(secciones, metadatos, destino, opciones)
        indice = self._indice(marcadores, libro)
        if indice:
            # El índice propio del PDF —sus marcadores— es el que hizo quien
            # escribió el documento, así que manda sobre el que se deduciría
            # de los encabezados.  En un informe de trescientas páginas es la
            # diferencia entre un índice de verdad y una lista de titulillos.
            libro.indice = indice
        # El informe se redacta al final, cuando el índice ya es el definitivo:
        # antes contaría los encabezados en lugar de los marcadores del PDF.
        metadatos.accesibilidad = self._informe(libro, etiquetado, diagnostico,
                                                correcciones)
        return libro

    # -- apertura ------------------------------------------------------------

    def _preparar(self, destino: Path, opciones: OpcionesAnalisis) -> _Apertura:
        """Diagnostica, descifra y abre el PDF, reparándolo si hace falta.

        Es donde se resuelven los dos motivos por los que un PDF perfectamente
        legible se quedaba sin abrir:

        * **La contraseña.**  Un PDF puede llevar dos, y solo una impide leer
          (véase :class:`formatos.pdf_diagnostico.Cifrado`).  La de propietario
          se salta sola; la de usuario se le pide a quien abre el documento.
        * **El índice roto.**  Se abre desde una copia reparada
          (:mod:`formatos.pdf_reparacion`) sin tocar el original.
        """
        from . import pdf_diagnostico as diag

        pdfium = self._motor()
        contrasena = self.contrasena or ""
        cifrado, lector = diag.cifrado_de(destino, contrasena)
        intento = 0
        while cifrado is diag.Cifrado.USUARIO:
            nueva = self._solicitar_contrasena(destino, intento)
            if not nueva:
                raise ErrorFormato(_(
                    "Este PDF está cifrado y hace falta una contraseña para leerlo."))
            contrasena = nueva
            intento += 1
            cifrado, lector = diag.cifrado_de(destino, contrasena)
        self.contrasena = contrasena
        informe = diag.diagnosticar(destino, contrasena, lector)
        informe.cifrado = cifrado

        documento = self._abrir(pdfium, destino, tolerar=True)
        if documento is not None and not self._necesita_reparacion(destino, informe):
            return _Apertura(documento, destino, informe)

        copia = self._reparar(destino, documento is None)
        if copia is None:
            if documento is not None:
                return _Apertura(documento, destino, informe)
            raise ErrorFormato(_("El PDF está dañado y no se ha podido reparar."))
        reparado = self._abrir(pdfium, copia, tolerar=True)
        if reparado is None:
            self._borrar(copia)
            if documento is not None:
                return _Apertura(documento, destino, informe)
            raise ErrorFormato(_("El PDF está dañado y no se ha podido reparar."))
        if documento is not None:
            try:
                documento.close()
            except Exception:
                pass
        from . import pdf_reparacion

        informe.reparado = True
        informe.hallazgos.anadir(pdf_reparacion.hallazgo_reparado(bool(informe.firmas)))
        del opciones
        return _Apertura(reparado, copia, informe, copia)

    def _solicitar_contrasena(self, destino: Path, intento: int) -> str:
        """Le pide la contraseña al usuario, si hay quien se la pueda pedir."""
        if self.pedir_contrasena is None:
            return ""
        try:
            return (self.pedir_contrasena(destino, intento) or "").strip()
        except Exception as error:
            registrar_excepcion(log, "Error pidiendo la contraseña del PDF", error)
            return ""

    @staticmethod
    def _necesita_reparacion(destino: Path, informe) -> bool:
        """Decide si conviene trabajar sobre una copia reparada.

        PDFium abre casi cualquier cosa, así que «se ha abierto» no basta: el
        motivo para reparar no es que el archivo no se abra, es que su índice
        roto impida **medirlo** con pdfminer, y con ello se pierdan los
        encabezados y las tablas de los PDF sin etiquetar.  Por eso solo se
        repara cuando además hace falta la geometría.
        """
        from . import pdf_reparacion

        if getattr(informe, "danado", False):
            return True
        if getattr(informe, "arbol_logico", False):
            # Con estructura propia no se usa la geometría, así que un índice
            # roto no molesta y no hay razón para escribir una copia.
            return False
        return pdf_reparacion.parece_roto(destino)

    def _reparar(self, destino: Path, imprescindible: bool):
        """Escribe una copia reparada en la carpeta temporal del programa."""
        from . import pdf_reparacion

        try:
            copia = rutas.ruta_temp() / ("reparado-%s.pdf" % destino.stem[:60])
            return pdf_reparacion.reparar(destino, copia)
        except Exception as error:
            registrar_excepcion(log, "No se ha podido reparar el PDF", error)
            if imprescindible:
                raise ErrorFormato(_("El PDF está dañado y no se ha podido reparar."))
            return None

    def _limpiar_temporal(self, apertura: _Apertura) -> None:
        """Borra la copia reparada, que solo hacía falta mientras se leía."""
        if apertura.temporal is not None:
            self._borrar(apertura.temporal)

    @staticmethod
    def _borrar(ruta: Path) -> None:
        """Borra un archivo sin protestar si ya no está."""
        try:
            ruta.unlink()
        except OSError:
            pass

    @staticmethod
    def _motor():
        """Importa pypdfium2 y explica qué hacer si no está."""
        try:
            import pypdfium2 as pdfium
        except ImportError:
            raise ErrorFormato(_(
                "Para abrir archivos PDF hace falta el complemento «pypdfium2», que no está "
                "instalado. Instálalo con: pip install pypdfium2"))
        return pdfium

    def _abrir(self, pdfium, destino: Path, tolerar: bool = False):
        """Abre el PDF, distinguiendo el archivo dañado del protegido.

        Un PDF puede estar cifrado de dos maneras muy distintas y conviene no
        confundirlas: con **contraseña de propietario**, que solo limita
        imprimir o copiar y se abre igual —es el caso de casi todos los
        documentos «protegidos» que circulan—, o con **contraseña de usuario**,
        que sí hace falta para leerlo.  Solo la segunda impide abrirlo.

        :param tolerar: Devolver ``None`` en lugar de fallar.  Lo usa la
                        apertura, que ante un archivo dañado todavía tiene una
                        carta que jugar: repararlo.
        """
        try:
            return pdfium.PdfDocument(str(destino), password=self.contrasena or None)
        except Exception as error:
            mensaje = str(error).lower()
            if "password" in mensaje or "contrase" in mensaje:
                raise ErrorFormato(_(
                    "Este PDF está cifrado y hace falta una contraseña para leerlo."))
            if tolerar:
                log.info("PDFium no ha podido abrir %s: %s", destino.name, error)
                return None
            raise ErrorFormato(_("El PDF está dañado o no se puede abrir: %s") % error)

    # -- estructura ----------------------------------------------------------

    def _explorar(self, documento, total: int, opciones: OpcionesAnalisis) -> Etiquetado:
        """Mira unas cuantas páginas para decidir si el etiquetado sirve.

        Un árbol de estructura no garantiza nada por sí solo: hay PDF con un
        árbol de adorno que deja fuera medio documento, y usarlo perdería
        texto.  La comprobación es cuánto del texto de la página cae dentro del
        árbol; si no llega al mínimo, se lee el PDF como si no estuviera
        etiquetado, que es peor de navegar pero no pierde nada.
        """
        from . import pdf_etiquetado

        informe = Etiquetado()
        informe.marcado = pdf_etiquetado.esta_marcado(documento.raw)
        informe.idioma = pdf_etiquetado.idioma_del_documento(documento.raw)
        if not opciones.estructura_pdf:
            informe.desactivado = True
            return informe

        paso = max(1, total // _MUESTRA_ESTRUCTURA)
        del_arbol = 0
        de_la_pagina = 0
        for numero in range(0, total, paso):
            informe.paginas_miradas += 1
            try:
                pagina = documento[numero]
                pagina_texto = pagina.get_textpage()
                resultado = pdf_etiquetado.convertir_pagina(
                    documento.raw, pagina.raw, pagina_texto.raw, numero + 1,
                    informe.idioma)
                llano = pagina_texto.get_text_bounded() or ""
            except Exception as error:
                registrar_excepcion(
                    log, "Error explorando la estructura de la página %d" % (numero + 1), error)
                continue
            if resultado is None:
                continue
            informe.paginas_con_arbol += 1
            del_arbol += resultado.caracteres
            de_la_pagina += len(llano.strip())
        if de_la_pagina:
            informe.cobertura = del_arbol / de_la_pagina
        elif informe.paginas_con_arbol:
            # Páginas sin texto (portadas, láminas): el árbol no tiene nada que
            # cubrir y no hay motivo para desconfiar de él.
            informe.cobertura = 1.0
        informe.usar = (informe.paginas_con_arbol > 0
                        and informe.cobertura >= pdf_etiquetado.COBERTURA_MINIMA)
        return informe

    # -- páginas -------------------------------------------------------------

    def _paginas(self, documento, total: int, opciones: OpcionesAnalisis,
                 etiquetado: Etiquetado, apertura: _Apertura,
                 correcciones: Correcciones):
        """Convierte cada página, con OCR cuando hace falta.

        Se cuenta el avance página a página: en un PDF escaneado esto tarda
        minutos, y sin decir por dónde va sería un silencio en el que no se
        sabe si el programa trabaja o se ha colgado.

        El orden en que se prueban los tres caminos no es negociable, porque va
        del más fiable al menos:

        1. **La estructura etiquetada**, cuando el archivo la trae y sirve.  Es
           lo que dijo el autor.
        2. **La geometría** (:mod:`formatos.pdf_geometria`), que deduce
           encabezados y tablas de cómo está escrita la página.
        3. **El reconocimiento óptico**, que es lo único que queda cuando la
           página es una fotografía.

        :return: ``(secciones, cuántas se reconocieron con OCR)``.
        """
        from . import ocr

        progreso = opciones.progreso
        secciones = []
        reconocidas = 0
        sin_ocr_avisado = False
        tope_avisado = False
        medidor = self._abrir_medidor(total, opciones, etiquetado, apertura)
        try:
            with cronometro(log, "conversion de las paginas del PDF"):
                for numero in range(total):
                    progreso.paso(numero, total,
                                  _("Página %d de %d") % (numero + 1, total))
                    texto, estructurado = self._leer_pagina(documento, numero, etiquetado)
                    if not estructurado:
                        estructurado = self._por_geometria(
                            medidor, numero + 1, self._enlaces(documento, numero))

                    if (self.ocr_modo == "grafico"
                            and self._necesita_ocr(documento, numero, texto,
                                                   estructurado)):
                        # El usuario ha pedido ver el documento tal cual está.
                        # La página se deja como una imagen: no se reconoce
                        # nada, no se inventa ningún orden de lectura, y lo que
                        # hay se puede ver con Control+I y describir con la
                        # inteligencia artificial, que en un cómic o un manga
                        # es lo único que de verdad ayuda.
                        estructurado = self._pagina_como_imagen(documento, numero)
                        texto = ""
                    elif self._necesita_ocr(documento, numero, texto, estructurado) \
                            and self.ocr_modo != "ninguno":
                        if self.ocr_maximo and reconocidas >= self.ocr_maximo:
                            if not tope_avisado:
                                log.warning(
                                    "Se ha alcanzado el tope de %d páginas reconocidas",
                                    self.ocr_maximo)
                                tope_avisado = True
                            if not texto.strip():
                                continue
                        progreso.paso(
                            numero, total,
                            _("Reconociendo la página %d de %d...") % (numero + 1, total))
                        try:
                            reconocido = self._reconocer(documento, numero)
                        except RuntimeError as error:
                            if not sin_ocr_avisado:
                                log.warning("Sin OCR disponible: %s", error)
                                sin_ocr_avisado = True
                            reconocido = None
                        except Exception as error:
                            registrar_excepcion(
                                log, "Error reconociendo la página %d" % (numero + 1), error)
                            reconocido = None
                        if reconocido is not None and len(reconocido) > len(texto.strip()):
                            texto = reconocido.texto
                            # Si el motor ha sabido reconstruir la disposición, se
                            # usa su XHTML tal cual: es lo que conserva las tablas
                            # y el orden de lectura, que se perderían al volver a
                            # deducirlos del texto ya aplanado.
                            estructurado = reconocido.html
                            reconocidas += 1

                    if not estructurado and not texto.strip():
                        continue
                    cuerpo = estructurado or self._estructurar(texto)
                    cuerpo = correcciones.corregir_pagina(cuerpo, numero + 1)
                    if not cuerpo.strip():
                        # El usuario ha marcado como artefacto todo lo que había
                        # en la página.  La marca de página sí se conserva: sin
                        # ella, «Ir a la página» dejaría de encontrarla.
                        cuerpo = ""
                    cuerpo = self._marca_de_pagina(documento, numero) + cuerpo
                    secciones.append((_("página %s") % (numero + 1), envolver(cuerpo)))
        finally:
            self._cerrar_medidor(medidor)
        if sin_ocr_avisado and not secciones:
            raise ErrorFormato(ocr.motivo_sin_ocr(self.ocr_modo))
        return secciones, reconocidas

    # -- geometría -----------------------------------------------------------

    def _abrir_medidor(self, total: int, opciones: OpcionesAnalisis,
                       etiquetado: Etiquetado, apertura: _Apertura):
        """Prepara la medida de la maquetación, si toca y si se puede.

        Solo toca cuando **no** hay estructura etiquetada utilizable.  Cuando
        la hay, ya se sabe qué es cada cosa por el camino bueno y medirlo otra
        vez sería gastar medio segundo por página para llegar a una conclusión
        peor.

        :return: ``(documento medido, contexto)`` o ``None``.
        """
        from . import pdf_geometria

        if etiquetado.usar or not self.geometria or not opciones.geometria_pdf:
            return None
        if not pdf_geometria.disponible():
            log.debug("Sin pdfplumber: no se deducirá la estructura de la maquetación.")
            return None
        with cronometro(log, "medida de la maquetacion del PDF"):
            medido = pdf_geometria.abrir(apertura.ruta, self.contrasena)
            temporal = None
            if medido is None:
                # PDFium ha abierto el archivo reconstruyendo su índice por su
                # cuenta, pero pdfminer es estricto y se niega.  Es exactamente
                # el caso para el que existe la reparación: el contenido está
                # entero y lo que falta es el mapa.  Se intenta aquí, y no
                # antes, para no escribir una copia de todos los archivos que
                # simplemente no necesitan geometría.
                temporal = self._reparar(apertura.ruta, imprescindible=False)
                if temporal is None:
                    log.info("El PDF no se puede medir y no se ha podido reparar.")
                    return None
                medido = pdf_geometria.abrir(temporal, self.contrasena)
                if medido is None:
                    self._borrar(temporal)
                    return None
                log.info("La estructura se deducirá desde una copia reparada del PDF.")
                self._anotar_reparacion(apertura.diagnostico)
            try:
                contexto = pdf_geometria.medir_documento(medido, total)
            except Exception as error:
                registrar_excepcion(log, "Error midiendo la maquetación del PDF", error)
                pdf_geometria.cerrar(medido)
                if temporal is not None:
                    self._borrar(temporal)
                return None
        if not contexto.cuerpo and not contexto.hay_dibujos:
            # Ni una letra ni un trazo en toda la muestra: es un escaneado, y lo
            # que va a resolverlo es el reconocimiento óptico.  Medir cada
            # página para no sacar nada de ninguna cuesta medio segundo cada
            # diez, que en un libro escaneado de quinientas páginas son
            # veinticinco segundos regalados.
            #
            # Se exige que **tampoco** haya dibujos, y no solo que falte el
            # texto: un PDF hecho solo de imágenes no tiene tamaño de letra
            # ninguno y sin esa condición se quedaría sin que se le encontraran
            # las figuras, que es lo único que tiene y lo que se puede describir
            # con inteligencia artificial.
            log.info("El PDF no tiene texto ni dibujos que medir: la estructura "
                     "saldrá del reconocimiento óptico.")
            pdf_geometria.cerrar(medido)
            if temporal is not None:
                self._borrar(temporal)
            return None
        log.info("Estructura deducida de la maquetación: cuerpo %.1f pt, %d niveles "
                 "de título, %d líneas repetidas",
                 contexto.cuerpo, len(contexto.escala), len(contexto.artefactos))
        return medido, contexto, temporal

    @staticmethod
    def _anotar_reparacion(diagnostico) -> None:
        """Deja constancia de que se ha trabajado sobre una copia reparada."""
        from . import pdf_reparacion

        if diagnostico is None:
            return
        diagnostico.reparado = True
        diagnostico.hallazgos.anadir(
            pdf_reparacion.hallazgo_reparado(bool(getattr(diagnostico, "firmas", 0))))

    @staticmethod
    def _por_geometria(medidor, numero: int, enlaces=()) -> str:
        """Deduce la estructura de una página a partir de cómo está escrita."""
        if medidor is None:
            return ""
        from . import pdf_geometria

        medido, contexto, _temporal = medidor
        try:
            pagina = pdf_geometria.leer_pagina(medido, numero, enlaces)
            if pagina is None:
                return ""
            return pdf_geometria.estructurar(pagina, contexto)
        except Exception as error:
            registrar_excepcion(
                log, "Error deduciendo la estructura de la página %d" % numero, error)
            return ""

    @staticmethod
    def _enlaces(documento, numero: int):
        """Lee los enlaces de una página con PDFium.

        Los saca PDFium y no pdfminer porque solo PDFium resuelve a qué página
        lleva un enlace interno, que es lo que convierte el índice de un
        informe en un índice que salta de verdad.
        """
        from . import pdf_etiquetado

        try:
            pagina = documento[numero]
        except Exception:
            return ()
        try:
            return pdf_etiquetado.enlaces_de_pagina(documento.raw, pagina.raw)
        except Exception as error:
            log.debug("No se han podido leer los enlaces de la página %d: %s",
                      numero + 1, error)
            return ()

    def _cerrar_medidor(self, medidor) -> None:
        """Cierra el documento de medida y borra la copia reparada, si la hubo."""
        if medidor is None:
            return
        from . import pdf_geometria

        pdf_geometria.cerrar(medidor[0])
        if medidor[2] is not None:
            self._borrar(medidor[2])

    # -- reconocimiento óptico -----------------------------------------------

    def _necesita_ocr(self, documento, numero: int, texto: str,
                      estructurado: str) -> bool:
        """Decide si una página hay que reconocerla.

        Contar caracteres, que es lo que se hacía, se equivoca en el caso más
        frecuente: una página escaneada casi siempre trae texto de verdad —el
        número de página, el sello de la biblioteca que la digitalizó, una
        marca de agua— y con eso ya supera el mínimo y se queda sin reconocer.
        El usuario recibe una página en la que solo se lee «118».

        Cuando la cantidad de texto es dudosa se mira **dónde** cae: si el
        cuerpo de la página está vacío y todo lo que hay son marcas de los
        márgenes, la página es una fotografía por muchos caracteres que tenga.
        La comprobación cara se hace solo en esa franja de duda, que es donde
        aporta algo.
        """
        if estructurado.strip():
            return False
        largo = len(texto.strip())
        if largo >= DUDA_TEXTO:
            return False
        if largo < MINIMO_TEXTO:
            return True
        return not self._texto_en_el_cuerpo(documento, numero)

    @staticmethod
    def _texto_en_el_cuerpo(documento, numero: int) -> bool:
        """Comprueba si queda texto al descartar los márgenes de la página."""
        from . import pdf_diagnostico as diag

        try:
            pagina = documento[numero]
            ancho, alto = pagina.get_size()
            pagina_texto = pagina.get_textpage()
        except Exception:
            return True
        try:
            cajas = []
            for indice in range(min(int(pagina_texto.count_rects()), 2000)):
                izquierda, abajo, derecha, arriba = pagina_texto.get_rect(indice)
                trozo = pagina_texto.get_text_bounded(izquierda, abajo, derecha, arriba) or ""
                cajas.append((diag.Caja(izquierda, abajo, derecha, arriba),
                              len(trozo.strip())))
        except Exception:
            return True
        finally:
            try:
                pagina_texto.close()
            except Exception:
                pass
        clase, _dentro = diag.clasificar_pagina(cajas, 0.0, ancho, alto)
        return clase in (diag.ClasePagina.DIGITAL, diag.ClasePagina.HIBRIDA)

    def _leer_pagina(self, documento, numero: int, etiquetado: Etiquetado):
        """Saca de una página su texto y, si la hay, su estructura ya en XHTML.

        :return: ``(texto plano, XHTML de la estructura o cadena vacía)``.
        """
        try:
            pagina = documento[numero]
            pagina_texto = pagina.get_textpage()
            texto = pagina_texto.get_text_bounded() or ""
        except Exception as error:
            registrar_excepcion(log, "Error leyendo la página %d" % (numero + 1), error)
            return "", ""
        if not etiquetado.usar:
            return texto, ""
        from . import pdf_etiquetado

        try:
            resultado = pdf_etiquetado.convertir_pagina(
                documento.raw, pagina.raw, pagina_texto.raw, numero + 1,
                etiquetado.idioma)
        except Exception as error:
            registrar_excepcion(
                log, "Error leyendo la estructura de la página %d" % (numero + 1), error)
            return texto, ""
        if resultado is None or not resultado.cuerpo.strip():
            return texto, ""
        for etiqueta, cuantas in resultado.etiquetas.items():
            etiquetado.etiquetas[etiqueta] = etiquetado.etiquetas.get(etiqueta, 0) + cuantas
        for par, cuantas in resultado.pares.items():
            etiquetado.pares[par] = etiquetado.pares.get(par, 0) + cuantas
        etiquetado.figuras += resultado.figuras
        etiquetado.figuras_sin_alt += resultado.figuras_sin_alt
        for codigo, cuantas in resultado.idiomas.items():
            etiquetado.idiomas[codigo] = etiquetado.idiomas.get(codigo, 0) + cuantas
        return texto, resultado.cuerpo

    def _pagina_como_imagen(self, documento, numero: int) -> str:
        """Devuelve la página entera escrita como una imagen.

        Se usa la misma referencia que las figuras —la página con su rectángulo
        completo—, de modo que ver la página, guardarla y describirla con la
        inteligencia artificial funcionan sin escribir nada nuevo: son los
        caminos que ya estaban hechos.
        """
        try:
            pagina = documento[numero]
            ancho, alto = pagina.get_size()
        except Exception as error:
            log.debug("No se ha podido medir la página %d: %s", numero + 1, error)
            return ""
        referencia = "pdf-figura:%d:0.00,0.00,%.2f,%.2f" % (numero + 1, ancho, alto)
        return '<img src="%s" alt="%s"/>' % (
            escapar(referencia), escapar(_("Página %d") % (numero + 1)))

    @staticmethod
    def _marca_de_pagina(documento, numero: int) -> str:
        """Ancla y salto de página que se ponen al principio de cada página.

        Es lo que da tres cosas de golpe: la marca de página con la que
        funciona «Ir a la página», el ancla ``#pagina-N`` a la que apuntan los
        enlaces internos y el índice del propio PDF, y el rótulo correcto
        cuando el documento numera el prólogo en romanos.

        Se escribe con ``role="doc-pagebreak"``, que es como lo dicen las
        recomendaciones de accesibilidad de la web y lo que el conversor ya
        entiende de los EPUB 3.
        """
        rotulo = _rotulo_de_pagina(documento, numero) or str(numero + 1)
        return ('<span role="doc-pagebreak" id="pagina-%d" title="%s"></span>'
                % (numero + 1, escapar(rotulo)))

    # -- informe y correcciones ----------------------------------------------

    @staticmethod
    def _aplicar_correcciones_documento(metadatos: Metadatos,
                                        correcciones: Correcciones) -> None:
        """Deja que el usuario mande sobre el título y el idioma del documento.

        Los dos son datos que el archivo puede traer mal y que cambian mucho la
        lectura: un idioma equivocado hace que la voz lea un texto en español
        con acento inglés, y un título vacío o con el nombre del archivo hace
        que la lista de libros no se pueda recorrer.
        """
        metadatos.huella = correcciones.huella
        if correcciones.titulo:
            metadatos.titulo = correcciones.titulo
        if correcciones.idioma:
            metadatos.idioma = correcciones.idioma

    def _informe(self, libro, etiquetado: Etiquetado, diagnostico,
                 correcciones: Correcciones) -> str:
        """Redacta lo que se le cuenta al usuario sobre este documento.

        Son tres capas distintas y se dicen en este orden porque es el de menos
        a más detalle:

        1. Lo que el archivo **es** —etiquetado o no, cifrado, reparado—.
        2. Lo que **trae** para poder recorrerlo, que es lo que ya contaba
           :mod:`nucleo.accesibilidad` y vale igual para todos los formatos.
        3. Lo que le **falta**, con su remedio, que es la parte nueva.
        """
        from . import pdf_auditoria

        hallazgos = pdf_auditoria.auditar(diagnostico, etiquetado, libro)
        if diagnostico is not None:
            hallazgos.extender(diagnostico.hallazgos)
        self.ultimos_hallazgos = hallazgos
        for hallazgo in hallazgos.de_severidad(Severidad.AVISO):
            log.info("PDF: %s", hallazgo.redactar(con_norma=True))

        delante = etiquetado.resumen()
        tecnico = diagnostico.resumen() if diagnostico is not None else ""
        if tecnico:
            delante = ("%s %s" % (delante, tecnico)).strip()
        partes = [accesibilidad.resumen(libro, delante)]
        pendientes = hallazgos.redactar(maximo=6, minima=Severidad.AVISO,
                                        con_norma=False)
        if pendientes:
            partes.append(_("Lo que falta:"))
            partes.append(pendientes)
        if correcciones:
            partes.append(correcciones.resumen())
        return "\n".join(parte for parte in partes if parte)

    # -- índice --------------------------------------------------------------

    @staticmethod
    def _marcadores(documento) -> list[tuple[int, str, int]]:
        """Lee el índice de marcadores del PDF: ``(nivel, título, página)``.

        Es el índice que escribió quien hizo el documento.  En un informe con
        cuatrocientas entradas no hay heurística de encabezados que se le
        acerque, así que cuando existe se prefiere.
        """
        entradas: list[tuple[int, str, int]] = []
        try:
            for marcador in documento.get_toc():
                titulo = (marcador.get_title() or "").strip()
                if not titulo:
                    continue
                pagina = -1
                try:
                    destino = marcador.get_dest()
                    if destino is not None:
                        pagina = destino.get_index()
                except Exception:
                    pagina = -1
                if pagina is None or pagina < 0:
                    continue
                entradas.append((int(marcador.level), titulo, int(pagina) + 1))
        except Exception as error:
            registrar_excepcion(log, "No se han podido leer los marcadores del PDF", error)
            return []
        return entradas

    @staticmethod
    def _indice(marcadores, libro) -> list[ElementoIndice]:
        """Convierte los marcadores del PDF en el índice del documento.

        Cada marcador apunta a una página, y cada página dejó un ancla
        ``pagina-N`` en el texto: con eso se sabe a qué posición saltar.
        """
        if not marcadores:
            return []
        raices: list[ElementoIndice] = []
        pila: list[tuple[int, ElementoIndice]] = []
        for nivel, titulo, pagina in marcadores:
            posicion = libro.posiciones_id.get("pagina-%d" % pagina)
            if posicion is None:
                continue
            entrada = ElementoIndice(titulo[:200], posicion)
            while pila and pila[-1][0] >= nivel:
                pila.pop()
            if pila:
                pila[-1][1].hijos.append(entrada)
            else:
                raices.append(entrada)
            pila.append((nivel, entrada))
        return raices

    # -- reconocimiento ------------------------------------------------------

    def _reconocer(self, documento, numero: int):
        """Rasteriza una página y la manda al OCR.

        El mapa de bits que devuelve PDFium se convierte a PNG con el
        codificador propio del programa (:mod:`formatos.png`): es lo que
        entienden los dos motores de OCR y evita depender de Pillow solo para
        esto.
        """
        from . import ocr, png

        # Cada motor rinde mejor a un aumento distinto (véase ocr.ESCALA):
        # Tesseract necesita mas resolucion que la IA para la letra pequena.
        # El usuario puede fijar uno propio desde las opciones.
        motores = ocr.motores_disponibles(self.servicio_ia, self.ocr_modo)
        ajustes = self.ocr_ajustes or ocr.Ajustes()
        escala = ajustes.escala_de(motores[0] if motores else "")
        mapa = documento[numero].render(scale=escala)
        try:
            imagen = png.desde_bitmap(mapa)
        finally:
            try:
                mapa.close()
            except Exception:
                pass
        return ocr.reconocer(imagen, self.servicio_ia, modo=self.ocr_modo,
                             idiomas_tesseract=self.ocr_idiomas,
                             ajustes=self.ocr_ajustes)

    # -- texto sin estructura ------------------------------------------------

    @staticmethod
    def _estructurar(texto: str) -> str:
        """Convierte el texto de una página en párrafos, marcando los títulos.

        Es el camino de los PDF **sin etiquetar**: como el archivo no dice qué
        línea es un título, se deduce de su forma —una línea corta, sola entre
        líneas en blanco y sin punto final casi siempre lo es—.  Acertar aquí es
        lo que permite recorrer el documento con la tecla ``H`` en lugar de
        línea a línea.
        """
        bloques = re.split(r"\n\s*\n", texto.replace("\r\n", "\n").replace("\r", "\n"))
        partes = []
        for bloque in bloques:
            lineas = [linea.strip() for linea in bloque.split("\n") if linea.strip()]
            if not lineas:
                continue
            if (len(lineas) == 1 and len(lineas[0]) <= _LARGO_TITULO
                    and not lineas[0].endswith((".", ",", ";", ":"))):
                partes.append("<h2>%s</h2>" % escapar(lineas[0]))
            else:
                partes.append(parrafos_de_texto("\n".join(lineas)))
        return "".join(partes) or "<p></p>"

    # -- metadatos y recursos ------------------------------------------------

    @staticmethod
    def _metadatos(documento, destino: Path) -> Metadatos:
        """Lee título y autor de las propiedades del PDF."""
        metadatos = Metadatos()
        try:
            crudos = documento.get_metadata_dict()
        except Exception:
            crudos = {}
        metadatos.titulo = (crudos.get("Title") or "").strip()
        metadatos.autor = (crudos.get("Author") or "").strip()
        metadatos.editorial = (crudos.get("Producer") or "").strip()
        metadatos.fecha = (crudos.get("CreationDate") or "").strip()[:30]
        metadatos.descripcion = (crudos.get("Subject") or "").strip()
        if not metadatos.titulo:
            metadatos.titulo = destino.stem
        return metadatos

    def extraer_recurso(self, ruta: str | os.PathLike, interna: str) -> bytes | None:
        """Recorta una figura de una página y la devuelve como PNG.

        Las figuras de un PDF etiquetado no son archivos que se puedan sacar:
        un gráfico de un informe está hecho de decenas de líneas, rellenos y
        rótulos sueltos.  Lo que se guardó al analizar fue el rectángulo que
        ocupa la figura, y aquí se rasteriza ese trozo de la página, que es lo
        que se puede enseñar (Ctrl+I) y lo que se le puede pasar a la
        inteligencia artificial para que la describa.
        """
        coincidencia = _FIGURA.match(interna or "")
        if not coincidencia:
            return None
        from . import png

        numero = int(coincidencia.group(1))
        izquierda, abajo, derecha, arriba = (float(coincidencia.group(i)) for i in (2, 3, 4, 5))
        pdfium = self._motor()
        try:
            documento = pdfium.PdfDocument(str(ruta), password=self.contrasena or None)
        except Exception as error:
            log.debug("No se ha podido abrir el PDF para recortar la figura: %s", error)
            return None
        try:
            if not 1 <= numero <= len(documento):
                return None
            pagina = documento[numero - 1]
            ancho, alto = pagina.get_size()
            # «crop» son los márgenes que se quitan por cada lado, no el
            # rectángulo: hay que darle la vuelta a la derecha y a la de arriba.
            recorte = (max(izquierda, 0), max(abajo, 0),
                       max(ancho - derecha, 0), max(alto - arriba, 0))
            if recorte[0] + recorte[2] >= ancho or recorte[1] + recorte[3] >= alto:
                recorte = (0, 0, 0, 0)
            mapa = pagina.render(scale=ESCALA_FIGURA, crop=recorte)
            try:
                return png.desde_bitmap(mapa)
            finally:
                try:
                    mapa.close()
                except Exception:
                    pass
        except Exception as error:
            registrar_excepcion(log, "Error recortando la figura %s" % interna, error)
            return None
        finally:
            try:
                documento.close()
            except Exception:
                pass


def _rotulo_de_pagina(documento, numero: int) -> str:
    """Rótulo con el que el propio PDF numera esa página.

    Muchos documentos numeran el prólogo en romanos y el cuerpo en arábigos, y
    empiezan a contar en el «1» varias páginas después del principio del
    archivo.  Cuando el PDF lo dice, es ese número el que hay que anunciar: es
    el que el lector ve impreso y el que aparece en las citas.
    """
    try:
        from pypdfium2 import raw as C

        largo = C.FPDF_GetPageLabel(documento.raw, numero, None, 0)
        if not largo or largo <= 2:
            return ""
        buffer = ctypes.create_string_buffer(largo)
        C.FPDF_GetPageLabel(documento.raw, numero, buffer, largo)
        return buffer.raw[:largo].decode("utf-16-le", "replace").rstrip("\x00").strip()
    except Exception:
        return ""


#: Instancia única, para que la ventana pueda darle el servicio de IA.
analizador_pdf = AnalizadorPDF()
registrar(analizador_pdf)
