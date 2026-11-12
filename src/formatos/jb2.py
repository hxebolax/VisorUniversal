# -*- coding: utf-8 -*-
"""JB2: las imágenes en blanco y negro de un DjVu.

Un DjVu de biblioteca guarda cada página en tres capas: la **máscara**, que es
el texto y los dibujos de línea en blanco y negro; y el fondo y el primer plano
en color, que son las manchas de papel y la tinta. La máscara va en un trozo
``Sjbz`` y se comprime con JB2. Este módulo la descomprime.

**Por qué hacía falta.** Hasta ahora un DjVu se leía por su capa de texto, que
es lo que hace falta cuando está. Un DjVu *sin* capa de texto —y hay muchos, los
que se digitalizaron sin pasar el reconocedor— no se podía leer de ninguna
manera: no había forma de sacar la página como imagen para reconocerla aquí. Con
la máscara descomprimida sí la hay, y además las figuras de un DjVu se pueden
ver y describir como las de cualquier otro documento.

**Cómo comprime JB2, en una idea.** Una página de texto escaneada es la misma
letra repetida miles de veces. En vez de guardar cada mancha, JB2 guarda un
**diccionario de formas** —una «a», una «e», una coma— y después, para cada una
de las miles de manchas de la página, dice qué forma del diccionario es y dónde
va. Las que se parecen a una que ya está pero no son idénticas se guardan como
la **diferencia** contra ella. De ahí que una página quepa en tres kilobytes.

Va todo sobre el mismo codificador ZP de ``bzz.py``, que ya estaba escrito y
comprobado: JB2 no es otro compresor, es otro **modelo** encima del mismo. Lo
que cambia son los contextos con los que se le pregunta.

**Los cuatro sitios donde es fácil equivocarse**, escritos aquí porque cada uno
cuesta una tarde:

- Las filas van **de abajo arriba**: la fila 0 es la de abajo del todo, como en
  DjVuLibre. Darles la vuelta parece inofensivo y descoloca todos los contextos,
  porque el contexto de un píxel son sus vecinos de *arriba*.
- El codificador de números **construye un árbol sobre la marcha**: cada nodo
  guarda su variable de contexto y los índices de sus dos hijos, y el camino que
  se recorre depende de los bits que van saliendo. No es una tabla fija.
- En ``_numero`` la decisión se toma **con cortocircuito**: si el rango ya está
  decidido no se lee ningún bit. Leerlo «por si acaso» desincroniza el
  descodificador en el acto.
- Los mapas llevan un **borde de tres celdas** a cada lado. No es holgura: los
  contextos miran hasta dos columnas a la izquierda y dos a la derecha, y en el
  desplazamiento hasta la columna siguiente al final de la fila.

**Lo que está escrito y no probado con un archivo de verdad:** el diccionario
compartido entre páginas —el trozo ``Djbz``—. De los DjVu mirados para esto no
lo llevaba ninguno: casi todos los compresores meten el diccionario dentro del
``Sjbz`` de cada página, y el compartido solo lo produce ``minidjvu``. El camino
está escrito porque una página que lo pida y no lo encuentre no se puede leer, y
la respuesta correcta es **negarse**: una página a la que le faltan las formas
heredadas saldría con manchas donde va el texto, y eso no se nota leyéndola.

Escrito siguiendo ``JB2Image.cpp`` y ``JB2Image.h`` de DjVuLibre, que están
guardados en ``adjuntos/Estudio/djvulibre``. El formato no tiene norma publicada
que sirva para escribir un descodificador.
"""
from __future__ import annotations

from .bzz import CodificadorZP, Corrupto

#: Los tipos de registro, en el orden en que los numera el formato.  El orden
#: importa: el propio tipo se lee como un número entre el primero y el último.
_INICIO = 0
_MARCA_NUEVA = 1
_MARCA_NUEVA_SOLO_BIBLIOTECA = 2
_MARCA_NUEVA_SOLO_IMAGEN = 3
_PARECIDA = 4
_PARECIDA_SOLO_BIBLIOTECA = 5
_PARECIDA_SOLO_IMAGEN = 6
_COPIA = 7
_SIN_MARCA = 8
_DICCIONARIO_O_REINICIO = 9
_COMENTARIO = 10
_FIN = 11

#: Los límites con los que se leen los números que no tienen otro tope.  Son los
#: de DjVuLibre y no se pueden cambiar: entran en el recorrido del árbol.
_MUY_POSITIVO = 262142
_MUY_NEGATIVO = -262143

