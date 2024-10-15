from typing import List, Type, TypeVar

from .definitions import ZwaveApp, ZwaveRegion
from .devices import DevZwave, DevCluster
from .zwave_cli import DevZwaveDoorLockKeypad, DevZwaveLedBulb, DevZwaveMultilevelSensor, DevZwavePowerStrip, DevZwaveSensorPIR, DevZwaveSwitchOnOff, DevZwaveWallController
from .zwave_gw import DevZwaveGwZpc

DevZwaveT = TypeVar('DevZwaveT', bound=DevZwave)

# This class is responsible for spawning the different types of devices. (Nodes in z-wave-test-system).
# and making sure they are stopped correctly.
# We could have it as an abstract class later for cli and button devices.
class DeviceFactory(object):

    def __init__(self, cluster: DevCluster) -> None:
        self._counter: int = 0
        self._cluster: DevCluster = cluster
        self._devices: List[DevZwave] = []

    def _spawn(self, device_cls: Type[DevZwaveT], region: ZwaveRegion, app_name: ZwaveApp) -> DevZwaveT:
        assert issubclass(device_cls, DevZwave)
        device = device_cls(self._counter, self._cluster.get_free_wpk(), region, app_name)

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

    def serial_api_controller(self, region: ZwaveRegion = 'REGION_EU') -> DevZwaveGwZpc:
        """Create a new SerialAPIController node. (actually it's ZPC with a NCP Serial API Controller)

        Args:
            region (Region): Z-Wave region

        Returns:
            New instance of SerialAPINode.
        """
        return self._spawn(DevZwaveGwZpc, region, 'zwave_ncp_serial_api_controller')

    def door_lock_key_pad(self, region: ZwaveRegion = 'REGION_EU') -> DevZwaveDoorLockKeypad:
        """Create a new DoorLockKeyPad node.

        Args:
            region (Region): Z-Wave region

        Returns:
            New instance of DoorLockKeyPadNode.
        """
        return self._spawn(DevZwaveDoorLockKeypad, region, 'zwave_soc_door_lock_keypad')

    def led_bulb(self, region: ZwaveRegion = 'REGION_EU') -> DevZwaveLedBulb:
        """Create a new LEDBulb node.

        Args:
            region (Region): Z-Wave region

        Returns:
            New instance of LEDBulbNode.
        """
        return self._spawn(DevZwaveLedBulb, region, 'zwave_soc_led_bulb')

    def power_strip(self, region: ZwaveRegion = 'REGION_EU') -> DevZwavePowerStrip:
        """Create a new PowerStrip node.

        Args:
            region (Region): Z-Wave region

        Returns:
            New instance of PowerStripNode.
        """
        return self._spawn(DevZwavePowerStrip, region, 'zwave_soc_power_strip')

    def sensor_pir(self, region: ZwaveRegion = 'REGION_EU') -> DevZwaveSensorPIR:
        """Create a new SensorPIR node.

        Args:
            region (Region): Z-Wave region

        Returns:
            New instance of SensorPIRNode.
        """
        return self._spawn(DevZwaveSensorPIR, region, 'zwave_soc_sensor_pir')

    def switch_on_off(self, region: ZwaveRegion = 'REGION_EU') -> DevZwaveSwitchOnOff:
        """Create a new SwitchOnOff node.

        Args:
            region (Region): Z-Wave region

        Returns:
            New instance of SwitchOnOffNode.
        """
        return self._spawn(DevZwaveSwitchOnOff, region, 'zwave_soc_switch_on_off')

    def wall_controller(self, region: ZwaveRegion = 'REGION_EU') -> DevZwaveWallController:
        """Create a new WallController node.

        Args:
            region (Region): Z-Wave region

        Returns:
            New instance of WallControllerNode.
        """
        return self._spawn(DevZwaveWallController, region, 'zwave_soc_wall_controller')

    def multilevel_sensor(self, region: ZwaveRegion = 'REGION_EU') -> DevZwaveMultilevelSensor:
        """Create a new MultilevelSensor node.

        Args:
            region (Region): Z-Wave region

        Returns:
            New instance of MultilevelSensor.
        """
        return self._spawn(DevZwaveMultilevelSensor, region, 'zwave_soc_multilevel_sensor')

