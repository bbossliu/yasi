from sqlalchemy import select

from app.database import Base, make_session_factory
from app.models import ErrorItem, ReviewCard, User, Word
from app.services.vocab_link import link_vocab_errors


def make_db(tmp_path):
    factory = make_session_factory(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(factory.kw["bind"])
    s = factory()
    s.add(User(id=1))
    s.add(Word(id=1, text="abandon", pos="v.", meaning="放弃", topic="教育",
               paraphrase_chain=[], example_sentence=""))
    s.add(Word(id=2, text="mitigate", pos="v.", meaning="缓解", topic="环境",
               paraphrase_chain=[], example_sentence=""))
    s.commit()
    s.close()
    return factory


def make_error(error_type, context):
    e = ErrorItem(user_id=1, practice_id=1, error_type=error_type, context=context)
    return e


def test_link_creates_and_resets_cards(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    # 命中 abandon（含词形变化 abandoning 也命中——用前缀匹配）
    hit = link_vocab_errors(s, 1, [make_error("词汇搭配", "People often abandon their plans too early.")])
    assert hit == [1]
    card = s.scalars(select(ReviewCard).where(ReviewCard.word_id == 1)).one()
    assert card.interval_days == 1

    # 重复命中：重置已有卡（先把它改成大间隔）
    card.interval_days = 30
    card.reps = 5
    s.commit()
    hit = link_vocab_errors(s, 1, [make_error("词汇搭配", "Never abandon hope.")])
    assert hit == [1]
    assert card.interval_days == 1 and card.reps == 0

    # 非词汇错误不动
    assert link_vocab_errors(s, 1, [make_error("时态", "abandon abandon")]) == []
    # 未命中词库不动
    assert link_vocab_errors(s, 1, [make_error("词汇搭配", "xyzzy plugh")]) == []
    s.close()


def test_link_no_duplicate_card(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    link_vocab_errors(s, 1, [make_error("词汇搭配", "abandon it"), make_error("词汇搭配", "mitigate risks")])
    s.commit()
    cards = s.scalars(select(ReviewCard)).all()
    assert len(cards) == 2
    s.close()
