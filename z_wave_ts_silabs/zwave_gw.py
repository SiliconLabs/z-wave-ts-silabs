import os
import re
import json
import time
import paho.mqtt.client as mqtt

from .definitions import AppName, ZwaveRegion
from .devices import DevZwave, DevWpk
from .processes import Zpc, UicUpvl, UicImageProvider
from .session_context import SessionContext


class DevZwaveGwZpc(DevZwave):
    """ZPC Z-Wave Gateway (based on UnifySDK)."""

    @classmethod
    def app_name(cls) -> AppName:
        return 'zwave_ncp_serial_api_controller'

    def __init__(self, ctxt: SessionContext, device_number: int, wpk: DevWpk, region: ZwaveRegion) -> None:
        """Initializes the device.
        :param device_number: The device name
        :param wpk: The wpk with the radio board acting as NCP
        :param region: The Z-Wave region of the device
        """
        self.zpc_process: Zpc | None = None
        self.uic_upvl_process: UicUpvl | None = None
        self.uic_image_provider_process: UicImageProvider | None = None
        self.mqtt_client: MqttClientZpc | None = None
        # TODO: maybe create a class with the fields below (Some of these states need to be shared with the MQTT client):
        self.network_dict: dict | None = None
        self.ota_status: dict | None = None
        self.command_status: dict | None = None
        self.dsk_list: dict | None = None

        super().__init__(ctxt, device_number, wpk, region)

    # should be called by the device factory
    def start(self):
        super().start() # important: otherwise the rtt and pti loggers are not started
        if self.zpc_process is not None and self.zpc_process.is_alive:
            raise Exception("ZPC process is already running")

        self.logger.debug('zpc process starting')
        self.zpc_process = Zpc(self._ctxt, self.region, self.wpk.hostname)
        if not self.zpc_process.is_alive:
            raise Exception("zpc process did not start or died unexpectedly")
        self.logger.debug('zpc process started')

        self.home_id = self.zpc_process.home_id
        self.logger.debug(f'Home ID: {self.home_id}')

        self.node_id = int(self.zpc_process.node_id)
        self.logger.debug(f'Node ID: {self.node_id}')

        # according to: uic/components/unify_dotdot_attribute_store/src/unify_dotdot_attribute_store_node_state.cpp
        # Nodes can be in these states
        # "Online interviewing", "Online functional", "Online non-functional", "Online interviewing", "Offline", "Unavailable"
        self.network_dict = {self.node_id: "Offline"}
        self.ota_status = {}  # node_id: None (default), True if finished, False if issue -> it sucks, make it a property or something
        self.command_status = {}  # node_id: { "command" : "state" }, and then do something about the state.
        # list of provisioned DSKs for S2 secured inclusion (not SmartStart ! see uic_upvl for that)
        self.dsk_list = []

        # We pass a reference of this DevZwaveGwZpc object (self) to the MqttClientZpc to avoid duplicating attributes
        self.mqtt_client = MqttClientZpc(self)

    # start the ZPC process in ncp_update mode, the stop() method should be called before calling this else it will fail
    def ncp_update(self):
        if self.zpc_process is not None and self.zpc_process.is_alive:
            raise Exception("ZPC process is already running")

        self.logger.debug('zpc_ncp_update process starting')
        self.zpc_process = Zpc(self._ctxt, self.region, self.wpk.hostname, self.gbl_v255_file)
        self.logger.debug('zpc_ncp_update process finished')
        self.zpc_process.stop()
        if self.zpc_process.is_alive:
            raise Exception("zpc_ncp_update process did NOT die as expected")
        else:
            self.logger.debug("zpc_ncp_update process died as expected")

        # cleanup after update so that can the start() method can be called.
        self.zpc_process = None

    def start_uic_upvl(self):
        self.uic_upvl_process = UicUpvl(self._ctxt)
        if not self.uic_upvl_process.is_alive:
            raise Exception("uic_upvl process did not start or died unexpectedly")


    def start_uic_image_provider(self, devices_to_update: list[DevZwave]):
        devices = [ ]
        
        for dev in devices_to_update:
            entry = {
                'file': dev.gbl_v255_file,
                'uiid': dev.uiid(),
                'unid': dev.unid()
            }
            self.ota_status[dev.node_id] = None
            devices.append(entry)

        self.logger.info(devices)
        self.uic_image_provider_process = UicImageProvider(self._ctxt, devices)
        if not self.uic_image_provider_process.is_alive:
            raise Exception("uic_image_provider process did not start or died unexpectedly")
        # the UicImageProvider class only looks for v255 gbl files
        # so we're going to look for that information in the MQTT client

    def stop_uic_upvl(self):
        if self.uic_upvl_process is not None:
            self.uic_upvl_process.stop()
            self.uic_upvl_process = None

    def stop_uic_image_provider(self):
        if self.uic_image_provider_process is not None:
            self.uic_image_provider_process.stop()
            self.uic_image_provider_process = None

    # should be called everytime a test involves ZPC
    def stop(self):
        super().stop() # important: otherwise the rtt and pti loggers are never stopped
        # just in case a user forgets to stop these services
        self.stop_uic_image_provider()
        self.stop_uic_upvl()
        if self.mqtt_client is not None:
            self.mqtt_client.stop()
        if self.zpc_process is not None:
            self.zpc_process.stop()

    def __del__(self):
        self.stop()

    def add_node(self, dsk: str = None):
        self.mqtt_client.add_node(dsk)
    
    def remove_node(self):
        self.mqtt_client.remove_node()

    def _is_node_connected(self, node_id: int) -> bool:
        if self.network_dict.get(node_id) is not None:
            if self.network_dict[node_id] == "Online functional":
                return True
        return False

    def _is_node_disconnected(self, node_id: int) -> bool:
        if self.network_dict.get(node_id) is None:
            return True
        return False

    # ZPC state machine has a 40 sec timemout on state transitions if nothing happens to go back to idle
    def wait_for_node_connection(self, device: DevZwave, timeout: float = 40):
        end_time = time.time() + timeout
        self.logger.info(f'waiting for connection of node: {device}')

        while time.time() < end_time:
            if device.get_node_id() != 0 and self._is_node_connected(device.node_id):
                break
            os.sched_yield() # let the MQTT client thread run

        if not self._is_node_connected(device.node_id):
            raise Exception(f"timeout waiting for connection of node: {device}")

        if len(device.get_home_id()) == 0: # retrieves the home ID
            raise Exception(f"node: {device} has no home id")

        self.logger.info(f'node: {device} connected with node ID: {device.node_id}')
        self.logger.info(f'node: {device} connected with home ID: {device.home_id}')

    # no default value for timeout, it depends on the type of test
    def wait_for_node_list_connection(self, device_list: list[DevZwave], timeout: float):
        end_time = time.time() + timeout
        self.logger.info(f'waiting for connection of nodes: {device_list}')

        # dict to store the nodes states
        is_device_connected = {}
        for device in device_list:
            is_device_connected[device] = False

        while time.time() < end_time:
            for device in device_list:
                if device.get_node_id() != 0:
                    is_device_connected[device] = self._is_node_connected(device.node_id)

            if all(is_device_connected.values()):
                break

            os.sched_yield() # let the MQTT client thread run
        
        if not all(is_device_connected.values()):
            raise Exception(f"timeout waiting for connection of node(s): { [ k for k,v in is_device_connected.items() if not v ] }")

        for device in device_list:
            if len(device.get_home_id()) == 0: # retrieves the home ID
                raise Exception(f"node: {device} has no home id")

        self.logger.info(f'nodes: {device_list} connected')

    def wait_for_node_disconnection(self, device: DevZwave, timeout: float = 40):
        end_time = time.time() + timeout
        self.logger.info(f'waiting for disconnection of node: {device}')
        
        while time.time() < end_time:
            if self._is_node_disconnected(device.node_id):
                break
            os.sched_yield() # let the MQTT client thread run

        if not self._is_node_disconnected(device.node_id):
            raise Exception(f"timeout waiting for disconnection of node: {device}")
        
        self.logger.info(f'node: {device} disconnected')

    # secured OTA should not take more than 10 minutes
    def wait_for_ota_update_to_finish(self, device: DevZwave, timeout: float = 600):
        end_time = time.time() + timeout
        
        while time.time() < end_time:
            if self.ota_status[device.node_id] is True:
                break
            elif self.ota_status[device.node_id] is False:
                raise Exception("OTA was aborted")
            os.sched_yield() # let the MQTT client thread run
        
        if not self.ota_status[device.node_id]:
            raise Exception(f"timeout waiting for OTA update of node: {device}")
        self.logger.info(f'node: {device} OTA update successful')


