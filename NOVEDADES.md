# Novedades del Visor Universal

Lo que cambia en cada versión, contado para quien lo va a usar.

Este archivo **no es decorativo**: `herramientas/empaquetar.py` lee de aquí el
apartado de la versión que se está publicando y lo mete en el campo `notas` del
`version.json`, que es lo que el programa enseña como «Novedades» al ofrecer la
actualización. Así lo que se anuncia y lo que está escrito no pueden
desincronizarse, y no hay que acordarse de rellenar a mano un archivo generado.

El formato importa: cada versión empieza por `## ` seguido del número, y lo que
va debajo hasta el siguiente `## ` es lo que se publica.

---

## 1.3.9

Esta versión va de que el programa **pese menos**: que arranque, abra sus
ventanas y se cierre sin hacer esperar.

**Arrancar con la sesión anterior, sin esperas.** Antes se abrían de golpe todos
los documentos que había abiertos al cerrar, y con varios libros grandes la
ventana se quedaba varios segundos sin atender. Ahora cada documento recupera su
pestaña con su nombre, pero solo se abre el que estaba delante; los demás se
abren al entrar en su pestaña. La sesión se guarda igual de completa que antes.

**Opciones se abre al momento.** El diálogo de Opciones montaba sus catorce
pestañas antes de enseñarse y tardaba más de un segundo. Ahora se abre al
instante y las pestañas se van montando solas mientras no se pulsa nada, de
modo que al llegar a cualquiera ya está lista, con las flechas, con
Control+Tab o con el ratón. Al aceptar solo se guarda lo de las pestañas
visitadas: las demás no han podido cambiar.

**Sin bloqueos con la IA local instalada.** Si la IA local estaba instalada
pero parada, el programa se quedaba unos dos segundos esperando cada vez que
comprobaba si estaba en marcha: al cerrar y, varias veces, al pasar a las
pestañas de inteligencia artificial de Opciones, donde llegaba a bloquearse
más de seis segundos. Ahora lo averigua al instante, y el programa se cierra
en cuanto se le pide.

**Adiós a los cierres de golpe al salir.** A veces el programa terminaba de
golpe al cerrarlo con documentos abiertos, y quedaba un informe de caída en la
carpeta de registros. La causa eran unos relojes internos —el que vigila el
cursor de cada pestaña, entre otros— que seguían en marcha después de cerrarse
su ventana. Ahora se paran todos al cerrarla.

**Más ligero en el día a día.**

- Si hay un lector de pantalla en marcha, ya no se prepara además la voz de
  Windows al arrancar, que no se iba a usar.
- Las pestañas que no se ven dejan de vigilar el cursor.
- Los menús de documentos recientes y de pestañas solo se rehacen cuando
  cambian, y ya no van acumulando trabajo a lo largo de la sesión.

## 1.3.8

**La ficha de un libro, con los datos que tú elijas.** Dentro de la ficha hay un
botón nuevo, «Elegir los datos», para marcar qué datos salen y en qué orden
(también con Alt+flecha arriba y Alt+flecha abajo). Además, el orden de fábrica
cambia: primero van el título, la serie, los autores y la sinopsis, que es lo que
se mira para decidir si leer un libro, y después lo técnico.

**Libros similares.** Un botón nuevo en la biblioteca, «Libros similares», y el
mismo menú con la tecla de aplicaciones sobre la lista: trae a la lista los
libros de la misma serie, del mismo autor, de la misma colección, con la misma
etiqueta o de la misma editorial. Con la serie, además, se ordenan por su número.

**Exportar fichas.** Las fichas de los libros marcados, o de todos los que se
ven, se guardan en texto o en CSV para una hoja de cálculo, con sus propios datos
elegidos: se puede consultar con una ficha corta y exportar una completa.

**Actualizaciones también desde GitHub.** El programa ya es de código abierto y
cada versión se publica en GitHub además de en el servidor de siempre. En
Opciones, «Avanzado», se elige dónde buscarlas: el servidor, GitHub, los dos (lo
de fábrica; si uno falla se usa el otro) o una dirección personalizada. Venga de
donde venga, solo se instala un paquete firmado por el autor.

## 1.3.7

Se ha mejorado la estimación del ritmo y del tiempo restante de lectura:

- Los saltos a secciones, las búsquedas y otras órdenes de navegación ya no se cuentan como texto leído. También se descartan avances desproporcionados del cursor para evitar velocidades disparadas.
- Si un documento tenía guardado un ritmo excesivo, se vuelve a medir conservando el tiempo acumulado.
- El porcentaje se anuncia como «Posición en el documento»: indica dónde estás, independientemente de cómo hayas llegado o de la velocidad de lectura.
- Al llegar al final se anuncia «Has llegado al final del documento», en lugar de «menos de un minuto».

El ritmo y el tiempo restante siguen siendo aproximados. Mientras se reúne una muestra suficiente, se utiliza el ritmo supuesto y se indica en el aviso.

## 1.3.6

Esta versión sigue con lo mismo que la 1.3.5 —**la biblioteca, y que aguante
bibliotecas enormes**— y por eso aquí va todo junto: primero lo nuevo de la
1.3.6 y debajo todo lo de la 1.3.5, para quien venga directamente de la 1.3.4.

**Lo nuevo de la 1.3.6:**

**La bibliografía de una biblioteca entera, en dos segundos y sin colgarse.**
Hasta ahora, para sacar la bibliografía se abría y se analizaba **cada libro**
entero solo para leer su editorial y su año, y todo en el hilo de la ventana:
con una biblioteca de calibre de casi doscientos mil libros eran horas con el
programa parado y una barra que solo decía el título del libro de turno, sin
porcentaje ni cuánto quedaba. Ahora los datos salen de la biblioteca, que ya
los tiene desde que se importó calibre o los EPUB: título, autores, editorial,
fecha e ISBN. No se abre ningún libro, y con 193.878 referencias tarda unos dos
segundos.

* **La ventana se abre al momento** y las referencias se preparan en segundo
  plano, con una barra, **el porcentaje y lo que se está haciendo** escritos al
  lado («Preparando las referencias: 12000 de 193878 (6 %)»), el avance dicho
  en voz alta cada pocos segundos y un botón para **detener**.
* **La lista ya no se atasca**: solo se monta la cita de las filas que se ven,
  así que cambiar de estilo es instantáneo tenga las referencias que tenga.
* **Copiar y guardar van también en segundo plano.**
* **Ver solo las incompletas**: un desplegable deja la lista con las
  referencias a las que les falta algún dato, que son las que hay que revisar.
  Copiar y guardar actúan sobre lo que se ve.
* **Abrir los libros incompletos es ahora una casilla**, apagada por omisión:
  es lo único lento de verdad. Si se marca, solo se abren los que se han
  quedado sin algún dato, con su avance y se puede detener.

**Las citas con varios autores salen bien.** Un libro de calibre con dos o tres
autores se citaba como si fuera uno solo con un nombre muy largo. Ahora cada
norma los pone a su manera: ISO 690 con punto y coma entre ellos, APA con sus
iniciales y «y» antes del último, MLA con el primero invertido y «et al.» a
partir de tres; en BibTeX van separados por «and» y en RIS, uno por línea, que
es lo que hace que Zotero o Mendeley los reconozcan por separado. Y el apellido
ya no se adivina cuando no hace falta: se usa la forma de cita de cada autor
que tiene calibre («Fuentes Aguirre, Armando») o que trae el EPUB.

La primera vez que abras la biblioteca después de actualizar, tus bibliotecas
de calibre se vuelven a leer solas, en segundo plano, para traer esa forma de
cita de cada autor.

**En cualquier lista, saber dónde estás e ir a un número.** En la lista de
libros, la de grupos, los resultados de la búsqueda, la bibliografía, la de
bibliotecas y carpetas, y el resto de listas de varias columnas del programa:

* `Control+I` dice en qué elemento estás y de cuántos: «Resultados de la
  búsqueda: 1 de 2484». Si hay varios marcados, también cuántos.
* `Control+G` pregunta a qué número quieres ir y te deja en él. Solo se pueden
  escribir cifras, y si el número no está entre 1 y el total se dice y no se
  mueve; las flechas arriba y abajo suben y bajan el número sin salirse.

Las dos teclas se pueden cambiar, o quitar, en Opciones → Accesibilidad.

**Registros más limpios.** Un libro con el HTML mal cerrado se lee bien —el
programa lo corrige al vuelo—, pero cada corrección se apuntaba como un error
grave: con una biblioteca grande, el registro de errores llegaba a un mega en
una sola sesión sin que hubiera fallado nada. Ahora esas correcciones se
apuntan como detalle de depuración. Y cuando se trabaja con miles de libros
seguidos (buscar en todos, abrir los libros de la bibliografía) ya no se
apuntan siete líneas por libro: solo los avisos, y un resumen de cada
importación.

**Y todo lo que trajo la 1.3.5:**

Esta versión es entera para **la biblioteca** (`Control+Mayús+B`), y sobre todo
para las grandes: ahora aguanta bibliotecas de cientos de miles de libros, se
lleva bien con calibre y no deja la ventana colgada en ningún momento.

**La biblioteca se abre al momento.** Antes, cada vez que se abría, el programa
volvía a recorrer todas las carpetas añadidas y a preguntar al disco por cada
libro, y la ventana no aparecía hasta terminar: con unos miles de libros eran
segundos de silencio, sin saber si el programa trabajaba o se había quedado
colgado. Ahora la ventana sale enseguida, los libros se cargan después con su
barra de avance, y mientras tanto se puede ir escribiendo en el filtro. Al
terminar se dice cuántos libros hay y el foco se queda donde estaba. Con una
biblioteca de casi doscientos mil libros, la carga tarda menos de dos segundos.

**Ya no hay tope de libros.** Añadir una carpeta grande se cortaba en 5000
libros sin avisar, y por eso de una carpeta con más de cien mil solo aparecían
unos cinco mil. El tope ya no existe: se recorre la carpeta entera, y se hace
**una sola vez**: lo encontrado queda guardado y la próxima vez no se vuelve a
recorrer el disco.

**Añadir una carpeta no cuelga la ventana.** Se hace en segundo plano: el avance
se ve en una barra y se dice en voz alta cada pocos segundos (cada cuántos, o
nunca, se elige en Opciones), se puede seguir usando la biblioteca mientras
tanto, se puede detener sin perder lo hecho, y al terminar sale un **resumen**
con cuántos libros son nuevos, cuántos se han puesto al día, cuántos seguían
igual, cuántos se han quitado porque ya no estaban y cuánto ha tardado.

**Las bibliotecas de calibre se reconocen solas y se importan con todos sus
datos.** Si la carpeta que añades es una biblioteca de calibre, el programa no
recorre el disco: lee directamente la base de datos de calibre, sin escribir
nada en ella, y trae todo lo que calibre sabe de cada libro: título, autores,
serie y número, etiquetas, editorial, fecha de publicación, fecha en que se
añadió, idiomas, valoración, ISBN y demás identificadores, sinopsis, formatos,
si tiene portada y **las columnas propias** que hayas creado en calibre. Y cada
libro con la ruta exacta de su archivo. Una biblioteca de calibre de casi
doscientos mil libros se importa entera en medio minuto. Si dentro de una
carpeta corriente hay bibliotecas de calibre, se importan aparte con sus datos.

**De los EPUB sueltos también se leen sus datos.** En una carpeta corriente, de
cada EPUB se sacan los metadatos que trae dentro (título, autores, serie, fecha,
idioma, editorial, materias, identificadores y sinopsis), en vez de quedarse
solo con el nombre del archivo. Al actualizar solo se releen los que han
cambiado.

**Bibliotecas y carpetas, en una ventana para gestionarlas en lote.** Desde la
biblioteca o desde Opciones se abre la lista de todas las carpetas y
bibliotecas de calibre que has añadido, con cuántos libros trae cada una, cuándo
se actualizó y si el disco está conectado. Se marcan una, varias o todas
(`Control+E`) y se puede:

* **Actualizarlas**, las marcadas o todas de una vez.
* **Quitarlas con todos sus libros**, de golpe y sin ir libro por libro. No se
  borra nada del disco ni nada de lo que hayas hecho en los libros.
* **Editarlas**: cambiarles el nombre, o la ruta cuando el disco cambia de letra
  o se ha movido la carpeta entera; los libros se recolocan al momento sin
  volver a importar.
* Hacer una **copia de seguridad** de la biblioteca entera —con por dónde vas en
  cada libro, los marcadores, las notas y las colecciones— y **restaurarla**,
  para llevarte el programa a otro equipo con toda su biblioteca.

**La ventana de la biblioteca, más completa:**

* A la izquierda, **los grupos**, y a la derecha, los libros del grupo elegido,
  como el explorador de etiquetas de calibre. Se agrupa por colección, autor,
  serie, etiqueta, editorial, idioma, formato, año de publicación, biblioteca de
  la que sale o estado de lectura. Con sesenta mil autores la lista de grupos va
  igual de ligera que con diez.
