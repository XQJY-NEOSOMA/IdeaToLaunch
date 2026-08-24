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
        "next_step": "完成 PRD 与 MVP 里程碑",
    },
    "key_assumptions": [
        {"statement": "目标用户愿意月付 100 元", "status": "ASSUMED", "evidence_refs": ["H-01"]},
    ],
    "critical_uncertainties": ["真实转化率未知"],
    "constraints": ["预算 ≤ 50 万"],
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
"""


def test_assemble_bp() -> None:
    print("[assemble_bp.py]")
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp) / "ws"
        ws.mkdir()
        (ws / "handoff.json").write_text(json.dumps(GO_HANDOFF, ensure_ascii=False), encoding="utf-8")
        (ws / "research_log.md").write_text(RESEARCH_LOG, encoding="utf-8")
        (ws / "decision_journal.md").write_text(DECISION_JOURNAL, encoding="utf-8")

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
