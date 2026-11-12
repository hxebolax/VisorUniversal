# -*- coding: utf-8 -*-
"""La biblioteca: todos los libros a la vez, y buscar en todos de golpe.

Hasta ahora había «documentos recientes», que es una lista de los últimos diez
archivos abiertos.  Sirve para volver a lo de ayer y no sirve para nada más.
Falta lo de después, que es donde de verdad se nota:

* **Buscar una frase en todos los libros a la vez.**  Para quien estudia, esta
  es la diferencia entre usar el programa y no usarlo: buscar una cita en
  cuarenta PDF abriéndolos de uno en uno no lo hace nadie.
* **Ver todo lo que hay**, agrupado por autor, por serie, por etiqueta o por
  colección, y saber cuáles se han terminado y por dónde va cada uno de los
  demás.

De dónde salen los libros
-------------------------

De dos sitios que se suman:

1. **Los que se han abierto alguna vez.**  El programa ya guarda de cada uno su
   título, su posición y sus marcadores, así que la biblioteca no tiene que
   inventar nada: ya estaban ahí.
2. **Las carpetas y las bibliotecas de calibre que el usuario añada.**  Se
   exploran una vez y lo encontrado se guarda en una base de datos propia
   (:mod:`nucleo.biblioteca_datos`); abrir la biblioteca es leerla, no volver
   a recorrer el disco.  No hay tope: ciento noventa mil libros se cargan en
   un par de segundos.

Los archivos que ya no existen no se borran solos: un libro en un disco
extraíble que hoy no está enchufado vuelve mañana, y borrar su posición de
lectura por eso sería el peor de los favores.

Cómo se busca en todos
----------------------

Sin montar ningún índice.  Cada libro se abre —de la caché si ya está analizado,
que es lo normal, y analizándolo si no— y se busca en su texto.  Un índice de
palabras sería más rápido a la décima búsqueda, pero habría que mantenerlo,
ocuparía tanto como los libros y quedaría desfasado en cuanto se cambiara un
ajuste de análisis.  Con la caché puesta, buscar en cuarenta libros ya
analizados tarda un par de segundos.

La búsqueda avisa de por dónde va y se puede parar: en una biblioteca con libros
sin analizar, la primera vez puede tardar.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from . import biblioteca_datos as datos
from .biblioteca_importar import sin_tildes as _sin_tildes
from .idioma import _
from .registro import obtener_registro

log = obtener_registro(__name__)

#: Cuántas coincidencias se devuelven de cada libro.  Con más, la lista de
#: resultados deja de poder recorrerse y el libro que más repita la palabra se
#: come todos los resultados de los demás.
POR_LIBRO = 20

#: Cuántas coincidencias se devuelven en total.
TOTALES = 500

#: Caracteres de contexto que se enseñan a cada lado de lo encontrado.
CONTEXTO = 60

#: A partir de qué porcentaje se da un libro por terminado.  No se exige el
#: cien: casi nadie llega hasta el último carácter, porque al final están los
#: agradecimientos, el índice y los créditos.
TERMINADO = 97


class Libro:
    """Un libro de la biblioteca, con lo que se sabe de él sin abrirlo.

    Se llena con lo que ya hay guardado.  **Ni abrir el libro ni preguntar al
    disco hace falta** para enseñar la lista: si el archivo sigue ahí se
    comprueba la primera vez que alguien lo pregunta, y no al crearlo.  Es lo
    que permite que una biblioteca de ciento noventa mil libros en un disco de
    los de girar aparezca en segundos y no en minutos.
    """

    __slots__ = ("ruta", "clave", "titulo", "autor", "posicion", "total", "tamano",
                 "fecha", "_existe", "en_disco", "coleccion", "serie", "serie_indice",
                 "etiquetas", "editorial", "publicado", "idioma", "_formato", "fuente",
                 "anadido", "valoracion", "busqueda", "orden_titulo", "orden_autor",
                 "actualizado", "isbn", "autores_orden")

    def __init__(self, ruta: str, titulo: str = "", autor: str = "",
                 posicion: int = 0, total: int = 0, coleccion: str = "") -> None:
        self.ruta = str(ruta)
        self.clave = datos.clave(self.ruta)
        self.titulo = (titulo or "").strip() or Path(self.ruta).stem
        self.autor = (autor or "").strip()
        #: Colección o asignatura a la que el usuario lo ha asignado.
        self.coleccion = (coleccion or "").strip()
        self.posicion = int(posicion or 0)
        self.total = int(total or 0)
        self.tamano = 0
        self.fecha = 0.0
        self._existe = None
        #: Si está en una carpeta o biblioteca añadida y no solo en lo recordado.
        self.en_disco = False
        self.serie = ""
        self.serie_indice = 0.0
        self.etiquetas = ""
        self.editorial = ""
        self.publicado = ""
        self.idioma = ""
        self._formato = ""
        #: Número de la fuente de la que sale, o 0 si solo se conoce por abrirlo.
        self.fuente = 0
        self.anadido = ""
        self.valoracion = 0
        self.isbn = ""
        self.autores_orden = ""
        #: Cuándo se leyó por última vez (lo apunta la configuración).
        self.actualizado = 0.0
        self.busqueda = _sin_tildes("%s %s %s" % (self.titulo, self.autor,
                                                  Path(self.ruta).name))
        self.orden_titulo = _sin_tildes(self.titulo)
        self.orden_autor = _sin_tildes(self.autor)

    @classmethod
    def desde_fila(cls, fila) -> "Libro":
        """Un libro tal como está en la base de datos de la biblioteca.

        Se salta el ``__init__`` a propósito: con ciento noventa mil filas,
        cada operación de más se nota, y aquí todo viene ya calculado.
        """
        libro = cls.__new__(cls)
        libro.ruta = fila["ruta"]
        libro.clave = fila["clave"]
        libro.titulo = fila["titulo"] or Path(libro.ruta).stem
        libro.autor = fila["autor"] or ""
        libro.coleccion = ""
        libro.posicion = 0
        libro.total = 0
        libro.tamano = int(fila["tamano"] or 0)
        libro.fecha = float(fila["fecha"] or 0)
        # Se da por bueno lo que se vio al importar: preguntarle al disco por
        # cada uno es justo lo que hacía lenta la biblioteca.  Si al abrirlo
        # resulta que no está, se avisa entonces.
        libro._existe = True
        libro.en_disco = True
        libro.serie = fila["serie"] or ""
        libro.serie_indice = float(fila["serie_indice"] or 0)
        libro.etiquetas = fila["etiquetas"] or ""
        libro.editorial = fila["editorial"] or ""
        libro.publicado = fila["publicado"] or ""
        libro.idioma = fila["idioma"] or ""
        libro._formato = fila["formato"] or ""
        libro.fuente = int(fila["fuente"] or 0)
        libro.anadido = fila["anadido"] or ""
        libro.valoracion = int(fila["valoracion"] or 0)
        libro.isbn = fila["isbn"] or ""
        libro.autores_orden = fila["autores_orden"] or ""
        libro.actualizado = 0.0
        libro.busqueda = fila["busqueda"] or ""
        libro.orden_titulo = fila["orden_titulo"] or ""
        libro.orden_autor = fila["orden_autor"] or ""
        return libro

    @property
    def existe(self) -> bool:
        """Si el archivo está en su sitio.  Se mira la primera vez que se pide."""
        if self._existe is None:
            self._mirar()
        return bool(self._existe)

    @existe.setter
    def existe(self, valor: bool) -> None:
        self._existe = bool(valor)

    def _mirar(self) -> None:
        """Consulta el disco: si está, cuánto ocupa y de cuándo es."""
        try:
            estado = os.stat(self.ruta)
        except OSError:
            self._existe = False
            return
        self._existe = True
        self.tamano = estado.st_size
        self.fecha = estado.st_mtime

    @property
    def formato(self) -> str:
        """La extensión, en mayúsculas y sin el punto."""
        return self._formato or Path(self.ruta).suffix.lstrip(".").upper()

    @property
    def porcentaje(self) -> int:
        """Por dónde va la lectura, de 0 a 100."""
        if self.total <= 0:
            return 0
        return max(0, min(100, int(self.posicion * 100 / self.total)))

    @property
    def terminado(self) -> bool:
        """Indica si se ha llegado prácticamente al final."""
        return self.total > 0 and self.porcentaje >= TERMINADO

    @property
    def empezado(self) -> bool:
        """Indica si se ha leído algo de él."""
        return self.posicion > 0

    def estado(self) -> str:
        """Frase corta con por dónde va, para la lista."""
        if not self.existe:
            return _("no se encuentra el archivo")
        if self.terminado:
            return _("terminado")
        if self.empezado:
            return _("%d %%") % self.porcentaje
        return _("sin empezar")

    def fecha_legible(self) -> str:
        """La fecha del archivo escrita como se lee."""
        if not self.existe or not self.fecha:
            return ""
        return time.strftime("%d/%m/%Y", time.localtime(self.fecha))

    def serie_legible(self) -> str:
        """La serie con su número: «Episodios nacionales 3»."""
        if not self.serie:
            return ""
        if self.serie_indice:
            numero = self.serie_indice
            texto = str(int(numero)) if float(numero).is_integer() else str(numero)
            return "%s %s" % (self.serie, texto.replace(".", ","))
        return self.serie

    def tamano_legible(self) -> str:
        """Lo que ocupa, en la unidad que se entiende."""
        return tamano_legible(self.tamano)


def tamano_legible(octetos: int) -> str:
    """Un tamaño en bytes escrito como se dice: «1,4 MB»."""
    if octetos <= 0:
        return ""
    if octetos < 1024 * 1024:
        return _("%d KB") % max(1, round(octetos / 1024))
    return (_("%.1f MB") % (octetos / (1024 * 1024))).replace(".", ",")


def _anadir_recordado(libros: dict, ruta: str, datos_libro, excluidos: set) -> None:
    """Junta con la lista lo que la configuración recuerda de un libro."""
    clave = datos.clave(ruta)
    if clave in excluidos:
        return
    libro = libros.get(clave)
    if libro is None:
        libro = Libro(ruta, getattr(datos_libro, "titulo", ""),
                      getattr(datos_libro, "autor", ""))
        libros[clave] = libro
    libro.posicion = int(getattr(datos_libro, "posicion", 0) or 0)
    libro.total = int(getattr(datos_libro, "total", 0) or 0)
    libro.coleccion = (getattr(datos_libro, "coleccion", "") or "").strip()
    libro.actualizado = float(getattr(datos_libro, "actualizado", 0) or 0)


def cargar(configuracion, progreso=None, cancelado=None, ruta_bd=None):
    """Reúne todos los libros: los de la base de datos y los recordados.

    Está pensada para llamarse **en un hilo aparte**: con una biblioteca
    grande tarda unos segundos y avisa de por dónde va.

    :param progreso: Se llama con ``(hecho, total, detalle)``.
    :param cancelado: Si devuelve verdadero, se deja de leer.
    :return: ``(libros, fuentes)``, los libros ordenados por título y las
             fuentes de la biblioteca.
    """
    conexion = datos.conectar(ruta_bd)
    try:
        total = datos.contar_libros(conexion)
        excluidos = datos.excluidas(conexion)
        fuentes = datos.fuentes(conexion)
        libros: dict[str, Libro] = {}
        if progreso is not None:
            progreso(0, total, _("Leyendo la biblioteca..."))
        for tanda in datos.leer_libros(conexion):
            if cancelado is not None and cancelado():
                break
            for fila in tanda:
                libro = Libro.desde_fila(fila)
                libros[libro.clave] = libro
            if progreso is not None:
                progreso(len(libros), total, _("Leyendo la biblioteca: %(hecho)d de "
                                               "%(total)d libros")
                         % {"hecho": len(libros), "total": total})
    finally:
        conexion.close()
    for ruta, datos_libro in configuracion.libros_recordados():
        _anadir_recordado(libros, ruta, datos_libro, excluidos)
    for ruta in configuracion.recientes():
        clave = datos.clave(ruta)
        if clave not in libros and clave not in excluidos:
            libros[clave] = Libro(ruta)
    if progreso is not None:
        progreso(total, total, _("Ordenando..."))
    return ordenar(libros.values(), "titulo"), fuentes


def desde_configuracion(configuracion, carpetas=None) -> list[Libro]:
    """Los libros recordados más los de unas carpetas exploradas en el momento.

    Es la forma antigua, sin base de datos, y queda para quien la use desde
    fuera.  La ventana de la biblioteca usa :func:`cargar`.

    :param carpetas: Carpetas que hay que explorar.  Con ``None`` se usan las
                     que el usuario tuviera guardadas de versiones anteriores.
    """
    libros: dict[str, Libro] = {}
    for ruta, datos_libro in configuracion.libros_recordados():
        _anadir_recordado(libros, ruta, datos_libro, set())
    for ruta in configuracion.recientes():
        if datos.clave(ruta) not in libros:
            libros[datos.clave(ruta)] = Libro(ruta)
    if carpetas is None:
        carpetas = configuracion.obtener("biblioteca_carpetas", []) or []
    for encontrado in explorar(carpetas):
        clave = datos.clave(encontrado)
        if clave in libros:
            libros[clave].en_disco = True
            continue
        libro = Libro(encontrado)
        libro.en_disco = True
        libros[clave] = libro
    return ordenar(libros.values(), "titulo")


def _clave(ruta: str) -> str:
    """Cómo se compara si dos rutas son el mismo libro."""
    return datos.clave(ruta)


def explorar(carpetas) -> list[str]:
    """Busca en esas carpetas, enteras y sin tope, los archivos que se saben abrir.

    Se pregunta al registro de analizadores en vez de llevar una lista aquí:
    así, un formato nuevo aparece en la biblioteca en cuanto su analizador
    existe, sin tocar este módulo.
    """
    from formatos import base
    from .biblioteca_importar import _Avance, recorrer

    admitidas = set(base.extensiones_admitidas())
    encontrados: list[str] = []
    for carpeta in carpetas:
        if not os.path.isdir(str(carpeta)):
            continue
        for ruta, _tamano, _fecha in recorrer(str(carpeta), admitidas, set(),
                                              _Avance(None, None), None):
            encontrados.append(ruta)
    return encontrados


# -- columnas de la lista ------------------------------------------------------

#: Columnas que puede tener la lista de libros, en el orden en que salen.  El
#: título va siempre; las demás se eligen en Opciones → Biblioteca.
COLUMNAS = (
    ("titulo", _("Título")),
    ("autor", _("Autor")),
    ("serie", _("Serie")),
    ("coleccion", _("Colección")),
    ("etiquetas", _("Etiquetas")),
    ("editorial", _("Editorial")),
    ("publicado", _("Publicación")),
    ("idioma", _("Idioma")),
    ("formato", _("Formato")),
    ("tamano", _("Tamaño")),
    ("valoracion", _("Valoración")),
    ("fuente", _("Biblioteca")),
    ("anadido", _("Añadido")),
    ("lectura", _("Lectura")),
    ("ruta", _("Archivo")),
)

#: Las que se enseñan si el usuario no ha elegido otras.
COLUMNAS_POR_OMISION = ("titulo", "autor", "serie", "coleccion", "formato", "lectura")


def columnas_elegidas(pedidas) -> list[str]:
    """Las columnas que quiere el usuario, en el orden de :data:`COLUMNAS`."""
    # Lo guardado en «biblioteca_columnas»; si no sirve, las de siempre.
    if not isinstance(pedidas, (list, tuple)) or not pedidas:
        pedidas = COLUMNAS_POR_OMISION
    validas = [clave for clave, _nombre in COLUMNAS if clave in pedidas]
    if "titulo" not in validas:
        validas.insert(0, "titulo")
    return validas


def _fecha_corta(texto: str) -> str:
    """``AAAA-MM-DD`` como ``DD/MM/AAAA``."""
    if len(texto) >= 10 and texto[4] == "-":
        return "%s/%s/%s" % (texto[8:10], texto[5:7], texto[:4])
    return texto


def texto_columna(libro: Libro, columna: str, nombres_fuente=None) -> str:
    """Lo que se enseña de un libro en una columna."""
    if columna == "titulo":
        return libro.titulo
    if columna == "autor":
        return libro.autor or _("(sin autor)")
    if columna == "serie":
        return libro.serie_legible()
    if columna == "publicado":
        return libro.publicado[:4]
    if columna == "tamano":
        return libro.tamano_legible()
    if columna == "valoracion":
        from .biblioteca_importar import _estrellas

        return _estrellas(libro.valoracion)
    if columna == "fuente":
        return (nombres_fuente or {}).get(libro.fuente, "") if libro.fuente else ""
    if columna == "anadido":
        return _fecha_corta(libro.anadido)
    if columna == "lectura":
        return libro.estado()
    if columna == "formato":
        return libro.formato
    if columna == "ruta":
        return libro.ruta
    return str(getattr(libro, columna, "") or "")


# -- ordenar y agrupar ---------------------------------------------------------

#: Por qué se puede ordenar la lista, con el nombre que se enseña.
ORDENES = (
    ("titulo", _("Título")),
    ("autor", _("Autor")),
    ("serie", _("Serie y número")),
    ("publicado", _("Fecha de publicación, de la más reciente")),
    ("anadido", _("Añadidos, de los más recientes")),
    ("abierto", _("Leídos, de los más recientes")),
    ("formato", _("Formato")),
)

_ULTIMO = "￿"


def ordenar(libros, criterio: str) -> list[Libro]:
    """Ordena los libros por uno de los criterios de :data:`ORDENES`."""
    lista = list(libros)
    if criterio == "autor":
        lista.sort(key=lambda l: (l.orden_autor or _ULTIMO, _sin_tildes(l.serie) or _ULTIMO,
                                  l.serie_indice, l.orden_titulo))
    elif criterio == "serie":
        lista.sort(key=lambda l: (_sin_tildes(l.serie) or _ULTIMO, l.serie_indice,
                                  l.orden_titulo))
    elif criterio == "publicado":
        lista.sort(key=lambda l: l.orden_titulo)
        lista.sort(key=lambda l: l.publicado or "", reverse=True)
    elif criterio == "anadido":
        lista.sort(key=lambda l: l.orden_titulo)
        lista.sort(key=lambda l: l.anadido or "", reverse=True)
    elif criterio == "abierto":
        lista.sort(key=lambda l: l.orden_titulo)
        lista.sort(key=lambda l: l.actualizado, reverse=True)
    elif criterio == "formato":
        lista.sort(key=lambda l: (l.formato, l.orden_titulo))
    else:
        lista.sort(key=lambda l: (l.orden_titulo, l.clave))
    return lista


#: Por qué se puede agrupar, con el nombre que se enseña.
AGRUPACIONES = (
    ("coleccion", _("Colección o asignatura")),
    ("autor", _("Autor")),
    ("serie", _("Serie")),
    ("etiquetas", _("Etiqueta")),
    ("editorial", _("Editorial")),
    ("idioma", _("Idioma")),
    ("formato", _("Formato")),
    ("publicado", _("Año de publicación")),
    ("fuente", _("Biblioteca o carpeta")),
    ("lectura", _("Estado de lectura")),
)

#: Clave del grupo que reúne los libros que no tienen ese dato.
SIN_GRUPO = "?"


def valores_de(libro: Libro, campo: str, nombres_fuente=None) -> list[str]:
    """Los valores de un libro para una agrupación.  Un libro puede tener varios.

    Un libro de dos autores sale con los dos, y uno con tres etiquetas, en las
    tres: es lo que se espera al buscar «todo lo de Fulano».
    """
    if campo == "autor":
        return [a.strip() for a in libro.autor.split("&") if a.strip()]
    if campo in ("etiquetas", "idioma", "editorial"):
        return [v.strip() for v in getattr(libro, campo).split(",") if v.strip()]
    if campo == "publicado":
        return [libro.publicado[:4]] if libro.publicado[:4].isdigit() else []
    if campo == "formato":
        return [libro.formato] if libro.formato else []
    if campo == "fuente":
        if not libro.fuente:
            return [_("Libros abiertos sueltos")]
        return [(nombres_fuente or {}).get(libro.fuente, str(libro.fuente))]
    if campo == "lectura":
        if libro.terminado:
            return [_("Terminados")]
        if libro.empezado:
            return [_("A medias")]
        return [_("Sin empezar")]
    valor = (getattr(libro, campo, "") or "").strip()
    return [valor] if valor else []


def indice_de_grupos(libros, campo: str, nombres_fuente=None):
    """Reparte los libros en sus grupos de una vez, para elegir grupo al instante.

    Con sesenta mil autores, buscar los libros de uno recorriendo la
    biblioteca entera cada vez que se baja con la flecha por la lista de
    autores se notaría; con el reparto hecho, es mirar un diccionario.  Cada
    grupo conserva el orden en que vienen los libros.

    Los grupos se ordenan alfabéticamente y no por número: una lista de
    asignaturas se recorre buscando **una concreta**, y para eso el orden
    alfabético es el único que permite adivinar dónde está sin leerla entera.
    Los años van del más reciente al más antiguo, que es como se buscan.

    :return: ``(grupos, reparto)``: ``grupos`` es ``[(nombre, clave, cuántos)]``
             con, al final, los que no tienen el dato (clave :data:`SIN_GRUPO`);
             ``reparto`` es ``{clave: [libros]}``.
    """
    reparto: dict[str, list[Libro]] = {}
    escritos: dict[str, str] = {}
    for libro in libros:
        valores = valores_de(libro, campo, nombres_fuente)
        if not valores:
            reparto.setdefault(SIN_GRUPO, []).append(libro)
            continue
        vistos = set()
        for valor in valores:
            clave = _sin_tildes(valor)
            if clave in vistos:
                continue
            vistos.add(clave)
            reparto.setdefault(clave, []).append(libro)
            escritos.setdefault(clave, valor)
    salida = [(escritos[c], c, len(lista)) for c, lista in reparto.items()
              if c != SIN_GRUPO]
    salida.sort(key=lambda trio: trio[1], reverse=(campo == "publicado"))
    if SIN_GRUPO in reparto:
        salida.append(("", SIN_GRUPO, len(reparto[SIN_GRUPO])))
    return salida, reparto


def grupos(libros, campo: str, nombres_fuente=None) -> list[tuple[str, str, int]]:
    """Los grupos que hay para una agrupación y cuántos libros lleva cada uno.

    :return: ``[(nombre, clave, cuántos), ...]``; al final, si los hay, los que
             no tienen el dato, con la clave :data:`SIN_GRUPO`.
    """
    return indice_de_grupos(libros, campo, nombres_fuente)[0]


def de_grupo(libros, campo: str, clave: str, nombres_fuente=None) -> list[Libro]:
    """Los libros de un grupo.  Con la clave vacía, todos."""
    if not clave:
        return list(libros)
    if clave == SIN_GRUPO:
        return [l for l in libros if not valores_de(l, campo, nombres_fuente)]
    return [l for l in libros
            if any(_sin_tildes(v) == clave for v in valores_de(l, campo, nombres_fuente))]


def autores(libros) -> dict[str, list[Libro]]:
    """Agrupa los libros por autor, para poder recorrerlos así."""
    salida: dict[str, list[Libro]] = {}
    for libro in libros:
        salida.setdefault(libro.autor or _("(sin autor)"), []).append(libro)
    return salida


def colecciones(libros) -> list[tuple[str, int]]:
    """Las colecciones que hay y cuántos libros lleva cada una, por orden alfabético."""
    return [(nombre, n) for nombre, clave, n in grupos(libros, "coleccion")
            if clave != SIN_GRUPO]


def de_coleccion(libros, coleccion: str) -> list[Libro]:
    """Los libros de una colección. Sin colección, todos.

    El nombre especial ``"?"`` deja **los que no tienen ninguna**, que es lo que
    hace falta para ir asignándolas sin perder de vista lo que queda por
    clasificar.
    """
    nombre = (coleccion or "").strip()
    if not nombre:
        return list(libros)
    if nombre == "?":
        return [l for l in libros if not (l.coleccion or "").strip()]
    return de_grupo(libros, "coleccion", _sin_tildes(nombre))


# -- libros parecidos ----------------------------------------------------------

#: Por qué datos se buscan libros parecidos a uno, en el orden en que se
#: ofrecen.  Son agrupaciones de :data:`AGRUPACIONES`: buscar «los de la misma
#: serie» es elegir el grupo de esa serie, sin tener que buscarlo en la lista.
SIMILARES = (
    ("serie", _("De la misma serie")),
    ("autor", _("Del mismo autor")),
    ("coleccion", _("De la misma colección")),
    ("etiquetas", _("Con la misma etiqueta")),
    ("editorial", _("De la misma editorial")),
)

#: Cuántas etiquetas de un libro se ofrecen como mucho.  Hay libros de calibre
#: con treinta, y un menú de treinta entradas no se recorre.
MAX_ETIQUETAS_SIMILARES = 12


def clave_de_grupo(valor: str) -> str:
    """La clave del grupo al que pertenece un valor (sin tildes ni mayúsculas)."""
    return _sin_tildes(valor or "")


def similares(libro: Libro) -> list[tuple[str, str, str]]:
    """De qué maneras se pueden buscar libros parecidos a uno.

    :return: ``[(campo, valor, clave), ...]``: el campo por el que se agrupa, el
             valor tal como se escribe («Harry Potter», «J. K. Rowling») y la
             clave del grupo en :func:`indice_de_grupos`.  Un libro de dos
             autores da dos entradas; uno sin serie no da ninguna de serie.
    """
    salida: list[tuple[str, str, str]] = []
    for campo, _nombre in SIMILARES:
        valores = valores_de(libro, campo)
        if campo == "etiquetas":
            valores = valores[:MAX_ETIQUETAS_SIMILARES]
        vistos = set()
        for valor in valores:
            clave = clave_de_grupo(valor)
            if clave and clave not in vistos:
                vistos.add(clave)
                salida.append((campo, valor, clave))
    return salida


def filtrar(libros, texto: str) -> list[Libro]:
    """Deja los libros en los que salgan **todas** las palabras escritas.

    Se mira el título, los autores, la serie, las etiquetas, la editorial, la
    colección y el nombre del archivo, sin acentos ni mayúsculas.  Con varias
    palabras basta con que estén, en cualquier orden: «galdos episodios»
    encuentra los «Episodios nacionales» de Galdós.
    """
    palabras = _sin_tildes(texto).split()
    if not palabras:
        return list(libros)
    salida = []
    for libro in libros:
        donde = libro.busqueda
        if libro.coleccion:
            donde = donde + " " + _sin_tildes(libro.coleccion)
        if all(palabra in donde for palabra in palabras):
            salida.append(libro)
    return salida


class Coincidencia:
    """Un sitio de un libro donde aparece lo que se buscaba."""

    __slots__ = ("libro", "posicion", "contexto", "sitio")

    def __init__(self, libro: Libro, posicion: int, contexto: str,
                 sitio: str = "") -> None:
        self.libro = libro
        self.posicion = posicion
        self.contexto = contexto
        self.sitio = sitio


def buscar_en_todos(libros, texto: str, opciones, progreso=None, cancelado=None,
                    solo_cacheados: bool = False) -> list[Coincidencia]:
    """Busca un texto en todos los libros y devuelve dónde aparece.

    :param opciones: :class:`~formatos.base.OpcionesAnalisis` con la que se
                     abrieron; hace falta para dar con la entrada de la caché.
    :param progreso: Se llama con ``(hecho, total, detalle)``.
    :param cancelado: Se consulta entre libro y libro.
    :param solo_cacheados: Si solo se miran los libros ya analizados.  Es lo
                           que hace que la primera búsqueda sea instantánea:
                           lo que ya está, se busca; lo que no, se ofrece
                           analizarlo aparte.
    """
    from nucleo import cache

    buscado = _sin_tildes(texto)
    if not buscado:
        return []
    resultados: list[Coincidencia] = []
    total = len(libros)
    for numero, libro in enumerate(libros):
        if cancelado is not None and cancelado():
            break
        if progreso is not None:
            progreso(numero, total, _("Buscando en: %s") % libro.titulo)
        if not libro.existe:
            continue
        documento = _abrir(libro, opciones, cache, solo_cacheados)
        if documento is None:
            continue
        # El título y el autor se aprovechan de paso: si el libro estaba en la
        # lista sin ellos, aquí se rellenan solos.
        libro.titulo = documento.metadatos.titulo or libro.titulo
        libro.autor = documento.metadatos.autor or libro.autor
        libro.total = libro.total or len(documento.texto)
        for coincidencia in _en_documento(libro, documento, buscado):
            resultados.append(coincidencia)
            if len(resultados) >= TOTALES:
                log.info("La búsqueda se corta en %d resultados", TOTALES)
                return resultados
    if progreso is not None:
        progreso(total, total, _("Búsqueda terminada."))
    return resultados


def _abrir(libro: Libro, opciones, cache, solo_cacheados: bool):
    """Trae el documento del libro, de la caché o analizándolo."""
    firma = opciones.firma()
    try:
        documento = cache.cargar(libro.ruta, firma)
    except Exception as error:                       # pragma: no cover
        log.debug("No se ha podido leer la caché de %s: %s", libro.ruta, error)
        documento = None
    if documento is not None or solo_cacheados:
        return documento
    from formatos import base

    analizador = base.analizador_para(libro.ruta)
    if analizador is None:
        return None
    try:
        documento = analizador.analizar(libro.ruta, opciones)
    except Exception as error:
        log.info("No se ha podido abrir %s para buscar: %s", libro.ruta, error)
        return None
    try:
        cache.guardar(documento, firma)
    except Exception:                                # pragma: no cover
        pass
    return documento


def _en_documento(libro: Libro, documento, buscado: str):
    """Encuentra el texto dentro de un documento ya abierto."""
    from .marcas import TipoMarca

    texto = _sin_tildes(documento.texto)
    original = documento.texto
    # La comparación se hace sobre el texto sin acentos, y el trozo que se
    # enseña se saca del original: así se busca sin preocuparse de las tildes y
    # a la vez se ve lo que de verdad dice el libro.
    if len(texto) != len(original):
        # Quitar acentos ha cambiado la longitud (pasa con algunos caracteres
        # compuestos), así que las posiciones ya no valdrían.  Se busca sobre
        # el original en minúsculas, que es lo seguro.
        texto = original.lower()
        buscado = buscado.lower()

    salida = []
    desde = 0
    while len(salida) < POR_LIBRO:
        donde = texto.find(buscado, desde)
        if donde < 0:
            break
        inicio = max(0, donde - CONTEXTO)
        fin = min(len(original), donde + len(buscado) + CONTEXTO)
        contexto = " ".join(original[inicio:fin].split())
        salida.append(Coincidencia(libro, donde, contexto,
                                   _sitio(documento, donde, TipoMarca)))
        desde = donde + max(len(buscado), 1)
    return salida


def _sitio(documento, posicion: int, TipoMarca) -> str:
    """Dice dónde cae la coincidencia: su página, o su porcentaje."""
    try:
        if getattr(documento, "total_paginas", 0):
            indice = documento.indice_de_pagina(posicion)
            if indice >= 0:
                marca = documento.marcas.grupo(TipoMarca.SALTO_PAGINA)[indice]
                return _("Página %s") % (marca.texto or str(indice + 1))
        return "%d %%" % documento.porcentaje_en(posicion)
    except Exception:                                # pragma: no cover
        return ""


def resumen(libros) -> str:
    """Frase con lo que hay en la biblioteca, para decirla al abrirla."""
    total = len(libros)
    terminados = sum(1 for libro in libros if libro.terminado)
    empezados = sum(1 for libro in libros if libro.empezado and not libro.terminado)
    perdidos = sum(1 for libro in libros if not libro.existe)
    partes = [_("%d libros") % total]
    if terminados:
        partes.append(_("%d terminados") % terminados)
    if empezados:
        partes.append(_("%d a medias") % empezados)
    if perdidos:
        partes.append(_("%d que ya no están en su sitio") % perdidos)
    return ", ".join(partes) + "."
