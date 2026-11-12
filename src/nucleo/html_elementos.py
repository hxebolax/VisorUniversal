# -*- coding: utf-8 -*-
"""Reconstrucción en HTML de los elementos estructurados del libro.

El visor convierte el libro entero a texto plano y guarda la estructura aparte,
como marcas.  Eso es lo que lo hace rápido y lo que permite leerlo con las
teclas de siempre, pero tiene un límite conocido: **una tabla deja de ser una
tabla**.  En el texto es una rejilla de tabuladores, y el lector de pantalla ya
no puede usar sus órdenes de tabla —moverse por filas y columnas, oír el
encabezado de cada celda— porque para él ahí no hay ninguna tabla.

Este módulo deshace ese camino para un elemento concreto: coge la marca y
reconstruye el HTML semántico correspondiente.  Ese HTML se muestra después en
un visor de verdad (:mod:`interfaz.dialogos.visor_html`), donde el lector de
pantalla lo trata como lo que es y se navega igual que en una página web.

Se reconstruyen los tres elementos donde la estructura importa de verdad:

* **tablas**: filas, columnas y encabezados;
* **listas**, incluidas las anidadas, distinguiendo las ordenadas;
* **citas** en bloque.

El HTML se genera a mano, sin plantillas ni bibliotecas: son unas pocas
etiquetas y así se controla exactamente qué sale.
"""

from __future__ import annotations

import html
import json
import re

from .idioma import _
from .marcas import (ENCABEZADOS, Marca, TipoMarca, es_encabezado,
                     nivel_de_encabezado)
from .registro import obtener_registro
from version import NOMBRE

log = obtener_registro(__name__)

#: Tipos de marca que este módulo sabe convertir a HTML.
#:
#: Las imágenes están aquí desde que se pueden sacar **los datos** de un
#: gráfico: una figura con su tabla de valores es justo el caso en el que ver el
#: elemento como HTML cambia las cosas, porque la tabla se recorre entonces con
#: las órdenes de tabla del lector de pantalla en vez de oírse como una frase.
CONVERTIBLES = (TipoMarca.TABLA, TipoMarca.LISTA, TipoMarca.CITA, TipoMarca.FORMULA,
                TipoMarca.CODIGO, TipoMarca.IMAGEN, TipoMarca.FIGURA)

#: Detecta el número o la letra con la que el conversor abre un elemento de
#: lista ordenada («3. », «iv. », «b. »).  Se usa para saber si la lista era
#: ordenada, dato que el texto plano conserva pero las marcas no.
_ORDENADA = re.compile(r"^\s*(\d+|[ivxlcdm]+|[a-z]|[IVXLCDM]+|[A-Z])[.)]\s")

#: Hoja de estilo del documento que se guarda en disco.  Es deliberadamente
#: sobria y usa los colores del sistema, de modo que respete el alto contraste
#: de Windows igual que el resto del programa.
ESTILOS = """
.formula { font-size: 1.4em; margin: 1em 0; overflow-x: auto; }
math { font-size: 1.4em; }
.pagina { color: GrayText; font-size: 0.9em; margin: 0.6em 0; }
  :root { color-scheme: light dark; }
  body { font-family: system-ui, Segoe UI, Arial, sans-serif; font-size: 1.05rem;
         line-height: 1.6; margin: 0 auto; padding: 1.5rem; max-width: 60rem; }
  caption { text-align: left; font-weight: bold; padding-bottom: 0.5rem; }
  table { border-collapse: collapse; width: 100%; }
  th, td { border: 1px solid GrayText; padding: 0.4rem 0.6rem; text-align: left;
           vertical-align: top; }
  th { background: Field; }
  table.datos caption { font-size: 1.1em; }
  figure { margin: 1em 0; }
  figcaption { font-weight: bold; margin-bottom: 0.4rem; }
  blockquote { border-left: 4px solid GrayText; margin-left: 0; padding-left: 1rem; }
  .procedencia { color: GrayText; font-size: 0.9rem; border-top: 1px solid GrayText;
                 margin-top: 2rem; padding-top: 0.5rem; }
  .codigo { position: relative; margin: 1em 0; }
  .codigo pre { background: Field; border: 1px solid GrayText; border-radius: 6px;
                padding: 0.8rem; overflow-x: auto; margin: 0; }
  .codigo code { font-family: Consolas, Menlo, monospace; font-size: 0.95em;
                 white-space: pre; }
  .codigo .copiar { float: right; margin: 0 0 0.3rem 0.5rem; padding: 0.25rem 0.7rem;
                    font: inherit; font-size: 0.9em; cursor: pointer; }
  .aviso-copia { color: GrayText; font-size: 0.9rem; min-height: 1.2em; }
  @media (forced-colors: active) { th, td { border: 1px solid CanvasText; }
                                   .codigo pre { border: 1px solid CanvasText; } }
"""


def _escapar(texto: str) -> str:
    """Deja un texto listo para meterlo en el HTML."""
    return html.escape(texto or "", quote=False)


# ---------------------------------------------------------------------------
# Tablas
# ---------------------------------------------------------------------------

def rejilla_de(marca: Marca) -> list[list[str]]:
    """Devuelve la tabla como lista de filas de celdas.

    El conversor guarda la rejilla completa en ``referencia``, con las filas
    separadas por saltos de línea y las celdas por tabuladores, para que la
    tabla siga estando disponible aunque en el texto solo aparezca el rótulo
    ``[Tabla]``.
    """
    crudo = marca.referencia or ""
    return [linea.split("\t") for linea in crudo.split("\n") if linea != ""]


