# -*- coding: utf-8 -*-
"""Ayuda de cada control: qué es, para qué sirve y qué conviene poner.

Una ventana de opciones bien hecha tiene el problema de que cada ajuste cabe en
una línea, y una línea no da para explicar **qué consigue**, **cuándo conviene
tocarlo** y **qué pasa si lo cambias**.  Quien ve la pantalla se apaña con el
contexto: el grupo donde está, el texto pequeño de al lado, lo que hay
alrededor.  Quien no la ve recorre los controles de uno en uno y solo oye el
nombre.

Aquí está esa explicación, y :kbd:`Control+F1` la enseña sobre el control en el
que se esté.  No es un consejo suelto: cada entrada dice para qué es, qué
consigue y qué se recomienda, que es lo que hay que saber para decidir.

Las ayudas se buscan por el **nombre del atributo** con el que el control vive
en su diálogo (``ocr_gris``, ``daisy_velocidad``…).  Es lo más estable que hay:
no depende del texto de la etiqueta, que cambia al traducir, ni del orden, que
cambia al reordenar la ventana.

Y se puede poner delante **el nombre de la ventana** —``DialogoCuaderno.lista``—
para los nombres que se repiten.  Hay muchos: casi todas las ventanas tienen una
``lista``, un ``filtro`` y un ``boton_guardar``, y no son la misma cosa.  Se
busca primero la clave con ventana y después la suelta, de modo que un ajuste que
se llama igual en todas partes se escribe una sola vez y el que significa algo
distinto en cada sitio se escribe donde toca.
"""

from __future__ import annotations

import wx

from nucleo.idioma import _
from nucleo.registro import obtener_registro

log = obtener_registro(__name__)


#: Ayudas registradas **en marcha**: las de los ajustes que trae un motor de voz
#: añadido.  No pueden estar en la tabla de siempre porque el programa no las
#: conoce hasta que alguien instala el paquete que las trae, y aun así tienen
#: que salir con Control+F1 como cualquier otro control.
_ANADIDAS: dict[str, tuple[str, str]] = {}


def registrar(clave: str, titulo: str, explicacion: str) -> None:
    """Añade la ayuda de un control que no está en la tabla.

    La usan los ajustes de los motores de voz, que llegan con su paquete. Si el
    paquete no trae explicación no se registra nada: es preferible que
    Control+F1 diga que no hay ayuda a que diga una inventada.
    """
    if clave and titulo and explicacion:
        _ANADIDAS[clave] = (titulo, explicacion)


def olvidar_anadidas(prefijo: str = "") -> None:
    """Quita las ayudas registradas en marcha.

    Se llama al cambiar de motor: los controles de antes ya no existen, y dejar
    sus explicaciones haría que Control+F1 contestara sobre un ajuste que no
    está en la pantalla.
    """
    for clave in [clave for clave in _ANADIDAS if clave.startswith(prefijo)]:
        del _ANADIDAS[clave]


def ayudas() -> dict[str, tuple[str, str]]:
    """Devuelve ``{atributo: (título, explicación)}`` ya traducido.

    Son las de la tabla de siempre más las que hayan registrado los motores de
    voz añadidos.
    """
    catalogo = _tabla()
    catalogo.update(_ANADIDAS)
    return catalogo


