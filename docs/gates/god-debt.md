# 上帝对象欠账台账

由 `scripts/gates/god_debt.py --write` 生成，**不要手改数字**——`--check` 会拿它与 `god-baseline.json` 对账，改了就红（想让数字变小只能真的去拆）。

<!-- debt-total: 86310 -->

- 阈值：文件 ≤ 1000 行 / 最长函数 ≤ 80 行 / 最大类型 ≤ 20 成员（同 `scripts/gates/god.gate.json`）
- 欠账文件 316 个，总欠账 86310（加权：行数×1 + 函数×3 + 成员×2——函数最难读，权重最高）
- 基线在册 4629 个文件；棘轮（god_gate）保证每项只准减 ⇒ 总欠账只准减
- 另有**跨文件上帝类型** 20 个 / 欠 4083（见下表第二张；总欠账 = 86310 + 4083 = 90393）

## 认领与清零

拆一块就在 `.agents/claims/<agent>.json` 里认领对应文件（避免几个智能体同时动一处），拆完跑 `python -X utf8 scripts/gates/gate.py --write` 重记基线，再跑 `--write` 更新本页。
三项硬阈（`god.gate.json` 的 `*_hard_threshold`）**全部翻 true 之后，欠账即清零**。

| # | 文件 | 欠账 | 明细 | 认领 |
| - | --- | --- | --- | --- |
| 1 | `internal/session/control/controller_test.go` | 4302 | 文件行数 5239→≤1000（超 4239）、最长函数行数 101→≤80（超 21） |  |
| 2 | `internal/assembly/boot/boot_test.go` | 3625 | 文件行数 4367→≤1000（超 3367）、最长函数行数 166→≤80（超 86） |  |
| 3 | `internal/platform/repair/update.go` | 3296 | 文件行数 3696→≤1000（超 2696）、最长函数行数 280→≤80（超 200） |  |
| 4 | `internal/platform/repair/update_test.go` | 3003 | 文件行数 3895→≤1000（超 2895）、最长函数行数 116→≤80（超 36） |  |
| 5 | `internal/contract/config/edit_test.go` | 2264 | 文件行数 3261→≤1000（超 2261）、最长函数行数 81→≤80（超 1） |  |
| 6 | `desktop/frontend-next/src/ui/Pane.tsx` | 1767 | 最长函数行数 669→≤80（超 589） |  |
| 7 | `internal/state/sessionstore/save_test.go` | 1757 | 文件行数 2748→≤1000（超 1748）、最长函数行数 83→≤80（超 3） |  |
| 8 | `internal/contract/config/render.go` | 1626 | 文件行数 1348→≤1000（超 348）、最长函数行数 506→≤80（超 426） |  |
| 9 | `internal/ext/installsource/install_source_test.go` | 1554 | 文件行数 2554→≤1000（超 1554） |  |
| 10 | `internal/state/sessionstore/save.go` | 1482 | 文件行数 2077→≤1000（超 1077）、最长函数行数 215→≤80（超 135） |  |
| 11 | `internal/model/openai/openai_test.go` | 1435 | 文件行数 2411→≤1000（超 1411）、最长函数行数 88→≤80（超 8） |  |
| 12 | `internal/runtime/agent/agent.go` | 1415 | 文件行数 1995→≤1000（超 995）、最长函数行数 214→≤80（超 134）、最大类型成员数 29→≤20（超 9） |  |
| 13 | `internal/frontend/cli/cli.go` | 1309 | 文件行数 1766→≤1000（超 766）、最长函数行数 261→≤80（超 181） |  |
| 14 | `internal/frontend/acp/server_test.go` | 1282 | 文件行数 2186→≤1000（超 1186）、最长函数行数 112→≤80（超 32） |  |
| 15 | `internal/contract/config/load.go` | 1252 | 文件行数 1994→≤1000（超 994）、最长函数行数 166→≤80（超 86） |  |
| 16 | `internal/session/control/refs.go` | 1215 | 文件行数 1204→≤1000（超 204）、最长函数行数 417→≤80（超 337） |  |
| 17 | `internal/contract/config/render_test.go` | 1198 | 文件行数 1556→≤1000（超 556）、最长函数行数 294→≤80（超 214） |  |
| 18 | `internal/contract/config/edit.go` | 1134 | 文件行数 2134→≤1000（超 1134） |  |
| 19 | `internal/base/i18n/i18n.go` | 1050 | 最大类型成员数 545→≤20（超 525） |  |
| 20 | `internal/tools/jobs/jobs.go` | 1049 | 文件行数 1925→≤1000（超 925）、最长函数行数 120→≤80（超 40）、最大类型成员数 22→≤20（超 2） |  |
| 21 | `internal/frontend/cli/cli_test.go` | 1043 | 文件行数 2043→≤1000（超 1043） |  |
| 22 | `internal/ext/plugin/plugin_test.go` | 1038 | 文件行数 1774→≤1000（超 774）、最长函数行数 168→≤80（超 88） |  |
| 23 | `desktop/frontend-next/src/state/session.ts` | 984 | 最长函数行数 408→≤80（超 328） |  |
| 24 | `internal/runtime/agent/extensions_test.go` | 970 | 文件行数 1970→≤1000（超 970） |  |
| 25 | `internal/contract/config/config.go` | 951 | 文件行数 1899→≤1000（超 899）、最大类型成员数 46→≤20（超 26） |  |
| 26 | `internal/contract/config/backfill_test.go` | 939 | 文件行数 1909→≤1000（超 909）、最长函数行数 90→≤80（超 10） |  |
| 27 | `internal/ext/hook/hook_test.go` | 901 | 文件行数 1901→≤1000（超 901） |  |
| 28 | `internal/runtime/recovery/decision_test.go` | 897 | 最长函数行数 379→≤80（超 299） |  |
| 29 | `internal/frontend/acp/service.go` | 895 | 文件行数 1603→≤1000（超 603）、最长函数行数 172→≤80（超 92）、最大类型成员数 28→≤20（超 8） |  |
| 30 | `desktop/frontend-next/src/ui/RemoteHosts.tsx` | 873 | 最长函数行数 371→≤80（超 291） |  |
| 31 | `internal/state/checkpoint/transaction.go` | 822 | 文件行数 1537→≤1000（超 537）、最长函数行数 175→≤80（超 95） |  |
| 32 | `internal/ext/plugin/plugin.go` | 798 | 文件行数 1675→≤1000（超 675）、最长函数行数 113→≤80（超 33）、最大类型成员数 32→≤20（超 12） |  |
| 33 | `internal/contract/config/provider_presets_test.go` | 795 | 最长函数行数 345→≤80（超 265） |  |
| 34 | `internal/runtime/agent/usecapability_test.go` | 793 | 文件行数 1790→≤1000（超 790）、最长函数行数 81→≤80（超 1） |  |
| 35 | `internal/runtime/coordinator/coordinator_test.go` | 760 | 文件行数 1760→≤1000（超 760） |  |
| 36 | `internal/model/openai/openai.go` | 745 | 文件行数 1304→≤1000（超 304）、最长函数行数 223→≤80（超 143）、最大类型成员数 26→≤20（超 6） |  |
| 37 | `workers/crash-report/src/index.ts` | 736 | 文件行数 1487→≤1000（超 487）、最长函数行数 163→≤80（超 83） |  |
| 38 | `internal/ext/hook/hook.go` | 695 | 文件行数 1584→≤1000（超 584）、最长函数行数 117→≤80（超 37） |  |
| 39 | `internal/platform/repair/plan_test.go` | 692 | 文件行数 1671→≤1000（超 671）、最长函数行数 87→≤80（超 7） |  |
| 40 | `internal/platform/update/apply_darwin.go` | 663 | 最长函数行数 301→≤80（超 221） |  |

