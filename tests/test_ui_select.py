import pytest
from textual.app import App, ComposeResult
from textual.widgets import Select


class SelectTestApp(App):
    def compose(self) -> ComposeResult:
        yield Select([("A", "0"), ("B", "1")], value="0")

    def on_mount(self):
        select = self.query_one(Select)
        select.set_options([("A (1)", "0"), ("B (2)", "1")])
        select.value = "1"


@pytest.mark.asyncio
async def test_select_widget():
    """Test standard Select widget mounting and initialization."""
    app = SelectTestApp()
    async with app.run_test():
        select = app.query_one(Select)
        assert select.value == "1"
        # Textual adds a blank choice by default to Select unless allow_blank=False
        assert len(select._options) == 3
