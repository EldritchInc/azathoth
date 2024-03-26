from flask import Flask, send_from_directory, request, jsonify
from flask_cors import CORS
import os
from azathoth.prompting.prompt_manager import PromptManager
from azathoth.prompting.couchdb import CouchDB

app = Flask(__name__, static_folder='ui/prompt-ui/build')
CORS(app, resources={r"/*": {"origins": "*"}})

couch_user_name = os.environ.get('COUCH_USER_NAME')
couch_password = os.environ.get('COUCH_PASSWORD')

db = CouchDB('http://localhost:5984', 'azathoth', couch_user_name, couch_password)
db.create_views()
prompt_manager = PromptManager(db)

# Serve React App
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    if path != "" and os.path.exists(app.static_folder + '/' + path):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')

# API routes
@app.route('/prompt-goals/<string:prompt_goal_id>/prompts', methods=['GET', 'POST'])
def prompts(prompt_goal_id):
    if request.method == 'GET':
        prompts = prompt_manager.get_all_prompts_for_goal(prompt_goal_id)
        return jsonify([prompt.__dict__ for prompt in prompts])
    elif request.method == 'POST':
        prompt_data = request.get_json()
        prompt = prompt_manager.create_prompt(prompt_goal_id, prompt_data)
        return jsonify(prompt.__dict__)

@app.route('/prompt-goals', methods=['GET', 'POST', 'PUT'])
def prompt_goals():
    if request.method == 'GET':
        prompt_goals = prompt_manager.get_all_prompt_goals()
        return jsonify([prompt_goal.__dict__ for prompt_goal in prompt_goals])
    elif request.method == 'POST':
        prompt_goal_data = request.get_json()
        prompt_goal = prompt_manager.create_prompt_goal(prompt_goal_data)
        return jsonify(prompt_goal.__dict__)
    elif request.method == 'PUT':
        prompt_goal_data = request.get_json()
        prompt_goal = prompt_manager.update_prompt_goal(prompt_goal_data)
        return jsonify(prompt_goal.__dict__)
@app.route('/prompt-goals/<string:prompt_goal_id>', methods=['GET', 'PUT'])
def prompt_goal(prompt_goal_id):
    if request.method == 'GET':
        prompt_goal = prompt_manager.get_prompt_goal(prompt_goal_id)
        return jsonify(prompt_goal.__dict__)
    elif request.method == 'PUT':
        prompt_goal_data = request.get_json()
        prompt_goal = prompt_manager.update_prompt_goal(prompt_goal_data)
        return jsonify(prompt_goal.__dict__)
@app.route('/run-tests', methods=['POST', 'OPTIONS'])
def run_tests():
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        return '', 204, headers
    elif request.method == 'POST':
        test_data = request.get_json()
        prompt_id = test_data['prompt_id']
        test_cases = test_data['test_cases']

        # Retrieve the prompt from the database using the prompt_id
        prompt = prompt_manager.get_prompt(prompt_id)

        # Run the tests using the prompt and test cases
        test_results = []
        for test_case in test_cases:
            context = test_case['context']
            expected_response = test_case['expected_response']

            # Execute the prompt with the given context
            actual_response = prompt_manager.execute_prompt(prompt_id, context)

            # Compare the actual response with the expected response
            passed = actual_response == expected_response

            test_results.append({'passed': passed, 'actual_response': actual_response})

        return jsonify(test_results)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)