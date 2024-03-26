import unittest
from unittest.mock import MagicMock, patch
from azathoth.prompting.llm_executor import LLMExecutor
from azathoth.prompting.handlers.base_model_handler import BaseModelHandler

class TestLLMExecutor(unittest.TestCase):
    def setUp(self):
        self.model_registry_mock = MagicMock()
        self.llm_executor = LLMExecutor(self.model_registry_mock)
        self.prompt = {"model_brand": "test_brand", "model_config": {}}

    def test_execute_prompt(self):
        expected_response = "Processed response"
        execute_prompt_response = "Response"

        handler_class_mock = MagicMock()
        handler_instance_mock = MagicMock()
        handler_instance_mock.execute_prompt.return_value = execute_prompt_response
        handler_instance_mock.process_response.return_value = expected_response
        handler_class_mock.return_value = handler_instance_mock

        self.model_registry_mock.get_handler.return_value = handler_class_mock

        result = self.llm_executor.execute_prompt(self.prompt, [])

        self.assertEqual(result, expected_response)
        self.model_registry_mock.get_handler.assert_called_once_with("test_brand")
        handler_class_mock.assert_called_once_with(self.prompt["model_config"])
        handler_instance_mock.execute_prompt.assert_called_once_with(self.prompt, [])
        handler_instance_mock.process_response.assert_called_once_with(execute_prompt_response)

if __name__ == '__main__':
    unittest.main()