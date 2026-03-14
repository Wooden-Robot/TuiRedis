import json
from unittest.mock import patch

from tuiredis.config import (
    ConnectionProfile,
    delete_connection,
    get_config_dir,
    get_connections_file,
    load_connections,
    save_connection,
)


def test_get_config_dir_creates_dir(tmp_path):
    with patch("tuiredis.config.Path.home", return_value=tmp_path):
        config_dir = get_config_dir()
        assert config_dir == tmp_path / ".tuiredis"
        assert config_dir.exists()


def test_load_connections_empty(tmp_path):
    with patch("tuiredis.config.Path.home", return_value=tmp_path):
        assert load_connections() == []


def test_save_connection_new(tmp_path):
    with patch("tuiredis.config.Path.home", return_value=tmp_path):
        profile: ConnectionProfile = {
            "name": "Test DB",
            "host": "localhost",
            "port": 6379,
            "db": 0,
        }
        saved_profile, connections, persisted = save_connection(profile)

        assert persisted is True
        assert len(connections) == 1
        assert connections[0]["name"] == "Test DB"
        assert "id" in connections[0]  # ID must be generated
        assert saved_profile["id"] == connections[0]["id"]

        # Verify written file
        file_path = get_connections_file()
        assert file_path.exists()
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert data[0]["name"] == "Test DB"
            assert data[0]["id"] == connections[0]["id"]


def test_save_connection_update(tmp_path):
    with patch("tuiredis.config.Path.home", return_value=tmp_path):
        profile: ConnectionProfile = {
            "name": "DB 1",
            "host": "localhost",
            "port": 6379,
            "db": 0,
        }
        saved1, conns1, persisted1 = save_connection(profile)
        assert persisted1 is True
        conn_id = saved1["id"]

        # Update name
        profile_update = dict(conns1[0])
        profile_update["name"] = "DB 1 Updated"
        profile_update["port"] = 6380

        saved2, conns2, persisted2 = save_connection(profile_update)  # type: ignore

        assert persisted2 is True
        assert len(conns2) == 1
        assert conns2[0]["id"] == conn_id
        assert conns2[0]["name"] == "DB 1 Updated"
        assert conns2[0]["port"] == 6380


def test_save_multiple_connections(tmp_path):
    with patch("tuiredis.config.Path.home", return_value=tmp_path):
        p1 = {"host": "h1", "port": 1}
        p2 = {"host": "h2", "port": 2}

        _, _, persisted1 = save_connection(p1)  # type: ignore
        _, connections, persisted2 = save_connection(p2)  # type: ignore

        assert persisted1 is True
        assert persisted2 is True
        assert len(connections) == 2
        assert connections[0]["host"] == "h1"
        assert connections[1]["host"] == "h2"
        # Names should be generated since none were provided
        assert connections[0]["name"] == "h1:1"
        assert connections[1]["name"] == "h2:2"


def test_delete_connection(tmp_path):
    with patch("tuiredis.config.Path.home", return_value=tmp_path):
        _, _, persisted1 = save_connection({"name": "c1", "host": "h1", "port": 1})  # type: ignore
        saved2, _, persisted2 = save_connection({"name": "c2", "host": "h2", "port": 2})  # type: ignore

        assert persisted1 is True
        assert persisted2 is True
        id_to_delete = saved2["id"]

        after_del, persisted = delete_connection(id_to_delete)
        assert persisted is True
        assert len(after_del) == 1
        assert after_del[0]["name"] == "c1"


def test_load_connections_invalid_json(tmp_path):
    """load_connections should return [] when file contains invalid JSON."""
    with patch("tuiredis.config.Path.home", return_value=tmp_path):
        cfg_file = get_connections_file()
        cfg_file.parent.mkdir(parents=True, exist_ok=True)
        cfg_file.write_text("not valid json", encoding="utf-8")
        assert load_connections() == []


def test_load_connections_non_list_json(tmp_path):
    """load_connections should return [] when file contains valid JSON but not a list."""
    with patch("tuiredis.config.Path.home", return_value=tmp_path):
        cfg_file = get_connections_file()
        cfg_file.parent.mkdir(parents=True, exist_ok=True)
        cfg_file.write_text('{"key": "value"}', encoding="utf-8")
        assert load_connections() == []


def test_save_connection_deduplication(tmp_path):
    """Saving a connection with the same host/port/db should update, not duplicate."""
    with patch("tuiredis.config.Path.home", return_value=tmp_path):
        p1 = {"host": "localhost", "port": 6379, "db": 0}
        saved1, _, persisted1 = save_connection(p1)  # type: ignore
        assert persisted1 is True
        conn_id = saved1["id"]

        # Second save — same details, no ID passed → should find and reuse the ID
        p2 = {"host": "localhost", "port": 6379, "db": 0, "name": "Updated"}
        saved2, conns, persisted2 = save_connection(p2)  # type: ignore
        assert persisted2 is True
        assert len(conns) == 1
        assert saved2["id"] == conn_id
        assert conns[0]["name"] == "Updated"


def test_save_connection_different_passwords_do_not_deduplicate(tmp_path):
    with patch("tuiredis.config.Path.home", return_value=tmp_path):
        _, _, persisted1 = save_connection({"host": "localhost", "port": 6379, "db": 0, "password": "a"})  # type: ignore
        _, conns, persisted2 = save_connection({"host": "localhost", "port": 6379, "db": 0, "password": "b"})  # type: ignore

        assert persisted1 is True
        assert persisted2 is True
        assert len(conns) == 2


def test_save_connection_write_failure(tmp_path):
    """save_connection should report persistence failure without raising."""
    with patch("tuiredis.config.Path.home", return_value=tmp_path):
        with patch("pathlib.Path.open", side_effect=OSError("disk full")):
            profile, conns, persisted = save_connection({"name": "X", "host": "h", "port": 1})  # type: ignore
            assert profile.get("name") == "X"
            assert len(conns) == 1
            assert persisted is False
            assert not get_connections_file().exists()


def test_delete_connection_nonexistent_id(tmp_path):
    """delete_connection with an unknown ID should be a no-op (list unchanged)."""
    with patch("tuiredis.config.Path.home", return_value=tmp_path):
        _, _, persisted1 = save_connection({"name": "keep", "host": "h1", "port": 1})  # type: ignore
        assert persisted1 is True
        result, persisted2 = delete_connection("does-not-exist")
        assert persisted2 is True
        assert len(result) == 1
        assert result[0]["name"] == "keep"


def test_delete_connection_write_failure(tmp_path):
    """delete_connection should report persistence failure without raising."""
    with patch("tuiredis.config.Path.home", return_value=tmp_path):
        saved, _, persisted1 = save_connection({"name": "keep", "host": "h1", "port": 1})  # type: ignore
        assert persisted1 is True
        with patch("pathlib.Path.open", side_effect=OSError("disk full")):
            result, persisted2 = delete_connection(saved["id"])
        assert persisted2 is False
        assert result == []
        assert load_connections()[0]["id"] == saved["id"]


def test_get_config_dir_mkdir_failure(tmp_path):
    """get_config_dir should not raise even if mkdir fails."""
    with patch("tuiredis.config.Path.home", return_value=tmp_path):
        with patch("pathlib.Path.mkdir", side_effect=OSError("permission denied")):
            # Should not raise
            result = get_config_dir()
            assert result == tmp_path / ".tuiredis"
