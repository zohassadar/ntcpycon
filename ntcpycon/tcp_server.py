import asyncio
import itertools
import logging

import ntcpycon.abstract
import ntcpycon.binaryframe

BinaryFrame = ntcpycon.binaryframe.BinaryFrame
Receiver = ntcpycon.abstract.Receiver

logger = logging.getLogger()
logger.addHandler(logging.NullHandler())

EXPECTED_MAX = 1000

INFO_CYCLE = 1500


class TCPServer(Receiver):
    def __init__(
        self,
        queues: list[asyncio.Queue],
        port: int = 3338,
    ):
        self.queues = queues
        self.port = port
        self.stopped = False

    def __repr__(self):
        queues = self.queues
        port = self.port
        return f"{type(self).__name__}({queues=}, {port=})"

    async def receive(self):
        tcp_server = await asyncio.start_server(
            self.handler,
            port=self.port,
        )
        await tcp_server.serve_forever()

    async def handler(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ):

        await asyncio.gather(
            self.write_handler(client_writer),
            self.read_handler(client_reader),
        )

    async def write_handler(
        self,
        client_writer: asyncio.StreamWriter,
    ):
        ...

    async def read_handler(
        self,
        client_reader: asyncio.StreamReader,
    ):
        ticker = itertools.cycle(range(INFO_CYCLE))
        frame_count = 0
        while True:
            if not next(ticker):
                logger.info(f"TCP Connection Open: Frame Receive Count: {frame_count}")
            if self.stopped:
                break
            try:
                payload_lengthb = await client_reader.read(4)
                if not payload_lengthb:
                    continue
                # https://github.com/alex-ong/NESTrisOCR/blob/488beeb30e596ccd0548152e241e1c6f772e717b/nestris_ocr/network/tcp_client.py#L56
                payload_length = int.from_bytes(payload_lengthb, byteorder="little")
                if payload_length > EXPECTED_MAX:
                    logger.debug(
                        f"Payload length of {payload_length} possibly incorrect.  Flushing buffer",
                    )
                    # Sometimes this reads from the middle of a stream and the length shows up as a huge number
                    # If this happens then whatever is in the buffer is thrown away
                    while True:
                        flushed = await client_reader.read(EXPECTED_MAX)
                        bytes_flushed = len(flushed)
                        if bytes_flushed < EXPECTED_MAX:
                            break
                        logger.debug(f'Flushed {bytes_flushed} bytes')
                    logger.debug('Carrying on')
                    continue
                payload = await client_reader.read(payload_length)
                logger.debug(f"Received {len(payload)} bytes")

                frame = BinaryFrame(payload)
                if not frame.binary_frame:
                    logger.info(f"Empty binary frame received")
                    continue
                frame_count += 1
                for queue in self.queues:
                    await queue.put(frame.binary_frame)

            except Exception as exc:
                logger.error(f"{type(exc).__name__}: {exc!s}")
                break
