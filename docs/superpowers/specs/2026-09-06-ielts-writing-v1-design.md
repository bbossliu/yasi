# V1 设计规格：雅思学习网站 · 写作 Task 2 AI 批改

> 日期：2026-09-06
> 上游文档：`~/Downloads/雅思学习网站设计方案.md`（产品总纲，含 V1-V4 路线图）
> 本规格范围：**仅 V1 迭代** —— 写作 Task 2 议论文批改单点突破，FastAPI + React 全栈。

## 1. 背景与目标

总纲定义的产品闭环：练习 → AI 评分/批改 → 错误沉淀 → 针对性复习 → 再练习。V1 只实现写作 Task 2 的「练习 → 批改 → 错误入库」段，但数据模型按全量设计，为 V2-V4 留好地基。

**V1 成功标准**：用户提交一篇 Task 2 作文后，能看到四项分项评分雷达图、逐句批注、原文 vs AI 修改版并排对比；批改中提取的语法错误模式自动入个人错误库；历史成绩曲线可查。无 API key 时凭内置 mock 数据也能走通完整流程。

## 2. 已确认的关键决策

| 决策点 | 结论 |
|---|---|
| 技术形态 | A：FastAPI 后端 + 前端框架正式全栈路线（非 Streamlit 验证版） |
| 前端栈 | React + Vite + TypeScript + Tailwind + Framer Motion + ECharts |
| LLM 调用 | OpenAI SDK 兼容模式直连 DeepSeek，`response_format={"type":"json_object"}`，Pydantic 校验输出 |
| API key | 存 `.env`（`DEEPSEEK_API_KEY`），缺失时自动降级到 mock 批改器 |
| 数据库 | SQLite（SQLAlchemy 模型层不变，后期切 PostgreSQL 只改连接串） |
| 缓存/队列 | 不用 Redis；批改结果轮询/SSE 获取 |
| 用户体系 | 无注册登录，单人硬编码（user_id=1） |

## 3. 仓库结构

```
wraptest/
├── backend/
│   ├── app/
│   │   ├── main.py            FastAPI 入口，挂载路由与 CORS
│   │   ├── config.py          环境变量加载（pydantic-settings）
│   │   ├── database.py        SQLAlchemy 2.0 engine/session
│   │   ├── models/            全部 9 张表（见 §5）
│   │   ├── schemas/           Pydantic：批改请求/响应 schema
│   │   ├── api/               /api/essays、/api/health
│   │   └── services/
│   │       ├── grader.py          DeepSeek 批改管线
│   │       ├── prompt_templates.py 官方四项 rubric 的 system prompt
│   │       └── mock_grader.py     固定示例批改结果（无 key 时启用）
│   ├── tests/                 pytest：评分管线、API、错误入库
│   └── pyproject.toml         优先用 uv 管理；环境无 uv 则退到 python -m venv + pip
├── frontend/
│   └── src/
│       ├── pages/             WritingPage / ResultPage / HistoryPage / DashboardPage(简版)
│       ├── components/        RadarChart、ScanOverlay、SentenceAnnotations、DiffView
│       └── api/               fetch 封装
└── docs/superpowers/specs/
```

## 4. V1 功能与页面

1. **写作页**：题目选择（内置 3-5 道 Task 2 真题风格题目）+ 文本框；侧边 AI 实时分析条（词数、预估分数区间、高级词汇占比，随输入滚动更新——V1 用词数/词汇统计的本地启发式，不调 LLM）。
2. **批改中**：全屏扫描动画（光束扫过文本，Framer Motion）。
3. **结果页**：
   - 四项分项雷达图（TR/CC/LR/GRA，ECharts，生长动画）
   - 逐句批注：打字机流式展示（SSE 或分段轮询）
   - 原文 vs AI 修改版并排对比，修改词高亮
4. **历史页**：历次成绩曲线 + 词数/用时记录。
5. **仪表盘（简版）**：最近一次总分、篇数、错误 TOP 类型占位卡。
6. **示例系统**：内置一篇 6 分风格示例作文 + 完整批改结果，「试试这个」一键填充，不写一个字即可体验全流程。

## 5. 数据模型（V1 全量建表，SQLAlchemy 2.0）

| 表 | 说明 | V1 使用情况 |
|---|---|---|
| user | 用户（含 target_band，默认 6.5） | 单行硬编码 |
| skill_node | 能力树节点（父子层级、模块、点亮标准 JSON） | 写入写作分支约 20 个能力点种子数据 |
| skill_mastery | 用户能力点掌握状态（未学/已学未验证/已验证 + 判定依据） | 批改回写时命中节点标黄 |
| word | 词库 | 建表留空 |
| review_card | SM-2 复习卡 | 建表留空 |
| listening_mat | 听力素材 | 建表留空 |
| practice | 练习记录（模块、得分、用时、原始输入、关联能力点） | 核心表 |
| ai_feedback | AI 反馈（分项分数 JSON、批注、改写文章） | 核心表 |
| error_item | 错误库（错误类型、上下文、来源 practice_id） | 核心表 |
| mock_exam | 模考记录 | 建表留空 |

## 6. 批改管线（grader.py）

1. `POST /api/essays`：落 `practice`（status=pending），后台任务启动批改，返回 practice_id。
2. 构造 prompt：system 内置官方四项评分 rubric + 输出 JSON schema 说明；user 为题目与作文原文。
3. 调用 DeepSeek（`json_object` 模式）→ Pydantic 校验：
   - 校验失败 → 带错误信息重试一次
   - 再失败 → practice 标记 `needs_review`，返回兜底错误提示
4. 成功 → 写 `ai_feedback`；从批注中提取语法错误模式聚类写入 `error_item`；命中 `skill_node` 的写 `skill_mastery`（已学未验证）；practice 标记 done。
5. 前端 SSE/轮询拿分项结果流式渲染。
6. `DEEPSEEK_API_KEY` 缺失 → 走 `mock_grader`，返回预置示例批改（同样落库，界面标注"演示数据"）。

## 7. 错误处理

- LLM 超时/限流：指数退避重试 1 次，最终失败落 `needs_review` 状态，前端可见明确错误信息。
- JSON 校验失败：见 §6 第 3 步。
- 空文本/超词数上限（如 500 词）：前端校验 + 后端 422。
- 音频、并发、多用户等问题 V1 不处理。

## 8. 测试

- `test_grader.py`：mock DeepSeek 响应，验证管线解析、重试、落库、错误提取。
- `test_api.py`：FastAPI TestClient 走提交→查询结果全流程（用 mock_grader）。
- `test_mastery.py`：能力点标黄逻辑。
- 前端不强制测试框架，手测为主（V2 再定）。

## 9. 明确不做（YAGNI）

注册登录、口语/听力/词汇模块、SM-2 复习调度、全真模考、PostgreSQL/Redis、AI 助教悬浮球、AI 周报、首页闭环动画、遗忘曲线动画。能力点点亮规则（绿态判定）V4 再接。
