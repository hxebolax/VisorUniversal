# -*- coding: utf-8 -*-
"""Auditoría de accesibilidad de un PDF, con las reglas comprobables por máquina.

La norma **PDF/UA** (ISO 14289-1) dice qué tiene que cumplir un PDF para que se
pueda leer sin ver.  Son unas cien reglas, y se reparten en tres grupos muy
distintos:

* Las que una máquina **puede comprobar sola**: si el archivo declara idioma, si
  las tablas marcan su fila de encabezados, si los niveles de título van
  seguidos, si las figuras traen texto alternativo.
* Las que una máquina puede comprobar **a medias**: existe un texto
  alternativo, sí, pero si dice «imagen1.png» no sirve de nada.
* Las que **solo puede juzgar una persona**: si el orden de lectura es el que
  el autor quiso, si un enlace se entiende fuera de contexto.

Este módulo hace el primer grupo y **dice claramente que solo hace ese**.  Esa
advertencia no es modestia: un informe automático que dijera «documento
accesible» sería falso y peligroso, porque quien publica se quedaría tranquilo
con un documento que no hay quien lea.  Lo que se puede afirmar es lo
contrario: cuando algo **falla** aquí, falla de verdad.

Para qué sirve
--------------

Para dos personas distintas, y por eso cada hallazgo lleva remedio:

* **Quien lee** quiere saber a qué atenerse antes de empezar: si no hay
  encabezados no merece la pena buscarlos con ``H``, y si las imágenes vienen
  sin describir, ahí está la orden de describirlas con inteligencia artificial.
* **Quien publica** quiere saber qué volver a exportar, y para eso necesita la
  cláusula de la norma, que es lo que le permite ir al texto original y lo que
  entenderá la herramienta con la que hizo el documento.

De dónde sale cada cosa
-----------------------

No se vuelve a abrir el archivo ni se recorre nada de nuevo: se auditan los
datos que el análisis ya ha reunido por su cuenta.

* Del **diagnóstico** (:mod:`formatos.pdf_diagnostico`): el catálogo, el
  idioma declarado, el título, las fuentes.
* Del **etiquetado** que recoge el analizador al leer el árbol de estructura:
  qué etiquetas PDF aparecen y cuántas figuras se han quedado sin describir.
* Del **documento ya convertido**: la secuencia real de encabezados, que es lo
  único que dice si los niveles se saltan.

Referencias a la norma
----------------------

Cada regla cita su cláusula de ISO 14289-1:2014.  Se citan las cláusulas y no
se copia su redacción: el número no cambia entre reimpresiones y es lo que
sirve para buscar.  La comprobación es propia; la norma es la referencia.
"""

from __future__ import annotations

from nucleo.idioma import _, _n
from nucleo.marcas import ENCABEZADOS, TipoMarca

from .pdf_hallazgos import (ColeccionHallazgos, Hallazgo, Severidad, aviso,
                            informativo)

#: Frase que acompaña siempre al informe.  Es la parte más importante del
#: módulo: sin ella, un informe sin fallos se leería como un certificado.
DECLARACION = _(
    "Estas comprobaciones son automáticas y parciales: detectan lo que falta, "
    "no garantizan que el documento se pueda leer bien."
)

#: Proporción del texto que el árbol de estructura tiene que cubrir para que la
#: estructura se pueda usar.  Es la misma que aplica el analizador al decidir
#: por qué camino leer el PDF, y se repite aquí para poder explicar **por qué**
#: se descartó una estructura que el archivo sí traía.
COBERTURA_MINIMA = 0.55

