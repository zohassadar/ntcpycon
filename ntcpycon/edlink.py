from __future__ import annotations
import asyncio
import logging
import sys

import edlinkn8
import ntcpycon.abstract

Receiver = ntcpycon.abstract.Receiver

logger = logging.getLogger(__name__)

CMD_SEND_STATS = 0x42

class ED2NTCFrame:
    def __init__(self, frame: bytes):
        # ; gameMode 1
        self.game_mode = frame[0]
        # ; playState 1
        self.play_state = frame[1]
        # ; rowY 1
        self.row_y = frame[2]
        # ; completedRow 4
        self.completed_row0 = frame[3]
        self.completed_row1 = frame[4]
        self.completed_row2 = frame[5]
        self.completed_row3 = frame[6]
        # ; lines 2 (bcd)
        self.lines0 = frame[7]
        self.lines1 = frame[8]
        # ; levelNumber 1
        self.level = frame[9]
        # ; binScore 4
        self.score0 = frame[10]
        self.score1 = frame[11]
        self.score2 = frame[12]
        self.score3 = frame[13]
        # ; nextPiece 1
        self.next_piece = frame[14]
        # ; currentPiece 1
        self.current_piece = frame[15]
        # ; tetriminoX 1 Needed to determine where piece is in playfield
        self.tetrimino_x = frame[16]
        # ; tetriminoY 1 same
        self.tetrimino_y = frame[17]
        # ; frameCounter 2 Used for line clearing animation
        self.frame_counter0 = frame[18]
        self.frame_counter0 = frame[19]
        # ; autoRepeatX 1 current DAS
        self.autorepeat_x = frame[20]
        # ; statsByType 14
        self.stats = frame[21:35]
        # ; playfield 200
        self.playfield = frame[35:235]
        # ; subtotal 235/0xeb

        # ; footer : 2 * $AA
        self.footer = frame[235:]


class EDLink(Receiver):
    def __init__(
        self,
        queues: list[asyncio.Queue],
        launch: bool = False,
    ):
        self.queues = queues
        self.launch = launch
        self.everdrive = edlinkn8.Everdrive()
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
        last = 0
        loop = asyncio.get_running_loop()
        while True:
            await loop.run_in_executor(
                None, self.everdrive.write_fifo, bytearray([0x42])
            )
            msg = await loop.run_in_executor(None, self.everdrive.receive_data, 0xED)
            logger.debug(f"Received {len(msg)} bytes from ed")

            # frame drop/error detection
            if len(msg) == 0xED:
                fc = int.from_bytes(msg[18:20], "little")
                if (lastn := ((last + 1) & 0xFFFF)) != fc:
                    logger.warning(
                        f'dropped {fc-lastn} frame{"s" if fc-lastn>1 else ""}.  {last+1} to {fc-1}'
                    )
                last = fc
            else:
                logger.warning(f"Invalid frame length: {len(msg)}")

            for queue in self.queues:
                await queue.put(bytearray(73))
