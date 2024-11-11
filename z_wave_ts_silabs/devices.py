from __future__ import annotations
import os
import re
import struct
import time
import select
import socket
import logging
import threading
from abc import ABCMeta, abstractmethod
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass

from . import telnetlib
from .session_context import SessionContext
from .parsers import DchPacket
from .processes import CommanderCli
from .definitions import ZwaveAppProductType, ZwaveRegion, ZwaveApp, ZpalRadioRegion

# ZLF is used by Zniffer and Zniffer is a C# app thus:
# https://learn.microsoft.com/en-us/dotnet/api/system.datetime.ticks?view=net-8.0#remarks
# since C# stores ticks and a tick occurs every 100ns according to the above link,
# we need to offset each timestamp with the base unix timestamp,
# which should be equal to: January 1, 1970 12:00:00 AM (or 00:00:00 in 24h format)
BASE_UNIX_TIMESTAMP_IN_TICKS = int((datetime.fromtimestamp(0) - datetime.min).total_seconds() * 10_000_000)


@dataclass
class TargetDevInfo:
    part_number: str
    flash_size: str
    sram_size: str
    unique_id: str


# Does not represent a device, but allows all DevWpk (and DevCluster) to have the same time reference.
class DevTimeServer(object):

    def __init__(self):
        self._server_address: str | None = None
        self._reference_time_host: int | None = None
        self._reference_time_target: int | None = None
        self._reference_time: int | None = None

    @property
    def server_address(self):
        return self._server_address

    @server_address.setter
    def server_address(self, value: str):
        self._server_address = value

    @property
    def reference_time(self) -> int:
        if self._reference_time is None:
            self._reference_time = self._reference_time_host - self._reference_time_target
        return self._reference_time


