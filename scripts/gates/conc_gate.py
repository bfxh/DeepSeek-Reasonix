"""并发门：Go 里那些**编译器不报错、但迟早出事**的并发写法。

  C1 `go func(` 裸协程数量 —— 棘轮：数量本身就是并发面的大小，涨得快说明在到处开协程。
  C2 包级可变全局（`var` 在顶层）—— 棘轮：共享可变状态是数据竞争的温床。
  C3 `time.After(` 出现在 `for` 循环体内 —— 棘轮：每次迭代都新建一个定时器，
     循环不退出就一直攒着（Go 里最常见的定时器泄漏）。
  C4 `go func` 体里调 `wg.Add(` —— 棘轮：Add 必须在启动协程**之前**调，放里面是竞态
     （协程可能先跑完 Wait，主流程才 Add）。存量 6 处全进基线，只拦新增。
  C5 空 `select {}` —— 棘轮：永久阻塞，写出来就是要挂死。

  为什么 C4/C5 是棘轮不是硬规则：存量分别有 6 / 若干处，其中大多是 `_test.go` 里测试
  并发的常见写法。直接硬开会当场卡住所有并行开发；正确做法是录基线、只许减。本仓
  真正"零容忍"的硬规则在 sec（InsecureSkipVerify / 本地 replace）、dep（二进制库化）、
  iface（上帝接口）那几道。

用法：python3 -X utf8 scripts/gates/conc_gate.py [--git-tracked] [--list] [--write]
"""
import argparse
import importlib.util
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gates_common as gc  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
BASELINE = "docs/gates/conc-baseline.json"
GOFUNC = re.compile(r"^\s*go\s+func\s*\(")
FOR_RE = re.compile(r"^\s*(?:for|range)\b|^\s*for\s")
TOPVAR = re.compile(r"^var\s+([A-Za-z_]\w*)\s")
INNER_VAR = re.compile(r"^\s+([A-Za-z_]\w*)\s+\S")
AFTER = re.compile(r"time\.After\s*\(")
ADD = re.compile(r"\.Add\s*\(")
EMPTY_SELECT = re.compile(r"^\s*select\s*\{\s*\}\s*$")


def load_god():
    spec = importlib.util.spec_from_file_location("god_gate_for_conc",
                                                  ROOT / "scripts" / "gates" / "god_gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def block_end(lines, i):
    """从声明行 i 起，花括号配平到闭合行（返回行号）。"""
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
    cur = {"gofunc": {}, "globalvar": {}, "after_in_loop": {}, "wg_add": {}, "empty_select": {}}
    for rel in gc.go_files(root, git_tracked):
        text = gc.read_text(root, rel)
        if not text:
            continue
        lines = gg._mask(text, go=True).splitlines()
        raw = text.splitlines()
        n_func = n_after = 0
        for i, line in enumerate(lines):
            if GOFUNC.match(line):
                n_func += 1
                end = block_end(lines, i)
                body = "\n".join(raw[i:end + 1])
                if ADD.search(body):
                    cur["wg_add"][rel] = cur["wg_add"].get(rel, 0) + 1
            if FOR_RE.match(line) and "{" in line:
                end = block_end(lines, i)
                body = "\n".join(raw[i + 1:end])
                n_after += len(AFTER.findall(body))
        for i, line in enumerate(raw, 1):
            if EMPTY_SELECT.match(line):
                cur["empty_select"][rel] = cur["empty_select"].get(rel, 0) + 1
        if n_func:
            cur["gofunc"][rel] = n_func
        if n_after:
            cur["after_in_loop"][rel] = n_after
        nv = 0
        for i, line in enumerate(raw):
            if TOPVAR.match(line):
                nv += 1
            if line.strip() == "var (":
                for j in range(i + 1, min(i + 200, len(raw))):
                    if raw[j].strip() == ")":
                        break
                    if INNER_VAR.match(raw[j]) and not raw[j].lstrip().startswith("//"):
                        nv += 1
        if nv:
            cur["globalvar"][rel] = nv
    return cur


def main() -> int:
    ap = gc.add_args(argparse.ArgumentParser())
    a = ap.parse_args()
    root = ROOT
    bpath = root / BASELINE
    cur = scan(root, a.git_tracked)
    print("CONC-GATE " + " ".join(f"{k}={sum(v.values())}" for k, v in cur.items()))
    if a.list:
        for k, v in cur.items():
            for r, n in sorted(v.items(), key=lambda kv: -kv[1])[:a.top]:
                print(f"  {k:14s} {n:3d}  {r}")
        return 0
    if a.write:
        gc.write_baseline(bpath, cur)
        print(f"已写基线 {BASELINE}（gofunc/globalvar/after_in_loop/wg_add/empty_select）——此后只准减")
        return 0
    base = gc.load_baseline(bpath)
    if not base:
        print(f"警告：无 {BASELINE} ⇒ 不判；跑 --write 才会管住存量")
    bad, shrank = [], []
    for k in ("gofunc", "globalvar", "after_in_loop", "wg_add", "empty_select"):
        gc.ratchet(cur[k], base.get(k, {}), k, bad, shrank)
    return gc.report("CONC-GATE", bad, shrank)


if __name__ == "__main__":
    sys.exit(main())
