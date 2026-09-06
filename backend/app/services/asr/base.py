from dataclasses import dataclass
from typing import Protocol


@dataclass
class TranscriptResult:
    text: str
    confidence: float  # 0-1


class TranscribeFailed(Exception):
    pass


class Transcriber(Protocol):
    is_mock: bool

    def transcribe(self, audio_path: str) -> TranscriptResult: ...
