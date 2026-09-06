# 雅思 V2 口语模块 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 V1 骨架上实现口语模块——录音(WAV)上传 → ASR 转写（讯飞/Mock）→ DeepSeek 四项评分 → 逐句批注 + 改写 → 错误入库，含 Part 1/2/3 三入口与多轮 AI 考官对话（Part 3 LLM 追问）、edge-tts 提问语音。

**Architecture:** 复用 V1 的 practice/ai_feedback/error_item 核心表与「后台任务 + 前端轮询」模式。新增 ASR 适配器层（Mock 降级）、speaking_card/speaking_session 两张表、practice 加 audio_path/session_id 两列。前端新增 SpeakingPage 与聊天式 PracticeRoom，口语结果内嵌对话气泡，不改 V1 ResultPage。

**Tech Stack:** 同 V1（FastAPI/SQLAlchemy 2.0/Pydantic v2/openai SDK/pytest；React/Vite/TS/Tailwind/ECharts）+ 新增 edge-tts（TTS）、httpx（讯飞 HTTP，已在 openai 依赖链中）、Web Audio API WAV 编码（前端）。

**上游规格:** `docs/superpowers/specs/2026-09-06-ielts-speaking-v2-design.md`

## Global Constraints

- Python >= 3.11，uv 管理；测试在 `backend/` 下 `uv run pytest`；测试 DB 一律 tmp 路径 SQLite，绝不碰 `./yasi.db`
- LLM 调用沿用 V1 加固：`response_format={"type":"json_object"}`、temperature=0.2、max_tokens=8192、最多 3 次尝试、容忍未闭合 JSON（补 `}` 重 parse）、validate 失败记录 finish_reason/usage
- 讯飞配置读 `.env`：`IFLYTEK_APP_ID / IFLYTEK_API_SECRET`；缺失时自动用 MockTranscriber（界面经 `is_mock` 标注"演示数据"）
- 音频上限 5MB，格式仅接受 .wav；`backend/uploads/` 与 `backend/tts_cache/` 均 gitignored
- 发音分项为间接评估，UI 固定标注「发音分为间接评估，仅供参考」
- 单人模式 user_id=1；口语能力点种子用 `speaking.` 前缀，seed 按模块幂等
- 本机端口 8000 被其他项目占用：所有冒烟/手动验证用 `--port 8022`；shell 代理会破坏外网请求，`uv`/npm/网络命令先 unset 代理环境变量；前端命令必须 Homebrew Node v22
- git 提交信息用中文 Conventional Commits
- 本机环境有真实 `DEEPSEEK_API_KEY`：测试中一律 monkeypatch 掉（沿用 V1 test_api 的 fixture 写法），真实调用只允许在 Task 9 的验收步骤发生

---

### Task 1: ASR 适配器层（base/mock/iflytek）

**Files:**
- Modify: `backend/app/config.py`（加讯飞与目录配置）
- Create: `backend/app/services/asr/__init__.py`
- Create: `backend/app/services/asr/base.py`
- Create: `backend/app/services/asr/mock.py`
- Create: `backend/app/services/asr/iflytek.py`
- Test: `backend/tests/test_asr.py`

**Interfaces:**
- Consumes: `settings`（V1）
- Produces:
  - `TranscriptResult`（dataclass：`text: str, confidence: float`）、`TranscribeFailed`（`app.services.asr.base`）
  - `MockTranscriber` / `IFlytekTranscriber`，均有属性 `is_mock: bool` 与方法 `transcribe(self, audio_path: str) -> TranscriptResult`
  - `build_transcriber()`（`app.services.asr`）：有 `iflytek_app_id + iflytek_api_secret` 返回 IFlytek，否则 Mock。Task 4 的 `run_speaking_turn` 消费这些

- [ ] **Step 1: 写失败测试**

`backend/tests/test_asr.py`:
```python
import json

from app.config import settings
from app.services.asr import build_transcriber
from app.services.asr.base import TranscriptResult
from app.services.asr.iflytek import IFlytekTranscriber
from app.services.asr.mock import MockTranscriber


def test_mock_transcriber():
    t = MockTranscriber()
    assert t.is_mock is True
    result = t.transcribe("any.wav")
    assert isinstance(result, TranscriptResult)
    assert len(result.text.split()) >= 50
    assert 0 < result.confidence <= 1


def test_build_transcriber_falls_back_to_mock(monkeypatch):
    monkeypatch.setattr(settings, "iflytek_app_id", "")
    monkeypatch.setattr(settings, "iflytek_api_secret", "")
    assert build_transcriber().is_mock is True


def test_build_transcriber_picks_iflytek(monkeypatch):
    monkeypatch.setattr(settings, "iflytek_app_id", "appid")
    monkeypatch.setattr(settings, "iflytek_api_secret", "secret")
    assert build_transcriber().is_mock is False


def test_iflytek_sign_is_deterministic():
    t = IFlytekTranscriber("myappid", "mysecret")
    # 讯飞签名 = base64(hmac-sha1(md5(appid+ts), secret))
    import base64, hashlib, hmac
    ts = "1700000000"
    expected = base64.b64encode(
        hmac.new(b"mysecret", hashlib.md5(b"myappid1700000000").hexdigest().encode(), hashlib.sha1
        ).digest()).decode()
    assert t._sign(ts) == expected


def test_iflytek_parse_result_json():
    t = IFlytekTranscriber("a", "s")
    # 讯飞 getResult 的 content.orderResult（JSON 字符串）的最小结构样例
    order_result = json.dumps({
        "lattice2": [
            {"json_1best": {"st": {"rt": [{"ws": [
                {"w": "Well", "wp": "n"}, {"w": " ", "wp": "s"},
                {"w": "I", "wp": "n"}, {"w": " ", "wp": "s"},
                {"w": "think", "wp": "n"}
            ]}], "sc": 87}}}
        ]
    })
    result = t._parse_order_result(order_result)
    assert result.text == "Well I think"
    assert 0 < result.confidence <= 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && uv run pytest tests/test_asr.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.services.asr'`

- [ ] **Step 3: config.py 加配置**

在 `Settings` 类中追加：
```python
    iflytek_app_id: str = ""
    iflytek_api_secret: str = ""
    iflytek_api_key: str = ""  # 预留（流式接口用）
    uploads_dir: str = "uploads"
    tts_cache_dir: str = "tts_cache"
```

- [ ] **Step 4: 实现 base.py 与 mock.py**

`backend/app/services/asr/base.py`:
```python
from dataclasses import dataclass
from typing import Protocol


@dataclass
class TranscriptResult:
    text: str
    confidence: float  # 0-1


class TranscribeFailed(Exception):
    pass


class Transcriber(Protocol):
    is_mock: bool

    def transcribe(self, audio_path: str) -> TranscriptResult: ...
```

`backend/app/services/asr/mock.py`:
```python
from app.services.asr.base import TranscriptResult

MOCK_TRANSCRIPT = (
    "Well, I think working from home is, um, it has a lot of benefits. "
    "First, people can save time because they don't need to, you know, "
    "take the bus or subway for two hours every day. "
    "And also it is more comfortable, you can wear what you like. "
    "But sometimes I feel lonely, because I cannot talk with my colleagues face to face. "
    "So I think it depends on the person, but for me the good things is more than the bad things."
)


class MockTranscriber:
    is_mock = True

    def transcribe(self, audio_path: str) -> TranscriptResult:
        return TranscriptResult(text=MOCK_TRANSCRIPT, confidence=0.9)
```

- [ ] **Step 5: 实现 iflytek.py**

讯飞「语音转写（长语音）」REST API（raasr）。**实现前先核对官方文档**（https://www.xfyun.cn/doc/asr/ifasrt_new/API.html 或站内最新链接）确认字段名未变；若文档与下方代码有出入，以文档为准并在报告中说明偏差。

`backend/app/services/asr/iflytek.py`:
```python
import base64
import hashlib
import hmac
import json
import time
import wave

import httpx

from app.services.asr.base import TranscribeFailed, TranscriptResult

API_UPLOAD = "https://raasr.xfyun.cn/v2/api/upload"
API_RESULT = "https://raasr.xfyun.cn/v2/api/getResult"
POLL_INTERVAL_SEC = 2
POLL_TIMEOUT_SEC = 60


class IFlytekTranscriber:
    is_mock = False

    def __init__(self, app_id: str, api_secret: str):
        self.app_id = app_id
        self.api_secret = api_secret

    def _sign(self, ts: str) -> str:
        md5 = hashlib.md5((self.app_id + ts).encode()).hexdigest().encode()
        digest = hmac.new(self.api_secret.encode(), md5, hashlib.sha1).digest()
        return base64.b64encode(digest).decode()

    def _audio_duration_ms(self, audio_path: str) -> int:
        with wave.open(audio_path, "rb") as wf:
            return int(wf.getnframes() / wf.getframerate() * 1000)

    def _parse_order_result(self, order_result: str) -> TranscriptResult:
        data = json.loads(order_result)
        words: list[str] = []
        scores: list[float] = []
        for lattice in data.get("lattice2", []):
            st = lattice["json_1best"]["st"]
            if st.get("sc"):
                scores.append(float(st["sc"]))
            for rt in st.get("rt", []):
                for ws in rt.get("ws", []):
                    words.append(ws["w"])
        text = "".join(words).strip()
        # 讯飞按词给出空格分隔的 wp=s 占位，清掉多余空白
        text = " ".join(text.split())
        confidence = min(sum(scores) / len(scores) / 100, 1.0) if scores else 0.9
        return TranscriptResult(text=text, confidence=round(confidence, 2))

    def transcribe(self, audio_path: str) -> TranscriptResult:
        with open(audio_path, "rb") as f:
            audio = f.read()
        ts = str(int(time.time()))
        try:
            with httpx.Client(trust_env=False, timeout=30.0) as client:
                resp = client.post(API_UPLOAD, data={
                    "appId": self.app_id,
                    "signa": self._sign(ts),
                    "ts": ts,
                    "fileSize": str(len(audio)),
                    "fileName": "audio.wav",
                    "duration": str(self._audio_duration_ms(audio_path)),
                }, files={"content": ("audio.wav", audio, "audio/wav")})
                body = resp.json()
                if body.get("code") != "000000":
                    raise TranscribeFailed(f"upload failed: {body}")
                order_id = body["content"]["orderId"]

                deadline = time.time() + POLL_TIMEOUT_SEC
                while time.time() < deadline:
                    ts = str(int(time.time()))
                    resp = client.post(API_RESULT, data={
                        "appId": self.app_id,
                        "signa": self._sign(ts),
                        "ts": ts,
                        "orderId": order_id,
                    })
                    body = resp.json()
                    if body.get("code") != "000000":
                        raise TranscribeFailed(f"getResult failed: {body}")
                    status = body["content"]["orderInfo"]["status"]
                    if status == 4:  # 完成
                        return self._parse_order_result(body["content"]["orderResult"])
                    if status == -1:
                        raise TranscribeFailed(f"transcribe failed: {body}")
                    time.sleep(POLL_INTERVAL_SEC)
                raise TranscribeFailed("transcribe timeout")
        except TranscribeFailed:
            raise
        except Exception as exc:
            raise TranscribeFailed(str(exc)) from exc
```

