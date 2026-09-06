from app.data.sample import SAMPLE_GRADING
from app.schemas import GradingResult


class MockGrader:
    """无 DEEPSEEK_API_KEY 时的降级批改器：返回预置示例批改结果。"""

    model = "mock"
    is_mock = True

    def grade(self, prompt_text: str, content: str) -> GradingResult:
        return SAMPLE_GRADING
