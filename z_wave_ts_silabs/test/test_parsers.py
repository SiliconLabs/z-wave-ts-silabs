from .. import DchType
from ..parsers import DchFrame


def test_dch_frame_from_bytes_short_garbage():
    # 3 bytes long frame to check if the parser returns None instead of raising an exception on the first struct.unpack
    dch_frame_as_bytes = bytes([ 0x00 for _ in range(3) ])
    assert DchFrame.from_bytes(dch_frame_as_bytes) is None


def test_dch_frame_from_bytes_long_garbage():
    # 5000 bytes long frame, the parser should return None on the first check for DchSymbol.START
    dch_frame_as_bytes = bytes([ 0x00 for _ in range(5000) ])
    assert DchFrame.from_bytes(dch_frame_as_bytes) is None


# the following tests use 2 Z-Wave frame taken from a WPK
#
# NOP from Controller (Tx):
# 5B 25 00 03 00 CC 9D 29 C5 01 05 00 00 29 00 00 00 00 00 B9 6C FC DF EE BB 0C 01 41 02 0B 02 00 32 FD 01 01 06 09 5D
#
# ACK from EndDevice (Rx):
# 5B 25 00 03 00 A4 8C A3 C5 01 05 00 00 2A 00 00 00 00 00 BA 6C F8 DF EE BB 0C 02 03 82 0A 01 F1 F9 1C 01 01 06 51 5D
#
# They will be used to test the parser

def test_dch_frame_from_and_to_bytes_dchv2_frame():

    dch_frame_structure = [
        0x5B, # start symbol
        0x1E, 0x00, # length
        0x02, 0x00, # version
        0xCC, 0x9D, 0x29, 0xC5, 0x01, 0x05,  # timestamp (us)
        0x2A, 0x00, # type
        0x6C, # Sequence number
        0xF8, # PTI start symbol, Rx Start
        0xDF, 0xEE, 0xBB, 0x0C, 0x02, 0x03, 0x82, 0x0A, 0x01, 0xF1, # Z-Wave Payload, ACK from End Device
        0xF9, # PTI stop symbol, Rx Success
        0x1C, # RSSI
        0x01, #
        0x01, #
        0x06, #
        0x51, #
        0x5D # stop symbol
    ]

    dch_frame = DchFrame.from_bytes(bytes(dch_frame_structure))
    assert dch_frame is not None
    assert dch_frame.dch_type == DchType.PTI_RX.value

    dch_frame_to_bytes = dch_frame.to_bytes()
    assert dch_frame_to_bytes == bytes(dch_frame_structure)

def test_dch_frame_from_and_to_bytes_dchv3_frame():
    dch_frame_structure = [
        0x5B, # start symbol
        0x25, 0x00, # length
        0x03, 0x00, # version
        0xCC, 0x9D, 0x29, 0xC5, 0x01, 0x05, 0x00, 0x00,  # timestamp (ns)
        0x2A, 0x00, # type
        0x00, 0x00, 0x00, 0x00, # flags
        0xBA, 0x6C, # Sequence number
        0xF8, # PTI start symbol, Rx Start
        0xDF, 0xEE, 0xBB, 0x0C, 0x02, 0x03, 0x82, 0x0A, 0x01, 0xF1, # Z-Wave Payload, ACK from End Device
        0xF9, # PTI stop symbol, Rx Success
        0x1C, # RSSI
        0x01, #
        0x01, #
        0x06, #
        0x51, #
        0x5D # stop symbol
    ]

    dch_frame = DchFrame.from_bytes(bytes(dch_frame_structure))
    assert dch_frame is not None
    assert dch_frame.dch_type == DchType.PTI_RX.value

    dch_frame_to_bytes = dch_frame.to_bytes()
    assert dch_frame_to_bytes == bytes(dch_frame_structure)
