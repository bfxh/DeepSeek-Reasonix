"""分层依赖门：依赖方向错了，模块就没法独立演进、没法单测。

  Go 编译器只禁止**环**依赖，但允许一堆合法的烂方向。这里钉两条：

  D1 **二进制不可被库化** —— `internal/**` 里任何文件 import `desktop` 或 `cmd/*`
      （它们都是可执行入口，被别的包当库 import 是架构倒挂）。**硬**：当前 0 条，
      出现即红，不进基线。
  D2 **内部依赖扇出棘轮** —— 一个 `internal/**` 包 import 了多少个*别的* `internal/**`
      包。单包突然 import 十几个 internal 包 = 上帝依赖，新增大涨即红（只准减）。

  形态：纯文本解析 `import (` 块与单行 import，挑出模块内路径。

用法：python3 -X utf8 scripts/gates/dep_gate.py [--git-tracked] [--list] [--write]
"""
import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gates_common as gc  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
BASELINE = "docs/gates/dep-baseline.json"
MODULE = "reasonix/"          # 本仓 go.mod 的 module 名（不是 github URL）


def imports_of(text: str):
    """返回该文件 import 的模块内路径列表（引号内即路径，忽略 alias / 行注释）。"""
    out = []
    in_block = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("//"):
            continue
        if s.startswith("import ("):
            in_block = True
            continue
        if in_block:
            if s == ")":
                in_block = False
                continue
            # 块内可能是多行 import ("a" "b")，逐行取引号串最稳
            out += re.findall(r'"([^"]+)"', s)
            continue
        if s.startswith("import "):
            out += re.findall(r'"([^"]+)"', s[len("import "):])
    return out


def scan(root: pathlib.Path, git_tracked: bool):
    cur = {"fanout": {}}         # 每文件的 internal 扇出数（棘轮）
    hard = []
    for rel in gc.go_files(root, git_tracked):
        if rel.endswith("_test.go"):
            continue
        text = gc.read_text(root, rel)
        if not text:
            continue
        paths = imports_of(text)
        internal = [p for p in paths if p.startswith(MODULE + "internal/")]
        # D1：二进制被库化
        for p in paths:
            if p == MODULE + "desktop" or p.startswith(MODULE + "cmd/"):
                if rel.startswith("internal/"):
                    hard.append(f"D1 {rel}: import {p} —— 二进制不可被 internal 包当库 import（架构倒挂）")
        if internal:
            cur["fanout"][rel] = len(set(internal))
    return cur, hard


def main() -> int:
    ap = gc.add_args(argparse.ArgumentParser())
    a = ap.parse_args()
    root = ROOT
    bpath = root / BASELINE
    cur, hard = scan(root, a.git_tracked)
    n = sum(cur["fanout"].values())
    print(f"DEP-GATE fanout_edges={n} 硬规则命中={len(hard)}")
    if a.list:
        for r, v in sorted(cur["fanout"].items(), key=lambda kv: -kv[1])[:a.top]:
            print(f"  {v:3d}  {r}")
        for h in hard[:a.top]:
            print(f"  HARD  {h}")
        return 0
    if a.write:
        gc.write_baseline(bpath, cur)
        print(f"已写基线 {BASELINE}——此后只准减（D1 是硬规则，不进基线）")
        return 0
    base = gc.load_baseline(bpath)
    if not base:
        print(f"警告：无 {BASELINE} ⇒ 只对硬规则判；跑 --write 才会管住存量")
    bad, shrank = [], []
    gc.ratchet(cur["fanout"], base.get("fanout", {}), "dep", bad, shrank)
    bad.extend(hard)
    return gc.report("DEP-GATE", bad, shrank)


if __name__ == "__main__":
    sys.exit(main())
