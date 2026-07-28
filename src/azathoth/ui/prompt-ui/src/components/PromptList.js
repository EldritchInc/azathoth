import React from 'react';
import { useNavigate } from 'react-router-dom';
import Button from 'react-bootstrap/Button';


const PromptList = ({ promptGoalId, prompts }) => {
  const nav = useNavigate();
  const handleAddPromptClick = () => {
    nav(`/edit-prompt/${promptGoalId}`); // Navigate with ID for adding prompt
  };

  return (
    <div className="prompt-list">
      {prompts.map((prompt) => (
        <div key={prompt._id} className="prompt-item">
          <div className="prompt-header">
            <h4>{prompt.name}</h4>
            <Button variant="link">Edit</Button>
            <Button variant="link">Delete</Button>
            <Button variant="link">Run Tests</Button>
          </div>
          <div className="prompt-description">{prompt.description}</div>
        </div>
      ))}
      <Button variant="primary" onClick={handleAddPromptClick}>Add Prompt</Button>
    </div>
  );
};

export default PromptList;