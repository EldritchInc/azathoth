import React from 'react';
import Form from 'react-jsonschema-form';
import { savePrompt } from '../api/promptApi';

const schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Prompt Configuration Schema",
    "type": "object",
    "properties": {
        "$schema": {"type": "string"},
        "prompt_id": {"type": "string"},
        "prompt_name": {"type": "string"},
        "prompt_version": {"type": "integer"},
        "model": {"type": "string"},
        "model_brand": {"type": "string"},
        "needs": {
            "type": "array",
            "items": {"type": "string"}
        },
        "response_tokens": {"type": "integer"},
        "temperature": {"type": "number"},
        "prompt": {"type": "string"},
        "chat": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "chat_element_id": {"type": "string"},
                    "message": {"type": "string"},
                    "jump_regex": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "regex": {"type": "string"},
                                "jump": {"type": "string"}
                            },
                            "required": ["regex", "jump"]
                        }
                    },
                    "stop_regex": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "required": ["chat_element_id", "message"]
            }
        }
    },
    "required": ["prompt_id", "prompt_name", "prompt_version", "model", "model_brand", "needs", "response_tokens", "temperature", "prompt", "chat"],
    "additionalProperties": false
};

const uiSchema = {
    "ui:order": ["model", "prompt_name", "model_brand", "needs", "response_tokens", "temperature", "prompt", "chat", "prompt_id", "prompt_version", "$schema"],
    "prompt_id": {
      "ui:widget": "hidden"
    },
    "prompt_version": {
      "ui:widget": "hidden"
    },
    "$schema": {
      "ui:widget": "hidden"
    }
  };

const PromptEditor = () => {
    const handleSubmit = async (data) => {
        try {
          const savedPrompt = await savePrompt(data.formData);
          console.log('Prompt saved:', savedPrompt);
          // Optionally, you can show a success message to the user
        } catch (error) {
          console.error('Error saving prompt:', error);
          // Optionally, you can show an error message to the user
        }
      };

  return (
    <div>
      <h2>Prompt Editor</h2>
      <Form schema={schema} uiSchema={uiSchema} onSubmit={handleSubmit} />
    </div>
  );
};

export default PromptEditor;