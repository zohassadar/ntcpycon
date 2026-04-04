import asyncio
import itertools
import json
import logging
import re
import time

import ntcpycon.abstract
import ntcpycon.nestrisocr
import ntcpycon.binaryframe

Receiver = ntcpycon.abstract.Receiver
BinaryFrame3 = ntcpycon.binaryframe.BinaryFrame3

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

EXPECTED_MAX = 1000

INFO_CYCLE = 1500

IDLE_MAX = 0.25


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

PIECE_TO_VALUE = {
    "T": 0,
    "J": 1,
    "Z": 2,
    "O": 3,
    "S": 4,
    "L": 5,
    "I": 6,
}


class NOCRPayload:
    def __init__(self, payload: bytes):
        self.original = payload
        self.payload = {}
        try:
            self.payload = json.loads(payload.decode("utf-8"))
        except Exception as e:
            logger.error(f"Exception trying to decode: {type(e)}: {e!s}")
            logger.error(f"{payload!s}")
        self._gameid: str | None = self.payload.get("gameid")

        self.gameid: int = (
            int(self._gameid) & (2**16 - 1)
            if self._gameid is not None
            else 2**16 - 1
        )

        self._preview: str | None = self.payload.get("preview")
        self.preview: int = (
            2**3 - 1 if self._preview is None else PIECE_TO_VALUE[self._preview]
        )

        self._lines: str | None = self.payload.get("lines")
        self._level: str | None = self.payload.get("level")
        self._score: str | None = self.payload.get("score")
        self._field: str | None = self.payload.get("field")
        self._time: float | None = self.payload.get("time")
        self._T: str | None = self.payload.get("T")
        self._J: str | None = self.payload.get("J")
        self._Z: str | None = self.payload.get("Z")
        self._O: str | None = self.payload.get("O")
        self._S: str | None = self.payload.get("S")
        self._L: str | None = self.payload.get("L")
        self._I: str | None = self.payload.get("I")

    @property
    def time(self) -> int:
        max = 0xF_FF_FF_FF
        result = max
        if self._time is not None:
            result = (int(self._time * 1000)) & max
        elif self.time is not None:  # lol what?
            logger.debug(f"Unexpected Time Value: {self.time=}")
        return result

    @property
    def stats(self) -> dict[str, int]:
        results = {}
        max = 0xFF
        for stat in ["_T", "_J", "_Z", "_O", "_S", "_L", "_I"]:
            result = max
            value = getattr(self, stat)
            if value is not None and value.isdigit():
                result = int(value) & max
            elif value is not None:
                logger.debug(f"Unexpected Piece Stat Value: {stat=} {value=}")
            results[stat.replace("_", "")] = result
        return results

    @property
    def score(self) -> int:
        score = self._score
        result = max = 0x1F_FF_FF
        # https://github.com/timotheeg/nestrischamps/blob/861f8222c023f3e613b02012c8ad6a4fb68ec1a3/public/js/BinaryFrame.js#L225
        if isinstance(score, str) and re.search(r"^[A-F]", score):
            score = score.replace("A", "10")
            score = score.replace("B", "11")
            score = score.replace("C", "12")
            score = score.replace("D", "13")
            score = score.replace("E", "14")
            score = score.replace("F", "15")
        if score is not None and score.isdigit():
            result = int(score) & max
        elif score is not None:
            logger.debug(f"Unexpected Score Value: {score=}")
        return result

    @property
    def level(self) -> int:
        level = self._level
        result = max = 0b11_1111
        if level is not None and level.isdigit():
            result = int(level) & max
        elif level is not None:
            logger.debug(f"Unexpected Level Value: {level=}")
        return result

    @property
    def lines(self) -> int:
        lines = self._lines
        result = max = 0b1_1111_1111
        if lines and lines.isdigit():
            result = int(lines) & max
        elif lines is not None:
            logger.error(f"Unexpected Lines Value: {lines=}")
        return result

    @property
    def field_bytes(self) -> bytearray:
        # "3021" -> 0b11_00_10_01
        result = bytearray(50)
        if not isinstance(self._field, str):
            return result
        if not len(self._field) == 200:
            print("error.   not 200 bytes")
            return result
        for idx, chunk in enumerate(
            self._field[i : i + 4] for i in range(0, len(self._field), 4)
        ):
            b1 = int(chunk[0]) << 6
            b2 = int(chunk[1]) << 4
            b3 = int(chunk[2]) << 2
            b4 = int(chunk[3])
            result[idx] = b1 | b2 | b3 | b4
        return result



class NESTrisOCRServer(Receiver):
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
