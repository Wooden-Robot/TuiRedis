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
        res = save_connection(profile)

        assert len(res) == 1
        assert res[0]["name"] == "Test DB"
        assert "id" in res[0]  # ID must be generated

        # Verify written file
        file_path = get_connections_file()
        assert file_path.exists()
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert data[0]["name"] == "Test DB"
            assert data[0]["id"] == res[0]["id"]


def test_save_connection_update(tmp_path):
    with patch("tuiredis.config.Path.home", return_value=tmp_path):
        profile: ConnectionProfile = {
            "name": "DB 1",
            "host": "localhost",
            "port": 6379,
            "db": 0,
        }
        res1 = save_connection(profile)
        conn_id = res1[0]["id"]

        # Update name
        profile_update = dict(res1[0])
        profile_update["name"] = "DB 1 Updated"
        profile_update["port"] = 6380

        res2 = save_connection(profile_update) # type: ignore

        assert len(res2) == 1
        assert res2[0]["id"] == conn_id
        assert res2[0]["name"] == "DB 1 Updated"
        assert res2[0]["port"] == 6380


def test_save_multiple_connections(tmp_path):
    with patch("tuiredis.config.Path.home", return_value=tmp_path):
        p1 = {"host": "h1", "port": 1}
        p2 = {"host": "h2", "port": 2}

        save_connection(p1)  # type: ignore
        res = save_connection(p2)  # type: ignore

        assert len(res) == 2
        assert res[0]["host"] == "h1"
        assert res[1]["host"] == "h2"
        # Names should be generated since none were provided
        assert res[0]["name"] == "h1:1"
        assert res[1]["name"] == "h2:2"


def test_delete_connection(tmp_path):
    with patch("tuiredis.config.Path.home", return_value=tmp_path):
        save_connection({"name": "c1", "host": "h1", "port": 1}) # type: ignore
        res = save_connection({"name": "c2", "host": "h2", "port": 2}) # type: ignore

        id_to_delete = res[0]["id"]

        after_del = delete_connection(id_to_delete)
        assert len(after_del) == 1
        assert after_del[0]["name"] == "c2"
