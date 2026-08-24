#!/usr/bin/env python3
"""初始化项目工作区（IdeaToLaunch 技能确定性工具）。

用法：
    python3 scripts/init_workspace.py <项目名> [--date YYYYMMDD] [--dir 基目录] [--with-contract]

行为：
    创建 ``<基目录>/<项目名>-<日期>/`` 工作区目录，并从技能模板复制生成
    ``decision_journal.md``（决策日志）与 ``research_log.md``（研究日志）；
    复制时去除模板首行标题的「（模板）」标记（其余内容字节不变）。
    同时按 schemas/handoff_v1.json 生成 ``handoff.json`` 契约骨架
    （recommendation 预填 ABSTAIN，decision_question 预填「（待填写：本次决策问题）」
    作为未填写标记），生成后自调用 validate_handoff 逻辑自检。
    ``--with-contract`` 时另从 templates/judgment-contract.md 复制生成
    ``judgment_contract.md``（幂等规则同账本）。

纪律（账本不可涂改）：
    - 幂等：目标文件已存在则跳过并提示，绝不覆盖已有账本；
    - 工作区目录已存在也安全（复用，不报错）。

输出（stdout，JSON）：
    {"workspace": 路径, "created": [...], "skipped": [...], "handoff_selfcheck": ...}

退出码：0 成功；2 参数或环境错误（模板缺失等）。
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

# 技能根目录：本脚本位于 <技能根>/scripts/，模板在 <技能根>/templates/
SKILL_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = SKILL_ROOT / "templates"

# (模板文件, 工作区内账本文件名) —— 文件名固定，见 SKILL.md「项目工作区约定」
LEDGERS = [
    ("decision-journal.md", "decision_journal.md"),
    ("research-log.md", "research_log.md"),
]
# --with-contract 时追加复制的判断合同模板
CONTRACT_LEDGER = ("judgment-contract.md", "judgment_contract.md")

# handoff.json 骨架占位标记：recommendation 预填合法枚举 ABSTAIN，
# decision_question 预填待填写标记（additionalProperties:false，不能加注释字段）
SKELETON_QUESTION = "（待填写：本次决策问题）"


def handoff_skeleton(project: str) -> dict:
    """按 schemas/handoff_v1.json 的 required 字段生成 handoff.json 骨架。"""
    return {
        "contract_version": "1.0",
        "project": {"name": project},
        "decision_question": SKELETON_QUESTION,
        "recommendation": "ABSTAIN",
        "confidence": None,
        "key_assumptions": [],
        "critical_uncertainties": [],
    }


def selfcheck_handoff(skeleton: dict) -> None:
    """骨架自检：复用 validate_handoff.py 的校验逻辑（schema 为单一事实源）。"""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import validate_handoff

    if not validate_handoff.SCHEMA_PATH.is_file():
        die(f"契约 schema 缺失：{validate_handoff.SCHEMA_PATH}。请确认技能目录完整。")
    schema = json.loads(validate_handoff.SCHEMA_PATH.read_text(encoding="utf-8"))
    errors: list = []
    validate_handoff.validate(skeleton, schema, "", errors)
    if errors:
        die(f"handoff.json 骨架自检未通过（须与 validate_handoff.py 行为一致）：{errors}")


def copy_template(src: Path, dst: Path) -> None:
    """复制模板：首行标题去除「（模板）」标记，其余内容字节不变。"""
    text = src.read_text(encoding="utf-8")
    first, sep, rest = text.partition("\n")
    dst.write_text(first.replace("（模板）", "") + sep + rest, encoding="utf-8")


def die(message: str) -> None:
    """以中文可操作错误信息输出 JSON 并以退出码 2 终止。"""
    print(json.dumps({"error": message}, ensure_ascii=False), file=sys.stderr)
    sys.exit(2)


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="初始化 IdeaToLaunch 项目工作区（幂等，绝不覆盖已有账本）。"
    )
    parser.add_argument("project", help="项目名（工作区目录命名为 项目名-YYYYMMDD/）")
    parser.add_argument(
        "--date",
        default=None,
        help="日期戳，格式 YYYYMMDD；缺省为今天",
    )
    parser.add_argument(
        "--dir",
        default=".",
        help="基目录（工作区创建于其下）；缺省为当前目录",
    )
    parser.add_argument(
        "--with-contract",
        action="store_true",
        help="同时从 templates/judgment-contract.md 复制生成 judgment_contract.md（幂等规则同账本）",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    project = args.project.strip()
    if not project:
        die("项目名不能为空。用法：python3 scripts/init_workspace.py <项目名> [--date YYYYMMDD] [--dir 基目录]")
    if any(sep in project for sep in ("/", "\\")):
        die(f"项目名 {project!r} 含路径分隔符，请只给项目名本身，基目录用 --dir 指定。")

    day = args.date or date.today().strftime("%Y%m%d")
    if not re.fullmatch(r"\d{8}", day):
        die(f"--date 格式错误：{day!r}。需要 8 位数字 YYYYMMDD，例如 20250131。")

    base = Path(args.dir).expanduser().resolve()
    workspace = base / f"{project}-{day}"
    workspace.mkdir(parents=True, exist_ok=True)

    created, skipped = [], []
    ledgers = list(LEDGERS)
    if args.with_contract:
        ledgers.append(CONTRACT_LEDGER)
    for template_name, ledger_name in ledgers:
        src = TEMPLATE_DIR / template_name
        dst = workspace / ledger_name
        if not src.is_file():
            die(f"模板缺失：{src}。请确认技能目录完整（templates/{template_name} 必须存在）。")
        if dst.exists():
            # 账本纪律：已存在的账本绝不覆盖
            skipped.append(str(dst))
        else:
            copy_template(src, dst)
            created.append(str(dst))

    # handoff.json 契约骨架（幂等规则同账本），生成后自调用 validate 逻辑自检
    handoff_path = workspace / "handoff.json"
    handoff_selfcheck = "skipped（已存在，未触碰）"
    if handoff_path.exists():
        skipped.append(str(handoff_path))
    else:
        skeleton = handoff_skeleton(project)
        selfcheck_handoff(skeleton)
        handoff_path.write_text(
            json.dumps(skeleton, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        created.append(str(handoff_path))
        handoff_selfcheck = "valid（通过 validate_handoff 逻辑自检）"

    print(
        json.dumps(
            {
                "workspace": str(workspace),
                "created": created,
                "skipped": skipped,
                "handoff_selfcheck": handoff_selfcheck,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
