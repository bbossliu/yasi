from app.database import Base, make_session_factory
from app.models import AIFeedback, ErrorItem, Practice, SkillMastery, SkillNode, User


def make_db(tmp_path):
    factory = make_session_factory(f"sqlite:///{tmp_path}/test.db")
    engine = factory.kw["bind"]
    Base.metadata.create_all(engine)
    return factory


def test_practice_feedback_error_roundtrip(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    s.add(User(id=1, target_band=6.5))
    s.add(Practice(id=1, user_id=1, prompt_title="t", prompt_text="p", content="hello world",
                   word_count=2, status="done", total_band=6.5))
    s.add(AIFeedback(practice_id=1, bands={"overall": 6.5}, annotations=[], rewrite="rw",
                     model="mock", is_mock=True))
    s.add(ErrorItem(user_id=1, practice_id=1, error_type="时态", context="hello world"))
    s.commit()

    p = s.get(Practice, 1)
    assert p.feedback.bands["overall"] == 6.5
    assert p.feedback.is_mock is True
    errors = s.query(ErrorItem).filter_by(practice_id=1).all()
    assert errors[0].error_type == "时态"


def test_skill_tree(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    parent = SkillNode(module="writing", code="writing.task2", title="Task 2 议论文")
    s.add(parent)
    s.flush()
    child = SkillNode(module="writing", code="writing.task2.tr", title="审题与立场",
                      parent_id=parent.id)
    s.add(child)
    s.add(SkillMastery(user_id=1, node_id=parent.id, status="learned",
                       evidence={"source": "essay_graded"}))
    s.commit()

    assert s.get(SkillMastery, 1).status == "learned"
    assert child.parent_id == parent.id
