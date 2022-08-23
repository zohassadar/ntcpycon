import asyncio
import sys

import ntcpycon.abstract
import ntcpycon.config

Receiver = ntcpycon.abstract.Receiver
Sender = ntcpycon.abstract.Sender

get_receiver_and_senders = ntcpycon.config.get_receiver_and_senders


async def connect(receiver: Receiver, senders: list[Sender]):
    if not receiver or not senders:
        sys.exit("Cannot connect without receiver and at least one sender")
    jobs = [s.send() for s in senders]
    jobs.append(receiver.receive())
    await asyncio.gather(*jobs)


def start_connect():
    try:
        receiver, senders = get_receiver_and_senders()
        asyncio.run(connect(receiver=receiver, senders=senders))
    except KeyboardInterrupt:
        print("Exiting")
