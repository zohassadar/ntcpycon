from __future__ import annotations

import asyncio
import logging

from scapy.all import PacketList, rdpcap
from scapy.packet import Raw

import ntcpycon.abstract

Receiver = ntcpycon.abstract.Receiver


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class WebSocketPayload:
    def __init__(
        self,
        payload: bytes,
    ):
        self.payload = payload
        self.fin = 0
        self.rsv1 = 0
        self.rsv2 = 0
        self.rsv3 = 0
        self.opcode = 0
        self.mask = 0
        self.len = 0
        self.xlen = 0
        self.key = 0
        self.data = 0

        blob = self.payload
        logger.debug(f"Working on a {len(blob)} payload")

        first_byte, blob = blob[0], blob[1:]
        logger.debug(
            f"First byte has int value of {first_byte}.  Remaining length is {len(blob)}"
        )

        self.fin = 1 if first_byte & 0b10000000 else 0
        logger.debug(f"{self.fin=}")

        self.rsv1 = 1 if first_byte & 0b01000000 else 0
        logger.debug(f"{self.rsv1=}")

        self.rsv2 = 1 if first_byte & 0b00100000 else 0
        logger.debug(f"{self.rsv2=}")

        self.rsv3 = 1 if first_byte & 0b00010000 else 0
        logger.debug(f"{self.rsv3=}")

        self.opcode = first_byte & 0b00001111
        logger.debug(f"{self.opcode=}")

        second_byte, blob = blob[0], blob[1:]
        logger.debug(
            f"Second byte has int value of {second_byte}.  Remaining length is {len(blob)}"
        )

        self.mask = 1 if second_byte & 0b10000000 else 0
        logger.debug(f"{self.mask=}")

        self.len = second_byte & 0b01111111
        logger.debug(f"{self.len=}")

        if self.len == 126:
            logger.debug(f"Length is 126.  Reading length from next two bytes")
            length, blob = blob[:2], blob[2:]
            self.len = int.from_bytes(length, byteorder="big")

        if self.len == 127:
            logger.debug(f"Length is 127.  Reading length from next four bytes")
            length, blob = blob[:4], blob[4:]
            self.len = int.from_bytes(length, byteorder="big")

        if self.mask:
            self.key, blob = blob[:4], blob[4:]
            logger.debug(
                f"Mask is {self.key!r}.  Remaining length of data is {len(blob)}"
            )
        else:
            self.data = blob
            return

        # Line the key up with the length of the data
        key = (self.key * (1 + (len(blob) // len(self.key))))[: len(blob)]
        logger.debug(f"Key length is {len(key)}")

        # XOR the bytes together
        self.data = bytes([b ^ k for b, k in zip(blob, key)])

    @classmethod
    def load_packetlist(
        cls,
        packetlist: PacketList,
    ) -> list[WebSocketPayload]:
        return [cls(p) for p in packetlist]

    def __str__(self):
        return self.data.hex()

    def __repr__(self):
        return f"{type(self).__name__}({self.payload})"


def read_pcap_file(
    filename: str,
) -> PacketList:
    logger.debug(f"Attempting to open pcap file {filename}")
    packets = rdpcap(filename)
    logger.debug(f"Successfully read {len(packets)} packets")
    return packets


def filter_packets_by_dest(
    packets: PacketList,
    dst: str,
) -> PacketList:
    packets_from_client = [p for p in packets if p.payload.fields.get("dst") == dst]
    logger.debug(f"Filtered {len(packets)} -> {len(packets_from_client)} - To {dst}")
    return PacketList(packets_from_client)


def filter_packets_with_raw(
    packets: PacketList,
) -> PacketList:
    packets_with_payload = [
        p for p in packets if isinstance(p.payload.payload.payload, Raw)
    ]
    logger.debug(
        f"Filtered {len(packets)} -> {len(packets_with_payload)} - Raw payload"
    )
    return packets_with_payload


def filter_payloads_by_len(
    payloads: list[WebSocketPayload],
    length: int,
) -> list[WebSocketPayload]:
    payloads_by_len = [p for p in payloads if p.len == length]
    logger.debug(
        f"Filtered {len(payloads)} -> {len(payloads_by_len)} - Length of {length}"
    )
    return payloads_by_len


def extract_payloads_dict(
    packets: PacketList,
) -> dict[int, bytes]:
    payloads = {
        p.payload.fields.get("id"): p.payload.payload.payload.load for p in packets
    }
    logger.debug(f"Extracted {len(payloads)}")
    return payloads


def extract_payloads(
    packets: PacketList,
) -> list[bytes]:
    payloads = [p.payload.payload.payload.load for p in packets]
    logger.debug(f"Extracted {len(payloads)}")
    return payloads


def extract_bytes(
    payloads: list[WebSocketPayload],
) -> list[bytes]:
    extracted = [p.data for p in payloads]
    logger.debug(f"Extracted {len(extracted)}")
    return extracted


def get_bytes_from_pcap(
    filename: str,
    dst_host: str,
    length: int,
) -> list[bytes]:
    """
    Opens pcap and extracts bytes from packets addressed to dst_host and with a payload matching length
    """
    packets = read_pcap_file(filename)
    from_client = filter_packets_by_dest(packets, dst_host)
    with_payload = filter_packets_with_raw(from_client)
    payloads = extract_payloads(with_payload)
    converted = WebSocketPayload.load_packetlist(payloads)
    correct_length = filter_payloads_by_len(converted, length)
    extracted = extract_bytes(correct_length)
    return extracted


class PCapReplay(Receiver):
    def __init__(
        self,
        queues: list[asyncio.Queue],
        filename: str,
        dst: str,
        length: int,
    ):
        logger.debug(f"new PCapReplay: {queues=} {filename=} {dst=} {length=}")
        self.queues = queues
        self.filename = filename
        self.dst = dst
        self.length = length
        self.loaded_frames = get_bytes_from_pcap(filename, dst, length)
        logger.info(f"Loaded {len(self.loaded_frames)} from {filename}")


    def __repr__(self):
        queues=self.queues
        filename=self.filename
        dst=self.dst
        length = self.length
        return f'{type(self).__name__}({queues=}, {filename=}, {dst=}, {length=})'

    async def receive(self):
        logger.info("Replay started")
        for value in self.loaded_frames:
            for queue in self.queues:
                await queue.put(value)
        for queue in self.queues:
            await queue.put(None)
        logger.info("Replay complete")
