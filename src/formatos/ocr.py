# -*- coding: utf-8 -*-
"""Reconocimiento óptico de caracteres: sacar texto de una página escaneada.

Un PDF escaneado son imágenes: no hay texto que leer, y por eso un lector de
pantalla no puede hacer nada con él.  Es la carencia que más se repite en la
bibliografía sobre lectura accesible, y la que deja fuera buena parte de lo que
le llega a una persona ciega: apuntes fotocopiados, artículos antiguos, libros
digitalizados, folletos.

Hay **tres motores** y se pueden usar todos; cuál conviene depende del
documento, así que se eligen en Opciones:

1. **Tesseract** (``tesseract``).  Viene con el programa, en
   ``data/tesseract``, sin nada que instalar.  Es el mejor cuando la página
   tiene *estructura*: columnas, tablas, rejillas de tarjetas.  Devuelve las
   coordenadas de cada palabra, y con ellas se reconstruye el orden de lectura
   y se detectan las tablas (véase :mod:`formatos.disposicion`).  Funciona sin
   conexión y no gasta cuota.
2. **La inteligencia artificial** que esté configurada (``ia``).  Es la que
   mejor lee el texto suelto y la que aguanta un escaneado torcido, con
   manchas o con letra rara.  Necesita conexión y gasta cuota.
3. **El OCR de Windows** (``windows``).  Gratis y sin conexión, ya está en el
   sistema.  Acierta bien en un escaneado limpio de texto corrido y se queda
   corto en todo lo demás.  También da coordenadas, así que se le aplica el
   mismo análisis de disposición que a Tesseract.

Por qué importa la disposición
------------------------------

Un folleto de supermercado con nueve productos en rejilla, leído renglón a
renglón, sale así: «Sandía Melocotón Pitaya 0,90 €/kg 3,35 €/kg 2,15 €/ud».
Los nombres por un lado y los precios por otro, sin forma de saber cuál va con
cuál.  Leído con análisis de disposición sale cada producto con su precio.  Esa
diferencia —y no la de acertar una letra más— es la que decide si un documento
se puede usar o no.

El módulo no sabe nada de PDF: recibe imágenes ya rasterizadas y devuelve texto
o XHTML.  Así sirve igual para un PDF, para una imagen suelta o para lo que
venga después.
"""

from __future__ import annotations

import asyncio
import csv
import io
import subprocess
import tempfile
from pathlib import Path

from nucleo.idioma import _
from nucleo.registro import obtener_registro, registrar_excepcion

from . import disposicion

log = obtener_registro(__name__)

#: Prompt que se le da a la IA para transcribir.  Insiste en el **orden de
#: lectura** y en las tablas porque es donde se juega el resultado: un modelo
#: al que solo se le pide «transcribe» devuelve las columnas entremezcladas.
PROMPT_TRANSCRIBIR = (
    "Transcribe TODO el texto de esta página respetando el ORDEN DE LECTURA humano.\n\n"
    "Reglas:\n"
    "1. Si la página tiene varias columnas, fichas, recuadros o tarjetas, transcribe cada "
    "una COMPLETA antes de pasar a la siguiente, de izquierda a derecha y de arriba abajo. "
    "Nunca leas en horizontal cruzando de una columna a otra.\n"
    "2. Mantén junto lo que va junto: un nombre de producto con su precio, un titular con "
    "su texto, un pie con su figura.\n"
    "3. Si hay una TABLA, devuélvela en HTML con <table>, <tr> y <td>, con una fila por "
    "fila real y una celda por columna real. Usa <th> para los encabezados.\n"
    "4. Respeta los párrafos y los saltos de línea del resto del texto.\n"
    "5. No describas la página, no añadas comentarios y no inventes nada. Si algo no se lee, "
    "escribe [ilegible].\n"
    "6. Si la página no tiene texto, responde exactamente: (sin texto)."
)

#: Lo que responde la IA cuando la página no tiene nada.
SIN_TEXTO = "(sin texto)"

#: Aumento con el que se rasteriza una página para cada motor.  Tesseract
#: mejora claramente al subir de 2 a 3 —a 200 puntos por pulgada empieza a
#: fallar con la letra pequeña de un folleto— y empeora a partir de ahí, porque
#: el desenfoque del aumento pesa más que el detalle que aporta.  La IA no lo
#: necesita y cada punto de más son tokens que se pagan.
ESCALA = {"tesseract": 3.0, "windows": 2.0, "ia": 2.0}

