@echo off
setlocal EnableDelayedExpansion
title Visor Universal - Herramientas

rem ===========================================================================
rem  Visor Universal - archivo de tareas
rem
rem  Este archivo hace todo lo necesario para trabajar con el programa:
rem    1. Elegir con que Python se crea el entorno virtual e instalarlo todo.
rem    2. Ejecutar el programa desde el codigo fuente.
rem    3. Compilarlo con cx_Freeze en un ejecutable independiente.
rem
rem  El entorno virtual se crea en la carpeta "entorno", dentro del proyecto.
rem  A partir de ese momento TODO (ejecutar, compilar, comprobar) usa el
rem  Python de ese entorno, nunca el del sistema.
rem
rem  IMPORTANTE PARA QUIEN EDITE ESTE ARCHIVO: debe guardarse con saltos de
rem  linea de Windows (CRLF).  Con saltos de linea de Unix (LF), cmd.exe
rem  pierde la cuenta de las posiciones dentro del archivo y falla al buscar
rem  etiquetas, con el error "no encuentra la etiqueta por lotes".
rem ===========================================================================

set "RAIZ=%~dp0"
cd /d "%RAIZ%"
set "ENTORNO=%RAIZ%entorno"
set "PYENV=%ENTORNO%\Scripts\python.exe"
set "SALIDA=%RAIZ%build\VisorUniversal"
set "FICHA=%ENTORNO%\python_usado.txt"
set "DETECTOR=%RAIZ%herramientas\detectar_python.py"

:menu
cls
set "INFO=(sin datos)"
if exist "%FICHA%" set /p INFO=<"%FICHA%"
echo ===========================================================================
echo                    VISOR UNIVERSAL - Herramientas
echo ===========================================================================
echo.
if exist "%PYENV%" (
    echo   Entorno virtual: INSTALADO
    echo   Creado con .... !INFO!
    echo   Carpeta ....... %ENTORNO%
) else (
    echo   Entorno virtual: NO INSTALADO   ^(empieza por la opcion 1^)
)
echo.
echo   1. Crear el entorno virtual ^(eliges la version de Python^)
echo   2. Ejecutar el programa desde el codigo fuente
echo   3. Compilar el ejecutable con cx_Freeze
echo   4. Abrir la carpeta del ejecutable compilado
echo   5. Reinstalar o actualizar los requisitos
echo   6. Limpiar ^(borra build, cache y archivos temporales^)
echo   7. Comprobar la instalacion
echo   8. Eliminar el entorno virtual
echo   9. Preparar el paquete de actualizacion ^(zip firmado + version.json^)
echo   T. Traducir el programa a otros idiomas ^(editor accesible^)
echo   F. Firma de las actualizaciones ^(ver estado y clave^)
echo   P. Ejecutar la bateria de pruebas ^(pytest^)
echo   0. Salir
echo.
set "OPCION="
set /p OPCION=Elige una opcion y pulsa Intro:

if "%OPCION%"=="1" goto instalar
if "%OPCION%"=="2" goto ejecutar
if "%OPCION%"=="3" goto compilar
if "%OPCION%"=="4" goto abrir
if "%OPCION%"=="5" goto actualizar
if "%OPCION%"=="6" goto limpiar
if "%OPCION%"=="7" goto comprobar
if "%OPCION%"=="8" goto borrar_entorno
if "%OPCION%"=="9" goto empaquetar
if /i "%OPCION%"=="T" goto idiomas
if /i "%OPCION%"=="P" goto pruebas
if /i "%OPCION%"=="F" goto firma
if "%OPCION%"=="0" goto fin
goto menu

rem ---------------------------------------------------------------------------
rem  Opcion 1: elegir el Python y crear el entorno virtual
rem ---------------------------------------------------------------------------
:instalar
cls
echo === Crear el entorno virtual ===
echo.

rem Se necesita un Python cualquiera del sistema solo para ejecutar el
rem detector; el que se use luego lo elige el usuario en la lista.
set "PYARRANQUE="
where py >nul 2>nul && set "PYARRANQUE=py"
if not defined PYARRANQUE (
    where python >nul 2>nul && set "PYARRANQUE=python"
)
if not defined PYARRANQUE (
    echo ERROR: no se ha encontrado ningun Python en este equipo.
    echo.
    echo Descargalo de https://www.python.org/downloads/ y marca la casilla
    echo "Add Python to PATH" durante la instalacion.
    goto pausa
)

