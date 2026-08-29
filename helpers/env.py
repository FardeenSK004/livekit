"""Environment configuration helper."""

import os
from typing import Optional, overload
from dotenv import load_dotenv

# Load .env and .env.local with override=True for consistent local dev overrides
load_dotenv(".env")
load_dotenv(".env.local", override=True)

from custom_types.env import ENV_VARIABLE, PY_ENV


def get_py_env() -> PY_ENV:
    """Return the current python environment name."""
    env = os.getenv("PY_ENV", "development").lower()
    if env in ("production", "prod"):
        return "production"
    if env in ("staging", "stage"):
        return "staging"
    if env in ("test", "testing"):
        return "test"
    return "development"


@overload
def get_env(var: ENV_VARIABLE) -> str: ...


@overload
def get_env(var: ENV_VARIABLE, *, return_none: bool = False) -> Optional[str]: ...


def get_env(var: ENV_VARIABLE, *, return_none: bool = False) -> Optional[str]:
    """Type-safe environment variable retrieval."""
    val = os.getenv(var)
    if val is None or val == "":
        if return_none:
            return None
        return ""
    return val
