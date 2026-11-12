# -*- coding: utf-8 -*-
"""Copiar un pasaje **con su cita ya hecha**.

Es donde más tiempo se pierde escribiendo un trabajo.  Se resalta un párrafo,
se copia, y luego hay que volver al principio del libro a buscar el autor, la
editorial y el año, contar en qué página estaba y montar la referencia a mano,
con su orden y su puntuación.  Quien no ve hace ese recorrido a ciegas, saltando
de un sitio a otro del documento y perdiendo el hilo de lo que estaba
escribiendo.

Y el programa **ya sabe todo lo que hace falta**: el título, el autor, la
editorial y la fecha están en los metadatos del archivo, y la página es la marca
de página en la que cae el cursor.  Lo único que faltaba era juntarlo con la
puntuación de cada norma.

Qué estilos hay y por qué esos
------------------------------

``iso690``
    La norma española y europea (UNE-ISO 690).  Es la que piden las
    universidades españolas cuando no piden APA, y la que usan las
    bibliotecas.  Es la que viene puesta.

``apa``
    APA 7.ª edición.  Es el estilo de psicología, educación y ciencias
    sociales, y el más extendido del mundo.

``mla``
    MLA 9.ª.  Humanidades y filología.

``sencilla``
    Sin norma: autor, obra y página, en una frase que se entiende leída en voz
    alta.  Es la que sirve para un apunte propio, para un correo o para una
    reseña, que es lo que uno hace la mayoría de las veces.

Lo que no se inventa
--------------------

Un dato que el archivo no trae **no se rellena**.  Un EPUB sin editorial da una
cita sin editorial, no una cita con «s.n.» inventado.  Ponerse a suplir lo que
falta acabaría produciendo referencias falsas, y una referencia falsa en un
trabajo es peor que una incompleta: la incompleta se ve y se completa; la falsa
se cuela.

Sí se avisa de lo que falta, con :func:`lo_que_falta`, para que quien cite lo
sepa antes de pegarlo.
"""

from __future__ import annotations

import re

from .idioma import _
from .marcas import TipoMarca

#: Estilos disponibles, en el orden en que se ofrecen.
ESTILOS = ("iso690", "apa", "mla", "sencilla")

#: Cuántos caracteres del pasaje se citan como mucho.  Una cita literal más
#: larga que esto ya no es una cita: es una copia, y en un trabajo va sangrada
#: y sin comillas.  Se corta y se avisa con puntos suspensivos.
LARGO_MAXIMO = 2000

#: Un año de cuatro cifras dentro de una fecha escrita de cualquier manera
#: («2011», «2011-03-04», «4 de marzo de 2011»).
_ANO = re.compile(r"(1[0-9]{3}|20[0-9]{2}|21[0-9]{2})")

#: Partículas que acompañan al apellido y que no son ni nombre ni apellido.
PARTICULAS = frozenset(("de", "del", "la", "las", "los", "van", "von", "der",
                        "da", "di", "du", "le", "mac", "mc", "y", "e"))


def nombres() -> list[tuple[str, str]]:
    """``(clave, nombre)`` de cada estilo, para la lista del diálogo."""
    return [
        ("iso690", _("ISO 690 (la norma española y europea)")),
        ("apa", _("APA 7.ª edición")),
        ("mla", _("MLA 9.ª edición")),
        ("sencilla", _("Sencilla, para un apunte o un correo")),
    ]


#: Cómo se separan varios autores en un mismo campo: calibre los une con «&»
#: y muchos EPUB con punto y coma.
_SEPARA_AUTORES = re.compile(r"\s*[&;]\s*")


