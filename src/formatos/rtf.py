# -*- coding: utf-8 -*-
"""Lectura de documentos RTF con su estructura, sin depender de nadie.

El RTF es un formato de 1987 que sigue vivo porque lo escribe todo el mundo:
Word, WordPad, LibreOffice, los programas de gestión, los juzgados.  Y llega
mucho: es lo que sale de «guardar como» cuando alguien quiere que su documento
se abra en cualquier parte.

Por dentro es texto plano con **llaves y palabras de control**:

.. code-block:: text

    {\\rtf1\\ansi\\ansicpg1252
    {\\stylesheet {\\s1 heading 1;}}
    \\pard\\s1\\b Un t\\'edtulo\\b0\\par
    \\pard Un p\\'e1rrafo normal.\\par
    }

Cada llave abre un ámbito que hereda el formato del de fuera y lo devuelve al
cerrarse; cada ``\\palabra`` cambia algo.  Eso es todo, y es lo que hace que se
pueda leer entero sin bibliotecas.

Qué se saca
-----------

* **Títulos**, por el nivel de esquema del párrafo (``\\outlinelevel``) y, si no
  lo trae, por el nombre de su estilo en la tabla de estilos.
* **Negrita, cursiva y subrayado**, y los superíndices de las llamadas de nota.
* **Listas** con viñeta y numeradas.
* **Tablas**, con sus filas y sus celdas.
* **Enlaces**, que en RTF son un campo con la dirección dentro.
* **Notas al pie**, con su ida y su vuelta.
* **Imágenes**, que van en hexadecimal dentro del propio archivo.
* **Los metadatos**: título, autor y compañía.

Por qué propio y no una biblioteca
----------------------------------

Lo que había antes usaba ``striprtf``, que devuelve **texto plano**: un RTF de
doscientas páginas se abría sin un solo título, sin listas y sin tablas.  Y era
una dependencia opcional, así que en un equipo sin ella el formato ni se abría.
Esto lo lee entero, sin instalar nada.
"""

from __future__ import annotations

import re
from pathlib import Path

from nucleo.documento import Metadatos
from nucleo.idioma import _
from nucleo.registro import obtener_registro

from .base import Analizador, ErrorFormato, OpcionesAnalisis, registrar
from .ensamblador import envolver, escapar, montar

log = obtener_registro(__name__)

#: Páginas de códigos que declara un RTF, traducidas a las de Python.
PAGINAS = {
    437: "cp437", 850: "cp850", 852: "cp852", 866: "cp866", 874: "cp874",
    932: "cp932", 936: "cp936", 949: "cp949", 950: "cp950",
    1250: "cp1250", 1251: "cp1251", 1252: "cp1252", 1253: "cp1253",
    1254: "cp1254", 1255: "cp1255", 1256: "cp1256", 1257: "cp1257",
    1258: "cp1258", 10000: "mac-roman",
}

#: Grupos cuyo contenido no es texto del documento y se salta entero.
#: ``pict`` no está: sus datos sí se leen, para poder enseñar las imágenes.
GRUPOS_QUE_SOBRAN = frozenset({
    "fonttbl", "colortbl", "stylesheet", "listtable", "listoverridetable",
    "revtbl", "rsidtbl", "generator", "themedata", "colorschememapping",
    "latentstyles", "datastore", "xmlnstbl", "filetbl", "protusertbl",
    "mmathPr", "wgrffmtfilter", "template", "listtext", "pntext", "pntxta",
    "pntxtb", "bkmkstart", "bkmkend", "xe", "tc", "atrfstart", "atrfend",
    "annotation", "atnid", "atnauthor", "atndate", "atnref", "atnparent",
    "falt", "panose", "objdata", "objclass", "objname", "result",
})

#: Palabras de control que valen por un carácter.
SIMBOLOS = {
    "par": "\n", "line": "\n", "tab": "\t", "emdash": "\u2014",
    "endash": "\u2013", "lquote": "\u2018", "rquote": "\u2019",
    "ldblquote": "\u201c", "rdblquote": "\u201d", "bullet": "\u2022",
    "enspace": " ", "emspace": " ", "qmspace": " ", "nbsp": "\u00a0",
    "zwnj": "", "zwj": "", "softline": "\n", "ltrmark": "", "rtlmark": "",
}

