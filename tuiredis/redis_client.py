"""Redis client wrapper for tuiredis."""

from __future__ import annotations

import redis


class RedisClient:
    """Manages Redis connection and provides high-level operations."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 6379,
        password: str | None = None,
        db: int = 0,
        use_cluster: bool = False,
        use_sentinel: bool = False,
        sentinel_nodes: str | None = None,
        sentinel_host: str | None = None,
        sentinel_port: int = 26379,
        sentinel_master_name: str | None = None,
        sentinel_password: str | None = None,
        ssh_host: str | None = None,
        ssh_port: int = 22,
        ssh_user: str | None = None,
        ssh_password: str | None = None,
        ssh_private_key: str | None = None,
    ):
        self.host = host
        self.port = port
        self.password = password
        self.db = db
        self.use_cluster = use_cluster
        self.use_sentinel = use_sentinel
        self.sentinel_nodes = sentinel_nodes
        self.sentinel_host = sentinel_host
        self.sentinel_port = sentinel_port
        self.sentinel_master_name = sentinel_master_name
        self.sentinel_password = sentinel_password

        # SSH configurations
        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.ssh_user = ssh_user
        self.ssh_password = ssh_password
        self.ssh_private_key = ssh_private_key

        self._client: redis.Redis | None = None
        self._ssh_tunnel = None
        self._cluster_scan_states: dict[str, dict[str, object]] = {}

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            raise ConnectionError("Not connected to Redis")
        return self._client

    def _should_retry_after_error(self, error: Exception) -> bool:
        if not self.use_sentinel:
            return False
        if isinstance(error, (redis.ConnectionError, redis.TimeoutError)):
            return True
        if isinstance(error, redis.ResponseError) and "READONLY" in str(error).upper():
            return True
        return False

    def _reconnect_for_retry(self) -> None:
        success, err_msg = self.connect()
        if not success:
            raise ConnectionError(err_msg or "Reconnect failed")

    def _call_with_retry(self, operation):
        try:
            return operation()
        except Exception as error:
            if not self._should_retry_after_error(error):
                raise
            self._reconnect_for_retry()
            return operation()

    def _get_sentinel_addresses(self) -> list[tuple[str, int]]:
        if self.sentinel_nodes:
            addresses: list[tuple[str, int]] = []
            for raw_node in self.sentinel_nodes.split(","):
                node = raw_node.strip()
                if not node:
                    continue
                if ":" in node:
                    host, port_str = node.rsplit(":", 1)
                    addresses.append((host.strip(), int(port_str.strip())))
                else:
                    addresses.append((node, self.sentinel_port))
            if addresses:
                return addresses
        return [(self.sentinel_host or "127.0.0.1", self.sentinel_port)]

    def connect(self) -> tuple[bool, str]:
        """Connect to Redis server, optionally through an SSH tunnel. Returns (success, error_msg)."""
        target_host = self.host
        target_port = self.port

        try:
            self._cluster_scan_states.clear()
            if self.use_cluster and self.use_sentinel:
                raise ValueError("Redis Cluster cannot be used together with Redis Sentinel")
            if self.use_cluster and self.ssh_host:
                raise ValueError("Redis Cluster is not supported together with SSH tunnel yet")
            if self.use_sentinel and self.ssh_host:
                raise ValueError("Redis Sentinel is not supported together with SSH tunnel yet")

            if self.use_cluster:
                from redis.cluster import RedisCluster

                self._client = RedisCluster(
                    host=self.host,
                    port=self.port,
                    password=self.password or None,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=10,
                )
                self._client.ping()
                return True, ""

            if self.use_sentinel:
                from redis.sentinel import Sentinel

                sentinel_kwargs = {
                    "socket_timeout": 10,
                    "socket_connect_timeout": 5,
                    "decode_responses": True,
                }
                if self.sentinel_password:
                    sentinel_kwargs["password"] = self.sentinel_password

                sentinel = Sentinel(
                    self._get_sentinel_addresses(),
                    sentinel_kwargs=sentinel_kwargs,
                )
                self._client = sentinel.master_for(
                    self.sentinel_master_name or "",
                    password=self.password or None,
                    db=self.db,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=10,
                )
                self._client.ping()
                return True, ""

            if self.ssh_host:
                # Workaround for sshtunnel <=0.4.0 breaking on paramiko >= 3.4.0
                import paramiko

                if not hasattr(paramiko, "DSSKey"):
                    paramiko.DSSKey = None

                from sshtunnel import SSHTunnelForwarder

                kwargs = {
                    "ssh_address_or_host": (self.ssh_host, self.ssh_port),
                    "ssh_username": self.ssh_user,
                    "remote_bind_address": (self.host, self.port),
                }
                if self.ssh_private_key:
                    kwargs["ssh_pkey"] = self.ssh_private_key
                if self.ssh_password:
                    kwargs["ssh_password"] = self.ssh_password

                self._ssh_tunnel = SSHTunnelForwarder(**kwargs)
                self._ssh_tunnel.start()

                target_host = "127.0.0.1"
                target_port = self._ssh_tunnel.local_bind_port

            self._client = redis.Redis(
                host=target_host,
                port=target_port,
                password=self.password or None,
                db=self.db,
                decode_responses=True,
                socket_connect_timeout=5,  # TCP handshake timeout (seconds)
                socket_timeout=10,          # read/write timeout after connect
            )
            self._client.ping()
            return True, ""
        except Exception as e:
            err_msg = str(e) or repr(e)
            self.disconnect()
            return False, err_msg

    def disconnect(self):
        """Close the Redis connection and SSH tunnel if active."""
        cluster_scan_states = getattr(self, "_cluster_scan_states", None)
        if isinstance(cluster_scan_states, dict):
            cluster_scan_states.clear()
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

        if self._ssh_tunnel:
            try:
                self._ssh_tunnel.stop()
            except Exception:
                pass
            self._ssh_tunnel = None

    @property
    def is_connected(self) -> bool:
        if self._client is None:
            return False
        try:
            self._call_with_retry(lambda: self._client.ping())
            return True
        except Exception:
            return False

    def switch_db(self, db_index: int) -> bool:
        """Switch to a different Redis database."""
        if self.use_cluster:
            return False
        try:
            self._call_with_retry(lambda: self.client.select(db_index))
            self.db = db_index
            return True
        except Exception:
            return False

    # ── Key Operations ───────────────────────────────────────────

    def scan_keys(self, pattern: str = "*", count: int = 500) -> list[str]:
        """Scan keys matching pattern using SCAN (non-blocking)."""
        if self.use_cluster:
            return sorted(self.scan_keys_paginated(cursor=0, pattern=pattern, count=count)[1])

        keys: list[str] = []
        cursor = 0
        while True:
            cursor, batch = self._call_with_retry(
                lambda current_cursor=cursor: self.client.scan(cursor=current_cursor, match=pattern, count=count)
            )
            keys.extend(batch)
            if cursor == 0:
                break
        return sorted(keys)

    def scan_keys_paginated(self, cursor: int = 0, pattern: str = "*", count: int = 2000) -> tuple[int, list[str]]:
        """Return at least `count` keys (or fewer if exhausted) and the next cursor."""
        if self.use_cluster:
            return self._scan_keys_paginated_cluster(cursor=cursor, pattern=pattern, count=count)

        result_keys: list[str] = []
        next_cursor = cursor

        # Redis SCAN COUNT is a hint; often returns fewer keys or even 0 keys per call.
        # Loop until we accumulate the requested amount or finish the scan.
        while len(result_keys) < count:
            request_count = max(
                count - len(result_keys), 10
            )  # slightly higher minimum to avoid spinning on small counts
            next_cursor, batch = self._call_with_retry(
                lambda current_cursor=next_cursor, current_count=request_count: self.client.scan(
                    cursor=current_cursor, match=pattern, count=current_count
                )
            )
            result_keys.extend(batch)
            if next_cursor == 0:
                break

        return next_cursor, result_keys

    def _scan_keys_paginated_cluster(self, cursor: int = 0, pattern: str = "*", count: int = 2000) -> tuple[int, list[str]]:
        state = self._cluster_scan_states.get(pattern)
        if state is None or cursor == 0 or cursor != state.get("offset", 0):
            state = {
                "iterator": self.client.scan_iter(match=pattern, count=count),
                "buffer": [],
                "offset": 0,
            }
            self._cluster_scan_states[pattern] = state
            if cursor > 0:
                self._advance_cluster_iterator(state, cursor)

        result_keys = self._consume_cluster_iterator(state, count + 1)
        has_more = len(result_keys) > count
        if has_more:
            state["buffer"] = [result_keys.pop()]
        else:
            state["buffer"] = []

        state["offset"] = int(state.get("offset", 0)) + len(result_keys)
        next_cursor = int(state["offset"]) if has_more else 0
        if not has_more:
            self._cluster_scan_states.pop(pattern, None)
        return next_cursor, result_keys

    def _advance_cluster_iterator(self, state: dict[str, object], items_to_skip: int) -> None:
        skipped = 0
        while skipped < items_to_skip:
            batch = self._consume_cluster_iterator(state, items_to_skip - skipped)
            if not batch:
                break
            skipped += len(batch)
        state["offset"] = skipped

    def _consume_cluster_iterator(self, state: dict[str, object], limit: int) -> list[str]:
        iterator = state["iterator"]
        buffer = list(state.get("buffer", []))
        result: list[str] = []

        while buffer and len(result) < limit:
            result.append(buffer.pop(0))

        while len(result) < limit:
            try:
                result.append(next(iterator))  # type: ignore[arg-type]
            except StopIteration:
                break

        state["buffer"] = buffer
        return result

    def get_type(self, key: str) -> str:
        """Return the Redis type of a key."""
        return self._call_with_retry(lambda: self.client.type(key))  # type: ignore[return-value]

    def get_types(self, keys: list[str]) -> dict[str, str]:
        """Return types for multiple keys efficiently using a pipeline."""
        if not keys:
            return {}
        if self.use_cluster:
            return {key: self.get_type(key) for key in keys}
        pipeline = self.client.pipeline(transaction=False)
        for key in keys:
            pipeline.type(key)
        types = self._call_with_retry(pipeline.execute)
        return dict(zip(keys, types, strict=False))

    def get_ttl(self, key: str) -> int:
        """Return TTL in seconds. -1 = no expiry, -2 = key missing."""
        return self._call_with_retry(lambda: self.client.ttl(key))  # type: ignore[return-value]

    def get_encoding(self, key: str) -> str:
        """Return internal encoding of a key."""
        result = self._call_with_retry(lambda: self.client.object("encoding", key))
        return str(result) if result else "unknown"

    def get_memory_usage(self, key: str) -> int | None:
        """Return approximate memory usage in bytes."""
        try:
            return self._call_with_retry(lambda: self.client.memory_usage(key))  # type: ignore[return-value]
        except Exception:
            return None

    def delete_key(self, key: str) -> bool:
        """Delete a key. Returns True if the key was deleted."""
        return self._call_with_retry(lambda: self.client.delete(key)) > 0

    def rename_key(self, old_key: str, new_key: str) -> bool:
        try:
            self._call_with_retry(lambda: self.client.rename(old_key, new_key))
            return True
        except redis.ResponseError:
            return False

    def key_exists(self, key: str) -> bool:
        """Return True if the key exists in Redis."""
        return bool(self._call_with_retry(lambda: self.client.exists(key)))

    def get_ttls(self, keys: list[str]) -> dict[str, int]:
        """Return TTL for each key via a pipeline. -1 = no expiry, -2 = missing."""
        if not keys:
            return {}
        if self.use_cluster:
            return {key: self.get_ttl(key) for key in keys}
        pipeline = self.client.pipeline(transaction=False)
        for key in keys:
            pipeline.ttl(key)
        results = self._call_with_retry(pipeline.execute)
        return dict(zip(keys, results, strict=False))

    def delete_keys_batch(self, keys: list[str]) -> int:
        """Delete multiple keys atomically. Returns number of keys deleted."""
        if not keys:
            return 0
        return self._call_with_retry(lambda: self.client.delete(*keys))  # type: ignore[return-value]

    def set_ttl(self, key: str, ttl: int) -> bool:
        """Set TTL on a key. Use -1 to remove expiry."""
        if ttl < 0:
            return self._call_with_retry(lambda: self.client.persist(key))  # type: ignore[return-value]
        return self._call_with_retry(lambda: self.client.expire(key, ttl))  # type: ignore[return-value]

    # ── Value Operations ─────────────────────────────────────────

    def get_string(self, key: str) -> str | None:
        return self._call_with_retry(lambda: self.client.get(key))  # type: ignore[return-value]

    def set_string(self, key: str, value: str, ttl: int | None = None):
        self._call_with_retry(lambda: self.client.set(key, value, ex=ttl if ttl and ttl > 0 else None))

    # Maximum number of collection elements shown in the value viewer at once.
    # This protects the UI against blocking on very large keys.
    DISPLAY_LIMIT = 500

    def get_list(self, key: str, start: int = 0, end: int = -1) -> list[str]:
        if end == -1:
            end = self.DISPLAY_LIMIT - 1
        return self._call_with_retry(lambda: self.client.lrange(key, start, end))  # type: ignore[return-value]

    def get_list_count(self, key: str) -> int:
        return self._call_with_retry(lambda: self.client.llen(key))  # type: ignore[return-value]

    def list_push(self, key: str, *values: str):
        self._call_with_retry(lambda: self.client.rpush(key, *values))

    def list_set(self, key: str, index: int, value: str):
        self._call_with_retry(lambda: self.client.lset(key, index, value))

    def list_remove(self, key: str, value: str, count: int = 1):
        self._call_with_retry(lambda: self.client.lrem(key, count, value))

    def list_delete_by_index(self, key: str, index: int) -> None:
        """Delete the element at `index` from a list without touching duplicate values.

        Strategy: LSET the position to a unique tombstone, then LREM 1 occurrence.
        """
        tombstone = "__TUIREDIS_DEL_TOMBSTONE__"
        self._call_with_retry(lambda: self.client.lset(key, index, tombstone))
        self._call_with_retry(lambda: self.client.lrem(key, 1, tombstone))

    def get_hash(self, key: str) -> dict[str, str]:
        count = self._call_with_retry(lambda: self.client.hlen(key))
        if count <= self.DISPLAY_LIMIT:
            return self._call_with_retry(lambda: self.client.hgetall(key))  # type: ignore[return-value]
        result: dict[str, str] = {}
        _, pairs = self._call_with_retry(lambda: self.client.hscan(key, cursor=0, count=self.DISPLAY_LIMIT))
        result.update(pairs)
        return result

    def get_hash_page(self, key: str, cursor: int = 0, count: int | None = None) -> tuple[int, dict[str, str]]:
        """Return a hash page and next cursor using HSCAN."""
        if count is None:
            count = self.DISPLAY_LIMIT
        next_cursor, pairs = self._call_with_retry(lambda: self.client.hscan(key, cursor=cursor, count=count))
        return int(next_cursor), dict(pairs)

    def scan_hash(self, key: str, cursor: int = 0, count: int = 500) -> tuple[int, dict[str, str]]:
        """Return (next_cursor, {field: value}) using HSCAN.
        cursor=0 to start; returns cursor=0 when scan is complete.
        """
        next_cursor, pairs = self._call_with_retry(lambda: self.client.hscan(key, cursor=cursor, count=count))
        return int(next_cursor), dict(pairs)

    def get_hash_count(self, key: str) -> int:
        return self._call_with_retry(lambda: self.client.hlen(key))  # type: ignore[return-value]

    def hash_set(self, key: str, field: str, value: str):
        self._call_with_retry(lambda: self.client.hset(key, field, value))

    def hash_delete(self, key: str, *fields: str):
        self._call_with_retry(lambda: self.client.hdel(key, *fields))

    def get_set(self, key: str) -> set[str]:
        count = self._call_with_retry(lambda: self.client.scard(key))
        if count <= self.DISPLAY_LIMIT:
            return self._call_with_retry(lambda: self.client.smembers(key))  # type: ignore[return-value]
        result: set[str] = set()
        _, members = self._call_with_retry(lambda: self.client.sscan(key, cursor=0, count=self.DISPLAY_LIMIT))
        result.update(members)
        return result

    def get_set_page(self, key: str, cursor: int = 0, count: int | None = None) -> tuple[int, list[str]]:
        """Return a set page and next cursor using SSCAN."""
        if count is None:
            count = self.DISPLAY_LIMIT
        next_cursor, members = self._call_with_retry(lambda: self.client.sscan(key, cursor=cursor, count=count))
        return int(next_cursor), list(members)

    def scan_set(self, key: str, cursor: int = 0, count: int = 500) -> tuple[int, list[str]]:
        """Return (next_cursor, [member, ...]) using SSCAN."""
        next_cursor, members = self._call_with_retry(lambda: self.client.sscan(key, cursor=cursor, count=count))
        return int(next_cursor), list(members)

    def get_set_count(self, key: str) -> int:
        return self._call_with_retry(lambda: self.client.scard(key))  # type: ignore[return-value]

    def set_add(self, key: str, *members: str):
        self._call_with_retry(lambda: self.client.sadd(key, *members))

    def set_remove(self, key: str, *members: str):
        self._call_with_retry(lambda: self.client.srem(key, *members))

    def get_zset(self, key: str, start: int = 0, end: int = -1) -> list[tuple[str, float]]:
        if end == -1:
            end = self.DISPLAY_LIMIT - 1
        return self._call_with_retry(lambda: self.client.zrange(key, start, end, withscores=True))  # type: ignore[return-value]

    def get_zset_count(self, key: str) -> int:
        return self._call_with_retry(lambda: self.client.zcard(key))  # type: ignore[return-value]

    def zset_add(self, key: str, member: str, score: float):
        self._call_with_retry(lambda: self.client.zadd(key, {member: score}))

    def zset_remove(self, key: str, *members: str):
        self._call_with_retry(lambda: self.client.zrem(key, *members))

    # ── Server Info ──────────────────────────────────────────────

    def get_server_info(self) -> dict:
        """Return parsed Redis INFO output."""
        info = self._call_with_retry(lambda: self.client.info())  # type: ignore[assignment]
        if self.use_cluster:
            return self._aggregate_cluster_info(info)
        return info  # type: ignore[return-value]

    def get_keyspace_info(self) -> dict[int, int]:
        """Return a mapping of db_index to key count."""
        try:
            info = self._call_with_retry(lambda: self.client.info("keyspace"))
            if self.use_cluster:
                return self._aggregate_cluster_keyspace(info)
            result = {}
            for key, val in info.items():
                if key.startswith("db"):
                    try:
                        db_idx = int(key[2:])
                        if isinstance(val, dict):
                            result[db_idx] = val.get("keys", 0)
                    except ValueError:
                        pass
            return result
        except Exception:
            return {}

    def get_database_count(self) -> int:
        """Return the configured number of logical databases."""
        if self.use_cluster:
            return 1

        try:
            config = self._call_with_retry(lambda: self.client.config_get("databases"))
            raw_value = config.get("databases")
            if raw_value is not None:
                count = int(raw_value)
                if count > 0:
                    return count
        except Exception:
            pass

        keyspace = self.get_keyspace_info()
        if keyspace:
            return max(keyspace) + 1
        return max(self.db + 1, 16)

    def get_db_size(self) -> int:
        size = self._call_with_retry(lambda: self.client.dbsize())
        if self.use_cluster and isinstance(size, dict):
            return sum(int(node_size or 0) for node_size in size.values())
        return size  # type: ignore[return-value]

    @staticmethod
    def _format_bytes(num_bytes: int) -> str:
        units = ["B", "KB", "MB", "GB", "TB", "PB"]
        size = float(max(num_bytes, 0))
        unit = units[0]
        for unit in units:
            if size < 1024 or unit == units[-1]:
                break
            size /= 1024
        if unit == "B":
            return f"{int(size)}B"
        return f"{size:.1f}{unit}"

    def _aggregate_cluster_info(self, info: dict) -> dict:
        node_infos = [node_info for node_info in info.values() if isinstance(node_info, dict)]
        if not node_infos:
            return info

        sample = node_infos[0]
        aggregated: dict[str, object] = {
            "redis_mode": "cluster",
            "cluster_nodes": len(node_infos),
        }
        for field in ["redis_version", "os", "role"]:
            if field in sample:
                aggregated[field] = sample[field]

        numeric_sums = {
            "connected_clients": 0,
            "blocked_clients": 0,
            "tracking_clients": 0,
            "total_connections_received": 0,
            "total_commands_processed": 0,
            "instantaneous_ops_per_sec": 0,
            "keyspace_hits": 0,
            "keyspace_misses": 0,
            "used_memory": 0,
            "used_memory_peak": 0,
            "maxmemory": 0,
        }
        fragmentation_values: list[float] = []
        uptime_days = 0

        for node_info in node_infos:
            for field in numeric_sums:
                raw_value = node_info.get(field, 0)
                try:
                    numeric_sums[field] += int(raw_value or 0)
                except (TypeError, ValueError):
                    pass
            try:
                uptime_days = max(uptime_days, int(node_info.get("uptime_in_days", 0) or 0))
            except (TypeError, ValueError):
                pass
            try:
                fragmentation_values.append(float(node_info.get("mem_fragmentation_ratio", 0) or 0))
            except (TypeError, ValueError):
                pass

        aggregated["uptime_in_days"] = uptime_days
        aggregated["used_memory_human"] = self._format_bytes(numeric_sums["used_memory"])
        aggregated["used_memory_peak_human"] = self._format_bytes(numeric_sums["used_memory_peak"])
        aggregated["maxmemory_human"] = self._format_bytes(numeric_sums["maxmemory"])
        aggregated["mem_fragmentation_ratio"] = (
            round(sum(fragmentation_values) / len(fragmentation_values), 2) if fragmentation_values else 0
        )

        for field in [
            "connected_clients",
            "blocked_clients",
            "tracking_clients",
            "total_connections_received",
            "total_commands_processed",
            "instantaneous_ops_per_sec",
            "keyspace_hits",
            "keyspace_misses",
        ]:
            aggregated[field] = numeric_sums[field]

        for db_idx, key_count in self._aggregate_cluster_keyspace(info).items():
            aggregated[f"db{db_idx}"] = {"keys": key_count}

        return aggregated

    @staticmethod
    def _aggregate_cluster_keyspace(info: dict) -> dict[int, int]:
        totals: dict[int, int] = {}
        node_infos = info.values() if info and all(isinstance(v, dict) for v in info.values()) else [info]
        for node_info in node_infos:
            if not isinstance(node_info, dict):
                continue
            for key, val in node_info.items():
                if not isinstance(key, str) or not key.startswith("db"):
                    continue
                try:
                    db_idx = int(key[2:])
                except ValueError:
                    continue
                if isinstance(val, dict):
                    try:
                        totals[db_idx] = totals.get(db_idx, 0) + int(val.get("keys", 0) or 0)
                    except (TypeError, ValueError):
                        continue
        return totals

    def execute_command(self, command_str: str) -> str:
        """Execute a raw Redis command string and return the result."""
        parts = command_str.strip().split()
        if not parts:
            return ""
        cmd = parts[0].upper()
        args = parts[1:]
        if getattr(self, "use_cluster", False) and cmd == "SELECT":
            return "(error) SELECT is not supported in Redis Cluster"
        try:
            result = self._call_with_retry(lambda: self.client.execute_command(cmd, *args))
            return self._format_command_result(result)
        except redis.ResponseError as e:
            return f"(error) {e}"
        except Exception as e:
            return f"(error) {e}"

    def _format_command_result(self, result, indent: int = 0) -> str:
        if result is None:
            return "(nil)"
        if isinstance(result, bool):
            return "1" if result else "0"
        if isinstance(result, bytes):
            return result.decode("utf-8", errors="replace")
        if isinstance(result, (list, tuple)):
            if not result:
                return "(empty list)"
            prefix = " " * indent
            lines = []
            for i, item in enumerate(result, 1):
                formatted = self._format_command_result(item, indent + 2)
                if "\n" in formatted:
                    lines.append(f"{prefix}{i})")
                    lines.append(formatted)
                else:
                    lines.append(f"{prefix}{i}) {formatted}")
            return "\n".join(lines)
        if isinstance(result, dict):
            prefix = " " * indent
            lines = []
            for key, value in result.items():
                rendered_key = self._format_command_result(key)
                formatted = self._format_command_result(value, indent + 2)
                if "\n" in formatted:
                    lines.append(f"{prefix}{rendered_key}:")
                    lines.append(formatted)
                else:
                    lines.append(f"{prefix}{rendered_key}: {formatted}")
            return "\n".join(lines)
        return str(result)

    @property
    def connection_label(self) -> str:
        """Human-readable connection string."""
        auth = "🔒" if self.password else ""
        return f"{auth}{self.host}:{self.port}/db{self.db}"
