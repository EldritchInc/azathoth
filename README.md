# Azathoth AI Framework

Welcome to the **Azathoth AI Framework**, an innovative Python library designed for constructing agentic intelligences. Our framework facilitates the development of advanced AI agents, leveraging the power of external tools, including Large Language Models (LLMs), image processing systems, and more, to create robust and versatile intelligences.

as far as I know, the only OSS software in development with a song on a released album dedicated to it
[Eris' Gift](https://open.spotify.com/track/6TebeIJkyhUQhvULctPkYc?si=9lZXkCuGSBO9zqp3H19OtQ&context=spotify%3Aalbum%3A0aYdIPm6JOGKJ4DEqiXcwZ)
## Features

- **Versatile Agent Construction**: Build AI agents with complex behaviors, capable of operating in diverse environments.
- **Integration with Advanced Tools**: Seamlessly incorporate LLMs, image recognition systems, and other cutting-edge technologies to enhance agent capabilities.
- **Python-Based**: Utilize the extensive Python ecosystem for development, ensuring ease of use and broad compatibility.
- **Open Source**: Collaborate, modify, and distribute the framework with the support of a growing community.

## Prerequisites

Before you start, ensure you have the following installed on your system:
- Python (3.7 or higher)
- Node.js (v14.0.0 or higher) and npm (v6.0.0 or higher)
- CouchDB (2.3.1 or higher)

## Installation

### CouchDB Setup Instructions

1. **Install CouchDB**: Follow the [official CouchDB installation guide](https://docs.couchdb.org/en/stable/install/index.html). macOS users, please ensure to set an admin password when prompted—a small field for this might be easy to miss.
2. **Configure CouchDB**:
   - Access the CouchDB web interface by navigating to `http://localhost:5984/_utils`.
   - Create a new database named "azathoth" or your preferred name.
   - Ensure the framework's configuration matches your database name.

### Flask Dependencies

Ensure all Python dependencies are installed by running:
```shell
pip install Flask Flask-CORS
```
This installs Flask and Flask-CORS, required to run the UI server. For a complete list of dependencies, refer to the `requirements.txt` file.

### Running the Prompt UI

#### Frontend Setup

1. Navigate to the Prompt UI directory:
   ```shell
   cd azathoth/ui/prompt-ui
   ```
2. Install Node.js dependencies:
   ```shell
   npm install
   ```
3. Build the React application:
   ```shell
   npm run build
   ```

#### Backend Setup

1. Return to the root directory of the Azathoth AI Framework:
   ```shell
   cd ../../
   ```
2. Start the UI server:
   ```shell
   python -m azathoth.ui_server
   ```
3. Access the Prompt UI by visiting `http://localhost:5000` in your browser.

## Configuration Management

Use the `config.json` file to manage all application configurations, including API keys and database information, to simplify the setup process.

## Default Prompt Goal Examples

To help you get started, here are some default prompt goal examples and JSON schemas. [Link to examples]

## Troubleshooting

- **No CouchDB Admin password found**: Ensure you've set an admin password for CouchDB. This field is required during the installation but might be easy to overlook on macOS.
- **ModuleNotFoundError for Flask or Flask-CORS**: Make sure you've installed all Python dependencies from the `requirements.txt` file.
- **Adding a goal crashes on empty JSON schema**: Ensure that the JSON schema for new goals is valid and not empty. Here's a basic schema to start with: [Link to schema]

## Security Audit

We regularly review and update dependencies to ensure security. Our commitment to security is reflected in our choice of reputable dependencies such as Flask for our web server and React for our frontend. We appreciate the community's vigilance and welcome any security audits to help us improve.

## Support the Project

Developing and maintaining open-source projects like the Azathoth AI Framework requires time, effort, and resources. If you find this project useful and want to support its growth, consider becoming a patron. Your contributions can help ensure the project remains up-to-date, secure, and able to evolve with new features and improvements.

[Become a Patron on Patreon](https://www.patreon.com/AzathothAI)

Your support is greatly appreciated, whether it's through contributing code, reporting bugs, or providing financial assistance. Every bit helps make Azathoth AI Framework better for everyone.

## Contributing

We welcome contributions from the community! Whether it's adding new features, improving documentation, or reporting bugs, your help makes Azathoth better for everyone.

## License

The Azathoth AI Framework is open-source software licensed under the [MIT license](LICENSE).
