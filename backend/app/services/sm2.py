from datetime import datetime, timedelta

from sqlalchemy import select

from app.models import ReviewCard, Word


def get_or_create_card(session, user_id: int, word_id: int) -> ReviewCard:
    card = session.scalars(
        select(ReviewCard).where(
            ReviewCard.user_id == user_id, ReviewCard.word_id == word_id)).first()
    if card is None:
        card = ReviewCard(user_id=user_id, word_id=word_id, due_at=datetime.now())
        session.add(card)
        session.flush()
    return card


def sm2_review(card: ReviewCard, quality: int, now: datetime) -> None:
    """标准 SM-2：quality 0-5（本系统只用 1/3/5）。原地更新卡片。"""
    if quality < 3:
        card.reps = 0
        card.interval_days = 1
    else:
        card.reps += 1
        if card.reps == 1:
            card.interval_days = 1
        elif card.reps == 2:
            card.interval_days = 6
        else:
            card.interval_days = round(card.interval_days * card.ease_factor)
        if quality < 5:  # 满分不加分，只有模糊/勉强才下调 ease
            card.ease_factor = max(
                1.3, card.ease_factor + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    card.due_at = now + timedelta(days=card.interval_days)


def build_review_queue(session, user_id: int, limit: int = 20,
                       now: datetime | None = None) -> tuple[list[dict], int]:
    """到期卡优先（due 升序），不足 limit 用新词（未建卡）补齐。返回 (卡片列表, 到期总数)。"""
    now = now or datetime.now()
    due_cards = session.scalars(
        select(ReviewCard)
        .where(ReviewCard.user_id == user_id, ReviewCard.due_at <= now)
        .order_by(ReviewCard.due_at)).all()
    due_total = len(due_cards)

    queue: list[dict] = []
    word_ids = {c.word_id for c in due_cards}
    words = {w.id: w for w in session.scalars(
        select(Word).where(Word.id.in_(word_ids or {0}))).all()}
    for card in due_cards[:limit]:
        w = words.get(card.word_id)
        if w is None:
            continue  # 词已被删的孤儿卡，跳过避免 500
        queue.append({"word_id": w.id, "text": w.text, "pos": w.pos, "meaning": w.meaning,
                      "paraphrase_chain": w.paraphrase_chain,
                      "example_sentence": w.example_sentence, "is_new": False})

    if len(queue) < limit:
        new_words = session.scalars(
            select(Word)
            .where(~Word.id.in_(
                select(ReviewCard.word_id).where(ReviewCard.user_id == user_id)))
            .order_by(Word.id).limit(limit - len(queue))).all()
        for w in new_words:
            queue.append({"word_id": w.id, "text": w.text, "pos": w.pos, "meaning": w.meaning,
                          "paraphrase_chain": w.paraphrase_chain,
                          "example_sentence": w.example_sentence, "is_new": True})
    return queue, due_total
