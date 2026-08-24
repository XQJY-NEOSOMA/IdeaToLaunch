#!/usr/bin/env python3
"""handoff.json 契约校验器（IdeaToLaunch 技能确定性工具，纯标准库）。

用法：
    python3 scripts/validate_handoff.py <handoff.json>

校验 schemas/handoff_v1.json 的契约：required 字段、recommendation 枚举
（GO/NO_GO/ABSTAIN）、confidence 范围或 null、key_assumptions[*].status 枚举、
additionalProperties: false（拒绝未知顶层字段）等。

无第三方依赖：内建一个 hand-rolled 的 JSON Schema 子集校验器，直接从
schemas/handoff_v1.json 读取 required/enum/const/范围——schema 是单一事实源，
本文件不重复硬编码任何字段清单或枚举值。

输出（stdout，JSON）：{"valid": true/false, "errors": [...]}
退出码：0 校验通过；1 校验不通过；2 参数/文件/schema 读取错误。
"""

import json
import sys
from pathlib import Path

# 技能根目录：本脚本位于 <技能根>/scripts/，schema 在 <技能根>/schemas/
SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = SKILL_ROOT / "schemas" / "handoff_v1.json"

# JSON Schema 类型 → Python 类型（注意 bool 是 int 的子类，须单独排除）
TYPE_MAP = {
    "object": dict,
    "array": list,
    "string": str,
    "null": type(None),
}


def die(message: str) -> None:
    """以中文可操作错误信息输出 JSON 并以退出码 2 终止。"""
    print(json.dumps({"error": message}, ensure_ascii=False), file=sys.stderr)
    sys.exit(2)


def _type_ok(value, type_name: str) -> bool:
    """判断值是否符合 JSON Schema 类型名（number/integer 排除 bool）。"""
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    py_type = TYPE_MAP.get(type_name)
    if py_type is None:
        return True  # 未认识的类型名放行（schema 子集之外不擅自拒绝）
    return isinstance(value, py_type)


def _type_label(type_spec) -> str:
    return "/".join(type_spec) if isinstance(type_spec, list) else str(type_spec)


def validate(instance, schema: dict, path: str, errors: list) -> None:
    """JSON Schema 子集校验：type / required / properties / items /
    enum / const / minimum / maximum / additionalProperties:false。

    所有规则（字段清单、枚举、范围）一律从 schema 对象读取，不硬编码。
    """
    # const
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}：必须等于常量 {schema['const']!r}，收到 {instance!r}")
        return

    # enum
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}：取值必须是 {schema['enum']} 之一，收到 {instance!r}")
        return

    # type
    type_spec = schema.get("type")
    if type_spec is not None:
        allowed = type_spec if isinstance(type_spec, list) else [type_spec]
        if not any(_type_ok(instance, t) for t in allowed):
            errors.append(f"{path}：类型必须是 {_type_label(type_spec)}，收到 {type(instance).__name__}（值 {instance!r}）")
            return

    # 数值范围
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}：必须 ≥ {schema['minimum']}，收到 {instance}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}：必须 ≤ {schema['maximum']}，收到 {instance}")

    # 对象：required / properties / additionalProperties
    if isinstance(instance, dict):
        for req in schema.get("required", []):
            if req not in instance:
                errors.append(f"{path or '(顶层)'}：缺少必填字段 {req!r}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in properties:
                    errors.append(
                        f"{path or '(顶层)'}：未知字段 {key!r} 被拒绝（additionalProperties: false）；"
                        f"允许字段：{sorted(properties)}"
                    )
        for key, value in instance.items():
            sub = properties.get(key)
            if sub:
                validate(value, sub, f"{path}.{key}" if path else key, errors)

    # 数组：逐项校验 items
    if isinstance(instance, list) and "items" in schema:
        for i, item in enumerate(instance):
            validate(item, schema["items"], f"{path}[{i}]", errors)


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 1:
        die("用法：python3 scripts/validate_handoff.py <handoff.json>")

    if not SCHEMA_PATH.is_file():
        die(f"契约 schema 缺失：{SCHEMA_PATH}。请确认技能目录完整。")
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        die(f"契约 schema 不是合法 JSON：{SCHEMA_PATH} 第 {exc.lineno} 行，{exc.msg}。")

    target = Path(argv[0])
    if not target.is_file():
        die(f"待校验文件不存在：{target}")
    try:
        instance = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(
            json.dumps(
                {
                    "valid": False,
                    "errors": [f"{target}：不是合法 JSON（第 {exc.lineno} 行第 {exc.colno} 列，{exc.msg}）"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    errors: list = []
    validate(instance, schema, "", errors)
    print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
