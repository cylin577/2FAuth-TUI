from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path

from rich.panel import Panel
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Static

from .client import ApiError, TwoFAuthClient, normalize_server_url
from .models import AccountView
from .security import make_password_record, verify_password, write_json
from .storage import (
    CONFIG_FILE,
    PAT_FILE,
    PASSWORD_FILE,
    ensure_app_dir,
    has_setup,
    install_launcher,
    launcher_exists,
    launcher_file,
    load_json,
    load_text,
    save_json,
    save_text,
)


@dataclass(slots=True)
class SetupState:
    server_url: str = ""
    pat: str = ""


class MessagePanel(Static):
    def set_text(self, title: str, message: str, style: str = "green") -> None:
        self.update(Panel(message, title=title, border_style=style))


class BaseFormScreen(Screen[None]):
    def set_status(self, text: str, style: str = "yellow") -> None:
        panel = self.query_one("#status", MessagePanel)
        panel.set_text("Status", text, style)

    def set_busy(self, busy: bool) -> None:
        for button_id in ("continue", "install"):
            try:
                self.query_one(f"#{button_id}", Button).disabled = busy
                return
            except Exception:
                continue


class ServerScreen(BaseFormScreen):
    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Vertical(
                Label("2FAuth server URL"),
                Input(id="server_url", placeholder="https://2fauth.example.com"),
                Button("Continue", id="continue", variant="primary"),
                MessagePanel(id="status"),
            ),
            id="form",
        )
        yield Footer()

    def on_mount(self) -> None:
        existing = load_json(CONFIG_FILE) or {}
        if existing.get("server_url"):
            self.query_one("#server_url", Input).value = str(existing["server_url"])
        self.set_status("Enter 2FAuth base URL, then I’ll probe `/api/v1/features`.", "blue")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "continue":
            return
        raw = self.query_one("#server_url", Input).value.strip()
        try:
            server_url = normalize_server_url(raw)
        except ValueError as exc:
            self.set_status(str(exc), "red")
            return

        self.set_busy(True)
        self.set_status(f"Checking {server_url} ...", "yellow")
        probe = await TwoFAuthClient(server_url).probe()
        if not probe.available:
            self.set_busy(False)
            self.set_status(f"Can’t reach server: {probe.message}", "red")
            return

        self.app.state.server_url = server_url
        save_json(CONFIG_FILE, {"server_url": server_url})
        self.set_status(f"Server reachable. HTTP {probe.status_code}. Next: PAT.", "green")
        self.app.pop_screen()
        self.app.push_screen(PatScreen())


class PatScreen(BaseFormScreen):
    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Vertical(
                Label("2FAuth Personal Access Token"),
                Input(id="pat", placeholder="Paste PAT here"),
                Button("Continue", id="continue", variant="primary"),
                MessagePanel(id="status"),
            ),
            id="form",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.set_status("PAT is stored in its own file, with restrictive permissions.", "blue")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "continue":
            return
        token = self.query_one("#pat", Input).value.strip()
        if not token:
            self.set_status("PAT cannot be empty.", "red")
            return
        self.set_busy(True)
        self.set_status("Validating PAT against `/api/v1/twofaccounts` ...", "yellow")
        client = TwoFAuthClient(self.app.state.server_url, token)
        try:
            await client.validate()
        except ApiError as exc:
            self.set_busy(False)
            self.set_status(str(exc), "red")
            return
        save_text(PAT_FILE, token)
        self.app.state.pat = token
        self.app.client = client
        self.set_status("PAT accepted. Next: set local unlock password.", "green")
        self.app.pop_screen()
        self.app.push_screen(PasswordSetupScreen())


class PasswordSetupScreen(BaseFormScreen):
    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Vertical(
                Label("Set local password"),
                Input(id="password1", password=True, placeholder="Password"),
                Input(id="password2", password=True, placeholder="Confirm password"),
                Button("Finish", id="continue", variant="primary"),
                MessagePanel(id="status"),
            ),
            id="form",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.set_status("Password is never stored in plain text. Salted hash only.", "blue")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "continue":
            return
        p1 = self.query_one("#password1", Input).value
        p2 = self.query_one("#password2", Input).value
        if not p1:
            self.set_status("Password cannot be empty.", "red")
            return
        if p1 != p2:
            self.set_status("Passwords do not match.", "red")
            return
        record = make_password_record(p1)
        write_json(PASSWORD_FILE, record)
        if launcher_exists():
            self.set_status("Password saved. Launcher already installed.", "green")
            self.app.pop_screen()
            self.app.push_screen(MainScreen())
            return
        self.set_status("Password saved. Next: optional launcher install.", "green")
        self.app.pop_screen()
        self.app.push_screen(InstallScreen())


