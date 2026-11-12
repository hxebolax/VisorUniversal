# Cómo hacer un paquete de motor de voz

Guía completa para programadores. Al terminarla tendrás un archivo
`.motorvoz` que cualquiera puede instalar desde el propio programa y que añade
una voz nueva con sus ajustes, su ayuda y su prueba.

No hace falta tocar ni una línea del Visor Universal. Ese es el punto: si
añadir un motor obligara a modificar el programa, no sería un sistema de
paquetes.

## Índice

1. [Qué es un motor de voz aquí](#1-que-es-un-motor-de-voz-aqui)
2. [El contrato: las quince cosas que hay que saber hacer](#2-el-contrato-las-quince-cosas-que-hay-que-saber-hacer)
3. [Lo que hay dentro de un paquete](#3-lo-que-hay-dentro-de-un-paquete)
4. [El manifiesto, campo por campo](#4-el-manifiesto-campo-por-campo)
5. [Los ajustes que declara tu motor](#5-los-ajustes-que-declara-tu-motor)
6. [Escribir el adaptador](#6-escribir-el-adaptador)
7. [Los cinco sitios donde se falla](#7-los-cinco-sitios-donde-se-falla)
8. [Armar el paquete](#8-armar-el-paquete)
9. [Probarlo de verdad](#9-probarlo-de-verdad)
10. [Un motor completo, de principio a fin](#10-un-motor-completo-de-principio-a-fin)
11. [Preguntas que salen siempre](#11-preguntas-que-salen-siempre)

---

## 1. Qué es un motor de voz aquí

Un **objeto de Python** que sabe hablar. Nada más.

El programa no sabe si por debajo hay una DLL de 1993, un proceso de 32 bits,
un servidor en internet o un modelo neuronal de cuarenta megas. Le pide quince
cosas concretas y le da igual cómo las resuelvas.

Ese objeto lo devuelve una función llamada `crear`, y esa función es **la única
entrada** de tu paquete:

```python
def crear(carpeta, ajustes):
    """carpeta: dónde está instalado tu motor. ajustes: lo que eligió el usuario."""
    return MiMotor(carpeta, ajustes)
```

### Por qué el contrato es el que es

No se inventó para esto. Es, letra por letra, **lo que el lector en voz alta ya
le pedía a la voz de Windows** desde el principio. Por eso admitir motores
nuevos no obligó a cambiar ni una línea de la lectura, y por eso puedes fiarte
de que está probado: lleva años funcionando.

---

## 2. El contrato: las quince cosas que hay que saber hacer

Doce métodos y tres propiedades. Se comprueban **de verdad** al cargar el motor,
no leyendo tu manifiesto: si falta alguno, el programa vuelve a la voz de
Windows y lo dice.

### Las voces

```python
def voces(self) -> list[str]:
    """Los nombres de tus voces, tal como se enseñan en la lista."""

def elegir_voz(self, nombre: str) -> bool:
    """Pone una por su nombre. Devuelve si ha podido."""

def voz_actual(self) -> str:
    """Cuál está puesta ahora."""

def voces_con_idioma(self) -> list[tuple[str, str]]:
    """[(nombre, código de idioma)]. El código va como «es-ES» o «es»."""

def voz_para_idioma(self, codigo: str) -> str:
    """La voz que mejor lee ese idioma, o cadena vacía si ninguna."""
```

Se busca **por nombre y no por número** a propósito: el orden de las voces
cambia al instalar o quitar alguna, y guardar un número haría que un día el
programa hablara con otra voz sin motivo aparente.

`voz_para_idioma` es la que permite que un libro con una cita en inglés se lea
con voz inglesa. Devuelve cadena vacía si tu motor no puede: no pasa nada, se
sigue con la voz de siempre. **Es preferible eso a devolver una voz que no
habla ese idioma.**

### Los ajustes

```python
def establecer_velocidad(self, valor: int) -> None:
    """Velocidad, de -10 a 10, con 0 en la normal."""

def establecer_volumen(self, valor: int) -> None:
    """Volumen, de 0 a 100."""
```

La escala de la velocidad es la de la voz de Windows —de -10 a 10, con el 0 en
la velocidad normal— y casi ningún motor usa esa. Tienes que
convertirla, y **conviene pensarlo dos veces**: el 0 tiene que caer donde tu
motor suena a velocidad normal, no en la mitad de tu escala. Los hay cuya
velocidad normal es 55 de 100, y ahí la conversión no es una regla de tres:

```python
def _a_mi_escala(velocidad):
    acotada = max(-10, min(10, int(velocidad)))
    if acotada >= 0:
        return int(55 + acotada * (100 - 55) / 10.0)
    return int(55 + acotada * 55 / 10.0)
```

### Hablar

```python
def decir(self, texto: str, con_marcas: bool = False) -> bool:
    """Empieza a decir un texto, descartando lo que hubiera antes."""

@staticmethod
def con_tono(texto: str, tono: int) -> str:
    """Envuelve un texto para que suene más agudo, o lo devuelve tal cual."""

def pausar(self) -> None: ...
def continuar(self) -> None: ...
def detener(self) -> None: ...
```

`decir` **no bloquea**: le pasas el texto, vuelve, y la voz sigue hablando. Si
tu motor sintetiza de forma síncrona, hazlo en un hilo o genera el audio y
reprodúcelo; lo que no puede es tardar segundos en volver, porque la interfaz se
congelaría.

`con_marcas` es para el cambio de tono en los diálogos, y llega con marcado XML
de la voz de Windows. **Si tu motor no lo entiende, ignóralo**: se pierde el
cambio de tono y
ni una palabra del libro. Lo que no puedes es dejarlo pasar tal cual, porque el
motor leería las etiquetas en voz alta.

`con_tono` es la otra mitad. Si tu motor no sabe cambiar de tono por frase,
devuelve el texto limpio:

```python
@staticmethod
def con_tono(texto, tono):
    return texto
```

### El estado

```python
@property
def disponible(self) -> bool:
    """Si este motor puede hablar ahora mismo."""

@property
def pausada(self) -> bool: ...

@property
def hablando(self) -> bool:
    """Si está diciendo algo ahora mismo."""
```

**`hablando` es la más importante del contrato.** Es lo que el lector mira para
saber cuándo pasarle la frase siguiente, y equivocarse aquí se nota
inmediatamente:

* Si dice `False` mientras suena, el lector le pasa la frase siguiente encima y
  se atropellan.
* Si dice `True` cuando ya acabó, la lectura se para y no sigue.
* **Una pausa tiene que contar como «sigue»**. Si al pausar dijera `False`, el
  lector daría la frase por terminada y se saltaría el resto.

```python
@property
def hablando(self):
    if self._pausado:
        return True          # pausado es «sigue», no «terminó»
    return self._suena_de_verdad()
```

### Tres métodos que no son obligatorios y conviene tener

```python
def cerrar(self) -> None:
    """Suelta lo que haya que soltar: procesos, conexiones, canales."""

@property
def espera_maxima(self) -> float:
    """Cuánto puedes tardar en empezar a sonar, en segundos."""

def problema(self) -> str:
    """Por qué no vas a poder hablar, en una frase. Vacío si todo va bien."""
```

`cerrar` se llama al cambiar de motor. Si el tuyo abre un proceso aparte y no lo
cierras, al cambiar tres veces habrá tres procesos vivos.

`espera_maxima` **es imprescindible si tu motor no habla al instante.** El
lector espera ese tiempo antes de dar una frase por perdida; si no lo declaras,
supone tres décimas —lo que tarda la voz de Windows— y **se saltará el libro
entero en silencio**. Una voz neuronal que tarda cinco segundos y no lo dice es
una voz que no lee nada.

| Motor | `espera_maxima` razonable |
|---|---|
| Una DLL local rápida | no hace falta declararla |
| Sintetiza la frase entera antes de sonar | 4 |
| Habla por una tubería a un proceso aparte | 3 |
| Lee del disco trozos grabados y los pega | 6 |
| Un programa aparte que se queda esperando | 8 |
| Voz neuronal local (levanta un motor) | 10 |
| Voz por internet | 12 |

Mientras se espera, el programa avisa solo: un pulso corto cada segundo y pico
y, si se alarga, un «Preparando la voz…». No tienes que hacer nada.

`problema` es para el caso incómodo: tu motor **arranca bien, lista sus voces y
aun así no puede sonar**. Le falta la clave con la que se abren sus modelos, no
encuentra los datos de la voz, la tarjeta de sonido está ocupada. Si `decir`
devuelve `False` y no hay nada que contar, quien pulse «Probar» no ve nada
suceder: ni sonido, ni error, ni pista. Y eso, desde fuera, no se distingue de
un programa colgado.

```python
def problema(self) -> str:
    if self._sintetizador is None:
        return "la biblioteca de voz no ha cargado"
    if not self._clave:
        return "falta la clave de las voces: ponla junto a cada una"
    return ""
```

Escríbelo **para que se lea en voz alta**, porque ahí va a acabar: una frase
corta, en minúscula, diciendo qué falta y dónde se pone. No pegues el mensaje
de error de la biblioteca tal cual si viene en inglés y con un código.

---

## 3. Lo que hay dentro de un paquete

Un paquete es **un archivo** con extensión `.motorvoz`. Por dentro es un ZIP
corriente, y eso es a propósito: cualquiera puede abrirlo y mirar qué lleva
antes de meter en su programa código que va a ejecutarse.

```
mi_motor.motorvoz
├── motor.json              quién eres y qué ajustes tienes
├── motor_mi_motor.pyc      tu adaptador, compilado
├── mimo_rutas.pyc          dónde están tus cosas
├── mimo_loquesea.pyc       lo demás que necesites
├── mimo_deps/              bibliotecas de terceros, si las traes
└── voces_mimo/             tus datos: DLL, voces, modelos
```

### Tres reglas de los nombres

1. **Todo lleva el prefijo de tu motor.** Dos paquetes instalados a la vez con
   un módulo llamado igual se tapan: el segundo en cargarse gana, y las voces de
   uno saldrían con el nombre del otro. Es la clase de fallo que parece
   funcionar.
2. **El módulo de entrada lo dices tú** en el manifiesto, con el campo `modulo`.
   Que se llame `motor_lo_que_sea` y no `motor` a secas.
3. **Nada de rutas absolutas ni de `..`.** El instalador las rechaza antes de
   descomprimir nada.

### Lo que NO tienes que traer

Lo que el programa ya pone:

* **BASS**, para reproducir audio. Está para los libros DAISY y puedes usarlo.
* El registro de actividad: usa `logging.getLogger("visor.motor.lo_que_sea")`.
* Todo lo de la biblioteca estándar de Python.

Traer tu propia copia de eso haría el paquete diez veces más grande y se
quedaría desfasado a la primera actualización.

### Lo que SÍ tienes que traer

Todo lo demás: tus DLL, tus voces, tus modelos y las bibliotecas de Python que
uses y no vengan con el programa.

---

## 4. El manifiesto, campo por campo

`motor.json`, en UTF-8:

```json
{
  "id": "mi_motor",
  "nombre": "Mi motor de voz",
  "version": "1.0",
  "contrato": 1,
  "modulo": "motor_mi_motor",
  "autor": "Quien lo hizo",
  "origen": "De dónde salen las voces y los binarios",
  "licencia": "Con qué licencia se pueden usar",
  "descripcion": "Qué es, qué hace bien y qué cuesta.",
  "ajustes": []
}
```

| Campo | Obligatorio | Qué es |
|---|---|---|
| `id` | **sí** | Letras, números y guion bajo. Es el nombre de su carpeta al instalarse, y no puede ser el que usa la voz de Windows |
| `nombre` | **sí** | Lo que se lee en la lista de motores |
| `contrato` | **sí** | Hoy `1`. Si no coincide, el paquete se rechaza |
| `modulo` | **sí** | Tu archivo de entrada, sin extensión |
| `version` | recomendado | La tuya, para saber qué hay instalado |
| `autor`, `origen`, `licencia` | **muy recomendados** | Se le enseñan a quien va a instalar, **antes** de instalar |
| `descripcion` | **muy recomendado** | Para qué sirve y qué cuesta |
| `python` | lo pone el constructor | Con qué versión se compiló |
| `necesita` | lo pone el constructor | Qué módulos de Python usa tu código |
| `conservar` | si bajas cosas | Carpetas tuyas que en realidad son de quien te usa |
| `sistema` | si tocas el registro | Qué tocas fuera de tu carpeta, y por qué |
| `ajustes` | no | Lo que tu motor deja tocar |

### `necesita`, y por qué existe

Este no lo escribes tú: lo calcula el constructor leyendo tus importaciones. Pero
conviene que sepas qué es, porque detrás hay el error más caro que se puede
cometer con un motor de voz: **funciona mientras lo pruebas y falla en el
programa compilado**.

El visor se reparte compilado, y al compilarlo la biblioteca estándar de Python
no va entera: se incluye lo que el compilador ve importado en el código del
programa. Tu motor se carga en marcha, desde un archivo que está fuera, así que
el compilador **no lo mira**. Si usas algo que el visor no use por su cuenta, ahí
no está.

Pasó de verdad, con dos motores de los que se reparten: uno levanta un servidor
local y necesita `http.server`; otro maneja galletas y necesita `http.cookies`.
Los dos arrancaban de maravilla en desarrollo y los dos decían «no module named
http.server» en el ejecutable.

Por eso el paquete lo declara. El constructor lee el árbol de sintaxis de tus
archivos, apunta lo que importas y lo guarda en el manifiesto; al compilar el
visor, se leen los manifiestos de `plugins_voz` y se incluye lo que pidan.

Hay una regla que sí te toca a ti:

> **La biblioteca estándar la pone el programa. Todo lo demás lo traes tú.**

De lo que declares, solo se incluye lo que Python trae de serie. Un paquete de
terceros —`requests`, `aiohttp`, lo que sea— no se toma del entorno de quien
compila: **tiene que viajar dentro de tu paquete**. Los motores que hablan por
internet lo hacen así: llevan su propio `aiohttp`, su `certifi` y una docena más
en una carpeta suya que ellos mismos ponen en la ruta de búsqueda.

Y no es un capricho de orden. Si se cogieran del entorno de quien compila,
bastaría con que tu motor mencionara un paquete raro para que el visor entero no
se pudiera compilar: el compilador sigue las importaciones de lo que se le pide y
se para en la primera que no resuelva.

La única excepción son las cosas que el visor ya usa por su cuenta —`comtypes`
para hablar con Windows, o `basskit` para el sonido—: esas están porque el
programa las necesita, y tu motor puede contar con ellas.

### `sistema`, si tu motor toca algo fuera de su carpeta

Lo normal es no tocar nada: tu motor vive dentro de su carpeta, se instala
copiándola y se quita borrándola. Si puedes hacerlo así, hazlo así y sáltate
este apartado.

Algunos motores no pueden. Los hay que buscan la lista de sus voces en el
registro de Windows y no arrancan sin ella. Si es tu caso, decláralo:

```json
"sistema": {
  "resumen": "Necesita apuntar sus voces en el registro para encontrarlas al arrancar.",
  "registro": [
    {
      "raiz": "HKCU",
      "clave": "Software\\Fabricante\\Producto",
      "porque": "Es donde el motor busca la lista de sus voces."
    }
  ]
}
```

Con eso, el programa hace tres cosas por su cuenta:

1. **Lo cuenta antes de instalar**, con la rama entera escrita y tu explicación
   al lado, junto a lo que ya enseña de tu autoría y tu licencia. Quien lo lea
   decide con eso.
2. **Apunta qué había ya** antes de tocar nada. Si esa rama existía —porque quien
   te instala ya tenía ese motor por su cuenta— no es tuya y no se toca.
3. **Lo deshace al quitarte**, subiendo también por las claves padre que se
   queden vacías.

Lo escribes tú y lo borra el programa, y no al revés. Es a propósito: un motor
que alguien quita porque da problemas es justo el que no se puede cargar para
pedirle que se limpie solo. Con lo declarado en tu manifiesto basta para
deshacerlo sin ejecutar una línea tuya.

**Solo `HKCU`.** La rama del equipo (`HKLM`) se rechaza: haría falta ser
administrador y lo que escribieras valdría para todas las cuentas. Un lector de
libros no tiene por qué pedir eso. Se rechazan también las ramas de Windows y
cualquiera con menos de dos niveles: con `Software` a secas estarías pidiendo
permiso para borrar media configuración del equipo al desinstalarte.

Y una cosa más, por si sirve de algo: si puedes evitar el registro, evítalo. De
los motores que trae el programa, ninguno lo toca, y esa es la razón de que se
pueda llevar en un lápiz de memoria y funcionar en cualquier equipo.

### `conservar`, si tu motor baja algo

Si tu motor deja bajar voces o idiomas, di aquí en qué carpetas los deja:

```json
"conservar": ["voces"]
```

Son rutas dentro de tu paquete, y lo que haya ahí sobrevive a que alguien
reinstale tu motor. Sin esto, actualizar tu paquete a una versión nueva borra
todo lo que quien lo use hubiera bajado, y eso pueden ser cientos de megas que
desaparecen por instalar una corrección de dos líneas.

Lo que trae tu paquete nuevo gana siempre: se conserva lo que hubiera y que tú
no traigas. Al revés sería peor —una voz corregida en tu versión nueva se vería
pisada por la vieja— y eso no hay manera de notarlo salvo oyéndolo.

Lo declaras tú y no lo adivina el programa, y por lo mismo de siempre: el
programa no sabe qué guardas dentro, y ponerse a suponer qué carpeta es de
descargas sería empezar a suponerlo mal.

### Por qué `origen` y `licencia` importan

Porque el programa los enseña en un aviso antes de instalar, y quien lo lea
decide con eso. Un paquete que no dice de dónde salen sus binarios es un paquete
que nadie debería instalar, y el tuyo no tiene por qué parecerlo.

---

## 5. Los ajustes que declara tu motor

Aquí está la idea que hace que esto funcione: **el programa no sabe qué ajustes
tiene tu motor, y no debe saberlo**. Se los preguntas tú en el manifiesto y él
los pinta.

```json
{
  "clave": "tono",
  "clase": "deslizador",
  "etiqueta": "&Tono de la voz, de 0 a 100:",
  "minimo": 0,
  "maximo": 100,
  "defecto": 50,
  "ayuda": "Cómo de grave o de aguda suena...\n\nEntre 40 y 60 se nota..."
}
```

### Las cuatro clases

| Clase | Control | Campos propios |
|---|---|---|
| `lista` | desplegable | `opciones`: `[{"valor": ..., "texto": "..."}]` |
| `deslizador` | deslizador con su número | `minimo`, `maximo` |
| `casilla` | casilla de verificación | — |
| `texto` | campo de texto | — |

El `&` de la etiqueta marca la letra de acceso. Si dos ajustes tuyos chocan, no
pasa nada grave; si puedes, evítalo.

### La ayuda es obligatoria y no es un trámite

**Un ajuste sin `ayuda` hace que el paquete se rechace al instalarlo.** No es
rigidez: en este programa cada control se explica con `Control+F1`, y quien lo
maneja no ve la pantalla. Un control sin explicación es un control que no se va
a tocar nunca.

Y la explicación la tienes que escribir tú, porque eres quien sabe qué hace. Una
buena ayuda dice tres cosas:

1. **Qué es**, en una frase.
2. **Qué consigue**, con lo que se nota.
3. **Qué conviene poner**, y por qué.

Compara:

> ❌ «Ajusta el tono de la voz.»

> ✅ «Cómo de grave o de aguda es la voz. Por debajo de 40 suena a hombre mayor;
> por encima de 80, a dibujo animado.
>
> No es un capricho estético: leyendo muchas horas, un tono que te resulte
> cómodo cansa mucho menos. Y si vas a usar el cambio de tono en los diálogos,
> deja aquí un valor medio para que le quede sitio hacia arriba.»

La segunda se puede oír una vez y decidir. La primera no dice nada que la
etiqueta no dijera ya.

### Cómo te llegan

En el diccionario `ajustes` de tu función `crear`, ya validados: si el usuario
tenía guardado un valor que ya no existe —porque actualizaste el motor y
quitaste una voz—, te llega el de fábrica y no el que sobra.

Hay una clave que no declaras y que te llega igual: **`_voz_elegida`**, con la
voz que el usuario tenía puesta en tu motor. Úsala al arrancar.

---

## 6. Escribir el adaptador

### Esqueleto mínimo

```python
# -*- coding: utf-8 -*-
"""Mi motor de voz para el Visor Universal."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger("visor.motor.mi_motor")

# Tu carpeta va en la ruta de importación para que tus módulos se encuentren
# entre ellos. El programa la pone mientras te construye y la quita después.
_AQUI = Path(__file__).resolve().parent
if str(_AQUI) not in sys.path:
    sys.path.insert(0, str(_AQUI))


class MiMotor:
    def __init__(self, carpeta: Path, ajustes: dict) -> None:
        self._carpeta = Path(carpeta)
        self._ajustes = dict(ajustes)
        self._pausado = False
        self._arrancar()

    def _arrancar(self) -> None:
        """Si algo falla, se apunta y se sigue vivo: NO se lanza excepción."""
        try:
            ...
        except Exception as error:
            log.warning("No se ha podido arrancar: %s", error)

    # ... el contrato entero ...


def crear(carpeta, ajustes):
    return MiMotor(Path(carpeta), dict(ajustes or {}))
```

### Reproducir el sonido con BASS

Si tu motor devuelve muestras en vez de reproducir, BASS ya está en el programa:

```python
def _reproducir(self, pcm: bytes, muestreo: int) -> bool:
    import ctypes

    from basskit.alto_nivel.reproductor import inicializar
    from basskit.constantes.bass import BASS_STREAM_PRESCAN
    from basskit.dlls.bass import bass

    if not self._bass:
        try:
            inicializar(-1, 44100)
        except Exception:
            pass          # puede estar ya listo por el reproductor DAISY
        self._bass = True
    onda = _envolver_en_wav(pcm, muestreo)
    # El buffer se guarda en un atributo: si se recoge como basura mientras
    # suena, el sonido se corta a mitad.
    self._memoria = ctypes.create_string_buffer(onda)
    self._canal = bass.BASS_StreamCreateFile(True, self._memoria, 0, len(onda),
                                             BASS_STREAM_PRESCAN)
    return bool(self._canal and bass.BASS_ChannelPlay(self._canal, True))
```

Y con eso tienes pausa de verdad:

```python
def pausar(self):
    if self._canal and not self._pausado:
        bass.BASS_ChannelPause(self._canal)
        self._pausado = True
```

### Cargar una DLL

```python
import ctypes

self._dll = ctypes.cdll.LoadLibrary(str(self._carpeta / "mi_motor.dll"))
self._dll.mi_funcion.restype = ctypes.c_char_p
self._dll.mi_funcion.argtypes = (ctypes.c_char_p,)
```

**Declara `restype` y `argtypes` siempre.** Sin ellos, ctypes supone `c_int` de
32 bits, y en 64 bits un puntero devuelto se trunca. El síntoma es un fallo
aparentemente aleatorio que aparece solo a veces.

**Si tu DLL es de 32 bits, no se puede cargar.** El programa es de 64, y eso no
se rodea con un truco: es cómo funciona Windows. La única salida es un proceso
aparte de 32 bits y una tubería. Hay paquetes hechos así y funciona bien: el
proceso pequeño carga la DLL y le pasa el sonido al programa por la tubería.

---

## 7. Los cinco sitios donde se falla

Escritos aquí porque cada uno cuesta una tarde.

### 1. `hablando` mal implementado

Ya está arriba, y merece repetirse porque es el que más veces se hace mal.
Pausado cuenta como «sigue». Y si tu motor tarda en empezar, el rato entre que
recibe el texto y suena **también** cuenta como «sigue», o el lector le pasará
la frase siguiente antes de oír la primera.

### 2. No declarar `espera_maxima`

Tu motor tarda cuatro segundos en la primera frase, el lector espera tres
décimas y se salta el libro entero. Sin error, sin aviso: silencio y un
documento leído a saltos.

### 3. Reventar en `crear`

Si lanzas excepción, el programa se queda con la voz de Windows y lo dice, así
que tampoco es un desastre. Pero es mejor arrancar de todos modos y contestar
`disponible = False`: así el usuario puede entrar en tus ajustes, cambiar el que
falla y volver a probar sin desinstalar nada.

### 4. Importar dentro de un método

Tu carpeta está en la ruta de importación **mientras el programa te construye**,
y se quita después. Un `import` perezoso en un método que se llama más tarde no
encontrará tus módulos. Importa lo tuyo en el módulo o en `__init__`.

### 5. Dejar pasar el marcado de la voz de Windows

`decir(texto, con_marcas=True)` te llega con `<pitch middle="4">…</pitch>`. Si
tu motor no lo entiende, **lo leerá en voz alta, etiqueta incluida**. O lo
procesas, o te aseguras de que `con_tono` devuelva el texto limpio para que no
llegue nunca así.

### 6. Llamar a una biblioteca nativa desde el hilo que te llama

Este es el peor de todos, porque **en desarrollo no se ve**: aparece solo con el
programa compilado, y no como un error sino como la ventana desapareciendo.

`decir` se llama desde el hilo que atiende la ventana. Si ahí dentro entras en
una DLL que sintetiza, generas el sonido y vuelves, la ventana se queda quieta
todo ese rato —y eso es lo de menos—. Lo grave es que un fallo dentro de esa DLL
no se puede capturar: no hay excepción de Python que valga, y el proceso se cae
entero. Windows lo apunta como violación de acceso, y si ocurre mientras la
biblioteca te está llamando de vuelta, como «excepción fatal en una llamada de
retorno».

Haz lo que hacen los que funcionan: una cola y un hilo tuyo que la atienda.

```python
def decir(self, texto, con_marcas=False):
    self.detener()
    self._preparando = True          # cuenta como «hablando» desde ya
    self._asegurar_el_hilo()
    self._cola.put((texto, self._turno))
    return True

def _atender(self):
    while True:
        tarea = self._cola.get()
        if tarea is None:
            return
        try:
            self._decir_de_verdad(*tarea)
        except Exception as error:      # de todo, y sin excepciones
            log.error("La voz no ha podido hablar: %s", error)
```

Tres detalles que se olvidan:

* El `except` es **de todo**. Una excepción que suba de ese hilo acaba
  atravesando código que no es de Python.
* Un **turno** que suba en `detener` y que el hilo compruebe, o al pasar página
  se oirá encima la frase anterior.
* Y baja la bandera de «preparando» **después** de poner el sonido a sonar, no
  antes: en las décimas de por medio no hay nada sonando todavía y `hablando`
  diría que no.

Y si tu biblioteca usa COM —muchas de Windows lo hacen sin decirlo— **mete tu
hilo en el apartamento multihilo antes de nada**:

```python
import ctypes
ctypes.windll.ole32.CoInitializeEx(None, 0)     # 0 = multihilo
```

Sin eso, Windows lleva las llamadas de tu biblioteca al hilo de la ventana, que
es de apartamento único. Y ahí van a chocar con las que el lector de pantalla
está haciendo para leer la interfaz: Windows las rechaza y el proceso se cae.
Es un fallo que **no aparece probando sin lector de pantalla**, así que no te
fíes de que a ti no te pase.

### 7. Que otro programa tenga tus mismas bibliotecas

Este es el peor de todos y no es culpa tuya. Windows resuelve una biblioteca
pedida por su nombre devolviendo **la primera que ya esté cargada con ese
nombre**, sin mirar de dónde salió. Si en el equipo hay otro programa con una
copia distinta de las tuyas —adaptadores de voz, complementos de lectores de
pantalla, y hay unos cuantos— y esa copia entra antes en el proceso, la tuya
usará la ajena. Cuando las versiones no casan, no da un error: tira el programa.

Se reconoce por dos señales: pasa **solo con el programa compilado**, y en el
archivo `caida_<fecha>.txt` la traza acaba dentro de tu biblioteca sin ninguna
razón aparente. Para confirmarlo, mira qué módulos tiene el proceso:

```powershell
(Get-Process VisorUniversal).Modules | Where-Object { $_.ModuleName -like '*loquesea*' }
```

Si ves **dos rutas distintas** para el mismo archivo, es esto.

La cura es llegar antes. Declara en tu manifiesto las bibliotecas que necesitas,
en orden, y el programa las cargará al arrancar, antes de tocar nada de voz:

```json
"precargar": [
  "libs/nucleo.dll",
  "libs/la_que_choca.dll"
]
```

Las rutas van dentro de tu carpeta —no se admite salir de ella— y se cargan una
sola vez. Ten en cuenta el precio: dos versiones de la misma biblioteca no caben
en un programa, así que el otro que la usara se quedará con la tuya. Dilo en la
descripción de tu paquete si eso le puede quitar algo a alguien.

Lo mismo vale para soltar. Si tu biblioteca te engancha una llamada de retorno
—te va entregando el sonido por trozos— **suéltalo todo en orden y a mano**:
primero quien llama, después lo llamado. Dejar que el recolector decida el orden
funciona casi siempre, y el día que no, se lleva el programa.

---

## 8. Armar el paquete

### Dónde va tu código

```
plugins_voz/
    crear_paquetes.py       el constructor
    fuentes/mi_motor/       tu motor: motor.py y motor.json
    mi_motor.motorvoz       lo que sale
```

### La receta

En `crear_paquetes.py`, al lado de las demás:

```python
RECETAS["mi_motor"] = Receta(
    identificador="mi_motor",
    prefijo="mimo",                      # con esto empiezan tus módulos
    modulo="motor_mi_motor",             # tu punto de entrada
    modulos={},                          # módulos que traer de otro sitio
    rutas=_rutas("mimo", 'DATOS = AQUI / "voces_mimo"'),
    datos={"voces_mimo": "ruta/en/el/origen"},
    archivos={"mi_motor.dll": "ruta/mi_motor.dll"},
    pip=("una-biblioteca",),             # se instala dentro del paquete
)
```

Y se arma:

```bash
entorno\Scripts\python.exe plugins_voz\crear_paquetes.py mi_motor
```

**Con el Python del programa y no con otro.** Los paquetes salen compilados a
bytecode, y el bytecode solo lo carga la versión con la que se compiló.

### Qué hace el constructor por ti

1. Copia tu adaptador con el nombre que dice el manifiesto.
2. Escribe tu módulo de rutas.
3. Trae los módulos que hayas pedido y **les reescribe las importaciones** con
   tu prefijo. No tienes que editarlos a mano.
4. Copia datos y binarios.
5. Instala con pip lo que hayas pedido, dentro del paquete.
6. Compila todo a `.pyc` y borra el fuente.
7. Comprime y **comprueba el resultado con el mismo código que lo instalará**.

Para probar mientras escribes, `--sin-compilar` deja el código legible.

---

## 9. Probarlo de verdad

### Comprobar el contrato antes que nada

```python
import sys
sys.path.insert(0, "src")
from nucleo import paquetes_voz, motores_voz

paquetes_voz.instalar("plugins_voz/mi_motor.motorvoz")
motor, aviso = motores_voz.crear("mi_motor", {})

print("falta:", motores_voz.comprobar_contrato(motor))   # tiene que ser []
print("disponible:", motor.disponible)
print("voces:", motor.voces()[:5])
```

Si `comprobar_contrato` devuelve algo, no sigas: el programa no usará tu motor.

### Comprobar que habla y cuándo empieza

```python
import time

motor.elegir_voz(motor.voces()[0])
motor.establecer_velocidad(0)
motor.establecer_volumen(90)

t0 = time.time()
print("decir ->", motor.decir("Una frase de prueba con números: 3, 145."))
for _ in range(100):
    time.sleep(0.1)
    if motor.hablando:
        print("suena a los %.2f s" % (time.time() - t0))
        break
else:
    print("NO HA SONADO: mira «hablando» y «espera_maxima»")
```

**Ese número es el que tiene que ir en `espera_maxima`**, redondeado hacia
arriba y con margen: mídelo en el peor caso, que es la primera frase después de
arrancar.

### Comprobar la pausa

```python
motor.decir("Una frase larga, de las que dan tiempo a pausar por la mitad.")
time.sleep(1)
motor.pausar()
assert motor.pausada and motor.hablando      # pausado es «sigue»
motor.continuar()
time.sleep(1)
motor.detener()
motor.cerrar()
```

### Y con el programa delante

Ábrelo, ve a **Voz → Lectura en voz alta → Motores de voz**, elige el tuyo y
pulsa **Probar la voz** en la pestaña «Voz». Después abre un libro y léelo un
par de minutos: los fallos de `hablando` no salen en una frase suelta, salen
encadenando cincuenta.

Pruébalo también con `Control+F1` sobre cada uno de tus ajustes. Si alguno no
contesta, tu manifiesto tiene una ayuda vacía.

---

## 10. Un motor completo, de principio a fin

Uno que no depende de nada, para copiar y empezar. Habla usando la voz de
Windows pero al revés, letra por letra: no sirve para nada y hace todo lo que el
contrato pide.

`plugins_voz/fuentes/alreves/motor.json`:

```json
{
  "id": "alreves",
  "nombre": "Voz que lee al revés",
  "version": "1.0",
  "contrato": 1,
  "modulo": "motor_alreves",
  "autor": "Un ejemplo",
  "origen": "Usa la voz de Windows; es solo un ejemplo para programadores.",
  "licencia": "Del proyecto.",
  "descripcion": "Lee cada frase al revés. No sirve para nada: está para copiarlo y hacer un motor de verdad encima.",
  "ajustes": [
    {
      "clave": "por_palabras",
      "clase": "casilla",
      "etiqueta": "Invertir las &palabras y no las letras",
      "defecto": false,
      "ayuda": "Con esto, «hola mundo» se lee «mundo hola» en vez de «odnum aloh».\n\nEstá aquí solo para enseñar cómo se declara una casilla y cómo llega su valor al motor."
    }
  ]
}
```

`plugins_voz/fuentes/alreves/motor.py`:

```python
# -*- coding: utf-8 -*-
"""Un motor de ejemplo: lee al revés con la voz que trae el sistema.

Habla por la interfaz de voz de Windows porque está en cualquier equipo y así
el ejemplo se puede ejecutar tal cual. Lo que se enseña aquí no es esa interfaz,
sino el contrato: en su lugar iría tu DLL, tu proceso aparte o tu servicio.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger("visor.motor.alreves")


class MotorAlReves:
    def __init__(self, carpeta: Path, ajustes: dict) -> None:
        self._ajustes = dict(ajustes)
        self._voz = None
        self._pausado = False
        try:
            import win32com.client

            self._voz = win32com.client.Dispatch("SAPI.SpVoice")
        except Exception as error:
            log.warning("No hay voz del sistema: %s", error)

    # -- voces ---------------------------------------------------------------

    @property
    def disponible(self):
        return self._voz is not None

    def voces(self):
        if self._voz is None:
            return []
        fichas = self._voz.GetVoices()
        return [fichas.Item(i).GetDescription() for i in range(fichas.Count)]

    def elegir_voz(self, nombre):
        if self._voz is None:
            return False
        fichas = self._voz.GetVoices()
        for i in range(fichas.Count):
            if fichas.Item(i).GetDescription() == nombre:
                self._voz.Voice = fichas.Item(i)
                return True
        return False

    def voz_actual(self):
        return self._voz.Voice.GetDescription() if self._voz else ""

    def voces_con_idioma(self):
        return [(nombre, "") for nombre in self.voces()]

    def voz_para_idioma(self, codigo):
        return ""            # este motor no sabe de idiomas, y lo dice

    # -- ajustes -------------------------------------------------------------

    def establecer_velocidad(self, valor):
        if self._voz:
            self._voz.Rate = max(-10, min(10, int(valor)))

    def establecer_volumen(self, valor):
        if self._voz:
            self._voz.Volume = max(0, min(100, int(valor)))

    # -- hablar --------------------------------------------------------------

    def decir(self, texto, con_marcas=False):
        if not texto or self._voz is None:
            return False
        if self._ajustes.get("por_palabras"):
            alreves = " ".join(reversed(texto.split()))
        else:
            alreves = texto[::-1]
        self.detener()
        self._voz.Speak(alreves, 1)          # 1 = no bloquear
        return True

    @staticmethod
    def con_tono(texto, tono):
        return texto                          # sin marcas: no las entendemos

    def pausar(self):
        if self._voz and not self._pausado:
            self._voz.Pause()
            self._pausado = True

    def continuar(self):
        if self._voz and self._pausado:
            self._voz.Resume()
            self._pausado = False

    def detener(self):
        if self._voz is None:
            return
        if self._pausado:
            self._voz.Resume()
            self._pausado = False
        self._voz.Speak("", 1 | 2)            # 2 = vaciar la cola

    @property
    def pausada(self):
        return self._pausado

    @property
    def hablando(self):
        if self._pausado:
            return True
        return self._voz is not None and int(self._voz.Status.RunningState) == 2


def crear(carpeta, ajustes):
    return MotorAlReves(Path(carpeta), dict(ajustes or {}))
```

La receta:

```python
RECETAS["alreves"] = Receta(
    identificador="alreves",
    prefijo="alrev",
    modulo="motor_alreves",
    modulos={},
    rutas=_rutas("alrev", "# este motor no necesita nada"),
)
```

Y ya:

```bash
entorno\Scripts\python.exe plugins_voz\crear_paquetes.py alreves
```

---

## 11. Preguntas que salen siempre

**¿Puedo reemplazar la voz de Windows?**
No. Su identificador está reservado y un paquete que lo use se rechaza, diciendo
cuál es. La voz de Windows es la que queda cuando cualquier otra falla, y el
programa nunca se queda mudo.

**¿Y si mi motor necesita una biblioteca de pip?**
Ponla en `pip` en la receta y se instala dentro del paquete. Ojo con las que
traen partes compiladas: quedarían atadas a la versión de Python con la que se
instalaron. Si pip encuentra una versión sin compilar, la usa.

**¿Puedo traer un ejecutable?**
Sí, en `archivos`. Es como se hacen los puentes de 32 bits, por ejemplo. Dilo
en `origen` y en `licencia`, que es lo que se le enseña a quien lo instale.

**¿Cómo actualizo un motor ya instalado?**
Instalando el paquete otra vez. Se descomprime a un lado y solo al final se pone
en su sitio, así que si falla a mitad el que había sigue funcionando. Los
ajustes del usuario se conservan.

**¿Dónde queda instalado?**
En `data/motores/<id>`, dentro de la carpeta del programa. No se toca el sistema
ni el registro de Windows: llevarse el programa en un lápiz de memoria se lleva
las voces con él.

**¿Y si el usuario tiene otra versión de Python?**
Tu paquete no cargará y el instalador lo dirá antes de copiar nada, porque el
manifiesto declara con qué versión se compiló. Vuelve a armarlo con la nueva.

**¿Puedo hacer que mi motor descargue voces nuevas?**
Sí, y es buena idea si tu motor lo permite. Hazlo desde tus propios ajustes —una
lista que se rellena con lo que haya— y guarda lo descargado dentro de tu
carpeta en `data/motores/<id>`, nunca fuera.

**¿Tengo que traducir mi paquete?**
No hay soporte de traducción en los manifiestos. Escríbelo en el idioma de quien
lo vaya a usar. Si haces uno para repartir, el español es lo que espera este
programa.

---

## Y lo último

Antes de repartir un paquete, léete la ayuda de tus propios ajustes con
`Control+F1`, uno a uno, **con los ojos cerrados**. Si alguna no te dice qué
poner, reescríbela: eso es exactamente lo que le va a pasar a quien lo instale.
