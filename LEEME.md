# Visor Universal

**Documento técnico.** Lector accesible de libros y documentos escrito en
Python 3 con interfaz wxPython, pensado para leer con el teclado y con lector de
pantalla. Aquí se cuenta cómo está hecho cada formato, las decisiones de diseño y
por qué se tomaron.

- Presentación, descarga y cómo colaborar: [`README.md`](README.md)
- Manual para el usuario final: [`data/idiomas/es/docs/MANUAL_USUARIO.md`](data/idiomas/es/docs/MANUAL_USUARIO.md)
- Todo se maneja desde: **`VisorUniversal.bat`**

---

## Puesta en marcha

Ejecuta `VisorUniversal.bat` y elige una opción del menú:

| Opción | Qué hace |
|---|---|
| 1 | **Elige con qué versión de Python** crear el entorno e instala los requisitos |
| 2 | Ejecuta el programa desde el código fuente |
| 3 | Compila el ejecutable con cx_Freeze en `build\VisorUniversal\` |
| 4 | Abre la carpeta del ejecutable compilado |
| 5 | Reinstala o actualiza los requisitos |
| 6 | Limpia compilaciones, caché y temporales |
| 7 | Comprueba que la instalación es correcta |
| 8 | Elimina el entorno virtual |
| 9 | Prepara el paquete de actualización (ZIP firmado + `version.json`) |
| T | Editor accesible de traducciones |
| F | Estado de la firma de las actualizaciones |
| P | Batería de pruebas |

La opción 1 detecta **todas** las versiones de Python instaladas
(`herramientas/detectar_python.py`) y las presenta numeradas con su versión,
su arquitectura y su ruta. Las compilaciones «sin GIL» (*free-threading*) se
omiten, porque wxPython no publica paquetes para ellas y el entorno nacería
inservible; las versiones más recientes que la última con wxPython conocido se
listan con un aviso y piden confirmación.

La versión elegida queda anotada en `entorno\python_usado.txt` y se muestra en
la cabecera del menú. A partir de ahí **todo** —ejecutar, compilar, comprobar—
usa `entorno\Scripts\python.exe`, nunca el Python del sistema.

> El archivo `.bat` debe guardarse con saltos de línea de Windows (CRLF). Con
> saltos de Unix (LF), `cmd.exe` pierde la cuenta de las posiciones dentro del
> archivo y falla al buscar etiquetas.

---

## Rendimiento medido

Con *La rueda del tiempo* (EPUB de 20,1 MB, 857 capítulos, 28.886.508
caracteres, 104.801 líneas), en el ejecutable compilado:

| Operación | Tiempo |
|---|---|
| Primera apertura (análisis completo) | **1,11 s** |
| Aperturas siguientes (desde la caché) | **0,13 s** |
| Cargar el tramo de texto en la ventana | 65 ms |
| Saltar al encabezado siguiente | 7 ms |
| Saltar del principio al final del libro | 240 ms |
| Buscar una expresión en todo el libro | 250 ms (la primera vez) |
| Contar sus 20.267 apariciones | 22 ms |

Comprobado además contra **400 libros EPUB reales**: 0 fallos, 0,15 s de media.

---

## Cómo está organizado

```
ePubViewer/
├── VisorUniversal.bat        Menú de tareas (instalar, ejecutar, compilar)
├── requirements.txt         Requisitos
├── setup_cx.py              Compilación con cx_Freeze
├── NOVEDADES.md             Qué cambia en cada versión; de aquí salen las
│                            «Novedades» que enseña el actualizador
├── herramientas/
│   ├── empaquetar.py        Deja el ZIP y el version.json listos para subir
│   ├── textos.py            Extrae los textos, crea idiomas y compila los .mo
│   ├── traductor.py         Traducción automática que respeta las variables
│   ├── editor_idiomas.py    Editor accesible de traducciones (opción T del menú)
│   └── detectar_python.py   Localiza los Python instalados, para el menú
├── data/                    TODO lo que acompaña o genera el programa
│   ├── idiomas/             Traducciones y documentación, una carpeta por idioma
│   │   └── es/docs/         El manual de usuario, en su idioma original
│   ├── config/              Ajustes, posiciones, marcadores y notas
│   ├── logs/                Registro de actividad y de errores
│   ├── cache/               Libros ya analizados
│   ├── sonidos/             Sonidos de navegación (se generan solos)
│   └── temp/                Temporales (incluido el manual convertido)
└── src/
    ├── main.py              Punto de entrada
    ├── nucleo/              Lógica independiente de la interfaz
    │   ├── rutas.py         Localización de la carpeta «data»
    │   ├── idioma.py        Traducción de la interfaz (gettext)
    │   ├── registro.py      Sistema de registro avanzado
    │   ├── configuracion.py Preferencias y datos por libro
    │   ├── texto.py         Normalización de texto y unidades de posición
    │   ├── marcas.py        Marcas de estructura e índices por tipo
    │   ├── documento.py     Modelo del libro analizado
    │   ├── navegacion.py    Motor de saltos entre elementos
    │   ├── busqueda.py      Búsqueda de texto
    │   ├── marcado.py       Conversor propio de Markdown a HTML
    │   ├── html_elementos.py  Tablas, listas y citas reconstruidas en HTML
    │   ├── accesibilidad.py Qué trae el documento para poder leerse
    │   ├── ia/ollama.py      Ollama portable: instalarlo, arrancarlo, modelos
    │   ├── ia/modelos_vision.py  Qué modelos con visión se ofrecen y para qué
    │   ├── segmentador.py   Partido del texto en frases, para la voz
    │   ├── voz.py           Voz del sistema (SAPI 5)
    │   ├── descripciones.py Descripciones de imágenes guardadas por libro
    │   ├── ia/              Descripción de imágenes con Gemini o en local
    │   ├── daisy.py         Lectura del formato DAISY: NCC, NCX, SMIL, frases
    │   ├── tesseract.py     Tesseract portable y sus idiomas
    │   ├── audio.py         Reproducción de audio sobre basskit (BASS)
    │   ├── instancia.py     Una sola copia del programa a la vez
    │   ├── correcciones.py  Lo que el usuario corrige de un PDF, atado a su huella
    │   ├── resaltados.py    Sacar los pasajes resaltados a txt, Markdown o HTML
    │   └── cache.py         Caché de libros analizados
    ├── formatos/            Analizadores de formato
    │   ├── base.py          Interfaz común y registro de formatos
    │   ├── lectura_xml.py   Analizadores XML/HTML tolerantes y sin red
    │   ├── conversor.py     XHTML → texto plano + marcas
    │   ├── ensamblador.py   Secciones XHTML → Documento (lo comparten todos)
    │   ├── tablas.py        Tablas HTML → texto
    │   ├── epub.py          EPUB 2 y 3
    │   ├── texto.py         TXT, Markdown, HTML y FictionBook
    │   ├── ofimatica.py     DOCX, ODT y RTF
    │   ├── pdf.py           PDF: etiquetados, normales y escaneados
    │   ├── pdf_etiquetado.py  Árbol de estructura de los PDF accesibles
    │   ├── pdf_diagnostico.py  Qué es el archivo: cifrado, catálogo, fuentes
    │   ├── pdf_geometria.py   Estructura deducida de cómo está escrita la página
    │   ├── pdf_reparacion.py  Reconstruir el índice de un PDF roto, en copia
    │   ├── pdf_auditoria.py   Qué le falta al documento, según la norma PDF/UA
    │   ├── pdf_hallazgos.py   Lo encontrado, con su gravedad y su remedio
    │   ├── daisy.py         DAISY: el texto, siguiendo el orden del SMIL
    │   ├── ocr.py           Reconocimiento: Tesseract, IA y Windows
    │   ├── disposicion.py   Orden de lectura y detección de tablas
    │   ├── imagen.py        Preparar la página antes de reconocerla
    │   └── png.py           Codificador de PNG para pasarle la página al OCR
    ├── version.py           Versión, autoría y enlaces (se lee sin importar nada)
    ├── interfaz/            Interfaz gráfica wxPython
    │   ├── app.py           Objeto de aplicación
    │   ├── ventana.py       Ventana principal
    │   ├── lector.py        Panel de lectura y ventana deslizante
    │   ├── sesion.py        Un documento abierto y todo lo suyo (una pestaña)
    │   ├── pestanas.py      Los documentos abiertos, con lengüetas o sin ellas
    │   ├── arbol.py         Árbol de contenido de la zona izquierda
    │   ├── lectura_voz.py   Lectura en voz alta frase a frase
    │   ├── reproductor_daisy.py  Reproductor de las grabaciones DAISY
    │   ├── teclas_globales.py  Teclas del lector para todo el sistema
    │   ├── bandeja.py       Icono en la bandeja del sistema
    │   ├── atajos.py        Tabla de atajos de teclado
    │   ├── anuncios.py      Comunicación con el lector de pantalla
    │   ├── accesible.py     Nombres accesibles de los controles
    │   ├── listas.py        Listas recorribles por columnas con las flechas
    │   ├── colores.py       Paleta de colores con nombre
    │   ├── ventanas_win32.py  Ajustes que exigen hablar con Windows
    │   └── dialogos/        Índice, elementos, opciones, IA, registro, visor HTML...
    └── sonidos/             Síntesis y reproducción de los sonidos
```

---

## Las tres decisiones que explican la velocidad

Están tomadas del funcionamiento de [Paperback](https://paperback.dev), el
lector en Rust que sirvió de referencia.

**1. El libro se convierte en un único texto plano con marcas.**
No se renderiza HTML. Cada capítulo se convierte a texto y su estructura
(encabezados, enlaces, imágenes, listas, tablas, separadores, citas) se guarda
aparte como una lista de posiciones etiquetadas. Saltar al siguiente elemento
de un tipo es entonces una búsqueda binaria sobre una lista de enteros:
instantáneo por grande que sea el libro. Además, al ser texto plano en un
control de edición nativo, el lector de pantalla lo lee sin intermediarios.

**2. Ventana deslizante en el control de texto, solo cuando hace falta.**
Medido en este equipo, cargar texto en el control cuesta 64 ms con 800.000
caracteres, 340 ms con 3 millones y 2,2 s con 10 millones; en cambio, mover el
cursor cuesta lo mismo (~1,6 ms por línea) con cualquiera de esos tamaños. Por
eso el umbral está en **3 millones de caracteres**: por debajo, el libro se
carga entero y todas las teclas propias del control (Control+Fin, Av Pág, la
barra de desplazamiento, seleccionar todo) abarcan el libro completo. Por
encima se cargan 1,2 millones alrededor del cursor y el tramo se recoloca solo
cuando el cursor se acerca a un borde. Fuera de `interfaz/lector.py` todas las
posiciones son absolutas dentro del libro: los tramos son invisibles para el
resto del programa.

**3. Posiciones incrementales durante la conversión.**
El conversor nunca recalcula cuánto texto lleva escrito: lo lleva contado. Los
espacios se colapsan al vuelo y el espacio final de línea se emite de forma
diferida, lo que garantiza que la posición registrada en cada marca coincide
exactamente con el texto definitivo. Esta es la diferencia entre un coste
lineal y uno cuadrático.

A eso se añaden dos cosas propias: la **caché en disco** (segundas aperturas en
0,13 s) y el uso de **lxml**, que analiza los 31 MB de XHTML del libro de
prueba en 0,14 s.

---

## Añadir un formato nuevo

1. Crea `src/formatos/mi_formato.py` con una clase que herede de
   `formatos.base.Analizador`, declare sus `extensiones` y devuelva un
   `nucleo.documento.Documento` desde `analizar()`.
2. Llama a `registrar(MiAnalizador())` al final del módulo.
3. Impórtalo en `src/main.py`, junto a `from formatos import epub`.

El resto de la aplicación —navegación, sonidos, búsqueda, marcadores,
diálogos— funciona sin ningún cambio, porque solo conoce el modelo
`Documento`.

---

## Accesibilidad: lo que se comprobó midiendo

El nombre que anuncia un lector de pantalla al llegar a un control se leyó
directamente de la API de accesibilidad de Windows, en vez de darlo por
supuesto. Eso destapó dos controles mudos y una trampa:

* `wx.SpinCtrl` no expone **ningún** nombre, ni con una etiqueta delante ni con
  `SetName`. Necesita un objeto `wx.Accessible` propio.
* `wx.ColourPickerCtrl` anunciaba «colourpicker». Se sustituyó por una lista de
  colores con nombre (`interfaz/colores.py`).
* **La trampa**: forzar el nombre de un contenedor se lo impone también a todos
  sus elementos, porque wxWidgets contesta con el mismo objeto para cada hijo.
  Un índice etiquetado así anunciaría «Contenido del libro» en cada capítulo.
  Por eso `interfaz/accesible.py` solo fuerza el nombre en controles sin
  elementos interiores.

Un `wx.ListCtrl` en modo informe muestra columnas, pero el teclado solo se
mueve de fila en fila: al bajar se lee la fila entera y no hay forma de volver
sobre una columna concreta. `interfaz/listas.py` le añade un **cursor de
columna** propio, que las flechas izquierda y derecha mueven sin tocar la
selección ni el foco; así el lector de pantalla no dice nada por su cuenta y no
hay doble lectura. La misma clase guarda el texto **íntegro** de cada celda,
porque Windows recorta a unos 511 caracteres el que se le pasa al control y
`GetItemText` no vale para leer en voz alta una nota larga.

Se recorrieron las trece pantallas de la aplicación comprobando que todos los
controles tuvieran nombre. Así se detectó que instalar dos veces el filtro de
mensajes sobre el mismo control dejaba un puntero colgando y el control se
quedaba mudo; ahora el filtro no se instala dos veces.

El **deslizador de volumen** anunciaba «70» —su propio valor— en lugar de para
qué servía. El culpable era el estilo `wx.SL_LABELS`: añade al deslizador unas
etiquetas con el valor, y Windows deduce el nombre del control del texto que
tiene justo delante, que pasaba a ser esa etiqueta. Sin ese estilo, y con su
texto estático delante, se anuncia bien:

| Construcción | Nombre que anuncia |
|---|---|
| Etiqueta previa, sin `SL_LABELS` | «Volumen de los sonidos, de 0 a 100» |
| Etiqueta previa, con `SL_LABELS` | «70» |
| Solo `name=`, sin etiqueta previa | ninguno |

El valor se muestra en un texto aparte, a la derecha del deslizador.

### El menú contextual del control de texto

Costó tres intentos porque hay **tres vías** distintas y ninguna se tapa sola.
La documentación de wxWidgets lo dice: *«wx.TextCtrl no entrega el evento
EVT_CONTEXT_MENU; en su lugar aparece el menú del sistema»*.

| Vía | Qué hace falta |
|---|---|
| Mensaje `WM_CONTEXTMENU` (Mayús+F10, botón derecho) | Filtrarlo en el procedimiento de ventana |
| Botón derecho del ratón | Atender `EVT_RIGHT_UP` (en Windows el menú solo se genera si nadie lo atendió) |
| **Tecla Aplicaciones** | Filtrar `WM_KEYDOWN`/`WM_KEYUP` con `VK_APPS` |

La tercera fue la que se resistía: el control abre su menú al recibir esa
tecla **sin enviar antes `WM_CONTEXTMENU`**, y la tecla ni siquiera llega al
sistema de eventos de wxPython. Se descubrió midiendo con una pulsación real
del teclado y leyendo el contenido del menú que aparecía (`Deshacer, Rehacer,
Cortar, Copiar…`, el menú nativo del control).

Está en `interfaz/ventanas_win32.py`, y se comprobaron las cinco formas de
pedirlo, con y sin libro abierto.

## Un formato nuevo es un módulo, no un parche

Casi todos los formatos acaban siendo lo mismo: una sucesión de trozos de
XHTML. Un EPUB los trae así; un DOCX, un ODT, un FB2 o un DAISY se convierten
con unas pocas reglas propias. A partir de ahí el trabajo —convertir cada trozo
a texto, recolocar las marcas, sumar desplazamientos— es idéntico, y **estaba
escrito solo dentro del analizador de EPUB**.

`formatos/ensamblador.py` lo tiene ahora una sola vez. Un analizador nuevo se
reduce a lo suyo: sacar los trozos de XHTML y los metadatos, y llamar a
`montar()`. Eso es lo que ha permitido pasar de un formato a diez sin repetir
doscientas líneas delicadas de aritmética de posiciones.

Dos decisiones concretas que se ganaron probando:

* **Word guarda el identificador del estilo sin acentos ni espacios**, así que
  «Título 2» acaba escrito `Ttulo2`. Sin contemplarlo, en un documento hecho en
  español ningún título se reconocería y el archivo entero sería un bloque
  plano. La prueba lo destapó.
* **Un PDF sin etiquetar no dice qué línea es un título.** Se deduce de su
  forma: línea corta, sola entre líneas en blanco y sin punto final. Es una
  heurística, y es lo que convierte un PDF cualquiera en algo recorrible con la
  tecla `H`. Cuando el PDF **sí** trae etiquetas no hace falta adivinar nada:
  véase la sección siguiente.

### Traducir el programa

Los textos viven en el código envueltos en `_()`, y de ahí salen a un catálogo
por idioma (`data/idiomas/<código>/LC_MESSAGES/visor.po`) que se compila a `.mo`,
que es lo que carga `gettext`.  El **español no se traduce**: es el original, y
por tanto la clave de cada entrada.

El **manual** va en la misma carpeta del idioma, en `docs/MANUAL_USUARIO.md`.
Está ahí y no suelto en `data` por una razón práctica: traducir la
documentación pasa a ser dejar un archivo en la carpeta que toca, sin tocar
código, sin registrar nada y sin compilar.  `rutas.ruta_manual()` busca el del
idioma activo, prueba con el idioma base si lo que hay puesto es una variante
regional —a quien tenga `pt_BR` le sirve el manual en portugués— y termina en
el español, que es el original.  Un idioma sin manual no deja a nadie sin
ayuda: F1 abre el español.

Cuando no existe ninguno, la ruta que se devuelve —y que sale en el aviso— es
**la del español**, no la del idioma del usuario: el aviso tiene que señalar la
carpeta donde de verdad hay que poner el archivo.

Las tres herramientas son `herramientas/textos.py` (extraer, crear un idioma y
compilar), `herramientas/traductor.py` (traducción automática) y
`herramientas/editor_idiomas.py` (la ventana con la que se trabaja, y que se
abre desde la opción **T** del menú de `VisorUniversal.bat`).

Del traductor automático hay tres cosas que costaron encontrar:

* **Lo que no se puede traducir hay que sacarlo del texto antes de mandarlo**:
  las variables (`%s`, `%d`), los saltos de línea, las rutas y —esto es propio
  de este programa, que está lleno de ellas— las **combinaciones de teclas**.
  Traducir «Control» por «Controllo» deja una instrucción que no lleva a ninguna
  parte.
* **La forma del sustituto importa.**  Con `XQV0VQX` el traductor se comía la
  frase entera alrededor del token; con `ZZQ0QZZ`, no.  Como eso no se puede
  garantizar por diseño, después se **comprueba** que el sustituto siga ahí: si
  falta, la entrada se deja sin traducir en lugar de guardar un texto al que le
  falta un `%d` que reventaría el programa en un idioma que quien lo escribió no
  habla.  Hay una prueba que lo vigila en los cuatro catálogos.
* **Los aceleradores de menú se reubican, no se conservan.**  El subrayado tiene
  que caer en una letra de la palabra **ya traducida**, y solo en palabras que
  tengan letras: en francés, «Color de la &letra:» acaba en «Couleur des
  &lettres :», donde la última «palabra» es un dos puntos suelto.

Y una de rendimiento: se mandan **cuarenta renglones por petición** en lugar de
uno.  Una petición por texto son cuatro segundos por entrada y casi seis horas
para tres idiomas; agrupando, tres minutos por idioma.

La plantilla `visor.pot` se rehace **al compilar** —tanto los catálogos como el
ejecutable—, de forma que la que se publica dentro del programa nunca va por
detrás de los textos que este tiene de verdad.

Y dentro del ejecutable van también los **`.po`**, no solo los `.mo`.  Estaban
fuera por ser «el original de trabajo», y era un error: con solo la plantilla,
quien quiera arreglar una frase mal traducida al italiano tiene que rehacer las
mil novecientas entradas desde cero, cuando lo que necesita es continuar sobre
lo ya hecho.  Son un cuarto de mega cada uno.  Un `LEEME.txt` en la carpeta
explica cuál es cuál, porque tres extensiones parecidas no se distinguen solas.

### La IA local: que se monte sola

Tener inteligencia artificial en el propio equipo es lo mejor que le puede
pasar a este programa —no sale nada del ordenador y no hay cuota—, y montarla
era justo lo que dejaba fuera a quien más falta le hace: buscar un servidor,
instalarlo, elegir un modelo, saber qué es un GGUF.

`nucleo/ia/ollama.py` lo hace por el usuario: descarga **Ollama portable** en
`data`, lo arranca, le da modelos y lo apaga al salir.  Tres decisiones de
aislamiento, y las tres importan:

* **Puerto propio (11436).**  El 11434 es el de Ollama de toda la vida y no se
  toca.  Y no basta con usar otro: antes de adoptar un servidor que conteste se
  comprueba que el proceso que escucha sea **exactamente nuestro ejecutable**.
  Adoptar uno ajeno sería usar sus modelos sin permiso; matarlo, peor.  Esa
  comprobación también iba por `wmic` y también se quedó muda con Windows 11:
  al no poder saber de quién era el proceso, el programa no reconocía **ni su
  propio servidor**.  Ahora se pregunta por PowerShell y, si eso fallara, por
  la API de Windows; una respuesta vacía sigue significando «no se sabe», y sin
  saberlo no se adopta ni se mata nada.
* **Almacén propio** (`data/ollama_modelos`), para no mezclar los modelos con
  los del usuario ni borrárselos.
* **Todo dentro de `data`**, para que el programa siga siendo portable: la IA
  se va con él en la memoria USB.

Del resto, lo que costó:

* **Las descargas reanudan.**  Es más de un giga de motor y hasta siete de
  modelo: quien tiene una conexión regular no puede empezar de cero cada vez.
  Se guarda un `.parte`, se pide con `Range` y se contempla el 416 —el trozo ya
  no sirve— reiniciando en lugar de dejar al usuario atascado.
* **El ZIP se extrae comprobando rutas.**  Un paquete bajado de internet que
  traiga `..\..\Windows` es un archivo ajeno escribiendo donde quiera.
* **Se instala a un lado y se cambia al final.**  Si algo falla a mitad, lo que
  había sigue funcionando.
* **Al parar se mata el árbol de procesos.**  Ollama lanza un ayudante por cada
  modelo cargado; matando solo al padre, esos ayudantes se quedan reteniendo la
  memoria de la tarjeta y el arranque siguiente falla por falta de sitio.
* **El progreso se traduce.**  Ollama informa con un flujo de líneas JSON donde
  pone `pulling manifest`; eso no le dice nada a nadie, así que se convierte en
  porcentaje y en una frase.  Y el porcentaje **se suma por capas**: cada
  línea de `/api/pull` habla de una capa —los pesos, el proyector de visión, la
  plantilla—, no del modelo, y cada una empieza a contar de cero.  Quedándose
  con la última línea, que es lo que se hacía, el porcentaje sube dentro de una
  capa, vuelve atrás al empezar la siguiente y se queda clavado en cero
  mientras una arranca: exactamente «no avanza nada».  Se anota lo que lleva
  cada capa por su `digest` y se suma.
* **Una descarga parada se dice.**  Si el porcentaje no se mueve en treinta
  segundos se añade cuánto lleva así.  Sin eso, una conexión cortada suena
  igual que una descarga lenta: la misma frase una y otra vez.  Y cuando el
  fallo es de red se explica en lugar de repetir la línea en inglés de Ollama,
  porque los modelos se bajan de un almacén distinto del servidor y ese salto
  es el que bloquean algunos antivirus y cortafuegos —todo lo demás funciona y
  solo la descarga se queda quieta.
* **Un `null` no lo ataja el valor por omisión.**  `datos.get("data", [])`
  devuelve la lista vacía cuando **falta** la clave, pero devuelve `None`
  cuando la clave está y vale `null`, y entonces recorrerla revienta.  Ollama
  contesta exactamente eso a `/v1/models` mientras no haya ningún modelo
  instalado —`{"object": "list", "data": null}`—, o sea justo al terminar de
  instalarlo, que es cuando más se mira.  En todo el código que lee JSON ajeno
  se usa `or []` y `or {}`, que sí cubre los dos casos.
* **Nada se pinta después de cerrar.**  El hilo de trabajo sigue vivo unos
  segundos tras cerrar el asistente —una descarga no se corta en el acto— y sus
  avisos llegaban a una barra ya destruida: quinientas veintiuna excepciones
  seguidas en el registro de una sola sesión.  Ahora se comprueba que el
  diálogo siga en pie antes de tocarlo, que es lo que el diálogo de progreso
  del resto del programa ya hacía.
* **Ver la tarjeta gráfica cuesta más de lo que parece.**  La primera versión
  preguntaba con `wmic` y se quedaba con el primer adaptador que saliera.  En un
  equipo con una RTX 3060 de doce gigas el asistente anunciaba «sin tarjeta
  gráfica dedicada», y por tres motivos a la vez, ninguno de los cuales daba
  error:

  * **`wmic` ya no viene con Windows 11.**  La orden no existe, la excepción se
    tragaba y la detección entera se quedaba a ciegas.  Ahora se lee el
    **registro** (`HardwareInformation.qwMemorySize`) y se contrasta con
    `nvidia-smi`; PowerShell y `Get-CimInstance` quedan de último recurso.
  * **Windows enumera los monitores virtuales como si fueran tarjetas.**  Quien
    tenga tres salen los tres antes que la de verdad, así que quedarse con el
    primero es quedarse con un monitor de mentira.  Se descartan por nombre.
  * **La memoria que da WMI es un entero de 32 bits** y se queda clavada en
    4 GB: una tarjeta de doce se ve como de cuatro.  La del registro es de 64 y
    dice la verdad.  Cuando no hay más remedio que usar WMI se devuelve **cero
    —desconocida— en lugar de la cifra falsa**, y una memoria desconocida ya no
    descarta la tarjeta: decide el motor, que sabe mirarlo mejor.

  De propina, los nombres vienen con símbolos de marca por medio («AMD
  Radeon(TM) Graphics»), y ese `(TM)` bastaba para no reconocer una integrada y
  tomarla por una tarjeta aparte.  El mismo fallo dejaba sin el complemento de
  AMD a quien tuviera una Radeon, porque esa comprobación también iba por
  `wmic` y respondía siempre que no.

`nucleo/ia/modelos_vision.py` es la lista de modelos, corta a propósito: siete
que caben en un ordenador normal, están en la biblioteca de Ollama y sirven
para lo que hace este programa.  Cada uno lleva escrito para qué es bueno y qué
memoria pide, porque «2B» no le dice nada a nadie y «funciona con 4 GB y tarda
medio minuto por imagen», sí.

`Ollama.importar_modelo` mete en el almacén un GGUF que ya esté en el disco.
Son tres pasos por archivo —firmarlo, copiarlo si no estaba, y crear el modelo—,
y el detalle que lo hace usable es que sean **dos** archivos: los pesos y el
proyector de visión.  Quien se baja un modelo multimodal por su cuenta acaba con
dos `.gguf` sueltos y sin manera de juntarlos; cuál es cuál lo reconoce el propio
Ollama por lo que el GGUF lleva escrito dentro, así que aquí basta con
entregárselos.

Lo que se cuidó:

* **La huella es del contenido**, no del nombre, así que un archivo que ya esté
  no se vuelve a copiar: importar el mismo modelo dos veces con nombres
  distintos no ocupa el doble.
* **Se comprueban las cuatro primeras letras** del archivo antes de copiar nada.
  Decirle a alguien que se equivocó de archivo cuesta un segundo al principio y
  diez minutos de copia si se dice al final.
* **El nombre se arregla en vez de rechazarlo.**  Ollama solo admite letras,
  números, puntos y guiones; «Qwen visión 3B», que es lo que uno escribiría, lo
  rechaza con un error que no explica nada.  Se pasa a `qwen-vision-3b`.
* **La barra se reparte por tamaño.**  El proyector suele ser diez veces más
  pequeño que los pesos: darle la mitad del recorrido dejaría la barra plantada
  en el 50 % durante casi toda la importación.
* **Se avisa si faltan los ojos.**  Importar sin proyector es legítimo —hay
  modelos de solo texto— pero en un lector de libros es media herramienta, así
  que se pregunta antes en vez de descubrirlo al pedir la primera descripción.

`interfaz/dialogos/asistente_ia.py` es el recorrido de cinco pantallas, hecho a
imagen del recorrido guiado.  La diferencia es que aquí los pasos **hacen
cosas** y esas cosas tardan: cada una va en un hilo aparte con su barra, se
cancela con Escape y avisa al terminar.

### Preguntar dos veces sobre lo mismo

`nucleo/ia/preguntas.Conversacion` guarda los turnos y arma cada envío.  Dos
decisiones:

* **El documento solo viaja en el primer turno.**  Es lo más largo con
  diferencia, y ya está dentro de la conversación que se manda entera; repetirlo
  multiplicaría el coste sin añadir nada.
* **Se poda por pares.**  Cortar por la mitad deja una respuesta sin su
  pregunta, y eso confunde al modelo más de lo que le ayuda.

En el servicio hay dos caminos según el proveedor: los que hablan el formato de
OpenAI reciben los turnos con sus papeles, y a los demás se les pasa la
conversación **escrita**.  Funciona igual de bien y evita cuatro
implementaciones distintas de lo mismo.

### Publicar una versión

El actualizador consulta un `version.json` y compara su número con el de
`src/version.py`.  La comparación es **numérica** (`(1, 2, 10) > (1, 2, 9)`),
porque como texto `"1.2.10" < "1.2.9"`, que es justo lo contrario de lo que hace
falta.

Ese `version.json` lo genera `herramientas/empaquetar.py` al compilar, con el
`sha256` del paquete y su firma.  El campo `notas` es lo que el programa enseña
como **«Novedades»** al ofrecer la actualización, dentro de un cuadro de texto
que se recorre con las flechas —y no de una etiqueta, que solo se puede oír de
una tirada—.

Esas notas **no se escriben en el JSON**: se escriben en `NOVEDADES.md`, en un
apartado `## <versión>`, y el empaquetador las copia.  El motivo es que el
`version.json` es un archivo *generado*, y lo que se escribe a mano en un
archivo generado se pierde en la compilación siguiente.  Si falta el apartado,
el empaquetador lo dice en voz alta en lugar de publicar una versión muda.

