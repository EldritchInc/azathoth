import React from 'react';
import { Button, Form, Row, Col } from 'react-bootstrap';

const DynamicList = ({ label, name, items, onChange, schema, renderItem }) => {
  const handleAddItem = (parentIndex = null, key = null) => {
    if (parentIndex !== null && key !== null) {
      const updatedItems = [...items];
      if (schema[key].type === 'array' && schema[key].items.type === 'object') {
        // For nested array of objects
        const newItemStructure = Object.keys(schema[key].items.properties).reduce((acc, propKey) => {
          acc[propKey] = ''; // Initialize with default values based on schema
          return acc;
        }, {});
        updatedItems[parentIndex][key].push(newItemStructure);
      } else if (schema[key].type === 'array') {
        // For simple array (e.g., array of strings)
        updatedItems[parentIndex][key].push('');
      }
      onChange(updatedItems);
    } else {
      // Add new top-level item
      const newItem = Object.keys(schema).reduce((acc, schemaKey) => {
        acc[schemaKey] = schema[schemaKey].type === 'array' ? [] : '';
        return acc;
      }, {});
      onChange([...items, newItem]);
    }
  };

  const handleItemChange = (parentIndex, key, value, nestedIndex = null) => {
    const updatedItems = [...items];
    if (nestedIndex !== null) {
      if (typeof value === 'object' && value !== null) {
        // For nested array of objects
        updatedItems[parentIndex][key][nestedIndex] = { ...updatedItems[parentIndex][key][nestedIndex], ...value };
      } else {
        // For simple array (e.g., array of strings)
        updatedItems[parentIndex][key][nestedIndex] = value;
      }
    } else {
      updatedItems[parentIndex][key] = value;
    }
    onChange(updatedItems);
  };

  const handleRemoveItem = (parentIndex, key = null, nestedIndex = null) => {
    let updatedItems = [...items];
    if (nestedIndex !== null) {
      updatedItems[parentIndex][key] = updatedItems[parentIndex][key].filter((_, index) => index !== nestedIndex);
    } else {
      updatedItems = updatedItems.filter((_, index) => index !== parentIndex);
    }
    onChange(updatedItems);
  };

  const renderItemFields = (item, index) => {
    return Object.keys(schema).map((key) => {
      const isArray = schema[key].type === 'array';
      const isArrayOfObjects = isArray && schema[key].items && schema[key].items.type === 'object';
      const isArrayOfStrings = isArray && schema[key].items && schema[key].items.type === 'string';

      if (isArrayOfObjects) {
        return (
          <div key={key}>
            <Form.Label>{key}</Form.Label>
            {item[key].map((nestedItem, nestedIndex) => (
              <Row key={nestedIndex}>
                {Object.keys(schema[key].items.properties).map((nestedKey) => (
                  <Col key={nestedKey} xs={12}>
                    <Form.Control
                      type="text"
                      placeholder={schema[key].items.properties[nestedKey].placeholder || ''}
                      value={nestedItem[nestedKey] || ''}
                      onChange={(e) =>
                        handleItemChange(index, key, { [nestedKey]: e.target.value }, nestedIndex)
                      }
                    />
                  </Col>
                ))}
                <Col xs={12}>
                  <Button variant="danger" onClick={() => handleRemoveItem(index, key, nestedIndex)}>Remove</Button>
                </Col>
              </Row>
            ))}
            <Button onClick={() => handleAddItem(index, key)}>Add to {key}</Button>
          </div>
        );
      } else if (isArrayOfStrings) {
        return (
          <div key={key}>
            <Form.Label>{key}</Form.Label>
            {item[key].map((nestedItem, nestedIndex) => (
              <Row key={nestedIndex} className="mb-2">
                <Col xs={10}>
                  <Form.Control
                    type="text"
                    placeholder={schema[key].items.placeholder || ''}
                    value={nestedItem || ''}
                    onChange={(e) => handleItemChange(index, key, e.target.value, nestedIndex)}
                  />
                </Col>
                <Col xs={2}>
                  <Button variant="danger" onClick={() => handleRemoveItem(index, key, nestedIndex)}>Remove</Button>
                </Col>
              </Row>
            ))}
            <Button onClick={() => handleAddItem(index, key)}>Add to {key}</Button>
          </div>
        );
      } else {
        // For regular fields
        return (
          <Form.Group key={key} controlId={`${name}-${key}-${index}`} className="mb-2">
            <Form.Label>{key}</Form.Label>
            <Form.Control
              as={schema[key].type === 'textarea' ? 'textarea' : 'input'}
              type={schema[key].type}
              placeholder={schema[key].placeholder || ''}
              value={item[key] || ''}
              onChange={(e) => handleItemChange(index, key, e.target.value)}
            />
          </Form.Group>
        );
      }
    });
  };

  return (
    <Form.Group controlId={name}>
      <Form.Label>{label}</Form.Label>
      {renderItem ? (
        items.map((item, index) =>
          renderItem(
            item,
            index,
            (itemIndex, value) => handleItemChange(itemIndex, value),
            (itemIndex) => handleRemoveItem(itemIndex)
          )
        )
      ) : (
        items.map((item, index) => (
          <div key={index}>
            {renderItemFields(item, index)}
            <Button variant="outline-danger" onClick={() => handleRemoveItem(index)}>
              Remove Item
            </Button>
          </div>
        ))
      )}
      <Button onClick={() => handleAddItem()}>Add New Item</Button>
    </Form.Group>
  );
};

export default DynamicList;