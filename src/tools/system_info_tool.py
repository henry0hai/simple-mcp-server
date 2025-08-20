# src/tools/system_info_tool.py

from src.utils.utils import (
    get_sys_info,
    get_cpu_usage,
    get_ram_usage,
    get_disk_usage,
    get_uptime,
)
from src.config.config import config

from src.utils.logging_utils import get_logger  
logger = get_logger(__name__)


def get_system_info_tool():
    # System Info
    os_info, python_version, cpu_count = get_sys_info()
    cpu_percent = get_cpu_usage(interval=3)
    ram_used, ram_total, ram_percent = get_ram_usage()
    disk_used, disk_total, disk_percent = get_disk_usage()
    uptime_str = get_uptime()
    app_version = config.app_version

    logger.info("Call get_system_info_tool")

    return {
        "app_version": app_version,
        "os_info": os_info,
        "python_version": python_version,
        "cpu_count": cpu_count,
        "cpu_percent": cpu_percent,
        "ram_used_gb": ram_used,
        "ram_total_gb": ram_total,
        "ram_percent": ram_percent,
        "disk_used_gb": disk_used,
        "disk_total_gb": disk_total,
        "disk_percent": disk_percent,
        "uptime": uptime_str,
    }
