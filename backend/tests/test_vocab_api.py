from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.database import Base, make_session_factory
from app.main import app
from app.models import ReviewCard, User, Word
from app.seed_vocab import seed_vocab_db


@pytest.fixture()
def client(tmp_path, monkeypatch):
    factory = make_session_factory(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(factory.kw["bind"])
    s = factory()
    s.add(User(id=1))
    s.commit()
    seed_vocab_db(s)
    # 造 3 张卡：word1 已掌握、word2 到期、word3 未到期
    s.add(ReviewCard(user_id=1, word_id=1, reps=3, interval_days=15,
                     due_at=datetime.now() + timedelta(days=10)))
    s.add(ReviewCard(user_id=1, word_id=2, reps=1, interval_days=1,
                     due_at=datetime.now() - timedelta(hours=1)))
    s.add(ReviewCard(user_id=1, word_id=3, reps=1, interval_days=6,
                     due_at=datetime.now() + timedelta(days=3)))
    s.commit()
    s.close()
    monkeypatch.setattr(app.state, "session_factory", factory)
    return TestClient(app)


def test_topics_aggregate(client):
    topics = client.get("/api/vocab/topics").json()
    assert len(topics) == 10
    edu = next(t for t in topics if t["topic"] == "教育")
    assert edu["word_count"] == 20
    assert edu["mastered_count"] + edu["due_count"] <= 20
    # 全部话题合计：掌握 1（word1 reps3/interval15）
    assert sum(t["mastered_count"] for t in topics) == 1
    assert sum(t["due_count"] for t in topics) == 1


def test_words_with_review_state(client):
    words = client.get("/api/vocab/words", params={"topic": "教育"}).json()
    assert len(words) == 20
    w1 = next(w for w in words if w["id"] == 1)
    assert w1["reps"] == 3
    assert w1["due_at"] is not None
    assert all(len(w["paraphrase_chain"]) >= 3 for w in words)


def test_review_queue_and_submit(client):
    queue = client.get("/api/vocab/review/queue", params={"limit": 5}).json()
    assert queue["due_total"] == 1
    assert len(queue["cards"]) == 5
    assert queue["cards"][0]["word_id"] == 2  # 到期卡优先
    assert queue["cards"][0]["is_new"] is False
    assert queue["cards"][1]["is_new"] is True

    resp = client.post("/api/vocab/review/2", json={"quality": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["interval_days"] == 6  # reps 1→2

    # 提交后 word2 不再到期
    queue2 = client.get("/api/vocab/review/queue", params={"limit": 5}).json()
    assert queue2["due_total"] == 0

    assert client.post("/api/vocab/review/2", json={"quality": 4}).status_code == 422
    assert client.post("/api/vocab/review/9999", json={"quality": 5}).status_code == 404


def test_forecast(client):
    forecast = client.get("/api/vocab/forecast").json()
    assert len(forecast) == 7
    assert sum(f["count"] for f in forecast) == 2  # word1(+10天不在内) word3(+3天)
    day3 = forecast[3]
    assert day3["count"] == 1
