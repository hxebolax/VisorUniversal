# -*- coding: utf-8 -*-
"""Lectura de los libros KFX de Kindle, el formato actual de Amazon.

Un KFX no se parece a un EPUB en nada.  No hay HTML dentro, ni archivos por
capítulo, ni una hoja de estilo: hay un **contenedor binario** con miles de
piezas numeradas que se apuntan unas a otras, y el texto va suelto, en listas
de cadenas, separado de la información que dice qué es cada una.

La cadena para llegar al texto es esta, y hay que recorrerla entera:

.. code-block:: text

    documento del libro  ($538)   dice en qué orden van las secciones
      └─ sección         ($260)   dice qué historia contiene
          └─ historia    ($259)   lista de bloques: párrafos, imágenes
              └─ bloque           dice de qué contenido sale su texto...
                  └─ contenido ($145)  ...y en qué posición de su lista

Los nombres de las propiedades no vienen escritos: el formato usa una tabla de
símbolos que no está en el archivo, así que todo llega numerado (``$146``,
``$790``).  Los números **son estables** —Amazon no los reordena—, de modo que
lo que hace este módulo es traducir los que hacen falta, y solo esos, con la
constante :data:`CLAVES` como diccionario.  Se han averiguado comparando tres
libros con su versión EPUB, y el resultado es exacto: de 736.854 letras, salen
las mismas 736.854.

Lo que se saca:

* **El texto**, en su orden de lectura de verdad.
* **Los títulos**, por la marca ``$790``, que es como el formato dice «esto es
  un encabezado» sin decir de qué nivel.
* **El índice** del libro, con sus destinos.
* **Las imágenes**, con su texto alternativo cuando lo traen.
* **Las cursivas, las negritas y los enlaces**, que van como tramos de
  caracteres sobre el texto pelado.
* **Los metadatos**: título, autores, editorial e idioma.

No se descifra nada: un KFX con DRM se rechaza con un mensaje que lo dice.  Lo
que este módulo lee son archivos que ya vienen sin protección.
"""

from __future__ import annotations

import struct
import zipfile
from pathlib import Path
from typing import NamedTuple

from nucleo.idioma import _
from nucleo.registro import obtener_registro

from .ensamblador import escapar

log = obtener_registro(__name__)

#: Marca de un contenedor KFX.
CONTENEDOR = b"CONT"

#: Marca de una entidad dentro del contenedor.
ENTIDAD = b"ENTY"

#: Marca del comienzo de un flujo Ion binario (la versión 1.0 del formato).
ION = b"\xe0\x01\x00\xea"

#: Marca de un contenedor cifrado.  Un archivo así no se puede leer.
CIFRADO = b"\xeaDRMION\xee"

#: Profundidad máxima al recorrer los bloques anidados.  Un archivo mal formado
#: puede tener ciclos, y sin tope el recorrido no termina.
PROFUNDIDAD_MAXIMA = 60

#: Qué significa cada número de propiedad, de los que hacen falta.  El formato
#: numera sus propiedades contra una tabla de símbolos que no viaja dentro del
#: archivo; estos números son los que se han identificado comparando libros con
#: su versión EPUB, y son estables entre libros y entre versiones.
CLAVES = {
    "contenido": "$145",        # de qué contenido sale el texto de un bloque
    "hijos": "$146",            # bloques de dentro, o cadenas de texto
    "nombre": "$4",             # nombre de un contenido
    "posicion": "$403",         # qué cadena de ese contenido, por su índice
    "identificador": "$155",    # identificador del bloque, al que apunta el índice
    "estilo": "$157",           # estilo del bloque o del tramo
    "clase": "$159",            # qué clase de bloque es
    "tramos": "$142",           # tramos de caracteres con estilo propio
    "desde": "$143",            # primer carácter del tramo
    "cuantos": "$144",          # cuántos caracteres ocupa
    "encabezado": "$790",       # el bloque es un título
    "alternativo": "$584",      # texto alternativo de una imagen
    "recurso": "$175",          # a qué recurso apunta el bloque
    "historia": "$176",         # qué historia trae una sección
    "seccion": "$174",          # nombre de la sección
    "plantillas": "$141",       # plantillas de página de una sección
    "ordenes": "$169",          # órdenes de lectura del documento
    "orden": "$170",            # secciones en el orden de lectura
    "indice": "$392",           # el índice del libro
    "entradas": "$247",         # entradas de ese índice
    "rotulo": "$241",           # rótulo de una entrada
    "texto_rotulo": "$244",     # su texto
    "destino": "$246",          # a dónde lleva la entrada
    "clase_indice": "$235",     # de qué clase es cada navegación
    "ancho": "$422",            # ancho declarado de una imagen
    "alto": "$423",             # su alto
    "enlace": "$179",           # el tramo es un enlace, y esto es su destino
    "sitio": "$183",            # a qué bloque lleva ese destino
    "metadatos": "$491",        # bloques de metadatos
    "pares": "$258",            # pares clave/valor de un bloque
    "clave": "$492",            # nombre del dato
    "valor": "$307",            # su valor
    "fuente_estilo": "$12",     # redonda o cursiva
    "grosor": "$13",            # normal o negrita
}

