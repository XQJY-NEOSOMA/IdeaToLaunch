# 后端引擎：安装、配置与命令面

IdeaToLaunch 编排两个独立引擎。两者保持独立仓库、独立数据库、独立版本线。

## Vencertia（决策质量引擎）

- 仓库：https://github.com/qq547820639/Vencertia-Intelligence-Lab（v2.0.1）
- 安装：`pip install -e .`（Python ≥ 3.11；依赖 pydantic/FastAPI/typer/httpx）
- LLM 配置：`MODEL_PROVIDER=openai_compatible` + 端点凭据；未配置时响亮失败（无静默降级）
- 命令面（以 `vencertia --help` 为准）：

| 任务 | 命令 |
|---|---|
| 想法入口 | `vencertia idea "<文本>" [--json]` |
| 完整求解 | `vencertia solve ...` / `quick-solve ...` |
| 决策编译/评估/敏感度/追踪 | `decision-compile / decision-evaluate / decision-sensitivity / decision-trace` |
| 证据 | `evidence-add / evidence-bind / evidence-import` |
| 研究 | `research-plan / research-run` |
| 实验 | `experiment-propose <decision_id>` |
| 结果登记 | `outcome-record <action_id> <result>` |
| 预测 | `prediction-create / prediction-resolve` |
| 校准 | `calibration-report [--scope ALL]` |
| 商业计划 | `vencertia bp ...` |
| 回归基准 | `benchmark-run --level L0|L1|L2` |

## AIPD-OS（产品开发执行引擎）

- 仓库：https://github.com/qq547820639/AIPD-OS（v5.10）
- 安装：`pip install -e ".[dev]"`（Python ≥3.9,<3.13；核心仅依赖 jsonschema，CAD/图像等为可选 extra）
- 须在源码仓库目录内运行（其 CLI 运行时依赖仓库布局）
- 命令面（以 `aipd --help` 为准，主线 30 个命令）：

| 任务 | 命令（示例） |
|---|---|
| 初始化/想法录入 | `aipd init` / `aipd intake` |
| 推进工作队列 | `aipd run-supervisor` |
| 决策处理 | `aipd submit-decision` |
| 手册/CAD | `aipd manual generate` / `aipd cad preflight` / `aipd cad build` |
| BOM/成本 | `aipd bom add --unit-cost ...` / `aipd cost calc` |
| 工业化/验证 | `aipd industrialize` / `aipd validate` |
| 体检/发布 | `aipd doctor` / `aipd release check` / `aipd package` |

## 健康检查顺序

引擎报"不可用"时先查：① 是否已安装且在当前环境可 import；② 凭据/环境变量；③ AIPD 是否在仓库目录内运行。仍不行则如实告知用户并转入降级模式（SKILL.md「诚实降级」节）。
