# -*- coding: utf-8 -*-
"""Musicografía braille: una partitura que se puede leer con los dedos.

Es lo que piden los estudiantes de conservatorio, y hasta ahora era lo único
del programa que no tenía respuesta: una partitura llegaba como una imagen o
como un archivo que no se abría.

Se sigue el **documento técnico B 4-2 de la Comisión Braille Española**,
guardado en ``adjuntos/Estudio/normas``. La musicografía braille es
internacional: lo que sale de aquí lo lee igual un músico de Madrid que uno de
Tokio.

**Cómo funciona, en tres ideas**, porque no se parece a nada de lo demás:

1. **Una nota es una sola celda** que dice a la vez *qué* nota y *cuánto* dura.
   La altura va en los puntos 1, 2, 4 y 5 —son las letras ``d`` a ``j`` para do,
   re, mi, fa, sol, la y si— y la figura, en los puntos 3 y 6: redonda los dos,
   blanca el 3, negra el 6 y corchea ninguno.
2. **La misma celda vale para dos figuras**: la redonda y la semicorchea se
   escriben igual, la blanca y la fusa también. No es un defecto del sistema:
   con solo cuatro combinaciones de dos puntos no dan más de sí, y el compás
   deshace la duda. Aquí se resuelve escribiendo, además de la partitura, cuánto
   dura cada nota en palabras.
3. **La octava no se escribe casi nunca.** Se pone al principio y solo se repite
   cuando el salto lo exige. Esa regla —que es la que más cuesta— es lo que hace
   que una partitura braille quepa en una hoja en vez de en tres.

4. **Un acorde no se escribe nota a nota.** Se escribe **una** nota —la más
   aguda o la más grave, según el instrumento— y las demás con **signos de
   intervalo** medidos desde ella. Un acorde de tres notas ocupa tres celdas y
   no seis, y al leerlo se sabe de golpe qué distancia hay entre las voces, que
   es lo que un acorde dice.
5. **Dos voces en el mismo pentagrama se separan con la cópula**, y después de
   ella —y al empezar el compás siguiente— siempre va signo de octava: la
   segunda voz empieza donde le da la gana, no donde acabó la primera.

6. **Cómo se toca va pegado a la nota.** El picado, el acento, la ligadura de
   expresión y el dedo con el que se pulsa tienen su celda, y van delante o
   detrás de su nota sin separarse de ella. Una partitura sin eso dice qué notas
   hay y no dice cómo suenan, que en música no es un detalle de adorno.
7. **Las palabras se marcan como palabras.** Un «piano», un «a tempo» o un
   «poco a poco cresc.» llevan delante el **signo de palabra**, que es lo que
   impide leer una `p` de matiz como si fuera una nota. Y la nota siguiente
   vuelve a llevar su octava.

8. **Los adornos van delante de su nota** y no obligan a poner octava. El
   documento B 4-2 no los recoge —él mismo avisa de que no es exhaustivo y
   remite al manual internacional—, así que sus signos se han tomado de ahí:
   del *New International Manual of Braille Music Notation*, que está guardado
   en ``adjuntos/Estudio/normas``.

**Lo que no se transcribe se dice, y no se inventa.** Lo que queda fuera —el
trémolo, los arpegios que cruzan dos pentagramas, la *Bebung*— se dice en
palabras y se advierte. Una partitura braille con una nota mal puesta no se
detecta leyéndola: se detecta tocándola delante de alguien.
"""

from __future__ import annotations

from .braille import ASCII_BRAILLE, LETRAS as LETRAS_TEXTO, UNICODE_BRAILLE
from .idioma import _
from .registro import obtener_registro

log = obtener_registro(__name__)


def _puntos(*numeros: int) -> int:
    celda = 0
    for numero in numeros:
        celda |= 1 << (numero - 1)
    return celda


BLANCO = 0

#: Los siete grados, con la celda que les corresponde **como corchea**. Son las
#: letras ``d`` a ``j``: la altura vive en los puntos 1, 2, 4 y 5.
GRADOS = {
    "C": _puntos(1, 4, 5),      # do
    "D": _puntos(1, 5),         # re
    "E": _puntos(1, 2, 4),      # mi
    "F": _puntos(1, 2, 4, 5),   # fa
    "G": _puntos(1, 2, 5),      # sol
    "A": _puntos(2, 4),         # la
    "B": _puntos(2, 4, 5),      # si
}

