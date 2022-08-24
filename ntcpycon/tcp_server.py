import asyncio
import logging
import ntcpycon.abstract
import ntcpycon.binaryframe

BinaryFrame = ntcpycon.binaryframe.BinaryFrame
Receiver = ntcpycon.abstract.Receiver

logger = logging.getLogger()
logger.addHandler(logging.NullHandler())

EXPECTED_MAX = 1000


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
        logger.info("Reading has begun")
        while True:
            if self.stopped:
                break
            try:
                payload_lengthb = await client_reader.read(4)
                if not payload_lengthb:
                    await asyncio.sleep(0.1)
                    continue
                # https://github.com/alex-ong/NESTrisOCR/blob/488beeb30e596ccd0548152e241e1c6f772e717b/nestris_ocr/network/tcp_client.py#L56
                payload_length = int.from_bytes(payload_lengthb, byteorder="little")
                if payload_length > EXPECTED_MAX:
                    logger.error(
                        f"Payload length of {payload_length} possibly incorrect.  Flushing buffer",
                    )
                    # Sometimes this reads from the middle of a stream and the length shows up as a huge number
                    # If this happens then whatever is in the buffer is thrown away
                    await client_reader.read()
                    continue
                payload = await client_reader.read(payload_length)
                logger.debug(f"Received {len(payload)} bytes")

                frame = BinaryFrame(payload)
                if not frame.binary_frame:
                    logger.info(f"Empty binary frame received")
                    continue
                for queue in self.queues:
                    await queue.put(frame.binary_frame)

            except Exception as exc:
                logger.error(f"{type(exc).__name__}: {exc!s}")
                break
