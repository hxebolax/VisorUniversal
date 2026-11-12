# -*- coding: utf-8 -*-
"""Punto de entrada del programa.

Orden de arranque, pensado para que cualquier fallo quede registrado desde el
primer instante:

1. Se crea la carpeta ``data`` con todas sus subcarpetas.
2. Se pone en marcha el sistema de registro (todavía con el nivel por
   omisión, porque aún no se ha leído la configuración).
3. Se cargan las preferencias y se ajusta el nivel de registro definitivo.
4. Se registran los analizadores de formato disponibles.
5. Se arranca la interfaz gráfica.

Si algo falla antes de que exista la ventana, se muestra un mensaje claro y
se indica dónde está el archivo de registro.
"""

from __future__ import annotations

from nucleo.idioma import _
import argparse
import os
import sys
from pathlib import Path


def asegurar_las_salidas() -> None:
    """Deja los descriptores de salida y de errores apuntando a algún sitio.

    Compilado como programa de ventana no hay consola, y en Windows eso deja
    los descriptores 1 y 2 sin nada detrás.  Python lo lleva bien: pone
    ``sys.stdout`` y ``sys.stderr`` a ``None``.  Una biblioteca escrita en C no:
    escribe en el 2 sus avisos y sus aserciones sin preguntar, y hacerlo sobre
    un descriptor que no vale tumba el proceso entero desde uno de sus hilos
    —violación de acceso, sin excepción que capturar y sin una línea en el
    registro—.

    Así que se les pone ``nul`` detrás.  Lo que escriban se pierde, que es lo
    que pasaría de todos modos, pero ya no se lleva el programa.  Esto tiene
    que ir **lo primero**, antes de cargar nada que traiga bibliotecas.
    """
    for numero in (1, 2):
        try:
            os.fstat(numero)
            continue                      # ese ya vale
        except OSError:
            pass
        try:
            hueco = os.open(os.devnull, os.O_RDWR)
        except OSError:
            continue                      # sin «nul» no hay nada que hacer
        if hueco == numero:
            continue
        try:
            os.dup2(hueco, numero)
        finally:
            os.close(hueco)


asegurar_las_salidas()

#: El archivo abierto donde «faulthandler» escribirá si el proceso se cae.  Se
#: guarda aquí para que no lo cierre el recolector: si se cerrara, el manejador
#: escribiría en un archivo que ya no existe justo cuando más falta hace.
_donde_apuntar_la_caida = None

#: Códigos de excepción de Windows que el sistema resuelve solo y que no son una
#: caída: si una sesión que se cierra bien solo tiene de estos, su archivo de
#: «caída» se borra.  0x8001010d es RPC_E_CANTCALLOUT_ININPUTSYNCCALL.
EXCEPCIONES_RESUELTAS = frozenset(("0x8001010d",))


def vigilar_las_caidas(carpeta) -> None:
    """Engancha ``faulthandler`` para que una caída nativa deje rastro.

    Las bibliotecas que traen los motores de voz, los descodificadores de sonido
    o los lectores de documentos no son de Python, y cuando una de ellas se
    estrella se lleva el proceso entero: no hay excepción, no hay traza y en el
    registro no queda ni una línea, porque no da tiempo a escribirla.

    Esto no lo evita —no se puede— pero deja escrito en qué estaba cada hilo en
    ese momento, que es la diferencia entre poder arreglarlo y no.
    """
    global _donde_apuntar_la_caida
    import faulthandler

    if faulthandler.is_enabled():
        return
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        import datetime

        cuando = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        _donde_apuntar_la_caida = (carpeta / ("caida_%s.txt" % cuando)).open(
            "w", encoding="utf-8", buffering=1)
        faulthandler.enable(_donde_apuntar_la_caida, all_threads=True)
    except Exception:
        # Sin esto se sigue igual: es una ayuda para depurar, no un requisito.
        _donde_apuntar_la_caida = None

# Al ejecutar «python src/main.py» la carpeta «src» ya está en la ruta de
# búsqueda; al ejecutarlo compilado o como módulo, conviene asegurarlo.
_CARPETA = Path(__file__).resolve().parent
if str(_CARPETA) not in sys.path:
    sys.path.insert(0, str(_CARPETA))

