from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Wpk:
    board: str
    serial: str


@dataclass
class GPIOMapping:
    serial: str
    BTN0: int
    BTN1: int
    BTN2: int
    BTN3: int


@dataclass
class Rpi:
    hostname: str
    GPIO_mapping: list[GPIOMapping]


@dataclass
class Cluster:
    wpks: list[Wpk]
    rpis: list[Rpi] = field(default_factory=lambda: [])  # this makes rpis optional

    @staticmethod
    def from_dict(cluster_name: str, cluster_dict: dict) -> Cluster:
        wpks = []
        rpis = []

        if 'wpks' not in cluster_dict:
            raise Exception(f"no wpks in {cluster_name}")

        for wpk in cluster_dict['wpks']:
            wpks.append(Wpk(wpk['board'], wpk['serial']))

        # if the cluster definition does not contain a RPi list then just return now
        if 'rpi' not in cluster_dict:
            return Cluster(wpks)

        for rpi in cluster_dict['rpis']:
            gpio_mapping = []
            for gpio_mapping in rpi['GPIO_mapping']:
                gpio_mapping.append(GPIOMapping(**gpio_mapping))
            rpis.append(Rpi(rpi['hostname'], gpio_mapping))

        return Cluster(wpks, rpis)
