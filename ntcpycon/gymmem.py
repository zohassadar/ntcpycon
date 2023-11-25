import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


"""
this is an idea for later:

MESSAGE_HEADER = 0xA55A
MESSAGE_FOODER = 0xFFFF ^ MESSAGE_HEADER

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





class GymMemory:
    # shared
    game_mode: int
    playstate: int
    vram_row: int # for later
    _playfield: bytearray
    _playfield_buffer: bytearray
    row_y: int
    next_piece: int
    current_piece: int
    tetrimino_x: int
    tetrimino_y: int
    autorepeat_x: int
    frame_counter_hi: int
    frame_counter_lo: int
    lines_hi: int
    lines_lo: int
    score0: int
    score1: int
    score2: int
    score3: int
    completed_row0: bytearray
    completed_row1: bytearray
    completed_row2: bytearray
    completed_row3: bytearray
    stats_t_hi: int
    stats_t_lo: int
    stats_j_hi: int
    stats_j_lo: int
    stats_z_hi: int
    stats_z_lo: int
    stats_o_hi: int
    stats_o_lo: int
    stats_s_hi: int
    stats_s_lo: int
    stats_l_hi: int
    stats_l_lo: int
    stats_i_hi: int
    stats_i_lo: int

    @staticmethod
    def _hybrid_bcd_convert(hi: int, lo: int) -> int:
        return (hi * 100) + ((lo >> 4) * 10) + (lo & 0xF)

    @property
    def frame_counter(self) -> int:
        return self.frame_counter_hi << 8 | self.frame_counter_lo

    @property
    def lines(self) -> int:
        return self._hybrid_bcd_convert(self.lines_hi, self.lines_lo)

    @property
    def score(self) -> int:
        return self.score3 << 24 | self.score2 << 16 | self.score1 << 8 | self.score

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

    def __init__(self):
        self.frame_counter_hi = 0
        self.frame_counter_lo = 0
        self.game_mode = 0
        self.playstate = 0

        self.vram_row = 0
        self.playfield = bytearray(200)
        self.playfield_buffer = bytearray(200)

        self.row_y = 0
        self.completed_row0 = 0
        self.completed_row1 = 0
        self.completed_row2 = 0
        self.completed_row3 = 0
        self.linesHi = 0
        self.linesLo = 0
        self.score0 = 0
        self.score1 = 0
        self.score2 = 0
        self.score3 = 0
        self.next_piece = 0
        self.current_piece = 0
        self.tetrimino_x = 0
        self.tetrimino_y = 0
        self.autorepeat_x = 0
        self.stats_t_hi = 0
        self.stats_t_lo = 0
        self.stats_j_hi = 0
        self.stats_j_lo = 0
        self.stats_z_hi = 0
        self.stats_z_lo = 0
        self.stats_o_hi = 0
        self.stats_o_lo = 0
        self.stats_s_hi = 0
        self.stats_s_lo = 0
        self.stats_l_hi = 0
        self.stats_l_lo = 0
        self.stats_i_hi = 0
        self.stats_i_lo = 0

    def overlay_piece(self):
        if self.current_piece > 0x12:
            logger.error(
                f"overlay_piece called with invalid current_piece id: {self.current_piece}"
            )
            return
        for x_offset, y_offset in ORIENTATION_TABLE[self.current_piece]:
            index = (self.tetrimino_y + y_offset) * 10 + self.tetrimino_x + x_offset
            if index >= 0 and index < 200:
                self.playfield[index] = PIECE_ORIENTATION_TO_TILE_ID[self.current_piece]

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

        for row in self.completed_row:
            if not row:
                continue
            offset = row * 10
            for blank_range in ranges_by_row_y[self.row_y]:
                for blank in blank_range:
                    self.playfield[offset + blank] = BLANK_TILE

    def update_playfield_buffer(self):
        ...

    def update_playfield(self):
        if self.playstate in (1, 8):
            self.overlay_piece()
        elif self.playstate in (2, 5, 6, 7) and self.vram_row == 0x20:
            self.playfield[:] = self.playfield_buffer
        elif self.playstate == 4:
            playfield = self.overlay_lineclear()
        elif self.playstate in (0, 10):
            ...
        else:
            raise RuntimeError(f"Unexpected playstate {self.playstate}")
        
    @property
    def compressed(self) -> bytearray:
        _compressed = bytearray(50)
        for i in range(50):
            _compressed[i] = (
                (self.playfield[i * 4] & 3) << 6
                | (self.playfield[i * 4 + 1] & 3) << 4
                | (self.playfield[i * 4 + 2] & 3) << 2
                | (self.playfield[i * 4 + 3] & 3)
            )
        return _compressed