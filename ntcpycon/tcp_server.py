import asyncio
import itertools
import logging
import time

import ntcpycon.abstract
import ntcpycon.nestrisocr
import ntcpycon.binaryframe

NOCRPayload = ntcpycon.nestrisocr.NOCRPayload
Receiver = ntcpycon.abstract.Receiver
BinaryFrame3 = ntcpycon.binaryframe.BinaryFrame3

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

EXPECTED_MAX = 1000

INFO_CYCLE = 1500

IDLE_MAX = 0.25


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
        _last_frame_sent = ()
        _last_frame_sent_when = time.time()
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
                        logger.debug(f"Flushed {bytes_flushed} bytes")
                    logger.debug("Carrying on")
                    continue
                payload = await client_reader.read(payload_length)
                logger.debug(f"Received {len(payload)} bytes")

                nocrpayload = NOCRPayload(payload)
                bframe = BinaryFrame3.from_nestris_ocr(nocrpayload)
                now = time.time()
                if (bframe.compare_data == _last_frame_sent) and (
                    now - _last_frame_sent_when < IDLE_MAX
                ):
                    logger.debug(f"Skipping transmit of frame")
                    continue
                frame_count += 1
                _last_frame_sent_when = now
                _last_frame_sent = bframe.compare_data
                for queue in self.queues:
                    await queue.put(bframe.payload)

            except Exception as exc:
                logger.error(f"{type(exc).__name__}: {exc!s}")
                break
