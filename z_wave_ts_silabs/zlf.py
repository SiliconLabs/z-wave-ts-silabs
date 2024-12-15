import time
from pathlib import Path
from datetime import datetime

from .parsers import DchPacket

# ZLF is used by Zniffer and Zniffer is a C# app thus:
# https://learn.microsoft.com/en-us/dotnet/api/system.datetime.ticks?view=net-8.0#remarks
# since C# stores ticks and a tick occurs every 100ns according to the above link,
# we need to offset each timestamp with the base unix timestamp,
# which should be equal to: January 1, 1970 12:00:00 AM (or 00:00:00 in 24h format)
_BASE_UNIX_TIMESTAMP_IN_TICKS = int((datetime.fromtimestamp(0) - datetime.min).total_seconds() * 10_000_000)

_ZLF_HEADER_SIZE: int = 2048
_ZLF_HEADER: bytes = bytes([0x68] + [0x00] * (_ZLF_HEADER_SIZE-3) + [0x23, 0x12])

_ZLF_DATACHUNK_HEADER_SIZE: int = 5
_ZLF_API_TYPE_ZNIFFER: int = 0xF5


class ZlfFileWriter(object):
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self._create()

    def _create(self):
        """Creates a new zlf file."""
        with open(self.file_path, "wb") as file:
            file.write(_ZLF_HEADER)

    def write_datachunk(self, dch_packet: bytes):
        """Dumps frame to ZLF file.
        :param dch_packet: DCH packet directly from WSTK/WPK/TB
        """
        # Hacky timestamp stuff from C# datetime format. a Datetime format is made of a kind part on 2 bits
        # and a tick part on the remainder 62 bits.

        # convert nanoseconds to ticks.
        zlf_timestamp = time.time_ns() // 100
        # set the kind to: UTC https://learn.microsoft.com/en-us/dotnet/api/system.datetimekind?view=net-8.0#fields
        zlf_timestamp |= (1 << 63)
        # add base unix timestamp in tick to current
        zlf_timestamp += _BASE_UNIX_TIMESTAMP_IN_TICKS
        with open(self.file_path, "ab") as file:
            data_chunk = bytearray()
            data_chunk.extend(zlf_timestamp.to_bytes(8, 'little'))
            # properties: 0x00 is RX | 0x01 is TX (but we set it to 0x00 all the time)
            data_chunk.append(0x00)
            data_chunk.extend((len(dch_packet)).to_bytes(4, 'little'))
            data_chunk.extend(dch_packet)
            # api_type: some value in Zniffer, it has to be there, 0xF5 is for PTI.
            data_chunk.append(0xF5)
            file.write(data_chunk)


class ZlfFileReader(object):
    def __init__(self, file_path: Path):
        self.file_path = file_path
        if not self.file_path.exists():
            raise FileNotFoundError
        self.datachunks = self._open()
        self.current_index = 0

    def _open(self) -> bytes:
        with open(self.file_path, "rb") as file:
            file_content = file.read()
            assert file_content[:_ZLF_HEADER_SIZE] == _ZLF_HEADER
            return file_content[_ZLF_HEADER_SIZE:]

    def read_datachunk(self) -> DchPacket | None:
        if self.current_index >= len(self.datachunks):
            return None

        timestamp = self.datachunks[self.current_index:self.current_index+8]
        self.current_index += 8

        properties = self.datachunks[self.current_index]
        self.current_index += 1

        length = int.from_bytes(self.datachunks[self.current_index:self.current_index+4], byteorder='little')
        self.current_index += 4

        payload = self.datachunks[self.current_index:self.current_index+length]
        self.current_index += length

        payload_type = self.datachunks[self.current_index]
        self.current_index += 1

        dch_packet: DchPacket | None = None
        if payload_type == 0xF5:
            dch_packet = DchPacket.from_bytes(payload)

        return dch_packet
