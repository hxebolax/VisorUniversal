# -*- coding: utf-8 -*-
"""Pruebas de la lectura de fórmulas MathML."""

from lxml import etree

from formatos import matematicas


def formula(xml: str):
    """Convierte un fragmento de MathML en un elemento."""
    return etree.fromstring(xml)


ESPACIO = 'xmlns="http://www.w3.org/1998/Math/MathML"'


def test_ecuacion_de_segundo_grado():
    """Una potencia con exponente 2 se dice «al cuadrado», no «elevado a 2»."""
    elemento = formula(
        '<math %s><mrow><msup><mi>x</mi><mn>2</mn></msup><mo>+</mo><mn>3</mn>'
        '<mi>x</mi><mo>-</mo><mn>5</mn><mo>=</mo><mn>0</mn></mrow></math>' % ESPACIO)
    assert matematicas.a_texto(elemento) == "x al cuadrado más 3 x menos 5 igual a 0"


def test_numero_y_letra_no_se_pegan():
    """«3» seguido de «x» se separa: pegados se leen como una sola palabra."""
    elemento = formula('<math %s><mn>3</mn><mi>x</mi></math>' % ESPACIO)
    assert matematicas.a_texto(elemento) == "3 x"


def test_fraccion():
    """Una fracción se abre y se cierra, para saber dónde acaba."""
    elemento = formula(
        '<math %s><mfrac><mrow><mi>a</mi><mo>+</mo><mi>b</mi></mrow>'
        '<mn>2</mn></mfrac></math>' % ESPACIO)
    dicho = matematicas.a_texto(elemento)
    assert dicho.startswith("la fracción")
    assert "partido por" in dicho
    assert dicho.endswith("fin de la fracción")


def test_raiz_cuadrada():
    elemento = formula('<math %s><msqrt><mi>x</mi></msqrt></math>' % ESPACIO)
    assert matematicas.a_texto(elemento) == "raíz cuadrada de x, fin de la raíz"


def test_sumatorio_con_limites_no_dice_de_desde():
    """El «de» del sumatorio sobra cuando detrás viene «desde»."""
    elemento = formula(
        '<math %s><munderover><mo>&#8721;</mo><mrow><mi>i</mi><mo>=</mo><mn>1</mn>'
        '</mrow><mi>n</mi></munderover></math>' % ESPACIO)
    dicho = matematicas.a_texto(elemento)
    assert "de desde" not in dicho
    assert dicho == "sumatorio desde i igual a 1 hasta n"


def test_letras_griegas():
    elemento = formula('<math %s><mi>&#945;</mi><mo>&#8804;</mo><mi>&#946;</mi></math>'
                       % ESPACIO)
    assert matematicas.a_texto(elemento) == "alfa menor o igual que beta"


def test_funciones_conocidas():
    """«sin» es el seno, no una palabra que deletrear."""
    elemento = formula('<math %s><mi>sin</mi><mi>x</mi></math>' % ESPACIO)
    assert matematicas.a_texto(elemento).startswith("seno de")


def test_matriz():
    elemento = formula(
        '<math %s><mtable><mtr><mtd><mn>1</mn></mtd><mtd><mn>2</mn></mtd></mtr>'
        '<mtr><mtd><mn>3</mn></mtd><mtd><mn>4</mn></mtd></mtr></mtable></math>' % ESPACIO)
    dicho = matematicas.a_texto(elemento)
    assert "matriz de 2 filas" in dicho
    assert "1, 2; 3, 4" in dicho


def test_sin_espacio_de_nombres():
    """Los libros viejos no declaran el espacio de nombres y hay que aceptarlos."""
    elemento = formula("<math><mi>x</mi><mo>=</mo><mn>1</mn></math>")
    assert matematicas.a_texto(elemento) == "x igual a 1"


def test_alttext_como_ultimo_recurso():
    """Sin contenido legible se usa el texto alterno antes que callar."""
    elemento = formula('<math %s alttext="E = mc^2"></math>' % ESPACIO)
    assert matematicas.a_texto(elemento) == "E = mc^2"


def test_formula_vacia_del_todo():
    elemento = formula("<math %s></math>" % ESPACIO)
    assert matematicas.a_texto(elemento) == "fórmula"


def test_anotacion_no_se_lee():
    """La anotación en LaTeX es la misma fórmula otra vez: no se dice."""
    elemento = formula(
        '<math %s><semantics><mrow><mi>x</mi></mrow>'
        '<annotation encoding="application/x-tex">x</annotation></semantics></math>'
        % ESPACIO)
    assert matematicas.a_texto(elemento) == "x"


def test_html_conserva_el_espacio_de_nombres():
    """El navegador solo reconoce las matemáticas con su espacio de nombres."""
    elemento = formula("<math><mi>x</mi></math>")
    html = matematicas.a_html(elemento)
    assert "http://www.w3.org/1998/Math/MathML" in html
    assert "<mi>x</mi>" in html


def test_es_formula():
    assert matematicas.es_formula("{http://www.w3.org/1998/Math/MathML}math")
    assert matematicas.es_formula("math")
    assert not matematicas.es_formula("table")
    assert not matematicas.es_formula(None)


def test_anidamiento_absurdo_no_revienta():
    """Una fórmula generada por un programa puede venir con cientos de niveles."""
    xml = "<math %s>" % ESPACIO + "<mrow>" * 200 + "<mi>x</mi>" + "</mrow>" * 200 + "</math>"
    dicho = matematicas.a_texto(formula(xml))
    assert dicho  # lo que importe es que no lance ni agote la pila
