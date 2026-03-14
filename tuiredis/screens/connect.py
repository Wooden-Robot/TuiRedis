"""Connection screen — form for configuring Redis connection."""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Horizontal, Vertical, VerticalScroll
from textual.events import Mount
from textual.screen import Screen
from textual.widgets import Button, Checkbox, Footer, Header, Input, Label, ListItem, ListView, Static

from tuiredis.config import ConnectionProfile, delete_connection, load_connections, save_connection


class ConnectScreen(Screen):
    """Initial screen with a connection form."""

    BINDINGS = [Binding("q", "quit", "Quit", priority=True)]

    DEFAULT_CSS = """
    ConnectScreen {
        align: center middle;
        background: $surface-darken-2;
    }
    ConnectScreen #main-container {
        width: 100;
        height: auto;
        min-height: 80%;
        max-height: 45;
        align: center middle;
        layout: horizontal;
    }
    ConnectScreen #history-card {
        width: 32;
        height: 100%;
        padding: 1 2;
        border: heavy #DC382D;
        background: $surface;
        margin-right: 2;
        display: none;
    }
    ConnectScreen #history-card.has-history {
        display: block;
    }
    ConnectScreen .history-title {
        text-align: center;
        text-style: bold;
        color: #DC382D;
        padding: 0 0 1 0;
        border-bottom: solid $surface-lighten-2;
        width: 1fr;
    }
    ConnectScreen .history-header {
        width: 100%;
        height: auto;
        margin-bottom: 1;
    }
    ConnectScreen #new-conn-btn {
        min-width: 4;
        width: 4;
        height: 1;
        padding: 0;
        margin: 0 0 0 1;
    }
    ConnectScreen #history-list {
        height: 1fr;
        background: transparent;
    }
    ConnectScreen #history-list ListItem {
        padding: 1;
    }
    ConnectScreen #delete-btn {
        width: 100%;
        margin-top: 1;
        display: none;
    }
    ConnectScreen #delete-btn.visible {
        display: block;
    }
    ConnectScreen #connect-card {
        width: 64;
        height: 100%;
        padding: 1 2;
        border: heavy #DC382D;
        background: $surface;
    }
    ConnectScreen #form-scroll {
        height: 1fr;
        width: 100%;
        overflow-y: auto;
        scrollbar-size: 1 1;
    }
    ConnectScreen #connect-title {
        text-align: center;
        text-style: bold;
        color: #DC382D;
        padding: 1 0;
        width: 100%;
    }
    ConnectScreen #connect-subtitle {
        text-align: center;
        color: $text-muted;
        padding: 0 0 1 0;
        width: 100%;
    }
    ConnectScreen .form-label {
        margin: 1 0 0 0;
        color: $text;
        text-style: bold;
    }
    ConnectScreen Input {
        margin: 0 0 1 0;
    }
    ConnectScreen #connect-row {
        height: auto;
        margin: 0;
    }
    ConnectScreen #connect-row Input {
        width: 1fr;
    }
    ConnectScreen .action-row {
        height: auto;
        margin: 1 0 0 0;
        width: 100%;
    }
    ConnectScreen .action-row Button {
        width: 1fr;
        margin: 0 1;
    }
    ConnectScreen #connect-error {
        text-align: center;
        color: $error;
        padding: 1 0;
        display: none;
    }
    ConnectScreen #connect-error.visible {
        display: block;
    }
    ConnectScreen .ascii-art {
        text-align: center;
        color: #DC382D;
        padding: 0 0 1 0;
        width: 100%;
    }
    ConnectScreen #ssh-card {
        display: none;
        height: auto;
        border-top: tall $surface-lighten-2;
        margin: 1 0 0 0;
        padding: 1 0 0 0;
    }
    ConnectScreen #sentinel-card {
        display: none;
        height: auto;
        border-top: tall $surface-lighten-2;
        margin: 1 0 0 0;
        padding: 1 0 0 0;
    }
    ConnectScreen #sentinel-card.visible {
        display: block;
    }
    ConnectScreen #ssh-card.visible {
        display: block;
    }
    ConnectScreen #sentinel-row {
        height: auto;
        margin: 0;
    }
    ConnectScreen #sentinel-row Input {
        width: 1fr;
    }
    ConnectScreen #ssh-row {
        height: auto;
        margin: 0;
    }
    ConnectScreen #ssh-row Input {
        width: 1fr;
    }
    ConnectScreen Checkbox {
        margin: 1 0 0 0;
        width: 1fr;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.profiles: dict[str, ConnectionProfile] = {}
        self.current_profile_id: str | None = None

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Prevent 'q' from quitting the app when typing in an Input."""
        if action == "quit":
            if isinstance(self.app.focused, Input):
                return False
        return True

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Center():
            with Horizontal(id="main-container"):
                with Vertical(id="history-card"):
                    with Horizontal(classes="history-header"):
                        yield Static("Saved Connections", classes="history-title")
                        yield Button("➕", id="new-conn-btn", variant="success", tooltip="New Connection")
                    yield ListView(id="history-list")
                    yield Button("🗑 Delete", variant="error", id="delete-btn")

                with Vertical(id="connect-card"):
                    with VerticalScroll(id="form-scroll"):
                        yield Static(
                            "[bold #DC382D]\n"
                            "  _____      _ ____          _ _     \n"
                            " |_   _|   _(_)  _ \\ ___  __| (_)___ \n"
                            "   | || | | | | |_) / _ \\/ _` | / __|\n"
                            "   | || |_| | |  _ <  __/ (_| | \\__ \\\n"
                            "   |_| \\__,_|_|_| \\_\\___|\\__,_|_|___/[/]",
                            classes="ascii-art",
                        )
                        yield Static("Redis Terminal UI Client", id="connect-subtitle")

                        yield Static("Profile Name", classes="form-label")
                        yield Input(placeholder="(Optional) e.g. Production DB", id="profile-name-input")

                        yield Static("Host", classes="form-label")
                        yield Input(value="127.0.0.1", placeholder="Redis host", id="host-input")
                        with Horizontal(id="connect-row"):
                            yield Input(value="6379", placeholder="Port", id="port-input", type="integer")
                            yield Input(value="0", placeholder="DB", id="db-input", type="integer")
                        yield Static("Password", classes="form-label")
                        yield Input(placeholder="(optional)", password=True, id="password-input")
                        yield Checkbox("Save passwords to disk", id="save-secrets-checkbox")
                        yield Checkbox("Use Redis Cluster", id="use-cluster-checkbox")

                        yield Checkbox("Use Redis Sentinel", id="use-sentinel-checkbox")
                        with Vertical(id="sentinel-card"):
                            yield Static("Sentinel Host & Port", classes="form-label")
                            with Horizontal(id="sentinel-row"):
                                yield Input(placeholder="Sentinel host", id="sentinel-host-input")
                                yield Input(value="26379", placeholder="Port", id="sentinel-port-input", type="integer")
                            yield Input(
                                placeholder="Optional nodes: host1:26379,host2:26379",
                                id="sentinel-nodes-input",
                            )
                            yield Static("Master Name", classes="form-label")
                            yield Input(placeholder="e.g. mymaster", id="sentinel-master-input")
                            yield Static("Sentinel Password", classes="form-label")
                            yield Input(placeholder="(optional)", password=True, id="sentinel-password-input")

                        yield Checkbox("Use SSH Tunnel", id="use-ssh-checkbox")
                        with Vertical(id="ssh-card"):
                            yield Static("SSH Host & Port", classes="form-label")
                            with Horizontal(id="ssh-row"):
                                yield Input(placeholder="SSH host", id="ssh-host-input")
                                yield Input(value="22", placeholder="Port", id="ssh-port-input", type="integer")
                            yield Static("SSH User", classes="form-label")
                            yield Input(placeholder="e.g. root", id="ssh-user-input")
                            yield Static("SSH Password", classes="form-label")
                            yield Input(placeholder="(optional)", password=True, id="ssh-password-input")
                            yield Static("SSH Private Key", classes="form-label")
                            yield Input(placeholder="(optional path to key)", id="ssh-key-input")

                    yield Static("", id="connect-error")

                    with Horizontal(classes="action-row"):
                        yield Button("💾 Save", variant="default", id="save-btn")
                        yield Button("🔗 Connect", variant="primary", id="connect-btn")
        yield Footer()

    async def on_mount(self, event: Mount) -> None:
        await self._refresh_history()

    async def _refresh_history(self) -> None:
        raw_profiles = load_connections()
        self.profiles = {p["id"]: p for p in raw_profiles}

        history_card = self.query_one("#history-card")
        list_view = self.query_one("#history-list", ListView)

        await list_view.clear()

        if self.profiles:
            history_card.add_class("has-history")
            for pid, profile in self.profiles.items():
                list_view.append(ListItem(Label(profile["name"]), id=f"prof-{pid}"))
        else:
            history_card.remove_class("has-history")
            self.current_profile_id = None
            self.query_one("#delete-btn").remove_class("visible")

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        if not event.item or not event.item.id:
            return

        pid = event.item.id.replace("prof-", "")
        self.current_profile_id = pid
        profile = self.profiles.get(pid)

        if profile:
            self.query_one("#profile-name-input", Input).value = profile.get("name", "")
            self.query_one("#host-input", Input).value = profile.get("host", "127.0.0.1")
            self.query_one("#port-input", Input).value = str(profile.get("port", "6379"))
            self.query_one("#db-input", Input).value = str(profile.get("db", "0"))
            self.query_one("#password-input", Input).value = profile.get("password") or ""
            self.query_one("#save-secrets-checkbox", Checkbox).value = bool(
                profile.get("save_secrets")
                or profile.get("password")
                or profile.get("sentinel_password")
                or profile.get("ssh_password")
            )
            self.query_one("#use-cluster-checkbox", Checkbox).value = profile.get("use_cluster", False)
            use_sentinel = profile.get("use_sentinel", False)
            sentinel_checkbox = self.query_one("#use-sentinel-checkbox", Checkbox)
            sentinel_checkbox.value = use_sentinel
            self.query_one("#sentinel-host-input", Input).value = profile.get("sentinel_host") or ""
            self.query_one("#sentinel-port-input", Input).value = str(profile.get("sentinel_port") or 26379)
            self.query_one("#sentinel-nodes-input", Input).value = profile.get("sentinel_nodes") or ""
            self.query_one("#sentinel-master-input", Input).value = profile.get("sentinel_master_name") or ""
            self.query_one("#sentinel-password-input", Input).value = profile.get("sentinel_password") or ""

            use_ssh = profile.get("use_ssh", False)
            checkbox = self.query_one("#use-ssh-checkbox", Checkbox)
            checkbox.value = use_ssh

            # The on_checkbox_changed will show/hide the card, but let's set values anyway
            self.query_one("#ssh-host-input", Input).value = profile.get("ssh_host") or ""
            self.query_one("#ssh-port-input", Input).value = str(profile.get("ssh_port") or 22)
            self.query_one("#ssh-user-input", Input).value = profile.get("ssh_user") or ""
            self.query_one("#ssh-password-input", Input).value = profile.get("ssh_password") or ""
            self.query_one("#ssh-key-input", Input).value = profile.get("ssh_private_key") or ""

            self.query_one("#delete-btn").add_class("visible")

        now = time.time()
        last_click_id = getattr(self, "_last_click_id", None)
        last_click_time = getattr(self, "_last_click_time", 0.0)

        if last_click_id == pid and (now - last_click_time) < 0.5:
            # Double click detected
            await self._do_connect()
        else:
            self._last_click_id = pid
            self._last_click_time = now

    def _clear_form(self) -> None:
        """Clear the form for a new connection."""
        self.current_profile_id = None
        self.query_one("#profile-name-input", Input).value = ""
        self.query_one("#host-input", Input).value = "127.0.0.1"
        self.query_one("#port-input", Input).value = "6379"
        self.query_one("#db-input", Input).value = "0"
        self.query_one("#password-input", Input).value = ""
        self.query_one("#save-secrets-checkbox", Checkbox).value = False
        self.query_one("#use-cluster-checkbox", Checkbox).value = False
        self.query_one("#use-sentinel-checkbox", Checkbox).value = False
        self.query_one("#sentinel-host-input", Input).value = ""
        self.query_one("#sentinel-port-input", Input).value = "26379"
        self.query_one("#sentinel-nodes-input", Input).value = ""
        self.query_one("#sentinel-master-input", Input).value = ""
        self.query_one("#sentinel-password-input", Input).value = ""

        checkbox = self.query_one("#use-ssh-checkbox", Checkbox)
        checkbox.value = False

        self.query_one("#ssh-host-input", Input).value = ""
        self.query_one("#ssh-port-input", Input).value = "22"
        self.query_one("#ssh-user-input", Input).value = ""
        self.query_one("#ssh-password-input", Input).value = ""
        self.query_one("#ssh-key-input", Input).value = ""

        self.query_one("#delete-btn").remove_class("visible")

        # Deselect any item in history list
        list_view = self.query_one("#history-list", ListView)
        list_view.index = None

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "connect-btn":
            await self._do_connect()
        elif event.button.id == "save-btn":
            await self._do_save()
        elif event.button.id == "delete-btn":
            await self._do_delete()
        elif event.button.id == "new-conn-btn":
            self._clear_form()

    def action_quit(self) -> None:
        """Exit the application when q is pressed."""
        self.app.exit()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Allow pressing Enter in any input to connect."""
        await self._do_connect()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id == "use-ssh-checkbox":
            ssh_card = self.query_one("#ssh-card")
            if event.value:
                ssh_card.add_class("visible")
            else:
                ssh_card.remove_class("visible")
        elif event.checkbox.id == "use-sentinel-checkbox":
            sentinel_card = self.query_one("#sentinel-card")
            if event.value:
                sentinel_card.add_class("visible")
            else:
                sentinel_card.remove_class("visible")

    def _build_profile_from_inputs(self) -> ConnectionProfile:
        name = self.query_one("#profile-name-input", Input).value.strip() or ""
        host = self.query_one("#host-input", Input).value.strip() or "127.0.0.1"
        port_str = self.query_one("#port-input", Input).value.strip() or "6379"
        db_str = self.query_one("#db-input", Input).value.strip() or "0"
        password = self.query_one("#password-input", Input).value
        save_secrets = self.query_one("#save-secrets-checkbox", Checkbox).value
        use_cluster = self.query_one("#use-cluster-checkbox", Checkbox).value
        use_sentinel = self.query_one("#use-sentinel-checkbox", Checkbox).value
        use_ssh = self.query_one("#use-ssh-checkbox", Checkbox).value

        try:
            port = int(port_str)
        except ValueError:
            port = 6379
        try:
            db = int(db_str)
        except ValueError:
            db = 0

        ssh_host = None
        ssh_port = 22
        ssh_user = None
        ssh_password = None
        ssh_private_key = None
        sentinel_host = None
        sentinel_port = 26379
        sentinel_nodes = None
        sentinel_master_name = None
        sentinel_password = None

        if use_sentinel:
            sentinel_host = self.query_one("#sentinel-host-input", Input).value.strip() or None
            try:
                sentinel_port = int(self.query_one("#sentinel-port-input", Input).value.strip() or "26379")
            except ValueError:
                sentinel_port = 26379
            sentinel_nodes = self.query_one("#sentinel-nodes-input", Input).value.strip() or None
            sentinel_master_name = self.query_one("#sentinel-master-input", Input).value.strip() or None
            sentinel_password = self.query_one("#sentinel-password-input", Input).value or None

        if use_ssh:
            ssh_host = self.query_one("#ssh-host-input", Input).value.strip() or None
            try:
                ssh_port = int(self.query_one("#ssh-port-input", Input).value.strip() or "22")
            except ValueError:
                ssh_port = 22
            ssh_user = self.query_one("#ssh-user-input", Input).value.strip() or None
            ssh_password = self.query_one("#ssh-password-input", Input).value or None
            ssh_private_key = self.query_one("#ssh-key-input", Input).value.strip() or None

        profile: ConnectionProfile = {
            "name": name,
            "host": host,
            "port": port,
            "db": db,
            "password": password or None,
            "save_secrets": save_secrets,
            "use_cluster": use_cluster,
            "use_sentinel": use_sentinel,
            "sentinel_nodes": sentinel_nodes,
            "sentinel_host": sentinel_host,
            "sentinel_port": sentinel_port,
            "sentinel_master_name": sentinel_master_name,
            "sentinel_password": sentinel_password,
            "use_ssh": use_ssh,
            "ssh_host": ssh_host,
            "ssh_port": ssh_port,
            "ssh_user": ssh_user,
            "ssh_password": ssh_password,
            "ssh_private_key": ssh_private_key,
        }

        if self.current_profile_id:
            profile["id"] = self.current_profile_id

        return profile

    @staticmethod
    def _profile_for_storage(profile: ConnectionProfile) -> ConnectionProfile:
        """Return a copy of the profile safe for disk persistence."""
        stored = dict(profile)
        if not stored.get("save_secrets"):
            stored["password"] = None
            stored["sentinel_password"] = None
            stored["ssh_password"] = None
        return stored

    async def _do_save(self) -> None:
        profile = self._build_profile_from_inputs()
        validation_error = self._validate_profile(profile)
        if validation_error:
            error_label = self.query_one("#connect-error", Static)
            error_label.update(f"⚠️ {validation_error}")
            error_label.add_class("visible")
            return

        saved_profile, _, persisted = save_connection(self._profile_for_storage(profile))
        error_label = self.query_one("#connect-error", Static)
        if not persisted:
            error_label.update("❌ Failed to save connection profile")
            error_label.add_class("visible")
            return

        error_label.update("")
        error_label.remove_class("visible")
        # Use the returned profile directly — its ID is guaranteed to be correct
        self.current_profile_id = saved_profile.get("id")
        await self._refresh_history()

    async def _do_delete(self) -> None:
        if self.current_profile_id:
            _, persisted = delete_connection(self.current_profile_id)
            error_label = self.query_one("#connect-error", Static)
            if not persisted:
                error_label.update("❌ Failed to delete connection profile")
                error_label.add_class("visible")
                return

            error_label.update("")
            error_label.remove_class("visible")
            self._clear_form()
            await self._refresh_history()

    @staticmethod
    def _is_valid_host(host: str) -> bool:
        """Return True if host is a valid IPv4, IPv6, or hostname/FQDN."""
        import ipaddress
        import re

        if not host:
            return False
        # Try as IP address first (covers both v4 and v6, including brackets like [::1])
        cleaned = host.strip("[]")
        try:
            ipaddress.ip_address(cleaned)
            return True
        except ValueError:
            pass
        # Validate as hostname / FQDN:
        # - Must be at least 2 characters (single letters are almost always typos)
        # - Labels: letters, digits, hyphens; must not start/end with hyphen
        # - Total length ≤ 253, each label ≤ 63
        if len(host) < 2 or len(host) > 253:
            return False
        hostname_re = re.compile(r"^(?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.?)+$")
        return bool(hostname_re.match(host))

    def _validate_profile(self, profile: dict) -> str | None:
        """Validate connection parameters before attempting network I/O.

        Returns an error message string if invalid, or None if all checks pass.
        """
        host = (profile.get("host") or "").strip()
        if not host:
            return "Host cannot be empty"
        if not self._is_valid_host(host):
            return f"Host {host!r} is not a valid IP address or hostname"

        port = profile.get("port")
        if not isinstance(port, int) or not (1 <= port <= 65535):
            return f"Port must be an integer between 1 and 65535 (got {port!r})"

        db = profile.get("db")
        if not isinstance(db, int) or db < 0:
            return f"DB must be a non-negative integer (got {db!r})"

        if profile.get("use_cluster"):
            if profile.get("db") not in (0, None):
                return "Redis Cluster only supports DB 0"
            if profile.get("use_sentinel"):
                return "Redis Cluster cannot be used together with Redis Sentinel"
            if profile.get("use_ssh"):
                return "Redis Cluster cannot be used together with SSH tunnel yet"

        if profile.get("use_sentinel"):
            sentinel_nodes = (profile.get("sentinel_nodes") or "").strip()
            sentinel_host = (profile.get("sentinel_host") or "").strip()
            if sentinel_nodes:
                for raw_node in sentinel_nodes.split(","):
                    node = raw_node.strip()
                    if not node:
                        continue
                    host_part = node
                    port_part = profile.get("sentinel_port", 26379)
                    if ":" in node:
                        host_part, port_str = node.rsplit(":", 1)
                        try:
                            port_part = int(port_str)
                        except ValueError:
                            return f"Sentinel node {node!r} has an invalid port"
                    if not self._is_valid_host(host_part.strip()):
                        return f"Sentinel node host {host_part!r} is not a valid IP address or hostname"
                    if not isinstance(port_part, int) or not (1 <= port_part <= 65535):
                        return f"Sentinel node port must be between 1 and 65535 (got {port_part!r})"
            elif not sentinel_host:
                return "Sentinel Host cannot be empty when Redis Sentinel is enabled"
            elif not self._is_valid_host(sentinel_host):
                return f"Sentinel Host {sentinel_host!r} is not a valid IP address or hostname"
            sentinel_port = profile.get("sentinel_port", 26379)
            if not isinstance(sentinel_port, int) or not (1 <= sentinel_port <= 65535):
                return f"Sentinel Port must be between 1 and 65535 (got {sentinel_port!r})"
            master_name = (profile.get("sentinel_master_name") or "").strip()
            if not master_name:
                return "Sentinel Master Name cannot be empty when Redis Sentinel is enabled"
            if profile.get("use_ssh"):
                return "Redis Sentinel cannot be used together with SSH tunnel yet"

        if profile.get("use_ssh"):
            ssh_host = (profile.get("ssh_host") or "").strip()
            if not ssh_host:
                return "SSH Host cannot be empty when SSH tunnel is enabled"
            if not self._is_valid_host(ssh_host):
                return f"SSH Host {ssh_host!r} is not a valid IP address or hostname"
            ssh_port = profile.get("ssh_port", 22)
            if not isinstance(ssh_port, int) or not (1 <= ssh_port <= 65535):
                return f"SSH Port must be between 1 and 65535 (got {ssh_port!r})"

        return None

    async def _do_connect(self) -> None:
        import asyncio

        from tuiredis.redis_client import RedisClient

        profile = self._build_profile_from_inputs()

        error_label = self.query_one("#connect-error", Static)
        connect_btn = self.query_one("#connect-btn", Button)

        # Fast client-side validation before touching the network
        validation_error = self._validate_profile(profile)
        if validation_error:
            error_label.update(f"⚠️ {validation_error}")
            error_label.add_class("visible")
            return

        # Disable button to prevent double-clicks while waiting for socket timeout
        connect_btn.disabled = True
        error_label.update("🔗 Connecting...")
        error_label.add_class("visible")

        client = RedisClient(
            host=profile["host"],
            port=profile["port"],
            password=profile.get("password"),
            db=profile["db"],
            use_cluster=profile.get("use_cluster", False),
            use_sentinel=profile.get("use_sentinel", False),
            sentinel_nodes=profile.get("sentinel_nodes"),
            sentinel_host=profile.get("sentinel_host"),
            sentinel_port=profile.get("sentinel_port", 26379),
            sentinel_master_name=profile.get("sentinel_master_name"),
            sentinel_password=profile.get("sentinel_password"),
            ssh_host=profile.get("ssh_host"),
            ssh_port=profile.get("ssh_port", 22),
            ssh_user=profile.get("ssh_user"),
            ssh_password=profile.get("ssh_password"),
            ssh_private_key=profile.get("ssh_private_key"),
        )

        # Run the blocking connect (TCP handshake + optional SSH tunnel) in a thread
        # so the Textual event loop stays responsive during the connection attempt.
        success, err_msg = await asyncio.to_thread(client.connect)

        connect_btn.disabled = False

        if success:
            error_label.update("")
            error_label.remove_class("visible")

            # Auto-save successful connections; use the returned profile for its ID.
            saved_profile, _, persisted = save_connection(self._profile_for_storage(profile))
            if persisted:
                self.current_profile_id = saved_profile.get("id")
                await self._refresh_history()
            elif not persisted:
                error_label.update("⚠️ Connected, but failed to save connection profile")
                error_label.add_class("visible")

            self.app.redis_client = client  # type: ignore[attr-defined]

            # Inform the main screen to refresh its content with the new connection
            main_screen = self.app.get_screen("main")
            if hasattr(main_screen, "refresh_connection"):
                main_screen.refresh_connection()

            self.app.push_screen("main")
        else:
            error_label.update(f"❌ {profile['host']}:{profile['port']} - {err_msg}")
            error_label.add_class("visible")