Un detalle que conviene saber: **la firma cubre solo `"<versión>:<sha256>"`**,
no las notas.  Eso permite corregir una errata en el texto sin volver a firmar
—ni a compilar—, y no debilita nada: lo que la firma protege es que el paquete
que se instala sea el que se publicó.

### Tres zonas, una sesión por pestaña

La ventana tenía un solo documento y lo guardaba en sus propios atributos:
`self.documento`, `self.marcadores`, `self.lector`…  Con pestañas eso deja de
valer, porque **cada documento tiene lo suyo** —incluida la posición de lectura,
que es lo que hace útiles las pestañas y lo que se pierde si el programa se
limita a cambiar el texto de la pantalla—.

La solución evita reescribir mil líneas: `interfaz/sesion.py` reúne todo lo de
un documento y la ventana convierte aquellos atributos en **propiedades** que
van a parar a la sesión activa.  El resto del programa no se ha enterado del
cambio, que era justo la idea.

`interfaz/pestanas.py` presenta la colección de dos maneras según el ajuste:
con `wx.Notebook` cuando las lengüetas se ven —control nativo, así que el lector
de pantalla anuncia «pestaña 2 de 4» y las flechas cambian de documento sin que
haya que programar nada— y con `wx.Simplebook` cuando no, que es el mismo
contenedor sin lengüetas.  Los dos son `wx.BookCtrlBase` y se manejan igual.
Cambiar de modo **no cierra nada**: los paneles se cambian de padre
(`Reparent`), porque recrearlos obligaría a volver a analizar los documentos y a
perder la posición de cada uno.

`interfaz/arbol.py` es la tercera zona.  Dos decisiones que se notan: las ramas
se llenan **al desplegarlas** —un libro puede tener catorce mil elementos de
lista y construirlos todos costaría más que analizarlo— y moverse por el árbol
**no** mueve la lectura, que se salta con Intro; si cada flecha arrastrara el
documento, mirar qué hay dentro sería imposible sin perder el sitio.

Las tres zonas se recorren con `F6` y `Mayús+F6`, y la lista de zonas se
construye cada vez con las que estén a la vista: con el árbol y las pestañas
apagados no hay más que una, y la tecla lo dice en lugar de quedarse muda.

### Qué trae cada documento para poder leerse

`nucleo/accesibilidad.py` mira el documento **ya convertido** —lo tiene todo en
sus marcas— y redacta una frase con lo que ha encontrado: encabezados, índice,
tablas, listas, imágenes descritas y sin describir, páginas e idioma.  Se hace
en `ensamblador.montar()`, que es por donde pasan todos los formatos, así que un
DOCX dice lo mismo que un PDF sin que cada analizador lo repita.  Cada uno puede
añadir delante lo suyo: el PDF, si está etiquetado y cuánto de su texto cubre la
estructura; el EPUB, los metadatos de accesibilidad que la norma pide declarar.

Para poder contar las imágenes sin describir hizo falta un dato que no había: el
conversor deja ahora el campo `nivel` de la marca a 1 cuando la imagen traía
texto alternativo o pie.  Sin eso habría que adivinarlo comparando el rótulo con
la palabra «Imagen», que es exactamente la clase de heurística que este programa
evita cuando el dato está disponible.

### DOCX y ODT: el etiquetado que ya traían

Los dos formatos llevaban dentro mucho más de lo que se estaba leyendo.  Ahora
se aprovecha:

* el **texto alternativo** de las imágenes (`wp:docPr/@descr` en DOCX,
  `svg:desc` en ODT), que es lo que sus respectivos comprobadores de
  accesibilidad piden rellenar y lo único que hace legible una imagen;
* la **fila de encabezados** de las tablas (`w:tblHeader`,
  `table:table-header-rows`), que se traduce a `<th scope="col">`;
* los **enlaces**, que en DOCX son un identificador que hay que buscar en
  `document.xml.rels` y que antes se perdían enteros;
* las **listas de verdad**: Word no tiene listas, tiene párrafos que dicen
  «pertenezco a la numeración 3, nivel 0».  Se agrupan los que van seguidos, se
  anidan por su nivel y se mira en `numbering.xml` si llevan viñeta o número;
  antes, veinte viñetas seguidas eran veinte listas de un punto y la tecla `L`
  no servía para nada;
* las **notas al pie** del ODT, cuya llamada se queda en su sitio y cuyo texto
  se aparta detrás del párrafo, que es para lo que existe una nota al pie.

### PDF etiquetado: leer un PDF como se lee un EPUB

Desde 2012 la norma **PDF/UA** (ISO 14289-1) exige que un PDF accesible lleve un
**árbol de estructura** (`StructTreeRoot`) paralelo al dibujo de la página, con
el mismo vocabulario que el HTML: `H1`..`H6`, `P`, `L`/`LI`/`Lbl`/`LBody`,
`Table`/`THead`/`TR`/`TH`/`TD` con `Scope` y `Summary`, `BlockQuote`, `Note`,
`Reference`, `Link`, `Figure` con su `Alt`, `TOC`/`TOCI` y el `Lang` de cada
fragmento. `formatos/pdf_etiquetado.py` lo lee y **lo traduce a XHTML**, que se
le pasa al conversor de siempre. Un analizador nuevo de doscientas líneas
convierte así el peor formato del programa en uno que se navega igual que un
EPUB: con `H`, `T`, `L`, `Q`, `I`, `O`, con `F7` y con `Ctrl+H`.

Tres cosas que costaron encontrar:

* **El árbol no contiene el texto**: contiene números de contenido marcado
  (*MCID*). El texto está en la página, pegado a esos números. Hay que recorrer
  los objetos de la página (`FPDFPageObj_GetMarkedContentID` y
  `FPDFTextObj_GetText`) para montar el diccionario MCID → texto, y solo
  entonces se puede recorrer el árbol. De propina, todo lo que el PDF marca como
  **artefacto** —encabezados y pies, números de página, filetes— se queda fuera
  del árbol, y con eso un informe de doscientas páginas se libra de doscientas
  repeticiones de su propio título.
* **El árbol no dice a dónde llevan los enlaces**: eso vive en las anotaciones
  de la página, que son otra lista. El puente entre las dos es la **posición**,
  así que se pregunta por el punto que ocupa el texto del enlace
  (`FPDFLink_GetLinkAtPoint`). Los destinos internos se traducen a `#pagina-N`,
  que es el ancla que el analizador pone al principio de cada página; con eso el
  índice de un informe salta de verdad al capítulo.
* **El idioma se hereda**: dentro del árbol solo llevan `Lang` los trozos que
  *cambian* de idioma, así que contarlos daría el resultado contrario al bueno
  —un informe en español con cuatro citas en portugués saldría portugués—. El
  idioma del documento es el del catálogo (`FPDFCatalog_GetLanguage`), y en el
  XHTML solo se escribe el `lang` donde de verdad cambia.

No basta con que exista el árbol: hay PDF con un etiquetado de adorno que deja
fuera medio documento. Antes de fiarse se mira una docena de páginas repartidas
y se compara **cuánto del texto de la página cae dentro del árbol**; por debajo
del 55 % se lee el PDF como si no estuviera etiquetado, que es peor de navegar
pero no pierde nada. El resultado de esa comprobación se guarda en los
metadatos y se ve en `Ctrl+D`.

### PDF sin etiquetar: deducir la estructura midiendo la página

El PDF etiquetado es la minoría. El caso normal es el PDF que solo dice dónde
pintar cada letra, y ahí la estructura hay que **deducirla**. Hasta la 1.3.0 eso
se hacía mirando la forma del texto ya aplanado —línea corta, suelta y sin punto
final se daba por título—, y fallaba en el caso más común: PDFium devuelve los
renglones seguidos, sin línea en blanco entre el título y el párrafo, así que el
título ni siquiera se distinguía como bloque. Medido sobre un manual de 498
páginas: **cero encabezados, cero tablas, cero enlaces, cero listas**.

Lo que faltaba no era una heurística mejor, era **el dato**. Un título no se
reconoce porque sea corto: se reconoce porque está escrito más grande. El tamaño
de letra está en el archivo, pero PDFium no lo expone por palabra; pdfminer sí,
a través de pdfplumber. Con eso, `formatos/pdf_geometria.py` deduce encabezados,
listas, tablas y columnas. El mismo manual, después: **2178 encabezados, 106
tablas, 625 enlaces y 622 listas**.

Cuatro decisiones que costaron encontrar:

* **El tamaño del cuerpo es del documento, no de la página.** Una portada tiene
  una sola línea, enorme, y comparada consigo misma no destaca. Se mide una
  muestra de 24 páginas repartidas por todo el documento y cada página se juzga
  contra esa referencia.
* **El nivel sale de una escala, no de un umbral.** Puntuar cada título por
  cuánto excede al cuerpo produce jerarquías con huecos: 24, 18 y 14 sobre un
  cuerpo de 12 daban `h1`, `h2` y `h4` porque 14 y 18 caen en tramos distintos, y
  saltarse un nivel rompe el árbol del documento y es un fallo de la norma
  (ISO 14289-1, 7.4). En su lugar se recogen **los tamaños que este documento usa
  para titular**, se ordenan de mayor a menor y el sitio que ocupa cada uno *es*
  su nivel. Sin huecos, midan lo que midan.
* **Dos columnas de texto y una tabla sin líneas se parecen mucho.** Las dos son
  franjas verticales con sus renglones a la misma altura, y `disposicion.py` —que
  está pensado para el OCR de un folleto— reconoce las dos como rejilla. La
  diferencia está en **cuántas palabras lleva cada renglón**: una columna de
  texto son frases partidas, con media docena de palabras; una celda lleva un
  dato. Esa medida no depende del tamaño de la página y separa los dos casos
  limpiamente. Además, más de dos pasillos verticales no es una maquetación: es
  una tabla, y entonces no se parte nada.
