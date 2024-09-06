import os
import re
from typing import Literal
from pathlib import Path
from dataclasses import dataclass

from . import telnetlib, config
from .processes import CommanderCli
from .utils import ZwaveAppProductType, ZwaveRegion, ZwaveApp

@dataclass
class TargetDevInfo:
    part_number: str
    flash_size: str
    sram_size: str
    unique_id: str


class DevWpk(object):
    """Represents a WPK board. 
    inspired from DevWstk class in witef-core,
    this one here uses commander instead of the Jlink lib.
    """

    VCOM_PORT_OFFSET = 1
    ADMIN_PORT_OFFSET = 2
    DCH_PORT_OFFSET = 5

    def __init__(self, ):
        pass

    def __init__(self, serial_no: int, hostname: str = None, vuart_port: int = 4900):
        """Initializes the WPK board.
        :param serial_no: J-Link serial number
        :param hostname: Device's IP address or hostname
        :param chip_name: Chip name
        :param vuart_port: VUART port number (VCOM, admin and DCH port numbers are offsets)
        """
        self.serial_no = serial_no
        self.hostname = hostname
        self.vuart_port = vuart_port
        self.commander_cli = CommanderCli(self.hostname)
        try:
            self.telnet_client = telnetlib.Telnet(host=self.hostname, port=self.admin_port)
        except:
            raise Exception(f"Error trying to connect to {hostname}")
        self.telnet_prompt = self.telnet_client.read_some().decode('ascii')
        self.target_dsk = None
        self.logger = config.LOGGER.getChild(f"wpk_{self.serial_no}")
        self.tty = f"/dev/serial/by-id/usb-Silicon_Labs_J-Link_Pro_OB_000{self.serial_no}-if00"

    @property
    def vcom_port(self) -> int:
        """Gets the VCOM port (typ. 4901).
        :return: VCOM port
        """
        return self.vuart_port + DevWpk.VCOM_PORT_OFFSET

    @property
    def admin_port(self) -> int:
        """Gets the admin port (typ. 4902).
        :return: admin port
        """
        return self.vuart_port + DevWpk.ADMIN_PORT_OFFSET

    @property
    def dch_port(self) -> int:
        """Gets the DCH port (typ. 4905).
        :return: DCH port
        """
        return self.vuart_port + DevWpk.DCH_PORT_OFFSET

    def _run_admin(self, command: str) -> str:
        """Runs a command on admin interface.

        :param command: String command
        :return: string result
        """
        self.telnet_client.write(bytes(f'{command}\r\n' ,encoding='ascii'))
        return self.telnet_client.read_until(bytes(f'\r\n{self.telnet_prompt}', encoding='ascii'), timeout=1).decode('ascii')

    def reset(self):
        """Resets the WPK board itself."""
        sys_reset_sys_output = self._run_admin("sys reset sys")
        if sys_reset_sys_output != b'':
            self.logger.debug(f"sys_reset_sys_output: {sys_reset_sys_output}")
        self.telnet_client = telnetlib.Telnet(host=self.hostname, port=self.admin_port)
        self.telnet_prompt = self.telnet_client.read_some().decode('ascii')

    def target_reset(self):
        """Resets the radio board plugged into the WPK."""
        self._run_admin("target reset 1")

    @property
    def radio_board(self) -> str | None:
        """Gets the radio board name (e.g.brd4170a)
        :return: The radio board name
        """
        match = re.search(
                r'\[A2h\]\s+(?P<boardid>\w+)',
                self._run_admin("boardid")
          )
        if match:
            return match.groupdict()['boardid']
        return None

    def _get_target_devinfo(self) -> TargetDevInfo:
        device_info_output = self.commander_cli.device_info()
        for line in device_info_output.splitlines():
            if 'Part Number' in line:
                part_number = line.split(':')[1].strip()
            if 'Flash Size' in line:
                flash_size = line.split(':')[1].strip()
            if 'SRAM Size' in line:
                sram_size = line.split(':')[1].strip()
            if 'Unique ID' in line:
                eui64 = line.split(':')[1].strip()
        return TargetDevInfo(part_number, flash_size, sram_size, eui64)

    @property
    def target_devinfo(self) -> TargetDevInfo:
        """Gets the target's cached Dev Info.
        :return: TargetDevInfo dataclass
        """
        if not hasattr(self, '_target_devinfo'):
            self._target_devinfo = self._get_target_devinfo()
        return self._target_devinfo

    # does more than flashing
    def flash_target(self, firmware_path: str, signing_key_path: str = None, encrypt_key_path: str = None):
        # Z-Wave devices require all of this
        self.commander_cli.device_recover()
        self.commander_cli.device_pageerase('@userdata')
        if signing_key_path and encrypt_key_path:
            self.commander_cli.flash_tokenfiles('znet', (signing_key_path, encrypt_key_path))
        self.commander_cli.flash_token('znet', 'MFG_ZWAVE_COUNTRY_FREQ:0xFF')
        self.commander_cli.flash(firmware_path)
        cmd_output = self.commander_cli.device_zwave_qrcode()
        qr_code = re.search(r'[0-9]{90,}', cmd_output.splitlines()[0])
        if qr_code:
            self.target_dsk = qr_code.group()[12:53]


