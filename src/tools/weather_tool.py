# src/tools/weather_tool.py

from src.utils.utils import get_weather


def get_weather_tool(city: str) -> str:
    """Get current weather information for a given city."""
    return get_weather(city)
