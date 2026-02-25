"""Value viewer/editor widget — displays Redis values by type."""

from __future__ import annotations

import json

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, DataTable, Input, Select, Static, TextArea


class ValueViewer(Widget):
    """Displays and allows editing of Redis key values for all types."""

    DEFAULT_CSS = """
    ValueViewer {
        height: 1fr;
        padding: 0;
    }
    ValueViewer .vv-header {
        height: 3;
        padding: 0 1;
        background: $surface;
        color: $text;
    }
    ValueViewer .vv-type-badge {
        color: $accent;
        text-style: bold;
    }
    ValueViewer .vv-body {
        height: 1fr;
    }
    ValueViewer .vv-empty {
        height: 1fr;
        content-align: center middle;
        color: $text-muted;
        text-style: italic;
    }
    ValueViewer .vv-actions {
        height: 3;
        dock: bottom;
        padding: 0 1;
        align: right middle;
    }
    ValueViewer Button {
        margin: 0 1;
    }
    ValueViewer #vv-add-row {
        height: auto;
        padding: 0 1;
    }
    """

    class ValueSaved(Message):
        """Emitted when the user saves a value edit."""

        def __init__(self, key: str, value_type: str, data) -> None:
            self.key = key
            self.value_type = value_type
            self.data = data
            super().__init__()

    class MemberAdded(Message):
        """Emitted when a member is added to a collection."""

        def __init__(self, key: str, value_type: str, data) -> None:
            self.key = key
            self.value_type = value_type
            self.data = data
            super().__init__()

    class MemberDeleted(Message):
        """Emitted when a member is deleted from a collection."""

        def __init__(self, key: str, value_type: str, data) -> None:
            self.key = key
            self.value_type = value_type
            self.data = data
            super().__init__()

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._current_key: str | None = None
        self._current_type: str | None = None
        self._current_raw_data: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Select a key to view its value", classes="vv-empty", id="vv-placeholder")

    def show_empty(self):
        """Show the empty state."""
        self._current_key = None
        self._current_type = None
        self.query("*").remove()
        self.mount(
            Vertical(
                Static("Select a key to view its value", classes="vv-empty", id="vv-placeholder")
            )
        )

    async def show_value(self, key: str, value_type: str, data):
        """Display the value for a given key."""
        self._current_key = key
        self._current_type = value_type
        self._current_raw_data = data

        # Clear existing
        await self.query("*").remove()

        type_labels = {
            "string": "STRING",
            "list": "LIST",
            "hash": "HASH",
            "set": "SET",
            "zset": "ZSET",
        }

        type_colors = {
            "string": "#4CAF50",
            "list": "#2196F3",
            "hash": "#FF9800",
            "set": "#9C27B0",
            "zset": "#F44336",
        }

        type_label = type_labels.get(value_type, value_type.upper())
        type_color = type_colors.get(value_type, "#888")

        header = Static(
            f"[bold {type_color}]⬤ {type_label}[/]  [dim]{key}[/]",
            classes="vv-header",
        )

        if value_type == "string":
            body = TextArea(str(data) if data else "", id="vv-text", language=None)

            # Format Selector for strings
            format_opts = [("Raw", "raw"), ("JSON", "json")]
            format_select = Select(format_opts, value="raw", id="vv-format-select", allow_blank=False)

            actions = Horizontal(
                format_select,
                Button("💾 Save", variant="primary", id="vv-save-string"),
                classes="vv-actions",
            )
            container = Vertical(header, body, actions)

        elif value_type == "list":
            table = DataTable(id="vv-table")
            table.add_columns("Index", "Value")
            if data:
                for i, val in enumerate(data):
                    table.add_row(str(i), str(val), key=str(i))
            add_row = Horizontal(
                Input(placeholder="New value...", id="vv-add-input"),
                Button("➕ Add", variant="success", id="vv-add-list"),
                id="vv-add-row",
            )
            container = Vertical(header, table, add_row)

        elif value_type == "hash":
            table = DataTable(id="vv-table")
            table.add_columns("Field", "Value")
            if data:
                for field, val in sorted(data.items()):
                    table.add_row(str(field), str(val), key=str(field))
            add_row = Horizontal(
                Input(placeholder="Field", id="vv-add-field"),
                Input(placeholder="Value", id="vv-add-value"),
                Button("➕ Add", variant="success", id="vv-add-hash"),
                id="vv-add-row",
            )
            container = Vertical(header, table, add_row)

        elif value_type == "set":
            table = DataTable(id="vv-table")
            table.add_columns("#", "Member")
            if data:
                for i, member in enumerate(sorted(data), 1):
                    table.add_row(str(i), str(member), key=str(member))
            add_row = Horizontal(
                Input(placeholder="New member...", id="vv-add-input"),
                Button("➕ Add", variant="success", id="vv-add-set"),
                id="vv-add-row",
            )
            container = Vertical(header, table, add_row)

        elif value_type == "zset":
            table = DataTable(id="vv-table")
            table.add_columns("#", "Member", "Score")
            if data:
                for i, (member, score) in enumerate(data, 1):
                    table.add_row(str(i), str(member), str(score), key=str(member))
            add_row = Horizontal(
                Input(placeholder="Member", id="vv-add-field"),
                Input(placeholder="Score", id="vv-add-value"),
                Button("➕ Add", variant="success", id="vv-add-zset"),
                id="vv-add-row",
            )
            container = Vertical(header, table, add_row)

        else:
            container = Vertical(
                header,
                Static(f"Unsupported type: {value_type}", classes="vv-empty"),
            )

        await self.mount(container)

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle format change for strings."""
        if getattr(event.select, "id", None) == "vv-format-select" and self._current_raw_data is not None:
            textarea = self.query_one("#vv-text", TextArea)
            if event.value == "json":
                try:
                    parsed = json.loads(self._current_raw_data)
                    formatted_json = json.dumps(parsed, indent=2, ensure_ascii=False)
                    textarea.language = "json"
                    textarea.text = formatted_json
                except (ValueError, TypeError):
                    # Not valid JSON
                    textarea.language = None
                    textarea.text = str(self._current_raw_data)
                    # Keep select value to let user see it failed, or revert? We'll just display raw content
            else:
                textarea.language = None
                textarea.text = str(self._current_raw_data)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses within the viewer."""
        if not self._current_key:
            return

        btn_id = getattr(event.button, "id", None)

        if btn_id == "vv-save-string":
            textarea = self.query_one("#vv-text", TextArea)
            self.post_message(
                self.ValueSaved(self._current_key, "string", textarea.text)
            )

        elif btn_id == "vv-add-list":
            inp = self.query_one("#vv-add-input", Input)
            if inp.value.strip():
                self.post_message(
                    self.MemberAdded(self._current_key, "list", inp.value.strip())
                )
                inp.value = ""

        elif btn_id == "vv-add-hash":
            field_inp = self.query_one("#vv-add-field", Input)
            value_inp = self.query_one("#vv-add-value", Input)
            if field_inp.value.strip():
                self.post_message(
                    self.MemberAdded(
                        self._current_key,
                        "hash",
                        (field_inp.value.strip(), value_inp.value),
                    )
                )
                field_inp.value = ""
                value_inp.value = ""

        elif btn_id == "vv-add-set":
            inp = self.query_one("#vv-add-input", Input)
            if inp.value.strip():
                self.post_message(
                    self.MemberAdded(self._current_key, "set", inp.value.strip())
                )
                inp.value = ""

        elif btn_id == "vv-add-zset":
            field_inp = self.query_one("#vv-add-field", Input)
            score_inp = self.query_one("#vv-add-value", Input)
            if field_inp.value.strip():
                try:
                    score = float(score_inp.value)
                except ValueError:
                    score = 0.0
                self.post_message(
                    self.MemberAdded(
                        self._current_key,
                        "zset",
                        (field_inp.value.strip(), score),
                    )
                )
                field_inp.value = ""
                score_inp.value = ""
