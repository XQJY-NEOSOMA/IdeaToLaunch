# 成果转化链：从决策到商业文档（GO 后自动触发）

> 本文件为 IdeaToLaunch 内建方法论，定义"决策 GO → 投资 BP / 深度调研报告"的自动转化链与多技能协作协议。

## 一、定位与触发

当一个想法通过可行性分析（环节 1-2）且决策为 **GO（干）** 时，自动进入本转化链；用户中途直接要求"出 BP / 出调研报告"时也可手动进入（若未过决策验证，先补环节 1-2）。

**可读性是最终产物，不是附加属性。** 本链的每个环节都以"非专业读者能看懂、能复述、能追问"为验收标准；末端的可读性验收门不过，整个交付不放行。

两条产物线（按用户意图选择，默认 A 线）：
- **A 线 · 投资 BP**（对外：融资、合作汇报）——七章结构（templates/business-plan.md）为骨架；
- **B 线 · 深度调研报告**（对内：决策存档、董事会材料）——研究叙事为主线。

## 二、协作总图与职责边界

**铁律**：IdeaToLaunch 是唯一编排者与真相源——账本（decision_journal / research_log / product_baseline / handoff）与纪律（证据分级、数字挂来源、呈现层契约）由它独占维护；执行技能均为专项工，**不得修改账本**；所有产出数字必须能回溯到账本编号；外部产出与账本冲突时以账本为准并回写修正。

| 阶段 | 职责 | 首选技能（在场自动介入） | 缺席时内建回退 | 输入 → 输出 |
|---|---|---|---|---|
| 0 素材汇集 | 从账本提取结构化素材包 | （内建） | — | 账本 → `deliverable-brief`（见 §三） |
| 1 研究补强 | 多维证据扩展与交叉验证 | `deep-research-swarm` | references/market-research.md 自行补研 | 素材包 → 证据附录 |
| 2 市场成稿素材 | 市场洞察段落（规模/趋势/竞争） | `market-insight-report` 或 `market-research-brief` | market-research.md §五模板 | 证据 → 市场段落初稿 |
| 3 财务建模 | 估值、财务模型、可刷新表格 | `discounted-cashflow-model` 或 `cashflow-valuation`（估值）+ `xlsx`（模型文件） | scripts/calc.py + business-model.md §3 单位经济 | 假设台账 → DCF/单位经济模型 |
| 3a SaaS/定价专项 | SaaS 指标口径、定价页 | `saas-metrics-coach` / `pricing-strategy` | business-model.md §2 | 单位经济 → 定价方案段落 |
| 4 风险深化 | 风险评分、交互热力图、合规 | `risk-heatmap` / `legal-risk-assessment` | templates/risk-register.md | 风险登记 → 风险章节+热力图 |
| 5 长文成稿 | 深度调研报告（B 线） | `report-writing` | references/decision-quality.md §八 BP 七章自行撰写 | 素材+各段初稿 → 报告全文 |
| 5a 投资 BP 成稿（A 线） | 文字 BP / 大纲 / 路演 PPT | `investment-memo`（文字 BP）→ `fundraising-bp-planner` 或 `investor-pitch-planner`（大纲）→ `business-plan-ppt` 或 `kimi-slides`（PPT） | templates/business-plan.md 自行撰写 | 素材 → BP 全文 / PPT |
| 6 图表 | 数据图、信息图 | `chart-gen` / `data-viz-gen` | 文字描述表格替代 | 数据 → PNG/SVG/HTML 图 |
| 7 成品格式 | Word/PDF 交付 | `docx`（默认 Word） | markdown 直出 | 成稿 → .docx |
| 8 可读性验收门 | 盲测评审 + 来源回挂检查 | （内建，见 §四） | — | 成品 → 放行/返工 |

## 三、交接契约：deliverable-brief（素材汇集包）

阶段 0 产出的统一输入，传给后续每个执行技能（模板 `templates/deliverable-brief.md`）。必填内容：判断合同全文、假设台账（含状态与编号）、单位经济三档、TAM/SAM/SOM 双法表、最小实验及其结果（如有）、风险登记、关键数据及来源清单。**规则：素材包之外的数字不得进入成稿；每个数字标注其账本编号。**

## 四、可读性验收门（末端的放行判据）

成稿后、交付前，必须过两道检查：

1. **盲测评审**：以"聪明但非专业的读者"视角审读成品，按三问验收——
   - 能否一句话复述这个生意是做什么的、为什么值得投/做？
   - 能否说出最大的风险和最不确定的假设？
   - 能否找到每个关键数字的来源标注？
   评分门槛：结论清晰度 ≥8/10；低于门槛定位到章节返工重写（不是加术语解释，而是用大白话重写）。
2. **回挂检查**：成稿中每个数字都能点回素材包编号（H-xx/R-xx/算式编号）；出现素材包之外的数字 → 该段落退回，先补账本再成稿。

## 五、协作流程（一次完整 A 线示例）

1. 决策 GO 存档后，编排者生成 deliverable-brief；
2. 若需补强证据：调 `deep-research-swarm`，产出并入 research_log.md（先更新账本，再进素材包）；
3. 调财务技能建模型：假设台账三档 → DCF/单位经济，`xlsx` 产出可刷新模型文件附于交付包；
4. 调 `risk-heatmap` 深化风险登记并生成热力图；
5. 调 `investment-memo` 成稿（或先 `fundraising-bp-planner` 出大纲再成稿），`chart-gen` 配图；
6. 需要路演版时：调 `business-plan-ppt` 或 `kimi-slides` 产 PPT；
7. 调 `docx` 输出 Word 成品；
8. 过可读性验收门 → 放行交付；全链路产物与账本一并归档到项目工作区 `deliverables/` 子目录。

**编排纪律**：每个执行技能调用前，向其传递 deliverable-brief + 该阶段的呈现层语言纪律（大白话、来源就近标注、判定词中文）；调用后检查产出是否守住纪律，未守住当场返工——编排者对最终可读性负全责。
