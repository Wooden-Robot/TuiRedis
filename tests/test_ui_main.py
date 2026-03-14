import asyncio
from unittest.mock import MagicMock, patch

import pytest
from textual.widgets import Input, Select

from tuiredis.app import TRedisApp
from tuiredis.redis_client import RedisClient
from tuiredis.screens.main import MainScreen
from tuiredis.widgets.key_detail import KeyDetail
from tuiredis.widgets.key_tree import KeyTree
from tuiredis.widgets.value_viewer import ValueViewer


@pytest.fixture
def mock_redis_client():
    client = MagicMock()
    client.connection_label = "mock_host:6379"
    client.use_cluster = False
    client.use_sentinel = False
    client.get_server_info.return_value = {"redis_version": "7.0.0", "db0": 10}
    client.db = 0
    client.password = None
    client.get_db_size.return_value = 10
    client.get_keyspace_info.return_value = {0: 10, 1: 5}
    client.get_database_count.return_value = 16
    client.scan_keys_paginated.return_value = (0, ["user:1", "user:2"])
    client.get_types.return_value = {"user:1": "string", "user:2": "hash"}
    client.get_type.return_value = "string"
    client.get_ttl.return_value = -1
    client.get_encoding.return_value = "raw"
    client.get_memory_usage.return_value = 128
    client.get_string.return_value = "mock_value"
    client.get_set.return_value = {"a", "b"}
    client.get_list.return_value = ["1", "2"]
    client.get_hash.return_value = {"f": "v"}
    client.get_zset.return_value = [("z1", 1.0)]
    client.get_list_count.return_value = 2
    client.get_hash_count.return_value = 1
    client.get_set_count.return_value = 2
    client.get_zset_count.return_value = 1
    client.get_ttls.return_value = {}  # no expiry data by default
    client.scan_hash.return_value = (0, {})
    client.scan_set.return_value = (0, [])
    return client


@pytest.mark.asyncio
async def test_app_auto_connect(mock_redis_client):
    """Test auto-connect bypassing the connect screen."""
    with patch.object(RedisClient, "connect", return_value=(True, "")):
        with (
            patch.object(RedisClient, "get_server_info", mock_redis_client.get_server_info),
            patch.object(RedisClient, "get_keyspace_info", mock_redis_client.get_keyspace_info),
            patch.object(RedisClient, "scan_keys_paginated", mock_redis_client.scan_keys_paginated),
            patch.object(RedisClient, "get_types", mock_redis_client.get_types),
        ):
            app = TRedisApp(auto_connect=True)
            async with app.run_test(size=(120, 40)) as pilot:
                assert isinstance(app.screen, MainScreen)
                await pilot.pause(0.1)

                # Check if tree is populated
                tree = app.screen.query_one(KeyTree)
                assert len(tree.root.children) > 0


@pytest.mark.asyncio
async def test_main_screen_interactions(mock_redis_client):
    app = TRedisApp()
    # Inject our mock client directly
    app.redis_client = mock_redis_client
    app.redis_client.is_connected = True

    async with app.run_test(size=(120, 40)) as pilot:
        # Push main screen manually
        app.push_screen("main")
        await pilot.pause(0.1)

        main_screen = app.screen
        assert isinstance(main_screen, MainScreen)

        # Test switching DB
        db_select = main_screen.query_one("#db-select", Select)
        db_select.value = "1"
        await pilot.pause(0.1)
        mock_redis_client.switch_db.assert_called_with(1)

        # Test key search filter
        search_input = main_screen.query_one("#search-box", Input)
        search_input.value = "user"
        await pilot.pause(0.1)
        tree = main_screen.query_one(KeyTree)
        assert tree._filter == "user"

        # Test selecting a key from tree
        tree.post_message(KeyTree.KeySelected("user:1"))
        await pilot.pause(0.1)

        mock_redis_client.get_type.assert_called_with("user:1")
        mock_redis_client.get_string.assert_called_with("user:1")

        # Test Key Deletion flow
        detail = main_screen.query_one(KeyDetail)
        detail.post_message(KeyDetail.KeyDeleted("user:1"))
        await pilot.pause(0.1)
        mock_redis_client.delete_key.assert_called_with("user:1")

        # Test Key TTL Set flow
        detail.post_message(KeyDetail.TtlSet("user:1", 3600))
        await pilot.pause(0.1)
        mock_redis_client.set_ttl.assert_called_with("user:1", 3600)


