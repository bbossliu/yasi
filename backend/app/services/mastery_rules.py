from datetime import datetime, timedelta

from sqlalchemy import select

from app.models import (AIFeedback, ErrorItem, Practice, ReviewCard, SkillMastery,
                        SkillNode, Word)

VOCAB_MASTER_MIN_REPS = 2
VOCAB_MASTER_MIN_INTERVAL = 7


def _recent_practices(session, user_id: int, module: str, window: int) -> list[Practice]:
    return session.scalars(
        select(Practice)
        .where(Practice.user_id == user_id, Practice.module == module,
               Practice.status == "done")
        .order_by(Practice.created_at.desc(), Practice.id.desc())
        .limit(window)).all()


def _rule_no_error_type(session, user_id: int, criteria: dict) -> bool:
    practices = _recent_practices(session, user_id, criteria["module"], criteria["window"])
    if len(practices) < criteria["window"]:
        return False
    pids = [p.id for p in practices]
    hit = session.scalars(
        select(ErrorItem.id).where(
            ErrorItem.practice_id.in_(pids),
            ErrorItem.error_type == criteria["error_type"])).first()
    return hit is None


def _rule_band_avg(session, user_id: int, criteria: dict) -> bool:
    practices = _recent_practices(session, user_id, criteria["module"], criteria["window"])
    if len(practices) < criteria["window"]:
        return False
    scores = []
    for p in practices:
        if not p.feedback:
            return False
        value = p.feedback.bands.get(criteria["band"])
        if value is None:
            return False
        scores.append(value)
    return sum(scores) / len(scores) >= criteria["min"]


def _rule_listening_accuracy(session, user_id: int, criteria: dict) -> bool:
    practices = _recent_practices(session, user_id, "listening", criteria["window"])
    if len(practices) < criteria["window"]:
        return False
    if any((p.total_band or 0) < criteria["min"] for p in practices):
        return False
    error_type = criteria.get("error_type")
    max_ratio = criteria.get("max_ratio")
    if error_type and max_ratio is not None:
        pids = [p.id for p in practices]
        all_errors = session.scalars(
            select(ErrorItem).where(ErrorItem.practice_id.in_(pids))).all()
        if all_errors:
            typed = [e for e in all_errors if e.error_type == error_type]
            if len(typed) / len(all_errors) > max_ratio:
                return False
    return True


def _rule_vocab_mastery_rate(session, user_id: int, criteria: dict) -> bool:
    total = len(session.scalars(select(Word.id)).all())
    if total == 0:
        return False
    mastered = len(session.scalars(
        select(ReviewCard.id).where(
            ReviewCard.user_id == user_id,
            ReviewCard.reps >= VOCAB_MASTER_MIN_REPS,
            ReviewCard.interval_days >= VOCAB_MASTER_MIN_INTERVAL)).all())
    return mastered / total >= criteria["min"]


def evaluate_node(node: SkillNode, session, user_id: int) -> bool:
    """聚合节点绿 = 全部直接子节点绿；叶节点按 criteria 规则。"""
    children = session.scalars(
        select(SkillNode).where(SkillNode.parent_id == node.id)).all()
    if children:
        for child in children:
            m = session.scalars(select(SkillMastery).where(
                SkillMastery.user_id == user_id,
                SkillMastery.node_id == child.id)).first()
            child_green = (m and m.status == "verified") or evaluate_node(child, session, user_id)
            if not child_green:
                return False
        return True
    # 已 verified 的叶节点保持绿
    m = session.scalars(select(SkillMastery).where(
        SkillMastery.user_id == user_id, SkillMastery.node_id == node.id)).first()
    if m and m.status == "verified":
        return True
    criteria = node.criteria or {}
    rule = criteria.get("rule")
    if rule == "no_error_type":
        return _rule_no_error_type(session, user_id, criteria)
    if rule == "band_avg":
        return _rule_band_avg(session, user_id, criteria)
    if rule == "listening_accuracy":
        return _rule_listening_accuracy(session, user_id, criteria)
    if rule == "vocab_mastery_rate":
        return _rule_vocab_mastery_rate(session, user_id, criteria)
    return False


def evaluate_all(session, user_id: int) -> int:
    """把所有 learned 节点中满足规则的提升为 verified。返回提升数。"""
    updated = 0
    masteries = session.scalars(
        select(SkillMastery).where(SkillMastery.user_id == user_id,
                                   SkillMastery.status == "learned")).all()
    for m in masteries:
        node = session.get(SkillNode, m.node_id)
        if node and evaluate_node(node, session, user_id):
            m.status = "verified"
            m.evidence = {**(m.evidence or {}), "verified_at": datetime.now().isoformat()}
            updated += 1
    session.commit()
    return updated
