from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.database import Base, make_session_factory
from app.main import app
from app.models import AIFeedback, ErrorItem, Practice, ReviewCard, SkillMastery, SkillNode, User, Word
from app.seed import seed_db
from app.seed_rules import seed_mastery_rules
from app.services.exam_scoring import accuracy_to_band, overall_round, vocab_rate_to_band


@pytest.fixture()
def client(tmp_path, monkeypatch):
    factory = make_session_factory(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(factory.kw["bind"])
    s = factory()
    s.add(User(id=1))
    s.commit()
    seed_db(s)
    seed_mastery_rules(s)
    s.close()
    monkeypatch.setattr(app.state, "session_factory", factory)
    return TestClient(app)


def test_scoring_tables():
    assert accuracy_to_band(30) == 4.5
    assert accuracy_to_band(72) == 6.0
    assert accuracy_to_band(96) == 7.5
    assert vocab_rate_to_band(0.4) == 5.0
    assert vocab_rate_to_band(0.97) == 7.0
    # 官方取整
    assert overall_round(6.25) == 6.5
    assert overall_round(6.125) == 6.0
    assert overall_round(6.75) == 7.0
    assert overall_round(6.5) == 6.5


def _make_practice(s, pid, module, band, bands=None):
    s.add(Practice(id=pid, user_id=1, module=module, prompt_title="t", prompt_text="p",
                   content="c", status="done", total_band=band))
    if bands:
        s.add(AIFeedback(practice_id=pid, bands=bands, annotations=[], rewrite="", model="m"))
    s.commit()


def test_mock_exam_flow(client):
    factory = app.state.session_factory
    s = factory()
    _make_practice(s, 1, "writing", 6.5, {"overall": 6.5})
    _make_practice(s, 2, "speaking", 6.0, {"overall": 6.0})
    _make_practice(s, 3, "listening", 90)  # 正确率 90 → 7.0
    for i in range(4):
        s.add(Word(id=i + 1, text=f"w{i}", topic="教育"))
        s.add(ReviewCard(user_id=1, word_id=i + 1, reps=2, interval_days=7,
                         due_at=datetime.now()))
    s.add(ErrorItem(user_id=1, practice_id=1, error_type="时态", context="x"))
    s.commit()
    s.close()

    exam = client.post("/api/mock_exams").json()
    out = client.post(f"/api/mock_exams/{exam['exam_id']}/complete",
                      json={"practice_ids": [1, 2, 3]}).json()
    assert out["scores"] == {"writing": 6.5, "speaking": 6.0, "listening": 7.0, "vocab": 7.0}
    # 均分 6.625 → 6.5
    assert out["predicted_band"] == 6.5
    assert out["report"]["top_errors"][0] == {"type": "时态", "count": 1}
    assert len(out["report"]["weak_nodes"]) > 0  # 全未绿

    latest = client.get("/api/mock_exams/latest").json()
    assert latest["id"] == out["id"]
    assert len(client.get("/api/mock_exams").json()) == 1


def test_complete_requires_four_modules(client):
    exam = client.post("/api/mock_exams").json()
    resp = client.post(f"/api/mock_exams/{exam['exam_id']}/complete",
                       json={"practice_ids": []})
    assert resp.status_code == 422
