from __future__ import annotations
from typing import List
from dataclasses import dataclass, field
import json


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
    GPIO_mapping: List[GPIOMapping]


@dataclass
class Cluster:
    wpks: List[Wpk]
    rpis: List[Rpi] = field(default_factory=lambda: [])  # this makes rpis optional

    @staticmethod
    def from_json(json_file: str, cluster_name: str) -> Cluster:
        wpks = []
        rpis = []

        with open(json_file, 'r') as f:
            clusters_json = json.load(f)

        if cluster_name not in clusters_json:
            raise Exception(f"no cluster named {cluster_name} in {json_file}")
        cluster_dict = clusters_json[cluster_name]

        if 'wpks' not in cluster_dict:
            raise Exception(f"no wpks in {json_file}")

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
