# src/commands.py
from telegram import Update
from datetime import datetime
from tzlocal import get_localzone
from telegram.ext import ContextTypes
from src.utils.utils import (
    get_weather,
    get_cpu_usage,
    get_ram_usage,
    get_disk_usage,
    get_sys_info,
    get_uptime,
)
from src.config.config import config, bot_lock
from src.scheduler import on_startup, scheduled_weather, debug_time
from src.ai import process_with_ai


from src.utils.logging_utils import get_logger  
logger = get_logger(__name__)

# New handler for non-command text
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text
    user_id = update.message.from_user.id
    username = update.message.from_user.username or "Unknown"

    # Log user input (when database is ready)
    # log_to_database(user_id, username, user_input)

    # Process with AI
    response = await process_with_ai(user_input, update, context)
    if response is not None and response.strip():  # Check for None and empty strings
        await update.message.reply_text(response)
    elif response is not None:
        logger.warning(
            f"Empty response received for input '{user_input}' from {username} ({user_id})"
        )

    # Log bot response (optional, when database is ready)
    # log_to_database(user_id, username, f"Bot response: {response}", is_bot=True)


# Generic async command wrapper for error handling
async def run_command(update: Update, func, error_message="Error occurred"):
    """Wrapper to handle exceptions in async commands."""
    try:
        result = func()
        return result
    except Exception as e:
        await update.message.reply_text(f"{error_message}: {str(e)}")
        logger.error(f"{error_message}: {str(e)}")
        return None


# Command implementations
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE, params=None):
    async with bot_lock:
        user_name = update.message.from_user.username
        if user_name != config.admin_user_name:
            await update.message.reply_text("Sorry, only the admin can stop the bot.")
            return

        logger.info(
            f"Stop command received. config.is_bot_running: {config.is_bot_running}"
        )

        if config.job_queue:
            logger.info(f"Current job count: {len(config.job_queue.jobs())}")
        else:
            logger.warning("Job queue is None")

        await update.message.reply_text("Stopping bot activities...")
        logger.info("Bot activities stopped by admin")

        if config.job_queue and config.job_queue.jobs():
            jobs = config.job_queue.jobs()
            logger.info(f"Found {len(jobs)} scheduled jobs before removal")
            for job in jobs:
                job.schedule_removal()
            remaining_jobs = len(config.job_queue.jobs())
            logger.info(f"After removal, {remaining_jobs} jobs remain")
            if remaining_jobs > 0:
                logger.warning("Some jobs may not have been removed immediately")
        else:
            logger.info("No scheduled jobs to remove or job queue is None")

        config.is_bot_running = False
        await update.message.reply_text("All scheduled activities have been stopped.")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE, params=None):
    async with bot_lock:
        user = update.message.from_user.first_name
        if config.is_bot_running:
            message = f"Hello {user}! The bot is already running. Use /help to see available commands."
            await update.message.reply_text(message)
            return

        message = f"Hello {user}! Restarting bot activities now. Use /help to see available commands."
        await update.message.reply_text(message)

        if config.job_queue:
            config.job_queue.run_once(on_startup, 0, data={"user": user})
            config.job_queue.run_repeating(
                scheduled_weather, interval=config.scheduled_weather_loop, first=0
            )
            config.job_queue.run_repeating(
                debug_time, interval=config.debug_time_loop, first=0
            )
            logger.info(f"User {user} restarted all bot activities")

        config.is_bot_running = True


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with bot_lock:
        help_text = """
        Available commands:
        /start - Start the bot
        /help - Show this help message
        /say <message> - Echo your message
        /status - Check bot status
        /cpu - Get CPU usage
        /ram - Get RAM usage
        /disk - Get disk usage
        /stop - Stop the bot (admin only)
        /weather <city> - Get current weather
        /uptime - Show bot uptime
        /info - Show system information
        """
        await update.message.reply_text(help_text)


