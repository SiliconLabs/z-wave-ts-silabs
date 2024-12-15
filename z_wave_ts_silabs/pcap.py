import struct
from pathlib import Path
from dataclasses import dataclass

from .parsers import DchPacket
from .definitions import ZwavePcapTapTLVType, ZwavePcapFcsType, ZwavePcapRegionID, RAILZwaveRegions, ZwavePcapDataRate, \
    RAILZwaveRegionID_to_ZwavePcapRegionID, RAILZwaveBaud_to_ZwavePcapDataRate

_PCAP_HEADER_SIZE: int = 24
_PCAP_HEADER: bytes = struct.pack(
    "<IHHQII",
    0xA1B2C3D4,  # Magic Number (4 bytes) 0xA1B2C3D4 -> s and us | 0xA1B23C4D -> s and ns
    2,               # Major version (2 bytes) the current standard is 2
    4,               # Minor version (2 bytes) the current standard is 4
    0,               # Reserved 1 (4 bytes) and Reserved 2 (4 bytes) both set to 0
    4096,            # SnapLen (4 bytes) max number of octets captured from each packet, must not be 0
    297              # LinkType and additional information (4 bytes), we only set the link type to LINKTYPE_ZWAVE_TAP: 297
)
_PCAP_ZWAVE_TAP_HEADER_AND_TLVS_SIZE: int = 32 # 32 is TAP header + TAP TLVs


@dataclass
class PcapZwavePacket:
    fcs: int
    rss: float
    region_id: int
    data_rate: int
    frequency: int
    zwave_packet: bytes

    @staticmethod
    def csv_str_format() -> str:
        """returns the name of the csv columns used by the __str__ method of this class"""
        return "fcs, rss, region_id, data_rate, frequency, zwave_packet"

    def __str__(self) -> str:
        return f"{self.fcs:01}, {self.rss: 06.1f}, {ZwavePcapRegionID(self.region_id).name}, {ZwavePcapDataRate(self.data_rate).name}, {self.frequency}, {self.zwave_packet.hex(' ')}"


class PcapFileWriter(object):
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self._create()

    def _create(self):
        """Creates a new pcap file."""
        # we follow this specification: https://ietf-opsawg-wg.github.io/draft-ietf-opsawg-pcap/draft-ietf-opsawg-pcap.html#name-general-file-structure
        with open(self.file_path, 'wb') as file:
            file.write(_PCAP_HEADER)

    def write_packet(self, dch_packet: DchPacket, reference_time: int):
        """Dumps frame to pcap file.
        :param dch_packet: parsed DCH packet from WSTK/WPK/TB containing Z-Wave frames
        :param reference_time: reference time
        """
        if dch_packet is None:
            return

        with open(self.file_path, 'ab') as file:
            for frame in dch_packet.frames:
                # extract RAIL radio information
                rail_region_id = frame.payload.appended_info.radio_config.z_wave_region_id
                rail_channel_number = frame.payload.appended_info.radio_info.channel_number
                rail_region = RAILZwaveRegions[rail_region_id]
                rail_baud = rail_region.channels[rail_channel_number].baud
                rail_rssi = frame.payload.appended_info.get_rssi_value()
                # convert RAIL radio information to PCAP format
                pcap_region_id = RAILZwaveRegionID_to_ZwavePcapRegionID[rail_region_id]
                pcap_data_rate = RAILZwaveBaud_to_ZwavePcapDataRate[rail_baud]
                pcap_frequency = rail_region.channels[rail_channel_number].frequency
                # FCS: NON_CORRECTING_FCS_8_BIT for R1 and R2, CRC_CCITT_16_BIT for R3
                pcap_fcs = ZwavePcapFcsType.CRC_CCITT_16_BIT.value if pcap_data_rate == ZwavePcapDataRate.R3.value else ZwavePcapFcsType.NON_CORRECTING_FCS_8_BIT.value
                pcap_rss = float(rail_rssi)

                # https://ietf-opsawg-wg.github.io/draft-ietf-opsawg-pcap/draft-ietf-opsawg-pcap.html#name-packet-record
                cur_time = (reference_time + frame.timestamp)
                cur_time_second = cur_time // (10 ** 6)
                cur_time_microsecond = cur_time % (10 ** 6)
                packet_length = _PCAP_ZWAVE_TAP_HEADER_AND_TLVS_SIZE + len(frame.payload.ota_packet_data)

                # PCAP Packet Record
                file.write(
                    struct.pack(
                        "<IIII",
                        cur_time_second,    # Timestamp (seconds)
                        cur_time_microsecond,   # Timestamp (microseconds)
                        packet_length,          # Captured packet length
                        packet_length           # Original packet length
                    )
                )

                # PCAP Packet Data
                # TAP header
                file.write(
                    struct.pack(
                        "<BBH",
                        1,  # version
                        0,      # reserved (0)
                        7       # length of TLVs section (7 32bit words with all 3 TLVs)
                    )
                )

                # TAP TLVs
                # Frame Check Sequence
                file.write(
                    struct.pack(
                        "<HHB3s",
                        ZwavePcapTapTLVType.FCS.value,      # Type = FCS (0)
                        1,                                  # length of FCS TLV = 1
                        pcap_fcs,                           # FCS Type
                        int(0).to_bytes(length=3)           # padding (0)
                    )
                )

                # Receive Signal Strength
                file.write(
                    struct.pack(
                        "<HHf",
                        ZwavePcapTapTLVType.RSS.value,      # Type = RSS (1)
                        4,                                  # length of RSS TLV = 4
                        pcap_rss                            # RSS in dBm
                    )
                )

                # Radio Frequency Information
                file.write(
                    struct.pack(
                        "<HHHHI",
                        ZwavePcapTapTLVType.RF_INFO.value,  # Type = RF INFO (2)
                        8,                                  # length of RF INFO TLV = 8
                        pcap_region_id,                     # Region
                        pcap_data_rate,                     # Data Rate
                        pcap_frequency                      # Frequency in kHzs
                    )
                )

                # Z-Wave payload
                file.write(frame.payload.ota_packet_data)


