# https://gist.github.com/jmfrank63/5fb9909a8e06c91dead9265cab2f33de
import asyncio
from collections import deque


class AsyncDeque(deque):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._not_empty = asyncio.Condition()  # For signaling when items are added
        self._stopped = False  # To indicate when the deque is stopped

    def __aiter__(self):
        return self

    async def __anext__(self):
        async with self._not_empty:
            while not self and not self._stopped:
                await self._not_empty.wait()  # Wait until an item is added or stopped
            if self._stopped and not self:
                raise StopAsyncIteration
            return self.popleft()

    async def put(self, item):
        """Add an item to the deque and notify waiting consumers."""
        async with self._not_empty:
            self.append(item)
            self._not_empty.notify()

    async def stop(self):
        """Stop all waiting consumers by notifying them."""
        async with self._not_empty:
            self._stopped = True
            self._not_empty.notify_all()

    async def __aenter__(self):
        """Enter context, returning the deque."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit context, ensuring proper cleanup."""
        await self.stop()
