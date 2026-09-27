"""弃用 ioutil 门：自 Go 1.16 起 `io/ioutil` 整包弃用，函数已迁到 os / io / io/fs。

  `ioutil.ReadFile`→`os.ReadFile`、`ioutil.ReadAll`→`io.ReadAll`、`ioutil.WriteFile`→
  `os.WriteFile`、`ioutil.ReadDir`→`os.ReadDir`、`ioutil.Discard`→`io.Discard`、
  `ioutil.NopCloser`→`io.NopCloser`、`ioutil.TempFile`/`TempDir`→`os.CreateTemp`/`os.MkdirTemp`。
  留着只是技术债，新代码不该再出现。

  X1 任何 `.go` 文件里出现 `ioutil.<func>` —— 棘轮：只准减（新增即红）。
      不排 `_test.go`：测试也在用 ioutil 同样是债，统一管。

用法：python3 -X utf8 scripts/gates/ioutil_gate.py [--git-tracked] [--list] [--write]
"""
import argparse
import importlib.util
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gates_common as gc  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
BASELINE = "docs/gates/ioutil-baseline.json"
IOUTIL = re.compile(r"\bioutil\.(ReadFile|ReadAll|WriteFile|ReadDir|Discard|NopCloser|"
                    r"TempFile|TempDir|TempFile|WriteFile)\b")


def load_god():
    spec = importlib.util.spec_from_file_location("god_gate_for_ioutil",
                                                  ROOT / "scripts" / "gates" / "god_gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def scan(root: pathlib.Path, git_tracked: bool):
    gg = load_god()
    cur = {}
    for rel in gc.go_files(root, git_tracked):
        text = gc.read_text(root, rel)
        if not text:
            continue
        masked = gg._mask(text, go=True)
        n = len(IOUTIL.findall(masked))
        if n:
            cur[rel] = n
    return cur


def main() -> int:
    ap = gc.add_args(argparse.ArgumentParser())
    a = ap.parse_args()
    cur = scan(ROOT, a.git_tracked)
    print(f"IOUTIL-GATE count={sum(cur.values())}")
    if a.list:
        for r, n in sorted(cur.items(), key=lambda kv: -kv[1])[:a.top]:
            print(f"  {n:3d}  {r}")
        return 0
    # 硬规则：当前全仓 0 处，出现任何 `ioutil.<func>` 即红（自 Go 1.16 起整包弃用，不进基线）。
    # 迁移目标：ReadFile→os.ReadFile / ReadAll→io.ReadAll / WriteFile→os.WriteFile /
    # ReadDir→os.ReadDir / Discard→io.Discard / NopCloser→io.NopCloser /
    # TempFile→os.CreateTemp / TempDir→os.MkdirTemp。
    bad = [f"{rel}: {n} 处弃用 ioutil（硬规则：自 Go 1.16 起弃用，改用 os/io/io/fs 对应函数）"
           for rel, n in sorted(cur.items(), key=lambda kv: -kv[1])]
    return gc.report("IOUTIL-GATE", bad, [])


if __name__ == "__main__":
    sys.exit(main())
