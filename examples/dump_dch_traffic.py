#!/usr/bin/env python3

import time
import select
import signal
import socket
import argparse
from pathlib import Path

from z_wave_ts_silabs import ZlfFileWriter, DchPacket, PcapFileWriter

def handler(signum, frame):
    exit()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Dump DCH traffic from a WPK into zlf and pcap files')
    parser.add_argument("--ip", required=True, type=str, help="IP adddress of the WPK")
    # filename is optional, this script will create the zlf and pcap files in the directory from which the script is started
    parser.add_argument("--filename", type=str, default="trace", help=" zlf and pcap file path")
    args = parser.parse_args()

    zlf_file = ZlfFileWriter(Path(f"{args.filename}.zlf"))
    pcap_file = PcapFileWriter(Path(f"{args.filename}.pcap"))

    # redirect output from port 4905.
    dch_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    dch_socket.connect((args.ip, 4905))

    # the reference time will be updated on the first received frame.
    reference_time = 0

    # set the signal handler so we can gracefully exit when using Ctrl+C.
    signal.signal(signal.SIGINT, handler)

    print("PTI logging started")

    while True:

        read_fd_list, _, _ = select.select([dch_socket], [], [], 0.1) # timeout is in seconds, we set it to 100 milliseconds

        if len(read_fd_list) == 0:
            continue

        try:
            dch_packet = dch_socket.recv(2048)
            if dch_packet == b'':
                continue

            zlf_file.write_datachunk(dch_packet)

            dch_packet = DchPacket.from_bytes(dch_packet)
            if dch_packet is not None:
                if reference_time == 0 and len(dch_packet.frames) > 0:
                    reference_time = time.time_ns() // (10 ** 3) - dch_packet.frames[0].timestamp # update the reference time using the first reported timestamp

                print(f"dch packet nb: {len(dch_packet.frames)}")
                for dch_frame in dch_packet.frames:
                    print(f"dch frame: {dch_frame}"
                        f"dch_version: {dch_frame.version} | "
                        f"timestamp_us: {reference_time + dch_frame.get_timestamp_us()} | "
                        f"zwave_frame: {dch_frame.payload.ota_packet_data.hex(' ')} | "
                        f"rssi: {dch_frame.payload.appended_info.get_rssi_value()} | "
                        f"region: {dch_frame.payload.appended_info.radio_config.z_wave_region_id} | "
                        f"channel_number: {dch_frame.payload.appended_info.radio_info.channel_number} | "
                        f"direction: {"Rx" if dch_frame.payload.appended_info.appended_info_cfg.is_rx else "Tx"} | "
                        f"pti_length: {dch_frame.payload.appended_info.appended_info_cfg.length} | "
                        f"pti_version: {dch_frame.payload.appended_info.appended_info_cfg.version} | "
                        f"error_code: {dch_frame.payload.appended_info.status_0.error_code}"
                    )

            pcap_file.write_packet(dch_packet, reference_time)
        except ConnectionResetError:
            print("dch socket: connection was reset by peer")

    print("PTI logging stopped")
