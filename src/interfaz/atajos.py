# -*- coding: utf-8 -*-
"""Tabla de atajos de teclado.

Se separan en dos grupos:

* **Teclas de navegación rápida**: una sola letra o número, sin modificadores
  (con ``Mayús`` para ir hacia atrás).  Reproducen las órdenes a las que están
  acostumbrados los usuarios de lectores de pantalla en las páginas web:
  ``H`` para encabezados, ``T`` para tablas, ``L`` para listas, etc.  Como el
  texto es de solo lectura, escribir esas letras no interfiere con nada.

* **Órdenes de menú**: combinaciones con ``Control``, ``Alt`` o teclas de
  función, declaradas junto a cada opción de menú.

Este módulo contiene únicamente los datos.  Quien los interpreta es
:mod:`interfaz.ventana`.  Tenerlos aquí permite generar automáticamente el
cuadro de diálogo de atajos y la sección correspondiente del manual, sin
riesgo de que la documentación se quede desfasada.
"""

from __future__ import annotations

from typing import NamedTuple

from nucleo.idioma import _
from nucleo.navegacion import Objetivo


class AtajoNavegacion(NamedTuple):
    """Una tecla de navegación rápida.

    :param tecla: Carácter que hay que pulsar.
    :param objetivo: Tipo de elemento al que salta.
    :param nivel: Filtro de nivel, solo para encabezados (0 = cualquiera).
    :param descripcion: Texto que aparece en la ayuda.
    """

    tecla: str
    objetivo: Objetivo
    nivel: int
    descripcion: str


#: Teclas de navegación rápida.  Cada una funciona hacia delante tal cual y
#: hacia atrás combinada con «Mayús».
NAVEGACION: tuple[AtajoNavegacion, ...] = (
    AtajoNavegacion("H", Objetivo.ENCABEZADO, 0, _("Encabezado")),
    AtajoNavegacion("1", Objetivo.ENCABEZADO, 1, _("Encabezado de nivel 1")),
    AtajoNavegacion("2", Objetivo.ENCABEZADO, 2, _("Encabezado de nivel 2")),
    AtajoNavegacion("3", Objetivo.ENCABEZADO, 3, _("Encabezado de nivel 3")),
    AtajoNavegacion("4", Objetivo.ENCABEZADO, 4, _("Encabezado de nivel 4")),
    AtajoNavegacion("5", Objetivo.ENCABEZADO, 5, _("Encabezado de nivel 5")),
    AtajoNavegacion("6", Objetivo.ENCABEZADO, 6, _("Encabezado de nivel 6")),
    AtajoNavegacion("K", Objetivo.ENLACE, 0, _("Enlace")),
    AtajoNavegacion("G", Objetivo.IMAGEN, 0, _("Imagen")),
    AtajoNavegacion("F", Objetivo.FIGURA, 0, _("Figura")),
    AtajoNavegacion("T", Objetivo.TABLA, 0, _("Tabla")),
    AtajoNavegacion("L", Objetivo.LISTA, 0, _("Lista")),
    AtajoNavegacion("I", Objetivo.ELEMENTO_LISTA, 0, _("Elemento de lista")),
    AtajoNavegacion("S", Objetivo.SEPARADOR, 0, _("Separador")),
    AtajoNavegacion("P", Objetivo.PAGINA, 0, _("Página")),
    AtajoNavegacion("Q", Objetivo.CITA, 0, _("Cita")),
    # La «E» de ecuación: en un libro técnico saltar de fórmula en fórmula es
    # tan útil como saltar de encabezado en encabezado en uno normal.
    AtajoNavegacion("E", Objetivo.FORMULA, 0, _("Fórmula matemática")),
    # La «O» de «nota al pie»: la «N» ya es la nota que escribe el usuario, y
    # confundir las dos sería peor que una letra sin mnemotecnia perfecta.
    AtajoNavegacion("O", Objetivo.NOTA_PIE, 0, _("Llamada de nota al pie")),
    # La «X» del código no tiene mnemotecnia y no la busca: «C» es el capítulo,
    # «F» la figura, «P» la página, «S» el separador y «L» la lista.  De las
    # letras que quedaban libres, la X es la que en más programas significa
    # «esto es código», y una letra rara vale más que una mala.
    AtajoNavegacion("X", Objetivo.CODIGO, 0, _("Bloque de código")),
)

#: Tecla de navegación por secciones (capítulos del libro).  Todas las teclas
#: de esta zona son letras a propósito: los signos de puntuación cambian de
#: sitio con cada distribución de teclado y varios de ellos (los corchetes,
#: por ejemplo) solo se escriben con AltGr en el teclado español, combinación
#: que el programa nunca llega a ver como una pulsación simple.
SECCION_SIGUIENTE = "C"      # capítulo; con Mayús, el anterior

