from ntcpycon import __version__

import ntcpycon.abstract
import ntcpycon.nestrisocr
import ntcpycon.binaryframe
import ntcpycon.config
import ntcpycon.connect
import ntcpycon.file_handler
import ntcpycon.pcap_replay
import ntcpycon.tcp_server
import ntcpycon.ws_sender


def test_version():
    assert __version__ == "0.1.0"



