"""架构约束门（Go 版）：把「写给人看的规矩」变成机器判。

本仓 `tools/repolint/layers.go` 已经管住了**包与 import 边界**，这一道补它管不到的：
代码里的坏味道与禁词。全部走「只准减」的棘轮（新增即红），只有 `unsafe` 是硬规则。

  G1 `panic(` 出现在产品代码（非 `_test.go`）—— 库代码 panic 会把整个进程带下去，
     错误应该往上返回。棘轮。
  G2 `os.Exit(` 出现在 `cmd/` 与 `package main` 之外 —— 库里调 os.Exit，调用方连清理的机会都没有。棘轮。
  G3 `import "unsafe"` —— **硬**：只允许出现在**平台后缀文件**（`_windows.go` / `_darwin.go` /
     `_unix.go` / `_linux.go`）与 `third_party/` 里（syscall 互操作本来就得用），
     其余一律红；确实要用的走 `docs/gates/unsafe-exempt.json` **带 why 登记**。
     不做基线祖父化——unsafe 是安全面，不能「历史上就有」就算了。
  G4 `fmt.Print*` / `print` / `println` 出现在产品代码 —— 日志要走统一的 logger，
     直接打 stdout 会绕掉日志级别与结构化字段。棘轮。
  G5 注释里未落地的 TODO / FIXME / HACK / XXX。棘轮。
  G6 形参超过 6 个的函数 —— Go 里这种签名基本都该换成 options 结构体。棘轮。

用法：
  python3 -X utf8 scripts/gates/arch_gate.py --list    # 看看现在违反多少
  python3 -X utf8 scripts/gates/arch_gate.py --write    # 记基线
  python3 -X utf8 scripts/gates/arch_gate.py --git-tracked   # 门
退出码：0 = 通过；1 = 命中；2 = 配置错。
"""
import argparse
import fnmatch
import json
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
BASELINE = "docs/gates/arch-baseline.json"
EXCLUDE_PAT = ("**/node_modules/**", "**/vendor/**", "**/.git/**", "**/*/generated/**",
               "**/generated/**", "**/*.generated.*", "**/benchmarks/**", "**/testdata/**")
PANIC_RE = re.compile(r"(?<![A-Za-z0-9_.])panic\s*\(")
EXIT_RE = re.compile(r"(?<![A-Za-z0-9_.])os\.Exit\s*\(")
UNSAFE_RE = re.compile(r'^\s*(?:_\s+|[A-Za-z_]\w*\s+)?"unsafe"', re.M)
PRINT_RE = re.compile(r"(?<![A-Za-z0-9_.])(?:fmt\.Print(?:f|ln)?|print|println)\s*\(")
MARK_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b")
LINE_COMMENT = re.compile(r"//.*$", re.M)
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
STR_LIT = re.compile(r'"(?:\\.|[^"\\])*"')
RAW_STR = re.compile(r"`[^`]*`", re.S)
FUNC_RE = re.compile(r"^func\s+(?:\([^)]*\)\s+)?([A-Za-z_]\w*)")
MAX_PARAMS = 6
# unsafe 只允许在这些地方：平台后缀的 syscall 互操作文件 + 第三方目录 + 带 why 的豁免登记
PLATFORM_SUFFIX = ("_windows.go", "_darwin.go", "_unix.go", "_linux.go", "_android.go", "_ios.go")
EXEMPT_FILE = "docs/gates/unsafe-exempt.json"


def git(*args):
    return subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", shell=False).stdout


def matched(rel: str) -> bool:
    def hit(pat):
        return fnmatch.fnmatch(rel, pat) or (pat.startswith("**/") and fnmatch.fnmatch(rel, pat[3:]))
    return not any(hit(p) for p in EXCLUDE_PAT)


def go_files(git_tracked: bool):
    tracked = set(git("ls-files").split()) if git_tracked else None
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules", "vendor"}]
        for fn in filenames:
            if not fn.endswith(".go"):
                continue
            rel = (pathlib.Path(dirpath) / fn).relative_to(ROOT).as_posix()
            if not matched(rel):
                continue
            if tracked is not None and rel not in tracked:
                continue
            out.append(rel)
    return sorted(out)


def code_only(text: str) -> str:
    t = BLOCK_COMMENT.sub("", text)
    t = RAW_STR.sub("``", t)
    t = STR_LIT.sub('""', t)
    return LINE_COMMENT.sub("", t)


