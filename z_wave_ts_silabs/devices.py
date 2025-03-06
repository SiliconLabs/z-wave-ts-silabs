from __future__ import annotations
import os
import re
import time
import select
import socket
import logging
import threading
from abc import ABCMeta, abstractmethod
from pathlib import Path
from dataclasses import dataclass

from . import telnetlib
from .session_context import SessionContext
from .parsers import DchPacket
from .processes import CommanderCli
from .definitions import AppName, ZwaveAppProductType, ZwaveRegion, ZpalRadioRegion
from .pcap import PcapFileWriter
from .zlf import ZlfFileWriter


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
    """

    VCOM_PORT_OFFSET = 1
    ADMIN_PORT_OFFSET = 2
    DCH_PORT_OFFSET = 5

    def __init__(self, ctxt: SessionContext, serial_no: str, ip: str, time_server: DevTimeServer, vuart_port: int = 4900):
        """Initializes the WPK board.
        :param serial_no: J-Link serial number
        :param ip: Device's IP address
        :param vuart_port: VUART port number (VCOM, admin and DCH port numbers are offsets)
        """
        self._ctxt = ctxt
        self.serial_no = int(serial_no)
        self.ip = ip
        self.time_server = time_server
        self.vuart_port = vuart_port
        self.commander_cli = CommanderCli(self._ctxt, self.ip)
        try:
            self.telnet_client = telnetlib.Telnet(host=self.ip, port=self.admin_port)
        except:
            raise Exception(f"Error trying to connect to {self.ip}")
        self.telnet_prompt = self.telnet_client.read_some().decode('ascii')
        self.logger = logging.getLogger(f"{self.__class__.__name__}-{self.serial_no}")
        self._pti_thread: threading.Thread | None = None
        self._pti_thread_stop_event: threading.Event = threading.Event()
        self.target_devinfo: TargetDevInfo = self._get_target_devinfo()

        # set dch version to 3
        if self.dch_message_version != 3:
            self.dch_message_version = 3

        # no WPK is serving as time server yet.
        if time_server.server_address is None:
            self.setup_as_time_server() # will use self.time_server
            self.time_server.server_address = self.ip
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
        try:
            self.telnet_client.write(bytes(f'{command}\r\n' ,encoding='ascii'))
        except BrokenPipeError as e: # single retry of the command
            self.telnet_client.close()
            self.telnet_client = telnetlib.Telnet(self.ip, port=self.admin_port)
            self.telnet_client.write(bytes(f'{command}\r\n' ,encoding='ascii'))
        return self.telnet_client.read_until(bytes(f'\r\n{self.telnet_prompt}', encoding='ascii'), timeout=1).decode('ascii')

    def reset(self):
        """Resets the WPK board itself."""
        sys_reset_sys_output = self._run_admin("sys reset sys")
        if sys_reset_sys_output != b'':
            self.logger.debug(f"sys_reset_sys_output: {sys_reset_sys_output}")
        self.telnet_client = telnetlib.Telnet(host=self.ip, port=self.admin_port)
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
        # Make sure the radio board (target) connected to the WPK is powered on before leaving target_reset()
        if not self.is_target_status_ok():
            self.logger.debug("target status is not ok after target reset")
        time.sleep(0.01) # wait 10ms before returning to leave enough time for the chip to boot up

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
        device_info_output = ''
        try:
            device_info_output = self.commander_cli.device_info()
        except Exception as e:
            self.logger.debug(f"Could not get device info: {e}")
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
        try:
            self.commander_cli.device_recover()
        except:
            self.logger.debug(f"commander device recover can fail in some cases")
        self.commander_cli.device_pageerase('@userdata')

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


    def flash_zwave_region_token(self, region: str):
        # this is for compatibility reasons with tools that use only the abbreviation for the region and not the full REGION_<abbreviation>.
        zpal_radio_region_str = '_'.join(['REGION', region]) if 'REGION_' not in region else region

        zpal_radio_region = ZpalRadioRegion[zpal_radio_region_str]
        self.commander_cli.flash_token('znet', f'MFG_ZWAVE_COUNTRY_FREQ:0x{zpal_radio_region.value:02X}')

    def flash_zwave_bootloader_tokenfiles(self, signing_key_path: str, encrypt_key_path: str):
        self.commander_cli.flash_tokenfiles('znet', (signing_key_path, encrypt_key_path))

    def _pti_logger_thread(self, logger_name: str):
        # get sub logger here from self, and re-direct output in file.
        # redirect output from port 4905.
        zlf_file = ZlfFileWriter(self._ctxt.current_test_logdir / f"{logger_name}.zlf")
        pcap_file = PcapFileWriter(self._ctxt.current_test_logdir / f"{logger_name}.pcap")
        dch_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        dch_socket.connect((self.ip, self.dch_port))

        self.logger.debug("_pti_logger_thread started")

        while not self._pti_thread_stop_event.is_set():

            read_fd_list, _, _ = select.select([dch_socket], [], [], 0.1) # timeout is in seconds, we set it to 100 milliseconds

            if len(read_fd_list) == 0:
                continue

            try:
                dch_packet = dch_socket.recv(2048)
                if dch_packet == b'':
                    continue
                zlf_file.write_datachunk(dch_packet)
                dch_packet = DchPacket.from_bytes(dch_packet)
                pcap_file.write_packet(dch_packet, self.time_server.reference_time)
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
        self._pti_thread.start()

    def stop_pti_logger(self):
        if self._pti_thread is not None:
            self._pti_thread_stop_event.set()
            self._pti_thread.join(1)
            self._pti_thread = None

    def start_rtt_logger(self, logger_name: str) -> None:
        self.commander_cli.spawn_rtt_logger_background_process(logger_name)

    def stop_rtt_logger(self):
        self.commander_cli.kill_rtt_logger_background_process()

    def target_power_on(self):
        self._run_admin("target power on")

    def target_power_off(self):
        self._run_admin("target power off")

    def is_target_status_ok(self) -> bool:
        target_status = self._run_admin("target status")
        if re.search(r'OK', target_status):
            return True
        return False


class DevCluster(object):

    def __init__(self, name: str | None, wpk_list: list[DevWpk]):
        self.name: str | None = name
        self.wpk_list: list[DevWpk] = wpk_list

    def get_free_wpk(self) -> DevWpk:
        if self.name is None:
            raise Exception(f"No cluster name was provided, check your configuration")

        for wpk in self.wpk_list:
            if wpk.is_free is True:
                wpk.is_free = False
                return wpk

        raise Exception(f"All WPKs in cluster: {self.name} are reserved") # if self.name is None then the cluster name could not be found

    def free_all_wpk(self) -> None:
        for wpk in self.wpk_list:
            wpk.is_free = True


class Device(metaclass=ABCMeta):
    """Base class for any device"""

    @classmethod
    @abstractmethod
    def app_name(cls) -> AppName:
        raise NotImplementedError

    def __init__(self, ctxt: SessionContext, device_number: int, wpk: DevWpk, region: ZwaveRegion):
        self._ctxt: SessionContext = ctxt
        self._device_number: int = device_number
        self.wpk: DevWpk = wpk
        self.region: ZwaveRegion = region

        # the path to the firmware of the device
        self._firmware_file: str | None = None

        # the name that will be used by the logger for this device
        self._name =f'{self.__class__.__name__}-{self._device_number}'
        self.logger = logging.getLogger(self._name)

        self._radio_board = self.wpk.radio_board.lower()
        self.logger.debug(self._radio_board)

        for file in os.listdir(ctxt.zwave_binaries):
            if (
                    (self.app_name() in file) and
                    (self._radio_board in file) and
                    (file.endswith('.hex')) and
                    not ('DEBUG' in file)
            ):
                self._firmware_file = file
                break

        if self._firmware_file is None:
            raise Exception(f'No suitable firmware was found for {self._name}')

        # Make sure the radio board (target) connected to the WPK is powered on before leaving Device.__init__()
        if not self.wpk.is_target_status_ok():
            self.wpk.target_power_on()

    @abstractmethod
    def start(self):
        raise NotImplementedError

    @abstractmethod
    def stop(self):
        raise NotImplementedError


class DevZwave(Device, metaclass=ABCMeta):
    """Base class for Z-Wave devices."""
    
    def __init__(self, ctxt: SessionContext, device_number: int, wpk: DevWpk, region: ZwaveRegion):
        """Initializes the device.
        :param device_number: Device number (helps with logger)
        :param wpk: WPK hosting the radio board
        :param region: Z-Wave region 
        """
        super().__init__(ctxt, device_number, wpk, region)

        # file used for OTA/OTW updates
        self.gbl_v255_file: str | None = None
        self.home_id: str | None = None
        self.node_id: int | None = None

        # Unify exposes this as an attribute called: SerialNumber, thus the name
        self.serial_number = f"h'{self.wpk.target_devinfo.unique_id.upper()}"

        # TODO: we should check ZGM130 -> ncp controller needs to be flashed with sample keys
        if 'ncp_serial_api_controller' in self.app_name():
            btl_signing_key = ctxt.zwave_btl_signing_key_controller
            btl_encrypt_key = ctxt.zwave_btl_encrypt_key_controller
        else:
            btl_signing_key = ctxt.zwave_btl_signing_key_end_device
            btl_encrypt_key = ctxt.zwave_btl_encrypt_key_end_device

        self.logger.debug(f'flashing: {self._firmware_file} with: {btl_encrypt_key}, {btl_signing_key}')
        self.wpk.flash_zwave_target(
            region=region,
            firmware_path=f'{ctxt.zwave_binaries}/{self._firmware_file}',
            signing_key_path=btl_signing_key,
            encrypt_key_path=btl_encrypt_key
        )

        self.gbl_v255_file = f'{Path(self._firmware_file).stem}_v255.gbl'
        if not os.path.exists(f'{ctxt.zwave_binaries}/{self.gbl_v255_file}'):
            raise Exception(f'could not find matching v255.gbl file in {ctxt.zwave_binaries}/ for {self._firmware_file}')

    # Uiid are used by Unify
    def uiid(self) -> str:
        if 'soc' in self.app_name(): # End Device Only
            return f"ZWave-0000-{ZwaveAppProductType[self.app_name()].value:04}-0004-00-01"
        return ''

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
