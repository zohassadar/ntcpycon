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
import subprocess
import yaml

from ntcpycon.ws_sender import NewWSSender
from ntcpycon.edlink import NewEDLink
from ntcpycon.adeque import AsyncDeque

from edlinkn8 import Everdrive

CONTROL_PORT = 9999
NTC_ROOMS = "rooms.yml"
GYM_PATH = pathlib.Path.cwd() / "TetrisGYM"
BUILD_SCRIPT = GYM_PATH / "build.js"
DEFAULT_BUILD_ARGS = ["-e"]
NODE = shutil.which("node")

if NODE is None:
    raise RuntimeError("missing node")

logger = logging.getLogger(__name__)

logging.basicConfig(level=logging.INFO)


def encode_data(data: dict) -> bytes:
    json_data = json.dumps(data).encode()
    size = len(json_data).to_bytes(4, byteorder="little")
    return size + json_data


def send_command(cmd: str, **kwargs):
    payload = encode_data(dict(cmd=cmd, kwargs=kwargs))
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect(("localhost", CONTROL_PORT))
        s.sendall(payload)
        # data = s.recv(1024)
        s.close()
    # print(data.decode())


def get_everdrives():
    return Everdrive.list_ports()


def get_ntc_rooms():
    with open(NTC_ROOMS) as file:
        return {i: f for i, f in enumerate(yaml.safe_load(file))}


def get_roms():
    return {i: f for i, f in enumerate(GYM_PATH.glob("*.nes"))}


def rom_name(args: list[str]) -> str:
    sargs = sorted(args)
    return f'tetris{"".join(sargs)}.nes'


class GameDataStream:
    def __init__(
        self,
        ed_game_data: AsyncDeque,
        ws_game_data: AsyncDeque,
    ):
        self.ed_game_data = ed_game_data
        self.ws_game_data = ws_game_data

    async def connect(self):
        async for message in self.ed_game_data:
            if message is None:
                return
            await self.ws_game_data.put(message)

    async def end(self):
        await self.ed_game_data.put(None)


