from __future__ import annotations
from dataclasses import dataclass
from enum import IntEnum
import struct
import logging

from .definitions import DchSymbol, PtiDchTypes, PtiProtocolID

_logger = logging.getLogger(__name__)


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

        if packet[0] != DchSymbol.START or packet[-1] != DchSymbol.END:
            # this packet is not DCH
            return None

        cur_dch_frame_length = 0
        while len(packet) > cur_dch_frame_length:
            frame = DchFrame.from_bytes(packet[cur_dch_frame_length:])
            if frame is None:
                # the DCH frame parser failed to parse this packet. Abort.
                return None
            frames.append(frame)
            cur_dch_frame_length += len(frame)

        return cls(frames=frames)

    def to_bytes(self) -> bytes:
        packet: bytes = bytes()
        for frame in self.frames:
            packet += frame.to_bytes()
        return packet


@dataclass
class DchFrame:
    start_symbol: int
    length: int  # the length stored here will take into account the start and stop symbol, which is not the case with the real frame.
    version: int  # we only support version 2 and 3
    timestamp: int  # either in microseconds (DCHv2) or nanoseconds (DCHv3) -> IMPORTANT: DCH timestamp are the amount of time elapsed since first boot of the WPK
    dch_type: int  # determines the type of DCH frame, we're only looking for PTI.
    flags: int | None  # not in DCHv2
    sequence_number: int
    payload: PtiFrame  # the payload can be something other than pti but for now we only care about that
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
    def get_v2_header_size(cls) -> int:
        # a DCHv2 frame header is 13 bytes in length (not taking into account the DCH start/end symbols and the payload)
        return 13

    @classmethod
    def get_v3_header_size(cls) -> int:
        # a DCHv3 frame header is 20 bytes in length (not taking into account the DCH start/end symbols and the payload)
        return 20

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
        if start_symbol != DchSymbol.START:
            return None

        # check that the given frame matches at least the total length, +2 is added to length because
        # the DCH length field does not take into account the start and stop symbols
        if len(frame) < length + 2:
            _logger.debug("DCH frame length mismatch")
            return None

        # retrieve end symbol now to check if it's a valid DCH frame before going any further
        stop_symbol_index = length + 1 # +1 to take into account the DCH start symbol
        stop_symbol = frame[stop_symbol_index]
        if stop_symbol != DchSymbol.END:
            return None

        # check the DCH version
        if version == 2:
            if length <= DchFrame.get_v2_header_size():
                # no payload to parse
                return None
            flags = None  # there's no flag
            timestamp, dch_type, sequence_number = struct.unpack("<6sHB", frame[current_index:current_index + 9])
            current_index += 9

        elif version == 3:
            if length <= DchFrame.get_v3_header_size():
                # no payload to parse
                return None
            timestamp, dch_type, flags, sequence_number = struct.unpack("<QHIH",
                                                                        frame[current_index:current_index + 16])
            current_index += 16
        else:
            _logger.debug("DCH frame version unsupported")
            return None

        # we don't care about stuff not related to PTI
        if dch_type not in PtiDchTypes:
            return None

        payload = PtiFrame.from_bytes(frame[current_index:stop_symbol_index]) # stop symbol is excluded
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

    def to_bytes(self) -> bytes:
        frame = struct.pack("<BHH", self.start_symbol, self.length, self.version)
        if self.version == 2:
            frame += struct.pack("<6sHB", self.timestamp, self.dch_type, self.sequence_number)
        elif self.version == 3:
            frame += struct.pack("<QHIH", self.timestamp, self.dch_type, self.flags, self.sequence_number)
        else:
            raise Exception(f"unsupported DCH version: {self.version}")
        frame += self.payload.to_bytes()
        frame += struct.pack("<B", self.stop_symbol)

        return frame

    def __len__(self):
        return self.length + 2 # + 2 to take into account the start and stop symbols.


