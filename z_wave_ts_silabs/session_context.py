from __future__ import annotations
import os
import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path


@dataclass
class Wpk:
    serial: str
    board: str

    @staticmethod
    def from_json_list(wpk_list: list[dict]) -> list[Wpk]:
        return [ Wpk(elt['serial'], elt['board']) for elt in wpk_list ]


@dataclass
class SessionContext:
    clusters_json: str = "clusters.json"
    commander_cli: str = "/opt/silabs/commander-cli/commander-cli"
    uic: str = "/opt/silabs/uic"
    zwave_binaries: str = "dist/bin"
    zwave_btl_encrypt_key_controller: str = "platform/SiliconLabs/PAL/BootLoader/controller-keys/controller_encrypt.key"
    zwave_btl_signing_key_controller: str = "platform/SiliconLabs/PAL/BootLoader/controller-keys/controller_sign.key-tokens.txt"
    zwave_btl_encrypt_key_end_device: str = "platform/SiliconLabs/PAL/BootLoader/sample-keys/sample_encrypt.key"
    zwave_btl_signing_key_end_device: str = "platform/SiliconLabs/PAL/BootLoader/sample-keys/sample_sign.key-tokens.txt"

    @staticmethod
    def from_json(config_file_path: str) -> SessionContext:
        context = SessionContext()
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
        # clusters holds every cluster described in the JSON file under the form of Cluster objects
        self.clusters: dict[str, list[Wpk]] = {}
        # TODO: logdir may have to be handled by a fixture instead, it's only useful to construct current_test_logdir
        self.logdir: Path = Path.cwd() / f"logs/{datetime.now().strftime('%Y_%m_%d-%H_%M_%S')}"
        # current_test_logdir is used by most classes to store logs, but also other files such as configuration files for ZPC.
        self.current_test_logdir: Path | None = None

        # used in DevZwave devices to enable RTT logs and PTI traces.
        self.current_test_rtt_enabled: bool = True
        self.current_test_pti_enabled: bool = True

        # create the session log directory
        self.logdir.mkdir(parents=True, exist_ok=True)

        # now we load the cluster list from the JSON file.
        # we don't use a try block on purpose, a FileNotFoundException will be raised if the cluster JSON file is not found
        with open(self.clusters_json, 'r') as f:
            clusters_dict = json.load(f)

            for name, wpk_list in clusters_dict.items():
                self.clusters[name] = Wpk.from_json_list(wpk_list)
