# -*- coding: utf-8 -*-
"""Quedarse solo con el artículo de una página web guardada.

Una página bajada de internet llega con todo lo que la rodeaba: el menú de
navegación, el aviso de las galletas, la columna de «lo más leído», los botones
de compartir, el formulario del boletín y el pie con cincuenta enlaces.  Con la
vista, el ojo va directo al texto y no ve nada de eso.  De oído hay que
**atravesarlo entero** —a veces doscientas líneas— antes de llegar a la primera
frase del artículo, y otras tantas al final antes de saber que se ha acabado.

Esto es lo que hacen los modos de lectura de los navegadores, y es de lo que más
se agradece al abrir algo guardado de internet.

Cómo se decide qué es el artículo
---------------------------------

Por dos caminos, y en este orden:

1. **Lo que la propia página declara.**  Si trae un ``<article>`` o un
   ``<main>``, ahí está el artículo y no hay nada que adivinar.  Es lo que
   ocurre en la mayoría de las páginas hechas en los últimos diez años.

2. **Midiendo.**  Cuando no lo declara, se puntúa cada bloque por la cantidad
   de texto que tiene **descontando el que va dentro de enlaces**.  Esa resta es
   la clave: un menú de navegación puede tener mucho texto, pero es casi todo
   enlaces; un artículo tiene párrafos largos y pocos enlaces por línea.

Antes de las dos cosas se tiran los elementos que nunca son contenido —guiones,
estilos, formularios, cabeceras, pies, barras laterales— y los que se llaman a
sí mismos por su nombre: una clase o un identificador que diga «menu»,
«cookie», «sidebar» o «compartir» está diciendo lo que es.

Cuándo *no* se toca la página
-----------------------------

Aquí está la parte que evita hacer daño.  Si después de limpiar queda **menos de
la cuarta parte del texto**, se deja la página tal como estaba.  Es la señal de
que el reparto de la página no encaja con lo que este método sabe reconocer, y
en esa duda **más vale sobrar que faltar**: leer de más es incómodo, y perder la
mitad de un artículo sin enterarse es mucho peor.
"""

from __future__ import annotations

import re

from nucleo.idioma import _
from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

#: Etiquetas que nunca son el artículo.  Se van enteras, con lo que lleven
#: dentro.
FUERA = ("script", "style", "noscript", "nav", "header", "footer", "aside",
         "form", "button", "select", "iframe", "svg", "canvas", "template",
         "dialog", "menu", "figcaption")

#: Palabras que, en una clase o en un identificador, delatan lo que **no** es
#: el artículo.  Están en inglés y en español porque las dos aparecen.
RUIDO = re.compile(
    r"(?i)\b("
    r"nav|navbar|navigation|menu|menú|sidebar|side-bar|lateral|"
    r"comment|comentario|disqus|"
    r"cookie|galleta|consent|gdpr|rgpd|aviso-legal|"
    r"banner|advert|advertis|publicidad|anuncio|patrocin|sponsor|promo|"
    r"share|compartir|social|redes|"
    r"related|relacionad|recommend|recomendad|mas-leido|lo-mas|trending|popular|"
    r"newsletter|boletin|suscri|subscribe|signup|register|"
    r"breadcrumb|migas|pagination|paginacion|"
    r"footer|pie-de|header|cabecera|masthead|"
    r"modal|popup|overlay|toolbar|widget|skip-link|"
    r"hidden|screen-reader-only|sr-only|visually-hidden"
    r")\b")

#: Palabras que dicen lo contrario: aquí está el contenido.  Suman en vez de
#: restar, y evitan tirar un bloque que se llame, por ejemplo,
#: ``article-body-related-content``.
CONTENIDO = re.compile(
    r"(?i)\b(article|articulo|artículo|post|entry|content|contenido|cuerpo|"
    r"body-text|main|principal|story|noticia|texto)\b")

#: Etiquetas que pueden llegar a ser el bloque del artículo.
CANDIDATAS = ("article", "main", "div", "section", "td")

#: Proporción del texto que hay que conservar para fiarse del recorte.  Por
#: debajo de esto se deja la página entera: es la salvaguarda que impide perder
#: medio artículo por una maquetación rara.
MINIMO_CONSERVADO = 0.25

#: Caracteres mínimos para que un bloque valga como artículo.  Por debajo, lo
#: que se ha encontrado es un titular o un pie, no un texto.
LARGO_MINIMO = 400


def _nombre(elemento) -> str:
    """Nombre de la etiqueta, sin su espacio de nombres."""
    etiqueta = getattr(elemento, "tag", "")
    if not isinstance(etiqueta, str):
        return ""
    return etiqueta.rsplit("}", 1)[-1].lower()


def _senas(elemento) -> str:
    """La clase, el identificador y el papel del elemento, todo junto."""
    return " ".join(str(elemento.get(nombre, "") or "")
                    for nombre in ("class", "id", "role", "data-testid"))


def _texto_de(elemento) -> str:
    """Todo el texto que hay dentro, con los espacios normalizados."""
    return " ".join("".join(elemento.itertext()).split())


def _texto_de_enlaces(elemento) -> int:
    """Cuántos caracteres del texto van dentro de un enlace."""
    total = 0
    for hijo in elemento.iter():
        if _nombre(hijo) == "a":
            total += len(" ".join("".join(hijo.itertext()).split()))
    return total


