# -*- coding: utf-8 -*-
"""Traducción de la aplicación a otros idiomas.

Todo el texto que ve o escucha el usuario pasa por :func:`_`.  Con eso, traducir
el programa a otro idioma es cuestión de dejar un archivo en su sitio, sin tocar
ni una línea de código.

Cómo funciona
-------------

Se usa :mod:`gettext`, que es el mecanismo estándar.  Los textos originales
están **en español**: son ellos mismos la clave con la que se busca la
traducción.  Eso tiene una consecuencia cómoda: si no hay traducción para el
idioma elegido —o no hay ninguna instalada— el programa sigue funcionando en
español sin más, porque :func:`_` devuelve el texto tal cual.

Las traducciones van en ``data/idiomas/<código>/LC_MESSAGES/visor.mo``, donde
``<código>`` es ``en``, ``fr``, ``pt``…

**Los idiomas se detectan solos.**  No hay ninguna lista que mantener: al abrir
las opciones se mira qué carpetas hay y se ofrecen todas.  Añadir un idioma es
copiar su carpeta ahí dentro; quitarlo, borrarla.  El nombre que se muestra sale
de :data:`NOMBRES`, un diccionario de códigos ISO 639-1 con el nombre de cada
lengua **en esa misma lengua** —«Français», no «Francés»—, que es lo que espera
quien va a elegirla.  Si aparece un código que no está en el diccionario, se
muestra el código y se puede elegir igualmente.

Cómo se usa
-----------

Cada módulo que tenga texto para el usuario hace::

    from nucleo.idioma import _

y envuelve sus textos: ``_("Abrir documento")``.

:func:`_` es una función propia que consulta la traducción **en el momento de
llamarla**, no una referencia directa a la de :mod:`gettext`.  Así, importarla
una vez al principio de cada módulo sigue valiendo aunque la traducción cambie
después.

El idioma se elige al arrancar: los textos que se construyen al importar los
módulos (las tablas de atajos, los nombres de los prompts) se traducen una sola
vez, de modo que **cambiar de idioma pide reiniciar el programa**.  Es lo
honesto: lo contrario obligaría a reconstruir media aplicación en caliente para
un cambio que se hace una vez en la vida.
"""

from __future__ import annotations

import gettext
import locale
import os

from . import rutas

#: Nombre del dominio de traducción, que es el del archivo ``.mo``.
DOMINIO = "visor"

#: Idioma en el que están escritos los textos originales.  Siempre se puede
#: elegir, tenga o no archivo de traducción: es el propio programa.
ORIGINAL = "es"

#: Nombre de cada idioma **en su propia lengua**, que es como se ponen en un
#: selector de idioma: quien busca el francés busca «Français», no «Francés».
#: Están los códigos ISO 639-1 con presencia real; cualquier otro se muestra por
#: su código y funciona igual.
NOMBRES = {
    "af": "Afrikaans", "am": "አማርኛ", "ar": "العربية", "az": "Azərbaycan",
    "be": "Беларуская", "bg": "Български", "bn": "বাংলা", "bs": "Bosanski",
    "ca": "Català", "cs": "Čeština", "cy": "Cymraeg", "da": "Dansk",
    "de": "Deutsch", "el": "Ελληνικά", "en": "English", "eo": "Esperanto",
    "es": "Español", "et": "Eesti", "eu": "Euskara", "fa": "فارسی",
    "fi": "Suomi", "fil": "Filipino", "fo": "Føroyskt", "fr": "Français",
    "ga": "Gaeilge", "gl": "Galego", "gu": "ગુજરાતી", "he": "עברית",
    "hi": "हिन्दी", "hr": "Hrvatski", "hu": "Magyar", "hy": "Հայերեն",
    "id": "Bahasa Indonesia", "is": "Íslenska", "it": "Italiano", "ja": "日本語",
    "ka": "ქართული", "kk": "Қазақша", "km": "ខ្មែរ", "kn": "ಕನ್ನಡ",
    "ko": "한국어", "lt": "Lietuvių", "lv": "Latviešu", "mk": "Македонски",
    "ml": "മലയാളം", "mn": "Монгол", "mr": "मराठी", "ms": "Bahasa Melayu",
    "mt": "Malti", "nb": "Norsk bokmål", "ne": "नेपाली", "nl": "Nederlands",
    "nn": "Norsk nynorsk", "no": "Norsk", "pa": "ਪੰਜਾਬੀ", "pl": "Polski",
    "pt": "Português", "ro": "Română", "ru": "Русский", "si": "සිංහල",
    "sk": "Slovenčina", "sl": "Slovenščina", "sq": "Shqip", "sr": "Српски",
    "sv": "Svenska", "sw": "Kiswahili", "ta": "தமிழ்", "te": "తెలుగు",
    "th": "ไทย", "tr": "Türkçe", "uk": "Українська", "ur": "اردو",
    "uz": "Oʻzbekcha", "vi": "Tiếng Việt", "zh": "中文",
}

