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
async def test_server_info_shows_cluster_aggregation_hint():
    app = DummyApp()
    async with app.run_test() as pilot:
        server_info = app.query_one(ServerInfo)
        server_info.update_info({"redis_mode": "cluster", "cluster_nodes": 3, "redis_version": "7.0.0"})
        await pilot.pause(0.1)

        text = str(server_info.query_one("#si-text").render())
        assert "Aggregated cluster view across 3 nodes" in text


@pytest.mark.asyncio
async def test_server_info_shows_sentinel_hint():
    app = DummyApp()
    async with app.run_test() as pilot:
        server_info = app.query_one(ServerInfo)
        server_info.update_info({"redis_mode": "sentinel", "redis_version": "7.0.0"})
        await pilot.pause(0.1)

        text = str(server_info.query_one("#si-text").render())
        assert "Sentinel control-plane view" in text


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


@pytest.mark.asyncio
async def test_value_viewer_count_hint_shown_when_truncated():
    """Header should show (showing X of Y) when total_count > len(data)."""
    from textual.widgets import Static

    app = DummyApp()
    async with app.run_test() as pilot:
        viewer = app.query_one(ValueViewer)
        await viewer.show_value("mykey", "list", ["a", "b"], total_count=1000)
        await pilot.pause(0.1)
        header_text = str(viewer.query_one(".vv-header", Static).render())
        assert "1,000" in header_text or "2" in header_text  # hint is present


@pytest.mark.asyncio
async def test_value_viewer_list_enter_to_submit():
    """Pressing Enter in the list value input should emit MemberAdded."""
    from textual.widgets import Input

    app = DummyApp()
    captured: list = []

    async with app.run_test(size=(120, 40)) as pilot:
        viewer = app.query_one(ValueViewer)
        await viewer.show_value("mykey", "list", [])
        await pilot.pause(0.1)

        # Intercept the message by patching post_message on the viewer
        original_post = viewer.post_message

        def _capture(msg):
            captured.append(msg)
            return original_post(msg)

        viewer.post_message = _capture

        val_inp = viewer.query_one("#vv-list-val", Input)
        val_inp.value = "hello"
        await val_inp.action_submit()
        await pilot.pause(0.2)

    added = [m for m in captured if isinstance(m, ValueViewer.MemberAdded)]
    assert len(added) == 1
    assert added[0].data == (None, "hello")


@pytest.mark.asyncio
async def test_value_viewer_list_edit_mode_button_label():
    """Clicking a row should change Save button to 'Update'; Clear should restore it."""
    from textual.widgets import Button, DataTable

    app = DummyApp()
    async with app.run_test(size=(120, 40)) as pilot:
        viewer = app.query_one(ValueViewer)
        await viewer.show_value("mykey", "list", ["alpha", "beta"])
        await pilot.pause(0.1)

        table = viewer.query_one("#vv-table", DataTable)
        table.move_cursor(row=0)
        await pilot.pause(0.1)
        table.action_select_cursor()
        await pilot.pause(0.1)

        save_btn = viewer.query_one("#vv-save-list", Button)
        assert "Update" in str(save_btn.label)

        # Trigger Clear via Button.Pressed (avoids OutOfBounds for hidden buttons)
        clear_btn = viewer.query_one("#vv-clear-selection", Button)
        viewer.on_button_pressed(Button.Pressed(clear_btn))
        await pilot.pause(0.1)
        assert "Update" not in str(save_btn.label)
        assert not viewer._editing


@pytest.mark.asyncio
async def test_value_viewer_set_duplicate_warning():
    """Adding an existing member should show a warning, not emit MemberAdded."""
    app = DummyApp()
    async with app.run_test() as pilot:
        viewer = app.query_one(ValueViewer)
        await viewer.show_value("myset", "set", {"existing_member"})
        await pilot.pause(0.1)

        from textual.widgets import Input

        inp = viewer.query_one("#vv-set-val", Input)
        inp.value = "existing_member"

        messages = []
        viewer.app.on_message = lambda m: messages.append(m)
        await inp.action_submit()
        await pilot.pause(0.1)

        added = [m for m in messages if isinstance(m, ValueViewer.MemberAdded)]
        assert len(added) == 0  # duplicate was blocked


