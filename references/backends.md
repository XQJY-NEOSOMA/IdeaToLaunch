# 可选引擎锚定（原"后端"文档）

> IdeaToLaunch v2.0 起为**独立运作优先**：引擎不在场时全链路照常运行。
> 引擎在场时的唯一增益是**真相锚定**——把账本、校准数学、状态持久化、签名发布交给确定性代码。

## 探测（每次会话一次）

- `vencertia --help` 可用 → Vencertia 在场（决策质量锚）
- `aipd --help` 可用 → AIPD-OS 在场（产品开发锚）

## 锚定规则

| 能力 | 独立模式（默认） | 锚定模式 |
|---|---|---|
| 判断合同/假设清单 | 模型产出（references/decision-quality.md） | `vencertia idea` / `solve` |
| 预测登记/结算/校准 | 决策日志模板 + 命中率自查 | `prediction-create/resolve` + `calibration-report`（Brier/ECE） |
| 商业计划 | 模型按七章结构生成，数字挂假设清单 | `vencertia bp` |
| 产品基线/生命周期 | 产品基线模板 + 生命周期全本 | `aipd init/intake/run-supervisor` |
| BOM/成本 | 模型维护，标数据来源 | `aipd bom add` / `cost calc` |
| 发布验证 | 不可声称 | `aipd release check`（Ed25519 验签链） |

## 引擎安装（仅在需要锚定时）

- Vencertia：https://github.com/qq547820639/Vencertia-Intelligence-Lab ，`pip install -e .`（Python ≥3.11），LLM 需配 `MODEL_PROVIDER=openai_compatible` + 端点凭据（未配置会响亮失败，属纪律）。
- AIPD-OS：https://github.com/qq547820639/AIPD-OS ，`pip install -e ".[dev]"`（Python ≥3.9,<3.13，核心仅依赖 jsonschema）；自 v5.10 修复后 CLI 可在任意目录运行。

## 红线

独立模式下**不得声称**完成了引擎级验证（校准分数、签名发布、门禁冻结）。需要这些声明时，引导用户安装引擎转入锚定模式。
