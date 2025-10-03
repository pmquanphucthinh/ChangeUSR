"""PyQt5 GUI for the ChangeUSR application."""

from __future__ import annotations

from PyQt5.QtCore import QThread
from PyQt5.QtWidgets import (
    QApplication,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .automation import AutomationWorker


class MainWindow(QWidget):
    """Main application window hosting the automation controls."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("GitHub Username Changer")
        self.setGeometry(100, 100, 700, 680)

        self._thread: QThread | None = None
        self._worker: AutomationWorker | None = None

        self._setup_ui()

    # ------------------------------------------------------------------
    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout()
        form_layout = QFormLayout()

        self.token_input = QLineEdit()
        self.token_input.setPlaceholderText("GOLOGIN_API_TOKEN")

        self.proxy_input = QLineEdit()
        self.proxy_input.setPlaceholderText("host:port:user:pass")

        self.account_input = QLineEdit()
        self.account_input.setPlaceholderText("newusername|currentusername|password|2fa_secret")

        form_layout.addRow(QLabel("Gologin API Token:"), self.token_input)
        form_layout.addRow(QLabel("Proxy (SOCKS5):"), self.proxy_input)
        form_layout.addRow(QLabel("Thông tin tài khoản:"), self.account_input)

        self.run_button = QPushButton("Bắt đầu đổi Username")
        self.run_button.clicked.connect(self.start_automation)  # type: ignore[arg-type]

        self.continue_button = QPushButton("Tiếp tục ▶")
        self.continue_button.setEnabled(False)
        self.continue_button.clicked.connect(self._rerun)  # type: ignore[arg-type]

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText("Log trạng thái sẽ hiển thị ở đây...")

        self.result_label = QLabel("Kết quả:")
        self.result_output = QLineEdit()
        self.result_output.setReadOnly(True)

        main_layout.addLayout(form_layout)
        main_layout.addWidget(self.run_button)
        main_layout.addWidget(self.continue_button)
        main_layout.addWidget(QLabel("Log:"))
        main_layout.addWidget(self.log_output)
        main_layout.addWidget(self.result_label)
        main_layout.addWidget(self.result_output)

        self.setLayout(main_layout)

    # ------------------------------------------------------------------
    def start_automation(self) -> None:
        token = self.token_input.text().strip()
        proxy = self.proxy_input.text().strip()
        account = self.account_input.text().strip()

        if not all([token, proxy, account]):
            self.log_output.setPlainText(
                "Lỗi: Vui lòng điền đủ Token, Proxy và Thông tin tài khoản."
            )
            return

        if len(account.split("|")) < 4:
            self.log_output.setPlainText(
                "Lỗi: Định dạng phải là newusername|currentusername|password|2fa_secret"
            )
            return

        self.run_button.setEnabled(False)
        self.continue_button.setEnabled(False)
        self.run_button.setText("Đang chạy...")
        self.log_output.clear()
        self.result_output.clear()

        self._thread = QThread()
        self._worker = AutomationWorker(token, proxy, account)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)  # type: ignore[arg-type]
        self._worker.progress.connect(self._append_log)
        self._worker.error.connect(self._handle_error)
        self._worker.finished.connect(self._handle_finished)

        self._thread.finished.connect(self._thread.deleteLater)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)

        self._thread.start()

    # ------------------------------------------------------------------
    def _rerun(self) -> None:
        self.log_output.appendPlainText("\n--- Tiếp tục thao tác (chạy lại) ---")
        self.start_automation()

    def _append_log(self, message: str) -> None:
        self.log_output.appendPlainText(message)

    def _handle_error(self, message: str) -> None:
        self.log_output.appendPlainText(f"\n--- LỖI ---\n{message}\n-----------")
        self.run_button.setEnabled(True)
        self.run_button.setText("Chạy lại")
        self.continue_button.setEnabled(True)

    def _handle_finished(self, message: str) -> None:
        self.log_output.appendPlainText("\n--- HOÀN THÀNH ---")
        self.result_output.setText(message)
        self.run_button.setEnabled(True)
        self.run_button.setText("Bắt đầu đổi Username")
        self.continue_button.setEnabled(False)


def run() -> int:
    """Start the Qt event loop and return its exit code."""

    import sys

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec_()


def main() -> None:
    """Console-script entry point."""

    raise SystemExit(run())
