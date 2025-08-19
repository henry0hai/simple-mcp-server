# Simple MCP Server & Client Example

This project demonstrates how to build and interact with a simple Model Context Protocol (MCP) server using Python. The server exposes tools and resources, and the client shows how to call them asynchronously.

## Features
- Add two numbers (`add` tool)
- Search Google using SerpAPI (`search_google` tool)
- Get server config (`get_config` resource)
- Get a personalized greeting (`personalized_greeting` resource)

---

## Setup

### 1. Clone the repository
```
git clone git@github.com:henry0hai/simple-mcp-server.git
cd simple-mcp-server
```

### 2. Create and activate a Python virtual environment (optional but recommended)
```
python3 -m venv mcp-env
source mcp-env/bin/activate
```

### 3. Install dependencies
```
pip install -r requirements.txt
```

### 4. Set up environment variables
Create a `.env` file in the project root with your SerpAPI key:
```
SERPAPI_KEY=your_serpapi_key_here
```

---

## Running the MCP Server

```
python server.py
```
The server will start on `http://127.0.0.1:8000/mcp` (or the port set in your `.env` as `MCP_SERVER_PORT`).

---

## Running the MCP Client

```
python client.py
```
You should see demo calls to the `add` tool, `get_config` resource, and `personalized_greeting` resource, with results printed to the console.

---

## Adding More Tools
- To add more tools, define a new function in `server.py` and decorate it with `@mcp.tool()`.
- For new resources, use `@mcp.resource("resource://your_resource")`.

---

## Notes
- The `search_google` tool requires a free [SerpAPI](https://serpapi.com/) key.
- For production use, secure your API keys and consider error handling and rate limits.

> **Notes**: I using qdrant as a vector database for storing and retrieving embeddings.

```bash
docker run -p 6333:6333 -p 6334:6334 \
    -v "$(pwd)/qdrant_storage:/qdrant/storage:z" \
    qdrant/qdrant
```

---

## License
MIT