#: Qué motores usa cada modo de reconocimiento, y en qué orden.  Cuando hay
#: varios, se prueba el siguiente si el anterior falla.
MODOS = {
    "auto": ("tesseract", "ia", "windows"),
    "tesseract": ("tesseract",),
    "ia": ("ia",),
    "windows": ("windows",),
    "ia_tesseract": ("ia", "tesseract"),
    "ninguno": (),
}

#: Modo de fábrica.  Empieza por Tesseract porque viene con el programa, no
#: gasta cuota, no necesita conexión y es el que mejor conserva la estructura.
MODO_POR_OMISION = "auto"


def nombres_de_modo() -> list[tuple[str, str]]:
    """Devuelve los modos en el orden en que se le ofrecen al usuario.

    Es una función y no una constante porque los rótulos van traducidos y el
    idioma se elige después de importar el módulo.
    """
    return [
        ("auto", _("Automático: Tesseract y, si no puede, la IA o el de Windows (recomendado)")),
        ("tesseract", _("Solo Tesseract (viene incluido, sin conexión, respeta las tablas)")),
        ("ia", _("Solo la inteligencia artificial (la que mejor lee la letra difícil)")),
        ("windows", _("Solo el de Windows (sin conexión y sin gastar cuota)")),
        ("ia_tesseract", _("La IA y, si no puede, Tesseract")),
        ("grafico", _("No reconocer: enseñar las páginas escaneadas como imágenes")),
        ("ninguno", _("No reconocer: los PDF escaneados se abrirán vacíos")),
    ]


class Ajustes:
    """Todo lo que se puede tocar del reconocimiento, en un solo sitio.

    Antes esto eran atributos sueltos repartidos por el analizador de PDF, y
    cada ajuste nuevo obligaba a tocar tres archivos.  Aquí van juntos, se
    construyen de una vez desde las preferencias y viajan hasta el motor.

    Los valores de fábrica no son arbitrarios: salen de medir sobre un folleto
    real cuántos productos se leían **con su precio al lado** y cuánta basura
    salía.  El preprocesado en gris con contraste 3 fue lo que más aportó.
    """

    __slots__ = ("modo", "idiomas", "escala", "psm", "oem", "dpi", "confianza",
                 "gris", "contraste", "binarizar", "umbral", "quitar_simbolos",
                 "detectar_tablas", "maximo_paginas", "idioma_windows", "esmerado",
                 "confianza_relleno")

    def __init__(self, **valores) -> None:
        self.modo = MODO_POR_OMISION
        self.idiomas = ""
        self.escala = 0.0            # 0 = el que le vaya bien a cada motor
        self.psm = 1                 # segmentación automática con orientación
        self.oem = 3                 # el motor que Tesseract prefiera
        self.dpi = 0                 # 0 = que lo deduzca
        self.confianza = 30.0
        self.gris = True
        self.contraste = 3.0
        self.binarizar = False
        self.umbral = 160
        self.quitar_simbolos = True
        self.detectar_tablas = True
        self.maximo_paginas = 100
        self.idioma_windows = "es"
        # Doble pasada: se lee la página dos veces con la imagen preparada de
        # dos formas distintas y se juntan los resultados.  Medido sobre un
        # folleto real, pasó de 15 a 20 productos leídos con su precio de 23.
        self.esmerado = True
        #: Confianza que se le exige a una letra suelta de la segunda pasada.
        #: Alta a propósito: con 95, el folleto de prueba pasó de 12 líneas de
        #: basura a 4 sin perder ni un acierto.
        self.confianza_relleno = 95.0
        for nombre, valor in valores.items():
            if nombre in self.__slots__:
                setattr(self, nombre, valor)

    @classmethod
    def desde_configuracion(cls, configuracion) -> "Ajustes":
        """Construye los ajustes a partir de las preferencias del usuario."""
        obtener = configuracion.obtener
        return cls(
            modo=str(obtener("pdf_ocr_modo", MODO_POR_OMISION)),
            idiomas=str(obtener("pdf_ocr_idiomas", "") or ""),
            escala=float(obtener("pdf_ocr_escala", 0) or 0),
            psm=int(obtener("pdf_ocr_psm", 1)),
            oem=int(obtener("pdf_ocr_oem", 3)),
            dpi=int(obtener("pdf_ocr_dpi", 0) or 0),
            confianza=float(obtener("pdf_ocr_confianza", 30)),
            gris=bool(obtener("pdf_ocr_gris", True)),
            contraste=float(obtener("pdf_ocr_contraste", 3.0)),
            binarizar=bool(obtener("pdf_ocr_binarizar", False)),
            umbral=int(obtener("pdf_ocr_umbral", 160)),
            quitar_simbolos=bool(obtener("pdf_ocr_quitar_simbolos", True)),
            detectar_tablas=bool(obtener("pdf_ocr_tablas", True)),
            maximo_paginas=int(obtener("pdf_ocr_maximo", 100)),
            esmerado=bool(obtener("pdf_ocr_esmerado", True)),
            confianza_relleno=float(obtener("pdf_ocr_confianza_relleno", 95)),
        )

    def escala_de(self, motor: str) -> float:
        """Aumento con el que rasterizar para un motor concreto."""
        return self.escala if self.escala > 0 else ESCALA.get(motor, 2.0)

    def __repr__(self) -> str:
        return ("<Ajustes OCR modo=%s idiomas=%s psm=%d gris=%s contraste=%.1f>"
                % (self.modo, self.idiomas or "auto", self.psm, self.gris, self.contraste))


