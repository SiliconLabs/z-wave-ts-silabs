import re
from typing import Literal

from . import telnetlib
from .definitions import ZwaveRegion, ZwaveSocApp, ZwaveApp
from .devices import DevZwave, DevWpk
from .session_context import SessionContext


class DevZwaveCli(DevZwave):
    
     def __init__(self, ctxt: SessionContext, device_number: int, wpk: DevWpk, region: ZwaveRegion, app_name: ZwaveSocApp):
          """Instantiates a Z-Wave CLI device.
          :param device_number: Device number
          :param wpk: The wpk with the radio board acting as an End Device
          """
          super().__init__(ctxt, device_number, wpk, region, app_name)
          self.telnet_client = telnetlib.Telnet(wpk.hostname, '4901', 1)
          # send empty command to check if everything is working correctly
          if '>' not in self._run_cmd(''):
               raise Exception("This application does not have a CLI")
     
     def _run_cmd(self, command: str) -> str:
          self.telnet_client.write(bytes(f'{command}\n' ,encoding='ascii'))
          return self.telnet_client.read_until(b'\n> ', timeout=1).decode('ascii')

     def set_learn_mode(self) -> None:
          output = self._run_cmd(f'set_learn_mode')
          self.logger.debug(f'set_learn_mode: {output.encode("ascii")}')

     def factory_reset(self) -> None:
          self._run_cmd('factory_reset')

     def get_dsk(self) -> str | None:
          match = re.search(
               r'\[I\] (?P<dsk>(\d{5}-){7}\d{5})', 
               self._run_cmd('get_dsk')
          )
          if match is not None:
               dsk = match.groupdict()['dsk']
               self.logger.debug(f"dsk: {dsk}")
               return dsk
          return None

     def get_region(self) -> str | None:
          match = re.search(
               r'\[I\] (?P<region>\w+)', 
               self._run_cmd('get_region')
          )
          if match is not None:
               region = match.groupdict()['region']
               self.logger.debug(f"region {region}")
               return region
          return None

     def get_node_id(self) -> int:
          match = re.search(
               r'\[I\] (?P<node_id>\d+)',
               self._run_cmd('get_node_id')
          )
          if match is not None:
               node_id = match.groupdict()['node_id']
               self.logger.debug(f"node_id: {node_id}")
               self.node_id = int(node_id)
          return super().get_node_id()


class DevZwaveDoorLockKeypad(DevZwaveCli):

     @classmethod
     def zwave_app(cls) -> ZwaveApp:
          return 'zwave_soc_door_lock_keypad'

     def enable_sleeping(self):
          self._run_cmd('enable_sleeping')
     
     def battery_report(self):
          self._run_cmd('battery_report')

     def enter_user_code(self, four_digit_user_code: str):
          self._run_cmd(f'enter_user_code {four_digit_user_code}')
     
     def set_new_user_code(self, four_digit_user_code: str):
          self._run_cmd(f'set_new_user_code {four_digit_user_code}')

     def set_door_handle_state(self, state: Literal['activate', 'deactivate']):
          self._run_cmd(f'set_door_handle_state {state}')
     

class DevZwaveLedBulb(DevZwaveCli):

     @classmethod
     def zwave_app(cls) -> ZwaveApp:
          return 'zwave_soc_led_bulb'


class DevZwaveMultilevelSensor(DevZwaveCli):

     @classmethod
     def zwave_app(cls) -> ZwaveApp:
          return 'zwave_soc_multilevel_sensor'

     def enable_sleeping(self):
          self._run_cmd('enable_sleeping')
     
     def send_battery_and_sensor_report(self):
          self._run_cmd('send_battery_and_sensor_report')


class DevZwavePowerStrip(DevZwaveCli):

     @classmethod
     def zwave_app(cls) -> ZwaveApp:
          return 'zwave_soc_power_strip'

     def toggle_endpoint(self, endpoint: Literal[1, 2]):
          self._run_cmd(f'toggle_endpoint {endpoint}')

     def dim_endpoint(self, dimming_level: int):
          self._run_cmd(f'dim_endpoint {dimming_level}')

     def toggle_notification_sending(self):
          self._run_cmd('toggle_notification_sending')


class DevZwaveSensorPIR(DevZwaveCli):

     @classmethod
     def zwave_app(cls) -> ZwaveApp:
          return 'zwave_soc_sensor_pir'

     def enable_sleeping(self):
          self._run_cmd('enable_sleeping')
     
     def battery_report(self):
          self._run_cmd('battery_report')

     def motion_detected(self):
          self._run_cmd('motion_detected')


class DevZwaveSwitchOnOff(DevZwaveCli):

     @classmethod
     def zwave_app(cls) -> ZwaveApp:
          return 'zwave_soc_switch_on_off'

     def toggle_led(self):
          self._run_cmd('toggle_led')
     
     def send_nif(self):
          self._run_cmd('send_nif')


class DevZwaveWallController(DevZwaveCli):

     @classmethod
     def zwave_app(cls) -> ZwaveApp:
          return 'zwave_soc_wall_controller'

     def send_central_scene_key(self, key_number: Literal[1, 2, 3], key_action: Literal['press', 'hold', 'release']):
          self._run_cmd(f'send_central_scene_key {key_number} {key_action}')