#: Cómo se llama cada grado al leerlo en voz alta.
NOMBRES = {"C": _("do"), "D": _("re"), "E": _("mi"), "F": _("fa"),
           "G": _("sol"), "A": _("la"), "B": _("si")}

#: Qué se le suma a la celda de la nota según la figura. Cada valor sirve para
#: **dos** figuras, una dieciséis veces más corta que la otra.
FIGURAS = {
    "whole": _puntos(3, 6), "16th": _puntos(3, 6),
    "half": _puntos(3), "32nd": _puntos(3),
    "quarter": _puntos(6), "64th": _puntos(6),
    "eighth": 0, "128th": 0,
}

#: Cómo se llama cada figura al leerla en voz alta.
NOMBRE_FIGURA = {
    "whole": _("redonda"), "half": _("blanca"), "quarter": _("negra"),
    "eighth": _("corchea"), "16th": _("semicorchea"), "32nd": _("fusa"),
    "64th": _("semifusa"), "128th": _("garrapatea"),
    "breve": _("cuadrada"), "long": _("longa"),
}

#: Los cuatro silencios. Como las notas, cada uno vale para dos figuras.
SILENCIOS = {
    "whole": _puntos(1, 3, 4), "16th": _puntos(1, 3, 4),
    "half": _puntos(1, 3, 6), "32nd": _puntos(1, 3, 6),
    "quarter": _puntos(1, 2, 3, 6), "64th": _puntos(1, 2, 3, 6),
    "eighth": _puntos(1, 3, 4, 6), "128th": _puntos(1, 3, 4, 6),
}

#: Signos de octava, de la primera a la séptima. La cuarta es la del la 440.
OCTAVAS = {
    1: _puntos(4), 2: _puntos(4, 5), 3: _puntos(4, 5, 6), 4: _puntos(5),
    5: _puntos(4, 6), 6: _puntos(5, 6), 7: _puntos(6),
}

#: Alteraciones. Van delante de la nota, y entre ellas y la nota solo cabe el
#: signo de octava.
SOSTENIDO = _puntos(1, 4, 6)
BEMOL = _puntos(1, 2, 6)
BECUADRO = _puntos(1, 6)

#: El puntillo: punto 3, pegado detrás de la nota o del silencio.
PUNTILLO = _puntos(3)

#: Signo de número, para el compás.
NUMERO = _puntos(3, 4, 5, 6)

#: Cifras en posición normal, para el numerador del compás.
CIFRAS = {
    "1": _puntos(1), "2": _puntos(1, 2), "3": _puntos(1, 4), "4": _puntos(1, 4, 5),
    "5": _puntos(1, 5), "6": _puntos(1, 2, 4), "7": _puntos(1, 2, 4, 5),
    "8": _puntos(1, 2, 5), "9": _puntos(2, 4), "0": _puntos(2, 4, 5),
}

#: Cifras en posición baja, para el denominador del compás.
CIFRAS_BAJAS = {
    "1": _puntos(2), "2": _puntos(2, 3), "3": _puntos(2, 5), "4": _puntos(2, 5, 6),
    "5": _puntos(2, 6), "6": _puntos(2, 3, 5), "7": _puntos(2, 3, 5, 6),
    "8": _puntos(2, 3, 6), "9": _puntos(3, 5), "0": _puntos(3, 5, 6),
}

#: Ligadura de prolongación: une dos notas de la misma altura en una sola.
LIGADURA = (_puntos(4), _puntos(1, 4))

#: Orden de los grados dentro de la octava, para medir intervalos.
_ORDEN = {"C": 0, "D": 1, "E": 2, "F": 3, "G": 4, "A": 5, "B": 6}


class Imposible(Exception):
    """La partitura usa algo que esta transcripción no cubre."""


