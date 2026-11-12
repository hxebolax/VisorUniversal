# -*- coding: utf-8 -*-
"""Descripción de imágenes con inteligencia artificial.

El paquete está escrito **solo con la biblioteca estándar**: las peticiones se
hacen con :mod:`urllib.request` y las respuestas se leen con :mod:`json`.  No
hace falta instalar nada más, ni el SDK de Google ni ``requests``, de modo que
el programa compilado no crece ni depende de que un paquete de terceros siga
manteniéndose.

Piezas:

* :mod:`nucleo.ia.prompts`: las instrucciones que se le dan a la IA, con un
  juego de prompts predefinidos por tipo de libro y los que añada el usuario.
* :mod:`nucleo.ia.gemini`: Google Gemini, por su API REST.
* :mod:`nucleo.ia.local`: cualquier servidor local compatible con la API de
  OpenAI (llama.cpp, Ollama, LM Studio).
* :mod:`nucleo.ia.servicio`: la puerta de entrada; elige proveedor, arma el
  prompt y devuelve la descripción.
"""
