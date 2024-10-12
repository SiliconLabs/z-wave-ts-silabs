from __future__ import annotations
import os
import platform
import re
import json
import time
import shlex
import base64
import shutil
import socket
import hashlib
import threading
from typing import List, Dict, TextIO
from datetime import datetime
from subprocess import Popen, PIPE, STDOUT, DEVNULL

from .config import ctxt


logger = ctxt.session_logger.getChild(__name__)


class BackgroundProcess(object):

    _process_list: List[BackgroundProcess] = []

    @staticmethod
    def are_all_patterns_matched(patterns: Dict[str, re.Match | None] | None) -> bool:
        if patterns is None:
            return True

        if None in patterns.values():
            return False
        return True

    @staticmethod
    def pattern_matching(patterns: Dict[str, re.Match | None] | None, log_file: TextIO):
        if patterns is None:
            return

        for line in log_file.readlines():
            for p in patterns.keys():
                m = re.search(p, line)
                if m is not None:
                    patterns[p] = m

    @staticmethod
    def stop_all():
        while len(BackgroundProcess._process_list) != 0:
            bg_proc = BackgroundProcess._process_list.pop()
            bg_proc.stop()

    @staticmethod
    def register(process: BackgroundProcess):
        if process not in BackgroundProcess._process_list:
            BackgroundProcess._process_list.append(process)

    # patterns dict keys must be set to None
    def __init__(self, name: str, cmd_line: str, patterns: Dict[str, re.Match | None] = None, timeout: float = 10):
        self._name = name
        self._process: Popen | None = None
        self._thread: threading.Thread | None = None
        self.log_file_path = f"{ctxt.session_logdir_current_test}/{self._name}.log"
        self.wo_log_file = open(self.log_file_path, 'w')
        self.ro_log_file = open(self.log_file_path, 'r')

        logger.debug(cmd_line)
        # create thread to start background process
        self._thread = threading.Thread(target=self._start_process_in_thread, args=(cmd_line,))
        self._thread.daemon = True
        self._thread.start()

        end_time = time.time() + timeout
        while time.time() < end_time:
            if not self.is_alive:
                continue
            if BackgroundProcess.are_all_patterns_matched(patterns):
                break
            else:
                BackgroundProcess.pattern_matching(patterns, self.ro_log_file)

        # if process is still alive add it to the module list, test fixtures can then be used to kill background processes
        if self.is_alive:
            BackgroundProcess.register(self)
        # otherwise just log the event that the process has died, it's the caller responsibility to check
        # if the process is still alive with BackgroundProcess.is_alive
        else:
            logger.debug(f"process: {self._name} died")

    # there's no equivalent start() function because the constructor starts the process right away
    def stop(self):
        self.wo_log_file.close()
        self.ro_log_file.close()

        if self._process:
            self._process.kill()
            self._process.wait(1)  # 1 second should be enough to kill a process
            self._process = None

        # check that the thread that spawned the process has ended
        if self._thread and not self._thread.is_alive():
            self._thread = None

    def _start_process_in_thread(self, cmd_line: str):
        self._process = Popen(
            shlex.split(cmd_line),
            stdin=DEVNULL,
            stdout=self.wo_log_file,
            stderr=STDOUT,
        )
        self._process.wait()  # wait is a blocking call, this thread should stop after that

    @property
    def is_alive(self) -> bool:
        if self._process:
            if self._process.poll() is None:
                return True
        return False


