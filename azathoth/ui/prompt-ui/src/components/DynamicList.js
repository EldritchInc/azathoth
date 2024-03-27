import React from 'react';
import { Button, Form, Row, Col } from 'react-bootstrap';

const DynamicList = ({ label, name, items, onChange, itemType = 'text', schema }) => {
  const handleItemChange = (index, value) => {
    const updatedItems = [...items];
    if (itemType === 'object' && schema) {
      updatedItems[index] = { ...updatedItems[index], ...value };
    } else {
      updatedItems[index] = value;
    }
    onChange(updatedItems);
  };

  const handleAddItem = () => {
    const newItem = itemType === 'object' ? {} : '';
    onChange([...items, newItem]);
  };

  const handleRemoveItem = (index) => {
    const updatedItems = items.filter((_, i) => i !== index);
    onChange(updatedItems);
  };

  const renderItemInput = (item, index) => {
    if (itemType === 'object' && schema) {
      return Object.keys(schema).map((key) => (
        <Form.Control
          key={key}
          as={schema[key].type === 'textarea' ? 'textarea' : 'input'}
          type={schema[key].type === 'text' ? 'text' : undefined}
          placeholder={schema[key].placeholder || ''}
          value={item[key] || ''}
          onChange={(e) => handleItemChange(index, { [key]: e.target.value })}
          className="mb-2"
        />
      ));
    }
    return (
      <Form.Control
        type="text"
        value={item}
        onChange={(e) => handleItemChange(index, e.target.value)}
        className="mb-2"
      />
    );
  };

  return (
    <Form.Group controlId={name}>
      <Form.Label>{label}</Form.Label>
      {items.map((item, index) => (
        <Row key={index} className="align-items-center mb-2">
          <Col>{renderItemInput(item, index)}</Col>
          <Col xs="auto">
            <Button variant="outline-danger" onClick={() => handleRemoveItem(index)}>
              Remove
            </Button>
          </Col>
        </Row>
      ))}
      <Button onClick={handleAddItem}>Add {itemType === 'object' ? 'Object' : 'Item'}</Button>
    </Form.Group>
  );
};

export default DynamicList;
