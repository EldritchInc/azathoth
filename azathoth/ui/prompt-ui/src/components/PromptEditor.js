import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Container, Button, Alert } from "react-bootstrap";
import Form from "react-bootstrap/Form";
import CodeEditor from "./CodeEditor";
import DynamicList from "./DynamicList";
import {
  savePrompt,
  fetchPrompt,
  updatePrompt,
  getModelBrands,
  getModelsForBrand,
} from "../api/promptApi";

const PromptEditor = () => {
  const { promptId, promptGoalId } = useParams();
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    prompt_version: 1,
    needs: [],
    chat: [],
    model_brand: "", // Added for brand selection
    model: "", // This will be updated based on the model selection
  });
  const [model_brands, setModel_brands] = useState([]);
  const [models, setModels] = useState([]);
  const [error, setError] = useState("");

  const handleCancel = () => {
    navigate(`/`);
  };
  
  useEffect(() => {
    const fetchBrands = async () => {
      try {
        const brandsData = await getModelBrands();
        setModel_brands(brandsData);
      } catch (error) {
        setError("Failed to fetch brands.");
        console.error("Error fetching brands:", error);
      }
    };

    if (promptId) {
      const fetchFormData = async () => {
        try {
          const data = await fetchPrompt(promptId);
          setFormData(data);
          if (data.model_brand) {
            const modelsData = await getModelsForBrand(data.model_brand);
            setModels(modelsData);
          }
        } catch (error) {
          setError("Failed to fetch prompt data.");
          console.error("Error fetching prompt data:", error);
        }
      };
      fetchFormData();
    }
    fetchBrands();
  }, [promptId]);

  const handleBrandChange = async ({ target: { value } }) => {
    try {
      const modelsData = await getModelsForBrand(value);
      setFormData((prev) => ({
        ...prev,
        model_brand: value,
        model: modelsData.length > 0 ? modelsData[0] : "",
      }));
      setModels(modelsData);
    } catch (error) {
      setError("Failed to fetch models for the selected brand.");
      console.error("Error fetching models:", error);
    }
  };

  const handleChange = ({ target: { name, value } }) => {
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    try {
      if (promptId) {
        await updatePrompt(promptId, formData);
      } else {
        await savePrompt(promptGoalId, formData);
      }
      navigate("/");
    } catch (error) {
      setError("Error saving prompt.");
      console.error("Error saving prompt:", error);
    }
  };

  const handleDynamicChange = (name, value) => {
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const chatElementSchema = {
    chat_element_id: { type: "text", placeholder: "Chat Element ID" },
    message: { type: "textarea", placeholder: "Enter message" },
    jump_regex: {
      type: "array",
      items: {
        type: "object",
        properties: {
          regex: { type: "text", placeholder: "Regex Pattern" },
          jump: { type: "text", placeholder: "Jump To" },
        },
        required: ["regex", "jump"], // Optional, if you want to enforce required fields
      },
    },
    stop_regex: {
      type: "array",
      items: {
        type: "text", placeholder: "Regex Pattern"
      },
    },  
    temperature: { type: "number", placeholder: "Temperature" },
    response_tokens: { type: "integer", placeholder: "Response Tokens" },
  };
  
  return (
    <Container>
      {/* UI components remain largely the same, with the addition of two dropdowns for brand and model selection */}
      <div className="p-5 mb-4 bg-light rounded-3">
        <h1 className="display-5 fw-bold mb-3">
          {promptId ? "Edit Prompt" : "Add New Prompt"}
        </h1>
        {error && <Alert variant="danger">{error}</Alert>}
        <Form onSubmit={handleSubmit}>
          <Form.Group className="mb-3" controlId="prompt_name">
            <Form.Label>Prompt Name</Form.Label>
            <br />
            <Form.Text className="text-muted">
              A unique name for the prompt
            </Form.Text>
            <Form.Control
              type="text"
              name="prompt_name"
              value={formData.prompt_name || ""}
              onChange={handleChange}
            />
          </Form.Group>

          <Form.Group className="mb-3" controlId="model_brand">
            <Form.Label>Model Brand</Form.Label>
            <Form.Select
              name="model_brand"
              value={formData.model_brand || ""}
              onChange={handleBrandChange}
            >
              <option>Select a brand</option>
              {model_brands.map((model_brand) => (
                <option key={model_brand} value={model_brand}>
                  {model_brand}
                </option>
              ))}
            </Form.Select>
          </Form.Group>

          <Form.Group className="mb-3" controlId="model">
            <Form.Label>Model</Form.Label>
            <Form.Select
              name="model"
              value={formData.model || ""}
              onChange={handleChange}
            >
              <option>Select a model</option>
              {models.map((model) => (
                <option key={model} value={model}>
                  {model}
                </option>
              ))}
            </Form.Select>
          </Form.Group>

          <DynamicList
            label="Needs"
            name="needs"
            items={formData.needs}
            onChange={(value) => handleDynamicChange("needs", value)}
            schema={{ type: "array", items: { type: "text", placeholder: "NeedId"}}}
          />

          <CodeEditor
            name="prompt"
            label="Prompt Template"
            value={formData.prompt || ""}
            onChange={(value) => handleDynamicChange("prompt", value)}
          />

          <DynamicList
            label="Chat Elements"
            name="chat"
            items={formData.chat}
            onChange={(value) => handleDynamicChange("chat", value)}
            itemType="object"
            schema={chatElementSchema}
          />

          <Form.Group className="mb-3" controlId="prompt_version">
            <Form.Label>Prompt Version</Form.Label>
            <Form.Control
              type="number"
              name="prompt_version"
              value={formData.prompt_version || ""}
              onChange={handleChange}
            />
          </Form.Group>

          <div className="d-grid gap-2 d-md-flex justify-content-md-end mt-4">
            <Button variant="primary" type="submit">
              Submit
            </Button>
            <Button variant="outline-secondary" onClick={handleCancel}>
              Cancel
            </Button>
          </div>
        </Form>
      </div>
    </Container>
  );
};

export default PromptEditor;