def html_de_tabla(marca: Marca) -> str:
    """Reconstruye una tabla del libro como una tabla HTML de verdad.

    La primera fila se toma como encabezado (``<th scope="col">``), que es lo
    que hace que el lector de pantalla anuncie «Columna, Precio» al moverse por
    las celdas.  Las marcas no guardan qué celdas eran ``th`` en el EPUB
    original, así que es una suposición; acierta en la inmensa mayoría de las
    tablas y no estropea nada cuando falla, porque el contenido se lee igual.
    """
    filas = rejilla_de(marca)
    if not filas:
        return "<p>Esta tabla no tiene contenido legible.</p>"
    columnas = max(len(fila) for fila in filas)
    titulo = (marca.texto or "").strip()

    partes = ["<table>"]
    if titulo:
        partes.append("<caption>%s</caption>" % _escapar(titulo))
    if len(filas) > 1:
        partes.append("<thead><tr>")
        for numero in range(columnas):
            celda = filas[0][numero] if numero < len(filas[0]) else ""
            partes.append('<th scope="col">%s</th>' % _escapar(celda))
        partes.append("</tr></thead>")
        cuerpo = filas[1:]
    else:
        cuerpo = filas
    partes.append("<tbody>")
    for fila in cuerpo:
        partes.append("<tr>")
        for numero in range(columnas):
            celda = fila[numero] if numero < len(fila) else ""
            partes.append("<td>%s</td>" % _escapar(celda))
        partes.append("</tr>")
    partes.append("</tbody></table>")
    partes.append('<p class="procedencia">%d filas por %d columnas.</p>'
                  % (len(filas), columnas))
    return "".join(partes)


# ---------------------------------------------------------------------------
# Listas
# ---------------------------------------------------------------------------

def elementos_de_lista(documento, marca: Marca) -> list[tuple[int, str, bool]]:
    """Devuelve los elementos de una lista: ``(nivel, texto, ordenado)``.

    Los elementos son las marcas :data:`TipoMarca.ELEMENTO_LISTA` que caen
    dentro del tramo que ocupa la lista.  Que un elemento pertenezca a una
    lista ordenada no está en las marcas, pero sí en el texto: el conversor
    escribe «1. » o «• » delante de cada uno, así que se deduce de ahí.
    """
    inicio = marca.posicion
    fin = inicio + max(marca.longitud, 1)
    elementos: list[tuple[int, str, bool]] = []
    for hijo in documento.marcas.grupo(TipoMarca.ELEMENTO_LISTA).marcas:
        if hijo.posicion < inicio:
            continue
        if hijo.posicion >= fin:
            break
        linea = documento.texto_de_linea(hijo.posicion)
        elementos.append((max(hijo.nivel, 1), (hijo.texto or "").strip(),
                          bool(_ORDENADA.match(linea))))
    return elementos


def html_de_lista(documento, marca: Marca) -> str:
    """Reconstruye una lista del libro, con su anidamiento y su clase.

    Se recorre la lista de elementos llevando la cuenta del nivel: al subir se
    abre una lista dentro del último elemento —que es como se anida en HTML y
    lo que hace que el lector de pantalla anuncie «lista dentro de lista,
    nivel 2»—, y al bajar se cierran las que hagan falta.
    """
    elementos = elementos_de_lista(documento, marca)
    if not elementos:
        return "<p>Esta lista no tiene elementos legibles.</p>"

    partes: list[str] = []
    #: Listas abiertas ahora mismo, como ``(nivel, era_ordenada)``.
    pila: list[tuple[int, bool]] = []

    def cerrar_una() -> None:
        """Cierra la lista más interna, con el elemento que la contiene."""
        _nivel, ordenada = pila.pop()
        partes.append("</li>")
        partes.append("</ol>" if ordenada else "</ul>")

    for nivel, texto, ordenada in elementos:
        while pila and pila[-1][0] > nivel:
            cerrar_una()
        if pila and pila[-1][0] == nivel:
            partes.append("</li>")           # el elemento anterior era hermano
        else:
            # Se abre una lista: la primera, o una anidada.  Si es anidada va
            # **dentro** del elemento que la precede, que por eso se deja sin
            # cerrar: es lo que hace que el lector anuncie «nivel 2».
            partes.append("<ol>" if ordenada else "<ul>")
            pila.append((nivel, ordenada))
        partes.append("<li>%s" % _escapar(texto))
    while pila:
        cerrar_una()
    partes.append('<p class="procedencia">%d elementos.</p>' % len(elementos))
    return "".join(partes)


# ---------------------------------------------------------------------------
# Citas
# ---------------------------------------------------------------------------

def html_de_cita(documento, marca: Marca) -> str:
    """Reconstruye una cita en bloque, con un párrafo por línea."""
    inicio = marca.posicion
    fin = min(inicio + max(marca.longitud, 1), len(documento.texto))
    parrafos = [linea.strip() for linea in documento.texto[inicio:fin].split("\n")]
    parrafos = [parrafo for parrafo in parrafos if parrafo]
    if not parrafos:
        return "<p>Esta cita no tiene contenido legible.</p>"
    cuerpo = "".join("<p>%s</p>" % _escapar(parrafo) for parrafo in parrafos)
    return "<blockquote>%s</blockquote>" % cuerpo