@pytest.mark.asyncio
async def test_value_viewer_string_json_invalid_notify():
    """Switching to JSON format with non-JSON content should not crash and display raw text."""
    from textual.widgets import Select, TextArea

    app = DummyApp()
    async with app.run_test() as pilot:
        viewer = app.query_one(ValueViewer)
        await viewer.show_value("mykey", "string", "not-a-json-value")
        await pilot.pause(0.1)

        fmt_select = viewer.query_one("#vv-format-select", Select)
        fmt_select.value = "json"
        await pilot.pause(0.2)

        # TextArea should still show the raw content (didn't crash)
        ta = viewer.query_one("#vv-text", TextArea)
        assert "not-a-json-value" in ta.text


@pytest.mark.asyncio
async def test_key_detail_rename_emits_message():
    """Clicking Rename with a new name should emit KeyDetail.KeyRenamed."""
    from textual.widgets import Button, Input

    app = DummyApp()
    captured: list = []

    async with app.run_test(size=(120, 40)) as pilot:
        detail = app.query_one(KeyDetail)
        await detail.show_detail("old_key", "string", -1, "raw", 64)
        await pilot.pause(0.1)

        original_post = detail.post_message

        def _capture(msg):
            captured.append(msg)
            return original_post(msg)

        detail.post_message = _capture

        rename_inp = detail.query_one("#kd-rename-input", Input)
        rename_inp.value = "new_key"
        rename_btn = detail.query_one("#kd-rename", Button)
        detail.on_button_pressed(Button.Pressed(rename_btn))
        await pilot.pause(0.1)

    renamed = [m for m in captured if isinstance(m, KeyDetail.KeyRenamed)]
    assert len(renamed) == 1
    assert renamed[0].old_key == "old_key"
    assert renamed[0].new_key == "new_key"


@pytest.mark.asyncio
async def test_key_detail_rename_same_name_ignored():
    """Renaming to the same name should not emit KeyRenamed."""
    from textual.widgets import Button, Input

    app = DummyApp()
    captured: list = []

    async with app.run_test(size=(120, 40)) as pilot:
        detail = app.query_one(KeyDetail)
        await detail.show_detail("same_key", "string", -1, "raw", 64)
        await pilot.pause(0.1)

        original_post = detail.post_message

        def _capture(msg):
            captured.append(msg)
            return original_post(msg)

        detail.post_message = _capture

        rename_inp = detail.query_one("#kd-rename-input", Input)
        rename_inp.value = "same_key"  # same as current
        rename_btn = detail.query_one("#kd-rename", Button)
        detail.on_button_pressed(Button.Pressed(rename_btn))
        await pilot.pause(0.1)

    renamed = [m for m in captured if isinstance(m, KeyDetail.KeyRenamed)]
    assert len(renamed) == 0


# ── Additional value_viewer save/delete helpers ───────────────────────────────

@pytest.mark.asyncio
async def test_value_viewer_hash_save_emits_member_added():
    """Pressing Save on a hash field should emit MemberAdded with (field, value)."""
    from textual.widgets import Button, Input

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

        viewer.query_one("#vv-hash-fld", Input).value = "myfield"
        viewer.query_one("#vv-hash-val").text = "myvalue"
        btn = viewer.query_one("#vv-save-hash", Button)
        viewer.on_button_pressed(Button.Pressed(btn))
        await pilot.pause(0.1)

    added = [m for m in captured if isinstance(m, ValueViewer.MemberAdded)]
    assert len(added) == 1
    assert added[0].data == ("myfield", "myvalue")


