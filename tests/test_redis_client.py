import unittest
from unittest.mock import MagicMock, patch

import redis

from tuiredis.redis_client import RedisClient


class TestRedisClient(unittest.TestCase):
    def setUp(self):
        self.client = RedisClient(host="localhost", port=6379, password="pass", db=1)
        self.mock_redis = MagicMock(spec=redis.Redis)
        self.client._client = self.mock_redis

    def test_client_property_not_connected(self):
        self.client._client = None
        with self.assertRaises(ConnectionError):
            _ = self.client.client

    def test_client_property_connected(self):
        self.assertEqual(self.client.client, self.mock_redis)

    @patch('tuiredis.redis_client.redis.Redis')
    def test_connect_success(self, mock_redis_class):
        mock_instance = mock_redis_class.return_value
        self.client._client = None
        result, msg = self.client.connect()
        self.assertTrue(result)
        self.assertEqual(msg, "")
        mock_redis_class.assert_called_once_with(
            host="localhost", port=6379, password="pass", db=1, decode_responses=True, socket_connect_timeout=5
        )
        mock_instance.ping.assert_called_once()

    @patch('tuiredis.redis_client.redis.Redis')
    def test_connect_failure(self, mock_redis_class):
        mock_instance = mock_redis_class.return_value
        mock_instance.ping.side_effect = redis.ConnectionError()
        self.client._client = None
        result, msg = self.client.connect()
        self.assertFalse(result)
        self.assertIn("network:ConnectionError", msg)
        self.assertIsNone(self.client._client)

    def test_disconnect(self):
        tunnel_mock = MagicMock()
        self.client._ssh_tunnel = tunnel_mock
        self.client.disconnect()
        self.mock_redis.close.assert_called_once()
        tunnel_mock.stop.assert_called_once()
        self.assertIsNone(self.client._client)
        self.assertIsNone(self.client._ssh_tunnel)

    def test_disconnect_already_disconnected(self):
        self.client._client = None
        self.client._ssh_tunnel = None
        self.client.disconnect()  # Should not raise
        self.assertIsNone(self.client._client)
        self.assertIsNone(self.client._ssh_tunnel)

    def test_is_connected_true(self):
        self.assertTrue(self.client.is_connected)
        self.mock_redis.ping.assert_called_once()

    def test_is_connected_false_no_client(self):
        self.client._client = None
        self.assertFalse(self.client.is_connected)

    def test_is_connected_false_ping_fails(self):
        self.mock_redis.ping.side_effect = redis.ConnectionError()
        self.assertFalse(self.client.is_connected)

    @patch('tuiredis.redis_client.redis.Redis')
    def test_connect_with_ssh(self, mock_redis_class):
        # Setup SSH Client
        client = RedisClient(host="remote", port=6379, ssh_host="jump", ssh_user="root")

        mock_ssh_class = MagicMock()
        mock_ssh_instance = mock_ssh_class.return_value
        mock_ssh_instance.local_bind_port = 9999

        mock_redis_instance = mock_redis_class.return_value

        # Patch __import__ to return our mock for sshtunnel
        original_import = __import__
        def mock_import(name, *args, **kwargs):
            if name == 'sshtunnel':
                mock_module = MagicMock()
                mock_module.SSHTunnelForwarder = mock_ssh_class
                return mock_module
            return original_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=mock_import):
            result, msg = client.connect()
        self.assertTrue(result)
        self.assertEqual(msg, "")

        mock_ssh_class.assert_called_once_with(
            ssh_address_or_host=("jump", 22),
            ssh_username="root",
            remote_bind_address=("remote", 6379)
        )
        mock_ssh_instance.start.assert_called_once()

        # Should connect to the local forwarded port
        mock_redis_class.assert_called_once_with(
            host="127.0.0.1", port=9999, password=None, db=0, decode_responses=True, socket_connect_timeout=5
        )
        mock_redis_instance.ping.assert_called_once()

    @patch('tuiredis.redis_client.redis.Redis')
    def test_connect_ssh_failure(self, mock_redis_class):
        client = RedisClient(host="remote", port=6379, ssh_host="jump", ssh_user="root")

        mock_ssh_class = MagicMock()
        mock_ssh_instance = mock_ssh_class.return_value
        mock_ssh_instance.start.side_effect = Exception("SSH Failed")

        original_import = __import__
        def mock_import(name, *args, **kwargs):
            if name == 'sshtunnel':
                mock_module = MagicMock()
                mock_module.SSHTunnelForwarder = mock_ssh_class
                return mock_module
            return original_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=mock_import):
            result, msg = client.connect()

        self.assertFalse(result)
        self.assertIn("SSH Failed", msg)
        # Verify disconnect was called implicitly cleaning up
        self.assertIsNone(client._client)
        self.assertIsNone(client._ssh_tunnel)

    def test_switch_db_success(self):
        result = self.client.switch_db(2)
        self.mock_redis.select.assert_called_once_with(2)
        self.assertTrue(result)
        self.assertEqual(self.client.db, 2)

    def test_switch_db_failure(self):
        self.mock_redis.select.side_effect = redis.RedisError()
        result = self.client.switch_db(2)
        self.assertFalse(result)
        self.assertEqual(self.client.db, 1)

    def test_scan_keys(self):
        self.mock_redis.scan.side_effect = [
            (1, ["key1", "key2"]),
            (0, ["key3"])
        ]
        result = self.client.scan_keys(pattern="test*", count=100)
        self.assertEqual(result, sorted(["key1", "key2", "key3"]))
        self.assertEqual(self.mock_redis.scan.call_count, 2)

    def test_scan_keys_paginated_exact_count(self):
        keys = [f"key:{i}" for i in range(10)]
        self.mock_redis.scan.return_value = (0, keys)
        cursor, result = self.client.scan_keys_paginated(cursor=0, pattern="*", count=10)
        self.assertEqual(cursor, 0)
        self.assertEqual(len(result), 10)
        self.mock_redis.scan.assert_called_with(cursor=0, match="*", count=10)

    def test_scan_keys_paginated_multiple_calls_needed(self):
        def scan_side_effect(cursor, match, count):
            if cursor == 0:
                return (1, [f"key:1:{i}" for i in range(20)])
            elif cursor == 1:
                return (2, [f"key:2:{i}" for i in range(15)])
            elif cursor == 2:
                return (0, [f"key:3:{i}" for i in range(20)])

        self.mock_redis.scan.side_effect = scan_side_effect
        result_cursor, result_keys = self.client.scan_keys_paginated(cursor=0, pattern="*", count=50)
        self.assertEqual(result_cursor, 0)
        self.assertEqual(len(result_keys), 55)
        self.assertEqual(self.mock_redis.scan.call_count, 3)

    def test_get_type(self):
        self.mock_redis.type.return_value = "string"
        self.assertEqual(self.client.get_type("mykey"), "string")
        self.mock_redis.type.assert_called_once_with("mykey")

    def test_get_types(self):
        mock_pipeline = MagicMock()
        self.mock_redis.pipeline.return_value = mock_pipeline
        mock_pipeline.execute.return_value = ["string", "list"]

        result = self.client.get_types(["key1", "key2"])
        self.assertEqual(result, {"key1": "string", "key2": "list"})
        self.assertEqual(mock_pipeline.type.call_count, 2)
        mock_pipeline.execute.assert_called_once()

    def test_get_types_empty(self):
        self.assertEqual(self.client.get_types([]), {})

    def test_get_ttl(self):
        self.mock_redis.ttl.return_value = 100
        self.assertEqual(self.client.get_ttl("mykey"), 100)
        self.mock_redis.ttl.assert_called_once_with("mykey")

    def test_get_encoding(self):
        self.mock_redis.object.return_value = b"raw"
        self.assertEqual(self.client.get_encoding("mykey"), "b'raw'")

    def test_get_memory_usage(self):
        self.mock_redis.memory_usage.return_value = 1024
        self.assertEqual(self.client.get_memory_usage("mykey"), 1024)

    def test_get_memory_usage_error(self):
        self.mock_redis.memory_usage.side_effect = redis.RedisError()
        self.assertIsNone(self.client.get_memory_usage("mykey"))

    def test_delete_key(self):
        self.mock_redis.delete.return_value = 1
        self.assertTrue(self.client.delete_key("mykey"))
        self.mock_redis.delete.assert_called_once_with("mykey")

    def test_rename_key_success(self):
        self.mock_redis.rename.return_value = True
        self.assertTrue(self.client.rename_key("old", "new"))
        self.mock_redis.rename.assert_called_once_with("old", "new")

    def test_rename_key_failure(self):
        self.mock_redis.rename.side_effect = redis.ResponseError()
        self.assertFalse(self.client.rename_key("old", "new"))

    def test_set_ttl(self):
        self.mock_redis.expire.return_value = True
        self.assertTrue(self.client.set_ttl("mykey", 100))
        self.mock_redis.expire.assert_called_once_with("mykey", 100)

    def test_set_ttl_remove(self):
        self.mock_redis.persist.return_value = True
        self.assertTrue(self.client.set_ttl("mykey", -1))
        self.mock_redis.persist.assert_called_once_with("mykey")

    def test_get_string(self):
        self.mock_redis.get.return_value = "val"
        self.assertEqual(self.client.get_string("mykey"), "val")

    def test_set_string(self):
        self.client.set_string("mykey", "val", ttl=100)
        self.mock_redis.set.assert_called_once_with("mykey", "val", ex=100)

    def test_get_list(self):
        self.mock_redis.lrange.return_value = ["1", "2"]
        self.assertEqual(self.client.get_list("mykey"), ["1", "2"])

    def test_list_push(self):
        self.client.list_push("mykey", "v1", "v2")
        self.mock_redis.rpush.assert_called_once_with("mykey", "v1", "v2")

    def test_list_set(self):
        self.client.list_set("mykey", 0, "val")
        self.mock_redis.lset.assert_called_once_with("mykey", 0, "val")

    def test_list_remove(self):
        self.client.list_remove("mykey", "val", count=2)
        self.mock_redis.lrem.assert_called_once_with("mykey", 2, "val")

    def test_get_hash(self):
        self.mock_redis.hgetall.return_value = {"f1": "v1"}
        self.assertEqual(self.client.get_hash("mykey"), {"f1": "v1"})

    def test_hash_set(self):
        self.client.hash_set("mykey", "f1", "v1")
        self.mock_redis.hset.assert_called_once_with("mykey", "f1", "v1")

    def test_hash_delete(self):
        self.client.hash_delete("mykey", "f1", "f2")
        self.mock_redis.hdel.assert_called_once_with("mykey", "f1", "f2")

    def test_get_set(self):
        self.mock_redis.smembers.return_value = {"v1", "v2"}
        self.assertEqual(self.client.get_set("mykey"), {"v1", "v2"})

    def test_set_add(self):
        self.client.set_add("mykey", "v1", "v2")
        self.mock_redis.sadd.assert_called_once_with("mykey", "v1", "v2")

    def test_set_remove(self):
        self.client.set_remove("mykey", "v1", "v2")
        self.mock_redis.srem.assert_called_once_with("mykey", "v1", "v2")

    def test_get_zset(self):
        self.mock_redis.zrange.return_value = [("v1", 1.0)]
        self.assertEqual(self.client.get_zset("mykey"), [("v1", 1.0)])

    def test_zset_add(self):
        self.client.zset_add("mykey", "v1", 1.0)
        self.mock_redis.zadd.assert_called_once_with("mykey", {"v1": 1.0})

    def test_zset_remove(self):
        self.client.zset_remove("mykey", "v1", "v2")
        self.mock_redis.zrem.assert_called_once_with("mykey", "v1", "v2")

    def test_get_server_info(self):
        self.mock_redis.info.return_value = {"redis_version": "7.0.0"}
        self.assertEqual(self.client.get_server_info(), {"redis_version": "7.0.0"})

    def test_get_keyspace_info(self):
        self.mock_redis.info.return_value = {
            "db0": {"keys": 10},
            "db1": {"keys": 5},
            "dbx": "invalid"
        }
        self.assertEqual(self.client.get_keyspace_info(), {0: 10, 1: 5})

    def test_get_keyspace_info_error(self):
        self.mock_redis.info.side_effect = redis.RedisError()
        self.assertEqual(self.client.get_keyspace_info(), {})

    def test_get_db_size(self):
        self.mock_redis.dbsize.return_value = 100
        self.assertEqual(self.client.get_db_size(), 100)

    def test_execute_command(self):
        self.mock_redis.execute_command.return_value = b"OK"
        self.assertEqual(self.client.execute_command("PING"), "OK")

        self.mock_redis.execute_command.return_value = ["a", "b"]
        self.assertEqual(self.client.execute_command("LRANGE key 0 -1"), "1) a\n2) b")

        self.mock_redis.execute_command.return_value = {"k": "v"}
        self.assertEqual(self.client.execute_command("HGETALL key"), "k: v")

        self.mock_redis.execute_command.return_value = True
        self.assertEqual(self.client.execute_command("EXISTS key"), "OK")

        self.mock_redis.execute_command.return_value = None
        self.assertEqual(self.client.execute_command("GET missing"), "(nil)")

    def test_execute_command_errors(self):
        self.mock_redis.execute_command.side_effect = redis.ResponseError("ERR syntax")
        self.assertEqual(self.client.execute_command("BADCMD"), "(error) ERR syntax")

        self.mock_redis.execute_command.side_effect = Exception("Unknown")
        self.assertEqual(self.client.execute_command("CMD"), "(error) Unknown")

        self.assertEqual(self.client.execute_command("   "), "")

    def test_execute_command_empty_list(self):
        self.mock_redis.execute_command.return_value = []
        self.assertEqual(self.client.execute_command("LRANGE empty 0 -1"), "(empty list)")

    def test_connection_label(self):
        self.assertEqual(self.client.connection_label, "🔒localhost:6379/db1")
        self.client.password = None
        self.assertEqual(self.client.connection_label, "localhost:6379/db1")

if __name__ == '__main__':
    unittest.main()
