from fastmcp import FastMCP
from dotenv import load_dotenv
import os
import math
import requests

mcp = FastMCP(name="My First MCP Server")


# Load environment variables from the .env file
load_dotenv()

# Get the port from the environment variable, or use a default if it's not set
port = int(os.getenv("MCP_SERVER_PORT", 8000))
serpapi_key = os.getenv("SERPAPI_KEY", "YOUR_SERPAPI_KEY")

@mcp.tool()
def add(a: int, b: int) -> int:
    """Adds two integer numbers together."""
    return a + b


@mcp.tool()
def search_google(query: str) -> dict:
    """Search Google and return the top results using SerpAPI."""
    api_key = serpapi_key
    url = "https://serpapi.com/search"
    params = {
        "q": query,
        "api_key": api_key,
        "engine": "google"
    }
    response = requests.get(url, params=params)
    return response.json()

@mcp.resource("resource://config")
def get_config() -> dict:
    """Provides the application's configuration."""
    return {"version": "1.0", "author": "Henry0Hai"}


@mcp.resource("greetings://{name}")
def personalized_greeting(name: str) -> str:
    """Generates a personalized greeting for the given name."""
    return f"Hello, {name}! Welcome to the MCP server."


if __name__ == "__main__":
    # Start an HTTP server on port port
    mcp.run(transport="http", host="127.0.0.1", port=port)
