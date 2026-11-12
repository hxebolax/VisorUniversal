# -*- coding: utf-8 -*-
"""Diagramas de flujo, circuitos y organigramas: su estructura, no su foto.

Un diagrama de flujo descrito en un párrafo no sirve para seguirlo. «Un diagrama
con seis cajas y dos rombos de decisión» dice qué hay dibujado y no dice **por
dónde se va**, que es lo único que un diagrama de flujo cuenta. Y es de lo que
más se queja quien estudia una ingeniería o una asignatura de procedimientos.

La diferencia con :mod:`nucleo.graficos` es la forma del dato. Un gráfico de
barras es una tabla: filas y columnas, y con eso ya se recorre. Un diagrama no
es una tabla: es un **grafo** —cajas y flechas—, y lo que se puede recorrer de un
grafo es su **recorrido**, que en braille y de oído se lee como una lista
anidada: de aquí se va a esto, y si la respuesta es «sí» a esto otro.

Por eso lo que sale de aquí es una lista anidada de verdad, con sus ``<ol>``:
así el lector de pantalla la anuncia como lista, dice en qué nivel está y se
salta de elemento en elemento con sus propias órdenes. Un párrafo con flechas
escritas con guiones no se puede recorrer así.

**Qué se hace con los ciclos.** Un diagrama de flujo casi siempre tiene alguno
—un bucle que vuelve atrás—, y una lista anidada no puede repetirlo sin dar
vueltas para siempre. Cuando el recorrido llega a un paso por el que ya se pasó,
se escribe «vuelve al paso N» y se corta ahí. Es exactamente lo que diría alguien
leyéndolo en voz alta.

**Y lo que no se sabe, no se inventa.** Si la imagen no es un diagrama con
estructura, la IA lo dice y aquí no se guarda nada. Un diagrama inventado es peor
que ninguno: parece un procedimiento.
"""

from __future__ import annotations

import re

from .idioma import _
from .idioma import _n
from .registro import obtener_registro

log = obtener_registro(__name__)

#: Instrucción que se manda con la imagen. Pide **dos tablas** —las cajas y las
#: flechas— por la misma razón por la que el módulo de gráficos pide una tabla
#: de Markdown: es lo que mejor escriben todos los modelos y, sobre todo, se
#: degrada bien. Si el modelo se despista en una flecha, se pierde esa flecha y
#: el resto del diagrama sigue valiendo.
INSTRUCCION = _(
    "Esta imagen es un diagrama con estructura: un diagrama de flujo, un "
    "organigrama, un mapa conceptual, un esquema de un circuito o similar. Tu "
    "tarea es extraer SU ESTRUCTURA —las cajas y las flechas—, no describirla.\n\n"
    "Responde EXACTAMENTE con este formato y con nada más:\n\n"
    "TITULO: el título del diagrama, o de qué trata si no lo lleva escrito\n"
    "TIPO: diagrama de flujo, organigrama, mapa conceptual, circuito u otro\n"
    "CAJAS:\n"
    "| id | clase | texto |\n"
    "| --- | --- | --- |\n"
    "| 1 | inicio | Empezar |\n"
    "| 2 | paso | Leer el archivo |\n"
    "| 3 | decision | ¿Existe el archivo? |\n"
    "| 4 | fin | Terminar |\n"
    "FLECHAS:\n"
    "| desde | hasta | rotulo |\n"
    "| --- | --- | --- |\n"
    "| 1 | 2 | |\n"
    "| 3 | 4 | sí |\n"
    "NOTA: una sola frase con lo que no quepa en las tablas, o «ninguna»\n"
    "FIABILIDAD: alta, media o baja, seguida de dos puntos y de una frase corta "
    "diciendo por qué\n\n"
    "Reglas:\n"
    "- Numera las cajas de 1 en adelante, en el orden en que aparecen de arriba "
    "abajo y de izquierda a derecha.\n"
    "- La clase es una de estas: inicio, fin, paso, decision, entrada, salida, "
    "dato, componente u otro. Si no lo tienes claro, escribe «paso».\n"
    "- Copia el texto de cada caja tal y como está escrito, sin resumirlo.\n"
    "- Pon una fila de FLECHAS por cada flecha del dibujo, incluidas las que "
    "vuelven hacia atrás. El rótulo es lo que ponga sobre la flecha («sí», "
    "«no», «si falla»...); si no pone nada, déjalo vacío.\n"
    "- Si una flecha no tiene punta y solo une dos cajas (como en un circuito), "
    "escríbela igual, en el orden en que se lee el dibujo.\n"
    "- En FIABILIDAD, pon «alta» solo si has podido leer todas las cajas y "
    "seguir todas las flechas. Pon «media» si alguna flecha se cruza con otra o "
    "algún texto está pequeño. Pon «baja» si el diagrama está tan apretado que "
    "has tenido que suponer por dónde va alguna flecha. **No te pongas alta por "
    "cortesía**: en un diagrama de flujo, una flecha mal leída cambia el "
    "procedimiento entero.\n"
    "- Si la imagen NO es un diagrama con cajas y flechas, responde únicamente: "
    "NO ES UN DIAGRAMA")

