"""统一门禁入口（DeepSeek-Reasonix 版；形态取自 unified-rx-mcp 的 local_gate.py）。

一条命令跑完**与 CI 同一套**审核（CI 逐条显式调用同一批脚本 ⇒ 不漂移，由
`gate_selftest.py` 的 S1 锁死）。本仓另有一套 `scripts/local_audit.py`（S148：
repolint / vet / golangci / 明文 / 历史 / 依赖 / 上帝文件 / 时效 / 覆盖率），
那套管安全与流程，这一套管**结构与复杂度**，两者互补、各自独立判红。

  python3 -X utf8 scripts/gates/gate.py --fast    # 快门（pre-commit 同款，秒级+十几秒扫描）
  python3 -X utf8 scripts/gates/gate.py           # 全门（多跑 gofmt / go vet / go build）
  python3 -X utf8 scripts/gates/gate.py --list
  python3 -X utf8 scripts/gates/gate.py --only god-gate
  python3 -X utf8 scripts/gates/gate.py --no-go   # 无 Go 工具链时（**显式**，不静默）
  python3 -X utf8 scripts/gates/gate.py --write   # 重记全部基线（拆完一块后跑，要 git diff 过目）
  QJ_GATE_FORCE_FAIL=god-gate …                   # 自检：注入失败，验证门是真门

退出码：0 = 全绿；1 = 有门红；2 = 用法/环境错。
纪律：go 缺失默认 **FAIL 不静默**——确需跳过必须显式 `--no-go`。
"""
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PY = sys.executable
GO = shutil.which("go") or "go"
G = "scripts/gates/"

STEPS = [
    ("agent-gate", [PY, "-X", "utf8", G + "agent_gate.py"], "fast",
     "多智能体协作（声明/域不重叠/不越界）"),
    ("god-gate", [PY, "-X", "utf8", G + "god_gate.py", "--root", ".", "--git-tracked"], "fast",
     "上帝对象（文件/函数/类型规模棘轮 + 分项硬阈）"),
    ("type-span", [PY, "-X", "utf8", G + "type_span_gate.py", "--git-tracked"], "fast",
     "跨文件上帝类型（按接收者聚合方法数 / 散落文件数）"),
    ("arch-gate", [PY, "-X", "utf8", G + "arch_gate.py", "--git-tracked"], "fast",
     "架构约束（panic / os.Exit / unsafe / 直接打印 / 残留标记 / 长参数列表）"),
    ("sec-gate", [PY, "-X", "utf8", G + "sec_gate.py", "--git-tracked"], "fast",
     "安全（InsecureSkipVerify/本地 replace/无超时 Client/exec 注入/硬编码凭证/权限）"),
    ("conc-gate", [PY, "-X", "utf8", G + "conc_gate.py", "--git-tracked"], "fast",
     "并发（裸协程数/包级可变全局/time.After 泄漏/WaitGroup.Add 竞态/空 select）"),
    ("cyc-gate", [PY, "-X", "utf8", G + "cyc_gate.py", "--git-tracked"], "fast",
     "圈复杂度（函数分支点 >15 / >50 双档棘轮）"),
    ("iface-gate", [PY, "-X", "utf8", G + "iface_gate.py", "--git-tracked"], "fast",
     "接口隔离（方法 >12 棘轮 / >40 硬禁止）"),
    ("dep-gate", [PY, "-X", "utf8", G + "dep_gate.py", "--git-tracked"], "fast",
     "分层依赖（二进制不可被 internal 库化 / 内部依赖扇出棘轮）"),
    ("test-gate", [PY, "-X", "utf8", G + "test_gate.py", "--git-tracked"], "fast",
     "测试覆盖（新增源文件无伴生 _test.go 即红）"),
    ("dupe-gate", [PY, "-X", "utf8", G + "dupe_gate.py", "--git-tracked"], "fast",
     "重复代码（MinHash+LSH，雷同对新增即红）"),
    ("god-debt", [PY, "-X", "utf8", G + "god_debt.py", "--check"], "fast",
     "上帝对象欠账台账对账（数字不许手改）"),
    # 比棘轮更严厉的一步：改了**已经超阈**的文件，就必须把它变小（缺省比 HEAD，CI 传 PR base）
    ("god-touch", [PY, "-X", "utf8", G + "god_touch.py"], "fast",
     "碰了就得减（改超阈文件却没把它变小 = 红）"),
    ("selftest", [PY, "-X", "utf8", G + "gate_selftest.py"], "fast",
     "门禁自检（门不许被悄悄削弱/绕过）"),
    ("gofmt", [GO, "fmt", "-l", "."], "full", "gofmt（有输出即未格式化）"),
    ("vet", [GO, "vet", "./..."], "full", "go vet"),
    ("build", [GO, "build", "./..."], "full", "go build"),
]