#: Nombre de las variantes regionales que de verdad se distinguen entre sí.
VARIANTES = {
    "pt_BR": "Português (Brasil)", "pt_PT": "Português (Portugal)",
    "es_MX": "Español (México)", "es_AR": "Español (Argentina)",
    "en_GB": "English (United Kingdom)", "en_US": "English (United States)",
    "zh_CN": "中文 (简体)", "zh_TW": "中文 (繁體)",
    "fr_CA": "Français (Canada)",
}

#: Traducción activa.  Se empieza con la nula, que devuelve el texto original.
_traduccion: gettext.NullTranslations = gettext.NullTranslations()

#: Código del idioma que está puesto.  Hace falta saberlo fuera de aquí: a la
#: inteligencia artificial hay que decirle **en qué idioma responder**, y ese
#: dato no se puede sacar de una traducción, que solo sabe traducir textos que
#: ya conoce.
_activo: str = ORIGINAL


def carpeta_idiomas():
    """Carpeta donde se buscan las traducciones."""
    return rutas.carpeta_idiomas()


def nombre_de(codigo: str) -> str:
    """Nombre de un idioma en su propia lengua, o su código si no se conoce.

    Reconoce las variantes regionales (``pt_BR``) y, si no conoce la variante
    concreta, cae en el idioma base: más vale «Português (BR)» que un código
    suelto que no le dice nada a nadie.
    """
    if not codigo:
        return ""
    limpio = codigo.replace("-", "_")
    if limpio in VARIANTES:
        return VARIANTES[limpio]
    if limpio.lower() in NOMBRES:
        return NOMBRES[limpio.lower()]
    base = limpio.split("_")[0].lower()
    if base in NOMBRES:
        if "_" in limpio:
            return "%s (%s)" % (NOMBRES[base], limpio.split("_", 1)[1].upper())
        return NOMBRES[base]
    return codigo


def instalados() -> list[str]:
    """Códigos de los idiomas que tienen traducción en la carpeta.

    Se buscan por su archivo **compilado**: una carpeta con solo el ``.po`` sin
    compilar no cuenta, porque no se podría usar.
    """
    encontrados = []
    try:
        for hijo in sorted(carpeta_idiomas().iterdir()):
            if not hijo.is_dir():
                continue
            if (hijo / "LC_MESSAGES" / ("%s.mo" % DOMINIO)).exists():
                encontrados.append(hijo.name)
    except OSError:
        pass
    return encontrados


