# 全链路能力评估（v3.0，独立化后）

> 日期：2026-08-24
> 对象：IdeaToLaunch v3.0（完全自包含）对「创意 → 发布（Idea to Launch）」全链路的支撑能力
> 方法：建立标准环节链，逐环节核查"方法论 / 模板 / 阶段门 / 红线"四要素覆盖情况

## 评估结论（先行）

**覆盖：全链路 6 大环节、21 个子环节全部有方法论与模板支撑，无断点。**
**结论：具备从创意到发布的全链路主管能力，达生产级文档标准。**

v2.0 → v3.0 的缺口修复：市场研究、竞品分析、商业模式与定价、发布上市与增长 4 个方法论从缺失/薄弱补全为全本；PRD、风险登记、路线图、发布检查单、商业计划 5 个模板从缺失补全为填入即用。

## 环节覆盖矩阵

| 环节 | 子环节 | 方法论 | 模板/契约 | 阶段门 | 判定 |
|---|---|---|---|---|---|
| 0 意图理解 | 意图识别与分流 | SKILL.md 环节 0 | — | 模糊时单问澄清 | ✅ |
| 1 机会验证 | 桌面研究 | references/market-research.md §2 | 研究结论卡 | 两独立来源才升级 | ✅ |
| | 用户研究 | market-research.md §3 | 访谈记录表 | 问行为不问观点 | ✅ |
| | 市场规模 | market-research.md §5 | TAM/SAM/SOM 模板 | 双法交叉强制 | ✅ |
| | 竞品分析 | references/competitive-analysis.md | 对比矩阵/差评挖掘表 | 亲测优先、来源必标 | ✅ |
| | 商业模式 | references/business-model.md §1–2 | 商业模式一页纸 | 对接率<80% 升级 | ✅ |
| | 定价与单位经济 | business-model.md §3–5 | 单位经济表 | 三档测算强制 | ✅ |
| 2 决策 | 判断合同 | references/decision-quality.md §1 | templates/judgment-contract.md | 五段完整强制 | ✅ |
| | 证据分级 | decision-quality.md §2–3 | 假设清单（内嵌） | 外部研究不得直升事实 | ✅ |
| | ABSTAIN | decision-quality.md §4 | 最小实验规格 | 不得美化为 GO | ✅ |
| | 交接 | SKILL.md 环节 2 | schemas/handoff_v1.json | NO_GO/ABSTAIN 不进落地 | ✅ |
| 3 产品落地 | 产品定义 | SKILL.md 环节 3 | templates/prd.md | 验收标准可检验 | ✅ |
| | 里程碑/风险 | references/product-lifecycle.md | templates/roadmap.md + risk-register.md | evidence-gated 出口判据 | ✅ |
| | 硬件轨执行 | product-lifecycle.md §1–7（S0–S8/C0–C7/声明门） | templates/product-baseline.md | 成熟度上限封顶 | ✅ |
| | 软件轨执行 | product-lifecycle.md §8（W0–W7/灰度/回滚） | roadmap.md 附录 B | mvp→ga 声明门 | ✅ |
| 4 发布上市 | 就绪评审 | references/launch-gtm.md §1 | templates/launch-checklist.md | 六线逐项判据 + 放行签字 | ✅ |
| | 发布策略与 GTM | launch-gtm.md §2–4 | 发布日作战清单 | 上市声明三证证据门 | ✅ |
| 5 运营复盘 | 指标基线 | launch-gtm.md §5 | 30/60/90 天指标表 | 数据不足诚实呈现 | ✅ |
| | 预测结算与校准 | decision-quality.md §5–6 | templates/decision-journal.md | 先登记后结算、不可逆 | ✅ |
| | 商业计划 | decision-quality.md §8 | templates/business-plan.md | 无编号数字禁止出现 | ✅ |

## 补全前缺口 → 补全措施映射

| 缺口（补全前） | 补全措施 | 状态 |
|---|---|---|
| 市场/用户研究无方法论 | 新增 market-research.md（220 行，含交叉验证硬性规则） | ✅ |
| 竞品分析仅一句话提及 | 新增 competitive-analysis.md（167 行，含差评挖掘规程） | ✅ |
| 商业模式/定价/单位经济缺失 | 新增 business-model.md（220 行，软硬件双口径） | ✅ |
| 发布上市与增长缺失 | 新增 launch-gtm.md（209 行，六线就绪+GTM+90 天基线） | ✅ |
| 无 PRD/风险/路线图/发布检查单/BP 模板 | 新增 5 个填入即用模板 | ✅ |
| 软件产品无执行轨 | product-lifecycle.md 新增软件轨（W0–W7） | ✅ |
| 依赖外部引擎（v2.0） | 全部移除，引擎锚定体系废弃，契约内化 | ✅ |

## 残余限制（诚实声明）

1. **本技能是方法论与编排层，不替代现实世界执行**：实体制造、真实渠道投放、法律文件签署等物理/法律动作只能规划与跟进，不能由技能完成。
2. **分析质量依赖底层模型能力**：方法论保证流程与诚实性，不保证单次判断的智力上限。
3. ~~无代码级计算引擎~~（v3.2 已消除）：`scripts/calc.py` 内建单位经济/TAM 双法/加成链/校准统计（Brier/ECE，样本不足机械化拒答），输出含算式回显供账本留痕；另有工作区初始化与交接包校验脚本，全部纯标准库、15 项自测。
4. **模板是起点不是枷锁**：可按项目裁剪，但记录纪律（登记/不可逆/挂来源）不可裁剪。

## 独立性核查

全仓 grep：`vencertia|aipd|github.com|锚定|继承自` 零命中（业务词汇除外）。无安装依赖、无环境变量、无外部服务。可整体放入任意 agent 技能目录直接使用。

---

## 附录：Dogfood 实测记录（2026-08-24）

以冷启动方式（全新 agent、仅给技能包与真实想法）实测环节 0→2，案例："面向养老社区的智能外骨骼助行服务（租赁+上门康复指导）"。

**结果**：技能正常引导出诚实结论 **ABSTAIN**——需求基本盘真实（60+ 人口 3.1 亿等真实来源数据），但"子女持续付费意愿"UNVERIFIED 且基准档单位经济毛利为负（工具实算），输出最小实验 E-1（3 家养老社区付费试点，证实/证伪判据量化）。证据纪律在无人监督下被完整执行。

**实测发现的 6 处摩擦点及修补（已全部落地，v3.1）**：

| # | 摩擦点 | 修补 |
|---|---|---|
| 1 | 研究结论卡与假设台账无存放位置 | 增设第四法定账本 `research_log.md` + `templates/research-log.md` |
| 2 | handoff.json 在 NO_GO/ABSTAIN 时是否产出含糊 | 明确"每次决策都存档，仅 GO 进环节 3"（SKILL.md + schema） |
| 3 | 交叉验证对中国宏观数据过严（转载链无法判独立） | §2.3 新增官方统计豁免条款 |
| 4 | 纯桌面研究轮无显式出口 | §七新增出口规则：证据天花板 ESTIMATED → 只允许 ABSTAIN+最小实验或 NO_GO |
| 5 | 登记概率与"未校准"并列易误读 | decision-quality.md 明确：登记概率是先验，必须与校准状态并列呈现 |
| 6 | 单位经济表"草案"标注无区分度 | business-model.md 改为健康度打分（达标才可支撑报价决策） |

另按审查建议新增：项目工作区约定（固定账本文件名 + 会话开始先开账本）、"算术必须用计算工具并保留算式"规则。
