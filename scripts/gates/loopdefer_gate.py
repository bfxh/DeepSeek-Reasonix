"""循环 defer 门：Go 里 `defer` 在 `for`/`range` 循环体里是经典反模式。

  `defer` 直到**函数**返回才执行，不是循环迭代结束。循环里 `defer` 关文件/解锁，
  会一直攒到函数返回——循环跑一万次就攒一万个，文件描述符 / 锁一直占着，轻则泄漏、
  重则把系统资源吃光。正确写法是把循环体抽成闭包、或在循环里显式 `Close()`。

  L1 循环体直接子层（花括号深度 = 循环体 +1）里的 `defer` 数量 —— 棘轮：只准减。

  形态：掩码后按花括号配平取循环块，数"直接子层"的 defer。嵌套函数字面量里的 defer
  不计数（那个 defer 跟闭包走，没问题）。

用法：python3 -X utf8 scripts/gates/loopdefer_gate.py [--git-tracked] [--list] [--write]
"""
import argparse
import importlib.util
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gates_common as gc  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
BASELINE = "docs/gates/loopdefer-baseline.json"
DEFER = re.compile(r"^\s*defer\b")


def load_god():
    spec = importlib.util.spec_from_file_location("god_gate_for_loop",
                                                  ROOT / "scripts" / "gates" / "god_gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def scan(root: pathlib.Path, git_tracked: bool):
    gg = load_god()
    cur = {}
    for rel in gc.go_files(root, git_tracked):
        if rel.endswith("_test.go"):      # 测试里的 defer-in-loop 危害小，不判产品风险
            continue
        text = gc.read_text(root, rel)
        if not text:
            continue
        lines = gg._mask(text, go=True).splitlines()
        n = 0
        i = 0
        while i < len(lines):
            # 找循环头：本行 `for`/`range` 带 `{`，或本行无 `{` 但下一行是 `{`
            if not re.match(r"^\s*(?:for|range)\b", lines[i]):
                i += 1
                continue
            if "{" not in lines[i]:
                if i + 1 < len(lines) and lines[i + 1].lstrip().startswith("{"):
                    # `{` 在下一行：循环体从下一行起算；那行的 `{` 已开一层深度
                    body_start = i + 1
                    d = 1
                else:
                    i += 1
                    continue
            else:
                body_start = i
                d = lines[i].count("{") - lines[i].count("}")
            # 配平到循环体闭合；块内第一层（d==1）的 defer 即直接子层
            end = body_start
            depth = d
            for j in range(body_start + 1, len(lines)):
                depth += lines[j].count("{") - lines[j].count("}")
                if DEFER.match(lines[j]) and depth == 1:
                    n += 1
                if depth <= 0:
                    end = j
                    break
            i = end + 1
        if n:
            cur[rel] = n
    return cur


def main() -> int:
    ap = gc.add_args(argparse.ArgumentParser())
    a = ap.parse_args()
    root = ROOT
    bpath = root / BASELINE
    cur = scan(root, a.git_tracked)
    print(f"LOOPDEFER-GATE count={sum(cur.values())}")
    if a.list:
        for r, n in sorted(cur.items(), key=lambda kv: -kv[1])[:a.top]:
            print(f"  {n:3d}  {r}")
        return 0
    if a.write:
        gc.write_baseline(bpath, cur)
        print(f"已写基线 {BASELINE}（{sum(cur.values())} 处循环 defer）——此后只准减")
        return 0
    base = gc.load_baseline(bpath)
    if not base:
        print(f"警告：无 {BASELINE} ⇒ 不判；跑 --write 才会管住存量")
    bad, shrank = [], []
    gc.ratchet(cur, base, "loopdefer", bad, shrank)
    return gc.report("LOOPDEFER-GATE", bad, shrank)


if __name__ == "__main__":
    sys.exit(main())
