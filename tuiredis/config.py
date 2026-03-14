"""Configuration manager for TRedis."""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import TypedDict, cast

logger = logging.getLogger(__name__)


class ConnectionProfile(TypedDict, total=False):
    """Represents a saved Redis connection configuration."""

    id: str
    name: str
    host: str
    port: int
    db: int
    password: str | None
    save_secrets: bool
    use_cluster: bool
    use_sentinel: bool
    sentinel_nodes: str | None
    sentinel_host: str | None
    sentinel_port: int
    sentinel_master_name: str | None
    sentinel_password: str | None

    # SSH fields
    use_ssh: bool
    ssh_host: str | None
    ssh_port: int
    ssh_user: str | None
    ssh_password: str | None
    ssh_private_key: str | None


def get_config_dir() -> Path:
    """Return the configuration directory, creating it if necessary."""
    config_dir = Path.home() / ".tuiredis"
    if not config_dir.exists():
        try:
            config_dir.mkdir(parents=True, exist_ok=True)
            # Ensure the directory is private (read/write/execute by owner only)
            config_dir.chmod(0o700)
        except Exception as e:
            logger.error(f"Failed to create config directory: {e}")
    return config_dir


def get_connections_file() -> Path:
    """Return the path to the connections.json file."""
    return get_config_dir() / "connections.json"


def load_connections() -> list[ConnectionProfile]:
    """Load connection profiles from disk."""
    config_file = get_connections_file()
    if not config_file.exists():
        return []

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return cast(list[ConnectionProfile], data)
            return []
    except Exception as e:
        logger.error(f"Failed to load connections configuration: {e}")
        return []


def save_connection(profile: ConnectionProfile) -> tuple[ConnectionProfile, list[ConnectionProfile], bool]:
    """Save a connection profile. If it lacks an ID, generate one.
    Updates existing profiles with the same ID.
    If no ID is passed, checks for existing profiles with the same connection details to update instead of duplicate.
    Returns a tuple of (saved_profile, updated_list_of_profiles, persisted).
    """
    config_file = get_connections_file()
    connections = load_connections()

    # Ensure profile has a name
    if not profile.get("name"):
        profile["name"] = f"{profile.get('host', '127.0.0.1')}:{profile.get('port', 6379)}"

    # Check for deduplication if no ID is provided
    if not profile.get("id"):
        for conn in connections:
            if (
                conn.get("host") == profile.get("host")
                and conn.get("port") == profile.get("port")
                and conn.get("db") == profile.get("db")
                and conn.get("password") == profile.get("password")
                and conn.get("use_cluster") == profile.get("use_cluster")
                and conn.get("use_sentinel") == profile.get("use_sentinel")
                and conn.get("sentinel_nodes") == profile.get("sentinel_nodes")
                and conn.get("sentinel_host") == profile.get("sentinel_host")
                and conn.get("sentinel_port") == profile.get("sentinel_port")
                and conn.get("sentinel_master_name") == profile.get("sentinel_master_name")
                and conn.get("sentinel_password") == profile.get("sentinel_password")
                and conn.get("use_ssh") == profile.get("use_ssh")
                and conn.get("ssh_host") == profile.get("ssh_host")
                and conn.get("ssh_port") == profile.get("ssh_port")
                and conn.get("ssh_user") == profile.get("ssh_user")
                and conn.get("ssh_password") == profile.get("ssh_password")
                and conn.get("ssh_private_key") == profile.get("ssh_private_key")
            ):
                # Found exact same connection details, update this one instead of creating new
                profile["id"] = conn.get("id", str(uuid.uuid4()))
                break

    # If still no ID, generate one
    if not profile.get("id"):
        profile["id"] = str(uuid.uuid4())

    # Find and update, or append
    updated = False
    for i, conn in enumerate(connections):
        if conn.get("id") == profile["id"]:
            connections[i] = profile
            updated = True
            break

    if not updated:
        connections.append(profile)

    temp_file = config_file.with_suffix(".tmp")
    try:
        # Create a temporary file, write data, set permissions, then rename
        # This prevents permission race conditions on new files
        with temp_file.open("w", encoding="utf-8") as f:
            json.dump(connections, f, indent=2)
        temp_file.chmod(0o600)  # Read/write by owner only
        os.replace(temp_file, config_file)
    except Exception as e:
        logger.error(f"Failed to save connections configuration: {e}")
        try:
            temp_file.unlink(missing_ok=True)
        except OSError:
            pass

        return profile, connections, False

    return profile, connections, True


def delete_connection(profile_id: str) -> tuple[list[ConnectionProfile], bool]:
    """Delete a connection profile by ID. Returns (updated_list, persisted)."""
    config_file = get_connections_file()
    connections = load_connections()

    connections = [c for c in connections if c.get("id") != profile_id]

    temp_file = config_file.with_suffix(".tmp")
    try:
        with temp_file.open("w", encoding="utf-8") as f:
            json.dump(connections, f, indent=2)
        temp_file.chmod(0o600)
        os.replace(temp_file, config_file)
    except Exception as e:
        logger.error(f"Failed to save connections configuration after deletion: {e}")
        try:
            temp_file.unlink(missing_ok=True)
        except OSError:
            pass

        return connections, False

    return connections, True
