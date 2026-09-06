import re
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.config import settings
from app.models import Practice, SpeakingCard, SpeakingSession
from app.schemas import (FeedbackOut, SessionCreate, SessionOut, SessionSummary,
                         SpeakingCardOut, TurnDetail, TurnSummaryItem)
from app.services.speaking_grader import run_speaking_turn
from app.services.tts import tts_url_for

router = APIRouter(prefix="/api")

MAX_AUDIO_BYTES = 5 * 1024 * 1024
TTS_NAME_RE = re.compile(r"^[a-f0-9]{16}\.mp3$")


def get_session(request: Request):
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


@router.get("/speaking/cards", response_model=list[SpeakingCardOut])
def list_cards(part: int, session=Depends(get_session)):
    return session.scalars(
        select(SpeakingCard).where(SpeakingCard.part == part)
        .order_by(SpeakingCard.id)).all()


@router.post("/speaking/sessions", response_model=SessionOut, status_code=201)
def create_session(payload: SessionCreate, session=Depends(get_session)):
    card = session.get(SpeakingCard, payload.card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="话题卡不存在")
    if card.part == 2:
        cues = "、".join(card.payload.get("cues", []))
        question = f"{card.topic}\nYou should say: {cues}"
    else:
        question = card.payload["questions"][0]
    speaking_session = SpeakingSession(
        user_id=1, card_id=card.id, current_question=question)
    session.add(speaking_session)
    session.commit()
    session.refresh(speaking_session)
    return SessionOut(
        id=speaking_session.id, part=card.part, topic=card.topic,
        status=speaking_session.status, question=question,
        tts_url=tts_url_for(question),
    )


@router.post("/speaking/turns", status_code=202)
def submit_turn(request: Request, background: BackgroundTasks,
                session_id: int = Form(...), audio: UploadFile = File(...),
                session=Depends(get_session)):
    speaking_session = session.get(SpeakingSession, session_id)
    if speaking_session is None or speaking_session.status != "active":
        raise HTTPException(status_code=404, detail="会话不存在或已结束")
    if not (audio.filename or "").lower().endswith(".wav"):
        raise HTTPException(status_code=422, detail="仅支持 .wav 音频")
    data = audio.file.read()
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="音频超过 5MB 上限")

    uploads = Path(settings.uploads_dir)
    uploads.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.wav"
    (uploads / filename).write_bytes(data)

    practice = Practice(
        user_id=1, module="speaking", session_id=speaking_session.id,
        prompt_title=speaking_session.card.topic,
        prompt_text=speaking_session.current_question,
        content="", audio_path=str(uploads / filename), status="pending",
    )
    session.add(practice)
    session.commit()
    session.refresh(practice)
    background.add_task(run_speaking_turn, practice.id, request.app.state.session_factory)
    return {"practice_id": practice.id}


@router.get("/speaking/turns/{practice_id}", response_model=TurnDetail)
def get_turn(practice_id: int, session=Depends(get_session)):
    practice = session.get(Practice, practice_id)
    if practice is None or practice.module != "speaking":
        raise HTTPException(status_code=404, detail="练习不存在")
    feedback = None
    if practice.feedback:
        feedback = FeedbackOut(
            bands=practice.feedback.bands,
            annotations=practice.feedback.annotations,
            rewrite=practice.feedback.rewrite,
            is_mock=practice.feedback.is_mock,
        )
    speaking_session = session.get(SpeakingSession, practice.session_id)
    session_done = speaking_session.status == "done"
    # 仅当本轮评分完成后才把"下一问"暴露给前端（pending 期间 current_question 还是旧问题）
    next_q = speaking_session.current_question if (
        not session_done and practice.status == "done") else None
    return TurnDetail(
        practice_id=practice.id,
        status=practice.status,
        transcript=practice.content or None,
        feedback=feedback,
        next_question=next_q,
        next_tts_url=tts_url_for(next_q) if next_q else None,
        session_done=session_done,
    )


@router.post("/speaking/sessions/{session_id}/finish", response_model=SessionSummary)
def finish_session(session_id: int, session=Depends(get_session)):
    speaking_session = session.get(SpeakingSession, session_id)
    if speaking_session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    speaking_session.status = "done"
    turns = session.scalars(
        select(Practice)
        .where(Practice.session_id == session_id, Practice.status == "done")
        .order_by(Practice.created_at)).all()
    session.commit()
    bands = [t.total_band for t in turns if t.total_band is not None]
    return SessionSummary(
        session_id=session_id,
        avg_band=round(sum(bands) / len(bands), 1) if bands else None,
        turns=[TurnSummaryItem(question=t.prompt_text, transcript=t.content,
                               total_band=t.total_band) for t in turns],
    )


@router.get("/tts/{filename}")
def get_tts(filename: str):
    if not TTS_NAME_RE.match(filename):
        raise HTTPException(status_code=404, detail="不存在")
    path = Path(settings.tts_cache_dir) / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="不存在")
    return FileResponse(path, media_type="audio/mpeg")
