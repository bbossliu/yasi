from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import select

from app.data.sample import SAMPLE_ESSAY, SAMPLE_PROMPT_TEXT, SAMPLE_PROMPT_TITLE
from app.models import ErrorItem, Practice
from app.schemas import ErrorItemOut, EssayCreate, EssayDetail, EssayOut, FeedbackOut, PromptOut
from app.seed import TASK2_PROMPTS
from app.services.grader import run_grading

router = APIRouter(prefix="/api")


def get_session(request: Request):
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


@router.get("/prompts", response_model=list[PromptOut])
def list_prompts():
    return TASK2_PROMPTS


@router.get("/sample")
def get_sample() -> dict:
    return {"title": SAMPLE_PROMPT_TITLE, "prompt_text": SAMPLE_PROMPT_TEXT, "content": SAMPLE_ESSAY}


@router.post("/essays", response_model=EssayOut, status_code=202)
def submit_essay(payload: EssayCreate, background: BackgroundTasks, request: Request,
                 session=Depends(get_session)):
    practice = Practice(
        user_id=1,
        prompt_title=payload.prompt_title,
        prompt_text=payload.prompt_text,
        content=payload.content,
        word_count=len(payload.content.split()),
        duration_sec=payload.duration_sec,
    )
    session.add(practice)
    session.commit()
    session.refresh(practice)
    background.add_task(run_grading, practice.id, request.app.state.session_factory)
    return practice


@router.get("/essays", response_model=list[EssayOut])
def list_essays(session=Depends(get_session)):
    return session.scalars(select(Practice).order_by(Practice.created_at.desc())).all()


@router.get("/essays/{practice_id}", response_model=EssayDetail)
def get_essay(practice_id: int, session=Depends(get_session)):
    practice = session.get(Practice, practice_id)
    if practice is None:
        raise HTTPException(status_code=404, detail="练习不存在")
    feedback = FeedbackOut(
        bands=practice.feedback.bands,
        annotations=practice.feedback.annotations,
        rewrite=practice.feedback.rewrite,
        is_mock=practice.feedback.is_mock,
    ) if practice.feedback else None
    errors = session.scalars(
        select(ErrorItem).where(ErrorItem.practice_id == practice_id)
        .order_by(ErrorItem.created_at)).all()
    return EssayDetail(
        **EssayOut.model_validate(practice).model_dump(),
        prompt_text=practice.prompt_text,
        content=practice.content,
        feedback=feedback,
        errors=[ErrorItemOut.model_validate(e) for e in errors],
    )


@router.get("/errors", response_model=list[ErrorItemOut])
def list_errors(session=Depends(get_session)):
    return session.scalars(select(ErrorItem).order_by(ErrorItem.created_at.desc())).all()
