import json
from azathoth.prompting.handlers.base_model_handler import BaseModelHandler
from openai import OpenAI
from azathoth.util.logging import error_log, info_log

def load_config():
    with open('../config.json') as f:
        return json.load(f)

config = load_config()
class OpenAIModelHandler(BaseModelHandler):
    def __init__(self):
        self.api_token = config["api"]["openai_key"]
        if not self.api_token:
            raise ValueError("API token for OpenAI is not provided in the model config.")
        self.client = OpenAI(api_key=self.api_token)

    def execute_prompt(self, prompt, command_conversation):
        """
        Executes a prompt on an OpenAI model.
        """
        try:
            response = self.client.chat.completions.create(
                model=prompt["model"],
                messages=command_conversation,
                max_tokens=int(prompt.get("response_tokens", 50)),
                temperature=float(prompt.get("temperature", 1.0))
            )
            return self.process_response(response)
        except Exception as e:
            error_log(f"Error executing prompt on OpenAI model: {e}")
            raise

    def process_response(self, response):
        """
        Processes the response from the OpenAI API.
        """
        if response and response.choices:
            return response.choices[0].message.content
        else:
            error_log(f"Unexpected response format or empty response from OpenAI: {response}")
            return ""
