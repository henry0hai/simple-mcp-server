# src/utils/utils.py
import pytz
import time
import psutil
import requests
import platform
from datetime import datetime
from src.config.config import (
    config,
    WEATHER_API_KEY,
    WEATHER_BASE_URL,
    WEATHER_ICONS,
    ICON_WIND,
    ICON_TEMP,
    ICON_HUMIDITY,
    ICON_SUNRISE,
    ICON_SUNSET,
    ICON_TIME,
)

from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


def degrees_to_direction(deg):
    directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    index = round(deg / 45) % 8
    return directions[index]


async def get_weather(city, context=None, chat_id=None):
    if not city or not isinstance(city, str) or not city.strip():
        error_msg = "Invalid city name provided"
        if context and chat_id:
            await context.bot.send_message(chat_id=chat_id, text=error_msg)
        logger.error(error_msg)
        return None

    try:
        params = {"q": city, "appid": WEATHER_API_KEY, "units": "metric"}
        response = requests.get(WEATHER_BASE_URL, params=params)
        response.raise_for_status()  # Raise an exception for HTTP errors
        data = response.json()

        if data.get("cod") != 200:
            error_msg = f"Error for {city}: {data.get('message', 'City not found')}"
            if context and chat_id:
                await context.bot.send_message(chat_id=chat_id, text=error_msg)
            logger.warning(error_msg)
            return None

        condition_main = data["weather"][0]["main"]
        condition_desc = data["weather"][0]["description"]
        temp = data["main"]["temp"]
        feels_like = data["main"]["feels_like"]
        temp_max = data["main"]["temp_max"]
        temp_min = data["main"]["temp_min"]
        humidity = data["main"]["humidity"]
        wind_speed = data["wind"]["speed"] * 3.6
        wind_deg = data["wind"]["deg"]
        sunrise = data["sys"]["sunrise"]
        sunset = data["sys"]["sunset"]
        timezone_offset = data["timezone"]
        country = data["sys"]["country"]

        icon = WEATHER_ICONS.get(condition_main, "🌍")
        utc = pytz.utc
        local_tz = pytz.timezone(
            f"Etc/GMT{'+' if timezone_offset < 0 else '-'}{abs(timezone_offset) // 3600}"
        )
        sunrise_dt = datetime.fromtimestamp(sunrise, utc).astimezone(local_tz)
        sunset_dt = datetime.fromtimestamp(sunset, utc).astimezone(local_tz)
        current_dt = datetime.now(utc).astimezone(local_tz)
        local_now = datetime.now()

        hours_offset = abs(timezone_offset) // 3600
        minutes_offset = (abs(timezone_offset) % 3600) // 60
        tz_offset_str = f"GMT{'+' if timezone_offset >= 0 else '-'}{hours_offset:02d}:{minutes_offset:02d}"

        weather_info = (
            f"Weather in: *{city}:*\n"
            f"{icon} Condition: {condition_main} - {condition_desc}\n"
            f"{ICON_TEMP} Temp: {temp}°C, Feels like: {feels_like}°C\n"
            f"{ICON_TEMP} Range: {temp_max}°C (max) - {temp_min}°C (min)\n"
            f"{ICON_HUMIDITY} Humidity: {humidity}%\n"
            f"{ICON_WIND} Wind: {wind_speed:.2f} km/h, Direction: {degrees_to_direction(wind_deg)}\n"
            f"{ICON_SUNRISE} Sunrise: {sunrise_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
            f"{ICON_SUNSET} Sunset: {sunset_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
            f"{ICON_TIME} Location Time: {current_dt.strftime('%Y-%m-%d %H:%M:%S %Z')} ({tz_offset_str}, {country})\n"
            f"{ICON_TIME} Local Time: {local_now.strftime('%Y-%m-%d %H:%M:%S %Z')}"
        )

        logger.info(f"Weather data retrieved for {city}")
        return weather_info

    except requests.RequestException as e:
        logger.error(f"HTTP error fetching weather for {city}: {str(e)}")
        if context and chat_id:
            await context.bot.send_message(
                chat_id=chat_id, text=f"Error fetching weather for {city}: {str(e)}"
            )
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching weather for {city}: {str(e)}")
        if context and chat_id:
            await context.bot.send_message(
                chat_id=chat_id, text=f"Error fetching weather for {city}: {str(e)}"
            )
        return None


# Helper functions for resource usage
def get_cpu_usage(interval=1):
    """Get CPU usage percentage."""
    return psutil.cpu_percent(interval=interval)


def get_ram_usage():
    """Get RAM usage in GB and percentage."""
    memory = psutil.virtual_memory()
    used = memory.used / (1024 * 1024 * 1024)  # Convert to GB
    total = memory.total / (1024 * 1024 * 1024)  # Convert to GB
    return used, total, memory.percent


def get_disk_usage(path="/"):
    """Get disk usage in GB and percentage."""
    disk = psutil.disk_usage(path)
    used = disk.used / (1024 * 1024 * 1024)  # Convert to GB
    total = disk.total / (1024 * 1024 * 1024)  # Convert to GB
    return used, total, disk.percent


def get_sys_info():
    """Get system information."""
    os_info = platform.system() + " " + platform.release()
    python_version = platform.python_version()
    cpu_count = psutil.cpu_count()
    return os_info, python_version, cpu_count


def get_uptime():
    """Calculate and return formatted uptime or None if start_time is not set."""
    if config.start_time is None:
        return None
    uptime_seconds = time.time() - config.start_time
    hours, remainder = divmod(int(uptime_seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes}m {seconds}s"
