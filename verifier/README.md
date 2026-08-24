# verifier 索引（append-only）

## v1（创建于 2026-08-24）
- 测量对象：IdeaToLaunch 工作树的机械健康基线（自测全绿、链路体检冒烟、交接契约、SKILL.md 结构、vendor 元信息、仓库卫生）。
- 与上一版差异：首版。
- 运行方式：`python3 verifier/v1/verify.py`，全部 PASS 且 exit 0 为通过。

## runs 记录约定
- 每次运行将结果追加到 `verifier/runs/<UTC时间戳>.log`（命令、exit code、各检查项结果），包括未作为迭代节点发布的运行。

## v1 工具修订记录（标准未变，仅工具修补）
- 2026-08-24 修补①：子进程注入 PYTHONDONTWRITEBYTECODE（防验证器自身触发 C6）；
- 2026-08-24 修补②：C6 检查前自清 pycache（selftest 孙进程与编译检查会再生，顺序性误报）。

## v2（创建于 2026-08-24）
- 测量对象：v1 全部 6 项 + 新增 C7（标签体系治理：decision-quality.md 分工与映射节、product-baseline 四态声明）。
- 与上一版差异：新增 C7；v1 各检查项逻辑不变。
- 运行方式：`python3 verifier/v2/verify.py`。
