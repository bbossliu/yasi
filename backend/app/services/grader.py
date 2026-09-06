import logging

from openai import OpenAI
from sqlalchemy import select

from app.config import settings
from app.models import AIFeedback, ErrorItem, Practice, SkillMastery, SkillNode
from app.prompt_templates import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from app.schemas import GradingResult
from app.services.mock_grader import MockGrader

logger = logging.getLogger(__name__)


class GradingFailed(Exception):
    pass


class LLMGrader:
    is_mock = False

    def __init__(self, api_key: str, base_url: str, model: str):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def grade(self, prompt_text: str, content: str) -> GradingResult:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": USER_PROMPT_TEMPLATE.format(
                            prompt_text=prompt_text, content=content)},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                    max_tokens=8192,
                )
                return GradingResult.model_validate_json(resp.choices[0].message.content)
            except Exception as exc:  # 网络错误与 JSON 校验失败统一重试
                last_error = exc
                logger.warning("grading attempt %d failed: %s", attempt + 1, exc)
        raise GradingFailed(str(last_error))


def build_grader():
    if settings.deepseek_api_key:
        return LLMGrader(settings.deepseek_api_key, settings.deepseek_base_url, settings.deepseek_model)
    return MockGrader()


def mark_writing_learned(session, user_id: int) -> int:
    """把 writing 模块下所有能力点标为 learned（已学未验证），幂等。返回新标黄数量。"""
    node_ids = session.scalars(select(SkillNode.id).where(SkillNode.module == "writing")).all()
    existing = set(session.scalars(
        select(SkillMastery.node_id).where(SkillMastery.user_id == user_id)).all())
    added = 0
    for node_id in node_ids:
        if node_id not in existing:
            session.add(SkillMastery(user_id=user_id, node_id=node_id, status="learned",
                                     evidence={"source": "essay_graded"}))
            added += 1
    return added


def run_grading(practice_id: int, session_factory, grader=None) -> None:
    session = session_factory()
    try:
        practice = session.get(Practice, practice_id)
        if practice is None:
            return
        if grader is None:
            grader = build_grader()
        try:
            result = grader.grade(practice.prompt_text, practice.content)
        except GradingFailed as exc:
            practice.status = "needs_review"
            session.commit()
            logger.error("grading failed for practice %s: %s", practice_id, exc)
            return

        session.add(AIFeedback(
            practice_id=practice.id,
            bands=result.bands.model_dump(),
            annotations=[a.model_dump() for a in result.annotations],
            rewrite=result.rewrite,
            model=getattr(grader, "model", "unknown"),
            is_mock=getattr(grader, "is_mock", False),
        ))
        practice.status = "done"
        practice.total_band = result.bands.overall
        for annotation in result.annotations:
            if annotation.error_type:
                session.add(ErrorItem(
                    user_id=practice.user_id,
                    practice_id=practice.id,
                    error_type=annotation.error_type,
                    context=annotation.original,
                ))
        mark_writing_learned(session, practice.user_id)
        session.commit()
    finally:
        session.close()
