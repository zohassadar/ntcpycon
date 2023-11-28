import json
import logging
import re

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
