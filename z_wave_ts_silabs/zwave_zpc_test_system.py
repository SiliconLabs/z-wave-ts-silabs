import json
import time
import logging
from pathlib import Path
from contextlib import contextmanager

import paho.mqtt.client as mqtt

from .definitions import ZwaveRegion
from .processes import ZpcTestSystem
from .session_context import SessionContext


class ZpcTestSystemInterface(object):

    def __init__(self, controller_name: str, region: ZwaveRegion, ctxt: SessionContext, ncp_pty: str) -> None:
        self._logger = logging.getLogger(f"{self.__class__.__name__}:{ncp_pty}")

        self._zpc_test_system_process: ZpcTestSystem | None = None
        self._mqtt_client: mqtt.Client | None = None
        # will be used to store the last registered command and it's return value
        self._registered_mqtt_command: str | None = None
        self._registered_mqtt_command_return_value: dict | None = None

        self._controller_name = controller_name
        self._region = region
        self._ctxt = ctxt
        self._ncp_pty = ncp_pty

        self._mqtt_host = Path(self._ctxt.current_test_logdir / f"mqtt_sock_{controller_name}")

        self.start()

    def _start_mqtt_client(self, mqtt_host: Path):
        self._mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, transport='unix')
        self._mqtt_client.on_connect = self._on_mqtt_connect
        self._mqtt_client.on_message = self._on_mqtt_message
        self._mqtt_client.connect(mqtt_host.as_posix()) # keepalive is 60 by default, we only use a broker that's running on localhost
        self._mqtt_client.loop_start()

        self._logger.debug('mqtt_client: connected to broker')

        # will be used to store the last registered command and it's return value
        self._registered_mqtt_command = None
        self._registered_mqtt_command_return_value = None

    def _stop_mqtt_client(self):
        if self._mqtt_client is not None:
            # TODO: check return values of these functions
            self._mqtt_client.loop_stop()
            self._mqtt_client.disconnect()
            self._mqtt_client = None

    # The callback for when the client receives a CONNACK response from the server.
    def _on_mqtt_connect(self, client, userdata, flags, reason_code, properties):
        # TODO: check reason_code
        self._logger.debug(f'connected with result code {reason_code}')
        # Subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed.
        #TODO: error message if we can't subscribe to this topic
        self._mqtt_client.subscribe("#")

    # The callback for when a PUBLISH message is received from the server.
    def _on_mqtt_message(self, client, userdata, msg):
        # msg.topic     type: str
        # msg.payload   type: bytes (should be JSON, ascii encoded ?)

        if 'zpc/test_system/callbacks' in msg.topic:
            self._logger.debug(f'received message {msg.topic}: {msg.payload.decode("utf-8")}')

            if 'zpc/test_system/callbacks' in msg.topic:
                if 'on_dsk_report' in msg.topic:
                    pass

        if (self._registered_mqtt_command is not None) and (f'zpc/test_system/command_result/{self._registered_mqtt_command}' in msg.topic):
            self._logger.info(f'received command return value: {self._registered_mqtt_command}, {msg.topic}: {msg.payload.decode("utf-8")}')
            self._registered_mqtt_command = None
            self._registered_mqtt_command_return_value = json.loads(msg.payload)

    def _send_mqtt_command(self, command: str, payload: dict) -> dict:
        self._registered_mqtt_command = command

        topic   = f'zpc/test_system/commands/{command}'
        payload = bytes(json.dumps(payload), encoding='ascii')
        self._mqtt_client.publish(topic, payload, qos=1)

        # TODO: add a timeout here for the response (second ?)
        timeout = 1000000000 # 1 billion ns = 1s
        t0 = time.time_ns()
        while self._registered_mqtt_command_return_value is None:
            if time.time_ns() - t0 > timeout:
                raise TimeoutError
            pass
        t1 = time.time_ns()
        self._logger.info(f'getting command return value took {(t1 - t0) // 1000} us')
        ret: dict = self._registered_mqtt_command_return_value

        # reset the value
        self._registered_mqtt_command_return_value = None

        return ret

    def start(self):
        self._zpc_test_system_process = ZpcTestSystem(self._controller_name, self._ctxt, self._region, self._ncp_pty, self._mqtt_host)
        self._start_mqtt_client(self._mqtt_host)

    def stop(self):
        self._stop_mqtt_client()
        if self._zpc_test_system_process is not None:
            self._zpc_test_system_process.stop()

    def get_keys(self) -> list[tuple[int, bytes]]: # SecurityScheme instead of int in testlib_proxy
        keys: list[tuple[int, bytes]] = []
        for scheme in [
            0x80, # SecurityScheme.S0,
            0x04, # SecurityScheme.S2_ACCESS,
            0x02, # SecurityScheme.S2_AUTHENTICATED,
            0x01, # SecurityScheme.S2_UNAUTHENTICATED,
            0x10, # SecurityScheme.S2_ACCESS_LR,
            0x08, # SecurityScheme.S2_AUTHENTICATED_LR
       ]:
            ret = self._send_mqtt_command('keystore_network_key_read', {"keyclass": scheme})
            if ret["key"] is not None:
                keys.append((scheme, ret["key"]))

        self._logger.info(f'get_keys:')
        for key in keys:
            key_str = ''
            for byte in key[1]:
                key_str += f'{byte:X}'
            self._logger.info(f'scheme: {hex(key[0])}, key: {key_str}')
        return keys

    def get_node_id(self) -> int:
        ret = self._send_mqtt_command('zwapi_memory_get_ids', {})
        self._logger.info(f'get_node_id: {ret["node_id"]}')
        return ret["node_id"]

    def get_home_id(self) -> int:
        ret = self._send_mqtt_command('zwapi_memory_get_ids', {})
        self._logger.info(f'get_home_id: {ret["home_id"]:X}')
        return ret["home_id"]

    # was def send(self, node_id: int, cmd: CmdBase | bytes | str, tx_opt: TransmitOption = (TransmitOption.ACK | TransmitOption.AUTO_ROUTE | TransmitOption.EXPLORE)) -> tuple[TxStatus, TxReport]:
    def send(self, node_id: int, cmd: bytes, tx_opt: int = (0x01 | 0x04 | 0x20)) -> tuple[int, int]:
        self._logger.info(f'send to {node_id}, cmd: {cmd}')
        cmd_str = ''
        for byte in cmd:
            cmd_str += f'{byte:02X}'
        ret = self._send_mqtt_command('zwapi_send_data', {
            "destination_node_id": node_id,
            "data": cmd_str,
            "tx_options": tx_opt
        })
        self._logger.info(f'send status: {ret["status"]}')
        return 0, 0 # TODO: the tuple should come from a callback on MQTT. logic has to be added in the mqtt_client for this.

    # was def send_multicast(self, node_ids: list[int], cmd: CmdBase | bytes | str, tx_opt: TransmitOption = TransmitOption(0)) -> TxStatus:
    def send_multicast(self, node_ids: list[int], cmd: bytes, tx_opt: int = 0) -> int:
        self._logger.info(f'send_multicast to {node_ids}, cmd: {cmd}')
        cmd_str = ''
        for byte in cmd:
            cmd_str += f'{byte:02X}'
        ret = self._send_mqtt_command('zwapi_send_data_multi', {
            "destination_node_id": node_ids,
            "data": cmd_str,
            "tx_options": tx_opt
        })
        self._logger.info(f'send status: {ret["status"]}')
        return 0 # TODO: the return value should come from a callback on MQTT. logic has to be added in the mqtt_client for this.

    # was def send_nop(self, node_id: int) -> tuple[TxStatus, TxReport]:
    def send_nop(self, node_id: int) -> tuple[int, int]:
        self._logger.info(f'send_nop to {node_id}')
        return self.send(node_id, bytes([0x00]))

    # was def send_secure(self, node_id: int, cmd: CmdBase | bytes | str, scheme: SecurityScheme = SecurityScheme.ALL) -> tuple[TxStatus, TxReport]:
    def send_secure(self, node_id: int, cmd: bytes, scheme: int = (0x80 | 0x01 | 0x02 | 0x04)) -> tuple[int, int]:
        self._logger.info(f'send_secure to {node_id}, cmd: {cmd}, scheme: {scheme}')
        # allowed_schemes = [SecurityScheme.NONE, SecurityScheme.S0, SecurityScheme.S2_UNAUTHENTICATED, SecurityScheme.S2_AUTHENTICATED, SecurityScheme.S2_ACCESS]
        # not_allowed = SecurityScheme.S2_ACCESS_LR | SecurityScheme.S2_AUTHENTICATED_LR
        allowed_schemes = [0x00, 0x80, 0x01, 0x02, 0x04]
        not_allowed = 0x08 | 0x10
        if scheme & not_allowed != 0:
            raise ValueError(f'Invalid scheme, allowed schemes: {allowed_schemes}')

        if scheme != 0x00:
            if node_id == 0xFF:
                raise ValueError(f'Invalid scheme for broadcast frame, allowed schemes: {[0x00]}')

            granted_keys = self._storage.get_attribute(node_id, SecurityScheme)
            if granted_keys is None:
                our_node_id = self.get_node_id()
                granted_keys = self._storage.get_attribute(our_node_id, SecurityScheme)
                assert granted_keys is not None, 'Unknown granted keys'
                protocol = self._storage.get_attribute(our_node_id, Protocol)
                assert protocol is not None, 'Unknown protocol'
                self._storage.set_attribute(node_id, granted_keys)
                self._storage.set_attribute(node_id, protocol)
                if granted_keys & (SecurityScheme.S2 | SecurityScheme.S2_LR):
                    self._storage.set_attribute(node_id, S2CapableAttribute())

            scheme = scheme & granted_keys

        cmd_str = ''
        for byte in cmd:
            cmd_str += f'{byte:02X}'
        ret = self._send_mqtt_command('zwapi_send_data', {

        })
        self._logger.info(f'send_secure status: {ret["status"]}')
        return 0, 0 # TODO: the tuple should come from a callback on MQTT. logic has to be added in the mqtt_client for this.

    # was def create_multicast_group(self, node_ids: list[int]) -> MulticastGroup:
    def create_multicast_group(self, node_ids: list[int]) -> int:
        pass

    # was def send_secure_multicast(self, group: MulticastGroup, cmd: CmdBase | bytes | str, scheme: SecurityScheme = SecurityScheme.ALL, send_follow_ups: bool = True) -> tuple[TxStatus, TxReport]:
    def send_secure_multicast(self, group: int, cmd: bytes, scheme: int = (0x80 | 0x01 | 0x02 | 0x04), send_follow_ups: bool = True) -> tuple[int, int]:
        pass

    # was def send_test_frame(self, node_id: int, power: RfPowerLevel) -> tuple[TxStatus, TxReport]:
    def send_test_frame(self, node_id: int, power: int) -> tuple[int, int]:
        ret = self._send_mqtt_command('zwave_tx_send_test_frame', {
            "destination_node_id": node_id,
            "power_level": power,
        })
        return 0, 0 # TODO: should be retrieved from a callback on MQTT.

    def send_nif(self, dst_node_id: int): # was -> TxStatus:

        tx_options = 0x04 | 0x20 # TransmitOption.AUTO_ROUTE | TransmitOption.EXPLORE
        if dst_node_id != 0xFF:
            tx_options = tx_options | 0x01 # TransmitOption.ACK
        ret = self._send_mqtt_command('zwapi_send_node_information', {
            "destination_node_id": dst_node_id,
            "tx_options": tx_options
        })

    def request_nif(self, node_id: int):
        ret = self._send_mqtt_command('zwapi_request_node_info', {
            "destination_node_id": node_id,
        })

    @contextmanager
    def start_learn_mode(self, mode: int = 0): # was mode: LearnMode = LearnMode.CLASSIC
        # mode: LearnMode, CLASSIC = 1, NWI = 2, NWE = 3
        ret = self._send_mqtt_command('zwave_network_management_learn_mode', {
            "mode": mode,
        })
        # TODO: wait for NMState.LEARN_MODE
        yield
        # TODO: wait for NMState.IDLE

    def stop_learn_mode(self):
        ret = self._send_mqtt_command('zwave_network_management_learn_mode', {
            "mode": 0,
        })

    def start_nwi(self):
        ret = self._send_mqtt_command('zwave_network_management_add_node', {})
        if ret["status"] != 0:
            raise Exception(f"start_nwi status: {ret["status"]}")

    def start_nwe(self):
        ret = self._send_mqtt_command('zwave_network_management_remove_node', {})
        if ret["status"] != 0:
            raise Exception(f"start_nwe status: {ret["status"]}")

    def abort(self):
        ret = self._send_mqtt_command('zwave_network_management_abort', {})
        if ret["status"] != 0:
            raise Exception(f"abort status: {ret["status"]}")
        # TODO: wait for NMState.IDLE

    def get_dsk(self): # was -> Dsk:
        # TODO: find a function to get the DSK, the testlib uses it's internal storage (that may be why we have SPAN resynchro)
        ret = self._send_mqtt_command('zwave_s2_keystore_get_dsk', {})
        self._logger.info(f'get_dsk: {ret["dsk"]}')
        return ret["dsk"]

    def set_as_sis(self, node_id: int):
        # TODO: seems complicated. We'll see afterwards
        pass

    def get_suc_node_id(self) -> int:
        ret = self._send_mqtt_command('zwapi_get_suc_node_id', {})
        self._logger.info(f'get_suc_node_id: {ret["node_id"]}')
        return ret["node_id"]

    def is_sis(self) -> bool:
        ret = self._send_mqtt_command('zwave_network_management_is_zpc_sis', {})
        self._logger.info(f'is_sis: {ret["sis"]}')
        return ret["sis"]

    def set_default(self):
        # zwave_network_management_set_default

        # TODO: wait for NMState.IDLE
        pass

    def network_update(self):
        ret = self._send_mqtt_command('zwapi_request_network_update', {})
        if ret["status"] != 0:
            raise Exception(f"abort status: {ret["status"]}")

    # was def add_node(self, security_scheme: SecurityScheme = SecurityScheme.NONE, dsk: Dsk | None = None, *, nwi: bool = False, auto_set_as_sis: bool = True, send_no_more_info: bool = True, set_lifeline: bool = True) -> AddNodeResult:
    def add_node(self, security_scheme: int = 0, dsk: int | None = None, *, nwi: bool = False, auto_set_as_sis: bool = True, send_no_more_info: bool = True, set_lifeline: bool = True):
        ret = self._send_mqtt_command('zwave_network_management_add_node_classic', {})
        if ret["status"] != 0:
            raise Exception(f"add_node status: {ret["status"]}")
        # TODO: add a way to register something in the on_message handler of the client (at least the result from the command)

    def remove_node(self, *, nwe: bool = False) -> int | None:
        ret = self._send_mqtt_command('zwave_network_management_remove_node_classic', {})
        if ret["status"] != 0:
            raise Exception(f"remove_node status: {ret["status"]}")
        # TODO: wait for NMState.WAITING_FOR_NODE_REMOVAL
        # TODO: wait for NMState.IDLE

    def remove_failed(self, node_id: int):
        ret = self._send_mqtt_command('zwave_network_management_remove_failed', {})
        if ret["status"] != 0:
            raise Exception(f"remove_node status: {ret["status"]}")

        # TODO: wait for NMState.IDLE
        # TODO: find a way to retrieve the node ID of the node that just got removed

    def enable_smart_start_learn_mode(self, enable: bool = True):
        # zwave_network_management_enable_smart_start_learn_mode
        pass

    def enable_smart_start_add_mode(self, enable: bool = True):
        # zwave_network_management_enable_smart_start_add_mode
        pass

    def add_to_provisioning_list(self, entry: int): # was entry: ProvisioningListEntry
        # TODO: just store the entry somewhere in a list
        pass

    def remove_from_provisioning_list(self, dsk: int): # was dsk: Dsk
        # TODO: remove from the list mentioned earlier
        pass

    def wait_smart_start_node_added(self): # was -> AddNodeResult:
        # TODO: wait for some callback values (_on_node_added, _on_error)
        # TODO: if there's a NM_ERROR in a callback check it and raise an Exception
        pass

    def assign_return_route(self, node_id: int, dst_node_id: int):
        # zwapi_assign_return_route
        pass

    def assign_suc_return_route(self, node_id: int):
        # zwapi_assign_suc_return_route
        pass

    def assign_priority_return_route(self, node_id: int, dst_node_id: int, route: list[int], speed: int): # was speed: DataRate
        # TODO: check length of route
        # zwapi_assign_priority_return_route
        pass

    def assign_priority_suc_return_route(self, node_id: int, route: list[int], speed: int): # was speed: DataRate
        # zwapi_assign_priority_suc_return_route
        pass

    def shift(self) -> int:
        # zwapi_transfer_primary_ctrl_role
        # TODO: and it has to be called twice with magic numbers 2 and 5 ?
        # TODO: also look for a callback return value and check against: LearnModeStatus.UNDOCUMENTED_VALUE, LearnModeStatus.DONE, LearnModeStatus.FAILED
        # TODO: this callback will also return the Node ID of the node which will get the new role so it needs to be retrieved.
        pass

    def get_node_list(self) -> list[int]:
        ret = self._send_mqtt_command('zwapi_get_full_node_list', {})
        node_list = []
        return_early = False
        for nodemask in ret["node_list"]:
            if return_early:
                break

            for i in range(0,8):
                if nodemask & (0x01 << i):
                    node_list.append(i+1)
                else:
                    return_early = True
                    break

        self._logger.info(f'get_node_list: {node_list}')
        return node_list

    def is_node_failed(self, node_id: int) -> bool:
        ret = self._send_mqtt_command('zwapi_is_node_failed', {
            'node_id': node_id
        })
        # bool type in C is either 0 for false and any other value for true.
        return ret["status"] != 0

    def get_failed_node_list(self) -> list[int]:
        node_list = self.get_node_list()
        return list(filter(self.is_node_failed, node_list))

    def get_controller_capabilities(self) -> int:
        # class ControllerCapabilities(IntFlag):
        #     CONTROLLER_IS_SECONDARY = 0x01
        #     CONTROLLER_ON_OTHER_NETWORK = 0x02
        #     CONTROLLER_NODEID_SERVER_PRESENT = 0x04
        #     CONTROLLER_IS_REAL_PRIMARY = 0x08
        #     CONTROLLER_IS_SUC = 0x10
        #     NO_NODES_INCLUDED = 0x20
        ret = self._send_mqtt_command('zwapi_get_controller_capabilities', {})
        return 0 # TODO: check in the MQTT client the return value of the function.

    @contextmanager
    def app_cmd_queue(self):
        pass

    # @property
    # def association(self) -> AssociationAPI:
    #     pass

    # @property
    # def ertt(self) -> ErttAPI:
    #     pass
