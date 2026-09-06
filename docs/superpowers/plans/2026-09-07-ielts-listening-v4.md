# 雅思 V4 听力精听 + 仪表盘 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 V4——听力精听（逐句字幕/单句循环/变速/听写词级 diff/跟读 ASR 比对/四选一错题归因）+ 历史页按模块成绩曲线 + 仪表盘听力卡。

**Architecture:** 复用 `listening_mat` 表（transcript = 句子数组）与 V2 的 ASR 适配器。音频用 edge-tts **逐句**生成（单句循环不需要时间戳）。听写比对用 rapidfuzz 词级 Levenshtein opcodes。听写练习落 `practice(module="listening", total_band=正确率0-100)` + `ai_feedback(bands={"accuracy": x}, annotations=逐句diff)`。

**Tech Stack:** 同 V1-V3 + 新增 `rapidfuzz`（词级 diff）。

**上游规格:** `docs/superpowers/specs/2026-09-07-ielts-listening-v4-design.md`

## Global Constraints

- 沿用 V1-V3 全部约束（uv/pytest/tmp SQLite/中文 Conventional Commits/端口 8022/unset 代理/Node v22/测试 monkeypatch 掉所有外部 key）
- 正确率 = 全对句数/总句数 ×100 取整；`practice.total_band` 存 0-100 整数；历史页听力曲线 y 轴 0-100
- 错题归因 error_type 取值：`听力:连读 / 听力:词汇 / 听力:口音 / 听力:注意力`（其他值 422）
- 音频逐句生成，`backend/listening_audio/` gitignored；edge-tts 失败降级"音频不可用"，不阻塞文本练习
- 听力能力树节点 12 个，`listening.` 前缀，seed 幂等；听写提交后标黄（`mark_listening_learned`）
- 不打包任何剑桥真题素材

---

### Task 1: 听写比对服务（rapidfuzz 词级 diff）

**Files:**
- Modify: `backend/pyproject.toml`（加 rapidfuzz）
- Create: `backend/app/services/dictation.py`
- Test: `backend/tests/test_dictation.py`

**Interfaces:**
- Produces:
  - `diff_words(reference: str, hypothesis: str) -> dict`：`{"tokens": [{"type": "ok|missing|wrong|extra", "ref": str, "hyp": str}], "correct": bool}`
  - `score_dictation(sentences: list[str], answers: list[str]) -> dict`：`{"accuracy": int(0-100), "per_sentence": [{"diff": <diff_words 结果>, "correct": bool}]}`；answers 数量不足视为空串
  - Task 3 的 API 消费这两个函数

- [ ] **Step 1: 写失败测试**

`backend/tests/test_dictation.py`:
```python
from app.services.dictation import diff_words, score_dictation


def test_diff_all_correct():
    result = diff_words("An hour and a half.", "an hour and a half")
    assert result["correct"] is True
    assert all(t["type"] == "ok" for t in result["tokens"])


def test_diff_missing_wrong_extra():
    # 漏词
    r = diff_words("I really enjoy reading books", "I enjoy reading books")
    assert any(t["type"] == "missing" and t["ref"] == "really" for t in r["tokens"])
    assert r["correct"] is False
    # 错词（听错）
    r = diff_words("an hour and a half", "a nourana half")
    types = [t["type"] for t in r["tokens"]]
    assert "wrong" in types or "missing" in types
    assert r["correct"] is False
    # 多词
    r = diff_words("she sells seashells", "she sells some seashells")
    assert any(t["type"] == "extra" and t["hyp"] == "some" for t in r["tokens"])
    assert r["correct"] is False


def test_diff_ignores_case_and_punctuation():
    assert diff_words("Hello, World!", "hello world")["correct"] is True


def test_score_dictation_accuracy():
    sentences = ["one two", "three four", "five six"]
    answers = ["one two", "three five", ""]
    result = score_dictation(sentences, answers)
    assert result["accuracy"] == 33  # 1/3
    assert result["per_sentence"][0]["correct"] is True
    assert result["per_sentence"][2]["correct"] is False
    # 全对
    assert score_dictation(sentences, sentences)["accuracy"] == 100
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_dictation.py -v`
Expected: FAIL，`ModuleNotFoundError`

- [ ] **Step 3: 实现 dictation.py**

`backend/app/services/dictation.py`:
```python
import re
import string

from rapidfuzz.distance import Levenshtein

_STRIP = string.punctuation + "，。！？；：""''（）【】"


def _tokenize(text: str) -> list[str]:
    return [t.strip(_STRIP) for t in text.lower().split() if t.strip(_STRIP)]


def diff_words(reference: str, hypothesis: str) -> dict:
    """词级 diff：ok/missing/wrong/extra。忽略大小写与标点。"""
    ref = _tokenize(reference)
    hyp = _tokenize(hypothesis)
    tokens: list[dict] = []
    for tag, a0, a1, b0, b1 in Levenshtein.opcodes(ref, hyp):
        if tag == "equal":
            for i in range(a0, a1):
                tokens.append({"type": "ok", "ref": ref[i], "hyp": ref[i]})
        elif tag == "delete":
            for i in range(a0, a1):
                tokens.append({"type": "missing", "ref": ref[i], "hyp": ""})
        elif tag == "insert":
            for j in range(b0, b1):
                tokens.append({"type": "extra", "ref": "", "hyp": hyp[j]})
        else:  # replace
            pairs = max(a1 - a0, b1 - b0)
            for k in range(pairs):
                r = ref[a0 + k] if a0 + k < a1 else ""
                h = hyp[b0 + k] if b0 + k < b1 else ""
                if r and h:
                    tokens.append({"type": "wrong", "ref": r, "hyp": h})
                elif r:
                    tokens.append({"type": "missing", "ref": r, "hyp": ""})
                else:
                    tokens.append({"type": "extra", "ref": "", "hyp": h})
    return {"tokens": tokens, "correct": all(t["type"] == "ok" for t in tokens)}


def score_dictation(sentences: list[str], answers: list[str]) -> dict:
    """逐句比对；正确率 = 全对句数/总句数 ×100 取整。答案不足按空串。"""
    per_sentence = []
    correct_count = 0
    for i, sentence in enumerate(sentences):
        answer = answers[i] if i < len(answers) else ""
        diff = diff_words(sentence, answer)
        per_sentence.append({"diff": diff, "correct": diff["correct"]})
        if diff["correct"]:
            correct_count += 1
    total = len(sentences)
    accuracy = round(100 * correct_count / total) if total else 0
    return {"accuracy": accuracy, "per_sentence": per_sentence}
```

