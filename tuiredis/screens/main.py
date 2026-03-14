"""Main screen — primary workspace after connecting to Redis."""

from __future__ import annotations

import asyncio
import fnmatch
import os
import signal
import subprocess
import sys
from urllib.parse import quote

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Footer, Header, Input, Select, Static, TabbedContent, TabPane

from tuiredis.screens.new_key_modal import NewKeyModal
from tuiredis.widgets.key_detail import KeyDetail
from tuiredis.widgets.key_tree import KeyTree
from tuiredis.widgets.server_info import ServerInfo
from tuiredis.widgets.value_viewer import ValueViewer


class IRedisDbConfirm(ModalScreen):

    DEFAULT_CSS = """
    IRedisDbConfirm {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    #iredis-db-card {
        width: 60;
        height: auto;
        padding: 2;
        background: $surface;
        border: heavy #DC382D;
    }
    #iredis-db-card .dialog-title {
        text-align: center;
        text-style: bold;
        color: #DC382D;
        padding: 0 0 1 0;
    }
    #iredis-db-card .dialog-body {
        padding: 0 0 1 0;
    }
    #iredis-db-btns {
        height: auto;
        align: right middle;
        margin-top: 1;
    }
    #iredis-db-btns Button {
        margin: 0 1;
    }
    """

    def __init__(self, old_db: int, new_db: int) -> None:
        super().__init__()
        self._old_db = old_db
        self._new_db = new_db

    def compose(self) -> ComposeResult:
        with Vertical(id="iredis-db-card"):
            yield Static("DB Changed", classes="dialog-title")
            yield Static(
                f"IRedis session is on DB {self._old_db}, "
                f"but you switched to DB {self._new_db}.\n\n"
                "Restart IRedis for the new DB?\n"
                f"('Resume' keeps the old DB {self._old_db} session)",
                classes="dialog-body",
            )
            with Horizontal(id="iredis-db-btns"):
                yield Button("Resume", variant="default", id="iredis-db-resume")
                yield Button(
                    f"Restart (DB {self._new_db})",
                    variant="primary",
                    id="iredis-db-restart",
                )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "iredis-db-resume":
            self.dismiss(False)
        elif event.button.id == "iredis-db-restart":
            self.dismiss(True)