* **Se ordena** por título, autor, serie y número, fecha de publicación, los
  últimos añadidos, los últimos leídos o formato.
* **El filtro busca todas las palabras**, en cualquier orden, en el título, los
  autores, la serie, las etiquetas, la editorial y la colección, y dice cuántos
  libros quedan.
* **La ficha del libro** (`Alt+Intro` o su botón) enseña todos sus datos y la
  sinopsis en un cuadro que se recorre y se copia, con botones para abrir el
  libro o su carpeta.
* **Quitar libros de la biblioteca**, uno o muchos de una vez (`Suprimir`), sin
  borrar ningún archivo. No vuelven al actualizar; se pueden devolver desde
  Bibliotecas y carpetas.
* Las **columnas** de la lista se eligen en Opciones.

**Todo se puede ajustar** en Opciones → Biblioteca y sincronización: qué hacer
al añadir una biblioteca de calibre (importarla con sus datos, preguntar o
tratarla como carpeta), si se importan las de calibre que haya dentro de una
carpeta, si se leen los metadatos de los EPUB, si se guardan las sinopsis, si un
libro en varios formatos sale una vez o una por formato y qué formato se
prefiere, si se ponen al día las bibliotecas de calibre al abrir la biblioteca,
cada cuántos segundos se dice el avance y qué columnas tiene la lista. Cada
ajuste se explica con `Control+F1`.

Las carpetas que tuvieras añadidas en versiones anteriores se pasan solas la
primera vez que abras la biblioteca.

---

## 1.3.5

Esta versión es entera para **la biblioteca** (`Control+Mayús+B`), y sobre todo
para las grandes: ahora aguanta bibliotecas de cientos de miles de libros, se
lleva bien con calibre y no deja la ventana colgada en ningún momento.

**La biblioteca se abre al momento.** Antes, cada vez que se abría, el programa
volvía a recorrer todas las carpetas añadidas y a preguntar al disco por cada
libro, y la ventana no aparecía hasta terminar: con unos miles de libros eran
segundos de silencio, sin saber si el programa trabajaba o se había quedado
colgado. Ahora la ventana sale enseguida, los libros se cargan después con su
barra de avance, y mientras tanto se puede ir escribiendo en el filtro. Al
terminar se dice cuántos libros hay y el foco se queda donde estaba. Con una
biblioteca de casi doscientos mil libros, la carga tarda menos de dos segundos.

**Ya no hay tope de libros.** Añadir una carpeta grande se cortaba en 5000
libros sin avisar, y por eso de una carpeta con más de cien mil solo aparecían
unos cinco mil. El tope ya no existe: se recorre la carpeta entera, y se hace
**una sola vez**: lo encontrado queda guardado y la próxima vez no se vuelve a
recorrer el disco.

**Añadir una carpeta no cuelga la ventana.** Se hace en segundo plano: el avance
se ve en una barra y se dice en voz alta cada pocos segundos (cada cuántos, o
nunca, se elige en Opciones), se puede seguir usando la biblioteca mientras
tanto, se puede detener sin perder lo hecho, y al terminar sale un **resumen**
con cuántos libros son nuevos, cuántos se han puesto al día, cuántos seguían
igual, cuántos se han quitado porque ya no estaban y cuánto ha tardado.

**Las bibliotecas de calibre se reconocen solas y se importan con todos sus
datos.** Si la carpeta que añades es una biblioteca de calibre, el programa no
recorre el disco: lee directamente la base de datos de calibre, sin escribir
nada en ella, y trae todo lo que calibre sabe de cada libro: título, autores,
serie y número, etiquetas, editorial, fecha de publicación, fecha en que se
añadió, idiomas, valoración, ISBN y demás identificadores, sinopsis, formatos,
si tiene portada y **las columnas propias** que hayas creado en calibre. Y cada
libro con la ruta exacta de su archivo. Una biblioteca de calibre de casi
doscientos mil libros se importa entera en medio minuto. Si dentro de una
carpeta corriente hay bibliotecas de calibre, se importan aparte con sus datos.

**De los EPUB sueltos también se leen sus datos.** En una carpeta corriente, de
cada EPUB se sacan los metadatos que trae dentro (título, autores, serie, fecha,
idioma, editorial, materias, identificadores y sinopsis), en vez de quedarse
solo con el nombre del archivo. Al actualizar solo se releen los que han
cambiado.

**Bibliotecas y carpetas, en una ventana para gestionarlas en lote.** Desde la
biblioteca o desde Opciones se abre la lista de todas las carpetas y
bibliotecas de calibre que has añadido, con cuántos libros trae cada una, cuándo
se actualizó y si el disco está conectado. Se marcan una, varias o todas
(`Control+E`) y se puede:

* **Actualizarlas**, las marcadas o todas de una vez.
* **Quitarlas con todos sus libros**, de golpe y sin ir libro por libro. No se
  borra nada del disco ni nada de lo que hayas hecho en los libros.
* **Editarlas**: cambiarles el nombre, o la ruta cuando el disco cambia de letra
  o se ha movido la carpeta entera; los libros se recolocan al momento sin
  volver a importar.
* Hacer una **copia de seguridad** de la biblioteca entera —con por dónde vas en
  cada libro, los marcadores, las notas y las colecciones— y **restaurarla**,
  para llevarte el programa a otro equipo con toda su biblioteca.

**La ventana de la biblioteca, más completa:**

* A la izquierda, **los grupos**, y a la derecha, los libros del grupo elegido,
  como el explorador de etiquetas de calibre. Se agrupa por colección, autor,
  serie, etiqueta, editorial, idioma, formato, año de publicación, biblioteca de
  la que sale o estado de lectura. Con sesenta mil autores la lista de grupos va
  igual de ligera que con diez.
* **Se ordena** por título, autor, serie y número, fecha de publicación, los
  últimos añadidos, los últimos leídos o formato.
* **El filtro busca todas las palabras**, en cualquier orden, en el título, los
  autores, la serie, las etiquetas, la editorial y la colección, y dice cuántos
  libros quedan.
* **La ficha del libro** (`Alt+Intro` o su botón) enseña todos sus datos y la
  sinopsis en un cuadro que se recorre y se copia, con botones para abrir el
  libro o su carpeta.
* **Quitar libros de la biblioteca**, uno o muchos de una vez (`Suprimir`), sin
  borrar ningún archivo. No vuelven al actualizar; se pueden devolver desde
  Bibliotecas y carpetas.
* Las **columnas** de la lista se eligen en Opciones.

**Todo se puede ajustar** en Opciones → Biblioteca y sincronización: qué hacer
al añadir una biblioteca de calibre (importarla con sus datos, preguntar o
tratarla como carpeta), si se importan las de calibre que haya dentro de una
carpeta, si se leen los metadatos de los EPUB, si se guardan las sinopsis, si un
libro en varios formatos sale una vez o una por formato y qué formato se
prefiere, si se ponen al día las bibliotecas de calibre al abrir la biblioteca,
cada cuántos segundos se dice el avance y qué columnas tiene la lista. Cada
ajuste se explica con `Control+F1`.

Las carpetas que tuvieras añadidas en versiones anteriores se pasan solas la
primera vez que abras la biblioteca.

---

## 1.3.4

**Leer la nota al pie de aquí pasa a `Alt+Mayús+N`.** Hasta ahora era
`Control+Alt+N`, que es la combinación con la que se arranca NVDA: Windows se la
da a NVDA antes que a cualquier programa, así que al pulsarla no se leía la nota
sino que NVDA se reiniciaba. La nueva combinación no la usa ningún lector de
pantalla ni ninguna otra orden del programa. Lo demás de las notas no cambia:
`O` va de llamada en llamada, `Intro` salta a la nota y `Control+Mayús+N` abre
el visor con todas.

* Cambios menores

---

## 1.3.3

Las dos cosas de esta versión son la misma: **dónde se queda el cursor mientras
lee el lector de pantalla**.  No es un detalle de comodidad; es la diferencia
entre parar la lectura y seguir a mano, o parar la lectura y tener que buscar
por dónde ibas.

**Al parar la lectura continua, el cursor se queda en la frase que sonaba.** La
lectura continua de un lector de pantalla —`NVDA+A`— va diciendo el texto
**renglón a renglón**, y deja el cursor al principio del renglón que está
sonando. Como aquí cada párrafo es un renglón, al parar la lectura el cursor
aparecía al principio del párrafo entero: se acababan de oír veinte líneas y
había que volver a bajar por todas ellas para seguir a mano. En un ensayo con
párrafos de media página, eso es rehacer a ciegas el camino cada vez que se
para.

Ahora, con **«Empezar cada frase en un renglón nuevo»** (Opciones → Lectura, o
Herramientas → Cada frase en un renglón), el renglón es la frase: al parar, el
cursor se queda en la frase que estaba sonando, y las flechas arriba y abajo
van de frase en frase en lugar de saltar párrafos completos.

**No cambia el texto ni una sola posición.** Lo único que ocurre es que el
espacio que separa dos frases se enseña como un salto de línea, y un espacio y
un salto ocupan exactamente lo mismo. Los marcadores, las notas, los
resaltados, la búsqueda y por dónde ibas siguen apuntando al mismo carácter que
antes, el libro no se toca, y lo que se copia o se cita sale con sus espacios,
no con los saltos. Los párrafos que no traen puntuación —listas volcadas en una
línea, poesía, textos antiguos— se parten por una coma o un punto y coma, que
es donde menos se nota.

Viene apagado: quien lee con la vista no tiene este problema y un párrafo
troceado en renglones cortos se ve raro.

**Recorrer con las flechas ya no repite ni se salta texto.** Con el ajuste de
línea activado pasaba esto: se bajaba con la flecha y, cada cierto trecho, el
lector de pantalla releía algo que se acababa de oír o se dejaba un trozo sin
decir. No era el ajuste de línea ni la voz: era **la negrita y la cursiva**.

El programa las va aplicando a medida que uno avanza, porque aplicarlas de
golpe a un libro entero cuesta segundos. Y una letra en negrita ocupa más ancho
que la normal, así que dar estilo a un párrafo **cambia por dónde se parte en
renglones**. Si eso ocurría en el párrafo que se estaba leyendo, los renglones
dejaban de estar donde estaban justo debajo del cursor: la flecha abajo bajaba
un renglón, pero ya no era el siguiente.

Ahora el estilo no se toca nunca en el párrafo donde está el cursor —cada
párrafo se parte en renglones por su cuenta, así que retocar los de al lado no
descoloca nada—, y además se espera a que el cursor lleve medio segundo quieto
en vez de hacerlo en mitad de la lectura. Recorrer un capítulo entero con las
flechas ya no aplica formato ni una sola vez: se aplica al parar.

* Mejoras internas.

---

## 1.3.2

Tres cosas que se pedían y que tenían en común no poder arreglarse desde dentro
del programa: la pantalla de bienvenida no se podía quitar, un documento ya
abierto no se podía volver a analizar y el cursor solo sabía quedarse en un
sitio al parar la lectura.

**La pantalla de bienvenida se puede quitar.** Mientras no hay ningún documento
abierto, el cuadro de lectura enseña un resumen de lo que el programa sabe hacer
y con qué tecla. Es lo que hace falta el primer día, cuando no se sabe ni por
dónde empezar; cuando ya te sabes las teclas es una pantalla de más entre abrir
el programa y abrir el libro. Ahora se apaga en **Opciones →
Personalización**, desmarcando «Enseñar el resumen de teclas mientras no hay
ningún documento abierto».

Apagada **no queda una ventana en blanco**, que de oído no dice nada: no se
sabría si el programa está listo, si el documento no se ha abierto o si se ha
quedado colgado. Quedan dos líneas —el nombre del programa y «Control+O para
abrir»— y el resumen entero sigue donde estaba, en `Mayús+F1`, con todas las
teclas y su descripción.

**`F5` vuelve a analizar el documento.** Convertir un libro cuesta tiempo —y uno
escaneado, minutos—, así que el resultado se guarda y la segunda vez se abre al
instante. Eso guardado deja de valer cuando cambia el archivo o cuando cambia
algo de lo que forma parte de su firma, y ahí estaba el problema: **los ajustes
de reconocimiento no forman parte de esa firma**. Quien abrió un PDF escaneado
con el reconocimiento apagado, o con el tope de páginas por debajo de las que
tiene el libro, lo seguía abriendo exactamente igual por mucho que arreglara los
ajustes después. La única salida era ir a «Datos guardados» y borrar los del
documento, que además se lleva por delante los marcadores, las notas y las
descripciones de las imágenes.

Ahora `F5` —o **Herramientas → Volver a analizar el documento**— lo convierte
otra vez desde el archivo, sin usar nada de lo guardado, y deja el cursor donde
estaba. **No toca nada de lo tuyo.** Y al cambiar en las opciones cualquier
ajuste que afecte a cómo se convierte el documento —el reconocimiento incluido,
que antes no contaba— se ofrece volver a leerlo en ese momento.

