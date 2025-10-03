"""Automation worker for changing GitHub usernames.

This module exposes :class:`AutomationWorker`, a :class:`~PyQt5.QtCore.QObject`
subclass used by the GUI to run the Playwright automation logic in a
background thread.
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from json.decoder import JSONDecodeError

from PyQt5.QtCore import QObject, pyqtSignal
from playwright.sync_api import Locator, Page, TimeoutError
from gologin import GoLogin


@dataclass(frozen=True)
class ProxySettings:
    """Proxy configuration parsed from the UI input string."""

    host: str
    port: int
    username: str
    password: str

    @classmethod
    def parse(cls, proxy_string: str) -> "ProxySettings":
        """Parse a ``host:port:user:pass`` proxy string."""

        parts = proxy_string.split(":", 3)
        if len(parts) != 4:
            raise ValueError("Proxy phải có dạng host:port:user:pass")
        host, port, username, password = parts
        try:
            port_int = int(port)
        except ValueError as exc:  # pragma: no cover - defensive guard
            raise ValueError("Port của proxy phải là số") from exc
        return cls(host=host, port=port_int, username=username, password=password)


@dataclass(frozen=True)
class AccountInfo:
    """GitHub account information parsed from the UI input string."""

    new_username: str
    current_username: str
    password: str
    totp_secret: str

    @classmethod
    def parse(cls, account_string: str) -> "AccountInfo":
        """Parse a ``new|current|password|2fa`` account string."""

        parts = [part.strip() for part in account_string.split("|", 3)]
        if len(parts) != 4 or any(not part for part in parts):
            raise ValueError(
                "Sai định dạng. Yêu cầu: newusername|currentusername|password|2fa_secret"
            )
        return cls(
            new_username=parts[0],
            current_username=parts[1],
            password=parts[2],
            totp_secret=parts[3],
        )


class AutomationWorker(QObject):
    """Execute the GitHub username change flow using Playwright."""

    progress = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, token: str, proxy: str, account: str) -> None:
        super().__init__()
        self._token = token
        self._proxy_string = proxy
        self._account_string = account

    # ------------------------------------------------------------------
    @staticmethod
    def _random_delay(min_seconds: float = 1.2, max_seconds: float = 2.8) -> None:
        """Sleep for a random amount of time to mimic human behaviour."""

        time.sleep(random.uniform(min_seconds, max_seconds))

    def _human_like_type(self, locator: Locator, text: str) -> None:
        locator.click()
        for char in text:
            locator.type(char, delay=random.uniform(110, 220))
        self._random_delay(0.6, 1.2)

    def _human_like_click(self, locator: Locator) -> None:
        locator.scroll_into_view_if_needed()
        locator.hover()
        self._random_delay(0.6, 1.1)
        locator.click(delay=random.uniform(90, 160))

    def _get_totp_code(self, page: Page, secret_key: str) -> str | None:
        self.progress.emit(
            f"Đang lấy mã 2FA qua trình duyệt cho key: ...{secret_key[-4:]}"
        )
        api_page = page.context.new_page()
        api_page.goto(
            f"https://2fa.live/tok/{secret_key}",
            wait_until="domcontentloaded",
            timeout=15_000,
        )
        content = api_page.inner_text("body")
        api_page.close()
        token = json.loads(content).get("token")
        if token:
            self.progress.emit(f"Lấy mã thành công: {token}")
        return token

    # ------------------------------------------------------------------
    def run(self) -> None:  # pragma: no cover - executed in QThread
        profile_id: str | None = None
        gl_creator: GoLogin | None = None
        try:
            proxy_settings = ProxySettings.parse(self._proxy_string)
            account_info = AccountInfo.parse(self._account_string)

            gl_creator = GoLogin({"token": self._token})
            self.progress.emit("Đang tạo profile Gologin...")
            profile_id = gl_creator.create(
                {
                    "name": f"Profile-{account_info.current_username}",
                    "os": "win",
                    "proxyEnabled": True,
                    "proxy": {
                        "mode": "socks5",
                        "host": proxy_settings.host,
                        "port": proxy_settings.port,
                        "username": proxy_settings.username,
                        "password": proxy_settings.password,
                    },
                }
            )
            self.progress.emit(f"Đã tạo profile ID: {profile_id}")

            gl_runner = GoLogin({"token": self._token, "profile_id": profile_id})
            debugger_address = gl_runner.start()

            from playwright.sync_api import sync_playwright  # lazy import

            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp(f"http://{debugger_address}")
                context = browser.contexts[0]
                page = context.pages[0]

                self._login(page, account_info)
                self._change_username(page, account_info)

                self.finished.emit(
                    f"ĐÃ ĐỔI THÀNH CÔNG USERNAME -> {account_info.new_username}"
                )

        except ValueError as exc:
            self.error.emit(str(exc))
        except JSONDecodeError:
            self.error.emit(
                "LỖI GIAO TIẾP GOLOGIN:\n- API Token không hợp lệ/hết hạn.\n- Mạng/Proxy chặn kết nối."
            )
        except TimeoutError:
            self.error.emit(
                "LỖI TIMEOUT: Trang/phần tử không tải kịp.\n- Kiểm tra kết nối/proxy.\n- Có thể giao diện GitHub đã thay đổi."
            )
        except Exception as exc:  # pragma: no cover - defensive guard
            self.error.emit(f"ĐÃ GẶP LỖI:\n{exc}")
        finally:
            if profile_id and gl_creator:
                self.progress.emit("Kết thúc tiến trình.")

    # ------------------------------------------------------------------
    def _login(self, page: Page, account_info: AccountInfo) -> None:
        page.goto("https://github.com/login", wait_until="domcontentloaded", timeout=35_000)
        page.wait_for_load_state("networkidle", timeout=35_000)
        self._random_delay()

        self.progress.emit("Gõ username hiện tại...")
        self._human_like_type(
            page.get_by_label("Username or email address"), account_info.current_username
        )

        self.progress.emit("Gõ password...")
        self._human_like_type(page.get_by_label("Password"), account_info.password)

        self.progress.emit("Nhấn Sign in...")
        self._human_like_click(page.get_by_role("button", name="Sign in", exact=True))

        page.wait_for_url("**/sessions/two-factor/app**", timeout=35_000)
        self.progress.emit("Tới trang nhập mã 2FA.")
        totp_code = self._get_totp_code(page, account_info.totp_secret)
        if not totp_code:
            raise RuntimeError("Không thể lấy mã 2FA.")

        self.progress.emit("Gõ mã 2FA...")
        self._human_like_type(page.get_by_placeholder("XXXXXX"), totp_code)

        dashboard_selector = "header[role='banner']"
        skip_button_selector = (
            "button:has-text('skip 2FA verification'), button:has-text('Skip for now')"
        )
        self.progress.emit("Chờ xác nhận đăng nhập...")
        page.wait_for_selector(f"{dashboard_selector}, {skip_button_selector}", timeout=35_000)
        skip_button = page.locator(skip_button_selector)
        if skip_button.is_visible():
            self.progress.emit("Thấy màn hình xác minh thiết bị: nhấn Skip.")
            self._human_like_click(skip_button)
        else:
            self.progress.emit("Đăng nhập thành công.")

        self._random_delay(2.2, 4.2)

    # ------------------------------------------------------------------
    def _change_username(self, page: Page, account_info: AccountInfo) -> None:
        self.progress.emit("Mở trang quản trị đổi username...")
        page.goto("https://github.com/settings/admin", wait_until="domcontentloaded", timeout=35_000)
        page.wait_for_load_state("networkidle", timeout=35_000)
        self._random_delay()

        frame = page.frame_locator("turbo-frame#settings-frame")

        self.progress.emit('Bấm "Change username" (robust)...')
        change_button = frame.locator("button#dialog-show-rename-warning-dialog")
        change_button.wait_for(state="visible", timeout=30_000)
        page.evaluate("window.scrollTo(0, 0)")
        change_button.scroll_into_view_if_needed()

        page.wait_for_function(
            """
            (selector) => {
                const el = document.querySelector('turbo-frame#settings-frame')?.querySelector(selector);
                if (!el) return false;
                const rect = el.getBoundingClientRect();
                const inView = rect.width > 0 && rect.height > 0 && rect.top >= 0 && rect.left >= 0;
                const disabled = el.disabled || el.getAttribute('aria-disabled') === 'true';
                return inView && !disabled;
            }
            """,
            arg="button#dialog-show-rename-warning-dialog",
            timeout=10_000,
        )

        self._retry_click(page, change_button, "Change username", max_attempts=5)

        self.progress.emit("Chờ dialog cảnh báo mở...")
        page.wait_for_function(
            "document.getElementById('rename-warning-dialog')?.open === true",
            timeout=12_000,
        )
        self._random_delay(0.8, 1.4)

        self.progress.emit('Bấm "I understand, let’s change my username"...')
        understand_button = page.locator(
            "dialog#rename-warning-dialog button[data-show-dialog-id='rename-form-dialog']"
        )
        understand_button.wait_for(state="visible", timeout=15_000)
        understand_button.scroll_into_view_if_needed()
        self._retry_click(
            page, understand_button, "I understand, let’s change my username", max_attempts=4
        )

        self.progress.emit("Chờ form đổi username mở...")
        page.wait_for_function(
            "document.getElementById('rename-form-dialog')?.open === true",
            timeout=12_000,
        )
        self._random_delay(0.8, 1.4)

        self.progress.emit("Nhập username mới...")
        username_input = page.locator("dialog#rename-form-dialog input#login")
        username_input.wait_for(state="visible", timeout=15_000)
        username_input.scroll_into_view_if_needed()
        username_input.fill("")
        self._human_like_type(username_input, account_info.new_username)

        page.keyboard.press("Tab")
        time.sleep(0.8)

        submit_button = page.locator(
            'dialog#rename-form-dialog button.Button--primary.Button--medium.Button[type="submit"], '
            'dialog#rename-form-dialog button:has-text("Change my username")'
        )
        submit_button.first.wait_for(state="visible", timeout=15_000)
        submit_button.first.scroll_into_view_if_needed()

        self.progress.emit('Bấm "Change my username" lần 1 (kích hoạt check)...')
        try:
            submit_button.first.click(delay=random.uniform(90, 160))
        except Exception:
            element = submit_button.first.element_handle()
            if element is not None:
                page.evaluate("(el) => el.click()", element)

        if not self._wait_availability(page):
            error_icon = page.locator(
                "dialog#rename-form-dialog .FormControl-inlineValidation [data-target=\"primer-text-field.validationErrorIcon\"]:not([hidden])"
            )
            if error_icon.count() > 0 and error_icon.is_visible():
                raise RuntimeError("GitHub báo lỗi: username không khả dụng hoặc không hợp lệ.")
            raise RuntimeError("Không thấy xác nhận khả dụng (icon success hoặc 'is available').")

        self._random_delay(1.0, 1.8)

        self.progress.emit('Bấm "Change my username" lần 2 để xác nhận...')
        enabled_button = page.locator(
            'dialog#rename-form-dialog button[type="submit"]:not([disabled]):not([aria-disabled="true"])'
        )
        target_button = enabled_button.first if enabled_button.count() > 0 else submit_button.first
        target_button.scroll_into_view_if_needed()
        try:
            target_button.click(delay=random.uniform(90, 160))
        except Exception:
            element = target_button.element_handle()
            if element is not None:
                page.evaluate("(el) => el.click()", element)

        self.progress.emit("Chờ xác nhận đổi username thành công...")
        page.wait_for_load_state("networkidle", timeout=35_000)
        success_banner = page.locator("text=Your username has been changed")
        new_profile_hint = page.locator(
            f"a[href='/{account_info.new_username}'], text={account_info.new_username}"
        )
        if success_banner.count() == 0 and new_profile_hint.count() == 0:
            dialog_open = page.locator("dialog#rename-form-dialog[open]")
            error_icon = page.locator(
                "dialog#rename-form-dialog .FormControl-inlineValidation [data-target=\"primer-text-field.validationErrorIcon\"]:not([hidden])"
            )
            if dialog_open.count() > 0 and error_icon.count() > 0 and error_icon.is_visible():
                raise RuntimeError("GitHub báo lỗi khi đổi username (validation error).")
            self.progress.emit(
                "Không thấy banner, nhưng không có lỗi hiển thị. Có thể đã đổi xong."
            )

    # ------------------------------------------------------------------
    def _wait_availability(self, page: Page, timeout_seconds: float = 35.0) -> bool:
        self.progress.emit("Chờ xác nhận khả dụng (icon xanh hoặc \"is available\")...")
        success_icon = page.locator(
            "dialog#rename-form-dialog .FormControl-inlineValidation "
            "[data-target='primer-text-field.validationSuccessIcon']:not([hidden])"
        )
        success_text = page.locator("dialog#rename-form-dialog >> text=is available")
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                if success_icon.count() > 0 and success_icon.is_visible():
                    return True
            except Exception:  # pragma: no cover - locator transient errors
                pass
            try:
                if success_text.count() > 0 and success_text.is_visible():
                    return True
            except Exception:  # pragma: no cover
                pass
            time.sleep(0.6)
        return False

    def _retry_click(
        self, page: Page, locator: Locator, name: str, max_attempts: int = 5
    ) -> None:
        clicked = False
        for attempt in range(1, max_attempts + 1):
            try:
                if attempt == 1:
                    locator.click()
                elif attempt == 2:
                    locator.click(force=True)
                elif attempt == 3:
                    element = locator.element_handle()
                    if not element:
                        raise RuntimeError("Không tìm thấy phần tử để click.")
                    box = element.bounding_box()
                    if not box:
                        raise RuntimeError("Không lấy được bounding box của phần tử.")
                    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                    time.sleep(random.uniform(0.18, 0.32))
                    page.mouse.down()
                    time.sleep(random.uniform(0.06, 0.12))
                    page.mouse.up()
                elif attempt == max_attempts:
                    locator.click(force=True)
                else:
                    element = locator.element_handle()
                    if element is None:
                        raise RuntimeError("Không tìm thấy phần tử để click.")
                    page.evaluate("(el)=>el.click()", element)
                clicked = True
                break
            except Exception as exc:
                self.progress.emit(f'Thử click "{name}" lần {attempt} lỗi: {exc}')
                time.sleep(0.5)
        if not clicked:
            raise RuntimeError(f'Không thể click "{name}" sau nhiều lần thử.')
