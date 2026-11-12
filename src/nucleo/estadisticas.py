# -*- coding: utf-8 -*-
"""Cuánto se ha leído de un documento, a qué ritmo y cuánto queda.

Saber que a este ritmo quedan dos horas cambia cómo se organiza uno la tarde, y
ver que un libro que parecía interminable va por el sesenta por ciento anima a
seguir.  Es barato de calcular y sale gratis: el programa ya sabe dónde está el
cursor y cuánto ocupa el documento.

Lo único que tiene miga es **medir el tiempo de verdad**.  Contar desde que se
abre el documento hasta que se cierra daría cifras absurdas: quien deja el
programa abierto toda la noche no ha leído toda la noche.  Aquí el tiempo se
cuenta a trozos, entre señales de que se está leyendo —el cursor que se mueve,
la voz que pasa de frase—, y **un hueco largo entre dos señales no se cuenta**:
si pasan más de :data:`LIMITE_PAUSA` sin nada, ese rato se da por no leído.

El ritmo se mide en caracteres, no en palabras: contar palabras obligaría a
recorrer el texto y el número no sería más exacto.  Al enseñarlo se convierte a
palabras con una media, y se dice que es aproximado.
"""

from __future__ import annotations

import time
import math
from dataclasses import dataclass

from .idioma import _, _n

#: Segundos sin ninguna señal a partir de los cuales se da por hecho que no se
#: está leyendo.  Dos minutos: caben de sobra una pausa para pensar, un párrafo
#: releído despacio o una interrupción corta, y no cabe irse a cenar.
LIMITE_PAUSA = 120.0

#: Caracteres por palabra que se usan al convertir el ritmo a palabras por
#: minuto.  Cinco más el espacio, que es la medida clásica y vale para el
#: español y el inglés por igual.
LETRAS_POR_PALABRA = 6.0

# Filtro conservador de navegación, no un límite fisiológico de lectura.
MAXIMO_CARACTERES_SEGUNDO = 120.0  # 1.200 palabras aproximadas por minuto.


@dataclass
class Cronometro:
    """Lleva la cuenta del tiempo leído y de lo que se ha avanzado.

    Se guarda con el documento, así que la cuenta continúa de una sesión a otra.

    :param segundos: Tiempo leído acumulado.
    :param caracteres: Caracteres recorridos hacia delante.
    """

    segundos: float = 0.0
    caracteres: int = 0

    def __post_init__(self) -> None:
        #: Momento de la última señal.  Se guarda ``None`` y no cero cuando no
        #: hay ninguna: el reloj puede valer cero perfectamente, y comprobarlo
        #: por «si es verdadero» hacía que el primer intervalo no se contara.
        self._ultima_senal: float | None = None
        self._ultima_posicion = -1
        self._segundos_anteriores = 0.0

    # -- medida ---------------------------------------------------------------

    def latido(self, posicion: int, salto: bool = False) -> None:
        """Señal de que se está leyendo, con la posición actual.

        La llama la ventana al moverse el cursor, también cuando sigue la voz.
        Los saltos explícitos, retrocesos, avances desproporcionados y pausas
        mayores que LIMITE_PAUSA solo actualizan la referencia. No aportan
        tiempo ni caracteres a la muestra de lectura.
        """
        ahora = time.monotonic()
        if salto:
            self._ultima_senal = ahora
            self._ultima_posicion = posicion
            return
        if self._ultima_senal is not None:
            transcurrido = ahora - self._ultima_senal
            avance = posicion - self._ultima_posicion
            if (0 < transcurrido <= LIMITE_PAUSA
                    and 0 <= avance <= transcurrido * MAXIMO_CARACTERES_SEGUNDO):
                self.segundos += transcurrido
                if self._ultima_posicion >= 0 and posicion > self._ultima_posicion:
                    # Cuenta avance aceptado, no caracteres únicos leídos.
                    self.caracteres += posicion - self._ultima_posicion
        self._ultima_senal = ahora
        self._ultima_posicion = posicion

    def soltar(self) -> None:
        """Corta la medida, al cerrar el documento o el programa."""
        self._ultima_senal = None
        self._ultima_posicion = -1

    # -- resultados ------------------------------------------------------------

    @property
    def hay_datos(self) -> bool:
        """Indica si se ha leído lo bastante como para decir algo."""
        return self.segundos - self._segundos_anteriores >= 60 and self.caracteres > 0

    def ritmo(self) -> float:
        """Caracteres por segundo, o cero si todavía no se puede decir."""
        return (self.caracteres / (self.segundos - self._segundos_anteriores)
                if self.hay_datos else 0.0)

    def palabras_por_minuto(self) -> int:
        """El ritmo en palabras por minuto, que es como se entiende."""
        return int(self.ritmo() * 60 / LETRAS_POR_PALABRA)

    def queda(self, restantes: int) -> float:
        """Segundos que faltarían para terminar, a este ritmo.

        :param restantes: Caracteres que quedan por leer.
        """
        velocidad = self.ritmo()
        return restantes / velocidad if velocidad > 0 else 0.0

    # -- guardado ---------------------------------------------------------------

    def como_dict(self) -> dict:
        """Representación para guardar en JSON."""
        return {"segundos": self.segundos, "caracteres": self.caracteres,
                "segundos_ritmo": self.segundos - self._segundos_anteriores}

    @classmethod
    def desde_dict(cls, datos) -> "Cronometro":
        """Reconstruye el cronómetro a partir del JSON."""
        if not isinstance(datos, dict):
            return cls()
        try:
            segundos = float(datos.get("segundos", 0) or 0)
            caracteres = int(datos.get("caracteres", 0) or 0)
            if not math.isfinite(segundos) or segundos < 0 or caracteres < 0:
                return cls()
            # No reutilizar medias antiguas disparadas por saltos. Conservar
            # el tiempo de actividad, pero empezar de nuevo la muestra de ritmo.
            muestra_segundos = float(datos.get("segundos_ritmo", segundos) or 0)
            if (not math.isfinite(muestra_segundos) or not 0 <= muestra_segundos <= segundos
                    or caracteres > muestra_segundos * MAXIMO_CARACTERES_SEGUNDO):
                caracteres, muestra_segundos = 0, 0.0
            resultado = cls(segundos=segundos, caracteres=caracteres)
            resultado._segundos_anteriores = segundos - muestra_segundos
            return resultado
        except (TypeError, ValueError, OverflowError):
            return cls()


