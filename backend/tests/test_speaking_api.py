import io
import wave

import pytest
from fastapi.testclient import TestClient

from app.database import Base, make_session_factory
from app.main import app
from app.models import User
from app.seed import seed_db
from app.seed_speaking import seed_speaking_db


@pytest.fixture()
def client(tmp_path, monkeypatch):
    factory = make_session_factory(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(factory.kw["bind"])
    s = factory()
    s.add(User(id=1))
    s.commit()
    seed_db(s)
    seed_speaking_db(s)
    s.close()
    monkeypatch.setattr("app.config.settings.deepseek_api_key", "")
    monkeypatch.setattr("app.config.settings.iflytek_app_id", "")
    monkeypatch.setattr("app.config.settings.iflytek_api_secret", "")
    monkeypatch.setattr("app.config.settings.uploads_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr("app.config.settings.tts_cache_dir", str(tmp_path / "tts"))
    # 打桩 TTS，避免测试触发 edge-tts 真实网络调用
    monkeypatch.setattr("app.api.speaking.tts_url_for", lambda text: None)
    monkeypatch.setattr(app.state, "session_factory", factory)
    return TestClient(app)


def make_wav_bytes() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 16000)  # 1 秒静音
    return buf.getvalue()


def test_cards_endpoint(client):
    cards = client.get("/api/speaking/cards", params={"part": 2}).json()
    assert len(cards) == 8
    assert cards[0]["payload"]["cues"]


def test_full_speaking_flow(client):
    cards = client.get("/api/speaking/cards", params={"part": 1}).json()
    sess = client.post("/api/speaking/sessions", json={"card_id": cards[0]["id"]}).json()
    assert sess["part"] == 1
    assert sess["question"]  # 第一问
    assert sess["status"] == "active"

    # 提交两轮（Part 1 该卡 4 问，会话应继续）
    for _ in range(2):
        resp = client.post("/api/speaking/turns",
                           data={"session_id": str(sess["id"])},
                           files={"audio": ("a.wav", make_wav_bytes(), "audio/wav")})
        assert resp.status_code == 202
        pid = resp.json()["practice_id"]
        detail = client.get(f"/api/speaking/turns/{pid}").json()
        assert detail["status"] == "done"
        assert detail["transcript"]
        assert detail["feedback"]["is_mock"] is True
        assert detail["session_done"] is False
        assert detail["next_question"]

    summary = client.post(f"/api/speaking/sessions/{sess['id']}/finish").json()
    assert summary["session_id"] == sess["id"]
    assert len(summary["turns"]) == 2
    assert summary["avg_band"] == 5.5


def test_upload_validation(client):
    cards = client.get("/api/speaking/cards", params={"part": 1}).json()
    sess = client.post("/api/speaking/sessions", json={"card_id": cards[0]["id"]}).json()
    # 非 wav 文件
    resp = client.post("/api/speaking/turns",
                       data={"session_id": str(sess["id"])},
                       files={"audio": ("a.mp3", b"fake", "audio/mpeg")})
    assert resp.status_code == 422


def test_tts_filename_guard(client):
    assert client.get("/api/tts/../etc/passwd").status_code == 404
    assert client.get("/api/tts/nothexname.mp3").status_code == 404
