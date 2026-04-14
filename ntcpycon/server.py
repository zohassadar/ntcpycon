from __future__ import annotations

import asyncio
import json
import logging

import yaml
from edlinkn8 import Everdrive

from ntcpycon import CONTROL_PORT
from ntcpycon import GYM_PATH
from ntcpycon import NTC_ROOMS
from ntcpycon import Payload
from ntcpycon.adeque import AsyncDeque
from ntcpycon.edlink import NewEDLink
from ntcpycon.ws_sender import NewWSSender

logger = logging.getLogger(__name__)


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

        for (e_idx, _), pair in self.data_pairs.items():
            if e_idx == everdrive_idx:
                await pair.end()
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

    async def cmd_bytes_to_everdrive(
        self,
        *,
        everdrive_idx: int,
        data: list[int],
    ):
        if not (edlink := self.connected_everdrives.get(everdrive_idx)):
            logger.error(f"everdrive {everdrive_idx} not connected")
            return
        logger.info(f"Sending {bytes(data).hex()} to everdrive {everdrive_idx}")
        await edlink.game_control.put(data)

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
                    f"everdrive {everdrive_idx} already paired with room {r_idx}",
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
            f"Connection between everdrive {everdrive_idx} and room {room_idx} ended",
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
                logger.info(
                    f"Disconnecting everdrive {everdrive_idx} from room {room_idx}",
                )
                await pair.end()
                return
        logger.error(
            f"No pair found between everdrive {everdrive_idx} and room {room_idx}",
        )

    async def cmd_check_status(self):
        logger.info(f"\nEverdrives:")
        for idx, port in self.everdrives.items():
            logger.info(
                f"{idx} - {port}: {'connected' if self.connected_everdrives.get(idx) else 'idle'}",
            )

        logger.info(f"\nRooms:")
        for idx, room in self.ntc_rooms.items():
            logger.info(
                f"{idx} - {room.split('/')[-1]}: {'connected' if self.connected_rooms.get(idx) else 'idle'}",
            )

        logger.info(f"\nActive pairs:")
        for (e, r), pair in self.data_pairs.items():
            logger.info(f"Everdrive {e} <-> Room {r}")

        # logger.info(f"Active jobs:")
        # for job in self._jobs:
        #     print(job.get_name())
        #

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

    async def game_stream(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ):
        try:
            logger.info("establishing game stream")
            while True:
                fields = 0
                payload = bytearray(Payload.SIZE * Payload.COUNT)
                for everdrive in list(self.connected_everdrives.values()):
                    span = slice(
                        fields * Payload.SIZE,
                        fields * Payload.SIZE + Payload.SIZE,
                    )
                    load = bytearray(Payload.SIZE)
                    load[Payload.playfield] = everdrive.gym._playfield[
                        Payload.playfield
                    ]
                    load[Payload.score] = everdrive.gym.score.to_bytes(
                        4,
                        byteorder="little",
                    )
                    load[Payload.lines] = everdrive.gym.lines.to_bytes(
                        4,
                        byteorder="little",
                    )
                    load[Payload.level] = everdrive.gym.level
                    load[Payload.next_] = everdrive.gym.next_piece

                    fields += 1
                    payload[span] = load
                await client_reader.read(1)
                client_writer.write(payload[: fields * Payload.SIZE])
                await client_writer.drain()
        except Exception as exc:
            logger.error(f"{type(exc).__name__}: {exc}")
        finally:
            logger.info("game stream ended")

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

            if cmd == "game_stream":
                task = asyncio.create_task(
                    self.game_stream(client_reader, client_writer),
                )
            else:
                kwargs = data.get("kwargs", {})
                task = asyncio.create_task(
                    getattr(self, f"cmd_{cmd}", self.unknown)(**kwargs),
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
