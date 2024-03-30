class ModelRegistry:
    def __init__(self):
        self.handlers = {}  # Stores handler instances
        self.model_brands = {}  # New dictionary to store model brands to their handlers

    def register_handler(self, model_brand, handler, models):
        self.handlers[model_brand] = handler
        self.model_brands[model_brand] = models

    def get_handler(self, model_brand):
        handler = self.handlers.get(model_brand)
        if not handler:
            raise ValueError(f"No handler registered for model brand: {model_brand}")
        return handler

    def get_brands(self):
        """Returns a list of all registered model brands."""
        return list(self.model_brands.keys())

    def get_models_by_brand(self, model_brand):
        """Returns a list of models for a given brand."""
        if model_brand not in self.model_brands:
            raise ValueError(f"No models found for brand: {model_brand}")
        return self.model_brands[model_brand]
