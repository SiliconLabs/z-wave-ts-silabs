import os
import json
import logging
from datetime import datetime

def setup_config() -> dict:
    # acts as an example configuration (based on zw-protocol repo layout)
    config: dict = {
        "clusters": "clusters.json",
        "commander-cli": "/opt/silabs/commander-cli/commander-cli",
        "uic-build": "/opt/silabs/uic/build",
        "zwave-binaries": "dist/bin",
        "zwave-btl-encrypt-key-controller": "platform/SiliconLabs/PAL/BootLoader/controller-keys/controller_encrypt.key",
        "zwave-btl-signing-key-controller": "platform/SiliconLabs/PAL/BootLoader/controller-keys/controller_sign.key-tokens.txt",
        "zwave-btl-encrypt-key-end-device": "platform/SiliconLabs/PAL/BootLoader/sample-keys/sample_encrypt.key",
        "zwave-btl-signing-key-end-device": "platform/SiliconLabs/PAL/BootLoader/sample-keys/sample_sign.key-tokens.txt"
    }
    
    # optional JSON config file to modify defaut configuration, 
    # in effect this config file is always necessary
    json_config: dict = None
    rootdir = os.getcwd()
    config_file_path = f'{rootdir}/zwave-silabs-config.json'

    try:
        with open(config_file_path, 'r') as f:
            json_config = json.loads(f.read())
        possible_entries = config.keys()
        for entry in possible_entries:
            if json_config.get(entry):
                config[entry] = json_config[entry]
    except FileNotFoundError:
        pass
    
    print(f'rootdir: {rootdir}, configfile: {config_file_path if json_config else "none"}')

    return config


def setup_logging() -> logging.Logger:
    logger = logging.getLogger('zwave-silabs')
    formatter = logging.Formatter('%(asctime)s.%(msecs)03d %(name)s %(levelname)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG) # change this to INFO to reduce the number of traces.
    
    return logger


def setup_logs_directory() -> str:
    logs_directory = f"logs/{datetime.now().strftime('test_run_%Y_%m_%d_%H_%M_%S')}" 
    if not os.path.exists(logs_directory):
        os.makedirs(logs_directory)
    return logs_directory

# module variables
# to access them externally use: `from zwave-silabs import config`
# to access them from zwave-silabs use: `from . import config`
# then just use: `config.VAR_NAME` to access them
CONFIG: dict = setup_config()
LOGGER: logging.Logger = setup_logging()
LOGDIR: str = setup_logs_directory()

# This variable should be setup by a fixture before each test like this: f"{config.LOGDIR}/{test_name}"
LOGDIR_CURRENT_TEST: str = ""
