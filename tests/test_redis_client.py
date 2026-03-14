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

    @patch("tuiredis.redis_client.redis.Redis")
    def test_connect_success(self, mock_redis_class):
        mock_instance = mock_redis_class.return_value
        self.client._client = None
        result, msg = self.client.connect()
        self.assertTrue(result)
        self.assertEqual(msg, "")
        mock_redis_class.assert_called_once_with(
            host="localhost", port=6379, password="pass", db=1, decode_responses=True, socket_connect_timeout=5, socket_timeout=10
        )
        mock_instance.ping.assert_called_once()

    @patch("tuiredis.redis_client.redis.Redis")
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

    @patch("tuiredis.redis_client.redis.Redis")
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
            if name == "sshtunnel":
                mock_module = MagicMock()
                mock_module.SSHTunnelForwarder = mock_ssh_class
                return mock_module
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            result, msg = client.connect()
        self.assertTrue(result)
        self.assertEqual(msg, "")

        mock_ssh_class.assert_called_once_with(
            ssh_address_or_host=("jump", 22), ssh_username="root", remote_bind_address=("remote", 6379)
        )
        mock_ssh_instance.start.assert_called_once()

        # Should connect to the local forwarded port
        mock_redis_class.assert_called_once_with(
            host="127.0.0.1", port=9999, password=None, db=0, decode_responses=True, socket_connect_timeout=5, socket_timeout=10
        )
        mock_redis_instance.ping.assert_called_once()

    @patch("tuiredis.redis_client.redis.Redis")
    def test_connect_ssh_failure(self, mock_redis_class):
        client = RedisClient(host="remote", port=6379, ssh_host="jump", ssh_user="root")

        mock_ssh_class = MagicMock()
        mock_ssh_instance = mock_ssh_class.return_value
        mock_ssh_instance.start.side_effect = Exception("SSH Failed")

        original_import = __import__

        def mock_import(name, *args, **kwargs):
            if name == "sshtunnel":
                mock_module = MagicMock()
                mock_module.SSHTunnelForwarder = mock_ssh_class
                return mock_module
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            result, msg = client.connect()

        self.assertFalse(result)
        self.assertIn("SSH Failed", msg)
        # Verify disconnect was called implicitly cleaning up
        self.assertIsNone(client._client)
        self.assertIsNone(client._ssh_tunnel)

    @patch("redis.sentinel.Sentinel")
    def test_connect_with_sentinel(self, mock_sentinel_class):
        client = RedisClient(
            password="redis-pass",
            db=2,
            use_sentinel=True,
            sentinel_host="sentinel.local",
            sentinel_port=26379,
            sentinel_master_name="mymaster",
            sentinel_password="sentinel-pass",
        )
        sentinel_instance = mock_sentinel_class.return_value
        redis_instance = MagicMock(spec=redis.Redis)
        sentinel_instance.master_for.return_value = redis_instance

        result, msg = client.connect()

        self.assertTrue(result)
        self.assertEqual(msg, "")
        mock_sentinel_class.assert_called_once_with(
            [("sentinel.local", 26379)],
            sentinel_kwargs={
                "socket_timeout": 10,
                "socket_connect_timeout": 5,
                "decode_responses": True,
                "password": "sentinel-pass",
            },
        )
        sentinel_instance.master_for.assert_called_once_with(
            "mymaster",
            password="redis-pass",
            db=2,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=10,
        )
        redis_instance.ping.assert_called_once()

    @patch("redis.cluster.RedisCluster")
    def test_connect_with_cluster(self, mock_cluster_class):
        client = RedisClient(
            host="cluster.local",
            port=7000,
            password="cluster-pass",
            use_cluster=True,
        )
        cluster_instance = mock_cluster_class.return_value

        result, msg = client.connect()

        self.assertTrue(result)
        self.assertEqual(msg, "")
        mock_cluster_class.assert_called_once_with(
            host="cluster.local",
            port=7000,
            password="cluster-pass",
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=10,
        )
        cluster_instance.ping.assert_called_once()

    @patch("redis.sentinel.Sentinel")
    def test_connect_with_multiple_sentinel_nodes(self, mock_sentinel_class):
        client = RedisClient(
            use_sentinel=True,
            sentinel_nodes="s1:26379,s2:26380,s3",
            sentinel_port=26379,
            sentinel_master_name="mymaster",
        )
        sentinel_instance = mock_sentinel_class.return_value
        redis_instance = MagicMock(spec=redis.Redis)
        sentinel_instance.master_for.return_value = redis_instance

        result, msg = client.connect()

        self.assertTrue(result)
        self.assertEqual(msg, "")
        mock_sentinel_class.assert_called_once_with(
            [("s1", 26379), ("s2", 26380), ("s3", 26379)],
            sentinel_kwargs={
                "socket_timeout": 10,
                "socket_connect_timeout": 5,
                "decode_responses": True,
            },
        )

    def test_connect_sentinel_with_ssh_rejected(self):
        client = RedisClient(use_sentinel=True, sentinel_master_name="mymaster", ssh_host="jump")
        result, msg = client.connect()
        self.assertFalse(result)
        self.assertIn("SSH tunnel", msg)

    def test_connect_cluster_with_sentinel_rejected(self):
        client = RedisClient(use_cluster=True, use_sentinel=True)
        result, msg = client.connect()
        self.assertFalse(result)
        self.assertIn("Sentinel", msg)

    def test_connect_cluster_with_ssh_rejected(self):
        client = RedisClient(use_cluster=True, ssh_host="jump")
        result, msg = client.connect()
        self.assertFalse(result)
        self.assertIn("SSH tunnel", msg)

    def test_get_string_retries_after_sentinel_connection_error(self):
        client = RedisClient(use_sentinel=True, sentinel_master_name="mymaster")
        first_redis = MagicMock(spec=redis.Redis)
        second_redis = MagicMock(spec=redis.Redis)
        first_redis.get.side_effect = redis.ConnectionError("failover")
        second_redis.get.return_value = "value"
        client._client = first_redis

        def reconnect():
            client._client = second_redis
            return True, ""

        client.connect = MagicMock(side_effect=reconnect)

        result = client.get_string("mykey")

        self.assertEqual(result, "value")
        client.connect.assert_called_once()
        second_redis.get.assert_called_once_with("mykey")

    def test_set_string_retries_after_sentinel_readonly_error(self):
        client = RedisClient(use_sentinel=True, sentinel_master_name="mymaster")
        first_redis = MagicMock(spec=redis.Redis)
        second_redis = MagicMock(spec=redis.Redis)
        first_redis.set.side_effect = redis.ResponseError("READONLY You can't write against a read only replica.")
        second_redis.set.return_value = True
        client._client = first_redis

        def reconnect():
            client._client = second_redis
            return True, ""

        client.connect = MagicMock(side_effect=reconnect)

        client.set_string("mykey", "value", ttl=30)

        client.connect.assert_called_once()
        second_redis.set.assert_called_once_with("mykey", "value", ex=30)

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

    def test_switch_db_rejected_for_cluster(self):
        client = RedisClient(use_cluster=True)
        client._client = MagicMock()

        result = client.switch_db(0)

        self.assertFalse(result)
        client._client.select.assert_not_called()

    def test_scan_keys(self):
        self.mock_redis.scan.side_effect = [(1, ["key1", "key2"]), (0, ["key3"])]
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

    def test_scan_keys_paginated_cluster_uses_iterator_state(self):
        client = RedisClient(use_cluster=True)
        cluster_client = MagicMock()
        cluster_client.scan_iter.return_value = iter(["k1", "k2", "k3", "k4", "k5"])
        client._client = cluster_client

        cursor_1, keys_1 = client.scan_keys_paginated(cursor=0, pattern="user:*", count=2)
        cursor_2, keys_2 = client.scan_keys_paginated(cursor=cursor_1, pattern="user:*", count=2)
        cursor_3, keys_3 = client.scan_keys_paginated(cursor=cursor_2, pattern="user:*", count=2)

        self.assertEqual((cursor_1, keys_1), (2, ["k1", "k2"]))
        self.assertEqual((cursor_2, keys_2), (4, ["k3", "k4"]))
        self.assertEqual((cursor_3, keys_3), (0, ["k5"]))
        cluster_client.scan_iter.assert_called_once_with(match="user:*", count=2)

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

    def test_get_types_cluster_routes_per_key(self):
        client = RedisClient(use_cluster=True)
        cluster_client = MagicMock()
        cluster_client.type.side_effect = ["string", "hash"]
        client._client = cluster_client

        result = client.get_types(["key1", "key2"])

        self.assertEqual(result, {"key1": "string", "key2": "hash"})
        cluster_client.pipeline.assert_not_called()
        self.assertEqual(cluster_client.type.call_count, 2)

    def test_get_types_empty(self):
        self.assertEqual(self.client.get_types([]), {})

    def test_get_ttl(self):
        self.mock_redis.ttl.return_value = 100
        self.assertEqual(self.client.get_ttl("mykey"), 100)
        self.mock_redis.ttl.assert_called_once_with("mykey")

    def test_get_ttls_cluster_routes_per_key(self):
        client = RedisClient(use_cluster=True)
        cluster_client = MagicMock()
        cluster_client.ttl.side_effect = [100, -1]
        client._client = cluster_client

        result = client.get_ttls(["key1", "key2"])

        self.assertEqual(result, {"key1": 100, "key2": -1})
        cluster_client.pipeline.assert_not_called()
        self.assertEqual(cluster_client.ttl.call_count, 2)

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

    def test_list_delete_by_index(self):
        tombstone = "__TUIREDIS_DEL_TOMBSTONE__"
        self.client.list_delete_by_index("mykey", 2)
        self.mock_redis.lset.assert_called_once_with("mykey", 2, tombstone)
        self.mock_redis.lrem.assert_called_once_with("mykey", 1, tombstone)

    def test_get_hash(self):
        self.mock_redis.hlen.return_value = 1  # small hash → uses hgetall fast path
        self.mock_redis.hgetall.return_value = {"f1": "v1"}
        self.assertEqual(self.client.get_hash("mykey"), {"f1": "v1"})

    def test_hash_set(self):
        self.client.hash_set("mykey", "f1", "v1")
        self.mock_redis.hset.assert_called_once_with("mykey", "f1", "v1")

    def test_hash_delete(self):
        self.client.hash_delete("mykey", "f1", "f2")
        self.mock_redis.hdel.assert_called_once_with("mykey", "f1", "f2")

    def test_get_set(self):
        self.mock_redis.scard.return_value = 2  # small set → uses smembers fast path
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

    def test_get_server_info_aggregates_cluster_nodes(self):
        client = RedisClient(use_cluster=True)
        cluster_client = MagicMock()
        cluster_client.info.return_value = {
            "127.0.0.1:7000": {
                "redis_version": "7.0.0",
                "redis_mode": "cluster",
                "os": "Linux",
                "uptime_in_days": 2,
                "connected_clients": 5,
                "blocked_clients": 1,
                "tracking_clients": 0,
                "total_connections_received": 10,
                "total_commands_processed": 100,
                "instantaneous_ops_per_sec": 20,
                "keyspace_hits": 11,
                "keyspace_misses": 3,
                "used_memory": 1024,
                "used_memory_peak": 2048,
                "maxmemory": 0,
                "mem_fragmentation_ratio": 1.2,
                "db0": {"keys": 4},
            },
            "127.0.0.1:7001": {
                "redis_version": "7.0.0",
                "redis_mode": "cluster",
                "os": "Linux",
                "uptime_in_days": 5,
                "connected_clients": 7,
                "blocked_clients": 0,
                "tracking_clients": 2,
                "total_connections_received": 30,
                "total_commands_processed": 400,
                "instantaneous_ops_per_sec": 40,
                "keyspace_hits": 13,
                "keyspace_misses": 5,
                "used_memory": 2048,
                "used_memory_peak": 4096,
                "maxmemory": 1024,
                "mem_fragmentation_ratio": 1.4,
                "db0": {"keys": 6},
            },
        }
        client._client = cluster_client

        info = client.get_server_info()

        self.assertEqual(info["redis_mode"], "cluster")
        self.assertEqual(info["cluster_nodes"], 2)
        self.assertEqual(info["uptime_in_days"], 5)
        self.assertEqual(info["connected_clients"], 12)
        self.assertEqual(info["total_commands_processed"], 500)
        self.assertEqual(info["db0"], {"keys": 10})
        self.assertEqual(info["used_memory_human"], "3.0KB")

    def test_get_keyspace_info(self):
        self.mock_redis.info.return_value = {"db0": {"keys": 10}, "db1": {"keys": 5}, "dbx": "invalid"}
        self.assertEqual(self.client.get_keyspace_info(), {0: 10, 1: 5})

    def test_get_keyspace_info_aggregates_cluster_nodes(self):
        client = RedisClient(use_cluster=True)
        cluster_client = MagicMock()
        cluster_client.info.return_value = {
            "127.0.0.1:7000": {"db0": {"keys": 10}, "db1": {"keys": 2}},
            "127.0.0.1:7001": {"db0": {"keys": 7}},
        }
        client._client = cluster_client

        self.assertEqual(client.get_keyspace_info(), {0: 17, 1: 2})

    def test_get_keyspace_info_error(self):
        self.mock_redis.info.side_effect = redis.RedisError()
        self.assertEqual(self.client.get_keyspace_info(), {})

    def test_get_database_count_from_config(self):
        self.mock_redis.config_get.return_value = {"databases": "32"}
        self.assertEqual(self.client.get_database_count(), 32)
        self.mock_redis.config_get.assert_called_once_with("databases")

    def test_get_database_count_falls_back_to_keyspace(self):
        self.mock_redis.config_get.side_effect = redis.RedisError()
        self.mock_redis.info.return_value = {"db0": {"keys": 10}, "db7": {"keys": 5}}
        self.assertEqual(self.client.get_database_count(), 8)

    def test_get_database_count_falls_back_to_current_db(self):
        self.mock_redis.config_get.side_effect = redis.RedisError()
        self.mock_redis.info.side_effect = redis.RedisError()
        self.client.db = 42
        self.assertEqual(self.client.get_database_count(), 43)

    def test_get_database_count_returns_one_for_cluster(self):
        client = RedisClient(use_cluster=True, db=42)
        self.assertEqual(client.get_database_count(), 1)

    def test_get_db_size(self):
        self.mock_redis.dbsize.return_value = 100
        self.assertEqual(self.client.get_db_size(), 100)

    def test_get_db_size_sums_cluster_nodes(self):
        client = RedisClient(use_cluster=True)
        cluster_client = MagicMock()
        cluster_client.dbsize.return_value = {"127.0.0.1:7000": 10, "127.0.0.1:7001": 15}
        client._client = cluster_client

        self.assertEqual(client.get_db_size(), 25)

    def test_execute_command(self):
        self.mock_redis.execute_command.return_value = b"OK"
        self.assertEqual(self.client.execute_command("PING"), "OK")

        self.mock_redis.execute_command.return_value = ["a", "b"]
        self.assertEqual(self.client.execute_command("LRANGE key 0 -1"), "1) a\n2) b")

        self.mock_redis.execute_command.return_value = {"k": "v"}
        self.assertEqual(self.client.execute_command("HGETALL key"), "k: v")

        self.mock_redis.execute_command.return_value = True
        self.assertEqual(self.client.execute_command("EXISTS key"), "1")

        self.mock_redis.execute_command.return_value = None
        self.assertEqual(self.client.execute_command("GET missing"), "(nil)")

    def test_execute_command_rejects_select_for_cluster(self):
        client = RedisClient(use_cluster=True)
        client._client = MagicMock()

        self.assertEqual(client.execute_command("SELECT 1"), "(error) SELECT is not supported in Redis Cluster")
        client._client.execute_command.assert_not_called()

    def test_execute_command_formats_cluster_node_results(self):
        client = RedisClient(use_cluster=True)
        cluster_client = MagicMock()
        cluster_client.execute_command.return_value = {
            "127.0.0.1:7000": {"db0": {"keys": 2}, "role": "master"},
            "127.0.0.1:7001": {"db0": {"keys": 3}, "role": "master"},
        }
        client._client = cluster_client

        rendered = client.execute_command("INFO")

        self.assertIn("127.0.0.1:7000:", rendered)
        self.assertIn("db0:", rendered)
        self.assertIn("keys: 2", rendered)
        self.assertIn("role: master", rendered)

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

    # ── New: key_exists ─────────────────────────────────────────

    def test_key_exists_true(self):
        self.mock_redis.exists.return_value = 1
        self.assertTrue(self.client.key_exists("mykey"))
        self.mock_redis.exists.assert_called_once_with("mykey")

    def test_key_exists_false(self):
        self.mock_redis.exists.return_value = 0
        self.assertFalse(self.client.key_exists("missing"))

    # ── New: count methods ───────────────────────────────────────

    def test_get_list_count(self):
        self.mock_redis.llen.return_value = 42
        self.assertEqual(self.client.get_list_count("mykey"), 42)
        self.mock_redis.llen.assert_called_once_with("mykey")

    def test_get_hash_count(self):
        self.mock_redis.hlen.return_value = 10
        self.assertEqual(self.client.get_hash_count("mykey"), 10)
        self.mock_redis.hlen.assert_called_once_with("mykey")

    def test_get_set_count(self):
        self.mock_redis.scard.return_value = 7
        self.assertEqual(self.client.get_set_count("mykey"), 7)
        self.mock_redis.scard.assert_called_once_with("mykey")

    def test_get_zset_count(self):
        self.mock_redis.zcard.return_value = 5
        self.assertEqual(self.client.get_zset_count("mykey"), 5)
        self.mock_redis.zcard.assert_called_once_with("mykey")

    # ── New: display limits ──────────────────────────────────────

    def test_get_list_default_limit(self):
        """get_list() with default end should request at most DISPLAY_LIMIT rows."""
        self.mock_redis.lrange.return_value = ["v1"]
        self.client.get_list("mykey")
        self.mock_redis.lrange.assert_called_once_with("mykey", 0, self.client.DISPLAY_LIMIT - 1)

    def test_get_list_explicit_end(self):
        """Callers may override end to get a specific range."""
        self.mock_redis.lrange.return_value = ["v1", "v2"]
        self.client.get_list("mykey", start=0, end=9)
        self.mock_redis.lrange.assert_called_once_with("mykey", 0, 9)

    def test_get_zset_default_limit(self):
        self.mock_redis.zrange.return_value = [("v1", 1.0)]
        self.client.get_zset("mykey")
        self.mock_redis.zrange.assert_called_once_with(
            "mykey", 0, self.client.DISPLAY_LIMIT - 1, withscores=True
        )

    def test_get_hash_large_uses_hscan(self):
        """For hashes > DISPLAY_LIMIT, get_hash should use hscan (single page)."""
        self.mock_redis.hlen.return_value = self.client.DISPLAY_LIMIT + 100
        pairs = {f"f{i}": f"v{i}" for i in range(self.client.DISPLAY_LIMIT)}
        # hscan returns (next_cursor, dict_of_pairs)
        self.mock_redis.hscan.return_value = (0, pairs)
        result = self.client.get_hash("mykey")
        self.assertEqual(len(result), self.client.DISPLAY_LIMIT)
        self.mock_redis.hscan.assert_called_once_with("mykey", cursor=0, count=self.client.DISPLAY_LIMIT)
        self.mock_redis.hgetall.assert_not_called()

    def test_get_hash_page_returns_cursor_and_pairs(self):
        self.mock_redis.hscan.return_value = (7, {"f1": "v1"})
        cursor, pairs = self.client.get_hash_page("mykey", cursor=3, count=25)
        self.assertEqual(cursor, 7)
        self.assertEqual(pairs, {"f1": "v1"})
        self.mock_redis.hscan.assert_called_once_with("mykey", cursor=3, count=25)

    def test_get_set_large_uses_sscan(self):
        """For sets > DISPLAY_LIMIT, get_set should use sscan (single page)."""
        self.mock_redis.scard.return_value = self.client.DISPLAY_LIMIT + 50
        members = [f"m{i}" for i in range(self.client.DISPLAY_LIMIT)]
        # sscan returns (next_cursor, list_of_members)
        self.mock_redis.sscan.return_value = (0, members)
        result = self.client.get_set("mykey")
        self.assertEqual(len(result), self.client.DISPLAY_LIMIT)
        self.mock_redis.sscan.assert_called_once_with("mykey", cursor=0, count=self.client.DISPLAY_LIMIT)
        self.mock_redis.smembers.assert_not_called()

    def test_get_set_page_returns_cursor_and_members(self):
        self.mock_redis.sscan.return_value = (9, ["a", "b"])
        cursor, members = self.client.get_set_page("mykey", cursor=2, count=15)
        self.assertEqual(cursor, 9)
        self.assertEqual(members, ["a", "b"])
        self.mock_redis.sscan.assert_called_once_with("mykey", cursor=2, count=15)

    def test_execute_command_bool_false_returns_zero(self):
        """Boolean False (e.g. SETNX on existing key) should display as '0', not '(error)'."""
        self.mock_redis.execute_command.return_value = False
        self.assertEqual(self.client.execute_command("SETNX key val"), "0")


if __name__ == "__main__":
    unittest.main()
