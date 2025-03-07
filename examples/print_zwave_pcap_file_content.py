#!/usr/bin/env python3

from pathlib import Path
import argparse

from z_wave_ts_silabs import PcapFileReader, PcapZwavePacket

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Print the content of Z-Wave pcap file.')
    parser.add_argument("source", type=str, help="Source PCAP file path")
    args = parser.parse_args()

    src_pcap = Path(args.source)

    if not src_pcap.exists():
        exit("Source PCAP file does not exist")

    # the output of this script follows the csv format
    print(PcapZwavePacket.csv_str_format())
    pcap_file_reader = PcapFileReader(src_pcap)
    packet = pcap_file_reader.read_packet()
    while packet is not None:
        print(packet)
        packet = pcap_file_reader.read_packet()