#: Lo que responde la IA cuando la imagen no tiene estructura que sacar.
SIN_ESTRUCTURA = "no es un diagrama"

#: Marca que llevan los datos guardados en disco, para distinguirlos de la
#: rejilla de un gráfico: las dos cosas se guardan en el mismo sitio.
MARCA = "ESQUEMA"

#: Topes de sensatez. Un diagrama de verdad no tiene trescientas cajas; si
#: salen, es que el modelo se ha desbocado.
MAXIMAS_CAJAS = 120
MAXIMAS_FLECHAS = 300

#: Hasta dónde se anida el recorrido. Más allá, la lista deja de poder leerse
#: —el lector de pantalla canta ocho niveles antes de cada línea— y lo que se
#: hace es cortar diciendo a dónde sigue.
NIVELES = 8

#: Cómo se lee en voz alta cada clase de caja. Va delante del texto porque es lo
#: que dice de qué tipo de paso se trata, y en un diagrama de flujo saber que
#: algo es una decisión antes de oírla es la mitad del trabajo.
CLASES = {
    "inicio": _("inicio"),
    "fin": _("fin"),
    "paso": _("paso"),
    "decision": _("decisión"),
    "entrada": _("entrada"),
    "salida": _("salida"),
    "dato": _("dato"),
    "componente": _("componente"),
}

_SEPARADORA = re.compile(r"^[\s:|+-]+$")

_ROTULOS = {
    "titulo": ("titulo", "título", "title"),
    "tipo": ("tipo", "type"),
    "cajas": ("cajas", "nodos", "boxes", "nodes"),
    "flechas": ("flechas", "arrows", "aristas", "edges"),
    "nota": ("nota", "note", "notas"),
    "fiabilidad": ("fiabilidad", "confianza", "reliability", "confidence"),
}


def _sin_tildes(texto: str) -> str:
    import unicodedata

    plano = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(letra for letra in plano if not unicodedata.combining(letra))


def _rotulo_de(linea: str):
    """Si la línea empieza por uno de los rótulos, lo devuelve con su resto."""
    if ":" not in linea:
        return None
    nombre, resto = linea.split(":", 1)
    limpio = _sin_tildes(nombre.strip().strip("*# "))
    for clave, formas in _ROTULOS.items():
        if limpio in [_sin_tildes(forma) for forma in formas]:
            return clave, resto.strip()
    return None


def _celdas(linea: str):
    """Las celdas de una fila de tabla, o ``None`` si la línea no lo es."""
    crudo = linea.strip()
    if not crudo or _SEPARADORA.match(crudo):
        return None
    if crudo.startswith("|"):
        crudo = crudo[1:]
    if crudo.endswith("|"):
        crudo = crudo[:-1]
    if "|" in crudo:
        partes = crudo.split("|")
    elif "\t" in crudo:
        partes = crudo.split("\t")
    else:
        return None
    return [parte.strip() for parte in partes]


class Caja:
    """Una caja del diagrama: qué es y qué pone dentro."""

    __slots__ = ("identificador", "clase", "texto")

    def __init__(self, identificador: str, clase: str = "paso",
                 texto: str = "") -> None:
        self.identificador = identificador
        self.clase = clase or "paso"
        self.texto = texto

    def nombre(self) -> str:
        """Cómo se lee: «decisión: ¿existe el archivo?»."""
        clase = CLASES.get(self.clase)
        if clase and self.clase not in ("paso", "otro"):
            return "%s: %s" % (clase, self.texto or _("(sin texto)"))
        return self.texto or _("(sin texto)")


class Flecha:
    """Una flecha: de dónde sale, a dónde va y qué pone encima."""

    __slots__ = ("desde", "hasta", "rotulo")

    def __init__(self, desde: str, hasta: str, rotulo: str = "") -> None:
        self.desde = desde
        self.hasta = hasta
        self.rotulo = rotulo


