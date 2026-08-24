# vendor/ — 内置集成的官方技能注册表

> 本目录以"整体搬运/内置集成"方式并入 Kimi 官方已验证技能。全部内容（提示词、脚本、知识数据、示例、校验用例）已完整复制到本地，**离线独立运行，不依赖外部服务或原技能在线状态**。
> 每个子目录含 `VENDOR.json`（来源/版本/适用边界/去重说明/依赖）。
> 集成日期：2026-08-24（首批 9 个，v3.6）+ 2026-08-24（第二批 12 个，v3.8，补齐环节 3/4/5）。来源：`/app/.agents/skills/`（Kimi 官方技能库）。

## 注册表

| 子目录 | 接入模块（成果转化引擎） | 职能 | 依赖 | 冒烟回归 |
|---|---|---|---|---|
| `cashflow-valuation/` | 模块 5 财务建模 | DCF 估值 + 增长×折现率敏感性矩阵（`scripts/dcf_model.py`，JSON/CLI） | 纯标准库 | ✅ 实算通过 |
| `saas-metrics-coach/` | 模块 3/5 SaaS 专项 | ARR/MRR/churn/NRR/LTV/CAC/quick ratio 三脚本 + 公式与基准库 | 纯标准库 | ✅ 实算通过（缺输入时诚实报 `_missing`） |
| `pricing-strategy/` | 模块 4 定价专项 | 价格弹性分析、档位结构推荐（`scripts/pricing_modeler.py`）+ 定价知识库 | 纯标准库 | ✅ 实算通过 |
| `risk-heatmap/` | 模块 6 风险评估 | 风险登记册校验 + 交互热力图 HTML（`scripts/generate_risk_heatmap.py`） | 纯标准库 | ✅ 实算通过（输入需 `id/name/probability/impact` 字段） |
| `data-viz-gen/` | 模块 3 数据图表 | KPI 卡/对比柱状/流程图/仪表盘 HTML（`scripts/build_infographic.py`） | 纯标准库 | ✅ 实算通过 |
| `report-writing/` | 模块 7（B 线） | 长文报告方法论：大纲→内容→评审→引用 + 四种风格模板 | 纯文档 | ✅ 结构核查 |
| `market-insight-report/` | 模块 2 成稿 | 咨询风格市场洞察报告方法论 + 分析框架/结构/图表/风格契约 | 纯文档 | ✅ 结构核查 |
| `investment-memo/` | 模块 7（A 线） | 投资分析备忘录方法论（风投式/研报式两种格式） | 纯文档 | ✅ 结构核查 |
| `fundraising-bp-planner/` | 模块 7（A 线） | 融资 BP 六模块大纲 + 数据呈现建议 | 纯文档 | ✅ 结构核查 |
| `idea-to-prd/` | 环节 3 产品定义 | 一句话需求 → 完整 PRD 方法论（用户故事/MoSCoW/验收标准） | 纯文档 | ✅ 结构核查 |
| `user-story-canvas/` | 环节 3 用户故事 | 用户故事地图 HTML（`scripts/generate_story_map.py`） | 纯标准库 | ✅ 冒烟通过 |
| `iteration-planner/` | 环节 3 软件轨 | Sprint 范围/拆点/依赖/负载均衡计划 | 纯文档 | ✅ 结构核查 |
| `gantt-chart-builder/` | 环节 3 里程碑 | 交互甘特图 + CPM 关键路径（`scripts/gantt_generator.py`） | 纯标准库 | ✅ 实算通过 |
| `workload-calculator/` | 环节 3 工时估算 | PERT/T-shirt/FPA 三点估算（`scripts/estimate_calculator.py`） | 纯标准库 | ✅ 实算通过（字段契约 name/O/M/P） |
| `software-testing-guide/` | 环节 3 验证测试 | QA 流程/测试用例/缺陷 P0-P4/质量指标/OWASP（11 文件含模板） | 纯文档+模板 | ✅ 结构核查 |
| `api-doc-gen/` | 环节 3 软件轨 | 从代码生成 API 文档（`scripts/generate_api_doc.py`，ast 解析） | 纯标准库 | ✅ 冒烟通过 |
| `compliance-review-planner/` | 环节 4 合规线 | 上线前合规检查清单（GDPR/个保法/广告法/数安法） | 纯文档 | ✅ 结构核查 |
| `tos-clause-scanner/` | 环节 4 法务线 | 服务条款风险扫描（ToS/隐私政策） | 纯文档 | ✅ 结构核查 |
| `lp-proto-gen/` | 环节 4 GTM 资产 | 产品落地页 HTML 原型（`scripts/generate_landing_page.py`） | 纯标准库 | ✅ 冒烟通过 |
| `process-doc/` | 环节 4 售后线 | SOP/RACI/流程文档方法论 | 纯文档 | ✅ 结构核查 |
| `okr-planner/` | 环节 5 运营目标 | OKR 制定/拆解/复盘教练 | 纯文档 | ✅ 结构核查 |

