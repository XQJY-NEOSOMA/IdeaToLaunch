#!/usr/bin/env python3
"""初始化项目工作区（IdeaToLaunch 技能确定性工具）。

用法：
    python3 scripts/init_workspace.py <项目名> [--date YYYYMMDD] [--dir 基目录]

行为：
    创建 ``<基目录>/<项目名>-<日期>/`` 工作区目录，并从技能模板复制生成
    ``decision_journal.md``（决策日志）与 ``research_log.md``（研究日志）。

纪律（账本不可涂改）：
    - 幂等：目标文件已存在则跳过并提示，绝不覆盖已有账本；
    - 工作区目录已存在也安全（复用，不报错）。

输出（stdout，JSON）：
    {"workspace": 路径, "created": [...], "skipped": [...]}

退出码：0 成功；2 参数或环境错误（模板缺失等）。
"""

import argparse
import json
import re
import shutil
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
    for template_name, ledger_name in LEDGERS:
        src = TEMPLATE_DIR / template_name
        dst = workspace / ledger_name
        if not src.is_file():
            die(f"模板缺失：{src}。请确认技能目录完整（templates/{template_name} 必须存在）。")
        if dst.exists():
            # 账本纪律：已存在的账本绝不覆盖
            skipped.append(str(dst))
        else:
            shutil.copyfile(src, dst)
            created.append(str(dst))

    print(
        json.dumps(
            {"workspace": str(workspace), "created": created, "skipped": skipped},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
