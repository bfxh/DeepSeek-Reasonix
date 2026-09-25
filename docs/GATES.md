# 结构与复杂度门禁

ci.yml 管「对不对」（编译、测试、lint），这一套管「会不会越改越难改」。全部零依赖、纯 Python，
不需要 Go 工具链——`make gates` 一条命令，约 3 分钟跑完 7000+ 个文件、23 道门。

```bash
make gates            # 快门（pre-commit 同款）
make gates-full       # 多跑 gofmt / go vet / go build
python3 -X utf8 scripts/gates/gate.py --list
python3 -X utf8 scripts/gates/gate.py --only god-gate
make gates-baseline   # 拆完一块后重记基线（**必须 git diff 过目**：基线变松 = 门变松）
```

移植自 `D:/开发/unified-rx-mcp`，按 Go 适配：`god_gate` 认 `func` 与 `type X struct`、
掩掉反引号原始字符串与 rune 字面量（否则万行文件的括号配平会整体失真）；
`type_span_gate` 按**接收者**聚合方法；`dupe_gate` 用 LSH 分带，7000 个文件十几秒。

## 一、上帝对象门（`god_gate.py`）

| 指标 | 阈值 | 棘轮 | 硬阈 | 当前存量 |
| --- | --- | --- | --- | --- |
| `file_lines` 单文件行数 | 1000 | 只准减 | 待开 | 681 个文件超阈，最大 `desktop/app.go` 11631 行 |
| `max_fn_lines` 最长函数 | 80 | 只准减 | 待开 | 最大 `internal/boot/boot.go` 的 `build` **1840 行** |
| `max_type_members` 结构体字段数 | 20 | 只准减 | 待开 | 最大 `Controller` **134 个字段** |

本仓原先已有一份 `.godfiles-baseline.json`（只量文件行数与字节、阈值 5000、只准变大就拦）。
这一份往下钻到函数与类型，阈值也收紧一个数量级；两份并存，互不替代。

拆函数导致的行数增长按「函数降幅 ≥ 文件涨幅」放行（否则正确的重构会被棘轮逼着去关门）。

## 二、跨文件上帝类型（`type_span_gate.py`）

按**接收者**把方法聚合起来看：`func (a *App) Foo()` 全算 `App` 的，不管散在哪个文件。
按文件量规模永远看不见这一层——`desktop/app.go` 拆成 306 个文件之后每个文件都不大。

| 指标 | 阈值 | 当前最重 |
| --- | --- | --- |
| 一个类型的方法总数 | 40 | `desktop\|App` **1847 个方法 / 306 个文件** |
| 这些方法散在几个文件 | 8 | `internal/control\|Controller` 803 / 114 |

## 三、碰了就得减（`god_touch.py`）—— 比棘轮更严厉的那一步

棘轮只说「不许变胖」，于是存量能永远躺着：11631 行的 `desktop/app.go`，只要没人给它加行，
它就永远是 11631 行，而每个人都在绕着它走。

**规则**：改了**已经超阈**的文件，就必须把它变小（配置 `touch_tax_min_reduction`，默认至少 1）。
没减就红，哪怕只加了一行注释。没超阈的文件不受这条管，仍受棘轮管。

CI 传 PR 的 base sha 只判本次改动；本地缺省比 `git diff HEAD`。

## 四、架构约束门（`arch_gate.py`）

本仓 `tools/repolint/layers.go` 已经管住包与 import 边界，这一道补它管不到的坏味道：

| 编号 | 规则 | 判定 |
| --- | --- | --- |
| G1 | `panic(` 出现在产品代码（库代码 panic 会把整个进程带下去） | 棘轮 |
| G2 | `os.Exit(` 出现在 `cmd/` 与 `package main` 之外 | 棘轮 |
| G3 | `import "unsafe"` 出现在**非平台后缀**文件且不在 `third_party/` | **红（硬）**，需带 why 登记豁免 |
| G4 | `fmt.Print*` / `println` 出现在产品代码（日志该走 logger） | 棘轮 |
| G5 | 注释里未落地的 TODO / FIXME / HACK / XXX | 棘轮 |
| G6 | 形参超过 6 个的函数（Go 里这种签名基本都该换 options 结构体） | 棘轮 |

G3 的硬规则特意不进基线：unsafe 是安全面，不能「历史上就有」就算了。
平台后缀（`_windows.go` / `_darwin.go` …）与 `third_party/` 是 syscall 互操作的正当用法，放行；
`internal/tool/builtin/codeindex_treesitter.go`（cgo FFI）走 `docs/gates/unsafe-exempt.json` 登记。

