import io
import wave

import pytest
from fastapi.testclient import TestClient

from app.database import Base, make_session_factory
from app.main import app
from app.models import ErrorItem, Practice, User
from app.seed_listening import seed_listening_db


@pytest.fixture()
def client(tmp_path, monkeypatch):
    factory = make_session_factory(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(factory.kw["bind"])
    s = factory()
    s.add(User(id=1))
    s.commit()
    seed_listening_db(s)
    s.close()
    monkeypatch.setattr("app.config.settings.deepseek_api_key", "")
    monkeypatch.setattr("app.config.settings.iflytek_app_id", "")
    monkeypatch.setattr("app.config.settings.iflytek_api_secret", "")
    monkeypatch.setattr("app.config.settings.listening_audio_dir", str(tmp_path / "la"))
    monkeypatch.setattr("app.config.settings.uploads_dir", str(tmp_path / "up"))
    monkeypatch.setattr(app.state, "session_factory", factory)
    return TestClient(app)


def make_wav_bytes() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 16000)
    return buf.getvalue()


def test_materials_and_detail(client):
    mats = client.get("/api/listening/materials").json()
    assert len(mats) == 6
    assert mats[0]["sentence_count"] >= 8
    assert mats[0]["ready_count"] == 0  # 测试环境不生成音频

    detail = client.get(f"/api/listening/materials/{mats[0]['id']}").json()
    assert len(detail["sentences"]) == mats[0]["sentence_count"]
    assert client.get("/api/listening/materials/999").status_code == 404
    # 音频不存在 → 404
    assert client.get(f"/api/listening/audio/{mats[0]['id']}/0.mp3").status_code == 404


def test_dictation_flow_and_attribution(client):
    mats = client.get("/api/listening/materials").json()
    mat = client.get(f"/api/listening/materials/{mats[0]['id']}").json()
    answers = list(mat["sentences"])  # 先全对
    answers[0] = "wrong words here"
    resp = client.post("/api/listening/dictation", json={
        "material_id": mat["id"], "answers": answers})
    assert resp.status_code == 200
    body = resp.json()
    total = len(mat["sentences"])
    assert body["accuracy"] == round(100 * (total - 1) / total)
    assert body["per_sentence"][0]["correct"] is False
    assert body["per_sentence"][1]["correct"] is True
    assert body["per_sentence"][0]["diff"]["tokens"]

    # 归因
    resp = client.post("/api/listening/attribution", json={
        "practice_id": body["practice_id"], "sentence_index": 0, "reason": "连读"})
    assert resp.status_code == 201
    # 非法归因
    assert client.post("/api/listening/attribution", json={
        "practice_id": body["practice_id"], "sentence_index": 0, "reason": "粗心"}).status_code == 422
    # practice 404
    assert client.post("/api/listening/attribution", json={
        "practice_id": 999, "sentence_index": 0, "reason": "连读"}).status_code == 404


def test_shadowing_mock(client):
    mats = client.get("/api/listening/materials").json()
    resp = client.post("/api/listening/shadowing",
                       data={"material_id": str(mats[0]["id"])},
                       files={"audio": ("a.wav", make_wav_bytes(), "audio/wav")})
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_mock"] is True
    assert body["transcript"]
    assert "tokens" in body["diff"]