class Nota:
    """Una nota o un silencio, con lo justo para escribirlo.

    :param grado: ``C``…``B``, o cadena vacía si es un silencio.
    :param octava: Octava científica, la misma que usa MusicXML: el do central
                   es el de la cuarta.
    :param figura: ``whole``, ``half``, ``quarter``, ``eighth``…
    :param alteracion: -2 a 2, en tonos: -1 es bemol, 1 sostenido.
    :param puntillos: Cuántos puntillos lleva.
    :param ligada: Si se ata a la nota siguiente (ligadura de prolongación).
    :param adornos: Trinos, mordentes y grupetos, por su nombre de MusicXML.
        Van delante de todo lo demás, que es donde los pone la norma.
    :param apoyatura: ``"larga"``, ``"corta"`` o ``""``.  Una apoyatura no es un
        adorno: es una nota de verdad que se escribe como nota, con su signo
        delante.
    :param articulaciones: Cómo se ataca: ``staccato``, ``accent``…  Son varias
        porque una nota puede llevar más de una, y en braille se escriben
        seguidas delante de ella.
    :param ligado: Ligadura **de expresión**, que es otra cosa que la de
        prolongación: aquella une dos notas del mismo sonido y esta dice que un
        grupo se toca ligado.  En tinta se dibujan igual y en braille hay que
        distinguirlas.  Vale ``"sigue"`` —el ligado continúa hasta la nota
        siguiente, y el signo va **entre** las dos—, ``"abre-larga"`` y
        ``"cierra-larga"`` para los grupos de cinco notas o más, que llevan un
        signo doble delante de la primera y otro detrás de la última.
    :param dedo: Con qué dedo se pulsa, de 1 a 5, o 0 si no se dice.
    :param palabras: Texto que va delante de la nota: un matiz, un «a tempo».
    :param reguladores: Aperturas y cierres de crescendo o diminuendo que
        empiezan en esta nota.
    """

    __slots__ = ("grado", "octava", "figura", "alteracion", "puntillos",
                 "ligada", "es_silencio", "articulaciones", "ligado", "dedo",
                 "palabras", "reguladores", "adornos", "apoyatura")

    def __init__(self, grado: str = "", octava: int = 4, figura: str = "quarter",
                 alteracion: int = 0, puntillos: int = 0, ligada: bool = False,
                 es_silencio: bool = False, articulaciones=(), ligado: str = "",
                 dedo: int = 0, palabras=(), reguladores=(), adornos=(),
                 apoyatura: str = "") -> None:
        self.grado = grado
        self.octava = octava
        self.figura = figura
        self.alteracion = alteracion
        self.puntillos = puntillos
        self.ligada = ligada
        self.es_silencio = es_silencio or not grado
        self.articulaciones = tuple(articulaciones or ())
        self.ligado = ligado
        self.dedo = int(dedo or 0)
        self.palabras = tuple(palabras or ())
        self.reguladores = tuple(reguladores or ())
        self.adornos = tuple(adornos or ())
        self.apoyatura = apoyatura

    @property
    def altura(self) -> int:
        """Su sitio en la escala, contando grados desde el do más grave."""
        return self.octava * 7 + _ORDEN.get(self.grado, 0)

    def nombre(self) -> str:
        """Cómo se lee en voz alta: «do sostenido negra con puntillo»."""
        if self.es_silencio:
            texto = _("silencio de %s") % NOMBRE_FIGURA.get(self.figura,
                                                            self.figura)
        else:
            partes = [NOMBRES.get(self.grado, self.grado)]
            if self.alteracion == 1:
                partes.append(_("sostenido"))
            elif self.alteracion == -1:
                partes.append(_("bemol"))
            elif self.alteracion == 2:
                partes.append(_("doble sostenido"))
            elif self.alteracion == -2:
                partes.append(_("doble bemol"))
            partes.append(NOMBRE_FIGURA.get(self.figura, self.figura))
            texto = " ".join(partes)
        if self.puntillos == 1:
            texto += " " + _("con puntillo")
        elif self.puntillos > 1:
            texto += " " + _("con %d puntillos") % self.puntillos
        for cual in self.adornos:
            nombre = NOMBRE_ADORNO.get(cual)
            if nombre:
                texto += " " + _("con %s") % nombre
        if self.apoyatura:
            texto = "%s, %s" % (_("apoyatura corta") if self.apoyatura == "corta"
                                else _("apoyatura"), texto)
        for cual in self.articulaciones:
            nombre = NOMBRE_ARTICULACION.get(cual)
            if nombre:
                texto += " " + nombre
        if self.dedo:
            texto += " " + _("con el dedo %d") % self.dedo
        delante = list(self.palabras)
        delante.extend(NOMBRE_REGULADOR.get(cual, "") for cual in self.reguladores)
        delante = [pieza for pieza in delante if pieza]
        if delante:
            # Delante y no detrás: un matiz dice cómo se toca lo que viene, y
            # oírlo después de la nota llega tarde.
            texto = "%s, %s" % (", ".join(delante), texto)
        return texto


