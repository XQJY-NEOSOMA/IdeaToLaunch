# vendor/ —— 内置技能库说明

这个目录是 IdeaToLaunch 的「内置工具箱」，收纳了 **21 个来自官方、经过验证的专项技能**。它们已经完整打包到本地，**离线即可使用**，不需要联网，也不需要额外安装任何东西。

这份说明面向两类人：想知道「里面装了些什么能力」的使用者，以及需要维护这个技能库的进阶用户。

## 一句话使用原则

这是**按需查阅的资料库**，不是「主动加载的模块」：

- 只有当当前任务确实需要某个专项能力时，才去打开对应的子目录。例如要做 DCF 估值（现金流折现，估算项目现值的方法）就查 `cashflow-valuation/`，要画甘特图就查 `gantt-chart-builder/`。
- 不要在初次学习时通读全部内容，也不要在产出里堆砌多个技能的方法论。
- 当同一主题存在多套方法时，以根目录 `SKILL.md` 的「单一权威表」为准。

> 来源说明：这些技能以「整体搬运、内置集成」的方式并入 Kimi 官方已验证技能库，全部内容已复制到本地，**不依赖外部服务或原技能的在线状态**。每个子目录里都有一份 `VENDOR.json`，记录了它的来源、版本、适用边界、去重说明和依赖。集成日期为 2026-08-24。

---

## 内置技能一览（21 个）

以下按「产品全链路」的环节分组，每项列出它能做什么，以及它的形态（带 Python 脚本 = 可离线计算；纯文档 = 提供方法论）。

### 环节 3 · 产品落地（把想法做成产品）

| 技能目录 | 它能做什么 | 形态 |
|---|---|---|
| `idea-to-prd/` | 把一句话需求，写成完整的产品需求文档（PRD）：用户故事、优先级、验收标准 | 纯文档 |
| `user-story-canvas/` | 生成用户故事地图（可视化 HTML） | 脚本 |
| `iteration-planner/` | 制定迭代（Sprint）计划：范围拆分、依赖、负载均衡 | 纯文档 |
| `gantt-chart-builder/` | 生成交互式甘特图，并标出关键路径（CPM，关键路径法） | 脚本 |
| `workload-calculator/` | 估算工时（PERT / 三点估算法等） | 脚本 |
| `software-testing-guide/` | 软件测试全流程：测试用例、缺陷分级、质量指标（含模板） | 文档+模板 |
| `api-doc-gen/` | 从代码自动生成 API 接口文档 | 脚本 |

### 环节 4 · 发布上市（产品上线）

| 技能目录 | 它能做什么 | 形态 |
|---|---|---|
| `compliance-review-planner/` | 上线前的合规检查清单（数据保护 / 个人信息 / 广告法等） | 纯文档 |
| `tos-clause-scanner/` | 扫描服务条款与隐私政策中的风险点 | 纯文档 |
| `lp-proto-gen/` | 生成产品落地页原型（HTML） | 脚本 |
| `process-doc/` | 编写售后流程 / 标准作业流程（SOP）文档 | 纯文档 |

### 环节 4.5 · 成果交付（出 BP / 报告）

| 技能目录 | 它能做什么 | 形态 |
|---|---|---|
| `cashflow-valuation/` | DCF 现金流折现估值 + 敏感性分析 | 脚本 |
| `saas-metrics-coach/` | SaaS 指标：ARR / MRR / 流失率 / 净收入留存 / LTV / CAC 等 | 脚本 |
| `pricing-strategy/` | 价格弹性分析、定价档位结构推荐 | 脚本 |
| `risk-heatmap/` | 风险登记册校验 + 交互式风险热力图 | 脚本 |
| `data-viz-gen/` | 生成 KPI 卡片、对比柱状图、流程图、仪表盘等图表 | 脚本 |
| `report-writing/` | 长文报告方法论：大纲 → 内容 → 评审 → 引用 | 纯文档 |
| `market-insight-report/` | 咨询风格的市场洞察报告方法论 | 纯文档 |
| `investment-memo/` | 投资分析备忘录（风投式 / 研报式） | 纯文档 |
| `fundraising-bp-planner/` | 融资商业计划书（BP）大纲 + 数据呈现建议 | 纯文档 |

### 环节 5 · 运营复盘

| 技能目录 | 它能做什么 | 形态 |
|---|---|---|
| `okr-planner/` | 制定、拆解和复盘 OKR（目标与关键结果） | 纯文档 |

---

## 为什么有些官方技能没被收录

官方技能库里还有一些技能没有搬进来，原因如下（保留中文版、避免重复、或无法离线运行）：

| 未收录的官方技能 | 原因 |
|---|---|
| `discounted-cashflow-model`、`product-spec-writer`、`sprint-plan-builder`、`regulatory-audit-generator`、`gantt-planner`、`project-sizing-guide`、`test-suite-architect`、`market-research-brief` | 分别是已收录技能（cashflow-valuation / idea-to-prd / iteration-planner / compliance-review-planner / gantt-chart-builder / workload-calculator / software-testing-guide / market-insight-report）的**英文版**，内容重复，统一保留中文版 |
| `investor-pitch-planner` | 与 `fundraising-bp-planner` 职能重合（都是 BP 大纲），保留中文官方版 |
| `chart-gen` | 依赖 Node.js 运行时（需要 `npm install`），**无法离线内置**；其职能已由纯 Python 的 `data-viz-gen` 覆盖 |

