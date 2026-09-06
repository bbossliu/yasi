# yasi

AI 驱动的雅思私教（V1 写作批改 + V2 口语练习）。

## 快速开始

```bash
# 后端（Python >= 3.11，优先 uv）
cd backend
uv sync                      # 无 uv：python -m venv .venv && .venv/bin/pip install -e .
cp .env.example .env         # 填入 DEEPSEEK_API_KEY；不填则用内置演示批改
uv run uvicorn app.main:app --port 8000

# 前端（Node >= 22）（本机实测 v20 无法构建）
cd frontend
npm install
npm run dev                  # http://localhost:5173
```

注意：V2 给 practice 表加了列，V3 给 word 表加了 pos/meaning 列；旧版生成的 `backend/yasi.db` 请删除后重建（开发期无迁移机制）。

### 端口占用

前端 `vite.config.ts` 的代理写死指向 `http://localhost:8000`。若 8000 被其他项目占用，可任选其一：

- 释放 8000 端口后再启动后端；或
- 让后端跑在其他端口（如 `--port 8022`），并把 `frontend/vite.config.ts` 中 `server.proxy['/api'].target` 改为对应地址。

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

## 结构

- `backend/` FastAPI + SQLAlchemy 2.0 + SQLite；批改管线在 `app/services/grader.py`
- `frontend/` React + Vite + Tailwind + ECharts + Framer Motion
- `docs/superpowers/specs/` 设计规格；`docs/superpowers/plans/` 实施计划
