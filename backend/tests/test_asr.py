import json

from app.config import settings
from app.services.asr import build_transcriber
from app.services.asr.base import TranscriptResult
from app.services.asr.iflytek import IFlytekTranscriber
from app.services.asr.mock import MockTranscriber


def test_mock_transcriber():
    t = MockTranscriber()
    assert t.is_mock is True
    result = t.transcribe("any.wav")
    assert isinstance(result, TranscriptResult)
    assert len(result.text.split()) >= 50
    assert 0 < result.confidence <= 1


def test_build_transcriber_falls_back_to_mock(monkeypatch):
    monkeypatch.setattr(settings, "iflytek_app_id", "")
    monkeypatch.setattr(settings, "iflytek_api_secret", "")
    assert build_transcriber().is_mock is True


def test_build_transcriber_picks_iflytek(monkeypatch):
    monkeypatch.setattr(settings, "iflytek_app_id", "appid")
    monkeypatch.setattr(settings, "iflytek_api_secret", "secret")
    assert build_transcriber().is_mock is False


def test_iflytek_sign_is_deterministic():
    t = IFlytekTranscriber("myappid", "mysecret")
    # 讯飞签名 = base64(hmac-sha1(md5(appid+ts), secret))
    import base64, hashlib, hmac
    ts = "1700000000"
    expected = base64.b64encode(
        hmac.new(b"mysecret", hashlib.md5(b"myappid1700000000").hexdigest().encode(), hashlib.sha1
        ).digest()).decode()
    assert t._sign(ts) == expected


def test_iflytek_parse_result_json():
    t = IFlytekTranscriber("a", "s")
    # 讯飞 getResult 的 content.orderResult（JSON 字符串）的最小结构样例
    order_result = json.dumps({
        "lattice2": [
            {"json_1best": {"st": {"rt": [{"ws": [
                {"w": "Well", "wp": "n"}, {"w": " ", "wp": "s"},
                {"w": "I", "wp": "n"}, {"w": " ", "wp": "s"},
                {"w": "think", "wp": "n"}
            ]}], "sc": 87}}}
        ]
    })
    result = t._parse_order_result(order_result)
    assert result.text == "Well I think"
    assert 0 < result.confidence <= 1


def test_iflytek_parse_result_json_with_cw():
    t = IFlytekTranscriber("a", "s")
    # 真实 API 结构：词被 cw 候选数组包裹（ws[].cw[].w），且可能只有 lattice
    order_result = json.dumps({
        "lattice": [
            {"json_1best": {"st": {"rt": [{"ws": [
                {"cw": [{"w": "I", "wp": "n"}]},
                {"cw": [{"w": " ", "wp": "s"}]},
                {"cw": [{"w": "agree", "wp": "n"}]}
            ]}], "sc": 92}}}
        ]
    })
    result = t._parse_order_result(order_result)
    assert result.text == "I agree"
    assert 0 < result.confidence <= 1