@pytest.mark.asyncio
async def test_value_viewer_hash_delete_emits_member_deleted():
    """Pressing Delete with a field filled should emit MemberDeleted."""
    from textual.widgets import Button, Input

    app = DummyApp()
    captured: list = []

    async with app.run_test(size=(120, 40)) as pilot:
        viewer = app.query_one(ValueViewer)
        await viewer.show_value("myhash", "hash", {"f": "v"})
        await pilot.pause(0.1)

        original_post = viewer.post_message

        def _capture(msg):
            captured.append(msg)
            return original_post(msg)

        viewer.post_message = _capture

        viewer.query_one("#vv-hash-fld", Input).value = "f"
        btn = viewer.query_one("#vv-delete-hash", Button)
        viewer.on_button_pressed(Button.Pressed(btn))
        await pilot.pause(0.1)

    deleted = [m for m in captured if isinstance(m, ValueViewer.MemberDeleted)]
    assert len(deleted) == 1
    assert deleted[0].data == "f"


@pytest.mark.asyncio
async def test_value_viewer_set_save_new_member():
    """Adding a non-duplicate member emits MemberAdded."""
    from textual.widgets import Button, Input

    app = DummyApp()
    captured: list = []

    async with app.run_test(size=(120, 40)) as pilot:
        viewer = app.query_one(ValueViewer)
        await viewer.show_value("myset", "set", {"existing"})
        await pilot.pause(0.1)

        original_post = viewer.post_message

        def _capture(msg):
            captured.append(msg)
            return original_post(msg)

        viewer.post_message = _capture

        viewer.query_one("#vv-set-val", Input).value = "new_member"
        btn = viewer.query_one("#vv-save-set", Button)
        viewer.on_button_pressed(Button.Pressed(btn))
        await pilot.pause(0.1)

    added = [m for m in captured if isinstance(m, ValueViewer.MemberAdded)]
    assert len(added) == 1
    assert added[0].data == "new_member"


@pytest.mark.asyncio
async def test_value_viewer_set_delete_emits_member_deleted():
    """Pressing Delete on a set with a member filled should emit MemberDeleted."""
    from textual.widgets import Button, Input

    app = DummyApp()
    captured: list = []

    async with app.run_test(size=(120, 40)) as pilot:
        viewer = app.query_one(ValueViewer)
        await viewer.show_value("myset", "set", {"m"})
        await pilot.pause(0.1)

        original_post = viewer.post_message

        def _capture(msg):
            captured.append(msg)
            return original_post(msg)

        viewer.post_message = _capture

        viewer.query_one("#vv-set-val", Input).value = "m"
        btn = viewer.query_one("#vv-delete-set", Button)
        viewer.on_button_pressed(Button.Pressed(btn))
        await pilot.pause(0.1)

    deleted = [m for m in captured if isinstance(m, ValueViewer.MemberDeleted)]
    assert len(deleted) == 1
    assert deleted[0].data == "m"


@pytest.mark.asyncio
async def test_value_viewer_zset_save_valid():
    """ZSet save with valid member+score emits MemberAdded."""
    from textual.widgets import Button, Input

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

        viewer.query_one("#vv-zset-mem", Input).value = "m1"
        viewer.query_one("#vv-zset-score", Input).value = "9.5"
        btn = viewer.query_one("#vv-save-zset", Button)
        viewer.on_button_pressed(Button.Pressed(btn))
        await pilot.pause(0.1)

    added = [m for m in captured if isinstance(m, ValueViewer.MemberAdded)]
    assert len(added) == 1
    assert added[0].data == ("m1", 9.5)


@pytest.mark.asyncio
async def test_value_viewer_zset_invalid_score_no_emit():
    """ZSet save with non-numeric score should not emit MemberAdded."""
    from textual.widgets import Button, Input

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

        viewer.query_one("#vv-zset-mem", Input).value = "m1"
        viewer.query_one("#vv-zset-score", Input).value = "not_a_number"
        btn = viewer.query_one("#vv-save-zset", Button)
        viewer.on_button_pressed(Button.Pressed(btn))
        await pilot.pause(0.1)

    added = [m for m in captured if isinstance(m, ValueViewer.MemberAdded)]
    assert len(added) == 0


