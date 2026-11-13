# -*- coding: utf-8 -*-
"""Lectura del libro en voz alta, frase a frase.

Es el «reproductor» del programa: se pone a leer desde donde está el cursor y
va encadenando frases hasta el final del libro, con pausa, frase anterior y
frase siguiente, velocidad al vuelo y elección de voz.

Cómo funciona
-------------

SAPI no avisa cuando termina de decir algo, así que el encadenado se resuelve
con un temporizador que, varias veces por segundo, mira si la voz sigue
hablando; en cuanto calla, se le pasa la frase siguiente.  Es sencillo, no
necesita hilos y sobrevive a que el usuario cambie de ventana.

El cursor **no se mueve mientras se lee**, y esto es deliberado.  El control de
texto tiene el foco, de modo que mover el cursor haría que el lector de
pantalla leyera la línea *además* de nuestra voz: dos voces diciendo lo mismo a
la vez.  En su lugar se recuerda por dónde va la lectura y el cursor se coloca
ahí **al pausar o al detener**, que es cuando el usuario quiere seguir a mano
justo por donde lo dejó.  Quien prefiera lo contrario —por ejemplo para
seguirlo en una línea braille— puede activarlo en las opciones.

Al parar, «ahí» son dos sitios distintos según para qué se pare, y también se
elige en las opciones: al **principio** de la frase que sonaba, para volver a
leerla porque no se ha entendido, o **detrás** de ella, para que las flechas
sigan por lo que aún no se ha oído en lugar de repetir el párrafo.

El texto sale del documento completo, no del tramo cargado en el control, así
que la lectura no se detiene en los bordes de la ventana deslizante y puede
recorrer un libro entero sin intervención.
"""

from __future__ import annotations

import time

import wx

from interfaz.temporizadores import parar_al_destruir
from interfaz.accesible import etiquetar, fila_etiquetada
from interfaz.dialogos import ayuda_opcion
from nucleo import omisiones, pronunciacion, quimica, segmentador
from nucleo.idioma import _
from nucleo.marcas import TipoMarca
from nucleo.registro import obtener_registro
from nucleo.voz import (RAPIDEZ_NORMAL, Sintetizador, parecido,
                       sapi_desde_porcentaje)

log = obtener_registro(__name__)

MARGEN = 8

#: Cada cuánto se comprueba si la voz ha terminado la frase, en milisegundos.
#: Bajarlo hace el encadenado más ajustado; subirlo, más barato.  A 120 ms el
#: hueco entre frases no se nota y el coste es inapreciable.
LATIDO = 120

#: Margen, en segundos, desde que se le pasa una frase a la voz hasta que se
#: empieza a comprobar si ha terminado.  SAPI tarda unas centésimas en decir
#: que está hablando, y sin este margen la comprobación llegaba a tiempo de ver
#: la voz «callada» y pasaba a la frase siguiente.  Eso es lo que hacía que
#: «frase anterior» pareciera no funcionar: retrocedía una y el latido
#: siguiente la adelantaba otra, dejándolo todo igual.
MARGEN_ARRANQUE = 0.30

#: Cuánto se espera, como mucho, a un motor que no dice lo que tarda.  Se usa
#: solo cuando el motor no declara su propia espera; los que la declaran mandan.
MARGEN_ARRANQUE_MAXIMO = 30.0

#: A partir de cuánta espera se empieza a avisar con un pulso, en segundos.  Por
#: debajo de esto no se avisa: un pitido antes de cada frase sería insufrible.
ESPERA_PARA_AVISAR = 0.7

#: Cada cuánto se repite el pulso mientras se espera.
ESPERA_ENTRE_PULSOS = 1.2

#: Y a partir de cuánta espera se dice además con palabras.  Es para el caso
#: raro: la primera frase de una voz neuronal, o una conexión que se ha caído.
ESPERA_PARA_DECIRLO = 2.5


