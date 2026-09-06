import base64
import hashlib
import hmac
import json
import time
import wave

import httpx

from app.services.asr.base import TranscribeFailed, TranscriptResult

API_UPLOAD = "https://raasr.xfyun.cn/v2/api/upload"
API_RESULT = "https://raasr.xfyun.cn/v2/api/getResult"
POLL_INTERVAL_SEC = 2
POLL_TIMEOUT_SEC = 60


class IFlytekTranscriber:
    is_mock = False

    def __init__(self, app_id: str, api_secret: str):
        self.app_id = app_id
        self.api_secret = api_secret

    def _sign(self, ts: str) -> str:
        md5 = hashlib.md5((self.app_id + ts).encode()).hexdigest().encode()
        digest = hmac.new(self.api_secret.encode(), md5, hashlib.sha1).digest()
        return base64.b64encode(digest).decode()

    def _audio_duration_ms(self, audio_path: str) -> int:
        with wave.open(audio_path, "rb") as wf:
            return int(wf.getnframes() / wf.getframerate() * 1000)

    def _parse_order_result(self, order_result: str) -> TranscriptResult:
        data = json.loads(order_result)
        words: list[str] = []
        scores: list[float] = []
        for lattice in data.get("lattice2", []):
            st = lattice["json_1best"]["st"]
            if st.get("sc"):
                scores.append(float(st["sc"]))
            for rt in st.get("rt", []):
                for ws in rt.get("ws", []):
                    words.append(ws["w"])
        text = "".join(words).strip()
        # 讯飞按词给出空格分隔的 wp=s 占位，清掉多余空白
        text = " ".join(text.split())
        confidence = min(sum(scores) / len(scores) / 100, 1.0) if scores else 0.9
        return TranscriptResult(text=text, confidence=round(confidence, 2))

    def transcribe(self, audio_path: str) -> TranscriptResult:
        with open(audio_path, "rb") as f:
            audio = f.read()
        ts = str(int(time.time()))
        try:
            with httpx.Client(trust_env=False, timeout=30.0) as client:
                resp = client.post(API_UPLOAD, data={
                    "appId": self.app_id,
                    "signa": self._sign(ts),
                    "ts": ts,
                    "fileSize": str(len(audio)),
                    "fileName": "audio.wav",
                    "duration": str(self._audio_duration_ms(audio_path)),
                }, files={"content": ("audio.wav", audio, "audio/wav")})
                body = resp.json()
                if body.get("code") != "000000":
                    raise TranscribeFailed(f"upload failed: {body}")
                order_id = body["content"]["orderId"]

                deadline = time.time() + POLL_TIMEOUT_SEC
                while time.time() < deadline:
                    ts = str(int(time.time()))
                    resp = client.post(API_RESULT, data={
                        "appId": self.app_id,
                        "signa": self._sign(ts),
                        "ts": ts,
                        "orderId": order_id,
                    })
                    body = resp.json()
                    if body.get("code") != "000000":
                        raise TranscribeFailed(f"getResult failed: {body}")
                    status = body["content"]["orderInfo"]["status"]
                    if status == 4:  # 完成
                        return self._parse_order_result(body["content"]["orderResult"])
                    if status == -1:
                        raise TranscribeFailed(f"transcribe failed: {body}")
                    time.sleep(POLL_INTERVAL_SEC)
                raise TranscribeFailed("transcribe timeout")
        except TranscribeFailed:
            raise
        except Exception as exc:
            raise TranscribeFailed(str(exc)) from exc