---

## 它与主体项目的职责分工

一个关键原则：**vendor 目录只提供「方法」，真正的「标准与契约」以 `templates/` 和 `SKILL.md` 的单一权威表为准。**

具体来说：

- **文档结构以 `templates/` 为准**：多个技能自带的模板、清单、单位口径（如 idea-to-prd 的模板、workload-calculator 的人日口径）不作为最终标准，`templates/` 才是唯一契约。
- **计算核心保留在 `scripts/calc.py`**：通用单位经济（LTV / CAC / 回本期）、市场规模双法交叉、硬件成本加成、命中率校准等，官方技能没有对应能力，故 `calc.py` 保留不动。
- **SaaS 专项分工**：通用单位经济走 `calc.py`；ARR / MRR / 流失率 / 净收入留存等 SaaS 专项指标走 `saas-metrics-coach/`。
- **定价分工**：通用定价方法以 `references/business-model.md` 为准；SaaS 定价档位与提价深化走 `pricing-strategy/`。
- **风险分工**：风险登记册格式以 `templates/risk-register.md` 为数据标准，热力图生成走 `risk-heatmap/`。
- **BP 方法论**：以官方版（investment-memo / fundraising-bp-planner / report-writing）为主体，本体的「数字挂证据、数据不足标注、语言纪律」作为叠加层，不与官方方法重复。
- **产品落地分工**：`templates/prd.md` 是 PRD 的数据格式（可检验判据 + 假设编号），`idea-to-prd/` 是生成方法；`templates/roadmap.md` 是路线图骨架，`gantt-chart-builder/` 负责可视化；生命周期以 `references/product-lifecycle.md` 为准，其余为软件轨道的执行工具；硬件产品的验证阶段（EVT / DVT / PVT）以 product-lifecycle.md 为准。
- **发布分工**：`templates/launch-checklist.md` 是六线放行声明契约；`compliance-review-planner/` 深化合规线、`tos-clause-scanner/` 覆盖法务线、`process-doc/` 覆盖售后、`lp-proto-gen/` 生成落地页。
- **复盘分工**：`okr-planner/` 负责运营期目标管理；决策命中率校准仍以决策日志 + `calc.py` 为准，不替代。

---

## 无法内置的依赖与离线方案

| 依赖 | 影响 | 离线方案 |
|---|---|---|
| chart-gen 需要的 Node.js 运行时 | 无法使用 chart-gen | 已由 `data-viz-gen`（纯 Python）替代，职能覆盖 |
| docx 技能需要的 C# OpenXML 工具链 | 无法直接生成 Word 文件 | 成品保持 Markdown 直出；若运行环境自带 docx 技能，可作最后的格式加速器（非必要） |

---

## 对全部 21 个技能的统一规则

这些规则适用于所有内置技能，且优先级高于各技能文件里的原文：

1. **触发描述仅作存档**：各技能里「当用户提到 X 时触发」的说明不作为加载依据，是否加载只由 IdeaToLaunch 主入口和单一权威表决定。
2. **假设必须如实标注**：任何「基于合理假设 / 快速模式 / 默认值」产出的内容，一律标注为「假设 / 未验证」，并登记到研究日志，不得悄悄当成事实。
3. **英文判定词译成中文**：如 HEALTHY / WATCH / CRITICAL、红黄绿灯、星级、彩色圆点等，面向用户时统一译为「健康 / 及格线边缘 / 不健康」等中文判定词。
4. **无来源数字要标注**：经验法则、基准区间、竞品现价等无来源数字，引用时标注为「估算值」，并注明「引用前须实时核实」。
5. **不可用能力如实降级**：docx / PDF / PPTX / 位图图表等无法生成的能力，按各文件头部的「使用边界」降级处理（改用 Markdown / HTML 图表等），严禁伪造已执行。
6. **研究产物必须回流**：研究和分析的结果必须写回项目的工作区账本，不得只留下零散的临时文件。

---

## 已知注意事项

- **合规清单以数据 / 隐私为中心**：`compliance-review-planner` 的法规表覆盖数据保护、个人信息、广告法等，但**不含实体产品的安全标准**。做实体产品时需自行补查（如纺织品贴肤、玩具年龄边界、皮肤接触、CCC 认证目录等），并标注来源与时效。
- **落地页小瑕疵**：`lp-proto-gen` 在「用户评价」为空时，页面上会留一个空白区块，生成后需人工检查并隐藏空区块。
- **放行声明的机器校验是启发式的**：流水线对「放行声明」的识别基于文件名、关键词和签署行等特征，不会判断六线内容的真伪；签字的真实性由「声明人必须是真人」这条纪律兜底。
