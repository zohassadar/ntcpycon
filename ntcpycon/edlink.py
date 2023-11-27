import edlinkn8

CMD_SEND_STATS = 0x42

"""
; needed for nestrischamps:
; gameMode 1 
; playState 1
; rowY 1
; completedRow 4
; lines 2 (bcd)
; levelNumber 1
; binScore 4
; nextPiece 1
; currentPiece 1
; tetriminoX 1 Needed to determine where piece is in playfield
; tetriminoY 1 same
; frameCounter 2 Used for line clearing animation
; autoRepeatX 1 current DAS
; statsByType 14
; playfield 200
; subtotal 235/0xeb

; footer : 2 * $AA
; Total 237/0xed
"""

def edlink():
    everdrive = edlinkn8.Everdrive()
    gym = edlinkn8.NesRom.from_file('TetrisGYM/ed2ntc.nes')
    try:
        everdrive.load_game(gym)
    except:
        ...
    last = 0
    while True: 
        everdrive.write_fifo(bytearray([0x42]))
        msg = everdrive.receive_data(0xed)
        if len(msg) == 0xed:
            fc = int.from_bytes(msg[18:20], 'little')
            if (lastn := ((last + 1) & 0xffff)) != fc:
                print(f'dropped {fc-lastn} frame{"s" if fc-lastn>1 else ""}.  {last+1} to {fc-1}')
            last = fc
        else:
            break
    print("Finished")