class Esquema:
    """Un diagrama con estructura: sus cajas, sus flechas y su recorrido."""

    __slots__ = ("titulo", "tipo", "cajas", "flechas", "nota", "fiabilidad",
                 "por_que")

    def __init__(self, titulo: str = "", tipo: str = "", cajas=None,
                 flechas=None, nota: str = "", fiabilidad: str = "",
                 por_que: str = "") -> None:
        self.titulo = titulo
        self.tipo = tipo
        self.cajas: list[Caja] = list(cajas or [])
        self.flechas: list[Flecha] = list(flechas or [])
        self.nota = nota
        self.fiabilidad = fiabilidad
        self.por_que = por_que

    def __bool__(self) -> bool:
        return bool(self.cajas)

    # -- consultas -----------------------------------------------------------

    def caja(self, identificador: str):
        for caja in self.cajas:
            if caja.identificador == identificador:
                return caja
        return None

    def salidas_de(self, identificador: str) -> list[Flecha]:
        return [flecha for flecha in self.flechas
                if flecha.desde == identificador]

    def entradas(self) -> list[Caja]:
        """Por dónde se empieza: las cajas a las que no llega ninguna flecha.

        Si todas tienen entrada —un diagrama que es un ciclo cerrado— se empieza
        por la primera, que es lo único razonable: hay que empezar por algún
        sitio y decirlo.
        """
        llegan = {flecha.hasta for flecha in self.flechas}
        sueltas = [caja for caja in self.cajas
                   if caja.identificador not in llegan]
        if sueltas:
            return sueltas
        return self.cajas[:1]

    def numero_de(self, identificador: str) -> int:
        """En qué puesto está una caja, para poder decir «vuelve al paso 3»."""
        for numero, caja in enumerate(self.cajas, start=1):
            if caja.identificador == identificador:
                return numero
        return 0

    def cuantas_decisiones(self) -> int:
        return sum(1 for caja in self.cajas if caja.clase == "decision")

    def resumen(self) -> str:
        """Frase con lo que tiene el diagrama, para anunciarlo."""
        piezas = [_n("%d caja", "%d cajas", len(self.cajas)) % len(self.cajas),
                  _n("%d flecha", "%d flechas", len(self.flechas))
                  % len(self.flechas)]
        decisiones = self.cuantas_decisiones()
        if decisiones:
            piezas.append(_n("%d decisión", "%d decisiones", decisiones)
                          % decisiones)
        return _("%s.") % ", ".join(piezas)

    def hay_que_avisar(self) -> bool:
        """Si la fiabilidad declarada obliga a advertirlo."""
        return self.fiabilidad in ("media", "baja")

    def aviso(self) -> str:
        """Lo que se dice cuando la IA no se ha fiado del todo de sí misma."""
        if not self.hay_que_avisar():
            return ""
        cabeza = (_("La inteligencia artificial ha tenido que suponer por dónde "
                    "va alguna flecha.") if self.fiabilidad == "media"
                  else _("La inteligencia artificial dice que ha leído este "
                         "diagrama con poca seguridad."))
        return "%s %s" % (cabeza, self.por_que) if self.por_que else cabeza

    # -- el recorrido --------------------------------------------------------

    def recorrido(self):
        """El diagrama como un árbol que se puede leer siguiendo las flechas.

        Devuelve una lista de ``(nivel, texto, identificador o "")``.  Un nivel
        más adentro es un paso al que se llega desde el anterior; el rótulo de
        la flecha —«sí», «no»— va delante del paso al que lleva, porque es la
        condición para llegar hasta él.
        """
        salida: list[tuple[int, str, str]] = []
        for arranque in self.entradas():
            self._bajar(arranque.identificador, "", 0, [], salida)
        return salida

    def _bajar(self, identificador: str, rotulo: str, nivel: int,
               camino: list, salida: list) -> None:
        """Escribe una caja y, debajo, aquello a lo que lleva."""
        caja = self.caja(identificador)
        if caja is None:
            return
        texto = caja.nombre()
        if rotulo:
            texto = _("si %(rotulo)s, %(paso)s") % {"rotulo": rotulo,
                                                    "paso": texto}
        if identificador in camino:
            # Un bucle. Se dice a dónde vuelve y se corta: repetirlo daría
            # vueltas para siempre, y quien lo lee ya ha pasado por ahí. El
            # rótulo se conserva porque en un diagrama de flujo el bucle suele
            # ser justo la rama del «no», y sin decirlo no se sabe cuándo se
            # vuelve.
            vuelta = _("vuelve al paso %d") % self.numero_de(identificador)
            if rotulo:
                vuelta = _("si %(rotulo)s, %(paso)s") % {"rotulo": rotulo,
                                                         "paso": vuelta}
            salida.append((nivel, vuelta, ""))
            return
        salida.append((nivel, texto, identificador))
        # Se corta un nivel antes del tope: la línea que dice por dónde sigue
        # va **dentro** del paso que se corta, así que también ocupa nivel.
        if nivel + 2 >= NIVELES:
            siguientes = self.salidas_de(identificador)
            if siguientes:
                salida.append((nivel + 1, _("sigue en el paso %d")
                               % self.numero_de(siguientes[0].hasta), ""))
            return
        for flecha in self.salidas_de(identificador):
            self._bajar(flecha.hasta, flecha.rotulo, nivel + 1,
                        camino + [identificador], salida)

    def lineas(self) -> list[str]:
        """El recorrido en texto, con sangría. Para leerlo de corrido."""
        return ["%s%s" % ("  " * nivel, texto)
                for nivel, texto, _id in self.recorrido()]

    def planta(self):
        """Dónde va cada caja si se dibuja: ``([(nivel, rama)], [(de, a)])``.

        El nivel es lo lejos que está del principio siguiendo las flechas, y la
        rama, en qué sitio de ese nivel cae. Con eso se puede dibujar la silueta
        del diagrama, que es lo que la lista anidada no cuenta: si esto es una
        fila recta o un rombo que se abre y se vuelve a juntar.
        """
        niveles: dict[str, int] = {}
        for arranque in self.entradas():
            self._niveles_desde(arranque.identificador, 0, [], niveles)
        if not niveles:
            return [], []
        orden = [caja.identificador for caja in self.cajas
                 if caja.identificador in niveles]
        ocupacion: dict[int, int] = {}
        sitio = {}
        for identificador in orden:
            nivel = niveles[identificador]
            rama = ocupacion.get(nivel, 0)
            ocupacion[nivel] = rama + 1
            sitio[identificador] = (nivel, rama)
        cajas = [sitio[identificador] for identificador in orden]
        numero_de = {identificador: numero
                     for numero, identificador in enumerate(orden)}
        flechas = [(numero_de[flecha.desde], numero_de[flecha.hasta])
                   for flecha in self.flechas
                   if flecha.desde in numero_de and flecha.hasta in numero_de]
        return cajas, flechas

    def _niveles_desde(self, identificador: str, nivel: int, camino: list,
                       niveles: dict) -> None:
        """Reparte las cajas por niveles siguiendo las flechas, sin dar vueltas."""
        if identificador in camino or nivel > NIVELES:
            return
        antes = niveles.get(identificador)
        if antes is not None and antes <= nivel:
            return
        niveles[identificador] = nivel
        for flecha in self.salidas_de(identificador):
            self._niveles_desde(flecha.hasta, nivel + 1,
                                camino + [identificador], niveles)

    # -- guardar y traer -----------------------------------------------------

    def para_guardar(self) -> str:
        """El diagrama como rejilla de texto, que es como se guarda en disco.

        Se guarda **ya interpretado** y no la respuesta cruda de la IA, por lo
        mismo que los gráficos: lo que interesa conservar es la estructura.
        """
        filas = [[MARCA, self.tipo or ""]]
        for caja in self.cajas:
            filas.append(["C", caja.identificador, caja.clase, caja.texto])
        for flecha in self.flechas:
            filas.append(["F", flecha.desde, flecha.hasta, flecha.rotulo])
        return "\n".join("\t".join(celda.replace("\t", " ") for celda in fila)
                         for fila in filas)


