"""Key detail/metadata panel widget."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Input, Static


class KeyDetail(Widget):
    """Shows metadata and actions for the selected key."""

    DEFAULT_CSS = """
    KeyDetail {
        height: auto;
        max-height: 100%;
        padding: 0;
    }
    KeyDetail #kd-content {
        padding: 1;
    }
    KeyDetail #kd-actions {
        padding: 0 1;
        height: auto;
    }
    KeyDetail #kd-actions Button {
        width: 100%;
        margin: 0 0 1 0;
    }
    KeyDetail #kd-ttl-row {
        height: auto;
        padding: 0 1;
    }
    KeyDetail #kd-ttl-row Input {
        width: 1fr;
    }
    KeyDetail #kd-ttl-row Button {
        width: auto;
        min-width: 8;
    }
    """

    class KeyDeleted(Message):
        def __init__(self, key: str) -> None:
            self.key = key
            super().__init__()

    class TtlSet(Message):
        def __init__(self, key: str, ttl: int) -> None:
            self.key = key
            self.ttl = ttl
            super().__init__()

    class KeyRenamed(Message):
        def __init__(self, old_key: str, new_key: str) -> None:
            self.old_key = old_key
            self.new_key = new_key
            super().__init__()

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._current_key: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("[dim italic]No key selected[/]", id="kd-content")

    async def show_detail(self, key: str, key_type: str, ttl: int, encoding: str, memory: int | None):
        """Display key metadata."""
        self._current_key = key

        await self.query("*").remove()

        ttl_display = "♾️  No expiry" if ttl == -1 else f"⏱️  {ttl}s"
        memory_display = self._format_bytes(memory) if memory else "N/A"

        type_colors = {
            "string": "#4CAF50",
            "list": "#2196F3",
            "hash": "#FF9800",
            "set": "#9C27B0",
            "zset": "#F44336",
        }
        color = type_colors.get(key_type, "#888")

        info_text = (
            f"[bold]Key Info[/]\n"
            f"[dim]{'─' * 28}[/]\n"
            f"[bold]Type:[/]     [{color}]{key_type.upper()}[/]\n"
            f"[bold]TTL:[/]      {ttl_display}\n"
            f"[bold]Encoding:[/] {encoding}\n"
            f"[bold]Memory:[/]   {memory_display}\n"
        )

        from textual.containers import Horizontal

        container = Vertical(
            Static(info_text, id="kd-content"),
            Horizontal(
                Input(placeholder="TTL (seconds)", id="kd-ttl-input", type="integer"),
                Button("Set", variant="primary", id="kd-set-ttl"),
                id="kd-ttl-row",
            ),
            Vertical(
                Button("🗑️  Delete Key", variant="error", id="kd-delete"),
                id="kd-actions",
            ),
        )
        await self.mount(container)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if not self._current_key:
            return
        if event.button.id == "kd-delete":
            self.post_message(self.KeyDeleted(self._current_key))
        elif event.button.id == "kd-set-ttl":
            inp = self.query_one("#kd-ttl-input", Input)
            try:
                ttl = int(inp.value)
            except ValueError:
                return
            self.post_message(self.TtlSet(self._current_key, ttl))

    @staticmethod
    def _format_bytes(num_bytes: int | None) -> str:
        if num_bytes is None:
            return "N/A"
        if num_bytes < 1024:
            return f"{num_bytes} B"
        elif num_bytes < 1024 * 1024:
            return f"{num_bytes / 1024:.1f} KB"
        else:
            return f"{num_bytes / (1024 * 1024):.1f} MB"
