# IdeaToLaunch

**从一句话想法到产品落地的全链路主管技能——开箱即可独立运作。**

一个 Agent Skill 包（`SKILL.md` 在根目录），完全继承 [Vencertia](https://github.com/qq547820639/Vencertia-Intelligence-Lab)（决策质量方法论）与 [AIPD-OS](https://github.com/qq547820639/AIPD-OS)（产品开发方法论）：

```
想法 → Phase 1 决策验证（该不该做）→ Phase 2 产品落地（怎么做）→ Phase 3 复盘回流（做得对不对）→ 循环
```

## 独立运作（v2.0 起）

**无需安装任何后端。** 全部方法论内建于 `references/`，记录文件（判断合同 / 决策日志 / 产品基线）由模型按 `templates/` 直接维护。两个原仓库降级为**可选真相锚**——在场时把账本、校准数学（Brier/ECE）、签名发布锚定到它们的确定性代码；不在场时全链路照常运行，只是不声称引擎级验证。

## 设计信条

> **模型负责理解与编排，规则负责真相与账本。**

意图判断、流程编排、内容生成、记录维护交给模型——模型越强，主管越强。校准数学、证据分级、台账不可逆结算、签名发布这类"真相与账本"职能，引擎在场时交给确定性代码；独立模式下由"先登记后结算、结算不可逆、改判只追加"的记录纪律兜底。

## 仓库内容

- `SKILL.md` — 主管行为契约（双运行模式 / 三阶段主循环 / 升级决策纪律 / 红线）
- `references/decision-quality.md` — 决策质量方法论全本（判断合同、假设状态、证据权威分级、ABSTAIN、校准与复盘）
- `references/product-lifecycle.md` — 产品开发生命周期全本（S0–S8、事实状态、C0–C7 成熟度、声明门、物理世界边界）
- `references/backends.md` — 可选引擎锚定方式
- `templates/` — 判断合同 / 决策日志 / 产品基线
- `schemas/handoff_v1.json` — 决策→执行交接契约（版本化 JSON Schema）
- `docs/architecture.md` — 架构论证与演进路线
- `docs/chain-evaluation.md` — 全链路支撑能力评估（含引擎修复状态）

## 使用

将本仓库放入 agent 的技能目录。用户提出产品/决策类意图时自动启用，按 SKILL.md 独立完成全链路；检测到引擎在场时自动转入锚定模式。
