"""context.TODO 门：产品代码里 `context.TODO()` 表示「还没想好 ctx 从哪来」。

  `context.Background()` 在 main / server 顶层是正当的「根 ctx」；`context.TODO()` 则是
  「我欠着」——一旦落地，调用链里就出现拿不到取消/超时的 ctx，整条链路的控制力掉了还
  不好查。编译器不报，但这是明确的「半成品」标记。

  X1 产品代码（`_test.go` 不判）出现 `context.TODO()` —— 棘轮：只准减（新增即红）。

用法：python3 -X utf8 scripts/gates/ctxtodo_gate.py [--git-tracked] [--list] [--write]
"""
import argparse
import importlib.util
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gates_common as gc  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
BASELINE = "docs/gates/ctxtodo-baseline.json"
TODO = re.compile(r"context\.TODO\s*\(\s*\)")


def load_god():
    spec = importlib.util.spec_from_file_location("god_gate_for_ctxtodo",
                                                  ROOT / "scripts" / "gates" / "god_gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def scan(root: pathlib.Path, git_tracked: bool):
    gg = load_god()
    cur = {}
    for rel in gc.go_files(root, git_tracked):
        if rel.endswith("_test.go"):
            continue
        text = gc.read_text(root, rel)
        if not text:
            continue
        masked = gg._mask(text, go=True)
        n = len(TODO.findall(masked))
        if n:
            cur[rel] = n
    return cur


def main() -> int:
    ap = gc.add_args(argparse.ArgumentParser())
    a = ap.parse_args()
    cur = scan(ROOT, a.git_tracked)
    print(f"CTXTODO-GATE count={sum(cur.values())}")
    if a.list:
        for r, n in sorted(cur.items(), key=lambda kv: -kv[1])[:a.top]:
            print(f"  {n:3d}  {r}")
        return 0
    # 硬规则：当前产品代码 0 处，出现任何 `context.TODO()` 即红（不进基线、不许 grandfather）。
    # TODO 是「ctx 从哪来还没想好」的半成品标记，产品代码里只允许 `context.Background()` 作根。
    bad = [f"{rel}: {n} 处 context.TODO（硬规则：产品代码禁止 TODO，改用 Background 或传 ctx）"
           for rel, n in sorted(cur.items(), key=lambda kv: -kv[1])]
    return gc.report("CTXTODO-GATE", bad, [])


if __name__ == "__main__":
    sys.exit(main())
