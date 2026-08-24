#!/usr/bin/env python3
"""集中自测（IdeaToLaunch 技能 scripts/ 工具箱）。

以子进程方式真实调用 scripts/ 下各 CLI，做正确性断言：
    - calc.py unit-economics：手算对照（gross_margin / churn_rate / cogs / initial_cost 四条路径）
    - calc.py calibration：Brier 手算对照、n<20 时绝不输出 Brier/ECE 数字
    - calc.py tam / price-chain：手算对照与双法交叉判定；bottomup 因子链与旧形式兼容
    - calc.py expr：白名单算术正常计算、注入与变量名一律拒绝（退出码 2）
    - validate_handoff.py：合法样本通过、非法样本逐条报错
    - init_workspace.py：幂等性、handoff.json 骨架过契约校验、模板「（模板）」标记去除、
      --with-contract 生效
    - pipeline.py：空工作区全 fail/pending；环节 0-2 完成后前三环 pass；环节 3 在
      GO/ABSTAIN 两种 handoff 下的不同表现；环节 5 已结算预测驱动命中率自查判据

用法：python3 scripts/selftest.py
退出码：0 全部通过；1 存在失败断言。
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent

PASS_COUNT = 0
FAIL_COUNT = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    """记录一条断言结果；失败时输出可操作细节。"""
    global PASS_COUNT, FAIL_COUNT
    if condition:
        PASS_COUNT += 1
        print(f"  PASS  {label}")
    else:
        FAIL_COUNT += 1
        print(f"  FAIL  {label}" + (f"  —— {detail}" if detail else ""))


def run(script: str, *args: str):
    """以子进程运行脚本，返回 (退出码, stdout 解析后的 JSON 或 None, stderr)。"""
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script), *args],
        capture_output=True,
        text=True,
    )
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        out = None
    return proc.returncode, out, proc.stderr


def close(a: float, b: float, tol: float = 1e-3) -> bool:
    return abs(a - b) <= tol


# ---------------------------------------------------------------------------
# calc.py unit-economics
# ---------------------------------------------------------------------------

def test_unit_economics() -> None:
    print("[calc.py unit-economics]")
    # 手算对照：月毛利=100×0.8=80；LTV=80×10=800；LTV/CAC=800/150≈5.3333；回本=150/80=1.875 → healthy
    code, out, err = run(
        "calc.py", "unit-economics",
        "--json", '{"price": 100, "cac": 150, "gross_margin": 0.8, "lifespan_months": 10}',
    )
    ok = (
        code == 0 and out is not None
        and close(out["monthly_gross_profit"], 80)
        and close(out["ltv"], 800)
        and close(out["ltv_cac_ratio"], 800 / 150)
        and close(out["payback_months"], 1.875)
        and out["verdict"] == "healthy"
    )
    check("手算对照：gross_margin 路径（LTV=800, ratio≈5.333, 回本=1.875, healthy）", ok,
          f"code={code} out={out} err={err}")

    # churn_rate 路径：lifespan = 1/0.1 = 10，结果应与上面一致
    code, out, err = run(
        "calc.py", "unit-economics",
        "--json", '{"price": 100, "cac": 150, "gross_margin": 0.8, "churn_rate": 0.1}',
    )
    ok = code == 0 and out is not None and close(out["lifespan_months"], 10) and close(out["ltv"], 800)
    check("churn_rate 路径：lifespan=1/0.1=10，LTV=800", ok, f"code={code} out={out} err={err}")

    # cogs 路径：毛利率 = (100−30)/100 = 0.7
    code, out, err = run(
        "calc.py", "unit-economics",
        "--json", '{"price": 100, "cac": 100, "cogs": 30, "lifespan_months": 6}',
    )
    ok = code == 0 and out is not None and close(out["gross_margin"], 0.7) and close(out["ltv"], 420)
    check("cogs 路径：毛利率=0.7，LTV=70×6=420", ok, f"code={code} out={out} err={err}")

    # initial_cost：月毛利=30，LTV=150−20=130，ratio=1.3，回本=(100+20)/30=4 → marginal
    code, out, err = run(
        "calc.py", "unit-economics",
        "--json", '{"price": 50, "cac": 100, "gross_margin": 0.6, "lifespan_months": 5, "initial_cost": 20}',
    )
    ok = (
        code == 0 and out is not None
        and close(out["ltv"], 130)
        and close(out["ltv_cac_ratio"], 1.3)
        and close(out["payback_months"], 4)
        and out["verdict"] == "marginal"
    )
    check("initial_cost 路径：LTV=130, ratio=1.3, 回本=4, marginal", ok, f"code={code} out={out} err={err}")

    # 回本期口径标注：formulas 与 verdict_rule 均注明含 initial_cost 首投及出处
    ok = (
        out is not None
        and "business-model.md §3.1" in json.dumps(out["formulas"], ensure_ascii=False)
        and "回本期含 initial_cost 首投" in out["verdict_rule"]
    )
    check("回本期口径标注：方法论 references/business-model.md §3.1 可互查", ok,
          f"out={out}")

    # 纪律：lifespan_months 与 churn_rate 同时给必须报错（退出码 2）
    code, out, err = run(
        "calc.py", "unit-economics",
        "--json", '{"price": 100, "cac": 150, "gross_margin": 0.8, "lifespan_months": 10, "churn_rate": 0.1}',
    )
    check("lifespan_months 与 churn_rate 同时给出 → 报错退出码 2",
          code == 2 and "二选一" in err, f"code={code} err={err}")


# ---------------------------------------------------------------------------
# calc.py calibration
# ---------------------------------------------------------------------------

def test_calibration() -> None:
    print("[calc.py calibration]")
    # n=3 < 20：status=UNCALIBRATED，且输出中不得出现 brier/ece 数字
    code, out, err = run(
        "calc.py", "calibration",
        "--json", '{"predictions": [{"probability": 0.9, "outcome": true}, '
                  '{"probability": 0.8, "outcome": false}, {"probability": 0.6, "outcome": true}]}',
    )
    ok = (
        code == 0 and out is not None
        and out["status"] == "UNCALIBRATED"
        and "brier" not in out and "ece" not in out and "buckets" not in out
    )
    check("n<20 → UNCALIBRATED 且不输出 Brier/ECE 数字", ok, f"code={code} out={out} err={err}")

    # 手算对照：20 条 p=0.7，14 真 6 假
    # Brier = (14×0.3² + 6×0.7²)/20 = (1.26 + 2.94)/20 = 0.21
    # 全部落在同一桶，桶内平均置信度 0.7 = 命中率 14/20=0.7 → ECE = 0
    preds = [{"probability": 0.7, "outcome": True}] * 14 + [{"probability": 0.7, "outcome": False}] * 6
    code, out, err = run("calc.py", "calibration", "--json", json.dumps({"predictions": preds}))
    ok = (
        code == 0 and out is not None
        and out["status"] == "OK"
        and close(out["brier"], 0.21)
        and close(out["ece"], 0.0)
        and len(out["buckets"]) == 1
        and out["buckets"][0]["count"] == 20
    )
    check("手算对照：n=20, Brier=0.21, ECE=0（单桶 0.7 vs 14/20）", ok,
          f"code={code} out={out} err={err}")


# ---------------------------------------------------------------------------
# calc.py tam / price-chain
# ---------------------------------------------------------------------------

def test_tam_and_price_chain() -> None:
    print("[calc.py tam]")
    # 手算：自顶向下 1e9×0.5×0.2=1e8；自底向上 10000×0.1×1000=1e6；比值 100 → fail
    code, out, err = run(
        "calc.py", "tam",
        "--json", '{"topdown": {"base_market": 1000000000, "unit": "元", "factors": ['
                  '{"name": "目标细分", "value": 0.5, "source": "行业报告"}, '
                  '{"name": "可服务比例", "value": 0.2, "source": "假设 H-03"}]}, '
                  '"bottomup": {"customers": 10000, "penetration": 0.1, "arpu": 1000}}',
    )
    ok = (
        code == 0 and out is not None
        and close(out["topdown_result"], 1e8)
        and close(out["bottomup_result"], 1e6)
        and close(out["magnitude_ratio"], 100)
        and out["status"].startswith("fail")
    )
    check("手算对照：1e8 vs 1e6，比值 100 → fail", ok, f"code={code} out={out} err={err}")

    # 比值恰为 10（区间边界）→ pass
    code, out, err = run(
        "calc.py", "tam",
        "--json", '{"topdown": {"base_market": 1000000000, "factors": [{"name": "细分", "value": 0.5, "source": "s"}, '
                  '{"name": "渗透", "value": 0.2, "source": "s"}]}, '
                  '"bottomup": {"customers": 100000, "penetration": 0.1, "arpu": 1000}}',
    )
    ok = code == 0 and out is not None and close(out["magnitude_ratio"], 10) and out["status"] == "pass"
    check("边界：比值 10 → pass（区间含端点）", ok, f"code={code} out={out} err={err}")

    # bottomup 因子链（新形式）：2127×10×0.05×9600 = 10,209,600，算式回显带 name 与 source
    code, out, err = run(
        "calc.py", "tam",
        "--json", '{"topdown": {"base_market": 10209600, "factors": [{"name": "细分", "value": 1.0, "source": "s"}]}, '
                  '"bottomup": {"factors": ['
                  '{"name": "园区数", "value": 2127, "source": "中物联2024"}, '
                  '{"name": "每园区站点数", "value": 10, "source": "ASSUMED"}, '
                  '{"name": "渗透率", "value": 0.05, "source": "ASSUMED"}, '
                  '{"name": "ARPU", "value": 9600, "source": "ASSUMED"}]}}',
    )
    formulas_text = json.dumps(out["formulas"], ensure_ascii=False) if out else ""
    ok = (
        code == 0 and out is not None
        and close(out["bottomup_result"], 2127 * 10 * 0.05 * 9600)
        and out["status"] == "pass"
        and "园区数" in formulas_text and "中物联2024" in formulas_text
        and "ARPU" in formulas_text and "ASSUMED" in formulas_text
    )
    check("bottomup 因子链：连乘=10209600，回显带每个因子的 name 与 source", ok,
          f"code={code} out={out} err={err}")

    # 旧形式与新形式同时给出 → 口径冲突报错（退出码 2）
    code, out, err = run(
        "calc.py", "tam",
        "--json", '{"topdown": {"base_market": 100}, '
                  '"bottomup": {"customers": 100, "penetration": 0.1, "arpu": 10, '
                  '"factors": [{"name": "x", "value": 2, "source": "s"}]}}',
    )
    check("bottomup 新旧两形式同时给出 → 报错退出码 2", code == 2 and "二选一" in err,
          f"code={code} err={err}")

    print("[calc.py price-chain]")
    # 手算：出厂=100×1.05=105；准备金=105×0.05=5.25；含税=110.25/0.87≈126.7241；零售=126.7241/0.8≈158.4052
    code, out, err = run(
        "calc.py", "price-chain",
        "--json", '{"bom_cost": 100, "loss_rate": 0.05, "warranty_rate": 0.05, '
                  '"tax_rate": 0.13, "channel_margin": 0.2}',
    )
    ok = (
        code == 0 and out is not None
        and close(out["ex_factory"], 105)
        and close(out["retail"], 110.25 / 0.87 / 0.8)
        and len(out["steps"]) == 4
        and close(out["retail_to_bom_ratio"], 110.25 / 0.87 / 0.8 / 100)
    )
    check("手算对照：出厂=105，零售≈158.4052，四环算式齐全", ok, f"code={code} out={out} err={err}")


# ---------------------------------------------------------------------------
# calc.py expr（白名单表达式）
# ---------------------------------------------------------------------------

def test_expr() -> None:
    print("[calc.py expr]")
    # 正常计算：50×80×12 = 48000，formula 可直接粘进算式附录
    code, out, err = run(
        "calc.py", "expr",
        "--json", '{"expression": "50*80*12", "note": "ARPU=50人×80元×12月"}',
    )
    ok = (
        code == 0 and out is not None
        and out["result"] == 48000
        and out["formula"] == "50*80*12 = 48000"
        and out["note"] == "ARPU=50人×80元×12月"
    )
    check("手算对照：50*80*12=48000，formula 回显可粘贴", ok, f"code={code} out={out} err={err}")

    # 括号 / 一元负号 / 幂均在白名单内：-(2+3)**2 = -25
    code, out, err = run("calc.py", "expr", "--json", '{"expression": "-(2+3)**2"}')
    ok = code == 0 and out is not None and out["result"] == -25
    check("括号 + 一元负号 + ** ：-(2+3)**2 = -25", ok, f"code={code} out={out} err={err}")

    # 注入拒绝：函数调用
    code, out, err = run("calc.py", "expr", "--json", '{"expression": "__import__(\\"os\\")"}')
    check("注入拒绝：__import__(\"os\") → 报错退出码 2", code == 2 and "error" in err,
          f"code={code} err={err}")

    # 注入拒绝：字母变量名
    code, out, err = run("calc.py", "expr", "--json", '{"expression": "a+b"}')
    check("注入拒绝：字母变量 a+b → 报错退出码 2", code == 2 and "error" in err,
          f"code={code} err={err}")

    # 注入拒绝：属性访问
    code, out, err = run("calc.py", "expr", "--json", '{"expression": "(1).bit_length()"}')
    check("注入拒绝：属性/调用 (1).bit_length() → 报错退出码 2", code == 2 and "error" in err,
          f"code={code} err={err}")


# ---------------------------------------------------------------------------
# validate_handoff.py
# ---------------------------------------------------------------------------

VALID_HANDOFF = {
    "contract_version": "1.0",
    "project": {"name": "示例项目", "decision_log_ref": "decision_journal.md#1"},
    "decision_question": "是否进入产品落地环节？",
    "recommendation": "GO",
    "confidence": None,
    "judgment_contract": {"current_judgment": "值得做", "next_step": "完成 PRD"},
    "key_assumptions": [
        {"statement": "目标用户愿意月付 100 元", "status": "ASSUMED", "evidence_refs": ["H-01"]},
        {"statement": "月流失率 ≤ 10%", "status": "ESTIMATED"},
    ],
    "critical_uncertainties": ["真实转化率未知"],
    "constraints": ["预算 ≤ 50 万"],
    "residual_risks": ["供应链延期"],
}

INVALID_HANDOFF = {
    "contract_version": "2.0",               # 违反 const "1.0"
    "project": {"name": "示例项目"},
    # 缺 decision_question
    "recommendation": "MAYBE",               # 非法枚举
    "confidence": 1.5,                       # 超出 [0,1]
    "key_assumptions": [{"statement": "x", "status": "PROBABLY"}],  # 非法 status 枚举
    "critical_uncertainties": ["u"],
    "extra_field": "不应存在",                # 违反 additionalProperties:false
}


def test_validate_handoff() -> None:
    print("[validate_handoff.py]")
    with tempfile.TemporaryDirectory() as tmp:
        valid_path = Path(tmp) / "valid.json"
        invalid_path = Path(tmp) / "invalid.json"
        valid_path.write_text(json.dumps(VALID_HANDOFF, ensure_ascii=False), encoding="utf-8")
        invalid_path.write_text(json.dumps(INVALID_HANDOFF, ensure_ascii=False), encoding="utf-8")

        code, out, err = run("validate_handoff.py", str(valid_path))
        check("合法样本 → valid=true，退出码 0",
              code == 0 and out is not None and out["valid"] is True and out["errors"] == [],
              f"code={code} out={out} err={err}")

        code, out, err = run("validate_handoff.py", str(invalid_path))
        errors_text = json.dumps(out["errors"], ensure_ascii=False) if out else ""
        ok = (
            code == 1 and out is not None and out["valid"] is False
            and "contract_version" in errors_text      # const 违例
            and "decision_question" in errors_text     # 缺必填字段
            and "recommendation" in errors_text        # 枚举违例
            and "confidence" in errors_text            # 范围违例
            and "PROBABLY" in errors_text              # status 枚举违例
            and "extra_field" in errors_text           # 未知字段被拒
        )
        check("非法样本 → valid=false，退出码 1，六类错误全部检出", ok,
              f"code={code} out={out} err={err}")


# ---------------------------------------------------------------------------
# init_workspace.py
# ---------------------------------------------------------------------------

def test_init_workspace() -> None:
    print("[init_workspace.py]")
    with tempfile.TemporaryDirectory() as tmp:
        # 首次运行：创建两个账本 + handoff.json 骨架
        code, out, err = run("init_workspace.py", "演示项目", "--date", "20250131", "--dir", tmp)
        ws = Path(tmp) / "演示项目-20250131"
        ok = (
            code == 0 and out is not None
            and ws.is_dir()
            and len(out["created"]) == 3 and out["skipped"] == []
            and (ws / "decision_journal.md").is_file()
            and (ws / "research_log.md").is_file()
            and (ws / "handoff.json").is_file()
        )
        check("首次运行：创建工作区并生成两个账本 + handoff.json 骨架", ok,
              f"code={code} out={out} err={err}")

        # handoff.json 骨架必须能被 validate_handoff.py 通过
        code, out, err = run("validate_handoff.py", str(ws / "handoff.json"))
        ok = code == 0 and out is not None and out["valid"] is True and out["errors"] == []
        check("handoff.json 骨架被 validate_handoff.py 通过（valid=true）", ok,
              f"code={code} out={out} err={err}")

        # 骨架占位标记：ABSTAIN + 待填写决策问题 + confidence=null
        skeleton = json.loads((ws / "handoff.json").read_text(encoding="utf-8"))
        ok = (
            skeleton["recommendation"] == "ABSTAIN"
            and "待填写" in skeleton["decision_question"]
            and skeleton["confidence"] is None
            and skeleton["project"]["name"] == "演示项目"
            and skeleton["key_assumptions"] == []
            and skeleton["critical_uncertainties"] == []
        )
        check("骨架占位：ABSTAIN / 待填写标记 / confidence=null / 空假设清单", ok,
              f"skeleton={skeleton}")

        # 模板首行「（模板）」标记已去除，其余内容字节不变
        journal_text = (ws / "decision_journal.md").read_text(encoding="utf-8")
        template_text = (SCRIPTS_DIR.parent / "templates" / "decision-journal.md").read_text(encoding="utf-8")
        t_first, _, t_rest = template_text.partition("\n")
        j_first, _, j_rest = journal_text.partition("\n")
        ok = (
            "（模板）" in t_first
            and "（模板）" not in j_first
            and j_rest == t_rest
        )
        check("模板首行「（模板）」标记已去除，其余内容字节不变", ok,
              f"模板首行={t_first!r} 账本首行={j_first!r}")

        # 篡改账本内容，验证二次运行绝不覆盖（幂等 + 账本纪律）
        marker = "手工登记的预测，不可被工具覆盖"
        journal = ws / "decision_journal.md"
        journal.write_text(marker, encoding="utf-8")

        code, out, err = run("init_workspace.py", "演示项目", "--date", "20250131", "--dir", tmp)
        ok = (
            code == 0 and out is not None
            and out["created"] == [] and len(out["skipped"]) == 3
            and journal.read_text(encoding="utf-8") == marker
        )
        check("二次运行：全部跳过，已有账本内容原样保留（幂等）", ok,
              f"code={code} out={out} err={err}")

        # --with-contract：生成 judgment_contract.md，且首行「（模板）」同样去除
        code, out, err = run(
            "init_workspace.py", "演示项目", "--date", "20250131", "--dir", tmp, "--with-contract",
        )
        contract = ws / "judgment_contract.md"
        ok = (
            code == 0 and out is not None
            and str(contract) in out["created"]
            and contract.is_file()
            and "（模板）" not in contract.read_text(encoding="utf-8").partition("\n")[0]
        )
        check("--with-contract：生成 judgment_contract.md 且去除「（模板）」", ok,
              f"code={code} out={out} err={err}")

        # --with-contract 幂等：二次运行跳过，不覆盖
        code, out, err = run(
            "init_workspace.py", "演示项目", "--date", "20250131", "--dir", tmp, "--with-contract",
        )
        ok = code == 0 and out is not None and out["created"] == [] and len(out["skipped"]) == 4
        check("--with-contract 二次运行：全部跳过（幂等）", ok, f"code={code} out={out} err={err}")

        # --date 格式校验
        code, out, err = run("init_workspace.py", "演示项目", "--date", "2025-01-31", "--dir", tmp)
        check("非法 --date 格式 → 报错退出码 2", code == 2 and "YYYYMMDD" in err,
              f"code={code} err={err}")


# ---------------------------------------------------------------------------
# assemble_bp.py
# ---------------------------------------------------------------------------

GO_HANDOFF = {
    "contract_version": "1.0",
    "project": {"name": "演示项目", "decision_log_ref": "decision_journal.md#1"},
    "decision_question": "是否进入产品落地环节？",
    "recommendation": "GO",
    "confidence": None,
    "judgment_contract": {
        "current_judgment": "值得做：细分市场有真实付费意愿",
        "what_would_change_my_mind": "内测 90 天付费率 <2%",
        "next_step": "进入环节3：完成 PRD 与 MVP 里程碑",
        "biggest_unknown": "真实转化率未知",
    },
    "key_assumptions": [
        {"statement": "目标用户愿意月付 100 元", "status": "ASSUMED", "evidence_refs": ["H-01"]},
        {"statement": "目标用户愿意月付 100 元（真实付费率未验证）", "status": "UNVERIFIED"},
    ],
    "critical_uncertainties": ["真实转化率未知"],
    "constraints": ["预算 ≤ 50 万", "真人测试前须升级用户确认（技能'何时问用户'纪律）",
                    "结构方案硬约束：后入式半包围——后方完全开放、驾驶员从正后方步入"],
}

RESEARCH_LOG = """# 研究日志

