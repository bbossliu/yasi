from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    target_band: Mapped[float] = mapped_column(Float, default=6.5)


class SkillNode(Base):
    __tablename__ = "skill_node"

    id: Mapped[int] = mapped_column(primary_key=True)
    module: Mapped[str] = mapped_column(String(20))  # writing/speaking/listening/vocab
    code: Mapped[str] = mapped_column(String(50), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("skill_node.id"), nullable=True)
    criteria: Mapped[dict] = mapped_column(JSON, default=dict)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class SkillMastery(Base):
    __tablename__ = "skill_mastery"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), default=1)
    node_id: Mapped[int] = mapped_column(ForeignKey("skill_node.id"))
    status: Mapped[str] = mapped_column(String(20), default="unseen")  # unseen/learned/verified
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Word(Base):
    __tablename__ = "word"

    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(String(100), unique=True)
    pos: Mapped[str] = mapped_column(String(20), default="")
    meaning: Mapped[str] = mapped_column(String(300), default="")
    topic: Mapped[str] = mapped_column(String(50), default="")
    paraphrase_chain: Mapped[list] = mapped_column(JSON, default=list)
    example_sentence: Mapped[str] = mapped_column(Text, default="")


class ReviewCard(Base):
    __tablename__ = "review_card"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), default=1)
    word_id: Mapped[int] = mapped_column(ForeignKey("word.id"))
    ease_factor: Mapped[float] = mapped_column(Float, default=2.5)
    interval_days: Mapped[int] = mapped_column(Integer, default=1)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reps: Mapped[int] = mapped_column(Integer, default=0)


class ListeningMat(Base):
    __tablename__ = "listening_mat"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    audio_path: Mapped[str] = mapped_column(String(500), default="")
    transcript: Mapped[list] = mapped_column(JSON, default=list)


class Practice(Base):
    __tablename__ = "practice"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), default=1)
    module: Mapped[str] = mapped_column(String(20), default="writing")
    prompt_title: Mapped[str] = mapped_column(String(300))
    prompt_text: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    duration_sec: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/done/needs_review
    total_band: Mapped[float | None] = mapped_column(Float, nullable=True)
    audio_path: Mapped[str] = mapped_column(String(500), default="")
    session_id: Mapped[int | None] = mapped_column(ForeignKey("speaking_session.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    feedback: Mapped["AIFeedback | None"] = relationship(back_populates="practice")


class AIFeedback(Base):
    __tablename__ = "ai_feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    practice_id: Mapped[int] = mapped_column(ForeignKey("practice.id"), unique=True)
    bands: Mapped[dict] = mapped_column(JSON)  # {task_response, coherence, lexical, grammar, overall}
    annotations: Mapped[list] = mapped_column(JSON)
    rewrite: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(50), default="")
    is_mock: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    practice: Mapped[Practice] = relationship(back_populates="feedback")


class ErrorItem(Base):
    __tablename__ = "error_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), default=1)
    practice_id: Mapped[int] = mapped_column(ForeignKey("practice.id"))
    error_type: Mapped[str] = mapped_column(String(100))
    context: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MockExam(Base):
    __tablename__ = "mock_exam"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), default=1)
    scores: Mapped[dict] = mapped_column(JSON, default=dict)
    predicted_band: Mapped[float | None] = mapped_column(Float, nullable=True)
    report: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SpeakingCard(Base):
    __tablename__ = "speaking_card"

    id: Mapped[int] = mapped_column(primary_key=True)
    part: Mapped[int] = mapped_column(Integer)  # 1/2/3
    topic: Mapped[str] = mapped_column(String(300))
    season: Mapped[str] = mapped_column(String(20), default="2026-09")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    sessions: Mapped[list["SpeakingSession"]] = relationship(back_populates="card")


class SpeakingSession(Base):
    __tablename__ = "speaking_session"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), default=1)
    card_id: Mapped[int] = mapped_column(ForeignKey("speaking_card.id"))
    status: Mapped[str] = mapped_column(String(20), default="active")  # active/done
    current_question: Mapped[str] = mapped_column(Text, default="")
    turn_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    card: Mapped[SpeakingCard] = relationship(back_populates="sessions")
