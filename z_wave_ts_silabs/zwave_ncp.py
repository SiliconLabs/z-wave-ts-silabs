from .processes import Socat
from .definitions import AppName, ZwaveRegion
from .devices import DevZwave, DevWpk
from .session_context import SessionContext


class DevZwaveNcp(DevZwave):

    def __init__(self, ctxt: SessionContext, device_number: int, wpk: DevWpk, region: ZwaveRegion) -> None:
        super().__init__(ctxt, device_number, wpk, region)

        self.socat_process: Socat | None = None
        self.pty: str | None = None

    def start(self):
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


class DevZwaveNcpZniffer(DevZwaveNcp):

    @classmethod
    def app_name(cls) -> AppName:
        return 'zwave_ncp_zniffer'
