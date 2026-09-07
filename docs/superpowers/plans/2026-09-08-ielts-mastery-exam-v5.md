# 雅思 V5 能力树点亮 + 全真模考 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现"掌握即通过"体系——能力树三态可视化与绿态规则引擎、四模块通关判定、全真模考（四步向导 + 预测总分 + 薄弱点报告）、仪表盘预测分。

**Architecture:** 规则引擎读既有 practice/ai_feedback/error_item/review_card 数据判定 skill_mastery 绿态；mock_exam 表启用（加 practice_ids 列）；模考四步复用 V1-V4 练习 API，后端只负责汇总计算。无新外部依赖。

**Tech Stack:** 同 V1-V4。

**上游规格:** `docs/superpowers/specs/2026-09-08-ielts-mastery-exam-v5-design.md`

## Global Constraints

- 沿用 V1-V4 全部约束（uv/pytest/tmp SQLite/中文 Conventional Commits/8022 冒烟/unset 代理/Node v22/测试 monkeypatch 掉外部 key）
- 绿态规则四类型：`no_error_type` / `band_avg` / `listening_accuracy` / `vocab_mastery_rate`；聚合节点绿 = 全部直接子节点绿
- 掌握判定（词汇）：reps>=2 且 interval_days>=7（与 V3 一致）
- 通关判定对照规格 §2 表格（写作/口语/听力/词汇四条）
- 分数换算表与官方取整规则（.25 进 .5、.75 进下一整分）必须精确实现
- 模考解锁条件：所有能力节点至少 learned（变黄）

---

### Task 1: 规则引擎 + 规则种子

**Files:**
- Create: `backend/app/seed_rules.py`
- Create: `backend/app/services/mastery_rules.py`
- Modify: `backend/app/main.py`（startup 加 seed_mastery_rules）
- Test: `backend/tests/test_mastery_rules.py`

**Interfaces:**
- Consumes: `SkillNode / SkillMastery / Practice / AIFeedback / ErrorItem / ReviewCard / Word`
- Produces:
  - `RULES: dict[str, dict]`（`app.seed_rules`，叶节点 code → criteria 规则 dict）
  - `seed_mastery_rules(session)`（幂等：按 code 更新 criteria 字段）
  - `evaluate_node(node: SkillNode, session, user_id: int) -> bool`（`app.services.mastery_rules`）
  - `evaluate_all(session, user_id: int) -> int`（learned → verified 的节点数；未 learned 不直接跳绿）

- [ ] **Step 1: 写失败测试**

`backend/tests/test_mastery_rules.py`:
```python
from datetime import datetime

from sqlalchemy import select

from app.database import Base, make_session_factory
from app.models import (AIFeedback, ErrorItem, Practice, ReviewCard, SkillMastery,
                        SkillNode, User, Word)
from app.seed_rules import RULES, seed_mastery_rules
from app.services.mastery_rules import evaluate_all, evaluate_node


def make_db(tmp_path):
    from app.seed import seed_db
    from app.seed_listening import seed_listening_db
    from app.seed_speaking import seed_speaking_db

    factory = make_session_factory(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(factory.kw["bind"])
    s = factory()
    seed_db(s)            # 写作能力树节点（RULES 依赖这些 code）
    seed_speaking_db(s)   # 口语节点 + 话题卡
    seed_listening_db(s)  # 听力节点
    s.close()
    return factory


def add_practice(s, pid, module, bands):
    s.add(Practice(id=pid, user_id=1, module=module, prompt_title="t", prompt_text="p",
                   content="c", status="done", total_band=bands.get("overall")))
    s.add(AIFeedback(practice_id=pid, bands=bands, annotations=[], rewrite="", model="m"))
    s.flush()


def test_no_error_type_rule(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    s.add(User(id=1))
    seed_mastery_rules(s)
    node = s.scalars(select(SkillNode).where(
        SkillNode.code == "writing.task2.gra.agreement")).one()
    assert node.criteria["rule"] == "no_error_type"

    # 无练习 → False
    assert evaluate_node(node, s, 1) is False
    # 5 篇写作，其中 1 篇有主谓一致错误 → False
    for i in range(5):
        add_practice(s, 10 + i, "writing", {"overall": 6.5, "grammar": 6.5})
    s.add(ErrorItem(user_id=1, practice_id=10, error_type="主谓一致", context="x"))
    s.commit()
    assert evaluate_node(node, s, 1) is False
    # 再来 5 篇干净写作（窗口滑动后）→ True
    for i in range(5):
        add_practice(s, 20 + i, "writing", {"overall": 6.5, "grammar": 6.5})
    s.commit()
    assert evaluate_node(node, s, 1) is True
    s.close()


def test_band_avg_rule(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    s.add(User(id=1))
    seed_mastery_rules(s)
    node = s.scalars(select(SkillNode).where(
        SkillNode.code == "writing.task2.tr.identify")).one()
    assert node.criteria["rule"] == "band_avg"
    for i, score in enumerate([6.5, 6.5, 6.0]):
        add_practice(s, i + 1, "writing",
                     {"overall": 6.5, "task_response": score})
    s.commit()
    assert evaluate_node(node, s, 1) is False  # 均分 6.33 < 6.5
    add_practice(s, 9, "writing", {"overall": 7.0, "task_response": 7.0})
    s.commit()
    # 最近 3 篇 = 6.5, 6.0, 7.0 → 均分 6.5
    assert evaluate_node(node, s, 1) is True
    s.close()


def test_aggregate_node_green_when_all_children_green(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    s.add(User(id=1))
    seed_mastery_rules(s)
    parent = s.scalars(select(SkillNode).where(SkillNode.code == "writing.task2.tr")).one()
    child = s.scalars(select(SkillNode).where(
        SkillNode.code == "writing.task2.tr.identify")).one()
    # 伪造：三个子节点全 verified
    for code in ["writing.task2.tr.identify", "writing.task2.tr.position", "writing.task2.tr.cover"]:
        n = s.scalars(select(SkillNode).where(SkillNode.code == code)).one()
        s.add(SkillMastery(user_id=1, node_id=n.id, status="verified"))
    s.commit()
    assert evaluate_node(parent, s, 1) is True
    assert evaluate_node(child, s, 1) is True  # 已 verified 保持绿
    s.close()


def test_evaluate_all_only_promotes_learned(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    s.add(User(id=1))
    seed_mastery_rules(s)
    # 一个 learned 节点（条件满足）+ 一个 unseen 节点（条件也满足但不应跳绿）
    ok_node = s.scalars(select(SkillNode).where(
        SkillNode.code == "writing.task2.gra.agreement")).one()
    s.add(SkillMastery(user_id=1, node_id=ok_node.id, status="learned"))
    for i in range(5):
        add_practice(s, i + 1, "writing", {"overall": 7.0, "grammar": 7.0})
    s.commit()
    updated = evaluate_all(s, 1)
    s.commit()
    assert updated == 1
    m = s.scalars(select(SkillMastery).where(SkillMastery.node_id == ok_node.id)).one()
    assert m.status == "verified"
    s.close()
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_mastery_rules.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.seed_rules'`

- [ ] **Step 3: 实现 seed_rules.py**