def html_de_codigo(documento, marca: Marca, indice: int = 0) -> str:
    """Reconstruye un bloque de código tal cual está, con su botón de copiar.

    Se escribe dentro de ``<pre><code>`` y **sin tocar ni un espacio**: la
    sangría de un listado no es presentación, es lo que dice qué va dentro de
    qué.  Por eso este es el único elemento del visor cuyo contenido no se
    normaliza.

    El botón de copiar es un ``<button>`` de verdad —no un adorno con un
    ``onclick``—, así que se alcanza con el tabulador y el lector de pantalla lo
    anuncia como botón.  Al pulsarlo no copia la página desde el propio
    navegador: avisa a la aplicación, que copia el código exacto con el
    portapapeles del sistema.  El motivo es que la página se carga sin origen
    y ahí el portapapeles del navegador no está disponible.
    """
    inicio = marca.posicion
    fin = min(inicio + max(marca.longitud, 1), len(documento.texto))
    codigo = documento.texto[inicio:fin].rstrip("\n")
    if not codigo.strip():
        return "<p>%s</p>" % _escapar(_("Este bloque de código está vacío."))
    lenguaje = (marca.referencia or "").strip()
    rotulo = _("Copiar el código")
    if lenguaje:
        rotulo = _("Copiar el código %s") % (lenguaje[:1].upper() + lenguaje[1:])
    return (
        '<div class="codigo">'
        '<button type="button" class="copiar" data-codigo="%d">%s</button>'
        '<pre><code%s>%s</code></pre>'
        "</div>"
    ) % (indice, _escapar(rotulo),
         ' class="language-%s"' % _escapar(lenguaje) if lenguaje else "",
         _escapar(codigo))


def guion_copiar() -> str:
    """Guión del botón de copiar, para meterlo al final de la página.

    Va dentro de la propia página porque el visor no admite guión por fuera, y
    sirve para los dos sitios donde esa página acaba:

    * **Dentro del programa**, donde avisa por el mismo puente que ya usa la
      tecla Escape y copia la aplicación.  Hace falta porque la página se carga
      sin origen, y en esas condiciones el portapapeles del navegador no está
      disponible.
    * **En la página guardada**, abierta después en un navegador de verdad,
      donde no hay puente y copia el navegador.  Se prueba primero el
      portapapeles moderno y, si no está, el de toda la vida.

    El aviso de que se ha copiado se escribe en una región activa para que el
    lector de pantalla lo diga: un botón que no contesta parece un botón roto.
    """
    hecho = json.dumps(_("Código copiado al portapapeles."))
    fallo = json.dumps(_("No se ha podido copiar."))
    return (
        "<script>(function(){"
        "function avisar(b,t){var a=document.getElementById('aviso-copia');"
        "if(a){a.textContent=t;}b.focus();}"
        "document.addEventListener('click',function(e){"
        "var b=e.target.closest&&e.target.closest('button.copiar');"
        "if(!b)return;e.preventDefault();"
        "if(window.visor&&window.visor.postMessage){"
        "window.visor.postMessage(JSON.stringify("
        "{type:'copiar',indice:parseInt(b.getAttribute('data-codigo'),10)||0}));return;}"
        "var p=b.parentNode.querySelector('pre');if(!p)return;var t=p.textContent;"
        "if(navigator.clipboard&&navigator.clipboard.writeText){"
        "navigator.clipboard.writeText(t).then(function(){avisar(b,HECHO);},"
        "function(){avisar(b,FALLO);});return;}"
        "var s=document.createElement('textarea');s.value=t;document.body.appendChild(s);"
        "s.select();var ok=false;try{ok=document.execCommand('copy');}catch(x){}"
        "document.body.removeChild(s);avisar(b,ok?HECHO:FALLO);"
        "});})();</script>"
        '<p id="aviso-copia" role="status" aria-live="polite" class="aviso-copia"></p>'
    ).replace("HECHO", hecho).replace("FALLO", fallo)


def codigos_de(cuerpo: str) -> list[str]:
    """Saca de un cuerpo HTML el texto de cada bloque de código, en orden.

    Se lee del propio HTML que se está enseñando en lugar de llevar una lista
    en paralelo: así lo que se copia y lo que se ve no pueden separarse, por
    mucho que cambie luego cómo se escribe la página.
    """
    return [html.unescape(trozo) for trozo in re.findall(
        r"<pre><code[^>]*>(.*?)</code></pre>", cuerpo or "", re.DOTALL)]


# ---------------------------------------------------------------------------
# Puerta de entrada
# ---------------------------------------------------------------------------

def html_de_formula(marca: Marca) -> str:
    """Devuelve el MathML original de una fórmula, listo para el navegador.

    El MathML se guardó entero al analizar el libro justamente para esto: aquí
    llega intacto al lector de pantalla, que lo lee con su propio motor
    matemático y deja recorrer la fórmula parte por parte, que es la única
    forma de entender una ecuación larga de oído.

    Debajo se pone también la versión leída que aparece en el texto, por si el
    lector de pantalla que se esté usando no sabe de MathML: así siempre hay
    algo que oír.
    """
    mathml = (marca.referencia or "").strip()
    partes = []
    if mathml:
        partes.append('<div class="formula">%s</div>' % mathml)
    if marca.texto.strip():
        partes.append("<p><em>%s</em> %s</p>"
                      % (_escapar(_("Leída:")), _escapar(marca.texto.strip())))
    if not partes:
        partes.append("<p>%s</p>" % _escapar(_("La fórmula no se pudo recuperar.")))
    return "\n".join(partes)


