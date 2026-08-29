"""Database connection provider for MCP server."""

import os
import asyncpg
from dotenv import load_dotenv

load_dotenv(".env.local")
load_dotenv()


async def get_db_connection() -> asyncpg.Connection:
    """Acquire asyncpg database connection from environment."""
    return await asyncpg.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        database=os.getenv("POSTGRES_DB"),
    )