## 四-B、附加六道门（安全 / 并发 / 复杂度 / 接口 / 分层 / 测试）

这六道都是棘轮（存量全进基线，只拦**新增**）；真正零容忍的硬规则放在 sec / dep / iface。

### 安全门（`sec_gate.py`）

| 编号 | 规则 | 判定 | 当前存量 |
| --- | --- | --- | --- |
| S0 | `go.mod` 的 `replace` 指向本机路径（依赖重写会让别人构建指向你本机） | **硬** | 0 |
| S1 | `InsecureSkipVerify: true` 关掉 TLS 校验 | **硬**（排除 `_test.go` 的 TLS fixture） | 0 |
| S2 | 无 `Timeout` 的 `http.Client`（挂住时整条请求链占着 goroutine） | 棘轮 | 195 |
| S3 | `exec.Command` 参数含变量（命令行注入面） | 棘轮 | 192 |
| S4 | 硬编码凭证字面量（key/token/secret/password ≥12 字符） | 棘轮 | 0 |
| S5 | 文件权限 0777 / 0666 | 棘轮 | 4 |

### 并发门（`conc_gate.py`）

| 编号 | 规则 | 判定 | 当前存量 |
| --- | --- | --- | --- |
| C1 | 裸 `go func(` 数量（并发面大小） | 棘轮 | 883 |
| C2 | 包级可变全局（共享可变状态 = 数据竞争温床） | 棘轮 | 1317 |
| C3 | `time.After(` 在循环里（定时器泄漏，Go 最常见） | 棘轮 | 85 |
| C4 | `go func` 体里 `wg.Add(`（Add 须在启动协程前，放里面是竞态） | 棘轮 | 6 |
| C5 | 空 `select {}`（永久阻塞） | 棘轮 | 0 |

C4/C5 是棘轮不是硬规则：存量大多在 `_test.go`（测试并发的常见写法），硬开会当场卡住
所有并行开发。正确做法是录基线、只许减。本仓真正"零容忍"的硬规则在 sec（S0/S1）、
dep（D1）、iface（I2）。

### 圈复杂度门（`cyc_gate.py`）

纯文本统计分支点（if / for / range / switch / select / case / && / || / ?:），**只判产品代码**
（测试 setup 函数复杂度高是常态，不算产品风险）。

| 指标 | 阈值 | 判定 | 当前 |
| --- | --- | --- | --- |
| 函数圈复杂度 | >15 | 棘轮 | 1483 |
| 函数圈复杂度 | >50（单测无法覆盖） | 棘轮 | 32（最大 `desktop/tabs.go:buildTabControllerWithContextCore` = 91） |

### 接口隔离门（`iface_gate.py`）

| 指标 | 阈值 | 判定 | 当前最大 |
| --- | --- | --- | --- |
| 接口方法数 | >12 | 棘轮 | 8 |
| 接口方法数 | >40（失去"小契约"意义） | **硬** | 31（`internal/control/port.go:Capabilities`） |

### 分层依赖门（`dep_gate.py`）

| 编号 | 规则 | 判定 |
| --- | --- | --- |
| D1 | `internal/**` import `desktop` 或 `cmd/*`（二进制被库化 = 架构倒挂） | **硬** |
| D2 | 单包 import 的 internal 包数（内部依赖扇出） | 棘轮（当前 3399 条边，最大 `internal/boot/boot.go` 45） |

依赖方向错了，编译器只拦**环**、不拦**烂方向**。D1 钉死"二进制不可被当库 import"；
D2 钉住单包别突然 import 十几个 internal 包（上帝依赖）。

### 测试覆盖门（`test_gate.py`）

`internal/`、`cmd/`、`desktop/` 下的源文件，若同目录没有 `_test.go` 伴生，记一笔。
棘轮只拦**新增**无测试文件（存量欠账进基线），逼人给新代码写测试，不逼人回填历史。
当前 7 个缺测试文件。

## 四-C、再加三道（错误吞没 / 循环 defer / 休眠）

专盯"编译器不报、但迟早出事或拖慢"的坏味道，三道都是棘轮、只判产品代码（测试不判）。

### 错误处理门（`err_gate.py`）

| 指标 | 阈值 | 判定 | 当前 |
| --- | --- | --- | --- |
| `if err != nil {` 块里 `return nil` / `return nil, nil`（错误发生却假装成功） | 出现即记 | 棘轮 | 105（最大 `desktop/sessions.go`、`internal/agent/save.go`、`internal/repair/update.go` 各 6） |