echo Buscando las versiones de Python instaladas...
echo.
set "TOTAL=0"
set "OMITIDAS=0"
for /f "usebackq tokens=1,2,3* delims=|" %%A in (`%PYARRANQUE% "%DETECTOR%" 2^>nul`) do (
    if "%%C"=="no" (
        rem Compilaciones sin GIL: wxPython no publica paquetes para ellas,
        rem asi que no se ofrecen para evitar que el entorno nazca inservible.
        set /a OMITIDAS+=1
    ) else (
        set /a TOTAL+=1
        set "VER_!TOTAL!=%%A"
        set "ETI_!TOTAL!=%%B"
        set "APTO_!TOTAL!=%%C"
        set "RUTA_!TOTAL!=%%D"
        if "%%C"=="nueva" (
            echo    !TOTAL!. Python %%A  ^(%%B^)  -- muy reciente, puede que wxPython aun no la admita
        ) else (
            echo    !TOTAL!. Python %%A  ^(%%B^)
        )
        echo        %%D
    )
)
if "%TOTAL%"=="0" (
    echo No se ha encontrado ninguna version de Python que sirva.
    if not "%OMITIDAS%"=="0" (
        echo Se han omitido %OMITIDAS% compilaciones "sin GIL", que wxPython no admite.
    )
    echo Instala Python desde https://www.python.org/downloads/
    goto pausa
)
echo.
echo    0. Cancelar
echo.
if not "%OMITIDAS%"=="0" (
    echo Se han omitido %OMITIDAS% compilaciones "sin GIL": wxPython no las admite.
    echo.
)
set "ELEGIDO="
set /p ELEGIDO=Con que version quieres crear el entorno (numero):
if "%ELEGIDO%"=="0" goto menu
if not defined ELEGIDO goto menu
set "PYSISTEMA=!RUTA_%ELEGIDO%!"
set "PYVERSION=!VER_%ELEGIDO%!"
set "PYETIQUETA=!ETI_%ELEGIDO%!"
set "PYAPTO=!APTO_%ELEGIDO%!"
if not defined PYSISTEMA (
    echo.
    echo Ese numero no esta en la lista.
    goto pausa
)
if not exist "!PYSISTEMA!" (
    echo.
    echo No se encuentra el archivo: !PYSISTEMA!
    goto pausa
)

echo.
echo Se usara Python !PYVERSION! ^(!PYETIQUETA!^)
echo   !PYSISTEMA!
echo.
if "!PYAPTO!"=="nueva" (
    echo AVISO: esta version es muy reciente y puede que wxPython todavia no
    echo        tenga paquete para ella. Si la instalacion falla, vuelve a la
    echo        opcion 1 y elige una version anterior.
    set "CONFIRMA="
    set /p CONFIRMA=Escribe S para continuar de todos modos:
    if /i not "!CONFIRMA!"=="S" goto menu
    echo.
)

if exist "%ENTORNO%" (
    echo Ya existe un entorno virtual. Se va a sustituir por uno nuevo.
    set "CONFIRMA="
    set /p CONFIRMA=Escribe S para continuar:
    if /i not "!CONFIRMA!"=="S" goto menu
    rmdir /s /q "%ENTORNO%"
)

echo Creando el entorno virtual...
"!PYSISTEMA!" -m venv "%ENTORNO%"
if not exist "%PYENV%" (
    echo.
    echo ERROR: no se ha podido crear el entorno virtual.
    echo Comprueba que esa version de Python incluye el modulo "venv".
    goto pausa
)

rem Se deja constancia de con que Python se creo, para mostrarlo en el menu.
> "%FICHA%" echo Python !PYVERSION! (!PYETIQUETA!) - !PYSISTEMA!