#: Signos de articulación: cómo se ataca la nota. Todos acaban en la misma
#: celda —los puntos 236— y se distinguen por lo que llevan delante, que es lo
#: que permite reconocerlos al tacto sin haberlos memorizado uno a uno.
_PICADO = _puntos(2, 3, 6)
ARTICULACIONES = {
    "staccato": (_PICADO,),
    "staccatissimo": (_puntos(6), _PICADO),
    "detached-legato": (_puntos(5), _PICADO),          # picado-ligado
    "tenuto": (_puntos(4, 5, 6), _PICADO),             # acento agógico
    "accent": (_puntos(4, 6), _PICADO),
    "strong-accent": (_puntos(5, 6), _PICADO),         # martellato
}

#: Cómo se lee cada articulación en voz alta.
NOMBRE_ARTICULACION = {
    "staccato": _("picado"),
    "staccatissimo": _("muy picado"),
    "detached-legato": _("picado ligado"),
    # «Mantenido» y no «sostenido»: sostenido ya es la alteración, y oír «mi
    # negra sostenido» cuando lo que hay es un tenuto sería decir otra cosa.
    "tenuto": _("mantenido"),
    "accent": _("acentuado"),
    "strong-accent": _("muy acentuado"),
}

#: Cómo se lee cada regulador en voz alta.
NOMBRE_REGULADOR = {
    "crescendo": _("empieza a crecer"),
    "fin-crescendo": _("deja de crecer"),
    "diminuendo": _("empieza a apagarse"),
    "fin-diminuendo": _("deja de apagarse"),
}

#: Los adornos, del manual internacional (tabla 11).  Van **delante** de la nota
#: y no obligan a signo de octava, igual que la articulación.
#:
#: Casi todos se construyen sobre dos celdas: la del trino —los puntos 235— y la
#: del grupeto —los puntos 256—, con un prefijo delante o los puntos 123 detrás
#: que las convierten en su versión corta, extendida o invertida.  Reconocerlos
#: al tacto es reconocer esas dos y saber qué les han puesto alrededor.
_TRINO = _puntos(2, 3, 5)
_GRUPETO = _puntos(2, 5, 6)
_INVERSION = _puntos(1, 2, 3)

ADORNOS = {
    "trill-mark": (_TRINO,),
    # El mordente de MusicXML es el de la rayita vertical, que en el manual es
    # el mordente propiamente dicho; el «invertido» de MusicXML es el trino
    # corto, el pralltriller. Los nombres van cambiados entre los dos mundos y
    # confundirlos toca la nota de al lado en vez de la de abajo.
    "mordent": (_puntos(5), _TRINO, _INVERSION),
    "inverted-mordent": (_puntos(5), _TRINO),
    "turn": (_puntos(6), _GRUPETO),
    "inverted-turn": (_puntos(6), _GRUPETO, _INVERSION),
}

#: Cómo se lee cada adorno en voz alta.
NOMBRE_ADORNO = {
    "trill-mark": _("trino"),
    "mordent": _("mordente"),
    "inverted-mordent": _("mordente invertido"),
    "turn": _("grupeto"),
    "inverted-turn": _("grupeto invertido"),
}

#: Las apoyaturas, que en MusicXML no son adornos sino **notas de adorno**: una
#: nota de verdad marcada como tal.  La corta —la que lleva la rayita cruzada—
#: es la acciaccatura.
APOYATURA = (_puntos(5), _puntos(2, 6))
APOYATURA_CORTA = (_puntos(2, 6),)

#: Ligadura de expresión corta: va **entre** las dos notas que une.
LIGADURA_EXPRESION = _puntos(1, 4)

