import asyncio
import logging
from typing import Set

logger = logging.getLogger(__name__)

class Broadcaster:
    def __init__(self):
        self._queues: Set[asyncio.Queue] = set()

    async def subscribe(self) -> asyncio.Queue:
        queue = asyncio.Queue()
        self._queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue):
        if queue in self._queues:
            self._queues.remove(queue)

    async def publish(self, message: str):
        logger.info(f"Broadcasting event: {message} to {len(self._queues)} subscribers")
        for queue in list(self._queues):
            await queue.put(message)

# Global singleton
broadcaster = Broadcaster()