class MainScreen(Screen):
    """Main workspace screen with key browser, value viewer, and console."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._virtual_keys: dict[str, str] = {}
        self._iredis_proc: subprocess.Popen | None = None  # suspended iredis session
        self._iredis_db: int | None = None  # DB index when iredis was started
        self._keys_request_id = 0
        self._server_info_request_id = 0
        self._detail_request_id = 0
        self._load_more_request_id = 0
        self._loading_states: set[str] = set()
        self._server_mode = "standalone"
        self._server_role = ""
        self._mode_notices_shown: set[str] = set()

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
        grid-rows: 1fr;
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
        yield Static("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        """Load keys on mount."""
        client = self._get_client()
        if getattr(client, "use_cluster", False):
            self._server_mode = "cluster"
        self._load_db_options(selected_db=client.db)
        self.query_one("#db-select", Select).disabled = not self._supports_db_switching()
        asyncio.create_task(self._initialize_screen())

    async def _initialize_screen(self) -> None:
        await self._load_server_info_async()
        await self._load_keys_async()

    def _get_client(self):
        return self.app.redis_client  # type: ignore[attr-defined]

    def _set_loading(self, key: str, is_loading: bool, message: str) -> None:
        if is_loading:
            self._loading_states.add(key)
        else:
            self._loading_states.discard(key)

        if not self.is_mounted:
            return

        status_bar = self.query_one("#status-bar", Static)
        if self._loading_states:
            status_bar.update(f"[dim]{message}[/]")
        else:
            status_bar.update("")

    def _notify_mode_once(self, notice_key: str, message: str, severity: str = "warning") -> None:
        if notice_key in self._mode_notices_shown:
            return
        self._mode_notices_shown.add(notice_key)
        self.notify(message, severity=severity, timeout=4)

    def _supports_db_switching(self) -> bool:
        return self._server_mode not in {"cluster", "sentinel"}

    def _supports_data_browsing(self) -> bool:
        return self._server_mode != "sentinel"

    def _apply_server_capabilities(self, info: dict) -> None:
        self._server_mode = str(info.get("redis_mode") or "standalone")
        self._server_role = str(info.get("role") or "")
        self._load_db_options(selected_db=self._get_client().db)

        db_select = self.query_one("#db-select", Select)
        db_select.disabled = not self._supports_db_switching()

        if self._server_mode == "cluster":
            self._notify_mode_once(
                "cluster",
                "Cluster mode: DB switching is disabled, only DB 0 is available, and some views may still reflect the connected node.",
            )
        elif self._server_mode == "sentinel":
            self._notify_mode_once(
                "sentinel",
                "Sentinel mode detected: key browsing and value operations are unavailable on this connection.",
            )
            self.query_one("#key-tree", KeyTree).load_keys([], {}, next_cursor=0, ttl_map={})
            self.query_one("#value-viewer", ValueViewer).show_empty()
        elif self._server_role in {"slave", "replica"}:
            self._notify_mode_once(
                "replica",
                "Replica detected: read operations work, but writes may fail on a read-only replica.",
            )

    def refresh_connection(self) -> None:
        """Reset the UI state for a new Redis connection."""
        if not self.is_mounted:
            return

        client = self._get_client()
        self._server_mode = "cluster" if getattr(client, "use_cluster", False) else "standalone"
        self._server_role = ""
        self._load_db_options(selected_db=client.db)
        self.query_one("#db-select", Select).disabled = not self._supports_db_switching()

        self.query_one("#value-viewer", ValueViewer).show_empty()
        self._virtual_keys.clear()  # stale virtual keys don't apply to new connection

        # Reset pagination/search
        tree = self.query_one("#key-tree", KeyTree)
        tree._next_cursor = 0

        asyncio.create_task(self._refresh_connection_async())

    async def _refresh_connection_async(self) -> None:
        await self._load_server_info_async()
        await self._load_keys_async()

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
        asyncio.create_task(self._load_keys_async(pattern))

    async def _load_keys_async(self, pattern: str | None = None) -> None:
        self._keys_request_id += 1
        request_id = self._keys_request_id
        self._set_loading("keys", True, "Loading keys...")
        if pattern is not None:
            self._current_pattern = pattern
        elif not hasattr(self, "_current_pattern"):
            self._current_pattern = "*"

        if not self._supports_data_browsing():
            self.query_one("#key-tree", KeyTree).load_keys([], {}, next_cursor=0, ttl_map={})
            self._set_loading("keys", False, "")
            return

        try:
            next_cursor, keys, key_types, ttl_map = await asyncio.to_thread(
                self._fetch_keys_payload,
                self._current_pattern,
                self._get_page_limit(),
            )
            if request_id != self._keys_request_id or not self.is_mounted:
                return

            tree = self.query_one("#key-tree", KeyTree)
            tree.load_keys(keys, key_types, next_cursor=next_cursor, ttl_map=ttl_map)
            self._load_db_options()
        except Exception as e:
            if request_id == self._keys_request_id and self.is_mounted:
                self.query_one("#key-tree", KeyTree).load_keys([], {}, next_cursor=0, ttl_map={})
                self.notify(f"Failed to load keys: {e}", severity="error", timeout=4)
        finally:
            if request_id == self._keys_request_id:
                self._set_loading("keys", False, "")

    def _fetch_keys_payload(
        self,
        pattern: str,
        page_limit: int,
    ) -> tuple[int, list[str], dict[str, str], dict[str, int]]:
        client = self._get_client()
        next_cursor, keys = client.scan_keys_paginated(cursor=0, pattern=pattern, count=page_limit)

        for v_key in self._virtual_keys:
            if fnmatch.fnmatch(v_key, pattern) and v_key not in keys:
                keys.append(v_key)

        keys = list(dict.fromkeys(keys))
        key_types = client.get_types(keys)

        for v_key, v_type in self._virtual_keys.items():
            if v_key in keys and key_types.get(v_key, "none") == "none":
                key_types[v_key] = v_type

        ttl_sample = keys[:2000]
        try:
            ttl_map = client.get_ttls(ttl_sample)
        except Exception:
            ttl_map = {}

        return next_cursor, keys, key_types, ttl_map

    def _load_db_options(self, selected_db: int | None = None):
        client = self._get_client()
        keyspace = client.get_keyspace_info()
        db_count = max(client.get_database_count(), (selected_db if selected_db is not None else client.db) + 1)
        db_opts = []
        for i in range(db_count):
            count = keyspace.get(i, 0)
            if count > 0:
                label = f"DB {i} ({count})"
            else:
                label = f"DB {i}"
            db_opts.append((label, str(i)))

        try:
            select = self.query_one("#db-select", Select)
            target_val = str(selected_db if selected_db is not None else (select.value or client.db))

            with select.prevent(Select.Changed):
                select.set_options(db_opts)
                select.value = target_val
        except Exception:
            pass

    def _load_server_info(self):
        asyncio.create_task(self._load_server_info_async())

    async def _load_server_info_async(self) -> None:
        self._server_info_request_id += 1
        request_id = self._server_info_request_id
        self._set_loading("server_info", True, "Loading server info...")
        try:
            info = await asyncio.to_thread(self._get_client().get_server_info)
            if request_id != self._server_info_request_id or not self.is_mounted:
                return
            self.query_one("#server-info", ServerInfo).update_info(info)
            self._apply_server_capabilities(info)
        except Exception:
            pass
        finally:
            if request_id == self._server_info_request_id:
                self._set_loading("server_info", False, "")

    # ── Actions ──────────────────────────────────────────────────

    async def action_refresh(self) -> None:
        await asyncio.gather(self._load_keys_async(), self._load_server_info_async())
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
        client = self._get_client()

        # If there is a suspended iredis on a different DB, ask the user first
        if self._iredis_proc is not None and self._iredis_db != client.db:
            self.app.push_screen(
                IRedisDbConfirm(self._iredis_db, client.db),
                self._on_iredis_db_confirm,
            )
        else:
            self._run_iredis()

    def _on_iredis_db_confirm(self, restart: bool | None) -> None:
        """Callback from IRedisDbConfirm dialog."""
        self._run_iredis(force_restart=bool(restart))

    def _run_iredis(self, force_restart: bool = False) -> None:
        iredis_bin = os.path.join(os.path.dirname(sys.executable), "iredis")
        client = self._get_client()

        if not os.path.exists(iredis_bin):
            self.notify("IRedis is not installed in the current environment", severity="error", timeout=4)
            return

        # If the user chose to restart for a DB change, kill the old process
        if force_restart and self._iredis_proc is not None:
            try:
                os.kill(-self._iredis_proc.pid, signal.SIGTERM)
                self._iredis_proc.wait(timeout=2)
            except Exception:
                try:
                    os.kill(-self._iredis_proc.pid, signal.SIGKILL)
                except Exception:
                    pass
            self._iredis_proc = None
            self._iredis_db = None
            _restarted_for_db = client.db
        else:
            _restarted_for_db = None

        kwargs = client.client.connection_pool.connection_kwargs
        actual_host = kwargs.get("host", client.host)
        actual_port = kwargs.get("port", client.port)

        # Construct secure connection URL
        if client.password:
            password = quote(client.password, safe="")
            url = f"redis://:{password}@{actual_host}:{actual_port}/{client.db}"
        else:
            url = f"redis://{actual_host}:{actual_port}/{client.db}"

        env = os.environ.copy()
        env["IREDIS_URL"] = url

        with self.app.suspend():
            stdin_fd = sys.stdin.fileno()

            if self._iredis_proc is not None:
                # Resume the previously suspended iredis session
                proc = self._iredis_proc
                os.kill(-proc.pid, signal.SIGCONT)   # SIGCONT to the whole process group
            else:
                # Start iredis in its own process group so Ctrl+Z only affects it
                proc = subprocess.Popen(
                    [iredis_bin],
                    env=env,
                    preexec_fn=os.setpgrp,  # new process group, pgid == proc.pid
                )
                self._iredis_proc = proc
                self._iredis_db = client.db

            # Hand terminal control to iredis's process group
            # Ignore SIGTTOU so tcsetpgrp doesn't block us while we're "background"
            old_sigttou = signal.signal(signal.SIGTTOU, signal.SIG_IGN)
            try:
                os.tcsetpgrp(stdin_fd, proc.pid)
            except OSError:
                pass

            # Wait for iredis to exit OR be suspended by Ctrl+Z
            while True:
                try:
                    _, status = os.waitpid(proc.pid, os.WUNTRACED)
                except ChildProcessError:
                    self._iredis_proc = None
                    break

                if os.WIFSTOPPED(status):
                    # iredis is now suspended — reclaim terminal and return to TuiRedis
                    break
                elif os.WIFEXITED(status) or os.WIFSIGNALED(status):
                    self._iredis_proc = None
                    break

            # Reclaim terminal control for TuiRedis
            try:
                os.tcsetpgrp(stdin_fd, os.getpgrp())
            except OSError:
                pass
            signal.signal(signal.SIGTTOU, old_sigttou)

        # Show a hint in the status bar when iredis is suspended
        status_bar = self.query_one("#status-bar", Static)
        if self._iredis_proc is not None:
            status_bar.update("[dim]IRedis session suspended — Ctrl+T to resume[/]")
        else:
            status_bar.update("")

        if _restarted_for_db is not None:
            self.notify(f"♻️ IRedis restarted (DB changed → DB {_restarted_for_db})", timeout=3)

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

    async def on_select_changed(self, event: Select.Changed) -> None:
        if getattr(event.select, "id", None) == "db-select":
            if event.value is None or event.value == getattr(Select, "BLANK", None):
                return
            try:
                new_db = int(str(event.value))
            except (ValueError, TypeError):
                return

            client = self._get_client()
            if client.db != new_db:
                if not self._supports_db_switching():
                    self._notify_mode_once(
                        f"{self._server_mode}-db-switch",
                        f"DB switching is unavailable in {self._server_mode} mode.",
                    )
                    with event.select.prevent(Select.Changed):
                        event.select.value = str(client.db)
                    return
                if not await asyncio.to_thread(client.switch_db, new_db):
                    self.notify(f"Failed to switch to DB {new_db}", severity="error", timeout=3)
                    with event.select.prevent(Select.Changed):
                        event.select.value = str(client.db)
                    return
                self.query_one("#value-viewer", ValueViewer).show_empty()
                self._virtual_keys.clear()  # virtual keys are DB-scoped
                await self._load_keys_async()
                self.notify(f"Switched to DB {new_db}", timeout=2)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search-box":
            tree = self.query_one("#key-tree", KeyTree)
            tree.filter_keys(event.value)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "limit-box":
            await self._load_keys_async()
            self.notify(f"Keys reloaded (limit: {self._get_page_limit()})", timeout=2)
        elif event.input.id == "search-box":
            pattern = f"*{event.value}*" if event.value else "*"
            await self._load_keys_async(pattern=pattern)
            self.notify(f"Search matching {pattern}", timeout=2)

    async def on_key_tree_load_more_clicked(self, event: KeyTree.LoadMoreClicked) -> None:
        """Fetch the next page of keys and append to the tree."""
        if not self._supports_data_browsing():
            self._notify_mode_once(
                "sentinel-browse",
                "Key browsing is unavailable in sentinel mode.",
            )
            return
        tree = self.query_one("#key-tree", KeyTree)
        if tree._next_cursor == 0:
            return

        self._load_more_request_id += 1
        request_id = self._load_more_request_id
        self._set_loading("load_more", True, "Loading more keys...")
        actual_pattern = getattr(self, "_current_pattern", "*")
        try:
            next_cursor, keys, key_types, ttl_map = await asyncio.to_thread(
                self._fetch_load_more_keys_payload,
                tree._next_cursor,
                actual_pattern,
                self._get_page_limit(),
            )
            if request_id != self._load_more_request_id or not self.is_mounted:
                return

            if keys:
                tree.append_keys(keys, key_types, next_cursor, ttl_map=ttl_map)
            else:
                tree._next_cursor = next_cursor
                tree._rebuild_tree()
        finally:
            if request_id == self._load_more_request_id:
                self._set_loading("load_more", False, "")

    def _fetch_load_more_keys_payload(
        self,
        cursor: int,
        pattern: str,
        page_limit: int,
    ) -> tuple[int, list[str], dict[str, str], dict[str, int]]:
        client = self._get_client()
        next_cursor, keys = client.scan_keys_paginated(cursor=cursor, pattern=pattern, count=page_limit)
        if not keys:
            return next_cursor, [], {}, {}

        key_types = client.get_types(keys)
        try:
            ttl_map = client.get_ttls(keys[:2000])
        except Exception:
            ttl_map = {}
        return next_cursor, keys, key_types, ttl_map

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

    async def action_bulk_delete(self) -> None:
        """Delete all currently selected keys."""
        if not self._supports_data_browsing():
            self._notify_mode_once(
                "sentinel-write",
                "Key operations are unavailable in sentinel mode.",
            )
            return
        tree = self.query_one("#key-tree", KeyTree)
        selected = tree.bulk_delete_selected()
        if not selected:
            self.notify("No keys selected — press Space on a key to select it", timeout=3)
            return
        deleted = await asyncio.to_thread(self._get_client().delete_keys_batch, list(selected))
        self.query_one("#status-bar", Static).update("")
        self.notify(f"🗑️ Deleted {deleted} key{'s' if deleted != 1 else ''}", timeout=3)
        self.query_one("#value-viewer", ValueViewer).show_empty()
        await self._load_keys_async()

    async def on_key_tree_key_selected(self, event: KeyTree.KeySelected) -> None:
        """When a key is selected in the tree, show its value and detail."""
        if not self._supports_data_browsing():
            self._notify_mode_once(
                "sentinel-detail",
                "Value inspection is unavailable in sentinel mode.",
            )
            return
        key = event.key
        self._detail_request_id += 1
        request_id = self._detail_request_id
        self._set_loading("detail", True, f"Loading {key}...")
        try:
            key_type, data, total_count, cursor, ttl, encoding, memory = await asyncio.to_thread(
                self._fetch_key_details_payload,
                key,
            )
            if request_id != self._detail_request_id or not self.is_mounted:
                return

            if key_type == "none" and hasattr(self, "_virtual_keys"):
                # Check if it was a virtual key that hasn't been written to Redis yet
                if key in self._virtual_keys:
                    key_type = self._virtual_keys[key]
                    data, total_count, cursor = self._get_value(key, key_type)

            viewer = self.query_one("#value-viewer", ValueViewer)
            await viewer.show_value(key, key_type, data, total_count=total_count, cursor=cursor)

            detail = self.query_one("#key-detail", KeyDetail)
            await detail.show_detail(key, key_type, ttl, encoding, memory)

            tabs = self.query_one("#center-panel", TabbedContent)
            tabs.active = "tab-value"
        finally:
            if request_id == self._detail_request_id:
                self._set_loading("detail", False, "")

    def _fetch_key_details_payload(self, key: str) -> tuple[str, object, int | None, int, int, str, int | None]:
        client = self._get_client()
        key_type = client.get_type(key)
        data, total_count, cursor = self._get_value(key, key_type)
        ttl = client.get_ttl(key)
        encoding = client.get_encoding(key)
        memory = client.get_memory_usage(key)
        return key_type, data, total_count, cursor, ttl, encoding, memory

    def _get_value(self, key: str, key_type: str) -> tuple:
        """Return (data, total_count, cursor). total_count is None for string keys."""
        client = self._get_client()
        if key_type == "string":
            return client.get_string(key), None, 0
        elif key_type == "list":
            return client.get_list(key), client.get_list_count(key), 0
        elif key_type == "hash":
            total = client.get_hash_count(key)
            if total <= client.DISPLAY_LIMIT:
                return client.get_hash(key), total, 0
            next_cursor, data = client.get_hash_page(key, cursor=0)
            return data, total, next_cursor
        elif key_type == "set":
            total = client.get_set_count(key)
            if total <= client.DISPLAY_LIMIT:
                return client.get_set(key), total, 0
            next_cursor, data = client.get_set_page(key, cursor=0)
            return data, total, next_cursor
        elif key_type == "zset":
            return client.get_zset(key), client.get_zset_count(key), 0
        return None, None, 0

    # ── Value Viewer Messages ────────────────────────────────────

    async def on_value_viewer_value_saved(self, event: ValueViewer.ValueSaved) -> None:
        if not self._supports_data_browsing():
            self._notify_mode_once("sentinel-write", "Key operations are unavailable in sentinel mode.")
            return
        client = self._get_client()
        if event.value_type == "string":
            client.set_string(event.key, event.data)
            self.notify(f"✅ Saved {event.key}", timeout=2)

    async def on_value_viewer_member_added(self, event: ValueViewer.MemberAdded) -> None:
        if not self._supports_data_browsing():
            self._notify_mode_once("sentinel-write", "Key operations are unavailable in sentinel mode.")
            return
        try:
            key_type, data, total_count, cursor = await asyncio.to_thread(self._apply_member_add_and_reload, event)
            viewer = self.query_one("#value-viewer", ValueViewer)
            await viewer.show_value(event.key, key_type, data, total_count=total_count, cursor=cursor)
            self.notify(f"✅ Saved to {event.key}", timeout=2)
        except Exception as e:
            self.notify(f"⚠️ Edit failed: {e}", severity="error", timeout=4)

    def _apply_member_add_and_reload(self, event: ValueViewer.MemberAdded) -> tuple[str, object, int | None, int]:
        client = self._get_client()
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

        key_type = client.get_type(event.key)
        data, total_count, cursor = self._get_value(event.key, key_type)
        return key_type, data, total_count, cursor

    async def on_value_viewer_member_deleted(self, event: ValueViewer.MemberDeleted) -> None:
        if not self._supports_data_browsing():
            self._notify_mode_once("sentinel-write", "Key operations are unavailable in sentinel mode.")
            return
        try:
            key_type, data, total_count, cursor = await asyncio.to_thread(self._apply_member_delete_and_reload, event)
            if key_type == "none":
                # Deleted last element, key might be gone!
                self.query_one("#value-viewer", ValueViewer).show_empty()
                await self._load_keys_async()
            else:
                viewer = self.query_one("#value-viewer", ValueViewer)
                await viewer.show_value(event.key, key_type, data, total_count=total_count, cursor=cursor)
            self.notify(f"🗑️ Deleted from {event.key}", timeout=2)
        except Exception as e:
            self.notify(f"⚠️ Delete failed: {e}", severity="error", timeout=4)

    def _apply_member_delete_and_reload(
        self,
        event: ValueViewer.MemberDeleted,
    ) -> tuple[str, object | None, int | None, int]:
        client = self._get_client()
        if event.value_type == "list":
            idx, val = event.data
            if idx is not None:
                client.list_delete_by_index(event.key, idx)
            else:
                client.list_remove(event.key, val, 1)
        elif event.value_type == "hash":
            client.hash_delete(event.key, event.data)
        elif event.value_type == "set":
            client.set_remove(event.key, event.data)
        elif event.value_type == "zset":
            client.zset_remove(event.key, event.data)

        key_type = client.get_type(event.key)
        if key_type == "none":
            return key_type, None, None, 0
        data, total_count, cursor = self._get_value(event.key, key_type)
        return key_type, data, total_count, cursor

    async def on_value_viewer_load_more(self, event: ValueViewer.LoadMore) -> None:
        """Fetch the next page of list/zset/hash/set data and append it to the viewer."""
        if not self._supports_data_browsing():
            self._notify_mode_once("sentinel-browse", "Key browsing is unavailable in sentinel mode.")
            return
        viewer = self.query_one("#value-viewer", ValueViewer)
        try:
            new_data, total, next_cursor = await asyncio.to_thread(self._fetch_value_viewer_page, event)
            viewer.append_rows(new_data, total, next_cursor=next_cursor)
        except Exception as e:
            self.notify(f"⚠️ Load more failed: {e}", severity="error", timeout=4)

    def _fetch_value_viewer_page(self, event: ValueViewer.LoadMore) -> tuple[object, int, int]:
        client = self._get_client()
        if event.value_type == "list":
            start = event.offset
            end = start + client.DISPLAY_LIMIT - 1
            new_data = client.get_list(event.key, start=start, end=end)
            total = client.get_list_count(event.key)
            return new_data, total, 0
        elif event.value_type == "zset":
            start = event.offset
            end = start + client.DISPLAY_LIMIT - 1
            new_data = client.get_zset(event.key, start=start, end=end)
            total = client.get_zset_count(event.key)
            return new_data, total, 0
        elif event.value_type == "hash":
            next_cursor, new_data = client.scan_hash(event.key, cursor=event.cursor)
            total = client.get_hash_count(event.key)
            return new_data, total, next_cursor
        elif event.value_type == "set":
            next_cursor, new_data = client.scan_set(event.key, cursor=event.cursor)
            total = client.get_set_count(event.key)
            return new_data, total, next_cursor
        return [], 0, 0

    # ── Key Detail Messages ──────────────────────────────────────

    async def on_key_detail_key_deleted(self, event: KeyDetail.KeyDeleted) -> None:
        if not self._supports_data_browsing():
            self._notify_mode_once("sentinel-write", "Key operations are unavailable in sentinel mode.")
            return
        await asyncio.to_thread(self._get_client().delete_key, event.key)

        if event.key in self._virtual_keys:
            del self._virtual_keys[event.key]

        await self._load_keys_async()
        viewer = self.query_one("#value-viewer", ValueViewer)
        viewer.show_empty()
        self.notify(f"🗑️  Deleted {event.key}", timeout=2)

    async def on_key_detail_key_renamed(self, event: KeyDetail.KeyRenamed) -> None:
        if not self._supports_data_browsing():
            self._notify_mode_once("sentinel-write", "Key operations are unavailable in sentinel mode.")
            return
        success = await asyncio.to_thread(self._get_client().rename_key, event.old_key, event.new_key)
        if not success:
            self.notify(f"⚠️ Rename failed: {event.old_key!r} may not exist or target already exists", severity="error", timeout=4)
            return

        # Update virtual keys tracking if applicable
        if event.old_key in self._virtual_keys:
            self._virtual_keys[event.new_key] = self._virtual_keys.pop(event.old_key)

        await self._load_keys_async()
        self.notify(f"✏️  Renamed {event.old_key!r} → {event.new_key!r}", timeout=2)

        # Re-open the renamed key in the value viewer
        key_type, data, total_count, cursor, ttl, encoding, memory = await asyncio.to_thread(
            self._fetch_key_details_payload,
            event.new_key,
        )
        viewer = self.query_one("#value-viewer", ValueViewer)
        await viewer.show_value(event.new_key, key_type, data, total_count=total_count, cursor=cursor)

        detail = self.query_one("#key-detail", KeyDetail)
        await detail.show_detail(event.new_key, key_type, ttl, encoding, memory)

    async def on_key_detail_ttl_set(self, event: KeyDetail.TtlSet) -> None:
        if not self._supports_data_browsing():
            self._notify_mode_once("sentinel-write", "Key operations are unavailable in sentinel mode.")
            return
        await asyncio.to_thread(self._get_client().set_ttl, event.key, event.ttl)
        self.notify(f"⏱️  TTL set to {event.ttl}s for {event.key}", timeout=2)

    # ── New Key Dialog ───────────────────────────────────────────