#: Ligadura de expresión larga —más de cuatro notas—: una celda doble antes de
#: la primera y otra después de la última.
LIGADURA_LARGA_ABRE = (_puntos(5, 6), _puntos(1, 2))
LIGADURA_LARGA_CIERRA = (_puntos(4, 5), _puntos(2, 3))

#: A partir de cuántas notas la ligadura se escribe como larga. La norma dice
#: que el signo simple vale para dos, tres o cuatro.
LIGADURA_LARGA_DESDE = 5

#: Signo de palabra: lo que va delante de cualquier texto metido en la música
#: —un matiz, un «a tempo»— para que no se lea como notas.
PALABRA = _puntos(3, 4, 5)

#: Reguladores: abrir y cerrar el crescendo y el diminuendo. Los cuatro llevan
#: delante el signo de palabra, que es lo que son: una indicación escrita.
REGULADORES = {
    "crescendo": (PALABRA, _puntos(1, 4)),
    "fin-crescendo": (PALABRA, _puntos(2, 5)),
    "diminuendo": (PALABRA, _puntos(1, 4, 5)),
    "fin-diminuendo": (PALABRA, _puntos(2, 5, 6)),
}

#: Los cinco dedos. Van **detrás** de la nota, y detrás del puntillo si lo hay.
DEDOS = {
    1: _puntos(1),
    2: _puntos(1, 2),
    3: _puntos(1, 2, 3),
    4: _puntos(2),
    5: _puntos(1, 3),
}

#: Los signos de intervalo, medidos desde la nota escrita. Son todos de la
#: parte baja de la celda, que es lo que los distingue al tacto de las notas.
INTERVALOS = {
    2: _puntos(3, 4),
    3: _puntos(3, 4, 6),
    4: _puntos(3, 4, 5, 6),
    5: _puntos(3, 5),
    6: _puntos(3, 5, 6),
    7: _puntos(2, 5),
    8: _puntos(3, 6),
}

#: Cópula total: separa dos voces que ocupan **el compás entero**.
COPULA_TOTAL = (_puntos(1, 2, 6), _puntos(3, 4, 5))

#: Cópula parcial: cuando la disparidad de valores solo afecta a un trozo.
COPULA_PARCIAL = (_puntos(5), _puntos(2))

#: Fraccionador de compás, que acompaña a la cópula parcial y dice qué parte
#: del compás está afectada.
FRACCIONADOR = (_puntos(4, 6), _puntos(1, 3))


class Acorde:
    """Varias notas del mismo valor que suenan a la vez.

    :param notas: Las notas del acorde, en cualquier orden.
    :param hacia_abajo: Si se escribe de arriba abajo.  Es lo normal en los
        instrumentos agudos y en la mano derecha del teclado; los graves y la
        mano izquierda se escriben de abajo arriba.  Decide **cuál es la nota
        que se escribe entera**, y por tanto desde dónde se miden los
        intervalos, así que no es un detalle de presentación.
    """

    __slots__ = ("notas", "hacia_abajo")

    def __init__(self, notas, hacia_abajo: bool = True) -> None:
        self.notas = sorted(notas, key=lambda nota: nota.altura,
                            reverse=hacia_abajo)
        self.hacia_abajo = hacia_abajo

    @property
    def principal(self) -> Nota:
        """La nota que se escribe en su forma real; el resto son intervalos."""
        return self.notas[0]

    @property
    def es_silencio(self) -> bool:
        return False

    def nombre(self) -> str:
        """Cómo se lee en voz alta, que es lo que oye quien no lee braille."""
        # Se dicen de grave a aguda aunque en braille vayan al revés: «do mi
        # sol» es como se nombra un acorde, y quien lo oye no está leyendo.
        piezas = [NOMBRES.get(nota.grado, nota.grado)
                  for nota in sorted(self.notas, key=lambda n: n.altura)]
        return _("acorde de %(notas)s, %(figura)s") % {
            "notas": " ".join(piezas),
            "figura": NOMBRE_FIGURA.get(self.principal.figura,
                                        self.principal.figura)}


def intervalo_entre(principal: Nota, otra: Nota) -> int:
    """Cuántos grados hay de una nota a otra, contando las dos.

    Es el intervalo tal y como se cuenta en música: de do a mi son tres, no dos.
    """
    return abs(otra.altura - principal.altura) + 1


