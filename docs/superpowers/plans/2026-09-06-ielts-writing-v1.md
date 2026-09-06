# 雅思 V1 写作 Task 2 AI 批改 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 V1 迭代——用户提交 Task 2 作文 → DeepSeek/Mock 批改 → 雷达图 + 逐句批注 + 改写对比 → 错误入库 + 能力点标黄，含历史曲线与简版仪表盘。

**Architecture:** FastAPI + SQLAlchemy 2.0 + SQLite 后端（9 张表全量建好），React + Vite + TS + Tailwind 前端。批改走后台任务，前端轮询结果；无 DeepSeek key 时自动降级 MockGrader 返回预置示例批改。

**Tech Stack:** Python 3.11+ / uv / FastAPI / SQLAlchemy 2.0 / Pydantic v2 / openai SDK / pytest；Node 18+ / Vite / React 18 / TypeScript / Tailwind v4 / Framer Motion / ECharts。

**上游规格:** `docs/superpowers/specs/2026-09-06-ielts-writing-v1-design.md`

## Global Constraints

- Python >= 3.11；依赖管理优先 uv，无 uv 退 `python -m venv + pip`
- LLM 调用：openai SDK 兼容模式直连 DeepSeek，`response_format={"type":"json_object"}`，temperature=0.2，失败重试 1 次
- API key 从 `.env` 读 `DEEPSEEK_API_KEY`，缺失时自动用 MockGrader（界面对 mock 结果标注"演示数据"）
- 数据库默认 `sqlite:///./yasi.db`，模型层与方言无关
- 单人模式：`user_id=1` 硬编码，无注册登录
- 作文词数上限 500，前后端都校验
- 所有后端测试在 `backend/` 下用 `uv run pytest` 执行；测试数据库用 tmp 路径 SQLite，绝不碰 `./yasi.db`
- 前端无单元测试要求（V1 手测），但必须 `npm run build` 通过（含 tsc 类型检查）
- git 提交信息用中文 Conventional Commits（如 `feat: 添加批改管线`）

---

### Task 1: 后端骨架 + 健康检查

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`（空文件）
- Create: `backend/app/config.py`
- Create: `backend/app/database.py`
- Create: `backend/app/main.py`
- Test: `backend/tests/test_health.py`

**Interfaces:**
- Produces: `settings`（`app.config.settings`，字段 `deepseek_api_key/deepseek_base_url/deepseek_model/database_url`）；`Base`、`make_session_factory(url)`（`app.database`）；FastAPI 实例 `app`（`app.main`），`app.state.session_factory` 为全局 session 工厂。后续所有任务都消费这三个接口。

- [ ] **Step 1: 创建 pyproject.toml**

```toml
[project]
name = "yasi-backend"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn>=0.30",
    "sqlalchemy>=2.0",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "openai>=1.40",
]

[dependency-groups]
dev = [
    "pytest>=8",
    "httpx>=0.27",
]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

- [ ] **Step 2: 初始化环境**

Run:
```bash
cd backend && uv sync
```
Expected: 依赖安装成功（无 uv 则 `python -m venv .venv && .venv/bin/pip install fastapi uvicorn sqlalchemy pydantic pydantic-settings openai pytest httpx`，后续命令中 `uv run` 替换为 `.venv/bin/` 直调）。

- [ ] **Step 3: 写 config.py 和 database.py**

`backend/app/config.py`:
```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    database_url: str = "sqlite:///./yasi.db"


settings = Settings()
```

`backend/app/database.py`:
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def make_session_factory(url: str) -> sessionmaker:
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
```

- [ ] **Step 4: 写 main.py（先只有 health）**

`backend/app/main.py`:
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, make_session_factory

app = FastAPI(title="yasi")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.session_factory = make_session_factory(settings.database_url)


@app.on_event("startup")
def init_db() -> None:
    from app import models  # noqa: F401  确保表已注册

    engine = app.state.session_factory.kw["bind"]
    Base.metadata.create_all(engine)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 5: 写失败测试**

`backend/tests/__init__.py`（空文件）和 `backend/tests/test_health.py`:
```python
from fastapi.testclient import TestClient

from app.main import app


def test_health():
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

- [ ] **Step 6: 运行测试确认通过**

Run: `cd backend && uv run pytest -v`
Expected: PASS（health 路由已随 Step 4 写好；若 Step 4 未完成则此处应 FAIL）

- [ ] **Step 7: 手动验证服务能起**

Run: `cd backend && uv run uvicorn app.main:app --port 8000`，另开终端 `curl localhost:8000/api/health`
Expected: `{"status":"ok"}`；验证后 Ctrl-C 停止

- [ ] **Step 8: Commit**

```bash
git add backend/ && git commit -m "feat: 后端骨架 + 健康检查"
```

---

### Task 2: 数据模型（9 张表）

**Files:**
- Create: `backend/app/models.py`
- Test: `backend/tests/test_models.py`

**Interfaces:**
- Consumes: `Base`、`make_session_factory`（Task 1）
- Produces: 九个模型类 `User, SkillNode, SkillMastery, Word, ReviewCard, ListeningMat, Practice, AIFeedback, ErrorItem, MockExam`（`app.models`）。字段名见下方代码——Task 3/5/6 的 schema 与管线严格按这些字段名取值，尤其 `Practice.status`（`pending/done/needs_review`）、`Practice.total_band`、`AIFeedback.bands/annotations/rewrite/is_mock`、`ErrorItem.error_type/context`。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_models.py`:
```python
from app.database import Base, make_session_factory
from app.models import AIFeedback, ErrorItem, Practice, SkillMastery, SkillNode, User


def make_db(tmp_path):
    factory = make_session_factory(f"sqlite:///{tmp_path}/test.db")
    engine = factory.kw["bind"]
    Base.metadata.create_all(engine)
    return factory


