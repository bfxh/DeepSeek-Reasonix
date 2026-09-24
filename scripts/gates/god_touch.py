"""上帝对象「碰了就得减」税（god_touch）——比棘轮更严厉的那一步。

**为什么棘轮不够**：棘轮只说「不许变胖」，于是存量可以永远躺着：一个 11631 行的
`desktop/app.go`，只要没人给它加行，它就永远是 11631 行，而每个人都在绕着它走。
本门把规则改成：**你改了它，就必须把它变小**（`touch_tax_min_reduction`，默认至少减 1 行）。

判据（只对「相对基线 ref 有改动」且**已超阈**的文件生效）：
  · 该文件的**最差指标**（按超阈幅度最大的那一项算）必须比基线**严格下降**至少 N；
  · 或者该文件的所有指标都降到阈值以内（清零当然放行）；
  · 没超阈的文件不受这条管（只受 god_gate 的棘轮管：涨了就红）；
  · 新增文件不受这条管（直接对阈值判，由 god_gate 管）。

用法（CI 传 PR 的 base sha；本地不传就退回 `git diff HEAD`）：
  python3 -X utf8 scripts/gates/god_touch.py --base <ref>
  python3 -X utf8 scripts/gates/god_touch.py --base origin/main-v2 --min-reduction 5
退出码：0 = 通过；1 = 有文件被碰了却没变小；2 = 配置/基线错。
"""
import argparse
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
CFG = "scripts/gates/god.gate.json"
KEYS = ("file_lines", "max_fn_lines", "max_type_members")


def load_cfg() -> dict:
    return json.loads((ROOT / CFG).read_text(encoding="utf-8"))


def git(*args):
    return subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", shell=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=None,
                    help="比较基线（CI 传 github.event.pull_request.base.sha）；缺省用工作树 diff")
    ap.add_argument("--min-reduction", type=int, default=None,
                    help="覆盖配置里的 touch_tax_min_reduction")
    a = ap.parse_args()
    cfg = load_cfg()
    if not cfg.get("touch_tax_enabled", True):
        print("GOD-TOUCH SKIP touch_tax_enabled=false（配置关掉了）")
        return 0
    need = a.min_reduction if a.min_reduction is not None else cfg.get("touch_tax_min_reduction", 1)
    bpath = ROOT / cfg["baseline"]
    if not bpath.is_file():
        print(f"GOD-TOUCH FAIL 没有基线 {cfg['baseline']}——先跑 gate.py --write")
        return 2
    base = json.loads(bpath.read_text(encoding="utf-8"))
    lim = {"file_lines": cfg["max_file_lines"], "max_fn_lines": cfg["max_fn_lines"],
           "max_type_members": cfg["max_type_members"]}

    if a.base:
        out = git("diff", "--name-only", a.base).stdout
    else:
        out = git("diff", "--name-only", "HEAD").stdout
    changed = {p.strip() for p in out.splitlines() if p.strip()}

    bad, ok = [], 0
    for rel in sorted(changed & set(base)):
        b = base[rel]
        over = {k: b.get(k, 0) - lim[k] for k in KEYS if b.get(k, 0) > lim[k]}
        if not over:
            continue                       # 没超阈：交给 god_gate 的棘轮
        worst = max(over, key=lambda k: over[k])
        # 当前值：重扫一遍拿不到（要 god_gate 的扫描器），这里用 git 工作树的真实行数做对比
        cur = {}
        p = ROOT / rel
        if p.is_file():
            cur["file_lines"] = p.read_text(encoding="utf-8", errors="replace").count("\n") + 1
        # fn / type 需要扫描器：交给 god_gate 的 scan（单文件）
        cur.update(scan_metrics(p))
        now = cur.get(worst)
        if now is None:
            continue
        drop = b.get(worst, 0) - now
        if drop >= need:
            ok += 1
            print(f"  ✓ {rel}: {worst} {b.get(worst)} → {now}（减 {drop}，≥{need}）")
        else:
            bad.append(f"{rel}: 超阈 {worst}（{b.get(worst)} > {lim[worst]}），"
                       f"改了却只减 {drop}（要求 ≥{need}）——碰了就得减，"
                       f"拆掉一块再提交，或者别动这个文件")
    for line in bad[:25]:
        print(f"  ✗ {line}")
    if len(bad) > 25:
        print(f"  …另有 {len(bad) - 25} 条")
    print(f"GOD-TOUCH {'FAIL' if bad else 'OK'} 改动={len(changed)} 欠账文件已减={ok} "
          f"未减={len(bad)}（要求每次碰超阈文件至少减 {need}）")
    return 1 if bad else 0


def scan_metrics(p: pathlib.Path) -> dict:
    """单文件的 fn / type 指标（复用 god_gate 的扫描器，保证与基线同口径）。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("god_gate_for_touch",
                                                  ROOT / "scripts" / "gates" / "god_gate.py")
    gg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gg)
    try:
        src = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    go = p.suffix == ".go"
    m = (gg.brace_metrics(src, js=not go, go=go) if p.suffix != ".py" else gg.py_metrics(src))
    fns = [n for _, n, k in m if k == "fn"]
    tys = [n for _, n, k in m if k == "type"]
    return {"max_fn_lines": max(fns, default=0), "max_type_members": max(tys, default=0)}


if __name__ == "__main__":
    sys.exit(main())
