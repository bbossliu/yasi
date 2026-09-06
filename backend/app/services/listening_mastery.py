from sqlalchemy import select

from app.models import SkillMastery, SkillNode


def mark_listening_learned(session, user_id: int) -> int:
    node_ids = session.scalars(select(SkillNode.id).where(SkillNode.module == "listening")).all()
    existing = set(session.scalars(
        select(SkillMastery.node_id).where(SkillMastery.user_id == user_id)).all())
    added = 0
    for node_id in node_ids:
        if node_id not in existing:
            session.add(SkillMastery(user_id=user_id, node_id=node_id, status="learned",
                                     evidence={"source": "dictation_submitted"}))
            added += 1
    return added