#: Teclas para moverse respecto al contenedor (lista o tabla) actual.
CONTENEDOR_INICIO = "Z"      # con Mayús
CONTENEDOR_FIN = "Z"         # sin Mayús

#: Teclas de marcadores y notas.
MARCADOR_SIGUIENTE = "B"
NOTA_SIGUIENTE = "N"

#: Tecla que describe con inteligencia artificial la imagen del cursor.
DESCRIBIR_IMAGEN = "A"

#: Tecla que define la palabra del cursor.  La «V» de «ver la definición»:
#: la «D» de diccionario y la «P» de palabra estaban cogidas, y las letras que
#: quedan libres son pocas.
DEFINIR_PALABRA = "V"

#: Tecla que anuncia dónde se está leyendo.
DONDE_ESTOY = "D"

#: Tecla que repite el último anuncio.
REPETIR_ANUNCIO = "R"


class AtajoOrden(NamedTuple):
    """Una orden de menú con su combinación de teclas.

    :param atajo_alterno: Segunda combinación que hace lo mismo.  Se usa para
                          el manual: la tecla F1 es la costumbre universal para
                          la ayuda, pero hay equipos donde algún otro programa
                          la captura y nunca llega a la aplicación, así que
                          conviene ofrecer una alternativa.
    """

    identificador: str
    etiqueta: str
    atajo: str
    categoria: str
    descripcion: str
    atajo_alterno: str = ""