`backend/app/seed_rules.py`（叶节点精确映射；窗口默认写作/口语 5 篇、听力 3 篇）:
```python
from sqlalchemy import select

from app.models import SkillNode

_W = {"window": 5, "module": "writing"}
_S = {"window": 5, "module": "speaking"}

RULES: dict[str, dict] = {
    # 写作 TR/CC 由对应子分驱动
    "writing.task2.tr.identify": {"rule": "band_avg", "band": "task_response", "min": 6.5, **_W},
    "writing.task2.tr.position": {"rule": "band_avg", "band": "task_response", "min": 6.5, **_W},
    "writing.task2.tr.cover": {"rule": "band_avg", "band": "task_response", "min": 6.5, **_W},
    "writing.task2.cc.frame": {"rule": "band_avg", "band": "coherence", "min": 6.5, **_W},
    "writing.task2.cc.paragraphing": {"rule": "band_avg", "band": "coherence", "min": 6.5, **_W},
    "writing.task2.cc.linkers": {"rule": "no_error_type", "error_type": "连接词", **_W},
    "writing.task2.cc.reference": {"rule": "band_avg", "band": "coherence", "min": 6.5, **_W},
    "writing.task2.lr.paraphrase": {"rule": "band_avg", "band": "lexical", "min": 6.5, **_W},
    "writing.task2.lr.collocation": {"rule": "no_error_type", "error_type": "词汇搭配", **_W},
    "writing.task2.lr.academic": {"rule": "band_avg", "band": "lexical", "min": 6.5, **_W},
    "writing.task2.lr.spelling": {"rule": "no_error_type", "error_type": "拼写", **_W},
    "writing.task2.gra.complex": {"rule": "band_avg", "band": "grammar", "min": 6.5, **_W},
    "writing.task2.gra.agreement": {"rule": "no_error_type", "error_type": "主谓一致", **_W},
    "writing.task2.gra.tense": {"rule": "no_error_type", "error_type": "时态", **_W},
    "writing.task2.gra.article": {"rule": "no_error_type", "error_type": "冠词", **_W},
    # 口语
    "speaking.fc.length": {"rule": "band_avg", "band": "fluency", "min": 6.5, **_S},
    "speaking.fc.hesitation": {"rule": "no_error_type", "error_type": "自我重复", **_S},
    "speaking.fc.connectives": {"rule": "band_avg", "band": "fluency", "min": 6.5, **_S},
    "speaking.lr.idiom": {"rule": "band_avg", "band": "lexical", "min": 6.5, **_S},
    "speaking.lr.paraphrase": {"rule": "band_avg", "band": "lexical", "min": 6.5, **_S},
    "speaking.lr.topic": {"rule": "no_error_type", "error_type": "词汇搭配", **_S},
    "speaking.gra.complex": {"rule": "band_avg", "band": "grammar", "min": 6.5, **_S},
    "speaking.gra.tense": {"rule": "no_error_type", "error_type": "时态", **_S},
    "speaking.gra.agreement": {"rule": "no_error_type", "error_type": "主谓一致", **_S},
    "speaking.pr.intelligibility": {"rule": "band_avg", "band": "pronunciation", "min": 6.0, **_S},
    "speaking.pr.intonation": {"rule": "band_avg", "band": "pronunciation", "min": 6.0, **_S},
    "speaking.p1.direct": {"rule": "band_avg", "band": "overall", "min": 6.5, **_S},
    "speaking.p2.structure": {"rule": "band_avg", "band": "overall", "min": 6.5, **_S},
    "speaking.p3.depth": {"rule": "band_avg", "band": "overall", "min": 6.5, **_S},
    # 听力
    "listening.dictation.liaison": {"rule": "listening_accuracy", "min": 90, "window": 3,
                                    "error_type": "听力:连读", "max_ratio": 0.2},
    "listening.dictation.numbers": {"rule": "listening_accuracy", "min": 90, "window": 3,
                                    "error_type": "听力:词汇", "max_ratio": 0.5},
    "listening.dictation.spelling": {"rule": "listening_accuracy", "min": 85, "window": 3},
    "listening.shadowing.fluency": {"rule": "listening_accuracy", "min": 85, "window": 3},
    "listening.shadowing.completeness": {"rule": "listening_accuracy", "min": 90, "window": 3},
    "listening.vocab.academic": {"rule": "listening_accuracy", "min": 80, "window": 3},
    "listening.vocab.paraphrase": {"rule": "listening_accuracy", "min": 80, "window": 3},
    "listening.attention.sustain": {"rule": "listening_accuracy", "min": 80, "window": 3},
    # 词汇（模块级规则，挂到词汇掌握率）
}


def seed_mastery_rules(session) -> None:
    """幂等：按 code 把 RULES 写入对应节点的 criteria 字段。"""
    nodes = session.scalars(select(SkillNode)).all()
    by_code = {n.code: n for n in nodes}
    changed = False
    for code, criteria in RULES.items():
        node = by_code.get(code)
        if node is not None and node.criteria != criteria:
            node.criteria = criteria
            changed = True
    if changed:
        session.commit()
```

- [ ] **Step 4: 实现 mastery_rules.py**

`backend/app/services/mastery_rules.py`:
```python
from datetime import datetime, timedelta

from sqlalchemy import select

from app.models import (AIFeedback, ErrorItem, Practice, ReviewCard, SkillMastery,
                        SkillNode)

VOCAB_MASTER_MIN_REPS = 2
VOCAB_MASTER_MIN_INTERVAL = 7


def _recent_practices(session, user_id: int, module: str, window: int) -> list[Practice]:
    return session.scalars(
        select(Practice)
        .where(Practice.user_id == user_id, Practice.module == module,
               Practice.status == "done")
        .order_by(Practice.created_at.desc())
        .limit(window)).all()


def _rule_no_error_type(session, user_id: int, criteria: dict) -> bool:
    practices = _recent_practices(session, user_id, criteria["module"], criteria["window"])
    if len(practices) < criteria["window"]:
        return False
    pids = [p.id for p in practices]
    hit = session.scalars(
        select(ErrorItem.id).where(
            ErrorItem.practice_id.in_(pids),
            ErrorItem.error_type == criteria["error_type"])).first()
    return hit is None


def _rule_band_avg(session, user_id: int, criteria: dict) -> bool:
    practices = _recent_practices(session, user_id, criteria["module"], criteria["window"])
    if len(practices) < criteria["window"]:
        return False
    scores = []
    for p in practices:
        if not p.feedback:
            return False
        value = p.feedback.bands.get(criteria["band"])
        if value is None:
            return False
        scores.append(value)
    return sum(scores) / len(scores) >= criteria["min"]


def _rule_listening_accuracy(session, user_id: int, criteria: dict) -> bool:
    practices = _recent_practices(session, user_id, "listening", criteria["window"])
    if len(practices) < criteria["window"]:
        return False
    if any((p.total_band or 0) < criteria["min"] for p in practices):
        return False
    error_type = criteria.get("error_type")
    max_ratio = criteria.get("max_ratio")
    if error_type and max_ratio is not None:
        pids = [p.id for p in practices]
        all_errors = session.scalars(
            select(ErrorItem).where(ErrorItem.practice_id.in_(pids))).all()
        if all_errors:
            typed = [e for e in all_errors if e.error_type == error_type]
            if len(typed) / len(all_errors) > max_ratio:
                return False
    return True


def _rule_vocab_mastery_rate(session, user_id: int, criteria: dict) -> bool:
    total = len(session.scalars(select(Word.id)).all())
    if total == 0:
        return False
    mastered = len(session.scalars(
        select(ReviewCard.id).where(
            ReviewCard.user_id == user_id,
            ReviewCard.reps >= VOCAB_MASTER_MIN_REPS,
            ReviewCard.interval_days >= VOCAB_MASTER_MIN_INTERVAL)).all())
    return mastered / total >= criteria["min"]


def evaluate_node(node: SkillNode, session, user_id: int) -> bool:
    """聚合节点绿 = 全部直接子节点绿；叶节点按 criteria 规则。"""
    children = session.scalars(
        select(SkillNode).where(SkillNode.parent_id == node.id)).all()
    if children:
        for child in children:
            m = session.scalars(select(SkillMastery).where(
                SkillMastery.user_id == user_id,
                SkillMastery.node_id == child.id)).first()
            child_green = (m and m.status == "verified") or evaluate_node(child, session, user_id)
            if not child_green:
                return False
        return True
    # 已 verified 的叶节点保持绿
    m = session.scalars(select(SkillMastery).where(
        SkillMastery.user_id == user_id, SkillMastery.node_id == node.id)).first()
    if m and m.status == "verified":
        return True
    criteria = node.criteria or {}
    rule = criteria.get("rule")
    if rule == "no_error_type":
        return _rule_no_error_type(session, user_id, criteria)
    if rule == "band_avg":
        return _rule_band_avg(session, user_id, criteria)
    if rule == "listening_accuracy":
        return _rule_listening_accuracy(session, user_id, criteria)
    if rule == "vocab_mastery_rate":
        return _rule_vocab_mastery_rate(session, user_id, criteria)
    return False


def evaluate_all(session, user_id: int) -> int:
    """把所有 learned 节点中满足规则的提升为 verified。返回提升数。"""
    updated = 0
    masteries = session.scalars(
        select(SkillMastery).where(SkillMastery.user_id == user_id,
                                   SkillMastery.status == "learned")).all()
    for m in masteries:
        node = session.get(SkillNode, m.node_id)
        if node and evaluate_node(node, session, user_id):
            m.status = "verified"
            m.evidence = {**(m.evidence or {}), "verified_at": datetime.now().isoformat()}
            updated += 1
    session.commit()
    return updated
```

注意：models import 需要 `Word`（vocab 规则用）——`from app.models import ... Word`。