#: Etiquetas de estructura que la norma define (ISO 32000-1:2008, 14.8.4).  Se
#: escriben aquí enteras y no se deducen: son una lista cerrada y corta, y
#: tenerla es lo que permite distinguir la etiqueta inventada —que hay que
#: declarar a qué equivale— de la de siempre.
ETIQUETAS_NORMALIZADAS = frozenset({
    "Document", "Part", "Art", "Sect", "Div", "BlockQuote", "Caption", "TOC",
    "TOCI", "Index", "NonStruct", "Private", "P", "H", "H1", "H2", "H3", "H4",
    "H5", "H6", "L", "LI", "Lbl", "LBody", "Table", "TR", "TH", "TD", "THead",
    "TBody", "TFoot", "Span", "Quote", "Note", "Reference", "BibEntry", "Code",
    "Link", "Annot", "Ruby", "RB", "RT", "RP", "Warichu", "WT", "WP", "Figure",
    "Formula", "Form", "Artifact",
})

#: Qué puede colgar de qué, según la norma, en las tres familias donde el
#: anidamiento **importa para leer**: la tabla, la lista y el índice.  Fuera de
#: ellas la norma es mucho más abierta y comprobarlo daría falsos avisos.
#:
#: Cada entrada es «padre: hijos admitidos» (ISO 14289-1, 7.2).  ``Span`` y
#: ``Artifact`` se admiten en todas porque son envoltorios que no cambian lo
#: que el elemento es.
HIJOS_ADMITIDOS = {
    "Table": frozenset({"TR", "THead", "TBody", "TFoot", "Caption"}),
    "THead": frozenset({"TR"}),
    "TBody": frozenset({"TR"}),
    "TFoot": frozenset({"TR"}),
    "TR": frozenset({"TH", "TD"}),
    "L": frozenset({"L", "LI", "Caption"}),
    "LI": frozenset({"Lbl", "LBody"}),
    "TOC": frozenset({"TOC", "TOCI", "Caption"}),
}

#: Dónde tiene que estar cada etiqueta que solo existe dentro de otra.  Es la
#: comprobación complementaria de :data:`HIJOS_ADMITIDOS`: una dice qué puede
#: haber dentro, la otra qué no puede andar suelto (ISO 14289-1, 7.2).
PADRES_ADMITIDOS = {
    "TR": frozenset({"Table", "THead", "TBody", "TFoot"}),
    "TH": frozenset({"TR"}),
    "TD": frozenset({"TR"}),
    "LI": frozenset({"L"}),
    "LBody": frozenset({"LI"}),
    "Lbl": frozenset({"LI", "Note", "Reference", "BibEntry"}),
    "TOCI": frozenset({"TOC"}),
}

#: Envoltorios que no cuentan al juzgar el anidamiento.
TRANSPARENTES = frozenset({"Span", "Artifact", "NonStruct", "Private", "Div"})


def auditar(diagnostico=None, etiquetado=None, documento=None) -> ColeccionHallazgos:
    """Reúne todo lo que se puede comprobar solo, en un orden útil.

    Los tres argumentos son opcionales porque no siempre están: un PDF que no
    se ha podido convertir tiene diagnóstico y no tiene documento, y sin pypdf
    no hay diagnóstico.  Lo que no se puede comprobar, sencillamente no se
    comprueba: no se afirma que falte.
    """
    hallazgos = ColeccionHallazgos()
    if diagnostico is not None:
        _revisar_documento(hallazgos, diagnostico)
    if etiquetado is not None:
        _revisar_etiquetado(hallazgos, etiquetado, diagnostico)
        _revisar_anidamiento(hallazgos, dict(getattr(etiquetado, "pares", {}) or {}))
        _revisar_equivalencias(hallazgos, etiquetado, diagnostico)
    if documento is not None:
        _revisar_estructura(hallazgos, documento)
    return hallazgos


def redactar(hallazgos: ColeccionHallazgos, con_norma: bool = True) -> str:
    """Escribe el informe completo, siempre precedido de su advertencia."""
    cuerpo = hallazgos.redactar(maximo=12, minima=Severidad.INFORMACION,
                                con_norma=con_norma)
    if not cuerpo:
        return "%s %s" % (
            _("No se ha detectado ninguna carencia de las que se comprueban."),
            DECLARACION)
    return "%s\n%s" % (DECLARACION, cuerpo)


# ---------------------------------------------------------------------------
# El documento como archivo
# ---------------------------------------------------------------------------

