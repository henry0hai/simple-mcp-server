# src/config/config.py
import os
from asyncio import Lock
from dotenv import load_dotenv
from src.__version__ import VERSION
from src.utils.logging_utils import get_logger

# Load .env file
load_dotenv()

# Environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
ADMIN_USER_NAME = os.getenv("ADMIN_USER_NAME")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
WEATHER_BASE_URL = "http://api.openweathermap.org/data/2.5/weather"
CITIES = os.getenv("CITIES", "").split(",")
HF_API_KEY = os.getenv("HF_API_KEY")
GRAPHQL_SERVER_URL = os.getenv(
    "GRAPHQL_SERVER_URL", "http://192.168.1.199:3000/graphql"
)
GRAPHQL_API_TOKEN = os.getenv("GRAPHQL_API_TOKEN")

# Validate environment variables
if not all([TELEGRAM_BOT_TOKEN, ADMIN_ID, WEATHER_API_KEY, CITIES]):
    raise ValueError(
        "Missing required environment variables: TELEGRAM_BOT_TOKEN, ADMIN_ID, WEATHER_API_KEY, or CITIES"
    )

# Weather condition icons
WEATHER_ICONS = {
    "Clear": "☀️",
    "Clouds": "☁️",
    "Rain": "🌧️",
    "Drizzle": "🌦️",
    "Thunderstorm": "⛈️",
    "Snow": "❄️",
    "Mist": "🌫️",
    "Haze": "🌫️",
}
ICON_WIND, ICON_TEMP, ICON_HUMIDITY = "💨", "🌡️", "💧"
ICON_SUNRISE, ICON_SUNSET, ICON_TIME = "🌅", "🌇", "🕒"

# Global state
START_TIME = None
DEBUG_TIME_LOOP = 1800  # 30 minutes
SCHEDULED_WEATHER_LOOP = 7200  # 2 hours


class BotConfig:
    def __init__(self):
        self.is_bot_running = False
        self.start_time = None
        self.job_queue = None
        self.telegram_bot_token = TELEGRAM_BOT_TOKEN
        self.admin_user_name = ADMIN_USER_NAME
        self.admin_id = ADMIN_ID
        self.weather_api_key = WEATHER_API_KEY
        self.weather_base_url = WEATHER_BASE_URL
        self.cities = CITIES
        self.hf_key_api = HF_API_KEY
        self.debug_time_loop = DEBUG_TIME_LOOP
        self.scheduled_weather_loop = SCHEDULED_WEATHER_LOOP
        self.graphql_server_url = GRAPHQL_SERVER_URL
        self.graphql_api_token = GRAPHQL_API_TOKEN
        self.app_version = VERSION


config = BotConfig()

# Bot state (avoid global variables where possible)
bot_lock = Lock()  # Keep it as asyncio.Lock for async compatibility

# Test log to confirm setup
logger = get_logger(__name__)
logger.info("Logging initialized!")