- [ ] **Step 4: 加依赖 + 测试通过 + 全套回归**

`pyproject.toml` dependencies 加 `"rapidfuzz>=3"`，`uv sync`（unset 代理）。
Run: `cd backend && uv run pytest -v`
Expected: 全部通过（48 既有 + 4 新增）

- [ ] **Step 5: Commit**

```bash
git add backend/ && git commit -m "feat: 听写词级比对服务（rapidfuzz diff + 正确率）"
```

---

### Task 2: 听力素材种子 + 能力树节点 + 逐句 TTS

**Files:**
- Create: `backend/app/data/listening_seed.py`
- Create: `backend/app/seed_listening.py`
- Create: `backend/app/services/listening_tts.py`
- Modify: `backend/app/main.py`（startup 接线）
- Modify: `backend/app/config.py`（加 listening_audio_dir）
- Modify: `.gitignore`（listening_audio/）
- Test: `backend/tests/test_listening_seed.py`

**Interfaces:**
- Consumes: `ListeningMat / SkillNode`（V1）
- Produces:
  - `LISTENING_MATERIALS: list[dict]`（`{title, section: int(2/3/4), sentences: [str...]}`，6 篇）
  - `seed_listening_db(session)`（幂等：材料按 title 查重，节点按 `listening.%` 前缀）
  - `audio_path_for(mat_id: int, idx: int) -> Path`、`audio_ready_count(mat_id: int, total: int) -> int`、`generate_audio_batch(mat_id: int, sentences: list[str]) -> None`（逐句 edge-tts，失败跳过该句；`app.services.listening_tts`）
  - `mark_listening_learned(session, user_id) -> int`（`backend/app/services/listening_mastery.py`）

- [ ] **Step 1: 写失败测试**

`backend/tests/test_listening_seed.py`:
```python
from sqlalchemy import select

from app.data.listening_seed import LISTENING_MATERIALS
from app.database import Base, make_session_factory
from app.models import ListeningMat, SkillNode
from app.seed_listening import seed_listening_db


def make_db(tmp_path):
    factory = make_session_factory(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(factory.kw["bind"])
    return factory


def test_materials_shape():
    assert len(LISTENING_MATERIALS) == 6
    sections = [m["section"] for m in LISTENING_MATERIALS]
    assert sections.count(2) == 2 and sections.count(3) == 2 and sections.count(4) == 2
    for m in LISTENING_MATERIALS:
        assert 8 <= len(m["sentences"]) <= 12
        assert all(len(s.split()) >= 5 for s in m["sentences"])


def test_seed_listening_idempotent(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    seed_listening_db(s)
    seed_listening_db(s)
    mats = s.scalars(select(ListeningMat)).all()
    assert len(mats) == 6
    assert all(len(m.transcript) >= 8 for m in mats)
    nodes = s.scalars(select(SkillNode).where(SkillNode.code.like("listening.%"))).all()
    assert len(nodes) == 12
    assert all(n.module == "listening" for n in nodes)
    s.close()
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_listening_seed.py -v`
Expected: FAIL，`ModuleNotFoundError`

- [ ] **Step 3: listening_seed.py（6 篇手写材料）**

`backend/app/data/listening_seed.py`：`LISTENING_MATERIALS: list[dict]`。

内容与质量要求：
- Section 2 ×2：校园设施导览、课程注册咨询（独白/半对话，生活化学术场景）
- Section 3 ×2：师生论文讨论、小组项目分工讨论（学术讨论，含意见交换与追问）
- Section 4 ×2：城市农业讲座、海洋保护讲座（学术独白，含数据与术语）
- 每篇 8-12 句，每句 ≥5 词；句子含雅思听力高频连读/弱读对应的书面形式（如 "an hour and a half"、"a couple of"、"going to"、"kind of"）；Section 4 含数字与学术词汇
- 结构：`{"title": "...", "section": 2, "sentences": ["...", "..."]}`

- [ ] **Step 4: seed_listening.py + listening_mastery.py**

