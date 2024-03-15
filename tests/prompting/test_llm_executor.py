import unittest
from unittest.mock import MagicMock
from azathoth.prompting.llm_executor import LLMExecutor

class TestLLMExecutor(unittest.TestCase):
    def setUp(self):
        self.model_registry_mock = MagicMock()
        self.llm_executor = LLMExecutor(self.model_registry_mock)
        self.prompt = {"model_brand": "test_brand", "model_config": {}}

    def test_execute_prompt(self):
        expected_response = "Processed response"
        handler_mock = MagicMock()
        handler_mock.execute_prompt.return_value = expected_response
        self.model_registry_mock.get_handler.return_value = handler_mock

        result = self.llm_executor.execute_prompt(self.prompt, [])

        self.assertEqual(result, expected_response)
        self.model_registry_mock.get_handler.assert_called_once_with("test_brand")
        handler_mock.execute_prompt.assert_called_once()

if __name__ == '__main__':
    unittest.main()
