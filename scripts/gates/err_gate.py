"""错误处理门：Go 里"出错但当没出错"是最隐蔽的 bug 来源。

  E1 **吞错**：`if err != nil {` 的块体里直接 `return nil` / `return nil, nil`
      —— 错误已经发生，调用方却看到成功。棘轮：只准减（新增即红）。
      这是唯一会被判的吞错形态；`return err` / `return fmt.Errorf(...)` 是正确写法，不判。

  形态：掩码后按花括号配平取 `if err != nil` 块，看块内有没有 `return nil`。

  为什么不做"忽略 error 的 `_ =`"：那是正当写法（`_ = w.Write(...)`），误报太多，反而让门变噪音。
  只抓"明确假装成功"这一种。

用法：python3 -X utf8 scripts/gates/err_gate.py [--git-tracked] [--list] [--write]
"""
import argparse
import importlib.util
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gates_common as gc  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
BASELINE = "docs/gates/err-baseline.json"
ERRCK = re.compile(r"^\s*if\s+err\s*!=\s*nil\s*\{")
RET_NIL = re.compile(r"return\s+nil\s*(,\s*nil)?\s*$")


def load_god():
    spec = importlib.util.spec_from_file_location("god_gate_for_err",
                                                  ROOT / "scripts" / "gates" / "god_gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def block_end(lines, i):
    depth, started, end = 0, False, i
    for j in range(i, len(lines)):
        depth += lines[j].count("{") - lines[j].count("}")
        if "{" in lines[j]:
            started = True
        if started and depth <= 0:
            return j
    return end


def scan(root: pathlib.Path, git_tracked: bool):
    gg = load_god()
    cur = {}
    for rel in gc.go_files(root, git_tracked):
        if rel.endswith("_test.go"):      # 测试里 return nil 在 fake 里常见，不判产品风险
            continue
        text = gc.read_text(root, rel)
        if not text:
            continue
        lines = gg._mask(text, go=True).splitlines()
        n = 0
        for i, line in enumerate(lines):
            if ERRCK.match(line):
                end = block_end(lines, i)
                if any(RET_NIL.match(b.strip()) for b in lines[i + 1:end]):
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
    print(f"ERR-GATE swallowed={len(cur)}")
    if a.list:
        for r, n in sorted(cur.items(), key=lambda kv: -kv[1])[:a.top]:
            print(f"  {n:3d}  {r}")
        return 0
    if a.write:
        gc.write_baseline(bpath, cur)
        print(f"已写基线 {BASELINE}（{len(cur)} 处吞错）——此后只准减")
        return 0
    base = gc.load_baseline(bpath)
    if not base:
        print(f"警告：无 {BASELINE} ⇒ 不判；跑 --write 才会管住存量")
    bad, shrank = [], []
    gc.ratchet(cur, base, "err", bad, shrank)
    return gc.report("ERR-GATE", bad, shrank)


if __name__ == "__main__":
    sys.exit(main())