#: Órdenes de menú, con la combinación de teclas que las activa.
ORDENES: tuple[AtajoOrden, ...] = (
    # --- Archivo ------------------------------------------------------------
    AtajoOrden("abrir", _("&Abrir..."), "Ctrl+O", _("Archivo"),
               _("Abre un documento del disco.")),
    AtajoOrden("abrir_direccion", _("Abrir una dirección de &internet..."),
               "Ctrl+Shift+U", _("Archivo"),
               _("Pega una dirección y el programa trae la página, le quita los menús "
                 "y los anuncios y la abre para leerla. Evita el rodeo de guardarla "
                 "con el navegador. La página queda guardada en el disco, así que se "
                 "puede volver a ella sin conexión.")),
    AtajoOrden("recientes", _("&Recientes"), "", _("Archivo"),
               _("Lista de los últimos documentos abiertos.")),
    AtajoOrden("cerrar_libro", _("&Cerrar"), "Ctrl+W", _("Archivo"),
               _("Cierra el documento actual guardando la posición de lectura. Con las "
                 "pestañas activadas cierra la pestaña, y si es la última se queda "
                 "vacía en lugar de desaparecer.")),
    AtajoOrden("exportar_texto", _("Exportar a &texto (.txt)..."), "Ctrl+E", _("Archivo"),
               _("Guarda el documento como texto plano, que abre cualquier programa.")),
    AtajoOrden("exportar_md", _("Exportar a &Markdown (.md)..."), "", _("Archivo"),
               _("Guarda el documento en Markdown, conservando encabezados y listas.")),
    AtajoOrden("exportar_html", _("Exportar a &página web (.html)..."), "", _("Archivo"),
               _("Guarda el documento como página web, para abrirlo en el navegador.")),
    AtajoOrden("exportar_epub", _("Exportar a &libro EPUB (.epub)..."), "", _("Archivo"),
               _("Guarda el documento como libro electrónico, para leerlo en el móvil o "
                 "en un lector de libros.")),
    AtajoOrden("exportar_braille", _("Exportar a &braille (.brf)..."), "", _("Archivo"),
               _("Transcribe el documento a braille de grado 1 y lo guarda en un archivo "
                 "BRF, que es lo que se lleva a una impresora braille o a un anotador.")),
    AtajoOrden("exportar_pef", _("Exportar a braille en &XML (.pef)..."), "", _("Archivo"),
               _("El mismo braille que el BRF, pero en el formato PEF, que lleva dentro "
                 "el título y el autor y es lo que se intercambian las bibliotecas y las "
                 "imprentas braille de Europa.")),
    AtajoOrden("exportar_daisy", _("Exportar a libro &DAISY..."), "", _("Archivo"),
               _("Escribe una carpeta con el libro en DAISY 3, el formato de las "
                 "bibliotecas para personas ciegas. Con el texto solo, o con el texto y "
                 "la voz sincronizados frase a frase.")),
    AtajoOrden("exportar_audio", _("Exportar a &audio (MP3)..."), "", _("Archivo"),
               _("Convierte el documento en archivos de sonido, uno por capítulo o uno solo, "
                 "para escucharlo en el móvil o en el coche.")),
    AtajoOrden("salir", _("&Salir"), "Alt+F4", _("Archivo"),
               _("Cierra la aplicación.")),
    # --- Pestañas y zonas ---------------------------------------------------
    # Las pestañas y el árbol de contenido son opcionales, pero sus órdenes
    # están siempre en la tabla: así aparecen en la ayuda de atajos aunque
    # estén apagadas, y quien las lea sabe que existen y dónde encenderlas.
    AtajoOrden("nueva_pestana", _("&Nueva pestaña..."), "Ctrl+N", _("Pestañas"),
               _("Abre un documento en una pestaña nueva, sin cerrar el que estés leyendo.")),
    AtajoOrden("pestana_siguiente", _("Pestaña &siguiente"), "Ctrl+Tabulador", _("Pestañas"),
               _("Pasa a la pestaña siguiente; desde la última vuelve a la primera.")),
    AtajoOrden("pestana_anterior", _("Pestaña &anterior"), "Ctrl+Mayús+Tabulador",
               _("Pestañas"),
               _("Pasa a la pestaña anterior; desde la primera vuelve a la última.")),
    AtajoOrden("lista_pestanas", _("&Lista de pestañas..."), "Ctrl+F6", _("Pestañas"),
               _("Enseña los documentos abiertos para saltar al que quieras.")),
    AtajoOrden("zona_siguiente", _("Zona siguien&te"), "F6", _("Pestañas"),
               _("Va a la zona siguiente de la ventana: el árbol de contenido, las "
                 "pestañas y el texto del documento.")),
    AtajoOrden("zona_anterior", _("&Zona anterior"), "Mayús+F6", _("Pestañas"),
               _("Va a la zona anterior de la ventana.")),
    AtajoOrden("arbol_contenido", _("Árbol de &contenido"), "Ctrl+Alt+B", _("Pestañas"),
               _("Enseña o esconde el árbol con el índice y los elementos del documento, "
                 "a la izquierda del texto.")),
    # --- Ir a ---------------------------------------------------------------
    AtajoOrden("buscar", _("&Buscar..."), "Ctrl+F", _("Ir a"),
               _("Abre el cuadro de búsqueda.")),
    AtajoOrden("buscar_siguiente", _("Buscar &siguiente"), "F3", _("Ir a"),
               _("Repite la última búsqueda hacia delante.")),
    AtajoOrden("buscar_anterior", _("Buscar &anterior"), "Shift+F3", _("Ir a"),
               _("Repite la última búsqueda hacia atrás.")),
    AtajoOrden("ir_linea", _("Ir a la &línea..."), "Ctrl+G", _("Ir a"),
               _("Salta a un número de línea.")),
    AtajoOrden("ir_porcentaje", _("Ir al porcenta&je..."), "Ctrl+Shift+G", _("Ir a"),
               _("Salta a un punto del documento indicado en porcentaje.")),
    AtajoOrden("ir_pagina", _("Ir a la pá&gina..."), "Ctrl+P", _("Ir a"),
               _("Salta a un número de página, si el documento las tiene.")),
    AtajoOrden("ir_principio", _("Ir al &principio"), "Ctrl+Inicio", _("Ir a"),
               _("Salta al principio del documento.")),
    AtajoOrden("ir_final", _("Ir al &final"), "Ctrl+Fin", _("Ir a"),
               _("Salta al final del documento.")),
    AtajoOrden("atras", _("A&trás"), "Alt+Izquierda", _("Ir a"),
               _("Vuelve a la posición anterior.")),
    AtajoOrden("adelante", _("A&delante"), "Alt+Derecha", _("Ir a"),
               _("Avanza a la posición siguiente del historial.")),
    AtajoOrden("indice", _("Í&ndice del documento..."), "Ctrl+T", _("Ir a"),
               _("Abre el índice de contenidos.")),
    AtajoOrden("elementos", _("Lista de &elementos..."), "F7", _("Ir a"),
               _("Lista todos los encabezados, enlaces, imágenes y tablas.")),
    AtajoOrden("marcadores", _("&Marcadores y notas..."), "Ctrl+B", _("Ir a"),
               _("Abre la lista de marcadores y notas del documento.")),
    AtajoOrden("notas_al_pie", _("N&otas al pie..."), "Ctrl+Shift+N", _("Ir a"),
               _("Abre todas las notas al pie del libro, con su texto entero, "
                 "para leerlas de seguido, buscar en ellas, ir a donde se citan "
                 "o saltar a la nota.")),
    # --- Herramientas -------------------------------------------------------
    AtajoOrden("poner_marcador", _("Poner o quitar &marcador"), "Ctrl+M", _("Herramientas"),
               _("Coloca o quita un marcador en la posición actual.")),
    AtajoOrden("poner_nota", _("Poner o editar &nota..."), "Ctrl+Shift+M", _("Herramientas"),
               _("Escribe una nota en la posición actual.")),
    AtajoOrden("ver_imagen", _("&Ver imagen..."), "Ctrl+I", _("Herramientas"),
               _("Muestra la imagen que hay en la posición del cursor.")),
    AtajoOrden("ver_tabla", _("Ver &tabla..."), "Ctrl+Shift+T", _("Herramientas"),
               _("Muestra la tabla actual en una rejilla.")),
    AtajoOrden("ver_html", _("Ver el elemento como &HTML..."), "Ctrl+H", _("Herramientas"),
               _("Muestra la tabla, la lista o la cita del cursor en un visor web navegable.")),
    AtajoOrden("describir_imagen", _("&Describir la imagen con IA..."), "Ctrl+Alt+I", _("Herramientas"),
               _("Pide a la inteligencia artificial que describa la imagen del cursor.")),
    AtajoOrden("describir_todo", _("Describir &todas las imágenes..."), "Ctrl+Alt+D", _("Herramientas"),
               _("Describe de una vez todas las imágenes del documento que falten por describir.")),
    AtajoOrden("resaltar", _("&Resaltar lo seleccionado"), "Ctrl+Alt+E",
               _("Herramientas"),
               _("Guarda el texto seleccionado como pasaje resaltado. Sobre un resaltado "
                 "que ya existe, lo quita.")),
    AtajoOrden("biblioteca", _("&Biblioteca..."), "Ctrl+Shift+B", _("Archivo"),
               _("Todos tus libros en una lista, con por dónde va cada uno, y la "
                 "búsqueda de una frase en todos a la vez. Se pueden añadir carpetas "
                 "para que aparezcan también los libros que aún no has abierto.")),
    AtajoOrden("citar", _("Copiar con la &cita..."), "Ctrl+Shift+C", _("Herramientas"),
               _("Copia el pasaje seleccionado con su referencia bibliográfica ya hecha: "
                 "autor, título, editorial, año y página. En ISO 690, APA, MLA o en una "
                 "frase sencilla.")),
    AtajoOrden("resaltados", _("Lista d&e resaltados..."), "Ctrl+Alt+K", _("Herramientas"),
               _("Enseña todos los pasajes resaltados del documento para ir a ellos, "
                 "quitarlos o guardarlos en un archivo de texto.")),
    AtajoOrden("corregir_elemento", _("&Corregir este elemento..."), "Ctrl+Alt+C",
               _("Herramientas"),
               _("Dice qué es de verdad la línea del cursor cuando el programa lo ha "
                 "deducido mal en un PDF sin etiquetar. La corrección se guarda y se "
                 "vuelve a aplicar cada vez que se abra ese documento.")),
    AtajoOrden("revisar_estructura", _("Revisar la &estructura con IA..."), "",
               _("Herramientas"),
               _("Le manda a la inteligencia artificial el esqueleto del documento —los "
                 "títulos y el tipo de cada bloque, sin el texto— para que señale lo que "
                 "está mal deducido: un índice tomado por capítulos, un pie de página "
                 "tomado por un título. Tú decides qué se corrige.")),
    AtajoOrden("diccionario", _("Definir la &palabra del cursor..."), "Ctrl+Alt+P",
               _("Herramientas"),
               _("Busca la palabra donde está el cursor en el diccionario de la RAE, en el "
                 "Wikcionario o preguntándoselo a la inteligencia artificial.")),
    AtajoOrden("ver_capitulo", _("Ver el ca&pítulo como HTML..."), "Ctrl+Shift+H",
               _("Herramientas"),
               _("Muestra el capítulo entero en el visor web, con sus encabezados, listas y "
                 "tablas de verdad, para recorrerlo con las órdenes del lector de pantalla.")),
    AtajoOrden("leer_nota", _("Leer la &nota al pie de aquí"), "Alt+Shift+N",
               _("Herramientas"),
               _("Dice el texto de la nota al pie sin moverte del sitio. Con Intro sobre la "
                 "llamada se salta a la nota, y con Alt+Izquierda se vuelve.")),
    AtajoOrden("resumir", _("Resumir este capítulo con &IA..."), "Ctrl+Alt+U",
               _("Herramientas"),
               _("Le pide a la inteligencia artificial un resumen del capítulo donde estás.")),
    AtajoOrden("preguntar", _("Pre&guntar sobre el documento..."), "Ctrl+Alt+Q",
               _("Herramientas"),
               _("Le pregunta a la inteligencia artificial sobre lo que estás leyendo: un "
                 "resumen, quién es quién, qué significa un párrafo difícil.")),
    AtajoOrden("cuanto_queda", _("Cuánto &queda"), "Ctrl+Shift+Q", _("Herramientas"),
               _("Dice cuánto falta para terminar el capítulo y el documento, en minutos, "
                 "al ritmo al que lees tú. Con la vista eso se ve por el grosor de lo que "
                 "queda; de oído no hay forma de saberlo.")),
    AtajoOrden("informacion", _("&Información del documento..."), "Ctrl+D", _("Herramientas"),
               _("Muestra el título, el autor y las estadísticas del documento.")),
    AtajoOrden("ajuste_linea", _("&Ajuste de línea"), "Ctrl+Alt+W", _("Herramientas"),
               _("Activa o desactiva el ajuste automático de línea.")),
    AtajoOrden("renglon_frase", _("Cada &frase en un renglón"), "", _("Herramientas"),
               _("Empieza cada frase en un renglón nuevo. Sirve para la lectura "
                 "continua del lector de pantalla, que al parar deja el cursor al "
                 "principio del renglón que estaba sonando: siendo el renglón la "
                 "frase, el cursor se queda en la frase y no al principio del "
                 "párrafo. No cambia el texto ni una sola posición.")),
    AtajoOrden("sonidos", _("&Sonidos de navegación"), "Ctrl+Alt+S", _("Herramientas"),
               _("Activa o desactiva los sonidos.")),
    AtajoOrden("modo_lectura", _("Modo &lectura"), "Ctrl+Alt+M", _("Herramientas"),
               _("Apaga de una vez todo lo que acompaña a la lectura —los sonidos, "
                 "el aviso de los elementos, la barra de estado y el árbol de "
                 "contenido— para leer un libro de un tirón sin nada por medio. "
                 "Al volver a pulsarlo se recupera exactamente lo que había.")),
    AtajoOrden("temporizador", _("&Temporizador de apagado..."), "Ctrl+Alt+T",
               _("Herramientas"),
               _("Deja de leer al cabo del tiempo que se indique, para dormirse escuchando. "
                 "Vale para la voz sintética y para las grabaciones DAISY.")),
    AtajoOrden("datos_guardados", _("&Datos guardados..."), "Ctrl+Alt+G", _("Herramientas"),
               _("Muestra qué ha guardado el programa de cada documento y permite borrarlo "
                 "por partes.")),
    # F5 es la tecla de «volver a mirar» en todos los programas que tienen una,
    # y aquí significa exactamente eso: volver a convertir el archivo desde
    # cero.  Hace falta porque hay ajustes que cambian lo que se saca del
    # documento —el reconocimiento de las páginas escaneadas, el tope de
    # páginas que se reconocen— y que no forman parte de la firma con la que se
    # guarda el análisis: el archivo no ha cambiado, así que lo guardado sigue
    # valiendo, y hasta ahora la única forma de rehacerlo era ir a borrar los
    # datos del documento.
    AtajoOrden("volver_a_analizar", _("Volve&r a analizar el documento"), "F5",
               _("Herramientas"),
               _("Convierte otra vez el documento desde el archivo, sin usar lo que se "
                 "guardó la vez anterior. Es lo que hay que hacer después de cambiar el "
                 "reconocimiento de texto o los ajustes de PDF para que se apliquen a un "
                 "documento que ya habías abierto.")),
    AtajoOrden("perfiles", _("&Perfiles de lectura..."), "Ctrl+Alt+F", _("Herramientas"),
               _("Guarda de una vez la voz, los sonidos y cómo se presenta el texto, y "
                 "cambia de un perfil a otro: no se lee igual una novela que un manual.")),
    AtajoOrden("opciones", _("&Opciones..."), "Ctrl+Alt+O", _("Herramientas"),
               _("Abre las preferencias de la aplicación.")),
    # --- Voz ----------------------------------------------------------------
    # Estas órdenes tienen dos destinatarios: la voz sintética en un documento
    # normal y la grabación en un DAISY con audio.  Se dice en cada descripción
    # porque, si no, quien lee «sube la velocidad de la voz» con un libro
    # grabado delante no sabe si le va a cambiar la del narrador o la de la voz
    # del sistema, que son dos ajustes distintos y en dos sitios distintos.
    AtajoOrden("leer_voz", _("&Leer en voz alta o pausar"), "Ctrl+Espacio", _("Voz"),
               _("Empieza a leer desde el cursor; si ya se está leyendo, pausa o continúa. "
                 "En un libro DAISY grabado manda sobre la grabación.")),
    AtajoOrden("detener_voz", _("&Detener la lectura"), "Ctrl+Shift+Espacio", _("Voz"),
               _("Corta la lectura y deja el cursor en la frase por la que iba. "
                 "En un libro DAISY grabado detiene la grabación.")),
    AtajoOrden("frase_siguiente", _("Frase &siguiente"), "Ctrl+Alt+Derecha", _("Voz"),
               _("Pasa a la frase siguiente (o mueve el cursor, si no se está leyendo). "
                 "En un libro DAISY grabado avanza una frase de la grabación.")),
    AtajoOrden("frase_anterior", _("Frase &anterior"), "Ctrl+Alt+Izquierda", _("Voz"),
               _("Vuelve a la frase anterior (o mueve el cursor, si no se está leyendo). "
                 "En un libro DAISY grabado retrocede una frase de la grabación.")),
    AtajoOrden("voz_mas_rapido", _("Leer &más deprisa"), "Ctrl+Alt+Arriba", _("Voz"),
               _("Sube la velocidad de la voz sintética sin cortar la lectura. "
                 "En un libro DAISY grabado sube la de la grabación.")),
    AtajoOrden("voz_mas_lento", _("Leer más des&pacio"), "Ctrl+Alt+Abajo", _("Voz"),
               _("Baja la velocidad de la voz sintética sin cortar la lectura. "
                 "En un libro DAISY grabado baja la de la grabación.")),
    AtajoOrden("leer_seleccion", _("Leer la selecció&n"), "Ctrl+Alt+L", _("Voz"),
               _("Lee en voz alta solo el texto seleccionado.")),
    AtajoOrden("pronunciacion", _("Diccionario de pronun&ciación..."), "", _("Voz"),
               _("Cambia cómo se pronuncian los nombres propios y las siglas de este "
                 "documento, o de todos.")),
    AtajoOrden("ajustes_voz", _("&Voz y velocidad de la voz sintética..."), "Ctrl+Alt+V",
               _("Voz"),
               _("Elige la voz del sistema, su velocidad y su volumen. La velocidad de las "
                 "grabaciones DAISY se ajusta aparte, en Opciones.")),
    AtajoOrden("abrir_carpeta", _("Abrir la carpeta de un libro &DAISY..."), "Ctrl+Shift+O",
               _("Archivo"),
               _("Un libro DAISY es una carpeta entera, no un archivo suelto: aquí se elige.")),
    # --- Reproductor DAISY --------------------------------------------------
    # Cuando el libro abierto es un DAISY con grabación, las órdenes de «Voz»
    # —reproducir, detener, frase anterior, más deprisa— mandan sobre el
    # reproductor en vez de sobre la voz sintética: es la misma acción con el
    # motor que corresponde.  Estas de aquí son las que solo tienen sentido con
    # una grabación delante.
    AtajoOrden("daisy_reproductor", _("&Reproductor DAISY..."), "Ctrl+Alt+R", _("Reproductor DAISY"),
               _("Abre los mandos del reproductor y la lista de capítulos y páginas.")),
    AtajoOrden("daisy_atras", _("Atrás diez se&gundos"), "Ctrl+Alt+Z", _("Reproductor DAISY"),
               _("Retrocede diez segundos de grabación.")),
    AtajoOrden("daisy_adelante", _("Adelante diez segu&ndos"), "Ctrl+Alt+X", _("Reproductor DAISY"),
               _("Avanza diez segundos de grabación.")),
    AtajoOrden("daisy_punto_anterior", _("Punto de navegación &anterior"), "Ctrl+Alt+RePag",
               _("Reproductor DAISY"),
               _("Va al capítulo, sección, página o frase anterior, según el nivel elegido.")),
    AtajoOrden("daisy_punto_siguiente", _("Punto de navegación &siguiente"), "Ctrl+Alt+AvPag",
               _("Reproductor DAISY"),
               _("Va al capítulo, sección, página o frase siguiente, según el nivel elegido.")),
    AtajoOrden("daisy_nivel_arriba", _("Su&bir de nivel de navegación"), "Ctrl+Shift+Arriba",
               _("Reproductor DAISY"),
               _("Cambia a una unidad de navegación mayor: de páginas a secciones, de secciones a capítulos.")),
    AtajoOrden("daisy_nivel_abajo", _("Bajar de nive&l de navegación"), "Ctrl+Shift+Abajo",
               _("Reproductor DAISY"),
               _("Cambia a una unidad de navegación menor: de capítulos a secciones, de secciones a páginas o frases.")),
    AtajoOrden("daisy_donde_estoy", _("&Dónde estoy"), "Ctrl+Alt+J", _("Reproductor DAISY"),
               _("Dice el capítulo, la página, el tiempo transcurrido y lo que queda.")),
    # --- Ayuda --------------------------------------------------------------
    AtajoOrden("manual", _("&Manual de usuario"), "F1", _("Ayuda"),
               _("Abre el manual de usuario en el navegador (también con Control+F1)."),
               _("Ctrl+F1")),
    AtajoOrden("atajos_ayuda", _("&Atajos de teclado..."), "Shift+F1", _("Ayuda"),
               _("Muestra la lista completa de atajos.")),
    AtajoOrden("novedades", _("Ver las últimas &novedades"), "", _("Ayuda"),
               _("Abre en el navegador lo que ha cambiado en cada versión del "
                 "programa, empezando por la más reciente.")),
    AtajoOrden("primer_uso", _("&Recorrido guiado..."), "", _("Ayuda"),
               _("Enseña las teclas esenciales de una en una, dejándolas probar. Es lo "
                 "que se ofrece la primera vez que se abre el programa.")),
    AtajoOrden("practicar", _("&Practicar con este documento..."), "", _("Ayuda"),
               _("Propone ejercicios cortos —ve al tercer encabezado, pon un "
                 "marcador— sobre el documento que tengas abierto y avisa "
                 "cuando salen. Leer una tecla y usarla no son lo mismo.")),
    AtajoOrden("carpeta_datos", _("Abrir carpeta de &datos"), "", _("Ayuda"),
               _("Abre la carpeta donde se guarda todo lo que genera el programa.")),
    AtajoOrden("ver_registro", _("&Ver registro de la aplicación"), "", _("Ayuda"),
               _("Abre el visor de registros, útil para comunicar un problema.")),
    AtajoOrden("buscar_actualizaciones", _("&Buscar actualizaciones..."), "", _("Ayuda"),
               _("Comprueba si hay una versión nueva del programa y ofrece instalarla.")),
    AtajoOrden("invitar_cafe", _("&Invítame a un café si te gusta mi trabajo"), "", _("Ayuda"),
               _("Abre en el navegador la página de donaciones del autor.")),
    AtajoOrden("acerca_de", _("A&cerca de..."), "", _("Ayuda"),
               _("Información sobre el programa.")),
)