# El nombre y la versión viven en su propio archivo (``src/version.py``) para
# poder cambiarlos en un solo sitio: los leen también el diálogo «Acerca de»,
# la pantalla de bienvenida y el guion de compilación.
from version import NOMBRE, VERSION


def analizar_argumentos() -> argparse.Namespace:
    """Interpreta los argumentos de la línea de órdenes."""
    analizador = argparse.ArgumentParser(
        prog=NOMBRE,
        description=_("Visor accesible de documentos: libros, PDF, Word y DAISY."),
    )
    analizador.add_argument(
        "archivo", nargs="?", default=None,
        help=_("Documento que se abrirá al arrancar (opcional)."),
    )
    analizador.add_argument(
        "--nivel-registro", default=None, choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help=_("Fuerza el nivel de detalle del registro solo para esta ejecución."),
    )
    analizador.add_argument(
        "--comprobar-voz", nargs="?", const="", default=None, metavar="MOTOR",
        help=_("Arranca, dice una frase con el motor elegido —o con el que se "
               "indique—, lo apunta en el registro y se cierra. Sirve para "
               "reproducir fallos que solo salen con el programa compilado."),
    )
    return analizador.parse_args()


def main() -> int:
    """Arranca la aplicación.  Devuelve el código de salida del proceso."""
    from nucleo import rutas

    rutas.preparar_estructura()
    vigilar_las_caidas(rutas.subcarpeta("logs"))

    from nucleo import registro as modulo_registro

    argumentos = analizar_argumentos()
    # Primer arranque del registro con el nivel por omisión: hace falta antes
    # de leer la configuración, para que un fallo al leerla quede anotado.
    modulo_registro.iniciar(argumentos.nivel_registro or "INFO", VERSION)
    modulo_registro.conectar_registro_lxml()
    log = modulo_registro.obtener_registro(__name__)

    try:
        from nucleo.configuracion import Configuracion

        configuracion = Configuracion()
        if argumentos.nivel_registro is None:
            modulo_registro.cambiar_nivel(str(configuracion.obtener("nivel_registro")))

        # El idioma se elige **antes** de importar la interfaz: las tablas de
        # atajos y los nombres de los prompts se construyen al importar sus
        # módulos, y para entonces la traducción tiene que estar puesta.
        from nucleo import idioma

        activo = idioma.instalar(str(configuracion.obtener("idioma", "auto")))
        log.info("Idioma de la interfaz: %s", activo)

        # La sincronización va **antes** de abrir nada: si en otro equipo se
        # leyó ayer, hay que traerlo ya, o al restaurar los documentos abiertos
        # se colocaría el cursor donde estaba aquí y se perdería lo de allí.
        if configuracion.obtener("sincronizacion_automatica", True):
            from nucleo import sincronizacion

            resultado = sincronizacion.sincronizar(configuracion)
            if resultado.libros or resultado.traidos:
                log.info("Al arrancar: %s", resultado.frase())

        eliminados = rutas.limpiar_temporales()
        if eliminados:
            log.debug("Archivos temporales eliminados: %d", eliminados)

        # Cada analizador se registra al importarse.  Aquí están todos los
        # formatos que abre el programa; añadir uno es escribir su módulo y
        # ponerlo en esta lista.
        from formatos import epub          # noqa: F401  EPUB 2 y 3
        from formatos import texto         # noqa: F401  TXT, Markdown, HTML, FB2
        from formatos import ofimatica     # noqa: F401  DOCX y ODT
        from formatos import rtf           # noqa: F401  Texto enriquecido
        from formatos import comic         # noqa: F401  CBZ y CBT
        from formatos import pdf           # noqa: F401  PDF, con OCR si hace falta
        from formatos import daisy         # noqa: F401  DAISY 2.02 y 3
        from formatos import kindle        # noqa: F401  KFX, AZW3 y MOBI
        from formatos import correo        # noqa: F401  EML, MHT y MHTML
        from formatos import chm           # noqa: F401  Ayuda de Windows
        from formatos import hlp           # noqa: F401  Ayuda anterior al CHM
        from formatos import djvu          # noqa: F401  Escaneos de biblioteca
        from formatos import presentaciones  # noqa: F401  PPTX y ODP
        from formatos import hojas         # noqa: F401  XLSX y ODS
        from formatos import musicaxml     # noqa: F401  Partituras
        from formatos import ofimatica_antigua  # noqa: F401  DOC, XLS y PPT
        from formatos import braille       # noqa: F401  BRA (Braille ASCII español)

        # La integración con el explorador guarda la ruta del programa, así que
        # al mover la carpeta —cosa normal en un programa portátil— apuntaría a
        # donde ya no hay nada.  Se comprueba al arrancar y se rehace sola.
        from nucleo import integracion

        formatos_integrados = configuracion.obtener("integracion_formatos", []) or []
        if formatos_integrados and integracion.disponible():
            integracion.revisar(
                formatos_integrados,
                bool(configuracion.obtener("integracion_menu", True)),
                bool(configuracion.obtener("integracion_abrir_con", True)))

        # Antes de la interfaz, porque la interfaz prepara la voz del sistema y
        # eso puede meter en el proceso la copia que otro programa tenga de las
        # mismas bibliotecas.  Quien llega primero manda, y tiene que ser el
        # motor instalado.
        try:
            from nucleo import motores_voz

            motores_voz.precargar_bibliotecas()
        except Exception:
            # Si esto falla se sigue igual: es una precaución, no un requisito.
            log.debug("Al precargar las bibliotecas de los motores",
                      exc_info=True)

        from interfaz.app import Aplicacion

        try:
            aplicacion = Aplicacion(configuracion, VERSION, argumentos.archivo)
            if argumentos.comprobar_voz is not None:
                programar_la_comprobacion(aplicacion, argumentos.comprobar_voz)
        except SystemExit:
            # wxPython termina de esta forma cuando la preparación de la
            # aplicación decide no seguir, que es lo que ocurre cuando el
            # programa ya estaba abierto: esa copia le pasa el libro a la que
            # ya existe y se retira.  No es un error, así que se sale con éxito.
            log.info("Esta copia termina porque el programa ya estaba abierto")
            return 0
        aplicacion.MainLoop()
        configuracion.guardar()
        recoger_el_vigilante()
        return 0
    except Exception as error:
        log.critical("Fallo irrecuperable durante el arranque", exc_info=True)
        _avisar_del_fallo(error)
        return 1


