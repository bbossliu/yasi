from app.services.dictation import diff_words, score_dictation


def test_diff_all_correct():
    result = diff_words("An hour and a half.", "an hour and a half")
    assert result["correct"] is True
    assert all(t["type"] == "ok" for t in result["tokens"])


def test_diff_missing_wrong_extra():
    # 漏词
    r = diff_words("I really enjoy reading books", "I enjoy reading books")
    assert any(t["type"] == "missing" and t["ref"] == "really" for t in r["tokens"])
    assert r["correct"] is False
    # 错词（听错）
    r = diff_words("an hour and a half", "a nourana half")
    types = [t["type"] for t in r["tokens"]]
    assert "wrong" in types or "missing" in types
    assert r["correct"] is False
    # 多词
    r = diff_words("she sells seashells", "she sells some seashells")
    assert any(t["type"] == "extra" and t["hyp"] == "some" for t in r["tokens"])
    assert r["correct"] is False


def test_diff_ignores_case_and_punctuation():
    assert diff_words("Hello, World!", "hello world")["correct"] is True


def test_score_dictation_accuracy():
    sentences = ["one two", "three four", "five six"]
    answers = ["one two", "three five", ""]
    result = score_dictation(sentences, answers)
    assert result["accuracy"] == 33  # 1/3
    assert result["per_sentence"][0]["correct"] is True
    assert result["per_sentence"][2]["correct"] is False
    # 全对
    assert score_dictation(sentences, sentences)["accuracy"] == 100