class InstallScreen(BaseFormScreen):
    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Vertical(
                Label("Install 2FAuth-TUI launcher"),
                Static(id="launcher_info"),
                *(
                    [Button("Install launcher", id="install", variant="primary")]
                    if not launcher_exists()
                    else []
                ),
                Button("Skip", id="skip"),
                MessagePanel(id="status"),
            ),
            id="form",
        )
        yield Footer()

    def on_mount(self) -> None:
        if launcher_exists():
            self.query_one("#launcher_info", Static).update(
                f"Launcher already exists at {launcher_file()}\n"
                "No install needed."
            )
            self.set_status("Launcher already installed. Continue to dashboard.", "green")
            return

        self.query_one("#launcher_info", Static).update(
            f"Install launcher to {launcher_file()}\n"
            "Then run `2fauth` from shell.\n"
            "This step is optional, but handy for daily use."
        )
        self.set_status("Launcher uses `uv run --directory <repo> 2FAuth-TUI`.", "blue")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "skip":
            self.set_status("Skipped launcher install. Opening dashboard ...", "green")
            self.app.pop_screen()
            self.app.push_screen(MainScreen())
            return

        if event.button.id != "install":
            return

        self.set_busy(True)
        try:
            launcher = install_launcher(self.app.repo_root)
        except Exception as exc:
            self.set_busy(False)
            self.set_status(f"Install failed: {exc}", "red")
            return

        self.set_status(f"Installed {launcher}. Make sure ~/.local/bin is on PATH.", "green")
        self.app.pop_screen()
        self.app.push_screen(MainScreen())


class UnlockScreen(BaseFormScreen):
    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Vertical(
                Label("Unlock 2FAuth-TUI"),
                Input(id="password", password=True, placeholder="Local password"),
                Button("Unlock", id="continue", variant="primary"),
                MessagePanel(id="status"),
            ),
            id="form",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.set_status("Enter local password to view OTPs.", "blue")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "continue":
            return
        password = self.query_one("#password", Input).value
        record = load_json(PASSWORD_FILE)
        if not record:
            self.set_status("Missing password record. Re-run setup.", "red")
            return
        if not verify_password(password, record):
            self.set_status("Wrong password.", "red")
            return
        self.app.unlock(password)
        self.set_status("Unlocked.", "green")
        self.app.pop_screen()
        self.app.push_screen(MainScreen())


