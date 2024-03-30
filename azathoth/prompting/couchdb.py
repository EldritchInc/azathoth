import uuid
import requests
import json
import csv

class CouchDB:
    def __init__(self, base_url, db_name, username=None, password=None):
        self.base_url = base_url
        self.db_name = db_name
        self.auth = (username, password) if username and password else None
        self.session = requests.Session()
        if self.auth:
            self.session.auth = self.auth
        
    def create_views(self):
        design_doc_id = "_design/design_doc_name"
        design_doc = {
            "_id": design_doc_id,
            "views": {
                "prompts_by_goal": {
                    "map": "function (doc) { if (doc.type === 'prompt' && doc.prompt_goal_id) { emit(doc.prompt_goal_id, doc); } }"
                },
                "all_prompt_goals": {
                    "map": "function (doc) { if (doc.type === 'prompt_goal' && !doc.deleted) { emit(null, doc); } }"
                },
                "test_inputs_by_goal": {
                    "map": "function (doc) { if (doc.type === 'test_input' && !doc.deleted && doc.prompt_goal_id) { emit(doc.prompt_goal_id, doc); } }"
                },
                "filter_test_inputs": {
                    "map": "function (doc) { if (doc.type === 'test_input' && !doc.deleted) { emit(null, doc); } }"
                },
                "all_prompt_outputs_for_test_input": {
                    "map": "function (doc) { if (doc.type === 'prompt_output' && doc.test_input_id) { emit(doc.test_input_id, doc); } }"
                },
                "all_prompt_outputs_for_prompt": {
                    "map": "function (doc) { if (doc.type === 'prompt_output' && doc.prompt_id) { emit(doc.prompt_id, doc); } }"
                }
            }
        }
    
        # Check if the design document already exists
        existing_design_doc = self.get_document(design_doc_id)
        if existing_design_doc:
            # Update the existing design document with the new views
            design_doc["_rev"] = existing_design_doc["_rev"]
            self.update_document(design_doc_id, design_doc)
        else:
            # Create a new design document
            self.create_document(design_doc, doc_id=design_doc_id)

    def _make_request(self, method, path, **kwargs):
        url = f"{self.base_url}/{self.db_name}/{path}"
        try:
            if 'params' in kwargs and 'key' in kwargs['params']:
                # JSON-encode the 'key' parameter to ensure it's correctly formatted for the CouchDB query
                kwargs['params']['key'] = json.dumps(kwargs['params']['key'])
            
            if self.auth:
                kwargs['auth'] = self.auth
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()  # Raises stored HTTPError, if one occurred.
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            return None


    def create_document(self, doc, doc_id=None):
        if doc_id:
            return self._make_request('PUT', f"{doc_id}", json=doc)  # Use PUT for specific doc IDs
        else:
            return self._make_request('POST', '', json=doc)  # POST for server-generated IDs

    def generate_doc_id(self, prefix):
        return f"{prefix}{uuid.uuid4()}"

    def get_document(self, doc_id):
        return self._make_request('GET', doc_id)

    def update_document(self, doc_id, doc):
        if '_rev' not in doc:
            raise ValueError("Document must contain a '_rev' field for updates.")
        return self._make_request('PUT', doc_id, json=doc)

    def delete_document(self, doc_id, rev=None, hard_delete=False):
        if not rev:
            doc = self.get_document(doc_id)
            if not doc:
                print(f"Document {doc_id} not found.")
                return None
            rev = doc['_rev']
        if hard_delete:
            return self._make_request('DELETE', f"{doc_id}?rev={rev}")
        else:
            updated_doc = {"_rev": rev, "deleted": True}
            return self._make_request('PUT', doc_id, json=updated_doc)

    def query_view(self, design_doc, view_name, **kwargs):
        return self._make_request('GET', f"_design/{design_doc}/_view/{view_name}", params=kwargs)

    def create_prompt_goal(self, goal_data):
        doc_id = self.generate_doc_id("prompt_goal_")
        goal_data["type"] = "prompt_goal"
        goal_data["prompt_goal_id"] = doc_id
        return self.create_document(goal_data, doc_id=doc_id)

    def create_prompt(self, prompt_data, prompt_goal_id):
        doc_id = self.generate_doc_id("prompt_")
        prompt_data["prompt_goal_id"] = prompt_goal_id
        prompt_data["type"] = "prompt"
        prompt_data["prompt_id"] = doc_id
        return self.create_document(prompt_data, doc_id=doc_id)

    def delete_prompt(self, prompt_id, hard_delete=False):
        prompt = self.get_document(prompt_id)
        return self.delete_document(prompt_id, prompt['_rev'], hard_delete=hard_delete)

    def delete_prompt_goal(self, prompt_goal_id, hard_delete=False):
        prompt_goal = self.get_document(prompt_goal_id)
        return self.delete_document(prompt_goal_id, prompt_goal['_rev'], hard_delete=hard_delete)

    def get_prompts_for_goal(self, prompt_goal_id, include_deleted=False):
        prompt_query_result = self.query_view("design_doc_name", "prompts_by_goal", key=prompt_goal_id)
        if not prompt_query_result:
            return []
        prompts = prompt_query_result.get('rows', [])
        if not include_deleted:
            prompts = [prompt for prompt in prompts if not prompt.get('value', {}).get('deleted', False)]
        return prompts

    def get_test_inputs_for_goal(self, prompt_goal_id, include_deleted=False):
        test_inputs_result = self.query_view("design_doc_name", "test_inputs_by_goal", key=prompt_goal_id)
        if not test_inputs_result:
            return []
        test_inputs = test_inputs_result.get('rows', [])
        if not include_deleted:
            test_inputs = [test_input for test_input in test_inputs if not test_input.get('deleted', False)]
        return test_inputs

    def get_all_prompt_goals(self):
        prompt_goals = self.query_view("design_doc_name", "all_prompt_goals")
        if prompt_goals:
            return [goal['value'] for goal in prompt_goals['rows']]
        else:
            return []
    
    def get_prompt_goal(self, prompt_goal_id):
        return self.get_document(prompt_goal_id)
    
    def get_prompt(self, prompt_id):
        return self.get_document(prompt_id)
    
    def update_prompt(self, prompt_id, prompt_data):
        return self.update_document(prompt_id, prompt_data)
    
    def update_prompt_goal(self, prompt_goal_id, prompt_goal_data):
        return self.update_document(prompt_goal_id, prompt_goal_data)
    
    def create_test_input(self, test_input_data, prompt_goal_id):
        doc_id = self.generate_doc_id("test_input_")
        test_input_data["prompt_goal_id"] = prompt_goal_id
        test_input_data["type"] = "test_input"
        test_input_data["test_input_id"] = doc_id
        return self.create_document(test_input_data, doc_id=doc_id)
    
    def update_test_input(self, test_input_id, test_input_data):
        return self.update_document(test_input_id, test_input_data)
    
    def delete_test_input(self, test_input_id, hard_delete=False):
        test_input = self.get_document(test_input_id)
        return self.delete_document(test_input_id, test_input['_rev'], hard_delete=hard_delete)

    def filter_test_inputs(self, criteria):
        return self.query_view("design_doc_name", "filter_test_inputs", **criteria)

    def create_prompt_output(self, prompt_output_data, prompt_id, test_input_id):
        doc_id = self.generate_doc_id("prompt_output_")
        prompt_output_data["type"] = "prompt_output"
        prompt_output_data["prompt_id"] = prompt_id
        prompt_output_data["test_input_id"] = test_input_id
        prompt_output_data["prompt_output_id"] = doc_id
        return self.create_document(prompt_output_data, doc_id=doc_id)
        
    def get_prompt_outputs_for_test_input(self, test_input_id):
        prompt_outputs = self.query_view("design_doc_name", "all_prompt_outputs_for_test_input", key=test_input_id)
        return prompt_outputs if prompt_outputs else []
        
    def get_prompt_output(self, prompt_output_id):
        return self.get_document(prompt_output_id)
        
    def update_prompt_output(self, prompt_output_id, prompt_output_data):
        return self.update_document(prompt_output_id, prompt_output_data)
        
    def delete_prompt_output(self, prompt_output_id, hard_delete=False):
        prompt_output = self.get_document(prompt_output_id)
        return self.delete_document(prompt_output_id, prompt_output['_rev'], hard_delete=hard_delete)
        
    def get_prompt_outputs_for_prompt(self, prompt_id):
        prompt_outputs = self.query_view("design_doc_name", "all_prompt_outputs_for_prompt", key=prompt_id)
        return prompt_outputs if prompt_outputs else []
    
    def create_prompt_aggregation(self, prompt_aggregation_data):
        doc_id = self.generate_doc_id("prompt_aggregation_")
        prompt_aggregation_data["type"] = "prompt_aggregation"
        prompt_aggregation_data["prompt_aggregation_id"] = doc_id
        return self.create_document(prompt_aggregation_data, doc_id=doc_id)
    
    def get_prompt_aggregation(self, prompt_aggregation_id):
        return self.get_document(prompt_aggregation_id)
    
    def update_prompt_aggregation(self, prompt_aggregation_id, prompt_aggregation_data):
        return self.update_document(prompt_aggregation_id, prompt_aggregation_data)
    
    def delete_prompt_aggregation(self, prompt_aggregation_id, hard_delete=False):
        prompt_aggregation = self.get_document(prompt_aggregation_id)
        return self.delete_document(prompt_aggregation_id, prompt_aggregation['_rev'], hard_delete=hard_delete)
    
    def get_prompt_aggregations_for_prompt(self, prompt_id):
        prompt_aggregations = self.query_view("design_doc_name", "prompt_aggregations_for_prompt", key=prompt_id)
        return prompt_aggregations if prompt_aggregations else []
    
    def get_prompt_aggregations_for_test_input(self, test_input_id):
        prompt_aggregations = self.query_view("design_doc_name", "prompt_aggregations_for_test_input", key=test_input_id)
        return prompt_aggregations if prompt_aggregations else []    

    def export_data(self, data, destination, format='json'):
        if format == 'json':
            with open(destination, 'w', encoding='utf-8') as file:
                json.dump(data, file, ensure_ascii=False, indent=4)
        elif format == 'csv':
            if not data:
                print("No data to export.")
                return
            with open(destination, 'w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerow(data[0].keys())
                for row in data:
                    writer.writerow(row.values())
        else:
            print(f"Unsupported format: {format}")
