import React from 'react';
import AceEditor from 'react-ace';

import 'ace-builds/src-noconflict/mode-json';
import 'ace-builds/src-noconflict/theme-github';

const CodeEditor = ({ name, value, onChange }) => {
  const handleChange = (newValue) => {
    onChange(newValue);
  };

  // Convert value to a JSON string if it's not a string
  const jsonValue = typeof value === 'string' ? value : JSON.stringify(value, null, 2);

  return (
    <AceEditor
      mode="json"
      theme="github"
      name={name}
      value={jsonValue}
      onChange={handleChange}
      editorProps={{ $blockScrolling: true }}
      setOptions={{
        showLineNumbers: true,
        tabSize: 2,
      }}
      height='300px'
    />
  );
};

export default CodeEditor;