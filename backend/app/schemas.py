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
