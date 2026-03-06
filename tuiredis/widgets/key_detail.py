"""Key detail/metadata panel widget."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
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
    /* Shared section style for rename and TTL groups */
    KeyDetail .kd-section {
        height: auto;
        padding: 0 1 1 1;
        border-top: solid $surface-lighten-2;
    }
    KeyDetail .kd-section-label {
        color: $text-muted;
        text-style: bold;
        padding: 0;
        height: auto;
    }
    KeyDetail .kd-section Input {
        width: 100%;
        margin: 0 0 1 0;
    }
    KeyDetail .kd-section Button {
        width: auto;
        margin: 0;
    }
    KeyDetail #kd-actions {
        height: auto;
        padding: 1 1 0 1;
        border-top: solid $surface-lighten-2;
    }
    KeyDetail #kd-actions Button {
        width: 100%;
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

        container = Vertical(
            Static(info_text, id="kd-content"),
            # ── Rename section ───────────────────────────────────
            Vertical(
                Static("[bold #F5A623]✏️  Rename Key[/]", classes="kd-section-label"),
                Input(placeholder="new name", id="kd-rename-input"),
                Button("✏️ Rename", variant="warning", id="kd-rename"),
                classes="kd-section",
            ),
            # ── TTL section ──────────────────────────────────────────
            Vertical(
                Static("[bold #2196F3]⏱  Set Expiry[/]  [dim](-1 = no expiry)[/]", classes="kd-section-label"),
                Input(placeholder="seconds", id="kd-ttl-input", type="integer"),
                Button("⏱ Set TTL", variant="primary", id="kd-set-ttl"),
                classes="kd-section",
            ),
            # ── Danger zone ──────────────────────────────────────
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
        elif event.button.id == "kd-rename":
            inp = self.query_one("#kd-rename-input", Input)
            new_name = inp.value.strip()
            if not new_name:
                return
            if new_name == self._current_key:
                inp.value = ""
                return
            self.post_message(self.KeyRenamed(self._current_key, new_name))
            inp.value = ""
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
