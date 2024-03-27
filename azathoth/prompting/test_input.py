import re
import json
from datetime import datetime
import jsonschema
from azathoth.prompting.couchdb import CouchDB
from typing import List, Dict, Any

class TestInput:
    def __init__(self, test_input_data: Dict[str, Any], prompt_goal_id: str):
        self.validate_data(test_input_data)
        if "_id" in test_input_data:
            self._id = test_input_data["_id"]
            self._rev = test_input_data["_rev"]
        if "deleted" in test_input_data:
            self.deleted = test_input_data["deleted"]
        ## the above is an example of my repeating code where I want the decision to be obvious until it can find a happier and more permanent home
        self.test_input_id = test_input_data["test_input_id"]
        self.event_data = test_input_data["event_data"]
        self.prompt_goal_id = prompt_goal_id
        self.timestamp = test_input_data.get("timestamp", datetime.now().isoformat())
        self.event_classification = test_input_data.get("event_classification", "all")
        
    @staticmethod
    def validate_data(test_input_data: Dict[str, Any]):
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": "Test Input Schema",
            "type": "object",
            "properties": {
                "$schema": {
                    "type": "string",
                    "description": "The JSON Schema version used to validate the test input.",
                },
                "type": {
                    "type": "string",
                    "description": "Always set to 'test_input'.",
                },
                "_id": {
                    "type": "string",
                    "description": "An internal identifier for the test input.",
                },
                "_rev": {
                    "type": "string",
                    "description": "The revision number of the test input document.",
                },
                "test_input_id": {
                    "type": "string",
                    "description": "A unique identifier for the test input.",
                },
                "event_data": {
                    "type": "object",
                    "description": "The data that the prompt goal will use to generate a prompt.",
                },
                "timestamp": {
                    "type": "string",
                    "description": "The time at which the test input was created.",
                },
                "event_classification": {
                    "type": "string",
                    "description": "The classification of the event data.",
                },
            },
            "required": ["$schema", "type", "test_input_id", "event_data"],
        }
        jsonschema.validate(test_input_data, schema)
        
    