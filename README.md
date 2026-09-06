# yasi

AI 驱动的雅思私教（V1：写作 Task 2 智能批改）。

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

### 端口占用

前端 `vite.config.ts` 的代理写死指向 `http://localhost:8000`。若 8000 被其他项目占用，可任选其一：

- 释放 8000 端口后再启动后端；或
- 让后端跑在其他端口（如 `--port 8022`），并把 `frontend/vite.config.ts` 中 `server.proxy['/api'].target` 改为对应地址。

## 测试

```bash
cd backend && uv run pytest -v
cd frontend && npm run build
```

## 结构

- `backend/` FastAPI + SQLAlchemy 2.0 + SQLite；批改管线在 `app/services/grader.py`
- `frontend/` React + Vite + Tailwind + ECharts + Framer Motion
- `docs/superpowers/specs/` 设计规格；`docs/superpowers/plans/` 实施计划
