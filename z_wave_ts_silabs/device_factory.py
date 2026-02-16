from typing import Literal, cast
from .definitions import ZwaveRegion
from .devices import Device, DevCluster, DevWpk, DevZwave
from .railtest import DevRailtest
from .session_context import SessionContext
from .zwave_cli import DevZwaveCli, DevZwaveDoorLockKeypad, DevZwaveLedBulb, DevZwaveMultilevelSensor, DevZwavePowerStrip, DevZwaveSensorPIR, DevZwaveSwitchOnOff, DevZwaveWallController
from .zwave_ncp import DevZwaveNcpSerialApiController, DevZwaveNcpSerialApiEndDevice, DevZwaveNcpZniffer

WpkSerialSpeed = int | Literal["auto"]


# This class is responsible for spawning the different types of devices. (Nodes in z-wave-test-system).
# and making sure they are stopped correctly.
# We could have it as an abstract class later for cli and button devices.
# it should be created by a pytest fixture, yielded to tests and then finalized (stopped ?) by the fixture that created it
class DeviceFactory(object):

    def __init__(self, ctxt: SessionContext, cluster: DevCluster) -> None:
        self._counter: int = 0
        self._ctxt = ctxt
        self._cluster: DevCluster = cluster
        self._devices: list[Device] = []

    def _spawn[T: Device](self, device_cls: type[T], region: ZwaveRegion, wpk_serial_speed: WpkSerialSpeed, capture_name: str | None = None) -> T:
        assert issubclass(device_cls, Device)
        wpk = self._cluster.get_free_wpk()
        # SOC devices only: resolve "auto" by querying WPK admin (TCP 4902) for "serial vcom"
        if wpk_serial_speed == "auto":
            if issubclass(device_cls, DevZwaveCli):
                wpk_serial_speed = wpk.get_serial_vcom_speed()
            else:
                raise ValueError('wpk_serial_speed="auto" is only supported for SOC (CLI) devices, not NCP')
        device = device_cls(self._ctxt, self._counter, wpk, region, wpk_serial_speed)

        self._counter += 1
        self._devices.append(device)
        device.start()

        # No pcap/rtt folders for zniffer and railtest (railtest is not DevZwave so already skipped)
        if issubclass(device_cls, DevZwave) and not issubclass(device_cls, DevZwaveNcpZniffer):
            self._execute_start_ctxt_checks(cast(DevZwave, device), capture_name)

        return device

    def _finalize(self):
        for device in self._devices:
            try:
                device.stop()
                if isinstance(device, DevZwave) and not isinstance(device, DevZwaveNcpZniffer):
                    self._execute_stop_ctxt_checks(device)
            except TimeoutError:
                pass

    def _execute_start_ctxt_checks(self, device: DevZwave, capture_name: str | None = None):
        if self._ctxt.current_test_pti_enabled:
            device.start_zlf_capture(capture_name)
        if self._ctxt.current_test_rtt_enabled:
            device.start_log_capture(capture_name)

    def _execute_stop_ctxt_checks(self, device: DevZwave):
        if self._ctxt.current_test_pti_enabled:
            device.stop_zlf_capture()
        if self._ctxt.current_test_rtt_enabled:
            device.stop_log_capture()

    def finalize(self):
        self._finalize()

    def serial_api_controller(self, region: ZwaveRegion = 'REGION_EU', wpk_serial_speed=115200, capture_name: str | None = None) -> DevZwaveNcpSerialApiController:
        """Create a new SerialAPIController device.

        Args:
            region (Region): Z-Wave region
            wpk_serial_speed (int): WPK serial speed
            capture_name (str | None): Directory name for traces/logs (e.g. 1_SerialAPIController). If None, derived from device.

        Returns:
            New instance of DevZwaveNcpSerialApiController.
        """
        return self._spawn(DevZwaveNcpSerialApiController, region, wpk_serial_speed, capture_name)

    def serial_api_end_device(self, region: ZwaveRegion = 'REGION_EU', wpk_serial_speed=115200, capture_name: str | None = None) -> DevZwaveNcpSerialApiEndDevice:
        """Create a new SerialAPIEndDevice device.

        Args:
            region (Region): Z-Wave region
            wpk_serial_speed (int): WPK serial speed
            capture_name (str | None): Directory name for traces/logs. If None, derived from device.

        Returns:
            New instance of DevZwaveNcpSerialApiEndDevice.
        """
        return self._spawn(DevZwaveNcpSerialApiEndDevice, region, wpk_serial_speed, capture_name)

    def door_lock_keypad(self, region: ZwaveRegion = 'REGION_EU', wpk_serial_speed: WpkSerialSpeed = "auto", capture_name: str | None = None) -> DevZwaveDoorLockKeypad:
        """Create a new DoorLockKeyPad device.

        Args:
            region (Region): Z-Wave region
            wpk_serial_speed: Baud rate or "auto" to query the WPK admin (TCP 4902, serial vcom). SOC only.

        Returns:
            New instance of DevZwaveDoorLockKeypad.
        """
        return self._spawn(DevZwaveDoorLockKeypad, region, wpk_serial_speed, capture_name)

    def led_bulb(self, region: ZwaveRegion = 'REGION_EU', wpk_serial_speed: WpkSerialSpeed = "auto", capture_name: str | None = None) -> DevZwaveLedBulb:
        """Create a new LEDBulb device.

        Args:
            region (Region): Z-Wave region
            wpk_serial_speed: Baud rate or "auto" to query the WPK admin (TCP 4902, serial vcom). SOC only.

        Returns:
            New instance of DevZwaveLedBulb.
        """
        return self._spawn(DevZwaveLedBulb, region, wpk_serial_speed, capture_name)

    def power_strip(self, region: ZwaveRegion = 'REGION_EU', wpk_serial_speed: WpkSerialSpeed = "auto", capture_name: str | None = None) -> DevZwavePowerStrip:
        """Create a new PowerStrip device.

        Args:
            region (Region): Z-Wave region
            wpk_serial_speed: Baud rate or "auto" to query the WPK admin (TCP 4902, serial vcom). SOC only.

        Returns:
            New instance of DevZwavePowerStrip.
        """
        return self._spawn(DevZwavePowerStrip, region, wpk_serial_speed, capture_name)

    def sensor_pir(self, region: ZwaveRegion = 'REGION_EU', wpk_serial_speed: WpkSerialSpeed = "auto", capture_name: str | None = None) -> DevZwaveSensorPIR:
        """Create a new SensorPIR device.

        Args:
            region (Region): Z-Wave region
            wpk_serial_speed: Baud rate or "auto" to query the WPK admin (TCP 4902, serial vcom). SOC only.

        Returns:
            New instance of DevZwaveSensorPIR.
        """
        return self._spawn(DevZwaveSensorPIR, region, wpk_serial_speed, capture_name)

    def switch_on_off(self, region: ZwaveRegion = 'REGION_EU', wpk_serial_speed: WpkSerialSpeed = "auto", capture_name: str | None = None) -> DevZwaveSwitchOnOff:
        """Create a new SwitchOnOff device.

        Args:
            region (Region): Z-Wave region
            wpk_serial_speed: Baud rate or "auto" to query the WPK admin (TCP 4902, serial vcom). SOC only.

        Returns:
            New instance of DevZwaveSwitchOnOff.
        """
        return self._spawn(DevZwaveSwitchOnOff, region, wpk_serial_speed, capture_name)

    def wall_controller(self, region: ZwaveRegion = 'REGION_EU', wpk_serial_speed: WpkSerialSpeed = "auto", capture_name: str | None = None) -> DevZwaveWallController:
        """Create a new WallController device.

        Args:
            region (Region): Z-Wave region
            wpk_serial_speed: Baud rate or "auto" to query the WPK admin (TCP 4902, serial vcom). SOC only.

        Returns:
            New instance of DevZwaveWallController.
        """
        return self._spawn(DevZwaveWallController, region, wpk_serial_speed, capture_name)

    def multilevel_sensor(self, region: ZwaveRegion = 'REGION_EU', wpk_serial_speed: WpkSerialSpeed = "auto", capture_name: str | None = None) -> DevZwaveMultilevelSensor:
        """Create a new MultilevelSensor device.

        Args:
            region (Region): Z-Wave region
            wpk_serial_speed: Baud rate or "auto" to query the WPK admin (TCP 4902, serial vcom). SOC only.

        Returns:
            New instance of DevZwaveMultilevelSensor.
        """
        return self._spawn(DevZwaveMultilevelSensor, region, wpk_serial_speed, capture_name)

    def railtest(self, region: ZwaveRegion = 'REGION_EU', wpk_serial_speed=115200, capture_name: str | None = None) -> DevRailtest:
        return self._spawn(DevRailtest, region, wpk_serial_speed, capture_name)

    def zniffer(self, region: ZwaveRegion = 'REGION_EU', wpk_serial_speed=115200, capture_name: str | None = None) -> DevZwaveNcpZniffer:
        return self._spawn(DevZwaveNcpZniffer, region, wpk_serial_speed, capture_name)
