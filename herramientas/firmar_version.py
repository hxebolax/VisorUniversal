# -*- coding: utf-8 -*-
"""Firma del aviso de versión con Ed25519.

El ``sha256`` que se publica junto al paquete protege del transporte: una
descarga a medias o manipulada por el camino no se instala.  Lo que **no**
protege es del propio servidor: quien se hiciera con él podría cambiar el ZIP y
su resumen a la vez, y todos los clientes lo aceptarían.

La firma cierra ese hueco.  Se firma el mensaje ``"<version>:<sha256>"`` con una
clave **privada** que no está en el servidor ni dentro del programa, y el
programa lleva incrustada la **pública** en :data:`version.CLAVE_PUBLICA`.  Sin
la privada no se puede fabricar un aviso que los clientes acepten, así que
secuestrar el servidor no basta para colar una versión falsa.

Normalmente no hay que llamar a nada de esto a mano: **al compilar se hace
solo**.  El guion de compilación llama a ``preparar``, que la primera vez crea
el par de claves y escribe la pública en ``src/version.py``, y después
``empaquetar.py`` firma el ``version.json``.  Lo único que queda por hacer es
subir al servidor el ZIP y el JSON.

A mano, por si hace falta:

* ``python herramientas/firmar_version.py preparar`` — crea la clave si no la
  hay y deja la pública puesta en ``version.py``.
* ``python herramientas/firmar_version.py estado`` — dice qué hay y si cuadra.
* ``python herramientas/firmar_version.py firmar build/version.json`` — firma un
  manifiesto concreto.

**Guarda una copia de la clave privada fuera del equipo.**  Es lo único que no
se puede rehacer: sin ella no se pueden publicar más versiones que los clientes
ya instalados acepten, y habría que repartir a mano una versión con una clave
nueva.
"""

from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

#: Dónde vive la clave privada del proyecto.  La carpeta ``claves`` queda fuera
#: de lo que se empaqueta: la compilación solo copia ``data`` y las bibliotecas
#: de Visual C++, así que la privada no puede colarse en el ZIP ni por
#: descuido.
CLAVE = RAIZ / "herramientas" / "claves" / "visor_ed25519.key"

#: Archivo donde vive la clave pública, dentro del programa.
VERSION_PY = RAIZ / "src" / "version.py"


# ---------------------------------------------------------------------------
# Las claves
# ---------------------------------------------------------------------------

def _ruta_clave(clave: Path | None = None) -> Path:
    """La ruta de la clave privada que toca usar.

    Se resuelve **al llamar** y no como valor por omisión de cada función: un
    valor por omisión se fija al definirse, y entonces cambiar :data:`CLAVE`
    —para probar, o para tener el proyecto en otro sitio— no surtiría efecto en
    las funciones que la usan por dentro.
    """
    return clave if clave is not None else CLAVE


def hay_clave(clave: Path | None = None) -> bool:
    """Indica si el proyecto tiene clave privada con la que firmar."""
    return _ruta_clave(clave).is_file()


def generar(destino: Path | None = None, forzar: bool = False) -> str:
    """Crea un par de claves nuevo y devuelve la pública en hexadecimal.

    :param forzar: Necesario para sustituir una clave que ya existe.  Sin él no
                   se toca: cambiar de clave deja **sin actualizaciones** a
                   todos los que tengan instalada una versión con la anterior,
                   porque rechazarán cualquier aviso firmado con la nueva.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    destino = _ruta_clave(destino)
    if destino.exists() and not forzar:
        raise SystemExit(
            "Ya hay una clave en %s.\n"
            "Generar otra dejaría sin actualizaciones a quien tenga instalada una\n"
            "versión firmada con la anterior. Si de verdad quieres empezar de cero,\n"
            "bórrala a mano y vuelve a intentarlo." % destino)

    privada = Ed25519PrivateKey.generate()
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(privada.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption()))
    return clave_publica_de(destino)


def clave_publica_de(clave: Path | None = None) -> str:
    """Deduce la clave pública a partir de la privada, en hexadecimal.

    Se deduce y no se guarda aparte: así no pueden desincronizarse nunca, que es
    el fallo más tonto y más difícil de encontrar de todo este asunto.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    privada = Ed25519PrivateKey.from_private_bytes(_ruta_clave(clave).read_bytes())
    return privada.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw).hex()


# ---------------------------------------------------------------------------
# La clave pública dentro del programa
# ---------------------------------------------------------------------------

def clave_en_version() -> str:
    """La clave pública que hay ahora mismo en ``version.py``."""
    fuente = VERSION_PY.read_text(encoding="utf-8")
    encontrada = re.search(r'^CLAVE_PUBLICA\s*=\s*["\']([^"\']*)["\']', fuente, re.M)
    return encontrada.group(1) if encontrada else ""


