"""Logging configuration — ColorFormatter and setup helpers."""

from __future__ import annotations

import logging
import os
import sys

from colorama import Back, Fore, Style, init as colorama_init

colorama_init(autoreset=True)


class ColorFormatter(logging.Formatter):
    LEVEL_COLORS = {
        logging.DEBUG: Fore.CYAN,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.RED + Back.WHITE,
    }

    def format(self, record):
        record.raw_msg = record.getMessage()
        color = self.LEVEL_COLORS.get(record.levelno, Fore.WHITE)
        record.msg = f"{color}{record.msg}{Style.RESET_ALL}"
        return super().format(record)


def setup_logger(
    name: str,
    level: int = logging.INFO,
    fmt: str | None = None,
) -> logging.Logger:
    """Create a configured logger for a module."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        return logger

    _is_inference = os.getenv("LIVEKIT_AGENTS_INFERENCE") == "1"
    _proc_type = "Inference Subprocess" if _is_inference else "Main Worker"
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(
        ColorFormatter(
            fmt
            or f"%(asctime)s INFO (Type: {_proc_type}, PID: {os.getpid()}) {name}: %(message)s"
        )
    )
    logger.addHandler(_handler)
    logger.propagate = True
    return logger
