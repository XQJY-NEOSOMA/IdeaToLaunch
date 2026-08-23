# IdeaToLaunch

**从一句话想法到产品落地的全链路主管技能。**

一个 Agent Skill 包（`SKILL.md` 在根目录），是 [Vencertia](https://github.com/qq547820639/Vencertia-Intelligence-Lab)（决策质量）与 [AIPD-OS](https://github.com/qq547820639/AIPD-OS)（产品开发执行）两个引擎的**唯一入口**：

```
想法 → Phase 1 决策验证（该不该做）→ Phase 2 产品落地（怎么做）→ Phase 3 复盘回流（做得对不对）→ 回到 Phase 1
```

## 设计信条

> **模型负责理解与编排，规则负责真相与账本。**

意图判断、流程编排、内容生成交给模型——模型越强，主管越强。校准数学、证据分级、预测台账、门禁、签名发布交给两个引擎的确定性代码——不随模型漂移，且模型输出永不允许直接改写这些状态。

## 仓库内容

- `SKILL.md` — 主管行为契约（三阶段主循环 / 升级决策纪律 / 红线）
- `references/decision-quality.md` — 决策质量方法论（判断合同、证据权威分级、ABSTAIN 纪律、校准）
- `references/product-lifecycle.md` — 产品开发生命周期（Product Truth、事实状态、C0–C7 成熟度、升级时刻）
- `references/backends.md` — 两个引擎的安装、配置与命令面速查
- `schemas/handoff_v1.json` — 决策→执行交接契约（版本化 JSON Schema）
- `docs/architecture.md` — 架构论证、不合并的依据、僵化规则降级路线、路线图

## 使用

将本仓库放入 agent 的技能目录。用户提出产品/决策类意图时自动启用，由模型按 SKILL.md 编排两个引擎完成全链路。
