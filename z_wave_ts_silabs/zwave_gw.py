import os
import re
import json
import time
import paho.mqtt.client as mqtt
from typing import Dict, List


from .devices import ZwaveDevBase, DevWpk
from .processes import Zpc, UicUpvl, UicImageProvider


class DevZwaveGwZpc(ZwaveDevBase):
    """ZPC Z-Wave Gateway (based on UnifySDK)."""

    def __init__(self, name: str, wpk: DevWpk, region: str, usb: bool = False, update: bool = False) -> None:
        """Initializes the device.
        :param name: The device name
        :param wpk: The wpk with the radio board acting as NCP
        :param uart_ncp: The NCP uart
        """

        self.zpc_process: Zpc = None
        self.uic_upvl_process: UicUpvl = None
        self.uic_image_provider_process: UicImageProvider = None
        self.mqtt_client: MqttClientZpc = None

        super().__init__(name, wpk, region, 'zwave_ncp_serial_api_controller')

        # zpc_process when started with update=True does not return other information
        if update:
            self.loggger.debug('zpc_ncp_update process starting')
            self.zpc_process = Zpc(self.region, self.wpk.tty if usb else self.wpk.hostname, update, self.gbl_v255_file)
            self.loggger.debug('zpc_ncp_update process finished')
            self.zpc_process.stop()
            if self.zpc_process.is_alive:
                raise Exception("zpc_ncp_update process did NOT die as expected")
            else:
                self.loggger.debug("zpc_ncp_update process died as expected")

        self.loggger.debug('zpc process starting')
        self.zpc_process = Zpc(self.region, self.wpk.tty if usb else self.wpk.hostname)
        if not self.zpc_process.is_alive:
            raise Exception("zpc process did not start or died unexpectedly")
        self.loggger.debug('zpc process started')

        self.home_id = self.zpc_process.home_id
        self.loggger.debug(f'Home ID: {self.home_id}')
        
        self.node_id = int(self.zpc_process.node_id)
        self.loggger.debug(f'Node ID: {self.node_id}')

        self.network_next_node_id = self.node_id + 1

        # according to: uic/components/unify_dotdot_attribute_store/src/unify_dotdot_attribute_store_node_state.cpp
        # Nodes can be in these states 
        # "Online interviewing", "Online functional", "Online non-functional", "Online interviewing", "Offline", "Unavailable"
        self.network_dict = { self.node_id: "Offline" }
        self.ota_status = {} # node_id: None (default), True if finished, False if issue -> it sucks, make it a property or something
        self.command_status = {} # node_id: { "command" : "state" }, and then do something about the state.
        # list of provisioned DSKs for S2 secured inclusion (not SmartStart ! see uic_upvl for that)
        self.dsk_list = []

        # We pass a reference of this DevZwaveGwZpc object (self) to the MqttClientZpc to avoid duplicating attributes
        self.mqtt_client = MqttClientZpc(self)


    def start_uic_upvl(self):
        self.uic_upvl_process = UicUpvl()
        if not self.uic_upvl_process.is_alive:
            raise Exception("uic_upvl process did not start or died unexpectedly")


    def start_uic_image_updater(self, devices_to_update: List[ZwaveDevBase]):
        devices = [ ]
        
        for dev in devices_to_update:
            entry = {}
            entry['file'] = dev.gbl_v255_file
            entry['uiid'] = dev.uiid()
            entry['unid'] = dev.unid()
            self.ota_status[dev.node_id] = None
            devices.append(entry)

        self.loggger.info(devices)
        self.uic_image_provider_process = UicImageProvider(devices)
        if not self.uic_image_provider_process.is_alive:
            raise Exception("uic_image_provider process did not start or died unexpectedly")
        # the UicImageProvider class only looks for v255 gbl files
        # so we're going to look for that information in the MQTT client

    def stop_uic_upvl(self):
        if self.uic_upvl_process is not None:
            self.uic_upvl_process.stop()
            self.uic_upvl_process = None

    def stop_uic_image_updater(self):
        if self.uic_image_provider_process is not None:
            self.uic_image_provider_process.stop()
            self.uic_image_provider_process = None

    # should be called everytime a test involves ZPC
    def stop(self):
        # just in case a user forgets to stop these services
        self.stop_uic_image_updater()
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
    def wait_for_node_connection(self, device: ZwaveDevBase, timeout: float = 40):
        node_id = self.network_next_node_id
        
        end_time = time.time() + timeout
        self.loggger.info(f'waiting for connection of node: {node_id}')
        
        while (time.time() < end_time) and not self._is_node_connected(node_id):
            os.sched_yield() # let the MQTT client thread run
        
        if not self._is_node_connected(node_id):
            raise Exception(f"timeout waiting for connection of node: {node_id}")
        
        self.loggger.info(f'node: {node_id} connected')

        # do not forget to increment self.network_next_node_id before returning
        self.network_next_node_id += 1

        device.node_id = node_id
        device.home_id = self.home_id

    # no default value for timeout, it depends on the type of tests
    def wait_for_node_list_connection(self, device_list: List[ZwaveDevBase], timeout: float):
        end_time = time.time() + timeout

        node_id_list = [ x for x in range(self.network_next_node_id, self.network_next_node_id + len(device_list)) ]        
        self.loggger.info(f'waiting for connection of nodes: {node_id_list}')

        # dict to store the nodes states
        is_node_id_connected = {}
        for node_id in node_id_list:
            is_node_id_connected[node_id] = False

        while (time.time() < end_time):
            for node_id in is_node_id_connected.keys():
                is_node_id_connected[node_id] = self._is_node_connected(node_id)

            if all(is_node_id_connected.values()):
                break

            os.sched_yield() # let the MQTT client thread run
        
        if not all(is_node_id_connected.values()):
            raise Exception(f"timeout waiting for connection of node(s): { [ k for k,v in is_node_id_connected.items() if not v ] }")
        
        self.loggger.info(f'nodes: {node_id_list} connected')

        # do not forget to increment self.network_next_node_id before returning
        self.network_next_node_id += len(device_list)

        # this is where it gets tricky, how do we know which device is the one with a particular homeid ?
        # for now we do something super stupid but we'll have to find a way to do that smart.
        for device, node_id in zip(device_list, node_id_list):
            device.node_id = node_id
            device.home_id = self.home_id

    def wait_for_node_disconnection(self, device: ZwaveDevBase, timeout: float = 40):
        node_id = device.node_id
        end_time = time.time() + timeout
        self.loggger.info(f'waiting for disconnection of nodes: {node_id}')
        
        while (time.time() < end_time) and not self._is_node_disconnected(node_id):
            os.sched_yield() # let the MQTT client thread run

        if not self._is_node_disconnected(node_id):
            raise Exception(f"timeout waiting for disconnection of node: {node_id}")
        
        self.loggger.info(f'node: {node_id} disconnected')

    # secured OTA should not take more than 10 minutes
    def wait_for_ota_update_to_finish(self, device: ZwaveDevBase, timeout: float = 600):
        node_id = device.node_id
        end_time = time.time() + timeout
        
        while (time.time() < end_time):
            if self.ota_status[node_id] is True:
                break
            elif self.ota_status[node_id] is False:
                raise Exception("OTA was aborted")
            os.sched_yield() # let the MQTT client thread run
        
        if not self.ota_status[node_id]:
            raise Exception(f"timeout waiting for OTA update of node: {node_id}")
        self.loggger.info(f'node: {node_id} OTA update successful')


class MqttClientZpc(object):

    def __init__(self, zpc: DevZwaveGwZpc , timeout: float = 30):
        self.zpc = zpc
        self.logger = self.zpc.loggger.getChild('mqtt_client')
        
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
            match = re.search(r"ucl\/by-unid\/zw-(?P<homeid>([A-F]|[0-9]){8})-(?P<nodeid>(\d{4}))", msg.topic)
            if match is not None:
                home_id = match.groupdict()['homeid']
                node_id = int(match.groupdict()['nodeid'])
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
            security_code = ""
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
            match = re.search(r"ucl\/by-unid\/zw-(?P<homeid>([A-F]|[0-9]){8})-(?P<nodeid>(\d{4}))", msg.topic)
            if match is not None:
                node_id = int(match.groupdict()['nodeid'])
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
            match = re.search(r"ucl\/by-unid\/zw-(?P<homeid>([A-F]|[0-9]){8})-(?P<nodeid>(\d{4}))", msg.topic)
            if match is not None:
                node_id = int(match.groupdict()['nodeid'])
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
        payload = { "DSK": dsk, "Include": True, "ProtocolControllerUnid": "", "Unid": "", "PreferredProtocols": ["Z-Wave", "Z-Wave Long Range"] }
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
