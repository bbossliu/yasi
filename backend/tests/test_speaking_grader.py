from sqlalchemy import select

from app.data.sample import SAMPLE_SPEAKING_RESULT
from app.database import Base, make_session_factory
from app.models import (AIFeedback, ErrorItem, Practice, SkillMastery, SkillNode,
                        SpeakingCard, SpeakingSession, User)
from app.seed_speaking import seed_speaking_db
from app.services.asr.base import TranscribeFailed, TranscriptResult
from app.services.speaking_grader import run_speaking_turn


def make_db(tmp_path):
    factory = make_session_factory(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(factory.kw["bind"])
    return factory


def seed(factory, part=1, questions=None):
    s = factory()
    s.add(User(id=1))
    seed_speaking_db(s)
    payload = {"questions": questions or ["Q1?", "Q2?"]}
    s.add(SpeakingCard(id=99, part=part, topic="T", season="2026-09", payload=payload))
    s.add(SpeakingSession(id=99, user_id=1, card_id=99, status="active",
                          current_question="Q1?", turn_count=0))
    s.add(Practice(id=99, user_id=1, module="speaking", session_id=99,
                   prompt_title="T", prompt_text="Q1?", content="",
                   audio_path="x.wav", status="pending"))
    s.commit()
    s.close()


class FakeTranscriber:
    is_mock = True

    def transcribe(self, audio_path):
        return TranscriptResult(text="Well I think it is good things.", confidence=0.9)


class BrokenTranscriber:
    is_mock = True

    def transcribe(self, audio_path):
        raise TranscribeFailed("asr down")


class FakeSpeakingGrader:
    is_mock = False
    model = "fake"

    def grade(self, question, transcript, confidence):
        return SAMPLE_SPEAKING_RESULT


def test_speaking_turn_success_and_session_advance(tmp_path):
    factory = make_db(tmp_path)
    seed(factory)
    run_speaking_turn(99, factory, transcriber=FakeTranscriber(), grader=FakeSpeakingGrader())

    s = factory()
    p = s.get(Practice, 99)
    assert p.status == "done"
    assert p.content.startswith("Well I think")  # 转写文本落库
    assert p.total_band == 5.5
    fb = s.scalars(select(AIFeedback).where(AIFeedback.practice_id == 99)).one()
    assert fb.bands["fluency"] == 5.5
    errors = s.scalars(select(ErrorItem).where(ErrorItem.practice_id == 99)).all()
    assert {e.error_type for e in errors} == {"流利度", "词汇搭配", "主谓一致"}
    # 会话推进到第二问
    sess = s.get(SpeakingSession, 99)
    assert sess.turn_count == 1
    assert sess.current_question == "Q2?"
    assert sess.status == "active"
    # 口语能力点标黄
    masteries = s.scalars(select(SkillMastery)).all()
    speaking_nodes = s.scalars(select(SkillNode.id).where(SkillNode.module == "speaking")).all()
    assert {m.node_id for m in masteries} == set(speaking_nodes)
    s.close()


def test_session_completes_after_last_question(tmp_path):
    factory = make_db(tmp_path)
    seed(factory, questions=["Q1?"])
    run_speaking_turn(99, factory, transcriber=FakeTranscriber(), grader=FakeSpeakingGrader())
    s = factory()
    sess = s.get(SpeakingSession, 99)
    assert sess.status == "done"
    assert sess.turn_count == 1
    s.close()


def test_transcribe_failure_marks_needs_review(tmp_path):
    factory = make_db(tmp_path)
    seed(factory)
    run_speaking_turn(99, factory, transcriber=BrokenTranscriber(), grader=FakeSpeakingGrader())
    s = factory()
    assert s.get(Practice, 99).status == "needs_review"
    assert s.scalars(select(AIFeedback)).all() == []
    s.close()


PART3_QUESTIONS = ["Q1?", "Q2?", "Q3?"]


def add_turn_practice(factory, practice_id, question):
    s = factory()
    s.add(Practice(id=practice_id, user_id=1, module="speaking", session_id=99,
                   prompt_title="T", prompt_text=question, content="",
                   audio_path="x.wav", status="pending"))
    s.commit()
    s.close()


def run_turns(factory, count):
    for i in range(count):
        pid = 99 + i
        if i > 0:
            s = factory()
            question = s.get(SpeakingSession, 99).current_question
            s.close()
            add_turn_practice(factory, pid, question)
        run_speaking_turn(pid, factory, transcriber=FakeTranscriber(),
                          grader=FakeSpeakingGrader())


def test_part3_followup_after_preset_questions(tmp_path, monkeypatch):
    factory = make_db(tmp_path)
    seed(factory, part=3, questions=PART3_QUESTIONS)
    monkeypatch.setattr("app.services.followup.generate_followup",
                        lambda topic, history: "Why do you think so?")
    run_turns(factory, 3)  # 耗完 3 个预设问
    s = factory()
    sess = s.get(SpeakingSession, 99)
    assert sess.status == "active"
    assert sess.turn_count == 3
    assert sess.current_question == "Why do you think so?"
    s.close()


def test_part3_followup_failure_ends_session(tmp_path, monkeypatch):
    factory = make_db(tmp_path)
    seed(factory, part=3, questions=PART3_QUESTIONS)
    monkeypatch.setattr("app.services.followup.generate_followup",
                        lambda topic, history: None)
    run_turns(factory, 3)
    s = factory()
    sess = s.get(SpeakingSession, 99)
    assert sess.status == "done"
    assert sess.current_question == ""
    s.close()


def test_part3_max_turns_stops_followup(tmp_path, monkeypatch):
    factory = make_db(tmp_path)
    seed(factory, part=3, questions=PART3_QUESTIONS)
    calls = []

    def fake_followup(topic, history):
        calls.append((topic, history))
        return "Why do you think so?"

    monkeypatch.setattr("app.services.followup.generate_followup", fake_followup)
    run_turns(factory, 5)  # 3 预设 + 2 追问，达到 PART3_MAX_TURNS
    s = factory()
    sess = s.get(SpeakingSession, 99)
    assert sess.turn_count == 5
    assert sess.status == "done"
    s.close()
    assert len(calls) == 2  # 第 4、5 轮各追问一次，第 5 轮后不再追问
