from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.models import AIFeedback, ErrorItem, ListeningMat, Practice
from app.schemas import (AttributionSubmit, DictationResultOut, DictationSubmit,
                         MatDetailOut, MatListOut)
from app.services.asr import build_transcriber
from app.services.dictation import diff_words, score_dictation
from app.services.listening_mastery import mark_listening_learned
from app.services.listening_tts import (audio_path_for, audio_ready_count,
                                        generate_audio_batch)

router = APIRouter(prefix="/api")


def get_session(request: Request):
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def _section_of(mat: ListeningMat) -> int:
    return int(mat.audio_path.strip("s")) if mat.audio_path else 0


@router.get("/listening/materials", response_model=list[MatListOut])
def list_materials(session=Depends(get_session)):
    mats = session.scalars(select(ListeningMat).order_by(ListeningMat.id)).all()
    return [MatListOut(
        id=m.id, title=m.title, section=_section_of(m),
        sentence_count=len(m.transcript),
        ready_count=audio_ready_count(m.id, len(m.transcript)),
    ) for m in mats]


@router.get("/listening/materials/{mat_id}", response_model=MatDetailOut)
def get_material(mat_id: int, session=Depends(get_session)):
    mat = session.get(ListeningMat, mat_id)
    if mat is None:
        raise HTTPException(status_code=404, detail="素材不存在")
    return MatDetailOut(
        id=mat.id, title=mat.title, section=_section_of(mat),
        sentences=mat.transcript, sentences_zh=mat.transcript_zh,
        ready_count=audio_ready_count(mat.id, len(mat.transcript)),
    )


@router.post("/listening/materials/{mat_id}/audio")
def generate_audio(mat_id: int, background: BackgroundTasks, session=Depends(get_session)):
    mat = session.get(ListeningMat, mat_id)
    if mat is None:
        raise HTTPException(status_code=404, detail="素材不存在")
    total = len(mat.transcript)
    ready = audio_ready_count(mat_id, total)
    if ready < total:
        background.add_task(generate_audio_batch, mat_id, mat.transcript)
        return {"status": "started", "ready_count": ready, "total": total}
    return {"status": "ready", "ready_count": ready, "total": total}


@router.get("/listening/audio/{mat_id}/{idx}.mp3")
def get_audio(mat_id: int, idx: int):
    path = audio_path_for(mat_id, idx)
    if not path.exists():
        raise HTTPException(status_code=404, detail="音频不存在")
    return FileResponse(path, media_type="audio/mpeg")


@router.post("/listening/dictation", response_model=DictationResultOut)
def submit_dictation(payload: DictationSubmit, session=Depends(get_session)):
    mat = session.get(ListeningMat, payload.material_id)
    if mat is None:
        raise HTTPException(status_code=404, detail="素材不存在")
    result = score_dictation(mat.transcript, payload.answers)
    practice = Practice(
        user_id=1, module="listening", prompt_title=mat.title,
        prompt_text=f"Section {_section_of(mat)} 精听听写",
        content="\n".join(payload.answers),
        word_count=sum(len(a.split()) for a in payload.answers),
        status="done", total_band=result["accuracy"],
    )
    session.add(practice)
    session.flush()
    session.add(AIFeedback(
        practice_id=practice.id,
        bands={"accuracy": result["accuracy"]},
        annotations=[{"sentence_index": i, "diff": ps["diff"], "correct": ps["correct"]}
                     for i, ps in enumerate(result["per_sentence"])],
        rewrite="", model="dictation", is_mock=False,
    ))
    mark_listening_learned(session, 1)
    session.commit()
    return DictationResultOut(
        practice_id=practice.id, accuracy=result["accuracy"],
        per_sentence=result["per_sentence"],
    )


@router.post("/listening/shadowing")
def shadowing(material_id: int = Form(...), audio: UploadFile = File(...),
              session=Depends(get_session)):
    mat = session.get(ListeningMat, material_id)
    if mat is None:
        raise HTTPException(status_code=404, detail="素材不存在")
    import uuid
    from pathlib import Path

    from app.config import settings

    data = audio.file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="音频超过 5MB 上限")
    uploads = Path(settings.uploads_dir)
    uploads.mkdir(parents=True, exist_ok=True)
    path = uploads / f"shadow-{uuid.uuid4().hex}.wav"
    path.write_bytes(data)

    transcriber = build_transcriber()
    try:
        result = transcriber.transcribe(str(path))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"转写失败: {exc}")
    reference = " ".join(mat.transcript)
    return {
        "transcript": result.text,
        "diff": diff_words(reference, result.text),
        "is_mock": transcriber.is_mock,
    }


@router.post("/listening/attribution", status_code=201)
def attribute(payload: AttributionSubmit, session=Depends(get_session)):
    practice = session.get(Practice, payload.practice_id)
    if practice is None or practice.module != "listening":
        raise HTTPException(status_code=404, detail="练习不存在")
    item = ErrorItem(
        user_id=1, practice_id=practice.id,
        error_type=f"听力:{payload.reason}",
        context=f"第 {payload.sentence_index + 1} 句",
    )
    session.add(item)
    session.commit()
    return {"id": item.id}