De paso se ha arreglado esa oferta, que llevaba tiempo sin hacer nada: decía
«¿quieres volver a abrirlo?», se contestaba que sí, y como el documento ya
estaba abierto la orden se quedaba en «ya estaba abierto» sin volver a
convertir nada.

**Dónde queda el cursor al parar la lectura ahora se elige.** Al pausar o
detener, el cursor se coloca solo para poder seguir a mano sin buscar el sitio.
Hasta ahora se colocaba siempre al principio de la frase que sonaba, que es lo
que conviene cuando se para porque algo no se ha entendido: la flecha arriba
vuelve a leer justo eso. Pero cuando se para para **seguir leyendo a mano**, eso
hace que las flechas repitan el párrafo que se acaba de oír.

En `Control+Alt+V → Al leer` está ahora **«Al pausar o detener, dejar el
cursor»**, con las dos opciones: al principio de esa frase —lo de siempre, y lo
que sigue viniendo de fábrica— o justo detrás de ella, y entonces las flechas
siguen por lo que aún no ha sonado. Volver a dar a leer retoma donde estaba en
los dos casos: la frase que quedó a medias se termina, no se pierde.

---

## 1.3.1

Las voces que se añaden al programa ya no pueden tumbarlo, y las notas al pie se
leen enteras, solas y todas juntas en una ventana propia.

**Un motor de voz ya no puede llevarse el programa por delante.** Podía pasar
—y pasaba— que al pulsar «Probar» se cerrara la aplicación entera: no un error,
ni un aviso, sino la ventana desapareciendo con el libro abierto. Un motor puede
traer bibliotecas que no son de Python, y con esas no hay red: lo que falle ahí
dentro no se puede capturar y se lleva el proceso.

Lo que lo provocaba no estaba en el programa ni en el motor, sino en una regla
de Windows: **cuando una biblioteca pide otra por su nombre, recibe la primera
que ya esté cargada con ese nombre**, venga de donde venga. Y en un equipo puede
haber otro programa —un adaptador de voces, el complemento de un lector de
pantalla— con una copia más vieja de esas mismas bibliotecas. Esa copia entra en
cuanto se prepara la voz del sistema, que es lo primero que hace el programa al
abrirse; y cuando el motor pedía las suyas, se encontraba con las ajenas. Al no
casar las versiones, eso no da un error: tira el proceso entero.

Ahora un paquete puede declarar qué bibliotecas necesita tener cargadas, y el
programa las mete en el proceso al arrancar, antes de tocar nada de voz. Cuesta
unas centésimas y solo lo paga quien tenga ese motor instalado.

Tiene una consecuencia que conviene saber: dos versiones de la misma biblioteca
no caben en un programa, así que **gana la del motor instalado**. Si tenías otro
programa que ofrecía esas mismas voces por otro camino, esas voces suyas dejarán
de aparecer mientras el motor esté instalado. No se pierde nada: son las mismas,
y por el motor vienen con todos sus ajustes.

Se han cerrado además los dos sitios por donde también pasaba. Uno, que la voz
se generaba en el mismo hilo que atiende la ventana: ahora eso ocurre aparte, y
de paso la ventana ya no se queda quieta esas décimas —lo que antes tardaba tres
décimas en devolver, ahora vuelve al instante—. Y dos, el orden en que se
sueltan las piezas al cambiar de motor: la que recibe el sonido se soltaba a
veces antes que la que lo genera, y esa seguía llamando a algo que ya no estaba.
Ahora se sueltan una a una y en orden.

**Si un día vuelve a pasar, quedará escrito.** Cuando un programa se cae dentro
de código que no es de Python no hay excepción, ni traza, ni una línea en el
registro: la ventana desaparece y no queda nada. Ahora sí queda: se escribe un
archivo `caida_<fecha>.txt` junto al registro, con lo que estaba haciendo cada
hilo en ese instante. No evita el porrazo —eso no se puede— pero es la
diferencia entre poder arreglarlo y no. Y al generar la primera frase se apunta
antes de entrar en la biblioteca y después de salir, así que la última línea del
registro dice dónde estaba.

**Un motor que no puede hablar ahora lo dice.** Podía pasar que un motor
arrancara, listara sus voces y no sonara: le falta la clave con la que se abren
sus modelos, o los datos de una voz. Pulsar «Probar» en ese caso no hacía
absolutamente nada: ni sonido, ni aviso, ni pista de qué faltaba, y desde fuera
no se distingue de un programa colgado. Ahora un motor puede explicar en una
frase por qué no va a sonar, y esa frase sale en un cuadro al probar. Es
opcional: un motor que siempre suena no tiene que decir nada.

**Un motor que se reinstala estando en uso ahora avisa.** Las bibliotecas que no
son de Python no se descargan hasta que el programa se cierra, así que
reinstalar un motor que estabas usando deja sus archivos viejos abiertos y los
nuevos sin poder cargarse. Antes eso se descubría al probar la voz; ahora se
dice al instalar, que es cuando aún se puede hacer algo: cerrar y volver a
abrir.

**Los motores se descargan aparte, y ahora se dice bien.** Entre todos ocupan
casi un giga, así que no van dentro del programa: quien lo instala no tiene por
qué bajárselos para leer, ni volver a bajárselos con cada actualización. Se
descargan del mismo sitio que el visor y se instalan desde Voz → Lectura en voz
alta → Motores de voz → Agregar. La ayuda decía que venían en una carpeta al
lado del ejecutable, que es donde están al compilar en casa pero no en lo que se
reparte, y quien la buscaba no la encontraba. Ya está corregida, y dice además
lo que importa: **para leer no hace falta instalar ninguno**, porque la voz de
Windows viene con el programa y no se puede quitar.

**Leer una nota al pie se para donde la nota acaba.** `Control+Alt+N` leía desde
el principio de la nota hasta el final de su párrafo. En casi cualquier libro
eso coincide, pero en una edición muy anotada las notas van **todas seguidas
dentro del mismo párrafo**: pedías la 18 y te leían la 18, la 19 y media 20.
Medido sobre un volumen de discursos clásicos, **512 de sus 515 notas** se leían
con texto que no era suyo. Ahora se para en lo primero que aparezca —el final
del párrafo, el número con el que empieza la de al lado, o la flecha de volver
al pasaje—, y esa flecha ya no se lee, que es un botón y en voz alta no dice
nada.

**Y están todas juntas, en un visor propio.** `Control+Mayús+N` abre la lista
entera de notas del libro, cada una con su texto completo debajo, que cambia
según te mueves con las flechas. Se abre por la nota más cercana a por donde
ibas leyendo, tiene un buscador que filtra según escribes —y que no distingue
tildes ni mayúsculas: escribiendo «isocrates» salen las de «Isócrates»— y de
cada nota se puede ir **a donde se cita**, ir **a la nota**, o copiarla.

Hasta ahora las notas solo se podían ver de una en una: ir, oírla y volver. En
un volumen con quinientas, eso son quinientos viajes. Con ese mismo libro: las
quinientas se sacan en dos milésimas y recorrerlas enteras con las flechas
cuesta tres décimas de milisegundo cada una.

Y aparecen también en la lista de elementos de `F7`, como «Llamadas de nota»,
que era donde había que buscarlas y no estaban.

**Esto que estás leyendo se puede volver a leer cuando quieras.** En `Ayuda →
Ver las últimas novedades` se abre en el navegador lo que ha traído cada
versión, la más reciente arriba. Antes esto solo pasaba por delante una vez, en
el aviso de la actualización, y solo de la versión que llegaba.

---

## 1.3.0

Los PDF corrientes —los que no están etiquetados, que son la inmensa mayoría—
se recorren ya como un libro, y el programa dice qué le pasa a cada documento y
qué se puede hacer al respecto.

**Los PDF normales ya tienen encabezados, tablas y enlaces.** Hasta ahora solo
se recorrían con H, T y L los PDF etiquetados, que son la minoría. El resto se
abrían como un churro de texto en el que no se sabía dónde empezaba cada
apartado. Ahora el programa **mide** cada página y deduce lo que el archivo no
dice: los títulos por su tamaño de letra y por su numeración, las listas por
sus viñetas, las tablas por cómo se alinean sus columnas, y los enlaces por
dónde están dibujados. En un documento con cuatro apartados evidentes, antes se
encontraban cero encabezados; ahora, los cuatro, y con sus niveles bien
anidados. Se apaga en Opciones → PDF si en algún archivo concreto estorba.

**Y también las imágenes, con su descripción.** Las fotografías, los gráficos y
los esquemas de un PDF corriente se encuentran ahora aunque el archivo no diga
que están ahí: los dibujos, porque sus trazos se agrupan en una zona de la
página; las fotografías, porque son imágenes de verdad. Se recorren con `G`, se
ven con `Control+I` y **se describen con inteligencia artificial igual que en un
EPUB** (`Control+Alt+I` una, `Control+Alt+D` todas), y esa descripción se guarda
y vuelve con el documento. Si la figura lleva un pie —«Figura 4. Ventas por
trimestre»— se lee como pie; si el pie solo la numera —«Figura 3»— la figura
sigue contando como pendiente de describir, porque un número no dice qué se ve.

**Y el resto de lo que trae un PDF.** Notas al pie, que se reconocen por estar
abajo, en letra menor y numeradas, con su llamada volada marcada para poder
saltar a ellas; citas en bloque, por su sangría; negritas y cursivas, que están
en la fuente de cada palabra; filetes que separan secciones, distinguidos de las
rayas de la cabecera y de los bordes de las tablas; y **los comentarios y notas
adhesivas que alguien haya dejado en el PDF**, que hasta ahora se perdían
enteros y muchas veces son lo más importante de la página.

**Los niveles de título no se saltan.** Los títulos no se puntúan uno por uno:
se mira qué tamaños de letra usa **el documento entero** para titular y se
numeran de mayor a menor. Así el segundo nivel es siempre el dos, aunque el
maquetador eligiera 13 puntos en vez de 14, y al moverse por niveles no falta
un peldaño.

**Los textos a dos columnas se leen columna por columna.** Un artículo o un
periódico a dos columnas se leía saltando de una a otra en cada renglón. Ahora
se lee entera la izquierda y después entera la derecha. Y una tabla sin líneas
sigue leyéndose como tabla, que es lo que costaba distinguir.

**Los PDF con contraseña se abren.** Un PDF puede llevar dos contraseñas muy
distintas y antes se trataban igual. La de propietario, que solo prohíbe
imprimir o copiar y que llevan casi todos los artículos de revista y los
boletines oficiales, se salta sola: esos documentos se abren sin preguntar
nada. La de usuario, que sí hace falta para leer, se pide en una ventana al
abrir el libro.

**Los PDF dañados se abren igual.** Si a un archivo se le ha roto el índice
interno —por una descarga cortada, por un servidor que le añadió una línea— el
programa lo reconstruye en una copia y lee de ahí. **El archivo original no se
toca nunca.**

**Las páginas escaneadas ya no se cuelan.** Una página fotografiada casi
siempre trae algún texto de verdad: su número, un sello, una marca de agua. Con
eso pasaba por «página con texto» y se quedaba sin reconocer, y el lector
recibía una página en la que solo se leía «118». Ahora se mira **dónde** cae
ese texto: si el cuerpo de la página está vacío, la página se reconoce aunque
tenga caracteres.

**El informe de accesibilidad dice qué falta y qué hacer.** Control+D añade
ahora lo que le falta al documento y cómo remediarlo, citando la norma para
quien quiera arreglar el original: si no declara idioma y por eso se leerá con
otra voz, si sus tablas no marcan los encabezados de columna y por eso no se
podrá anunciar de qué columna es cada dato, si la jerarquía de títulos se salta
niveles, cuántas imágenes están sin describir, si el archivo lleva JavaScript
—que se detecta y nunca se ejecuta—, adjuntos o firmas. Y avisa siempre de que
son comprobaciones automáticas y parciales: detectan lo que falta, no
garantizan que el documento se lea bien.

**Un PDF de puras imágenes se puede abrir tal como está, sin reconocerlo.**
Lo pidió un usuario del foro y tenía razón: un cómic, un manga o un álbum
escaneado no tienen texto que sacar, y pasarlos por el reconocimiento da un
revoltijo de palabras sueltas en el orden en que estuvieran las viñetas. Pero al
apagar el reconocimiento el programa se negaba a abrirlos. Ahora hay una opción
más en `Opciones → Reconocimiento`: **«enseñar las páginas escaneadas como
imágenes»**. Con ella el documento se abre tal cual, **cada página es una
imagen**, se recorren con `G`, se ven con `Control+I` y se describen con
inteligencia artificial, que en un cómic es lo único que de verdad cuenta lo que
pasa. Y el aviso de «este PDF está escaneado» ahora explica esa salida en vez de
dejar al usuario sin opciones.

**Ya no se pierde ninguna imagen al exportar.** De las 136 imágenes de un PDF de
prueba se escribían 111: las 25 que faltaban caían justo donde había un salto de
página, y el recorrido escribía **un solo elemento por sitio**, así que el salto
se llevaba la imagen por delante. Ahora los saltos de página y los separadores
se escriben aparte —no son contenido, son señales— y en el mismo sitio caben las
dos cosas. Salen las 136. El mismo fallo afectaba a ver un capítulo con
`Control+Mayús+H`.