@pytest.mark.asyncio
async def test_main_screen_db_switch_failure_keeps_original_selection(mock_redis_client):
    mock_redis_client.db = 0
    mock_redis_client.switch_db.return_value = False

    app = TRedisApp()
    app.redis_client = mock_redis_client
    app.redis_client.is_connected = True

    async with app.run_test(size=(120, 40)) as pilot:
        app.push_screen("main")
        await pilot.pause(0.1)

        main_screen = app.screen
        db_select = main_screen.query_one("#db-select", Select)
        db_select.value = "1"
        await pilot.pause(0.1)

        mock_redis_client.switch_db.assert_called_with(1)
        assert db_select.value == "0"


@pytest.mark.asyncio
async def test_main_screen_open_iredis_reports_missing_binary(mock_redis_client):
    app = TRedisApp()
    app.redis_client = mock_redis_client
    app.redis_client.is_connected = True

    async with app.run_test(size=(120, 40)) as pilot:
        app.push_screen("main")
        await pilot.pause(0.1)

        main_screen = app.screen
        with patch("tuiredis.screens.main.os.path.exists", return_value=False):
            main_screen.action_open_iredis()
        await pilot.pause(0.1)

        assert main_screen._iredis_proc is None


@pytest.mark.asyncio
async def test_main_screen_db_options_expand_to_server_database_count(mock_redis_client):
    mock_redis_client.db = 20
    mock_redis_client.get_database_count.return_value = 32
    mock_redis_client.get_keyspace_info.return_value = {0: 10, 20: 3, 31: 1}

    app = TRedisApp()
    app.redis_client = mock_redis_client
    app.redis_client.is_connected = True

    async with app.run_test(size=(120, 40)) as pilot:
        app.push_screen("main")
        await pilot.pause(0.1)

        main_screen = app.screen
        db_select = main_screen.query_one("#db-select", Select)
        assert db_select.value == "20"
        assert len(db_select._options) == 32


@pytest.mark.asyncio
async def test_main_screen_cluster_mode_disables_db_switch(mock_redis_client):
    mock_redis_client.get_server_info.return_value = {"redis_version": "7.0.0", "redis_mode": "cluster"}

    app = TRedisApp()
    app.redis_client = mock_redis_client
    app.redis_client.is_connected = True

    async with app.run_test(size=(120, 40)) as pilot:
        app.push_screen("main")
        await pilot.pause(0.2)

        main_screen = app.screen
        db_select = main_screen.query_one("#db-select", Select)
        assert db_select.disabled is True


@pytest.mark.asyncio
async def test_main_screen_cluster_connection_starts_with_single_db_option(mock_redis_client):
    mock_redis_client.use_cluster = True
    mock_redis_client.get_database_count.return_value = 1
    mock_redis_client.get_server_info.return_value = {"redis_version": "7.0.0", "redis_mode": "cluster"}

    app = TRedisApp()
    app.redis_client = mock_redis_client
    app.redis_client.is_connected = True

    async with app.run_test(size=(120, 40)) as pilot:
        app.push_screen("main")
        await pilot.pause(0.05)

        main_screen = app.screen
        db_select = main_screen.query_one("#db-select", Select)
        assert db_select.disabled is True
        assert db_select.value == "0"
        assert len(db_select._options) == 1


@pytest.mark.asyncio
async def test_main_screen_sentinel_mode_disables_browsing(mock_redis_client):
    mock_redis_client.get_server_info.return_value = {"redis_version": "7.0.0", "redis_mode": "sentinel"}
    mock_redis_client.scan_keys_paginated.side_effect = AssertionError("scan should not run in sentinel mode")

    app = TRedisApp()
    app.redis_client = mock_redis_client
    app.redis_client.is_connected = True

    async with app.run_test(size=(120, 40)) as pilot:
        app.push_screen("main")
        await pilot.pause(0.2)

        main_screen = app.screen
        db_select = main_screen.query_one("#db-select", Select)
        tree = main_screen.query_one(KeyTree)
        viewer = main_screen.query_one(ValueViewer)

        assert db_select.disabled is True
        assert len(tree.root.children) == 0
        assert viewer._current_key is None