- [ ] **Step 6: 实现 asr/__init__.py**

```python
from app.config import settings
from app.services.asr.base import TranscribeFailed, Transcriber, TranscriptResult
from app.services.asr.iflytek import IFlytekTranscriber
from app.services.asr.mock import MockTranscriber

__all__ = [
    "TranscribeFailed", "Transcriber", "TranscriptResult",
    "IFlytekTranscriber", "MockTranscriber", "build_transcriber",
]


def build_transcriber() -> Transcriber:
    if settings.iflytek_app_id and settings.iflytek_api_secret:
        return IFlytekTranscriber(settings.iflytek_app_id, settings.iflytek_api_secret)
    return MockTranscriber()
```

- [ ] **Step 7: 运行测试确认通过 + 全套回归**

Run: `cd backend && uv run pytest -v`
Expected: test_asr 5 个用例 + 既有 16 个全部通过

- [ ] **Step 8: Commit**

```bash
git add backend/ && git commit -m "feat: ASR 适配器层（讯飞转写 + Mock 降级）"
```

---

### Task 2: 口语 schema + 评分 Prompt + 示例数据 + 通用 LLM JSON 调用提取

**Files:**
- Modify: `backend/app/schemas.py`（加口语 schema + EssayOut 加 module）
- Modify: `backend/app/prompt_templates.py`（加口语 rubric + 追问模板）
- Modify: `backend/app/data/sample.py`（加口语示例）
- Create: `backend/app/services/llm_json.py`
- Modify: `backend/app/services/grader.py`（LLMGrader 改用 llm_json，行为不变）
- Test: `backend/tests/test_speaking_schemas.py`

**Interfaces:**
- Consumes: V1 全部
- Produces:
  - `SpeakingBands / SpeakingResult`（`app.schemas`，bands 键为 `fluency/lexical/grammar/pronunciation/overall`）；`EssayOut` 新增 `module: str`
  - `SYSTEM_PROMPT_SPEAKING / USER_PROMPT_SPEAKING_TEMPLATE / FOLLOWUP_PROMPT_TEMPLATE`（`app.prompt_templates`）
  - `SAMPLE_SPEAKING_QUESTION / SAMPLE_SPEAKING_RESULT`（`app.data.sample`）
  - `chat_json(client, model, system, user, schema, max_tokens=8192, attempts=3)`（`app.services.llm_json`）——Task 4 的 SpeakingGrader 与 followup 都用它；V1 `LLMGrader.grade` 改为调用它（对外行为不变）

- [ ] **Step 1: 写失败测试**

`backend/tests/test_speaking_schemas.py`:
```python
import pytest
from pydantic import ValidationError

from app.data.sample import SAMPLE_SPEAKING_RESULT
from app.schemas import SpeakingResult


def test_speaking_result_schema():
    result = SAMPLE_SPEAKING_RESULT
    assert result.bands.fluency <= 9
    assert result.bands.pronunciation <= 9
    assert len(result.annotations) >= 3
    assert len(result.rewrite.split()) >= 40


def test_speaking_result_rejects_writing_bands():
    bad = """{
      "bands": {"task_response": 6.0, "coherence": 6.0, "lexical": 6.0, "grammar": 6.0, "overall": 6.0},
      "annotations": [], "rewrite": "x"
    }"""
    with pytest.raises(ValidationError):
        SpeakingResult.model_validate_json(bad)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_speaking_schemas.py -v`
Expected: FAIL（`ImportError: cannot import name 'SpeakingResult'` 或 `SAMPLE_SPEAKING_RESULT`）

- [ ] **Step 3: schemas.py 追加**

```python
class SpeakingBands(BaseModel):
    fluency: float = Field(ge=0, le=9)
    lexical: float = Field(ge=0, le=9)
    grammar: float = Field(ge=0, le=9)
    pronunciation: float = Field(ge=0, le=9)
    overall: float = Field(ge=0, le=9)


class SpeakingResult(BaseModel):
    bands: SpeakingBands
    annotations: list[Annotation]
    rewrite: str
```

`EssayOut` 加一行：`module: str`（ORM 已有该列，from_attributes 自动取值）。

- [ ] **Step 4: prompt_templates.py 追加**

```python
SYSTEM_PROMPT_SPEAKING = """你是一名资深雅思口语考官，根据考生的回答转写文本（ASR 转写，可能含少量识别误差），按雅思官方口语四项标准评分：
1. Fluency & Coherence（流利度与连贯性）：表达的连续度、自我重复与停顿、话语标记使用、逻辑展开
2. Lexical Resource（词汇资源）：词汇广度与准确性、习语与搭配、同义替换
3. Grammatical Range & Accuracy（语法多样性与准确性）：句式多样性、语法错误密度
4. Pronunciation（发音）：你只能根据 ASR 转写置信度与文本特征做间接侧面评估（置信度见用户消息）。
   评分时保持保守并在 issue 中说明这是间接评估。

评分规则：
- 四项子分与 overall 均为 0-9，允许 0.5 步进；overall 按官方均分取整规则
- annotations 只批注最有教学价值的问题，最多 8 条，按严重程度排序：
  sentence_index 为该句在转写文本中的序号（从 0 开始，按句号/问号/叹号切分），
  original 抄录原句，issue 用中文说明问题（不超过 50 字），suggestion 只给修改后的句子，
  error_type 从以下枚举中选一个：主谓一致、时态、单复数、冠词、词汇搭配、句式、自我重复、流利度、离题、其他
- rewrite 给出该问题 7.5 分水平的口语化改写回答（自然口语风格，80-150 词）

只输出一个 JSON 对象，不要输出任何其他文字。JSON schema：
{
  "bands": {"fluency": 6.0, "lexical": 6.0, "grammar": 6.0, "pronunciation": 6.0, "overall": 6.0},
  "annotations": [{"sentence_index": 0, "original": "...", "issue": "...", "suggestion": "...", "error_type": "时态"}],
  "rewrite": "..."
}"""

USER_PROMPT_SPEAKING_TEMPLATE = """【考官问题】
{question}

【考生回答转写】（ASR 置信度 {confidence}）
{transcript}"""

FOLLOWUP_PROMPT_TEMPLATE = """你是一名雅思口语 Part 3 考官，正在进行深度讨论。话题：{topic}

到目前为止的对话：
{history}

请根据考生上一个回答的内容，生成一个自然的追问（深挖原因/比较/利弊/未来趋势等角度）。
只输出追问问题本身（一句英文），不要输出任何其他文字。"""
```

- [ ] **Step 5: sample.py 追加口语示例**

```python
SAMPLE_SPEAKING_QUESTION = "Do you prefer working from home or in an office?"

SAMPLE_SPEAKING_RESULT = SpeakingResult(
    bands=SpeakingBands(fluency=5.5, lexical=5.5, grammar=5.5, pronunciation=6.5, overall=5.5),
    annotations=[
        Annotation(
            sentence_index=1,
            original="First, people can save time because they don't need to, you know, take the bus or subway for two hours every day.",
            issue="插入语 you know 与冗长从句打断流利度；通勤有地道词 commute。",
            suggestion="First of all, people save a great deal of time because they no longer have to commute for two hours every day.",
            error_type="流利度",
        ),
        Annotation(
            sentence_index=3,
            original="But sometimes I feel lonely, because I cannot talk with my colleagues face to face.",
            issue="词汇简单重复 feel/talk；可用 isolated / interact in person 提升档次。",
            suggestion="That said, I sometimes feel isolated because I can't interact with my colleagues in person.",
            error_type="词汇搭配",
        ),
        Annotation(
            sentence_index=4,
            original="So I think it depends on the person, but for me the good things is more than the bad things.",
            issue="主谓一致与表达中式：the good things is 应为 are；the pros outweigh the cons 更地道。",
            suggestion="So it depends on the person, but for me the pros definitely outweigh the cons.",
            error_type="主谓一致",
        ),
    ],
    rewrite="""Well, to be honest, I'd say I prefer working from home. The biggest reason is that it saves me a huge amount of time — I used to spend nearly two hours commuting every day, and now I can use that time to exercise or just sleep a bit longer. On top of that, I find it much easier to concentrate at home because there are fewer distractions than in a busy office. Of course, I do miss chatting with my colleagues in person sometimes, but overall, for me, the benefits definitely outweigh the drawbacks.""",
)
```

（`SAMPLE_SPEAKING_RESULT` 放在文件末尾，复用本文件已 import 的 `Annotation`；需补 import `SpeakingBands, SpeakingResult`——sample.py 头部 import 行相应扩展。）

- [ ] **Step 6: 提取 llm_json.py 并改造 grader.py（行为不变）**

