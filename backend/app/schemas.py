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
    duration_sec: int
    module: str
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


class TopicOut(BaseModel):
    topic: str
    word_count: int
    mastered_count: int
    due_count: int


class WordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str
    pos: str
    meaning: str
    paraphrase_chain: list[str]
    example_sentence: str
    due_at: datetime | None = None
    reps: int = 0


class ReviewCardOut(BaseModel):
    word_id: int
    text: str
    pos: str
    meaning: str
    paraphrase_chain: list[str]
    example_sentence: str
    is_new: bool


class ReviewQueueOut(BaseModel):
    cards: list[ReviewCardOut]
    due_total: int


class ReviewSubmit(BaseModel):
    quality: int = Field(ge=1, le=5)

    @field_validator("quality")
    @classmethod
    def only_three_levels(cls, v: int) -> int:
        if v not in (1, 3, 5):
            raise ValueError("quality 仅支持 1（不认识）/ 3（模糊）/ 5（认识）")
        return v


class ForecastOut(BaseModel):
    date: str
    count: int