`backend/app/seed_listening.py`:
```python
from sqlalchemy import select

from app.data.listening_seed import LISTENING_MATERIALS
from app.models import ListeningMat, SkillNode

LISTENING_NODES: list[tuple[str, str, str | None, int]] = [
    ("listening.dictation", "精听听写", None, 0),
    ("listening.dictation.liaison", "连读/弱读识别", "listening.dictation", 0),
    ("listening.dictation.numbers", "数字与单位听写", "listening.dictation", 1),
    ("listening.dictation.spelling", "拼写准确", "listening.dictation", 2),
    ("listening.shadowing", "影子跟读", None, 1),
    ("listening.shadowing.fluency", "流利跟读不停顿", "listening.shadowing", 0),
    ("listening.shadowing.completeness", "不漏词", "listening.shadowing", 1),
    ("listening.vocab", "听力词汇", None, 2),
    ("listening.vocab.academic", "学术词汇听辨", "listening.vocab", 0),
    ("listening.vocab.paraphrase", "同义替换听辨", "listening.vocab", 1),
    ("listening.attention", "注意力与策略", None, 3),
    ("listening.attention.sustain", "长段落注意力持续", "listening.attention", 0),
]


def seed_listening_db(session) -> None:
    """幂等：材料按 title 查重（便于后续追加素材），节点按前缀查重。"""
    existing = set(session.scalars(select(ListeningMat.title)).all())
    for m in LISTENING_MATERIALS:
        if m["title"] not in existing:
            session.add(ListeningMat(title=m["title"], transcript=m["sentences"],
                                     audio_path=f"s{ m['section'] }"))
    has_nodes = session.scalars(
        select(SkillNode.id).where(SkillNode.code.like("listening.%"))).first()
    if not has_nodes:
        code_to_node: dict[str, SkillNode] = {}
        for code, title, parent_code, sort_order in LISTENING_NODES:
            node = SkillNode(
                module="listening", code=code, title=title,
                parent_id=code_to_node[parent_code].id if parent_code else None,
                sort_order=sort_order,
            )
            session.add(node)
            session.flush()
            code_to_node[code] = node
    session.commit()
```

（注：`ListeningMat.audio_path` 字段复用为 section 标记，如 "s2"；真实音频按 mat_id 存文件系统，不入库。）

`backend/app/services/listening_mastery.py`:
```python
from sqlalchemy import select

from app.models import SkillMastery, SkillNode


def mark_listening_learned(session, user_id: int) -> int:
    node_ids = session.scalars(select(SkillNode.id).where(SkillNode.module == "listening")).all()
    existing = set(session.scalars(
        select(SkillMastery.node_id).where(SkillMastery.user_id == user_id)).all())
    added = 0
    for node_id in node_ids:
        if node_id not in existing:
            session.add(SkillMastery(user_id=user_id, node_id=node_id, status="learned",
                                     evidence={"source": "dictation_submitted"}))
            added += 1
    return added
```

- [ ] **Step 5: listening_tts.py + config + gitignore + main.py**

`backend/app/services/listening_tts.py`:
```python
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
```

`config.py` Settings 加：`listening_audio_dir: str = "listening_audio"`
`.gitignore` 加：`backend/listening_audio/`
`main.py` init_db 末尾加：
```python
        from app.seed_listening import seed_listening_db
        seed_listening_db(session)
```

- [ ] **Step 6: 测试通过 + 全套回归**

Run: `cd backend && uv run pytest -v`
Expected: 全部通过（52 既有 + 2 新增）。注意：测试中不要触发真实 edge-tts 调用。

- [ ] **Step 7: Commit**

```bash
git add backend/ .gitignore && git commit -m "feat: 听力素材种子 + 能力树节点 + 逐句 TTS 服务"
```

---

### Task 3: 听力 API

**Files:**
- Modify: `backend/app/schemas.py`
- Create: `backend/app/api/listening.py`
- Modify: `backend/app/main.py`（挂路由）
- Test: `backend/tests/test_listening_api.py`

**Interfaces:**
- Consumes: Task 1-2 全部 + V2 `build_transcriber`
- Produces（前端 Task 4 严格按此对接）:
  - `GET /api/listening/materials` → `list[MatListOut]`（`{id, title, section, sentence_count, ready_count}`）
  - `GET /api/listening/materials/{id}` → `MatDetailOut`（`{id, title, section, sentences: list[str], ready_count}`，404）
  - `POST /api/listening/materials/{id}/audio` → `{"status": "started"|"ready", "ready_count, "total"}`（后台任务批量生成；全部就绪返回 ready）
  - `GET /api/listening/audio/{mat_id}/{idx}.mp3` → 文件或 404（路径参数为 int，天然防穿越）
  - `POST /api/listening/dictation`，body `{material_id, answers: list[str]}` → `DictationResultOut`（`{practice_id, accuracy, per_sentence: [{diff, correct}]}`），素材不存在 404
  - `POST /api/listening/shadowing`，multipart `material_id` + `audio`(wav) → `{transcript, diff, is_mock}`
  - `POST /api/listening/attribution`，body `{practice_id, sentence_index, reason}` → 201 `{“id”: int}`；reason 非法 422；practice 不存在/非听力 404

- [ ] **Step 1: schemas.py 追加**

```python
class MatListOut(BaseModel):
    id: int
    title: str
    section: int
    sentence_count: int
    ready_count: int


class MatDetailOut(BaseModel):
    id: int
    title: str
    section: int
    sentences: list[str]
    ready_count: int


class DictationSubmit(BaseModel):
    material_id: int
    answers: list[str]


class DictationResultOut(BaseModel):
    practice_id: int
    accuracy: int
    per_sentence: list[dict]


class AttributionSubmit(BaseModel):
    practice_id: int
    sentence_index: int = Field(ge=0)
    reason: str

    @field_validator("reason")
    @classmethod
    def valid_reason(cls, v: str) -> str:
        if v not in ("连读", "词汇", "口音", "注意力"):
            raise ValueError("归因取值仅支持：连读/词汇/口音/注意力")
        return v
```

