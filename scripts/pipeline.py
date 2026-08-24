#!/usr/bin/env python3
"""全链路阶段门执行器（IdeaToLaunch 技能确定性工具，纯标准库）。

用法：
    python3 scripts/pipeline.py <工作区路径> [--json]

行为：
    对一个项目工作区做"链路体检"：按 SKILL.md 全链路地图逐环节核查出口判据
    （环节 0 工作区 → 1 机会验证 → 2 决策 → 3 产品落地 → 4 发布上市
    → 4.5 成果交付 → 5 运营复盘），输出每环节状态、已通过判据数、缺失项
    清单与下一步建议命令，并给出总览（chain_progress / current_gate）。

环节状态语义：
    pass    全部出口判据通过；
    fail    存在未通过判据（missing 列出缺失项）；
    blocked 按契约不进入（handoff recommendation 为 NO_GO/ABSTAIN 时的环节 3）；
    pending 可选/尚未触发的环节（如无 GO+发布意图的环节 4、无已结算预测的环节 5）。

规则表数据驱动：STAGES 登记环节元信息与求值函数，新增环节只需追加一行
并提供一个求值函数；判据识别（研究结论卡、假设台账四态标签、放行声明、
已结算预测、命中率自查）均按 templates/ 的模板标记解析，不硬编码内容。

handoff.json 校验复用 scripts/validate_handoff.py 的 validate 逻辑
（schema 为单一事实源，与 init_workspace.py 同一调用方式）。

输出（--json，stdout）：
    {"workspace": ..., "stages": [{"id", "name", "status", "passed", "total",
     "missing": [...], "next_action", "note"}], "chain_progress": ...,
     "current_gate": {...|null}}
默认输出人类可读表格（状态词带 ✅/❌/⛔/⏳ 图标）。

退出码：0 无 fail 环节；1 存在 fail 环节；2 参数/环境错误。
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

# 技能根目录：本脚本位于 <技能根>/scripts/
SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent

# 假设状态四态标签（与 references/decision-quality.md、handoff_v1.json 一致）
FOUR_STATES = ("VERIFIED", "ESTIMATED", "ASSUMED", "UNVERIFIED")

# 状态图标（人类可读表格用）
STATUS_ICON = {"pass": "✅", "fail": "❌", "blocked": "⛔", "pending": "⏳", "waived": "🚫"}

# 各环节默认下一步建议命令（数据驱动，求值函数可按上下文覆盖）
NEXT_ACTIONS = {
    "0": "运行 python3 scripts/init_workspace.py <项目名> --dir <基目录> 初始化工作区账本",
    "1": "按 references/market-research.md 补研究结论卡，并在假设台账登记 ≥1 条带四态标签（VERIFIED/ESTIMATED/ASSUMED/UNVERIFIED）的假设",
    "2": "补 judgment_contract.md 与 handoff.json，随后运行 python3 scripts/validate_handoff.py <工作区>/handoff.json 校验",
    "3": "从 templates/product-baseline.md 建立 product_baseline.md，进入产品落地",
    "4": "按 templates/launch-checklist.md 完成六线就绪评审并签署放行声明，归档到工作区",
    "4.5": "按 templates/deliverable-brief.md 产出 deliverables/brief.md；主文档须配 readability_report 与 quality_report",
    "5": "在 decision_journal.md「命中率自查」节填写已结算统计与结论",
}


def die(message: str) -> None:
    """以中文可操作错误信息输出 JSON 并以退出码 2 终止。"""
    print(json.dumps({"error": message}, ensure_ascii=False), file=sys.stderr)
    sys.exit(2)


def read_text(path: Path):
    """读取 UTF-8 文本；文件不存在或读取出错返回 None。"""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def section(text: str, header_keyword: str) -> str:
    """截取第一个标题含 header_keyword 的「## 节」正文（到下一「## 」或文末）。"""
    m = re.search(rf"^## [^\n]*{re.escape(header_keyword)}[^\n]*$", text, re.M)
    if not m:
        return ""
    rest = text[m.end():]
    nxt = re.search(r"^## ", rest, re.M)
    return rest[: nxt.start()] if nxt else rest


