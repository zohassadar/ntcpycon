import sys
if len(sys.argv) == 1:
    import ntcpycon.connect
    ntcpycon.connect.start_connect()
elif sys.argv[1] == "edlink-test":
    # temp entrypoint to test
    import ntcpycon.edlink
    ntcpycon.edlink.edlink()
