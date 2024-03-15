
class LLMExecutor:
    def __init__(self, model_registry):
        self.model_registry = model_registry

    def execute_prompt(self, prompt, command_conversation):
        model_brand = prompt["model_brand"]
        model_config = prompt["model_config"]  # Assume this includes necessary configuration, like API tokens and URLs
        
        handler_class = self.model_registry.get_handler(model_brand)
        handler = handler_class(model_config)
        response = handler.execute_prompt(prompt, command_conversation)
        return handler.process_response(response)