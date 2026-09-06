from sqlalchemy import select

from app.database import Base, make_session_factory
from app.models import Practice, SpeakingCard, SpeakingSession, User
from app.seed_speaking import seed_speaking_db


def make_db(tmp_path):
    factory = make_session_factory(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(factory.kw["bind"])
    return factory


def test_speaking_session_and_practice_link(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    s.add(User(id=1))
    s.add(SpeakingCard(id=1, part=2, topic="Describe a person", season="2026-09",
                       payload={"cues": ["who", "what", "why"]}))
    s.add(SpeakingSession(id=1, user_id=1, card_id=1, status="active",
                          current_question="Describe a person you admire.", turn_count=0))
    s.add(Practice(id=1, user_id=1, module="speaking", session_id=1,
                   prompt_title="Describe a person", prompt_text="Describe a person you admire.",
                   content="transcript", audio_path="uploads/x.wav", word_count=1))
    s.commit()

    p = s.get(Practice, 1)
    assert p.module == "speaking"
    assert p.session_id == 1
    assert p.audio_path == "uploads/x.wav"
    sess = s.get(SpeakingSession, 1)
    assert sess.card.topic == "Describe a person"


def test_seed_speaking_idempotent(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    seed_speaking_db(s)
    seed_speaking_db(s)  # 第二次不重复
    cards = s.scalars(select(SpeakingCard)).all()
    assert len([c for c in cards if c.part == 1]) == 5
    assert len([c for c in cards if c.part == 2]) == 8
    assert len([c for c in cards if c.part == 3]) == 5
    from app.models import SkillNode
    speaking_nodes = s.scalars(
        select(SkillNode).where(SkillNode.code.like("speaking.%"))).all()
    assert len(speaking_nodes) == 18
    assert all(n.module == "speaking" for n in speaking_nodes)
    s.close()