def table_rows(sec: str):
    """解析 Markdown 表格数据行（跳过表头与分隔行），返回单元格列表的行列表。"""
    rows = []
    for line in sec.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not cells or not cells[0] or set(cells[0]) <= set("-: "):
            continue
        rows.append(cells)
    return rows


def is_placeholder(value: str) -> bool:
    """判断单元格/字段值是否仍是模板占位（空、（填…）、（一句话…）等）。"""
    return not value or value.startswith("（") or set(value) <= set("_ ")


# ---------------------------------------------------------------------------
# 判据识别器（按 templates/ 模板标记解析）
# ---------------------------------------------------------------------------

def count_conclusion_cards(research_log: str) -> int:
    """统计 research_log.md 中已填写的【研究结论卡】数量。

    模板自身在代码围栏内给出一张示例卡（结论行为占位「（一句话，可证伪的
    陈述）」），不计入；只统计「结论：」后为非占位内容的卡片。
    """
    count = 0
    for m in re.finditer(r"【研究结论卡】", research_log):
        block = research_log[m.end(): m.end() + 600]
        cm = re.search(r"^结论[：:]\s*(.+?)\s*$", block, re.M)
        if cm and not is_placeholder(cm.group(1)):
            count += 1
    return count


def hypothesis_rows(research_log: str):
    """解析假设台账：返回 [(编号, 状态是否合法四态标签)]，只计真实条目。

    真实条目 = 编号形如 H-xx 且假设内容非占位；状态列（第 4 列）必须命中
    四态标签之一。
    """
    rows = []
    for cells in table_rows(section(research_log, "假设台账")):
        if not re.fullmatch(r"H-\d+", cells[0]):
            continue
        content = cells[1] if len(cells) > 1 else ""
        if is_placeholder(content):
            continue
        status_ok = len(cells) > 3 and cells[3] in FOUR_STATES
        rows.append((cells[0], status_ok))
    return rows


def settled_predictions(journal: str):
    """解析决策日志「预测登记」表，返回已结算（状态/结果列恰为 成真/落空）的行编号。

    模板示例行结果列为「成真/落空」（含斜杠，是填写说明而非结算结果），不计入。
    """
    settled = []
    for cells in table_rows(section(journal, "预测登记")):
        if cells[0] == "#" or len(cells) < 7:
            continue
        content = cells[2] if len(cells) > 2 else ""
        if is_placeholder(content):
            continue
        if any(re.fullmatch(r"(成真|落空)", c) for c in cells[6:]):
            settled.append(cells[0])
    return settled


def hitrate_section_filled(journal: str) -> bool:
    """判断决策日志「命中率自查」节是否已有实质内容。"""
    sec = section(journal, "命中率自查")
    if not sec:
        return False
    m = re.search(r"已结算预测数[：:]\s*(\d+)", sec)
    if m and int(m.group(1)) >= 1:
        return True
    m = re.search(r"结论\*\*[：:]\s*(.+?)\s*$", sec, re.M)
    return bool(m and not is_placeholder(m.group(1)))


def load_handoff(workspace: Path):
    """读取并校验 handoff.json。

    返回 (是否存在, 校验错误列表, recommendation 或 None)。
    另通过返回 dict 的 "scope" 键携带豁免声明（handoff scope 字段）。"
    校验复用 validate_handoff.py 的 validate 逻辑（schema 为单一事实源）。
    """
    path = workspace / "handoff.json"
    if not path.is_file():
        return False, ["handoff.json 不存在"], None
    raw = read_text(path)
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        line = getattr(exc, "lineno", "?")
        return True, [f"handoff.json 不是合法 JSON（第 {line} 行）"], None

    sys.path.insert(0, str(SCRIPTS_DIR))
    import validate_handoff

    if not validate_handoff.SCHEMA_PATH.is_file():
        return True, [f"契约 schema 缺失：{validate_handoff.SCHEMA_PATH}，无法校验"], None
    schema = json.loads(validate_handoff.SCHEMA_PATH.read_text(encoding="utf-8"))
    errors: list = []
    validate_handoff.validate(data, schema, "", errors)
    # 骨架识别：init_workspace 生成的占位骨架虽能通过 schema 校验，
    # 但不代表已发生真实决策（decision_question 含待填写标记或为空）。
    if isinstance(data, dict):
        dq = str(data.get("decision_question") or "")
        if not dq.strip() or "待填写" in dq:
            errors.append("handoff.json 仍是未填写的骨架（decision_question 为占位内容）")
    rec = data.get("recommendation") if isinstance(data, dict) and not errors else None
    return True, errors, rec



