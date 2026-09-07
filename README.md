# yasi

AI 驱动的雅思私教（V1 写作批改 + V2 口语练习 + V3 词汇 + V4 听力 + V5 掌握体系）。

## 快速开始

```bash
# 后端（Python >= 3.11，优先 uv）
cd backend
uv sync                      # 无 uv：python -m venv .venv && .venv/bin/pip install -e .
cp .env.example .env         # 填入 DEEPSEEK_API_KEY；不填则用内置演示批改
uv run uvicorn app.main:app --port 8022

# 前端（Node >= 22）（本机实测 v20 无法构建）
cd frontend
npm install
npm run dev                  # http://localhost:5173（被占用时自动顺延，如 5174）
```

注意：V2 给 practice 表加了列，V3 给 word 表加了 pos/meaning 列，V5 给 mock_exam 表改了列；旧版生成的 `backend/yasi.db` 请删除后重建（开发期无迁移机制）。

### 端口占用

前端 `vite.config.ts` 的代理默认指向 `http://localhost:8022`（因本机 8000 被其他项目长期占用）。若你使用 8000 端口起后端，把 `server.proxy['/api']` 改回 `http://localhost:8000` 即可；反之亦然——两端端口保持一致即可。

## 测试

```bash
cd backend && uv run pytest -v
cd frontend && npm run build
```

## 口语模块（V2）

- 入口：`/speaking`，Part 1/2/3 三个部分，当季（2026-09）题库
- 录音在浏览器端编码为 16kHz WAV 上传；讯飞 key 未配置时使用演示转写
- Part 3 由 AI 根据回答生成追问；提问语音由 edge-tts 生成（生成失败自动降级为文字）
- 发音分项为间接评估，仅供参考

## 词汇模块（V3）

- 入口：`/vocab`，10 个雅思话题 × 20 核心词（释义 / 真题风格例句 / 同义替换链）
- 复习采用 SM-2 间隔重复：认识 / 模糊 / 不认识三档自评自动调度下次复习
- 写作、口语批改中的「词汇搭配」错误命中词库时会自动建复习卡（错词强制复现）
- 扩充词库：配好 DEEPSEEK_API_KEY 后运行 `cd backend && uv run python scripts/generate_vocab.py`

## 听力模块（V4）

- 入口：`/listening`，Section 2/3/4 各 2 篇 AI 生成素材（无版权问题）
- 音频由 edge-tts 逐句生成（首次打开素材时后台触发）；生成失败时文本练习仍可用
- 三种模式：逐句字幕对照（单句循环 + 0.75/1/1.25 变速）/ 精听听写（词级 diff 标红 + 错题归因）/ 影子跟读（ASR 转写比对）
- 听写正确率计入历史曲线（按模块切换查看）

## 掌握体系（V5）

- `/skills` 能力树：四模块能力点三态（未学/已学/已验证），绿态由练习数据按规则自动判定
- `/mock` 全真模考：写作 → 口语 Part 2 → 听力精听 → 词汇快测 四步，输出预测总分 + 薄弱点报告
- 模考解锁条件：所有能力点至少学过一遍（变黄）；预测分 ≥ 目标分显示「可赴考」
- 目标分默认 6.5，仪表盘可切换 6.0/6.5/7.0/7.5

## 结构

- `backend/` FastAPI + SQLAlchemy 2.0 + SQLite；批改管线在 `app/services/grader.py`
- `frontend/` React + Vite + Tailwind + ECharts + Framer Motion
- `docs/superpowers/specs/` 设计规格；`docs/superpowers/plans/` 实施计划
