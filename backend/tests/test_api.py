import time

import pytest
from fastapi.testclient import TestClient

from app.database import Base, make_session_factory
from app.main import app
from app.models import SkillMastery, SkillNode, User
from app.seed import seed_db


@pytest.fixture()
def client(tmp_path, monkeypatch):
    factory = make_session_factory(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(factory.kw["bind"])
    s = factory()
    s.add(User(id=1))
    s.commit()
    seed_db(s)
    s.close()
    # 防止测试机环境变量里恰好有 DEEPSEEK_API_KEY 导致走真实调用
    monkeypatch.setattr("app.config.settings.deepseek_api_key", "")
    monkeypatch.setattr(app.state, "session_factory", factory)
    return TestClient(app)


def test_prompts_and_sample(client):
    prompts = client.get("/api/prompts").json()
    assert len(prompts) >= 4  # 内置 4 题 + 可能的扩充题（writing_prompts_expanded.json）
    sample = client.get("/api/sample").json()
    assert len(sample["content"].split()) >= 200


def test_load_task2_prompts_merges_expanded(tmp_path, monkeypatch):
    import json
    import app.seed as seed_mod

    expanded = [
        {"title": "重复题", "text": seed_mod.TASK2_PROMPTS[0]["text"]},
        {"title": "饮食话题：糖税", "text": "Some countries tax sugary drinks. Is this fair?"},
    ]
    fake = tmp_path / "writing_prompts_expanded.json"
    fake.write_text(json.dumps(expanded, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(seed_mod, "EXPANDED_PROMPTS_PATH", fake)

    prompts = seed_mod.load_task2_prompts()
    assert len(prompts) == 4 + 1
    assert prompts[-1]["title"] == "饮食话题：糖税"


def test_submit_and_poll_result(client):
    resp = client.post("/api/essays", json={
        "prompt_title": "t", "prompt_text": "p",
        "content": "This is a test essay with enough words to pass validation.",
        "duration_sec": 120,
    })
    assert resp.status_code == 202
    pid = resp.json()["id"]
    assert resp.json()["word_count"] == 11

    # TestClient 会同步执行 BackgroundTasks，无需轮询等待
    detail = client.get(f"/api/essays/{pid}").json()
    assert detail["status"] == "done"
    assert detail["total_band"] == 6.0
    assert detail["feedback"]["is_mock"] is True  # 测试环境无 DEEPSEEK_API_KEY
    assert len(detail["feedback"]["annotations"]) >= 3
    assert {e["error_type"] for e in detail["errors"]} == {"主谓一致", "词汇搭配", "单复数", "连接词"}

    errors = client.get("/api/errors").json()
    assert len(errors) == 4

    essays = client.get("/api/essays").json()
    assert essays[0]["id"] == pid


def test_mastery_seeded_and_marked(client):
    client.post("/api/essays", json={
        "prompt_title": "t", "prompt_text": "p", "content": "valid content here"})
    factory = app.state.session_factory
    s = factory()
    nodes = s.query(SkillNode).filter_by(module="writing").count()
    assert nodes >= 15  # 写作分支种子
    masteries = s.query(SkillMastery).filter_by(status="learned").count()
    assert masteries == nodes
    s.close()


def test_validation_and_404(client):
    resp = client.post("/api/essays", json={"prompt_title": "t", "prompt_text": "p", "content": " "})
    assert resp.status_code == 422
    assert client.get("/api/essays/999").status_code == 404