class DevWpk(object):
    """Represents a WPK board. 
    inspired from DevWstk class in witef-core,
    this one here uses commander instead of the Jlink lib.
    """

    VCOM_PORT_OFFSET = 1
    ADMIN_PORT_OFFSET = 2
    DCH_PORT_OFFSET = 5

    def __init__(self, ctxt: SessionContext, serial_no: str, hostname: str, time_server: DevTimeServer, vuart_port: int = 4900):
        """Initializes the WPK board.
        :param serial_no: J-Link serial number
        :param hostname: Device's IP address or hostname
        :param vuart_port: VUART port number (VCOM, admin and DCH port numbers are offsets)
        """
        self._ctxt = ctxt
        self.serial_no = int(serial_no)
        self.hostname = hostname
        self.time_server = time_server
        self.vuart_port = vuart_port
        self.commander_cli = CommanderCli(self._ctxt, self.hostname)
        try:
            self.telnet_client = telnetlib.Telnet(host=self.hostname, port=self.admin_port)
        except:
            raise Exception(f"Error trying to connect to {hostname}")
        self.telnet_prompt = self.telnet_client.read_some().decode('ascii')
        self.target_dsk: str | None = None
        self.logger = logging.getLogger(f"{self.__class__.__name__}-{self.serial_no}")
        self._pti_thread: threading.Thread | None = None
        self._pti_thread_stop_event: threading.Event = threading.Event()
        self._target_devinfo: TargetDevInfo | None = None

        # set dch version to 3
        if self.dch_message_version != 3:
            self.dch_message_version = 3

        # no WPK is serving as time server yet.
        if time_server.server_address is None:
            self.setup_as_time_server() # will use self.time_server
            self.time_server.server_address = socket.gethostbyname(self.hostname)
        # a WPK is already acting as a time server.
        else:
            self.setup_as_time_client(time_server.server_address)

        # set PTI bitrate to 1.6M (can also be setup to 3.2M)
        if self.pti_config_bitrate != 1600000:
            self.pti_config_bitrate = 1600000
        # Enable PTI
        self.enable_pti()

        # boolean to control WPK reservation
        self.is_free = False

    @property
    def vcom_port(self) -> int:
        """Gets the VCOM port (typ. 4901).
        :return: VCOM port
        """
        return self.vuart_port + DevWpk.VCOM_PORT_OFFSET

    @property
    def admin_port(self) -> int:
        """Gets the admin port (typ. 4902).
        :return: admin port
        """
        return self.vuart_port + DevWpk.ADMIN_PORT_OFFSET

    @property
    def dch_port(self) -> int:
        """Gets the DCH port (typ. 4905).
        :return: DCH port
        """
        return self.vuart_port + DevWpk.DCH_PORT_OFFSET

    def _run_admin(self, command: str) -> str:
        """Runs a command on admin interface.

        :param command: String command
        :return: string result
        """
        self.telnet_client.write(bytes(f'{command}\r\n' ,encoding='ascii'))
        return self.telnet_client.read_until(bytes(f'\r\n{self.telnet_prompt}', encoding='ascii'), timeout=1).decode('ascii')

    def reset(self):
        """Resets the WPK board itself."""
        sys_reset_sys_output = self._run_admin("sys reset sys")
        if sys_reset_sys_output != b'':
            self.logger.debug(f"sys_reset_sys_output: {sys_reset_sys_output}")
        self.telnet_client = telnetlib.Telnet(host=self.hostname, port=self.admin_port)
        self.telnet_prompt = self.telnet_client.read_some().decode('ascii')

    @staticmethod
    def parallel_reset(wpk_list: list[DevWpk]):
        reset_threads: list[threading.Thread] = []
        for wpk in wpk_list:
            reset_threads.append(threading.Thread(target=wpk.reset))
            reset_threads[-1].start()
        for thread in reset_threads:
            thread.join()

    def target_reset(self):
        """Resets the radio board plugged into the WPK."""
        self._run_admin("target reset 1")

    @property
    def radio_board(self) -> str:
        """Gets the radio board name (e.g.brd4170a)
        :return: The radio board name
        """
        match = re.search(
                r'\[A2h]\s+(?P<boardid>\w+)',
                self._run_admin("boardid")
          )
        if match:
            return match.groupdict()['boardid']
        raise Exception("Could not get radio board name")

    def _get_target_devinfo(self) -> TargetDevInfo:
        device_info_output = self.commander_cli.device_info()
        part_number = flash_size = sram_size = eui64 = ''
        for line in device_info_output.splitlines():
            if 'Part Number' in line:
                part_number = line.split(':')[1].strip()
            if 'Flash Size' in line:
                flash_size = line.split(':')[1].strip()
            if 'SRAM Size' in line:
                sram_size = line.split(':')[1].strip()
            if 'Unique ID' in line:
                eui64 = line.split(':')[1].strip()
        return TargetDevInfo(part_number, flash_size, sram_size, eui64)

    @property
    def target_devinfo(self) -> TargetDevInfo:
        """Gets the target's cached Dev Info.
        :return: TargetDevInfo dataclass
        """
        if self._target_devinfo is None:
            self._target_devinfo = self._get_target_devinfo()
        return self._target_devinfo

    @property
    def dch_message_version(self) -> int:
        match = re.search(
            r'Message protocol version : (?P<dch_version>\d)',
            self._run_admin("dch message version")
        )
        if match:
            return int(match.groupdict()['dch_version'])
        raise Exception("Could not get DCH version")

    @dch_message_version.setter
    def dch_message_version(self, version: int):
        #TODO: check result
        self._run_admin(f"dch message version {version}")

    @property
    def pti_config_bitrate(self) -> int:
        match = re.search(
            r'Bitrate {11}: (?P<bitrate>\d)',
            self._run_admin("pti config")
        )
        if match:
            return int(match.groupdict()['bitrate'])
        raise Exception("Could not get PTI config")

    @pti_config_bitrate.setter
    def pti_config_bitrate(self, bitrate: int):
        # TODO: check result
        self._run_admin(f"pti config 0 efruart {bitrate}")

    def enable_pti(self):
        # TODO: check result
        self._run_admin("dch message pti enable")

    def setup_as_time_server(self):
        self._run_admin("time server")
        self.time_server._reference_time_host = time.time_ns() // (10 ** 3) # convert ns to us
        time_info_output = self._run_admin("time info")

        # first check that the time server is active
        match = re.search(
            r'Time service mode {4}: server \[5]',
            time_info_output
        )
        if match is None:
           raise Exception("Could not set up time server")

        # then extract the current time on this WPK
        match = re.search(
            r'Current local time {3}: (?P<current_local_time>\d+) us',
            time_info_output
        )
        if match:
            self.time_server._reference_time_target = int(match.groupdict()['current_local_time'])
        else:
            self.logger.info(f"NO WPK TIME SET UP")

    def setup_as_time_client(self, ip_client: str):
        self._run_admin(f"time client {ip_client}")
        match = re.search(
            r'Time service mode {4}: client \[3]',
            self._run_admin(f"time info")
        )
        if match is None:
            raise Exception("Could not set up time client")

    def clear_flash(self):
        self.commander_cli.device_recover()
        self.commander_cli.device_pageerase('@userdata')

    def get_zwave_dsk_from_flash(self) -> str:
        cmd_output = self.commander_cli.device_zwave_qrcode()
        qr_code = re.search(r'[0-9]{90,}', cmd_output.splitlines()[0])
        if qr_code:
            self.target_dsk = qr_code.group()[12:53]
        return self.target_dsk

    def flash_target(self, firmware_path: str):
        self.commander_cli.flash(firmware_path)

    # does more than flashing
    def flash_zwave_target(self, region: str, firmware_path: str, signing_key_path: str = None, encrypt_key_path: str = None):
        # clear the main flash of the device and the MFG tokens
        self.clear_flash()

        # flash the region token
        self.flash_zwave_region_token(region)

        # flash the bootloader keys and firmware
        if signing_key_path and encrypt_key_path:
            self.flash_zwave_bootloader_tokenfiles(signing_key_path, encrypt_key_path)

        # flash the firmware
        self.flash_target(firmware_path)

        # store the target dsk in self.target_dsk for later use (the Z-Wave CLI on End Devices provides a similar option).
        self.get_zwave_dsk_from_flash()

    def flash_zwave_region_token(self, region: str):
        # this is for compatibility reasons with tools that use only the abbreviation for the region and not the full REGION_<abbreviation>.
        zpal_radio_region_str = '_'.join(['REGION', region]) if 'REGION_' not in region else region

        zpal_radio_region = ZpalRadioRegion[zpal_radio_region_str]
        self.commander_cli.flash_token('znet', f'MFG_ZWAVE_COUNTRY_FREQ:0x{zpal_radio_region.value:02X}')

    def flash_zwave_bootloader_tokenfiles(self, signing_key_path: str, encrypt_key_path: str):
        self.commander_cli.flash_tokenfiles('znet', (signing_key_path, encrypt_key_path))

    @staticmethod
    def _create_pcap_file(filename: str) -> None:
        """Creates a new pcap file.
        :param filename: File path
        """
        # we follow this specification: https://ietf-opsawg-wg.github.io/draft-ietf-opsawg-pcap/draft-ietf-opsawg-pcap.html#name-general-file-structure
        with open(filename, 'wb') as file:
            file.write(struct.pack("<IHHQII",
                                   0xA1B2C3D4,  # Magic Number (4 bytes) 0xA1B2C3D4 -> s and us | 0xA1B23C4D -> s and ns
                                   2,               # Major version (2 bytes) the current standard is 2
                                   4,               # Minor version (2 bytes) the current standard is 4
                                   0,               # Reserved 1 (4 bytes) and Reserved 2 (4 bytes) both set to 0
                                   4096,            # SnapLen (4 bytes) max number of octets captured from each packet, must not be 0
                                   297              # LinkType and additional information (4 bytes), we only set the link type to LINKTYPE_ZWAVE_TAP: 297
                                   ))

    @staticmethod
    def _dump_to_pcap_file(filename: str, dch_packet: DchPacket, reference_time: int) -> None:
        """Dumps frame to pcap file.
        :param filename: File path
        :param dch_packet: parsed DCH packet from WSTK/WPK/TB containing Z-Wave frames
        """
        if dch_packet is None:
            return

        with open(filename, 'ab') as file:
            # file.write(struct.pack("<II", timestamp_s, timestamp_ns))
            for frame in dch_packet.frames:
                # https://ietf-opsawg-wg.github.io/draft-ietf-opsawg-pcap/draft-ietf-opsawg-pcap.html#name-packet-record
                cur_time = (reference_time + frame.timestamp)
                cur_time_second = cur_time // (10 ** 6)
                cur_time_microsecond = cur_time % (10 ** 6)
                # TODO: write total packet size with TAP header + TLVs (should be 30 bytes)
                packet_length = 32 + len(frame.payload.ota_packet_data) # 32 is TAP header + TAP TLVs
                # Timestamp (seconds), Timestamp (microseconds), Captured packet length, Original packet length
                file.write(struct.pack("<IIII", cur_time_second, cur_time_microsecond, packet_length, packet_length))
                # TAP header
                file.write(struct.pack("<BBH", 1, 0, 7)) # version, reserved (0), length of TLVs section (7 32bit words with all 3 TLVs)
                file.write(struct.pack("<HHI", 0, 1, 0)) # FCS: 1 for R1 and R2, 2 for R3 TODO: replace 0 with the right value
                file.write(struct.pack("<HHI", 1, 4, 0)) # RSS: TODO: replace 0 with the RSSI value in dBm from RAIL
                file.write(struct.pack("<HHHHI", 2, 8, 0, 0, 0)) # RFI: radio frequency information -> Region, Data Rate, Frequency in KHz
                file.write(frame.payload.ota_packet_data)

    @staticmethod
    def _create_zlf_file(filename: str) -> None:
        """Creates a new zlf file.
        :param filename: File path
        """
        with open(filename, "wb") as file:
            file.write(bytes([104]))  # ZLF_VERSION
            file.write(bytes([0x00] * (2048 - 3)))
            file.write(bytes([0x23, 0x12]))

    @staticmethod
    def _dump_to_zlf_file(filename: str, dch_packet: bytes) -> None:
        """Dumps frame to ZLF file.
        :param filename: File path
        :param dch_packet: DCH packet directly from WSTK/WPK/TB
        """
        # Hacky timestamp stuff from C# datetime format. a Datetime format is made of a kind part on 2 bits
        # and a tick part on the remainder 62 bits.

        # convert nanoseconds to ticks.
        zlf_timestamp = time.time_ns() // 100
        # set the kind to: UTC https://learn.microsoft.com/en-us/dotnet/api/system.datetimekind?view=net-8.0#fields
        zlf_timestamp |= (1 << 63)
        # add base unix timestamp in tick to current
        zlf_timestamp += BASE_UNIX_TIMESTAMP_IN_TICKS
        with open(filename, "ab") as file:
            data_chunk = bytearray()
            data_chunk.extend(zlf_timestamp.to_bytes(8, 'little'))
            # properties: 0x00 is RX | 0x01 is TX (but we set it to 0x00 all the time)
            data_chunk.append(0x00)
            data_chunk.extend((len(dch_packet)).to_bytes(4, 'little'))
            data_chunk.extend(dch_packet)
            # api_type: some value in Zniffer, it has to be there.
            data_chunk.append(0xF5)
            file.write(data_chunk)

    def _pti_logger_thread(self, logger_name: str):
        filename = f"{self._ctxt.current_test_logdir}/{logger_name}.zlf"
        filename_pcap = f"{self._ctxt.current_test_logdir}/{logger_name}.pcap"
        # get sub logger here from self, and re-direct output in file.
        # redirect output from port 4905.
        DevWpk._create_zlf_file(filename)
        DevWpk._create_pcap_file(filename_pcap)
        dch_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        dch_socket.connect((self.hostname, self.dch_port))

        self.logger.debug("_pti_logger_thread started")

        while not self._pti_thread_stop_event.is_set():

            read_fd_list, _, _ = select.select([dch_socket], [], [], 0.1) # timeout is in seconds, we set it to 100 milliseconds

            if len(read_fd_list) == 0:
                continue

            try:
                dch_packet = dch_socket.recv(2048)
                if dch_packet == b'':
                    continue
                    # raise Exception('DCH socket connection broken')
                self._dump_to_zlf_file(filename, dch_packet)
                dch_packet = DchPacket.from_bytes(dch_packet)
                self._dump_to_pcap_file(filename_pcap, dch_packet, self.time_server.reference_time)
                # if dch_packet is not None:
                #     self.logger.info(f"dch packet nb: {len(dch_packet.frames)}")
                #     for dch_frame in dch_packet.frames:
                #         self.logger.info(
                #             f"dch_version: {dch_frame.version} | "
                #             f"timestamp_us: {self.time_server.reference_time + dch_frame.get_timestamp_us()} | "
                #             f"zwave_frame: {dch_frame.payload.ota_packet_data.hex(' ')} | "
                #             f"rssi: {dch_frame.payload.appended_info.get_rssi_value()} | "
                #             f"region: {dch_frame.payload.appended_info.radio_config.z_wave_region_id} | "
                #             f"channel_number: {dch_frame.payload.appended_info.radio_info.channel_number} | "
                #             f"direction: {"Rx" if dch_frame.payload.appended_info.appended_info_cfg.is_rx else "Tx"} | "
                #             f"pti_length: {dch_frame.payload.appended_info.appended_info_cfg.length} | "
                #             f"pti_version: {dch_frame.payload.appended_info.appended_info_cfg.version} | "
                #             f"error_code: {dch_frame.payload.appended_info.status_0.error_code}"
                #         )
            except ConnectionResetError:
                self.logger.debug("dch socket: connection was reset by peer")

        self.logger.debug("_pti_logger_thread stopped")

        return

    def start_pti_logger(self, logger_name: str) -> None:
        if self._pti_thread_stop_event.is_set():
            self._pti_thread_stop_event.clear()
        self._pti_thread = threading.Thread(target=self._pti_logger_thread, args=(logger_name,))
        self._pti_thread.daemon = True
        # TODO: check that the thread is running
        self._pti_thread.start()

    def stop_pti_logger(self):
        self._pti_thread_stop_event.set()
        self._pti_thread.join(1)  # TODO: check if still running and set timeout

    def start_rtt_logger(self, logger_name: str) -> None:
        self.commander_cli.spawn_rtt_logger_background_process(logger_name)

    def stop_rtt_logger(self):
        self.commander_cli.kill_rtt_logger_background_process()