@pytest.mark.asyncio
async def test_main_screen_value_viewer_events(mock_redis_client):
    app = TRedisApp()
    app.redis_client = mock_redis_client
    app.redis_client.is_connected = True

    async with app.run_test(size=(120, 40)) as pilot:
        app.push_screen("main")
        await pilot.pause(0.2)
        main_screen = app.screen

        viewer = main_screen.query_one(ValueViewer)

        # Test ValueSaved event (String)
        viewer.post_message(ValueViewer.ValueSaved("mykey", "string", "new_val"))
        await pilot.pause(0.1)
        mock_redis_client.set_string.assert_called()

        # Test MemberAdded (Hash field)
        viewer.post_message(ValueViewer.MemberAdded("myhash", "hash", ("field", "new_val_h")))
        await pilot.pause(0.1)
        mock_redis_client.hash_set.assert_called_with("myhash", "field", "new_val_h")

        # Test MemberAdded (List) — data is (idx, val) tuple; None idx means append
        viewer.post_message(ValueViewer.MemberAdded("mylist", "list", (None, "new_item")))
        await pilot.pause(0.1)
        mock_redis_client.list_push.assert_called_with("mylist", "new_item")

        # Test MemberAdded (Set)
        viewer.post_message(ValueViewer.MemberAdded("myset", "set", "new_member"))
        await pilot.pause(0.1)
        mock_redis_client.set_add.assert_called_with("myset", "new_member")

        # Test MemberDeleted (List) — by index: sends (idx, None)
        viewer.post_message(ValueViewer.MemberDeleted("mylist", "list", (1, None)))
        await pilot.pause(0.1)
        mock_redis_client.list_delete_by_index.assert_called_with("mylist", 1)

        # Test MemberDeleted (List) — by value fallback: sends (None, val)
        viewer.post_message(ValueViewer.MemberDeleted("mylist", "list", (None, "old_item")))
        await pilot.pause(0.1)
        mock_redis_client.list_remove.assert_called_with("mylist", "old_item", 1)


@pytest.mark.asyncio
async def test_main_screen_stale_key_selection_does_not_override_latest(mock_redis_client):
    app = TRedisApp()
    app.redis_client = mock_redis_client
    app.redis_client.is_connected = True

    slow_request_gate = asyncio.Event()

    async def fake_to_thread(func, *args, **kwargs):
        if getattr(func, "__name__", "") == "_fetch_key_details_payload":
            key = args[0]
            if key == "user:1":
                await slow_request_gate.wait()
                return ("string", "stale-value", None, 0, -1, "raw", 1)
            if key == "user:2":
                return ("string", "fresh-value", None, 0, -1, "raw", 2)
        return func(*args, **kwargs)

    with patch("tuiredis.screens.main.asyncio.to_thread", side_effect=fake_to_thread):
        async with app.run_test(size=(120, 40)) as pilot:
            app.push_screen("main")
            await pilot.pause(0.1)
            main_screen = app.screen
            viewer = main_screen.query_one(ValueViewer)

            stale_task = asyncio.create_task(main_screen.on_key_tree_key_selected(KeyTree.KeySelected("user:1")))
            await pilot.pause(0.05)
            fresh_task = asyncio.create_task(main_screen.on_key_tree_key_selected(KeyTree.KeySelected("user:2")))
            await pilot.pause(0.05)

            slow_request_gate.set()
            await asyncio.gather(stale_task, fresh_task)
            await pilot.pause(0.1)

            assert viewer._current_key == "user:2"
            assert viewer._current_raw_data == "fresh-value"


@pytest.mark.asyncio
async def test_main_screen_shows_loading_status_during_key_detail_fetch(mock_redis_client):
    app = TRedisApp()
    app.redis_client = mock_redis_client
    app.redis_client.is_connected = True

    slow_request_gate = asyncio.Event()

    async def fake_to_thread(func, *args, **kwargs):
        if getattr(func, "__name__", "") == "_fetch_key_details_payload":
            await slow_request_gate.wait()
            return ("string", "value", None, 0, -1, "raw", 1)
        return func(*args, **kwargs)

    with patch("tuiredis.screens.main.asyncio.to_thread", side_effect=fake_to_thread):
        async with app.run_test(size=(120, 40)) as pilot:
            app.push_screen("main")
            await pilot.pause(0.1)
            main_screen = app.screen

            task = asyncio.create_task(main_screen.on_key_tree_key_selected(KeyTree.KeySelected("user:1")))
            await pilot.pause(0.05)
            status_bar = main_screen.query_one("#status-bar")
            assert "Loading user:1..." in str(status_bar.render())

            slow_request_gate.set()
            await task
            await pilot.pause(0.05)
            assert str(status_bar.render()) == ""


@pytest.mark.asyncio
async def test_key_rename_event(mock_redis_client):
    """Test that KeyRenamed event calls rename_key on the client."""
    mock_redis_client.rename_key.return_value = True
    mock_redis_client.get_type.return_value = "string"
    mock_redis_client.get_string.return_value = "value"
    mock_redis_client.get_ttl.return_value = -1
    mock_redis_client.get_encoding.return_value = "raw"
    mock_redis_client.get_memory_usage.return_value = 64

    app = TRedisApp()
    app.redis_client = mock_redis_client

    async with app.run_test(size=(120, 40)) as pilot:
        app.push_screen("main")
        await pilot.pause(0.2)
        main_screen = app.screen

        detail = main_screen.query_one(KeyDetail)
        detail.post_message(KeyDetail.KeyRenamed("old_key", "new_key"))
        await pilot.pause(0.2)

        mock_redis_client.rename_key.assert_called_with("old_key", "new_key")