（另有 276 个欠账文件未列出，跑 `--write` 前的完整清单见命令输出）

## 跨文件上帝类型（`type_span_gate.py`）

按类型名聚合 `impl` 块：`methods > 40` 或 `files > 8` 即欠账（加权 方法×2 + 文件×5——职责发散比单纯方法多更难改）。这类**每个文件都很小**，按文件量规模的门抓不到，只有聚合才看得见。

| # | 类型（crate\|类型名） | 欠账 | 方法 | 散在文件 | 认领 |
| - | --- | --- | --- | --- | --- |
| 1 | `internal/session/control|Controller` | 1261 | 508（超 468） | 73（超 65） |  |
| 2 | `internal/runtime/agent|Agent` | 808 | 299（超 259） | 66（超 58） |  |
| 3 | `internal/frontend/serve|Server` | 664 | 237（超 197） | 62（超 54） |  |
| 4 | `internal/contract/config|Config` | 327 | 161（超 121） | 25（超 17） |  |
| 5 | `internal/runtime/agent|contextWindow` | 214 | 112（超 72） | 22（超 14） |  |
| 6 | `internal/frontend/serve|Hub` | 154 | 97（超 57） | 16（超 8） |  |
| 7 | `internal/frontend/tui|model` | 134 | 97（超 57） | 12（超 4） |  |
| 8 | `internal/safety/evidence|Ledger` | 78 | 59（超 19） | 16（超 8） |  |
| 9 | `internal/state/checkpoint|Store` | 70 | 75（超 35） | 3（超 0） |  |
| 10 | `internal/frontend/acp|service` | 63 | 69（超 29） | 9（超 1） |  |
| 11 | `internal/state/sessionstore|Session` | 59 | 67（超 27） | 9（超 1） |  |
| 12 | `internal/contract/config|Roots` | 57 | 51（超 11） | 15（超 7） |  |
| 13 | `internal/runtime/delegation|TaskTool` | 48 | 59（超 19） | 10（超 2） |  |
| 14 | `internal/tools/jobs|Manager` | 38 | 59（超 19） | 5（超 0） |  |
| 15 | `internal/ext/plugin|Host` | 34 | 57（超 17） | 8（超 0） |  |
| 16 | `internal/ext/installsource|installSourceTool` | 33 | 54（超 14） | 9（超 1） |  |
| 17 | `internal/platform/browser|Session` | 20 | 50（超 10） | 8（超 0） |  |
| 18 | `internal/ext/extension/sidecar|Client` | 10 | 45（超 5） | 5（超 0） |  |
| 19 | `internal/state/sessioninbox|Store` | 6 | 43（超 3） | 5（超 0） |  |
| 20 | `internal/ext/plugin|Client` | 5 | 33（超 0） | 9（超 1） |  |
