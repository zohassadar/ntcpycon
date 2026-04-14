from __future__ import annotations

import pathlib
import shutil

__version__ = "0.1.0"

CONTROL_PORT = 9999
NTC_ROOMS = "rooms.yml"
GYM_PATH = pathlib.Path.cwd() / "TetrisGYM"
BUILD_SCRIPT = GYM_PATH / "build.js"
DEFAULT_BUILD_ARGS = ["-e"]
NODE = shutil.which("node")
CMD_SEND_SEED = 0x44
CMD_SEND_INPUT = 0x45


class Payload:
    # 200 + 4 + 4 + 1 + 4 pfield score lines level next
    SIZE = 210
    COUNT = 2
    playfield = slice(200)
    score = slice(200, 204)
    lines = slice(204, 208)
    level = 209
    next_ = 208
