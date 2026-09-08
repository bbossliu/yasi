import json
from pathlib import Path

from sqlalchemy import select

from app.data.vocab_seed import VOCAB_WORDS
from app.models import Word

EXPANDED_PATH = Path(__file__).parent / "data" / "vocab_expanded.json"


def seed_vocab_db(session) -> None:
    """幂等写入词库种子（word 表非空即跳过）。

    若存在 app/data/vocab_expanded.json（expand_vocab.py 生成、export_vocab.py 导出的
    扩充词库），一并入库，与内置 200 词按 text 去重。
    """
    if session.scalars(select(Word.id)).first():
        return
    words = list(VOCAB_WORDS)
    if EXPANDED_PATH.exists():
        seen = {w["text"].lower() for w in words}
        expanded = json.loads(EXPANDED_PATH.read_text(encoding="utf-8"))
        words.extend(w for w in expanded if w["text"].lower() not in seen)
    for w in words:
        session.add(Word(
            text=w["text"], pos=w["pos"], meaning=w["meaning"], topic=w["topic"],
            paraphrase_chain=w["paraphrase_chain"], example_sentence=w["example_sentence"],
        ))
    session.commit()
