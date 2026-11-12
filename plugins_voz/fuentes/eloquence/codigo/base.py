from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Callable


class TTSState(str, Enum):
    STOPPED = "detenido"
    PLAYING = "reproduciendo"
    PAUSED = "pausado"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class VoiceInfo:
    id: str
    name: str
    language: str = ""


class BaseTTSProvider(ABC):
    provider_id = "base"
    rate_min = -10
    rate_max = 10

    def __init__(self):
        self.on_finished: Callable[[], None] | None = None
        self.on_state: Callable[[TTSState], None] | None = None
        self.on_error: Callable[[str], None] | None = None

    @abstractmethod
    def voices(self) -> list[VoiceInfo]: ...

    @abstractmethod
    def speak(self, text: str) -> None: ...

    @abstractmethod
    def pause(self) -> None: ...

    @abstractmethod
    def resume(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def set_voice(self, voice_id: str) -> None: ...

    @abstractmethod
    def set_rate(self, rate: int) -> None: ...

    @abstractmethod
    def set_volume(self, volume: int) -> None: ...

    @abstractmethod
    def close(self) -> None: ...
