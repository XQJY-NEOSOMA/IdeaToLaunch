#!/usr/bin/env python3
"""计算核心（IdeaToLaunch 技能确定性工具，纯标准库，禁止心算入文）。

四个子命令，输入均为 JSON（--json 字符串或 --file 路径，二选一），
输出均为 JSON，含完整算式回显（formulas 字段），可直接粘贴到账本
research_log.md 的「算式附录」。

子命令：
    unit-economics  单位经济：毛利率 / 月毛利 / LTV / LTV/CAC / 回本期 / 健康判定
    tam             市场规模：自顶向下 × 自底向上双法交叉
    price-chain     硬件 BOM → 零售价加成链（口径见 references/business-model.md 2.6）
    calibration     预测校准：Brier / ECE（10 桶）；n<20 时拒绝输出数字（纪律机械化）
    expr            通用表达式：白名单算术（消除"辅助算术灰色地带"，禁止心算入文）

退出码：0 成功；2 输入或参数错误。
"""

import argparse
import ast
import json
import sys
from pathlib import Path

# 校准纪律：已结算预测不足 20 条时，Brier/ECE 一律不输出（见 SKILL.md 环节 5）
CALIBRATION_MIN_SAMPLES = 20
# TAM 双法交叉容忍区间：比值在 [0.1, 10] 内为 pass
TAM_RATIO_LOW, TAM_RATIO_HIGH = 0.1, 10.0
# 单位经济健康判线（见 references/business-model.md：LTV/CAC ≥ 3 且回本期 ≤ 12 月）
UE_RATIO_HEALTHY = 3.0
UE_PAYBACK_HEALTHY_MONTHS = 12.0


def die(message: str) -> None:
    """以中文可操作错误信息输出 JSON 并以退出码 2 终止。"""
    print(json.dumps({"error": message}, ensure_ascii=False), file=sys.stderr)
    sys.exit(2)


def emit(payload: dict) -> None:
    """输出 JSON 结果（保留中文，缩进便于直接阅读与粘贴）。"""
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def num(x: float) -> float:
    """输出数值统一保留 4 位小数，避免浮点长尾污染账本。"""
    return round(float(x), 4)


def require_number(data: dict, key: str, ctx: str):
    """取必填数值字段；缺失或类型错误时给出可操作的中文报错。"""
    if key not in data:
        die(f"{ctx} 缺少必填字段 {key!r}。")
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        die(f"{ctx} 字段 {key!r} 必须是数字，收到：{value!r}。")
    return float(value)


def load_input(args) -> dict:
    """从 --json 字符串或 --file 路径读取输入 JSON（二选一，缺一不可）。"""
    if args.json is not None and args.file is not None:
        die("--json 与 --file 只能二选一。")
    if args.json is None and args.file is None:
        die("缺少输入：请用 --json '<JSON 字符串>' 或 --file <路径> 提供输入。")
    if args.json is not None:
        raw = args.json
        source = "--json"
    else:
        path = Path(args.file)
        if not path.is_file():
            die(f"输入文件不存在：{path}。请检查 --file 路径。")
        raw = path.read_text(encoding="utf-8")
        source = str(path)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        die(f"输入不是合法 JSON（来源 {source}）：第 {exc.lineno} 行第 {exc.colno} 列，{exc.msg}。")
    if not isinstance(data, dict):
        die(f"输入 JSON 顶层必须是对象 {{...}}，收到的是 {type(data).__name__}。")
    return data


# ---------------------------------------------------------------------------
# 子命令 1：unit-economics
# ---------------------------------------------------------------------------

