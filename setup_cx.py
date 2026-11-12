# -*- coding: utf-8 -*-
"""Generación del ejecutable con cx_Freeze.

No se ejecuta a mano: lo lanza la opción «Compilar» del archivo
``VisorUniversal.bat``.

Qué hace además de empaquetar el código:

* **Incluye las bibliotecas de Visual C++.**  Un ejecutable de Python necesita
  ``vcruntime140.dll``, ``vcruntime140_1.dll``, ``msvcp140.dll`` y
  ``concrt140.dll``.  Si faltan, el programa no arranca en equipos que no
  tengan instalado el paquete redistribuible de Microsoft.  Aquí se buscan en
  la instalación de Python y en el sistema, y se copian junto al ejecutable.

* **Crea una carpeta ``data`` limpia.**  La aplicación compilada se entrega
  con la estructura de carpetas ya creada, con los sonidos generados y con el
  manual de usuario dentro, pero **sin** ajustes, registros ni caché de las
  pruebas de desarrollo.
"""

from __future__ import annotations

import os
import shutil
import sys
import sysconfig
from pathlib import Path

from cx_Freeze import Executable, setup

RAIZ = Path(__file__).resolve().parent
CARPETA_FUENTE = RAIZ / "src"
sys.path.insert(0, str(CARPETA_FUENTE))

#: Nombre del ejecutable y de la carpeta de salida.
NOMBRE = "VisorUniversal"

#: Versión, tomada del propio programa para que nunca se desincronicen.
def _leer_version() -> str:
    """Extrae la versión declarada en ``src/version.py``.

    Se lee como texto, sin importar el módulo, para que este guion funcione
    aunque el entorno del programa no esté preparado todavía.
    """
    for linea in (CARPETA_FUENTE / "version.py").read_text(encoding="utf-8").splitlines():
        if linea.startswith("VERSION"):
            return linea.split("=", 1)[1].strip().strip('"').strip("'")
    return "1.0.0"


VERSION = _leer_version()

#: Bibliotecas de tiempo de ejecución de Visual C++ que hay que acompañar.
DLL_VISUAL_C = (
    "vcruntime140.dll",
    "vcruntime140_1.dll",
    "msvcp140.dll",
    "msvcp140_1.dll",
    "msvcp140_2.dll",
    "concrt140.dll",
    "vcomp140.dll",
)


def localizar_runtimes() -> list[tuple[str, str]]:
    """Busca las DLL de Visual C++ y devuelve la lista de archivos a copiar.

    Se buscan, por este orden, en la carpeta de Python, en su subcarpeta
    ``DLLs`` y en el sistema.  Se avisa por pantalla de las que no aparezcan,
    para que quien compile sepa exactamente qué falta.
    """
    carpetas = [
        Path(sys.base_prefix),
        Path(sys.base_prefix) / "DLLs",
        Path(sysconfig.get_paths()["platlib"]),
        Path(r"C:\Windows\System32"),
    ]
    encontradas: list[tuple[str, str]] = []
    faltan: list[str] = []
    for nombre in DLL_VISUAL_C:
        for carpeta in carpetas:
            candidata = carpeta / nombre
            if candidata.is_file():
                encontradas.append((str(candidata), nombre))
                break
        else:
            faltan.append(nombre)
    print("Bibliotecas de Visual C++ incluidas: %s" % ", ".join(n for _, n in encontradas))
    if faltan:
        print("AVISO: no se han encontrado (puede que no hagan falta): %s" % ", ".join(faltan))
    return encontradas


