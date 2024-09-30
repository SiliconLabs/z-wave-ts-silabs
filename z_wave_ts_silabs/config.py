from __future__ import annotations
import os
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class Context:
    clusters: str = "clusters.json"
    commander_cli: str = "/opt/silabs/commander-cli/commander-cli"
    uic_build: str = "/opt/silabs/uic/build"
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
        self.session_logger: logging.Logger = self.setup_logging()
        self.session_logdir: str = self.setup_logs_directory()
        self.session_logdir_current_test: str | None = None

    @staticmethod
    def setup_logging() -> logging.Logger:
        logger = logging.getLogger('ts_silabs')
        formatter = logging.Formatter('%(asctime)s.%(msecs)03d %(name)s %(levelname)s %(message)s',
                                      datefmt='%Y-%m-%d %H:%M:%S')
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)  # change this to INFO to reduce the number of traces.

        return logger

    @staticmethod
    def setup_logs_directory() -> str:
        logs_directory = f"logs/{datetime.now().strftime('%Y_%m_%d-%H_%M_%S')}"
        if not os.path.exists(logs_directory):
            os.makedirs(logs_directory)
        return logs_directory


# global config context
# to access it externally use: `from z_wave_ts_silabs import ctxt`
# to access it from z_wave_ts_silabs use: `from .config import ctxt`
ctxt: Context = Context.from_json(f'{os.getcwd()}/config.json')
