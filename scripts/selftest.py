#!/usr/bin/env python3
"""集中自测（IdeaToLaunch 技能 scripts/ 工具箱）。

以子进程方式真实调用 scripts/ 下各 CLI，做正确性断言：
    - calc.py unit-economics：手算对照（gross_margin / churn_rate / cogs / initial_cost 四条路径）
    - calc.py calibration：Brier 手算对照、n<20 时绝不输出 Brier/ECE 数字
    - calc.py tam / price-chain：手算对照与双法交叉判定
    - validate_handoff.py：合法样本通过、非法样本逐条报错
    - init_workspace.py：幂等性（二次运行跳过且不覆盖被修改过的账本）

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
        # 首次运行：创建两个账本
        code, out, err = run("init_workspace.py", "演示项目", "--date", "20250131", "--dir", tmp)
        ws = Path(tmp) / "演示项目-20250131"
        ok = (
            code == 0 and out is not None
            and ws.is_dir()
            and len(out["created"]) == 2 and out["skipped"] == []
            and (ws / "decision_journal.md").is_file()
            and (ws / "research_log.md").is_file()
        )
        check("首次运行：创建工作区并生成两个账本", ok, f"code={code} out={out} err={err}")

        # 篡改账本内容，验证二次运行绝不覆盖（幂等 + 账本纪律）
        marker = "手工登记的预测，不可被工具覆盖"
        journal = ws / "decision_journal.md"
        journal.write_text(marker, encoding="utf-8")

        code, out, err = run("init_workspace.py", "演示项目", "--date", "20250131", "--dir", tmp)
        ok = (
            code == 0 and out is not None
            and out["created"] == [] and len(out["skipped"]) == 2
            and journal.read_text(encoding="utf-8") == marker
        )
        check("二次运行：全部跳过，已有账本内容原样保留（幂等）", ok,
              f"code={code} out={out} err={err}")

        # --date 格式校验
        code, out, err = run("init_workspace.py", "演示项目", "--date", "2025-01-31", "--dir", tmp)
        check("非法 --date 格式 → 报错退出码 2", code == 2 and "YYYYMMDD" in err,
              f"code={code} err={err}")


def main() -> int:
    print(f"自测目录：{SCRIPTS_DIR}\n")
    test_unit_economics()
    test_calibration()
    test_tam_and_price_chain()
    test_validate_handoff()
    test_init_workspace()
    print(f"\n合计：{PASS_COUNT} 通过，{FAIL_COUNT} 失败。")
    return 0 if FAIL_COUNT == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
