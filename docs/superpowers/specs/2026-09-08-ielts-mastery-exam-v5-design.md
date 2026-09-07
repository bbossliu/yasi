# V5 设计规格：掌握即通过 —— 能力树点亮 + 全真模考 + 预测分体系

> 日期：2026-09-08
> 上游文档：`~/Downloads/雅思学习网站设计方案.md`（§1.4 终极目标：四个子系统）
> 本规格范围：目标分数反推的落地版——能力树三态可视化与绿态判定、模块通关判定、全真模考（mock_exam 表启用）、仪表盘预测分。
> 注：无人值守决策，遵循原方案与既有架构惯例。

## 1. 目标与成功标准

**V5 成功标准**：能力树页展示四模块全部节点及三态（灰=未学/黄=已学未验证/绿=已验证掌握）；绿态由练习数据按规则自动判定，不靠自评；每模块有明确通关判定（对照原方案 §③ 通关标准）；用户可进入全真模考向导，依次完成写作（计时 Task 2）→ 口语（Part 2 一卡）→ 听力（一篇听写）→ 词汇（20 卡快测），提交后得到预测总分 + 薄弱点报告；预测分 ≥ 目标分（默认 6.5）显示「可赴考」；仪表盘核心指标变为「当前预测分 → 目标分 + 能力点掌握率进度条」。

## 2. 关键决策

| 决策点 | 结论 |
|---|---|
| 绿态判定 | 规则引擎：节点 `criteria` JSON 声明规则，评估服务按最近练习数据判定。规则类型四种：`no_error_type`（最近 window 次练习中某 error_type 出现 0 次）、`band_avg`（最近 window 篇某子分均分 ≥ min）、`listening_accuracy`（最近 window 篇听写正确率 ≥ min 且指定归因占比 ≤ max_ratio）、`vocab_mastery_rate`（词库掌握率 ≥ min） |
| 规则挂载 | 叶节点挂具体规则；中间节点/根节点绿 = 全部直接子节点绿（聚合，不挂规则） |
| 模块通关 | 四模块各一个函数（对照原方案 6.5 目标版）：写作=最近 5 篇 Task 2 均分 ≥6.5 且四项子分无 <6.0；口语=最近 3 个不同 Part 2 话题 ≥6.5 且 fluency 子分 ≥6.5；听力=最近 3 篇精听正确率 ≥90 且非词汇归因占比 <20%；词汇=词库掌握率 ≥80%（200 词版本调整，原 95% 对应 3000 词） |
| 全真模考 | 单次会话四步（写作 → 口语 P2 → 听力听写 → 词汇 20 卡），复用既有练习管线（各步就是普通 practice，打上 exam 关联）；完成后汇总：四科换算 band → 均分 → 预测总分；薄弱点 = 近 30 天 error_item 聚类 TOP5 + 未绿节点列表 |
| 分数换算 | 听力正确率→band：<40→4.5, <55→5.0, <70→5.5, <80→6.0, <90→6.5, <95→7.0, ≥95→7.5；词汇掌握率→band：<50%→5.0, <70→5.5, <85→6.0, <95→6.5, ≥95→7.0；写作/口语直接用 AI 评分。预测总分 = 四科均分按官方规则取整（.25 进 .5） |
| 模考入口 | 所有能力点至少变黄（学过一遍）才解锁模考（对应原方案"学完所有能力点后解锁"的 V5 简化版）；未解锁时前端显示缺口提示 |
| 目标分 | 用户表 target_band 已有（默认 6.5），V5 提供修改入口（仪表盘小控件，可选 6.0/6.5/7.0/7.5） |

## 3. 数据模型变更

- `mock_exam` 启用：scores = `{"writing": 6.5, "speaking": 6.0, "listening": 6.5, "vocab": 6.0}`，predicted_band = 均分取整，report = 薄弱点报告 JSON `{top_errors: [{type, count}], weak_nodes: [{code, title}]}`
- `mock_exam` 加关联：`practice_ids` JSON 列（四步产生的 practice id 列表）——**加一列**（开发期删库重建，README 已有提示）
- 其余表不动。节点 criteria 规则通过**数据迁移式种子更新**：新增 `seed_rules.py`，为既有叶节点写 criteria（按 code 精确匹配更新，幂等）

