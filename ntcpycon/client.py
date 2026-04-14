from __future__ import annotations

import argparse
import cmd
import json
import logging
import random
import shutil
import socket
import subprocess
import sys

from edlinkn8 import Everdrive

from ntcpycon import CMD_SEND_INPUT
from ntcpycon import CMD_SEND_SEED
from ntcpycon import CONTROL_PORT
from ntcpycon import DEFAULT_BUILD_ARGS
from ntcpycon import GYM_PATH
from ntcpycon import Payload
from ntcpycon.server import get_everdrives
from ntcpycon.server import get_ntc_rooms
from ntcpycon.server import get_roms
from ntcpycon.server import rom_name

logger = logging.getLogger(__name__)

HISTORY = ".ed2ntc-history"
HISTORY_MAX = 1000


def encode_data(data: dict) -> bytes:
    json_data = json.dumps(data).encode()
    size = len(json_data).to_bytes(4, byteorder="little")
    return size + json_data


def send_command(cmd: str, **kwargs):
    payload = encode_data(dict(cmd=cmd, kwargs=kwargs))
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect(("localhost", CONTROL_PORT))
            s.sendall(payload)
            # data = s.recv(1024)
            s.close()
        # print(data.decode())
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}")


class Client(cmd.Cmd):
    def __init__(self, *args, **kwargs):
        print("starting")
        super().__init__(*args, **kwargs)
        self.prompt = "ed2ntc> "

    intro = "everdrive ntc connector.  Type help or ? to list commands.\n"
    file = None

    def cmdloop(self, *args, **kwargs):
        import readline

        try:
            readline.read_history_file(HISTORY)
        except Exception:
            logger.error(f"can't read {HISTORY}")
        super().cmdloop(*args, **kwargs)
        readline.set_history_length(HISTORY_MAX)
        readline.write_history_file(HISTORY)

    @staticmethod
    def everdrive_help(everdrives):
        return f"""
Everdrives:
{'\n'.join(f"{idx}: {everdrive}" for idx,everdrive in everdrives.items())}
"""

    @staticmethod
    def room_help(rooms):
        return f"""
Rooms:
{'\n'.join(f"{idx}: {room}" for idx,room in rooms.items())}
"""

    @staticmethod
    def roms_help(roms):
        return f"""
Roms:
{'\n'.join(f"{idx}: {rom.name}" for idx,rom in roms.items())}
"""

    def default(self, line):
        if line.strip().startswith("#"):
            return
        print(f"{line!r} not defined", file=sys.stderr)

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
        help_ = self.everdrive_help(everdrives)

        parser = argparse.ArgumentParser(
            prog="pair",
            description=help_,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.add_argument(
            "everdrive",
            type=int,
            metavar="<everdrive>",
            choices=everdrives,
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
            f"{'dis' if args.disconnect else ''}connect_pair",
            everdrive_idx=args.everdrive,
            room_idx=args.room,
        )

    def do_wsc(self, raw_args):
        rooms = get_ntc_rooms()
        help_ = self.room_help(rooms)
        parser = argparse.ArgumentParser(
            prog="wsc",
            description=help_,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.add_argument(
            "room",
            type=int,
            nargs="+",
            metavar="<room>",
            choices=rooms,
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
        for room in args.room:
            send_command(
                f"{'dis' if args.disconnect else ''}connect_room",
                room_idx=room,
            )

    def do_stat(self, _):
        send_command("check_status")

    def do_refresh(self, _):
        send_command("refresh_everdrives")
        send_command("refresh_roomlist")

    def do_data(self, raw_args):
        def hex_int(i):
            if i.startswith("0x"):
                return int(i[2:], 16)
            return int(i)

        everdrives = get_everdrives()
        help_ = self.everdrive_help(everdrives)
        parser = argparse.ArgumentParser(
            prog="data",
            description=help_,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.add_argument(
            "everdrive",
            type=int,
            metavar="<everdrive>",
            choices=everdrives,
        )
        parser.add_argument(
            "data",
            type=hex_int,
            nargs="+",
        )
        try:
            args = parser.parse_args(raw_args.split())
        except:
            return

        send_command(
            f"bytes_to_everdrive",
            everdrive_idx=args.everdrive,
            data=args.data,
        )

    def do_seed(self, raw_args):
        everdrives = get_everdrives()
        help_ = self.everdrive_help(everdrives)
        parser = argparse.ArgumentParser(
            prog="seed",
            description=help_,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.add_argument(
            "everdrives",
            nargs=2,
            type=int,
            choices=everdrives,
        )
        try:
            args = parser.parse_args(raw_args.split())
        except:
            return
        if len(set(args.everdrives)) != len(args.everdrives):
            print(f"Choose unique everdrives")
            return

        seed = [
            random.randint(0x0, 0xFF),
            random.randint(0x2, 0xFF),  # Avoid buggy seeds
            random.randint(0x0, 0xFF),
        ]

        print(
            f"Generated seed {''.join(f'{b:02X}' for b in seed)} for "
            f"everdrives {args.everdrives[0]} and {args.everdrives[1]}",
        )
        send_command(
            f"bytes_to_everdrive",
            everdrive_idx=args.everdrives[0],
            data=[CMD_SEND_SEED, *seed],
        )
        send_command(
            f"bytes_to_everdrive",
            everdrive_idx=args.everdrives[1],
            data=[CMD_SEND_SEED, *seed],
        )

    def do_edc(self, raw_args):
        everdrives = get_everdrives()
        help_ = self.everdrive_help(everdrives)

        parser = argparse.ArgumentParser(
            prog="edc",
            description=help_,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.add_argument(
            "everdrive",
            type=int,
            nargs="+",
            metavar="<everdrive>",
            choices=everdrives,
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
        for everdrive in args.everdrive:
            send_command(
                f"{'dis' if args.disconnect else ''}connect_everdrive",
                everdrive_idx=everdrive,
            )

    def do_launch(self, raw_args):
        roms = get_roms()
        everdrives = get_everdrives()
        help_ = "\n".join(
            [
                self.roms_help(roms),
                self.everdrive_help(everdrives),
            ],
        )
        parser = argparse.ArgumentParser(
            prog="launch",
            description=help_,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.add_argument("rom", type=int, metavar="<rom>", choices=roms)
        parser.add_argument(
            "everdrive",
            nargs="+",
            type=int,
            metavar="<everdrive>",
            choices=everdrives,
        )
        try:
            args = parser.parse_args(raw_args.split())
        except:
            return
        rom = roms[args.rom]

        for ed in args.everdrive:
            everdrive = everdrives[ed]
            try:
                Everdrive(serial=everdrive).launch_rom_from_file(rom)
            except Exception as exc:
                print(f"{type(exc).__name__}: {exc}")

    def emptyline(self):
        return False

    def do_EOF(self, _):
        print("")
        return True

    def do_exit(self, _):
        return True
