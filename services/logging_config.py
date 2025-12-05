"""Logging configuration for the application."""

import logging
import logging.handlers
import os
from datetime import datetime


def setup_logging(log_dir: str = None) -> logging.Logger:
    """
    Set up application logging.

    Args:
        log_dir: Directory for log files. Defaults to app directory.

    Returns:
        Configured logger instance.
    """
    if log_dir is None:
        log_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    log_file = os.path.join(log_dir, "aichatroom.log")

    # Create logger
    logger = logging.getLogger("AIChatRoom")
    logger.setLevel(logging.DEBUG)

    # Prevent duplicate handlers
    if logger.handlers:
        return logger

    # File handler - detailed logging with rotation
    # Keep 5 backup files, max 10MB each (50MB total max)
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s.%(funcName)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_format)

    # Console handler - info and above
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter('%(levelname)s: %(message)s')
    console_handler.setFormatter(console_format)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    logger.info(f"Logging initialized. Log file: {log_file}")

    return logger


def get_logger(name: str = None) -> logging.Logger:
    """
    Get a logger instance.

    Args:
        name: Logger name (will be prefixed with AIChatRoom.)

    Returns:
        Logger instance.
    """
    if name:
        return logging.getLogger(f"AIChatRoom.{name}")
    return logging.getLogger("AIChatRoom")