def se_puede_convertir(marca: Marca, documento=None) -> bool:
    """Indica si de esa marca se puede sacar HTML.

    Con las imágenes hay una condición más: que tengan **algo que enseñar**.
    Una ilustración sin texto alternativo, sin descripción guardada y sin datos
    daría una página en blanco, y abrir una ventana para no enseñar nada es
    peor que decir que ahí no hay nada que ver.

    :param documento: Si se pasa, se mira también lo que se haya guardado de la
                      imagen (la descripción de la IA y la tabla del gráfico).
    """
    if marca is None or marca.tipo not in CONVERTIBLES:
        return False
    if marca.tipo not in (TipoMarca.IMAGEN, TipoMarca.FIGURA):
        return True
    if (marca.texto or "").strip():
        return True
    anotada = _anotacion_de(documento, marca) if documento is not None else None
    return bool(anotada is not None
                and ((anotada.texto or "").strip() or anotada.tiene_datos))


def titulo_de(marca: Marca) -> str:
    """Frase con la que se nombra el elemento en la ventana y en el archivo."""
    nombres = {TipoMarca.TABLA: "Tabla", TipoMarca.LISTA: "Lista", TipoMarca.CITA: "Cita",
               TipoMarca.FORMULA: "Fórmula", TipoMarca.CODIGO: _("Bloque de código"),
               TipoMarca.IMAGEN: "Imagen", TipoMarca.FIGURA: "Figura"}
    nombre = nombres.get(marca.tipo, "Elemento")
    if marca.tipo is TipoMarca.CODIGO:
        # Del código interesa el lenguaje, no la primera línea: «Bloque de
        # código: import os» no dice nada, y «Bloque de código Python» sí.
        # El lenguaje se escribe como lo declara el documento salvo la
        # inicial: «bloque de código python» se lee peor que «Python».
        lenguaje = (marca.referencia or "").strip()
        if lenguaje:
            return "%s %s" % (nombre, lenguaje[:1].upper() + lenguaje[1:])
        return nombre
    detalle = (marca.texto or "").strip()
    return "%s: %s" % (nombre, detalle[:80]) if detalle else nombre


def cuerpo_html(documento, marca: Marca) -> str:
    """Devuelve el HTML del elemento, sin la envoltura del documento."""
    if marca.tipo is TipoMarca.TABLA:
        return html_de_tabla(marca)
    if marca.tipo is TipoMarca.LISTA:
        return html_de_lista(documento, marca)
    if marca.tipo is TipoMarca.FORMULA:
        return html_de_formula(marca)
    if marca.tipo is TipoMarca.CITA:
        return html_de_cita(documento, marca)
    if marca.tipo is TipoMarca.CODIGO:
        return html_de_codigo(documento, marca) + guion_copiar()
    if marca.tipo in (TipoMarca.IMAGEN, TipoMarca.FIGURA):
        return html_de_imagen(documento, marca)
    return "<p>Este elemento no se puede mostrar como HTML.</p>"


# ---------------------------------------------------------------------------
# Un capítulo entero
# ---------------------------------------------------------------------------

def limites_del_capitulo(documento, posicion: int) -> tuple:
    """Devuelve ``(inicio, fin, título)`` del capítulo donde cae esa posición.

    Se usan los saltos de sección, que es lo que separa los archivos de un
    EPUB; si el documento no los trae —un PDF, un texto suelto— se prueba con
    los encabezados de nivel 1, y si tampoco, el documento entero es el
    capítulo.
    """
    texto = documento.texto
    for tipo in (TipoMarca.SALTO_SECCION, TipoMarca.ENCABEZADO1):
        grupo = documento.marcas.grupo(tipo)
        if len(grupo) < 2:
            continue
        inicio, fin, titulo = 0, len(texto), ""
        for marca in grupo.marcas:
            if marca.posicion <= posicion:
                inicio, titulo = marca.posicion, marca.texto.strip()
            else:
                fin = marca.posicion
                break
        return inicio, fin, titulo
    # Sin cortes con los que repartir, el capítulo es el documento entero.  Su
    # título es el del primer encabezado, si lo hay: el del documento vale para
    # el libro, pero aquí lo que se está viendo es su contenido.
    for tipo in ENCABEZADOS:
        grupo = documento.marcas.grupo(tipo)
        if len(grupo):
            titulo = grupo.marcas[0].texto.strip()
            if titulo:
                return 0, len(texto), titulo
    return 0, len(texto), documento.metadatos.titulo


def html_de_capitulo(documento, posicion: int) -> tuple:
    """Reconstruye el capítulo donde cae esa posición.  Devuelve ``(título, cuerpo)``."""
    inicio, fin, titulo = limites_del_capitulo(documento, posicion)
    cuerpo = html_de_tramo(documento, inicio, fin, primero_es_titulo=True)
    if not cuerpo:
        cuerpo = "<p>%s</p>" % _escapar(_("Este capítulo no tiene texto."))
    return (titulo or _("Capítulo"), cuerpo)


