import pytest
from fastapi.testclient import TestClient

from app.database import Base, make_session_factory
from app.main import app
from app.models import SkillMastery, SkillNode, User
from app.seed import seed_db
from app.seed_listening import seed_listening_db
from app.seed_rules import seed_mastery_rules
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
    seed_listening_db(s)
    seed_mastery_rules(s)
    s.close()
    monkeypatch.setattr(app.state, "session_factory", factory)
    return TestClient(app)


def test_tree_shape_and_status(client):
    tree = client.get("/api/skills/tree").json()
    modules = {m["module"] for m in tree}
    assert modules == {"writing", "speaking", "listening"}
    writing = next(m for m in tree if m["module"] == "writing")
    assert len(writing["nodes"]) == 20
    assert all(n["status"] == "unseen" for n in writing["nodes"])
    # 叶节点带 can_verify 字段
    assert any("can_verify" in n for n in writing["nodes"])


def test_evaluate_and_eligibility(client):
    # 未学过任何 → 不可模考
    elig = client.get("/api/skills/exam-eligibility").json()
    assert elig["eligible"] is False
    assert elig["missing"]["writing"] == 20

    # 全部标 learned 后 → 可模考
    resp = client.post("/api/skills/evaluate").json()
    assert resp["updated"] == 0  # 没有 learned 节点
    factory = app.state.session_factory
    s = factory()
    for n in s.query(SkillNode).all():
        s.add(SkillMastery(user_id=1, node_id=n.id, status="learned"))
    s.commit()
    s.close()
    elig = client.get("/api/skills/exam-eligibility").json()
    assert elig["eligible"] is True


def test_target_band(client):
    assert client.get("/api/skills/target").json() == {"target_band": 6.5}
    assert client.put("/api/skills/target", json={"target_band": 7.0}).status_code == 200
    assert client.get("/api/skills/target").json() == {"target_band": 7.0}
    assert client.put("/api/skills/target", json={"target_band": 5.5}).status_code == 422
