# 网络加速（客户端侧）

English version: [NETWORK_ACCELERATION.md](./NETWORK_ACCELERATION.md)

## 范围与非目标

**范围**：让资源/raw/archive 下载（以及可选的只读 Git 流量）在到 github.com 链路慢或被墙时更快。

**明确非目标**：**不需要 Reasonix 自己的服务器**。没有中继、没有 CDN、没有代理集群、
没有 telemetry 上报端点。测速、分片调度、校验、回退全部在客户端进程内完成；
第三方镜像一律视为不可信的公开文件代理。

## 档位

| 档位 | 行为 | 副作用 |
| --- | --- | --- |
| `off` | 什么都不碰 | 无 |
| `download`（默认） | 把下载链接改写为最快端点 | 无 |
| `git-readonly` | 额外写 `git config --local url.<fastest>.insteadOf https://github.com/` | 改本地 git 配置，写 receipt |

`git-readonly` 不作为默认：写 git 配置是副作用，只对瓶颈在 `fetch`/`clone` 的用户值得。

## 端点池与打分

```text
候选：
  direct   https://github.com                         （永远在池内、永远参与排序）
  mirrors  https://<mirror-host>/https://github.com   （prefix 型）
  raw      https://raw.githubusercontent.com（+ 镜像）
  api      https://api.github.com  → 永不走镜像（涉及凭据与写操作）
```

```text
score = w1 * exp(-rttP50 / R0) + w2 * successRate(窗口) - w3 * penalty
penalty：近期出现校验和不一致 / TLS 错误 / 5xx 峰值 → 大幅降权 + 冷静期
```

探测只用最小的只读资源（几 KB 的 raw 文件），绝不消耗 API 配额。
直连永远留在候选池：镜像全挂时降级为「没加速」，绝不会变成「不可用」。

## 多连接下载

与「换镜像」正交：同一个文件，用多个连接并行拉。

```text
HEAD → Content-Length + Accept-Ranges: bytes
  ├─ 不支持 Range，或小于阈值 → 单连接（切片没有意义）
  └─ 分片：N 路并发 `Range: bytes=a-b`
        → 分片落 <dest>.part.<i>（长度不符即判失败）
        → 按序拼接 → <dest>
        → sha256 校验：不一致 → 删产物 + 清分片 + 换下一个源
```

- **断点续传**：分片进度写在 `<dest>.state.json`；重跑只拉缺的分片，
  并校验分片文件确实存在（杜绝假进度）。
- **重试**：单片重试 3 次，仍失败则放弃该源，换下一个候选。
- **顺序**：直连永远是第一个候选，镜像只作回退。

## 强制安全规则

1. **push 永不走镜像**：绝不写 `pushInsteadOf`；写 `insteadOf` 前先检查 remote 的
   push URL，发现被镜像污染就移除。
2. **校验和强制**：有官方 sha256 就必须比对，不一致即丢弃产物并将该镜像纳入冷静期。
   宁可慢，不可脏。
3. **TLS 不降级**：禁止 `http.sslVerify=false`，禁止忽略证书错误。
4. **凭据不转发**：携带 token 的请求一律直连官方。
5. **可一键撤销**：每次写 git 配置都记 receipt（含撤销参数），逆序回放即可完整回滚。
   没有 receipt 的动作不允许执行。

## 配置项

| 键 | 默认 | 含义 |
| --- | --- | --- |
| `github.autoAccelerate` | `true` | 启动时自动测速并启用 |
| `github.mode` | `download` | 见档位表 |
| `github.mirrors` | `[]` | 自定义镜像（仅 https） |
| `github.requireChecksum` | `true` | 比对官方 sha256 |
| `download.connections` | `4` | 单下载并发连接数 |
| `download.chunkBytes` | `1 MiB` | 分片大小 |
| `download.minSizeForChunks` | `8 MiB` | 小于此值走单连接 |
| `download.resume` | `true` | 断点续传 |

## 可观测性

每个操作都进宿主统计（次数、p50/p95/max、成功率，见 [HOST_METRICS.zh-CN.md](./HOST_METRICS.zh-CN.md)）。
两个最值得盯的数字：

- `download.fetch` 的 p95 —— 加了连接数仍不改善，说明瓶颈在链路不在并发。
- `github.bench` 的成功率 —— 镜像开始出现校验失败时，这里会先于用户反馈暴露。

## 验收

- 镜像可用时：≥ 80% 的下载走非直连端点，且 0 例校验和不一致被放行。
- 镜像全不可达时：下载仍走直连成功，未修改任何配置，除日志外不打扰用户。
- `undo` 能把 git 配置逐字节还原。