def _invertir(nombre: str) -> str:
    """Un autor escrito «Apellido, Nombre», que es como va en una cita.

    Solo se le da la vuelta cuando el nombre viene escrito «Nombre Apellido» y
    no tiene ya una coma.  Si trae «Cervantes Saavedra, Miguel de», se respeta:
    ya está en el orden bueno.
    """
    if not nombre or "," in nombre:
        return nombre
    piezas = nombre.split()
    if len(piezas) < 2:
        return nombre
    # La partícula se queda **detrás del nombre**, que es como manda la norma
    # española: «Miguel de Cervantes» se cita «Cervantes, Miguel de», y se
    # alfabetiza por la C.  Escribirlo «de Cervantes, Miguel» lo colocaría en
    # la D, que es justo lo que la regla evita.
    corte = len(piezas) - 1
    arrastradas = []
    while corte > 1 and piezas[corte - 1].lower() in PARTICULAS:
        corte -= 1
        arrastradas.insert(0, piezas[corte])
    apellidos = " ".join(piezas[corte + len(arrastradas):])
    nombre_pila = " ".join(piezas[:corte] + arrastradas)
    return "%s, %s" % (apellidos, nombre_pila)


def _abreviar(completo: str) -> str:
    """«Cervantes, Miguel de» como «Cervantes, M. de», que es lo que pide APA.

    Las partículas no se abrevian: «Cervantes, M. de» y nunca «Cervantes, M.
    D.», que sería un segundo nombre que no existe.
    """
    if "," not in completo:
        return completo
    apellidos, nombre = completo.split(",", 1)
    piezas = []
    for parte in nombre.split():
        if parte.lower() in PARTICULAS:
            piezas.append(parte.lower())
        elif parte[:1].isalpha():
            piezas.append("%s." % parte[0].upper())
    iniciales = " ".join(piezas)
    return "%s, %s" % (apellidos.strip(), iniciales) if iniciales else apellidos.strip()


def _lista(partes: list[str]) -> str:
    """«A», «A y B», «A, B y C»: varios autores como se enumeran al leer."""
    if len(partes) <= 1:
        return "".join(partes)
    return _("%(lista)s y %(ultimo)s") % {"lista": ", ".join(partes[:-1]),
                                          "ultimo": partes[-1]}


class Referencia:
    """Los datos con los que se monta una cita.

    Se saca del documento con :func:`desde_documento` y se puede montar sola en
    las pruebas, que es lo que permite comprobar cada estilo sin abrir ningún
    archivo.

    ``autor`` puede llevar varios autores separados por «&» (como los da
    calibre) o por punto y coma.  ``autor_orden`` es, si se sabe, la forma de
    cita de cada uno en el mismo orden —«Fuentes Aguirre, Armando»—: calibre la
    tiene de cada autor y los EPUB la traen en ``opf:file-as``, y es mejor que
    adivinar dónde empieza el apellido.
    """

    __slots__ = ("titulo", "autor", "editorial", "fecha", "pagina", "capitulo",
                 "identificador", "ruta", "autor_orden")

    def __init__(self, titulo: str = "", autor: str = "", editorial: str = "",
                 fecha: str = "", pagina: str = "", capitulo: str = "",
                 identificador: str = "", ruta: str = "", autor_orden: str = "") -> None:
        self.titulo = (titulo or "").strip()
        self.autor = (autor or "").strip()
        self.editorial = (editorial or "").strip()
        self.fecha = (fecha or "").strip()
        self.pagina = (pagina or "").strip()
        self.capitulo = (capitulo or "").strip()
        self.identificador = (identificador or "").strip()
        self.ruta = (ruta or "").strip()
        self.autor_orden = (autor_orden or "").strip()

    @property
    def ano(self) -> str:
        """El año solo, sacado de la fecha venga como venga."""
        encontrado = _ANO.search(self.fecha)
        return encontrado.group(1) if encontrado else ""

    def autores(self) -> list[str]:
        """Cada autor por separado, tal como se escribe su nombre."""
        return [a for a in _SEPARA_AUTORES.split(self.autor) if a]

    def autores_invertidos(self) -> list[str]:
        """Cada autor en forma de cita, «Apellido, Nombre»."""
        nombres = self.autores()
        formas = []
        if self.autor_orden:
            formas = [a for a in _SEPARA_AUTORES.split(self.autor_orden) if a]
        if len(formas) != len(nombres):
            formas = [""] * len(nombres)
        # La forma guardada solo se usa si de verdad está invertida: hay
        # bibliotecas de calibre configuradas para copiar el nombre tal cual
        # como orden, y entonces «Karina M. Soto» no dice dónde va el apellido.
        return [forma if "," in forma else _invertir(nombre)
                for nombre, forma in zip(nombres, formas)]

    def apellido_primero(self) -> str:
        """Los autores escritos «Apellido, Nombre», separados por punto y coma.

        Es la forma de la norma ISO 690 y la que mejor se alfabetiza.  Con un
        solo autor es simplemente «Cervantes, Miguel de».
        """
        return "; ".join(self.autores_invertidos())

    def inicial(self) -> str:
        """Los autores como «Apellido, N.», enumerados, que es lo que pide APA."""
        return _lista([_abreviar(forma) for forma in self.autores_invertidos()])

    def para_mla(self) -> str:
        """Los autores como los pide MLA.

        El primero invertido; con dos, el segundo en su orden natural; con tres
        o más, el primero y «et al.».
        """
        invertidos = self.autores_invertidos()
        if len(invertidos) <= 1:
            return "".join(invertidos)
        if len(invertidos) == 2:
            return _lista([invertidos[0], self.autores()[1]])
        return _("%s et al.") % invertidos[0]

    def legibles(self) -> str:
        """Los autores en orden natural, como se dicen: «Ana Pérez y Luis Gil»."""
        return _lista(self.autores())