def test_practice_feedback_error_roundtrip(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    s.add(User(id=1, target_band=6.5))
    s.add(Practice(id=1, user_id=1, prompt_title="t", prompt_text="p", content="hello world",
                   word_count=2, status="done", total_band=6.5))
    s.add(AIFeedback(practice_id=1, bands={"overall": 6.5}, annotations=[], rewrite="rw",
                     model="mock", is_mock=True))
    s.add(ErrorItem(user_id=1, practice_id=1, error_type="时态", context="hello world"))
    s.commit()

    p = s.get(Practice, 1)
    assert p.feedback.bands["overall"] == 6.5
    assert p.feedback.is_mock is True
    errors = s.query(ErrorItem).filter_by(practice_id=1).all()
    assert errors[0].error_type == "时态"


def test_skill_tree(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    parent = SkillNode(module="writing", code="writing.task2", title="Task 2 议论文")
    s.add(parent)
    s.flush()
    child = SkillNode(module="writing", code="writing.task2.tr", title="审题与立场",
                      parent_id=parent.id)
    s.add(child)
    s.add(SkillMastery(user_id=1, node_id=parent.id, status="learned",
                       evidence={"source": "essay_graded"}))
    s.commit()

    assert s.get(SkillMastery, 1).status == "learned"
    assert child.parent_id == parent.id
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && uv run pytest tests/test_models.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.models'`

- [ ] **Step 3: 实现 models.py**

`backend/app/models.py`:
```python
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    target_band: Mapped[float] = mapped_column(Float, default=6.5)


class SkillNode(Base):
    __tablename__ = "skill_node"

    id: Mapped[int] = mapped_column(primary_key=True)
    module: Mapped[str] = mapped_column(String(20))  # writing/speaking/listening/vocab
    code: Mapped[str] = mapped_column(String(50), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("skill_node.id"), nullable=True)
    criteria: Mapped[dict] = mapped_column(JSON, default=dict)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class SkillMastery(Base):
    __tablename__ = "skill_mastery"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), default=1)
    node_id: Mapped[int] = mapped_column(ForeignKey("skill_node.id"))
    status: Mapped[str] = mapped_column(String(20), default="unseen")  # unseen/learned/verified
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Word(Base):
    __tablename__ = "word"

    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(String(100), unique=True)
    topic: Mapped[str] = mapped_column(String(50), default="")
    paraphrase_chain: Mapped[list] = mapped_column(JSON, default=list)
    example_sentence: Mapped[str] = mapped_column(Text, default="")


class ReviewCard(Base):
    __tablename__ = "review_card"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), default=1)
    word_id: Mapped[int] = mapped_column(ForeignKey("word.id"))
    ease_factor: Mapped[float] = mapped_column(Float, default=2.5)
    interval_days: Mapped[int] = mapped_column(Integer, default=1)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reps: Mapped[int] = mapped_column(Integer, default=0)


class ListeningMat(Base):
    __tablename__ = "listening_mat"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    audio_path: Mapped[str] = mapped_column(String(500), default="")
    transcript: Mapped[list] = mapped_column(JSON, default=list)


class Practice(Base):
    __tablename__ = "practice"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), default=1)
    module: Mapped[str] = mapped_column(String(20), default="writing")
    prompt_title: Mapped[str] = mapped_column(String(300))
    prompt_text: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    duration_sec: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/done/needs_review
    total_band: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    feedback: Mapped["AIFeedback | None"] = relationship(back_populates="practice")


class AIFeedback(Base):
    __tablename__ = "ai_feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    practice_id: Mapped[int] = mapped_column(ForeignKey("practice.id"), unique=True)
    bands: Mapped[dict] = mapped_column(JSON)  # {task_response, coherence, lexical, grammar, overall}
    annotations: Mapped[list] = mapped_column(JSON)
    rewrite: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(50), default="")
    is_mock: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    practice: Mapped[Practice] = relationship(back_populates="feedback")


class ErrorItem(Base):
    __tablename__ = "error_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), default=1)
    practice_id: Mapped[int] = mapped_column(ForeignKey("practice.id"))
    error_type: Mapped[str] = mapped_column(String(100))
    context: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MockExam(Base):
    __tablename__ = "mock_exam"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), default=1)
    scores: Mapped[dict] = mapped_column(JSON, default=dict)
    predicted_band: Mapped[float | None] = mapped_column(Float, nullable=True)
    report: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && uv run pytest tests/test_models.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/tests/test_models.py && git commit -m "feat: 全量 9 张数据表模型"
```

---

### Task 3: Pydantic schema + 评分 Prompt 模板

**Files:**
- Create: `backend/app/schemas.py`
- Create: `backend/app/prompt_templates.py`
- Test: `backend/tests/test_schemas.py`

**Interfaces:**
- Consumes: 无（纯数据结构）
- Produces: `BandScores / Annotation / GradingResult / EssayCreate / EssayOut / ErrorItemOut / FeedbackOut / EssayDetail / PromptOut`（`app.schemas`）；`SYSTEM_PROMPT`、`USER_PROMPT_TEMPLATE`（`app.prompt_templates`）。Task 4 的 mock 数据、Task 5 的管线校验、Task 6 的 API 全部用这些类。**注意** `GradingResult.model_validate_json(...)` 是 Task 5 解析 LLM 输出的入口。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_schemas.py`:
```python
import pytest
from pydantic import ValidationError

from app.schemas import EssayCreate, GradingResult


GOOD_JSON = """{
  "bands": {"task_response": 6.0, "coherence": 6.5, "lexical": 5.5, "grammar": 6.0, "overall": 6.0},
  "annotations": [
    {"sentence_index": 2, "original": "He go to school.", "issue": "主谓一致错误",
     "suggestion": "He goes to school.", "error_type": "主谓一致"}
  ],
  "rewrite": "Some rewritten essay."
}"""


def test_grading_result_parses_valid_json():
    result = GradingResult.model_validate_json(GOOD_JSON)
    assert result.bands.overall == 6.0
    assert result.annotations[0].error_type == "主谓一致"


def test_grading_result_rejects_out_of_range_band():
    bad = GOOD_JSON.replace('"overall": 6.0', '"overall": 9.5')
    with pytest.raises(ValidationError):
        GradingResult.model_validate_json(bad)


def test_essay_create_rejects_empty_and_too_long():
    with pytest.raises(ValidationError):
        EssayCreate(prompt_title="t", prompt_text="p", content="   ")
    with pytest.raises(ValidationError):
        EssayCreate(prompt_title="t", prompt_text="p", content="word " * 501)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && uv run pytest tests/test_schemas.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.schemas'`

- [ ] **Step 3: 实现 schemas.py**

`backend/app/schemas.py`:
```python
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BandScores(BaseModel):
    task_response: float = Field(ge=0, le=9)
    coherence: float = Field(ge=0, le=9)
    lexical: float = Field(ge=0, le=9)
    grammar: float = Field(ge=0, le=9)
    overall: float = Field(ge=0, le=9)


class Annotation(BaseModel):
    sentence_index: int = Field(ge=0)
    original: str
    issue: str
    suggestion: str
    error_type: str | None = None  # 主谓一致/时态/单复数/冠词/拼写/连接词/词汇搭配/句式/跑题/其他


class GradingResult(BaseModel):
    bands: BandScores
    annotations: list[Annotation]
    rewrite: str


class EssayCreate(BaseModel):
    prompt_title: str = Field(min_length=1, max_length=300)
    prompt_text: str = Field(min_length=1)
    content: str
    duration_sec: int = Field(default=0, ge=0)

    @field_validator("content")
    @classmethod
    def check_content(cls, v: str) -> str:
        words = v.split()
        if not words:
            raise ValueError("作文内容不能为空")
        if len(words) > 500:
            raise ValueError("词数超过 500 上限")
        return v


class PromptOut(BaseModel):
    title: str
    text: str


class EssayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    total_band: float | None
    prompt_title: str
    word_count: int
    created_at: datetime


class ErrorItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    error_type: str
    context: str
    created_at: datetime


class FeedbackOut(BaseModel):
    bands: dict
    annotations: list[dict]
    rewrite: str
    is_mock: bool


class EssayDetail(EssayOut):
    prompt_text: str
    content: str
    feedback: FeedbackOut | None
    errors: list[ErrorItemOut]
```

- [ ] **Step 4: 实现 prompt_templates.py**

`backend/app/prompt_templates.py`:
```python
SYSTEM_PROMPT = """你是一名资深雅思写作考官，严格按照雅思官方 Task 2 四项评分标准批改作文：
1. Task Response（任务回应）：立场是否清晰、是否回应题目所有部分、论证是否充分
2. Coherence & Cohesion（连贯与衔接）：结构分段、连接词多样性、指代衔接
3. Lexical Resource（词汇资源）：词汇广度、搭配准确性、同义替换能力、拼写
4. Grammatical Range & Accuracy（语法多样性与准确性）：句式多样性、语法错误密度

评分规则：
- 四项子分与 overall 总分均为 0-9，允许 0.5 步进
- overall 为四项均分按官方规则取整（均分 .25 进 .5，.75 进下一整分）
- annotations 只批注有问题的句子：sentence_index 为该句在原文中的序号（从 0 开始，按句号/问号/叹号切分），
  original 抄录原句，issue 用中文说明问题，suggestion 给出修改后的句子，
  error_type 从以下枚举中选一个：主谓一致、时态、单复数、冠词、拼写、连接词、词汇搭配、句式、跑题、其他
- rewrite 给出该题目 7.5 分水平的完整改写版（250-280 词）

只输出一个 JSON 对象，不要输出任何其他文字。JSON schema：
{
  "bands": {"task_response": 6.0, "coherence": 6.0, "lexical": 6.0, "grammar": 6.0, "overall": 6.0},
  "annotations": [{"sentence_index": 0, "original": "...", "issue": "...", "suggestion": "...", "error_type": "时态"}],
  "rewrite": "..."
}"""

USER_PROMPT_TEMPLATE = """【题目】
{prompt_text}

【考生作文】
{content}"""
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd backend && uv run pytest tests/test_schemas.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas.py backend/app/prompt_templates.py backend/tests/test_schemas.py && git commit -m "feat: 批改 schema 与评分 prompt 模板"
```

---

### Task 4: 示例数据 + Mock 批改器

**Files:**
- Create: `backend/app/data/__init__.py`（空文件）
- Create: `backend/app/data/sample.py`
- Create: `backend/app/services/__init__.py`（空文件）
- Create: `backend/app/services/mock_grader.py`
- Test: `backend/tests/test_mock_grader.py`

**Interfaces:**
- Consumes: `GradingResult`（Task 3）
- Produces: `SAMPLE_ESSAY: str`、`SAMPLE_PROMPT_TITLE: str`、`SAMPLE_PROMPT_TEXT: str`、`SAMPLE_GRADING: GradingResult`（`app.data.sample`）；`MockGrader`，方法签名 `grade(self, prompt_text: str, content: str) -> GradingResult`（`app.services.mock_grader`）。Task 5 的 `build_grader()` 与 Task 6 的 `/api/sample` 消费这些。`MockGrader.grade` 与 Task 5 的 `LLMGrader.grade` 签名必须完全一致。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_mock_grader.py`:
```python
from app.data.sample import SAMPLE_ESSAY, SAMPLE_GRADING
from app.services.mock_grader import MockGrader


def test_mock_grader_returns_valid_result():
    result = MockGrader().grade(prompt_text="any", content="any essay text")
    assert result.bands.overall == 6.0
    assert len(result.annotations) >= 3
    assert len(result.rewrite.split()) >= 200
    types = {a.error_type for a in result.annotations}
    assert "时态" in types or "主谓一致" in types


def test_sample_essay_is_band6_length():
    words = len(SAMPLE_ESSAY.split())
    assert 200 <= words <= 320
    assert SAMPLE_GRADING.bands.overall == 6.0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && uv run pytest tests/test_mock_grader.py -v`
Expected: FAIL，`ModuleNotFoundError`

- [ ] **Step 3: 实现 sample.py**

`backend/app/data/sample.py`（示例作文刻意含典型 6 分错误，与下方批注一一对应）:
```python
from app.schemas import Annotation, BandScores, GradingResult

SAMPLE_PROMPT_TITLE = "科技话题：远程办公"
SAMPLE_PROMPT_TEXT = (
    "Some people believe that working from home benefits employees, "
    "while others think it brings more problems. "
    "Discuss both views and give your own opinion."
)

SAMPLE_ESSAY = """In recent years, more and more people choose to work from home. Some people think it is good for employees, but others believe it cause many problems. In my opinion, working from home has more advantages than disadvantages.

On the one hand, working from home can save a lot of time. People don't need to spend two hours on the bus or subway every day, so they can use this time to work or rest. Also, it is more comfortable. Employees can wear what they like and arrange their schedule freely. For example, a mother can take care of her children while she is working.

On the other hand, there are some problems. Firstly, people may feel lonely because they don't communicate with colleagues face to face. Secondly, it is hard to separate work and life. Many people find themself working at midnight, which is bad for their health. In addition, some managers think employees will be lazy without supervision.

In conclusion, although working from home has some disadvantages such as loneliness and blurred boundaries, I believe the benefits are greater. Companies should provide training to help employees adapt to this new way of working."""

SAMPLE_GRADING = GradingResult(
    bands=BandScores(task_response=6.5, coherence=6.5, lexical=5.5, grammar=5.5, overall=6.0),
    annotations=[
        Annotation(
            sentence_index=1,
            original="Some people think it is good for employees, but others believe it cause many problems.",
            issue="主谓一致错误：主语 it 为第三人称单数，动词应为 causes。",
            suggestion="Some people think it is good for employees, but others believe it causes many problems.",
            error_type="主谓一致",
        ),
        Annotation(
            sentence_index=4,
            original="People don't need to spend two hours on the bus or subway every day, so they can use this time to work or rest.",
            issue="词汇搭配：'on the bus or subway' 更地道的表达是 'commuting'；'this time' 指代略含糊。",
            suggestion="People no longer need to spend two hours commuting every day, so they can devote that time to work or rest.",
            error_type="词汇搭配",
        ),
        Annotation(
            sentence_index=10,
            original="Many people find themself working at midnight, which is bad for their health.",
            issue="单复数错误：themself 不是标准用法，主语为 many people，应为 themselves。",
            suggestion="Many people find themselves working at midnight, which is detrimental to their health.",
            error_type="单复数",
        ),
        Annotation(
            sentence_index=11,
            original="In addition, some managers think employees will be lazy without supervision.",
            issue="连接词单一：全文论证过渡仅依赖 Firstly/Secondly/In addition，缺乏更高阶的衔接手段。",
            suggestion="A further concern raised by some managers is that productivity may decline without direct supervision.",
            error_type="连接词",
        ),
    ],
    rewrite="""In recent years, an increasing number of employees have opted to work remotely. While some argue that this trend benefits workers, others contend that it gives rise to considerable difficulties. In my view, the advantages of working from home outweigh its drawbacks.

On the one hand, remote work eliminates the daily commute, allowing employees to reclaim hours that would otherwise be spent in transit. This time can be redirected towards productive work or much-needed rest. Moreover, the flexibility of home-based work enables individuals to structure their schedules around personal responsibilities. A parent, for instance, can attend to childcare while remaining professionally active.

On the other hand, working from home is not without its problems. The absence of face-to-face interaction may leave employees feeling isolated, which can erode team cohesion over time. Furthermore, the boundary between professional and private life tends to blur, with many people finding themselves working late into the night at the expense of their health. Some managers also worry that productivity may decline without direct supervision.

In conclusion, although remote working poses challenges such as social isolation and blurred work-life boundaries, I believe its benefits are more significant. Companies should invest in training and clear policies to help employees adapt to this new mode of work.""",
)
```

- [ ] **Step 4: 实现 mock_grader.py**

`backend/app/services/mock_grader.py`:
```python
from app.data.sample import SAMPLE_GRADING
from app.schemas import GradingResult


class MockGrader:
    """无 DEEPSEEK_API_KEY 时的降级批改器：返回预置示例批改结果。"""

    model = "mock"

    def grade(self, prompt_text: str, content: str) -> GradingResult:
        return SAMPLE_GRADING
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd backend && uv run pytest tests/test_mock_grader.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/data/ backend/app/services/ backend/tests/test_mock_grader.py && git commit -m "feat: 示例作文与 mock 批改器"
```

---

### Task 5: 批改管线（DeepSeek 调用 + 错误提取 + 能力点标黄）

**Files:**
- Create: `backend/app/services/grader.py`
- Test: `backend/tests/test_grader.py`

**Interfaces:**
- Consumes: `Practice/AIFeedback/ErrorItem/SkillNode/SkillMastery`（Task 2）；`GradingResult`（Task 3）；`SYSTEM_PROMPT/USER_PROMPT_TEMPLATE`（Task 3）；`MockGrader`（Task 4）；`settings`（Task 1）
- Produces:
  - `class GradingFailed(Exception)`（`app.services.grader`）
  - `class LLMGrader`，`__init__(self, api_key: str, base_url: str, model: str)`，方法 `grade(self, prompt_text: str, content: str) -> GradingResult`（与 `MockGrader.grade` 签名一致），属性 `model: str`、`is_mock = False`
  - `def build_grader()`：有 key 返回 `LLMGrader`，无 key 返回 `MockGrader`
  - `def run_grading(practice_id: int, session_factory) -> None`：完整管线（Task 6 的 BackgroundTasks 直接注册它）
  - `def mark_writing_learned(session, user_id: int) -> int`（返回新标黄的节点数）

- [ ] **Step 1: 写失败测试**

`backend/tests/test_grader.py`:
```python
import pytest
from sqlalchemy import select

from app.data.sample import SAMPLE_GRADING
from app.database import Base, make_session_factory
from app.models import AIFeedback, ErrorItem, Practice, SkillMastery, SkillNode, User
from app.services.grader import GradingFailed, LLMGrader, run_grading


def make_db(tmp_path):
    factory = make_session_factory(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(factory.kw["bind"])
    return factory


def seed(factory):
    s = factory()
    s.add(User(id=1))
    s.add(SkillNode(id=1, module="writing", code="writing.task2", title="Task 2"))
    s.add(SkillNode(id=2, module="writing", code="writing.task2.tr", title="审题与立场", parent_id=1))
    s.add(SkillNode(id=3, module="listening", code="listening.s3", title="Section 3"))
    s.add(Practice(id=1, user_id=1, prompt_title="t", prompt_text="p",
                   content="some essay text", word_count=3))
    s.add(Practice(id=2, user_id=1, prompt_title="t2", prompt_text="p2",
                   content="another essay text", word_count=3))
    s.commit()
    s.close()


class FakeGrader:
    model = "fake"
    is_mock = False

    def grade(self, prompt_text, content):
        return SAMPLE_GRADING


class BrokenGrader:
    model = "broken"
    is_mock = False

    def grade(self, prompt_text, content):
        raise GradingFailed("bad json twice")


def test_run_grading_success(tmp_path):
    factory = make_db(tmp_path)
    seed(factory)
    run_grading(1, factory, grader=FakeGrader())

    s = factory()
    p = s.get(Practice, 1)
    assert p.status == "done"
    assert p.total_band == 6.0
    fb = s.scalars(select(AIFeedback).where(AIFeedback.practice_id == 1)).one()
    assert fb.bands["grammar"] == 5.5
    assert fb.is_mock is False
    errors = s.scalars(select(ErrorItem).where(ErrorItem.practice_id == 1)).all()
    assert {e.error_type for e in errors} == {"主谓一致", "词汇搭配", "单复数", "连接词"}
    # 能力点：仅 writing 模块标黄
    mastered = s.scalars(select(SkillMastery)).all()
    assert {m.node_id for m in mastered} == {1, 2}
    assert all(m.status == "learned" for m in mastered)
    s.close()

    # 幂等性：批改另一篇作文（practice 2），标黄不重复
    # 注：AIFeedback.practice_id 有唯一约束，同一 practice 不能重复批改
    run_grading(2, factory, grader=FakeGrader())
    s = factory()
    assert len(s.scalars(select(SkillMastery)).all()) == 2
    s.close()


def test_run_grading_marks_needs_review_on_failure(tmp_path):
    factory = make_db(tmp_path)
    seed(factory)
    run_grading(1, factory, grader=BrokenGrader())

    s = factory()
    assert s.get(Practice, 1).status == "needs_review"
    assert s.scalars(select(AIFeedback)).all() == []
    s.close()


def test_llm_grader_retries_then_raises():
    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise RuntimeError("boom")

    grader = LLMGrader.__new__(LLMGrader)
    grader.client = FakeClient()
    grader.model = "test"
    with pytest.raises(GradingFailed):
        grader.grade("p", "c")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && uv run pytest tests/test_grader.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.services.grader'`

- [ ] **Step 3: 实现 grader.py**

`backend/app/services/grader.py`:
```python
import logging

from openai import OpenAI
from sqlalchemy import select

from app.config import settings
from app.models import AIFeedback, ErrorItem, Practice, SkillMastery, SkillNode
from app.prompt_templates import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from app.schemas import GradingResult
from app.services.mock_grader import MockGrader

logger = logging.getLogger(__name__)


class GradingFailed(Exception):
    pass


class LLMGrader:
    is_mock = False

    def __init__(self, api_key: str, base_url: str, model: str):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def grade(self, prompt_text: str, content: str) -> GradingResult:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": USER_PROMPT_TEMPLATE.format(
                            prompt_text=prompt_text, content=content)},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                )
                return GradingResult.model_validate_json(resp.choices[0].message.content)
            except Exception as exc:  # 网络错误与 JSON 校验失败统一重试
                last_error = exc
                logger.warning("grading attempt %d failed: %s", attempt + 1, exc)
        raise GradingFailed(str(last_error))


def build_grader():
    if settings.deepseek_api_key:
        return LLMGrader(settings.deepseek_api_key, settings.deepseek_base_url, settings.deepseek_model)
    return MockGrader()


def mark_writing_learned(session, user_id: int) -> int:
    """把 writing 模块下所有能力点标为 learned（已学未验证），幂等。返回新标黄数量。"""
    node_ids = session.scalars(select(SkillNode.id).where(SkillNode.module == "writing")).all()
    existing = set(session.scalars(
        select(SkillMastery.node_id).where(SkillMastery.user_id == user_id)).all())
    added = 0
    for node_id in node_ids:
        if node_id not in existing:
            session.add(SkillMastery(user_id=user_id, node_id=node_id, status="learned",
                                     evidence={"source": "essay_graded"}))
            added += 1
    return added


def run_grading(practice_id: int, session_factory, grader=None) -> None:
    session = session_factory()
    try:
        practice = session.get(Practice, practice_id)
        if practice is None:
            return
        if grader is None:
            grader = build_grader()
        try:
            result = grader.grade(practice.prompt_text, practice.content)
        except GradingFailed as exc:
            practice.status = "needs_review"
            session.commit()
            logger.error("grading failed for practice %s: %s", practice_id, exc)
            return

        session.add(AIFeedback(
            practice_id=practice.id,
            bands=result.bands.model_dump(),
            annotations=[a.model_dump() for a in result.annotations],
            rewrite=result.rewrite,
            model=getattr(grader, "model", "unknown"),
            is_mock=getattr(grader, "is_mock", False),
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
        mark_writing_learned(session, practice.user_id)
        session.commit()
    finally:
        session.close()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && uv run pytest tests/test_grader.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/grader.py backend/tests/test_grader.py && git commit -m "feat: DeepSeek 批改管线 + 错误提取 + 能力点标黄"
```

---

### Task 6: API 路由 + 启动种子数据

**Files:**
- Create: `backend/app/api/__init__.py`（空文件）
- Create: `backend/app/api/essays.py`
- Create: `backend/app/seed.py`
- Modify: `backend/app/main.py`（挂路由 + 启动时 seed）
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: Task 1-5 全部
- Produces（前端 Task 7 的 api client 严格按此对接）:
  - `GET /api/health` → `{"status": "ok"}`
  - `GET /api/prompts` → `list[PromptOut]`（内置 4 道 Task 2 题，含示例题）
  - `GET /api/sample` → `{"title": str, "prompt_text": str, "content": str}`
  - `POST /api/essays`，body=`EssayCreate`，返回 202 + `EssayOut`，后台启动批改
  - `GET /api/essays` → `list[EssayOut]`（created_at 倒序）
  - `GET /api/essays/{id}` → `EssayDetail`（404 若不存在；`feedback` 在完成前为 null）
  - `GET /api/errors` → `list[ErrorItemOut]`（created_at 倒序）

- [ ] **Step 1: 写失败测试**

`backend/tests/test_api.py`:
```python
import time

import pytest
from fastapi.testclient import TestClient

from app.database import Base, make_session_factory
from app.main import app
from app.models import SkillMastery, SkillNode, User
from app.seed import seed_db


@pytest.fixture()
def client(tmp_path, monkeypatch):
    factory = make_session_factory(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(factory.kw["bind"])
    s = factory()
    s.add(User(id=1))
    s.commit()
    seed_db(s)
    s.close()
    # 防止测试机环境变量里恰好有 DEEPSEEK_API_KEY 导致走真实调用
    monkeypatch.setattr("app.config.settings.deepseek_api_key", "")
    monkeypatch.setattr(app.state, "session_factory", factory)
    return TestClient(app)


def test_prompts_and_sample(client):
    prompts = client.get("/api/prompts").json()
    assert len(prompts) == 4
    sample = client.get("/api/sample").json()
    assert len(sample["content"].split()) >= 200


def test_submit_and_poll_result(client):
    resp = client.post("/api/essays", json={
        "prompt_title": "t", "prompt_text": "p",
        "content": "This is a test essay with enough words to pass validation.",
        "duration_sec": 120,
    })
    assert resp.status_code == 202
    pid = resp.json()["id"]
    assert resp.json()["word_count"] == 11

    # TestClient 会同步执行 BackgroundTasks，无需轮询等待
    detail = client.get(f"/api/essays/{pid}").json()
    assert detail["status"] == "done"
    assert detail["total_band"] == 6.0
    assert detail["feedback"]["is_mock"] is True  # 测试环境无 DEEPSEEK_API_KEY
    assert len(detail["feedback"]["annotations"]) >= 3
    assert {e["error_type"] for e in detail["errors"]} == {"主谓一致", "词汇搭配", "单复数", "连接词"}

    errors = client.get("/api/errors").json()
    assert len(errors) == 4

    essays = client.get("/api/essays").json()
    assert essays[0]["id"] == pid


def test_mastery_seeded_and_marked(client):
    client.post("/api/essays", json={
        "prompt_title": "t", "prompt_text": "p", "content": "valid content here"})
    factory = app.state.session_factory
    s = factory()
    nodes = s.query(SkillNode).filter_by(module="writing").count()
    assert nodes >= 15  # 写作分支种子
    masteries = s.query(SkillMastery).filter_by(status="learned").count()
    assert masteries == nodes
    s.close()


def test_validation_and_404(client):
    resp = client.post("/api/essays", json={"prompt_title": "t", "prompt_text": "p", "content": " "})
    assert resp.status_code == 422
    assert client.get("/api/essays/999").status_code == 404
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && uv run pytest tests/test_api.py -v`
Expected: FAIL，路由 404 / ModuleNotFoundError

- [ ] **Step 3: 实现 seed.py（能力树种子 + 题库）**

`backend/app/seed.py`:
```python
from sqlalchemy import select

from app.models import SkillNode

WRITING_NODES: list[tuple[str, str, str | None, int]] = [
    # (code, title, parent_code, sort_order)
    ("writing.task2", "Task 2 议论文", None, 0),
    ("writing.task2.tr", "审题与立场（TR）", "writing.task2", 1),
    ("writing.task2.tr.identify", "识别题型（观点/讨论/利弊/报告）", "writing.task2.tr", 0),
    ("writing.task2.tr.position", "立场句一句话写清", "writing.task2.tr", 1),
    ("writing.task2.tr.cover", "回应题目所有部分", "writing.task2.tr", 2),
    ("writing.task2.cc", "论证结构（CC）", "writing.task2", 2),
    ("writing.task2.cc.frame", "五段式框架", "writing.task2.cc", 0),
    ("writing.task2.cc.paragraphing", "分段清晰、一段一义", "writing.task2.cc", 1),
    ("writing.task2.cc.linkers", "连接词多样性（≥8 类）", "writing.task2.cc", 2),
    ("writing.task2.cc.reference", "指代衔接", "writing.task2.cc", 3),
    ("writing.task2.lr", "词汇（LR）", "writing.task2", 3),
    ("writing.task2.lr.paraphrase", "同义替换避免重复", "writing.task2.lr", 0),
    ("writing.task2.lr.collocation", "搭配准确", "writing.task2.lr", 1),
    ("writing.task2.lr.academic", "学术词汇占比", "writing.task2.lr", 2),
    ("writing.task2.lr.spelling", "拼写正确", "writing.task2.lr", 3),
    ("writing.task2.gra", "语法（GRA）", "writing.task2", 4),
    ("writing.task2.gra.complex", "复杂句式多样", "writing.task2.gra", 0),
    ("writing.task2.gra.agreement", "主谓一致", "writing.task2.gra", 1),
    ("writing.task2.gra.tense", "时态正确", "writing.task2.gra", 2),
    ("writing.task2.gra.article", "冠词与单复数", "writing.task2.gra", 3),
]

TASK2_PROMPTS: list[dict] = [
    {"title": "科技话题：远程办公", "text": "Some people believe that working from home benefits employees, while others think it brings more problems. Discuss both views and give your own opinion."},
    {"title": "教育话题：大学应重理论还是实践", "text": "Some people think universities should focus on academic knowledge, while others believe practical skills are more important. Discuss both views and give your own opinion."},
    {"title": "环境话题：个人能否改变环境", "text": "Some people believe individuals can make a difference to the environment, while others think only governments and large companies can. Discuss both views and give your own opinion."},
    {"title": "媒体话题：广告的利弊", "text": "Advertising encourages people to buy things they do not need. To what extent do you agree or disagree?"},
]


def seed_db(session) -> None:
    """幂等写入能力树种子数据。"""
    existing = session.scalars(select(SkillNode.code)).all()
    if existing:
        return
    code_to_node: dict[str, SkillNode] = {}
    for code, title, parent_code, sort_order in WRITING_NODES:
        node = SkillNode(
            module="writing", code=code, title=title,
            parent_id=code_to_node[parent_code].id if parent_code else None,
            sort_order=sort_order,
        )
        session.add(node)
        session.flush()
        code_to_node[code] = node
    session.commit()
```

- [ ] **Step 4: 实现 api/essays.py**

`backend/app/api/essays.py`:
```python
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import select

from app.data.sample import SAMPLE_ESSAY, SAMPLE_PROMPT_TEXT, SAMPLE_PROMPT_TITLE
from app.models import ErrorItem, Practice
from app.schemas import ErrorItemOut, EssayCreate, EssayDetail, EssayOut, FeedbackOut, PromptOut
from app.seed import TASK2_PROMPTS
from app.services.grader import run_grading

router = APIRouter(prefix="/api")


def get_session(request: Request):
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


@router.get("/prompts", response_model=list[PromptOut])
def list_prompts():
    return TASK2_PROMPTS


@router.get("/sample")
def get_sample() -> dict:
    return {"title": SAMPLE_PROMPT_TITLE, "prompt_text": SAMPLE_PROMPT_TEXT, "content": SAMPLE_ESSAY}


@router.post("/essays", response_model=EssayOut, status_code=202)
def submit_essay(payload: EssayCreate, background: BackgroundTasks, request: Request,
                 session=Depends(get_session)):
    practice = Practice(
        user_id=1,
        prompt_title=payload.prompt_title,
        prompt_text=payload.prompt_text,
        content=payload.content,
        word_count=len(payload.content.split()),
        duration_sec=payload.duration_sec,
    )
    session.add(practice)
    session.commit()
    session.refresh(practice)
    background.add_task(run_grading, practice.id, request.app.state.session_factory)
    return practice


@router.get("/essays", response_model=list[EssayOut])
def list_essays(session=Depends(get_session)):
    return session.scalars(select(Practice).order_by(Practice.created_at.desc())).all()


@router.get("/essays/{practice_id}", response_model=EssayDetail)
def get_essay(practice_id: int, session=Depends(get_session)):
    practice = session.get(Practice, practice_id)
    if practice is None:
        raise HTTPException(status_code=404, detail="练习不存在")
    feedback = FeedbackOut(
        bands=practice.feedback.bands,
        annotations=practice.feedback.annotations,
        rewrite=practice.feedback.rewrite,
        is_mock=practice.feedback.is_mock,
    ) if practice.feedback else None
    errors = session.scalars(
        select(ErrorItem).where(ErrorItem.practice_id == practice_id)
        .order_by(ErrorItem.created_at)).all()
    return EssayDetail(
        **EssayOut.model_validate(practice).model_dump(),
        prompt_text=practice.prompt_text,
        content=practice.content,
        feedback=feedback,
        errors=[ErrorItemOut.model_validate(e) for e in errors],
    )


@router.get("/errors", response_model=list[ErrorItemOut])
def list_errors(session=Depends(get_session)):
    return session.scalars(select(ErrorItem).order_by(ErrorItem.created_at.desc())).all()
```

- [ ] **Step 5: 修改 main.py 挂路由 + 启动 seed**

`backend/app/main.py` 全文替换为：
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.essays import router as essays_router
from app.config import settings
from app.database import Base, make_session_factory
from app.models import User

app = FastAPI(title="yasi")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.session_factory = make_session_factory(settings.database_url)
app.include_router(essays_router)


@app.on_event("startup")
def init_db() -> None:
    from app import models  # noqa: F401  确保表已注册
    from app.seed import seed_db

    engine = app.state.session_factory.kw["bind"]
    Base.metadata.create_all(engine)
    session = app.state.session_factory()
    try:
        if session.get(User, 1) is None:
            session.add(User(id=1, target_band=6.5))
            session.commit()
        seed_db(session)
    finally:
        session.close()
```

- [ ] **Step 6: 运行全部后端测试确认通过**

Run: `cd backend && uv run pytest -v`
Expected: 全部通过（health + models + schemas + mock_grader + grader + api 共约 12 个用例）

- [ ] **Step 7: 手动 curl 冒烟**

Run: `cd backend && uv run uvicorn app.main:app --port 8000`，另开终端依次：
```bash
curl localhost:8000/api/prompts
curl -X POST localhost:8000/api/essays -H 'Content-Type: application/json' \
  -d '{"prompt_title":"t","prompt_text":"p","content":"Some essay with a few words here."}'
sleep 1 && curl localhost:8000/api/essays/1
```
Expected: 最终返回 `status: "done"`、`feedback.is_mock: true`

- [ ] **Step 8: Commit**

```bash
git add backend/ && git commit -m "feat: 写作批改 API + 能力树种子数据"
```

---

### Task 7: 前端骨架 + API client + 布局导航

**Files:**
- Create: `frontend/`（Vite react-ts 脚手架）
- Modify: `frontend/vite.config.ts`（Tailwind 插件 + /api 代理）
- Create: `frontend/src/index.css`
- Create: `frontend/src/api/types.ts`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/components/NavBar.tsx`
- Modify: `frontend/src/App.tsx`、`frontend/src/main.tsx`

**Interfaces:**
- Produces（Task 8-10 消费）:
  - `api/types.ts`：`PromptOut / EssayCreate / EssayOut / BandScores / Annotation / FeedbackOut / ErrorItemOut / EssayDetail`，字段与后端 schema 一一对应
  - `api/client.ts`：`listPrompts(): Promise<PromptOut[]>`、`getSample(): Promise<{title: string; prompt_text: string; content: string}>`、`submitEssay(body: EssayCreate): Promise<EssayOut>`、`listEssays(): Promise<EssayOut[]>`、`getEssay(id: number): Promise<EssayDetail>`、`listErrors(): Promise<ErrorItemOut[]>`
  - 路由表：`/` → DashboardPage，`/write` → WritingPage，`/result/:id` → ResultPage，`/history` → HistoryPage（Task 8-10 各自填充页面，本任务先放占位组件）

- [ ] **Step 1: 脚手架 + 装依赖**

Run:
```bash
npm create vite@latest frontend -- --template react-ts
cd frontend && npm install
npm install react-router-dom echarts framer-motion
npm install -D tailwindcss @tailwindcss/vite
```

- [ ] **Step 2: 配置 vite.config.ts 与 index.css**

`frontend/vite.config.ts`:
```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: { '/api': 'http://localhost:8000' },
  },
})
```

`frontend/src/index.css` 全文替换：
```css
@import "tailwindcss";
```

删除脚手架自带的 `frontend/src/App.css`，并清空 `frontend/src/assets/` 内不需要的示例 svg。

- [ ] **Step 3: 写 api/types.ts**

`frontend/src/api/types.ts`:
```ts
export interface PromptOut {
  title: string
  text: string
}

export interface EssayCreate {
  prompt_title: string
  prompt_text: string
  content: string
  duration_sec: number
}

export interface EssayOut {
  id: number
  status: 'pending' | 'done' | 'needs_review'
  total_band: number | null
  prompt_title: string
  word_count: number
  created_at: string
}

export interface BandScores {
  task_response: number
  coherence: number
  lexical: number
  grammar: number
  overall: number
}

export interface Annotation {
  sentence_index: number
  original: string
  issue: string
  suggestion: string
  error_type: string | null
}

export interface FeedbackOut {
  bands: BandScores
  annotations: Annotation[]
  rewrite: string
  is_mock: boolean
}

export interface ErrorItemOut {
  id: number
  error_type: string
  context: string
  created_at: string
}

export interface EssayDetail extends EssayOut {
  prompt_text: string
  content: string
  feedback: FeedbackOut | null
  errors: ErrorItemOut[]
}
```

- [ ] **Step 4: 写 api/client.ts**

`frontend/src/api/client.ts`:
```ts
import type { EssayCreate, EssayDetail, EssayOut, ErrorItemOut, PromptOut } from './types'

const BASE = '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, init)
  if (!resp.ok) {
    const body = await resp.text()
    throw new Error(`API ${resp.status}: ${body}`)
  }
  return resp.json() as Promise<T>
}

export function listPrompts(): Promise<PromptOut[]> {
  return request('/prompts')
}

export function getSample(): Promise<{ title: string; prompt_text: string; content: string }> {
  return request('/sample')
}

export function submitEssay(body: EssayCreate): Promise<EssayOut> {
  return request('/essays', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function listEssays(): Promise<EssayOut[]> {
  return request('/essays')
}

export function getEssay(id: number): Promise<EssayDetail> {
  return request(`/essays/${id}`)
}

export function listErrors(): Promise<ErrorItemOut[]> {
  return request('/errors')
}
```

- [ ] **Step 5: 写 NavBar 与路由骨架**

`frontend/src/components/NavBar.tsx`:
```tsx
import { NavLink } from 'react-router-dom'

const links = [
  { to: '/', label: '仪表盘' },
  { to: '/write', label: '写作练习' },
  { to: '/history', label: '历史记录' },
]

export function NavBar() {
  return (
    <nav className="flex items-center gap-6 border-b border-slate-200 bg-white px-6 py-3">
      <span className="text-lg font-bold text-indigo-600">雅思私教</span>
      {links.map((l) => (
        <NavLink
          key={l.to}
          to={l.to}
          className={({ isActive }) =>
            isActive ? 'font-semibold text-indigo-600' : 'text-slate-500 hover:text-slate-800'
          }
        >
          {l.label}
        </NavLink>
      ))}
    </nav>
  )
}
```

`frontend/src/App.tsx` 全文替换（占位页面由 Task 8-10 替换为真页面）:
```tsx
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { NavBar } from './components/NavBar'

function Placeholder({ name }: { name: string }) {
  return <div className="p-10 text-slate-400">{name}（待实现）</div>
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-slate-50 text-slate-800">
        <NavBar />
        <main className="mx-auto max-w-6xl p-6">
          <Routes>
            <Route path="/" element={<Placeholder name="仪表盘" />} />
            <Route path="/write" element={<Placeholder name="写作练习" />} />
            <Route path="/result/:id" element={<Placeholder name="批改结果" />} />
            <Route path="/history" element={<Placeholder name="历史记录" />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
```

`frontend/src/main.tsx` 保持脚手架内容（确认它 import 了 `./index.css`），不做其他修改。

- [ ] **Step 6: 验证构建与联调**

Run:
```bash
cd frontend && npm run build
```
Expected: `tsc -b && vite build` 通过，无类型错误

联调：后端 `uvicorn app.main:app --port 8000` 与前端 `npm run dev` 同时运行，浏览器开 `http://localhost:5173`，导航栏可见，四个路由可切换（显示占位文案）。

- [ ] **Step 7: Commit**

```bash
git add frontend/ && git commit -m "feat: 前端骨架 + API client + 路由布局"
```

---

### Task 8: 写作页（题目选择 + 实时分析条 + 示例填充）

**Files:**
- Create: `frontend/src/pages/WritingPage.tsx`
- Create: `frontend/src/components/AnalysisBar.tsx`
- Modify: `frontend/src/App.tsx`（`/write` 路由换真页面）

**Interfaces:**
- Consumes: `listPrompts / getSample / submitEssay`（Task 7）
- Produces: `AnalysisBar` 组件 props：`{ content: string }`；`estimateBand(content: string): string` 与 `advancedRatio(content: string): number`（`AnalysisBar.tsx` 导出，纯函数，前端启发式不调 LLM）

- [ ] **Step 1: 实现 AnalysisBar（含启发式函数）**

`frontend/src/components/AnalysisBar.tsx`:
```tsx
const ACADEMIC_WORDS = new Set([
  'furthermore', 'moreover', 'nevertheless', 'consequently', 'therefore', 'whereas',
  'significant', 'substantial', 'considerable', 'crucial', 'essential', 'beneficial',
  'detrimental', 'controversial', 'inevitable', 'phenomenon', 'perspective', 'implication',
  'alleviate', 'facilitate', 'implement', 'demonstrate', 'emphasize', 'undertake',
  'comprehensive', 'sustainable', 'increasingly', 'predominantly', 'notably', 'arguably',
  'drawback', 'outweigh', 'cohesion', 'supervision', 'isolation', 'infrastructure',
])

export function countWords(content: string): number {
  return content.trim().split(/\s+/).filter(Boolean).length
}

export function estimateBand(content: string): string {
  const n = countWords(content)
  if (n === 0) return '—'
  if (n < 150) return '≤ 5.0（词数不足）'
  if (n < 200) return '4.5 - 5.5'
  if (n < 260) return '5.5 - 6.5'
  if (n <= 340) return '6.0 - 7.0'
  return '6.5 - 7.5'
}

export function advancedRatio(content: string): number {
  const words = content.toLowerCase().replace(/[^a-z\s]/g, '').split(/\s+/).filter(Boolean)
  if (words.length === 0) return 0
  const hits = words.filter((w) => ACADEMIC_WORDS.has(w)).length
  return hits / words.length
}

export function AnalysisBar({ content }: { content: string }) {
  const ratio = advancedRatio(content)
  return (
    <div className="w-56 shrink-0 space-y-4 rounded-xl border border-slate-200 bg-white p-4 text-sm">
      <div className="font-semibold text-slate-700">AI 实时分析</div>
      <div>
        <div className="text-slate-400">词数</div>
        <div className="text-2xl font-bold text-indigo-600">{countWords(content)}</div>
        <div className="text-xs text-slate-400">Task 2 要求 ≥ 250 词</div>
      </div>
      <div>
        <div className="text-slate-400">预估分数区间</div>
        <div className="text-lg font-semibold">{estimateBand(content)}</div>
        <div className="text-xs text-slate-400">基于词数与词汇的粗估，非 AI 评分</div>
      </div>
      <div>
        <div className="text-slate-400">学术词汇占比</div>
        <div className="text-lg font-semibold">{(ratio * 100).toFixed(1)}%</div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: 实现 WritingPage**

`frontend/src/pages/WritingPage.tsx`:
```tsx
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getSample, listPrompts, submitEssay } from '../api/client'
import type { PromptOut } from '../api/types'
import { AnalysisBar, countWords } from '../components/AnalysisBar'

export default function WritingPage() {
  const [prompts, setPrompts] = useState<PromptOut[]>([])
  const [selected, setSelected] = useState(0)
  const [content, setContent] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const startRef = useRef(Date.now())
  const navigate = useNavigate()

  useEffect(() => {
    listPrompts().then(setPrompts).catch((e) => setError(String(e)))
  }, [])

  const fillSample = async () => {
    const sample = await getSample()
    const idx = prompts.findIndex((p) => p.title === sample.title)
    if (idx >= 0) setSelected(idx)
    setContent(sample.content)
    startRef.current = Date.now()
  }

  const submit = async () => {
    if (countWords(content) === 0 || submitting) return
    setSubmitting(true)
    setError('')
    try {
      const prompt = prompts[selected]
      const essay = await submitEssay({
        prompt_title: prompt.title,
        prompt_text: prompt.text,
        content,
        duration_sec: Math.round((Date.now() - startRef.current) / 1000),
      })
      navigate(`/result/${essay.id}`)
    } catch (e) {
      setError(String(e))
      setSubmitting(false)
    }
  }

  if (prompts.length === 0) {
    return <div className="p-10 text-slate-400">加载题目中…</div>
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <select
          className="rounded-lg border border-slate-300 px-3 py-2"
          value={selected}
          onChange={(e) => setSelected(Number(e.target.value))}
        >
          {prompts.map((p, i) => (
            <option key={p.title} value={i}>{p.title}</option>
          ))}
        </select>
        <button
          onClick={fillSample}
          className="rounded-lg border border-indigo-300 px-3 py-2 text-indigo-600 hover:bg-indigo-50"
        >
          试试这个（填充示例作文）
        </button>
      </div>
      <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-600">
        {prompts[selected].text}
      </div>
      <div className="flex gap-4">
        <textarea
          className="min-h-[420px] flex-1 rounded-xl border border-slate-300 p-4 font-mono text-sm focus:border-indigo-400 focus:outline-none"
          placeholder="在这里写你的 Task 2 作文（250 词以上）…"
          value={content}
          onChange={(e) => setContent(e.target.value)}
        />
        <AnalysisBar content={content} />
      </div>
      {error && <div className="text-sm text-red-500">{error}</div>}
      <button
        onClick={submit}
        disabled={countWords(content) === 0 || submitting}
        className="rounded-xl bg-indigo-600 px-6 py-3 font-semibold text-white disabled:opacity-40"
      >
        {submitting ? '提交中…' : '提交批改'}
      </button>
    </div>
  )
}
```

- [ ] **Step 3: 接入路由**

`frontend/src/App.tsx`：顶部加 `import WritingPage from './pages/WritingPage'`，将 `/write` 路由的 `element={<Placeholder name="写作练习" />}` 改为 `element={<WritingPage />}`。

- [ ] **Step 4: 构建 + 手测**

Run: `cd frontend && npm run build`
Expected: 通过

手测（前后端同开）：进 `/write`，下拉框有 4 道题；点「试试这个」自动选中"科技话题：远程办公"并填充约 260 词示例；分析条词数/预估区间/学术词汇占比实时变化；点「提交批改」跳转 `/result/1`（结果页还是占位，属正常）。

- [ ] **Step 5: Commit**

```bash
git add frontend/ && git commit -m "feat: 写作页 + AI 实时分析条 + 示例填充"
```

---

### Task 9: 结果页（轮询 + 扫描动画 + 雷达图 + 打字机批注 + 改写对比）

**Files:**
- Create: `frontend/src/hooks/useEcharts.ts`
- Create: `frontend/src/components/ScanOverlay.tsx`
- Create: `frontend/src/components/RadarChart.tsx`
- Create: `frontend/src/components/AnnotationList.tsx`
- Create: `frontend/src/components/DiffView.tsx`
- Create: `frontend/src/pages/ResultPage.tsx`
- Modify: `frontend/src/App.tsx`（`/result/:id` 路由换真页面）

**Interfaces:**
- Consumes: `getEssay`（Task 7）、`EssayDetail / Annotation`（Task 7 types）
- Produces: `useEcharts(option: EChartsOption): RefObject<HTMLDivElement>`（`hooks/useEcharts.ts`，RadarChart 与 Task 10 的成绩曲线共用）

- [ ] **Step 1: useEcharts hook**

`frontend/src/hooks/useEcharts.ts`:
```ts
import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'

export function useEcharts(option: EChartsOption) {
  const ref = useRef<HTMLDivElement>(null)
  const optionJson = JSON.stringify(option)
  useEffect(() => {
    if (!ref.current) return
    const chart = echarts.init(ref.current)
    chart.setOption(JSON.parse(optionJson))
    const onResize = () => chart.resize()
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      chart.dispose()
    }
  }, [optionJson])
  return ref
}
```

- [ ] **Step 2: ScanOverlay（扫描动画）**

`frontend/src/components/ScanOverlay.tsx`:
```tsx
import { motion } from 'framer-motion'

export function ScanOverlay({ text }: { text: string }) {
  return (
    <div className="relative overflow-hidden rounded-xl border border-slate-200 bg-white p-6">
      <pre className="whitespace-pre-wrap font-mono text-sm text-slate-500">{text}</pre>
      <motion.div
        className="absolute inset-x-0 h-16 bg-gradient-to-b from-transparent via-indigo-300/40 to-transparent"
        initial={{ top: '-10%' }}
        animate={{ top: '110%' }}
        transition={{ duration: 2.2, repeat: Infinity, ease: 'linear' }}
      />
      <div className="mt-4 text-center text-sm text-indigo-500">AI 考官正在逐句批改，请稍候…</div>
    </div>
  )
}
```

- [ ] **Step 3: RadarChart（生长动画由 echarts 自带 animation 完成）**

`frontend/src/components/RadarChart.tsx`:
```tsx
import { useEcharts } from '../hooks/useEcharts'
import type { BandScores } from '../api/types'

export function RadarChart({ bands }: { bands: BandScores }) {
  const ref = useEcharts({
    radar: {
      indicator: [
        { name: '任务回应 TR', max: 9 },
        { name: '连贯衔接 CC', max: 9 },
        { name: '词汇资源 LR', max: 9 },
        { name: '语法 GRA', max: 9 },
      ],
    },
    series: [
      {
        type: 'radar',
        data: [
          {
            value: [bands.task_response, bands.coherence, bands.lexical, bands.grammar],
            name: '本次得分',
            areaStyle: { opacity: 0.25 },
            itemStyle: { color: '#4f46e5' },
          },
        ],
      },
    ],
    animationDuration: 1200,
  })
  return <div ref={ref} className="h-72 w-full" />
}
```

- [ ] **Step 4: AnnotationList（打字机逐条浮现）**

`frontend/src/components/AnnotationList.tsx`:
```tsx
import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import type { Annotation } from '../api/types'

export function AnnotationList({ annotations }: { annotations: Annotation[] }) {
  const [visibleCount, setVisibleCount] = useState(0)

  useEffect(() => {
    setVisibleCount(0)
    if (annotations.length === 0) return
    const timer = setInterval(() => {
      setVisibleCount((n) => {
        if (n >= annotations.length) {
          clearInterval(timer)
          return n
        }
        return n + 1
      })
    }, 600)
    return () => clearInterval(timer)
  }, [annotations])

  return (
    <div className="space-y-3">
      {annotations.slice(0, visibleCount).map((a, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-xl border border-slate-200 bg-white p-4 text-sm"
        >
          <div className="mb-1 flex items-center gap-2">
            <span className="rounded bg-red-100 px-2 py-0.5 text-xs text-red-600">
              {a.error_type ?? '批注'}
            </span>
            <span className="text-xs text-slate-400">第 {a.sentence_index + 1} 句</span>
          </div>
          <div className="text-slate-500 line-through">{a.original}</div>
          <div className="mt-1 text-slate-700">{a.issue}</div>
          <div className="mt-1 text-emerald-700">✎ {a.suggestion}</div>
        </motion.div>
      ))}
      {visibleCount < annotations.length && (
        <div className="text-center text-xs text-slate-400">AI 正在输出批注…</div>
      )}
    </div>
  )
}
```

- [ ] **Step 5: DiffView（原文 vs 改写版并排）**

`frontend/src/components/DiffView.tsx`:
```tsx
import type { Annotation } from '../api/types'

/** 原文列：被批注的句子按 original 字符串匹配标红；右列为 AI 改写版。 */
export function DiffView({ original, rewrite, annotations }: {
  original: string
  rewrite: string
  annotations: Annotation[]
}) {
  const flagged = annotations.map((a) => a.original)
  const sentences = original.match(/[^.!?]+[.!?]+(\s|$)/g) ?? [original]

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <div className="mb-2 text-sm font-semibold text-slate-500">你的原文</div>
        <p className="text-sm leading-7">
          {sentences.map((s, i) => {
            const isFlagged = flagged.some((f) => s.trim().startsWith(f.trim().slice(0, 30)))
            return (
              <span key={i} className={isFlagged ? 'rounded bg-red-100 px-0.5' : undefined}>
                {s}
              </span>
            )
          })}
        </p>
      </div>
      <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
        <div className="mb-2 text-sm font-semibold text-emerald-600">AI 改写版（7.5 分水平）</div>
        <p className="text-sm leading-7 text-slate-700">{rewrite}</p>
      </div>
    </div>
  )
}
```

- [ ] **Step 6: ResultPage（轮询组装）**

`frontend/src/pages/ResultPage.tsx`:
```tsx
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getEssay } from '../api/client'
import type { EssayDetail } from '../api/types'
import { AnnotationList } from '../components/AnnotationList'
import { DiffView } from '../components/DiffView'
import { RadarChart } from '../components/RadarChart'
import { ScanOverlay } from '../components/ScanOverlay'

