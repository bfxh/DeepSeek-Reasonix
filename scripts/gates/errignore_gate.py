"""忽略错误返回门：产品代码里把函数调用的返回值（通常是 error）用 `_` 丢弃。

  Go 里「调用返回 error 的函数却不处理」是头号坏味道：`v, _ := strconv.Atoi(s)` 把解析
  失败吞了，`_ = f()` 把出错可能整个扔了。errcheck 这道著名 linter 管的正是不处理 error。
  本门做语法层的保守版——只盯「赋值里用 `_` 丢弃、且右值是函数调用」的情形，避开
  `for _, v := range` / `if x, err := f()` 这类正当用法（它们以 for/if 开头，直接跳过）。

  X1 产品代码（`_test.go` 不判）里 `_ = call(` / `x, _ = call(` / `_, x := call(` 等 —— 棘轮。
      只判「右值是调用（行内含 `(`）」且「不是 for/if/switch/select 初始化子句」的丢弃。

用法：python3 -X utf8 scripts/gates/errignore_gate.py [--git-tracked] [--list] [--write]
"""
import argparse
import importlib.util
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gates_common as gc  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
BASELINE = "docs/gates/errignore-baseline.json"
# 丢弃整次调用结果：`_ = f()`
BARE = re.compile(r"^\s*_\s*=\s*\S.*\(")
# 丢弃多返回值之一（第二或第一项）：`x, _ = f()` / `_, x := f()`
COMMA = re.compile(r"^\s*\w+\s*,\s*_\s*[:=]\s*\S.*\(|^\s*_\s*,\s*\w+\s*[:=]\s*\S.*\(")
# for/if/switch/select 的初始化子句里 `_` 是正当的（range / 多返回值解构），跳过
INIT = re.compile(r"^\s*(?:else\s+)?(?:for|if|switch|select)\b")


def load_god():
    spec = importlib.util.spec_from_file_location("god_gate_for_errignore",
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
        n = 0
        for line in masked.splitlines():
            if INIT.match(line):
                continue
            if BARE.match(line) or COMMA.match(line):
                n += 1
        if n:
            cur[rel] = n
    return cur


def main() -> int:
    ap = gc.add_args(argparse.ArgumentParser())
    a = ap.parse_args()
    root = ROOT
    bpath = root / BASELINE
    cur = scan(root, a.git_tracked)
    print(f"ERRIGNORE-GATE count={sum(cur.values())}")
    if a.list:
        for r, n in sorted(cur.items(), key=lambda kv: -kv[1])[:a.top]:
            print(f"  {n:3d}  {r}")
        return 0
    if a.write:
        gc.write_baseline(bpath, cur)
        print(f"已写基线 {BASELINE}（{sum(cur.values())} 处忽略错误返回）——此后只准减")
        return 0
    base = gc.load_baseline(bpath)
    if not base:
        print(f"警告：无 {BASELINE} ⇒ 不判；跑 --write 才会管住存量")
    bad, shrank = [], []
    gc.ratchet(cur, base, "errignore", bad, shrank)
    return gc.report("ERRIGNORE-GATE", bad, shrank)


if __name__ == "__main__":
    sys.exit(main())
