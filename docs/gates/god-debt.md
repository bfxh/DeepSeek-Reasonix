# 上帝对象欠账台账

由 `scripts/gates/god_debt.py --write` 生成，**不要手改数字**——`--check` 会拿它与 `god-baseline.json` 对账，改了就红（想让数字变小只能真的去拆）。

<!-- debt-total: 253699 -->

- 阈值：文件 ≤ 1000 行 / 最长函数 ≤ 80 行 / 最大类型 ≤ 20 成员（同 `scripts/gates/god.gate.json`）
- 欠账文件 679 个，总欠账 253699（加权：行数×1 + 函数×3 + 成员×2——函数最难读，权重最高）
- 基线在册 7178 个文件；棘轮（god_gate）保证每项只准减 ⇒ 总欠账只准减
- 另有**跨文件上帝类型** 31 个 / 欠 11635（见下表第二张；总欠账 = 253699 + 11635 = 265334）

## 认领与清零

拆一块就在 `.agents/claims/<agent>.json` 里认领对应文件（避免几个智能体同时动一处），拆完跑 `python -X utf8 scripts/gates/gate.py --write` 重记基线，再跑 `--write` 更新本页。
三项硬阈（`god.gate.json` 的 `*_hard_threshold`）**全部翻 true 之后，欠账即清零**。

