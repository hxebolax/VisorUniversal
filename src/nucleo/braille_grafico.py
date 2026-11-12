# -*- coding: utf-8 -*-
"""Dibujar la forma de una curva en una línea braille.

Los datos de un gráfico ya se sacan y se enseñan como tabla
(:mod:`nucleo.graficos`), que es lo que hacía falta para saber **los valores**.
Esto es lo otro: la **forma**. Saber que una curva sube despacio, cae de golpe y
se queda plana es lo primero que ve quien mira un gráfico, y una tabla de
cuarenta números no lo dice por más que se recorra.

Se dibuja con celdas braille de ocho puntos, que son una rejilla de dos
columnas por cuatro filas. Una línea de cuarenta celdas son ochenta puntos de
ancho por cuatro de alto; con cuatro líneas, ochenta por dieciséis. En una línea
braille moderna, con celdas gráficas, eso se palpa como un dibujo.

**Por qué esto no contradice lo que dice el propio programa sobre sonificar**
—que convertir los datos en sonido no comunica valores exactos y cansa—: aquí no
se sustituye nada. Los valores siguen estando en la tabla, exactos, y el dibujo
va **además**, para lo único que la tabla no da: la forma de un vistazo. Y a
diferencia del sonido, un dibujo braille se queda quieto y se puede volver a
recorrer con el dedo tantas veces como haga falta.

**Se dibuja en ocho puntos y no en seis** porque los puntos 7 y 8 completan la
rejilla: con seis puntos las celdas son de dos por tres y las curvas salen a
escalones. Las líneas braille de cuarenta celdas de hoy son todas de ocho
puntos.
"""

from __future__ import annotations

from .braille import UNICODE_BRAILLE
from .idioma import _
from .registro import obtener_registro

log = obtener_registro(__name__)

#: Qué bit enciende cada punto dentro de la celda, colocados como están en el
#: cajetín: dos columnas de cuatro filas. La numeración de los puntos no sigue
#: el orden de lectura —el 7 y el 8 se añadieron debajo mucho después—, así que
#: hace falta esta tabla para poder pensar en filas y columnas.
_PUNTO = (
    (0, 0, 1 << 0),   # fila 0, columna izquierda: punto 1
    (0, 1, 1 << 3),   # fila 0, columna derecha:  punto 4
    (1, 0, 1 << 1),   # fila 1, izquierda:        punto 2
    (1, 1, 1 << 4),   # fila 1, derecha:          punto 5
    (2, 0, 1 << 2),   # fila 2, izquierda:        punto 3
    (2, 1, 1 << 5),   # fila 2, derecha:          punto 6
    (3, 0, 1 << 6),   # fila 3, izquierda:        punto 7
    (3, 1, 1 << 7),   # fila 3, derecha:          punto 8
)

#: Índice rápido: ``_BIT[(fila, columna)]`` da el bit que hay que encender.
_BIT = {(fila, columna): bit for fila, columna, bit in _PUNTO}

#: Ancho y alto por omisión, en celdas y en líneas. Cuarenta celdas es lo que
#: mide una línea braille corriente; cuatro líneas es lo que se recorre con la
#: mano sin perder el sitio.
ANCHO = 40
ALTO = 4