@dataclass
class PtiRadioConfigZwave:
    # b7 b6 b5 are always set to 0
    z_wave_region_id: int  # 5 bits (b4 b3 b2 b1 b0)

    @classmethod
    def from_int(cls, data: int) -> PtiRadioConfigZwave:
        return PtiRadioConfigZwave(
            z_wave_region_id=   (data & 0b00011111) >> 0
        )

    def to_int(self) -> int:
        return int(
            ((self.z_wave_region_id & 0b00011111) << 0)
        )


@dataclass
class PtiRadioInfo:
    is_antenna_selected: int  # 1 bit (b7)
    is_syncword_selected: int  # 1 bit (b6)
    channel_number: int  # 6 bits (b5 b4 b3 b2 b1 b0)

    @classmethod
    def from_int(cls, data: int) -> PtiRadioInfo:
        return PtiRadioInfo(
            is_antenna_selected=    (data & 0b10000000) >> 7,
            is_syncword_selected=   (data & 0b01000000) >> 6,
            channel_number=         (data & 0b00111111) >> 0
        )

    def to_int(self) -> int:
        return int(
            ((self.is_antenna_selected  & 0b00000001) << 7) +
            ((self.is_syncword_selected & 0b00000001) << 6) +
            ((self.channel_number       & 0b00111111) << 0)
        )


@dataclass
class PtiStatus0:
    error_code: int  # 4 bits (b7 b6 b5 b4)
    protocol_id: int  # 4 bits (b3 b2 b1 b0)

    @classmethod
    def from_int(cls, data: int) -> PtiStatus0:
        return PtiStatus0(
            error_code=     (data & 0b11110000) >> 4,
            protocol_id=    (data & 0b00001111) >> 0
        )

    def to_int(self) -> int:
        return int(
            ((self.error_code   & 0b00001111) << 4) +
            ((self.protocol_id  & 0b00001111) << 0)
        )


@dataclass
class PtiAppendedInfoCfg:
    # b7 is always set to 0
    is_rx: int  # 1 bit (b6) -> Rx = 1, Tx = 0
    length: int # 3 bits (b5 b4 b3) -> Size of APPENDED_INFO - 3 (I think that's because APPENDED_INFO_CFG, STATUS_0 and RADIO_INFO are mandatory)
    version: int  # 3 bits (b2 b1 b0) -> from version 1 onward the RSSI (Rx only) will have to be compensated by subtracting 0x32 to get the actual RSSI

    @classmethod
    def from_int(cls, data: int) -> PtiAppendedInfoCfg:
        return PtiAppendedInfoCfg(
            is_rx=      (data & 0b01000000) >> 6,
            length=     (data & 0b00111000) >> 3,
            version=    (data & 0b00000111) >> 0
        )

    def to_int(self) -> int:
        return int(
            ((self.is_rx    & 0b00000001) << 6) +
            ((self.length   & 0b00000111) << 3) +
            ((self.version  & 0b00000111) << 0)
        )


