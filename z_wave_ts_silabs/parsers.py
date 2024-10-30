from __future__ import annotations
from dataclasses import dataclass
from enum import IntEnum
import struct
import logging

from .definitions import RAILZwaveRegionID, RAILZwave2CHRegionIDs, RAILZwave3ChRegionIDs, RAILZwaveLRControllerRegionIDs, RAILZwaveLREndDeviceRegionIDs

_logger = logging.getLogger(__name__)


class DchSymbol(IntEnum):
    DCH_START_SYMBOL    = 0x5B #  [
    DCH_END_SYMBOL      = 0x5D #  ]

class DchType(IntEnum):
    DCH_TYPE_PTI_TX     = 0x29
    DCH_TYPE_PTI_RX     = 0x2A
    DCH_TYPE_PTI_OTHER  = 0x2B

DCH_TYPES = [ DchType.DCH_TYPE_PTI_TX, DchType.DCH_TYPE_PTI_RX, DchType.DCH_TYPE_PTI_OTHER ]

#
#       DCH frame start symbol is always 0x5D -> [
#       DCH frame stop symbol is always 0x5D -> ]
#       Payload is variable in size and can be empty/omitted
#
#                          DCHv2 frame (min size is 15 bytes)
#     0               1               2               3
#     0 1 2 3 4 5 6 7 0 1 2 3 4 5 6 7 0 1 2 3 4 5 6 7 0 1 2 3 4 5 6 7
#    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
#    | Start Symbol  |            Length             |     Version
#    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
#                    |          Timestamp
#    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
#                                                    |    DCH Type
#    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
#                    |  Seq. Number  |    Payload    |  Stop Symbol  |
#    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
#
#                          DCHv3 frame (min size is 22 bytes)
#     0               1               2               3
#     0 1 2 3 4 5 6 7 0 1 2 3 4 5 6 7 0 1 2 3 4 5 6 7 0 1 2 3 4 5 6 7
#    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
#    | Start Symbol  |            Length             |     Version
#    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
#                    |
#    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
#                                Timestamp
#    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
#                    |          DCH Type             |
#    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
#                        Flags                       |    Sequence
#    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
#         Number     |             Payload           |  Stop Symbol  |
#    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
#
@dataclass
class DchPacket:
    # a TCP packet on from port 4905 can contain multiple DCH frames.
    frames: list[DchFrame]

    @classmethod
    def from_bytes(cls, packet: bytes) -> DchPacket | None:
        frames: list[DchFrame] = []

        # sanity check on the given packet, this should never happen in normal conditions
        if len(packet) == 0:
            return None

        if packet[0] != DchSymbol.DCH_START_SYMBOL or packet[-1] != DchSymbol.DCH_END_SYMBOL:
            # this packet is not DCH
            return None

        cur_dch_frame_length = 0
        while len(packet) > cur_dch_frame_length:
            frame = DchFrame.from_bytes(packet[cur_dch_frame_length:])
            if frame is None:
                # the DCH frame parser failed to parse this packet. Abort.
                return None
            frames.append(frame)
            cur_dch_frame_length += frame.length

        return cls(frames=frames)