只抓"明确假装成功"这一种：`return err` / `return fmt.Errorf(...)` 是正确写法，不判；
也不抓 `_ = f()`（那是正当忽略，误报太多）。

### 循环 defer 门（`loopdefer_gate.py`）

| 指标 | 阈值 | 判定 | 当前 |
| --- | --- | --- | --- |
| `for`/`range` 体里**直接子层**的 `defer` | 出现即记 | 棘轮 | 3 |

`defer` 直到**函数**返回才执行，不是循环迭代结束。循环里 `defer` 关文件/解锁会一直攒到
函数返回——循环一万次攒一万个，FD / 锁一直占着。嵌套函数字面量里的 defer 不计数（跟闭包走）。

### 休眠门（`sleep_gate.py`）

| 指标 | 阈值 | 判定 | 当前 |
| --- | --- | --- | --- |
| 产品代码（非 `_test.go`）里的 `time.Sleep(` | 出现即记 | 棘轮 | 37（最大 `internal/serve/session_reclaim.go` 4） |

轮询等某事发生、循环里 sleep 节流、启动顺序靠 sleep 凑——都会让程序在 CI / 弱机器上 flake、
在延迟敏感路径上卡顿。正确做法是 `sync.Cond` / channel / `context` 取消 / `time.After`+`select`。

## 四-D、再加六道（context 首参 / context.TODO 硬禁 / 协程 recover / 弃用 ioutil 硬禁 / 忽略错误返回 / 行长）

专盯 Go 里「编译器不报、但是约定 / 可靠性 / 可维护性」的坑。两道**硬规则**（当前为零，出现即红、
不进基线），四道**棘轮**（存量进基线，只拦新增）。

### context 首参门（`ctxfirst_gate.py`）

| 指标 | 阈值 | 判定 | 当前 |
| --- | --- | --- | --- |
| 函数签名里出现 `context.Context` 但不是第一个参数 | 出现即记 | 棘轮（仅产品代码，排除 `_test.go`） | 29（最大 `internal/plugin/plugin.go` 5） |

`context.Context` 不排第一，调用方就没法传取消 / 超时 / 值，整条 ctx 传播废了。掩码后按括号配平取签名，顶层拆参数找其位置。

### context.TODO 硬禁门（`ctxtodo_gate.py`）

| 指标 | 判定 | 当前 |
| --- | --- | --- |
| 产品代码（排除 `_test.go`）出现 `context.TODO()` | **硬**（出现即红，不进基线） | 0 |

`context.Background()` 在 main / server 顶层是正当的「根」；`context.TODO()` 是「我欠着 ctx 从哪来」的半成品标记。当前零处，硬规则锁死不许再出现。

### 协程 recover 门（`grrecover_gate.py`）

| 指标 | 阈值 | 判定 | 当前 |
| --- | --- | --- | --- |
| 产品代码（排除 `_test.go`）里 `go func` 字面量、体内无 `recover()` 兜底 | 出现即记 | 棘轮 | 141（最大 `internal/remote/sshtest/sshtest.go` 4） |

一个 goroutine panic 会拖垮整个进程；凡是自己开协程跑可能出错的逻辑，标准做法是 defer + recover 包一层。`go foo()` 调具名函数静态看不进来，本门只判函数字面量。

### 弃用 ioutil 硬禁门（`ioutil_gate.py`）

| 指标 | 判定 | 当前 |
| --- | --- | --- |
| 任意 `.go` 文件出现 `ioutil.<func>`（ReadFile/ReadAll/WriteFile/ReadDir/Discard/NopCloser/TempFile/TempDir） | **硬**（出现即红，不进基线） | 0 |

自 Go 1.16 起 `io/ioutil` 整包弃用，函数已迁到 `os` / `io` / `io/fs`：ReadFile→os.ReadFile、ReadAll→io.ReadAll、WriteFile→os.WriteFile、ReadDir→os.ReadDir、Discard→io.Discard、NopCloser→io.NopCloser、TempFile→os.CreateTemp、TempDir→os.MkdirTemp。

### 忽略错误返回门（`errignore_gate.py`）

| 指标 | 阈值 | 判定 | 当前 |
| --- | --- | --- | --- |
| 产品代码（排除 `_test.go`）里 `_ = f()` / `x, _ = f()` / `_, x := f()` 丢弃函数调用结果 | 出现即记 | 棘轮 | 2743（最大 `internal/bot/gateway.go` 63） |

errcheck 这道著名 linter 管的正是不处理 error。本门做语法层保守版：只盯「右值是调用（行内含 `(`）」且「不是 for/if/switch/select 初始化子句」的丢弃——`for _, v := range` / `if x, err := f()` 这类正当用法直接跳过。

