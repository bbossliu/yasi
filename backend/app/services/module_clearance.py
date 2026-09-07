from sqlalchemy import select

from app.models import AIFeedback, ErrorItem, Practice, ReviewCard, SkillMastery, SkillNode, Word

TARGET = 6.5


def _recent_done(session, module: str, limit: int) -> list[Practice]:
    return session.scalars(
        select(Practice)
        .where(Practice.user_id == 1, Practice.module == module, Practice.status == "done")
        .order_by(Practice.created_at.desc(), Practice.id.desc()).limit(limit)).all()


def _writing(session) -> tuple[bool, str]:
    essays = _recent_done(session, "writing", 5)
    if len(essays) < 5:
        return False, f"需要最近 5 篇 Task 2（当前 {len(essays)} 篇）"
    if sum(p.total_band for p in essays) / 5 < TARGET:
        return False, "最近 5 篇均分未达 6.5"
    for p in essays:
        for key in ("task_response", "coherence", "lexical", "grammar"):
            if p.feedback and p.feedback.bands.get(key, 0) < 6.0:
                return False, f"存在子分 < 6.0（{key}）"
    return True, "最近 5 篇均分 ≥ 6.5 且子分全部 ≥ 6.0"


def _speaking(session) -> tuple[bool, str]:
    turns = _recent_done(session, "speaking", 20)
    p2 = [p for p in turns if p.prompt_text and len(p.content.split()) > 30]
    topics = {}
    for p in p2:
        if p.total_band is not None:
            topics.setdefault(p.prompt_title, []).append(p)
    qualified = [t for t, ps in topics.items()
                 if any(p.total_band >= TARGET and p.feedback
                        and p.feedback.bands.get("fluency", 0) >= TARGET for p in ps)]
    if len(qualified) >= 3:
        return True, "3 个不同话题 Part 2 均达 6.5 且流利度 ≥ 6.5"
    return False, f"需要 3 个不同话题 Part 2 ≥ 6.5（当前 {len(qualified)} 个）"


def _listening(session) -> tuple[bool, str]:
    dictations = _recent_done(session, "listening", 3)
    if len(dictations) < 3:
        return False, f"需要最近 3 篇精听（当前 {len(dictations)} 篇）"
    if any((p.total_band or 0) < 90 for p in dictations):
        return False, "存在正确率 < 90% 的精听"
    pids = [p.id for p in dictations]
    errors = session.scalars(select(ErrorItem).where(ErrorItem.practice_id.in_(pids))).all()
    if errors:
        non_vocab = [e for e in errors if e.error_type != "听力:词汇"]
        if len(non_vocab) / len(errors) >= 0.2:
            return False, "非词汇类归因占比 ≥ 20%"
    return True, "最近 3 篇精听正确率 ≥ 90% 且归因结构健康"


def _vocab(session) -> tuple[bool, str, float]:
    total = len(session.scalars(select(Word.id)).all())
    if total == 0:
        return False, "词库为空", 0.0
    mastered = len(session.scalars(
        select(ReviewCard.id).where(ReviewCard.reps >= 2,
                                    ReviewCard.interval_days >= 7)).all())
    rate = mastered / total
    if rate >= 0.8:
        return True, f"词库掌握率 {rate:.0%} ≥ 80%", rate
    return False, f"词库掌握率 {rate:.0%} < 80%", rate


def _mastery_rate(session, module: str) -> float:
    node_ids = session.scalars(select(SkillNode.id).where(SkillNode.module == module)).all()
    if not node_ids:
        return 0.0
    verified = len(session.scalars(
        select(SkillMastery.id).where(SkillMastery.node_id.in_(node_ids),
                                      SkillMastery.status == "verified")).all())
    return verified / len(node_ids)


def clearance_summary(session, user_id: int) -> list[dict]:
    result = []
    for module, fn in (("writing", _writing), ("speaking", _speaking),
                       ("listening", _listening)):
        cleared, detail = fn(session)
        result.append({"module": module, "cleared": cleared, "detail": detail,
                       "mastery_rate": round(_mastery_rate(session, module), 2)})
    # 词汇模块无 skill 节点，mastery_rate 用词库卡掌握率
    cleared, detail, rate = _vocab(session)
    result.append({"module": "vocab", "cleared": cleared, "detail": detail,
                   "mastery_rate": round(rate, 2)})
    return result