**Lo que el programa deduce de un PDF ya se puede guardar.** Es lo más
importante de esta versión. Hasta ahora, todo lo que el programa averigua de un
PDF sin estructura —sus títulos, sus tablas, sus listas, sus bloques de código,
la descripción que la inteligencia artificial pone a cada imagen— vivía dentro
del programa y moría al cerrarlo. Ahora **se exporta a un EPUB accesible** que
se abre en cualquier lector: de un PDF de 498 páginas sin una sola etiqueta
salen 353 títulos, 65 listas, 3 tablas y 1575 bloques de código, y **su índice
navega de verdad** (antes todas las entradas llevaban al principio del libro).

El EPUB declara además, en sus metadatos, qué trae para poder leerse: con qué
sentidos se puede leer, qué recursos de accesibilidad tiene y qué riesgos no
tiene. Es lo que la **ley europea de accesibilidad** exige desde junio de 2025,
y se declara **solo lo que es verdad**: cada rasgo se comprueba sobre el
documento antes de escribirlo, porque un libro que dijera traer descripciones
sin traerlas sería peor que uno que no dijera nada.

**Exportación a braille.** Un archivo `.brf` con el documento transcrito a
braille español de grado 1, 40 celdas por línea y 25 líneas por página, listo
para una impresora braille o un anotador. Es la única forma de **sacar el libro
del ordenador**: quien lee en braille lee lo que su lector de pantalla le manda
a la línea, pero para llevarse un documento hace falta un archivo.

**Se avisa de los libros que pueden hacer daño.** Un EPUB puede declarar que
contiene destellos, y un destello puede provocar una crisis a quien tenga
epilepsia fotosensible. Eso ya no se queda perdido en una lista de propiedades:
se dice **por delante de todo lo demás** al abrir el libro.

**Las letras capitulares dejan de leerse sueltas.** La inicial grande con la que
empieza un capítulo va, en muchos libros, en su propio bloque, y el lector de
pantalla decía «E. rase una vez». Ahora se junta con lo que sigue. Es de las
molestias más repetidas por quien lee así.

**Modo lectura (`Control+Alt+M`).** Apaga de una vez los sonidos, el aviso de
los elementos, la barra de estado y el árbol de contenido, para leer una novela
de un tirón. Al volver a pulsarlo se recupera **exactamente** lo que tuvieras
puesto, no lo que viene de fábrica.

**Se abren los cómics** (`.cbz`, `.cbt`, y los `.cbr` que por dentro son un
ZIP). Un cómic es una carpeta de imágenes y no tiene texto, así que hasta ahora
era un archivo que no había forma de abrir. Con la descripción por inteligencia
artificial sí la hay: cada página es una imagen del documento, se recorren con
`G` y se describen de una en una o todas de golpe, y la descripción se guarda.

**El RTF se lee entero, no como un churro de texto.** Hasta ahora un RTF se
abría con un complemento que devuelve **texto plano**: un documento de
doscientas páginas se abría sin un solo título, sin listas y sin tablas, y en
un equipo sin ese complemento ni se abría. Ahora hay un lector propio que
entiende el formato de verdad: **títulos** —por el nivel de esquema del párrafo
y, si no lo trae, por el nombre de su estilo, que Word traduce a cada idioma—,
**negrita, cursiva y subrayado**, **listas**, **tablas** con su fila de
encabezados, **enlaces**, **imágenes** y los metadatos del documento. En un RTF
de dos megas eso son 72 títulos y 376 pasajes en cursiva donde antes había
cero. Y **una dependencia menos**: ya no hace falta instalar nada.

**Un texto guardado como «Unicode» ya no se abre como basura.** El Bloc de
notas de Windows guarda en UTF-16 cuando se elige esa opción, y esos archivos
se leían con un byte nulo entre cada dos letras. Ahora se mira primero la marca
que el archivo lleva al principio para decir en qué codificación está —UTF-8,
UTF-16 y UTF-32, en sus dos órdenes—, que es la única señal fiable que hay:
probar codificaciones a ver cuál no falla no sirve, porque un UTF-16 se deja
decodificar mal sin protestar.

**Los libros «Print Replica» de Kindle (AZW4).** Por fuera son un contenedor de
Kindle y por dentro un PDF entero. Se saca el PDF y se lee con el lector de PDF
del programa, así que traen de golpe todo lo que este sabe hacer con uno:
estructura deducida, reconocimiento óptico si hace falta e informe de
accesibilidad.

**Se abre desde el explorador de archivos, y solo con lo que tú digas.** En
`Opciones → Integración con el sistema` hay una lista con los 28 formatos que
el programa abre, y marcas los que quieras. En esos —y solo en esos— aparece
**«Abrir con Visor Universal»** al pulsar el botón derecho, y el programa figura
en el «Abrir con» de Windows. Lo que no marques se queda exactamente como
estaba: no se cambia con qué programa se abre nada.

Se escribe **solo para tu usuario**, así que no hace falta ser administrador. Y
**si mueves la carpeta del programa, la integración se rehace sola** al abrirlo:
es portátil y está pensado para que lo sea. Al abrir un archivo desde el
explorador con el programa ya en marcha —aunque esté escondido en la bandeja—,
la ventana vuelve al frente con el documento abierto y respetando lo que tengas
puesto sobre pestañas.

Dos cosas que conviene saber, y que no dependen de este programa: en Windows 11
la orden sale en «Mostrar más opciones» —el menú corto está reservado a los
programas instalados desde la tienda—, y **ponerse como programa predeterminado
no lo puede hacer ningún programa por su cuenta** desde Windows 8. Para eso hay
un botón que abre la ventana de Windows donde se elige.

**Se leen los libros de Kindle.** Los tres formatos que ha usado Amazon en
veinte años, **sin DRM** y sin instalar nada:

- **KFX** (`.kfx`, `.kfx-zip`), el de ahora. No lleva HTML dentro: es un
  contenedor binario con miles de piezas numeradas que se apuntan unas a otras,
  y hay que reconstruir el libro pieza a pieza. Se ha hecho comparándolo contra
  el EPUB del mismo libro: de 736.854 letras salen las mismas 736.854, los
  mismos 72 títulos y las mismas 75 entradas de índice. Y **trae 267 pasajes en
  cursiva que ese EPUB había perdido por el camino**.
- **AZW3** (`.azw3`, `.azw`), el anterior. Guarda el XHTML del libro partido en
  dos mitades —los esqueletos y sus fragmentos— y hay que volver a coserlo. El
  resultado es carácter por carácter idéntico al EPUB del mismo libro.
- **MOBI** (`.mobi`, `.prc`, `.azw`), el original. Un HTML enorme comprimido,
  con dos compresiones distintas —una de ellas un Huffman con diccionario— y
  las anclas puestas por posición de byte.

Los tres se recorren **igual que un EPUB**: `H` para los títulos, `K` para los
enlaces, `G` para las imágenes, índice con `F5`, marcadores, resaltados y
lectura en voz alta.

**Un MOBI no marca sus títulos**: el generador de Amazon deja los capítulos
como párrafos con letra más grande, así que un MOBI se abría sin un solo
encabezado. Se recuperan de su **índice interno**, que va en registros aparte y
con un formato propio. En *Moby Dick* eso son 146 capítulos que antes no
existían.

**Las imágenes de un KFX se emparejan comprobándolo, no suponiéndolo.** El
nombre de cada imagen vive en una tabla de símbolos que no viaja dentro del
archivo, así que la correspondencia hay que reconstruirla: se hace comparando
las medidas que el libro declara con las que trae la imagen en su propia
cabecera. De quince imágenes de tres libros, las quince cuadran.

**El informe de accesibilidad comprueba el triple.** `Control+D` pasaba una
docena de reglas de PDF/UA; ahora pasa cerca de treinta, todas escritas como
código propio y sin añadir ni una dependencia ni un megabyte. Las nuevas salen
del **anidamiento**, que es la mitad de la norma y lo que más se nota al leer:
filas fuera de su tabla, celdas fuera de su fila, puntos de lista sin su cuerpo,
entradas de índice sueltas. Existen en el archivo, pero el lector de pantalla no
puede anunciarlas como lo que son: una celda que no cuelga de una fila no tiene
columna, y sin columna no hay encabezado que decir. Se comprueban con la cuenta
de pares padre-hijo que el recorrido del árbol ya hacía, así que no cuesta nada.

También se avisa ahora de las **etiquetas que el documento se inventa** sin decir
a qué equivalen —se leerán como texto suelto— y de las de la norma a las que les
cambia el significado; de los **formularios XFA dinámicos**, que no llevan texto
que leer; de las **capas que se encienden solas**, con lo que lo que se lee puede
no ser lo que se ve; de las **fuentes con la codificación mal declarada**, que es
lo que hace que el texto salga con las letras cambiadas; y de si el archivo
declara cumplir PDF/UA.

Cada aviso se ha acotado para que **solo salte cuando importa**: casi todo lo que
sale de Word dice que su etiqueta «Artifact» equivale a un párrafo aunque no use
ni una, y quejarse de eso sería quejarse en todos los documentos de algo que no
le pasa a ninguno. De los cuatro PDF etiquetados con los que se probó, los dos
bien hechos no producen ninguna queja.

**El código de los PDF etiquetados también se recorre.** La etiqueta `Code` está
definida en la norma para el código de dentro de una frase, pero los generadores
la usan también para el bloque entero. Cuando viene así se trata como bloque: en
un manual de accesibilidad web de prueba, eso son 37 bloques que antes eran
párrafos sueltos y ahora se saltan con `X` y se copian con su botón.

**El código fuente es un elemento más, y se copia con un botón.** En un LÉAME
de GitHub, en un manual técnico o en un PDF de programación, el código era hasta
ahora texto suelto sin más. Ahora es un elemento como una tabla o una lista: se
salta de uno a otro con `X`, se sale del bloque con `Z`, suena distinto —tres
toques secos, como una máquina de escribir—, aparece en el árbol de contenido y
en `F7`, y **conserva la sangría tal cual**, que en un lenguaje como Python no
es presentación sino sintaxis. Con `Control+H` se abre en el visor, y allí hay
un **botón para copiarlo al portapapeles** que copia el código y solo el código,
con su sangría, listo para pegar; el botón funciona igual dentro del programa y
en la página guardada abierta después en el navegador. Si el documento declara
el lenguaje se dice: «Bloque de código Python».

**Los LÉAME de GitHub se entienden enteros.** El conversor de Markdown no sabía
nada de los bloques vallados con tres comillas invertidas: las vallas se leían
como texto y cada renglón del ejemplo salía como un párrafo suelto. Ahora se
reconocen, con su lenguaje si lo declaran.

**El código de los manuales técnicos se lee como código.** En un PDF, un
bloque de código no está marcado en ninguna parte: lo único que lo distingue
del texto es que va en letra de máquina de escribir. Al no verlo, sus renglones
se unían como los de un párrafo, y diez sentencias se leían de corrido —«jump(-60)
n = 7 radius = 60 angle = 60»—, mezcladas además con el párrafo de al lado. Ahora
esa letra **se reconoce midiéndola** (que la «i» y la «m» ocupen lo mismo es lo
que la define; el nombre de la fuente no dice nada), cada renglón se queda en su
sitio y **se conserva la sangría**, que en Python no es presentación sino
sintaxis. Si el documento entero está escrito a máquina —un listado, un informe
antiguo— no se toca nada: esa es su letra normal y no señala nada.

**El fondo gris de un recuadro ya no es una imagen.** Un bloque de código o un
aviso enmarcado se pintan como un rectángulo relleno con el texto encima. Ese
rectángulo se estaba anunciando como una imagen y se ofrecía para describirlo
con la inteligencia artificial, que poco podía decir de un rectángulo gris. Se
distingue ahora de un gráfico de verdad por el texto que lleva dentro: si lo
llena de arriba abajo, renglón tras renglón, es un fondo; si son rótulos
sueltos repartidos por la zona, es un gráfico y se conserva.

**Las palabras ya no se pegan en letra pequeña.** El texto a nueve puntos —notas
al pie, manuales técnicos, documentos a dos columnas— salía escrito de corrido:
«Solaris2.2mayrequiresetting». El hueco que separa dos palabras se medía en una
cantidad fija de puntos, mayor que lo que ocupa un espacio en letra pequeña, así
que el renglón entero se leía como una sola palabra. Ahora se mide **en
proporción al cuerpo de la letra**, de modo que un espacio es un espacio tanto
en un titular como en una nota al pie. En un manual de 500 páginas eso ha
sacado a la luz 318 enlaces y 218 negritas que estaban ahí y no se veían.