def escribir_en_version(publica: str) -> bool:
    """Deja esa clave pública en ``version.py``.

    :return: ``True`` si el archivo ha cambiado.

    Se sustituye solo el valor y se respeta todo lo demás —los comentarios que
    explican para qué sirve, el resto del archivo—: este guion lo ejecuta la
    compilación y no puede permitirse reescribir a lo bruto un archivo que se
    lee a mano.
    """
    fuente = VERSION_PY.read_text(encoding="utf-8")
    if clave_en_version() == publica:
        return False
    nuevo, cuantas = re.subn(r'^CLAVE_PUBLICA\s*=\s*["\'][^"\']*["\']',
                            'CLAVE_PUBLICA = "%s"' % publica, fuente, count=1, flags=re.M)
    if not cuantas:
        raise SystemExit("No se encuentra CLAVE_PUBLICA en %s" % VERSION_PY)
    VERSION_PY.write_text(nuevo, encoding="utf-8", newline="")
    return True


# ---------------------------------------------------------------------------
# Lo que llama la compilación
# ---------------------------------------------------------------------------

def preparar() -> str:
    """Deja todo listo para firmar, sin preguntar nada.

    Es lo que llama el guion de compilación **antes** de compilar, y en ese
    orden a propósito: la clave pública tiene que estar dentro de
    ``version.py`` cuando cx_Freeze empaqueta el programa, o el ejecutable
    saldría sin ella y no comprobaría ninguna firma.

    La primera vez crea el par de claves; las demás solo comprueba que la
    pública que hay en ``version.py`` es la que corresponde a la privada.

    :return: La clave pública en hexadecimal.
    """
    if not hay_clave():
        publica = generar()
        print("Se ha creado el par de claves de firma:")
        print("   %s" % _ruta_clave())
        print()
        print("   GUARDA UNA COPIA DE ESE ARCHIVO FUERA DEL EQUIPO.")
        print("   Sin él no se pueden publicar más actualizaciones que los")
        print("   programas ya instalados acepten.")
        print()
    else:
        publica = clave_publica_de()

    if escribir_en_version(publica):
        print("Clave pública puesta en src/version.py:")
        print("   %s" % publica)
    return publica


def _url_de_actualizaciones() -> str:
    """La dirección del servidor que haya en ``version.py``.

    Se lee como texto y no importando el módulo: así este guion funciona sin
    tener que meter ``src`` en la ruta de importación, que es justo lo que
    permite ejecutarlo desde el ``.bat`` sin más preparativos.
    """
    fuente = VERSION_PY.read_text(encoding="utf-8")
    encontrada = re.search(r'^URL_ACTUALIZACIONES\s*=\s*["\']([^"\']*)["\']', fuente, re.M)
    return encontrada.group(1) if encontrada else ""


def estado() -> None:
    """Cuenta cómo está la firma, para mirarlo desde el menú."""
    print("Clave privada: %s" % (_ruta_clave() if hay_clave() else "NO EXISTE todavía"))
    if hay_clave():
        publica = clave_publica_de()
        en_version = clave_en_version()
        print("Clave publica: %s" % publica)
        if en_version == publica:
            print("En version.py: la misma. Todo correcto.")
        elif not en_version:
            print("En version.py: VACIA. Se pondra al compilar.")
        else:
            print("En version.py: OTRA DISTINTA. Se corregira al compilar.")
            print("   (%s)" % en_version)
    else:
        print("Clave publica: se creara al compilar por primera vez.")
    print()
    if not _url_de_actualizaciones().strip():
        print("AVISO: no hay servidor de actualizaciones en src/version.py.")
        print("       La firma se genera igual, pero nadie va a buscarla.")


# ---------------------------------------------------------------------------
# Firmar un manifiesto
# ---------------------------------------------------------------------------

def firmar(ruta_json: Path, clave: Path | None = None) -> None:
    """Añade al aviso de versión el campo ``firma_ed25519``."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    clave = _ruta_clave(clave)
    if not clave.exists():
        raise SystemExit(
            "No se encuentra la clave privada: %s\n"
            "Genérala con: python herramientas/firmar_version.py preparar" % clave)

    privada = Ed25519PrivateKey.from_private_bytes(clave.read_bytes())
    manifiesto = json.loads(Path(ruta_json).read_text(encoding="utf-8"))
    version = str(manifiesto.get("version", "")).strip()
    resumen = str(manifiesto.get("sha256", "")).strip().lower()
    if not version or not resumen:
        raise SystemExit("El aviso de versión necesita «version» y «sha256» antes de firmarse.")

    mensaje = ("%s:%s" % (version, resumen)).encode("utf-8")
    manifiesto["firma_ed25519"] = base64.b64encode(privada.sign(mensaje)).decode("ascii")
    Path(ruta_json).write_text(
        json.dumps(manifiesto, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Firmado: %s (versión %s)" % (ruta_json, version))


if __name__ == "__main__":
    orden = sys.argv[1] if len(sys.argv) > 1 else ""
    if orden == "preparar":
        preparar()
    elif orden == "estado":
        estado()
    elif orden == "generar":
        # Sigue estando, para quien quiera crear la clave por su cuenta.
        print("Clave pública: %s"
              % generar(Path(sys.argv[2]) if len(sys.argv) > 2 else CLAVE))
    elif orden == "firmar" and len(sys.argv) > 2:
        firmar(Path(sys.argv[2]))
    else:
        print(__doc__)
        raise SystemExit(1)