def recoger_el_vigilante() -> None:
    """Se lleva el archivo del vigilante si no hubo nada que contar.

    Cada sesión abre uno, y en la inmensa mayoría no pasa nada: dejarlos todos
    llenaría la carpeta de archivos vacíos y el que importe se perdería entre
    ellos.  Así solo quedan los de las sesiones en las que algo se cayó.
    """
    global _donde_apuntar_la_caida
    from nucleo.registro import obtener_registro

    log = obtener_registro(__name__)

    if _donde_apuntar_la_caida is None:
        return
    try:
        import faulthandler

        faulthandler.disable()
        donde = Path(_donde_apuntar_la_caida.name)
        _donde_apuntar_la_caida.close()
        _donde_apuntar_la_caida = None
        if not donde.is_file():
            return
        if donde.stat().st_size == 0:
            donde.unlink()
            return
        # Si se ha llegado aquí el programa se está cerrando bien, así que lo
        # apuntado no fue una caída.  «faulthandler» anota toda excepción de
        # Windows, también las que el sistema resuelve solo; la más habitual
        # es 0x8001010d (RPC_E_CANTCALLOUT_ININPUTSYNCCALL), una llamada de
        # COM del lector de pantalla en mitad de un mensaje de entrada.  Si
        # solo hay de esas, se deja una línea en la sesión y el archivo se va:
        # un archivo de «caída» en cada sesión acaba haciendo que nadie mire el
        # día que hay una de verdad.
        import re

        # Se miran **todas** las anotadas: una caída de verdad, como «access
        # violation», no lleva código, y basta una para conservar el archivo.
        anotadas = re.findall(r"Windows fatal exception: ([^\r\n]+)",
                              donde.read_text(encoding="utf-8", errors="replace"))
        codigos = [a.strip()[5:].lower() for a in anotadas if a.strip().startswith("code ")]
        if (anotadas and len(codigos) == len(anotadas)
                and all(codigo in EXCEPCIONES_RESUELTAS for codigo in codigos)):
            log.info("Windows anotó %d excepciones que resolvió por su cuenta (%s); "
                     "no hubo ninguna caída", len(codigos), ", ".join(sorted(set(codigos))))
            donde.unlink()
    except Exception:
        log.debug("Al recoger el archivo del vigilante", exc_info=True)


