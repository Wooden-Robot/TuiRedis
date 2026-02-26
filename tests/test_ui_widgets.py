from unittest.mock import MagicMock

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Input

from tuiredis.redis_client import RedisClient
from tuiredis.widgets.command_input import CommandInput
from tuiredis.widgets.key_detail import KeyDetail
from tuiredis.widgets.key_tree import KeyTree
from tuiredis.widgets.server_info import ServerInfo
from tuiredis.widgets.value_viewer import ValueViewer


class DummyApp(App):
    def compose(self) -> ComposeResult:
        yield ServerInfo()
        yield CommandInput()
        yield KeyTree()
        yield KeyDetail()
        yield ValueViewer()


@pytest.fixture
def mock_client():
    client = MagicMock(spec=RedisClient)
    client.connection_label = "localhost:6379"
    client.get_server_info.return_value = {
        "redis_version": "7.0.0",
        "os": "Linux",
        "used_memory_human": "1M",
        "db0": 100,
    }
    client.get_db_size.return_value = 100
    client.get_keyspace_info.return_value = {0: 100}
    return client


@pytest.mark.asyncio
async def test_server_info(mock_client):
    app = DummyApp()
    async with app.run_test() as pilot:
        server_info = app.query_one(ServerInfo)
        server_info.update_info(mock_client.get_server_info())
        await pilot.pause(0.1)
        # Check text render output
        text = str(server_info.query_one("#si-text").render())
        assert "7.0.0" in text


@pytest.mark.asyncio
async def test_command_input():
    app = DummyApp()
    async with app.run_test() as pilot:
        cmd_input = app.query_one(CommandInput)
        input_widget = cmd_input.query_one(Input)

        messages = []
        app.accept_messages = lambda msg: messages.append(msg)

        input_widget.value = "GET mykey"
        await input_widget.action_submit()
        await pilot.pause(0.1)

        assert len(cmd_input._history) == 1
        assert cmd_input._history[0] == "GET mykey"

        input_widget.focus()
        input_widget.value = ""
        await pilot.press("up")
        assert input_widget.value == "GET mykey"

        await pilot.press("escape")

        # Test writing result
        cmd_input.write_result("GET mykey", "(nil)")
        await pilot.pause(0.1)


@pytest.mark.asyncio
async def test_key_tree():
    app = DummyApp()
    async with app.run_test() as pilot:
        tree = app.query_one(KeyTree)
        tree.load_keys(
            keys=["user:1", "user:2", "config"], key_types={"user:1": "string", "user:2": "hash", "config": "list"}
        )
        await pilot.pause(0.1)

        # 'config' comes before 'user' alphabetically
        assert tree.root.children[0].label.plain == "📋 config"
        assert tree.root.children[1].label.plain == "📁 user (2)"

        # Test loading more
        tree.append_keys(keys=["user:3"], key_types={"user:3": "string"}, next_cursor=10)
        await pilot.pause(0.1)

        # Test filter
        tree.filter_keys("conf")
        await pilot.pause(0.1)
        # filtered should show only 'config' node under root. The load more node might still be there.
        children_labels = [c.label.plain for c in tree.root.children]
        assert "📋 config" in children_labels
        assert "📁 user (3)" not in children_labels


@pytest.mark.asyncio
async def test_key_detail(mock_client):
    app = DummyApp()
    async with app.run_test() as pilot:
        detail = app.query_one(KeyDetail)

        await detail.show_detail("mykey", "string", 100, "raw", 1024)
        await pilot.pause(0.1)

        text = str(detail.query_one("#kd-content").render())
        # mykey is not actually rendered in that text block, only the metadata
        assert "STRING" in text
        assert "100s" in text
        assert "1.0 KB" in text


@pytest.mark.asyncio
async def test_value_viewer_string():
    app = DummyApp()
    async with app.run_test() as pilot:
        viewer = app.query_one(ValueViewer)
        await viewer.show_value("mykey", "string", "my string value")
        await pilot.pause(0.1)


@pytest.mark.asyncio
async def test_value_viewer_json():
    app = DummyApp()
    async with app.run_test() as pilot:
        viewer = app.query_one(ValueViewer)
        await viewer.show_value("mykey", "string", '{"key": "value"}')
        await pilot.pause(0.1)


@pytest.mark.asyncio
async def test_value_viewer_list():
    app = DummyApp()
    async with app.run_test() as pilot:
        viewer = app.query_one(ValueViewer)
        await viewer.show_value("mykey", "list", ["item1", "item2"])
        await pilot.pause(0.1)


@pytest.mark.asyncio
async def test_value_viewer_hash():
    app = DummyApp()
    async with app.run_test() as pilot:
        viewer = app.query_one(ValueViewer)
        await viewer.show_value("mykey", "hash", {"f1": "v1"})
        await pilot.pause(0.1)


@pytest.mark.asyncio
async def test_value_viewer_set():
    app = DummyApp()
    async with app.run_test() as pilot:
        viewer = app.query_one(ValueViewer)
        await viewer.show_value("mykey", "set", {"member1"})
        await pilot.pause(0.1)


@pytest.mark.asyncio
async def test_value_viewer_zset():
    app = DummyApp()
    async with app.run_test() as pilot:
        viewer = app.query_one(ValueViewer)
        await viewer.show_value("mykey", "zset", [("m1", 1.0)])
        await pilot.pause(0.1)