def html_de_tramo(documento, inicio: int, fin: int, primero_es_titulo: bool = False,
                  con_anclas: bool = False) -> str:
    """Reconstruye como HTML de verdad el tramo de documento que se le pida.

    Esto deshace lo que la conversión a texto tuvo que aplanar: los
    encabezados vuelven a ser encabezados, las listas listas, las tablas
    tablas y las fórmulas fórmulas.  Lo usa el visor de elementos para enseñar
    un capítulo, y la exportación para escribir un EPUB que se pueda recorrer
    igual que el original.

    :param primero_es_titulo: Si la primera línea con texto que no traiga marca
                              propia se escribe como encabezado de nivel uno.
                              Vale para un capítulo, cuyo título suele ser esa
                              línea; no vale para un documento entero.
    :param con_anclas: Si cada encabezado lleva un ``id`` con el que poder
                       enlazarlo.  Hace falta para que el índice de un EPUB
                       exportado lleve de verdad a cada capítulo.
    """
    texto = documento.texto
    fin = min(fin, len(texto))

    # Marcas que empiezan dentro del tramo, agrupadas por posición.  Se
    # consulta por posición y no recorriendo la lista entera en cada línea:
    # un capítulo largo tiene miles de líneas y cientos de marcas.
    porPosicion: dict = {}
    for tipo in (list(ENCABEZADOS) + [TipoMarca.LISTA, TipoMarca.TABLA, TipoMarca.CITA,
                                      TipoMarca.FORMULA, TipoMarca.SALTO_PAGINA,
                                      TipoMarca.SEPARADOR, TipoMarca.CODIGO,
                                      TipoMarca.IMAGEN, TipoMarca.FIGURA]):
        for marca in documento.marcas.grupo(tipo).marcas:
            if inicio <= marca.posicion < fin:
                porPosicion.setdefault(marca.posicion, []).append(marca)

    partes: list = []
    primera_util = primero_es_titulo
    bloques_de_codigo = 0
    numero_de_ancla = 0

    posicion_actual = inicio
    saltar_hasta = inicio
    while posicion_actual < fin:
        final_linea = texto.find("\n", posicion_actual)
        if final_linea < 0 or final_linea > fin:
            final_linea = fin
        linea = texto[posicion_actual:final_linea]

        if posicion_actual < saltar_hasta:
            # Dentro de un bloque que ya se ha escrito entero —una lista, una
            # tabla, un trozo de código— puede haber quedado una imagen: se
            # escribe detrás del bloque para no perderla.  Perder una imagen es
            # perder su descripción, que muchas veces es lo único que dice qué
            # hay ahí.
            for marca in porPosicion.get(posicion_actual, ()):
                if marca.tipo in (TipoMarca.IMAGEN, TipoMarca.FIGURA):
                    partes.append(_imagen_a_html(documento, marca))
            posicion_actual = final_linea + 1
            continue

        marcas_aqui = porPosicion.get(posicion_actual, [])
        escrito = False

        # Los saltos de página y los separadores se escriben **antes y aparte**:
        # no son contenido, son señales puestas en un sitio, y en ese mismo
        # sitio puede haber además una imagen o un título.  Mezclarlos con lo
        # demás en un solo bucle hacía que el primero que apareciera se llevara
        # la línea entera: en un PDF, veinticinco imágenes caían justo en un
        # salto de página y se perdían las veinticinco.
        for marca in marcas_aqui:
            if marca.tipo is TipoMarca.SEPARADOR:
                partes.append("<hr/>")
            elif marca.tipo is TipoMarca.SALTO_PAGINA:
                rotulo = marca.texto.strip()
                partes.append('<p class="pagina">%s</p>'
                              % _escapar(_("Página %s") % rotulo if rotulo else _("Página")))

        for marca in marcas_aqui:
            if marca.tipo is TipoMarca.TABLA:
                partes.append(html_de_tabla(marca))
                saltar_hasta = marca.posicion + max(marca.longitud, 1)
                escrito = True
                break
            if marca.tipo is TipoMarca.LISTA:
                partes.append(html_de_lista(documento, marca))
                saltar_hasta = marca.posicion + max(marca.longitud, 1)
                escrito = True
                break
            if marca.tipo is TipoMarca.CITA:
                partes.append(html_de_cita(documento, marca))
                saltar_hasta = marca.posicion + max(marca.longitud, 1)
                escrito = True
                break
            if marca.tipo is TipoMarca.FORMULA:
                partes.append(html_de_formula(marca))
                escrito = True
                break
            if marca.tipo is TipoMarca.CODIGO:
                partes.append(html_de_codigo(documento, marca, bloques_de_codigo))
                bloques_de_codigo += 1
                saltar_hasta = marca.posicion + max(marca.longitud, 1)
                escrito = True
                break
            if marca.tipo in (TipoMarca.IMAGEN, TipoMarca.FIGURA):
                partes.append(_imagen_a_html(documento, marca))
                escrito = True
                break
            if es_encabezado(marca.tipo):
                # El nivel se respeta tal cual: como el título del capítulo no
                # se escribe aparte, no hay ningún encabezado por encima que
                # obligue a desplazarlos.
                nivel = nivel_de_encabezado(marca.tipo)
                ancla = ""
                if con_anclas:
                    numero_de_ancla += 1
                    ancla = ' id="t%d"' % numero_de_ancla
                partes.append("<h%d%s>%s</h%d>"
                              % (nivel, ancla, _escapar(linea.strip()), nivel))
                escrito = True
                break
            if marca.tipo in (TipoMarca.SEPARADOR, TipoMarca.SALTO_PAGINA):
                # Ya se han escrito arriba; aquí solo cuentan como «había algo»
                # para que una línea vacía con un salto de página no acabe
                # escribiéndose además como párrafo.
                escrito = escrito or not linea.strip()
                continue

        if not escrito and linea.strip():
            etiqueta = "h1" if primera_util else "p"
            ancla = ""
            if etiqueta == "h1" and con_anclas:
                numero_de_ancla += 1
                ancla = ' id="t%d"' % numero_de_ancla
            partes.append("<%s%s>%s</%s>"
                          % (etiqueta, ancla, _escapar(linea.strip()), etiqueta))
            escrito = True
        if escrito and linea.strip():
            primera_util = False
        posicion_actual = final_linea + 1

    if bloques_de_codigo:
        partes.append(guion_copiar())
    return "\n".join(partes)


