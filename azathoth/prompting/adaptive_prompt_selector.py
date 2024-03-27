import json
from typing import List, Dict, Any
import uuid
import jsonschema
from azathoth.prompting.prompt_goal import PromptGoal
from azathoth.prompting.prompt import Prompt
from azathoth.prompting.prompt_output import PromptOutput
from azathoth.prompting.test_input import TestInput
from azathoth.prompting.prompt_aggregation import PromptAggregation
from azathoth.prompting.couchdb import CouchDB

class AdaptivePromptSelector:
    def __init__(self, adaptive_prompt_selector_data: Dict[str, Any]):
        self.validate_data(adaptive_prompt_selector_data)
        if "_id" in adaptive_prompt_selector_data:
            self._id = adaptive_prompt_selector_data["_id"]
            self._rev = adaptive_prompt_selector_data["_rev"]
        if "deleted" in adaptive_prompt_selector_data:
            self.deleted = adaptive_prompt_selector_data["deleted"]
        self.prompt_goal_id = adaptive_prompt_selector_data["prompt_goal_id"]
        self.classification_name = adaptive_prompt_selector_data["classification_name"] | "all"
        self.classification_schema = adaptive_prompt_selector_data["classification_schema"] | {}
        self.aggregations = adaptive_prompt_selector_data.get("aggregations", [])
        
    @staticmethod
    def validate_data(adaptive_prompt_selector_data: Dict[str, Any]):
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": "Adaptive Prompt Selector Schema",
            "type": "object",
            "properties": {
                "$schema": {
                    "type": "string",
                    "description": "The JSON Schema version used to validate the adaptive prompt selector.",
                },
                "type": {
                    "type": "string",
                    "description": "Always set to 'adaptive_prompt_selector'.",
                },
                "_id": {
                    "type": "string",
                    "description": "An internal identifier for the adaptive prompt selector.",
                },
                "_rev": {
                    "type": "string",
                    "description": "The revision number of the adaptive prompt selector document.",
                },
                "prompt_goal_id": {
                    "type": "string",
                    "description": "The unique identifier of the prompt goal.",
                },
                "classification_name": {
                    "type": "string",
                    "description": "The classification name for the adaptive prompt selector.",
                },
                "classification_schema": {
                    "type": "object",
                    "description": "The schema for the classification data.",
                },
                "timestamp": {
                    "type": "string",
                    "format": "date-time",
                    "description": "ISO 8601 timestamp of when the adaptive prompt selector was created.",
                },
                "deleted": {
                    "type": "boolean",
                    "description": "Whether the adaptive prompt selector has been deleted.",
                },
                "aggregations": {
                    "type": "array",
                    "description": "The list of prompt aggregations.",
                    "items": {
                        "type": "string",
                        "description": "The unique identifier of the prompt aggregation.",
                    },
                },
            },
            "required": ["$schema", "type", "prompt_goal_id", "classification_name", "classification_schema"],
        }
        jsonschema.validate(adaptive_prompt_selector_data, schema)
        
    @staticmethod
    def select_adaptive_prompt_selectors(selectors: List['AdaptivePromptSelector'], context_data: Dict[str, Any]) -> List['AdaptivePromptSelector']:
        """
        Static method to select AdaptivePromptSelectors based on the provided context data.

        :param selectors: A list of AdaptivePromptSelector instances.
        :param context_data: A dictionary containing the context data for the current prompt.
        :return: A list of AdaptivePromptSelectors that match the context data.
        """
        matching_selectors = []
        for selector in selectors:
            try:
                jsonschema.validate(instance=context_data, schema=selector.classification_schema)
                matching_selectors.append(selector)
            except jsonschema.exceptions.ValidationError:
                continue  # This selector's schema does not match the context data

        return matching_selectors
    
    def estimate_prompt_goal_success_rate(self) -> float:
        """
        Find our most likely success rate for the prompt goal associated with this selector's prompt set based on its aggregations.
        """
        total_successes = 0
        total_failures = 0
        total_incompletes = 0
        for aggregation_id in self.aggregations:
            aggregation = CouchDB.get_document(aggregation_id)
            total_successes += aggregation.metrics["successes"]
            total_failures += aggregation.metrics["failures"]
            total_incompletes += aggregation.metrics["incompletes"]
        total_outcomes = total_successes + total_failures + total_incompletes
        if total_outcomes == 0:
            return 0.5
        return total_successes / total_outcomes
    
    def get_best_prompt_optimize_for_success_rate(self) -> Prompt:
        
        prompt_aggregations = []
        for aggregation_id in self.aggregations:
            prompt_aggregations.append(CouchDB.get_prompt_aggregation(aggregation_id))
            
        best_prompt_id = None
        best_success_rate = 0
        for prompt_aggregation in prompt_aggregations:
            prompt_success_rate = prompt_aggregation.metrics["successes"] / prompt_aggregation.metrics["total"]
            if prompt_success_rate > best_success_rate:
                best_prompt_id = prompt_aggregation.prompt_id
                best_success_rate = prompt_success_rate
        return CouchDB.get_prompt(best_prompt_id)
    
    def get_best_prompt_optimize_for_success_rate_and_attempts(self) -> Prompt:
            
        prompt_aggregations = []
        for aggregation_id in self.aggregations:
            prompt_aggregations.append(CouchDB.get_prompt_aggregation(aggregation_id))
            
        best_prompt_id = None
        best_success_rate = 0
        best_attempts = 0
        for prompt_aggregation in prompt_aggregations:
            prompt_success_rate = prompt_aggregation.metrics["successes"] / prompt_aggregation.metrics["total"]
            prompt_attempts = prompt_aggregation.metrics["attempts"]
            if prompt_success_rate > best_success_rate:
                best_prompt_id = prompt_aggregation.prompt_id
                best_success_rate = prompt_success_rate
                best_attempts = prompt_attempts
            elif prompt_success_rate >= best_success_rate - 0.01 and prompt_success_rate < best_success_rate + 0.1:
                if prompt_attempts < best_attempts:
                    best_prompt_id = prompt_aggregation.prompt_id
                    best_success_rate = prompt_success_rate
                    best_attempts = prompt_attempts
        return CouchDB.get_prompt(best_prompt_id)
        
    def get_best_prompt_optimize_for_success_rate_and_cost(self) -> Prompt:
        
        prompt_aggregations = []
        for aggregation_id in self.aggregations:
            prompt_aggregations.append(CouchDB.get_prompt_aggregation(aggregation_id))
            
        best_prompt_id = None
        best_cost = float("inf")
        best_success_rate = 0
        for prompt_aggregation in prompt_aggregations:
            prompt_cost = prompt_aggregation.metrics["average_cost"]
            if prompt_cost < best_cost:
                best_prompt_id = prompt_aggregation.prompt_id
                best_cost = prompt_cost
                best_success_rate = prompt_aggregation.metrics["successes"] / prompt_aggregation.metrics["total"]
            elif prompt_cost >= best_cost - 0.01 and prompt_cost < best_cost + 0.1:
                prompt_success_rate = prompt_aggregation.metrics["successes"] / prompt_aggregation.metrics["total"]
                if prompt_success_rate > best_success_rate:
                    best_prompt_id = prompt_aggregation.prompt_id
                    best_cost = prompt_cost
                    best_success_rate = prompt_success_rate
        return CouchDB.get_prompt(best_prompt_id)