echo.
echo Actualizando pip...
"%PYENV%" -m pip install --upgrade pip --quiet
echo.
echo Instalando los requisitos. Esto puede tardar varios minutos...
echo.
"%PYENV%" -m pip install -r "%RAIZ%requirements.txt"
if errorlevel 1 (
    echo.
    echo AVISO: alguno de los requisitos no se ha podido instalar.
    echo        Imprescindibles: wxPython y lxml.
    echo        Opcionales: accessible-output2 y cx_Freeze.
    echo        Si ha fallado wxPython, prueba con otra version de Python.
)
echo.
echo === Comprobacion ===
goto comprobar_comun

rem ---------------------------------------------------------------------------
:actualizar
cls
echo === Reinstalar o actualizar los requisitos ===
if not exist "%PYENV%" (
    echo El entorno virtual no existe. Usa antes la opcion 1.
    goto pausa
)
echo.
"%PYENV%" -m pip install --upgrade -r "%RAIZ%requirements.txt"
goto pausa

rem ---------------------------------------------------------------------------
:ejecutar
cls
echo === Ejecutando el Visor Universal ===
if not exist "%PYENV%" (
    echo El entorno virtual no existe. Usa antes la opcion 1.
    goto pausa
)
echo.
echo Se usa el Python del entorno:
echo   %PYENV%
echo.
echo Se abrira la ventana del programa. Cierrala para volver a este menu.
echo Si algo falla, mira el archivo data\logs\errores.log
echo.
"%PYENV%" "%RAIZ%src\main.py"
if errorlevel 1 (
    echo.
    echo El programa ha terminado con errores. Revisa data\logs\errores.log
)
goto pausa

rem ---------------------------------------------------------------------------
:compilar
cls
echo === Compilando el ejecutable con cx_Freeze ===
if not exist "%PYENV%" (
    echo El entorno virtual no existe. Usa antes la opcion 1.
    goto pausa
)
echo.
echo Se compila con el Python del entorno:
if exist "%FICHA%" (
    set "INFO="
    set /p INFO=<"%FICHA%"
    echo   !INFO!
)
echo.
"%PYENV%" -c "import cx_Freeze" 2>nul
if errorlevel 1 (
    echo cx_Freeze no esta instalado en el entorno. Instalandolo...
    "%PYENV%" -m pip install cx_Freeze
    if errorlevel 1 (
        echo ERROR: no se ha podido instalar cx_Freeze.
        goto pausa
    )
)

"%PYENV%" -c "import cryptography" 2>nul
if errorlevel 1 (
    echo Instalando cryptography, que hace falta para firmar las actualizaciones...
    "%PYENV%" -m pip install cryptography
    if errorlevel 1 (
        echo ERROR: no se ha podido instalar cryptography.
        goto pausa
    )
)

echo.
echo Preparando la firma de las actualizaciones...
"%PYENV%" "%RAIZ%herramientas\firmar_version.py" preparar
if errorlevel 1 (
    echo.
    echo ERROR: no se ha podido preparar la firma. Revisa los mensajes de arriba.
    goto pausa
)

if exist "%SALIDA%" (
    echo Borrando la compilacion anterior...
    rmdir /s /q "%SALIDA%"
)

echo.
echo Los paquetes de motor de voz NO se incluyen: son casi un giga y quien
echo instale el programa no tiene por que bajarselos. Se reparten aparte, y
echo se instalan desde Voz, Lectura en voz alta, Motores de voz.
echo Lo que esos motores necesitan de Python si va dentro, para que uno
echo instalado despues funcione.
echo.
echo Compilando. Esto tarda un rato...
echo.
set "VISOR_SIN_PAQUETES_VOZ=1"
"%PYENV%" "%RAIZ%setup_cx.py" build
set "VISOR_SIN_PAQUETES_VOZ="
if errorlevel 1 (
    echo.
    echo ERROR: la compilacion ha fallado. Revisa los mensajes de arriba.
    goto pausa
)

echo.
echo Comprobando las bibliotecas de Visual C++ en la salida...
set "FALTANTES="
for %%D in (vcruntime140.dll vcruntime140_1.dll msvcp140.dll) do (
    if exist "%SALIDA%\%%D" (
        echo   [OK]     %%D
    ) else (
        echo   [FALTA]  %%D
        set "FALTANTES=1"
    )
)
if defined FALTANTES (
    echo.
    echo AVISO: falta alguna biblioteca de Visual C++. El programa puede no
    echo        arrancar en equipos sin el paquete redistribuible de Microsoft.
)

