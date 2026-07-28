import React from "react";
import Button from "react-bootstrap/Button";

const TestList = ({ promptGoalId, tests }) => {
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

export default TestList;