`backend/app/services/llm_json.py`:
```python
import logging
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMCallFailed(Exception):
    pass


def chat_json(client: OpenAI, model: str, system: str, user: str,
              schema: type[T], max_tokens: int = 8192, attempts: int = 3) -> T:
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
                temperature=0.2,
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
```

`grader.py` 改造：`LLMGrader.grade` 方法体替换为：
```python
    def grade(self, prompt_text: str, content: str) -> GradingResult:
        try:
            return chat_json(
                self.client, self.model, SYSTEM_PROMPT,
                USER_PROMPT_TEMPLATE.format(prompt_text=prompt_text, content=content),
                GradingResult,
            )
        except LLMCallFailed as exc:
            raise GradingFailed(str(exc)) from exc
```
（保留 `GradingFailed` 类与 `build_grader/run_grading/mark_writing_learned` 不动；`GradingFailed` 仍是 run_grading 捕获的类型。`import` 相应更新。）

- [ ] **Step 7: 全套回归**

Run: `cd backend && uv run pytest -v`
Expected: 全部通过（含 V1 的 test_grader.py——chat_json 提取后重试/补`}`行为不变，回归测试必须仍绿）

- [ ] **Step 8: Commit**

```bash
git add backend/ && git commit -m "feat: 口语评分 schema/prompt/示例 + 通用 LLM JSON 调用提取"
```

---

### Task 3: 数据模型变更 + 口语种子数据

**Files:**
- Modify: `backend/app/models.py`（加 SpeakingCard/SpeakingSession，Practice 加两列）
- Create: `backend/app/seed_speaking.py`
- Modify: `backend/app/main.py`（startup 加 seed_speaking_db）
- Modify: `.gitignore`（uploads/、tts_cache/）
- Test: `backend/tests/test_speaking_models.py`

**Interfaces:**
- Consumes: V1 models
- Produces:
  - `SpeakingCard`（`id, part: int, topic: str, season: str, payload: dict, created_at`）
  - `SpeakingSession`（`id, user_id, card_id, status: str(active/done), current_question: str, turn_count: int, created_at`，relationship `card`）
  - `Practice.audio_path: str = ""`、`Practice.session_id: int | None`（FK speaking_session.id）
  - `seed_speaking_db(session)`（幂等）：写入 SPEAKING_CARDS（Part1×5、Part2×8、Part3×5，season="2026-09"）+ 口语能力树 16 节点（`speaking.` 前缀）

- [ ] **Step 1: 写失败测试**

`backend/tests/test_speaking_models.py`:
```python
from sqlalchemy import select

from app.database import Base, make_session_factory
from app.models import Practice, SpeakingCard, SpeakingSession, User
from app.seed_speaking import seed_speaking_db


def make_db(tmp_path):
    factory = make_session_factory(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(factory.kw["bind"])
    return factory


def test_speaking_session_and_practice_link(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    s.add(User(id=1))
    s.add(SpeakingCard(id=1, part=2, topic="Describe a person", season="2026-09",
                       payload={"cues": ["who", "what", "why"]}))
    s.add(SpeakingSession(id=1, user_id=1, card_id=1, status="active",
                          current_question="Describe a person you admire.", turn_count=0))
    s.add(Practice(id=1, user_id=1, module="speaking", session_id=1,
                   prompt_title="Describe a person", prompt_text="Describe a person you admire.",
                   content="transcript", audio_path="uploads/x.wav", word_count=1))
    s.commit()

    p = s.get(Practice, 1)
    assert p.module == "speaking"
    assert p.session_id == 1
    assert p.audio_path == "uploads/x.wav"
    sess = s.get(SpeakingSession, 1)
    assert sess.card.topic == "Describe a person"


def test_seed_speaking_idempotent(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    seed_speaking_db(s)
    seed_speaking_db(s)  # 第二次不重复
    cards = s.scalars(select(SpeakingCard)).all()
    assert len([c for c in cards if c.part == 1]) == 5
    assert len([c for c in cards if c.part == 2]) == 8
    assert len([c for c in cards if c.part == 3]) == 5
    from app.models import SkillNode
    speaking_nodes = s.scalars(
        select(SkillNode).where(SkillNode.code.like("speaking.%"))).all()
    assert len(speaking_nodes) == 16
    assert all(n.module == "speaking" for n in speaking_nodes)
    s.close()
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_speaking_models.py -v`
Expected: FAIL，`ImportError: cannot import name 'SpeakingCard'`

- [ ] **Step 3: models.py 追加/修改**

文件末尾追加：
```python
class SpeakingCard(Base):
    __tablename__ = "speaking_card"

    id: Mapped[int] = mapped_column(primary_key=True)
    part: Mapped[int] = mapped_column(Integer)  # 1/2/3
    topic: Mapped[str] = mapped_column(String(300))
    season: Mapped[str] = mapped_column(String(20), default="2026-09")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    sessions: Mapped[list["SpeakingSession"]] = relationship(back_populates="card")


class SpeakingSession(Base):
    __tablename__ = "speaking_session"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), default=1)
    card_id: Mapped[int] = mapped_column(ForeignKey("speaking_card.id"))
    status: Mapped[str] = mapped_column(String(20), default="active")  # active/done
    current_question: Mapped[str] = mapped_column(Text, default="")
    turn_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    card: Mapped[SpeakingCard] = relationship(back_populates="sessions")
```

`Practice` 类中追加两个字段：
```python
    audio_path: Mapped[str] = mapped_column(String(500), default="")
    session_id: Mapped[int | None] = mapped_column(ForeignKey("speaking_session.id"), nullable=True)
```

- [ ] **Step 4: 实现 seed_speaking.py**

`backend/app/seed_speaking.py`:
```python
from sqlalchemy import select

from app.models import SkillNode, SpeakingCard

SPEAKING_NODES: list[tuple[str, str, str | None, int]] = [
    ("speaking.fc", "流利度与连贯（FC）", None, 0),
    ("speaking.fc.length", "持续表达不冷场", "speaking.fc", 0),
    ("speaking.fc.hesitation", "减少停顿与自我重复", "speaking.fc", 1),
    ("speaking.fc.connectives", "话语标记使用", "speaking.fc", 2),
    ("speaking.lr", "词汇资源（LR）", None, 1),
    ("speaking.lr.idiom", "习语与搭配", "speaking.lr", 0),
    ("speaking.lr.paraphrase", "同义替换", "speaking.lr", 1),
    ("speaking.lr.topic", "话题词汇", "speaking.lr", 2),
    ("speaking.gra", "语法（GRA）", None, 2),
    ("speaking.gra.complex", "复杂句式", "speaking.gra", 0),
    ("speaking.gra.tense", "时态正确", "speaking.gra", 1),
    ("speaking.gra.agreement", "主谓一致", "speaking.gra", 2),
    ("speaking.pr", "发音（P）", None, 3),
    ("speaking.pr.intelligibility", "清晰度", "speaking.pr", 0),
    ("speaking.pr.intonation", "语调与重音", "speaking.pr", 1),
    ("speaking.p2.structure", "Cue Card 结构（背景-经过-感受）", None, 4),
    ("speaking.p1.direct", "直接回答 + 原因扩展", None, 5),
    ("speaking.p3.depth", "深度论证（观点-原因-例子）", None, 6),
]

SPEAKING_CARDS: list[dict] = [
    # Part 1：日常问答，每题 4 问
    {"part": 1, "topic": "Home & Accommodation", "payload": {"questions": [
        "Do you live in a house or an apartment?",
        "What do you like most about your home?",
        "Is there anything you would like to change about your home?",
        "Do you plan to live there for a long time?",
    ]}},
    {"part": 1, "topic": "Work & Study", "payload": {"questions": [
        "Do you work or are you a student?",
        "What do you find most interesting about your work or studies?",
        "Do you prefer to work in the morning or in the evening?",
        "Would you like to change your job or major in the future?",
    ]}},
    {"part": 1, "topic": "Reading", "payload": {"questions": [
        "Do you like reading books?",
        "What kind of books do you prefer?",
        "Did you read a lot when you were a child?",
        "Do you think e-books will replace paper books?",
    ]}},
    {"part": 1, "topic": "Weather", "payload": {"questions": [
        "What is the weather like in your hometown?",
        "Do you prefer hot or cold weather?",
        "Does the weather affect your mood?",
        "What do you usually do on rainy days?",
    ]}},
    {"part": 1, "topic": "Technology", "payload": {"questions": [
        "How often do you use your smartphone?",
        "What apps do you use most?",
        "Do you think technology makes life easier?",
        "Is there any technology you find difficult to use?",
    ]}},
    # Part 2：cue card
    {"part": 2, "topic": "Describe a person who has inspired you", "payload": {"cues": [
        "who this person is", "how you know this person",
        "what this person has done", "and explain why he or she has inspired you",
    ]}},
    {"part": 2, "topic": "Describe a place you visited that left a deep impression", "payload": {"cues": [
        "where it is", "when you visited it",
        "what you did there", "and explain why it impressed you",
    ]}},
    {"part": 2, "topic": "Describe a skill you would like to learn", "payload": {"cues": [
        "what the skill is", "why you want to learn it",
        "how you would learn it", "and explain how it would help you",
    ]}},
    {"part": 2, "topic": "Describe a difficult decision you once made", "payload": {"cues": [
        "what the decision was", "when you made it",
        "what the result was", "and explain why it was difficult",
    ]}},
    {"part": 2, "topic": "Describe a book or film that you enjoyed", "payload": {"cues": [
        "what it is", "when you read or watched it",
        "what it is about", "and explain why you enjoyed it",
    ]}},
    {"part": 2, "topic": "Describe a time when you helped someone", "payload": {"cues": [
        "who you helped", "how you helped them",
        "how they responded", "and explain how you felt about it",
    ]}},
    {"part": 2, "topic": "Describe a city you would like to visit", "payload": {"cues": [
        "where it is", "what it is famous for",
        "what you would do there", "and explain why you want to visit it",
    ]}},
    {"part": 2, "topic": "Describe an important event in your life", "payload": {"cues": [
        "what the event was", "when it happened",
        "who was with you", "and explain why it was important",
    ]}},
    # Part 3：深度讨论，预设 3 问 + LLM 追问
    {"part": 3, "topic": "Inspiration and role models", "payload": {"questions": [
        "Do you think celebrities make good role models for young people?",
        "How do role models influence people's choices in life?",
        "Is it better to be inspired by famous people or by people around us?",
    ]}},
    {"part": 3, "topic": "Travel and tourism", "payload": {"questions": [
        "How has tourism changed the places people visit?",
        "Do the benefits of tourism outweigh its drawbacks?",
        "How do you think travel will change in the future?",
    ]}},
    {"part": 3, "topic": "Learning and education", "payload": {"questions": [
        "Is it better to learn skills from teachers or by yourself?",
        "How has technology changed the way people learn new skills?",
        "Should schools focus more on practical skills or academic knowledge?",
    ]}},
    {"part": 3, "topic": "Decisions and choices", "payload": {"questions": [
        "Why do some people find it hard to make decisions?",
        "Should young people make big decisions on their own?",
        "How has the internet changed the way people make choices?",
    ]}},
    {"part": 3, "topic": "Cities and urban life", "payload": {"questions": [
        "What are the advantages of living in a big city?",
        "Do you think cities are becoming too crowded?",
        "How will cities change in the next twenty years?",
    ]}},
]


def seed_speaking_db(session) -> None:
    """幂等写入口语能力树节点与当季话题卡。"""
    has_nodes = session.scalars(
        select(SkillNode.id).where(SkillNode.code.like("speaking.%"))).first()
    if not has_nodes:
        code_to_node: dict[str, SkillNode] = {}
        for code, title, parent_code, sort_order in SPEAKING_NODES:
            node = SkillNode(
                module="speaking", code=code, title=title,
                parent_id=code_to_node[parent_code].id if parent_code else None,
                sort_order=sort_order,
            )
            session.add(node)
            session.flush()
            code_to_node[code] = node
    has_cards = session.scalars(select(SpeakingCard.id)).first()
    if not has_cards:
        for card in SPEAKING_CARDS:
            session.add(SpeakingCard(part=card["part"], topic=card["topic"],
                                     season="2026-09", payload=card["payload"]))
    session.commit()
```