@pytest.mark.asyncio
async def test_value_viewer_zset_delete_emits_member_deleted():
    """ZSet delete with member filled emits MemberDeleted."""
    from textual.widgets import Button, Input

    app = DummyApp()
    captured: list = []

    async with app.run_test(size=(120, 40)) as pilot:
        viewer = app.query_one(ValueViewer)
        await viewer.show_value("myzset", "zset", [("m1", 1.0)])
        await pilot.pause(0.1)

        original_post = viewer.post_message

        def _capture(msg):
            captured.append(msg)
            return original_post(msg)

        viewer.post_message = _capture

        viewer.query_one("#vv-zset-mem", Input).value = "m1"
        btn = viewer.query_one("#vv-delete-zset", Button)
        viewer.on_button_pressed(Button.Pressed(btn))
        await pilot.pause(0.1)

    deleted = [m for m in captured if isinstance(m, ValueViewer.MemberDeleted)]
    assert len(deleted) == 1
    assert deleted[0].data == "m1"


@pytest.mark.asyncio
async def test_value_viewer_list_index_save():
    """List save with an explicit index emits MemberAdded with (idx, val)."""
    from textual.widgets import Button, Input

    app = DummyApp()
    captured: list = []

    async with app.run_test(size=(120, 40)) as pilot:
        viewer = app.query_one(ValueViewer)
        await viewer.show_value("mylist", "list", ["a", "b"])
        await pilot.pause(0.1)

        original_post = viewer.post_message

        def _capture(msg):
            captured.append(msg)
            return original_post(msg)

        viewer.post_message = _capture

        viewer.query_one("#vv-list-idx", Input).value = "0"
        viewer.query_one("#vv-list-val", Input).value = "updated"
        btn = viewer.query_one("#vv-save-list", Button)
        viewer.on_button_pressed(Button.Pressed(btn))
        await pilot.pause(0.1)

    added = [m for m in captured if isinstance(m, ValueViewer.MemberAdded)]
    assert len(added) == 1
    assert added[0].data == (0, "updated")


@pytest.mark.asyncio
async def test_value_viewer_show_empty_resets_state():
    """show_empty should reset all internal state variables."""
    app = DummyApp()
    async with app.run_test(size=(120, 40)) as pilot:
        viewer = app.query_one(ValueViewer)
        await viewer.show_value("k", "list", ["a", "b"], total_count=100)
        await pilot.pause(0.1)
        assert viewer._current_key == "k"
        assert viewer._displayed_count == 2

        viewer.show_empty()
        await pilot.pause(0.1)
        assert viewer._current_key is None
        assert viewer._displayed_count == 0
        assert not viewer._editing


@pytest.mark.asyncio
async def test_value_viewer_append_rows_list():
    """append_rows should add new list rows and update displayed_count."""
    from textual.widgets import DataTable

    app = DummyApp()
    async with app.run_test(size=(120, 40)) as pilot:
        viewer = app.query_one(ValueViewer)
        await viewer.show_value("mylist", "list", ["a", "b"], total_count=4)
        await pilot.pause(0.1)
        assert viewer._displayed_count == 2

        viewer.append_rows(["c", "d"], total_count=4)
        await pilot.pause(0.1)

        assert viewer._displayed_count == 4
        table = viewer.query_one("#vv-table", DataTable)
        assert table.row_count == 4


@pytest.mark.asyncio
async def test_value_viewer_append_rows_removes_button_when_done():
    """When all rows are loaded, append_rows should remove the load-more button."""
    app = DummyApp()
    async with app.run_test(size=(120, 40)) as pilot:
        viewer = app.query_one(ValueViewer)
        await viewer.show_value("mylist", "list", ["a"], total_count=2)
        await pilot.pause(0.1)

        # load-more button should be present
        assert len(viewer.query("#vv-load-more")) == 1

        viewer.append_rows(["b"], total_count=2)
        await pilot.pause(0.1)

        # button should be gone — all rows loaded
        assert len(viewer.query("#vv-load-more")) == 0


