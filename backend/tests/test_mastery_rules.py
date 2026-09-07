from datetime import datetime

from sqlalchemy import select

from app.database import Base, make_session_factory
from app.models import (AIFeedback, ErrorItem, Practice, ReviewCard, SkillMastery,
                        SkillNode, User, Word)
from app.seed_rules import RULES, seed_mastery_rules
from app.services.mastery_rules import evaluate_all, evaluate_node


def make_db(tmp_path):
    from app.seed import seed_db
    from app.seed_listening import seed_listening_db
    from app.seed_speaking import seed_speaking_db

    factory = make_session_factory(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(factory.kw["bind"])
    s = factory()
    seed_db(s)            # 写作能力树节点（RULES 依赖这些 code）
    seed_speaking_db(s)   # 口语节点 + 话题卡
    seed_listening_db(s)  # 听力节点
    s.close()
    return factory


def add_practice(s, pid, module, bands):
    s.add(Practice(id=pid, user_id=1, module=module, prompt_title="t", prompt_text="p",
                   content="c", status="done", total_band=bands.get("overall")))
    s.add(AIFeedback(practice_id=pid, bands=bands, annotations=[], rewrite="", model="m"))
    s.flush()


def test_no_error_type_rule(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    s.add(User(id=1))
    seed_mastery_rules(s)
    node = s.scalars(select(SkillNode).where(
        SkillNode.code == "writing.task2.gra.agreement")).one()
    assert node.criteria["rule"] == "no_error_type"

    # 无练习 → False
    assert evaluate_node(node, s, 1) is False
    # 5 篇写作，其中 1 篇有主谓一致错误 → False
    for i in range(5):
        add_practice(s, 10 + i, "writing", {"overall": 6.5, "grammar": 6.5})
    s.add(ErrorItem(user_id=1, practice_id=10, error_type="主谓一致", context="x"))
    s.commit()
    assert evaluate_node(node, s, 1) is False
    # 再来 5 篇干净写作（窗口滑动后）→ True
    for i in range(5):
        add_practice(s, 20 + i, "writing", {"overall": 6.5, "grammar": 6.5})
    s.commit()
    assert evaluate_node(node, s, 1) is True
    s.close()


def test_band_avg_rule(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    s.add(User(id=1))
    seed_mastery_rules(s)
    node = s.scalars(select(SkillNode).where(
        SkillNode.code == "writing.task2.tr.identify")).one()
    assert node.criteria["rule"] == "band_avg"
    for i, score in enumerate([6.5, 6.5, 6.0]):
        add_practice(s, i + 1, "writing",
                     {"overall": 6.5, "task_response": score})
    s.commit()
    assert evaluate_node(node, s, 1) is False  # 均分 6.33 < 6.5
    add_practice(s, 9, "writing", {"overall": 7.0, "task_response": 7.0})
    s.commit()
    # 最近 3 篇 = 6.5, 6.0, 7.0 → 均分 6.5
    assert evaluate_node(node, s, 1) is True
    s.close()


def test_aggregate_node_green_when_all_children_green(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    s.add(User(id=1))
    seed_mastery_rules(s)
    parent = s.scalars(select(SkillNode).where(SkillNode.code == "writing.task2.tr")).one()
    child = s.scalars(select(SkillNode).where(
        SkillNode.code == "writing.task2.tr.identify")).one()
    # 伪造：三个子节点全 verified
    for code in ["writing.task2.tr.identify", "writing.task2.tr.position", "writing.task2.tr.cover"]:
        n = s.scalars(select(SkillNode).where(SkillNode.code == code)).one()
        s.add(SkillMastery(user_id=1, node_id=n.id, status="verified"))
    s.commit()
    assert evaluate_node(parent, s, 1) is True
    assert evaluate_node(child, s, 1) is True  # 已 verified 保持绿
    s.close()


def test_listening_accuracy_rule(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    s.add(User(id=1))
    seed_mastery_rules(s)
    spelling = s.scalars(select(SkillNode).where(
        SkillNode.code == "listening.dictation.spelling")).one()
    assert spelling.criteria["rule"] == "listening_accuracy"

    # 不足 window（仅 1 篇）→ False
    add_practice(s, 1, "listening", {"overall": 92})
    s.commit()
    assert evaluate_node(spelling, s, 1) is False
    # 3 篇精听 92/95/91 全部 ≥ 85 → True
    add_practice(s, 2, "listening", {"overall": 95})
    add_practice(s, 3, "listening", {"overall": 91})
    s.commit()
    assert evaluate_node(spelling, s, 1) is True
    # 其中一篇正确率降到 80 < 85 → False
    p3 = s.get(Practice, 3)
    p3.total_band = 80
    s.commit()
    assert evaluate_node(spelling, s, 1) is False

    # error_type 比率分支：恢复正确率达标后，归因 听力:连读 ×3 + 听力:词汇 ×1
    liaison = s.scalars(select(SkillNode).where(
        SkillNode.code == "listening.dictation.liaison")).one()
    assert liaison.criteria["error_type"] == "听力:连读"
    p3.total_band = 91
    for pid, etype in ((1, "听力:连读"), (2, "听力:连读"), (3, "听力:连读"), (1, "听力:词汇")):
        s.add(ErrorItem(user_id=1, practice_id=pid, error_type=etype, context="x"))
    s.commit()
    assert evaluate_node(liaison, s, 1) is False  # 3/4 = 0.75 > max_ratio 0.2
    s.close()


def test_evaluate_all_only_promotes_learned(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    s.add(User(id=1))
    seed_mastery_rules(s)
    # 一个 learned 节点（条件满足）+ 一个 unseen 节点（条件也满足但不应跳绿）
    ok_node = s.scalars(select(SkillNode).where(
        SkillNode.code == "writing.task2.gra.agreement")).one()
    s.add(SkillMastery(user_id=1, node_id=ok_node.id, status="learned"))
    for i in range(5):
        add_practice(s, i + 1, "writing", {"overall": 7.0, "grammar": 7.0})
    s.commit()
    updated = evaluate_all(s, 1)
    s.commit()
    assert updated == 1
    m = s.scalars(select(SkillMastery).where(SkillMastery.node_id == ok_node.id)).one()
    assert m.status == "verified"
    s.close()