class Lienzo:
    """Una rejilla de puntos que al final se convierte en celdas braille."""

    __slots__ = ("ancho", "alto", "puntos")

    def __init__(self, ancho: int = ANCHO, alto: int = ALTO) -> None:
        self.ancho = max(1, ancho)
        self.alto = max(1, alto)
        #: Una celda por posición, con sus bits encendidos.
        self.puntos = [[0] * self.ancho for _ in range(self.alto)]

    @property
    def puntos_de_ancho(self) -> int:
        """Cuántos puntos caben a lo ancho: dos por celda."""
        return self.ancho * 2

    @property
    def puntos_de_alto(self) -> int:
        """Cuántos puntos caben a lo alto: cuatro por celda."""
        return self.alto * 4

    def encender(self, x: int, y: int) -> None:
        """Enciende el punto ``(x, y)``, contando ``y`` **desde arriba**."""
        if not (0 <= x < self.puntos_de_ancho and 0 <= y < self.puntos_de_alto):
            return
        celda_x, columna = divmod(x, 2)
        celda_y, fila = divmod(y, 4)
        self.puntos[celda_y][celda_x] |= _BIT[(fila, columna)]

    def segmento(self, x1: int, y1: int, x2: int, y2: int) -> None:
        """Traza una raya recta entre dos puntos.

        Es el algoritmo de Bresenham, que dibuja rectas con números enteros y
        sin dividir.  Se usa aquí por lo que se nota al tacto y no por lo que se
        ve: una recta trazada saltándose puntos deja huecos, y un hueco bajo el
        dedo no es una recta más fina, es dos rayas.
        """
        x, y = int(x1), int(y1)
        destino_x, destino_y = int(x2), int(y2)
        paso_x = 1 if destino_x >= x else -1
        paso_y = 1 if destino_y >= y else -1
        avance_x = abs(destino_x - x)
        avance_y = -abs(destino_y - y)
        error = avance_x + avance_y
        vueltas = 0
        tope = self.puntos_de_ancho * self.puntos_de_alto + 4
        while vueltas < tope:
            self.encender(x, y)
            if x == destino_x and y == destino_y:
                return
            doble = 2 * error
            if doble >= avance_y:
                error += avance_y
                x += paso_x
            if doble <= avance_x:
                error += avance_x
                y += paso_y
            vueltas += 1

    def rectangulo(self, x1: int, y1: int, x2: int, y2: int) -> None:
        """Dibuja el contorno de un rectángulo, no su relleno.

        Relleno no se dibuja nunca: bajo el dedo, una mancha de puntos es una
        mancha, y lo que dice qué figura es son sus bordes.
        """
        self.segmento(x1, y1, x2, y1)
        self.segmento(x2, y1, x2, y2)
        self.segmento(x2, y2, x1, y2)
        self.segmento(x1, y2, x1, y1)

    def circunferencia(self, centro_x: int, centro_y: int, radio: int) -> None:
        """Dibuja una circunferencia por su contorno.

        Se recorre el ángulo y no la rejilla: en un lienzo donde los puntos son
        el doble de altos que de anchos, recorrer la rejilla da una elipse.
        """
        import math

        if radio <= 0:
            self.encender(centro_x, centro_y)
            return
        cuantos = max(16, int(radio * 8))
        for paso in range(cuantos):
            angulo = 2 * math.pi * paso / cuantos
            self.encender(int(round(centro_x + radio * math.cos(angulo))),
                          int(round(centro_y - radio * math.sin(angulo))))

    def poligono(self, puntos) -> None:
        """Une una lista de puntos y cierra la figura."""
        lista = [(int(x), int(y)) for x, y in puntos]
        if len(lista) < 2:
            return
        for numero in range(len(lista)):
            desde = lista[numero]
            hasta = lista[(numero + 1) % len(lista)]
            self.segmento(desde[0], desde[1], hasta[0], hasta[1])

    def lineas(self) -> list[str]:
        """El dibujo, una cadena de signos braille por línea."""
        return ["".join(chr(UNICODE_BRAILLE + celda) for celda in fila)
                for fila in self.puntos]

    def __str__(self) -> str:
        return "\n".join(self.lineas())


def _escalar(valores, ancho: int) -> list[float]:
    """Reparte los valores a lo ancho del dibujo.

    Con más valores que columnas se promedia por tramos, que conserva la forma;
    quedarse con uno de cada n dejaría fuera justo los picos, que es lo que se
    está intentando enseñar.
    """
    if not valores:
        return []
    if len(valores) <= ancho:
        # Menos datos que columnas: cada dato ocupa su tramo, sin inventar
        # valores intermedios que no están medidos.
        salida = []
        for columna in range(ancho):
            indice = int(columna * len(valores) / ancho)
            salida.append(valores[min(indice, len(valores) - 1)])
        return salida
    salida = []
    for columna in range(ancho):
        desde = int(columna * len(valores) / ancho)
        hasta = max(desde + 1, int((columna + 1) * len(valores) / ancho))
        tramo = valores[desde:hasta]
        salida.append(sum(tramo) / len(tramo))
    return salida