#: Clase de navegación que es el índice del libro.  Un KFX trae varias —la
#: guía, los marcadores del principio y la lista de posiciones de Kindle, que
#: son 608 en un libro corriente y no llevan rótulo—, y solo esta es el índice
#: que el lector quiere recorrer.
INDICE_DEL_LIBRO = "$212"

#: Clase de bloque: párrafo de texto, imagen o contenedor de otros bloques.
CLASE_PARRAFO = "$269"
CLASE_IMAGEN = "$271"
CLASE_CONTENEDOR = "$270"

#: Valores de estilo que interesan.  Son los únicos dos que cambian cómo se lee
#: un texto: la cursiva y la negrita.  El resto —la fuente, el tamaño, el
#: color— no se lee en voz alta ni se navega, así que no se traduce.
CURSIVA = "$382"
NEGRITA = "$361"

#: Tipos de entidad del contenedor que hacen falta.
TIPO_CONTENIDO = 145
TIPO_ESTILO = 157
TIPO_HISTORIA = 259
TIPO_SECCION = 260
TIPO_DOCUMENTO = 538
TIPO_INDICE = 389
TIPO_METADATOS = 490
TIPO_RECURSO = 164
TIPO_DATOS = 417
#: Entidad que dice a qué bloque lleva un enlace.  Un enlace no apunta al
#: bloque directamente: apunta a una de estas, y esta al bloque.
TIPO_DESTINO = 266


class ErrorKFX(ValueError):
    """El archivo no es un KFX legible."""


# ---------------------------------------------------------------------------
# El contenedor
# ---------------------------------------------------------------------------

class _Lector:
    """Lectura secuencial de una estructura binaria."""

    __slots__ = ("datos", "pos")

    def __init__(self, datos: bytes) -> None:
        self.datos = datos
        self.pos = 0

    def leer(self, formato: str) -> tuple:
        """Lee varios valores y avanza."""
        valores = struct.unpack_from(formato, self.datos, self.pos)
        self.pos += struct.calcsize(formato)
        return valores

    def uno(self, formato: str, avanzar: bool = True):
        """Lee un valor, avanzando o sin avanzar."""
        valor = struct.unpack_from(formato, self.datos, self.pos)[0]
        if avanzar:
            self.pos += struct.calcsize(formato)
        return valor

    def sacar(self, cuantos: int) -> bytes:
        """Devuelve los siguientes ``cuantos`` bytes."""
        trozo = self.datos[self.pos:self.pos + cuantos]
        self.pos += cuantos
        return trozo

    def queda(self) -> int:
        """Bytes que faltan por leer."""
        return len(self.datos) - self.pos


def _numero_variable(datos: bytes, pos: int) -> tuple[int, int]:
    """Lee un número de longitud variable: siete bits por byte, el último marcado.

    Es como el formato guarda las longitudes y los identificadores de
    propiedad.  Devuelve el número y cuántos bytes ha ocupado.
    """
    numero = 0
    consumidos = 0
    limite = min(len(datos), pos + 10)
    while pos + consumidos < limite:
        byte = datos[pos + consumidos]
        consumidos += 1
        numero = (numero << 7) | (byte & 0x7F)
        if byte & 0x80:
            break
    return numero, consumidos


