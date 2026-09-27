"""圈复杂度门：Go 函数里的分支点越多，越难读、越难测、越容易藏 bug。

  编译器不报，但 50 行的 `if/for/switch` 嵌套函数是人类读不懂的。纯文本统计分支点
  （if / for / range / switch / select / case / && / || / ?:）得到圈复杂度，按函数量。

  C1 复杂度 > 15 的函数数量 —— 棘轮：只准减（新增即红）。
  C2 复杂度 > 50 的函数数量 —— 棘轮：只准减。单函数复杂到这种程度已没法单测覆盖
      （`desktop/tabs.go:buildTabControllerWithContextCore` 高达 91），存量 32 个
      全进基线，此后只许拆、不许新增。想升硬阈先把这 32 个拆到 50 以下。

  形态：复刻 god_gate 的 Go 分支函数提取（掩码后按花括号配平取函数体），不重复造轮子。
  只判产品代码：测试 setup 函数复杂度高是常态，不算产品风险。

用法：python3 -X utf8 scripts/gates/cyc_gate.py [--git-tracked] [--list] [--write]
"""
import argparse
import importlib.util
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gates_common as gc  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
BASELINE = "docs/gates/cyc-baseline.json"
SOFT_CAP = 15          # 超过这个就算"复杂"，计数走棘轮
HARD_CAP = 50          # 超过这个算"不可测"，硬禁止
DECISION = re.compile(r"\b(if|for|range|switch|select|case|default)\b|\&\&|\|\||\?")


def load_god():
    spec = importlib.util.spec_from_file_location("god_gate_for_cyc",
                                                  ROOT / "scripts" / "gates" / "god_gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def funcs_of(gg, text):
    """返回 [(name, complexity)]：每个顶层 func 的圈复杂度。"""
    masked = gg._mask(text, go=True).splitlines()
    raw = text.splitlines()
    out = []
    for i, line in enumerate(masked):
        m = re.match(r"^\s*func\s+(?:\([^)]*\)\s+)?([A-Za-z_]\w*)\b", line)
        if not m:
            continue
        depth, started, end = 0, False, i
        for j in range(i, len(masked)):
            depth += masked[j].count("{") - masked[j].count("}")
            if "{" in masked[j]:
                started = True
            if started and depth <= 0:
                end = j
                break
        body = "\n".join(raw[i:end + 1])
        # 分支点计数在**原始**文本上做（字符串里的 if/for 极少，且掩码会吃掉需要的括号）
        comp = 1 + len(DECISION.findall(body))
        out.append((m.group(1), comp))
    return out


def scan(root: pathlib.Path, git_tracked: bool):
    gg = load_god()
    cur = {"over_soft": {}, "over_hard": {}}   # 复杂函数数（双档棘轮）
    for rel in gc.go_files(root, git_tracked):
        if rel.endswith("_test.go"):      # 测试 setup 函数复杂度高是常态，不判产品风险
            continue
        text = gc.read_text(root, rel)
        if not text:
            continue
        for name, comp in funcs_of(gg, text):
            if comp > HARD_CAP:
                cur["over_hard"][rel] = cur["over_hard"].get(rel, 0) + 1
            elif comp > SOFT_CAP:
                cur["over_soft"][rel] = cur["over_soft"].get(rel, 0) + 1
    return cur


def main() -> int:
    ap = gc.add_args(argparse.ArgumentParser())
    a = ap.parse_args()
    root = ROOT
    bpath = root / BASELINE
    cur = scan(root, a.git_tracked)
    n = sum(cur["over_soft"].values())
    h = sum(cur["over_hard"].values())
    print(f"CYC-GATE over_soft={n} over_hard={h}")
    if a.list:
        # 列出最复杂的函数
        gg = load_god()
        rows = []
        for rel in gc.go_files(root, a.git_tracked):
            if rel.endswith("_test.go"):
                continue
            text = gc.read_text(root, rel)
            if text:
                rows += [(rel, nm, c) for nm, c in funcs_of(gg, text) if c > SOFT_CAP]
        for rel, nm, c in sorted(rows, key=lambda r: -r[2])[:a.top]:
            print(f"  {c:3d}  {rel}:{nm}")
        return 0
    if a.write:
        gc.write_baseline(bpath, cur)
        print(f"已写基线 {BASELINE}（over_soft={n} over_hard={h}）——此后只准减")
        return 0
    base = gc.load_baseline(bpath)
    if not base:
        print(f"警告：无 {BASELINE} ⇒ 不判；跑 --write 才会管住存量")
    bad, shrank = [], []
    gc.ratchet(cur["over_soft"], base.get("over_soft", {}), "cyc", bad, shrank)
    gc.ratchet(cur["over_hard"], base.get("over_hard", {}), "cyc50", bad, shrank)
    return gc.report("CYC-GATE", bad, shrank)


if __name__ == "__main__":
    sys.exit(main())