def curva(valores, ancho: int = ANCHO, alto: int = ALTO) -> Lienzo:
    """Dibuja una serie de números como una curva.

    Los puntos consecutivos **se unen con una raya vertical** cuando quedan a
    distinta altura. Sin unirlos, una subida fuerte se vería como dos puntos
    sueltos con un hueco en medio, que al tacto no es una subida: es nada.
    """
    lienzo = Lienzo(ancho, alto)
    numeros = [float(v) for v in valores if v is not None]
    if len(numeros) < 2:
        return lienzo
    escalados = _escalar(numeros, lienzo.puntos_de_ancho)
    menor = min(escalados)
    mayor = max(escalados)
    recorrido = mayor - menor
    tope = lienzo.puntos_de_alto - 1

    def altura(valor: float) -> int:
        if recorrido <= 0:
            # Todos iguales: una raya recta por la mitad, que es la verdad.
            return tope // 2
        return tope - int(round((valor - menor) / recorrido * tope))

    anterior = None
    for x, valor in enumerate(escalados):
        y = altura(valor)
        if anterior is not None and abs(y - anterior) > 1:
            paso = 1 if y > anterior else -1
            for medio in range(anterior + paso, y, paso):
                lienzo.encender(x, medio)
        lienzo.encender(x, y)
        anterior = y
    return lienzo


def barras(valores, ancho: int = ANCHO, alto: int = ALTO) -> Lienzo:
    """Dibuja una serie como barras que salen del suelo.

    Se usa cuando los datos son categorías —ventas por mes, votos por partido—
    y no una función continua: unir con una línea dos categorías que no tienen
    nada entre medias sugiere un paso gradual que no existe.
    """
    lienzo = Lienzo(ancho, alto)
    numeros = [float(v) for v in valores if v is not None]
    if not numeros:
        return lienzo
    escalados = _escalar(numeros, lienzo.puntos_de_ancho)
    menor = min(0.0, min(escalados))
    mayor = max(escalados)
    recorrido = mayor - menor
    tope = lienzo.puntos_de_alto - 1
    for x, valor in enumerate(escalados):
        if recorrido <= 0:
            alto_barra = tope
        else:
            alto_barra = tope - int(round((valor - menor) / recorrido * tope))
        for y in range(alto_barra, lienzo.puntos_de_alto):
            lienzo.encender(x, y)
    return lienzo


#: Con qué se marca cada serie cuando hay varias en el mismo dibujo. Son
#: patrones de puntos distintos dentro de la celda, no colores: al tacto, lo que
#: distingue dos series es que se noten diferentes, y con más de tres se dejan de
#: distinguir por mucho que se inventen patrones.
MARCAS_DE_SERIE = 3


def varias_curvas(series, ancho: int = ANCHO, alto: int = ALTO) -> Lienzo:
    """Dibuja varias series en el mismo lienzo, a la misma escala.

    A la misma escala **a propósito**: es lo único que permite comparar dos
    series, que es para lo que se ponen juntas. Cada una con su propia escala
    daría dos dibujos superpuestos que no dicen nada.

    Se admiten tres como mucho. Con cuatro, los puntos se pisan y lo que queda
    bajo el dedo es una mancha; decirlo es más útil que dibujar algo ilegible.
    """
    lienzo = Lienzo(ancho, alto)
    utiles = [list(serie) for serie in series if serie][:MARCAS_DE_SERIE]
    if not utiles:
        return lienzo
    todos = [valor for serie in utiles for valor in serie]
    minimo, maximo = min(todos), max(todos)
    rango = (maximo - minimo) or 1.0
    alto_puntos = lienzo.puntos_de_alto
    for numero, serie in enumerate(utiles):
        repartida = _escalar(serie, lienzo.puntos_de_ancho)
        anterior = None
        for columna, valor in enumerate(repartida):
            altura = int((valor - minimo) / rango * (alto_puntos - 1))
            fila = alto_puntos - 1 - altura
            if anterior is not None and abs(fila - anterior) > 1:
                paso = 1 if fila > anterior else -1
                for medio in range(anterior + paso, fila, paso):
                    lienzo.encender(columna, medio)
            lienzo.encender(columna, fila)
            # La segunda y la tercera serie se engrosan hacia abajo y hacia
            # arriba: con dos puntos seguidos se notan más gruesas, que es lo
            # que las separa de la primera al tacto.
            if numero == 1:
                lienzo.encender(columna, fila + 1)
            elif numero == 2 and columna % 2 == 0:
                lienzo.encender(columna, fila - 1)
            anterior = fila
    return lienzo