- [ ] **Step 5: main.py 接线**

`init_db` 末尾（seed_listening_db 之后）加：
```python
        from app.seed_rules import seed_mastery_rules
        seed_mastery_rules(session)
```

- [ ] **Step 6: 测试通过 + 全套回归**

Run: `cd backend && uv run pytest -v`
Expected: 全部通过（57 既有 + 4 新增）


- [ ] **Step 7: Commit**

```bash
git add backend/ && git commit -m "feat: 能力树绿态规则引擎 + 规则种子"
```

---

### Task 2: 模块通关判定 + 分数换算 + skills API

**Files:**
- Create: `backend/app/services/module_clearance.py`
- Create: `backend/app/services/exam_scoring.py`
- Create: `backend/app/api/skills.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/main.py`（挂 skills 路由）
- Test: `backend/tests/test_clearance.py`、`backend/tests/test_skills_api.py`

**Interfaces:**
- Produces:
  - `clearance_summary(session, user_id) -> list[dict]`：`[{module, cleared, detail, mastery_rate}]`（module ∈ writing/speaking/listening/vocab）
  - `accuracy_to_band(acc: int) -> float`、`vocab_rate_to_band(rate: float) -> float`、`overall_round(avg: float) -> float`（`app.services.exam_scoring`）
  - `GET /api/skills/tree` → `list[ModuleTree]`（`{module, nodes: [{id, code, title, parent_id, status, sort_order}]}`，status 实时评估：verified 直接绿，否则调 evaluate_node 给前端"可点亮"提示字段 `can_verify: bool`）
  - `POST /api/skills/evaluate` → `{updated: int}`
  - `GET /api/skills/clearance` → `list[ClearanceOut]`
  - `GET /api/skills/exam-eligibility` → `{eligible: bool, missing: dict[str, int]}`（各模块未变黄节点数）
  - `GET /api/skills/target` → `{target_band: float}`；`PUT /api/skills/target` body `{target_band: float}`（仅接受 6.0/6.5/7.0/7.5，否则 422）

- [ ] **Step 1: 写失败测试 test_clearance.py**

```python
from datetime import datetime

from app.database import Base, make_session_factory
from app.models import (AIFeedback, ErrorItem, Practice, ReviewCard, SkillMastery,
                        SkillNode, User, Word)
from app.services.module_clearance import clearance_summary


def make_db(tmp_path):
    factory = make_session_factory(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(factory.kw["bind"])
    s = factory()
    s.add(User(id=1))
    s.commit()
    s.close()
    return factory


def add_essays(s, bands_list, start_id=100):
    for i, bands in enumerate(bands_list):
        pid = start_id + i
        s.add(Practice(id=pid, user_id=1, module="writing", prompt_title="t",
                       prompt_text="p", content="c", status="done",
                       total_band=bands["overall"]))
        s.add(AIFeedback(practice_id=pid, bands=bands, annotations=[],
                         rewrite="", model="m"))
    s.commit()


def test_writing_clearance(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    good = {"overall": 7.0, "task_response": 7.0, "coherence": 7.0,
            "lexical": 6.5, "grammar": 6.5}
    add_essays(s, [good] * 5)
    summary = {m["module"]: m for m in clearance_summary(s, 1)}
    assert summary["writing"]["cleared"] is True
    assert summary["vocab"]["cleared"] is False  # 无复习记录
    assert summary["listening"]["cleared"] is False

    # 一篇子分低于 6.0 → 不通过
    bad = {"overall": 6.5, "task_response": 6.5, "coherence": 6.5,
           "lexical": 6.5, "grammar": 5.5}
    add_essays(s, [bad], start_id=110)
    s.close()
    s = factory()
    summary = {m["module"]: m for m in clearance_summary(s, 1)}
    assert summary["writing"]["cleared"] is False
    s.close()


def test_listening_clearance_with_attribution_ratio(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    for i in range(3):
        s.add(Practice(id=200 + i, user_id=1, module="listening", prompt_title="t",
                       prompt_text="p", content="c", status="done", total_band=92))
    s.commit()
    summary = {m["module"]: m for m in clearance_summary(s, 1)}
    assert summary["listening"]["cleared"] is True
    # 非词汇归因占比 >= 20% → 不通过
    for i in range(3):
        s.add(ErrorItem(user_id=1, practice_id=200, error_type="听力:连读", context="x"))
    s.add(ErrorItem(user_id=1, practice_id=200, error_type="听力:词汇", context="x"))
    s.commit()
    summary = {m["module"]: m for m in clearance_summary(s, 1)}
    assert summary["listening"]["cleared"] is False
    s.close()


def test_vocab_clearance(tmp_path):
    factory = make_db(tmp_path)
    s = factory()
    for i in range(10):
        s.add(Word(id=i + 1, text=f"w{i}", topic="教育"))
    for i in range(8):  # 8/10 = 80% → 通过
        s.add(ReviewCard(user_id=1, word_id=i + 1, reps=2, interval_days=7,
                         due_at=datetime.now()))
    s.commit()
    summary = {m["module"]: m for m in clearance_summary(s, 1)}
    assert summary["vocab"]["cleared"] is True
    assert abs(summary["vocab"]["mastery_rate"] - 0.8) < 0.01
    s.close()
```

- [ ] **Step 2: 写失败测试 test_skills_api.py**

```python
import pytest
from fastapi.testclient import TestClient

from app.database import Base, make_session_factory
from app.main import app
from app.models import SkillMastery, SkillNode, User
from app.seed import seed_db
from app.seed_listening import seed_listening_db
from app.seed_rules import seed_mastery_rules
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
    seed_listening_db(s)
    seed_mastery_rules(s)
    s.close()
    monkeypatch.setattr(app.state, "session_factory", factory)
    return TestClient(app)


def test_tree_shape_and_status(client):
    tree = client.get("/api/skills/tree").json()
    modules = {m["module"] for m in tree}
    assert modules == {"writing", "speaking", "listening"}
    writing = next(m for m in tree if m["module"] == "writing")
    assert len(writing["nodes"]) == 20
    assert all(n["status"] == "unseen" for n in writing["nodes"])
    # 叶节点带 can_verify 字段
    assert any("can_verify" in n for n in writing["nodes"])


def test_evaluate_and_eligibility(client):
    # 未学过任何 → 不可模考
    elig = client.get("/api/skills/exam-eligibility").json()
    assert elig["eligible"] is False
    assert elig["missing"]["writing"] == 20

    # 全部标 learned 后 → 可模考
    resp = client.post("/api/skills/evaluate").json()
    assert resp["updated"] == 0  # 没有 learned 节点
    factory = app.state.session_factory
    s = factory()
    for n in s.query(SkillNode).all():
        s.add(SkillMastery(user_id=1, node_id=n.id, status="learned"))
    s.commit()
    s.close()
    elig = client.get("/api/skills/exam-eligibility").json()
    assert elig["eligible"] is True


def test_target_band(client):
    assert client.get("/api/skills/target").json() == {"target_band": 6.5}
    assert client.put("/api/skills/target", json={"target_band": 7.0}).status_code == 200
    assert client.get("/api/skills/target").json() == {"target_band": 7.0}
    assert client.put("/api/skills/target", json={"target_band": 5.5}).status_code == 422
```

- [ ] **Step 3: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_clearance.py tests/test_skills_api.py -v`
Expected: FAIL

- [ ] **Step 4: 实现 exam_scoring.py**

`backend/app/services/exam_scoring.py`:
```python
def accuracy_to_band(acc: float) -> float:
    """听力正确率(0-100) → band"""
    if acc < 40: return 4.5
    if acc < 55: return 5.0
    if acc < 70: return 5.5
    if acc < 80: return 6.0
    if acc < 90: return 6.5
    if acc < 95: return 7.0
    return 7.5


def vocab_rate_to_band(rate: float) -> float:
    """词汇掌握率(0-1) → band"""
    if rate < 0.5: return 5.0
    if rate < 0.7: return 5.5
    if rate < 0.85: return 6.0
    if rate < 0.95: return 6.5
    return 7.0


def overall_round(avg: float) -> float:
    """雅思官方均分取整：.25 进 .5，.75 进下一整分"""
    whole = int(avg)
    frac = avg - whole
    if frac < 0.25:
        return float(whole)
    if frac < 0.75:
        return whole + 0.5
    return float(whole + 1)
```

- [ ] **Step 5: 实现 module_clearance.py**

`backend/app/services/module_clearance.py`:
```python
from sqlalchemy import select