def desde_documento(documento, posicion: int = 0) -> Referencia:
    """Saca del documento abierto todo lo que hace falta para citarlo.

    :param posicion: Punto del texto que se está citando, del que salen la
                     página y el capítulo.
    """
    metadatos = getattr(documento, "metadatos", None)
    pagina = ""
    capitulo = ""
    if documento is not None:
        try:
            if getattr(documento, "total_paginas", 0):
                indice = documento.indice_de_pagina(posicion)
                if indice >= 0:
                    marca = documento.marcas.grupo(TipoMarca.SALTO_PAGINA)[indice]
                    pagina = (marca.texto or str(indice + 1)).strip()
        except Exception:
            pagina = ""
        try:
            grupo = documento.marcas.encabezados
            indice = grupo.indice_actual(posicion)
            if indice >= 0:
                capitulo = (grupo[indice].texto or "").strip()
        except Exception:
            capitulo = ""
    return Referencia(
        titulo=getattr(metadatos, "titulo", "") or "",
        autor=getattr(metadatos, "autor", "") or "",
        editorial=getattr(metadatos, "editorial", "") or "",
        fecha=getattr(metadatos, "fecha", "") or "",
        identificador=getattr(metadatos, "identificador", "") or "",
        pagina=pagina, capitulo=capitulo,
        ruta=str(getattr(documento, "ruta_archivo", "") or ""))


def _unir(piezas, separador: str = ". ") -> str:
    """Junta las piezas que existen, sin doblar la puntuación.

    Una pieza que ya acaba en punto —«Cervantes, M. de»— no lleva otro detrás.
    Escrito se vería raro; leído en voz alta el lector de pantalla dice «punto
    punto», que es peor.
    """
    salida = ""
    for pieza in piezas:
        if not pieza:
            continue
        if not salida:
            salida = pieza
        elif salida.endswith((".", "!", "?")) and separador.startswith("."):
            salida += separador[1:] + pieza
        else:
            salida += separador + pieza
    return salida


def _cerrar(texto: str) -> str:
    """Pone el punto final, salvo que ya lo haya.

    Un autor abreviado acaba en punto —«Cervantes, M.»—, y una referencia que
    termine ahí no lleva dos.  Leído en voz alta se nota: el lector de pantalla
    dice «punto punto».
    """
    if not texto:
        return ""
    return texto if texto.endswith((".", "!", "?", ")")) else texto + "."