def modos_de_segmentacion() -> list[tuple[int, str]]:
    """Los modos de segmentación de página de Tesseract que tienen sentido aquí.

    Se omiten los que solo valen para casos muy concretos —una sola línea, una
    sola palabra, un solo carácter— porque en un documento no se usan nunca y
    solo estorbarían en la lista.
    """
    return [
        (1, _("Automática, detectando la orientación (recomendado)")),
        (3, _("Automática, sin detectar la orientación")),
        (4, _("Una sola columna de texto de tamaños variables")),
        (6, _("Un único bloque de texto uniforme")),
        (11, _("Texto disperso: busca todo el texto que pueda, sin orden")),
        (12, _("Texto disperso, detectando la orientación")),
    ]


def motores_de_tesseract() -> list[tuple[int, str]]:
    """Los motores internos de Tesseract."""
    return [
        (3, _("El que Tesseract prefiera (recomendado)")),
        (1, _("Solo el de redes neuronales (LSTM)")),
        (0, _("Solo el clásico, más rápido y menos preciso")),
        (2, _("Los dos combinados")),
    ]


class Reconocido:
    """Lo que devuelve un motor al leer una página.

    Lleva las dos formas del resultado porque no siempre interesa la misma: el
    ``texto`` sirve para decidir si mereció la pena reconocer, y el ``html``
    —cuando el motor ha sabido reconstruir la estructura— es lo que conserva
    las tablas y el orden de lectura al montar el libro.
    """

    __slots__ = ("texto", "html", "motor")

    def __init__(self, texto: str, html: str = "", motor: str = "") -> None:
        self.texto = texto or ""
        self.html = html or ""
        self.motor = motor

    def __bool__(self) -> bool:
        return bool(self.texto.strip())

    def __len__(self) -> int:
        return len(self.texto.strip())

    def __repr__(self) -> str:
        return "<Reconocido %s %d caracteres%s>" % (
            self.motor, len(self.texto), ", con estructura" if self.html else "")


# ---------------------------------------------------------------------------
# Disponibilidad de cada motor
# ---------------------------------------------------------------------------

def _windows_disponible() -> bool:
    """Indica si el OCR de Windows se puede usar en este equipo."""
    try:
        import winsdk.windows.media.ocr  # noqa: F401

        return True
    except Exception:
        return False


def _tesseract_disponible() -> bool:
    """Indica si hay un Tesseract con idiomas listo para usar."""
    from nucleo import tesseract

    return tesseract.disponible() and bool(tesseract.instalados())


