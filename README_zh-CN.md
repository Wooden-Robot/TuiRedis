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
- **🔗 灵活的连接管理** — 支持快速连接任意 Redis 实例（支持密码验证、指定 DB 索引与 SSH 隧道）。
- **🌲 层级化键值浏览器** — 树形结构自动按照 `:` 分隔符折叠 Keys，并支持实时模糊搜索过滤。
- **⏱️ TTL 过期状态指示** — Key 按过期时间着色：🔴 紧急（< 60s）、⏱ 即将过期（< 1h）。
- **☑ 多选 & 批量删除** — 在 Key 树中按 `Space` 选择 Key，`Ctrl+D` 一键批量删除所有选中项。
- **📄 高级数据查看器** — 原生支持完整查看及修改 `String`、`List`、`Hash`、`Set` 和 `Sorted Set` 数据结构。
- **⚡ 高性能弹性分页加载** — 利用原生 SCAN 游标，即使拥有数百万 Key 也能流畅加载不卡顿。Hash 和 Set 类型支持基于 `HSCAN`/`SSCAN` 游标的分页加载。
- **📋 一键复制到剪贴板** — 一键复制 String 类型的值到系统剪贴板。
- **📤 数据导出** — 将任意 Key 的值导出为本地文件（String → `.txt`，结构化类型 → `.json`）。
- **📊 服务器状态监控** — 实时查看 Redis 内存开销、连接客户端数量和各数据库键数量占比。
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

# 通过 SSH 隧道安全连接
tuiredis -H 127.0.0.1 -p 6379 --ssh-host my-bastion.com --ssh-user root --ssh-key ~/.ssh/id_rsa -c

# 查看所有受支持的启动参数
tuiredis --help
```

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
