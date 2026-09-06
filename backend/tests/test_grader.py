import pytest
from sqlalchemy import select

from app.data.sample import SAMPLE_GRADING
from app.database import Base, make_session_factory
from app.models import AIFeedback, ErrorItem, Practice, SkillMastery, SkillNode, User
from app.services.grader import GradingFailed, LLMGrader, run_grading


def make_db(tmp_path):
    factory = make_session_factory(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(factory.kw["bind"])
    return factory


def seed(factory):
    s = factory()
    s.add(User(id=1))
    s.add(SkillNode(id=1, module="writing", code="writing.task2", title="Task 2"))
    s.add(SkillNode(id=2, module="writing", code="writing.task2.tr", title="审题与立场", parent_id=1))
    s.add(SkillNode(id=3, module="listening", code="listening.s3", title="Section 3"))
    s.add(Practice(id=1, user_id=1, prompt_title="t", prompt_text="p",
                   content="some essay text", word_count=3))
    s.add(Practice(id=2, user_id=1, prompt_title="t2", prompt_text="p2",
                   content="another essay text", word_count=3))
    s.commit()
    s.close()


class FakeGrader:
    model = "fake"
    is_mock = False

    def grade(self, prompt_text, content):
        return SAMPLE_GRADING


class BrokenGrader:
    model = "broken"
    is_mock = False

    def grade(self, prompt_text, content):
        raise GradingFailed("bad json twice")


def test_run_grading_success(tmp_path):
    factory = make_db(tmp_path)
    seed(factory)
    run_grading(1, factory, grader=FakeGrader())

    s = factory()
    p = s.get(Practice, 1)
    assert p.status == "done"
    assert p.total_band == 6.0
    fb = s.scalars(select(AIFeedback).where(AIFeedback.practice_id == 1)).one()
    assert fb.bands["grammar"] == 5.5
    assert fb.is_mock is False
    errors = s.scalars(select(ErrorItem).where(ErrorItem.practice_id == 1)).all()
    assert {e.error_type for e in errors} == {"主谓一致", "词汇搭配", "单复数", "连接词"}
    # 能力点：仅 writing 模块标黄
    mastered = s.scalars(select(SkillMastery)).all()
    assert {m.node_id for m in mastered} == {1, 2}
    assert all(m.status == "learned" for m in mastered)
    s.close()

    # 幂等性：批改另一篇作文（practice 2），标黄不重复
    # 注：AIFeedback.practice_id 有唯一约束，同一 practice 不能重复批改
    run_grading(2, factory, grader=FakeGrader())
    s = factory()
    assert len(s.scalars(select(SkillMastery)).all()) == 2
    s.close()


def test_run_grading_marks_needs_review_on_failure(tmp_path):
    factory = make_db(tmp_path)
    seed(factory)
    run_grading(1, factory, grader=BrokenGrader())

    s = factory()
    assert s.get(Practice, 1).status == "needs_review"
    assert s.scalars(select(AIFeedback)).all() == []
    s.close()


def test_llm_grader_retries_then_raises():
    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise RuntimeError("boom")

    grader = LLMGrader.__new__(LLMGrader)
    grader.client = FakeClient()
    grader.model = "test"
    with pytest.raises(GradingFailed):
        grader.grade("p", "c")
