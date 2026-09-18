import unittest

from error_classifier import classify_error


class ErrorClassifierTests(unittest.TestCase):
    def test_invalid_api_key_is_clean(self):
        status_code, message = classify_error(
            RuntimeError("401 Unauthorized: invalid_api_key")
        )
        self.assertEqual(status_code, 401)
        self.assertEqual(
            message,
            "Authentication with the AI provider failed. Please check the configured API key.",
        )
        self.assertNotIn("invalid_api_key", message)
        self.assertNotIn("Unauthorized", message)

    def test_unknown_error_is_truncated_and_prefixed(self):
        status_code, message = classify_error(
            RuntimeError("some provider detail that should be surfaced")
        )
        self.assertEqual(status_code, 502)
        self.assertTrue(message.startswith("AI service error: "))


if __name__ == "__main__":
    unittest.main()
