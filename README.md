# IdeaToLaunch

**从一句话想法到产品发布的全链路主管技能——完全自包含，开箱即用。**

一个 Agent Skill 包（`SKILL.md` 在根目录），覆盖从创意到发布的完整链路：

```
一句话想法 → 机会验证（市场/竞品/商业模式）→ 决策（判断合同）→ 产品落地（PRD/双轨执行）
          → 发布上市（就绪评审/放行声明）→ 运营复盘（命中率校准）→ 回到机会验证，闭环不断
```

## 设计信条

> **模型负责理解与编排，记录纪律守护真相与账本。**

意图判断、研究分析、流程编排、内容生成、记录维护全部由模型按内建方法论执行——模型越强，主管越强。诚实性由记录纪律守护：预测先登记后结算、结算不可逆、改判只追加更正、每个数字必须挂假设或证据来源。

## 全链路覆盖

| 环节 | 方法论（references/） | 交付模板（templates/） |
|---|---|---|
| 机会验证 | 市场与用户研究 · 竞品分析 · 商业模式与定价 | — |
| 决策 | 决策质量（判断合同/证据分级/ABSTAIN/校准） | 判断合同 |
| 产品落地 | 产品开发生命周期（硬件 S0–S8 + 软件 MVP→GA 双轨） | PRD · 产品基线 · 里程碑路线图 · 风险登记 |
| 发布上市 | 发布与增长（就绪评审/GTM/90 天指标基线） | 发布就绪检查单（含放行声明） |
| 成果交付 | 成果转化引擎（10 内部模块+数据契约+阶段门禁） | 项目简报 → 投资 BP / 深度调研报告 + 可读性/质量报告 |
| 运营复盘 | （决策质量 §校准与复盘） | 决策日志 · 商业计划书 |
| 环节交接 | — | schemas/handoff_v1.json（决策→落地契约） |
| 计算与初始化 | — | scripts/（纯标准库，带自测） |

## 内建脚本工具箱（scripts/，纯 Python 标准库）

| 脚本 | 用途 |
|---|---|
| `init_workspace.py` | 创建项目工作区并初始化法定账本（幂等，绝不覆盖账本） |
| `calc.py` | 单位经济（LTV/CAC/回本期）、TAM 双法交叉、硬件 BOM→零售加成链、校准统计（Brier/ECE，样本不足机械化拒答）——输出含算式回显 |
| `validate_handoff.py` | 按 schema 校验交接包（规则从 schema 读取，单一事实源） |
| `pipeline.py` | 全链路阶段门执行器：逐环节核查出口判据，报告当前门与下一步命令 |
| `assemble_bp.py` | GO 后从账本自动组装 BP 初稿（七章、数字挂账本编号、数据不足如实标注） |
| `selftest.py` | 44 项自测断言 |

## 内置集成的官方技能（vendor/，离线可用）

21 个 Kimi 官方已验证技能以整体搬运方式内置，覆盖全链路：环节 3 产品落地（idea-to-prd/user-story-canvas/iteration-planner/gantt-chart-builder/workload-calculator/software-testing-guide/api-doc-gen）、环节 4 发布上市（compliance-review-planner/tos-clause-scanner/process-doc/lp-proto-gen）、环节 4.5 成果交付（DCF 估值/SaaS 指标/定价/风险热力图/数据图表/报告写作/市场洞察/投资 BP/融资大纲）、环节 5 运营复盘（okr-planner）。注册表、去重记录与职能边界见 `vendor/README.md`。

## 使用

将本仓库放入 agent 的技能目录。用户提出想法/产品/项目类意图时自动启用，按 `SKILL.md` 的全链路地图独立执行。

## 文档

- `docs/architecture.md` — 设计原则与演进
- `docs/chain-evaluation.md` — 全链路能力评估（环节覆盖矩阵与结论）
