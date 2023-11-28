from __future__ import annotations
import asyncio
import logging
import sys
import time

import edlinkn8
import ntcpycon.abstract
import ntcpycon.gymmem
import ntcpycon.binaryframe

Receiver = ntcpycon.abstract.Receiver
GymMemory = ntcpycon.gymmem.GymMemory
BinaryFrame3 = ntcpycon.binaryframe.BinaryFrame3

logger = logging.getLogger(__name__)

IDLE_MAX = .25

CMD_SEND_STATS = 0x42

class ED2NTCCompactFrame:
    def __init__(self, frame: bytes):
        self.game_start_game_state = 0
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
        self.playfield_chunk = bytearray([0xef] * 40)

        # header 2
        self.header = frame[0:2]

        # frameCounter 2 
        self.frame_counter0 = frame[2]
        self.frame_counter1 = frame[3]

        # gameModeState 1
        self.game_mode_state = frame[4]

        # playState 1
        self.playstate = frame[5]
        
        # gameStart 1
        self.game_start = frame[6]

        # gameState
        self.game_state = frame[7]

        # frame type 1
        self.frame_type = frame[8]

        if not self.frame_type:
            # ; gameMode 1

            # ; rowY 1
            self.row_y = frame[9]
            # ; completedRow 4
            self.completed_row0 = frame[10]
            self.completed_row1 = frame[11]
            self.completed_row2 = frame[12]
            self.completed_row3 = frame[13]
            # ; lines 2 (bcd)
            self.lines0 = frame[14]
            self.lines1 = frame[15]
            # ; levelNumber 1
            self.level = frame[16]
            # ; binScore 4
            self.score0 = frame[17]
            self.score1 = frame[18]
            self.score2 = frame[19]
            self.score3 = frame[20]
            # ; nextPiece 1
            self.next_piece = frame[21]
            # ; currentPiece 1
            self.current_piece = frame[22]
            # ; tetriminoX 1 Needed to determine where piece is in playfield
            self.tetrimino_x = frame[23]
            # ; tetriminoY 1 same
            self.tetrimino_y = frame[24]

            # ; autoRepeatX 1 current DAS
            self.autorepeat_x = frame[25]
            # ; statsByType 14
            self.stats[:] = frame[26:40]

            # padding 22
            self.padding = frame[40:62]
        else:
            self.vram_row = frame[9]
            self.playfield_chunk[:] = frame[10:50]
            self.padding = frame[50:62]
        
        self.footer = frame[62:64]

        header = int.from_bytes(self.header, "little")
        footer = int.from_bytes(self.footer, "little")
        self.invalid=False
        if header^footer!=0xFFFF:
            logger.warning(f'{header:04x} ^ {footer:04x} != 0xFFFF')
            self.invalid = True


class ED2NTCFrame:
    def __init__(self, frame: bytes):
        # ; gameMode 1
        self.game_start_game_state = frame[0]
        # ; playState 1
        self.game_mode_state_play_state = frame[1]
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
        self.frame_counter1 = frame[19]
        # ; autoRepeatX 1 current DAS
        self.autorepeat_x = frame[20]
        # ; statsByType 14
        self.stats = frame[21:35]
        # ; playfield 200
        self.playfield = frame[35:235]
        # ; subtotal 235/0xeb

        # ; footer : 2 * $AA
        self.footer = frame[235:]

class CompactOptions:
    REQUEST = 0x43
    SIZE = 0x40
    FC_LOC = slice(2,4)
    FRAME = ED2NTCCompactFrame
    UPDATE = "update_from_edlink_compact"

class Options:
    REQUEST = 0x42
    SIZE = 0xED
    FC_LOC = slice(18,20)
    FRAME = ED2NTCFrame
    UPDATE = "update_from_edlink"

options = CompactOptions

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
        loop = asyncio.get_running_loop()
        _last_frame_counter = 0
        _last_frame_sent = ()
        _last_frame_sent_when = time.time()
        gym = GymMemory()

        while True:
            await loop.run_in_executor(
                None, self.everdrive.write_fifo, bytearray([options.REQUEST])
            )
            frame = await loop.run_in_executor(None, self.everdrive.receive_data, options.SIZE)
            logger.debug(f"Received {len(frame)} bytes from ed")

            # frame drop/error detection
            if len(frame) == options.SIZE:
                fc = int.from_bytes(frame[options.FC_LOC], "little")
                if (_last_fc_nrmlzed := ((_last_frame_counter + 1) & 0xFFFF)) != fc:
                    logger.warning(
                        f'dropped {fc-_last_fc_nrmlzed} frame{"s" if fc-_last_fc_nrmlzed>1 else ""}.  {_last_frame_counter+1} to {fc-1}'
                    )
                _last_frame_counter = fc
            else:
                logger.warning(f"Invalid frame length: {len(frame)}")

            edframe = options.FRAME(frame)
            getattr(gym, options.UPDATE)(edframe)
            bframe = BinaryFrame3.from_gym_memory(gym)

            now = time.time()
            if (bframe.compare_data == _last_frame_sent) and (now - _last_frame_sent_when < IDLE_MAX):
                logger.debug(f"Skipping transmit of frame")
                continue
            _last_frame_sent_when = now
            _last_frame_sent = bframe.compare_data
            for queue in self.queues:
                await queue.put(bframe.payload)
