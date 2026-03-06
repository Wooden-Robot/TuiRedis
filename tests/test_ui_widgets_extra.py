"""Additional widget-level tests for improved coverage."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

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


# ── CommandInput ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_command_input_submit_empty_does_not_add_history():
    """Submitting an empty command should not add to history."""
    app = DummyApp()
    async with app.run_test(size=(120, 40)) as pilot:
        from textual.widgets import Input

        cmd = app.query_one(CommandInput)
        inp = cmd.query_one("#cmd-input", Input)
        inp.value = ""
        await inp.action_submit()
        await pilot.pause(0.1)
        assert len(cmd._history) == 0


@pytest.mark.asyncio
async def test_command_input_history_navigation():
    """Up/down arrows should navigate command history."""
    app = DummyApp()
    async with app.run_test(size=(120, 40)) as pilot:
        from textual.widgets import Input

        cmd = app.query_one(CommandInput)
        inp = cmd.query_one("#cmd-input", Input)

        # Add two commands via submit
        inp.value = "PING"
        await inp.action_submit()
        await pilot.pause(0.05)
        inp.value = "GET foo"
        await inp.action_submit()
        await pilot.pause(0.05)

        assert len(cmd._history) == 2

        # Focus input and press up
        inp.focus()
        await pilot.press("up")
        await pilot.pause(0.05)
        assert inp.value == "GET foo"

        await pilot.press("up")
        await pilot.pause(0.05)
        assert inp.value == "PING"

        # Press down to go forward
        await pilot.press("down")
        await pilot.pause(0.05)
        assert inp.value == "GET foo"

        await pilot.press("down")
        await pilot.pause(0.05)
        assert inp.value == ""  # past end → cleared


@pytest.mark.asyncio
async def test_command_input_write_result_error():
    """write_result with error prefix should not raise."""
    app = DummyApp()
    async with app.run_test() as pilot:
        cmd = app.query_one(CommandInput)
        cmd.write_result("BADCMD", "(error) ERR syntax error")
        await pilot.pause(0.1)


@pytest.mark.asyncio
async def test_command_input_write_result_ok_and_nil():
    """write_result with OK, PONG and (nil) should render without crashing."""
    app = DummyApp()
    async with app.run_test() as pilot:
        cmd = app.query_one(CommandInput)
        cmd.write_result("PING", "PONG")
        cmd.write_result("SET x y", "OK")
        cmd.write_result("GET missing", "(nil)")
        await pilot.pause(0.1)


# ── ServerInfo ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_server_info_all_sections():
    """update_info should populate all four info sections without crashing."""
    app = DummyApp()
    async with app.run_test() as pilot:
        from textual.widgets import Static

        server_info = app.query_one(ServerInfo)
        server_info.update_info(
            {
                "redis_version": "7.0.5",
                "redis_mode": "standalone",
                "os": "Linux x86_64",
                "uptime_in_days": "10",
                "process_id": "1234",
                "used_memory_human": "2.00M",
                "used_memory_peak_human": "3.00M",
                "maxmemory_human": "0B",
                "mem_fragmentation_ratio": "1.1",
                "connected_clients": "5",
                "blocked_clients": "0",
                "tracking_clients": "0",
                "total_connections_received": "100",
                "total_commands_processed": "500",
                "instantaneous_ops_per_sec": "10",
                "keyspace_hits": "400",
                "keyspace_misses": "50",
                "db0": {"keys": 42},
            }
        )
        await pilot.pause(0.1)
        text = str(server_info.query_one("#si-text", Static).render())
        assert "7.0.5" in text


# ── ValueViewer row-select ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_value_viewer_hash_row_select_populates_inputs():
    """Clicking a hash row should populate field+value inputs and set edit mode."""
    from textual.widgets import DataTable, Input

    app = DummyApp()
    async with app.run_test(size=(120, 40)) as pilot:
        viewer = app.query_one(ValueViewer)
        await viewer.show_value("myhash", "hash", {"name": "Alice"})
        await pilot.pause(0.1)

        table = viewer.query_one("#vv-table", DataTable)
        table.move_cursor(row=0)
        table.action_select_cursor()
        await pilot.pause(0.1)

        field_val = viewer.query_one("#vv-hash-fld", Input).value
        assert field_val == "name"
        assert viewer._editing is True


@pytest.mark.asyncio
async def test_value_viewer_zset_row_select_populates_inputs():
    """Clicking a zset row should populate member+score inputs."""
    from textual.widgets import DataTable, Input

    app = DummyApp()
    async with app.run_test(size=(120, 40)) as pilot:
        viewer = app.query_one(ValueViewer)
        await viewer.show_value("myzset", "zset", [("alpha", 2.5)])
        await pilot.pause(0.1)

        table = viewer.query_one("#vv-table", DataTable)
        table.move_cursor(row=0)
        table.action_select_cursor()
        await pilot.pause(0.1)

        assert viewer.query_one("#vv-zset-mem", Input).value == "alpha"
        assert viewer.query_one("#vv-zset-score", Input).value == "2.5"
        assert viewer._editing is True


@pytest.mark.asyncio
async def test_value_viewer_set_row_select_populates_input():
    """Clicking a set row should populate the member input."""
    from textual.widgets import DataTable, Input

    app = DummyApp()
    async with app.run_test(size=(120, 40)) as pilot:
        viewer = app.query_one(ValueViewer)
        await viewer.show_value("myset", "set", {"beta"})
        await pilot.pause(0.1)

        table = viewer.query_one("#vv-table", DataTable)
        table.move_cursor(row=0)
        table.action_select_cursor()
        await pilot.pause(0.1)

        assert viewer.query_one("#vv-set-val", Input).value == "beta"


# ── ValueViewer on_input_submitted routing ────────────────────────────────────


@pytest.mark.asyncio
async def test_value_viewer_hash_field_enter_triggers_save():
    """Pressing Enter on hash field input should call _do_save_hash."""
    from textual.widgets import Input

    app = DummyApp()
    captured: list = []

    async with app.run_test(size=(120, 40)) as pilot:
        viewer = app.query_one(ValueViewer)
        await viewer.show_value("myhash", "hash", {})
        await pilot.pause(0.1)

        original_post = viewer.post_message

        def _capture(msg):
            captured.append(msg)
            return original_post(msg)

        viewer.post_message = _capture

        viewer.query_one("#vv-hash-fld", Input).value = "k"
        viewer.query_one("#vv-hash-val").text = "v"
        await viewer.query_one("#vv-hash-fld", Input).action_submit()
        await pilot.pause(0.1)

    added = [m for m in captured if isinstance(m, ValueViewer.MemberAdded)]
    assert len(added) == 1


@pytest.mark.asyncio
async def test_value_viewer_zset_score_enter_triggers_save():
    """Pressing Enter on zset score input should call _do_save_zset."""
    from textual.widgets import Input

    app = DummyApp()
    captured: list = []

    async with app.run_test(size=(120, 40)) as pilot:
        viewer = app.query_one(ValueViewer)
        await viewer.show_value("myzset", "zset", [])
        await pilot.pause(0.1)

        original_post = viewer.post_message

        def _capture(msg):
            captured.append(msg)
            return original_post(msg)

        viewer.post_message = _capture

        viewer.query_one("#vv-zset-mem", Input).value = "m"
        score_inp = viewer.query_one("#vv-zset-score", Input)
        score_inp.value = "5.0"
        await score_inp.action_submit()
        await pilot.pause(0.1)

    added = [m for m in captured if isinstance(m, ValueViewer.MemberAdded)]
    assert len(added) == 1
    assert added[0].data == ("m", 5.0)


# ── ValueViewer additional button paths ──────────────────────────────────────


@pytest.mark.asyncio
async def test_value_viewer_string_save_button():
    """Pressing the string save button emits ValueSaved."""
    from textual.widgets import Button

    app = DummyApp()
    captured: list = []

    async with app.run_test(size=(120, 40)) as pilot:
        viewer = app.query_one(ValueViewer)
        await viewer.show_value("mykey", "string", "hello")
        await pilot.pause(0.1)

        original_post = viewer.post_message

        def _capture(msg):
            captured.append(msg)
            return original_post(msg)

        viewer.post_message = _capture

        btn = viewer.query_one("#vv-save-string", Button)
        viewer.on_button_pressed(Button.Pressed(btn))
        await pilot.pause(0.1)

    saved = [m for m in captured if isinstance(m, ValueViewer.ValueSaved)]
    assert len(saved) == 1
    assert saved[0].key == "mykey"


@pytest.mark.asyncio
async def test_value_viewer_clear_hash_inputs():
    """Clear button for hash should wipe field/value inputs."""
    from textual.widgets import Button, Input

    app = DummyApp()
    async with app.run_test(size=(120, 40)) as pilot:
        viewer = app.query_one(ValueViewer)
        await viewer.show_value("myhash", "hash", {"a": "b"})
        await pilot.pause(0.1)

        viewer.query_one("#vv-hash-fld", Input).value = "a"
        viewer.query_one("#vv-hash-val").text = "b"
        viewer._editing = True

        clear_btn = viewer.query_one("#vv-clear-selection", Button)
        viewer.on_button_pressed(Button.Pressed(clear_btn))
        await pilot.pause(0.1)

        assert viewer.query_one("#vv-hash-fld", Input).value == ""
        assert not viewer._editing


@pytest.mark.asyncio
async def test_value_viewer_list_delete_by_value():
    """List delete with value but no index should emit MemberDeleted with (None, val)."""
    from textual.widgets import Button, Input

    app = DummyApp()
    captured: list = []

    async with app.run_test(size=(120, 40)) as pilot:
        viewer = app.query_one(ValueViewer)
        await viewer.show_value("mylist", "list", ["alpha"])
        await pilot.pause(0.1)

        original_post = viewer.post_message

        def _capture(msg):
            captured.append(msg)
            return original_post(msg)

        viewer.post_message = _capture

        # No index, but has value
        viewer.query_one("#vv-list-idx", Input).value = ""
        viewer.query_one("#vv-list-val", Input).value = "alpha"

        btn = viewer.query_one("#vv-delete-list", Button)
        viewer.on_button_pressed(Button.Pressed(btn))
        await pilot.pause(0.1)

    deleted = [m for m in captured if isinstance(m, ValueViewer.MemberDeleted)]
    assert len(deleted) == 1
    assert deleted[0].data == (None, "alpha")


@pytest.mark.asyncio
async def test_value_viewer_list_delete_no_input_shows_warning():
    """List delete with no index and no value should not emit MemberDeleted."""
    from textual.widgets import Button, Input

    app = DummyApp()
    captured: list = []

    async with app.run_test(size=(120, 40)) as pilot:
        viewer = app.query_one(ValueViewer)
        await viewer.show_value("mylist", "list", ["alpha"])
        await pilot.pause(0.1)

        original_post = viewer.post_message

        def _capture(msg):
            captured.append(msg)
            return original_post(msg)

        viewer.post_message = _capture

        viewer.query_one("#vv-list-idx", Input).value = ""
        viewer.query_one("#vv-list-val", Input).value = ""

        btn = viewer.query_one("#vv-delete-list", Button)
        viewer.on_button_pressed(Button.Pressed(btn))
        await pilot.pause(0.1)

    deleted = [m for m in captured if isinstance(m, ValueViewer.MemberDeleted)]
    assert len(deleted) == 0


# ── redis_client disconnect / bytes paths ─────────────────────────────────────


def test_disconnect_with_tunnel():
    """disconnect() should safely close SSH tunnel even if stop() raises."""
    from unittest.mock import MagicMock, patch

    from tuiredis.redis_client import RedisClient

    client = RedisClient.__new__(RedisClient)
    client._client = MagicMock()
    tunnel = MagicMock()
    tunnel.stop.side_effect = Exception("tunnel error")
    client._ssh_tunnel = tunnel

    client.disconnect()  # should not raise
    assert client._client is None
    assert client._ssh_tunnel is None


def test_disconnect_client_close_raises():
    """disconnect() should not raise if _client.close() raises."""
    from unittest.mock import MagicMock

    from tuiredis.redis_client import RedisClient

    client = RedisClient.__new__(RedisClient)
    mock_redis = MagicMock()
    mock_redis.close.side_effect = Exception("close failed")
    client._client = mock_redis
    client._ssh_tunnel = None

    client.disconnect()  # should not raise
    assert client._client is None


def test_execute_command_bytes():
    """execute_command should decode bytes results."""
    from unittest.mock import MagicMock, patch

    import redis

    from tuiredis.redis_client import RedisClient

    client = RedisClient.__new__(RedisClient)
    mock_redis = MagicMock()
    mock_redis.execute_command.return_value = b"hello bytes"
    client._client = mock_redis

    result = client.execute_command("SOME CMD")
    assert result == "hello bytes"
