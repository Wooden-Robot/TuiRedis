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
    ConnectScreen #ssh-card.visible {
        display: block;
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

    def _build_profile_from_inputs(self) -> ConnectionProfile:
        name = self.query_one("#profile-name-input", Input).value.strip() or ""
        host = self.query_one("#host-input", Input).value.strip() or "127.0.0.1"
        port_str = self.query_one("#port-input", Input).value.strip() or "6379"
        db_str = self.query_one("#db-input", Input).value.strip() or "0"
        password = self.query_one("#password-input", Input).value
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

    async def _do_save(self) -> None:
        profile = self._build_profile_from_inputs()
        connections = save_connection(profile)
        # Find the saved profile to get its ID in case it was newly generated or deduplicated
        for p in connections:
            if (
                p.get("host") == profile.get("host")
                and p.get("port") == profile.get("port")
                and p.get("db") == profile.get("db")
                and p.get("name") == profile.get("name")
            ):
                self.current_profile_id = p.get("id")
                break

        await self._refresh_history()

    async def _do_delete(self) -> None:
        if self.current_profile_id:
            delete_connection(self.current_profile_id)
            self._clear_form()
            await self._refresh_history()

    async def _do_connect(self) -> None:
        profile = self._build_profile_from_inputs()

        error_label = self.query_one("#connect-error", Static)
        error_label.update("🔗 Connecting (this may take a moment)...")
        error_label.add_class("visible")
        self.app.refresh()  # Force UI update immediately

        from tuiredis.redis_client import RedisClient

        client = RedisClient(
            host=profile["host"],
            port=profile["port"],
            password=profile.get("password"),
            db=profile["db"],
            ssh_host=profile.get("ssh_host"),
            ssh_port=profile.get("ssh_port", 22),
            ssh_user=profile.get("ssh_user"),
            ssh_password=profile.get("ssh_password"),
            ssh_private_key=profile.get("ssh_private_key"),
        )

        success, err_msg = client.connect()
        if success:
            error_label.update("")
            error_label.remove_class("visible")

            # Auto-save successful connections if they are new or deduplicated
            connections = save_connection(profile)
            if not self.current_profile_id:
                for p in connections:
                    if (
                        p.get("host") == profile.get("host")
                        and p.get("port") == profile.get("port")
                        and p.get("db") == profile.get("db")
                    ):
                        self.current_profile_id = p.get("id")
                        break
                await self._refresh_history()

            self.app.redis_client = client  # type: ignore[attr-defined]

            # Inform the main screen to refresh its content with the new connection
            main_screen = self.app.get_screen("main")
            if hasattr(main_screen, "refresh_connection"):
                main_screen.refresh_connection()

            self.app.push_screen("main")
        else:
            error_label.update(f"❌ {profile['host']}:{profile['port']} - {err_msg}")
            error_label.add_class("visible")
