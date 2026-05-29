import gzip
import logging
import shutil
import time
from pathlib import Path
from datetime import datetime
from typing import Iterator

from .parsers import DchPacket

logger = logging.getLogger(__name__)

# ZLF is used by Zniffer and Zniffer is a C# app thus:
# https://learn.microsoft.com/en-us/dotnet/api/system.datetime.ticks?view=net-8.0#remarks
# since C# stores ticks and a tick occurs every 100ns according to the above link,
# we need to offset each timestamp with the base unix timestamp,
# which should be equal to: January 1, 1970 12:00:00 AM (or 00:00:00 in 24h format)
_BASE_UNIX_TIMESTAMP_IN_TICKS = int((datetime.fromtimestamp(0) - datetime.min).total_seconds() * 10_000_000)

_ZLF_HEADER_SIZE: int = 2048
_ZLF_HEADER: bytes = bytes([0x68] + [0x00] * (_ZLF_HEADER_SIZE-3) + [0x23, 0x12])

_ZLF_DATACHUNK_HEADER_SIZE: int = 5
_ZLF_API_TYPE_ZNIFFER: int = 0xF5 #  0xF5 is for PTI

# Suggested max size when enabling rotation on long-running captures (50 MiB).
PTI_ZLF_MAX_SIZE_BYTES: int = 50 * 1024 * 1024

# Minimum size to consider a file as valid ZLF (at least the header)
_MIN_VALID_ZLF_SIZE = _ZLF_HEADER_SIZE


def _rotated_path(base: Path, index: int, compressed: bool) -> Path:
    """Path of rotated file: base.zlf.1, base.zlf.1.gz, etc."""
    p = base.with_suffix(base.suffix + f".{index}")
    return Path(str(p) + ".gz") if compressed else p


def _list_rotated_files(base: Path, compressed: bool) -> list[tuple[int, Path]]:
    """List already rotated files (index, path), sorted by index descending."""
    stem_name = base.name
    pattern = f"{stem_name}.*.gz" if compressed else f"{stem_name}.*"
    result: list[tuple[int, Path]] = []
    for f in base.parent.glob(pattern):
        if f == base:
            continue
        name = f.name
        if compressed and not name.endswith(".gz"):
            continue
        if compressed:
            name = name[:-3]
        if not name.startswith(stem_name + "."):
            continue
        try:
            idx_str = name[len(stem_name) + 1 :]
            idx = int(idx_str)
        except ValueError:
            continue
        result.append((idx, f))
    result.sort(key=lambda x: x[0], reverse=True)
    return result


def _is_valid_zlf_file(path: Path) -> bool:
    """Return True if the file has at least the ZLF header size (2048 bytes)."""
    try:
        return path.is_file() and path.stat().st_size >= _MIN_VALID_ZLF_SIZE
    except OSError:
        return False


