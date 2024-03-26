import re
import json
from datetime import datetime
import jsonschema
from azathoth.prompting.couchdb import CouchDB
from typing import List, Dict, Any


class Prompt:
    def __init__(self, prompt_data: Dict[str, Any], prompt_goal_id: str):
        self.validate_data(prompt_data)
        self.prompt_id = prompt_data["prompt_id"]
        self.prompt_version = prompt_data["prompt_version"]
        self.model = prompt_data["model"]
        self.model_brand = prompt_data["model_brand"]
        self.needs = prompt_data["needs"]
        self.response_tokens = prompt_data["response_tokens"]
        self.temperature = prompt_data["temperature"]
        self.prompt_text = prompt_data["prompt"]
        self.chat = prompt_data["chat"]
        self.prompt_goal_id = prompt_goal_id
        self.response_history: List[Dict[str, Any]] = []

    @staticmethod
    def validate_data(prompt_data: Dict[str, Any]):
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": "Prompt Configuration Schema",
            "type": "object",
            "properties": {
                "$schema": {"type": "string"},
                "type": {
                    "type": "string",
                    "description": "Always set to 'prompt'.",
                },
                "prompt_id": {"type": "string"},
                "prompt_name": {"type": "string"},
                "prompt_version": {"type": "integer"},
                "model": {"type": "string"},
                "model_brand": {"type": "string"},
                "needs": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "response_tokens": {"type": "integer"},
                "temperature": {"type": "number"},
                "prompt": {"type": "string"},
                "chat": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "chat_element_id": {"type": "string"},
                            "message": {"type": "string"},
                            "jump_regex": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "regex": {"type": "string"},
                                        "jump": {"type": "string"}
                                    },
                                    "required": ["regex", "jump"]
                                }
                            },
                            "stop_regex": {
                                "type": "array",
                                "items": {"type": "string"}
                            }
                        },
                        "required": ["chat_element_id", "message"]
                    }
                }
            },
            "required": ["prompt_id", "prompt_version", "model", "model_brand", "needs", "response_tokens", "temperature", "prompt", "chat"],
            "additionalProperties": False
        }
        jsonschema.validate(prompt_data, schema)

    def execute(self, context: dict) -> str:
        # Implementing the core logic to simulate the interaction with a model
        current_timestamp = datetime.now().timestamp()
        context['prompt_goal_input_timestamp'] = str(current_timestamp)
        command_conversation = [{"role": "system", "content": self.prompt_text.format(**context)}]
        candidate_result, chat_index, end_met = "", 0, False

        while not end_met:
            if len(self.chat) > chat_index:
                chat_message_with_data, command_conversation, candidate_result = self.process_chat_message(chat_index, context, command_conversation)
                end_met, chat_index = self.evaluate_end_conditions(chat_index, candidate_result)
            else:
                candidate_result = self.generate_response(command_conversation).strip()
                end_met = True

        return self.clean_up_response(candidate_result)
    
    def process_chat_message(self, chat_index: int, context: dict, command_conversation: List[Dict[str, Any]]):
        chat_element = self.chat[chat_index]
        chat_message_with_data = chat_element["message"].format(**context)
        command_conversation.append({"role": "user", "content": chat_message_with_data})
        completion = self.generate_response(command_conversation)
        candidate_result = completion.strip()
        context["candidate_result"] = candidate_result
        command_conversation.append({"role": "assistant", "content": candidate_result})
        return chat_message_with_data, command_conversation, candidate_result

    def evaluate_end_conditions(self, chat_index: int, candidate_result: str):
        chat_element = self.chat[chat_index]
        has_stop = "stop_regex" in chat_element
        end_met = has_stop and any(re.search(pattern, candidate_result) for pattern in chat_element["stop_regex"])
        return end_met, chat_index + 1 if not has_stop or not end_met else chat_index


    def generate_response(self, context: dict) -> str:
        # Implement the logic to generate a response using the specified model and parameters
        # This method will interact with the actual language model or API to generate the response
        pass

    def update(self, prompt_data: Dict[str, Any]):
        # Update the prompt data
        self.validate_data(prompt_data)
        self.prompt_name = prompt_data["prompt_name"]
        self._id = prompt_data["_id"]
        self._rev = prompt_data["_rev"]
        self.prompt_version = prompt_data["prompt_version"]
        self.model = prompt_data["model"]
        self.model_brand = prompt_data["model_brand"]
        self.needs = prompt_data["needs"]
        self.response_tokens = prompt_data["response_tokens"]
        self.temperature = prompt_data["temperature"]
        self.prompt_text = prompt_data["prompt"]
        self.chat = prompt_data["chat"]

    def optimize(self) -> Dict[str, Any]:
        # Optimize the prompt based on the response_history and return the optimized prompt data
        pass

    def get_response_history(self) -> List[Dict[str, Any]]:
        return self.response_history
    
    def store_response(self, context: dict, response: str):
        # Enhanced to store response history in CouchDB
        response_record = {"context": context, "response": response, "prompt_id": self.prompt_id}
        CouchDB.create_document(response_record, doc_id=CouchDB.generate_doc_id("response_"))
        self.response_history.append(response_record)

    def load_response_history(self):
        # Load response history for this prompt from CouchDB
        self.response_history = CouchDB.get_prompts_for_goal(self.prompt_id, include_deleted=False)