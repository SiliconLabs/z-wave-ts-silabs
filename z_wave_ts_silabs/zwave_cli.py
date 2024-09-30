import re
from typing import Literal

from . import telnetlib
from .definitions import ZwaveRegion, ZwaveSocApp
from .devices import ZwaveDevBase, DevWpk


class DevZwaveCli(ZwaveDevBase):
    
     def __init__(self, name: str, wpk: DevWpk, region: ZwaveRegion, app_name: ZwaveSocApp):
          """Instantiates a Z-Wave CLI device.
          :param name: Device name
          :param wpk: The wpk with the radio board acting as an End Device
          """
          super().__init__(name, wpk, region, app_name)
          self.telnet_client = telnetlib.Telnet(wpk.hostname, '4901', 1)
          # send empty command to check if everything is working correctly
          if '>' not in self._run_cmd(''):
               raise Exception("This application does not have a CLI")
     
     def _run_cmd(self, command: str) -> str:
          self.telnet_client.write(bytes(f'{command}\n' ,encoding='ascii'))
          return self.telnet_client.read_until(b'\n> ', timeout=1).decode('ascii')

     def set_learn_mode(self) -> None:
          output = self._run_cmd(f'set_learn_mode')
          self.loggger.debug(f'set_learn_mode: {output.encode("ascii")}')

     def factory_reset(self) -> None:
          self._run_cmd('factory_reset')

     def get_dsk(self) -> str | None:
          match = re.search(
               r'\[I\] (?P<dsk>(\d{5}-){7}\d{5})', 
               self._run_cmd('get_dsk')
          )
          if match is not None:
               dsk = match.groupdict()['dsk']
               self.loggger.debug(f"dsk: {dsk}")
               return dsk
          return None

     def get_region(self) -> str | None:
          match = re.search(
               r'\[I\] (?P<region>\w+)', 
               self._run_cmd('get_region')
          )
          if match is not None:
               region = match.groupdict()['region']
               self.loggger.debug(f"region {region}")
               return region
          return None


class DevZwaveDoorLockKeypad(DevZwaveCli):
     
     def __init__(self, name: str, wpk: DevWpk, region: ZwaveRegion):
          super().__init__(name, wpk, region, 'zwave_soc_door_lock_keypad') 

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
     
     def __init__(self, name: str, wpk: DevWpk, region: ZwaveRegion):
          super().__init__(name, wpk, region, 'zwave_soc_led_bulb') 


class DevZwaveMultilevelSensor(DevZwaveCli):
     
     def __init__(self, name: str, wpk: DevWpk, region: ZwaveRegion):
          super().__init__(name, wpk, region, 'zwave_soc_multilevel_sensor') 

     def enable_sleeping(self):
          self._run_cmd('enable_sleeping')
     
     def send_battery_and_sensor_report(self):
          self._run_cmd('send_battery_and_sensor_report')


class DevZwavePowerStrip(DevZwaveCli):

     def __init__(self, name: str, wpk: DevWpk, region: ZwaveRegion):
          super().__init__(name, wpk, region, 'zwave_soc_power_strip') 
     
     def toggle_endpoint(self, endpoint: Literal[1, 2]):
          self._run_cmd(f'toggle_endpoint {endpoint}')

     def dim_endpoint(self, dimming_level: int):
          self._run_cmd(f'dim_endpoint {dimming_level}')

     def toggle_notification_sending(self):
          self._run_cmd('toggle_notification_sending')


class DevZwaveSensorPIR(DevZwaveCli):

     def __init__(self, name: str, wpk: DevWpk, region: ZwaveRegion):
          super().__init__(name, wpk, region, 'zwave_soc_sensor_pir') 
     
     def enable_sleeping(self):
          self._run_cmd('enable_sleeping')
     
     def battery_report(self):
          self._run_cmd('battery_report')

     def motion_detected(self):
          self._run_cmd('motion_detected')


class DevZwaveSwitchOnOff(DevZwaveCli):

     def __init__(self, name: str, wpk: DevWpk, region: ZwaveRegion):
          super().__init__(name, wpk, region, 'zwave_soc_switch_on_off') 
     
     def toggle_led(self):
          self._run_cmd('toggle_led')
     
     def send_nif(self):
          self._run_cmd('send_nif')


class DevZwaveWallController(DevZwaveCli):

     def __init__(self, name: str, wpk: DevWpk, region: ZwaveRegion):
          super().__init__(name, wpk, region, 'zwave_soc_wall_controller') 
     
     def send_central_scene_key(self, key_number: Literal[1, 2, 3], key_action: Literal['press', 'hold', 'release']):
          self._run_cmd(f'send_central_scene_key {key_number} {key_action}')