@dataclass
class PtiAppendedInfo:
    rssi: int # 1 byte -> Rx only (not present in Tx, we set it to 0 for convenience when manipulating this dataclass, we omit it when using to_bytes)
    # syncword: int                         # 4 bytes -> BLE only, Rx and Tx
    radio_config: PtiRadioConfigZwave  # 0/1/2 bytes -> different for every protocol, we're only interested in Z-Wave, and for Z-Wave it's 1 byte long
    radio_info: PtiRadioInfo  # 1 byte
    status_0: PtiStatus0  # 1 byte
    appended_info_cfg: PtiAppendedInfoCfg  # 1 byte

    @classmethod
    def from_bytes(cls, frame: bytes) -> PtiAppendedInfo | None:
        # we must parse the PTI frame backward because appended_info contains information on the radio frame.
        current_index: int = -1

        # APPENDED_INFO_CFG (1 byte)
        pti_appended_info_cfg = PtiAppendedInfoCfg.from_int(frame[current_index])
        current_index -= 1

        # STATUS_0 (1 byte)
        pti_status0 = PtiStatus0.from_int(frame[current_index])
        current_index -= 1

        # we should not go any further if protocol_id does not match Z-Wave
        if pti_status0.protocol_id != PtiProtocolID.ZWAVE:
            return None

        # RADIO_INFO (1 byte)
        pti_radio_info = PtiRadioInfo.from_int(frame[current_index])
        current_index -= 1

        # RADIO_CONFIG (0/1/2 byte(s)) it's 1 byte for Z-Wave
        pti_radio_config = PtiRadioConfigZwave.from_int(frame[current_index])
        current_index -= 1

        # RSSI (0/1 byte) depends on pti_appended_info_cfg.is_rx
        rssi = None
        if pti_appended_info_cfg.is_rx == 1:
            rssi = frame[current_index]

        return PtiAppendedInfo(
            rssi=rssi,
            radio_config=pti_radio_config,
            radio_info=pti_radio_info,
            status_0=pti_status0,
            appended_info_cfg=pti_appended_info_cfg
        )

    def to_bytes(self) -> bytes:
        appended_info_values = [
            self.radio_config.to_int(),
            self.radio_info.to_int(),
            self.status_0.to_int(),
            self.appended_info_cfg.to_int()
        ]
        if self.rssi:
            appended_info_values.insert(0, self.rssi) # add RSSI at the start
        return bytes(appended_info_values)

    def  __len__(self) -> int:
        # at most the PTI appended info is 10 bytes in size,
        # for Z-Wave it will only be 5 bytes maximum (Rx) and 4 bytes maximum (Tx)
        return self.appended_info_cfg.length + 3 # 3 bytes are mandatory (APPENDED_INFO_CFG, STATUS_0 and RADIO_INFO)

    def get_rssi_value(self) -> int:
        if not self.rssi:
            return 0 # Tx
        if self.appended_info_cfg.version >= 1:
            return self.rssi - 0x32 # since PTI version 1 and onward the RSSI must be offset by 0x32
        return self.rssi


@dataclass
class PtiFrame:
    hw_start: int  # 1 byte
    ota_packet_data: bytes  # variable size
    hw_end: int  # 1 byte
    appended_info: PtiAppendedInfo  # variable size

    @classmethod
    def from_bytes(cls, frame: bytes) -> PtiFrame | None:

        # sanity check
        if len(frame) < 6:  # 6 is the minimum possible size for a Z-Wave PTI frame (hw_start + no ota_packet_data + hw_end + appended_info = 1 + 0 + 1 + 4 = 6).
            return None

        # we must parse the PTI frame backward because PTI appended_info contains crucial information about the encapsulated frame.

        # APPENDED_INFO (variable size)
        pti_appended_info = PtiAppendedInfo.from_bytes(frame)
        if pti_appended_info is None:
            # parsing of PtiAppendedInfo failed
            return None

        # HW_END (1 byte)
        hw_end_position = -1 - len(pti_appended_info) # to get the position of HW_END we must subtract 1 to the length of the appended_info
        # We're only interested in Rx Success and Tx Success, so 0xF9 and 0xFD
        hw_end = frame[hw_end_position]

        # OTA_PACKET_DATA (variable size)
        ota_packet_data = frame[1:hw_end_position] # in Python when using this syntax: `[left_operand:right_operand]` to extract part of a list the right_operand is excluded.

        # HW_START (1 byte)
        hw_start = frame[0]

        return cls(
            hw_start=hw_start,
            ota_packet_data=ota_packet_data,
            hw_end=hw_end,
            appended_info=pti_appended_info
        )

    def to_bytes(self) -> bytes:
        frame = struct.pack("<B", self.hw_start)
        frame += self.ota_packet_data
        frame += struct.pack("<B", self.hw_end)
        frame += self.appended_info.to_bytes()
        return frame

    def  __len__(self) -> int:
        return len(self.ota_packet_data) + len(self.appended_info) + 2 # + 2 because of the HW_START and HW_END symbols
