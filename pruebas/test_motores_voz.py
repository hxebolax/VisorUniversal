# -*- coding: utf-8 -*-
"""Pruebas del sistema de motores de voz y de sus paquetes.

Lo que hay que garantizar aquí no es que un motor suene bien —eso se comprueba
escuchándolo— sino tres cosas que sí se pueden comprobar solas y que, si fallan,
dejan a alguien sin poder leer:

1. **Que el programa nunca se quede mudo.** Pase lo que pase con un motor
   añadido, tiene que volver la voz de Windows y decirse por qué. Un lector de
   libros que se calla sin explicación no se distingue de uno colgado.
2. **Que un paquete no pueda hacer daño al instalarse.** Trae código y archivos,
   y hay trucos viejos —nombres con «..», ZIP que se hinchan— que se rechazan
   antes de tocar el disco.
3. **Que el contrato se cumpla de verdad.** No que lo diga el manifiesto, que lo
   escribe quien hace el paquete y puede estar equivocado de buena fe.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from nucleo import motores_voz, paquetes_voz

RAIZ = Path(__file__).resolve().parent.parent
PAQUETES = RAIZ / "plugins_voz"


# ---------------------------------------------------------------------------
# El contrato
# ---------------------------------------------------------------------------


class PruebaContrato:
    """Qué tiene que saber hacer una voz para poder leer un libro."""

    def test_la_voz_de_windows_lo_cumple(self):
        """Y no es una casualidad: el contrato **es** lo que ella sabe hacer.

        Se escribió copiando lo que el lector en voz alta ya le pedía al
        sintetizador de siempre. Por eso admitir motores nuevos no obligó a
        cambiar ni una línea de la lectura, y por eso esta prueba tiene que
        pasar sin que nadie haya tocado `voz.py`.
        """
        from nucleo.voz import Sintetizador

        assert motores_voz.comprobar_contrato(Sintetizador()) == []

    def test_se_comprueba_lo_que_hay_y_no_lo_que_se_promete(self):
        """Un manifiesto lo escribe quien hace el paquete y puede equivocarse."""

        class MediaVoz:
            def voces(self):
                return []

        falta = motores_voz.comprobar_contrato(MediaVoz())

        assert "decir" in falta and "hablando" in falta
        assert "voces" not in falta

    def test_la_voz_de_windows_no_se_puede_quitar(self):
        """Es la que queda cuando cualquier otra falla."""
        with pytest.raises(paquetes_voz.ErrorPaquete):
            paquetes_voz.quitar(motores_voz.SAPI5)

    def test_un_motor_que_no_esta_devuelve_la_de_windows_y_lo_dice(self):
        """Callarse sería lo peor: no se distingue de un programa colgado."""
        from nucleo.voz import Sintetizador

        motor, aviso = motores_voz.crear("uno_que_no_existe")

        assert isinstance(motor, Sintetizador)
        assert aviso and "uno_que_no_existe" in aviso

    def test_sapi5_es_siempre_el_primero_del_catalogo(self):
        catalogo = motores_voz.catalogo()

        assert catalogo[0].identificador == motores_voz.SAPI5
        assert catalogo[0].propio


# ---------------------------------------------------------------------------
# Los ajustes que declara un motor
# ---------------------------------------------------------------------------


class PruebaAjustes:
    """Lo que un motor deja tocar lo declara él, no el programa."""

    def test_un_ajuste_sin_explicacion_se_rechaza(self):
        """No es una formalidad.

        En este programa cada control se explica con Control+F1. Un ajuste que
        llega sin su explicación dejaría un hueco justo donde alguien que no ve
        iría a preguntar qué es, y eso no se puede arreglar después: la
        explicación la tiene que escribir quien hizo el motor.
        """
        with pytest.raises(ValueError, match="explicación"):
            motores_voz.Ajuste.desde_json(
                {"clave": "tono", "clase": "deslizador", "etiqueta": "Tono:"})

    def test_una_lista_sin_opciones_se_rechaza(self):
        with pytest.raises(ValueError, match="opciones"):
            motores_voz.Ajuste.desde_json(
                {"clave": "idioma", "clase": "lista", "etiqueta": "Idioma:",
                 "ayuda": "El idioma."})

    def test_una_clase_desconocida_se_rechaza(self):
        with pytest.raises(ValueError, match="clase"):
            motores_voz.Ajuste.desde_json(
                {"clave": "x", "clase": "ruleta", "etiqueta": "X:",
                 "ayuda": "Algo."})

    def test_un_valor_fuera_de_rango_vuelve_al_de_fabrica(self):
        """La configuración es un archivo de texto que alguien puede editar."""
        ajuste = motores_voz.Ajuste.desde_json(
            {"clave": "tono", "clase": "deslizador", "etiqueta": "Tono:",
             "ayuda": "El tono.", "minimo": 0, "maximo": 100, "defecto": 50})

        assert ajuste.valor_valido(300) == 100
        assert ajuste.valor_valido(-5) == 0
        assert ajuste.valor_valido("no es un número") == 50

    def test_una_opcion_que_ya_no_existe_vuelve_a_la_de_fabrica(self):
        """Un motor puede haberse actualizado y haber quitado una voz."""
        ajuste = motores_voz.Ajuste.desde_json(
            {"clave": "idioma", "clase": "lista", "etiqueta": "Idioma:",
             "ayuda": "El idioma.", "defecto": "esp",
             "opciones": [{"valor": "esp", "texto": "Español"},
                          {"valor": "eng", "texto": "Inglés"}]})

        assert ajuste.valor_valido("klingon") == "esp"
        assert ajuste.valor_valido("eng") == "eng"


# ---------------------------------------------------------------------------
# Instalar un paquete
# ---------------------------------------------------------------------------


def _paquete_de_prueba(carpeta: Path, nombres: dict, manifiesto=None) -> Path:
    """Arma un paquete a medida para probar una pega concreta."""
    salida = carpeta / "prueba.motorvoz"
    with zipfile.ZipFile(salida, "w") as paquete:
        if manifiesto is not None:
            paquete.writestr(motores_voz.MANIFIESTO,
                             json.dumps(manifiesto, ensure_ascii=False))
        for nombre, contenido in nombres.items():
            paquete.writestr(nombre, contenido)
    return salida


MANIFIESTO_MINIMO = {
    "id": "prueba", "nombre": "Motor de prueba", "contrato": 1,
    "modulo": "motor", "version": "1.0",
}


class PruebaInstalacion:
    """Un paquete trae código que se va a ejecutar: se mira antes de tocarlo."""

    def test_un_archivo_que_no_es_un_paquete_se_dice_claro(self, tmp_path):
        cualquiera = tmp_path / "foto.jpg"
        cualquiera.write_bytes(b"no soy un zip")

        with pytest.raises(paquetes_voz.ErrorPaquete) as fallo:
            paquetes_voz.examinar(cualquiera)

        assert "no es un paquete" in str(fallo.value).lower()

    def test_un_zip_sin_manifiesto_se_rechaza(self, tmp_path):
        ruta = _paquete_de_prueba(tmp_path, {"cosas.txt": "hola"})

        with pytest.raises(paquetes_voz.ErrorPaquete) as fallo:
            paquetes_voz.examinar(ruta)

        assert "motor.json" in str(fallo.value)

    def test_un_paquete_que_escribe_fuera_de_su_carpeta_se_rechaza(self, tmp_path):
        """Es el truco de toda la vida, y la respuesta es igual de vieja.

        Un nombre con «..» dentro del ZIP escribiría donde le pareciera. Se mira
        **antes** de descomprimir nada, que es lo único que sirve: después ya
        está escrito.
        """
        ruta = _paquete_de_prueba(
            tmp_path, {"../../fuera.txt": "no debería estar aquí",
                       "motor.py": "def crear(c, a): pass"},
            MANIFIESTO_MINIMO)

        with pytest.raises(paquetes_voz.ErrorPaquete) as fallo:
            paquetes_voz.examinar(ruta)

        assert "fuera de su carpeta" in str(fallo.value)

    def test_un_paquete_para_otra_version_se_rechaza(self, tmp_path):
        manifiesto = dict(MANIFIESTO_MINIMO, contrato=99)
        ruta = _paquete_de_prueba(tmp_path, {"motor.py": ""}, manifiesto)

        with pytest.raises(paquetes_voz.ErrorPaquete) as fallo:
            paquetes_voz.examinar(ruta)

        assert "otra versión" in str(fallo.value)

    def test_un_paquete_que_quiere_ser_la_voz_de_windows_se_rechaza(self, tmp_path):
        manifiesto = dict(MANIFIESTO_MINIMO, id=motores_voz.SAPI5)
        ruta = _paquete_de_prueba(tmp_path, {"motor.py": ""}, manifiesto)

        with pytest.raises(paquetes_voz.ErrorPaquete) as fallo:
            paquetes_voz.examinar(ruta)

        assert "Windows" in str(fallo.value)

    def test_la_ficha_dice_qué_es_antes_de_instalar_nada(self, tmp_path):
        """Quien instala tiene derecho a saber qué acepta.

        La ficha se saca leyendo dentro del ZIP, **sin descomprimir al disco**:
        es lo que permite enseñarla y que la respuesta sea «no, gracias».
        """
        manifiesto = dict(MANIFIESTO_MINIMO, autor="Alguien",
                          origen="De algún sitio", licencia="Libre",
                          descripcion="Una voz de prueba.")
        ruta = _paquete_de_prueba(tmp_path, {"motor.py": "x = 1"}, manifiesto)

        ficha = paquetes_voz.examinar(ruta)
        resumen = ficha.resumen()

        assert ficha.identificador == "prueba"
        assert "Alguien" in resumen and "Libre" in resumen
        assert "De algún sitio" in resumen
        # Y cuánto ocupa, que es lo que decide si cabe en el equipo.
        assert "MB" in resumen


# ---------------------------------------------------------------------------
# Los paquetes que vienen con el programa
# ---------------------------------------------------------------------------


def _los_que_hay():
    return sorted(PAQUETES.glob("*" + paquetes_voz.EXTENSION))


@pytest.mark.lenta
class PruebaPaquetesDelPrograma:
    """Los cuatro paquetes de ``plugins_voz``, tal como se reparten.

    No se comprueba que hablen —eso pide altavoces y unos segundos por motor—
    sino que están **bien armados**: que se dejan examinar, que traen lo que
    dicen, que van compilados y que cada uno lleva sus archivos con su nombre.
    """

    def test_hay_paquetes_y_todos_se_dejan_examinar(self):
        paquetes = _los_que_hay()
        if not paquetes:
            pytest.skip("no hay paquetes armados; se arman con "
                        "plugins_voz/crear_paquetes.py")

        for ruta in paquetes:
            ficha = paquetes_voz.examinar(ruta)
            assert ficha.nombre and ficha.identificador
            # Sin esto, quien lo instale no sabe qué está aceptando.
            assert ficha.descripcion, ruta.name
            assert ficha.licencia, ruta.name
            assert ficha.origen, ruta.name

    def test_van_compilados_y_sin_codigo_fuente(self):
        """Un paquete que se reparte lleva bytecode, no fuente."""
        paquetes = _los_que_hay()
        if not paquetes:
            pytest.skip("no hay paquetes armados")

        for ruta in paquetes:
            with zipfile.ZipFile(ruta) as paquete:
                nombres = paquete.namelist()
            assert not [uno for uno in nombres if uno.endswith(".py")], ruta.name
            assert [uno for uno in nombres if uno.endswith(".pyc")], ruta.name

    def test_cada_motor_lleva_sus_archivos_con_su_nombre(self):
        """Dos paquetes instalados a la vez no pueden tener módulos homónimos.

        Si los tuvieran, el segundo en cargarse taparía al primero y las voces
        de uno saldrían con el nombre del otro: la clase de fallo que parece
        funcionar.
        """
        paquetes = _los_que_hay()
        if len(paquetes) < 2:
            pytest.skip("hacen falta dos paquetes para que puedan chocar")

        vistos: dict = {}
        for ruta in paquetes:
            with zipfile.ZipFile(ruta) as paquete:
                modulos = {uno for uno in paquete.namelist()
                           if uno.endswith(".pyc") and "/" not in uno}
            choques = modulos & set(vistos)
            assert not choques, "%s choca con %s en %s" % (
                ruta.name, [vistos[uno] for uno in choques], choques)
            for uno in modulos:
                vistos[uno] = ruta.name

    def test_dicen_para_que_version_de_python_estan_compilados(self):
        """El bytecode va atado a la versión, y hay que poder avisar antes."""
        paquetes = _los_que_hay()
        if not paquetes:
            pytest.skip("no hay paquetes armados")

        for ruta in paquetes:
            with zipfile.ZipFile(ruta) as paquete:
                datos = json.loads(paquete.read(motores_voz.MANIFIESTO))
            assert datos.get("python"), ruta.name
            assert motores_voz._mismo_python(datos["python"]), ruta.name

    def test_todos_sus_ajustes_traen_su_explicacion(self):
        """La regla del programa vale también para lo que llega en un paquete."""
        paquetes = _los_que_hay()
        if not paquetes:
            pytest.skip("no hay paquetes armados")

        for ruta in paquetes:
            with zipfile.ZipFile(ruta) as paquete:
                datos = json.loads(paquete.read(motores_voz.MANIFIESTO))
            for ajuste in datos.get("ajustes", []):
                # Se construye con el mismo código que los lee al instalar: si
                # alguno no trae explicación, esto lanza excepción.
                leido = motores_voz.Ajuste.desde_json(ajuste)
                assert len(leido.ayuda) > 40, (ruta.name, leido.clave)


#: Un motor de mentira que cumple lo mínimo: tener una función «crear».
CREAR_VACIO = "def crear(carpeta, ajustes):\n    return object()\n"


class PruebaInstalarYQuitar:
    """El viaje entero: instalar, verlo en la lista y quitarlo."""

    def test_instalar_y_quitar_deja_todo_como_estaba(self, tmp_path, monkeypatch):
        carpeta = tmp_path / "motores"
        monkeypatch.setattr(motores_voz, "carpeta_de_motores", lambda: carpeta)
        carpeta.mkdir()
        manifiesto = dict(MANIFIESTO_MINIMO, descripcion="Prueba")
        ruta = _paquete_de_prueba(
            tmp_path,
            {"motor.py": "def crear(carpeta, ajustes):\n    return object()\n"},
            manifiesto)

        motor = paquetes_voz.instalar(ruta)
        assert motor.identificador == "prueba"
        assert (carpeta / "prueba" / "motor.py").is_file()
        assert "prueba" in [uno.identificador for uno in motores_voz.instalados()]

        assert paquetes_voz.quitar("prueba") is True
        assert "prueba" not in [uno.identificador for uno in motores_voz.instalados()]

    def test_al_reinstalar_no_se_pierde_lo_que_el_motor_haya_bajado(
            self, tmp_path, monkeypatch):
        """Actualizar un motor no puede tirar los idiomas que alguien bajó.

        Tres de los motores dejan bajar voces de otros idiomas, y bajarlas todas
        son cientos de megas. Reinstalar el paquete —cambiarlo por una versión
        nueva, que es lo normal— borraba la carpeta entera y se los llevaba por
        delante sin decir nada.
        """
        carpeta = tmp_path / "motores"
        monkeypatch.setattr(motores_voz, "carpeta_de_motores", lambda: carpeta)
        carpeta.mkdir()
        manifiesto = dict(MANIFIESTO_MINIMO, conservar=["voces"])
        ruta = _paquete_de_prueba(
            tmp_path,
            {"motor.py": CREAR_VACIO,
             "voces/la_que_viene.dat": "la del paquete"},
            manifiesto)

        paquetes_voz.instalar(ruta)
        bajadas = carpeta / "prueba" / "voces"
        (bajadas / "la_que_baje_yo.dat").write_text("bajada", encoding="utf-8")

        paquetes_voz.instalar(ruta)
        assert (bajadas / "la_que_baje_yo.dat").is_file()
        # Y la del paquete sigue siendo la del paquete: si una versión nueva
        # corrige una voz, la corregida es la que queda.
        assert (bajadas / "la_que_viene.dat").read_text(
            encoding="utf-8") == "la del paquete"

    def test_lo_que_se_conserva_no_puede_salir_de_la_carpeta(
            self, tmp_path, monkeypatch):
        """Un manifiesto no puede pedir que se conserve media unidad de disco.

        Lo declara quien hace el paquete, así que aquí vale lo mismo que con los
        nombres de archivo del ZIP: se mira, y lo que apunte fuera se ignora.
        """
        carpeta = tmp_path / "motores"
        monkeypatch.setattr(motores_voz, "carpeta_de_motores", lambda: carpeta)
        carpeta.mkdir()
        manifiesto = dict(MANIFIESTO_MINIMO,
                          conservar=["../../otra_cosa", "/absoluta", ""])
        ruta = _paquete_de_prueba(
            tmp_path,
            {"motor.py": CREAR_VACIO},
            manifiesto)

        fuera = tmp_path / "otra_cosa"
        fuera.mkdir()
        (fuera / "secreto.txt").write_text("no es suyo", encoding="utf-8")

        paquetes_voz.instalar(ruta)
        paquetes_voz.instalar(ruta)
        assert not (carpeta / "prueba" / "otra_cosa").exists()
        assert (fuera / "secreto.txt").is_file()

    def test_un_motor_que_no_cumple_el_contrato_no_se_usa(self, tmp_path, monkeypatch):
        """Se carga, se mira lo que trae y se rechaza. Sin quedarse mudo."""
        from nucleo.voz import Sintetizador

        carpeta = tmp_path / "motores"
        monkeypatch.setattr(motores_voz, "carpeta_de_motores", lambda: carpeta)
        carpeta.mkdir()
        ruta = _paquete_de_prueba(
            tmp_path,
            {"motor.py": "def crear(carpeta, ajustes):\n    return object()\n"},
            dict(MANIFIESTO_MINIMO))
        paquetes_voz.instalar(ruta)

        motor, aviso = motores_voz.crear("prueba")

        assert isinstance(motor, Sintetizador)
        assert "compatible" in aviso

    def test_un_motor_que_revienta_al_arrancar_no_tumba_la_lectura(
            self, tmp_path, monkeypatch):
        from nucleo.voz import Sintetizador

        carpeta = tmp_path / "motores"
        monkeypatch.setattr(motores_voz, "carpeta_de_motores", lambda: carpeta)
        carpeta.mkdir()
        ruta = _paquete_de_prueba(
            tmp_path,
            {"motor.py": "def crear(carpeta, ajustes):\n"
                         "    raise RuntimeError('me falta una biblioteca')\n"},
            dict(MANIFIESTO_MINIMO))
        paquetes_voz.instalar(ruta)

        motor, aviso = motores_voz.crear("prueba")

        assert isinstance(motor, Sintetizador)
        assert "biblioteca" in aviso

    def test_un_motor_roto_no_esconde_a_los_demas(self, tmp_path, monkeypatch):
        """Quien tenga tres instalados y uno estropeado usa los otros dos.

        Y, sobre todo, puede entrar a quitar el que falla: si un manifiesto
        ilegible tumbara la lista entera, no habría manera de llegar a él.
        """
        carpeta = tmp_path / "motores"
        monkeypatch.setattr(motores_voz, "carpeta_de_motores", lambda: carpeta)
        (carpeta / "roto").mkdir(parents=True)
        (carpeta / "roto" / motores_voz.MANIFIESTO).write_text(
            "esto no es json", encoding="utf-8")
        (carpeta / "bueno").mkdir()
        (carpeta / "bueno" / motores_voz.MANIFIESTO).write_text(
            json.dumps(dict(MANIFIESTO_MINIMO, id="bueno")), encoding="utf-8")
        (carpeta / "bueno" / "motor.py").write_text("", encoding="utf-8")

        instalados = motores_voz.instalados()

        assert [uno.identificador for uno in instalados] == ["bueno"]

    def test_los_restos_de_una_instalacion_a_medias_se_limpian(
            self, tmp_path, monkeypatch):
        """Un motor con una biblioteca cargada no se deja borrar del todo.

        Windows no borra un archivo en uso, así que queda para el arranque
        siguiente, que es cuando ya no lo está.
        """
        carpeta = tmp_path / "motores"
        monkeypatch.setattr(motores_voz, "carpeta_de_motores", lambda: carpeta)
        (carpeta / "_instalando_x").mkdir(parents=True)
        (carpeta / "_anterior_y").mkdir()
        (carpeta / "z").mkdir()
        (carpeta / "z" / ".borrar").write_text("", encoding="utf-8")

        cuantos = paquetes_voz.limpiar_restos()

        assert cuantos == 3
        assert not list(carpeta.iterdir())


# ---------------------------------------------------------------------------
# El idioma de una voz
# ---------------------------------------------------------------------------


class PruebaIdiomaDeLasVoces:
    """Windows no dice «español»: dice un número, y hay más de uno por idioma.

    De acertar esto depende que un libro con una cita en inglés se lea con voz
    inglesa, y que un documento en español de España no acabe leído con acento
    mexicano teniendo voz española instalada.
    """

    def test_el_espanol_moderno_de_windows_trae_su_pais(self):
        """Windows tiene **dos** números para el español de España.

        El antiguo, ``40a``, y el que llevan las voces modernas —Helena, Laura,
        Pablo—, que es ``c0a``. Con solo el primero en la tabla, esas tres
        salían como «español» a secas: seguían leyendo, en español, y el
        programa podía preferirles una voz de otro país que sí llevara el suyo
        escrito. No falla nada y suena distinto sin motivo aparente.
        """
        from nucleo.voz import idioma_de_lcid

        assert idioma_de_lcid("40a") == "es-ES"
        assert idioma_de_lcid("c0a") == "es-ES"

    def test_los_paises_de_habla_hispana_se_distinguen(self):
        from nucleo.voz import idioma_de_lcid

        assert idioma_de_lcid("80a") == "es-MX"
        assert idioma_de_lcid("2c0a") == "es-AR"
        assert idioma_de_lcid("340a") == "es-CL"
        assert idioma_de_lcid("540a") == "es-US"

    def test_una_voz_espanola_moderna_gana_a_una_de_otro_pais(self):
        """Es lo que la tabla decide de verdad."""
        from nucleo.voz import idioma_de_lcid, parecido

        moderna = idioma_de_lcid("c0a")
        mexicana = idioma_de_lcid("80a")

        assert parecido(moderna, "es-ES") == 2
        assert parecido(mexicana, "es-ES") == 1

    def test_un_identificador_que_no_se_conoce_no_revienta(self):
        """Se devuelve lo que se sepa, aunque sea nada: la lectura sigue."""
        from nucleo.voz import idioma_de_lcid

        assert idioma_de_lcid("") == ""
        assert idioma_de_lcid("no es un número") == ""
        # Una lengua conocida con una región que no está en la tabla se queda
        # sin país, que es mejor que descartarla.
        assert idioma_de_lcid("100a") in ("es", "es-GT")


class PruebaUnMotorQueNoPuedeHablar:
    """Arrancar y no poder sonar es un caso real, no una rareza.

    A las voces neuronales les puede faltar la clave con la que se abren sus
    modelos: se listan, se eligen, y no sale sonido. Antes de esto, pulsar
    «Probar» en ese caso no hacía nada de nada —ni sonido ni aviso— y no había
    forma de saber qué faltaba.
    """

    def test_problema_es_opcional_y_esta_declarado(self):
        """Está en la lista de lo opcional, así que se puede tener o no."""
        from nucleo import motores_voz

        assert "problema" in motores_voz.OPCIONALES
        # Y no en el contrato: un motor que siempre suena no tiene que tenerlo.
        assert "problema" not in motores_voz.CONTRATO

    def test_un_motor_sin_problema_sigue_cumpliendo_el_contrato(self):
        """Lo opcional no puede volverse obligatorio por la puerta de atrás."""
        from nucleo import motores_voz

        class Mudo:
            disponible = True
            pausada = False
            hablando = False

            def __getattr__(self, nombre):
                if nombre in motores_voz.CONTRATO:
                    return lambda *a, **k: None
                raise AttributeError(nombre)

        assert motores_voz.comprobar_contrato(Mudo()) == []
        assert not hasattr(Mudo(), "problema")


class PruebaBibliotecasQueSePrecargan:
    """Un paquete puede pedir que sus bibliotecas entren en el proceso pronto.

    Windows le da a quien pide una biblioteca por su nombre la primera que ya
    esté cargada con ese nombre, venga de donde venga. Si otro programa del
    equipo tiene una copia más vieja y entra antes, el motor usa la suya y,
    cuando las versiones no casan, se lleva el proceso entero. Llegar antes lo
    arregla, y por eso el manifiesto puede pedirlo.
    """

    def test_el_manifiesto_puede_pedir_precargas(self, tmp_path):
        from nucleo import motores_voz

        carpeta = tmp_path / "uno"
        carpeta.mkdir()
        (carpeta / "motor_uno.py").write_text("", encoding="utf-8")
        (carpeta / "motor.json").write_text(json.dumps({
            "id": "uno", "nombre": "Uno", "modulo": "motor_uno", "contrato": 1,
            "precargar": ["libs/una.dll", "libs/otra.dll"],
        }), encoding="utf-8")

        motor = motores_voz.leer_manifiesto(carpeta)

        assert motor.precargar == ("libs/una.dll", "libs/otra.dll")

    def test_no_se_admite_salirse_de_la_carpeta(self, tmp_path):
        """Esto se ejecuta al arrancar, antes que nada: no puede cargar de fuera."""
        from nucleo import motores_voz

        carpeta = tmp_path / "dos"
        carpeta.mkdir()
        (carpeta / "motor_dos.py").write_text("", encoding="utf-8")
        (carpeta / "motor.json").write_text(json.dumps({
            "id": "dos", "nombre": "Dos", "modulo": "motor_dos", "contrato": 1,
            "precargar": ["../fuera.dll", "/absoluta.dll", "..\\otra.dll",
                          "buena.dll"],
        }), encoding="utf-8")

        motor = motores_voz.leer_manifiesto(carpeta)

        assert motor.precargar == ("buena.dll",)

    def test_un_motor_sin_precargas_no_pide_nada(self, tmp_path):
        from nucleo import motores_voz

        carpeta = tmp_path / "tres"
        carpeta.mkdir()
        (carpeta / "motor_tres.py").write_text("", encoding="utf-8")
        (carpeta / "motor.json").write_text(json.dumps({
            "id": "tres", "nombre": "Tres", "modulo": "motor_tres", "contrato": 1,
        }), encoding="utf-8")

        assert motores_voz.leer_manifiesto(carpeta).precargar == ()
