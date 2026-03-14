<div align="center">

# TuiRedis 🔴

一款基于 Python & [Textual](https://textual.textualize.io/) 构建的、美观且高性能的 Redis 终端可视化管理工具。

[English](README.md) | [中文说明](README_zh-CN.md)

<br>
<img src="./docs/imgs/1.png" alt="TuiRedis 主要视图" width="800">
<img src="./docs/imgs/2.png" alt="TuiRedis 数值视图" width="800">

</div>

---

### 🚀 核心特性
- **🔗 灵活的连接管理** — 支持连接单机 Redis、通过 Redis Sentinel 自动发现主库、连接 Redis Cluster，以及通过 SSH 隧道安全连接。
- **🧭 多 Sentinel 节点支持** — 可配置一个或多个 Sentinel 节点，自动解析当前主库。
- **🔁 Sentinel 故障切换恢复** — 在 Sentinel 主从切换、连接中断或出现 `READONLY` 错误后，常见读写操作会自动重连并重试。
- **🔐 更安全的连接保存** — 连接配置默认不落盘密码，只有显式勾选后才会保存 Redis / Sentinel / SSH 密码。
- **🗂️ 动态数据库识别** — 单机模式下会根据服务端配置动态识别逻辑数据库数量，不再默认假设只有 `0..15`。
- **🌲 层级化键值浏览器** — 树形结构自动按照 `:` 分隔符折叠 Keys，并支持实时模糊搜索过滤。
- **⏱️ TTL 过期状态指示** — Key 按过期时间着色：🔴 紧急（< 60s）、⏱ 即将过期（< 1h）。
- **☑ 多选 & 批量删除** — 在 Key 树中按 `Space` 选择 Key，`Ctrl+D` 一键批量删除所有选中项。
- **📄 高级数据查看器** — 原生支持完整查看及修改 `String`、`List`、`Hash`、`Set` 和 `Sorted Set` 数据结构。
- **⚡ 异步无阻塞加载** — Key 列表、Key 详情、服务器信息、批量操作和分页加载都已移出 UI 线程，并带有加载提示和过期响应丢弃保护。
- **⚡ 高性能弹性分页加载** — 利用原生 SCAN 游标，即使拥有数百万 Key 也能流畅加载不卡顿。Hash 和 Set 类型支持基于 `HSCAN`/`SSCAN` 游标的分页加载。
- **📋 一键复制到剪贴板** — 一键复制 String 类型的值到系统剪贴板。
- **📤 数据导出** — 将任意 Key 的值导出为本地文件（String → `.txt`，结构化类型 → `.json`）。
- **📊 服务器状态监控** — 实时查看 Redis 内存开销、连接客户端数量和各数据库键数量占比。Cluster 连接会显示聚合后的摘要信息。
- **✨ 全功能 CRUD** — 无缝创建、读取、更新和删除键值。
- **🎨 现代暗黑主题** — 沉浸式的终端 UI 体验及顺滑的动画交互。
- **🛠️ IRedis 强强联合** — 按 `Ctrl+T` 一键进入 `iredis` 交互式会话；在 iredis 中按 `Ctrl+Z` 即可挂起并立刻返回 TuiRedis；再次按 `Ctrl+T` 可悍美恢复上次的 iredis 会话记录不丢失。

### 📦 安装指南
TuiRedis 已经发布至 PyPI，您可以使用常用的 Python 包管理工具进行安装。

**使用 pipx (推荐)**
```bash
pipx install tuiredis
```

**使用 uvx / uv**
```bash
uvx tuiredis
# 或
uv tool install tuiredis
```

**使用 pip**
```bash
pip install tuiredis
```

**从源码安装**
```bash
# 克隆项目仓库
git clone https://github.com/Wooden-Robot/tuiredis.git
cd tuiredis

# 使用 uv 同步并安装依赖
uv sync

# 运行项目
uv run tuiredis
```

### 💻 使用姿势
如果您是通过 `pipx` 或 `pip` 将 TuiRedis 安装到了全局环境中，您可以直接在终端中随时使用 `tuiredis` 命令启动。如果您是在源码目录下开发或运行，请使用 `uv run tuiredis`。
```bash
# 直接启动，并在 TUI 中通过可视化弹窗输入连接信息
tuiredis

# 命令行直连（适用快速启动场景）
tuiredis -H 127.0.0.1 -p 6379 -a mypassword -n 0 -c

# 通过 Redis Sentinel 自动发现主库并连接
tuiredis --sentinel --sentinel-host 127.0.0.1 --sentinel-port 26379 --sentinel-master mymaster -a mypassword -c

# 通过多个 Redis Sentinel 节点连接
tuiredis --sentinel --sentinel-node 127.0.0.1:26379 --sentinel-node 127.0.0.1:26380 --sentinel-master mymaster -a mypassword -c

# 连接 Redis Cluster 入口节点
tuiredis --cluster -H 127.0.0.1 -p 7000 -a mypassword -c

# 通过 SSH 隧道安全连接
tuiredis -H 127.0.0.1 -p 6379 --ssh-host my-bastion.com --ssh-user root --ssh-key ~/.ssh/id_rsa -c

# 查看所有受支持的启动参数
tuiredis --help
```

### Redis 模式支持说明
- `standalone`：完整支持。
- `sentinel`：已支持主库发现；可在连接页面配置，或通过 `--sentinel ...` 使用，也支持多 Sentinel 节点。
- `replica`：可读，但写操作在只读副本上可能失败。
- `cluster`：已支持通过 `RedisCluster` 连接；仅允许 `DB 0`，禁用 DB 切换。Key 扫描可跨集群执行，服务器信息页显示聚合后的摘要视图。
- `cluster + SSH tunnel`：暂不支持。
- `sentinel + SSH tunnel`：暂不支持。

### 补充说明
- 保存连接时，默认不会把 Redis / Sentinel / SSH 密码写入磁盘，除非勾选 `Save passwords to disk`。
- 在 cluster 模式下，原生命令中的 `SELECT` 会被直接拒绝，因为 Redis Cluster 只支持 `DB 0`。
- `Server Info` 页会明确标注 cluster 为聚合视图，sentinel 为控制平面视图，避免误解当前数据语义。

### ⌨️ 快捷键列表
| 快捷键 | 功能说明 |
|--------|----------|
| `q` | 退出程序 |
| `F5` | 刷新 Key 树和服务器状态 |
| `/` | 焦点跳转至搜索框 |
| `n` | 创建新的 Key |
| `Space` | 在 Key 树中切换选中状态 |
| `Ctrl+D` | 批量删除所有选中的 Key |
| `Tab` | 在不同面板区域间切换焦点 |
| `Ctrl+o`| 切换/重新连接 Redis 实例 |
| `Ctrl+t`| 切换 IRedis 会话 — 启动、挂起（在 iredis 内按 `Ctrl+Z`）、恢复，一键丝滑 |
| `Ctrl+i`| 切换/显示服务器详细状态信息面板 |

---
*Requirements: Python >= 3.10 / Redis Server*
