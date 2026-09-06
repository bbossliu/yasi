import logging

from openai import OpenAI
from sqlalchemy import select

from app.config import settings
from app.models import AIFeedback, ErrorItem, Practice, SkillMastery, SkillNode
from app.prompt_templates import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from app.schemas import GradingResult
from app.services.llm_json import LLMCallFailed, chat_json
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
        try:
            return chat_json(
                self.client, self.model, SYSTEM_PROMPT,
                USER_PROMPT_TEMPLATE.format(prompt_text=prompt_text, content=content),
                GradingResult,
            )
        except LLMCallFailed as exc:
            raise GradingFailed(str(exc)) from exc


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
            new_errors = []
            for annotation in result.annotations:
                if annotation.error_type:
                    item = ErrorItem(
                        user_id=practice.user_id,
                        practice_id=practice.id,
                        error_type=annotation.error_type,
                        context=annotation.original,
                    )
                    session.add(item)
                    new_errors.append(item)
            from app.services.vocab_link import link_vocab_errors
            link_vocab_errors(session, practice.user_id, new_errors)
            mark_writing_learned(session, practice.user_id)
            session.commit()
        except Exception:
            session.rollback()
            practice = session.get(Practice, practice_id)
            if practice is not None:
                practice.status = "needs_review"
                session.commit()
            logger.exception("unexpected grading error for practice %s", practice_id)
    finally:
        session.close()