def _anotacion_de(documento, marca):
    """Devuelve lo que se haya guardado de esa imagen, o ``None``.

    La colección se guarda pegada al documento la primera vez que se pide.  Sin
    esa memoria, exportar un libro con cien imágenes leía cien veces el mismo
    archivo de descripciones del disco, una por imagen.
    """
    from . import descripciones

    if documento is None:
        return None
    coleccion = getattr(documento, "_descripciones_html", None)
    if coleccion is None:
        try:
            coleccion = descripciones.Coleccion(getattr(documento, "ruta_archivo", ""))
        except Exception as error:                     # pragma: no cover
            log.debug("No se han podido leer las descripciones: %s", error)
            return None
        try:
            documento._descripciones_html = coleccion
        except Exception:
            pass          # un documento de prueba puede no admitir atributos
    try:
        return coleccion.obtener(marca.referencia or "")
    except Exception:                                  # pragma: no cover
        return None


def html_de_esquema(esquema) -> str:
    """Escribe un diagrama de flujo como **lista anidada**, no como párrafo.

    Es lo que lo hace recorrible: el lector de pantalla anuncia la lista, dice
    en qué nivel está y salta de elemento en elemento con sus propias órdenes.
    Un párrafo con flechas escritas con guiones se oye entero o no se oye.

    Cada nivel más adentro es un paso al que se llega desde el de fuera, y el
    rótulo de la flecha —«sí», «no»— va delante del paso al que lleva, que es lo
    que convierte un rombo de decisión en dos caminos que se pueden seguir por
    separado.

    Debajo va **la lista de cajas numerada**, porque el recorrido corta los
    bucles diciendo «vuelve al paso 3» y ese número tiene que poder buscarse.
    """
    if not esquema:
        return ""
    partes = []
    titulo = esquema.titulo or _("Diagrama")
    if esquema.tipo:
        titulo = "%s (%s)" % (titulo, esquema.tipo)
    partes.append("<h1>%s</h1>" % _escapar(titulo))
    partes.append("<p>%s</p>" % _escapar(esquema.resumen()))

    partes.append("<h2>%s</h2>" % _escapar(_("Por dónde se va")))
    partes.extend(_lista_del_recorrido(esquema.recorrido()))

    partes.extend(_silueta_del_esquema(esquema))

    partes.append("<h2>%s</h2>" % _escapar(_("Las cajas, una a una")))
    partes.append("<ol>")
    for caja in esquema.cajas:
        partes.append("<li>%s</li>" % _escapar(caja.nombre()))
    partes.append("</ol>")

    if esquema.nota:
        partes.append("<p><em>%s</em> %s</p>"
                      % (_escapar(_("Nota:")), _escapar(esquema.nota)))
    aviso = esquema.aviso() if hasattr(esquema, "aviso") else ""
    if aviso:
        # Debajo y no encima, por lo mismo que en la tabla de un gráfico: quien
        # vuelve a consultar el diagrama ya lo leyó la primera vez.
        partes.append("<p><strong>%s</strong> %s</p>"
                      % (_escapar(_("Cuidado con este diagrama:")),
                         _escapar(aviso)))
    return "\n".join(partes)


def _silueta_del_esquema(esquema) -> list[str]:
    """El diagrama dibujado en braille, para palparlo de un vistazo.

    Va **debajo del recorrido y encima de la lista de cajas**: quien viene a
    seguir el procedimiento ya lo ha leído arriba, y esto es lo otro —la forma—,
    que se mira una vez y sitúa todo lo demás.
    """
    from nucleo import braille_grafico

    try:
        cajas, flechas = esquema.planta()
    except Exception:                                    # pragma: no cover
        return []
    if len(cajas) < 2:
        return []
    dibujo = str(braille_grafico.esquema(cajas, flechas))
    if not dibujo.strip():
        return []
    return ["<h2>%s</h2>" % _escapar(_("La forma del diagrama")),
            "<p>%s</p>" % _escapar(_(
                "Dibujado en braille de ocho puntos, para leerlo con los dedos "
                "en una línea braille de celdas gráficas. Cada cuadradito es "
                "una caja, numeradas de arriba abajo como en la lista de "
                "abajo, y cada raya es una flecha.")),
            "<pre>%s</pre>" % _escapar(dibujo)]


def _lista_del_recorrido(pasos) -> list[str]:
    """Convierte los pasos con su nivel en listas ordenadas anidadas.

    La sublista va **dentro** del ``<li>`` del que cuelga y no detrás: es lo que
    hace que el lector de pantalla anuncie «nivel 2» en lugar de leer dos listas
    seguidas sin relación entre ellas.  La recursión no se desboca porque el
    recorrido corta a los ocho niveles.
    """
    if not pasos:
        return []

    def escribir(indice: int, nivel: int):
        partes = ["<ol>"]
        while indice < len(pasos) and pasos[indice][0] == nivel:
            partes.append("<li>%s" % _escapar(pasos[indice][1]))
            indice += 1
            if indice < len(pasos) and pasos[indice][0] == nivel + 1:
                hijos, indice = escribir(indice, nivel + 1)
                partes.extend(hijos)
            partes.append("</li>")
        partes.append("</ol>")
        return partes, indice

    partes, _fin = escribir(0, 0)
    return partes


