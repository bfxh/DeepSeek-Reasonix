"""重复代码门（Go/TS/Python，纯 stdlib bottom-k MinHash + LSH 分带）。

**为什么不用逐对比**：本仓 7000+ 个源文件，两两比是 2500 万对，纯 Python 跑不动。
这里用 MinHash + **LSH 分带**（128 维指纹切成 16 带，只有命中同一桶的对才真比），
复杂度降到接近线性，全仓一遍约十几秒。

判据：文件对 Jaccard ≥ `--threshold`（默认 0.85）即雷同；**基线里没有的新对 ⇒ 红**。
与 `type_span_gate.py` 一样走「只准减」的棘轮：`--write-baseline` 记现状，
此后出现基线里没有的对就红，消失的对提示可收紧。

用法：
  python3 -X utf8 scripts/gates/dupe_gate.py --list            # 只列当前雷同对
  python3 -X utf8 scripts/gates/dupe_gate.py --write-baseline   # 记基线（人工过目后提交）
  python3 -X utf8 scripts/gates/dupe_gate.py --git-tracked      # 门：新增即红
退出码：0 = 通过；1 = 有新增雷同；2 = 配置错。
"""
import argparse
import fnmatch
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
BASELINE = "docs/gates/dupe-baseline.json"
NG, K, BANDS = 5, 128, 16
DEFAULT_THRESHOLD = 0.85
EXTS = (".go", ".ts", ".tsx", ".py", ".mjs", ".js")
EXCLUDE_DIRS = {".git", "node_modules", "target", "__pycache__", "dist", "build",
                "vendor", ".venv", "venv"}
EXCLUDE_PAT = ("**/node_modules/**", "**/vendor/**", "**/dist/**", "**/site/**",
               "**/*/generated/**", "**/generated/**", "**/*.generated.*", "**/.git/**",
               # benchmarks/ 下是 e2e **语料夹具**：同一个 .py 在几十个 task 目录里各放一份，
               # 天然 100% 雷同。那是测试数据不是产品代码，判它只会把基线灌满噪声
               # （实测：821 对里 800+ 全是这类，真正的雷同一条都看不见）。
               "**/benchmarks/**")
LINE_COMMENT = re.compile(r"//.*$", re.M)
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
HASH_COMMENT = re.compile(r"^\s*#.*$", re.M)
STR_LIT = re.compile(r'"(?:\\.|[^"\\])*"')
RAW_STR = re.compile(r"`[^`]*`", re.S)
TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+")
MAX_BUCKET = 400            # 单桶过大就跳过（生成物/夹具面会挤在一起，判了也没意义）


def matched(rel: str) -> bool:
    def hit(pat):
        return fnmatch.fnmatch(rel, pat) or (pat.startswith("**/") and fnmatch.fnmatch(rel, pat[3:]))
    return not any(hit(p) for p in EXCLUDE_PAT)


def collect(root: pathlib.Path, git_tracked: bool):
    tracked = None
    if git_tracked:
        cp = subprocess.run(["git", "ls-files"], cwd=str(root), capture_output=True, text=True,
                            encoding="utf-8", errors="replace", shell=False)
        tracked = set(cp.stdout.split())
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            if not fn.endswith(EXTS):
                continue
            fp = pathlib.Path(dirpath) / fn
            rel = fp.relative_to(root).as_posix()
            if not matched(rel):
                continue
            if tracked is not None and rel not in tracked:
                continue
            out.append(rel)
    return sorted(out)


def normalize(text: str) -> str:
    """去掉注释与字符串字面量：**字面量不同、骨架相同**才是要抓的雷同。"""
    text = BLOCK_COMMENT.sub(" ", text)
    text = RAW_STR.sub(' `` ', text)
    text = STR_LIT.sub(' "" ', text)
    text = LINE_COMMENT.sub(" ", text)
    text = HASH_COMMENT.sub(" ", text)
    return text


def fingerprint(text: str):
    toks = TOKEN.findall(normalize(text))
    if len(toks) < NG:
        return None
    seen = set()
    for i in range(len(toks) - NG + 1):
        g = " ".join(toks[i:i + NG])
        h = hashlib.blake2b(g.encode("utf-8"), digest_size=8).digest()
        seen.add(int.from_bytes(h, "little"))
    return sorted(seen)[:K]


def jaccard(a, b) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def candidates(fps):
    """LSH：按带分桶，只把「至少共命中一带」的对作为候选。"""
    seen = set()
    buckets: dict[tuple, list] = {}
    for idx, fp in fps:
        sk = sorted(fp)[:K]
        for b in range(BANDS):
            band = sk[b * (K // BANDS):(b + 1) * (K // BANDS)]
            if len(band) < K // BANDS:
                break
            key = (b, hashlib.blake2b(b",".join(str(x).encode() for x in band),
                                      digest_size=8).digest())
            buckets.setdefault(key, []).append((idx, sk))
    for _key, members in buckets.items():
        if len(members) > MAX_BUCKET or len(members) < 2:
            continue
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i][0], members[j][0]
                if a != b:
                    seen.add((a, b) if a < b else (b, a))
    return seen


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--write-baseline", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--git-tracked", action="store_true")
    a = ap.parse_args()
    root = pathlib.Path(a.root).resolve()
    bpath = root / BASELINE

    rels = collect(root, a.git_tracked)
    fps = []
    for idx, rel in enumerate(rels):
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        s = fingerprint(text)
        if s and len(s) >= 16:
            fps.append((idx, set(s)))
    pairs = candidates(fps)
    by_idx = dict(fps)
    cur = {}
    for x, y in pairs:
        sim = jaccard(by_idx[x], by_idx[y])
        if sim >= a.threshold:
            p, q = sorted((rels[x], rels[y]))
            cur[f"{p}|{q}"] = round(sim, 3)
    print(f"DUPE-GATE root={root} 文件={len(fps)} 候选对={len(pairs)} 阈值={a.threshold} "
          f"当前雷同对={len(cur)}")
    for key, sim in sorted(cur.items(), key=lambda kv: -kv[1])[:12]:
        print(f"  {sim:.3f}  {key}")
    if len(cur) > 12:
        print(f"  …另有 {len(cur) - 12} 对")
    if a.list:
        return 0
    if a.write_baseline:
        bpath.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"policy": "雷同对基线：新增即红（scripts/gates/dupe_gate.py，"
                                        "MinHash+LSH，纯 stdlib）",
                              "threshold": a.threshold, "ng": NG, "k": K, "bands": BANDS,
                              "pairs": sorted(cur)}, ensure_ascii=False, indent=1) + "\n"
        tmp = bpath.with_suffix(bpath.suffix + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, bpath)
        print(f"已写基线 {BASELINE}（{len(cur)} 对）——此后只准减")
        return 0
    if not bpath.is_file():
        print(f"警告：无 {BASELINE} ⇒ 先跑 --write-baseline 才会管住存量")
        return 0
    base = set(json.loads(bpath.read_text(encoding="utf-8"))["pairs"])
    new = sorted(set(cur) - base)
    gone = sorted(base - set(cur))
    for k in new[:20]:
        print(f"  ✗ 新增雷同对 {cur[k]:.3f}  {k}")
    if len(new) > 20:
        print(f"  …另有 {len(new) - 20} 对")
    if gone:
        print(f"  （{len(gone)} 对已消失，可收紧基线）")
    if new:
        print("DUPE-GATE FAIL 新增雷同对 —— 抽公共函数/复用已有实现，别再复制一份")
        return 1
    print("DUPE-GATE OK 无新增雷同对")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
