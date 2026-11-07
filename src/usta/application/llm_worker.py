"""Background Gemini request worker for the chat UI."""

from PySide6.QtCore import QThread, Signal

from usta.core.llm.gemini import GeminiClient


class GeminiChatWorker(QThread):
    answered = Signal(str)
    failed = Signal(str)

    def __init__(self, api_key: str, messages: list[dict[str, str]], model: str):
        super().__init__()
        self.api_key = api_key
        self.messages = [dict(item) for item in messages]
        self.model = model

    def run(self):
        try:
            self.answered.emit(GeminiClient(self.api_key).send_message(self.messages, self.model))
        except Exception as exc:
            self.failed.emit(str(exc))
