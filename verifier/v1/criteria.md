# 验收标准 v1（2026-08-24 建立）

对 IdeaToLaunch 工作树的机械验收。全部通过 = exit 0。

| # | 检查项 | 通过判据 |
|---|---|---|
| C1 | 自研脚本自测 | `scripts/selftest.py` 全绿（≥45 断言） |
| C2 | 链路体检冒烟 | 新建骨架工作区：环节 0 pass、环节 1 fail、环节 2 fail（骨架占位识别）、退出码 1 |
| C3 | 交接契约 | `schemas/handoff_v1.json` 为合法 JSON；真实使用工作区 handoff.json 通过 validate_handoff |
| C4 | SKILL.md 结构 | front matter 含 name/description；「单一权威表」「文档索引」「功能冻结声明」各恰好一节；文档索引中引用的文件全部存在 |
| C5 | vendor 完整性 | 21 个子目录均存在且各含合法 VENDOR.json（必填键：name/source/vendored_at/module_mapping/applicability_boundary/dependencies） |
| C6 | 仓库卫生 | 工作树无 `__pycache__`、无 `.pyc` |