#: Lo que se deja dentro de «data/idiomas» del ejecutable.  Tres extensiones y
#: nadie tiene por qué saberse cuál es cuál: quien abra la carpeta con ganas de
#: arreglar una frase se merece que se lo pongan por escrito.
AVISO_IDIOMAS = """Las traducciones de la interfaz.

Hay una carpeta por idioma, con su código: es, en, fr, it, pt...

Dentro de cada una, en LC_MESSAGES, están los textos de la interfaz:

  visor.po   El catálogo que se edita.  Es texto: cada frase original con su
             traducción debajo.  Este es el que hay que tocar para corregir o
             completar un idioma, y va incluido justo para eso: para que puedas
             seguir a partir de lo ya traducido en vez de empezar de cero.
  visor.mo   El mismo catálogo compilado.  Es el que lee el programa.  No se
             edita a mano: se genera a partir del .po.

Y en docs, la documentación de ese idioma:

  MANUAL_USUARIO.md   El manual completo, en Markdown.  Es lo que abre F1.
  NOVEDADES.md        Lo que ha cambiado en cada versión.  Se abre desde el
                      menú Ayuda, en «Ver las últimas novedades».

Para traducir el manual a un idioma, se copia el de es/docs, se traduce y se
deja en la carpeta docs de ese idioma.  No hay nada que compilar ni que
registrar: el programa abre el manual del idioma que esté puesto y, si ese
idioma todavía no lo tiene, abre el español.

Y suelta, en esta carpeta:

  visor.pot  La plantilla con todos los textos del programa sin traducir, al
             día de esta versión.  Sirve para empezar un idioma nuevo.

Para cambiar un texto de la interfaz: edita el visor.po del idioma que quieras
y vuelve a compilarlo.  Hasta que no se compile, el programa seguirá usando el
.mo que haya, así que los cambios no se verán.  El manual, en cambio, se lee
tal cual: se guarda y ya está.

Si envías tu visor.po o tu manual corregidos, entran en la siguiente versión.
"""