echo.
if exist "%SALIDA%\data\sonidos" (
    echo   [OK]     carpeta data limpia con los sonidos
) else (
    echo   [FALTA]  carpeta data
)

echo.
echo Preparando el paquete de actualizacion...
echo.
"%PYENV%" "%RAIZ%herramientas\empaquetar.py"
if errorlevel 1 (
    echo.
    echo AVISO: el ejecutable esta compilado, pero no se ha podido preparar el
    echo        paquete de actualizacion. Revisa los mensajes de arriba.
)

echo.
echo === Compilacion terminada ===
echo El ejecutable esta en:
echo   %SALIDA%\VisorUniversal.exe
echo.
echo Esta compilacion va limpia, sin los paquetes de motor de voz. Si quieres
echo probarlos en ella, copialos a mano desde la carpeta plugins_voz o
echo instalalos desde el propio programa.
goto pausa

rem ---------------------------------------------------------------------------
:firma
cls
echo === Firma de las actualizaciones ===
if not exist "%PYENV%" (
    echo El entorno virtual no existe. Usa antes la opcion 1.
    goto pausa
)
echo.
echo La firma impide que alguien que se haga con el servidor pueda colar una
echo version falsa: sin la clave PRIVADA no se puede firmar un aviso que los
echo programas ya instalados acepten.
echo.
echo No hay nada que hacer a mano: al compilar ^(opcion 3^) se crea la clave la
echo primera vez, se mete la publica en el programa y se firma el version.json.
echo.
"%PYENV%" "%RAIZ%herramientas\firmar_version.py" estado
echo.
echo -------------------------------------------------------------------------
echo IMPORTANTE: guarda una copia de la clave privada FUERA de este equipo.
echo Esta en: herramientas\claves\visor_ed25519.key
echo Sin ella no podras publicar mas actualizaciones que acepten los programas
echo que ya estan instalados.
echo -------------------------------------------------------------------------
goto pausa

rem ---------------------------------------------------------------------------
rem ---------------------------------------------------------------------------
rem  Opcion T: editor de traducciones
rem ---------------------------------------------------------------------------
:idiomas
cls
echo === Traducir el programa a otros idiomas ===
if not exist "%PYENV%" (
    echo El entorno virtual no existe. Usa antes la opcion 1.
    goto pausa
)
echo.
echo Se abrira el editor de traducciones. Con el puedes:
echo.
echo   - Crear un idioma nuevo con todos los textos del programa.
echo   - Traducirlo entero de una vez, respetando las variables y las teclas.
echo   - Corregir a mano entrada por entrada, con lector de pantalla.
echo   - Compilar los idiomas para que el programa los pueda usar.
echo.
echo Cierra la ventana del editor para volver a este menu.
echo.
"%PYENV%" "%~dp0herramientas\editor_idiomas.py"
if errorlevel 1 (
    echo.
    echo El editor ha terminado con errores. Revisa lo de arriba.
)
goto pausa

rem ---------------------------------------------------------------------------
rem  Opcion P: bateria de pruebas
rem ---------------------------------------------------------------------------
:pruebas
cls
echo === Bateria de pruebas ===
if not exist "%PYENV%" (
    echo El entorno virtual no existe. Usa antes la opcion 1.
    goto pausa
)
"%PYENV%" -c "import pytest" 2>nul
if errorlevel 1 (
    echo pytest no esta instalado en el entorno. Instalandolo...
    "%PYENV%" -m pip install pytest
    if errorlevel 1 (
        echo ERROR: no se ha podido instalar pytest.
        goto pausa
    )
)
echo.
echo Comprobando el programa entero. Tarda unos segundos.
echo.
"%PYENV%" -m pytest
if errorlevel 1 (
    echo.
    echo HAY PRUEBAS QUE FALLAN. Arriba se dice cuales y por que.
) else (
    echo.
    echo Todo correcto.
)
goto pausa

