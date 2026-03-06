"""New Key creation modal screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Input, RadioButton, RadioSet, Static


class NewKeyModal(ModalScreen):
    """Modal dialog for creating a new Redis key."""

    DEFAULT_CSS = """
    NewKeyModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    #nk-card {
        width: 70;
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
    #nk-card Input {
        margin: 0 0 1 0;
    }
    #nk-card .dialog-title {
        text-align: center;
        text-style: bold;
        color: #DC382D;
        padding: 0 0 1 0;
    }
    #nk-btns {
        height: auto;
        align: right middle;
        margin-top: 1;
    }
    #nk-btns Button {
        margin: 0 1;
    }
    .nk-type-fields {
        display: none;
        height: auto;
    }
    .nk-type-fields.visible {
        display: block;
    }
    .nk-type-fields Horizontal {
        height: auto;
    }
    .nk-type-fields Input {
        width: 1fr;
    }
    """

    class KeyCreated(Message):
        """Emitted when a key is successfully created or registered as virtual."""

        def __init__(self, key: str, key_type: str, wrote_to_redis: bool) -> None:
            self.key = key
            self.key_type = key_type
            self.wrote_to_redis = wrote_to_redis
            super().__init__()

    _NK_TYPE_MAP = {
        "nk-rb-string": "string",
        "nk-rb-list": "list",
        "nk-rb-hash": "hash",
        "nk-rb-set": "set",
        "nk-rb-zset": "zset",
    }
    _NK_FIELD_IDS = [
        "nk-fields-string",
        "nk-fields-list",
        "nk-fields-hash",
        "nk-fields-set",
        "nk-fields-zset",
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="nk-card"):
            yield Static("✨ New Key", classes="dialog-title")
            with RadioSet(id="nk-type-radios"):
                yield RadioButton("String", value=True, id="nk-rb-string")
                yield RadioButton("List", id="nk-rb-list")
                yield RadioButton("Hash", id="nk-rb-hash")
                yield RadioButton("Set", id="nk-rb-set")
                yield RadioButton("ZSet", id="nk-rb-zset")
            yield Input(placeholder="Key name (required)", id="nk-name")
            with Vertical(id="nk-fields-string", classes="nk-type-fields visible"):
                yield Input(placeholder="Initial value (optional)", id="nk-str-val")
            with Vertical(id="nk-fields-list", classes="nk-type-fields"):
                yield Input(placeholder="First element (optional)", id="nk-list-val")
            with Vertical(id="nk-fields-hash", classes="nk-type-fields"):
                with Horizontal():
                    yield Input(placeholder="Field (optional)", id="nk-hash-fld")
                    yield Input(placeholder="Value (optional)", id="nk-hash-val")
            with Vertical(id="nk-fields-set", classes="nk-type-fields"):
                yield Input(placeholder="First member (optional)", id="nk-set-val")
            with Vertical(id="nk-fields-zset", classes="nk-type-fields"):
                with Horizontal():
                    yield Input(placeholder="Member (optional)", id="nk-zset-mem")
                    yield Input(placeholder="Score (optional)", id="nk-zset-score")
            with Horizontal(id="nk-btns"):
                yield Button("Cancel", variant="default", id="nk-cancel")
                yield Button("✨ Create", variant="primary", id="nk-create")

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        """Show the initial-value container matching the selected type."""
        if not hasattr(event.pressed, "id") or not event.pressed.id:
            return
        pressed_type = self._NK_TYPE_MAP.get(event.pressed.id)
        if pressed_type is None:
            return
        for fid in self._NK_FIELD_IDS:
            try:
                w = self.query_one(f"#{fid}")
                if fid == f"nk-fields-{pressed_type}":
                    w.add_class("visible")
                else:
                    w.remove_class("visible")
            except Exception:
                pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "nk-cancel":
            self.dismiss(None)
        elif event.button.id == "nk-create":
            self.app.call_later(self._submit)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter in any input submits the form."""
        nk_inputs = {
            "nk-name", "nk-str-val", "nk-list-val",
            "nk-hash-fld", "nk-hash-val",
            "nk-set-val", "nk-zset-mem", "nk-zset-score",
        }
        if getattr(event.input, "id", None) in nk_inputs:
            self.app.call_later(self._submit)

    async def _submit(self) -> None:
        """Validate and emit KeyCreated, then dismiss."""
        from tuiredis.redis_client import RedisClient

        client: RedisClient = self.app.redis_client  # type: ignore[attr-defined]

        radio_set = self.query_one("#nk-type-radios", RadioSet)
        name_input = self.query_one("#nk-name", Input)
        name = name_input.value.strip()
        if not name:
            return

        pressed_id = radio_set.pressed_button.id if radio_set.pressed_button else "nk-rb-string"
        key_type = self._NK_TYPE_MAP.get(pressed_id, "string")

        if client.key_exists(name):
            self.notify(
                f"⚠️  Key '{name}' already exists — select it from the tree to edit",
                severity="warning",
                timeout=4,
            )
            return

        wrote_to_redis = False
        try:
            if key_type == "string":
                val = self.query_one("#nk-str-val", Input).value
                if val:
                    client.set_string(name, val)
                    wrote_to_redis = True

            elif key_type == "list":
                val = self.query_one("#nk-list-val", Input).value.strip()
                if val:
                    client.list_push(name, val)
                    wrote_to_redis = True

            elif key_type == "hash":
                field = self.query_one("#nk-hash-fld", Input).value.strip()
                val = self.query_one("#nk-hash-val", Input).value.strip()
                if field and val:
                    client.hash_set(name, field, val)
                    wrote_to_redis = True
                elif field or val:
                    self.notify(
                        "Hash initial value requires both Field and Value — creating empty key",
                        severity="warning",
                        timeout=3,
                    )

            elif key_type == "set":
                val = self.query_one("#nk-set-val", Input).value.strip()
                if val:
                    client.set_add(name, val)
                    wrote_to_redis = True

            elif key_type == "zset":
                member = self.query_one("#nk-zset-mem", Input).value.strip()
                score_str = self.query_one("#nk-zset-score", Input).value.strip()
                if member and score_str:
                    try:
                        score = float(score_str)
                    except ValueError:
                        self.notify(
                            f"Invalid score: {score_str!r} — must be a number",
                            severity="error",
                            timeout=4,
                        )
                        return
                    client.zset_add(name, member, score)
                    wrote_to_redis = True
                elif member or score_str:
                    self.notify(
                        "ZSet initial value requires both Member and Score — creating empty key",
                        severity="warning",
                        timeout=3,
                    )
        except Exception as e:
            self.notify(f"⚠️ Failed to create key: {e}", severity="error", timeout=4)
            return

        self.dismiss(self.KeyCreated(name, key_type, wrote_to_redis))
