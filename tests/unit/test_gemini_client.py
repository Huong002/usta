import json
import unittest
from unittest import mock

from usta.core.llm.gemini import GeminiClient


class GeminiClientTests(unittest.TestCase):
    def test_sends_multiturn_chat_to_gemini_generate_content(self):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps(
            {"candidates": [{"content": {"parts": [{"text": "Try this fix."}]}}]}
        ).encode()
        opener = mock.Mock(return_value=response)

        result = GeminiClient(api_key="private", opener=opener).send_message(
            [{"role": "user", "text": "Why does it fail?"}], "gemini-3.1-flash-lite"
        )

        self.assertEqual(result, "Try this fix.")
        request = opener.call_args.args[0]
        self.assertEqual(request.full_url, "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent")
        self.assertEqual(request.get_header("X-goog-api-key"), "private")
        self.assertEqual(
            json.loads(request.data),
            {"contents": [{"role": "user", "parts": [{"text": "Why does it fail?"}]}]},
        )

    def test_missing_key_is_reported_before_network(self):
        with self.assertRaisesRegex(ValueError, "API key"):
            GeminiClient(api_key="").send_message([], "gemini-3.1-flash-lite")

    def test_empty_model_response_is_reported(self):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'{"candidates": []}'
        with self.assertRaisesRegex(RuntimeError, "empty response"):
            GeminiClient(api_key="key", opener=mock.Mock(return_value=response)).send_message(
                [{"role": "user", "text": "hello"}], "gemini-3.1-flash-lite"
            )
