from __future__ import annotations

import ctypes
import logging
import re
import threading
import time
from pathlib import Path

from .eci_proxy import EciProxy
from .ipc_client import terminate_host_32
from .assets import supports_22khz

log = logging.getLogger(__name__)

ECI_SYNTH_MODE = 0
ECI_INPUT_TYPE = 1
ECI_SAMPLE_RATE = 5
ECI_NUMBER_MODE = 10

PARAM_HEAD_SIZE = 1
PARAM_PITCH = 2
PARAM_FLUCTUATION = 3
PARAM_ROUGHNESS = 4
PARAM_BREATHINESS = 5
PARAM_SPEED = 6
PARAM_VOLUME = 7

ECI_WAVEFORM_BUFFER = 0
ECI_INDEX_REPLY = 2
FINAL_INDEX = 0xFFFF
AUDIO_BUFFER_SAMPLES = 3300

SAMPLE_RATES = {0: 8000, 1: 11025, 2: 22050}
SAMPLE_RATE_LABELS = {0: "8 kHz", 1: "11 kHz", 2: "22 kHz"}
LANGS = {
    "esp": (0x00020000, "Español de España"),
    "esm": (0x00020001, "Español latinoamericano"),
    "enu": (0x00010000, "Inglés americano"),
    "eng": (0x00010001, "Inglés británico"),
    "fra": (0x00030000, "Francés"),
    "frc": (0x00030001, "Francés de Canadá"),
    "deu": (0x00040000, "Alemán"),
    "ita": (0x00050000, "Italiano"),
    "ptb": (0x00070000, "Portugués de Brasil"),
    "fin": (0x00090000, "Finlandés"),
    "chs": (0x00060000, "Chino"),
    "jpn": (0x00080000, "Japonés"),
    "kor": (0x000A0000, "Coreano"),
}
LANG_ENCODINGS = {"chs": "gb18030", "jpn": "cp932", "kor": "cp949"}
VOICE_VARIANTS = {
    1: "Reed",
    2: "Shelley",
    3: "Sandy",
    4: "Rocko",
    5: "Glen",
    6: "FastFlo",
    7: "Grandma",
    8: "Grandpa",
}
VOICE_SETTINGS = {
    PARAM_HEAD_SIZE: "tamano_cabeza",
    PARAM_PITCH: "tono",
    PARAM_FLUCTUATION: "entonacion",
    PARAM_ROUGHNESS: "carraspeo",
    PARAM_BREATHINESS: "respiracion",
    PARAM_SPEED: "velocidad",
    PARAM_VOLUME: "volumen",
}

_ECI_MIN_RATE = 40
_ECI_MAX_RATE = 156


def percent_to_eci_rate(percent: int) -> int:
    percent = max(0, min(100, int(percent)))
    return _ECI_MIN_RATE + percent * (_ECI_MAX_RATE - _ECI_MIN_RATE) // 100