@dataclass
class DchFrame:
    start_symbol: int
    length: int # the length stored here will take into account the start and stop symbol, which is not the case with the real frame.
    version: int
    timestamp: int # either in microseconds (DCHv2) or nanoseconds (DCHv3) -> IMPORTANT: DCH timestamp are the amount of time elapsed since first boot of the WPK
    dch_type: int
    flags: int | None # not in DCHv2
    sequence_number: int
    payload: PtiFrame # the payload can be something other than pti but for now we only care about that
    stop_symbol: int

    def get_timestamp_us(self) -> int:
        if self.version == 2:
            return self.timestamp
        elif self.version == 3:
            return self.timestamp // (10 ** 3)
        else:
            raise Exception(f"version {self.version} is not supported")

    def get_timestamp_ns(self) -> int:
        if self.version == 2:
            return self.timestamp * (10 ** 3)
        elif self.version == 3:
            return self.timestamp
        else:
            raise Exception(f"version {self.version} is not supported")

    @classmethod
    def from_bytes(cls, frame: bytes) -> DchFrame | None:
        start_symbol: int
        length: int
        version: int
        timestamp: int
        dch_type: int
        flags: int | None
        sequence_number: int
        payload: PtiFrame | None
        stop_symbol: int

        # will be used to track our current position in the frame
        current_index: int = 0

        # sanity check on the given frame, this should never happen in normal conditions
        if len(frame) == 0:
            return None

        start_symbol, length, version = struct.unpack("<BHH", frame[current_index:5])
        current_index += 5

        # check if it's a valid DCH frame before going any further
        if start_symbol != DchSymbol.DCH_START_SYMBOL:
            return None

        # the DCH length field does not take into account the start and stop symbols
        # so we update the given length to take them into account.
        length = length+2
        # check that the given frame matches at least the given length
        if len(frame) < length:
            _logger.debug("DCH frame length mismatch")
            return None

        # retrieve end symbol now to check if it's a valid DCH frame before going any further
        stop_symbol = frame[length-1]
        if stop_symbol != DchSymbol.DCH_END_SYMBOL:
            return None

        # check the DCH version
        if version == 2:
            if length <= 15:
                # a DCHv2 frame is 15 bytes in length at minimum, if it there won't be a payload afterward
                return None
            flags = None # there's no flag
            timestamp, dch_type, sequence_number = struct.unpack("<6sHB", frame[current_index:current_index + 9])
            current_index += 9

        elif version == 3:
            if length <= 22:
                # a DCHv3 frame is 22 bytes in length at minimum,  there won't be a payload afterward
                return None
            timestamp, dch_type, flags, sequence_number = struct.unpack("<QHIH", frame[current_index:current_index + 16])
            current_index += 16
        else:
            _logger.debug("DCH frame version unsupported")
            return None

        # we don't care about stuff not related to PTI
        if dch_type not in DCH_TYPES:
            return None

        payload = PtiFrame.from_bytes(frame[current_index:length-1])
        if payload is None:
            return None

        return cls(
            start_symbol=start_symbol,
            length=length,
            version=version,
            timestamp=timestamp,
            dch_type=dch_type,
            flags=flags,
            sequence_number=sequence_number,
            payload=payload,
            stop_symbol=stop_symbol
        )

class PtiHwStartType(IntEnum):
    PTI_HW_START_RX_START   = 0xF8
    PTI_HW_START_RX_END     = 0xFC

class PtiHwEndType(IntEnum):
    PTI_HW_END_RX_SUCCESS   = 0xF9
    PTI_HW_END_RX_ABORT     = 0xFA
    PTI_HW_END_TX_SUCCESS   = 0xFD
    PTI_HW_END_TX_ABORT     = 0xFE

class PtiProtocolID(IntEnum):
    PTI_PROTOCOL_ID_ZWAVE   = 0x06

class PtiRxErrorCodeZwave(IntEnum):
    PTI_RX_ERROR_CODE_SUCCESS               = 0x0  # Success
    PTI_RX_ERROR_CODE_CRC_ERROR             = 0x1  # CRC Failed or invalid packet length, Packet had a CRC error. This is the only case when we know for sure that the packet was corrupted.
    PTI_RX_ERROR_CODE_DROPPED               = 0x2  # Dropped/Overflow, Packet was dropped for reasons other than the other errors, including Rx overflow.  E.g. Packets that appear successful but ended prematurely during filtering are dropped.
    # PTI_RX_ERROR_CODE_RESERVED            = 0x3
    PTI_RX_ERROR_CODE_ADDRESS_FILTERED      = 0x4  # Packet was not addressed to this node. For Z-Wave, this refers to the HomeId only.
    # PTI_RX_ERROR_CODE_RESERVED            = 0x5
    # PTI_RX_ERROR_CODE_RESERVED            = 0x6
    # PTI_RX_ERROR_CODE_RESERVED            = 0x7
    # PTI_RX_ERROR_CODE_RESERVED            = 0x8
    # PTI_RX_ERROR_CODE_RESERVED            = 0x9
    # PTI_RX_ERROR_CODE_RESERVED            = 0xA
    PTI_RX_ERROR_CODE_ZWAVE_BEAM_ACCEPTED   = 0xB  # Packet was a Z-Wave Beam packet deemed pertinent to the receiving node (despite being filtered).
    PTI_RX_ERROR_CODE_ZWAVE_BEAM_IGNORED    = 0xC  # Packet was a Z-Wave Beam packet filtered as not pertinent to the receiving node.
    # PTI_RX_ERROR_CODE_RESERVED            = 0xD
    PTI_RX_ERROR_CODE_USER_ABORT            = 0xE
    # PTI_RX_ERROR_CODE_RESERVED            = 0xF