#: Nombres en español de las teclas que no son letras, con su equivalente en
#: wxPython.  Se usan para construir la tabla de aceleradores a mano: wxWidgets
#: solo sabe interpretar los nombres en inglés («Home», «Left»...), de modo que
#: escribirlos en español en el menú dejaría los atajos sin funcionar.
TECLAS_ESPECIALES: dict[str, str] = {
    "F1": "WXK_F1", "F2": "WXK_F2", "F3": "WXK_F3", "F4": "WXK_F4",
    "F5": "WXK_F5", "F6": "WXK_F6", "F7": "WXK_F7", "F8": "WXK_F8",
    "F9": "WXK_F9", "F10": "WXK_F10", "F11": "WXK_F11", "F12": "WXK_F12",
    "Inicio": "WXK_HOME", "Fin": "WXK_END",
    "Izquierda": "WXK_LEFT", "Derecha": "WXK_RIGHT",
    "Arriba": "WXK_UP", "Abajo": "WXK_DOWN",
    "RePag": "WXK_PAGEUP", "AvPag": "WXK_PAGEDOWN",
    "Intro": "WXK_RETURN", "Escape": "WXK_ESCAPE",
    "Espacio": "WXK_SPACE", "Suprimir": "WXK_DELETE",
    "Insertar": "WXK_INSERT", "Tabulador": "WXK_TAB",
    "Retroceso": "WXK_BACK",
}