rem ---------------------------------------------------------------------------
:empaquetar
cls
echo === Paquete de actualizacion ===
if not exist "%PYENV%" (
    echo El entorno virtual no existe. Usa antes la opcion 1.
    goto pausa
)
if not exist "%SALIDA%" (
    echo No hay ninguna compilacion en %SALIDA%
    echo Compila primero con la opcion 3.
    goto pausa
)
echo.
echo Se comprime la compilacion, se calcula su sha256 y se escribe el
echo version.json que hay que subir al servidor junto al zip.
echo.
"%PYENV%" "%RAIZ%herramientas\empaquetar.py"
goto pausa

rem ---------------------------------------------------------------------------
:abrir
if exist "%SALIDA%" (
    start "" explorer "%SALIDA%"
    goto menu
)
cls
echo Todavia no hay ninguna compilacion. Usa la opcion 3.
goto pausa

rem ---------------------------------------------------------------------------
:limpiar
cls
echo === Limpieza ===
echo.
echo Se borraran:
echo   - la carpeta build ^(compilaciones^)
echo   - data\cache ^(libros analizados^)
echo   - data\temp ^(archivos temporales^)
echo   - los archivos .pyc del codigo
echo.
echo NO se borran tus ajustes, marcadores, registros ni el entorno virtual.
echo.
set "CONFIRMA="
set /p CONFIRMA=Escribe S para continuar:
if /i not "%CONFIRMA%"=="S" goto menu
if exist "%RAIZ%build" rmdir /s /q "%RAIZ%build"
if exist "%RAIZ%data\cache" rmdir /s /q "%RAIZ%data\cache"
if exist "%RAIZ%data\temp" rmdir /s /q "%RAIZ%data\temp"
for /d /r "%RAIZ%src" %%D in (__pycache__) do if exist "%%D" rmdir /s /q "%%D"
echo Limpieza terminada.
goto pausa

rem ---------------------------------------------------------------------------
:borrar_entorno
cls
echo === Eliminar el entorno virtual ===
if not exist "%ENTORNO%" (
    echo No hay ningun entorno virtual que eliminar.
    goto pausa
)
echo.
echo Se borrara por completo la carpeta:
echo   %ENTORNO%
echo.
echo Despues tendras que volver a usar la opcion 1.
echo.
set "CONFIRMA="
set /p CONFIRMA=Escribe S para continuar:
if /i not "%CONFIRMA%"=="S" goto menu
rmdir /s /q "%ENTORNO%"
echo Entorno virtual eliminado.
goto pausa

rem ---------------------------------------------------------------------------
:comprobar
cls
echo === Comprobacion de la instalacion ===
:comprobar_comun
echo.
if not exist "%PYENV%" (
    echo El entorno virtual no existe. Usa antes la opcion 1.
    goto pausa
)
if exist "%FICHA%" (
    set "INFO="
    set /p INFO=<"%FICHA%"
    echo Entorno creado con: !INFO!
    echo.
)
"%PYENV%" -c "import sys; print('Python del entorno .', sys.version.split()[0], sys.executable)"
"%PYENV%" -c "import wx; print('wxPython ..........', wx.version())" 2>nul || echo wxPython ......... NO INSTALADO
"%PYENV%" -c "import lxml.etree as e; print('lxml ..............', '.'.join(str(n) for n in e.LXML_VERSION))" 2>nul || echo lxml ............. NO INSTALADO
"%PYENV%" -c "import accessible_output2; print('accessible-output2 . instalado')" 2>nul || echo accessible-output2 . no instalado ^(opcional^)
"%PYENV%" -c "import cx_Freeze; print('cx_Freeze .........', cx_Freeze.__version__)" 2>nul || echo cx_Freeze ......... no instalado ^(solo para compilar^)
echo.
echo Comprobando que el codigo del programa se puede cargar...
"%PYENV%" -c "import sys; sys.path.insert(0, r'%RAIZ%src'); from nucleo import rutas; rutas.preparar_estructura(); from formatos import epub; print('Codigo correcto. Carpeta de datos:', rutas.directorio_datos())"
goto pausa

rem ---------------------------------------------------------------------------
:pausa
echo.
pause
goto menu

:fin
endlocal
