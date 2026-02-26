"""Main screen — primary workspace after connecting to Redis."""

from __future__ import annotations

import subprocess

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, RadioButton, RadioSet, Select, Static, TabbedContent, TabPane

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

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("ctrl+o", "switch_connection", "Switch Connection", priority=True),
        Binding("f5", "refresh", "Refresh"),
        Binding("slash", "focus_search", "Search", key_display="/"),
        Binding("n", "new_key", "New Key"),
        Binding("ctrl+i", "toggle_info", "Server Info"),
        Binding("ctrl+t", "open_iredis", "IRedis Terminal"),
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
    /* New key dialog */
    #new-key-overlay {
        display: none;
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
        layer: overlay;
    }
    #new-key-overlay.visible {
        display: block;
    }
    #new-key-card {
        width: 60;
        height: auto;
        padding: 2;
        background: $surface;
        border: heavy #DC382D;
    }
    #nk-type-radios {
        height: auto;
        layout: horizontal;
        margin: 0 0 1 0;
    }
    #nk-type-radios RadioButton {
        width: auto;
        margin: 0 1 0 0;
        padding: 0;
    }
    #new-key-card Input {
        margin: 0 0 1 0;
    }
    #new-key-card .dialog-title {
        text-align: center;
        text-style: bold;
        color: #DC382D;
        padding: 0 0 1 0;
    }
    #new-key-btns {
        height: auto;
        align: right middle;
    }
    #new-key-btns Button {
        margin: 0 1;
    }
    #nk-input-container {
        height: auto;
    }
    #nk-input-container Horizontal {
        height: auto;
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
        # New key overlay
        with Vertical(id="new-key-overlay"):
            with Vertical(id="new-key-card"):
                yield Static("✨ New Key", classes="dialog-title")
                with RadioSet(id="nk-type-radios"):
                    yield RadioButton("String", value=True, id="nk-rb-string")
                    yield RadioButton("List", id="nk-rb-list")
                    yield RadioButton("Hash", id="nk-rb-hash")
                    yield RadioButton("Set", id="nk-rb-set")
                    yield RadioButton("ZSet", id="nk-rb-zset")
                yield Input(placeholder="Key name", id="nk-name")
                with Horizontal(id="new-key-btns"):
                    yield Button("Cancel", variant="default", id="nk-cancel")
                    yield Button("Create", variant="primary", id="nk-create")
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

    def _load_keys(self, pattern: str | None = None):
        if pattern is not None:
            self._current_pattern = pattern
        elif not hasattr(self, "_current_pattern"):
            self._current_pattern = "*"

        client = self._get_client()
        next_cursor, keys = client.scan_keys_paginated(
            cursor=0, pattern=self._current_pattern, count=self._get_page_limit()
        )

        # Overwrite with virtual keys if they match the pattern
        import fnmatch

        for v_key in getattr(self, "_virtual_keys", {}):
            if fnmatch.fnmatch(v_key, self._current_pattern):
                if v_key not in keys:
                    keys.append(v_key)

        # Get types for all keys (optimized batch)
        key_types = client.get_types(keys)

        for v_key, v_type in getattr(self, "_virtual_keys", {}).items():
            if v_key in keys and key_types.get(v_key, "none") == "none":
                key_types[v_key] = v_type

        tree = self.query_one("#key-tree", KeyTree)
        tree.load_keys(keys, key_types, next_cursor=next_cursor)
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
        overlay = self.query_one("#new-key-overlay")
        overlay.add_class("visible")
        self.query_one("#nk-name", Input).focus()

    def action_toggle_info(self) -> None:
        tabs = self.query_one("#center-panel", TabbedContent)
        tabs.active = "tab-info" if tabs.active != "tab-info" else "tab-value"

    def action_open_iredis(self) -> None:
        """Launch iredis terminal."""
        self._run_iredis()

    def _run_iredis(self) -> None:
        import os
        import sys

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
            tree.append_keys(keys, key_types, next_cursor)
        else:
            # If redis returned empty batch but non-zero cursor
            tree._next_cursor = next_cursor
            tree._rebuild_tree()

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
        data = self._get_value(key, key_type)
        await viewer.show_value(key, key_type, data)

        # Show detail
        detail = self.query_one("#key-detail", KeyDetail)
        ttl = client.get_ttl(key)
        encoding = client.get_encoding(key)
        memory = client.get_memory_usage(key)
        await detail.show_detail(key, key_type, ttl, encoding, memory)

        # Switch to value tab
        tabs = self.query_one("#center-panel", TabbedContent)
        tabs.active = "tab-value"

    def _get_value(self, key: str, key_type: str):
        client = self._get_client()
        if key_type == "string":
            return client.get_string(key)
        elif key_type == "list":
            return client.get_list(key)
        elif key_type == "hash":
            return client.get_hash(key)
        elif key_type == "set":
            return client.get_set(key)
        elif key_type == "zset":
            return client.get_zset(key)
        return None

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
            data = self._get_value(event.key, key_type)
            viewer = self.query_one("#value-viewer", ValueViewer)
            await viewer.show_value(event.key, key_type, data)
            self.notify(f"✅ Saved to {event.key}", timeout=2)
        except Exception as e:
            self.notify(f"⚠️ Edit failed: {e}", severity="error", timeout=4)

    async def on_value_viewer_member_deleted(self, event: ValueViewer.MemberDeleted) -> None:
        client = self._get_client()
        try:
            if event.value_type == "list":
                # For Redis, list_remove removes by value. Textual passes the actual string value.
                client.list_remove(event.key, event.data, 1)
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
                data = self._get_value(event.key, key_type)
                viewer = self.query_one("#value-viewer", ValueViewer)
                await viewer.show_value(event.key, key_type, data)
            self.notify(f"🗑️ Deleted from {event.key}", timeout=2)
        except Exception as e:
            self.notify(f"⚠️ Delete failed: {e}", severity="error", timeout=4)

    # ── Key Detail Messages ──────────────────────────────────────

    async def on_key_detail_key_deleted(self, event: KeyDetail.KeyDeleted) -> None:
        client = self._get_client()
        client.delete_key(event.key)

        if hasattr(self, "_virtual_keys") and event.key in self._virtual_keys:
            del self._virtual_keys[event.key]

        self._load_keys()
        viewer = self.query_one("#value-viewer", ValueViewer)
        viewer.show_empty()
        self.notify(f"🗑️  Deleted {event.key}", timeout=2)

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

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "nk-cancel":
            self.query_one("#new-key-overlay").remove_class("visible")
        elif event.button.id == "nk-create":
            radio_set = self.query_one("#nk-type-radios", RadioSet)
            name_input = self.query_one("#nk-name", Input)

            # map radio button ID to key_type
            rb_id_map = {
                "nk-rb-string": "string",
                "nk-rb-list": "list",
                "nk-rb-hash": "hash",
                "nk-rb-set": "set",
                "nk-rb-zset": "zset",
            }

            pressed_id = radio_set.pressed_button.id if radio_set.pressed_button else "nk-rb-string"
            key_type = rb_id_map.get(pressed_id, "string")

            name = name_input.value.strip()

            if name:
                # We do not immediately store empty values into Redis because Redis automatically
                # deletes Hash/Set/List/Zset that are completely empty.
                # Instead, we create a "virtual key" that exists locally in the UI.
                # It will physically save to Redis once you add the first value in the right panel.
                if not hasattr(self, "_virtual_keys"):
                    self._virtual_keys = {}
                self._virtual_keys[name] = key_type

                name_input.value = ""
                self.query_one("#new-key-overlay").remove_class("visible")
                self._load_keys()
                self.notify(f"✨ Created virtual {key_type} key: {name}", timeout=2)