def figura(clase: str, ancho: int = ANCHO, alto: int = ALTO) -> Lienzo:
    """Dibuja una figura de geometría elemental, centrada en el lienzo.

    Se admiten ``circulo``, ``cuadrado``, ``rectangulo``, ``triangulo`` y
    ``rombo``.  Es poco, y es lo que se puede hacer bien: una figura de
    geometría se dibuja de memoria porque se sabe qué es. Un mapa o un circuito
    no, y por eso no están aquí.
    """
    lienzo = Lienzo(ancho, alto)
    medio_x = lienzo.puntos_de_ancho // 2
    medio_y = lienzo.puntos_de_alto // 2
    radio = min(medio_x, medio_y) - 1
    if radio < 1:
        return lienzo
    nombre = (clase or "").strip().lower()
    if nombre in ("circulo", "círculo", "circunferencia"):
        lienzo.circunferencia(medio_x, medio_y, radio)
    elif nombre in ("cuadrado", "rectangulo", "rectángulo"):
        lado_x = radio * 2 if nombre != "cuadrado" else radio
        lienzo.rectangulo(medio_x - lado_x, medio_y - radio,
                          medio_x + lado_x, medio_y + radio)
    elif nombre in ("triangulo", "triángulo"):
        lienzo.poligono([(medio_x, medio_y - radio),
                         (medio_x + radio * 2, medio_y + radio),
                         (medio_x - radio * 2, medio_y + radio)])
    elif nombre in ("rombo",):
        lienzo.poligono([(medio_x, medio_y - radio),
                         (medio_x + radio * 2, medio_y),
                         (medio_x, medio_y + radio),
                         (medio_x - radio * 2, medio_y)])
    return lienzo


#: Cuántas cajas se dibujan como mucho. Con más, cada una queda en dos puntos y
#: el dibujo deja de decir nada: es preferible no dibujarlo.
MAXIMAS_CAJAS = 24


