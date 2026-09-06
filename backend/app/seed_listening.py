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
