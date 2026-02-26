"""TRedis — main Textual application."""

from __future__ import annotations

from pathlib import Path

from textual.app import App

from tuiredis.redis_client import RedisClient
from tuiredis.screens.connect import ConnectScreen
from tuiredis.screens.main import MainScreen

CSS_PATH = Path(__file__).parent / "styles" / "app.tcss"


class TRedisApp(App):
    """The TRedis terminal UI application."""

    TITLE = "TRedis"
    SUB_TITLE = "Redis Terminal UI Client"
    CSS_PATH = CSS_PATH

    SCREENS = {
        "connect": ConnectScreen,
        "main": MainScreen,
    }

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 6379,
        password: str | None = None,
        db: int = 0,
        auto_connect: bool = False,
        ssh_host: str | None = None,
        ssh_port: int = 22,
        ssh_user: str | None = None,
        ssh_password: str | None = None,
        ssh_private_key: str | None = None,
    ):
        super().__init__()
        self.redis_client = RedisClient(
            host=host,
            port=port,
            password=password,
            db=db,
            ssh_host=ssh_host,
            ssh_port=ssh_port,
            ssh_user=ssh_user,
            ssh_password=ssh_password,
            ssh_private_key=ssh_private_key,
        )
        self._auto_connect = auto_connect

    def on_mount(self) -> None:
        if self._auto_connect:
            success, _ = self.redis_client.connect()
            if success:
                self.push_screen("main")
            else:
                self.push_screen("connect")
        else:
            self.push_screen("connect")