## 一、研究结论卡

【研究结论卡】
结论：2025 年目标细分市场规模约 120 亿元/年，年增速 15%
对应假设：H-01
证据等级：ESTIMATED
证据类型：桌面研究
来源：某行业年度报告
时效：2025 年数据，2025-01 采集

## 二、假设台账

| 编号 | 假设内容 | 数值/口径 | 状态 | 来源/依据 | 关联结论卡 | 复核日期 |
|---|---|---|---|---|---|---|
| H-01 | 目标用户愿意月付 100 元 | 100 元/月 | ASSUMED | 访谈 3 人 | R-01 | |

## 五、算式附录

- 2025-01-30 PERT 三点估算（工具：scripts/calc.py expr）：输入 3 个工作包 O/M/P（设计 2/3/5、开发 5/8/14、测试 1/2/4，单位人日），JSON 存档于 estimate.txt。结果：ΣE=18.50 人日，90% 置信区间 15.00–22.00 人日。
50*80*12 = 48000（ARPU 估算，2025-01）
"""

DECISION_JOURNAL = """# 决策日志

## 预测登记

| # | 日期 | 预测内容 | 概率 | 到期判据/时间 | 当时依据 | 状态 | 结算日期 | 结果 | 更正记录 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | | | 0.0–1.0 | | | 未到期 | | 成真/落空 | |

