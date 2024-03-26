import React from 'react';

const PromptList = ({ prompts }) => {
  return (
    <div>
      <h2>Prompts</h2>
      {/* Render the list of prompts */}
      {prompts.map((prompt) => (
        <div key={prompt.id}>
          <h3>{prompt.prompt_name}</h3>
          {/* Render other prompt details */}
        </div>
      ))}
    </div>
  );
};

export default PromptList;