（`MatListOut`/`MatDetailOut` 的 `section` 来自 `audio_path` 字段的复用标记，API 层用 `_section_of()` 解析 `int(audio_path.strip("s"))`；自定义字段不适用 `from_attributes`，端点手工构造。）

- [ ] **Step 2: 写失败测试**

`backend/tests/test_listening_api.py`:
```python
import io
import wave

import pytest
from fastapi.testclient import TestClient

from app.database import Base, make_session_factory
from app.main import app
from app.models import ErrorItem, Practice, User
from app.seed_listening import seed_listening_db


@pytest.fixture()
def client(tmp_path, monkeypatch):
    factory = make_session_factory(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(factory.kw["bind"])
    s = factory()
    s.add(User(id=1))
    s.commit()
    seed_listening_db(s)
    s.close()
    monkeypatch.setattr("app.config.settings.deepseek_api_key", "")
    monkeypatch.setattr("app.config.settings.iflytek_app_id", "")
    monkeypatch.setattr("app.config.settings.iflytek_api_secret", "")
    monkeypatch.setattr("app.config.settings.listening_audio_dir", str(tmp_path / "la"))
    monkeypatch.setattr(app.state, "session_factory", factory)
    return TestClient(app)


def make_wav_bytes() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 16000)
    return buf.getvalue()


def test_materials_and_detail(client):
    mats = client.get("/api/listening/materials").json()
    assert len(mats) == 6
    assert mats[0]["sentence_count"] >= 8
    assert mats[0]["ready_count"] == 0  # 测试环境不生成音频

    detail = client.get(f"/api/listening/materials/{mats[0]['id']}").json()
    assert len(detail["sentences"]) == mats[0]["sentence_count"]
    assert client.get("/api/listening/materials/999").status_code == 404
    # 音频不存在 → 404
    assert client.get(f"/api/listening/audio/{mats[0]['id']}/0.mp3").status_code == 404


def test_dictation_flow_and_attribution(client):
    mats = client.get("/api/listening/materials").json()
    mat = client.get(f"/api/listening/materials/{mats[0]['id']}").json()
    answers = list(mat["sentences"])  # 先全对
    answers[0] = "wrong words here"
    resp = client.post("/api/listening/dictation", json={
        "material_id": mat["id"], "answers": answers})
    assert resp.status_code == 200
    body = resp.json()
    total = len(mat["sentences"])
    assert body["accuracy"] == round(100 * (total - 1) / total)
    assert body["per_sentence"][0]["correct"] is False
    assert body["per_sentence"][1]["correct"] is True
    assert body["per_sentence"][0]["diff"]["tokens"]

    # 归因
    resp = client.post("/api/listening/attribution", json={
        "practice_id": body["practice_id"], "sentence_index": 0, "reason": "连读"})
    assert resp.status_code == 201
    # 非法归因
    assert client.post("/api/listening/attribution", json={
        "practice_id": body["practice_id"], "sentence_index": 0, "reason": "粗心"}).status_code == 422
    # practice 404
    assert client.post("/api/listening/attribution", json={
        "practice_id": 999, "sentence_index": 0, "reason": "连读"}).status_code == 404


def test_shadowing_mock(client):
    mats = client.get("/api/listening/materials").json()
    resp = client.post("/api/listening/shadowing",
                       data={"material_id": str(mats[0]["id"])},
                       files={"audio": ("a.wav", make_wav_bytes(), "audio/wav")})
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_mock"] is True
    assert body["transcript"]
    assert "tokens" in body["diff"]
```

- [ ] **Step 3: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_listening_api.py -v`
Expected: FAIL，404

- [ ] **Step 4: 实现 api/listening.py**

`backend/app/api/listening.py`:
```python
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.models import AIFeedback, ErrorItem, ListeningMat, Practice
from app.schemas import (AttributionSubmit, DictationResultOut, DictationSubmit,
                         MatDetailOut, MatListOut)
from app.services.asr import build_transcriber
from app.services.dictation import diff_words, score_dictation
from app.services.listening_mastery import mark_listening_learned
from app.services.listening_tts import (audio_path_for, audio_ready_count,
                                        generate_audio_batch)

router = APIRouter(prefix="/api")


def get_session(request: Request):
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def _section_of(mat: ListeningMat) -> int:
    return int(mat.audio_path.strip("s")) if mat.audio_path else 0


@router.get("/listening/materials", response_model=list[MatListOut])
def list_materials(session=Depends(get_session)):
    mats = session.scalars(select(ListeningMat).order_by(ListeningMat.id)).all()
    return [MatListOut(
        id=m.id, title=m.title, section=_section_of(m),
        sentence_count=len(m.transcript),
        ready_count=audio_ready_count(m.id, len(m.transcript)),
    ) for m in mats]


@router.get("/listening/materials/{mat_id}", response_model=MatDetailOut)
def get_material(mat_id: int, session=Depends(get_session)):
    mat = session.get(ListeningMat, mat_id)
    if mat is None:
        raise HTTPException(status_code=404, detail="素材不存在")
    return MatDetailOut(
        id=mat.id, title=mat.title, section=_section_of(mat),
        sentences=mat.transcript,
        ready_count=audio_ready_count(mat.id, len(mat.transcript)),
    )


