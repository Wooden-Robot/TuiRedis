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

        # SSH configurations
        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.ssh_user = ssh_user
        self.ssh_password = ssh_password
        self.ssh_private_key = ssh_private_key

        self._client: redis.Redis | None = None
        self._ssh_tunnel = None

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            raise ConnectionError("Not connected to Redis")
        return self._client

    def connect(self) -> tuple[bool, str]:
        """Connect to Redis server, optionally through an SSH tunnel. Returns (success, error_msg)."""
        target_host = self.host
        target_port = self.port

        try:
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
                socket_connect_timeout=5,
            )
            self._client.ping()
            return True, ""
        except Exception as e:
            err_msg = str(e) or repr(e)
            self.disconnect()
            return False, err_msg

    def disconnect(self):
        """Close the Redis connection and SSH tunnel if active."""
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
            self._client.ping()
            return True
        except Exception:
            return False

    def switch_db(self, db_index: int) -> bool:
        """Switch to a different Redis database."""
        try:
            self.client.select(db_index)
            self.db = db_index
            return True
        except Exception:
            return False

    # ── Key Operations ───────────────────────────────────────────

    def scan_keys(self, pattern: str = "*", count: int = 500) -> list[str]:
        """Scan keys matching pattern using SCAN (non-blocking)."""
        keys: list[str] = []
        cursor = 0
        while True:
            cursor, batch = self.client.scan(cursor=cursor, match=pattern, count=count)
            keys.extend(batch)
            if cursor == 0:
                break
        return sorted(keys)

    def scan_keys_paginated(self, cursor: int = 0, pattern: str = "*", count: int = 2000) -> tuple[int, list[str]]:
        """Return at least `count` keys (or fewer if exhausted) and the next cursor."""
        result_keys: list[str] = []
        next_cursor = cursor

        # Redis SCAN COUNT is a hint; often returns fewer keys or even 0 keys per call.
        # Loop until we accumulate the requested amount or finish the scan.
        while len(result_keys) < count:
            request_count = max(count - len(result_keys), 10)  # slightly higher minimum to avoid spinning on small counts
            next_cursor, batch = self.client.scan(cursor=next_cursor, match=pattern, count=request_count)
            result_keys.extend(batch)
            if next_cursor == 0:
                break

        return next_cursor, result_keys

    def get_type(self, key: str) -> str:
        """Return the Redis type of a key."""
        return self.client.type(key)  # type: ignore[return-value]

    def get_types(self, keys: list[str]) -> dict[str, str]:
        """Return types for multiple keys efficiently using a pipeline."""
        if not keys:
            return {}
        pipeline = self.client.pipeline(transaction=False)
        for key in keys:
            pipeline.type(key)
        types = pipeline.execute()
        return dict(zip(keys, types, strict=False))

    def get_ttl(self, key: str) -> int:
        """Return TTL in seconds. -1 = no expiry, -2 = key missing."""
        return self.client.ttl(key)  # type: ignore[return-value]

    def get_encoding(self, key: str) -> str:
        """Return internal encoding of a key."""
        result = self.client.object("encoding", key)
        return str(result) if result else "unknown"

    def get_memory_usage(self, key: str) -> int | None:
        """Return approximate memory usage in bytes."""
        try:
            return self.client.memory_usage(key)  # type: ignore[return-value]
        except Exception:
            return None

    def delete_key(self, key: str) -> bool:
        """Delete a key. Returns True if the key was deleted."""
        return self.client.delete(key) > 0

    def rename_key(self, old_name: str, new_name: str) -> bool:
        """Rename a key."""
        try:
            self.client.rename(old_name, new_name)
            return True
        except redis.ResponseError:
            return False

    def set_ttl(self, key: str, ttl: int) -> bool:
        """Set TTL on a key. Use -1 to remove expiry."""
        if ttl < 0:
            return self.client.persist(key)  # type: ignore[return-value]
        return self.client.expire(key, ttl)  # type: ignore[return-value]

    # ── Value Operations ─────────────────────────────────────────

    def get_string(self, key: str) -> str | None:
        return self.client.get(key)  # type: ignore[return-value]

    def set_string(self, key: str, value: str, ttl: int | None = None):
        self.client.set(key, value, ex=ttl if ttl and ttl > 0 else None)

    def get_list(self, key: str, start: int = 0, end: int = -1) -> list[str]:
        return self.client.lrange(key, start, end)  # type: ignore[return-value]

    def list_push(self, key: str, *values: str):
        self.client.rpush(key, *values)

    def list_set(self, key: str, index: int, value: str):
        self.client.lset(key, index, value)

    def list_remove(self, key: str, value: str, count: int = 1):
        self.client.lrem(key, count, value)

    def get_hash(self, key: str) -> dict[str, str]:
        return self.client.hgetall(key)  # type: ignore[return-value]

    def hash_set(self, key: str, field: str, value: str):
        self.client.hset(key, field, value)

    def hash_delete(self, key: str, *fields: str):
        self.client.hdel(key, *fields)

    def get_set(self, key: str) -> set[str]:
        return self.client.smembers(key)  # type: ignore[return-value]

    def set_add(self, key: str, *members: str):
        self.client.sadd(key, *members)

    def set_remove(self, key: str, *members: str):
        self.client.srem(key, *members)

    def get_zset(self, key: str, start: int = 0, end: int = -1) -> list[tuple[str, float]]:
        return self.client.zrange(key, start, end, withscores=True)  # type: ignore[return-value]

    def zset_add(self, key: str, member: str, score: float):
        self.client.zadd(key, {member: score})

    def zset_remove(self, key: str, *members: str):
        self.client.zrem(key, *members)

    # ── Server Info ──────────────────────────────────────────────

    def get_server_info(self) -> dict:
        """Return parsed Redis INFO output."""
        return self.client.info()  # type: ignore[return-value]

    def get_keyspace_info(self) -> dict[int, int]:
        """Return a mapping of db_index to key count."""
        try:
            info = self.client.info("keyspace")
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

    def get_db_size(self) -> int:
        return self.client.dbsize()  # type: ignore[return-value]

    def execute_command(self, command_str: str) -> str:
        """Execute a raw Redis command string and return the result."""
        parts = command_str.strip().split()
        if not parts:
            return ""
        cmd = parts[0].upper()
        args = parts[1:]
        try:
            result = self.client.execute_command(cmd, *args)
            if result is None:
                return "(nil)"
            if isinstance(result, (list, tuple)):
                if not result:
                    return "(empty list)"
                lines = []
                for i, item in enumerate(result, 1):
                    lines.append(f"{i}) {item}")
                return "\n".join(lines)
            if isinstance(result, dict):
                lines = []
                for k, v in result.items():
                    lines.append(f"{k}: {v}")
                return "\n".join(lines)
            if isinstance(result, bool):
                return "OK" if result else "(error)"
            if isinstance(result, bytes):
                return result.decode("utf-8", errors="replace")
            return str(result)
        except redis.ResponseError as e:
            return f"(error) {e}"
        except Exception as e:
            return f"(error) {e}"

    @property
    def connection_label(self) -> str:
        """Human-readable connection string."""
        auth = "🔒" if self.password else ""
        return f"{auth}{self.host}:{self.port}/db{self.db}"
