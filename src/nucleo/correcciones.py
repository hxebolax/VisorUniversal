# -*- coding: utf-8 -*-
"""Correcciones del usuario: arreglar un documento sin tocar el archivo.

Todo lo que el programa deduce de un PDF sin etiquetar —qué línea era un
título, qué imagen es decorativa, qué encabezado se repite en todas las
páginas— es una deducción, y a veces se equivoca.  Hasta ahora, cuando se
equivocaba no había nada que hacer: el error volvía a aparecer cada vez que se
abría el libro.

Este módulo permite corregirlo **una vez**.  El usuario dice «esto no es un
título, es un párrafo» o «esta imagen se llama *Gráfico de ventas de 2024*», y
la corrección se guarda aparte y se vuelve a aplicar cada vez que se abra ese
mismo documento.

Tres decisiones y por qué
-------------------------

**El archivo original no se toca nunca.**  Ni se reescribe ni se guarda una
copia corregida.  Un PDF puede ser un documento oficial, estar firmado o ser el
único ejemplar que alguien tiene; modificarlo para arreglar cómo se lee sería
desproporcionado.  Las correcciones viven en un archivo aparte —un *sidecar*—
dentro de la carpeta de datos del programa.

**Se atan al contenido, no a la ruta.**  La clave es el resumen SHA-256 del
archivo.  Así un libro que se mueve de carpeta o se renombra conserva sus
correcciones, y un archivo distinto que ocupa el sitio del anterior no las
hereda.  Atarlas a la ruta habría dado las dos respuestas equivocadas.

**Se identifican por el texto, no por la posición.**  Podría parecer más simple
guardar «el carácter 14.320 es un encabezado», y sería frágil hasta lo inútil:
basta con que mejore el reconocimiento óptico, se active otra opción o se
corrija un guion para que todas las posiciones se desplacen y las correcciones
apunten a otra cosa.  Lo que no se mueve es **lo que dice** la línea, y en qué
página está.  Un texto que ya no aparece simplemente no corrige nada, que es el
fallo inofensivo: no se pierde contenido, solo deja de aplicarse un arreglo.

Cómo se aplican
---------------

Sobre el XHTML de cada página, justo antes de convertirlo.  Es el único sitio
por el que pasan los tres caminos de lectura de un PDF —la estructura
etiquetada, la geometría deducida y el reconocimiento óptico—, así que una
corrección hecha sobre un documento reconocido sigue valiendo si mañana se
instala una versión mejor del reconocedor.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import rutas
from .registro import obtener_registro, registrar_excepcion

log = obtener_registro(__name__)

#: Versión del formato del sidecar.  Si cambia de forma incompatible, los
#: archivos antiguos se ignoran en lugar de romper: perder unas correcciones es
#: molesto, abrir mal un libro es peor.
VERSION = 1

#: Qué se puede decir que es un elemento.  Deliberadamente cortos: son la
#: respuesta a «esto en realidad qué es».
TIPOS = ("encabezado", "parrafo", "artefacto", "cita")

#: Etiqueta XHTML con la que se escribe cada tipo corregido.
_ETIQUETAS = {"parrafo": "p", "cita": "blockquote"}

#: Etiquetas cuyo texto se puede corregir.  Las celdas de tabla quedan fuera a
#: propósito: cambiarle el tipo a una celda rompería la rejilla, y para eso lo
#: que hace falta es corregir la tabla entera, que es harina de otro costal.
_CORREGIBLES = frozenset({"p", "h1", "h2", "h3", "h4", "h5", "h6",
                          "blockquote", "li", "div"})


def clave_de(texto: str) -> str:
    """Reduce un texto a lo que lo identifica aunque cambie el análisis.

    Se quitan los espacios sobrantes y se pasa a minúsculas, porque ninguna de
    las dos cosas cambia lo que la línea dice y las dos varían entre versiones
    del conversor.  Los números **sí** se conservan, al revés que al detectar
    encabezados repetidos: aquí lo que se busca es esta línea concreta, y «Tabla
    3» y «Tabla 4» no son la misma.
    """
    return " ".join((texto or "").split()).casefold()[:300]


class Correcciones:
    """Las correcciones de un documento, listas para aplicarse.

    Se usa siempre así: se carga por la huella del archivo, se consulta al
    convertir cada página y, cuando el usuario corrige algo, se anota y se
    guarda.  Un objeto vacío es perfectamente válido y no hace nada, que es lo
    que ocurre con la inmensa mayoría de los documentos.
    """

    __slots__ = ("huella", "titulo", "idioma", "elementos", "descripciones", "_sucio")

    def __init__(self, huella: str = "") -> None:
        self.huella = huella
        #: Título con el que el usuario quiere ver el documento.  Vacío = el que
        #: traiga el archivo.
        self.titulo = ""
        #: Idioma con el que leerlo.  Vacío = el que declare el archivo.
        self.idioma = ""
        #: Correcciones de elementos: clave → ``{"tipo": ..., "nivel": ...}``.
        self.elementos: dict[str, dict] = {}
        #: Descripciones de imágenes: referencia del recurso → texto.
        self.descripciones: dict[str, str] = {}
        self._sucio = False

    # -- estado --------------------------------------------------------------

    def __bool__(self) -> bool:
        """Indica si hay alguna corrección que aplicar."""
        return bool(self.elementos or self.descripciones or self.titulo or self.idioma)

    def __len__(self) -> int:
        """Cuántas correcciones hay en total."""
        return (len(self.elementos) + len(self.descripciones)
                + bool(self.titulo) + bool(self.idioma))

    def resumen(self) -> str:
        """Frase para la ventana de información del documento."""
        from .idioma import _

        if not self:
            return ""
        partes = []
        if self.elementos:
            partes.append(_("%d elementos corregidos") % len(self.elementos))
        if self.descripciones:
            partes.append(_("%d imágenes descritas a mano") % len(self.descripciones))
        if self.titulo:
            partes.append(_("título propio"))
        if self.idioma:
            partes.append(_("idioma forzado a %s") % self.idioma)
        return _("Correcciones guardadas: %s.") % ", ".join(partes)

    # -- anotar --------------------------------------------------------------

    def marcar(self, pagina: int, texto: str, tipo: str, nivel: int = 0) -> bool:
        """Dice qué es de verdad un elemento.

        :param pagina: Página en la que está, empezando en 1.  Forma parte de
                       la clave porque la misma frase puede aparecer en varias
                       páginas queriendo decir cosas distintas.
        :param tipo: Uno de :data:`TIPOS`.  ``"artefacto"`` quita el elemento de
                     la lectura: es lo que se hace con un encabezado de página
                     que se repite o con una imagen decorativa.
        :param nivel: Nivel del encabezado, de 1 a 6.  Solo para
                      ``"encabezado"``.
        :return: Si la corrección se ha anotado.
        """
        clave = clave_de(texto)
        if not clave or tipo not in TIPOS:
            return False
        entrada = {"pagina": int(pagina), "tipo": tipo}
        if tipo == "encabezado":
            entrada["nivel"] = max(1, min(6, int(nivel) or 2))
        self.elementos[self._indice(pagina, clave)] = entrada
        self._sucio = True
        return True

    def olvidar(self, pagina: int, texto: str) -> bool:
        """Deshace la corrección de un elemento."""
        if self.elementos.pop(self._indice(pagina, clave_de(texto)), None) is None:
            return False
        self._sucio = True
        return True

    def describir(self, referencia: str, texto: str) -> bool:
        """Guarda la descripción de una imagen.

        :param referencia: Identificador del recurso tal como lo guarda el
                           analizador (para un PDF, ``pdf-figura:...``).  Es
                           estable porque describe **dónde está** la figura en
                           la página, no en qué punto del texto salió.
        """
        if not referencia:
            return False
        limpio = " ".join((texto or "").split())
        if limpio:
            self.descripciones[referencia] = limpio[:2000]
        else:
            self.descripciones.pop(referencia, None)
        self._sucio = True
        return True

    def fijar_titulo(self, titulo: str) -> None:
        """Fija el título con el que se anunciará el documento."""
        self.titulo = " ".join((titulo or "").split())[:300]
        self._sucio = True

    def fijar_idioma(self, idioma: str) -> None:
        """Fija el idioma con el que se leerá el documento."""
        self.idioma = (idioma or "").strip()[:35]
        self._sucio = True

    # -- aplicar -------------------------------------------------------------

    def corregir_pagina(self, cuerpo: str, pagina: int) -> str:
        """Aplica al XHTML de una página las correcciones que le toquen.

        Recorre los elementos con texto y, si hay una corrección para lo que
        dicen, cambia su etiqueta.  Se usa el analizador de lxml que ya
        procesa todos los formatos, así que no se añade ninguna dependencia y
        el resultado sigue siendo XHTML válido para el conversor.

        Si algo falla se devuelve el cuerpo original sin tocar: una corrección
        que no se puede aplicar no debe impedir leer la página.
        """
        if not self.elementos or not cuerpo:
            return cuerpo
        pendientes = {clave: entrada for clave, entrada in self.elementos.items()
                      if entrada.get("pagina") == int(pagina)}
        if not pendientes:
            return cuerpo
        try:
            return self._reescribir(cuerpo, pagina, pendientes)
        except Exception as error:
            registrar_excepcion(
                log, "No se han podido aplicar las correcciones de la página %d" % pagina,
                error)
            return cuerpo

    def descripcion_de(self, referencia: str) -> str:
        """Devuelve la descripción que el usuario dio a una imagen."""
        return self.descripciones.get(referencia, "")

    # -- persistencia --------------------------------------------------------

    @classmethod
    def cargar(cls, huella: str) -> "Correcciones":
        """Carga las correcciones de un documento, o devuelve unas vacías."""
        correcciones = cls(huella)
        if not huella:
            return correcciones
        destino = ruta_de(huella)
        if not destino.is_file():
            return correcciones
        try:
            datos = json.loads(destino.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            log.warning("No se han podido leer las correcciones de %s: %s", huella[:12], error)
            return correcciones
        if not isinstance(datos, dict) or int(datos.get("version", 0)) != VERSION:
            return correcciones
        correcciones.titulo = str(datos.get("titulo", ""))
        correcciones.idioma = str(datos.get("idioma", ""))
        elementos = datos.get("elementos")
        if isinstance(elementos, dict):
            for clave, entrada in elementos.items():
                if isinstance(entrada, dict) and entrada.get("tipo") in TIPOS:
                    correcciones.elementos[str(clave)] = {
                        "pagina": int(entrada.get("pagina", 0) or 0),
                        "tipo": str(entrada["tipo"]),
                        "nivel": int(entrada.get("nivel", 0) or 0),
                    }
        descripciones = datos.get("descripciones")
        if isinstance(descripciones, dict):
            correcciones.descripciones = {
                str(clave): str(valor) for clave, valor in descripciones.items()}
        log.debug("Cargadas %d correcciones de %s", len(correcciones), huella[:12])
        return correcciones

    def guardar(self, forzar: bool = False) -> bool:
        """Escribe el sidecar si hay algo que escribir.

        Se escribe primero en un archivo temporal y se renombra encima, que es
        lo que evita que un corte de luz a media escritura deje un archivo
        medio escrito y sin poder leer.
        """
        if not self.huella or (not self._sucio and not forzar):
            return False
        destino = ruta_de(self.huella)
        if not self:
            # Sin correcciones no hay que dejar un archivo vacío por ahí.
            try:
                destino.unlink()
            except OSError:
                pass
            self._sucio = False
            return True
        datos = {
            "version": VERSION,
            "huella": self.huella,
            "titulo": self.titulo,
            "idioma": self.idioma,
            "elementos": self.elementos,
            "descripciones": self.descripciones,
        }
        temporal = destino.with_suffix(".tmp")
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=1),
                                encoding="utf-8")
            temporal.replace(destino)
        except OSError as error:
            log.warning("No se han podido guardar las correcciones: %s", error)
            return False
        self._sucio = False
        log.info("Guardadas %d correcciones en %s", len(self), destino.name)
        return True

    # -- interior ------------------------------------------------------------

    @staticmethod
    def _indice(pagina: int, clave: str) -> str:
        """Construye la clave con la que se guarda una corrección."""
        return "%d %s" % (int(pagina), clave)

    def _reescribir(self, cuerpo: str, pagina: int, pendientes: dict) -> str:
        """Cambia las etiquetas de los elementos corregidos de una página."""
        from lxml import etree, html as lxml_html

        arbol = lxml_html.fragment_fromstring(cuerpo, create_parent="div")
        cambios = 0
        for elemento in list(arbol.iter()):
            etiqueta = _nombre(elemento.tag)
            if etiqueta not in _CORREGIBLES:
                continue
            clave = self._indice(pagina, clave_de("".join(elemento.itertext())))
            entrada = pendientes.get(clave)
            if entrada is None:
                continue
            cambios += 1
            if entrada["tipo"] == "artefacto":
                padre = elemento.getparent()
                if padre is not None:
                    # El texto que iba detrás del elemento no es suyo y tiene
                    # que sobrevivir a su desaparición.
                    if elemento.tail:
                        _heredar_cola(elemento, padre)
                    padre.remove(elemento)
                continue
            if entrada["tipo"] == "encabezado":
                elemento.tag = "h%d" % max(1, min(6, entrada.get("nivel") or 2))
            else:
                elemento.tag = _ETIQUETAS.get(entrada["tipo"], "p")
        if not cambios:
            return cuerpo
        interior = etree.tostring(arbol, encoding="unicode", method="xml")
        # «fragment_fromstring» envolvió el cuerpo en un div que no estaba y que
        # no debe llegar al conversor.
        return re.sub(r"^<div>|</div>$", "", interior.strip())


def ruta_de(huella: str) -> Path:
    """Devuelve el archivo de correcciones de un documento.

    El nombre es la huella, que ya es hexadecimal: no hace falta escaparlo y no
    puede colisionar con nada ni salirse de la carpeta.
    """
    limpio = re.sub(r"[^0-9a-f]", "", (huella or "").lower())[:64] or "sin-huella"
    return rutas.subcarpeta("correcciones") / ("%s.json" % limpio)


def _nombre(etiqueta) -> str:
    """Devuelve el nombre de una etiqueta sin su espacio de nombres XML."""
    if not isinstance(etiqueta, str):
        return ""
    if etiqueta.startswith("{"):
        etiqueta = etiqueta.rsplit("}", 1)[-1]
    return etiqueta.lower()


def _heredar_cola(elemento, padre) -> None:
    """Pasa el texto que sigue a un elemento a quien va a quedarse en su sitio."""
    anterior = elemento.getprevious()
    if anterior is not None:
        anterior.tail = (anterior.tail or "") + elemento.tail
    else:
        padre.text = (padre.text or "") + elemento.tail