**Las palabras ya no se parten.** En los documentos compuestos en versalitas
—muy comunes en textos jurídicos y académicos— la letra inicial de cada palabra
va escrita unos puntos más grande, y eso hacía que el texto saliera «I NSTITUTO
DE E STUDIOS» en vez de «INSTITUTO DE ESTUDIOS». Ya no: el hueco entre dos
trozos de texto se mide ahora en proporción al tamaño de la letra, no en una
medida fija, y el estilo de cada palabra se averigua por sus letras en lugar de
pedírselo al extractor, que era quien las partía.

**El ajuste de línea se queda como lo dejas.** La casilla «Ajustar las líneas al
ancho de la ventana» volvía a aparecer desmarcada por mucho que se marcara: al
aplicarla se invertía una vez por documento abierto, así que con uno solo delante
volvía a quedarse como estaba. Además, ahora `Control+Alt+W` cambia el ajuste en
**todas** las pestañas y no solo en la de delante.

**Renglones más cortos, si quieres.** En Opciones → Lectura puedes fijar un ancho
máximo de renglón en caracteres. Un renglón muy largo es incómodo de seguir: al
llegar al final hay que volver al principio del siguiente, y cuanto más largo sea
más fácil es perderse. **No cambia el texto ni una sola posición**: lo que se
estrecha es la columna, dejando márgenes; los marcadores, las notas y por dónde
ibas siguen exactamente donde estaban.

**Resaltados.** Selecciona un texto y pulsa `Control+Alt+E` para resaltarlo;
`Control+Alt+K` enseña la lista de todos los del documento, para ir a ellos,
quitarlos o **guardarlos en un archivo**, cada uno con su página, para repasar
después las ideas de un documento. Se puede guardar en **texto plano** —lo
universal—, en **Markdown** —para una libreta de notas, con cada pasaje como
cita— o en **HTML**, para abrirlo en el navegador. Se guardan con el libro, como
los marcadores, y vuelven al reabrirlo.

**Volver a lo que estabas leyendo.** En Opciones → Pestañas puedes pedir que al
abrir el programa se recuperen los documentos que dejaste abiertos, cada uno por
donde ibas. Viene apagado: quien abre el programa para leer una cosa concreta no
quiere media biblioteca abriéndose delante. Si abres un libro haciendo doble clic
sobre él, se abre ese y no se recupera nada.

**Las notas de los libros anotados ya se reconocen como notas.** Casi ningún
libro declara sus llamadas de nota: son un enlace corriente a la sección de
notas, con el número entre corchetes. Sin reconocerlas, la tecla `O` no
encontraba **ninguna nota** en un libro con quinientas, y `K` recorría los
enlaces mezclando las llamadas con todo lo demás. Ahora se reconocen por su
forma —un número entre corchetes o en superíndice que lleva a un sitio del
propio libro— y con eso funcionan `O` para ir de nota en nota, `Control+Alt+N`
para leer la nota sin moverse del sitio y la lista de elementos de `F7`. Medido
sobre el volumen 2 de los *Discursos* de Isócrates: de 0 a **515 notas**
encontradas.

**Una llamada de nota ya no suena igual que un enlace.** En un libro anotado
—unos discursos clásicos, por ejemplo— en el texto salen números de dos clases:
unos son llamadas de nota y otros referencias al pasaje. Los dos son enlaces, y
los dos hacían **el mismo pitido**, así que no había forma de saber cuál era
cuál. Ahora la llamada de nota tiene su propio sonido, distinto del de un enlace
corriente.

**Y se puede pedir que los elementos se digan, no que suenen.** En Opciones →
Sonidos puedes elegir cómo se avisa de lo que hay en cada línea: con un sonido
—lo de siempre—, **diciéndolo con la voz**, con las dos cosas o con ninguna. La
voz existe porque el pitido tiene un límite: solo puede sonar **uno por línea**,
así que en una línea que lleva un salto de página y una llamada de nota suena el
salto de página y la nota se queda sin señalar. En un libro muy anotado eso es la
mitad de las notas, y es la razón de que el pitido pareciera aparecer y
desaparecer sin motivo. Dichos, se oyen todos.

**Y se puede oír «nota» en la lectura continua.** Los sonidos del programa
acompañan al cursor, así que en la lectura continua del lector de pantalla
—`NVDA+A`— el cursor no se mueve y no puede sonar nada. Lo único que se oye ahí
es el texto, y una llamada de nota es un número suelto que suena igual que
cualquier otro número: en una edición clásica, igual que el de la cita. Con la
casilla «Decir "nota" en las llamadas de nota» (Opciones → Lectura) el texto
dice «nota 12» en lugar de «12», y así se distingue oyendo. Viene apagada
porque alarga el texto.

**Los gráficos, en números.** Describir un gráfico no basta: un lector de
pantalla puede decir «gráfico de barras de ventas por trimestre» y quien escucha
sigue sin saber ni un solo número. En la ventana de descripción de una imagen hay
ahora un botón **«Sacar los datos»**: le pide a la inteligencia artificial los
valores en vez de una descripción, y lo que vuelve se guarda **como una tabla**
que se recorre celda a celda con `Control+H`, oyendo el encabezado de cada
columna. Los datos se suman a la descripción, no la sustituyen —la descripción
dice de qué va y la tabla dice cuánto—, viajan con el libro exportado a EPUB, y
si la imagen no es un gráfico con valores se dice y no se guarda nada, porque una
tabla inventada parecería un dato.

**La biblioteca, y buscar en todos los libros a la vez.** `Control+Mayús+B` abre
todos tus libros en una lista, con su autor y por dónde vas en cada uno, y se
pueden añadir carpetas para que aparezcan también los que nunca has abierto. Lo
que de verdad cambia las cosas si estudias es el campo de búsqueda: escribe una
frase y aparece en qué página de qué libro está, con el trozo de texto donde
sale, **y al pulsar Intro se abre ese libro en ese punto**. Buscar una cita en
cuarenta PDF abriéndolos de uno en uno no lo hacía nadie.

**Seguir donde lo dejaste, en otro equipo.** En Opciones → Biblioteca y
sincronización se elige una carpeta que ya sincronices por tu cuenta —Dropbox,
OneDrive, Drive, un pendrive, una carpeta de red— y el programa deja ahí una copia
de por dónde vas en cada libro, de tus marcadores, de tus notas y de las
descripciones de imágenes. Al abrirlo en el otro equipo se junta con lo que haya,
libro por libro y sin perder nada: gana la versión más reciente y los marcadores
de los dos sitios se suman. No hace falta ninguna cuenta ni ningún servicio, y las
preferencias **no** se sincronizan: la voz que tienes en casa puede no estar en el
trabajo.

**Copiar con la cita hecha.** `Control+Mayús+C` copia el pasaje seleccionado con
su referencia bibliográfica montada: autor, título, editorial, año y la página en
la que estabas. En ISO 690, APA, MLA o en una frase sencilla, y la referencia se
puede corregir antes de copiar. Lo que el documento no diga no se inventa: se
avisa de lo que falta.

**Cuánto queda.** `Control+Mayús+Q` dice cuánto falta para terminar el capítulo y
el libro, en minutos, al ritmo al que lees tú. Con la vista eso se ve por el
grosor de lo que queda; de oído no había forma de saberlo.

**Las fórmulas químicas se leen.** Las matemáticas ya se leían; la química no.
`H2SO4` sonaba «hache dos ese o cuatro», que además confunde la letra O con el
cero. Ahora se dice **«hidrógeno 2 azufre oxígeno 4»**, que es como lo dicta un
profesor, y también la carga de un ion, el estado de agregación y la flecha de
reacción. Viene en automático: solo se aplica a los documentos que traen química
de verdad, así que en una novela no cambia nada.

**Lo que no se quiere oír al leer de corrido.** Con la vista, el ojo se salta solo
la cabecera repetida de cada página, el folio del pie y el numerito volado de una
nota; de oído suena todo, y suena en medio de la frase. Tres casillas nuevas en
Voz permiten no oírlos. Las cabeceras repetidas se reconocen midiendo: se miran
las dos primeras y las dos últimas líneas de cada página y se toma por cabecera lo
que sale en al menos un tercio de ellas.

**Exportar a libro DAISY.** El programa leía DAISY desde hace tiempo; ahora
también lo escribe. `Archivo → Exportar → Libro DAISY` genera una carpeta en
DAISY 3 —el formato de las bibliotecas para personas ciegas de todo el mundo— con
el texto, el índice y las páginas; y, si se quiere, **con la voz sincronizada
frase a frase**. Generar un DAISY a partir de un PDF recién reconocido es
justamente lo que no se podía hacer sin herramientas de pago.

**Braille en XML, y braille matemático.** Además del BRF de siempre se exporta a
**PEF**, que es el braille ya compuesto guardado en XML, lleva dentro el título y
el autor y es lo que se intercambian las bibliotecas y las imprentas braille de
Europa. Y en los dos, **las fórmulas salen en braille matemático** siguiendo el
Código Matemático Unificado para Iberoamérica: el signo de número, los índices,
las raíces, las fracciones. Lo que ese código no cubre —integrales, matrices— se
escribe hablado, como antes: una fórmula mal transcrita sería peor que una dicha
con palabras.

**Marcas de capítulo en el audio.** Al exportar a audio hay un reparto nuevo: un
solo archivo **con sus capítulos dentro**, para poder saltar de uno a otro en el
reproductor del móvil o del coche en vez de tener diez horas seguidas por las que
solo se avanza a ciegas. En MP3 van dentro del archivo; en WAV se deja al lado una
hoja de pistas `.cue`.

**El EPUB exportado se comprueba antes de darlo por bueno.** Había informe de
accesibilidad para lo que se lee y no lo había para lo que se escribe. Ahora, al
exportar a EPUB, el programa revisa lo que acaba de escribir: el envoltorio, los
metadatos de accesibilidad, el índice y sus enlaces, los niveles de encabezado,
las imágenes sin describir y las tablas sin encabezados.

**La inteligencia artificial revisa la estructura deducida.** En un PDF sin
etiquetar el programa acierta casi siempre, y cuando falla, falla de formas
reconocibles: un índice tomado por capítulos, un pie de página tomado por un
título. Ahora se le puede mandar a la IA **el esqueleto** del documento —los
títulos y el tipo de cada bloque, sin el texto del libro— para que señale lo que
cante. Lo que propone se enseña como una lista y se acepta una a una: nada se
aplica solo, porque una corrección equivocada esconde texto.

**Correo guardado y páginas web.** Se abren los `.eml` de Outlook o Thunderbird y
los `.mht` de Edge o Chrome. Del correo se lee primero quién escribe, a quién,
cuándo y de qué, después el cuerpo con toda su estructura, y al final lo que venía
adjunto. Y de cualquier página guardada el programa **se queda solo con el
artículo**: fuera los menús, el aviso de galletas y la columna de «lo más leído».
Si el recorte no se puede decidir con seguridad, la página se lee entera.

**Los archivos de ayuda de Windows se abren.** Los `.chm` —la documentación
técnica de los años noventa y dos mil, que en ingeniería sigue siendo la única
que hay de muchas cosas— eran hasta ahora un archivo que no se podía abrir de
ninguna manera. Ahora se leen enteros, con sus doscientas páginas **en el orden
de su índice** y con el título que el manual le da a cada una, así que se
recorren con `H` y aparecen en el árbol de contenido. Por dentro van comprimidos
con un algoritmo propio de Microsoft que Python no trae; está escrito para el
programa, así que no hace falta tener instalado nada más.

**Cómics en RAR y en 7z de verdad.** Los `.cbr` que por dentro eran ZIP ya se
abrían. Ahora, cuando es un RAR de verdad, se usa el descompresor que Windows 10 y
11 **ya traen**, que sabe leer RAR, RAR5 y 7z. No hay que instalar nada.

**Cinco cosas que se pueden encender desde el recorrido guiado.** Las encuestas
insisten en algo incómodo: la función de accesibilidad que hay que activar no la
encuentra quien la necesita. El recorrido guiado tiene ahora un paso con las cinco
que más cambian la lectura, **con sus casillas ahí mismo**.

**Buscar entre tus notas.** La lista de marcadores y notas tiene un campo de
búsqueda, y al sacar los resaltados a un archivo se pueden incluir las notas y la
cita del documento: lo subrayado y lo pensado, juntos y en el orden del libro.

**Correcciones que se quedan.** Lo que el programa deduce a veces se equivoca.
Ahora se puede decir «esto no era un título, es un párrafo», «esto sí lo era»,
«este pie de página sobra» o poner a mano la descripción de una imagen, y la
corrección se guarda y se vuelve a aplicar cada vez que se abra ese documento.
Se atan al contenido del archivo, no a su ruta: un libro que se mueve de
carpeta o se renombra conserva sus correcciones.

**El menú Herramientas, por tareas.** Había llegado a veintidós órdenes
seguidas, y una lista de veintidós renglones no se recorre hasta el final: se
acaba usando solo lo de arriba. Ahora está repartido en cinco submenús —marcar
y citar, ver el elemento, inteligencia artificial, corregir el documento y
consultar—, con las tres casillas de cada día y las cuatro órdenes del programa
todavía a la vista, sin bajar un nivel. **Ninguna tecla cambia.**