def cmd_unit_economics(data: dict) -> dict:
    """单位经济计算。

    输入字段：
        price           单价/月费（必填，>0）
        cac             单客获取成本（必填，>0）
        cogs            单位成本（与 gross_margin 二选一）
        gross_margin    毛利率，0–1（与 cogs 二选一）
        lifespan_months 客户生命周期（月，与 churn_rate 二选一，>0）
        churn_rate      月流失率，0–1（与 lifespan_months 二选一；lifespan = 1/churn_rate）
        initial_cost    可选，硬件首投（单客一次性成本，≥0），计入 LTV 扣减与回本分子
    """
    ctx = "unit-economics"
    price = require_number(data, "price", ctx)
    cac = require_number(data, "cac", ctx)
    if price <= 0:
        die(f"{ctx}：price 必须 > 0，收到 {price}。")
    if cac <= 0:
        die(f"{ctx}：cac 必须 > 0，收到 {cac}。")

    # 毛利率口径：cogs 与 gross_margin 二选一
    has_cogs = "cogs" in data
    has_margin = "gross_margin" in data
    if has_cogs and has_margin:
        die(f"{ctx}：cogs 与 gross_margin 只能二选一（两者都给会产生口径歧义）。")
    if not has_cogs and not has_margin:
        die(f"{ctx}：必须提供 cogs 或 gross_margin 之一以确定毛利率。")
    formulas = []
    if has_cogs:
        cogs = require_number(data, "cogs", ctx)
        gross_margin = (price - cogs) / price
        formulas.append(
            f"毛利率 = (price − cogs) ÷ price = ({num(price)} − {num(cogs)}) ÷ {num(price)} = {num(gross_margin)}"
        )
    else:
        gross_margin = require_number(data, "gross_margin", ctx)
        formulas.append(f"毛利率 = gross_margin（直接输入）= {num(gross_margin)}")
    if not 0 < gross_margin <= 1:
        die(f"{ctx}：毛利率须在 (0, 1] 区间，算得/收到 {num(gross_margin)}。请检查 price 与 cogs 口径。")

    # 生命周期口径：lifespan_months 与 churn_rate 二选一
    has_lifespan = "lifespan_months" in data
    has_churn = "churn_rate" in data
    if has_lifespan and has_churn:
        die(f"{ctx}：lifespan_months 与 churn_rate 只能二选一（同时给出会口径冲突）。")
    if not has_lifespan and not has_churn:
        die(f"{ctx}：必须提供 lifespan_months 或 churn_rate 之一以确定生命周期。")
    if has_lifespan:
        lifespan = require_number(data, "lifespan_months", ctx)
        if lifespan <= 0:
            die(f"{ctx}：lifespan_months 必须 > 0，收到 {lifespan}。")
        formulas.append(f"生命周期 = lifespan_months（直接输入）= {num(lifespan)} 月")
    else:
        churn = require_number(data, "churn_rate", ctx)
        if not 0 < churn <= 1:
            die(f"{ctx}：churn_rate 须在 (0, 1] 区间，收到 {churn}。")
        lifespan = 1.0 / churn
        formulas.append(f"生命周期 = 1 ÷ churn_rate = 1 ÷ {num(churn)} = {num(lifespan)} 月")

    initial_cost = 0.0
    if "initial_cost" in data:
        initial_cost = require_number(data, "initial_cost", ctx)
        if initial_cost < 0:
            die(f"{ctx}：initial_cost 不能为负，收到 {initial_cost}。")

    monthly_gp = price * gross_margin
    ltv_gross = monthly_gp * lifespan
    ltv = ltv_gross - initial_cost
    upfront = cac + initial_cost
    ltv_cac = ltv / cac
    payback = upfront / monthly_gp

    formulas.append(f"月毛利 = price × 毛利率 = {num(price)} × {num(gross_margin)} = {num(monthly_gp)}")
    formulas.append(f"LTV（毛）= 月毛利 × 生命周期 = {num(monthly_gp)} × {num(lifespan)} = {num(ltv_gross)}")
    if initial_cost > 0:
        formulas.append(f"LTV（净）= LTV（毛）− initial_cost = {num(ltv_gross)} − {num(initial_cost)} = {num(ltv)}")
    formulas.append(f"LTV/CAC = {num(ltv)} ÷ {num(cac)} = {num(ltv_cac)}")
    if initial_cost > 0:
        formulas.append(
            f"回本期 = (CAC + initial_cost) ÷ 月毛利 = ({num(cac)} + {num(initial_cost)}) ÷ {num(monthly_gp)} = {num(payback)} 月"
        )
    else:
        formulas.append(f"回本期 = CAC ÷ 月毛利 = {num(cac)} ÷ {num(monthly_gp)} = {num(payback)} 月")

    rule = (
        f"健康判定规则：LTV/CAC ≥ {UE_RATIO_HEALTHY:g} 且回本期 ≤ {UE_PAYBACK_HEALTHY_MONTHS:g} 月 → healthy；"
        f"LTV/CAC < 1 → unhealthy；其余 → marginal。"
        "回本期含 initial_cost 首投（方法论：references/business-model.md §3.1）。"
    )
    if ltv_cac >= UE_RATIO_HEALTHY and payback <= UE_PAYBACK_HEALTHY_MONTHS:
        verdict = "healthy"
    elif ltv_cac < 1:
        verdict = "unhealthy"
    else:
        verdict = "marginal"
    formulas.append(rule + f"本组：LTV/CAC={num(ltv_cac)}、回本期={num(payback)} 月 → {verdict}")
    formulas.append("口径出处：回本期含 initial_cost 首投（方法论：references/business-model.md §3.1）")

    return {
        "command": "unit-economics",
        "inputs": data,
        "gross_margin": num(gross_margin),
        "monthly_gross_profit": num(monthly_gp),
        "lifespan_months": num(lifespan),
        "ltv": num(ltv),
        "ltv_cac_ratio": num(ltv_cac),
        "payback_months": num(payback),
        "verdict": verdict,
        "verdict_rule": rule,
        "formulas": formulas,
    }


