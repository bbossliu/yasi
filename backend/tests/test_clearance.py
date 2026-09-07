from datetime import datetime

from app.database import Base, make_session_factory
from app.models import (AIFeedback, ErrorItem, Practice, ReviewCard, SkillMastery,
                        SkillNode, User, Word)
from app.services.module_clearance import clearance_summary


def make_db(tmp_path):
    factory = make_session_factory(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(factory.kw["bind"])
    s = factory()
    s.add(User(id=1))
    s.commit()
    s.close()
    return factory


def add_essays(s, bands_list, start_id=100):
    for i, bands in enumerate(bands_list):
        pid = start_id + i
        s.add(Practice(id=pid, user_id=1, module="writing", prompt_title="t",
                       prompt_text="p", content="c", status="done",
                       total_band=bands["overall"]))
        s.add(AIFeedback(practice_id=pid, bands=bands, annotations=[],
                         rewrite="", model="m"))
    s.commit()


def test_writing_clearance(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    good = {"overall": 7.0, "task_response": 7.0, "coherence": 7.0,
            "lexical": 6.5, "grammar": 6.5}
    add_essays(s, [good] * 5)
    summary = {m["module"]: m for m in clearance_summary(s, 1)}
    assert summary["writing"]["cleared"] is True
    assert summary["vocab"]["cleared"] is False  # 无复习记录
    assert summary["listening"]["cleared"] is False

    # 一篇子分低于 6.0 → 不通过
    bad = {"overall": 6.5, "task_response": 6.5, "coherence": 6.5,
           "lexical": 6.5, "grammar": 5.5}
    add_essays(s, [bad], start_id=110)
    s.close()
    s = factory()
    summary = {m["module"]: m for m in clearance_summary(s, 1)}
    assert summary["writing"]["cleared"] is False
    s.close()


def test_listening_clearance_with_attribution_ratio(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    for i in range(3):
        s.add(Practice(id=200 + i, user_id=1, module="listening", prompt_title="t",
                       prompt_text="p", content="c", status="done", total_band=92))
    s.commit()
    summary = {m["module"]: m for m in clearance_summary(s, 1)}
    assert summary["listening"]["cleared"] is True
    # 非词汇归因占比 >= 20% → 不通过
    for i in range(3):
        s.add(ErrorItem(user_id=1, practice_id=200, error_type="听力:连读", context="x"))
    s.add(ErrorItem(user_id=1, practice_id=200, error_type="听力:词汇", context="x"))
    s.commit()
    summary = {m["module"]: m for m in clearance_summary(s, 1)}
    assert summary["listening"]["cleared"] is False
    s.close()


def test_vocab_clearance(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    for i in range(10):
        s.add(Word(id=i + 1, text=f"w{i}", topic="教育"))
    for i in range(8):  # 8/10 = 80% → 通过
        s.add(ReviewCard(user_id=1, word_id=i + 1, reps=2, interval_days=7,
                         due_at=datetime.now()))
    s.commit()
    summary = {m["module"]: m for m in clearance_summary(s, 1)}
    assert summary["vocab"]["cleared"] is True
    assert abs(summary["vocab"]["mastery_rate"] - 0.8) < 0.01
    s.close()
