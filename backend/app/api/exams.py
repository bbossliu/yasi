from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import and_, or_, select

from app.models import (AIFeedback, ErrorItem, MockExam, Practice, ReviewCard,
                        SkillMastery, SkillNode, Word)
from app.schemas import ExamComplete, ExamOut
from app.services.exam_scoring import accuracy_to_band, overall_round, vocab_rate_to_band

router = APIRouter(prefix="/api")


def get_session(request: Request):
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


@router.post("/mock_exams", status_code=201)
def create_exam(session=Depends(get_session)):
    exam = MockExam(user_id=1)
    session.add(exam)
    session.commit()
    session.refresh(exam)
    return {"exam_id": exam.id}


@router.post("/mock_exams/{exam_id}/complete", response_model=ExamOut)
def complete_exam(exam_id: int, payload: ExamComplete, session=Depends(get_session)):
    exam = session.get(MockExam, exam_id)
    if exam is None:
        raise HTTPException(status_code=404, detail="模考不存在")
    practices = [session.get(Practice, pid) for pid in payload.practice_ids]
    by_module: dict[str, Practice] = {}
    for p in practices:
        if p is not None and p.status == "done" and p.module not in by_module:
            by_module[p.module] = p

    missing = [m for m in ("writing", "speaking", "listening") if m not in by_module]
    if missing:
        raise HTTPException(status_code=422, detail=f"缺少模块成绩: {', '.join(missing)}")

    scores = {
        "writing": by_module["writing"].feedback.bands["overall"],
        "speaking": by_module["speaking"].feedback.bands["overall"],
        "listening": accuracy_to_band(by_module["listening"].total_band or 0),
    }
    total_words = len(session.scalars(select(Word.id)).all())
    mastered = len(session.scalars(
        select(ReviewCard.id).where(ReviewCard.reps >= 2,
                                    ReviewCard.interval_days >= 7)).all())
    scores["vocab"] = vocab_rate_to_band(mastered / total_words if total_words else 0)

    avg = sum(scores.values()) / 4
    predicted = overall_round(avg)

    # 薄弱点报告：近 30 天错误聚类 TOP5 + 未绿节点
    since = datetime.now() - timedelta(days=30)
    errors = session.scalars(
        select(ErrorItem).where(ErrorItem.created_at >= since)).all()
    counts: dict[str, int] = {}
    for e in errors:
        counts[e.error_type] = counts.get(e.error_type, 0) + 1
    top_errors = [{"type": t, "count": c}
                  for t, c in sorted(counts.items(), key=lambda kv: -kv[1])[:5]]
    weak = session.scalars(
        select(SkillNode).outerjoin(
            SkillMastery, and_(SkillMastery.node_id == SkillNode.id,
                               SkillMastery.user_id == 1))
        .where(or_(SkillMastery.status.is_(None),
                   SkillMastery.status != "verified"))).all()
    weak_nodes = [{"code": n.code, "title": n.title} for n in weak[:10]]

    exam.scores = scores
    exam.predicted_band = predicted
    exam.report = {"top_errors": top_errors, "weak_nodes": weak_nodes}
    exam.practice_ids = payload.practice_ids
    session.commit()
    session.refresh(exam)
    return exam


@router.get("/mock_exams", response_model=list[ExamOut])
def list_exams(session=Depends(get_session)):
    return session.scalars(
        select(MockExam).where(MockExam.predicted_band.isnot(None))
        .order_by(MockExam.created_at.desc())).all()


@router.get("/mock_exams/latest", response_model=ExamOut | None)
def latest_exam(session=Depends(get_session)):
    return session.scalars(
        select(MockExam).where(MockExam.predicted_band.isnot(None))
        .order_by(MockExam.created_at.desc()).limit(1)).first()
