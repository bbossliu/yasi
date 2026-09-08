"""把当前数据库 word 表导出为 app/data/vocab_expanded.json（随仓库分发的扩充词库）。

用法（在 backend/ 下，通常在 expand_vocab.py 跑完后执行）：
    uv run python scripts/export_vocab.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.config import settings
from app.database import make_session_factory
from app.models import Word

OUT = Path(__file__).resolve().parent.parent / "app" / "data" / "vocab_expanded.json"


def main() -> None:
    session = make_session_factory(settings.database_url)()
    try:
        words = session.scalars(select(Word).order_by(Word.topic, Word.id)).all()
        data = [{
            "text": w.text, "pos": w.pos, "meaning": w.meaning, "topic": w.topic,
            "paraphrase_chain": w.paraphrase_chain, "example_sentence": w.example_sentence,
        } for w in words]
        OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"导出 {len(data)} 词 → {OUT}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
