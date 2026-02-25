from unittest.mock import patch

import pytest
from textual.widgets import Button, Input, Static

from tuiredis.app import TRedisApp
from tuiredis.screens.connect import ConnectScreen


@pytest.fixture
def mock_redis_client():
    from tuiredis.redis_client import RedisClient
    with patch.object(RedisClient, 'connect', return_value=(True, "")):
        with patch.object(RedisClient, 'get_server_info', return_value={"redis_version": "7.0.0"}):
            with patch.object(RedisClient, 'scan_keys_paginated', return_value=(0, [])):
                with patch.object(RedisClient, 'get_keyspace_info', return_value={0: 10, 1: 5}):
                    with patch.object(RedisClient, 'get_types', return_value={}):
                        with patch('tuiredis.screens.connect.load_connections', return_value=[]), \
                             patch('tuiredis.screens.connect.save_connection'):
                            yield


@pytest.mark.asyncio
async def test_connect_screen(mock_redis_client):
    """Test connecting to redis via ConnectScreen."""
    app = TRedisApp()
    async with app.run_test(size=(120, 80)) as pilot:
        # We start at connect screen
        assert isinstance(app.screen, ConnectScreen)

        # Test default values
        host_input = app.screen.query_one("#host-input", Input)
        port_input = app.screen.query_one("#port-input", Input)

        assert host_input.value == "127.0.0.1"
        assert port_input.value == "6379"

        # Simulate connecting
        connect_btn = app.screen.query_one("#connect-btn", Button)
        await pilot.click(connect_btn)
        await pilot.pause(0.1)

        # Should transition out of ConnectScreen to MainScreen
        if isinstance(app.screen, ConnectScreen):
            err_msg = app.screen.query_one("#connect-error", Static).renderable
            pytest.fail(f"Did not transition. UI Error: {err_msg}")
        assert not isinstance(app.screen, ConnectScreen)
