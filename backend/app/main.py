from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.essays import router as essays_router
from app.api.listening import router as listening_router
from app.api.skills import router as skills_router
from app.api.speaking import router as speaking_router
from app.api.vocab import router as vocab_router
from app.config import settings
from app.database import Base, make_session_factory
from app.models import User

app = FastAPI(title="yasi")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.session_factory = make_session_factory(settings.database_url)
app.include_router(essays_router)
app.include_router(listening_router)
app.include_router(skills_router)
app.include_router(speaking_router)
app.include_router(vocab_router)


@app.on_event("startup")
def init_db() -> None:
    from app import models  # noqa: F401  确保表已注册
    from app.seed import seed_db

    engine = app.state.session_factory.kw["bind"]
    Base.metadata.create_all(engine)
    session = app.state.session_factory()
    try:
        if session.get(User, 1) is None:
            session.add(User(id=1, target_band=6.5))
            session.commit()
        seed_db(session)
        from app.seed_speaking import seed_speaking_db
        seed_speaking_db(session)
        from app.seed_vocab import seed_vocab_db
        seed_vocab_db(session)
        from app.seed_listening import seed_listening_db
        seed_listening_db(session)
        from app.seed_rules import seed_mastery_rules
        seed_mastery_rules(session)
    finally:
        session.close()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
