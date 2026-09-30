# 宿主调用统计（本地）

English version: [HOST_METRICS.md](./HOST_METRICS.md)

## 为什么

加速、下载、汉化、解释代码有个共同点：**没有数字就说不清好不好**。
没有次数和耗时分布，"感觉慢"只是 anecdote，每次回退都是用户先发现而不是我们先发现。

这是一份**本地**登记表，不是 telemetry：数据不出机器。

## 记什么

按 `subsystem.operation` 聚合：

| 字段 | 含义 |
| --- | --- |
| `count` | 调用次数 |
| `okCount` / `failCount` | 成功/失败分开——快失败和慢失败是两个不同的问题 |
| `successRate` | 成功率 |
| `p50Ms` / `p95Ms` / `maxMs` / `avgMs` | 耗时分布，不只用平均值糊弄 |
| `lastMs` | 最近一次耗时 |

可选的 `meta` 带维度值（如下载的 `sources`/`connections`、汉化的 `items`、解释的 `lines`），
这样 p95 变慢时能和相关输入规模对照，而不是靠猜。

埋点操作：`mcp.connectAll`、`mcp.rewire`、`github.bench`、`github.undo`、
`download.fetch`、`i18n.extract`、`i18n.translate`、`explain.code`、`explain.hover`。

## 不记什么

- 不记源码内容、不记提示词与响应体；
- 不记与操作无关的路径，不记个人标识；
- **不上报**：数据只落在 `<stateDir>/metrics.jsonl`，滚动保留 5000 条；
- `metrics.enabled=false` 即完全关闭，一行都不写。

## 报表

```text
subsystem.operation    count  ok  fail  rate   p50    p95    max    last
download.fetch             8   7     1  87.5%  820ms  1900ms 2400ms  760ms
github.bench               3   3     0 100.0%   95ms   140ms  140ms  110ms
i18n.translate             2   1     1  50.0% 1200ms  1200ms 1200ms 1200ms
explain.hover             56  41    15  73.2%    3ms    12ms   18ms    4ms
```

怎么用这些数字：

- `download.fetch` p95 不随 `connections` 增加而改善 ⇒ 瓶颈在链路不在并发，别再加连接数；
- `i18n.translate` 成功率下降 ⇒ 浏览器翻译后端不可用了，管线按设计失败关闭；
- `explain.hover` 失败率高 ⇒ 大多是符号未命中，说明扫描器该换成真正的语言服务；
- `mcp.connectAll` p95 抬升 ⇒ 某个 server 握手超时，先查健康状态，别怪模型。

## 实现要点

- `timed(subsystem, operation, fn, meta?)` 包装异步调用：成功失败都记，失败照抛，
  埋点不改变控制流；
- 落盘是 fire-and-forget，写失败只记日志继续——统计绝不能拖垮被统计的操作；
- 载入时跳过损坏行，一条脏数据不至于丢掉整段历史；
- 失败也计时。卡死的错误路径正是要看的东西。

## 开放问题

1. 宿主统计是并进 `reasonix doctor`（与运行时诊断一起展示），还是单独一条命令？
2. 除了 5000 条上限，要不要再加按时间的保留策略（如 7 天）？
3. 将来若做可选上报，是否以这份计数为底？还是严格分开，好让这份登记表保持可审计的简单性？
