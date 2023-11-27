from __future__ import annotations

import dataclasses
import logging
import time
import typing

from collections import defaultdict

if typing.TYPE_CHECKING:
    from .edlink import ED2NTCFrame


logger = logging.getLogger(__name__)


"""
this is an idea for later:

MESSAGE_HEADER = 0xA55A
MESSAGE_FOOTER = 0xFFFF ^ MESSAGE_HEADER

STATE_UPDATE = 0xD0
FIELD_UPDATE = 0xD1

data:

2   header
2   frame counter (id)
1   playstate
1   frame type
32  data blob
24  future
2   trailer xor header = 0xFFFF
64 

field:

2   header
2   frame counter (id)
1   playstate
1   frame type
1   vramRow
40  playfield
15  future
2   trailer xor header = 0xFFFF
64 


to_game:

2 header
1 frames received since last acknowledgement
11 future
2 trailer xor header = 0xFFFF
16

"""

RAM_TO_NTC_TILES = defaultdict(lambda: 1)
RAM_TO_NTC_TILES[0x7B] = 1
RAM_TO_NTC_TILES[0x7C] = 3
RAM_TO_NTC_TILES[0x7D] = 2
RAM_TO_NTC_TILES[0xEF] = 0


BLANK_TILE = 0xEF

ORIENTATION_TO_ID = [
    0,
    0,
    0,
    0,
    1,
    1,
    1,
    1,
    2,
    2,
    3,
    4,
    4,
    5,
    5,
    5,
    5,
    6,
    6,
    7,
]

PIECE_ORIENTATION_TO_TILE_ID = [
    0x7B,
    0x7B,
    0x7B,
    0x7B,
    0x7D,
    0x7D,
    0x7D,
    0x7D,
    0x7C,
    0x7C,
    0x7B,
    0x7D,
    0x7D,
    0x7C,
    0x7C,
    0x7C,
    0x7C,
    0x7B,
    0x7B,
]


ORIENTATION_TABLE = [
    [(-1, 0), (0, 0), (1, 0), (0, -1)],  # T up
    [(0, -1), (0, 0), (1, 0), (0, 1)],  # T right
    [(-1, 0), (0, 0), (1, 0), (0, 1)],  # T down (spawn)
    [(0, -1), (-1, 0), (0, 0), (0, 1)],  # T left
    [(0, -1), (0, 0), (-1, 1), (0, 1)],  # J left
    [(-1, -1), (-1, 0), (0, 0), (1, 0)],  # J up
    [(0, -1), (1, -1), (0, 0), (0, 1)],  # J right
    [(-1, 0), (0, 0), (1, 0), (1, 1)],  # J down (spawn)
    [(-1, 0), (0, 0), (0, 1), (1, 1)],  # Z horizontal (spawn)
    [(1, -1), (0, 0), (1, 0), (0, 1)],  # Z vertical
    [(-1, 0), (0, 0), (-1, 1), (0, 1)],  # O (spawn)
    [(0, 0), (1, 0), (-1, 1), (0, 1)],  # S horizontal (spawn)
    [(0, -1), (0, 0), (1, 0), (1, 1)],  # S vertical
    [(0, -1), (0, 0), (0, 1), (1, 1)],  # L right
    [(-1, 0), (0, 0), (1, 0), (-1, 1)],  # L down (spawn)
    [(-1, -1), (0, -1), (0, 0), (0, 1)],  # L left
    [(1, -1), (-1, 0), (0, 0), (1, 0)],  # L up
    [(0, -2), (0, -1), (0, 0), (0, 1)],  # I vertical
    [(-2, 0), (-1, 0), (0, 0), (1, 0)],  # I horizontal (spawn)
]


