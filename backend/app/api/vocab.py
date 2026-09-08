from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from app.models import ReviewCard, Word
from app.schemas import (ForecastOut, ReviewCardOut, ReviewQueueOut, ReviewSubmit,
                         TopicOut, WordOut)
from app.services.sm2 import build_review_queue, get_or_create_card, sm2_review
from app.services.tts import tts_url_for

router = APIRouter(prefix="/api")

MASTERY_MIN_REPS = 2
MASTERY_MIN_INTERVAL = 7


def get_session(request: Request):
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


@router.get("/vocab/topics", response_model=list[TopicOut])
def list_topics(session=Depends(get_session)):
    words = session.scalars(select(Word)).all()
    cards = {c.word_id: c for c in session.scalars(select(ReviewCard)).all()}
    now = datetime.now()
    agg: dict[str, dict] = defaultdict(lambda: {"word_count": 0, "mastered_count": 0, "due_count": 0})
    for w in words:
        bucket = agg[w.topic]
        bucket["word_count"] += 1
        card = cards.get(w.id)
        if card:
            if card.reps >= MASTERY_MIN_REPS and card.interval_days >= MASTERY_MIN_INTERVAL:
                bucket["mastered_count"] += 1
            if card.due_at and card.due_at <= now:
                bucket["due_count"] += 1
    return [TopicOut(topic=t, **v) for t, v in sorted(agg.items())]


@router.get("/vocab/words", response_model=list[WordOut])
def list_words(topic: str, session=Depends(get_session)):
    words = session.scalars(
        select(Word).where(Word.topic == topic).order_by(Word.id)).all()
    cards = {c.word_id: c for c in session.scalars(select(ReviewCard)).all()}
    result = []
    for w in words:
        card = cards.get(w.id)
        result.append(WordOut(
            id=w.id, text=w.text, pos=w.pos, meaning=w.meaning,
            paraphrase_chain=w.paraphrase_chain, example_sentence=w.example_sentence,
            due_at=card.due_at if card else None,
            reps=card.reps if card else 0,
        ))
    return result


@router.get("/vocab/review/queue", response_model=ReviewQueueOut)
def review_queue(limit: int = 20, session=Depends(get_session)):
    cards, due_total = build_review_queue(session, 1, limit=limit)
    return ReviewQueueOut(cards=[ReviewCardOut(**c) for c in cards], due_total=due_total)


@router.post("/vocab/review/{word_id}")
def submit_review(word_id: int, payload: ReviewSubmit, session=Depends(get_session)):
    word = session.get(Word, word_id)
    if word is None:
        raise HTTPException(status_code=404, detail="单词不存在")
    card = get_or_create_card(session, 1, word_id)
    sm2_review(card, payload.quality, datetime.now())
    session.commit()
    return {"next_due_at": card.due_at, "interval_days": card.interval_days}


@router.post("/vocab/tts/{word_id}")
def word_tts(word_id: int, session=Depends(get_session)):
    """合成单词发音（edge-tts，磁盘缓存），返回 {"url": "/api/tts/xxx.mp3"}。"""
    word = session.get(Word, word_id)
    if word is None:
        raise HTTPException(status_code=404, detail="单词不存在")
    url = tts_url_for(word.text)
    if url is None:
        raise HTTPException(status_code=503, detail="语音合成失败，请稍后重试")
    return {"url": url}


@router.get("/vocab/forecast", response_model=list[ForecastOut])
def forecast(session=Depends(get_session)):
    now = datetime.now()
    today = now.date()
    cards = session.scalars(select(ReviewCard).where(ReviewCard.due_at.isnot(None))).all()
    counts: dict[str, int] = defaultdict(int)
    for card in cards:
        if card.due_at <= now:  # 今天到期（含逾期）计入今天
            counts[today.isoformat()] += 1
        else:
            day = card.due_at.date()
            if day <= today + timedelta(days=6):
                counts[day.isoformat()] += 1
    return [ForecastOut(date=(today + timedelta(days=i)).isoformat(),
                        count=counts.get((today + timedelta(days=i)).isoformat(), 0))
            for i in range(7)]