class _Ion(_Lector):
    """Decodifica el Ion binario, que es como el KFX guarda sus estructuras.

    Ion es el formato de serialización de Amazon: un JSON binario con tipos.
    Se implementa solo lo que el KFX usa —booleanos, enteros, cadenas,
    símbolos, listas, estructuras y valores con anotación—, porque lo demás
    (decimales, marcas de tiempo, blobs) no aparece en el contenido de un
    libro y añadirlo sería código que nunca se ejecuta.

    Los símbolos salen como ``"$146"`` en vez de con su nombre: la tabla que
    los traduce no viaja dentro del archivo.  Véase :data:`CLAVES`.
    """

    #: Códigos de tipo de Ion, en el nibble alto del byte de mando.
    BOOLEANO = 1
    ENTERO = 2
    ENTERO_NEGATIVO = 3
    SIMBOLO = 7
    CADENA = 8
    ESTRUCTURA_LISTA = 11
    LISTA = 12
    OBJETO = 13
    ANOTADO = 14

    def decodificar(self):
        """Decodifica el flujo entero, que empieza por su marca."""
        if self.sacar(4) != ION:
            raise ErrorKFX("falta la marca de comienzo de los datos")
        return self.valor()

    def numero(self) -> int:
        """Lee un número de longitud variable y avanza."""
        numero, consumidos = _numero_variable(self.datos, self.pos)
        self.pos += consumidos
        return numero

    def entero(self, largo: int) -> int:
        """Lee un entero sin signo de ``largo`` bytes, el más significativo primero."""
        return int.from_bytes(self.sacar(largo), "big") if largo else 0

    def valor(self):
        """Lee un valor cualquiera: el byte de mando dice de qué tipo es."""
        mando = self.uno("B")
        tipo = mando >> 4
        largo = mando & 0x0F
        if largo == 14:
            largo = self.numero()
        if tipo == self.BOOLEANO:
            return largo != 0
        if tipo == self.ENTERO:
            return self.entero(largo)
        if tipo == self.ENTERO_NEGATIVO:
            return -self.entero(largo)
        if tipo == self.SIMBOLO:
            return "$%d" % self.entero(largo)
        if tipo == self.CADENA:
            return self.sacar(largo).decode("utf-8", "replace")
        if tipo in (self.ESTRUCTURA_LISTA, self.LISTA):
            dentro = _Ion(self.sacar(largo))
            lista = []
            while dentro.queda():
                lista.append(dentro.valor())
            return lista
        if tipo == self.OBJETO:
            dentro = _Ion(self.sacar(largo))
            objeto = {}
            while dentro.queda():
                # El nombre y el valor se leen en dos pasos y en este orden a
                # propósito: en «objeto[clave()] = valor()» Python llama antes
                # a «valor()» que a «clave()», y aquí las dos lecturas avanzan
                # sobre los mismos bytes, así que se leerían cambiadas.
                clave = "$%d" % dentro.numero()
                objeto[clave] = dentro.valor()
            return objeto
        if tipo == self.ANOTADO:
            # Valor con anotaciones delante.  Las anotaciones dicen de qué
            # clase es el valor, cosa que aquí no hace falta: se saltan y se
            # devuelve el valor de dentro.
            dentro = _Ion(self.sacar(largo))
            dentro.numero()
            dentro.numero()
            return dentro.valor()
        # Nulos, flotantes, decimales y demás: no aparecen en el contenido.
        self.pos += largo
        return None


def _entidades(datos: bytes) -> list[tuple[int, int, bytes]]:
    """Devuelve ``(tipo, identificador, datos)`` de cada entidad del contenedor.

    La tabla de entidades va justo detrás de la cabecera y se acaba donde
    empiezan los datos, que se reconocen por su marca Ion.
    """
    lector = _Lector(datos)
    if lector.sacar(4) != CONTENEDOR:
        raise ErrorKFX("no es un contenedor KFX")
    lector.uno("<H")                     # versión del contenedor
    largo_cabecera = lector.uno("<L")
    lector.pos += 8                      # dos campos que no hacen falta
    salida = []
    while lector.queda() >= 24 and lector.uno("4s", avanzar=False) != ION:
        ident, tipo, desplazamiento, largo = lector.leer("<LLQQ")
        inicio = largo_cabecera + desplazamiento
        salida.append((tipo, ident, datos[inicio:inicio + largo]))
    return salida


