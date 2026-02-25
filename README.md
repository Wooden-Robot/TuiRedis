<div align="center">

# TuiRedis 🔴

A beautiful, high-performance Redis Terminal UI built with Python & [Textual](https://textual.textualize.io/).

[English](README.md) | [中文说明](README_zh-CN.md)

</div>

---

### 🚀 Features
- **🔗 Connection Management** — Connect to any Redis instance (supports Password / DB Indexing).
- **🌲 Hierarchical Key Browser** — Interactive Tree view grouping keys by `:` separator with real-time fuzzy search.
- **📄 Advanced Value Viewer** — Native support for viewing & editing `String`, `List`, `Hash`, `Set`, and `Sorted Set`.
- **⚡ Pagination & Elastic Loading** — Safe loading of millions of keys without blocking the TUI.
- **⌨️ Command Console** — Execute raw Redis commands directly within the app.
- **📊 Server Info & Monitoring** — View exact server stats, memory footprints, connected clients, and keyspace utilization.
- **✨ CRUD Operations** — Create, Read, Update, Delete keys seamlessly.
- **⏱️ TTL Management** — View and set key expiration intuitively.
- **🎨 Modern Dark Theme** — Redis-branded aesthetics with fluid terminal animations.
- **🛠️ IRedis Integration** — One-click launch into `iredis` terminal via internal bindings.

### 📦 Installation
TRedis is built using modern Python tooling (`uv`).

```bash
# Clone the repository
git clone https://github.com/Wooden-Robot/tuiredis.git
cd tuiredis

# Sync dependencies using uv
uv sync
```

### 💻 Usage
```bash
# Launch TRedis with the Interactive Connection Dialog
uv run tuiredis

# Fast connect via CLI arguments
uv run tuiredis -H 127.0.0.1 -p 6379 -n 0 -c

# Connect securely via an SSH Tunnel
uv run tuiredis -H 127.0.0.1 -p 6379 --ssh-host my-bastion.com --ssh-user root -c

# Show all available CLI options
uv run tuiredis --help
```

### ⌨️ Keyboard Shortcuts
| Key | Action |
|-----|--------|
| `q` | Quit the application |
| `F5` | Refresh Key Tree & Info |
| `/` | Focus search bar |
| `n` | Create a New Key |
| `Tab` | Switch between active panels |
| `Ctrl+t`| Launch IRedis Terminal (`uv` will prompt to install if missing) |
| `Ctrl+i`| Toggle Server Info Panel |

---
*Requirements: Python >= 3.10 / Redis Server*
