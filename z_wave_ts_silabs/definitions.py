from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from enum import IntEnum

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
class ZwaveAppProductType(IntEnum):
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
class RAILZwaveRegionID(IntEnum):
    INV = 0 # INVALID region ID in RAIL
    EU = 1
    US = 2
    ANZ = 3
    HK = 4
    MY = 5
    IN = 6
    JP = 7
    RU = 8
    IL = 9
    KR = 10
    CN = 11
    US_LR1 = 12
    US_LR2 = 13
    US_LR3 = 14
    US_LR_END_DEVICE = US_LR3
    EU_LR1 = 15
    EU_LR2 = 16
    EU_LR3 = 17
    EU_LR_END_DEVICE = EU_LR3

    # RAIL allows up to 4 channels per region (channel hopping).
    # each region has a number of predefined RAIL channels that match a particular
    # Z-Wave Data Rate + central frequency + channel spacing (among other things)

    def is_2ch(self):
        """Check if Region is a RAIL 2-channels region (Z-Wave LR End Device)"""
        return self in [self.US_LR3, self.EU_LR3]

    def is_3ch(self):
        """Check if Region is a RAIL 3-channels region (Z-Wave Classic)"""
        return not self.is_2ch() and not self.is_4ch()

    def is_4ch(self):
        """Check if Region is a RAIL 4-channels region (Z-Wave LR Controller)"""
        return self in [self.US_LR1, self.US_LR2, self.EU_LR1, self.EU_LR2]

    def is_4ch_with_lr_channel_a(self):
        """Check if Region is a RAIL 4-channels region with LR channel A (Z-Wave LR Controller)"""
        return self in [self.US_LR1, self.EU_LR1]

    def is_4ch_with_lr_channel_b(self):
        """Check if Region is a RAIL 4-channels region with LR channel B (Z-Wave LR Controller)"""
        return self in [self.US_LR2, self.EU_LR2]

    @classmethod
    def get_2ch_list(cls) -> list[RAILZwaveRegionID]:
        """Return a list of RAIL 2-channels regions."""
        return list(filter(lambda r: r.is_2ch(), iter(RAILZwaveRegionID)))

    @classmethod
    def get_3ch_list(cls) -> list[RAILZwaveRegionID]:
        """Return a list of RAIL 3-channels regions."""
        return list(filter(lambda r: r.is_3ch(), iter(RAILZwaveRegionID)))

    @classmethod
    def get_4ch_list(cls) -> list[RAILZwaveRegionID]:
        """Return a list of RAIL 4-channels regions."""
        return list(filter(lambda r: r.is_4ch(), iter(RAILZwaveRegionID)))


class RAILZwaveBaud(IntEnum):
    BAUD_9600 = 0       # R1
    BAUD_40K = 1        # R2
    BAUD_100K = 2       # R3
    BAUD_100K_LR = 3    # R3 for LR ? (RAIL treats the baud rate of LR with a different enum value)


@dataclass
class RAILZwaveChannel:
    frequency: int          # in KHz
    baud: RAILZwaveBaud     # 9.6K, 40K, 100K and 100K_LR


# RAILZwaveRegion.channels is a dict that MUST always be of length 4
@dataclass
class RAILZwaveRegion:
    name: str                               # RAIL region name  (from RAILZwaveRegionID.name)
    channels: dict[int, RAILZwaveChannel]   # maps a RAIL channel index with a RAILZwaveChannel


