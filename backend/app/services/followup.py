import logging

from openai import OpenAI

from app.config import settings
from app.prompt_templates import FOLLOWUP_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)


def generate_followup(topic: str, history: list[dict]) -> str | None:
    """Part 3 追问生成；无 key 或调用失败返回 None（调用方回退预设序列/结束）。"""
    if not settings.deepseek_api_key:
        return None
    history_text = "\n".join(
        f"考官: {h['question']}\n考生: {h['answer']}" for h in history[-4:])
    try:
        client = OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url)
        resp = client.chat.completions.create(
            model=settings.deepseek_model,
            messages=[{"role": "user", "content": FOLLOWUP_PROMPT_TEMPLATE.format(
                topic=topic, history=history_text)}],
            temperature=0.7,
            max_tokens=256,
        )
        question = (resp.choices[0].message.content or "").strip().strip('"')
        return question or None
    except Exception:
        logger.exception("followup generation failed")
        return None