def programar_la_comprobacion(aplicacion, cual: str) -> None:
    """Hace que el programa se diga una frase a sí mismo y se cierre.

    Se espera un poco antes de empezar para que la ventana esté hecha del todo
    y el lector de pantalla la haya leído: eso es parte de lo que se quiere
    reproducir, no un adorno.
    """
    import wx

    def comprobar():
        from nucleo import motores_voz

        registro = __import__("logging").getLogger("visor.comprobacion")
        motor = None
        try:
            elegido = cual or str(
                aplicacion.configuracion.obtener("voz_motor", motores_voz.SAPI5))
            registro.info("Comprobando la voz con el motor «%s»", elegido)
            ajustes = dict(
                aplicacion.configuracion.obtener("voz_ajustes_motores", {}) or {})
            motor, aviso = motores_voz.crear(elegido, ajustes.get(elegido, {}))
            registro.info("Motor creado. Aviso: %r. Voces: %d",
                          aviso, len(motor.voces()))
            problema = getattr(motor, "problema", None)
            if callable(problema):
                registro.info("El motor dice: %r", problema())
            motor.establecer_velocidad(0)
            motor.establecer_volumen(80)
            registro.info("Pidiendo la frase...")
            dicho = motor.decir("Esto es una comprobación de la voz.")
            registro.info("Ha aceptado la frase: %s", dicho)
            import time

            esperando = time.perf_counter()
            while motor.hablando and time.perf_counter() - esperando < 20:
                time.sleep(0.05)
            registro.info("Ha terminado de sonar en %.2f s",
                          time.perf_counter() - esperando)
        except Exception:
            registro.error("La comprobación ha fallado", exc_info=True)
        finally:
            if motor is not None:
                cerrar = getattr(motor, "cerrar", None)
                if callable(cerrar):
                    try:
                        cerrar()
                    except Exception:
                        registro.debug("Al cerrar el motor", exc_info=True)
            registro.info("COMPROBACIÓN TERMINADA SIN CAERSE")

            def cerrar_todo():
                # Por el camino de siempre —«Close»— y no destruyendo a lo
                # bruto: una ventana destruida mientras el bucle la está usando
                # se lleva el proceso, y sería un fallo de esta comprobación
                # haciéndose pasar por uno del motor.
                for ventana in list(wx.GetTopLevelWindows()):
                    try:
                        ventana.Close(True)
                    except Exception:
                        registro.debug("Al cerrar una ventana", exc_info=True)

            wx.CallAfter(cerrar_todo)

    wx.CallLater(4000, comprobar)


def _avisar_del_fallo(error: BaseException) -> None:
    """Informa al usuario de un fallo de arranque de la forma más visible posible."""
    from nucleo.registro import ruta_archivo_registro

    destino = ruta_archivo_registro()
    mensaje = _(
        "%s no ha podido arrancar.\n\n"
        "%s: %s\n\n"
        "Encontrarás los detalles en el registro:\n%s"
    ) % (NOMBRE, type(error).__name__, error, destino or _("(sin registro)"))
    try:
        import wx

        aplicacion = wx.App(False)
        wx.MessageBox(mensaje, _("Error de arranque"), wx.OK | wx.ICON_ERROR)
        aplicacion.Destroy()
    except Exception:
        print(mensaje, file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
