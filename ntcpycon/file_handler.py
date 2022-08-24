import asyncio
import itertools
import logging

import sys
import ntcpycon.abstract

WRITE_WAIT_LOOPS = 500

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

Receiver = ntcpycon.abstract.Receiver
Sender = ntcpycon.abstract.Sender


class FileReceiver(Receiver):
    def __init__(
        self,
        queues: list[asyncio.Queue],
        filename: str,
    ):
        self.queues = queues
        self.filename = filename
        try:
            open(filename)
        except OSError:
            sys.exit(f"Unable to open {filename}")

    def __repr__(self):
        queues = self.queues
        filename = self.filename
        return f"{type(self).__name__}({queues=}, {filename=})"

    async def receive(self):
        with open(
            self.filename,
            "rb",
        ) as file:
            logger.info(f"Opening {self.filename}")
            while True:
                length = int.from_bytes(
                    file.read(2),
                    byteorder="big",
                )
                if not length:
                    logger.info("End of file reached")
                    break
                payload = file.read(length)
                for queue in self.queues:
                    await queue.put(payload)


class FileWriter(Sender):
    def __init__(
        self,
        filename: str,
        overwrite: bool = False,
    ):
        self.filename = filename
        self.overwrite = overwrite

        self.queue = asyncio.Queue()

        self.buffer = b""

        exists = False
        try:
            open(filename, "rb")
            exists = True
        except OSError:
            pass
        if exists and not overwrite:
            sys.exit(f"{filename} exists and overwrite flag is not set")

        # Blank out the file or establish it
        open(self.filename, "wb")

    def __repr__(self):
        filename = self.filename
        overwrite = self.overwrite
        return f"{type(self).__name__}({filename=}, {overwrite=})"

    def write_buffer(self):
        length = len(self.buffer)
        if not length:
            logger.warning("Unable to write empty buffer")
            return
        with open(self.filename, "ab") as file:
            file.write(self.buffer)
        logger.info(f"Successfully wrote {length} bytes to {self.filename}")
        self.buffer = b""

    async def send(self):
        ticker = itertools.cycle(range(WRITE_WAIT_LOOPS))
        try:
            while True:
                msg = await self.queue.get()
                if not msg:
                    logger.info(f"Empty message received.  Breaking")
                    break
                length = len(msg)
                lengthb = length.to_bytes(2, byteorder="big")
                self.buffer += lengthb + msg
                if not next(ticker):
                    self.write_buffer()
        finally:
            logger.info(f"File write loop exited.  Writing the rest of the buffer")
            self.write_buffer()
