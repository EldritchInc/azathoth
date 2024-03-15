
class ModelRegistry:
    def __init__(self):
        self.handlers = {}

    def register_handler(self, model_brand, handler):
        self.handlers[model_brand] = handler

    def get_handler(self, model_brand):
        handler = self.handlers.get(model_brand)
        if not handler:
            raise ValueError(f"No handler registered for model brand: {model_brand}")
        return handler