@pytest.mark.asyncio
async def test_main_screen_zset_events(mock_redis_client):
    """Test MemberAdded for ZSet and MemberDeleted for Hash/Set/ZSet."""
    app = TRedisApp()
    app.redis_client = mock_redis_client
    app.redis_client.is_connected = True

    async with app.run_test(size=(120, 40)) as pilot:
        app.push_screen("main")
        await pilot.pause(0.2)
        main_screen = app.screen
        viewer = main_screen.query_one(ValueViewer)

        # MemberAdded ZSet
        viewer.post_message(ValueViewer.MemberAdded("myzset", "zset", ("member", 1.5)))
        await pilot.pause(0.1)
        mock_redis_client.zset_add.assert_called_with("myzset", "member", 1.5)

        # MemberDeleted Hash
        viewer.post_message(ValueViewer.MemberDeleted("myhash", "hash", "field1"))
        await pilot.pause(0.1)
        mock_redis_client.hash_delete.assert_called_with("myhash", "field1")

        # MemberDeleted Set
        viewer.post_message(ValueViewer.MemberDeleted("myset", "set", "member1"))
        await pilot.pause(0.1)
        mock_redis_client.set_remove.assert_called_with("myset", "member1")

        # MemberDeleted ZSet
        viewer.post_message(ValueViewer.MemberDeleted("myzset", "zset", "member"))
        await pilot.pause(0.1)
        mock_redis_client.zset_remove.assert_called_with("myzset", "member")


@pytest.mark.asyncio
async def test_main_screen_load_more_list(mock_redis_client):
    """on_value_viewer_load_more for list calls get_list with correct offset."""
    mock_redis_client.get_list.return_value = ["item3", "item4"]
    mock_redis_client.get_list_count.return_value = 10
    mock_redis_client.DISPLAY_LIMIT = 500

    app = TRedisApp()
    app.redis_client = mock_redis_client
    app.redis_client.is_connected = True

    async with app.run_test(size=(120, 40)) as pilot:
        app.push_screen("main")
        await pilot.pause(0.2)
        main_screen = app.screen
        viewer = main_screen.query_one(ValueViewer)

        # Simulate a list already loaded (2 items) then request page 2
        await viewer.show_value("mylist", "list", ["a", "b"], total_count=10)
        await pilot.pause(0.1)

        viewer.post_message(ValueViewer.LoadMore("mylist", "list", 2))
        await pilot.pause(0.2)

        mock_redis_client.get_list.assert_called_with("mylist", start=2, end=501)
        assert viewer._displayed_count == 4  # 2 original + 2 new


@pytest.mark.asyncio
async def test_main_screen_load_more_zset(mock_redis_client):
    """on_value_viewer_load_more for zset calls get_zset with correct offset."""
    mock_redis_client.get_zset.return_value = [("z3", 3.0)]
    mock_redis_client.get_zset_count.return_value = 5
    mock_redis_client.DISPLAY_LIMIT = 500

    app = TRedisApp()
    app.redis_client = mock_redis_client
    app.redis_client.is_connected = True

    async with app.run_test(size=(120, 40)) as pilot:
        app.push_screen("main")
        await pilot.pause(0.2)
        main_screen = app.screen
        viewer = main_screen.query_one(ValueViewer)

        await viewer.show_value("myzset", "zset", [("z1", 1.0), ("z2", 2.0)], total_count=5)
        await pilot.pause(0.1)

        viewer.post_message(ValueViewer.LoadMore("myzset", "zset", 2))
        await pilot.pause(0.2)

        mock_redis_client.get_zset.assert_called_with("myzset", start=2, end=501)
        assert viewer._displayed_count == 3



async def test_main_screen_member_deleted_key_gone(mock_redis_client):
    """If deleting last element makes key disappear, show_empty is called."""
    mock_redis_client.get_type.return_value = "none"  # key gone after delete

    app = TRedisApp()
    app.redis_client = mock_redis_client
    app.redis_client.is_connected = True

    async with app.run_test(size=(120, 40)) as pilot:
        app.push_screen("main")
        await pilot.pause(0.2)
        main_screen = app.screen
        viewer = main_screen.query_one(ValueViewer)

        viewer.post_message(ValueViewer.MemberDeleted("mylist", "list", (0, None)))
        await pilot.pause(0.2)

        # Viewer should be empty since key type is "none"
        assert viewer._current_key is None