def es_esquema(crudo: str) -> bool:
    """Dice si lo guardado en disco es un diagrama y no la tabla de un gráfico."""
    return bool(crudo) and str(crudo).split("\t", 1)[0].strip() == MARCA


def desde_guardado(crudo: str):
    """Reconstruye el diagrama tal y como se guardó."""
    if not es_esquema(crudo):
        return None
    cajas, flechas, tipo = [], [], ""
    for numero, linea in enumerate(str(crudo).split("\n")):
        partes = linea.split("\t")
        if numero == 0:
            tipo = partes[1] if len(partes) > 1 else ""
            continue
        if partes[0] == "C" and len(partes) >= 4:
            cajas.append(Caja(partes[1], partes[2], partes[3]))
        elif partes[0] == "F" and len(partes) >= 3:
            flechas.append(Flecha(partes[1], partes[2],
                                  partes[3] if len(partes) > 3 else ""))
    esquema = Esquema(tipo=tipo, cajas=cajas, flechas=flechas)
    return esquema or None


# ---------------------------------------------------------------------------
# Interpretar lo que responde la IA
# ---------------------------------------------------------------------------

def interpretar(respuesta: str):
    """Convierte la respuesta de la IA en un :class:`Esquema`, o ``None``.

    Se devuelve ``None`` tanto si la IA dice que no es un diagrama como si lo
    que ha respondido no tiene cajas: un diagrama sin cajas no es un diagrama a
    medias, es nada.
    """
    if not respuesta:
        return None
    if SIN_ESTRUCTURA in _sin_tildes(respuesta):
        return None

    titulo = tipo = nota = fiabilidad = por_que = ""
    cajas: list[Caja] = []
    flechas: list[Flecha] = []
    dentro = ""
    for linea in str(respuesta).splitlines():
        marca = _rotulo_de(linea)
        if marca is not None:
            clave, resto = marca
            if clave == "titulo":
                titulo, dentro = _sin_relleno(resto), ""
            elif clave == "tipo":
                tipo, dentro = _sin_relleno(resto), ""
            elif clave == "nota":
                nota, dentro = _sin_relleno(resto), ""
            elif clave == "fiabilidad":
                fiabilidad, por_que = _fiabilidad_de(resto)
                dentro = ""
            else:
                dentro = clave
            continue
        if not dentro:
            continue
        celdas = _celdas(linea)
        if celdas is None:
            continue
        if dentro == "cajas" and len(cajas) < MAXIMAS_CAJAS:
            caja = _caja_de(celdas)
            if caja is not None:
                cajas.append(caja)
        elif dentro == "flechas" and len(flechas) < MAXIMAS_FLECHAS:
            flecha = _flecha_de(celdas)
            if flecha is not None:
                flechas.append(flecha)

    if not cajas:
        return None
    conocidas = {caja.identificador for caja in cajas}
    # Una flecha que sale o llega a una caja que no existe no se puede seguir,
    # y dejarla dibujaría un camino a ninguna parte.
    flechas = [flecha for flecha in flechas
               if flecha.desde in conocidas and flecha.hasta in conocidas]
    return Esquema(titulo, tipo, cajas, flechas, nota, fiabilidad, por_que)