- [ ] **Step 5: main.py startup 与 .gitignore**

`main.py` 的 `init_db` 中 `seed_db(session)` 之后加：
```python
        from app.seed_speaking import seed_speaking_db
        seed_speaking_db(session)
```

`.gitignore` 追加：
```
backend/uploads/
backend/tts_cache/
```

- [ ] **Step 6: 测试通过 + 全套回归**

Run: `cd backend && uv run pytest -v`
Expected: 全部通过（既有 16 + 新增）

注意：V1 的 `test_api.py` 断言 `masteries == nodes`（writing 节点数），本任务不动 writing seed，不应破坏它；若失败检查是否误触 writing 种子逻辑。

- [ ] **Step 7: Commit**

```bash
git add backend/ .gitignore && git commit -m "feat: 口语数据模型 + 当季话题卡与能力树种子"
```

---

### Task 4: 口语评分管线 + 追问生成 + TTS 服务

**Files:**
- Create: `backend/app/services/speaking_grader.py`
- Create: `backend/app/services/followup.py`
- Create: `backend/app/services/tts.py`
- Modify: `backend/pyproject.toml`（加 edge-tts 依赖）
- Test: `backend/tests/test_speaking_grader.py`

**Interfaces:**
- Consumes: `chat_json`（Task 2）、`build_transcriber / TranscribeFailed / TranscriptResult`（Task 1）、`SYSTEM_PROMPT_SPEAKING / USER_PROMPT_SPEAKING_TEMPLATE / FOLLOWUP_PROMPT_TEMPLATE`（Task 2）、`SpeakingCard / SpeakingSession / Practice / AIFeedback / ErrorItem / SkillNode / SkillMastery`（Task 3/V1）
- Produces:
  - `SpeakingGrader`：`__init__(api_key, base_url, model)`，`grade(self, question: str, transcript: str, confidence: float) -> SpeakingResult`，属性 `is_mock = False`、`model`
  - `build_speaking_grader()`：有 DeepSeek key → SpeakingGrader，否则 `MockSpeakingGrader`（返回 `SAMPLE_SPEAKING_RESULT`，`is_mock = True`，`model = "mock"`）
  - `run_speaking_turn(practice_id: int, session_factory, transcriber=None, grader=None) -> None`：转写 → 评分 → 落库 → 推进会话（Task 5 注册为后台任务）
  - `generate_followup(topic: str, history: list[dict]) -> str | None`（`app.services.followup`；history 元素 `{"question": str, "answer": str}`）
  - `tts_url_for(text: str) -> str | None`（`app.services.tts`）：返回 `/api/tts/{hash}.mp3`，失败返回 None

- [ ] **Step 1: 写失败测试**

`backend/tests/test_speaking_grader.py`:
```python
from sqlalchemy import select

from app.data.sample import SAMPLE_SPEAKING_RESULT
from app.database import Base, make_session_factory
from app.models import (AIFeedback, ErrorItem, Practice, SkillMastery, SkillNode,
                        SpeakingCard, SpeakingSession, User)
from app.seed_speaking import seed_speaking_db
from app.services.asr.base import TranscribeFailed, TranscriptResult
from app.services.speaking_grader import run_speaking_turn


def make_db(tmp_path):
    factory = make_session_factory(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(factory.kw["bind"])
    return factory


def seed(factory, part=1, questions=None):
    s = factory()
    s.add(User(id=1))
    seed_speaking_db(s)
    payload = {"questions": questions or ["Q1?", "Q2?"]}
    s.add(SpeakingCard(id=99, part=part, topic="T", season="2026-09", payload=payload))
    s.add(SpeakingSession(id=99, user_id=1, card_id=99, status="active",
                          current_question="Q1?", turn_count=0))
    s.add(Practice(id=99, user_id=1, module="speaking", session_id=99,
                   prompt_title="T", prompt_text="Q1?", content="",
                   audio_path="x.wav", status="pending"))
    s.commit()
    s.close()


class FakeTranscriber:
    is_mock = True

    def transcribe(self, audio_path):
        return TranscriptResult(text="Well I think it is good things.", confidence=0.9)


class BrokenTranscriber:
    is_mock = True

    def transcribe(self, audio_path):
        raise TranscribeFailed("asr down")


class FakeSpeakingGrader:
    is_mock = False
    model = "fake"

    def grade(self, question, transcript, confidence):
        return SAMPLE_SPEAKING_RESULT


def test_speaking_turn_success_and_session_advance(tmp_path):
    factory = make_db(tmp_path)
    seed(factory)
    run_speaking_turn(99, factory, transcriber=FakeTranscriber(), grader=FakeSpeakingGrader())

    s = factory()
    p = s.get(Practice, 99)
    assert p.status == "done"
    assert p.content.startswith("Well I think")  # 转写文本落库
    assert p.total_band == 5.5
    fb = s.scalars(select(AIFeedback).where(AIFeedback.practice_id == 99)).one()
    assert fb.bands["fluency"] == 5.5
    errors = s.scalars(select(ErrorItem).where(ErrorItem.practice_id == 99)).all()
    assert {e.error_type for e in errors} == {"流利度", "词汇搭配", "主谓一致"}
    # 会话推进到第二问
    sess = s.get(SpeakingSession, 99)
    assert sess.turn_count == 1
    assert sess.current_question == "Q2?"
    assert sess.status == "active"
    # 口语能力点标黄
    masteries = s.scalars(select(SkillMastery)).all()
    speaking_nodes = s.scalars(select(SkillNode.id).where(SkillNode.module == "speaking")).all()
    assert {m.node_id for m in masteries} == set(speaking_nodes)
    s.close()


def test_session_completes_after_last_question(tmp_path):
    factory = make_db(tmp_path)
    seed(factory, questions=["Q1?"])
    run_speaking_turn(99, factory, transcriber=FakeTranscriber(), grader=FakeSpeakingGrader())
    s = factory()
    sess = s.get(SpeakingSession, 99)
    assert sess.status == "done"
    assert sess.turn_count == 1
    s.close()


def test_transcribe_failure_marks_needs_review(tmp_path):
    factory = make_db(tmp_path)
    seed(factory)
    run_speaking_turn(99, factory, transcriber=BrokenTranscriber(), grader=FakeSpeakingGrader())
    s = factory()
    assert s.get(Practice, 99).status == "needs_review"
    assert s.scalars(select(AIFeedback)).all() == []
    s.close()
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_speaking_grader.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.services.speaking_grader'`

- [ ] **Step 3: 实现 speaking_grader.py**

