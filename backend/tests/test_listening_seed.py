from sqlalchemy import select

from app.data.listening_seed import LISTENING_MATERIALS
from app.database import Base, make_session_factory
from app.models import ListeningMat, SkillNode
from app.seed_listening import seed_listening_db


def make_db(tmp_path):
    factory = make_session_factory(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(factory.kw["bind"])
    return factory


def test_materials_shape():
    assert len(LISTENING_MATERIALS) == 6
    sections = [m["section"] for m in LISTENING_MATERIALS]
    assert sections.count(2) == 2 and sections.count(3) == 2 and sections.count(4) == 2
    for m in LISTENING_MATERIALS:
        # 扩写后每篇为真实雅思体量（30-40 句）
        assert 30 <= len(m["sentences"]) <= 40
        assert all(len(s.split()) >= 5 for s in m["sentences"])


def test_seed_listening_idempotent(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    seed_listening_db(s)
    seed_listening_db(s)
    mats = s.scalars(select(ListeningMat)).all()
    assert len(mats) == 6
    assert all(len(m.transcript) >= 8 for m in mats)
    nodes = s.scalars(select(SkillNode).where(SkillNode.code.like("listening.%"))).all()
    assert len(nodes) == 12
    assert all(n.module == "listening" for n in nodes)
    s.close()