### 行长门（`linelen_gate.py`）

| 指标 | 阈值 | 判定 | 当前 |
| --- | --- | --- | --- |
| 单行超过 200 字符 | 出现即记 | 棘轮 | 1189（最大 `internal/billing/catalog.go` 28） |

Go 官方不强制行长，但超长行在 review / diff / 终端里都难读，也常是「一个表达式塞太多东西」或「超长 struct tag / import 路径」的信号。只拦**新增**超长行，改文件时顺手断行即可。

## 五、重复代码门（`dupe_gate.py`）

MinHash + **LSH 分带**：7000 个源文件两两比是 2500 万对，纯 Python 跑不动；
切成 16 带分桶后只比候选对，全仓十几秒。Jaccard ≥ 0.85 即雷同，**基线里没有的新对 ⇒ 红**。

`benchmarks/` 是 e2e 语料夹具（同一个 .py 在几十个 task 目录里各放一份，天然 100% 雷同），
不进扫描面——判它只会把基线灌满噪声，真正的雷同一条也看不见。当前基线 7 对，都是真复制：
`workers/accounts` 与 `workers/crash-report` 的 `errors.ts` / `cors.ts` 完全相同。

## 六、多智能体协作门（`agent_gate.py`）

本仓同时有多个智能体在开发。一智能体一声明文件（`.agents/claims/<id>.json`，文件名互异
⇒ 天然无写冲突），机器判：A1 格式 / A2 重名 / A3 **域重叠** / A4 越界 / A5 未登记。
前五条命中即红。协议全文见 [`.agents/CLAIMS.md`](../.agents/CLAIMS.md)。

## 七、门禁自检（`gate_selftest.py`）

门全是仓库里的文本文件——删掉 workflow 一行、调大阈值、把硬阈改回 false、把钩子里的
`--fast` 去掉，都不会让任何测试变红，门却已经没了。**门静默变弱比没有门更危险**。

- S1 本地 `gate.py` 的 STEPS 与 `gates.yml` **双向同源**；
- S2 `pre-commit` 必须挂着 `gate.py --fast`；
- S3 阈值只许收紧、硬阈只许 false→true、`include` 不许少、`exclude` 不许多；
- S4 `god_gate.py` 的本仓适配（脚本同目录取配置 / 三档硬阈 / Go 支持）仍在；
- S5 十七份基线在位且是合法 JSON（`god` / `dupe` / `type-span` / `arch` / `sec` / `conc` / `cyc` / `iface` / `dep` / `test` / `err` / `loopdefer` / `sleep` / `ctxfirst` / `grrecover` / `errignore` / `linelen`）；`ctxtodo` / `ioutil` 是硬规则，无基线；
- S6 `.agents/CLAIMS.md` 在位；
- S7 `ci.yml` 的 `gate-shape` 锚在位。

S7 与 ci.yml 那道**互盯**：gates.yml 被整个删掉时它自己不会跑，只有 ci.yml 会发现；
反过来 S7 又能发现有人把 ci.yml 的锚摘掉。CI 另跑一次注入失败自检（门必须红，绿了说明门是假的）。

## 八、接进流水线的地方

| 位置 | 跑什么 |
| --- | --- |
| `.githooks/pre-commit` | `gate.py --fast`（`make hooks` 安装） |
| `.github/workflows/gates.yml` | 二十个 job：上帝对象（含类型跨度与碰了就得减）/ 架构 / 安全 / 并发 / 复杂度 / 接口隔离 / 分层依赖 / 测试覆盖 / 错误吞没 / 循环 defer / 休眠 / context 首参 / context.TODO 硬禁 / 协程 recover / 弃用 ioutil 硬禁 / 忽略错误返回 / 行长 / 雷同 / 多智能体 / 自检 |
| `ci.yml` 的 `gate-shape` job | 钉子挂在这里：gates.yml 被删时它还能报警 |
| `Makefile` | `make gates` / `gates-full` / `gates-baseline` |
| `CONTRIBUTING.md` | 面向贡献者的四条硬规矩（**不动 `REASONIX.md`**：它进 cache-stable 的 system prefix，多一行就是每轮都要付的前缀成本，这个仓对它有 byte-stable 要求） |

## 九、欠账台账

`docs/gates/god-debt.md`：681 个欠账文件 + 31 个跨文件上帝类型，加权总欠 265496。
台账数字与基线对账 ⇒ **手改即红**，想变小只能真的去拆。认领流程见 `.agents/CLAIMS.md`。