`backend/app/services/speaking_grader.py`:
```python
import logging

from openai import OpenAI
from sqlalchemy import select

from app.config import settings
from app.data.sample import SAMPLE_SPEAKING_RESULT
from app.models import (AIFeedback, ErrorItem, Practice, SkillMastery, SkillNode,
                        SpeakingSession)
from app.prompt_templates import SYSTEM_PROMPT_SPEAKING, USER_PROMPT_SPEAKING_TEMPLATE
from app.schemas import SpeakingResult
from app.services.asr import TranscribeFailed, build_transcriber
from app.services.llm_json import LLMCallFailed, chat_json

logger = logging.getLogger(__name__)

PART3_MAX_TURNS = 5  # Part 3：预设问用完后由 LLM 追问，总轮数上限


class SpeakingGrader:
    is_mock = False

    def __init__(self, api_key: str, base_url: str, model: str):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def grade(self, question: str, transcript: str, confidence: float) -> SpeakingResult:
        return chat_json(
            self.client, self.model, SYSTEM_PROMPT_SPEAKING,
            USER_PROMPT_SPEAKING_TEMPLATE.format(
                question=question, transcript=transcript, confidence=confidence),
            SpeakingResult,
        )


class MockSpeakingGrader:
    is_mock = True
    model = "mock"

    def grade(self, question: str, transcript: str, confidence: float) -> SpeakingResult:
        return SAMPLE_SPEAKING_RESULT


def build_speaking_grader():
    if settings.deepseek_api_key:
        return SpeakingGrader(settings.deepseek_api_key, settings.deepseek_base_url,
                              settings.deepseek_model)
    return MockSpeakingGrader()


def mark_speaking_learned(session, user_id: int) -> int:
    node_ids = session.scalars(select(SkillNode.id).where(SkillNode.module == "speaking")).all()
    existing = set(session.scalars(
        select(SkillMastery.node_id).where(SkillMastery.user_id == user_id)).all())
    added = 0
    for node_id in node_ids:
        if node_id not in existing:
            session.add(SkillMastery(user_id=user_id, node_id=node_id, status="learned",
                                     evidence={"source": "speaking_turn_graded"}))
            added += 1
    return added


def _next_question(session, practice: Practice) -> str | None:
    """根据 card part 与 turn_count 决定下一问；None 表示会话结束。"""
    speaking_session = session.get(SpeakingSession, practice.session_id)
    card = speaking_session.card
    questions: list[str] = card.payload.get("questions", [])
    turn = speaking_session.turn_count  # 已完成的轮数
    if card.part == 2:
        return None
    if turn < len(questions):
        return questions[turn]
    if card.part == 3 and turn < PART3_MAX_TURNS:
        from app.services.followup import generate_followup

        history = [
            {"question": p.prompt_text, "answer": p.content}
            for p in session.scalars(
                select(Practice)
                .where(Practice.session_id == speaking_session.id, Practice.status == "done")
                .order_by(Practice.created_at)
            ).all()
        ]
        return generate_followup(card.topic, history)
    return None


def run_speaking_turn(practice_id: int, session_factory, transcriber=None, grader=None) -> None:
    session = session_factory()
    try:
        practice = session.get(Practice, practice_id)
        if practice is None:
            return
        if transcriber is None:
            transcriber = build_transcriber()
        if grader is None:
            grader = build_speaking_grader()
        try:
            transcript = transcriber.transcribe(practice.audio_path)
        except TranscribeFailed as exc:
            practice.status = "needs_review"
            session.commit()
            logger.error("transcribe failed for practice %s: %s", practice_id, exc)
            return
        practice.content = transcript.text
        practice.word_count = len(transcript.text.split())

        try:
            result = grader.grade(practice.prompt_text, transcript.text, transcript.confidence)
        except LLMCallFailed as exc:
            practice.status = "needs_review"
            session.commit()
            logger.error("speaking grading failed for practice %s: %s", practice_id, exc)
            return

        session.add(AIFeedback(
            practice_id=practice.id,
            bands=result.bands.model_dump(),
            annotations=[a.model_dump() for a in result.annotations],
            rewrite=result.rewrite,
            model=getattr(grader, "model", "unknown"),
            is_mock=bool(transcriber.is_mock or getattr(grader, "is_mock", False)),
        ))
        practice.status = "done"
        practice.total_band = result.bands.overall
        for annotation in result.annotations:
            if annotation.error_type:
                session.add(ErrorItem(
                    user_id=practice.user_id,
                    practice_id=practice.id,
                    error_type=annotation.error_type,
                    context=annotation.original,
                ))
        mark_speaking_learned(session, practice.user_id)

        # 推进会话
        speaking_session = session.get(SpeakingSession, practice.session_id)
        speaking_session.turn_count += 1
        next_q = _next_question(session, practice)
        if next_q is None:
            speaking_session.status = "done"
            speaking_session.current_question = ""
        else:
            speaking_session.current_question = next_q
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("run_speaking_turn failed for practice %s", practice_id)
        try:
            practice = session.get(Practice, practice_id)
            if practice is not None:
                practice.status = "needs_review"
                session.commit()
        except Exception:
            logger.exception("failed to mark practice %s needs_review", practice_id)
    finally:
        session.close()
```

- [ ] **Step 4: 实现 followup.py**

`backend/app/services/followup.py`:
```python
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
```

- [ ] **Step 5: 实现 tts.py + 加依赖**

`backend/app/services/tts.py`:
```python
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
```

`pyproject.toml` dependencies 追加 `"edge-tts>=7"`，然后 `uv sync`（unset 代理）。

- [ ] **Step 6: 测试通过 + 全套回归**

Run: `cd backend && uv run pytest -v`
Expected: 全部通过

- [ ] **Step 7: Commit**

```bash
git add backend/ && git commit -m "feat: 口语评分管线 + Part 3 追问生成 + TTS 服务"
```

---

### Task 5: 口语 API 路由

**Files:**
- Create: `backend/app/api/speaking.py`
- Modify: `backend/app/main.py`（挂 speaking 路由 + tts 静态路由）
- Modify: `backend/app/schemas.py`（加口语 API 响应 schema）
- Test: `backend/tests/test_speaking_api.py`

**Interfaces:**
- Consumes: Task 1-4 全部
- Produces（前端 Task 6-7 严格按此对接）:
  - `GET /api/speaking/cards?part=1` → `list[SpeakingCardOut]`（`{id, part, topic, season, payload}`）
  - `POST /api/speaking/sessions`，body `{"card_id": int}` → `SessionOut`（`{id, part, topic, status, question, tts_url}`）
  - `POST /api/speaking/turns`，multipart 表单字段 `session_id: int` + 文件 `audio`（.wav）→ 202 `{"practice_id": int}`；>5MB 或非 wav → 413/422
  - `GET /api/speaking/turns/{practice_id}` → `TurnDetail`（`{practice_id, status, transcript, feedback: FeedbackOut|null, next_question: str|null, next_tts_url: str|null, session_done: bool}`）
  - `POST /api/speaking/sessions/{id}/finish` → `SessionSummary`（`{session_id, avg_band: float|null, turns: [{question, transcript, total_band}]}`），把会话标 done
  - `GET /api/tts/{filename}` → mp3 文件（filename 仅允许 `^[a-f0-9]{16}\.mp3$`，否则 404）

- [ ] **Step 1: schemas.py 追加 API schema**

```python
class SpeakingCardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    part: int
    topic: str
    season: str
    payload: dict


class SessionCreate(BaseModel):
    card_id: int


class SessionOut(BaseModel):
    id: int
    part: int
    topic: str
    status: str
    question: str
    tts_url: str | None


class TurnDetail(BaseModel):
    practice_id: int
    status: str
    transcript: str | None
    feedback: FeedbackOut | None
    next_question: str | None
    next_tts_url: str | None
    session_done: bool


class TurnSummaryItem(BaseModel):
    question: str
    transcript: str
    total_band: float | None


class SessionSummary(BaseModel):
    session_id: int
    avg_band: float | None
    turns: list[TurnSummaryItem]
```

- [ ] **Step 2: 写失败测试**

`backend/tests/test_speaking_api.py`:
```python
import io
import wave

import pytest
from fastapi.testclient import TestClient

from app.database import Base, make_session_factory
from app.main import app
from app.models import User
from app.seed import seed_db
from app.seed_speaking import seed_speaking_db


@pytest.fixture()
def client(tmp_path, monkeypatch):
    factory = make_session_factory(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(factory.kw["bind"])
    s = factory()
    s.add(User(id=1))
    s.commit()
    seed_db(s)
    seed_speaking_db(s)
    s.close()
    monkeypatch.setattr("app.config.settings.deepseek_api_key", "")
    monkeypatch.setattr("app.config.settings.iflytek_app_id", "")
    monkeypatch.setattr("app.config.settings.iflytek_api_secret", "")
    monkeypatch.setattr("app.config.settings.uploads_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr("app.config.settings.tts_cache_dir", str(tmp_path / "tts"))
    monkeypatch.setattr(app.state, "session_factory", factory)
    return TestClient(app)


def make_wav_bytes() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 16000)  # 1 秒静音
    return buf.getvalue()


def test_cards_endpoint(client):
    cards = client.get("/api/speaking/cards", params={"part": 2}).json()
    assert len(cards) == 8
    assert cards[0]["payload"]["cues"]


def test_full_speaking_flow(client):
    cards = client.get("/api/speaking/cards", params={"part": 1}).json()
    sess = client.post("/api/speaking/sessions", json={"card_id": cards[0]["id"]}).json()
    assert sess["part"] == 1
    assert sess["question"]  # 第一问
    assert sess["status"] == "active"

    # 提交两轮（Part 1 该卡 4 问，会话应继续）
    for _ in range(2):
        resp = client.post("/api/speaking/turns",
                           data={"session_id": str(sess["id"])},
                           files={"audio": ("a.wav", make_wav_bytes(), "audio/wav")})
        assert resp.status_code == 202
        pid = resp.json()["practice_id"]
        detail = client.get(f"/api/speaking/turns/{pid}").json()
        assert detail["status"] == "done"
        assert detail["transcript"]
        assert detail["feedback"]["is_mock"] is True
        assert detail["session_done"] is False
        assert detail["next_question"]

    summary = client.post(f"/api/speaking/sessions/{sess['id']}/finish").json()
    assert summary["session_id"] == sess["id"]
    assert len(summary["turns"]) == 2
    assert summary["avg_band"] == 5.5


def test_upload_validation(client):
    cards = client.get("/api/speaking/cards", params={"part": 1}).json()
    sess = client.post("/api/speaking/sessions", json={"card_id": cards[0]["id"]}).json()
    # 非 wav 文件
    resp = client.post("/api/speaking/turns",
                       data={"session_id": str(sess["id"])},
                       files={"audio": ("a.mp3", b"fake", "audio/mpeg")})
    assert resp.status_code == 422


def test_tts_filename_guard(client):
    assert client.get("/api/tts/../etc/passwd").status_code == 404
    assert client.get("/api/tts/nothexname.mp3").status_code == 404
```

