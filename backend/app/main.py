from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.essays import router as essays_router
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
    finally:
        session.close()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
