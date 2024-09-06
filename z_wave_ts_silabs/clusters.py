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
    rpis: List[Rpi] = field(default_factory=lambda: []) # this makes rpis optional

    def __post_init__(self):
        # Only useful if Cluster is created with from_json()
        for i, elt in enumerate(self.wpks):
            if type(elt) == dict:
                self.wpks[i] = Wpk(**elt)
        for i, elt in enumerate(self.rpis):
            if type(elt) == dict:
                self.rpis[i] = Rpi(**elt)

    @staticmethod
    def from_json(json_file: str, cluster_name: str) -> Cluster:
        with open(json_file, 'r') as f:
            clusters_json = json.load(f)
        return Cluster(**clusters_json[cluster_name])
