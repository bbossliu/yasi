from sqlalchemy import select

from app.models import SkillNode

# no_error_type 窗口 5 篇；band_avg 窗口 3 篇（见 v5 设计文档 §4）
_W = {"window": 5, "module": "writing"}
_S = {"window": 5, "module": "speaking"}
_W3 = {"window": 3, "module": "writing"}
_S3 = {"window": 3, "module": "speaking"}

RULES: dict[str, dict] = {
    # 写作 TR/CC 由对应子分驱动
    "writing.task2.tr.identify": {"rule": "band_avg", "band": "task_response", "min": 6.5, **_W3},
    "writing.task2.tr.position": {"rule": "band_avg", "band": "task_response", "min": 6.5, **_W3},
    "writing.task2.tr.cover": {"rule": "band_avg", "band": "task_response", "min": 6.5, **_W3},
    "writing.task2.cc.frame": {"rule": "band_avg", "band": "coherence", "min": 6.5, **_W3},
    "writing.task2.cc.paragraphing": {"rule": "band_avg", "band": "coherence", "min": 6.5, **_W3},
    "writing.task2.cc.linkers": {"rule": "no_error_type", "error_type": "连接词", **_W},
    "writing.task2.cc.reference": {"rule": "band_avg", "band": "coherence", "min": 6.5, **_W3},
    "writing.task2.lr.paraphrase": {"rule": "band_avg", "band": "lexical", "min": 6.5, **_W3},
    "writing.task2.lr.collocation": {"rule": "no_error_type", "error_type": "词汇搭配", **_W},
    "writing.task2.lr.academic": {"rule": "band_avg", "band": "lexical", "min": 6.5, **_W3},
    "writing.task2.lr.spelling": {"rule": "no_error_type", "error_type": "拼写", **_W},
    "writing.task2.gra.complex": {"rule": "band_avg", "band": "grammar", "min": 6.5, **_W3},
    "writing.task2.gra.agreement": {"rule": "no_error_type", "error_type": "主谓一致", **_W},
    "writing.task2.gra.tense": {"rule": "no_error_type", "error_type": "时态", **_W},
    "writing.task2.gra.article": {"rule": "no_error_type", "error_type": "冠词", **_W},
    # 口语
    "speaking.fc.length": {"rule": "band_avg", "band": "fluency", "min": 6.5, **_S3},
    "speaking.fc.hesitation": {"rule": "no_error_type", "error_type": "自我重复", **_S},
    "speaking.fc.connectives": {"rule": "band_avg", "band": "fluency", "min": 6.5, **_S3},
    "speaking.lr.idiom": {"rule": "band_avg", "band": "lexical", "min": 6.5, **_S3},
    "speaking.lr.paraphrase": {"rule": "band_avg", "band": "lexical", "min": 6.5, **_S3},
    "speaking.lr.topic": {"rule": "no_error_type", "error_type": "词汇搭配", **_S},
    "speaking.gra.complex": {"rule": "band_avg", "band": "grammar", "min": 6.5, **_S3},
    "speaking.gra.tense": {"rule": "no_error_type", "error_type": "时态", **_S},
    "speaking.gra.agreement": {"rule": "no_error_type", "error_type": "主谓一致", **_S},
    "speaking.pr.intelligibility": {"rule": "band_avg", "band": "pronunciation", "min": 6.0, **_S3},
    "speaking.pr.intonation": {"rule": "band_avg", "band": "pronunciation", "min": 6.0, **_S3},
    "speaking.p1.direct": {"rule": "band_avg", "band": "overall", "min": 6.5, **_S3},
    "speaking.p2.structure": {"rule": "band_avg", "band": "overall", "min": 6.5, **_S3},
    "speaking.p3.depth": {"rule": "band_avg", "band": "overall", "min": 6.5, **_S3},
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