class CommanderCli(object):

    def __init__(self, hostname) -> None:
        self.hostname = hostname
        if re.match(r'^[0-9]{9}$', self.hostname):
            self.ip_or_sn = '--serialno'
        else:
            self.ip_or_sn = '--ip'
            self.hostname = socket.gethostbyname(self.hostname)

        if not os.path.exists(ctxt.commander_cli):
            raise Exception('commander-cli not found on system')
        self._commander_cli_path = ctxt.commander_cli
        self._rtt_logger_background_process: BackgroundProcess | None = None

    def _run_commander_cli(self, cmd) -> str:
        cmd_output = ''
        cmd_line = f"{self._commander_cli_path} {cmd} {self.ip_or_sn} {self.hostname}"
        p = Popen(
            shlex.split(cmd_line),
            stdin=DEVNULL,
            stdout=PIPE,
            stderr=STDOUT,
            text=True
        )
        for line in p.stdout:
            cmd_output += line
        p.wait()
        if p.returncode != 0:
            logger.error(f'+ {cmd_line}')
            logger.error(cmd_output)
            raise Exception(f'commander-cli FAILED with exit code {p.returncode}')
        logger.debug(f'commander-cli: {cmd_line}')
        return cmd_output

    def device_info(self):
        return self._run_commander_cli('device info')

    def device_recover(self):
        return self._run_commander_cli('device recover')

    def device_pageerase(self, region: str):
        return self._run_commander_cli(f'device pageerase --region {region}')

    def device_zwave_qrcode(self):
        return self._run_commander_cli(f'device zwave-qrcode --timeout 2000')

    def flash(self, firmware_path):
        return self._run_commander_cli(f'flash {firmware_path}')

    def flash_token(self, token_group: str, token: str):
        return self._run_commander_cli(f'flash --tokengroup {token_group} --token {token}')

    def flash_tokenfiles(self, token_group: str, token_files: tuple):
        cmd_line = f'flash --tokengroup {token_group}'
        for tkfile_path in token_files:
            cmd_line += f' --tokenfile {tkfile_path}'
        return self._run_commander_cli(cmd_line)

    def spawn_rtt_logger_background_process(self, process_name: str):
        cmd_line = f"{self._commander_cli_path} rtt connect --noreset {self.ip_or_sn} {self.hostname}"
        self._rtt_logger_background_process = BackgroundProcess(name=process_name, cmd_line=cmd_line)

    def kill_rtt_logger_background_process(self):
        self._rtt_logger_background_process.stop()


class Mosquitto(BackgroundProcess):

    def __init__(self):
        mosquitto_path = shutil.which('mosquitto')
        if not os.path.exists(mosquitto_path):
            raise Exception('mosquitto not found on system')

        super().__init__('mosquitto', mosquitto_path)


class MosquittoSub(BackgroundProcess):

    def __init__(self, topic: str = 'ucl/#'):
        mosquitto_sub_path = shutil.which('mosquitto_sub')
        if not os.path.exists(mosquitto_sub_path):
            raise Exception('mosquitto_sub not found on system')

        cmd_line = f"{mosquitto_sub_path} -F '@Y-@m-@d @H:@M:@S %t %p' -t '{topic}'"
        # naming the process 'mqtt' so that the log file bears the name mqtt.log
        super().__init__('mqtt', cmd_line)


class Socat(BackgroundProcess):

    def __init__(self, hostname: str, port: int):
        socat_path = shutil.which('socat')
        if not os.path.exists(socat_path):
            raise Exception('socat not found on system')

        pty_path_regex = r"PTY is (?P<pty>(\/dev\/.+))"
        self.patterns = {
            pty_path_regex: None
        }
        cmd_line = f"{socat_path} -x -v -dd TCP:{hostname}:{port},nodelay PTY,rawer,sane"
        super().__init__('socat', cmd_line, self.patterns)
        if self.patterns[pty_path_regex] is not None:
            self.pty_path = self.patterns[pty_path_regex].groupdict()['pty']
        else:
            raise Exception(f"could not find pattern: '{pty_path_regex}' in socat output")


class UicUpvl(BackgroundProcess):

    def __init__(self):
        # the ZPC background process is in charge of creating this configuration file
        uic_config_file_path = f"{ctxt.session_logdir_current_test}/uic.cfg"
        if not os.path.exists(uic_config_file_path):
            raise FileNotFoundError

        rust_platform: str | None = None
        if platform.system() == 'Linux':
            if platform.machine() == 'x86_64': # is amd64 on windows
                rust_platform = "x86_64-unknown-linux-gnu"
            elif platform.machine() == 'arm64':
                rust_platform = "aarch64-unknown-linux-gnu"
            elif platform.machine() == 'arm':
                rust_platform = "armv7-unknown-linux-gnueabihf"
        elif platform.system() == 'Darwin':
            if platform.machine() == 'x86_64':
                rust_platform = "x86_64-apple-darwin"
            elif platform.machine() == 'arm64':
                rust_platform = "aarch64-apple-darwin"
        if rust_platform is None:
            raise OSError(f"unsupported OS: {platform.system()}")

        cmd_line = f'{ctxt.uic}/build/cargo/uic_upvl_build/{rust_platform}/debug/uic-upvl --conf {uic_config_file_path}'
        super().__init__('upvl', cmd_line)