@router.post("/listening/materials/{mat_id}/audio")
def generate_audio(mat_id: int, background: BackgroundTasks, session=Depends(get_session)):
    mat = session.get(ListeningMat, mat_id)
    if mat is None:
        raise HTTPException(status_code=404, detail="素材不存在")
    total = len(mat.transcript)
    ready = audio_ready_count(mat_id, total)
    if ready < total:
        background.add_task(generate_audio_batch, mat_id, mat.transcript)
        return {"status": "started", "ready_count": ready, "total": total}
    return {"status": "ready", "ready_count": ready, "total": total}


@router.get("/listening/audio/{mat_id}/{idx}.mp3")
def get_audio(mat_id: int, idx: int):
    path = audio_path_for(mat_id, idx)
    if not path.exists():
        raise HTTPException(status_code=404, detail="音频不存在")
    return FileResponse(path, media_type="audio/mpeg")


@router.post("/listening/dictation", response_model=DictationResultOut)
def submit_dictation(payload: DictationSubmit, session=Depends(get_session)):
    mat = session.get(ListeningMat, payload.material_id)
    if mat is None:
        raise HTTPException(status_code=404, detail="素材不存在")
    result = score_dictation(mat.transcript, payload.answers)
    practice = Practice(
        user_id=1, module="listening", prompt_title=mat.title,
        prompt_text=f"Section {_section_of(mat)} 精听听写",
        content="\n".join(payload.answers),
        word_count=sum(len(a.split()) for a in payload.answers),
        status="done", total_band=result["accuracy"],
    )
    session.add(practice)
    session.flush()
    session.add(AIFeedback(
        practice_id=practice.id,
        bands={"accuracy": result["accuracy"]},
        annotations=[{"sentence_index": i, "diff": ps["diff"], "correct": ps["correct"]}
                     for i, ps in enumerate(result["per_sentence"])],
        rewrite="", model="dictation", is_mock=False,
    ))
    mark_listening_learned(session, 1)
    session.commit()
    return DictationResultOut(
        practice_id=practice.id, accuracy=result["accuracy"],
        per_sentence=result["per_sentence"],
    )


@router.post("/listening/shadowing")
def shadowing(material_id: int = Form(...), audio: UploadFile = File(...),
              session=Depends(get_session)):
    mat = session.get(ListeningMat, material_id)
    if mat is None:
        raise HTTPException(status_code=404, detail="素材不存在")
    import uuid
    from pathlib import Path

    from app.config import settings

    data = audio.file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="音频超过 5MB 上限")
    uploads = Path(settings.uploads_dir)
    uploads.mkdir(parents=True, exist_ok=True)
    path = uploads / f"shadow-{uuid.uuid4().hex}.wav"
    path.write_bytes(data)

    transcriber = build_transcriber()
    try:
        result = transcriber.transcribe(str(path))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"转写失败: {exc}")
    reference = " ".join(mat.transcript)
    return {
        "transcript": result.text,
        "diff": diff_words(reference, result.text),
        "is_mock": transcriber.is_mock,
    }


@router.post("/listening/attribution", status_code=201)
def attribute(payload: AttributionSubmit, session=Depends(get_session)):
    practice = session.get(Practice, payload.practice_id)
    if practice is None or practice.module != "listening":
        raise HTTPException(status_code=404, detail="练习不存在")
    item = ErrorItem(
        user_id=1, practice_id=practice.id,
        error_type=f"听力:{payload.reason}",
        context=f"第 {payload.sentence_index + 1} 句",
    )
    session.add(item)
    session.commit()
    return {"id": item.id}
```

- [ ] **Step 5: main.py 挂路由**

`from app.api.listening import router as listening_router` + `app.include_router(listening_router)`。

- [ ] **Step 6: 测试通过 + 全套回归**

Run: `cd backend && uv run pytest -v`
Expected: 全部通过（54 既有 + 3 新增）

- [ ] **Step 7: Commit**

```bash
git add backend/ && git commit -m "feat: 听力 API（素材/逐句音频/听写评分/跟读比对/归因）"
```

---

### Task 4: 前端听力页（播放器 + 三模式）

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/client.ts`
- Create: `frontend/src/components/DiffTokens.tsx`
- Create: `frontend/src/pages/ListeningPage.tsx`
- Modify: `frontend/src/App.tsx`（`/listening` 路由）
- Modify: `frontend/src/components/NavBar.tsx`（加"听力"链接）

**Interfaces:**
- Consumes: Task 3 API 契约；`WavRecorder`（V2）
- Produces: `DiffTokens`（props `{tokens: DiffToken[]}`，Task 内听写/跟读共用）

- [ ] **Step 1: types.ts / client.ts 追加**

types.ts:
```ts
export interface MatListOut {
  id: number
  title: string
  section: number
  sentence_count: number
  ready_count: number
}

export interface MatDetailOut {
  id: number
  title: string
  section: number
  sentences: string[]
  ready_count: number
}

export interface DiffToken {
  type: 'ok' | 'missing' | 'wrong' | 'extra'
  ref: string
  hyp: string
}

export interface DictationResultOut {
  practice_id: number
  accuracy: number
  per_sentence: { diff: { tokens: DiffToken[]; correct: boolean }; correct: boolean }[]
}

export interface ShadowingResult {
  transcript: string
  diff: { tokens: DiffToken[]; correct: boolean }
  is_mock: boolean
}
```