from app.models import AIFeedback, ErrorItem, Practice, ReviewCard, SkillMastery, SkillNode, Word

TARGET = 6.5


def _recent_done(session, module: str, limit: int) -> list[Practice]:
    return session.scalars(
        select(Practice)
        .where(Practice.user_id == 1, Practice.module == module, Practice.status == "done")
        .order_by(Practice.created_at.desc()).limit(limit)).all()


def _writing(session) -> tuple[bool, str]:
    essays = _recent_done(session, "writing", 5)
    if len(essays) < 5:
        return False, f"需要最近 5 篇 Task 2（当前 {len(essays)} 篇）"
    if sum(p.total_band for p in essays) / 5 < TARGET:
        return False, "最近 5 篇均分未达 6.5"
    for p in essays:
        for key in ("task_response", "coherence", "lexical", "grammar"):
            if p.feedback and p.feedback.bands.get(key, 0) < 6.0:
                return False, f"存在子分 < 6.0（{key}）"
    return True, "最近 5 篇均分 ≥ 6.5 且子分全部 ≥ 6.0"


def _speaking(session) -> tuple[bool, str]:
    turns = _recent_done(session, "speaking", 20)
    p2 = [p for p in turns if p.prompt_text and len(p.content.split()) > 30]
    topics = {}
    for p in p2:
        if p.total_band is not None:
            topics.setdefault(p.prompt_title, []).append(p)
    qualified = [t for t, ps in topics.items()
                 if any(p.total_band >= TARGET and p.feedback
                        and p.feedback.bands.get("fluency", 0) >= TARGET for p in ps)]
    if len(qualified) >= 3:
        return True, "3 个不同话题 Part 2 均达 6.5 且流利度 ≥ 6.5"
    return False, f"需要 3 个不同话题 Part 2 ≥ 6.5（当前 {len(qualified)} 个）"


def _listening(session) -> tuple[bool, str]:
    dictations = _recent_done(session, "listening", 3)
    if len(dictations) < 3:
        return False, f"需要最近 3 篇精听（当前 {len(dictations)} 篇）"
    if any((p.total_band or 0) < 90 for p in dictations):
        return False, "存在正确率 < 90% 的精听"
    pids = [p.id for p in dictations]
    errors = session.scalars(select(ErrorItem).where(ErrorItem.practice_id.in_(pids))).all()
    if errors:
        non_vocab = [e for e in errors if e.error_type != "听力:词汇"]
        if len(non_vocab) / len(errors) >= 0.2:
            return False, "非词汇类归因占比 ≥ 20%"
    return True, "最近 3 篇精听正确率 ≥ 90% 且归因结构健康"


def _vocab(session) -> tuple[bool, str]:
    total = len(session.scalars(select(Word.id)).all())
    if total == 0:
        return False, "词库为空"
    mastered = len(session.scalars(
        select(ReviewCard.id).where(ReviewCard.reps >= 2,
                                    ReviewCard.interval_days >= 7)).all())
    rate = mastered / total
    if rate >= 0.8:
        return True, f"词库掌握率 {rate:.0%} ≥ 80%"
    return False, f"词库掌握率 {rate:.0%} < 80%"


def _mastery_rate(session, module: str) -> float:
    node_ids = session.scalars(select(SkillNode.id).where(SkillNode.module == module)).all()
    if not node_ids:
        return 0.0
    verified = len(session.scalars(
        select(SkillMastery.id).where(SkillMastery.node_id.in_(node_ids),
                                      SkillMastery.status == "verified")).all())
    return verified / len(node_ids)


def clearance_summary(session, user_id: int) -> list[dict]:
    result = []
    for module, fn in (("writing", _writing), ("speaking", _speaking),
                       ("listening", _listening), ("vocab", _vocab)):
        cleared, detail = fn(session)
        result.append({"module": module, "cleared": cleared, "detail": detail,
                       "mastery_rate": round(_mastery_rate(session, module), 2)})
    return result
```

（词汇模块 mastery_rate 用掌握率而非节点：`_vocab` 的 detail 里已含；`_mastery_rate("vocab")` 无节点返回 0.0——前端展示时用词汇卡的掌握率。）

- [ ] **Step 6: schemas.py 追加 + api/skills.py**

schemas.py:
```python
class SkillNodeOut(BaseModel):
    id: int
    code: str
    title: str
    parent_id: int | None
    status: str  # unseen/learned/verified
    can_verify: bool
    sort_order: int


class ModuleTree(BaseModel):
    module: str
    nodes: list[SkillNodeOut]


class ClearanceOut(BaseModel):
    module: str
    cleared: bool
    detail: str
    mastery_rate: float


class TargetBandUpdate(BaseModel):
    target_band: float

    @field_validator("target_band")
    @classmethod
    def valid_target(cls, v: float) -> float:
        if v not in (6.0, 6.5, 7.0, 7.5):
            raise ValueError("目标分仅支持 6.0/6.5/7.0/7.5")
        return v
```

`backend/app/api/skills.py`:
```python
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from app.models import SkillMastery, SkillNode, User
from app.schemas import ClearanceOut, ModuleTree, SkillNodeOut, TargetBandUpdate
from app.services.mastery_rules import evaluate_all, evaluate_node
from app.services.module_clearance import clearance_summary

router = APIRouter(prefix="/api")


def get_session(request: Request):
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


@router.get("/skills/tree", response_model=list[ModuleTree])
def skill_tree(session=Depends(get_session)):
    nodes = session.scalars(select(SkillNode).order_by(SkillNode.sort_order, SkillNode.id)).all()
    masteries = {m.node_id: m for m in session.scalars(select(SkillMastery)).all()}
    modules: dict[str, list[SkillNodeOut]] = {}
    for n in nodes:
        m = masteries.get(n.id)
        status = m.status if m else "unseen"
        can_verify = status != "verified" and evaluate_node(n, session, 1)
        modules.setdefault(n.module, []).append(SkillNodeOut(
            id=n.id, code=n.code, title=n.title, parent_id=n.parent_id,
            status=status, can_verify=can_verify, sort_order=n.sort_order))
    return [ModuleTree(module=mod, nodes=ns) for mod, ns in modules.items()]


@router.post("/skills/evaluate")
def evaluate(session=Depends(get_session)):
    return {"updated": evaluate_all(session, 1)}


@router.get("/skills/clearance", response_model=list[ClearanceOut])
def clearance(session=Depends(get_session)):
    return clearance_summary(session, 1)


@router.get("/skills/exam-eligibility")
def exam_eligibility(session=Depends(get_session)):
    nodes = session.scalars(select(SkillNode)).all()
    learned_ids = set(session.scalars(
        select(SkillMastery.node_id).where(SkillMastery.user_id == 1)).all())
    missing: dict[str, int] = {}
    for n in nodes:
        if n.id not in learned_ids:
            missing[n.module] = missing.get(n.module, 0) + 1
    return {"eligible": not missing, "missing": missing}


@router.get("/skills/target")
def get_target(session=Depends(get_session)):
    return {"target_band": session.get(User, 1).target_band}


@router.put("/skills/target")
def put_target(payload: TargetBandUpdate, session=Depends(get_session)):
    user = session.get(User, 1)
    user.target_band = payload.target_band
    session.commit()
    return {"target_band": user.target_band}
```

main.py 挂路由：`from app.api.skills import router as skills_router` + `app.include_router(skills_router)`。

- [ ] **Step 7: 测试通过 + 全套回归**

Run: `cd backend && uv run pytest -v`
Expected: 全部通过（61 既有 + 6 新增）

- [ ] **Step 8: Commit**

```bash
git add backend/ && git commit -m "feat: 能力树 API + 模块通关判定 + 分数换算"
```

---

### Task 3: 模考 API（mock_exam 启用）

**Files:**
- Modify: `backend/app/models.py`（MockExam 加 practice_ids 列）
- Modify: `backend/app/schemas.py`
- Create: `backend/app/api/exams.py`
- Modify: `backend/app/main.py`（挂 exams 路由）
- Test: `backend/tests/test_exams.py`

**Interfaces:**
- Consumes: `exam_scoring`（Task 2）、`mastery_rules`（Task 1）
- Produces（前端 Task 4 对接）:
  - `POST /api/mock_exams` → 201 `{exam_id: int}`
  - `POST /api/mock_exams/{id}/complete`，body `{practice_ids: [int...]}` → `ExamOut`（`{id, scores: dict, predicted_band: float, report: {top_errors: [{type, count}], weak_nodes: [{code, title}]}, created_at}`）；四科缺一 → 422
  - `GET /api/mock_exams` → `list[ExamOut]`（倒序）
  - `GET /api/mock_exams/latest` → `ExamOut | null`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_exams.py`:
