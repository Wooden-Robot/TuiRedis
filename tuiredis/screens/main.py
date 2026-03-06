"""Main screen — primary workspace after connecting to Redis."""

from __future__ import annotations

import fnmatch
import os
import subprocess
import sys

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Select, Static, TabbedContent, TabPane

from tuiredis.screens.new_key_modal import NewKeyModal
from tuiredis.widgets.command_input import CommandInput
from tuiredis.widgets.key_detail import KeyDetail
from tuiredis.widgets.key_tree import KeyTree
from tuiredis.widgets.server_info import ServerInfo
from tuiredis.widgets.value_viewer import ValueViewer


class MainScreen(Screen):
    """Main workspace screen with key browser, value viewer, and console."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._virtual_keys: dict[str, str] = {}

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Prevent priority bindings from quitting when typing in an Input."""
        if action in ("quit", "switch_connection"):
            if isinstance(self.app.focused, Input):
                return False
        return True

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("ctrl+o", "switch_connection", "Switch Connection", priority=True),
        Binding("f5", "refresh", "Refresh"),
        Binding("slash", "focus_search", "Search", key_display="/"),
        Binding("n", "new_key", "New Key"),
        Binding("ctrl+i", "toggle_info", "Server Info"),
        Binding("ctrl+t", "open_iredis", "IRedis Terminal"),
        Binding("ctrl+d", "bulk_delete", "Bulk Delete", show=False),
    ]

    DEFAULT_CSS = """
    MainScreen {
        layout: grid;
        grid-size: 1;
        grid-rows: 1fr auto;
    }
    #main-body {
        height: 1fr;
    }
    #left-panel {
        width: 32;
        min-width: 24;
        border-right: tall $surface-lighten-2;
    }
    #left-panel #db-select {
        margin: 0;
        height: auto;
        border: none;
        border-bottom: tall $surface-lighten-2;
    }
    #search-row {
        height: auto;
        border-bottom: tall $surface-lighten-2;
    }
    #search-row #search-box {
        width: 1fr;
        border: none;
        border-right: tall $surface-lighten-2;
        margin: 0;
    }
    #search-row #limit-box {
        width: 10;
        border: none;
        margin: 0;
    }
    #left-panel #key-tree {
        height: 1fr;
    }
    #center-panel {
        width: 1fr;
    }
    #right-panel {
        width: 30;
        min-width: 24;
        border-left: tall $surface-lighten-2;
    }
    #bottom-panel {
        height: 14;
        border-top: tall $surface-lighten-2;
    }
    #status-bar {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 2;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main-body"):
            with Vertical(id="left-panel"):
                db_opts = [(f"DB {i}", str(i)) for i in range(16)]
                yield Select(db_opts, value="0", id="db-select", allow_blank=False)
                with Horizontal(id="search-row"):
                    yield Input(placeholder="🔍 Search...", id="search-box")
                    yield Input(value="2000", id="limit-box", type="integer")
                yield KeyTree(id="key-tree")
            with TabbedContent(id="center-panel"):
                with TabPane("📄 Value", id="tab-value"):
                    yield ValueViewer(id="value-viewer")
                with TabPane("📊 Server Info", id="tab-info"):
                    yield ServerInfo(id="server-info")
            with Vertical(id="right-panel"):
                yield KeyDetail(id="key-detail")
        with Vertical(id="bottom-panel"):
            yield CommandInput(id="command-input")
        yield Static("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        """Load keys on mount."""
        client = self._get_client()
        db_select = self.query_one("#db-select", Select)
        db_select.value = str(client.db)

        self._load_keys()
        self._load_server_info()

    def _get_client(self):
        return self.app.redis_client  # type: ignore[attr-defined]

    def refresh_connection(self) -> None:
        """Reset the UI state for a new Redis connection."""
        if not self.is_mounted:
            return

        client = self._get_client()
        db_select = self.query_one("#db-select", Select)

        # Prevent the change event from triggering a DB switch since we are already connected
        with db_select.prevent(Select.Changed):
            db_select.value = str(client.db)

        self.query_one("#value-viewer", ValueViewer).show_empty()
        self._virtual_keys.clear()  # stale virtual keys don't apply to new connection

        # Reset pagination/search
        tree = self.query_one("#key-tree", KeyTree)
        tree._next_cursor = 0

        self._load_keys()
        self._load_server_info()

    # ── Key Loading ──────────────────────────────────────────────

    def _get_page_limit(self) -> int:
        try:
            val = self.query_one("#limit-box", Input).value
            if not val:
                return 2000
            limit = int(val)
            return max(10, min(limit, 1000000))
        except Exception:
            return 2000

    def _load_keys(self, pattern: str | None = None) -> None:
        if pattern is not None:
            self._current_pattern = pattern
        elif not hasattr(self, "_current_pattern"):
            self._current_pattern = "*"

        client = self._get_client()
        next_cursor, keys = client.scan_keys_paginated(
            cursor=0, pattern=self._current_pattern, count=self._get_page_limit()
        )

        for v_key in self._virtual_keys:
            if fnmatch.fnmatch(v_key, self._current_pattern):
                if v_key not in keys:
                    keys.append(v_key)

        # Get types for all keys (optimized batch)
        key_types = client.get_types(keys)

        for v_key, v_type in self._virtual_keys.items():
            if v_key in keys and key_types.get(v_key, "none") == "none":
                key_types[v_key] = v_type

        # Fetch TTLs for expiry indicators (limit to 2000 to avoid stalling)
        ttl_sample = keys[:2000]
        try:
            ttl_map = client.get_ttls(ttl_sample)
        except Exception:
            ttl_map = {}

        tree = self.query_one("#key-tree", KeyTree)
        tree.load_keys(keys, key_types, next_cursor=next_cursor, ttl_map=ttl_map)
        self._load_db_options()

    def _load_db_options(self):
        client = self._get_client()
        keyspace = client.get_keyspace_info()
        db_opts = []
        for i in range(16):
            count = keyspace.get(i, 0)
            if count > 0:
                label = f"DB {i} ({count})"
            else:
                label = f"DB {i}"
            db_opts.append((label, str(i)))

        try:
            select = self.query_one("#db-select", Select)
            current_val = select.value

            with select.prevent(Select.Changed):
                select.set_options(db_opts)
                if current_val:
                    select.value = current_val
        except Exception:
            pass

    def _load_server_info(self):
        client = self._get_client()
        try:
            info = client.get_server_info()
            self.query_one("#server-info", ServerInfo).update_info(info)
        except Exception:
            pass

    # ── Actions ──────────────────────────────────────────────────

    def action_refresh(self) -> None:
        self._load_keys()
        self._load_server_info()
        self.notify("🔄 Refreshed", timeout=2)

    def action_focus_search(self) -> None:
        self.query_one("#search-box", Input).focus()

    def action_new_key(self) -> None:
        self.app.push_screen(NewKeyModal(), self._on_new_key_created)

    def _on_new_key_created(self, result) -> None:
        """Callback from NewKeyModal — result is KeyCreated or None (cancelled)."""
        if result is None:
            return
        key = result.key
        key_type = result.key_type
        if not result.wrote_to_redis:
            self._virtual_keys[key] = key_type
        self._load_keys()
        self.notify(f"✨ Created {key_type} key: {key}", timeout=2)
        self.query_one("#key-tree", KeyTree).post_message(KeyTree.KeySelected(key))

    def action_toggle_info(self) -> None:
        tabs = self.query_one("#center-panel", TabbedContent)
        tabs.active = "tab-info" if tabs.active != "tab-info" else "tab-value"

    def action_open_iredis(self) -> None:
        """Launch iredis terminal."""
        self._run_iredis()

    def _run_iredis(self) -> None:
        iredis_bin = os.path.join(os.path.dirname(sys.executable), "iredis")
        client = self._get_client()

        kwargs = client.client.connection_pool.connection_kwargs
        actual_host = kwargs.get("host", client.host)
        actual_port = kwargs.get("port", client.port)

        # Construct secure connection URL
        if client.password:
            url = f"redis://:{client.password}@{actual_host}:{actual_port}/{client.db}"
        else:
            url = f"redis://{actual_host}:{actual_port}/{client.db}"

        env = os.environ.copy()
        env["IREDIS_URL"] = url

        with self.app.suspend():
            subprocess.run([iredis_bin], check=False, env=env)

    def action_quit(self) -> None:
        client = self._get_client()
        client.disconnect()
        self.app.exit()

    def action_switch_connection(self) -> None:
        """Disconnect and return to the connect screen."""
        client = self._get_client()
        client.disconnect()
        self.app.switch_screen("connect")

    # ── Event Handlers ───────────────────────────────────────────

    def on_select_changed(self, event: Select.Changed) -> None:
        if getattr(event.select, "id", None) == "db-select":
            if event.value is None or event.value == getattr(Select, "BLANK", None):
                return
            try:
                new_db = int(str(event.value))
            except (ValueError, TypeError):
                return

            client = self._get_client()
            if client.db != new_db:
                client.switch_db(new_db)
                self.query_one("#value-viewer", ValueViewer).show_empty()
                self._virtual_keys.clear()  # virtual keys are DB-scoped
                self._load_keys()
                self.notify(f"Switched to DB {new_db}", timeout=2)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search-box":
            tree = self.query_one("#key-tree", KeyTree)
            tree.filter_keys(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "limit-box":
            self._load_keys()
            self.notify(f"Keys reloaded (limit: {self._get_page_limit()})", timeout=2)
        elif event.input.id == "search-box":
            pattern = f"*{event.value}*" if event.value else "*"
            self._load_keys(pattern=pattern)
            self.notify(f"Search matching {pattern}", timeout=2)

    async def on_key_tree_load_more_clicked(self, event: KeyTree.LoadMoreClicked) -> None:
        """Fetch the next page of keys and append to the tree."""
        tree = self.query_one("#key-tree", KeyTree)
        if tree._next_cursor == 0:
            return

        client = self._get_client()

        actual_pattern = getattr(self, "_current_pattern", "*")
        next_cursor, keys = client.scan_keys_paginated(
            cursor=tree._next_cursor, pattern=actual_pattern, count=self._get_page_limit()
        )

        if keys:
            key_types = client.get_types(keys)
            try:
                ttl_map = client.get_ttls(keys[:2000])
            except Exception:
                ttl_map = {}
            tree.append_keys(keys, key_types, next_cursor, ttl_map=ttl_map)
        else:
            tree._next_cursor = next_cursor
            tree._rebuild_tree()

    def on_key_tree_selection_changed(self, event: KeyTree.SelectionChanged) -> None:
        """Show selection count in the status bar."""
        n = len(event.selected_keys)
        if n == 0:
            self.query_one("#status-bar", Static).update("")
        else:
            self.query_one("#status-bar", Static).update(
                f"[bold yellow]☑ {n} key{'s' if n != 1 else ''} selected[/]  "
                f"[dim]Ctrl+D to delete all selected[/]"
            )

    def action_bulk_delete(self) -> None:
        """Delete all currently selected keys."""
        tree = self.query_one("#key-tree", KeyTree)
        selected = tree.bulk_delete_selected()
        if not selected:
            self.notify("No keys selected — press Space on a key to select it", timeout=3)
            return
        client = self._get_client()
        deleted = client.delete_keys_batch(list(selected))
        self.query_one("#status-bar", Static).update("")
        self.notify(f"🗑️ Deleted {deleted} key{'s' if deleted != 1 else ''}", timeout=3)
        self.query_one("#value-viewer", ValueViewer).show_empty()
        self._load_keys()

    async def on_key_tree_key_selected(self, event: KeyTree.KeySelected) -> None:
        """When a key is selected in the tree, show its value and detail."""
        client = self._get_client()
        key = event.key
        key_type = client.get_type(key)

        if key_type == "none" and hasattr(self, "_virtual_keys"):
            # Check if it was a virtual key that hasn't been written to Redis yet
            if key in self._virtual_keys:
                key_type = self._virtual_keys[key]

        # Show value
        viewer = self.query_one("#value-viewer", ValueViewer)
        data, total_count = self._get_value(key, key_type)
        await viewer.show_value(key, key_type, data, total_count=total_count)

        # Show detail
        detail = self.query_one("#key-detail", KeyDetail)
        ttl = client.get_ttl(key)
        encoding = client.get_encoding(key)
        memory = client.get_memory_usage(key)
        await detail.show_detail(key, key_type, ttl, encoding, memory)

        # Switch to value tab
        tabs = self.query_one("#center-panel", TabbedContent)
        tabs.active = "tab-value"

    def _get_value(self, key: str, key_type: str) -> tuple:
        """Return (data, total_count). total_count is None for string keys."""
        client = self._get_client()
        if key_type == "string":
            return client.get_string(key), None
        elif key_type == "list":
            return client.get_list(key), client.get_list_count(key)
        elif key_type == "hash":
            return client.get_hash(key), client.get_hash_count(key)
        elif key_type == "set":
            return client.get_set(key), client.get_set_count(key)
        elif key_type == "zset":
            return client.get_zset(key), client.get_zset_count(key)
        return None, None

    # ── Value Viewer Messages ────────────────────────────────────

    async def on_value_viewer_value_saved(self, event: ValueViewer.ValueSaved) -> None:
        client = self._get_client()
        if event.value_type == "string":
            client.set_string(event.key, event.data)
            self.notify(f"✅ Saved {event.key}", timeout=2)

    async def on_value_viewer_member_added(self, event: ValueViewer.MemberAdded) -> None:
        client = self._get_client()
        try:
            if event.value_type == "list":
                idx, val = event.data
                if idx is not None:
                    client.list_set(event.key, idx, val)
                else:
                    client.list_push(event.key, val)
            elif event.value_type == "hash":
                field, value = event.data
                client.hash_set(event.key, field, value)
            elif event.value_type == "set":
                client.set_add(event.key, event.data)
            elif event.value_type == "zset":
                member, score = event.data
                client.zset_add(event.key, member, score)

            # Refresh the view
            key_type = client.get_type(event.key)
            data, total_count = self._get_value(event.key, key_type)
            viewer = self.query_one("#value-viewer", ValueViewer)
            await viewer.show_value(event.key, key_type, data, total_count=total_count)
            self.notify(f"✅ Saved to {event.key}", timeout=2)
        except Exception as e:
            self.notify(f"⚠️ Edit failed: {e}", severity="error", timeout=4)

    async def on_value_viewer_member_deleted(self, event: ValueViewer.MemberDeleted) -> None:
        client = self._get_client()
        try:
            if event.value_type == "list":
                idx, val = event.data
                if idx is not None:
                    # Precise index-based deletion — safe even when list contains duplicates
                    client.list_delete_by_index(event.key, idx)
                else:
                    # Fallback: delete by value (removes first occurrence)
                    client.list_remove(event.key, val, 1)
            elif event.value_type == "hash":
                client.hash_delete(event.key, event.data)
            elif event.value_type == "set":
                client.set_remove(event.key, event.data)
            elif event.value_type == "zset":
                client.zset_remove(event.key, event.data)

            # Refresh the view
            key_type = client.get_type(event.key)
            if key_type == "none":
                # Deleted last element, key might be gone!
                self.query_one("#value-viewer", ValueViewer).show_empty()
                self._load_keys()
            else:
                data, total_count = self._get_value(event.key, key_type)
                viewer = self.query_one("#value-viewer", ValueViewer)
                await viewer.show_value(event.key, key_type, data, total_count=total_count)
            self.notify(f"🗑️ Deleted from {event.key}", timeout=2)
        except Exception as e:
            self.notify(f"⚠️ Delete failed: {e}", severity="error", timeout=4)

    async def on_value_viewer_load_more(self, event: ValueViewer.LoadMore) -> None:
        """Fetch the next page of list/zset/hash/set data and append it to the viewer."""
        client = self._get_client()
        viewer = self.query_one("#value-viewer", ValueViewer)
        try:
            if event.value_type == "list":
                start = event.offset
                end = start + client.DISPLAY_LIMIT - 1
                new_data = client.get_list(event.key, start=start, end=end)
                total = client.get_list_count(event.key)
                viewer.append_rows(new_data, total)
            elif event.value_type == "zset":
                start = event.offset
                end = start + client.DISPLAY_LIMIT - 1
                new_data = client.get_zset(event.key, start=start, end=end)
                total = client.get_zset_count(event.key)
                viewer.append_rows(new_data, total)
            elif event.value_type == "hash":
                next_cursor, new_data = client.scan_hash(event.key, cursor=event.cursor)
                total = client.get_hash_count(event.key)
                viewer.append_rows(new_data, total, next_cursor=next_cursor)
            elif event.value_type == "set":
                next_cursor, new_data = client.scan_set(event.key, cursor=event.cursor)
                total = client.get_set_count(event.key)
                viewer.append_rows(new_data, total, next_cursor=next_cursor)
        except Exception as e:
            self.notify(f"⚠️ Load more failed: {e}", severity="error", timeout=4)

    # ── Key Detail Messages ──────────────────────────────────────

    async def on_key_detail_key_deleted(self, event: KeyDetail.KeyDeleted) -> None:
        client = self._get_client()
        client.delete_key(event.key)

        if event.key in self._virtual_keys:
            del self._virtual_keys[event.key]

        self._load_keys()
        viewer = self.query_one("#value-viewer", ValueViewer)
        viewer.show_empty()
        self.notify(f"🗑️  Deleted {event.key}", timeout=2)

    async def on_key_detail_key_renamed(self, event: KeyDetail.KeyRenamed) -> None:
        client = self._get_client()
        success = client.rename_key(event.old_key, event.new_key)
        if not success:
            self.notify(f"⚠️ Rename failed: {event.old_key!r} may not exist or target already exists", severity="error", timeout=4)
            return

        # Update virtual keys tracking if applicable
        if event.old_key in self._virtual_keys:
            self._virtual_keys[event.new_key] = self._virtual_keys.pop(event.old_key)

        self._load_keys()
        self.notify(f"✏️  Renamed {event.old_key!r} → {event.new_key!r}", timeout=2)

        # Re-open the renamed key in the value viewer
        key_type = client.get_type(event.new_key)
        data, total_count = self._get_value(event.new_key, key_type)
        viewer = self.query_one("#value-viewer", ValueViewer)
        await viewer.show_value(event.new_key, key_type, data, total_count=total_count)

        detail = self.query_one("#key-detail", KeyDetail)
        ttl = client.get_ttl(event.new_key)
        encoding = client.get_encoding(event.new_key)
        memory = client.get_memory_usage(event.new_key)
        await detail.show_detail(event.new_key, key_type, ttl, encoding, memory)

    async def on_key_detail_ttl_set(self, event: KeyDetail.TtlSet) -> None:
        client = self._get_client()
        client.set_ttl(event.key, event.ttl)
        self.notify(f"⏱️  TTL set to {event.ttl}s for {event.key}", timeout=2)

    # ── Command Console Messages ─────────────────────────────────

    def on_command_input_command_submitted(self, event: CommandInput.CommandSubmitted) -> None:
        client = self._get_client()
        result = client.execute_command(event.command)
        console = self.query_one("#command-input", CommandInput)
        console.write_result(event.command, result)

        # Auto-refresh if write command
        cmd_upper = event.command.strip().split()[0].upper() if event.command.strip() else ""
        write_cmds = {
            "SET",
            "DEL",
            "HSET",
            "HDEL",
            "LPUSH",
            "RPUSH",
            "SADD",
            "ZADD",
            "SREM",
            "ZREM",
            "RENAME",
            "EXPIRE",
            "PERSIST",
            "FLUSHDB",
        }
        if cmd_upper in write_cmds:
            self._load_keys()

    # ── New Key Dialog ───────────────────────────────────────────

