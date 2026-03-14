<div align="center">

# TuiRedis 🔴

A beautiful, high-performance Redis Terminal UI built with Python & [Textual](https://textual.textualize.io/).

[English](README.md) | [中文说明](README_zh-CN.md)

<br>
<img src="./docs/imgs/1.png" alt="TuiRedis Main View" width="800">
<img src="./docs/imgs/2.png" alt="TuiRedis Value View" width="800">

</div>

---

### 🚀 Features
- **🔗 Connection Management** — Connect to Redis in standalone mode, through Redis Sentinel master discovery, in Redis Cluster mode, or over an SSH tunnel.
- **🧭 Multi-Sentinel Support** — Configure one or more Sentinel nodes and automatically resolve the active master.
- **🔁 Sentinel Failover Recovery** — Common read/write operations automatically reconnect and retry after Sentinel master failover, connection resets, or `READONLY` errors.
- **🔐 Safer Saved Profiles** — Passwords are not written to disk unless you explicitly opt in when saving a profile.
- **🗂️ Dynamic DB Awareness** — Standalone connections detect the server's logical database count instead of assuming `0..15`.
- **🌲 Hierarchical Key Browser** — Interactive Tree view grouping keys by `:` separator with real-time fuzzy search.
- **⏱️ TTL Expiry Indicators** — Keys color-coded by expiry: 🔴 critical (< 60s), ⏱ expiring (< 1h).
- **☑ Multi-select & Bulk Delete** — Press `Space` on any key to select, `Ctrl+D` to delete all selected keys at once.
- **📄 Advanced Value Viewer** — Native support for viewing & editing `String`, `List`, `Hash`, `Set`, and `Sorted Set`.
- **⚡ Responsive Async Loading** — Key lists, key details, server info, bulk actions, and pagination run off the UI thread, with loading indicators and stale-response protection.
- **⚡ Pagination & Elastic Loading** — Safe loading of millions of keys without blocking the TUI. Hash and Set types support cursor-based `HSCAN`/`SSCAN` pagination.
- **📋 Copy to Clipboard** — One-click copy of any String value to your system clipboard.
- **📤 Export to File** — Export any key's value to a local file (`.txt` for strings, `.json` for structured types).
- **📊 Server Info & Monitoring** — View server stats, memory footprints, connected clients, and keyspace utilization. Cluster connections show an aggregated summary in the info panel.
- **✨ CRUD Operations** — Create, Read, Update, Delete keys seamlessly.
- **🎨 Modern Dark Theme** — Redis-branded aesthetics with fluid terminal animations.
- **🛠️ IRedis Integration** — Press `Ctrl+T` to jump into an `iredis` interactive session. Press `Ctrl+Z` inside iredis to suspend it and return to TuiRedis instantly; press `Ctrl+T` again to resume the same session where you left off.

### 📦 Installation
TuiRedis is available on PyPI and can be installed using your preferred Python package manager.

**Using pipx (Recommended)**
```bash
pipx install tuiredis
```

**Using uvx / uv**
```bash
uvx tuiredis
# or
uv tool install tuiredis
```

**Using pip**
```bash
pip install tuiredis
```

**From Source**
```bash
# Clone the repository
git clone https://github.com/Wooden-Robot/tuiredis.git
cd tuiredis

# Sync dependencies using uv
uv sync

# Run the project
uv run tuiredis
```

### 💻 Usage
If you installed TuiRedis via `pipx` or `pip`, you can start it directly from the terminal by running `tuiredis`. If you cloned from the source, you should use `uv run tuiredis` instead.
```bash
# Launch TuiRedis with the Interactive Connection Dialog
tuiredis

# Fast connect via CLI arguments
tuiredis -H 127.0.0.1 -p 6379 -a mypassword -n 0 -c

# Connect through Redis Sentinel and discover the master automatically
tuiredis --sentinel --sentinel-host 127.0.0.1 --sentinel-port 26379 --sentinel-master mymaster -a mypassword -c

# Connect through multiple Redis Sentinel nodes
tuiredis --sentinel --sentinel-node 127.0.0.1:26379 --sentinel-node 127.0.0.1:26380 --sentinel-master mymaster -a mypassword -c

# Connect to a Redis Cluster entry node
tuiredis --cluster -H 127.0.0.1 -p 7000 -a mypassword -c

# Connect securely via an SSH Tunnel
tuiredis -H 127.0.0.1 -p 6379 --ssh-host my-bastion.com --ssh-user root --ssh-key ~/.ssh/id_rsa -c

# Show all available CLI options
tuiredis --help
```

### Redis Modes
- `standalone`: fully supported.
- `sentinel`: supported via master discovery; configure it in the connection dialog or with `--sentinel ...`. Multiple Sentinel nodes are supported.
- `replica`: readable, but writes may fail on read-only replicas.
- `cluster`: supported via `RedisCluster`; only `DB 0` is valid and DB switching is disabled. Key scanning works across the cluster, while server info is shown as an aggregated summary.
- `cluster + SSH tunnel`: not supported yet.
- `sentinel + SSH tunnel`: not supported yet.

### Notes
- Saved connection profiles do not persist Redis or Sentinel passwords unless `Save passwords to disk` is enabled.
- In cluster mode, raw `SELECT` commands are rejected because Redis Cluster only supports `DB 0`.
- The Server Info tab labels cluster views as aggregated summaries and Sentinel views as control-plane information.

### ⌨️ Keyboard Shortcuts
| Key | Action |
|-----|--------|
| `q` | Quit the application |
| `F5` | Refresh Key Tree & Info |
| `/` | Focus search bar |
| `n` | Create a New Key |
| `Space` | Toggle key selection (in Key Tree) |
| `Ctrl+D` | Bulk delete all selected keys |
| `Tab` | Switch between active panels |
| `Ctrl+o`| Switch Connection |
| `Ctrl+t`| Toggle IRedis session — launch, suspend (`Ctrl+Z` in iredis), and resume seamlessly |
| `Ctrl+i`| Toggle Server Info Panel |

---
*Requirements: Python >= 3.10 / Redis Server*