class Server:
    def __init__(
        self,
        port: int = CONTROL_PORT,
    ):
        self.port = port

        self.connected_everdrives = {}
        self.connected_rooms = {}
        self.data_pairs = {}

        self.ntc_rooms = {}
        self.load_ntc_rooms()

        self.everdrives = {}
        self.load_everdrives()
        self._jobs = set()

    def load_everdrives(self):
        self.everdrives = get_everdrives()
        for idx, drive in self.everdrives.items():
            logger.info(f"Everdrive: {idx} - {drive}")

    def load_ntc_rooms(self):
        self.ntc_rooms = get_ntc_rooms()
        for idx, room in self.ntc_rooms.items():
            logger.info(f"NTC Room: {idx} - {room}")

    async def cmd_refresh_everdrives(self):
        logger.info("refreshing everdrive list")
        self.load_everdrives()

    async def cmd_refresh_roomlist(self):
        logger.info("refreshing ntc room list")
        self.load_ntc_rooms()

    async def cmd_connect_room(
        self,
        *,
        room_idx: int,
    ):
        if self.connected_rooms.get(room_idx):
            logger.error(f"room {room_idx} already connected")
            return
        try:
            room_uri = self.ntc_rooms[room_idx]
            ntc_ws = NewWSSender(room_uri, no_verify=True)
            logger.info(f"connecting to room {room_idx}")
            self.connected_rooms[room_idx] = ntc_ws
            await ntc_ws.connect()
        except Exception as exc:
            logger.error(f"{type(exc).__name__}: {exc!s}")
        finally:
            self.connected_rooms.pop(room_idx, None)

        for (_, r_idx), pair in self.data_pairs.items():
            if r_idx == room_idx:
                await pair.end()
        logger.info(f"room {room_idx} connection ended")

    async def cmd_disconnect_room(
        self,
        *,
        room_idx: int,
    ):
        if not (ntc_ws := self.connected_rooms.pop(room_idx, None)):
            logger.error(f"room {room_idx} not connected")
            return
        logger.info(f"disconnecting room {room_idx}")
        await ntc_ws.end()

    async def cmd_connect_everdrive(
        self,
        *,
        everdrive_idx: int,
    ):
        if self.connected_everdrives.get(everdrive_idx):
            logger.error(f"everdrive {everdrive_idx} already connected")
            return
        logger.info(f"connecting everdrive {everdrive_idx}")
        everdrive = self.everdrives[everdrive_idx]
        edlink = NewEDLink(serial=everdrive)
        self.connected_everdrives[everdrive_idx] = edlink
        try:
            await edlink.connect()
        except Exception as exc:
            logger.error(f"{type(exc).__name__}: {exc!s}")
        finally:
            self.connected_everdrives.pop(everdrive_idx, None)
        logger.info(f"everdrive {everdrive_idx} connection ended")

    async def cmd_disconnect_everdrive(
        self,
        *,
        everdrive_idx: int,
    ):
        if not (edlink := self.connected_everdrives.pop(everdrive_idx, None)):
            logger.error(f"everdrive {everdrive_idx} not connected")
            return
        logger.info(f"disconnecting everdrive {everdrive_idx}")
        await edlink.end()

    async def cmd_connect_pair(
        self,
        *,
        everdrive_idx: int,
        room_idx: int,
    ):
        if (edlink := self.connected_everdrives.get(everdrive_idx)) is None:
            logger.error(f"everdrive {everdrive_idx} not connected")
            return
        if (ntc_ws := self.connected_rooms.get(room_idx)) is None:
            logger.error(f"room {room_idx} not connected")
            return
        for e_idx, r_idx in self.data_pairs:
            if e_idx == everdrive_idx:
                logger.error(
                    f"everdrive {everdrive_idx} already paired with room {r_idx}"
                )
                return
            if r_idx == room_idx:
                logger.error(f"room {room_idx} already paired with everdrive {e_idx}")
                return
        logger.info(f"connecting everdrive {everdrive_idx} to room {room_idx}")
        pair = GameDataStream(edlink.game_data, ntc_ws.game_data)
        self.data_pairs[(everdrive_idx, room_idx)] = pair
        try:
            await pair.connect()
        except Exception as exc:
            logger.error(f"{type(exc).__name__}: {exc!s}")
        finally:
            self.data_pairs.pop((everdrive_idx, room_idx), None)
        logger.info(
            f"Connection between everdrive {everdrive_idx} and room {room_idx} ended"
        )

    async def cmd_disconnect_pair(
        self,
        *,
        everdrive_idx: int,
        room_idx: int,
    ):
        if self.connected_everdrives.get(everdrive_idx) is None:
            logger.error(f"everdrive {everdrive_idx} not connected")
            return
        if self.connected_rooms.get(room_idx) is None:
            logger.error(f"room {room_idx} not connected")
            return
        for ed_room, pair in self.data_pairs.items():
            if ed_room == (everdrive_idx, room_idx):
                logger.info(f"Disconnecting everdrive {everdrive_idx} from room {room_idx}")
                await pair.end()
                return
        logger.error(
            f"No pair found between everdrive {everdrive_idx} and room {room_idx}"
        )

    async def cmd_check_status(self):
        logger.info(f"Everdrives:")
        for idx, port in self.everdrives.items():
            logger.info(f"Everdrive {idx} - {port}: {'connected' if self.connected_everdrives.get(idx) else 'idle'}")

        logger.info(f"Rooms:")
        for idx, room in self.ntc_rooms.items():
            logger.info(f"Room {idx} - {room}: {'connected' if self.connected_rooms.get(idx) else 'idle'}")

        logger.info (f"Active pairs:")
        for (e, r), pair in self.data_pairs.items():
            logger.info(f"Everdrive {e} <-> room {r}")

        logger.info (f"Active jobs:")
        for job in self._jobs:
            print(job.get_name())

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
            task = asyncio.create_task(
                getattr(self, f"cmd_{cmd}", self.unknown)(**kwargs)
            )
            self._jobs.add(task)
            task.add_done_callback(self._jobs.discard)

            # message = str(result)
            # client_writer.write(message.encode())
            # await client_writer.drain()
            # client_writer.close()
            # await client_writer.wait_closed()

        except Exception as exc:
            logger.error("Problem with handling socket", exc_info=True)