## 决策台账

| # | 日期 | 决定 | 推荐 | 实际行动 | 结果 | 复盘备注 |
|---|---|---|---|---|---|---|
| 1 | 2025-01-15 | 立项进入产品落地（GO） | GO | 已执行 | — | |
"""

# 含内部痕迹（references/ 路径、S0/S2 阶段码、声明门）与材料参数表的基线：
# 用于验证「章题错配诚实处理」与「内部引用清洗」两项修补
PRODUCT_BASELINE = """# 产品基线

## 产品定义

- 目标：演示产品定义要点

## 关键参数表

| 参数 | 数值 | 状态标签 | 来源/证据 |
|---|---|---|---|
| 整机重量 | ≤2.5kg | A | 工程假设 |
| 材料抗拉强度 | 48–53 MPa | E | 厂商 TDS |

## 生命周期状态

- 当前阶段：S2 产品定义（见 references/product-lifecycle.md）——PRD 初稿完成，待冻结
- 已达成的声明门：S0 目标与约束显性化
"""


def test_assemble_bp() -> None:
    print("[assemble_bp.py]")
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp) / "ws"
        ws.mkdir()
        (ws / "handoff.json").write_text(json.dumps(GO_HANDOFF, ensure_ascii=False), encoding="utf-8")
        (ws / "research_log.md").write_text(RESEARCH_LOG, encoding="utf-8")
        (ws / "decision_journal.md").write_text(DECISION_JOURNAL, encoding="utf-8")
        (ws / "product_baseline.md").write_text(PRODUCT_BASELINE, encoding="utf-8")

        # GO 工作区：成功组装，七章标题齐全
        code, out, err = run("assemble_bp.py", str(ws))
        draft = ws / "deliverables" / "bp_draft.md"
        ok = code == 0 and out is not None and draft.is_file()
        check("GO 工作区 → 退出码 0，默认输出 deliverables/bp_draft.md", ok,
              f"code={code} out={out} err={err}")

        text = draft.read_text(encoding="utf-8") if draft.is_file() else ""
        titles = ["第一章 执行摘要", "第二章 市场机会", "第三章 为什么是我们",
                  "第四章 关键假设与风险", "第五章 计划与里程碑",
                  "第六章 什么会推翻这个计划", "第七章 复盘与校准"]
        check("七章标题齐全（与 templates/business-plan.md 一致）",
              all(f"## {t}" in text for t in titles))

        # 数据不足章被如实标注：本工作区第七章无预测登记、第三章无基线
        ok = "数据不足" in text and "待补清单" in text and out is not None \
            and any("第七章" in t for t in out["chapters_insufficient"])
        check("账本缺内容的章节如实标「数据不足」+ 待补清单（含第七章）", ok,
              f"chapters_insufficient={out['chapters_insufficient'] if out else None}")

        # 编号标注：假设台账 H-01 与结论卡 R-01 均出现在输出中
        ok = "〔H-01〕" in text and "〔R-01〕" in text and out is not None \
            and "H-01" in out["refs_used"] and out["numbers_cited"] >= 1
        check("数字/结论自动挂账本编号（〔H-01〕〔R-01〕），coverage 统计已挂编号数字", ok,
              f"refs_used={out['refs_used'] if out else None} "
              f"numbers_cited={out['numbers_cited'] if out else None}")

        # 末尾附假设与证据总登记处 + 覆盖率统计
        ok = "## 假设与证据总登记处" in text and "## 覆盖率统计" in text
        check("输出末尾附「假设与证据总登记处」与覆盖率统计", ok)

        # 修补 1：数据不足警示置顶——位于执行摘要章内（而非只埋在缺口章），并列出缺口章号
        ch1 = (text.split("## 第一章 执行摘要", 1)[1].split("## 第二章", 1)[0]
               if "## 第一章 执行摘要" in text else "")
        ok = ("⚠️" in ch1 and "数据不足警示" in ch1 and "暂不足以支撑投资决策" in ch1
              and "第三章" in ch1 and "第七章" in ch1)
        check("数据不足警示置顶在执行摘要开头并列出缺口章号（第三章/第七章）", ok,
              f"执行摘要段={ch1[:200]!r}")

        # 修补 2（R3 修订）：文首标签图例——四态释义固定输出、位于正文之前；
        # 本工作区正文未使用八态标签与英文判定词 → 两组释义行按需省略（避免读者白学）
        legend = text.split("## 标签图例", 1)[1].split("## 第一章", 1)[0] if "## 标签图例" in text else ""
        ok = ("## 标签图例" in text and "本项目内已验证" in legend
              and "不得作为决策依据" in legend and "工程假设" in legend
              and "参数八态" not in legend and "判定词" not in legend
              and "待测试" not in legend and "marginal＝及格线边缘" not in text
              and text.index("## 标签图例") < text.index("## 第一章 执行摘要"))
        check("文首标签图例：四态释义固定输出且位于正文之前；未使用八态/判定词 → 释义行省略", ok,
              f"图例段={legend!r}")

        # 修补 3：章题错配诚实处理——账本无「优势/壁垒/团队」主题内容时，
        # 第三章整章标数据不足，材料参数表等错配内容不得填入
        ch3 = (text.split("## 第三章 为什么是我们", 1)[1].split("## 第四章", 1)[0]
               if "## 第三章 为什么是我们" in text else "")
        ok = ("数据不足" in ch3 and "待补清单" in ch3 and "抗拉" not in ch3
              and "整机重量" not in ch3 and "MPa" not in ch3 and out is not None
              and any("第三章" in t for t in out["chapters_insufficient"]))
        check("章题错配：第三章无优势主题内容 → 整章数据不足，不填材料参数表", ok,
              f"第三章段={ch3[:200]!r}")

        # 修补 4：内部引用清洗——正文无内部路径、无 S0–S8 阶段码、环节码/声明门白话化
        ok = ("references/" not in text and "templates/" not in text
              and "S0" not in text and "S2" not in text
              and "声明门" not in text and "环节3" not in text and "环节1" not in text
              and "产品落地环节" in text and "阶段放行确认点" in text
              and "（handoff" not in text and "product_baseline.md 产品定义" not in text
              and "product_baseline.md 生命周期状态" not in text)
        check("内部引用清洗：无 references/ 路径、无 S0/S2 阶段码、环节码与声明门已白话化", ok)

        # 修补 5：coverage 数字统计口径收紧——仅统计带单位数字，并在 coverage 行注明口径
        cov = text.split("## 覆盖率统计", 1)[1] if "## 覆盖率统计" in text else ""
        ok = "仅统计带单位数字" in cov and "年份与比例代号不计入" in cov
        check("coverage 口径收紧：仅统计带单位数字并在文中注明口径", ok, f"覆盖率段={cov[:200]!r}")

        # 修补 6（R2）：内部括注黑话清除——正文（含括注）无内部流程词残留；
        # 裸出现的「决策台账」已白话化为「决策记录」
        ok = ("判断合同（" not in text and "决策交接包" not in text
              and "何时问用户" not in text and "产品基线·生命周期状态" not in text
              and "决策台账" not in text and "决策记录 #1" in text)
        check("内部括注黑话清除：无「判断合同（」「决策交接包」「何时问用户」残留，决策台账→决策记录", ok,
              f"残留片段={[w for w in ['判断合同（', '决策交接包', '何时问用户', '决策台账'] if w in text]}")

        # 修补 7（R2，R3 修订）：执行摘要去重——与第四章假设表重复时只保留一句汇总；
        # 交接包登记 2 项 vs 台账在册 1 项 → 两数并陈 + 差额，绝不只选一个数；
        # 「未挂账本编号，需回填」全文最多出现一次
        ok = ("交接包登记 2 项、台账在册 1 项（H-01），差 1 项待补登" in ch1
              and "共 2 项关键假设" not in ch1 and "共 1 项关键假设" not in ch1
              and "明细见第四章" in ch1
              and "其中 1 项未验证（H-01" in ch1
              and ch1.count("- 关键假设：") == 1
              and text.count("未挂账本编号") <= 1)
        check("执行摘要去重+数量对账：两数并陈（登记 2 项/在册 1 项，差 1 项待补登），不单选一数", ok,
              f"执行摘要段={ch1[:300]!r}")

        # 修补 8（R2，R3 修订）：图例 R 双义说明按需——八态未使用时连双义注释一并省略
        ok = "R-xx 与参数八态" not in legend and "属不同体系" not in legend
        check("图例 R 双义说明按需：八态未使用时编号说明行不带双义注释", ok,
              f"图例段={legend[-200:]!r}")

        # 修补 9（R2）：算式单元格减负——登记处 C-1 行只有结论数字；
        # O/M/P 输入明细迁至登记处之后的「算式明细附录」
        c1_row = next((ln for ln in text.splitlines() if ln.startswith("| C-1 |")), "")
        appendix = text.split("## 算式明细附录", 1)[1] if "## 算式明细附录" in text else ""
        ok = (c1_row and "O/M" not in c1_row and "ΣE=18.50 人日" in c1_row
              and "O/M/P" in appendix and "设计 2/3/5" in appendix
              and text.index("## 算式明细附录") > text.index("## 假设与证据总登记处"))
        check("算式单元格减负：C-1 行仅结论数字，O/M/P 明细在登记处之后的算式明细附录", ok,
              f"C-1 行={c1_row[:160]!r}")

        # 修补 10（R2）：coverage 口径对账——行末注明与执行摘要「未挂编号」口径不同、不矛盾
        ok = "与本表按带单位数字的口径不同" in cov and "两者不矛盾" in cov
        check("coverage 口径对账：行末注明与摘要「未挂编号」口径不同、两者不矛盾", ok,
              f"覆盖率段={cov[:250]!r}")

        # 修补 11（R3）：假设数量不一致计入 coverage 备注——两数并陈 + 差额 + 补齐指引
        ok = ("假设数量对账" in cov and "交接包登记 2 项" in cov
              and "台账在册 1 项（H-01）" in cov and "差 1 项待补登" in cov)
        check("假设数量不一致计入 coverage 备注（两数并陈 + 差额 + 补齐指引）", ok,
              f"覆盖率段={cov[:300]!r}")

        # 修补 12（R3）：警示块过渡句条件输出——本工作区无 waived_stages、无知情声明 → 不输出
        ok = "知情决策" not in ch1 and "非数据充分性结论" not in text
        check("警示块过渡句按需：非知情决策（无 waived_stages/知情声明）→ 不含「知情决策」句", ok,
              f"执行摘要段={ch1[:200]!r}")

        # 修补 13（R3）：图例按需输出——正文使用八态标签（T）与判定词 healthy 时，
        # 八态/判定词释义行与 R 双义说明保留；数量一致（各 2 项）时摘要照常写「共 2 项」
        tagged_log = RESEARCH_LOG.replace(
            "| H-01 | 目标用户愿意月付 100 元 | 100 元/月 | ASSUMED | 访谈 3 人 | R-01 | |",
            "| H-01 | 目标用户愿意月付 100 元 | 100 元/月 | ASSUMED | 访谈 3 人 | R-01 | |\n"
            "| H-02 | 试打印样件层间强度达标（T） | 待首件实测 | UNVERIFIED | 首件试打印 | | |",
        ).replace(
            "结论：2025 年目标细分市场规模约 120 亿元/年，年增速 15%",
            "结论：2025 年目标细分市场规模约 120 亿元/年，年增速 15%，单位经济 healthy",
        )
        (ws / "research_log.md").write_text(tagged_log, encoding="utf-8")
        code, out, err = run("assemble_bp.py", str(ws))
        text = (ws / "deliverables" / "bp_draft.md").read_text(encoding="utf-8")
        legend = text.split("## 标签图例", 1)[1].split("## 第一章", 1)[0]
        ch1 = text.split("## 第一章 执行摘要", 1)[1].split("## 第二章", 1)[0]
        ok = (code == 0
              and "参数八态" in legend and "待测试" in legend and "待供应商" in legend
              and "判定词" in legend and "marginal＝及格线边缘" in legend
              and "R-xx 与参数八态" in legend and "属不同体系" in legend)
        check("图例按需：正文使用八态标签（T）与判定词 healthy → 八态/判定词释义与 R 双义说明保留", ok,
              f"图例段={legend!r}")
        ok = "共 2 项关键假设" in ch1 and "待补登" not in ch1 and "假设数量对账" not in text
        check("数量一致时照常：摘要写「共 2 项关键假设」，coverage 无对账备注", ok,
              f"执行摘要段={ch1[:300]!r}")

        # 修补 14（R3，R4 修订）：知情决策注提升显著度——waived_stages 含环节 1 时，
        # 加粗独立行紧跟「决策结论：GO」行正下方；警示块内不再重复该注
        waived_handoff = dict(GO_HANDOFF, scope={"waived_stages": ["1"], "note": "用户明确承担风险跳过验证"})
        (ws / "handoff.json").write_text(json.dumps(waived_handoff, ensure_ascii=False), encoding="utf-8")
        code, out, err = run("assemble_bp.py", str(ws))
        text = (ws / "deliverables" / "bp_draft.md").read_text(encoding="utf-8")
        ch1 = text.split("## 第一章 执行摘要", 1)[1].split("## 第二章", 1)[0]
        text_lines = text.splitlines()
        go_idx = next((i for i, ln in enumerate(text_lines)
                       if ln.startswith("> 决策结论：GO")), -1)
        informed_note = ("**注：本 GO 为委托方知情决策（用户明确承担跳过机会验证的风险），"
                         "非数据充分性结论。**")
        ok = (go_idx >= 0 and text_lines[go_idx + 1] == informed_note
              and "知情决策" not in ch1 and "非数据充分性结论" not in ch1
              and "数据不足警示" in ch1)
        check("知情决策注：加粗独立行在 GO 行正下方，警示块内不再重复", ok,
              f"GO 行后续={text_lines[go_idx:go_idx + 3]!r} 执行摘要段={ch1[:200]!r}")

        # 修补 15（R4）：硬约束拆条——渲染为无序列表（每条一项、每项 ≤60 字），
        # 与父级重复的「…硬约束：」前缀去重；不再拼接成多冒号嵌套长句
        (ws / "handoff.json").write_text(json.dumps(GO_HANDOFF, ensure_ascii=False), encoding="utf-8")
        (ws / "research_log.md").write_text(RESEARCH_LOG, encoding="utf-8")
        code, out, err = run("assemble_bp.py", str(ws))
        text = (ws / "deliverables" / "bp_draft.md").read_text(encoding="utf-8")
        ch1 = text.split("## 第一章 执行摘要", 1)[1].split("## 第二章", 1)[0]
        ch1_lines = ch1.splitlines()
        hc_idx = ch1_lines.index("- 硬约束：") if "- 硬约束：" in ch1_lines else -1
        hc_items = []
        for ln in ch1_lines[hc_idx + 1:]:
            if ln.startswith(("  - ", "    ")):
                hc_items.append(ln)
            elif ln.strip():
                break
        ok = (hc_idx >= 0 and len(hc_items) == 3
              and any(ln.strip() == "- 预算 ≤ 50 万" for ln in hc_items)
              and any("结构方案：后入式半包围" in ln for ln in hc_items)
              and "结构方案硬约束：" not in text
              and "预算 ≤ 50 万；真人测试" not in ch1
              and all(len(ln.strip()) <= 60 for ln in hc_items))
        check("硬约束拆条：无序列表每条一项、≤60 字、重复前缀「…硬约束：」去重、无嵌套长句", ok,
              f"硬约束块={hc_items!r}")

        # 修补 16（R4）：逐字重复消除——同一规范文本全文只出现一次，后续替换为指针；
        # 覆盖「下一步」（第一章 vs 第五章）与「最大未知」（第四章 vs 第六章）
        ch5 = text.split("## 第五章 计划与里程碑", 1)[1].split("## 第六章", 1)[0]
        ch6 = text.split("## 第六章 什么会推翻这个计划", 1)[1].split("## 第七章", 1)[0]
        ok = ("完成 PRD 与 MVP 里程碑" in ch1
              and "完成 PRD 与 MVP 里程碑" not in ch5
              and "- 下一步：（同第一章执行摘要，见第一章）" in ch5
              and text.count("- 最大未知：真实转化率未知") == 1
              and "真实转化率未知" not in ch6
              and "- 最大未知：（同第四章关键假设与风险，见第四章）" in ch6)
        check("逐字重复消除：重复 bullet 替换为指针（下一步/最大未知各只出现一次）", ok,
              f"第五章段={ch5[:200]!r} 第六章段={ch6[:200]!r}")

        # 修补 17（R4）：领域术语小词典——正文命中 PERT/PRD/MVP → 图例附「术语表」小节；
        # 未命中的术语（如 BOM）不输出；正文含 TDS 时图例有「技术数据表」
        legend = text.split("## 标签图例", 1)[1].split("## 第一章", 1)[0]
        ok = ("术语表" in legend and "计划评审技术/三点估算法" in legend
              and "产品需求文档" in legend and "最小可行产品" in legend
              and "物料清单" not in legend and "技术数据表" not in legend)
        check("术语表按需：命中 PERT/PRD/MVP 输出释义，未命中 BOM/TDS 不输出", ok,
              f"图例段={legend!r}")
        tds_log = RESEARCH_LOG.replace("来源：某行业年度报告", "来源：某厂商 TDS")
        (ws / "research_log.md").write_text(tds_log, encoding="utf-8")
        code, out, err = run("assemble_bp.py", str(ws))
        text = (ws / "deliverables" / "bp_draft.md").read_text(encoding="utf-8")
        legend = text.split("## 标签图例", 1)[1].split("## 第一章", 1)[0]
        ok = "术语表" in legend and "TDS＝技术数据表" in legend
        check("术语表：正文含 TDS → 图例有「TDS＝技术数据表」", ok, f"图例段={legend!r}")
        (ws / "research_log.md").write_text(RESEARCH_LOG, encoding="utf-8")

        # 修补 18（质量核对遗留：表题即结论）：关键表格上方自动生成结论式标题，
        # 计数由内容机械计算；假设表标题含四态计数与 UNVERIFIED 编号，
        # 登记处合表标题含分类计数
        rich_log = RESEARCH_LOG.replace(
            "| H-01 | 目标用户愿意月付 100 元 | 100 元/月 | ASSUMED | 访谈 3 人 | R-01 | |",
            "| H-01 | 目标用户愿意月付 100 元 | 100 元/月 | ASSUMED | 访谈 3 人 | R-01 | |\n"
            "| H-02 | 试打印样件层间强度达标 | 待首件实测 | UNVERIFIED | 首件试打印 | | |\n"
            "| H-03 | 交付周期满足客户要求 | 30 天内交付 | VERIFIED | 试点客户验收 | | |\n"
            "| H-04 | 复购率不低于三成 | 30% | ESTIMATED | 行业基准 | | |",
        )
        (ws / "research_log.md").write_text(rich_log, encoding="utf-8")
        code, out, err = run("assemble_bp.py", str(ws))
        text = (ws / "deliverables" / "bp_draft.md").read_text(encoding="utf-8")
        ch4 = text.split("## 第四章 关键假设与风险", 1)[1].split("## 第五章", 1)[0]
        registry = text.split("## 假设与证据总登记处", 1)[1]
        ok = (code == 0
              and "**4 项关键假设：VERIFIED 1 / ESTIMATED 1 / ASSUMED 1 / UNVERIFIED 1（H-02）**" in ch4
              and ch4.index("**4 项关键假设") < ch4.index("| # | 关键假设 |"))
        check("表题即结论：假设表上方结论式标题含正确四态计数与 UNVERIFIED 编号", ok,
              f"第四章段={ch4[:300]!r}")
        ok = "**登记处共 7 条：假设 4 / 证据 1 / 算式 2**" in registry
        check("表题即结论：登记处合表标题含分类计数（共 7 条：假设 4/证据 1/算式 2）", ok,
              f"登记处段={registry[:200]!r}")

        # 修补 19（质量核对遗留：假设表单点维护）：第四章不再有 H-01~H-04 整表，
        # 只留 ASSUMED/UNVERIFIED 高关注行 + 登记处指针；登记处仍全量
        ok = ("| H-01 |" in ch4 and "| H-02 |" in ch4
              and "| H-03 |" not in ch4 and "| H-04 |" not in ch4
              and "完整假设台账见文末" in ch4)
        check("假设表单点维护：第四章仅高关注行（ASSUMED/UNVERIFIED）+ 登记处指针，无整表", ok,
              f"第四章段={ch4[:400]!r}")
        ok = all(f"| {hid} |" in registry for hid in ("H-01", "H-02", "H-03", "H-04"))
        check("假设表单点维护：登记处仍全量（H-01~H-04 全在合表）", ok,
              f"登记处段={registry[:300]!r}")

        # 表题退回描述性：台账为空时不编造计数标题；登记处标题省略零计数分类
        empty_hyp_log = RESEARCH_LOG.replace(
            "| H-01 | 目标用户愿意月付 100 元 | 100 元/月 | ASSUMED | 访谈 3 人 | R-01 | |\n", "")
        (ws / "research_log.md").write_text(empty_hyp_log, encoding="utf-8")
        code, out, err = run("assemble_bp.py", str(ws))
        text = (ws / "deliverables" / "bp_draft.md").read_text(encoding="utf-8")
        ch4 = text.split("## 第四章 关键假设与风险", 1)[1].split("## 第五章", 1)[0]
        ok = (code == 0 and "项关键假设：" not in ch4 and "| # | 关键假设 |" not in ch4
              and "**登记处共 3 条：证据 1 / 算式 2**" in text)
        check("表题退回：假设台账为空 → 不编造计数标题；登记处标题省略零计数分类", ok,
              f"第四章段={ch4[:200]!r}")
        (ws / "research_log.md").write_text(RESEARCH_LOG, encoding="utf-8")

        # handoff 为 ABSTAIN：拒绝进入成果交付，退出码 2
        abstain = dict(GO_HANDOFF, recommendation="ABSTAIN")
        (ws / "handoff.json").write_text(json.dumps(abstain, ensure_ascii=False), encoding="utf-8")
        code, out, err = run("assemble_bp.py", str(ws))
        check("handoff 为 ABSTAIN → 报错「非 GO 不进入成果交付」退出码 2",
              code == 2 and "非 GO 不进入成果交付" in err, f"code={code} err={err}")


# ---------------------------------------------------------------------------
# pipeline.py（全链路阶段门执行器）
# ---------------------------------------------------------------------------

PIPELINE_RESEARCH_LOG = """# 研究日志

