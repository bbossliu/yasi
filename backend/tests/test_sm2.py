from datetime import datetime, timedelta

from app.database import Base, make_session_factory
from app.models import ReviewCard, User, Word
from app.services.sm2 import build_review_queue, get_or_create_card, sm2_review

NOW = datetime(2026, 9, 7, 12, 0, 0)


def make_db(tmp_path):
    factory = make_session_factory(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(factory.kw["bind"])
    s = factory()
    s.add(User(id=1))
    for i in range(5):
        s.add(Word(id=i + 1, text=f"word{i}", pos="v.", meaning=f"含义{i}", topic="教育",
                   paraphrase_chain=["a", "b", "c"], example_sentence=f"Sentence {i} example."))
    s.commit()
    s.close()
    return factory


def test_sm2_first_pass_and_fail(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    card = get_or_create_card(s, 1, 1)
    assert card.ease_factor == 2.5 and card.reps == 0 and card.interval_days == 1

    sm2_review(card, 5, NOW)  # 第一次认识
    assert card.reps == 1 and card.interval_days == 1
    assert card.due_at == NOW + timedelta(days=1)

    sm2_review(card, 5, NOW)  # 第二次认识 → interval 6
    assert card.reps == 2 and card.interval_days == 6

    sm2_review(card, 5, NOW)  # 第三次 → 6 * 2.5 = 15
    assert card.reps == 3 and card.interval_days == 15

    sm2_review(card, 1, NOW)  # 不认识 → 重置
    assert card.reps == 0 and card.interval_days == 1
    s.close()


def test_sm2_quality3_keeps_progress_but_slower(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    card = get_or_create_card(s, 1, 1)
    sm2_review(card, 5, NOW)
    sm2_review(card, 5, NOW)
    # 两次认识后：reps=2, interval=6, ease=2.5
    sm2_review(card, 3, NOW)  # 模糊：interval 用旧 ease 推进（round(6*2.5)=15），ease 随后下降
    assert card.reps == 3
    assert card.interval_days == 15
    assert abs(card.ease_factor - 2.36) < 0.001  # 2.5 + 0.1 - 2*(0.08+2*0.02)
    s.close()


def test_sm2_ease_floor(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    card = get_or_create_card(s, 1, 1)
    for _ in range(10):
        sm2_review(card, 1, NOW)  # 反复失败 ease 不低于 1.3
    assert card.ease_factor >= 1.3
    s.close()


def test_review_queue_due_then_new(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    # word1 到期卡，word2 未到期卡，word3-5 新词
    c1 = get_or_create_card(s, 1, 1)
    c1.due_at = NOW - timedelta(days=1)
    c2 = get_or_create_card(s, 1, 2)
    c2.due_at = NOW + timedelta(days=3)
    s.commit()

    cards, due_total = build_review_queue(s, 1, limit=3, now=NOW)
    assert due_total == 1
    assert cards[0]["word_id"] == 1 and cards[0]["is_new"] is False
    assert cards[1]["is_new"] is True  # 新词补齐
    assert len(cards) == 3
    s.close()
