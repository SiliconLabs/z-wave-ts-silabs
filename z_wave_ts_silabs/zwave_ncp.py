import socket
import time
import threading
from typing import Optional

from .processes import Socat
from .definitions import AppName, ZwaveRegion, ZwaveRegionLr
from .devices import DevZwave, DevWpk
from .session_context import SessionContext
from typing import get_args


class DevZwaveNcp(DevZwave):

    def __init__(self, ctxt: SessionContext, device_number: int, wpk: DevWpk, region: ZwaveRegion, wpk_serial_speed=115200) -> None:
        super().__init__(ctxt, device_number, wpk, region)
        self.wpk_serial_speed = wpk_serial_speed
        self.socat_process: Socat | None = None
        self.pty: str | None = None

    def start(self):
        self.wpk._run_admin(f"serial vcom config speed {self.wpk_serial_speed}");
        if self.socat_process is not None:
            self.logger.debug(f"start() was called on a running instance of {self.__class__.__name__}")
            return

        self.socat_process = Socat(self._ctxt, self.wpk.ip, 4901)
        if not self.socat_process.is_alive:
            raise Exception("socat process did not start or died unexpectedly")
        self.pty = self.socat_process.pty_path

    def stop(self):
        if self.socat_process is None:
            self.logger.debug(f"stop() was called on a stopped instance of {self.__class__.__name__}")
            return

        self.socat_process.stop()
        self.socat_process = None
        self.pty = None


class DevZwaveNcpSerialApiController(DevZwaveNcp):

    @classmethod
    def app_name(cls) -> AppName:
        return 'zwave_ncp_serial_api_controller'


class DevZwaveNcpSerialApiEndDevice(DevZwaveNcp):

    @classmethod
    def app_name(cls) -> AppName:
        return 'zwave_ncp_serial_api_end_device'


