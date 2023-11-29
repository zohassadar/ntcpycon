import logging
import sys

import yaml

import ntcpycon.abstract
import ntcpycon.edlink
import ntcpycon.file_handler
import ntcpycon.pcap_replay
import ntcpycon.nestrisocr
import ntcpycon.ws_sender


WSSender = ntcpycon.ws_sender.WSSender
NESTrisOCRServer = ntcpycon.nestrisocr.NESTrisOCRServer
PCapReplay = ntcpycon.pcap_replay.PCapReplay
FileWriter = ntcpycon.file_handler.FileWriter
FileReceiver = ntcpycon.file_handler.FileReceiver
EDLink = ntcpycon.edlink.EDLink


def get_senders(
    senders_dict: dict,
):
    senders = []
    for websocket in senders_dict.get("websockets", []):
        uri = websocket.get("uri")
        if not uri:
            sys.exit("uri must be specified for websocket")
        no_verify = websocket.get("no_verify", False)
        senders.append(WSSender(uri, no_verify))

    if local_file := senders_dict.get("local_file"):
        filename = local_file.get("filename")
        if not filename:
            sys.exit("filename must be specified to read local_file")
        overwrite = local_file.get("overwrite", False)
        senders.append(FileWriter(filename, overwrite))

    if not senders:
        sys.exit(f"At least one sender must be specified in config file")

    return senders


def get_receiver(
    queues: list,
    receiver: dict,
):
    if ocr_server := receiver.get("ocr_server", {}):
        port = ocr_server.get("port")
        if not port:
            sys.exit("port must be specified to start tcp server")
        return NESTrisOCRServer(queues, port)

    elif (edlink := receiver.get("edlink", {})) or "edlink" in receiver.keys():
        launch = False
        if edlink:
            launch = edlink.get("launch")
        return EDLink(queues, launch=launch)

    elif local_file := receiver.get("local_file", {}):
        filename = local_file.get("filename")
        if not filename:
            sys.exit("filename must be specified to read local_file")
        return FileReceiver(queues, filename)

    elif packet_capture := receiver.get("packet_capture"):
        filename = packet_capture.get("filename")
        dst = packet_capture.get("dst")
        length = packet_capture.get("length")
        if not filename:
            sys.exit("filename must be specified to read packet_capture")
        if not dst:
            sys.exit("dst must be specified to read packet_capture")
        if not length:
            sys.exit("length must be specified to read packet_capture")
        return PCapReplay(queues, filename, dst, length)

    sys.exit(f"At least one receiver must be specified in config file")


def set_logging(debug: bool):
    level = logging.DEBUG if debug else logging.INFO
    logger = logging.getLogger()
    logger.setLevel(level)
    format = logging.Formatter(
        "{name} - {funcName} - {lineno} - {levelname}: {message}",
        style="{",
    )
    streamhandler = logging.StreamHandler()
    streamhandler.setFormatter(format)
    streamhandler.setLevel(level)
    while logger.handlers:
        logger.handlers.pop()
    logger.addHandler(streamhandler)


def get_receiver_and_senders():
    usage = f"ntcpycon <config file>"
    if len(sys.argv) < 2:
        sys.exit(usage)
    elif sys.argv[1].startswith("-h") or sys.argv[1].startswith("--h"):
        sys.exit(usage)

    config_file = sys.argv[1]
    try:
        with open(config_file) as file:
            config = yaml.safe_load(file)
    except Exception as exc:
        sys.exit(f"Unable to load config: {type(exc).__name__}: {exc!s}")

    senders_dict = config.get("senders", {})
    receiver_dict = config.get("receiver", {})
    debug_bool = config.get("debug", False)

    set_logging(debug_bool)

    senders = get_senders(senders_dict)

    queues = [sender.queue for sender in senders]

    receiver = get_receiver(queues, receiver_dict)

    return receiver, senders