* **Los enlaces no son texto**, son cajas dibujadas encima de la página. Se
  enumeran con `FPDFLink_Enumerate`, se traduce su destino igual que en el camino
  etiquetado y se envuelven las palabras cuyo **centro** cae dentro de la caja
  —el centro y no la caja entera, porque los rectángulos de enlace se quedan
  cortos por un par de puntos y exigir contención dejaría fuera la primera y la
  última palabra de casi todos.

### Lo que un PDF trae además del texto

Un PDF no es solo letras. La norma PDF/UA define una treintena de tipos de
elemento, y las anotaciones de una página son otra lista aparte. Sin etiquetas,
cada uno hay que encontrarlo por su cuenta:

* **Figuras.** Hay dos clases y no se parecen. Una fotografía es una imagen
  incrustada y aparece como tal. Un **gráfico de un informe no es ninguna
  imagen**: son decenas de líneas, rellenos y rótulos dibujados uno a uno, y se
  reconoce porque esos trazos se agrupan en una zona de la página y son muchos.
  Se emite la misma referencia `pdf-figura:página:x0,y0,x1,y1` que produce el
  camino etiquetado, y por eso todo lo que ya existía funciona sin tocarlo:
  verla con `Ctrl+I`, describirla con IA y que la descripción se guarde y vuelva
  con el documento, igual que en un EPUB. Lo que se rasteriza y se le manda a la
  IA es el trozo de página, no un archivo: es lo único que funciona con un
  diagrama.

  Dos decisiones aquí. La primera: **no se quita el texto que cae dentro de una
  figura**, al contrario que en el camino etiquetado. Allí el árbol dice con
  certeza qué pertenece a la figura; aquí es una deducción, y equivocarse
  borrando texto es mucho peor que dejar los rótulos de un gráfico leyéndose
  detrás de él —que además dicen bastante de lo que el gráfico enseña—. La
  segunda: un pie que solo numera la figura («Figura 7-26.») **no cuenta como
  descripción**. Se escribe como pie, pero el `alt` se deja vacío, porque darlo
  por bueno dejaría esa figura fuera del alcance de la IA para siempre.

* **Notas al pie.** Se piden tres condiciones a la vez, porque cada una por
  separado se equivoca: abajo del todo (ahí está el pie de página), en letra
  menor que el cuerpo (ahí están los créditos de una figura) y empezando por un
  número o un asterisco (ahí empieza cualquier lista numerada). La llamada
  volada se reconoce por ser un número más pequeño que su renglón, y se marca
  como `noteref` para que la orden de notas salte a ella.

* **Citas en bloque.** Por su sangría, y con dos guardas que costaron encontrar.
  La sangría se mide contra el margen de **su columna**, no contra el del
  documento: en un texto a dos columnas, la de la derecha empieza decenas de
  puntos más allá y la columna entera pasaba por cita. Y el bloque tiene que ser
  **prosa**: una columna de cifras de una tabla también empieza muy a la derecha,
  y sin esa condición un documento con datos salía con decenas de citas.

* **Negrita y cursiva.** Están en el nombre de la fuente de cada palabra. Solo
  se marcan cuando distinguen un trozo del resto del renglón: un título entero
  en negrita no lleva negrita dentro, porque entonces la marca no señalaría nada.

* **Filetes.** Se descartan los que están a la misma altura en casi todas las
  páginas —la raya de la cabecera y la del pie, que son mobiliario— y los que van
  muy juntos, que son la rejilla de una tabla. Sin esas dos guardas, un manual de
  498 páginas producía 806 separadores; con ellas, 153, que son los de verdad.

* **Comentarios.** Las notas adhesivas, los subrayados con comentario y las
  correcciones que alguien dejó en el PDF no forman parte del texto de la
  página: son anotaciones, y se perdían enteras. Se recogen y se emiten como
  notas, que es lo que son.

El camino solo se recorre cuando **no** hay estructura etiquetada utilizable:
cuando la hay, medir otra vez costaría medio segundo por página para llegar a una
conclusión peor.

### Reparar, diagnosticar y auditar

Tres módulos más pequeños, cada uno para un problema que dejaba documentos sin
leer:

* **`pdf_diagnostico.py`** mira el archivo antes de abrirlo, con pypdf, que es lo
  único que expone el interior del PDF. Lo caro se hace **sobre una muestra**:
  recorrer las 756 páginas de la norma ISO con pypdf para contar sus fuentes
  costaba 10 segundos; muestreando doce, 0,7. De aquí sale también la distinción
  entre las dos contraseñas de un PDF —la de propietario, que solo prohíbe
  imprimir y **se salta sola probando la contraseña vacía**, y la de usuario, que
  se le pide a quien abre— y la clasificación de cada página, que ya no cuenta
  caracteres sino que mira **dónde caen**: una página escaneada casi siempre trae
  su número impreso en texto de verdad, y contando caracteres pasaba por «página
  con texto» y se quedaba sin reconocer.
* **`pdf_reparacion.py`** reconstruye el índice de referencias cruzadas de un PDF
  roto **sin instalar nada**: los objetos no se han movido, así que se recorre el
  archivo anotando cada `N 0 obj` y se escribe una tabla nueva al final de una
  copia, sin tocar un byte de los originales. Importa porque PDFium reconstruye
  el índice por su cuenta y abre el archivo, pero pdfminer es estricto y se
  niega: en un PDF con el índice roto se leía el texto y se perdían los
  encabezados y las tablas. Por eso la reparación se intenta justo donde hace
  falta —al no poder medir— y no de entrada. Y la copia solo se acepta si **abre
  y no ha perdido páginas**: una reconstrucción incompleta produce un archivo
  válido con medio libro dentro, que es un desastre silencioso.
* **`pdf_auditoria.py`** comprueba el subconjunto de PDF/UA que una máquina puede
  comprobar sola, citando la cláusula de la norma, y **dice siempre que solo hace
  ese subconjunto**: un informe automático que dijera «documento accesible» sería
  falso y dejaría tranquilo a quien publica un documento que no hay quien lea. No
  vuelve a abrir nada: audita lo que el análisis ya reunió.

### Correcciones: enmendar una deducción sin tocar el archivo

Todo lo anterior son deducciones y a veces se equivocan.
`nucleo/correcciones.py` permite decirlo una vez (`Ctrl+Alt+C`) y que se aplique
siempre. Tres decisiones:

* **El archivo original no se toca nunca.** Un PDF puede ser un documento oficial
  o estar firmado; modificarlo para arreglar cómo se lee sería desproporcionado.
  Las correcciones viven en `data/correcciones`.
* **Se atan al contenido, no a la ruta.** La clave es el SHA-256 del archivo: un
  libro que se mueve o se renombra conserva las suyas, y un archivo distinto no
  las hereda. Atarlas a la ruta daba las dos respuestas equivocadas.
* **Se identifican por el texto y la página, no por la posición.** Guardar «el
  carácter 14.320 es un encabezado» sería frágil hasta lo inútil: basta con que
  mejore el reconocimiento o cambie una opción para que todas las posiciones se
  desplacen. Lo que no se mueve es lo que dice la línea. Un texto que ya no
  aparece simplemente no corrige nada, que es el fallo inofensivo.

Se aplican sobre el XHTML de cada página, que es el único sitio por el que pasan
los tres caminos —etiquetas, geometría y OCR—, así que una corrección hecha sobre
un documento reconocido sigue valiendo si mañana mejora el reconocedor.

### Una palabra no se parte porque cambie el tamaño de su letra

Un fallo que reportaron varios lectores: en documentos compuestos en versalitas
—habituales en textos jurídicos y académicos— el texto salía «I NSTITUTO DE
E STUDIOS». La causa resultó ser doble, y las dos veces la misma idea de fondo:
**una medida absoluta donde hacía falta una relativa**.

* En el camino etiquetado, `_separacion` metía un espacio entre dos trozos
  cuando el hueco pasaba de 1,5 puntos. En un título grande, la separación
  normal entre letras ya pasa de eso.  Ahora el umbral es proporcional al cuerpo
  de la letra, que es como se mide un espacio de verdad (alrededor de un tercio).
* En el camino geométrico era peor y era propio: pedirle a pdfplumber el tamaño
  de letra con `extra_attrs` hace que **parta una palabra en cuanto cambia
  cualquier atributo pedido**, y en versalitas la inicial va dos puntos más
  grande. Se le piden las palabras sin atributos —que es como las parte bien— y
  el estilo se averigua después mirando qué letras caen dentro de cada palabra
  (`_letras_por_renglon`). De paso mejora la detección de títulos, que estaba
  midiendo palabras partidas.

### El ancho del renglón se cambia sin tocar el texto

Los renglones muy largos son incómodos de seguir, y en una ventana maximizada
salen del doble de largos que en papel. Lo evidente sería insertar saltos de
línea en el texto, y sería un error: **todas las posiciones del libro se
moverían**, y con ellas los marcadores, las notas, los resaltados y la posición
de lectura, que son datos del usuario.

Lo que se estrecha es el **control**, con márgenes laterales calculados a partir
del ancho pedido en caracteres y del ancho real de un carácter con la fuente
puesta (`PanelLectura.ajustar_ancho`). El ajuste de línea lo sigue haciendo
Windows sobre el mismo texto de siempre, así que no cambia ni una posición.

### Un ajuste se aplica, no se invierte

La casilla del ajuste de línea no se quedaba puesta, y el motivo es una lección
que vale para cualquier preferencia: `alternar_ajuste_de_linea` hacía **dos
cosas** —invertir el ajuste guardado y rehacer el control— y quien aplicaba las
preferencias lo llamaba **una vez por pestaña abierta**. Con un documento
delante, el ajuste se invertía dos veces (una al guardarlo en el diálogo, otra
al aplicarlo) y volvía a como estaba.

Ahora están separadas: `alternar_ajuste_de_linea` decide, y
`aplicar_ajuste_de_linea` solo obedece a lo que ya está decidido. Aplicar algo
ya aplicado tiene que ser inofensivo, y hay una prueba que lo comprueba.

### La caché no puede firmar lo que no sabe

La clave de la caché mezcla la ruta del archivo, su fecha, su tamaño, la versión
del formato y la **firma de las opciones de análisis**. Mientras todo eso siga
igual, lo guardado vale: es imposible mostrar contenido desfasado.

Imposible **de lo que la firma abarca**, que no es todo. Los ajustes del
reconocimiento de texto —con qué motor, con qué idiomas, cuántas páginas como
mucho— no viajan en `OpcionesAnalisis`: se le ponen al analizador de PDF justo
antes de abrir, porque salen de la configuración y del servicio de IA que esté
montado en ese momento. Cambiarlos no cambia la firma, así que un PDF escaneado
que se abrió con el reconocimiento apagado se seguía abriendo vacío para
siempre, y la única salida era borrar sus datos guardados —que se lleva por
delante los marcadores y las notas—.

Meterlos en la firma habría sido la solución elegante y es la equivocada: son
trece ajustes, la mayoría afinan el resultado sin cambiarlo de arriba abajo, y
tocar cualquiera invalidaría de golpe la caché de la biblioteca entera. Es el
mismo motivo por el que `estructura_pdf` solo se añade a la firma **cuando está
apagado**: las firmas de lo que no es un PDF tienen que seguir siendo las de
siempre.

Así que la salida es la contraria: dejar que el usuario diga «este no». `F5`
—`al_volver_a_analizar`— abre el documento con `releer=True`, que se salta la
lectura de la caché y guarda encima el resultado nuevo. Lo anotado sobre el
documento vive aparte, en `documentos.json`, y no se toca.

Al hacerlo salió un fallo viejo de al lado: al cambiar una opción que obliga a
reconvertir, la ventana ofrecía volver a abrir el libro y llamaba a
`abrir_libro(ruta)` sin más. Como el documento ya estaba abierto,
`_ir_a_lo_ya_abierto` lo cazaba, saltaba a su pestaña y contestaba «ya estaba
abierto» sin convertir nada. Ahora esa llamada lleva `releer=True` y
`en_pestana_nueva=False`, que es lo que quería decir desde el principio.

### Una nota es una nota aunque el libro no lo diga

La norma EPUB 3 tiene `epub:type="noteref"` para marcar la llamada de una nota,
y las recomendaciones de accesibilidad de la web tienen `role="doc-noteref"`.
Casi ningún libro real usa ninguno de los dos. Lo que hay en las bibliotecas es
esto:

```html
<a href="../Text/notas.xhtml#nt465" id="rf465"><sup>[465]</sup></a>
```

Un enlace corriente. Reconocer solo lo declarado dejaba el volumen 2 de los
*Discursos* de Isócrates —1.049 enlaces, 515 de ellos llamadas de nota— con
**cero notas**: la tecla `O` no encontraba ninguna y `K` recorría las 515
llamadas revueltas con las 515 vueltas al texto y el índice.

Así que además de lo declarado se mira **la forma**, y se piden tres cosas a la
vez porque cada una por separado se equivoca:

* Que **apunte dentro del libro**, a un sitio concreto. Una llamada lleva a su
  nota, no a una página web.
* Que su texto sea **solo un número o un signo de nota**. Los romanos quedan
  fuera: un «IV» suele ser un capítulo.
* Que vaya **entre corchetes o en superíndice**. Sin esto, el índice onomástico
  —donde cada número de página es un enlace— se llena de notas que no lo son.

Los paréntesis a secas **no** cuentan, y eso lo enseñó un libro de verdad: en un
texto técnico, «la ecuación (6)» con el `(6)` enlazado a la ecuación es una
referencia cruzada, y los paréntesis son la forma normal de numerar ecuaciones.
Con ese caso dentro aparecían dieciséis notas inexistentes en un manual de
curvas de Bézier. Entre paréntesis **y** en superíndice, sí es una llamada.

### Lo que se oye en la lectura continua es el texto, y solo el texto

Un lector reportó que las llamadas de nota «no suenan en la lectura continua,
NVDA más A». No es un fallo que se pueda arreglar: los sonidos del programa se
disparan al **moverse el cursor**, y en la lectura continua el lector de
pantalla recorre el texto por su cuenta sin mover el cursor del control. No hay
nada a lo que engancharse.

Lo único que se oye ahí es **el texto**, así que si hay que distinguir algo en
lectura continua, tiene que estar en el texto. De ahí
`marcar_llamadas_de_nota`: con la opción puesta, la llamada se escribe
`[nota 12]` en lugar de `[12]`. Es exactamente la misma idea que el
`[Imagen: ...]` que el programa ya escribe donde hay una imagen: lo que no es
texto, o lo que es texto pero no se distingue de otro texto, se dice.

Cambia el texto del libro, así que entra en la firma de las opciones y obliga a
volver a analizarlo; y viene apagada, porque en un libro de quinientas notas son
quinientas palabras más.

### El renglón es la unidad de la lectura continua, así que se hace la frase

De la misma observación sale el otro problema, y este sí tiene arreglo. Al
**parar** la lectura continua, el lector de pantalla deja el cursor al principio
del **renglón** que estaba sonando, para que se pueda seguir a mano desde ahí.
Sin ajuste de línea, un renglón del control es un párrafo entero del libro: se
acaban de oír veinte líneas y el cursor aparece arriba del todo, con las veinte
por delante otra vez. Con el ajuste de línea puesto ya no pasa —el renglón es
una línea visual— pero entonces el texto se lee a trozos que no coinciden con
ninguna unidad del idioma.

La respuesta no es pelearse con el lector de pantalla, sino **darle la unidad
que queremos que use**: si el renglón es la frase, al parar el cursor se queda
en la frase. De ahí `renglon_por_frase` y `segmentador.partir_en_renglones`.

Lo que hace que esto sea barato en vez de peligroso es una decisión de una
línea: **se cambia un espacio por un salto de línea, no se inserta nada**. Un
espacio y un salto ocupan lo mismo, así que el texto que ve el control mide
exactamente lo que el del libro y `PanelLectura` sigue traduciendo posiciones
con el mapa de siempre. Ningún marcador, ninguna nota, ningún resaltado y
ninguna posición de lectura se mueve, y por eso la opción se puede encender y
apagar con un libro abierto sin volver a convertirlo. Hay una prueba que
compara el texto partido con el original carácter a carácter, porque toda la
opción se sostiene sobre eso.

Los cortes son los mismos que usaría la voz, con dos matices: los dos puntos y
el punto y coma **no** cortan —para decir dan una pausa, pero como renglón
trocean una enumeración en diez renglones de tres palabras— y un párrafo sin
puntuación se parte igualmente por una coma o una raya, porque poesía, listas y
textos antiguos son justo donde el problema era peor. La búsqueda de finales se
hace con una expresión regular y no carácter a carácter: aquí se parten cientos
de miles de caracteres cada vez que se carga un tramo, y así cuesta 76 ms por
cada 2,8 millones.

Como el control enseña un salto donde el libro tiene un espacio, lo que se copia
y lo que se cita **no puede salir del control**: `texto_seleccionado()` devuelve
el texto del documento entre las dos posiciones de la selección, y `copiar()`
escribe eso en el portapapeles.

### La negrita no se aplica en el párrafo que se está leyendo

Un lector reportó que, con el ajuste de línea puesto, al recorrer con las
flechas el lector de pantalla repetía cada cierto trecho algo ya leído, o se
saltaba un trozo. No era el ajuste de línea ni la voz: era **la negrita y la
cursiva**.

El formato se aplica a medida que se avanza (`_formatear_alrededor`), porque
aplicarlo a un libro entero cuesta segundos. Y una letra en negrita ocupa más
ancho que la normal, así que dar estilo a un párrafo **cambia por dónde se parte
en renglones**. Si eso ocurre en el párrafo donde está el cursor, los renglones
dejan de estar donde estaban justo debajo de él: la flecha abajo baja un
renglón, pero ya no es el siguiente. Sin ajuste de línea no se nota, porque no
hay renglones que mover, y de ahí que pareciera un fallo del ajuste.

Dos cambios lo cierran, y el primero es el que importa:

* **Leyendo no se toca el estilo del párrafo donde está el cursor.** Los
  renglones de un párrafo se calculan por su cuenta, así que retocar los de al
  lado no descoloca nada. El tramo formateado solo se amplía desde el final de
  ese párrafo hacia delante y desde su principio hacia atrás. Se formatea el
  párrafo entero, con el cursor dentro, únicamente cuando se **llega de un
  salto** (`ir_a`, con `tras_salto`): ahí el lector de pantalla va a leer la
  línea de nuevo de todas formas.
* **Y se espera a que el cursor pare.** Media segundo (`RETARDO_FORMATO`), y
  cada movimiento cancela la espera anterior, de modo que recorrer un capítulo
  entero con las flechas no aplica formato ni una sola vez: se aplica al parar.

### Un pitido por línea, y por qué eso hacía falta arreglarlo

Al mover el cursor se avisa de lo que hay en la línea, y suena **un solo
sonido**: un acorde de pitidos no dice nada, y en un libro anotado casi todas
las líneas llevan dos o tres elementos. Elegir cuál suena es lo que hace
`ORDEN_DE_INTERES` (en `nucleo/marcas.py`).

Un lector reportó que el pitido de los enlaces «a veces suena y a veces no», y
que el programa no le servía para distinguir el número de una nota del número
del pasaje en unos discursos clásicos. Eran **dos** cosas, y las dos salían de
esa lista:

* **La llamada de nota no estaba en ella.** Una llamada de nota *es* un enlace
  —el conversor la marca como las dos cosas, para que se siga con `Intro` como
  cualquier enlace y a la vez se pueda saltar de nota en nota—, así que al no
  estar la llamada ganaba el enlace y las dos hacían el mismo pitido. Puesta
  por delante, cada una suena distinto.
* **Un solo sonido por línea deja cosas sin señalar.** En una línea con un salto
  de página y una llamada de nota, suena el salto y la nota se calla. Eso no se
  arregla reordenando —siempre habrá una que pierda— sino **cambiando de
  canal**: la voz sí puede enumerar. De ahí `avisar_elementos`, con cuatro
  valores (`sonido`, `voz`, `ambos`, `ninguno`), y `marcas.nombrar()`, que
  nombra hasta tres elementos en el mismo orden que usa el sonido.

