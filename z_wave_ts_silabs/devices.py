from __future__ import annotations
import os
import re
import time
import json
import select
import socket
import logging
import threading
from abc import ABCMeta, abstractmethod
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

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
        self._reference_time_host: int | None = None    # in microseconds
        self._reference_time_target: int | None = None  # in microseconds
        self._reference_time: int | None = None         # in microseconds

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
        self._admin_lock = threading.Lock()  # Protect telnet admin commands from concurrent access
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
        Thread-safe: Uses a lock to prevent concurrent access to telnet client.

        :param command: String command
        :return: string result
        """
        with self._admin_lock:
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

    def target_get_power(self) -> float:
        """Returns the current consumption as reported by the WSTK.
        :return: Current in mA
        """
        # send to wpk cli cmd and retreive current from response
        try:
            answer = self._run_admin("aem avg") # avg is not 'average' per say, rather a single measurement at the moment of the call
        except Exception as e:
            self.logger.error(f"Could not measure current consumption of target device: {e}")
            raise
        match = re.search(r'(?P<current>\d+\.\d+) mA', answer)
        if match:
            return float(match.groupdict()['current'])
        else:
            self.logger.error("Invalid current measurement")
            raise Exception("Could not parse current consumption from WPK response")
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

    # turn off all boards to ensure that unused boards do not disturb the test (with unsolicited frames)
    def neutralize_all_wpk(self) -> None:
        for wpk in self.wpk_list:
            wpk.target_power_off()

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
            time.sleep(0.01) # wait 10ms to be sure that the board has boot up

    @abstractmethod
    def start(self):
        raise NotImplementedError

    @abstractmethod
    def stop(self):
        raise NotImplementedError

class PowerDataScope(Enum):
    """Enumeration for power data collection scopes"""
    PRE_INCLUSION = 0
    INCLUSION = 1
    POST_INCLUSION_AWAKE = 2
    POST_INCLUSION_SLEEP = 3
    EXCLUSION = 4
class PowerDataCollector:
    """Helper class to collect power consumption data in a separate thread"""

    def __init__(self, device, test_name: str, interval: float = 1.0, unit: str = "mA"):
        self.device = device
        self.test_name = test_name
        self.interval = interval
        self.unit = unit
        self.thread_running = False  # Thread lifecycle control
        self.collecting = False      # Data collection control
        self.thread = None
        self.data = []
        self.start_time = None
        self.scope = PowerDataScope.PRE_INCLUSION

    def _collect_data(self):
        """Internal method to collect power data periodically"""
        self.start_time = time.time()
        while self.thread_running:
            try:
                # Only collect data when collecting flag is True
                if self.collecting:
                    timestamp = time.time()
                    relative_time = timestamp - self.start_time
                    power_reading = self.device.get_single_datapoint_power(self.unit)

                    data_point = {
                        "power": power_reading,
                        "time": round(relative_time, 3),
                        "unit": self.unit,
                        "scope": self.scope.value if self.scope else None
                    }

                    self.data.append(data_point)
                    self.device.logger.debug(f"Power data collected: {power_reading} at {relative_time:.3f}s")

            except Exception as e:
                self.device.logger.warning(f"Failed to collect power data: {e}")

            # Always sleep to maintain timing, regardless of collecting state
            time.sleep(self.interval)

    def reset_power_scope(self):
        """reset the scope to PRE_INCLUSION"""
        self.scope = PowerDataScope.PRE_INCLUSION

    def _calculate_power_statistics(self, sorted_values: list[float], unit: str, data_points: int = None) -> dict:
        """Calculate comprehensive power statistics from sorted values"""
        if not sorted_values:
            return {}

        n = len(sorted_values)
        if data_points is None:
            data_points = n

        def percentile(values, p):
            """Calculate percentile value"""
            index = (len(values) - 1) * p / 100
            if index.is_integer():
                return values[int(index)]
            else:
                lower = values[int(index)]
                upper = values[int(index) + 1]
                return lower + (upper - lower) * (index - int(index))

        def trimmed_mean(values, trim_percent=10):
            """Calculate trimmed mean (removes top and bottom trim_percent/2)"""
            if len(values) <= 2:
                return sum(values) / len(values)
            trim_count = max(1, int(len(values) * trim_percent / 200))  # Divide by 200 for each side
            trimmed = values[trim_count:-trim_count]
            return sum(trimmed) / len(trimmed) if trimmed else sum(values) / len(values)

        # Basic statistics
        stats = {
            "min_power": min(sorted_values),
            "max_power": max(sorted_values),
            "median_power": percentile(sorted_values, 50),  # More robust than average
            "trimmed_mean_power": trimmed_mean(sorted_values),  # Average without extremes
            "data_points": data_points,
            "unit": unit
        }

        # Add percentiles for distribution analysis
        if n >= 4:
            stats["percentiles"] = {
                "p25": percentile(sorted_values, 25),
                "p75": percentile(sorted_values, 75),
                "p90": percentile(sorted_values, 90),
                "p95": percentile(sorted_values, 95)
            }

        # Add mode if there are repeated values
        from collections import Counter
        counts = Counter(sorted_values)
        most_common = counts.most_common(1)[0]
        if most_common[1] > 1:  # Only if value appears more than once
            stats["mode_power"] = most_common[0]
            stats["mode_frequency"] = most_common[1]

        return stats

    def enter_power_scope(self, new_scope: PowerDataScope):
        """Move to the specified scope in the enumeration"""
        if not isinstance(new_scope, PowerDataScope):
            raise ValueError(f"Invalid scope: {new_scope}. Must be a PowerDataScope enum value.")
        self.scope = new_scope
        self.device.logger.info(f"Power data collection scope changed to: {new_scope.name}")

    def start(self):
        """Start collecting power data in a separate thread"""
        # Start the thread if it's not running
        if not self.thread_running:
            self.thread_running = True
            self.thread = threading.Thread(target=self._collect_data, daemon=True)
            self.thread.start()
            self.device.logger.info(f"Started power data collection thread for {self.test_name} (interval: {self.interval}s, unit: {self.unit})")

        # Enable data collection
        if not self.collecting:
            self.collecting = True
            self.device.logger.info(f"Resumed power data collection for {self.test_name}")
        else:
            self.device.logger.warning(f"Power data collection already active for {self.test_name}")

    def stop(self):
        """Stop collecting power data and save to file"""
        # Stop data collection
        self.collecting = False

        # Stop and wait for thread to finish
        if self.thread_running:
            self.thread_running = False
            if self.thread:
                self.thread.join(timeout=2.0)
                self.thread = None

        # Save data to file
        self._save_data()
        self.device.logger.info(f"Stopped power data collection for {self.test_name}. Collected {len(self.data)} data points.")

    def pause(self):
        """Pause data collection but keep thread alive and time continuing"""
        if self.collecting:
            self.collecting = False
            self.device.logger.info(f"Paused power data collection for {self.test_name} (thread continues for timing)")
        else:
            self.device.logger.warning(f"Power data collection is not active for {self.test_name}")

    def resume(self):
        """Resume data collection (alias for start for clarity)"""
        self.start()

    def update_interval(self, new_interval: float):
        """Update the data collection interval"""
        if new_interval <= 0:
            raise ValueError("Interval must be a positive number")
        self.interval = new_interval
        self.device.logger.info(f"Updated power data collection interval to {self.interval}s for {self.test_name}")

    def _save_data(self):
        """Save collected data to a JSON file"""
        if not self.data:
            return

        output_dir = self.device._ctxt.current_test_logdir
        os.makedirs(output_dir, exist_ok=True)

        # Generate filename with timestamp
        filename = f"{output_dir}/power_data.json"

        # Prepare metadata
        metadata = {
            "test_name": self.test_name,
            "collection_start": datetime.fromtimestamp(self.start_time).isoformat() if self.start_time else None,
            "collection_end": datetime.now().isoformat(),
            "total_duration_s": time.time() - self.start_time if self.start_time else 0,
            "interval_s": self.interval,
            "unit": self.unit,
            "total_data_points": len(self.data)
        }

        # Calculate basic statistics
        if self.data:
            power_values = []
            scope_data = {}  # Dictionary to store data points by scope

            for point in self.data:
                # Extract numeric value from power reading string
                try:
                    power_str = point["power"].split()[0]
                    power_value = float(power_str)
                    power_values.append(power_value)

                    # Group data by scope
                    scope = point.get("scope", "unknown")
                    if scope not in scope_data:
                        scope_data[scope] = []
                    scope_data[scope].append(power_value)

                except (ValueError, IndexError, KeyError):
                    continue

            # Overall statistics
            if power_values:
                sorted_values = sorted(power_values)
                metadata["statistics"] = {
                    "overall": self._calculate_power_statistics(sorted_values, self.unit)
                }

                # Per-scope statistics
                metadata["statistics"]["by_scope"] = {}
                for scope, values in scope_data.items():
                    if values:
                        # Convert scope value to scope name for readability
                        scope_name = scope
                        if isinstance(scope, int):
                            try:
                                scope_name = PowerDataScope(scope).name
                            except ValueError:
                                scope_name = f"scope_{scope}"

                        sorted_scope_values = sorted(values)
                        metadata["statistics"]["by_scope"][scope_name] = self._calculate_power_statistics(
                            sorted_scope_values, self.unit, len(values)
                        )

        output_data = {
            "metadata": metadata,
            "data": self.data
        }

        try:
            with open(filename, 'w') as f:
                json.dump(output_data, f, indent=2)
            self.device.logger.info(f"Power data saved to: {filename}")
        except Exception as e:
            self.device.logger.error(f"Failed to save power data to {filename}: {e}")

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
        self.gbl_v254_file: str | None = None
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

        v254_path = f'{ctxt.zwave_binaries}/{Path(self._firmware_file).stem}_v254.gbl'
        self.gbl_v254_file = os.path.basename(v254_path) if os.path.exists(v254_path) else None
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

    def start_zlf_capture(self, optional_capture_name: str | None = None) -> None:
        capture_name = self._name if optional_capture_name is None else optional_capture_name
        self.wpk.start_pti_logger(capture_name)

    def stop_zlf_capture(self) -> None:
        self.wpk.stop_pti_logger()

    def start_log_capture(self, optional_capture_name: str | None = None) -> None:
        capture_name = self._name if optional_capture_name is None else optional_capture_name
        self.wpk.start_rtt_logger(f"{capture_name}_rtt")

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

    def get_single_datapoint_power(self, unit: str = "mA") -> str:
        """
        Returns the current consumption of the target device at the moment of the call.
        :param unit: Unit of the current, can be 'A', 'mA' or 'uA'
        :return: Current in the specified unit as a formatted string
        :raises ValueError: If the unit is not one of 'A', 'mA' or 'uA'
        """
        current_mA = self.wpk.target_get_power()
        if unit == "A":
            return f"{current_mA / 1000.0:.3f} A"
        elif unit == "mA":
            return f"{current_mA:.3f} mA"
        elif unit == "uA":
            return f"{current_mA * 1000.0:.3f} uA"
        else:
            raise ValueError(f"Invalid unit: {unit}. Valid units are 'A', 'mA' or 'uA'.")