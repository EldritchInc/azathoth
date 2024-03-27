import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Container, Button, Form, Alert } from 'react-bootstrap';
import CodeEditor from './CodeEditor'; // Assuming a custom component for JSON editing
import DynamicList from './DynamicList'; // A custom component for handling dynamic lists
import { savePrompt, fetchPrompt, updatePrompt } from '../api/promptApi';

const PromptEditor = () => {
  const { promptId, promptGoalId } = useParams();
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    prompt_version: 1,
    needs: [],
    chat: [],
  });
  const [error, setError] = useState('');

  useEffect(() => {
    if (promptId) {
      const fetchFormData = async () => {
        try {
          const data = await fetchPrompt(promptId);
          setFormData(data);
        } catch (error) {
          setError('Failed to fetch prompt data.');
          console.error('Error fetching prompt data:', error);
        }
      };
      fetchFormData();
    }
  }, [promptId]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    try {
      if (promptId) {
        await updatePrompt(promptId, formData);
      } else {
        await savePrompt(formData);
      }
      navigate('/prompts');
    } catch (error) {
      setError('Error saving prompt.');
      console.error('Error saving prompt:', error);
    }
  };

  const handleChange = ({ target: { name, value } }) => {
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleDynamicChange = (name, value) => {
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleCancel = () => navigate('/prompts');

  return (
    <Container>
      <div className="p-5 mb-4 bg-light rounded-3">
        <h1 className="display-5 fw-bold mb-3">
          {promptId ? 'Edit Prompt' : 'Add New Prompt'}
        </h1>
        {error && <Alert variant="danger">{error}</Alert>}
        <Form onSubmit={handleSubmit}>
          <Form.Group className="mb-3" controlId="prompt_name">
            <Form.Label>Prompt Name</Form.Label><br />
            <Form.Text className="text-muted">A unique name for the prompt</Form.Text>
            <Form.Control type="text" name="prompt_name" value={formData.prompt_name || ''} onChange={handleChange} />
          </Form.Group>

          <Form.Group className="mb-3" controlId="model">
            <Form.Label>Model</Form.Label>
            <Form.Control type="text" name="model" value={formData.model || ''} onChange={handleChange} />
          </Form.Group>

          <DynamicList
            label="Needs"
            name="needs"
            items={formData.needs}
            onChange={(value) => handleDynamicChange('needs', value)}
          />

          <CodeEditor
            name="prompt"
            label="Prompt Template"
            value={formData.prompt || ''}
            onChange={(value) => handleDynamicChange('prompt', value)}
          />

          <DynamicList
            label="Chat Elements"
            name="chat"
            items={formData.chat}
            onChange={(value) => handleDynamicChange('chat', value)}
            itemType="object"
            schema={{
              chat_element_id: { type: 'text' },
              message: { type: 'textarea' },
              jump_regex: { type: 'code' },
              stop_regex: { type: 'code' },
            }}
          />

          <div className="d-grid gap-2 d-md-flex justify-content-md-end mt-4">
            <Button variant="primary" type="submit">Submit</Button>
            <Button variant="outline-secondary" onClick={handleCancel}>Cancel</Button>
          </div>
        </Form>
      </div>
    </Container>
  );
};

export default PromptEditor;