La lista vive en `marcas.py` y no en el gestor de sonidos porque no es una
decisión sobre los sonidos, sino sobre los elementos: cuáles merece la pena
señalar y cuál dice más. `gestor.PRIORIDAD` **es** esa misma tupla, no una
copia, para que las dos formas de avisar no puedan acabar diciendo cosas
distintas.

Lo que no está en la lista es tan deliberado como lo que está: la negrita, la
cursiva, el subrayado y los cambios de idioma quedan fuera porque aparecen en
casi cada línea, y avisar de ellos convertiría el aviso en un ruido continuo que
habría que apagar —llevándose por delante el de los elementos que sí importan—.

### Resaltados: un marcador que señala un pasaje

Un resaltado no necesitó estructura propia. `Marcador` ya guardaba `inicio`,
`fin` y `fragmento`, así que un resaltado es un marcador con un pasaje dentro y
una bandera. Con eso hereda gratis el guardado por documento, la exportación, la
navegación y el borrado, y el archivo de quien no use resaltados no cambia: la
bandera solo se escribe cuando es cierta.

Lo que sí es propio es su **lista aparte**: un marcador señala un punto al que
volver y un resaltado un pasaje que conservar, y son dos formas de trabajar
distintas —el marcador se pone leyendo, el resaltado se repasa después—.
Mezclarlos obligaría a filtrar cada vez.

La exportación (`nucleo/resaltados.py`) sale a **texto plano, Markdown y HTML**,
y siempre con la página de cada pasaje: un resaltado sin referencia no se puede
volver a encontrar en el original, y volver al original —para comprobar, para
citar, para leer lo que había alrededor— es la mitad de para lo que se resalta.
En Markdown cada pasaje va como **cita** y no como párrafo porque eso es lo que
es: palabras de otro documento, y al pegarlas en una libreta de notas tiene que
verse de un vistazo qué es cita y qué es cosecha propia.

El módulo trabaja sobre una clase `Pasaje` propia y no sobre los marcadores: un
marcador guarda posiciones, que solo significan algo con el documento delante, y
aquí hace falta lo contrario, algo que se pueda escribir en un archivo y siga
entendiéndose sin el programa. Por lo mismo se escribe el fragmento que se
guardó al resaltar y no lo que diga hoy el documento, así el archivo sale bien
aunque el libro se haya vuelto a analizar con otras opciones.

### PDF y OCR

`pypdfium2` (el motor PDF de Chrome) hace las dos cosas que hacen falta —sacar
el texto y rasterizar la página— sin ningún programa externo, y con licencia
permisiva; PyMuPDF es más rápido pero es AGPL, lo que obligaría a cambiar la
licencia del programa.

Hay **tres motores** (`formatos/ocr.py`) y ninguno sobra, porque fallan en
sitios distintos: **Tesseract** conserva la estructura y no sale del ordenador,
la **IA** lee mejor la letra difícil pero manda la página a un servidor y gasta
cuota, y el **de Windows** ya está instalado y es tres veces más rápido.
`ocr.MODOS` combina los tres y el usuario elige en Opciones; cuando el modo
elegido no puede usarse, `motivo_sin_ocr()` explica qué hacer **según ese
modo**, porque de nada sirve decirle que configure la IA a quien ha pedido
precisamente que no se use.

Tesseract va **portable**, en `data/tesseract` (`nucleo/tesseract.py`). Pedirle
a alguien que instale un programa aparte para poder leer un PDF es pedirle
demasiado, y más a quien no ve la pantalla y tiene que pelearse con un
instalador ajeno. Lo prepara `herramientas/tesseract_portable.py`, que reúne el
ejecutable, sus bibliotecas y —esto es fácil de olvidar— la carpeta
`tessdata/configs`: sin ella, Tesseract no sabe producir el formato TSV, se
queja de que no puede abrir un archivo llamado «tsv» y no escribe ninguna
salida. Los idiomas se añaden y se quitan desde el propio programa,
descargándolos del repositorio oficial.

### Preparar la imagen

`formatos/imagen.py` pasa la página a gris y le sube el contraste antes de
dársela al motor, y resultó ser **lo que más mejora el resultado** de todo lo
que se probó: sobre un folleto en color, los productos leídos con su precio
pasaron de 7 a 10 sobre 14 y la basura de 31 líneas a 7. Por encima de cambiar
el modo de segmentación, el motor interno o la resolución, que apenas movieron
la aguja.

Funciona porque al pasar a gris, un fondo saturado y una letra clara quedan a
distancias de luminosidad manejables, y el contraste separa lo que queda.
Binarizar del todo se probó y sale peor: rompe la letra fina.

Todos estos ajustes están en Opciones y no por afán de configurabilidad: el
documento perfecto para un ajuste es el peor para otro, y un escaneado en blanco
y negro de un libro antiguo sale mejor sin tocarle nada.

### La doble pasada

Preparar bien la imagen tiene un techo, y en un folleto en color se alcanza
pronto: los precios sobre un círculo rojo se pierden hagas lo que hagas con el
contraste. Lo que rompe ese techo es **leer la página dos veces** decidiendo de
dos formas distintas qué es tinta y qué es fondo —el umbral global de siempre y
Sauvola, que lo calcula por zonas— y juntar lo leído. Como no fallan en los
mismos sitios, cada una recupera lo que la otra se dejó: de 15 productos leídos
con su precio a 19, de 23.

La fusión (`disposicion.fusionar`) es **por sitio, no por texto**: de la segunda
pasada se añade solo lo que cae donde la primera no encontró nada. Así no se
duplica ni una palabra y no hay que decidir cuál de dos lecturas distintas de la
misma palabra es la buena.

Dos cosas se decidieron midiendo, y las dos salieron al revés de lo esperado:

- **El orden de las pasadas importa, y no es «la que más saque primero».** Se
  ordenaba por número de palabras, lo que parecía razonable y era justo lo
  contrario: la pasada con Sauvola reconoce más cosas porque también lee los
  adornos, salía elegida como principal y su ruido entraba sin pasar ningún
  filtro. Con la de umbral global de primera y Sauvola de relleno: los mismos
  19 aciertos con 2 líneas de basura en vez de 5.
- **A la pasada de relleno se le exige más.** Lo que aporta de verdad son
  cifras —un precio siempre las lleva—, así que las palabras con dígitos entran
  siempre y las demás tienen que parecer palabras: cuatro letras, con vocal y
  sin mayúsculas por dentro. Sin eso entraban «bed», «bon» y «ÉS», que son
  trozos de icono que el motor lee con toda la confianza del mundo.

### El orden de lectura

`formatos/disposicion.py` es lo que convierte un montón de palabras con
coordenadas en texto que se puede leer. Es la mitad del trabajo que no se ve:

Un folleto con nueve productos en rejilla, leído renglón a renglón, sale
«Sandía Melocotón Pitaya 0,90 3,35 2,15». Los nombres por un lado y los precios
por otro. No es un fallo de reconocimiento —las letras están todas bien— y es
justo lo que deja el documento inservible para quien no puede mirar la página y
reconstruir mentalmente qué va con qué.

Se resuelve con el **corte recursivo en X e Y**, el clásico *XY-cut*: se busca
el hueco blanco más ancho que parta la región, se corta por ahí y se repite en
cada mitad. Cortar por un hueco vertical da las columnas; por uno horizontal,
las bandas. Recorrer el resultado en ese orden **es** el orden de lectura.

Dos detalles que costaron encontrar:

- **El corte se hace sobre las palabras, no sobre renglones ya montados.** Si
  primero se agrupan las palabras en líneas por su altura, las tres fichas de
  una fila pasan a ser un único renglón que cruza la página, y a partir de ahí
  ya no hay hueco vertical que encontrar. Cortando antes, las columnas salen
  solas.
- **Una tabla también tiene columnas separadas por huecos**, y cortar por ellas
  la volvería ilegible: los encabezados por un lado y los números por otro. Por
  eso, antes de cortar, `_es_rejilla()` comprueba si todas las columnas tienen
  el mismo número de filas **y a las mismas alturas**. Si lo son, la región se
  deja entera y se escribe como `<table>`. Esa condición es lo que distingue
  una tabla de verdad de un folleto con fichas, donde cada una lleva el texto
  que lleva y las alturas no coinciden.
- **Esa decisión se toma una sola vez**, al cortar, y viaja con el bloque
  (`Bloque.es_tabla`). Volver a deducirla después, ya sobre las líneas
  montadas, convertía en tabla cualquier **párrafo justificado**: el justificado
  alinea palabras en vertical por casualidad, y el criterio laxo picaba.

El módulo no sabe de qué motor vienen las palabras, así que se le aplica igual
a Tesseract y al de Windows. En el de Windows es donde más se nota: por su
cuenta lee las páginas a varias columnas de arriba abajo, columna entera a
columna entera.

Para pasarle la página al OCR hace falta un PNG, y en vez de arrastrar Pillow
por eso está `formatos/png.py`: treinta líneas con `zlib`, que ya viene con
Python. La imagen no se guarda en ningún sitio, se genera y se tira.

## Los libros DAISY

DAISY es lo que prestan las bibliotecas para personas ciegas, y **la mayor parte
de lo que prestan no es texto**: es una grabación humana. Un lector que solo
sepa leer el texto deja fuera casi todo el catálogo, y por eso aquí hay tres
piezas en vez de una.

`nucleo/daisy.py` lee el formato y no sabe nada de audio ni de interfaz.
Entiende las dos generaciones —la 2.02 se navega con `ncc.html` y SMIL 1.0
(`clip-begin="npt=1.709s"`), la 3 con `.ncx`, `.opf` y SMIL 2.0
(`clipBegin="0:00:01.709"`)— y devuelve dos listas atadas entre sí: las
**frases** (los `<par>` del SMIL, en orden de lectura) y la **navegación** (el
índice y las páginas, cada uno apuntando a la frase donde empieza).

Dos detalles que costaron encontrar y que conviene no deshacer:

- **La codificación se resuelve aquí, no en lxml.** Estos libros llevan veinte
  años circulando y casi todos vienen en `windows-1252`. Si se le pasan los
  bytes tal cual, lxml los reinterpreta y el autor de *El principito* pasa a
  llamarse «SAINT-EXUPÃ‰RY». Peor todavía: sobre estos NCC —XHTML con espacio
  de nombres y DOCTYPE externo— el analizador de HTML **se atasca a los pocos
  elementos** cuando recibe bytes, y devuelve dos encabezados de los treinta y
  uno que hay. Con una cadena ya descodificada los lee todos.
- **Los relojes de SMIL se parten de derecha a izquierda.** `01:30` es minuto y
  medio, no una hora y media. Escrito con grupos opcionales de una expresión
  regular sale al revés, porque el primer grupo se queda con lo que encuentra.

`formatos/daisy.py` convierte eso en un `Documento`, y lo hace **siguiendo el
SMIL**, frase a frase. Cada frase deja en el texto un ancla `daisy-N`; como el
ensamblador guarda los identificadores con su posición, el reproductor puede ir
en los dos sentidos: del cursor a la grabación y de la grabación al cursor. Un
libro de solo audio deja así de ser un caso perdido: se monta con lo que sí
trae —el índice y los números de página— y desde cualquier punto se escucha.

`nucleo/audio.py` e `interfaz/reproductor_daisy.py` ponen el sonido. Por debajo
está **basskit**, que envuelve BASS de Un4seen, y se eligió por tres cosas que
un audiolibro necesita: posicionar en el segundo exacto —un libro DAISY
reproduce recortes, no archivos—, cambiar la velocidad **sin cambiar el tono**
(BASS_FX), y abrir igual los MP3 de 1998 y los formatos de ahora. Cada archivo
se abre en dos capas: un flujo de descodificación y, encima, uno de *tempo*.

El reproductor no corta el sonido entre frases: casi siempre la siguiente es el
trozo contiguo del mismo archivo, y en ese caso solo se anota el avance y se
deja sonar. Sin ese cuidado, un libro de seis mil frases sonaría con seis mil
cortes.

Y las teclas —las del programa y las globales— **mandan sobre la grabación
cuando el libro es un DAISY con audio**, y sobre la voz sintética en cualquier
otro caso. Es la misma acción con el motor que corresponde: la tecla significa
«lee esto en voz alta», y cuando el libro trae la voz de un narrador humano eso
es lo que hay que hacer sonar.

## Lo que el programa guarda

La biblioteca —de dónde salen los libros y qué se sabe de cada uno— vive
aparte, en `data/config/biblioteca.db`. Se puede rehacer importando otra vez,
pero con una biblioteca grande eso es un rato, así que «Bibliotecas y carpetas»
tiene su propia copia de seguridad: un ZIP con la base de datos (hecha con la
copia en caliente de SQLite) y `documentos.json`.

De cada libro quedan cuatro rastros —caché, descripciones, marcadores y
posición— y **no valen lo mismo**: la caché se rehace sola volviendo a abrir el
libro, mientras que un marcador lo puso una persona a mano y una descripción
costó una petición a la IA. Por eso `interfaz/dialogos/datos.py` no tiene un
botón de borrar sino una lista de libros y unas casillas para elegir qué
quitarles: tirar la caché de un libro mal analizado sin perder lo demás es
exactamente el caso que hay que poder resolver.

Para saber de qué libro es cada entrada de caché, `guardar()` deja al lado un
archivo `.origen` con la ruta en texto plano. Parece redundante —la ruta ya va
dentro— y no lo es: sin él, listar la caché obligaría a deserializar el
documento entero de cada entrada, que es justo lo que la caché existe para
evitar.

Las casillas son `interfaz.listas.ListaCasillas`. Un `wx.CheckListBox` a secas
expone sus elementos como filas de lista corrientes, así que el lector de
pantalla lee el texto pero **no dice si están marcados**, que es lo único que
hay que saber. Se arregla con un objeto accesible que los declara casillas de
verificación y con un `NotifyWinEvent` al cambiar, que es lo que hace que el
cambio se cante en el momento de pulsar la barra.

## Controles que no se anuncian

`interfaz/accesible.py` le pone nombre a cada control porque el lector de
pantalla anuncia el **nombre accesible**, y sin él se oye solo «cuadro de
edición». Hay dos trampas encontradas midiendo, no leyendo documentación:

- **`wx.SpinCtrl` no anuncia nada por sí solo**, y `wx.Slider` con
  `wx.SL_LABELS` anuncia su propio valor. Por eso el nombre se impone a la
  fuerza con un `wx.Accessible` propio en vez de confiar en que Windows lo
  deduzca del texto de al lado.
- **`wx.SpinCtrlDouble` es un control compuesto.** Por dentro son un
  `wx.TextCtrl` y un `wx.SpinButton`, y **el foco cae en el cuadro de texto
  interno**, que se llama `text` de fábrica. Aunque el contenedor tuviera su
  nombre bien puesto, lo que se oía era «text». `_nombrar_interiores()` se lo
  pone también a esas piezas. `wx.SpinCtrl` no lo sufre porque en Windows es un
  control nativo único.

Estos fallos **no se ven mirando la pantalla**: la etiqueta está escrita al
lado y todo parece correcto. Solo aparecen al recorrer la ventana con el
teclado. Por eso está `herramientas/revisar_accesible.py`, que abre las
ventanas del programa, enfoca cada control y comprueba qué nombre anunciaría
*el que de verdad recibe el foco* —que en los compuestos no es el mismo—.

    python herramientas/revisar_accesible.py

Los contenedores quedan fuera a propósito: un cuaderno de pestañas se anuncia
por la pestaña elegida, y ponerle nombre propio lo sustituiría en todas.

## Las letras de acceso de los menús

En un menú de Windows, la letra subrayada (`&` en la etiqueta) llega a una orden
de una pulsación. Cuando **dos órdenes del mismo menú llevan la misma letra**,
esa tecla deja de activar nada: la primera pulsación resalta una, la segunda
resalta la otra, y encima hay que rematar con Intro. Mirando la pantalla apenas
se nota; recorriendo el menú de oído se vive como que la letra «no funciona», y
no hay forma de averiguar por qué.

En español y en inglés se reparten a mano. En los demás idiomas **no se puede**:
el traductor pone la letra sobre una palabra del texto traducido sin saber qué
hay al lado en ese menú, así que dos órdenes acaban compartiéndola sin que nadie
lo haya decidido. Por eso están las dos mitades:

- `pruebas/test_interfaz.py` construye la barra de menús —submenús incluidos— y
  **falla** si alguna letra se repite dentro de un menú. Es lo que impide que
  vuelva a colarse una.
- `herramientas/revisar_menus.py` hace lo mismo en cada idioma, en un proceso
  aparte por idioma (las tablas de menú se traducen al importarlas y ya no se
  vuelven a traducir), y con `--arreglar` **elige otra letra del propio texto
  traducido** —prefiriendo el principio de una palabra, que es donde se busca— y
  la escribe en el catálogo.

      python herramientas/revisar_menus.py            # solo dice qué encuentra
      python herramientas/revisar_menus.py --arreglar # además lo corrige

Lo que la herramienta no puede resolver lo dice en voz alta: si una traducción
es tan corta que **todas sus letras están ya cogidas**, avisa con «sin letra
libre» y hay que darle un rótulo más largo a mano. Pasó con el italiano de
«Acerca de», que había quedado en «Di...».

La lista de documentos recientes se numera en marcha y no pasa por el catálogo:
ahí la letra se pone solo a los nueve primeros, porque del décimo en adelante el
subrayado caería otra vez sobre el «1».

## Progreso y cancelación

`OpcionesAnalisis` lleva un `Progreso` (`formatos/base.py`), y los analizadores
llaman a `paso(hecho, total, mensaje)` por cada capítulo, sección o página. Es
un canal en las dos direcciones: cuenta por dónde va y, si mientras tanto se ha
pedido cancelar, ese mismo `paso` levanta `Cancelado`, que la ventana atiende
sin tratarlo como avería. El canal **no entra en `firma()`**: no cambia el
resultado, así que no debe invalidar la caché.

Al otro lado está `DialogoProgreso` (`interfaz/dialogos/progreso.py`), con dos
decisiones que solo se entienden pensando en el oído:

- **No aparece enseguida** (`mostrar_tras`). Un EPUB se abre en una décima de
  segundo; sacar y quitar una ventana en ese tiempo es un parpadeo que además le
  roba el foco al lector de pantalla justo cuando va a leer el libro. Con medio
  segundo de retardo, la ventana sale solo cuando hay espera de verdad.
- **No canta cada paso.** Un PDF de trescientas páginas dispararía trescientos
  avisos, cortándose unos a otros. Se anuncia cada diez puntos porcentuales y
  nunca dos veces en menos de tres segundos; la barra, en cambio, se actualiza
  siempre, para quien la consulte a propósito.

Lo que tarda y no se puede medir —describir una imagen, vaciar la caché,
consultar los modelos de un proveedor— usa una barra que late: `DialogoEspera`
si hay que bloquear, o la barra del propio diálogo si no.

## Traducible desde el principio

Todo el texto que ve o escucha el usuario pasa por `_()` (`nucleo/idioma.py`).
Los originales están **en español**: son ellos mismos la clave de la traducción,
de modo que sin ningún `.mo` instalado el programa funciona exactamente igual y
`_()` devuelve el texto tal cual. `herramientas/textos.py` extrae la plantilla
—**753 textos** hoy— y compila los `.po` sin necesitar `gettext` instalado.
Vienen **español e inglés**, y los idiomas que se dejen en `data/idiomas` se
detectan solos: no hay ninguna lista que mantener, y el nombre de cada lengua
sale de un diccionario de códigos ISO 639-1 escrito en la propia lengua.

Un detalle que costó encontrar: un `.mo` **sin su entrada de cabecera** hace que
`gettext` lo lea como ASCII y reviente en el primer acento. El compilador la
pone siempre, incluso si el `.po` viene sin ella.

`_()` es una función propia que consulta la traducción **en cada llamada**, no
una referencia directa a la de `gettext`. Así, el `from nucleo.idioma import _`
que hay al principio de cada módulo sigue valiendo aunque la traducción cambie
después.

Dos decisiones que conviene conocer:

* **Los mensajes del registro NO se traducen.** Un registro que envía un usuario
  tiene que poder leerlo quien lo reciba, hable el idioma que hable.