def html_de_grafico(grafico) -> str:
    """Escribe los datos sacados de un gráfico como una tabla de verdad.

    Es todo el sentido de sacarlos: una descripción se oye como una frase y se
    olvida, y una tabla se recorre celda a celda oyendo el encabezado de cada
    columna.  Lo que se ve aquí es exactamente lo que la IA leyó del gráfico, ni
    redondeado ni retocado.
    """
    if not grafico:
        return ""
    filas = grafico.filas
    columnas = max(len(fila) for fila in filas)
    partes = ['<table class="datos">']
    titulo = grafico.titulo or _("Datos del gráfico")
    if grafico.unidades:
        titulo = "%s (%s)" % (titulo, grafico.unidades)
    partes.append("<caption>%s</caption>" % _escapar(titulo))
    partes.append("<thead><tr>")
    for celda in filas[0] + [""] * (columnas - len(filas[0])):
        partes.append('<th scope="col">%s</th>' % _escapar(celda))
    partes.append("</tr></thead><tbody>")
    for fila in filas[1:]:
        partes.append("<tr>")
        for numero, celda in enumerate(fila + [""] * (columnas - len(fila))):
            # La primera columna es la categoría —el año, el país, la
            # categoría—, y marcarla como encabezado de fila es lo que hace que
            # el lector de pantalla diga «2024, ventas, 1.200» en lugar de
            # cantar un número suelto sin saber de qué.
            etiqueta = 'th scope="row"' if numero == 0 else "td"
            cierre = "th" if numero == 0 else "td"
            partes.append("<%s>%s</%s>" % (etiqueta, _escapar(celda), cierre))
        partes.append("</tr>")
    partes.append("</tbody></table>")
    if grafico.nota:
        partes.append("<p><em>%s</em> %s</p>"
                      % (_escapar(_("Nota:")), _escapar(grafico.nota)))
    # El aviso va **debajo de la tabla y no encima**: encima habría que
    # atravesarlo cada vez que se abre, y quien viene a consultar un número ya
    # lo ha leído la primera vez. Debajo se encuentra al terminar de recorrerla,
    # que es cuando uno decide si se fía.
    aviso = grafico.aviso() if hasattr(grafico, "aviso") else ""
    if aviso:
        partes.append("<p><strong>%s</strong> %s</p>"
                      % (_escapar(_("Cuidado con estos datos:")), _escapar(aviso)))
    partes.extend(_forma_del_grafico(grafico))
    return "\n".join(partes)


def _numeros_de(grafico) -> list:
    """Los números de la primera columna numérica que tenga la tabla.

    Se busca **la primera columna que sean números de arriba abajo**, no la
    segunda por costumbre: hay tablas cuya primera columna es el año, que
    también son números, y dibujar los años como una curva daría una recta que
    no dice nada. Se salta la primera columna, que es la de las categorías.
    """
    filas = [fila for fila in grafico.filas[1:] if fila]
    if len(filas) < 2:
        return []
    ancho = max(len(fila) for fila in filas)
    for columna in range(1, ancho):
        valores = []
        for fila in filas:
            if columna >= len(fila):
                valores = []
                break
            numero = _como_numero(fila[columna])
            if numero is None:
                valores = []
                break
            valores.append(numero)
        if len(valores) >= 2:
            return valores
    return []


def _todas_las_series(grafico) -> list:
    """Todas las columnas de números que tenga la tabla, no solo la primera.

    Un gráfico con dos líneas cuenta **la comparación** entre ellas, y dibujar
    solo una es contar la mitad. Se cogen hasta tres: con cuatro, los puntos se
    pisan y lo que queda bajo el dedo es una mancha.
    """
    from nucleo.braille_grafico import MARCAS_DE_SERIE

    filas = [fila for fila in grafico.filas[1:] if fila]
    if len(filas) < 2:
        return []
    ancho = max(len(fila) for fila in filas)
    series = []
    for columna in range(1, ancho):
        valores = []
        for fila in filas:
            numero = (_como_numero(fila[columna]) if columna < len(fila)
                      else None)
            if numero is None:
                valores = []
                break
            valores.append(numero)
        if len(valores) >= 2:
            series.append(valores)
        if len(series) >= MARCAS_DE_SERIE:
            break
    return series


def _nombres_de_serie(grafico, cuantas: int) -> list:
    """Cómo se llama cada serie, de la fila de encabezados."""
    if not grafico.filas:
        return []
    cabecera = grafico.filas[0]
    return [cabecera[numero].strip() if numero < len(cabecera) else ""
            for numero in range(1, cuantas + 1)]


def _como_numero(celda: str):
    """Convierte el texto de una celda en un número, o devuelve ``None``.

    Se admiten las dos formas de escribirlos que salen en un gráfico —«1.240,5»
    y «1,240.5»— y los que traen unidad pegada: «45 %», «12 €».
    """
    texto = (celda or "").strip()
    if not texto:
        return None
    texto = texto.replace("\u00a0", "").replace(" ", "")
    for sobrante in ("%", "€", "$", "£"):
        texto = texto.replace(sobrante, "")
    if not texto:
        return None
    if "," in texto and "." in texto:
        # La que va la última es la decimal; la otra separa los miles.
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None


