#!/usr/bin/env python3
"""投资 BP 初稿自动组装器（IdeaToLaunch 技能确定性工具，纯标准库）。

用法：
    python3 scripts/assemble_bp.py <工作区路径> [--out deliverables/bp_draft.md] [--type bp|report]

行为（环节 4.5 成果转化引擎的机械组装环节）：
    1. 读取工作区法定账本：handoff.json（必须 GO，否则报错退出码 2——
       非 GO 不进入成果交付）、research_log.md（解析研究结论卡区、假设台账区、
       最小实验登记、算式附录）、decision_journal.md，以及存在的 product_baseline.md；
    2. 按 templates/business-plan.md 的七章结构组装 BP 初稿（Markdown）：
       执行摘要 / 市场机会 / 为什么是我们 / 关键假设与风险 /
       计划与里程碑 / 什么会推翻这个计划 / 复盘与校准；
    3. 每个引用的数字/结论后自动附来源标注（〔H-03〕〔R-02〕〔算式 C-1〕），
       编号映射从账本机械解析：假设台账 H-xx 沿用原编号，研究结论卡按出现顺序
       编 R-xx，算式附录按行编 C-x；
    4. 账本中找不到内容的章节：写入「数据不足」占位并列出「待补清单」，
       绝不编造内容充数；末尾生成 coverage 统计（七章中几章有实内容、
       几个数字已挂编号、几个未挂）；
    5. 输出末尾自动附「假设与证据总登记处」（从假设台账 + 结论卡 + 算式附录生成）。

输出（stdout，JSON）：{"workspace", "out", "type", "chapters_with_content",
"chapters_total", "chapters_insufficient", "numbers_cited", "numbers_uncited",
"refs_used", "coverage"}
退出码：0 成功；2 参数/文件错误，或 handoff 非 GO。
"""

import argparse
import json
import re
import sys
from pathlib import Path


def die(message: str) -> None:
    """以中文可操作错误信息输出 JSON 并以退出码 2 终止。"""
    print(json.dumps({"error": message}, ensure_ascii=False), file=sys.stderr)
    sys.exit(2)