class PcapFileReader(object):
    def __init__(self, file_path: Path):
        self.file_path = file_path
        if not self.file_path.exists():
            raise FileNotFoundError
        self.packets = self._open()
        self.current_index = 0

    def _open(self) -> bytes:
        with open(self.file_path, 'rb') as file:
            file_content = file.read()
            assert file_content[:_PCAP_HEADER_SIZE] == _PCAP_HEADER
            return file_content[_PCAP_HEADER_SIZE:]

    def read_packet(self) -> PcapZwavePacket | None:
        if self.current_index >= len(self.packets):
            return None

        time_second, time_microsecond, captured_packet_length, original_packet_length = struct.unpack(
            "<IIII",
            self.packets[self.current_index:self.current_index + 16]
        )
        self.current_index += 16

        version, reserved, tlv_section_length = struct.unpack(
            "<BBH",
            self.packets[self.current_index:self.current_index + 4]
        )
        self.current_index += 4

        # the TLV section length is the number of 32-bit lines in the following TLV block
        tlv_section_length_in_bytes = tlv_section_length * 4
        tlv_section_ending_index = self.current_index + tlv_section_length_in_bytes

        fcs: int = 0
        rss: float = 0
        region_id: int = 0
        data_rate: int = 0
        frequency: int = 0

        while self.current_index < tlv_section_ending_index:
            tlv_type, tlv_length = struct.unpack(
                "<HH",
                self.packets[self.current_index:self.current_index + 4]
            )
            self.current_index += 4
            if tlv_type == ZwavePcapTapTLVType.FCS.value:
                fcs, _ = struct.unpack(
                    "<B3s",
                    self.packets[self.current_index:self.current_index + 4]
                )
                self.current_index += 4  # 1 + 3 bytes of padding
            elif tlv_type == ZwavePcapTapTLVType.RSS.value:
                rss, = struct.unpack(
                    "<f",
                    self.packets[self.current_index:self.current_index + 4]
                )
                self.current_index += 4
            elif tlv_type == ZwavePcapTapTLVType.RF_INFO.value:
                region_id, data_rate, frequency = struct.unpack(
                    "<HHI",
                    self.packets[self.current_index:self.current_index + 8]
                )
                self.current_index += 8
            else:
                raise Exception("Unknown TLV type")

        payload_length = captured_packet_length - _PCAP_ZWAVE_TAP_HEADER_AND_TLVS_SIZE
        payload = self.packets[self.current_index:self.current_index + payload_length]
        self.current_index += payload_length

        return PcapZwavePacket(
            fcs=fcs,
            rss=rss,
            region_id=region_id,
            data_rate=data_rate,
            frequency=frequency,
            zwave_packet=payload
        )