# ---------------------------------------------------------------------------
# 子命令 2：tam
# ---------------------------------------------------------------------------

def cmd_tam(data: dict) -> dict:
    """市场规模双法交叉：自顶向下 × 因子链，自底向上 × 因子链/客户×渗透×ARPU。

    输入字段：
        topdown.base_market   基准大盘（必填，>0）
        topdown.factors       过滤因子列表 [{name, value, source}...]，value 为乘数
        topdown.unit          可选，金额单位（缺省 "元"），照抄标注进算式
        bottomup 两种口径二选一（同时给出会口径冲突，报错）：
            新形式 bottomup.factors      因子链 [{name, value, source}...]，各 value 连乘，
                                         算式回显带每个因子的 name 与 source（与 topdown 对称）
            旧形式 bottomup.customers    目标客户数（必填，>0）
                   bottomup.penetration  渗透率 0–1（必填）
                   bottomup.arpu         单客年收入（必填，>0）
        bottomup.unit         可选，金额单位（缺省沿用 topdown.unit 或 "元"）
    """
    ctx = "tam"
    for section in ("topdown", "bottomup"):
        if section not in data or not isinstance(data[section], dict):
            die(f"{ctx}：缺少对象字段 {section!r}。需要 topdown 与 bottomup 两个对象。")
    top, bottom = data["topdown"], data["bottomup"]

    unit_top = top.get("unit", data.get("unit", "元"))
    unit_bottom = bottom.get("unit", data.get("unit", unit_top))

    base = require_number(top, "base_market", f"{ctx}.topdown")
    if base <= 0:
        die(f"{ctx}：topdown.base_market 必须 > 0，收到 {base}。")
    factors = top.get("factors", [])
    if not isinstance(factors, list):
        die(f"{ctx}：topdown.factors 必须是列表 [{{name, value, source}}...]。")
    for i, factor in enumerate(factors):
        if not isinstance(factor, dict) or "value" not in factor:
            die(f"{ctx}：topdown.factors[{i}] 必须是含 value 的对象 {{name, value, source}}。")
        if isinstance(factor["value"], bool) or not isinstance(factor["value"], (int, float)):
            die(f"{ctx}：topdown.factors[{i}].value 必须是数字，收到 {factor['value']!r}。")

    result_top = base
    chain = [f"{num(base)}"]
    for factor in factors:
        result_top *= float(factor["value"])
        name = factor.get("name", "?")
        chain.append(f"{factor['value']}（{name}）")

    # 自底向上口径：新形式 factors 因子链（各 value 连乘，与 topdown 对称）
    # 与旧形式 customers × penetration × arpu 二选一，向后兼容，输出结构不变
    has_b_factors = "factors" in bottom
    legacy_keys = [k for k in ("customers", "penetration", "arpu") if k in bottom]
    if has_b_factors and legacy_keys:
        die(f"{ctx}：bottomup.factors 与 bottomup.customers/penetration/arpu 只能二选一（同时给出会口径冲突）。")
    if has_b_factors:
        b_factors = bottom["factors"]
        if not isinstance(b_factors, list) or not b_factors:
            die(f"{ctx}：bottomup.factors 必须是非空列表 [{{name, value, source}}...]。")
        result_bottom = 1.0
        b_chain = []
        for i, factor in enumerate(b_factors):
            if not isinstance(factor, dict) or "value" not in factor:
                die(f"{ctx}：bottomup.factors[{i}] 必须是含 value 的对象 {{name, value, source}}。")
            value = factor["value"]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                die(f"{ctx}：bottomup.factors[{i}].value 必须是数字，收到 {value!r}。")
            if value <= 0:
                die(f"{ctx}：bottomup.factors[{i}].value 必须 > 0，收到 {value}。")
            result_bottom *= float(value)
            name = factor.get("name", "?")
            source = factor.get("source", "?")
            b_chain.append(f"{num(float(value))}（{name}｜{source}）")
        formula_bottom = f"自底向上：TAM = {' × '.join(b_chain)} = {num(result_bottom)} {unit_bottom}"
    else:
        customers = require_number(bottom, "customers", f"{ctx}.bottomup")
        penetration = require_number(bottom, "penetration", f"{ctx}.bottomup")
        arpu = require_number(bottom, "arpu", f"{ctx}.bottomup")
        if customers <= 0 or arpu <= 0:
            die(f"{ctx}：bottomup.customers 与 bottomup.arpu 必须 > 0。")
        if not 0 < penetration <= 1:
            die(f"{ctx}：bottomup.penetration 须在 (0, 1] 区间，收到 {penetration}。")
        result_bottom = customers * penetration * arpu
        formula_bottom = (
            f"自底向上：TAM = customers × penetration × arpu = {num(customers)} × {num(penetration)} × {num(arpu)}"
            f" = {num(result_bottom)} {unit_bottom}"
        )

    ratio = result_top / result_bottom
    passed = TAM_RATIO_LOW <= ratio <= TAM_RATIO_HIGH
    status = "pass" if passed else "fail——找出分歧最大的假设"

    formulas = [
        f"自顶向下：TAM = base_market × " + " × ".join(chain[1:])
        + f" = {' × '.join(chain)} = {num(result_top)} {unit_top}"
        if factors
        else f"自顶向下：TAM = base_market = {num(base)} {unit_top}",
        formula_bottom,
        f"数量级比值 = 自顶向下 ÷ 自底向上 = {num(result_top)} ÷ {num(result_bottom)} = {num(ratio)}；"
        f"判定区间 [{TAM_RATIO_LOW:g}, {TAM_RATIO_HIGH:g}] → {status}",
        "口径出处：references/market-research.md §5（市场规模估算规程 TAM/SAM/SOM 与双法交叉）",
    ]

    return {
        "command": "tam",
        "inputs": data,
        "topdown_result": num(result_top),
        "bottomup_result": num(result_bottom),
        "topdown_unit": unit_top,
        "bottomup_unit": unit_bottom,
        "magnitude_ratio": num(ratio),
        "status": status,
        "status_rule": f"两法比值在 [{TAM_RATIO_LOW:g}, {TAM_RATIO_HIGH:g}] 内为 pass，否则 fail——找出分歧最大的假设",
        "formulas": formulas,
    }


