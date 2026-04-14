from __future__ import annotations

import argparse
import logging

logging.basicConfig(level=logging.INFO)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "client_or_server",
        choices=["client", "server"],
    )
    args = parser.parse_args()
    if args.client_or_server == "client":
        from ntcpycon.client import Client

        Client().cmdloop()
    elif args.client_or_server == "server":
        import asyncio

        from ntcpycon.server import Server

        asyncio.run(Server().serve())


if __name__ == "__main__":
    main()