## 去重记录（未搬运及理由）

| 官方技能 | 处置 | 理由 |
|---|---|---|
| discounted-cashflow-model | 不搬运 | 与 cashflow-valuation 脚本逐字节相同，为其英文版；保留中文版 |
| market-research-brief | 不搬运 | market-insight-report 的英文版；保留中文版 |
| investor-pitch-planner | 不搬运 | 与 fundraising-bp-planner 职能重合（BP 大纲）；保留中文官方版 |
| chart-gen | 不搬运 | 依赖 Node.js 运行时（chart.mjs + npm install），无法离线内置；职能由 data-viz-gen（纯 Python）覆盖 |
| product-spec-writer | 不搬运 | idea-to-prd 的英文版；保留中文版 |
| sprint-plan-builder | 不搬运 | iteration-planner 的英文版；保留中文版 |
| regulatory-audit-generator | 不搬运 | compliance-review-planner 的英文版；保留中文版 |
| gantt-planner | 不搬运 | gantt-chart-builder 的英文版；保留中文版 |
| project-sizing-guide | 不搬运 | workload-calculator 的英文版；保留中文版 |
| test-suite-architect | 不搬运 | software-testing-guide 的英文版；保留中文版 |

## 与本体的职能边界（防重复实现）

- **`scripts/calc.py` 保留不动**：承载账本纪律（算式回显进 research_log）、TAM 双法、硬件加成链、校准统计——官方技能无对应能力。
- **SaaS 专项指标分工**：通用单位经济（LTV/CAC/回本期）仍走 calc.py；ARR/MRR/churn/NRR/quick ratio 等 SaaS 专项走 `saas-metrics-coach/` 三脚本。
- **定价分工**：通用定价方法论以 `references/business-model.md` 为准；SaaS 定价页/档位/提价深化走 `pricing-strategy/`。
- **风险分工**：风险登记册格式以 `templates/risk-register.md` 为数据契约（R-xx 编号映射为官方脚本的 id/name 字段）；热力图生成走 `risk-heatmap/`。
- **BP 方法论**：以官方版（investment-memo/fundraising-bp-planner/report-writing）为主体；本体的"数字挂账本编号、数据不足标注、呈现层语言纪律"作为集成覆盖层，不与官方方法论重复。
- **环节 3 分工（v3.8 新增）**：`templates/prd.md` 保留为 PRD 数据契约格式（可检验判据+假设编号纪律），`idea-to-prd/` 为生成方法论；`templates/roadmap.md` 保留双轨骨架与出口判据，`gantt-chart-builder/` 负责可视化与 CPM；生命周期主权在 `references/product-lifecycle.md`，`iteration-planner/`、`workload-calculator/`、`software-testing-guide/`、`api-doc-gen/` 为软件轨 W2–W5 阶段执行工具；硬件 EVT/DVT/PVT 仍以 product-lifecycle.md 为准，software-testing-guide 仅覆盖软件 QA。
- **环节 4 分工（v3.8 新增）**：`templates/launch-checklist.md` 保留六线放行声明契约；`compliance-review-planner/` 深化合规线、`tos-clause-scanner/` 覆盖法务线、`process-doc/` 覆盖售后 SOP、`lp-proto-gen/` 生成 GTM 落地页原型。
- **环节 5 分工（v3.8 新增）**：`okr-planner/` 承担运营期目标管理；决策校准仍以 decision_journal + calc.py 为准，不替代。

## 无法内置的依赖与离线方案

| 依赖 | 影响 | 离线方案 |
|---|---|---|
| chart-gen 的 Node.js 运行时 | 无法使用 chart-gen | 已由 data-viz-gen（纯 Python）替代，职能覆盖 |
| docx 技能的 C# OpenXML 工具链 | 无法内置 Word 生成 | 成品保持 Markdown 直出；运行环境若自带 docx 技能可作模块 7 后段的格式加速器（非架构组成） |
