"""安全门：Go 里那些**写出来就是错**的东西，以及会慢慢积累的注入面。

  S0 `go.mod` 里的 `replace` 指向**本地路径** —— 硬：合进主干的依赖重写会让别人的构建
     悄悄指向你本机的目录（当前 0 条，所以当天就能开硬）。
  S1 `InsecureSkipVerify: true` —— **硬**：关掉 TLS 校验，当前 0 条 ⇒ 出现即红，
     不做基线祖父化（安全面不接受「历史上就有」）。
  S2 `http.DefaultClient` / `http.DefaultTransport` / `&http.Client{}` 不带 `Timeout`
     —— 棘轮：没有超时的 HTTP 客户端挂住时，整条请求链会一直占着 goroutine。
  S3 `exec.Command` 的参数不是纯字面量 —— 棘轮：变量拼进命令行就是注入面。
  S4 硬编码凭证（key/token/secret/password 后面跟 ≥12 字符的字面量）—— 棘轮。
  S5 写文件权限 0777 / 0666 —— 棘轮。

用法：python3 -X utf8 scripts/gates/sec_gate.py [--git-tracked] [--list] [--write]
"""
import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gates_common as gc  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
BASELINE = "docs/gates/sec-baseline.json"
INSECURE = re.compile(r"InsecureSkipVerify\s*:\s*true")
DEFAULT_CLIENT = re.compile(r"http\.(DefaultClient|DefaultTransport)")
CLIENT_LIT = re.compile(r"http\.Client\s*\{")
EXEC = re.compile(r"exec\.Command(?:Context)?\s*\(")
CRED = re.compile(r"(?i)\b(api[_-]?key|token|secret|password|passwd|private[_-]?key)\b\s*[:=]\s*"
                  r"\"([A-Za-z0-9+/=_-]{12,})\"")
PERM = re.compile(r"\b0(?:777|666)\b")


def scan(root: pathlib.Path, git_tracked: bool):
    cur = {"noclienttimeout": {}, "exec_var": {}, "cred": {}, "perm": {}}
    for rel in gc.go_files(root, git_tracked):
        text = gc.read_text(root, rel)
        if not text:
            continue
        n = len(DEFAULT_CLIENT.findall(text))
        # `&http.Client{` / `http.Client{` —— 同一个复合字面量里没有 Timeout 才算
        for m in CLIENT_LIT.finditer(text):
            tail = text[m.end():m.end() + 400]
            end = tail.find("}")
            block = tail[:end] if end > 0 else tail
            if "Timeout" not in block:
                n += 1
        if n:
            cur["noclienttimeout"][rel] = n
        n = 0
        for m in EXEC.finditer(text):
            tail = text[m.end():m.end() + 200]
            depth = 1
            args = ""
            for i, ch in enumerate(tail):
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        args = tail[:i]
                        break
            # 纯字符串字面量参数不算注入面；出现标识符/拼接就算
            if args and not re.fullmatch(r'\s*(?:"[^"]*"\s*,?\s*)+', args):
                n += 1
        if n:
            cur["exec_var"][rel] = n
        n = len([m for m in CRED.finditer(text) if not rel.endswith("_test.go")])
        if n:
            cur["cred"][rel] = n
        n = len(PERM.findall(text))
        if n:
            cur["perm"][rel] = n
    return cur


def hard_rules(root: pathlib.Path, bad: list):
    gomod = root / "go.mod"
    if gomod.is_file():
        for i, line in enumerate(gomod.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip().startswith("replace ") and ("=>" in line):
                target = line.split("=>")[-1].strip()
                if target.startswith((".", "/", "..")) or "file://" in target:
                    bad.append(f"S0 go.mod:{i}: replace 指向本地路径 {target} "
                               f"——主干上不许有依赖重写指向某人的本机目录")
    for rel in gc.go_files(root, True):
        if rel.endswith("_test.go"):      # 测试 TLS server 关校验是合理 fixture，不判
            continue
        text = gc.read_text(root, rel)
        for i, line in enumerate(text.splitlines(), 1):
            if INSECURE.search(line):
                bad.append(f"S1 {rel}:{i}: InsecureSkipVerify: true —— 关掉 TLS 校验，硬禁止")


def main() -> int:
    ap = gc.add_args(argparse.ArgumentParser())
    a = ap.parse_args()
    root = ROOT
    bpath = root / BASELINE
    cur = scan(root, a.git_tracked)
    print("SEC-GATE " + " ".join(f"{k}={sum(v.values())}" for k, v in cur.items()))
    if a.list:
        for k, v in cur.items():
            for r, n in sorted(v.items(), key=lambda kv: -kv[1])[:a.top]:
                print(f"  {k:16s} {n:3d}  {r}")
        return 0
    if a.write:
        gc.write_baseline(bpath, cur)
        print(f"已写基线 {BASELINE}——此后只准减（S0/S1 是硬规则，不进基线）")
        return 0
    base = gc.load_baseline(bpath)
    if not base:
        print(f"警告：无 {BASELINE} ⇒ 只对硬规则判；跑 --write 才会管住存量")
    bad, shrank = [], []
    for k in ("noclienttimeout", "exec_var", "cred", "perm"):
        gc.ratchet(cur[k], base.get(k, {}), k, bad, shrank)
    hard_rules(root, bad)
    return gc.report("SEC-GATE", bad, shrank)


if __name__ == "__main__":
    sys.exit(main())