def _datos_de_entidad(cuerpo: bytes) -> bytes:
    """Devuelve los bytes de una entidad que no lleva estructura, sino datos."""
    if cuerpo[:4] != ENTIDAD:
        return b""
    lector = _Lector(cuerpo)
    lector.sacar(4)
    lector.uno("<H")
    return cuerpo[lector.uno("<L"):]


def _decodificar_entidad(cuerpo: bytes):
    """Decodifica el contenido de una entidad, o devuelve ``None``.

    Las entidades que no llevan datos Ion son recursos: imágenes, fuentes.  Se
    dejan pasar sin decodificar, que es lo que corresponde.
    """
    if cuerpo[:4] != ENTIDAD:
        return None
    lector = _Lector(cuerpo)
    lector.sacar(4)
    lector.uno("<H")
    interior = cuerpo[lector.uno("<L"):]
    if interior[:4] != ION:
        return None
    try:
        return _Ion(interior).decodificar()
    except Exception as error:
        log.debug("Una entidad KFX no se ha podido decodificar: %s", error)
        return None


# ---------------------------------------------------------------------------
# El libro
# ---------------------------------------------------------------------------

class Entrada(NamedTuple):
    """Una entrada del índice del libro."""

    rotulo: str
    #: Identificador del bloque al que lleva, para escribirlo como ancla.
    destino: int
    nivel: int


