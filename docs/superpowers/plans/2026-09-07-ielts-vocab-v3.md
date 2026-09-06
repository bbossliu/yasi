# 雅思 V3 词汇模块 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 V3 词汇模块——10 话题 × 20 词种子词库（释义/例句/同义替换链）、SM-2 间隔重复复习（三档自评）、批改错词联动自动建卡、前端话题浏览 + 复习会话 + 仪表盘掌握率。

**Architecture:** 复用既有 `word`/`review_card` 表（word 加 meaning/pos 两列）。SM-2 为纯函数服务；错词联动挂在写作/口语两条批改管线的 error_item 写入点之后。前端新增 VocabPage（浏览 + 内嵌复习会话）。

**Tech Stack:** 同 V1/V2（FastAPI/SQLAlchemy 2.0/Pydantic v2/pytest；React/Vite/TS/Tailwind/ECharts）。无新增后端依赖；扩充脚本复用 openai SDK。

**上游规格:** `docs/superpowers/specs/2026-09-07-ielts-vocab-v3-design.md`

## Global Constraints

- 沿用 V1/V2 全部约束：uv/pytest/tmp SQLite/中文 Conventional Commits/端口 8022 冒烟/unset 代理/Node v22
- SM-2 参数：quality ∈ {1,3,5}（不认识/模糊/认识）；初始 ease=2.5；interval 序列 1→6→round(prev*ease)；ease 下限 1.3
- 掌握判定：`reps >= 2 且 interval_days >= 7`
- 词库种子：10 话题（教育/科技/环境/犯罪/媒体/健康/工作/城市化/文化/全球化）× 20 词
- 错词联动只处理 `error_type=="词汇搭配"` 的 error_item，词边界子串匹配（小写），幂等
- 本机 env 有真实 DEEPSEEK_API_KEY：测试中 monkeypatch 掉；扩充脚本只在用户手动运行时走真实 API

---

### Task 1: word 模型加列 + 词库种子数据

**Files:**
- Modify: `backend/app/models.py`（Word 加 meaning/pos）
- Create: `backend/app/data/vocab_seed.py`
- Create: `backend/app/seed_vocab.py`
- Modify: `backend/app/main.py`（startup 加 seed_vocab_db）
- Test: `backend/tests/test_vocab_seed.py`

**Interfaces:**
- Consumes: V1 `Word` 模型
- Produces: `Word.meaning: str`、`Word.pos: str`；`VOCAB_WORDS: list[dict]`（`app.data.vocab_seed`，200 条）；`seed_vocab_db(session)`（幂等，word 表非空即跳过）。Task 2/3 消费。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_vocab_seed.py`:
```python
from sqlalchemy import select

from app.data.vocab_seed import VOCAB_WORDS
from app.database import Base, make_session_factory
from app.models import Word
from app.seed_vocab import seed_vocab_db


