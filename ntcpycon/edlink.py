from __future__ import annotations
import asyncio
import logging
import sys
import time

import edlinkn8

from ntcpycon.abstract import Receiver
from ntcpycon.gymmem import GymMemory
from ntcpycon.binaryframe import BinaryFrame3

logger = logging.getLogger(__name__)

IDLE_MAX = 0.25

CMD_SEND_STATS = 0x42


class ED2NTCCompactFrame:
    def __init__(self, frame: bytes):
        self.row_y = 0
        self.completed_row0 = 0
        self.completed_row1 = 0
        self.completed_row2 = 0
        self.completed_row3 = 0
        self.lines0 = 0
        self.lines1 = 0
        self.level = 0
        self.score0 = 0
        self.score1 = 0
        self.score2 = 0
        self.score3 = 0
        self.next_piece = 0
        self.current_piece = 0
        self.tetrimino_x = 0
        self.tetrimino_y = 0
        self.autorepeat_x = 0
        self.vram_row = 0
        self.padding = bytearray()
        self.stats = bytearray(14)
        self.playfield_chunk = bytearray([0xEF] * 40)

        # header 2
        self.header = frame[0:2]
        if len(frame) < 2:
            print(f"{self.header=}")
            self.invalid = True
            return

        # frameCounter 2
        self.frame_counter0 = frame[2]
        self.frame_counter1 = frame[3]

        # gameMode
        self.gamemode = frame[4]

        # playState 1
        self.playstate = frame[5]

        # frame type 1
        self.frame_type = frame[6]

        if not self.frame_type:
            # ; gameMode 1

            # ; rowY 1
            self.row_y = frame[7]
            # ; completedRow 4
            self.completed_row0 = frame[8]
            self.completed_row1 = frame[9]
            self.completed_row2 = frame[10]
            self.completed_row3 = frame[11]
            # ; lines 2 (bcd)
            self.lines0 = frame[12]
            self.lines1 = frame[13]
            # ; levelNumber 1
            self.level = frame[14]
            # ; binScore 4
            self.score0 = frame[15]
            self.score1 = frame[16]
            self.score2 = frame[17]
            self.score3 = frame[18]
            # ; nextPiece 1
            self.next_piece = frame[19]
            # ; currentPiece 1
            self.current_piece = frame[20]
            # ; tetriminoX 1 Needed to determine where piece is in playfield
            self.tetrimino_x = frame[21]
            # ; tetriminoY 1 same
            self.tetrimino_y = frame[22]

            # ; autoRepeatX 1 current DAS
            self.autorepeat_x = frame[23]
            # ; statsByType 14
            self.stats[:] = frame[24:38]

            # padding 22
            self.padding = frame[38:62]
        else:
            self.vram_row = frame[7]
            self.playfield_chunk[:] = frame[8:48]
            self.padding = frame[48:62]

        self.footer = frame[62:64]

        header = int.from_bytes(self.header, "little")
        footer = int.from_bytes(self.footer, "little")
        self.invalid = False
        if header ^ footer != 0xFFFF:
            logger.warning(f"{header:04x} ^ {footer:04x} != 0xFFFF")
            self.invalid = True


class CompactOptions:
    REQUEST = 0x43
    SIZE = 0x40


class EDLink(Receiver):
    def __init__(
        self,
        queues: list[asyncio.Queue],
        launch: bool = False,
        index: int = 0,
    ):
        self.queues = queues
        self.launch = launch
        self.everdrive = edlinkn8.Everdrive(index=index)
        if launch:
            # todo:  clean this
            gym = edlinkn8.NesRom.from_file("TetrisGYM/ed2ntc.nes")
            try:
                self.everdrive.load_game(gym)
            except Exception as exc:
                print(f"Unable to load game: {exc}", file=sys.stderr)
                sys.exit(1)

    def __repr__(self):
        queues = self.queues
        everdrive = self.everdrive
        return f"{type(self).__name__}({queues=}, {everdrive=})"

    async def receive(self):
        loop = asyncio.get_running_loop()
        _last_fc = None
        _last_frame_sent = ()
        _last_frame_sent_when = time.time()
        gym = GymMemory()

        while True:
            await loop.run_in_executor(
                None, self.everdrive.write_fifo, bytearray([CompactOptions.REQUEST])
            )
            frame = await loop.run_in_executor(
                None, self.everdrive.receive_data, CompactOptions.SIZE
            )
            logger.debug(f"Received {len(frame)} bytes from ed")

            # frame drop/error detection
            if len(frame) == CompactOptions.SIZE:
                fc = int.from_bytes(frame[2:4], "little")
                if _last_fc is None:
                    logger.info(f"Discarding first frame: {fc:04X}")
                    _last_fc = fc
                    continue
                _expected = (_last_fc + 1) & 0xFFFF
                if _expected != fc:
                    dropped = fc - _expected
                    if dropped  < 0:
                        logger.warning(f"Duplicate or backward jump {_last_fc} -> {fc}")
                    else:
                        logger.warning(
                            f'dropped {dropped} frame{"s" if dropped>1 else ""}. '
                            f"{_last_fc:04X} -> {fc:04X}"
                        )
                _last_fc = fc
            else:
                logger.warning(f"Invalid frame length: {len(frame)}")

            edframe = ED2NTCCompactFrame(frame)
            if edframe.invalid:
                logger.error(f"Skipping invalid frame")
                continue
            gym.update_from_edlink_compact(edframe)
            bframe = BinaryFrame3.from_gym_memory(gym)

            now = time.time()
            if (bframe.compare_data == _last_frame_sent) and (
                now - _last_frame_sent_when < IDLE_MAX
            ):
                logger.debug(f"Skipping transmit of frame")
                continue
            _last_frame_sent_when = now
            _last_frame_sent = bframe.compare_data
            for queue in self.queues:
                await queue.put(bframe.payload)
