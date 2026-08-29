"""Dispatcher background task wrapper."""

from core.dispatcher import main, dispatch_call, get_lk_client

__all__ = ["main", "dispatch_call", "get_lk_client"]

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
