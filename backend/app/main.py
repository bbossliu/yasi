from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, make_session_factory

app = FastAPI(title="yasi")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.session_factory = make_session_factory(settings.database_url)


@app.on_event("startup")
def init_db() -> None:
    from app import models  # noqa: F401  确保表已注册

    engine = app.state.session_factory.kw["bind"]
    Base.metadata.create_all(engine)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