**Las letras subrayadas de los menús ya no se repiten.** Cuando dos órdenes del
mismo menú llevaban la misma letra, esa tecla dejaba de activar nada: había que
pulsarla varias veces y rematar con Intro. Estaban repetidas en seis menús, y en
la lista de documentos recientes a partir del décimo. Se han repartido de nuevo
en los cinco idiomas, y una prueba nueva impide que vuelva a colarse ninguna.

**Los DjVu se abren.** Es el formato en el que se digitalizó media biblioteca
técnica y universitaria —manuales agotados, tesis, colecciones de revistas— y
hasta ahora era un archivo que no se podía abrir. No hacen falta las imágenes:
un DjVu de biblioteca lleva dentro el texto que se reconoció al escanearlo, y
para quien no ve **ese texto es el libro entero**. Salen sus páginas, su índice
y sus párrafos de verdad, no el churro de renglones del reconocimiento: las
palabras partidas al final de la línea se recomponen, y las direcciones de
internet no pierden su guion por el camino. Se ha comprobado letra por letra
contra el texto que el propio archivo declara.

**Los apuntes de clase, tal como llegan.** Se abren las **presentaciones** de
PowerPoint e Impress y las **hojas de cálculo** de Excel y Calc. En una
presentación, cada diapositiva es un encabezado —así se salta con `H`— y los
cuadros se leen **en el orden en que se ven en la pantalla**, no en el que
estaban guardados: sin eso, el título puede salir en medio y el pie antes que el
cuerpo. Las notas del ponente se leen también, que en unos apuntes suelen tener
más contenido que la diapositiva. En una hoja de cálculo, cada pestaña es un
apartado y su contenido, una tabla de verdad, recortando el rectángulo vacío que
tantas hojas declaran: una tabla que dice tener catorce filas y no mil.

**Las partituras.** Un archivo MusicXML —el formato en el que se intercambian
casi todas— se abre y cada compás se cuenta en palabras («do negra, re corchea»)
y se escribe en **musicografía braille**, siguiendo el documento B 4-2 de la
Comisión Braille Española. Es lo que piden los estudiantes de conservatorio y lo
único del programa que no tenía respuesta.

**Química en braille.** Las fórmulas ya se leían en voz alta; ahora también se
escriben, con la signografía de la Comisión Braille Española. No es la notación
matemática: `H₂O` son tres celdas y no cinco, porque el número de átomos va en
la quinta serie del braille sin signo de subíndice.

**La forma de un gráfico, además de sus números.** Debajo de la tabla de datos
se dice ahora cómo es la curva en una frase —«sube en conjunto, con altibajos;
el máximo está en el punto 7 de 12»— y se dibuja con puntos braille para
palparla en una línea braille de celdas gráficas. Y se pregunta a la
inteligencia artificial **de qué se fía**: cuando ha tenido que estimar valores
midiendo la altura de una barra, se dice y se recuerda comprobarlo en el
original. Un número estimado y uno leído no valen lo mismo en un trabajo.

**Etiquetas en las notas.** Debajo del texto de una nota hay un campo de
etiquetas: «examen», «capítulo 4», «dudas». La lista de resaltados deja entonces
quedarse con una sola, y al guardar en un archivo sale **solo lo de ese tema**.
Para preparar el capítulo cuatro no hacen falta los ciento veinte resaltados del
libro: hacen falta los once de ese tema, estén en el libro que estén.

**La bibliografía del final, hecha.** Desde la biblioteca se saca la lista de
referencias de los libros que se estén viendo, ordenada por apellido y en el
estilo que se elija. Se copia al portapapeles o se guarda en seis formatos, y
dos de ellos no se leen: se **importan**. Con BibTeX y con RIS las referencias
entran en Zotero, Mendeley o EndNote con sus campos separados, en vez de como un
párrafo que hay que volver a trocear. Arriba se dice a cuántas les falta algún
dato: una bibliografía con tres años en blanco hay que arreglarla antes de
entregarla, no después.

**Agrupar la biblioteca por asignatura.** A los libros se les puede poner una
colección —«Contabilidad», «Historia moderna»— y quedarse solo con los de una.
Se aplica a todos los que estén marcados a la vez, porque clasificar de uno en
uno son veinte diálogos y entonces no se clasifica nada. Viaja al otro equipo
con la sincronización.

**Buscar por lo que significa, no por cómo se escribe.** Los apuntes dicen
«amortización» y el manual dice «depreciación»; buscando por letras eso no
aparece, y lo que no aparece se da por que no está. El botón «Palabras
relacionadas» enseña qué otras palabras salen en los mismos pasajes **en tus
propios libros**, y tú eliges cuáles añadir. Lo aprende de tu biblioteca, no de
un diccionario: en una de derecho, «prescripción» sale junto a «caducidad»; en
una de medicina, junto a «receta». No hace falta cuenta ni conexión, y no se
manda nada a ningún sitio. De paso, la búsqueda entiende ahora las formas de una
palabra: buscar «amortización» encuentra «amortizar» y «amortizaciones».

**Pegar una dirección y leerla.** `Control+Mayús+U` trae una página de internet,
le quita los menús y los anuncios y la abre. Evita el rodeo de abrir el
navegador, buscar «Guardar como», elegir el formato y acordarse de dónde ha ido
a parar. La página se guarda en el disco, así que se puede volver a ella sin
conexión y se le pueden poner marcadores. De paso se ha arreglado un fallo que
venía de antes: **una página web moderna se leía casi vacía**, porque se
analizaba con el lector de XML en vez de con el de HTML. Un artículo de la
Wikipedia pasaba de doscientas cuarenta mil letras a cuatrocientas.

**El braille se puede escribir contraído.** En Opciones → Exportar hay una
casilla nueva, apagada de fábrica, que escribe el BRF y el PEF en **braille
contraído español (grado 2)**: «bien» pasa a ser una sola celda e «importante»,
tres en vez de diez. En una novela de ochocientas mil letras el archivo baja de
874 a 619 kilobytes, que en papel es casi un tercio menos de tomos. Se sigue el
documento técnico B 16-1 de la Comisión Braille Española, revisión de 2025, con
sus cinco pasos en el orden que manda —la lista de palabras, los principios, los
finales, las secuencias y las contracciones—, y se ha comprobado contra los
ciento veintitrés ejemplos resueltos que trae el propio documento: acierta en
**todas** las palabras de su lista y en **nueve de cada diez** de las que hay que
abreviar sobre la marcha. Viene apagada por dos razones y las dos importan: quien
no ha estudiado el contraído no lo entiende, y para algo que vaya a imprimirse y
repartirse conviene que lo repase alguien que lo lea a diario. Las fórmulas
—matemáticas, químicas y la música— no se contraen nunca: sus signos son los de
su propio código.

**Las tablas salen en braille como tablas.** Hasta ahora una tabla se exportaba
como texto seguido, y con el dedo encima de un número no había forma de saber de
qué columna era. Ahora se componen en **columnas alineadas**, que es lo que
permite recorrer la hoja hacia abajo siguiendo una; y cuando no caben en el
renglón —seis columnas no entran en cuarenta celdas— se escriben con **el nombre
de la columna delante de cada dato**, que ocupa más papel pero no deja ningún
número sin decir de qué es. La raya de separación solo se pone cuando la primera
fila son de verdad los títulos: en una tabla de palabras sin encabezado, esa raya
diría algo que no es.

**Un cuaderno con lo marcado en todos los libros.** Quien prepara una asignatura
no estudia un libro: estudia un tema repartido por seis. En la biblioteca,
**Cuaderno de estudio** junta las notas y los resaltados de todos los libros que
se estén viendo, los agrupa **por etiqueta** y saca un solo archivo con todo lo
del tema, diciendo de qué libro y de qué punto sale cada cosa. Filtrar la
biblioteca por asignatura y sacar el cuaderno de esa asignatura son dos pasos
seguidos. **No hace falta abrir ningún libro**: cada marcador guarda su propio
trozo de texto, así que el cuaderno de trescientos libros se monta al instante y
sin que ninguno esté a mano.

**Y lo marcado vuelve cuando toca olvidarlo.** Desde el cuaderno, el botón
**Repasar** convierte cada resaltado y cada nota en una tarjeta, sin escribir
nada aparte. Cada tarjeta se enseña en dos tiempos: primero de dónde sale y tu
nota, y solo cuando pulsas Espacio se descubre el pasaje —recordar y reconocer no
son lo mismo, y una tarjeta que enseña la respuesta a la vez que la pregunta no
enseña nada—. Se responde con tres teclas: 1 no me acordaba, 2 me ha costado, 3
lo sabía. Lo que sale bien tarda cada vez más en volver; lo que se resiste vuelve
mañana. Se guarda después de **cada** tarjeta, así que cerrar la ventana no
pierde el repaso, y una tanda son treinta como mucho, que es media hora: una
lista de doscientas se abandona a la quinta.

**El programa trae su propio 7-Zip.** Va en `data/bin` y viaja con el
ejecutable, así que abrir un cómic ya no depende de lo que cada equipo tenga
instalado. Era el último sitio donde el programa tenía que decirle a alguien
«instala otra cosa»: un `.cbr`, o un cómic partido en `album.part1.rar`,
`album.part2.rar`… en un equipo pelado. El descompresor que trae Windows, ante
un RAR partido, saca las páginas del primer volumen y dice que ha terminado; el
7-Zip los junta. Son dos megas y medio, y con ellos se abren además los `.7z`,
los `.cab` y una veintena de formatos más. Los avisos han dejado de mandar
instalar nada, porque ya no hace falta.

**Buscar mientras se escucha, sin perder la lectura.** Hasta ahora, buscar algo
durante la lectura en voz alta costaba la lectura entera: había que parar,
buscar, volver a colocarse a mano y arrancar otra vez. Ahora, al abrir la
búsqueda la voz **se calla y se guarda el sitio**, y al cerrarla sigue leyendo:
desde el resultado si se ha encontrado algo —que es para lo que se buscaba— y
desde donde se dejó si no. Quien buscaba en silencio no nota nada: la voz no
arranca sola.

**Un modo «entrevista» para las novelas.** En una novela con mucho diálogo,
oírlo todo con la misma voz obliga a reconstruir sobre la marcha quién dice cada
cosa: quien lee con los ojos ve las rayas en el margen, y de oído no están. En
**Voz → Ajustes de voz** hay ahora una casilla que hace que lo que dice un
personaje suene un poco más agudo, y que el inciso del narrador —«dijo ella»—
vuelva al tono normal. Se puede regular cuánto cambia, de 1 a 10.

Lo que costaba de esto no era cambiar el tono: era **distinguir una raya de un
guion**. Un guion al principio de un renglón es también una viñeta de lista, y
poner voz de personaje a la lista de la compra es mucho peor que no cambiar de
voz. Así que el programa es prudente a propósito: la raya larga se toma siempre
por diálogo; el guion corriente, solo cuando el libro no usa rayas en ninguna
parte y el renglón se parece de verdad a una intervención. Ante la duda, se lee
como narración.

**Control+F1 explica cualquier control, en cualquier ventana.** Antes lo hacía
en diez ventanas —las de ajustes— y en las demás no decía nada. Ahora está en
**las cuarenta y nueve**, y hay explicación escrita para **todos** los controles:
qué es, qué consigue y qué conviene poner. Dos ventanas se quedan fuera a
propósito y por su motivo: la de capturar una tecla, porque su trabajo es recoger
cualquier combinación que se pulse —Control+F1 incluida—, y la propia ventana de
ayuda, que se abriría sobre sí misma. Y para que esto no se pudra, hay una
comprobación que recorre el programa entero y falla si alguien añade un botón sin
explicarlo.

**Word, Excel y PowerPoint de 1997: los `.doc`, `.xls` y `.ppt` se abren.** Son
los apuntes pasados a Word hace veinte años, los temarios de oposición, la hoja
de una asignatura, la presentación de un profesor que nunca actualizó nada. Word
y Excel de hoy ya avisan de que algún día dejarán de abrirlos. El programa los
lee **con código propio**, sin instalar nada: un `.doc` siguiendo su tabla de
trozos —que es lo que hace que las tildes salgan bien y los párrafos en su
orden—, un `.xls` con sus hojas y sus celdas en una tabla de verdad, y un `.ppt`
con una diapositiva por encabezado. Si el archivo está protegido con contraseña,
se dice: el programa no quita protecciones de nada. Y una hoja de Excel 4, de
antes de 1993, se reconoce y se explica en vez de soltar disparates.

**Los archivos de ayuda `.hlp`, los de antes del CHM.** Son los manuales de todo
un decenio de programas, y hoy no hay nada que los abra: Windows dejó de traer el
visor en Vista y a partir de Windows 10 el parche oficial ni se instala. Ahora se
leen, con su título y un encabezado por tema, deshaciendo por nuestra cuenta las
**dos** compresiones que llevan dentro: la de toda la vida y la de frases, que
guarda aparte lo que más se repite en el manual. Comprobado contra dos archivos
de verdad y distintos: uno sin comprimir y otro con las dos compresiones puestas.

