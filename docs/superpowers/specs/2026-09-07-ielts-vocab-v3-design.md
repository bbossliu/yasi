# V3 设计规格：雅思学习网站 · 词汇模块

> 日期：2026-09-07
> 上游文档：`~/Downloads/雅思学习网站设计方案.md`（产品总纲模块 1 + 动画优先级）、V1/V2 规格
> 本规格范围：**仅 V3 迭代** —— 话题词库 + SM-2 间隔重复复习 + 错词联动。
> 注：本次为无人值守决策（用户授权"继续干"），所有取舍遵循原方案文档与 YAGNI。

## 1. 目标与成功标准

原方案模块 1 的核心：词库按话题场景切分、艾宾浩斯/SM-2 复习调度、同义替换链、错词联动强制复现。

**V3 成功标准**：用户能按话题浏览词库（词 + 释义 + 真题风格例句 + 同义替换链）；开始复习会话，对卡片做三档自评（认识/模糊/不认识），SM-2 正确调度下次复习时间；写作/口语批改中出现词汇搭配错误且命中词库时自动建复习卡；仪表盘显示词汇掌握率。

## 2. 关键决策

| 决策点 | 结论 |
|---|---|
| 词库规模 | V3 种子 10 话题 × 20 词 = 200 核心词（手写 JSON 入库）；附 DeepSeek 批量扩充脚本 `scripts/generate_vocab.py`（有 key 时可把例句/替换链补全或扩词） |
| 复习算法 | 标准 SM-2（quality 0-5），前端三档映射：不认识=1、模糊=3、认识=5 |
| 例句/替换链 | 种子数据直接内置（预生成思路的静态版）；扩充脚本走 DeepSeek 批量 |
| 错词联动 | 批改写 `error_item` 时若 `error_type=="词汇搭配"`，在错误上下文中匹配词库单词 → 自动建/重置复习卡（确定性规则，可测试）。不做模糊词抽取 |
| 每日一句/动画 | 不做实时 LLM 每日一句（YAGNI）；遗忘曲线/词汇树动画简化为：替换链 chip 横排 + hover 显示、复习页显示未来 7 天到期分布（ECharts bar） |
| 掌握判定 | 复习卡的 `reps >= 2 且 interval_days >= 7` 视为"已掌握"，仪表盘掌握率 = 已掌握/词库总数 |

## 3. 数据模型变更

`word` 表加两列（开发期删 yasi.db 重建，README 已有提示）：

```
meaning  中文释义（String(300)，默认 ""）
pos      词性（String(20)，默认 ""，如 v./n./adj.）
```

`review_card` 复用现有列（ease_factor=2.5 起、interval_days、due_at、reps），不加列。

## 4. 后端组件

```
backend/app/
├── data/vocab_seed.py      200 词条目（text/pos/meaning/topic/paraphrase_chain/example_sentence）
├── services/sm2.py         sm2_review(card, quality) -> None（原地更新 ease/interval/due/reps）
│                           与 build_review_queue(session, limit)（到期卡 + 新词补充）
├── services/vocab_link.py  link_vocab_errors(session, user_id, error_items)：
│                           词汇搭配错误 → 匹配词库 → 建/重置复习卡（幂等）
├── api/vocab.py            词汇路由
└── seed_vocab.py           seed_vocab_db(session)（幂等，word 表空才写入）
```

**SM-2 标准流程**：quality < 3 → reps=0、interval=1；否则 reps+1，interval = 1 / 6 / round(prev*ease)；ease = max(1.3, ease + 0.1 - (5-q)*(0.08+(5-q)*0.02))；due_at = now + interval 天。

**API**：

```
GET  /api/vocab/topics                     [{topic, word_count, mastered_count, due_count}]
GET  /api/vocab/words?topic=xxx            [{id, text, pos, meaning, paraphrase_chain, example_sentence, review: {due_at, reps}|null}]
GET  /api/vocab/review/queue?limit=20      {cards: [{word_id, text, pos, meaning, paraphrase_chain, example_sentence, is_new}], due_total}
POST /api/vocab/review/{word_id}           body {quality: 1|3|5} → {next_due_at, interval_days}
GET  /api/vocab/forecast                   未来 7 天每天到期数 [{date, count}]
```

**错词联动接线**：`run_grading`（写作）与 `run_speaking_turn`（口语）在写 `error_item` 后调用 `link_vocab_errors`——对每条 `error_type=="词汇搭配"` 的 annotation，在其 `original` 句中做词库单词的子串匹配（小写、词边界），命中的词若无卡则建卡（due=now，立即到期），已有卡则重置 interval=1、due=now（强制复现）。匹配不到任何库内词则不动。

## 5. 前端改动

| 页面 | 内容 |
|---|---|
| `VocabPage`（新，`/vocab`） | 话题 chips（含词数/掌握/待复习数）→ 词表：每词卡片展示 释义/例句/替换链 chips（hover 显示该词例句）；顶部"开始复习"按钮（due_total>0 时高亮） |
| 复习会话（内嵌 VocabPage 或 `/vocab/review`） | 卡片式：正面单词+词性 → 点击翻转显示释义/例句/替换链 → 三档按钮（不认识/模糊/认识）；队列走完显示完成页 + 未来 7 天到期分布条形图 |
| `DashboardPage`（改） | 加词汇掌握率卡（已掌握/总词数 + 今日到期数），横幅改为"能力树、听力模块将在 V4 解锁" |
| NavBar | 加"词汇"链接 |

## 6. 种子数据

10 话题：教育、科技、环境、犯罪、媒体、健康、工作、城市化、文化、全球化。每话题 20 个雅思核心词，含 pos/meaning/替换链（3-5 词）/雅思风格例句。手写保证质量，JSON 结构：

```python
{"text": "abandon", "pos": "v.", "meaning": "放弃；抛弃", "topic": "教育",
 "paraphrase_chain": ["give up", "quit", "relinquish", "forsake"],
 "example_sentence": "Some students abandon their studies when they encounter difficulties."}
```

## 7. 测试

- `test_sm2.py`：SM-2 各 quality 分支的 interval/ease/due 转换；复习队列（到期 + 新词补充 + 数量上限）
- `test_vocab_api.py`：topics/words/queue/submit/forecast 全链路；三档评分后 due 时间正确推进；幂等
- `test_vocab_link.py`：词汇搭配错误命中词库建卡、重复命中重置、非词汇错误不动、未命中不动
- 前端无单测，`npm run build` 为门槛

## 8. 明确不做（YAGNI）

AI 实时每日一句、遗忘曲线动画（用 ECharts 到期分布替代）、词汇树生长动画、词库后台管理界面、3000 词全量（脚本扩充留给了用户）、单词发音 TTS、多用户。
