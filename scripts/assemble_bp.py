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
    4. 每章填充前做主题匹配：账本中该章主题内容缺失的章节，写入「数据不足」
       占位并列出「待补清单」，绝不填入错配内容充数；凡有数据不足章节，
       在执行摘要开头置顶显著警示块（列出缺口章号）；
    5. 文首自动附「标签图例」（假设四态释义固定输出；参数八态/判定词释义仅在
       正文实际使用时输出）；正文
       面向外部读者：自动清除内部文件路径、S0-S8 阶段码/环节码/声明门等
       内部术语白话化、英文判定词译中文；
    6. 末尾生成 coverage 统计（仅统计带单位数字，口径在文中注明），
       并自动附「假设与证据总登记处」（从假设台账 + 结论卡 + 算式附录生成）。

输出（stdout，JSON）：{"workspace", "out", "type", "chapters_with_content",
"chapters_total", "chapters_insufficient", "numbers_cited", "numbers_uncited",
"refs_used", "coverage"}
退出码：0 成功；2 参数/文件错误，或 handoff 非 GO。
"""

import argparse
import difflib
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


# 统计口径（收紧）：只统计"带单位的数字"——kg/MPa/元/万元/亿元/人日/%/天/月/年
# 邻接数值；年份（19xx/20xx）与比例代号（1:1、1:6 等）不计入，避免误导。
_ID_RE = re.compile(r"[HREC]-\d+|〔[^〕]*〕")
_YEAR_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}\s*年?")
_UNITED_NUMBER_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:万元|亿元|kg|MPa|人日|元|%|％|天|月|年)")

COVERAGE_NOTE = ("口径：仅统计带单位数字"
                 "（kg/MPa/元/万元/亿元/人日/%/天/月/年 邻接数值；年份与比例代号不计入）")


def count_numbers(line: str) -> int:
    """统计一行正文中"带单位数字"个数（排除编号标注与年份本身）。"""
    cleaned = _YEAR_RE.sub("", _ID_RE.sub("", line))
    return len(_UNITED_NUMBER_RE.findall(cleaned))


# ---------------------------------------------------------------------------
# 内部痕迹清洗（输出面向外部读者：去内部路径、内部术语白话化）
# ---------------------------------------------------------------------------

# 内部账本/字段名 → 外部读者可读的白话
_INTERNAL_TERM_MAP = [
    ("product_baseline.md 生命周期状态", "产品基线·生命周期状态"),
    ("product_baseline.md 产品定义", "产品基线·产品定义"),
    ("handoff critical_uncertainties", "决策交接包·最大未知清单"),
    ("handoff residual_risks", "决策交接包·残余风险清单"),
    ("handoff 判断合同", "判断合同"),
    ("research_log 最小实验登记", "研究日志·最小实验登记"),
    ("research_log 算式附录", "研究日志·算式附录"),
    ("product_baseline.md", "产品基线"),
    ("research_log.md", "研究日志"),
    ("decision_journal.md", "决策日志"),
    ("judgment_contract.md", "判断合同"),
    ("handoff.json", "决策交接包"),
]

# 环节码 → 白话环节名（与 SKILL.md 环节定义一致）
_STAGE_NAME = {"0": "意图理解", "1": "机会验证", "2": "决策", "3": "产品落地",
               "4": "发布上市", "4.5": "成果转化", "5": "运营复盘"}

# 阶段码 S0–S8（如 "S2 产品定义" → "产品定义阶段"）
_STAGE_CODE_RE = re.compile(r"(?<![A-Za-z0-9])S([0-8])(?![0-9])\s*([一-鿿][一-鿿/·]*)?")

# 英文判定词 → 中文（SKILL.md 纪律：面向用户必须译中文）
_VERDICT_MAP = {"healthy": "健康", "marginal": "及格线边缘", "unhealthy": "不健康"}

_INTERNAL_PATH_RE = re.compile(r"(?:references|templates|vendor|scripts)/[\w.\-/]+")

# 内部流程黑话：含这些词的全角括注整体删除（信息已在正文或编号中）；
# 裸出现时按下表白话化（面向外部读者，不留技能内部行话）
_JARGON_PAREN_RE = re.compile(
    r"（[^（）]*(?:决策交接包|判断合同|产品基线·|研究日志·|何时问用户|决策台账)[^（）]*）")
_JARGON_NAKED_MAP = [
    ("判断合同", "决策结论"),
    ("决策交接包", "决策交接材料"),
    ("决策台账", "决策记录"),
]


def scrub_internal(text: str) -> str:
    """清洗单行内容中的内部痕迹；保留账本编号〔H-xx〕等来源标注。"""
    # 1. 「见 内部路径」指引整体移除；其余内部路径 token 以占位说明替代
    text = re.sub(r"见\s*" + _INTERNAL_PATH_RE.pattern, "", text)
    text = _INTERNAL_PATH_RE.sub("（内部路径，已略）", text)
    text = re.sub(r"[（(]\s*[）)]", "", text)  # 清出空括注
    # 2. 内部账本/字段名白话化
    for old, new in _INTERNAL_TERM_MAP:
        text = text.replace(old, new)
    # 2.5 内部流程词：全角括注整体删除，裸出现白话化；随后清理多余空格与连续标点
    text = _JARGON_PAREN_RE.sub("", text)
    for old, new in _JARGON_NAKED_MAP:
        text = text.replace(old, new)
    text = re.sub(r"(?<=.) {2,}", " ", text)  # 折叠行内多余空格，保留行首列表缩进
    text = re.sub(r"\s+([，。；：、？！）])", r"\1", text)
    text = re.sub(r"（\s+", "（", text)
    text = re.sub(r"([。；，：])\1+", r"\1", text)
    text = text.rstrip()
    # 3. 环节码白话化（先处理「环节1机会验证」连写，再处理裸「环节1」；4.5 先于 4）
    for num in ("4.5", "0", "1", "2", "3", "4", "5"):
        name = _STAGE_NAME[num]
        text = text.replace(f"环节{num}{name}", f"{name}环节")
        text = re.sub(rf"环节\s*{re.escape(num)}(?![0-9.])", f"{name}环节", text)
    # 4. 阶段码 S0–S8 白话化
    text = _STAGE_CODE_RE.sub(
        lambda m: (m.group(2) + "阶段") if m.group(2) else f"第{m.group(1)}阶段", text)
    # 5. 其他内部术语白话化
    text = text.replace("声明门", "阶段放行确认点")
    # 6. 英文判定词译中文
    for en, zh in _VERDICT_MAP.items():
        text = re.sub(rf"(?<![A-Za-z]){en}(?![A-Za-z])", zh, text)
    return text


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
    2: ["在 research_log.md 研究结论卡区补充『优势/差异化/壁垒/团队』主题的可验证结论卡"
        "（本章主题为「为什么是我们」；产品参数表等主题不匹配的内容按纪律不填入本章）"],
    3: ["在 research_log.md 假设台账区登记关键假设（H-xx，四态标签），"
        "并在 handoff.json 补 critical_uncertainties / residual_risks"],
    4: ["在 handoff.json judgment_contract.next_step 写明下一步，"
        "在 product_baseline.md 生命周期状态区登记当前阶段，"
        "决策台账登记已发生的商业决策"],
    5: ["在 handoff.json judgment_contract.what_would_change_my_mind 写明翻转条件，"
        "（如有 ABSTAIN 实验）在 research_log.md 最小实验登记区补证伪判据"],
    6: ["在 decision_journal.md 预测登记表登记可结算预测（先登记后结算）"],
}


def assumption_count_summary(key_assumptions: list, hypotheses: list) -> str:
    """执行摘要假设数量口径：交接包登记数与假设台账在册数对账。

    两者一致时照常写「共 N 项」；不一致时两数并陈并给出差额（数量不一致
    本身即账本治理缺口），绝不只选一个数充数。
    """
    n_handoff = len(key_assumptions)
    n_ledger = len(hypotheses)
    if not hypotheses or n_handoff == n_ledger:
        return f"共 {n_handoff} 项关键假设"
    ids = [h["id"] for h in hypotheses]
    span = f"{ids[0]}~{ids[-1]}" if len(ids) > 1 else ids[0]
    return (f"交接包登记 {n_handoff} 项、台账在册 {n_ledger} 项（{span}），"
            f"差 {abs(n_handoff - n_ledger)} 项待补登")


# 假设四态固定顺序（结论式表题计数口径）
HYPOTHESIS_STATES = ("VERIFIED", "ESTIMATED", "ASSUMED", "UNVERIFIED")


def hypothesis_table_title(hypotheses: list) -> str:
    """假设表结论式标题：状态计数由台账内容机械计算，UNVERIFIED 行列出编号。

    台账为空或存在四态之外的状态（算不出来）时退回描述性标题，不编造计数。
    """
    if not hypotheses:
        return "关键假设"
    counts = {s: 0 for s in HYPOTHESIS_STATES}
    for h in hypotheses:
        status = h["status"].strip().upper()
        if status not in counts:
            return "关键假设（ASSUMED/UNVERIFIED 高关注行）"  # 算不出来 → 描述性
        counts[status] += 1
    title = (f"{len(hypotheses)} 项关键假设："
             + " / ".join(f"{s} {counts[s]}" for s in HYPOTHESIS_STATES))
    unverified_ids = [h["id"] for h in hypotheses
                      if h["status"].strip().upper() == "UNVERIFIED"]
    if unverified_ids:
        title += f"（{'、'.join(unverified_ids)}）"
    return title


def registry_table_title(hypotheses: list, cards: list, formulas: list) -> str:
    """登记处合表结论式标题：分类计数；全空时返回空串（退回占位行，不编造）。"""
    total = len(hypotheses) + len(cards) + len(formulas)
    if not total:
        return ""
    parts = []
    if hypotheses:
        parts.append(f"假设 {len(hypotheses)}")
    if cards:
        parts.append(f"证据 {len(cards)}")
    if formulas:
        parts.append(f"算式 {len(formulas)}")
    return f"登记处共 {total} 条：{' / '.join(parts)}"


def match_hypothesis_id(statement: str, hypotheses: list) -> str:
    """把执行摘要假设语句匹配回假设台账编号（字符序列相似度最高且 ≥0.5 的 H-xx）。"""
    core = re.sub(r"（[^（）]*）", "", statement)
    best_id, best_ratio = "", 0.0
    for h in hypotheses:
        ratio = difflib.SequenceMatcher(None, core, h["content"]).ratio()
        if ratio > best_ratio:
            best_id, best_ratio = h["id"], ratio
    return best_id if best_ratio >= 0.5 else ""


# 约束前缀标签去重：父级已是「硬约束」，条目自身的「…硬约束：」前缀只保留限定词
_CONSTRAINT_PREFIX_RE = re.compile(r"^(.{0,12}?)硬约束：")


def dedup_constraint_prefix(item: str) -> str:
    """『结构方案硬约束：…』→『结构方案：…』；『硬约束：…』→『…』（去掉与父级重复的标签）。"""
    m = _CONSTRAINT_PREFIX_RE.match(item)
    if not m:
        return item
    head = m.group(1).strip("： ")
    return (f"{head}：" if head else "") + item[m.end():]


def wrap_constraint_item(text: str, limit: int = 60) -> list:
    """单项 ≤limit 字；超出部分在标点边界（、，；。）语义换行，供调用方缩进续行。"""
    if len(text) <= limit:
        return [text]
    chunks, cur = [], ""
    for seg in re.split(r"(?<=[、，；。])", text):
        if cur and len(cur) + len(seg) > limit:
            chunks.append(cur)
            cur = seg
        else:
            cur += seg
    if cur:
        chunks.append(cur)
    pieces = []
    for chunk in chunks:  # 无标点长句兜底硬切
        while len(chunk) > limit:
            pieces.append(chunk[:limit])
            chunk = chunk[limit:]
        pieces.append(chunk)
    return pieces


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
        # 硬约束渲染为无序列表：每条一项、每项 ≤60 字（超出部分语义换行缩进），
        # 不拼接成多冒号嵌套长句；条目前缀与父级「硬约束」重复的标签去重
        lines.append("- 硬约束：")
        for item in constraints:
            pieces = wrap_constraint_item(dedup_constraint_prefix(item))
            lines.append(f"  - {pieces[0]}")
            lines += [f"    {p}" for p in pieces[1:]]
    confidence = handoff.get("confidence")
    if confidence is not None:
        lines.append(f"- 置信度：{confidence}（未经校准时按契约为 null，不得编造）")
    key_assumptions = handoff.get("key_assumptions") or []
    if key_assumptions and hypotheses:
        # 与第四章假设表大面积重复 → 摘要只保留一句汇总，不逐条重复
        unverified = [a for a in key_assumptions if a.get("status") == "UNVERIFIED"]
        summary = assumption_count_summary(key_assumptions, hypotheses)
        if unverified:
            tags = []
            for a in unverified:
                hid = match_hypothesis_id(a.get("statement", ""), hypotheses)
                if hid:
                    content = next(h["content"] for h in hypotheses if h["id"] == hid)
                else:
                    content = re.sub(r"（[^（）]*）", "", a.get("statement", ""))
                if len(content) > 24:
                    content = content[:24] + "…"
                tags.append(f"{hid} {content}".strip())
            summary += f"，其中 {len(unverified)} 项未验证（{'；'.join(tags)}）"
        lines.append(f"- 关键假设：{summary}，明细见第四章")
    elif key_assumptions:
        # 无第四章假设表可对照时才逐条列出；「未挂编号」提示全文最多出现一次
        note_emitted = False
        for a in key_assumptions:
            refs = cite(*re.findall(r"H-\d+", " ".join(a.get("evidence_refs") or [])))
            if refs:
                note = refs
            elif not note_emitted:
                note = "（未挂账本编号，需回填）"
                note_emitted = True
            else:
                note = "（同上）"
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

    # 第三章 为什么是我们（主题匹配纪律：只收"优势/壁垒/团队"类内容；
    # 基线参数表是产品规格而非"为什么是我们"，主题不匹配一律不填——
    # 账本中该章主题内容缺失时整章标「数据不足」，诚实纪律优先于覆盖率）
    lines = []
    edge_kw = re.compile(r"优势|差异化|壁垒|护城河|团队|专利|资质|独家")
    for card in cards:
        if edge_kw.search(card["conclusion"]):
            lines.append(f"- {card['conclusion']}{cite(card['id'], *card['assumptions'])}")
    for h in hypotheses:
        if edge_kw.search(h["content"]):
            lines.append(f"- {h['content']}（{h['status']}）〔{h['id']}〕")
    chapters.append((CHAPTER_TITLES[2], lines, bool(lines)))

    # 第四章 关键假设与风险（假设表单点维护：全量台账只在文末登记处出现；
    # 本章只渲染结论式标题 + ASSUMED/UNVERIFIED 高关注行 + 登记处指针，
    # 避免与登记处整表重复——三轮评审均指出该重复）
    lines = []
    if hypotheses:
        attention = [h for h in hypotheses
                     if h["status"].strip().upper() in ("ASSUMED", "UNVERIFIED")]
        lines += [f"**{hypothesis_table_title(hypotheses)}**", ""]
        if attention:
            lines += ["| # | 关键假设 | 数值/口径 | 状态 | 来源/依据 |",
                      "|---|---|---|---|---|"]
            for h in attention:
                lines.append(
                    f"| {h['id']} | {h['content']} | {h['value']} | {h['status']} | {h['source']} |")
            lines.append("")
        else:
            lines += ["- 当前无 ASSUMED/UNVERIFIED 假设（全部为 VERIFIED/ESTIMATED）。", ""]
        lines += ["完整假设台账见文末「假设与证据总登记处」。", ""]
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


def formula_conclusion(content: str) -> str:
    """算式单元格减负：只保留结论数字（「结果：」至句末）；无结果标记的短算式保留原文。"""
    m = re.search(r"结果：(.+?)(?:。|$)", content)
    return m.group(1).strip() if m else content


def build_registry(hypotheses: list, cards: list, formulas: list) -> list:
    """假设与证据总登记处：从假设台账 + 结论卡 + 算式附录机械生成。"""
    lines = [
        "## 假设与证据总登记处（所有章节引用此处编号）",
        "",
    ]
    title = registry_table_title(hypotheses, cards, formulas)
    if title:
        lines += [f"**{title}**", ""]
    lines += [
        "| 编号 | 类型 | 内容 | 状态 | 来源/依据 |",
        "|---|---|---|---|---|",
    ]
    for h in hypotheses:
        lines.append(scrub_internal(
            f"| {h['id']} | 假设 | {h['content']} | {h['status']} | {h['source']} |"))
    for card in cards:
        meta = "；".join(x for x in [card["source"], card["time"]] if x)
        lines.append(scrub_internal(
            f"| {card['id']} | 证据 | {card['conclusion']} | {card['level']} | {meta} |"))
    for f in formulas:
        lines.append(scrub_internal(
            f"| {f['id']} | 算式 | {formula_conclusion(f['content'])} | — | 算式明细附录（见下文） |"))
    if not (hypotheses or cards or formulas):
        lines.append("| — | — | （账本为空，登记处待补） | — | — |")
    return lines


def build_formula_appendix(formulas: list) -> list:
    """算式明细附录：输入明细（O/M/P 各值、工具路径、JSON 存档位置）集中于此，正文只引结论数字。"""
    lines = [
        "## 算式明细附录（正文仅引结论数字；输入明细与工具存档备查于此）",
        "",
    ]
    for f in formulas:
        content = re.sub(r"^-\s*", "", f["content"])
        lines.append(scrub_internal(f"- {f['id']}：{content}"))
    return lines


# 八态标签在正文中的引用格式：全角/半角括号包裹的单字母标签，如 （V）（T）
_EIGHT_STATE_REF_RE = re.compile(r"[（(][VSCEAPTR][）)]")
# 英文判定词（healthy/marginal/unhealthy）整词出现
_VERDICT_WORD_RE = re.compile(r"(?<![A-Za-z])(?:healthy|marginal|unhealthy)(?![A-Za-z])")

# 领域术语小词典（仅通用工程/商业词，≤10 个；禁止扩成大词典）：
# 正文（白话化前的原始内容）命中才把释义追加为图例「术语表」小节，未命中不输出
GLOSSARY = [
    ("TDS", "技术数据表", r"(?<![A-Za-z0-9])TDS(?![A-Za-z0-9])"),
    ("PERT", "计划评审技术/三点估算法", r"(?<![A-Za-z0-9])PERT(?![A-Za-z0-9])"),
    ("FDM", "熔融沉积成型（3D 打印工艺）", r"(?<![A-Za-z0-9])FDM(?![A-Za-z0-9])"),
    ("harness", "承重背带系统", r"(?<![A-Za-z])harness(?![A-Za-z])"),
    ("PLA/PETG", "常用 3D 打印线材", r"(?<![A-Za-z0-9])(?:PLA|PETG)(?![A-Za-z0-9])"),
    ("BOM", "物料清单", r"(?<![A-Za-z0-9])BOM(?![A-Za-z0-9])"),
    ("PRD", "产品需求文档", r"(?<![A-Za-z0-9])PRD(?![A-Za-z0-9])"),
    ("CPM", "关键路径法", r"(?<![A-Za-z0-9])CPM(?![A-Za-z0-9])"),
    ("MVP", "最小可行产品", r"(?<![A-Za-z0-9])MVP(?![A-Za-z0-9])"),
    ("GA", "正式发布", r"(?<![A-Za-z0-9])GA(?![A-Za-z0-9])"),
]


def legend_block(rendered_raw: str) -> list:
    """文首「标签图例」：面向外部读者解释账本标签体系（盲测扣分点：无图例读不懂标签）。

    按需输出：参数八态/判定词两组释义仅在正文实际使用时出现（检测白话化前
    的原始正文），未使用则省略对应行，避免读者"白学"用不到的标签体系。
    """
    uses_eight_state = bool(_EIGHT_STATE_REF_RE.search(rendered_raw))
    uses_verdict = bool(_VERDICT_WORD_RE.search(rendered_raw))
    lines = [
        "## 标签图例（阅读本稿前必读）",
        "",
        "- **假设四态**：VERIFIED＝本项目内已验证；ESTIMATED＝有外部证据、本项目尚未验证；"
        "ASSUMED＝工程假设（未经证实）；UNVERIFIED＝未验证，不得作为决策依据。",
    ]
    if uses_eight_state:
        lines.append(
            "- **参数八态**（产品参数事实状态标签）：V＝实测；S＝仿真；C＝计算；E＝外部证据；"
            "A＝假设；P＝待供应商确认；T＝待测试（实测前不得采信）；R＝废弃（仅留档备查）。")
    if uses_verdict:
        lines.append("- **判定词**：healthy＝健康；marginal＝及格线边缘；unhealthy＝不健康。")
    id_note = "- **编号说明**：〔H-xx〕假设编号、〔R-xx〕研究结论卡编号、〔C-x〕算式编号"
    if uses_eight_state:
        # R 双义消除：八态体系在用时才需要区分 R-xx 与 R（废弃）
        id_note += "——R-xx 与参数八态中的 R（废弃）无关，属不同体系。"
    else:
        id_note += "。"
    lines.append(id_note)
    # 术语表小节：仅列出正文实际命中的术语，未命中不输出该节
    hits = [(term, desc) for term, desc, pat in GLOSSARY if re.search(pat, rendered_raw)]
    if hits:
        lines.append("- **术语表**：" + "；".join(f"{term}＝{desc}" for term, desc in hits) + "。")
    lines.append("")
    return lines


def informed_go(handoff: dict) -> bool:
    """GO 是否为委托方知情决策：scope.waived_stages 含环节 1，或交接包中
    有「知情（承担/决策）」类声明（排除「不知情」表述）。"""
    scope = handoff.get("scope") or {}
    waived = [str(s) for s in scope.get("waived_stages") or []]
    if "1" in waived:
        return True
    text = json.dumps(handoff, ensure_ascii=False)
    return "知情" in text and "不知情" not in text


# 知情决策注（知情 GO 时置于「决策结论：GO」行正下方，加粗独立行，提升显著度）
INFORMED_GO_NOTE = ("**注：本 GO 为委托方知情决策（用户明确承担跳过机会验证的风险），"
                    "非数据充分性结论。**")


def shortage_warning(chapters_insufficient: list) -> list:
    """数据不足警示块：置顶在执行摘要开头，列出缺口章号，不把警示只埋在缺口章内。

    知情决策注不在此重复——已加粗置于文首「决策结论：GO」行正下方（见主流程）。
    """
    nums = "、".join(t.split(" ")[0] for t in chapters_insufficient)
    lines = [
        f"> ⚠️ **数据不足警示**：本稿尚缺数据（{'、'.join(chapters_insufficient)}），"
        f"暂不足以支撑投资决策（缺口章号：{nums}）。"
        f"请先按各章「待补清单」补齐账本数据，再使用本稿。",
        "",
    ]
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

    chapters = build_chapters(handoff, cards, hypotheses, experiments,
                              formulas, predictions, decisions, baseline)

    # 图例按需输出：检测将实际进入正文的原始内容（白话化前）使用了哪些标签体系
    rendered_raw = "\n".join(
        [line for _title, lines, _has in chapters for line in lines]
        + [" ".join([h["content"], h["value"], h["status"], h["source"]]) for h in hypotheses]
        + [" ".join([c["conclusion"], c["level"], c["source"], c["time"]]) for c in cards]
        + [f["content"] for f in formulas]
    )

    body = [
        f"# {doc_title}：{project_name}",
        "",
        f"> 本初稿由 scripts/assemble_bp.py 从工作区法定账本机械组装；"
        f"素材包之外的数字不得成稿，每个数字挂账本编号；数据不足的章节如实标注。",
        f"> 决策结论：GO｜决策问题：{handoff.get('decision_question', '')}",
    ]
    # 知情决策注：紧跟「决策结论：GO」行正下方，加粗独立行（非知情 GO 不输出）
    if informed_go(handoff):
        body.append(INFORMED_GO_NOTE)
    body.append("")
    # 标签图例置于文首（标题之后、正文之前）
    body += legend_block(rendered_raw)

    chapters_with_content = 0
    chapters_insufficient = [title for title, _lines, has in chapters if not has]
    numbers_cited = 0
    numbers_uncited = 0
    refs_used = set()

    seen_bullets = {}  # 规范文本（去编号标注）→ 首次出现章号，用于逐字重复消除

    for index, (title, lines, has_content) in enumerate(chapters):
        body.append(f"## {title}")
        body.append("")
        # 数据不足警示置顶：执行摘要开头先亮缺口，再进正文
        if index == 0 and chapters_insufficient:
            body += shortage_warning(chapters_insufficient)
        if not has_content:
            body += insufficient_block(index)
        else:
            chapters_with_content += 1
            lines = [scrub_internal(line) for line in lines]
            # 逐字重复消除：同一规范文本（去编号标注/前缀标签后）全文只出现一次；
            # 后续出现处替换为指向首现章的指针（如「（同第一章执行摘要，见第一章）」）
            deduped = []
            for line in lines:
                m = re.match(r"- ([^：:]{1,20})：(.+)", line)
                if m:
                    label = m.group(1)
                    norm = re.sub(r"〔[^〕]*〕", "", m.group(2))
                    norm = re.sub(r"\s+", "", norm).rstrip("。")
                    if len(norm) >= 6:
                        if norm in seen_bullets:
                            first = CHAPTER_TITLES[seen_bullets[norm]]
                            deduped.append(
                                f"- {label}：（同{first.replace(' ', '')}，"
                                f"见{first.split(' ')[0]}）")
                            continue
                        seen_bullets[norm] = index
                deduped.append(line)
            lines = deduped
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
    # 假设数量对账备注：交接包 key_assumptions 数与台账 H-xx 行数不一致时如实记录
    key_assumptions = handoff.get("key_assumptions") or []
    assumption_gap = ""
    if key_assumptions and hypotheses and len(key_assumptions) != len(hypotheses):
        assumption_gap = assumption_count_summary(key_assumptions, hypotheses)

    coverage_lines = [
        "---",
        "",
        "## 覆盖率统计（组装器自动生成）",
        "",
        f"- 章节覆盖：七章中 {chapters_with_content}/7 章有实内容；"
        f"数据不足章节：{'、'.join(chapters_insufficient) if chapters_insufficient else '无'}",
        f"- 数字挂编号：已挂 {numbers_cited} 个；未挂 {numbers_uncited} 个（{COVERAGE_NOTE}）"
        + ("；未挂编号的数字须回填账本编号或删除" if numbers_uncited else "")
        + "（执行摘要中「未挂编号」标注指向假设级缺口，"
          "与本表按带单位数字的口径不同，两者不矛盾）",
        f"- 引用编号：{'、'.join(sorted(refs_used)) if refs_used else '无'}",
    ]
    if assumption_gap:
        coverage_lines.append(
            f"- 假设数量对账：{assumption_gap}（摘要已两数并陈；"
            f"请回填假设台账或修正交接包 key_assumptions 后重新组装）")
    coverage_lines.append("")
    body += coverage_lines

    # 5. 假设与证据总登记处 + 算式明细附录（算式输入明细从单元格迁至文末）
    body += build_registry(hypotheses, cards, formulas)
    body.append("")
    if formulas:
        body += build_formula_appendix(formulas)
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
                    f"{numbers_cited} 个数字已挂编号，{numbers_uncited} 个未挂（仅统计带单位数字）",
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