def emit(payload: dict) -> None:
    """输出 JSON 结果（保留中文，缩进便于直接阅读）。"""
    print(json.dumps(payload, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# 账本读取与解析
# ---------------------------------------------------------------------------

def read_ledger(path: Path, required: bool = True) -> str:
    """读取账本全文；必需账本缺失时报错退出码 2，可选账本缺失返回空串。"""
    if not path.is_file():
        if required:
            die(f"法定账本缺失：{path}。请先用 scripts/init_workspace.py 初始化工作区并如实登记。")
        return ""
    return path.read_text(encoding="utf-8")


def split_sections(text: str) -> dict:
    """按 Markdown 二级标题（## …）切分，返回 {标题: 正文}（标题不含 ## 前缀）。"""
    sections = {}
    current = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return {title: "\n".join(body) for title, body in sections.items()}


def find_section(sections: dict, keyword: str) -> str:
    """在二级标题中按关键词定位章节正文；找不到返回空串。"""
    for title, body in sections.items():
        if keyword in title:
            return body
    return ""


def parse_table_rows(text: str) -> list:
    """解析 Markdown 表格行，返回单元格列表的列表；自动跳过表头分隔行。"""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not (line.startswith("|") and line.endswith("|")):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells and all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
            continue  # 表头分隔行
        rows.append(cells)
    return rows


def strip_code_fences(text: str) -> str:
    """剔除 ``` 围栏代码块（模板中的示例结论卡在围栏内，不是真实账本内容）。"""
    return re.sub(r"```.*?```", "", text, flags=re.S)


def parse_conclusion_cards(section_text: str) -> list:
    """解析研究结论卡区：以「【研究结论卡】」分块，按出现顺序编号 R-01…。

    提取字段：结论 / 对应假设 / 证据等级 / 来源 / 时效。跳过模板占位块
    （围栏示例与结论字段为空或含「（填」的块视为占位，不入正文）。
    """
    cards = []
    blocks = strip_code_fences(section_text).split("【研究结论卡】")
    for block in blocks[1:]:
        def field(name: str) -> str:
            m = re.search(rf"^{re.escape(name)}：(.*)$", block, flags=re.M)
            return m.group(1).strip() if m else ""

        conclusion = field("结论")
        if not conclusion or "（填" in conclusion:
            continue
        cards.append({
            "id": f"R-{len(cards) + 1:02d}",
            "conclusion": conclusion,
            "assumptions": re.findall(r"H-\d+", field("对应假设")),
            "level": field("证据等级"),
            "source": field("来源"),
            "time": field("时效"),
        })
    return cards


def parse_hypotheses(section_text: str) -> list:
    """解析假设台账表格：编号列形如 H-xx 且内容列非模板占位的行。"""
    hypotheses = []
    for cells in parse_table_rows(section_text):
        if len(cells) < 2 or not re.fullmatch(r"H-\d+", cells[0]):
            continue
        if any("（填" in c for c in cells):
            continue  # 模板占位行
        hypotheses.append({
            "id": cells[0],
            "content": cells[1],
            "value": cells[2] if len(cells) > 2 else "",
            "status": cells[3] if len(cells) > 3 else "",
            "source": cells[4] if len(cells) > 4 else "",
        })
    return hypotheses


def parse_experiments(section_text: str) -> list:
    """解析最小实验登记表（ABSTAIN 实验可能携带证伪判据，供第六章引用）。"""
    experiments = []
    for cells in parse_table_rows(section_text):
        if len(cells) < 2 or not re.fullmatch(r"E-\d+", cells[0]):
            continue
        content = cells[1]
        criterion = cells[3] if len(cells) > 3 else ""
        # 空占位行（实验内容为空或判据仍是 ____ 模板占位）不入正文
        if not content or "（填" in content:
            continue
        if "____" in criterion:
            criterion = ""
        experiments.append({"id": cells[0], "content": content, "criterion": criterion})
    return experiments


def parse_formulas(section_text: str) -> list:
    """解析算式附录：每条非空、非括号说明的实质性行按顺序编号 C-1…。"""
    formulas = []
    for line in section_text.splitlines():
        line = line.strip().strip("`")
        if not line or line.startswith(("（", "(", ">", "#")):
            continue
        formulas.append({"id": f"C-{len(formulas) + 1}", "content": line})
    return formulas


def parse_journal_predictions(journal_text: str) -> list:
    """解析决策日志「预测登记」表：序号列为数字且预测内容非空的行。"""
    sections = split_sections(journal_text)
    body = find_section(sections, "预测登记")
    predictions = []
    for cells in parse_table_rows(body):
        if len(cells) < 3 or not cells[0].isdigit():
            continue
        if not cells[2] or cells[2] == "#":
            continue
        predictions.append({
            "no": cells[0],
            "date": cells[1],
            "content": cells[2],
            "probability": cells[3] if len(cells) > 3 else "",
            "deadline": cells[4] if len(cells) > 4 else "",
            "status": cells[6] if len(cells) > 6 else "",
        })
    return predictions


def parse_journal_decisions(journal_text: str) -> list:
    """解析决策日志「决策台账」表：序号列为数字且有实质内容的行。"""
    sections = split_sections(journal_text)
    body = find_section(sections, "决策台账")
    decisions = []
    for cells in parse_table_rows(body):
        if len(cells) < 3 or not cells[0].isdigit():
            continue
        if all(not c for c in cells[1:]):
            continue
        decisions.append({"no": cells[0], "date": cells[1], "decision": cells[2]})
    return decisions


def parse_baseline(baseline_text: str) -> dict:
    """解析产品基线（可选账本）：产品定义要点与关键参数表非占位行。"""
    if not baseline_text:
        return {"definitions": [], "parameters": [], "lifecycle": []}
    sections = split_sections(baseline_text)

    definitions = []
    for line in find_section(sections, "产品定义").splitlines():
        line = line.strip()
        if line.startswith("- ") and "：" in line:
            key, _, value = line[2:].partition("：")
            if value.strip():
                definitions.append((key.strip(), value.strip()))

    parameters = []
    for cells in parse_table_rows(find_section(sections, "关键参数表")):
        if len(cells) < 2 or cells[0] == "参数" or not cells[1]:
            continue
        if cells[0].startswith("例："):
            continue  # 模板示例行
        parameters.append({
            "name": cells[0],
            "value": cells[1],
            "tag": cells[2] if len(cells) > 2 else "",
            "source": cells[3] if len(cells) > 3 else "",
        })

    lifecycle = []
    for line in find_section(sections, "生命周期状态").splitlines():
        line = line.strip()
        if line.startswith("- ") and "：" in line:
            key, _, value = line[2:].partition("：")
            if value.strip():
                lifecycle.append((key.strip(), value.strip()))
    return {"definitions": definitions, "parameters": parameters, "lifecycle": lifecycle}


# ---------------------------------------------------------------------------
# 编号标注与统计
# ---------------------------------------------------------------------------

def cite(*ref_ids) -> str:
    """把编号列表渲染为来源标注串，如 〔H-03〕〔R-02〕。"""
    return "".join(f"〔{r}〕" for r in ref_ids if r)


# 统计口径：剔除 〔…〕标注与 H-xx/R-xx/C-x 编号本身后，正文里剩余的数字
_NUMBER_RE = re.compile(r"(?<![-\w])\d+(?:\.\d+)?")
_ID_RE = re.compile(r"[HREC]-\d+|〔[^〕]*〕")


def count_numbers(line: str) -> int:
    """统计一行正文中"数字"个数（排除编号标注本身）。"""
    cleaned = _ID_RE.sub("", line)
    return len(_NUMBER_RE.findall(cleaned))


# ---------------------------------------------------------------------------
# 七章组装
# ---------------------------------------------------------------------------

# 各章「待补清单」：账本缺内容时如实列出缺口，禁止编造
CHAPTER_TITLES = [
    "第一章 执行摘要",
    "第二章 市场机会",
    "第三章 为什么是我们",
    "第四章 关键假设与风险",
    "第五章 计划与里程碑",
    "第六章 什么会推翻这个计划",
    "第七章 复盘与校准",
]

TODO_BY_CHAPTER = {
    0: ["在 handoff.json 的 judgment_contract 中补全五段判断合同（当前判断/理由/下一步）"],
    1: ["在 research_log.md 研究结论卡区补充市场/规模/竞品结论卡（带来源与时效），"
        "市场规模按 TAM/SAM/SOM 双法交叉（可用 scripts/calc.py tam，算式入附录）"],
    2: ["在 product_baseline.md 补全产品定义与关键参数表（带事实状态标签），"
        "并在 research_log.md 结论卡区补充优势/壁垒的可验证证据"],
    3: ["在 research_log.md 假设台账区登记关键假设（H-xx，四态标签），"
        "并在 handoff.json 补 critical_uncertainties / residual_risks"],
    4: ["在 handoff.json judgment_contract.next_step 写明下一步，"
        "在 product_baseline.md 生命周期状态区登记当前阶段，"
        "决策台账登记已发生的商业决策"],
    5: ["在 handoff.json judgment_contract.what_would_change_my_mind 写明翻转条件，"
        "（如有 ABSTAIN 实验）在 research_log.md 最小实验登记区补证伪判据"],
    6: ["在 decision_journal.md 预测登记表登记可结算预测（先登记后结算）"],
}


def insufficient_block(chapter_index: int) -> list:
    """生成「数据不足」占位与待补清单。"""
    lines = [
        "> **数据不足**：本章在法定账本中未找到可用内容，按纪律不编造，先列补齐计划。",
        "",
        "待补清单：",
    ]
    lines += [f"- [ ] {item}" for item in TODO_BY_CHAPTER[chapter_index]]
    return lines


def build_chapters(handoff: dict, cards: list, hypotheses: list, experiments: list,
                   formulas: list, predictions: list, decisions: list, baseline: dict) -> list:
    """按七章结构机械组装；每章返回 (标题, 行列表, 是否有实内容)。"""
    chapters = []
    contract = handoff.get("judgment_contract") or {}

    def contract_lines(mapping) -> list:
        return [f"- {label}：{contract[field]}"
                for field, label in mapping if contract.get(field)]

    # 第一章 执行摘要
    lines = []
    if contract:
        lines += contract_lines([
            ("current_judgment", "一句话结论"),
            ("rationale", "核心理由"),
            ("next_step", "本轮需要的决策/下一步"),
        ])
    constraints = handoff.get("constraints") or []
    if constraints:
        lines.append("- 硬约束：" + "；".join(constraints))
    confidence = handoff.get("confidence")
    if confidence is not None:
        lines.append(f"- 置信度：{confidence}（未经校准时按契约为 null，不得编造）")
    for a in handoff.get("key_assumptions") or []:
        refs = cite(*re.findall(r"H-\d+", " ".join(a.get("evidence_refs") or [])))
        note = refs if refs else "（未挂账本编号，需回填）"
        lines.append(f"- 关键假设：{a['statement']}（{a['status']}）{note}")
    chapters.append((CHAPTER_TITLES[0], lines, bool(lines)))

    # 第二章 市场机会（结论卡中与市场相关的部分）
    lines = []
    market_kw = re.compile(r"市场|TAM|SAM|SOM|规模|竞品|竞争|增长|份额|渗透率")
    for card in cards:
        if market_kw.search(card["conclusion"]):
            meta = "，".join(x for x in [f"证据等级 {card['level']}" if card["level"] else "",
                                        f"来源：{card['source']}" if card["source"] else "",
                                        f"时效：{card['time']}" if card["time"] else ""] if x)
            lines.append(f"- {card['conclusion']}（{meta}）{cite(card['id'], *card['assumptions'])}")
    chapters.append((CHAPTER_TITLES[1], lines, bool(lines)))

    # 第三章 为什么是我们
    lines = []
    for key, value in baseline["definitions"]:
        lines.append(f"- {key}：{value}（product_baseline.md 产品定义）")
    for p in baseline["parameters"]:
        tag = f"，状态标签 {p['tag']}" if p["tag"] else ""
        lines.append(f"- 参数 {p['name']}：{p['value']}（{p['source'] or '基线登记'}{tag}）")
    edge_kw = re.compile(r"优势|差异化|壁垒|护城河|团队|专利|资质|独家")
    for card in cards:
        if edge_kw.search(card["conclusion"]):
            lines.append(f"- {card['conclusion']}{cite(card['id'], *card['assumptions'])}")
    chapters.append((CHAPTER_TITLES[2], lines, bool(lines)))

    # 第四章 关键假设与风险
    lines = []
    if hypotheses:
        lines += ["", "| # | 关键假设 | 数值/口径 | 状态 | 来源/依据 |",
                  "|---|---|---|---|---|"]
        for h in hypotheses:
            lines.append(f"| {h['id']} | {h['content']} | {h['value']} | {h['status']} | {h['source']} |")
        lines.append("")
    for u in handoff.get("critical_uncertainties") or []:
        lines.append(f"- 最大未知：{u}（handoff critical_uncertainties）")
    for r in handoff.get("residual_risks") or []:
        lines.append(f"- 残余风险：{r}（handoff residual_risks）")
    chapters.append((CHAPTER_TITLES[3], lines, bool(lines)))

    # 第五章 计划与里程碑
    lines = []
    if contract.get("next_step"):
        lines.append(f"- 下一步：{contract['next_step']}（handoff 判断合同）")
    for key, value in baseline["lifecycle"]:
        lines.append(f"- {key}：{value}（product_baseline.md 生命周期状态）")
    for d in decisions:
        lines.append(f"- 决策台账 #{d['no']}（{d['date']}）：{d['decision']}")
    chapters.append((CHAPTER_TITLES[4], lines, bool(lines)))

    # 第六章 什么会推翻这个计划
    lines = []
    if contract.get("what_would_change_my_mind"):
        lines.append(f"- 翻转条件：{contract['what_would_change_my_mind']}（handoff 判断合同）")
    if contract.get("biggest_unknown"):
        lines.append(f"- 最大未知：{contract['biggest_unknown']}（handoff 判断合同）")
    for e in experiments:
        criterion = f"；判据：{e['criterion']}" if e["criterion"] else ""
        lines.append(f"- 实验 {e['id']}：{e['content']}{criterion}（research_log 最小实验登记）")
    chapters.append((CHAPTER_TITLES[5], lines, bool(lines)))

    # 第七章 复盘与校准
    lines = []
    for p in predictions:
        prob = f"，概率 {p['probability']}" if p["probability"] else ""
        deadline = f"，到期 {p['deadline']}" if p["deadline"] else ""
        lines.append(f"- 预测 #{p['no']}（{p['date']}）：{p['content']}{prob}{deadline}，状态 {p['status']}")
    chapters.append((CHAPTER_TITLES[6], lines, bool(lines)))

    return chapters


def build_registry(hypotheses: list, cards: list, formulas: list) -> list:
    """假设与证据总登记处：从假设台账 + 结论卡 + 算式附录机械生成。"""
    lines = [
        "## 假设与证据总登记处（所有章节引用此处编号）",
        "",
        "| 编号 | 类型 | 内容 | 状态 | 来源/依据 |",
        "|---|---|---|---|---|",
    ]
    for h in hypotheses:
        lines.append(f"| {h['id']} | 假设 | {h['content']} | {h['status']} | {h['source']} |")
    for card in cards:
        meta = "；".join(x for x in [card["source"], card["time"]] if x)
        lines.append(f"| {card['id']} | 证据 | {card['conclusion']} | {card['level']} | {meta} |")
    for f in formulas:
        lines.append(f"| {f['id']} | 算式 | {f['content']} | — | research_log 算式附录 |")
    if not (hypotheses or cards or formulas):
        lines.append("| — | — | （账本为空，登记处待补） | — | — |")
    return lines


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="投资 BP 初稿自动组装器（从法定账本机械组装，不编造数字）")
    parser.add_argument("workspace", help="项目工作区路径（含 handoff.json 等法定账本）")
    parser.add_argument("--out", default="deliverables/bp_draft.md",
                        help="输出路径（相对工作区；默认 deliverables/bp_draft.md）")
    parser.add_argument("--type", choices=["bp", "report"], default="bp",
                        help="文档类型：bp=投资 BP 初稿（默认），report=深度调研报告初稿")
    args = parser.parse_args(argv)

    workspace = Path(args.workspace)
    if not workspace.is_dir():
        die(f"工作区不存在：{workspace}。请先运行 scripts/init_workspace.py 初始化。")

    # 1. handoff.json：非 GO 不进入成果交付（纪律机械化）
    handoff_path = workspace / "handoff.json"
    if not handoff_path.is_file():
        die(f"handoff.json 缺失：{handoff_path}。决策结论必须先存档并通过契约校验。")
    try:
        handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        die(f"handoff.json 不是合法 JSON：第 {exc.lineno} 行，{exc.msg}。"
            f"请修正后运行 scripts/validate_handoff.py 校验。")
    recommendation = handoff.get("recommendation")
    if recommendation != "GO":
        die(f"非 GO 不进入成果交付：handoff recommendation={recommendation!r}。"
            f"NO_GO 停止、ABSTAIN 先做最小实验；GO 之后再运行本组装器。")

    # 2. 读取并解析各法定账本
    research_text = read_ledger(workspace / "research_log.md")
    journal_text = read_ledger(workspace / "decision_journal.md")
    baseline_text = read_ledger(workspace / "product_baseline.md", required=False)

    research_sections = split_sections(research_text)
    cards = parse_conclusion_cards(find_section(research_sections, "研究结论卡"))
    hypotheses = parse_hypotheses(find_section(research_sections, "假设台账"))
    experiments = parse_experiments(find_section(research_sections, "最小实验"))
    formulas = parse_formulas(find_section(research_sections, "算式附录"))
    predictions = parse_journal_predictions(journal_text)
    decisions = parse_journal_decisions(journal_text)
    baseline = parse_baseline(baseline_text)

    # 3. 组装七章 + 登记处
    doc_title = "投资 BP（初稿）" if args.type == "bp" else "深度调研报告（初稿）"
    project_name = (handoff.get("project") or {}).get("name", workspace.name)
    body = [
        f"# {doc_title}：{project_name}",
        "",
        f"> 本初稿由 scripts/assemble_bp.py 从工作区法定账本机械组装；"
        f"素材包之外的数字不得成稿，每个数字挂账本编号；数据不足的章节如实标注。",
        f"> 决策结论：GO｜决策问题：{handoff.get('decision_question', '')}",
        "",
    ]

    chapters = build_chapters(handoff, cards, hypotheses, experiments,
                              formulas, predictions, decisions, baseline)
    chapters_with_content = 0
    chapters_insufficient = []
    numbers_cited = 0
    numbers_uncited = 0
    refs_used = set()

    for index, (title, lines, has_content) in enumerate(chapters):
        body.append(f"## {title}")
        body.append("")
        if not has_content:
            chapters_insufficient.append(title)
            body += insufficient_block(index)
        else:
            chapters_with_content += 1
            body += lines
            for line in lines:
                # 假设台账表格行以 H-xx 编号为首列，编号本身即来源标注
                row_id = re.match(r"\|\s*([HREC]-\d+)\s*\|", line)
                if "〔" in line or row_id:
                    numbers_cited += count_numbers(line)
                    refs_used.update(re.findall(r"〔([^〕]+)〕", line))
                    if row_id:
                        refs_used.add(row_id.group(1))
                else:
                    numbers_uncited += count_numbers(line)
        body.append("")

    # 4. coverage 统计（如实呈现，不粉饰）
    body += [
        "---",
        "",
        "## 覆盖率统计（组装器自动生成）",
        "",
        f"- 章节覆盖：七章中 {chapters_with_content}/7 章有实内容；"
        f"数据不足章节：{'、'.join(chapters_insufficient) if chapters_insufficient else '无'}",
        f"- 数字挂编号：已挂 {numbers_cited} 个；未挂 {numbers_uncited} 个"
        + ("（未挂编号的数字须回填账本编号或删除）" if numbers_uncited else ""),
        f"- 引用编号：{'、'.join(sorted(refs_used)) if refs_used else '无'}",
        "",
    ]

    # 5. 假设与证据总登记处
    body += build_registry(hypotheses, cards, formulas)
    body.append("")

    # 6. 落盘 + JSON 状态输出
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = workspace / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(body), encoding="utf-8")

    emit({
        "workspace": str(workspace),
        "out": str(out_path),
        "type": args.type,
        "chapters_with_content": chapters_with_content,
        "chapters_total": len(chapters),
        "chapters_insufficient": chapters_insufficient,
        "numbers_cited": numbers_cited,
        "numbers_uncited": numbers_uncited,
        "refs_used": sorted(refs_used),
        "coverage": f"七章中 {chapters_with_content}/7 章有实内容；"
                    f"{numbers_cited} 个数字已挂编号，{numbers_uncited} 个未挂",
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
