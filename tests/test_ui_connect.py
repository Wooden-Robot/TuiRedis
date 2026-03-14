from unittest.mock import AsyncMock, patch

import pytest
from textual.widgets import Button, Input, Static

from tuiredis.app import TRedisApp
from tuiredis.config import ConnectionProfile
from tuiredis.screens.connect import ConnectScreen


@pytest.fixture
def mock_redis_client():
    from tuiredis.redis_client import RedisClient

    with patch.object(RedisClient, "connect", return_value=(True, "")):
        with patch.object(RedisClient, "get_server_info", return_value={"redis_version": "7.0.0"}):
            with patch.object(RedisClient, "scan_keys_paginated", return_value=(0, [])):
                with patch.object(RedisClient, "get_keyspace_info", return_value={0: 10, 1: 5}):
                    with patch.object(RedisClient, "get_types", return_value={}):
                        with (
                            patch("tuiredis.screens.connect.load_connections", return_value=[]),
                            patch(
                                "tuiredis.screens.connect.save_connection",
                                return_value=(
                                    {"id": "test-id", "host": "127.0.0.1", "port": 6379, "db": 0},
                                    [],
                                    True,
                                ),
                            ),
                        ):
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


@pytest.mark.asyncio
async def test_connect_screen_quit_action_input(mock_redis_client):
    """Test quit action behavior in ConnectScreen when focused on input."""
    app = TRedisApp()
    async with app.run_test(size=(120, 80)) as pilot:
        # Start at connect screen
        assert isinstance(app.screen, ConnectScreen)

        # Focus host input
        host_input = app.screen.query_one("#host-input", Input)
        host_input.focus()
        await pilot.pause()

        # q should NOT quit app, but input a 'q'
        await pilot.press("q")
        await pilot.pause()
        assert app.is_running is True
        assert "q" in host_input.value


@pytest.mark.asyncio
async def test_connect_existing_profile_refreshes_history_after_successful_connect():
    from tuiredis.redis_client import RedisClient

    with (
        patch.object(RedisClient, "connect", return_value=(True, "")),
        patch.object(RedisClient, "get_server_info", return_value={"redis_version": "7.0.0"}),
        patch.object(RedisClient, "scan_keys_paginated", return_value=(0, [])),
        patch.object(RedisClient, "get_keyspace_info", return_value={0: 10, 1: 5}),
        patch.object(RedisClient, "get_types", return_value={}),
        patch("tuiredis.screens.connect.load_connections", return_value=[]),
        patch(
            "tuiredis.screens.connect.save_connection",
            return_value=(
                {"id": "existing-id", "name": "Updated", "host": "127.0.0.1", "port": 6379, "db": 0},
                [],
                True,
            ),
        ),
        patch.object(ConnectScreen, "_refresh_history", new_callable=AsyncMock) as refresh_history,
    ):
        app = TRedisApp()
        async with app.run_test(size=(120, 80)) as pilot:
            assert isinstance(app.screen, ConnectScreen)
            connect_screen = app.screen
            connect_screen.current_profile_id = "existing-id"

            connect_btn = connect_screen.query_one("#connect-btn", Button)
            await pilot.click(connect_btn)
            await pilot.pause(0.1)

            refresh_history.assert_awaited()
            assert connect_screen.current_profile_id == "existing-id"


def test_validate_profile_allows_large_db_index():
    screen = ConnectScreen()
    profile: ConnectionProfile = {"host": "127.0.0.1", "port": 6379, "db": 42}
    assert screen._validate_profile(profile) is None


def test_validate_profile_rejects_negative_db_index():
    screen = ConnectScreen()
    profile: ConnectionProfile = {"host": "127.0.0.1", "port": 6379, "db": -1}
    assert screen._validate_profile(profile) == "DB must be a non-negative integer (got -1)"


def test_profile_for_storage_strips_passwords_by_default():
    profile: ConnectionProfile = {
        "host": "127.0.0.1",
        "port": 6379,
        "db": 0,
        "password": "redis-secret",
        "sentinel_password": "sentinel-secret",
        "ssh_password": "ssh-secret",
        "save_secrets": False,
    }
    stored = ConnectScreen._profile_for_storage(profile)
    assert stored["password"] is None
    assert stored["sentinel_password"] is None
    assert stored["ssh_password"] is None


def test_profile_for_storage_keeps_passwords_when_enabled():
    profile: ConnectionProfile = {
        "host": "127.0.0.1",
        "port": 6379,
        "db": 0,
        "password": "redis-secret",
        "sentinel_password": "sentinel-secret",
        "ssh_password": "ssh-secret",
        "save_secrets": True,
    }
    stored = ConnectScreen._profile_for_storage(profile)
    assert stored["password"] == "redis-secret"
    assert stored["sentinel_password"] == "sentinel-secret"
    assert stored["ssh_password"] == "ssh-secret"


def test_validate_profile_requires_sentinel_master_name():
    screen = ConnectScreen()
    profile: ConnectionProfile = {
        "host": "127.0.0.1",
        "port": 6379,
        "db": 0,
        "use_sentinel": True,
        "sentinel_host": "127.0.0.1",
        "sentinel_port": 26379,
    }
    assert screen._validate_profile(profile) == "Sentinel Master Name cannot be empty when Redis Sentinel is enabled"


def test_validate_profile_rejects_cluster_db_not_zero():
    screen = ConnectScreen()
    profile: ConnectionProfile = {
        "host": "127.0.0.1",
        "port": 7000,
        "db": 1,
        "use_cluster": True,
    }
    assert screen._validate_profile(profile) == "Redis Cluster only supports DB 0"


def test_validate_profile_rejects_sentinel_with_ssh():
    screen = ConnectScreen()
    profile: ConnectionProfile = {
        "host": "127.0.0.1",
        "port": 6379,
        "db": 0,
        "use_sentinel": True,
        "sentinel_host": "127.0.0.1",
        "sentinel_port": 26379,
        "sentinel_master_name": "mymaster",
        "use_ssh": True,
        "ssh_host": "jump.local",
        "ssh_port": 22,
    }
    assert screen._validate_profile(profile) == "Redis Sentinel cannot be used together with SSH tunnel yet"


def test_validate_profile_rejects_cluster_with_ssh():
    screen = ConnectScreen()
    profile: ConnectionProfile = {
        "host": "127.0.0.1",
        "port": 7000,
        "db": 0,
        "use_cluster": True,
        "use_ssh": True,
        "ssh_host": "jump.local",
        "ssh_port": 22,
    }
    assert screen._validate_profile(profile) == "Redis Cluster cannot be used together with SSH tunnel yet"


def test_validate_profile_accepts_multiple_sentinel_nodes():
    screen = ConnectScreen()
    profile: ConnectionProfile = {
        "host": "127.0.0.1",
        "port": 6379,
        "db": 0,
        "use_sentinel": True,
        "sentinel_nodes": "s1:26379,s2:26380,s3",
        "sentinel_port": 26379,
        "sentinel_master_name": "mymaster",
    }
    assert screen._validate_profile(profile) is None
