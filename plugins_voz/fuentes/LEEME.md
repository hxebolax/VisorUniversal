# Las fuentes de los motores de voz

Aquí está **todo** lo que hace falta para armar cada paquete de voz: el código,
los datos, las bibliotecas y los binarios. Armar un paquete no necesita nada
más que esta carpeta —ni la aplicación de la que salieron algunos módulos, ni
una instalación de NVDA, ni conexión—.

```bash
python plugins_voz/crear_paquetes.py --listar
```

dice cuáles están listos y cuáles no.

---

## Los dos pasos

**Reunir** va a buscar las piezas a donde estén y las deja aquí. Se hace una
vez, en un equipo que tenga los orígenes a mano, o cuando algo cambie en su
origen:

```bash
python plugins_voz/crear_paquetes.py --reunir            # todos
python plugins_voz/crear_paquetes.py --reunir espeak     # uno
```

**Armar** lee solo esta carpeta y saca los `.motorvoz`:

```bash
python plugins_voz/crear_paquetes.py
```

Si al armar falta una pieza, el aviso dice qué motor hay que reunir.

Dos motores necesitan además un paso previo, porque lo suyo no está en ningún
equipo: hay que bajarlo y montarlo. Sus herramientas lo hacen y **comprueban que
suena** antes de dar nada por bueno:

```bash
python herramientas/espeak_mbrola.py    # eSpeak oficial + MBROLA + 7 voces
python herramientas/piper.py            # Piper + catálogo + una voz española
```

---

## Qué hay dentro de cada motor

| Carpeta | Qué lleva |
|---|---|
| `motor.py` | El adaptador: lo que traduce entre lo que el visor pide y lo que ese motor sabe hacer. Es código propio del proyecto |
| `motor.json` | El manifiesto: qué motor es, de dónde sale, con qué licencia y qué deja ajustar |
| `codigo/` | Los módulos que se traen de fuera, **tal como vienen de su origen** |
| `datos/` | Las carpetas de datos y de voces |
| `archivos/` | Los binarios sueltos, ya con la ruta que tendrán dentro del paquete |
| `vendor/` | Dependencias que vienen con el propio motor |
| `biblioteca/` | Dependencias traídas con pip |

Un motor no tiene por qué usar todas: Piper no trae ningún módulo de Python
—es un programa aparte al que se le habla por una tubería— y Core no trae nada
en absoluto, porque las voces ya están en Windows.

Los módulos de `codigo/` **no se editan a mano nunca**. Sus importaciones se
reescriben al armar, que es cuando se sabe con qué prefijo va cada uno. Así se
pueden volver a traer cuando cambien en su origen sin perder nada por el camino.

---

## De dónde sale cada uno, y con qué licencia

Esto importa: **no todo lo que hay aquí se puede repartir igual**.

| Motor | De dónde sale | Se puede repartir |
|---|---|---|
| `espeak` | La biblioteca y los datos de una instalación de NVDA | Sí: eSpeak NG es GPL v3 |
| `espeak_mbrola` | eSpeak NG oficial, MBROLA de 64 bits y las voces de numediart, con `herramientas/espeak_mbrola.py` | Sí, **mientras no se cobre**: es la condición de las voces MBROLA. Su aviso viaja dentro del paquete |
| `piper` | El programa de Piper para Windows y las voces de `rhasspy/piper-voices`, con `herramientas/piper.py` | Sí: Piper es MIT y cada voz viaja con su ficha de licencia |
| `rhvoice` | Se baja de los repositorios de RHVoice al reunir | Sí: GPL v3, y la licencia va dentro |
| `onecore` | No trae nada: las voces ya están en Windows | Sí, no hay nada que repartir |
| `eloquence` | Bibliotecas de IBM de los noventa y el puente de 32 bits | **No.** Es software propietario. El paquete se arma para uso propio |
| `acapela` | Adaptador BabTTS y puente x86 propios; el runtime y las voces los aporta quien tenga una licencia de Acapela | El adaptador sí. Las DLL y voces de Acapela **no** se incluyen ni se redistribuyen |
| `google_local` | El motor local de Google, de la otra aplicación | **No.** Es de Google |
| `edge_online` | `edge-tts` con pip, y el catálogo de la otra aplicación | El código sí (MIT); las voces son de Microsoft y suenan desde sus servidores |

De los que no se pueden repartir, en el repositorio público estaría solo el
**adaptador** —las doscientas líneas propias— y la receta que dice cómo armar el
paquete a quien tenga derecho a usar los binarios.

---

## Añadir un motor nuevo

En `data/idiomas/es/docs/CREAR_MOTOR_DE_VOZ.md` está escrito paso a paso: el
contrato entero, los cinco sitios donde se falla, cómo armarlo y un motor
completo de ejemplo.

En corto: una carpeta aquí con `motor.py` y `motor.json`, y una receta en
`crear_paquetes.py` que diga qué se trae y con qué prefijo.