client.ts:
```ts
export function listListeningMaterials(): Promise<MatListOut[]> {
  return request('/listening/materials')
}

export function getListeningMaterial(id: number): Promise<MatDetailOut> {
  return request(`/listening/materials/${id}`)
}

export function requestListeningAudio(id: number): Promise<{ status: string; ready_count: number; total: number }> {
  return request(`/listening/materials/${id}/audio`, { method: 'POST' })
}

export function submitDictation(materialId: number, answers: string[]): Promise<DictationResultOut> {
  return request('/listening/dictation', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ material_id: materialId, answers }),
  })
}

export function submitShadowing(materialId: number, audio: Blob): Promise<ShadowingResult> {
  const form = new FormData()
  form.append('material_id', String(materialId))
  form.append('audio', audio, 'shadow.wav')
  return request('/listening/shadowing', { method: 'POST', body: form })
}

export function submitAttribution(practiceId: number, sentenceIndex: number, reason: string): Promise<{ id: number }> {
  return request('/listening/attribution', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ practice_id: practiceId, sentence_index: sentenceIndex, reason }),
  })
}
```

- [ ] **Step 2: DiffTokens 组件**

`frontend/src/components/DiffTokens.tsx`:
```tsx
import type { DiffToken } from '../api/types'

/** 词级 diff 渲染：ok 正常 / missing 红虚线下划线 / wrong 红底显示原文+你的词 / extra 删除线 */
export function DiffTokens({ tokens }: { tokens: DiffToken[] }) {
  return (
    <span className="leading-7">
      {tokens.map((t, i) => {
        if (t.type === 'ok') return <span key={i}>{t.ref} </span>
        if (t.type === 'missing') {
          return (
            <span key={i} className="border-b-2 border-dashed border-red-400 text-red-500">
              {t.ref}{' '}
            </span>
          )
        }
        if (t.type === 'wrong') {
          return (
            <span key={i} className="rounded bg-red-100 px-0.5 text-red-600" title={`你写的是: ${t.hyp}`}>
              {t.ref} <s className="text-red-400">{t.hyp}</s>{' '}
            </span>
          )
        }
        return (
          <span key={i} className="text-slate-400 line-through">
            {t.hyp}{' '}
          </span>
        )
      })}
    </span>
  )
}
```

- [ ] **Step 3: ListeningPage**

