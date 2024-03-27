import json
from typing import List, Dict, Any
import numpy as np
from datetime import datetime, timezone
import uuid
import jsonschema
from azathoth.prompting.prompt import Prompt
from azathoth.prompting.couchdb import CouchDB


class PromptAggregation:
    def __init__(self):
        self.aggregates = {}

    @staticmethod
    def validate_data(prompt_aggregation_data: Dict[str, Any]):
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": "PromptAggregation",
            "type": "object",
            "properties": {
                "_id": {
                    "type": "string",
                    "description": "A unique identifier for the aggregation document.",
                },
                "type": {
                    "type": "string",
                    "description": "Document type, set to 'PromptAggregation'.",
                    "enum": ["PromptAggregation"],
                },
                "prompt_id": {
                    "type": "string",
                    "description": "The unique identifier of the prompt.",
                },
                "test_input_id": {
                    "type": "string",
                    "description": "The unique identifier of the test input.",
                },
                "timestamp": {
                    "type": "string",
                    "format": "date-time",
                    "description": "ISO 8601 timestamp of when the aggregation was performed.",
                },
                "metrics": {
                    "type": "object",
                    "properties": {
                        "successes": {
                            "type": "integer",
                            "description": "Total number of successful outcomes.",
                        },
                        "failures": {
                            "type": "integer",
                            "description": "Total number of failed outcomes.",
                        },
                        "incompletes": {
                            "type": "integer",
                            "description": "Total number of incomplete outcomes.",
                        },
                        "total": {
                            "type": "integer",
                            "description": "Total number of attempts.",
                        },
                        "average_cost": {
                            "type": "number",
                            "description": "Average cost of the prompts.",
                        },
                        "cost_std_deviation": {
                            "type": "number",
                            "description": "Standard deviation of the cost.",
                        },
                        "average_response_time": {
                            "type": "number",
                            "description": "Average response time in milliseconds.",
                        },
                        "response_time_std_deviation": {
                            "type": "number",
                            "description": "Standard deviation of the response times in milliseconds.",
                        },
                        "average_tokens": {
                            "type": "number",
                            "description": "Average number of tokens used.",
                        },
                        "tokens_std_deviation": {
                            "type": "number",
                            "description": "Standard deviation of the number of tokens used.",
                        },
                    },
                    "required": [
                        "successes",
                        "failures",
                        "incompletes",
                        "total",
                        "average_cost",
                        "cost_std_deviation",
                        "average_response_time",
                        "response_time_std_deviation",
                        "average_tokens",
                        "tokens_std_deviation",
                    ],
                },
            },
            "required": [
                "_id",
                "type",
                "prompt_id",
                "test_input_id",
                "timestamp",
                "metrics",
            ],
        }
        jsonschema.validate(prompt_aggregation_data, schema)

    def add_prompt_output(self, prompt_output):
        """
        Add a PromptOutput instance to the aggregation.
        :param prompt_output: An instance of PromptOutput.
        """
        key = (prompt_output.prompt_id, prompt_output.test_input_id)
        if key not in self.aggregates:
            self.aggregates[key] = {
                "costs": [],
                "response_times": [],
                "tokens": [],
                "successes": 0,
                "failures": 0,
                "incompletes": 0,
                "total": 0,
            }

        agg = self.aggregates[key]
        agg["costs"].append(prompt_output.cost)
        agg["response_times"].append(prompt_output.response_time)
        agg["tokens"].append(prompt_output.token_count)
        agg["total"] += 1
        # Update successes, failures, and incompletes as needed
        # This assumes you have a way to determine these from your PromptOutput instances
        if prompt_output.correctness == -1:
            agg["incompletes"] += 1
        elif prompt_output.correctness > 0.5:
            agg["successes"] += 1
        else:
            agg["failures"] += 1
        

    def calculate_statistics(self):
        """
        Calculate average and standard deviation for each metric.
        """
        for key, agg in self.aggregates.items():
            agg["average_cost"] = np.mean(agg["costs"])
            agg["cost_std_deviation"] = np.std(
                agg["costs"], ddof=1
            )  # ddof=1 for sample standard deviation
            agg["average_response_time"] = np.mean(agg["response_times"])
            agg["response_time_std_deviation"] = np.std(agg["response_times"], ddof=1)
            agg["average_tokens"] = np.mean(agg["tokens"])
            agg["tokens_std_deviation"] = np.std(agg["tokens"], ddof=1)

    def to_couchdb_document(self):
        """
        Prepare aggregated data for CouchDB storage according to the schema.
        :return: A list of documents ready for storage in CouchDB.
        """
        documents = []
        for key, agg in self.aggregates.items():
            prompt_id, test_input_id = key
            document = {
                "_id": str(uuid.uuid4()),
                "type": "PromptAggregation",
                "prompt_id": prompt_id,
                "test_input_id": test_input_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metrics": {
                    "successes": agg["successes"],
                    "failures": agg["failures"],
                    "incompletes": agg["incompletes"],
                    "total": agg["total"],
                    "average_cost": agg["average_cost"],
                    "cost_std_deviation": agg["cost_std_deviation"],
                    "average_response_time": agg["average_response_time"],
                    "response_time_std_deviation": agg["response_time_std_deviation"],
                    "average_tokens": agg["average_tokens"],
                    "tokens_std_deviation": agg["tokens_std_deviation"],
                },
            }
            documents.append(document)
        return documents


# Example usage:
# Assuming you have instances of PromptOutput, you would add them to the aggregator like so:
# aggregator = PromptAggregation()
# aggregator.add_prompt_output(prompt_output_instance)
# Once all PromptOutput instances are added, calculate the statistics:
# aggregator.calculate_statistics()
# Now, prepare the documents for CouchDB:
# documents_to_store = aggregator.to_couchdb_document()
