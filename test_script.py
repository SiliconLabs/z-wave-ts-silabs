from typing import List, Dict

import pytest
from z_wave_ts_silabs import DevZwaveGwZpc, DevZwaveDoorLockKeypad, DevZwaveLedBulb, DevZwaveMultilevelSensor, \
    DevZwavePowerStrip, DevZwaveSensorPIR, DevZwaveSwitchOnOff, DevZwaveWallController, DevWpk, ZwaveRegion


@pytest.mark.parametrize('region', ['REGION_EU'])
def test_door_lock_keypad_basic_set(hw_cluster_wpks: List[DevWpk], region: ZwaveRegion):
    wpks = hw_cluster_wpks
    zpc = DevZwaveGwZpc('zpc', wpks[-1], region)
    end_device_1 = DevZwaveDoorLockKeypad('end_device_1', wpks[0], region)

    # secure inclusion
    zpc.add_node(end_device_1.get_dsk())
    end_device_1.set_learn_mode()
    zpc.wait_for_node_connection(end_device_1)

    # TODO: check that Node was securely included

    zpc.stop_zlf_capture()
    zpc.stop_log_capture()
    end_device_1.stop_zlf_capture()
    end_device_1.stop_log_capture()

    zpc.stop()


@pytest.mark.parametrize('region', ['REGION_EU'])
def test_led_buld_inclusion(hw_cluster_wpks: List[DevWpk], region: ZwaveRegion):
    wpks = hw_cluster_wpks
    zpc = DevZwaveGwZpc('zpc', wpks[-1], region)
    end_device_1 = DevZwaveLedBulb('end_device_1', wpks[0], region)

    # secure inclusion
    zpc.add_node(end_device_1.get_dsk())
    end_device_1.set_learn_mode()
    zpc.wait_for_node_connection(end_device_1)

    zpc.stop_zlf_capture()
    zpc.stop_log_capture()
    end_device_1.stop_zlf_capture()
    end_device_1.stop_log_capture()

    zpc.stop()


@pytest.mark.parametrize('region', ['REGION_EU'])
def test_multilevel_sensor_inclusion(hw_cluster_wpks: List[DevWpk], region: ZwaveRegion):
    wpks = hw_cluster_wpks
    zpc = DevZwaveGwZpc('zpc', wpks[-1], region)
    end_device_1 = DevZwaveMultilevelSensor('end_device_1', wpks[0], region)

    # secure inclusion
    zpc.add_node(end_device_1.get_dsk())
    end_device_1.set_learn_mode()
    zpc.wait_for_node_connection(end_device_1)

    zpc.stop_zlf_capture()
    zpc.stop_log_capture()
    end_device_1.stop_zlf_capture()
    end_device_1.stop_log_capture()

    zpc.stop()


@pytest.mark.parametrize('region', ['REGION_EU'])
def test_power_strip_inclusion_and_control(hw_cluster_wpks: List[DevWpk], region: ZwaveRegion):
    wpks = hw_cluster_wpks
    zpc = DevZwaveGwZpc('zpc', wpks[-1], region)
    end_device_1 = DevZwavePowerStrip('end_device_1', wpks[0], region)

    # secure inclusion
    zpc.add_node(end_device_1.get_dsk())
    end_device_1.set_learn_mode()
    zpc.wait_for_node_connection(end_device_1)

    # TODO: implement the rest of the

    zpc.stop_zlf_capture()
    zpc.stop_log_capture()
    end_device_1.stop_zlf_capture()
    end_device_1.stop_log_capture()

    zpc.stop()


@pytest.mark.parametrize('region', ['REGION_EU'])
def test_sensor_pir_battery_report(hw_cluster_wpks: List[DevWpk], region: ZwaveRegion):
    wpks = hw_cluster_wpks
    zpc = DevZwaveGwZpc('zpc', wpks[-1], region)
    end_device_1 = DevZwaveSensorPIR('end_device_1', wpks[0], region)

    # secure inclusion
    zpc.add_node(end_device_1.get_dsk())
    end_device_1.set_learn_mode()
    zpc.wait_for_node_connection(end_device_1)

    # TODO: implement the rest of the test:
    # we will need some more MQTT functions

    end_device_1.battery_report()
    # TODO: check battery_report

    zpc.stop_zlf_capture()
    zpc.stop_log_capture()
    end_device_1.stop_zlf_capture()
    end_device_1.stop_log_capture()

    zpc.stop()


@pytest.mark.parametrize('region', ['REGION_EU'])
def test_serial_api_controller_otw_update(hw_cluster_wpks: List[DevWpk], region: ZwaveRegion):
    wpks = hw_cluster_wpks
    # setting update to True does an OTW with a v255 firmware
    zpc = DevZwaveGwZpc('zpc', wpks[-1], region, update=True)
    end_device_1 = DevZwaveSwitchOnOff('end_device_1', wpks[0], region)

    # unsecure inclusion
    zpc.add_node()
    end_device_1.set_learn_mode()
    zpc.wait_for_node_connection(end_device_1)

    # TODO: basic set just to be sure

    zpc.stop_zlf_capture()
    zpc.stop_log_capture()
    end_device_1.stop_zlf_capture()
    end_device_1.stop_log_capture()

    zpc.stop()


