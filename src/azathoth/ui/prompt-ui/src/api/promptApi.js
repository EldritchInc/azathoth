import axios from "axios";

const BASE_URL = "http://127.0.0.1:5000"; // Replace with your backend URL

export const getModelBrands = async () => {
  try {
    const response = await axios.get(`${BASE_URL}/models`);
    return response.data;
  } catch (error) {
    console.error("Error fetching model brands:", error);
    throw error;
  }
}

export const getModelsForBrand = async (brand) => {
  try {
    const response = await axios.get(`${BASE_URL}/models/${brand}`);
    return response.data;
  } catch (error) {
    console.error("Error fetching models for brand:", error);
    throw error;
  }
}

export const fetchPrompts = async (prompt_goal_id) => {
  console.log("Fetching prompts for prompt goal ID:", prompt_goal_id);
  try {
    const response = await axios.get(
      `${BASE_URL}/prompt-goals/${prompt_goal_id}/prompts`, 
      { headers: { 'Content-Type': 'application/json' } }
    );
    
    return response.data;
  } catch (error) {
    console.error("Error fetching prompts:", error);
    throw error;
  }
};

export const fetchTestInputs = async (prompt_goal_id) => {
  try {
    const response = await axios.get(
      `${BASE_URL}/prompt-goals/${prompt_goal_id}/test-inputs`
    );
    return response.data;
  } catch (error) {
    console.error("Error fetching test inputs:", error);
    throw error;
  }
}

export const fetchPromptGoals = async () => {
  try {
    const response = await axios.get(`${BASE_URL}/prompt-goals`);
    return response.data;
  } catch (error) {
    console.error("Error fetching prompt goals:", error);
    throw error;
  }
};

export const fetchPromptGoal = async (promptGoalId) => {
  try {
    const response = await axios.get(
      `${BASE_URL}/prompt-goals/${promptGoalId}`
    );
    return response.data;
  } catch (error) {
    console.error("Error fetching prompt goal:", error);
    throw error;
  }
};

export const savePrompt = async (promptGoalId, promptData) => {
  try {
    const response = await axios.post(
      `${BASE_URL}/prompt-goals/${promptGoalId}/prompts`,
      promptData
    );
    return response.data;
  } catch (error) {
    console.error("Error creating prompt:", error);
    throw error;
  }
}

export const savePromptGoal = async (promptGoalData) => {
  try {
    const response = await axios.post(
      `${BASE_URL}/prompt-goals`,
      promptGoalData
    );
    return response.data;
  } catch (error) {
    console.error("Error saving prompt goal:", error);
    throw error;
  }
};

export const deletePromptGoal = async (promptGoalId) => {
  try {
    const promptGoal = await fetchPromptGoal(promptGoalId);
    promptGoal.deleted = true;
    await updatePromptGoal(promptGoalId, promptGoal);
  } catch (error) {
    console.error("Error deleting prompt goal:", error);
    throw error;
  }
};

export const deletePrompt = async (promptId) => {
  try {
    const prompt = await fetchPrompt(promptId);
    prompt.deleted = true;
    await updatePrompt(promptId, prompt);
  } catch (error) {
    console.error("Error deleting prompt:", error);
    throw error;
  }
};

export const fetchPrompt = async (promptId) => {
  try {
    const response = await axios.get(`${BASE_URL}/prompts/${promptId}`);
    return response.data;
  } catch (error) {
    console.error("Error fetching prompt:", error);
    throw error;
  }
}

export const updatePrompt = async (promptId, promptData) => {
  try {
    const response = await axios.put(`${BASE_URL}/prompts/${promptId}`, promptData);
    return response.data;
  } catch (error) {
    console.error("Error updating prompt:", error);
    throw error;
  }
}

export const fetchTestInput = async (testInputId) => {
  try {
    const response = await axios.get(`${BASE_URL}/test-inputs/${testInputId}`);
    return response.data;
  } catch (error) {
    console.error("Error fetching test input:", error);
    throw error;
  }
}

export const updateTestInput = async (testInputId, testInputData) => {
  try {
    const response = await axios.put(`${BASE_URL}/test-inputs/${testInputId}`, testInputData);
    return response.data;
  } catch (error) {
    console.error("Error updating test input:", error);
    throw error;
  }
}

export const deleteTestInput = async (testInputId) => {
  try {
    const testInput = await fetchTestInput(testInputId);
    testInput.deleted = true;
    await updateTestInput(testInputId, testInput);
  } catch (error) {
    console.error("Error deleting test input:", error);
    throw error;
  }
}

export const updatePromptGoal = async (promptGoalId, promptGoalData) => {
  try {
    console.log("SAVING: " + promptGoalData);
    const response = await axios.put(
      `${BASE_URL}/prompt-goals/${promptGoalId}`,
      promptGoalData
    );
    return response.data;
  } catch (error) {
    console.error("Error updating prompt goal:", error);
    throw error;
  }
};

export const runTests = async (promptId, testCases) => {
  try {
    const response = await axios.post(`${BASE_URL}/run-tests`, {
      promptId,
      testCases,
    });
    return response.data;
  } catch (error) {
    console.error("Error running tests:", error);
    throw error;
  }
};
