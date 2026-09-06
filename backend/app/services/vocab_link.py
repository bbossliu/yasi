import re
from datetime import datetime

from sqlalchemy import select

from app.models import ErrorItem, Word
from app.services.sm2 import get_or_create_card


def link_vocab_errors(session, user_id: int, errors: list[ErrorItem]) -> list[int]:
    """词汇搭配错误 → 上下文命中词库 → 建卡或重置（强制复现）。返回命中的 word_id。"""
    targets = [e for e in errors if e.error_type == "词汇搭配" and e.context]
    if not targets:
        return []
    words = session.scalars(select(Word)).all()
    if not words:
        return []
    hit_ids: list[int] = []
    for error in targets:
        context_lower = error.context.lower()
        for word in words:
            # 词边界前缀匹配：abandon 命中 abandoning/abandoned
            if re.search(rf"\b{re.escape(word.text.lower())}", context_lower):
                card = get_or_create_card(session, user_id, word.id)
                if card.reps > 0 or card.interval_days > 1:
                    card.reps = 0
                    card.interval_days = 1
                card.due_at = datetime.now()
                if word.id not in hit_ids:
                    hit_ids.append(word.id)
    return hit_ids
