"""练习内容扩充脚本：用 DeepSeek 批量生成写作题 / 口语话题卡 / 听力素材。

产物分两份：
- app/data/*_expanded.json —— 随仓库分发，全新部署时由 seed_* 合并入库/出题
- 当前开发库（yasi.db）—— 口语卡与听力素材直接插入（按 topic/title 去重，可重复跑）

用法（在 backend/ 下）：
    uv run python scripts/expand_content.py --dry-run
    uv run python scripts/expand_content.py                  # 三类全扩
    uv run python scripts/expand_content.py --only listening
"""
import argparse
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openai import OpenAI
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app.config import settings
from app.database import make_session_factory
from app.models import ListeningMat, SpeakingCard
from app.seed import load_task2_prompts
from app.services.llm_json import LLMCallFailed, chat_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATA = Path(__file__).resolve().parent.parent / "app" / "data"
SYSTEM = "你是雅思教研专家，编写贴近真实雅思考试的练习材料。只输出 JSON。"


class PromptItem(BaseModel):
    title: str
    text: str


class PromptBatch(BaseModel):
    prompts: list[PromptItem]


class CardItem(BaseModel):
    part: int
    topic: str
    payload: dict

    @field_validator("payload")
    @classmethod
    def check_payload(cls, v: dict, info) -> dict:
        return v


class CardBatch(BaseModel):
    cards: list[CardItem]


class MatItem(BaseModel):
    title: str
    section: int
    sentences: list[str] = Field(min_length=20)


class MatBatch(BaseModel):
    materials: list[MatItem]


def merge_json(path: Path, new_items: list[dict], key: str) -> list[dict]:
    """读已有 JSON，合并新项（按 key 去重），写回，返回全量。"""
    items = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    seen = {i[key] for i in items}
    added = 0
    for i in new_items:
        if i[key] not in seen:
            items.append(i)
            seen.add(i[key])
            added += 1
    path.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    logger.info("%s: 新增 %d，文件累计 %d", path.name, added, len(items))
    return items


def expand_writing(client: OpenAI, n: int = 26) -> list[dict]:
    existing = "；".join(p["title"] for p in load_task2_prompts())
    user = f"""请编写 {n} 道雅思 Writing Task 2 真题风格题目。
要求：
- 话题覆盖：教育、科技、环境、犯罪、媒体、健康、工作、城市化、文化、全球化、政府、经济、交通、旅游、家庭、社会、艺术、饮食、语言、人口（尽量均匀分布）
- 题型混合：观点类(agree/disagree)、讨论双方(discuss both views)、利弊(advantages/disadvantages)、报告类(causes/solutions)
- title 格式："话题：简短中文名"，如 "科技话题：远程办公"
- text 为英文题目原文，1-3 句，结尾必须是标准指令句（如 "To what extent do you agree or disagree?"）
- 不要与以下已有题目重复：{existing}
只输出 JSON：{{"prompts": [{{"title": "...", "text": "..."}}]}}"""
    out = chat_json(client, settings.deepseek_model, SYSTEM, user, PromptBatch,
                    max_tokens=6000, temperature=0.7)
    return [p.model_dump() for p in out.prompts]


def expand_speaking(client: OpenAI) -> list[dict]:
    user = """请编写雅思口语当季话题卡，共 18 张：
- Part 1（6 张）：日常话题（如 Hometown、Music、Sports、Food、Reading、Shopping 等，避开 Home/Work/Reading/Weather/Technology），每张 4 个英文问题
- Part 2（8 张）：Cue Card，topic 为 "Describe ..." 句式，payload.cues 为 4 个要点（前 3 个为小写短语，第 4 个以 "and explain" 开头）
- Part 3（4 张）：深度讨论话题，每张 3 个英文问题
只输出 JSON：{"cards": [{"part": 1, "topic": "...", "payload": {"questions": [...]}} 或 {"part": 2, "topic": "...", "payload": {"cues": [...]}}]}"""
    out = chat_json(client, settings.deepseek_model, SYSTEM, user, CardBatch,
                    max_tokens=6000, temperature=0.7)
    cards = []
    for c in out.cards:
        if c.part == 2:
            cues = c.payload.get("cues") or []
            if len(cues) < 3:
                continue
            cards.append({"part": 2, "topic": c.topic, "payload": {"cues": cues}})
        elif c.part in (1, 3):
            qs = c.payload.get("questions") or []
            if len(qs) < 3:
                continue
            cards.append({"part": c.part, "topic": c.topic, "payload": {"questions": qs}})
    return cards


LISTENING_SPEC = {
    2: "校园/生活设施介绍独白（如图书馆、健身房、住宿），口语化、含数字与地名",
    3: "师生讨论学术任务的对话（如论文选题、小组项目、实验安排），2 人交替发言",
    4: "学术讲座独白（如环境、考古、心理、商业主题），书面学术英语",
}


def gen_listening_mat(client: OpenAI, section: int, idx: int) -> dict | None:
    user = f"""请编写一篇雅思听力 Section {section} 的原文脚本：{LISTENING_SPEC[section]}。
要求：
- 30-40 个句子，每句 8-25 词，贴近真实考试语速与衔接
- 自然包含数字、时间、价格、人名地名等考点细节
- title 为英文小标题（如 "Campus Facilities Tour"）
只输出 JSON：{{"materials": [{{"title": "...", "section": {section}, "sentences": ["..."]}}]}}"""
    try:
        out = chat_json(client, settings.deepseek_model, SYSTEM, user, MatBatch,
                        max_tokens=4000, temperature=0.8)
    except LLMCallFailed as exc:
        logger.warning("听力素材生成失败 section=%d idx=%d: %s", section, idx, exc)
        return None
    if not out.materials:
        return None
    m = out.materials[0]
    return {"title": m.title, "section": section, "sentences": m.sentences}


def expand_listening(client: OpenAI, per_section: int = 2) -> list[dict]:
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = [pool.submit(gen_listening_mat, client, s, i)
                for s in (2, 3, 4) for i in range(per_section)]
        return [m for f in futs if (m := f.result())]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", choices=["writing", "speaking", "listening"])
    args = parser.parse_args()
    if args.dry_run:
        print("将扩充：写作题 +26、口语卡 +18、听力素材 +6（S2/S3/S4 各 2）")
        return
    if not settings.deepseek_api_key:
        print("未配置 DEEPSEEK_API_KEY，退出")
        sys.exit(1)

    client = OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url)
    targets = [args.only] if args.only else ["writing", "speaking", "listening"]

    if "writing" in targets:
        prompts = expand_writing(client)
        merge_json(DATA / "writing_prompts_expanded.json", prompts, "text")

    session = make_session_factory(settings.database_url)()
    try:
        if "speaking" in targets:
            cards = expand_speaking(client)
            existing = set(session.scalars(select(SpeakingCard.topic)).all())
            for c in cards:
                if c["topic"] not in existing:
                    session.add(SpeakingCard(part=c["part"], topic=c["topic"],
                                             season="2026-09", payload=c["payload"]))
            session.commit()
            merge_json(DATA / "speaking_cards_expanded.json", cards, "topic")
            logger.info("口语卡入库完成")

        if "listening" in targets:
            mats = expand_listening(client)
            existing = set(session.scalars(select(ListeningMat.title)).all())
            for m in mats:
                if m["title"] not in existing:
                    session.add(ListeningMat(title=m["title"], transcript=m["sentences"],
                                             audio_path=f"s{m['section']}"))
            session.commit()
            merge_json(DATA / "listening_expanded.json", mats, "title")
            logger.info("听力素材入库完成")
    finally:
        session.close()


if __name__ == "__main__":
    main()