def rotate_zlf_file(
    zlf_path: Path,
    *,
    max_size_bytes: int | None = None,
    keep_count: int = 0,
    compress: bool = True,
    dry_run: bool = False,
) -> bool:
    """
    Apply logrotate-style rotation to a single .zlf file. Caller should create
    a new active file after rotation (e.g. ZlfFileWriter._create()).
    keep_count 0 = keep all rotated files (no suppression).
    """
    if zlf_path.suffix.lower() != ".zlf":
        logger.debug("Ignoring non-.zlf file: %s", zlf_path)
        return False
    if not _is_valid_zlf_file(zlf_path):
        logger.debug("Skipping file (too small or missing): %s", zlf_path)
        return False
    size = zlf_path.stat().st_size
    if max_size_bytes is not None and size < max_size_bytes:
        return False

    existing = _list_rotated_files(zlf_path, compress)
    for idx, path in existing:
        if keep_count > 0 and idx >= keep_count:
            if dry_run:
                logger.info("[dry-run] Would remove %s", path)
            else:
                path.unlink(missing_ok=True)
                logger.debug("Removed old rotated file: %s", path)
        else:
            new_path = _rotated_path(zlf_path, idx + 1, compress)
            if new_path == path:
                continue
            if dry_run:
                logger.info("[dry-run] Would move %s -> %s", path, new_path)
            else:
                if new_path.exists():
                    new_path.unlink()
                shutil.move(str(path), str(new_path))
                logger.debug("Moved %s -> %s", path, new_path)

    dest_uncompressed = _rotated_path(zlf_path, 1, False)
    dest_final = _rotated_path(zlf_path, 1, compress)
    if dry_run:
        logger.info("[dry-run] Would rotate %s -> %s (compress=%s)", zlf_path, dest_final, compress)
        return True
    if dest_uncompressed.exists():
        dest_uncompressed.unlink()
    shutil.move(str(zlf_path), str(dest_uncompressed))
    if compress:
        with open(dest_uncompressed, "rb") as f_in:
            with gzip.open(dest_final, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        dest_uncompressed.unlink()
        logger.info("Rotated %s -> %s", zlf_path, dest_final)
    else:
        logger.info("Rotated %s -> %s", zlf_path, dest_uncompressed)
    return True


def rotate_zlf_in_directory(
    directory: Path,
    *,
    max_size_bytes: int | None = None,
    keep_count: int = 0,
    compress: bool = True,
    dry_run: bool = False,
    recursive: bool = False,
) -> int:
    """Walk a directory and apply rotation to each .zlf file found."""
    count = 0
    pattern = "**/*.zlf" if recursive else "*.zlf"
    for zlf_path in directory.glob(pattern):
        if not zlf_path.is_file():
            continue
        if rotate_zlf_file(
            zlf_path,
            max_size_bytes=max_size_bytes,
            keep_count=keep_count,
            compress=compress,
            dry_run=dry_run,
        ):
            count += 1
    return count


def collect_zlf_paths(directory: Path, recursive: bool = False) -> Iterator[Path]:
    """Enumerate .zlf paths under directory."""
    pattern = "**/*.zlf" if recursive else "*.zlf"
    for p in directory.glob(pattern):
        if p.is_file():
            yield p


def prune_rotated_only(
    directory: Path,
    *,
    keep_count: int = 0,
    compressed: bool = True,
    dry_run: bool = False,
    recursive: bool = False,
) -> int:
    """Remove rotated files beyond keep_count (0 = keep all). Returns number removed."""
    removed = 0
    for zlf_path in collect_zlf_paths(directory, recursive=recursive):
        existing = _list_rotated_files(zlf_path, compressed)
        for idx, path in existing:
            if keep_count > 0 and idx > keep_count:
                if dry_run:
                    logger.info("[dry-run] Would remove %s", path)
                else:
                    path.unlink(missing_ok=True)
                    logger.debug("Removed %s", path)
                removed += 1
    return removed


class ZlfFileWriter(object):
    def __init__(
        self,
        file_path: Path,
        *,
        max_size_bytes: int | None = None,
        keep_count: int = 0,
        compress_rotated: bool = True,
    ) -> None:
        """
        Write Zniffer-compatible ZLF files.

        Rotation is opt-in: pass max_size_bytes (e.g. PTI_ZLF_MAX_SIZE_BYTES) for
        long-running captures. Short-lived tools and converters can omit it.
        """
        self.file_path = file_path
        self._max_size_bytes = max_size_bytes
        self._keep_count = keep_count
        self._compress_rotated = compress_rotated
        self._create()

    def _create(self) -> None:
        """Creates a new zlf file (2048-byte header)."""
        with open(self.file_path, "wb") as file:
            file.write(_ZLF_HEADER)

    def _rotate_if_needed(self) -> None:
        """If rotation is enabled and file size >= max_size, rotate and create a new file."""
        if self._max_size_bytes is None or not self.file_path.exists():
            return
        try:
            size = self.file_path.stat().st_size
        except OSError:
            return
        if size < self._max_size_bytes:
            return
        rotate_zlf_file(
            self.file_path,
            max_size_bytes=self._max_size_bytes,
            keep_count=self._keep_count,
            compress=self._compress_rotated,
            dry_run=False,
        )
        self._create()

    def write_datachunk(self, dch_packet: bytes) -> None:
        """Dumps frame to ZLF file. Rotates when max_size_bytes was set and the file exceeds it.
        :param dch_packet: DCH packet directly from WSTK/WPK/TB
        """
        self._rotate_if_needed()
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
            # api_type: some value in Zniffer, it has to be there
            data_chunk.append(_ZLF_API_TYPE_ZNIFFER)
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