## 4. 后端组件

```
backend/app/
├── services/mastery_rules.py   evaluate_node(node, session, user_id) -> bool；
│                               evaluate_all(session, user_id) -> 更新 learned→verified
├── services/module_clearance.py 四个通关判定函数 + clearance_summary(session, user_id)
├── services/exam_scoring.py    accuracy_to_band / vocab_rate_to_band / overall_round（官方取整）
├── api/skills.py               能力树/通关 API
├── api/exams.py                模考 API
└── seed_rules.py               seed_mastery_rules(session)（叶节点 criteria 写入，幂等）
```

**叶节点规则映射（writing 为例，其余模块同理）**：
- `writing.task2.gra.agreement` → `{"rule": "no_error_type", "error_type": "主谓一致", "window": 5, "module": "writing"}`
- `writing.task2.tr.*` → `{"rule": "band_avg", "band": "task_response", "window": 3, "min": 6.5, "module": "writing"}`
- `speaking.fc.*` → band_avg fluency（口语）、`listening.dictation.liaison` → `{"rule": "listening_accuracy", "window": 3, "min": 90, "error_type": "听力:连读", "max_ratio": 0.2}`
- `speaking.pr.*`（发音）规则从简：band_avg pronunciation window 3 min 6.0
- 词汇模块节点少，vocab 规则只挂在词库层面；词汇无 skill_node 分支（V3 未建），V5 不补词汇节点，模块通关单独判定

**API**：

```
GET  /api/skills/tree                        四模块树 + 每节点 {code,title,status,evidence}
POST /api/skills/evaluate                    触发全量评估（绿态刷新）→ {updated: n}
GET  /api/skills/clearance                   四模块 {module, cleared: bool, detail: str, mastery_rate}
GET  /api/skills/exam-eligibility            {eligible: bool, missing: [未变黄节点数 by module]}

POST /api/mock_exams                         开始模考 → {exam_id}
POST /api/mock_exams/{id}/complete           四步完成后调用 → 汇总计算 → MockExamOut
GET  /api/mock_exams                         历史模考列表
GET  /api/mock_exams/latest                  最新一次（仪表盘用）
GET  /api/skills/target                      {target_band}；PUT /api/skills/target {target_band}
```

**模考流程**：前端向导四步各自复用现有练习 API（写作 POST /api/essays、口语 speaking turns、听力 dictation、词汇 review），收集 practice_ids；complete 时后端校验四科都有数据 → 计算分数与报告 → 落 mock_exam。

## 5. 前端改动

| 页面 | 内容 |
|---|---|
| `SkillTreePage`（新，`/skills`） | 四模块树状缩进列表，节点三态圆点（灰/黄/绿）+ 通关状态横幅；「重新评估」按钮调 evaluate |
| `MockExamPage`（新，`/mock`） | 向导式四步：每步内嵌对应练习的精简版（写作计时 40min 编辑器、口语 P2 录音、听力听写、词汇 20 卡）；完成页：四项分数 + 预测总分大卡 + 薄弱点报告 + 可赴考徽章（若达标） |
| `DashboardPage`（改） | 顶部改为「预测总分 → 目标分」大卡（来自最新模考或滚动估计：无模考时用各科最近成绩估计）+ 四模块掌握率进度条 + 目标分切换下拉 |
| NavBar | 加「能力树」「模考」 |

## 6. 测试

- `test_mastery_rules.py`：四种规则的真假分支、聚合节点、evaluate_all 幂等
- `test_clearance.py`：四模块通关判定的通过/不通过边界
- `test_exams.py`：分数换算表、overall 取整规则、complete 汇总（构造四科 practice）、eligibility
- 前端无单测，`npm run build` 门槛

## 7. 明确不做（YAGNI）

模考严格锁时强制提交（只有计时器提示）、口语音频的多轮完整模考（只考 P2）、阅读模块（原方案四大模块无阅读练习功能，能力树阅读分支也不建）、预测分曲线图（历史模考列表即可）、能力点掌握率的分模块细分图表。