class ZwaveDevBase(object):
    """Base class for Z-Wave devices."""
    
    def __init__(self, name: str, wpk: DevWpk, region: ZwaveRegion, app_type: ZwaveApp, debug: bool = False):
        """Initializes the device.
        :param name: Device name (helps with logger)
        :param wpk: WPK hosting the radio board
        :param region: Z-Wave region 
        """
        self.name: str = name
        self.wpk: DevWpk = wpk
        self.region: str = region
        self.app_type: ZwaveApp = app_type
        self.firmware_file: str = None
        self.gbl_v255_file: str = None
        self.home_id: str = None
        self.node_id: int = None

        self.loggger = config.LOGGER.getChild(f'dev_{self.name}')
        self.radio_board = self.wpk.radio_board.lower()
        self.loggger.debug(self.radio_board)

        devinfo: TargetDevInfo = self.wpk.target_devinfo
        # Unify exposes this as an attribute called: SerialNumber, thus the name
        self.serial_number = f"h'{devinfo.unique_id.upper()}"
        
        for file in os.listdir(config.CONFIG["zwave-binaries"]):
            if (
                (self.app_type in file) and 
                (self.radio_board in file) and 
                (self.region in file) and
                (file.endswith('.hex')) and 
                not ('DEBUG' in file)
            ):
                self.firmware_file = file
                break
        
        if self.firmware_file is None:
            raise Exception(f'No suitable firmware was found for {self.name}')

        # TODO: we should check ZGM130 -> ncp controller needs to be flashed with sample keys
        if 'ncp_serial_api_controller' in self.app_type:
            btl_signing_key = config.CONFIG["zwave-btl-signing-key-controller"]
            btl_encrypt_key = config.CONFIG["zwave-btl-encrypt-key-controller"]
        else:          
            btl_signing_key = config.CONFIG["zwave-btl-signing-key-end-device"]
            btl_encrypt_key = config.CONFIG["zwave-btl-encrypt-key-end-device"]

        self.loggger.debug(f'flashing: {self.firmware_file} with: {btl_encrypt_key}, {btl_signing_key}')
        self.wpk.flash_target(f'{config.CONFIG["zwave-binaries"]}/{self.firmware_file}', signing_key_path=btl_signing_key, encrypt_key_path=btl_encrypt_key)

        self.gbl_v255_file = f'{Path(self.firmware_file).stem}_v255.gbl'
        if not os.path.exists(f'{config.CONFIG["zwave-binaries"]}/{self.gbl_v255_file}'):
            raise Exception(f'could not find matching v255.gbl file in {config.CONFIG["zwave-binaries"]}/ for {self.firmware_file}')

    # Uiid are used by Unify
    def uiid(self) -> str:
        return f"ZWave-0000-{ZwaveAppProductType[self.app_type].value:04}-0004-00-01"

    # Unid are used by Unify
    def unid(self) -> str | None:
        if self.home_id is None or self.node_id is None:
            return None
        return f"zw-{self.home_id}-{self.node_id:04}"
