//! Puente x86 para la API BabTTS de Acapela.
//!
//! No registra COM/SAPI, no ejecuta instaladores y no modifica el Registro.
//! Toda la comunicación usa marcos binarios por stdin/stdout. El sonido lo
//! reproduce el propio runtime mediante su salida WaveOut.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::env;
use std::ffi::{c_char, c_void, CStr, CString, OsStr};
use std::fs;
use std::io::{self, Read, Write};
use std::mem;
use std::os::windows::ffi::OsStrExt;
use std::path::{Path, PathBuf};
use std::ptr;
use std::sync::atomic::{AtomicBool, Ordering};

const MAX_FRAME: usize = 16 * 1024 * 1024;

const OP_ENUMERAR: u8 = 1;
const OP_ELEGIR: u8 = 2;
const OP_PARAMETRO: u8 = 3;
const OP_DECIR: u8 = 4;
const OP_PAUSAR: u8 = 5;
const OP_CONTINUAR: u8 = 6;
const OP_DETENER: u8 = 7;
const OP_ESTADO: u8 = 8;
const OP_CERRAR: u8 = 9;

const BABTTS_USEDEFDICT: u32 = 0x0000_0004;
const BABTTS_CB_FUNCTION: u32 = 0x0000_0002;
const BABTTS_MSG_TEXTBEGIN: u32 = 0x2008;
const BABTTS_MSG_TEXTEND: u32 = 0x2009;

static HABLANDO: AtomicBool = AtomicBool::new(false);
static PAUSADO: AtomicBool = AtomicBool::new(false);

type HModule = *mut c_void;
type FarProc = *mut c_void;

#[link(name = "kernel32")]
extern "system" {
    fn LoadLibraryW(name: *const u16) -> HModule;
    fn GetProcAddress(module: HModule, name: *const c_char) -> FarProc;
    fn FreeLibrary(module: HModule) -> i32;
    fn SetDllDirectoryW(path: *const u16) -> i32;
    fn SetCurrentDirectoryW(path: *const u16) -> i32;
}

type Callback = unsafe extern "system" fn(*mut c_void, u32, *mut c_void, usize);
type FnInit = unsafe extern "system" fn() -> i32;
type FnUninit = unsafe extern "system" fn() -> i32;
type FnCreate = unsafe extern "system" fn() -> *mut c_void;
type FnClose = unsafe extern "system" fn(*mut c_void) -> i32;
type FnOpen = unsafe extern "system" fn(*mut c_void, *const c_char, u32) -> i32;
type FnSpeak = unsafe extern "system" fn(*mut c_void, *const c_void, u32) -> i32;
type FnSimple = unsafe extern "system" fn(*mut c_void) -> i32;
type FnSet = unsafe extern "system" fn(*mut c_void, u32, u32) -> i32;
type FnNumVoices = unsafe extern "system" fn() -> i32;
type FnEnumVoice = unsafe extern "system" fn(i32, *mut c_char) -> i32;
type FnSetCallback = unsafe extern "system" fn(*mut c_void, Callback, u32) -> i32;

unsafe extern "system" fn evento(
    _instancia: *mut c_void,
    mensaje: u32,
    _contexto: *mut c_void,
    _informacion: usize,
) {
    if mensaje == BABTTS_MSG_TEXTBEGIN {
        HABLANDO.store(true, Ordering::Release);
    } else if mensaje == BABTTS_MSG_TEXTEND {
        HABLANDO.store(false, Ordering::Release);
        PAUSADO.store(false, Ordering::Release);
    }
}

fn ancho(texto: &OsStr) -> Vec<u16> {
    texto.encode_wide().chain(std::iter::once(0)).collect()
}

fn codigo_error(codigo: i32) -> &'static str {
    match codigo {
        -27 => "datos de voz incompatibles con esta versión del motor",
        -26 => "diccionario de voz demasiado antiguo",
        -25 => "biblioteca no inicializada",
        -24 => "licencia no válida para la función o la voz solicitada",
        -23 => "diccionario de pronunciación ausente",
        -22 => "archivo de datos de voz ausente",
        -21 => "función no implementada",
        -15 => "no se puede abrir un archivo necesario",
        -13 => "etiqueta de texto no válida",
        -12 => "módulo lingüístico no disponible",
        -10 => "parámetro no válido",
        -9 => "el runtime exige una configuración de Registro inexistente",
        -8 => "configuración de Registro no válida",
        -7 => "fallo interno del proceso del motor",
        -6 => "dispositivo de sonido no disponible",
        -5 => "no se puede escribir en el dispositivo de sonido",
        -4 => "error de síntesis",
        -3 => "el motor ya está hablando",
        -2 => "error al liberar memoria",
        -1 => "memoria insuficiente",
        _ => "error no documentado",
    }
}

