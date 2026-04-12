import asyncio
import itertools
import logging
import ssl

from ntcpycon.adeque import AsyncDeque

from websockets.client import connect

import ntcpycon.abstract

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

INFO_CYCLE = 50000
MAX_NTC_RCV = 100
MAX_NTC_SEND = 100


class WSSender(ntcpycon.abstract.Sender):
    def __init__(self, uri: str, no_verify=False):
        self.uri = uri
        self.no_verify = no_verify
        self.queue = asyncio.Queue()
        self.connect_kwargs = (
            {"ssl": ssl._create_unverified_context()} if no_verify else {}
        )
        self.stopped = False
        self.masked_uri = "/".join(self.uri.split("/")[:-1]) + "/<hidden>"

    def __repr__(self):
        uri = self.masked_uri
        no_verify = self.no_verify
        return f"{type(self).__name__}({uri=}, {no_verify=})"

    async def read_handler(self, websocket, queue: Queue | None = None):
        async for message in websocket:
            logger.info(f"Received from websocket: {message}")
            if queue is not None:
                await queue.put(message)

    async def write_handler(self, websocket, queue: Queue | None = None):
        ticker = itertools.cycle(range(INFO_CYCLE))
        frame_count = 0
        q = self.queue if queue is None else queue
        while True:
            if not next(ticker):
                logger.info(
                    f"Web Socket to {self.masked_uri} open.  Frame Send Count: {frame_count}"
                )
            if self.stopped:
                logger.debug("Stopping")
                break
            try:
                message = await q.get()
                if not message:
                    logger.info("Empty message received.  Stopping.")
                    break
                else:
                    logger.debug(f"Msg len: {len(message)} -> {self.masked_uri}")
                    await websocket.send(message)
                    frame_count += 1
            except Exception as exc:
                logger.error(f"{type(exc).__name__}: {exc!s}")
                break
        logger.info("while loop broken")


    async def send(self):
        """
        this name is not good.

        this should be called "init" or "run"
        """
        websocket = await connect(self.uri, **self.connect_kwargs)  # type: ignore
        await asyncio.gather(
            self.read_handler(websocket),
            self.write_handler(websocket),
        )




class NewWSSender:
    def __init__(self, uri: str, no_verify=True):
        self.uri = uri
        self.no_verify = no_verify
        self.game_data = AsyncDeque(maxlen=MAX_NTC_SEND)
        self.ntc_data = AsyncDeque(maxlen=MAX_NTC_RCV)
        self.connect_kwargs = (
            {"ssl": ssl._create_unverified_context()} if no_verify else {}
        )
        self.masked_uri = "/".join(self.uri.split("/")[:-1]) + "/<hidden>"
        self.task = None

    async def read_handler(self):
        async for message in self.websocket:
            logger.info(f"Received from websocket: {message}")
            await self.ntc_data.put(message)

    async def write_handler(self):
        ticker = itertools.cycle(range(INFO_CYCLE))
        frame_count = 0
        async for message in self.game_data:
            if not next(ticker):
                logger.info(
                    f"Web Socket to {self.masked_uri} open.  Frame Send Count: {frame_count}"
                )
            try:
                await self.websocket.send(message)
                frame_count += 1
            except Exception as exc:
                logger.error(f"{type(exc).__name__}: {exc!s}")
                break

    async def end(self):
        await self.game_data.stop()
        if getattr(self, 'websocket', None):
            await self.websocket.close()
        if self.task:
            logger.info('awaiting task end')
            await self.task
            logger.info('task ended')

    def connect(self, callback):
        self.task = asyncio.create_task(self._connect())
        self.task.add_done_callback(callback)

    async def _connect(self):
        self.websocket = await connect(self.uri, **self.connect_kwargs)  # type: ignore
        self.task = asyncio.gather(
            self.read_handler(),
            self.write_handler(),
        )