def celdas_de_intervalo(principal: Nota, otra: Nota) -> list[int]:
    """El signo de intervalo de una nota del acorde.

    Un intervalo mayor que la octava lleva delante **el signo de octava de esa
    nota** y después el signo del intervalo reducido: una décima es octava más
    tercera, y se escribe con la octava y el signo de tercera.  Sin eso, una
    décima y una tercera se escribirían igual.
    """
    distancia = intervalo_entre(principal, otra)
    if distancia == 1:
        raise Imposible("dos notas del acorde suenan al unísono")
    salida: list[int] = []
    if otra.alteracion:
        base = SOSTENIDO if otra.alteracion > 0 else BEMOL
        salida.extend([base] * min(abs(otra.alteracion), 2))
    if distancia > 8:
        marca = OCTAVAS.get(otra.octava)
        if marca is None:
            raise Imposible("octava fuera de las siete: %d" % otra.octava)
        salida.append(marca)
        reducida = (distancia - 1) % 7 + 1
        distancia = 8 if reducida == 1 else reducida
    signo = INTERVALOS.get(distancia)
    if signo is None:                                   # pragma: no cover
        raise Imposible("intervalo desconocido: %d" % distancia)
    salida.append(signo)
    return salida


def celdas_de_acorde(acorde: Acorde, anterior: Nota | None) -> list[int]:
    """Las celdas de un acorde: la nota principal y sus intervalos.

    La regla de la octava se aplica **a la nota principal** y se sigue contando
    desde ella, no desde la última nota del acorde: es la única que está escrita
    como nota.
    """
    if not acorde.notas:                                # pragma: no cover
        raise Imposible("acorde sin notas")
    salida = celdas_de_nota(acorde.principal, anterior)
    for otra in acorde.notas[1:]:
        salida.extend(celdas_de_intervalo(acorde.principal, otra))
    return salida


def hace_falta_octava(anterior: Nota | None, actual: Nota) -> bool:
    """Dice si esta nota tiene que llevar delante su signo de octava.

    Es **la** regla de la musicografía, y la que decide si una partitura se lee
    con soltura o se lee deletreando:

    - La primera nota siempre lo lleva.
    - Un salto de segunda o de tercera, nunca.
    - Un salto de cuarta o de quinta, solo si las dos notas están en octavas
      distintas.
    - Un salto de sexta o mayor, siempre.
    """
    if anterior is None or anterior.es_silencio or actual.es_silencio:
        return not actual.es_silencio
    distancia = abs(actual.altura - anterior.altura)
    intervalo = distancia + 1
    if intervalo <= 3:
        return False
    if intervalo <= 5:
        return actual.octava != anterior.octava
    return True