#: Cuántas celdas de borde lleva cada mapa a cada lado.  Ver la cabecera.
_BORDE = 3

#: Tope de píxeles de un mapa, sea una forma suelta o la página entera.  Está
#: para que un archivo corrupto no pida dos mil millones de píxeles y deje el
#: programa sin memoria antes de que nadie pueda cancelar nada.
#:
#: Es alto a propósito, y el número no es redondo por casualidad: la portada de
#: un diario de gran formato de 1883 digitalizado a seiscientos puntos son
#: 8543×12807 —ciento nueve millones de píxeles—, y dentro lleva **una sola
#: forma** con el grabado de la cabecera que ocupa casi lo mismo.  Un tope
#: pequeño para las formas y otro grande para la página parecía razonable hasta
#: que apareció ese archivo: en JB2 un grabado a toda página es una forma más.
_MAXIMO_MAPA = 192 * 1024 * 1024


class Mapa:
    """Una imagen de un bit por píxel, con su borde de ceros alrededor.

    Las filas van **de abajo arriba** —``filas[0]`` es la de abajo— y dentro de
    cada una el píxel ``x`` está en la posición ``_BORDE + x``.  Pedir una fila
    que no existe devuelve una de ceros, que es justo lo que quieren los
    contextos al trabajar sobre la primera fila.
    """

    __slots__ = ("ancho", "alto", "filas", "_vacia")

    def __init__(self, ancho: int, alto: int) -> None:
        if ancho < 0 or alto < 0 or ancho * alto > _MAXIMO_MAPA:
            raise Corrupto("tamaño de mapa imposible: %dx%d" % (ancho, alto))
        self.ancho = ancho
        self.alto = alto
        largo = ancho + 2 * _BORDE
        self.filas = [bytearray(largo) for _ in range(alto)]
        self._vacia = bytearray(largo)

    def fila(self, y: int) -> bytearray:
        """La fila ``y``, o uno de ceros si se sale del mapa."""
        if 0 <= y < self.alto:
            return self.filas[y]
        return self._vacia

    def caja(self):
        """El rectángulo que ocupa lo pintado: ``(izq, der, abajo, arriba)``.

        Es lo que JB2 usa para centrar una forma contra otra al compararlas, y
        por eso se mide sobre la tinta y no sobre el tamaño declarado: dos
        letras del mismo alto pueden llevar cantidades de blanco muy distintas.
        Un mapa en blanco devuelve un rectángulo vacío —el derecho por debajo
        del izquierdo—, igual que DjVuLibre.
        """
        b = _BORDE
        ancho, alto = self.ancho, self.alto
        derecha = -1
        for x in range(ancho - 1, -1, -1):
            if any(fila[b + x] for fila in self.filas):
                derecha = x
                break
        arriba = -1
        for y in range(alto - 1, -1, -1):
            if any(self.filas[y][b:b + ancho]):
                arriba = y
                break
        izquierda = 0
        while izquierda <= derecha:
            if any(fila[b + izquierda] for fila in self.filas):
                break
            izquierda += 1
        abajo = 0
        while abajo <= arriba:
            if any(self.filas[abajo][b:b + ancho]):
                break
            abajo += 1
        return izquierda, derecha, abajo, arriba


class Forma:
    """Una forma del diccionario: su mapa y de cuál se sacó, si se sacó de una."""

    __slots__ = ("mapa", "padre")

    def __init__(self) -> None:
        self.mapa = None
        self.padre = -1


class Pegado:
    """Una forma puesta en un sitio de la página."""

    __slots__ = ("izquierda", "abajo", "forma")

    def __init__(self) -> None:
        self.izquierda = 0
        self.abajo = 0
        self.forma = -1


class Coleccion:
    """Un diccionario de formas, sea suelto (``Djbz``) o el de una página.

    Un ``Djbz`` es el diccionario **compartido** entre todas las páginas de un
    libro: la «a» se guarda una vez para el tomo entero.  Por eso una página
    puede empezar diciendo cuántas formas hereda, y sin ese trozo no se puede
    descomprimir.
    """

    __slots__ = ("formas", "heredadas", "heredado", "cajas", "ancho", "alto",
                 "pegados")

    def __init__(self) -> None:
        self.formas = []
        self.heredadas = 0
        self.heredado = None
        self.cajas = []
        self.ancho = 0
        self.alto = 0
        self.pegados = []

    def forma(self, numero: int) -> Forma:
        if self.heredado is not None and numero < self.heredadas:
            return self.heredado.forma(numero)
        indice = numero - self.heredadas
        if indice < 0 or indice >= len(self.formas):
            raise Corrupto("forma inexistente: %d" % numero)
        return self.formas[indice]

    def cuantas(self) -> int:
        return self.heredadas + len(self.formas)

    def caja_de(self, numero: int):
        """El rectángulo de la forma ``numero``, del diccionario que la tenga."""
        if self.heredado is not None and numero < self.heredadas:
            return self.heredado.caja_de(numero)
        indice = numero - self.heredadas
        if 0 <= indice < len(self.cajas):
            return self.cajas[indice]
        return self.forma(numero).mapa.caja()

    def anadir(self, forma: Forma) -> int:
        self.formas.append(forma)
        return self.cuantas() - 1