def _caja_de(celdas):
    """Una fila de la tabla de cajas."""
    if len(celdas) < 2:
        return None
    identificador = celdas[0].strip()
    if not identificador or _sin_tildes(identificador) in ("id", "numero"):
        return None
    if len(celdas) == 2:
        return Caja(identificador, "paso", celdas[1])
    clase = _sin_tildes(celdas[1]).strip()
    if clase not in CLASES:
        clase = "paso"
    return Caja(identificador, clase, celdas[2])


def _flecha_de(celdas):
    """Una fila de la tabla de flechas."""
    if len(celdas) < 2:
        return None
    desde, hasta = celdas[0].strip(), celdas[1].strip()
    if not desde or not hasta:
        return None
    if _sin_tildes(desde) == "desde":
        return None
    return Flecha(desde, hasta, celdas[2].strip() if len(celdas) > 2 else "")


def _sin_relleno(texto: str) -> str:
    """Quita los «no consta» y los «ninguna» con los que responde la IA."""
    limpio = (texto or "").strip().strip("*")
    if _sin_tildes(limpio) in ("no consta", "ninguna", "ninguno", "n/a", "-"):
        return ""
    return limpio


def _fiabilidad_de(resto: str) -> tuple[str, str]:
    """Saca el nivel de fiabilidad y el porqué de la línea correspondiente."""
    crudo = (resto or "").strip().strip("*")
    nivel, por_que = "", crudo
    if ":" in crudo:
        cabeza, cola = crudo.split(":", 1)
        nivel, por_que = _sin_tildes(cabeza.strip()), cola.strip()
    else:
        nivel = _sin_tildes(crudo.split()[0]) if crudo.split() else ""
        por_que = " ".join(crudo.split()[1:])
    if nivel not in ("alta", "media", "baja"):
        nivel = ""
    return nivel, por_que
