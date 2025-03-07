#!/usr/bin/env python3

from pathlib import Path
import argparse

from z_wave_ts_silabs import DchPacket, ZlfFileReader, PcapFileWriter


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Convert a ZLF file into a pcap file.')
    parser.add_argument("source", type=str, help="Source ZLF file path")
    # dest is optional, this script will create the pcap file next to the original zlf file by default
    parser.add_argument("--dest", type=str, help="Destination pcap file path")
    args = parser.parse_args()

    src_zlf = Path(args.source)
    if not src_zlf.exists():
        raise FileNotFoundError("Source ZLF file does not exist")

    dst_pcap = src_zlf.with_suffix(".pcap")
    if args.dest:
        dst_pcap = Path(args.dest)

    if dst_pcap.exists():
        print("WARNING: Destination pcap file exists, it will be overwritten !")

    zlf_file = ZlfFileReader(src_zlf)
    pcap_file = PcapFileWriter(dst_pcap)
    reference_time = 0 # TODO: get a reference time from the first timestamp of the datachunk of the ZLF file

    dch_packet: DchPacket | None = zlf_file.read_datachunk()
    while dch_packet is not None:
        pcap_file.write_packet(dch_packet, reference_time)
        dch_packet = zlf_file.read_datachunk()

    print(f"Converted:\n{src_zlf}\nto:\n{dst_pcap}")