class PtiTxErrorCodeZwave(IntEnum):
    PTI_TX_ERROR_CODE_SUCCESS       = 0x0
    PTI_TX_ERROR_CODE_ABORT         = 0x1
    PTI_TX_ERROR_CODE_UNDERFLOW     = 0x2
    PTI_TX_ERROR_CODE_USER_ABORT    = 0x3
    # PTI_RX_ERROR_CODE_RESERVED    = 0x4
    # PTI_RX_ERROR_CODE_RESERVED    = 0x5
    # PTI_RX_ERROR_CODE_RESERVED    = 0x6
    # PTI_RX_ERROR_CODE_RESERVED    = 0x7
    # PTI_RX_ERROR_CODE_RESERVED    = 0x8
    # PTI_RX_ERROR_CODE_RESERVED    = 0x9
    # PTI_RX_ERROR_CODE_RESERVED    = 0xA
    # PTI_RX_ERROR_CODE_RESERVED    = 0xB
    # PTI_RX_ERROR_CODE_RESERVED    = 0xC
    # PTI_RX_ERROR_CODE_RESERVED    = 0xD
    # PTI_RX_ERROR_CODE_RESERVED    = 0xE
    # PTI_RX_ERROR_CODE_RESERVED    = 0xF

class PtiZwaveRegionId(IntEnum):
    PTI_ZWAVE_REGION_ID_UNKNOWN = 0x00 # Unknown
    PTI_ZWAVE_REGION_ID_EU      = 0x01 # European Union
    PTI_ZWAVE_REGION_ID_US      = 0x02 # United States
    PTI_ZWAVE_REGION_ID_ANZ     = 0x03 # Australia/New Zealand
    PTI_ZWAVE_REGION_ID_HK      = 0x04 # Hong Kong
    PTI_ZWAVE_REGION_ID_MA      = 0x05 # Malaysia
    PTI_ZWAVE_REGION_ID_IN      = 0x06 # India
    PTI_ZWAVE_REGION_ID_JP      = 0x07 # Japan
    PTI_ZWAVE_REGION_ID_RU      = 0x08 # Russian Federation
    PTI_ZWAVE_REGION_ID_IS      = 0x09 # Israel
    PTI_ZWAVE_REGION_ID_KR      = 0x0A # Korea
    PTI_ZWAVE_REGION_ID_CN      = 0x0B # China
    PTI_ZWAVE_REGION_ID_US_LR1  = 0x0C # United States Long Range 1
    PTI_ZWAVE_REGION_ID_US_LR2  = 0x0D # United States Long Range 2
    PTI_ZWAVE_REGION_ID_US_LR3  = 0x0E # United States Long Range 3 (also named EndDevice)
    PTI_ZWAVE_REGION_ID_EU_LR1  = 0x0F # Europe Long Range 1
    PTI_ZWAVE_REGION_ID_EU_LR2  = 0x10 # Europe Long Range 2
    PTI_ZWAVE_REGION_ID_EU_LR3  = 0x11 # Europe Long Range 3 (also named EndDevice)

@dataclass
class PtiRadioConfigZwave:
    # b7 b6 b5 are always set to 0
    z_wave_region_id: int # 5 bits (b4 b3 b2 b1 b0)

@dataclass
class PtiRadioInfo:
    is_antenna_selected: int    # 1 bit (b7)
    is_syncword_selected: int   # 1 bit (b6)
    channel_number: int         # 6 bits (b5 b4 b3 b2 b1 b0)

@dataclass
class PtiStatus0:
    error_code: int     # 4 bits (b7 b6 b5 b4)
    protocol_id: int    # 4 bits (b3 b2 b1 b0)