class _Descodificador:
    """El descodificador propiamente dicho: un ZP y un montón de contextos.

    Se escribe como una clase y no como una función porque los contextos son
    estado que dura todo el trozo: lo que hace que JB2 comprima es que las
    variables van aprendiendo, y reiniciarlas a mitad rompe la sincronía con el
    compresor.
    """

    def __init__(self, datos: bytes, inicio: int = 0, fin: int | None = None) -> None:
        self.zp = CodificadorZP(datos, inicio, fin)
        # Contextos de bit: uno por cada configuración de vecinos posible.  Mil
        # veinticuatro para el modo directo —diez vecinos— y dos mil cuarenta y
        # ocho para el de diferencias, que mira además la forma de referencia.
        self.directos = [0] * 1024
        self.cruzados = [0] * 2048
        self.reinicio_bandera = [0]
        # El árbol del codificador de números.  La celda 0 es el hueco que marca
        # «aquí todavía no hay nodo», así que el árbol de verdad empieza en 1.
        self.celdas = [0]
        self.izquierdas = [0]
        self.derechas = [0]
        self._reiniciar_numeros()
        # Estas dos no se reinician nunca, ni siquiera con el registro de
        # reinicio: lo dice DjVuLibre y hay que hacer lo mismo o el
        # descodificador deja de ir a la par del compresor.
        self.raices_bit = [0, 0]
        self.refinado = False
        self.hubo_inicio = False
        self.forma_a_biblioteca = []
        self.biblioteca_a_forma = []
        self.cajas = []
        self.columnas = 0
        self.filas_imagen = 0

    # -- el codificador de números ------------------------------------------

    def _reiniciar_numeros(self) -> None:
        """Todos los contextos numéricos a cero, y el árbol vacío.

        Lo pide el propio formato con un registro suyo: un archivo largo puede
        preferir empezar de nuevo si a mitad de página cambia la letra y lo
        aprendido ya no vale.
        """
        # Cada nombre es una raíz distinta del árbol.  Van en una lista para que
        # ``_numero`` pueda quedarse con «la lista y la posición» y escribir de
        # vuelta en su sitio, que es lo que en C++ hace un puntero.
        self.raices = [0] * _CUANTAS_RAICES
        del self.celdas[1:]
        del self.izquierdas[1:]
        del self.derechas[1:]

    def _numero(self, bajo: int, alto: int, lista: list, sitio: int) -> int:
        """Un número entre ``bajo`` y ``alto``, por el árbol de ``lista[sitio]``.

        El árbol se construye a medida que se recorre: cada decisión baja a un
        hijo que puede no existir todavía, y entonces se crea.  Así el modelo se
        adapta a los números que de verdad aparecen —los desplazamientos de una
        letra a la siguiente son casi siempre los mismos tres o cuatro— sin
        gastar nada en los que no aparecen nunca.
        """
        negativo = False
        corte = 0
        fase = 1
        rango = 0xffffffff
        while rango != 1:
            if not lista[sitio]:
                self.celdas.append(0)
                self.izquierdas.append(0)
                self.derechas.append(0)
                lista[sitio] = len(self.celdas) - 1
            nodo = lista[sitio]
            # El cortocircuito no es una optimización: cuando el rango ya está
            # decidido **no se lee ningún bit**, y leerlo desincroniza.
            decision = (bajo >= corte) or (
                alto >= corte and bool(self.zp.decodificar(self.celdas, nodo)))
            lista = self.derechas if decision else self.izquierdas
            sitio = nodo
            if fase == 1:
                negativo = not decision
                if negativo:
                    bajo, alto = -alto - 1, -bajo - 1
                fase = 2
                corte = 1
            elif fase == 2:
                if not decision:
                    fase = 3
                    rango = (corte + 1) // 2
                    corte = 0 if rango == 1 else corte - rango // 2
                else:
                    corte += corte + 1
            else:
                rango //= 2
                if rango != 1:
                    corte += rango // 2 if decision else -(rango // 2)
                elif not decision:
                    corte -= 1
        return -corte - 1 if negativo else corte

    def _num(self, bajo: int, alto: int, raiz: int) -> int:
        """Como ``_numero``, partiendo de una de las raíces con nombre."""
        return self._numero(bajo, alto, self.raices, raiz)

    def _bit(self, contextos: list, sitio: int) -> bool:
        return bool(self.zp.decodificar(contextos, sitio))

    # -- las piezas del formato ---------------------------------------------

    def _tipo_de_registro(self) -> int:
        return self._num(_INICIO, _FIN, _R_TIPO)

    def _indice_parecida(self) -> int:
        cual = self._num(0, len(self.biblioteca_a_forma) - 1, _R_PARECIDA)
        if cual < 0 or cual >= len(self.biblioteca_a_forma):
            raise Corrupto("referencia a una forma que no está")
        return cual

    def _tamano_absoluto(self) -> Mapa:
        ancho = self._num(0, _MUY_POSITIVO, _R_ANCHO_ABS)
        alto = self._num(0, _MUY_POSITIVO, _R_ALTO_ABS)
        if not 0 <= ancho <= 0xffff or not 0 <= alto <= 0xffff:
            raise Corrupto("tamaño de forma fuera de rango")
        return Mapa(ancho, alto)

    def _tamano_relativo(self, ancho_ref: int, alto_ref: int) -> Mapa:
        ancho = ancho_ref + self._num(_MUY_NEGATIVO, _MUY_POSITIVO, _R_ANCHO_REL)
        alto = alto_ref + self._num(_MUY_NEGATIVO, _MUY_POSITIVO, _R_ALTO_REL)
        if not 0 <= ancho <= 0xffff or not 0 <= alto <= 0xffff:
            raise Corrupto("tamaño de forma fuera de rango")
        return Mapa(ancho, alto)

    def _empezar(self) -> None:
        """Lo que deja preparado el registro de inicio.

        ``ultima_izquierda`` empieza *pasado el borde derecho* a propósito: así
        la primera forma de la página cuenta como «renglón nuevo» sin necesidad
        de un caso aparte.
        """
        self.ultima_izquierda = 1 + self.columnas
        self.izquierda_renglon = 0
        self.abajo_renglon = self.filas_imagen
        self.ultima_derecha = 0
        self.ultimo_abajo = self.abajo_renglon
        self.cortos = [self.abajo_renglon] * 3
        self.corto_actual = 0
        self.hubo_inicio = True

    def _empezar_diccionario(self) -> None:
        """Igual, pero un diccionario suelto no tiene página donde colocar."""
        self.ultima_izquierda = 1
        self.izquierda_renglon = 0
        self.abajo_renglon = 0
        self.ultima_derecha = 0
        self.ultimo_abajo = 0
        self.cortos = [0] * 3
        self.corto_actual = 0
        self.hubo_inicio = True

    def _mediana(self, valor: int) -> int:
        """La mediana de las tres últimas bases, que es la línea de escritura.

        Las letras de un renglón no están todas a la misma altura —una «p» baja,
        una «t» sube— así que tomar la última como referencia haría zigzaguear
        las predicciones.  La mediana de tres es estable y es lo que usa el
        formato.
        """
        self.corto_actual = (self.corto_actual + 1) % 3
        self.cortos[self.corto_actual] = valor
        a, b, c = self.cortos
        if a >= b:
            return (b if b >= c else c) if a > c else a
        return ((c if b >= c else b) if a < c else a)

    def _situar_relativo(self, pegado: Pegado, filas: int, columnas: int) -> None:
        """Dónde va esta forma, contado desde la anterior.

        Es la otra mitad de por qué JB2 comprime tanto: las posiciones no se
        guardan, se guarda **cuánto se ha avanzado**, y avanzar el ancho de una
        letra es el número que más se repite en toda la página.
        """
        if not self.hubo_inicio:
            raise Corrupto("una forma antes del registro de inicio")
        renglon_nuevo = self._bit(self.raices_bit, _B_TIPO_SALTO)
        if renglon_nuevo:
            izquierda = self.izquierda_renglon + self._num(
                _MUY_NEGATIVO, _MUY_POSITIVO, _R_X_RENGLON)
            arriba = self.abajo_renglon + self._num(
                _MUY_NEGATIVO, _MUY_POSITIVO, _R_Y_RENGLON)
            derecha = izquierda + columnas - 1
            abajo = arriba - filas + 1
            self.ultima_izquierda = self.izquierda_renglon = izquierda
            self.ultima_derecha = derecha
            self.ultimo_abajo = self.abajo_renglon = abajo
            self.cortos = [abajo] * 3
            self.corto_actual = 0
        else:
            izquierda = self.ultima_derecha + self._num(
                _MUY_NEGATIVO, _MUY_POSITIVO, _R_X_SEGUIDO)
            abajo = self.ultimo_abajo + self._num(
                _MUY_NEGATIVO, _MUY_POSITIVO, _R_Y_SEGUIDO)
            self.ultima_izquierda = izquierda
            self.ultima_derecha = izquierda + columnas - 1
            self.ultimo_abajo = self._mediana(abajo)
        pegado.abajo = abajo - 1
        pegado.izquierda = izquierda - 1

    def _situar_absoluto(self, pegado: Pegado, filas: int, columnas: int) -> None:
        if not self.hubo_inicio:
            raise Corrupto("una forma antes del registro de inicio")
        izquierda = self._num(1, self.columnas, _R_X_ABS)
        arriba = self._num(1, self.filas_imagen, _R_Y_ABS)
        pegado.abajo = arriba - filas
        pegado.izquierda = izquierda - 1

    # -- los dos modos de pintar --------------------------------------------

    def _pintar_directo(self, mapa: Mapa) -> None:
        """Píxel a píxel, prediciendo cada uno por sus diez vecinos de arriba.

        Los diez son los de las dos filas de encima y los dos de la izquierda de
        la propia: en una letra, saber eso deja el píxel siguiente casi decidido,
        y un bit casi decidido casi no ocupa.
        """
        zp = self.zp
        contextos = self.directos
        ancho = mapa.ancho
        b = _BORDE
        for y in range(mapa.alto - 1, -1, -1):
            dos = mapa.fila(y + 2)
            una = mapa.fila(y + 1)
            cero = mapa.filas[y]
            contexto = (
                (dos[b - 1] << 9) | (dos[b] << 8) | (dos[b + 1] << 7) |
                (una[b - 2] << 6) | (una[b - 1] << 5) | (una[b] << 4) |
                (una[b + 1] << 3) | (una[b + 2] << 2) |
                (cero[b - 2] << 1) | cero[b - 1])
            for x in range(ancho):
                n = zp.decodificar(contextos, contexto)
                cero[b + x] = n
                contexto = (((contexto << 1) & 0x37a) |
                            (una[b + x + 3] << 2) | (dos[b + x + 2] << 7) | n)

    def _pintar_por_diferencias(self, mapa: Mapa, referencia: Mapa,
                                caja) -> None:
        """Contra una forma que ya está: solo se guarda en qué se diferencian.

        Las dos se centran por su **tinta**, no por su tamaño declarado, porque
        lo que se compara son dos letras y no dos rectángulos.  El
        desplazamiento tiene que caber en quince píxeles: más que eso quiere
        decir que el archivo está roto y que se estaría leyendo cualquier cosa.
        """
        izq, der, aba, arr = caja
        ancho = mapa.ancho
        alto = mapa.alto
        dx = (ancho // 2 - ancho + 1) - ((der - izq + 1) // 2 - der)
        dy = (alto // 2 - alto + 1) - ((arr - aba + 1) // 2 - arr)
        if not -15 <= dx <= 15 or not -15 <= dy <= 15:
            raise Corrupto("dos formas que no se pueden centrar")
        zp = self.zp
        contextos = self.cruzados
        b = _BORDE
        # La fila de la referencia se copia desplazada a un trozo con dos celdas
        # de holgura a cada lado, que es hasta donde miran los contextos.
        anchura_ref = referencia.ancho

        def fila_ref(cy: int) -> bytearray:
            origen = referencia.fila(cy)
            trozo = bytearray(ancho + 4)
            for i in range(ancho + 4):
                columna = i - 2 + dx
                if 0 <= columna < anchura_ref:
                    trozo[i] = origen[b + columna]
            return trozo

        y = alto - 1
        cy = y + dy
        una = mapa.fila(y + 1)
        arriba_ref = fila_ref(cy + 1)
        misma_ref = fila_ref(cy)
        abajo_ref = fila_ref(cy - 1)
        while y >= 0:
            cero = mapa.filas[y]
            contexto = (
                (una[b - 1] << 10) | (una[b] << 9) | (una[b + 1] << 8) |
                (cero[b - 1] << 7) |
                (arriba_ref[2] << 6) |
                (misma_ref[1] << 5) | (misma_ref[2] << 4) | (misma_ref[3] << 3) |
                (abajo_ref[1] << 2) | (abajo_ref[2] << 1) | abajo_ref[3])
            for x in range(ancho):
                n = zp.decodificar(contextos, contexto)
                cero[b + x] = n
                contexto = (((contexto << 1) & 0x636) |
                            (una[b + x + 2] << 8) |
                            (arriba_ref[x + 3] << 6) |
                            (misma_ref[x + 4] << 3) |
                            abajo_ref[x + 4] |
                            (n << 7))
            y -= 1
            cy -= 1
            una = cero
            arriba_ref = misma_ref
            misma_ref = abajo_ref
            abajo_ref = fila_ref(cy - 1)

    # -- la biblioteca ------------------------------------------------------

    def _iniciar_biblioteca(self, coleccion: Coleccion) -> None:
        cuantas = coleccion.heredadas
        self.forma_a_biblioteca = list(range(cuantas))
        self.biblioteca_a_forma = list(range(cuantas))
        self.cajas = [coleccion.caja_de(i) for i in range(cuantas)]

    def _anadir_a_biblioteca(self, numero: int, forma: Forma) -> None:
        self.biblioteca_a_forma.append(numero)
        while len(self.forma_a_biblioteca) <= numero:
            self.forma_a_biblioteca.append(-1)
        self.forma_a_biblioteca[numero] = len(self.biblioteca_a_forma) - 1
        self.cajas.append(forma.mapa.caja())

    def _comentario(self) -> None:
        cuantos = self._num(0, _MUY_POSITIVO, _R_LARGO_COMENTARIO)
        for _i in range(cuantos):
            self._num(0, 255, _R_BYTE_COMENTARIO)

    def _cuantas_hereda(self, coleccion: Coleccion) -> None:
        cuantas = self._num(0, _MUY_POSITIVO, _R_HEREDADAS)
        if cuantas:
            if coleccion.heredado is None:
                raise Corrupto("la página necesita un diccionario Djbz que no está")
            if cuantas != coleccion.heredado.cuantas():
                raise Corrupto("el diccionario Djbz no es el de esta página")
            coleccion.heredadas = cuantas

    # -- el bucle -----------------------------------------------------------

    def descodificar(self, coleccion: Coleccion, es_pagina: bool) -> None:
        """Lee registro tras registro hasta el de fin."""
        tipo = -1
        vueltas = 0
        while tipo != _FIN:
            vueltas += 1
            if vueltas > 4_000_000:
                raise Corrupto("demasiados registros: el archivo no acaba")
            tipo = self._registro(coleccion, es_pagina)
        if not self.hubo_inicio:
            raise Corrupto("el trozo no trae registro de inicio")
        if not es_pagina:
            coleccion.cajas = list(self.cajas[coleccion.heredadas:])

    def _registro(self, coleccion: Coleccion, es_pagina: bool) -> int:
        tipo = self._tipo_de_registro()
        forma = None
        pegado = Pegado() if es_pagina else None
        mapa = None
        cual = -1

        admitidos = _DE_PAGINA if es_pagina else _DE_DICCIONARIO
        if tipo not in admitidos:
            raise Corrupto("registro JB2 de tipo %d donde no cabe" % tipo)
        if tipo in (_CON_FORMA if es_pagina else _CON_FORMA_DICCIONARIO):
            forma = Forma()
            if tipo == _SIN_MARCA:
                forma.padre = -2

        if tipo == _INICIO:
            if es_pagina:
                self.columnas = self._num(0, _MUY_POSITIVO, _R_TAMANO)
                self.filas_imagen = self._num(0, _MUY_POSITIVO, _R_TAMANO)
                if not self.columnas or not self.filas_imagen:
                    raise Corrupto("la página no tiene tamaño")
                coleccion.ancho = self.columnas
                coleccion.alto = self.filas_imagen
                self.refinado = self._bit(self.raices_bit, _B_REFINADO)
                self._empezar()
            else:
                ancho = self._num(0, _MUY_POSITIVO, _R_TAMANO)
                alto = self._num(0, _MUY_POSITIVO, _R_TAMANO)
                if ancho or alto:
                    raise Corrupto("un diccionario no puede traer tamaño")
                self.refinado = self._bit(self.raices_bit, _B_REFINADO)
                self._empezar_diccionario()
            self._iniciar_biblioteca(coleccion)

        elif tipo == _MARCA_NUEVA:
            mapa = forma.mapa = self._tamano_absoluto()
            self._pintar_directo(mapa)
            self._situar_relativo(pegado, mapa.alto, mapa.ancho)

        elif tipo == _MARCA_NUEVA_SOLO_BIBLIOTECA:
            mapa = forma.mapa = self._tamano_absoluto()
            self._pintar_directo(mapa)

        elif tipo == _MARCA_NUEVA_SOLO_IMAGEN:
            mapa = forma.mapa = self._tamano_absoluto()
            self._pintar_directo(mapa)
            self._situar_relativo(pegado, mapa.alto, mapa.ancho)

        elif tipo in (_PARECIDA, _PARECIDA_SOLO_BIBLIOTECA, _PARECIDA_SOLO_IMAGEN):
            cual = self._indice_parecida()
            forma.padre = self.biblioteca_a_forma[cual]
            referencia = coleccion.forma(forma.padre).mapa
            izq, der, aba, arr = self.cajas[cual]
            mapa = forma.mapa = self._tamano_relativo(der - izq + 1, arr - aba + 1)
            # Dentro de una **página**, la forma que solo va a la biblioteca se
            # queda en blanco: se lee su tamaño y ahí acaba el registro.  Parece
            # un descuido de DjVuLibre y probablemente lo sea, pero su
            # compresor escribe exactamente eso, así que leer aquí las
            # diferencias sería leerlas donde no están y perder el resto del
            # archivo.  En un **diccionario** sí se leen: es otra rama del
            # mismo programa y ahí sí está la llamada.
            pinta = (tipo != _PARECIDA_SOLO_BIBLIOTECA) if es_pagina else True
            if pinta:
                self._pintar_por_diferencias(mapa, referencia, self.cajas[cual])
            if es_pagina and tipo in (_PARECIDA, _PARECIDA_SOLO_IMAGEN):
                self._situar_relativo(pegado, mapa.alto, mapa.ancho)

        elif tipo == _COPIA:
            cual = self._indice_parecida()
            pegado.forma = self.biblioteca_a_forma[cual]
            izq, der, aba, arr = self.cajas[cual]
            pegado.izquierda += izq
            pegado.abajo += aba
            self._situar_relativo(pegado, arr - aba + 1, der - izq + 1)
            pegado.izquierda -= izq
            pegado.abajo -= aba

        elif tipo == _SIN_MARCA:
            mapa = forma.mapa = self._tamano_absoluto()
            self._pintar_directo(mapa)
            self._situar_absoluto(pegado, mapa.alto, mapa.ancho)

        elif tipo == _COMENTARIO:
            self._comentario()

        elif tipo == _DICCIONARIO_O_REINICIO:
            if not self.hubo_inicio:
                self._cuantas_hereda(coleccion)
            else:
                self._reiniciar_numeros()

        elif tipo != _FIN:
            raise Corrupto("registro JB2 de tipo desconocido: %d" % tipo)

        # -- lo que hay que hacer después ------------------------------------
        numero = -1
        if forma is not None and forma.mapa is not None:
            numero = coleccion.anadir(forma)
            while len(self.forma_a_biblioteca) <= numero:
                self.forma_a_biblioteca.append(-1)
        if tipo in _A_BIBLIOTECA and numero >= 0:
            self._anadir_a_biblioteca(numero, forma)
        if es_pagina and tipo in _CON_PEGADO:
            if tipo != _COPIA:
                pegado.forma = numero
            coleccion.pegados.append(pegado)
        return tipo


#: Qué tipos de registro admite cada trozo.  Un diccionario suelto no coloca
#: nada en ninguna página, así que ni siquiera sabe qué sería colocarlo.
_DE_PAGINA = frozenset(range(_INICIO, _FIN + 1))
_DE_DICCIONARIO = frozenset((_INICIO, _MARCA_NUEVA_SOLO_BIBLIOTECA,
                             _PARECIDA_SOLO_BIBLIOTECA, _COMENTARIO,
                             _DICCIONARIO_O_REINICIO, _FIN))

#: Los registros que traen forma nueva, en una página y en un diccionario.
_CON_FORMA = frozenset((_MARCA_NUEVA, _MARCA_NUEVA_SOLO_BIBLIOTECA,
                        _MARCA_NUEVA_SOLO_IMAGEN, _PARECIDA,
                        _PARECIDA_SOLO_BIBLIOTECA, _PARECIDA_SOLO_IMAGEN,
                        _SIN_MARCA))
_CON_FORMA_DICCIONARIO = frozenset((_MARCA_NUEVA_SOLO_BIBLIOTECA,
                                    _PARECIDA_SOLO_BIBLIOTECA))

#: Los que además guardan la forma en la biblioteca para poder repetirla.
_A_BIBLIOTECA = frozenset((_MARCA_NUEVA, _MARCA_NUEVA_SOLO_BIBLIOTECA,
                           _PARECIDA, _PARECIDA_SOLO_BIBLIOTECA))

#: Los que colocan algo en la página.
_CON_PEGADO = frozenset((_MARCA_NUEVA, _MARCA_NUEVA_SOLO_IMAGEN, _PARECIDA,
                         _PARECIDA_SOLO_IMAGEN, _SIN_MARCA, _COPIA))

#: Las raíces del codificador de números, una por cada clase de número que el
#: formato distingue.  Están separadas porque cada una tiene su reparto: los
#: desplazamientos dentro de un renglón no se parecen en nada a los tamaños.
(_R_BYTE_COMENTARIO, _R_LARGO_COMENTARIO, _R_TIPO, _R_PARECIDA, _R_X_ABS,
 _R_Y_ABS, _R_ANCHO_ABS, _R_ALTO_ABS, _R_TAMANO, _R_HEREDADAS, _R_X_SEGUIDO,
 _R_X_RENGLON, _R_Y_SEGUIDO, _R_Y_RENGLON, _R_ANCHO_REL,
 _R_ALTO_REL) = range(16)
_CUANTAS_RAICES = 16

#: Las dos variables de bit sueltas: si la página lleva refinado sin pérdidas y
#: si la forma siguiente empieza renglón.
_B_REFINADO, _B_TIPO_SALTO = 0, 1


def leer_diccionario(datos: bytes, inicio: int = 0,
                     fin: int | None = None) -> Coleccion:
    """Descomprime un trozo ``Djbz``: el diccionario compartido del libro."""
    coleccion = Coleccion()
    _Descodificador(datos, inicio, fin).descodificar(coleccion, False)
    return coleccion


def leer_mascara(datos: bytes, inicio: int = 0, fin: int | None = None,
                 diccionario: Coleccion | None = None) -> Coleccion:
    """Descomprime un trozo ``Sjbz``: la máscara de una página."""
    coleccion = Coleccion()
    coleccion.heredado = diccionario
    _Descodificador(datos, inicio, fin).descodificar(coleccion, True)
    return coleccion


def componer(coleccion: Coleccion) -> Mapa:
    """Pone cada forma en su sitio y devuelve la página entera.

    Se compone al final y no sobre la marcha porque una forma se coloca muchas
    veces: la «a» del diccionario se pinta una vez y se pega doscientas.
    """
    pagina = Mapa(coleccion.ancho, coleccion.alto)
    b = _BORDE
    for pegado in coleccion.pegados:
        try:
            mapa = coleccion.forma(pegado.forma).mapa
        except Corrupto:
            # Un pegado que apunta a una forma que no está no invalida la
            # página: se pierde una letra y se sigue, que es infinitamente
            # mejor que no poder leer nada.
            continue
        if mapa is None:
            continue
        for y in range(mapa.alto):
            destino_y = pegado.abajo + y
            if not 0 <= destino_y < pagina.alto:
                continue
            origen = mapa.filas[y]
            destino = pagina.filas[destino_y]
            for x in range(mapa.ancho):
                if origen[b + x]:
                    columna = pegado.izquierda + x
                    if 0 <= columna < pagina.ancho:
                        destino[b + columna] = 1
    return pagina


def filas_empaquetadas(mapa: Mapa) -> list[bytes]:
    """Las filas del mapa de arriba abajo y a ocho píxeles por byte.

    El mapa está de abajo arriba y en JB2 el uno es **tinta**; un PNG en blanco
    y negro va de arriba abajo y su uno es **papel**.  Las dos vueltas se dan
    aquí, en un sitio, en vez de dejarlas repartidas por quien lo use.
    """
    b = _BORDE
    ancho = mapa.ancho
    por_fila = (ancho + 7) // 8
    salida = []
    for y in range(mapa.alto - 1, -1, -1):
        fila = mapa.filas[y]
        empaquetada = bytearray(b"\xff" * por_fila)
        for x in range(ancho):
            if fila[b + x]:
                empaquetada[x >> 3] &= ~(0x80 >> (x & 7)) & 0xff
        salida.append(bytes(empaquetada))
    return salida


def a_png(mapa: Mapa) -> bytes:
    """La página como PNG en blanco y negro, lista para reconocer o para ver."""
    from . import png

    return png.codificar_un_bit(mapa.ancho, mapa.alto, filas_empaquetadas(mapa))