- [ ] **Step 3: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_speaking_api.py -v`
Expected: FAIL，404 / ModuleNotFoundError

- [ ] **Step 4: 实现 api/speaking.py**

`backend/app/api/speaking.py`:
```python
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.config import settings
from app.models import AIFeedback, Practice, SpeakingCard, SpeakingSession
from app.schemas import (FeedbackOut, SessionCreate, SessionOut, SessionSummary,
                         SpeakingCardOut, TurnDetail, TurnSummaryItem)
from app.services.speaking_grader import run_speaking_turn
from app.services.tts import tts_url_for

router = APIRouter(prefix="/api")

MAX_AUDIO_BYTES = 5 * 1024 * 1024
TTS_NAME_RE = re.compile(r"^[a-f0-9]{16}\.mp3$")


def get_session(request: Request):
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


@router.get("/speaking/cards", response_model=list[SpeakingCardOut])
def list_cards(part: int, session=Depends(get_session)):
    return session.scalars(
        select(SpeakingCard).where(SpeakingCard.part == part)
        .order_by(SpeakingCard.id)).all()


@router.post("/speaking/sessions", response_model=SessionOut, status_code=201)
def create_session(payload: SessionCreate, session=Depends(get_session)):
    card = session.get(SpeakingCard, payload.card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="话题卡不存在")
    if card.part == 2:
        cues = "、".join(card.payload.get("cues", []))
        question = f"{card.topic}\nYou should say: {cues}"
    else:
        question = card.payload["questions"][0]
    speaking_session = SpeakingSession(
        user_id=1, card_id=card.id, current_question=question)
    session.add(speaking_session)
    session.commit()
    session.refresh(speaking_session)
    return SessionOut(
        id=speaking_session.id, part=card.part, topic=card.topic,
        status=speaking_session.status, question=question,
        tts_url=tts_url_for(question),
    )


@router.post("/speaking/turns", status_code=202)
def submit_turn(request: Request, background: BackgroundTasks,
                session_id: int = Form(...), audio: UploadFile = File(...),
                session=Depends(get_session)):
    speaking_session = session.get(SpeakingSession, session_id)
    if speaking_session is None or speaking_session.status != "active":
        raise HTTPException(status_code=404, detail="会话不存在或已结束")
    if not (audio.filename or "").lower().endswith(".wav"):
        raise HTTPException(status_code=422, detail="仅支持 .wav 音频")
    data = audio.file.read()
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="音频超过 5MB 上限")

    uploads = Path(settings.uploads_dir)
    uploads.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.wav"
    (uploads / filename).write_bytes(data)

    practice = Practice(
        user_id=1, module="speaking", session_id=speaking_session.id,
        prompt_title=speaking_session.card.topic,
        prompt_text=speaking_session.current_question,
        content="", audio_path=str(uploads / filename), status="pending",
    )
    session.add(practice)
    session.commit()
    session.refresh(practice)
    background.add_task(run_speaking_turn, practice.id, request.app.state.session_factory)
    return {"practice_id": practice.id}


@router.get("/speaking/turns/{practice_id}", response_model=TurnDetail)
def get_turn(practice_id: int, session=Depends(get_session)):
    practice = session.get(Practice, practice_id)
    if practice is None or practice.module != "speaking":
        raise HTTPException(status_code=404, detail="练习不存在")
    feedback = None
    if practice.feedback:
        feedback = FeedbackOut(
            bands=practice.feedback.bands,
            annotations=practice.feedback.annotations,
            rewrite=practice.feedback.rewrite,
            is_mock=practice.feedback.is_mock,
        )
    speaking_session = session.get(SpeakingSession, practice.session_id)
    session_done = speaking_session.status == "done"
    # 仅当本轮评分完成后才把"下一问"暴露给前端（pending 期间 current_question 还是旧问题）
    next_q = speaking_session.current_question if (
        not session_done and practice.status == "done") else None
    return TurnDetail(
        practice_id=practice.id,
        status=practice.status,
        transcript=practice.content or None,
        feedback=feedback,
        next_question=next_q,
        next_tts_url=tts_url_for(next_q) if next_q else None,
        session_done=session_done,
    )


@router.post("/speaking/sessions/{session_id}/finish", response_model=SessionSummary)
def finish_session(session_id: int, session=Depends(get_session)):
    speaking_session = session.get(SpeakingSession, session_id)
    if speaking_session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    speaking_session.status = "done"
    turns = session.scalars(
        select(Practice)
        .where(Practice.session_id == session_id, Practice.status == "done")
        .order_by(Practice.created_at)).all()
    session.commit()
    bands = [t.total_band for t in turns if t.total_band is not None]
    return SessionSummary(
        session_id=session_id,
        avg_band=round(sum(bands) / len(bands), 1) if bands else None,
        turns=[TurnSummaryItem(question=t.prompt_text, transcript=t.content,
                               total_band=t.total_band) for t in turns],
    )


@router.get("/tts/{filename}")
def get_tts(filename: str):
    if not TTS_NAME_RE.match(filename):
        raise HTTPException(status_code=404, detail="不存在")
    path = Path(settings.tts_cache_dir) / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="不存在")
    return FileResponse(path, media_type="audio/mpeg")
```

- [ ] **Step 5: main.py 挂路由**

加 `from app.api.speaking import router as speaking_router`，并在 `app.include_router(essays_router)` 后加 `app.include_router(speaking_router)`。

- [ ] **Step 6: 测试通过 + 全套回归**

Run: `cd backend && uv run pytest -v`
Expected: 全部通过

注意：测试中 TestClient 会同步执行后台任务；TTS 在测试环境会真实尝试 edge-tts 网络调用——若测试因网络慢/失败，属预期降级（返回 None），但为免测试被网络拖住，允许在测试 fixture 中对 `app.api.speaking.tts_url_for` 打桩为 `lambda text: None`。若打桩，在报告里说明。

- [ ] **Step 7: Commit**

```bash
git add backend/ && git commit -m "feat: 口语练习 API（会话/轮次/汇总/TTS）"
```

---

### Task 6: 前端 API 扩展 + 口语入口页（SpeakingPage）

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/client.ts`
- Create: `frontend/src/pages/SpeakingPage.tsx`
- Modify: `frontend/src/App.tsx`（加 `/speaking` 与 `/speaking/session/:id` 路由）
- Modify: `frontend/src/components/NavBar.tsx`（加"口语练习"链接）

**Interfaces:**
- Consumes: Task 5 的 API 契约
- Produces（Task 7-8 消费）:
  - types：`SpeakingCardOut / SessionOut / TurnDetail / SessionSummary / SpeakingBands / SpeakingFeedback`；`EssayOut` 加 `module: string`
  - client：`listSpeakingCards(part)` / `createSpeakingSession(cardId)` / `submitSpeakingTurn(sessionId, audio: Blob)` / `getSpeakingTurn(practiceId)` / `finishSpeakingSession(id)`

- [ ] **Step 1: types.ts 追加**

```ts
export interface SpeakingCardOut {
  id: number
  part: number
  topic: string
  season: string
  payload: { questions?: string[]; cues?: string[] }
}

export interface SessionOut {
  id: number
  part: number
  topic: string
  status: 'active' | 'done'
  question: string
  tts_url: string | null
}

export interface SpeakingBands {
  fluency: number
  lexical: number
  grammar: number
  pronunciation: number
  overall: number
}

export interface SpeakingFeedback {
  bands: SpeakingBands
  annotations: Annotation[]
  rewrite: string
  is_mock: boolean
}

export interface TurnDetail {
  practice_id: number
  status: 'pending' | 'done' | 'needs_review'
  transcript: string | null
  feedback: SpeakingFeedback | null
  next_question: string | null
  next_tts_url: string | null
  session_done: boolean
}

export interface TurnSummaryItem {
  question: string
  transcript: string
  total_band: number | null
}

export interface SessionSummary {
  session_id: number
  avg_band: number | null
  turns: TurnSummaryItem[]
}
```

`EssayOut` 接口加一行：`module: string`

- [ ] **Step 2: client.ts 追加**

```ts
export function listSpeakingCards(part: number): Promise<SpeakingCardOut[]> {
  return request(`/speaking/cards?part=${part}`)
}

export function createSpeakingSession(cardId: number): Promise<SessionOut> {
  return request('/speaking/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ card_id: cardId }),
  })
}

export function submitSpeakingTurn(sessionId: number, audio: Blob): Promise<{ practice_id: number }> {
  const form = new FormData()
  form.append('session_id', String(sessionId))
  form.append('audio', audio, 'answer.wav')
  return request('/speaking/turns', { method: 'POST', body: form })
}

export function getSpeakingTurn(practiceId: number): Promise<TurnDetail> {
  return request(`/speaking/turns/${practiceId}`)
}

export function finishSpeakingSession(id: number): Promise<SessionSummary> {
  return request(`/speaking/sessions/${id}/finish`, { method: 'POST' })
}
```

（文件头部 import 类型列表相应加 `SpeakingCardOut, SessionOut, SessionSummary, TurnDetail`。）

- [ ] **Step 3: SpeakingPage**

