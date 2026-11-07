"""Small Gemini Developer API client using the standard library."""

import json
import urllib.error
import urllib.request
from collections.abc import Callable

DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiClient:
    def __init__(self, api_key: str, opener: Callable | None = None, timeout: int = 45):
        self.api_key = api_key.strip()
        self._opener = opener or urllib.request.urlopen
        self.timeout = timeout

    def send_message(self, messages: list[dict[str, str]], model: str) -> str:
        if not self.api_key:
            raise ValueError("Gemini API key is required. Add your key in the LLM tab.")
        if not model or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for char in model):
            raise ValueError("Invalid Gemini model name.")

        contents = [
            {"role": "model" if item["role"] == "assistant" else "user", "parts": [{"text": item["text"]}]}
            for item in messages
        ]
        request = urllib.request.Request(
            _ENDPOINT.format(model=model),
            data=json.dumps({"contents": contents}).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Goog-Api-Key": self.api_key},
            method="POST",
        )
        try:
            with self._opener(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                error_data = json.loads(exc.read().decode("utf-8"))
                detail = error_data.get("error", {}).get("message", "")
            except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
                pass
            raise RuntimeError(detail or f"Gemini API request failed (HTTP {exc.code}).") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"Could not reach Gemini API: {exc}") from None
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Gemini API returned an invalid response.") from exc

        try:
            text = "".join(part.get("text", "") for part in payload["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError, TypeError):
            text = ""
        if not text.strip():
            raise RuntimeError("Gemini returned an empty response.")
        return text.strip()