fn comprobar(codigo: i32, operacion: &str) -> Result<i32, String> {
    if codigo < 0 {
        Err(format!("{}: {} (código {})", operacion, codigo_error(codigo), codigo))
    } else {
        Ok(codigo)
    }
}

unsafe fn simbolo(module: HModule, nombre: &str) -> Result<FarProc, String> {
    let c = CString::new(nombre).map_err(|_| "nombre de símbolo no válido")?;
    let valor = GetProcAddress(module, c.as_ptr());
    if valor.is_null() {
        Err(format!("a la DLL le falta la función {}", nombre))
    } else {
        Ok(valor)
    }
}

struct Api {
    module: HModule,
    init: FnInit,
    uninit: FnUninit,
    create: FnCreate,
    close: FnClose,
    open: FnOpen,
    speak: FnSpeak,
    reset: FnSimple,
    pause: FnSimple,
    resume: FnSimple,
    set: FnSet,
    num_voices: FnNumVoices,
    enum_voice: FnEnumVoice,
    set_callback: FnSetCallback,
}

impl Api {
    unsafe fn cargar(ruta: &Path) -> Result<Self, String> {
        let carpeta = ruta.parent().ok_or("la DLL no tiene carpeta")?;
        if carpeta.join("CLKERN.DLL").exists()
            || carpeta.join("INFOVOX3.EXE.cracklock").exists()
        {
            return Err(
                "la carpeta contiene componentes de activación alterados; usa un runtime oficial"
                    .to_string(),
            );
        }
        let carpeta_w = ancho(carpeta.as_os_str());
        SetDllDirectoryW(carpeta_w.as_ptr());
        let ruta_w = ancho(ruta.as_os_str());
        let module = LoadLibraryW(ruta_w.as_ptr());
        if module.is_null() {
            return Err(format!("Windows no puede cargar {}", ruta.display()));
        }

        macro_rules! cargar {
            ($nombre:literal, $tipo:ty) => {{
                let p = simbolo(module, $nombre)?;
                mem::transmute::<FarProc, $tipo>(p)
            }};
        }

        Ok(Self {
            module,
            init: cargar!("BabTTS_Init", FnInit),
            uninit: cargar!("BabTTS_Uninit", FnUninit),
            create: cargar!("BabTTS_Create", FnCreate),
            close: cargar!("BabTTS_Close", FnClose),
            open: cargar!("BabTTS_Open", FnOpen),
            speak: cargar!("BabTTS_Speak", FnSpeak),
            reset: cargar!("BabTTS_Reset", FnSimple),
            pause: cargar!("BabTTS_Pause", FnSimple),
            resume: cargar!("BabTTS_Resume", FnSimple),
            set: cargar!("BabTTS_SetSettings", FnSet),
            num_voices: cargar!("BabTTS_GetNumVoices", FnNumVoices),
            enum_voice: cargar!("BabTTS_EnumVoices", FnEnumVoice),
            set_callback: cargar!("BabTTS_SetCallback", FnSetCallback),
        })
    }
}

impl Drop for Api {
    fn drop(&mut self) {
        unsafe {
            FreeLibrary(self.module);
        }
    }
}

struct Motor {
    api: Api,
    inicializado: bool,
    instancia: *mut c_void,
    voces: Vec<String>,
    texto: Vec<u16>,
}

impl Motor {
    unsafe fn cargar(dll: &Path, datos: Option<&Path>) -> Result<Self, String> {
        if let Some(donde) = datos {
            if !donde.is_dir() {
                return Err(format!("no existe la carpeta de datos {}", donde.display()));
            }
            env::set_var("ACATTS", donde);
            let donde_w = ancho(donde.as_os_str());
            // Solo cambia el directorio del proceso puente, nunca el del visor.
            SetCurrentDirectoryW(donde_w.as_ptr());
        }
        let api = Api::cargar(dll)?;
        if let Some(donde) = datos {
            let bin = donde.join("bin");
            if bin.is_dir() {
                // AcaTTS carga Colibri/TTSNlp en Init, después de cargar el
                // kernel. En ese momento su carpeta debe estar en la búsqueda.
                let bin_w = ancho(bin.as_os_str());
                SetDllDirectoryW(bin_w.as_ptr());
            }
        }
        comprobar((api.init)(), "inicializando Acapela")?;
        let mut motor = Self {
            api,
            inicializado: true,
            instancia: ptr::null_mut(),
            voces: Vec::new(),
            texto: Vec::new(),
        };
        motor.voces = motor.enumerar()?;
        Ok(motor)
    }