#: Cómo se llama un estilo de título en los idiomas en los que se escribe.
#: Word traduce el nombre del estilo, así que un documento en español dice
#: «Título 1» donde uno en inglés dice «heading 1».
NOMBRES_DE_TITULO = ("heading", "título", "titulo", "titre", "überschrift",
                     "uberschrift", "titolo", "kop", "rubrik", "заголовок")

#: Tope de anidamiento de llaves.  Un archivo dañado puede no cerrarlas nunca.
PROFUNDIDAD_MAXIMA = 200


class _Formato:
    """El formato en vigor: lo que se hereda al abrir una llave."""

    __slots__ = ("negrita", "cursiva", "subrayado", "volado", "estilo",
                 "nivel", "en_tabla", "lista", "oculto")

    def __init__(self) -> None:
        self.negrita = False
        self.cursiva = False
        self.subrayado = False
        self.volado = 0          # 1 arriba, -1 abajo, 0 en la línea
        self.estilo = -1         # índice en la tabla de estilos
        self.nivel = 0           # nivel de esquema + 1, o 0 si no lo es
        self.en_tabla = False
        self.lista = ""          # "" , "ul" o "ol"
        self.oculto = False

    def copia(self) -> "_Formato":
        """Una copia, que es lo que hereda el ámbito de dentro."""
        otro = _Formato()
        for nombre in self.__slots__:
            setattr(otro, nombre, getattr(self, nombre))
        return otro


class ErrorRTF(ValueError):
    """El archivo no es un RTF legible."""