class LectorEnVozAlta:
    """Lee el libro en voz alta desde la posición del cursor.

    :param ventana: Ventana principal, de donde salen el documento, el panel de
                    lectura y los anuncios.
    """

    def __init__(self, ventana) -> None:
        self.ventana = ventana
        #: El sintetizador del motor elegido.  Empieza siendo el de Windows y
        #: se cambia en cuanto se sabe cuál toca: construirlo aquí obligaría a
        #: leer la configuración antes de que la ventana esté montada.
        self.sintetizador = Sintetizador()
        #: Lo que hubo que decir al arrancar el motor, si hubo algo.  Se guarda
        #: en vez de enseñarlo aquí porque al construir el lector todavía no hay
        #: dónde enseñarlo.
        self.aviso_motor = ""
        #: Tramo de la frase que se está diciendo, en posiciones del libro.
        self.frase: tuple[int, int] = (0, 0)
        #: Dónde retomar cuando se ha parado para buscar. Guardarlo
        #: aquí y no en la ventana es lo que permite que buscar dos
        #: veces seguidas siga volviendo al mismo sitio.
        self._retomar_en = None
        #: Dónde se dejó el cursor la última vez que se paró.  Sirve para saber
        #: si el usuario se ha movido después: al reanudar hay que distinguir
        #: «sigo donde lo dejaste» de «me he ido a otra parte, empieza aquí», y
        #: con el cursor detrás de la frase —que es lo que se puede pedir en las
        #: opciones— la comparación con el tramo de la frase ya no basta.
        self._cursor_puesto: int | None = None
        #: Si en **este** documento un guion al principio del renglón cuenta
        #: como raya de diálogo. Se decide una vez y no frase a frase: es lo que
        #: evita que en el mismo libro un guion sea diálogo en una página y una
        #: lista en la siguiente.
        self._dialogos_con_guion = False
        self._leyendo = False
        #: Momento en que se le pasó la frase actual a la voz, y si se ha
        #: llegado a ver hablando.  Los dos juntos evitan adelantar una frase
        #: que todavía no ha empezado a sonar.
        self._lanzada_en = 0.0
        self._ha_sonado = False
        #: Cuándo sonó el último pulso de «estoy preparando la voz», y si ya se
        #: ha dicho con palabras.  Los dos se reinician con cada frase.
        self._ultimo_pulso = 0.0
        self._espera_dicha = False
        #: Tabla de pronunciación en vigor.  Se rehace al abrir un documento y
        #: al cambiar las reglas; compilarla en cada frase costaría más que
        #: leerla.
        self.pronunciacion = pronunciacion.VACIA
        #: Cómo se dicen las fórmulas químicas en este documento.  Se resuelve
        #: al abrirlo y no en cada frase: decidirlo obliga a mirar el texto, y
        #: eso hay que hacerlo una vez.
        self.modo_quimica = "no"
        #: Tramos que la voz no dice: llamadas de nota, folios y cabeceras
        #: repetidas.  Se calculan al abrir el documento, igual que la química.
        self.omisiones = omisiones.NINGUNA
        #: Voz elegida en las opciones y voz que está puesta ahora mismo.  Son
        #: dos cosas distintas en cuanto el documento cambia de idioma: al
        #: llegar a una cita en inglés se pone una voz inglesa, y al salir de
        #: ella hay que volver a la del usuario, no a otra española cualquiera.
        self._voz_elegida = ""
        self._voz_puesta = ""
        self._temporizador = wx.Timer(ventana)
        parar_al_destruir(ventana, self._temporizador)
        ventana.Bind(wx.EVT_TIMER, self._al_latir, self._temporizador)

    # -- estado --------------------------------------------------------------

    @property
    def disponible(self) -> bool:
        """Indica si el equipo tiene voces con las que leer."""
        return self.sintetizador.disponible

    @property
    def leyendo(self) -> bool:
        """Indica si hay una lectura en curso, aunque esté pausada."""
        return self._leyendo

    def _configuracion(self):
        """Atajo a las preferencias de la aplicación."""
        return self.ventana.configuracion

    def _texto(self) -> str:
        """Texto completo del libro abierto, o cadena vacía si no hay ninguno."""
        documento = self.ventana.documento
        return documento.texto if documento is not None else ""

    # -- ajustes -------------------------------------------------------------

    def aplicar_motor(self) -> str:
        """Pone el sintetizador del motor elegido. Devuelve el aviso, si lo hay.

        Se llama al arrancar y cada vez que se cambia de motor en la ventana de
        la voz. El anterior se cierra: un motor puede tener abierto un proceso
        de treinta y dos bits o una conexión, y dejarlos colgando iría sumando
        uno por cada cambio.
        """
        from nucleo import motores_voz

        configuracion = self._configuracion()
        elegido = str(configuracion.obtener("voz_motor", motores_voz.SAPI5))
        ajustes = dict(configuracion.obtener("voz_ajustes_motores", {}) or {})
        nuevo, aviso = motores_voz.crear(elegido, ajustes.get(elegido, {}))
        anterior = self.sintetizador
        self.sintetizador = nuevo
        if anterior is not None and anterior is not nuevo:
            try:
                anterior.detener()
                cerrar = getattr(anterior, "cerrar", None)
                if callable(cerrar):
                    cerrar()
            except Exception as error:
                log.debug("Al cerrar el motor anterior: %s", error)
        # La lista de voces por idioma es del motor que había: si no se olvida,
        # al cambiar de motor se buscarían voces que este no tiene.
        self._voz_elegida = ""
        self._voz_puesta = ""
        self.aviso_motor = aviso
        if aviso:
            log.warning("Motor de voz: %s", aviso)
        return aviso

    def aplicar_ajustes(self) -> None:
        """Lleva a la voz la voz, la velocidad y el volumen configurados."""
        configuracion = self._configuracion()
        nombre = str(configuracion.obtener("voz_nombre", "") or "")
        if nombre:
            self.sintetizador.elegir_voz(nombre)
        self._voz_elegida = nombre or self.sintetizador.voz_actual()
        self._voz_puesta = self._voz_elegida
        self.sintetizador.establecer_velocidad(
            sapi_desde_porcentaje(int(configuracion.obtener("voz_rapidez", RAPIDEZ_NORMAL))))
        self.sintetizador.establecer_volumen(int(configuracion.obtener("voz_volumen", 100)))

    def mirar_si_hay_dialogo(self) -> None:
        """Mira, al abrir un documento, cómo marca sus diálogos.

        Se hace una vez por libro porque la respuesta vale para el libro entero,
        y porque recorrer el texto en cada frase costaría más que decirla.
        """
        from nucleo import dialogos

        texto = self._texto()
        self._dialogos_con_guion = bool(texto) and not dialogos.usa_rayas(texto)

    def refrescar_pronunciacion(self) -> None:
        """Rehace la tabla de pronunciación del documento abierto."""
        self.pronunciacion = pronunciacion.tabla_para(
            self._configuracion(), getattr(self.ventana, "ruta_actual", ""))
        configuracion = self._configuracion()
        self.modo_quimica = quimica.modo_efectivo(
            str(configuracion.obtener("voz_quimica", "auto")), self._texto())
        self.omisiones = omisiones.Omisiones(
            self.ventana.documento,
            notas=bool(configuracion.obtener("voz_saltar_notas", False)),
            paginas=bool(configuracion.obtener("voz_saltar_folios", False)),
            repetidos=bool(configuracion.obtener("voz_saltar_cabeceras", False)))

    def _para_decir(self, texto: str) -> str:
        """Deja una frase lista para la voz: química y pronunciación.

        El orden importa.  Primero la química, que trabaja sobre las fórmulas
        tal como están escritas; después el diccionario del usuario, que es la
        última palabra y puede corregir cualquier cosa de lo anterior.
        """
        return self.pronunciacion.aplicar(quimica.leer(texto, self.modo_quimica))

    def cambiar_velocidad(self, incremento: int) -> None:
        """Sube o baja la velocidad y **la aplica al momento**.

        SAPI fija la velocidad al encolar cada texto: lo que ya está sonando
        conserva la suya pase lo que pase.  Si solo se cambiara el ajuste, el
        efecto no se oiría hasta la frase siguiente, que en un párrafo largo
        puede tardar bastante y da la impresión de que la tecla no funciona.

        Por eso, si se está leyendo, se vuelve a decir la frase en curso desde
        el principio con la velocidad nueva.  Las frases son cortas por
        diseño, así que repetirla cuesta poco y a cambio se oye el cambio en el
        acto, que es lo único que permite ajustar la velocidad de oído.

        :param incremento: Puntos de porcentaje que se suman o se restan.
        """
        configuracion = self._configuracion()
        valor = int(configuracion.obtener("voz_rapidez", RAPIDEZ_NORMAL)) + incremento
        valor = max(0, min(100, valor))
        configuracion.establecer("voz_rapidez", valor)
        configuracion.guardar()
        self.sintetizador.establecer_velocidad(sapi_desde_porcentaje(valor))
        self.ventana.anunciar("Velocidad %d por ciento." % valor, inmediato=True)
        if self._leyendo and not self.sintetizador.pausada:
            self._decir_desde(self.frase[0])

    # -- órdenes -------------------------------------------------------------

    def alternar(self) -> None:
        """Empieza a leer, pausa o continúa, según el momento.

        Es la orden principal, la de una sola tecla: si no se está leyendo,
        empieza desde el cursor; si se está leyendo, pausa; si estaba pausada,
        sigue.
        """
        if not self._comprobar():
            return
        if not self._leyendo:
            self.empezar(self.ventana.lector.posicion())
            return
        if self.sintetizador.pausada:
            # Si durante la pausa el usuario se ha ido a leer a otra parte con
            # las flechas, al reanudar se empieza **donde está**, no donde se
            # quedó la voz: es lo que uno espera después de haberse movido, y
            # convierte la pausa en la forma natural de saltar a otro punto.
            #
            # «Otra parte» es cualquier sitio que no sea la frase que sonaba ni
            # el punto exacto donde la pausa dejó el cursor.  Lo segundo hace
            # falta desde que el cursor se puede dejar **detrás** de la frase:
            # ahí está fuera del tramo, y sin esta comprobación reanudar se
            # comería el final de la frase que se había pausado.
            posicion = self.ventana.lector.posicion()
            if (posicion != self._cursor_puesto
                    and not self.frase[0] <= posicion < self.frase[1]):
                self.empezar(posicion)
                return
            self.sintetizador.continuar()
            self.ventana.anunciar(_("Se sigue leyendo."), inmediato=True)
        else:
            self.sintetizador.pausar()
            self._llevar_cursor(al_parar=True)
            self.ventana.anunciar(_("Lectura en pausa."), inmediato=True)

    def empezar(self, desde: int) -> None:
        """Empieza a leer desde una posición del libro."""
        if not self._comprobar():
            return
        self.aplicar_ajustes()
        self._leyendo = True
        self.frase = (desde, desde)
        log.info("Lectura en voz alta desde la posición %d", desde)
        if not self._decir_desde(desde):
            self.detener()
            self.ventana.anunciar(_("No queda nada por leer."), inmediato=True)
            return
        self._temporizador.Start(LATIDO)

    def pausar_para_buscar(self) -> bool:
        """Calla la voz **sin olvidar que estaba leyendo**.

        Es la diferencia entre parar y perder el sitio. Buscar algo mientras se
        escucha un libro es lo más normal del mundo —«¿dónde decía esto?»— y
        hasta ahora costaba la lectura entera: había que parar, buscar, volver a
        colocarse a mano y arrancar otra vez.

        Devuelve si de verdad estaba leyendo, para que quien llama sepa si
        tendrá algo que reanudar.
        """
        if not self.leyendo:
            # Y se olvida lo que hubiera pendiente: si ahora no suena nada, no
            # hay ninguna lectura esperando, y guardar un sitio de hace media
            # hora haría que una búsqueda cualquiera arrancara el libro solo.
            self._retomar_en = None
            return False
        self._retomar_en = self.frase[0] if self.frase else None
        self.detener()
        return True

    def seguir_desde(self, posicion: int | None = None) -> bool:
        """Vuelve a leer, desde donde se diga o desde donde se dejó.

        Con una posición, se sigue **desde el resultado de la búsqueda**, que es
        lo que se quería: se ha buscado para leer desde ahí. Sin ella, se vuelve
        exactamente a la frase que se estaba diciendo.
        """
        if posicion is None:
            posicion = self._retomar_en
        self._retomar_en = None
        if posicion is None or not self.disponible:
            return False
        self.empezar(posicion)
        return True

    @property
    def habia_lectura(self) -> bool:
        """Si hay una lectura en pausa esperando a que se reanude."""
        return self._retomar_en is not None

    def detener(self, anunciar: bool = False) -> None:
        """Corta la lectura y deja el cursor en la frase donde iba."""
        estaba = self._leyendo
        self._temporizador.Stop()
        self.sintetizador.detener()
        self._leyendo = False
        self.ventana.lector._quitar_resalte()
        if estaba:
            self._llevar_cursor(al_parar=True)
        if anunciar and estaba:
            self.ventana.anunciar(_("Lectura detenida."), inmediato=True)

    def saltar_frase(self, adelante: bool) -> None:
        """Va a la frase siguiente o a la anterior sin salir de la lectura."""
        if not self._leyendo:
            # Fuera de la lectura, la orden mueve el cursor: así las mismas
            # teclas sirven para recorrer el libro frase a frase en silencio.
            self._mover_cursor_una_frase(adelante)
            return
        texto = self._texto()
        if adelante:
            destino = self.frase[1]
        else:
            inicio, _fin = segmentador.frase_anterior(texto, self.frase[0])
            destino = inicio
        self.sintetizador.continuar()   # si estaba en pausa, se reanuda al saltar
        if not self._decir_desde(destino):
            self.detener()
            self.ventana.anunciar(_("Final del documento."), inmediato=True)

    def leer_seleccion(self) -> None:
        """Lee en voz alta solo lo que esté seleccionado."""
        if not self._comprobar():
            return
        desde, hasta = self.ventana.lector.seleccion()
        if desde == hasta:
            self.ventana.anunciar(_("No hay nada seleccionado."), inmediato=True)
            return
        self.aplicar_ajustes()
        self.detener()
        self.sintetizador.decir(self._para_decir(
            segmentador.para_decir(self._texto()[desde:hasta])))

    # -- motor ---------------------------------------------------------------

    def _comprobar(self) -> bool:
        """Comprueba que se puede leer, y avisa con claridad si no."""
        if self.ventana.documento is None:
            self.ventana.anunciar(_("Abre un documento para poder leerlo en voz alta."), inmediato=True)
            return False
        if not self.sintetizador.disponible:
            wx.MessageBox(
                _("Este equipo no tiene ninguna voz del sistema instalada, así que no se puede "
                "leer en voz alta.\n\nLas voces se añaden en Configuración de Windows, "
                "en «Hora e idioma», «Voz»."),
                _("Lectura en voz alta"), wx.OK | wx.ICON_INFORMATION, self.ventana)
            return False
        return True

    def _decir_desde(self, posicion: int, continuacion: bool = False) -> bool:
        """Dice la frase que empieza en esa posición.  Devuelve si había alguna."""
        texto = self._texto()
        inicio, fin = segmentador.siguiente_frase(texto, posicion)
        if inicio >= fin:
            return False
        self.frase = (inicio, fin)
        self._lanzada_en = time.monotonic()
        self._ha_sonado = False
        # El aviso de espera se cuenta por frase: si no, la primera frase de un
        # motor lento dejaría dicho «preparando la voz» para todo el capítulo.
        self._ultimo_pulso = 0.0
        self._espera_dicha = False
        if self._configuracion().obtener("voz_mover_cursor", False):
            self._llevar_cursor(lectura=continuacion)
        if self._configuracion().obtener("voz_resaltar_frase", False):
            self.ventana.lector.resaltar_frase(inicio, fin)
        # La pronunciación se aplica **aquí y solo aquí**: cambia lo que se
        # oye, no el libro.  El texto que se ve, se copia y se busca sigue
        # siendo exactamente el del autor.
        self._ajustar_idioma(inicio)
        crudo = self.omisiones.filtrar(texto[inicio:fin], inicio)
        dicho = segmentador.para_decir(crudo) + self._descripciones_en(inicio, fin)
        if not dicho.strip():
            # La frase entera era algo que no se dice —un folio suelto, una
            # cabecera repetida—.  Se pasa a la siguiente en vez de quedarse
            # callado, que es lo que haría el ojo al leer.
            return self._decir_desde(fin)
        listo = self._para_decir(dicho)
        marcado = self._con_tono_de_dialogo(listo)
        if marcado is not None:
            return self.sintetizador.decir(marcado, con_marcas=True)
        return self.sintetizador.decir(listo)

    def _con_tono_de_dialogo(self, texto: str):
        """Devuelve el texto con las marcas de tono, o ``None`` si no toca.

        Es el «modo entrevista»: en una novela con mucho diálogo, oírlo todo con
        la misma voz obliga a reconstruir sobre la marcha quién dice cada cosa.
        Quien lee con los ojos ve las rayas en el margen; de oído no están.

        Devolver ``None`` y no el texto tal cual es a propósito: así la lectura
        normal **no pasa por el camino de las marcas**, que obliga a escapar el
        texto y a que la voz lo interprete. Lo que no hace falta, no se hace.
        """
        if not self._configuracion().obtener("voz_modo_dialogo", False):
            return None
        tono = int(self._configuracion().obtener("voz_tono_dialogo", 4) or 0)
        if not tono:
            return None
        from nucleo import dialogos

        trozos = dialogos.tramos(texto, con_guiones=self._dialogos_con_guion)
        if not any(es_dialogo for _trozo, es_dialogo in trozos):
            return None
        return "".join(self.sintetizador.con_tono(trozo, tono if es_dialogo else 0)
                       for trozo, es_dialogo in trozos)

    def _ajustar_idioma(self, posicion: int) -> None:
        """Pone la voz que corresponde al idioma del texto que va a decir.

        Los libros bien hechos —un EPUB accesible, un PDF etiquetado según
        PDF/UA— dicen en qué idioma está cada fragmento.  Leer una cita en
        inglés con una voz española la vuelve incomprensible, así que aquí se
        hace lo mismo que hacen los lectores de pantalla: si hay instalada una
        voz de ese idioma, se cambia a ella mientras dure el fragmento y se
        vuelve a la del usuario en cuanto se sale.

        Si no hay ninguna voz de ese idioma no se toca nada: es mejor oírlo con
        acento que no oírlo.
        """
        if not self._configuracion().obtener("voz_seguir_idioma", True):
            if self._voz_puesta != self._voz_elegida:
                self._poner_voz(self._voz_elegida)
            return
        documento = self.ventana.documento
        codigo = ""
        if documento is not None:
            marca = documento.marcas.marca_que_cubre(TipoMarca.IDIOMA, posicion)
            if marca is not None:
                codigo = marca.texto
        if not codigo:
            self._poner_voz(self._voz_elegida)
            return
        # Si la voz del usuario ya sirve tan bien como la mejor que haya
        # instalada para ese idioma, se queda: cambiar de voz sin ganar nada
        # solo consigue que el libro suene a dos personas distintas.
        idiomas = dict(self.sintetizador.voces_con_idioma())
        propia = parecido(idiomas.get(self._voz_elegida, ""), codigo)
        candidata = self.sintetizador.voz_para_idioma(codigo)
        if propia >= parecido(idiomas.get(candidata, ""), codigo):
            self._poner_voz(self._voz_elegida)
            return
        self._poner_voz(candidata or self._voz_elegida)

    def _poner_voz(self, nombre: str) -> None:
        """Cambia la voz solo si hace falta, y le devuelve sus ajustes.

        SAPI no garantiza que la velocidad y el volumen sobrevivan al cambio de
        voz, y una frase suelta leída al doble de velocidad se pierde entera.
        """
        if not nombre or nombre == self._voz_puesta:
            return
        if not self.sintetizador.elegir_voz(nombre):
            return
        self._voz_puesta = nombre
        configuracion = self._configuracion()
        self.sintetizador.establecer_velocidad(
            sapi_desde_porcentaje(int(configuracion.obtener("voz_rapidez", RAPIDEZ_NORMAL))))
        self.sintetizador.establecer_volumen(int(configuracion.obtener("voz_volumen", 100)))

    def _descripciones_en(self, inicio: int, fin: int) -> str:
        """Descripciones guardadas de las imágenes que caen en un tramo.

        En el texto una ilustración es solo ``[Imagen: Logo]``, un rótulo que
        no cuenta nada.  Con esta opción activada, al llegar ahí la lectura
        continúa con la descripción que se hizo en su día con inteligencia
        artificial, de modo que escuchar el libro incluye ver sus imágenes.

        Devuelve la cadena vacía si la opción está desactivada, si no hay
        ninguna imagen en el tramo o si ninguna tiene descripción guardada.
        """
        if not self._configuracion().obtener("voz_leer_descripciones", False):
            return ""
        documento = self.ventana.documento
        if documento is None:
            return ""
        partes = []
        for tipo in (TipoMarca.IMAGEN, TipoMarca.FIGURA):
            grupo = documento.marcas.grupo(tipo)
            indice = grupo.indice_siguiente(inicio - 1)
            while indice != -1 and indice < len(grupo):
                marca = grupo[indice]
                if marca.posicion >= fin:
                    break
                guardada = self.ventana.descripciones.obtener(marca.referencia or "")
                if guardada is not None and guardada.texto.strip():
                    partes.append(guardada.texto.strip())
                indice += 1
        if not partes:
            return ""
        return _(" Descripción de la imagen. ") + " ".join(partes)

    def _al_latir(self, evento) -> None:
        """Pasa a la frase siguiente en cuanto la voz termina la actual.

        Solo se da una frase por terminada cuando se la ha visto sonar, o
        cuando ha pasado el :data:`MARGEN_ARRANQUE` sin que empezara.  Sin esa
        condición, el latido inmediatamente posterior a lanzar una frase la
        encontraba todavía «callada» y la adelantaba.
        """
        if not self._leyendo or self.sintetizador.pausada:
            return
        if self.sintetizador.hablando:
            self._ha_sonado = True
            return
        if not self._ha_sonado:
            esperando = time.monotonic() - self._lanzada_en
            if esperando < self._margen_de_arranque():
                self._avisar_de_la_espera(esperando)
                return
        if not self._decir_desde(self.frase[1], continuacion=True):
            self.detener()
            self.ventana.anunciar(_("Fin del libro."), inmediato=True)

    def _margen_de_arranque(self) -> float:
        """Cuánto se espera a que esta voz empiece a sonar, en segundos.

        Lo dice el motor: la voz de Windows arranca en décimas y una neuronal
        puede tardar segundos. Con un margen fijo, o se saltan las frases de las
        lentas o se espera de más en las rápidas cada vez que una frase acaba.
        """
        declarada = getattr(self.sintetizador, "espera_maxima", None)
        if declarada is None:
            return MARGEN_ARRANQUE
        try:
            return max(MARGEN_ARRANQUE, min(MARGEN_ARRANQUE_MAXIMO,
                                            float(declarada)))
        except (TypeError, ValueError):
            return MARGEN_ARRANQUE

    def _avisar_de_la_espera(self, esperando: float) -> None:
        """Hace saber que la voz se está preparando, sin cansar.

        Primero un pulso corto cada segundo y pico —dice «sigo aquí» sin
        interrumpir— y, si la espera se alarga, una frase por el lector de
        pantalla. La frase se dice **una sola vez** por frase leída: repetirla
        cada dos segundos taparía justo la voz que se está esperando.
        """
        if esperando < ESPERA_PARA_AVISAR:
            return
        ahora = time.monotonic()
        if ahora - self._ultimo_pulso >= ESPERA_ENTRE_PULSOS:
            self._ultimo_pulso = ahora
            try:
                self.ventana.sonidos.reproducir("esperando")
            except Exception as error:
                log.debug("Al avisar de la espera: %s", error)
        if not self._espera_dicha and esperando >= ESPERA_PARA_DECIRLO:
            self._espera_dicha = True
            self.ventana.anunciar(_("Preparando la voz..."))

    def _llevar_cursor(self, al_parar: bool = False, lectura: bool = False) -> None:
        """Coloca el cursor en la frase que se está diciendo.

        Mientras la lectura sigue, el cursor va **al principio** de la frase:
        es lo que hace que la línea braille y el resaltado enseñen lo que suena.

        Al pausar o al detener hay dos costumbres distintas y ninguna es la
        buena para todo el mundo, así que se elige en las opciones de la voz:

        * *Al principio de la frase* —lo de siempre— es lo que conviene cuando
          se para porque algo no se ha entendido: la flecha arriba vuelve a
          leer justo eso.
        * *Detrás de la frase* es lo que conviene cuando se para para seguir a
          mano: las flechas continúan por lo que aún no ha sonado en vez de
          repetir el párrafo que se acaba de oír.

        :param al_parar: Si la lectura se está deteniendo o pausando, que es
                         cuando manda el ajuste; en marcha, el cursor va
                         siempre al principio de la frase.
        """
        if self.ventana.documento is None:
            return
        destino = self.frase[0]
        if al_parar and str(self._configuracion().obtener(
                "voz_cursor_al_parar", "inicio")) == "fin":
            destino = max(self.frase[0], self.frase[1])
        self._cursor_puesto = destino
        self.ventana.lector.ir_a(destino, mover_foco=False, lectura=lectura)

    def _mover_cursor_una_frase(self, adelante: bool) -> None:
        """Mueve el cursor una frase, sin leer nada."""
        if self.ventana.documento is None:
            return
        texto = self._texto()
        actual = self.ventana.lector.posicion()
        if adelante:
            _inicio, fin = segmentador.siguiente_frase(texto, actual)
            destino, _ = segmentador.siguiente_frase(texto, fin)
        else:
            destino, _ = segmentador.frase_anterior(texto, actual)
        self.ventana.lector.ir_a(destino)
