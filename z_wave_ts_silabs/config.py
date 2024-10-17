from __future__ import annotations
import os
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict
from pathlib import Path

from .clusters import Cluster


@dataclass
class Context:
    clusters_json: str = "clusters.json"
    commander_cli: str = "/opt/silabs/commander-cli/commander-cli"
    uic: str = "/opt/silabs/uic"
    zwave_binaries: str = "dist/bin"
    zwave_btl_encrypt_key_controller: str = "platform/SiliconLabs/PAL/BootLoader/controller-keys/controller_encrypt.key"
    zwave_btl_signing_key_controller: str = "platform/SiliconLabs/PAL/BootLoader/controller-keys/controller_sign.key-tokens.txt"
    zwave_btl_encrypt_key_end_device: str = "platform/SiliconLabs/PAL/BootLoader/sample-keys/sample_encrypt.key"
    zwave_btl_signing_key_end_device: str = "platform/SiliconLabs/PAL/BootLoader/sample-keys/sample_sign.key-tokens.txt"

    @staticmethod
    def from_json(config_file_path: str) -> Context:
        context = Context()
        json_config: dict | None = None
        try:
            with open(config_file_path, 'r') as f:
                json_config = json.loads(f.read())
                possible_entries = asdict(context).keys()
                for entry in possible_entries:
                    if json_config.get(entry):
                        setattr(context, entry, json_config[entry])
        except FileNotFoundError:
            pass

        print(f'rootdir: {os.getcwd()}, configfile: {config_file_path if json_config else "none"}')

        return context

    def __post_init__(self):
        self.session_logdir: Path = Path.cwd() / f"logs/{datetime.now().strftime('%Y_%m_%d-%H_%M_%S')}"
        self.session_logdir_current_test: Path | None = None
        self.clusters: Dict[str, Cluster] = {}

        # create the session log directory
        self.session_logdir.mkdir(parents=True, exist_ok=True)

        # now we load the cluster list from the JSON file.
        # we don't use a try block on purpose, a FileNotFoundException will be raised if the cluster JSON file is not found
        with open(self.clusters_json, 'r') as f:
            clusters_dict = json.load(f)

            for k, v in clusters_dict.items():
                self.clusters[k] = Cluster.from_dict(k, v)


# global config context
# to access it externally use: `from z_wave_ts_silabs import ctxt`
# to access it from z_wave_ts_silabs use: `from .config import ctxt`
ctxt: Context = Context.from_json(f'{os.getcwd()}/config.json')
