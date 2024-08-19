from typing import Literal
from enum import Enum

ZwaveNcpApp = Literal[
    'zwave_ncp_serial_api_controller',
    'zwave_ncp_serial_api_end_device',
    'zwave_ncp_serial_api_test_controller',
    'zwave_ncp_zniffer',
    'zwave_ncp_zniffer_pti',
]

ZwaveSocApp = Literal[
    'zwave_soc_door_lock_keypad',
    'zwave_soc_led_bulb',
    'zwave_soc_multilevel_sensor',
    'zwave_soc_power_strip',
    'zwave_soc_sensor_pir',
    'zwave_soc_switch_on_off',
    'zwave_soc_wall_controller'
]

ZwaveApp = Literal[ ZwaveNcpApp, ZwaveSocApp ]

ZwaveRegion = Literal[
    'REGION_EU',
    'REGION_EU_LR`',
    'REGION_US',
    'REGION_US_LR',
    'REGION_ANZ',
    'REGION_HK',
    'REGION_IN',
    'REGION_IL',
    'REGION_RU',
    'REGION_CN',
    'REGION_JP',
    'REGION_KR'
]


# see ZAF/ApplicationUtilities/ZW_product_id_enum.h in zw-protocol: typedef enum _PRODUCT_PLUS_ID_ENUM_
class ZwaveAppProductType(Enum):
    zwave_soc_door_lock_keypad = 1
    zwave_soc_switch_on_off = 2
    zwave_soc_sensor_pir = 3
    zwave_ncp_serial_api = 4
    zwave_soc_power_strip = 5
    zwave_soc_wall_controller = 6
    zwave_soc_led_bulb = 7
    zwave_soc_multilevel_sensor = 8
    # zwave_soc_key_fob = 9