    unsafe fn enumerar(&self) -> Result<Vec<String>, String> {
        let total = comprobar((self.api.num_voices)(), "enumerando voces")?;
        let mut salida = Vec::new();
        for indice in 0..total {
            let mut buffer = vec![0i8; 512];
            comprobar(
                (self.api.enum_voice)(indice, buffer.as_mut_ptr()),
                "leyendo una voz",
            )?;
            let bytes = CStr::from_ptr(buffer.as_ptr()).to_bytes();
            // Los nombres de las voces estudiadas son ASCII. Para cualquier
            // byte ANSI se conserva una representación estable en vez de fallar.
            let nombre: String = bytes.iter().map(|&b| char::from(b)).collect();
            let nombre = nombre.trim().to_string();
            if !nombre.is_empty() {
                salida.push(nombre);
            }
        }
        Ok(salida)
    }

    fn ansi(texto: &str) -> Result<CString, String> {
        let bytes: Vec<u8> = texto
            .chars()
            .map(|c| if (c as u32) <= 255 { c as u8 } else { b'?' })
            .collect();
        CString::new(bytes).map_err(|_| "el nombre de voz contiene un cero".to_string())
    }

    unsafe fn elegir(&mut self, nombre: &str) -> Result<(), String> {
        if !self.voces.iter().any(|v| v == nombre) {
            return Err(format!("la voz «{}» no aparece en el runtime", nombre));
        }
        self.cerrar_voz();
        let instancia = (self.api.create)();
        if instancia.is_null() {
            return Err("Acapela no ha podido crear una instancia de voz".to_string());
        }
        let nombre_ansi = Self::ansi(nombre)?;
        if let Err(error) = comprobar(
            (self.api.open)(instancia, nombre_ansi.as_ptr(), BABTTS_USEDEFDICT),
            "abriendo la voz",
        ) {
            (self.api.close)(instancia);
            return Err(error);
        }
        if let Err(error) = comprobar(
            (self.api.set_callback)(instancia, evento, BABTTS_CB_FUNCTION),
            "conectando las notificaciones",
        ) {
            (self.api.close)(instancia);
            return Err(error);
        }
        self.instancia = instancia;
        Ok(())
    }

    unsafe fn parametro(&mut self, clave: u32, valor: u32) -> Result<(), String> {
        if self.instancia.is_null() {
            return Err("no hay ninguna voz abierta".to_string());
        }
        comprobar(
            (self.api.set)(self.instancia, clave, valor),
            &format!("aplicando el parámetro {}", clave),
        )?;
        Ok(())
    }

    unsafe fn decir(&mut self, texto: &str, modo: u32) -> Result<(), String> {
        if self.instancia.is_null() {
            return Err("no hay ninguna voz abierta".to_string());
        }
        self.detener()?;
        self.texto = texto.encode_utf16().chain(std::iter::once(0)).collect();
        HABLANDO.store(true, Ordering::Release);
        let resultado = comprobar(
            (self.api.speak)(self.instancia, self.texto.as_ptr().cast(), modo),
            "enviando el texto a Acapela",
        );
        if resultado.is_err() {
            HABLANDO.store(false, Ordering::Release);
            self.texto.clear();
        }
        resultado.map(|_| ())
    }

    unsafe fn pausar(&mut self) -> Result<(), String> {
        if !self.instancia.is_null() && !PAUSADO.load(Ordering::Acquire) {
            comprobar((self.api.pause)(self.instancia), "pausando Acapela")?;
            PAUSADO.store(true, Ordering::Release);
        }
        Ok(())
    }

    unsafe fn continuar(&mut self) -> Result<(), String> {
        if !self.instancia.is_null() && PAUSADO.load(Ordering::Acquire) {
            comprobar((self.api.resume)(self.instancia), "continuando Acapela")?;
            PAUSADO.store(false, Ordering::Release);
        }
        Ok(())
    }

    unsafe fn detener(&mut self) -> Result<(), String> {
        if self.instancia.is_null() {
            return Ok(());
        }
        if PAUSADO.swap(false, Ordering::AcqRel) {
            (self.api.resume)(self.instancia);
        }
        comprobar((self.api.reset)(self.instancia), "deteniendo Acapela")?;
        HABLANDO.store(false, Ordering::Release);
        self.texto.clear();
        Ok(())
    }

    unsafe fn cerrar_voz(&mut self) {
        if !self.instancia.is_null() {
            let _ = self.detener();
            (self.api.close)(self.instancia);
            self.instancia = ptr::null_mut();
        }
    }
}

impl Drop for Motor {
    fn drop(&mut self) {
        unsafe {
            self.cerrar_voz();
            if self.inicializado {
                (self.api.uninit)();
                self.inicializado = false;
            }
        }
    }
}