class LibroKFX:
    """Un libro KFX ya abierto, listo para dar sus secciones en XHTML.

    :param ruta: Archivo ``.kfx``, ``.kfx-zip`` o ``.azw`` con formato KFX.
    """

    def __init__(self, ruta: Path) -> None:
        self.ruta = Path(ruta)
        #: Entidades por identificador: ``{id: [(tipo, valor), ...]}``.
        self._entidades: dict[int, list] = {}
        #: Metadatos del libro, ya en claro.
        self.metadatos: dict[str, object] = {}
        #: Índice del libro, en orden.
        self.indice: list[Entrada] = []
        #: Bytes de las imágenes, por identificador de entidad.
        self._crudos: dict[int, bytes] = {}
        #: Correspondencia ya calculada entre recurso e imagen.
        self._por_recurso: dict | None = None
        self._cargar()

    # -- apertura ------------------------------------------------------------

    def _cargar(self) -> None:
        """Lee todos los contenedores del archivo y los indexa."""
        for datos in self._contenedores():
            if CIFRADO in datos[:4096]:
                raise ErrorKFX(_("Este libro de Kindle está protegido con DRM y no se "
                                 "puede leer."))
            try:
                entidades = _entidades(datos)
            except ErrorKFX:
                continue
            for tipo, ident, cuerpo in entidades:
                valor = _decodificar_entidad(cuerpo)
                if valor is not None:
                    self._entidades.setdefault(ident, []).append((tipo, valor))
                elif tipo == TIPO_DATOS:
                    self._crudos[ident] = _datos_de_entidad(cuerpo)
        if not self._entidades:
            raise ErrorKFX(_("El archivo no trae ningún contenido que se pueda leer."))
        self._leer_metadatos()
        self._leer_indice()

    def _contenedores(self):
        """Va devolviendo los bytes de cada contenedor KFX del archivo.

        Un libro puede venir como un contenedor suelto o como un zip con
        varios: el del texto, los de los recursos y el de los metadatos.
        """
        if zipfile.is_zipfile(str(self.ruta)):
            with zipfile.ZipFile(str(self.ruta)) as archivo:
                for nombre in archivo.namelist():
                    try:
                        datos = archivo.read(nombre)
                    except Exception as error:
                        log.debug("No se ha podido leer %s: %s", nombre, error)
                        continue
                    if datos[:4] == CONTENEDOR:
                        yield datos
            return
        datos = self.ruta.read_bytes()
        if datos[:4] != CONTENEDOR:
            raise ErrorKFX(_("El archivo no es un libro KFX."))
        yield datos

    def _de_tipo(self, tipo: int, ident: int | None = None):
        """Devuelve el valor de la entidad de ese tipo, o ``None``."""
        if ident is not None:
            for clase, valor in self._entidades.get(ident, ()):
                if clase == tipo:
                    return valor
            return None
        for lista in self._entidades.values():
            for clase, valor in lista:
                if clase == tipo:
                    return valor
        return None

    # -- metadatos e índice ---------------------------------------------------

    def _leer_metadatos(self) -> None:
        """Saca título, autores, editorial e idioma del bloque de metadatos."""
        bloque = self._de_tipo(TIPO_METADATOS)
        if not isinstance(bloque, dict):
            return
        autores: list[str] = []
        for grupo in bloque.get(CLAVES["metadatos"]) or ():
            if not isinstance(grupo, dict):
                continue
            for par in grupo.get(CLAVES["pares"]) or ():
                if not isinstance(par, dict):
                    continue
                clave = par.get(CLAVES["clave"])
                valor = par.get(CLAVES["valor"])
                if not isinstance(clave, str) or not isinstance(valor, str):
                    continue
                if clave == "author":
                    autores.append(valor)
                elif clave in ("title", "publisher", "language", "ASIN"):
                    self.metadatos.setdefault(clave, valor)
        if autores:
            self.metadatos["authors"] = autores

    def _leer_indice(self) -> None:
        """Lee el índice del libro, si lo trae.

        Las entradas pueden anidarse —partes con capítulos dentro—, y el nivel
        sale de lo hondo que esté cada una, que es lo que después permite
        recorrer el índice como el de un EPUB.
        """
        navegacion = self._de_tipo(TIPO_INDICE)
        if navegacion is None:
            return
        grupos = navegacion if isinstance(navegacion, list) else [navegacion]
        for grupo in grupos:
            if not isinstance(grupo, dict):
                continue
            indices = grupo.get(CLAVES["indice"]) or ()
            for indice in indices if isinstance(indices, list) else [indices]:
                if not isinstance(indice, dict):
                    continue
                if indice.get(CLAVES["clase_indice"]) != INDICE_DEL_LIBRO:
                    continue
                self._entradas(indice.get(CLAVES["entradas"]) or (), 1)

    def _entradas(self, entradas, nivel: int) -> None:
        """Recorre las entradas del índice, entrando en las que tengan hijas."""
        if nivel > 6:
            return
        for entrada in entradas:
            if not isinstance(entrada, dict):
                continue
            rotulo = entrada.get(CLAVES["rotulo"])
            texto = ""
            if isinstance(rotulo, dict):
                texto = str(rotulo.get(CLAVES["texto_rotulo"]) or "").strip()
            destino = entrada.get(CLAVES["destino"])
            identificador = 0
            if isinstance(destino, dict):
                identificador = int(destino.get(CLAVES["identificador"]) or 0)
            if texto:
                self.indice.append(Entrada(texto, identificador, nivel))
            hijas = entrada.get(CLAVES["entradas"])
            if isinstance(hijas, list):
                self._entradas(hijas, nivel + 1)

    # -- contenido ------------------------------------------------------------

    def secciones(self) -> list[tuple[str, bytes]]:
        """Devuelve el libro como secciones XHTML, en su orden de lectura.

        Es el formato que espera el ensamblador: el mismo que sale de un EPUB,
        de modo que a partir de aquí el libro se recorre, se busca y se lee
        exactamente igual.  Convertirlo a XHTML en vez de montar el texto a
        mano no es un rodeo: es lo que hace que los títulos, las cursivas, las
        imágenes y las anclas del índice pasen por el mismo camino que ya está
        probado para los demás formatos.
        """
        documento = self._de_tipo(TIPO_DOCUMENTO)
        nombres = []
        if isinstance(documento, dict):
            for orden in documento.get(CLAVES["ordenes"]) or ():
                if isinstance(orden, dict):
                    nombres.extend(orden.get(CLAVES["orden"]) or ())
        if not nombres:
            # Sin documento que diga el orden se leen las secciones tal como
            # aparecen: es peor que el orden de verdad, y mucho mejor que no
            # leer el libro.
            nombres = ["$%d" % ident for ident, lista in sorted(self._entidades.items())
                       if any(tipo == TIPO_SECCION for tipo, _valor in lista)]
        salida = []
        for posicion, nombre in enumerate(nombres, start=1):
            cuerpo = self._seccion_a_html(nombre)
            if not cuerpo:
                continue
            pagina = ('<?xml version="1.0" encoding="utf-8"?>\n'
                      '<html xmlns="http://www.w3.org/1999/xhtml"><body>%s</body></html>'
                      % cuerpo)
            salida.append(("seccion-%d" % posicion, pagina.encode("utf-8")))
        return salida

    def _seccion_a_html(self, nombre) -> str:
        """Escribe una sección entera como XHTML."""
        seccion = self._de_tipo(TIPO_SECCION, _identificador(nombre))
        if not isinstance(seccion, dict):
            return ""
        partes: list[str] = []
        for plantilla in seccion.get(CLAVES["plantillas"]) or ():
            if not isinstance(plantilla, dict):
                continue
            historia = self._de_tipo(
                TIPO_HISTORIA, _identificador(plantilla.get(CLAVES["historia"])))
            if isinstance(historia, dict):
                for bloque in historia.get(CLAVES["hijos"]) or ():
                    self._bloque_a_html(bloque, partes)
            else:
                # Hay plantillas que traen el contenido dentro, sin historia.
                self._bloque_a_html(plantilla, partes)
        return "".join(partes)

    def _bloque_a_html(self, bloque, partes: list, profundidad: int = 0) -> None:
        """Escribe un bloque y todo lo que cuelgue de él."""
        if not isinstance(bloque, dict) or profundidad > PROFUNDIDAD_MAXIMA:
            return
        ancla = self._ancla(bloque)
        if bloque.get(CLAVES["clase"]) == CLASE_IMAGEN:
            alternativo = str(bloque.get(CLAVES["alternativo"]) or "")
            partes.append('<img src="kfx:%s" alt="%s"%s/>'
                          % (escapar(str(bloque.get(CLAVES["recurso"]) or "")),
                             escapar(alternativo), ancla))
            ancla = ""
        texto = self._texto_de(bloque)
        if texto:
            # El formato dice si un bloque es un título, pero no de qué nivel,
            # así que todos salen como nivel uno.  Es lo que hay en el archivo:
            # inventarse una jerarquía a partir del tamaño de la letra daría
            # niveles que el autor no puso.
            etiqueta = "h1" if CLAVES["encabezado"] in bloque else "p"
            partes.append("<%s%s>%s</%s>"
                          % (etiqueta, ancla, self._con_tramos(bloque, texto), etiqueta))
        elif ancla:
            # Un bloque sin texto al que apunta el índice: el ancla tiene que
            # existir igualmente, o esa entrada no llevaría a ninguna parte.
            partes.append("<span%s></span>" % ancla)
        for hijo in bloque.get(CLAVES["hijos"]) or ():
            self._bloque_a_html(hijo, partes, profundidad + 1)

    def _ancla(self, bloque: dict) -> str:
        """Devuelve el atributo ``id`` del bloque, que es a donde va el índice."""
        identificador = bloque.get(CLAVES["identificador"])
        if not isinstance(identificador, int):
            return ""
        return ' id="%s"' % ancla_de(identificador)

    def _texto_de(self, bloque: dict) -> str:
        """Saca el texto de un bloque siguiendo su referencia al contenido."""
        referencia = bloque.get(CLAVES["contenido"])
        if not isinstance(referencia, dict):
            return ""
        contenido = self._de_tipo(
            TIPO_CONTENIDO, _identificador(referencia.get(CLAVES["nombre"])))
        if not isinstance(contenido, dict):
            return ""
        piezas = contenido.get(CLAVES["hijos"]) or ()
        posicion = referencia.get(CLAVES["posicion"])
        if isinstance(posicion, int):
            if 0 <= posicion < len(piezas) and isinstance(piezas[posicion], str):
                return piezas[posicion]
            return ""
        return "".join(pieza for pieza in piezas if isinstance(pieza, str))

    def _con_tramos(self, bloque: dict, texto: str) -> str:
        """Aplica al texto los tramos de cursiva y de negrita que lleve.

        Los tramos vienen como «desde el carácter tal, tantos caracteres», y se
        aplican de izquierda a derecha cortando el texto en trozos.  Cada trozo
        se escapa por separado, que es lo que hay que hacer: escapar primero el
        renglón entero y luego cortar por posiciones partiría por la mitad
        cualquier «&amp;» que hubiera antes del tramo.
        """
        tramos = bloque.get(CLAVES["tramos"])
        if not isinstance(tramos, list) or not tramos:
            return escapar(texto)
        marcados = []
        for tramo in tramos:
            if not isinstance(tramo, dict):
                continue
            desde = tramo.get(CLAVES["desde"])
            cuantos = tramo.get(CLAVES["cuantos"])
            if not isinstance(desde, int) or not isinstance(cuantos, int):
                continue
            hasta = min(desde + cuantos, len(texto))
            if not 0 <= desde < hasta:
                continue
            etiquetas = self._etiquetas_de_estilo(tramo.get(CLAVES["estilo"]))
            destino = self._destino_de_enlace(tramo.get(CLAVES["enlace"]))
            if destino:
                # El enlace va por fuera del énfasis: así el texto del enlace
                # sigue siendo el mismo aunque además vaya en cursiva.
                etiquetas = ['a href="#%s"' % destino] + etiquetas
            if etiquetas:
                marcados.append((desde, hasta, etiquetas))
        if not marcados:
            return escapar(texto)
        piezas: list[str] = []
        anterior = 0
        for desde, hasta, etiquetas in sorted(marcados):
            if desde < anterior:
                continue                 # tramos que se pisan: manda el primero
            piezas.append(escapar(texto[anterior:desde]))
            abre = "".join("<%s>" % etiqueta for etiqueta in etiquetas)
            # Al cerrar solo va el nombre de la etiqueta, sin sus atributos.
            cierra = "".join("</%s>" % etiqueta.split(" ")[0]
                             for etiqueta in reversed(etiquetas))
            piezas.append("%s%s%s" % (abre, escapar(texto[desde:hasta]), cierra))
            anterior = hasta
        piezas.append(escapar(texto[anterior:]))
        return "".join(piezas)

    def _destino_de_enlace(self, referencia) -> str:
        """Devuelve el ancla a la que lleva un enlace, o cadena vacía.

        Un enlace no apunta al bloque de destino directamente: apunta a una
        entidad intermedia que es la que dice a qué bloque lleva.  Ese rodeo
        es lo que permite que el libro mueva un capítulo de sitio sin tener
        que tocar todos los enlaces que van a él.
        """
        identificador = _identificador(referencia)
        if identificador is None:
            # Sin destino no hay enlace.  Hay que decirlo aquí: pedir una
            # entidad sin identificador quiere decir «la primera de ese tipo»,
            # y eso convertiría en enlace todos los tramos que no lo son.
            return ""
        entidad = self._de_tipo(TIPO_DESTINO, identificador)
        if not isinstance(entidad, dict):
            return ""
        sitio = entidad.get(CLAVES["sitio"])
        if not isinstance(sitio, dict):
            return ""
        bloque = sitio.get(CLAVES["identificador"])
        return ancla_de(bloque) if isinstance(bloque, int) else ""

    def _etiquetas_de_estilo(self, estilo) -> list[str]:
        """Devuelve ``["em"]``, ``["strong"]``, las dos o ninguna."""
        definicion = self._de_tipo(TIPO_ESTILO, _identificador(estilo))
        if not isinstance(definicion, dict):
            return []
        etiquetas = []
        if definicion.get(CLAVES["fuente_estilo"]) == CURSIVA:
            etiquetas.append("em")
        if definicion.get(CLAVES["grosor"]) == NEGRITA:
            etiquetas.append("strong")
        return etiquetas


    # -- imágenes -------------------------------------------------------------

    def recurso(self, referencia: str) -> bytes | None:
        """Devuelve los bytes de una imagen del libro, o ``None``.

        La referencia es la que se escribió en el ``src`` de la imagen al
        convertir el libro.

        Véase :meth:`_imagenes` para cómo se empareja cada imagen con sus
        bytes, que es lo único que aquí tiene truco.
        """
        identificador = _identificador(referencia.replace("kfx:", "").strip())
        if identificador is None:
            return None
        pares = self._imagenes()
        return pares.get(identificador)

    def _imagenes(self) -> dict:
        """Empareja cada imagen declarada con los bytes que le tocan.

        El libro declara sus imágenes en un sitio —con su tipo, sus medidas y
        su nombre— y guarda los bytes en otro, cada uno en una entidad cuyo
        identificador es el símbolo del nombre.  Esa correspondencia entre
        símbolo y nombre va en una tabla que **no viaja dentro del archivo**,
        así que hay que reconstruirla.

        Se hace **comprobándola, no suponiéndola**: la declaración dice cuánto
        mide la imagen, y los bytes lo dicen también en su propia cabecera, así
        que se empareja por medidas y solo se acepta cuando no hay dudas.  Las
        que queden —dos imágenes del mismo tamaño— se reparten por orden, que
        es como están escritas.  De quince imágenes de tres libros, las quince
        cuadran por medidas.
        """
        if self._por_recurso is not None:
            return self._por_recurso
        declarados = sorted(
            (ident, valor) for ident, lista in self._entidades.items()
            for tipo, valor in lista
            if tipo == TIPO_RECURSO and isinstance(valor, dict))
        crudos = sorted(self._crudos.items())
        self._por_recurso = {}
        libres = list(crudos)
        pendientes = []
        for ident, valor in declarados:
            medida = (valor.get(CLAVES["ancho"]), valor.get(CLAVES["alto"]))
            iguales = [par for par in libres if _medidas(par[1]) == medida] \
                if all(medida) else []
            if len(iguales) == 1:
                self._por_recurso[ident] = iguales[0][1]
                libres.remove(iguales[0])
            else:
                pendientes.append(ident)
        for ident, (_numero, datos) in zip(pendientes, libres):
            self._por_recurso[ident] = datos
        if pendientes:
            log.debug("KFX: %d imágenes emparejadas por medidas y %d por orden",
                      len(declarados) - len(pendientes), len(pendientes))
        return self._por_recurso