* **Cambiar de idioma pide reiniciar.** Las tablas de atajos y los nombres de
  los prompts se construyen al importar sus módulos, así que se traducen una
  sola vez. Lo contrario obligaría a reconstruir media aplicación en caliente
  para un cambio que se hace una vez en la vida. Por eso `main.py` llama a
  `idioma.instalar()` **antes** de importar nada de `interfaz`.

## Deshacer el texto plano: el visor HTML

Convertir el libro a texto plano es lo que hace rápido al programa, pero tiene
un precio conocido: **una tabla deja de ser una tabla**. En el texto es una
rejilla de tabuladores, y el lector de pantalla ya no puede aplicarle sus
órdenes de tabla porque para él ahí no hay ninguna.

`nucleo/html_elementos.py` deshace ese camino para un elemento concreto:
reconstruye el HTML semántico a partir de la marca (tablas con `<th scope>`,
listas anidadas distinguiendo `<ol>` de `<ul>`, citas en `<blockquote>`) y
`interfaz/dialogos/visor_html.py` lo muestra en un `wx.html2.WebView`.

El WebView se maneja con el paquete **`wx-accessible-webview`**, que resuelve un
problema viejo: al ser un control nativo creado por una factoría no se puede
heredar de él para arreglarlo, y empotrado en wxPython se leía de forma
irregular en NVDA y casi nunca en JAWS. Su enfoque es no pelearse con el
control, sino generar dentro un documento HTML semántico, que es lo que el
lector de pantalla sigue sin problemas.

Dos datos que las marcas no guardan y que se deducen del texto:

* **qué fila era el encabezado de la tabla**: se toma la primera, igual que ya
  hacía la ventana de rejilla; falla poco y cuando falla no estropea nada;
* **si una lista era ordenada**: el conversor escribe «1. » o «• » delante de
  cada elemento, así que se deduce de la línea.

Todo el HTML que sale del libro se escapa antes de insertarlo, de modo que el
contenido de un EPUB no pueda inyectar etiquetas en el visor.

## Inteligencia artificial sin dependencias

La descripción de imágenes habla con **Google Gemini** y con **cualquier servidor
local compatible con la API de OpenAI** (llama.cpp, Ollama, LM Studio) usando
solo `urllib.request` y `json`. No se instala el SDK de Google ni `requests`:
para lo que hace falta —mandar una imagen en base64 con un texto y leer la
respuesta— son dos peticiones HTTP, y evitarlo mantiene el ejecutable pequeño y
sin depender de que un paquete de terceros siga manteniéndose.

Dos detalles que salen del uso real:

* **Varias claves de Gemini.** La capa gratuita tiene cuota por clave. Se
  admiten varias y, ante un 429, se pasa sola a la siguiente sin que el usuario
  se entere: para él es una operación que tarda algo más.
* **Solo los modelos que sirven.** `models.list` devuelve también los de voz,
  los de incrustaciones y los que *generan* imágenes en vez de leerlas. Se
  filtran por nombre (`nucleo/ia/gemini.py`), de modo que en el desplegable solo
  aparece lo que de verdad puede describir una foto. El campo es editable, para
  que un modelo nuevo se pueda escribir a mano sin esperar a una versión nueva.

Las descripciones se guardan **por libro** en `data/descripciones`, y no dentro
de `documentos.json`: son largas y no conviene releerlas todas al arrancar, y
así se pueden borrar las de un libro sin tocar sus marcadores.

## La lectura en voz alta y las dos voces

El lector TTS usa las voces SAPI 5 del sistema a través de `win32com`, y lee
**frase a frase** (`nucleo/segmentador.py`). La unidad importa: con párrafos,
pausar tardaría en responder y no habría forma de releer una frase suelta. El
partido conoce las abreviaturas españolas (`Sr.`, `pág.`, `D.`) y los decimales,
que si no cortarían la frase por la mitad.

El encadenado se resuelve con un temporizador que mira cada 120 ms si SAPI sigue
hablando: SAPI no avisa al terminar, y así no hace falta ningún hilo.

**El cursor no acompaña a la voz**, y esa es la decisión de diseño principal. El
control de texto tiene el foco, de modo que mover el cursor haría que el lector
de pantalla leyera la línea *además* de nuestra voz: dos voces diciendo lo mismo.
En su lugar se recuerda por dónde va la lectura y el cursor se coloca ahí **al
pausar o al detener**, que es cuando el usuario quiere seguir a mano. Es
opcional para quien lo siga en una línea braille.

## Teclas globales: cuatro comprobaciones, una que manda

`interfaz/teclas_globales.py` registra las teclas del lector con
`wx.Window.RegisterHotKey`, que por debajo es la `RegisterHotKey` de Windows.
Dos detalles de esa API mandan sobre el diseño: quiere **códigos de tecla
virtuales** (la flecha arriba es 0x26, no `wx.WXK_UP`), y **falla si la
combinación ya está cogida** (error 1409). Eso segundo convierte un intento de
registro en la comprobación definitiva: no hay que adivinar qué tiene ocupado el
sistema, basta con pedirlo.

De ahí las cuatro comprobaciones, en orden de coste: forma válida, lista negra,
choque con otra acción propia y, por último, registro real contra Windows. La
lista negra no sobra pese a tener la cuarta: las teclas de los lectores de
pantalla **sí** se registran (NVDA y JAWS capturan el teclado por debajo), de
modo que sin ella el usuario creería haberlas asignado y no funcionarían nunca.

Las combinaciones de fábrica se eligieron **sondeando el sistema**, no por
intuición: `Alt+Windows` con las flechas y `Control+Windows` con las flechas
están cogidas por Windows, y `Control+Alt` a secas lo usan los atajos de la
propia aplicación —una tecla global con esa forma dejaría sin efecto el atajo de
dentro, porque el registro global tiene prioridad—. `Control+Alt+Mayús` quedó
libre en las siete.

## Los datos de un gráfico, no su descripción

`nucleo/graficos.py` es la pieza que faltaba entre tres que ya existían: el
programa recortaba la figura y se la mandaba a la IA, la IA sabe leer los valores
de un gráfico, y el programa sabe enseñar una tabla navegable. Lo único que hacía
falta era una instrucción distinta y un intérprete de lo que vuelve.

Tres decisiones que explican el módulo:

- **Se pide una tabla de Markdown**, no un JSON ni tabuladores. El JSON falla
  entero cuando falla —una coma de más y no hay nada que salvar—, y el tabulador
  casi ningún modelo lo respeta. Una tabla de Markdown **se degrada bien**: si el
  modelo se despista en una fila, esa fila se pierde y las demás valen.
- **Se puede decir que no.** Si la imagen no es un gráfico con valores, la
  instrucción pide una palabra concreta y el intérprete devuelve `None`. Una
  tabla inventada parecería un dato, que es el peor de los fallos posibles.
- **La tabla se guarda ya interpretada**, junto a la descripción y en el mismo
  archivo (`nucleo/descripciones.py`), con las filas separadas por saltos y las
  celdas por tabuladores: el mismo formato que usan las tablas del libro. Así se
  enseña con la maquinaria que ya había, sin escribir ni una línea de dibujado.

---

## Química y matemáticas: dos caminos distintos a propósito

Las **matemáticas** se convierten en el momento del análisis: el MathML pasa a
texto y a una marca `FORMULA` que guarda el original. La **química** no toca el
documento en ningún momento: se aplica **solo a lo que se dice**
(`nucleo/quimica.py`), como el diccionario de pronunciación. La razón es que una
fórmula química no está marcada en ninguna parte del archivo —es texto normal— y
reconocerla es una **conjetura**; una conjetura no puede cambiar el texto del
libro.

De ahí sale la regla que gobierna el módulo: **solo es fórmula lo que trae un
número, una carga o un estado de agregación.** Muchas palabras corrientes se
descomponen en símbolos químicos —«con» es C+O+N, «sin» es S+In, «no» es N+O— y
leer «con» como «carbono oxígeno nitrógeno» en una novela sería mucho peor que no
leer bien una fórmula en un libro de química. Y por si acaso, el modo automático
mide el documento antes de encenderse: por debajo de cinco fórmulas, no se activa.

---

## Braille matemático: hacerlo bien o no hacerlo

`nucleo/braille_matematicas.py` sigue el **Código Matemático Unificado para
Iberoamérica**, y sus signos están tomados literalmente del documento, con la
cláusula de cada uno anotada en el propio módulo.

Lo que define su diseño es lo que hace cuando no sabe: **se niega**. Devuelve
`None` en cuanto encuentra una integral, una matriz o un sumatorio con límites, y
entonces la fórmula se escribe hablada, como antes. Una transcripción matemática
equivocada es peor que ninguna, porque quien la lee no tiene forma de saber que
está mal y se lleva a un examen una fórmula que no es la del libro.

La regla de los paréntesis auxiliares se decide por **estructura y no por número
de celdas**: «x elevado a 2» son cuatro celdas y un solo término, y el código lo
escribe sin paréntesis.

---

## BZZ: el codificador que costó dos intentos

`formatos/bzz.py` descomprime el texto de un DjVu. Son dos piezas encadenadas: un
codificador aritmético binario adaptativo —el «ZP»— y una transformada de
Burrows-Wheeler. Está escrito siguiendo `ZPCodec.cpp` y `BSByteStream.cpp` de
DjVuLibre, que es la única descripción completa que existe; los resúmenes
publicados se dejan justo los detalles que deciden si funciona.

El primer intento se abandonó y se borró: descodificaba bien los números **sin**
modelo de contexto —el tamaño de cada bloque salía exacto— y se descarrilaba en
cuanto entraba el modelo. La causa está ahora anotada en el módulo y es una sola
línea:

- **El atajo de la valla no es una optimización.** La ruta rápida devuelve el bit
  sin renormalizar y dejando `a = z`; la larga renormaliza. Tomar siempre la
  larga desincroniza el codificador a los pocos bits. Y como la decodificación
  *sin* contexto nunca pasa por la valla, esa salía bien y la otra mal, que es
  exactamente lo que se observaba.
- **La variable de contexto es a la vez estado y predicción**, y hay que
  escribirla de vuelta donde estaba o lo aprendido se pierde.
- **Un chorro BZZ tiene que ir acotado.** Solo para al leer un tamaño de bloque
  cero; sin decirle dónde acaba su trozo, se come el siguiente. El índice de un
  DjVu se descomprimía bien y acto seguido se estropeaba con lo que tenía al lado.

Se comprobó contra un DjVu real de una biblioteca: el texto sale **idéntico letra
por letra** al que el propio archivo declara, salvo por las palabras partidas al
final del renglón, que aquí se recomponen y allí no.

---

## DjVu: por qué el texto no se corta por líneas

El árbol de zonas de un DjVu describe página, columna, región, párrafo, línea y
palabra, con el trozo de texto que ocupa cada una. Parece natural cortar por las
zonas de línea. **No lo es**: los rangos de las zonas trocean el texto plano en
tramos seguidos que no respetan los límites de palabra. En una página con una
nota al margen, el texto plano intercala la nota con el cuerpo, y la línea que
geométricamente las cruza acaba en «Jam» mientras la siguiente empieza en «es».
Uniendo esos tramos con un espacio sale «Jam es Caldwell».

Por eso se corta por **zonas de párrafo**, y aun así con una condición: una zona
que **no acaba en un espacio** no es un párrafo, es una palabra partida, y se
pega a la siguiente sin poner nada en medio. Dentro de un párrafo ya mandan los
saltos de línea del texto plano, que son los renglones que había en el papel.

---

## Raíces y significados: dos módulos, dos problemas distintos

`nucleo/raices.py` recorta cada palabra hasta su raíz siguiendo el **algoritmo de
Snowball para español**. Se escribió propio —doscientas líneas— en vez de traer
una biblioteca, y se comprobó contra el vocabulario oficial del proyecto:
**28 378 palabras, cero diferencias**, en dos décimas de segundo. Esa prueba
encontró tres errores que a ojo no se veían: faltaba la terminación `id`, sobraba
`ais` sin tilde —que dejaba «Beauvais» en «beauv»— y, al fallar una terminación
en `y`, el algoritmo se rendía en vez de seguir probando.

`nucleo/semantica.py` es otra cosa: no mira la palabra, mira **dónde sale**. Dos
palabras que significan casi lo mismo aparecen en los mismos pasajes, y eso se
mide. Se hace sobre la biblioteca del usuario y no con un modelo de lenguaje
porque un modelo costaría cientos de megabytes o una cuenta, y devolvería las
relaciones de un castellano general en vez de las de esa asignatura.

Lo que evita que devuelva ruido, que es el único riesgo:

- Una raíz que sale en más de un tercio de los pasajes **no relaciona nada**: se
  descarta. Así no hace falta una lista de palabras vacías escrita a mano.
- Se exige que dos raíces coincidan **más de lo que coincidirían por azar** dadas
  sus frecuencias. Sin eso, «aquello» y «mientras» salen como parientes de todo.
- El texto se recorre **dos veces** —contar y después guardar— en lugar de
  troceado en memoria: trescientos libros son cuarenta mil pasajes, y tenerlos a
  la vez costaría más memoria de la que se puede pedir en un programa portátil.
- Y lo relacionado **se ofrece, no se impone**: la búsqueda sigue encontrando lo
  que se escribió, y las palabras emparentadas se enseñan aparte para que el
  usuario elija.

---

## Química y música en braille: la misma regla que las matemáticas

`nucleo/braille_quimica.py` sigue el documento B 6-1 de la Comisión Braille
Española y `nucleo/braille_musica.py`, el B 4-2. Los dos están guardados en
`adjuntos/Estudio/normas`.

No se reutiliza el módulo de matemáticas porque **no es la misma notación**: en
química el número de átomos va en la quinta serie del braille sin signo de
subíndice, así que `H₂O` son tres celdas y no cinco. Y hay una regla que decide
si el resultado se puede leer: los puntos de las cifras bajas **son los mismos**
que los de los operadores —el seis bajo y el signo de sumar son los dos puntos
235—, y la norma lo resuelve exigiendo un espacio a cada lado de todo operador.
Sin él, `2H₂ + O₂` y otra cosa se escriben igual.

En musicografía, la regla que decide si una partitura se lee con soltura o
deletreando es **cuándo se escribe el signo de octava**: nunca tras un salto de
segunda o tercera, solo si cambia de octava tras una cuarta o una quinta, y
siempre a partir de la sexta. Y no se reinicia en la barra de compás: se sigue
contando de una nota a la siguiente.

Los acordes y las voces simultáneas sí se escriben: el acorde, con **una** nota
y las demás medidas desde ella con signos de intervalo; las voces, separadas por
la cópula. Y los adornos —trinos, mordentes, grupetos, apoyaturas— llevan los
signos del *New International Manual of Braille Music Notation*, porque el B 4-2
avisa de que no es exhaustivo y remite ahí.

Los dos hacen lo mismo que el braille matemático cuando no saben: **se niegan**.
Las estructuras químicas dibujadas, el trémolo y los arpegios que cruzan dos
pentagramas se dicen en palabras y se advierte.

---

## Braille contraído: cómo se comprueba una transcripción

`nucleo/braille_contraido.py` sigue el documento B 16-1 de la Comisión Braille
Española y aplica sus cinco pasos en orden: la lista de palabras abreviadas, los
principios, los finales, las secuencias y las contracciones. El orden no es
decorativo, y la propia norma lo dice: saltarse el primer paso «no es elegir
entre dos abreviaturas alternativas, sino hacerlo mal».

**El problema de fondo de este módulo no es escribirlo: es saber si está bien.**
Un texto contraído mal no lo distingue de uno correcto quien lo lee con los
dedos, así que una prueba escrita a mano solo comprobaría lo que uno mismo ha
entendido del documento. La salida fue esta:

1. El documento escribe **cada signo dos veces**: como glifo del ASCII braille de
   la ONCE y como lista de puntos. Emparejando las dos columnas se reconstruye la
   correspondencia entre ambos —salieron **64 signos sin un solo conflicto**, que
   ya es una señal de que la extracción es fiel—.
2. Con esa correspondencia se pueden **descodificar los ejemplos resueltos** que
   el documento trae repartidos por sus capítulos: 123 palabras con su
   transcripción, más seis contraejemplos de lo que **no** hay que escribir.
3. Y eso es la prueba de aceptación (`pruebas/test_braille_contraido.py`).

El resultado medido: **100 % en las palabras de la lista, 100 % en sus variantes
y 91 % en el proceso mecánico**. Los siete fallos están enumerados uno a uno en
la prueba, con lo que se sabe de cada uno, para que un cambio los mueva y se note.

Las tablas se **extraen del PDF con sus columnas de verdad** y no del texto
aplanado. Es la diferencia entre tener las variantes aceptadas de cada palabra y
no tenerlas: en una tabla de cuatro columnas, el texto aplanado derrama la última
sobre las filas de al lado.

Tres reglas que costaron y que están en el código con su porqué:

- **Los principios se encadenan** —«sobreinterpretar» son tres seguidos— y solo
  el último tiene que preceder a una consonante. Y tienen que preceder a **dos
  letras al menos**: por eso «entren» es «en-tr-en» y no «entre-» más una ene.
- **Gana la contracción de detrás**: «labrar» es l-a-br-ar, no l-ab-r-ar.
- **La marca de plural depende de quién la lleve.** Una palabra de la lista usa el
  signo de género; un final usa la marca que le toca en su propia tabla, que puede
  ser una letra suelta. Por eso «mimbres» acaba en una ese y «asientos», en el
  signo de «-os».

Está **apagado por omisión**, y no por prudencia con el código: quien no ha
estudiado el contraído no lo entiende, así que encenderlo por omisión dejaría a
mucha gente con un archivo ilegible.

---

## Control+F1 en todas partes, y comprobado a máquina

`interfaz/ayuda_control.py` guarda la explicación de cada control y
`interfaz/dialogos/ayuda_opcion.py` la enseña. Dos cosas que cambiaron al
llevarlo de diez ventanas a las cuarenta y nueve:

**La clave puede llevar delante el nombre de la ventana.** Casi todas tienen una
`lista`, un `filtro` y un `boton_guardar`, y no son la misma cosa. Se busca
primero `DialogoCuaderno.lista` y después `lista` a secas, así que un ajuste que
significa lo mismo en todas partes se escribe una vez y el que significa algo
distinto en cada sitio se escribe donde toca, sin tener que renombrar controles.

**Y hay una comprobación que lo recorre entero** (`herramientas/revisar_ayuda.py`,
y una prueba que la ejecuta). Lee el código con `ast` —no abre ninguna ventana—,
busca los controles que cada ventana guarda en un atributo propio y falla si
alguno no tiene explicación o si una ventana no engancha `Control+F1`. Una
explicación escrita una vez y no vuelta a mirar envejece sola: se añade un botón,
se olvida la entrada y quien pulsa encima oye que no hay nada escrito. Con la
vista eso se disimula con el rótulo y con lo que hay alrededor; sin ella, no.

Las dos ventanas que se quedan fuera están **escritas en el propio comprobador**,
con su motivo, para que se vea que es una decisión y no un olvido.

---

## Office 97: un sistema de archivos dentro de un archivo

`formatos/ole.py` lee el envoltorio de los `.doc`, `.xls` y `.ppt`, y por dentro
se parece muchísimo a un disquete en FAT: sector de arranque, tabla de asignación
que dice qué sector va detrás de cuál, directorio con nombres, y una segunda
tabla más pequeña para los flujos diminutos —lo mismo que hacía el DOS para no
desperdiciar un sector entero en un archivo de doscientos bytes—.

Está escrito aquí y no se usa una biblioteca por lo mismo que con el LZX y el
BZZ: son doscientas líneas que no van a cambiar nunca —el formato lleva congelado
desde 1997— y una dependencia por esto se arrastraría en el ejecutable, en la
licencia y en cada actualización. El material de consulta está en
`adjuntos/Estudio/olefile` y `adjuntos/Estudio/catdoc`.

De lo de encima, lo que costó fue **Word**. El documento está partido en trozos
—el *piece table*— y **cada trozo dice por su cuenta si está en Latin-1 o en
UTF-16**, porque Word 97 guardaba en un byte lo que cupiera en un byte. Leer el
archivo de principio a fin sin mirar esa tabla da un texto que parece bien y está
mal: trozos desordenados y la mitad de las tildes rotas. Es lo que hacen las
herramientas de línea de órdenes de siempre, y por eso avisan de que en un
documento «guardado rápido» se pierde información.

