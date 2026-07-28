import React, { useEffect, useState } from "react";
import Button from "react-bootstrap/Button";
import Container from "react-bootstrap/Container";
import Image from "react-bootstrap/Image";
import Form from "react-bootstrap/Form";
import CodeEditor from "./CodeEditor";

import { useParams, useNavigate } from "react-router-dom";
import {
  savePromptGoal,
  fetchPromptGoal,
  updatePromptGoal,
} from "../api/promptApi";

const PromptGoalEditor = () => {
  const { promptGoalId } = useParams();
  const nav = useNavigate();
  const [formData, setFormData] = useState(null);

  useEffect(() => {
    const fetchFormData = async () => {
      if (promptGoalId) {
        const data = await fetchPromptGoal(promptGoalId); // Fetch data based on ID
        setFormData(data);
      }
    };
    fetchFormData();
  }, [promptGoalId]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    try {
      if (promptGoalId) {
        await updatePromptGoal(promptGoalId, formData);
      } else {
        await savePromptGoal(formData);
      }
      nav("/"); // Navigate back to dashboard or prompt goal list
    } catch (error) {
      console.error("Error saving prompt goal:", error);
    }
  };

  const handleCancel = () => {
    // Navigate back to the dashboard or wherever is appropriate for your app
    nav("/");
  };

  const handleChange = (event) => {
    const { name, value } = event.target;
    setFormData((prevFormData) => {
      // Create a copy of the previous form data
      const newFormData = { ...prevFormData };

      // Check if the field name contains square brackets (for arrays)
      if (name.includes("[")) {
        // Parse the field name to get the array name and index
        const [arrayName, index] = name.split(/\[|\]/);

        // Update the value in the array
        newFormData[arrayName][index] = value;
      } else {
        // Update the value directly in the form data object
        newFormData[name] = value;
      }

      return newFormData;
    });
  };

  const addNeed = () => {
    setFormData((prevFormData) => {
      const newFormData = { ...prevFormData };
      newFormData.needs = [...(newFormData.needs || []), ""];
      return newFormData;
    });
  };

  const removeNeed = (index) => {
    setFormData((prevFormData) => {
      const updatedNeeds = [...prevFormData.needs];
      updatedNeeds.splice(index, 1);
      return { ...prevFormData, needs: updatedNeeds };
    });
  };

  const moveNeedUp = (index) => {
    setFormData((prevFormData) => {
      const updatedNeeds = [...prevFormData.needs];
      const temp = updatedNeeds[index];
      updatedNeeds[index] = updatedNeeds[index - 1];
      updatedNeeds[index - 1] = temp;
      return { ...prevFormData, needs: updatedNeeds };
    });
  };

  const moveNeedDown = (index) => {
    setFormData((prevFormData) => {
      const updatedNeeds = [...prevFormData.needs];
      const temp = updatedNeeds[index];
      updatedNeeds[index] = updatedNeeds[index + 1];
      updatedNeeds[index + 1] = temp;
      return { ...prevFormData, needs: updatedNeeds };
    });
  };

  const addWant = () => {
    setFormData((prevFormData) => {
      const newFormData = { ...prevFormData };
      newFormData.wants = [...(newFormData.wants || []), ""];
      return newFormData;
    });
  };

  const removeWant = (index) => {
    setFormData((prevFormData) => {
      const updatedWants = [...prevFormData.wants];
      updatedWants.splice(index, 1);
      return { ...prevFormData, wants: updatedWants };
    });
  };

  const moveWantUp = (index) => {
    setFormData((prevFormData) => {
      const updatedWants = [...prevFormData.wants];
      const temp = updatedWants[index];
      updatedWants[index] = updatedWants[index - 1];
      updatedWants[index - 1] = temp;
      return { ...prevFormData, wants: updatedWants };
    });
  };

  const moveWantDown = (index) => {
    setFormData((prevFormData) => {
      const updatedWants = [...prevFormData.wants];
      const temp = updatedWants[index];
      updatedWants[index] = updatedWants[index + 1];
      updatedWants[index + 1] = temp;
      return { ...prevFormData, wants: updatedWants };
    });
  };

  const addStatistic = () => {
    setFormData((prevFormData) => {
      // Create a copy of the previous form data
      const newFormData = { ...prevFormData };

      // Add a new empty statistic object to the statistics array
      newFormData.statistics = [
        ...(newFormData.statistics || []),
        { key: "", value: "" },
      ];

      return newFormData;
    });
  };

  return (
    <Container>
      {" "}
      <div className="p-5 mb-4 bg-light rounded-3">
        {" "}
        <div className="container-fluid py-5">
          {" "}
          <div className="row align-items-center">
            {" "}
            <div className="col-md-3">
              {" "}
              <Image
                src="../azathoth.png"
                className="img-fluid mb-3 mb-md-0"
                alt="Azathoth"
              />{" "}
            </div>{" "}
            <div className="col-md-9">
              {" "}
              <h1 className="display-5 fw-bold mb-3">
                {" "}
                {promptGoalId ? "Edit Prompt Goal" : "Add New Prompt Goal"}{" "}
              </h1>{" "}
              <p className="fs-4 text-muted mb-4">
                {" "}
                Fill in the details below to create or edit a prompt goal.{" "}
              </p>{" "}
            </div>{" "}
          </div>{" "}
          <div className="row justify-content-center">
            {" "}
            <div className="col-md-8">
              {" "}
              <Form className="prompt-goal-form" onSubmit={handleSubmit}>
                {" "}<br />
                <Form.Group className="mb-4" controlId="prompt_goal_name">
                  {" "}
                  <Form.Label>
                    {" "}
                    <i className="bi bi-bullseye me-2"></i> Goal Name{" "}
                  </Form.Label>{" "}<br />
                  <Form.Text className="form-text-small text-muted">
                    {" "}
                    Enter a short, descriptive name for your goal.{" "}
                  </Form.Text>{" "}
                  <Form.Control
                    type="text"
                    className="form-control-subtle"
                    name="prompt_goal_name"
                    value={formData?.prompt_goal_name}
                    onChange={handleChange}
                  />{" "}
                </Form.Group>
                <Form.Group
                  className="mb-4"
                  controlId="prompt_goal_description"
                >
                  <Form.Label>Goal Description</Form.Label><br />
                  <Form.Text className="form-text-small text-muted">
                    Provide additional context or clarification for your goal.
                  </Form.Text>
                  <Form.Control
                    as="textarea"
                    className="form-control-subtle"
                    rows={4}
                    name="prompt_goal_description"
                    value={formData?.prompt_goal_description}
                    onChange={handleChange}
                  />
                </Form.Group>
                <Form.Group className="mb-4" controlId="desired_outcomes">
                  <Form.Label>Desired Outcomes</Form.Label><br />
                  <Form.Text className="form-text-small text-muted">
                    Describe what you aim to achieve with this goal. Be as
                    detailed as possible.
                  </Form.Text>
                  <Form.Control
                    as="textarea"
                    className="form-control-subtle"
                    rows={4}
                    name="desired_outcomes"
                    value={formData?.desired_outcomes}
                    onChange={handleChange}
                  />
                </Form.Group>
                <Form.Group className="mb-4" controlId="needs">
                  <Form.Label>Required Inputs</Form.Label><br />
                  <Form.Text className="form-text-small text-muted">
                    List all inputs or information needed to achieve the
                    outcomes.
                  </Form.Text>
                  {formData?.needs?.map((need, index) => (
                    <div key={index} className="input-group mb-2">
                      <Form.Control
                        type="text"
                        className="form-control-subtle"
                        name={`needs[${index}]`}
                        value={need}
                        onChange={handleChange}
                      />
                      <Button
                        variant="outline-secondary"
                        onClick={() => removeNeed(index)}
                        className="btn-sm"
                      >
                        <i className="bi bi-x"></i>
                      </Button>
                      <Button
                        variant="outline-secondary"
                        onClick={() => moveNeedUp(index)}
                        disabled={index === 0}
                        className="btn-sm"
                      >
                        <i className="bi bi-chevron-up"></i>
                      </Button>
                      <Button
                        variant="outline-secondary"
                        onClick={() => moveNeedDown(index)}
                        disabled={index === formData?.needs?.length - 1}
                        className="btn-sm"
                      >
                        <i className="bi bi-chevron-down"></i>
                      </Button>
                    </div>
                  ))}
                  <Button variant="outline-primary" size="sm" onClick={addNeed}>
                    <i className="bi bi-plus me-2"></i>
                    Add Need
                  </Button>
                </Form.Group>
                <Form.Group className="mb-4" controlId="wants">
                  <Form.Label>Optional Inputs</Form.Label><br />
                  <Form.Text className="form-text-small text-muted">
                    List all inputs or information wanted to achieve the
                    outcomes.
                  </Form.Text>
                  {formData?.wants?.map((want, index) => (
                    <div key={index} className="input-group mb-2">
                      <Form.Control
                        type="text"
                        className="form-control-subtle"
                        name={`wants[${index}]`}
                        value={want}
                        onChange={handleChange}
                      />
                      <Button
                        variant="outline-secondary"
                        onClick={() => removeWant(index)}
                        className="btn-sm"
                      >
                        <i className="bi bi-x"></i>
                      </Button>
                      <Button
                        variant="outline-secondary"
                        onClick={() => moveWantUp(index)}
                        disabled={index === 0}
                        className="btn-sm"
                      >
                        <i className="bi bi-chevron-up"></i>
                      </Button>
                      <Button
                        variant="outline-secondary"
                        onClick={() => moveWantDown(index)}
                        disabled={index === formData?.wants?.length - 1}
                        className="btn-sm"
                      >
                        <i className="bi bi-chevron-down"></i>
                      </Button>
                    </div>
                  ))}
                  <Button variant="outline-primary" size="sm" onClick={addWant}>
                    <i className="bi bi-plus me-2"></i>
                    Add Want
                  </Button>
                </Form.Group>
                <Form.Group className="mb-4" controlId="response_schema">
                  <Form.Label>Response Format Schema</Form.Label><br />
                  <Form.Text className="form-text-small text-muted">
                    Define the JSON structure for the response. Use the editor
                    for syntax highlighting and real-time validation.
                  </Form.Text>
                  <CodeEditor
                    name="response_schema"
                    value={formData?.response_schema}
                    onChange={handleChange}
                  />
                </Form.Group>
                <Form.Group className="mb-4" controlId="prompt_goal_id">
                  <Form.Label>Goal Identifier</Form.Label><br />
                  <Form.Text className="form-text-small text-muted">
                    A unique identifier for the prompt goal that will be added to all it's prompts.
                  </Form.Text>
                  <Form.Control
                    type="text"
                    className="form-control-subtle"
                    name="prompt_goal_id"
                    value={formData?.prompt_goal_id}
                    readOnly
                  />
                </Form.Group>
                {/* Render hidden fields */}
                <input type="hidden" name="$schema" value={formData?.$schema} />
                <input type="hidden" name="type" value={formData?.type} />
                <input type="hidden" name="_id" value={formData?._id} />
                <input type="hidden" name="_rev" value={formData?._rev} />
                <Form.Group className="mb-4" controlId="statistics">
                  <Form.Label>Statistics</Form.Label><br />
                  <Form.Text className="form-text-small text-muted">
                    Add any relevant statistics or metrics that this goal will
                    track.
                  </Form.Text>
                  {formData?.statistics?.map((statistic, index) => (
                    <div key={index} className="row mb-2">
                      <div className="col">
                        <Form.Control
                          type="text"
                          className="form-control-subtle"
                          name={`statistics[${index}].key`}
                          value={statistic.key}
                          onChange={handleChange}
                          placeholder="Statistic Name"
                        />
                      </div>
                      <div className="col">
                        <Form.Control
                          type="text"
                          className="form-control-subtle"
                          name={`statistics[${index}].value`}
                          value={statistic.value}
                          onChange={handleChange}
                          placeholder="Statistic Value"
                        />
                      </div>
                      <div className="col-auto">
                        <Button variant="outline-secondary" size="sm">
                          <i className="bi bi-x"></i>
                        </Button>
                      </div>
                    </div>
                  ))}
                  <Button
                    variant="outline-primary"
                    size="sm"
                    onClick={addStatistic}
                  >
                    <i className="bi bi-plus me-2"></i>
                    Add Statistic
                  </Button>
                </Form.Group>
                <div className="d-grid gap-2 d-md-flex justify-content-md-end mt-4">
                  <Button variant="primary" size="lg" type="submit">
                    Submit
                  </Button>
                  <Button
                    variant="outline-secondary"
                    size="lg"
                    onClick={handleCancel}
                  >
                    Cancel
                  </Button>
                </div>
              </Form>
            </div>
          </div>
        </div>
      </div>
    </Container>
  );
};

export default PromptGoalEditor;
