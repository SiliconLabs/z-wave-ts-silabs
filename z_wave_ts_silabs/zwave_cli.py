import re
from typing import Literal

from . import telnetlib
from .definitions import AppName, ZwaveRegion
from .devices import DevZwave, DevWpk
from .session_context import SessionContext


class DevZwaveCli(DevZwave):
    
     def __init__(self, ctxt: SessionContext, device_number: int, wpk: DevWpk, region: ZwaveRegion):
          """Instantiates a Z-Wave CLI device.
          :param device_number: Device number
          :param wpk: The wpk with the radio board acting as an End Device
          """
          super().__init__(ctxt, device_number, wpk, region)
          self.telnet_client: telnetlib.Telnet | None = None

     def start(self):
          if self.telnet_client is not None:
               self.logger.debug(f"start() was called on a running instance of {self.__class__.__name__}")
               return

          self.telnet_client = telnetlib.Telnet(self.wpk.ip, '4901', 1)
          # send empty command to check if everything is working correctly
          if '>' not in self._run_cmd(''):
               raise Exception("This application does not have a CLI")

     def stop(self):
          if self.telnet_client is None:
               self.logger.debug(f"stop() was called on a stopped instance of {self.__class__.__name__}")
               return

          self.telnet_client.close()
          self.telnet_client = None

     def _run_cmd(self, command: str) -> str:
          """Execute a command and return the response.

          1. Clears any pending data in the buffer.
          2. Sends the command to the device.
          3. Reads the response in 2 phases:
               - First, wait for the command echo.
               - Then, wait for the next prompt (">").
          :param command: The command to execute
          :return: The response from the command
          """
          # clear any pending data
          self.telnet_client.read_very_eager()
          # Send the command
          try:
               self.telnet_client.write(bytes(f'{command}\n', encoding='ascii'))
          except BrokenPipeError:
               # Reconnect and retry on pipe error
               self.stop()
               self.start()
          
          # Wait for initial response - command echo
          response = ""
          try:
               # First read until we see our command echoed back
               response += self.telnet_client.read_until(bytes(f'{command}\n', 'ascii'), timeout=1).decode('ascii')
               
               # Then read until the next prompt (">")
               response += self.telnet_client.read_until(b'> ', timeout=1).decode('ascii')
               
               if command not in response or '> ' not in response:
                    self.logger.debug(f'Command response not properly synchronized: {response}')
                    # Might be reading problem, try to recover by reading all data (very_eager)
                    extra = self.telnet_client.read_very_eager().decode('ascii', errors='ignore')
                    if extra:
                         response += extra
                         self.logger.debug(f'Additional data: {extra}')
                         
          except BrokenPipeError as e:
               # Connection closed, try to recover
               self.stop()
               self.start()

          except UnicodeDecodeError as e:
               raise Exception(f"UnicodeDecodeError: {e}") from e
          
          except Exception as e:
               raise Exception(f"Unexpected error: {e}") from e
          
          return response

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
               r'\[I\] (?P<node_id>[0-9A-F]{4})',
               self._run_cmd('get_node_id')
          )
          if match is not None:
               self.node_id = int(match.groupdict()['node_id'], base=16)
               self.logger.debug(f"node_id: {self.node_id}")
          return super().get_node_id()

     def get_home_id(self) -> str:
          match = re.search(
               r'\[I\] (?P<home_id>[0-9A-F]{8})',
               self._run_cmd('get_home_id')
          )
          if match is not None:
               self.home_id = match.groupdict()['home_id']
               self.logger.debug(f"home_id: {self.home_id}")
          return super().get_home_id()

     # TODO: process output
     def node_id_filtering_enforce(self, enforce : bool):
          self._run_cmd(f'node_id_filtering_enforce { 1 if enforce else 0 }')

     def node_id_filtering_add(self, node_id : int):
          self._run_cmd(f'node_id_filtering_add {node_id}')

     def node_id_filtering_remove(self, node_id : int):
          self._run_cmd(f'node_id_filtering_remove {node_id}')

     def node_id_filtering_clear(self):
          self._run_cmd('node_id_filtering_clear')


class DevZwaveDoorLockKeypad(DevZwaveCli):

     @classmethod
     def app_name(cls) -> AppName:
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
     def app_name(cls) -> AppName:
          return 'zwave_soc_led_bulb'


class DevZwaveMultilevelSensor(DevZwaveCli):

     def start(self):
          super().start()
          self.disable_sleeping()
     
     @classmethod
     def app_name(cls) -> AppName:
          return 'zwave_soc_multilevel_sensor'

     def enable_sleeping(self):
          self._run_cmd('sleeping enable')

     def disable_sleeping(self):
          self._run_cmd('sleeping disable')
     
     def send_battery_and_sensor_report(self):
          self._run_cmd('send_battery_and_sensor_report')


class DevZwavePowerStrip(DevZwaveCli):

     @classmethod
     def app_name(cls) -> AppName:
          return 'zwave_soc_power_strip'

     def toggle_endpoint(self, endpoint: Literal[1, 2]):
          self._run_cmd(f'toggle_endpoint {endpoint}')

     def dim_endpoint(self, dimming_level: int):
          self._run_cmd(f'dim_endpoint {dimming_level}')

     def toggle_notification_sending(self):
          self._run_cmd('toggle_notification_sending')


class DevZwaveSensorPIR(DevZwaveCli):

     def start(self):
          super().start()
          self.disable_sleeping()
     
     @classmethod
     def app_name(cls) -> AppName:
          return 'zwave_soc_sensor_pir'

     def enable_sleeping(self):
          self._run_cmd('sleeping enable')

     def disable_sleeping(self):
          self._run_cmd('sleeping disable')
     
     def battery_report(self):
          self._run_cmd('battery_report')

     def motion_detected(self):
          self._run_cmd('motion_detected')


class DevZwaveSwitchOnOff(DevZwaveCli):

     @classmethod
     def app_name(cls) -> AppName:
          return 'zwave_soc_switch_on_off'

     def toggle_led(self):
          self._run_cmd('toggle_led')
     
     def send_nif(self):
          self._run_cmd('send_nif')


class DevZwaveWallController(DevZwaveCli):

     @classmethod
     def app_name(cls) -> AppName:
          return 'zwave_soc_wall_controller'

     def send_central_scene_key(self, key_number: Literal[1, 2, 3], key_action: Literal['press', 'hold', 'release']):
          self._run_cmd(f'send_central_scene_key {key_number} {key_action}')
