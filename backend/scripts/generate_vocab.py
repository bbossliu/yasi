"""词库扩充脚本：为 word 表中缺失例句或替换链的词批量生成内容（DeepSeek）。

用法（在 backend/ 下）：
    uv run python scripts/generate_vocab.py --dry-run   # 只列出待处理词，不调 API
    uv run python scripts/generate_vocab.py             # 真实生成并入库
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openai import OpenAI

from app.config import settings
from app.database import make_session_factory
from app.models import Word

PROMPT = """为雅思核心词 "{word}"（{pos}，话题：{topic}）生成学习材料，只输出 JSON：
{{"meaning": "1-2个核心中文释义", "paraphrase_chain": ["3-5个由口语到书面递进的同义替换"],
  "example_sentence": "一句10-20词的雅思Task 2风格真题语境例句（须自然使用目标词）"}}"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    factory = make_session_factory(settings.database_url)
    session = factory()
    try:
        from sqlalchemy import select
        # JSON 列不支持与 [] 直接比较（SQLite 下不可靠），在 Python 侧过滤
        incomplete = [w for w in session.scalars(select(Word)).all()
                      if not w.example_sentence or not w.paraphrase_chain]
        print(f"待补全词条: {len(incomplete)}")
        if args.dry_run:
            for w in incomplete:
                print(f"  - {w.text} ({w.topic})")
            return
        if not settings.deepseek_api_key:
            print("未配置 DEEPSEEK_API_KEY，退出")
            sys.exit(1)
        client = OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url)
        for w in incomplete:
            resp = client.chat.completions.create(
                model=settings.deepseek_model,
                messages=[{"role": "user", "content": PROMPT.format(
                    word=w.text, pos=w.pos, topic=w.topic)}],
                response_format={"type": "json_object"}, temperature=0.3, max_tokens=512)
            data = json.loads(resp.choices[0].message.content)
            w.meaning = w.meaning or data.get("meaning", "")
            w.paraphrase_chain = w.paraphrase_chain or data.get("paraphrase_chain", [])
            w.example_sentence = w.example_sentence or data.get("example_sentence", "")
            session.commit()
            print(f"  ✓ {w.text}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