class LectorRTF:
    """Lee un RTF y lo convierte en XHTML.

    :param datos: El archivo entero.  Se trabaja sobre bytes porque un RTF
                  mezcla ASCII con bytes sueltos de su página de códigos, y
                  decodificarlo entero de una vez rompería esos bytes.
    """

    def __init__(self, datos: bytes) -> None:
        if not datos.lstrip()[:5].startswith(b"{\\rtf"):
            raise ErrorRTF(_("El archivo no es un documento RTF."))
        self._datos = datos
        self.metadatos: dict[str, str] = {}
        #: Imágenes encontradas, en el orden en que aparecen.
        self.imagenes: list[bytes] = []
        self._codificacion = "cp1252"
        self._estilos: dict[int, str] = {}
        self._leer_cabecera()

    # -- preparación ----------------------------------------------------------

    def _leer_cabecera(self) -> None:
        """Saca del principio la página de códigos y la tabla de estilos.

        Se hace en una pasada aparte y sobre el texto crudo porque las dos
        cosas hacen falta **antes** de empezar a convertir: sin la página de
        códigos las eñes salen mal, y sin los estilos no se sabe qué párrafo
        era un título.
        """
        cabecera = self._datos[:200000]
        pagina = re.search(rb"\\ansicpg(\d+)", cabecera)
        if pagina:
            self._codificacion = PAGINAS.get(int(pagina.group(1)), "cp1252")
        elif re.search(rb"\\mac[^a-z]", cabecera):
            self._codificacion = "mac-roman"
        self._estilos = _tabla_de_estilos(self._datos, self._codificacion)

    # -- conversión -----------------------------------------------------------

    def a_html(self) -> str:
        """Convierte el documento entero en el cuerpo de un XHTML."""
        salida = _Salida(self._estilos)
        formato = _Formato()
        pila: list[_Formato] = []
        # ``ucN`` dice cuántos caracteres de repuesto sigue a un ``\\uN``, que
        # hay que saltarse: son la versión del carácter para quien no entienda
        # Unicode, y escribirlos dejaría cada letra rara duplicada.
        saltar_repuesto = 1
        pendientes = 0
        destino = ""            # grupo especial en el que estamos
        posicion = 0
        datos = self._datos
        total = len(datos)
        while posicion < total:
            byte = datos[posicion]
            if byte == 0x7B:                        # {
                pila.append(formato)
                formato = formato.copia()
                posicion += 1
                if len(pila) > PROFUNDIDAD_MAXIMA:
                    break
                continue
            if byte == 0x7D:                        # }
                if pila:
                    formato = pila.pop()
                salida.cerrar_ambito(len(pila))
                destino = ""
                posicion += 1
                continue
            if byte == 0x5C:                        # \
                orden, argumento, posicion = _leer_orden(datos, posicion)
                if orden is None:
                    continue
                saltado, saltar_repuesto, pendientes, destino = self._aplicar(
                    orden, argumento, formato, salida, saltar_repuesto,
                    pendientes, destino, pila, posicion)
                if saltado is not None:
                    posicion = saltado
                continue
            if byte in (0x0D, 0x0A):                # los saltos del archivo no cuentan
                posicion += 1
                continue
            if pendientes > 0:
                pendientes -= 1
                posicion += 1
                continue
            fin = _hasta_lo_siguiente(datos, posicion)
            if not formato.oculto and not destino:
                salida.texto(datos[posicion:fin].decode(self._codificacion, "replace"),
                             formato)
            posicion = fin
        salida.cerrar_todo()
        return salida.html()

    def _aplicar(self, orden, argumento, formato, salida, saltar_repuesto,
                 pendientes, destino, pila, posicion):
        """Atiende una palabra de control.  Devuelve dónde seguir y el estado."""
        datos = self._datos
        if orden == "*":
            # «\\*» marca un grupo que quien no lo entienda debe saltarse
            # entero.  Lo que va detrás dice de qué grupo se trata.
            siguiente, _argumento, _fin = _leer_orden(datos, posicion)
            if siguiente not in ("fldinst", "shppict"):
                return _saltar_grupo(datos, posicion), saltar_repuesto, pendientes, destino
            return None, saltar_repuesto, pendientes, destino
        if orden in GRUPOS_QUE_SOBRAN:
            return _saltar_grupo(datos, posicion), saltar_repuesto, pendientes, destino
        if orden in ("info", "pict"):
            fin = _saltar_grupo(datos, posicion)
            if orden == "info":
                self._leer_info(datos[posicion:fin])
            else:
                self._leer_imagen(datos[posicion:fin], salida)
            return fin, saltar_repuesto, pendientes, destino
        if orden == "'":
            # Un byte suelto escrito en hexadecimal.  Si venimos de un
            # «\\uN», este byte es su repuesto para quien no entienda Unicode
            # y hay que saltárselo: escribirlo dejaría cada letra rara dos
            # veces, una bien y otra mal.
            if pendientes > 0:
                return posicion + 2, saltar_repuesto, pendientes - 1, destino
            crudo = datos[posicion:posicion + 2]
            try:
                letra = bytes([int(crudo, 16)]).decode(self._codificacion, "replace")
            except ValueError:
                letra = ""
            if not formato.oculto and not destino:
                salida.texto(letra, formato)
            return posicion + 2, saltar_repuesto, pendientes, destino
        if orden == "u":
            if argumento is not None and not formato.oculto and not destino:
                # Word escribe los caracteres de más de 16 bits como un número
                # negativo, que hay que devolver a su sitio.
                numero = argumento + 65536 if argumento < 0 else argumento
                if 0 <= numero <= 0x10FFFF:
                    salida.texto(chr(numero), formato)
            return None, saltar_repuesto, saltar_repuesto, destino
        if orden == "uc":
            return None, max(0, argumento or 0), pendientes, destino
        if orden in SIMBOLOS:
            if orden in ("par", "line", "softline"):
                salida.fin_de_parrafo(formato, len(pila))
            elif not formato.oculto and not destino:
                salida.texto(SIMBOLOS[orden], formato)
            return None, saltar_repuesto, pendientes, destino
        if orden == "fldinst":
            salida.instruccion_de_campo(len(pila))
            return None, saltar_repuesto, pendientes, destino
        if orden == "fldrslt":
            salida.resultado_de_campo(len(pila))
            return None, saltar_repuesto, pendientes, destino
        self._formato(orden, argumento, formato, salida, len(pila))
        return None, saltar_repuesto, pendientes, destino

    def _formato(self, orden, argumento, formato, salida, profundidad) -> None:
        """Aplica al formato en vigor lo que dice una palabra de control."""
        if orden == "pard":
            formato.negrita = formato.cursiva = formato.subrayado = False
            formato.volado = 0
            formato.estilo = -1
            formato.nivel = 0
            formato.en_tabla = False
            formato.lista = ""
            return
        if orden == "plain":
            formato.negrita = formato.cursiva = formato.subrayado = False
            formato.volado = 0
            return
        encendido = argumento != 0
        if orden == "b":
            formato.negrita = encendido
        elif orden == "i":
            formato.cursiva = encendido
        elif orden in ("ul", "ulw", "uld", "uldb", "ulth", "ulwave"):
            formato.subrayado = encendido
        elif orden == "ulnone":
            formato.subrayado = False
        elif orden == "super":
            formato.volado = 1 if encendido else 0
        elif orden == "sub":
            formato.volado = -1 if encendido else 0
        elif orden == "nosupersub":
            formato.volado = 0
        elif orden == "v":
            formato.oculto = encendido
        elif orden == "s":
            formato.estilo = argumento if argumento is not None else -1
        elif orden == "outlinelevel":
            # 0 es el nivel uno; 9 quiere decir «texto normal».
            formato.nivel = (argumento + 1) if argumento is not None and argumento < 9 else 0
        elif orden in ("intbl",):
            formato.en_tabla = True
        elif orden == "ilvl":
            formato.lista = formato.lista or "ul"
        elif orden == "ls":
            formato.lista = formato.lista or "ul"
        elif orden == "pnlvlblt":
            formato.lista = "ul"
        elif orden in ("pnlvlbody", "pndec"):
            formato.lista = "ol"
        elif orden == "cell":
            salida.fin_de_celda(formato, profundidad)
        elif orden == "row":
            salida.fin_de_fila()
        elif orden == "trowd":
            salida.empezar_fila()
        elif orden == "footnote":
            salida.nota()
        elif orden == "field":
            salida.empezar_campo()

    def _leer_info(self, grupo: bytes) -> None:
        """Saca el título y el autor del grupo de información del documento."""
        for orden, clave in (("title", "titulo"), ("author", "autor"),
                             ("company", "editorial"), ("subject", "descripcion")):
            hallado = re.search(rb"\\" + orden.encode() + rb"[ ]?([^{}]*)", grupo)
            if hallado:
                valor = self._descifrar_dato(hallado.group(1))
                if valor:
                    self.metadatos[clave] = valor

    def _descifrar_dato(self, crudo: bytes) -> str:
        """Convierte en texto un dato de la información del documento.

        Ahí también aparecen los bytes escritos en hexadecimal, así que hay que
        deshacerlos: sin esto, un autor apellidado «Muñoz» se queda en «Mu».
        """
        trozos = []
        posicion = 0
        while posicion < len(crudo):
            byte = crudo[posicion]
            if byte == 0x5C:
                if crudo[posicion + 1:posicion + 2] == b"'":
                    try:
                        trozos.append(bytes([int(crudo[posicion + 2:posicion + 4], 16)]))
                    except ValueError:
                        pass
                    posicion += 4
                    continue
                break                       # otra orden: aquí acaba el dato
            trozos.append(bytes([byte]))
            posicion += 1
        return b"".join(trozos).decode(self._codificacion, "replace").strip()

    def _leer_imagen(self, grupo: bytes, salida: "_Salida") -> None:
        """Guarda una imagen del documento y deja su hueco en el texto.

        Las imágenes van escritas en hexadecimal dentro del propio archivo, así
        que no hay nada que extraer de fuera: se pasa a bytes y se guarda.
        """
        # Primero se quitan las palabras de control y luego lo que no sea
        # hexadecimal.  Al revés no vale: «\pngblip» tiene letras que también
        # son dígitos hexadecimales, y colarlas correría todos los bytes.
        sin_ordenes = re.sub(rb"\\[a-zA-Z]+-?\d*[ ]?", b"", grupo.split(b"}")[0])
        crudo = re.sub(rb"[^0-9a-fA-F]", b"", sin_ordenes[-2000000:])
        if len(crudo) < 32:
            return
        try:
            datos = bytes.fromhex(crudo.decode("ascii", "ignore")[:len(crudo) // 2 * 2])
        except ValueError:
            return
        if not datos:
            return
        self.imagenes.append(datos)
        salida.imagen(len(self.imagenes) - 1)


# ---------------------------------------------------------------------------
# La salida
# ---------------------------------------------------------------------------

class _Salida:
    """Va montando el XHTML a medida que el lector recorre el archivo."""

    def __init__(self, estilos: dict) -> None:
        self._estilos = estilos
        self._partes: list[str] = []
        self._parrafo: list[str] = []
        self._abiertos: list[str] = []
        self._lista = ""
        self._en_tabla = False
        self._fila: list[str] = []
        self._celda: list[str] = []
        self._filas: list[list[str]] = []
        self._campo = ""
        self._destino_campo = ""
        self._profundidad_campo = -1
        self._inicio_enlace = 0
        self._pendiente = ""
        self._ultimo_formato = None
        self._formato_pendiente = _Formato()

    # -- texto ---------------------------------------------------------------

    def texto(self, cadena: str, formato: _Formato) -> None:
        """Añade texto con las etiquetas de énfasis que le correspondan.

        Los trozos seguidos con el mismo formato se juntan en uno: el archivo
        parte el texto por cada byte raro que trae, y sin juntarlos una palabra
        en negrita con una tilde dentro saldría como tres negritas distintas.
        """
        if not cadena:
            return
        if self._campo == "instruccion":
            self._destino_campo += cadena
            return
        marca = (formato.negrita, formato.cursiva, formato.subrayado, formato.volado)
        if marca == self._ultimo_formato and self._parrafo:
            self._pendiente += cadena
            return
        self._volcar_pendiente()
        self._ultimo_formato = marca
        self._pendiente = cadena
        self._parrafo.append("")            # sitio reservado para lo pendiente
        self._formato_pendiente = formato.copia()

    def _volcar_pendiente(self) -> None:
        """Escribe el trozo acumulado con su formato, si lo hay."""
        if not self._pendiente:
            return
        texto = self._con_enfasis(escapar(self._pendiente), self._formato_pendiente)
        # El hueco que se reservó al empezar el trozo.
        for indice in range(len(self._parrafo) - 1, -1, -1):
            if self._parrafo[indice] == "":
                self._parrafo[indice] = texto
                break
        else:
            self._parrafo.append(texto)
        self._pendiente = ""

    @staticmethod
    def _con_enfasis(texto: str, formato: _Formato) -> str:
        """Envuelve un trozo en las etiquetas que digan su formato."""
        if formato.volado == 1:
            texto = "<sup>%s</sup>" % texto
        elif formato.volado == -1:
            texto = "<sub>%s</sub>" % texto
        if formato.subrayado:
            texto = "<u>%s</u>" % texto
        if formato.cursiva:
            texto = "<em>%s</em>" % texto
        if formato.negrita:
            texto = "<strong>%s</strong>" % texto
        return texto

    def imagen(self, numero: int) -> None:
        """Deja en el texto el hueco de una imagen."""
        self._volcar_pendiente()
        self._ultimo_formato = None
        self._parrafo.append('<img src="rtf:%d" alt=""/>' % numero)

    def nota(self) -> None:
        """Marca que lo que sigue es una nota al pie."""
        # Las notas se escriben donde aparecen, que en RTF es justo detrás de
        # su llamada.  Con eso el lector las encuentra en su sitio.
        self._parrafo.append(" ")

    # -- párrafos ------------------------------------------------------------

    def fin_de_parrafo(self, formato: _Formato, profundidad: int) -> None:
        """Cierra el párrafo en curso y decide qué era."""
        del profundidad
        self._volcar_pendiente()
        self._ultimo_formato = None
        texto = "".join(self._parrafo).strip()
        self._parrafo.clear()
        if not texto:
            self._cerrar_lista()
            return
        if formato.en_tabla:
            self._celda.append(texto)
            return
        nivel = self._nivel_de(formato)
        if nivel:
            self._cerrar_lista()
            self._partes.append("<h%d>%s</h%d>" % (nivel, texto, nivel))
            return
        if formato.lista:
            if self._lista != formato.lista:
                self._cerrar_lista()
                self._partes.append("<%s>" % formato.lista)
                self._lista = formato.lista
            self._partes.append("<li>%s</li>" % texto)
            return
        self._cerrar_lista()
        self._partes.append("<p>%s</p>" % texto)

    def _nivel_de(self, formato: _Formato) -> int:
        """Devuelve el nivel de título del párrafo, o cero.

        Manda el nivel de esquema, que es un número y no admite dudas.  Si el
        documento no lo trae —los hay— se mira cómo se llama su estilo, que es
        lo único que queda; ahí se admiten los nombres de varios idiomas porque
        Word los traduce.
        """
        if formato.nivel:
            return min(formato.nivel, 6)
        nombre = self._estilos.get(formato.estilo, "").lower()
        if not nombre:
            return 0
        for candidato in NOMBRES_DE_TITULO:
            if candidato in nombre:
                numero = re.search(r"(\d)", nombre)
                return min(int(numero.group(1)), 6) if numero else 1
        return 0

    def _cerrar_lista(self) -> None:
        if self._lista:
            self._partes.append("</%s>" % self._lista)
            self._lista = ""

    # -- tablas --------------------------------------------------------------

    def empezar_fila(self) -> None:
        self._en_tabla = True

    def fin_de_celda(self, formato: _Formato, profundidad: int) -> None:
        """Cierra una celda con lo que hubiera dentro."""
        del profundidad
        self._volcar_pendiente()
        self._ultimo_formato = None
        texto = "".join(self._parrafo).strip()
        self._parrafo.clear()
        if texto:
            self._celda.append(texto)
        self._fila.append(" ".join(self._celda))
        self._celda.clear()
        del formato

    def fin_de_fila(self) -> None:
        """Cierra una fila de la tabla."""
        if self._fila:
            self._filas.append(list(self._fila))
            self._fila.clear()

    def _volcar_tabla(self) -> None:
        """Escribe la tabla acumulada, con su primera fila como encabezado."""
        if not self._filas:
            self._en_tabla = False
            return
        self._cerrar_lista()
        partes = ["<table>"]
        primera = self._filas[0]
        # La primera fila se toma como encabezado solo si las demás tienen las
        # mismas celdas: si no, es una fila de datos como cualquier otra y
        # anunciarla como encabezado engañaría al lector de pantalla.
        cabecera = len(self._filas) > 1 and all(
            len(fila) == len(primera) for fila in self._filas)
        if cabecera:
            partes.append("<thead><tr>%s</tr></thead>"
                          % "".join("<th>%s</th>" % celda for celda in primera))
            cuerpo = self._filas[1:]
        else:
            cuerpo = self._filas
        partes.append("<tbody>")
        for fila in cuerpo:
            partes.append("<tr>%s</tr>" % "".join("<td>%s</td>" % celda for celda in fila))
        partes.append("</tbody></table>")
        self._partes.append("".join(partes))
        self._filas.clear()
        self._en_tabla = False

    # -- campos (los enlaces) -------------------------------------------------

    def empezar_campo(self) -> None:
        """Empieza un campo: en la práctica, casi siempre un enlace."""
        self._campo = "esperando"
        self._destino_campo = ""

    def instruccion_de_campo(self, profundidad: int) -> None:
        """Lo que viene ahora dice qué es el campo y a dónde lleva."""
        del profundidad
        self._volcar_pendiente()
        self._campo = "instruccion"
        self._destino_campo = ""

    def resultado_de_campo(self, profundidad: int) -> None:
        """Lo que viene ahora es el texto que se ve del campo.

        Aquí ya se sabe a dónde lleva —lo dijo la instrucción—, así que se
        apunta por dónde va el párrafo para poder envolver después justo lo que
        se escriba a partir de ahora.
        """
        self._volcar_pendiente()
        hallado = re.search(r'HYPERLINK\s+"?([^"\s}]+)"?', self._destino_campo or "")
        self._destino_campo = hallado.group(1) if hallado else ""
        self._campo = "resultado" if self._destino_campo else ""
        self._inicio_enlace = len(self._parrafo)
        self._profundidad_campo = profundidad

    def cerrar_ambito(self, profundidad: int) -> None:
        """Se ha cerrado una llave: puede haber acabado un campo o una tabla."""
        if self._campo == "instruccion":
            # Se cierra la instrucción sin que llegue el resultado: no era un
            # enlace o el campo está a medias.
            self._campo = "esperando"
            return
        if (self._campo == "resultado" and self._destino_campo
                and profundidad <= self._profundidad_campo):
            self._volcar_pendiente()
            texto = "".join(self._parrafo[self._inicio_enlace:])
            del self._parrafo[self._inicio_enlace:]
            if texto.strip():
                self._parrafo.append('<a href="%s">%s</a>'
                                     % (escapar(self._destino_campo), texto))
            self._campo = ""
            self._destino_campo = ""
            self._ultimo_formato = None
        if self._en_tabla and not self._fila and self._filas:
            self._volcar_tabla()

    def cerrar_todo(self) -> None:
        """Cierra lo que quede abierto al acabarse el archivo."""
        self._volcar_pendiente()
        if self._parrafo:
            self._partes.append("<p>%s</p>" % "".join(self._parrafo).strip())
            self._parrafo.clear()
        self.fin_de_fila()
        if self._filas:
            self._volcar_tabla()
        self._cerrar_lista()

    def html(self) -> str:
        return "".join(parte for parte in self._partes if parte.strip())


# ---------------------------------------------------------------------------
# Recorrer el archivo
# ---------------------------------------------------------------------------

def _leer_orden(datos: bytes, posicion: int):
    """Lee una palabra de control y devuelve ``(nombre, número, dónde sigue)``.

    Una palabra de control es una barra invertida, letras, un número con signo
    opcional y un espacio que se traga.  Si detrás de la barra no hay letras,
    es un símbolo de control y vale por sí mismo.
    """
    posicion += 1
    if posicion >= len(datos):
        return None, None, posicion
    byte = datos[posicion]
    if not (0x61 <= byte <= 0x7A or 0x41 <= byte <= 0x5A):
        # Símbolo: «\\'» para un byte, «\\\\» para una barra, «\\{» para una llave.
        simbolo = chr(byte)
        if simbolo in ("\\", "{", "}"):
            return "literal" + simbolo, None, posicion + 1
        return simbolo, None, posicion + 1
    fin = posicion
    while fin < len(datos) and (0x61 <= datos[fin] <= 0x7A or 0x41 <= datos[fin] <= 0x5A):
        fin += 1
    nombre = datos[posicion:fin].decode("ascii", "replace")
    numero = None
    inicio_numero = fin
    if fin < len(datos) and datos[fin] == 0x2D:      # signo menos
        fin += 1
    while fin < len(datos) and 0x30 <= datos[fin] <= 0x39:
        fin += 1
    if fin > inicio_numero:
        try:
            numero = int(datos[inicio_numero:fin])
        except ValueError:
            numero = None
    if fin < len(datos) and datos[fin] == 0x20:      # el espacio que la cierra
        fin += 1
    return nombre, numero, fin


def _hasta_lo_siguiente(datos: bytes, posicion: int) -> int:
    """Dónde acaba el texto corriente que empieza en esa posición."""
    fin = posicion
    total = len(datos)
    while fin < total and datos[fin] not in (0x5C, 0x7B, 0x7D, 0x0D, 0x0A):
        fin += 1
    return fin


def _saltar_grupo(datos: bytes, posicion: int) -> int:
    """Devuelve dónde acaba el grupo que está abierto, contando las llaves."""
    profundidad = 1
    total = len(datos)
    while posicion < total:
        byte = datos[posicion]
        if byte == 0x5C:
            posicion += 2                    # lo que sigue a la barra no cuenta
            continue
        if byte == 0x7B:
            profundidad += 1
        elif byte == 0x7D:
            profundidad -= 1
            if profundidad <= 0:
                return posicion              # la llave la cierra quien llama
        posicion += 1
    return total


def _tabla_de_estilos(datos: bytes, codificacion: str) -> dict[int, str]:
    """Lee la tabla de estilos: qué número es cada estilo y cómo se llama.

    Hace falta para los documentos que no traen el nivel de esquema en cada
    párrafo, que son muchos: ahí lo único que dice que algo era un título es
    que su estilo se llame «Título 1».
    """
    inicio = datos.find(b"{\\stylesheet")
    if inicio < 0:
        return {}
    fin = _saltar_grupo(datos, inicio + 1)
    estilos: dict[int, str] = {}
    for grupo in re.finditer(rb"\{([^{}]*)\}", datos[inicio:fin]):
        cuerpo = grupo.group(1).split(b";")[0]
        numero = re.search(rb"\\s(\d+)", cuerpo)
        # El nombre del estilo va al final del grupo, detrás de todas sus
        # órdenes.  Se quitan **solo las del principio**: dentro del nombre
        # también hay barras invertidas —«T\'edtulo 1» es «Título 1»— y
        # cortar por la última se comería la primera letra.
        nombre = re.sub(rb"^(?:\\[a-zA-Z*]+-?\d*[ ]?)+", b"", cuerpo)
        legible = _sin_hexadecimales(nombre, codificacion).strip()
        indice = int(numero.group(1)) if numero else 0
        if legible:
            estilos[indice] = legible
    return estilos


def _sin_hexadecimales(crudo: bytes, codificacion: str) -> str:
    """Convierte a texto un trozo deshaciendo los bytes escritos como «\'hh»."""
    def sustituir(coincidencia):
        try:
            return bytes([int(coincidencia.group(1), 16)])
        except ValueError:
            return b""

    return re.sub(rb"\\'([0-9a-fA-F]{2})", sustituir, crudo).decode(
        codificacion, "replace")


# ---------------------------------------------------------------------------
# El analizador
# ---------------------------------------------------------------------------

class AnalizadorRTF(Analizador):
    """Documentos con formato enriquecido (.rtf)."""

    extensiones = (".rtf",)
    descripcion = _("Texto enriquecido")

    #: Documentos ya leídos, para poder sacarles una imagen después sin volver
    #: a recorrer el archivo entero.
    _abiertos: dict = {}

    def analizar(self, ruta, opciones: OpcionesAnalisis):
        """Lee el RTF con su estructura y lo convierte en documento."""
        destino = Path(ruta)
        try:
            lector = LectorRTF(destino.read_bytes())
        except ErrorRTF as error:
            raise ErrorFormato(str(error)) from error
        except OSError as error:
            raise ErrorFormato(_("No se ha podido abrir el archivo: %s") % error) from error
        try:
            cuerpo = lector.a_html()
        except Exception as error:
            log.debug("Error convirtiendo el RTF: %s", error)
            raise ErrorFormato(_("El archivo RTF está dañado: %s") % error) from error
        if not cuerpo.strip():
            raise ErrorFormato(_("El archivo RTF no contiene texto legible."))
        self._abiertos[str(destino)] = lector
        metadatos = Metadatos(
            titulo=lector.metadatos.get("titulo", "") or destino.stem,
            autor=lector.metadatos.get("autor", ""),
            editorial=lector.metadatos.get("editorial", ""),
            descripcion=lector.metadatos.get("descripcion", ""),
        )
        documento = montar([(destino.name, envolver(cuerpo))], metadatos, destino, opciones)
        log.info("RTF analizado: %s | %d caracteres | %d imágenes",
                 metadatos.titulo, len(documento.texto), len(lector.imagenes))
        return documento

    def extraer_recurso(self, ruta, interna: str) -> bytes | None:
        """Devuelve una imagen del documento, para verla o describirla."""
        lector = self._abiertos.get(str(Path(ruta)))
        if lector is None:
            try:
                lector = LectorRTF(Path(ruta).read_bytes())
                lector.a_html()
            except Exception:
                return None
        numero = re.search(r"(\d+)", interna or "")
        if not numero:
            return None
        indice = int(numero.group(1))
        if 0 <= indice < len(lector.imagenes):
            return lector.imagenes[indice]
        return None


registrar(AnalizadorRTF())