`frontend/src/pages/SpeakingPage.tsx`:
```tsx
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createSpeakingSession, listSpeakingCards } from '../api/client'
import type { SpeakingCardOut } from '../api/types'

const PARTS = [
  { part: 1, name: 'Part 1 日常问答', desc: '4 个日常话题小问题，每题回答 20-30 秒' },
  { part: 2, name: 'Part 2 个人陈述', desc: 'Cue Card：准备 1 分钟，陈述 2 分钟' },
  { part: 3, name: 'Part 3 深度讨论', desc: 'AI 考官根据你的回答连续追问' },
]

export default function SpeakingPage() {
  const [part, setPart] = useState(1)
  const [cards, setCards] = useState<SpeakingCardOut[]>([])
  const [error, setError] = useState('')
  const [starting, setStarting] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    setCards([])
    listSpeakingCards(part).then(setCards).catch((e) => setError(String(e)))
  }, [part])

  const start = async (card: SpeakingCardOut) => {
    if (starting) return
    setStarting(true)
    setError('')
    try {
      const session = await createSpeakingSession(card.id)
      navigate(`/speaking/session/${session.id}`, { state: { session } })
    } catch (e) {
      setError(String(e))
      setStarting(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        {PARTS.map((p) => (
          <button
            key={p.part}
            onClick={() => setPart(p.part)}
            className={`rounded-lg px-4 py-2 text-sm font-medium ${
              part === p.part ? 'bg-indigo-600 text-white' : 'bg-white text-slate-600 border border-slate-200'
            }`}
          >
            {p.name}
          </button>
        ))}
      </div>
      <p className="text-sm text-slate-400">{PARTS[part - 1].desc}</p>
      {error && <div className="text-sm text-red-500">{error}</div>}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {cards.map((card) => (
          <button
            key={card.id}
            onClick={() => start(card)}
            disabled={starting}
            className="rounded-xl border border-slate-200 bg-white p-5 text-left hover:border-indigo-300 hover:shadow-sm disabled:opacity-50"
          >
            <div className="font-semibold text-slate-700">{card.topic}</div>
            <div className="mt-1 text-xs text-slate-400">
              {card.season} 季度题库 ·{' '}
              {card.part === 2 ? `${card.payload.cues?.length ?? 0} 个提示点` : `${card.payload.questions?.length ?? 0} 个问题`}
            </div>
          </button>
        ))}
      </div>
      {cards.length === 0 && !error && (
        <div className="py-10 text-center text-sm text-slate-400">加载话题卡中…</div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: 路由与导航**

`App.tsx`：加 `import SpeakingPage from './pages/SpeakingPage'`；路由表加 `<Route path="/speaking" element={<SpeakingPage />} />` 和 `<Route path="/speaking/session/:id" element={<div className="p-10 text-slate-400">练习室（下一任务实现）</div>} />`（Task 7 替换为 PracticeRoom；不要恢复 V1 已删除的 Placeholder 组件）。

`NavBar.tsx` links 数组加 `{ to: '/speaking', label: '口语练习' }`。

- [ ] **Step 5: 构建验证**

Run: `cd frontend && npm run build`（Node v22，unset 代理）
Expected: 通过

- [ ] **Step 6: Commit**

```bash
git add frontend/ && git commit -m "feat: 口语入口页 + 前端 API 扩展"
```

---

### Task 7: WAV 录音器 + 练习室（PracticeRoom）

**Files:**
- Create: `frontend/src/lib/recorder.ts`
- Create: `frontend/src/components/SpeakingFeedbackCard.tsx`
- Create: `frontend/src/pages/PracticeRoom.tsx`
- Modify: `frontend/src/App.tsx`（`/speaking/session/:id` 换真页面，删除临时占位）

**Interfaces:**
- Consumes: Task 6 的 client/types
- Produces: `WavRecorder` 类（`start(): Promise<void>`、`stop(): Promise<Blob>`，输出 16kHz 单声道 16bit WAV）；`SpeakingFeedbackCard`（props `{feedback: SpeakingFeedback}`，分项分行展示 + 批注展开 + 发音局限标注 + is_mock 演示数据徽标）

- [ ] **Step 1: 实现 recorder.ts**

`frontend/src/lib/recorder.ts`:
```ts
/** 浏览器录音 → 16kHz 单声道 16bit WAV（讯飞 ASR 要求 wav）。 */
export class WavRecorder {
  private ctx: AudioContext | null = null
  private stream: MediaStream | null = null
  private processor: ScriptProcessorNode | null = null
  private chunks: Float32Array[] = []

  async start(): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    this.ctx = new AudioContext()
    const source = this.ctx.createMediaStreamSource(this.stream)
    this.processor = this.ctx.createScriptProcessor(4096, 1, 1)
    this.chunks = []
    this.processor.onaudioprocess = (e) => {
      this.chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)))
    }
    source.connect(this.processor)
    this.processor.connect(this.ctx.destination)
  }

  async stop(): Promise<Blob> {
    this.processor?.disconnect()
    this.stream?.getTracks().forEach((t) => t.stop())
    const sampleRate = this.ctx?.sampleRate ?? 48000
    await this.ctx?.close()
    this.ctx = null
    const samples = mergeChunks(this.chunks)
    const pcm16 = downsampleTo16k(samples, sampleRate)
    return encodeWav(pcm16, 16000)
  }
}

function mergeChunks(chunks: Float32Array[]): Float32Array {
  const total = chunks.reduce((n, c) => n + c.length, 0)
  const out = new Float32Array(total)
  let offset = 0
  for (const c of chunks) {
    out.set(c, offset)
    offset += c.length
  }
  return out
}

function downsampleTo16k(samples: Float32Array, fromRate: number): Int16Array {
  const ratio = fromRate / 16000
  const outLen = Math.floor(samples.length / ratio)
  const out = new Int16Array(outLen)
  for (let i = 0; i < outLen; i++) {
    const s = Math.max(-1, Math.min(1, samples[Math.floor(i * ratio)]))
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff
  }
  return out
}

function encodeWav(pcm: Int16Array, sampleRate: number): Blob {
  const buffer = new ArrayBuffer(44 + pcm.length * 2)
  const view = new DataView(buffer)
  const writeStr = (offset: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(offset + i, s.charCodeAt(i))
  }
  writeStr(0, 'RIFF')
  view.setUint32(4, 36 + pcm.length * 2, true)
  writeStr(8, 'WAVE')
  writeStr(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true) // PCM
  view.setUint16(22, 1, true) // mono
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeStr(36, 'data')
  view.setUint32(40, pcm.length * 2, true)
  new Int16Array(buffer, 44).set(pcm)
  return new Blob([buffer], { type: 'audio/wav' })
}
```

- [ ] **Step 2: SpeakingFeedbackCard**

`frontend/src/components/SpeakingFeedbackCard.tsx`:
```tsx
import { useState } from 'react'
import type { SpeakingFeedback } from '../api/types'

const BAND_LABELS: [keyof SpeakingFeedback['bands'], string][] = [
  ['fluency', '流利度 FC'],
  ['lexical', '词汇 LR'],
  ['grammar', '语法 GRA'],
  ['pronunciation', '发音 P'],
]

