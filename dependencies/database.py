"""Database connection and pool dependencies for FastAPI."""

import os
from typing import Annotated, Optional
import asyncpg
from fastapi import Depends, Request


async def get_db_connection(request: Optional[Request] = None) -> asyncpg.Connection:
    """Create a PostgreSQL connection for queries."""
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return await asyncpg.connect(dsn=database_url, timeout=5.0)
    return await asyncpg.connect(
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        database=os.getenv("POSTGRES_DB"),
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT"),
        timeout=5.0,
    )


DatabaseConnectionService = Annotated[asyncpg.Connection, Depends(get_db_connection)]

__all__ = ["get_db_connection", "DatabaseConnectionService"]
