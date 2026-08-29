"""Backward-compatible wrapper for core.dispatcher."""

from core.dispatcher import *

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
