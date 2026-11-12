# -*- coding: utf-8 -*-
"""Partituras en MusicXML, leídas y escritas en musicografía braille.

MusicXML es el formato en el que se intercambian partituras entre todos los
editores —Finale, Sibelius, MuseScore, Dorico— y en el que están publicadas
casi todas las que se pueden descargar. Hasta ahora era un archivo que el
programa no abría.

Lo que sale al abrirlo **no es la partitura dibujada**: es la partitura leída.
Cada compás se convierte en dos cosas, y las dos hacen falta:

- **Una frase que se puede escuchar**: «compás 3: do negra, re corchea, mi
  corchea con puntillo». Es lo que permite hacerse una idea sin tocar nada, y lo
  que sirve para repasar de camino a clase.
- **La musicografía braille de ese compás**, en signos braille de Unicode. En
  una línea braille se lee con los dedos, tal cual, y al exportar el documento a
  BRF sale una partitura braille de verdad
  (:mod:`nucleo.braille_musica`).

**Qué se lee y qué no.** Una voz por pentagrama, con sus notas, silencios,
alteraciones, puntillos y ligaduras. Los acordes se dicen en palabras —«acorde
de tres notas»— y no se transcriben, porque su signografía tiene reglas propias
que no están cubiertas y una transcripción a medias no se detecta leyéndola.

Un ``.mxl`` es el mismo XML dentro de un ZIP, así que se abre igual.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from lxml import etree

from nucleo import braille_musica
from nucleo.braille_musica import Nota
from nucleo.documento import Metadatos
from nucleo.idioma import _
from nucleo.idioma import _n
from nucleo.registro import obtener_registro, registrar_excepcion

from .base import Analizador, ErrorFormato, OpcionesAnalisis, registrar
from .ensamblador import escapar, montar
from .lectura_xml import crear_parser_xml

log = obtener_registro(__name__)

#: Cuántos compases se leen como mucho. Una partitura de orquesta de mil
#: compases por doce instrumentos no es un documento que nadie recorra de oído.
MAXIMOS_COMPASES = 2000


def _texto(elemento, camino: str, por_omision: str = "") -> str:
    """El texto de un hijo, o lo que se diga si no está."""
    if elemento is None:
        return por_omision
    hijo = elemento.find(camino)
    if hijo is None or hijo.text is None:
        return por_omision
    return hijo.text.strip()


def _entero(elemento, camino: str, por_omision: int = 0) -> int:
    try:
        return int(_texto(elemento, camino, str(por_omision)))
    except ValueError:
        return por_omision


class Pentagrama:
    """Una parte de la partitura: su nombre y sus compases."""

    __slots__ = ("nombre", "compases", "armadura", "compasillo", "avisos",
                 "hacia_abajo")

    def __init__(self, nombre: str) -> None:
        self.nombre = nombre
        #: Lista de compases; cada uno, una lista de :class:`Nota`.
        self.compases: list[list[Nota]] = []
        self.armadura = 0
        self.compasillo: tuple[int, int] | None = None
        #: Si los acordes se escriben de arriba abajo.  Lo decide la clave: los
        #: instrumentos agudos y la mano derecha se escriben de arriba abajo;
        #: los graves y la mano izquierda, al revés.  No es presentación: decide
        #: cuál es la nota que se escribe entera y desde dónde se miden los
        #: intervalos, así que un acorde escrito al revés dice otra cosa.
        self.hacia_abajo = True
        #: Lo que se ha encontrado y no se transcribe, por compás.
        self.avisos: dict[int, list[str]] = {}


def leer(raiz) -> tuple[list[Pentagrama], Metadatos]:
    """Saca de un MusicXML sus partes, sus compases y sus datos."""
    metadatos = Metadatos()
    metadatos.titulo = _texto(raiz, ".//work/work-title") or ""
    if not metadatos.titulo:
        metadatos.titulo = _texto(raiz, ".//movement-title") or ""
    for creador in raiz.findall(".//identification/creator"):
        if (creador.get("type") or "").lower() in ("composer", "") and creador.text:
            metadatos.autor = creador.text.strip()
            break

    nombres: dict[str, str] = {}
    for parte in raiz.findall(".//part-list/score-part"):
        nombres[parte.get("id", "")] = _texto(parte, "part-name") or _("Parte")

    pentagramas = []
    for parte in raiz.findall(".//part"):
        identificador = parte.get("id", "")
        pentagrama = Pentagrama(nombres.get(identificador, _("Parte")))
        _leer_parte(parte, pentagrama)
        if pentagrama.compases:
            pentagramas.append(pentagrama)
    return pentagramas, metadatos


def _leer_parte(parte, pentagrama: Pentagrama) -> None:
    """Recorre los compases de una parte y los convierte en notas."""
    for numero, compas in enumerate(parte.findall("measure"), start=1):
        if numero > MAXIMOS_COMPASES:
            log.info("La partitura se corta en %d compases", MAXIMOS_COMPASES)
            break
        atributos = compas.find("attributes")
        if atributos is not None:
            if atributos.find("key") is not None:
                pentagrama.armadura = _entero(atributos, "key/fifths", 0)
            tiempo = atributos.find("time")
            if tiempo is not None:
                arriba = _entero(tiempo, "beats", 4)
                abajo = _entero(tiempo, "beat-type", 4)
                if pentagrama.compasillo is None:
                    pentagrama.compasillo = (arriba, abajo)
            clave = _texto(atributos, "clef/sign").upper()
            if clave:
                # En clave de fa el acorde se escribe de abajo arriba, que es lo
                # que hace la mano izquierda del teclado y los instrumentos
                # graves.
                pentagrama.hacia_abajo = clave != "F"

        voces, avisos = _leer_voces(compas, pentagrama.hacia_abajo)
        if voces:
            # Con una sola voz se guarda la lista de elementos tal cual: así el
            # caso normal --que es casi todo-- sigue siendo exactamente lo que
            # era, y solo las partituras a dos voces estrenan el camino nuevo.
            pentagrama.compases.append(voces[0] if len(voces) == 1 else voces)
            if avisos:
                pentagrama.avisos[len(pentagrama.compases)] = avisos


def _leer_voces(compas, hacia_abajo: bool):
    """Reparte las notas de un compás en sus voces, armando los acordes.

    MusicXML pone las notas de un acorde **seguidas**, marcando con ``<chord/>``
    las que se apilan sobre la anterior; y numera las voces con ``<voice>``.
    Aquí se deshacen las dos cosas: cada voz queda con su lista de notas y
    acordes, en el orden en que suenan.
    """
    por_voz: dict[str, list] = {}
    orden: list[str] = []
    avisos: list[str] = []
    ultima_voz = "1"
    ligados: list = []
    #: Lo que se ha leído en un ``<direction>`` y todavía no tiene nota a la que
    #: pegarse. En MusicXML una indicación va suelta entre las notas, y en
    #: braille tiene que ir delante de la nota a la que afecta.
    pendientes: list[str] = []
    abiertos: list[str] = []
    for nodo in compas:
        etiqueta = etree.QName(nodo).localname
        if etiqueta == "direction":
            pendientes.extend(_palabras_de(nodo))
            for cual in _reguladores_de(nodo):
                if cual == "cierra":
                    ultimo = abiertos.pop() if abiertos else "crescendo"
                    pendientes.append("regulador:fin-%s" % ultimo)
                else:
                    abiertos.append(cual)
                    pendientes.append("regulador:%s" % cual)
            continue
        if etiqueta != "note":
            continue
        if (any(etree.QName(hijo).localname in SIN_ESCRIBIR
                for grupo in nodo.findall("notations/ornaments")
                for hijo in grupo) and "ornamento" not in avisos):
            avisos.append("ornamento")
        de_acorde = nodo.find("chord") is not None
        voz = (_texto(nodo, "voice") or ultima_voz) if not de_acorde else ultima_voz
        nota = _leer_nota(nodo)
        if nota is None:
            continue
        ultima_voz = voz
        if voz not in por_voz:
            por_voz[voz] = []
            orden.append(voz)
        if pendientes and not de_acorde:
            nota.palabras = tuple(t for t in pendientes
                                  if not t.startswith("regulador:"))
            nota.reguladores = tuple(t.split(":", 1)[1] for t in pendientes
                                     if t.startswith("regulador:"))
            pendientes = []
        lista = por_voz[voz]
        if de_acorde and lista and not nota.es_silencio:
            apilada = _apilar(lista[-1], nota, hacia_abajo)
            if apilada is not None:
                lista[-1] = apilada
                continue
        lista.append(nota)
        if not nota.es_silencio:
            ligados.append((nota, _ligado_de(nodo)))
    _marcar_ligados(ligados)
    return [por_voz[voz] for voz in orden if por_voz[voz]], avisos


def _ligado_de(nodo) -> str:
    """Si en esta nota empieza o acaba una ligadura de expresión."""
    for atadura in nodo.findall("notations/slur"):
        clase = (atadura.get("type") or "").lower()
        if clase in ("start", "stop"):
            return clase
    return ""


def _apilar(anterior, nota: Nota, hacia_abajo: bool):
    """Añade una nota al acorde que se está formando.

    Si lo de antes era una nota suelta se convierte en acorde; si ya era un
    acorde, se le suma una nota más.
    """
    if isinstance(anterior, braille_musica.Acorde):
        return braille_musica.Acorde(list(anterior.notas) + [nota], hacia_abajo)
    if getattr(anterior, "es_silencio", False):
        # Un silencio no se apila con nada. Devolver None hace que la nota se
        # escriba detrás, suelta: perderla por venir mal marcada sería quitar
        # una nota de la partitura sin decirlo.
        return None
    return braille_musica.Acorde([anterior, nota], hacia_abajo)


#: Adornos que MusicXML sabe nombrar y que **aquí no se escriben**: sus signos
#: no están en la tabla del manual internacional o tienen reglas de colocación
#: propias. Se dicen en palabras y se avisa, en vez de escribir algo que parezca
#: un trino y no lo sea.
SIN_ESCRIBIR = ("tremolo", "schleifer", "wavy-line", "vertical-turn",
                "inverted-vertical-turn", "shake", "haydn")


def _articulaciones_de(nodo) -> tuple:
    """Las articulaciones de una nota, de las que sí se saben escribir."""
    from nucleo.braille_musica import ARTICULACIONES

    salida = []
    for grupo in nodo.findall("notations/articulations"):
        for hijo in grupo:
            nombre = etree.QName(hijo).localname
            if nombre in ARTICULACIONES and nombre not in salida:
                salida.append(nombre)
    return tuple(salida)


def _adornos_de(nodo) -> tuple:
    """Los adornos de una nota, de los que sí se saben escribir."""
    from nucleo.braille_musica import ADORNOS

    salida = []
    for grupo in nodo.findall("notations/ornaments"):
        for hijo in grupo:
            nombre = etree.QName(hijo).localname
            if nombre in ADORNOS and nombre not in salida:
                salida.append(nombre)
    return tuple(salida)


def _apoyatura_de(nodo) -> str:
    """Si esta nota es una nota de adorno, y de cuál de las dos clases.

    En MusicXML una apoyatura no es un adorno: es **una nota de verdad** marcada
    con ``<grace/>``. La que lleva la rayita cruzada —``slash="yes"``— es la
    corta, la acciaccatura; la otra es la apoyatura larga. En braille se
    distinguen por su signo, así que la diferencia hay que conservarla.
    """
    adorno = nodo.find("grace")
    if adorno is None:
        return ""
    return "corta" if (adorno.get("slash") or "").lower() == "yes" else "larga"


def _dedo_de(nodo) -> int:
    """Con qué dedo se pulsa, si la partitura lo dice."""
    for tecnica in nodo.findall("notations/technical/fingering"):
        crudo = (tecnica.text or "").strip()
        if crudo.isdigit() and 1 <= int(crudo) <= 5:
            return int(crudo)
    return 0


def _leer_nota(nodo) -> Nota | None:
    """Convierte un ``<note>`` de MusicXML en una :class:`Nota`."""
    figura = _texto(nodo, "type") or "quarter"
    puntillos = len(nodo.findall("dot"))
    if nodo.find("rest") is not None:
        return Nota(figura=figura, puntillos=puntillos, es_silencio=True)
    altura = nodo.find("pitch")
    if altura is None:
        return None
    grado = _texto(altura, "step").upper()
    octava = _entero(altura, "octave", 4)
    alteracion = _entero(altura, "alter", 0)
    ligada = any((atadura.get("type") or "") == "start"
                 for atadura in nodo.findall("tie"))
    return Nota(grado, octava, figura, alteracion, puntillos, ligada,
                articulaciones=_articulaciones_de(nodo), dedo=_dedo_de(nodo),
                adornos=_adornos_de(nodo), apoyatura=_apoyatura_de(nodo))


def _palabras_de(direccion) -> tuple:
    """Los matices y los textos de una indicación: «p», «a tempo»…"""
    salida = []
    for tipo in direccion.findall("direction-type"):
        for hijo in tipo:
            nombre = etree.QName(hijo).localname
            if nombre == "dynamics":
                for matiz in hijo:
                    salida.append(etree.QName(matiz).localname)
            elif nombre in ("words", "rehearsal"):
                crudo = " ".join((hijo.text or "").split())
                if crudo:
                    salida.append(crudo)
    return tuple(salida)


def _reguladores_de(direccion) -> tuple:
    """Las aperturas y los cierres de crescendo y de diminuendo."""
    salida = []
    for cuna in direccion.findall("direction-type/wedge"):
        clase = (cuna.get("type") or "").lower()
        if clase == "crescendo":
            salida.append("crescendo")
        elif clase == "diminuendo":
            salida.append("diminuendo")
        elif clase == "stop":
            # MusicXML no dice de cuál se cierra, así que se cierra el que
            # estuviera abierto; lo resuelve quien recorre el compás.
            salida.append("cierra")
    return tuple(salida)


def _marcar_ligados(elementos) -> None:
    """Reparte las ligaduras de expresión por las notas que abarcan.

    MusicXML dice dónde empieza y dónde acaba; la musicografía necesita otra
    cosa: el signo va **entre** cada dos notas del grupo, y si el grupo pasa de
    cuatro notas se escribe de otra manera —doble delante de la primera y otro
    detrás de la última—. Así que hay que contar cuántas abarca.
    """
    from nucleo.braille_musica import LIGADURA_LARGA_DESDE

    dentro = []
    for elemento, ligado in elementos:
        if ligado == "start" or (dentro and ligado != "stop"):
            dentro.append(elemento)
            continue
        if ligado == "stop":
            dentro.append(elemento)
            _aplicar_ligado(dentro, LIGADURA_LARGA_DESDE)
            dentro = []
    if len(dentro) > 1:
        _aplicar_ligado(dentro, LIGADURA_LARGA_DESDE)


def _aplicar_ligado(grupo, desde: int) -> None:
    """Marca un grupo de notas ligadas, corto o largo."""
    if len(grupo) < 2:
        return
    principales = [_principal(elemento) for elemento in grupo]
    if len(grupo) >= desde:
        principales[0].ligado = "abre-larga"
        principales[-1].ligado = "cierra-larga"
        return
    for nota in principales[:-1]:
        nota.ligado = "sigue"


def _principal(elemento):
    """La nota que representa a un elemento, sea nota suelta o acorde."""
    return getattr(elemento, "principal", elemento)


def _decir(elementos) -> str:
    """Lo que suena en una voz, dicho en palabras."""
    return ", ".join(elemento.nombre() for elemento in elementos)


def _compas_a_html(numero: int, contenido, celdas_braille: str, avisos) -> str:
    """Un compás: lo que se dice y lo que se lee con los dedos."""
    partes = []
    if contenido and all(isinstance(voz, (list, tuple)) for voz in contenido):
        # Un compás a dos voces se dice voz por voz y no todo seguido: de
        # corrido serían dos melodías mezcladas y no se entendería ninguna.
        partes.append("<p>%s</p>" % escapar(
            _("Compás %(numero)d, %(cuantas)d voces:")
            % {"numero": numero, "cuantas": len(contenido)}))
        for indice, voz in enumerate(contenido, start=1):
            partes.append("<p>%s</p>" % escapar(
                _("Voz %(numero)d: %(notas)s.")
                % {"numero": indice, "notas": _decir(voz)}))
    else:
        partes.append("<p>%s</p>" % escapar(
            _("Compás %(numero)d: %(notas)s.")
            % {"numero": numero, "notas": _decir(contenido)}))
    if avisos:
        if any(a == "ornamento" for a in avisos):
            partes.append("<p>%s</p>" % escapar(
                _("En este compás hay adornos que no se escriben en braille "
                  "—un trémolo, un arpegio entre pentagramas—: sus signos no "
                  "están cubiertos y se dicen en palabras.")))
    if celdas_braille:
        partes.append("<pre>%s</pre>" % escapar(celdas_braille))
    return "".join(partes)


class AnalizadorMusicXML(Analizador):
    """Partituras en MusicXML, comprimidas o no."""

    extensiones = (".musicxml", ".mxl")
    descripcion = _("Partituras MusicXML")

    def analizar(self, ruta, opciones: OpcionesAnalisis):
        camino = Path(ruta)
        datos = self._contenido(camino)
        try:
            raiz = etree.fromstring(datos, parser=crear_parser_xml())
        except Exception as error:
            raise ErrorFormato(
                _("El archivo no es una partitura MusicXML válida: %s") % error)
        if raiz is None:
            raise ErrorFormato(_("El archivo no es una partitura MusicXML válida."))

        pentagramas, metadatos = leer(raiz)
        if not pentagramas:
            raise ErrorFormato(_("La partitura no tiene ninguna nota."))
        metadatos.titulo = metadatos.titulo or camino.stem

        secciones = []
        total = len(pentagramas)
        for numero, pentagrama in enumerate(pentagramas, start=1):
            opciones.progreso.paso(numero - 1, total,
                                   _("Leyendo: %s") % pentagrama.nombre)
            secciones.append(("parte%d" % numero,
                              self._parte_a_xhtml(pentagrama)))
        return montar(secciones, metadatos, camino, opciones)

    @staticmethod
    def _contenido(camino: Path) -> bytes:
        """Los bytes del XML, saliendo del ZIP si es un ``.mxl``."""
        try:
            if zipfile.is_zipfile(str(camino)):
                with zipfile.ZipFile(str(camino)) as archivo:
                    # El contenedor dice cuál es el archivo bueno; si no está,
                    # se coge el primer XML que no sea el propio contenedor.
                    nombres = archivo.namelist()
                    elegido = ""
                    if "META-INF/container.xml" in nombres:
                        try:
                            envoltorio = etree.fromstring(
                                archivo.read("META-INF/container.xml"),
                                parser=crear_parser_xml())
                            for recurso in envoltorio.iter():
                                camino_interno = recurso.get("full-path")
                                if camino_interno:
                                    elegido = camino_interno
                                    break
                        except Exception:
                            elegido = ""
                    if not elegido or elegido not in nombres:
                        candidatos = [n for n in nombres
                                      if n.lower().endswith((".xml", ".musicxml"))
                                      and not n.startswith("META-INF/")]
                        if not candidatos:
                            raise ErrorFormato(
                                _("El archivo comprimido no lleva ninguna partitura."))
                        elegido = candidatos[0]
                    return archivo.read(elegido)
            return camino.read_bytes()
        except ErrorFormato:
            raise
        except (OSError, KeyError, zipfile.BadZipFile) as error:
            raise ErrorFormato(_("El archivo no se puede abrir: %s") % error)

    @staticmethod
    def _parte_a_xhtml(pentagrama: Pentagrama) -> bytes:
        """Monta el XHTML de una parte: su cabecera y sus compases."""
        partes = ["<h1>%s</h1>" % escapar(pentagrama.nombre)]

        datos = []
        if pentagrama.compasillo:
            datos.append(_("Compás de %(arriba)d por %(abajo)d")
                         % {"arriba": pentagrama.compasillo[0],
                            "abajo": pentagrama.compasillo[1]})
        if pentagrama.armadura:
            cuantas = abs(pentagrama.armadura)
            datos.append(
                _n("%d sostenido", "%d sostenidos", cuantas) % cuantas
                if pentagrama.armadura > 0 else
                _n("%d bemol", "%d bemoles", cuantas) % cuantas)
        datos.append(_n("%d compás", "%d compases", len(pentagrama.compases))
                     % len(pentagrama.compases))
        partes.append("<p>%s</p>" % escapar(". ".join(datos) + "."))

        cabecera = []
        cabecera.extend(braille_musica.celdas_de_armadura(pentagrama.armadura))
        if pentagrama.compasillo:
            cabecera.extend(braille_musica.celdas_de_compasillo(
                pentagrama.compasillo[0], pentagrama.compasillo[1]))
        if cabecera:
            partes.append("<p>%s</p>" % escapar(
                _("Armadura y compás en braille:")))
            partes.append("<pre>%s</pre>"
                          % escapar(braille_musica.a_unicode(cabecera)))

        anterior = None
        for numero, compas in enumerate(pentagrama.compases, start=1):
            try:
                celdas, anterior = braille_musica.celdas_de_compas(compas, anterior)
                braille = braille_musica.a_unicode(celdas)
            except braille_musica.Imposible as motivo:
                log.debug("Compás %d no transcrito: %s", numero, motivo)
                braille = ""
            except Exception as error:               # pragma: no cover
                registrar_excepcion(log, "Compás %d ilegible" % numero, error)
                braille = ""
            partes.append(_compas_a_html(numero, compas, braille,
                                         pentagrama.avisos.get(numero)))
        return ("<?xml version=\"1.0\" encoding=\"utf-8\"?>"
                "<html xmlns=\"http://www.w3.org/1999/xhtml\"><head>"
                "<meta charset=\"utf-8\"/></head><body>%s</body></html>"
                % "".join(partes)).encode("utf-8")


registrar(AnalizadorMusicXML())