class UicImageProvider(BackgroundProcess):

    @staticmethod
    def md5_base64(file: str) -> str | None:
        with open(file, 'rb') as f:
            md5_hash = hashlib.md5(f.read())
            return base64.b64encode(md5_hash.digest()).decode()

    def __init__(self, devices_to_update: List[Dict[str, str]]):
        # the ZPC background process is in charge of creating this configuration file
        uic_config_file_path = f"{ctxt.session_logdir_current_test}/uic.cfg"
        if not os.path.exists(uic_config_file_path):
            raise FileNotFoundError

        # devices_to_update format is 
        # [
        #   {
        #       "file": str,
        #       "uiid": str,
        #       "unid": str
        #   },
        #   ...
        # ]
        self.updates_dir_path = f'{ctxt.session_logdir_current_test}/uic-image-provider/updates'
        self.images_file_path = f'{ctxt.session_logdir_current_test}/uic-image-provider/images.json'
        self.images_json = {
            "Version": "1",
            "Images": []
        }

        # there's a mapping between app and Product type part of UIID
        # see OTA UIID Construction in: https://siliconlabs.github.io/UnifySDK/applications/zpc/readme_user.html

        # create the updates/ folder and the images.json file
        os.mkdir(f'{ctxt.session_logdir_current_test}/uic-image-provider/')
        os.mkdir(self.updates_dir_path)
        with open(self.images_file_path, 'w') as f:

            for dev in devices_to_update:
                file = dev['file']
                uuid = dev['uiid']
                unid = dev['unid']

                src_path = f'{ctxt.zwave_binaries}/{file}'
                dst_path = f'{self.updates_dir_path}/{file}'
                images_entry = {
                    "FileName": f"updates/{file}",
                    "Uiid": uuid,
                    "Unid": [unid],
                    "Version": "255.0.0",
                    "ApplyAfter": "2000-01-01T10:00:00+02:00",
                    # date is set way back so that the update starts right away
                    "Md5": UicImageProvider.md5_base64(f'{ctxt.zwave_binaries}/{file}')
                }
                self.images_json["Images"].append(images_entry)
                shutil.copyfile(src_path, dst_path)

            logger.debug(f'uic-image-provider: images.json: {self.images_json}')
            f.write(json.dumps(self.images_json))

        rust_platform: str | None = None
        if platform.system() == 'Linux':
            if platform.machine() == 'x86_64':  # is amd64 on windows
                rust_platform = "x86_64-unknown-linux-gnu"
            elif platform.machine() == 'arm64':
                rust_platform = "aarch64-unknown-linux-gnu"
            elif platform.machine() == 'arm':
                rust_platform = "armv7-unknown-linux-gnueabihf"
        elif platform.system() == 'Darwin':
            if platform.machine() == 'x86_64':
                rust_platform = "x86_64-apple-darwin"
            elif platform.machine() == 'arm64':
                rust_platform = "aarch64-apple-darwin"
        if rust_platform is None:
            raise OSError(f"unsupported OS: {platform.system()}")

        cmd_line = f'{ctxt.uic}/build/cargo/uic_image_provider_build/{rust_platform}/debug/uic-image-provider --conf {uic_config_file_path}'
        super().__init__('image_provider', cmd_line)