class MqttClientZpc(object):

    def __init__(self, zpc: DevZwaveGwZpc , timeout: float = 30):
        self.zpc = zpc
        self.logger = self.zpc.logger.getChild(f'{self.__class__.__name__}')
        
        self.mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.mqttc.on_connect = self._on_connect
        self.mqttc.on_message = self._on_message

        # We could make this configurable but for now we run on the host mqtt broker
        self.mqttc.connect('127.0.0.1') # port is 1883 and keepalive is 60 by default
        self.mqttc.loop_start()

        self.logger.debug('connected to broker')

        end_time = time.time() + timeout
        while (time.time() < end_time) and (self.is_functional is not True):
            os.sched_yield() # let other threads run
        if self.is_functional is not True:
            raise Exception("MQTT client starting failed")

    def stop(self):
        if self.mqttc is not None:
            # TODO: check return values of these functions
            self.mqttc.loop_stop()
            self.mqttc.disconnect()
            self.mqttc = None

    # The callback for when the client receives a CONNACK response from the server.
    def _on_connect(self, client, userdata, flags, reason_code, properties):
        # TODO: check reason_code 
        self.logger.debug(f'connected with result code {reason_code}')
        # Subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed.
        #TODO: error message if we can't subscribe to this topic
        self.mqttc.subscribe("ucl/#")

    # The callback for when a PUBLISH message is received from the server.
    def _on_message(self, client, userdata, msg):
        # msg.topic     type: str
        # msg.payload   type: bytes (should be JSON, ascii encoded ?)
        
        # this condition updates the state of nodes in the network
        # NetworkStatus/Reported payload should always be: {"value":"State"}
        # we update the network dictionnary of ZPC with the state of the node.
        if (
            ('State/Attributes/NetworkStatus/Reported' in msg.topic) and
            (self.zpc.home_id in msg.topic)
        ):
            match = re.search(r"ucl\/by-unid\/zw-(?P<homeid>([0-9A-F]{8}))-(?P<nodeid>([0-9A-F]{4}))", msg.topic)
            if match is not None:
                home_id = match.groupdict()['homeid']
                node_id = int(match.groupdict()['nodeid'], base=16)
                if (msg.payload is not None) and (msg.payload != b''):
                    msg_payload = json.loads(msg.payload)
                    if self.zpc.home_id == home_id:
                        self.zpc.network_dict[node_id] = msg_payload['value']
                        self.logger.debug(f"{home_id} {node_id} {self.zpc.network_dict[node_id]}")
                else: # empty payload means the node has been removed
                    if self.zpc.network_dict.get(node_id):
                        self.zpc.network_dict.pop(node_id)

        
        # this condition handles secured and unsecured inclusion through learn mode
        if (
            ('ProtocolController/NetworkManagement' in msg.topic) and
            (b'"RequestedStateParameters":["SecurityCode","UserAccept","AllowMultipleInclusions"]' in msg.payload)
        ):
            # Example payload: 
            # {
            #     "RequestedStateParameters":["SecurityCode","UserAccept","AllowMultipleInclusions"],
            #     "State":"add node",
            #     "StateParameters": {"ProvisioningMode":"ZWaveDSK","SecurityCode":"xxxxx-05417-18642-54899-54659-53543-56356-17880"},
            #     "SupportedStateList":["idle"]
            # }
            security_code = "00000-00000-00000-00000-00000-00000-00000-00000"
            request = json.loads(msg.payload)
            if request["StateParameters"]["ProvisioningMode"] == "ZWaveDSK":
                dsk_end = request["StateParameters"]["SecurityCode"].replace('xxxxx-', '')
                for pdsk in self.zpc.dsk_list:
                    if dsk_end in pdsk:
                        security_code = pdsk
                        break
            topic = f'ucl/by-unid/zw-{self.zpc.home_id}-0001/ProtocolController/NetworkManagement/Write'
            payload = {"State":"add node","StateParameters":{"UserAccept":True,"SecurityCode":security_code,"AllowMultipleInclusions":False}}
            payload = bytes(json.dumps(payload), encoding='ascii')
            self.mqttc.publish(topic, payload, qos=1)
        
        # this condition handles the OTA update status (TODO: it needs a bit of refactor)
        # I need to think about a programming model for registering callbacks based on topics elsewhere.
        # this will be necessary if we want to interact with the ZPC class. Otherwise we'll be copying attributes around.
        if (
            'OTA' in msg.topic and 
            'CurrentVersion/Reported' in msg.topic
        ):
            # f"ucl/by-unid/{self.node_id_to_unid(node_id)}/ep0/OTA/Attributes/UIID/ZWave-0000-0002-0004-00-01/CurrentVersion/Reported"
            match = re.search(r"ucl\/by-unid\/zw-(?P<homeid>([0-9A-F]{8}))-(?P<nodeid>([0-9A-F]{4}))", msg.topic)
            if match is not None:
                node_id = int(match.groupdict()['nodeid'], base=16)
                if (msg.payload is not None) and (msg.payload != b''):
                    msg_payload = json.loads(msg.payload)
                    if msg_payload['value'] == "255.0.0":
                        self.zpc.ota_status[node_id] = True
                else:
                    # there's nothing to do if the payload is empty
                    pass
        
        if (
            'OTA' in msg.topic and
            'LastError/Reported' in msg.topic
        ):
            match = re.search(r"ucl\/by-unid\/zw-(?P<homeid>([0-9A-F]{8}))-(?P<nodeid>([0-9A-F]{4}))", msg.topic)
            if match is not None:
                node_id = int(match.groupdict()['nodeid'], base=16)
                if (msg.payload is not None) and (msg.payload != b''):
                    msg_payload = json.loads(msg.payload)
                    if msg_payload['value'] != "Success":
                        self.zpc.ota_status[node_id] = False

    # TODO: this function should return a node id of the next node to be added
    def add_node(self, dsk: str = None):
        if dsk is not None:
            if not dsk in self.zpc.dsk_list:
                self.zpc.dsk_list.append(dsk)
        topic   = f'ucl/by-unid/zw-{self.zpc.home_id}-0001/ProtocolController/NetworkManagement/Write'
        payload = b'{"State": "add node"}'
        self.mqttc.publish(topic, payload, qos=1)

    def remove_node(self):
        topic   = f'ucl/by-unid/zw-{self.zpc.home_id}-0001/ProtocolController/NetworkManagement/Write'
        payload = b'{"State": "remove node"}'
        self.mqttc.publish(topic, payload, qos=1)

    def smartstart_list_update(self, dsk: str):
        topic   = f'ucl/SmartStart/List/Update'
        # according to https://siliconlabs.github.io/UnifySDK/doc/unify_specifications/Chapter03-network-management.html?highlight=mqtt#
        # ProtocolControllerUnid can be set to "" since we're using a single physical controller
        # TODO: we could ask for a specific Unid (Node ID) here when including a node.
        # TODO: as for ProtocolControllerUnid we already have it so we can pass it inside the payload
        payload = { "DSK": dsk, "Include": True, "ProtocolControllerUnid": "", "Unid": "", "PreferredProtocols": [] }
        payload = bytes(json.dumps(payload), encoding='ascii')
        self.mqttc.publish(topic, payload, qos=1)

    def smartstart_list_remove(self, dsk: str):
        topic   = f'ucl/SmartStart/List/Remove'
        payload = { "DSK": dsk }
        payload = bytes(json.dumps(payload), encoding='ascii')
        self.mqttc.publish(topic, payload, qos=1)

    # function to send a basic set for example 
    def send_command(self, node_id: int, command: str, timeout: float):
        # first append a value to a list and or dict that we will create and update its state depending on the state.
        # this is begining to feel like their attribute mapper, and of course it does
        pass

    @property
    def is_functional(self) -> bool:
        return self.zpc.network_dict[self.zpc.node_id] == "Online functional"
