from __future__ import annotations
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

type Clusters = dict[str, list[Wpk]]

@dataclass
class Wpk:
    serial: str
    board: str
    ip: bool = True # we consider that the WPK can be accessed through IP by default

    @staticmethod
    def from_json_list(wpk_list: list[dict]) -> list[Wpk]:
        return [ Wpk(elt['serial'], elt['board'], bool(elt['ip']) if elt.get('ip') else False) for elt in wpk_list ]


@dataclass
class SessionContext:
    clusters_json: Path = Path('clusters.json') # clusters.json file which contains the description of available clusters
    commander_cli: Path = Path('/opt/silabs/commander-cli/commander-cli') # commander-cli binary
    uic: Path = Path('/opt/silabs/uic') # UIC directory, MUST contain a build directory with executables of zpc, uic-image-provider and uic-upvl
    zwave_binaries: Path = Path('dist/bin') # directory with all Z-Wave firmwares binaries (and railtest too, maybe it should have its own entry)
    zwave_btl_encrypt_key_controller: Path = Path('platform/SiliconLabs/PAL/BootLoader/controller-keys/controller_encrypt.key') # bootloader encryption/decryption key on controller (needed for OTW updates)
    zwave_btl_signing_key_controller: Path = Path('platform/SiliconLabs/PAL/BootLoader/controller-keys/controller_sign.key-tokens.txt') # bootloader signing key on controller (needed for OTW updates)
    zwave_btl_encrypt_key_end_device: Path = Path('platform/SiliconLabs/PAL/BootLoader/sample-keys/sample_encrypt.key') # bootloader encryption/decryption key on end devices (needed for OTA updates)
    zwave_btl_signing_key_end_device: Path = Path('platform/SiliconLabs/PAL/BootLoader/sample-keys/sample_sign.key-tokens.txt') # bootloader signing key on end devices (needed for OTA updates)

    @staticmethod
    def from_json(config_file_path: Path) -> SessionContext:

        with config_file_path.open('r') as f:
            json_config: dict = json.loads(f.read())

        return SessionContext(
            clusters_json=Path(json_config['clusters_json']),
            commander_cli=Path(json_config['commander_cli']),
            uic=Path(json_config['uic']),
            zwave_binaries=Path(json_config['zwave_binaries']),
            zwave_btl_encrypt_key_controller = Path(json_config['zwave_btl_encrypt_key_controller']),
            zwave_btl_signing_key_controller = Path(json_config['zwave_btl_signing_key_controller']),
            zwave_btl_encrypt_key_end_device = Path(json_config['zwave_btl_encrypt_key_end_device']),
            zwave_btl_signing_key_end_device = Path(json_config['zwave_btl_signing_key_end_device']),
        )

    def __post_init__(self):
        # TODO: logdir may have to be handled by a fixture instead, it's only useful to construct current_test_logdir
        self.logdir: Path = Path.cwd() / f"logs/{datetime.now().strftime('%Y_%m_%d-%H_%M_%S')}"
        # current_test_logdir is used by most classes to store logs, but also other files such as configuration files for ZPC.
        self.current_test_logdir: Path | None = None

        # used in DevZwave devices to enable RTT logs and PTI traces.
        self.current_test_rtt_enabled: bool = True
        self.current_test_pti_enabled: bool = True

        # create the session log directory
        self.logdir.mkdir(parents=True, exist_ok=True)