```python
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.database import Base, make_session_factory
from app.main import app
from app.models import AIFeedback, ErrorItem, Practice, ReviewCard, SkillMastery, SkillNode, User, Word
from app.seed import seed_db
from app.seed_rules import seed_mastery_rules
from app.services.exam_scoring import accuracy_to_band, overall_round, vocab_rate_to_band


@pytest.fixture()
def client(tmp_path, monkeypatch):
    factory = make_session_factory(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(factory.kw["bind"])
    s = factory()
    s.add(User(id=1))
    s.commit()
    seed_db(s)
    seed_mastery_rules(s)
    s.close()
    monkeypatch.setattr(app.state, "session_factory", factory)
    return TestClient(app)


def test_scoring_tables():
    assert accuracy_to_band(30) == 4.5
    assert accuracy_to_band(72) == 6.0
    assert accuracy_to_band(96) == 7.5
    assert vocab_rate_to_band(0.4) == 5.0
    assert vocab_rate_to_band(0.97) == 7.0
    # 官方取整
    assert overall_round(6.25) == 6.5
    assert overall_round(6.125) == 6.0
    assert overall_round(6.75) == 7.0
    assert overall_round(6.5) == 6.5


def _make_practice(s, pid, module, band, bands=None):
    s.add(Practice(id=pid, user_id=1, module=module, prompt_title="t", prompt_text="p",
                   content="c", status="done", total_band=band))
    if bands:
        s.add(AIFeedback(practice_id=pid, bands=bands, annotations=[], rewrite="", model="m"))
    s.commit()


def test_mock_exam_flow(client):
    factory = app.state.session_factory
    s = factory()
    _make_practice(s, 1, "writing", 6.5, {"overall": 6.5})
    _make_practice(s, 2, "speaking", 6.0, {"overall": 6.0})
    _make_practice(s, 3, "listening", 90)  # 正确率 90 → 7.0
    for i in range(4):
        s.add(Word(id=i + 1, text=f"w{i}", topic="教育"))
        s.add(ReviewCard(user_id=1, word_id=i + 1, reps=2, interval_days=7,
                         due_at=datetime.now()))
    s.add(ErrorItem(user_id=1, practice_id=1, error_type="时态", context="x"))
    s.close()

    exam = client.post("/api/mock_exams").json()
    out = client.post(f"/api/mock_exams/{exam['exam_id']}/complete",
                      json={"practice_ids": [1, 2, 3]}).json()
    assert out["scores"] == {"writing": 6.5, "speaking": 6.0, "listening": 7.0, "vocab": 7.0}
    # 均分 6.625 → 6.5
    assert out["predicted_band"] == 6.5
    assert out["report"]["top_errors"][0] == {"type": "时态", "count": 1}
    assert len(out["report"]["weak_nodes"]) > 0  # 全未绿

    latest = client.get("/api/mock_exams/latest").json()
    assert latest["id"] == out["id"]
    assert len(client.get("/api/mock_exams").json()) == 1


def test_complete_requires_four_modules(client):
    exam = client.post("/api/mock_exams").json()
    resp = client.post(f"/api/mock_exams/{exam['exam_id']}/complete",
                       json={"practice_ids": []})
    assert resp.status_code == 422
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_exams.py -v`
Expected: FAIL

- [ ] **Step 3: models.py MockExam 加列 + report 改 JSON**

```python
    practice_ids: Mapped[list] = mapped_column(JSON, default=list)
    report: Mapped[dict] = mapped_column(JSON, default=dict)  # 由 Text 改为 JSON（薄弱点报告是结构化数据）
```

- [ ] **Step 4: schemas.py 追加**

```python
class ExamComplete(BaseModel):
    practice_ids: list[int]


class ExamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scores: dict
    predicted_band: float | None
    report: dict
    practice_ids: list[int]
    created_at: datetime
```


- [ ] **Step 5: 实现 api/exams.py**

`backend/app/api/exams.py`:
```python
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from app.models import (AIFeedback, ErrorItem, MockExam, Practice, ReviewCard,
                        SkillMastery, SkillNode, Word)
from app.schemas import ExamComplete, ExamOut
from app.services.exam_scoring import accuracy_to_band, overall_round, vocab_rate_to_band

router = APIRouter(prefix="/api")


def get_session(request: Request):
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


@router.post("/mock_exams", status_code=201)
def create_exam(session=Depends(get_session)):
    exam = MockExam(user_id=1)
    session.add(exam)
    session.commit()
    session.refresh(exam)
    return {"exam_id": exam.id}


@router.post("/mock_exams/{exam_id}/complete", response_model=ExamOut)
def complete_exam(exam_id: int, payload: ExamComplete, session=Depends(get_session)):
    exam = session.get(MockExam, exam_id)
    if exam is None:
        raise HTTPException(status_code=404, detail="模考不存在")
    practices = [session.get(Practice, pid) for pid in payload.practice_ids]
    by_module: dict[str, Practice] = {}
    for p in practices:
        if p is not None and p.status == "done" and p.module not in by_module:
            by_module[p.module] = p

    missing = [m for m in ("writing", "speaking", "listening") if m not in by_module]
    if missing:
        raise HTTPException(status_code=422, detail=f"缺少模块成绩: {', '.join(missing)}")

    scores = {
        "writing": by_module["writing"].feedback.bands["overall"],
        "speaking": by_module["speaking"].feedback.bands["overall"],
        "listening": accuracy_to_band(by_module["listening"].total_band or 0),
    }
    total_words = len(session.scalars(select(Word.id)).all())
    mastered = len(session.scalars(
        select(ReviewCard.id).where(ReviewCard.reps >= 2,
                                    ReviewCard.interval_days >= 7)).all())
    scores["vocab"] = vocab_rate_to_band(mastered / total_words if total_words else 0)

    avg = sum(scores.values()) / 4
    predicted = overall_round(avg)

    # 薄弱点报告：近 30 天错误聚类 TOP5 + 未绿节点
    since = datetime.now() - timedelta(days=30)
    errors = session.scalars(
        select(ErrorItem).where(ErrorItem.created_at >= since)).all()
    counts: dict[str, int] = {}
    for e in errors:
        counts[e.error_type] = counts.get(e.error_type, 0) + 1
    top_errors = [{"type": t, "count": c}
                  for t, c in sorted(counts.items(), key=lambda kv: -kv[1])[:5]]
    weak = session.scalars(
        select(SkillNode).join(SkillMastery, SkillMastery.node_id == SkillNode.id)
        .where(SkillMastery.user_id == 1, SkillMastery.status != "verified")).all()
    weak_nodes = [{"code": n.code, "title": n.title} for n in weak[:10]]

    exam.scores = scores
    exam.predicted_band = predicted
    exam.report = {"top_errors": top_errors, "weak_nodes": weak_nodes}
    exam.practice_ids = payload.practice_ids
    session.commit()
    session.refresh(exam)
    return exam


@router.get("/mock_exams", response_model=list[ExamOut])
def list_exams(session=Depends(get_session)):
    return session.scalars(
        select(MockExam).where(MockExam.predicted_band.isnot(None))
        .order_by(MockExam.created_at.desc())).all()


@router.get("/mock_exams/latest", response_model=ExamOut | None)
def latest_exam(session=Depends(get_session)):
    return session.scalars(
        select(MockExam).where(MockExam.predicted_band.isnot(None))
        .order_by(MockExam.created_at.desc()).limit(1)).first()
```

main.py 挂路由：`from app.api.exams import router as exams_router` + `app.include_router(exams_router)`。

- [ ] **Step 6: 测试通过 + 全套回归**

Run: `cd backend && uv run pytest -v`
Expected: 全部通过（67 既有 + 3 新增）

- [ ] **Step 7: Commit**

```bash
git add backend/ && git commit -m "feat: 全真模考 API（四科汇总 + 预测分 + 薄弱点报告）"
```

---

### Task 4: 前端能力树页 + 模考向导

**Files:**
- Modify: `frontend/src/api/types.ts` / `frontend/src/api/client.ts`
- Create: `frontend/src/pages/SkillTreePage.tsx`
- Create: `frontend/src/pages/MockExamPage.tsx`
- Create: `frontend/src/components/ExamSteps.tsx`（四个步骤组件）
- Modify: `frontend/src/App.tsx`（`/skills`、`/mock` 路由）
- Modify: `frontend/src/components/NavBar.tsx`