export function SpeakingFeedbackCard({ feedback }: { feedback: SpeakingFeedback }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div className="mt-2 rounded-lg border border-indigo-100 bg-indigo-50/50 p-3 text-sm">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-lg font-bold text-indigo-600">
          {feedback.bands.overall.toFixed(1)}
        </span>
        {BAND_LABELS.map(([key, label]) => (
          <span key={key} className="text-xs text-slate-500">
            {label} <b>{feedback.bands[key].toFixed(1)}</b>
          </span>
        ))}
        {feedback.is_mock && (
          <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-700">演示数据</span>
        )}
      </div>
      <div className="mt-1 text-xs text-slate-400">发音分为间接评估，仅供参考</div>
      <button
        onClick={() => setExpanded(!expanded)}
        className="mt-2 text-xs text-indigo-600 hover:underline"
      >
        {expanded ? '收起批注 ▲' : `查看 ${feedback.annotations.length} 条批注与 7 分改写 ▼`}
      </button>
      {expanded && (
        <div className="mt-2 space-y-2">
          {feedback.annotations.map((a, i) => (
            <div key={i} className="rounded bg-white p-2">
              <span className="mr-1 rounded bg-red-100 px-1.5 py-0.5 text-xs text-red-600">
                {a.error_type ?? '批注'}
              </span>
              <span className="text-slate-500 line-through">{a.original}</span>
              <div className="mt-1 text-slate-700">{a.issue}</div>
              <div className="text-emerald-700">✎ {a.suggestion}</div>
            </div>
          ))}
          <div className="rounded border border-emerald-200 bg-emerald-50 p-2">
            <div className="text-xs font-semibold text-emerald-600">7 分改写版</div>
            <p className="mt-1 text-slate-700">{feedback.rewrite}</p>
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: PracticeRoom**

`frontend/src/pages/PracticeRoom.tsx`:
```tsx
import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { finishSpeakingSession, getSpeakingTurn, submitSpeakingTurn } from '../api/client'
import type { SessionOut, SessionSummary, SpeakingFeedback } from '../api/types'
import { SpeakingFeedbackCard } from '../components/SpeakingFeedbackCard'
import { WavRecorder } from '../lib/recorder'

interface Msg {
  role: 'examiner' | 'user' | 'system'
  text: string
  ttsUrl?: string | null
  audioUrl?: string
  feedback?: SpeakingFeedback
}

const PART2_RECORD_SEC = 120
const DEFAULT_RECORD_SEC = 180
const PART2_PREP_SEC = 60

export default function PracticeRoom() {
  const location = useLocation()
  const navigate = useNavigate()
  const session = (location.state as { session?: SessionOut } | null)?.session

  const [messages, setMessages] = useState<Msg[]>([])
  const [recording, setRecording] = useState(false)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  const [summary, setSummary] = useState<SessionSummary | null>(null)
  const [prepLeft, setPrepLeft] = useState<number | null>(null)
  const [error, setError] = useState('')
  const recorderRef = useRef<WavRecorder | null>(null)
  const recordTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!session) return
    setMessages([{ role: 'examiner', text: session.question, ttsUrl: session.tts_url }])
    if (session.part === 2) {
      setPrepLeft(PART2_PREP_SEC)
    }
  }, [session?.id])

  // Part 2 准备倒计时
  useEffect(() => {
    if (prepLeft === null || prepLeft <= 0) return
    const t = setTimeout(() => setPrepLeft(prepLeft - 1), 1000)
    return () => clearTimeout(t)
  }, [prepLeft])

  if (!session) {
    return (
      <div className="p-10 text-slate-400">
        会话信息缺失，请从
        <button className="text-indigo-600 hover:underline" onClick={() => navigate('/speaking')}>
          口语练习页
        </button>
        重新开始。
      </div>
    )
  }

  const startRecord = async () => {
    setError('')
    try {
      recorderRef.current = new WavRecorder()
      await recorderRef.current.start()
      setRecording(true)
      const maxSec = session.part === 2 ? PART2_RECORD_SEC : DEFAULT_RECORD_SEC
      recordTimerRef.current = setTimeout(() => stopRecord(), maxSec * 1000)
    } catch {
      setError('无法访问麦克风，请检查浏览器权限')
    }
  }

  const stopRecord = async () => {
    if (!recorderRef.current) return
    if (recordTimerRef.current) clearTimeout(recordTimerRef.current)
    setRecording(false)
    setBusy(true)
    try {
      const blob = await recorderRef.current.stop()
      recorderRef.current = null
      const audioUrl = URL.createObjectURL(blob)
      const { practice_id } = await submitSpeakingTurn(session.id, blob)
      // 轮询该轮结果
      let detail = await getSpeakingTurn(practice_id)
      while (detail.status === 'pending') {
        await new Promise((r) => setTimeout(r, 2000))
        detail = await getSpeakingTurn(practice_id)
      }
      if (detail.status === 'needs_review' || !detail.feedback) {
        setMessages((m) => [...m, { role: 'system', text: '本次转写/评分未完成，请重新回答该问题。' }])
        return
      }
      setMessages((m) => [
        ...m,
        {
          role: 'user',
          text: detail.transcript ?? '',
          audioUrl,
          feedback: detail.feedback ?? undefined,
        },
      ])
      if (detail.session_done) {
        setDone(true)
        setSummary(await finishSpeakingSession(session.id))
      } else if (detail.next_question) {
        setMessages((m) => [...m, {
          role: 'examiner', text: detail.next_question!, ttsUrl: detail.next_tts_url,
        }])
      }
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const finishEarly = async () => {
    setDone(true)
    setSummary(await finishSpeakingSession(session.id))
  }

  const canRecord = !busy && !done && (session.part !== 2 || prepLeft === 0)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <span className="rounded bg-indigo-100 px-2 py-0.5 text-xs text-indigo-600">
            Part {session.part}
          </span>
          <span className="ml-2 font-semibold">{session.topic}</span>
        </div>
        {!done && (
          <button onClick={finishEarly} className="text-sm text-slate-400 hover:text-slate-600">
            结束会话
          </button>
        )}
      </div>

      {prepLeft !== null && prepLeft > 0 && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-center text-amber-700">
          准备时间：{prepLeft} 秒（Part 2 请先构思，倒计时结束后开始录音）
        </div>
      )}

      <div className="space-y-3">
        {messages.map((msg, i) => (
          <div key={i} className={msg.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
            <div className={`max-w-[80%] rounded-2xl p-4 ${
              msg.role === 'examiner' ? 'bg-white border border-slate-200'
              : msg.role === 'user' ? 'bg-indigo-600 text-white'
              : 'bg-amber-50 border border-amber-200 text-amber-700 text-sm'
            }`}>
              {msg.role === 'examiner' && (
                <div className="mb-1 flex items-center gap-2">
                  <span className="text-xs text-slate-400">AI 考官</span>
                  {msg.ttsUrl && (
                    <audio controls src={msg.ttsUrl} className="h-7 max-w-[220px]" />
                  )}
                </div>
              )}
              <div className="whitespace-pre-wrap text-sm">{msg.text}</div>
              {msg.audioUrl && <audio controls src={msg.audioUrl} className="mt-2 h-8" />}
              {msg.feedback && <SpeakingFeedbackCard feedback={msg.feedback} />}
            </div>
          </div>
        ))}
        {busy && <div className="text-center text-sm text-indigo-400">AI 考官正在听写并评分…</div>}
      </div>

      {error && <div className="text-sm text-red-500">{error}</div>}

      {!done ? (
        <button
          onClick={recording ? stopRecord : startRecord}
          disabled={!recording && !canRecord}
          className={`w-full rounded-xl py-3 font-semibold text-white disabled:opacity-40 ${
            recording ? 'bg-red-500' : 'bg-indigo-600'
          }`}
        >
          {recording ? '■ 停止并提交' : busy ? '评分中…' : '● 开始录音回答'}
        </button>
      ) : (
        summary && (
          <div className="rounded-xl border border-slate-200 bg-white p-6 text-center">
            <div className="text-sm text-slate-400">本次会话均分</div>
            <div className="text-4xl font-bold text-indigo-600">
              {summary.avg_band !== null ? summary.avg_band.toFixed(1) : '—'}
            </div>
            <div className="mt-2 text-sm text-slate-500">
              完成 {summary.turns.length} 轮问答
            </div>
            <button
              onClick={() => navigate('/speaking')}
              className="mt-4 rounded-lg bg-indigo-600 px-6 py-2 text-white"
            >
              返回再练
            </button>
          </div>
        )
      )}
    </div>
  )
}
```

- [ ] **Step 4: 路由接入**

`App.tsx`：`/speaking/session/:id` 换成 `<PracticeRoom />`（import 之），删除 Task 6 留下的临时占位；若 `Placeholder` 组件此时已无任何引用则删除。

- [ ] **Step 5: 构建验证**

Run: `cd frontend && npm run build`（Node v22，unset 代理）
Expected: 通过（tsc 无类型错误）

- [ ] **Step 6: Commit**

```bash
git add frontend/ && git commit -m "feat: 口语练习室（WAV 录音 + 多轮对话 + 轮内反馈卡）"
```

---

### Task 8: 历史页/仪表盘支持口语

**Files:**
- Modify: `frontend/src/pages/HistoryPage.tsx`
- Modify: `frontend/src/pages/DashboardPage.tsx`

**Interfaces:**
- Consumes: `EssayOut.module`（Task 6 已加进 types；后端 Task 2 已加进 schema）

- [ ] **Step 1: HistoryPage 修改**

- 成绩曲线数据改为只统计写作：`essays.filter((e) => e.total_band !== null && e.module === 'writing')`
- 表格"题目"列前加模块标签：
```tsx
<span className={`mr-2 rounded px-1.5 py-0.5 text-xs ${
  e.module === 'speaking' ? 'bg-emerald-100 text-emerald-700' : 'bg-indigo-100 text-indigo-700'
}`}>{e.module === 'speaking' ? '口语' : '写作'}</span>
```
- 口语行（`module === 'speaking'`）的题目列渲染纯文本（不包 Link——口语结果在练习室里看，无 /result 页面）；写作行保持 Link。

- [ ] **Step 2: DashboardPage 修改**

- `latest` 保持写作口径：`essays.find((e) => e.total_band !== null && e.module === 'writing')`
- 在第一张卡后插入口语卡（外层 grid 由 `md:grid-cols-3` 改为 `md:grid-cols-2 lg:grid-cols-4`）：
```tsx
const latestSpeaking = essays.find((e) => e.total_band !== null && e.module === 'speaking')
```
卡片内容：标题"口语最新分"，分值 `latestSpeaking?.total_band?.toFixed(1) ?? '—'`，底部链接 `/speaking`「去练口语 →」。

- [ ] **Step 3: 构建验证**

Run: `cd frontend && npm run build`
Expected: 通过

- [ ] **Step 4: Commit**

```bash
git add frontend/ && git commit -m "feat: 历史与仪表盘支持口语模块"
```

---

### Task 9: V2 端到端验证 + 文档 + 推送

**Files:**
- Modify: `backend/.env.example`
- Modify: `README.md`

- [ ] **Step 1: 全量测试 + 构建**

```bash
cd backend && uv run pytest -v
cd ../frontend && npm run build
```
Expected: 全绿

- [ ] **Step 2: 口语 mock 链路 e2e（端口 8022）**

```bash
cd backend && env -u DEEPSEEK_API_KEY -u IFLYTEK_APP_ID -u IFLYTEK_API_SECRET \
  uv run uvicorn app.main:app --port 8022
```
另开终端（用 python 造 1 秒静音 wav 文件 /tmp/a.wav）：
```bash
curl "localhost:8022/api/speaking/cards?part=1"
curl -X POST localhost:8022/api/speaking/sessions -H 'Content-Type: application/json' -d '{"card_id": 1}'
curl -X POST localhost:8022/api/speaking/turns -F "session_id=1" -F "audio=@/tmp/a.wav"
sleep 1 && curl localhost:8022/api/speaking/turns/1
curl -X POST localhost:8022/api/speaking/sessions/1/finish
```
Expected: 转写为 mock 文本、评分 done、is_mock=true、追问推进、汇总 avg_band=5.5

- [ ] **Step 3: 真实评分验证（本机有 DEEPSEEK_API_KEY，允许一次）**

去掉 `-u DEEPSEEK_API_KEY` 重启后端（ASR 仍 mock），再提交一轮：确认 `is_mock=true`（因为转写是 mock——标注语义正确）且 bands 是 DeepSeek 对 mock 转写文本的真实评分。若 deepseek 偶发截断走重试属预期加固路径，看日志即可。

- [ ] **Step 4: .env.example 与 README**

`backend/.env.example` 全文：
```bash
DEEPSEEK_API_KEY=sk-xxxxxxxx
# 讯飞语音转写（不配则口语走演示转写）
IFLYTEK_APP_ID=
IFLYTEK_API_SECRET=
```

README「结构」前加一节：
```markdown
## 口语模块（V2）

- 入口：`/speaking`，Part 1/2/3 三个部分，当季（2026-09）题库
- 录音在浏览器端编码为 16kHz WAV 上传；讯飞 key 未配置时使用演示转写
- Part 3 由 AI 根据回答生成追问；提问语音由 edge-tts 生成（生成失败自动降级为文字）
- 发音分项为间接评估，仅供参考
```

- [ ] **Step 5: Commit + push**

```bash
git add -A && git commit -m "docs: README 与 env 示例更新，V2 完成" && git push
```

- [ ] **Step 6: 收尾核对（对照规格 §1 成功标准逐项确认）**

- 任一口语练习后有转写文本 + 四项雷达/分项 + 批注 + 改写 ✓
- Part 1/3 多轮连续问答 ✓；Part 3 LLM 追问 ✓
- 无讯飞 key 走 Mock 完整跑通 ✓
- 发音局限标注 ✓；5MB/wav 校验 ✓
