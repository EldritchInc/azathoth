import React, { useState, useEffect } from "react";
import { runTests } from "../api/promptApi";
import { fetchPrompts, fetchPromptGoals } from "../api/promptApi";

const TestRunner = () => {
  const [selectedPrompt, setSelectedPrompt] = useState(null);
  const [testCases, setTestCases] = useState([]);
  const [testResults, setTestResults] = useState([]);
  const [prompts, setPrompts] = useState([]);
  const [promptGoals, setPromptGoals] = useState([]);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const fetchedPrompts = await fetchPrompts();
        setPrompts(fetchedPrompts);
        const fetchedPromptGoals = await fetchPromptGoals();
        setPromptGoals(fetchedPromptGoals);
      } catch (error) {
        console.error("Error fetching data:", error);
      }
    };

    fetchData();
  }, []);

  const handlePromptChange = (event) => {
    setSelectedPrompt(event.target.value);
  };

  const handleTestCaseChange = (index, field, value) => {
    const updatedTestCases = [...testCases];
    updatedTestCases[index][field] = value;
    setTestCases(updatedTestCases);
  };

  const handleAddTestCase = () => {
    setTestCases([...testCases, { context: "", expectedResponse: "" }]);
  };

  const handleRemoveTestCase = (index) => {
    const updatedTestCases = [...testCases];
    updatedTestCases.splice(index, 1);
    setTestCases(updatedTestCases);
  };

  const handleRunTests = async () => {
    try {
      const testResults = await runTests(selectedPrompt, testCases);
      setTestResults(testResults);
    } catch (error) {
      console.error("Error running tests:", error);
      // Optionally, you can show an error message to the user
    }
  };

  return (
    <div>
      <h2>Test Runner</h2>
      <div>
        <label>
          Select Prompt:
          <select value={selectedPrompt} onChange={handlePromptChange}>
            <option value="">Select a prompt</option>
            {prompts.map((prompt) => (
              <option key={prompt.id} value={prompt.id}>
                {prompt.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div>
        <h3>Test Cases</h3>
        {testCases.map((testCase, index) => (
          <div key={index}>
            <input
              type="text"
              placeholder="Context"
              value={testCase.context}
              onChange={(e) =>
                handleTestCaseChange(index, "context", e.target.value)
              }
            />
            <input
              type="text"
              placeholder="Expected Response"
              value={testCase.expectedResponse}
              onChange={(e) =>
                handleTestCaseChange(index, "expectedResponse", e.target.value)
              }
            />
            <button onClick={() => handleRemoveTestCase(index)}>Remove</button>
          </div>
        ))}
        <button onClick={handleAddTestCase}>Add Test Case</button>
      </div>
      <div>
        <button onClick={handleRunTests}>Run Tests</button>
      </div>
      <div>
        <h3>Test Results</h3>
        {testResults.map((result, index) => (
          <div key={index}>
            Test {index + 1}: {result.passed ? "Passed" : "Failed"}
          </div>
        ))}
      </div>
    </div>
  );
};

export default TestRunner;