Tres decisiones que salieron de probarlo contra veintiocho archivos de verdad:

- **Las posiciones de la cabecera se calculan, no se dan por sabidas.** Los
  números fijos que circulan —0x1A2 para la tabla de trozos— valen para el Word
  97 corriente y fallan con otras versiones. La cabecera dice su propia
  estructura y se recorre.
- **Un archivo cifrado se dice.** Sin detectarlo, un `.xls` protegido **se abre
  igual** y saca nombres de hoja como «䉽퉶捠». Uno que se abre y dice disparates
  es peor que uno que dice claramente que no puede.
- **Un registro roto se salta y la hoja sigue.** Con un archivo de hace veinte
  años sacado de un disquete, perder una celda es mucho mejor que perder la hoja.

Y de PowerPoint: solo se recoge lo que está **dentro de una diapositiva**. Por el
mismo archivo andan el texto de la plantilla, los nombres de los objetos
incrustados y las marcas de versión del programa, todo en átomos idénticos a los
del texto de verdad. Recogerlo de corrido daba una presentación llena de
«___PPT12» y «Objekt-Manager-Shellobjekt» en la que había que adivinar qué
escribió una persona.

---

## Una raya no es un guion, y ahí está todo el trabajo

`nucleo/dialogos.py` reparte una frase en lo que dice el personaje y lo que dice
el narrador, para leerlos con dos tonos. Cambiar el tono es una línea; lo que
cuesta es saber **dónde**.

En español el diálogo se marca con raya (—) y el inciso del narrador va entre
dos más: «—No pienso ir —dijo ella—. Y no insistas». Contar rayas resuelve el
caso limpio. El problema es el libro convertido deprisa desde un PDF, donde la
raya se ha vuelto un guion corriente — y un guion al principio de un renglón es
también **una viñeta de lista**.

Poner voz de personaje a la lista de la compra es mucho peor que no cambiar de
voz en absoluto, así que la regla es deliberadamente prudente y va por documento,
no por renglón:

- La raya larga se toma siempre por diálogo: en español no significa otra cosa.
- El guion solo cuenta si el libro **no usa rayas en ninguna parte** —si las usa,
  ese guion es otra cosa— y además el renglón se parece a una intervención:
  tiene verbo de habla, o acaba en punto, y no es una de esas líneas cortas y
  sin puntuación de las que se hacen las listas.
- Decidirlo una vez por libro, y no frase a frase, es lo que evita que un guion
  sea diálogo en una página y una lista en la siguiente.

**Cuando hay duda, se lee como narración.** Equivocarse hacia ese lado deja la
frase igual que antes; hacia el otro, pone voz de personaje a un índice.

Y el cambio de tono se hace con las marcas de SAPI, no cambiando de voz: un
`<pitch>` alrededor del tramo. Por eso el texto se escapa siempre —un libro trae
signos de menor y ampersand— y por eso la lectura normal **no pasa por ese
camino**: si no hay diálogo, se dice el texto tal cual y la voz no tiene nada que
interpretar.

---

## El 7-Zip va dentro, como Tesseract

Por la misma razón que el reconocimiento óptico: pedirle a alguien que instale
otro programa para poder leer su propio archivo es justo lo que este programa no
quiere hacer. Son dos megas y medio en `data/bin`, y quitan de en medio el único
sitio donde el programa todavía tenía que decir «instala otra cosa».

Dos detalles que importan:

- Se copian **`7z.exe` y `7z.dll`**. La biblioteca es donde viven los formatos:
  sin ella, el ejecutable entiende 7z y ZIP y deja fuera justamente el RAR.
- Va **el primero** de la lista, y también el primero al preguntar qué hay
  dentro de un comprimido. El `tar` de Windows, ante un RAR partido, lista solo
  el primer volumen sin decir que se deja el resto; preguntándole a él, comparar
  lo listado con lo extraído daba «completo» faltando media historieta.

Se prepara con `python herramientas/siete_zip_portable.py`, que lo descarga, se
queda con lo que hace falta y **comprueba que el ejecutable reconoce RAR**, que
es lo único que de verdad importa comprobar.

---

## Un RAR partido, sin depender de que haya nada instalado

`nucleo/rar.py` no descomprime: lee cabeceras y copia bytes. Suena a poco y
resuelve el caso que quedaba pendiente, por una razón que no es casualidad: **las
páginas de un cómic son JPEG o PNG, que ya están comprimidos**, y comprimir de
nuevo algo comprimido no ahorra nada, así que los programas los guardan tal cual.

Lo que se gana es lo que no se veía: la página que queda **partida entre dos
volúmenes**. Comprobado con un archivo hecho a propósito de doce páginas en dos
volúmenes: las doce salen y son idénticas byte a byte a las originales, incluida
la que cruza la costura.

Cuando un archivo sí va comprimido de verdad lo saca el 7-Zip que va dentro, así
que el aviso de «esto no se puede abrir» ya no le hace falta a nadie. El código
propio se queda igualmente: es el que junta los volúmenes y el que resuelve la
página partida entre dos, que ningún descompresor hace.

Y los nombres de dentro se limpian antes de escribir nada: un comprimido puede
traer rutas con «..» o absolutas, y escribirlas tal cual dejaría que un archivo
cualquiera pusiera cosas donde le pareciera. Es un problema viejo y la respuesta
es igual de vieja.

---

## Un diagrama no es una tabla: es un grafo

`nucleo.esquemas` es el hermano de `nucleo.graficos`, y la diferencia es la forma
del dato. Un gráfico de barras **es** una tabla: con filas y columnas ya se
recorre. Un diagrama de flujo no: es un grafo, y lo que se recorre de un grafo es
su **recorrido**, que de oído se lee como una lista anidada.

Por eso la salida son `<ol>` anidados de verdad y no un párrafo con flechas
dibujadas con guiones: la lista la anuncia el lector de pantalla, dice en qué
nivel está y deja saltar de elemento en elemento. Un párrafo se oye entero o no
se oye.

Cuatro cosas que hubo que decidir:

- **Los ciclos.** Un diagrama de flujo casi siempre tiene un bucle, y una lista
  anidada no puede repetirlo sin dar vueltas para siempre. Al llegar a un paso
  por el que ya se pasó se escribe «vuelve al paso N» **con el rótulo de su
  flecha** —«si no, vuelve al paso 2»—, porque el bucle suele ser justo la rama
  del «no» y sin decirlo no se sabe cuándo se vuelve.
- **La profundidad.** A partir de ocho niveles el lector de pantalla canta más
  niveles que texto, así que se corta diciendo por dónde sigue.
- **Un botón y no dos.** La misma orden pregunta primero por los datos y, solo si
  la imagen no era un gráfico, por la estructura. Saber si dentro de una imagen
  hay una tabla o un diagrama es exactamente lo que quien no ve no puede
  averiguar antes de pulsar.
- **Se guarda donde la tabla**, con una marca (`ESQUEMA`) en la primera celda.
  Para una imagen solo puede haber una de las dos cosas —o tiene valores o tiene
  estructura—, y `Descripcion.grafico()` devuelve `None` cuando lo guardado lleva
  esa marca: sin eso, un diagrama se leería como una tabla de tres columnas que
  no significa nada.

---

## Un acorde en braille: cómo se comprobó la tabla de intervalos

Los siete signos de intervalo son la pieza que hacía falta para escribir acordes,
y son siete celdas que no se pueden equivocar: un acorde con un intervalo mal
puesto no se detecta leyéndolo.

El documento B 4-2 los da **como glifos** del ASCII braille de la ONCE, no como
listas de puntos, y su PDF usa una codificación de fuente distinta de la del
B 16-1: los mismos puntos salen con otro carácter. Así que la tabla no se copió,
se **verificó cruzando los dos documentos**: seis de los siete glifos aparecen
también en el alfabeto reconstruido del B 16-1
(`adjuntos/Estudio/normas/contraido_tablas.json`) y dan exactamente los puntos
del sistema internacional —segunda 34, cuarta 3456, quinta 35, sexta 356,
séptima 25, octava 36—. El séptimo, la tercera, completa el juego con los puntos
346. Los signos de cópula y el fraccionador se comprobaron igual, contra los
signos de mano derecha e izquierda que el propio B 4-2 escribe en otro epígrafe:
salen los mismos puntos por los dos caminos.

Tres reglas que están en el código con su porqué:

- **La dirección la decide la clave**, no el gusto: en clave de sol el acorde se
  escribe de arriba abajo y en clave de fa, de abajo arriba. No es presentación
  —decide cuál es la nota que se escribe entera y desde dónde se miden los
  intervalos—, así que un acorde escrito al revés dice otra cosa.
- **La regla de la octava se cuenta desde la nota principal** del acorde, que es
  la única escrita como nota.
- **Después de una cópula va octava, y también al empezar el compás siguiente.**
  Lo dice la norma y se ve por qué en cuanto se prueba: la segunda voz empieza
  donde le da la gana.

Y una comodidad que evitó tocar el camino normal: un compás de una sola voz se
sigue guardando como una lista de notas, y solo los de varias voces se guardan
como lista de listas. Casi toda la música pasa por donde pasaba antes.

---

## Practicar: por qué se mira el documento y no las teclas

`nucleo.practica` guarda los ejercicios y `interfaz.dialogos.practica` los pone
en pantalla. La separación no es ceremonia: el enunciado, el que decide si ha
salido y el que elige cuáles caben en este documento son funciones sobre datos, y
por eso se prueban enteros sin abrir wxPython.

**La comprobación mira el estado del documento cada 250 ms, no las pulsaciones.**
Enganchar las teclas sería más directo y estaría mal: quien llega al tercer
encabezado con el árbol de contenido en vez de con `H` ha hecho el ejercicio, y
decirle que no lo ha hecho sería mentirle. Además, engancharse a las teclas
obligaría a duplicar el mapa de atajos en un segundo sitio.

Tres decisiones que salieron de probarlo:

- **La ventana no es modal.** El ejercicio se hace en el documento; una ventana
  modal lo haría imposible.
- **Todo lo que se dice se anuncia por la ventana principal** (`ventana.anunciar`),
  porque es la que tiene el foco mientras se practica. Un aviso dicho por una
  ventana que no tiene el foco no lo oye nadie.
- **`hecho()` recibe dos estados, el de antes y el de ahora.** «Poner un
  marcador» no es tener marcadores: es tener **uno más** que al empezar el
  ejercicio, y en un libro ya trabajado eso no se puede saber mirando solo cómo
  está ahora.

Y un caso que solo aparece usándolo: el cursor está donde uno lo dejó, así que un
ejercicio puede estar cumplido **antes de empezar**. Se dice —«este ya lo tenías
hecho»— y se pasa al siguiente, en lugar de felicitar a alguien por no haber
hecho nada.

---

## Una tabla en braille: la columna es el dato

`nucleo.braille.tabla_a_lineas()` compone una tabla en columnas alineadas y, si
no cabe en el renglón, la lineariza poniendo el nombre de la columna delante de
cada dato. Tres cosas que no son evidentes:

**El encabezado se decide, no se supone.** Dar la primera fila por encabezado
siempre tiene dos costes. El menor: dibujar una raya de separación bajo una fila
que es de datos, diciendo que son los títulos. El grave: en el texto linealizado
esa fila **desaparece**, porque pasa a ser la lista de rótulos. Se comprobó sobre
una tabla de verdad —las palabras reservadas del manual de Python, cincuenta
palabras en cinco columnas sin ningún título— y por eso `_hay_encabezado()` pide
que arriba no haya celdas vacías ni números y que debajo haya alguno.

**En contraído hay que contraer antes de alinear.** «Ventas» ocupa seis celdas en
integral y cinco en contraído. Alinear con las anchuras del texto y contraer
después descuadra todas las columnas, que es exactamente lo que la tabla venía a
evitar. Por eso `tabla_a_lineas` recibe un `traducir` y lo aplica **celda a
celda**, antes de medir.

**Y la puntuación se traduce dentro del renglón.** En el texto linealizado, los
dos puntos de «Trimestre: 12.400» tienen su propio signo braille. Componer el
renglón en braille y pegarle después un `:` de teclado dejaría un carácter que en
braille ASCII significa otra cosa, así que se traduce la frase entera de una vez.

---

## Repasar lo marcado: dónde vive el estado, y por qué no con el libro

`nucleo.repaso` implementa SM-2 con **tres** respuestas en vez de seis. No es un
recorte por comodidad: de oído hay que escuchar las seis opciones cada vez, y
decidir entre «casi» y «casi casi» no lo sabe hacer nadie.

Lo repasado se guarda en `config/repaso.json`, **fuera de los datos de cada
documento**, por dos razones que tiran en la misma dirección: una tanda de repaso
cruza libros —los seis de la asignatura— y lo que se guarda aquí caduca, mientras
que un marcador dura lo que dure el libro. Juntarlos haría que borrar un repaso
tocara los marcadores.

Dos decisiones de la ventana que son de accesibilidad y no de diseño:

- **La tarjeta se enseña en dos tiempos y la respuesta está detrás de una tecla**,
  no debajo. Puesta debajo, el cursor la leería sola al bajar por el cuadro y la
  tarjeta dejaría de preguntar nada.
- **Se guarda después de cada tarjeta**, no al cerrar. Son unos kilobytes, y a
  cambio cerrar con la cruz no tira media hora de repaso.

El cuaderno (`nucleo.cuaderno`) se monta **sin abrir ningún libro**: cada marcador
guarda su propio `fragmento`, así que trescientos libros se recorren al instante.
Lo único que se pierde es la página exacta —solo se sabe con el documento
delante—, y en su lugar va el porcentaje, que ya está guardado.

---

## Dibujar una curva en la línea braille

`nucleo/braille_grafico.py` dibuja los datos de un gráfico con celdas de ocho
puntos, que son una rejilla de dos por cuatro. Cuarenta celdas dan ochenta puntos
de ancho.

Esto no contradice lo que el programa dice sobre sonificar los gráficos —que no
comunica valores exactos y cansa—, porque **no sustituye a nada**: los números
siguen en la tabla, exactos, y el dibujo va además, para lo único que una tabla
no da, que es la forma de un vistazo. A diferencia del sonido, un dibujo braille
se queda quieto y se puede recorrer con el dedo tantas veces como haga falta.

Va acompañado **siempre** de una frase que dice lo mismo —«sube en conjunto, con
altibajos; el máximo está en el punto 7 de 12»—, porque la mayoría de la gente no
tiene una línea braille de celdas gráficas.

---

## Traer una página: dónde está el fallo que llevaba años

`nucleo/traer_web.py` descarga una página con `urllib`. Lo interesante no es eso,
sino lo que destapó: **una página web moderna se leía casi vacía**. El conversor
prefería el analizador de XML —que es lo correcto para un EPUB— y solo se pasaba
al de HTML si veía entidades como `&nbsp;`. Un HTML5 sin entidades se lo tragaba
el analizador de XML, que perdona los errores, y devolvía un árbol casi vacío sin
protestar: un artículo de la Wikipedia de doscientas cuarenta mil letras se
quedaba en cuatrocientas.

La condición nueva mira **el espacio de nombres**, no el doctipo: un capítulo de
EPUB 3 también lleva `<!DOCTYPE html>` y tiene que seguir leyéndose como XML.
Solo se cambia de analizador si además **no** declara el espacio de nombres de
XHTML, que es lo que distingue una página guardada del navegador de un capítulo
de libro. Se comprobó sobre 1 831 capítulos de 63 EPUB reales: **ninguno** cambia
de analizador.

---

## Un cómic que se acaba antes de tiempo

`nucleo/descomprimir.py` tenía un fallo que no se veía y que era el peor tipo de
fallo de este programa: devolvía éxito con la mitad del contenido.

Ante un RAR partido en volúmenes, el descompresor que trae Windows saca las
páginas del primer volumen y termina **sin decir que se ha dejado el resto**. Ni
siquiera al listar el archivo las cuenta: un RAR de doce páginas partido en tres
se lista con cinco entradas. Comparar lo listado con lo extraído daba «completo».

Lo único que delata que falta algo es **que al lado hay más volúmenes**, así que
eso es lo que se mira. Y `extraer_detallado` ya no se para en el primer programa
que saque *algo*: se para en el primero que lo saque *todo*, y el primero que se
prueba es el 7-Zip que viaja en `data/bin`, así que el cómic se abre entero sin
depender de lo que haya instalado. El aviso de que falta media historieta sigue
escrito y sigue saliendo **en la primera línea del documento** —antes de la
primera página, porque al final solo lo leería quien haya llegado hasta allí—
para el caso que quede: un volumen que de verdad no esté en la carpeta.

---

## Motores de voz: el contrato no se inventó, ya estaba escrito

`nucleo/motores_voz.py` deja añadir voces al programa como paquete. Lo que hace
que esto funcione no es el código: es **de dónde salió el contrato**.

Un motor tiene que saber hacer quince cosas. No se eligieron pensando en un
sistema de complementos: son, letra por letra, **lo que el lector en voz alta ya
le pedía a la voz de Windows** desde el primer día. Se miró qué llamaba
`lectura_voz.py`, se escribió eso en una lista y ese fue el contrato.

La consecuencia es la que se buscaba: admitir motores nuevos **no cambió ni una
línea de la lectura**. Ni el paso de frase, ni el cambio de voz por idioma, ni
el tono de los diálogos, ni el temporizador. Y la primera comprobación que se
hizo fue pasarle el contrato a la clase de siempre, que lo cumplió sin tocarla.

Un contrato inventado a la vez que el sistema de complementos habría salido más
elegante y habría obligado a reescribir lo que ya funcionaba.

### Lo que el programa deliberadamente no sabe

Qué ajustes tiene un motor. No los conoce y no debe conocerlos: si los
conociera, añadir un motor obligaría a tocar el diálogo de la voz, y entonces
esto no sería un sistema de paquetes sino una lista de motores admitidos.

Lo que hace es preguntar. Cada paquete declara sus ajustes en su manifiesto
—clase, límites, valor de fábrica— y el diálogo los pinta. Eloquence declara
trece; las voces de Edge, cuatro; la de Windows, ninguno.

**Y declara también su explicación de Control+F1.** Un manifiesto con un ajuste
sin explicación se rechaza al instalarlo, y eso no es rigidez: en este programa
cada control se explica, y quien lo maneja no ve la pantalla. La explicación la
tiene que escribir quien hizo el motor, que es quien sabe qué hace.

### Por qué la voz de Windows no se puede desinstalar

Porque es el suelo del que el programa no se cae. Si el motor elegido no está,
no arranca o no cumple el contrato, se vuelve a ella **y se dice en una frase**.

Quedarse mudo sería lo peor que puede pasar en un lector de libros: quien no ve
la pantalla no puede distinguir entre «el programa se ha colgado» y «la voz no
arranca», y las dos cosas se arreglan de manera distinta.

### El fallo que apareció al meter la primera voz lenta

El lector daba una frase por terminada si a las tres décimas no había empezado a
sonar. Con la voz de Windows sobraba: SAPI arranca en décimas.

Una voz neuronal tarda **casi cinco segundos** en la primera frase: genera el
sonido entero antes de reproducirlo y encima levanta su motor. Con el margen de
siempre, el lector daba cada frase por terminada a las tres décimas y saltaba a
la siguiente: **se saltaba el libro entero, sin un error, sin un aviso**.

Ahora el margen lo declara el motor, que es el único que lo sabe. Y mientras se
espera se avisa —un pulso corto cada segundo y pico, y a los dos segundos y medio
una frase—, porque cinco segundos de silencio después de pulsar «leer» tampoco
se distinguen de un programa colgado.

### Compilados, y lo que eso cuesta

Los paquetes llevan bytecode, no código fuente. Siguen siendo un ZIP que
cualquiera puede abrir para ver qué archivos trae —eso hay que poder hacerlo
antes de instalar código que va a ejecutarse— pero el código no se lee de un
vistazo.

El precio es real y conviene tenerlo escrito: **el bytecode va atado a la
versión de Python**. Un paquete de 3.15 no lo carga 3.16, y no a medias: no
carga. Por eso el manifiesto declara con qué versión se compiló y el instalador
lo comprueba **antes de copiar nada**, diciéndolo en una frase que se entiende.
Al actualizar Python hay que rehacer los paquetes.

