import sys
from loguru import logger
from config.settings import settings


def setup_logging() -> None:
    logger.remove()  # Remove default handler

    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    # Console
    logger.add(
        sys.stdout,
        format=log_format,
        level=settings.app_log_level,
        colorize=True,
    )

    # File (rotating)
    logger.add(
        "logs/sdlc_pipeline_{time:YYYY-MM-DD}.log",
        format=log_format,
        level=settings.app_log_level,
        rotation="00:00",      # New file each day
        retention="14 days",
        compression="gz",
    )

    logger.info(f"Logging initialised | env={settings.app_env} | level={settings.app_log_level}")
