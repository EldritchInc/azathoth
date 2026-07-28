import React from "react";
import 'ace-builds'
import 'ace-builds/webpack-resolver'
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import Dashboard from "./components/Dashboard";
import PromptGoalEditor from "./components/PromptGoalEditor";
import PromptEditor from "./components/PromptEditor";

import Container from "react-bootstrap/Container";

import "./App.css";
import 'bootstrap-icons/font/bootstrap-icons.css';

// Define the App component
function App() {
  return (
    <Container>
      <Router>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route
            path="/edit-prompt-goal/:promptGoalId"
            element={<PromptGoalEditor />}
          />
          {/* Add a route for adding a new prompt goal without an ID */}
          <Route path="/edit-prompt-goal" element={<PromptGoalEditor />} />
          <Route path="/edit-prompt/:promptGoalId" element={<PromptEditor />} />
          <Route path="/edit-prompt/:promptGoalId/:promptId" element={<PromptEditor />} />
        </Routes>
      </Router>
    </Container>
  );
}

export default App;