### Cada motor con sus propios nombres

Dentro de un paquete, todos los módulos llevan el prefijo de su motor:
`eloq_engine`, `glocal_bridge`, `edgeol_catalog`, `esp_rutas`. No es cosmética.

Los motores vienen de otra aplicación donde cada uno vive en su carpeta, así que
dos pueden tener un `provider.py` sin estorbarse. Aquí cada paquete es una
carpeta plana, y con nombres iguales el segundo en cargarse taparía al primero:
se vería como que las voces de un motor salen con el nombre de otro, que es la
clase de fallo que parece funcionar.

El constructor pone los nombres y **reescribe las importaciones solo**. Los
módulos que se traen no se editan a mano nunca: así se pueden volver a traer
cuando cambien en su origen.

### Los nueve paquetes, y de dónde sale cada uno

Eloquence son bibliotecas de IBM de los noventa; el motor local de Google es de
Google; eSpeak sale de una instalación de NVDA. **Ninguno se puede redistribuir
alegremente**, y meterlos en el repositorio sería justo eso.

Así que en el repositorio está el **adaptador** de cada uno —unas doscientas
líneas propias que traducen entre lo que el visor pide y lo que ese motor sabe—
y `plugins_voz/crear_paquetes.py`, que arma el paquete con los binarios de quien
tenga derecho a usarlos.

Los nueve cubren cosas distintas a propósito: eSpeak y Eloquence para leer
deprisa, MBROLA y las neuronales para escuchar bien, y de las neuronales dos sin
conexión —Piper y la de Google— y una por internet, porque no todo el mundo
puede permitirse que lo que lee salga de su equipo. Core y RHVoice están porque
no cuestan nada: uno enseña voces que Windows ya tiene y esconde, y el otro es
libre entero.

### Voces que se añaden copiando una carpeta

Vocalizer trae tres voces dentro y admite las que se le echen. El adaptador le
pasa **cada subcarpeta de `voces`** y él decide cuáles reconoce: quien sabe si
una carpeta es una voz es él, y adivinarlo desde fuera solo serviría para dejar
alguna fuera. Con eso, añadir una es copiarla ahí, y quitarla es borrarla.

Las carpetas se llaman `spe_jorge_premium-high` —idioma, voz y calidad—, que sale
del nombre del propio archivo de Nuance quitándole la versión. A Vocalizer el
nombre de la carpeta le da igual, y está comprobado renombrando una y viendo que
la detecta igual; se aprovecha para que diga algo y para que las tres que vienen
sirvan de plantilla a quien añada la cuarta.

La carpeta va declarada en `conservar`, así que actualizar el paquete no se lleva
por delante lo que se haya añadido. Y hay un ajuste para apuntar a otra carpeta
del disco, por si alguien ya las tiene en otro sitio y no quiere duplicar gigas.

Es, con diferencia, el paquete más grande: setecientos once megas con las tres
voces. `herramientas/vocalizer.py --sin-voces` prepara solo el motor, que son
once.

### Un ajuste que no hace nada no protesta

`herramientas/revisar_motores.py` compara lo que un paquete promete con lo que
hace. Un motor declara sus ajustes en un archivo y los usa en otro, y nada obliga
a que coincidan: se añade uno al manifiesto y se olvida leerlo, o se lee uno que
nadie declaró. Las dos cosas fallan calladas —el ajuste sale en la ventana, se
mueve, se guarda, y no llega a ninguna parte— y solo se descubren sospechando.

La primera pasada encontró siete de verdad: dos ajustes de Edge y uno de Google
que solo existían en el manifiesto, una variante de Eloquence que el motor leía
y nadie podía tocar, y las calidades de Vocalizer. Ninguno se veía usando el
programa.

También enseñó algo del propio detector: buscar `self._ajustes.get("clave")` no
basta, porque los motores leen de muchas formas —`self._entero("frecuencia", 22)`,
o pasando los ajustes enteros a un proveedor que los lee en otro archivo—. Ahora
mira si la clave aparece como texto en cualquier archivo del motor, que es lo que
distingue un ajuste vivo de uno huérfano. Y en Core se cambió una clave que se
armaba a trozos (`"usar_" + catalogo`) por las tres escritas enteras: funcionaba,
pero una clave que no aparece escrita no se puede comprobar.

### Opciones que solo el motor sabe

El manifiesto es fijo y hay ajustes que no lo son. Vocalizer ofrecía siete
calidades de voz cuando las voces instaladas solo tienen una, y eso no es un
descuido: las calidades dependen de las voces, y las voces se copian **después**
de armar el paquete.

Por eso un motor puede tener `opciones_de(clave)` y decir en marcha qué hay de
verdad. Es opcional —el que no lo tenga sigue usando las de su manifiesto— y la
ventana ya construye el motor para listar sus voces, así que preguntárselo no
cuesta nada. El manifiesto se queda como respaldo para cuando el motor no ha
podido arrancar.

Un detalle de orden que hubo que corregir: al cambiar de motor, la ventana
pintaba sus ajustes **antes** de construirlo, así que las listas salían con lo
del manifiesto aunque el motor supiera más. Ahora se construye primero.

### La compilación que se reparte va sin paquetes

Los nueve paquetes juntos son ochocientos setenta megas. Con ellos dentro, lo que
se distribuye pasa del gigabyte, y quien instale el programa se baja casi un giga
de voces que quizá no use ninguna —y se lo vuelve a bajar en cada actualización—.

Por eso la opción de compilar del menú, que es la que además hace el ZIP y el
`version.json`, pone `VISOR_SIN_PAQUETES_VOZ` y `setup_cx.py` deja la carpeta
fuera: 371 megas en vez de 1,3 gigas. Los paquetes se reparten aparte y se
instalan desde el propio programa.

Lo que **sí** se queda dentro son los noventa y ocho módulos de Python que los
motores declaran necesitar. Tienen que ir aunque los paquetes no vayan: si no, un
motor instalado después arrancaría diciendo que le falta un módulo, que es
exactamente el fallo que costó descubrir la primera vez.

Dos cosas que se aprendieron probándolo, y que están en el código porque fallan
en silencio:

- La **frecuencia** no es un ajuste que la voz obedezca: es un dato suyo. Las
  premium están grabadas a 22 kHz y pedirles 11 hace que acepten el parámetro y
  luego fallen al sintetizar con «estado incorrecto», sin una palabra y sin
  explicación. Ahora se lee la frecuencia real de cada calidad y solo se usa la
  pedida si esa voz la tiene.
- La **lista de rutas** que se le pasa hay que guardarla en el objeto. La
  biblioteca se queda con el puntero, y si el recolector se lleva el array antes
  de tiempo, lo que lee después es basura.

### Las voces neuronales de Microsoft, y lo que costó que sonaran

Son las mismas voces de Edge, pero generadas dentro del equipo. Van por
`cffi` contra ocho bibliotecas de Microsoft, y lo que se les manda es SSML: de
ahí salen el tono, el estilo y su fuerza, que las demás voces no tienen.

Tres cosas hicieron falta para que sonara una sola frase, y las tres fallan
calladas:

- **La licencia va junto a cada voz**, no en un sitio común. Cada una se
  reparte con la suya, en un `SynthModel.license` en su raíz —la carpeta que
  tiene el `data` dentro—. Se admite además una sola para todas en la carpeta
  `licencia`, para quien la tenga así.
- **Una clave no se pasa igual que una licencia.** Si el archivo es un
  `SynthModel.key`, hay que anteponerle `Key:` al contenido. Sin eso, una clave
  correcta se rechaza.
- **Una voz se reconoce por su `Tokens.xml`**, que es lo que la biblioteca
  busca de verdad. Buscar carpetas llamadas `data` colaba cualquier cosa.

Sin la clave, la biblioteca no revienta: acepta el texto, devuelve cero bytes
de sonido y deja en el registro un `Protobuf parsing failed` que solo se ve si
alguien mira. Desde la ventana eso era pulsar «Probar» y que no pasara nada.
De ahí sale el `problema()` opcional del contrato, que sirve para todos.

Y una cuarta, la peor, que solo se ve compilado: **nada de esto se puede llamar
desde el hilo de la interfaz**. En el ejecutable, pulsar «Probar» cerraba la
aplicación en seco —sin excepción, sin traza, el registro cortado a media
línea—. Windows sí lo apuntaba, y ahí estaba todo: violación de acceso
(`0xC0000005`) dentro de `...extension.embedded.tts.dll`, y detrás
`0xC000041D`, que es la que lanza cuando una excepción escapa por una llamada de
retorno. El controlador de NVDA del que sale esto —que corre congelado igual que
nosotros— nunca llama a la síntesis desde el hilo principal: la mete en una cola
que atiende un hilo suyo, y ahí captura toda excepción. Este motor hace lo
mismo, y `decir` pasó de tardar 0,34 s en devolver a no tardar nada.

Y la causa de fondo, que costó cuatro rondas y no estaba ni en el motor ni en el
programa. El equipo tenía instalado **NaturalVoiceSAPIAdapter**, que ofrece las
voces neuronales como voces SAPI 5 y trae su propia copia del SDK de Microsoft
Speech: la 1.41.1, con ONNX Runtime 1.15.1. La nuestra es la 1.51.1, con ONNX
Runtime 1.23.2. Windows resuelve una DLL pedida por su nombre devolviendo **la
primera que ya esté cargada con ese nombre**, sin mirar de dónde salió; y la del
adaptador entra en el proceso en cuanto se prepara la voz del sistema, que es lo
primero que hace el programa. Así que nuestra `embedded.tts.dll` pedía la API 23
de ONNX Runtime y recibía una que solo llega a la 15:

```
The requested API version [23] is not available, only API versions [1, 15]
are supported in this build. Current ORT Version is: 1.15.1
```

Y eso no es un error que se pueda capturar: es una violación de acceso que se
lleva el proceso entero.

Se ve enumerando los módulos del proceso con `Get-Process`: aparecen dos juegos
completos del SDK, uno en `C:\NaturalVoiceSAPIAdapter\x64` y otro en
`data/motores/neural/speechapi`. De ahí sale el mecanismo de **precarga**: un
paquete declara en `precargar` qué bibliotecas necesita, y `main.py` las mete en
el proceso antes de tocar nada de voz. Cuesta unas centésimas y gana la carrera.

El precio es que dos versiones de la misma biblioteca no caben en un proceso:
mientras el motor esté instalado, el adaptador pierde las suyas —en este equipo,
las dos voces `(Natural)` de su lista SAPI, que son las mismas que el motor ya
da mejor— y deja un `0xC0000139` capturado al enumerar. Sin efectos colaterales
solo se puede con la biblioteca en un proceso aparte, como el puente de 32 bits.

Antes de dar con esto se probaron y descartaron, con el ejecutable compilado en
la mano: el desemparejamiento del runtime de C++, COM en apartamento único, los
descriptores de salida inválidos sin consola, crear el motor dos veces,
reinstalarlo en marcha, y los 45 cruces de velocidad, tono y volumen. Ninguno
era. Lo que sí salió por el camino y se quedó es que el hilo de la voz declare
su apartamento con `CoInitializeEx(NULL, COINIT_MULTITHREADED)`: es lo que hace
el controlador de NVDA del que sale esto, y evita que sus llamadas de COM
crucen al hilo de la ventana.

La otra mitad del mismo problema es el orden al soltar. El envoltorio engancha
una llamada de retorno al crear la salida de sonido y la desengancha en su
`__del__`; si el recolector se lleva la salida antes que el sintetizador, la
biblioteca se queda apuntando a un contexto liberado. Por eso `cerrar` los
suelta uno a uno, con un `gc.collect()` entre medias: primero quien llama,
después lo llamado, y al final la configuración.

Y algo que se descubrió persiguiendo esto y vale para todo el programa: **una
biblioteca que no es de Python puede tirar el proceso y no dejar rastro**. No
hay excepción que capturar, no da tiempo a escribir en el registro y la ventana
desaparece. Por eso ahora se engancha `faulthandler` al arrancar, con su archivo
en `data/logs/caida_<fecha>.txt`: cuando el proceso se cae, ahí queda escrito en
qué estaba cada hilo, con la pila de Python y la de C. Lo que Windows apunta en
el visor de eventos da el módulo y el desplazamiento; esto da la línea.

Se comprobó provocando una violación de acceso a propósito desde un hilo, que es
lo más parecido a lo que hace una biblioteca al estrellarse. También se le ponen
al proceso salidas válidas al arrancar —`nul` detrás de los descriptores 1 y 2
si no valen—, porque un ejecutable de ventana no tiene consola y hay
bibliotecas que escriben ahí sus avisos sin preguntar.

Y una quinta que no es de la biblioteca sino de cómo se reparte: **el paquete
lleva las voces dentro**. Ciento veinticinco megas, pero un motor de voz que se
instala sin voces arranca, no lista nada y no dice por qué; y quien lo instala
no tiene de dónde sacarlas.

De los que llevan binarios de fuera, cuatro se preparan con su herramienta, como
Tesseract y 7-Zip: `herramientas/espeak_mbrola.py` baja eSpeak NG oficial,
MBROLA de 64 bits y las siete voces españolas, y `herramientas/piper.py` baja el
programa de Piper, su catálogo de ciento setenta y seis voces y una española.
`herramientas/vocalizer.py` saca del controlador de NVDA la parte de 64 bits del
motor de Nuance —la de 32 no sirve— y sus datos comunes, y
`herramientas/neural.py` la biblioteca de voz de Microsoft y las siete voces con
su licencia, comprobando voz por voz que la traiga: una voz sin clave viaja
igual y no suena. Las cuatro **comprueban que suena** antes de dar nada por
bueno.

### Reunir y armar, que son dos cosas

`plugins_voz/fuentes/<motor>` tiene **todo** lo que hace falta para armar ese
paquete: el código, los datos, las bibliotecas y los binarios. Armar no necesita
nada más —ni la otra aplicación, ni NVDA, ni conexión—:

```bash
python plugins_voz/crear_paquetes.py --reunir   # trae las piezas, una vez
python plugins_voz/crear_paquetes.py            # saca los .motorvoz
```

**Con el Python del entorno, no con el del sistema.** Un paquete lleva su código
compilado y apunta para qué versión de Python está hecho; el programa rechaza el
que no coincida. Armarlos con otro Python no falla en ninguna parte: salen los
diez, con su tamaño y su resumen, y no cargan. Eso pasó una vez y se descubrió
instalándolos, así que ahora la herramienta compara su intérprete con el del
entorno y se planta antes de armar nada.

Antes eran un solo paso, y eso ataba armar un paquete a tener a mano los cuatro
orígenes distintos de donde salen las piezas. En este equipo están todos, y por
eso funcionaba; en otro, o dentro de un año, no armaba nada.

Los módulos que se traen de fuera se guardan **tal como vienen**. Las
importaciones se reescriben al armar, que es cuando se sabe qué prefijo lleva
cada uno: guardarlos ya reescritos haría imposible volver a traerlos cuando
cambien en su origen. `plugins_voz/fuentes/LEEME.md` cuenta el reparto y, lo que
más importa, **qué se puede repartir y qué no**: Eloquence y el motor de Google
son de otros.

### Eloquence busca su ECI.INI donde le digan, no donde uno cree

Dos cosas separadas que juntas daban un fallo difícil de leer: Eloquence sonaba
en un equipo solo mientras hubiera **otro** programa con Eloquence instalado y
activo.

* **Las rutas de las voces son absolutas.** `ECI.INI` trae una línea `Path=` por
  idioma con la ruta completa de su `.syn`, y esa ruta es la del equipo donde se
  preparó el paquete. `assets.update_eci_ini` la reescribe: de cada línea
  conserva **solo el nombre del archivo** y le pone delante la carpeta desde la
  que se arranca en ese momento. Se hace al activar el motor —no al instalarlo—
  porque la carpeta puede cambiar entre una vez y otra: un visor portátil en un
  lápiz de memoria es hoy la unidad E y mañana la G.
* **Y ECI decide por su cuenta qué `ECI.INI` lee.** Lo busca por el nombre que
  le diga la variable de entorno `ECIINI`, y solo si no está recurre a lo que
  encuentre. Sin ponerla, en un equipo con otro Eloquence instalado la
  biblioteca podía leer el `ECI.INI` de ese otro programa, que apunta a **sus**
  voces: por eso el motor solo sonaba mientras ese programa estaba, y por eso
  parecía que dependía del lector de pantalla. Ahora `assets.eci_environment`
  la pone y el proceso de 32 bits arranca con ella.

Debajo de las dos queda una red: el paquete se arma con los nombres de las voces
**a secas**, sin ninguna ruta (`completar_eloquence`, en `crear_paquetes.py`).
El proceso de 32 bits arranca siempre con la carpeta de las voces como
directorio de trabajo, así que un nombre suelto se resuelve solo aunque el
`ECI.INI` no se haya podido reescribir —una instalación de solo lectura— y
aunque la carpeta lleve caracteres que no quepan en la página de códigos ANSI,
que es lo único que ECI entiende.

### Un motor que toca Windows

`nucleo/sistema_motores.py`. Ninguno de los ocho lo hace, y esa es la razón de
que el programa se pueda llevar en un lápiz de memoria. Pero los hay que no
pueden: algunos sintetizadores buscan la lista de sus voces en el registro y no
arrancan sin ella.

El paquete lo declara en su manifiesto —`sistema.registro`, con la rama y el
porqué— y el programa se encarga del resto: lo dice en el aviso previo con la
rama entera escrita, apunta qué existía ya antes de tocar nada, y al quitar el
motor borra lo que puso, subiendo por las claves padre que se queden vacías.

Tres decisiones que hacen que esto sea seguro:

- **Solo `HKCU`.** La rama del equipo necesitaría administrador y valdría para
  todas las cuentas. Se rechaza, igual que las ramas de Windows y cualquiera con
  menos de dos niveles: con `Software` a secas un paquete estaría pidiendo
  permiso para borrar media configuración al desinstalarse.
- **Se apunta qué había antes.** Si quien instala ya tenía ese motor por su
  cuenta, esa rama no es nuestra. Sin esto, quitar el motor le destrozaría su
  instalación.
- **Borra el programa, no el motor.** Un motor que se quita porque da problemas
  es justo el que no se puede cargar para pedirle que se limpie solo. Con lo
  declarado basta para deshacerlo sin ejecutar una línea suya.

Las pruebas de esto escriben en el registro de verdad y le preguntan a Windows
si quedó algo, porque preguntárselo a la función que borra no comprueba nada.

### Qué pone el programa y qué trae el paquete

La regla es corta: **la biblioteca estándar de Python la pone el programa; todo
lo demás lo trae el paquete dentro**. El de Edge viaja con su propio `aiohttp` y
su propio `certifi` en una carpeta suya que él mismo pone en la ruta de
búsqueda. La única excepción son las cosas que el visor ya usa por su cuenta
—`comtypes`, `basskit`—, que están porque el programa las necesita.

Y del lado de lo estándar hay una trampa que costó descubrir: al compilar con
cx_Freeze **no va entera**, se incluye lo que el analizador ve importado, y un
motor que se carga en marcha desde un archivo externo no lo mira nadie. El de
Google necesita `http.server` y el de Edge `http.cookies`, y ninguno de los dos
estaba: los dos funcionaban en desarrollo y fallaban compilados.

Por eso cada paquete declara en su manifiesto, en `necesita`, los módulos que
importa su propio código —lo calcula el constructor leyendo el árbol de sintaxis
al armarlo— y `setup_cx.py` lee los manifiestos de `plugins_voz` y le pide a
cx_Freeze lo que sea estándar. Lo de terceros que aparezca ahí se deja fuera a
propósito y no solo porque sobre: cx_Freeze sigue las importaciones de lo que se
le pide y se para en la primera que no resuelva, así que un motor de un tercero
que mencionara algo raro dejaría el visor entero sin poder compilarse.

---

## JB2: por qué la máscara de un DjVu vale más que la fotografía

`formatos/jb2.py` descomprime la capa en blanco y negro de una página de DjVu.
Se escribió para un caso concreto: un DjVu **sin** capa de texto no se podía
leer de ninguna manera, porque para reconocerlo hacía falta la página como
imagen y no había forma de sacarla.