def _revisar_documento(hallazgos: ColeccionHallazgos, diagnostico) -> None:
    """Comprueba lo que se declara en el catálogo del PDF."""
    if not getattr(diagnostico, "con_pypdf", False):
        return
    if not diagnostico.arbol_logico:
        hallazgos.anadir(Hallazgo(
            "SIN_ARBOL",
            _("El PDF no lleva estructura: no dice qué es un título, una tabla "
              "ni una imagen."),
            Severidad.ERROR,
            remedio=_("El programa deducirá la estructura de la maquetación, que "
                      "es menos fiable."),
            norma="ISO 14289-1, 7.1"))
    elif not diagnostico.marcado:
        hallazgos.anadir(aviso(
            "SIN_MARKINFO",
            _("El PDF trae estructura pero no se declara como documento "
              "etiquetado."),
            norma="ISO 14289-1, 7.1"))
    if getattr(diagnostico, "xfa_dinamico", False):
        hallazgos.anadir(Hallazgo(
            "XFA_DINAMICO",
            _("El documento es un formulario XFA din\u00e1mico, que se dibuja solo al "
              "abrirlo y no lleva texto que se pueda leer."),
            Severidad.ERROR,
            remedio=_("Solo se puede leer rellen\u00e1ndolo en Adobe Reader y guardando "
                      "una copia como PDF normal."),
            norma="ISO 14289-1, 7.15"))
    if getattr(diagnostico, "capas_conmutables", False):
        hallazgos.anadir(aviso(
            "CAPAS_CONMUTABLES",
            _("El documento tiene capas que se encienden y apagan solas, as\u00ed que "
              "lo que se lee puede no ser lo que se ve."),
            norma="ISO 14289-1, 7.10"))
    mal_codificadas = getattr(diagnostico, "fuentes_mal_codificadas", None) or ()
    if mal_codificadas:
        hallazgos.anadir(aviso(
            "FUENTES_MAL_CODIFICADAS",
            _n("%d fuente declara mal su codificaci\u00f3n, as\u00ed que su texto puede salir "
               "con las letras cambiadas.",
               "%d fuentes declaran mal su codificaci\u00f3n, as\u00ed que su texto puede salir "
               "con las letras cambiadas.",
               len(mal_codificadas)) % len(mal_codificadas),
            cantidad=len(mal_codificadas),
            norma="ISO 14289-1, 7.21.6"))
    if diagnostico.arbol_logico and not getattr(diagnostico, "con_metadatos", True):
        hallazgos.anadir(informativo(
            "SIN_METADATOS",
            _("El documento no lleva metadatos XMP, que es donde se declara lo que "
              "cumple."),
            norma="ISO 14289-1, 7.1"))
    elif diagnostico.arbol_logico and not getattr(diagnostico, "declara_pdfua", 1):
        hallazgos.anadir(informativo(
            "NO_DECLARA_PDFUA",
            _("El documento trae estructura pero no declara cumplir PDF/UA."),
            remedio=_("Se lee igual: es una declaraci\u00f3n del programa que lo cre\u00f3, "
                      "no una carencia del texto."),
            norma="ISO 14289-1, 5"))
    if diagnostico.suspects:
        hallazgos.anadir(aviso(
            "ESTRUCTURA_SOSPECHOSA",
            _("El propio archivo marca su estructura como no verificada."),
            norma="ISO 14289-1, 7.1"))
    if not diagnostico.idioma:
        hallazgos.anadir(Hallazgo(
            "SIN_IDIOMA",
            _("El documento no declara en qué idioma está."),
            Severidad.ERROR,
            remedio=_("Se leerá con la voz del idioma del programa, que puede no "
                      "ser el suyo."),
            norma="ISO 14289-1, 7.2"))
    if not diagnostico.titulo_xmp:
        hallazgos.anadir(aviso(
            "SIN_TITULO",
            _("El documento no declara un título propio en sus metadatos."),
            remedio=_("Se usará el nombre del archivo."),
            norma="ISO 14289-1, 7.1"))
    elif not diagnostico.mostrar_titulo:
        hallazgos.anadir(informativo(
            "TITULO_NO_PREFERIDO",
            _("El documento tiene título, pero pide que se muestre el nombre del "
              "archivo en su lugar."),
            norma="ISO 14289-1, 7.1"))


