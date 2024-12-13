import struct
from pathlib import Path

from .parsers import DchPacket
from .definitions import RAILZwaveRegions, ZwavePCAPDataRate, RAILZwaveRegionID_to_ZwavePCAPRegionID, RAILZwaveBaud_to_ZwavePCAPDataRate


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
                pcap_region_id = RAILZwaveRegionID_to_ZwavePCAPRegionID[rail_region_id]
                pcap_data_rate = RAILZwaveBaud_to_ZwavePCAPDataRate[rail_baud]
                pcap_frequency = rail_region.channels[rail_channel_number].frequency
                # FCS: 1 for R1 and R2, 2 for R3
                # TODO: create an enum or a map for that instead of hardcoded values
                pcap_fcs = 2 if pcap_data_rate == ZwavePCAPDataRate.R3.value else 1
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
                        0,                      # Type = FCS (0)
                        1,                          # length of FCS TLV = 1
                        pcap_fcs,                   # FCS Type
                        int(0).to_bytes(length=3)   # padding (0)
                    )
                )

                # Receive Signal Strength
                file.write(
                    struct.pack(
                        "<HHf",
                        1,      # Type = RSS (1)
                        4,          # length of RSS TLV = 1
                        pcap_rss    # RSS in dBm
                    )
                )

                # Radio Frequency Information
                file.write(
                    struct.pack(
                        "<HHHHI",
                        2,          # Type = RF INFO (2)
                        8,              # length of RF INFO TLV = 8
                        pcap_region_id, # Region
                        pcap_data_rate, # Data Rate
                        pcap_frequency  # Frequency in kHzs
                    )
                )

                # Z-Wave payload
                file.write(frame.payload.ota_packet_data)
