from app.services.asr.base import TranscriptResult

MOCK_TRANSCRIPT = (
    "Well, I think working from home is, um, it has a lot of benefits. "
    "First, people can save time because they don't need to, you know, "
    "take the bus or subway for two hours every day. "
    "And also it is more comfortable, you can wear what you like. "
    "But sometimes I feel lonely, because I cannot talk with my colleagues face to face. "
    "So I think it depends on the person, but for me the good things is more than the bad things."
)


class MockTranscriber:
    is_mock = True

    def transcribe(self, audio_path: str) -> TranscriptResult:
        return TranscriptResult(text=MOCK_TRANSCRIPT, confidence=0.9)