# ---------------------------------------------------------------------------
# El árbol de etiquetas
# ---------------------------------------------------------------------------

def _revisar_etiquetado(hallazgos: ColeccionHallazgos, etiquetado,
                        diagnostico=None) -> None:
    """Comprueba lo que se ha visto al recorrer el árbol de estructura.

    Solo tiene sentido si el árbol se ha llegado a leer.  Si el analizador lo
    descartó por incompleto, eso mismo es lo que hay que contar: el archivo
    traía estructura y no ha servido, que es un fallo distinto de no traerla.
    """
    etiquetas = dict(getattr(etiquetado, "etiquetas", {}) or {})
    if getattr(etiquetado, "desactivado", False):
        hallazgos.anadir(informativo(
            "ESTRUCTURA_DESACTIVADA",
            _("La lectura de la estructura de los PDF está desactivada en las "
              "opciones.")))
        return
    if getattr(etiquetado, "paginas_con_arbol", 0) and not getattr(etiquetado, "usar", False):
        hallazgos.anadir(Hallazgo(
            "ESTRUCTURA_INCOMPLETA",
            _("La estructura del PDF solo cubre el %d por ciento de su texto, así "
              "que se ha descartado para no perder contenido.")
            % round(getattr(etiquetado, "cobertura", 0.0) * 100),
            Severidad.ERROR,
            remedio=_("El resto del documento tendría que volver a etiquetarse en "
                      "origen."),
            norma="ISO 14289-1, 7.1"))
    figuras = int(getattr(etiquetado, "figuras", 0) or 0)
    sin_alt = int(getattr(etiquetado, "figuras_sin_alt", 0) or 0)
    if sin_alt:
        hallazgos.anadir(Hallazgo(
            "FIGURAS_SIN_ALTERNATIVA",
            _("%d de las %d imágenes del documento no traen descripción.")
            % (sin_alt, figuras),
            Severidad.ERROR,
            cantidad=sin_alt,
            remedio=_("Se pueden describir con inteligencia artificial desde el "
                      "menú de imagen."),
            norma="ISO 14289-1, 7.3"))
    _revisar_tablas(hallazgos, etiquetas)
    _revisar_listas(hallazgos, etiquetas)
    if not getattr(etiquetado, "idioma", "") and getattr(etiquetado, "idiomas", None):
        hallazgos.anadir(informativo(
            "IDIOMAS_SIN_PRINCIPAL",
            _("Hay fragmentos con idioma declarado pero el documento no declara "
              "el suyo."),
            norma="ISO 14289-1, 7.2"))
    del diagnostico


