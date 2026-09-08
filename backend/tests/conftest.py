"""全局测试隔离：让 *_expanded.json（仓库内可能存在的扩充内容文件）不影响断言固定数量的测试。

需要测试合并逻辑的用例会在测试内重新 monkeypatch 对应路径（后设置的生效）。
"""
import pytest


@pytest.fixture(autouse=True)
def _isolate_expanded_content(tmp_path, monkeypatch):
    import app.seed
    import app.seed_listening
    import app.seed_speaking
    import app.seed_vocab

    missing = tmp_path / "missing_expanded.json"
    monkeypatch.setattr(app.seed, "EXPANDED_PROMPTS_PATH", missing)
    monkeypatch.setattr(app.seed_vocab, "EXPANDED_PATH", missing)
    monkeypatch.setattr(app.seed_speaking, "EXPANDED_CARDS_PATH", missing)
    monkeypatch.setattr(app.seed_listening, "EXPANDED_MATS_PATH", missing)
    monkeypatch.setattr(app.seed_listening, "ZH_PATH", missing)