export default function ResultPage() {
  const { id } = useParams<{ id: string }>()
  const [essay, setEssay] = useState<EssayDetail | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!id) return
    let stopped = false
    const poll = async () => {
      try {
        const detail = await getEssay(Number(id))
        if (stopped) return
        setEssay(detail)
        if (detail.status === 'pending') {
          setTimeout(poll, 2000)
        }
      } catch (e) {
        if (!stopped) setError(String(e))
      }
    }
    poll()
    return () => { stopped = true }
  }, [id])

  if (error) return <div className="p-10 text-red-500">{error}</div>
  if (!essay) return <div className="p-10 text-slate-400">加载中…</div>

  if (essay.status === 'pending') {
    return <ScanOverlay text={essay.content} />
  }
  if (essay.status === 'needs_review' || !essay.feedback) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-6 text-amber-700">
        本次批改未能完成（AI 返回格式异常或服务不可用），请重新提交。原文已保存在历史记录中。
      </div>
    )
  }

  const fb = essay.feedback
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-6">
        <div className="rounded-2xl bg-indigo-600 px-8 py-6 text-center text-white">
          <div className="text-sm opacity-80">综合评分</div>
          <div className="text-5xl font-bold">{fb.bands.overall.toFixed(1)}</div>
        </div>
        <div>
          <div className="font-semibold">{essay.prompt_title}</div>
          <div className="text-sm text-slate-400">
            {essay.word_count} 词 · 用时 {Math.round(essay.duration_sec / 60)} 分钟
          </div>
          {fb.is_mock && (
            <div className="mt-1 rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-700">
              演示数据（未配置 DEEPSEEK_API_KEY）
            </div>
          )}
        </div>
      </div>
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <RadarChart bands={fb.bands} />
      </div>
      <div>
        <h3 className="mb-3 font-semibold">逐句批注（{fb.annotations.length} 条）</h3>
        <AnnotationList annotations={fb.annotations} />
      </div>
      <div>
        <h3 className="mb-3 font-semibold">原文 vs 改写版</h3>
        <DiffView original={essay.content} rewrite={fb.rewrite} annotations={fb.annotations} />
      </div>
    </div>
  )
}
```

- [ ] **Step 7: 接入路由**

`frontend/src/App.tsx`：顶部加 `import ResultPage from './pages/ResultPage'`，将 `/result/:id` 的占位换成 `<ResultPage />`。

- [ ] **Step 8: 构建 + 手测**

Run: `cd frontend && npm run build`
Expected: 通过

手测：`/write` 提交示例作文 → 跳转结果页先看到扫描动画 → 约 2 秒后出现总分卡、雷达图、批注逐条浮现、双栏对比中原句标红；因为无 key，看到"演示数据"标签。

- [ ] **Step 9: Commit**

```bash
git add frontend/ && git commit -m "feat: 批改结果页（扫描动画/雷达图/打字机批注/改写对比）"
```

---

### Task 10: 历史页 + 简版仪表盘

**Files:**
- Create: `frontend/src/pages/HistoryPage.tsx`
- Create: `frontend/src/pages/DashboardPage.tsx`
- Modify: `frontend/src/App.tsx`（`/` 与 `/history` 路由换真页面）

**Interfaces:**
- Consumes: `listEssays / listErrors`（Task 7）、`useEcharts`（Task 9）

- [ ] **Step 1: HistoryPage**

`frontend/src/pages/HistoryPage.tsx`:
```tsx
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listEssays } from '../api/client'
import type { EssayOut } from '../api/types'
import { useEcharts } from '../hooks/useEcharts'

