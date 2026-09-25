"""协程无 recover 门：裸 `go func() { ... }()` 体里没有 `recover()` 兜底。

  Go 里一个 goroutine panic 会拖垮整个进程。凡是「自己开协程跑一段可能出错的逻辑」，
  标准做法是 defer + recover 包一层。编译器不报，但生产环境一个没兜住的 panic 就是线上
  事故。`go foo()` 调的是具名函数，静态看不进来，本门只判**函数字面量** `go func(...) {`。

  X1 产品代码（`_test.go` 不判）里 `go func` 字面量且体内无 `recover()` —— 棘轮：只准减。
      只判语法层能确认的缺 recover；具名函数 `go f()` 不在范围内（静态无法核实）。

用法：python3 -X utf8 scripts/gates/grrecover_gate.py [--git-tracked] [--list] [--write]
"""
import argparse
import importlib.util
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gates_common as gc  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
BASELINE = "docs/gates/grrecover-baseline.json"
GOFUNC = re.compile(r"\bgo\s+func\s*\(")
RECOVER = re.compile(r"recover\s*\(\s*\)")


def load_god():
    spec = importlib.util.spec_from_file_location("god_gate_for_gr",
                                                  ROOT / "scripts" / "gates" / "god_gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def count_unrecovered(masked: str) -> int:
    """统计掩码文本里「go func 字面量且体内无 recover」的个数。"""
    n = 0
    for m in GOFUNC.finditer(masked):
        depth, started, body_start, body = 0, False, None, None
        j = m.end()
        while j < len(masked):
            c = masked[j]
            if c == "{":
                if not started:
                    started, depth, body_start = True, 1, j + 1
                else:
                    depth += 1
            elif c == "}":
                depth -= 1
                if started and depth == 0:
                    body = masked[body_start:j]
                    break
            j += 1
        if body is not None and not RECOVER.search(body):
            n += 1
    return n


def scan(root: pathlib.Path, git_tracked: bool):
    gg = load_god()
    cur = {}
    for rel in gc.go_files(root, git_tracked):
        if rel.endswith("_test.go"):
            continue
        text = gc.read_text(root, rel)
        if not text:
            continue
        n = count_unrecovered(gg._mask(text, go=True))
        if n:
            cur[rel] = n
    return cur


def main() -> int:
    ap = gc.add_args(argparse.ArgumentParser())
    a = ap.parse_args()
    root = ROOT
    bpath = root / BASELINE
    cur = scan(root, a.git_tracked)
    print(f"GRRECOVER-GATE count={sum(cur.values())}")
    if a.list:
        for r, n in sorted(cur.items(), key=lambda kv: -kv[1])[:a.top]:
            print(f"  {n:3d}  {r}")
        return 0
    if a.write:
        gc.write_baseline(bpath, cur)
        print(f"已写基线 {BASELINE}（{sum(cur.values())} 处 goroutine 无 recover）——此后只准减")
        return 0
    base = gc.load_baseline(bpath)
    if not base:
        print(f"警告：无 {BASELINE} ⇒ 不判；跑 --write 才会管住存量")
    bad, shrank = [], []
    gc.ratchet(cur, base, "grrecover", bad, shrank)
    return gc.report("GRRECOVER-GATE", bad, shrank)


if __name__ == "__main__":
    sys.exit(main())
