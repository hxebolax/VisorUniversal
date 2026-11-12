# -*- coding: utf-8 -*-
"""Datos de identidad del programa: versión, autoría y enlaces.

Está aparte y sin ninguna importación a propósito.  Lo leen el programa (la
pantalla de bienvenida, el diálogo «Acerca de», la cabecera del registro) y
también el guion de compilación, que lo abre como texto sin llegar a ejecutar
nada.  Así basta con cambiar aquí el número para que quede cambiado en todas
partes a la vez.
"""

#: Nombre del programa.  Está aquí y solo aquí: todo lo demás lo lee de este
#: módulo, de forma que cambiarlo es cambiar una línea.  No lleva ``_()`` a
#: propósito —un nombre propio no se traduce— y por eso tampoco aparece dentro
#: de los textos traducibles: se interpola en ellos.
NOMBRE = "Visor Universal"

#: El mismo nombre sin espacios, para lo que no los admite: el ejecutable, el
#: nombre de la instancia única y las carpetas.
NOMBRE_ARCHIVO = "VisorUniversal"

#: Versión del programa.  Es lo único que hay que tocar al publicar una nueva.
VERSION = "1.3.8"

#: Autor del programa.
AUTOR = "Héctor J. Benítez Corredera"

#: Aviso de derechos de autor que se muestra en «Acerca de».
COPYRIGHT = "Copyright (C) 2026 Héctor J. Benítez Corredera"

#: Licencia con la que se distribuye.  Se deja sin traducir a propósito: el
#: nombre de una licencia es el mismo en todos los idiomas, y este módulo lo
#: lee el guion de compilación como texto, sin ejecutar nada.
LICENCIA = "GPL (GNU General Public License)"

#: Página de donaciones que abre «Invítame a un café si te gusta mi trabajo».
URL_DONACIONES = "https://www.paypal.com/paypalme/hjbcdonaciones?country.x=ES&locale.x=es_ES"

#: Dirección donde se publican las actualizaciones.  **Es lo único que hay que
#: rellenar para que el programa avise de las versiones nuevas.**  Es la carpeta
#: del servidor —sin barra final— donde se dejan los dos archivos que genera
#: ``herramientas/empaquetar.py`` al compilar:
#:
#: * ``version.json``, el aviso de versión con su ``sha256`` y su firma.
#: * ``VisorUniversal_v<version>.zip``, el paquete de esa versión.
#:
#: Por ejemplo:
#:
#:     URL_ACTUALIZACIONES = "https://xebolax.synology.me/VisorUniversal"
#:
#: Sirve cualquier sitio que sepa servir dos archivos por HTTPS: un servidor
#: propio, un alojamiento web, un espacio de almacenamiento público.
#:
#: Dejándola vacía, no se pregunta a ningún servidor.  La orden «Buscar
#: actualizaciones» sigue en el menú de Ayuda —para que se vea que existe— y al
#: pulsarla dice que no hay servidor configurado.
URL_ACTUALIZACIONES = "https://xebolax.synology.me/VisorUniversal"

#: Repositorio de GitHub, como ``propietario/nombre``, donde está el código y
#: donde se publica cada versión como *release* con los mismos dos archivos
#: (``version.json`` y el ZIP) adjuntos.  Es la segunda fuente de
#: actualizaciones: en Opciones, «Avanzado», se elige si se busca en el
#: servidor, en GitHub, en los dos o en una dirección personalizada.
#:
#: Dejándolo vacío, GitHub no se ofrece como fuente.
REPOSITORIO_GITHUB = "hxebolax/VisorUniversal"

#: Clave pública Ed25519, en hexadecimal, con la que se comprueba la **firma**
#: del ``version.json``.  Separa la autenticidad del transporte: el ``sha256``
#: evita instalar una descarga corrompida, pero si alguien se hiciera con el
#: servidor cambiaría el ZIP y su resumen a la vez.  Con la firma le haría falta
#: además la clave **privada**, que no está ni en el servidor ni aquí.
#:
#: **Esto se rellena solo.**  Al compilar (opción 3 del menú), el programa crea
#: el par de claves la primera vez, escribe aquí la pública y firma el
#: ``version.json`` del paquete.  No hay que tocar nada: basta con subir al
#: servidor el ZIP y el JSON que quedan en ``build``.
#:
#: La clave privada vive en ``herramientas/claves/visor_ed25519.key``, fuera de
#: todo lo que se empaqueta.  **Guarda una copia fuera del equipo**: es lo único
#: que no se puede rehacer, porque cambiarla dejaría sin actualizaciones a quien
#: ya tenga instalada una versión firmada con la anterior.
CLAVE_PUBLICA = "24763f2afcaded58159dd7f941b4a9e0b4f5f2c2e792b1ac4777e80d96cb501a"
