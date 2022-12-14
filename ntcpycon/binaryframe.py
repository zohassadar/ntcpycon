import functools
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


def decode_payload(payload: bytes) -> dict:
    result = {}
    try:
        result = json.loads(payload.decode("utf-8"))
    except Exception as e:
        logger.error(f"Exception trying to decode: {type(e)}: {e!s}")
        logger.error(f"{payload!s}")
    finally:
        return result


class BinaryFrame:
    VERSION = 1
    GAME_TYPE = 1
    PLAYER_ID = 0
    FIRST_BYTE = (VERSION << 5 | GAME_TYPE << 3 | PLAYER_ID).to_bytes(
        1,
        byteorder="big",
    )

    def __init__(self, payload: bytes):
        self.binary_frame = b""
        self.original = payload
        self.payload = decode_payload(payload)
        if not self.payload:
            return
        self.lines = self.payload.get("lines")
        self.level = self.payload.get("level")
        self.score = self.payload.get("score")
        self.field = self.payload.get("field")
        self.preview = self.payload.get("preview")
        self.gameid = self.payload.get("gameid")
        self.time = self.payload.get("time")
        self.T = self.payload.get("T")
        self.J = self.payload.get("J")
        self.Z = self.payload.get("Z")
        self.O = self.payload.get("O")
        self.S = self.payload.get("S")
        self.L = self.payload.get("L")
        self.I = self.payload.get("I")

        # Convert everything to a number that works with the binary structure
        try:
            self.normalize_score()
            self.normalize_level()
            self.normalize_lines()
            self.normalize_time()
            self.normalize_piece_stats()
            self.set_binary_frame()
        except Exception as e:
            logger.error(f"Exception normalizing {type(e)}: {e!s}")
        logger.debug(
            f"Frame: {self.lines=} {self.level=} {self.score=} {self.preview=} {self.time=} {self.T=} {self.J=} {self.Z=} {self.O=} {self.S=} {self.L=} {self.I=}",
        )

    def normalize_time(self):
        max = 0xF_FF_FF_FF
        if self.time is not None:
            self.time = int(self.time * 1000) & max
        elif self.time is not None:
            logger.debug(f"Unexpected Time Value: {self.time=}")
            self.time = max
        else:
            self.time = max

    def normalize_piece_stats(self):
        max = 0xFF
        for stat in ["T", "J", "Z", "O", "S", "L", "I"]:
            value = getattr(self, stat)
            if value is not None and value.isdigit():
                setattr(self, stat, int(value) & max)
            elif value is not None:
                logger.debug(f"Unexpected Piece Stat Value: {stat=} {value=}")
                setattr(self, stat, max)
            else:
                setattr(self, stat, max)

    def normalize_score(self):
        score = self.score
        max = 0x1F_FF_FF
        # https://github.com/timotheeg/nestrischamps/blob/861f8222c023f3e613b02012c8ad6a4fb68ec1a3/public/js/BinaryFrame.js#L225
        if score and re.search(r"^[A-F]", score):
            score = score.replace("A", "10")
            score = score.replace("B", "11")
            score = score.replace("C", "12")
            score = score.replace("D", "13")
            score = score.replace("E", "14")
            score = score.replace("F", "15")
        if score is not None and score.isdigit():
            self.score = int(score) & max
        elif score is not None:
            logger.debug(f"Unexpected Score Value: {score=}")
            self.score = max
        else:
            self.score = max

    def normalize_level(self):
        level = self.level
        max = 0b11_1111
        if level is not None and level.isdigit():
            self.level = int(level) & max
        elif level is not None:
            logger.debug(f"Unexpected Level Value: {level=}")
            self.level = max
        else:
            self.level = max

    def normalize_lines(self):
        lines = self.lines
        max = 0b1_1111_1111
        if lines and lines.isdigit():
            self.lines = int(lines) & max
        elif lines is not None:
            logger.error(f"Unexpected Lines Value: {lines=}")
            self.lines = max
        else:
            self.lines = max

    @functools.cached_property
    def field_bytes(self):
        # "3021" -> 0b11_00_10_01
        result = []
        if not len(self.field) == 200:
            print("error.   not 200 bytes")
            return bytes(50)
        for chunk in (self.field[i : i + 4] for i in range(0, len(self.field), 4)):
            b1 = int(chunk[0]) << 6
            b2 = int(chunk[1]) << 4
            b3 = int(chunk[2]) << 2
            b4 = int(chunk[3])
            result.append(b1 | b2 | b3 | b4)
        return bytes(result)

    def set_binary_frame(self):
        #         "001", -- version
        #         "01", -- game type (classic)
        #         "000", -- player number (always 0 for client)
        result = self.FIRST_BYTE

        #         toBits(gameNo, 16), -- game
        game_no = 0 if self.gameid is None else self.gameid
        result += game_no.to_bytes(2, byteorder="big")

        #         toBits(ms, 28), -- milliseconds
        msecs = self.time << 36

        #         toBits(score, 21), -- score
        score = self.score << 15
        #         toBits(lines, 9), -- lines
        lines = self.lines << 6
        #         toBits(level, 6), -- level
        level = self.level

        next_eight = msecs | score | lines | level
        result += next_eight.to_bytes(8, byteorder="big")

        #         "11111", -- DAS stuff
        das_stuff = 0b11111 << 3

        #         toBits(preview, 3), -- preview
        preview = PIECE_TO_VALUE.get(self.preview, 7)

        result += (das_stuff | preview).to_bytes(1, byteorder="big")

        #         "11111", -- DAS stuff
        #         "111", -- DAS stuff
        result += (0b11111_111).to_bytes(1, byteorder="big")

        #         toBits(statistics[1], 8), -- piece counts
        #         toBits(statistics[2], 8),
        #         toBits(statistics[3], 8),
        #         toBits(statistics[4], 8),
        #         toBits(statistics[5], 8),
        #         toBits(statistics[6], 8),
        #         toBits(statistics[7], 8),

        for piece in PIECE_TO_VALUE.keys():
            result += getattr(self, piece).to_bytes(1, byteorder="big")

        # pad with 7 null values for now
        # result += (0xFF).to_bytes(1, byteorder="big") * 7

        result += self.field_bytes

        # Empty byte trailer
        result += bytes(1)

        self.binary_frame = result