**Un cómic partido en volúmenes se abre entero sin instalar nada.** Era el
arreglo más importante que quedaba, aunque parezca el más pequeño: el
descompresor que trae Windows, ante un `album.part1.rar`, sacaba las páginas del
primer volumen y terminaba **sin decir que se había dejado el resto**. Un cómic
de doce páginas se abría con cinco, y quien lo leyera llegaba a la quinta
entendiendo que ahí se acababa. Ahora el programa **junta los volúmenes por su
cuenta**, incluida la página que queda partida entre dos —que es justo la que se
perdía—, y lo que vaya comprimido de verdad lo saca el 7-Zip que ahora viaja
dentro. Ya no hay ningún cómic que haya que avisar de que no se puede abrir.

**Dibujos táctiles más allá de una curva.** Un gráfico con dos o tres líneas se
dibuja ahora **con todas**, en el mismo dibujo y a la misma escala, que es lo
único que permite compararlas; se distinguen por el grosor del trazo, no por el
color. Y un diagrama de flujo trae además **su silueta**: cada caja un
cuadradito, cada flecha una raya, para palpar de un vistazo si esto es una fila
recta de ocho pasos o algo que se abre en dos ramas y se vuelve a juntar. Eso es
lo que la lista anidada no cuenta y quien ve el diagrama sabe antes de leer nada.

**Un diagrama de flujo ya se puede seguir, no solo oír de qué va.** «Un diagrama
con seis cajas y dos rombos de decisión» dice qué hay dibujado y no dice **por
dónde se va**, que es lo único que un diagrama de flujo cuenta. Ahora, al pulsar
**Sacar los datos** sobre una imagen, si no es un gráfico con valores el programa
prueba con la otra pregunta: las cajas y las flechas. Y lo que sale es una
**lista anidada de verdad** —«pedir el correo; si es válido, crear la cuenta; si
no, vuelve al paso 2»— que el lector de pantalla anuncia como lista, diciendo en
qué nivel está y dejando saltar de paso en paso con sus propias órdenes. Los
bucles se cortan diciendo a dónde vuelven, con el rótulo de su flecha, que es
exactamente lo que diría alguien leyéndolo en voz alta. Vale igual para
organigramas, mapas conceptuales y esquemas de circuitos, y como todo lo que sale
de la IA, dice de qué se fía: si ha tenido que suponer por dónde va una flecha,
lo advierte debajo. Se guarda con la imagen y viaja al EPUB exportado.

**Las partituras: los acordes y las dos voces ya se escriben.** Hasta ahora, un
compás con un acorde se decía en palabras y se avisaba de que no se transcribía;
era la mitad de la música para teclado y para guitarra. Ahora un acorde se
escribe como se escribe en braille: **una** nota —la más aguda o la más grave,
según la clave— y las demás con **signos de intervalo** medidos desde ella, así
que ocupa tres celdas y no seis y al leerlo se sabe de golpe qué distancia hay
entre las voces. Y dos voces en el mismo pentagrama se separan con la **cópula**,
poniendo el signo de octava después de ella y al empezar el compás siguiente, que
es lo que manda la norma y lo que evita leer la segunda voz en el registro de la
primera. En clave de fa los acordes se escriben de abajo arriba, como hace la
mano izquierda del teclado. Con el primer preludio de Chopin —tres voces y
acordes en los dos pentagramas— se transcribe entero.

**Y los adornos y los matices de la partitura.** Con los acordes ya escritos,
lo que seguía diciéndose en palabras eran los trinos, los mordentes, los
grupetos y las apoyaturas, más los reguladores, los matices y la digitación. Ya
se escriben todos. Los signos de los adornos no están en el documento B 4-2
—que avisa él mismo de que no es exhaustivo—, así que se han tomado del *New
International Manual of Braille Music Notation*, que es a donde el propio B 4-2
remite; queda guardado en `adjuntos/Estudio/normas` para poder comprobarlo. Y
una **apoyatura** ya no se tira: en MusicXML no es un adorno sino una nota de
verdad marcada como tal, y en braille la larga y la corta tienen signo distinto,
así que la diferencia se conserva. Lo único que sigue diciéndose en palabras es
lo que no tiene signo en esa tabla —el trémolo, los arpegios que cruzan dos
pentagramas—, y se advierte: **lo que no se puede escribir bien, no se inventa.**

**Y un modo de práctica, para hacerlo en vez de leerlo.** En **Ayuda →
Practicar** el programa propone ejercicios cortos —«ve al tercer encabezado, el
que se llama tal», «pon un marcador», «busca esta palabra»— **sobre el documento
que tengas abierto**, y avisa en cuanto salen. Leer que `H` salta al encabezado
siguiente y hacerlo con un libro delante no son lo mismo. Tres cosas que importan:
solo se proponen los ejercicios que ese documento admite, porque pedir el tercer
encabezado en una novela que no tiene ninguno enseña que el programa no funciona;
**da igual cómo lo hagas**, porque lo que se mira es el documento y no las teclas,
así que llegar con el árbol de contenido cuenta igual que llegar con `H`; y si un
ejercicio ya estaba cumplido cuando empieza, se dice y se pasa al siguiente en
vez de felicitarte por no haber hecho nada.

**El manual, a un tercio.** Pasa de dieciséis mil quinientas palabras a seis
mil. No se ha quitado nada que hiciera falta: se ha quitado lo que estaba dicho
dos veces. Un manual que explica ajuste por ajuste lo mismo que `Control+F1`
cuenta encima de cada control envejece a trozos —se cambia el control y el
manual sigue diciendo lo de antes— y, sobre todo, no se lee: cuarenta pantallas
de lector de pantalla para encontrar una tecla es no encontrarla. Ahora el
manual dice **qué hace cada cosa y con qué tecla**, y para el detalle remite a
donde está mejor: `Control+F1` sobre el control, `Mayús+F1` para la lista
completa de teclas —que se genera del propio programa y por eso no puede quedar
desfasada—. La lista de teclas sí sigue entera, en tablas: una tecla que no está
escrita en ninguna parte es una tecla que nadie encuentra.

**Media biblioteca digitalizada que no se podía abrir, ya se abre.** Un DjVu
lleva dentro, normalmente, el texto que se reconoció al escanearlo, y de ahí se
leía. Los que **no** lo llevan —los que se digitalizaron sin pasar el
reconocedor, que son muchos— no había forma de leerlos: para reconocerlos aquí
hacía falta sacar la página como imagen, y las páginas de un DjVu van
comprimidas en un formato, JB2, que no descomprime nada que se pueda usar. Ahora
se descomprime aquí. Una página de texto escaneada es la misma letra repetida
miles de veces, y JB2 lo aprovecha: guarda un **diccionario de formas** —una
«a», una «e», una coma— y después dice, para cada mancha de la página, qué forma
es y dónde va; las parecidas se guardan como la diferencia contra otra. De ahí
que una página de periódico quepa en tres kilobytes. Descomprimirlo son
seiscientas líneas sobre el mismo motor que ya se había escrito para el texto
del DjVu. Comprobado con dos libros de verdad —un facsímil de la Royal Society
de 1759 y un manuscrito árabe de cincuenta páginas—: las páginas salen idénticas,
con sus capitulares y sus grabados, y al reconocerlas sale el texto que el propio
archivo declara. El reconocimiento usa los mismos ajustes que el de los PDF, en
Opciones → Reconocimiento; con el tope de páginas puesto en cien de fábrica para
que un libro de quinientas no deje el programa abriendo durante horas.

**Una lámina de un DjVu ya se puede ver y describir.** Con la capa de texto
descomprimida quedaba fuera un caso: la página que **no tiene ni una letra**
—una lámina fotográfica, un mapa en color, la reproducción de un cuadro—. Esas
páginas no existían en el documento: ni texto que leer ni imagen que ver. Ahora
se descomprimen también las dos capas de color, que van en ondículas, y esa
página aparece como imagen: se llega a ella con `G`, se abre con `Control+I` y se
manda a describir con `Control+Alt+I` como la de cualquier otro libro. En un
libro de texto es una página de cada cincuenta; en un atlas o en un catálogo de
museo son todas. Cuando la página **sí** tiene texto se sigue usando la capa en
blanco y negro, que no es un apaño: llega ya separada del papel amarillento, y
por eso el reconocedor acierta más con ella que con la fotografía en color.

**Las imágenes de un archivo de ayuda de Windows.** Los `.hlp` ya se leían;
ahora también salen sus mapas de bits, con su compresión de 1990 deshecha aquí.
Casi siempre son iconos y adornos, pero no siempre: una captura de pantalla con
el rótulo «pulse aquí» dentro es contenido, y se perdía entero. Van **donde van
dentro del texto**, no amontonadas al final, y sin descripción, de forma que
quedan marcadas como pendientes y se pueden mandar a la IA.

**Las traducciones, repasadas de verdad.** Francés, italiano y portugués estaban
traducidos a máquina, y una máquina traduce bien las frases y se equivoca en lo
que no sabe que es un término. Salieron cosas así: **«do» era «faire»** —el verbo
«hacer»—, «la» era «le», «si» era «Ouais»; **«bemol» era «plat»** y «doble
bemol», «apartamento doble»; **«DAISY» era «Margherita»**, la flor, así que
«Libros DAISY» quedaba en «Livres MARGUERITE»; «Gemini» eran «los Gemelos»,
«Claude» era «Claudio», «Markdown» era una rebaja de precio y «Tesseract» era
«Tesserato». El botón **«Anterior» decía «Ex»** en italiano y «Antiguo» en
francés y portugués. Y en la ayuda de una opción **faltaba una frase entera**:
la que decía con qué tecla se abre una tabla aparte. Se han corregido más de
ciento treinta términos en los cuatro idiomas. Y para que no vuelva a pasar, la
comprobación se ejecuta ahora con las pruebas: hay un glosario de los nombres de
las notas, las figuras, las alteraciones y los adornos en cada idioma, y una
herramienta que vigila además los nombres propios, las siglas de los formatos,
los marcadores de formato y las teclas.

**Se le pueden poner otras voces.** Hasta ahora el programa leía con la voz de
Windows y con ninguna más. Para muchas cosas basta; para escuchar un libro
entero, no siempre: hay quien entiende una voz concreta al doble de velocidad
que cualquier otra porque lleva treinta años oyéndola, y hay quien quiere una
novela bien leída y necesita una voz que suene a persona. Ninguna de las dos
puede venir dentro del programa —unas no se pueden distribuir y otras son
cientos de megas—, así que ahora se **añaden como paquete**: Voz → Lectura en
voz alta → Motores de voz → Agregar.

Un paquete es un archivo que se elige y se instala, y lo que trae dentro lo
cuenta él: quién lo hizo, con qué licencia, qué ocupa y qué sabe hacer. Antes de
instalar nada se enseña todo eso y se puede decir que no. Quitarlo es un botón,
y desinstalar deja el programa como estaba.

**Y hay motores a los que se les añaden voces copiando una carpeta.** Se dejan
en la carpeta `voces` del motor y aparecen solas la próxima vez que abras la
ventana de la voz. No hay nada que registrar, ni que declarar, ni que
reinstalar; quitar una carpeta la quita de la lista y volver a ponerla la
devuelve. Las que vienen sirven de plantilla: cada una está en una carpeta que
la nombra y dentro hay un LEEME que explica qué significa cada trozo del nombre
y qué es lo que no se puede cambiar. Y como esa carpeta va declarada,
actualizar el motor no se lleva por delante las que hayas añadido.

**Y los idiomas se bajan cuando se piden.** Un motor puede hablar muchas más
lenguas de las que caben en un paquete, y meterlas todas serían gigas. Así que
un paquete puede traer las de tu idioma y ofrecer el resto para bajarlo al
elegirlo, en segundos, y después funcionar sin conexión igual que las que
venían. Lo que se baja se comprueba —el tamaño y su firma— antes de usarlo.

Y actualizar un motor ya no se lleva por delante lo que hubieras bajado. Antes,
reinstalar un paquete borraba su carpeta entera: quien tuviera diez idiomas los
perdía por instalar una corrección. Ahora cada paquete declara qué carpetas son
de quien lo usa y esas se conservan, con lo que trae la versión nueva mandando
sobre lo viejo.

**Un motor que toque Windows lo dice antes, y se va del todo al quitarlo.** Lo
normal es que no toque nada: se instalan copiando una carpeta y se quitan
borrándola, y por eso el programa se lleva en un lápiz de memoria. Pero los hay
que no pueden —alguno necesita apuntar sus voces en el registro de Windows para
encontrarlas al arrancar— y para esos hay ahora un trato explícito.

El paquete **declara** qué va a tocar y por qué, y el aviso previo lo lee con la
rama entera escrita, al lado de lo que ya decía de su autor y su licencia. Solo
se admite la parte del registro de tu cuenta: nada de pedir permisos de
administrador ni de dejar puesto algo para las demás cuentas del equipo. Y se
rechaza lo que no tenga sentido para un motor de voz —las ramas de Windows, o
pedir «Software» a secas, que sería pedir permiso para borrar media
configuración al desinstalarse—.