**Interfaces:**
- Consumes: Task 2/3 API + V1-V4 既有 API（prompts/essays/speaking/listening/vocab）
- Produces: 无下游

- [ ] **Step 1: types/client 追加**

types.ts:
```ts
export interface SkillNodeOut {
  id: number
  code: string
  title: string
  parent_id: number | null
  status: 'unseen' | 'learned' | 'verified'
  can_verify: boolean
  sort_order: number
}

export interface ModuleTree {
  module: string
  nodes: SkillNodeOut[]
}

export interface ClearanceOut {
  module: string
  cleared: boolean
  detail: string
  mastery_rate: number
}

export interface ExamOut {
  id: number
  scores: Record<string, number>
  predicted_band: number | null
  report: { top_errors: { type: string; count: number }[]; weak_nodes: { code: string; title: string }[] } | string
  practice_ids: number[]
  created_at: string
}
```

client.ts:
```ts
export function getSkillTree(): Promise<ModuleTree[]> { return request('/skills/tree') }
export function evaluateSkills(): Promise<{ updated: number }> { return request('/skills/evaluate', { method: 'POST' }) }
export function getClearance(): Promise<ClearanceOut[]> { return request('/skills/clearance') }
export function getExamEligibility(): Promise<{ eligible: boolean; missing: Record<string, number> }> { return request('/skills/exam-eligibility') }
export function getTargetBand(): Promise<{ target_band: number }> { return request('/skills/target') }
export function setTargetBand(band: number): Promise<{ target_band: number }> {
  return request('/skills/target', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ target_band: band }) })
}
export function createMockExam(): Promise<{ exam_id: number }> { return request('/mock_exams', { method: 'POST' }) }
export function completeMockExam(id: number, practiceIds: number[]): Promise<ExamOut> {
  return request(`/mock_exams/${id}/complete`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ practice_ids: practiceIds }) })
}
export function getLatestExam(): Promise<ExamOut | null> { return request('/mock_exams/latest') }
```

- [ ] **Step 2: SkillTreePage**

`frontend/src/pages/SkillTreePage.tsx`:
```tsx
import { useEffect, useState } from 'react'
import { evaluateSkills, getClearance, getSkillTree } from '../api/client'
import type { ClearanceOut, ModuleTree, SkillNodeOut } from '../api/types'

const MODULE_NAMES: Record<string, string> = {
  writing: '写作', speaking: '口语', listening: '听力', vocab: '词汇',
}

function dotClass(n: SkillNodeOut) {
  if (n.status === 'verified') return 'bg-emerald-500'
  if (n.status === 'learned') return 'bg-amber-400'
  return 'bg-slate-300'
}

export default function SkillTreePage() {
  const [tree, setTree] = useState<ModuleTree[]>([])
  const [clearance, setClearance] = useState<ClearanceOut[]>([])
  const [message, setMessage] = useState('')

  const load = () => {
    getSkillTree().then(setTree).catch(() => undefined)
    getClearance().then(setClearance).catch(() => undefined)
  }
  useEffect(load, [])

  const reevaluate = async () => {
    const r = await evaluateSkills()
    setMessage(r.updated > 0 ? `新点亮 ${r.updated} 个能力点 🎉` : '暂无新点亮的能力点，继续练习吧')
    load()
  }

  // 按 parent_id 计算缩进深度
  const renderNodes = (nodes: SkillNodeOut[]) => {
    const byId = new Map(nodes.map((n) => [n.id, n]))
    const depth = (n: SkillNodeOut): number =>
      n.parent_id && byId.has(n.parent_id) ? 1 + depth(byId.get(n.parent_id)!) : 0
    return [...nodes].sort((a, b) => a.code.localeCompare(b.code)).map((n) => (
      <div key={n.id} className="flex items-center gap-2 py-1"
        style={{ paddingLeft: `${depth(n) * 20}px` }}>
        <span className={`h-2.5 w-2.5 rounded-full ${dotClass(n)}`} />
        <span className={`text-sm ${n.status === 'verified' ? 'text-slate-800' : 'text-slate-500'}`}>
          {n.title}
        </span>
        {n.can_verify && (
          <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-xs text-emerald-600">
            达成条件，待点亮
          </span>
        )}
      </div>
    ))
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold">能力树</h2>
        <button onClick={reevaluate}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white">
          重新评估点亮
        </button>
      </div>
      {message && <div className="rounded-lg bg-indigo-50 p-3 text-sm text-indigo-700">{message}</div>}
      <div className="flex gap-4 text-xs text-slate-400">
        <span><i className="mr-1 inline-block h-2.5 w-2.5 rounded-full bg-slate-300" />未学</span>
        <span><i className="mr-1 inline-block h-2.5 w-2.5 rounded-full bg-amber-400" />已学未验证</span>
        <span><i className="mr-1 inline-block h-2.5 w-2.5 rounded-full bg-emerald-500" />已验证掌握</span>
      </div>
      {clearance.map((c) => (
        <div key={c.module} className={`rounded-lg border p-3 text-sm ${
          c.cleared ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                    : 'border-slate-200 bg-white text-slate-500'
        }`}>
          {MODULE_NAMES[c.module]}模块{c.cleared ? '已通关 🎓' : '未通关'}：{c.detail}
          {c.mastery_rate > 0 && `（能力点掌握率 ${(c.mastery_rate * 100).toFixed(0)}%）`}
        </div>
      ))}
      {tree.map((mod) => (
        <div key={mod.module} className="rounded-xl border border-slate-200 bg-white p-4">
          <h3 className="mb-2 font-semibold">{MODULE_NAMES[mod.module] ?? mod.module}</h3>
          {renderNodes(mod.nodes)}
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 3: MockExamPage + ExamSteps**

`frontend/src/pages/MockExamPage.tsx`（向导壳 + 结果页）:
```tsx
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  completeMockExam, createMockExam, getExamEligibility, getTargetBand,
} from '../api/client'
import type { ExamOut } from '../api/types'
import {
  ExamListeningStep, ExamSpeakingStep, ExamVocabStep, ExamWritingStep,
} from '../components/ExamSteps'

const STEPS = ['写作（40 分钟）', '口语 Part 2', '听力精听', '词汇快测'] as const

