#!/bin/sh
# 审计账本 .audit-ledger.json 的副本深扫仪式脚本（S148 落地，S147 提案 P2）。

# 职责：对工作树副本做一次"外部深扫"，并把 seal（头/条数/日期）记入账本；
# freshness 步骤据此判断审计是否超期。本脚本是**仪式入口**，深扫自身交给
# unified-rx 工具箱（secrets_hunt / near_dupes / ast_scan 等），此处只记账。
# 用法：python3 scripts/audit_ledger.py --seal <报告.md>
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

LEDGER = Path(__file__).resolve().parent.parent / ".audit-ledger.json"


def _head():
    cp = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                        text=True)
    return cp.stdout.strip() if cp.returncode == 0 else "unknown"


def main(argv):
    if "--seal" not in argv:
        print("usage: scripts/audit_ledger.py --seal <报告>")
        return 1
    idx = argv.index("--seal")
    if idx + 1 >= len(argv):
        print("缺少报告路径")
        return 1
    report = argv[idx + 1]
    round_no = str(len(json.loads(LEDGER.read_text(encoding="utf-8")).get("entries", [])) + 1) if LEDGER.exists() else "1"
    entry = {"round": f"S{round_no}", "date": str(date.today()), "head": _head(),
             "report": report}
    data = json.loads(LEDGER.read_text(encoding="utf-8")) if LEDGER.exists() else {}
    data.setdefault("entries", []).append(entry)
    LEDGER.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"sealed round={entry['round']} head={entry['head'][:12]} report={report}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))