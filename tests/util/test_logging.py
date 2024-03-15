import unittest
from azathoth.util.logging import format_log_message
from datetime import datetime

class TestLogging(unittest.TestCase):
    def test_format_log_message(self):
        message = "Test message"
        level = "info"
        # Assuming format_log_message does not include milliseconds
        expected_time = datetime.now().replace(microsecond=0).isoformat()
        expected = f"{expected_time} [{level}] {message}"
        # Because the exact time match might be tricky due to execution time,
        # consider mocking datetime.now() or testing components separately.
        result = format_log_message(message, level)
        self.assertTrue(result.startswith(expected_time))
        self.assertIn(f"[{level}] {message}", result)

if __name__ == '__main__':
    unittest.main()
