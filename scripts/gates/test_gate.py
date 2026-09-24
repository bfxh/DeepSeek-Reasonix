"""测试覆盖门：新代码必须有测试，存量欠账认领清零。

  形态：每个 `internal/`、`cmd/`、`desktop/` 下的**非测试** `.go` 文件，若同目录没有
  任何 `_test.go`，算一条"缺测试"。

  T1 缺测试文件数量 —— 棘轮：只准减（新加的源文件没带测试即红）。
      存量欠账巨大，进基线后只有**新增**无测试文件才会红——逼人给新代码写测试，
      而不是逼人回填十万行历史。

  为什么只用"同目录有没有 _test.go"这种粗判：纯文本、零依赖、秒级、可判红；
  真正的覆盖率由 golangci / `go test -cover` 在别处管，这里只管"新文件有没有测试伴生"。

用法：python3 -X utf8 scripts/gates/test_gate.py [--git-tracked] [--list] [--write]
"""
import argparse
import collections
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gates_common as gc  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
BASELINE = "docs/gates/test-baseline.json"
SCAN_ROOTS = ("internal", "cmd", "desktop")


def scan(root: pathlib.Path, git_tracked: bool):
    cur = {}
    by_dir = collections.defaultdict(lambda: {"src": 0, "test": 0})
    for rel in gc.go_files(root, git_tracked):
        if not rel.startswith(SCAN_ROOTS):
            continue
        d = rel.rsplit("/", 1)[0]
        if rel.endswith("_test.go"):
            by_dir[d]["test"] += 1
        else:
            by_dir[d]["src"] += 1
    for rel in gc.go_files(root, git_tracked):
        if not rel.startswith(SCAN_ROOTS) or rel.endswith("_test.go"):
            continue
        d = rel.rsplit("/", 1)[0]
        if by_dir[d]["test"] == 0:          # 同目录没有任何测试
            cur[rel] = 1
    return cur


def main() -> int:
    ap = gc.add_args(argparse.ArgumentParser())
    a = ap.parse_args()
    root = ROOT
    bpath = root / BASELINE
    cur = scan(root, a.git_tracked)
    print(f"TEST-GATE missing={len(cur)}")
    if a.list:
        for r in sorted(cur)[:a.top]:
            print(f"  {r}")
        if len(cur) > a.top:
            print(f"  …另有 {len(cur) - a.top} 个缺测试文件")
        return 0
    if a.write:
        gc.write_baseline(bpath, cur)
        print(f"已写基线 {BASELINE}（{len(cur)} 个缺测试文件）——此后只准减")
        return 0
    base = gc.load_baseline(bpath)
    if not base:
        print(f"警告：无 {BASELINE} ⇒ 不判；跑 --write 才会管住存量")
    bad, shrank = [], []
    gc.ratchet(cur, base, "test", bad, shrank)
    return gc.report("TEST-GATE", bad, shrank)


if __name__ == "__main__":
    sys.exit(main())