def motores_disponibles(servicio=None, modo: str = MODO_POR_OMISION) -> list[str]:
    """Devuelve qué motores se pueden usar ahora mismo, en orden de uso.

    :param servicio: Servicio de IA ya configurado, o ``None``.
    :param modo: Cuál de :data:`MODOS` ha elegido el usuario.
    """
    motores = []
    for motor in MODOS.get(modo, MODOS[MODO_POR_OMISION]):
        if motor == "ia" and servicio is not None and servicio.activa:
            motores.append("ia")
        elif motor == "windows" and _windows_disponible():
            motores.append("windows")
        elif motor == "tesseract" and _tesseract_disponible():
            motores.append("tesseract")
    return motores


def nombre_de_motor(motor: str) -> str:
    """Cómo se llama un motor, para decirlo en un mensaje."""
    return {
        "tesseract": _("Tesseract"),
        "ia": _("la inteligencia artificial"),
        "windows": _("el reconocimiento de Windows"),
    }.get(motor, motor)


def motivo_sin_ocr(modo: str = MODO_POR_OMISION) -> str:
    """Explica qué hacer cuando no hay ningún motor disponible.

    El consejo cambia según lo que el usuario haya elegido: de nada sirve
    decirle que configure la inteligencia artificial a quien ha pedido
    precisamente que no se use.
    """
    from nucleo import tesseract

    cabecera = _(
        "Este PDF está escaneado: son imágenes, no texto, así que hay que reconocerlo con OCR.")
    if modo == "ninguno":
        return cabecera + _(
            "\n\nTienes el reconocimiento desactivado. Actívalo en Opciones, «Lectura», "
            "«PDF escaneado».\n\nY si lo que quieres es ver el documento tal como "
            "está —un cómic, un manga, un álbum—, elige ahí «enseñar las páginas "
            "escaneadas como imágenes»: no se reconoce nada, y cada página se puede "
            "ver con Control+I y describir con la inteligencia artificial.")
    if modo == "tesseract":
        return cabecera + "\n\n" + (tesseract.motivo_no_disponible() or _(
            "Has elegido reconocer solo con Tesseract y no está disponible."))
    if modo == "ia":
        return cabecera + _(
            "\n\nHas elegido reconocer solo con la inteligencia artificial y no está "
            "configurada.\n\n"
            "• Configúrala en Opciones, «Inteligencia artificial».\n"
            "• O cambia el modo de reconocimiento para que pueda usar también Tesseract.")
    if modo == "windows":
        return cabecera + _(
            "\n\nHas elegido reconocer solo con Windows y no está disponible.\n\n"
            "• Instálalo con: pip install winsdk\n"
            "• O cambia el modo de reconocimiento para que pueda usar también Tesseract.")
    return cabecera + _(
        "\n\nNo hay ningún motor disponible. Formas de arreglarlo:\n"
        "• Tesseract debería venir con el programa, en «data\\tesseract»; comprueba que "
        "esa carpeta existe y tiene algún idioma.\n"
        "• Configura la inteligencia artificial en Opciones.\n"
        "• O instala el reconocimiento de Windows: pip install winsdk")


# ---------------------------------------------------------------------------
# Tesseract
# ---------------------------------------------------------------------------

#: Cómo se prepara la página en cada pasada del modo esmerado.
#:
#: Las dos van sobre la imagen preparada y solo cambian en **cómo se decide qué
#: es tinta y qué es fondo**: la primera con el umbral global de siempre y la
#: segunda con Sauvola, que lo calcula por zonas.  Ese detalle es el que hace
#: que fallen en sitios distintos, que es de lo que se trata.
#:
#: El orden importa y se eligió midiendo.  Sauvola encuentra más cosas, pero
#: entre ellas trozos de adorno; puesta la primera manda su ruido sin pasar
#: ningún filtro, y puesta la segunda solo aporta lo que pasa el filtro de
#: relleno.  Sobre el mismo folleto: de primera daba 19 aciertos con 5 líneas
#: de basura, y de segunda **los mismos 19 con 2**.
PASADAS = (
    {"preparar": True, "thresholding_method": "0"},   # umbral global
    {"preparar": True, "thresholding_method": "2"},   # Sauvola, por zonas
)


