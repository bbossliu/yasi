"""为听力素材生成逐句中文注释（DeepSeek），产物 app/data/listening_zh.json。

按 title 存储 {title: [zh, ...]}，seed_listening 加载时校验句数一致才附加。
可重复跑：已有注释且句数匹配的素材自动跳过。

用法（在 backend/ 下）：
    uv run python scripts/translate_listening.py --dry-run
    uv run python scripts/translate_listening.py
"""
import argparse
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openai import OpenAI
from pydantic import BaseModel

from app.config import settings
from app.seed_listening import ZH_PATH, load_listening_materials
from app.services.llm_json import LLMCallFailed, chat_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SYSTEM = "你是雅思听力教研专家，把英文听力原文逐句翻译成自然、准确的中文。只输出 JSON。"


class ZhOut(BaseModel):
    zh: list[str]


def translate_mat(client: OpenAI, title: str, sentences: list[str]) -> list[str] | None:
    numbered = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(sentences))
    user = f"""以下是雅思听力材料 "{title}" 的 {len(sentences)} 个句子：
{numbered}

请逐句翻译为中文（保持顺序与数量完全一致，共 {len(sentences)} 句）。
只输出 JSON：{{"zh": ["第1句译文", ...]}}"""
    try:
        out = chat_json(client, settings.deepseek_model, SYSTEM, user, ZhOut,
                        max_tokens=4000, attempts=3, temperature=0.2)
    except LLMCallFailed as exc:
        logger.warning("翻译失败 %s: %s", title, exc)
        return None
    if len(out.zh) != len(sentences):
        logger.warning("句数不匹配 %s: 期望 %d，实得 %d", title, len(sentences), len(out.zh))
        return None
    return out.zh


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    zh_map = json.loads(ZH_PATH.read_text(encoding="utf-8")) if ZH_PATH.exists() else {}
    mats = load_listening_materials()
    todo = [m for m in mats
            if not (m["title"] in zh_map and len(zh_map[m["title"]]) == len(m["sentences"]))]
    print(f"待翻译: {len(todo)} / {len(mats)} 篇")
    if args.dry_run:
        for m in todo:
            print(f"  - {m['title']} ({len(m['sentences'])} 句)")
        return
    if not todo:
        return
    if not settings.deepseek_api_key:
        print("未配置 DEEPSEEK_API_KEY，退出")
        sys.exit(1)

    client = OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(translate_mat, client, m["title"], m["sentences"]): m
                for m in todo}
        for fut, m in ((f, futs[f]) for f in futs):
            zh = fut.result()
            if zh:
                zh_map[m["title"]] = zh
                print(f"  ✓ {m['title']} ({len(zh)} 句)")
    ZH_PATH.write_text(json.dumps(zh_map, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"完成：{ZH_PATH} 共 {len(zh_map)} 篇")


if __name__ == "__main__":
    main()
