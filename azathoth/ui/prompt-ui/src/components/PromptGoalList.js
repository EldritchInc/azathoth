import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faTimes } from "@fortawesome/free-solid-svg-icons";
import Button from "react-bootstrap/Button";
import Container from "react-bootstrap/Container";
import Modal from "react-bootstrap/Modal";
import Collapse from "react-bootstrap/Collapse";
import Tab from "react-bootstrap/Tab";
import Tabs from "react-bootstrap/Tabs";
import { deletePromptGoal } from "../api/promptApi";

import { fetchPrompts, fetchTestInputs } from "../api/promptApi";

const PromptGoalList = ({ promptGoals }) => {
  const [expandedGoalId, setExpandedGoalId] = useState(null);
  const [prompts, setPrompts] = useState([]);
  const [testInputs, setTestInputs] = useState([]);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [selectedPromptGoalId, setSelectedPromptGoalId] = useState(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const goalsPerPage = 10;
  const nav = useNavigate();

  // Change page function
  const paginate = (pageNumber) => setCurrentPage(pageNumber);

  // Implement a simple pagination component below your goals map

  // Filter prompt goals based on search term
  const filteredPromptGoals = promptGoals.filter((goal) =>
    goal.prompt_goal_name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handlePromptGoalClick = (goalId) => {
    setExpandedGoalId(expandedGoalId === goalId ? null : goalId);
  };

  const indexOfLastGoal = currentPage * goalsPerPage;
  const indexOfFirstGoal = indexOfLastGoal - goalsPerPage;
  const currentGoals = filteredPromptGoals.slice(
    indexOfFirstGoal,
    indexOfLastGoal
  );

  // Function to open the confirmation dialog
  const confirmDelete = (promptGoalId) => {
    setSelectedPromptGoalId(promptGoalId);
    setShowDeleteConfirm(true);
  };

  // Actual deletion function, now separated for clarity
  const handleDeleteClick = () => {
    console.log("Delete:", selectedPromptGoalId);
    deletePromptGoal(selectedPromptGoalId);
    setShowDeleteConfirm(false); // Close modal after deletion
  };

  const handleAddClick = () => {
    nav("/edit-prompt-goal"); // Navigate without ID for adding
  };

  const handleEditClick = (promptGoalId) => {
    nav(`/edit-prompt-goal/${promptGoalId}`); // Navigate with ID for editing
  };

  useEffect(() => {
    const fetchData = async () => {
      if (expandedGoalId) {
        try {
          const fetchedPrompts = await fetchPrompts(expandedGoalId);
          setPrompts(fetchedPrompts);

          const fetchedTestInputs = await fetchTestInputs(expandedGoalId);
          setTestInputs(fetchedTestInputs);
        } catch (error) {
          console.error("Error fetching data:", error);
        }
      } else {
        setPrompts([]);
        setTestInputs([]);
      }
    };

    fetchData();
  }, [expandedGoalId]);

  return (
    <Container className="dashboard-container">
      <h2>Prompt Goals</h2>
      <div className="search-add-container">
        <input
          type="text"
          className="search-input"
          placeholder="Search prompt goals..."
          onChange={(e) => setSearchTerm(e.target.value)}
          style={{ marginBottom: "20px" }}
        />
        <Button onClick={handleAddClick}>Add New Prompt Goal</Button>
      </div>
      <div className="prompt-goal-list">
        {currentGoals.map((promptGoal) => (
          <div key={promptGoal._id} className="prompt-goal">
            <div
              className="prompt-goal-header"
              onClick={() => handlePromptGoalClick(promptGoal._id)}
            >
              <h3>{promptGoal.prompt_goal_name}</h3>
              <div className="prompt-goal-buttons">
                <Button variant="link">
                  {expandedGoalId === promptGoal._id ? "Collapse" : "Expand"}
                </Button>
                <Button onClick={() => handleEditClick(promptGoal._id)}>
                  Edit
                </Button>
                <Button
                  type="button"
                  className="btn btn-danger"
                  onClick={() => confirmDelete(promptGoal._id)}
                  style={{ marginLeft: "10px" }}
                >
                  <FontAwesomeIcon icon={faTimes} /> Delete
                </Button>
              </div>
            </div>
            <div className="prompt-goal-details">
              <Collapse Collapse in={expandedGoalId === promptGoal._id}>
                <div className="prompt-goal-details">
                  <div className="prompt-goal-description">
                    {promptGoal.description}
                  </div>
                  <Tabs defaultActiveKey="prompts">
                    <Tab eventKey="prompts" title="Prompts">
                      <PromptList prompts={prompts} />
                    </Tab>
                    <Tab eventKey="tests" title="Tests">
                      <TestList tests={testInputs} />
                    </Tab>
                  </Tabs>
                </div>
              </Collapse>
            </div>
          </div>
        ))}
      </div>
      <div className="pagination">
        {[
          ...Array(Math.ceil(filteredPromptGoals.length / goalsPerPage)).keys(),
        ].map((number) => (
          <Button key={number + 1} onClick={() => paginate(number + 1)}>
            {number + 1}
          </Button>
        ))}
      </div>
      <Modal
        show={showDeleteConfirm}
        onHide={() => setShowDeleteConfirm(false)}
      >
        <Modal.Header closeButton>
          <Modal.Title>Delete Prompt Goal</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          Are you sure you want to delete this prompt goal?
        </Modal.Body>
        <Modal.Footer>
          <Button
            variant="secondary"
            onClick={() => setShowDeleteConfirm(false)}
          >
            Cancel
          </Button>
          <Button variant="danger" onClick={handleDeleteClick}>
            Delete
          </Button>
        </Modal.Footer>
      </Modal>
    </Container>
  );
};

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

const TestList = ({ tests }) => {
  return (
    <div className="test-list">
      {tests.map((test) => (
        <div key={test._id} className="test-item">
          <div className="test-header">
            <h4>{test.name}</h4>
            <Button variant="link">Edit</Button>
            <Button variant="link">Delete</Button>
          </div>
          <div className="test-description">{test.description}</div>
        </div>
      ))}
      <Button variant="primary">Add Test Case</Button>
    </div>
  );
};

export default PromptGoalList;