def ocr_tesseract(datos_png: bytes, idioma: str = "", estructura: bool = True,
                  ajustes: "Ajustes | None" = None) -> Reconocido:
    """Reconoce una imagen con Tesseract y reconstruye su disposición.

    Se le pide la salida en TSV, que trae **una fila por palabra con sus
    coordenadas**.  Ese es todo el motivo de usar este formato y no el texto
    plano: con las coordenadas se puede averiguar el orden de lectura de una
    página a varias columnas y reconocer las tablas, que es justo lo que un
    lector de pantalla no puede deducir por su cuenta.

    :param datos_png: Imagen en PNG.
    :param idioma: Idiomas de Tesseract separados por «+», o vacío para elegir.
    :param estructura: Si se reordena la página y se buscan tablas.
    :raises RuntimeError: Si Tesseract no está disponible o falla.
    """
    from nucleo import tesseract

    from . import imagen as preparacion

    ajustes = ajustes or Ajustes()
    binario = tesseract.ejecutable()
    if binario is None:
        raise RuntimeError(tesseract.motivo_no_disponible())
    # Se pasa siempre por «idioma_por_omision», que quita lo que no es un
    # idioma de lectura —«osd» y «equ»— y limita a tres: con más, Tesseract
    # tarda el doble sin acertar una letra más.
    idiomas = tesseract.idioma_por_omision(idioma or ajustes.idiomas)
    if not idiomas:
        raise RuntimeError(tesseract.motivo_no_disponible())

    if ajustes.esmerado and preparacion.disponible():
        palabras = _dos_pasadas(datos_png, binario, idiomas, ajustes)
    else:
        preparada = preparacion.preparar(
            datos_png, gris=ajustes.gris, contraste=ajustes.contraste,
            binarizar=ajustes.binarizar, umbral=ajustes.umbral)
        palabras = _una_pasada(preparada, binario, idiomas, ajustes)

    if ajustes.quitar_simbolos:
        palabras = disposicion.quitar_sueltas(palabras)
    if not palabras:
        return Reconocido("", "", "tesseract")
    if not estructura:
        return Reconocido(" ".join(p.texto for p in palabras), "", "tesseract")
    log.debug("Tesseract (%s, psm %d%s): %s", idiomas, ajustes.psm,
              _(", doble pasada") if ajustes.esmerado else "",
              disposicion.resumen(palabras))
    return Reconocido(disposicion.a_texto(palabras),
                      disposicion.a_html(palabras, tablas=ajustes.detectar_tablas),
                      "tesseract")


def _dos_pasadas(datos_png: bytes, binario, idiomas: str,
                 ajustes: "Ajustes") -> list[disposicion.Palabra]:
    """Lee la página dos veces, preparada de dos formas, y junta lo leído.

    Las dos pasadas no fallan en los mismos sitios: la preparada lee bien el
    texto oscuro sobre claro y se come lo que va sobre un círculo de color, y
    la de la página tal cual, al revés.  Juntarlas recupera lo que solo vio una
    de ellas sin repetir nada, porque la fusión es por sitio (véase
    :func:`formatos.disposicion.fusionar`).
    """
    from . import imagen as preparacion

    resultados: list[list[disposicion.Palabra]] = []
    for pasada in PASADAS:
        if pasada["preparar"]:
            entrada = preparacion.preparar(
                datos_png, gris=ajustes.gris, contraste=ajustes.contraste,
                binarizar=ajustes.binarizar, umbral=ajustes.umbral)
        else:
            entrada = datos_png
        try:
            resultados.append(_una_pasada(
                entrada, binario, idiomas, ajustes,
                extra={"thresholding_method": pasada["thresholding_method"]}))
        except RuntimeError as error:
            log.debug("Una pasada del reconocimiento ha fallado: %s", error)
    if not resultados:
        return []
    # Manda **siempre la primera pasada**, la de la imagen preparada, y no la
    # que más palabras haya sacado.  Ordenar por cantidad parecía razonable y
    # era justo lo contrario: la pasada sin preparar reconoce más cosas porque
    # también lee los adornos, así que salía elegida como principal y su ruido
    # entraba sin pasar por ningún filtro.
    fusionadas = resultados[0]
    for otra in resultados[1:]:
        # A la de relleno se le exige más confianza que a la principal.  Lo que
        # se le pide es que aporte lo que la otra no vio —un precio sobre un
        # círculo de color—, no que añada su propia cosecha de adornos mal
        # leídos: sin este filtro la basura casi se cuadruplicaba.
        fusionadas = disposicion.fusionar(
            fusionadas, [p for p in otra if _vale_de_relleno(p, ajustes)])
    return fusionadas


