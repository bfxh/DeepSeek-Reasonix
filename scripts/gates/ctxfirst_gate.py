"""context 首参门：Go 惯例 `context.Context` 必须是函数的**第一个**参数。

  不守这条，调用方就没法传取消/超时/值，整条调用链断了。编译器不报，但所有
  `ctx` 传播都废了。

  X1 函数签名里出现 `context.Context` 但不是第一个参数 —— 棘轮：只准减（新增即红）。
      只判产品代码（`_test.go` 里 helper 常不守）。

  形态：掩码后按花括号/圆括号配平取出函数签名，分顶层拆参数，找 `context.Context` 的位置。

用法：python3 -X utf8 scripts/gates/ctxfirst_gate.py [--git-tracked] [--list] [--write]
"""
import argparse
import importlib.util
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gates_common as gc  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
BASELINE = "docs/gates/ctxfirst-baseline.json"
FUNC = re.compile(r"^\s*func\b")


def load_god():
    spec = importlib.util.spec_from_file_location("god_gate_for_ctx",
                                                  ROOT / "scripts" / "gates" / "god_gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def split_params(params: str):
    """顶层按逗号拆参数（尊重嵌套括号 / 泛型 < >）。"""
    out, depth, buf = [], 0, ""
    for ch in params:
        if ch in "([]":
            depth += 1
            buf += ch
        elif ch in ")]":
            depth -= 1
            buf += ch
        elif ch == "," and depth == 0:
            out.append(buf)
            buf = ""
        else:
            buf += ch
    if buf.strip():
        out.append(buf)
    return out


def signature_params(gg, lines, i):
    """从 `func` 行 i 起，配平取参数列表文本（含接收者判定）。返回 params 串。"""
    depth, started, end = 0, False, i
    for j in range(i, len(lines)):
        depth += lines[j].count("(") - lines[j].count(")")
        if "(" in lines[j]:
            started = True
        if started and depth <= 0:
            end = j
            break
    sig = "\n".join(lines[i:end + 1])
    # 顶层圆括号组
    groups, d, start = [], 0, None
    for k, ch in enumerate(sig):
        if ch == "(":
            if d == 0:
                start = k
            d += 1
        elif ch == ")":
            d -= 1
            if d == 0:
                groups.append(sig[start + 1:k])
    if not groups:
        return ""
    has_recv = re.match(r"func\s*\(", sig) is not None
    return groups[1] if (has_recv and len(groups) > 1) else groups[0]


def scan(root: pathlib.Path, git_tracked: bool):
    gg = load_god()
    cur = {}
    for rel in gc.go_files(root, git_tracked):
        if rel.endswith("_test.go"):
            continue
        text = gc.read_text(root, rel)
        if not text:
            continue
        lines = gg._mask(text, go=True).splitlines()
        n = 0
        for i, line in enumerate(lines):
            if not FUNC.match(line):
                continue
            params = signature_params(gg, lines, i)
            if not params.strip():
                continue
            parts = split_params(params)
            for idx, p in enumerate(parts):
                t = p.strip().split()[-1] if p.strip() else ""
                if t == "context.Context" and idx != 0:
                    n += 1
                    break
        if n:
            cur[rel] = n
    return cur


def main() -> int:
    ap = gc.add_args(argparse.ArgumentParser())
    a = ap.parse_args()
    root = ROOT
    bpath = root / BASELINE
    cur = scan(root, a.git_tracked)
    print(f"CTXFIRST-GATE count={sum(cur.values())}")
    if a.list:
        for r, n in sorted(cur.items(), key=lambda kv: -kv[1])[:a.top]:
            print(f"  {n:3d}  {r}")
        return 0
    if a.write:
        gc.write_baseline(bpath, cur)
        print(f"已写基线 {BASELINE}（{sum(cur.values())} 处 ctx 非首参）——此后只准减")
        return 0
    base = gc.load_baseline(bpath)
    if not base:
        print(f"警告：无 {BASELINE} ⇒ 不判；跑 --write 才会管住存量")
    bad, shrank = [], []
    gc.ratchet(cur, base, "ctxfirst", bad, shrank)
    return gc.report("CTXFIRST-GATE", bad, shrank)


if __name__ == "__main__":
    sys.exit(main())