def _revisar_anidamiento(hallazgos: ColeccionHallazgos, pares: dict) -> None:
    """Comprueba que las tablas, las listas y los \u00edndices est\u00e9n bien anidados.

    Es la mitad de las reglas de PDF/UA sobre estructura, y todas dicen lo
    mismo de formas distintas: una fila fuera de su tabla, un punto fuera de su
    lista o una celda fuera de su fila **existen** en el archivo, pero el
    lector de pantalla no puede anunciarlas como lo que son, porque lo que
    anuncia no es la etiqueta suelta sino la relaci\u00f3n.  Una celda que no
    cuelga de una fila no tiene columna, y sin columna no hay encabezado que
    decir.

    Se comprueba con la cuenta de pares padre-hijo que el recorrido del \u00e1rbol
    ya trae, sin volver a abrir nada, y se agrupa por familias: veinte avisos
    de \u00abTD fuera de TR\u00bb no dicen m\u00e1s que uno con su n\u00famero, y llenar\u00edan el
    informe tapando lo dem\u00e1s.
    """
    if not pares:
        return
    malos = _pares_indebidos(pares)
    if not malos:
        return

    def contar(familia):
        """Cuántos elementos mal colgados hay en esa familia de etiquetas."""
        return sum(cantidad for (padre, hijo), cantidad in malos.items()
                   if padre in familia or hijo in familia)

    cuantos = contar(("Table", "THead", "TBody", "TFoot", "TR", "TH", "TD"))
    if cuantos:
        hallazgos.anadir(aviso(
            "TABLA_MAL_FORMADA",
            _n("Hay %d elemento de tabla que no cuelga de donde debe.",
               "Hay %d elementos de tabla que no cuelgan de donde deben.",
               cuantos) % cuantos,
            cantidad=cuantos,
            remedio=_("Al recorrer esas tablas no se podrá decir de qué fila y "
                      "columna es cada dato."),
            norma="ISO 14289-1, 7.2"))
    cuantos = contar(("L", "LI", "Lbl", "LBody"))
    if cuantos:
        hallazgos.anadir(aviso(
            "LISTA_MAL_FORMADA",
            _n("Hay %d elemento de lista que no cuelga de donde debe.",
               "Hay %d elementos de lista que no cuelgan de donde deben.",
               cuantos) % cuantos,
            cantidad=cuantos,
            remedio=_("Esos puntos no se anunciarán como parte de una lista."),
            norma="ISO 14289-1, 7.2"))
    cuantos = contar(("TOC", "TOCI"))
    if cuantos:
        hallazgos.anadir(informativo(
            "INDICE_MAL_FORMADO",
            _n("Hay %d entrada del índice del documento que no cuelga de donde debe.",
               "Hay %d entradas del índice del documento que no cuelgan de donde "
               "deben.", cuantos) % cuantos,
            cantidad=cuantos,
            norma="ISO 14289-1, 7.2"))


def _pares_indebidos(pares: dict) -> dict:
    """Deja solo los pares padre-hijo que la norma no admite."""
    resultado: dict = {}
    for clave, cantidad in pares.items():
        try:
            padre, hijo = clave
        except (TypeError, ValueError):
            continue
        if padre in TRANSPARENTES or hijo in TRANSPARENTES:
            continue
        admitidos = HIJOS_ADMITIDOS.get(padre)
        if admitidos is not None and hijo not in admitidos:
            resultado[clave] = resultado.get(clave, 0) + cantidad
            continue
        padres = PADRES_ADMITIDOS.get(hijo)
        if padres is not None and padre not in padres:
            resultado[clave] = resultado.get(clave, 0) + cantidad
    return resultado