# maps a RAIL region ID (from RAILZwaveRegionID.value) with a RAILZwaveRegion
RAILZwaveRegions: dict[int, RAILZwaveRegion] = {
    RAILZwaveRegionID.INV: RAILZwaveRegion(RAILZwaveRegionID.INV.name, {
        0: RAILZwaveChannel(916000, RAILZwaveBaud.BAUD_100K),
        1: RAILZwaveChannel(908400, RAILZwaveBaud.BAUD_40K),
        2: RAILZwaveChannel(908420, RAILZwaveBaud.BAUD_9600),
        3: None
    }),
    RAILZwaveRegionID.EU: RAILZwaveRegion(RAILZwaveRegionID.EU.name, {
        0: RAILZwaveChannel(869850, RAILZwaveBaud.BAUD_100K),
        1: RAILZwaveChannel(868400, RAILZwaveBaud.BAUD_40K),
        2: RAILZwaveChannel(868420, RAILZwaveBaud.BAUD_9600),
        3: None
    }),
    RAILZwaveRegionID.US: RAILZwaveRegion(RAILZwaveRegionID.US.name, {
        0: RAILZwaveChannel(916000, RAILZwaveBaud.BAUD_100K),
        1: RAILZwaveChannel(908400, RAILZwaveBaud.BAUD_40K),
        2: RAILZwaveChannel(908420, RAILZwaveBaud.BAUD_9600),
        3: None
    }),
    RAILZwaveRegionID.ANZ: RAILZwaveRegion(RAILZwaveRegionID.ANZ.name, {
        0: RAILZwaveChannel(919800, RAILZwaveBaud.BAUD_100K),
        1: RAILZwaveChannel(921400, RAILZwaveBaud.BAUD_40K),
        2: RAILZwaveChannel(921420, RAILZwaveBaud.BAUD_9600),
        3: None
    }),
    RAILZwaveRegionID.HK: RAILZwaveRegion(RAILZwaveRegionID.HK.name, {
        0: RAILZwaveChannel(919800, RAILZwaveBaud.BAUD_100K),
        1: RAILZwaveChannel(919800, RAILZwaveBaud.BAUD_40K),
        2: RAILZwaveChannel(919820, RAILZwaveBaud.BAUD_9600),
        3: None
    }),
    RAILZwaveRegionID.MY: RAILZwaveRegion(RAILZwaveRegionID.MY.name, {
        0: RAILZwaveChannel(919800, RAILZwaveBaud.BAUD_100K),
        1: RAILZwaveChannel(921400, RAILZwaveBaud.BAUD_40K),
        2: RAILZwaveChannel(921420, RAILZwaveBaud.BAUD_9600),
        3: None
    }),
    RAILZwaveRegionID.IN: RAILZwaveRegion(RAILZwaveRegionID.IN.name, {
        0: RAILZwaveChannel(865200, RAILZwaveBaud.BAUD_100K),
        1: RAILZwaveChannel(865200, RAILZwaveBaud.BAUD_40K),
        2: RAILZwaveChannel(865220, RAILZwaveBaud.BAUD_9600),
        3: None
    }),
    RAILZwaveRegionID.JP: RAILZwaveRegion(RAILZwaveRegionID.JP.name, {
        0: RAILZwaveChannel(922500, RAILZwaveBaud.BAUD_100K),
        1: RAILZwaveChannel(923900, RAILZwaveBaud.BAUD_100K),
        2: RAILZwaveChannel(926300, RAILZwaveBaud.BAUD_100K),
        3: None
    }),
    RAILZwaveRegionID.RU: RAILZwaveRegion(RAILZwaveRegionID.RU.name, {
        0: RAILZwaveChannel(869000, RAILZwaveBaud.BAUD_100K),
        1: RAILZwaveChannel(869000, RAILZwaveBaud.BAUD_40K),
        2: RAILZwaveChannel(869020, RAILZwaveBaud.BAUD_9600),
        3: None
    }),
    RAILZwaveRegionID.IL: RAILZwaveRegion(RAILZwaveRegionID.IL.name, {
        0: RAILZwaveChannel(916000, RAILZwaveBaud.BAUD_100K),
        1: RAILZwaveChannel(916000, RAILZwaveBaud.BAUD_40K),
        2: RAILZwaveChannel(916020, RAILZwaveBaud.BAUD_9600),
        3: None
    }),
    RAILZwaveRegionID.KR: RAILZwaveRegion(RAILZwaveRegionID.KR.name, {
        0: RAILZwaveChannel(920900, RAILZwaveBaud.BAUD_100K),
        1: RAILZwaveChannel(921700, RAILZwaveBaud.BAUD_100K),
        2: RAILZwaveChannel(923100, RAILZwaveBaud.BAUD_100K),
        3: None
    }),
    RAILZwaveRegionID.CN: RAILZwaveRegion(RAILZwaveRegionID.CN.name, {
        0: RAILZwaveChannel(868400, RAILZwaveBaud.BAUD_100K),
        1: RAILZwaveChannel(868400, RAILZwaveBaud.BAUD_40K),
        2: RAILZwaveChannel(868420, RAILZwaveBaud.BAUD_9600),
        3: None
    }),
    RAILZwaveRegionID.US_LR1: RAILZwaveRegion(RAILZwaveRegionID.US_LR1.name, {
        0: RAILZwaveChannel(916000, RAILZwaveBaud.BAUD_100K),
        1: RAILZwaveChannel(908400, RAILZwaveBaud.BAUD_40K),
        2: RAILZwaveChannel(908420, RAILZwaveBaud.BAUD_9600),
        3: RAILZwaveChannel(912000, RAILZwaveBaud.BAUD_100K_LR)
    }),
    RAILZwaveRegionID.US_LR2: RAILZwaveRegion(RAILZwaveRegionID.US_LR2.name, {
        0: RAILZwaveChannel(916000, RAILZwaveBaud.BAUD_100K),
        1: RAILZwaveChannel(908400, RAILZwaveBaud.BAUD_40K),
        2: RAILZwaveChannel(908420, RAILZwaveBaud.BAUD_9600),
        3: RAILZwaveChannel(920000, RAILZwaveBaud.BAUD_100K_LR)
    }),
    RAILZwaveRegionID.US_LR3: RAILZwaveRegion(RAILZwaveRegionID.US_LR3.name, {
        0: RAILZwaveChannel(912000, RAILZwaveBaud.BAUD_100K_LR),
        1: RAILZwaveChannel(920000, RAILZwaveBaud.BAUD_100K_LR),
        2: None,
        3: None
    }),
    RAILZwaveRegionID.EU_LR1: RAILZwaveRegion(RAILZwaveRegionID.EU_LR1.name, {
        0: RAILZwaveChannel(869850, RAILZwaveBaud.BAUD_100K),
        1: RAILZwaveChannel(868400, RAILZwaveBaud.BAUD_40K),
        2: RAILZwaveChannel(868420, RAILZwaveBaud.BAUD_9600),
        3: RAILZwaveChannel(864400, RAILZwaveBaud.BAUD_100K_LR)
    }),
    RAILZwaveRegionID.EU_LR2: RAILZwaveRegion(RAILZwaveRegionID.EU_LR2.name, {
        0: RAILZwaveChannel(869850, RAILZwaveBaud.BAUD_100K),
        1: RAILZwaveChannel(868400, RAILZwaveBaud.BAUD_40K),
        2: RAILZwaveChannel(868420, RAILZwaveBaud.BAUD_9600),
        3: RAILZwaveChannel(866400, RAILZwaveBaud.BAUD_100K_LR)
    }),
    RAILZwaveRegionID.EU_LR3: RAILZwaveRegion(RAILZwaveRegionID.EU_LR3.name, {
        0: RAILZwaveChannel(864400, RAILZwaveBaud.BAUD_100K_LR),
        1: RAILZwaveChannel(866400, RAILZwaveBaud.BAUD_100K_LR),
        2: None,
        3: None
    })
}
