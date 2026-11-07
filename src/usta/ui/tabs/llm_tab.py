"""Optional, user-initiated Gemini chat for quick research and troubleshooting."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from usta.core.llm.gemini import DEFAULT_GEMINI_MODEL
from usta.i18n import _


class LLMTab(QWidget):
    message_submitted = Signal(str, object, str)
    api_key_changed = Signal(str)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(_("Gemini API key")))
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText(_("Paste your own Google AI Studio API key"))
        self.api_key_input.textChanged.connect(self._key_changed)
        layout.addWidget(self.api_key_input)
        layout.addWidget(
            QLabel(
                _(
                    "Free tier note: Google may use submitted prompts to improve its services. "
                    "Do not paste confidential or personal information."
                )
            )
        )
        key_link = QLabel(
            _('<a href="https://aistudio.google.com/app/apikey">Create your free Gemini API key</a>')
        )
        key_link.setOpenExternalLinks(True)
        layout.addWidget(key_link)
        layout.addWidget(
            QLabel(_("Model: {model} (free tier availability may vary)").format(model=DEFAULT_GEMINI_MODEL))
        )

        self.transcript = QTextBrowser()
        self.transcript.setOpenExternalLinks(True)
        layout.addWidget(self.transcript, 1)
        self.input = QPlainTextEdit()
        self.input.setPlaceholderText(_("Ask a question or paste an error message…"))
        self.input.setMaximumHeight(100)
        layout.addWidget(self.input)
        row = QHBoxLayout()
        self.status = QLabel(_("Ready"))
        row.addWidget(self.status, 1)
        self.send_button = QPushButton(_("Send"))
        self.send_button.clicked.connect(self._submit)
        row.addWidget(self.send_button)
        layout.addLayout(row)
        self._api_key = ""
        self._messages: list[dict[str, str]] = []

    def set_api_key(self, value: str):
        self._api_key = value
        self.api_key_input.setText(value)

    def _key_changed(self, value: str):
        self._api_key = value
        self.api_key_changed.emit(value)

    def _submit(self):
        text = self.input.toPlainText().strip()
        if not text:
            return
        if not self._api_key.strip():
            self.status.setText(_("Add a Gemini API key first"))
            return
        self._messages.append({"role": "user", "text": text})
        self.transcript.append(f"<b>You</b><br>{self._escape(text)}<br>")
        self.input.clear()
        self.status.setText(_("Thinking…"))
        self.send_button.setEnabled(False)
        self.message_submitted.emit(self._api_key, list(self._messages), DEFAULT_GEMINI_MODEL)

    def add_answer(self, text: str):
        self._messages.append({"role": "assistant", "text": text})
        self.transcript.append(f"<b>Gemini</b><br>{self._escape(text)}<br>")
        self.status.setText(_("Ready"))
        self.send_button.setEnabled(True)

    def show_error(self, text: str):
        if self._messages and self._messages[-1]["role"] == "user":
            self._messages.pop()
        self.transcript.append(f"<b>Error</b><br>{self._escape(text)}<br>")
        self.status.setText(_("Request failed"))
        self.send_button.setEnabled(True)

    @staticmethod
    def _escape(text: str):
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
