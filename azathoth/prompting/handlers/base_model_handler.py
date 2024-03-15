class BaseModelHandler:
    def __init__(self, model_config):
        self.model_config = model_config
    
    def execute_prompt(self, prompt, command_conversation):
        raise NotImplementedError("This method should be implemented by subclasses.")
    
    def process_response(self, response):
        raise NotImplementedError("This method should be implemented by subclasses.")