# 写基线步骤：顺序有讲究——先 god 基线（arch 拿它当「已登记文件」名单），
# 再 type-span（台账要读它），最后重算台账。
WRITE_STEPS = [
    ("god-baseline", [PY, "-X", "utf8", G + "god_gate.py", "--root", ".", "--git-tracked",
                      "--write-baseline"]),
    ("type-span-baseline", [PY, "-X", "utf8", G + "type_span_gate.py", "--git-tracked",
                            "--write-baseline"]),
    ("dupe-baseline", [PY, "-X", "utf8", G + "dupe_gate.py", "--git-tracked", "--write-baseline"]),
    ("arch-baseline", [PY, "-X", "utf8", G + "arch_gate.py", "--git-tracked", "--write"]),
    ("sec-baseline", [PY, "-X", "utf8", G + "sec_gate.py", "--git-tracked", "--write"]),
    ("conc-baseline", [PY, "-X", "utf8", G + "conc_gate.py", "--git-tracked", "--write"]),
    ("cyc-baseline", [PY, "-X", "utf8", G + "cyc_gate.py", "--git-tracked", "--write"]),
    ("iface-baseline", [PY, "-X", "utf8", G + "iface_gate.py", "--git-tracked", "--write"]),
    ("dep-baseline", [PY, "-X", "utf8", G + "dep_gate.py", "--git-tracked", "--write"]),
    ("test-baseline", [PY, "-X", "utf8", G + "test_gate.py", "--git-tracked", "--write"]),
    ("god-debt", [PY, "-X", "utf8", G + "god_debt.py", "--write"]),
]


def run(argv, name, force_fail=None):
    if force_fail == name:
        return False, 0.0, f"[自检注入] QJ_GATE_FORCE_FAIL={name}"
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    t0 = time.time()
    cp = subprocess.run(argv, cwd=ROOT, env=env, shell=False, capture_output=True,
                        text=True, encoding="utf-8", errors="replace", timeout=3600)
    out = (cp.stdout or "") + (("\n" + cp.stderr) if cp.stderr else "")
    return cp.returncode == 0, time.time() - t0, out


def main(argv):
    if "--list" in argv:
        for n, _a, tier, why in STEPS:
            print(f"{tier:4s} {n:12s} {why}")
        return 0
    write = "--write" in argv
    want_fast = "--fast" in argv
    no_go = "--no-go" in argv
    only = None
    for i, a in enumerate(argv):
        if a == "--only" and i + 1 < len(argv):
            only = {s.strip() for s in argv[i + 1].split(",") if s.strip()}
    force_fail = os.environ.get("QJ_GATE_FORCE_FAIL")

    if write:
        print("== 重记基线（跑完请 git diff 过目：基线变松 = 门变松） ==")
        bad = []
        for name, cmd in WRITE_STEPS:
            ok, secs, out = run(cmd, name, force_fail)
            print(f"{'OK  ' if ok else 'FAIL'} {name:20s} {secs:6.1f}s")
            if not ok:
                bad.append(name)
                print("  " + "\n  ".join(out.strip().splitlines()[-12:]))
        print(f"GATE-WRITE {'OK' if not bad else 'FAIL'} {bad}")
        return 1 if bad else 0

    rows, failed, skipped = [], [], []
    for name, cmd, tier, why in STEPS:
        if want_fast and tier != "fast":
            continue
        if only is not None and name not in only:
            continue
        if no_go and name in ("gofmt", "vet", "build"):
            print(f"SKIP {name:12s} --no-go（显式跳过；红线语义：不算全绿）")
            skipped.append(name)
            continue
        if name in ("gofmt", "vet", "build") and not shutil.which("go"):
            print(f"FAIL {name:12s} go 不可用——不静默降级（要跳过请显式 --no-go）")
            failed.append(name)
            continue
        ok, secs, out = run(cmd, name, force_fail)
        # `gofmt -l` 永远退出 0，靠**有没有输出**判断（有输出 = 有文件没格式化）
        if name == "gofmt" and ok and out.strip():
            ok = False
        rows.append((name, ok, secs))
        print(f"{'OK  ' if ok else 'FAIL'} {name:12s} {secs:6.1f}s {why}")
        if not ok:
            failed.append(name)
            print("  " + "\n  ".join(out.strip().splitlines()[-12:]))
    total = sum(r[2] for r in rows)
    print(f"GATE {'OK' if not failed else 'FAIL'} steps={len(rows)} "
          f"skipped={skipped or '[]'} failed={failed} total={total:.1f}s")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