export default function HistoryPage() {
  const [essays, setEssays] = useState<EssayOut[]>([])

  useEffect(() => {
    listEssays().then(setEssays).catch(() => setEssays([]))
  }, [])

  const graded = essays.filter((e) => e.total_band !== null)
  const ref = useEcharts({
    xAxis: {
      type: 'category',
      data: [...graded].reverse().map((e) => new Date(e.created_at).toLocaleDateString()),
    },
    yAxis: { type: 'value', min: 4, max: 9 },
    series: [{
      type: 'line',
      smooth: true,
      data: [...graded].reverse().map((e) => e.total_band),
      itemStyle: { color: '#4f46e5' },
      markLine: {
        silent: true,
        data: [{ yAxis: 6.5, label: { formatter: '目标 6.5' } }],
        lineStyle: { color: '#f59e0b', type: 'dashed' },
      },
    }],
    tooltip: { trigger: 'axis' },
  })

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <div className="mb-2 font-semibold">成绩曲线</div>
        {graded.length > 0
          ? <div ref={ref} className="h-64 w-full" />
          : <div className="py-10 text-center text-sm text-slate-400">还没有已批改的记录</div>}
      </div>
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-slate-500">
            <tr>
              <th className="px-4 py-2">题目</th>
              <th className="px-4 py-2">词数</th>
              <th className="px-4 py-2">用时</th>
              <th className="px-4 py-2">总分</th>
              <th className="px-4 py-2">状态</th>
            </tr>
          </thead>
          <tbody>
            {essays.map((e) => (
              <tr key={e.id} className="border-t border-slate-100">
                <td className="px-4 py-2">
                  <Link to={`/result/${e.id}`} className="text-indigo-600 hover:underline">
                    {e.prompt_title}
                  </Link>
                </td>
                <td className="px-4 py-2">{e.word_count}</td>
                <td className="px-4 py-2">{Math.round(e.duration_sec / 60)} 分钟</td>
                <td className="px-4 py-2 font-semibold">
                  {e.total_band !== null ? e.total_band.toFixed(1) : '—'}
                </td>
                <td className="px-4 py-2 text-slate-400">
                  {{ pending: '批改中', done: '已完成', needs_review: '需重试' }[e.status]}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: DashboardPage**

`frontend/src/pages/DashboardPage.tsx`:
```tsx
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { listErrors, listEssays } from '../api/client'
import type { EssayOut, ErrorItemOut } from '../api/types'

const TARGET_BAND = 6.5

export default function DashboardPage() {
  const [essays, setEssays] = useState<EssayOut[]>([])
  const [errors, setErrors] = useState<ErrorItemOut[]>([])

  useEffect(() => {
    listEssays().then(setEssays).catch(() => undefined)
    listErrors().then(setErrors).catch(() => undefined)
  }, [])

  const latest = essays.find((e) => e.total_band !== null)
  const topErrors = useMemo(() => {
    const counts = new Map<string, number>()
    for (const e of errors) counts.set(e.error_type, (counts.get(e.error_type) ?? 0) + 1)
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5)
  }, [errors])

  const progress = latest?.total_band ? Math.min(latest.total_band / TARGET_BAND, 1) : 0

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-white p-6">
          <div className="text-sm text-slate-400">当前预测分 → 目标分</div>
          <div className="mt-1 text-3xl font-bold text-indigo-600">
            {latest ? latest.total_band!.toFixed(1) : '—'}
            <span className="text-base font-normal text-slate-400"> / {TARGET_BAND}</span>
          </div>
          <div className="mt-3 h-2 rounded-full bg-slate-100">
            <div
              className="h-2 rounded-full bg-indigo-500 transition-all"
              style={{ width: `${progress * 100}%` }}
            />
          </div>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-6">
          <div className="text-sm text-slate-400">累计练习</div>
          <div className="mt-1 text-3xl font-bold">{essays.length} 篇</div>
          <Link to="/write" className="mt-3 inline-block text-sm text-indigo-600 hover:underline">
            开始新一篇 →
          </Link>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-6">
          <div className="text-sm text-slate-400">我的高频错误 TOP</div>
          {topErrors.length > 0 ? (
            <ul className="mt-2 space-y-1 text-sm">
              {topErrors.map(([type, count]) => (
                <li key={type} className="flex justify-between">
                  <span>{type}</span>
                  <span className="text-slate-400">{count} 次</span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="mt-2 text-sm text-slate-400">完成一次批改后生成</div>
          )}
        </div>
      </div>
      <div className="rounded-xl border border-dashed border-slate-300 p-6 text-center text-sm text-slate-400">
        能力树、口语 / 听力 / 词汇模块将在 V2-V4 解锁
      </div>
    </div>
  )
}
```

- [ ] **Step 3: 接入路由**

`frontend/src/App.tsx`：加 `import DashboardPage from './pages/DashboardPage'` 与 `import HistoryPage from './pages/HistoryPage'`，将 `/` 与 `/history` 的占位分别换成 `<DashboardPage />`、`<HistoryPage />`。此时 `Placeholder` 组件已无引用，从 App.tsx 中删除。

- [ ] **Step 4: 构建 + 手测**

Run: `cd frontend && npm run build`
Expected: 通过

手测：`/` 显示三张卡片（最新分/篇数/错误 TOP5，进度条指向 6.5）；`/history` 显示曲线（含 6.5 虚线目标线）与记录表，点题目可回到结果页。

- [ ] **Step 5: Commit**

```bash
git add frontend/ && git commit -m "feat: 历史成绩曲线 + 简版仪表盘"
```

---

### Task 11: 端到端验证 + README + 推送

**Files:**
- Create: `backend/.env.example`
- Modify: `README.md`

- [ ] **Step 1: 全量测试 + 构建**

Run:
```bash
cd backend && uv run pytest -v
cd ../frontend && npm run build
```
Expected: 后端全绿；前端构建通过

- [ ] **Step 2: 端到端冒烟（无 key，走 mock）**

Run（两个终端）:
```bash
cd backend && uv run uvicorn app.main:app --port 8000
cd frontend && npm run dev
```
完整走一遍：仪表盘（空态）→ 写作页「试试这个」→ 提交 → 扫描动画 → 结果页（总分 6.0、雷达图、4 条批注、双栏对比、"演示数据"标签）→ 历史页（一条记录、曲线一个点）→ 仪表盘（预测分 6.0、错误 TOP 四项）。再提交第二篇，确认曲线出现第二个点、能力点标黄不重复。

- [ ] **Step 3: （可选，有 key 时）真实批改验证**

`backend/.env.example`:
```bash
DEEPSEEK_API_KEY=sk-xxxxxxxx
```
复制为 `backend/.env` 填真 key，重启后端，提交一篇自己写的作文，确认 `is_mock` 为 false 且批注针对新内容。无 key 则跳过并在最终汇报中说明。

- [ ] **Step 4: 写 README**

`README.md` 全文替换：
```markdown
# yasi

AI 驱动的雅思私教（V1：写作 Task 2 智能批改）。

## 快速开始

```bash
# 后端（Python >= 3.11，优先 uv）
cd backend
uv sync                      # 无 uv：python -m venv .venv && .venv/bin/pip install -e .
cp .env.example .env         # 填入 DEEPSEEK_API_KEY；不填则用内置演示批改
uv run uvicorn app.main:app --port 8000

# 前端（Node >= 18）
cd frontend
npm install
npm run dev                  # http://localhost:5173
```

## 测试

```bash
cd backend && uv run pytest -v
cd frontend && npm run build
```

## 结构

- `backend/` FastAPI + SQLAlchemy 2.0 + SQLite；批改管线在 `app/services/grader.py`
- `frontend/` React + Vite + Tailwind + ECharts + Framer Motion
- `docs/superpowers/specs/` 设计规格；`docs/superpowers/plans/` 实施计划
```

- [ ] **Step 5: Commit 并推送**

```bash
git add -A && git commit -m "docs: README 与 env 示例，V1 完成" && git push
```

- [ ] **Step 6: 收尾核对（对照规格 §4 六项功能逐项确认）**

- 写作页（题目 + 分析条 + 试试这个）✓
- 批改中扫描动画 ✓
- 结果页（雷达图 + 逐句批注 + 并排对比）✓
- 历史页曲线 + 词数用时 ✓
- 仪表盘简版（最新分/篇数/错误 TOP）✓
- 示例系统（示例作文 + 完整批改结果，不写一字可体验）✓
- 能力树地基：9 表齐、写作分支 20 节点种子、批改后标黄 ✓