## 一、研究结论卡

```
【研究结论卡】
结论：（一句话，可证伪的陈述）
```

【研究结论卡】
结论：目标用户愿意月付 100 元
对应假设：H-01
证据等级：ESTIMATED

## 二、假设台账

| 编号 | 假设内容 | 数值/口径 | 状态 | 来源/依据 | 关联结论卡 | 复核日期 |
|---|---|---|---|---|---|---|
| H-01 | （填：可证伪的陈述） | | UNVERIFIED | | | |
| H-02 | 目标用户愿意月付 100 元 | 100元/月 | ESTIMATED | 访谈 I-01 | | |
"""


def _pipeline_workspace(root: Path, recommendation: str) -> Path:
    """构造环节 0-2 完成的临时工作区（研究日志含 1 张真实结论卡 + 1 条合法假设）。"""
    ws = root / f"链路项目-{recommendation}"
    ws.mkdir()
    ws.joinpath("decision_journal.md").write_text("# 决策日志\n\n## 预测登记\n", encoding="utf-8")
    ws.joinpath("research_log.md").write_text(PIPELINE_RESEARCH_LOG, encoding="utf-8")
    ws.joinpath("judgment_contract.md").write_text("# 判断合同\n", encoding="utf-8")
    handoff = {
        "contract_version": "1.0",
        "project": {"name": "链路项目"},
        "decision_question": "是否进入产品落地环节？",
        "recommendation": recommendation,
        "confidence": None,
        "key_assumptions": [{"statement": "目标用户愿意月付 100 元", "status": "ESTIMATED"}],
        "critical_uncertainties": ["真实转化率未知"],
    }
    ws.joinpath("handoff.json").write_text(json.dumps(handoff, ensure_ascii=False), encoding="utf-8")
    return ws


def _stage_map(out: dict) -> dict:
    return {s["id"]: s for s in out["stages"]}


def test_pipeline() -> None:
    print("[pipeline.py]")
    with tempfile.TemporaryDirectory() as tmp:
        # --- 空工作区：前三环节 fail，可选环节 pending，退出码 1 ---
        empty = Path(tmp) / "空项目"
        empty.mkdir()
        code, out, err = run("pipeline.py", str(empty), "--json")
        stages = _stage_map(out) if out else {}
        ok = (
            code == 1 and out is not None
            and stages["0"]["status"] == "fail" and stages["0"]["passed"] == 1 and stages["0"]["total"] == 3
            and stages["1"]["status"] == "fail" and stages["2"]["status"] == "fail" and stages["3"]["status"] == "fail"
            and stages["4"]["status"] == "pending" and stages["4.5"]["status"] == "pending" and stages["5"]["status"] == "pending"
            and out["chain_progress"] is None
            and out["current_gate"]["id"] == "0"
        )
        check("空工作区：环节 0-3 fail、4/4.5/5 pending，current_gate=环节 0，退出码 1", ok,
              f"code={code} out={out} err={err}")

        # --- 环节 0-2 完成 + GO handoff：前三环 pass，环节 3 因缺 product_baseline fail ---
        ws = _pipeline_workspace(Path(tmp), "GO")
        code, out, err = run("pipeline.py", str(ws), "--json")
        stages = _stage_map(out) if out else {}
        ok = (
            code == 1 and out is not None
            and stages["0"]["status"] == "pass" and stages["0"]["passed"] == 3
            and stages["1"]["status"] == "pass" and stages["1"]["passed"] == 2
            and stages["2"]["status"] == "pass" and stages["2"]["passed"] == 3
            and stages["3"]["status"] == "fail"
            and any("product_baseline" in m for m in stages["3"]["missing"])
            and out["chain_progress"] == "2" and out["current_gate"]["id"] == "3"
        )
        check("GO 工作区：环节 0-2 pass，环节 3 缺 product_baseline.md → fail，推进到环节 2", ok,
              f"code={code} out={out} err={err}")

        # 模板占位不计入：示例结论卡与「（填…）」假设行未造成误判（上面已 pass 即证明），
        # 再验证假设缺四态标签会被逐条点名
        log_path = ws / "research_log.md"
        log_path.write_text(
            PIPELINE_RESEARCH_LOG + "| H-03 | 月流失率 ≤ 10% | 10% | 待定 | | | |\n", encoding="utf-8"
        )
        code, out, err = run("pipeline.py", str(ws), "--json")
        stages = _stage_map(out) if out else {}
        ok = (
            out is not None and stages["1"]["status"] == "fail"
            and any("H-03" in m for m in stages["1"]["missing"])
        )
        check("假设台账条目缺四态标签 → 环节 1 fail 并点名 H-03", ok, f"out={out} err={err}")
        log_path.write_text(PIPELINE_RESEARCH_LOG, encoding="utf-8")

        # 补 product_baseline.md → 环节 3 pass，门推进到环节 4（GO 要求放行声明）
        ws.joinpath("product_baseline.md").write_text("# 产品基线\n", encoding="utf-8")
        code, out, err = run("pipeline.py", str(ws), "--json")
        stages = _stage_map(out) if out else {}
        ok = (
            out is not None and stages["3"]["status"] == "pass"
            and stages["4"]["status"] == "fail"
            and out["chain_progress"] == "3" and out["current_gate"]["id"] == "4"
        )
        check("补 product_baseline.md → 环节 3 pass，GO 下环节 4 缺放行声明 → fail", ok,
              f"out={out} err={err}")

        # --- 环节 4.5：有 brief + 主文档但缺报告 → fail；补报告 → pass ---
        dl = ws / "deliverables"
        dl.mkdir()
        dl.joinpath("brief.md").write_text("# 项目简报\n", encoding="utf-8")
        dl.joinpath("bp_v1.md").write_text("# 投资 BP 正文\n", encoding="utf-8")
        code, out, err = run("pipeline.py", str(ws), "--json")
        stages = _stage_map(out) if out else {}
        ok = (
            out is not None and stages["4.5"]["status"] == "fail" and stages["4.5"]["passed"] == 1
            and stages["4.5"]["total"] == 3
            and any("readability" in m for m in stages["4.5"]["missing"])
            and any("quality" in m for m in stages["4.5"]["missing"])
        )
        check("环节 4.5：主文档缺 readability/quality 报告 → fail（1/3）并点名两类报告", ok,
              f"out={out} err={err}")

        dl.joinpath("readability_report.md").write_text("# 可读性报告\n", encoding="utf-8")
        dl.joinpath("quality_report.md").write_text("# 质量核对报告\n", encoding="utf-8")
        ws.joinpath("launch_checklist.md").write_text(
            "# 发布就绪检查单\n\n## 七、放行声明\n\n- 声明人（签字）：张三/产品负责人\n- 日期：2025-02-01\n",
            encoding="utf-8",
        )
        code, out, err = run("pipeline.py", str(ws), "--json")
        stages = _stage_map(out) if out else {}
        ok = (
            out is not None and stages["4"]["status"] == "pass" and stages["4.5"]["status"] == "pass"
            and stages["5"]["status"] == "pending"
        )
        check("补报告 + 已签署放行声明 → 环节 4/4.5 pass；无已结算预测环节 5 仍 pending", ok,
              f"out={out} err={err}")

        # --- 环节 5：已结算预测存在但命中率自查未填 → fail；填写后 → pass 且退出码 0 ---
        journal_path = ws / "decision_journal.md"
        journal_path.write_text(
            "# 决策日志\n\n## 预测登记\n\n"
            "| # | 日期 | 预测内容 | 概率 | 到期判据/时间 | 当时依据 | 状态 | 结算日期 | 结果 | 更正记录 |\n"
            "|---|---|---|---|---|---|---|---|---|---|\n"
            "| 1 | 2025-01-01 | 首月付费转化率达 5% | 0.7 | 2025-02-01 | 访谈 | 成真 | 2025-02-02 | 成真 | |\n\n"
            "## 命中率自查（样本 ≥20 条已结算才可下结论）\n\n- 已结算预测数：\n\n**结论**：（样本不足 / 过度自信 / 信心不足 / 基本校准）\n",
            encoding="utf-8",
        )
        code, out, err = run("pipeline.py", str(ws), "--json")
        stages = _stage_map(out) if out else {}
        ok = (
            code == 1 and out is not None
            and stages["5"]["status"] == "fail" and stages["5"]["passed"] == 1 and stages["5"]["total"] == 2
            and out["current_gate"]["id"] == "5"
        )
        check("环节 5：有已结算预测但命中率自查未填 → fail（1/2），current_gate=环节 5", ok,
              f"code={code} out={out} err={err}")

        journal_path.write_text(
            journal_path.read_text(encoding="utf-8")
            .replace("- 已结算预测数：", "- 已结算预测数：1")
            .replace("**结论**：（样本不足 / 过度自信 / 信心不足 / 基本校准）", "**结论**：样本不足，结论不可用"),
            encoding="utf-8",
        )
        code, out, err = run("pipeline.py", str(ws), "--json")
        stages = _stage_map(out) if out else {}
        ok = (
            code == 0 and out is not None
            and all(s["status"] == "pass" for s in out["stages"])
            and out["chain_progress"] == "5" and out["current_gate"] is None
        )
        check("环节 5 命中率自查填写后：全链路 pass，退出码 0，current_gate=null", ok,
              f"code={code} out={out} err={err}")

        # --- ABSTAIN handoff：环节 3 blocked（按契约不进入）而非 fail，4/4.5 pending ---
        ws_abstain = _pipeline_workspace(Path(tmp), "ABSTAIN")
        code, out, err = run("pipeline.py", str(ws_abstain), "--json")
        stages = _stage_map(out) if out else {}
        ok = (
            code == 0 and out is not None
            and stages["0"]["status"] == "pass" and stages["1"]["status"] == "pass" and stages["2"]["status"] == "pass"
            and stages["3"]["status"] == "blocked" and "按契约不进入" in stages["3"]["note"]
            and stages["4"]["status"] == "pending" and stages["4.5"]["status"] == "pending"
            and out["chain_progress"] == "3"
        )
        check("ABSTAIN handoff：环节 3 blocked（按契约不进入）而非 fail，4/4.5 pending，退出码 0", ok,
              f"code={code} out={out} err={err}")

        # --- 工作区路径不存在 → 退出码 2 ---
        code, out, err = run("pipeline.py", str(Path(tmp) / "不存在的目录"), "--json")
        check("工作区路径不存在 → 报错退出码 2", code == 2 and "init_workspace" in err,
              f"code={code} err={err}")

    # --- 放行声明识别修订（R4 摩擦修补）：账本噪音排除/不放行识别/语义反转防护 ---
    with tempfile.TemporaryDirectory() as td4:
        ws4 = Path(td4) / "w"
        ws4.mkdir()
        (ws4 / "decision_journal.md").write_text("# 台账\n本行提及放行声明但不应被识别\n声明人：张三\n", encoding="utf-8")
        h4 = {"contract_version": "1.0", "project": {"name": "t"},
              "decision_question": "q", "recommendation": "GO",
              "key_assumptions": [], "critical_uncertainties": []}
        (ws4 / "handoff.json").write_text(json.dumps(h4, ensure_ascii=False), encoding="utf-8")
        (ws4 / "product_baseline.md").write_text("# 基线\n", encoding="utf-8")
        code, out, err = run("pipeline.py", str(ws4), "--json")
        st4 = {s["id"]: s for s in out["stages"]}["4"]
        check("账本文件提及放行声明不被误识别（噪音排除）",
              st4["status"] == "fail" and "未找到" in st4["missing"][0],
              f"s4={st4}")
        # 已签署的不放行声明 → 仍 fail（语义反转防护）
        (ws4 / "launch_checklist.md").write_text("# 评审\n## 放行声明\n结论：不放行（NO RELEASE）\n声明人：张三\n", encoding="utf-8")
        code, out, err = run("pipeline.py", str(ws4), "--json")
        st4 = {s["id"]: s for s in out["stages"]}["4"]
        check("已签署的不放行声明判 fail（语义反转防护）",
              st4["status"] == "fail" and "不放行" in st4["missing"][0],
              f"s4={st4}")
        # 正常签署放行 → pass
        (ws4 / "launch_checklist.md").write_text("# 评审\n## 放行声明\n准予放行\n声明人：张三\n", encoding="utf-8")
        code, out, err = run("pipeline.py", str(ws4), "--json")
        st4 = {s["id"]: s for s in out["stages"]}["4"]
        check("正常签署放行声明判 pass", st4["status"] == "pass", f"s4={st4}")

    # --- 豁免机制：waived_stages 标 waived、no_launch 保持 pending（R1 摩擦修补） ---
    with tempfile.TemporaryDirectory() as td3:
        code, out, err = run("init_workspace.py", "豁免测试", "--dir", td3, "--with-contract")
        assert code == 0, err
        ws3 = next(Path(td3).iterdir())
        h3 = json.loads((ws3 / "handoff.json").read_text(encoding="utf-8"))
        h3["decision_question"] = "已真实决策的测试项目"
        h3["recommendation"] = "GO"
        h3["scope"] = {"waived_stages": ["1"], "no_launch": True, "note": "用户明确承担风险跳过验证"}
        (ws3 / "handoff.json").write_text(json.dumps(h3, ensure_ascii=False), encoding="utf-8")
        # 补 product_baseline 使环节 3 通过，专注观察豁免效果
        (ws3 / "product_baseline.md").write_text("# 产品基线\n", encoding="utf-8")
        code, out, err = run("pipeline.py", str(ws3), "--json")
        st = {s["id"]: s for s in out["stages"]}
        check("scope.waived_stages → 环节 1 标 waived 且不计 fail",
              st["1"]["status"] == "waived" and code == 0, f"code={code} s1={st['1']}")
        check("scope.no_launch → 环节 4/4.5 保持 pending 而非 fail",
              st["4"]["status"] == "pending" and st["4.5"]["status"] == "pending",
              f"s4={st['4']['status']} s45={st['4.5']['status']}")

    # --- 骨架 handoff（init_workspace 占位）不得判 pass（真实使用摩擦修补） ---
    import tempfile as _tf2
    with _tf2.TemporaryDirectory() as td2:
        code, out, err = run("init_workspace.py", "骨架测试", "--dir", td2)
        assert code == 0, err
        ws2 = next(Path(td2).iterdir())
        code, out, err = run("pipeline.py", str(ws2), "--json")
        s2 = {s["id"]: s for s in out["stages"]}["2"]
        check("骨架 handoff 被环节 2 拒判为 fail（decision_question 占位识别）",
              code == 1 and s2["status"] == "fail"
              and any("骨架" in m or "待填写" in m for m in s2["missing"]),
              f"code={code} s2={s2}")


def main() -> int:
    print(f"自测目录：{SCRIPTS_DIR}\n")
    test_unit_economics()
    test_calibration()
    test_tam_and_price_chain()
    test_expr()
    test_validate_handoff()
    test_init_workspace()
    test_pipeline()
    test_assemble_bp()
    print(f"\n合计：{PASS_COUNT} 通过，{FAIL_COUNT} 失败。")
    return 0 if FAIL_COUNT == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
