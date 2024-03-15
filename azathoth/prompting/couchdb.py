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

    def _make_request(self, method, path, **kwargs):
        url = f"{self.base_url}/{self.db_name}/{path}"
        try:
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
        return self.create_document(goal_data, doc_id=doc_id)

    def create_prompt(self, prompt_data, prompt_goal_id):
        doc_id = self.generate_doc_id("prompt_")
        prompt_data["prompt_goal_id"] = prompt_goal_id
        return self.create_document(prompt_data, doc_id=doc_id)

    def delete_prompt(self, prompt_id, hard_delete=False):
        prompt = self.get_document(prompt_id)
        return self.delete_document(prompt_id, prompt['_rev'], hard_delete=hard_delete)

    def delete_prompt_goal(self, prompt_goal_id, hard_delete=False):
        prompt_goal = self.get_document(prompt_goal_id)
        return self.delete_document(prompt_goal_id, prompt_goal['_rev'], hard_delete=hard_delete)

    def get_prompts_for_goal(self, prompt_goal_id, include_deleted=False):
        prompts = self.query_view("design_doc_name", "prompts_by_goal", key=prompt_goal_id)
        if not include_deleted:
            prompts = [prompt for prompt in prompts if not prompt.get('deleted', False)]
        return prompts

    def filter_test_inputs(self, criteria):
        return self.query_view("design_doc_name", "view_name", **criteria)

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
