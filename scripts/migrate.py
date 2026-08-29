"""Database migration runner script."""

import os
import asyncio
import importlib
import logging
from glob import glob
from dotenv import load_dotenv

load_dotenv(".env.local")
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scripts.migrate")


async def main():
    migration_files = sorted(glob("migrations/00*.py"))
    logger.info(f"Found {len(migration_files)} migration files.")
    for mf in migration_files:
        mod_name = mf.replace("/", ".").replace(".py", "")
        logger.info(f"Running migration: {mod_name}")
        mod = importlib.import_module(mod_name)
        if hasattr(mod, "run_migration"):
            await mod.run_migration()
        elif hasattr(mod, "main"):
            await mod.main()
    logger.info("All migrations finished.")


if __name__ == "__main__":
    asyncio.run(main())
