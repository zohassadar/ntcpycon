import argparse
import asyncio
import cmd
import json
import logging
import pathlib
import shutil
import sys
import socket
import json

import yaml

CONTROL_PORT = 9999
MAX_NTC_RCV = 100
MAX_NTC_SEND = 100
MAX_ED_RCV = 100
MAX_ED_SEND = 100
NTC_ROOMS = "rooms.yml"

from asyncio import subprocess

from ntcpycon.ws_sender import WSSender
from ntcpycon.edlink import EDLink


from edlinkn8 import Everdrive

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

NODE = shutil.which("node")

if NODE is None:
    raise RuntimeError("missing node")

BUILD = pathlib.Path.cwd() / "TetrisGYM" / "build.js"

BUILD_ARGS = ["-e"]

"""
NTC  ---->  RECV      SEND ----> ED

NTC  <----  SEND      RECV <---- ED
"""

def encode_data(data: dict) -> bytes:
    json_data = json.dumps(data).encode()
    size = len(json_data).to_bytes(4, byteorder="little")
    return size + json_data

def get_ntc_rooms():
    with open(NTC_ROOMS) as file:
        return yaml.safe_load(file)

def rom_name(args: list[str]) -> str:
    sargs = sorted(args)
    return f'tetris{"".join(sargs)}.nes'

def rom_exists(rom: str | pathlib.Path) -> bool:
    return pathlib.Path(rom).exists()

class Server:
    def __init__(
        self,
        port: int = CONTROL_PORT,
    ):
        self.port = port

        self.ntc_recv_queues: dict[int, asyncio.Queue] = {}
        self.ntc_send_queues: dict[int, asyncio.Queue] = {}

        self.ed_recv_queues: dict[int, asyncio.Queue] = {}
        self.ed_send_queues: dict[int, asyncio.Queue] = {}

        self.pairs: dict = {}
        self.load_ntc_rooms()

    def __repr__(self):
        port = self.port
        return f"{type(self).__name__}({port=})"

    def load_ntc_rooms(self):
        self.ntc_rooms = get_ntc_rooms()

    async def cmd_build_rom(
        self,
        build_args: list[str],
    ):
        result = await asyncio.create_subprocess_exec(
            NODE,  # type: ignore
            BUILD,
            *build_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=BUILD.parent,
        )

        stdout = await result.stdout.read()
        stderr = await result.stderr.read()
        logger.debug("stdout received: %s, stdout.decode()")
        logger.debug("stderr received: %s, stderr.decode()")
        return result.returncode

    async def cmd_launch_rom(
        self,
        *,
        serial: str,
        rom: str,
        debug: bool = False,
    ):
        ed = Everdrive(serial=serial)
        ed.launch_rom_from_file(rom)

    async def cmd_connect_nestrischamps(
        self,
        *,
        debug: bool = False,
    ):
        pass

    async def cmd_disconnect_nestrischamps(
        self,
        *,
        debug: bool = False,
    ):
        pass

    async def cmd_connect_everdrive(
        self,
        *,
        debug: bool = False,
    ):
        pass

    async def cmd_disconnect_everdrive(
        self,
        *,
        debug: bool = False,
    ):
        pass

    async def cmd_create_pair(
        self,
        *,
        debug: bool = False,
    ):
        pass

    async def cmd_destroy_pair(
        self,
        *,
        debug: bool = False,
    ):
        pass

    async def cmd_check_status(
        self,
        *,
        debug: bool = False,
    ):
        pass

    async def unknown(
        self,
        *,
        debug: bool = False,
        **kwargs,
    ):
        valid_commands = [d for d in dir(self) if d.startswith("cmd_")]
        print(valid_commands)
        print(kwargs)

    async def serve(
        self,
    ):
        tcp_server = await asyncio.start_server(
            self.handler,
            "localhost",
            port=self.port,
        )
        await tcp_server.serve_forever()

    async def handler(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ):
        try:
            peer = client_writer.get_extra_info("peername")
            leng = await client_reader.read(4)
            if not leng:
                logger.error(f"Nothing received from %s", peer)
                return
            expected = int.from_bytes(leng, byteorder="little")
            payload = await client_reader.read(expected)
            message = payload.decode()
            try:
                data = json.loads(message)
            except:
                logger.error("Invalid json", exc_info=True)
                data = {}
            cmd = data.get("cmd")
            if not cmd:
                logger.error("Invalid command %s", cmd)
            kwargs = data.get("kwargs", {})
            result = None
            try:
                result = await getattr(self, f"cmd_{cmd}", self.unknown)(**kwargs)
            except:
                logger.error(
                    "Unable to run %s with kwargs %s", cmd, kwargs, exc_info=True
                )
            message = str(result)
            client_writer.write(message.encode())
            await client_writer.drain()
            client_writer.close()
            await client_writer.wait_closed()

        except Exception as exc:
            logger.error("Problem with handling socket", exc_info=True)



class NTC:
    async def __init__(self, uri: str):
        self.uri = uri
        self.recv = asyncio.Queue(maxsize=MAX_NTC_RCV)
        self.send = asyncio.Queue(maxsize=MAX_NTC_SEND)

    async def receive(self):
        """
        receives data intended for nestrischamps
        """
        try:
            while True:
                data = await self.recv.get()
                if data is None:
                    logger.info("%s recv shutdown received", self.uri)
                    break
        finally:
            logger.debug("%s end", self.uri)



def send_command(cmd: str, **kwargs):
    HOST = "127.0.0.1"  # The remote host
    PORT = 9999  # The same port as used by the server
    data = {"cmd": cmd, "kwargs": kwargs}

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((HOST, PORT))
        payload = json.dumps(data).encode()
        s.sendall(len(payload).to_bytes(4, byteorder="little"))
        s.sendall(payload)
        data = s.recv(1024)
        s.close()
    print("Received", repr(data))


class Client(cmd.Cmd):
    def __init__(self, *args, **kwargs):
        print("starting")
        super().__init__(*args, **kwargs)

    intro = "everdrive ntc connector.  Type help or ? to list commands.\n"
    file = None

    def _set_disconnected(self):
        self.prompt = "disconnected> "

    def do_something(self, what):
        print("something" + str(what))

    def default(self, command):
        print(f"{command!r} with {args!r} not defined", file=sys.stderr)

    def do_lsed(self, _):
        drives = Everdrive.list_ports()
        for idx, serial in drives.items():
            print(f"{idx}: {serial}")

    def do_lsntc(self, _):
        rooms = get_ntc_rooms()
        for idx, room in enumerate(rooms):
            print(f"{idx}: {room}")

    def emptyline(self):
        pass

    def do_EOF(self, arg):
        print("")
        return True

    def do_EXIT(self, arg):
        return True




def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "client_or_server",
        choices=["client", "server"],
    )
    args = parser.parse_args()
    if args.client_or_server == "client":
        Client().cmdloop()
    elif args.client_or_server == "server":
        asyncio.run(Server().serve())


if __name__ == "__main__":
    main()