def make_db(tmp_path):
    factory = make_session_factory(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(factory.kw["bind"])
    return factory


def test_vocab_seed_data_shape():
    assert len(VOCAB_WORDS) == 200
    topics = {w["topic"] for w in VOCAB_WORDS}
    assert len(topics) == 10
    for w in VOCAB_WORDS:
        assert w["text"] and w["meaning"] and w["pos"]
        assert len(w["paraphrase_chain"]) >= 3
        assert len(w["example_sentence"].split()) >= 6
    # 词文本唯一
    texts = [w["text"] for w in VOCAB_WORDS]
    assert len(set(texts)) == 200


def test_seed_vocab_idempotent(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    seed_vocab_db(s)
    seed_vocab_db(s)
    words = s.scalars(select(Word)).all()
    assert len(words) == 200
    w = next(w for w in words if w.text == "abandon")
    assert w.meaning == "放弃；抛弃"
    assert "give up" in w.paraphrase_chain
    s.close()
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_vocab_seed.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.data.vocab_seed'`

- [ ] **Step 3: models.py 的 Word 加列**

```python
class Word(Base):
    __tablename__ = "word"

    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(String(100), unique=True)
    pos: Mapped[str] = mapped_column(String(20), default="")
    meaning: Mapped[str] = mapped_column(String(300), default="")
    topic: Mapped[str] = mapped_column(String(50), default="")
    paraphrase_chain: Mapped[list] = mapped_column(JSON, default=list)
    example_sentence: Mapped[str] = mapped_column(Text, default="")
```

- [ ] **Step 4: 实现 vocab_seed.py（200 词条）**

`backend/app/data/vocab_seed.py`：`VOCAB_WORDS: list[dict]`，字段 `text/pos/meaning/topic/paraphrase_chain/example_sentence`。

话题与词条要求（每个话题 20 词，雅思核心词汇，替换链 3-5 个，例句为雅思写作/口语风格）：

- **教育**：abandon(v. 放弃；抛弃 [give up, quit, relinquish, forsake])、academic(adj. 学术的)、curriculum(n. 课程体系)、discipline、compulsory(adj. 强制的)、literacy(n. 读写能力)、pedagogy、tuition(n. 学费/教学)、vocational(adj. 职业的)、motivate、stimulate、comprehend、rote(n. 死记硬背)、scholarship(n. 奖学金)、dropout(n. 辍学者)、aptitude(n. 天资)、illiterate(adj. 文盲的)、enroll(v. 注册入学)、graduate、specialize(v. 专攻 [major in, focus on, concentrate on])
- **科技**：innovation、automation、artificial、cutting-edge(adj. 前沿的)、obsolete(adj. 过时的 [outdated, antiquated, outmoded])、breakthrough、digital、privacy、surveillance(n. 监控)、algorithm、 gadget、cyber、virtual、telecommunication、upgrade、malfunction(n./v. 故障)、user-friendly、streamline(v. 精简优化)、transform(v. 彻底改变 [revolutionize, reshape, overhaul])、database
- **环境**：sustainable(adj. 可持续的)、emission(n. 排放 [discharge, release])、contaminate(v. 污染 [pollute, taint])、deforestation、biodiversity、renewable、ecosystem、conservation、deplete(v. 耗尽 [exhaust, drain])、catastrophic、mitigate(v. 缓解 [alleviate, reduce, lessen])、toxic、landfill、carbon、recyclable、habitat、erosion、greenhouse、scarcity(n. 稀缺 [shortage, dearth])、deteriorate(v. 恶化 [worsen, decline])
- **犯罪**：deter(v. 威慑 [discourage, dissuade])、rehabilitate(v. 改造)、offender(n. 违法者)、juvenile(adj. 青少年的)、penalty(n. 刑罚 [punishment, sanction])、imprisonment、deterrent、recidivism(n. 再犯)、victim、surveillance、legislation、enforce(v. 执法 [implement, execute])、prohibit(v. 禁止 [ban, forbid, outlaw])、smuggle、felony(n. 重罪)、parole、innocent、guilty、prosecute(v. 起诉)、crime rate
- **媒体**：misleading(adj. 误导的)、sensational(adj. 哗众取宠的)、bias(n. 偏见 [prejudice, partiality])、censorship、journalism、headline、viral(adj. 疯传的)、propaganda、advertising、circulation、tabloid、celebrity、influence(v./n. 影响 [affect, sway, shape])、portray(v. 描绘 [depict, describe, represent])、exaggerate(v. 夸大 [overstate, inflate, magnify])、credibility、mainstream、viewer、fake news、manipulate
- **健康**：obesity(n. 肥胖)、epidemic(n. 流行病)、nutrition、sedentary(adj. 久坐的)、chronic(adj. 慢性的)、immune(adj. 免疫的)、therapy、hygiene、contagious、diagnose(v. 诊断)、symptom、vaccinate、wellbeing(n. 健康幸福)、life expectancy、mental(adj. 心理的)、addiction(n. 成瘾 [dependence, craving])、preventive(adj. 预防的)、remedy(n. 疗法 [cure, treatment])、hygiene、fitness
- **工作**：commute(v./n. 通勤)、redundant(adj. 被裁员的)、incentive(n. 激励 [motivation, stimulus])、promotion、resign(v. 辞职 [quit, step down])、colleague(n. 同事 [coworker, associate])、deadline、overtime、freelance(adj. 自由职业的)、productivity、workload、entrepreneur、candidate(n. 候选人 [applicant, contender])、recruit(v. 招聘 [hire, employ, take on])、responsibility、salary(n. 薪资 [wage, income, pay])、telecommute、turnover(n. 人员流动)、career、qualification
- **城市化**：infrastructure(n. 基础设施)、metropolitan(adj. 大都市的)、congestion(n. 拥堵)、overcrowded、housing、resident(n. 居民 [inhabitant, dweller])、municipal(adj. 市政的)、skyscraper、slum、urbanize、commute、amenity(n. 生活设施 [facility])、population density、rural(adj. 乡村的)、migrate(v. 迁移 [relocate, move])、gentrification、public transport、affordable(adj. 负担得起的)、sprawl(n. 无序扩张)、metropolis
- **文化**：heritage(n. 遗产 [legacy, inheritance])、diversity(n. 多样性 [variety, multiplicity])、indigenous(adj. 本土的)、ritual(n. 仪式 [ceremony, rite])、tradition(n. 传统 [custom, convention])、assimilate(v. 同化)、cosmopolitan(adj. 国际化的)、folklore、museum、festival、multicultural、preserve(v. 保护传承 [conserve, maintain, safeguard])、extinct(adj. 消亡的 [vanished, died out])、language barrier、stereotype、values、identity(n. 认同)、globalized、ceremony、cuisine
- **全球化**：globalization、outsourcing、multinational(adj./n. 跨国的)、tariff(n. 关税)、trade barrier、interconnected(adj. 互联的)、cultural exchange、homogenize(v. 同质化)、economy(n. 经济体)、import/export、supply chain、interdependence、domestic(adj. 国内的 [internal, national])、foreign investment、cooperation(n. 合作 [collaboration, partnership])、compete(v. 竞争 [rival, contend, vie])、emerging market、international、prosperity(n. 繁荣 [boom, affluence])、exchange rate、diplomacy

每词字段示例：
```python
{"text": "abandon", "pos": "v.", "meaning": "放弃；抛弃", "topic": "教育",
 "paraphrase_chain": ["give up", "quit", "relinquish", "forsake"],
 "example_sentence": "Some students abandon their studies when they encounter financial difficulties."}
```

**词条质量要求**：例句 10-20 词、雅思 Task 2 风格（话题相关、书面正式）；替换链按口语→书面递进排序；meaning 给 1-2 个核心中文释义。上述词条列表中给出了约一半词的完整字段示范，其余词按同样标准补齐（meaning/pos 必给，替换链 ≥3，例句必给）。

- [ ] **Step 5: 实现 seed_vocab.py + main.py 接线**

`backend/app/seed_vocab.py`:
```python
from sqlalchemy import select

from app.data.vocab_seed import VOCAB_WORDS
from app.models import Word


def seed_vocab_db(session) -> None:
    """幂等写入词库种子（word 表非空即跳过）。"""
    if session.scalars(select(Word.id)).first():
        return
    for w in VOCAB_WORDS:
        session.add(Word(
            text=w["text"], pos=w["pos"], meaning=w["meaning"], topic=w["topic"],
            paraphrase_chain=w["paraphrase_chain"], example_sentence=w["example_sentence"],
        ))
    session.commit()
```

`main.py` 的 `init_db` 中 `seed_speaking_db(session)` 之后加：
```python
        from app.seed_vocab import seed_vocab_db
        seed_vocab_db(session)
```

- [ ] **Step 6: 测试通过 + 全套回归**

Run: `cd backend && uv run pytest -v`
Expected: 全部通过（36 既有 + 2 新增）

- [ ] **Step 7: Commit**

```bash
git add backend/ && git commit -m "feat: 词库种子数据（10 话题 200 词）+ word 表加释义词性"
```

---

### Task 2: SM-2 服务 + 错词联动

**Files:**
- Create: `backend/app/services/sm2.py`
- Create: `backend/app/services/vocab_link.py`
- Modify: `backend/app/services/grader.py`（run_grading 接线 link_vocab_errors）
- Modify: `backend/app/services/speaking_grader.py`（run_speaking_turn 接线）
- Test: `backend/tests/test_sm2.py`、`backend/tests/test_vocab_link.py`

**Interfaces:**
- Consumes: `Word / ReviewCard / ErrorItem`（V1/V3-1）
- Produces:
  - `sm2_review(card: ReviewCard, quality: int, now: datetime) -> None`（原地更新 card 的 reps/interval_days/ease_factor/due_at）
  - `get_or_create_card(session, user_id: int, word_id: int) -> ReviewCard`（新建时 ease=2.5、interval=1、due=now、reps=0）
  - `build_review_queue(session, user_id: int, limit: int = 20, now: datetime | None = None) -> tuple[list[dict], int]`：返回（卡片列表, 到期总数）；卡片 dict 形如 `{"word_id", "text", "pos", "meaning", "paraphrase_chain", "example_sentence", "is_new"}`；先排到期卡（due_at <= now，按 due_at 升序），不足 limit 用未建卡的新词补齐（按 id 升序）
  - `link_vocab_errors(session, user_id: int, errors: list[ErrorItem]) -> list[int]`：对 error_type=="词汇搭配"的条目在 context 中匹配词库（小写词边界正则），命中词建卡或重置（interval=1、due=now）；返回命中的 word_id 列表。Task 3 的 API 与两条管线消费

- [ ] **Step 1: 写失败测试 test_sm2.py**

```python
from datetime import datetime, timedelta

from app.database import Base, make_session_factory
from app.models import ReviewCard, User, Word
from app.services.sm2 import build_review_queue, get_or_create_card, sm2_review

NOW = datetime(2026, 9, 7, 12, 0, 0)


def make_db(tmp_path):
    factory = make_session_factory(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(factory.kw["bind"])
    s = factory()
    s.add(User(id=1))
    for i in range(5):
        s.add(Word(id=i + 1, text=f"word{i}", pos="v.", meaning=f"含义{i}", topic="教育",
                   paraphrase_chain=["a", "b", "c"], example_sentence=f"Sentence {i} example."))
    s.commit()
    s.close()
    return factory


def test_sm2_first_pass_and_fail(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    card = get_or_create_card(s, 1, 1)
    assert card.ease_factor == 2.5 and card.reps == 0 and card.interval_days == 1

    sm2_review(card, 5, NOW)  # 第一次认识
    assert card.reps == 1 and card.interval_days == 1
    assert card.due_at == NOW + timedelta(days=1)

    sm2_review(card, 5, NOW)  # 第二次认识 → interval 6
    assert card.reps == 2 and card.interval_days == 6

    sm2_review(card, 5, NOW)  # 第三次 → 6 * 2.5 = 15
    assert card.reps == 3 and card.interval_days == 15

    sm2_review(card, 1, NOW)  # 不认识 → 重置
    assert card.reps == 0 and card.interval_days == 1
    s.close()


def test_sm2_quality3_keeps_progress_but_slower(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    card = get_or_create_card(s, 1, 1)
    sm2_review(card, 5, NOW)
    sm2_review(card, 5, NOW)
    # 两次认识后：reps=2, interval=6, ease=2.5
    sm2_review(card, 3, NOW)  # 模糊：interval 用旧 ease 推进（round(6*2.5)=15），ease 随后下降
    assert card.reps == 3
    assert card.interval_days == 15
    assert abs(card.ease_factor - 2.36) < 0.001  # 2.5 + 0.1 - 2*(0.08+2*0.02)
    s.close()


def test_sm2_ease_floor(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    card = get_or_create_card(s, 1, 1)
    for _ in range(10):
        sm2_review(card, 1, NOW)  # 反复失败 ease 不低于 1.3
    assert card.ease_factor >= 1.3
    s.close()


def test_review_queue_due_then_new(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    # word1 到期卡，word2 未到期卡，word3-5 新词
    c1 = get_or_create_card(s, 1, 1)
    c1.due_at = NOW - timedelta(days=1)
    c2 = get_or_create_card(s, 1, 2)
    c2.due_at = NOW + timedelta(days=3)
    s.commit()

    cards, due_total = build_review_queue(s, 1, limit=3, now=NOW)
    assert due_total == 1
    assert cards[0]["word_id"] == 1 and cards[0]["is_new"] is False
    assert cards[1]["is_new"] is True  # 新词补齐
    assert len(cards) == 3
    s.close()
```

- [ ] **Step 2: 写失败测试 test_vocab_link.py**

```python
from sqlalchemy import select

from app.database import Base, make_session_factory
from app.models import ErrorItem, ReviewCard, User, Word
from app.services.vocab_link import link_vocab_errors


def make_db(tmp_path):
    factory = make_session_factory(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(factory.kw["bind"])
    s = factory()
    s.add(User(id=1))
    s.add(Word(id=1, text="abandon", pos="v.", meaning="放弃", topic="教育",
               paraphrase_chain=[], example_sentence=""))
    s.add(Word(id=2, text="mitigate", pos="v.", meaning="缓解", topic="环境",
               paraphrase_chain=[], example_sentence=""))
    s.commit()
    s.close()
    return factory


def make_error(error_type, context):
    e = ErrorItem(user_id=1, practice_id=1, error_type=error_type, context=context)
    return e


def test_link_creates_and_resets_cards(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    # 命中 abandon（含词形变化 abandoning 也命中——用前缀匹配）
    hit = link_vocab_errors(s, 1, [make_error("词汇搭配", "People often abandon their plans too early.")])
    assert hit == [1]
    card = s.scalars(select(ReviewCard).where(ReviewCard.word_id == 1)).one()
    assert card.interval_days == 1

    # 重复命中：重置已有卡（先把它改成大间隔）
    card.interval_days = 30
    card.reps = 5
    s.commit()
    hit = link_vocab_errors(s, 1, [make_error("词汇搭配", "Never abandon hope.")])
    assert hit == [1]
    assert card.interval_days == 1 and card.reps == 0

    # 非词汇错误不动
    assert link_vocab_errors(s, 1, [make_error("时态", "abandon abandon")]) == []
    # 未命中词库不动
    assert link_vocab_errors(s, 1, [make_error("词汇搭配", "xyzzy plugh")]) == []
    s.close()


def test_link_no_duplicate_card(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    link_vocab_errors(s, 1, [make_error("词汇搭配", "abandon it"), make_error("词汇搭配", "mitigate risks")])
    s.commit()
    cards = s.scalars(select(ReviewCard)).all()
    assert len(cards) == 2
    s.close()
```

- [ ] **Step 3: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_sm2.py tests/test_vocab_link.py -v`
Expected: FAIL，`ModuleNotFoundError`

- [ ] **Step 4: 实现 sm2.py**

`backend/app/services/sm2.py`:
```python
from datetime import datetime, timedelta

from sqlalchemy import select

from app.models import ReviewCard, Word


def get_or_create_card(session, user_id: int, word_id: int) -> ReviewCard:
    card = session.scalars(
        select(ReviewCard).where(
            ReviewCard.user_id == user_id, ReviewCard.word_id == word_id)).first()
    if card is None:
        card = ReviewCard(user_id=user_id, word_id=word_id, due_at=datetime.now())
        session.add(card)
        session.flush()
    return card


def sm2_review(card: ReviewCard, quality: int, now: datetime) -> None:
    """标准 SM-2：quality 0-5（本系统只用 1/3/5）。原地更新卡片。"""
    if quality < 3:
        card.reps = 0
        card.interval_days = 1
    else:
        card.reps += 1
        if card.reps == 1:
            card.interval_days = 1
        elif card.reps == 2:
            card.interval_days = 6
        else:
            card.interval_days = round(card.interval_days * card.ease_factor)
        card.ease_factor = max(
            1.3, card.ease_factor + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    card.due_at = now + timedelta(days=card.interval_days)


def build_review_queue(session, user_id: int, limit: int = 20,
                       now: datetime | None = None) -> tuple[list[dict], int]:
    """到期卡优先（due 升序），不足 limit 用新词（未建卡）补齐。返回 (卡片列表, 到期总数)。"""
    now = now or datetime.now()
    due_cards = session.scalars(
        select(ReviewCard)
        .where(ReviewCard.user_id == user_id, ReviewCard.due_at <= now)
        .order_by(ReviewCard.due_at)).all()
    due_total = len(due_cards)

    queue: list[dict] = []
    word_ids = {c.word_id for c in due_cards}
    words = {w.id: w for w in session.scalars(
        select(Word).where(Word.id.in_(word_ids or {0}))).all()}
    for card in due_cards[:limit]:
        w = words[card.word_id]
        queue.append({"word_id": w.id, "text": w.text, "pos": w.pos, "meaning": w.meaning,
                      "paraphrase_chain": w.paraphrase_chain,
                      "example_sentence": w.example_sentence, "is_new": False})

    if len(queue) < limit:
        new_words = session.scalars(
            select(Word)
            .where(~Word.id.in_(
                select(ReviewCard.word_id).where(ReviewCard.user_id == user_id)))
            .order_by(Word.id).limit(limit - len(queue))).all()
        for w in new_words:
            queue.append({"word_id": w.id, "text": w.text, "pos": w.pos, "meaning": w.meaning,
                          "paraphrase_chain": w.paraphrase_chain,
                          "example_sentence": w.example_sentence, "is_new": True})
    return queue, due_total
```

- [ ] **Step 5: 实现 vocab_link.py**

`backend/app/services/vocab_link.py`:
```python
import re
from datetime import datetime

from sqlalchemy import select

from app.models import ErrorItem, Word
from app.services.sm2 import get_or_create_card


def link_vocab_errors(session, user_id: int, errors: list[ErrorItem]) -> list[int]:
    """词汇搭配错误 → 上下文命中词库 → 建卡或重置（强制复现）。返回命中的 word_id。"""
    targets = [e for e in errors if e.error_type == "词汇搭配" and e.context]
    if not targets:
        return []
    words = session.scalars(select(Word)).all()
    if not words:
        return []
    hit_ids: list[int] = []
    for error in targets:
        context_lower = error.context.lower()
        for word in words:
            # 词边界前缀匹配：abandon 命中 abandoning/abandoned
            if re.search(rf"\b{re.escape(word.text.lower())}", context_lower):
                card = get_or_create_card(session, user_id, word.id)
                if card.reps > 0 or card.interval_days > 1:
                    card.reps = 0
                    card.interval_days = 1
                card.due_at = datetime.now()
                if word.id not in hit_ids:
                    hit_ids.append(word.id)
    return hit_ids
```

- [ ] **Step 6: 管线接线**

`grader.py` 的 `run_grading` 中，errors 循环后、`mark_writing_learned` 前，把 error 循环改为先收集再联动：
```python
        new_errors = []
        for annotation in result.annotations:
            if annotation.error_type:
                item = ErrorItem(
                    user_id=practice.user_id,
                    practice_id=practice.id,
                    error_type=annotation.error_type,
                    context=annotation.original,
                )
                session.add(item)
                new_errors.append(item)
        from app.services.vocab_link import link_vocab_errors
        link_vocab_errors(session, practice.user_id, new_errors)
```
（延迟 import 避免循环依赖；`speaking_grader.py` 的 `run_speaking_turn` 同样改造。）

- [ ] **Step 7: 测试通过 + 全套回归**

Run: `cd backend && uv run pytest -v`
Expected: 全部通过（38 既有 + 6 新增）

- [ ] **Step 8: Commit**

```bash
git add backend/ && git commit -m "feat: SM-2 复习调度 + 批改错词联动建卡"
```

---

### Task 3: 词汇 API

**Files:**
- Create: `backend/app/api/vocab.py`
- Modify: `backend/app/main.py`（挂 vocab 路由）
- Modify: `backend/app/schemas.py`（加词汇 schema）
- Test: `backend/tests/test_vocab_api.py`

**Interfaces:**
- Consumes: Task 1-2 全部
- Produces（前端 Task 4 严格按此对接）:
  - `GET /api/vocab/topics` → `list[TopicOut]`（`{topic, word_count, mastered_count, due_count}`）
  - `GET /api/vocab/words?topic=教育` → `list[WordOut]`（`{id, text, pos, meaning, paraphrase_chain, example_sentence, due_at: datetime|null, reps: int}`）
  - `GET /api/vocab/review/queue?limit=20` → `ReviewQueueOut`（`{cards: list[ReviewCardOut], due_total: int}`；ReviewCardOut = `{word_id, text, pos, meaning, paraphrase_chain, example_sentence, is_new}`）
  - `POST /api/vocab/review/{word_id}` body `{quality: 1|3|5}` → `{next_due_at: datetime, interval_days: int}`；word 不存在 404，quality 非法 422
  - `GET /api/vocab/forecast` → `list[ForecastOut]`（`{date: str(YYYY-MM-DD), count: int}`，未来 7 天）

- [ ] **Step 1: schemas.py 追加**

```python
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
```

- [ ] **Step 2: 写失败测试**

`backend/tests/test_vocab_api.py`:
```python
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.database import Base, make_session_factory
from app.main import app
from app.models import ReviewCard, User, Word
from app.seed_vocab import seed_vocab_db


@pytest.fixture()
def client(tmp_path, monkeypatch):
    factory = make_session_factory(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(factory.kw["bind"])
    s = factory()
    s.add(User(id=1))
    s.commit()
    seed_vocab_db(s)
    # 造 3 张卡：word1 已掌握、word2 到期、word3 未到期
    s.add(ReviewCard(user_id=1, word_id=1, reps=3, interval_days=15,
                     due_at=datetime.now() + timedelta(days=10)))
    s.add(ReviewCard(user_id=1, word_id=2, reps=1, interval_days=1,
                     due_at=datetime.now() - timedelta(hours=1)))
    s.add(ReviewCard(user_id=1, word_id=3, reps=1, interval_days=6,
                     due_at=datetime.now() + timedelta(days=3)))
    s.commit()
    s.close()
    monkeypatch.setattr(app.state, "session_factory", factory)
    return TestClient(app)


def test_topics_aggregate(client):
    topics = client.get("/api/vocab/topics").json()
    assert len(topics) == 10
    edu = next(t for t in topics if t["topic"] == "教育")
    assert edu["word_count"] == 20
    assert edu["mastered_count"] + edu["due_count"] <= 20
    # 全部话题合计：掌握 1（word1 reps3/interval15）
    assert sum(t["mastered_count"] for t in topics) == 1
    assert sum(t["due_count"] for t in topics) == 1


def test_words_with_review_state(client):
    words = client.get("/api/vocab/words", params={"topic": "教育"}).json()
    assert len(words) == 20
    w1 = next(w for w in words if w["id"] == 1)
    assert w1["reps"] == 3
    assert w1["due_at"] is not None
    assert all(len(w["paraphrase_chain"]) >= 3 for w in words)


def test_review_queue_and_submit(client):
    queue = client.get("/api/vocab/review/queue", params={"limit": 5}).json()
    assert queue["due_total"] == 1
    assert len(queue["cards"]) == 5
    assert queue["cards"][0]["word_id"] == 2  # 到期卡优先
    assert queue["cards"][0]["is_new"] is False
    assert queue["cards"][1]["is_new"] is True

    resp = client.post("/api/vocab/review/2", json={"quality": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["interval_days"] == 6  # reps 1→2

    # 提交后 word2 不再到期
    queue2 = client.get("/api/vocab/review/queue", params={"limit": 5}).json()
    assert queue2["due_total"] == 0

    assert client.post("/api/vocab/review/2", json={"quality": 4}).status_code == 422
    assert client.post("/api/vocab/review/9999", json={"quality": 5}).status_code == 404


def test_forecast(client):
    forecast = client.get("/api/vocab/forecast").json()
    assert len(forecast) == 7
    assert sum(f["count"] for f in forecast) == 2  # word1(+10天不在内) word3(+3天)
    day3 = forecast[3]
    assert day3["count"] == 1
```

- [ ] **Step 3: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_vocab_api.py -v`
Expected: FAIL，404 / ModuleNotFoundError

- [ ] **Step 4: 实现 api/vocab.py**

`backend/app/api/vocab.py`:
```python
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from app.models import ReviewCard, Word
from app.schemas import (ForecastOut, ReviewCardOut, ReviewQueueOut, ReviewSubmit,
                         TopicOut, WordOut)
from app.services.sm2 import build_review_queue, get_or_create_card, sm2_review

router = APIRouter(prefix="/api")

MASTERY_MIN_REPS = 2
MASTERY_MIN_INTERVAL = 7


def get_session(request: Request):
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


@router.get("/vocab/topics", response_model=list[TopicOut])
def list_topics(session=Depends(get_session)):
    words = session.scalars(select(Word)).all()
    cards = {c.word_id: c for c in session.scalars(select(ReviewCard)).all()}
    now = datetime.now()
    agg: dict[str, dict] = defaultdict(lambda: {"word_count": 0, "mastered_count": 0, "due_count": 0})
    for w in words:
        bucket = agg[w.topic]
        bucket["word_count"] += 1
        card = cards.get(w.id)
        if card:
            if card.reps >= MASTERY_MIN_REPS and card.interval_days >= MASTERY_MIN_INTERVAL:
                bucket["mastered_count"] += 1
            if card.due_at and card.due_at <= now:
                bucket["due_count"] += 1
    return [TopicOut(topic=t, **v) for t, v in sorted(agg.items())]


@router.get("/vocab/words", response_model=list[WordOut])
def list_words(topic: str, session=Depends(get_session)):
    words = session.scalars(
        select(Word).where(Word.topic == topic).order_by(Word.id)).all()
    cards = {c.word_id: c for c in session.scalars(select(ReviewCard)).all()}
    result = []
    for w in words:
        card = cards.get(w.id)
        result.append(WordOut(
            id=w.id, text=w.text, pos=w.pos, meaning=w.meaning,
            paraphrase_chain=w.paraphrase_chain, example_sentence=w.example_sentence,
            due_at=card.due_at if card else None,
            reps=card.reps if card else 0,
        ))
    return result


@router.get("/vocab/review/queue", response_model=ReviewQueueOut)
def review_queue(limit: int = 20, session=Depends(get_session)):
    cards, due_total = build_review_queue(session, 1, limit=limit)
    return ReviewQueueOut(cards=[ReviewCardOut(**c) for c in cards], due_total=due_total)


@router.post("/vocab/review/{word_id}")
def submit_review(word_id: int, payload: ReviewSubmit, session=Depends(get_session)):
    word = session.get(Word, word_id)
    if word is None:
        raise HTTPException(status_code=404, detail="单词不存在")
    card = get_or_create_card(session, 1, word_id)
    sm2_review(card, payload.quality, datetime.now())
    session.commit()
    return {"next_due_at": card.due_at, "interval_days": card.interval_days}


@router.get("/vocab/forecast", response_model=list[ForecastOut])
def forecast(session=Depends(get_session)):
    now = datetime.now()
    today = now.date()
    cards = session.scalars(select(ReviewCard).where(ReviewCard.due_at.isnot(None))).all()
    counts: dict[str, int] = defaultdict(int)
    for card in cards:
        if card.due_at <= now:  # 今天到期（含逾期）计入今天
            counts[today.isoformat()] += 1
        else:
            day = card.due_at.date()
            if day <= today + timedelta(days=6):
                counts[day.isoformat()] += 1
    return [ForecastOut(date=(today + timedelta(days=i)).isoformat(),
                        count=counts.get((today + timedelta(days=i)).isoformat(), 0))
            for i in range(7)]
```

- [ ] **Step 5: main.py 挂路由**

加 `from app.api.vocab import router as vocab_router`，并在现有 include_router 后加 `app.include_router(vocab_router)`。

- [ ] **Step 6: 测试通过 + 全套回归**

Run: `cd backend && uv run pytest -v`
Expected: 全部通过（44 既有 + 4 新增）

- [ ] **Step 7: Commit**

```bash
git add backend/ && git commit -m "feat: 词汇 API（话题聚合/复习队列/SM-2 提交/到期预测）"
```

---

### Task 4: 前端词汇页 + 复习会话

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/client.ts`
- Create: `frontend/src/pages/VocabPage.tsx`（话题浏览 + 词卡列表 + 内嵌复习会话 + 到期分布图）
- Modify: `frontend/src/App.tsx`（`/vocab` 路由）
- Modify: `frontend/src/components/NavBar.tsx`（加"词汇"链接）
- Modify: `frontend/src/pages/DashboardPage.tsx`（词汇掌握率卡 + 横幅更新）

**Interfaces:**
- Consumes: Task 3 API 契约；`useEcharts`（V1）
- Produces: 无下游（最后的前端任务）

- [ ] **Step 1: types.ts / client.ts 追加**

types.ts:
```ts
export interface TopicOut {
  topic: string
  word_count: number
  mastered_count: number
  due_count: number
}

export interface WordOut {
  id: number
  text: string
  pos: string
  meaning: string
  paraphrase_chain: string[]
  example_sentence: string
  due_at: string | null
  reps: number
}

export interface ReviewCardOut {
  word_id: number
  text: string
  pos: string
  meaning: string
  paraphrase_chain: string[]
  example_sentence: string
  is_new: boolean
}

export interface ForecastOut {
  date: string
  count: number
}
```

client.ts:
```ts
export function listVocabTopics(): Promise<TopicOut[]> {
  return request('/vocab/topics')
}

export function listVocabWords(topic: string): Promise<WordOut[]> {
  return request(`/vocab/words?topic=${encodeURIComponent(topic)}`)
}

export function getReviewQueue(limit = 20): Promise<{ cards: ReviewCardOut[]; due_total: number }> {
  return request(`/vocab/review/queue?limit=${limit}`)
}

export function submitReview(wordId: number, quality: 1 | 3 | 5): Promise<{ next_due_at: string; interval_days: number }> {
  return request(`/vocab/review/${wordId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ quality }),
  })
}

export function getVocabForecast(): Promise<ForecastOut[]> {
  return request('/vocab/forecast')
}
```

（import 类型列表相应加 `TopicOut, WordOut, ReviewCardOut, ForecastOut`。）

- [ ] **Step 2: VocabPage**

`frontend/src/pages/VocabPage.tsx`:
```tsx
import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  getReviewQueue, getVocabForecast, listVocabTopics, listVocabWords, submitReview,
} from '../api/client'
import type { ForecastOut, ReviewCardOut, TopicOut, WordOut } from '../api/types'
import { useEcharts } from '../hooks/useEcharts'

export default function VocabPage() {
  const [topics, setTopics] = useState<TopicOut[]>([])
  const [selected, setSelected] = useState('')
  const [words, setWords] = useState<WordOut[]>([])
  const [reviewing, setReviewing] = useState(false)
  const [queue, setQueue] = useState<ReviewCardOut[]>([])
  const [dueTotal, setDueTotal] = useState(0)
  const [error, setError] = useState('')

  useEffect(() => {
    listVocabTopics().then((t) => {
      setTopics(t)
      if (t.length && !selected) setSelected(t[0].topic)
    }).catch((e) => setError(String(e)))
    getReviewQueue().then((q) => setDueTotal(q.due_total)).catch(() => undefined)
  }, [])

  useEffect(() => {
    if (!selected) return
    listVocabWords(selected).then(setWords).catch((e) => setError(String(e)))
  }, [selected])

  const startReview = async () => {
    const q = await getReviewQueue(20)
    if (q.cards.length === 0) {
      setError('词库已全部安排复习，暂无到期卡片')
      return
    }
    setQueue(q.cards)
    setReviewing(true)
  }

  if (reviewing) {
    return (
      <ReviewSession
        initialQueue={queue}
        onFinish={() => {
          setReviewing(false)
          listVocabTopics().then(setTopics)
          getReviewQueue().then((q) => setDueTotal(q.due_total))
        }}
      />
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex flex-wrap gap-2">
          {topics.map((t) => (
            <button
              key={t.topic}
              onClick={() => setSelected(t.topic)}
              className={`rounded-lg px-3 py-1.5 text-sm ${
                selected === t.topic
                  ? 'bg-indigo-600 text-white'
                  : 'bg-white border border-slate-200 text-slate-600'
              }`}
            >
              {t.topic}
              <span className="ml-1 text-xs opacity-70">
                {t.mastered_count}/{t.word_count}
                {t.due_count > 0 && ` · ${t.due_count} 待复习`}
              </span>
            </button>
          ))}
        </div>
        <button
          onClick={startReview}
          className={`rounded-xl px-5 py-2 font-semibold text-white ${
            dueTotal > 0 ? 'bg-amber-500' : 'bg-indigo-600'
          }`}
        >
          开始复习{dueTotal > 0 ? `（${dueTotal} 到期）` : ''}
        </button>
      </div>
      {error && <div className="text-sm text-red-500">{error}</div>}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {words.map((w) => (
          <div key={w.id} className="rounded-xl border border-slate-200 bg-white p-4">
            <div className="flex items-baseline gap-2">
              <span className="text-lg font-bold text-slate-800">{w.text}</span>
              <span className="text-xs text-slate-400">{w.pos}</span>
              {w.reps > 0 && (
                <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-xs text-emerald-700">
                  已复习 {w.reps} 次
                </span>
              )}
            </div>
            <div className="mt-0.5 text-sm text-slate-600">{w.meaning}</div>
            <div className="mt-1 text-xs italic text-slate-400">{w.example_sentence}</div>
            <div className="mt-2 flex flex-wrap gap-1">
              {w.paraphrase_chain.map((p) => (
                <span
                  key={p}
                  title={p}
                  className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs text-indigo-600"
                >
                  {p}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function ReviewSession({ initialQueue, onFinish }: {
  initialQueue: ReviewCardOut[]
  onFinish: () => void
}) {
  const [queue, setQueue] = useState(initialQueue)
  const [flipped, setFlipped] = useState(false)
  const [doneCount, setDoneCount] = useState(0)
  const [forecast, setForecast] = useState<ForecastOut[]>([])

  const current = queue[0]

  // 队列走完（完成页挂载）时拉取到期分布
  useEffect(() => {
    if (queue.length === 0) {
      getVocabForecast().then(setForecast).catch(() => undefined)
    }
  }, [queue.length])

  const rate = async (quality: 1 | 3 | 5) => {
    if (!current) return
    await submitReview(current.word_id, quality)
    setDoneCount((n) => n + 1)
    setQueue((q) => q.slice(1))
    setFlipped(false)
  }

  const chartRef = useEcharts({
    xAxis: { type: 'category', data: forecast.map((f) => f.date.slice(5)) },
    yAxis: { type: 'value', minInterval: 1 },
    series: [{ type: 'bar', data: forecast.map((f) => f.count), itemStyle: { color: '#4f46e5' } }],
    tooltip: {},
  })

  if (!current) {
    return (
      <div className="space-y-4">
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-8 text-center">
          <div className="text-2xl font-bold text-emerald-700">本轮完成！</div>
          <div className="mt-1 text-sm text-slate-500">共复习 {doneCount} 张卡片</div>
        </div>
        {forecast.length > 0 && (
          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <div className="mb-2 text-sm font-semibold">未来 7 天到期分布</div>
            <div ref={chartRef} className="h-48 w-full" />
          </div>
        )}
        <button onClick={onFinish}
          className="w-full rounded-xl bg-indigo-600 py-3 font-semibold text-white">
          返回词库
        </button>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-xl space-y-4">
      <div className="text-center text-sm text-slate-400">
        第 {doneCount + 1} / {doneCount + queue.length} 张
        {current.is_new && <span className="ml-2 rounded bg-sky-100 px-2 py-0.5 text-xs text-sky-700">新词</span>}
      </div>
      <AnimatePresence mode="wait">
        <motion.div
          key={current.word_id + String(flipped)}
          initial={{ rotateY: 90, opacity: 0 }}
          animate={{ rotateY: 0, opacity: 1 }}
          exit={{ rotateY: -90, opacity: 0 }}
          transition={{ duration: 0.2 }}
          onClick={() => setFlipped(!flipped)}
          className="cursor-pointer rounded-2xl border border-slate-200 bg-white p-10 text-center shadow-sm"
        >
          {!flipped ? (
            <>
              <div className="text-3xl font-bold text-slate-800">{current.text}</div>
              <div className="mt-1 text-sm text-slate-400">{current.pos}</div>
              <div className="mt-6 text-xs text-slate-300">点击卡片查看释义</div>
            </>
          ) : (
            <div className="space-y-3 text-left">
              <div className="text-center">
                <span className="text-2xl font-bold">{current.text}</span>
                <span className="ml-2 text-sm text-slate-400">{current.pos}</span>
              </div>
              <div className="text-slate-700">{current.meaning}</div>
              <div className="text-sm italic text-slate-500">{current.example_sentence}</div>
              <div className="flex flex-wrap gap-1">
                {current.paraphrase_chain.map((p) => (
                  <span key={p}
                    className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs text-indigo-600">
                    {p}
                  </span>
                ))}
              </div>
            </div>
          )}
        </motion.div>
      </AnimatePresence>
      {flipped && (
        <div className="grid grid-cols-3 gap-3">
          <button onClick={() => rate(1)}
            className="rounded-xl bg-red-500 py-3 font-semibold text-white">不认识</button>
          <button onClick={() => rate(3)}
            className="rounded-xl bg-amber-500 py-3 font-semibold text-white">模糊</button>
          <button onClick={() => rate(5)}
            className="rounded-xl bg-emerald-600 py-3 font-semibold text-white">认识</button>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: 路由/导航/仪表盘**

- `App.tsx`：加 `import VocabPage from './pages/VocabPage'` 与 `<Route path="/vocab" element={<VocabPage />} />`
- `NavBar.tsx` links 加 `{ to: '/vocab', label: '词汇' }`
- `DashboardPage.tsx`：
  - 顶部 import 加 `listVocabTopics`，state 加 `const [vocab, setVocab] = useState({ mastered: 0, total: 0, due: 0 })`，effect 里追加：
    ```ts
    listVocabTopics().then((topics) => setVocab({
      mastered: topics.reduce((n, t) => n + t.mastered_count, 0),
      total: topics.reduce((n, t) => n + t.word_count, 0),
      due: topics.reduce((n, t) => n + t.due_count, 0),
    })).catch(() => undefined)
    ```
  - 口语卡后再加一张词汇卡：标题"词汇掌握"，主数字 `{vocab.mastered}/{vocab.total}`，副文本 `{vocab.due > 0 ? `${vocab.due} 词今日到期` : '今日无到期'}`，链接 `/vocab`「去复习 →」
  - 横幅改为"能力树、听力模块将在 V4 解锁"

- [ ] **Step 4: 构建验证**

Run: `cd frontend && npm run build`（Node v22，unset 代理）
Expected: 通过

- [ ] **Step 5: Commit**

```bash
git add frontend/ && git commit -m "feat: 词汇页 + 复习会话（翻卡三档自评）+ 仪表盘掌握率"
```

---

### Task 5: 扩充脚本 + e2e + 文档 + 推送

**Files:**
- Create: `backend/scripts/generate_vocab.py`
- Modify: `backend/.env.example`（无需改——复用 DEEPSEEK_API_KEY；若无变化则跳过此文件）
- Modify: `README.md`

- [ ] **Step 1: 扩充脚本**

`backend/scripts/generate_vocab.py`（有 DeepSeek key 时为新词批量补例句/替换链；本任务只需保证 `--dry-run` 可运行，不发真实调用）:
```python
"""词库扩充脚本：为 word 表中缺失例句或替换链的词批量生成内容（DeepSeek）。

用法（在 backend/ 下）：
    uv run python scripts/generate_vocab.py --dry-run   # 只列出待处理词，不调 API
    uv run python scripts/generate_vocab.py             # 真实生成并入库
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openai import OpenAI

from app.config import settings
from app.database import make_session_factory
from app.models import Word

PROMPT = """为雅思核心词 "{word}"（{pos}，话题：{topic}）生成学习材料，只输出 JSON：
{{"meaning": "1-2个核心中文释义", "paraphrase_chain": ["3-5个由口语到书面递进的同义替换"],
  "example_sentence": "一句10-20词的雅思Task 2风格真题语境例句（须自然使用目标词）"}}"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    factory = make_session_factory(settings.database_url)
    session = factory()
    try:
        from sqlalchemy import select
        # JSON 列不支持与 [] 直接比较（SQLite 下不可靠），在 Python 侧过滤
        incomplete = [w for w in session.scalars(select(Word)).all()
                      if not w.example_sentence or not w.paraphrase_chain]
        print(f"待补全词条: {len(incomplete)}")
        if args.dry_run:
            for w in incomplete:
                print(f"  - {w.text} ({w.topic})")
            return
        if not settings.deepseek_api_key:
            print("未配置 DEEPSEEK_API_KEY，退出")
            sys.exit(1)
        client = OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url)
        for w in incomplete:
            resp = client.chat.completions.create(
                model=settings.deepseek_model,
                messages=[{"role": "user", "content": PROMPT.format(
                    word=w.text, pos=w.pos, topic=w.topic)}],
                response_format={"type": "json_object"}, temperature=0.3, max_tokens=512)
            data = json.loads(resp.choices[0].message.content)
            w.meaning = w.meaning or data.get("meaning", "")
            w.paraphrase_chain = w.paraphrase_chain or data.get("paraphrase_chain", [])
            w.example_sentence = w.example_sentence or data.get("example_sentence", "")
            session.commit()
            print(f"  ✓ {w.text}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
```

验证：`cd backend && uv run python scripts/generate_vocab.py --dry-run`（种子词库完整时应输出"待补全词条: 0"）。

- [ ] **Step 2: 全量测试 + 构建**

```bash
cd backend && uv run pytest -v
cd ../frontend && npm run build
```

- [ ] **Step 3: e2e（端口 8022，mock 环境变量全 unset）**

```bash
cd backend && env -u DEEPSEEK_API_KEY -u IFLYTEK_APP_ID -u IFLYTEK_API_SECRET \
  uv run uvicorn app.main:app --port 8022
```
```bash
curl localhost:8022/api/vocab/topics
curl "localhost:8022/api/vocab/words?topic=教育"
curl "localhost:8022/api/vocab/review/queue?limit=3"
curl -X POST localhost:8022/api/vocab/review/1 -H 'Content-Type: application/json' -d '{"quality": 5}'
curl localhost:8022/api/vocab/forecast
```
Expected: topics 10 个各 20 词；queue 含新词；提交返回 interval_days=1；forecast 7 天计数随提交变化。再验证错词联动：提交一篇含 "abandon" 词汇搭配错误的作文（mock grader 的示例批注含"词汇搭配"类，其 original 句含示例句词汇——检查 error 联动日志或查 review_card 表确认命中词建卡）。

- [ ] **Step 4: README 更新**

在「口语模块（V2）」节后加：
```markdown
## 词汇模块（V3）

- 入口：`/vocab`，10 个雅思话题 × 20 核心词（释义 / 真题风格例句 / 同义替换链）
- 复习采用 SM-2 间隔重复：认识 / 模糊 / 不认识三档自评自动调度下次复习
- 写作、口语批改中的「词汇搭配」错误命中词库时会自动建复习卡（错词强制复现）
- 扩充词库：配好 DEEPSEEK_API_KEY 后运行 `cd backend && uv run python scripts/generate_vocab.py`
```

- [ ] **Step 5: Commit + push**

```bash
git add -A && git commit -m "docs: README 更新 + 词库扩充脚本，V3 完成" && git push
```

- [ ] **Step 6: 收尾核对（对照规格 §1 成功标准）**

- 话题浏览（词 + 释义 + 例句 + 替换链）✓
- 复习会话三档自评 + SM-2 调度 ✓
- 词汇搭配错误命中词库自动建卡 ✓
- 仪表盘掌握率 ✓