export default function MockExamPage() {
  const [step, setStep] = useState(-1)  // -1 = 入口页
  const [eligible, setEligible] = useState<boolean | null>(null)
  const [missing, setMissing] = useState<Record<string, number>>({})
  const [examId, setExamId] = useState(0)
  const [practiceIds, setPracticeIds] = useState<number[]>([])
  const [result, setResult] = useState<ExamOut | null>(null)
  const [target, setTarget] = useState(6.5)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    getExamEligibility().then((e) => {
      setEligible(e.eligible)
      setMissing(e.missing)
    }).catch((e) => setError(String(e)))
    getTargetBand().then((t) => setTarget(t.target_band)).catch(() => undefined)
  }, [])

  const start = async () => {
    const e = await createMockExam()
    setExamId(e.exam_id)
    setStep(0)
  }

  const stepDone = (practiceId: number) => {
    const next = [...practiceIds, practiceId]
    setPracticeIds(next)
    if (step < 3) {
      setStep(step + 1)
    } else {
      completeMockExam(examId, next).then(setResult).catch((e) => setError(String(e)))
    }
  }

  if (result) {
    const passed = (result.predicted_band ?? 0) >= target
    return (
      <div className="mx-auto max-w-2xl space-y-6">
        <div className={`rounded-2xl p-8 text-center text-white ${passed ? 'bg-emerald-600' : 'bg-indigo-600'}`}>
          <div className="text-sm opacity-80">预测总分</div>
          <div className="text-6xl font-bold">{result.predicted_band?.toFixed(1)}</div>
          <div className="mt-2 text-lg">{passed ? '🎓 可赴考状态' : `目标 ${target}，继续加油`}</div>
        </div>
        <div className="grid grid-cols-4 gap-3 text-center">
          {Object.entries(result.scores).map(([mod, band]) => (
            <div key={mod} className="rounded-xl border border-slate-200 bg-white p-3">
              <div className="text-xs text-slate-400">
                {{ writing: '写作', speaking: '口语', listening: '听力', vocab: '词汇' }[mod] ?? mod}
              </div>
              <div className="text-xl font-bold">{band.toFixed(1)}</div>
            </div>
          ))}
        </div>
        {typeof result.report === 'object' && (
          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <h3 className="mb-2 font-semibold">薄弱点报告</h3>
            {(result.report.top_errors ?? []).length > 0 && (
              <div className="mb-3">
                <div className="text-sm text-slate-400">高频错误</div>
                {(result.report.top_errors ?? []).map((e) => (
                  <div key={e.type} className="flex justify-between text-sm">
                    <span>{e.type}</span><span className="text-slate-400">{e.count} 次</span>
                  </div>
                ))}
              </div>
            )}
            {(result.report.weak_nodes ?? []).length > 0 && (
              <div>
                <div className="text-sm text-slate-400">待回补能力点</div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {(result.report.weak_nodes ?? []).map((n) => (
                    <span key={n.code}
                      className="rounded bg-amber-50 px-2 py-0.5 text-xs text-amber-700">
                      {n.title}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
        <button onClick={() => navigate('/')}
          className="w-full rounded-xl bg-indigo-600 py-3 font-semibold text-white">
          回到仪表盘
        </button>
      </div>
    )
  }

  if (step === -1) {
    return (
      <div className="mx-auto max-w-xl space-y-4 text-center">
        <h2 className="text-2xl font-bold">全真模考</h2>
        <p className="text-sm text-slate-500">
          依次完成四个环节：{STEPS.join(' → ')}。完成后 AI 综评输出预测总分与薄弱点报告。
        </p>
        {eligible === false && (
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-left text-sm text-amber-700">
            <div className="font-semibold">尚未解锁模考</div>
            <div className="mt-1">需要先让所有能力点"学过一遍"（变黄）。当前缺口：</div>
            <ul className="mt-1 list-inside list-disc">
              {Object.entries(missing).map(([mod, n]) => (
                <li key={mod}>{mod}：{n} 个未学节点</li>
              ))}
            </ul>
            <div className="mt-2">去各模块任意练一次即可变黄。</div>
          </div>
        )}
        {eligible && (
          <button onClick={start}
            className="rounded-xl bg-indigo-600 px-8 py-3 text-lg font-semibold text-white">
            开始模考
          </button>
        )}
        {error && <div className="text-sm text-red-500">{error}</div>}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        {STEPS.map((s, i) => (
          <span key={s} className={`rounded-lg px-3 py-1 text-xs ${
            i < step ? 'bg-emerald-100 text-emerald-700'
            : i === step ? 'bg-indigo-600 text-white'
            : 'bg-slate-100 text-slate-400'
          }`}>
            {i + 1}. {s}
          </span>
        ))}
      </div>
      {step === 0 && <ExamWritingStep onDone={stepDone} />}
      {step === 1 && <ExamSpeakingStep onDone={stepDone} />}
      {step === 2 && <ExamListeningStep onDone={stepDone} />}
      {step === 3 && <ExamVocabStep onDone={stepDone} />}
      {error && <div className="text-sm text-red-500">{error}</div>}
    </div>
  )
}
```

`frontend/src/components/ExamSteps.tsx`（四个精简步骤，复用既有 API）:
```tsx
import { useEffect, useRef, useState } from 'react'
import {
  createSpeakingSession, finishSpeakingSession, getReviewQueue, getSpeakingTurn,
  listListeningMaterials, listPrompts, submitDictation, submitEssay,
  submitReview, submitSpeakingTurn, getListeningMaterial,
} from '../api/client'
import type { MatDetailOut, ReviewCardOut } from '../api/types'
import { WavRecorder } from '../lib/recorder'

export function ExamWritingStep({ onDone }: { onDone: (practiceId: number) => void }) {
  const [prompts, setPrompts] = useState<{ title: string; text: string }[]>([])
  const [selected, setSelected] = useState(0)
  const [content, setContent] = useState('')
  const [secondsLeft, setSecondsLeft] = useState(40 * 60)
  const [busy, setBusy] = useState(false)
  const startRef = useRef(Date.now())

  useEffect(() => {
    listPrompts().then(setPrompts).catch(() => undefined)
  }, [])
  useEffect(() => {
    if (secondsLeft <= 0) return
    const t = setTimeout(() => setSecondsLeft(secondsLeft - 1), 1000)
    return () => clearTimeout(t)
  }, [secondsLeft])

  if (prompts.length === 0) return <div className="p-10 text-slate-400">加载中…</div>

  const submit = async () => {
    setBusy(true)
    try {
      const p = prompts[selected]
      const essay = await submitEssay({
        prompt_title: p.title, prompt_text: p.text, content,
        duration_sec: Math.round((Date.now() - startRef.current) / 1000),
      })
      // 等批改完成再进下一步（轮询）
      const { getEssay } = await import('../api/client')
      let detail = await getEssay(essay.id)
      while (detail.status === 'pending') {
        await new Promise((r) => setTimeout(r, 2000))
        detail = await getEssay(essay.id)
      }
      onDone(essay.id)
    } finally {
      setBusy(false)
    }
  }

  const mm = String(Math.floor(secondsLeft / 60)).padStart(2, '0')
  const ss = String(secondsLeft % 60).padStart(2, '0')
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <select className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
          value={selected} onChange={(e) => setSelected(Number(e.target.value))}>
          {prompts.map((p, i) => <option key={p.title} value={i}>{p.title}</option>)}
        </select>
        <span className={`font-mono text-lg ${secondsLeft < 300 ? 'text-red-500' : 'text-slate-600'}`}>
          ⏱ {mm}:{ss}
        </span>
      </div>
      <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-600">
        {prompts[selected].text}
      </div>
      <textarea
        className="min-h-[300px] w-full rounded-xl border border-slate-300 p-4 font-mono text-sm"
        placeholder="Task 2 作文（250 词以上）…"
        value={content}
        onChange={(e) => setContent(e.target.value)}
      />
      <button onClick={submit} disabled={busy || content.trim().split(/\s+/).length < 30}
        className="w-full rounded-xl bg-indigo-600 py-3 font-semibold text-white disabled:opacity-40">
        {busy ? '批改中…' : '提交并进入下一环节'}
      </button>
    </div>
  )
}

export function ExamSpeakingStep({ onDone }: { onDone: (practiceId: number) => void }) {
  const [card, setCard] = useState<{ id: number; topic: string } | null>(null)
  const [sessionId, setSessionId] = useState(0)
  const [question, setQuestion] = useState('')
  const [recording, setRecording] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const recorderRef = useRef<WavRecorder | null>(null)

  useEffect(() => {
    (async () => {
      const cards = await import('../api/client').then((c) => c.listSpeakingCards(2))
      const pick = cards[Math.floor(Math.random() * cards.length)]
      setCard(pick)
      const sess = await createSpeakingSession(pick.id)
      setSessionId(sess.id)
      setQuestion(sess.question)
    })().catch((e) => setError(String(e)))
    return () => {
      if (recorderRef.current) {
        const r = recorderRef.current
        recorderRef.current = null
        void r.stop()
      }
    }
  }, [])

  const toggle = async () => {
    if (recording) {
      const recorder = recorderRef.current
      if (!recorder) return
      recorderRef.current = null
      setRecording(false)
      setBusy(true)
      try {
        const blob = await recorder.stop()
        const { practice_id } = await submitSpeakingTurn(sessionId, blob)
        let detail = await getSpeakingTurn(practice_id)
        let polls = 0
        while (detail.status === 'pending' && polls < 30) {
          await new Promise((r) => setTimeout(r, 2000))
          detail = await getSpeakingTurn(practice_id)
          polls++
        }
        await finishSpeakingSession(sessionId)
        onDone(practice_id)
      } catch (e) {
        setError(String(e))
        setBusy(false)
      }
    } else {
      try {
        recorderRef.current = new WavRecorder()
        await recorderRef.current.start()
        setRecording(true)
      } catch {
        setError('无法访问麦克风')
      }
    }
  }

  if (!card) return <div className="p-10 text-slate-400">抽题中…</div>
  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <div className="text-xs text-slate-400">Part 2 Cue Card</div>
        <div className="mt-1 whitespace-pre-wrap font-medium">{question}</div>
      </div>
      {error && <div className="text-sm text-red-500">{error}</div>}
      <button onClick={toggle} disabled={busy}
        className={`w-full rounded-xl py-3 font-semibold text-white disabled:opacity-40 ${
          recording ? 'bg-red-500' : 'bg-indigo-600'}`}>
        {recording ? '■ 停止并提交' : busy ? '评分中…' : '● 开始陈述（约 2 分钟）'}
      </button>
    </div>
  )
}

export function ExamListeningStep({ onDone }: { onDone: (practiceId: number) => void }) {
  const [mat, setMat] = useState<MatDetailOut | null>(null)
  const [answers, setAnswers] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    (async () => {
      const mats = await listListeningMaterials()
      const s4 = mats.filter((m) => m.section === 4)
      const pick = (s4.length ? s4 : mats)[Math.floor(Math.random() * (s4.length ? s4.length : mats.length))]
      const detail = await getListeningMaterial(pick.id)
      setMat(detail)
      setAnswers(detail.sentences.map(() => ''))
    })().catch((e) => setError(String(e)))
  }, [])

  if (!mat) return <div className="p-10 text-slate-400">选题中…</div>

  const submit = async () => {
    setBusy(true)
    try {
      const result = await submitDictation(mat.id, answers)
      onDone(result.practice_id)
    } catch (e) {
      setError(String(e))
      setBusy(false)
    }
  }

  return (
    <div className="space-y-3">
      <div className="text-sm text-slate-500">
        精听听写：{mat.title}（{mat.sentences.length} 句，逐句播放并输入）
      </div>
      {mat.sentences.map((_, i) => (
        <div key={i} className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-3">
          <button type="button"
            onClick={() => new Audio(`/api/listening/audio/${mat.id}/${i}.mp3`).play().catch(() => undefined)}
            className="shrink-0 rounded-lg bg-indigo-50 px-3 py-1 text-sm text-indigo-600">
            ▶ {i + 1}
          </button>
          <input
            className="flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
            value={answers[i]}
            onChange={(e) => {
              const next = [...answers]
              next[i] = e.target.value
              setAnswers(next)
            }}
          />
        </div>
      ))}
      {error && <div className="text-sm text-red-500">{error}</div>}
      <button onClick={submit} disabled={busy}
        className="w-full rounded-xl bg-indigo-600 py-3 font-semibold text-white disabled:opacity-40">
        {busy ? '比对中…' : '提交听写'}
      </button>
    </div>
  )
}

export function ExamVocabStep({ onDone }: { onDone: (practiceId: number) => void }) {
  const [queue, setQueue] = useState<ReviewCardOut[]>([])
  const [flipped, setFlipped] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    getReviewQueue(20).then((q) => setQueue(q.cards)).catch((e) => setError(String(e)))
  }, [])

  const current = queue[0]

  const rate = async (quality: 1 | 3 | 5) => {
    await submitReview(current.word_id, quality)
    setQueue((q) => q.slice(1))
    setFlipped(false)
  }

  if (error) return <div className="text-sm text-red-500">{error}</div>
  if (queue.length === 0 && !current) {
    // 队列空：词汇环节记为已完成——用一个 listening 之外的标记：直接调 onDone 是不行的（需要 practice_id）。
    // 词汇快测不产生 practice；用最近一次 listening/写作 practice？——见 plan 注：词汇环节不计 practice_id，complete 只需要写/口/听三科。
    return <VocabDone onDone={onDone} />
  }
  if (!current) return <VocabDone onDone={onDone} />

  return (
    <div className="mx-auto max-w-xl space-y-4">
      <div className="text-center text-sm text-slate-400">剩 {queue.length} 张</div>
      <div onClick={() => setFlipped(!flipped)}
        className="cursor-pointer rounded-2xl border border-slate-200 bg-white p-10 text-center shadow-sm">
        {!flipped ? (
          <div className="text-3xl font-bold">{current.text}</div>
        ) : (
          <div className="space-y-2">
            <div className="text-2xl font-bold">{current.text}</div>
            <div className="text-slate-700">{current.meaning}</div>
            <div className="text-sm italic text-slate-500">{current.example_sentence}</div>
          </div>
        )}
      </div>
      {flipped && (
        <div className="grid grid-cols-3 gap-3">
          <button onClick={() => rate(1)} className="rounded-xl bg-red-500 py-3 font-semibold text-white">不认识</button>
          <button onClick={() => rate(3)} className="rounded-xl bg-amber-500 py-3 font-semibold text-white">模糊</button>
          <button onClick={() => rate(5)} className="rounded-xl bg-emerald-600 py-3 font-semibold text-white">认识</button>
        </div>
      )}
    </div>
  )
}

function VocabDone({ onDone }: { onDone: (practiceId: number) => void }) {
  return (
    <div className="space-y-4 text-center">
      <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-6 text-emerald-700">
        词汇快测完成
      </div>
      <button onClick={() => onDone(-1)}  // -1 = 占位，complete 端只用写/口/听三科
        className="w-full rounded-xl bg-indigo-600 py-3 font-semibold text-white">
        完成模考，查看综评
      </button>
    </div>
  )
}
```

**Plan 注（实现者须知）**：词汇快测不产生 practice 记录（review 不算 practice）；`onDone(-1)` 是占位 id，后端 complete 只校验 writing/speaking/listening 三科（词汇分从词库掌握率算），`practice_ids` 里的 -1 会被 `session.get(Practice, -1)` 返回 None 安全跳过。

- [ ] **Step 4: 路由与导航**

- `App.tsx`：加 `SkillTreePage`、`MockExamPage` 路由 `/skills`、`/mock`
- `NavBar.tsx` links 追加 `{ to: '/skills', label: '能力树' }`、`{ to: '/mock', label: '模考' }`

- [ ] **Step 5: 构建验证**

Run: `cd frontend && npm run build`（Node v22，unset 代理）
Expected: 通过

- [ ] **Step 6: Commit**

```bash
git add frontend/ && git commit -m "feat: 能力树页 + 全真模考四步向导"
```

---

### Task 5: 仪表盘预测分 + e2e + 文档 + 推送

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx`
- Modify: `README.md`

- [ ] **Step 1: DashboardPage 顶部改造**

- 顶部大卡改为「预测分 → 目标分」：
  - 拉取 `getLatestExam()` + `getTargetBand()` + `getClearance()`
  - 有模考：显示 `latest.predicted_band`；无模考：用各科最近一次成绩滚动估计（写作/口语用 total_band，听力 `accuracy_to_band` 在前端复刻一个小映射函数，词汇用 topics 掌握率映射）——把估计逻辑写成一个 `estimateBand()` 辅助函数放页面内
  - 目标分下拉（6.0/6.5/7.0/7.5）调 `setTargetBand`
  - 预测分 ≥ 目标 → 绿色「可赴考」徽章
- 大卡下方加四模块掌握率进度条行（clearance 的 mastery_rate；词汇模块用词库掌握率，从 listVocabTopics 聚合）
- 保留原有各模块卡片；横幅删除（能力树已上线）

- [ ] **Step 2: 构建 + 全量测试**

```bash
cd frontend && npm run build
cd ../backend && uv run pytest -v
```
Expected: 全绿（70 后端用例）

- [ ] **Step 3: e2e（端口 8022，全 mock）**

起服务后：
```bash
curl localhost:8022/api/skills/tree | head -c 300
curl -X POST localhost:8022/api/skills/evaluate
curl localhost:8022/api/skills/clearance
curl localhost:8022/api/skills/exam-eligibility
# 走完写作/口语/听力各一次练习后：
curl -X POST localhost:8022/api/mock_exams
curl -X POST localhost:8022/api/mock_exams/1/complete -H 'Content-Type: application/json' -d '{"practice_ids": [1, 2, 3]}'
curl localhost:8022/api/mock_exams/latest
```
Expected：树返回三模块；eligibility 在练习后变 true；complete 返回四科 scores + predicted_band + report。

- [ ] **Step 4: README 更新**

加一节：
```markdown
## 掌握体系（V5）

- `/skills` 能力树：四模块能力点三态（未学/已学/已验证），绿态由练习数据按规则自动判定
- `/mock` 全真模考：写作 → 口语 Part 2 → 听力精听 → 词汇快测 四步，输出预测总分 + 薄弱点报告
- 模考解锁条件：所有能力点至少学过一遍（变黄）；预测分 ≥ 目标分显示「可赴考」
- 目标分默认 6.5，仪表盘可切换 6.0/6.5/7.0/7.5
```

- [ ] **Step 5: Commit + push**

```bash
git add -A && git commit -m "docs: README 更新 + 仪表盘预测分，V5 完成" && git push
```

- [ ] **Step 6: 收尾核对（对照规格 §1 成功标准）**

- 能力树三态 + 规则引擎点亮 ✓
- 四模块通关判定 ✓
- 模考四步 + 预测总分 + 薄弱点报告 ✓
- 可赴考徽章 + 仪表盘预测分/掌握率 ✓