def esquema(cajas, flechas, ancho: int = ANCHO, alto: int = ALTO) -> Lienzo:
    """Dibuja la **forma** de un diagrama: sus cajas y por dónde se une cada una.

    Es lo que la lista anidada no da. Una lista dice el camino paso a paso, y
    eso es lo que hace falta para seguirlo; lo que no dice es la **silueta**: si
    esto es una fila recta de ocho pasos o algo que se abre en dos ramas y se
    vuelve a juntar. Quien ve el diagrama sabe eso antes de leer nada.

    Se dibuja **de izquierda a derecha**, con los pasos avanzando a lo ancho y
    las ramas repartidas a lo alto.  En papel los diagramas de flujo van de
    arriba abajo, pero un renglón braille tiene ochenta puntos de ancho y
    dieciséis de alto: puesto en vertical, un diagrama de cinco pasos sale
    aplastado y no se distingue nada.

    Cada caja es un cuadradito y cada flecha una raya. Los rótulos no caben —una
    caja de cuatro puntos no admite texto—, así que las cajas van numeradas en
    el mismo orden que la lista de al lado.

    :param cajas: ``[(paso, rama)]``, una por caja, en el orden en que se
        numeran. El paso es lo lejos que está del principio y la rama, su sitio
        dentro de ese paso.
    :param flechas: ``[(desde, hasta)]``, con índices de la lista de cajas.
    """
    lienzo = Lienzo(ancho, alto)
    lista = [(int(paso), int(rama)) for paso, rama in cajas][:MAXIMAS_CAJAS]
    if not lista:
        return lienzo
    pasos = max(paso for paso, _r in lista) + 1
    ramas = max(rama for _p, rama in lista) + 1
    ancho_paso = max(4, lienzo.puntos_de_ancho // max(pasos, 1))
    alto_rama = max(3, lienzo.puntos_de_alto // max(ramas, 1))
    lado = max(1, min(ancho_paso // 2 - 1, alto_rama // 2 - 1, 3))

    centros = []
    for paso, rama in lista:
        centro_x = min(int((paso + 0.5) * ancho_paso),
                       lienzo.puntos_de_ancho - lado - 1)
        centro_y = min(int((rama + 0.5) * alto_rama),
                       lienzo.puntos_de_alto - lado - 1)
        centros.append((centro_x, centro_y))
        lienzo.rectangulo(centro_x - lado, centro_y - lado,
                          centro_x + lado, centro_y + lado)
    for desde, hasta in flechas:
        if not (0 <= desde < len(centros) and 0 <= hasta < len(centros)):
            continue
        if desde == hasta:
            continue
        origen, destino = centros[desde], centros[hasta]
        # La raya sale del borde de una caja y llega al borde de la otra, no del
        # centro: si atravesara las cajas, al tacto no habría cajas.
        if destino[0] > origen[0]:
            lienzo.segmento(origen[0] + lado + 1, origen[1],
                            destino[0] - lado - 1, destino[1])
        elif destino[0] < origen[0]:
            lienzo.segmento(origen[0] - lado - 1, origen[1],
                            destino[0] + lado + 1, destino[1])
        else:
            arriba = destino[1] > origen[1]
            lienzo.segmento(origen[0], origen[1] + (lado + 1 if arriba else -lado - 1),
                            destino[0], destino[1] - (lado + 1 if arriba else -lado - 1))
    return lienzo


def dibujar(valores, forma: str = "curva", ancho: int = ANCHO,
            alto: int = ALTO) -> str:
    """Devuelve el dibujo ya montado, listo para meterlo en el documento."""
    lienzo = barras(valores, ancho, alto) if forma == "barras" \
        else curva(valores, ancho, alto)
    return str(lienzo)


def resumen(valores) -> str:
    """Una frase con la forma de la curva, para quien no tenga línea braille.

    Va **siempre**, tenga o no el equipo con qué palpar el dibujo: la mayoría de
    la gente no tiene una línea braille de celdas gráficas, y esta frase es lo
    que les da la misma información en un renglón.
    """
    numeros = [float(v) for v in valores if v is not None]
    if len(numeros) < 2:
        return ""
    menor, mayor = min(numeros), max(numeros)
    donde_menor = numeros.index(menor) + 1
    donde_mayor = numeros.index(mayor) + 1
    subidas = sum(1 for a, b in zip(numeros, numeros[1:]) if b > a)
    bajadas = sum(1 for a, b in zip(numeros, numeros[1:]) if b < a)
    if subidas and not bajadas:
        forma = _("sube todo el rato")
    elif bajadas and not subidas:
        forma = _("baja todo el rato")
    elif numeros[-1] > numeros[0]:
        forma = _("sube en conjunto, con altibajos")
    elif numeros[-1] < numeros[0]:
        forma = _("baja en conjunto, con altibajos")
    else:
        forma = _("acaba donde empezó, con altibajos")
    return _("%(forma)s. El máximo, %(mayor)s, está en el punto %(donde_mayor)d "
             "de %(total)d; el mínimo, %(menor)s, en el %(donde_menor)d.") % {
        "forma": forma, "mayor": _numero(mayor), "menor": _numero(menor),
        "donde_mayor": donde_mayor, "donde_menor": donde_menor,
        "total": len(numeros)}


def _numero(valor: float) -> str:
    """Escribe un número sin decimales de más."""
    if abs(valor - round(valor)) < 1e-9:
        return str(int(round(valor)))
    return ("%.2f" % valor).rstrip("0").rstrip(".")
