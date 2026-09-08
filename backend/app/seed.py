import json
from pathlib import Path

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

EXPANDED_PROMPTS_PATH = Path(__file__).parent / "data" / "writing_prompts_expanded.json"


def load_task2_prompts() -> list[dict]:
    """内置题目 + expand_content.py 生成的扩充题目（按 text 去重）。"""
    prompts = list(TASK2_PROMPTS)
    if EXPANDED_PROMPTS_PATH.exists():
        seen = {p["text"] for p in prompts}
        expanded = json.loads(EXPANDED_PROMPTS_PATH.read_text(encoding="utf-8"))
        prompts.extend(p for p in expanded if p["text"] not in seen)
    return prompts


def seed_db(session) -> None:
    """幂等写入能力树种子数据（按模块判断，便于后续模块增量补种）。"""
    existing = session.scalars(
        select(SkillNode.code).where(SkillNode.code.like("writing.%"))).first()
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