Al quitarlo se borra todo lo que puso, **incluidas las claves padre que queden
vacías**: irse dejando una carpeta vacía en el registro de alguien es no haberse
ido. Y antes de tocar nada se apunta qué había ya, porque si tenías ese motor
instalado por tu cuenta, eso no lo pusimos nosotros y no se toca. Lo borra el
programa y no el motor, a propósito: el motor que se quita porque da problemas
es justo el que no se puede cargar para pedirle que se limpie solo.

Tres cosas que importan de cómo está hecho. La voz de Windows **no se puede
quitar**: es la que queda cuando cualquier otra falla, y el programa nunca se
queda mudo. Los motores se instalan **dentro de la carpeta del programa**, así
que llevártelo en un lápiz de memoria se lleva las voces con él. Y lo que se
puede ajustar de cada motor lo dice el propio motor, incluida la explicación de
`Control+F1` de cada ajuste, escrita por quien lo hizo.

**La ventana de la voz, en pestañas.** Era una columna con trece ajustes
seguidos: con la vista se recorre de un vistazo y de oído hay que atravesarla
entera cada vez. Ahora son cinco pestañas —Voz, Motores de voz, Al leer, Qué se
dice y Diálogos— entre las que se salta con Control+Tabulador. Y se prueba la
voz desde las dos pestañas donde hace falta: la de la voz y la de los motores,
porque un motor de trece ajustes se afina cambiando y escuchando, y mandar a la
otra pestaña a cada prueba son trece viajes de ida y vuelta.

**Los ajustes de cada motor se ven.** Estaban puestos y quedaban fuera de la
ventana. La ventana tomaba su tamaño al abrirse, con la voz de Windows, que no
tiene ninguno, y al elegir otro motor el panel no crecía: medido, había 175
píxeles y un motor con pocos ajustes ya pedía 190, y uno de trece, 658. Los
controles
existían, respondían al tabulador y no se veían. Ahora la ventana crece hasta lo
que quepa en la pantalla y el panel se desplaza para el resto.

**Y se avisa cuando la voz está tardando.** Hay voces que generan el sonido de
la frase entera antes de empezar, y la primera vez levantan además su motor:
casi cinco segundos. Cinco segundos de silencio después de pulsar «leer»
no se distinguen de un programa colgado. Ahora suena un pulso corto mientras se
prepara y, si se alarga, se dice. De paso se arregló algo peor que estaba
oculto: el programa daba una frase por terminada a las tres décimas, así que con
una voz lenta **se habría saltado el libro entero sin decir nada**. Ahora cada
motor declara cuánto tarda.

**Y los motores funcionan también en el programa compilado.** Este era de los
peores fallos posibles, porque en desarrollo no se veía: al compilar, la
biblioteca estándar de Python no va entera —se incluye lo que se ve importado— y
un motor que se carga en marcha no lo mira nadie. Uno necesitaba `http.server`
para su puente y otro `http.cookies`, y en el ejecutable los dos arrancaban
diciendo que faltaba un módulo. Ahora **cada paquete declara lo
que necesita**, leído de su propio código al armarlo, y al compilar se incluye lo
que pidan: un motor nuevo que use algo poco común lo trae escrito y nadie tiene
que acordarse.

**Una guía para hacer más.** En `data/idiomas/es/docs/CREAR_MOTOR_DE_VOZ.md` está
escrito paso a paso cómo hacer un paquete de voz: el contrato entero, los cinco
sitios donde se falla, cómo armarlo y un motor completo de ejemplo para copiar.

**Con varias imágenes en una línea, ya se puede mirar cualquiera.** Un cómic
escaneado puede dejar una página entera en una sola línea, con cuatro imágenes
seguidas. La tecla `G` iba a cada una, pero ver o describir cogían **siempre la
primera**, así que las otras tres no había forma de mirarlas. En el libro que lo
destapó son ochenta imágenes en cuarenta y seis líneas, y veintitrés de esas
líneas llevan más de una.

Ahora se hace caso al cursor, que es donde lo deja la propia navegación, y se
dice cuál es: «se describe la imagen 3 de 4 de esta línea». El criterio no había
ni que inventarlo, porque los enlaces ya lo usaban: solo las imágenes miraban la
línea en vez del punto exacto.

**Y el árbol de contenido tiene menú.** Con la tecla de aplicaciones o
`Mayúsculas+F10` sobre cualquier entrada sale lo que se puede hacer con ella, y
cambia según lo que sea: en una imagen, verla o describirla con inteligencia
artificial; en una tabla, abrirla para recorrerla; en un enlace, seguirlo; y en
cualquiera, ir, leer en voz alta desde ahí, copiar su texto o poner un marcador.

Sobre la **cabecera de una rama** actúa sobre todos a la vez: describir de una
sola vez las ochenta imágenes de un cómic, o sacar a un archivo la lista entera
de las tablas de un manual. Es lo que convierte el árbol en algo con lo que se
trabaja, y no en otra lista por la que pasar.

Cada acción salta primero al elemento y luego hace lo suyo, así que el cursor
acaba donde uno ha actuado y al volver con `F6` se sigue por ahí. Y por dentro
llama a las órdenes que ya existían: no hay dos maneras de ver una imagen que
puedan acabar comportándose distinto.

**Y el árbol y la lista de elementos enseñan también lo tuyo.** Los dos
enseñaban lo que trae el documento —su índice, sus imágenes, sus tablas— y no lo
que uno va dejando encima, que es justo lo que más se consulta al estudiar:
dónde puse aquella nota, qué párrafos llevo resaltados. Estaban cada uno en su
propia ventana y no en el mapa.

Ahora los **marcadores, las notas y los resaltados** son tres ramas más del
árbol, justo debajo del índice, y los tres primeros tipos de la lista de `F7`,
con el porcentaje delante para situarlos. Van los primeros porque al volver a un
libro ya trabajado es lo primero que se busca.

Con el menú del árbol se trabaja con ellos sin salir de ahí: escribir o cambiar
la nota, copiarla, copiar el texto señalado, o quitarlo —preguntando antes si la
nota tiene algo escrito—. Y sobre la rama entera: abrir su lista completa, que
es donde se buscan y se exportan, copiarla, guardarla en un archivo o quitarlos
todos.

Las ramas se rehacen solas cuando cambian. Poner un marcador y que el árbol
siguiera enseñando los de antes sería peor que no enseñarlos, y no hizo falta
avisar desde los seis sitios donde se ponen y se quitan: todos guardan la sesión
al terminar, así que se mira ahí y se compara con lo que había.

**El recorrido guiado, por partes.** A partir de la primera vez, Ayuda →
Recorrido guiado pregunta qué parte quieres repasar: lo primero, moverse por el
texto, la voz, estudiar, las imágenes o los ajustes. Nadie vuelve a atravesar
dieciséis pantallas para recordar una tecla, y un recorrido al que no se vuelve
se usa una vez y ya.

---

## 1.2.0

Los PDF accesibles se leen ya como un libro, se pueden tener varios documentos
abiertos a la vez y hay un árbol de contenido siempre a mano.

**PDF accesibles.** Los PDF etiquetados —los que cumplen la norma PDF/UA, y son
ya la mayoría de los informes de empresa y de los documentos oficiales— se
recorren igual que un EPUB: con H los encabezados, con T las tablas, con L las
listas, con Q las citas, con O las notas al pie, con F7 la lista de elementos y
con Control+H el visor web. Se aprovecha su índice de marcadores, sus enlaces
llevan a donde tienen que llevar, sus imágenes se leen con la descripción que
escribió el autor y sus tablas conservan la fila de encabezados. Además
desaparecen del texto el encabezado y el pie que se repetían en cada página.

**Cambio de voz por idioma.** Al llegar a una cita en inglés dentro de un
informe en español, la lectura en voz alta pone una voz inglesa si la tienes
instalada y vuelve a la tuya al salir, como hace NVDA. Distingue las variantes:
un trozo marcado como inglés británico se lee con voz británica si la hay. Se
desactiva en Control+Alt+V.

**Pestañas.** Con la opción activada puedes tener abiertos los documentos que
quieras, y cada uno guarda lo suyo: la posición de lectura, los marcadores y el
historial. Al volver a una pestaña la encuentras como la dejaste. Control+N
abre en una pestaña nueva, Control+W cierra la actual, Control+Tabulador pasa a
la siguiente y Control+F6 enseña la lista para saltar a cualquiera. Hay un menú
Pestañas y, al abrir con otro documento delante, el programa pregunta dónde lo
quieres.

**Árbol de contenido.** A la izquierda del texto, con el índice del documento y
sus elementos agrupados, en un árbol que se pliega y se despliega. Es lo mismo
que enseña F7 pero sin abrir y cerrar un diálogo cada vez, y al llegar a él ya
está colocado por donde vas leyendo. Se enciende con Control+Alt+B.

**Moverse entre zonas.** F6 va a la zona siguiente de la ventana y Mayús+F6 a
la anterior: árbol, pestañas y texto, solo las que estén a la vista.

**Barra de estado.** Además de la línea, el porcentaje y la página, dice ahora
cuántas palabras y cuántas páginas tiene el documento, y en qué pestaña estás.

**Word y LibreOffice.** Se aprovecha el etiquetado que ya traían y que antes se
perdía: el texto alternativo de las imágenes, la fila de encabezados de las
tablas, los enlaces, las listas de verdad —con sus niveles y sus números— y las
notas al pie del ODT.

**Informe de accesibilidad.** Control+D dice ahora qué trae el documento para
poder leerse: encabezados, índice, tablas, imágenes descritas y sin describir,
páginas e idioma. En un PDF añade si está etiquetado y cuánto de su texto cubre
esa estructura; en un EPUB, lo que el libro declara de sí mismo.

**Tu propia inteligencia artificial, sin saber de esto.** En Opciones, pestaña
«IA local», hay un asistente que monta una IA que funciona dentro de tu
ordenador: mira qué equipo tienes, descarga el motor, te deja elegir un modelo
de una lista donde cada uno explica para qué sirve y qué pide, lo descarga y lo
prueba. Todo con su barra de progreso y sin instalar nada en Windows: va a la
carpeta «data» del programa. Si ya usabas Ollama por tu cuenta, el tuyo no se
toca, porque este tiene su propio puerto y su propio almacén.

Funciona con tarjeta gráfica y sin ella. Los siete modelos que se ofrecen van
desde uno que cabe en dos gigas hasta los Gemma 4 de Google, recién salidos; el
recomendado está hecho para entender tablas, gráficos y páginas escaneadas, que
es lo que más se pide aquí. Hay un Gemma 4 pequeño que lee documentos en más de
ciento cuarenta idiomas sin necesidad de tarjeta gráfica, y uno grande para
quien la tenga. Desde esa misma pestaña se arranca y se para el
servidor, se instalan más modelos, se cambia de uno a otro y se busca si hay
versión nueva de Ollama.

**Se puede seguir preguntando.** Las preguntas a la inteligencia artificial ya
no son sueltas: recuerda la conversación. Preguntas por una fórmula, no
entiendes un paso y preguntas por ese paso, sin volver a explicar de qué
hablabas. El documento se manda solo en la primera pregunta, así que seguir
preguntando es rápido y barato.

**Traducir es más fácil.** Dentro del programa, en «data/idiomas», ahora van los
catálogos **editables** además de los compilados. Quien quiera corregir una
frase o terminar un idioma parte de lo que ya está traducido en vez de empezar
de cero, y un LEEME en esa carpeta explica qué es cada archivo.

**Puedes traer tu propio modelo.** En Opciones, «IA local», hay un botón nuevo:
«Importar uno del disco». Mete en el programa un modelo en formato GGUF que ya
tengas bajado, sin descargar nada. Se piden dos archivos, porque un modelo que ve
imágenes son dos: los pesos y el proyector de visión, ese que suele llamarse
«mmproj». El programa busca el segundo en la misma carpeta y lo pone solo, avisa
si los has puesto cambiados y avisa también si te dejas el de visión, porque
entonces el modelo solo servirá para texto. Todo con su barra de progreso.

**El manual, en tu idioma.** Cada idioma tiene ahora su propia carpeta de
documentación, en «data/idiomas», y F1 abre la del idioma que tengas puesto.
Traducir el manual es dejar el archivo en la carpeta de esa lengua: no hay nada
que compilar ni que configurar. Mientras un idioma no lo tenga se abre el
español, que es el original, así que nadie se queda sin ayuda.

**Opciones.** Pestaña nueva, «Personalización», con las pestañas, el árbol de
contenido y la barra de estado.

**El programa habla cinco idiomas.** A los que había —español e inglés— se
suman **italiano, francés y portugués**, con los mil setecientos textos del
programa traducidos. Se eligen en Opciones, Avanzado.

La primera vez que abras un documento que ya tuvieras leído, el programa lo
analizará otra vez: la caché anterior no conocía nada de esto.

---

## 1.1.0

Primera versión con actualizaciones automáticas.
