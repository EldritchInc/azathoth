from flask import Flask, send_from_directory, request, jsonify
from flask_cors import CORS
import os
from azathoth.prompting.prompt_manager import PromptManager
from azathoth.prompting.couchdb import CouchDB
from azathoth.prompting.handlers.openai_model_handler import OpenAIModelHandler
from azathoth.prompting.handlers.hugging_face_model_handler import HuggingFaceModelHandler
from azathoth.prompting.model_registry import ModelRegistry
import json
from azathoth.util.logging import debug_log, set_log_level

set_log_level('debug')

def load_config():
    with open('config.json') as f:
        return json.load(f)

config = load_config()



app = Flask(__name__, static_folder='ui/prompt-ui/build')
CORS(app, resources={r"/*": {"origins": "*"}})

db_host = config['database']['host']
db_port = config['database']['port']
db_name = config['database']['name']
db_user = config['database']['user']
db_password = config['database']['password']
db_connect_string = f'http://{db_host}:{db_port}'

db = CouchDB(db_connect_string, db_name, db_user, db_password)
db.create_views()
prompt_manager = PromptManager(db)

# Initialize the ModelRegistry
model_registry = ModelRegistry()

# Assuming you've implemented get_models methods in your handlers
openai_handler = OpenAIModelHandler()
huggingface_handler = HuggingFaceModelHandler()

# Register handlers with their respective models
model_registry.register_handler("OpenAI", openai_handler, openai_handler.get_models())
model_registry.register_handler("HuggingFace", huggingface_handler, huggingface_handler.get_models())

# Serve React App
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    debug_log('Serving path: ' + path)
    if path != "" and os.path.exists(app.static_folder + '/' + path):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')
    
@app.route('/models/<string:model_brand>', methods=['GET'])
def get_models_for_brand(model_brand):
    debug_log('Getting models for brand: ' + model_brand)
    try:
        models = model_registry.get_models_by_brand(model_brand)
        return jsonify(models)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    
@app.route('/models', methods=['GET'])
def get_models():
    debug_log('Getting all model brands')
    model_brands = model_registry.get_brands()
    return jsonify(model_brands)

# API routes
@app.route('/prompt-goals/<string:prompt_goal_id>/prompts', methods=['GET', 'POST'])
def prompts(prompt_goal_id):
    debug_log('Getting prompts for prompt goal id: ' + prompt_goal_id)
    debug_log('Request method: ' + request.method)
    if request.method == 'GET':
        prompts = prompt_manager.get_all_prompts_for_goal(prompt_goal_id)
        return jsonify([prompt.__dict__ for prompt in prompts])
    elif request.method == 'POST':
        debug_log('Creating prompt')
        debug_log(request.get_json())
        debug_log('Prompt goal id: ' + prompt_goal_id)
        prompt_data = request.get_json()
        prompt = prompt_manager.create_prompt(prompt_goal_id, prompt_data)
        return jsonify(prompt.__dict__)
    
@app.route('/prompt-goals/<string:prompt_goal_id>/test-inputs', methods=['GET', 'POST'])
def test_inputs(prompt_goal_id):
    debug_log('Getting test inputs for prompt goal id: ' + prompt_goal_id)
    debug_log('Request method: ' + request.method)
    if request.method == 'GET':
        test_inputs = prompt_manager.get_all_test_inputs_for_goal(prompt_goal_id)
        return jsonify([test_input.__dict__ for test_input in test_inputs])
    elif request.method == 'POST':
        debug_log('Creating test input')
        debug_log(request.get_json())
        debug_log('Prompt goal id: ' + prompt_goal_id)
        test_input_data = request.get_json()
        test_input = prompt_manager.create_test_input(prompt_goal_id, test_input_data)
        return jsonify(test_input.__dict__)
    
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
    
@app.route('/prompts/<string:prompt_id>', methods=['GET', 'PUT'])
def prompt(prompt_id):
    if request.method == 'GET':
        prompt = prompt_manager.get_prompt(prompt_id)
        return jsonify(prompt.__dict__)
    elif request.method == 'PUT':
        prompt_data = request.get_json()
        prompt = prompt_manager.update_prompt(prompt_data)
        return jsonify(prompt.__dict__)
    
@app.route('/test-inputs/<string:test_input_id>', methods=['GET', 'PUT'])
def test_input(test_input_id):
    if request.method == 'GET':
        test_input = prompt_manager.get_test_input(test_input_id)
        return jsonify(test_input.__dict__)
    elif request.method == 'PUT':
        test_input_data = request.get_json()
        test_input = prompt_manager.update_test_input(test_input_data)
        return jsonify(test_input.__dict__)
    
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