fn leer_marco<R: Read>(entrada: &mut R) -> io::Result<Option<(u8, Vec<u8>)>> {
    let mut op = [0u8; 1];
    match entrada.read_exact(&mut op) {
        Ok(()) => {}
        Err(error) if error.kind() == io::ErrorKind::UnexpectedEof => return Ok(None),
        Err(error) => return Err(error),
    }
    let mut longitud = [0u8; 4];
    entrada.read_exact(&mut longitud)?;
    let cuantos = u32::from_le_bytes(longitud) as usize;
    if cuantos > MAX_FRAME {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "marco desmesurado"));
    }
    let mut cuerpo = vec![0u8; cuantos];
    entrada.read_exact(&mut cuerpo)?;
    Ok(Some((op[0], cuerpo)))
}

fn responder<W: Write>(salida: &mut W, resultado: Result<String, String>) -> io::Result<()> {
    let (estado, texto) = match resultado {
        Ok(texto) => (0u8, texto),
        Err(texto) => (1u8, texto),
    };
    let bytes = texto.as_bytes();
    salida.write_all(&[estado])?;
    salida.write_all(&(bytes.len() as u32).to_le_bytes())?;
    salida.write_all(bytes)?;
    salida.flush()
}

fn u32_en(datos: &[u8], inicio: usize) -> Result<u32, String> {
    let fin = inicio + 4;
    let trozo = datos.get(inicio..fin).ok_or("orden incompleta")?;
    Ok(u32::from_le_bytes(trozo.try_into().unwrap()))
}

fn argumentos() -> Result<(PathBuf, Option<PathBuf>), String> {
    let mut dll = None;
    let mut datos = None;
    let mut args = env::args_os().skip(1);
    while let Some(arg) = args.next() {
        if arg == "--dll" {
            dll = args.next().map(PathBuf::from);
        } else if arg == "--data" {
            datos = args.next().map(PathBuf::from);
        } else {
            return Err(format!("argumento desconocido: {}", PathBuf::from(arg).display()));
        }
    }
    let dll = dll.ok_or("falta --dll con la biblioteca oficial de Acapela")?;
    if !dll.is_file() {
        return Err(format!("no existe la biblioteca {}", dll.display()));
    }
    Ok((dll, datos))
}

fn main() {
    let mut entrada = io::stdin().lock();
    let mut salida = io::stdout().lock();
    let preparado = argumentos().and_then(|(dll, datos)| unsafe {
        Motor::cargar(&dll, datos.as_deref())
    });
    let mut motor = match preparado {
        Ok(motor) => {
            if responder(&mut salida, Ok(motor.voces.join("\n"))).is_err() {
                return;
            }
            motor
        }
        Err(error) => {
            let _ = responder(&mut salida, Err(error));
            return;
        }
    };

    loop {
        let marco = match leer_marco(&mut entrada) {
            Ok(Some(marco)) => marco,
            Ok(None) => break,
            Err(error) => {
                let _ = responder(&mut salida, Err(error.to_string()));
                break;
            }
        };
        let (orden, carga) = marco;
        let resultado: Result<String, String> = unsafe {
            match orden {
                OP_ENUMERAR => Ok(motor.voces.join("\n")),
                OP_ELEGIR => String::from_utf8(carga)
                    .map_err(|_| "el nombre de voz no es UTF-8".to_string())
                    .and_then(|nombre| motor.elegir(&nombre).map(|_| String::new())),
                OP_PARAMETRO => {
                    let clave = u32_en(&carga, 0);
                    let valor = u32_en(&carga, 4);
                    clave.and_then(|c| valor.and_then(|v| motor.parametro(c, v)))
                        .map(|_| String::new())
                }
                OP_DECIR => {
                    let modo = u32_en(&carga, 0);
                    modo.and_then(|m| {
                        let texto = String::from_utf8(carga[4..].to_vec())
                            .map_err(|_| "el texto no es UTF-8".to_string())?;
                        motor.decir(&texto, m)
                    })
                    .map(|_| String::new())
                }
                OP_PAUSAR => motor.pausar().map(|_| String::new()),
                OP_CONTINUAR => motor.continuar().map(|_| String::new()),
                OP_DETENER => motor.detener().map(|_| String::new()),
                OP_ESTADO => Ok(if HABLANDO.load(Ordering::Acquire)
                    || PAUSADO.load(Ordering::Acquire)
                {
                    "1".to_string()
                } else {
                    "0".to_string()
                }),
                OP_CERRAR => {
                    let _ = responder(&mut salida, Ok(String::new()));
                    break;
                }
                _ => Err("orden desconocida".to_string()),
            }
        };
        if responder(&mut salida, resultado).is_err() {
            break;
        }
    }
}

// Evita que un cambio accidental añada ficheros o mecanismos de instalación.
#[allow(dead_code)]
fn _solo_archivos_locales(ruta: &Path) -> bool {
    fs::metadata(ruta).map(|m| m.is_file()).unwrap_or(false)
}