# 法定账本文件（只在其行文提及「放行声明」时不作候选，防噪音）
_LEDGER_NAMES = {"decision_journal.md", "research_log.md", "judgment_contract.md",
                 "product_baseline.md", "prd.md", "roadmap.md", "risk_register.md"}
# 不放行判定词（出现即整份文件视为不放行，不论是否签署）
_NO_RELEASE_RE = re.compile(r"不放行|不予放行|禁止发布|NO[_ ]RELEASE", re.I)


def find_launch_release(workspace: Path):
    """在工作区（含 deliverables/）内查找已签署的 launch 放行声明文件。

    识别规则（R4 摩擦修订）：
    - 只把「文件名含 launch/checklist/放行」的 .md/.txt 作为候选（账本文件行文提及不计）；
    - 内容含不放行判定词 → 记为 denied（不放行），不论签署与否（防语义反转）；
    - 已签署 = 「声明人」一行的值非占位。
    返回 (signed, unsigned, denied) 三个相对路径列表。
    """
    signed, unsigned, denied = [], [], []
    if not workspace.is_dir():
        return signed, unsigned, denied
    for p in sorted(workspace.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in (".md", ".txt"):
            continue
        name = p.name.lower()
        if p.name in _LEDGER_NAMES:
            continue
        if not any(k in name for k in ("launch", "checklist", "放行")):
            continue
        content = read_text(p)
        if content is None or "放行声明" not in content:
            continue
        rel = str(p.relative_to(workspace))
        if _NO_RELEASE_RE.search(content):
            denied.append(rel)
            continue
        sig = re.search(r"声明人[^\n：:]*[：:]\s*(.+?)\s*$", content, re.M)
        if sig and not is_placeholder(sig.group(1)):
            signed.append(rel)
        else:
            unsigned.append(rel)
    return signed, unsigned, denied


def main_documents(deliverables: Path):
    """列出 deliverables/ 下的成品主文档（排除简报/指标字典/可读性与质量报告）。"""
    docs = []
    if not deliverables.is_dir():
        return docs
    for p in sorted(deliverables.glob("*.md")):
        n = p.name.lower()
        if p.name in ("brief.md", "metrics.md"):
            continue
        if re.search(r"(^|_)readability_report\.md$", n) or re.search(r"(^|_)quality_report\.md$", n):
            continue
        docs.append(p)
    return docs


def has_report(deliverables: Path, kind: str) -> bool:
    """检查 deliverables/ 下是否存在指定类型报告（全局或按主文档命名）。"""
    return (deliverables / f"{kind}_report.md").is_file() or any(deliverables.glob(f"*_{kind}_report.md"))


# ---------------------------------------------------------------------------
# 环节求值器：每个返回 {"id","name","status","passed","total","missing","next_action","note"}
# ---------------------------------------------------------------------------

def _result(stage_id, name, checks, note="", next_action=None, forced=None):
    """汇总单环节结果。checks 为 [(判据描述, 是否通过, 缺失明细)]。"""
    passed = sum(1 for _, ok, _ in checks if ok)
    missing = [detail if detail else desc for desc, ok, detail in checks if not ok]
    status = forced or ("pass" if passed == len(checks) else "fail")
    return {
        "id": stage_id,
        "name": name,
        "status": status,
        "passed": passed,
        "total": len(checks),
        "missing": missing,
        "next_action": None if status in ("pass", "blocked") else (next_action or NEXT_ACTIONS[stage_id]),
        "note": note,
    }


def eval_stage0(ctx) -> dict:
    """环节 0 工作区：目录存在、decision_journal.md 与 research_log.md 存在。"""
    ws = ctx["workspace"]
    checks = [
        ("工作区目录存在", ws.is_dir(), f"目录不存在：{ws}"),
        ("decision_journal.md（决策日志）存在", (ws / "decision_journal.md").is_file(), "缺 decision_journal.md"),
        ("research_log.md（研究日志）存在", (ws / "research_log.md").is_file(), "缺 research_log.md"),
    ]
    return _result("0", "工作区", checks)


def eval_stage1(ctx) -> dict:
    """环节 1 机会验证：研究结论卡 ≥1 张；假设台账 ≥1 条且每条有四态标签。"""
    log = ctx["research_log"]
    if log is None:
        checks = [
            ("研究结论卡 ≥1 张", False, "research_log.md 缺失（先过环节 0）"),
            ("假设台账 ≥1 条且每条有四态标签", False, "research_log.md 缺失（先过环节 0）"),
        ]
        return _result("1", "机会验证", checks)
    cards = count_conclusion_cards(log)
    hypos = hypothesis_rows(log)
    bad = [hid for hid, ok in hypos if not ok]
    if not hypos:
        hypo_ok, hypo_detail = False, "假设台账无有效条目（H-xx 编号且内容非占位）"
    elif bad:
        hypo_ok, hypo_detail = False, f"假设台账存在缺四态标签的条目：{', '.join(bad)}"
    else:
        hypo_ok, hypo_detail = True, ""
    checks = [
        ("研究结论卡 ≥1 张（【研究结论卡】且结论非占位）", cards >= 1,
         "无已填写的研究结论卡（模板示例卡不计入）"),
        ("假设台账 ≥1 条且每条有四态标签", hypo_ok, hypo_detail),
    ]
    return _result("1", "机会验证", checks)


def eval_stage2(ctx) -> dict:
    """环节 2 决策：handoff.json 存在且通过 validate_handoff 校验；judgment_contract.md 存在。"""
    ws = ctx["workspace"]
    exists, errors, _ = ctx["handoff"]
    checks = [
        ("handoff.json 存在", exists, "缺 handoff.json（每次决策都须产出存档）"),
        ("handoff.json 通过 validate_handoff 契约校验", exists and not errors,
         "；".join(errors) if errors else ("handoff.json 缺失，无从校验（见上一条）" if not exists else "")),
        ("judgment_contract.md（判断合同）存在", (ws / "judgment_contract.md").is_file(),
         "缺 judgment_contract.md（可用 init_workspace.py --with-contract 生成）"),
    ]
    return _result("2", "决策", checks)


def eval_stage3(ctx) -> dict:
    """环节 3 产品落地：GO 时强校验 product_baseline.md；NO_GO/ABSTAIN 标 blocked。"""
    exists, errors, rec = ctx["handoff"]
    if rec == "GO":
        ws = ctx["workspace"]
        checks = [
            ("product_baseline.md（产品基线）存在", (ws / "product_baseline.md").is_file(),
             "缺 product_baseline.md（GO 后进入落地环节前必须建立统一基线）"),
        ]
        return _result("3", "产品落地", checks)
    if rec in ("NO_GO", "ABSTAIN"):
        return _result("3", "产品落地", [], forced="blocked",
                       note=f"handoff recommendation={rec}，按契约不进入环节 3")
    return _result("3", "产品落地",
                   [("存在通过契约校验的 handoff.json", False, "环节 2 未通过，无法判定是否允许进入")],
                   next_action="先完成环节 2（决策）：补 judgment_contract.md 并写入通过校验的 handoff.json")


def eval_stage4(ctx) -> dict:
    """环节 4 发布上市（可选环节）：GO 时要求存在已签署的 launch 放行声明文件。"""
    _, _, rec = ctx["handoff"]
    if rec != "GO":
        return _result("4", "发布上市", [], forced="pending",
                       note="可选环节：无 handoff GO + 发布意图，暂不进入")
    signed, unsigned, denied = find_launch_release(ctx["workspace"])
    if denied:
        checks = [("放行声明通过", False,
                   f"存在不放行声明（门保持关闭，正确行为）：{', '.join(denied)}")]
    elif signed:
        checks = [(f"已签署放行声明（{', '.join(signed)}）", True, "")]
    elif unsigned:
        checks = [("放行声明已签署（声明人/日期/证据清单）", False,
                   f"存在含放行声明的文件但声明人未签署：{', '.join(unsigned)}")]
    else:
        checks = [("存在 launch 放行声明文件", False,
                   "工作区（含 deliverables/）内未找到含「放行声明」的 launch 文件")]
    return _result("4", "发布上市", checks)


def eval_stage45(ctx) -> dict:
    """环节 4.5 成果交付：deliverables/brief.md 存在；有主文档时须配可读性/质量报告。"""
    ws = ctx["workspace"]
    _, _, rec = ctx["handoff"]
    deliverables = ws / "deliverables"
    brief = deliverables / "brief.md"
    if rec != "GO" and not brief.is_file():
        return _result("4.5", "成果交付", [], forced="pending",
                       note="GO 后自动触发的环节：无 GO 且 deliverables/brief.md 不存在，暂不进入")
    checks = [
        ("deliverables/brief.md（项目简报）存在", brief.is_file(),
         "缺 deliverables/brief.md（成果转化引擎统一输入契约）"),
    ]
    docs = main_documents(deliverables)
    if docs:
        names = ", ".join(p.name for p in docs)
        checks.append((f"主文档（{names}）配有 readability_report", has_report(deliverables, "readability"),
                       f"主文档 {names} 缺可读性报告（deliverables/readability_report.md 或 <主文档>_readability_report.md）"))
        checks.append((f"主文档（{names}）配有 quality_report", has_report(deliverables, "quality"),
                       f"主文档 {names} 缺质量核对报告（deliverables/quality_report.md 或 <主文档>_quality_report.md）"))
    return _result("4.5", "成果交付", checks)


def eval_stage5(ctx) -> dict:
    """环节 5 运营复盘：存在已结算预测时检查命中率自查节；无已结算标 pending。"""
    journal = ctx["journal"]
    if journal is None:
        return _result("5", "运营复盘", [], forced="pending",
                       note="decision_journal.md 缺失（先过环节 0）")
    settled = settled_predictions(journal)
    if not settled:
        return _result("5", "运营复盘", [], forced="pending",
                       note="预测登记表中无已结算预测（状态/结果列无「成真/落空」），未到复盘时点")
    checks = [
        (f"存在已结算预测（{len(settled)} 条）", True, ""),
        ("「命中率自查」节有实质内容（已结算预测数/结论）", hitrate_section_filled(journal),
         "已有已结算预测，但「命中率自查」节未填写（样本 <20 条也须明说「样本不足」）"),
    ]
    return _result("5", "运营复盘", checks)


# 规则表：环节顺序、名称与求值函数（扩展新环节 = 追加一行 + 一个求值函数）
STAGES = [
    ("0", "工作区", eval_stage0),
    ("1", "机会验证", eval_stage1),
    ("2", "决策", eval_stage2),
    ("3", "产品落地", eval_stage3),
    ("4", "发布上市", eval_stage4),
    ("4.5", "成果交付", eval_stage45),
    ("5", "运营复盘", eval_stage5),
]


def load_scope(workspace: Path) -> dict:
    """读取 handoff.json 的 scope 豁免声明（无文件/无字段/非法 JSON 时为空 dict）。"""
    try:
        data = json.loads(read_text(workspace / "handoff.json"))
    except Exception:  # noqa: BLE001
        return {}
    scope = data.get("scope") if isinstance(data, dict) else None
    return scope if isinstance(scope, dict) else {}


def build_context(workspace: Path) -> dict:
    """汇总各环节求值所需的只读上下文。"""
    return {
        "workspace": workspace,
        "journal": read_text(workspace / "decision_journal.md"),
        "research_log": read_text(workspace / "research_log.md"),
        "handoff": load_handoff(workspace),
        "scope": load_scope(workspace),
    }


def summarize(stages: list) -> dict:
    """总览：chain_progress = 前缀连续 pass/blocked 推进到的环节；
    current_gate = 第一个 fail 环节，其次第一个 pending 环节，全无则 None。"""
    progress = None
    for s in stages:
        if s["status"] in ("pass", "blocked", "waived"):
            progress = s["id"]
        else:
            break
    gate = next((s for s in stages if s["status"] == "fail"), None)
    if gate is None:
        gate = next((s for s in stages if s["status"] == "pending"), None)
    current_gate = None if gate is None else {"id": gate["id"], "name": gate["name"], "status": gate["status"]}
    return {"chain_progress": progress, "current_gate": current_gate}


# ---------------------------------------------------------------------------
# 人类可读输出（East Asian 宽字符对齐）
# ---------------------------------------------------------------------------

def _width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _width(text))


