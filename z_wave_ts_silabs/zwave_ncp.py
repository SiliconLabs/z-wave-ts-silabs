from .processes import Socat
from .definitions import ZwaveRegion, ZwaveNcpApp, ZwaveApp
from .devices import DevZwave, DevWpk
from .session_context import SessionContext


class DevZwaveNcp(DevZwave):

    def __init__(self, ctxt: SessionContext, device_number: int, wpk: DevWpk, region: ZwaveRegion, app_name: ZwaveNcpApp) -> None:
        super().__init__(ctxt, device_number, wpk, region, app_name)

        self.socat_process: Socat | None = None
        self.pty: str | None = None

    def start(self):
        super().start()
        self.socat_process = Socat(self._ctxt, self.wpk.hostname, 4901)
        if not self.socat_process.is_alive:
            raise Exception("socat process did not start or died unexpectedly")
        self.pty = self.socat_process.pty_path

    def stop(self):
        super().stop()
        self.socat_process.stop()
        self.socat_process = None
        self.pty = None


class DevZwaveNcpSerialApiController(DevZwaveNcp):

    @classmethod
    def zwave_app(cls) -> ZwaveApp:
        return 'zwave_ncp_serial_api_controller'
