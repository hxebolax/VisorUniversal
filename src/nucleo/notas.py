# -*- coding: utf-8 -*-
"""Las notas al pie de un documento: dónde acaban y qué dicen.

Casi ningún libro declara sus notas: son un enlace corriente que va del número
del texto a la sección de notas del final.  Reconocerlas ya se hace al analizar
el documento; lo que se hace aquí es lo otro, que resultó ser más difícil de lo
que parecía: **saber dónde acaba una**.

En un libro corriente cada nota es su propio párrafo y basta con eso.  En una
edición muy anotada —unos discursos clásicos, una edición crítica— van todas
seguidas dentro del mismo párrafo, cada una con su número delante y su enlace de
vuelta detrás.  Quedarse en el final del párrafo significaba leer la nota pedida
y las tres siguientes: medido sobre el volumen 2 de los *Discursos* de
Isócrates, **512 de sus 515 notas** se leían con texto que no era suyo.

Los dos riesgos no son simétricos.  Quedarse largo se nota —se oye la nota de al
lado— pero quedarse corto no: la nota acaba a media frase y quien escucha no
tiene forma de saber que le falta un trozo.  Por eso, ante la duda, se prefiere
leer de más.
"""

from __future__ import annotations

import re
from typing import NamedTuple

from .marcas import TipoMarca

#: Con qué empieza la nota siguiente: su número entre corchetes.  Es lo que
#: separa una nota de la de al lado cuando el libro las pone todas seguidas.
#:
#: Solo corchetes, y no paréntesis, aunque haya ediciones que numeren así: una
#: nota puede llevar dentro una enumeración —«(1) seguridad, (2) prosperidad»— y
#: cortarla ahí se comería media nota sin que nadie se enterara.
COMIENZO_DE_OTRA_NOTA = re.compile(r"[\[{]\s*\d{1,4}\s*[\]}]")

#: El enlace de vuelta al pasaje, que las ediciones ponen al final de cada nota.
#: Marca el final de la nota y además no se lee: es un botón para volver, y
#: decirlo en voz alta no aporta nada a quien escucha.
#:
#: Aquí **no** va la comilla «: en español abre una cita, y hay notas llenas de
#: ellas.  Cortar por ahí dejaba la nota a medias en la primera palabra
#: entrecomillada, que es peor que el fallo que se venía a arreglar.
VUELTA_AL_TEXTO = ("<<", "↑", "↩", "⏎", "▲")

#: Hasta dónde se busca el final de una nota cuando no se pide otra cosa.  Una
#: nota de más de esto es rarísima, y seguir buscando por medio libro para nada
#: sale caro cuando hay quinientas.
BUSCAR_HASTA = 4000


class Nota(NamedTuple):
    """Una nota al pie, con sus dos sitios y su texto.

    :param rotulo: Lo que se ve en el texto, normalmente ``[18]``.
    :param llamada: Dónde está el número dentro del documento.  Es a donde se
                    va para leer el pasaje que la cita.
    :param destino: Dónde empieza la nota.  Es a donde se va para leerla.
    :param texto: Lo que la nota dice, ya recortada donde acaba.
    """

    rotulo: str
    llamada: int
    destino: int
    texto: str


def final_de_la_nota(texto: str, destino: int, tope: int) -> int:
    """Dónde acaba la nota que empieza en ``destino``, sin pasar de ``tope``.

    Se para en lo primero que aparezca: el final de su párrafo, el número con
    el que empieza la nota de al lado, o el enlace de vuelta al pasaje.
    """
    fin = texto.find("\n\n", destino, tope)
    if fin < 0:
        fin = tope
    # El número con el que empieza la siguiente, saltándose el de esta: la nota
    # trae delante el suyo propio y ese no la termina.
    suyo = COMIENZO_DE_OTRA_NOTA.match(texto, destino, fin)
    siguiente = COMIENZO_DE_OTRA_NOTA.search(
        texto, suyo.end() if suyo else destino, fin)
    if siguiente is not None:
        fin = siguiente.start()
    for vuelta in VUELTA_AL_TEXTO:
        donde = texto.find(vuelta, destino, fin)
        if donde >= 0:
            fin = donde
    return fin


def limpiar_el_final(trozo: str) -> str:
    """Le quita a una nota el enlace de vuelta que se le haya quedado pegado."""
    for vuelta in VUELTA_AL_TEXTO:
        trozo = trozo.rstrip().removesuffix(vuelta).rstrip()
    return trozo


def texto_de(documento, marca, largo: int = 0) -> str:
    """El texto de la nota a la que apunta una llamada.

    :param largo: Longitud máxima, o 0 para traerla entera.  Se recorta para
                  leerla en voz alta, porque un aviso hablado no puede durar
                  cinco minutos; para verla entera está el visor de notas.
    :return: El texto, o cadena vacía si el enlace no lleva a ninguna parte.
    """
    destino = documento.resolver_referencia(getattr(marca, "referencia", "") or "")
    if destino < 0:
        return ""
    texto = documento.texto
    tope = min(len(texto), destino + (largo or BUSCAR_HASTA))
    fin = final_de_la_nota(texto, destino, tope)
    return limpiar_el_final(" ".join(texto[destino:fin].split()))


def todas(documento) -> list[Nota]:
    """Todas las notas del documento, en orden de lectura y con su texto.

    Se saca de una vez: en un libro anotado son quinientas y volver al texto una
    por una mientras alguien recorre la lista con las flechas se nota.
    """
    salida = []
    for marca in documento.marcas.grupo(TipoMarca.NOTA_PIE).marcas:
        destino = documento.resolver_referencia(marca.referencia or "")
        if destino < 0:
            continue
        salida.append(Nota(marca.texto or "", marca.posicion, destino,
                           texto_de(documento, marca)))
    return salida
