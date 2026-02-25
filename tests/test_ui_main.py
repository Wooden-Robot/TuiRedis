from unittest.mock import MagicMock, patch

import pytest
from textual.widgets import Input, Select

from tuiredis.app import TRedisApp
from tuiredis.redis_client import RedisClient
from tuiredis.screens.main import MainScreen
from tuiredis.widgets.command_input import CommandInput
from tuiredis.widgets.key_detail import KeyDetail
from tuiredis.widgets.key_tree import KeyTree
from tuiredis.widgets.value_viewer import ValueViewer


@pytest.fixture
def mock_redis_client():
    client = MagicMock(spec=RedisClient)
    client.connection_label = "mock_host:6379"
    client.get_server_info.return_value = {"redis_version": "7.0.0", "db0": 10}
    client.db = 0
    client.password = None
    client.get_db_size.return_value = 10
    client.get_keyspace_info.return_value = {0: 10, 1: 5}
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

    # Apply patches for connection management functions
    with patch('tuiredis.screens.connect.load_connections', return_value=[]), \
         patch('tuiredis.screens.connect.save_connection'):
        yield client


@pytest.mark.asyncio
async def test_app_auto_connect(mock_redis_client):
    """Test auto-connect bypassing the connect screen."""
    with patch.object(RedisClient, 'connect', return_value=(True, "")):
        with patch.object(RedisClient, 'get_server_info', mock_redis_client.get_server_info), \
             patch.object(RedisClient, 'get_keyspace_info', mock_redis_client.get_keyspace_info), \
             patch.object(RedisClient, 'scan_keys_paginated', mock_redis_client.scan_keys_paginated), \
             patch.object(RedisClient, 'get_types', mock_redis_client.get_types):

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

        # Test Command Input execution
        cmd = main_screen.query_one(CommandInput)
        mock_redis_client.execute_command.return_value = "PONG"
        cmd.post_message(CommandInput.CommandSubmitted("PING"))
        await pilot.pause(0.1)
        mock_redis_client.execute_command.assert_called_with("PING")

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

        # Test MemberAdded (List)
        viewer.post_message(ValueViewer.MemberAdded("mylist", "list", "new_item"))
        await pilot.pause(0.1)
        mock_redis_client.list_push.assert_called_with("mylist", "new_item")

        # Test MemberAdded (Set)
        viewer.post_message(ValueViewer.MemberAdded("myset", "set", "new_member"))
        await pilot.pause(0.1)
        mock_redis_client.set_add.assert_called_with("myset", "new_member")