class ECIEngine:
    """Cliente ECI de 64 bits respaldado por el host Rust de 32 bits."""

    def __init__(self, dll_path: Path):
        self.dll_path = Path(dll_path)
        self.proxy: EciProxy | None = None
        self.handle: int | None = None
        self.audio = bytearray()
        self.synthesizing = False
        self.language = "esp"
        self.sample_rate_index = 1
        self.voice_params: dict[int, int] = {}
        self.pause_mode = 2
        self.phrase_prediction = True
        self.phrase_final_pause = 10
        self.number_mode = True
        self.abbreviation_dict = False

    @property
    def sample_rate(self) -> int:
        return SAMPLE_RATES.get(self.sample_rate_index, 11025)

    def initialize(self, config: dict) -> None:
        self.proxy = EciProxy(str(self.dll_path))
        self.language = str(config.get("idioma", "esp"))
        maximum_rate = 2 if supports_22khz(self.dll_path) else 1
        self.sample_rate_index = max(
            0, min(maximum_rate, int(config.get("frecuencia", 1)))
        )
        variant = max(1, min(8, int(config.get("variante", 1))))
        dialect = LANGS.get(self.language, LANGS["esp"])[0]
        self.handle = self.proxy.eciNewEx(dialect)
        if not self.handle:
            raise RuntimeError(f"Eloquence no pudo iniciar el idioma {self.language}.")
        self.proxy.eciRegisterCallback(self.handle, self._callback)
        self.proxy.eciSetOutputBuffer(self.handle, AUDIO_BUFFER_SAMPLES)
        self.proxy.eciSetParam(self.handle, ECI_SYNTH_MODE, 1)
        self.proxy.eciSetParam(self.handle, ECI_INPUT_TYPE, 1)
        self.proxy.eciSetParam(self.handle, ECI_SAMPLE_RATE, self.sample_rate_index)
        self.proxy.eciSetParam(
            self.handle,
            ECI_NUMBER_MODE,
            1 if config.get("numeros_como_anos", True) else 0,
        )
        if variant != 1:
            self.proxy.eciCopyVoice(self.handle, variant, 0)
        for param_id, key in VOICE_SETTINGS.items():
            default = {1: 50, 2: 65, 3: 30, 4: 0, 5: 0, 6: 55, 7: 100}[param_id]
            self.set_voice_param(param_id, int(config.get(key, default)))
        self.pause_mode = max(0, min(2, int(config.get("modo_pausas", 2))))
        self.phrase_prediction = bool(config.get("prediccion_frases", True))
        self.phrase_final_pause = max(
            1, min(40, int(config.get("pausa_final_frase", 10)))
        )
        self.number_mode = bool(config.get("numeros_como_anos", True))
        self.abbreviation_dict = bool(config.get("expandir_abreviaturas", False))
        log.info(
            "Eloquence iniciado: idioma=%s, variante=%s, frecuencia=%s",
            self.language,
            variant,
            self.sample_rate,
        )

    def set_voice_param(self, param_id: int, value: int) -> None:
        value = max(0, min(100, int(value)))
        self.voice_params[param_id] = value
        if self.proxy and self.handle:
            native = percent_to_eci_rate(value) if param_id == PARAM_SPEED else value
            self.proxy.eciSetVoiceParam(self.handle, 0, param_id, native)

    def synthesize(self, text: str, stop_event: threading.Event) -> bytes:
        if not self.proxy or not self.handle:
            raise RuntimeError("El motor Eloquence no está inicializado.")
        self.audio.clear()
        self.synthesizing = True
        encoded = text.encode(
            LANG_ENCODINGS.get(self.language, "cp1252"), errors="replace"
        )
        if self.pause_mode == 2:
            encoded = re.sub(
                rb"([a-zA-Z0-9]|\s)([-,.:;?!])\2*?(\s|$)", rb"\1 `p1\2\3", encoded
            )
        prefix = [b"`pp1" if self.phrase_prediction else b"`pp0"]
        if self.phrase_final_pause != 10:
            prefix.append(b"`epf%d" % self.phrase_final_pause)
        prefix.extend(
            (
                b"`vv%d" % self.voice_params.get(PARAM_VOLUME, 100),
                b"`vs%d" % percent_to_eci_rate(self.voice_params.get(PARAM_SPEED, 55)),
            )
        )
        self.proxy.eciAddText(self.handle, b" ".join(prefix) + b" " + encoded)
        if self.pause_mode >= 1:
            self.proxy.eciAddText(self.handle, b" `p1 ")
        self.proxy.eciInsertIndex(self.handle, FINAL_INDEX)
        self.proxy.eciSynthesize(self.handle)
        deadline = time.monotonic() + max(30.0, len(text) / 15.0)
        while self.synthesizing and time.monotonic() < deadline:
            if stop_event.wait(0.02):
                self.proxy.eciStop(self.handle)
                self.synthesizing = False
                return b""
        if self.synthesizing:
            self.proxy.eciStop(self.handle)
            self.synthesizing = False
            raise TimeoutError(
                "Eloquence agotó el tiempo disponible para sintetizar el texto."
            )
        return bytes(self.audio)

    def stop(self) -> None:
        if self.proxy and self.handle:
            self.proxy.eciStop(self.handle)
        self.synthesizing = False

    def close(self) -> None:
        try:
            if self.proxy and self.handle:
                self.proxy.eciStop(self.handle)
                self.proxy.eciDelete(self.handle)
                self.handle = None
            if self.proxy:
                self.proxy.close()
        finally:
            self.proxy = None
            terminate_host_32()

    def _callback(self, _handle, message, length, _user_data) -> int:
        if message == ECI_WAVEFORM_BUFFER and self.proxy:
            pointer = self.proxy.get_audio_buffer_ptr()
            if pointer:
                self.audio.extend(ctypes.string_at(pointer, length * 2))
        elif message == ECI_INDEX_REPLY and length == FINAL_INDEX:
            self.synthesizing = False
        return 1