def _vale_de_relleno(palabra, ajustes: "Ajustes") -> bool:
    """Si una palabra de la segunda pasada merece añadirse.

    A la pasada de relleno se le pide que aporte lo que la otra no vio, no que
    añada su propia cosecha de adornos mal leídos.  El criterio sale de mirar
    qué aporta de verdad: **cifras**.  Lo que la primera pasada se pierde son
    los precios sobre fondos de color, y un precio siempre lleva dígitos; lo
    que sobra son fragmentos de una o dos letras sacados de un icono.

    Se aceptan, por tanto, las palabras con algún dígito, las de tres letras o
    más, y cualquiera que venga con mucha confianza.
    """
    texto = palabra.texto
    if any(c.isdigit() for c in texto):
        # Un precio siempre lleva cifras, y los precios son justo lo que la
        # primera pasada se deja: van sobre círculos de color.
        return True
    # Sin cifras hay que ser creíble, y «creíble» no es «con confianza alta»:
    # Tesseract está muy seguro de haber visto una «bed» donde había un icono.
    # Se pide además que sea una palabra de verdad —cuatro letras o más, con
    # vocal y sin mayúsculas sueltas por dentro—, que es lo que descarta los
    # trozos de adorno sin descartar ni un nombre de producto.
    if palabra.confianza < ajustes.confianza_relleno:
        return False
    return _parece_palabra(texto)


def _parece_palabra(texto: str) -> bool:
    """Si eso tiene pinta de ser una palabra y no un trozo de dibujo."""
    letras = [c for c in texto if c.isalpha()]
    if len(letras) < 4:
        return False
    if not any(c.lower() in "aeiouáéíóúàèìòùäëïöü" for c in letras):
        return False
    # Una mayúscula en medio delata un montaje de trozos: «WFORMAT», «ODisp».
    return not any(c.isupper() for c in letras[1:])


def _una_pasada(datos_png: bytes, binario, idiomas: str, ajustes: "Ajustes",
                extra: dict | None = None) -> list[disposicion.Palabra]:
    """Ejecuta Tesseract una vez y devuelve las palabras con sus coordenadas."""
    from nucleo import tesseract

    with tempfile.TemporaryDirectory(prefix="ocr_") as carpeta:
        entrada = Path(carpeta) / "pagina.png"
        entrada.write_bytes(datos_png)
        orden = [str(binario), str(entrada), str(Path(carpeta) / "salida"),
                 "-l", idiomas, "--psm", str(ajustes.psm), "--oem", str(ajustes.oem)]
        for clave, valor in (extra or {}).items():
            orden += ["-c", "%s=%s" % (clave, valor)]
        if ajustes.dpi > 0:
            # Sin esto Tesseract deduce la resolución y a veces se equivoca;
            # decírsela quita el aviso y afina la segmentación.
            orden += ["--dpi", str(ajustes.dpi)]
        orden.append("tsv")
        datos = tesseract.directorio_datos_tesseract()
        if datos is not None:
            orden[3:3] = ["--tessdata-dir", str(datos)]
        try:
            resultado = subprocess.run(
                orden, capture_output=True, text=True, timeout=180,
                creationflags=_sin_consola())
        except subprocess.TimeoutExpired:
            raise RuntimeError(_("Tesseract ha tardado demasiado en esta página."))
        except OSError as error:
            raise RuntimeError(_("No se ha podido ejecutar Tesseract: %s") % error)
        if resultado.returncode != 0:
            raise RuntimeError(_("Tesseract ha fallado: %s")
                               % (resultado.stderr or "").strip()[:300])
        salida = Path(carpeta) / "salida.tsv"
        if not salida.exists():
            return []
        return _leer_tsv(salida.read_text(encoding="utf-8", errors="replace"), ajustes)


