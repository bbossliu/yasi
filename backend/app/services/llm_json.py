import logging
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMCallFailed(Exception):
    pass


def chat_json(client: OpenAI, model: str, system: str, user: str,
              schema: type[T], max_tokens: int = 8192, attempts: int = 3,
              temperature: float = 0.2) -> T:
    """调 LLM 拿 JSON 并按 Pydantic 校验：容忍未闭合 JSON（补 } 重 parse），失败重试。"""
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
                temperature=temperature,
                max_tokens=max_tokens,
            )
            choice = resp.choices[0]
            raw = choice.message.content or ""
            try:
                return schema.model_validate_json(raw)
            except Exception:
                if raw.rstrip() and not raw.rstrip().endswith("}"):
                    try:
                        return schema.model_validate_json(raw.rstrip() + "}")
                    except Exception:
                        pass
                logger.warning(
                    "invalid llm json: finish_reason=%s usage=%s tail=%r",
                    choice.finish_reason, resp.usage, raw[-100:],
                )
                raise
        except Exception as exc:
            last_error = exc
            logger.warning("llm call attempt %d failed: %s", attempt + 1, exc)
    raise LLMCallFailed(str(last_error))