async def say(update: Update, context: ContextTypes.DEFAULT_TYPE, params=None):
    async with bot_lock:
        if context.args:
            message = " ".join(context.args)
            await update.message.reply_text(f"You said: {message}")
        else:
            await update.message.reply_text("Please provide a message after /say")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE, params=None):
    async with bot_lock:
        local_tz = get_localzone()  # Auto-detect system timezone
        current_time = datetime.now(local_tz).strftime("%Y-%m-%d %H:%M:%S %Z (%z)")
        await update.message.reply_text(f"Bot is running! Current time: {current_time}")


async def cpu(update: Update, context: ContextTypes.DEFAULT_TYPE, params=None):
    async with bot_lock:
        cpu_percent = await run_command(
            update, lambda: get_cpu_usage(interval=1), "Error getting CPU usage"
        )
        if cpu_percent is not None:
            await update.message.reply_text(f"CPU Usage: {cpu_percent}%")


async def ram(update: Update, context: ContextTypes.DEFAULT_TYPE, params=None):
    async with bot_lock:
        result = await run_command(update, get_ram_usage, "Error getting RAM usage")
        if result:
            used, total, percent = result
            await update.message.reply_text(
                f"RAM Usage: {used:.2f}GB / {total:.2f}GB ({percent}%)"
            )


async def disk(update: Update, context: ContextTypes.DEFAULT_TYPE, params=None):
    async with bot_lock:
        result = await run_command(update, get_disk_usage, "Error getting disk usage")
        if result:
            used, total, percent = result
            await update.message.reply_text(
                f"Disk Usage: {used:.2f}GB / {total:.2f}GB ({percent}%)"
            )


async def weather(update: Update, context: ContextTypes.DEFAULT_TYPE, params=None):
    async with bot_lock:
        if params:
            city = params
        elif context.args:
            city = " ".join(context.args)
        else:
            await update.message.reply_text(
                "🌦️ Please provide a city name (e.g., 'weather London' or '/weather London')"
            )
            return
        weather_info = await get_weather(city)
        if weather_info:
            await update.message.reply_text(weather_info, parse_mode="Markdown")


async def uptime(update: Update, context: ContextTypes.DEFAULT_TYPE, params=None):
    async with bot_lock:
        uptime_str = get_uptime()
        if uptime_str is None:
            await update.message.reply_text("Bot start time not set!")
        else:
            await update.message.reply_text(f"Bot uptime: {uptime_str}")


async def info(update: Update, context: ContextTypes.DEFAULT_TYPE, params=None):
    async with bot_lock:
        # System Info
        system_result = await run_command(
            update, get_sys_info, "Error getting system info"
        )

        # Resource Usage
        cpu_percent = await run_command(
            update, lambda: get_cpu_usage(interval=3), "Error getting CPU usage"
        )
        ram_result = await run_command(update, get_ram_usage, "Error getting RAM usage")
        disk_result = await run_command(
            update, get_disk_usage, "Error getting disk usage"
        )

        if (
            cpu_percent is None
            or ram_result is None
            or disk_result is None
            or system_result is None
        ):
            return  # Error messages already sent by run_command

        os_info, python_version, cpu_count = system_result
        ram_used, ram_total, ram_percent = ram_result
        disk_used, disk_total, disk_percent = disk_result

        app_version = config.app_version

        # Uptime
        uptime_str = get_uptime()

        # Formatted message with icons (using HTML for better formatting)
        message = (
            "<b>System Information</b> 📊\n"
            f"📌 <b>App Version:</b> {app_version}\n"
            f"💻 <b>OS:</b> {os_info}\n"
            f"🐍 <b>Python:</b> {python_version}\n"
            f"🧠 <b>CPU Cores:</b> {cpu_count}\n\n"
            f"⏰ <b>Uptime:</b> {uptime_str if uptime_str else 'Not available'}\n"
            f"\n"
            "<b>Resource Usage</b> ⚙️\n"
            f"📈 <b>CPU:</b> {cpu_percent}% (over 3s)\n"
            f"🧮 <b>RAM:</b> {ram_used:.2f}GB / {ram_total:.2f}GB ({ram_percent}%)\n"
            f"💾 <b>Disk:</b> {disk_used:.2f}GB / {disk_total:.2f}GB ({disk_percent}%)"
        )

        await update.message.reply_text(message, parse_mode="HTML")