# ---------------------------------------------------------------------------
# 子命令 3：price-chain
# ---------------------------------------------------------------------------

def cmd_price_chain(data: dict) -> dict:
    """硬件加成链：BOM → 出厂成本 → 售后准备金 → 含税出厂价 → 建议零售价。

    口径与 references/business-model.md 2.6 一致：
        出厂成本   = BOM × (1 + 损耗率)
        售后准备金 = 出厂成本 × 计提率
        含税出厂价 = (出厂成本 + 售后准备金) ÷ (1 − 税率)
        建议零售价 = 含税出厂价 ÷ (1 − 渠道毛利率)
    输入字段：bom_cost, loss_rate, warranty_rate, tax_rate, channel_margin（均必填，比率 0–1）。
    """
    ctx = "price-chain"
    bom = require_number(data, "bom_cost", ctx)
    if bom <= 0:
        die(f"{ctx}：bom_cost 必须 > 0，收到 {bom}。")
    rates = {}
    for key, label in (
        ("loss_rate", "损耗率"),
        ("warranty_rate", "售后准备金计提率"),
        ("tax_rate", "税率口径"),
        ("channel_margin", "渠道毛利率"),
    ):
        value = require_number(data, key, ctx)
        if not 0 <= value < 1:
            die(f"{ctx}：{key}（{label}）须在 [0, 1) 区间，收到 {value}。")
        rates[key] = value

    ex_factory = bom * (1 + rates["loss_rate"])
    warranty = ex_factory * rates["warranty_rate"]
    taxed = (ex_factory + warranty) / (1 - rates["tax_rate"])
    retail = taxed / (1 - rates["channel_margin"])
    multiple = retail / bom

    steps = [
        {
            "step": "ex_factory（出厂成本）",
            "formula": f"BOM × (1 + 损耗率) = {num(bom)} × (1 + {num(rates['loss_rate'])}) = {num(ex_factory)}",
            "value": num(ex_factory),
        },
        {
            "step": "warranty_reserve（售后准备金）",
            "formula": f"出厂成本 × 计提率 = {num(ex_factory)} × {num(rates['warranty_rate'])} = {num(warranty)}",
            "value": num(warranty),
        },
        {
            "step": "taxed_factory_price（含税出厂价）",
            "formula": (
                f"(出厂成本 + 售后准备金) ÷ (1 − 税率) = ({num(ex_factory)} + {num(warranty)}) "
                f"÷ (1 − {num(rates['tax_rate'])}) = {num(taxed)}"
            ),
            "value": num(taxed),
        },
        {
            "step": "retail（建议零售价）",
            "formula": f"含税出厂价 ÷ (1 − 渠道毛利率) = {num(taxed)} ÷ (1 − {num(rates['channel_margin'])}) = {num(retail)}",
            "value": num(retail),
        },
    ]

    return {
        "command": "price-chain",
        "inputs": data,
        "steps": steps,
        "ex_factory": num(ex_factory),
        "retail": num(retail),
        "retail_to_bom_ratio": num(multiple),
        "sanity_note": (
            f"零售价 ÷ BOM = {num(multiple)}。常见硬件 2.5×–5× 仅为经验 sanity check，不作定价依据；"
            "最终价必须 ≥ 本链结果才保本。"
        ),
        "formulas": [s["formula"] for s in steps]
        + ["口径出处：references/business-model.md §2.6（硬件：BOM 到零售价的上游加成规则）"],
    }


