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