def preparar_data_limpia() -> Path:
    """Crea una carpeta ``data`` recién hecha para acompañar al ejecutable.

    Contiene solo lo imprescindible:

    * ``sonidos``: los archivos de sonido ya generados, para que la primera
      ejecución no tenga que crearlos.
    * ``config``, ``logs``, ``cache``, ``temp``, ``descripciones`` y
      ``correcciones``: vacías, con un archivo de texto que explica para qué
      sirve cada una.
    * ``idiomas``: las traducciones de la interfaz y, dentro de cada idioma,
      su carpeta ``docs`` con el manual de usuario en esa lengua.
    * ``bin``: el 7-Zip portable, que es lo que abre los cómics en RAR y los
      comprimidos partidos en volúmenes sin pedirle a nadie que instale nada.

    Del ``data`` de desarrollo solo se copia la carpeta ``idiomas``: así el
    ejecutable sale siempre limpio, sin ajustes, registros ni caché de las
    pruebas.
    """
    destino = RAIZ / "build" / "data_limpia"
    if destino.exists():
        shutil.rmtree(destino)
    destino.mkdir(parents=True)

    explicaciones = {
        "config": "Aquí se guardan tus preferencias y la posición de lectura de cada libro.",
        "logs": "Aquí se guarda el registro de actividad del programa.",
        "cache": "Aquí se guardan los libros ya analizados para que se abran al instante.",
        "temp": "Archivos temporales. Se puede vaciar sin problema.",
        "sonidos": "Sonidos de navegación. Si borras uno, el programa lo vuelve a crear.",
        "descripciones": "Descripciones de las imágenes hechas con inteligencia artificial.",
        "correcciones": ("Lo que has corregido a mano en un PDF: qué era de verdad cada "
                         "elemento. Se guarda por documento y no toca el archivo original."),
    }
    for nombre, explicacion in explicaciones.items():
        carpeta = destino / nombre
        carpeta.mkdir()
        (carpeta / "LEEME.txt").write_text(explicacion + "\n", encoding="utf-8")

    # Los sonidos se generan aquí mismo, con el volumen por omisión.
    from sonidos import generador

    generador.generar(destino / "sonidos", volumen=70)

    # Traducciones.  Antes de copiarlas se rehace la plantilla y se vuelven a
    # compilar los catálogos, para que lo que viaja dentro del ejecutable sea
    # exactamente lo de esta versión: un «.pot» de hace tres versiones le da a
    # quien quiera traducir una lista de textos que ya no existen, y un «.mo»
    # sin recompilar deja fuera lo que se haya traducido desde la última vez.
    sys.path.insert(0, str(RAIZ / "herramientas"))
    try:
        import textos as catalogos

        catalogos.escribir_plantilla()
        catalogos.compilar()
    except Exception as error:                      # pragma: no cover - opcional
        print("AVISO: no se han podido rehacer las traducciones: %s" % error)

    # Se copia la carpeta entera: los «.mo» compilados, que son los que lee el
    # programa, la plantilla «.pot» para empezar un idioma desde cero y también
    # los «.po».  Estos últimos iban fuera por ser el original de trabajo, y era
    # un error: sin ellos, quien quiera arreglar una frase mal traducida al
    # italiano o continuar un idioma a medias tiene que rehacer las mil
    # novecientas entradas desde la plantilla.  Con el «.po» delante retoca lo
    # que haga falta y deja lo demás como está.  Ocupan un cuarto de mega cada
    # uno, que al lado de los noventa de Tesseract no es nada.
    idiomas = RAIZ / "data" / "idiomas"
    if idiomas.is_dir():
        shutil.copytree(idiomas, destino / "idiomas")
        cuantos = len(list((destino / "idiomas").glob("*/LC_MESSAGES/*.mo")))
        editables = len(list((destino / "idiomas").glob("*/LC_MESSAGES/*.po")))
        (destino / "idiomas" / "LEEME.txt").write_text(AVISO_IDIOMAS, encoding="utf-8")
        print("Traducciones incluidas: %d idiomas, %d catálogos .po editables "
              "y la plantilla visor.pot" % (cuantos, editables))

        # El manual ya no va suelto en «data»: cada idioma lleva el suyo en su
        # carpeta «docs», y el español es el que se abre cuando un idioma
        # todavía no lo tiene traducido.  Sin ese, F1 no abre nada.
        from nucleo.rutas import (IDIOMA_BASE, NOMBRE_CARPETA_DOCS,
                                  NOMBRE_MANUAL, NOMBRE_NOVEDADES)

        manuales = sorted(
            ruta.parent.parent.name
            for ruta in (destino / "idiomas").glob(
                "*/%s/%s" % (NOMBRE_CARPETA_DOCS, NOMBRE_MANUAL)))
        if IDIOMA_BASE in manuales:
            print("Manual de usuario incluido en: %s" % ", ".join(manuales))
        else:
            print("AVISO: falta el manual base en data/idiomas/%s/%s/%s"
                  % (IDIOMA_BASE, NOMBRE_CARPETA_DOCS, NOMBRE_MANUAL))

        # Y junto al manual, las novedades.  No se copia el NOVEDADES.md de la
        # raíz tal cual: ese empieza con unas notas que explican de dónde saca
        # el empaquetador las notas de la actualización y cómo hay que escribir
        # cada apartado, y eso no le interesa a quien abre las novedades para
        # ver qué ha cambiado.  Se copia desde la primera versión escrita, con
        # una cabecera propia delante.
        #
        # Se genera aquí y no se guarda en «data/idiomas» del proyecto a
        # propósito: ejecutando desde el código fuente se abre el NOVEDADES.md
        # de la raíz, que es el que se está escribiendo; una copia guardada en
        # docs sería siempre la de la compilación anterior.
        import empaquetar

        publicas = empaquetar.novedades_publicas()
        if publicas:
            docs = destino / "idiomas" / IDIOMA_BASE / NOMBRE_CARPETA_DOCS
            docs.mkdir(parents=True, exist_ok=True)
            (docs / NOMBRE_NOVEDADES).write_text(publicas, encoding="utf-8")
            versiones = publicas.count("\n## ")
            print("Novedades incluidas: %d versiones en data/idiomas/%s/%s/%s"
                  % (versiones, IDIOMA_BASE, NOMBRE_CARPETA_DOCS, NOMBRE_NOVEDADES))
        else:
            print("AVISO: NOVEDADES.md no tiene ningún apartado «## <versión>»,")
            print("       así que el programa saldrá sin novedades que enseñar.")

    # Tesseract portable: es lo que permite leer un PDF escaneado sin que el
    # usuario tenga que instalar nada aparte.  Son unos noventa megas, y van
    # dentro a propósito: pedirle a alguien que instale otro programa para
    # poder leer un documento es justo lo que este no quiere hacer.
    # Se prepara con «python herramientas/tesseract_portable.py».
    tesseract = RAIZ / "data" / "tesseract"
    if (tesseract / "tesseract.exe").is_file():
        shutil.copytree(tesseract, destino / "tesseract")
        megas = sum(a.stat().st_size for a in (destino / "tesseract").rglob("*")
                    if a.is_file()) / 1048576
        idiomas_ocr = len(list((destino / "tesseract" / "tessdata").glob("*.traineddata")))
        print("Tesseract portable incluido: %.0f MB, %d idiomas" % (megas, idiomas_ocr))
    else:
        print("AVISO: no hay Tesseract portable en %s" % tesseract)
        print("       Prepáralo con: python herramientas/tesseract_portable.py")
        print("       Sin él, los PDF escaneados solo se podrán leer con IA o con Windows.")

    # 7-Zip portable. Son dos megas y medio y quitan de en medio el único caso
    # en el que el programa tenía que decirle a alguien «instala otra cosa»: un
    # cómic en RAR, o partido en volúmenes, en un equipo pelado. El «tar» que
    # trae Windows saca la mitad de un RAR partido y dice que ha terminado.
    binarios = RAIZ / "data" / "bin"
    if (binarios / "7z.exe").is_file():
        shutil.copytree(binarios, destino / "bin")
        megas = sum(a.stat().st_size for a in (destino / "bin").rglob("*")
                    if a.is_file()) / 1048576
        print("7-Zip portable incluido: %.1f MB" % megas)
    else:
        print("AVISO: no hay 7-Zip portable en %s" % binarios)
        print("       Prepáralo con: python herramientas/siete_zip_portable.py")
        print("       Sin él, los cómics en RAR dependen de lo que tenga cada equipo.")

    print("Carpeta «data» limpia preparada en %s" % destino)
    return destino


