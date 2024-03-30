class BaseModelHandler:
    def __init__(self):
        pass
    
    def get_models(self):
        raise NotImplementedError("This method should be implemented by subclasses.")
    
    def execute_prompt(self, prompt, command_conversation):
        raise NotImplementedError("This method should be implemented by subclasses.")
    
    def process_response(self, response):
        raise NotImplementedError("This method should be implemented by subclasses.")
