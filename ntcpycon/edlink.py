from __future__ import annotations

import asyncio
import logging
import sys
import time

import edlinkn8

from ntcpycon.abstract import Receiver
from ntcpycon.adeque import AsyncDeque
from ntcpycon.binaryframe import BinaryFrame3
from ntcpycon.gymmem import GymMemory

logger = logging.getLogger(__name__)

IDLE_MAX = 0.25

CMD_SEND_STATS = 0x42

MAX_MISSED_FRAMES = 5

MAX_ED_RCV = 100
MAX_ED_SEND = 100


class Chunker:
    def __init__(self, frame: bytes):
        self.i = 0
        self.frame = frame

    def one(self) -> int:
        result = self.frame[self.i]
        self.i += 1
        return result

    def span(self, count: int) -> bytes:
        result = self.frame[self.i : self.i + count]
        self.i += count
        return result


class ED2NTCCompactFrame:
    def __init__(self, frame: bytes):
        c = Chunker(frame)

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
        self.header = c.span(2)
        if len(frame) < 2:
            self.invalid = True
            return

        # frameCounter 2
        self.frame_counter0 = c.one()
        self.frame_counter1 = c.one()

        # gameMode
        self.gamemode = c.one()

        # playState 1
        self.playstate = c.one()

        # frame type 1
        self.frame_type = c.one()

        if not self.frame_type:
            # ; gameMode 1

            # ; rowY 1
            self.row_y = c.one()
            # ; completedRow 4
            self.completed_row0 = c.one()
            self.completed_row1 = c.one()
            self.completed_row2 = c.one()
            self.completed_row3 = c.one()
            # ; lines 2 (bcd)
            self.lines0 = c.one()
            self.lines1 = c.one()
            # ; levelNumber 1
            self.level = c.one()
            # ; binScore 4
            self.score0 = c.one()
            self.score1 = c.one()
            self.score2 = c.one()
            self.score3 = c.one()
            # ; nextPiece 1
            self.next_piece = c.one()
            # ; currentPiece 1
            self.current_piece = c.one()
            # ; tetriminoX 1 Needed to determine where piece is in playfield
            self.tetrimino_x = c.one()
            # ; tetriminoY 1 same
            self.tetrimino_y = c.one()

            # ; autoRepeatX 1 current DAS
            self.autorepeat_x = c.one()
            # ; statsByType 14
            self.stats[:] = c.span(14)

            # padding 14
            self.padding = c.span(14)
        else:
            self.vram_row = c.one()
            self.playfield_chunk[:] = c.span(40)
            self.padding = c.span(4)

        self.footer = c.span(2)

        header = int.from_bytes(self.header, "little")
        footer = int.from_bytes(self.footer, "little")
        self.invalid = False
        if header ^ footer != 0xFFFF:
            logger.error(f"{header:04x} ^ {footer:04x} != 0xFFFF")
            self.invalid = True


class CompactOptions:
    REQUEST = 0x43
    SIZE = 0x36


class EDLink(Receiver):
    def __init__(
        self,
        queues: list[asyncio.Queue],
        launch: bool = False,
        index: int | None = None,
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
                None,
                self.everdrive.write_fifo,
                bytearray([CompactOptions.REQUEST]),
            )
            frame = await loop.run_in_executor(
                None,
                self.everdrive.receive_data,
                CompactOptions.SIZE,
            )
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
                    if dropped < 0:
                        logger.warning(f"Duplicate or backward jump {_last_fc} -> {fc}")
                    else:
                        logger.warning(
                            f'dropped {dropped} frame{"s" if dropped>1 else ""}. '
                            f"{_last_fc:04X} -> {fc:04X}",
                        )
                _last_fc = fc
            else:
                logger.warning(f"Invalid frame length: {len(frame)}")

            edframe = ED2NTCCompactFrame(frame)
            if edframe.invalid:
                logger.error("Skipping invalid frame")
                continue
            gym.update_from_edlink_compact(edframe)
            bframe = BinaryFrame3.from_gym_memory(gym)

            now = time.time()
            if (bframe.compare_data == _last_frame_sent) and (
                now - _last_frame_sent_when < IDLE_MAX
            ):
                logger.debug("Skipping transmit of frame")
                continue
            _last_frame_sent_when = now
            _last_frame_sent = bframe.compare_data
            for queue in self.queues:
                await queue.put(bframe.payload)


class NewEDLink:
    def __init__(
        self,
        serial: str,
    ):
        self.everdrive = edlinkn8.Everdrive(serial=serial)
        self.game_data = AsyncDeque(maxlen=MAX_ED_RCV)
        self.game_control = AsyncDeque(maxlen=MAX_ED_SEND)
        self.gym = GymMemory()
        self.bframe = BinaryFrame3()
        self.frames_missed = 0

    async def connect(self):
        self.task = asyncio.create_task(self._connect())
        await self.task

    async def end(self):
        await self.game_control.put(None)
        await self.task
        self.everdrive.port.close()

    async def _connect(self):
        loop = asyncio.get_running_loop()
        _last_fc = None
        _last_frame_sent = ()
        _last_frame_sent_when = time.time()
        _pending_command: list[int] | None = None

        async def _poll_game():
            nonlocal _last_fc
            nonlocal _last_frame_sent
            nonlocal _last_frame_sent_when
            nonlocal _pending_command

            if _pending_command:
                request = bytes(_pending_command)
                logger.info(f"Game control command: {request.hex()!r}")
            else:
                request = bytes([CompactOptions.REQUEST])

            await loop.run_in_executor(
                None,
                self.everdrive.write_fifo,
                request,
            )
            if _pending_command:
                logger.info(f"Skip poll after command: {request.hex()!r}")
                _pending_command = None
                return

            frame = await loop.run_in_executor(
                None,
                self.everdrive.receive_data,
                CompactOptions.SIZE,
            )
            # frame drop/error detection
            if not len(frame) == CompactOptions.SIZE:
                self.frames_missed += 1
                logger.warning(f"Invalid frame length: {len(frame)}")
                return

            self.frames_missed = 0
            fc = int.from_bytes(frame[2:4], "little")
            if _last_fc is None:
                logger.info(f"Discarding first frame: {fc:04X}")
                _last_fc = fc
                return
            _expected = (_last_fc + 1) & 0xFFFF
            if _expected != fc:
                dropped = fc - _expected
                if dropped < 0:
                    logger.warning(f"Duplicate or backward jump {_last_fc} -> {fc}")
                else:
                    logger.warning(
                        f'dropped {dropped} frame{"s" if dropped>1 else ""}. '
                        f"{_last_fc:04X} -> {fc:04X}",
                    )
            _last_fc = fc

            edframe = ED2NTCCompactFrame(frame)
            if edframe.invalid:
                logger.error("Skipping invalid frame")
                return
            self.gym.update_from_edlink_compact(edframe)
            self.bframe.update_from_gym_memory(self.gym)

            now = time.time()
            if (self.bframe.compare_data == _last_frame_sent) and (
                now - _last_frame_sent_when < IDLE_MAX
            ):
                logger.debug("Skipping transmit of frame")
                return
            _last_frame_sent_when = now
            _last_frame_sent = self.bframe.compare_data
            await self.game_data.put(self.bframe.payload)

        while True:
            if self.frames_missed == MAX_MISSED_FRAMES:
                logger.error("Everdrive timeout")
                return
            if self.game_control:
                command = self.game_control.popleft()
                if command is None:
                    logger.info(f"Ending")
                    return
                _pending_command = command
            await _poll_game()
