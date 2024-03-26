import React, { useState, useEffect } from "react";
import { fetchPromptGoals, fetchPrompts } from "../api/promptApi";
import PromptGoalList from "./PromptGoalList";
import PromptList from "./PromptList";
import Container from "react-bootstrap/Container";
import Image from "react-bootstrap/Image";

const Dashboard = () => {
  const [promptGoals, setPromptGoals] = useState([]);
  const [prompts, setPrompts] = useState([]);
  const [selectedPromptGoalId, setSelectedPromptGoalId] = useState(null);

  useEffect(() => {
    // Fetch prompt goals from the API
    const fetchPromptGoalsData = async () => {
      try {
        const fetchedPromptGoals = await fetchPromptGoals();
        setPromptGoals(fetchedPromptGoals);
      } catch (error) {
        console.error("Error fetching prompt goals:", error);
        // Handle the error, show an error message, etc.
      }
    };

    fetchPromptGoalsData();
  }, []);

  useEffect(() => {
    // Fetch prompts based on the selected prompt goal ID
    const fetchPromptsData = async () => {
      if (selectedPromptGoalId) {
        try {
          const fetchedPrompts = await fetchPrompts(selectedPromptGoalId);
          setPrompts(fetchedPrompts);
        } catch (error) {
          console.error("Error fetching prompts:", error);
          // Handle the error, show an error message, etc.
        }
      } else {
        setPrompts([]);
      }
    };

    fetchPromptsData();
  }, [selectedPromptGoalId]);

  const handlePromptGoalSelect = (promptGoalId) => {
    setSelectedPromptGoalId(promptGoalId);
  };

  return (
    <Container>
      <div class="p-5 mb-4 bg-light rounded-3">
        <div class="container-fluid py-5">
          <div class="d-flex align-items-center">
            <Image src="azathoth.png" className="flex-shrink-0 me-3" fluid />
            <div>
              <h1 class="display-5 fw-bold">Azathoth Prompting</h1>
              <p class="col-md-8 fs-4">Select a prompt goal to view prompts.</p>
            </div>
          </div>
          <PromptGoalList
            promptGoals={promptGoals}
            onSelectPromptGoal={handlePromptGoalSelect}
            selectedPromptGoalId={selectedPromptGoalId}
          />
          <PromptList prompts={prompts} />
        </div>
      </div>
    </Container>
  );
};

export default Dashboard;
