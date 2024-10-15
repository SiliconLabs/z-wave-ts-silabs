from __future__ import annotations
from typing import Literal, List
from enum import Enum, auto

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

ZwaveApp = Literal[ZwaveNcpApp, ZwaveSocApp]

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


# see https://github.com/SiliconLabs/simplicity_sdk/blob/sisdk-2024.6/platform/radio/rail_lib/protocol/zwave/rail_zwave.h
class RAILZwaveRegionID(Enum):
    RAIL_ZWAVE_REGIONID_UNKNOWN = 0
    RAIL_ZWAVE_REGIONID_EU = 1
    RAIL_ZWAVE_REGIONID_US = 2
    RAIL_ZWAVE_REGIONID_ANZ = 3
    RAIL_ZWAVE_REGIONID_HK = 4
    RAIL_ZWAVE_REGIONID_MY = 5
    RAIL_ZWAVE_REGIONID_IN = 6
    RAIL_ZWAVE_REGIONID_JP = 7
    RAIL_ZWAVE_REGIONID_RU = 8
    RAIL_ZWAVE_REGIONID_IL = 9
    RAIL_ZWAVE_REGIONID_KR = 10
    RAIL_ZWAVE_REGIONID_CN = 11
    RAIL_ZWAVE_REGIONID_US_LR1 = 12
    RAIL_ZWAVE_REGIONID_US_LR2 = 13
    RAIL_ZWAVE_REGIONID_US_LR3 = 14
    RAIL_ZWAVE_REGIONID_US_LR_END_DEVICE = RAIL_ZWAVE_REGIONID_US_LR3
    RAIL_ZWAVE_REGIONID_EU_LR1 = 15
    RAIL_ZWAVE_REGIONID_EU_LR2 = 16
    RAIL_ZWAVE_REGIONID_EU_LR3 = 17
    RAIL_ZWAVE_REGIONID_EU_LR_END_DEVICE = RAIL_ZWAVE_REGIONID_EU_LR3


# RAIL allows up to 4 channels per region (channel hopping).
# each region has a number of predefined RAIL channels that match a particular
# Z-Wave Data Rate + central frequency + channel spacing (among other things)

# these are named 2 channels ([9.6k, 40k] and 100k) in the Z-Wave stack but RAIL list 3 channels
# - ch0 -> 100k (CRC is on 2 bytes)
# - ch1 -> 40k  (CRC is on 1 byte)
# - ch2 -> 9.6k (CRC is on 1 byte)
# - ch3 -> INVALID (impossible)
RAILZwave2CHRegionIDs = Literal[
    RAILZwaveRegionID.RAIL_ZWAVE_REGIONID_EU,
    RAILZwaveRegionID.RAIL_ZWAVE_REGIONID_US,
    RAILZwaveRegionID.RAIL_ZWAVE_REGIONID_ANZ,
    RAILZwaveRegionID.RAIL_ZWAVE_REGIONID_HK,
    RAILZwaveRegionID.RAIL_ZWAVE_REGIONID_MY,
    RAILZwaveRegionID.RAIL_ZWAVE_REGIONID_IN,
    RAILZwaveRegionID.RAIL_ZWAVE_REGIONID_RU,
    RAILZwaveRegionID.RAIL_ZWAVE_REGIONID_IL,
    RAILZwaveRegionID.RAIL_ZWAVE_REGIONID_KR,
    RAILZwaveRegionID.RAIL_ZWAVE_REGIONID_CN
]

# these are 3channel 100k regions
# - ch0 -> 100k channel 1 (CRC is on 2 bytes)
# - ch1 -> 100k channel 2 (CRC is on 2 bytes)
# - ch2 -> 100k channel 3 (CRC is on 2 bytes)
# - ch3 -> INVALID (impossible)
RAILZwave3ChRegionIDs = Literal[
    RAILZwaveRegionID.RAIL_ZWAVE_REGIONID_JP,
    RAILZwaveRegionID.RAIL_ZWAVE_REGIONID_KR
]

# same as 2 channels regions + 1 long range channel
# - ch0 -> 100k
# - ch1 -> 40k  (CRC is on 1 byte)
# - ch2 -> 9.6k (CRC is on 1 byte)
# - ch3 -> 100k LR (CRC is on 2 bytes) either LR1 -> channel A and LR2 -> channel B
RAILZwaveLRControllerRegionIDs = Literal[
    RAILZwaveRegionID.RAIL_ZWAVE_REGIONID_US_LR1,
    RAILZwaveRegionID.RAIL_ZWAVE_REGIONID_US_LR2,
    RAILZwaveRegionID.RAIL_ZWAVE_REGIONID_EU_LR1,
    RAILZwaveRegionID.RAIL_ZWAVE_REGIONID_EU_LR2
]

# end device region, only 2 channels
# - ch0 -> 100k LR channel A
# - ch1 -> 100k LR channel B
# - ch2 -> INVALID (impossible)
# - ch3 -> INVALID (impossible)
RAILZwaveLREndDeviceRegionIDs = Literal[
    RAILZwaveRegionID.RAIL_ZWAVE_REGIONID_US_LR3,
    RAILZwaveRegionID.RAIL_ZWAVE_REGIONID_EU_LR3
]