`frontend/src/pages/ListeningPage.tsx`:
```tsx
import { useEffect, useRef, useState } from 'react'
import {
  getListeningMaterial, listListeningMaterials, requestListeningAudio,
  submitAttribution, submitDictation, submitShadowing,
} from '../api/client'
import type {
  DictationResultOut, MatDetailOut, MatListOut, ShadowingResult,
} from '../api/types'
import { DiffTokens } from '../components/DiffTokens'
import { WavRecorder } from '../lib/recorder'

const REASONS = ['连读', '词汇', '口音', '注意力'] as const
const SPEEDS = [0.75, 1, 1.25] as const

type Mode = 'transcript' | 'dictation' | 'shadowing'

export default function ListeningPage() {
  const [materials, setMaterials] = useState<MatListOut[]>([])
  const [selected, setSelected] = useState<MatDetailOut | null>(null)
  const [mode, setMode] = useState<Mode>('transcript')
  const [error, setError] = useState('')

  useEffect(() => {
    listListeningMaterials().then(setMaterials).catch((e) => setError(String(e)))
  }, [])

  const open = async (id: number) => {
    const detail = await getListeningMaterial(id)
    setSelected(detail)
    setMode('transcript')
    // 触发后台逐句音频生成（幂等；已就绪则立即 ready）
    requestListeningAudio(id).catch(() => undefined)
  }

  if (selected) {
    return <PracticeView mat={selected} mode={mode} setMode={setMode}
      onBack={() => setSelected(null)} />
  }

  const sections = [2, 3, 4]
  return (
    <div className="space-y-6">
      {error && <div className="text-sm text-red-500">{error}</div>}
      {sections.map((sec) => (
        <div key={sec}>
          <h3 className="mb-2 font-semibold text-slate-600">Section {sec}</h3>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {materials.filter((m) => m.section === sec).map((m) => (
              <button key={m.id} onClick={() => open(m.id)}
                className="rounded-xl border border-slate-200 bg-white p-4 text-left hover:border-indigo-300">
                <div className="font-medium text-slate-700">{m.title}</div>
                <div className="mt-1 text-xs text-slate-400">
                  {m.sentence_count} 句 · 音频就绪 {m.ready_count}/{m.sentence_count}
                </div>
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function PracticeView({ mat, mode, setMode, onBack }: {
  mat: MatDetailOut
  mode: Mode
  setMode: (m: Mode) => void
  onBack: () => void
}) {
  const [speed, setSpeed] = useState<number>(1)
  const [loopIdx, setLoopIdx] = useState<number | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  const play = (idx: number) => {
    audioRef.current?.pause()
    const audio = new Audio(`/api/listening/audio/${mat.id}/${idx}.mp3`)
    audio.playbackRate = speed
    audio.onended = () => setLoopIdx((cur) => (cur === idx ? null : cur))
    audio.onerror = () => setLoopIdx(null)
    audio.play().catch(() => undefined)
    audioRef.current = audio
  }

  const toggleLoop = (idx: number) => {
    if (loopIdx === idx) {
      audioRef.current?.pause()
      setLoopIdx(null)
      return
    }
    audioRef.current?.pause()
    const audio = new Audio(`/api/listening/audio/${mat.id}/${idx}.mp3`)
    audio.playbackRate = speed
    audio.loop = true
    audio.play().catch(() => undefined)
    audioRef.current = audio
    setLoopIdx(idx)
  }

  useEffect(() => () => audioRef.current?.pause(), [])

  const MODES: { key: Mode; label: string }[] = [
    { key: 'transcript', label: '字幕对照' },
    { key: 'dictation', label: '精听听写' },
    { key: 'shadowing', label: '影子跟读' },
  ]

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <button onClick={onBack} className="mr-3 text-sm text-slate-400 hover:text-slate-600">
            ← 返回
          </button>
          <span className="font-semibold">{mat.title}</span>
          <span className="ml-2 rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
            Section {mat.section}
          </span>
        </div>
        <div className="flex gap-1">
          {SPEEDS.map((s) => (
            <button key={s} onClick={() => setSpeed(s)}
              className={`rounded px-2 py-1 text-xs ${
                speed === s ? 'bg-indigo-600 text-white' : 'bg-white border border-slate-200'
              }`}>
              {s}x
            </button>
          ))}
        </div>
      </div>

      <div className="flex gap-2">
        {MODES.map((m) => (
          <button key={m.key} onClick={() => setMode(m.key)}
            className={`rounded-lg px-4 py-2 text-sm font-medium ${
              mode === m.key ? 'bg-indigo-600 text-white' : 'bg-white border border-slate-200 text-slate-600'
            }`}>
            {m.label}
          </button>
        ))}
      </div>

      {mode === 'transcript' && (
        <div className="space-y-2">
          {mat.sentences.map((s, i) => (
            <div key={i}
              className="flex items-start gap-3 rounded-xl border border-slate-200 bg-white p-3">
              <button onClick={() => toggleLoop(i)} title="单句循环"
                className={`shrink-0 rounded-lg px-3 py-1 text-sm ${
                  loopIdx === i ? 'bg-indigo-600 text-white' : 'bg-indigo-50 text-indigo-600'
                }`}>
                {loopIdx === i ? '⏸ 停止' : '▶ 循环'}
              </button>
              <span className="text-sm text-slate-700">{s}</span>
            </div>
          ))}
          <p className="text-xs text-slate-400">
            音频由 AI 语音生成；显示"音频不存在"时请稍后重试（后台生成中）。
          </p>
        </div>
      )}

      {mode === 'dictation' && <DictationMode mat={mat} play={play} />}
      {mode === 'shadowing' && <ShadowingMode mat={mat} />}
    </div>
  )
}

function DictationMode({ mat, play }: {
  mat: MatDetailOut
  play: (idx: number) => void
}) {
  const [answers, setAnswers] = useState<string[]>(mat.sentences.map(() => ''))
  const [result, setResult] = useState<DictationResultOut | null>(null)
  const [attributed, setAttributed] = useState<Set<number>>(new Set())
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    setBusy(true)
    try {
      setResult(await submitDictation(mat.id, answers))
    } finally {
      setBusy(false)
    }
  }

  const attribute = async (idx: number, reason: string) => {
    if (!result) return
    await submitAttribution(result.practice_id, idx, reason)
    setAttributed((prev) => new Set(prev).add(idx))
  }

  return (
    <div className="space-y-3">
      {mat.sentences.map((s, i) => (
        <div key={i} className="rounded-xl border border-slate-200 bg-white p-3">
          <div className="flex items-center gap-3">
            <button onClick={() => play(i)}
              className="shrink-0 rounded-lg bg-indigo-50 px-3 py-1 text-sm text-indigo-600">
              ▶ 第 {i + 1} 句
            </button>
            <input
              className="flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-indigo-400 focus:outline-none"
              placeholder="听写这一句…"
              value={answers[i]}
              onChange={(e) => {
                const next = [...answers]
                next[i] = e.target.value
                setAnswers(next)
              }}
              disabled={result !== null}
            />
          </div>
          {result && (
            <div className="mt-2 border-t border-slate-100 pt-2">
              <DiffTokens tokens={result.per_sentence[i].diff.tokens} />
              {!result.per_sentence[i].correct && (
                <div className="mt-2 flex items-center gap-2 text-xs">
                  <span className="text-slate-400">归因：</span>
                  {attributed.has(i) ? (
                    <span className="text-emerald-600">已记录 ✓</span>
                  ) : (
                    REASONS.map((r) => (
                      <button key={r} onClick={() => attribute(i, r)}
                        className="rounded border border-slate-200 px-2 py-0.5 text-slate-500 hover:border-indigo-300">
                        {r}
                      </button>
                    ))
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      ))}
      {!result ? (
        <button onClick={submit} disabled={busy}
          className="w-full rounded-xl bg-indigo-600 py-3 font-semibold text-white disabled:opacity-40">
          {busy ? '比对中…' : '提交比对'}
        </button>
      ) : (
        <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-4 text-center">
          <span className="text-sm text-slate-500">本篇正确率</span>
          <div className="text-3xl font-bold text-indigo-600">{result.accuracy}%</div>
        </div>
      )}
    </div>
  )
}

function ShadowingMode({ mat }: { mat: MatDetailOut }) {
  const [recording, setRecording] = useState(false)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<ShadowingResult | null>(null)
  const [error, setError] = useState('')
  const recorderRef = useRef<WavRecorder | null>(null)

  useEffect(() => () => {
    if (recorderRef.current) {
      const r = recorderRef.current
      recorderRef.current = null
      void r.stop()
    }
  }, [])

  const toggle = async () => {
    if (recording) {
      const recorder = recorderRef.current
      if (!recorder) return
      recorderRef.current = null
      setRecording(false)
      setBusy(true)
      setError('')
      try {
        const blob = await recorder.stop()
        setResult(await submitShadowing(mat.id, blob))
      } catch (e) {
        setError(String(e))
      } finally {
        setBusy(false)
      }
    } else {
      try {
        recorderRef.current = new WavRecorder()
        await recorderRef.current.start()
        setRecording(true)
        setResult(null)
      } catch {
        setError('无法访问麦克风，请检查浏览器权限')
      }
    }
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-600">
        <div className="mb-2 font-semibold">原文（{mat.sentences.length} 句）</div>
        {mat.sentences.map((s, i) => <p key={i} className="leading-7">{s}</p>)}
      </div>
      <button onClick={toggle} disabled={busy}
        className={`w-full rounded-xl py-3 font-semibold text-white disabled:opacity-40 ${
          recording ? 'bg-red-500' : 'bg-indigo-600'
        }`}>
        {recording ? '■ 停止并比对' : busy ? '转写比对中…' : '● 开始跟读录音'}
      </button>
      {error && <div className="text-sm text-red-500">{error}</div>}
      {result && (
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="mb-2 flex items-center gap-2">
            <span className="text-sm font-semibold">跟读比对</span>
            {result.is_mock && (
              <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-700">演示数据</span>
            )}
          </div>
          <div className="mb-2 text-sm text-slate-500">你的转写：{result.transcript}</div>
          <DiffTokens tokens={result.diff.tokens} />
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: 路由与导航**

- `App.tsx`：`import ListeningPage from './pages/ListeningPage'` + `<Route path="/listening" element={<ListeningPage />} />`
- `NavBar.tsx` links 加 `{ to: '/listening', label: '听力' }`

- [ ] **Step 5: 构建验证**

Run: `cd frontend && npm run build`（Node v22，unset 代理）
Expected: 通过

- [ ] **Step 6: Commit**

```bash
git add frontend/ && git commit -m "feat: 听力页（单句循环/变速/听写 diff/跟读比对/归因）"
```

---

### Task 5: 历史页分模块曲线 + 仪表盘 + e2e + 文档 + 推送

**Files:**
- Modify: `frontend/src/pages/HistoryPage.tsx`
- Modify: `frontend/src/pages/DashboardPage.tsx`
- Modify: `README.md`

- [ ] **Step 1: HistoryPage 分模块曲线**

- 曲线区加模块 Tab：`[写作, 口语, 听力]`，state `curveModule` 默认 "writing"
- 数据：`essays.filter((e) => e.total_band !== null && e.module === curveModule)`
- 听力模式：y 轴 `min: 0, max: 100`，markLine 改为 90（`目标 90%`），tooltip formatter 加 `%`；写作/口语保持 4-9 与 6.5 目标线
- 表格模块标签加听力：`module === 'listening'` → amber 底"听力"，总分列听力显示 `{value}%`

- [ ] **Step 2: DashboardPage 听力卡 + 横幅**

- 加 `const latestListening = essays.find((e) => e.total_band !== null && e.module === 'listening')`
- 词汇卡后加听力卡：标题"听力最新正确率"，主数字 `{latestListening ? `${latestListening.total_band}%` : '—'}`，链接 `/listening`「去精听 →」
- 横幅改为"能力树点亮验证将在后续版本上线"

- [ ] **Step 3: 构建 + 全量测试**

```bash
cd frontend && npm run build
cd ../backend && uv run pytest -v
```
Expected: 全绿（57 后端用例）

- [ ] **Step 4: e2e（端口 8022，全 mock）**

```bash
cd backend && env -u DEEPSEEK_API_KEY -u IFLYTEK_APP_ID -u IFLYTEK_API_SECRET \
  uv run uvicorn app.main:app --port 8022