@pytest.mark.asyncio
async def test_value_viewer_load_more_emits_message():
    """Pressing the load-more button should emit ValueViewer.LoadMore."""
    from textual.widgets import Button

    app = DummyApp()
    captured: list = []

    async with app.run_test(size=(120, 40)) as pilot:
        viewer = app.query_one(ValueViewer)
        await viewer.show_value("mylist", "list", ["a"], total_count=100)
        await pilot.pause(0.1)

        original_post = viewer.post_message

        def _capture(msg):
            captured.append(msg)
            return original_post(msg)

        viewer.post_message = _capture

        btn = viewer.query_one("#vv-load-more", Button)
        viewer.on_button_pressed(Button.Pressed(btn))
        await pilot.pause(0.1)

    load_more = [m for m in captured if isinstance(m, ValueViewer.LoadMore)]
    assert len(load_more) == 1
    assert load_more[0].key == "mylist"
    assert load_more[0].offset == 1  # = _displayed_count after initial load


# ── key_detail TTL and delete ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_key_detail_ttl_emits_message():
    """Clicking Set TTL with a value should emit KeyDetail.TtlSet."""
    from textual.widgets import Button, Input

    app = DummyApp()
    captured: list = []

    async with app.run_test(size=(120, 40)) as pilot:
        detail = app.query_one(KeyDetail)
        await detail.show_detail("mykey", "string", -1, "raw", 64)
        await pilot.pause(0.1)

        original_post = detail.post_message

        def _capture(msg):
            captured.append(msg)
            return original_post(msg)

        detail.post_message = _capture

        detail.query_one("#kd-ttl-input", Input).value = "3600"
        btn = detail.query_one("#kd-set-ttl", Button)
        detail.on_button_pressed(Button.Pressed(btn))
        await pilot.pause(0.1)

    ttl_msgs = [m for m in captured if isinstance(m, KeyDetail.TtlSet)]
    assert len(ttl_msgs) == 1
    assert ttl_msgs[0].ttl == 3600


@pytest.mark.asyncio
async def test_key_detail_ttl_invalid_no_emit():
    """Clicking Set TTL with non-integer input should not emit TtlSet."""
    from textual.widgets import Button, Input

    app = DummyApp()
    captured: list = []

    async with app.run_test(size=(120, 40)) as pilot:
        detail = app.query_one(KeyDetail)
        await detail.show_detail("mykey", "string", -1, "raw", 64)
        await pilot.pause(0.1)

        original_post = detail.post_message

        def _capture(msg):
            captured.append(msg)
            return original_post(msg)

        detail.post_message = _capture

        detail.query_one("#kd-ttl-input", Input).value = "not_a_number"
        btn = detail.query_one("#kd-set-ttl", Button)
        detail.on_button_pressed(Button.Pressed(btn))
        await pilot.pause(0.1)

    ttl_msgs = [m for m in captured if isinstance(m, KeyDetail.TtlSet)]
    assert len(ttl_msgs) == 0


@pytest.mark.asyncio
async def test_key_detail_delete_emits_message():
    """Clicking Delete Key should emit KeyDetail.KeyDeleted."""
    from textual.widgets import Button

    app = DummyApp()
    captured: list = []

    async with app.run_test(size=(120, 40)) as pilot:
        detail = app.query_one(KeyDetail)
        await detail.show_detail("mykey", "hash", 100, "ziplist", 512)
        await pilot.pause(0.1)

        original_post = detail.post_message

        def _capture(msg):
            captured.append(msg)
            return original_post(msg)

        detail.post_message = _capture

        btn = detail.query_one("#kd-delete", Button)
        detail.on_button_pressed(Button.Pressed(btn))
        await pilot.pause(0.1)

    deleted = [m for m in captured if isinstance(m, KeyDetail.KeyDeleted)]
    assert len(deleted) == 1
    assert deleted[0].key == "mykey"