@dataclass
class PtiAppendedInfoCfg:
    # b7 is always set to 0
    is_rx: int      # 1 bit (b6) -> Rx = 1, Tx = 0
    length: int     # 3 bits (b5 b4 b3) -> actual length - 2
    version: int    # 3 bits (b2 b1 b0) -> from version 1 onward the RSSI (Rx only) will have to be compensated by subtracting 0x32 to get the actual RSSI

# at most the PTI appended info is 10 bytes in size, for Z-Wave it will only be 5 bytes maximum (Rx) and 4 bytes maximum (Tx)
@dataclass
class PtiAppendedInfo:
    rssi: int | None                        # 1 byte -> Rx only
    # syncword: int                         # 4 bytes -> BLE only, Rx and Tx
    radio_config: PtiRadioConfigZwave       # 0/1/2 bytes -> different for every protocol, we're only interested in Z-Wave, and for Z-Wave it's 1 byte long
    radio_info: PtiRadioInfo                # 1 byte
    status_0: PtiStatus0                    # 1 byte
    appended_info_cfg: PtiAppendedInfoCfg   # 1 byte

@dataclass
class PtiFrame:
    hw_start: int                       # 1 byte
    ota_packet_data: bytes              # variable size
    hw_end: int                         # 1 byte
    appended_info: PtiAppendedInfo      # variable size

    @classmethod
    def from_bytes(cls, frame: bytes) -> PtiFrame | None:

        # sanity check
        if len(frame) < 6: # 6 is the minimum possible size for a Z-Wave PTI frame (hw_start + no ota_packet_data + hw_end + appended_info = 1 + 0 + 1 + 4 = 6).
            return None

        # we must parse the PTI frame backward because appended_info contains information on the radio frame.
        current_index: int = -1

        # APPENDED_INFO (variable size)

        # APPENDED_INFO_CFG (1 byte)
        pti_appended_info_cfg = PtiAppendedInfoCfg(
            is_rx=      (frame[current_index] & 0b01000000) >> 6,
            length=     (frame[current_index] & 0b00111000) >> 3,
            version=    (frame[current_index] & 0b00000111) >> 0
        )
        current_index -= 1

        # STATUS_0 (1 byte)
        pti_status0 = PtiStatus0(
            error_code=     (frame[current_index] & 0b11110000) >> 4,
            protocol_id=    (frame[current_index] & 0b00001111) >> 0
        )
        current_index -= 1

        # we should not go any further if protocol_id does not match Z-Wave
        if pti_status0.protocol_id != PtiProtocolID.PTI_PROTOCOL_ID_ZWAVE:
            return None

        # RADIO_INFO (1 byte)
        pti_radio_info = PtiRadioInfo(
            is_antenna_selected=    (frame[current_index] & 0b10000000) >> 7,
            is_syncword_selected=   (frame[current_index] & 0b01000000) >> 6,
            channel_number=         (frame[current_index] & 0b00111111) >> 0
        )
        current_index -= 1

        # RADIO_CONFIG (0/1/2 byte(s)) it's 1 byte for Z-Wave
        pti_radio_config = PtiRadioConfigZwave(
            z_wave_region_id=        (frame[current_index] & 0b00011111) >> 0
        )
        current_index -= 1

        # RSSI (0/1 byte) depends on pti_appended_info_cfg.is_rx
        rssi = 0
        if pti_appended_info_cfg.is_rx == 1:
            rssi = frame[current_index]
            if pti_appended_info_cfg.version >= 1:
                rssi -= 0x32
            current_index -= 1

        pti_appended_info = PtiAppendedInfo(
            rssi=rssi,
            radio_config=pti_radio_config,
            radio_info=pti_radio_info,
            status_0=pti_status0,
            appended_info_cfg=pti_appended_info_cfg
        )

        # HW_END (1 byte)
        # We're only interested in Rx Success and Tx Success, so 0xF9 and 0xFD
        hw_end = frame[current_index]
        # we don't decrement current_index here because in Python when using this syntax: `[left_operand:right_operand]`
        # to extract part of a list the right_operand is excluded.

        # OTA_PACKET_DATA (variable size)
        ota_packet_data = frame[1:current_index]

        # HW_START (1 byte)
        hw_start = frame[0]

        return cls(
            hw_start=hw_start,
            ota_packet_data=ota_packet_data,
            hw_end=hw_end,
            appended_info=pti_appended_info
        )