class DevZwaveNcpZniffer(DevZwave):
    def __init__(self, ctxt: SessionContext, device_number: int, wpk: DevWpk, region: ZwaveRegion, wpk_serial_speed=115200) -> None:
        super().__init__(ctxt, device_number, wpk, region)
        self.tcp_socket: socket.socket | None = None
        self.tcp_port = 4901

        # CI-safe defaults
        self.connect_timeout_s = 3.0
        self.cmd_timeout_s = 3.0
        self.reconnect_attempts = 30
        self.reconnect_sleep_s = 0.5

        # IMPORTANT: protect against concurrent calls from different threads/tests
        self._io_lock = threading.Lock()

    def start(self):
        self._reconnect_tcp_with_retry("start")

    def stop(self):
        self.close_tcp_socket()

    def set_region(self, region: ZwaveRegion):
        if "REGION_" not in region:
            region = f"REGION_{region}"

        if region not in get_args(ZwaveRegion):
            raise ValueError(f"Invalid region: {region}. Region must be in {ZwaveRegion}")

        # flashing likely resets the TCP service => always reconnect and re-probe
        self.close_tcp_socket()
        self.wpk.flash_zwave_region_token(region)
        self.logger.info(f"Zniffer configure for region {region}")

        # give device a moment to reboot (cheap + removes flakiness)
        time.sleep(5.0)

        self._reconnect_tcp_with_retry(f"after flash {region}")

        if region in get_args(ZwaveRegionLr):
            self.logger.info(f"LR region detected: {region} -> selecting channel configuration 3")
            self.select_channel_configuration(3)

        return True

    def select_channel_configuration(self, channel: int):
        if channel not in (1, 2, 3):
            raise ValueError(f"Invalid channel configuration: {channel}. Channel configuraiton must be 1, 2, or 3.")
        # self.send_cmd(bytes([0x23, 0x05, 0x00])) # Stop the zniffer
        self.send_cmd(bytes([0x23, 0x06, 0x01, channel])) # Set the channel
        # self.send_cmd(bytes([0x23, 0x04, 0x00])) # Start the zniffer
        self.send_cmd(bytes([0x23, 0x07, 0x00]), 7) # Get the channel
        return True

    def open_tcp_socket(self):
        if self.tcp_socket is not None:
            return

        s = socket.create_connection((self.wpk.ip, self.tcp_port), timeout=self.connect_timeout_s)
        s.settimeout(self.cmd_timeout_s)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.tcp_socket = s
        self.logger.info(f"TCP socket opened to {self.wpk.ip}:{self.tcp_port}")

    def close_tcp_socket(self):
        if self.tcp_socket is None:
            return
        try:
            self.tcp_socket.close()
        finally:
            self.tcp_socket = None

    def _reconnect_tcp_with_retry(self, context: str):
        last_err = None
        for i in range(1, self.reconnect_attempts + 1):
            try:
                self.open_tcp_socket()
                # readiness probe: send ch=3 cmd and require ACK
                self._probe_ready()
                self.logger.info(f"Zniffer TCP ready ({context}) attempt {i}/{self.reconnect_attempts}")
                return
            except Exception as e:
                last_err = e
                self.logger.warning(f"Zniffer TCP not ready ({context}) attempt {i}/{self.reconnect_attempts}: {e}")
                self.close_tcp_socket()
                time.sleep(self.reconnect_sleep_s)
        raise TimeoutError(f"Zniffer TCP never became ready ({context}) {self.wpk.ip}:{self.tcp_port}: {last_err}")

    def _probe_ready(self):
        # Send a command to check that the zniffer is running
        self._send_cmd_locked(bytes([0x23, 0x04, 0x00]))

    def send_cmd(self, command: bytes, response_length: int = 3) -> bool:
        if self.tcp_socket is None:
            raise Exception("TCP socket is not open. Call open_tcp_socket() first.")
        if len(command) < 3:
            raise ValueError(f"Command must be at least 3 bytes, trying to send {command.hex()}")

        # Serialize send/recv and keep socket state consistent
        attempts = 0
        while attempts < 3:
            if self._send_cmd_locked(command, response_length):
                return True
            attempts += 1
            time.sleep(0.1)
        return False

    def _send_cmd_locked(self, command: bytes, response_length: int = 3) -> bool:
        with self._io_lock:
            s = self.tcp_socket
            if s is None:
                raise Exception("TCP socket is not open. Call open_tcp_socket() first.")

            # bounded wait always
            s.settimeout(self.cmd_timeout_s)

            # don't "flush forever"; just drain whatever is already queued quickly
            self._drain_rx_nonblocking()

            s.sendall(command)
            self.logger.debug(f"Sent command: {command.hex()}")

            response = self._recv_exact(response_length)

            if response[0:2] != command[0:2]:
                self.logger.warning(f"Response mismatch: cmd={command[0:2].hex()} resp={response[0:2].hex()}")
                return False
            if response[2] != (response_length - 3):
                self.logger.warning(f"Response length error: expected {(response_length - 3)} got {response[2]} (resp={response.hex()})")
                return False

            self.logger.debug(f"Command successful, response: {response.hex()}")
            return True

    def _drain_rx_nonblocking(self):
        s = self.tcp_socket
        if s is None:
            return
        old_timeout = s.gettimeout()
        try:
            s.settimeout(0.0)
            while True:
                data = s.recv(4096)
                if not data:
                    break
        except (BlockingIOError, socket.timeout):
            pass
        finally:
            s.settimeout(old_timeout)

    def _recv_exact(self, n: int) -> bytes:
        s = self.tcp_socket
        if s is None:
            raise Exception("TCP socket is not open. Call open_tcp_socket() first.")
        buf = bytearray()
        while len(buf) < n:
            chunk = s.recv(n - len(buf))
            if not chunk:
                raise ConnectionError(f"Socket closed while waiting for {n} bytes (got {len(buf)})")
            buf += chunk
        return bytes(buf)

    @classmethod
    def app_name(cls) -> AppName:
        return 'zwave_ncp_zniffer'
