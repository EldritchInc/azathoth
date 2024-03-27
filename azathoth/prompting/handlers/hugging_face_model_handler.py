from azathoth.prompting.handlers.base_model_handler import BaseModelHandler
import requests
import json
from azathoth.util.logging import error_log, info_log

def load_config():
    with open('../config.json') as f:
        return json.load(f)

config = load_config()
class HuggingFaceModelHandler(BaseModelHandler):
    def __init__(self):
        self.api_token = config["api"]["hugging_face_token"]
        if not self.api_token:
            raise ValueError("API token for Hugging Face is not provided in the model config.")

    def execute_prompt(self, prompt, command_conversation):
        """
        Executes a prompt on a Hugging Face model.
        """
        try:
            payload = self.prepare_payload(prompt, command_conversation)
            response = self.send_request(payload)
            return self.process_response(response)
        except Exception as e:
            error_log(f"Error executing prompt on Hugging Face model: {e}")
            raise

    def send_request(self, payload):
        """
        Sends a POST request to the Hugging Face API.
        """
        headers = {"Authorization": f"Bearer {self.api_token}"}
        response = requests.post(self.model_config["url"], headers=headers, json=payload)
        info_log(f"Hugging Face API response: {response.status_code}")

        if response.status_code != 200:
            error_log(f"Error from Hugging Face API: {response.text}")
            response.raise_for_status()

        return response.json()

    def prepare_payload(self, prompt, command_conversation):
        """
        Prepares the payload for a Hugging Face API request.
        """
        command_conversation_str = json.dumps(command_conversation)
        response_tokens = prompt.get("response_tokens", 50)
        temperature = prompt.get("temperature", 1.0)

        payload = {
            "inputs": command_conversation_str,
            "parameters": {
                "max_new_tokens": response_tokens,
                "temperature": temperature,
            }
        }
        return payload

    def process_response(self, response):
        """
        Processes the response from the Hugging Face API.
        """
        if isinstance(response, dict) and "generated_text" in response:
            return self.trim_repeating_pattern(response["generated_text"])
        elif isinstance(response, str):
            return self.trim_repeating_pattern(response)
        else:
            error_log(f"Unexpected response format: {response}")
            return response

    def trim_repeating_pattern(self, text, min_pattern_length=15):
        """
        Trims repeating patterns from the response text.
        """
        # Implement the logic to trim repeating patterns from the text
        # This method remains as previously defined or can be updated based on new requirements
        return text