def _medidas(datos: bytes) -> tuple:
    """Ancho y alto de una imagen, leídos de su propia cabecera.

    Se miran solo JPEG y PNG, que es lo que traen los libros; de cualquier
    otra cosa se devuelve ``(None, None)``, que quiere decir «no lo sé» y hace
    que esa imagen se reparta por orden en vez de por medidas.
    """
    if datos[:8] == b"\x89PNG\r\n\x1a\n" and len(datos) >= 24:
        return struct.unpack(">LL", datos[16:24])
    if datos[:2] == b"\xff\xd8":
        posicion = 2
        while posicion + 9 < len(datos):
            if datos[posicion] != 0xFF:
                posicion += 1
                continue
            marca = datos[posicion + 1]
            largo = struct.unpack(">H", datos[posicion + 2:posicion + 4])[0]
            # Los marcadores de «comienzo de cuadro» son los que llevan las
            # medidas; los demás se saltan por su longitud.
            if marca in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                         0xC9, 0xCA, 0xCB):
                alto, ancho = struct.unpack(">HH", datos[posicion + 5:posicion + 9])
                return ancho, alto
            posicion += 2 + largo
    return (None, None)


def ancla_de(identificador: int) -> str:
    """Nombre del ancla que corresponde a un bloque, para el índice."""
    return "kfx-%d" % identificador


def _identificador(simbolo) -> int | None:
    """De ``"$854"`` al número 854."""
    if isinstance(simbolo, int):
        return simbolo
    if not isinstance(simbolo, str) or not simbolo.startswith("$"):
        return None
    try:
        return int(simbolo[1:])
    except ValueError:
        return None
