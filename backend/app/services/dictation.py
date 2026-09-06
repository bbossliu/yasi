import re
import string

from rapidfuzz.distance import Levenshtein

_STRIP = string.punctuation + "，。！？；：""''（）【】"


def _tokenize(text: str) -> list[str]:
    return [t.strip(_STRIP) for t in text.lower().split() if t.strip(_STRIP)]


def diff_words(reference: str, hypothesis: str) -> dict:
    """词级 diff：ok/missing/wrong/extra。忽略大小写与标点。"""
    ref = _tokenize(reference)
    hyp = _tokenize(hypothesis)
    tokens: list[dict] = []
    for tag, a0, a1, b0, b1 in Levenshtein.opcodes(ref, hyp):
        if tag == "equal":
            for i in range(a0, a1):
                tokens.append({"type": "ok", "ref": ref[i], "hyp": ref[i]})
        elif tag == "delete":
            for i in range(a0, a1):
                tokens.append({"type": "missing", "ref": ref[i], "hyp": ""})
        elif tag == "insert":
            for j in range(b0, b1):
                tokens.append({"type": "extra", "ref": "", "hyp": hyp[j]})
        else:  # replace
            pairs = max(a1 - a0, b1 - b0)
            for k in range(pairs):
                r = ref[a0 + k] if a0 + k < a1 else ""
                h = hyp[b0 + k] if b0 + k < b1 else ""
                if r and h:
                    tokens.append({"type": "wrong", "ref": r, "hyp": h})
                elif r:
                    tokens.append({"type": "missing", "ref": r, "hyp": ""})
                else:
                    tokens.append({"type": "extra", "ref": "", "hyp": h})
    return {"tokens": tokens, "correct": all(t["type"] == "ok" for t in tokens)}


def score_dictation(sentences: list[str], answers: list[str]) -> dict:
    """逐句比对；正确率 = 全对句数/总句数 ×100 取整。答案不足按空串。"""
    per_sentence = []
    correct_count = 0
    for i, sentence in enumerate(sentences):
        answer = answers[i] if i < len(answers) else ""
        diff = diff_words(sentence, answer)
        per_sentence.append({"diff": diff, "correct": diff["correct"]})
        if diff["correct"]:
            correct_count += 1
    total = len(sentences)
    accuracy = round(100 * correct_count / total) if total else 0
    return {"accuracy": accuracy, "per_sentence": per_sentence}