@pytest.mark.parametrize('region', ['REGION_EU'])
def test_switch_on_off_secure_inclusion_exclusion(hw_cluster_wpks: List[DevWpk], region: ZwaveRegion):
    wpks = hw_cluster_wpks
    zpc = DevZwaveGwZpc('zpc', wpks[-1], region)
    end_device_1 = DevZwaveSwitchOnOff('end_device_1', wpks[0], region)

    # secure inclusion
    zpc.add_node(end_device_1.get_dsk())
    end_device_1.set_learn_mode()
    zpc.wait_for_node_connection(end_device_1)

    # TODO: basic set just to be sure

    # exclusion
    zpc.remove_node()
    end_device_1.set_learn_mode()
    zpc.wait_for_node_disconnection(end_device_1)

    zpc.stop_zlf_capture()
    zpc.stop_log_capture()
    end_device_1.stop_zlf_capture()
    end_device_1.stop_log_capture()

    zpc.stop()


@pytest.mark.parametrize('region', ['REGION_EU'])
def test_switch_on_off_secure_ota(hw_cluster_wpks: List[DevWpk], region: ZwaveRegion):
    wpks = hw_cluster_wpks
    zpc = DevZwaveGwZpc('zpc', wpks[-1], region)
    end_device_1 = DevZwaveSwitchOnOff('end_device_1', wpks[0], region)

    # secure inclusion
    zpc.add_node(end_device_1.get_dsk())
    end_device_1.set_learn_mode()
    zpc.wait_for_node_connection(end_device_1)

    zpc.start_uic_image_updater([end_device_1])
    zpc.wait_for_ota_update_to_finish(end_device_1)

    zpc.stop_zlf_capture()
    zpc.stop_log_capture()
    end_device_1.stop_zlf_capture()
    end_device_1.stop_log_capture()

    zpc.stop_uic_image_updater()
    zpc.stop()


@pytest.mark.parametrize('region', ['REGION_EU'])
def test_switch_on_off_unsecure_inclusion_exclusion(hw_cluster_wpks: List[DevWpk], region: ZwaveRegion):
    wpks = hw_cluster_wpks
    zpc = DevZwaveGwZpc('zpc', wpks[-1], region)
    end_device_1 = DevZwaveSwitchOnOff('end_device_1', wpks[0], region)

    # unsecure inclusion
    zpc.add_node()
    end_device_1.set_learn_mode()
    zpc.wait_for_node_connection(end_device_1)

    # TODO: basic set just to be sure

    # exclusion
    zpc.remove_node()
    end_device_1.set_learn_mode()
    zpc.wait_for_node_disconnection(end_device_1)

    zpc.stop_zlf_capture()
    zpc.stop_log_capture()
    end_device_1.stop_zlf_capture()
    end_device_1.stop_log_capture()

    zpc.stop()


@pytest.mark.parametrize('region', ['REGION_EU'])
def test_switch_on_off_unsecure_ota(hw_cluster_wpks: List[DevWpk], region: ZwaveRegion):
    wpks = hw_cluster_wpks
    zpc = DevZwaveGwZpc('zpc', wpks[-1], region)
    end_device_1 = DevZwaveSwitchOnOff('end_device_1', wpks[0], region)

    # unsecure inclusion
    zpc.add_node()
    end_device_1.set_learn_mode()
    zpc.wait_for_node_connection(end_device_1)

    zpc.start_uic_image_updater([end_device_1])
    zpc.wait_for_ota_update_to_finish(end_device_1)

    zpc.stop_zlf_capture()
    zpc.stop_log_capture()
    end_device_1.stop_zlf_capture()
    end_device_1.stop_log_capture()

    zpc.stop_uic_image_updater()
    zpc.stop()


@pytest.mark.parametrize('region', ['REGION_EU'])
def test_switch_on_off_smartstart_inclusion(hw_cluster_wpks: List[DevWpk], region: ZwaveRegion):
    wpks = hw_cluster_wpks

    zpc = DevZwaveGwZpc('zpc', wpks[-1], region)
    zpc.start_uic_upvl()

    end_device_list: List[DevZwaveSwitchOnOff] = []
    dsk_list: List[str] = []

    nb_end_devices = 1

    for i in range(nb_end_devices):
        end_device = DevZwaveSwitchOnOff('end_device_1', wpks[i], region)
        end_device_list.append(end_device)
        dsk_list.append(end_device.get_dsk())

    for dsk in dsk_list:
        zpc.mqtt_client.smartstart_list_update(dsk)

    for ed in end_device_list:
        # reset the radio board to send the smart start message again
        ed.wpk.target_reset()

    # giving the test system 5 minutes to include 1 node in smartstart should be enough
    zpc.wait_for_node_list_connection(end_device_list, 300)

    # cleanup SmartStart list
    for dsk in dsk_list:
        zpc.mqtt_client.smartstart_list_remove(dsk)

    zpc.stop_uic_upvl()
    zpc.stop()


@pytest.mark.parametrize('region', ['REGION_EU'])
def test_wall_controller_basic_set(hw_cluster_wpks: List[DevWpk], region: ZwaveRegion):
    wpks = hw_cluster_wpks
    zpc = DevZwaveGwZpc('zpc', wpks[-1], region)
    end_device_1 = DevZwaveWallController('end_device_1', wpks[0], region)

    # secure inclusion
    zpc.add_node(end_device_1.get_dsk())
    end_device_1.set_learn_mode()
    zpc.wait_for_node_connection(end_device_1)

    # TODO: test a cli command for this app

    zpc.stop_zlf_capture()
    zpc.stop_log_capture()
    end_device_1.stop_zlf_capture()
    end_device_1.stop_log_capture()

    zpc.stop()
