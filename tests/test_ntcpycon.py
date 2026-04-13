from __future__ import annotations

import ntcpycon.abstract
import ntcpycon.binaryframe
import ntcpycon.config
import ntcpycon.connect
import ntcpycon.file_handler
import ntcpycon.nestrisocr
import ntcpycon.pcap_replay
import ntcpycon.ws_sender
from ntcpycon import __version__


def test_version():
    assert __version__ == "0.1.0"
