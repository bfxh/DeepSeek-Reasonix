"""门禁脚本的共用件（零依赖，纯 stdlib）。

为什么抽出来：新加的六道门（安全 / 并发 / 复杂度 / 接口隔离 / 分层依赖 / 测试覆盖）
判据各不相同，但「扫哪些文件、基线怎么读写、棘轮怎么判、结果怎么报」完全一样。
各写一遍就会有六份各差一点的副本——判据口径一旦漂移，同一个文件在不同门里算出来的
数不一样，比没有门更糟。

本文件**不是一道门**（不进 `gate.py` 的 STEPS、不出现在 workflow 里），只被各门 import。
"""
import fnmatch
import json
import os
import pathlib
import subprocess
import sys

EXCLUDE_PAT = ("**/node_modules/**", "**/vendor/**", "**/.git/**", "**/*/generated/**",
               "**/generated/**", "**/*.generated.*", "**/benchmarks/**", "**/testdata/**",
               "**/third_party/**")
EXCLUDE_DIRS = {".git", "node_modules", "vendor", "target", "__pycache__", "dist", "build"}


def matched(rel: str, extra_exclude=()) -> bool:
    def hit(pat):
        return fnmatch.fnmatch(rel, pat) or (pat.startswith("**/") and fnmatch.fnmatch(rel, pat[3:]))

    return not any(hit(p) for p in tuple(EXCLUDE_PAT) + tuple(extra_exclude))


def go_files(root: pathlib.Path, git_tracked: bool, suffix=".go", extra_exclude=()):
    """受扫文件清单（**相对路径，正斜杠**）；`--git-tracked` 时只算已跟踪的。"""
    tracked = None
    if git_tracked:
        cp = subprocess.run(["git", "ls-files"], cwd=str(root), capture_output=True,
                            text=True, encoding="utf-8", errors="replace", shell=False)
        tracked = set(cp.stdout.split())
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            if not fn.endswith(suffix):
                continue
            rel = (pathlib.Path(dirpath) / fn).relative_to(root).as_posix()
            if not matched(rel, extra_exclude):
                continue
            if tracked is not None and rel not in tracked:
                continue
            out.append(rel)
    return sorted(out)


def read_text(root: pathlib.Path, rel: str) -> str:
    try:
        return (root / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def mask_go(text: str) -> str:
    """Go 源码掩码（掩掉注释/字符串/反引号原始串/rune，避免里面的花括号骗配平）。

    复用 god_gate 的实现，避免各门各写一份、口径漂移。
    """
    import importlib.util
    gp = pathlib.Path(__file__).resolve().parent / "god_gate.py"
    spec = importlib.util.spec_from_file_location("god_gate_mask", gp)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._mask(text, go=True)


def load_baseline(path: pathlib.Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        sys.exit(f"基线 {path.name} 不是合法 JSON（{e}）——若上次写入被中断，重跑 --write 即可")


def write_baseline(path: pathlib.Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)          # 原子替换：中断也不留半截基线


def ratchet(cur: dict, base: dict, label: str, bad: list, shrank: list) -> None:
    """只准减：新增即红，减少则提示可收紧。"""
    for rel, v in sorted(cur.items()):
        bv = base.get(rel, 0)
        if v > bv:
            bad.append(f"{label} {rel}: {bv} → {v}（新增 {v - bv} 处，只准减）")
        elif v < bv:
            shrank.append(f"{label} {rel}: {bv} → {v}")


def report(name: str, bad: list, shrank: list, limit: int = 25) -> int:
    for line in bad[:limit]:
        print(f"  ✗ {line}")
    if len(bad) > limit:
        print(f"  …另有 {len(bad) - limit} 条")
    if shrank:
        print(f"  （{len(shrank)} 条可收紧，跑 --write 更新）")
    print(f"{name} {'FAIL' if bad else 'OK'} 命中={len(bad)}")
    return 1 if bad else 0


def add_args(ap):
    ap.add_argument("--git-tracked", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--top", type=int, default=8)
    return ap
