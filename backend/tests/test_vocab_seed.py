from sqlalchemy import select

from app.data.vocab_seed import VOCAB_WORDS
from app.database import Base, make_session_factory
from app.models import Word
from app.seed_vocab import seed_vocab_db


def make_db(tmp_path):
    factory = make_session_factory(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(factory.kw["bind"])
    return factory


def test_vocab_seed_data_shape():
    assert len(VOCAB_WORDS) == 200
    topics = {w["topic"] for w in VOCAB_WORDS}
    assert len(topics) == 10
    for w in VOCAB_WORDS:
        assert w["text"] and w["meaning"] and w["pos"]
        assert len(w["paraphrase_chain"]) >= 3
        assert len(w["example_sentence"].split()) >= 6
    # 词文本唯一
    texts = [w["text"] for w in VOCAB_WORDS]
    assert len(set(texts)) == 200


def test_seed_vocab_idempotent(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    seed_vocab_db(s)
    seed_vocab_db(s)
    words = s.scalars(select(Word)).all()
    assert len(words) == 200
    w = next(w for w in words if w.text == "abandon")
    assert w.meaning == "放弃；抛弃"
    assert "give up" in w.paraphrase_chain
    s.close()


def test_seed_loads_expanded_json(tmp_path, monkeypatch):
    import json
    import app.seed_vocab as seed_mod

    expanded = [
        {"text": "abandon", "pos": "v.", "meaning": "重复词应被跳过", "topic": "教育",
         "paraphrase_chain": ["x", "y"], "example_sentence": "dup."},
        {"text": "cumulative", "pos": "adj.", "meaning": "累积的", "topic": "经济",
         "paraphrase_chain": ["adding up", "accumulating", "aggregate"],
         "example_sentence": "The cumulative effect of pollution is severe."},
    ]
    fake = tmp_path / "vocab_expanded.json"
    fake.write_text(json.dumps(expanded, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(seed_mod, "EXPANDED_PATH", fake)

    factory = make_db(tmp_path)
    s = factory()
    seed_vocab_db(s)
    words = s.scalars(select(Word)).all()
    assert len(words) == 201  # 200 + 1（重复的 abandon 被跳过）
    w = next(w for w in words if w.text == "cumulative")
    assert w.topic == "经济"
    # 内置 abandon 释义未被扩充文件覆盖
    assert next(w for w in words if w.text == "abandon").meaning == "放弃；抛弃"
    s.close()