| # | 文件 | 欠账 | 明细 | 认领 |
| - | --- | --- | --- | --- |
| 1 | `desktop/frontend/src/lib/bridge.ts` | 18255 | 文件行数 5938→≤1000（超 4938）、最长函数行数 4519→≤80（超 4439） |  |
| 2 | `desktop/frontend/src/components/SettingsPanel.tsx` | 11615 | 文件行数 7242→≤1000（超 6242）、最长函数行数 1871→≤80（超 1791） |  |
| 3 | `desktop/app.go` | 11007 | 文件行数 11631→≤1000（超 10631）、最长函数行数 124→≤80（超 44）、最大类型成员数 142→≤20（超 122） |  |
| 4 | `desktop/app_test.go` | 9536 | 文件行数 10413→≤1000（超 9413）、最长函数行数 121→≤80（超 41） |  |
| 5 | `desktop/tabs.go` | 8084 | 文件行数 7894→≤1000（超 6894）、最长函数行数 444→≤80（超 364）、最大类型成员数 69→≤20（超 49） |  |
| 6 | `internal/boot/boot.go` | 7183 | 文件行数 2837→≤1000（超 1837）、最长函数行数 1840→≤80（超 1760）、最大类型成员数 53→≤20（超 33） |  |
| 7 | `internal/cli/chat_tui.go` | 6900 | 文件行数 4861→≤1000（超 3861）、最长函数行数 1003→≤80（超 923）、最大类型成员数 155→≤20（超 135） |  |
| 8 | `desktop/frontend/src/lib/useController.ts` | 5601 | 文件行数 4900→≤1000（超 3900）、最长函数行数 647→≤80（超 567） |  |
| 9 | `internal/control/controller.go` | 5413 | 文件行数 5882→≤1000（超 4882）、最长函数行数 181→≤80（超 101）、最大类型成员数 134→≤20（超 114） |  |
| 10 | `internal/control/controller_test.go` | 4421 | 文件行数 5361→≤1000（超 4361）、最长函数行数 100→≤80（超 20） |  |
| 11 | `desktop/frontend/src/components/Composer.tsx` | 3882 | 文件行数 4882→≤1000（超 3882） |  |
| 12 | `internal/boot/boot_test.go` | 3479 | 文件行数 4383→≤1000（超 3383）、最长函数行数 112→≤80（超 32） |  |
| 13 | `internal/cli/chat_tui_test.go` | 3327 | 文件行数 4327→≤1000（超 3327） |  |
| 14 | `internal/repair/update.go` | 3313 | 文件行数 3713→≤1000（超 2713）、最长函数行数 280→≤80（超 200） |  |
| 15 | `internal/repair/update_test.go` | 3001 | 文件行数 3893→≤1000（超 2893）、最长函数行数 116→≤80（超 36） |  |
| 16 | `internal/bot/gateway.go` | 2986 | 文件行数 3145→≤1000（超 2145）、最长函数行数 355→≤80（超 275）、最大类型成员数 28→≤20（超 8） |  |
| 17 | `desktop/frontend/src/components/CapabilitiesPanel.tsx` | 2690 | 文件行数 3444→≤1000（超 2444）、最长函数行数 162→≤80（超 82） |  |
| 18 | `internal/cli/cli.go` | 2685 | 文件行数 2749→≤1000（超 1749）、最长函数行数 392→≤80（超 312） |  |
| 19 | `internal/config/render.go` | 2673 | 文件行数 1714→≤1000（超 714）、最长函数行数 733→≤80（超 653） |  |
| 20 | `desktop/frontend/src/locales/zh.ts` | 2659 | 文件行数 3659→≤1000（超 2659） |  |
| 21 | `desktop/frontend/src/locales/en.ts` | 2658 | 文件行数 3658→≤1000（超 2658） |  |
| 22 | `desktop/frontend/src/locales/zh-TW.ts` | 2655 | 文件行数 3655→≤1000（超 2655） |  |
| 23 | `desktop/settings_app.go` | 2619 | 文件行数 3448→≤1000（超 2448）、最长函数行数 119→≤80（超 39）、最大类型成员数 47→≤20（超 27） |  |
| 24 | `desktop/tabs_topic_test.go` | 2608 | 文件行数 3593→≤1000（超 2593）、最长函数行数 85→≤80（超 5） |  |
| 25 | `internal/acp/service.go` | 2324 | 文件行数 3023→≤1000（超 2023）、最长函数行数 175→≤80（超 95）、最大类型成员数 28→≤20（超 8） |  |
| 26 | `internal/config/edit_test.go` | 2221 | 文件行数 3218→≤1000（超 2218）、最长函数行数 81→≤80（超 1） |  |
| 27 | `desktop/frontend/src/components/ApprovalModal.tsx` | 2209 | 文件行数 1013→≤1000（超 13）、最长函数行数 812→≤80（超 732） |  |
| 28 | `desktop/electron/src/main/index.ts` | 1818 | 最长函数行数 686→≤80（超 606） |  |
| 29 | `internal/config/load.go` | 1787 | 文件行数 2529→≤1000（超 1529）、最长函数行数 166→≤80（超 86） |  |
| 30 | `internal/bot/gateway_test.go` | 1785 | 文件行数 2707→≤1000（超 1707）、最长函数行数 106→≤80（超 26） |  |
| 31 | `internal/agent/save_test.go` | 1754 | 文件行数 2745→≤1000（超 1745）、最长函数行数 83→≤80（超 3） |  |
| 32 | `desktop/settings_app_test.go` | 1726 | 文件行数 2609→≤1000（超 1609）、最长函数行数 119→≤80（超 39） |  |
| 33 | `internal/agent/agent.go` | 1560 | 文件行数 2096→≤1000（超 1096）、最长函数行数 206→≤80（超 126）、最大类型成员数 63→≤20（超 43） |  |
| 34 | `internal/agent/save.go` | 1533 | 文件行数 2182→≤1000（超 1182）、最长函数行数 197→≤80（超 117） |  |
| 35 | `desktop/frontend/src/__tests__/composer-goal-toggle.test.tsx` | 1531 | 文件行数 2531→≤1000（超 1531） |  |
| 36 | `internal/installsource/install_source_test.go` | 1521 | 文件行数 2521→≤1000（超 1521） |  |
| 37 | `internal/config/edit.go` | 1398 | 文件行数 2398→≤1000（超 1398） |  |
| 38 | `internal/provider/openai/openai_test.go` | 1395 | 文件行数 2371→≤1000（超 1371）、最长函数行数 88→≤80（超 8） |  |
| 39 | `desktop/frontend/src/lib/types.ts` | 1373 | 文件行数 2373→≤1000（超 1373） |  |
| 40 | `internal/config/config.go` | 1372 | 文件行数 2315→≤1000（超 1315）、最长函数行数 81→≤80（超 1）、最大类型成员数 47→≤20（超 27） |  |

