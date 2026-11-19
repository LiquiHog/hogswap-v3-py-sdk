"""An asyncio client: the same methods as HogswapClient, awaitable.

Each call runs the synchronous client in a worker thread (``asyncio.to_thread``), so the shared
rate limiter and retries behave the same way. No extra dependencies.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Dict, Optional

from .client import HogswapClient


class AsyncHogswapClient:
    """``await client.quote(...)``, ``await client.execute(...)``, and so on.

    Takes the same arguments as :class:`HogswapClient`. ``client.sync`` is the underlying
    synchronous client.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.sync = HogswapClient(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self.sync, name)
        if not callable(attr) or name.startswith("_"):
            return attr

        async def call(*args: Any, **kwargs: Any) -> Any:
            return await asyncio.to_thread(attr, *args, **kwargs)

        call.__name__ = name
        call.__doc__ = attr.__doc__
        return call

    async def iterate_assets(self, *, limit: Optional[int] = None, q: Optional[str] = None) -> AsyncIterator[Dict[str, Any]]:
        cursor = None
        while True:
            page = await asyncio.to_thread(self.sync.assets, limit=limit, cursor=cursor, q=q)
            for a in page["assets"]:
                yield a
            cursor = page.get("next_cursor")
            if not cursor:
                return

    async def iterate_pools(self, **filters: Any) -> AsyncIterator[Dict[str, Any]]:
        cursor = None
        while True:
            page = await asyncio.to_thread(self.sync.pools, cursor=cursor, **filters)
            for p in page["pools"]:
                yield p
            cursor = page.get("next_cursor")
            if not cursor:
                return