def descomponer(atajo: str) -> tuple[list[str], str] | None:
    """Separa un atajo escrito («Ctrl+Mayús+G») en modificadores y tecla.

    :return: Una tupla ``(modificadores, tecla)``, o ``None`` si el atajo está
             vacío o solo contiene modificadores.
    """
    if not atajo:
        return None
    partes = [parte.strip() for parte in atajo.split("+") if parte.strip()]
    if not partes:
        return None
    # «Ctrl++» y similares dejan la tecla vacía al partir por el signo más.
    if atajo.endswith("++"):
        return partes, "+"
    modificadores = [parte for parte in partes[:-1]]
    return modificadores, partes[-1]


def orden(identificador: str) -> AtajoOrden:
    """Devuelve la definición de una orden por su identificador."""
    for definicion in ORDENES:
        if definicion.identificador == identificador:
            return definicion
    raise KeyError(identificador)


def etiqueta_de_menu(identificador: str) -> str:
    """Devuelve la etiqueta de menú de una orden, con su atajo incorporado."""
    definicion = orden(identificador)
    return "%s\t%s" % (definicion.etiqueta, definicion.atajo) if definicion.atajo else definicion.etiqueta


def resumen_para_ayuda() -> list[tuple[str, list[tuple[str, str]]]]:
    """Construye la lista de atajos agrupada por categorías.

    La usan tanto el diálogo de atajos como el manual de usuario, de modo que
    ambos reflejan siempre las teclas reales del programa.
    """
    grupos: list[tuple[str, list[tuple[str, str]]]] = []

    rapidas: list[tuple[str, str]] = []
    for atajo in NAVEGACION:
        rapidas.append((atajo.tecla, "%s siguiente" % atajo.descripcion))
        rapidas.append((_("Mayús+%s") % atajo.tecla, "%s anterior" % atajo.descripcion))
    rapidas.append((SECCION_SIGUIENTE, _("Capítulo siguiente")))
    rapidas.append((_("Mayús+%s") % SECCION_SIGUIENTE, _("Capítulo anterior")))
    rapidas.append((MARCADOR_SIGUIENTE, "Marcador siguiente"))
    rapidas.append((_("Mayús+%s") % MARCADOR_SIGUIENTE, "Marcador anterior"))
    rapidas.append((NOTA_SIGUIENTE, "Nota siguiente"))
    rapidas.append((_("Mayús+%s") % NOTA_SIGUIENTE, "Nota anterior"))
    rapidas.append((CONTENEDOR_FIN, _("Ir más allá del final de la lista o tabla actual")))
    rapidas.append((_("Mayús+%s") % CONTENEDOR_INICIO, _("Ir al principio de la lista o tabla actual")))
    rapidas.append((DESCRIBIR_IMAGEN, _("Describir con IA la imagen del cursor")))
    rapidas.append((DEFINIR_PALABRA, _("Definir la palabra del cursor")))
    rapidas.append((DONDE_ESTOY, _("Anunciar dónde se está leyendo")))
    rapidas.append((REPETIR_ANUNCIO, _("Repetir el último anuncio")))
    rapidas.append(("Intro", _("Seguir el enlace o abrir la imagen o tabla del cursor")))
    grupos.append((_("Navegación rápida (una sola tecla)"), rapidas))

    for categoria in ("Archivo", "Ir a", "Herramientas", "Voz", "Ayuda"):
        entradas = []
        for definicion in ORDENES:
            if definicion.categoria != categoria:
                continue
            teclas = definicion.atajo or "(sin atajo)"
            if definicion.atajo_alterno:
                teclas += " o " + definicion.atajo_alterno
            entradas.append((teclas, definicion.descripcion))
        grupos.append((_("Menú «%s»") % categoria, entradas))

    grupos.append((
        _("Listas de varias columnas (marcadores y notas, ventana de una tabla)"),
        [
            (_("Flechas arriba y abajo"), _("Fila anterior o siguiente")),
            (_("Flechas izquierda y derecha"), _("Columna anterior o siguiente de esa fila")),
            (_("Control+1 a Control+9"), _("Ir directamente a esa columna")),
            (_("Control+Inicio y Control+Fin"), _("Primera y última columna")),
            ("Intro", _("Aceptar la fila elegida")),
        ],
    ))

    grupos.append((
        _("Lectura (teclas propias del control de texto)"),
        [
            (_("Flechas arriba y abajo"), _("Línea anterior o siguiente")),
            (_("Flechas izquierda y derecha"), _("Carácter anterior o siguiente")),
            (_("Control+Flechas izquierda y derecha"), _("Palabra anterior o siguiente")),
            (_("Re Pág y Av Pág"), _("Pantalla anterior o siguiente")),
            (_("Inicio y Fin"), _("Principio y final de la línea")),
            (_("Control+Inicio y Control+Fin"), _("Principio y final del documento")),
            (_("Mayús + cualquiera de las anteriores"), "Seleccionar texto"),
            ("Control+C", _("Copiar la selección")),
        ],
    ))
    return grupos