def _tabla() -> dict[str, tuple[str, str]]:
    """La tabla escrita a mano: un control del programa, una explicación.

    Es una función y no una constante porque los textos van traducidos y el
    idioma se elige después de importar el módulo.
    """
    return {
        # ---- La ventana de la voz --------------------------------------------
        "DialogoNotas.buscar": (_("Buscar dentro de las notas"), _(
            "Filtra la lista según lo que escribas. Busca en el texto de la nota y en su "
            "número, y no distingue mayúsculas ni tildes: escribiendo «isocrates» salen "
            "las de «Isócrates», que en un libro clásico es la diferencia entre encontrar "
            "y no encontrar.\n\n"
            "Con Intro se pasa a la lista sin tocar el ratón. Borrando lo escrito vuelven "
            "todas.")),
        "DialogoNotas.lista": (_("Las notas del documento"), _(
            "Todas las notas al pie del libro, en el orden en que se citan. De cada una se "
            "ve su número y el principio de lo que dice; el texto entero está en el cuadro "
            "de debajo, y va cambiando según te mueves con las flechas.\n\n"
            "Al abrirse queda elegida la nota más cercana a por donde ibas leyendo, que es "
            "la que se busca nueve de cada diez veces.\n\n"
            "Con Intro, o haciendo doble clic, se salta al texto de la nota.")),
        "DialogoNotas.texto": (_("Lo que dice la nota"), _(
            "La nota entera, sin recortar, para leerla aquí mismo sin perder el sitio en el "
            "libro. Se puede recorrer con las órdenes de lectura de tu lector de pantalla y "
            "seleccionar para copiar un trozo.\n\n"
            "Es de solo lectura: lo que se escriba no se guarda en ningún sitio.")),
        "DialogoNotas.boton_llamada": (_("Ir a donde se cita la nota"), _(
            "Lleva al pasaje del libro que llama a esta nota, que es por donde se estaba "
            "leyendo. Es lo que se quiere cuando has encontrado una nota buscando y "
            "necesitas ver de qué habla.")),
        "DialogoNotas.boton_nota": (_("Ir a la nota"), _(
            "Lleva al texto de la nota donde está de verdad, al final del libro o del "
            "capítulo. Desde allí se sigue leyendo la de al lado, que es lo que se hace "
            "cuando las notas se leen de seguido.\n\n"
            "Con Alt+Izquierda se vuelve a donde estabas.")),
        "DialogoNotas.boton_copiar": (_("Copiar la nota"), _(
            "Copia al portapapeles el texto entero de la nota elegida, para pegarlo en un "
            "documento o en un correo. Se copia lo que se ve en el cuadro de abajo.")),
        "DialogoVoz.motores": (_("Qué programa pone la voz"), _(
            "El motor de voz es el programa que convierte el texto en sonido. El que trae "
            "el visor es la voz de Windows: está siempre, arranca al instante y es la "
            "misma que usa tu lector de pantalla, así que suena a lo que ya conoces.\n\n"
            "Se pueden añadir otros como paquete, y no es un capricho. Para escuchar un "
            "libro entero la voz importa más de lo que parece: hay quien entiende una voz "
            "concreta al doble de velocidad que cualquier otra porque lleva treinta años "
            "oyéndola, y hay quien quiere una novela bien leída y necesita una que suene a "
            "persona. Ninguna de las dos puede venir dentro del programa —unas no se pueden "
            "distribuir y otras ocupan cientos de megas—, así que se instalan aparte con el "
            "botón de debajo.\n\n"
            "Cada motor trae sus propias voces y sus propios ajustes, que aparecen justo "
            "debajo al elegirlo. Lo que pongas en uno no se pierde al cambiar a otro.\n\n"
            "Si un motor deja de funcionar —porque le falta un archivo, porque no hay "
            "conexión— el programa vuelve solo a la voz de Windows y te lo dice. No se "
            "queda mudo nunca.")),
        "DialogoVoz.boton_motores": (_("Agregar o quitar motores de voz"), _(
            "Abre un menú con dos órdenes:\n\n"
            "AGREGAR MOTOR DE VOZ pide un archivo de paquete —terminado en «.motorvoz»— y "
            "lo instala. Antes de instalar nada te enseña qué motor es, de dónde sale, con "
            "qué licencia viene y cuánto ocupa, y pregunta si sigues adelante: un paquete "
            "trae código que se va a ejecutar, y tienes derecho a saber qué aceptas.\n\n"
            "LOS PAQUETES NO VIENEN DENTRO DEL PROGRAMA: entre todos ocupan casi un giga y "
            "no hay por qué bajárselos para leer, ni volver a bajárselos en cada "
            "actualización. Se descargan aparte, del mismo sitio del que bajaste el visor, "
            "y se instalan aquí. Si al lado del programa tienes una carpeta «plugins_voz», "
            "los que haya dentro valen igual: esta ventana se abre ahí.\n\n"
            "Y NO HACE FALTA NINGUNO PARA LEER: la voz de Windows viene con el programa, no "
            "se puede quitar y es la que queda cuando cualquier otra falla.\n\n"
            "QUITAR MOTOR DE VOZ desinstala uno y deja puesta la voz de Windows. Se borran "
            "sus archivos, pero no los ajustes que tuvieras hechos: si lo vuelves a "
            "instalar, lo encuentras como lo dejaste.\n\n"
            "CASI NINGÚN MOTOR TOCA NADA DE WINDOWS: se instalan copiando una carpeta y se "
            "quitan borrándola. Alguno no puede, y hay motores que necesitan apuntar sus "
            "voces en el registro de Windows para encontrarlas. Cuando es así, el aviso "
            "previo lo dice con la rama entera escrita y explicando para qué es, y solo se "
            "admite la parte del registro de tu cuenta: no hace falta ser administrador y no "
            "afecta a nadie más que use el equipo.\n\n"
            "Y al quitar uno de esos se borra todo lo que puso, incluidas las claves que se "
            "queden vacías. Lo que ya estuviera ahí antes de instalarlo no se toca: si tenías "
            "ese mismo motor instalado por tu cuenta, sigue como estaba.\n\n"
            "LO QUE HAYAS BAJADO NO SE PIERDE al actualizar un motor. Hay motores que "
            "dejan bajar voces de otros idiomas y con el tiempo acumulan cientos de megas; "
            "volver a instalar el paquete los conserva.\n\n"
            "La voz de Windows no se puede quitar. No es una limitación: es la que garantiza "
            "que el programa siga hablando pase lo que pase con los demás.\n\n"
            "Nada de esto toca el sistema. Los motores se instalan dentro de la carpeta del "
            "programa, así que llevártelo a otro equipo en un lápiz de memoria se los lleva "
            "con él.")),
        "DialogoVoz.boton_probar": (_("Escuchar cómo suena"), _(
            "Lee una frase de prueba con todo lo que tengas puesto ahora mismo en esta "
            "ventana: el motor, la voz, la velocidad y el volumen. No hace falta aceptar "
            "para oírla, y si no te convence puedes cancelar y quedarte como estabas.\n\n"
            "La frase lleva números, una página y unas comillas a propósito. Es donde más "
            "se diferencian unas voces de otras: casi todas leen bien un párrafo llano, y "
            "no todas dicen «145» igual de claro.\n\n"
            "Con un motor que arranca despacio, la primera vez tarda unos segundos. Las "
            "siguientes van sueltas.")),
        "DialogoVoz.boton_probar_motor": (_("Escuchar cómo suena"), _(
            "Lo mismo que el botón de la pestaña «Voz», puesto aquí para no tener que ir "
            "y volver: lee una frase de prueba con el motor, la voz y los ajustes que "
            "tengas puestos en este momento.\n\n"
            "Está aquí porque los ajustes de un motor se afinan escuchando. Cambias el "
            "tono, pruebas, lo vuelves a cambiar. Con un motor de trece ajustes, mandarte "
            "a la otra pestaña a cada prueba serían trece viajes de ida y vuelta.\n\n"
            "Si el botón está apagado, el motor elegido no ofrece ninguna voz: no ha "
            "podido arrancar. La pestaña «Voz» dice por qué.")),
        "DialogoVoz.voces": (_("Qué voz lee el libro"), _(
            "Las voces que hay instaladas en este equipo. Windows trae al menos una en el "
            "idioma del sistema, y se pueden añadir más desde la configuración de "
            "Windows: Hora e idioma, Voz.\n\n"
            "Para escuchar un libro entero durante horas, la voz importa más que "
            "cualquier otro ajuste. Merece la pena probar todas las que haya con el botón "
            "«Probar la voz» antes de decidirse.")),
        "DialogoVoz.seguir_idioma": (_("Cambiar de voz según el idioma del texto"), _(
            "Los libros bien hechos dicen en qué idioma está cada fragmento. Con esto, una "
            "cita en inglés se lee con una voz inglesa si la hay instalada, y se vuelve a "
            "la tuya en cuanto se acaba.\n\n"
            "Leer una cita en inglés con voz española la vuelve incomprensible, así que "
            "esto es de las cosas que más se agradecen en un libro técnico o en uno con "
            "citas. Si no hay voz de ese idioma no se toca nada.\n\n"
            "Recomendado: activado.")),
        "DialogoVoz.mover": (_("Que el cursor acompañe a la voz"), _(
            "El cursor va saltando a la frase que suena.\n\n"
            "Viene apagado porque, con el lector de pantalla en marcha, mover el cursor "
            "hace que este lea también la línea y se oigan **dos voces a la vez**. "
            "Actívalo si sigues la lectura en una línea braille, que es donde de verdad "
            "sirve.\n\n"
            "Al pausar o al detener, el cursor se coloca de todas formas donde iba la "
            "lectura, así que no hace falta esto para no perder el sitio.")),
        "DialogoVoz.cursor_al_parar": (_("Dónde queda el cursor al parar"), _(
            "Cuando la lectura se para —con la pausa o con Control+Mayús+Espacio— el "
            "cursor se coloca solo, para que puedas seguir a mano sin buscar el sitio. "
            "Aquí se elige en cuál de los dos sitios.\n\n"
            "AL PRINCIPIO DE LA FRASE es lo de siempre. Es lo que conviene cuando paras "
            "porque algo no se ha entendido: la flecha arriba vuelve a leer justo esa "
            "frase.\n\n"
            "DETRÁS DE LA FRASE es lo que conviene cuando paras para seguir leyendo tú. "
            "Las flechas continúan por lo que todavía no ha sonado, en vez de repetirte "
            "el párrafo que acabas de oír.\n\n"
            "Volver a dar a leer retoma donde estaba en los dos casos: la frase que se "
            "quedó a medias se termina, no se pierde.")),
        "DialogoVoz.resaltar": (_("Resaltar la frase que se está leyendo"), _(
            "Pinta con fondo de color la frase que suena, para seguirla con la vista si "
            "conservas resto visual.\n\n"
            "No mueve el cursor, así que no interfiere con el lector de pantalla: se puede "
            "tener activado a la vez que se escucha. A cambio repinta un tramo del texto "
            "en cada frase, y eso se nota en un libro muy largo.")),
        "DialogoVoz.descripciones": (_("Leer también las descripciones de las imágenes"), _(
            "En el texto, una ilustración es solo «[Imagen: Logo]», que no cuenta nada. "
            "Con esto, al llegar ahí la lectura sigue con la descripción que le hicieras "
            "con inteligencia artificial.\n\n"
            "Viene apagado porque alarga la lectura y solo tiene sentido en libros con las "
            "imágenes ya descritas. Las que no lo estén se leen igual que ahora.")),
        "DialogoVoz.dialogos": (_("Cambiar de tono en los diálogos"), _(
            "En una novela con mucho diálogo, oírlo todo con la misma voz obliga a "
            "reconstruir sobre la marcha quién dice cada cosa. Quien lee con los ojos ve "
            "las rayas en el margen; de oído no están.\n\n"
            "Con esto, lo que dice un personaje suena un poco más agudo que la narración, "
            "y el inciso del narrador —«dijo ella»— vuelve al tono normal.\n\n"
            "**Lo que cuesta de esto es distinguir una raya de un guion**, y el programa "
            "es prudente a propósito: la raya larga se toma siempre por diálogo, y el "
            "guion corriente solo cuando el libro no usa rayas en ninguna parte y el "
            "renglón se parece de verdad a una intervención. Ante la duda se lee como "
            "narración, porque poner voz de personaje a una lista de la compra es mucho "
            "peor que no cambiar de voz.\n\n"
            "Recomendado: activado para novela, apagado para manuales y ensayos, donde no "
            "cambia nada.")),
        "DialogoVoz.tono_dialogo": (_("Cuánto cambia el tono en los diálogos"), _(
            "De 1 a 10. Cuatro se nota sin sonar raro; de ocho en adelante la voz se "
            "convierte en un dibujo animado.\n\n"
            "Depende mucho de la voz: las voces graves aguantan más cambio que las "
            "agudas. Merece la pena probarlo con un capítulo con diálogo antes de "
            "escuchar un libro entero.")),
        "DialogoVoz.saltar_folios": (_("No decir los números de página sueltos"), _(
            "Las líneas que no son más que un número —el folio de la página— se saltan al "
            "leer de corrido.\n\n"
            "Con la vista, el ojo se salta ese número sin darse cuenta. De oído suena en "
            "medio de la frase. El documento no cambia: se ve entero, se busca entero y se "
            "exporta entero.")),
        "DialogoVoz.saltar_cabeceras": (_("No decir la cabecera que se repite"), _(
            "La línea que aparece igual en la parte de arriba de casi todas las páginas "
            "—el título del libro, el del capítulo— se salta al leer de corrido.\n\n"
            "Se reconoce midiendo: se miran las dos primeras y las dos últimas líneas de "
            "cada página y se toma por cabecera lo que salga en al menos un tercio de "
            "ellas. Por eso no se equivoca con un título de verdad, que sale una vez.")),

        # ---- Opciones: pestañas y ventana ------------------------------------
        "usar_pestanas": (_("Abrir cada documento en su propia pestaña"), _(
            "Con esto, abrir un segundo libro no cierra el primero: los dos quedan abiertos "
            "y se cambia entre ellos con Control+Tabulador o con Control+Mayús+P.\n\n"
            "Recomendado: activado si estudias, porque comparar dos libros es la mitad del "
            "trabajo; apagado si lees una novela cada vez y prefieres no tener que pensar "
            "en pestañas.")),
        "restaurar_documentos": (_("Volver a abrir lo que quedó abierto"), _(
            "Al arrancar, se vuelven a abrir los documentos que tenías abiertos al cerrar, "
            "cada uno por donde ibas.\n\n"
            "Recomendado: activado. Es lo que hace que cerrar el programa a media tarde no "
            "cueste nada, y evita el trabajo de volver a buscar seis archivos.")),
        "pestanas_al_abrir": (_("Qué hacer al abrir con otro ya abierto"), _(
            "Si al abrir un documento se pone en una pestaña nueva, se sustituye el que "
            "había, o se pregunta cada vez.\n\n"
            "Recomendado: preguntar la primera semana y elegir después. La ventana que "
            "pregunta lleva una casilla para dejar de preguntar sin venir hasta aquí.")),
        "mostrar_arbol": (_("Enseñar el árbol de contenido"), _(
            "Pone a la izquierda del texto el índice del documento, como un árbol de "
            "capítulos y apartados. Y no solo el índice: también una rama por cada clase de "
            "elemento que el documento tenga —las imágenes, las tablas, los enlaces, las "
            "listas—, con lo que se ve de un vistazo todo lo que hay dentro.\n\n"
            "Se va con F6 y se vuelve con F6, y al llegar el árbol ya está colocado por "
            "donde va la lectura. Con Intro se salta al elemento.\n\n"
            "SOBRE CUALQUIER ENTRADA, LA TECLA DE APLICACIONES O MAYÚSCULAS+F10 ABREN UN "
            "MENÚ con lo que se puede hacer con ella, y cambia según lo que sea: en una "
            "imagen se ofrece verla o describirla con inteligencia artificial; en una tabla, "
            "abrirla para recorrerla; en un enlace, seguirlo; y en cualquiera, ir, leer en "
            "voz alta desde ahí, copiar su texto o poner un marcador.\n\n"
            "Y sobre la cabecera de una rama, lo mismo pero para todos a la vez: describir "
            "de una sola vez las ochenta imágenes de un cómic, o sacar a un archivo la lista "
            "entera de las tablas de un manual.\n\n"
            "Ocupa una zona más por la que pasar con F6. Si lo que quieres es saltar a un "
            "capítulo de vez en cuando, sale más cómodo Control+I, que abre el mismo índice "
            "en una ventana y la cierra al elegir.")),
        "barra_recuentos": (_("Enseñar el recuento de palabras y páginas"), _(
            "Pone en la barra de estado cuántas palabras y cuántas páginas tiene el "
            "documento.\n\n"
            "Es un dato que con la vista se estima con el grosor del libro y de oído no hay "
            "manera de estimar. Saber si lo que queda son diez páginas o ciento diez cambia "
            "lo que uno decide hacer.")),
        "mostrar_bienvenida": (_("Enseñar el resumen de teclas al arrancar"), _(
            "Mientras no hay ningún documento abierto, el cuadro de lectura no se queda "
            "vacío: enseña un resumen de lo que el programa sabe hacer y con qué tecla, y "
            "se recorre con las flechas igual que un libro.\n\n"
            "Es lo que hace falta el primer día, cuando no se sabe ni por dónde empezar. "
            "Cuando ya te sabes las teclas es una pantalla de más entre abrir el programa y "
            "abrir el libro, y por eso se puede apagar.\n\n"
            "Apagado quedan dos líneas —el nombre del programa y «Control+O para abrir»—, "
            "porque una ventana en blanco no dice nada de oído: no se sabe si está lista, "
            "si el documento no se ha abierto o si se ha quedado colgada.\n\n"
            "No se pierde nada: el resumen entero, con todas las teclas y su explicación, "
            "sigue en Mayús+F1.")),
        "renglon_frase": (_("Empezar cada frase en un renglón nuevo"), _(
            "La lectura continua del lector de pantalla —NVDA+A— va diciendo el texto "
            "renglón a renglón y deja el cursor al principio del renglón que está sonando. "
            "Con cada párrafo en una sola línea, al parar la lectura el cursor aparece al "
            "principio del párrafo entero: se han oído veinte líneas y hay que volver a "
            "bajar por ellas para seguir a mano.\n\n"
            "Con esto marcado el renglón es la frase, así que al parar el cursor se queda en "
            "la frase que estaba sonando, y las flechas arriba y abajo van de frase en "
            "frase.\n\n"
            "No cambia el texto ni una sola posición: lo único que ocurre es que el espacio "
            "que separa dos frases se enseña como un salto de línea. Los marcadores, las "
            "notas, los resaltados y por dónde ibas siguen donde estaban, y lo que se copia "
            "sale con sus espacios.\n\n"
            "Recomendado: activado si lees de oído con la lectura continua; apagado si lees "
            "con la vista, porque un párrafo troceado en renglones cortos se ve raro.")),
        "ancho_linea": (_("Ancho máximo del renglón"), _(
            "Corta las líneas a los caracteres que digas, en vez de usar todo el ancho de "
            "la ventana. Con 0 se usa todo el ancho.\n\n"
            "Un renglón muy largo cansa al leerlo con la vista y descoloca a quien usa "
            "magnificación, porque hay que barrer toda la pantalla y volver. Unos 80 "
            "caracteres es lo que usan los libros de papel, y no es casualidad.\n\n"
            "Recomendado: 80 si lees con resto visual; 0 si lees solo de oído, porque "
            "entonces no cambia nada.")),
        "tamano": (_("Tamaño de la letra"), _(
            "El cuerpo con el que se ve el texto del documento.\n\n"
            "No afecta a lo que dice el lector de pantalla ni a lo que se exporta: es solo "
            "cómo se ve. Para agrandar mucho, además de esto suele hacer falta la lupa del "
            "sistema.")),
        "usar_colores": (_("Usar colores propios"), _(
            "Deja elegir el color del texto y del fondo en lugar de usar los del sistema.\n\n"
            "Sirve para el contraste que a cada uno le va bien: hay quien lee mucho mejor en "
            "amarillo sobre negro que en negro sobre blanco. Si usas el modo de alto "
            "contraste de Windows, conviene dejarlo apagado para que mande el sistema.")),
        "marcar_notas": (_("Señalar las llamadas de nota al pie"), _(
            "Hace que el numerito volado de una nota se anuncie al pasar por él, y que la "
            "tecla O salte de una llamada a la siguiente.\n\n"
            "Con la vista, ese número se ve y se decide si se va a la nota. De oído, sin "
            "esto, la nota aparece en medio de la frase o no aparece.\n\n"
            "Recomendado: activado si estudias; apagado para escuchar una novela de un "
            "tirón.")),
        "avisar_elementos": (_("Cómo se avisa de los elementos"), _(
            "Qué pasa al pasar el cursor por un título, una tabla, una imagen o una cita: "
            "un sonido corto, decirlo con palabras, las dos cosas o nada.\n\n"
            "El sonido es mucho más rápido que la palabra y no interrumpe la lectura, pero "
            "hay que aprenderse cuál es cuál. Decirlo se entiende desde el primer minuto y "
            "corta el hilo.\n\n"
            "Recomendado: sonido cuando ya te has acostumbrado; decirlo la primera semana.")),
        "sonidos_activos": (_("Sonidos de navegación"), _(
            "Enciende los sonidos cortos que avisan de lo que se pasa: un título, una tabla, "
            "el final del documento, un resultado de búsqueda.\n\n"
            "Es una de las cosas que más se agradecen y de las que menos gente encuentra: "
            "dan la información sin robarle el turno a la voz.")),
        "solo_navegar": (_("Sonar solo al saltar entre elementos"), _(
            "Los sonidos suenan únicamente al usar las teclas que saltan de elemento en "
            "elemento (H, T, G...), y no al bajar línea a línea con las flechas.\n\n"
            "Recomendado: activado si te resulta cargante oír un sonido cada vez que pasas "
            "por un título leyendo de corrido.")),
        "volumen": (_("Volumen de los sonidos"), _(
            "Lo fuerte que suenan los avisos, sin tocar el volumen del sistema ni el de la "
            "voz.\n\n"
            "Conviene bajarlo bastante: los avisos suenan encima de la voz y solo tienen "
            "que notarse, no taparla. El botón de al lado los prueba.")),
        "sonido_prueba": (_("Probar el sonido"), _(
            "Reproduce uno de los avisos con el volumen que hayas puesto, para no tener que "
            "cerrar las opciones y ponerse a navegar para oírlo.")),

        # ---- Opciones: PDF ----------------------------------------------------
        "pdf_estructura": (_("Aprovechar la estructura de los PDF accesibles"), _(
            "Cuando un PDF viene **etiquetado** —lleva dentro qué es cada cosa: un título, "
            "una tabla, una lista—, se usa esa información en vez de deducirla.\n\n"
            "Es la minoría de los PDF, y en esa minoría es lo mejor que hay: son los datos "
            "que puso quien hizo el documento.\n\n"
            "Recomendado: activado. Apagarlo solo tiene sentido si un archivo concreto trae "
            "las etiquetas mal puestas, que pasa.")),
        "pdf_geometria": (_("Deducir la estructura de los PDF que no la traen"), _(
            "En un PDF sin etiquetar —la inmensa mayoría— el programa **mide** cada página "
            "y deduce lo que el archivo no dice: los títulos por su tamaño de letra y su "
            "numeración, las listas por sus viñetas, las tablas por cómo se alinean sus "
            "columnas, las notas al pie por estar abajo y en letra menor.\n\n"
            "Es la diferencia entre un churro de texto sin apartados y un documento que se "
            "recorre con H, T y L.\n\n"
            "Recomendado: activado. Se apaga si en un archivo concreto la deducción hace "
            "más daño que bien; y un título suelto mal deducido se arregla mejor con "
            "Control+Mayús+E encima de él.")),

        # ---- Opciones: inteligencia artificial ---------------------------------
        "ia_proveedor": (_("Qué inteligencia artificial se usa"), _(
            "De dónde sale la IA: apagada, un servicio de pago con tu clave, o un modelo "
            "**instalado en este equipo**.\n\n"
            "El modelo local no tiene cuenta, no tiene tarjeta, no manda nada a ningún "
            "sitio y funciona sin conexión; a cambio ocupa gigabytes y va más lento. Los "
            "servicios de pago describen mejor y cuestan céntimos por imagen.\n\n"
            "Recomendado: local si te preocupa la privacidad o vas a describir muchas "
            "imágenes; un servicio si quieres la mejor descripción de unas pocas.")),
        "ia_espera": (_("Segundos de espera a la respuesta"), _(
            "Cuánto se espera antes de dar por perdida una petición.\n\n"
            "Con un modelo local y un equipo modesto, describir una imagen puede pasar del "
            "minuto: si te salen errores de tiempo agotado, sube esto antes de pensar que "
            "algo está roto.")),
        "ia_guardar": (_("Guardar las descripciones"), _(
            "Guarda junto al documento lo que la IA describa, de modo que se pida una vez y "
            "vuelva siempre.\n\n"
            "Recomendado: activado. Sin esto, cada vez que abras el libro habría que "
            "describir —y pagar— otra vez las mismas imágenes.")),
        "ia_anunciar": (_("Decir la descripción al llegar a una imagen"), _(
            "Al pasar el cursor por una imagen que ya tiene descripción guardada, se dice "
            "sola.\n\n"
            "Recomendado: activado. Es lo que hace que el trabajo de describir sirva "
            "mientras se lee y no solo cuando uno se acuerda de preguntar.")),
        "ia_claves": (_("Clave del servicio"), _(
            "La clave que te da el servicio de inteligencia artificial para poder usarlo.\n\n"
            "Se guarda en tu equipo, en la carpeta de datos del programa, y no se manda a "
            "ningún sitio que no sea el propio servicio.")),
        "ia_claves_anthropic": (_("Clave de Anthropic"), _(
            "La clave de la cuenta de Anthropic. Se guarda solo en este equipo.")),
        "ia_claves_openai": (_("Clave de OpenAI"), _(
            "La clave de la cuenta de OpenAI. Se guarda solo en este equipo.")),
        "ia_url": (_("Dirección del servicio local"), _(
            "Dónde escucha el programa de IA que tengas instalado. Lo normal es no tocarlo: "
            "se rellena solo con la dirección que usa Ollama.")),
        "ia_url_openai": (_("Dirección del servicio compatible"), _(
            "Para usar otro servicio que hable el mismo idioma que OpenAI: un servidor "
            "propio, uno de empresa o uno alternativo. Si no sabes qué es esto, no hace "
            "falta tocarlo.")),
        "ia_servicio_openai": (_("Modelo del servicio compatible"), _(
            "Qué modelo pedirle a ese servicio. Cada uno tiene sus nombres.")),
        "boton_modelos": (_("Ver los modelos disponibles"), _(
            "Pregunta al servicio qué modelos hay y deja elegir uno de la lista, en vez de "
            "tener que escribir su nombre exacto sin equivocarse.")),
        "boton_probar": (_("Probar la conexión"), _(
            "Hace una petición de prueba y dice si funciona.\n\n"
            "Merece la pena pulsarlo antes de lanzar una tanda de cien imágenes: así el "
            "fallo aparece ahora y no a la mitad.")),
        "boton_prompts": (_("Instrucciones de descripción"), _(
            "Abre la lista de instrucciones con las que se le puede pedir una descripción a "
            "la IA, para editarlas o añadir las tuyas.\n\n"
            "No hay una instrucción buena para todo: la que describe bien un cuadro no "
            "describe bien un esquema eléctrico.")),
        "boton_consumo": (_("Lo que llevas gastado"), _(
            "Enseña cuántas peticiones se han hecho y lo que han costado, para que la "
            "factura no sea una sorpresa.\n\n"
            "Con una IA local siempre es cero, y por eso mismo el dato dice algo.")),

        # ---- Opciones: integración con Windows --------------------------------
        "integracion_formatos": (_("Formatos que abre el programa"), _(
            "Los tipos de archivo que Windows abrirá con este programa al hacer doble clic.\n\n"
            "Se marcan solo los que quieras: si ya tienes otro lector para los PDF y solo "
            "quieres este para los EPUB, se marca el EPUB y ya está.")),
        "integracion_menu": (_("Salir en el menú del botón derecho"), _(
            "Añade el programa al menú que sale al pulsar el botón derecho sobre un "
            "archivo, para abrirlo sin cambiar qué programa lo abre por omisión.")),
        "integracion_abrir_con": (_("Salir en «Abrir con»"), _(
            "Hace que el programa aparezca en la lista de «Abrir con» de Windows, aunque no "
            "sea el que abre ese tipo de archivo normalmente.")),

        # ---- Opciones: sincronización y sistema --------------------------------
        "sincro_auto": (_("Sincronizar sola al arrancar y al cerrar"), _(
            "Manda y trae los cambios por su cuenta, sin tener que acordarse.\n\n"
            "Recomendado: activado si usas dos equipos. Acordarse de sincronizar a mano "
            "funciona hasta el día que no te acuerdas, que es el día que pierdes por dónde "
            "ibas.")),
        "a_bandeja": (_("Al minimizar, quedarse en la bandeja"), _(
            "Al minimizar, el programa desaparece de la barra de tareas y queda solo como "
            "un icono junto al reloj.\n\n"
            "Va con las teclas globales: sirve para escuchar un libro mientras se trabaja "
            "en otra cosa, sin que el programa estorbe al ir cambiando de ventana.")),
        "globales_activas": (_("Teclas globales"), _(
            "Hace que unas pocas teclas funcionen **aunque el programa no tenga el foco**: "
            "parar y seguir la lectura, subir o bajar la velocidad, saltar de párrafo.\n\n"
            "Es lo que permite escuchar un libro mientras se escribe un correo. Si otro "
            "programa ya usa una de esas combinaciones, el botón de comprobar lo dice y se "
            "puede cambiar.")),
        "lista_globales": (_("Las teclas globales"), _(
            "Qué hace cada combinación. Se cambia con el botón de al lado, y las que estén "
            "cogidas por otro programa se señalan al comprobarlas.")),
        "boton_comprobar_teclas": (_("Comprobar las teclas globales"), _(
            "Prueba una a una si Windows deja registrar cada combinación.\n\n"
            "Es lo que evita el problema clásico: una tecla global que no hace nada porque "
            "otro programa se la quedó primero, sin que nadie avise.")),
        "boton_cambiar_tecla": (_("Cambiar esta tecla"), _(
            "Abre una ventana donde se pulsa la combinación que se quiera. Se recoge tal "
            "cual se pulse, así que no hay que escribirla.")),
        "boton_quitar_tecla": (_("Quitar esta tecla"), _(
            "Deja esa orden sin tecla global. Sigue funcionando dentro del programa.")),
        "boton_teclas_fabrica": (_("Volver a las teclas de fábrica"), _(
            "Devuelve todas las teclas globales a como venían.")),
        "nivel": (_("Detalle del registro de actividad"), _(
            "Cuánto apunta el programa de lo que hace.\n\n"
            "Lo normal apunta lo que pasa y lo que falla. El detallado apunta cada paso y "
            "es lo que hay que poner **antes** de reproducir un problema, para que quede "
            "constancia de él y se pueda mandar.\n\n"
            "El registro no lleva el contenido de tus libros: lleva qué se abrió, cuánto "
            "tardó y qué falló.")),
        "cuaderno": (_("Pestañas de esta ventana"), _(
            "Las secciones de las opciones. Se cambia entre ellas con Control+Tabulador, o "
            "con las flechas cuando el foco está en las propias pestañas.\n\n"
            "En cualquier control de cualquier pestaña, Control+F1 explica qué es ese "
            "ajuste, qué consigue y qué conviene poner.")),

        # ---- Últimos sueltos ---------------------------------------------------
        "DialogoDatos.casillas": (_("Qué datos borrar"), _(
            "Marca las clases de datos que quieras eliminar. Se dice cuánto ocupa cada una "
            "y se avisa antes de borrar; los marcadores y las notas no se tocan desde "
            "aquí.")),
        "DialogoDiccionario.boton_buscar": (_("Buscar la palabra"), _(
            "Busca la definición en la fuente elegida arriba.\n\n"
            "El diccionario de la Academia y el Wikcionario dan la definición del "
            "diccionario; la inteligencia artificial es la única que entiende **en qué "
            "sentido** se usa la palabra en la frase que estabas leyendo, que muchas veces "
            "es justo lo que hace falta.")),
        "DialogoIdiomasOCR.precisa": (_("Reconocimiento más preciso"), _(
            "Usa el modelo grande en vez del rápido.\n\n"
            "Tarda bastante más por página y se equivoca bastante menos. Merece la pena en "
            "un escaneo torcido, en letra pequeña o en un documento que vayas a citar; para "
            "leer un folleto, el rápido basta.")),
        "DialogoImportarModelo.aceptar": (_("Importar el modelo"), _(
            "Deja el modelo instalado y listo para usar. Puede tardar: son archivos de "
            "varios gigabytes que hay que copiar.")),
        "DialogoPrimerUso.texto": (_("Explicación del paso"), _(
            "Lo que se cuenta en esta pantalla del recorrido.\n\n"
            "Es un cuadro de solo lectura y no una etiqueta, a propósito: así el texto se "
            "recorre con las flechas y se puede releer la parte que no se haya entendido, "
            "que es lo que hace falta para aprender algo y no solo para oírlo pasar.")),
        "DialogoPrimerUso.practica": (_("Recuadro para practicar la tecla"), _(
            "Pulsa aquí la tecla que se acaba de explicar y el programa dice si era esa.\n\n"
            "Aprender una tecla pulsándola cuesta una vez; leyéndola en una lista, varias. "
            "Y cuando quieras hacerlo con un libro de verdad, en Ayuda está «Practicar».")),
        "DialogoPrimerUso.boton_siguiente": (_("Paso siguiente"), _(
            "Pasa a la pantalla siguiente del recorrido. En la última dice «Terminar».")),
        "DialogoPrimerUso.boton_anterior": (_("Paso anterior"), _(
            "Vuelve a la pantalla anterior, por si se quiere releer algo.")),
        "DialogoPrimerUso.boton_salir": (_("Salir del recorrido"), _(
            "Cierra el recorrido. Queda en Ayuda, Recorrido guiado, y se puede volver a "
            "entrar por la parte que se quiera repasar.")),
        "DialogoPronunciacion.cuaderno": (_("Reglas y diccionario"), _(
            "Las dos formas de arreglar cómo suena algo: las reglas, que cambian un texto "
            "por otro en todo el libro, y el diccionario de nombres propios.\n\n"
            "Es lo que hace que los nombres de una saga dejen de sonar mal durante "
            "ochocientas páginas.")),
        "DialogoTemporizador.boton_quitar": (_("Quitar el temporizador"), _(
            "Cancela el apagado programado. La lectura sigue hasta que la pares tú.")),
        "DialogoProgreso.boton": (_("Cancelar"), _(
            "Corta lo que se esté haciendo. Lo hecho hasta ese momento no se pierde: se "
            "queda lo que ya estuviera terminado.")),
        "DialogoAsistenteIA.boton_siguiente": (_("Paso siguiente"), _(
            "Pasa al siguiente paso de la instalación. Lo que ya se haya hecho no hay que "
            "repetirlo: cada paso se da por bueno en cuanto termina.")),
        "DialogoAsistenteIA.boton_anterior": (_("Paso anterior"), _(
            "Vuelve al paso de antes, por si hace falta releer lo que decía o repetir una "
            "descarga que se cortó.")),
        "DialogoAsistenteIA.boton_salir": (_("Salir del asistente"), _(
            "Cierra el asistente. Lo que ya se haya descargado o instalado se queda, y al "
            "volver se sigue por donde iba.")),
        "DialogoAsistenteIA.progreso": (_("Cómo va la descarga"), _(
            "Lo que lleva descargado o instalado el paso actual. Los modelos ocupan "
            "gigabytes: con una conexión normal es cuestión de minutos, no de segundos.")),
        "DialogoRegistro.boton_siguiente": (_("Siguiente aparición"), _(
            "Va a la siguiente línea del registro que contenga lo buscado.")),
        "DialogoRegistro.boton_anterior": (_("Aparición anterior"), _(
            "Va a la anterior línea del registro que contenga lo buscado.")),
        "DialogoAyudaOpcion.texto": (_("La explicación"), _(
            "Qué es esto, qué consigue y qué conviene poner.\n\n"
            "Va en un cuadro de solo lectura y no en un aviso corriente porque así **se "
            "puede recorrer**: con las flechas, línea a línea, volviendo atrás sobre lo que "
            "no se ha entendido, y copiándolo si hace falta. Un cuadro de mensaje se lee de "
            "una tirada y se cierra.")),
        "DialogoAyudaOpcion.lista": (_("Los demás ajustes"), _(
            "Todo lo que tiene explicación escrita, por orden alfabético.\n\n"
            "Sirve para leerse las opciones enteras de corrido sin ir control por control, "
            "que es como se descubre lo que uno no sabía que existía.")),
        "DialogoCapturarTecla.campo": (_("Pulsa la combinación"), _(
            "Pulsa aquí la combinación de teclas que quieras usar y se recoge tal cual, sin "
            "tener que escribirla.\n\n"
            "En esta ventana, Control+F1 no abre la ayuda: se recoge como cualquier otra "
            "tecla, porque si no sería la única que no se podría asignar.")),
        "DialogoCapturarTecla.aceptar": (_("Usar esta combinación"), _(
            "Asigna la combinación que se acaba de pulsar. Si ya está cogida por otro "
            "programa, se dice.")),

        # ---- Preguntar a la IA ----------------------------------------------
        "DialogoPreguntar.pregunta": (_("Tu pregunta sobre el documento"), _(
            "Lo que quieras preguntarle a la inteligencia artificial sobre lo que estás "
            "leyendo: «resume este capítulo», «qué dice de la amortización», «hazme cinco "
            "preguntas de examen».\n\n"
            "No se manda el libro entero: se manda el trozo que digas abajo, que es lo que "
            "hace que la respuesta hable de lo que estás leyendo y no de lo que el modelo "
            "recuerde del mundo.")),
        "DialogoPreguntar.ambito": (_("Sobre qué se pregunta"), _(
            "Qué trozo del documento se le manda con la pregunta: lo que estás leyendo, el "
            "capítulo, lo que tengas seleccionado o el documento entero si cabe.\n\n"
            "Cuanto más pequeño, más ajustada es la respuesta y menos cuesta. Preguntar "
            "sobre el libro entero solo tiene sentido para «de qué va esto».")),
        "DialogoPreguntar.respuesta": (_("La respuesta"), _(
            "Lo que ha contestado la inteligencia artificial. Es un cuadro de solo lectura, "
            "así que se recorre con las flechas y se puede releer y copiar.\n\n"
            "Conviene recordar una cosa: la IA se equivoca con seguridad y sin avisar. Para "
            "entender algo va muy bien; para citar un dato, hay que ir al libro.")),
        "DialogoPreguntar.propia": (_("Escribir la pregunta a mano"), _(
            "Deja escribir una pregunta cualquiera en vez de elegir una de las preparadas.")),
        "DialogoPreguntar.boton_preguntar": (_("Preguntar"), _(
            "Manda la pregunta con el trozo de documento elegido. Tarda unos segundos y se "
            "puede parar.")),

        # ---- Describir todas las imágenes ------------------------------------
        "DialogoDescribirTodo.eleccion": (_("Con qué instrucción describirlas"), _(
            "La misma instrucción se usa para todas las imágenes de la tanda. Elige la que "
            "encaje con el documento: un manual técnico y una novela no piden lo mismo.")),
        "DialogoDescribirTodo.con_datos": (_("Sacar también los datos de los gráficos"), _(
            "Además de describir cada imagen, intenta sacar la tabla de los que sean "
            "gráficos y el recorrido de los que sean diagramas.\n\n"
            "Tarda el doble, porque son dos preguntas por imagen. En un informe lleno de "
            "gráficos vale cada segundo: la diferencia es entre quince frases vagas y "
            "quince tablas que se recorren.")),
        "DialogoDescribirTodo.saltar_con_texto": (_("Saltar las que ya tienen descripción"), _(
            "No vuelve a describir las imágenes que ya traen un texto alternativo en el "
            "documento o una descripción guardada.\n\n"
            "Recomendado: activado. Lo que ya está descrito no hace falta pagarlo otra vez, "
            "y lo que trae el libro suele ser mejor que lo que adivina la IA.")),
        "DialogoDescribirTodo.pausa": (_("Espera entre imágenes"), _(
            "Segundos que se esperan entre una imagen y la siguiente.\n\n"
            "Los servicios de pago limitan cuántas peticiones se les pueden hacer por "
            "minuto, y pasarse significa que la tanda se corta a la mitad. Con una IA "
            "local, esto se puede dejar en cero.")),
        "DialogoDescribirTodo.registro": (_("Cómo va la tanda"), _(
            "Lo que va pasando, imagen por imagen: cuál se está describiendo, cuáles han "
            "salido y cuáles han fallado.\n\n"
            "Se escribe según ocurre, de modo que si algo va mal se ve en cuál y no al "
            "final.")),
        "DialogoDescribirTodo.boton_empezar": (_("Empezar a describir"), _(
            "Arranca la tanda. Se pueden describir cien imágenes de un libro de una vez y "
            "seguir leyendo mientras tanto.")),
        "DialogoDescribirTodo.boton_parar": (_("Parar la tanda"), _(
            "Corta después de la imagen que se esté describiendo. Lo hecho hasta ahí queda "
            "guardado y no hay que repetirlo.")),

        # ---- Instrucciones de la IA -------------------------------------------
        "DialogoPrompts.lista": (_("Instrucciones guardadas"), _(
            "Las instrucciones con las que se le puede pedir una descripción a la IA. Una "
            "de ellas es la preferida y es la que sale marcada por omisión.\n\n"
            "Están aquí porque no hay una instrucción buena para todo: la que describe bien "
            "un cuadro no describe bien un esquema eléctrico.")),
        "DialogoPrompts.boton_nuevo": (_("Nueva instrucción"), _(
            "Crea una instrucción propia. Es el sitio donde escribir «descríbeme esto como "
            "si fuera para un examen de anatomía» y tenerlo para siempre.")),
        "DialogoPrompts.boton_editar": (_("Editar la instrucción"), _(
            "Cambia el texto de la instrucción elegida. Retocar una que casi vale suele dar "
            "mejor resultado que escribir una desde cero.")),
        "DialogoPrompts.boton_duplicar": (_("Duplicar la instrucción"), _(
            "Hace una copia para poder retocarla sin perder la original. Es la forma "
            "cómoda de partir de una de las que trae el programa.")),
        "DialogoPrompts.boton_eliminar": (_("Eliminar la instrucción"), _(
            "Borra la instrucción elegida. Las que trae el programa se pueden restaurar.")),
        "DialogoPrompts.boton_preferido": (_("Marcar como preferida"), _(
            "Hace que esta sea la que salga elegida al pedir una descripción.")),
        "DialogoEditarPrompt.nombre": (_("Nombre de la instrucción"), _(
            "Cómo se llamará en la lista. Conviene que diga para qué sirve —«esquemas», "
            "«cuadros», «gráficas»—, porque es lo único que se oye al elegirla.")),
        "DialogoEditarPrompt.texto": (_("Texto de la instrucción"), _(
            "Lo que se le dice a la inteligencia artificial junto con la imagen.\n\n"
            "Cuanto más concreta, mejor sale: «di cuántas piezas hay, cómo se llaman y cómo "
            "están conectadas» da un resultado mucho más útil que «describe la imagen».")),

        # ---- Corregir la estructura -------------------------------------------
        "DialogoCorregir.tipo": (_("Qué es en realidad este elemento"), _(
            "Cambia lo que el programa ha deducido: convertir en encabezado lo que tomó por "
            "un párrafo, o al revés.\n\n"
            "Hace falta sobre todo en los PDF sin estructura, donde los títulos se deducen "
            "midiendo el tamaño de la letra y a veces se cuelan un pie de foto o un número "
            "de página.")),
        "DialogoCorregir.nivel": (_("Nivel del encabezado"), _(
            "Si es un capítulo (nivel 1), un apartado (2) o un subapartado (3), y así hasta "
            "el seis.\n\n"
            "Importa más de lo que parece: es lo que hace que al moverse por niveles con "
            "las teclas 1 a 6 no falte un peldaño y que el índice salga bien anidado.")),
        "DialogoCorregir.quitar": (_("Quitar esta marca"), _(
            "Deja el texto como texto normal. Es lo que se hace con la cabecera que se "
            "repite en cada página y que el programa tomó por un título.")),
        "DialogoEstructura.lista": (_("Correcciones propuestas"), _(
            "Lo que la inteligencia artificial cree que está mal en la estructura deducida "
            "del documento, una propuesta por línea, con lo que hay y lo que propone.\n\n"
            "Nada se aplica hasta que lo digas tú: son propuestas y algunas están mal.")),
        "DialogoEstructura.boton_revisar": (_("Pedir la revisión"), _(
            "Le manda a la IA el esqueleto del documento —los títulos, no el texto— y le "
            "pide que diga cuáles parecen mal.\n\n"
            "Se manda solo el esqueleto porque es lo que hace que quepa y que salga barato: "
            "quinientos títulos ocupan menos que un capítulo.")),
        "DialogoEstructura.boton_todas": (_("Marcar todas"), _(
            "Marca todas las propuestas para aplicarlas de una vez.")),
        "DialogoEstructura.boton_ninguna": (_("Desmarcar todas"), _(
            "Desmarca todas las propuestas, para ir eligiendo una a una.")),
        "DialogoEstructura.boton_aplicar": (_("Aplicar lo marcado"), _(
            "Cambia la estructura del documento con las propuestas que hayas marcado.\n\n"
            "El archivo no se toca: lo que se guarda es la corrección, junto a los "
            "marcadores, y vuelve la próxima vez que lo abras.")),

        # ---- Exportar --------------------------------------------------------
        "DialogoExportarDaisy.modo": (_("Qué DAISY se genera"), _(
            "Solo el texto sale en un segundo y lo lee la voz del propio reproductor.\n\n"
            "Texto y voz sincronizados frase a frase tarda lo que tarde en grabarse, y a "
            "cambio da un libro hablado que se puede seguir a la vez en la línea braille. Es "
            "lo que hacen las bibliotecas para personas ciegas, y lo que normalmente no se "
            "puede generar sin herramientas de pago.")),
        "DialogoExportarAudio.boton_generar": (_("Generar el audio"), _(
            "Empieza a grabar el documento con la voz elegida.\n\n"
            "Un libro entero tarda: se puede seguir usando el programa mientras tanto y se "
            "avisa al terminar. Con el reparto «un solo archivo con marcas de capítulo», el "
            "MP3 lleva sus capítulos dentro y el reproductor del móvil o del coche deja "
            "saltar de uno a otro.")),

        # ---- El registro -----------------------------------------------------
        "DialogoRegistro.lista": (_("Lo que ha ido haciendo el programa"), _(
            "El registro: lo que el programa ha hecho y lo que le ha salido mal, con su "
            "hora.\n\n"
            "Es lo que hay que mirar —o mandar— cuando algo no funciona. No lleva el "
            "contenido de tus libros: lleva qué se abrió, cuánto tardó y qué falló.")),
        "DialogoRegistro.filtro": (_("Filtrar el registro"), _(
            "Se queda con las líneas que contengan lo que escribas. Con «error» se ve de "
            "golpe todo lo que ha fallado.")),
        "DialogoRegistro.busqueda": (_("Buscar en el registro"), _(
            "Busca un texto y va saltando de aparición en aparición con los botones de "
            "siguiente y anterior.")),
        "DialogoRegistro.nivel_guardado": (_("Cuánto detalle se guarda"), _(
            "Cuánto se apunta en el archivo de registro.\n\n"
            "Normal apunta lo que pasa y lo que falla. Detallado apunta además cada paso, y "
            "es lo que hay que poner **antes** de reproducir un problema para que quede "
            "constancia de él.\n\n"
            "Recomendado: normal, salvo que estés persiguiendo un fallo.")),
        "DialogoRegistro.en_vivo": (_("Seguir el registro en vivo"), _(
            "Va añadiendo las líneas nuevas según ocurren, sin tener que recargar.\n\n"
            "Sirve para ver qué hace el programa mientras se hace algo en otra ventana.")),
        "DialogoRegistro.sesiones": (_("De qué sesión"), _(
            "Cada vez que se abre el programa se empieza un registro nuevo. Aquí se elige "
            "cuál mirar, incluidos los de días anteriores.")),
        "DialogoRegistro.boton_recargar": (_("Recargar"), _(
            "Vuelve a leer el archivo de registro para traer lo que haya pasado desde que "
            "se abrió esta ventana.")),
        "DialogoRegistro.boton_copiar": (_("Copiar el registro"), _(
            "Copia al portapapeles lo que estás viendo, para pegarlo en un correo o en un "
            "informe de fallo.")),
        "DialogoRegistro.boton_carpeta": (_("Abrir la carpeta del registro"), _(
            "Abre en el explorador la carpeta donde están los archivos de registro, por si "
            "hace falta adjuntar uno.")),
        "DialogoRegistro.boton_vaciar": (_("Vaciar el registro"), _(
            "Borra los registros guardados. No afecta a nada más del programa.")),

        # ---- Actualizaciones y modelos ----------------------------------------
        "DialogoActualizacion.texto": (_("Qué trae la versión nueva"), _(
            "La lista de cambios de la versión que se ofrece, tal y como viene escrita.\n\n"
            "Conviene leerla antes de actualizar: aquí es donde se dice si algo cambia de "
            "sitio o si hay que volver a abrir los libros.")),
        "DialogoActualizacion.boton_instalar": (_("Descargar e instalar"), _(
            "Trae la versión nueva y la deja instalada. **Tus datos no se tocan**: los "
            "marcadores, las notas, las descripciones y las preferencias están en una "
            "carpeta aparte y siguen ahí después de actualizar.")),
        "DialogoImportarModelo.campo_nombre": (_("Nombre del modelo"), _(
            "Cómo se llamará dentro del programa el modelo de inteligencia artificial que "
            "estás importando. Es el nombre que se verá al elegirlo.")),
        "DialogoContrasena.campo": (_("Contraseña del documento"), _(
            "La contraseña que hace falta para leer este PDF.\n\n"
            "Hay dos clases muy distintas y el programa ya las distingue: la que solo "
            "prohíbe imprimir o copiar se salta sola y no llega a preguntarse; esta es la "
            "otra, la que de verdad cifra el contenido.\n\n"
            "No se guarda en ningún sitio ni se manda a ninguna parte: se usa para abrir el "
            "archivo y se olvida.")),

        # ---- El visor y el reproductor ----------------------------------------
        "DialogoHtml.boton_navegador": (_("Abrir en el navegador"), _(
            "Abre lo que estás viendo en tu navegador, donde tu lector de pantalla usa "
            "todas sus órdenes de página web: saltar por encabezados, por tablas, por "
            "listas o por enlaces.")),
        "DialogoHtml.boton_guardar": (_("Guardar como página web"), _(
            "Escribe esto en un archivo HTML completo, con su estilo y con la referencia de "
            "dónde sale, para poder abrirlo en cualquier sitio o mandarlo por correo.")),
        "DialogoHtml.boton_copiar": (_("Copiar el contenido"), _(
            "Copia al portapapeles lo que estás viendo, como texto.")),
        "DialogoReproductor.lista": (_("Secciones del libro DAISY"), _(
            "Las secciones del libro hablado, al nivel que se haya elegido al lado. Intro "
            "empieza a reproducir por ahí.")),
        "DialogoReproductor.eleccion_nivel": (_("Nivel de navegación"), _(
            "Con qué detalle se enseña la estructura: solo las partes, los capítulos o "
            "hasta los apartados.\n\n"
            "Es la navegación propia del DAISY, y la razón de ser del formato: en un libro "
            "hablado de veinte horas, poder ir al apartado 4.3 en dos pulsaciones.")),
        "DialogoReproductor.boton_reproducir": (_("Reproducir o pausar"), _(
            "Empieza a leer desde donde estés, o para si ya está sonando.")),
        "DialogoReproductor.volumen": (_("Volumen del libro hablado"), _(
            "El volumen con el que suena la grabación, sin tocar el del resto del sistema.")),

        # ---- Perfiles, datos y asistente ---------------------------------------
        "DialogoPerfiles.lista": (_("Perfiles guardados"), _(
            "Cada perfil es un juego completo de preferencias con un nombre. Sirven para "
            "cambiar de golpe entre «estudiar» —con las llamadas de nota puestas y la voz "
            "lenta— y «escuchar una novela», sin ir tocando ajustes de uno en uno.")),
        "DialogoPerfiles.boton_ejemplos": (_("Traer los perfiles de ejemplo"), _(
            "Añade unos perfiles ya hechos —estudiar, escuchar, revisar— para partir de "
            "algo en vez de empezar en blanco. Se pueden cambiar después.")),
        "DialogoDatos.lista": (_("Lo que ocupa cada cosa"), _(
            "Cuánto ocupa en el disco cada clase de dato que guarda el programa: las "
            "descripciones de imágenes, el texto reconocido de los escaneos, los registros, "
            "la caché.\n\n"
            "Sirve para saber qué borrar cuando hace falta sitio, y para ver de un vistazo "
            "que el programa no guarda nada raro.")),
        "DialogoDatos.boton_borrar": (_("Borrar lo elegido"), _(
            "Borra la clase de datos que tengas marcada. Se avisa antes de lo que se va a "
            "perder; los marcadores y las notas nunca se tocan desde aquí.")),
        "DialogoDatos.boton_sobrantes": (_("Quitar lo que ya no sirve"), _(
            "Borra los datos de libros que ya no están en el disco. Es lo que se acumula "
            "solo, sin que nadie lo pida.")),
        "DialogoDatos.boton_actualizar": (_("Volver a medir"), _(
            "Vuelve a contar lo que ocupa cada cosa. Hace falta después de borrar algo, "
            "porque la medida se toma al abrir la ventana y no se rehace sola.")),
        "DialogoAsistenteIA.lista": (_("Pasos del asistente"), _(
            "Lo que hace falta para dejar la inteligencia artificial funcionando en este "
            "equipo, paso a paso, con el estado de cada uno.\n\n"
            "El asistente descarga e instala lo necesario por su cuenta: es el camino para "
            "tener IA **sin cuenta, sin tarjeta y sin conexión** una vez instalada.")),
        "DialogoAsistenteIA.texto": (_("Qué pasa en este paso"), _(
            "Lo que se está haciendo y qué se va a descargar, con su tamaño. Los modelos "
            "ocupan gigabytes, y conviene saberlo antes de empezar.")),
        "DialogoAsistenteIA.boton_accion": (_("Hacer este paso"), _(
            "Ejecuta el paso que toca: descargar, instalar o comprobar. Se puede parar y "
            "seguir después por donde iba.")),
        "DialogoIdiomasOCR.lista_puestos": (_("Idiomas instalados"), _(
            "Los idiomas que el reconocimiento de texto ya sabe leer en este equipo.")),
        "DialogoIdiomasOCR.lista_nuevos": (_("Idiomas que se pueden añadir"), _(
            "Los que se pueden descargar. Cada uno ocupa unos pocos megabytes.\n\n"
            "Hace falta el idioma correcto: un texto en alemán reconocido con el modelo "
            "español sale lleno de erratas justo en las palabras que importan.")),
        "DialogoIdiomasOCR.boton_anadir": (_("Añadir el idioma"), _(
            "Descarga e instala el idioma elegido para el reconocimiento de texto.")),
        "DialogoIdiomasOCR.boton_quitar": (_("Quitar el idioma"), _(
            "Borra del disco el idioma elegido. Se puede volver a descargar cuando haga "
            "falta.")),
        "DialogoAcercaDe.boton_cafe": (_("Invitar a un café"), _(
            "Abre en el navegador la página para hacer una donación, si te apetece. El "
            "programa es gratuito y lo seguirá siendo.")),

        # ---- Moverse por el documento --------------------------------------
        "PanelArbol.arbol": (_("Contenido del documento"), _(
            "El índice del documento, lo que tú has dejado puesto y todo lo que el "
            "documento contiene, en un árbol.\n\n"
            "Arriba va el índice que hizo quien escribió el documento. Debajo, TUS "
            "MARCADORES, TUS NOTAS Y TUS RESALTADOS, cada clase en su rama, porque al "
            "volver a un libro ya trabajado es lo primero que se busca. Y después una "
            "rama por cada clase de elemento que haya: encabezados, imágenes, tablas, "
            "enlaces, listas, páginas... Cada rama dice entre paréntesis cuántos hay, y "
            "las de los elementos se llenan al desplegarlas.\n\n"
            "Las tuyas se rehacen solas: pon un marcador y aparece ahí sin tener que "
            "recargar nada.\n\n"
            "Con las flechas te mueves sin que se mueva la lectura, que es lo que deja "
            "recorrerlo para ver qué hay sin perder el sitio. Con Intro saltas al elemento. "
            "Con F6 vuelves al texto.\n\n"
            "LA TECLA DE APLICACIONES, O MAYÚSCULAS+F10, ABRE UN MENÚ sobre lo que tengas "
            "seleccionado, y ofrece cosas distintas según lo que sea:\n\n"
            "En una IMAGEN: verla, describirla con inteligencia artificial.\n"
            "En una TABLA: abrirla para recorrerla fila a fila.\n"
            "En un ENLACE: seguirlo.\n"
            "En UN MARCADOR, UNA NOTA O UN RESALTADO: escribir o cambiar la nota, "
            "copiarla, copiar el texto señalado, o quitarlo. Si la nota tiene algo "
            "escrito se pregunta antes de quitarla.\n"
            "En CUALQUIERA: ir, leer en voz alta desde ahí, copiar su texto, poner un "
            "marcador.\n\n"
            "Y si estás en la CABECERA DE UNA RAMA —«Imágenes (80)»— el menú actúa sobre "
            "todos: describir de una vez las que falten, copiar la lista entera o guardarla "
            "en un archivo. En las tuyas, además, abrir su lista completa —que es donde "
            "se buscan y se exportan— o quitarlos todos, preguntando antes. Ahí es donde "
            "el árbol deja de ser una lista y sirve para trabajar.\n\n"
            "Al llegar con F6, el árbol se coloca solo por donde ibas leyendo.")),
        "DialogoIndice.arbol": (_("Índice del documento"), _(
            "El índice del libro como un árbol: los capítulos, y dentro de cada uno sus "
            "apartados.\n\n"
            "Con las flechas derecha e izquierda se abre y se cierra cada rama, así que se "
            "puede recorrer el libro entero por encima sin oír los ciento veinte apartados "
            "de golpe. Intro va al sitio elegido.\n\n"
            "En un PDF sin índice, esto sale de los encabezados que el programa ha deducido "
            "midiendo la página, así que puede no ser perfecto; se corrige con "
            "Control+Mayús+E sobre el título que esté mal.")),
        "DialogoElementos.lista": (_("Elementos del documento"), _(
            "Todo lo que hay del tipo elegido arriba —los encabezados, las imágenes, las "
            "tablas, los enlaces, las notas al pie—, en el orden en que aparecen y con el "
            "punto del libro en el que están.\n\n"
            "Es la manera de responder «¿cuántas tablas tiene esto y dónde?», que con la "
            "vista se contesta pasando páginas y de oído no se puede contestar de otra "
            "forma. Intro lleva al elemento.")),
        "DialogoElementos.tipos": (_("Qué elementos enseñar"), _(
            "Elige de qué son los elementos de la lista.\n\n"
            "Los tres primeros son TUYOS: los marcadores, las notas y los resaltados que "
            "hayas puesto en este documento, con el porcentaje delante para situarlos. "
            "Van primero porque al volver a un libro ya trabajado es lo primero que se "
            "busca.\n\n"
            "Después va lo que trae el documento: encabezados, imágenes, tablas, "
            "enlaces, notas al pie, citas, listas o fórmulas.\n\n"
            "Entre paréntesis va cuántos hay de cada clase, así que este desplegable ya "
            "es por sí solo el resumen de lo que hay y de lo que has dejado puesto.")),
        "DialogoSalto.campo": (_("A dónde ir"), _(
            "Escribe el número y pulsa Intro.\n\n"
            "Según desde dónde se haya abierto, es un número de línea, un porcentaje o un "
            "número de página. El rótulo de arriba dice cuál es y entre qué valores.\n\n"
            "Ir por porcentaje es lo que sirve en un EPUB, que no tiene páginas de verdad; "
            "ir por página, en un PDF y en un libro que traiga sus números.")),
        "DialogoPestanas.lista": (_("Documentos abiertos"), _(
            "Los documentos que tienes abiertos ahora mismo, con por dónde vas en cada "
            "uno. Intro cambia al elegido.\n\n"
            "Es lo mismo que Control+Tabulador, pero enseñándolos todos a la vez: con "
            "cuatro o cinco abiertos, ir girando de uno en uno hasta encontrar el que "
            "quieres es más lento que verlos.")),
        "DialogoDondeAbrir.recordarlo": (_("No volver a preguntar"), _(
            "Guarda la respuesta que des ahora y deja de preguntar cada vez que abras un "
            "documento.\n\n"
            "Se puede cambiar después en Opciones, en la pestaña de pestañas. Preguntar "
            "cada vez está bien la primera semana y estorba a partir de la segunda.")),

        # ---- Marcadores, notas y resaltados ---------------------------------
        "DialogoMarcadores.lista": (_("Marcadores y notas"), _(
            "Todo lo que has marcado en este documento: los marcadores sueltos, las notas "
            "que escribiste y los pasajes resaltados, con el trozo de texto al que está "
            "pegado cada uno.\n\n"
            "Intro lleva al sitio. El texto que se ve aquí es el que se guarda con el "
            "marcador, y es lo que permite que el cuaderno de estudio se monte sin abrir "
            "ningún libro.")),
        "DialogoMarcadores.filtro": (_("Filtrar por tema"), _(
            "Se queda solo con lo marcado que lleve esa etiqueta.\n\n"
            "Las etiquetas se le ponen a una nota al escribirla, separadas por comas. Son "
            "lo que permite juntar después «todo lo del tema cuatro» aunque esté repartido "
            "por seis libros.")),
        "DialogoMarcadores.busqueda": (_("Buscar entre lo marcado"), _(
            "Se queda con los marcadores cuyo texto o cuya nota contengan lo que escribas. "
            "En un libro con doscientos resaltados es la única forma de encontrar «el del "
            "gráfico de las ventas» sin recorrerlos todos.")),
        "DialogoMarcadores.boton_borrar": (_("Borrar el marcador"), _(
            "Quita el marcador, la nota o el resaltado elegido. Solo se quita la marca: el "
            "documento no se toca.")),
        "DialogoResaltados.lista": (_("Pasajes resaltados"), _(
            "Los trozos que has resaltado en este documento, en el orden en que aparecen, "
            "con la nota que le hayas puesto a cada uno.\n\n"
            "Intro lleva al pasaje dentro del libro.")),
        "DialogoResaltados.filtro": (_("Filtrar los resaltados por tema"), _(
            "Se queda solo con los resaltados que lleven esa etiqueta, que es el paso "
            "previo a exportar «todo lo del tema cuatro» de este libro.")),
        "DialogoResaltados.casilla_notas": (_("Incluir las notas al exportar"), _(
            "Saca también, junto a cada pasaje, la nota que le escribiste.\n\n"
            "Recomendado: activado si lo que vas a hacer es estudiar; apagado si lo que "
            "quieres es una lista de citas limpia para un trabajo.")),
        "DialogoResaltados.boton_exportar": (_("Guardar los resaltados"), _(
            "Escribe en un archivo los pasajes que estás viendo, con el filtro puesto.\n\n"
            "Esto es de **este** libro. Para juntar lo de varios a la vez está el cuaderno "
            "de estudio, en la biblioteca.")),
        "DialogoResaltados.boton_borrar": (_("Quitar el resaltado"), _(
            "Quita el resaltado elegido. El texto del documento no se toca.")),
        "DialogoNota.campo": (_("El texto de la nota"), _(
            "Lo que quieras escribir sobre este punto del documento.\n\n"
            "La nota se guarda pegada al trozo de texto que hay debajo del cursor, así que "
            "aunque el libro se vuelva a abrir dentro de un año la nota sigue sabiendo a "
            "qué se refería. Y viaja con la sincronización al otro equipo.")),
        "DialogoNota.campo_etiquetas": (_("Etiquetas de la nota"), _(
            "Temas de esta nota, separados por comas: «tema 4, examen, dudas».\n\n"
            "Es lo que después permite quedarse con «todo lo del tema cuatro» —en este "
            "libro y en los otros cinco de la asignatura— y sacarlo a un cuaderno. Sin "
            "etiquetas, las notas solo se pueden leer libro por libro y en orden.\n\n"
            "Da igual cómo las escribas: «Tema 4» y «tema 4» son la misma.")),

        # ---- Buscar ---------------------------------------------------------
        "DialogoBuscar.campo": (_("Qué buscar"), _(
            "La palabra o la frase que se busca en este documento.\n\n"
            "Los acentos y las mayúsculas dan igual salvo que digas lo contrario en las "
            "casillas de al lado. Después, F3 va a la siguiente aparición y Mayús+F3 a la "
            "anterior, sin volver a abrir esta ventana.")),
        "DialogoBuscar.regular": (_("Expresión regular"), _(
            "Trata lo escrito como una expresión regular en vez de como texto normal.\n\n"
            "Sirve para buscar cosas que no son una palabra: «\\d{4}» encuentra cualquier "
            "año de cuatro cifras y «^Capítulo» solo lo que empiece una línea.\n\n"
            "Recomendado: apagado, salvo que sepas qué es esto. Con ello encendido, "
            "caracteres como el punto o el paréntesis dejan de significar lo que parecen.")),
        "DialogoBuscar.boton_contar": (_("Contar apariciones"), _(
            "Dice cuántas veces sale en el documento entero, sin moverte de donde estás.\n\n"
            "Con la vista, la barra de desplazamiento ya da esa idea. De oído no hay manera "
            "de saber si una palabra sale dos veces o doscientas, y eso cambia lo que uno "
            "hace después.")),
        "DialogoBuscar.boton_siguiente": (_("Buscar hacia adelante"), _(
            "Va a la siguiente aparición a partir de donde está el cursor. Fuera de esta "
            "ventana, la tecla F3 hace lo mismo.")),
        "DialogoBuscar.boton_anterior": (_("Buscar hacia atrás"), _(
            "Va a la aparición anterior. Fuera de esta ventana, Mayús+F3.")),

        # ---- Citar ----------------------------------------------------------
        "DialogoCitar.campo_pasaje": (_("El pasaje que se va a citar"), _(
            "El trozo de texto tal y como se va a copiar. Se puede recortar aquí mismo "
            "antes de copiarlo: lo que quede es lo que se pega.")),
        "DialogoCitar.campo_referencia": (_("La referencia"), _(
            "De dónde sale la cita, ya escrita en el estilo elegido: autor, título, año y "
            "por dónde va.\n\n"
            "Es lo que evita el trabajo de siempre —copiar la frase, buscar la portada, "
            "apuntar la página— y lo que evita el error de siempre, que es citar mal por "
            "haberlo hecho de memoria.")),
        "DialogoCitar.estilo": (_("Estilo de la cita"), _(
            "Cómo se escribe la referencia: APA, MLA, Chicago o ISO 690.\n\n"
            "Recomendado: el que te pidan en la asignatura o en la revista. Si no te piden "
            "ninguno, APA es el más extendido.")),
        "DialogoCitar.boton_copiar": (_("Copiar la cita entera"), _(
            "Copia el pasaje y su referencia juntos, listos para pegar en el trabajo.")),
        "DialogoCitar.boton_solo": (_("Copiar solo la referencia"), _(
            "Copia únicamente la referencia, sin el pasaje. Es lo que hace falta cuando la "
            "frase ya la has escrito tú con tus palabras y solo hay que decir de dónde "
            "sale.")),

        # ---- Tablas e imágenes ----------------------------------------------
        "DialogoTabla.rejilla": (_("Contenido de la tabla"), _(
            "La tabla como una tabla de verdad, no como texto seguido.\n\n"
            "Se recorre por filas con las flechas arriba y abajo y **por celdas** con las "
            "flechas izquierda y derecha, oyendo el encabezado de cada columna. Es la única "
            "manera de consultar una casilla concreta sin oír la fila entera, y es justo lo "
            "que se pierde cuando una tabla se lee de corrido.")),
        "DialogoTabla.boton_html": (_("Ver la tabla como página web"), _(
            "Abre la misma tabla en el visor HTML, donde tu lector de pantalla usa **sus "
            "propias órdenes de tabla**: ir a la celda de al lado, leer el encabezado de "
            "esta columna, saltar a la primera fila.\n\n"
            "Merece la pena en las tablas grandes; en una de tres filas, la rejilla de aquí "
            "basta.")),
        "DialogoImagen.lienzo": (_("La imagen"), _(
            "La imagen tal y como está en el documento, por si hay resto visual o por si la "
            "va a mirar alguien más.\n\n"
            "Lo que se puede leer de ella está en la descripción de abajo, y si es un "
            "gráfico o un diagrama se le pueden sacar además los datos o el recorrido.")),
        "DialogoImagen.campo_descripcion": (_("Descripción de la imagen"), _(
            "Lo que dice la imagen, escrito. Puede venir del propio documento, haberla "
            "pedido a la inteligencia artificial o haberla escrito tú.\n\n"
            "Se puede corregir a mano y guardar: lo que escribas tú manda sobre lo demás, y "
            "vuelve con el documento la próxima vez.")),
        "DialogoImagen.boton_describir": (_("Describir con inteligencia artificial"), _(
            "Le pide a la IA que diga qué se ve en esta imagen.\n\n"
            "La descripción se guarda junto al documento, así que se pide una vez y ya "
            "está. Si la imagen es un gráfico o un diagrama, además conviene pulsar «Sacar "
            "los datos»: la descripción dice de qué va y los datos dicen cuánto.")),
        "DialogoImagen.boton_guardar": (_("Guardar la descripción"), _(
            "Guarda lo que haya en el cuadro de la descripción junto a esta imagen, para "
            "que vuelva la próxima vez que abras el documento.")),

        # ---- La imagen con IA -----------------------------------------------
        "DialogoDescripcion.campo": (_("Descripción de la imagen"), _(
            "Lo que dice la imagen. Se puede corregir a mano antes de guardarla: la IA "
            "acierta casi siempre en lo que hay y se equivoca a veces en lo que significa, "
            "y quien tiene el libro delante sabe cuál de las dos cosas hace falta.")),
        "DialogoDescripcion.eleccion": (_("Con qué instrucción describir"), _(
            "Qué se le pide exactamente a la inteligencia artificial.\n\n"
            "No es lo mismo describir la foto de una novela que un esquema de un manual: "
            "la primera pide contar la escena y el segundo, enumerar las piezas. Las "
            "instrucciones se editan y se añaden en Opciones, en la pestaña de la IA.")),
        "DialogoDescripcion.boton_describir": (_("Describir con IA"), _(
            "Manda la imagen y trae su descripción. Tarda unos segundos y se puede seguir "
            "usando el programa mientras tanto.")),
        "DialogoDescripcion.boton_datos": (_("Sacar los datos o la estructura"), _(
            "Este botón sirve para dos cosas, y no hay que elegir cuál: saber si dentro de "
            "una imagen hay una tabla o un diagrama es justo lo que no se puede ver.\n\n"
            "Si la imagen es un **gráfico**, saca sus valores en una tabla que se recorre "
            "celda a celda. Una descripción dice «un gráfico de barras de ventas por "
            "trimestre»; la tabla dice los doce números.\n\n"
            "Si no lo es, el programa vuelve a preguntar por **las cajas y las flechas**, y "
            "de un diagrama de flujo, un organigrama o un circuito sale su recorrido como "
            "una lista anidada que se puede seguir paso a paso.\n\n"
            "En los dos casos se dice de qué se fía: si ha tenido que estimar un valor o "
            "suponer por dónde va una flecha, lo advierte.")),
        "DialogoDescripcion.boton_tabla": (_("Ver la tabla o el esquema"), _(
            "Abre lo que se haya sacado de la imagen en el visor, donde el lector de "
            "pantalla lo trata como lo que es: una tabla de verdad, con sus órdenes de "
            "tabla, o una lista anidada que dice en qué nivel estás.\n\n"
            "El botón se llama según lo que haya, para no tener que pulsarlo para "
            "averiguarlo.")),
        "DialogoDescripcion.boton_copiar": (_("Copiar la descripción"), _(
            "Copia al portapapeles el texto de la descripción.")),
        "DialogoDescripcion.boton_olvidar": (_("Olvidar la descripción guardada"), _(
            "Borra lo que se había guardado de esta imagen —la descripción y, si los había, "
            "sus datos— para poder empezar de cero.\n\n"
            "Se usa cuando la descripción salió mal o cuando quieres probar con otra "
            "instrucción o con otro modelo.")),

        # ---- El cuaderno de estudio ----------------------------------------
        "DialogoCuaderno.tema": (_("Tema del cuaderno"), _(
            "Se queda solo con lo que hayas etiquetado con ese tema, en todos los libros a "
            "la vez. Entre paréntesis va cuántos apuntes lleva cada uno.\n\n"
            "Es lo que convierte una biblioteca en un cuaderno: «todo lo del tema cuatro», "
            "salga del libro que salga.\n\n"
            "Con «Todos los temas» sale el cuaderno entero, agrupado igualmente por tema y "
            "con lo que no lleva etiqueta en un grupo al final.")),
        "DialogoCuaderno.casilla_notas": (_("Incluir las notas"), _(
            "Mete en el cuaderno las notas que hayas escrito tú (Control+Mayús+M).\n\n"
            "Recomendado: activado. Lo que escribiste tú suele ser lo que hay que repasar; "
            "el pasaje resaltado es la prueba y la nota es la conclusión.")),
        "DialogoCuaderno.casilla_resaltados": (_("Incluir los resaltados"), _(
            "Mete en el cuaderno los pasajes que hayas resaltado (Control+R).\n\n"
            "Si lo apagas y dejas solo las notas, sale un cuaderno de conclusiones sin las "
            "citas. Sirve para repasar deprisa; para citar en un trabajo hacen falta las "
            "dos cosas.")),
        "DialogoCuaderno.lista": (_("Los apuntes del cuaderno"), _(
            "Cada línea es una cosa que marcaste: su tema, de qué libro y de qué punto sale, "
            "y el texto.\n\n"
            "Está agrupada por tema y ordenada del tema más usado al menos usado. Un apunte "
            "con dos etiquetas sale dos veces, a propósito: quien repasa el tema cuatro "
            "quiere verlo, y quien repasa «dudas», también.\n\n"
            "Con las flechas izquierda y derecha se recorren las columnas de una línea sin "
            "oírla entera.")),
        "DialogoCuaderno.boton_guardar": (_("Guardar el cuaderno en un archivo"), _(
            "Escribe todo lo que estás viendo en un archivo, en el formato del desplegable "
            "de al lado.\n\n"
            "En página web los temas son encabezados de verdad, así que se salta de tema en "
            "tema con la tecla H del lector de pantalla. En Markdown cada pasaje va como "
            "cita, listo para pegarlo en unos apuntes. En texto plano, lo mismo sin "
            "formato.")),
        "DialogoCuaderno.formato": (_("Formato del cuaderno"), _(
            "En qué se guarda el cuaderno.\n\n"
            "Página web (.html): encabezados de verdad, uno por tema, para saltar con la "
            "tecla H. Es el más cómodo de repasar.\n\n"
            "Markdown (.md): texto con marcas, cada pasaje como cita. Para pegarlo en unos "
            "apuntes o en un editor.\n\n"
            "Texto plano (.txt): lo mismo sin nada alrededor.")),
        "DialogoCuaderno.boton_repasar": (_("Repasar lo que estás viendo"), _(
            "Convierte en tarjetas de repaso lo que hay ahora mismo en la lista, con el "
            "tema que hayas puesto: si acabas de quedarte con el tema cuatro, repasas el "
            "tema cuatro.\n\n"
            "Cada tarjeta se enseña en dos tiempos —primero de dónde sale, y el pasaje solo "
            "cuando pulsas Espacio— y se responde con 1, 2 o 3. Lo que sabes tarda cada vez "
            "más en volver; lo que no, vuelve mañana.\n\n"
            "No hay que preparar nada: cada resaltado y cada nota ya son una tarjeta.")),

        # ---- El repaso -----------------------------------------------------
        "DialogoRepaso.tarjeta": (_("La tarjeta de repaso"), _(
            "Aquí está la tarjeta, y se enseña en dos tiempos.\n\n"
            "Primero ves de qué libro y de qué punto sale y, si la escribiste, tu nota: eso "
            "es la pregunta. Cuando hayas intentado recordarlo, pulsa Espacio y aparece el "
            "pasaje.\n\n"
            "Los dos tiempos no son un adorno: recordar y reconocer no son lo mismo, y una "
            "tarjeta que enseña la respuesta a la vez que la pregunta no enseña nada. Por "
            "eso la respuesta está detrás de una tecla y no debajo, donde el cursor la "
            "leería sola al bajar.\n\n"
            "Es un cuadro de solo lectura, así que el texto se recorre con las flechas para "
            "releer lo que interese.")),
        "DialogoRepaso.boton_descubrir": (_("Descubrir el pasaje"), _(
            "Enseña la respuesta de la tarjeta. También con la barra espaciadora, sin tener "
            "que salir del cuadro del texto.\n\n"
            "Hasta que no se descubre, los tres botones de respuesta están apagados: "
            "responder antes de mirar no mide nada.")),

        # ---- Practicar -----------------------------------------------------
        "DialogoPractica.enunciado": (_("El ejercicio que toca"), _(
            "Lo que hay que hacer, con qué tecla se hace y un recordatorio de que se hace "
            "**en el documento**, no aquí.\n\n"
            "Esta ventana no es modal a propósito: vuelve al texto con F6, hazlo, y el "
            "programa te avisa en cuanto salga. No hace falta volver aquí.\n\n"
            "Da igual cómo lo hagas: lo que se mira es el documento y no las teclas, así "
            "que llegar al tercer encabezado con el árbol de contenido cuenta igual que "
            "llegar con la H.")),
        "DialogoPractica.boton_repetir": (_("Repetir el enunciado"), _(
            "Vuelve a decir en voz alta lo que hay que hacer y con qué tecla.\n\n"
            "Está aquí porque al irse al documento a practicar es normal que el lector de "
            "pantalla haya tapado el enunciado con lo que se iba leyendo.")),
        "DialogoPractica.boton_saltar": (_("Saltar este ejercicio"), _(
            "Pasa al siguiente sin hacer este.\n\n"
            "Sirve para los que ya te sabes y para los que no te apetecen ahora. Al "
            "terminar se dice cuántos hiciste y cuántos saltaste, sin más.")),

        # ---- La biblioteca -------------------------------------------------
        "DialogoBiblioteca.agrupar": (_("Agrupar por"), _(
            "Elige cómo se reparten los libros en la lista de grupos de al lado: por "
            "colección, por autor, por serie, por etiqueta, por editorial, por idioma, por "
            "formato, por año de publicación, por la biblioteca o carpeta de la que salen o "
            "por cómo vas con ellos (terminados, a medias, sin empezar).\n\n"
            "Es como el explorador de etiquetas de calibre: eliges «Autor», bajas hasta el "
            "que buscas en la lista de grupos y en la lista de libros quedan solo los suyos.\n\n"
            "Un libro de dos autores sale con los dos, y uno con tres etiquetas, en las "
            "tres. La elección se recuerda para la próxima vez.")),
        "DialogoBiblioteca.grupo": (_("Grupos"), _(
            "Los grupos de la agrupación elegida, cada uno con cuántos libros tiene. El "
            "primero, «Todos», es la biblioteca entera; el último, «Sin este dato», reúne los "
            "que no lo tienen (los que no tienen serie, o colección...).\n\n"
            "Al moverte por ella, la lista de libros cambia sola al poco de pararte. Escribe "
            "las primeras letras para saltar a un grupo, e Intro para ir a sus libros.\n\n"
            "Es una lista que aguanta lo que haga falta: sesenta mil autores se recorren "
            "igual que diez.\n\nControl+I dice en qué elemento estás y de cuántos («1425 de 2484»), y Control+G pregunta a qué número ir y te deja en él. Las dos teclas se cambian en Opciones, «Accesibilidad».")),
        "DialogoBiblioteca.orden": (_("Ordenar por"), _(
            "En qué orden salen los libros: por título, por autor (y dentro de cada uno por "
            "serie y número), por serie y número, por fecha de publicación, por los últimos "
            "que se han añadido, por los últimos que has leído o por formato.\n\n"
            "Se recuerda para la próxima vez.")),
        "DialogoBiblioteca.lista": (_("Los libros de la biblioteca"), _(
            "Todos los libros: los que has abierto alguna vez y los de las carpetas y "
            "bibliotecas de calibre que hayas añadido, con las columnas que elijas en "
            "Opciones, «Biblioteca y sincronización».\n\n"
            "Intro abre el libro por donde lo dejaste. Alt+Intro enseña su ficha con todos "
            "sus datos. Suprimir lo quita de la biblioteca, sin borrar el archivo.\n\n"
            "Se pueden marcar varios —con Control y Mayús, como en cualquier lista, o todos "
            "con Control+E— y entonces los botones de abajo actúan sobre todos los marcados: "
            "ponerles colección, quitarlos, sacar la bibliografía o montar el cuaderno.\n\n"
            "Con las flechas izquierda y derecha se recorren las columnas de un libro sin "
            "oír la línea entera. Escribir las primeras letras de un título lleva a él.\n\n"
            "La lista no tiene tope: ciento noventa mil libros caben igual que diez.\n\nControl+I dice en qué elemento estás y de cuántos («1425 de 2484»), y Control+G pregunta a qué número ir y te deja en él. Las dos teclas se cambian en Opciones, «Accesibilidad».")),
        "DialogoBiblioteca.filtro": (_("Filtro de la lista de libros"), _(
            "Escribe aquí y la lista se queda con los libros en los que salgan todas las "
            "palabras escritas, en el título, los autores, la serie, las etiquetas, la "
            "editorial, la colección o el nombre del archivo. No hace falta acertar con los "
            "acentos ni con las mayúsculas, ni con el orden: «galdos episodios» encuentra "
            "los Episodios nacionales de Galdós.\n\n"
            "Se filtra al poco de dejar de escribir y se dice cuántos quedan. Filtra dentro "
            "del grupo elegido a la izquierda.")),
        "DialogoBiblioteca.boton_coleccion": (_("Poner colección a los marcados"), _(
            "Le pone la misma colección a todos los libros que tengas marcados, de una "
            "vez.\n\n"
            "Una colección es lo que tú quieras que sea: una asignatura, un trabajo, una "
            "saga. Se puede escribir una nueva o elegir una de las que ya usas. Dejarlo en "
            "blanco les quita la colección.\n\n"
            "Después, con «Agrupar por: Colección», se ven los libros de cada una. La "
            "colección viaja al otro equipo con la sincronización.")),
        "DialogoBiblioteca.boton_ficha": (_("Ficha del libro"), _(
            "Enseña todo lo que se sabe del libro con el foco: título, autores, serie y "
            "número, etiquetas, editorial, fecha de publicación, idioma, valoración, ISBN y "
            "demás identificadores, las columnas propias que tengas en calibre, formatos, "
            "tamaño, de qué biblioteca sale, dónde está el archivo y la sinopsis.\n\n"
            "Va en un cuadro que se recorre con las flechas y se puede copiar entero. "
            "También se abre con Alt+Intro en la lista.\n\n"
            "Qué datos salen y en qué orden lo eliges tú, con «Elegir los datos» dentro de "
            "la ficha. De fábrica van primero el título, la serie, los autores y la "
            "sinopsis, y después lo más técnico.")),
        "DialogoBiblioteca.boton_similares": (_("Libros similares"), _(
            "Abre un menú con las maneras de buscar libros parecidos al que tiene el foco: "
            "de la misma serie, del mismo autor (uno por cada autor que tenga), de la "
            "misma colección, con la misma etiqueta o de la misma editorial.\n\n"
            "Al elegir una, la lista se queda con esos libros y el foco sigue en el libro "
            "del que partías. Por ejemplo, desde un libro de Harry Potter, «De la misma "
            "serie» trae todos los de la saga, ordenados por su número.\n\n"
            "Por dentro es lo mismo que elegir «Agrupar por» y el grupo a mano, solo que "
            "de una vez: lo que queda se puede ordenar, filtrar, exportar o buscar dentro "
            "igual que cualquier grupo. Para volver a verlo todo, elige «Todos» en la "
            "lista de grupos.\n\n"
            "El mismo menú sale con la tecla de aplicaciones o Mayús+F10 en la lista de "
            "libros.")),
        "DialogoBiblioteca.boton_exportar": (_("Exportar fichas"), _(
            "Guarda en un archivo las fichas de los libros marcados o, si no hay varios "
            "marcados, las de todos los que se ven en la lista.\n\n"
            "Primero eliges qué datos llevan y en qué orden —esta elección es aparte de la "
            "de la ficha que se ve, para poder tener una ficha corta para consultar y una "
            "exportación completa para un trabajo— y después dónde guardarlas.\n\n"
            "En texto, una ficha detrás de otra, como se ven. En CSV, una fila por libro y "
            "una columna por dato, para abrirla con Excel o LibreOffice; va separada por "
            "punto y coma, que es lo que espera Excel en español.\n\n"
            "Se hace en segundo plano y se puede detener.")),
        "DialogoBiblioteca.busqueda": (_("Buscar en todos los libros"), _(
            "Busca una palabra o una frase **dentro** de todos los libros de la lista, no "
            "en sus títulos.\n\n"
            "No hay ningún índice que preparar ni que esperar: se abren los libros uno a "
            "uno y se va enseñando lo que aparece. Se puede parar en cualquier momento y lo "
            "encontrado hasta ahí se queda.")),
        "DialogoBiblioteca.boton_buscar": (_("Buscar en los ya analizados"), _(
            "Busca lo escrito solo en los libros que ya se han abierto alguna vez, que "
            "están guardados ya analizados. Es casi instantáneo.\n\n"
            "Si no sale lo que buscas, «Buscar en todos» mira también en los demás.")),
        "DialogoBiblioteca.boton_buscar_todo": (_("Empezar a buscar en todos"), _(
            "Empieza a buscar lo escrito en todos los libros que estén en la lista, con el "
            "grupo y el filtro que tengas puestos.\n\n"
            "Buscar en seis libros de una asignatura tarda unos segundos; en trescientos, "
            "un rato; en una biblioteca entera de calibre, mucho: conviene acotar antes con "
            "el grupo o el filtro. Por eso se puede parar.")),
        "DialogoBiblioteca.boton_parar": (_("Detener"), _(
            "Para lo que esté en marcha: la carga de la biblioteca, una importación o una "
            "búsqueda.\n\n"
            "Lo hecho hasta ese momento se queda: lo encontrado sigue en los resultados, y "
            "lo importado sigue guardado y se completa al actualizar.")),
        "DialogoBiblioteca.resultados": (_("Resultados de la búsqueda"), _(
            "Cada línea es una aparición: de qué libro, por dónde y con la frase alrededor "
            "para saber si es la que buscabas.\n\n"
            "Al abrir uno, el libro se abre **por ahí**, no por el principio.\n\nControl+I dice en qué elemento estás y de cuántos («1425 de 2484»), y Control+G pregunta a qué número ir y te deja en él. Las dos teclas se cambian en Opciones, «Accesibilidad».")),
        "DialogoBiblioteca.boton_relacionadas": (_("Palabras relacionadas"), _(
            "Enseña qué otras palabras salen en los mismos pasajes que la que has escrito, "
            "**en tus propios libros**, y te deja añadir las que quieras a la búsqueda.\n\n"
            "Sirve para lo que la búsqueda por letras no encuentra: tus apuntes dicen "
            "«amortización» y el manual dice «depreciación». Lo que no aparece se da por "
            "que no está.\n\n"
            "Lo aprende de tu biblioteca y no de un diccionario: en una de derecho, "
            "«prescripción» sale junto a «caducidad»; en una de medicina, junto a «receta». "
            "No hace falta cuenta ni conexión y no se manda nada a ningún sitio.")),
        "DialogoBiblioteca.boton_bibliografia": (_("Sacar la bibliografía"), _(
            "Monta la lista de referencias de los libros marcados —o de todos los que estés "
            "viendo— en el estilo que elijas, y la copia o la guarda.\n\n"
            "Dos de los seis formatos no se leen: se **importan**. Con BibTeX y con RIS las "
            "referencias entran en Zotero, Mendeley o EndNote con sus campos separados, en "
            "vez de como un párrafo que hay que volver a trocear.")),
        "DialogoBiblioteca.boton_cuaderno": (_("Cuaderno de estudio"), _(
            "Junta las notas y los resaltados de **todos los libros que estés viendo**, los "
            "agrupa por tema y los saca a un archivo.\n\n"
            "Quien prepara una asignatura no estudia un libro: estudia un tema repartido "
            "por seis. Como la lista ya se puede agrupar por colección, sacar «todo lo "
            "etiquetado como examen en los seis libros de Contabilidad» son dos pasos.\n\n"
            "No hace falta abrir ningún libro: cada marcador guarda consigo su trozo de "
            "texto.")),
        "DialogoBiblioteca.boton_carpeta": (_("Añadir carpeta o biblioteca de calibre"), _(
            "Añade una carpeta entera a la biblioteca, sin tope de libros. Se recorre una "
            "vez y lo encontrado se guarda: abrir la biblioteca después no vuelve a "
            "recorrer el disco.\n\n"
            "Si la carpeta es una **biblioteca de calibre** (tiene su metadata.db) se "
            "reconoce sola y se importa con todo lo que sabe calibre: autores, series y "
            "número, etiquetas, editorial, fechas, idiomas, valoración, identificadores, "
            "sinopsis y tus columnas propias. Qué hacer en ese caso se elige en Opciones.\n\n"
            "De los EPUB de una carpeta corriente se leen sus propios metadatos.\n\n"
            "Se hace en segundo plano: puedes seguir usando la ventana, el avance se dice "
            "cada pocos segundos, se puede detener y al final sale un resumen.")),
        "DialogoBiblioteca.boton_gestor": (_("Bibliotecas y carpetas"), _(
            "Abre la lista de todas las carpetas y bibliotecas de calibre de las que salen "
            "tus libros, para gestionarlas de varias en varias: actualizarlas, cambiarles "
            "el nombre o la ruta, quitarlas con todos sus libros, hacer una copia de "
            "seguridad de la biblioteca entera o restaurarla.")),
        "DialogoBiblioteca.boton_quitar": (_("Quitar de la biblioteca"), _(
            "Saca de la biblioteca los libros marcados (o el que tenga el foco). También "
            "con la tecla Suprimir en la lista.\n\n"
            "No borra ningún archivo ni nada de lo que hayas hecho en ellos: solo dejan de "
            "aparecer. Tampoco vuelven al actualizar su biblioteca; para recuperarlos está "
            "«Devolver los libros quitados» en Bibliotecas y carpetas.")),

        # ---- La ficha de un libro ---------------------------------------------
        "DialogoFicha.texto": (_("Datos del libro"), _(
            "Lo que se sabe del libro, un dato por línea, con los datos que hayas elegido "
            "y en tu orden. La sinopsis va en su propio párrafo. Se recorre con las "
            "flechas y se puede seleccionar y copiar.")),
        "DialogoFicha.boton_datos": (_("Elegir los datos de la ficha"), _(
            "Elige qué datos salen en la ficha y en qué orden: marca los que quieras ver, "
            "desmarca los que no y súbelos o bájalos.\n\n"
            "Sirve para todas las fichas, no solo para esta: si solo te interesan el "
            "título, el autor y la sinopsis, deja esos y la ficha se lee de un vistazo. Al "
            "aceptar, la ficha se rehace al momento.")),
        "DialogoCamposFicha.lista": (_("Datos de la ficha"), _(
            "Todos los datos que puede llevar una ficha, en el orden en que salen. Los "
            "marcados salen y los desmarcados no; espacio marca o desmarca el que tiene el "
            "foco, Control+E los marca todos y Control+D los desmarca.\n\n"
            "Alt+flecha arriba y Alt+flecha abajo mueven el dato con el foco un puesto, "
            "igual que los botones «Subir» y «Bajar».\n\n"
            "Hay que dejar al menos uno marcado.")),
        "DialogoCamposFicha.boton_subir": (_("Subir el dato"), _(
            "Sube un puesto el dato elegido en la lista, para que salga antes en la "
            "ficha. También con Alt+flecha arriba en la lista.")),
        "DialogoCamposFicha.boton_bajar": (_("Bajar el dato"), _(
            "Baja un puesto el dato elegido en la lista, para que salga después en la "
            "ficha. También con Alt+flecha abajo en la lista.")),
        "DialogoCamposFicha.boton_fabrica": (_("Valores de fábrica de la ficha"), _(
            "Vuelve a marcar todos los datos y los pone en el orden de fábrica: título, "
            "serie, autores y sinopsis primero, y después lo técnico. No se guarda hasta "
            "que aceptes.")),
        "DialogoFicha.boton_abrir": (_("Abrir el libro"), _(
            "Cierra la ficha y abre el libro por donde lo dejaste.")),
        "DialogoFicha.boton_carpeta": (_("Abrir la carpeta del libro"), _(
            "Abre el Explorador de Windows en la carpeta donde está el archivo, con el "
            "archivo ya marcado.")),
        "DialogoFicha.boton_copiar": (_("Copiar la ficha"), _(
            "Copia la ficha entera al portapapeles, para pegarla donde haga falta.")),

        # ---- Bibliotecas y carpetas ---------------------------------------------
        "DialogoFuentes.lista": (_("Bibliotecas y carpetas"), _(
            "Cada línea es una fuente de libros: una carpeta corriente o una biblioteca de "
            "calibre, con cuántos libros trae, cuándo se actualizó, si ahora mismo está "
            "disponible (si el disco está conectado) y su ruta.\n\n"
            "Marca una o varias con Control o Mayús, o todas con Control+E, y usa los "
            "botones: todos actúan sobre las marcadas. Intro edita la que tiene el foco y "
            "Suprimir quita las marcadas.\n\nControl+I dice en qué elemento estás y de cuántos («1425 de 2484»), y Control+G pregunta a qué número ir y te deja en él. Las dos teclas se cambian en Opciones, «Accesibilidad».")),
        "DialogoFuentes.boton_anadir": (_("Añadir carpeta o biblioteca de calibre"), _(
            "Añade una carpeta a la biblioteca y la importa en segundo plano. Si es una "
            "biblioteca de calibre se reconoce sola y se traen todos sus datos.\n\n"
            "Si la carpeta ya está, o cae dentro de otra que ya está, se avisa en lugar de "
            "meter los libros dos veces.")),
        "DialogoFuentes.boton_actualizar": (_("Actualizar las marcadas"), _(
            "Vuelve a mirar las fuentes marcadas: se añaden los libros nuevos, se ponen al "
            "día los que han cambiado y se quitan los que ya no están. Al final se enseña un "
            "resumen con cuántos de cada.\n\n"
            "De una carpeta solo se vuelven a leer los archivos que han cambiado, así que "
            "actualizar es mucho más rápido que la primera vez. Si una fuente no está "
            "disponible (el disco no está conectado), no se toca.")),
        "DialogoFuentes.boton_actualizar_todas": (_("Actualizar todas"), _(
            "Actualiza todas las fuentes de la lista, una detrás de otra, y al final enseña "
            "el resumen de todas.")),
        "DialogoFuentes.boton_editar": (_("Editar una fuente"), _(
            "Cambia el nombre de la fuente con el foco, su ruta o su tipo.\n\n"
            "Cambiar la ruta es para cuando el disco cambia de letra o se ha movido la "
            "carpeta entera: todos sus libros se recolocan al momento, sin volver a "
            "importarlos, y lo que hayas hecho en ellos se conserva.")),
        "DialogoFuentes.boton_quitar": (_("Quitar las marcadas"), _(
            "Quita de la biblioteca las fuentes marcadas con **todos** sus libros, de una "
            "vez. Antes se pregunta, diciendo cuántos libros saldrán.\n\n"
            "No se borra nada del disco, ni las posiciones de lectura, los marcadores o las "
            "notas: si vuelves a añadirla, todo está donde estaba.")),
        "DialogoFuentes.boton_abrir_carpeta": (_("Abrir la carpeta"), _(
            "Abre en el Explorador de Windows la carpeta de la fuente con el foco.")),
        "DialogoFuentes.boton_readmitir": (_("Devolver los libros quitados"), _(
            "Los libros que has quitado a mano de la biblioteca no vuelven al actualizar. "
            "Esto los devuelve: se olvida que los quitaste y se actualizan sus fuentes para "
            "que aparezcan otra vez.")),
        "DialogoFuentes.boton_copia": (_("Copia de seguridad de la biblioteca"), _(
            "Guarda en un archivo ZIP la biblioteca entera —las fuentes y todos los libros "
            "con todos sus datos— y lo que has hecho en cada libro: por dónde vas, los "
            "marcadores, las notas y las colecciones.\n\n"
            "Con esa copia el programa se lleva a otro equipo o se reinstala sin perder "
            "nada, y sin tener que volver a importar.")),
        "DialogoFuentes.boton_restaurar": (_("Restaurar una copia"), _(
            "Pone una copia de seguridad hecha antes en lugar de la biblioteca actual. Se "
            "dice antes de qué fecha es y cuántos libros tiene, y se pregunta.\n\n"
            "Si los libros estaban en otra letra de disco, después basta con editar la ruta "
            "de cada fuente.")),
        "DialogoFuentes.boton_detener": (_("Detener"), _(
            "Para la importación o la actualización en marcha. Lo hecho hasta ahí se queda "
            "guardado; al actualizar otra vez se sigue.")),

        # ---- Editar una fuente ----------------------------------------------------
        "DialogoEditarFuente.nombre": (_("Nombre de la fuente"), _(
            "Cómo se llama esta carpeta o biblioteca dentro del programa. Es lo que sale "
            "al agrupar por «Biblioteca o carpeta» y en la ficha de cada libro. No cambia "
            "nada en el disco.")),
        "DialogoEditarFuente.ruta": (_("Ruta de la carpeta"), _(
            "Dónde está. Si el disco ha cambiado de letra o has movido la carpeta entera, "
            "pon aquí la ruta nueva: los libros se recolocan sin volver a importarlos.")),
        "DialogoEditarFuente.boton_elegir": (_("Elegir otra carpeta"), _(
            "Abre el selector de carpetas para elegir la ruta nueva en lugar de "
            "escribirla.")),
        "DialogoEditarFuente.tipo": (_("Tipo de fuente"), _(
            "Si es una biblioteca de calibre —se leen sus datos de su metadata.db— o una "
            "carpeta corriente —se recorren sus archivos—. Cambiarlo vuelve a importarla.")),

        # ---- El resumen ---------------------------------------------------------
        "DialogoResumen.texto": (_("Resumen de lo hecho"), _(
            "Lo que ha hecho la importación o la actualización, fuente por fuente: cuántos "
            "libros hay, cuántos son nuevos, cuántos se han puesto al día, cuántos seguían "
            "igual, cuántos se han quitado porque ya no estaban y cuánto ha tardado. Se "
            "recorre con las flechas.")),

        # ---- La bibliografía -----------------------------------------------
        "DialogoBibliografia.estilo": (_("Estilo o formato de la bibliografía"), _(
            "En qué se escribe la lista de referencias.\n\n"
            "Los cuatro primeros son para leer y para pegar en un trabajo. Los dos últimos "
            "no se leen, se **importan**: BibTeX y RIS entran en Zotero, Mendeley o EndNote "
            "con cada dato en su campo, en vez de como un párrafo que habría que volver a "
            "trocear a mano.\n\n"
            "Recomendado: el que te pidan. Si no te piden ninguno y vas a usar un gestor, "
            "BibTeX o RIS.")),
        "DialogoBibliografia.lista": (_("Las referencias"), _(
            "La bibliografía de los libros que estás viendo, ordenada por apellido del "
            "autor, en el estilo elegido. En la segunda columna, lo que le falta a cada "
            "una.\n\n"
            "Arriba se dice a cuántas les falta algún dato. Una bibliografía con tres años "
            "en blanco hay que arreglarla antes de entregarla, no después, y con la vista "
            "eso se ve de un vistazo: aquí se dice.\n\n"
            "Aguanta una biblioteca entera: solo se monta la cita de las filas que se ven, "
            "así que cambiar de estilo es instantáneo tenga las que tenga.\n\nControl+I dice en qué elemento estás y de cuántos («1425 de 2484»), y Control+G pregunta a qué número ir y te deja en él. Las dos teclas se cambian en Opciones, «Accesibilidad».")),
        "DialogoBibliografia.mostrar": (_("Qué referencias se enseñan"), _(
            "Todas, o solo las que tienen algún dato sin rellenar (el autor, el título, la "
            "editorial o el año).\n\n"
            "Las incompletas son las que hay que revisar antes de entregar el trabajo; "
            "con una biblioteca grande, verlas aparte ahorra recorrer miles que ya están "
            "bien. Copiar y guardar actúan sobre lo que se ve.")),
        "DialogoBibliografia.abrir_libros": (_("Abrir los libros a los que les falten datos"), _(
            "Los datos de cada referencia salen de la biblioteca —de calibre o de los "
            "metadatos del EPUB—, sin abrir ningún libro, y por eso una biblioteca entera "
            "sale en un par de segundos.\n\n"
            "Si marcas esto, a las que se queden incompletas se les abre el libro entero "
            "por si dentro trae lo que falta. Es mucho más lento: con miles de libros, "
            "horas. Se puede detener cuando quieras y lo completado hasta ahí se queda. "
            "Se recuerda para la próxima vez.\n\n"
            "Recomendado: apagado.")),
        "DialogoBibliografia.boton_detener": (_("Detener"), _(
            "Para lo que esté en marcha: preparar las referencias, abrir los libros, "
            "preparar el texto para copiar o guardar el archivo. Lo hecho hasta ahí se "
            "enseña igual.")),
        "DialogoBibliografia.boton_copiar": (_("Copiar la bibliografía"), _(
            "Copia al portapapeles la lista entera, tal y como se ve, para pegarla al final "
            "del trabajo.")),
        "DialogoBibliografia.boton_guardar": (_("Guardar la bibliografía"), _(
            "Escribe la lista en un archivo. Con BibTeX o RIS, ese archivo se importa "
            "directamente en el gestor de referencias.")),

        # ---- Lectura -------------------------------------------------------
        "tablas": (_("Mostrar las tablas completas dentro del texto"), _(
            "Vuelca cada tabla entera en el texto del documento, celda a celda, en vez de "
            "dejar solo una marca que diga «tabla».\n\n"
            "Con esto puedes leer la tabla seguida como si fuera texto. Sin esto, las tablas "
            "se recorren con la tecla T y se abren aparte con Control+Shift+T, que las "
            "muestra como una tabla de verdad y deja usar las órdenes de tabla de tu lector "
            "de pantalla.\n\n"
            "Recomendado: desactivado. Una tabla larga metida en el texto es difícil de "
            "seguir de oído, y la ventana aparte es mejor para eso.\n\n"
            "Cambiar esto obliga a volver a abrir el documento.")),
        "ajuste": (_("Ajustar las líneas al ancho de la ventana"), _(
            "Parte los párrafos largos en líneas que quepan en la ventana.\n\n"
            "Si lo desactivas, cada línea es un párrafo completo, por largo que sea. Eso "
            "cambia lo que hacen las flechas arriba y abajo: con el ajuste puesto se mueven "
            "por trozos de línea, y sin él, de párrafo en párrafo.\n\n"
            "Recomendado: a gusto. Mucha gente que lee de oído lo desactiva, porque así una "
            "pulsación de flecha equivale a una idea completa.")),
        "solo_articulo": (_("Quedarse solo con el artículo"), _(
            "En una página web guardada, quita los menús, el aviso de las galletas, la "
            "columna de «lo más leído» y el pie con cincuenta enlaces, y deja solo el "
            "texto del artículo.\n\n"
            "Con la vista, el ojo se salta todo eso sin darse cuenta. De oído hay que "
            "atravesarlo —a veces doscientas líneas— antes de llegar a la primera frase.\n\n"
            "Cuando el recorte no se puede decidir con seguridad, la página se lee entera: "
            "más vale que sobre a que falte, porque perder medio artículo sin enterarse es "
            "mucho peor que oír un menú.\n\n"
            "Recomendado: activado. Cambiar esto obliga a volver a abrir la página.")),
        "revisar_epub": (_("Comprobar el libro EPUB al exportarlo"), _(
            "Pasa el EPUB que acabas de exportar por las mismas comprobaciones de "
            "accesibilidad que se le hacen a cualquier otro libro: si el envoltorio está "
            "bien formado, si declara los metadatos que pide la norma europea, si su índice "
            "lleva de verdad a cada capítulo, si los encabezados se saltan niveles, si hay "
            "imágenes sin describir y si las tablas marcan su fila de encabezados.\n\n"
            "Tarda una décima de segundo. Si algo está mal de verdad se enseña en una "
            "ventana; si solo hay observaciones, se dicen.\n\n"
            "Recomendado: activado. Es la diferencia entre mandarle a alguien un libro que "
            "se lee y uno que no.")),
        "braille_contraido": (_("Escribir el braille en contraído"), _(
            "El braille que se exporta es, por omisión, integral: una celda por letra. "
            "El contraído usa abreviaturas —«bien» es una sola celda, «importante» son "
            "tres— y ocupa alrededor de un tercio menos, que en papel es un tercio menos "
            "de tomos.\n\n"
            "Se sigue el documento B 16-1 de la Comisión Braille Española, la revisión de "
            "2025: la lista de palabras abreviadas y sus variantes, los principios, los "
            "finales, las secuencias y las contracciones, aplicados en el orden que manda "
            "la norma.\n\n"
            "Lo que conviene saber antes de encenderlo: **quien no haya estudiado el "
            "braille contraído no entiende un texto contraído**. Y la transcripción se ha "
            "comprobado contra los ejemplos resueltos del propio documento, donde acierta "
            "en las palabras de la lista y en sus variantes y falla en alrededor de una de "
            "cada diez de las que hay que abreviar sobre la marcha. Para leer, sirve; para "
            "algo que vaya a imprimirse y repartirse, conviene repasarlo.\n\n"
            "Solo afecta al BRF y al PEF. Las fórmulas no se contraen nunca.\n\n"
            "Recomendado: apagado, salvo que leas contraído.")),
        "quimica": (_("Cómo se dicen las fórmulas químicas"), _(
            "Una fórmula como H2SO4 la voz la lee «hache dos ese o cuatro», que no se "
            "entiende y además confunde la letra O con el número cero.\n\n"
            "Con «el nombre de cada elemento» se dice «hidrógeno 2 azufre oxígeno 4», que es "
            "como lo dicta un profesor y no se puede confundir con nada. Con «deletrear los "
            "símbolos» se oye la fórmula tal como se escribe, con separaciones claras: lo "
            "prefiere quien ya se sabe la tabla y quiere copiarla.\n\n"
            "En automático solo se aplica a los documentos que traen química de verdad, así "
            "que en una novela no cambia nada aunque mencione el H2O.\n\n"
            "Esto no toca el libro: cambia solo lo que dice la voz.\n\n"
            "Recomendado: automático.")),
        "saltar_notas": (_("Qué no se dice al leer de corrido"), _(
            "Con la vista, el ojo se salta solo la cabecera que se repite en cada página, el "
            "número de página del pie y el numerito volado de una nota. De oído suena todo, "
            "y suena en medio de la frase.\n\n"
            "Las llamadas de nota se saben con exactitud, porque el programa las marca una a "
            "una. Los números de página son las líneas que no son más que un número. Las "
            "cabeceras se reconocen midiendo: se miran las dos primeras y las dos últimas "
            "líneas de cada página y se toma por cabecera lo que sale en al menos un tercio "
            "de ellas.\n\n"
            "Recomendado: apagadas si estudias, porque entonces sí quieres oír las llamadas "
            "de nota; encendidas para escuchar una novela de un tirón.\n\n"
            "Esto no cambia el libro: se ve entero, se busca entero y se exporta entero.")),
        "sincro_carpeta": (_("Carpeta compartida entre equipos"), _(
            "Elige una carpeta que ya sincronices por tu cuenta —Dropbox, OneDrive, Drive, "
            "un pendrive o una carpeta de red— y el programa dejará ahí una copia de por "
            "dónde vas en cada libro, de tus marcadores, de tus notas y de las descripciones "
            "de imágenes que hayas hecho con inteligencia artificial.\n\n"
            "Al abrir el programa en el otro equipo se junta con lo que haya, libro por "
            "libro: de cada uno se queda la versión más reciente, y los marcadores de los dos "
            "sitios se suman, así que no se pierde nada.\n\n"
            "No hace falta ninguna cuenta ni ningún servicio, y no se manda nada a ningún "
            "servidor: el programa solo escribe en esa carpeta.\n\n"
            "Las preferencias no se sincronizan a propósito: la voz que tienes en casa puede "
            "no estar instalada en el trabajo.\n\n"
            "Déjala vacía para no sincronizar nada.")),
        "lista_tecla_posicion": (_("Tecla para saber en qué elemento estás"), _(
            "En cualquier lista de varias columnas —la biblioteca, sus grupos, los "
            "resultados de buscar, la bibliografía, las bibliotecas y carpetas— esta tecla "
            "dice en qué elemento estás y de cuántos: «Libros de la biblioteca: 1425 de "
            "2484». Si hay varios marcados, también cuántos.\n\n"
            "Hace falta en las listas largas: el lector de pantalla dice dónde estás al "
            "moverte, pero no siempre de cuántos.\n\n"
            "Recomendado: Control+I. Elige «Ninguna» para no usarla.")),
        "lista_tecla_ir_a": (_("Tecla para ir a un elemento por su número"), _(
            "En las mismas listas, esta tecla pregunta a qué número de elemento quieres ir "
            "y te deja en él. Solo admite cifras, y un número entre 1 y el total: si "
            "escribes otra cosa, te lo dice y no se mueve.\n\n"
            "Sirve para volver a un sitio concreto de una lista de miles sin bajar con la "
            "flecha.\n\n"
            "Recomendado: Control+G, la misma de «Ir a» en el Bloc de notas. No puede ser "
            "la misma que la de la opción anterior.")),
        "DialogoIrA.campo": (_("Número del elemento"), _(
            "Escribe el número del elemento al que quieres ir y pulsa Intro. Solo se "
            "pueden escribir cifras; las flechas arriba y abajo suben y bajan el número sin "
            "salirse de la lista.\n\n"
            "Si el número no está entre 1 y el total, se dice y no se cierra, para que lo "
            "corrijas. Escape cancela y te deja donde estabas.")),
        "boton_fuentes": (_("Bibliotecas y carpetas"), _(
            "Abre la lista de carpetas y bibliotecas de calibre de las que salen los libros "
            "de la biblioteca, para añadirlas, actualizarlas, editarlas o quitarlas de "
            "varias en varias, y para hacer o restaurar una copia de seguridad.")),
        "biblioteca_calibre_modo": (_("Al añadir una biblioteca de calibre"), _(
            "Qué se hace cuando la carpeta que añades es una biblioteca de calibre (tiene su "
            "metadata.db).\n\n"
            "Importarla con los datos de calibre trae todo lo que calibre sabe de cada "
            "libro —autores, series, etiquetas, editorial, fechas, idiomas, valoración, "
            "identificadores, sinopsis y tus columnas propias— y es muchísimo más rápido que "
            "recorrer el disco: ciento noventa mil libros en medio minuto.\n\n"
            "Recomendado: importarla con los datos de calibre.")),
        "biblioteca_calibre_anidadas": (_("Bibliotecas de calibre dentro de una carpeta"), _(
            "Si al recorrer una carpeta aparece dentro una biblioteca de calibre, se "
            "importa aparte, como fuente propia y con todos sus datos, en lugar de recorrer "
            "sus archivos uno a uno.\n\n"
            "Recomendado: activado.")),
        "biblioteca_leer_metadatos": (_("Leer los metadatos de los EPUB"), _(
            "Al importar una carpeta corriente, de cada EPUB se leen los datos que trae "
            "dentro: título, autores, serie, fecha, idioma, editorial, materias, "
            "identificadores y sinopsis. Sin esto solo se sabe el nombre del archivo.\n\n"
            "Tarda más la primera vez —en un disco de los de girar, unos minutos por cada "
            "diez mil libros—; al actualizar solo se leen los que han cambiado.\n\n"
            "Recomendado: activado.")),
        "biblioteca_importar_sinopsis": (_("Importar las sinopsis"), _(
            "Guarda la sinopsis de cada libro —la de calibre o la del EPUB— para enseñarla "
            "en su ficha.\n\n"
            "Ocupan bastante: en una biblioteca de doscientos mil libros son cientos de "
            "megas. Si no las lees, apágalo y actualiza.")),
        "biblioteca_un_libro_por_formato": (_("Un libro por formato"), _(
            "Cuando un libro de calibre está en varios formatos (EPUB y PDF, por ejemplo): "
            "apagado sale una vez, con el formato preferido; encendido sale una vez por "
            "cada formato.\n\n"
            "Recomendado: apagado.")),
        "biblioteca_formatos_preferidos": (_("Formatos preferidos"), _(
            "Qué formato se elige cuando un libro está en varios, por orden de preferencia "
            "y separados por comas. El primero que tenga el libro es el que sale.\n\n"
            "Por omisión van primero los que mejor se leen con el programa (EPUB, AZW3, "
            "MOBI...) y al final los escaneados y el texto plano.")),
        "biblioteca_actualizar_al_abrir": (_("Poner al día calibre al abrir la biblioteca"), _(
            "Cada vez que abres la biblioteca, se miran en segundo plano tus bibliotecas de "
            "calibre y se trae lo que hayas cambiado en calibre desde la última vez. Si hay "
            "cambios se dice, y si no, no se dice nada.\n\n"
            "Con una biblioteca muy grande son unos segundos de trabajo de fondo cada vez. "
            "Recomendado: activado si usas calibre a menudo.")),
        "biblioteca_anunciar_avance": (_("Decir el avance"), _(
            "Mientras se importa, se actualiza o se busca, cada cuántos segundos se dice en "
            "voz alta por dónde va. Con 0 no se dice: queda en la barra de avance y en el "
            "texto de al lado.\n\n"
            "Recomendado: 10.")),
        "biblioteca_columnas": (_("Columnas de la lista de libros"), _(
            "Qué columnas tiene la lista de libros de la biblioteca. El título va siempre. "
            "Marca o desmarca con la barra espaciadora; Control+E las marca todas.\n\n"
            "Menos columnas es menos que oír al recorrer la lista; con las flechas "
            "izquierda y derecha se pasa de una a otra.")),
        "circular": (_("Continuar desde el principio al llegar al final"), _(
            "Cuando saltas al elemento siguiente —una tabla, un encabezado— y ya no queda "
            "ninguno, la búsqueda sigue desde el principio del documento en vez de pararse.\n\n"
            "Recomendado: desactivado. Si está activado y das muchas veces a la misma tecla "
            "puedes dar la vuelta sin darte cuenta y creer que estás donde no estás.")),
        "recordar": (_("Recordar la posición de lectura de cada documento"), _(
            "Guarda por dónde ibas en cada documento y te devuelve ahí al volver a abrirlo.\n\n"
            "Recomendado: activado. Es lo que permite dejar un libro a medias y retomarlo "
            "sin buscar. Lo guardado se puede borrar en Herramientas, «Datos guardados».")),
        "formato": (_("Mostrar la negrita y la cursiva"), _(
            "Marca visualmente el texto en negrita y en cursiva del documento.\n\n"
            "Es solo visual: los lectores de pantalla anuncian el formato por su cuenta si "
            "los tienes configurados para eso.\n\n"
            "Recomendado: desactivado. En un documento con muchas cursivas hace más lento el "
            "desplazamiento y no aporta nada a quien lee de oído.")),
        "cache": (_("Usar la caché"), _(
            "Guarda el resultado de analizar cada documento para que la próxima vez se abra "
            "al instante en vez de volver a procesarlo.\n\n"
            "La diferencia se nota sobre todo en documentos grandes y en PDF escaneados, "
            "donde reconocer el texto puede llevar minutos.\n\n"
            "Recomendado: activada. Ocupa espacio, sí, pero se limita sola y se puede vaciar "
            "entera o documento a documento en Herramientas, «Datos guardados».")),

        # ---- Accesibilidad -------------------------------------------------
        "decir_fila": (_("Decir el número de fila"), _(
            "Al recorrer una lista con las flechas izquierda y derecha, dice en qué fila "
            "estás: «fila 3 de 20».\n\n"
            "Recomendado: activado. Es lo que te sitúa en una lista larga.")),
        "decir_encabezado": (_("Decir el nombre de la columna"), _(
            "Al moverte por las columnas de una lista, dice de qué columna es cada dato: "
            "«Título», «Página», «Fecha».\n\n"
            "Recomendado: activado. Sin él oyes los datos sueltos sin saber qué son.")),
        "decir_contenido": (_("Decir el contenido de la celda"), _(
            "Dice lo que hay escrito en la celda.\n\n"
            "Recomendado: activado. Si lo desactivas junto con los otros dos, se dice el "
            "contenido de todos modos: sin él no quedaría nada que anunciar.")),
        "imagenes": (_("Señalar las imágenes sin descripción"), _(
            "Marca en el texto las imágenes que el documento no ha molestado en describir, "
            "en vez de saltárselas en silencio.\n\n"
            "Recomendado: activado. Saber que hay una imagen ahí te permite decidir si "
            "pedirle una descripción a la inteligencia artificial con la tecla A.\n\n"
            "Cambiar esto obliga a volver a abrir el documento.")),

        # ---- Reconocimiento ------------------------------------------------
        "pdf_modo": (_("Cómo se reconocen las páginas escaneadas"), _(
            "Un PDF escaneado son fotografías: no hay texto que leer y hay que reconocerlo. "
            "Aquí eliges con qué.\n\n"
            "• Tesseract viene incluido, va sin conexión, no gasta cuota y es el que mejor "
            "conserva las columnas y las tablas.\n"
            "• La inteligencia artificial lee mejor la letra difícil, tachada o sobre fondos "
            "de color, pero necesita conexión, gasta cuota y manda la página a un servidor.\n"
            "• El de Windows ya está en el sistema y es el más rápido.\n\n"
            "Recomendado: automático. Prueba Tesseract y, si no puede, sigue con los otros. "
            "Si un documento concreto no sale bien, prueba con la IA.")),
        "pdf_maximo": (_("Páginas que se reconocen como mucho"), _(
            "Tope de páginas que se reconocen en un mismo documento. A 0 no hay tope.\n\n"
            "Importa porque reconocer es lento: sin tope, un libro escaneado de quinientas "
            "páginas dejaría el programa abriendo durante horas, y con la inteligencia "
            "artificial además gastaría quinientas peticiones.\n\n"
            "Recomendado: 100. Si de verdad necesitas un libro entero, súbelo y déjalo "
            "trabajando; puedes cancelar en cualquier momento con Escape.")),
        "ocr_gris": (_("Pasar la página a escala de grises"), _(
            "Convierte la página a grises antes de reconocerla.\n\n"
            "Un OCR no lee la página que se ve: lee la que se le da. En un documento en "
            "color —un folleto, un cartel— la letra clara sobre fondo saturado se reconoce "
            "mal, y al pasar a gris las luminosidades quedan a distancias manejables.\n\n"
            "Recomendado: activado. Medido sobre un folleto real, junto con el contraste "
            "llevó los productos leídos con su precio de 7 a 10 sobre 14, y la basura de 31 "
            "líneas a 7.")),
        "ocr_contraste": (_("Contraste"), _(
            "Cuánto se separa lo oscuro de lo claro antes de reconocer. 10 es no tocar "
            "nada.\n\n"
            "Sube el contraste para que la letra destaque del fondo. Pasarse tampoco es "
            "bueno: por encima de 40 la letra fina empieza a romperse.\n\n"
            "Recomendado: 30, que es lo que mejor salió en las pruebas. Si el documento ya "
            "es blanco y negro limpio, bájalo a 10: no hace falta.")),
        "ocr_binarizar": (_("Dejar la página en blanco y negro puro"), _(
            "Convierte cada punto de la página en blanco o negro, sin grises.\n\n"
            "Recomendado: desactivado. Rompe la letra fina y en las pruebas salió peor que "
            "el gris con contraste. Vale la pena probarlo en un escaneado muy sucio, con "
            "manchas o con el papel amarilleado.")),
        "ocr_umbral": (_("Umbral del blanco y negro"), _(
            "A partir de qué luminosidad un punto se considera blanco, de 1 a 254.\n\n"
            "Bajarlo deja más cosas en negro —recupera letra clara, pero también manchas—; "
            "subirlo limpia el fondo a costa de perder trazos finos.\n\n"
            "Recomendado: 160. Solo hace algo si tienes activado el blanco y negro puro.")),
        "ocr_psm": (_("Cómo se segmenta la página"), _(
            "Le dice a Tesseract qué clase de página va a leer, y con eso decide cómo "
            "buscar los bloques de texto.\n\n"
            "• Automática detectando la orientación: sirve para casi todo y además endereza "
            "las páginas escaneadas torcidas.\n"
            "• Una sola columna: para un documento de texto corrido sin recuadros.\n"
            "• Un único bloque uniforme: para una captura o un recorte.\n"
            "• Texto disperso: para un cartel o una página con texto por todas partes y "
            "ninguna estructura. Encuentra más texto, pero en peor orden.\n\n"
            "Recomendado: automática detectando la orientación.")),
        "ocr_oem": (_("Motor interno de Tesseract"), _(
            "Tesseract lleva dentro dos reconocedores: el clásico, de los años noventa, y "
            "uno de redes neuronales bastante mejor.\n\n"
            "Recomendado: el que Tesseract prefiera, que elige el de redes neuronales "
            "cuando el idioma lo admite. El clásico solo compensa si necesitas velocidad "
            "por encima de acierto.")),
        "ocr_escala": (_("Aumento de la página"), _(
            "Con cuánto detalle se fotografía la página antes de reconocerla.\n\n"
            "Más aumento es más detalle, pero también más desenfoque y más lentitud. Llega "
            "un punto en que empeora: a 4 aumentos ya se reconocen peor los precios "
            "pequeños que a 3.\n\n"
            "Recomendado: el que convenga a cada motor. Eso son 3 aumentos para Tesseract y "
            "2 para los demás, que es lo que mejor salió midiendo.")),
        "ocr_dpi": (_("Resolución que se le declara a Tesseract"), _(
            "Los puntos por pulgada que se le dicen a Tesseract que tiene la imagen. A 0 "
            "los deduce él.\n\n"
            "Sirve para quitar el aviso de «estimating resolution» y, a veces, para afinar "
            "la segmentación de un documento raro.\n\n"
            "Recomendado: 0. Solo tócalo si sabes la resolución real del escaneado.")),
        "ocr_confianza": (_("Confianza mínima para quedarse con una palabra"), _(
            "Tesseract puntúa de 0 a 100 lo seguro que está de cada palabra. Por debajo de "
            "este número, la palabra se tira.\n\n"
            "Subirlo limpia el ruido que salen de los adornos, pero cuidado: en un folleto, "
            "los precios sobre fondo de color se reconocen con poca confianza y se "
            "perderían. En las pruebas, subirlo de 30 a 50 quitó 5 líneas de basura pero "
            "también 3 precios.\n\n"
            "Recomendado: 30.")),
        "ocr_esmerado": (_("Leer cada página dos veces"), _(
            "Reconoce cada página dos veces, con la imagen preparada de dos formas "
            "distintas, y junta lo leído.\n\n"
            "Funciona porque las dos lecturas no fallan en los mismos sitios: la primera "
            "lee bien el texto oscuro sobre fondo claro y se come el precio que va sobre un "
            "círculo rojo; la segunda, al revés. De la segunda solo se añade lo que cae "
            "donde la primera no encontró nada, así que no se repite ni una palabra.\n\n"
            "Medido sobre un folleto de supermercado en color, pasó de 15 a 19 productos "
            "leídos con su precio al lado, de 23. Es lo que más mejora el resultado en "
            "documentos difíciles.\n\n"
            "Recomendado: activado. Tarda aproximadamente el doble, así que si vas a "
            "reconocer un libro entero de texto limpio puedes desactivarlo.")),
        "ocr_simbolos": (_("Descartar los adornos y símbolos sueltos"), _(
            "Tira lo que se ha reconocido y no tiene ninguna letra ni ningún número: "
            "flechas, marcos, iconos, restos de degradados.\n\n"
            "En un documento que se lee de oído esto no es cosmético: cada uno de esos es "
            "una línea que hay que oír y descartar a mano.\n\n"
            "Recomendado: activado. No se pierde nada legible, porque solo se quita lo que "
            "no tiene ni una letra.")),
        "ocr_tablas": (_("Reconstruir las tablas como tablas de verdad"), _(
            "Cuando el reconocimiento encuentra una rejilla —mismas filas en todas las "
            "columnas y a las mismas alturas— la escribe como tabla, y así se puede recorrer "
            "celda a celda con las órdenes de tabla de tu lector de pantalla.\n\n"
            "El orden de lectura se reconstruye siempre, esté esto como esté: sin él, un "
            "documento a varias columnas se lee cruzando de una a otra.\n\n"
            "Recomendado: activado.")),

        # ---- DAISY ---------------------------------------------------------
        "daisy_velocidad": (_("Velocidad de la grabación DAISY"), _(
            "A qué velocidad suena la voz del narrador que viene grabada dentro del libro "
            "DAISY. 100 es la velocidad a la que se grabó.\n\n"
            "No es la velocidad de la voz sintética: esa se ajusta en el menú «Voz», en "
            "«Voz y velocidad de la voz sintética» (Control+Alt+V). Son dos cosas distintas "
            "porque son dos voces distintas.\n\n"
            "Se cambia sin alterar el tono, así que subirla no convierte al narrador en un "
            "pato. Mucha gente escucha a 150 o más.\n\n"
            "Recomendado: 100 para empezar y subir hasta donde se siga entendiendo. También "
            "se cambia mientras suena con Control+Alt+Arriba y Control+Alt+Abajo.")),
        "daisy_volumen": (_("Volumen de la grabación"), _(
            "Volumen al que suena la grabación del libro DAISY, del 0 al 100.\n\n"
            "Es independiente del volumen de Windows y del de la voz sintética.\n\n"
            "Recomendado: 100, y bajar el de Windows si hace falta.")),
        "daisy_cursor": (_("Mover el cursor siguiendo a la grabación"), _(
            "Mientras suena la grabación, el cursor del texto se va moviendo a la frase que "
            "se está oyendo.\n\n"
            "Sirve para poder consultar en cualquier momento con tu lector de pantalla lo "
            "que acaba de sonar, y para saber por dónde vas. En un libro DAISY de solo "
            "audio es además la única forma de situarse.\n\n"
            "Recomendado: activado.")),
        "daisy_al_abrir": (_("Empezar a reproducir al abrir"), _(
            "Al abrir un libro DAISY que trae grabación, empieza a sonar solo.\n\n"
            "Recomendado: desactivado. Quien abre un libro no siempre quiere que le suene "
            "de golpe; con Control+Espacio empieza cuando tú quieras.")),

        # ---- Avanzado ------------------------------------------------------
        "idioma": (_("Idioma de la interfaz"), _(
            "En qué idioma se ven y se oyen los textos del programa.\n\n"
            "Los idiomas se detectan solos: el desplegable enseña los que haya en la carpeta "
            "«data/idiomas», con el nombre de cada lengua escrito en esa misma lengua.\n\n"
            "El cambio se aplica al reiniciar el programa.")),
        # ---- Actualizaciones ------------------------------------------------
        "comprobar_actualizaciones": (
            _("Comprobar al arrancar si hay una versión nueva"), _(
            "Al abrir el programa se pregunta al servidor si hay una versión más "
            "moderna que la instalada.\n\n"
            "Es una consulta diminuta —unos cientos de bytes— que se hace en segundo "
            "plano y no retrasa la apertura del documento. Si no hay versión nueva, o "
            "si no hay conexión, no dice nada: solo habla cuando hay algo que decir.\n\n"
            "Si aparece una versión nueva se te ofrece instalarla, con un botón para "
            "dejarlo para otro rato. La instalación no toca tus ajustes, tus marcadores "
            "ni tus documentos.\n\n"
            "Recomendado: activado. Enterarse de que hay una corrección esperando es la "
            "diferencia entre tenerla y no tenerla.")),
        "actualizaciones_origen": (
            _("Dónde se buscan las actualizaciones"), _(
            "Cada versión nueva se publica en dos sitios con el mismo paquete: el servidor "
            "del autor y GitHub. Aquí eliges dónde mirar:\n\n"
            "• El servidor del autor y GitHub: se pregunta a los dos a la vez y se ofrece "
            "la versión más nueva que tenga cualquiera. Si la descarga falla en uno, se "
            "intenta en el otro. Es lo recomendado: un servidor caído no te deja sin "
            "actualizaciones.\n"
            "• Solo el servidor del autor, o solo GitHub: útil si alguno de los dos está "
            "bloqueado en tu red.\n"
            "• Una dirección personalizada: la que escribas debajo, por ejemplo un espejo "
            "en tu propia red.\n\n"
            "Venga de donde venga, el paquete se comprueba igual: su resumen sha256 y la "
            "firma del autor. Un paquete que no esté firmado por el autor no se instala, "
            "sea cual sea su origen.")),
        "actualizaciones_url": (
            _("Dirección personalizada de actualizaciones"), _(
            "Solo se usa si en «Buscar las actualizaciones en» eliges «Una dirección "
            "personalizada».\n\n"
            "Puede ser una carpeta web donde estén los dos archivos que se publican con "
            "cada versión, version.json y el paquete ZIP —por ejemplo "
            "«https://mi-servidor/VisorUniversal»—, o la dirección de un repositorio de "
            "GitHub que publique esos dos archivos en sus releases.\n\n"
            "Sirve para tener un espejo, no para instalar paquetes de otra persona: el "
            "programa solo instala lo que lleve la firma del autor.")),

        # ---- Pronunciación ---------------------------------------------------
        "activa": (_("Aplicar el diccionario de pronunciación"), _(
            "Activa o desactiva de golpe todas las reglas de pronunciación, las de este "
            "documento y las generales.\n\n"
            "Sirve para comparar: apágalo, escucha un párrafo, enciéndelo y vuelve a "
            "escucharlo. Así se oye si una regla mejora o empeora.\n\n"
            "Las reglas cambian **solo lo que se oye**: el texto que se ve, se copia y "
            "se busca sigue siendo exactamente el del autor.\n\n"
            "Recomendado: activado.")),
        "buscar": (_("Lo que está escrito en el libro"), _(
            "La palabra tal y como aparece escrita en el documento: «Daenerys», «S.A.», "
            "«CD-ROM».\n\n"
            "Se busca sin distinguir mayúsculas salvo que marques la casilla "
            "correspondiente, así que una sola regla vale para la palabra al principio "
            "de una frase y en medio.\n\n"
            "Recomendado: escribe la palabra entera, no un trozo. Los trozos se cuelan "
            "dentro de otras palabras.")),
        "decir": (_("Cómo hay que decirlo"), _(
            "Lo que la voz dirá en su lugar, escrito tal y como suena: «Danerís» por "
            "«Daenerys», «sociedad anónima» por «S.A.».\n\n"
            "Prueba con el botón «Probar cómo suena» antes de guardar: cada voz "
            "pronuncia distinto y lo que funciona con una puede no funcionar con otra.\n\n"
            "**Dejándolo vacío, eso no se dice**. Es la forma de silenciar los adornos "
            "que trae el documento —cadenas de asteriscos, marcas de maquetación— sin "
            "tener que tocar el libro.")),
        "completa": (_("Solo cuando sea la palabra entera"), _(
            "La regla se aplica únicamente cuando lo buscado es una palabra completa, no "
            "cuando aparece dentro de otra.\n\n"
            "Sin esto, cambiar «Ana» por «Anna» convertiría «mañana» en «mañAnna» y «rana» "
            "en «rAnna». Con esto puesto, solo cambia la palabra «Ana» suelta.\n\n"
            "Recomendado: activado, salvo que quieras cambiar una terminación o un "
            "símbolo pegado a otras palabras.")),
        "mayusculas": (_("Distinguir mayúsculas de minúsculas"), _(
            "La regla solo se aplica si las mayúsculas coinciden exactamente.\n\n"
            "Hace falta cuando la misma letra significa cosas distintas según cómo esté "
            "escrita: «US» el país y «us» la palabra inglesa, o una sigla que también es "
            "una palabra común.\n\n"
            "Recomendado: desactivado. Así una sola regla vale para la palabra al "
            "principio de una frase y en medio.")),

        # ---- Exportar a audio -------------------------------------------------
        "reparto": (_("Cómo se reparte el audio"), _(
            "Decide si sale un archivo por capítulo o uno solo con todo el documento.\n\n"
            "Un archivo por capítulo es lo cómodo para escuchar en el móvil o en el "
            "coche: se salta de capítulo con los botones del reproductor y cada uno "
            "recuerda por dónde iba.\n\n"
            "Un solo archivo va mejor para un documento corto, o si vas a pasarlo a un "
            "aparato que no ordena bien las listas.\n\n"
            "Recomendado: por capítulos en un libro; un solo archivo en un documento de "
            "unas pocas páginas.")),
        "formato": (_("Formato del audio"), _(
            "MP3 comprime el sonido: un libro entero ocupa unas decenas de megas y lo "
            "abre cualquier reproductor, móvil o coche.\n\n"
            "WAV no comprime nada: suena exactamente igual —es una voz sintética, no hay "
            "matices que perder— pero ocupa entre diez y quince veces más.\n\n"
            "Recomendado: MP3. El WAV solo tiene sentido si vas a editar el audio con "
            "otro programa.")),
        "voz": (_("Voz con la que se graba"), _(
            "La voz de Windows que leerá el documento en los archivos generados.\n\n"
            "Puede ser distinta de la que usas para leer en pantalla: para escuchar un "
            "libro entero conviene una voz que canse poco, aunque para leer por encima "
            "prefieras otra más rápida.\n\n"
            "Recomendado: pruébala antes en Control+Alt+V, que ahí se oye al momento.")),
        "velocidad": (_("Velocidad de la grabación"), _(
            "A qué velocidad hablará la voz en los archivos generados. 50 es la normal "
            "de la voz; por debajo va más despacio y por encima, más deprisa.\n\n"
            "Ojo con pasarse: una velocidad que se sigue bien delante del ordenador puede "
            "resultar agotadora escuchando una hora seguida en el coche.\n\n"
            "Recomendado: la misma con la que lees a diario, o un poco más despacio.")),
        "carpeta": (_("Carpeta de destino"), _(
            "Dónde se dejan los archivos de audio.\n\n"
            "Se propone la carpeta del documento, o la última que usaste. Conviene una "
            "carpeta vacía o propia del libro: si eliges un archivo por capítulo pueden "
            "salir decenas de archivos.\n\n"
            "Al terminar se te ofrece abrirla, para copiarlos al móvil sin buscarlos.")),

        # ---- Temporizador -----------------------------------------------------
        "tiempo": (_("Detener la lectura dentro de"), _(
            "Cuánto tiempo se seguirá leyendo antes de callar. Sirve para dormirse "
            "escuchando sin que el libro siga sonando toda la noche.\n\n"
            "Un minuto antes del final se avisa con voz, y durante los últimos segundos "
            "el sonido se va apagando poco a poco en vez de cortarse de golpe.\n\n"
            "Manda igual sobre la voz sintética y sobre las grabaciones de un libro "
            "DAISY, así que no hay que acordarse de cuál está sonando.\n\n"
            "Recomendado: 30 minutos, que es lo que suele tardarse en dormir.")),

        # ---- Diccionario -------------------------------------------------------
        "palabra": (_("Palabra que se busca"), _(
            "La palabra que se va a definir. Viene puesta la del cursor, o lo que "
            "tuvieras seleccionado, así que normalmente no hay que escribir nada.\n\n"
            "Si tenías texto seleccionado manda la selección: es la forma de definir una "
            "locución de varias palabras, como «a la sazón», que suelta no significa lo "
            "mismo que sus partes.\n\n"
            "Se puede escribir cualquier otra palabra y pulsar Intro para buscarla.")),
        "fuente": (_("Dónde se busca la palabra"), _(
            "Las tres fuentes sirven para cosas distintas:\n\n"
            "**El diccionario de la RAE** es la referencia del español: da la etimología, "
            "las acepciones numeradas con su categoría gramatical y los sinónimos y "
            "antónimos de cada una. Necesita conexión.\n\n"
            "**El Wikcionario** cubre cualquier idioma, así que es la fuente para un "
            "libro que no esté en español. Necesita conexión.\n\n"
            "**La inteligencia artificial** es la única que entiende el contexto: se le "
            "pasa la frase del documento, así que distingue el «banco» de sentarse del de "
            "dinero, y define también nombres propios y tecnicismos que no salen en "
            "ningún diccionario. Necesita conexión, estar configurada y gasta cuota.\n\n"
            "Recomendado: la RAE para leer en español; la IA cuando la palabra no "
            "aparezca o cuando dudes de en qué sentido se usa.")),
        "resultado": (_("Definición"), _(
            "Lo que ha contestado la fuente elegida, en un cuadro que se recorre con las "
            "flechas para poder releer una acepción concreta.\n\n"
            "Se lee entero al llegar, que es lo que se ha venido a oír. Con el botón "
            "«Copiar» se lleva al portapapeles, y con F5 se vuelve a consultar.")),
        # ---- IA local ------------------------------------------------------
        "ollama_asistente": (_("Asistente para instalar la IA local"), _(
            "Monta paso a paso una inteligencia artificial que funciona dentro de este "
            "ordenador, sin cuenta, sin clave y sin que nada salga del equipo.\n\n"
            "Son cinco pantallas: mira qué ordenador tienes, descarga el motor (Ollama), "
            "te deja elegir un modelo de una lista corta donde cada uno dice para qué es "
            "bueno, lo descarga y lo prueba de verdad antes de dejarlo activado.\n\n"
            "Todo va a parar a la carpeta «data» del programa: no se instala nada en "
            "Windows y no se toca el Ollama que puedas tener por tu cuenta, porque este "
            "usa su propio puerto y su propio almacén de modelos.\n\n"
            "Lo que ocupa: el motor algo más de un giga, y el modelo entre dos y siete "
            "según el que elijas. Se descarga una vez.")),
        "ollama_estado": (_("Estado de la IA local"), _(
            "Dice si la IA local está instalada, si su servidor está en marcha, en qué "
            "dirección escucha y cuánto ocupan los modelos que tienes descargados.\n\n"
            "También es donde aparecen los avisos de los botones de al lado: al arrancar, "
            "al detener o al instalar un modelo, el resultado se escribe aquí arriba para "
            "que lo puedas leer con las flechas.\n\n"
            "Si dice que en el puerto contesta otro servidor que no es el de este "
            "programa, es que tienes Ollama instalado por tu cuenta y algo lo ha puesto "
            "en nuestro puerto. El programa no lo va a usar ni a cerrar: ciérralo tú.")),
        "ollama_modelo": (_("Modelo con el que se trabaja"), _(
            "Cuál de los modelos descargados se usa para describir imágenes y responder "
            "preguntas.\n\n"
            "Puedes tener varios instalados y cambiar de uno a otro cuando quieras: uno "
            "ligero para el día a día y otro más capaz para cuando haga falta.\n\n"
            "Para describir imágenes el modelo tiene que **admitir imágenes**. Los que "
            "instala el asistente las admiten todos. Si añades uno por tu cuenta y es de "
            "solo texto, aceptará la petición pero no verá la ilustración.\n\n"
            "La lista se llena preguntándole al servidor, así que si está parado puede "
            "salir vacía: arráncalo y pulsa «Actualizar la lista».")),
        "ollama_calculo": (_("Con qué calcula la IA local"), _(
            "Si el trabajo lo hace la tarjeta gráfica o el procesador.\n\n"
            "**Usar la tarjeta gráfica si la hay**: lo normal. Con una tarjeta decente, "
            "describir una imagen son segundos.\n\n"
            "**Usar solo el procesador**: más lento —de medio minuto a un par de minutos "
            "por imagen— pero funciona en cualquier equipo. Elígelo también si tu tarjeta "
            "es integrada y con poca memoria: en ese caso puede ser más lenta que el "
            "procesador, o quedarse sin sitio a mitad y fallar.\n\n"
            "Recomendado: dejar «si la hay». Cambia a procesador solo si ves fallos de "
            "memoria de vídeo.\n\n"
            "Cambiar esto pide reiniciar el servidor, con el botón «Reiniciar».")),
        "ollama_mantener": (_("Minutos que el modelo se queda cargado"), _(
            "Cargar un modelo en memoria lleva entre diez segundos y un minuto. Mientras "
            "sigue cargado, cada pregunta se responde al momento.\n\n"
            "Con 5 minutos, describir diez imágenes seguidas paga esa carga una sola vez. "
            "Con 0 se descarga en cuanto termina, lo que libera memoria pero hace que "
            "cada petición vuelva a esperar.\n\n"
            "Recomendado: 5. Súbelo si vas a estar un rato preguntando; bájalo a 0 si "
            "andas justo de memoria.\n\n"
            "Cambiar esto pide reiniciar el servidor.")),
        "ollama_contexto": (_("Tamaño del contexto"), _(
            "Cuánto texto es capaz de tener en cuenta el modelo de una vez, medido en "
            "fichas (más o menos, tres cuartos de palabra cada una).\n\n"
            "A 0 se usa el que traiga el propio modelo, que es lo que conviene salvo que "
            "sepas lo que haces. Subirlo permite preguntar sobre trozos más largos, pero "
            "**gasta mucha más memoria** y puede hacer que el modelo no quepa.\n\n"
            "Recomendado: 0.\n\n"
            "Cambiar esto pide reiniciar el servidor.")),
        "ollama_atencion": (_("Atención rápida"), _(
            "Una forma de calcular que ahorra memoria y va algo más deprisa en las "
            "tarjetas gráficas que la admiten. En las que no, el servidor la ignora sin "
            "dar problemas.\n\n"
            "Recomendado: activada si tienes tarjeta gráfica. Sin tarjeta no cambia "
            "nada.\n\n"
            "Cambiar esto pide reiniciar el servidor.")),
        "ollama_al_abrir": (_("Arrancar el servidor al abrir el programa"), _(
            "Levanta la IA local nada más abrir el lector, en segundo plano.\n\n"
            "Con esto puesto, la primera descripción que pidas no tiene que esperar a que "
            "arranque el servidor. A cambio, el servidor ocupa memoria desde el principio "
            "aunque no llegues a usarlo.\n\n"
            "Recomendado: desactivado. Sin esto se arranca solo la primera vez que se le "
            "pide algo, y son unos segundos.")),
        "ollama_al_salir": (_("Cerrar el servidor al salir del programa"), _(
            "Apaga la IA local al cerrar el lector.\n\n"
            "Recomendado: activado. Dejar un servidor de inteligencia artificial "
            "corriendo después de cerrar el programa no es lo que nadie espera, y sigue "
            "ocupando memoria hasta que se apaga el equipo.\n\n"
            "Desactívalo solo si usas ese mismo servidor desde otro programa y quieres "
            "que siga en marcha.\n\n"
            "Solo se cierra el servidor de este programa: si tienes Ollama instalado por "
            "tu cuenta, el tuyo no se toca nunca.")),
        "ollama_desinstalar": (_("Quitar la IA local del disco"), _(
            "Borra el motor y todos los modelos descargados.\n\n"
            "Es lo que hay que hacer para recuperar el espacio: entre el motor y un par "
            "de modelos se van varios gigas.\n\n"
            "Se puede volver a instalar cuando quieras con el asistente, pero habrá que "
            "descargarlo todo otra vez.")),
        "boton_montar_ia": (_("¿No sabes montar tu IA local?"), _(
            "Abre el asistente que instala una inteligencia artificial completa dentro de "
            "este programa.\n\n"
            "Está aquí porque es justo donde se planta quien quiere IA local: eliges "
            "«modelo local» y te encuentras con que hay que dar la dirección de un "
            "servidor que no tienes y que no sabes montar.\n\n"
            "El asistente descarga el motor, te deja elegir un modelo con visión de una "
            "lista corta, lo descarga y lo prueba. Después no hay que escribir ninguna "
            "dirección: el programa usa la suya.")),
        "ollama_resumen": (_("Estado de la IA local del programa"), _(
            "Dice si la IA local está instalada, si está en marcha y con qué modelo "
            "trabaja.\n\n"
            "Con este proveedor no hay nada que rellenar: la dirección, el puerto y el "
            "modelo los pone el programa. Todo lo que se puede tocar —arrancar, parar, "
            "instalar modelos, elegir si usa la tarjeta gráfica— está en la pestaña «IA "
            "local».")),
        "ollama_listar": (_("Actualizar la lista de modelos"), _(
            "Vuelve a preguntarle al servidor qué modelos tienes descargados.\n\n"
            "Hace falta después de instalar o importar uno desde fuera del programa, y "
            "cuando la lista sale vacía porque el servidor estaba parado: arráncalo y "
            "pulsa aquí.")),
        "ollama_instalar": (_("Instalar otro modelo"), _(
            "Descarga un modelo más de la biblioteca de Ollama y lo deja listo para "
            "usar.\n\n"
            "Se ofrece la misma lista corta que en el asistente, con lo que ocupa cada "
            "uno y para qué es bueno, más la posibilidad de escribir el nombre de "
            "cualquier otro modelo de la biblioteca si sabes cuál quieres.\n\n"
            "Puedes tener varios instalados y cambiar de uno a otro cuando quieras.")),
        "ollama_importar": (_("Importar un modelo del disco"), _(
            "Mete en la IA local un modelo que **ya tengas descargado**, en formato "
            "GGUF, sin bajar nada de internet.\n\n"
            "Para qué sirve: usar un modelo que no está en la biblioteca de Ollama, "
            "aprovechar uno que ya te habías bajado para otro programa, o instalarlo "
            "desde un disco externo si andas justo de conexión.\n\n"
            "**Se piden dos archivos.** Un modelo que ve imágenes son dos cosas: los "
            "pesos, que es el archivo grande, y el **proyector de visión**, que "
            "convierte la imagen en algo que los pesos entiendan. El proyector suele "
            "llamarse «mmproj-algo.gguf» y es mucho más pequeño. Si eliges el modelo, "
            "el programa busca el proyector en la misma carpeta y lo pone solo.\n\n"
            "Sin el proyector el modelo se importa igual, pero **no podrá describirte "
            "imágenes**: servirá solo para preguntas sobre el texto. Se avisa antes de "
            "hacerlo.\n\n"
            "El archivo original no se toca: se copia al almacén del programa, así que "
            "después puedes borrarlo si quieres recuperar el espacio. La copia lleva su "
            "rato —son varios gigas— y va con barra de progreso y con Escape para "
            "cancelar.")),
        "ollama_borrar": (_("Borrar el modelo elegido"), _(
            "Quita del disco el modelo que esté seleccionado en la lista de arriba.\n\n"
            "Es lo que hay que hacer para recuperar espacio cuando tienes varios y no "
            "los usas: cada uno ocupa entre dos y siete gigas.\n\n"
            "Se puede volver a descargar o a importar cuando quieras. Solo se borra de "
            "la IA local de este programa; si el modelo lo importaste de un archivo "
            "tuyo, ese archivo sigue donde estaba.")),
    }


def ayuda_de(control: wx.Window, dialogo: wx.Window) -> tuple[str, str] | None:
    """Busca la ayuda del control, subiendo por sus padres si hace falta.

    Se busca por el nombre del atributo con el que el control vive en su
    diálogo.  Si el foco está en una pieza interna de un control compuesto, se
    sube al padre, que es el que sí figura en el catálogo.
    """
    catalogo = ayudas()
    for atributo, valor in vars(dialogo).items():
        if valor is not control:
            continue
        for clave in claves_de(dialogo, atributo):
            if clave in catalogo:
                return catalogo[clave]
    padre = control.GetParent()
    if padre is not None and padre is not dialogo:
        return ayuda_de(padre, dialogo)
    return None


def claves_de(dialogo, atributo: str) -> list[str]:
    """Las claves con las que buscar un control, de la más concreta a la menos.

    Primero ``NombreDeLaVentana.atributo`` y después ``atributo`` a secas.  Así
    la ``lista`` del cuaderno y la de la biblioteca pueden explicarse cada una a
    su manera sin obligar a renombrar controles.
    """
    return ["%s.%s" % (type(dialogo).__name__, atributo), atributo]
