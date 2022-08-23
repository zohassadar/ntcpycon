import asyncio
import logging
import ssl

from websockets.client import connect

import ntcpycon.abstract
import ntcpycon.binaryframe
import ntcpycon.pcap_replay

logger = logging.getLogger()
logger.addHandler(logging.NullHandler())


class WSSender(ntcpycon.abstract.Sender):
    def __init__(self, uri: str, no_verify=False):
        self.uri = uri
        self.no_verify = no_verify
        self.queue = asyncio.Queue()
        self.connect_kwargs = (
            {"ssl": ssl._create_unverified_context()} if no_verify else {}
        )
        self.stopped = False

    def __repr__(self):
        uri=self.uri
        no_verify=self.no_verify
        return f'{type(self).__name__}({uri=}, {no_verify=})'


    async def read_handler(self, websocket):
        async for message in websocket:
            logger.info(f"Received from websocket: {message}")

    async def write_handler(self, websocket):
        while True:
            if self.stopped:
                logger.debug("Stopping")
                break
            try:
                message = await self.queue.get()
                if not message:
                    logger.info("No message.  Stopping.")
                    break
                else:
                    logger.debug(f"Msg len: {len(message)} -> {self.uri}")
                    await websocket.send(message)
            except Exception as exc:
                logger.error(f"{type(exc).__name__}: {exc!s}")
                break
        logger.info("while loop broken")

    async def send(self):
        websocket = await connect(self.uri, **self.connect_kwargs)
        await asyncio.gather(
            self.read_handler(websocket),
            self.write_handler(websocket),
        )
