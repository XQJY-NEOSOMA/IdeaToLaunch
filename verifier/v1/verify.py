#!/usr/bin/env python3
"""IdeaToLaunch 工作树验收脚本（verifier/v1）。通过全部检查则 exit 0。"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS: list[dict] = []
# 验证过程中不产生字节码缓存（否则 C6 会被验证器自身触发）
_ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}


def record(cid: str, name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append({"id": cid, "name": name, "ok": ok, "detail": detail})
    print(f"{'PASS' if ok else 'FAIL'}  {cid} {name}" + (f" :: {detail}" if detail and not ok else ""))


def c1_selftest() -> None:
    p = subprocess.run([sys.executable, str(ROOT / "scripts/selftest.py")],
                       capture_output=True, text=True, timeout=600, env=_ENV)
    m = re.search(r"合计：(\d+) 通过，(\d+) 失败", p.stdout)
    ok = p.returncode == 0 and m and int(m.group(1)) >= 45 and m.group(2) == "0"
    record("C1", "自研脚本自测全绿", bool(ok), p.stdout.strip().splitlines()[-1] if m else p.returncode)


def c2_pipeline_smoke() -> None:
    with tempfile.TemporaryDirectory() as td:
        subprocess.run([sys.executable, str(ROOT / "scripts/init_workspace.py"), "冒烟", "--dir", td],
                       capture_output=True, text=True, timeout=60, env=_ENV)
        ws = next(Path(td).iterdir())
        p = subprocess.run([sys.executable, str(ROOT / "scripts/pipeline.py"), str(ws), "--json"],
                           capture_output=True, text=True, timeout=60, env=_ENV)
        try:
            rep = json.loads(p.stdout)
            stages = {s["id"]: s["status"] for s in rep["stages"]}
            ok = (p.returncode == 1 and stages.get("0") == "pass"
                  and stages.get("1") == "fail" and stages.get("2") == "fail")
        except Exception as e:  # noqa: BLE001
            ok = False
            rep = str(e)
        record("C2", "链路体检冒烟（骨架工作区）", ok, str(rep)[:300])


def c3_handoff_contract() -> None:
    ok_schema = False
    try:
        json.loads((ROOT / "schemas/handoff_v1.json").read_text(encoding="utf-8"))
        ok_schema = True
    except Exception:  # noqa: BLE001
        pass
    real = ROOT.parent / "output/real-use/IdeaToLaunch自身演进-20260824/handoff.json"
    ok_real = None
    if real.is_file():
        p = subprocess.run([sys.executable, str(ROOT / "scripts/validate_handoff.py"), str(real)],
                           capture_output=True, text=True, timeout=60, env=_ENV)
        ok_real = p.returncode == 0
    record("C3", "交接契约合法且真实工作区通过校验", ok_schema and ok_real is True,
           f"schema={ok_schema} real={ok_real}")


def c4_skill_structure() -> None:
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    ok_fm = bool(m and re.search(r"^name:\s*\S+", m.group(1), re.M)
                 and re.search(r"^description:\s*.+", m.group(1), re.M))
    ok_sections = all(text.count(f"## {s}") == 1 for s in
                      ["单一权威表", "文档索引", "核心信条", "呈现层契约"]) \
        and "功能冻结声明" in text
    # 文档索引表中的 `path` 引用全部存在
    refs = set(re.findall(r"`((?:references|templates|schemas|scripts|vendor|docs)/[^`]+)`", text))
    missing = [r for r in sorted(refs) if not (ROOT / r).exists()]
    record("C4", "SKILL.md 结构与索引引用完整",
           ok_fm and ok_sections and not missing,
           f"fm={ok_fm} sections={ok_sections} missing_refs={missing[:5]}")


def c5_vendor_integrity() -> None:
    vdir = ROOT / "vendor"
    required = {"name", "source", "vendored_at", "module_mapping",
                "applicability_boundary", "dependencies"}
    bad = []
    dirs = [d for d in vdir.iterdir() if d.is_dir()]
    for d in sorted(dirs):
        vf = d / "VENDOR.json"
        if not vf.is_file():
            bad.append(f"{d.name}: 缺 VENDOR.json")
            continue
        try:
            v = json.loads(vf.read_text(encoding="utf-8"))
            miss = required - set(v)
            if miss:
                bad.append(f"{d.name}: 缺键 {sorted(miss)}")
        except Exception as e:  # noqa: BLE001
            bad.append(f"{d.name}: JSON 非法 {e}")
    record("C5", "vendor 完整性与元信息", len(dirs) == 21 and not bad,
           f"dirs={len(dirs)} bad={bad[:3]}")


def _clean_pycache() -> None:
    """清理 pycache（C1 自测的子进程会再生，C6 前必须自清）。"""
    import shutil
    for p in ROOT.rglob("__pycache__"):
        if ".git" not in p.parts:
            shutil.rmtree(p, ignore_errors=True)
    for p in ROOT.rglob("*.pyc"):
        if ".git" not in p.parts:
            p.unlink(missing_ok=True)


def c6_hygiene() -> None:
    _clean_pycache()
    junk = [p for p in ROOT.rglob("*")
            if ".git" not in p.parts and ("__pycache__" in p.parts or p.suffix == ".pyc")]
    record("C6", "仓库卫生（无 __pycache__/.pyc）", not junk, str(junk[:3]))


def main() -> int:
    c1_selftest()
    c2_pipeline_smoke()
    c3_handoff_contract()
    c4_skill_structure()
    c5_vendor_integrity()
    c6_hygiene()
    failed = [r for r in RESULTS if not r["ok"]]
    summary = {"total": len(RESULTS), "passed": len(RESULTS) - len(failed),
               "failed": len(failed), "failed_ids": [r["id"] for r in failed]}
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
