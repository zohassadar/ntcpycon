from __future__ import annotations

import curses
import socket
import time

PLAYFIELD = bytes(200)
PAYLOAD_SIZE = 200
PAYLOADS = 4


from ntcpycon.ed2ntc import CONTROL_PORT
from ntcpycon.ed2ntc import PAYLOAD_SIZE
from ntcpycon.ed2ntc import PAYLOADS
from ntcpycon.ed2ntc import encode_data


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
    last_chunks = bytearray(PAYLOAD_SIZE * PAYLOADS)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect(("localhost", CONTROL_PORT))
        init = encode_data(dict(cmd="game_stream"))
        s.sendall(init)
        curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLUE)
        line = 1
        while True:
            # render cycle

            # get input
            # if char > 0:
            #     stdscr.addstr(1, 0, f"{str(char):<30}")
            #     stdscr.addstr(2, 0, f"{chr(char)!r:<30}")
            #
            # line += 1

            s.sendall(b"a")
            chunks = s.recv(PAYLOAD_SIZE * PAYLOADS)
            for idx in range(PAYLOADS):
                span = slice(idx * PAYLOAD_SIZE, idx * PAYLOAD_SIZE + PAYLOAD_SIZE)
                if not len(chunk := chunks[span]) == PAYLOAD_SIZE:
                    continue
                for row in range(20):
                    if not compare_row(chunk, last_chunks[span], row):
                        draw_playfield_row(stdscr, chunk, row, 0, idx * 20)
                last_chunks[span] = chunk
            stdscr.refresh()
    return 0


def main() -> int:
    return curses.wrapper(c_main)


if __name__ == "__main__":
    raise SystemExit(main())
