"""Command input/console widget for executing raw Redis commands."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input, RichLog


class CommandInput(Widget):
    """A command input with history and output display."""

    DEFAULT_CSS = """
    CommandInput {
        height: 100%;
        padding: 0;
    }
    CommandInput #cmd-output {
        height: 1fr;
        border: tall $surface-lighten-2;
        background: $surface-darken-1;
        scrollbar-size: 1 1;
    }
    CommandInput #cmd-input {
        dock: bottom;
        margin: 0;
    }
    """

    class CommandSubmitted(Message):
        """Emitted when the user submits a Redis command."""

        def __init__(self, command: str) -> None:
            self.command = command
            super().__init__()

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._history: list[str] = []
        self._history_index: int = -1

    def compose(self) -> ComposeResult:
        with Vertical():
            yield RichLog(id="cmd-output", highlight=True, markup=True)
            yield Input(
                placeholder="Enter Redis command (e.g. PING, SET foo bar)...",
                id="cmd-input",
            )

    def on_mount(self) -> None:
        output = self.query_one("#cmd-output", RichLog)
        output.write("[bold #DC382D]TRedis Console[/] — Type Redis commands below")
        output.write("[dim]─" * 50 + "[/]")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "cmd-input":
            return
        command = event.value.strip()
        if not command:
            return
        self._history.append(command)
        self._history_index = -1
        event.input.value = ""
        self.post_message(self.CommandSubmitted(command))

    def write_result(self, command: str, result: str):
        """Write a command and its result to the output log."""
        output = self.query_one("#cmd-output", RichLog)
        output.write(f"[bold #DC382D]>[/] [bold]{command}[/]")
        # Color the output based on content
        if result.startswith("(error)"):
            output.write(f"[red]{result}[/]")
        elif result == "OK" or result == "PONG":
            output.write(f"[green]{result}[/]")
        elif result == "(nil)":
            output.write(f"[dim italic]{result}[/]")
        else:
            output.write(result)
        output.write("")

    def on_key(self, event) -> None:
        """Handle up/down arrow for command history."""
        input_widget = self.query_one("#cmd-input", Input)
        if not input_widget.has_focus:
            return

        if event.key == "up" and self._history:
            if self._history_index == -1:
                self._history_index = len(self._history) - 1
            elif self._history_index > 0:
                self._history_index -= 1
            input_widget.value = self._history[self._history_index]
            event.prevent_default()
        elif event.key == "down" and self._history:
            if self._history_index >= 0:
                self._history_index += 1
                if self._history_index >= len(self._history):
                    self._history_index = -1
                    input_widget.value = ""
                else:
                    input_widget.value = self._history[self._history_index]
            event.prevent_default()