```
```bash
curl localhost:8022/api/listening/materials
curl localhost:8022/api/listening/materials/1
curl -X POST localhost:8022/api/listening/materials/1/audio   # 无网络/edge-tts 失败也应返回 started
curl -X POST localhost:8022/api/listening/dictation -H 'Content-Type: application/json' \
  -d '{"material_id": 1, "answers": ["", "test"]}'
curl -X POST localhost:8022/api/listening/attribution -H 'Content-Type: application/json' \
  -d '{"practice_id": 1, "sentence_index": 0, "reason": "连读"}'
# 跟读（mock ASR）
curl -X POST localhost:8022/api/listening/shadowing -F "material_id=1" -F "audio=@/tmp/a.wav"
```
Expected：materials 6 篇；dictation 返回 accuracy 与 practice_id；attribution 201；shadowing 返回 mock 转写 + diff + is_mock=true

- [ ] **Step 5: README 更新**

在「词汇模块（V3）」后加：
```markdown
## 听力模块（V4）

- 入口：`/listening`，Section 2/3/4 各 2 篇 AI 生成素材（无版权问题）
- 音频由 edge-tts 逐句生成（首次打开素材时后台触发）；生成失败时文本练习仍可用
- 三种模式：逐句字幕对照（单句循环 + 0.75/1/1.25 变速）/ 精听听写（词级 diff 标红 + 错题归因）/ 影子跟读（ASR 转写比对）
- 听写正确率计入历史曲线（按模块切换查看）
```

- [ ] **Step 6: Commit + push**

```bash
git add -A && git commit -m "docs: README 更新 + 历史分模块曲线，V4 完成" && git push
```

- [ ] **Step 7: 收尾核对（对照规格 §1 成功标准）**

- 逐句字幕/单句循环/变速 ✓
- 听写词级 diff 标红 ✓；跟读 ASR 比对 ✓
- 四选一归引入错误库 ✓
- 历史页听力正确率曲线 ✓；仪表盘听力卡 ✓
- 素材无版权风险（AI 文本 + edge-tts）✓
