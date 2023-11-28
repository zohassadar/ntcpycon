import asyncio
import itertools
import logging
import ssl

from websockets.client import connect

import ntcpycon.abstract
import ntcpycon.pcap_replay

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

INFO_CYCLE = 50000


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

    async def read_handler(self, websocket):
        async for message in websocket:
            logger.info(f"Received from websocket: {message}")

    async def write_handler(self, websocket):
        ticker = itertools.cycle(range(INFO_CYCLE))
        frame_count = 0
        while True:
            if not next(ticker):
                logger.info(
                    f"Web Socket to {self.masked_uri} open.  Frame Send Count: {frame_count}"
                )
            if self.stopped:
                logger.debug("Stopping")
                break
            try:
                message = await self.queue.get()
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
        websocket = await connect(self.uri, **self.connect_kwargs)  # type: ignore
        await asyncio.gather(
            self.read_handler(websocket),
            self.write_handler(websocket),
        )
