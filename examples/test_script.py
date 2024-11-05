import pytest
from z_wave_ts_silabs import DeviceFactory, ZwaveRegion, DevZwave


@pytest.mark.parametrize('region', ['REGION_EU'])
def test_ncp_serial_api_controller_standalone(device_factory: DeviceFactory, region: ZwaveRegion):
    ncp_sapi_controller = device_factory.serial_api_controller(region)

    ncp_sapi_controller.logger.info(f"NCP SAPI Controller hostname: {ncp_sapi_controller.wpk.hostname}")
    ncp_sapi_controller.logger.info(f"NCP SAPI Controller pty: {ncp_sapi_controller.pty}")


@pytest.mark.parametrize('region', ['REGION_EU'])
def test_door_lock_keypad_basic_set(device_factory: DeviceFactory, region: ZwaveRegion):
    zpc = device_factory.zpc(region)
    end_device_1 = device_factory.door_lock_key_pad(region)

    # secure inclusion
    zpc.add_node(end_device_1.get_dsk())
    end_device_1.set_learn_mode()
    zpc.wait_for_node_connection(end_device_1)

    # TODO: check that Node was securely included


@pytest.mark.parametrize('region', ['REGION_EU'])
def test_led_bulb_inclusion(device_factory: DeviceFactory, region: ZwaveRegion):
    zpc = device_factory.zpc(region)
    end_device_1 = device_factory.led_bulb(region)

    # secure inclusion
    zpc.add_node(end_device_1.get_dsk())
    end_device_1.set_learn_mode()
    zpc.wait_for_node_connection(end_device_1)


@pytest.mark.parametrize('region', ['REGION_EU'])
def test_multilevel_sensor_inclusion(device_factory: DeviceFactory, region: ZwaveRegion):
    zpc = device_factory.zpc(region)
    end_device_1 = device_factory.multilevel_sensor(region)

    # secure inclusion
    zpc.add_node(end_device_1.get_dsk())
    end_device_1.set_learn_mode()
    zpc.wait_for_node_connection(end_device_1)


@pytest.mark.parametrize('region', ['REGION_EU'])
def test_power_strip_inclusion_and_control(device_factory: DeviceFactory, region: ZwaveRegion):
    zpc = device_factory.zpc(region)
    end_device_1 = device_factory.power_strip(region)

    # secure inclusion
    zpc.add_node(end_device_1.get_dsk())
    end_device_1.set_learn_mode()
    zpc.wait_for_node_connection(end_device_1)

    # TODO: implement the rest of the test:


@pytest.mark.parametrize('region', ['REGION_EU'])
def test_sensor_pir_battery_report(device_factory: DeviceFactory, region: ZwaveRegion):
    zpc = device_factory.zpc(region)
    end_device_1 = device_factory.sensor_pir(region)

    # secure inclusion
    zpc.add_node(end_device_1.get_dsk())
    end_device_1.set_learn_mode()
    zpc.wait_for_node_connection(end_device_1)

    # TODO: implement the rest of the test:
    # we will need some more MQTT functions

    end_device_1.battery_report()
    # TODO: check battery_report


@pytest.mark.parametrize('region', ['REGION_EU'])
def test_serial_api_controller_otw_update(device_factory: DeviceFactory, region: ZwaveRegion):
    zpc = device_factory.zpc(region)
    # ZPC has to be stopped in order to start the OTW NCP update process, then it can be started again
    zpc.stop()
    zpc.ncp_update()
    zpc.start()
    end_device_1 = device_factory.switch_on_off(region)

    # unsecure inclusion
    zpc.add_node()
    end_device_1.set_learn_mode()
    zpc.wait_for_node_connection(end_device_1)

    # TODO: basic set just to be sure


@pytest.mark.parametrize('region', ['REGION_EU'])
def test_switch_on_off_secure_inclusion_exclusion(device_factory: DeviceFactory, region: ZwaveRegion):
    zpc = device_factory.zpc(region)
    end_device_1 = device_factory.switch_on_off(region)

    # secure inclusion
    zpc.add_node(end_device_1.get_dsk())
    end_device_1.set_learn_mode()
    zpc.wait_for_node_connection(end_device_1)

    # TODO: basic set just to be sure

    # exclusion
    zpc.remove_node()
    end_device_1.set_learn_mode()
    zpc.wait_for_node_disconnection(end_device_1)


@pytest.mark.parametrize('region', ['REGION_EU'])
def test_switch_on_off_secure_ota(device_factory: DeviceFactory, region: ZwaveRegion):
    zpc = device_factory.zpc(region)
    end_device_1 = device_factory.switch_on_off(region)

    # secure inclusion
    zpc.add_node(end_device_1.get_dsk())
    end_device_1.set_learn_mode()
    zpc.wait_for_node_connection(end_device_1)

    # Start the OTA process
    # TODO: replace this by a function with a better name.
    zpc.start_uic_image_provider([end_device_1])
    zpc.wait_for_ota_update_to_finish(end_device_1)


@pytest.mark.parametrize('region', ['REGION_EU'])
def test_switch_on_off_unsecure_inclusion_exclusion(device_factory: DeviceFactory, region: ZwaveRegion):
    zpc = device_factory.zpc(region)
    end_device_1 = device_factory.switch_on_off(region)

    end_device_1.logger.info(f"nodeID before inclusion: {end_device_1.get_node_id()}")

    # unsecure inclusion
    zpc.add_node()
    end_device_1.set_learn_mode()
    zpc.wait_for_node_connection(end_device_1)

    # TODO: basic set just to be sure

    end_device_1.logger.info(f"nodeID after inclusion: {end_device_1.get_node_id()}")

    # exclusion
    zpc.remove_node()
    end_device_1.set_learn_mode()
    zpc.wait_for_node_disconnection(end_device_1)

    end_device_1.logger.info(f"nodeID after exclusion: {end_device_1.get_node_id()}")


@pytest.mark.parametrize('region', ['REGION_EU'])
def test_switch_on_off_unsecure_ota(device_factory: DeviceFactory, region: ZwaveRegion):
    zpc = device_factory.zpc(region)
    end_device_1 = device_factory.switch_on_off(region)

    # unsecure inclusion
    zpc.add_node()
    end_device_1.set_learn_mode()
    zpc.wait_for_node_connection(end_device_1)

    # start the OTA process
    zpc.start_uic_image_provider([end_device_1])
    zpc.wait_for_ota_update_to_finish(end_device_1)


@pytest.mark.parametrize('region', ['REGION_EU'])
def test_switch_on_off_smartstart_inclusion(device_factory: DeviceFactory, region: ZwaveRegion):
    zpc = device_factory.zpc(region)
    # TODO: uic_upvl should be implicitly started when updating the SmartStart List.
    zpc.start_uic_upvl()

    end_device_list: list[DevZwave] = []
    dsk_list: list[str] = []

    nb_end_devices = 1

    for i in range(nb_end_devices):
        end_device = device_factory.switch_on_off(region)
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

    zpc.stop()
    for ed in end_device_list:
        ed.stop()


@pytest.mark.parametrize('region', ['REGION_EU'])
def test_wall_controller_basic_set(device_factory: DeviceFactory, region: ZwaveRegion):
    zpc = device_factory.zpc(region)
    end_device_1 = device_factory.wall_controller(region)

    # secure inclusion
    zpc.add_node(end_device_1.get_dsk())
    end_device_1.set_learn_mode()
    zpc.wait_for_node_connection(end_device_1)

    # TODO: test a cli command for this app
