"""词库批量扩充脚本：按雅思话题调用 DeepSeek 生成新词条（含释义/替换链/例句）并入库。

与 generate_vocab.py（补全已有词的缺失字段）不同，本脚本生成**新词**。

用法（在 backend/ 下）：
    uv run python scripts/expand_vocab.py --dry-run            # 只打印扩充计划
    uv run python scripts/expand_vocab.py --topic 艺术 --per-topic 12   # 小规模试跑
    uv run python scripts/expand_vocab.py                      # 全量：25 话题 × 120 词
"""
import argparse
import logging
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openai import OpenAI
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app.config import settings
from app.database import make_session_factory
from app.models import Word
from app.services.llm_json import LLMCallFailed, chat_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# 已有 10 话题（各 20 词）+ 新增 15 话题，目标每话题 120 词
TOPICS = [
    "教育", "科技", "环境", "犯罪", "媒体", "健康", "工作", "城市化", "文化", "全球化",
    "政府", "经济", "交通", "旅游", "家庭", "社会", "艺术", "体育", "饮食", "语言",
    "自然", "住房", "心理", "商业", "人口",
]

SYSTEM = "你是雅思词汇教研专家，为雅思考生编选核心词汇学习材料。只输出 JSON。"

USER_TMPL = """请为雅思话题「{topic}」挑选 {n} 个核心词汇（难度覆盖 band 5.5-7.5，不要中学基础词），并为每个词生成学习材料。
要求：
- text 为单个英文单词（全小写，不含短语、不含空格）
- pos 为词性缩写（n./v./adj./adv. 等）
- meaning：1-2 个核心中文释义，用"；"分隔
- paraphrase_chain：3-5 个由口语到书面递进的英文同义替换
- example_sentence：一句 10-20 词的雅思 Task 2 风格例句，自然使用目标词
- 不要生成以下已收录的词：{exclude}
- 本批侧重角度：{angle}
只输出 JSON：{{"words": [{{"text": "...", "pos": "...", "meaning": "...", "paraphrase_chain": ["..."], "example_sentence": "..."}}]}}"""

ANGLES = [
    "学术书面语词汇", "偏口语和日常的表达用词", "以动词为主", "以名词为主",
    "以形容词和副词为主", "媒体与议论文高频考点词", "较难的 band 7+ 词汇",
    "band 5.5-6.5 中频核心词", "常用于搭配和短语的词", "描述趋势、变化、程度的词",
]

WORD_RE = re.compile(r"^[a-z][a-z\-']{1,39}$")


class WordEntry(BaseModel):
    text: str
    pos: str = ""
    meaning: str = ""
    paraphrase_chain: list[str] = Field(default_factory=list, min_length=2)
    example_sentence: str = ""

    @field_validator("text")
    @classmethod
    def check_text(cls, v: str) -> str:
        v = v.strip().lower()
        if not WORD_RE.match(v):
            raise ValueError(f"not a single word: {v!r}")
        return v


class BatchOut(BaseModel):
    words: list[WordEntry]


def gen_batch(client: OpenAI, topic: str, n: int, exclude: list[str], angle: str) -> list[WordEntry]:
    exclude_str = "、".join(exclude[-80:]) if exclude else "（无）"
    try:
        out = chat_json(client, settings.deepseek_model, SYSTEM,
                        USER_TMPL.format(topic=topic, n=n, exclude=exclude_str, angle=angle),
                        BatchOut, max_tokens=3000, attempts=3, temperature=0.7)
        return out.words
    except LLMCallFailed as exc:
        logger.warning("批次生成失败 topic=%s: %s", topic, exc)
        return []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--topic", help="只扩充指定话题")
    parser.add_argument("--per-topic", type=int, default=120)
    parser.add_argument("--batch-size", type=int, default=12)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--max-passes", type=int, default=3)
    args = parser.parse_args()

    if not settings.deepseek_api_key and not args.dry_run:
        print("未配置 DEEPSEEK_API_KEY，退出")
        sys.exit(1)

    session = make_session_factory(settings.database_url)()
    try:
        existing = session.scalars(select(Word)).all()
        by_topic: dict[str, list[str]] = {}
        seen: set[str] = set()
        for w in existing:
            by_topic.setdefault(w.topic, []).append(w.text)
            seen.add(w.text.lower())

        topics = [args.topic] if args.topic else TOPICS
        plan = {t: max(0, args.per_topic - len(by_topic.get(t, []))) for t in topics}
        print("扩充计划（缺口）:")
        for t, need in plan.items():
            print(f"  {t}: 现有 {len(by_topic.get(t, []))}，需新增 {need}")
        if args.dry_run:
            return

        client = OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url)
        total_new = 0
        for pass_no in range(1, args.max_passes + 1):
            tasks = []
            for t in topics:
                need = args.per_topic - len(by_topic.get(t, []))
                batches = (need + args.batch_size - 1) // args.batch_size
                for i in range(batches):
                    angle = ANGLES[(pass_no + i) % len(ANGLES)]
                    tasks.append((t, args.batch_size, angle))
            if not tasks:
                break
            logger.info("第 %d 轮：%d 个批次", pass_no, len(tasks))
            inserted_this_pass = 0
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                futures = {pool.submit(gen_batch, client, t, n, by_topic.get(t, []), a): t
                           for t, n, a in tasks}
                for fut in as_completed(futures):
                    topic = futures[fut]
                    for entry in fut.result():
                        if entry.text in seen:
                            continue
                        if len(by_topic.setdefault(topic, [])) >= args.per_topic:
                            break
                        session.add(Word(
                            text=entry.text, pos=entry.pos, meaning=entry.meaning,
                            topic=topic, paraphrase_chain=entry.paraphrase_chain,
                            example_sentence=entry.example_sentence))
                        seen.add(entry.text)
                        by_topic[topic].append(entry.text)
                        inserted_this_pass += 1
                    session.commit()
            total_new += inserted_this_pass
            logger.info("第 %d 轮入库 %d 词（累计 %d）", pass_no, inserted_this_pass, total_new)
            if inserted_this_pass == 0:
                break

        print(f"\n完成：新增 {total_new} 词")
        for t in topics:
            print(f"  {t}: {len(by_topic.get(t, []))}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