（另有 639 个欠账文件未列出，跑 `--write` 前的完整清单见命令输出）

## 跨文件上帝类型（`type_span_gate.py`）

按类型名聚合 `impl` 块：`methods > 40` 或 `files > 8` 即欠账（加权 方法×2 + 文件×5——职责发散比单纯方法多更难改）。这类**每个文件都很小**，按文件量规模的门抓不到，只有聚合才看得见。

| # | 类型（crate\|类型名） | 欠账 | 方法 | 散在文件 | 认领 |
| - | --- | --- | --- | --- | --- |
| 1 | `desktop|App` | 5104 | 1847（超 1807） | 306（超 298） |  |
| 2 | `internal/control|Controller` | 2056 | 803（超 763） | 114（超 106） |  |
| 3 | `internal/cli|chatTUI` | 1042 | 421（超 381） | 64（超 56） |  |
| 4 | `internal/agent|Agent` | 1029 | 372（超 332） | 81（超 73） |  |
| 5 | `internal/serve|Server` | 644 | 262（超 222） | 48（超 40） |  |
| 6 | `internal/config|Config` | 351 | 178（超 138） | 23（超 15） |  |
| 7 | `internal/sessioncatalog|Catalog` | 283 | 124（超 84） | 31（超 23） |  |
| 8 | `internal/agent|Session` | 227 | 116（超 76） | 23（超 15） |  |
| 9 | `internal/bot|BotGateway` | 166 | 113（超 73） | 12（超 4） |  |
| 10 | `internal/checkpoint|Store` | 91 | 83（超 43） | 9（超 1） |  |
| 11 | `internal/plugin|Host` | 82 | 81（超 41） | 8（超 0） |  |
| 12 | `desktop/internal/workspacestate|Store` | 66 | 63（超 23） | 12（超 4） |  |
| 13 | `internal/jobs|Manager` | 66 | 73（超 33） | 7（超 0） |  |
| 14 | `internal/acp|service` | 60 | 70（超 30） | 6（超 0） |  |
| 15 | `internal/session|Service` | 59 | 62（超 22） | 11（超 3） |  |
| 16 | `internal/session|Query` | 56 | 53（超 13） | 14（超 6） |  |
| 17 | `internal/sessioninbox|Store` | 38 | 59（超 19） | 6（超 0） |  |
| 18 | `internal/evidence|Ledger` | 35 | 55（超 15） | 9（超 1） |  |
| 19 | `internal/agent|UseCapabilityTool` | 34 | 47（超 7） | 12（超 4） |  |
| 20 | `desktop|WorkspaceTab` | 27 | 51（超 11） | 9（超 1） |  |
| 21 | `internal/installsource|installSourceTool` | 22 | 51（超 11） | 7（超 0） |  |
| 22 | `internal/agent|TaskTool` | 18 | 49（超 9） | 5（超 0） |  |
| 23 | `internal/browser/cdp|Executor` | 18 | 49（超 9） | 4（超 0） |  |
| 24 | `internal/skill|Store` | 18 | 49（超 9） | 6（超 0） |  |
| 25 | `internal/control|approvalManager` | 16 | 48（超 8） | 2（超 0） |  |
| 26 | `internal/session|Session` | 10 | 45（超 5） | 8（超 0） |  |
| 27 | `internal/turnevent|Ledger` | 6 | 43（超 3） | 5（超 0） |  |
| 28 | `internal/plugin|Client` | 5 | 34（超 0） | 9（超 1） |  |
| 29 | `internal/bot/feishu|adapter` | 2 | 41（超 1） | 4（超 0） |  |
| 30 | `internal/control|goalMachine` | 2 | 41（超 1） | 6（超 0） |  |
| 31 | `internal/workspacelease|Owner` | 2 | 41（超 1） | 2（超 0） |  |