def _revisar_equivalencias(hallazgos: ColeccionHallazgos, etiquetado,
                           diagnostico=None) -> None:
    """Comprueba las etiquetas que el documento se ha inventado.

    Un PDF puede llamar a sus elementos como quiera —\u00abTitular\u00bb, \u00abParrafo2\u00bb—
    con una condici\u00f3n: decir en el ``RoleMap`` a qu\u00e9 etiqueta de la norma
    equivale cada uno.  Sin esa equivalencia el elemento existe pero no
    significa nada, y el lector de pantalla lo lee como texto suelto.
    """
    if diagnostico is None or not getattr(diagnostico, "con_pypdf", False):
        return
    etiquetas = set(getattr(etiquetado, "etiquetas", {}) or {})
    if not etiquetas:
        return
    mapa = dict(getattr(diagnostico, "role_map", {}) or {})
    huerfanas = sorted(
        nombre for nombre in etiquetas
        if nombre not in ETIQUETAS_NORMALIZADAS and nombre not in mapa)
    if huerfanas:
        hallazgos.anadir(aviso(
            "ETIQUETAS_SIN_EQUIVALENCIA",
            _n("El documento usa %d etiqueta propia sin decir a qu\u00e9 equivale.",
               "El documento usa %d etiquetas propias sin decir a qu\u00e9 equivalen.",
               len(huerfanas)) % len(huerfanas),
            cantidad=len(huerfanas),
            remedio=_("Esos elementos se leer\u00e1n como texto suelto: %s.")
            % ", ".join(huerfanas[:6]),
            norma="ISO 14289-1, 7.1"))
    # Solo cuenta el cambio que **tiene efecto**: casi todo lo que sale de Word
    # trae «Artifact» apuntando a «P» aunque el documento no use ni una sola
    # etiqueta Artifact, y avisar de eso sería quejarse en todos los documentos
    # de algo que no le pasa a ninguno.
    cambiadas = sorted(nombre for nombre in mapa
                       if nombre in ETIQUETAS_NORMALIZADAS and nombre in etiquetas)
    if cambiadas:
        hallazgos.anadir(aviso(
            "ETIQUETAS_NORMALES_CAMBIADAS",
            _n("El documento cambia el significado de %d etiqueta de la norma.",
               "El documento cambia el significado de %d etiquetas de la norma.",
               len(cambiadas)) % len(cambiadas),
            cantidad=len(cambiadas),
            remedio=_("Se leerán como lo que el documento diga que son, no como lo "
                      "que su nombre indica: %s.") % ", ".join(cambiadas[:6]),
            norma="ISO 14289-1, 7.1"))
    if _mapa_circular(mapa):
        hallazgos.anadir(Hallazgo(
            "EQUIVALENCIA_CIRCULAR",
            _("Las equivalencias de etiquetas del documento se muerden la cola."),
            Severidad.ERROR,
            remedio=_("Los elementos afectados no significan nada para el lector "
                      "de pantalla."),
            norma="ISO 14289-1, 7.1"))
    _revisar_niveles_mezclados(hallazgos, etiquetas)


def _mapa_circular(mapa: dict) -> bool:
    """Indica si alguna equivalencia de etiquetas acaba volviendo sobre s\u00ed misma."""
    for inicio in mapa:
        visto = {inicio}
        actual = mapa.get(inicio)
        while actual is not None and actual in mapa:
            if actual in visto:
                return True
            visto.add(actual)
            actual = mapa.get(actual)
    return False


def _revisar_niveles_mezclados(hallazgos: ColeccionHallazgos, etiquetas) -> None:
    """Comprueba que el documento titule de una manera o de la otra, no de las dos.

    La norma admite dos formas de titular y **solo una por documento**: con
    ``H`` a secas, donde el nivel sale de lo hondo que est\u00e9 la secci\u00f3n, o con
    ``H1`` a ``H6``, donde el nivel va escrito.  Mezclarlas deja al lector de
    pantalla sin saber qu\u00e9 nivel tiene la mitad de los t\u00edtulos.
    """
    numerados = any(nombre in etiquetas for nombre in ("H1", "H2", "H3", "H4", "H5", "H6"))
    if "H" in etiquetas and numerados:
        hallazgos.anadir(aviso(
            "TITULOS_MEZCLADOS",
            _("El documento mezcla las dos formas de titular de la norma."),
            remedio=_("Algunos t\u00edtulos pueden quedarse sin nivel al recorrerlos."),
            norma="ISO 14289-1, 7.4.4"))


def _revisar_tablas(hallazgos: ColeccionHallazgos, etiquetas: dict) -> None:
    """Comprueba que las tablas digan cuáles son sus encabezados.

    Una tabla sin celdas de encabezado se recorre igual, pero al llegar a una
    celda el lector de pantalla no puede decir de qué columna es.  En una tabla
    de datos, eso convierte cada número en un número suelto: se oye «1.348» sin
    saber si son euros, habitantes o el año.
    """
    tablas = int(etiquetas.get("Table", 0))
    if not tablas:
        return
    if not etiquetas.get("TH"):
        hallazgos.anadir(Hallazgo(
            "TABLAS_SIN_ENCABEZADO",
            _("Las %d tablas del documento no marcan ninguna celda como "
              "encabezado.") % tablas,
            Severidad.ERROR,
            cantidad=tablas,
            remedio=_("Al recorrerlas no se podrá anunciar de qué columna es cada "
                      "dato."),
            norma="ISO 14289-1, 7.5"))
    if etiquetas.get("TD") and not etiquetas.get("TR"):
        hallazgos.anadir(aviso(
            "TABLA_SIN_FILAS",
            _("Hay celdas de tabla que no están dentro de ninguna fila."),
            norma="ISO 14289-1, 7.5"))