class Zpc(BackgroundProcess):

    def __init__(self, region: str, hostname: str, update: bool = False, update_file: str | None = None):

        self.mqtt_main_process: Mosquitto | None = None
        self.mqtt_logs_process: MosquittoSub | None = None
        self.socat_process: Socat | None = None
        self.tty_path: str = self._start_socat_process(hostname)

        uic_config_file_path = f"{ctxt.session_logdir_current_test}/uic.cfg"
        with open(uic_config_file_path, "w") as uic_cfg:
            uic_cfg.write(self._generate_uic_configuration_file(region=region, log_level='d', tx_power='0', protocol_pref='1,2'))

        cmd_line = f'{ctxt.uic}/build/applications/zpc/zpc --conf {uic_config_file_path}'
        if update:
            if update_file is None:
                raise Exception("no update file was given to zpc_ncp_update")

            sapi_ver_regex = r"\[zpc_ncp_update\] chip_serial_api_version: (?P<sapiver>(7.\d{1,3}.\d{1,3}))"
            self.patterns = {
                sapi_ver_regex: None,
                r"\[zpc_ncp_update\] Re-booting into the bootloader": None,
                r"\[uic_gbl_interface\] Transmission is done": None,
                r"\[uic_component_fixtures\] Startup sequence aborted by: ZPC NCP update": None
            }
            cmd_line += f' --zpc.ncp_update {ctxt.zwave_binaries}/{update_file}'
            # OTW should not take more than 30 seconds, giving it a minute is more than enough
            super().__init__('zpc_ncp_update', cmd_line, self.patterns, 60)
            if self.patterns[sapi_ver_regex] is not None:
                self.sapi_version = self.patterns[sapi_ver_regex].groupdict()['sapiver']
                logger.debug(f'OTW Serial API version: {self.sapi_version}')
            else:
                raise Exception(f"could not find pattern: '{sapi_ver_regex}' in zpc output")

            if self.patterns[r"\[uic_gbl_interface\] Transmission is done"] is None:
                raise Exception(f"OTW failed, check zpc_ncp_update.log")
        else:
            # it's useless to start mosquitto if we're doing an update of the ncp
            # that's why we only start it here
            self._start_mqtt_processes()

            zpc_info_regex = r"ZPC HomeID (?P<homeid>([A-F]|[0-9]){8}) - NodeID (?P<nodeid>(\d{1,3}))"
            self.patterns = {
                zpc_info_regex: None,
                r"We are connected to the MQTT broker.": None,
                r"Subscription to ucl\/by-unid\/zw-(([A-F]|[0-9]){8})-(\d{4})\/ProtocolController\/NetworkManagement\/Write successful": None
            }
            super().__init__('zpc', cmd_line, self.patterns, 30)
            if self.patterns[zpc_info_regex] is not None:
                self.home_id = self.patterns[zpc_info_regex].groupdict()['homeid']
                self.node_id = self.patterns[zpc_info_regex].groupdict()['nodeid']
            else:
                raise Exception(f"could not find pattern: '{zpc_info_regex}' in zpc output")

    def _generate_uic_configuration_file(self, region: str, log_level: str, tx_power: str, protocol_pref: str) -> str:
        uic_configuration = (
            f"# Unify configuration file (autogenerated on: {datetime.now()})\n"
            f"log:\n"
            f"  level: '{log_level}'\n"
            f"mapdir: '{ctxt.uic}/build/applications/zpc/components/dotdot_mapper/rules'\n"
            f"zpc:\n"
            f"  inclusion_protocol_preference: '{protocol_pref}'\n"
            f"  normal_tx_power_dbm: {tx_power}\n"
            f"  rf_region: '{region}'\n"
            f"  serial: '{self.tty_path}'\n"
            f"  serial_log_file: '{ctxt.session_logdir_current_test}/sapi.log'\n"
            f"  datastore_file: '{ctxt.session_logdir_current_test}/zpc.db'\n"
            f"  poll:\n"
            f"    attribute_list_file: '{ctxt.uic}/applications/zpc/components/zpc_rust/zwave_poll_config.yaml'\n"
            f"  ota:\n"
            f"    cache_path: '{ctxt.session_logdir_current_test}/zpc_ota_cache'\n"
            # maybe append this in the relevant processes instead ?
            f"upvl:\n"
            f"  datastore_file: '{ctxt.session_logdir_current_test}/upvl.db'\n"
            f"image_provider:\n"
            f"  image_path: '{ctxt.session_logdir_current_test}/uic-image-provider'\n"
        )

        return uic_configuration

    def _start_socat_process(self, hostname: str, port: int = 4901) -> str:
        self.socat_process = Socat(hostname, port)
        if not self.socat_process.is_alive:
            raise Exception("socat process did not start or died unexpectedly")
        return self.socat_process.pty_path

    def _start_mqtt_processes(self) -> None:
        self.mqtt_main_process = Mosquitto()
        if not self.mqtt_main_process.is_alive:
            raise Exception("mosquitto process did not start or died unexpectedly")
        self.mqtt_logs_process = MosquittoSub()
        if not self.mqtt_logs_process.is_alive:
            raise Exception("mosquitto_sub process did not start or died unexpectedly")

    def stop(self):
        super().stop()
        if self.socat_process is not None:
            self.socat_process.stop()
        if self.mqtt_logs_process is not None:
            self.mqtt_logs_process.stop()
        if self.mqtt_main_process is not None:
            self.mqtt_main_process.stop()
