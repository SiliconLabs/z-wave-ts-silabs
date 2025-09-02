from typing import cast
from .definitions import ZwaveRegion
from .devices import Device, DevCluster, DevZwave
from .railtest import DevRailtest
from .session_context import SessionContext
from .zwave_cli import DevZwaveDoorLockKeypad, DevZwaveLedBulb, DevZwaveMultilevelSensor, DevZwavePowerStrip, DevZwaveSensorPIR, DevZwaveSwitchOnOff, DevZwaveWallController
from .zwave_ncp import DevZwaveNcpSerialApiController, DevZwaveNcpSerialApiEndDevice, DevZwaveNcpZniffer


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

    def _spawn[T: Device](self, device_cls: type[T], region: ZwaveRegion, wpk_serial_speed) -> T:
        assert issubclass(device_cls, Device)
        device = device_cls(self._ctxt, self._counter, self._cluster.get_free_wpk(), region, wpk_serial_speed)

        self._counter += 1
        self._devices.append(device)
        device.start()

        if issubclass(device_cls, DevZwave):
            self._execute_start_ctxt_checks(cast(DevZwave, device)) # we use cast here so the type checker does not throw a warning, the check with issubclass should be enough to prevent errors.

        return device

    def _finalize(self):
        for device in self._devices:
            try:
                device.stop()
                if isinstance(device, DevZwave):
                    self._execute_stop_ctxt_checks(device)
            except TimeoutError:
                pass

    def _execute_start_ctxt_checks(self, device: DevZwave):
        if self._ctxt.current_test_pti_enabled:
            device.start_zlf_capture()
        if self._ctxt.current_test_rtt_enabled:
            device.start_log_capture()

    def _execute_stop_ctxt_checks(self, device: DevZwave):
        if self._ctxt.current_test_pti_enabled:
            device.stop_zlf_capture()
        if self._ctxt.current_test_rtt_enabled:
            device.stop_log_capture()

    def finalize(self):
        self._finalize()

    def serial_api_controller(self, region: ZwaveRegion = 'REGION_EU', wpk_serial_speed=115200) -> DevZwaveNcpSerialApiController:
        """Create a new SerialAPIController device.

        Args:
            region (Region): Z-Wave region
            wpk_serial_speed (int): WPK serial speed

        Returns:
            New instance of DevZwaveNcpSerialApiController.
        """
        return self._spawn(DevZwaveNcpSerialApiController, region, wpk_serial_speed)

    def serial_api_end_device(self, region: ZwaveRegion = 'REGION_EU', wpk_serial_speed=115200) -> DevZwaveNcpSerialApiEndDevice:
        """Create a new SerialAPIEndDevice device.

        Args:
            region (Region): Z-Wave region
            wpk_serial_speed (int): WPK serial speed

        Returns:
            New instance of DevZwaveNcpSerialApiEndDevice.
        """
        return self._spawn(DevZwaveNcpSerialApiEndDevice, region, wpk_serial_speed)

    def door_lock_keypad(self, region: ZwaveRegion = 'REGION_EU', wpk_serial_speed=9600) -> DevZwaveDoorLockKeypad:
        """Create a new DoorLockKeyPad device.

        Args:
            region (Region): Z-Wave region

        Returns:
            New instance of DevZwaveDoorLockKeypad.
        """
        return self._spawn(DevZwaveDoorLockKeypad, region, wpk_serial_speed)

    def led_bulb(self, region: ZwaveRegion = 'REGION_EU', wpk_serial_speed=9600) -> DevZwaveLedBulb:
        """Create a new LEDBulb device.

        Args:
            region (Region): Z-Wave region

        Returns:
            New instance of DevZwaveLedBulb.
        """
        return self._spawn(DevZwaveLedBulb, region, wpk_serial_speed)

    def power_strip(self, region: ZwaveRegion = 'REGION_EU', wpk_serial_speed=9600) -> DevZwavePowerStrip:
        """Create a new PowerStrip device.

        Args:
            region (Region): Z-Wave region

        Returns:
            New instance of DevZwavePowerStrip.
        """
        return self._spawn(DevZwavePowerStrip, region, wpk_serial_speed)

    def sensor_pir(self, region: ZwaveRegion = 'REGION_EU', wpk_serial_speed=9600) -> DevZwaveSensorPIR:
        """Create a new SensorPIR device.

        Args:
            region (Region): Z-Wave region

        Returns:
            New instance of DevZwaveSensorPIR.
        """
        return self._spawn(DevZwaveSensorPIR, region, wpk_serial_speed)

    def switch_on_off(self, region: ZwaveRegion = 'REGION_EU', wpk_serial_speed=9600) -> DevZwaveSwitchOnOff:
        """Create a new SwitchOnOff device.

        Args:
            region (Region): Z-Wave region

        Returns:
            New instance of DevZwaveSwitchOnOff.
        """
        return self._spawn(DevZwaveSwitchOnOff, region, wpk_serial_speed)

    def wall_controller(self, region: ZwaveRegion = 'REGION_EU', wpk_serial_speed=9600) -> DevZwaveWallController:
        """Create a new WallController device.

        Args:
            region (Region): Z-Wave region

        Returns:
            New instance of DevZwaveWallController.
        """
        return self._spawn(DevZwaveWallController, region, wpk_serial_speed)

    def multilevel_sensor(self, region: ZwaveRegion = 'REGION_EU', wpk_serial_speed=9600) -> DevZwaveMultilevelSensor:
        """Create a new MultilevelSensor device.

        Args:
            region (Region): Z-Wave region

        Returns:
            New instance of DevZwaveMultilevelSensor.
        """
        return self._spawn(DevZwaveMultilevelSensor, region, wpk_serial_speed)

    def railtest(self, region: ZwaveRegion = 'REGION_EU', wpk_serial_speed=115200) -> DevRailtest:
        return self._spawn(DevRailtest, region, wpk_serial_speed)

    def zniffer(self, region: ZwaveRegion = 'REGION_EU', wpk_serial_speed=115200) -> DevZwaveNcpZniffer:
        return self._spawn(DevZwaveNcpZniffer, region, wpk_serial_speed)
