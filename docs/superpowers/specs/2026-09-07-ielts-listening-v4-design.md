# V4 设计规格：雅思学习网站 · 听力精听 + 仪表盘完善

> 日期：2026-09-07
> 上游文档：`~/Downloads/雅思学习网站设计方案.md`（模块 2 + V4 路线图）
> 本规格范围：**仅 V4 迭代** —— 听力精听（逐句字幕/单句循环/变速/听写比对/跟读比对/错题归因）+ 成绩仪表盘四项补齐。
> 注：无人值守决策，取舍遵循原方案与 YAGNI。

## 1. 目标与成功标准

**V4 成功标准**：用户能在听力页播放素材（逐句字幕、单句循环、0.75/1/1.25 变速）；听写模式下逐句输入，系统用词级 diff 标出差异（错词标红）；跟读模式下录音经 ASR 转写后与原文比对标记漏词/错词；每个错误句可选归因（连读没听出/单词不认识/口音问题/注意力断点）入错误库；历史页展示听力正确率曲线；素材无版权问题（AI 生成文本 + edge-tts 预生成音频）。

## 2. 关键决策

| 决策点 | 结论 |
|---|---|
| 素材来源 | **不打包剑桥真题**（版权）。种子 6 篇 AI 风格精听材料（Section 2/3/4 学术场景各 2 篇，每篇 8-12 句，手写文本 + edge-tts 预生成音频） |
| 音频生成 | **逐句生成**（edge-tts 每句一个 mp3，存 `backend/listening_audio/{mat_id}/{idx}.mp3`）——这样单句循环不需要词级时间戳，直接播单句文件；首次打开素材时前端触发后台批量生成，前端轮询就绪进度；生成失败该句显示"音频不可用"，文本练习仍可用 |
| 听写比对 | 后端 API 用 rapidfuzz 做词级 diff（对齐后标注 missing/wrong/extra），返回结构化 diff；连读点不做音频级分析，靠归因标签沉淀 |
| 跟读比对 | 复用 V2 ASR 适配器（讯飞/Mock）转写后跟读录音 → 同一 diff 服务与原文比对 |
| 错题归因 | 前端在 diff 结果句上提供四选一归因按钮；写入 `error_item`（error_type 前缀 `听力:`），复用 V1 错误库与仪表盘 TOP 统计 |
| 正确率 | 听写句级正确率 = 全对句数/总句数（0-100 整数）。`practice.total_band` 直接存正确率（0-100）；历史页按 module 分支渲染——听力曲线 y 轴 0-100 显示 %，写作/口语保持 0-9 分 |
| 能力树 | 听力分支节点种子（`listening.` 前缀约 12 节点），完成一篇精听标黄 |

## 3. 数据模型变更

- `listening_mat` 复用现有表（title/audio_path/transcript JSON），transcript 结构：`["sentence 1", "sentence 2", ...]`（纯句数组，V1 建表时 transcript 是 JSON list 已兼容）
- 不加新表、不加列。`practice`：`module="listening"`、`prompt_title`=素材标题、`content`=用户听写全文（行分隔对应句）、`total_band`=正确率(0-100)、`session_id`=NULL
- `mock_exam` 表继续留空（模考属后续迭代）

## 4. 后端组件

```
backend/app/
├── data/listening_seed.py    6 篇材料文本（title/section/sentences）
├── services/dictation.py     diff_words(reference, hypothesis) -> 词级 diff 结构
│                             score_dictation(sentences, answers) -> {accuracy, per_sentence:[{diff, correct}]}
├── services/listening_tts.py ensure_audio(mat_id, text) -> path|None（edge-tts 懒生成缓存 backend/listening_audio/，gitignored）
├── api/listening.py          听力路由
└── seed_listening.py         seed_listening_db(session)（材料 + 能力树节点，幂等）
```

**rapidfuzz 依赖**：pyproject 加 `rapidfuzz>=3`。

**diff 结构**（词级对齐，前端渲染用）：

```json
{"tokens": [{"type": "ok|missing|wrong|extra", "ref": "original word", "hyp": "user word"}],
 "correct": false}
```

**API**：

```
GET  /api/listening/materials                 [{id, title, section, sentence_count, has_audio}]
GET  /api/listening/materials/{id}            {id, title, section, sentences: [...], ready_count, total}
POST /api/listening/materials/{id}/audio      后台批量生成逐句音频 → {status: "started"|"ready", ready_count, total}
GET  /api/listening/audio/{mat_id}/{idx}.mp3  单句音频（不存在 404）
POST /api/listening/dictation                 {material_id, answers: [str...]} → {accuracy(0-100), per_sentence: [{diff, correct}], practice_id}
POST /api/listening/shadowing                 multipart: material_id + 音频 → 转写 → 与全文比对 → {transcript, diff, is_mock}
POST /api/listening/attribution               {practice_id, sentence_index, reason} → 写 error_item（error_type="听力:连读|词汇|口音|注意力"）
```

**听写评分落库**：创建 `practice`（module=listening, total_band=accuracy）+ `ai_feedback`（bands={"accuracy": x}, annotations=逐句 diff JSON, rewrite=""）。错误归因由用户主动点击（attribution 端点），不自动归类。

## 5. 前端改动

| 页面 | 内容 |
|---|---|
| `ListeningPage`（新，`/listening`） | 素材列表（section 分组 + 正确率历史标记）→ 练习视图：播放器（原生 audio + 句列表，点句单句循环、变速按钮）、三个模式 Tab：逐句字幕对照 / 听写 / 跟读 |
| 听写模式 | 逐句输入框 + 播放该句按钮；全部提交 → 每句 diff 渲染（ok 正常/missing 红虚线/wrong 红底+正确词/extra 删除线）+ 正确率卡 + 每句归因按钮组（四选一） |
| 跟读模式 | 复用 V2 WavRecorder 录音 → 上传 → 转写文本 + 全文 diff + is_mock 徽标 |
| `HistoryPage`（改） | 听力记录 badge；曲线区加模块 Tab（写作分数 / 口语分数 / 听力正确率%），听力 y 轴 0-100 |
| `DashboardPage`（改） | 加听力最新正确率卡；横幅改为"能力树将在后续版本点亮" |
| NavBar | 加"听力"链接 |

## 6. 种子数据

6 篇材料：Section 2（校园导览/课程注册咨询）×2、Section 3（师生论文讨论/小组项目讨论）×2、Section 4（学术讲座：城市农业/海洋保护）×2。每篇 8-12 句，含连读/吞音高发表达（an hour and a half、going to→gonna 类用标准拼写但语速体现）。手写文本。听力能力树节点（`listening.` 前缀 12 节点：精听/跟读/连读识别/数字听写/学术词汇/方位词/同义替换听辨/注意力持续/ Section 2/3/4 策略等）。

## 7. 测试

- `test_dictation.py`：diff_words 各类型（ok/missing/wrong/extra）、score_dictation 正确率计算、全对/全错边界
- `test_listening_api.py`：materials 列表/详情、dictation 提交评分落库（practice + ai_feedback + 正确率）、attribution 写 error_item、shadowing 走 Mock ASR、音频缺失时 unavailable
- 前端无单测，`npm run build` 门槛

## 8. 明确不做（YAGNI）

全真模考、能力树绿态（点亮验证规则）、音频波形图（wavesurfer）、连读音频级分析、真实剑桥音频导入、语速自适应、听力词汇联动复习（V3 联动只覆盖写作/口语批改）。