def celdas_de_nota(nota: Nota, anterior: Nota | None) -> list[int]:
    """Las celdas de una nota, en el orden que manda la norma.

    Delante van las palabras —un matiz, un «a tempo»— y los reguladores; después
    los adornos y la apoyatura; después la articulación, la alteración y la
    octava; después la nota con su figura y sus puntillos; y detrás la
    digitación y las ligaduras.

    El orden no es de gusto: la articulación va antes de la nota **y no obliga a
    poner signo de octava**, mientras que el dedo va después del puntillo. Puesto
    de otra manera, lo que se lee es otra cosa.
    """
    salida: list[int] = []
    con_palabras = False
    for texto in nota.palabras:
        trozo = celdas_de_palabra(texto)
        if trozo:
            salida.extend(trozo)
            con_palabras = True
    for cual in nota.reguladores:
        signo = REGULADORES.get(cual)
        if signo:
            salida.extend(signo)
            con_palabras = True
    if nota.ligado == "abre-larga":
        salida.extend(LIGADURA_LARGA_ABRE)
    # Los adornos van delante de todo lo demás y **no obligan a signo de
    # octava**, igual que la articulación: lo dice el manual internacional.
    for cual in nota.adornos:
        signo = ADORNOS.get(cual)
        if signo is None:
            raise Imposible("adorno desconocido: %s" % cual)
        salida.extend(signo)
    if nota.apoyatura:
        salida.extend(APOYATURA_CORTA if nota.apoyatura == "corta"
                      else APOYATURA)
    if con_palabras:
        # La norma lo dice sin matices: la nota que sigue a un texto o a un
        # regulador lleva **siempre** su signo de octava. Es lo razonable: entre
        # medias ha pasado una palabra, y el hilo de dónde estábamos se corta.
        anterior = None
    for cual in nota.articulaciones:
        signo = ARTICULACIONES.get(cual)
        if signo is None:
            raise Imposible("articulación desconocida: %s" % cual)
        salida.extend(signo)
    if nota.es_silencio:
        figura = SILENCIOS.get(nota.figura)
        if figura is None:
            raise Imposible("figura de silencio desconocida: %s" % nota.figura)
        salida.append(figura)
    else:
        if nota.grado not in GRADOS:
            raise Imposible("nota desconocida: %s" % nota.grado)
        if nota.alteracion:
            signo = {1: SOSTENIDO, -1: BEMOL, 0: BECUADRO}.get(nota.alteracion)
            if signo is None:
                # Los dobles se escriben repitiendo el signo simple.
                base = SOSTENIDO if nota.alteracion > 0 else BEMOL
                salida.extend([base] * min(abs(nota.alteracion), 2))
            else:
                salida.append(signo)
        if hace_falta_octava(anterior, nota):
            marca = OCTAVAS.get(nota.octava)
            if marca is None:
                raise Imposible("octava fuera de las siete: %d" % nota.octava)
            salida.append(marca)
        base = FIGURAS.get(nota.figura)
        if base is None:
            raise Imposible("figura desconocida: %s" % nota.figura)
        salida.append(GRADOS[nota.grado] | base)
    salida.extend([PUNTILLO] * max(0, min(nota.puntillos, 3)))
    # El dedo va detrás de la nota y detrás del puntillo, que es donde la norma
    # lo pone y donde no se confunde con una cifra.
    if nota.dedo in DEDOS:
        salida.append(DEDOS[nota.dedo])
    if nota.ligada:
        salida.extend(LIGADURA)
    if nota.ligado == "sigue":
        # Entre las dos notas que une, que es donde la pone la norma: no delante
        # del grupo, sino en cada hueco.
        salida.append(LIGADURA_EXPRESION)
    elif nota.ligado == "cierra-larga":
        salida.extend(LIGADURA_LARGA_CIERRA)
    return salida


def celdas_de_palabra(texto: str) -> list[int]:
    """Un texto metido en la música, con su signo de palabra delante.

    Sin ese signo, un «p» de matiz se leería como la nota que le corresponda a
    esa celda, que es exactamente la confusión que el signo existe para evitar.

    Se escriben las letras que se sepan escribir; lo que no —un acento, un
    símbolo raro— se deja fuera antes que poner otra cosa en su lugar.
    """
    salida = [PALABRA]
    for letra in (texto or "").lower():
        if letra in LETRAS_TEXTO:
            salida.append(LETRAS_TEXTO[letra])
    return salida if len(salida) > 1 else []


def celdas_de_compas(compas, anterior_global: Nota | None = None):
    """Las celdas de un compás entero. Devuelve ``(celdas, última nota)``.

    Un compás es una lista de notas y acordes; si trae **varias voces** —una
    lista de listas— se escriben separadas por la cópula total.

    La última nota se devuelve porque la regla de la octava **no se reinicia en
    la barra**: se sigue contando de una nota a la siguiente aunque haya cambio
    de compás.  La excepción es la cópula: después de ella se devuelve ``None``
    para que la primera nota del compás siguiente lleve su octava, que es lo que
    manda la norma y lo que evita leer la segunda voz en el registro de la
    primera.
    """
    if _son_voces(compas):
        return _celdas_de_voces(compas, anterior_global)
    salida: list[int] = []
    anterior = anterior_global
    for elemento in compas:
        if isinstance(elemento, Acorde):
            salida.extend(celdas_de_acorde(elemento, anterior))
            anterior = elemento.principal
            continue
        salida.extend(celdas_de_nota(elemento, anterior))
        if not elemento.es_silencio:
            anterior = elemento
    return salida, anterior


def _son_voces(compas) -> bool:
    """Dice si el compás viene repartido en voces y no en notas sueltas."""
    return bool(compas) and all(isinstance(trozo, (list, tuple))
                                for trozo in compas)