def _leer_tsv(contenido: str, ajustes: "Ajustes | None" = None) -> list[disposicion.Palabra]:
    """Convierte la salida TSV de Tesseract en palabras con coordenadas."""
    ajustes = ajustes or Ajustes()
    palabras: list[disposicion.Palabra] = []
    lector = csv.DictReader(io.StringIO(contenido), delimiter="\t", quoting=csv.QUOTE_NONE)
    for fila in lector:
        # El nivel 5 es la palabra; los demás son página, bloque, párrafo y
        # línea, que aquí no hacen falta porque la agrupación se rehace.
        if fila.get("level") != "5":
            continue
        texto = (fila.get("text") or "").strip()
        if not texto:
            continue
        try:
            palabras.append(disposicion.Palabra(
                texto, int(fila["left"]), int(fila["top"]),
                int(fila["width"]), int(fila["height"]), float(fila["conf"])))
        except (KeyError, ValueError, TypeError):
            continue
    return disposicion.limpiar(palabras, confianza=ajustes.confianza,
                               quitar_simbolos=ajustes.quitar_simbolos)


def _sin_consola() -> int:
    """Bandera para que Windows no abra una ventana negra al ejecutar."""
    import sys

    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


# ---------------------------------------------------------------------------
# OCR de Windows
# ---------------------------------------------------------------------------

def ocr_windows(datos_png: bytes, idioma: str = "es", estructura: bool = True,
                ajustes: "Ajustes | None" = None) -> Reconocido:
    """Reconoce el texto de una imagen con el motor de Windows.

    Windows también devuelve la posición de cada palabra, así que se le aplica
    el mismo análisis de disposición que a Tesseract.  Es lo que arregla su
    peor defecto: por su cuenta lee las páginas a varias columnas de arriba
    abajo columna entera a columna entera, separando cada texto de su cifra.

    :param datos_png: Imagen en PNG.
    :param idioma: Idioma que se le pide al motor.  Si Windows no tiene ese
                   paquete de reconocimiento se usa el del sistema, que es
                   mejor que no reconocer nada.
    :param estructura: Si se reordena la página y se buscan tablas.
    """
    from winsdk.windows.globalization import Language
    from winsdk.windows.graphics.imaging import BitmapDecoder
    from winsdk.windows.media.ocr import OcrEngine
    from winsdk.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

    async def _trabajo():
        motor = None
        try:
            lengua = Language(idioma)
            if OcrEngine.is_language_supported(lengua):
                motor = OcrEngine.try_create_from_language(lengua)
        except Exception:
            motor = None
        if motor is None:
            motor = OcrEngine.try_create_from_user_profile_languages()
        if motor is None:
            raise RuntimeError(_(
                "Windows no tiene instalado ningún idioma de reconocimiento. Añádelo en "
                "Configuración de Windows, «Hora e idioma», «Idioma»."))
        flujo = InMemoryRandomAccessStream()
        escritor = DataWriter(flujo)
        escritor.write_bytes(datos_png)
        await escritor.store_async()
        await escritor.flush_async()
        escritor.detach_stream()
        flujo.seek(0)
        decodificador = await BitmapDecoder.create_async(flujo)
        mapa = await decodificador.get_software_bitmap_async()
        return await motor.recognize_async(mapa)

    # WinRT es asíncrono y esto se llama desde un hilo de trabajo normal, así
    # que hace falta un bucle propio para ese hilo.
    bucle = asyncio.new_event_loop()
    try:
        resultado = bucle.run_until_complete(_trabajo())
    finally:
        bucle.close()

    if resultado is None or not resultado.lines:
        return Reconocido("", "", "windows")

    palabras: list[disposicion.Palabra] = []
    for linea in resultado.lines:
        for palabra in getattr(linea, "words", []) or []:
            caja = palabra.bounding_rect
            palabras.append(disposicion.Palabra(
                palabra.text, int(caja.x), int(caja.y),
                int(caja.width), int(caja.height), 100.0))
    ajustes = ajustes or Ajustes()
    palabras = disposicion.limpiar(palabras, confianza=0.0,
                                   quitar_simbolos=ajustes.quitar_simbolos)
    if not palabras or not estructura:
        # Sin coordenadas utilizables se devuelve lo que dé el motor tal cual.
        return Reconocido("\n".join(linea.text for linea in resultado.lines), "", "windows")
    log.debug("OCR de Windows: %s", disposicion.resumen(palabras))
    return Reconocido(disposicion.a_texto(palabras),
                      disposicion.a_html(palabras, tablas=ajustes.detectar_tablas),
                      "windows")