def paquetes_de_voz_incluidos() -> list[tuple[str, str]]:
    """Los paquetes de motor de voz que se reparten con el programa.

    Van al lado del ejecutable, en «plugins_voz», que es exactamente donde la
    ayuda de «Agregar motor de voz» dice que están.  Sin esto, la versión
    compilada no traía ninguno y esa ayuda mandaba a una carpeta vacía.

    Se copian los archivos de paquete y nada más.  El código con el que se arman
    vive en la misma carpeta, pero eso es para quien construya paquetes, no para
    quien lee libros.
    """
    # Para repartir se compila sin ellos: son casi un giga y quien instale el
    # programa no tiene por qué bajárselos, ni volver a bajárselos en cada
    # actualización.  Los que quiera se instalan luego desde el propio programa.
    if os.environ.get("VISOR_SIN_PAQUETES_VOZ"):
        print("Motores de voz: los paquetes NO se incluyen (compilación para "
              "repartir)")
        print("   Lo que necesitan de Python sí va dentro, para que un motor "
              "instalado después funcione.")
        return []
    carpeta = RAIZ / "plugins_voz"
    paquetes = sorted(carpeta.glob("*.motorvoz")) if carpeta.is_dir() else []
    if not paquetes:
        print("AVISO: no hay paquetes de motor de voz en %s" % carpeta)
        print("       Prepáralos con: python plugins_voz/crear_paquetes.py")
        print("       Sin ellos, la versión compilada solo tendrá la voz de Windows.")
        return []
    megas = sum(uno.stat().st_size for uno in paquetes) / 1048576
    print("Motores de voz: %d paquetes incluidos, %.1f MB"
          % (len(paquetes), megas))
    return [(str(uno), "plugins_voz/" + uno.name) for uno in paquetes]


def archivos_incluidos() -> list[tuple[str, str]]:
    """Lista de archivos y carpetas que se copian junto al ejecutable."""
    incluidos: list[tuple[str, str]] = list(localizar_runtimes())
    incluidos.append((str(preparar_data_limpia()), "data"))
    incluidos.extend(paquetes_de_voz_incluidos())
    return incluidos