def _revisar_listas(hallazgos: ColeccionHallazgos, etiquetas: dict) -> None:
    """Comprueba que las listas estén bien formadas.

    Un punto de lista suelto, fuera de su lista, no se anuncia como tal y el
    lector pierde la cuenta de por dónde va.
    """
    if etiquetas.get("LI") and not etiquetas.get("L"):
        hallazgos.anadir(aviso(
            "PUNTOS_SIN_LISTA",
            _("Hay puntos de lista que no están dentro de ninguna lista."),
            norma="ISO 14289-1, 7.6"))
    if etiquetas.get("L") and not etiquetas.get("LBody"):
        hallazgos.anadir(informativo(
            "LISTA_SIN_CUERPO",
            _("Las listas no separan la viñeta del contenido de cada punto."),
            norma="ISO 14289-1, 7.6"))


# ---------------------------------------------------------------------------
# El documento ya convertido
# ---------------------------------------------------------------------------

def _revisar_estructura(hallazgos: ColeccionHallazgos, documento) -> None:
    """Comprueba la estructura tal como ha quedado, venga de donde venga.

    Se hace sobre el documento convertido a propósito, y no sobre el árbol del
    PDF: lo que importa es lo que el usuario va a poder recorrer, que puede
    venir de las etiquetas, de la geometría o del reconocimiento óptico.
    """
    marcas = documento.marcas
    niveles = _niveles(marcas)
    if not niveles:
        if not documento.indice:
            hallazgos.anadir(Hallazgo(
                "SIN_ENCABEZADOS",
                _("El documento no tiene ningún encabezado ni índice: no se puede "
                  "recorrer, solo leer de principio a fin."),
                Severidad.ERROR,
                norma="ISO 14289-1, 7.4"))
        else:
            hallazgos.anadir(aviso(
                "SIN_ENCABEZADOS_CON_INDICE",
                _("El documento no tiene encabezados, pero sí un índice propio con "
                  "el que moverse."),
                norma="ISO 14289-1, 7.4"))
        return
    if niveles[0] != 1:
        hallazgos.anadir(informativo(
            "EMPIEZA_SIN_NIVEL_UNO",
            _("El primer encabezado del documento es de nivel %d, no de nivel 1.")
            % niveles[0],
            norma="ISO 14289-1, 7.4"))
    saltos = _saltos_de_nivel(niveles)
    if saltos:
        hallazgos.anadir(aviso(
            "NIVELES_SALTADOS",
            _("La jerarquía de encabezados se salta un nivel %d veces.") % saltos,
            cantidad=saltos,
            remedio=_("Al moverse por niveles faltará un peldaño."),
            norma="ISO 14289-1, 7.4"))


def _niveles(marcas) -> list:
    """Devuelve los niveles de los encabezados en el orden en que aparecen."""
    ordenadas = sorted(marcas.encabezados, key=lambda marca: marca.posicion)
    resultado = []
    for marca in ordenadas:
        try:
            resultado.append(ENCABEZADOS.index(TipoMarca(marca.tipo)) + 1)
        except (ValueError, KeyError):
            continue
    return resultado


def _saltos_de_nivel(niveles: list) -> int:
    """Cuenta cuántas veces la jerarquía se salta un peldaño al bajar.

    Bajar de un ``h2`` a un ``h4`` es un salto; **subir** de un ``h4`` a un
    ``h2`` no lo es: cerrar dos secciones de golpe es normal y correcto.
    Contar los dos, que es el error fácil, daría por roto cualquier documento
    bien hecho con más de dos niveles.
    """
    saltos = 0
    anterior = 0
    for nivel in niveles:
        if anterior and nivel > anterior + 1:
            saltos += 1
        anterior = nivel
    return saltos