def referencia(datos: Referencia, estilo: str = "iso690") -> str:
    """Escribe la referencia bibliográfica en el estilo pedido."""
    if estilo == "apa":
        return _apa(datos)
    if estilo == "mla":
        return _mla(datos)
    if estilo == "sencilla":
        return _sencilla(datos)
    return _iso690(datos)


def _iso690(datos: Referencia) -> str:
    """AUTOR. *Título*. Editorial, año, p. N."""
    piezas = []
    if datos.autor:
        piezas.append(datos.apellido_primero().upper())
    if datos.titulo:
        piezas.append(datos.titulo)
    cola = ", ".join(p for p in (datos.editorial, datos.ano) if p)
    if cola:
        piezas.append(cola)
    if datos.pagina:
        piezas.append(_("p. %s") % datos.pagina)
    return _cerrar(_unir(piezas))


def _apa(datos: Referencia) -> str:
    """Apellido, N. (año). *Título*. Editorial. (p. N)"""
    piezas = []
    if datos.autor:
        piezas.append(datos.inicial())
    if datos.ano:
        piezas.append("(%s)" % datos.ano)
    if datos.titulo:
        piezas.append(datos.titulo)
    if datos.editorial:
        piezas.append(datos.editorial)
    texto = _cerrar(_unir(piezas))
    if datos.pagina:
        texto += " " + _("(p. %s)") % datos.pagina
    return texto


def _mla(datos: Referencia) -> str:
    """Apellido, Nombre. *Título*. Editorial, año, p. N."""
    piezas = []
    if datos.autor:
        piezas.append(datos.para_mla())
    if datos.titulo:
        piezas.append(datos.titulo)
    cola = ", ".join(p for p in (datos.editorial, datos.ano,
                                 _("p. %s") % datos.pagina if datos.pagina else "") if p)
    if cola:
        piezas.append(cola)
    return _cerrar(_unir(piezas))


def _sencilla(datos: Referencia) -> str:
    """La que se entiende leída en voz alta, sin puntuación de norma."""
    piezas = []
    if datos.titulo and datos.autor:
        piezas.append(_("%(titulo)s, de %(autor)s")
                      % {"titulo": datos.titulo, "autor": datos.legibles()})
    elif datos.titulo:
        piezas.append(datos.titulo)
    elif datos.autor:
        piezas.append(datos.legibles())
    if datos.capitulo:
        piezas.append(_("capítulo «%s»") % datos.capitulo)
    if datos.pagina:
        piezas.append(_("página %s") % datos.pagina)
    if datos.ano:
        piezas.append(datos.ano)
    return ", ".join(piezas)


def cita_completa(pasaje: str, datos: Referencia, estilo: str = "iso690") -> str:
    """El pasaje entrecomillado y, debajo, su referencia.

    Es lo que se copia al portapapeles: se pega en el trabajo y ya está el
    párrafo con su fuente, sin volver al libro a buscar nada.
    """
    limpio = " ".join((pasaje or "").split())
    if len(limpio) > LARGO_MAXIMO:
        limpio = limpio[:LARGO_MAXIMO].rsplit(" ", 1)[0] + "..."
    linea = referencia(datos, estilo)
    if not limpio:
        return linea
    return "«%s»\n\n%s" % (limpio, linea)


def lo_que_falta(datos: Referencia) -> list[str]:
    """Nombres de los datos que el documento no trae.

    Se dicen antes de copiar para que nadie pegue una referencia coja sin
    enterarse.  No se inventa ninguno: lo que el archivo no tiene, no está.
    """
    faltan = []
    if not datos.autor:
        faltan.append(_("el autor"))
    if not datos.titulo:
        faltan.append(_("el título"))
    if not datos.editorial:
        faltan.append(_("la editorial"))
    if not datos.ano:
        faltan.append(_("el año"))
    if not datos.pagina:
        faltan.append(_("la página"))
    return faltan
