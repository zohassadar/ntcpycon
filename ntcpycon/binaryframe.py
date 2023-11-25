from __future__ import annotations
import logging
import typing

if typing.TYPE_CHECKING:
    from .nestrisocr import NOCRPayload

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())



class BinaryFrame3:
    VERSION = 3
    GAME_TYPE = 1

    def __init__(self):
        self.playfield = bytearray(50)
        # todo: not all of these are nullable
        self.t = 2**10-1
        self.j = 2**10-1
        self.z = 2**10-1
        self.o = 2**10-1
        self.s = 2**10-1
        self.l = 2**10-1
        self.i = 2**10-1
        self.game_id = 2**16-1
        self.elapsed = 2**28-1
        self.lines = 2**12-1
        self.level = 2**8-1
        self.score = 2**24-1
        self.instant_das = 2**5-1
        self.preview = 2**3-1
        self.cur_piece = 2**3-1
        self.cur_piece_das = 2**5-1

    @classmethod
    def from_nestris_ocr(cls, ocr_payload: NOCRPayload) -> BinaryFrame3:
        result =  cls()
        stats = ocr_payload.stats
        result.t = stats["T"]
        logger.debug(f"{result.t=}")
        result.j = stats["J"]
        logger.debug(f"{result.j=}")
        result.z = stats["Z"]
        logger.debug(f"{result.z=}")
        result.o = stats["O"]
        logger.debug(f"{result.o=}")
        result.s = stats["S"]
        logger.debug(f"{result.s=}")
        result.l = stats["L"]
        logger.debug(f"{result.l=}")
        result.i = stats["I"]
        logger.debug(f"{result.i=}")
        result.elapsed = ocr_payload.time
        logger.debug(f"{result.elapsed=}")
        result.game_id = ocr_payload.gameid
        logger.debug(f"{result.game_id=}")
        result.level = ocr_payload.level
        logger.debug(f"{result.level=}")
        result.lines = ocr_payload.lines
        logger.debug(f"{result.lines=}")
        result.score = ocr_payload.score
        logger.debug(f"{result.score=}")
        result.preview = ocr_payload.preview
        logger.debug(f"{result.preview=}")
        result.playfield = ocr_payload.field_bytes
        logger.debug(f"{result.playfield=}")
        return result

    @property
    def stats(self) -> bytearray:
        _stats = bytearray(9)
        _stats[0] = (self.t & 0b1111111100) >> 2
        _stats[1] = ((self.t & 0b0000000011) << 6) | ((self.j & 0b1111110000) >> 4)
        _stats[2] = ((self.j & 0b0000001111) << 4) | ((self.z & 0b1111000000) >> 6)
        _stats[3] = ((self.z & 0b0000111111) << 2) | ((self.o & 0b1100000000) >> 8)
        _stats[4] = (self.o & 0b0011111111) << 0
        _stats[5] = (self.s & 0b1111111100) >> 2
        _stats[6] = ((self.s & 0b0000000011) << 6) | ((self.l & 0b1111110000) >> 4)
        _stats[7] = ((self.l & 0b0000001111) << 4) | ((self.i & 0b1111000000) >> 6)
        _stats[8] = (self.i & 0b0000111111) << 2
        return _stats


    @property
    def payload(self):
        _payload = bytearray(73)
        logger.debug(len(_payload))
        _payload[0] = ((self.VERSION & 0b111) << 5) | (
            (self.GAME_TYPE & 0b11) << 3
        )

        _payload[1] = (self.game_id & 0xFF00) >> 8
        _payload[2] = (self.game_id & 0x00FF) >> 0

        # ctime - 28 bits
        _payload[3] = (self.elapsed & 0xFF00000) >> 20
        _payload[4] = (self.elapsed & 0x00FF000) >> 12
        _payload[5] = (self.elapsed & 0x0000FF0) >> 4
        _payload[6] = ((self.elapsed & 0x0F) << 4) | ((self.lines & 0xF00) >> 8)

        # lines - 12 bits
        _payload[7] = self.lines & 0xFF

        # level - 8 bits
        _payload[8] = self.level

        # score - 24 bits
        _payload[9] = (self.score & 0xFF0000) >> 16
        _payload[10] = (self.score & 0x00FF00) >> 8
        _payload[11] = self.score & 0x0000FF
        _payload[12] = ((self.instant_das & 0b11111) << 3) | (self.preview & 0b111)
        _payload[13] = ((self.cur_piece_das & 0b11111) << 3) | (self.cur_piece & 0b111)
        _payload[14:23] = self.stats
        _payload[23:] = self.playfield
        return bytes(_payload)


