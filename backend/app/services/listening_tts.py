import asyncio
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

VOICE = "en-GB-LibbyNeural"


def audio_path_for(mat_id: int, idx: int) -> Path:
    return Path(settings.listening_audio_dir) / str(mat_id) / f"{idx}.mp3"


def audio_ready_count(mat_id: int, total: int) -> int:
    return sum(1 for i in range(total) if audio_path_for(mat_id, i).exists())


def generate_audio_batch(mat_id: int, sentences: list[str]) -> None:
    """逐句生成（后台任务用）。单句失败跳过，不影响其他句。"""
    import edge_tts

    for idx, sentence in enumerate(sentences):
        path = audio_path_for(mat_id, idx)
        if path.exists():
            continue
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            asyncio.run(edge_tts.Communicate(sentence, VOICE).save(str(path)))
        except Exception:
            logger.warning("listening tts failed: mat %s idx %s", mat_id, idx, exc_info=True)
