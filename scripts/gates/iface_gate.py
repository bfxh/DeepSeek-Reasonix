"""接口隔离门：Go 的接口应该小（接口隔离原则）。一个接口塞几十个方法 = 上帝接口，
  调用方被迫依赖一整坨，mock 也难写。

  形态：掩码后按花括号配平取 `type X interface {` 块，数方法签名数。

  I1 方法数 > 12 的接口数量 —— 棘轮：只准减（新增即红）。
  I2 方法数 > 25 的接口 —— **硬**：接口胖到这种程度已经失去"小契约"的意义，
      当前 0 条 ⇒ 出现即红（不进基线祖父化）。

用法：python3 -X utf8 scripts/gates/iface_gate.py [--git-tracked] [--list] [--write]
"""
import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gates_common as gc  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
BASELINE = "docs/gates/iface-baseline.json"
SOFT_CAP = 12
HARD_CAP = 40          # 接口方法数超过这个 = 上帝接口；当前最大 31 ⇒ 硬规则当天可开
IFACE = re.compile(r"^\s*type\s+([A-Za-z_]\w*)\s+interface\s*\{")
METHOD = re.compile(r"^\s*[A-Za-z_]\w*\s*(?:\([^)]*\)\s*)?[A-Za-z_]\w*")  # Foo(...) 或 Foo(bar)


def scan(root: pathlib.Path, git_tracked: bool):
    cur = {"over_soft": {}}
    hard = []
    for rel in gc.go_files(root, git_tracked):
        text = gc.read_text(root, rel)
        if not text:
            continue
        lines = gc.mask_go(text).splitlines() if hasattr(gc, "mask_go") else text.splitlines()
        i = 0
        while i < len(lines):
            m = IFACE.match(lines[i])
            if not m:
                i += 1
                continue
            name = m.group(1)
            depth, started, end = 0, False, i
            for j in range(i, len(lines)):
                depth += lines[j].count("{") - lines[j].count("}")
                if "{" in lines[j]:
                    started = True
                if started and depth <= 0:
                    end = j
                    break
            body = lines[i + 1:end]
            # 方法 = 形如 `Name(...)` 或 `Name(args) ret`；跳过空行与注释
            methods = 0
            for bl in body:
                s = bl.strip()
                if not s or s.startswith("//"):
                    continue
                if METHOD.match(s) and "(" in s:
                    methods += 1
            if methods > HARD_CAP:
                hard.append(f"I2 {rel}: 接口 {name} 有 {methods} 个方法（> {HARD_CAP}，上帝接口，硬禁止）")
            elif methods > SOFT_CAP:
                cur["over_soft"][rel] = cur["over_soft"].get(rel, 0) + 1
            i = end + 1
    return cur, hard


def main() -> int:
    ap = gc.add_args(argparse.ArgumentParser())
    a = ap.parse_args()
    root = ROOT
    bpath = root / BASELINE
    cur, hard = scan(root, a.git_tracked)
    n = sum(cur["over_soft"].values())
    print(f"IFACE-GATE over_soft={n} 硬规则命中={len(hard)}")
    if a.list:
        gg_lines = {}
        for rel in gc.go_files(root, a.git_tracked):
            text = gc.read_text(root, rel)
            if not text:
                continue
            lines = text.splitlines()
            i = 0
            while i < len(lines):
                m = re.match(r"^\s*type\s+([A-Za-z_]\w*)\s+interface\s*\{", lines[i])
                if not m:
                    i += 1
                    continue
                name = m.group(1)
                depth, started, end = 0, False, i
                for j in range(i, len(lines)):
                    depth += lines[j].count("{") - lines[j].count("}")
                    if "{" in lines[j]:
                        started = True
                    if started and depth <= 0:
                        end = j
                        break
                methods = sum(1 for bl in lines[i + 1:end]
                              if bl.strip() and not bl.strip().startswith("//")
                              and re.match(r"^\s*[A-Za-z_]\w*\s*\(.*\)", bl))
                if methods > SOFT_CAP:
                    gg_lines.setdefault(rel, []).append((name, methods))
                i = end + 1
        rows = [(rel, nm, c) for rel, lst in gg_lines.items() for nm, c in lst]
        for rel, nm, c in sorted(rows, key=lambda r: -r[2])[:a.top]:
            print(f"  {c:3d}  {rel}:{nm}")
        for h in hard[:a.top]:
            print(f"  HARD  {h}")
        return 0
    if a.write:
        gc.write_baseline(bpath, cur)
        print(f"已写基线 {BASELINE}——此后只准减（I2 是硬规则，不进基线）")
        return 0
    base = gc.load_baseline(bpath)
    if not base:
        print(f"警告：无 {BASELINE} ⇒ 只对硬规则判；跑 --write 才会管住存量")
    bad, shrank = [], []
    gc.ratchet(cur["over_soft"], base.get("over_soft", {}), "iface", bad, shrank)
    bad.extend(hard)
    return gc.report("IFACE-GATE", bad, shrank)


if __name__ == "__main__":
    sys.exit(main())
