from __future__ import annotations

import curses
import socket
import time

from ntcpycon import CONTROL_PORT
from ntcpycon import Payload
from ntcpycon.client import encode_data
from ntcpycon.gymmem import ORIENTATION_TO_ID

PIECES = "TJZOSLI-"


def draw_playfield_row(
    stdscr: curses._CursesWindow,
    playfield: bytes,
    row: int,
    row_offset: int,
    col_offset: int,
):
    stdscr.addstr(
        row + row_offset,
        col_offset,
        "".join("X" if playfield[row * 10 + x] != 0xEF else "." for x in range(10)),
    )


def compare_row(playfield: bytes, last_playfield: bytes | bytearray, row: int):
    for x in range(10):
        idx = row * 10 + x
        if playfield[idx] != last_playfield[idx]:
            return False
    return True


def c_main(stdscr: curses._CursesWindow) -> int:
    last_chunks = bytearray(Payload.SIZE * Payload.COUNT)
    ROW_OFFSET = 1
    COL_OFFSET = 5
    GAP = 18

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect(("localhost", CONTROL_PORT))
        init = encode_data(dict(cmd="game_stream"))
        s.sendall(init)
        curses.init_pair(
            1,
            curses.COLOR_CYAN,
            curses.COLOR_BLUE,
        )
        while True:
            s.sendall(b"a")
            chunks = s.recv(Payload.SIZE * Payload.COUNT)
            for idx in range(Payload.COUNT):
                span = slice(
                    idx * Payload.SIZE,
                    idx * Payload.SIZE + Payload.SIZE,
                )
                if not len(chunk := chunks[span]) == Payload.SIZE:
                    continue
                for row in range(20):
                    if not compare_row(
                        chunk[Payload.playfield],
                        last_chunks[span],
                        row,
                    ):
                        draw_playfield_row(
                            stdscr,
                            chunk,
                            row,
                            ROW_OFFSET,
                            idx * GAP + COL_OFFSET,
                        )
                score = int.from_bytes(chunk[Payload.score], byteorder="little")
                lines = int.from_bytes(chunk[Payload.lines], byteorder="little")
                level = chunk[Payload.level]
                next_ = chunk[Payload.next_]
                next_ = PIECES[ORIENTATION_TO_ID[next_]]
                stdscr.addstr(
                    20 + ROW_OFFSET,
                    idx * GAP + COL_OFFSET,
                    f"Next {next_:<2}",
                )
                stdscr.addstr(
                    21 + ROW_OFFSET,
                    idx * GAP + COL_OFFSET,
                    f"Level {level:<3}",
                )
                stdscr.addstr(
                    22 + ROW_OFFSET,
                    idx * GAP + COL_OFFSET,
                    f"Lines {lines:<4}",
                )
                stdscr.addstr(
                    23 + ROW_OFFSET,
                    idx * GAP + COL_OFFSET,
                    f"Score {score:<7}",
                )
                last_chunks[span] = chunk
            stdscr.refresh()
    return 0


def main() -> int:
    return curses.wrapper(c_main)


if __name__ == "__main__":
    raise SystemExit(main())
