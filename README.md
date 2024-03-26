# Azathoth AI Framework

Welcome to the **Azathoth AI Framework**, an innovative Python library designed for constructing agentic intelligences. Our framework facilitates the development of advanced AI agents, leveraging the power of external tools, including Large Language Models (LLMs), image processing systems, and more, to create robust and versatile intelligences.

## Features

- **Versatile Agent Construction**: Build AI agents with complex behaviors, capable of operating in diverse environments.
- **Integration with Advanced Tools**: Seamlessly incorporate LLMs, image recognition systems, and other cutting-edge technologies to enhance agent capabilities.
- **Python-Based**: Utilize the extensive Python ecosystem for development, ensuring ease of use and broad compatibility.
- **Open Source**: Collaborate, modify, and distribute the framework with the support of a growing community.

## CouchDB Setup Instructions

1. Install CouchDB on your system by following the official installation guide: https://docs.couchdb.org/en/stable/install/index.html
2. Once CouchDB is installed and running, open a web browser and navigate to `http://localhost:5984/_utils` to access the CouchDB web interface.
3. In the web interface, click on the "Create Database" button and enter a database name (e.g., "azathoth"). Make sure to use the same database name as specified in the library's configuration.
4. That's it! You don't need to manually create any design documents or views. The library will handle that automatically when it initializes the CouchDB instance.

Note: If you're using a different database name or have custom configuration settings, make sure to update the library's configuration accordingly.

## Running the Prompt UI

To run the Prompt UI, follow these steps:

1. Navigate to the `azathoth/ui/prompt-ui` directory.
2. Install the dependencies by running `npm install`.
3. Build the React app by running `npm run build`.
4. Navigate back to the root directory of the library.
5. Start the UI server by running `python -m azathoth.ui_server`.
6. Open your browser and visit `http://localhost:5000` to access the Prompt UI.

## MORE SOON
