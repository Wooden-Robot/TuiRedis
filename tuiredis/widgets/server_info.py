"""Server info panel widget."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Static


class ServerInfo(Widget):
    """Displays Redis server information in a formatted panel."""

    DEFAULT_CSS = """
    ServerInfo {
        height: 1fr;
        padding: 0;
    }
    ServerInfo #si-content {
        height: 1fr;
        padding: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="si-content"):
            yield Static("Connect to see server info", id="si-text")

    def update_info(self, info: dict):
        """Update the display with server info data."""
        text_widget = self.query_one("#si-text", Static)
        sections = self._format_info(info)
        text_widget.update(sections)

    def _format_info(self, info: dict) -> str:
        """Format Redis INFO dict into a readable display."""
        lines: list[str] = []

        # Server section
        lines.append("[bold #DC382D]━━ Server ━━[/]")
        for key in ["redis_version", "redis_mode", "os", "uptime_in_days", "process_id"]:
            if key in info:
                label = key.replace("_", " ").title()
                lines.append(f"  [bold]{label}:[/] {info[key]}")

        lines.append("")
        lines.append("[bold #FF9800]━━ Memory ━━[/]")
        for key in [
            "used_memory_human",
            "used_memory_peak_human",
            "maxmemory_human",
            "mem_fragmentation_ratio",
        ]:
            if key in info:
                label = key.replace("_", " ").title()
                lines.append(f"  [bold]{label}:[/] {info[key]}")

        lines.append("")
        lines.append("[bold #2196F3]━━ Clients ━━[/]")
        for key in ["connected_clients", "blocked_clients", "tracking_clients"]:
            if key in info:
                label = key.replace("_", " ").title()
                lines.append(f"  [bold]{label}:[/] {info[key]}")

        lines.append("")
        lines.append("[bold #4CAF50]━━ Stats ━━[/]")
        for key in [
            "total_connections_received",
            "total_commands_processed",
            "instantaneous_ops_per_sec",
            "keyspace_hits",
            "keyspace_misses",
        ]:
            if key in info:
                label = key.replace("_", " ").title()
                lines.append(f"  [bold]{label}:[/] {info[key]}")

        lines.append("")
        lines.append("[bold #9C27B0]━━ Keyspace ━━[/]")
        for key, val in info.items():
            if key.startswith("db"):
                lines.append(f"  [bold]{key}:[/] {val}")

        return "\n".join(lines)
