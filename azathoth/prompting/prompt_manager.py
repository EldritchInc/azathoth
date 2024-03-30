from typing import List, Dict, Any, Callable
from azathoth.prompting.prompt_goal import PromptGoal
from azathoth.prompting.prompt import Prompt
from azathoth.prompting.test_input import TestInput
from azathoth.prompting.couchdb import CouchDB

class PromptManager:
    def __init__(self, db: CouchDB):
        self.db = db

    def create_prompt_goal(self, prompt_goal_data: Dict[str, Any]) -> PromptGoal:
        # Validate the prompt goal data
        PromptGoal.validate_data(prompt_goal_data)
        
        # Create a new PromptGoal instance
        prompt_goal = PromptGoal(prompt_goal_data)
        
        # Convert the PromptGoal object to a dictionary
        prompt_goal_dict = {
            "prompt_goal_id": prompt_goal.prompt_goal_id,
            "prompt_goal_name": prompt_goal.prompt_goal_name,
            "type": "prompt_goal", # "type" is always set to "prompt_goal
            "desired_outcomes": prompt_goal.desired_outcomes,
            "needs": prompt_goal.needs,
            "wants": prompt_goal.wants, # Added "wants" field
            "prompt_goal_description": prompt_goal.prompt_goal_description,
            "response_schema": prompt_goal.response_schema,
            "statistics": prompt_goal.statistics
        }
        
        # Save the prompt goal dictionary to the database
        self.db.create_prompt_goal(prompt_goal_dict)
        
        return prompt_goal
        
        return prompt_goal
    
    def update_prompt_goal(self, prompt_goal_data: Dict[str, Any]) -> PromptGoal:
        # Validate the prompt goal data
        PromptGoal.validate_data(prompt_goal_data)
        
        # Create a new PromptGoal instance
        prompt_goal = PromptGoal(prompt_goal_data)
        
        # Convert the PromptGoal object to a dictionary
        prompt_goal_dict = {
            "prompt_goal_id": prompt_goal.prompt_goal_id,
            "prompt_goal_name": prompt_goal.prompt_goal_name,
            "type": "prompt_goal", # "type" is always set to "prompt_goal
            "desired_outcomes": prompt_goal.desired_outcomes,
            "needs": prompt_goal.needs,
            "wants": prompt_goal.wants, # Added "wants" field
            "prompt_goal_description": prompt_goal.prompt_goal_description,
            "response_schema": prompt_goal.response_schema,
            "statistics": prompt_goal.statistics,
            "_id": prompt_goal._id,
            "_rev": prompt_goal._rev
        }
        
        if "deleted" in prompt_goal_data:
            prompt_goal_dict["deleted"] = prompt_goal_data["deleted"]
        
        # Update the prompt goal dictionary in the database
        self.db.update_prompt_goal(prompt_goal._id, prompt_goal_dict)
        
        return prompt_goal

    def get_prompt_goal(self, prompt_goal_id: str) -> PromptGoal:
        prompt_goal_data = self.db.get_prompt_goal(prompt_goal_id)
        
        if prompt_goal_data:
            prompt_goal = PromptGoal(prompt_goal_data)
            return prompt_goal
        else:
            return None

    def get_all_prompt_goals(self) -> List[PromptGoal]:
        prompt_goal_data_list = self.db.get_all_prompt_goals()
        
        prompt_goals = []
        for data in prompt_goal_data_list:
            try:
                prompt_goal = PromptGoal(data)
                prompt_goals.append(prompt_goal)
            except ValueError as e:
                print(f"Skipping invalid prompt goal data: {e}")
        
        return prompt_goals
    
    def get_all_prompts_for_goal(self, prompt_goal_id: str) -> List[Prompt]:
        # Retrieve all prompts associated with the prompt goal
        prompt_data_list = self.db.get_prompts_for_goal(prompt_goal_id)
        
        # Create Prompt instances from the retrieved data
        prompts = [Prompt(data, prompt_goal_id) for data in prompt_data_list]
        
        return prompts
    
    def get_all_test_inputs_for_goal(self, prompt_goal_id: str) -> List[TestInput]:
        # Retrieve all test inputs associated with the prompt goal
        test_input_data_list = self.db.get_test_inputs_for_goal(prompt_goal_id)
        
        # Create TestInput instances from the retrieved data
        test_inputs = [TestInput(data, prompt_goal_id) for data in test_input_data_list]
        
        return test_inputs
    
    def create_test_input(self, prompt_goal_id: str, test_input_data: Dict[str, Any]) -> TestInput:
        # Retrieve the prompt goal
        prompt_goal = self.get_prompt_goal(prompt_goal_id)
        
        if prompt_goal:
            # Validate the test input data
            TestInput.validate_data(test_input_data)
            
            # Create a new TestInput instance
            test_input = TestInput(test_input_data, prompt_goal_id)
            
            # Save the test input to the database
            self.db.save_test_input(test_input)
            
            return test_input
        else:
            return None
        
    def get_test_inputs_for_goal(self, prompt_goal_id: str) -> List[TestInput]:
        # Retrieve all test inputs associated with the prompt goal
        test_input_data_list = self.db.get_test_inputs_for_goal(prompt_goal_id)
        
        # Create TestInput instances from the retrieved data
        test_inputs = [TestInput(data, prompt_goal_id) for data in test_input_data_list]
        
        return test_inputs
    
    def get_test_input(self, test_input_id: str) -> TestInput:
        # Retrieve the test input data from the database
        test_input_data = self.db.get_test_input(test_input_id)
        
        if test_input_data:
            # Retrieve the associated prompt goal
            prompt_goal_id = test_input_data["prompt_goal_id"]
            prompt_goal = self.get_prompt_goal(prompt_goal_id)
            
            if prompt_goal:
                # Create a TestInput instance from the retrieved data
                test_input = TestInput(test_input_data, prompt_goal_id)
                return test_input
            else:
                return None
        else:
            return None
        
    def update_test_input(self, test_input_id: str, test_input_data: Dict[str, Any]) -> TestInput:
        # Retrieve the test input
        test_input = self.get_test_input(test_input_id)
        
        if test_input:
            # Validate the test input data
            TestInput.validate_data(test_input_data)
            
            # Update the test input data in the database
            self.db.update_test_input(test_input_id, test_input_data)
            
            # Create a new TestInput instance with the updated data
            updated_test_input = TestInput(test_input_data, test_input.prompt_goal_id)
            
            return updated_test_input
        else:
            return None
        
    def delete_test_input(self, test_input_id: str, hard_delete: bool = False):
        # Retrieve the test input
        test_input = self.get_test_input(test_input_id)
        
        if test_input:
            # Delete the test input from the database
            self.db.delete_test_input(test_input_id, hard_delete)
        else:
            pass

    def create_prompt(self, prompt_goal_id: str, prompt_data: Dict[str, Any]) -> Prompt:
        # Retrieve the prompt goal
        prompt_goal = self.get_prompt_goal(prompt_goal_id)
        
        if prompt_goal:
            # Validate the prompt data
            Prompt.validate_data(prompt_data)
            
            # Create a new Prompt instance
            prompt = Prompt(prompt_data, prompt_goal)
            
            # Save the prompt to the database
            self.db.save_prompt(prompt)
            
            return prompt
        else:
            return None

    def get_prompt(self, prompt_id: str) -> Prompt:
        # Retrieve the prompt data from the database
        prompt_data = self.db.get_prompt(prompt_id)
        
        if prompt_data:
            # Retrieve the associated prompt goal
            prompt_goal_id = prompt_data["prompt_goal_id"]
            prompt_goal = self.get_prompt_goal(prompt_goal_id)
            
            if prompt_goal:
                # Create a Prompt instance from the retrieved data
                prompt = Prompt(prompt_data, prompt_goal)
                return prompt
            else:
                return None
        else:
            return None

    def generate_prompt(self, prompt_goal_id: str, model: str, parameters: dict) -> Prompt:
        # Retrieve the prompt goal
        prompt_goal = self.get_prompt_goal(prompt_goal_id)
        
        if prompt_goal:
            # Generate a new prompt based on the prompt goal, model, and parameters
            prompt_data = self.generate_prompt_data(prompt_goal, model, parameters)
            
            # Create a new Prompt instance
            prompt = Prompt(prompt_data, prompt_goal)
            
            # Save the prompt to the database
            self.db.save_prompt(prompt)
            
            return prompt
        else:
            return None

    def generate_prompt_data(self, prompt_goal: PromptGoal, model: str, parameters: dict) -> Dict[str, Any]:
        # Implement the logic to generate prompt data based on the prompt goal, model, and parameters
        pass

    def optimize_prompt(self, prompt_id: str) -> Prompt:
        # Retrieve the prompt
        prompt = self.get_prompt(prompt_id)
        
        if prompt:
            # Optimize the prompt based on the response history
            optimized_prompt_data = prompt.optimize()
            
            # Update the prompt data in the database
            self.db.update_prompt(prompt_id, optimized_prompt_data)
            
            # Create a new Prompt instance with the optimized data
            optimized_prompt = Prompt(optimized_prompt_data, prompt.prompt_goal)
            
            return optimized_prompt
        else:
            return None

    def gather_statistics(self):
        # Gather statistics for all prompts and prompt goals
        pass

    def execute_prompt(self, prompt_id: str, context: dict) -> str:
        # Retrieve the prompt
        prompt = self.get_prompt(prompt_id)
        
        if prompt:
            # Update the prompt goal with the test input
            self.db.create_test_input(prompt.prompt_goal.prompt_goal_id, context)
            # Execute the prompt with the given context
            response = prompt.execute(context)
            
            # Update the prompt goal with the test input
            self.db.create_prompt_output(prompt.prompt_goal.prompt_goal_id, prompt, response)
            
            return response
        else:
            return None

    def get_response_history(self, prompt_id: str) -> List[Dict[str, Any]]:
        # Retrieve the prompt
        prompt = self.get_prompt(prompt_id)
        
        if prompt:
            # Get the response history of the prompt
            response_history = prompt.get_response_history()
            return response_history
        else:
            return []

    def mark_response(self, prompt_id: str, response_id: str, is_correct: bool):
        # Retrieve the prompt
        prompt = self.get_prompt(prompt_id)
        
        if prompt:
            # Mark the response as correct or incorrect
            self.db.mark_response(prompt_id, response_id, is_correct)
        else:
            pass

    def validate_responses(self, prompt_id: str, validator: Callable[[str], bool]):
        # Retrieve the prompt
        prompt = self.get_prompt(prompt_id)
        
        if prompt:
            # Retrieve the response history of the prompt
            response_history = prompt.get_response_history()
            
            # Validate each response using the provided validator function
            for response in response_history:
                response_id = response["response_id"]
                response_text = response["response"]
                is_correct = validator(response_text)
                self.mark_response(prompt_id, response_id, is_correct)
        else:
            pass