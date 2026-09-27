"""休眠门：`time.Sleep` 出现在产品代码里几乎都是坏味道。

  轮询用 `time.Sleep` 等到某事发生、循环里 sleep 节流、启动顺序靠 sleep 凑——这些都会让
  程序在 CI / 弱机器上flake、在延迟敏感路径上卡顿。正确做法是 `sync.Cond` / channel /
  `context` 取消 / `time.After` + `select`。测试里 sleep 是另一回事（等异步就绪），不判。

  P1 产品代码（非 `_test.go`）里的 `time.Sleep(` 数量 —— 棘轮：只准减（新增即红）。

用法：python3 -X utf8 scripts/gates/sleep_gate.py [--git-tracked] [--list] [--write]
"""
import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gates_common as gc  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
BASELINE = "docs/gates/sleep-baseline.json"
SLEEP = re.compile(r"time\.Sleep\s*\(")


def scan(root: pathlib.Path, git_tracked: bool):
    cur = {}
    for rel in gc.go_files(root, git_tracked):
        if rel.endswith("_test.go"):
            continue
        text = gc.read_text(root, rel)
        if not text:
            continue
        n = len(SLEEP.findall(text))
        if n:
            cur[rel] = n
    return cur


def main() -> int:
    ap = gc.add_args(argparse.ArgumentParser())
    a = ap.parse_args()
    root = ROOT
    bpath = root / BASELINE
    cur = scan(root, a.git_tracked)
    print(f"SLEEP-GATE count={sum(cur.values())}")
    if a.list:
        for r, n in sorted(cur.items(), key=lambda kv: -kv[1])[:a.top]:
            print(f"  {n:3d}  {r}")
        return 0
    if a.write:
        gc.write_baseline(bpath, cur)
        print(f"已写基线 {BASELINE}（{sum(cur.values())} 处 time.Sleep）——此后只准减")
        return 0
    base = gc.load_baseline(bpath)
    if not base:
        print(f"警告：无 {BASELINE} ⇒ 不判；跑 --write 才会管住存量")
    bad, shrank = [], []
    gc.ratchet(cur, base, "sleep", bad, shrank)
    return gc.report("SLEEP-GATE", bad, shrank)


if __name__ == "__main__":
    sys.exit(main())