@dataclasses.dataclass
class GymMemory:
    # directly from memory
    game_mode: int = 0
    playstate: int = 0
    vram_row: int = 0  # for later
    row_y: int = 0
    next_piece: int = 0
    current_piece: int = 0
    tetrimino_x: int = 0
    tetrimino_y: int = 0
    autorepeat_x: int = 0
    frame_counter_lo: int = 0
    frame_counter_hi: int = 0
    lines_lo: int = 0
    lines_hi: int = 0
    score0: int = 0
    score1: int = 0
    score2: int = 0
    score3: int = 0
    completed_row0: int = 0
    completed_row1: int = 0
    completed_row2: int = 0
    completed_row3: int = 0
    stats_t_lo: int = 0
    stats_t_hi: int = 0
    stats_j_lo: int = 0
    stats_j_hi: int = 0
    stats_z_lo: int = 0
    stats_z_hi: int = 0
    stats_o_lo: int = 0
    stats_o_hi: int = 0
    stats_s_lo: int = 0
    stats_s_hi: int = 0
    stats_l_lo: int = 0
    stats_l_hi: int = 0
    stats_i_lo: int = 0
    stats_i_hi: int = 0

    # holds playfield that gets presented
    _playfield: bytearray = dataclasses.field(default_factory=lambda:bytearray([BLANK_TILE] * 200))

    # holds playfield that is updated from frame
    _playfield_buffer: bytearray = dataclasses.field(
        default_factory=lambda: bytearray([BLANK_TILE] * 200)
    )

    _previous_state: dict = dataclasses.field(default_factory=dict)

    # derived:
    time: int = dataclasses.field(default_factory=lambda: int(time.time() * 1000))
    game_id: int = 0
    spawn_autorepeat_x: int = 0

    def _general_update_start(self):
        self._previous_state = {
            k: v for k, v in dataclasses.asdict(self).items() if not k.startswith("_")
        }

    def _general_update_finish(self):

        if self.playstate == 8:
            self.spawn_autorepeat_x = self.autorepeat_x
        
        if self.game_mode == 4 and self._previous_state['game_mode'] != 4:
            # This is broken logic that needs to be fixed
            self._playfield[:] = [BLANK_TILE] * 200
            self.game_id += 1

        # update field according to playstate
        if self.playstate in (1, 8):
            self._playfield[:] = self._playfield_buffer
            self.overlay_piece()

        elif self.playstate in (2, 5, 6, 7):
            self._playfield[:] = self._playfield_buffer
            self.overlay_piece()

        elif self.playstate == 4:
            self.overlay_lineclear()

        elif self.playstate in (0, 3, 10):
            ...

        else:
            raise RuntimeError(f"Unexpected playstate {self.playstate}")

    def update_from_edlink(self, edframe: ED2NTCFrame):
        self._general_update_start()

        self.game_mode = edframe.game_mode
        self.playstate = edframe.play_state
        self.row_y = edframe.row_y
        self.next_piece = edframe.next_piece
        self.current_piece = edframe.current_piece
        self.tetrimino_x = edframe.tetrimino_x
        self.tetrimino_y = edframe.tetrimino_y
        self.autorepeat_x = edframe.autorepeat_x

        self.frame_counter_hi = edframe.frame_counter1
        self.frame_counter_lo = edframe.frame_counter0

        self.lines_hi = edframe.lines1
        self.lines_lo = edframe.lines0

        self.level = edframe.level

        self.score0 = edframe.score0
        self.score1 = edframe.score1
        self.score2 = edframe.score2
        self.score3 = edframe.score3

        self.completed_row0 = edframe.completed_row0
        self.completed_row1 = edframe.completed_row1
        self.completed_row2 = edframe.completed_row2
        self.completed_row3 = edframe.completed_row3

        self.stats_t_lo = edframe.stats[0]
        self.stats_t_hi = edframe.stats[1]
        self.stats_j_lo = edframe.stats[2]
        self.stats_j_hi = edframe.stats[3]
        self.stats_z_lo = edframe.stats[4]
        self.stats_z_hi = edframe.stats[5]
        self.stats_o_lo = edframe.stats[6]
        self.stats_o_hi = edframe.stats[7]
        self.stats_s_lo = edframe.stats[8]
        self.stats_s_hi = edframe.stats[9]
        self.stats_l_lo = edframe.stats[10]
        self.stats_l_hi = edframe.stats[11]
        self.stats_i_lo = edframe.stats[12]
        self.stats_i_hi = edframe.stats[13]

        self._playfield_buffer[:] = edframe.playfield

        self._general_update_finish()

    @staticmethod
    def _hybrid_bcd_convert(hi: int, lo: int) -> int:
        return (hi * 100) + ((lo >> 4) * 10) + (lo & 0xF)

    @property
    def current_piece_id(self):
        return ORIENTATION_TO_ID[self.current_piece]

    @property
    def next_piece_id(self):
        return ORIENTATION_TO_ID[self.next_piece]

    @property
    def frame_counter(self) -> int:
        return self.frame_counter_hi << 8 | self.frame_counter_lo

    @property
    def lines(self) -> int:
        return self._hybrid_bcd_convert(self.lines_hi, self.lines_lo)

    @property
    def score(self) -> int:
        return self.score3 << 24 | self.score2 << 16 | self.score1 << 8 | self.score0

    @property
    def completed_rows(self) -> bytearray:
        return bytearray(
            [
                self.completed_row0,
                self.completed_row1,
                self.completed_row2,
                self.completed_row3,
            ]
        )

    @property
    def stats_t(self) -> int:
        return self._hybrid_bcd_convert(self.stats_t_hi, self.stats_t_lo)

    @property
    def stats_j(self) -> int:
        return self._hybrid_bcd_convert(self.stats_j_hi, self.stats_j_lo)

    @property
    def stats_z(self) -> int:
        return self._hybrid_bcd_convert(self.stats_z_hi, self.stats_z_lo)

    @property
    def stats_o(self) -> int:
        return self._hybrid_bcd_convert(self.stats_o_hi, self.stats_o_lo)

    @property
    def stats_s(self) -> int:
        return self._hybrid_bcd_convert(self.stats_s_hi, self.stats_s_lo)

    @property
    def stats_l(self) -> int:
        return self._hybrid_bcd_convert(self.stats_l_hi, self.stats_l_lo)

    @property
    def stats_i(self) -> int:
        return self._hybrid_bcd_convert(self.stats_i_hi, self.stats_i_lo)

    def overlay_piece(self):
        if self.current_piece > 0x12:
            logger.error(
                f"overlay_piece called with invalid current_piece id: {self.current_piece}"
            )
            return
        for x_offset, y_offset in ORIENTATION_TABLE[self.current_piece]:
            index = (self.tetrimino_y + y_offset) * 10 + self.tetrimino_x + x_offset
            if index >= 0 and index < 200:
                self._playfield[index] = PIECE_ORIENTATION_TO_TILE_ID[
                    self.current_piece
                ]

    def overlay_lineclear(self):
        ranges_by_row_y = {
            0: (range(4, 5), range(5, 6)),
            1: (range(3, 5), range(5, 7)),
            2: (range(2, 5), range(5, 8)),
            3: (range(1, 5), range(5, 9)),
            4: (range(0, 5), range(5, 10)),
        }

        if self.frame_counter & 3:
            return

        if self.row_y > 4:
            return

        for row in self.completed_rows:
            if not row:
                continue
            offset = row * 10
            for blank_range in ranges_by_row_y[self.row_y]:
                for blank in blank_range:
                    self._playfield[offset + blank] = BLANK_TILE

    @property
    def compressed(self) -> bytearray:
        _compressed = bytearray(50)
        for i in range(50):
            _compressed[i] = (
                RAM_TO_NTC_TILES[self._playfield[i * 4]] << 6
                | RAM_TO_NTC_TILES[self._playfield[i * 4 + 1]] << 4
                | RAM_TO_NTC_TILES[self._playfield[i * 4 + 2]] << 2
                | RAM_TO_NTC_TILES[self._playfield[i * 4 + 3]]
            )
        return _compressed
