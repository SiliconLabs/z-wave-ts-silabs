from .definitions import ZwaveApp, ZwaveRegion
from .devices import DevZwave, DevCluster
from .session_context import SessionContext
from .zwave_cli import DevZwaveDoorLockKeypad, DevZwaveLedBulb, DevZwaveMultilevelSensor, DevZwavePowerStrip, DevZwaveSensorPIR, DevZwaveSwitchOnOff, DevZwaveWallController
from .zwave_ncp import DevZwaveNcpSerialApiController
from .zwave_gw import DevZwaveGwZpc


# This class is responsible for spawning the different types of devices. (Nodes in z-wave-test-system).
# and making sure they are stopped correctly.
# We could have it as an abstract class later for cli and button devices.
# it should be created by a pytest fixture, yielded to tests and then finalized (stopped ?) by the fixture that created it
class DeviceFactory(object):

    def __init__(self, ctxt: SessionContext, cluster: DevCluster) -> None:
        self._counter: int = 0
        self._ctxt = ctxt
        self._cluster: DevCluster = cluster
        self._devices: list[DevZwave] = []

    def _spawn[T: DevZwave](self, device_cls: type[T], region: ZwaveRegion) -> T:
        assert issubclass(device_cls, DevZwave)
        device = device_cls(self._ctxt, self._counter, self._cluster.get_free_wpk(), region, device_cls.zwave_app())

        self._counter += 1
        self._devices.append(device)
        device.start()

        return device

    def _finalize(self):
        for device in self._devices:
            try:
                device.stop()
            except TimeoutError:
                pass

    def finalize(self):
        self._finalize()

    def zpc(self, region: ZwaveRegion = 'REGION_EU') -> DevZwaveGwZpc:
        """Create a new DevZwaveGwZpc device. (actually it's ZPC + a NCP Serial API Controller)

        Args:
            region (Region): Z-Wave region

        Returns:
            New instance of DevZwaveGwZpc.
        """
        return self._spawn(DevZwaveGwZpc, region)

    def serial_api_controller(self, region: ZwaveRegion = 'REGION_EU') -> DevZwaveNcpSerialApiController:
        """Create a new SerialAPIController device.

        Args:
            region (Region): Z-Wave region

        Returns:
            New instance of DevZwaveNcpSerialApiController.
        """
        return self._spawn(DevZwaveNcpSerialApiController, region)

    def door_lock_key_pad(self, region: ZwaveRegion = 'REGION_EU') -> DevZwaveDoorLockKeypad:
        """Create a new DoorLockKeyPad device.

        Args:
            region (Region): Z-Wave region

        Returns:
            New instance of DevZwaveDoorLockKeypad.
        """
        return self._spawn(DevZwaveDoorLockKeypad, region)

    def led_bulb(self, region: ZwaveRegion = 'REGION_EU') -> DevZwaveLedBulb:
        """Create a new LEDBulb device.

        Args:
            region (Region): Z-Wave region

        Returns:
            New instance of DevZwaveLedBulb.
        """
        return self._spawn(DevZwaveLedBulb, region)

    def power_strip(self, region: ZwaveRegion = 'REGION_EU') -> DevZwavePowerStrip:
        """Create a new PowerStrip device.

        Args:
            region (Region): Z-Wave region

        Returns:
            New instance of DevZwavePowerStrip.
        """
        return self._spawn(DevZwavePowerStrip, region)

    def sensor_pir(self, region: ZwaveRegion = 'REGION_EU') -> DevZwaveSensorPIR:
        """Create a new SensorPIR device.

        Args:
            region (Region): Z-Wave region

        Returns:
            New instance of DevZwaveSensorPIR.
        """
        return self._spawn(DevZwaveSensorPIR, region)

    def switch_on_off(self, region: ZwaveRegion = 'REGION_EU') -> DevZwaveSwitchOnOff:
        """Create a new SwitchOnOff device.

        Args:
            region (Region): Z-Wave region

        Returns:
            New instance of DevZwaveSwitchOnOff.
        """
        return self._spawn(DevZwaveSwitchOnOff, region)

    def wall_controller(self, region: ZwaveRegion = 'REGION_EU') -> DevZwaveWallController:
        """Create a new WallController device.

        Args:
            region (Region): Z-Wave region

        Returns:
            New instance of DevZwaveWallController.
        """
        return self._spawn(DevZwaveWallController, region)

    def multilevel_sensor(self, region: ZwaveRegion = 'REGION_EU') -> DevZwaveMultilevelSensor:
        """Create a new MultilevelSensor device.

        Args:
            region (Region): Z-Wave region

        Returns:
            New instance of DevZwaveMultilevelSensor.
        """
        return self._spawn(DevZwaveMultilevelSensor, region)

