from . import telnetlib, AppName
from .definitions import RAILZwaveRegionID, ZwaveRegion
from .devices import Device, DevWpk
from .session_context import SessionContext


class DevRailtest(Device):

    @classmethod
    def app_name(cls) -> AppName:
        return 'railtest'

    def __init__(self, ctxt: SessionContext, device_number: int, wpk: DevWpk, region: ZwaveRegion):
        super().__init__(ctxt, device_number, wpk, region)
        self.telnet_client: telnetlib.Telnet | None = None

        self.region_id = self.rail_region_id(region)

        self.wpk.flash_target(
            firmware_path=f'{ctxt.zwave_binaries}/{self._firmware_file}',
        )

    def rail_region_id(self, region: str):
        rail_region = region.replace('REGION_', '') if 'REGION_' in region else region
        if '_LR' in rail_region:
            rail_region = rail_region.replace('_LR', '_LR3')
        return RAILZwaveRegionID[rail_region].value - 1 # RAILZwaveRegionID are all offset by 1 in railtest CLI

    def _run_cmd(self, command: str) -> str:
        try:
            self.telnet_client.write(bytes(f'{command}\r\n' ,encoding='ascii'))
        except BrokenPipeError as e: # single retry of the command
            self.telnet_client.close()
            self.telnet_client = telnetlib.Telnet(self.wpk.ip, '4901', 1)
            self.telnet_client.write(bytes(f'{command}\r\n' ,encoding='ascii'))
        return self.telnet_client.read_until(b'\r\n> ', timeout=1).decode('ascii')

    def start(self):
        if self.telnet_client is not None:
            self.logger.debug(f"start() was called on a running instance of {self.__class__.__name__}")
            return

        self.telnet_client = telnetlib.Telnet(self.wpk.ip, '4901', 1)
        # send empty command to check if everything is working correctly
        if '>' not in self._run_cmd(''):
            raise Exception("This application does not have a CLI")
        self.setup_zwave(self.region_id)

    def setup_zwave(self, region: int):
        self._run_cmd('reset')
        self._run_cmd('rx 0') # disable Rx
        self._run_cmd('enableRxChannelHopping 0') # disable channel hopping
        self._run_cmd('setZwaveMode 1 3') # enable Z-Wave, 
        self._run_cmd(f'setZwaveRegion {region}') # set the Z-Wave region
        self._run_cmd(f'setPower 1 raw') # sets the output power to its lowest value

    def stop(self):
        if self.telnet_client is None:
            self.logger.debug(f"stop() was called on a stopped instance of {self.__class__.__name__}")
            return

        self.telnet_client.close()

    # the setTxPayload CLI takes a string as argument and cannot take a big string, so we have to split it into chunks.
    # chunks have an offset and an associated string
    def tx_payload_chunk_list(self, payload: bytes, chunk_size: int) -> list[(int, str)]:
        chunk_list = []
        chunk: str = ''
        chunk_offset: int = 0
        for i in range(0, len(payload)):
            chunk += f' 0x{payload[i]:02X}'
            if 0 == ((i+1) % chunk_size) or i == (len(payload) - 1):
                chunk_list.append((chunk_offset, chunk))
                # this last part is not useful if i == (len(payload) - 1)
                chunk = '' # reset the chunk value
                chunk_offset = i+1 # update chunk offset

        return chunk_list

    def tx(self, payload: bytes, region: str, channel: int, break_crc: bool = False):
        region_id = self.rail_region_id(region)
        self.setup_zwave(region_id)

        self._run_cmd(f'setChannel {channel}')
        self._run_cmd(f'setTxLength {len(payload)}')

        chunk_list: list[(int, str)] = self.tx_payload_chunk_list(payload, 16)
        for chunk_offset, chunk in chunk_list:
            output = self._run_cmd(f'setTxPayload {chunk_offset}{chunk}')
            self.logger.info(output)

        if break_crc:
            self._run_cmd(f'setCrcInitVal 0')

        self._run_cmd('tx 1') # only send one frame

        if break_crc:
            self._run_cmd(f'resetCrcInitVal')