def _celdas_de_voces(voces, anterior_global: Nota | None):
    """Las voces de un compás, separadas por la cópula total.

    Cada voz empieza **con signo de octava**, que es lo que pide la norma
    inmediatamente después de una cópula: la segunda voz empieza donde le
    corresponde a ella y no donde acabó la primera, y sin la octava se leería en
    el registro equivocado.
    """
    escritas = []
    for numero, voz in enumerate(voces):
        # La primera voz sigue contando desde el compás anterior; las demás
        # arrancan de cero, que es lo que fuerza su signo de octava.
        celdas, _ultima = celdas_de_compas(list(voz),
                                           anterior_global if numero == 0 else None)
        if celdas:
            escritas.append(celdas)
    if not escritas:
        return [], anterior_global
    if len(escritas) == 1:
        return escritas[0], None
    salida: list[int] = []
    for numero, celdas in enumerate(escritas):
        if numero:
            salida.extend(COPULA_TOTAL)
        salida.extend(celdas)
    return salida, None


def celdas_de_compasillo(numerador: int, denominador: int) -> list[int]:
    """El compás: signo de número, numerador arriba y denominador abajo."""
    salida = [NUMERO]
    salida.extend(CIFRAS[c] for c in str(numerador) if c in CIFRAS)
    salida.extend(CIFRAS_BAJAS[c] for c in str(denominador) if c in CIFRAS_BAJAS)
    return salida


def celdas_de_armadura(alteraciones: int) -> list[int]:
    """La armadura: los sostenidos o bemoles que lleva la pieza.

    Hasta tres se escribe el signo repetido; de cuatro en adelante, el número y
    después el signo, que es lo que dice la norma y lo que ahorra celdas.
    """
    if not alteraciones:
        return []
    signo = SOSTENIDO if alteraciones > 0 else BEMOL
    cuantas = abs(alteraciones)
    if cuantas <= 3:
        return [signo] * cuantas
    return [NUMERO] + [CIFRAS[c] for c in str(cuantas) if c in CIFRAS] + [signo]


def a_unicode(celdas) -> str:
    """Pasa las celdas a los signos braille de Unicode, para verlos y oírlos."""
    return "".join(chr(UNICODE_BRAILLE + celda) for celda in celdas or ())


def a_brf(celdas) -> str:
    """Pasa las celdas a los caracteres de un archivo BRF."""
    return "".join(ASCII_BRAILLE[celda] if 0 <= celda < len(ASCII_BRAILLE) else " "
                   for celda in celdas or ())


def transcribir(compases, armadura: int = 0, compas=None) -> str | None:
    """Transcribe una lista de compases a musicografía braille.

    :param compases: Lista de compases; cada uno, una lista de :class:`Nota`.
    :param armadura: Alteraciones de la tonalidad, con signo.
    :param compas: Par ``(numerador, denominador)``, o ``None``.
    :return: La partitura en signos braille de Unicode, o ``None`` si hay algo
             que no se sabe escribir.

    **La línea divisoria es un espacio en blanco**: es así en la norma, y por
    eso los compases van separados por un espacio y nada más.
    """
    try:
        cabecera: list[int] = []
        cabecera.extend(celdas_de_armadura(armadura))
        if compas:
            cabecera.extend(celdas_de_compasillo(compas[0], compas[1]))
        trozos = []
        if cabecera:
            trozos.append(a_unicode(cabecera))
        anterior = None
        for uno in compases:
            celdas, anterior = celdas_de_compas(uno, anterior)
            if celdas:
                trozos.append(a_unicode(celdas))
        return " ".join(trozos) if trozos else None
    except Imposible as motivo:
        log.debug("Partitura no transcrita: %s", motivo)
        return None


def descripcion() -> str:
    """Frase que explica qué se obtiene, para la ventana de opciones."""
    return _("Las partituras se escriben en musicografía braille siguiendo el "
             "documento B 4-2 de la Comisión Braille Española. Los acordes van "
             "con sus signos de intervalo, las voces simultáneas separadas por "
             "la cópula, y los adornos —trinos, mordentes y grupetos— con los "
             "signos del manual internacional. El trémolo y los arpegios que "
             "cruzan dos pentagramas se dicen en palabras.")
