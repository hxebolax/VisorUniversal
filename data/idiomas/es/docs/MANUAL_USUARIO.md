# Manual del Visor Universal

Un lector de documentos hecho para leer de oído y con los dedos. Abre
veinticuatro familias de formatos, deduce la estructura de los que no la traen y
exporta a braille, a DAISY y a audio.

> **Este manual es corto a propósito.** Cuenta **qué hace cada cosa y con qué
> tecla**. Lo demás está donde se consulta mejor:
>
> - **`Control+F1`** sobre cualquier control de cualquier ventana explica ese
>   ajuste: qué es, qué consigue y qué conviene poner. Está escrito para los
>   doscientos y pico controles del programa, así que aquí no se repite.
> - **`Mayús+F1`** enseña **todas** las teclas, generadas del propio programa,
>   así que nunca están desfasadas.
> - **`NOVEDADES.md`** cuenta qué cambió en cada versión, y **`LEEME.md`**, por
>   qué está hecho así.
> - **`CREAR_MOTOR_DE_VOZ.md`**, en esta misma carpeta, explica paso a paso cómo
>   hacer un paquete de voz. Es para quien programe.

## Índice

1. [Empezar](#1-empezar)
2. [Leer y moverse](#2-leer-y-moverse)
3. [Varios documentos a la vez](#3-varios-documentos-a-la-vez)
4. [La biblioteca](#4-la-biblioteca)
5. [Buscar, marcar y estudiar](#5-buscar-marcar-y-estudiar)
6. [Imágenes, tablas, notas y fórmulas](#6-imagenes-tablas-notas-y-formulas)
7. [PDF y documentos escaneados](#7-pdf-y-documentos-escaneados)
8. [Libros DAISY](#8-libros-daisy)
9. [Leer en voz alta](#9-leer-en-voz-alta)
10. [Inteligencia artificial](#10-inteligencia-artificial)
11. [Opciones y perfiles](#11-opciones-y-perfiles)
12. [Exportar: braille, DAISY y audio](#12-exportar-braille-daisy-y-audio)
13. [Lo que el programa guarda](#13-lo-que-el-programa-guarda)
14. [Si algo va mal](#14-si-algo-va-mal)
15. [Las teclas](#15-las-teclas)

---

## 1. Empezar

Al abrir un documento oirás un tono ascendente, el título, el autor y por dónde
vas. **Se recuerda dónde lo dejaste** en cada uno.

La **primera vez** se ofrece un recorrido guiado que enseña las teclas de una en
una y deja probarlas ahí mismo. Queda en **Ayuda → Recorrido guiado**, y a partir
de entonces pregunta **qué parte** quieres repasar, para no atravesar dieciséis
pantallas por una tecla.

**Ayuda → Practicar** va un paso más allá: propone ejercicios cortos sobre el
documento que tengas abierto —«ve al tercer encabezado», «pon un marcador»,
«busca esta palabra»— y avisa en cuanto salen. La ventana no es modal: vuelves al
texto con `F6`, lo haces y el programa te avisa. Da igual cómo lo hagas; lo que
se mira es el documento, no las teclas.

**Una sola copia a la vez:** abrir el programa estando ya abierto trae al frente
la ventana que había y le pasa lo que pidieras abrir.

**Mientras no hay ningún documento abierto**, el cuadro de lectura enseña un
resumen de lo que se puede hacer y con qué tecla, y se recorre con las flechas
igual que un libro. Cuando ya te sepas las teclas puedes quitarlo en
`Opciones → Personalización`, desmarcando **«Enseñar el resumen de teclas
mientras no hay ningún documento abierto»**: quedan dos líneas en su lugar, y el
resumen entero sigue en `Mayús+F1`.

### Qué formatos abre

| Formato | Extensiones | Qué conviene saber |
|---|---|---|
| **EPUB** | `.epub` | Versiones 2 y 3, con índice, páginas y notas |
| **PDF** | `.pdf` | Si es accesible se navega como un EPUB; si no, se deduce su estructura; si está escaneado se reconoce con OCR |
| **Kindle** | `.kfx`, `.kfx-zip`, `.azw3`, `.azw`, `.azw4`, `.azw8`, `.mobi`, `.prc` | Los formatos de Amazon, **sin DRM** |
| **Word** | `.docx`, `.docm` | Títulos, listas anidadas, enlaces, tablas con encabezados e imágenes con su texto alternativo |
| **Word 97** | `.doc`, `.dot` | El formato binario de hace veinte años, con sus párrafos y sus tildes en su sitio |
| **Excel / Excel 97** | `.xlsx`, `.xlsm`, `.xls`, `.xlt` | Cada hoja es un encabezado y su contenido, una tabla de verdad |
| **PowerPoint / PowerPoint 97** | `.pptx`, `.pptm`, `.ppsx`, `.ppt`, `.pps`, `.pot` | Una diapositiva por encabezado, en el orden en que se ven, con las notas del ponente |
| **LibreOffice** | `.odt`, `.ods`, `.odp` y sus variantes planas y de plantilla | Igual que los de Office, y además las notas al pie |
| **DAISY** | carpeta, `.ncx`, `.opf`, `.daisy` | Con texto, con grabación o las dos cosas |
| **FictionBook** | `.fb2` | Con sus imágenes incrustadas |
| **Texto enriquecido** | `.rtf` | Títulos, listas, tablas, enlaces e imágenes |
| **Páginas web** | `.html`, `.htm`, `.xhtml`, `.xml` | Una página guardada, de la que se queda **solo el artículo** |
| **Correo y páginas archivadas** | `.eml`, `.mht`, `.mhtml` | Quién escribe, a quién, cuándo, el cuerpo y los adjuntos |
| **Ayuda de Windows** | `.chm`, `.hlp` | Documentación antigua, con sus imágenes. El `.hlp` es anterior al CHM y hoy no lo abre nada más |
| **DjVu** | `.djvu`, `.djv` | Media biblioteca digitalizada. Se saca el texto reconocido al escanear; **si no lo trae, se reconoce aquí**, y una página que sea solo una lámina se ve y se describe |
| **Partituras** | `.musicxml`, `.mxl` | Cada compás se dice en palabras y se escribe en **musicografía braille** |
| **Cómic** | `.cbz`, `.cbt`, `.cbr`, `.cb7` | Cada página es una imagen: se recorren con `G` y se describen con IA |
| **Braille** | `.bra` | Un archivo braille español se vuelve a pasar a tinta |
| **Texto y Markdown** | `.txt`, `.md`, `.markdown`, `.text`, `.log`, `.nfo` | Encabezados, listas y tablas quedan navegables |

Lo que no traiga índice propio lo construye el programa con sus encabezados, así
que `Control+T` sirve siempre.

**Los comprimidos se abren solos.** El programa trae su propio 7-Zip en
`data/bin`, así que un `.cbr`, un cómic partido en volúmenes o un `.cb7` se abren
sin instalar nada.

### Traer una página de internet

`Control+Mayús+U` pide una dirección, **la trae, le quita los menús y los
anuncios y la abre**. Si tenías el enlace copiado, aparece ya escrito. La página
se guarda en el disco, así que se puede volver a ella sin conexión y se le pueden
poner marcadores.

Una página que no escribe nada hasta que se ejecutan sus guiones se traerá vacía,
y entonces **se dice** en vez de abrir un documento en blanco.

---

## 2. Leer y moverse

El texto está en un cuadro de edición normal de Windows: funcionan todas las
órdenes de tu lector de pantalla. **Aquí una «línea» es un párrafo completo**, así
que `Flecha abajo` avanza un párrafo y el lector lo lee de una vez.
`Control+Alt+W` ajusta las líneas al ancho de la ventana, pero entonces la flecha
avanza por trozos visuales: mejor **apagado para leer de oído**.

`Control+D` da los datos del documento y **por dónde vas**: porcentaje, tiempo
leído, palabras por minuto y cuánto queda a ese ritmo. `Control+Mayús+Q` dice solo
lo que falta para acabar el capítulo y el documento.

### Saltar de un elemento a otro

**Una sola tecla** salta al siguiente elemento de ese tipo; con `Mayús`, al
anterior. Son las mismas que usan los lectores de pantalla en las páginas web.

| Tecla | Elemento | Tecla | Elemento |
|---|---|---|---|
| `H` | Encabezado | `Q` | Cita |
| `1` a `6` | Encabezado de ese nivel | `E` | Fórmula matemática |
| `K` | Enlace | `S` | Separador |
| `G` | Imagen | `P` | Página |
| `F` | Figura (imagen con pie) | `C` | Capítulo |
| `T` | Tabla | `B` | Marcador |
| `L` | Lista | `N` | Nota |
| `I` | Elemento de lista | `O` | Llamada de nota al pie |
| `X` | Bloque de código | `Z` | Salir de la lista o tabla actual |

`Intro` sobre un enlace salta allí (`Alt+Izquierda` vuelve); sobre una imagen o
una tabla, las abre. Cuando no queda ninguno suena un tono grave y se dice; en
Opciones puedes pedir que siga desde el principio.

### Sonidos y modo lectura

Al entrar el cursor en una línea donde empieza un elemento suena un aviso corto:
un tono limpio para un encabezado —más agudo cuanto más importante—, dos toques
para una imagen, un acorde grave para una tabla, un roce largo para un salto de
página, un tono grave cuando no hay más.

`Control+Alt+M` es el **modo lectura**: apaga de una vez los sonidos, el aviso de
elementos, la barra de estado y el árbol, y al volver a pulsarlo recupera
exactamente lo que tuvieras. `Control+Alt+S` silencia solo los sonidos.

En **Opciones → Sonidos** se elige **cómo se avisa**: con un sonido, **diciendo
los elementos con la voz**, las dos cosas o ninguna. La voz existe porque el
pitido solo puede sonar **uno por línea**: en una línea con un salto de página y
una llamada de nota, la nota se queda sin señalar. Dichos, se oyen hasta tres.

---

## 3. Varios documentos a la vez

Viene **apagado**; se enciende en `Opciones → Personalización`.

**Pestañas.** Cada una guarda lo suyo: posición, marcadores, historial y la frase
por la que iba la voz. Al abrir con otro delante el programa pregunta dónde lo
quieres, con casilla para no volver a preguntar.

**Árbol de contenido.** A la izquierda del texto, con el índice y los elementos
agrupados. `Flecha derecha` despliega, `Intro` salta y devuelve el foco al texto.
Al llegar a él ya está colocado por donde vas leyendo.

**Zonas.** `F6` va a la siguiente y `Mayús+F6` a la anterior: árbol, pestañas,
texto.

En `Opciones → Pestañas`, **«volver a abrir los documentos que quedaron
abiertos»** los recupera al arrancar, cada uno por donde ibas. Viene apagada, y
abrir un libro con doble clic abre ese y no recupera nada.

---

## 4. La biblioteca

`Control+Mayús+B` abre la biblioteca: **todos tus libros en una lista**, con su
autor, su formato y por dónde vas. El filtro reduce la lista al instante. Están
los que has abierto alguna vez y los de las carpetas que añadas; añadir una
carpeta no mueve ni copia nada.

**Agrupar por asignatura.** El botón **«Poner colección»** le pone a los libros
marcados el nombre de una colección —«Contabilidad», «Tesis»—, a todos a la vez.
Arriba aparece un desplegable para quedarse solo con los de una. Todo lo demás
—buscar, la bibliografía, el cuaderno— actúa sobre lo que se esté viendo, así que
filtrar por asignatura y sacar su bibliografía son dos pasos seguidos. La
colección viaja al otro equipo con la sincronización.

**Buscar en todos los libros.** Escribe la frase y pulsa Intro: abajo aparecen los
resultados con el trozo de texto y en qué página de qué libro está, y **`Intro`
abre ese libro en ese punto**. «Buscar en los analizados» mira solo los ya
abiertos y es instantáneo; «Buscar en todos» mira también los que nunca abriste y
para eso tiene que analizarlos.

**La ficha, con los datos que tú quieras.** `Alt+Intro` en la lista (o el botón
**«Ficha del libro»**) enseña lo que se sabe del libro, un dato por línea. De
fábrica van primero **el título, la serie, los autores y la sinopsis**, y después
lo técnico: editorial, fecha, ISBN, formato, archivo... Con **«Elegir los
datos»**, dentro de la ficha, marcas los que quieres ver y los subes o bajas
(también con `Alt+flecha arriba` y `Alt+flecha abajo`). Si solo te interesan el
título, el autor y la sinopsis, deja esos y la ficha se lee de un vistazo.

**Libros similares.** El botón **«Libros similares»**, o la tecla de aplicaciones
(`Mayús+F10`) sobre un libro de la lista, ofrece traer **los de la misma serie,
del mismo autor, de la misma colección, con la misma etiqueta o de la misma
editorial**. Desde un libro de Harry Potter, «De la misma serie» deja en la lista
toda la saga, ordenada por su número. Es lo mismo que agrupar a mano, pero de una
vez; para volver a verlo todo, elige «Todos» en la lista de grupos.

**Exportar las fichas.** El botón **«Exportar fichas»** guarda las fichas de los
libros marcados —o de todos los que se ven— en **texto** o en **CSV** para una
hoja de cálculo. Los datos de la exportación se eligen aparte de los de la ficha
que se ve: puedes consultar con una ficha corta y exportar una completa para un
trabajo.

**Buscar por lo que significa.** Tus apuntes dicen «amortización» y el manual dice
«depreciación»; por letras eso no aparece. El botón **«Palabras relacionadas»**
enseña qué otras palabras salen en los mismos pasajes **en tus propios libros**, y
tú eliges cuáles añadir. Lo aprende de tu biblioteca, no de un diccionario: en
una de derecho, «prescripción» sale junto a «caducidad». La primera vez hay que
leer los libros una vez; después es instantáneo. Sin cuenta, sin conexión y sin
mandar nada a ningún sitio.

**La bibliografía.** El botón **«Bibliografía»** saca la lista de referencias de
los libros que estés viendo, ordenada por apellido, en ISO 690, APA, MLA o
sencilla. Se copia o se guarda en seis formatos: tres para leer (texto, Markdown,
web) y tres para **importar** —BibTeX en Zotero o LaTeX, RIS en Mendeley o
EndNote, `.csv` en una hoja—. Arriba se dice **a cuántas les falta algún dato**;
lo que el archivo no trae, no se inventa.

**Sincronizar entre equipos.** En `Opciones → Biblioteca y sincronización` eliges
una carpeta que ya sincronices tú (Dropbox, OneDrive, un pendrive). El programa
deja ahí por dónde vas, marcadores, notas y descripciones, y al abrirlo en el otro
equipo lo junta. No hace falta ninguna cuenta, **no** se sincronizan las
preferencias —la voz de casa puede no estar en el trabajo— y al juntar no se
pierde nada.

---

## 5. Buscar, marcar y estudiar

| Orden | Tecla | Qué hace |
|---|---|---|
| **Índice** | `Control+T` | Árbol de capítulos, abierto por donde lees |
| **Lista de elementos** | `F7` | Eliges qué ver, con cuántos hay de cada |
| **Buscar** | `Control+F` | El cuadro se queda abierto. **Contar** dice cuántas veces aparece |
| **Marcadores y notas** | `Control+B` | La lista completa, con filtro |

**Buscar mientras escuchas.** Si estabas oyendo el libro, al abrir la búsqueda la
voz **se calla y guarda el sitio**; al cerrarla sigue leyendo desde el resultado
—que es para lo que buscabas— o desde donde se dejó si no encontró nada. Quien
busca en silencio sigue en silencio.

**Marcadores y notas.** Un marcador señala un punto; una nota es un marcador con
texto. `Control+M` pone o quita un marcador y `Control+Mayús+M` escribe una nota.
Se guardan por documento y vuelven entre sesiones.

**Resaltar pasajes.** Selecciona el texto y pulsa `Control+Alt+E`; la misma tecla
lo quita. `Control+Alt+K` da la lista, desde donde se guardan en un archivo
—texto, Markdown o HTML— **con su página**, que es la mitad de para lo que sirve
resaltar.

**Etiquetas.** Debajo del texto de una nota hay un campo de etiquetas separadas
por comas: «examen», «capítulo 4», «dudas». El desplegable ofrece las que ya usas,
que es lo que evita acabar con tres temas que son el mismo. En la lista de
resaltados aparece entonces «Mostrar solo la etiqueta», y al guardar sale solo lo
de ese tema. Se comparan sin tildes ni mayúsculas: «Análisis» y «analisis» son la
misma.

### El cuaderno de estudio

Quien prepara una asignatura no estudia un libro: estudia un tema repartido por
seis. En la biblioteca, el botón **Cuaderno de estudio** recoge las notas y los
resaltados de **todos los libros que estés viendo**, los agrupa **por etiqueta** y
saca un solo archivo diciendo de qué libro y de qué punto sale cada cosa. En
página web los temas son encabezados de verdad, así que se salta con `H`.

**No hace falta abrir ningún libro**: cada marcador guarda su propio trozo de
texto. Lo único que no se puede decir es la página exacta; en su lugar va el
porcentaje. Un apunte con dos etiquetas sale en los dos temas, y lo que no lleva
ninguna va en un grupo al final.

### Repasar lo marcado

El botón **Repasar** del cuaderno convierte cada resaltado y cada nota en una
tarjeta, sin escribir nada aparte, y se lleva el filtro de tema puesto.

Cada tarjeta se enseña **en dos tiempos**: primero de dónde sale y tu nota, y solo
al pulsar **Espacio** se descubre el pasaje. Recordar y reconocer no son lo mismo.
Después se responde con **1** (no me acordaba), **2** (me ha costado) o **3** (lo
sabía).

Lo que sale bien tarda cada vez más en volver —un día, seis, y después según lo
fácil que te resulte—; lo que no, **vuelve mañana**. Una tanda son treinta
tarjetas como mucho, y lo repasado se guarda después de cada una, así que cerrar
la ventana no pierde nada.

### Copiar con la cita hecha

`Control+Mayús+C` copia el pasaje seleccionado **con su referencia ya montada**:
autor, título, editorial, año y la página. Sin selección copia solo la referencia.
Hay cuatro estilos —ISO 690, APA 7.ª, MLA 9.ª y una sencilla— y se puede corregir
antes de copiar: de «Gabriel García Márquez», ningún programa sabe solo que
«García Márquez» son los dos apellidos. Lo que el documento no diga no se inventa.

---

## 6. Imágenes, tablas, notas y fórmulas

**Imágenes.** En el texto salen como `[Imagen: descripción]`. Con `G` te colocas
encima y con `Intro` o `Control+I` se abre la ventana.

**Tablas.** En el texto son filas separadas por tabuladores. `Control+Mayús+T`
—o `Intro` sobre la tabla— abre una rejilla con columnas de verdad.

**Verlo como HTML.** Convertida a texto, una tabla deja de ser una tabla.
`Control+H` coge la tabla, la lista, la cita, la fórmula o el bloque de código del
cursor, lo reconstruye como HTML y lo abre en un navegador empotrado: vuelven a
funcionar las órdenes de tabla del lector y en una lista anidada se anuncia el
nivel. `Control+Mayús+H` hace lo mismo con el capítulo entero. Hay botones para
guardar, abrir en el navegador y copiar.

**Notas al pie.** `O` salta de llamada en llamada. Sobre una, `Alt+Mayús+N`
**dice la nota sin mover el cursor**. Las llamadas se reconocen por su forma
—un número entre corchetes o volado que lleva a otro punto del libro— aunque el
libro no las declare, así que `O` las recorre todas y `K` se queda con los enlaces
que no son notas. En la lectura continua del lector de pantalla los sonidos no
pueden sonar; para eso está **«Decir "nota" en las llamadas»** en
`Opciones → Lectura`.

**Todas las notas juntas.** `Control+Mayús+N` abre el **visor de notas**: la
lista entera del libro, cada una con su texto completo debajo, que va cambiando
según te mueves con las flechas. Se abre por la nota más cercana a por donde ibas
leyendo.

Arriba hay un buscador que filtra según escribes y **no distingue tildes ni
mayúsculas**: escribiendo `isocrates` salen las de «Isócrates». Y de cada nota se
puede hacer lo que se hace con una nota:

| Botón | Qué hace |
|---|---|
| **Ir a donde se cita** | Lleva al pasaje del libro que llama a esa nota |
| **Ir a la nota** | Lleva a su texto, al final del libro; con `Alt+Izquierda` se vuelve |
| **Copiar** | Copia la nota entera al portapapeles |

Es lo que hace falta cuando las notas son la mitad del libro: en un volumen de
quinientas notas, verlas de una en una son quinientos viajes de ida y vuelta.

**Bloques de código.** Se saltan con `X` y **conservan la sangría**, que en Python
no es presentación sino sintaxis. `Control+H` los abre en el visor, con botón para
copiar solo el código.

**Fórmulas.** El MathML se lee de dos maneras: en el texto se convierte en una
frase —«x al cuadrado más 3 x menos 5 igual a 0»— y con `Control+H` se abre la
fórmula original, que llega intacta al lector para que la recorra por partes. `E`
salta de fórmula en fórmula.

### Los datos de un gráfico, y la estructura de un diagrama

Describir un gráfico no basta: «un gráfico de barras de ventas por trimestre» se
oye entero sin saber ni un solo número.

En la ventana de la imagen, el botón **«Sacar los datos»** sirve para dos cosas y
no hay que elegir cuál, porque saber si dentro de una imagen hay una tabla o un
diagrama es justo lo que no se puede ver:

- Si es un **gráfico**, saca sus valores en una tabla que se recorre celda a
  celda, y dibuja además su forma en braille de ocho puntos. Con dos o tres
  series se dibujan todas juntas y a la misma escala, distinguidas por el grosor
  del trazo.
- Si es un **diagrama de flujo, un organigrama o un circuito**, saca su
  **recorrido** como lista anidada —«pedir el correo; si es válido, crear la
  cuenta; si no, vuelve al paso 2»— y su silueta al tacto, con cada caja un
  cuadradito y cada flecha una raya.

En los dos casos **se dice de qué se fía**: si ha tenido que estimar un valor o
suponer por dónde va una flecha, lo advierte. Y si la imagen no tiene ni valores
ni estructura, se dice y no se guarda nada.

---

## 7. PDF y documentos escaneados

**PDF accesibles.** Los que vienen etiquetados traen dentro qué es cada cosa, y se
navegan como un EPUB.

**PDF normales.** Son la inmensa mayoría, y no traen nada. El programa **mide**
cada página y deduce lo que el archivo no dice: los títulos por su tamaño de letra
y su numeración, las listas por sus viñetas, las tablas por cómo se alinean sus
columnas, las notas al pie por estar abajo y en letra menor, los enlaces por dónde
están dibujados. Los textos a dos columnas se leen columna por columna. Se apaga
en `Opciones → PDF` si en un archivo concreto estorba.

**Corregir lo deducido.** `Control+Mayús+E` sobre un elemento cambia lo que el
programa creyó que era: convertir en encabezado lo que tomó por un párrafo, o
quitarle la marca a la cabecera que se repite. La corrección se guarda junto a los
marcadores; **el archivo no se toca**.

**Lo que le falta al documento.** `Control+Mayús+A` da un informe de
accesibilidad: si trae estructura, si las imágenes están descritas, si las tablas
marcan su fila de encabezados. Son comprobaciones automáticas y parciales:
detectan lo que falta, no garantizan que el documento se lea bien.

**Protegidos.** Un PDF puede llevar dos contraseñas. La de **propietario**, que
solo prohíbe imprimir y que llevan casi todos los artículos de revista, **se salta
sola**. La de **usuario**, que sí hace falta para leer, se pide al abrirlo. De los
`.doc`, `.xls`, `.ppt` y presentaciones protegidas se dice claramente que lo
están: el programa no quita protecciones de nada.

**Dañados.** Si se le ha roto el índice interno, el programa **lo reconstruye en
una copia** y lee de ahí. El original no se modifica.

### Escaneados: el reconocimiento de texto

Cuando una página es una fotografía, se reconoce. Vale igual para un PDF y para
un **DjVu que no traiga dentro el texto**, y los ajustes son los mismos para los
dos. Hay tres motores listos para usar: **Tesseract** (incluido, sin conexión ni cuota, fuerte en columnas y
tablas), **la IA que tengas configurada** (para letra difícil o escaneados
torcidos) y **el de Windows** (el más rápido).

El programa reconstruye el **orden de lectura** mirando dónde cae cada palabra,
así que un folleto en rejilla sale con cada producto junto a su precio. Vienen
español, catalán, gallego, euskera e inglés, y se añaden más en
`Opciones → Reconocimiento → Idiomas`: **los justos**, porque más de tres empeora
el resultado.

Si un documento se resiste, en esa misma pestaña están los ajustes que más
cambian: preparar la imagen, leer cada página dos veces (lo que más mejora, y
tarda el doble), la segmentación y el aumento. `Control+F1` sobre cada uno explica
qué hace y qué conviene poner.

**Un cómic o un álbum de fotos no tienen texto que sacar.** Para eso está
**«enseñar las páginas escaneadas como imágenes»**: cada página es una imagen, se
recorren con `G` y se describen con IA, que en un cómic es lo único que de verdad
cuenta lo que pasa.

### Volver a analizar: `F5`

Convertir un documento cuesta tiempo —y uno escaneado, minutos—, así que el
resultado se guarda y la segunda vez se abre al instante. Eso tiene una pega:
**si cambias los ajustes de reconocimiento, un documento que ya habías abierto
sigue saliendo como salió**. El archivo no ha cambiado, así que lo guardado se
sigue dando por bueno. Pasa cuando abriste un PDF escaneado con el
reconocimiento apagado, cuando lo abriste con el tope de páginas por debajo de
las que tiene, o cuando has cambiado de motor o de idiomas.

`F5` —o `Herramientas → Volver a analizar el documento`— lo convierte otra vez
desde el archivo, sin usar lo guardado, y te deja donde estabas. **No toca nada
de lo tuyo**: los marcadores, las notas, los resaltados y las descripciones de
las imágenes siguen ahí. Antes la única salida era borrar los datos del
documento en `Herramientas → Datos guardados`, que se los lleva por delante.

Al cambiar en las opciones algo que afecta a cómo se convierte el documento
—reconocimiento incluido— se te ofrece volver a leerlo en ese momento, que es lo
mismo sin tener que acordarse de `F5`.

---

## 8. Libros DAISY

El formato de las bibliotecas para personas ciegas: con texto, con grabación o las
dos cosas sincronizadas.

| Tecla | Qué hace |
|---|---|
| `Control+Alt+R` | Los mandos, con la lista de capítulos y páginas |
| `Control+Alt+Z` / `Control+Alt+X` | Diez segundos atrás o adelante |
| `Control+Alt+Re Pág` / `Control+Alt+Av Pág` | Punto de navegación anterior o siguiente |
| `Control+Mayús+Arriba` / `Control+Mayús+Abajo` | Cambia el **nivel** de navegación |
| `Control+Alt+J` | Dónde estás: capítulo, página, tiempo y lo que queda |

**El nivel** es lo que hace cómodo un reproductor DAISY: eliges si «anterior» y
«siguiente» significan capítulo, sección, página o frase, y recorres el libro con
dos teclas.

Se reproduce desde donde está el cursor, y el cursor sigue a la grabación para que
puedas consultar con el lector lo que suena. La velocidad va en **por ciento de la
grabada** —de 50 a 300— y **no altera el tono**, así que a 200 el narrador no se
convierte en un pato.

---

## 9. Leer en voz alta

Va **frase a frase**, así que pausar responde al instante y las teclas de frase
sirven para releer. Las abreviaturas y los decimales no parten la frase, y no se
detiene al final del capítulo.

**El cursor no se mueve mientras lee** —si lo hiciera, el lector leería la línea
encima de la voz—; se coloca en la frase que sonaba al pausar. **La pausa sirve
para saltar**: pausas, te mueves con las flechas y al reanudar empieza donde
estás.

**Dónde queda el cursor al parar lo eliges tú**, en `Control+Alt+V → Al leer`.
De fábrica queda **al principio de la frase que sonaba**, que es lo que conviene
cuando paras porque algo no se ha entendido: la flecha arriba vuelve a leer justo
eso. La otra opción lo deja **detrás de esa frase**, y entonces las flechas
siguen por lo que aún no ha sonado en vez de repetirte el párrafo que acabas de
oír; es lo que conviene cuando paras para seguir leyendo a mano. En los dos
casos, volver a dar a leer retoma donde estaba: la frase que quedó a medias se
termina.

**Cambia de voz sola cuando el documento cambia de idioma.** Al llegar a una cita
en inglés dentro de un informe en español pone una voz inglesa si la tienes
instalada y vuelve a la tuya al salir, igual que NVDA.

Los ajustes están en `Control+Alt+V`, repartidos en cinco pestañas: **Voz**
—cuál habla, a qué velocidad y a qué volumen—, **Motores de voz**, **Al leer**,
**Qué se dice** y **Diálogos**.

**Si una voz tarda en empezar**, oirás un pulso corto mientras se prepara y, si
se alarga, un aviso. Hay voces que generan la frase entera antes de sonar: unos
segundos la primera vez y décimas después.

### El modo «entrevista»: otro tono para los diálogos

En una novela con mucho diálogo, oírlo todo con la misma voz obliga a reconstruir
quién dice cada cosa: quien lee con los ojos ve las rayas en el margen, y de oído
no están. En **Voz → Ajustes de voz**, la casilla **«Cambiar de tono en los
diálogos»** hace que lo que dice un personaje suene un poco más agudo y que el
inciso del narrador vuelva al tono normal. Debajo se regula cuánto, de 1 a 10:
cuatro se nota sin sonar raro.

**Lo que cuesta es distinguir una raya de un guion.** Un guion al principio de un
renglón es también una viñeta de lista, y poner voz de personaje a la lista de la
compra es peor que no cambiar de voz. Por eso la raya larga se toma siempre por
diálogo y el guion solo cuando el libro no usa rayas en ninguna parte y el renglón
parece de verdad una intervención. Ante la duda, narración. Viene apagado, porque
en un manual no hay diálogo.

### Pronunciación, temporizador y teclas globales

**Voz → Diccionario de pronunciación**: una tabla donde se escribe la palabra tal
como está en el libro y cómo hay que decirla —«Danerís» por «Daenerys»—, con botón
para probarla. Hay dos tablas: la de este documento y las generales, para siglas y
símbolos.

**Temporizador** (`Control+Alt+T`): para de leer al cabo del tiempo que le digas,
avisando un minuto antes. Manda igual sobre la voz sintética y sobre las
grabaciones DAISY.

**Exportar a audio** (`Archivo → Exportar → Audio MP3`): un archivo por capítulo o
uno solo con todo, aplicando el mismo diccionario de pronunciación.

**Teclas globales** (`Opciones → Teclas globales`): llegan aunque estés escribiendo
en otro programa. Vienen **desactivadas**; de fábrica usan `Control+Alt+Mayús` más
`Espacio`, `Fin`, las flechas y `V`. Al cambiar una se comprueba que no la reserve
Windows ni la usen NVDA o JAWS, y que Windows la conceda de verdad.

**La bandeja**: al minimizar, el programa queda como un icono junto al reloj y la
lectura sigue sonando.

---

## 10. Inteligencia artificial

Es **opcional** y el programa funciona entero sin ella. Se configura en
`Opciones → Inteligencia artificial`, con tres caminos: un servicio de pago con tu
clave, un modelo **instalado en tu propio equipo** o nada.

**Describir imágenes.** `Control+Alt+I` describe la del cursor; `Control+Alt+D`,
todas las del documento, con barra de progreso, y **se puede parar y retomar**:
solo describe las que faltan. Cada imagen se describe una vez y un fallo suelto no
tira el trabajo. Las descripciones **se guardan y vuelven con el documento**: se
paga una vez y sirve siempre.

Una lámina no se cuenta igual en una novela que en un manual de botánica. Hay diez
instrucciones predefinidas —General, Breve, Novela, Libro técnico, Gráficos, Mapas,
Cómic, Arte, Infantil y Solo transcribir el texto— que se pueden duplicar y
retocar. La preferida es la que usa la tecla `A`.

**Tu propia IA.** El asistente descarga e instala Ollama y un modelo dentro de
`data`, sin cuenta, sin tarjeta y **sin conexión una vez instalado**. Funciona con
tarjeta gráfica o solo con el procesador. También se puede **importar un `.gguf`
que ya tengas** en el disco.

**Preguntar sobre el documento** (`Control+Alt+P`): resúmenes, explicaciones,
preguntas de examen. Se manda **el trozo que elijas**, no el libro entero, que es
lo que hace que la respuesta hable de lo que estás leyendo.

**Definir una palabra** (`V`): en el diccionario de la Academia, en el Wikcionario
o preguntándoselo a la IA, que es la única que entiende en qué sentido se usa esa
palabra en esa frase.

**Lo que llevas gastado**: cuántas peticiones y lo que han costado, para que la
factura no sea una sorpresa. Con una IA local siempre es cero.

> La IA se equivoca con seguridad y sin avisar. Para entender algo va muy bien;
> para citar un dato, hay que ir al libro.

---

## 11. Opciones y perfiles

`Control+Alt+O` abre las opciones: nueve pestañas, y `Control+Tabulador` para
cambiar entre ellas. **Sobre cualquier ajuste, `Control+F1` explica qué es, qué
consigue y qué conviene poner**, así que aquí no se repiten.

**Perfiles de lectura** (`Control+Alt+F`). No se lee igual una novela que un manual
técnico, y cambiarlo a mano son ocho ajustes en cuatro pestañas. Un perfil los
guarda de una vez con un nombre: voz, velocidad, volumen, sonidos, presentación
del texto, velocidad de las grabaciones y prompt preferido. No guarda el idioma de
la interfaz ni las claves de la IA. Con la lista vacía, **Crear tres perfiles de
ejemplo** deja preparados «Novela», «Libro técnico» y «Escuchar sin mirar».

**Abrir desde el explorador.** En `Opciones → Integración con el sistema` marcas,
formato a formato, cuáles quieres abrir con este programa. Lo que no marques se
queda como estaba.

Al hacer doble clic en un archivo pasa lo que tenga sentido según cómo trabajes:

- Con el programa **cerrado** y **«Recuperar los documentos abiertos» marcado**,
  vuelven las pestañas que dejaste y el libro nuevo se abre además, delante. Si
  no lo tienes marcado, se abre solo ese libro, que es lo que pediste.
- Con el programa **abierto**, el libro se abre en la ventana que ya está: no
  aparece una segunda.
- Y si **ese libro ya estaba abierto**, no se abre otra vez: se va a su pestaña.
  Si el archivo ha cambiado en el disco desde que lo abriste —lo has vuelto a
  exportar, ha llegado una versión nueva— se avisa y se relee, para que no sigas
  leyendo un texto que ya no es el que hay.

---

## 12. Exportar: braille, DAISY y audio

En **Archivo → Exportar**, además del texto, el Markdown, la página web, el EPUB y
el audio, hay tres salidas pensadas para quien no ve.

**Braille (.brf)** transcribe el documento a braille español con 40 celdas por
línea y 25 líneas por página. **Braille en XML (.pef)** es el mismo braille en el
formato que se intercambian las bibliotecas e imprentas braille de Europa.

En los dos:

- **Las matemáticas** se escriben en braille matemático, siguiendo el Código
  Matemático Unificado. Lo que ese código no cubre —integrales, matrices— se
  escribe con la frase hablada: una fórmula mal transcrita sería peor.
- **La química**, con la signografía del documento B 6-1: `H₂O` son tres celdas y
  no cinco.
- **Las partituras**, en musicografía braille (B 4-2). Los **acordes** no van nota
  a nota: se escribe una —la más aguda en clave de sol, la más grave en clave de
  fa— y las demás con **signos de intervalo**. **Dos voces** en el mismo
  pentagrama se separan con la **cópula**. Los adornos —trinos, mordentes— se
  dicen en palabras y se avisa.
- **Las tablas** se componen en **columnas alineadas**, y cuando no caben en el
  renglón se escriben con el nombre de la columna delante de cada dato.

### Braille contraído, o grado 2

En `Opciones → Exportar`, la casilla **«Escribir el braille en contraído»** —que
viene **apagada**— usa las abreviaturas del braille contraído español: en una
novela de ochocientas mil letras el archivo pasa de 874 a 619 kilobytes.

Se sigue el documento B 16-1 de la Comisión Braille Española, revisión de 2025,
con sus cinco pasos en el orden que manda. Viene apagada por dos razones: quien no
haya estudiado el contraído **no entiende un texto contraído**, y la transcripción
acierta en todas las palabras de la lista de la norma pero en nueve de cada diez
de las que hay que abreviar sobre la marcha. Para leer, sirve; para imprimir y
repartir, conviene que lo repase quien lea contraído. Las fórmulas no se contraen
nunca.

**Libro DAISY** escribe una carpeta en DAISY 3, con solo el texto —sale en un
segundo— o con **texto y voz sincronizados frase a frase**, que da un libro
hablado que se puede seguir a la vez en la línea braille. Poder generarlo a partir
de un PDF recién reconocido es justo lo que no se puede hacer sin herramientas de
pago.

**Audio con marcas de capítulo**: un único MP3 con sus capítulos dentro, de modo
que el reproductor del móvil o del coche deje saltar de uno a otro.

**Comprobar el libro exportado**: el EPUB que sale pasa por las mismas
comprobaciones de accesibilidad que cualquier otro libro.

---

## 13. Lo que el programa guarda

Todo vive en la carpeta `data`, al lado del programa. Es portátil: se copia
entera a un pendrive y sigue funcionando con tus ajustes.

| Carpeta | Qué hay |
|---|---|
| `config` | Preferencias, posición de lectura, marcadores, notas y resaltados |
| `cache` | Libros ya analizados, para que se abran al instante |
| `descripciones` | Lo que la IA ha descrito de cada imagen |
| `correcciones` | Lo que has corregido a mano en un PDF |
| `logs` | El registro de actividad |
| `idiomas` | Traducciones y este manual |
| `sonidos` | Los avisos que suenan al moverte por el documento |
| `tesseract` | El reconocimiento de texto portátil |
| `bin` | El 7-Zip que abre los comprimidos |
| `temp` | Archivos de paso, que se borran solos |

Si añades alguna voz aparecerá también una carpeta `motores`, con lo que cada
una necesite dentro. Por eso el programa se lleva en un pendrive con sus voces.

En `Herramientas → Datos guardados` se ve **cuánto ocupa cada cosa** y se borra lo
que sobre. Los marcadores y las notas no se tocan desde ahí.

**Actualizaciones**: `Ayuda → Buscar actualizaciones`, y también sola al arrancar.
Tus ajustes, marcadores, notas y posiciones **no se tocan**: viven en `data` y el
paquete no los trae. Cada versión se publica en el servidor del autor y en
GitHub; en `Opciones → Avanzado`, «Buscar las actualizaciones en», eliges uno,
los dos (lo de fábrica: si uno falla se usa el otro) o una dirección
personalizada. Venga de donde venga, solo se instala un paquete firmado por el
autor.

**Qué ha cambiado**: `Ayuda → Ver las últimas novedades` abre en el navegador lo
que trae cada versión, empezando por la más reciente. Es lo mismo que cuenta el
aviso de actualización, pero entero y cuando quieras, no solo al instalarla.

---

## 14. Si algo va mal

**El visor de registros** (`Ayuda → Ver registro de la aplicación`) muestra lo
anotado en cinco columnas recorribles con las flechas. Puedes elegir la sesión,
filtrar, buscar, copiar lo mostrado o vaciar la carpeta. **No es modal**, así que
déjalo abierto y reproduce el fallo; con **Seguir en vivo** se relee solo.

Antes de perseguir un fallo, pon el detalle en «detallado» (`Opciones →
Avanzado`): así queda constancia de lo que pasó y se puede mandar. El registro
**no lleva el contenido de tus libros**: lleva qué se abrió, cuánto tardó y qué
falló.

Tres cosas que resuelven casi todo:

- **Un documento se abre raro.** Prueba a apagar la deducción de estructura en
  `Opciones → PDF`, o corrige a mano con `Control+Mayús+E`.
- **Una tecla global no hace nada.** Otro programa se la ha quedado: usa
  **Comprobar todas** en `Opciones → Teclas globales`.
- **No hay voces.** Se añaden en Configuración de Windows → Hora e idioma → Voz.

---

## 15. Las teclas

**`Mayús+F1` las enseña todas** con su descripción, generadas del propio
programa. Aquí están igualmente, para poder buscarlas y leerlas de corrido.

### Una sola tecla, sobre el texto

Saltan al siguiente elemento de ese tipo; con `Mayús`, al anterior.

| Tecla | | Tecla | |
|---|---|---|---|
| `H` | Encabezado | `Q` | Cita |
| `1` a `6` | Encabezado de ese nivel | `E` | Fórmula |
| `K` | Enlace | `S` | Separador |
| `G` | Imagen | `P` | Página |
| `F` | Figura | `C` | Capítulo |
| `T` | Tabla | `B` | Marcador |
| `L` | Lista | `N` | Nota |
| `I` | Elemento de lista | `O` | Llamada de nota |
| `X` | Bloque de código | `Z` | Salir del bloque actual |
| `A` | Describir esta imagen con IA | `V` | Definir esta palabra |
| `D` | Dónde estoy | `R` | Repetir el último aviso |

### Archivo

| Tecla | Qué hace |
|---|---|
| `Control+O` | Abrir |
| `Control+Mayús+U` | Abrir una dirección de internet |
| `Control+Mayús+O` | Abrir la carpeta de un libro DAISY |
| `Control+Mayús+B` | Biblioteca |
| `Control+E` | Exportar a texto |
| `Control+W` | Cerrar |
| `Alt+F4` | Salir |

### Moverse

| Tecla | Qué hace |
|---|---|
| `Control+T` | Índice del documento |
| `F7` | Lista de elementos |
| `Control+B` | Marcadores y notas |
| `Control+F` / `F3` / `Mayús+F3` | Buscar, siguiente, anterior |
| `Control+G` / `Control+Mayús+G` / `Control+P` | Ir a línea, porcentaje o página |
| `Control+Inicio` / `Control+Fin` | Principio y final |
| `Alt+Izquierda` / `Alt+Derecha` | Atrás y adelante |

### Pestañas y zonas

| Tecla | Qué hace |
|---|---|
| `Control+N` | Nueva pestaña |
| `Control+Tabulador` / `Control+Mayús+Tabulador` | Pestaña siguiente y anterior |
| `Control+F6` | Lista de pestañas |
| `F6` / `Mayús+F6` | Zona siguiente y anterior |
| `Control+Alt+B` | Enseñar u ocultar el árbol de contenido |

### Herramientas

| Tecla | Qué hace |
|---|---|
| `Control+M` / `Control+Mayús+M` | Poner marcador / escribir nota |
| `Control+Alt+E` / `Control+Alt+K` | Resaltar / lista de resaltados |
| `Control+Mayús+C` | Copiar con la cita |
| `Control+I` / `Control+Mayús+T` | Ver la imagen / ver la tabla |
| `Control+H` / `Control+Mayús+H` | Ver el elemento / el capítulo como HTML |
| `Alt+Mayús+N` | Leer la nota al pie de aquí |
| `Control+Mayús+N` | Ver todas las notas al pie |
| `Control+Alt+I` / `Control+Alt+D` | Describir una imagen / todas |
| `Control+Alt+U` / `Control+Alt+Q` | Resumir el capítulo / preguntar sobre el documento |
| `Control+Alt+P` | Definir la palabra del cursor |
| `Control+Alt+C` | Corregir este elemento |
| `F5` | Volver a analizar el documento |
| `Control+D` / `Control+Mayús+Q` | Datos del documento / cuánto queda |
| `Control+Alt+W` | Ajuste de línea |
| `Control+Alt+S` / `Control+Alt+M` | Sonidos / modo lectura |
| `Control+Alt+T` | Temporizador de apagado |
| `Control+Alt+F` / `Control+Alt+O` | Perfiles / opciones |
| `Control+Alt+G` | Datos guardados |

### Voz

| Tecla | Qué hace |
|---|---|
| `Control+Espacio` / `Control+Mayús+Espacio` | Leer o pausar / detener |
| `Control+Alt+Izquierda` / `Control+Alt+Derecha` | Frase anterior y siguiente |
| `Control+Alt+Abajo` / `Control+Alt+Arriba` | Más despacio y más deprisa |
| `Control+Alt+L` | Leer la selección |
| `Control+Alt+V` | Voz y velocidad |

### Reproductor DAISY

| Tecla | Qué hace |
|---|---|
| `Control+Alt+R` | Los mandos |
| `Control+Alt+Z` / `Control+Alt+X` | Diez segundos atrás y adelante |
| `Control+Alt+Re Pág` / `Control+Alt+Av Pág` | Punto de navegación anterior y siguiente |
| `Control+Mayús+Arriba` / `Control+Mayús+Abajo` | Subir y bajar de nivel |
| `Control+Alt+J` | Dónde estoy |

### Ayuda

| Tecla | Qué hace |
|---|---|
| `F1` | Este manual |
| `Control+F1` | Qué es el control en el que estoy |
| `Mayús+F1` | Todas las teclas |

**En cualquier lista de varias columnas**: flechas arriba y abajo para las
entradas, **izquierda y derecha para las columnas**, `Control+1` a `Control+9`
para ir a una y `Control+Inicio` / `Control+Fin` para la primera y la última. Una
celda vacía se dice «en blanco».
