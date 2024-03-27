import json
from typing import List, Dict, Any
import uuid
import jsonschema
import datetime
from azathoth.prompting.couchdb import CouchDB

class PromptOutput:
    def __init__(self, prompt_output_data: Dict[str, Any], prompt_id: str, test_input_id: str):
        self.validate_data(prompt_output_data)
        if "_id" in prompt_output_data:
            self._id = prompt_output_data["_id"]
            self._rev = prompt_output_data["_rev"]
        if "deleted" in prompt_output_data:
            self.deleted = prompt_output_data["deleted"]
        self.prompt_output_id = prompt_output_data["prompt_output_id"]
        self.prompt_id = prompt_id
        self.test_input_id = test_input_id
        self.output_data = prompt_output_data["output_data"]
        self.timestamp = prompt_output_data.get("timestamp", datetime.now().isoformat())
        self.output_classification = prompt_output_data.get("output_classification", "all")
        
    @staticmethod
    def validate_data(prompt_output_data: Dict[str, Any]):
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": "Prompt Output Schema",
            "type": "object",
            "properties": {
                "$schema": {
                    "type": "string",
                    "description": "The JSON Schema version used to validate the prompt output.",
                },
                "type": {
                    "type": "string",
                    "description": "Always set to 'prompt_output'.",
                },
                "_id": {
                    "type": "string",
                    "description": "An internal identifier for the prompt output.",
                },
                "_rev": {
                    "type": "string",
                    "description": "The revision number of the prompt output document.",
                },
                "prompt_output_id": {
                    "type": "string",
                    "description": "A unique identifier for the prompt output.",
                },
                "output_data": {
                    "type": "object",
                    "description": "The data that the prompt will use to generate a prompt.",
                },
                "deleted": {
                    "type": "boolean",
                    "description": "Whether the prompt output has been deleted.",
                },
                "timestamp": {
                    "type": "string",
                    "description": "The time at which the prompt output was created.",
                },
                "output_classification": {
                    "type": "string",
                    "description": "The classification of the output data.",
                },
                "correctness": {
                    "type": "number",
                    "description": "A number between 0 and 1 indicating the correctness of the output. -1 for incomplete. 0 for incorrect. 1 for correct.",
                },
                "correctness_notes": {
                    "type": "string",
                    "description": "A human-readable description of the correctness of the output.",
                },
            },
            "required": ["$schema", "type", "prompt_output_id", "output_data", "timestamp", "output_classification"],
        }
        jsonschema.validate(prompt_output_data, schema)
        
    def to_dict(self) -> Dict[str, Any]:
        return_val = {
            "_id": self._id,
            "_rev": self._rev,
            "prompt_output_id": self.prompt_output_id,
            "prompt_id": self.prompt_id,
            "test_input_id": self.test_input_id,
            "output_data": self.output_data,
            "timestamp": self.timestamp,
            "output_classification": self.output_classification,
        }
        if "deleted" in self.__dict__:
            return_val["deleted"] = self.deleted
        return return_val
    
    