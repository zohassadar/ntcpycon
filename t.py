import asyncio
import logging
import shutil
import pathlib
from asyncio import subprocess

logger = logging.getLogger(__name__)

NODE = shutil.which("node")
if NODE is None:
    raise RuntimeError("missing node")

PYTHON = shutil.which("python")
if PYTHON is None:
    raise RuntimeError("missing python")

BUILD = pathlib.Path.cwd() / "TetrisGYM" / "build.js"

BUILD_ARGS = ["-e"]


def rom_name(args: list[str]) -> str:
    return f'tetris{"".join(args)}.nes'


async def hello(queue: asyncio.Queue):
    while True:
        job = await queue.get()
        if job is None:
            logger.info("bye")
            break
        print(f"helloing to {job}")
        await asyncio.sleep(1)
        print(f"done helloing to {job}")


q = asyncio.Queue()

async def launch_rom():
    result = await asyncio.create_subprocess_exec(
        NODE,  # type: ignore
        BUILD,
        *BUILD_ARGS,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=BUILD.parent,
    )

    stdout = await result.stdout.read()
    stderr = await result.stderr.read()

    print(f"{stdout=}")
    print(f"{stderr=}")