def print_table(report: dict) -> None:
    print(f"IdeaToLaunch 链路体检：{report['workspace']}\n")
    header = f"{_pad('环节', 8)}{_pad('名称', 12)}{_pad('状态', 12)}判据"
    print(header)
    print("-" * _width(header))
    for s in report["stages"]:
        line = f"{_pad(s['id'], 8)}{_pad(s['name'], 12)}{_pad(STATUS_ICON[s['status']] + ' ' + s['status'], 12)}{s['passed']}/{s['total']}"
        print(line)
        if s["note"]:
            print(f"    说明：{s['note']}")
        for item in s["missing"]:
            print(f"    缺失：{item}")
        if s["next_action"]:
            print(f"    下一步：{s['next_action']}")
    summary = report["summary"]
    progress = summary["chain_progress"]
    progress_text = "（未起步）" if progress is None else f"环节 {progress}"
    gate = summary["current_gate"]
    gate_text = "全链路无 fail/pending 环节" if gate is None else f"环节 {gate['id']} {gate['name']}（{gate['status']}）"
    print(f"\n总览：chain_progress={progress_text}，current_gate={gate_text}")


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="IdeaToLaunch 全链路阶段门执行器：对项目工作区做链路体检，逐环节核查出口判据。"
    )
    parser.add_argument("workspace", help="项目工作区路径（init_workspace.py 创建的目录）")
    parser.add_argument("--json", action="store_true", help="输出全部结构化 JSON（默认人类可读表格）")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.exists():
        die(f"工作区路径不存在：{workspace}。先运行 python3 scripts/init_workspace.py <项目名> --dir <基目录> 初始化。")

    ctx = build_context(workspace)
    scope = ctx.get("scope") or {}
    waived = set(scope.get("waived_stages") or [])
    stages = []
    for sid, name, evaluate in STAGES:
        if sid in waived:
            stages.append({
                "id": sid, "name": name, "status": "waived",
                "passed": 0, "total": 0, "missing": [],
                "next_action": None,
                "note": f"用户知情豁免（handoff scope：{scope.get('note', '未注明理由')}）",
            })
            continue
        result = evaluate(ctx)
        if scope.get("no_launch") and sid in ("4", "4.5") and result["status"] == "fail":
            result["status"] = "pending"
            result["note"] = "scope.no_launch=true：本项目无发布/交付意图，保持 pending"
        stages.append(result)
    report = {
        "workspace": str(workspace),
        "stages": stages,
        "summary": summarize(stages),
        # 冗余一份平铺字段，便于直接取用
        "chain_progress": None,
        "current_gate": None,
    }
    report["chain_progress"] = report["summary"]["chain_progress"]
    report["current_gate"] = report["summary"]["current_gate"]

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_table(report)
    return 1 if any(s["status"] == "fail" for s in stages) else 0


if __name__ == "__main__":
    sys.exit(main())