class MainScreen(Screen[None]):
    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("l", "lock", "Lock"),
        ("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield DataTable(id="accounts")
            yield Vertical(
                Static(id="summary"),
                Static(id="details"),
                *(
                    [Button("Install launcher", id="install_launcher")]
                    if not launcher_exists()
                    else []
                ),
                id="side",
            )
        yield Footer()

    def on_mount(self) -> None:
        self._refreshing = False
        table = self.query_one("#accounts", DataTable)
        table.cursor_type = "row"
        table.add_columns("Service", "Account", "OTP", "Expires")
        self.query_one("#summary", Static).update(Panel("Loading accounts ...", title="2FAuth"))
        self.query_one("#details", Static).update(Panel("Select an account.", title="Details"))
        if self.app.client is None and self.app.state.server_url:
            self.app.client = TwoFAuthClient(self.app.state.server_url, load_text(PAT_FILE) or "")
        self.set_interval(1, self._tick)
        self.run_worker(self.reload(), exclusive=True, group="reload")

    def _tick(self) -> None:
        if not self.app.views:
            return
        now = int(time.time())
        if (
            not self._refreshing
            and any(view.expires_at is not None and view.expires_at <= now for view in self.app.views)
        ):
            self._refreshing = True
            self.run_worker(self.reload(), exclusive=True, group="reload")
        self._render_table()

    def _render_table(self) -> None:
        table = self.query_one("#accounts", DataTable)
        selected = table.cursor_row
        table.clear()
        now = int(time.time())
        for view in self.app.views:
            otp = view.otp.password if view.otp else "..."
            if view.expires_at is None:
                expires = "HOTP"
            else:
                remaining = max(0, view.expires_at - now)
                expires = f"{remaining:02d}s"
            table.add_row(view.account.service, view.account.account, otp, expires, key=str(view.account.id))
        if table.row_count:
            if selected is not None and selected < table.row_count:
                table.cursor_coordinate = (selected, 0)
            self._update_details()
        summary = self.query_one("#summary", Static)
        summary.update(
            Panel(
                f"{len(self.app.views)} accounts from {self.app.state.server_url}\n"
                f"Refresh on demand with 'r'.",
                title="Status",
            )
        )

    def _update_details(self) -> None:
        table = self.query_one("#accounts", DataTable)
        details = self.query_one("#details", Static)
        if table.cursor_row is None or table.cursor_row >= len(self.app.views):
            details.update(Panel("Select an account.", title="Details"))
            return
        view = self.app.views[table.cursor_row]
        otp = view.otp.password if view.otp else "..."
        now = int(time.time())
        remaining = "HOTP"
        if view.expires_at is not None:
            remaining = f"{max(0, view.expires_at - now)} seconds"
        body = Text()
        body.append(f"{view.label}\n", style="bold")
        body.append(f"OTP: {otp}\n", style="green")
        body.append(f"Type: {view.account.otp_type}\n")
        if view.account.period is not None:
            body.append(f"Period: {view.account.period}\n")
        if view.account.counter is not None:
            body.append(f"Counter: {view.account.counter}\n")
        body.append(f"Expires: {remaining}\n")
        details.update(Panel(body, title="Details"))

    def action_refresh(self) -> None:
        self.run_worker(self.reload(), exclusive=True, group="reload")

    def action_lock(self) -> None:
        self.app.lock()
        self.app.pop_screen()
        self.app.push_screen(UnlockScreen())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "install_launcher":
            self._install_launcher()

    def _install_launcher(self) -> None:
        summary = self.query_one("#summary", Static)
        try:
            launcher = install_launcher(self.app.repo_root)
        except Exception as exc:
            summary.update(Panel(f"Launcher install failed: {exc}", title="Status", border_style="red"))
            return
        summary.update(
            Panel(
                f"Launcher installed at {launcher}\n"
                "Run `2fauth` from shell when `~/.local/bin` is on PATH.",
                title="Status",
                border_style="green",
            )
        )

    async def reload(self) -> None:
        summary = self.query_one("#summary", Static)
        summary.update(Panel("Refreshing ...", title="Status"))
        try:
            views = await self.app.client.load_dashboard()
        except Exception as exc:
            summary.update(Panel(f"Refresh failed: {exc}", title="Status", border_style="red"))
            self._refreshing = False
            return
        self.app.views = views
        self._render_table()
        self._refreshing = False

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self._update_details()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._update_details()


class TwoFAuthTuiApp(App[None]):
    TITLE = "2FAuth-TUI"
    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("l", "lock", "Lock"),
        ("q", "quit", "Quit"),
    ]
    CSS = """
    Screen {
        align: center middle;
    }
    #form {
        width: 80%;
        max-width: 80;
        padding: 1 2;
        border: round $accent;
        background: $panel;
    }
    #accounts {
        width: 2fr;
        height: 1fr;
        border: round $accent;
        margin: 1;
    }
    #side {
        width: 1fr;
        height: 1fr;
        margin: 1;
    }
    #summary, #details {
        border: round $accent;
        margin-bottom: 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        ensure_app_dir()
        self.state = SetupState()
        self.client: TwoFAuthClient | None = None
        self.views: list[AccountView] = []
        self._password: str | None = None
        self.repo_root = Path(__file__).resolve().parents[2]

    def on_mount(self) -> None:
        if has_setup():
            config = load_json(CONFIG_FILE) or {}
            server_url = str(config.get("server_url", "")).strip()
            if server_url:
                self.state.server_url = server_url
                self.client = TwoFAuthClient(server_url, load_text(PAT_FILE) or "")
                self.push_screen(UnlockScreen())
                return
        self.push_screen(ServerScreen())

    def unlock(self, password: str) -> None:
        self._password = password
        if self.state.server_url and not self.client:
            self.client = TwoFAuthClient(self.state.server_url, load_text(PAT_FILE) or "")

    def lock(self) -> None:
        self._password = None
