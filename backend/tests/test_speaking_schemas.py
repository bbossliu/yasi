import pytest
from pydantic import ValidationError

from app.data.sample import SAMPLE_SPEAKING_RESULT
from app.schemas import SpeakingResult


def test_speaking_result_schema():
    result = SAMPLE_SPEAKING_RESULT
    assert result.bands.fluency <= 9
    assert result.bands.pronunciation <= 9
    assert len(result.annotations) >= 3
    assert len(result.rewrite.split()) >= 40


def test_speaking_result_rejects_writing_bands():
    bad = """{
      "bands": {"task_response": 6.0, "coherence": 6.0, "lexical": 6.0, "grammar": 6.0, "overall": 6.0},
      "annotations": [], "rewrite": "x"
    }"""
    with pytest.raises(ValidationError):
        SpeakingResult.model_validate_json(bad)
