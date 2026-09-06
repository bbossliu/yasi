import pytest
from pydantic import ValidationError

from app.schemas import EssayCreate, GradingResult


GOOD_JSON = """{
  "bands": {"task_response": 6.0, "coherence": 6.5, "lexical": 5.5, "grammar": 6.0, "overall": 6.0},
  "annotations": [
    {"sentence_index": 2, "original": "He go to school.", "issue": "主谓一致错误",
     "suggestion": "He goes to school.", "error_type": "主谓一致"}
  ],
  "rewrite": "Some rewritten essay."
}"""


def test_grading_result_parses_valid_json():
    result = GradingResult.model_validate_json(GOOD_JSON)
    assert result.bands.overall == 6.0
    assert result.annotations[0].error_type == "主谓一致"


def test_grading_result_rejects_out_of_range_band():
    bad = GOOD_JSON.replace('"overall": 6.0', '"overall": 9.5')
    with pytest.raises(ValidationError):
        GradingResult.model_validate_json(bad)


def test_essay_create_rejects_empty_and_too_long():
    with pytest.raises(ValidationError):
        EssayCreate(prompt_title="t", prompt_text="p", content="   ")
    with pytest.raises(ValidationError):
        EssayCreate(prompt_title="t", prompt_text="p", content="word " * 501)
