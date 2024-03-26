import json
from typing import List, Dict, Any
import uuid
import jsonschema
from azathoth.prompting.prompt import Prompt
from azathoth.prompting.couchdb import CouchDB

class PromptGoal:
    def __init__(self, prompt_goal_data: Dict[str, Any]):
        self.validate_data(prompt_goal_data)
        if "_id" in prompt_goal_data:
            self._id = prompt_goal_data["_id"]
            self._rev = prompt_goal_data["_rev"]
        if "deleted" in prompt_goal_data:
            self.deleted = prompt_goal_data["deleted"]
        self.prompt_goal_id = prompt_goal_data["prompt_goal_id"]
        self.prompt_goal_name = prompt_goal_data["prompt_goal_name"]
        self.desired_outcomes = prompt_goal_data["desired_outcomes"]
        self.needs = prompt_goal_data["needs"]
        if "wants" in prompt_goal_data:
            self.wants = prompt_goal_data["wants"]
        self.prompt_goal_description = prompt_goal_data.get(
            "prompt_goal_description", ""
        )
        self.response_schema = prompt_goal_data["response_schema"]
        # Initialize statistics with default values.
        self.statistics: Dict[str, Any] = [{
            "score": 0,
            "attempts": 0,
            "classification_name": "all",
            "last_check": "",
            "prompt_id": "",
            "successes": 0
        }]

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
                "type": {
                    "type": "string",
                    "description": "Always set to 'prompt_goal'.",
                },
                "_id": {
                    "type": "string",
                    "description": "An internal identifier for the prompt goal.",
                },
                "_rev": {
                    "type": "string",
                    "description": "The revision number of the prompt goal document.",
                },
                "prompt_goal_name": {
                    "type": "string",
                    "description": "A human-readable name for the prompt goal.",
                },
                "statistics": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "A list of statistics objects, each containing a 'name' and 'value' field.",
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
                "wants": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "A list of optional inputs or information wants to achieve the desired outcomes.",
                },
                "prompt_goal_description": {
                    "type": "string",
                    "description": "An optional detailed description of the prompt goal, providing additional context or clarification.",
                },
                "deleted": {
                    "type": "boolean",
                    "description": "A flag indicating whether the prompt goal has been deleted.",
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
                "statistics",
                "prompt_goal_name"
            ],
            "additionalProperties": False,
        }
        
        if "response_schema" in prompt_goal_data:
            response_schema = prompt_goal_data["response_schema"]
            response_schema_object = None
            if isinstance(response_schema, dict):
                response_schema_object = response_schema
                for key, value in response_schema.items():
                    if isinstance(value, str):
                        try:
                            response_schema_object[key] = json.loads(value)
                        except json.JSONDecodeError as e:
                            pass
            
            if isinstance(response_schema, str):
                try:
                    response_schema_object = json.loads(response_schema)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid response schema: {e}")
                if response_schema_object:
                    prompt_goal_data["response_schema"] = response_schema_object

        try:
            jsonschema.validate(prompt_goal_data, schema)
        except jsonschema.ValidationError as e:
            # If validation fails, throw an error to be caught by the caller.
            raise ValueError(f"Invalid prompt goal data: {e.message}")

    def create_prompt(self, prompt_text: str, model: str, parameters: dict) -> Prompt:
        prompt_id = str(uuid.uuid4())
        prompt = Prompt(prompt_id, prompt_text, model, parameters, self)
        self.prompts.append(prompt)
        return prompt

    def get_statistics(self) -> Dict[str, Any]:
        return self.statistics

    def update_statistics(self, statistics: Dict[str, Any]):
        # Assuming `statistics` contains the exact structure to update.
        self.statistics.update(statistics)

    def export_data(self, format: str) -> str:
        try:
            exported_data = CouchDB.export_data(self.prompt_goal_id, format)
            return exported_data
        except Exception as e:
            # Handle or log the error based on your application's logging strategy.
            raise RuntimeError(f"Failed to export data: {e}")