# ---------------------------------------------------------------------------
# 子命令 4：calibration
# ---------------------------------------------------------------------------

def cmd_calibration(data: dict) -> dict:
    """预测校准：Brier 分数与 ECE（10 桶）。

    纪律机械化：已结算预测 n < 20 时，status="UNCALIBRATED"，不输出 Brier/ECE
    任何数字（样本不足，结论不可用，见 SKILL.md 环节 5 与 decision-quality.md 六章）。

    输入字段：
        predictions  列表 [{probability: 0–1, outcome: true/false}...]
    """
    ctx = "calibration"
    predictions = data.get("predictions")
    if not isinstance(predictions, list):
        die(f"{ctx}：缺少列表字段 'predictions'，格式 [{{probability, outcome}}...]。")
    n = len(predictions)
    for i, p in enumerate(predictions):
        if not isinstance(p, dict):
            die(f"{ctx}：predictions[{i}] 必须是对象 {{probability, outcome}}。")
        prob = p.get("probability")
        if isinstance(prob, bool) or not isinstance(prob, (int, float)) or not 0 <= prob <= 1:
            die(f"{ctx}：predictions[{i}].probability 须在 [0, 1] 区间，收到 {prob!r}。")
        if not isinstance(p.get("outcome"), bool):
            die(f"{ctx}：predictions[{i}].outcome 必须是 true/false，收到 {p.get('outcome')!r}。")

    if n < CALIBRATION_MIN_SAMPLES:
        return {
            "command": "calibration",
            "n": n,
            "status": "UNCALIBRATED",
            "message": (
                f"样本不足：已结算预测 {n} 条 < {CALIBRATION_MIN_SAMPLES} 条，"
                "Brier/ECE 不输出，校准结论不可用。继续登记并到期结算预测后再评。"
            ),
        }

    # Brier = (1/n) Σ (p_i − o_i)²
    brier = sum((float(p["probability"]) - (1.0 if p["outcome"] else 0.0)) ** 2 for p in predictions) / n

    # ECE：10 桶 [0,0.1)…[0.9,1.0]，加权 |桶内平均置信度 − 桶内命中率|
    buckets = [[] for _ in range(10)]
    for p in predictions:
        prob = float(p["probability"])
        idx = min(int(prob * 10), 9)  # p=1.0 归入最后一桶
        buckets[idx].append(p)

    bucket_table = []
    ece = 0.0
    for i, bucket in enumerate(buckets):
        if not bucket:
            continue
        count = len(bucket)
        avg_conf = sum(float(p["probability"]) for p in bucket) / count
        accuracy = sum(1.0 if p["outcome"] else 0.0 for p in bucket) / count
        gap = abs(avg_conf - accuracy)
        ece += (count / n) * gap
        bucket_table.append(
            {
                "bucket": f"[{i / 10:.1f}, {(i + 1) / 10:.1f}{']' if i == 9 else ')'}",
                "count": count,
                "avg_confidence": num(avg_conf),
                "accuracy": num(accuracy),
                "gap": num(gap),
            }
        )

    formulas = [
        f"Brier = (1/n) Σ(pᵢ − oᵢ)²，n={n} → {num(brier)}（0 为完美，越小越好）",
        f"ECE = Σ (桶样本数/n) × |桶内平均置信度 − 桶内命中率|，10 桶 → {num(ece)}（越小越校准）",
        "口径出处：references/decision-quality.md §六（校准与复盘）",
    ]
    return {
        "command": "calibration",
        "n": n,
        "status": "OK",
        "brier": num(brier),
        "ece": num(ece),
        "buckets": bucket_table,
        "note": "校准结果仅用于呈现历史判断可靠度，不自动改写后续预测概率（避免循环依赖）。",
        "formulas": formulas,
    }


