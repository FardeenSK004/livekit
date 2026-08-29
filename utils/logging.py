"""Logging setup and formatters."""

import sys
import logging


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Configure a named logger with standard stdout formatter."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s]: %(message)s"))
        logger.addHandler(handler)
    logger.propagate = True
    return logger
