from sqlalchemy import select

from app.data.vocab_seed import VOCAB_WORDS
from app.models import Word


def seed_vocab_db(session) -> None:
    """幂等写入词库种子（word 表非空即跳过）。"""
    if session.scalars(select(Word.id)).first():
        return
    for w in VOCAB_WORDS:
        session.add(Word(
            text=w["text"], pos=w["pos"], meaning=w["meaning"], topic=w["topic"],
            paraphrase_chain=w["paraphrase_chain"], example_sentence=w["example_sentence"],
        ))
    session.commit()