# ---------------------------------------------------------------------------
# Puerta de entrada
# ---------------------------------------------------------------------------

def reconocer(datos_png: bytes, servicio=None, idioma: str = "es",
              modo: str = "", idiomas_tesseract: str = "",
              ajustes: "Ajustes | None" = None) -> Reconocido:
    """Saca el texto de una imagen con el mejor motor disponible.

    :param datos_png: Imagen en PNG.
    :param servicio: Servicio de IA ya configurado, o ``None``.
    :param idioma: Idioma para el OCR de Windows.
    :param modo: Cuál de :data:`MODOS` ha elegido el usuario.
    :param idiomas_tesseract: Idiomas de Tesseract separados por «+».
    :return: El resultado, vacío si la página no tiene texto.
    :raises RuntimeError: Si no hay ningún motor con el que reconocer.
    """
    ajustes = ajustes or Ajustes()
    modo = modo or ajustes.modo
    motores = motores_disponibles(servicio, modo)
    if not motores:
        raise RuntimeError(motivo_sin_ocr(modo))

    ultimo_error = None
    for motor in motores:
        try:
            if motor == "ia":
                texto = servicio.describir(datos_png, "pagina.png",
                                           _PromptFijo(PROMPT_TRANSCRIBIR))
                resultado = Reconocido(texto, _html_de_la_ia(texto), "ia")
            elif motor == "tesseract":
                resultado = ocr_tesseract(datos_png, idiomas_tesseract, ajustes=ajustes)
            else:
                resultado = ocr_windows(datos_png, idioma, ajustes=ajustes)
        except Exception as error:
            # Si un motor falla —cuota agotada, sin conexión, un binario que no
            # arranca— se sigue con el siguiente en lugar de dejar el libro sin
            # texto.
            log.info("El motor de OCR «%s» ha fallado: %s", motor, error)
            ultimo_error = error
            continue
        limpio = resultado.texto.strip()
        if limpio.lower().startswith(SIN_TEXTO):
            return Reconocido("", "", motor)
        if limpio:
            return resultado
    if ultimo_error is not None:
        raise RuntimeError(str(ultimo_error))
    return Reconocido("", "", motores[0] if motores else "")


def _html_de_la_ia(texto: str) -> str:
    """Aprovecha la tabla que devuelva la IA, si la ha devuelto.

    Al prompt se le pide que escriba las tablas en HTML.  Cuando lo hace, ese
    trozo se conserva tal cual para que el libro tenga una tabla de verdad; el
    resto se reparte en párrafos.  Si no hay ninguna tabla no se toca nada y se
    deja que el texto siga su camino normal.
    """
    if "<table" not in (texto or "").lower():
        return ""
    partes: list[str] = []
    resto = texto
    while True:
        bajo = resto.lower()
        inicio = bajo.find("<table")
        if inicio < 0:
            break
        fin = bajo.find("</table>", inicio)
        if fin < 0:
            break
        fin += len("</table>")
        partes.append(_parrafos(resto[:inicio]))
        partes.append(resto[inicio:fin])
        resto = resto[fin:]
    partes.append(_parrafos(resto))
    return "".join(parte for parte in partes if parte)


def _parrafos(texto: str) -> str:
    """Convierte texto suelto en párrafos XHTML."""
    from .ensamblador import escapar

    trozos = [linea.strip() for linea in (texto or "").split("\n")]
    return "".join("<p>%s</p>" % escapar(linea) for linea in trozos if linea)


class _PromptFijo:
    """Prompt de usar y tirar con la forma que espera el servicio de IA.

    El servicio acepta cualquier objeto con ``nombre`` y ``texto``; aquí se
    aprovecha para pedir la transcripción sin tocar el prompt que el usuario
    tenga elegido para describir imágenes.
    """

    __slots__ = ("nombre", "texto", "predefinido", "identificador")

    def __init__(self, texto: str) -> None:
        self.identificador = "ocr"
        self.nombre = _("Transcripción de página escaneada")
        self.texto = texto
        self.predefinido = True
