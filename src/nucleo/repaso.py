# -*- coding: utf-8 -*-
"""Repasar lo marcado, con repetición espaciada.

Subrayar es la mitad del trabajo. La otra mitad —la que de verdad separa un
lector de un material de estudio— es **volver**, y volver en el momento en que
estabas a punto de olvidarlo. Eso es la repetición espaciada: lo que te sale
bien tarda cada vez más en volver a aparecer, y lo que se te resiste vuelve
mañana.

Aquí se aprovecha lo que ya hay: cada resaltado y cada nota son una tarjeta,
sin tener que escribir nada aparte. Y cada tarjeta se guarda con **cuándo toca
volver a verla**.

El método es el **SM-2**, el de toda la vida, con tres respuestas en vez de
seis: no me acordaba, me ha costado, lo sabía. Seis grados obligan a decidir
entre «casi» y «casi casi», que es una decisión que nadie sabe tomar y que
además hay que oír entera cada vez.

**Dónde se guarda lo repasado, y por qué no va con el libro.** Va en un archivo
propio (``config/repaso.json``) y no dentro de los datos de cada documento, por
dos razones: el repaso cruza libros —una tanda mezcla los seis de la
asignatura— y lo que se guarda aquí caduca, mientras que un marcador dura lo
que dure el libro. Mezclarlos haría que borrar un repaso tocara los marcadores.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from . import rutas
from .idioma import _
from .idioma import _n
from .registro import obtener_registro

log = obtener_registro(__name__)

#: Segundos que tiene un día. Los intervalos se llevan en días porque es la
#: unidad en la que se piensa al estudiar, pero se guardan en segundos.
DIA = 24 * 60 * 60

#: Facilidad de partida de una tarjeta nueva, la del método original.
FACILIDAD_INICIAL = 2.5

#: Por debajo de esto, una tarjeta se atasca: vuelve una y otra vez sin llegar
#: a espaciarse. El método lo pone justo aquí y conviene no bajarlo.
FACILIDAD_MINIMA = 1.3

#: Las tres respuestas, con la nota que le corresponde a cada una en el método.
#: Se usan tres y no seis porque decidir entre «casi» y «casi casi» no lo sabe
#: hacer nadie, y de oído hay que escuchar las seis cada vez.
RESPUESTAS = (("no", 0), ("regular", 3), ("si", 5))

#: Cuántas tarjetas trae una tanda como mucho. Media hora de repaso son unas
#: treinta; una lista de doscientas se abandona a la quinta.
TANDA = 30


def nombres_de_respuesta() -> list[tuple[str, str]]:
    """Las tres respuestas con su rótulo, para los botones."""
    return [("no", _("No me acordaba")),
            ("regular", _("Me ha costado")),
            ("si", _("Lo sabía"))]


class Tarjeta:
    """Lo que se sabe de una cosa marcada: cuándo toca y cómo va.

    :param clave: Qué identifica esto: la ruta del libro y dónde empieza.
    :param repeticiones: Cuántas veces seguidas ha salido bien.
    :param facilidad: Lo fácil que resulta, de 1,3 en adelante.
    :param intervalo: Días que se espera hasta la próxima vez.
    :param proximo: Cuándo toca, en segundos desde 1970.
    """

    __slots__ = ("clave", "repeticiones", "facilidad", "intervalo", "proximo",
                 "vistas")

    def __init__(self, clave: str, repeticiones: int = 0,
                 facilidad: float = FACILIDAD_INICIAL, intervalo: int = 0,
                 proximo: float = 0.0, vistas: int = 0) -> None:
        self.clave = clave
        self.repeticiones = repeticiones
        self.facilidad = facilidad
        self.intervalo = intervalo
        self.proximo = proximo
        self.vistas = vistas

    @property
    def es_nueva(self) -> bool:
        return self.vistas == 0

    def toca(self, ahora: float | None = None) -> bool:
        """Dice si esta tarjeta toca ya."""
        return self.proximo <= (time.time() if ahora is None else ahora)

    def responder(self, respuesta: str, ahora: float | None = None) -> None:
        """Apunta la respuesta y calcula cuándo vuelve.

        Cuando no te acordabas, la tarjeta **vuelve a empezar**: mañana otra
        vez. No basta con acortar el plazo, porque lo que no se recuerda no se
        ha aprendido a medias, no se ha aprendido.
        """
        nota = dict(RESPUESTAS).get(respuesta, 0)
        momento = time.time() if ahora is None else ahora
        self.vistas += 1
        if nota < 3:
            self.repeticiones = 0
            self.intervalo = 1
        else:
            self.repeticiones += 1
            if self.repeticiones == 1:
                self.intervalo = 1
            elif self.repeticiones == 2:
                self.intervalo = 6
            else:
                self.intervalo = max(1, int(round(self.intervalo * self.facilidad)))
        self.facilidad = max(
            FACILIDAD_MINIMA,
            self.facilidad + (0.1 - (5 - nota) * (0.08 + (5 - nota) * 0.02)))
        self.proximo = momento + self.intervalo * DIA

    def cuando(self) -> str:
        """Cuándo vuelve, dicho como se dice."""
        if self.es_nueva:
            return _("sin empezar")
        faltan = int((self.proximo - time.time()) / DIA)
        if faltan <= 0:
            return _("hoy")
        if faltan == 1:
            return _("mañana")
        return _n("dentro de %d día", "dentro de %d días", faltan) % faltan

    def como_dict(self) -> dict:
        return {"repeticiones": self.repeticiones,
                "facilidad": round(self.facilidad, 3),
                "intervalo": self.intervalo,
                "proximo": round(self.proximo, 1),
                "vistas": self.vistas}

    @classmethod
    def desde_dict(cls, clave: str, datos: dict) -> "Tarjeta":
        return cls(clave,
                   int(datos.get("repeticiones", 0)),
                   float(datos.get("facilidad", FACILIDAD_INICIAL)),
                   int(datos.get("intervalo", 0)),
                   float(datos.get("proximo", 0)),
                   int(datos.get("vistas", 0)))


def clave_de(ruta: str, inicio: int) -> str:
    """Cómo se identifica una cosa marcada entre repasos."""
    return "%s|%d" % (ruta, inicio)


def ruta_guardado() -> Path:
    """Dónde se guarda lo repasado."""
    return rutas.subcarpeta("config") / "repaso.json"


class Repaso:
    """Todo lo que se sabe de lo repasado, y con qué se arma una tanda."""

    __slots__ = ("tarjetas",)

    def __init__(self, tarjetas=None) -> None:
        self.tarjetas: dict[str, Tarjeta] = dict(tarjetas or {})

    def de(self, clave: str) -> Tarjeta:
        """La tarjeta de algo marcado, creándola si es la primera vez."""
        tarjeta = self.tarjetas.get(clave)
        if tarjeta is None:
            tarjeta = Tarjeta(clave)
            self.tarjetas[clave] = tarjeta
        return tarjeta

    def pendientes(self, apuntes, ahora: float | None = None) -> list:
        """Los apuntes que tocan hoy, en el orden en que conviene verlos.

        Primero **lo que ya se ha visto y toca**, y después lo nuevo. Al revés,
        una tanda con cincuenta tarjetas nuevas dejaría sin repasar lo que sí
        estaba a punto de olvidarse, que es justo lo que hay que salvar.
        """
        momento = time.time() if ahora is None else ahora
        vistos, nuevos = [], []
        for apunte in apuntes:
            tarjeta = self.de(clave_de(apunte.ruta, apunte.posicion))
            if tarjeta.es_nueva:
                nuevos.append(apunte)
            elif tarjeta.toca(momento):
                vistos.append(apunte)
        vistos.sort(key=lambda a: self.de(clave_de(a.ruta, a.posicion)).proximo)
        return (vistos + nuevos)[:TANDA]

    def cuenta(self, apuntes, ahora: float | None = None) -> tuple[int, int, int]:
        """``(tocan hoy, nuevas, en total)``, para poder decirlo antes."""
        momento = time.time() if ahora is None else ahora
        tocan = nuevas = 0
        for apunte in apuntes:
            tarjeta = self.de(clave_de(apunte.ruta, apunte.posicion))
            if tarjeta.es_nueva:
                nuevas += 1
            elif tarjeta.toca(momento):
                tocan += 1
        return tocan, nuevas, len(apuntes)

    def resumen(self, apuntes) -> str:
        """Frase con lo que hay para hoy."""
        tocan, nuevas, total = self.cuenta(apuntes)
        if not total:
            return _("No hay nada marcado que repasar.")
        if not tocan and not nuevas:
            return _("Hoy no toca nada. Vuelve mañana.")
        piezas = []
        if tocan:
            piezas.append(_n("%d para repasar", "%d para repasar", tocan) % tocan)
        if nuevas:
            piezas.append(_n("%d sin empezar", "%d sin empezar", nuevas) % nuevas)
        return _("Hoy: %s.") % _(" y ").join(piezas)

    # -- guardar y traer -----------------------------------------------------

    def guardar(self, destino=None) -> None:
        """Escribe lo repasado. Las tarjetas sin estrenar no se guardan."""
        ruta = Path(destino) if destino is not None else ruta_guardado()
        contenido = {clave: tarjeta.como_dict()
                     for clave, tarjeta in self.tarjetas.items()
                     if not tarjeta.es_nueva}
        temporal = ruta.with_suffix(ruta.suffix + ".tmp")
        temporal.write_text(json.dumps(contenido, ensure_ascii=False, indent=1),
                            encoding="utf-8")
        temporal.replace(ruta)

    def olvidar_libro(self, ruta_libro: str) -> int:
        """Quita lo repasado de un libro. Devuelve cuántas tarjetas se van."""
        prefijo = "%s|" % ruta_libro
        sobran = [clave for clave in self.tarjetas if clave.startswith(prefijo)]
        for clave in sobran:
            del self.tarjetas[clave]
        return len(sobran)


def cargar(origen=None) -> Repaso:
    """Trae lo repasado del disco. Si no hay archivo, empieza de cero."""
    ruta = Path(origen) if origen is not None else ruta_guardado()
    if not ruta.is_file():
        return Repaso()
    try:
        contenido = json.loads(ruta.read_text(encoding="utf-8"))
    except Exception as error:
        log.info("No se ha podido leer lo repasado: %s", error)
        return Repaso()
    return Repaso({clave: Tarjeta.desde_dict(clave, datos)
                   for clave, datos in contenido.items()
                   if isinstance(datos, dict)})
