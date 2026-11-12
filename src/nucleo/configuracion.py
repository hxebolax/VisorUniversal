# -*- coding: utf-8 -*-
"""Configuración de la aplicación y datos por documento.

Se guardan dos archivos JSON dentro de ``data/config``:

* ``ajustes.json``: preferencias generales (fuente, colores, sonidos, nivel
  de registro, lista de libros recientes...).
* ``documentos.json``: información propia de cada libro (última posición de
  lectura, marcadores y notas, historial de saltos).

Los dos se escriben de forma **atómica**: primero en un archivo temporal y
después se reemplaza el definitivo.  Así, un corte de corriente o un cierre
forzado no puede dejar la configuración a medio escribir.

Toda opción tiene un valor por omisión en :data:`AJUSTES_POR_OMISION`, de modo
que un archivo corrupto o incompleto nunca impide arrancar: simplemente se
recuperan los valores de fábrica.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from . import rutas
from .registro import obtener_registro, registrar_excepcion

log = obtener_registro(__name__)

#: Número máximo de libros que se recuerdan en «Documentos recientes».
MAXIMO_RECIENTES = 20

#: Valores de fábrica de todas las preferencias.
AJUSTES_POR_OMISION: dict[str, Any] = {
    # --- Registro -----------------------------------------------------------
    "nivel_registro": "INFO",
    # --- Idioma -------------------------------------------------------------
    # «auto» usa el de Windows.  El cambio se aplica al reiniciar: las tablas de
    # atajos y los nombres de los prompts se traducen al importar sus módulos.
    "idioma": "auto",
    # --- Lectura ------------------------------------------------------------
    "tablas_en_linea": True,
    "anunciar_imagenes_sin_texto": True,
    # Sin ajuste de línea, cada línea del control es un párrafo completo del
    # libro: la flecha abajo avanza de párrafo en párrafo y el lector de
    # pantalla lee el párrafo entero de una vez.  Con el ajuste activado, en
    # cambio, la flecha abajo avanza por líneas *visuales* y el párrafo se lee
    # a trozos.  Por eso viene desactivado, igual que en el lector de
    # referencia; se activa con Control+Alt+W para quien prefiera lo contrario.
    "ajuste_de_linea": False,
    # Empezar cada frase en un renglón nuevo dentro del cuadro de lectura.  Es
    # para la lectura continua del lector de pantalla: va diciendo el texto
    # renglón a renglón y deja el cursor al principio del que está sonando, de
    # modo que con el párrafo entero en una línea, al parar la lectura el
    # cursor aparece al principio del párrafo y hay que volver a bajar por lo
    # que ya se ha oído.  Con esto el renglón es la frase y el cursor se queda
    # en la frase que sonaba.  **No cambia el texto ni una sola posición**: lo
    # único que ocurre es que el espacio que separa dos frases se enseña como
    # un salto de línea.  Viene apagado porque cambia mucho cómo se ve el
    # texto, y quien lee con la vista no tiene el problema que arregla.
    "renglon_por_frase": False,
    "navegacion_circular": False,
    "recordar_posicion": True,
    "usar_cache": True,
    # Cambiar de voz al llegar a un fragmento en otro idioma, cuando el
    # documento lo declara (los EPUB accesibles y los PDF etiquetados lo hacen)
    # y hay instalada una voz de ese idioma.  Es lo que hacen NVDA y Adobe
    # Reader, y es lo que evita oír una cita en inglés con acento español.
    "voz_seguir_idioma": True,

    # --- Personalización de la ventana --------------------------------------
    # Abrir cada documento en su pestaña, para poder tener varios a la vez.
    # Viene apagado a propósito: quien lee una novela cada tarde no quiere una
    # fila de pestañas ni una zona más por la que pasar con F6, y obligarle a
    # ella sería empeorarle el programa para arreglarle un problema que no
    # tiene.  Quien estudia o compara lo enciende y no lo vuelve a tocar.
    "usar_pestanas": False,
    # Qué hacer al abrir un documento con otro ya abierto en la pestaña:
    # "preguntar", "nueva" (siempre en una pestaña nueva) o "actual".
    "pestanas_al_abrir": "preguntar",
    # Árbol con el índice y los elementos del documento, a la izquierda del
    # texto.  También apagado de fábrica y por el mismo motivo.
    "mostrar_arbol": False,
    # Ancho del árbol, en píxeles.  Se guarda al esconderlo o al cerrar.
    "arbol_ancho": 320,
    # Enseñar en la barra de estado cuántas palabras y cuántas páginas tiene el
    # documento.  Es lo que se echa de menos al venir de otros lectores: saber
    # el tamaño de lo que se está leyendo sin abrir ningún diálogo.
    "barra_recuentos": True,
    # Enseñar el resumen de teclas mientras no hay ningún documento abierto.
    # Encendido de fábrica: es lo que convierte la primera pantalla en algo que
    # se puede leer en lugar de una ventana vacía, y es donde se descubre lo
    # que el programa sabe hacer.  Se apaga cuando ya se sabe: entonces sale
    # una presentación de dos líneas, que se recorre de un vistazo.
    "mostrar_bienvenida": True,

    # --- PDF ----------------------------------------------------------------
    # Aprovechar el árbol de estructura de los PDF etiquetados (los que cumplen
    # PDF/UA): encabezados, listas, tablas, citas, notas y texto alternativo de
    # las imágenes, igual que en un EPUB.  Se puede apagar para volver a leer
    # el PDF como texto corrido, que es lo que conviene en los pocos archivos
    # cuyo etiquetado está peor hecho que el texto que esconde.
    # Ancho máximo del renglón, en caracteres, cuando el ajuste de línea está
    # activado.  A 0 el texto ocupa todo el ancho de la ventana, que en una
    # pantalla grande son renglones larguísimos donde es fácil perderse al
    # volver al principio de la línea siguiente.  No cambia el texto ni una
    # sola posición: solo se estrecha el control dejando márgenes.
    "ancho_maximo_linea": 0,
    # Volver a abrir al arrancar los documentos que quedaron abiertos al
    # cerrar.  Viene apagado porque no todo el mundo lo quiere: hay quien
    # abre el programa para leer una cosa concreta y se encontraría con
    # media biblioteca abriéndose delante.
    "restaurar_documentos": False,
    # Los documentos que quedaban abiertos y cuál estaba delante.  Se
    # apuntan siempre, aunque la opción esté apagada, para que quien la
    # active encuentre ahí lo que tenía y no una lista vacía.
    "documentos_abiertos": [],
    "documento_activo": 0,
    # --- Integración con el explorador de Windows -------------------------
    # Extensiones con las que el programa se integra en el sistema.  Vacía
    # quiere decir «sin integración», que es como viene de fábrica: un
    # programa portátil no debe tocar el equipo sin que se lo pidan.
    "integracion_formatos": [],
    # Si esos formatos llevan la orden «Abrir con...» en el menú del botón
    # derecho, y si el programa figura en el «Abrir con» de Windows.
    "integracion_menu": True,
    "integracion_abrir_con": True,
    # --- Modo lectura ------------------------------------------------------
    # Si está puesto el modo sin distracciones, y qué había antes de ponerlo
    # para poder devolverlo tal cual al salir.
    "modo_lectura": False,
    "modo_lectura_anterior": {},
    "pdf_estructura": True,
    # Deducir la estructura de los PDF **sin** etiquetar a partir de como
    # estan escritos: los titulos por su tamano de letra, las tablas por como
    # se alinean sus columnas, los enlaces por sus anotaciones.  Es lo que
    # convierte un PDF corriente en algo que se puede recorrer con H y con T
    # en lugar de leer de principio a fin.  Cuesta alrededor de medio segundo
    # cada diez paginas; se puede apagar en un equipo muy justo.
    "pdf_geometria": True,
    # Con qué se reconocen las páginas de un PDF que son imágenes: "auto" (la
    # inteligencia artificial y, si falla, el OCR de Windows), "ia", "windows"
    # o "ninguno".  Sin reconocer, un PDF escaneado se abre vacío.
    "pdf_ocr_modo": "auto",
    # Tope de páginas que se reconocen en un mismo PDF.  Reconocer es lento —con
    # la IA, mucho—, y sin un tope un libro escaneado de quinientas páginas
    # dejaría el programa abriendo durante horas sin poder cancelarlo.  A 0 no
    # hay tope.
    "pdf_ocr_maximo": 100,
    # Idiomas con los que reconoce Tesseract, separados por «+» (por ejemplo
    # "spa+cat").  Vacío deja que se elijan solos entre los instalados.
    "pdf_ocr_idiomas": "",
    # Aumento con el que se rasteriza la página antes de reconocerla.  A 0 se
    # usa el que le va bien a cada motor: 3 para Tesseract, 2 para los demás.
    "pdf_ocr_escala": 0,
    # Modo de segmentación de página de Tesseract.  El 1 analiza la página
    # entera detectando su orientación, y es el que mejor resultado dio.
    "pdf_ocr_psm": 1,
    # Motor interno de Tesseract: 3 lo deja elegir, 1 fuerza el de redes
    # neuronales, 0 el clásico, 2 los dos.
    "pdf_ocr_oem": 3,
    # Resolución que se le declara a Tesseract.  A 0 la deduce él.
    "pdf_ocr_dpi": 0,
    # Confianza mínima para quedarse con una palabra.  Subirla limpia el ruido
    # de los adornos, pero cuidado: en un folleto los precios sobre fondo de
    # color salen con confianza baja y se perderían.
    "pdf_ocr_confianza": 30,
    # Preparar la imagen antes de reconocerla.  Medido sobre un folleto real,
    # pasar a gris y subir el contraste llevó los productos leídos con su
    # precio de 7 a 9 sobre 14, y la basura de 8 líneas a 2.
    "pdf_ocr_gris": True,
    "pdf_ocr_contraste": 3.0,
    # Blanco y negro puro.  Apagado: rompe la letra fina y salió peor.
    "pdf_ocr_binarizar": False,
    "pdf_ocr_umbral": 160,
    # Descartar lo que no tiene ninguna letra ni número: flechas, marcos y
    # demás adornos que el motor intenta leer como si fueran texto.
    "pdf_ocr_quitar_simbolos": True,
    # Reconstruir las tablas como tablas de verdad.
    "pdf_ocr_tablas": True,
    # Doble pasada: leer cada página dos veces con la imagen preparada de dos
    # formas distintas y juntar lo leído.  Tarda el doble y merece la pena:
    # medido sobre un folleto en color, pasó de 15 a 20 productos leídos con su
    # precio de 23, porque las dos pasadas no fallan en los mismos sitios.
    "pdf_ocr_esmerado": True,
    # --- Reproductor DAISY --------------------------------------------------
    # Velocidad de la grabación en porcentaje: 100 es la del narrador.  Se
    # cambia sin alterar el tono de la voz, así que subirla no lo convierte en
    # un pato; mucha gente escucha a 150 o más.
    "daisy_velocidad": 100,
    "daisy_volumen": 100,
    # Llevar el cursor del texto siguiendo a la grabación.  Viene activado
    # porque es lo que permite consultar con el lector de pantalla lo que se
    # está oyendo, y porque en un libro de solo audio es la única forma de
    # saber por dónde va.
    "daisy_mover_cursor": True,
    # Empezar a reproducir en cuanto se abre un libro DAISY grabado.  Viene
    # apagado: quien abre un libro no siempre quiere que le suene de golpe.
    "daisy_reproducir_al_abrir": False,
    # --- Accesibilidad ------------------------------------------------------
    # Qué se dice de cada celda al recorrer una lista con las flechas
    # izquierda y derecha.  Vienen las tres activadas porque es lo que menos
    # supone: quien ya sabe en qué columna está las va apagando.
    "columnas_decir_fila": True,
    "columnas_decir_encabezado": True,
    "columnas_decir_contenido": True,
    # --- Inteligencia artificial --------------------------------------------
    # Viene desactivada: describir imágenes manda datos fuera del equipo (con
    # Gemini) o exige tener un servidor en marcha (en local), y ninguna de las
    # dos cosas debe pasar sin que el usuario lo haya pedido.
    "ia_proveedor": "off",             # off, gemini, anthropic, openai, local
                                       # u ollama_propio
    "ia_gemini_claves": [],            # varias claves: se rotan al agotarse
    "ia_gemini_modelo": "gemini-2.5-flash",
    # Los modelos que devuelve el proveedor se guardan aquí para no tener que
    # volver a pedirlos cada vez que se abren las opciones.
    "ia_gemini_modelos": [],
    # Cada proveedor guarda sus claves aparte, para poder cambiar de uno a otro
    # sin tener que volver a escribirlas.
    "ia_anthropic_claves": [],
    "ia_anthropic_modelo": "claude-haiku-4-5-20251001",
    "ia_anthropic_modelos": [],
    # OpenAI y todo lo que habla su misma API: Groq, DeepSeek, OpenRouter...
    # Por eso la dirección es un ajuste y no una constante.
    "ia_openai_claves": [],
    "ia_openai_url": "https://api.openai.com/v1",
    "ia_openai_modelo": "gpt-4o-mini",
    "ia_openai_modelos": [],
    # Contador de peticiones y de texto gastado, por proveedor.
    "ia_consumo": {},
    # Sobre qué parte del documento se pregunta por omisión.
    "ia_ambito": "capitulo",
    # --- Ollama propio: la IA local que instala el programa ------------------
    # Con qué trabaja el motor: "auto" usa la tarjeta gráfica si la hay, "cpu"
    # la ignora.  Hay equipos donde la gráfica es peor que el procesador —una
    # integrada con poca memoria acaba tirando por falta de sitio—, y ahí esto
    # es la diferencia entre funcionar y no funcionar.
    "ollama_calculo": "auto",
    # Modelo con el que se trabaja, de los que haya descargados.
    "ollama_modelo": "",
    # Minutos que el modelo se queda cargado en memoria después de usarlo.
    # Cargarlo cuesta entre diez segundos y un minuto, así que tenerlo a mano
    # se nota mucho al describir varias imágenes seguidas; a cambio ocupa
    # memoria.  A 0 se descarga en cuanto termina.
    "ollama_mantener_cargado": 5,
    # Tamaño del contexto, en fichas.  A 0 se usa el del propio modelo, que es
    # lo que conviene salvo que se sepa lo que se hace.
    "ollama_contexto": 0,
    # Atención rápida: en las tarjetas que la admiten ahorra memoria y va algo
    # más deprisa.  En las que no, el servidor lo ignora.
    "ollama_atencion_rapida": False,
    # Arrancar el servidor al abrir el programa.  Apagado, se arranca solo la
    # primera vez que se le pide algo, que tarda unos segundos.
    "ollama_arrancar_al_abrir": False,
    # Cerrar el servidor al salir del programa.  Encendido de fábrica: dejar
    # un servidor de IA corriendo después de cerrar el lector no es lo que
    # nadie espera, y ocupa memoria.
    "ollama_cerrar_al_salir": True,
    "ia_local_url": "http://localhost:8080/v1",
    "ia_local_modelo": "local",
    "ia_local_modelos": [],
    "ia_tiempo_espera": 90,            # segundos de espera a la respuesta
    # Espera entre imágenes al describir el libro entero.  En 0 salvo que el
    # proveedor se queje de cuota: la capa gratuita de Gemini limita las
    # peticiones por minuto.
    "ia_pausa_lote": 0,
    # Si al describir todas las imágenes se piden también los datos de los
    # gráficos.  Apagado: gasta una petición más por imagen y en un libro
    # ilustrado la mayoría de las imágenes no son gráficos.
    "ia_datos_en_lote": False,
    # Cómo se dicen las fórmulas químicas al leer en voz alta.  «auto» las lee
    # solo en los documentos que traen química de verdad, que es lo que evita
    # que una novela con una vitamina B12 suelta se lea como un libro de texto.
    # Estilo con el que se copia una cita bibliográfica.
    "cita_estilo": "iso690",
    # En una página web guardada, quedarse solo con el artículo.  Encendido:
    # si el recorte no es seguro, el extractor se echa atrás solo y la página
    # se lee entera, así que no hay nada que perder.
    "solo_articulo": True,
    # Comprobar el EPUB recién exportado con las reglas de accesibilidad antes
    # de darlo por bueno.  Tarda una décima y evita mandar un libro roto.
    "revisar_epub": True,
    # Escribir el braille en contraído (grado 2) en vez de en integral.
    # **Apagado a propósito.**  Quien no haya estudiado el braille contraído no
    # entiende un texto contraído, así que encenderlo por omisión dejaría a
    # mucha gente con un archivo ilegible.  Y quien sí lo lee lo enciende una
    # vez y se queda encendido.
    "braille_contraido": False,
    "voz_quimica": "auto",
    # Qué no se dice al leer de corrido.  Los tres vienen apagados: son
    # decisiones sobre el contenido del libro, y quien estudia sí quiere oír
    # las llamadas de nota.
    "voz_saltar_notas": False,
    "voz_saltar_folios": False,
    "voz_saltar_cabeceras": False,
    "ia_prompts": [],                  # prompts propios del usuario
    "ia_prompt_preferido": "general",
    "ia_guardar_descripciones": True,
    # Al llegar a una imagen que ya tiene descripción guardada, decirla.
    "ia_anunciar_descripcion": True,
    # --- Lectura en voz alta ------------------------------------------------
    # Qué programa pone la voz.  «sapi5» es la de Windows: la que está siempre,
    # la que arranca al instante y la que queda cuando cualquier otra falla.
    # Los demás motores se añaden como paquete desde la propia ventana de la
    # voz, y su identificador es el que traiga su paquete.
    "voz_motor": "sapi5",
    # Los ajustes propios de cada motor, por identificador:
    # ``{"eloquence": {"idioma": "esp", "variante": 1}}``.  Van todos juntos y
    # no en claves sueltas para que quitar un motor y volver a instalarlo
    # devuelva lo que estaba puesto: quien ajustó la variante y la frecuencia no
    # quiere volver a hacerlo.
    "voz_ajustes_motores": {},
    "voz_nombre": "",                  # vacío = la voz que tenga el sistema
    # Rapidez y volumen van de 0 a 100 para poder ponerlos en un deslizador y
    # decirlos en voz alta sin explicar nada; 50 es la velocidad normal.
    "voz_rapidez": 50,
    "voz_volumen": 100,
    # El cursor no acompaña a la voz por omisión: con el lector de pantalla en
    # marcha, moverlo hace que lea la línea y se oigan dos voces a la vez.
    "voz_mover_cursor": False,
    # Dónde queda el cursor al pausar o al detener la lectura: "inicio", al
    # principio de la frase que se estaba diciendo, o "fin", justo detrás de
    # ella.  De fábrica va "inicio", que es lo que conviene cuando se para
    # porque algo no se ha entendido: se vuelve a leer esa frase con las
    # flechas.  Con "fin", las flechas siguen por lo que aún no ha sonado, que
    # es lo que se busca cuando se para para seguir leyendo a mano.
    "voz_cursor_al_parar": "inicio",
    # Al llegar a una imagen, seguir con la descripción que se le hizo con
    # inteligencia artificial.  Desactivado de fábrica: alarga la lectura y
    # solo tiene sentido en libros con las imágenes ya descritas.
    "voz_leer_descripciones": False,
    # Pintar con fondo de color la frase que suena.  Desactivado de fábrica:
    # no le sirve de nada a quien lee solo de oído, que es el caso más común,
    # y a cambio repinta un tramo del texto en cada frase.
    "voz_resaltar_frase": False,
    # Cambiar de tono en las líneas de diálogo, para saber quién habla sin
    # tener que reconstruirlo. Apagado de fábrica por dos razones: en un ensayo
    # o en un manual no hay diálogo y no cambiaría nada, y a quien le molesta
    # que la voz cambie de registro le molesta desde la primera página.
    "voz_modo_dialogo": False,
    # Cuánto sube el tono en el diálogo, de 1 a 10. Cuatro se nota sin sonar
    # raro; de ocho en adelante la voz se convierte en un dibujo animado.
    "voz_tono_dialogo": 4,
    # Minutos del temporizador de apagado que se proponen la próxima vez.
    "voz_temporizador_minutos": 30,
    # --- Apariencia ---------------------------------------------------------
    "fuente_nombre": "",          # vacío = fuente del sistema
    "fuente_tamano": 11,
    "color_texto": "",            # vacío = colores del sistema
    "color_fondo": "",
    # La negrita y la cursiva se desactivan por omisión: aplicarlas obliga al
    # control de texto de Windows a rehacer la disposición del párrafo por cada
    # tramo, lo que en un libro con miles de cursivas se nota al desplazarse.
    "mostrar_formato": False,
    # --- Sonidos ------------------------------------------------------------
    "sonidos_activados": True,
    "sonidos_volumen": 70,
    "sonidos_solo_al_navegar": False,
    # Cómo se avisa de los elementos por los que pasa el cursor: "sonido" (un
    # pitido, lo de siempre), "voz" (se dicen), "ambos" o "ninguno".  La voz
    # existe porque el pitido solo puede ser uno por línea: en una línea con un
    # salto de página y una llamada de nota suena el salto y la nota se queda
    # sin señalar, y en un libro muy anotado eso es la mitad de las notas.
    "avisar_elementos": "sonido",
    # Escribir «[nota 12]» en lugar de «[12]» en las llamadas de nota.  Es lo
    # único que se oye en la lectura continua del lector de pantalla: los
    # sonidos del programa acompañan al cursor, y en la lectura continua el
    # cursor no se mueve.  Viene apagado porque alarga el texto, y en un libro
    # con quinientas notas eso son quinientas palabras más.
    "marcar_llamadas_de_nota": False,
    # --- Bandeja y teclas globales ------------------------------------------
    # Al minimizar, quitarse de la barra de tareas y dejar solo el icono de la
    # bandeja.  Desactivado de fábrica: hacer desaparecer una ventana de la
    # barra de tareas por sorpresa desorienta a cualquiera.
    "minimizar_a_bandeja": False,
    "teclas_globales_activas": False,
    "teclas_globales": {},             # solo lo que difiera de fábrica
    # --- Ventana ------------------------------------------------------------
    "ventana_ancho": 1000,
    "ventana_alto": 700,
    "ventana_maximizada": False,
    # --- Búsqueda -----------------------------------------------------------
    "buscar_mayusculas": False,
    "buscar_palabra_completa": False,
    "buscar_expresion_regular": False,
    "buscar_historial": [],
    # --- Perfiles de lectura --------------------------------------------------
    # Juegos de ajustes con nombre: no se lee igual una novela que un manual.
    "perfiles": {},
    "perfil_activo": "",
    # --- Pronunciación ------------------------------------------------------
    # Reglas que se aplican a todos los documentos.  Las de cada libro van
    # aparte, con sus marcadores.
    "pronunciacion_general": [],
    "pronunciacion_activa": True,
    # --- Primer uso ---------------------------------------------------------
    # El recorrido guiado se ofrece una sola vez.  Se guarda una marca propia y
    # no se deduce de si hay documentos recientes: quien abre el programa,
    # mira y lo cierra no debe encontrárselo otra vez al día siguiente.
    "primer_uso_hecho": False,
    # --- Actualizaciones ----------------------------------------------------
    # Comprobar al arrancar si hay versión nueva.  Activado: la comprobación
    # es una petición diminuta que no retrasa nada, y se calla salvo que haya
    # algo que decir.  Sin servidor configurado en version.py no se hace nada.
    "comprobar_actualizaciones": True,
    # Dónde se buscan: «ambos» (servidor y GitHub), «servidor», «github» o
    # «personalizada», con su dirección en «actualizaciones_url».
    "actualizaciones_origen": "ambos",
    "actualizaciones_url": "",
    # --- Recientes ----------------------------------------------------------
    "documentos_recientes": [],
    # Carpetas que la biblioteca exploraba hasta la 1.3.4.  Desde la 1.3.5 las
    # carpetas y las bibliotecas de calibre se guardan en biblioteca.db; las
    # que queden aquí se pasan allí la primera vez que se abre la biblioteca.
    "biblioteca_carpetas": [],
    # Qué hacer al añadir una carpeta que es una biblioteca de calibre:
    # «calibre» la importa con todos sus datos, «preguntar» lo pregunta cada
    # vez y «carpeta» la trata como una carpeta corriente.
    "biblioteca_calibre_modo": "calibre",
    # Si las bibliotecas de calibre que haya dentro de una carpeta se importan
    # aparte, con sus datos, en vez de recorrerse como archivos sueltos.
    "biblioteca_calibre_anidadas": True,
    # Leer los metadatos de los EPUB (título, autores, serie...) al importar
    # carpetas corrientes.  Tarda más, pero sin ello solo se sabe el nombre
    # del archivo.
    "biblioteca_leer_metadatos": True,
    # Traer las sinopsis de calibre y de los EPUB.  Ocupan bastante en la base
    # de datos; quien no las lea puede ahorrárselas.
    "biblioteca_importar_sinopsis": True,
    # Con un libro de calibre en varios formatos: una sola entrada con el
    # preferido, o una por formato.
    "biblioteca_un_libro_por_formato": False,
    # Orden de preferencia de los formatos cuando un libro tiene varios.
    "biblioteca_formatos_preferidos":
        "EPUB, KEPUB, AZW3, KFX, MOBI, AZW, FB2, DOCX, ODT, RTF, HTMLZ, HTML, PDF, DJVU, TXT",
    # Columnas de la lista de libros.
    "biblioteca_columnas": ["titulo", "autor", "serie", "coleccion", "formato", "lectura"],
    # Datos de la ficha de un libro, en su orden, y los de las fichas que se
    # exportan a un archivo.  Vacías, todos en el orden de fábrica (ver
    # nucleo/biblioteca_ficha.py).
    "biblioteca_ficha_campos": [],
    "biblioteca_exportar_campos": [],
    # Cada cuántos segundos se dice el avance de lo que tarda (0: nunca).
    "biblioteca_anunciar_avance": 10,
    # Poner al día las bibliotecas de calibre cada vez que se abre la biblioteca.
    "biblioteca_actualizar_al_abrir": False,
    # En cualquier lista de varias columnas: la tecla que dice en qué elemento
    # se está y de cuántos, y la que pregunta a qué número ir.  Vacía, ninguna.
    "lista_tecla_posicion": "ctrl+i",
    "lista_tecla_ir_a": "ctrl+g",
    # En la bibliografía, abrir los libros a los que les falten datos.  Viene
    # apagado: los datos salen de la biblioteca, y abrir los libros enteros es
    # lo único lento de verdad.
    "bibliografia_abrir_libros": False,
    # Cómo se dejó la vista de la biblioteca la última vez.
    "biblioteca_agrupar": "coleccion",
    "biblioteca_orden": "titulo",
    # Carpeta que el usuario sincroniza por su cuenta (Dropbox, OneDrive, un
    # pendrive...) y en la que el programa deja una copia de las posiciones de
    # lectura, los marcadores, las notas y las descripciones de imágenes.
    "sincronizacion_carpeta": "",
    # Si se sincroniza sola al arrancar y al cerrar.
    "sincronizacion_automatica": True,
    "ultima_carpeta": "",
}


@dataclass
class Marcador:
    """Algo que el usuario ha señalado en un libro: un marcador, una nota o un
    resaltado.

    Los tres son lo mismo con distinta intención, y por eso comparten
    estructura en lugar de tener cada uno la suya:

    * Un **marcador** señala un punto para volver a él.
    * Una **nota** es un marcador con algo escrito.
    * Un **resaltado** señala un **trozo** de texto que interesa conservar: la
      idea principal de un apartado, una definición, una cita.  Es lo que se
      exporta después para repasar.

    :param inicio: Posición inicial en el texto.
    :param fin: Posición final (igual que ``inicio`` si no hay selección).
    :param nota: Texto de la nota.  Si está vacío, no es una nota.
    :param fragmento: Trozo del texto marcado, para reconocerlo en la lista y
                      para poder exportarlo aunque el libro no esté abierto.
    :param resaltado: Si es un pasaje resaltado.
    :param etiquetas: Temas a los que pertenece esto, para poder juntar después
                      lo del mismo tema aunque esté repartido por seis libros
                      (:mod:`nucleo.etiquetas`).
    """

    inicio: int
    fin: int
    nota: str = ""
    fragmento: str = ""
    resaltado: bool = False
    etiquetas: list[str] = field(default_factory=list)

    @property
    def es_nota(self) -> bool:
        """Indica si el marcador lleva una nota escrita."""
        return bool(self.nota.strip())

    @property
    def es_resaltado(self) -> bool:
        """Indica si señala un pasaje y no un punto."""
        return bool(self.resaltado and self.fin > self.inicio)

    def como_dict(self) -> dict[str, Any]:
        """Representación para guardar en JSON.

        Los campos ``resaltado`` y ``etiquetas`` solo se escriben cuando hay
        algo que escribir: así los archivos de quien no los use siguen siendo
        exactamente los de antes y no engordan sin motivo.
        """
        datos = {"inicio": self.inicio, "fin": self.fin, "nota": self.nota,
                 "fragmento": self.fragmento}
        if self.resaltado:
            datos["resaltado"] = True
        if self.etiquetas:
            datos["etiquetas"] = list(self.etiquetas)
        return datos

    @classmethod
    def desde_dict(cls, datos: dict[str, Any]) -> "Marcador":
        """Reconstruye un marcador a partir de su representación en JSON."""
        return cls(
            inicio=int(datos.get("inicio", 0)),
            fin=int(datos.get("fin", 0)),
            nota=str(datos.get("nota", "")),
            fragmento=str(datos.get("fragmento", "")),
            resaltado=bool(datos.get("resaltado", False)),
            etiquetas=[str(e) for e in (datos.get("etiquetas") or [])],
        )


@dataclass
class DatosDocumento:
    """Todo lo que la aplicación recuerda de un libro concreto."""

    posicion: int = 0
    marcadores: list[Marcador] = field(default_factory=list)
    historial: list[int] = field(default_factory=list)
    indice_historial: int = 0
    titulo: str = ""
    #: Reglas de pronunciación propias de este documento, tal y como se
    #: guardan en el JSON.  Van aquí y no en los ajustes generales porque los
    #: nombres de una saga solo tienen sentido en esa saga.
    pronunciacion: list = field(default_factory=list)
    #: Tiempo leído y caracteres recorridos, para las estadísticas.
    lectura: dict = field(default_factory=dict)
    #: Autor del libro y cuánto mide su texto.  Los guarda la biblioteca para
    #: poder decir por dónde va cada libro **sin abrirlo**: sin el total, un
    #: número de posición no significa nada.
    autor: str = ""
    total: int = 0
    #: Cuándo se tocó por última vez, en segundos desde 1970.  Es lo que
    #: permite juntar dos equipos sin que gane el último que cierre.
    actualizado: float = 0.0
    #: A qué colección o asignatura pertenece este libro.  Lo pone el usuario
    #: desde la biblioteca, y es lo que permite quedarse con los seis libros de
    #: una asignatura en una biblioteca de trescientos.  Va aquí y no en un
    #: archivo aparte para que viaje con el resto entre equipos.
    coleccion: str = ""

    def como_dict(self) -> dict[str, Any]:
        """Representación para guardar en JSON."""
        return {
            "posicion": self.posicion,
            "titulo": self.titulo,
            "marcadores": [marcador.como_dict() for marcador in self.marcadores],
            "historial": self.historial[-50:],
            "indice_historial": self.indice_historial,
            "pronunciacion": self.pronunciacion,
            "lectura": self.lectura,
            "autor": self.autor,
            "total": self.total,
            "actualizado": round(self.actualizado, 3),
            "coleccion": self.coleccion,
        }

    @classmethod
    def desde_dict(cls, datos: dict[str, Any]) -> "DatosDocumento":
        """Reconstruye los datos de un libro a partir del JSON."""
        return cls(
            posicion=int(datos.get("posicion", 0)),
            titulo=str(datos.get("titulo", "")),
            marcadores=[Marcador.desde_dict(m) for m in datos.get("marcadores") or []],
            historial=[int(v) for v in datos.get("historial") or []],
            indice_historial=int(datos.get("indice_historial", 0)),
            pronunciacion=list(datos.get("pronunciacion") or []),
            lectura=dict(datos.get("lectura", {}) or {}),
            autor=str(datos.get("autor", "")),
            total=int(datos.get("total", 0) or 0),
            actualizado=float(datos.get("actualizado", 0) or 0),
            coleccion=str(datos.get("coleccion", "") or ""),
        )


def escribir_json(destino, contenido: Any) -> None:
    """Escribe un archivo JSON de forma atómica.

    Se escribe primero un archivo ``.tmp`` y solo después se reemplaza el
    definitivo, operación que el sistema de archivos garantiza como atómica.
    """
    temporal = destino.with_suffix(destino.suffix + ".tmp")
    with open(temporal, "w", encoding="utf-8") as archivo:
        json.dump(contenido, archivo, ensure_ascii=False, indent=1)
    os.replace(temporal, destino)


def leer_json(origen, por_omision: Any) -> Any:
    """Lee un archivo JSON, devolviendo un valor por omisión si falla."""
    try:
        with open(origen, "r", encoding="utf-8") as archivo:
            return json.load(archivo)
    except FileNotFoundError:
        return por_omision
    except (json.JSONDecodeError, OSError) as error:
        log.warning("No se ha podido leer %s (%s); se usan los valores por omisión", origen, error)
        return por_omision


class Configuracion:
    """Acceso centralizado a las preferencias y a los datos por documento.

    Es segura frente a accesos desde varios hilos: todas las operaciones se
    protegen con un cerrojo, porque el análisis de los libros se hace en un
    hilo secundario que también consulta los ajustes.
    """

    def __init__(self) -> None:
        self._cerrojo = threading.RLock()
        self._archivo_ajustes = rutas.ruta_config() / "ajustes.json"
        self._archivo_documentos = rutas.ruta_config() / "documentos.json"
        self._ajustes: dict[str, Any] = dict(AJUSTES_POR_OMISION)
        self._documentos: dict[str, DatosDocumento] = {}
        self.cargar()

    # -- carga y guardado ----------------------------------------------------

    def cargar(self) -> None:
        """Lee los dos archivos de configuración desde el disco."""
        with self._cerrojo:
            guardados = leer_json(self._archivo_ajustes, {})
            if isinstance(guardados, dict):
                self._traducir_ajustes_viejos(guardados)
                for clave, valor in guardados.items():
                    if clave in AJUSTES_POR_OMISION:
                        self._ajustes[clave] = valor
                    else:
                        log.debug("Se ignora el ajuste desconocido %r", clave)
            documentos = leer_json(self._archivo_documentos, {})
            if isinstance(documentos, dict):
                for ruta, datos in documentos.items():
                    try:
                        self._documentos[ruta] = DatosDocumento.desde_dict(datos)
                    except Exception as error:
                        registrar_excepcion(log, "Datos ilegibles del libro %s" % ruta, error)
            log.debug("Configuración cargada: %d ajustes, %d libros recordados",
                      len(self._ajustes), len(self._documentos))

    @staticmethod
    def _traducir_ajustes_viejos(guardados: dict[str, Any]) -> None:
        """Pone al día los ajustes que han cambiado de forma entre versiones.

        Los ajustes desconocidos se descartan al cargar, así que sin esto un
        cambio de nombre le devolvería al usuario el valor de fábrica sin
        avisar.  Aquí se traducen antes de ese filtro.
        """
        # «pdf_ocr» era un sí o no; ahora se elige además con qué motor.
        if "pdf_ocr_modo" not in guardados and "pdf_ocr" in guardados:
            guardados["pdf_ocr_modo"] = "auto" if guardados.get("pdf_ocr") else "ninguno"

    def guardar(self) -> None:
        """Escribe los dos archivos de configuración en el disco."""
        with self._cerrojo:
            try:
                escribir_json(self._archivo_ajustes, self._ajustes)
                escribir_json(
                    self._archivo_documentos,
                    {ruta: datos.como_dict() for ruta, datos in self._documentos.items()},
                )
            except OSError as error:
                registrar_excepcion(log, "No se ha podido guardar la configuración", error)

    # -- ajustes generales ---------------------------------------------------

    def obtener(self, clave: str, por_omision: Any = None) -> Any:
        """Devuelve el valor de un ajuste."""
        with self._cerrojo:
            if por_omision is None:
                por_omision = AJUSTES_POR_OMISION.get(clave)
            return self._ajustes.get(clave, por_omision)

    def establecer(self, clave: str, valor: Any) -> None:
        """Cambia el valor de un ajuste (sin guardarlo todavía en disco)."""
        with self._cerrojo:
            self._ajustes[clave] = valor

    # -- libros recientes ----------------------------------------------------

    def recientes(self) -> list[str]:
        """Lista de libros abiertos recientemente, del más al menos reciente."""
        with self._cerrojo:
            return list(self._ajustes.get("documentos_recientes") or [])

    def anadir_reciente(self, ruta: str) -> None:
        """Coloca un libro al principio de la lista de recientes."""
        with self._cerrojo:
            lista = [r for r in self._ajustes.get("documentos_recientes") or []
                     if r != ruta]
            lista.insert(0, ruta)
            self._ajustes["documentos_recientes"] = lista[:MAXIMO_RECIENTES]

    def quitar_reciente(self, ruta: str) -> None:
        """Elimina un libro de la lista de recientes."""
        with self._cerrojo:
            self._ajustes["documentos_recientes"] = [
                r for r in self._ajustes.get("documentos_recientes") or [] if r != ruta
            ]

    # -- historial de búsqueda ----------------------------------------------

    def anadir_busqueda(self, texto: str) -> None:
        """Recuerda un término de búsqueda."""
        if not texto:
            return
        with self._cerrojo:
            historial = [t for t in self._ajustes.get("buscar_historial") or []
                         if t != texto]
            historial.insert(0, texto)
            self._ajustes["buscar_historial"] = historial[:25]

    # -- datos por documento -------------------------------------------------

    def datos_de(self, ruta: str) -> DatosDocumento:
        """Devuelve (creándolos si hace falta) los datos guardados de un libro."""
        with self._cerrojo:
            datos = self._documentos.get(ruta)
            if datos is None:
                datos = DatosDocumento()
                self._documentos[ruta] = datos
            return datos

    def recordar_coleccion(self, ruta: str, coleccion: str) -> None:
        """Apunta a qué colección o asignatura pertenece un libro.

        Se marca la hora, como cualquier otro cambio: es lo que hace que al
        sincronizar con otro equipo gane el que lo cambió después y no el que
        cerró más tarde.
        """
        with self._cerrojo:
            datos = self._documentos.get(ruta)
            if datos is None:
                datos = DatosDocumento()
                self._documentos[ruta] = datos
            datos.coleccion = (coleccion or "").strip()
            datos.actualizado = time.time()

    def libros_recordados(self) -> list[tuple[str, DatosDocumento]]:
        """Todos los libros de los que se guarda algo, con sus datos.

        Es lo que permite enseñar en una sola lista qué ha ido dejando el
        programa por el camino y de qué libro es cada cosa.
        """
        with self._cerrojo:
            return sorted(self._documentos.items(),
                          key=lambda par: (par[1].titulo or par[0]).lower())

    def recargar_documentos(self) -> None:
        """Vuelve a leer del disco lo guardado de cada libro.

        Hace falta después de sincronizar: el archivo lo ha cambiado otro
        —otro equipo, o la propia sincronización— y lo que hay en memoria es
        de antes.
        """
        with self._cerrojo:
            self._documentos.clear()
            documentos = leer_json(self._archivo_documentos, {})
            if isinstance(documentos, dict):
                for ruta, datos in documentos.items():
                    if isinstance(datos, dict):
                        self._documentos[ruta] = DatosDocumento.desde_dict(datos)
        log.info("Datos de %d documentos releídos del disco", len(self._documentos))

    def tiene_datos_de(self, ruta: str) -> bool:
        """Si hay algo guardado de ese libro."""
        with self._cerrojo:
            return ruta in self._documentos

    def olvidar_documento(self, ruta: str, marcadores: bool = True,
                          posicion: bool = True) -> bool:
        """Borra lo que se recuerda de un libro, entero o por partes.

        Se puede querer olvidar la posición de lectura y conservar los
        marcadores, o al revés: son dos cosas distintas y cuestan distinto de
        rehacer.  Un marcador lo puso una persona a mano.

        :return: Si se ha llegado a cambiar algo.
        """
        with self._cerrojo:
            datos = self._documentos.get(ruta)
            if datos is None:
                return False
            if marcadores and posicion:
                del self._documentos[ruta]
                return True
            if marcadores:
                datos.marcadores = []
            if posicion:
                datos.posicion = 0
                datos.historial = []
                datos.indice_historial = -1
            return True
