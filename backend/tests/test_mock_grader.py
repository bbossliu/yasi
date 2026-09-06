from app.data.sample import SAMPLE_ESSAY, SAMPLE_GRADING
from app.services.mock_grader import MockGrader


def test_mock_grader_returns_valid_result():
    result = MockGrader().grade(prompt_text="any", content="any essay text")
    assert result.bands.overall == 6.0
    assert len(result.annotations) >= 3
    assert len(result.rewrite.split()) >= 200
    types = {a.error_type for a in result.annotations}
    assert "时态" in types or "主谓一致" in types


def test_sample_essay_is_band6_length():
    words = len(SAMPLE_ESSAY.split())
    assert 200 <= words <= 320
    assert SAMPLE_GRADING.bands.overall == 6.0
