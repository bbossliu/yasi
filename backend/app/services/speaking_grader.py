import logging

from openai import OpenAI
from sqlalchemy import select

from app.config import settings
from app.data.sample import SAMPLE_SPEAKING_RESULT
from app.models import (AIFeedback, ErrorItem, Practice, SkillMastery, SkillNode,
                        SpeakingSession)
from app.prompt_templates import SYSTEM_PROMPT_SPEAKING, USER_PROMPT_SPEAKING_TEMPLATE
from app.schemas import SpeakingResult
from app.services.asr import TranscribeFailed, build_transcriber
from app.services.llm_json import LLMCallFailed, chat_json

logger = logging.getLogger(__name__)

PART3_MAX_TURNS = 5  # Part 3：预设问用完后由 LLM 追问，总轮数上限


class SpeakingGrader:
    is_mock = False

    def __init__(self, api_key: str, base_url: str, model: str):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def grade(self, question: str, transcript: str, confidence: float) -> SpeakingResult:
        return chat_json(
            self.client, self.model, SYSTEM_PROMPT_SPEAKING,
            USER_PROMPT_SPEAKING_TEMPLATE.format(
                question=question, transcript=transcript, confidence=confidence),
            SpeakingResult,
        )


class MockSpeakingGrader:
    is_mock = True
    model = "mock"

    def grade(self, question: str, transcript: str, confidence: float) -> SpeakingResult:
        return SAMPLE_SPEAKING_RESULT


def build_speaking_grader():
    if settings.deepseek_api_key:
        return SpeakingGrader(settings.deepseek_api_key, settings.deepseek_base_url,
                              settings.deepseek_model)
    return MockSpeakingGrader()


def mark_speaking_learned(session, user_id: int) -> int:
    node_ids = session.scalars(select(SkillNode.id).where(SkillNode.module == "speaking")).all()
    existing = set(session.scalars(
        select(SkillMastery.node_id).where(SkillMastery.user_id == user_id)).all())
    added = 0
    for node_id in node_ids:
        if node_id not in existing:
            session.add(SkillMastery(user_id=user_id, node_id=node_id, status="learned",
                                     evidence={"source": "speaking_turn_graded"}))
            added += 1
    return added


def _next_question(session, practice: Practice) -> str | None:
    """根据 card part 与 turn_count 决定下一问；None 表示会话结束。"""
    speaking_session = session.get(SpeakingSession, practice.session_id)
    card = speaking_session.card
    questions: list[str] = card.payload.get("questions", [])
    turn = speaking_session.turn_count  # 已完成的轮数
    if card.part == 2:
        return None
    if turn < len(questions):
        return questions[turn]
    if card.part == 3 and turn < PART3_MAX_TURNS:
        from app.services.followup import generate_followup

        history = [
            {"question": p.prompt_text, "answer": p.content}
            for p in session.scalars(
                select(Practice)
                .where(Practice.session_id == speaking_session.id, Practice.status == "done")
                .order_by(Practice.created_at)
            ).all()
        ]
        return generate_followup(card.topic, history)
    return None


def run_speaking_turn(practice_id: int, session_factory, transcriber=None, grader=None) -> None:
    session = session_factory()
    try:
        practice = session.get(Practice, practice_id)
        if practice is None:
            return
        if transcriber is None:
            transcriber = build_transcriber()
        if grader is None:
            grader = build_speaking_grader()
        try:
            transcript = transcriber.transcribe(practice.audio_path)
        except TranscribeFailed as exc:
            practice.status = "needs_review"
            session.commit()
            logger.error("transcribe failed for practice %s: %s", practice_id, exc)
            return
        practice.content = transcript.text
        practice.word_count = len(transcript.text.split())

        try:
            result = grader.grade(practice.prompt_text, transcript.text, transcript.confidence)
        except LLMCallFailed as exc:
            practice.status = "needs_review"
            session.commit()
            logger.error("speaking grading failed for practice %s: %s", practice_id, exc)
            return

        session.add(AIFeedback(
            practice_id=practice.id,
            bands=result.bands.model_dump(),
            annotations=[a.model_dump() for a in result.annotations],
            rewrite=result.rewrite,
            model=getattr(grader, "model", "unknown"),
            is_mock=bool(transcriber.is_mock or getattr(grader, "is_mock", False)),
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
        mark_speaking_learned(session, practice.user_id)

        # 推进会话
        speaking_session = session.get(SpeakingSession, practice.session_id)
        speaking_session.turn_count += 1
        next_q = _next_question(session, practice)
        if next_q is None:
            speaking_session.status = "done"
            speaking_session.current_question = ""
        else:
            speaking_session.current_question = next_q
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("run_speaking_turn failed for practice %s", practice_id)
        try:
            practice = session.get(Practice, practice_id)
            if practice is not None:
                practice.status = "needs_review"
                session.commit()
        except Exception:
            logger.exception("failed to mark practice %s needs_review", practice_id)
    finally:
        session.close()