# ---------------------------------------------------------------------------
# 子命令 5：expr（通用白名单表达式，消除"辅助算术灰色地带"）
# ---------------------------------------------------------------------------

# 白名单：仅数字、括号、+ - * / // % **、一元负号；其余节点一律拒绝
_EXPR_BINOPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a ** b,
}
# ** 指数幅度上限：防止 10**10**10 之类的资源滥用（白名单之内的纪律）
_EXPR_POW_LIMIT = 1e6


def _eval_expr(node) -> float:
    """递归求值 ast 节点；白名单之外的任何节点直接报错退出码 2。"""
    if isinstance(node, ast.Expression):
        return _eval_expr(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            die(f"expr：仅允许数字字面量，收到 {node.value!r}。禁止名称、字符串与布尔值。")
        return float(node.value)
    if isinstance(node, ast.BinOp):
        op = _EXPR_BINOPS.get(type(node.op))
        if op is None:
            die(f"expr：不支持的运算符 {type(node.op).__name__}；仅允许 + - * / // % **。")
        left = _eval_expr(node.left)
        right = _eval_expr(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > _EXPR_POW_LIMIT:
            die(f"expr：** 的指数绝对值超过上限 {_EXPR_POW_LIMIT:g}，拒绝求值（防资源滥用）。")
        try:
            return op(left, right)
        except ZeroDivisionError:
            die(f"expr：除数为零，表达式不可求值。请检查算式。")
    if isinstance(node, ast.UnaryOp):
        operand = _eval_expr(node.operand)
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.UAdd):
            return operand
        die(f"expr：不支持的一元运算符 {type(node.op).__name__}；仅允许一元负号。")
    die(
        f"expr：表达式含不允许的语法元素 {type(node).__name__}。"
        "白名单仅允许：数字、括号、+ - * / // % **、一元负号。"
    )


def cmd_expr(data: dict) -> dict:
    """通用表达式计算（白名单算术）。

    输入字段：
        expression  算式字符串（必填），仅允许数字、括号、+ - * / // % **、一元负号
        note        可选，算式用途说明，照抄进输出便于账本标注
    输出 formula 字段可直接粘贴到账本 research_log.md 的「算式附录」。
    """
    ctx = "expr"
    expression = data.get("expression")
    if not isinstance(expression, str) or not expression.strip():
        die(f"{ctx}：缺少必填字段 'expression'（非空算式字符串），如 \"50*80*12\"。")
    note = data.get("note", "")
    if not isinstance(note, str):
        die(f"{ctx}：字段 'note' 必须是字符串，收到 {note!r}。")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        die(f"{ctx}：算式语法错误：{exc.msg}（第 {exc.lineno} 行第 {exc.offset} 列）。收到：{expression!r}")
    result = _eval_expr(tree)
    shown = int(result) if result.is_integer() else num(result)
    return {
        "command": "expr",
        "expression": expression,
        "note": note,
        "result": shown,
        "formula": f"{expression} = {shown}",
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

COMMANDS = {
    "unit-economics": cmd_unit_economics,
    "tam": cmd_tam,
    "price-chain": cmd_price_chain,
    "calibration": cmd_calibration,
    "expr": cmd_expr,
}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="IdeaToLaunch 计算核心：所有算术由工具完成并保留算式，禁止心算入文。"
    )
    parser.add_argument("command", choices=sorted(COMMANDS), help="子命令")
    parser.add_argument("--json", default=None, help="输入 JSON 字符串")
    parser.add_argument("--file", default=None, help="输入 JSON 文件路径")
    args = parser.parse_args(argv)

    data = load_input(args)
    emit(COMMANDS[args.command](data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
