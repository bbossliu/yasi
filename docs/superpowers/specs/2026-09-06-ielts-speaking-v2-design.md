# V2 设计规格：雅思学习网站 · 口语模块

> 日期：2026-09-06
> 上游文档：`~/Downloads/雅思学习网站设计方案.md`（产品总纲）、`docs/superpowers/specs/2026-09-06-ielts-writing-v1-design.md`（V1）
> 本规格范围：**仅 V2 迭代** —— 口语模块：录音上传 → ASR 转写 → DeepSeek 四项评分 → 7 分改写 → 错误入库，含 Part 1/2/3 三入口与多轮 AI 考官对话。

## 1. 背景与目标

V1 已交付写作 Task 2 批改闭环（practice/ai_feedback/error_item 三表核心逻辑、评分管线、结果页组件）。V2 在同一骨架上加口语：每个回答是一条 `practice`（module="speaking"），复用评分、错误入库、历史、结果页的全部既有逻辑。

**V2 成功标准**：用户完成一轮口语练习（任一部分）后，能看到该回答的转写文本、四项分项雷达图、逐句批注、7 分改写版；Part 1/3 支持一个话题下的多轮连续问答（聊天式界面）；无讯飞 key 时走 Mock 转写完整跑通。

## 2. 已确认的关键决策

| 决策点 | 结论 |
|---|---|
| ASR 方案 | 国产 ASR API，provider = **讯飞开放平台**（语音转写 HTTP API，HMAC-SHA256 签名） |
| ASR 配置 | `.env`：`IFLYTEK_APP_ID / IFLYTEK_API_SECRET / IFLYTEK_API_KEY`；缺失时自动降级 MockTranscriber |
| V2 范围 | 完整版：Part 1/2/3 三入口 + 多轮 AI 考官对话 + edge-tts 语音提问 |
| 对话推进 | Part 1 按预设问题序列；Part 3 由 DeepSeek 基于用户回答转写生成追问；每轮回答独立评分 |
| TTS | edge-tts 预生成提问音频，按题目 ID 缓存磁盘；失败降级纯文字 |
| 录音 | 浏览器 MediaRecorder（webm/opus），上传 FastAPI 存 `backend/uploads/`（gitignored） |
| 发音分项 | 转写置信度 + 文本表现侧面评估，UI 固定标注「发音分为间接评估，仅供参考」 |
| 题库 | 当季（2026 年 9-12 月换题季）话题卡种子：手写 + DeepSeek 预生成入库 |

## 3. 新增/变更数据模型

**新表：**

```
speaking_card    话题卡：id, part(1/2/3), topic, season(如 "2026-09"), payload(JSON：
                 Part1/3 = {questions: [...]}; Part2 = {topic, cues: [...], })、created_at
speaking_session 练习会话：id, user_id, card_id, status(active/done), created_at
```

**`practice` 加两列**（V1 库迁移方式：开发期删除 yasi.db 重建即可，README 注明）：

```
audio_path  可空字符串，录音文件相对路径
session_id  可空整数，FK speaking_session.id（写作练习为 NULL）
```

**复用不变**：`ai_feedback.bands` 是 schemaless JSON——口语用 `{fluency, lexical, grammar, pronunciation, overall}`；新增 Pydantic 校验 schema `SpeakingResult`。`error_item`、`skill_mastery`（口语节点标黄）逻辑不变。

## 4. 后端组件

```
backend/app/
├── services/
│   ├── asr/
│   │   ├── base.py           TranscriptResult(text, confidence) + BaseTranscriber 协议
│   │   ├── iflytek.py        IFlytekTranscriber（签名、上传、轮询结果）
│   │   └── mock.py           MockTranscriber（返回预置转写文本）
│   ├── speaking_grader.py    SpeakingGrader（DeepSeek，口语 rubric prompt）+ run_speaking_grading()
│   ├── followup.py           Part 3 追问生成（DeepSeek，基于对话历史）
│   └── tts.py                edge-tts 生成 + 磁盘缓存（backend/tts_cache/，gitignored）
├── api/speaking.py           口语路由
└── seed_speaking.py          话题卡种子 + 口语能力树节点种子
```

**API（全部沿用 V1 的 session_factory/后台任务模式）：**

```
GET  /api/speaking/cards?part=N          话题卡列表
POST /api/speaking/sessions              开会话（card_id）→ session + 第一问（文本 + tts_url）
POST /api/speaking/turns                 multipart：session_id + 音频文件
                                         → 存音频 → 后台任务：转写+评分+生成下一问
                                         → 返回 turn_id（practice_id）
GET  /api/speaking/turns/{id}            轮询该轮结果（转写/评分/下一问/会话是否结束）
POST /api/speaking/sessions/{id}/finish  主动结束会话 → 汇总（各轮均分）
GET  /api/tts/{question_hash}.mp3        TTS 音频静态服务
```

**评分管线**（与 V1 `run_grading` 对称）：转写失败 → `needs_review`；DeepSeek validate 失败 → 补 `}` 重 parse + 最多 3 次重试（沿用 V1 加固）；成功 → 写 `ai_feedback`（is_mock 标记）+ `error_item` + 口语能力点标黄（`mark_speaking_learned`，按 module="speaking"）。

**边界**：音频 ≤ 5MB、时长 ≤ 3 分钟（前端 MediaRecorder 超时自动停止 + 后端大小校验 413）；Part 3 追问生成失败时回退到预设序列下一题。

## 5. 前端改动

| 页面 | 内容 |
|---|---|
| `SpeakingPage`（新） | Part 1/2/3 三个 Tab + 话题卡列表，点卡开练 |
| `PracticeRoom`（新） | 聊天界面：AI 考官气泡（文字 + 播放按钮播 TTS）/ 用户气泡（录音回放 + 转写 + 该轮得分）；录音按钮（长按或点击启停，MediaRecorder）；Part 2 模式：cue card + 1 分钟准备倒计时 + 2 分钟陈述 |
| `ResultPage`（改） | 按 module 渲染：口语四项雷达（FC/LR/GRA/P）+ 发音局限标注 + 录音回放与转写对照 |
| `HistoryPage`（改） | 记录加模块标签（写作/口语） |
| `DashboardPage`（改） | 加口语最新分卡片 |
| 路由 | `/speaking`、`/speaking/session/:id` |

## 6. 种子数据

- `speaking_card`：Part 1 × 5 题（每题 4 问）、Part 2 × 8 卡、Part 3 × 5 题（每题 3 问预设 + LLM 追问），season="2026-09"
- `skill_node` 口语分支（module="speaking"，约 15 节点：流利度/词汇/语法/发音四类下挂具体能力点）；seed 按模块幂等（V1 已改为按 `writing.` 前缀判断，口语种子同理用 `speaking.` 前缀）

## 7. 测试

- `test_asr.py`：Mock 转写、IFlytekTranscriber 签名构造（mock HTTP）
- `test_speaking_grader.py`：评分管线（fake grader 成功/失败、错误入库、口语能力点标黄幂等）
- `test_speaking_api.py`：开会话 → 提交音频（构造 multipart）→ 轮询拿结果 → 追问生成 → 结束会话；超大小音频 413
- 前端仍不设单测，`npm run build` 为门槛

## 8. 明确不做（YAGNI）

实时打断/抢话、音素级发音评估、季度题库自动爬取、流式 ASR（边说边转）、多用户、V3 词汇 / V4 听力与仪表盘深化。