#: Módulos que cx_Freeze podría no detectar por sí solo.
def modulos_de_los_motores_de_voz() -> list:
    """Lo que piden los paquetes de voz de ``plugins_voz``.

    Cada paquete lleva en su manifiesto la lista de módulos de Python que
    necesita, sacada de su propio código al armarlo. Aquí se leen todos y se
    juntan.

    Hace falta porque un motor de voz **se carga en marcha**, desde un archivo
    que está fuera del programa: el analizador de cx_Freeze no lo mira y no
    incluye lo que use. El síntoma es de los peores: en desarrollo funciona todo
    y en el ejecutable el motor arranca y dice que le falta un módulo.

    Si no hay paquetes o alguno no se deja leer, se sigue: compilar el programa
    no puede depender de que estén ahí.
    """
    import importlib.util
    import json
    import zipfile

    carpeta = RAIZ / "plugins_voz"
    if not carpeta.is_dir():
        return []
    pedidos: dict = {}
    for paquete in sorted(carpeta.glob("*.motorvoz")):
        try:
            with zipfile.ZipFile(paquete) as archivo:
                datos = json.loads(archivo.read("motor.json").decode("utf-8"))
        except Exception as error:
            print("Aviso: no se ha podido leer %s (%s)" % (paquete.name, error))
            continue
        for uno in datos.get("necesita", []):
            pedidos.setdefault(str(uno), paquete.stem)

    # Solo lo estándar.  Lo de terceros el paquete lo trae dentro, así que no
    # hace falta, y pedirlo es peligroso: cx_Freeze sigue las importaciones de
    # lo que se le pide y se para en la primera que no resuelva.  El programa no
    # se puede quedar sin compilar porque un motor mencione algo raro.
    quedan = [nombre for nombre in sorted(pedidos) if _es_de_python(nombre)]
    fuera = [nombre for nombre in sorted(pedidos) if nombre not in quedan]
    if fuera:
        print("Motores de voz: %d módulos que trae el propio paquete" % len(fuera))

    # De las dos formas.  cx_Freeze incluye un paquete entero si se le pide en
    # «packages» y un módulo suelto si se le pide en «includes», y no le valen
    # el uno por el otro: pedir «email.message» como paquete no incluye nada y
    # no avisa.  Así que la raíz va de paquete —«email» entero son cuarenta
    # archivos y evita adivinar cuáles hacen falta— y el nombre completo va
    # además de módulo.
    raices = sorted({nombre.split(".")[0] for nombre in quedan})
    if quedan:
        print("Motores de voz: %d módulos de Python en %d paquetes"
              % (len(quedan), len(raices)))
    return raices, quedan


def _es_de_python(nombre: str) -> bool:
    """Si el módulo es de los que Python trae de serie.

    Se mira dónde vive: los de serie están dentro de la carpeta de la biblioteca
    estándar o son parte del propio intérprete.  Comparar con una lista de
    nombres escrita a mano envejecería mal, y aquí se equivocaría en el lado
    peor: dejando fuera algo que sí hace falta.
    """
    import importlib.util
    import pathlib
    import sys
    import sysconfig

    raiz = nombre.split(".")[0]
    if raiz in sys.builtin_module_names:
        return True
    try:
        ficha = importlib.util.find_spec(raiz)
    except (ImportError, ValueError, AttributeError):
        return False
    if ficha is None:
        return False
    if ficha.origin in ("built-in", "frozen"):
        return True
    if not ficha.origin:
        return False
    donde = pathlib.Path(ficha.origin).resolve()
    estandar = pathlib.Path(sysconfig.get_paths()["stdlib"]).resolve()
    try:
        donde.relative_to(estandar)
    except ValueError:
        return False
    # Dentro de la biblioteca estándar está «site-packages», que es justo lo
    # que no lo es.
    return "site-packages" not in donde.parts


#: Lo que hace falta para los motores de voz instalables, en las dos listas que
#: cx_Freeze distingue: paquetes enteros y módulos sueltos.
PAQUETES_DE_LOS_MOTORES, MODULOS_DE_LOS_MOTORES = modulos_de_los_motores_de_voz()