class DevCluster(object):

    def __init__(self, name: str, wpk_list: list[DevWpk]):
        self.name: str = name
        self.wpk_list: list[DevWpk] = wpk_list

    def get_free_wpk(self) -> DevWpk:
        for wpk in self.wpk_list:
            if wpk.is_free is True:
                wpk.is_free = False
                return wpk
        raise Exception(f"All WPKs in cluster: {self.name} are reserved")

    def free_all_wpk(self) -> None:
        for wpk in self.wpk_list:
            wpk.is_free = True


class DevZwave(metaclass=ABCMeta):
    """Base class for Z-Wave devices."""

    @classmethod
    @abstractmethod
    def zwave_app(cls):
        raise NotImplementedError
    
    def __init__(self, ctxt: SessionContext, device_number: int, wpk: DevWpk, region: ZwaveRegion, app_type: ZwaveApp, debug: bool = False):
        """Initializes the device.
        :param device_number: Device number (helps with logger)
        :param wpk: WPK hosting the radio board
        :param region: Z-Wave region 
        """
        self._ctxt: SessionContext = ctxt
        self._device_number: int = device_number
        self.wpk: DevWpk = wpk
        self.region: str = region
        self.app_type: ZwaveApp = app_type
        self._name = f'{self._device_number}-{self.app_type}' # derive the name from the device number and the app type
        self.firmware_file: str | None = None
        self.gbl_v255_file: str | None = None
        self.home_id: str | None = None
        self.node_id: int | None = None

        self.logger = logging.getLogger(f'{self.__class__.__name__}-{self._name}')
        self.radio_board = self.wpk.radio_board.lower()
        self.logger.debug(self.radio_board)

        devinfo: TargetDevInfo = self.wpk.target_devinfo
        # Unify exposes this as an attribute called: SerialNumber, thus the name
        self.serial_number = f"h'{devinfo.unique_id.upper()}"

        for file in os.listdir(ctxt.zwave_binaries):
            if (
                (self.app_type in file) and
                (self.radio_board in file) and
                (file.endswith('.hex')) and
                not ('DEBUG' in file)
            ):
                self.firmware_file = file
                break

        if self.firmware_file is None:
            raise Exception(f'No suitable firmware was found for {self._name}')

        # TODO: we should check ZGM130 -> ncp controller needs to be flashed with sample keys
        if 'ncp_serial_api_controller' in self.app_type:
            btl_signing_key = ctxt.zwave_btl_signing_key_controller
            btl_encrypt_key = ctxt.zwave_btl_encrypt_key_controller
        else:
            btl_signing_key = ctxt.zwave_btl_signing_key_end_device
            btl_encrypt_key = ctxt.zwave_btl_encrypt_key_end_device

        self.logger.debug(f'flashing: {self.firmware_file} with: {btl_encrypt_key}, {btl_signing_key}')
        self.wpk.flash_zwave_target(
            region=region,
            firmware_path=f'{ctxt.zwave_binaries}/{self.firmware_file}',
            signing_key_path=btl_signing_key,
            encrypt_key_path=btl_encrypt_key
        )

        self.gbl_v255_file = f'{Path(self.firmware_file).stem}_v255.gbl'
        if not os.path.exists(f'{ctxt.zwave_binaries}/{self.gbl_v255_file}'):
            raise Exception(f'could not find matching v255.gbl file in {ctxt.zwave_binaries}/ for {self.firmware_file}')

    def start(self):
        self.start_log_capture()
        self.start_zlf_capture()

    def stop(self):
        self.stop_log_capture()
        self.stop_zlf_capture()

    # Uiid are used by Unify
    def uiid(self) -> str:
        return f"ZWave-0000-{ZwaveAppProductType[self.app_type].value:04}-0004-00-01"

    # Unid are used by Unify
    def unid(self) -> str | None:
        if self.home_id is None or self.node_id is None:
            return None
        return f"zw-{self.home_id}-{self.node_id:04}"

    def start_zlf_capture(self) -> None:
        self.wpk.start_pti_logger(self._name)

    def stop_zlf_capture(self) -> None:
        self.wpk.stop_pti_logger()

    def start_log_capture(self) -> None:
        self.wpk.start_rtt_logger(f"{self._name}_rtt")

    def stop_log_capture(self) -> None:
        self.wpk.stop_rtt_logger()

    def get_node_id(self) -> int:
        if self.node_id:
            return self.node_id
        return 0

    def get_home_id(self) -> str:
        if self.home_id:
            return self.home_id
        return ''
