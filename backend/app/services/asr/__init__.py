from app.config import settings
from app.services.asr.base import TranscribeFailed, Transcriber, TranscriptResult
from app.services.asr.iflytek import IFlytekTranscriber
from app.services.asr.mock import MockTranscriber

__all__ = [
    "TranscribeFailed", "Transcriber", "TranscriptResult",
    "IFlytekTranscriber", "MockTranscriber", "build_transcriber",
]


def build_transcriber() -> Transcriber:
    if settings.iflytek_app_id and settings.iflytek_api_secret:
        return IFlytekTranscriber(settings.iflytek_app_id, settings.iflytek_api_secret)
    return MockTranscriber()