Lo que sorprende es que la máscara sea **mejor** para reconocer que la
fotografía en color de la misma página. Un DjVu guarda cada página en tres
capas: la máscara —el texto y los dibujos de línea, un bit por píxel— y el fondo
y el primer plano en color, que son el papel amarillento y las manchas. La
máscara es lo que el compresor ya separó del papel al digitalizar, así que
llega al reconocedor limpia y sin el paso de binarizar, que es justo donde un
OCR pierde las letras finas. Por eso este módulo no escala nada ni prepara la
imagen: viene mejor de lo que la dejaríamos.

Va sobre el codificador ZP que ya estaba escrito para el BZZ del texto, y eso
recorta el trabajo a la mitad: JB2 no es otro compresor, es otro **modelo**
encima del mismo. Lo que cambia son los contextos con los que se le pregunta.

Los sitios donde cuesta, y cómo se ven:

- **Las filas van de abajo arriba.** Darles la vuelta parece inofensivo porque
  el mapa sigue teniendo el tamaño bueno; lo que sale es ruido, porque el
  contexto de un píxel son sus vecinos de *arriba*.
- **El codificador de números construye un árbol sobre la marcha.** No es una
  tabla: cada decisión baja a un hijo que puede no existir todavía. Así el
  modelo aprende los desplazamientos que de verdad aparecen —de una letra a la
  siguiente son casi siempre los mismos tres o cuatro— sin gastar en los demás.
- **Un registro concreto se lee distinto en una página y en un diccionario.** La
  forma que solo va a la biblioteca, dentro de una página, se queda en blanco:
  DjVuLibre no lee ahí sus diferencias. Parece un descuido y probablemente lo
  sea, pero su compresor escribe exactamente eso, así que leerlas sería leerlas
  donde no están y perder el resto del archivo.

**Cómo se comprueba que está bien.** Que no reviente no dice nada: una máscara
con las columnas desplazadas dos píxeles pasa cualquier comprobación de tamaño.
La prueba de aceptación reconoce la página descomprimida y la compara con el
texto que el propio archivo lleva dentro, que es la respuesta buena escrita por
quien lo digitalizó. Sobre una página desplazada o invertida un OCR no acierta
ni una palabra.

Lo que **no** se hace son las dos capas de color, que van en ondículas. Una
página que sea solo una lámina fotográfica no tiene máscara y se queda sin
sacar; en un libro de texto son una de cada cincuenta.

---

## IW44: por qué también hacen falta las capas de color

`formatos/iw44.py` descomprime el fondo y el primer plano de una página de DjVu.
Para el texto no hacen falta —la máscara ya lo trae, y más limpio—: hacen falta
para lo que **no** está en la máscara. Una lámina fotográfica no tiene ni una
letra en blanco y negro, así que sin esto la página no existía: ni texto que
leer ni imagen que ver ni nada que mandar a describir.

El formato no guarda píxeles: guarda la imagen **descompuesta en escalas**.
Primero una versión diminuta y después, para cada paso de ampliación, solo el
detalle que hay que añadir. En una fotografía casi todo ese detalle es cero, y
ahí está el ahorro. Encima va un refinamiento por pasadas: la primera deja la
imagen reconocible y las siguientes le añaden precisión, así que un archivo
cortado por la mitad da una imagen borrosa y no media imagen. Por eso una página
trae cuatro o cinco trozos `BG44` seguidos y hay que dárselos todos, en orden y
al mismo descodificador: empezar de cero en cada uno daría una imagen plana.

Es el **tercer** formato que se apoya en el codificador ZP escrito para el BZZ
del texto, después del JB2 de la máscara. Esa es la razón de que quepa en lo que
cabe: lo difícil estaba escrito, y lo que cambia entre los tres es el modelo con
el que se le pregunta.

Dos detalles que costaron una tarde cada uno:

- **En blanco y negro el valor va invertido.** El formato guarda cuánta tinta
  hay, no cuánta luz, así que el píxel es `127 - valor` y no `valor + 128`.
  Confundirlo da la imagen en negativo, y eso **no se nota** en una página de
  texto casi vacía: se nota en la primera lámina, que sale negra.
- **El color va en YCbCr con la transformada de Pigeon**, no con la del JPEG. Se
  parecen lo justo para que una foto salga reconocible y con los colores
  cambiados, que es la peor manera de equivocarse.

---

## Las imágenes de un `.hlp`: lo que cuesta no es descomprimirlas

`formatos/hlp.py` saca los mapas de bits de un archivo de ayuda. Descomprimirlos
es lo fácil: son mapas de bits de Windows con una compresión de dos jugadas
—copiar tantos o repetir uno tantas veces— y unos enteros de longitud variable.

Lo que cuesta es **saber dónde va cada una**. El formato no lo dice de frente:
los mandatos que colocan una imagen están mezclados con los de formato de
letra, y para llegar a ellos hay que atravesar los ajustes del párrafo, que la
propia documentación del formato describe como «difíciles de describir» porque
la mitad de sus campos solo están si un bit de más arriba lo dice. Se leen campo
a campo comprobando la condición, que es la única manera, y contando los
mandatos se sabe **detrás de qué trozo de texto** iba la imagen.

Se podía haber puesto todas al final del tema y ahorrarse eso. No se ha hecho
porque en un manual de 1993 la frase y la captura que la acompaña se leen juntas
o no se entienden: «pulse el botón [imagen] para seguir» con la imagen al final
del capítulo no dice nada.

---

## Repasar una traducción automática sin hablar el idioma

Francés, italiano y portugués están traducidos a máquina, y no se pueden repasar
a mano: son tres mil cuatrocientas cadenas por idioma. Pero **una parte del
repaso sí se puede automatizar**, y es justo la parte donde una máquina se
equivoca sin que se note.

Una máquina traduce bien las frases. Con lo que se estrella es con lo que no
sabe que es un término, y aquí hay dos clases:

- **Palabras corrientes que además son términos.** Los nombres de las notas son
  el caso extremo: «la» y «si» también son artículo y conjunción, «mi» es un
  posesivo y «do» es el verbo «hacer» en inglés. Salieron «faire», «le» y
  «Ouais». Un compás que en español dice «do negra» quedaba en francés como
  «faire noir»: «hacer negro».
- **Nombres propios que parecen palabras.** «DAISY» pasó a ser la flor
  —*Margherita*, *Marguerite*, *Margarida*—, «Gemini» pasó a ser el signo del
  zodiaco, «Claude» pasó a ser Claudio, «Markdown» se leyó como una rebaja de
  precio y «Tesseract» quedó en «Tesserato».

`herramientas/revisar_traducciones.py` comprueba cinco cosas que se pueden
comprobar sin saber el idioma: que los nombres propios sigan ahí, que las siglas
de los formatos no se hayan traducido —«PEF» pasó a «FEP» en francés, y eso
estaba dentro del filtro de archivos del diálogo de guardar—, que los marcadores
de formato sean los mismos, que las teclas de los atajos no cambien y que el
vocabulario musical siga un **glosario** fijo por idioma.

El glosario no es una traducción palabra a palabra: es el término de cada
tradición. Una «redonda» es *ronde* en francés pero *semibreve* en italiano y en
portugués, porque una tradición nombra la figura por su forma y la otra por su
duración. Eso no lo puede acertar un traductor general.

**Lo que la herramienta encontró y no se buscaba** fue lo más grave: en la ayuda
de la opción de volcar tablas, las tres traducciones **se cortan a media frase**,
justo donde el original explica con qué tecla se abre la tabla aparte. El
traductor se atascó en «Control+Shift+T» y se dejó el resto del párrafo. Quien
leyera esa ayuda en francés se quedaba sin saber lo que había ido a mirar.

Lo que **no** comprueba es si una frase suena natural. Eso sigue queriendo una
lectura de quien hable el idioma, y por eso sigue anotado en `MEJORAS.md`. La
herramienta está para que ese repaso no tenga que empezar por lo evidente.

---

## LZX: cuatrocientas líneas que no cambian nunca

`formatos/lzx.py` descomprime el algoritmo con el que van los archivos de ayuda de
Windows. Se escribió entero porque las alternativas eran peores: depender de que
el usuario tenga 7-Zip, o traerse una biblioteca en C que habría que compilar para
cada versión de Python. El formato está cerrado desde 1997, así que es código que
se escribe una vez.

Los tres sitios donde es fácil equivocarse, y cómo se ven:

- **La ventana sobrevive a los reinicios.** En un punto de reinicio se ponen a
  cero las distancias recientes y los árboles, pero **lo ya descomprimido sigue
  estando**. Tirarlo da «apunta fuera de la ventana» en el tercer bloque.
- **El flujo de bits se realinea al final de cada trozo de 32 KB.** Sin eso, los
  primeros treinta y dos kilobytes salen **perfectos** y lo que sigue es basura.
  Es el fallo más difícil de ver de todo el formato, porque parece que funciona.
- **El tamaño de ventana está en el desplazamiento 0x10 de `ControlData`, y el
  intervalo de reinicio en el 0x0C.** Leerlos al revés da un árbol principal con
  el número de símbolos equivocado y no se descomprime ni el primer bloque.

Se comprobó contra un archivo de ayuda real: **291 de 291 archivos internos
idénticos byte a byte** a lo que extrae 7-Zip, en dos décimas de segundo.

---

## Buscar en todos los libros sin montar ningún índice

`nucleo/biblioteca.py` busca abriendo cada libro de la caché. Un índice invertido
sería más rápido a la décima búsqueda, pero habría que mantenerlo, ocuparía tanto
como los libros y quedaría desfasado en cuanto se cambiara un ajuste de análisis.
Con la caché puesta, buscar en cuarenta libros ya analizados tarda un par de
segundos.

De ahí sale la doble velocidad que la ventana enseña: **lo ya analizado se busca
al instante** y lo que no se ofrece aparte, con su barra y su botón de detener.

## Una biblioteca de doscientos mil libros, y calibre

Hasta la 1.3.4 la biblioteca **no se guardaba**: al abrir la ventana se
recorrían otra vez todas las carpetas añadidas con `Path.rglob`, se consultaba
el disco por cada archivo para saber si seguía ahí (`os.stat` en el constructor
de cada `Libro`) y se metían las filas de una en una en una `wx.ListCtrl`. Todo
en el hilo de la ventana. Con trescientos libros no se notaba; con ciento
noventa mil en un disco de los de girar eran minutos con la ventana colgada, y
por eso había un tope de 5000 libros que cortaba la exploración sin decir nada.

Ahora son cuatro piezas:

- **`nucleo/biblioteca_datos.py`**: una base de datos SQLite propia,
  `data/config/biblioteca.db`, con las **fuentes** (carpetas y bibliotecas de
  calibre) y los **libros** con todos sus datos. Se explora una vez, al añadir
  o al actualizar; abrir la biblioteca es leerla. Cada libro guarda su ruta
  **relativa** a la fuente, así que si el disco cambia de letra basta con
  editar la ruta de la fuente. Lo que el usuario hace en cada libro (posición,
  marcadores, colección) sigue en `documentos.json`, que es lo que se
  sincroniza.
- **`nucleo/biblioteca_importar.py`**: trae libros en otro hilo, avisando de
  por dónde va y atento a que se le pida parar. Una carpeta se recorre con
  `os.scandir`, que en Windows trae el tamaño y la fecha en la misma llamada que
  lista, y de cada EPUB se leen solo el `container.xml` y el OPF. Al actualizar,
  lo que no ha cambiado de tamaño ni de fecha no se relee. Se escribe en tandas
  de 2000 filas en una transacción, con una firma de cada libro para distinguir
  lo nuevo, lo cambiado y lo igual.
- **Calibre se lee de su base de datos, no del disco.** Su `metadata.db` es
  SQLite y su esquema está en `resources/metadata_sqlite.sql` de calibre:
  `books` con sus tablas de enlace (`books_authors_link`, `books_series_link`,
  `books_tags_link`...), `data` con un formato por fila —el archivo es
  `<biblioteca>/<books.path>/<data.name>.<formato>`— y `custom_columns` con sus
  `custom_column_N` y `books_custom_column_N_link`. Se abre en **solo lectura**
  (`?mode=ro`) y, si no se puede, se lee una copia. Hay que registrar la
  colación `PYNOCASE` y las funciones que calibre añade a SQLite (`title_sort`,
  `uuid4`...): sus índices y disparadores las nombran y SQLite rechaza la
  consulta si no existen. Se lee por tramos de identificadores para no tener
  ciento setenta mil sinopsis en memoria a la vez.
- **`interfaz/listas.ListaVirtual`**: una `wx.ListCtrl` en modo `LC_VIRTUAL`.
  Solo sabe cuántas filas hay y pide el texto de las que se ven; para el lector
  de pantalla es la misma lista de Windows de siempre (la del Explorador), con
  su búsqueda por primeras letras.

Medido con una biblioteca real de calibre de 192.785 libros en un disco de
4 TB: importarla entera con todos sus datos, 21 segundos; actualizarla sin
cambios, 12; leerla al abrir la ventana, 1,7 segundos en segundo plano, con la
ventana parada como mucho 0,13 segundos; filtrar, 0,07 segundos. Recorrer la
misma carpeta como carpeta corriente son 14 segundos, y leer los metadatos de
cada EPUB, unos 10 milisegundos por libro.

Los grupos (autores, series, etiquetas...) van también en una lista virtual y
no en un desplegable: un desplegable de Windows con 65.000 autores tarda más de
cuatro segundos en llenarse, y la lista virtual, nada. Al agrupar se reparte la
biblioteca en un diccionario de una vez, de modo que elegir un grupo es mirar
el diccionario (3 milisegundos) y no recorrer la biblioteca.

### La bibliografía, sin abrir los libros (1.3.6)

`nucleo/bibliografia.reunir` abría y analizaba cada libro para sacar su
editorial y su año, en el hilo de la ventana y con un `wx.ProgressDialog` modal
que solo se refrescaba entre libro y libro. Analizar un EPUB ronda los 23 ms en
el mejor caso: con 192.785 libros, más de una hora con todo parado. Y la lista
se llenaba fila a fila.

Ahora la biblioteca ya guarda la editorial, la fecha y el ISBN (y, desde el
esquema 2 de `biblioteca.db`, la forma de cita de cada autor, sacada de
`authors.sort` de calibre o de `opf:file-as`), así que `reunir` va en tres
pasos: lo que sabe la biblioteca, sin abrir nada; para los libros sueltos
incompletos, solo los metadatos del EPUB (1,4 ms) o la caché; y abrir el libro
entero, solo si se marca la casilla. Con 193.878 libros son 2,5 segundos, en
otro hilo, y la lista es una `ListaVirtual` que monta la cita de las filas que
se ven.

La forma de cita de calibre solo se usa si lleva coma: hay bibliotecas
configuradas para copiar el nombre como orden, y «Karina M. Soto» no dice dónde
empieza el apellido.

---

## Sincronizar sin servidor

`nucleo/sincronizacion.py` no habla con nada: escribe en una carpeta que el
usuario ya sincronice por su cuenta. Al juntar dos equipos hay dos reglas y solo
dos:

1. **Libro por libro, gana el más reciente.** Cada libro guarda cuándo se tocó
   (`DatosDocumento.actualizado`), así que leer por la mañana en un equipo y por
   la tarde en otro deja bien los dos, en vez de que gane el último que cierre.
2. **Los marcadores se suman.** Perder un marcador que costó poner es peor que
   tener uno repetido, y los repetidos se reconocen porque ocupan el mismo sitio.

Las preferencias **no** se sincronizan, y es deliberado: la voz que hay en casa
puede no estar instalada en el trabajo.

---

## Revisar lo que escribimos

Había informe de accesibilidad para lo que se **lee** y no lo había para lo que se
**escribe**. `nucleo/revision_epub.py` abre el EPUB recién exportado y lo mira con
las mismas reglas que a cualquier otro: el envoltorio, los metadatos de la norma
de accesibilidad, el índice y sus anclas, los niveles de encabezado, las imágenes
sin alternativa y las tablas sin encabezados. Reutiliza `ColeccionHallazgos`, así
que se lee y se cuenta igual que el informe de los PDF.

La prueba que más vale de ese módulo es la que comprueba que **nuestra propia
exportación pasa todas las comprobaciones**; la segunda arma un EPUB roto a
propósito y comprueba que se cazan los siete fallos.

---

## Preparado para lo que viene

- **Descripción de imágenes con inteligencia artificial.** Cada imagen ya se
  registra con su marca, su descripción y la ruta del archivo dentro del EPUB,
  y `formatos.base.extraer_recurso()` devuelve sus bytes. El diálogo de imagen
  (`interfaz/dialogos/contenido.py`) es el punto donde encajaría el botón
  «Describir esta imagen».
- **Más formatos**: el registro de analizadores descrito arriba.
- **Lectura en voz alta**: `nucleo.navegacion` ya sabe segmentar el documento
  por líneas, párrafos y elementos.
- **Menú contextual dinámico**: el punto de enganche está en
  `PanelLectura._al_menu_contextual`. `navegacion.elementos_en_linea()` ya
  devuelve qué hay bajo el cursor (enlace, imagen, tabla), que es justo lo que
  ese menú necesita para ofrecer unas opciones u otras.

---

## Limitaciones conocidas

- **Los libros con protección anticopia (DRM) no se pueden leer**, ni de Kindle
  ni de Adobe: se avisa con un mensaje claro y no se quita ninguna protección.
- **De un DjVu se lee su capa de texto, no sus imágenes.** Es lo que hace falta:
  un DjVu de biblioteca lleva dentro el texto que se reconoció al escanearlo. Un
  DjVu que solo sean imágenes —sin capa de texto— se dice claramente, y para eso
  está el reconocimiento con OCR.
- **El braille contraído (grado 2) viene apagado, y acierta en nueve de cada
  diez palabras que hay que abreviar sobre la marcha.** En las que están en la
  lista de la norma y en sus variantes acierta en todas. Está medido contra los
  ejemplos del propio documento y los siete fallos están enumerados en la prueba.
  Para leer sirve; para algo que vaya a imprimirse conviene repasarlo.
- **El ajuste de línea viene desactivado**, igual que en el lector de
  referencia (`word_wrap: false`). Así una línea del control es un párrafo
  completo del libro: la flecha abajo avanza de párrafo en párrafo y el lector
  de pantalla lo lee entero. Con el ajuste activado (`Ctrl+Alt+W`) la flecha
  abajo avanza por líneas *visuales* y el párrafo se lee a trozos. Además, sin
  ajuste el control es unas cuatro veces más rápido al desplazarse. Para quien
  lee con la lectura continua del lector de pantalla, la tercera vía es
  **«Empezar cada frase en un renglón nuevo»** (`renglon_por_frase`): el
  renglón pasa a ser la frase, sin cambiar ni una posición del libro.
- **La negrita y la cursiva vienen desactivadas.** Aplicarlas obliga al control
  de texto de Windows a rehacer la disposición del párrafo por cada tramo
  (unos 3 ms cada uno), lo que en un libro con miles de cursivas se nota al
  desplazarse. Se pueden activar en Opciones; entonces se aplican solo
  alrededor del cursor, nunca en el párrafo donde está el cursor —aplicarlas
  ahí movería los renglones bajo el propio cursor— y solo cuando lleva medio
  segundo quieto. La consecuencia es que un párrafo al que se llega de un
  arrastre de la barra de desplazamiento puede quedarse sin su negrita hasta el
  siguiente salto. La vía definitiva sería cargar el texto y su formato de una
  sola vez en el control mediante RTF, como hace Paperback.
- **Los libros que marcan las cursivas con estilos CSS** (`<span class="cursiva">`
  en lugar de `<em>`) no las registran como tales. Es la misma limitación que
  tiene el lector de referencia.
- **En libros de más de tres millones de caracteres** (por encima de unas 1.500
  páginas) el texto se carga por tramos. La lectura y la navegación funcionan
  con normalidad —el tramo se recoloca solo al acercarse el cursor a un
  borde—, pero *Seleccionar todo* abarca únicamente el tramo cargado y la barra
  de desplazamiento representa ese tramo, no el libro entero. Para el libro
  completo está *Archivo → Exportar a texto*.
