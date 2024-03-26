import axios from "axios";

const BASE_URL = "http://127.0.0.1:5000"; // Replace with your backend URL

export const fetchPrompts = async (prompt_goal_id) => {
  try {
    const response = await axios.get(
      `${BASE_URL}/prompt-goals/${prompt_goal_id}/prompts`
    );
    return response.data;
  } catch (error) {
    console.error("Error fetching prompts:", error);
    throw error;
  }
};

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

export const savePrompt = async (promptData) => {
  try {
    const response = await axios.post(`${BASE_URL}/prompts`, promptData);
    return response.data;
  } catch (error) {
    console.error("Error saving prompt:", error);
    throw error;
  }
};

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
