from typing import List, Dict, Any
import uuid
import jsonschema
from azathoth.prompting.prompt import Prompt
from azathoth.prompting.couchdb import create_prompt_goal, delete_prompt, filter_test_inputs, export_data

class PromptGoal:
    def __init__(self, prompt_goal_data: Dict[str, Any]):
        self.validate_data(prompt_goal_data)
        self.prompt_goal_id = prompt_goal_data["prompt_goal_id"]
        self.desired_outcomes = prompt_goal_data["desired_outcomes"]
        self.needs = prompt_goal_data["needs"]
        self.prompt_goal_description = prompt_goal_data.get(
            "prompt_goal_description", ""
        )
        self.response_schema = prompt_goal_data["response_schema"]
        self.prompts: List[Prompt] = []
        self.test_inputs: List[Dict[str, Any]] = []
        self.statistics: Dict[str, Any] = {}

    @staticmethod
    def validate_data(prompt_goal_data: Dict[str, Any]):
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": "Prompt Goal Schema",
            "type": "object",
            "properties": {
                "$schema": {
                    "type": "string",
                    "description": "The JSON Schema version used to validate the prompt goal.",
                },
                "prompt_goal_id": {
                    "type": "string",
                    "description": "A unique identifier for the prompt goal.",
                },
                "desired_outcomes": {
                    "type": "string",
                    "description": "A detailed description of what achieving this prompt goal entails.",
                },
                "needs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "A list of required inputs or information needs to achieve the desired outcomes.",
                },
                "prompt_goal_description": {
                    "type": "string",
                    "description": "An optional detailed description of the prompt goal, providing additional context or clarification.",
                },
                "response_schema": {
                    "type": "object",
                    "description": "A JSON Schema to validate the format of the response. This schema can define any valid JSON structure.",
                    "examples": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ],
                    "additionalProperties": True,
                },
            },
            "required": [
                "prompt_goal_id",
                "desired_outcomes",
                "needs",
                "response_schema",
            ],
            "additionalProperties": False,
        }

        jsonschema.validate(prompt_goal_data, schema)

    def create_prompt(self, prompt_text: str, model: str, parameters: dict) -> Prompt:
        prompt_id = str(uuid.uuid4())
        prompt = Prompt(prompt_id, prompt_text, model, parameters, self)
        self.prompts.append(prompt)
        return prompt

    def get_prompts(self) -> List[Prompt]:
        return self.prompts

    def get_statistics(self) -> Dict[str, Any]:
        return self.statistics

    def update_statistics(self, statistics: Dict[str, Any]):
        self.statistics.update(statistics)

    def add_test_input(self, context: dict, response: str, is_correct: bool = None):
        test_input = {
            "test_input_id": str(uuid.uuid4()),
            "context": context,
            "response": response,
            "is_correct": is_correct,
        }
        self.test_inputs.append(test_input)

    def get_test_inputs(self) -> List[Dict[str, Any]]:
        return self.test_inputs

    def update_test_input(self, test_input_id: str, is_correct: bool):
        for test_input in self.test_inputs:
            if test_input["test_input_id"] == test_input_id:
                test_input["is_correct"] = is_correct
                break
            
    def delete_prompt(self, prompt_id: str):
        self.prompts = [prompt for prompt in self.prompts if prompt.prompt_id != prompt_id]
        delete_prompt(self.prompt_goal_id, prompt_id)

    def filter_test_inputs(self, criteria: Dict[str, Any]) -> List[Dict[str, Any]]:
        filtered_inputs = filter_test_inputs(self.prompt_goal_id, criteria)
        return filtered_inputs

    def export_data(self, format: str) -> str:
        exported_data = export_data(self.prompt_goal_id, format)
        return exported_data