def disponibles() -> list[tuple[str, str]]:
    """Idiomas que se pueden elegir, como pares ``(código, nombre)``.

    Siempre están «El del sistema» y el idioma original del programa; detrás,
    todos los que se hayan dejado en la carpeta, detectados solos y ordenados
    por su nombre.  Esta es la lista que se ofrece en las opciones, y por eso no
    hay ninguna lista de idiomas que mantener a mano en ningún sitio.
    """
    lista = [("auto", _("El del sistema")), (ORIGINAL, nombre_de(ORIGINAL))]
    otros = [(codigo, nombre_de(codigo)) for codigo in instalados() if codigo != ORIGINAL]
    otros.sort(key=lambda par: par[1].lower())
    return lista + otros


def _idioma_del_sistema() -> str:
    """Devuelve el idioma de Windows, o el original si no se puede saber."""
    for variable in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        valor = os.environ.get(variable, "")
        if valor:
            return valor.split(".")[0].split(":")[0] or ORIGINAL
    try:
        idioma, _codificacion = locale.getdefaultlocale()
        if idioma:
            return idioma
    except Exception:
        pass
    return ORIGINAL


def instalar(codigo: str = "auto") -> str:
    """Prepara la traducción y la deja activa.

    Debe llamarse **al arrancar**, antes de importar la interfaz: los textos
    que se construyen al importar los módulos se traducen una sola vez.

    Si el idioma del sistema es, por ejemplo, ``pt_BR`` y solo hay traducción
    ``pt``, :mod:`gettext` la encuentra igualmente: prueba primero la variante
    completa y después el idioma base.

    :param codigo: Código de idioma, o ``"auto"`` para usar el del sistema.
    :return: El código que ha quedado activo.
    """
    global _traduccion, _activo
    elegido = (codigo or "auto").strip()
    if elegido.lower() in ("", "auto"):
        elegido = _idioma_del_sistema()
    base = elegido.replace("-", "_").split("_")[0].lower()
    if base == ORIGINAL:
        # El original no se traduce: no hay nada que buscar.
        _traduccion = gettext.NullTranslations()
        _activo = elegido
        return elegido
    try:
        _traduccion = gettext.translation(
            DOMINIO, localedir=str(carpeta_idiomas()),
            languages=[elegido, base], fallback=True)
    except Exception:
        _traduccion = gettext.NullTranslations()
    _activo = elegido
    return elegido


def _(mensaje: str) -> str:
    """Devuelve la traducción de un texto, o el texto original si no la hay.

    Se consulta la traducción activa en cada llamada, de modo que importarla
    una vez por módulo sigue siendo correcto aunque cambie después.
    """
    return _traduccion.gettext(mensaje)


def _n(singular: str, plural: str, cantidad: int) -> str:
    """Elige entre singular y plural según la cantidad.

    En español bastaría con mirar si la cantidad es uno, pero **no en todos los
    idiomas**: el ruso tiene tres formas y el árabe seis, y una traducción hecha
    a base de «si es 1» sale mal en cuanto se traduce a uno de ellos.  Esta
    función delega en :mod:`gettext`, que aplica la regla declarada por cada
    traducción en su cabecera ``Plural-Forms``.

    Se usa así::

        _n("%d imagen", "%d imágenes", cuantas) % cuantas

    El número se interpola **después**, y va en los dos textos, porque hay
    idiomas donde la forma singular tampoco lleva el número escrito igual.

    :param singular: Texto cuando la cantidad es una.
    :param plural: Texto cuando son varias.  Es el que sirve de referencia para
                   las traducciones que tienen más de dos formas.
    :param cantidad: El número del que se habla.
    """
    return _traduccion.ngettext(singular, plural, cantidad)


def activo() -> str:
    """Código del idioma que está puesto ahora mismo."""
    return _activo


def nombre_activo() -> str:
    """Nombre del idioma activo, en su propia lengua.

    Es lo que se le dice a la inteligencia artificial para que conteste en el
    idioma del programa: «responde en Español», «responde en English».  Se usa
    el nombre y no el código porque un modelo entiende «Français» y puede
    confundir «fr» con otra cosa.
    """
    return nombre_de(_activo) or nombre_de(ORIGINAL)
