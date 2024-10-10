#!/usr/bin/env pytest

import time

from z_wave_ts_silabs import (
    DevZwaveGwZpc,
    DevZwaveSwitchOnOff,
)


def test_swprot_7934_sapi_restarts_when_adding_zwlr_devices(get_wpks_from_cluster):
    # reset and flash devices
    # Configure ZPC to operate in US_LR
    # start ZPC
    # add a node
    # Stop ZPC
    # Configure ZPC to operate in US
    # start ZPC
    # add a node
    # Configure ZPC to operate in US_LR
    # start ZPC
    # add a node

    wpks = get_wpks_from_cluster('stdv1-5')
    zpc = DevZwaveGwZpc('zpc', wpks[-1], 'REGION_EU')
    end_device_1 = DevZwaveSwitchOnOff('end_device_1', wpks[0], 'REGION_EU')
    zpc.add_node(end_device_1.get_dsk())
    end_device_1.set_learn_mode()
    zpc.wait_for_node_connection(end_device_1)
    # print("Node added. Let's wait to check the config")

    # zpc.zpc_process.stop()
    # zpc.zpc_process.update_config(region='REGION_US_LR')
    # print("Node added. Let's wait to check the config")
    # time.sleep(30)

    # zpc.zpc_process.start()
    # time.sleep(30)
    # print("Node added. Let's wait to check the config")

    zpc.stop()