MODULOS_EXTRA = [
    "wx",
    "wx.adv",
    "wx.html2",
    "wx.lib.newevent",
    "wx_accessible_webview",
    "lxml",
    "lxml.etree",
    "lxml._elementpath",
    "nucleo",
    "formatos",
    "interfaz",
    # Correo guardado y páginas «.mht»: los dos son mensajes MIME, y quien los
    # descompone es la biblioteca estándar.
    "email",
    # Pegar los trozos de audio para poner las marcas de capítulo y para
    # sincronizar el DAISY frase a frase.
    "wave",
    # La bibliografía en hoja de cálculo, que es como mucha gente lleva la
    # lista de lecturas de una asignatura.
    "csv",
    # El índice de significados guarda sus listas de números como bloques de
    # bytes y no como listas de Python: con «array» ocupa diez veces menos, y
    # una biblioteca de trescientos libros cabe en memoria.
    "array",
    # Lectura de PDF y reconocimiento de páginas escaneadas.
    "pypdfium2",
    # Inspección del interior del PDF: cifrado, catálogo, estructura, fuentes,
    # formularios y firmas.  Es lo que permite distinguir el PDF que solo
    # prohíbe imprimir —y se abre— del que pide contraseña de verdad, y lo que
    # alimenta el informe de accesibilidad.
    "pypdf",
    # Medida de la maquetación de los PDF que no traen estructura: el tamaño de
    # letra de cada palabra, del que salen los encabezados, y la geometría de
    # las tablas.  Arrastra pdfminer.six, que es quien hace el trabajo.
    "pdfplumber",
    "pdfminer",
    # pdfminer detecta con esto la codificación de los textos del PDF y descifra
    # los archivos protegidos.  Son dependencias suyas y no se nombran solas.
    "charset_normalizer",
    "striprtf",
    "winsdk",
    # Preparación de la imagen antes del OCR.
    "PIL",
    # Reproducción de las grabaciones DAISY.  Sus DLL van dentro del propio
    # paquete, así que basta con nombrarlo para que cx_Freeze se las lleve.
    "basskit",
    "sonidos",
    "encodings.idna",
    # Peticiones HTTP a la IA (Gemini y modelo local).  Se hacen con la
    # biblioteca estándar, pero cx_Freeze no siempre arrastra el módulo de
    # cifrado que necesita HTTPS si no se nombra.
    "urllib.request",
    "ssl",
    "http.client",
    # Voz del sistema (SAPI 5) para la lectura en voz alta y para grabar el
    # documento en archivos de audio.  «pythoncom» va nombrado aparte porque la
    # exportación a audio inicializa COM en su propio hilo.
    "win32com",
    "win32com.client",
    "pythoncom",
    # Comprobación de la firma de las actualizaciones.  Solo se usa si hay una
    # clave pública puesta en «version.py», pero si falta cuando hace falta, el
    # programa rechazaría todas las actualizaciones sin saber por qué.
    "cryptography",
    "cryptography.hazmat.primitives.asymmetric.ed25519",
]

#: Módulos grandes que no se usan y que no tiene sentido empaquetar.
MODULOS_EXCLUIDOS = [
    "tkinter",
    "unittest",
    # La batería de pruebas y sus dependencias no pintan nada en el ejecutable.
    "pytest",
    "_pytest",
    "pluggy",
    "pydoc_data",
    "test",
    "distutils",
    "setuptools",
    "pip",
    "numpy",
    "PIL",
    "matplotlib",
]

opciones_construccion = {
    # A lo del programa se le suma lo que pidan los paquetes de voz, que se
    # cargan en marcha y por eso no los ve el analizador.
    "packages": MODULOS_EXTRA + PAQUETES_DE_LOS_MOTORES,
    # «faulthandler» se importa dentro de una función —solo se usa al arrancar—
    # y el analizador no lo ve. Sin él, una caída dentro de una biblioteca que
    # no es de Python no dejaría ni una línea escrita.
    # «sqlite3» se pone a mano por lo mismo: la biblioteca lo carga al abrirse,
    # y sin él no se podría ni guardar la biblioteca ni leer la de calibre.
    "includes": MODULOS_DE_LOS_MOTORES + ["faulthandler", "sqlite3"],
    "excludes": MODULOS_EXCLUIDOS,
    "include_files": archivos_incluidos(),
    "path": [str(CARPETA_FUENTE)] + sys.path,
    "build_exe": str(RAIZ / "build" / NOMBRE),
    "optimize": 1,
    "include_msvcr": True,
    "zip_include_packages": [],
    "silent_level": 1,
}

def base_grafica() -> str | None:
    """Nombre de la base de cx_Freeze para un programa sin ventana de consola.

    cx_Freeze cambió el nombre de ``Win32GUI`` a ``gui`` en su versión 7, así
    que se prueban los dos y se usa el que acepte la versión instalada.
    """
    if sys.platform != "win32":
        return None
    from cx_Freeze.executable import Executable as _Ejecutable

    for candidato in ("gui", "Win32GUI"):
        try:
            _Ejecutable(script=__file__, base=candidato)
            return candidato
        except Exception:
            continue
    print("AVISO: no se ha podido elegir una base gráfica; se usará la de consola.")
    return None


ejecutable = Executable(
    script=str(CARPETA_FUENTE / "main.py"),
    base=base_grafica(),
    target_name=NOMBRE + ".exe",
    icon=str(RAIZ / "data" / "icono.ico") if (RAIZ / "data" / "icono.ico").is_file() else None,
    copyright="Visor Universal",
)

setup(
    name="Visor Universal",
    version=VERSION,
    description="Lector accesible de libros electrónicos EPUB",
    options={"build_exe": opciones_construccion},
    executables=[ejecutable],
)
