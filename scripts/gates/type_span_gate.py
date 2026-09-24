"""类型跨度门（Go 版）：抓**跨文件的上帝类型**——`god_gate` 抓不到的那一半。

为什么还要单独一道：Go 里一个大类型的方法按文件拆开之后，每个文件都只有几百行，
`god_gate` 的三项指标可以从容全绿——但那个**类型本身**可能有 100 个方法、`Controller`
结构体 134 个字段。按文件量规模永远抓不到它，必须按**接收者**把方法聚合起来看。

判据（每个 Go 包 = 一个目录，按接收者类型名聚合）：
  · `methods` —— 该类型的方法总数（`func (r *Foo) Bar()` 全算它的）；
  · `files`   —— 这些方法散在几个文件里（职责发散度）；
  两项各有阈值 + 只准减的棘轮基线 + 可单独开硬阈。

用法：
  python3 -X utf8 scripts/gates/type_span_gate.py --list            # 看看谁最发散
  python3 -X utf8 scripts/gates/type_span_gate.py --write-baseline   # 记基线
  python3 -X utf8 scripts/gates/type_span_gate.py --git-tracked      # 门
退出码：0 = 通过；1 = 超标/变胖；2 = 配置错。
"""
import argparse
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
CFG_REL = "scripts/gates/god.gate.json"
DEFAULT = {
    "max_type_methods_total": 40,
    "max_type_impl_files": 8,
    "min_methods_to_track": 10,
    "type_span_hard_threshold": False,
    "include": ["**/*.go"],
    "exclude": ["**/.git/**", "**/node_modules/**", "**/vendor/**", "**/*/generated/**",
                "**/generated/**", "**/*.generated.*"],
    # 键名必须独立：`god.gate.json` 里有另一份 `baseline`（上帝对象基线），
    # 共用会把类型基线写进 god-baseline.json 整份覆盖（另一个仓已踩过）。
    "type_span_baseline": "docs/gates/type-span-baseline.json",
}
# 接收者：`func (r *Foo) Bar(` / `func (r Foo) Bar(` / 泛型 `func (r *Foo[T]) Bar(`
RECV_RE = re.compile(r"^func\s+\(\s*[A-Za-z_][A-Za-z0-9_]*\s+\*?([A-Za-z_][A-Za-z0-9_]*)"
                     r"(?:\[[^\]]*\])?\)\s+([A-Za-z_][A-Za-z0-9_]*)")


def load_gate():
    spec = importlib.util.spec_from_file_location("god_gate_for_span", ROOT / "scripts" / "gates" / "god_gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_cfg(root: pathlib.Path) -> dict:
    cfg = dict(DEFAULT)
    p = root / CFG_REL
    if p.is_file():
        cfg.update({k: v for k, v in json.loads(p.read_text(encoding="utf-8")).items() if k in cfg})
    return cfg


def matched(rel: str, cfg: dict) -> bool:
    import fnmatch

    def hit(pat):
        return fnmatch.fnmatch(rel, pat) or (pat.startswith("**/") and fnmatch.fnmatch(rel, pat[3:]))

    return (not any(hit(p) for p in cfg["exclude"])) and any(hit(p) for p in cfg["include"])


def scan(root: pathlib.Path, cfg: dict, git_tracked: bool):
    gg = load_gate()
    tracked = None
    if git_tracked:
        cp = subprocess.run(["git", "ls-files"], cwd=str(root), capture_output=True, text=True,
                            encoding="utf-8", errors="replace", shell=False)
        tracked = set(cp.stdout.split())
    out: dict[str, dict] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules", "vendor"}]
        for fn in filenames:
            if not fn.endswith(".go"):
                continue
            fp = pathlib.Path(dirpath) / fn
            rel = fp.relative_to(root).as_posix()
            if not matched(rel, cfg):
                continue
            if tracked is not None and rel not in tracked:
                continue
            try:
                src = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if rel.endswith("_test.go"):        # 测试不算产品面
                continue
            masked = gg._mask(src, go=True)
            lines = masked.splitlines()
            unit = os.path.dirname(rel) or "."
            for i, line in enumerate(lines):
                m = RECV_RE.match(line)
                if not m:
                    continue
                depth, started, end = 0, False, i
                for j in range(i, len(lines)):
                    depth += lines[j].count("{") - lines[j].count("}")
                    if "{" in lines[j]:
                        started = True
                    if started and depth <= 0:
                        end = j
                        break
                key = f"{unit}|{m.group(1)}"
                e = out.setdefault(key, {"methods": 0, "files": []})
                e["methods"] += 1
                if rel not in e["files"]:
                    e["files"].append(rel)
    return {k: v for k, v in out.items()
            if v["methods"] >= cfg["min_methods_to_track"] or len(v["files"]) >= 3}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--git-tracked", action="store_true")
    ap.add_argument("--write-baseline", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--top", type=int, default=15)
    a = ap.parse_args()
    root = pathlib.Path(a.root).resolve()
    cfg = load_cfg(root)
    bpath = root / cfg["type_span_baseline"]
    cur = scan(root, cfg, a.git_tracked)
    lim_m, lim_f = cfg["max_type_methods_total"], cfg["max_type_impl_files"]
    print(f"TYPE-SPAN root={root} 入册类型={len(cur)} 阈值: methods>{lim_m} files>{lim_f}"
          f"（追踪下限 methods≥{cfg['min_methods_to_track']}）")
    for k, v in sorted(cur.items(), key=lambda kv: (-kv[1]["methods"], -len(kv[1]["files"])))[:a.top]:
        print(f"  methods {v['methods']:4d}  散在 {len(v['files']):2d} 文件  {k}")
    if a.list:
        return 0
    if a.write_baseline:
        bpath.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({k: {"methods": v["methods"], "files": len(v["files"])}
                              for k, v in sorted(cur.items())},
                             ensure_ascii=False, indent=1) + "\n"
        tmp = bpath.with_suffix(bpath.suffix + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, bpath)
        print(f"已写基线 {cfg['type_span_baseline']}（{len(cur)} 个类型）——此后只准减")
        return 0
    base = json.loads(bpath.read_text(encoding="utf-8")) if bpath.is_file() else {}
    hard = cfg["type_span_hard_threshold"]
    bad, shrank = [], []
    for k, v in sorted(cur.items()):
        m, f = v["methods"], len(v["files"])
        b = base.get(k)
        if b is None:
            if m > lim_m:
                bad.append(f"{k}: methods={m} > {lim_m}（新增类型，无基线）")
            if f > lim_f:
                bad.append(f"{k}: files={f} > {lim_f}（新增类型，无基线）")
            continue
        for name, val, lim, bv in (("methods", m, lim_m, b.get("methods", 0)),
                                   ("files", f, lim_f, b.get("files", 0))):
            if hard and val > lim:
                bad.append(f"{k}: {name} {bv} → {val} > 硬阈 {lim}（基线不放行）")
            elif val > bv:
                bad.append(f"{k}: {name} {bv} → {val}（不许变胖）")
            elif val < bv:
                shrank.append(f"{k}: {name} {bv} → {val}")
    if not base and not a.write_baseline:
        print("警告：尚无基线 ⇒ 只对新增类型判阈值；跑 --write-baseline 才会管住存量")
    for line in bad[:25]:
        print(f"  ✗ {line}")
    if len(bad) > 25:
        print(f"  …另有 {len(bad) - 25} 条")
    if shrank:
        print(f"  （{len(shrank)} 条可收紧，跑 --write-baseline 更新）")
    print(f"TYPE-SPAN {'FAIL' if bad else 'OK'} 超标/变胖={len(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
