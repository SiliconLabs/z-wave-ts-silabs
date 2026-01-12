import socket
import time
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
        # Fail fast on broken/hung Zniffer service
        self.cmd_timeout_s: float = float(getattr(ctxt, "zniffer_cmd_timeout_s", 3.0)) if ctxt else 3.0
        self.connect_timeout_s: float = float(getattr(ctxt, "zniffer_connect_timeout_s", 3.0)) if ctxt else 3.0
        self.reconnect_attempts: int = int(getattr(ctxt, "zniffer_reconnect_attempts", 12)) if ctxt else 12
        self.reconnect_sleep_s: float = float(getattr(ctxt, "zniffer_reconnect_sleep_s", 0.5)) if ctxt else 0.5

    def start(self):
        self.open_tcp_socket()

    def stop(self):
        self.close_tcp_socket()

    def set_region(self, region: ZwaveRegion):
        if 'REGION_' not in region:
            region = '_'.join(['REGION', region])

        if region not in get_args(ZwaveRegion):
            raise ValueError(f"Invalid region: {region}. Region must be in {ZwaveRegion}")

        # Flashing may reset/reboot the device and kill/restart the TCP service.
        # Always drop the TCP session before flashing, then reconnect with retries.
        self.close_tcp_socket()
        self.wpk.flash_zwave_region_token(region)
        self._reconnect_tcp_with_retry(context=f"after flash region={region}")

        if region in get_args(ZwaveRegionLr):
            self.logger.info(f"Set channel configuration 3 for region {region}")
            self.select_channel_configuration(3)
        return True

    def select_channel_configuration(self, channel: int):
        if channel not in [1, 2, 3]:
            raise ValueError(f"Invalid channel: {channel}. Channel must be 1, 2, or 3.")

        try:
            self.send_cmd(bytes([0x23, 0x06, 0x01, channel]))
        except Exception as e:
            self.logger.error(f"Error selecting channel configuration of Zniffer: {e}")
            raise
        return True

    def open_tcp_socket(self):
        """Open a TCP socket connection to the device on port 4901."""
        if self.tcp_socket is not None:
            self.logger.debug("TCP socket is already open")
            return

        s = socket.create_connection((self.wpk.ip, self.tcp_port), timeout=self.connect_timeout_s)
        # IMPORTANT: ensure recv() cannot block forever
        s.settimeout(self.cmd_timeout_s)
        self.tcp_socket = s
        self.logger.info(f"TCP socket opened to {self.wpk.ip}:{self.tcp_port}")

    def _reconnect_tcp_with_retry(self, context: str = ""):
        last_err: Optional[Exception] = None
        for i in range(1, self.reconnect_attempts + 1):
            try:
                self.open_tcp_socket()
                # Optional tiny sanity check: make sure we can read/write without hanging
                self.flush_tcp_buffer()
                self.logger.info(f"TCP ready {context} (attempt {i}/{self.reconnect_attempts})")
                return
            except Exception as e:
                last_err = e
                self.close_tcp_socket()
                self.logger.warning(f"TCP not ready {context} (attempt {i}/{self.reconnect_attempts}): {e}")
                time.sleep(self.reconnect_sleep_s)
        raise TimeoutError(f"Zniffer TCP never became ready {context}: {last_err}")

    def close_tcp_socket(self):
        """Close the TCP socket connection."""
        if self.tcp_socket is None:
            self.logger.debug("TCP socket is already closed")
            return

        try:
            self.tcp_socket.close()
            self.logger.info("TCP socket closed")
        except Exception as e:
            self.logger.error(f"Error closing TCP socket: {e}")
        finally:
            self.tcp_socket = None

    def write_tcp(self, data: bytes) -> int:
        """
        Write raw data to the TCP socket.

        Args:
            data: Raw bytes to send

        Returns:
            Number of bytes sent

        Raises:
            Exception if socket is not open
        """
        if self.tcp_socket is None:
            raise Exception("TCP socket is not open. Call open_tcp_socket() first.")

        try:
            sent = self.tcp_socket.sendall(data)
            return len(data) if sent is None else sent
        except Exception as e:
            self.logger.error(f"Error writing to TCP socket: {e}")
            raise

    def read_tcp(self, buffer_size: int = 4096) -> bytes:
        """
        Read raw data from the TCP socket.

        Args:
            buffer_size: Maximum number of bytes to read (default: 4096)

        Returns:
            Raw bytes received

        Raises:
            Exception if socket is not open
        """
        if self.tcp_socket is None:
            raise Exception("TCP socket is not open. Call open_tcp_socket() first.")

        try:
            data = self.tcp_socket.recv(buffer_size, )
            return data
        except Exception as e:
            self.logger.error(f"Error reading from TCP socket: {e}")
            raise

    def flush_tcp_buffer(self):
        """Flush the TCP receive buffer by reading all pending data."""
        if self.tcp_socket is None:
            raise Exception("TCP socket is not open. Call open_tcp_socket() first.")

        s = self.tcp_socket
        old_timeout = s.gettimeout()
        try:
            # Non-blocking read without permanently changing timeouts/blocking behavior
            s.settimeout(0.0)
            while True:
                data = s.recv(4096)
                if not data:
                    break
        except (BlockingIOError, socket.timeout):
            pass
        finally:
            s.settimeout(old_timeout)
        self.logger.debug("TCP receive buffer flushed")

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

    def send_cmd(self, command: bytes) -> bool:
        """
        Send a command over TCP and verify the response.

        Args:
            command: Command bytes to send (should be at least 3 bytes)

        Returns:
            True if command succeeded (valid response received)

        Raises:
            Exception if socket is not open, command is invalid, or response is incorrect
        """
        if self.tcp_socket is None:
            raise Exception("TCP socket is not open. Call open_tcp_socket() first.")

        if len(command) < 3:
            raise ValueError(f"Command must be at least 3 bytes, trying to send {command.hex()}")

        # Step 1: Flush the TCP receive buffer
        self.flush_tcp_buffer()

        # Step 2: Send the command over TCP
        self.write_tcp(command)
        self.logger.debug(f"Sent command: {command.hex()}")

        # Step 3: Check the answer (should be 3 bytes)
        try:
            # Force a bounded wait for the ACK
            self.tcp_socket.settimeout(self.cmd_timeout_s)
            response = self._recv_exact(3)
        except socket.timeout as e:
            raise TimeoutError(
                f"Timeout waiting for 3B response to {command.hex()} from {self.wpk.ip}:{self.tcp_port} "
                f"(timeout={self.cmd_timeout_s}s)"
            ) from e

        if len(response) != 3:
            error_msg = f"Invalid response length: expected 3 bytes, got {len(response)} bytes. Bytes received: {response.hex()}"
            self.logger.error(error_msg)
            raise Exception(error_msg)

        # First 2 bytes should match the first 2 bytes of the command
        if response[0] != command[0] or response[1] != command[1]:
            error_msg = f"Response mismatch: command={command[0:2].hex()}, response={response[0:2].hex()}"
            self.logger.error(error_msg)
            raise Exception(error_msg)

        # Last byte should be 0
        if response[2] != 0:
            error_msg = f"Response status error: expected 0, got {response[2]}"
            self.logger.error(error_msg)
            raise Exception(error_msg)

        self.logger.debug(f"Command successful, response: {response.hex()}")
        return True

    @classmethod
    def app_name(cls) -> AppName:
        return 'zwave_ncp_zniffer'