def count_params(sig: str) -> int:
    """数形参：按顶层逗号切（跳过括号/方括号内的）。"""
    i = sig.find("(")
    j = sig.rfind(")")
    if i < 0 or j <= i:
        return 0
    inner = sig[i + 1:j]
    depth, n, cur = 0, 0, False
    for ch in inner:
        if ch in "([{<":
            depth += 1
        elif ch in ")]}>":
            depth -= 1
        if ch == "," and depth == 0:
            if cur:
                n += 1
            cur = False
        elif not ch.isspace():
            cur = True
    if cur:
        n += 1
    return n


def scan(rels):
    res = {"panic": {}, "exit": {}, "unsafe": {}, "print": {}, "mark": {}, "params": {}}
    for rel in rels:
        try:
            raw = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        product = not rel.endswith("_test.go")
        code = code_only(raw)
        if UNSAFE_RE.search(raw):
            res["unsafe"][rel] = 1
        if product:
            n = len(PANIC_RE.findall(code))
            if n:
                res["panic"][rel] = n
            if "package main" not in raw and not rel.startswith("cmd/"):
                n = len(EXIT_RE.findall(code))
                if n:
                    res["exit"][rel] = n
            n = len(PRINT_RE.findall(code))
            if n:
                res["print"][rel] = n
        n = len(MARK_RE.findall(raw))
        if n:
            res["mark"][rel] = n
        longp = 0
        for line in raw.splitlines():
            m = FUNC_RE.match(line)
            if not m:
                continue
            idx = line.find("(")
            if idx < 0:
                continue
            if count_params(line[idx:]) > MAX_PARAMS:
                longp += 1
        if longp:
            res["params"][rel] = longp
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--git-tracked", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--top", type=int, default=6)
    a = ap.parse_args()
    bpath = ROOT / BASELINE
    files = go_files(a.git_tracked)
    cur = scan(files)
    print(f"ARCH-GATE Go 文件={len(files)} " +
          " ".join(f"{k}={sum(v.values())}" for k, v in cur.items()))
    if a.list:
        for k, v in cur.items():
            for r, n in sorted(v.items(), key=lambda kv: -kv[1])[:a.top]:
                print(f"  {k:7s} {n:3d}  {r}")
        return 0
    if a.write:
        bpath.parent.mkdir(parents=True, exist_ok=True)
        tmp = bpath.with_suffix(bpath.suffix + ".tmp")
        tmp.write_text(json.dumps(cur, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        os.replace(tmp, bpath)
        print(f"已写基线 {BASELINE}——此后只准减（unsafe 不走基线，永远红）")
        return 0
    base = json.loads(bpath.read_text(encoding="utf-8")) if bpath.is_file() else {}
    if not base:
        print(f"警告：无 {BASELINE} ⇒ 只对 unsafe 判；跑 --write 才会管住存量")
    bad, shrank = [], []
    for k in ("panic", "exit", "print", "mark", "params"):
        for rel, v in sorted(cur[k].items()):
            bv = base.get(k, {}).get(rel, 0)
            if v > bv:
                bad.append(f"G·{k} {rel}: {bv} → {v}（新增 {v - bv} 处，只准减）")
            elif v < bv:
                shrank.append(f"{k} {rel}: {bv} → {v}")
    exempt = set()
    ep = ROOT / EXEMPT_FILE
    if ep.is_file():
        doc = json.loads(ep.read_text(encoding="utf-8"))
        for e in doc.get("entries", []):
            if not e.get("why"):
                bad.append(f"G3 豁免条目缺 why：{e}——豁免必须写明理由")
            else:
                exempt.add(e["path"])
    for rel in sorted(cur["unsafe"]):
        # `_windows_test.go` 这类要**先脱掉 `_test.go`** 再看平台后缀，
        # 否则测试文件全被误判（实测 7 个，全是 *_windows_test.go）
        stem = rel[:-len("_test.go")] + ".go" if rel.endswith("_test.go") else rel
        if stem.endswith(PLATFORM_SUFFIX) or "/third_party/" in rel or rel in exempt:
            continue
        bad.append(f"G3 {rel}: import \"unsafe\"——只允许平台后缀文件与 third_party；"
                   f"确需使用请在 {EXEMPT_FILE} 里带 why 登记")
    for line in bad[:25]:
        print(f"  ✗ {line}")
    if len(bad) > 25:
        print(f"  …另有 {len(bad) - 25} 条")
    if shrank:
        print(f"  （{len(shrank)} 条可收紧，跑 --write 更新）")
    print(f"ARCH-GATE {'FAIL' if bad else 'OK'} 命中={len(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
