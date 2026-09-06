import asyncio
import hashlib
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

VOICE = "en-GB-LibbyNeural"


def tts_url_for(text: str) -> str | None:
    """生成（或复用缓存的）提问音频，返回 /api/tts/{name}.mp3；失败返回 None。"""
    name = hashlib.md5(text.encode()).hexdigest()[:16]
    cache_dir = Path(settings.tts_cache_dir)
    path = cache_dir / f"{name}.mp3"
    if path.exists():
        return f"/api/tts/{name}.mp3"
    try:
        import edge_tts

        cache_dir.mkdir(parents=True, exist_ok=True)
        asyncio.run(edge_tts.Communicate(text, VOICE).save(str(path)))
        return f"/api/tts/{name}.mp3"
    except Exception:
        logger.warning("tts generation failed for %r", text[:50], exc_info=True)
        return None