class Client(cmd.Cmd):
    def __init__(self, *args, **kwargs):
        print("starting")
        super().__init__(*args, **kwargs)
        self.prompt = "ed2ntc> "

    intro = "everdrive ntc connector.  Type help or ? to list commands.\n"
    file = None

    def default(self, command):
        print(f"{command!r} not defined", file=sys.stderr)

    def do_build(self, args):
        build_args = DEFAULT_BUILD_ARGS + args.split()
        romname = rom_name(build_args)
        result = subprocess.run(
            [NODE, BUILD_SCRIPT, *build_args],  # type: ignore
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=GYM_PATH,
        )

        stdout = result.stdout
        stderr = result.stderr
        if stdout:
            print(f"stdout:\n {stdout.decode()}")
        if stderr:
            print(f"stderr:\n {stderr.decode()}")

        if not result.returncode:
            shutil.copy(GYM_PATH / "tetris.nes", GYM_PATH / romname)

        return result.returncode

    def do_lsed(self, _):
        drives = get_everdrives()
        for idx, serial in drives.items():
            print(f"{idx}: {serial}")

    def do_lsrom(self, _):
        roms = get_roms()
        for idx, rom in roms.items():
            print(f"{idx}: {rom.name}")

    def do_lsntc(self, _):
        rooms = get_ntc_rooms()
        for idx, room in rooms.items():
            print(f"{idx}: {room}")

    def do_pair(self, raw_args):
        everdrives = get_everdrives()
        rooms = get_ntc_rooms()
        help_ = f"""
Everdrives:
{'\n'.join(f"{idx}: {everdrive}" for idx,everdrive in everdrives.items())}

Rooms:
{'\n'.join(f"{idx}: {room}" for idx,room in rooms.items())}

"""
        parser = argparse.ArgumentParser(
            prog="pair",
            description=help_,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.add_argument("room", type=int, metavar="<room>", choices=rooms)
        parser.add_argument(
            "everdrive", type=int, metavar="<everdrive>", choices=everdrives
        )
        parser.add_argument(
            "-d",
            "--disconnect",
            action="store_true",
        )
        try:
            args = parser.parse_args(raw_args.split())
        except:
            return

        send_command(
            f"{'dis' if args.disconnect else ''}connect_pair",
            everdrive_idx=args.everdrive,
            room_idx=args.room,
        )

    def do_wsc(self, raw_args):
        rooms = get_ntc_rooms()
        help_ = f"""
Rooms:
{'\n'.join(f"{idx}: {room}" for idx,room in rooms.items())}

"""
        parser = argparse.ArgumentParser(
            prog="wsc",
            description=help_,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.add_argument("room", type=int, metavar="<room>", choices=rooms)
        parser.add_argument(
            "-d",
            "--disconnect",
            action="store_true",
        )
        try:
            args = parser.parse_args(raw_args.split())
        except:
            return
        send_command(
            f"{'dis' if args.disconnect else ''}connect_room",
            room_idx=args.room,
        )

    def do_stat(self, _):
        send_command("check_status")

    def do_edc(self, raw_args):
        everdrives = get_everdrives()
        help_ = f"""
Everdrives:
{'\n'.join(f"{idx}: {everdrive}" for idx,everdrive in everdrives.items())}

"""
        parser = argparse.ArgumentParser(
            prog="edc",
            description=help_,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.add_argument(
            "everdrive", type=int, metavar="<everdrive>", choices=everdrives
        )
        parser.add_argument(
            "-d",
            "--disconnect",
            action="store_true",
        )
        try:
            args = parser.parse_args(raw_args.split())
        except:
            return
        send_command(
            f"{'dis' if args.disconnect else ''}connect_everdrive",
            everdrive_idx=args.everdrive,
        )

    def do_launch(self, raw_args):
        roms = get_roms()
        everdrives = get_everdrives()
        help_ = f"""
Roms:
{'\n'.join(f"{idx}: {rom.name}" for idx,rom in roms.items())}

Everdrives:
{'\n'.join(f"{idx}: {everdrive}" for idx,everdrive in everdrives.items())}

"""
        parser = argparse.ArgumentParser(
            prog="launch",
            description=help_,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.add_argument("rom", type=int, metavar="<rom>", choices=roms)
        parser.add_argument(
            "everdrive", type=int, metavar="<everdrive>", choices=everdrives
        )
        try:
            args = parser.parse_args(raw_args.split())
        except:
            return
        everdrive = everdrives[args.everdrive]
        rom = roms[args.rom]

        print(f"gonna launch {rom.name} to {everdrive}")
        try:
            Everdrive(serial=everdrive).launch_rom_from_file(rom)
        except:
            import traceback

            traceback.print_exc()

    def emptyline(self):
        pass

    def do_EOF(self, _):
        print("")
        return True

    def do_EXIT(self, _):
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