def duracion(segundos: float) -> str:
    """Convierte una duración en algo que se entienda al oírlo.

    Nada de «02:47:13»: leído en voz alta, eso son once números seguidos.  Se
    dice con palabras y se redondea, porque en un dato así los segundos no le
    importan a nadie.
    """
    segundos = max(0, int(segundos))
    if segundos < 60:
        return _("menos de un minuto")
    minutos = segundos // 60
    if minutos < 60:
        return _n("%d minuto", "%d minutos", minutos) % minutos
    horas, resto = divmod(minutos, 60)
    horas_dichas = _n("%d hora", "%d horas", horas) % horas
    if not resto:
        return horas_dichas
    return _("%(horas)s y %(minutos)s") % {
        "horas": horas_dichas,
        "minutos": _n("%d minuto", "%d minutos", resto) % resto}


#: Ritmo que se supone mientras no haya medido ninguno: mil caracteres por
#: minuto, que son unas 170 palabras por minuto.  Es el ritmo de una lectura
#: tranquila y sirve para dar una respuesta desde el primer minuto, en lugar de
#: contestar «todavía no lo sé», que es lo que menos ayuda.
RITMO_SUPUESTO = 1000 / 60


def _ritmo_util(crono: Cronometro) -> tuple[float, bool]:
    """Devuelve ``(caracteres por segundo, si está medido de verdad)``."""
    medido = crono.ritmo()
    if medido > 0:
        return medido, True
    return RITMO_SUPUESTO, False


def cuanto_queda(crono: Cronometro, documento, posicion: int) -> str:
    """Frase con lo que falta para acabar el capítulo y el libro.

    Es de esas cosas pequeñas que se echan mucho de menos: con la vista, el
    grosor de lo que queda se ve de un vistazo, y de oído no hay forma de
    saberlo.  Se dice en minutos, que es la unidad en la que se decide si da
    tiempo a terminar el capítulo antes de bajarse del autobús.

    Cuando todavía no se ha leído lo bastante como para medir el ritmo propio
    se usa uno supuesto y **se dice que es supuesto**, en vez de callarse: un
    número aproximado sirve, y un «no lo sé» no sirve de nada.
    """
    from . import html_elementos

    texto = getattr(documento, "texto", "") or ""
    total = len(texto)
    if not total:
        return _("No hay ningún documento abierto.")
    posicion = max(0, min(int(posicion), total))
    ritmo, medido = _ritmo_util(crono)

    partes = []
    inicio, fin, titulo = html_elementos.limites_del_capitulo(documento, posicion)
    if fin - inicio < total:
        restante = max(0, fin - posicion)
        if titulo:
            partes.append(_("Del capítulo «%(titulo)s» queda: %(tiempo)s.")
                          % {"titulo": titulo, "tiempo": duracion(restante / ritmo)})
        else:
            partes.append(_("De este capítulo queda: %s.") % duracion(restante / ritmo))
    if posicion == total:
        return _("Has llegado al final del documento. Posición en el documento: 100 por ciento.")
    partes.append(_("Del documento entero queda: %s.")
                  % duracion(max(0, total - posicion) / ritmo))
    porcentaje = int(posicion * 100 / total) if total else 0
    partes.append(_("Posición en el documento: %d por ciento.") % porcentaje)
    if medido:
        partes.append(_("Calculado con tu ritmo: unas %d palabras por minuto.")
                      % crono.palabras_por_minuto())
    else:
        partes.append(_("Calculado con un ritmo normal de lectura, porque todavía no se "
                        "ha medido el tuyo."))
    return " ".join(partes)


def resumen(crono: Cronometro, posicion: int, total: int) -> list[str]:
    """Líneas con las estadísticas de lectura, listas para enseñar.

    Devuelve una lista y no un texto de una pieza porque quien lo enseña las
    mete en una lista de datos junto a las demás.
    """
    lineas = []
    if crono.segundos >= 60:
        lineas.append(_("Tiempo leído: %s") % duracion(crono.segundos))
    if not crono.hay_datos:
        lineas.append(_("Ritmo de lectura: hace falta leer un rato más para saberlo."))
        return lineas

    lineas.append(_("Ritmo: unas %d palabras por minuto (aproximado)")
                  % crono.palabras_por_minuto())
    restantes = max(0, total - posicion)
    if restantes:
        # Se dice como un dato con dos puntos y no como una frase: «quedan una
        # hora» y «quedan 56 minutos» no concuerdan con el mismo verbo, y una
        # frase que a veces suena mal se nota mucho más de oído que leyéndola.
        lineas.append(_("A este ritmo, para terminar queda: %s")
                      % duracion(crono.queda(restantes)))
    else:
        lineas.append(_("Has llegado al final del documento."))
    return lineas