def _puntuar(elemento) -> float:
    """Puntúa un bloque como candidato a ser el artículo.

    La puntuación es el texto que tiene **menos el que va dentro de enlaces**,
    ajustado por lo que digan su clase y su identificador.  Un menú con
    trescientos caracteres, todos en enlaces, puntúa cero; un párrafo de
    trescientos caracteres sin ningún enlace puntúa trescientos.
    """
    texto = _texto_de(elemento)
    if len(texto) < LARGO_MINIMO:
        return 0.0
    limpio = len(texto) - _texto_de_enlaces(elemento)
    if limpio <= 0:
        return 0.0
    senas = _senas(elemento)
    factor = 1.0
    if RUIDO.search(senas) and not CONTENIDO.search(senas):
        factor = 0.1
    elif CONTENIDO.search(senas):
        factor = 1.5
    # Un bloque con muchos párrafos vale más que uno con el mismo texto en un
    # solo bloque: los artículos vienen en párrafos y los menús, no.
    parrafos = sum(1 for hijo in elemento.iter() if _nombre(hijo) == "p")
    return limpio * factor * (1.0 + min(parrafos, 20) * 0.05)


def _quitar(elemento) -> None:
    """Saca un elemento de su padre conservando el texto que iba detrás."""
    padre = elemento.getparent()
    if padre is None:
        return
    cola = elemento.tail
    if cola and cola.strip():
        anterior = elemento.getprevious()
        if anterior is not None:
            anterior.tail = (anterior.tail or "") + cola
        else:
            padre.text = (padre.text or "") + cola
    padre.remove(elemento)


def _limpiar(raiz) -> None:
    """Tira de la página todo lo que nunca es el artículo."""
    for elemento in list(raiz.iter()):
        nombre = _nombre(elemento)
        if not nombre:
            continue
        if nombre in FUERA:
            _quitar(elemento)
            continue
        senas = _senas(elemento)
        if senas and RUIDO.search(senas) and not CONTENIDO.search(senas):
            # Un bloque de ruido puede llevar dentro texto de verdad si la
            # página está mal hecha; se comprueba antes de tirarlo.
            texto = _texto_de(elemento)
            if len(texto) - _texto_de_enlaces(elemento) < LARGO_MINIMO:
                _quitar(elemento)


def extraer(datos: bytes) -> bytes | None:
    """Devuelve la página quedándose solo con el artículo.

    :return: El HTML recortado, o ``None`` si no se ha podido decidir con
             seguridad y hay que dejar la página como estaba.
    """
    try:
        from lxml import html as lxml_html
    except ImportError:                              # pragma: no cover
        return None
    if not datos or not datos.strip():
        return None
    try:
        arbol = lxml_html.fromstring(datos)
    except Exception as error:
        log.debug("No se ha podido analizar la página: %s", error)
        return None

    original = len(_texto_de(arbol))
    if original < LARGO_MINIMO:
        return None            # una página corta no tiene ruido que quitar

    titulo = _titulo_de(arbol)
    _limpiar(arbol)

    mejor = None
    mejor_puntos = 0.0
    for elemento in arbol.iter():
        if _nombre(elemento) not in CANDIDATAS:
            continue
        puntos = _puntuar(elemento)
        # Los declarados por la propia página ganan siempre que tengan texto:
        # no hay nada que adivinar cuando la página lo dice.
        if _nombre(elemento) in ("article", "main") and puntos > 0:
            puntos *= 3
        if puntos > mejor_puntos:
            mejor, mejor_puntos = elemento, puntos

    if mejor is None:
        return None
    conservado = len(_texto_de(mejor))
    if conservado < original * MINIMO_CONSERVADO:
        log.info("El recorte del artículo dejaría solo el %d %% del texto: se deja "
                 "la página entera", int(conservado * 100 / max(original, 1)))
        return None

    from lxml import etree

    cuerpo = etree.tostring(mejor, encoding="unicode", method="html")
    pagina = ('<!DOCTYPE html>\n<html><head><meta charset="utf-8"/><title>%s</title>'
              "</head><body>%s%s</body></html>"
              % (_escapar(titulo), _titulo_html(titulo, mejor), cuerpo))
    log.info("Artículo extraído: %d de %d caracteres (%d %%)", conservado, original,
             int(conservado * 100 / max(original, 1)))
    return pagina.encode("utf-8")


def _titulo_html(titulo: str, bloque) -> str:
    """Pone el titular delante si el bloque elegido no lo llevaba dentro.

    Un artículo que empieza sin su título deja a quien escucha sin saber qué
    está leyendo, y el ``<h1>`` de la página suele quedarse fuera del bloque
    del cuerpo.
    """
    if not titulo:
        return ""
    for hijo in bloque.iter():
        if _nombre(hijo) in ("h1", "h2"):
            return ""
    return "<h1>%s</h1>" % _escapar(titulo)


def _titulo_de(arbol) -> str:
    """El titular de la página: su ``<h1>`` y, si no, su ``<title>``."""
    for elemento in arbol.iter():
        if _nombre(elemento) == "h1":
            texto = _texto_de(elemento)
            if texto:
                return texto[:200]
    for elemento in arbol.iter():
        if _nombre(elemento) == "title":
            texto = _texto_de(elemento)
            if texto:
                return texto[:200]
    return ""


def _escapar(texto: str) -> str:
    """Deja un texto listo para meterlo en el HTML."""
    import html as _html

    return _html.escape(texto or "", quote=False)


def descripcion() -> str:
    """Frase que explica qué hace, para la ventana de opciones."""
    return _("Quita de las páginas guardadas los menús, los avisos de galletas y las "
             "columnas laterales, y deja solo el artículo.")