def _forma_del_grafico(grafico) -> list:
    """La forma de la curva: en una frase y, debajo, dibujada en braille.

    Los números exactos ya están en la tabla de arriba. Esto es lo otro que ve
    quien mira un gráfico y que una tabla no da: **la forma**. Va en dos
    versiones porque hacen falta las dos: la frase la entiende cualquiera con
    cualquier equipo, y el dibujo se palpa en una línea braille de celdas
    gráficas, que es lo más parecido a verlo.
    """
    from nucleo import braille_grafico

    series = _todas_las_series(grafico)
    if not series or len(series[0]) < 3:
        return []
    partes = []
    nombres = _nombres_de_serie(grafico, len(series))
    partes.append("<h3>%s</h3>" % _escapar(
        _("Cómo es la curva") if len(series) == 1 else _("Cómo son las curvas")))
    for numero, valores in enumerate(series):
        frase = braille_grafico.resumen(valores)
        if not frase:
            continue
        nombre = nombres[numero] if numero < len(nombres) else ""
        partes.append("<p>%s</p>" % _escapar(
            "%s: %s" % (nombre, frase) if nombre else frase))
    if len(series) > 1:
        # Las dos o tres, en el mismo dibujo y a la misma escala: es lo único
        # que permite compararlas, que es para lo que están juntas. Se
        # distinguen por el grosor, no por el color, porque esto se lee con los
        # dedos.
        dibujo = str(braille_grafico.varias_curvas(series))
        pie = _("Las %d series juntas, a la misma escala. La primera va fina, "
                "la segunda gruesa y la tercera de trazo discontinuo.") % len(series)
    else:
        # Barras cuando los puntos son categorías sueltas y curva cuando son
        # muchos: unir con una raya dos categorías que no tienen nada entre
        # medias sugiere un paso gradual que no existe.
        forma = "barras" if len(series[0]) <= 12 else "curva"
        dibujo = braille_grafico.dibujar(series[0], forma)
        pie = _("Dibujado en braille de ocho puntos, para leerlo con los dedos "
                "en una línea braille de celdas gráficas:")
    if dibujo.strip():
        partes.append("<p>%s</p>" % _escapar(pie))
        partes.append("<pre>%s</pre>" % _escapar(dibujo))
    return partes


def html_de_imagen(documento, marca) -> str:
    """Enseña una imagen: su descripción y, si se sacaron, sus datos.

    Los datos van **primero** a propósito.  Quien abre esto sobre un gráfico
    quiere los números; la descripción explica de qué va y se lee después, sin
    tener que atravesarla para llegar a la tabla.
    """
    anotada = _anotacion_de(documento, marca)
    alternativo = (marca.texto or "").strip()
    guardada = (getattr(anotada, "texto", "") or "").strip() if anotada else ""

    partes = []
    if anotada is not None and anotada.tiene_datos:
        # De una imagen se saca una tabla o un diagrama, nunca las dos: o tiene
        # valores o tiene estructura.
        esquema = anotada.esquema()
        if esquema:
            partes.append(html_de_esquema(esquema))
        else:
            grafico = anotada.grafico()
            if grafico:
                partes.append(html_de_grafico(grafico))
    if guardada:
        partes.append("<h2>%s</h2>" % _escapar(_("Descripción")))
        for parrafo in guardada.split("\n"):
            if parrafo.strip():
                partes.append("<p>%s</p>" % _escapar(parrafo.strip()))
    if alternativo and alternativo != guardada:
        partes.append("<h2>%s</h2>" % _escapar(_("Texto alternativo del documento")))
        partes.append("<p>%s</p>" % _escapar(alternativo))
    if not partes:
        partes.append("<p>%s</p>" % _escapar(_("Esta imagen no tiene descripción.")))
    return "\n".join(partes)


def _imagen_a_html(documento, marca) -> str:
    """Escribe una imagen con la descripción que se le haya puesto.

    La descripción que el usuario o la inteligencia artificial hayan guardado
    vale más que el texto alternativo que trajera el libro, así que manda ella;
    si no la hay, se usa lo que hubiera.

    Cuando de la imagen se sacaron **datos**, detrás va la tabla.  Así un
    informe exportado a EPUB no lleva quince frases vagas sobre quince
    gráficos, sino quince tablas que se recorren celda a celda, que es lo único
    que de verdad sirve.
    """
    anotada = _anotacion_de(documento, marca)
    alternativo = (marca.texto or "").strip()
    guardada = (getattr(anotada, "texto", "") or "").strip() if anotada else ""
    imagen = '<img src="" alt="%s"/>' % _escapar(guardada or alternativo)
    if anotada is not None and anotada.tiene_datos:
        esquema = anotada.esquema()
        if esquema:
            return "<figure>%s<figcaption>%s</figcaption>%s</figure>" % (
                imagen, _escapar(_("Estructura leída del diagrama:")),
                html_de_esquema(esquema))
        tabla = html_de_grafico(anotada.grafico())
        if tabla:
            return "<figure>%s<figcaption>%s</figcaption>%s</figure>" % (
                imagen, _escapar(_("Datos leídos del gráfico:")), tabla)
    return imagen


def envolver_html(titulo: str, cuerpo: str, titulo_libro: str = "") -> str:
    """Mete un cuerpo HTML en una página completa, con estilo y procedencia.

    Lleva su propia hoja de estilo y de dónde sale, de modo que el archivo
    guardado se pueda abrir en cualquier navegador, enviar por correo o guardar
    como referencia sin depender de nada.
    """
    procedencia = ""
    if titulo_libro:
        procedencia = ('<p class="procedencia">%s</p>'
                       % _escapar(_("Extraído de «%s» con %s.")
                                  % (titulo_libro, NOMBRE)))
    return (
        "<!DOCTYPE html>\n"
        '<html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>%s</title><style>%s</style></head><body>"
        "<h1>%s</h1>%s%s</body></html>"
    ) % (_escapar(titulo), ESTILOS, _escapar(titulo), cuerpo, procedencia)


def documento_html(documento, marca: Marca, titulo_libro: str = "") -> str:
    """Arma el archivo HTML completo de un elemento suelto."""
    titulo = titulo_de(marca)
    return envolver_html(titulo, cuerpo_html(documento, marca), titulo_libro)
