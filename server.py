from fastmcp import FastMCP
from dotenv import load_dotenv
from serpapi import GoogleSearch

import os
import math
import requests

# Import the system info tool
from src.tools.system_info_tool import get_system_info_tool

# Import the weather tool
from src.tools.weather_tool import get_weather_tool

# Import the budget management tools
from src.tools.budget_management_tool import (
    add_expense_tool,
    add_income_tool,
    get_budget_summary_tool,
    get_expense_report_tool,
    get_available_categories_tool,
    predict_category_tool,
)

# Import the dynamic tool creator
from src.tools.dynamic_tool_creator import create_dynamic_tool

from src.utils.logging_utils import get_logger

from src.config.config import config

logger = get_logger(__name__)


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
    params = {"q": query, "api_key": api_key, "engine": "google"}
    # response = requests.get(url, params=params)
    # return response.json()

    search = GoogleSearch(params)
    results = search.get_dict()
    organic_results = results.get("organic_results", [])
    logger.info(f"Calling SerpAPI for query: {query}")
    return {"results": organic_results}


@mcp.tool()
def system_info() -> dict:
    """Retrieves server system information."""
    return get_system_info_tool()


@mcp.tool()
def get_weather(city: str) -> str:
    """Get current weather information for a given city."""
    return get_weather_tool(city)


@mcp.tool()
def add_expense(description: str, amount: float, category: str = None) -> dict:
    """Add a new expense transaction to the budget system. Category will be auto-detected if not provided."""
    return add_expense_tool(description, amount, category)


@mcp.tool()
def add_income(source: str, amount: float) -> dict:
    """Add a new income entry to the budget system."""
    return add_income_tool(source, amount)


@mcp.tool()
def get_budget_summary(month: str = None) -> dict:
    """Get comprehensive budget summary including transactions, incomes, and savings. If no month specified, defaults to current month (YYYY-MM format)."""
    return get_budget_summary_tool(month)


@mcp.tool()
def get_expense_report(
    month: int = None, year: int = None, all_data: bool = False
) -> str:
    """Generate and export expense report in CSV format. Defaults to current month/year if no parameters specified and all_data is False."""
    return get_expense_report_tool(month, year, all_data)


@mcp.tool()
def get_available_categories() -> dict:
    """Get list of all available expense categories."""
    return get_available_categories_tool()


@mcp.tool()
def predict_category(description: str) -> dict:
    """Predict the most appropriate category for an expense description without adding it."""
    return predict_category_tool(description)


@mcp.tool()
async def generic_tool_creation(
    user_request: str,
    preferred_language: str = "auto",
    send_to_telegram: bool = True,
    chat_id: str = config.admin_id,
) -> str:
    """
    Dynamically create and execute bash or Python scripts based on user requests.

    This tool can generate scripts for common system tasks like:
    - Getting server IP address
    - Checking disk usage
    - Memory usage analysis
    - Process listing
    - Date/time information
    - And more based on natural language requests

    Args:
        user_request: Natural language description of what you want the script to do
        preferred_language: "auto" (default), "bash", or "python"
        send_to_telegram: Whether to send results to Telegram bot (default: True)
        chat_id: Telegram chat ID to send to (uses admin ID if not provided)

    Returns:
        Formatted string with execution results and output
    """
    result = await create_dynamic_tool(
        user_request, preferred_language, send_to_telegram, chat_id
    )

    # Format the response for better MCP client display
    if result["success"]:
        # Extract the key information from stdout for AI processing
        output = result["stdout"].strip()

        # Create a clean, AI-friendly response
        if result.get("is_reused", False):
            response = f"Script reused successfully. "
        else:
            response = f"Script executed successfully. "

        response += f"Generated {result['language']} script: {result['filename']}. "
        response += f"Result: {output}"

        # Add any warnings if present
        if result["stderr"] and result["stderr"].strip():
            # Filter out logging messages from stderr for cleaner output
            stderr_lines = result["stderr"].strip().split("\n")
            non_log_errors = [
                line
                for line in stderr_lines
                if not any(
                    log_indicator in line.lower()
                    for log_indicator in [
                        "info",
                        "warning",
                        "debug",
                        "logging initialized",
                    ]
                )
            ]
            if non_log_errors:
                response += f" Warning: {' '.join(non_log_errors)}"

        return response
    else:
        error_msg = f"Script execution failed. "
        if "error" in result:
            error_msg += f"Error: {result['error']} "
        if result.get("stderr") and result["stderr"].strip():
            error_msg += f"Details: {result['stderr'].strip()} "
        if result.get("stdout") and result["stdout"].strip():
            error_msg += f"Partial output: {result['stdout'].strip()}"

        return error_msg


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
