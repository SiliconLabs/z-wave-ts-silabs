import re
import time
from typing import Literal, TypedDict

from . import telnetlib
from .definitions import AppName, ZwaveRegion
from .devices import DevZwave, DevWpk
from .session_context import SessionContext


class LbtThresholds(TypedDict):
    """Structure pour stocker les seuils LBT de chaque canal."""
    CH0: int
    CH1: int
    CH2: int
    CH3: int


class MonitorStatus(TypedDict):
    """Structure pour stocker l'état de monitoring de l'end device."""
    tx_queue_low_priority: tuple[int, int]  # (current, max)
    tx_queue_high_priority: tuple[int, int]  # (current, max)
    waiting_for_ack: bool
    transmitting: bool
    radio_state: str  # IDLE, RX, TX, ACTIVE


class DevZWaveCliError(Exception):
    """Exception raised when Z-Wave CLI connection fails after all retry attempts.

    This allows clients to specifically handle CLI connection failures
    separately from other types of exceptions.
    """
    pass


class DevZwaveCli(DevZwave):

     def __init__(self, ctxt: SessionContext, device_number: int, wpk: DevWpk,
                  region: ZwaveRegion, wpk_serial_speed=9600):
          """Instantiates a Z-Wave CLI device.
          :param device_number: Device number
          :param wpk: The wpk with the radio board acting as an End Device
          :vcom_speed: Baud rate of the WPK serial communication
          """

          self.wpk_serial_speed = wpk_serial_speed
          super().__init__(ctxt, device_number, wpk, region)
          self.telnet_client: telnetlib.Telnet | None = None

     def start(self) -> bool:
          """
          Attempt to establish a Telnet CLI connection to the Z-Wave device.

          Tries up to three times to connect to the device's CLI using Telnet.
          If the connection is already open, logs an error and returns False.
          On each attempt, sends a CRLF and checks for the CLI prompt.
          If successful, returns True. If all attempts fail, raises DevZWaveCliError.

          :returns: True if the CLI connection is established, False if already running.
          :raises DevZWaveCliError: If unable to establish CLI connection after all attempts.
          """
          self.wpk._run_admin(f"serial vcom config speed {self.wpk_serial_speed}");

          if self.telnet_client is not None:
               self.logger.error(f"start() was called on a running instance of {self.__class__.__name__}")
               return False

          max_attempts = 3
          for attempt in range(max_attempts):
               time.sleep(0.5 * attempt)
               try:
                    self.telnet_client = telnetlib.Telnet(self.wpk.ip, '4901', 1)
               except Exception as e:
                    self.logger.debug(f"CLI connection attempt {attempt + 1} failed: {e}")
                    continue

               response = ""
               try:
                    self.telnet_client.read_very_eager()
                    self.telnet_client.write(b'\r\n')
                    response = self.telnet_client.read_until(b'> ', timeout=3.0)
               except Exception as e:
                    self.logger.debug(f"CLI test failed on attempt {attempt + 1}: {e}")

               if response and b'>' in response:
                    return True
               else:
                    self.logger.debug(f"Instead of CLI the prompt got: {response} ")

               if self.telnet_client:
                    self.telnet_client.close()
                    self.telnet_client = None

          raise DevZWaveCliError(
            f"Failed to establish CLI connection after {max_attempts} attempts")

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
               self.telnet_client.write(f'{command}\r\n'.encode('ascii'))
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
                    self.logger.warning(f'Command response not properly synchronized: {response}')
                    # Might be reading problem, try to recover by reading all data (very_eager)
                    extra = self.telnet_client.read_very_eager().decode('ascii', errors='ignore')
                    if extra:
                         response += extra
                         self.logger.warning(f'Additional data: {extra}')

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

     def lbt_threshold_set(self, level: int) -> None:
          """Définit le seuil LBT pour tous les canaux radio.
          
          :param level: Valeur du seuil LBT en dBm (int8_t, plage -128 à 127)
          """
          if not (-128 <= level <= 127):
               raise ValueError(f"LBT threshold level must be between -128 and 127, got {level}")
          self._run_cmd(f'lbt_threshold_set {level}')

     def lbt_threshold_get(self) -> LbtThresholds:
          """Récupère les valeurs actuelles du seuil LBT pour tous les canaux radio.
          
          :return: Dictionnaire contenant les seuils LBT pour CH0, CH1, CH2, CH3 en dBm
          """
          output = self._run_cmd('lbt_threshold_get')
          
          # Pattern pour extraire les valeurs: "[I] LBT threshold CH0: -80 dBm"
          pattern = r'\[I\] LBT threshold CH(?P<channel>\d+): (?P<threshold>-?\d+) dBm'
          matches = re.findall(pattern, output)
          
          thresholds: LbtThresholds = {'CH0': 0, 'CH1': 0, 'CH2': 0, 'CH3': 0}
          
          for channel_str, threshold_str in matches:
               channel_num = int(channel_str)
               if 0 <= channel_num <= 3:
                    thresholds[f'CH{channel_num}'] = int(threshold_str)
          
          self.logger.debug(f"LBT thresholds: {thresholds}")
          return thresholds

     def get_status(self) -> MonitorStatus:
          """Récupère l'état actuel de l'end device.
          
          :return: Dictionnaire contenant l'état de monitoring (TxQueue, ACK, transmission, radio)
          """
          output = self._run_cmd('monitor')
          
          # Pattern pour TxQueue Low Priority: "[I] TxQueue Low Priority: 2/3"
          low_priority_match = re.search(
               r'\[I\] TxQueue Low Priority: (?P<current>\d+)/(?P<max>\d+)',
               output
          )
          
          # Pattern pour TxQueue High Priority: "[I] TxQueue High Priority: 1/4"
          high_priority_match = re.search(
               r'\[I\] TxQueue High Priority: (?P<current>\d+)/(?P<max>\d+)',
               output
          )
          
          # Pattern pour Waiting for ACK: "[I] Waiting for ACK: Yes" ou "No"
          ack_match = re.search(
               r'\[I\] Waiting for ACK: (?P<waiting>Yes|No)',
               output
          )
          
          # Pattern pour Transmitting: "[I] Transmitting: Yes" ou "No"
          transmitting_match = re.search(
               r'\[I\] Transmitting: (?P<transmitting>Yes|No)',
               output
          )
          
          # Pattern pour Radio State: "[I] Radio State: RX"
          radio_state_match = re.search(
               r'\[I\] Radio State: (?P<state>\w+)',
               output
          )
          
          status: MonitorStatus = {
               'tx_queue_low_priority': (
                    int(low_priority_match.group('current')) if low_priority_match else 0,
                    int(low_priority_match.group('max')) if low_priority_match else 3
               ),
               'tx_queue_high_priority': (
                    int(high_priority_match.group('current')) if high_priority_match else 0,
                    int(high_priority_match.group('max')) if high_priority_match else 4
               ),
               'waiting_for_ack': ack_match.group('waiting') == 'Yes' if ack_match else False,
               'transmitting': transmitting_match.group('transmitting') == 'Yes' if transmitting_match else False,
               'radio_state': radio_state_match.group('state') if radio_state_match else 'UNKNOWN'
          }
          
          self.logger.debug(f"Monitor status: {status}")
          return status


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
